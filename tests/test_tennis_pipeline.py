import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from beating.tennis_pipeline import (InsufficientData, fit_and_forecast,
                                     prepare_features, reconcile_history)


def records():
    return [{"event_id": "te:1", "date": "2021-01-01", "player1": "a", "player2": "b",
             "sets": [[6, 4], [6, 3]], "completed": True}]


def detail():
    def side(price):
        return {"opening_price": price, "opening_at": "2022-04-01T10:00:00+00:00",
                "final_price": 2.0, "final_at": "2022-04-02T10:00:00+00:00"}
    return {"event_id": "te:2", "date": "2022-04-02", "sample_date": "2022-04-02",
            "player1": "a", "player2": "b", "start_at": "2022-04-02T12:00:00+00:00",
            "entry_valid_n2": True, "entry_valid_n3": True, "entry_errors_n2": [], "entry_errors_n3": [],
            "totals_21_5": {"side1": side(2.0), "side2": side(1.9)},
            "moneyline": {"side1": side(1.8), "side2": side(2.2)},
            "closing_valid": True, "source_sha256": "a"*64}


def fake_kernel(*args):
    return {"hold1": .8, "hold2": .8, "max_probability_error": .001,
            "distribution": {"over_21_5_p": .51}}


def synthetic_frame():
    rng = np.random.default_rng(41)
    values = []
    for year in range(2021, 2026):
        for n in range(40):
            day = n % 20+1
            market = rng.uniform(.35, .65)
            values.append({"event_id": f"te:{year}-{n}", "year": year,
                "date": f"{year}-04-{day:02d}", "opening_at": f"{year}-04-{day:02d}T08:00:00+00:00",
                "label_available_at": f"{year}-04-{day+3:02d}T00:00:00+00:00",
                "y": n % 2, "odds_a": 1/(market*1.04), "odds_b": 1/((1-market)*1.04),
                "market_p": market, "market_logit": np.log(market/(1-market)),
                "structure_gap": rng.normal(0, .2), "workload_total": rng.uniform(0, 2),
                "workload_difference": rng.uniform(0, 1), "close_a": 2.0, "close_b": 1.9})
    return pd.DataFrame(values)


class TennisPipelineTests(unittest.TestCase):
    def test_latest_source_date_preserves_winners_and_delays_availability(self):
        earlier = records()[0]
        later = {**earlier, "date": "2021-01-03", "player1": "b", "player2": "a",
                 "sets": [[4, 6], [3, 6]]}
        combined, audit = reconcile_history([later, earlier])
        self.assertEqual(combined[0]["date"], "2021-01-03")
        self.assertEqual(combined[0]["sets"], earlier["sets"])
        self.assertEqual(len(audit), 1)
        conflict = {**earlier, "sets": [[6, 0], [6, 0]]}
        with self.assertRaisesRegex(ValueError, "same-date"):
            reconcile_history([earlier, conflict])

    @patch("beating.tennis_pipeline.fit_n3", side_effect=fake_kernel)
    def test_current_outcome_and_close_do_not_change_entry_features(self, _fit):
        match = detail()
        ungraded, _ = prepare_features(records(), [match], "n3")
        current = {"event_id": "te:2", "date": "2022-04-02", "player1": "a", "player2": "b",
                   "sets": [[6, 0], [6, 0]], "completed": True}
        match["closing_valid"] = False
        changed, _ = prepare_features(records()+[current], [match], "n3")
        columns = ["market_logit", "structure_gap", "workload_total", "workload_difference", "kernel_p"]
        np.testing.assert_array_equal(ungraded[columns], changed[columns])
        self.assertTrue(np.isnan(ungraded.y.iloc[0]))
        self.assertEqual(changed.y.iloc[0], 0)
        self.assertTrue(np.isnan(changed.close_a.iloc[0]))
        self.assertEqual(len(changed), 1)

    @patch("beating.tennis_pipeline.fit_n2", side_effect=fake_kernel)
    @patch("beating.tennis_pipeline.fit_n3", side_effect=fake_kernel)
    def test_n3_can_accept_unsynchronized_moneyline_that_n2_rejects(self, *_):
        match = detail()
        match["entry_valid_n2"] = False
        match["entry_errors_n2"] = ["moneyline_totals_opening_unsynchronized"]
        n2, audit = prepare_features(records(), [match], "n2")
        n3, _ = prepare_features(records(), [match], "n3")
        self.assertTrue(n2.empty)
        self.assertEqual(audit["counts"]["entry_rejected"], 1)
        self.assertEqual(len(n3), 1)

    def test_future_year_cannot_change_validation_choice_or_prior_fold(self):
        frame = synthetic_frame()
        predictions, fit = fit_and_forecast(frame)
        changed = frame.copy()
        future = changed.year.eq(2025)
        changed.loc[future, "y"] = 1-changed.loc[future, "y"]
        changed.loc[future, "structure_gap"] = 100
        changed.loc[future, "close_a"] = 200
        altered, altered_fit = fit_and_forecast(changed)
        self.assertEqual(fit["validation_trials"], altered_fit["validation_trials"])
        self.assertEqual(fit["selected_research_candidate"], altered_fit["selected_research_candidate"])
        self.assertEqual(fit["annual_models"]["2024"], altered_fit["annual_models"]["2024"])
        columns = ["p_calibration", "p_set_shape", "p_workload"]
        np.testing.assert_allclose(predictions.loc[predictions.year.eq(2024), columns],
                                   altered.loc[altered.year.eq(2024), columns])

    def test_delayed_training_labels_and_unavailable_selection_are_explicit(self):
        frame = synthetic_frame()
        # These prior-year labels are still unavailable at the first 2024 quote.
        delayed = frame.year.eq(2022)
        frame.loc[delayed, "label_available_at"] = "2024-12-01T00:00:00+00:00"
        # A quoted 2024 fixture predates completion of validation label collection.
        early = frame.index[frame.year.eq(2024)][0]
        frame.loc[early, "opening_at"] = "2023-04-01T00:00:00+00:00"
        predictions, fit = fit_and_forecast(frame)
        fold = fit["annual_models"]["2024"]
        self.assertEqual(fold["training_years"], [2021, 2023])
        self.assertIn(frame.loc[early, "event_id"], fold["model_unavailable_event_ids"])
        self.assertNotIn(frame.loc[early, "event_id"], predictions.event_id.tolist())
        self.assertLess(fold["maximum_label_available_at"], fold["first_forecast_quote"])

    def test_empty_declared_split_is_data_failure_not_silent_success(self):
        with self.assertRaises(InsufficientData):
            fit_and_forecast(pd.DataFrame())
        frame = synthetic_frame()
        frame.loc[frame.year.eq(2023), "y"] = np.nan
        with self.assertRaisesRegex(InsufficientData, "validation"):
            fit_and_forecast(frame)


if __name__ == "__main__":
    unittest.main()
