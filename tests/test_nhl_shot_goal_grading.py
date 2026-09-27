import math
import unittest

import numpy as np
import pandas as pd

from tools.grade_nhl_shot_goals import drawdown, paired_losses, returns, target_grade


class NHLShotGoalGradingTests(unittest.TestCase):
    def test_participation_and_inconsistent_targets_remain_explicit(self):
        def grade(toi, goals, shots):
            return target_grade(pd.DataFrame([{"toi": toi, "goals": goals, "shots_on_goal": shots}]))
        self.assertEqual(grade("00:00", 0, 0)[:2], ("void", None))
        self.assertEqual(grade("00:00", 0, 1)[0], "unknown")
        self.assertEqual(grade("12:34", 0, 0)[:2], ("settled", 1))
        self.assertEqual(grade("12:34", 1, 1)[:2], ("settled", 0))
        for values in [("12:60", 0, 0), ("12:34", 2, 1), ("12:34", .5, 1), ("12:34", 0, np.nan)]:
            self.assertEqual(grade(*values)[0], "unknown")
        self.assertEqual(target_grade(pd.DataFrame())[0], "unknown")
        self.assertEqual(target_grade(pd.DataFrame([{}, {}]))[2], "duplicate_target")

    def test_games_receive_equal_accuracy_weight_regardless_of_player_count(self):
        frame = pd.DataFrame([{"game_id": 1, "status": "settled", "y_under": 1,
                               "p_under": .8, "goal_q_under": .5} for _ in range(3)] +
                             [{"game_id": 2, "status": "settled", "y_under": 1,
                               "p_under": .2, "goal_q_under": .5}])
        result = paired_losses(frame, np.random.default_rng(1))
        expected_model = (-math.log(.8) - math.log(.2)) / 2
        self.assertAlmostEqual(result["model_log_loss"], expected_model)
        self.assertAlmostEqual(result["log_loss_gain_market_minus_model"], math.log(2) - expected_model)
        self.assertAlmostEqual(result["model_brier"], (.2**2 + .8**2)/2)
        self.assertEqual(result["graded_games"], 2)

    def test_unknown_forecast_labels_bound_the_full_denominator(self):
        frame = pd.DataFrame([
            {"game_id": 1, "status": "settled", "y_under": 1, "p_under": .8, "goal_q_under": .5},
            {"game_id": 1, "status": "unknown", "y_under": np.nan, "p_under": .9, "goal_q_under": .5},
            {"game_id": 2, "status": "void", "y_under": np.nan, "p_under": .9, "goal_q_under": .5}])
        result = paired_losses(frame, np.random.default_rng(1))
        bound = result["log_loss_gain_full_nonvoid_unknown_label_bounds"]
        known = math.log(.8/.5)
        self.assertAlmostEqual(bound["lower"], (known + math.log(.1/.5))/2)
        self.assertAlmostEqual(bound["upper"], (known + math.log(.9/.5))/2)
        self.assertEqual(bound["forecasts"], 2)
        self.assertEqual(bound["games"], 1)

    def test_roi_void_unknown_and_no_selection_games(self):
        rows = []
        for game, side, status, won, price, raw, haircut in [
            (1, "Over", "settled", 1, 3., 2., 1.96),
            (2, "Under", "settled", 0, 2., -1., -1.),
            (3, "Over", "unknown", np.nan, 4., np.nan, np.nan),
            (4, "Under", "void", np.nan, 2., 0., 0.),
            (5, "", "settled", np.nan, np.nan, np.nan, np.nan)]:
            rows.append({"game_id": game, "player_id": game, "player": str(game),
                         "selected_side": side, "status": status, "won": won,
                         "selected_decimal": price, "raw_profit": raw, "haircut_profit": haircut})
        result = returns(pd.DataFrame(rows), np.random.default_rng(1))
        self.assertEqual((result["selections"], result["settled"], result["voids"], result["unknowns"]), (4, 2, 1, 1))
        self.assertAlmostEqual(result["haircut_roi"], .48)
        bound = result["haircut_unknown_settlement_bounds"]
        self.assertAlmostEqual(bound["lower_roi"], -.04/3)
        self.assertAlmostEqual(bound["upper_roi"], 3.90/3)
        # Sampling all five games allows draws without settled bets, which must
        # remain undefined rather than silently becoming zero ROI.
        self.assertLess(result["haircut_roi_ci95"]["defined_draws"], 10_000)
        self.assertEqual(result["haircut_drawdown_settled_units"], 1.)
        self.assertEqual(result["haircut_drawdown_unknown_scenarios"]["all_unknown_losses"], 2.)

    def test_all_unknown_accuracy_still_has_label_bounds(self):
        frame = pd.DataFrame([{"game_id": 1, "status": "unknown", "y_under": np.nan,
                               "p_under": .8, "goal_q_under": .5}])
        result = paired_losses(frame, np.random.default_rng(1))
        self.assertEqual(result["graded_forecasts"], 0)
        bound = result["log_loss_gain_full_nonvoid_unknown_label_bounds"]
        self.assertAlmostEqual(bound["lower"], math.log(.2/.5))
        self.assertAlmostEqual(bound["upper"], math.log(.8/.5))
        frame["status"] = "void"
        result = paired_losses(frame, np.random.default_rng(1))
        self.assertNotIn("log_loss_gain_full_nonvoid_unknown_label_bounds", result)

    def test_drawdown_starts_from_zero_wealth(self):
        self.assertEqual(drawdown([-1., -1., 4., -1.]), 2.)
        self.assertEqual(drawdown([]), 0.)


if __name__ == "__main__":
    unittest.main()
