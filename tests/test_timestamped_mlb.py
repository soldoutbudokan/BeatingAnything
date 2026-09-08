"""Frozen F1 invariants using synthetic fixtures only; never run real results."""
import csv
from datetime import timedelta
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from beating.features import DIFF_FEATURES
from beating import timestamped_mlb as f1
from beating.mlb_first_pitch import first_pitch


class TimestampedMlbTests(unittest.TestCase):
    def test_first_pitch_ignores_nonpitch_events_and_checks_identity(self):
        feed = {"gamePk": 1, "liveData": {"plays": {"allPlays": [{"playEvents": [
            {"isPitch": False, "startTime": "2026-09-01T20:00:00Z"},
            {"isPitch": True, "startTime": "2026-09-01T22:01:10Z"},
            {"isPitch": True, "startTime": "2026-09-01T22:00:00Z"}]}]}}}
        self.assertEqual(first_pitch(feed, 1), "2026-09-01T22:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "identity"):
            first_pitch(feed, 2)

    def row(self, **updates):
        value = {"snapshot_ts": "2026-09-01T20:00:00Z", "sport": "baseball_mlb",
                 "home": "Home Club", "away": "Away Club", "commence_time": "2026-09-01T22:00:00Z",
                 "market": "ml", "side": "home", "line": "", "book": "fanduel", "american_odds": "-110"}
        return {**value, **updates}

    def pair_rows(self, **updates):
        return [self.row(side=side, **updates) for side in ("home", "away")]

    def game(self, **updates):
        value = {"gamePk": 1, "gameDate": "2026-09-01T22:00:00Z", "officialDate": "2026-09-01",
                 "gameType": "R", "scheduledInnings": 9, "doubleHeader": "N", "venue": {"id": 1},
                 "teams": {"home": {"team": {"id": 10, "name": "Home Club"}, "score": 3},
                           "away": {"team": {"id": 20, "name": "Away Club"}, "score": 1}},
                 "status": {"detailedState": "Final"}, "linescore": {"currentInning": 9}}
        return {**value, **updates}

    def schedule(self, games):
        return {"dates": [{"date": "2026-09-01", "games": games}]}

    def mapped(self, rows=None, games=None):
        pairs, _ = f1.paired_snapshots(rows if rows is not None else self.pair_rows())
        return f1.map_pairs(pairs, self.schedule(games if games is not None else [self.game()]))

    def artifact(self):
        return {"model_id": f1.MODEL_ID, "feature_columns": DIFF_FEATURES,
                "model": {"penalty": .1, "mean": [0.] * len(DIFF_FEATURES),
                          "scale": [1.] * len(DIFF_FEATURES), "coef": [.5] + [0.] * len(DIFF_FEATURES)}}

    def feature(self, pk=1, **updates):
        return {**{column: 0. for column in DIFF_FEATURES}, "game_pk": pk,
                "feature_travel_complete": True, "home_bullpen_recent_missing": 0,
                "away_bullpen_recent_missing": 0, "feature_cutoff_date": "2026-08-31", **updates}

    def test_partial_and_conflicting_pairs_never_reconstruct_a_quote(self):
        cases = [
            [self.row()],
            [self.row(), self.row(side="away", snapshot_ts="2026-09-01T20:01:00Z")],
            [self.row(), self.row(side="away", book="pinnacle")],
            [self.row(), self.row(side="away", commence_time="2026-09-01T22:05:00Z")],
            [*self.pair_rows(), self.row(american_odds="+110")],
            [*self.pair_rows(), self.row(american_odds="nan")],
            [*self.pair_rows(), self.row(side="draw")],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                pairs, _ = f1.paired_snapshots(rows)
                self.assertEqual(pairs, [])
        pairs, audit = f1.paired_snapshots([*self.pair_rows(), self.row()])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(audit["identical_duplicate_side_rows"], 1)

    def test_invalid_timestamps_are_audited_and_after_start_is_rejected(self):
        for timestamp in (None, "", "nonsense", "2026-09-01T20:00:00", "2026-09-01"):
            pairs, audit = f1.paired_snapshots(self.pair_rows(snapshot_ts=timestamp))
            self.assertEqual(pairs, [])
            self.assertEqual(audit["invalid_rows"], 2)
        pairs, audit = f1.paired_snapshots(self.pair_rows(snapshot_ts="2026-09-01T22:00:00Z"))
        self.assertEqual(pairs, [])
        self.assertEqual(audit["at_or_after_source_start_pairs"], 1)

    def test_recorded_first_pitch_only_tightens_the_pregame_boundary(self):
        pairs, _ = f1.paired_snapshots(self.pair_rows(snapshot_ts="2026-09-01T21:55:00Z"))
        mapped, _, audit = f1.map_pairs(pairs, self.schedule([self.game()]),
            {1: f1.utc("2026-09-01T21:54:00Z")})
        self.assertEqual(mapped, [])
        self.assertEqual(audit["at_or_after_recorded_first_pitch_pairs"], 1)
        later, _, _ = f1.map_pairs(pairs, self.schedule([self.game()]),
            {1: f1.utc("2026-09-01T22:10:00Z")})
        self.assertEqual(len(later), 1)
        # A late actual first pitch cannot make an after-scheduled quote pregame.
        after, _ = f1.paired_snapshots(self.pair_rows(snapshot_ts="2026-09-01T22:01:00Z",
            commence_time="2026-09-01T22:05:00Z"))
        rejected, _, _ = f1.map_pairs(after, self.schedule([self.game()]),
            {1: f1.utc("2026-09-01T22:10:00Z")})
        self.assertEqual(rejected, [])

    def test_unique_official_identity_is_required_and_athletics_is_only_alias(self):
        changed = self.game()
        changed["teams"]["home"]["team"]["name"] = "Athletics"
        mapped, _, _ = self.mapped(self.pair_rows(home="Oakland Athletics"), [changed])
        self.assertEqual(mapped[0]["game_pk"], 1)
        rejected, _, _ = self.mapped(self.pair_rows(home="A's"), [changed])
        self.assertEqual(rejected, [])
        ambiguous, _, audit = self.mapped(games=[self.game(), self.game(gamePk=2)])
        self.assertEqual(ambiguous, [])
        self.assertEqual(audit["unmatched_or_ambiguous_schedule_pairs"], 1)
        outside, _, _ = self.mapped(games=[self.game(gameDate="2026-09-01T22:15:01Z")])
        self.assertEqual(outside, [])
        boundary, _, _ = self.mapped(games=[self.game(gameDate="2026-09-01T22:15:00Z")])
        self.assertEqual(len(boundary), 1)

    def test_schedule_conflicts_are_sticky_and_missing_fixture_metadata_fails_closed(self):
        revised = self.game(gameDate="2026-09-01T22:05:00Z")
        for games in ([self.game(), revised, revised], [revised, self.game(), self.game()]):
            mapped, targets, _ = self.mapped(games=games)
            self.assertTrue(targets[1]["_ambiguous_schedule"])
            self.assertEqual(mapped, [])
        renamed = self.game()
        renamed["teams"]["home"]["team"]["id"] = 99
        mapped, _, _ = self.mapped(games=[renamed, self.game()])
        self.assertEqual(mapped, [])
        for updates in ({"doubleHeader": "Y"}, {"doubleHeader": "S"}, {"scheduledInnings": 7},
                        {"scheduledInnings": None}, {"doubleHeader": None}, {"gameType": "S"}):
            mapped, _, _ = self.mapped(games=[self.game(**updates)])
            self.assertEqual(mapped, [])

    def test_earliest_entry_does_not_depend_on_later_ev_closes_or_outcomes(self):
        early = self.pair_rows()
        later = self.pair_rows(snapshot_ts="2026-09-01T21:00:00Z", american_odds="+100")
        close = self.pair_rows(snapshot_ts="2026-09-01T21:55:00Z", book="pinnacle")
        selected = []
        for extra, game in (([], self.game()), (later + close, self.game()),
                            (later, self.game(status={"detailedState": "Cancelled"}))):
            mapped, targets, _ = self.mapped(early + extra, [game])
            entries, _ = f1.select_entries(mapped)
            self.assertEqual(len(entries), 1)
            selected.append(entries[0])
            forecast = f1.make_forecasts(mapped, entries, targets, [self.feature()], self.artifact())
            self.assertEqual(len(forecast), 1)
            self.assertEqual(forecast.iloc[0].entry_observed_at, "2026-09-01T20:00:00+00:00")
        self.assertEqual(selected[0], selected[1])
        self.assertEqual(selected[0], selected[2])

    def test_entry_window_boundaries_and_canonical_event_dedup(self):
        for lead_minutes, expected in ((360, 1), (361, 0), (30, 1), (29, 0)):
            start = f1.utc(self.row()["commence_time"])
            rows = self.pair_rows(snapshot_ts=(start - timedelta(minutes=lead_minutes)).isoformat())
            mapped, _, _ = self.mapped(rows)
            entries, _ = f1.select_entries(mapped)
            self.assertEqual(len(entries), expected)
        mapped, _, _ = self.mapped(self.pair_rows() + self.pair_rows(
            snapshot_ts="2026-09-01T21:00:00Z", commence_time="2026-09-01T22:05:00Z"))
        entries, _ = f1.select_entries(mapped)
        self.assertEqual([entry["game_pk"] for entry in entries], [1])
        self.assertEqual(entries[0]["observed"], f1.utc("2026-09-01T20:00:00Z"))
        conflicting = self.pair_rows() + self.pair_rows(commence_time="2026-09-01T22:05:00Z")
        for rows in (conflicting, list(reversed(conflicting))):
            mapped, _, _ = self.mapped(rows)
            entries, audit = f1.select_entries(mapped)
            self.assertEqual(entries, [])
            self.assertEqual(audit["conflicting_first_event_snapshot"], 1)
        mapped, _, _ = self.mapped(self.pair_rows(snapshot_ts="2026-09-01T23:00:00Z",
                                                  commence_time="2026-09-02T02:00:00Z"),
                                   [self.game(gameDate="2026-09-02T02:00:00Z", officialDate="2026-09-02")])
        entries, audit = f1.select_entries(mapped)
        self.assertEqual(entries, [])
        self.assertEqual(audit["entry_not_on_official_calendar_date_pairs"], 1)

    def test_near_start_pair_uses_earlier_schedule_and_never_later_prices(self):
        rows = self.pair_rows()
        for timestamp, source_start in (("21:29:59", "22:00:00"), ("21:30:00", "22:00:00"),
                                        ("21:59:00", "22:00:00"), ("21:59:01", "22:00:00"),
                                        ("22:01:00", "22:10:00")):
            rows += self.pair_rows(book="pinnacle", snapshot_ts=f"2026-09-01T{timestamp}Z",
                                   commence_time=f"2026-09-01T{source_start}Z")
        mapped, _, _ = self.mapped(rows)
        entries, _ = f1.select_entries(mapped)
        close = f1.near_start_pair(mapped, entries[0], "pinnacle")
        self.assertEqual(close["observed"], f1.utc("2026-09-01T21:59:00Z"))
        # Moving the publisher start earlier can only tighten that pair's bound.
        changed = {**close, "source_start": f1.utc("2026-09-01T21:55:00Z")}
        self.assertIsNone(f1.near_start_pair([changed], entries[0], "pinnacle"))

    def test_missing_outcomes_and_closes_stay_in_turnover_with_bounds(self):
        rows = self.pair_rows()
        mapped, targets, _ = self.mapped(rows, [self.game(status={"detailedState": "Cancelled"})])
        entries, _ = f1.select_entries(mapped)
        frame = f1.make_forecasts(mapped, entries, targets, [self.feature()], self.artifact())
        report = f1.describe(frame, "p_physical")
        self.assertEqual(report["events"], 1)
        self.assertEqual(report["bets"], 1)
        self.assertEqual(report["turnover_units"], 1)
        self.assertEqual(report["settled_bets"], 0)
        self.assertEqual(report["ungraded_bets"], 1)
        self.assertIsNone(report["roi"])
        self.assertIsNone(report["haircut_roi"])
        self.assertIsNone(report["max_drawdown_daily_units"])
        self.assertEqual(report["max_drawdown_daily_settled_units"], 0)
        self.assertEqual(report["roi_unresolved_outcome_bounds"][0], -1)
        self.assertAlmostEqual(report["roi_unresolved_outcome_bounds"][1], 100 / 110)
        self.assertEqual(report["closing_pinnacle"]["missing_bets"], 1)
        self.assertEqual(report["closing_pinnacle"]["covered_bets"], 0)
        self.assertEqual(report["roi_ci"], [None, None])
        self.assertFalse(report["passes_forward_promotion"])

    def test_unclear_official_outcomes_are_ungraded(self):
        cases = [{"status": {"detailedState": "Completed Early"}}, {"linescore": {"currentInning": 8}},
                 {"resumeDate": "2026-09-02"}, {"resumedFrom": "2026-09-01"}, {"rescheduleDate": "2026-09-02"}]
        for updates in cases:
            self.assertTrue(np.isnan(f1.outcome(self.game(**updates))))
        tied = self.game()
        tied["teams"]["away"]["score"] = 3
        self.assertTrue(np.isnan(f1.outcome(tied)))
        for score in (None, "9", -1, True, np.nan):
            invalid = self.game()
            invalid["teams"]["home"]["score"] = score
            self.assertTrue(np.isnan(f1.outcome(invalid)))
        self.assertTrue(np.isnan(f1.outcome(self.game(linescore={"currentInning": "9"}))))

    def test_synthetic_run_compares_exact_shared_population_and_retains_missing_models(self):
        # Exercise run wiring with a generated export and mocked feature builder.
        # No real source file, model artifact, or outcome is read.
        raw_rows, games = [], []
        for pk in (1, 2, 3):
            home = f"Home {pk}"
            raw_rows += self.pair_rows(home=home)
            if pk != 3:
                raw_rows += self.pair_rows(home=home, book="pinnacle")
            game = self.game(gamePk=pk)
            game["teams"]["home"]["team"]["name"] = home
            games.append(game)
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(raw_rows[0]))
        writer.writeheader(); writer.writerows(raw_rows)
        raw = stream.getvalue().encode()
        artifact_raw = json.dumps(self.artifact()).encode()
        real_read_bytes = Path.read_bytes

        def read_bytes(path):
            return artifact_raw if str(path) == "reports/physical_model.json" else real_read_bytes(path)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export = root / "synthetic.csv"
            export.write_bytes(raw)
            (root / "schedule_2026.json").write_text(json.dumps(self.schedule(games)))
            (root / "source_manifest.json").write_text(json.dumps({"synthetic": True}))
            with patch.object(f1, "EXPORT_SHA", hashlib.sha256(raw).hexdigest()), \
                    patch.object(f1, "ARTIFACT_SHA", hashlib.sha256(artifact_raw).hexdigest()), \
                    patch.object(Path, "read_bytes", read_bytes), \
                    patch.object(f1, "load_games", return_value=[]), \
                    patch.object(f1, "load_appearances", return_value=[]), \
                    patch.object(f1, "load_venues", return_value={}), \
                    patch.object(f1, "build_features", return_value=[self.feature(1), self.feature(3)]), \
                    patch("builtins.print"):
                result = f1.run(export, root, root / "reports")
            own = result["own_available_population"]
            self.assertEqual({key: node["events"] for key, node in own.items()}, {"fanduel": 3, "physical": 2, "pinnacle": 2})
            self.assertEqual({node["events"] for node in result["shared_population"].values()}, {1})
            self.assertEqual(result["physical_blocks"], {"missing_features": 1})
            forecasts = pd.read_csv(root / "reports" / "timestamped-mlb-forecasts.csv")
            self.assertEqual(set(forecasts.event_id), {"mlb:1", "mlb:2", "mlb:3"})
            physical = result["shared_population"]["physical"]
            market = result["shared_population"]["fanduel"]
            self.assertEqual(physical["market_log_loss"], market["log_loss"])


if __name__ == "__main__":
    unittest.main()
