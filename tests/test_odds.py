"""Economic and identity invariants for the archive boundary."""
import json
from pathlib import Path
import tempfile
import unittest

from beating.odds import american_to_decimal, load_archive


class OddsBoundaryTests(unittest.TestCase):
    def fixture(self, folder: Path, *, double=False, terminal=-1100, score=3):
        raw = {"2021-04-01": [{
            "gameView": {"startDate": "2021-04-01T17:10:00Z", "gameType": "Unknown",
                "homeTeam": {"shortName": "DET"}, "awayTeam": {"shortName": "CLE"},
                "homeTeamScore": score, "awayTeamScore": 2, "gameStatusText": "Final"},
            "odds": {"moneyline": [{"sportsbook": "fanduel", "openingLine": {"homeOdds": 158, "awayOdds": -192},
                "currentLine": {"homeOdds": terminal, "awayOdds": 620}}]}}]}
        game = {"gamePk": 1, "officialDate": "2021-04-01", "gameDate": "2021-04-01T17:10:00Z",
            "gameType": "R", "doubleHeader": "Y" if double else "N",
            "status": {"detailedState": "Final"}, "teams": {
                "home": {"team": {"id": 116, "name": "Detroit Tigers"}, "score": 3},
                "away": {"team": {"id": 114, "name": "Cleveland Guardians"}, "score": 2}}}
        a, s = folder / "raw.json", folder / "schedule.json"
        a.write_text(json.dumps(raw)); s.write_text(json.dumps({"dates": [{"date": "2021-04-01", "games": [game]}]}))
        return a, [s]

    def test_terminal_in_play_price_cannot_change_model_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            a, s = self.fixture(folder)
            first, _ = load_archive(a, s)
            a, s = self.fixture(folder, terminal=999999)
            second, _ = load_archive(a, s)
            self.assertTrue(first.equals(second))
            self.assertEqual(len(first), 1)
            self.assertAlmostEqual(first.iloc[0].fd_home_open_decimal, 2.58)
            self.assertFalse(any("current" in c or "close" in c for c in first.columns))

    def test_doubleheader_cannot_silently_join_an_opening_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, s = self.fixture(Path(tmp), double=True)
            rows, audit = load_archive(a, s)
            self.assertEqual(len(rows), 0)
            self.assertEqual(audit["structural_exclusions"]["doubleheader_source_merge_risk"], 1)

    def test_result_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, s = self.fixture(Path(tmp), score=7)
            rows, audit = load_archive(a, s)
            self.assertEqual(len(rows), 0)
            self.assertEqual(audit["structural_exclusions"]["score_disagrees_with_mlb"], 1)

    def test_odds_returns_have_correct_units(self):
        self.assertEqual(american_to_decimal(200), 3)
        self.assertEqual(american_to_decimal(-200), 1.5)
        for price in (0, 99, float("nan"), float("inf"), None, True):
            with self.assertRaises(ValueError):
                american_to_decimal(price)


if __name__ == "__main__":
    unittest.main()
