"""Synthetic checks for research-report scope and unresolved exposure."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from beating import tennis_pipeline as pipeline
from beating.tennis_evaluate import describe, gates
from beating.tennis_report import render, write_report


def synthetic_node(p=.5, y=1):
    frame = pd.DataFrame([{"event_id": "synthetic-only", "date": "2024-04-01", "y": y,
                           "odds_a": 1.91, "odds_b": 1.91, "market_p": .5,
                           "close_a": 1.91, "close_b": 1.91}])
    node = describe(frame, [p], with_ci=False)
    node["research_screen"] = gates(node)
    node["favorable_evidence_unblocked"] = False
    node["by_year"] = {"2024": describe(frame, [p], with_ci=False)}
    return node


def synthetic_record(experiment):
    return {
        "experiment": experiment, "status": "unproven",
        "acquisition": {"daily_dates_required": 1826, "sampled_unique_events": 4, "parsed_details": 4},
        "feature_audit": {"counts": {"feature_accepted": 4}}, "source_evidence_blocks": [],
        "fit": {"selected_research_candidate": "workload", "selection_available_at": "2023-12-30T00:00:00Z",
                "annual_models": {
                    "2024": {"status": "fitted", "model_unavailable_event_ids": ["early-synthetic-quote"]},
                    "2025": {"status": "missing_feature_valid_test_events", "model_unavailable_event_ids": []}}},
        "models": {"market": synthetic_node(), "calibration": synthetic_node(.8, np.nan),
                   "set_shape": synthetic_node(.6, 1), "workload": synthetic_node(.5, 1)},
    }


class TennisReportTests(unittest.TestCase):
    def test_all_candidates_zero_bets_and_ungraded_turnover_are_visible(self):
        text = render([synthetic_record("N2"), synthetic_record("N3")])
        self.assertIn("## N2", text)
        self.assertIn("## N3", text)
        for candidate in ("market", "calibration", "set_shape", "workload"):
            self.assertIn(f"| 2024 | {candidate} |", text)
        self.assertIn("| workload | 1 / 1 | 0 / 0 |", text)
        self.assertIn("| calibration | 1 / 0 | 1 / 0 | unavailable | unavailable | unavailable |", text)
        self.assertIn("| calibration | 1 | 1 | [-1.000000, 0.891800] | 0 | unavailable |", text)
        self.assertIn("outcome bounds, not confidence intervals", text)
        self.assertNotIn("nan", text.lower())

    def test_missing_annual_fold_is_explicit_and_does_not_change_gates(self):
        records = [synthetic_record("N2"), synthetic_record("N3")]
        records[0]["models"]["workload"]["favorable_evidence_unblocked"] = True
        original = copy.deepcopy(records)
        text = render(records)
        self.assertIn("**2024:** `fitted`", text)
        self.assertIn("**2025:** `missing_feature_valid_test_events`; forecasts / graded: 0 / 0", text)
        self.assertIn("cannot be described as a successful two-year evaluation", text)
        self.assertIn("on its available forecasts", text)
        self.assertEqual(records, original)

    def test_wholly_ungraded_year_is_not_described_as_complete(self):
        records = [synthetic_record("N2"), synthetic_record("N3")]
        for record in records:
            record["fit"]["annual_models"]["2025"]["status"] = "fitted"
            for node in record["models"].values():
                annual = copy.deepcopy(node["by_year"]["2024"])
                annual["settled_events"] = 0
                node["by_year"]["2025"] = annual
        text = render(records)
        self.assertIn("**2025:** `fitted`; forecasts / graded: 1 / 0", text)
        self.assertIn("The declared 2024–2025 evaluation is incomplete", text)

    def test_two_graded_folds_have_no_incomplete_scope_warning(self):
        records = [synthetic_record("N2"), synthetic_record("N3")]
        for record in records:
            record["fit"]["annual_models"]["2025"]["status"] = "fitted"
            for name in record["models"]:
                record["models"][name] = synthetic_node(.5, 1)
                node = record["models"][name]
                node["by_year"]["2025"] = copy.deepcopy(node["by_year"]["2024"])
        text = render(records)
        self.assertNotIn("evaluation is incomplete", text)
        self.assertEqual(text.count("graded comparison available: yes"), 4)

    def test_insufficient_records_keep_reasons_and_both_declared_years(self):
        insufficient = synthetic_record("N3")
        insufficient.update(status="insufficient_evaluable_data", reason="No graded validation events")
        insufficient.pop("models")
        insufficient.pop("fit")
        mixed = render([synthetic_record("N2"), insufficient])
        self.assertIn("No graded validation events", mixed)
        self.assertIn("**2025:** `not_evaluated`", mixed)
        first = copy.deepcopy(insufficient)
        first["experiment"] = "N2"
        text = render([first, insufficient])
        self.assertIn("Neither experiment had enough evaluable data", text)
        self.assertEqual(text.count("No fitted holdout comparison is available"), 2)

    def test_file_writer_and_pipeline_insufficient_branches_render_both_experiments(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            records = [synthetic_record("N2"), synthetic_record("N3")]
            for record in records:
                (output/f"tennis-{record['experiment'].lower()}-metrics.json").write_text(
                    json.dumps(record, allow_nan=False))
            path = write_report(output)
            self.assertEqual(path.read_text(), render(records))
            acquisition = {"daily_dates_required": 1826, "sampled_unique_events": 0, "parsed_details": 0}
            with patch.object(pipeline, "acquisition_inputs", return_value=([], [], acquisition)), \
                    patch.object(pipeline, "prepare_features", return_value=(pd.DataFrame(), {"counts": {}})), \
                    patch.object(pipeline, "digest", return_value="synthetic-hash"), patch("builtins.print"):
                pipeline.run(output/"synthetic-source", output)
            self.assertEqual(path.read_text().count("Insufficient evaluable data"), 2)

    def test_single_or_reversed_experiments_are_rejected(self):
        for records in ([synthetic_record("N2")], [synthetic_record("N3"), synthetic_record("N2")]):
            with self.subTest(experiments=[r["experiment"] for r in records]):
                with self.assertRaisesRegex(ValueError, "both N2 and N3"):
                    render(records)


if __name__ == "__main__":
    unittest.main()
