from copy import deepcopy
import unittest

from tools.backtest_nba_first_basket import (
    bootstrap_ratios, clock, forecast_boards, grade_outcome, history_available,
    norm, roster_status, scoring, settle_bet, summarize,
)


class FirstBasketChronologyTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "game_id": "202501010H", "season": 2025, "date": "2025-01-01",
            "home": "H", "away": "A", "available_at": "2025-01-02T05:00:00Z",
            "completed_at": "2025-01-02T03:00:00Z",
            "roster": [(f"p{i}", "H" if i < 5 else "A", True) for i in range(10)],
            "valid_jump": True, "valid_role": True, "jumper_home": "p0", "jumper_away": "p5",
            "possession_team": "H", "scorer_team": "H", "scorer": "p1",
        }
        self.board = {
            "game_id": "202501020H", "espn_game_id": "1", "nba_game_id": "2",
            "home_abbr": "H", "away_abbr": "A", "received_at": "2025-01-02T20:00:30Z",
            "prices": [{"name": f"Player {i}", "decimal": 12.0,
                        "quote_time": "2025-01-02T20:00:00Z"} for i in range(10)],
        }
        self.names = {norm(f"Player {i}"): {f"p{i}"} for i in range(10)}

    def test_future_target_winner_jump_and_roster_cannot_affect_forecast(self):
        target = {**deepcopy(self.event), "game_id": self.board["game_id"], "date": "2025-01-02",
                  "available_at": "2025-01-03T05:00:00Z", "completed_at": "2025-01-03T03:00:00Z"}
        expected = forecast_boards([self.board], [self.event], self.names)
        target.update(scorer="p9", scorer_team="A", possession_team="A", roster=[])
        actual = forecast_boards([self.board], [self.event, target], self.names)
        self.assertEqual(expected, actual)
        self.assertEqual(len(actual[0]), 1)
        self.assertEqual(actual[0][0]["history_games"], 1)

    def test_current_season_needs_both_prior_date_and_strict_completion_cutoff(self):
        quote = clock("2025-01-02T20:00:00Z")
        self.assertTrue(history_available(self.event, quote))
        for patch in ({"date": "2025-01-02"}, {"completed_at": None},
                      {"completed_at": quote.isoformat()}, {"available_at": quote.isoformat()}):
            with self.subTest(patch=patch):
                self.assertFalse(history_available({**self.event, **patch}, quote))
        # 02:00 UTC is still the prior NY calendar day, even if a game has ended.
        self.assertFalse(history_available(self.event, clock("2025-01-02T02:00:00Z")))

    def test_absent_prior_team_membership_cannot_be_filled_from_target_starters(self):
        prior = {**self.event, "roster": self.event["roster"][:-1]}
        forecasts, exclusions = forecast_boards([self.board], [prior], self.names)
        self.assertEqual(forecasts, [])
        self.assertEqual(exclusions[0]["reason"], "prior_roster_team_assignment")


class FirstBasketSettlementTests(unittest.TestCase):
    def setUp(self):
        self.roster = [{"player_id": f"p{i}", "Team": "H" if i < 5 else "A", "starter": "True"}
                       for i in range(10)]
        self.outcome = {"status": "resolved", "scorer": "p0"}

    def test_nonstarter_void_and_incomplete_roster_unresolved(self):
        bet = {"player_id": "bench", "decimal": 8}
        self.assertEqual(settle_bet(bet, self.outcome, self.roster, "H", "A")["status"], "void")
        self.assertEqual(settle_bet(bet, self.outcome, self.roster[:-1], "H", "A")["status"], "unresolved")
        self.assertEqual(roster_status(self.roster + [self.roster[0]], "H", "A"), "duplicate_or_missing_roster_player")

    def test_first_free_throw_grades_and_disagreement_remains_unresolved(self):
        play = {"sequence_number": 1, "period_number": 1, "scoring_play": True, "score_value": 1,
                "home_score": 1, "away_score": 0, "athlete_name_1": "Player Zero", "clock_display_value": "11:45"}
        forecast = {"probabilities": {"market": {"p0": .5}}}
        names = {norm("Player Zero"): {"p0"}}
        publisher = [{"first_basket": "p0", "pts_scored": "1", "time_elapsed": "15"}]
        result = grade_outcome(forecast, [play], names, publisher)
        self.assertEqual(result["scorer"], "p0")
        won = settle_bet({"player_id": "p0", "decimal": 8}, result, self.roster, "H", "A")
        self.assertAlmostEqual(won["profit"], 6.86)
        publisher[0]["first_basket"] = "p1"
        self.assertEqual(grade_outcome(forecast, [play], names, publisher)["status"], "unresolved")
        self.assertEqual(grade_outcome(forecast, [play], {}, [])["reason"], "independent_scorer_identity")

    def test_unlisted_winner_is_retained_in_scoring(self):
        probabilities = {f"p{i}": .1 for i in range(10)}
        result = scoring(probabilities, "bench")
        self.assertAlmostEqual(result["log_loss"], 4.605170185988091)
        self.assertAlmostEqual(result["brier"], 10 * .099 ** 2 + .99 ** 2)

    def test_voids_and_unknowns_keep_original_stake_denominator(self):
        settlements = [{"status": "win", "profit": 1.96}, {"status": "void", "profit": 0},
                       {"status": "unresolved", "profit": None}]
        rows = [{"week": "2025-W01", "settlements": {"tip": s}, "scores": None} for s in settlements]
        result = summarize(rows, "tip", "settlements")
        self.assertEqual(result["original_stake_turnover"], 3)
        self.assertEqual(result["nonvoid_settled_turnover"], 1)
        self.assertIsNone(result["haircut_roi"])
        self.assertAlmostEqual(result["unresolved_all_loss_roi"], .96 / 3)
        self.assertAlmostEqual(result["unresolved_all_void_roi"], 1.96 / 3)
        self.assertIsNone(result["roi_bootstrap_all_loss"]["corrected_interval"])

    def test_bootstrap_resamples_whole_weeks_and_requires_eight(self):
        self.assertIsNone(bootstrap_ratios([("week", 1, 1)])["corrected_interval"])
        rows = [(f"week{i}", 2, 1) for i in range(8)]
        self.assertEqual(bootstrap_ratios(rows)["corrected_interval"], [2, 2])


if __name__ == "__main__":
    unittest.main()
