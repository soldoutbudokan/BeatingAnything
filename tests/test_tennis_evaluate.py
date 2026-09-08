import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from beating.tennis_evaluate import (
    BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED, CONFIDENCE,
    decisions, describe, fair_pair, gates, interval,
)


class TennisEvaluationTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({
            "event_id": ["a", "b"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-08"]),
            "odds_a": [2.2, 2.2], "odds_b": [1.8, 1.8],
            "market_p": [.45, .45], "y": [1., 0.],
            "close_a": [2., 2.], "close_b": [2., 2.],
        })

    def test_entry_selection_uses_no_results_or_closes(self):
        f = self.frame()
        before = decisions(f[["odds_a", "odds_b"]], [.6, .6])
        f["y"] = [np.nan, 1]
        f[["close_a", "close_b"]] = np.nan
        after = decisions(f, [.6, .6])
        for key in before:
            np.testing.assert_array_equal(before[key], after[key])
        result = describe(f, [.6, .6], False)
        self.assertEqual(result["bets"], 2)
        self.assertEqual(result["unsettled_bets"], 1)
        self.assertEqual(result["closing_pinnacle"]["missing_bets"], 2)

    def test_unknown_selected_outcome_keeps_turnover_and_bounds(self):
        f = self.frame()
        f.loc[1, "y"] = np.nan
        r = describe(f, [.6, .6])
        self.assertEqual(r["turnover_units"], 2)
        self.assertEqual(r["complete_match_simulation"]["turnover_units"], 1)
        self.assertIsNone(r["roi"])
        self.assertEqual(r["roi_ci"], [None, None])
        self.assertAlmostEqual(r["roi_settled_only"], 1.2)
        np.testing.assert_allclose(r["roi_unresolved_outcome_bounds"], [.1, 1.2])
        np.testing.assert_allclose(r["haircut_roi_unresolved_outcome_bounds"], [.088, 1.176])
        self.assertEqual(r["paired_loss_events"], 1)
        self.assertFalse(gates(r)["complete_selected_settlements"])
        json.dumps(r, allow_nan=False)

    def test_settlement_haircut_losses_and_clv_have_separate_denominators(self):
        f = self.frame()
        f.loc[1, ["close_a", "close_b"]] = np.nan
        r = describe(f, [.6, .6], False)
        self.assertAlmostEqual(r["roi"], .1)
        self.assertAlmostEqual(r["haircut_roi"], .088)
        self.assertAlmostEqual(r["brier"], .26)
        self.assertAlmostEqual(r["market_brier"], .2525)
        self.assertAlmostEqual(r["paired_brier_delta"], .0075)
        self.assertAlmostEqual(r["paired_log_loss_delta"], -.5 * np.log(.24 / .2475))
        close = r["closing_pinnacle"]
        self.assertEqual(close["covered_bets"], 1)
        self.assertEqual(close["missing_bets"], 1)
        self.assertEqual(close["selected_close_coverage"], .5)
        self.assertAlmostEqual(close["mean_closing_ev"], .1)
        self.assertAlmostEqual(close["mean_raw_price_ratio"], .1)
        self.assertFalse(gates(r)["complete_selected_close_coverage"])

    def test_under_selection_uses_under_closing_probability_and_price(self):
        f = self.frame().iloc[:1].copy()
        f.loc[:, "y"] = 0
        f.loc[:, "close_a"] = 2.5
        f.loc[:, "close_b"] = 1.5
        r = describe(f, [.2], False)
        self.assertFalse(decisions(f, [.2])["over"][0])
        self.assertAlmostEqual(r["roi"], .8)
        self.assertAlmostEqual(r["closing_pinnacle"]["mean_closing_ev"], .125)
        self.assertAlmostEqual(r["closing_pinnacle"]["mean_raw_price_ratio"], .2)

    def test_power_sensitivity_and_invalid_pairs(self):
        a, b = [1.5, 2., 10., np.nan, 1.1], [3., 2., 10., 2., 1.1]
        q = fair_pair(a, b, power=True)
        np.testing.assert_allclose(q[:2], [2/3, .5])
        self.assertTrue(np.isnan(q[2:]).all())
        proportional = fair_pair([1.5], [2.8])[0]
        power = fair_pair([1.5], [2.8], power=True)[0]
        self.assertGreater(power, proportional)
        self.assertLess(power, 1)

    def test_fixed_policy_boundaries_invalid_pairs_and_over_tie(self):
        f = pd.DataFrame({
            "odds_a": [2., 2., 2., 1.2, 6., 6.01, 1.9, np.inf, 0., 2.2],
            "odds_b": [2., 2., 2., 5., 1.2, 1.2, 1.5, 2., 2., 2.2],
        })
        p = [.5, .515, .514, .99, .4, .4, .9, .6, .6, .6]
        d = decisions(f, p)
        self.assertTrue(d["over"][0])
        np.testing.assert_array_equal(d["selected"], [False, True, False, True, True, False, False, False, False, False])

    def test_no_outcomes_no_bets_and_empty_cohorts_are_json_safe(self):
        for kind in ("no_outcomes", "no_bets", "empty"):
            f = self.frame()
            if kind == "no_outcomes":
                f["y"] = np.nan
            elif kind == "empty":
                f = f.iloc[:0]
            p = np.full(len(f), .45 if kind == "no_bets" else .6)
            r = describe(f, p)
            json.dumps(r, allow_nan=False)
            self.assertFalse(all(gates(r).values()))
            if kind != "no_outcomes":
                self.assertEqual(r["bets"], 0)
                self.assertIsNone(r["roi"])
                self.assertEqual(r["roi_ci"], [None, None])
            if kind != "no_bets":
                self.assertIsNone(r["log_loss"])
                self.assertIsNone(r["paired_log_loss_delta"])

    def test_end_of_day_drawdown_is_chronological_and_ignores_intraday_path(self):
        f = self.frame()
        f["date"] = pd.to_datetime(["2024-01-01 23:00", "2024-01-01 10:00"])
        r = describe(f, [.6, .6], False)
        self.assertEqual(r["max_drawdown_daily_units"], 0)
        self.assertEqual(r["bet_days"], 1)
        self.assertEqual(r["calendar_span_days"], 1)
        f.loc[0, "date"] = pd.Timestamp("2024-01-03")
        self.assertAlmostEqual(describe(f, [.6, .6], False)["max_drawdown_daily_units"], 1)

    def test_week_bootstrap_parameters_and_cluster_invariance(self):
        f = self.frame()
        with patch("beating.tennis_evaluate.block_interval", return_value=[0., 1.]) as boot:
            interval(f, [1., 2.])
        self.assertEqual(boot.call_args.kwargs, {
            "confidence": 1 - .05 / 13, "n_boot": 10000, "seed": 1729,
        })
        self.assertEqual((CONFIDENCE, BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED), (1-.05/13, 10000, 1729))
        expanded = pd.DataFrame({"date": pd.to_datetime([
            "2024-01-01", "2024-01-02", "2024-01-08", "2024-01-09",
        ])})
        np.testing.assert_allclose(interval(f, [2., -2.], [2., 2.]),
                                   interval(expanded, [1., 1., -1., -1.]))
        one_week = expanded.iloc[:2]
        self.assertEqual(interval(one_week, [1., -1.]), [None, None])

    def test_invalid_forecasts_labels_dates_and_duplicate_events_fail(self):
        f = self.frame()
        for probabilities in ([.6], [.6, np.nan], [0., .6], [[.6], [.6]]):
            with self.assertRaises(ValueError):
                describe(f, probabilities, False)
        for column, values in (
            ("event_id", ["a", "a"]), ("date", [pd.NaT, pd.Timestamp("2024-01-08")]),
            ("y", [np.inf, 0]), ("y", [2, 0]), ("market_p", [.5, np.nan]),
        ):
            bad = f.copy()
            bad[column] = values
            with self.subTest(column=column, values=values), self.assertRaises(ValueError):
                describe(bad, [.6, .6], False)

    def test_gates_require_primary_reference_full_coverage_and_settlement(self):
        r = describe(self.frame(), [.6, .6], False)
        r["haircut_roi_ci"] = [.01, .1]
        r["paired_log_loss_delta_ci"] = [-.1, -.01]
        r["closing_pinnacle"]["mean_closing_ev_ci"] = [.01, .1]
        self.assertTrue(all(gates(r).values()))
        r["closing_pinnacle"]["mean_closing_ev_ci"] = [-.01, .1]
        r["closing_pinnacle_power"]["mean_closing_ev_ci"] = [.01, .1]
        self.assertFalse(gates(r)["positive_corrected_closing_ev"])
        self.assertFalse(r["execution_verified"])
        self.assertFalse(r["fanduel_evidence"])


if __name__ == "__main__":
    unittest.main()
