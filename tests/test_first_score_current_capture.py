import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from tools.capture_nba_first_score_current import CaptureStopped, fetch, inventory


class CurrentCaptureTests(unittest.TestCase):
    def fixture(self):
        return {"fixtureId": "SYNTHETIC", "sportId": 11, "tournamentId": 132, "tournamentSlug": "nba",
            "bookmakerOdds": {"fanduel": {"bookmakerIsActive": True, "suspended": False, "markets": {
                "112604": {"marketActive": False, "outcomes": {"112604": {"players": {
                    "1": {"active": True, "price": 8, "changedAt": "2020-01-01T00:00:00Z", "bookmakerChangedAt": None}
                }}}}}}}}

    def test_inactive_market_overrides_active_selection_and_missing_clock_stays_missing(self):
        result = inventory([self.fixture()], "fanduel")
        self.assertEqual(result["selection_active_inside_inactive_market"], 1)
        self.assertEqual(result["target_selection_count"], 1)
        self.assertFalse(result["target_selections"][0]["all_provider_open_flags"])
        self.assertIsNone(result["target_selections"][0]["bookmaker_changed_at"])
        self.assertFalse(result["source_verified"])

    def test_scope_and_duplicate_fixtures_stop(self):
        row = self.fixture()
        with self.assertRaises(CaptureStopped):
            inventory([row, row], "fanduel")
        row["tournamentId"] = 999
        with self.assertRaises(CaptureStopped):
            inventory([row], "fanduel")

    def test_single_book_parameter_raw_retention_and_separate_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = json.dumps([self.fixture()]).encode()
            def get(url):
                query = parse_qs(urlsplit(url).query)
                self.assertEqual(query["bookmaker"], ["fanduel"])
                self.assertNotIn("bookmakers", query)
                return 200, "SYNTHETIC-HTTP-DATE", raw
            data, meta = fetch("fanduel", "SYNTHETIC-KEY", Path(tmp), get)
            self.assertEqual((Path(tmp)/"fanduel.json").read_bytes(), raw)
            self.assertNotIn("SYNTHETIC-KEY", json.dumps(meta))
            self.assertEqual(meta["http_date"], "SYNTHETIC-HTTP-DATE")
            self.assertIn("response_received_at", meta)

    def test_echo_and_http_denial_stop_without_retry(self):
        for status, body, retained in ((200, b'SYNTHETIC-KEY', False), (403, b'{"error":"denied"}', True)):
            with tempfile.TemporaryDirectory() as tmp:
                calls = []
                def get(url):
                    calls.append(1)
                    return status, None, body
                with self.assertRaises(CaptureStopped):
                    fetch("fanduel", "SYNTHETIC-KEY", Path(tmp), get)
                self.assertEqual(len(calls), 1)
                self.assertEqual((Path(tmp)/"fanduel.json").exists(), retained)


if __name__ == "__main__":
    unittest.main()
