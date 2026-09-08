import unittest
import numpy as np
import pandas as pd

from beating.soccer_evaluate import decisions, describe, fair_pair


class ClosingEvaluationTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({"date":pd.to_datetime(["2024-01-01", "2024-01-02"]),
            "odds_a":[2.2, 2.2], "odds_b":[1.8, 1.8], "market_p":[.45, .45],
            "y":[1, 0], "close_a":[2., np.nan], "close_b":[2., np.nan],
            "book_close_a":[2., 2.], "book_close_b":[2., 2.]})

    def test_missing_future_close_cannot_remove_losing_bet(self):
        f = self.frame()
        result = describe(f, [.6, .6], False)
        self.assertEqual(result["bets"], 2)
        self.assertAlmostEqual(result["roi"], .1)
        self.assertEqual(result["closing_average"]["covered_bets"], 1)
        self.assertEqual(result["closing_average"]["missing_bets"], 1)
        self.assertAlmostEqual(result["closing_average"]["mean_closing_ev"], .1)

    def test_entry_decision_has_no_outcome_or_close_dependency(self):
        f = self.frame()
        before = decisions(f, [.6, .6])
        f["y"] = [0, 1]
        f[["close_a", "close_b"]] = 100
        after = decisions(f, [.6, .6])
        for key in before:
            np.testing.assert_array_equal(before[key], after[key])

    def test_power_devig_and_invalid_closing_pair(self):
        p = fair_pair([1.5, 2., 10.], [3., 2., 10.], power=True)
        self.assertAlmostEqual(p[0], 2/3)
        self.assertAlmostEqual(p[1], .5)
        self.assertTrue(np.isnan(p[2]))

    def test_unknown_outcome_is_neither_loss_nor_removed_turnover(self):
        f = self.frame()
        f.loc[1, "y"] = np.nan
        r = describe(f, [.6, .6], False)
        self.assertEqual(r["bets"], 2)
        self.assertEqual(r["settled_bets"], 1)
        self.assertIsNone(r["roi"])
        self.assertAlmostEqual(r["roi_unresolved_outcome_bounds"][0], .1)
        self.assertAlmostEqual(r["roi_unresolved_outcome_bounds"][1], 1.2)
