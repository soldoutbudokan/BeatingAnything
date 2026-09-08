"""Synthetic integrity and chronology checks, separate from real experiments."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from beating import tennis_pipeline as pipeline


class TennisPipelineAuditTests(unittest.TestCase):
    def acquisition_fixture(self, directory, *, detail_date="2021-01-05", parse_errors=None):
        root = Path(directory)
        day = "2021-01-05"
        fixture = {"event_id": "te:1", "match_id": "1", "date": day,
                   "source_url": "https://example.invalid/match-detail/?id=1", "challenger": True,
                   "player1": "a", "player2": "b"}
        daily = {"date": day, "records": [], "errors": parse_errors or [], "fixture_count": 1}
        detail = {"event_id": "te:1", "match_id": "1", "date": detail_date, "player1": "a", "player2": "b"}
        raws = {f"daily/{day}.html": b"synthetic-daily", "details/1.html": b"synthetic-detail"}
        for relative, raw in raws.items():
            path = root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        pin = {"date": day, "protocol": "N2-v1", "source_sha256": hashlib.sha256(raws[f"daily/{day}.html"]).hexdigest(),
               "matches": pipeline.select_sample([fixture], day)}
        saved_detail = {**detail, "sample_date": day, "source_sha256": hashlib.sha256(raws["details/1.html"]).hexdigest()}
        for relative, value in ((f"sample/{day}.json", pin), (f"parsed-daily/{day}.json", daily),
                                ("parsed-details/1.json", saved_detail)):
            path = root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
        first, last = date(2021, 1, 1), date(2025, 12, 31)
        files = [f"daily/{(first + timedelta(days=n)).isoformat()}.html" for n in range((last-first).days+1)] + ["details/1.html"]
        attempts = [{"file": name, "status": "downloaded", "sha256": hashlib.sha256(raws[name]).hexdigest()}
                    if name in raws else {"file": name, "status": "failed"} for name in files]
        (root/"acquisition.jsonl").write_text("\n".join(json.dumps(row) for row in attempts)+"\n")
        return fixture, daily, detail

    def load_fixture(self, root, fixture, daily, detail):
        with patch.object(pipeline, "parse_fixtures", return_value=[fixture]), \
                patch.object(pipeline, "parse_daily_results", return_value=daily), \
                patch.object(pipeline, "parse_match_detail", return_value=detail):
            return pipeline.acquisition_inputs(root)

    def test_attempted_failures_are_audited_without_fabricating_empty_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, daily, detail = self.acquisition_fixture(directory, detail_date="2021-01-06",
                                                              parse_errors=[{"event_id": "te:bad", "reason": "ambiguous"}])
            history, details, audit = self.load_fixture(directory, fixture, daily, detail)
            self.assertEqual(history, [])
            self.assertEqual(audit["sampled_unique_events"], 1)
            self.assertEqual(len(details), 1)
            self.assertEqual(len(audit["unknown_sample_dates"]), 1825)
            self.assertEqual(audit["daily_parse_errors"], [{"date": "2021-01-05", "errors": daily["errors"]}])
            self.assertEqual(audit["sample_detail_date_discrepancies"],
                             [{"event_id": "te:1", "sample_date": "2021-01-05", "detail_date": "2021-01-06"}])
            self.assertTrue(details[0]["sample_fixture_identity_valid"])

    def test_hash_sample_and_parsed_history_cannot_be_edited_under_same_raw_hash(self):
        for relative, mutation, expected_error in (
            ("sample/2021-01-05.json", lambda value: value.update(matches=[]), "Frozen sample"),
            ("parsed-daily/2021-01-05.json", lambda value: value.update(records=[{"event_id": "invented"}]), "Parsed daily"),
            ("parsed-details/1.json", lambda value: value.update(player1="wrong-player"), "Parsed detail"),
            ("parsed-details/1.json", lambda value: value.update(sample_date="2021-01-08"), "Parsed detail"),
        ):
            with self.subTest(relative=relative, error=expected_error), tempfile.TemporaryDirectory() as directory:
                fixture, daily, detail = self.acquisition_fixture(directory)
                path = Path(directory)/relative
                value = json.loads(path.read_text())
                mutation(value)
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, expected_error):
                    self.load_fixture(directory, fixture, daily, detail)

    def test_known_sample_survives_history_parse_failure_and_still_requires_detail_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, daily, detail = self.acquisition_fixture(directory)
            root = Path(directory)
            (root/"parsed-daily/2021-01-05.json").unlink()
            _, details, audit = self.load_fixture(root, fixture, daily, detail)
            self.assertEqual(len(details), 1)
            self.assertEqual(audit["sampled_unique_events"], 1)
            self.assertIn("2021-01-05", audit["failed_daily_dates"])
            self.assertNotIn("2021-01-05", audit["unknown_sample_dates"])
            ledger = root/"acquisition.jsonl"
            attempts = [json.loads(line) for line in ledger.read_text().splitlines()]
            ledger.write_text("\n".join(json.dumps(row) for row in attempts if row["file"] != "details/1.html"))
            with self.assertRaisesRegex(ValueError, "detail pages not yet attempted"):
                self.load_fixture(root, fixture, daily, detail)

    def test_raw_pin_and_parsed_outputs_cannot_replace_first_successful_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, daily, detail = self.acquisition_fixture(directory)
            root = Path(directory)
            replacement = b"a later synthetic source snapshot"
            (root/"daily/2021-01-05.html").write_bytes(replacement)
            pin_path = root/"sample/2021-01-05.json"
            pin = json.loads(pin_path.read_text())
            pin["source_sha256"] = hashlib.sha256(replacement).hexdigest()
            pin_path.write_text(json.dumps(pin))
            with self.assertRaisesRegex(ValueError, "first successful acquisition hash"):
                self.load_fixture(root, fixture, daily, detail)

    def test_detail_players_are_bound_to_sample_fixture_before_kernel_or_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture, daily, detail = self.acquisition_fixture(directory)
            fixture["player1"] = "different-original-player"
            _, details, audit = self.load_fixture(directory, fixture, daily, detail)
            self.assertEqual(audit["sample_detail_identity_mismatches"], ["te:1"])
            details[0]["entry_valid_n3"] = True
            with patch.object(pipeline, "fit_n3") as kernel:
                frame, feature_audit = pipeline.prepare_features([], details, "n3")
            self.assertTrue(frame.empty)
            kernel.assert_not_called()
            self.assertEqual(feature_audit["rejected_events"][0]["reasons"], ["sample_fixture_identity_mismatch_or_unknown"])

    def fit_frame(self):
        rows = []
        for year, label in ((2021, 0), (2022, 1), (2023, 0), (2024, 1), (2025, 0)):
            rows.append({"event_id": str(year), "year": year, "date": f"{year}-02-01",
                         "opening_at": f"{year}-02-01T10:00:00+00:00", "y": float(label),
                         "label_available_at": f"{year}-02-04T00:00:00+00:00",
                         "label_source_date": f"{year}-02-01", "market_p": .5,
                         "market_logit": year / 1000, "structure_gap": .1,
                         "workload_total": 1., "workload_difference": .5})
        return pd.DataFrame(rows)

    def test_every_graded_validation_label_needs_finite_value_and_known_availability(self):
        for field, value, error in (("label_available_at", None, "availability timestamp"),
                                    ("y", np.inf, "finite binary"), ("y", 2, "finite binary")):
            frame = self.fit_frame()
            frame.loc[frame.year.eq(2023), field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, error):
                pipeline.fit_and_forecast(frame, fit_as_of="2026-09-08T00:00:00Z")

    def test_final_artifact_records_real_fit_cutoff_and_actual_label_source_date(self):
        class FakeModel:
            def __init__(self, penalty):
                self.penalty = penalty

            def fit(self, x, y, market):
                self.markers = x.iloc[:, 0].tolist()
                return self

            def predict_proba(self, x, market):
                return np.full(len(x), .5)

            def to_dict(self):
                return {"penalty": self.penalty, "synthetic_training_markers": self.markers}

        frame = self.fit_frame()
        frame.loc[frame.year.eq(2025), "label_source_date"] = "2025-02-10"
        frame.loc[frame.year.eq(2025), "label_available_at"] = "2025-02-13T00:00:00+00:00"
        with patch.object(pipeline, "ResidualLogistic", FakeModel):
            predictions, fit = pipeline.fit_and_forecast(frame, fit_as_of="2026-09-08T00:00:00Z")
        self.assertEqual(fit["final_fit_as_of"], "2026-09-08T00:00:00+00:00")
        self.assertEqual(fit["training_through_source_date"], "2025-02-10")
        self.assertEqual(fit["final_maximum_label_available_at"], "2025-02-13T00:00:00+00:00")
        self.assertEqual(fit["final_training_events"], 5)
        self.assertIn("never used for reported holdout forecasts", fit["final_models_scope"])
        self.assertEqual(fit["annual_models"]["2024"]["training_events"], 3)
        self.assertEqual(fit["annual_models"]["2025"]["training_events"], 4)
        self.assertEqual(set(predictions.event_id), {"2024", "2025"})
        with self.assertRaisesRegex(ValueError, "outcomes unavailable"):
            pipeline.fit_and_forecast(frame, fit_as_of="2025-02-12T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
