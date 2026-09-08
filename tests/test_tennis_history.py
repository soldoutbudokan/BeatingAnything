"""Causal synthetic-history tests; no acquired match outcomes are evaluated."""
from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from beating.tennis_history import (History, completed_set, date_end_and_availability,
                                    elo_set_probability, fit_n2, fit_n3)


class TennisHistoryTests(unittest.TestCase):
    def record(self, **updates):
        value = {"event_id": "past-1", "date": "2024-01-01", "player1": "player-a",
                 "player2": "player-b", "sets": [[6, 4], [7, 6]], "completed": True}
        return {**value, **updates}

    def feature(self, records, decision="2024-01-05T00:00:00Z", event="forecast", player1="player-a", player2="player-b"):
        return History(records).features(player1, player2, event, decision)

    def test_empty_history_uses_frozen_priors_without_claiming_player_is_new(self):
        result = self.feature([])
        for player in ("player1_history", "player2_history"):
            summary = result[player]
            self.assertEqual(summary["elo"], 1500)
            self.assertEqual(summary["lifetime_completed_sets"], 0)
            self.assertEqual(summary["shrunk_tiebreak_rate_365d"], .12)
            self.assertTrue(summary["missing_history"])
            self.assertEqual(summary["coverage_status"], "unknown")
        self.assertEqual(result["elo_match_win_p"], .5)
        self.assertEqual(result["workload_total"], 0)

    def test_future_score_changes_cannot_change_features(self):
        past = self.record()
        future = self.record(event_id="future", date="2024-01-04")
        baseline = self.feature([past])
        self.assertEqual(self.feature([past, future]), baseline)
        changed = {**future, "sets": [[0, 6], [0, 6]]}
        self.assertEqual(self.feature([past, changed]), baseline)

    def test_current_event_never_predicts_itself_and_replays_indirect_elo_effects(self):
        current = self.record(event_id="current", date="2024-01-01", sets=[[6, 0], [6, 0]])
        later = self.record(event_id="later", date="2024-01-02", player1="player-b", player2="player-c")
        query = dict(decision="2024-01-06T00:00:00Z", event="current", player1="player-a", player2="player-c")
        expected = self.feature([later], **query)
        result = self.feature([current, later], **query)
        self.assertTrue(result["current_event_history_excluded"])
        self.assertTrue(result["current_event_history_inconsistency"])
        for key in ("player1_history", "player2_history", "elo_match_win_p", "set_tiebreak_p", "workload_total"):
            self.assertEqual(result[key], expected[key])
        changed = {**current, "sets": [[0, 6], [0, 6]]}
        self.assertEqual(self.feature([changed, later], **query), result)

    def test_current_event_normally_unavailable_is_excluded_without_inconsistency(self):
        current = self.record(event_id="current", date="2024-01-05")
        result = self.feature([current], event="current")
        self.assertTrue(result["current_event_history_excluded"])
        self.assertFalse(result["current_event_history_inconsistency"])
        self.assertEqual(result["player1_history"]["lifetime_completed_sets"], 0)

    def test_availability_is_exactly_48_elapsed_hours_after_local_midnight(self):
        for source_date, date_end, available in (
            ("2024-03-30", "2024-03-30T23:00:00+00:00", "2024-04-01T23:00:00+00:00"),
            ("2024-10-26", "2024-10-26T22:00:00+00:00", "2024-10-28T22:00:00+00:00"),
        ):
            with self.subTest(source_date=source_date):
                end, cutoff = date_end_and_availability(source_date)
                self.assertEqual(end.isoformat(), date_end)
                self.assertEqual(cutoff.isoformat(), available)
                self.assertEqual(cutoff - end, timedelta(hours=48))
                records = [self.record(date=source_date)]
                before = self.feature(records, decision=cutoff - timedelta(microseconds=1))
                at = self.feature(records, decision=cutoff)
                self.assertEqual(before["player1_history"]["lifetime_completed_sets"], 0)
                self.assertEqual(at["player1_history"]["lifetime_completed_sets"], 2)

    def test_rolling_windows_use_played_date_end_open_lower_boundary(self):
        record = self.record()
        end, _ = date_end_and_availability(record["date"])
        for days, field, count in ((7, "completed_match_games_7d", 23), (365, "completed_sets_365d", 2)):
            boundary = end + timedelta(days=days)
            before = self.feature([record], decision=boundary - timedelta(microseconds=1))["player1_history"]
            at = self.feature([record], decision=boundary)["player1_history"]
            self.assertEqual(before[field], count)
            self.assertEqual(at[field], 0)
            self.assertEqual(at["lifetime_completed_sets"], 2)
            self.assertGreater(at["elo"], 1500)

    def test_retirement_updates_completed_sets_but_never_match_workload(self):
        retired = self.record(sets=[[7, 6], [3, 1]], completed=False)
        summary = self.feature([retired])["player1_history"]
        self.assertEqual(summary["lifetime_completed_sets"], 1)
        self.assertEqual(summary["tiebreak_sets_365d"], 1)
        self.assertAlmostEqual(summary["shrunk_tiebreak_rate_365d"], 7 / 51)
        self.assertEqual(summary["elo"], 1508)
        self.assertEqual(summary["completed_match_games_7d"], 0)
        # A completed flag cannot turn a truncated or post-termination sequence
        # into a completed-match workload observation.
        for sets in ([[6, 0]], [[6, 0], [2, 1]], [[6, 0], [6, 0], [0, 6]]):
            summary = self.feature([self.record(sets=sets)])["player1_history"]
            self.assertEqual(summary["completed_match_games_7d"], 0)

    def test_recognizes_only_registered_conventional_completed_sets(self):
        valid = [(6, low) for low in range(5)] + [(7, 5), (7, 6)]
        for score in valid:
            self.assertTrue(completed_set(score))
            self.assertTrue(completed_set(tuple(reversed(score))))
        for score in ((6, 5), (6, 6), (7, 4), (7, 7), (8, 6), (10, 8), (0, 0)):
            self.assertFalse(completed_set(score))

    def test_elo_order_is_availability_then_event_id_then_set_order(self):
        first = self.record(event_id="a", sets=[[6, 0]], completed=False)
        second = self.record(event_id="z", sets=[[0, 6]], completed=False)
        expected_first = 1508.0
        expected = expected_first - 16 * elo_set_probability(1508, 1492)
        history = History([second, first])
        result = history.features("player-a", "player-b", "forecast", "2024-01-05T00:00:00Z")
        self.assertAlmostEqual(result["player1_history"]["elo"], expected)
        self.assertAlmostEqual(result["player1_history"]["elo"] + result["player2_history"]["elo"], 3000)
        self.assertEqual(result, self.feature([first, second]))
        history.features("player-a", "player-b", "earlier", "2024-01-02T00:00:00Z")
        self.assertEqual(result, history.features("player-a", "player-b", "forecast", "2024-01-05T00:00:00Z"))
        combined = self.feature([self.record(sets=[[6, 0], [0, 6]], completed=False)])
        self.assertAlmostEqual(combined["player1_history"]["elo"], expected)

    def test_stable_player_ids_do_not_merge_and_duplicate_events_do_not_double_count(self):
        record = self.record(player1="same-name-1", player2="opponent")
        history = History([record, record])
        query = ("same-name-1", "same-name-2", "forecast", "2024-01-05T00:00:00Z")
        result = history.features(*query)
        self.assertEqual(result["player1_history"]["lifetime_completed_sets"], 2)
        self.assertEqual(result["player2_history"]["lifetime_completed_sets"], 0)
        with self.assertRaisesRegex(ValueError, "conflicting history"):
            History([record, {**record, "sets": [[0, 6], [0, 6]]}])
        record["sets"][0][0] = 0
        self.assertEqual(history.features(*query), result)

    def test_workload_caps_and_player_swap(self):
        records = [self.record(event_id=f"event-{i}", player2=f"opponent-{i}", sets=[[7, 6], [7, 6]]) for i in range(10)]
        result = self.feature(records, player2="other-player")
        self.assertEqual(result["player1_history"]["completed_match_games_7d"], 260)
        self.assertEqual(result["workload_total"], 4)
        self.assertEqual(result["workload_difference"], 2)
        swapped = self.feature(records, player1="other-player", player2="player-a")
        self.assertAlmostEqual(result["elo_match_win_p"] + swapped["elo_match_win_p"], 1)
        self.assertEqual(result["set_tiebreak_p"], swapped["set_tiebreak_p"])
        self.assertEqual(result["workload_total"], swapped["workload_total"])

    def test_kernel_wrappers_keep_n2_market_and_n3_history_targets_separate(self):
        summary = self.feature([self.record()])
        with patch("beating.tennis_history.fit_hold_probabilities", return_value={"sentinel": True}) as fit:
            self.assertEqual(fit_n2(summary, .63), {"sentinel": True})
            fit.assert_called_once_with(.63, summary["set_tiebreak_p"])
            fit.reset_mock()
            fit_n3(summary)
            fit.assert_called_once_with(summary["elo_match_win_p"], summary["set_tiebreak_p"])

    def test_invalid_identity_date_score_or_clock_is_rejected(self):
        for updates in ({"player1": ""}, {"player2": "player-a"}, {"event_id": 1},
                        {"date": "20240101"}, {"completed": 1}, {"sets": [[6, True]]},
                        {"sets": [[6.0, 0]]}, {"sets": [[6, -1]]}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                History([self.record(**updates)])
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.feature([], decision=datetime(2024, 1, 5))


if __name__ == "__main__":
    unittest.main()
