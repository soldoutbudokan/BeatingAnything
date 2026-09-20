from datetime import datetime, timezone
import unittest

from tools.validate_nba_first_score_2026 import map_board, outcome_for, settle, state_at


class ProviderStateTests(unittest.TestCase):
    decision = datetime(2026, 4, 1, 23, 55, tzinfo=timezone.utc)

    def entry(self, minute, active=True, price=10):
        return {"createdAt": f"2026-04-01T23:{minute}:00Z", "price": price, "active": active}

    def test_future_entries_do_not_leak_and_boundary_is_inclusive(self):
        states, reason = state_at({"a": [self.entry("55"), self.entry("56", price=50)],
                                   "b": [self.entry("56")]}, self.decision)
        self.assertIsNone(reason)
        self.assertEqual(set(states), {"a"})
        self.assertEqual(states["a"]["decimal"], 10)
        self.assertEqual(states["a"]["entry_age_seconds"], 0)

    def test_latest_bad_state_does_not_resurrect_old_price(self):
        for entry in (self.entry("54", active=False), self.entry("54", price=None), self.entry("54", price=1)):
            states, reason = state_at({"a": [self.entry("53"), entry]}, self.decision)
            self.assertEqual(states, {})
            self.assertIsNone(reason)

    def test_equal_clock_conflict_and_unorderable_entry_reject_board(self):
        for entries, expected in (([self.entry("54"), self.entry("54", active=False)], "conflicting_latest_state"),
                                  ([self.entry("54"), {"createdAt": "2026-04-01T23:54:00"}], "unorderable_history_clock")):
            states, reason = state_at({"a": entries}, self.decision)
            self.assertIsNone(states)
            self.assertEqual(reason, expected)

    def test_duplicate_person_cannot_complete_board(self):
        states = {str(i): {"decimal": 10} for i in range(10)}
        identities = {str(i): {"espn_athlete_id": str(i), "player_id": str(i)} for i in range(10)}
        identities["9"] = identities["8"]
        self.assertEqual(map_board(states, identities)[1], "duplicate_person")


class IndependentSettlementTests(unittest.TestCase):
    def setUp(self):
        self.f = {"home_team_id": "h", "away_team_id": "a", "runners": [
            {"player_id": "bref0", "espn_athlete_id": "0", "name": "Player Zero"}]}
        self.bet = {"player_id": "bref0", "decimal": 10}
        self.roster = [{"athlete_id": str(i), "team_id": "h" if i < 5 else "a", "starter": True} for i in range(10)]

    def test_nonstarter_is_void_but_absent_player_is_unknown(self):
        self.roster[0]["starter"] = False
        self.roster.append({"athlete_id": "10", "team_id": "h", "starter": True})
        self.assertEqual(settle(self.bet, self.f, {"status": "unresolved"}, self.roster)["status"], "void")
        self.assertEqual(settle(self.bet, self.f, {"status": "unresolved"}, self.roster[1:])["status"], "unresolved")

    def test_free_throw_wins_and_unlisted_scorer_remains_resolved(self):
        play = {"sequence_number": 1, "scoring_play": True, "score_value": 1, "home_score": 1, "away_score": 0,
                "period_number": 1, "athlete_id_1": "0", "athlete_name_1": "Player Zero", "clock_display_value": "11:50"}
        outcome = outcome_for(self.f, [play], {"0": {"playerzero"}})
        self.assertEqual(settle(self.bet, self.f, outcome, self.roster), {"status": "win", "profit": 8.82})
        play.update(athlete_id_1="10", athlete_name_1="Player Ten")
        outcome = outcome_for(self.f, [play], {"10": {"playerten"}})
        self.assertEqual(outcome["status"], "resolved")
        self.assertFalse(outcome["listed"])
        self.assertEqual(settle(self.bet, self.f, outcome, self.roster)["status"], "loss")

    def test_scoreboard_and_identity_conflicts_stay_unknown(self):
        play = {"sequence_number": 1, "scoring_play": True, "score_value": 1, "home_score": 2, "away_score": 0,
                "period_number": 1, "athlete_id_1": "0", "athlete_name_1": "Player Zero", "clock_display_value": "11:50"}
        self.assertEqual(outcome_for(self.f, [play], {"0": {"playerzero"}})["status"], "unresolved")
        play["home_score"] = 1
        self.assertEqual(outcome_for(self.f, [play], {"0": {"anotherplayer"}})["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
