"""Only synthetic temporary artifacts; never invokes the tennis pipeline."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from beating.model import ResidualLogistic
from beating.tennis_evaluate import describe, gates
from tools.audit_tennis_forecasts import CANDIDATES, PENALTIES, audit, choose, summarize


def synthetic_outputs(root):
    docs, output = root/"docs", root/"reports"
    docs.mkdir(); output.mkdir()
    hashes = {}
    for field, name in (("protocol_sha256", "protocol-tennis-v1.md"),
                        ("independent_protocol_sha256", "protocol-tennis-independent-v1.md"),
                        ("implementation_review_sha256", "tennis-implementation-review.md")):
        path = docs/name
        path.write_text("Synthetic protocol fixture only\n")
        hashes[field] = hashlib.sha256(path.read_bytes()).hexdigest()
    values = []
    for year in (2024, 2025):
        for n, (market, gap, y, close) in enumerate(((.5, .8, np.nan, True), (.5, -.8, 0, False),
                                                   (.5, .3, 1, True), (.1, .9, 0, True),
                                                   (.5, 0., 1, True))):
            source_day = datetime(year, 4, 1+n*4, tzinfo=ZoneInfo("Europe/Prague"))
            label = (source_day+timedelta(days=1)).astimezone(timezone.utc)+timedelta(hours=48)
            mlogit = np.log(market/(1-market))
            values.append({"event_id": f"synthetic-{year}-{n}", "year": year,
                "date": source_day.date().isoformat(), "start_at": f"{source_day.date()}T12:00:00Z",
                "opening_at": f"{source_day.date()}T08:00:00Z", "y": y,
                "label_available_at": label.isoformat() if np.isfinite(y) else None,
                "label_source_date": source_day.date().isoformat() if np.isfinite(y) else None,
                "odds_a": 1/(market*1.04), "odds_b": 1/((1-market)*1.04), "market_p": market,
                "market_logit": mlogit, "kernel_p": 1/(1+np.exp(-(mlogit+gap))),
                "structure_gap": gap, "workload_total": .5+n*.1, "workload_difference": n*.1,
                "close_a": 1/(market*1.03) if close else np.nan,
                "close_b": 1/((1-market)*1.03) if close else np.nan, "closing_valid": close,
                "close_a_at": f"{source_day.date()}T11:00:00Z" if close else None,
                "close_b_at": f"{source_day.date()}T11:15:00Z" if close else None})
    frame = pd.DataFrame(values)
    trials = [{"candidate": name, "penalty": penalty, "validation_log_loss": score+index*.01,
               "development_events": 100, "validation_events": 20}
              for index, name in enumerate(CANDIDATES) for penalty, score in zip(PENALTIES, [.6, .3, .4, .5])]
    selected = {name: min([r for r in trials if r["candidate"] == name], key=lambda r: r["validation_log_loss"])
                for name in CANDIDATES}
    annual = {}
    for year in (2024, 2025):
        models = {}
        for name, columns in CANDIDATES.items():
            coef = {"calibration": [0., 0.], "set_shape": [.01*(year-2024), 0., .8],
                    "workload": [-.1+.03*(year-2024), 0., .8, .1, -.1]}[name]
            model = {"penalty": .01, "mean": [0.]*len(columns), "scale": [1.]*len(columns), "coef": coef}
            models[name] = model
            mask = frame.year.eq(year)
            frame.loc[mask, "p_"+name] = ResidualLogistic.from_dict(model).predict_proba(
                frame.loc[mask, columns], frame.loc[mask, "market_p"])
        annual[str(year)] = {"status": "fitted", "first_forecast_quote": f"{year}-04-01T08:00:00Z",
                            "model_unavailable_event_ids": [], "training_events": 120+(year-2024)*5,
                            "training_years": list(range(2021, year)),
                            "maximum_label_available_at": f"{year}-01-05T00:00:00Z", "models": models}
    fit = {"status": "unproven", "features": CANDIDATES, "annual_models": annual,
           "validation_trials": trials, "selected_penalties": selected, "selected_research_candidate": "calibration",
           "selection_available_at": "2024-01-05T00:00:00Z", "final_fit_as_of": "2026-01-01T00:00:00Z",
           "final_maximum_label_available_at": "2025-04-20T00:00:00Z",
           "final_models_scope": "Post-holdout refits; never used for reported holdout forecasts",
           "final_models": {name: {**model, "coef": [9.]+model["coef"][1:]}
                            for name, model in annual["2025"]["models"].items()}}
    for experiment in ("n2", "n3"):
        csv_path = output/f"tennis-{experiment}-forecasts.csv"
        frame.to_csv(csv_path, index=False)
        record = {"experiment": experiment.upper(), "status": "unproven", "entry_book": "Pinnacle",
                  "fanduel_execution_evidence": False, "alerts_enabled": False, "passes_forward_promotion": False,
                  "acquisition": {}, "source_evidence_blocks": [], "fit": fit,
                  "forecasts_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(), "models": {}, **hashes}
        for name in ("market", *CANDIDATES):
            col = "market_p" if name == "market" else "p_"+name
            node = describe(frame, frame[col])
            node["research_screen"] = gates(node)
            node["source_evidence_blocks"] = []
            node["favorable_evidence_unblocked"] = all(node["research_screen"].values())
            node["by_year"] = {str(year): describe(group, group[col]) for year, group in frame.groupby("year")}
            record["models"][name] = node
        (output/f"tennis-{experiment}-fit.json").write_text(json.dumps(fit, allow_nan=False))
        (output/f"tennis-{experiment}-metrics.json").write_text(json.dumps(record, allow_nan=False))
    return output


class TennisForecastAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.template = Path(cls.temporary.name)/"template"
        cls.template.mkdir()
        synthetic_outputs(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        import shutil
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(self.template, self.root, dirs_exist_ok=True)
        self.output = self.root/"reports"

    def change_metrics(self, mutation):
        path = self.output/"tennis-n2-metrics.json"
        record = json.loads(path.read_text()); mutation(record)
        path.write_text(json.dumps(record, allow_nan=False))

    def test_consistent_outputs_zero_bet_and_ungraded_candidates_pass(self):
        result = audit(self.output, self.root)
        self.assertTrue(result["passed"], result["failed_checks"])
        counts = result["experiments"]["n2"]["candidates"]
        self.assertEqual(counts["market"]["bets"], 0)
        self.assertGreater(counts["set_shape"]["unsettled_bets"], 0)
        self.assertGreater(result["checks"], 2500)
        json.dumps(result, allow_nan=False)

    def test_corrupt_metrics_and_ungraded_confidence_claims_are_rejected(self):
        for field, replacement in (("brier", .9), ("haircut_profit_units_settled", 77),
                                    ("turnover_units", 0), ("haircut_roi_unresolved_outcome_bounds", [1., 2.]),
                                    ("haircut_roi_ci", [.1, .2])):
            original = (self.template/"reports/tennis-n2-metrics.json").read_text()
            (self.output/"tennis-n2-metrics.json").write_text(original)
            with self.subTest(field=field):
                self.change_metrics(lambda r: r["models"]["set_shape"].update({field: replacement}))
                result = audit(self.output, self.root)
                self.assertFalse(result["passed"])
                self.assertTrue(any(field in s for s in result["failed_checks"]), result["failed_checks"])

    def test_forecast_probability_corruption_is_caught_after_hash_is_resealed(self):
        path = self.output/"tennis-n2-forecasts.csv"
        frame = pd.read_csv(path)
        frame.loc[0, "p_set_shape"] += .02
        frame.to_csv(path, index=False)
        self.change_metrics(lambda r: r.update(forecasts_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        result = audit(self.output, self.root)
        self.assertFalse(result["passed"])
        self.assertTrue(any("annual coefficient prediction" in s for s in result["failed_checks"]))

    def test_annual_training_and_selection_future_information_are_caught(self):
        path = self.output/"tennis-n2-fit.json"
        fit = json.loads(path.read_text())
        fit["annual_models"]["2024"]["maximum_label_available_at"] = "2024-04-01T08:00:00Z"
        fit["selected_research_candidate"] = "workload"
        path.write_text(json.dumps(fit))
        self.change_metrics(lambda r: r.update(fit=fit))
        result = audit(self.output, self.root)
        self.assertFalse(result["passed"])
        self.assertTrue(any("annual training precedes quote" in s for s in result["failed_checks"]))
        self.assertTrue(any("candidate chosen from validation" in s for s in result["failed_checks"]))

    def test_entry_normalization_and_poststart_close_are_rejected(self):
        path = self.output/"tennis-n2-forecasts.csv"
        original = path.read_text()
        for field, value, failure in (("market_p", .55, "entry no-vig"),
                                       ("close_a_at", "2024-04-01T12:00:00Z", "prestart close_a_at"),
                                       ("closing_valid", "unknown", "explicit closing flag")):
            path.write_text(original)
            frame = pd.read_csv(path)
            if field == "closing_valid":
                frame[field] = frame[field].astype(object)
            frame.loc[0, field] = value
            frame.to_csv(path, index=False)
            self.change_metrics(lambda r: r.update(forecasts_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            with self.subTest(field=field):
                result = audit(self.output, self.root)
                self.assertFalse(result["passed"])
                self.assertTrue(any(failure in s for s in result["failed_checks"]), result["failed_checks"])

    def test_closing_ev_and_annual_brier_corruption_are_rejected(self):
        def mutate(record):
            node = record["models"]["set_shape"]
            node["closing_pinnacle_power"]["mean_closing_ev"] = .99
            node["by_year"]["2025"]["brier"] = .999
        self.change_metrics(mutate)
        result = audit(self.output, self.root)
        self.assertFalse(result["passed"])
        self.assertTrue(any("closing_pinnacle_power.mean_closing_ev" in s for s in result["failed_checks"]))
        self.assertTrue(any("annual 2025 set_shape.brier" in s for s in result["failed_checks"]))

    def test_missing_annual_candidate_and_unverified_alert_are_caught(self):
        def mutate(record):
            del record["models"]["workload"]["by_year"]["2025"]
            record["alerts_enabled"] = True
        self.change_metrics(mutate)
        result = audit(self.output, self.root)
        self.assertFalse(result["passed"])
        self.assertTrue(any("alerts_enabled" in s for s in result["failed_checks"]))
        self.assertTrue(any("annual metric coverage" in s for s in result["failed_checks"]))

    def test_insufficient_data_does_not_load_stale_forecasts(self):
        for experiment in ("n2", "n3"):
            path = self.output/f"tennis-{experiment}-metrics.json"
            record = json.loads(path.read_text())
            record.update(status="insufficient_evaluable_data", reason="Synthetic missing validation")
            record.pop("fit"); record.pop("models")
            path.write_text(json.dumps(record))
            (self.output/f"tennis-{experiment}-forecasts.csv").write_text("unreadable stale file")
        result = audit(self.output, self.root)
        self.assertTrue(result["passed"], result["failed_checks"])
        self.assertEqual(result["experiments"]["n3"]["status"], "insufficient_evaluable_data")

    def test_stdlib_cli_runs_without_site_packages(self):
        script = Path(__file__).resolve().parents[1]/"tools/audit_tennis_forecasts.py"
        report = self.root/"audit.json"
        result = subprocess.run([sys.executable, "-S", str(script), "--root", str(self.root),
                                 "--output", str(self.output), "--report", str(report)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(json.loads(report.read_text())["passed"])

    def test_independent_tie_policy_and_empty_summary(self):
        row = {"odds_a": 2., "odds_b": 2.}
        over, odds, ev, selected = choose(row, .5)
        self.assertTrue(over); self.assertFalse(selected)
        value = summarize([], [])
        self.assertEqual(value["bets"], 0)
        self.assertEqual(value["roi_unresolved_outcome_bounds"], [None, None])
        json.dumps(value, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
