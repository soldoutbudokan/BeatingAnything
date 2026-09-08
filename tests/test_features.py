"""Chronology and official-source normalization regression tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from beating.features import build_features, build_live_snapshot, DIFF_FEATURES
from beating.mlb import load_appearances, load_games, assert_prior_games_complete


def game(pk, day, home=1, away=2, available=None, **extra):
    return dict(game_pk=pk, date=day, available_date=available or day,
                start_time=day+"T20:00:00Z", season=2024, venue_id=10,
                scheduled_innings=9, innings=9, home_team_id=home,
                away_team_id=away, home_score=4, away_score=2,
                home_win=1, suspended=False, **extra)


def appearance(g, pitcher=99, team=1, pitches=30):
    return dict(game_pk=g["game_pk"], pitcher_id=pitcher, team_id=team,
                date=g["date"], available_date=g["available_date"],
                season=2024, suspended=g["suspended"], started=False,
                pitches=pitches, outs=3, runs=0, earned_runs=0, strikeouts=2,
                walks=0, batters_faced=3, holds=1, saves=0)


VENUES = {10: {"location": {"defaultCoordinates": {"latitude": 40.8, "longitude": -73.9}},
               "timeZone": {"id": "America/New_York"}}}


class FeatureChronologyTests(unittest.TestCase):
    def test_future_targets_need_no_fabricated_results(self):
        past = game(1, "2024-04-01")
        target = {k: v for k, v in game(2, "2024-04-02").items()
                  if k not in {"available_date", "home_score", "away_score", "home_win", "innings"}}
        rows = build_features([past], [appearance(past, pitches=19)], VENUES,
                              target_games=[target])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["game_pk"], 2)
        self.assertEqual(rows[0]["home_bullpen_pitches_1d"], 19)
        self.assertNotIn("home_win", rows[0])

    def test_same_day_and_future_outcomes_do_not_change_features(self):
        games = [game(1, "2024-04-01"), game(2, "2024-04-02"),
                 game(3, "2024-04-02"), game(4, "2024-04-03")]
        apps = [appearance(g) for g in games]
        baseline = build_features(games, apps, VENUES)
        changed_games = copy.deepcopy(games)
        changed_apps = copy.deepcopy(apps)
        for g in changed_games[1:]:
            g["home_score"], g["away_score"], g["innings"] = 99, 0, 30
        for a in changed_apps[1:]:
            a["pitches"], a["strikeouts"] = 300, 80
        changed = build_features(changed_games, changed_apps, VENUES)
        for i in (1, 2):
            self.assertEqual([baseline[i][k] for k in DIFF_FEATURES],
                             [changed[i][k] for k in DIFF_FEATURES])
            self.assertEqual(baseline[i]["home_bullpen_pitches_1d"], 30)

    def test_suspended_result_waits_for_completion(self):
        suspended = game(1, "2024-04-01", available="2024-04-05")
        suspended["suspended"] = True
        games = [suspended, game(2, "2024-04-03"), game(3, "2024-04-06")]
        rows = build_features(games, [appearance(suspended)], VENUES)
        self.assertEqual(rows[1]["home_run_diff_28d"], 0)
        self.assertGreater(rows[2]["home_run_diff_28d"], 0)
        # Aggregated suspended-game pitches cannot be assigned to exact days.
        self.assertEqual(rows[2]["home_bullpen_pitches_1d"], 0)
        self.assertGreater(rows[2]["home_bullpen_recent_missing"], 0)

    def test_missing_venue_is_explicitly_flagged(self):
        rows = build_features([game(1, "2024-04-01"), game(2, "2024-04-02")], [], {})
        self.assertFalse(rows[1]["feature_travel_complete"])
        self.assertEqual(rows[1]["diff_travel_km"], 0)

    def test_lag_sensitivity_and_real_pitch_counts(self):
        games = [game(1, "2024-04-01"), game(2, "2024-04-02"), game(3, "2024-04-03")]
        apps = [appearance(games[0], pitches=17), appearance(games[1], pitches=24)]
        one = build_features(games, apps, VENUES, lag_days=1)[2]
        two = build_features(games, apps, VENUES, lag_days=2)[2]
        self.assertEqual(one["home_bullpen_pitches_1d"], 24)
        self.assertEqual(one["home_bullpen_pitches_3d"], 41)
        self.assertEqual(one["home_bullpen_back_to_back"], 1)
        self.assertEqual(two["home_bullpen_pitches_1d"], 0)
        self.assertEqual(two["home_bullpen_pitches_3d"], 17)
        self.assertEqual(two["feature_cutoff_date"], "2024-04-01")


class SourceNormalizationTests(unittest.TestCase):
    def test_pending_prior_game_blocks_before_cache_and_allows_retry(self):
        def schedule(state):
            return {"dates": [{"date": "2024-04-01", "games": [
                {"gamePk": 7, "gameType": "R", "status": {"detailedState": state}}]}]}
        for state in ("In Progress", "Suspended", "Scheduled", "Game Over"):
            with self.assertRaisesRegex(RuntimeError, "no daily snapshot was cached"):
                assert_prior_games_complete("2024-04-02", schedule=schedule(state))
        for state in ("Final", "Completed Early", "Postponed", "Cancelled"):
            assert_prior_games_complete("2024-04-02", schedule=schedule(state))
        with tempfile.TemporaryDirectory() as folder:
            with patch("beating.features.assert_prior_games_complete", side_effect=RuntimeError("pending")), \
                 patch("beating.features.download") as download:
                with self.assertRaisesRegex(RuntimeError, "pending"):
                    build_live_snapshot(folder, "2024-04-02")
                download.assert_not_called()
                self.assertFalse((Path(folder)/"2024-04-02").exists())
            # The next attempt invokes a fresh preflight, not cached state.
            with patch("beating.features.assert_prior_games_complete") as guard, \
                 patch("beating.features.download", side_effect=RuntimeError("download reached")):
                with self.assertRaisesRegex(RuntimeError, "download reached"):
                    build_live_snapshot(folder, "2024-04-02")
                guard.assert_called_once_with("2024-04-02")

    def test_traded_pitcher_dedup_uses_actual_game_team(self):
        g = game(10, "2024-04-01", home=147, away=121)
        split = {"game": {"gamePk": 10}, "gameType": "R", "team": {"id": 121},
                 "stat": {"gamesStarted": 0, "numberOfPitches": 27, "outs": 3}}
        source = {"roster": [{"person": {"id": 42, "stats": [
            {"group": {"displayName": "pitching"}, "splits": [split]}]}}]}
        with tempfile.TemporaryDirectory() as folder:
            for team in (147, 121):
                (Path(folder)/f"pitching_2024_{team}.json").write_text(json.dumps(source))
            apps = load_appearances(folder, [g])
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["team_id"], 121)
        self.assertEqual(apps[0]["pitches"], 27)

    def test_postponed_score_copy_and_suspended_duplicates(self):
        raw = {"gamePk": 10, "gameType": "R", "season": "2024",
               "officialDate": "2024-04-01", "gameDate": "2024-04-01T20:00:00Z",
               "venue": {"id": 10}, "teams": {
                   "home": {"team": {"id": 1, "name": "H"}, "score": 4},
                   "away": {"team": {"id": 2, "name": "A"}, "score": 2}},
               "status": {"abstractGameState": "Final", "detailedState": "Final"}}
        postponed = copy.deepcopy(raw)
        postponed["gamePk"] = 20
        postponed["status"]["detailedState"] = "Postponed"
        postponed["rescheduleDate"] = "2024-06-01T20:00:00Z"
        first = {**raw, "resumeDate": "2024-04-05T20:00:00Z", "resumeGameDate": "2024-04-05"}
        last = {**raw, "gameDate": "2024-04-05T20:00:00Z", "resumedFrom": raw["gameDate"]}
        source = {"dates": [{"date": "2024-04-01", "games": [first, postponed]},
                            {"date": "2024-04-05", "games": [last]}]}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/"schedule_2024.json").write_text(json.dumps(source))
            games = load_games(folder)
        self.assertEqual(len(games), 1)
        self.assertTrue(games[0]["suspended"])
        self.assertEqual(games[0]["available_date"], "2024-04-05")
        self.assertEqual(games[0]["start_time"], "2024-04-01T20:00:00Z")


if __name__ == "__main__":
    unittest.main()
