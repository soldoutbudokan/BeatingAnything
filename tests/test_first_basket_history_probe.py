import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from tools.probe_first_basket_history import (
    Client, NoRedirect, PLAN, ProbeStopped, cached_catalogs, choose_fixtures, first_score_markets, history_inventory,
)


class FakeResponse:
    def __init__(self, body, headers=None):
        self.body, self.status, self.headers = body, 200, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.body[:size]


class FakeOpener:
    def __init__(self, response):
        self.response, self.calls = response, []

    def open(self, request, timeout):
        self.calls.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class HistoryProbeTests(unittest.TestCase):
    def test_fixture_selection_ignores_price_availability_and_enforces_zoned_interval(self):
        fixtures = [{"fixtureId": str(i), "sportId": 11, "tournamentSlug": "nba",
                     "startTime": f"2026-03-02T{20+i}:00:00Z", "hasOdds": i != 0} for i in range(4)]
        self.assertEqual([r["fixtureId"] for r in choose_fixtures(list(reversed(fixtures)))], ["0", "1", "2"])
        boundary = {**fixtures[0], "fixtureId": "boundary", "startTime": PLAN["to"]}
        self.assertEqual(choose_fixtures([boundary]), [])
        self.assertEqual(choose_fixtures(fixtures + [boundary]), fixtures[:3])
        for rows in ([fixtures[0], fixtures[0]], [{**fixtures[0], "startTime": "2026-03-02T20:00:00"}],
                     [{**fixtures[0], "startTime": "2025-03-02T20:00:00Z"}]):
            with self.assertRaises(ProbeStopped):
                choose_fixtures(rows)

    def test_only_player_first_score_catalog_and_valid_active_pregame_entries_count(self):
        catalog = [{"marketId": 7, "sportId": 11, "playerProp": True, "marketName": "First Basket"},
                   {"marketId": 8, "sportId": 11, "playerProp": False, "marketName": "Team First Basket"},
                   {"marketId": 9, "sportId": 11, "playerProp": True, "marketName": "Player Points"},
                   {"marketId": 10, "sportId": 11, "playerProp": True, "marketName": "Over Under Player Points First Quarter"},
                   {"marketId": 11, "sportId": 11, "playerProp": True, "marketName": "Player First 3 Point FG"}]
        chosen = first_score_markets(catalog)
        self.assertEqual([r["marketId"] for r in chosen], [7])
        self.assertEqual(first_score_markets([{**catalog[0], "marketName": "Player First Point"}])[0]["marketId"], 7)
        valid = {"price": 10, "createdAt": "2026-03-02T19:00:00Z", "active": True}
        response = {"fixtureId": "a", "bookmakers": {"fanduel": {"markets": {"7": {"outcomes": {
            "yes": {"players": {"10": [valid, {**valid, "active": False}, {**valid, "createdAt": "2026-03-02T22:00:00Z"}],
                                  "11": [{**valid, "createdAt": "2026-03-02T19:00:00"}],
                                  "0": [valid]}}}}}}}}
        result = history_inventory(response, {"fixtureId": "a", "startTime": "2026-03-02T20:00:00Z"}, chosen)
        row = result["first_score_market_coverage"][0]
        self.assertEqual(row["players_with_active_pregame_entry"], 1)
        self.assertEqual(row["counts"]["active_pregame_entries"], 1)
        self.assertEqual(row["counts"]["invalid_price_or_clock"], 1)
        self.assertFalse(result["qualified_replication"])
        with self.assertRaises(ProbeStopped):
            history_inventory(response, {"fixtureId": "wrong"}, chosen)

    def test_credentials_never_enter_retained_url_body_or_error(self):
        key = "private-probe-test-key"
        cases = [FakeResponse(json.dumps({"echo": key}).encode()),
                 urllib.error.HTTPError("https://example.invalid/?apiKey=" + key, 403, key, {}, io.BytesIO(b'{"denied":true}')),
                 urllib.error.URLError("https://example.invalid/?apiKey=" + key)]
        for response in cases:
            with self.subTest(response=type(response).__name__), tempfile.TemporaryDirectory() as tmp:
                opener = FakeOpener(response)
                client = Client(key, Path(tmp), opener=opener)
                with self.assertRaises(ProbeStopped) as caught:
                    client.get("markets", {"language": "en"})
                self.assertNotIn(key, str(caught.exception))
                self.assertEqual(len(opener.calls), 1)
                for path in Path(tmp).iterdir():
                    self.assertNotIn(key.encode(), path.read_bytes())

    def test_request_cap_cooldown_and_no_redirect(self):
        with tempfile.TemporaryDirectory() as tmp:
            waits = []
            client = Client("private-probe-test-key", Path(tmp), opener=FakeOpener(FakeResponse(b'{}')), wait=waits.append)
            client.get("historical-odds", {"fixtureId": "a"})
            client.get("historical-odds", {"fixtureId": "b"})
            self.assertEqual(len(waits), 1)
            self.assertGreater(waits[0], 5)
            client.calls = PLAN["max_requests"]
            with self.assertRaises(ProbeStopped):
                client.get("fixtures", {})
            with self.assertRaises(ProbeStopped):
                client.get("settlements", {})
            self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.invalid"))

    def test_cached_catalogs_require_matching_receipts_and_no_prior_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "source", Path(tmp) / "output"
            source.mkdir()
            output.mkdir()
            (source / "plan.json").write_text(json.dumps(PLAN))
            client = Client("private-probe-test-key", source, opener=FakeOpener(FakeResponse(b'[]')))
            client.get("bookmakers", {})
            client.get("markets", {"language": "en"})
            client.get("fixtures", {"sportId": 11, "from": PLAN["from"], "to": PLAN["to"]})
            self.assertEqual(cached_catalogs(source, output), {"bookmakers": [], "markets": [], "fixtures": []})
            (source / "04-historical-odds.meta.json").write_text("{}")
            with self.assertRaises(ProbeStopped):
                cached_catalogs(source, output)
            (source / "04-historical-odds.meta.json").unlink()
            (source / "03-fixtures.json").write_text('[{}]')
            with self.assertRaises(ProbeStopped):
                cached_catalogs(source, output)


if __name__ == "__main__":
    unittest.main()
