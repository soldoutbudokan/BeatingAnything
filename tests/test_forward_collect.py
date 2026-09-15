"""Synthetic acquisition tests; no market evidence and no network requests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from beating.forward_collect import Collector, StopCollection
from beating.forward_collect_demo import demo_get


class ForwardCollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        return [json.loads(line) for line in (self.output / "index.jsonl").read_text().splitlines()]

    def collector(self, **kwargs):
        return Collector(self.output, {"sports": ["baseball_mlb"]}, **kwargs)

    def test_raw_bytes_append_and_independent_clocks(self):
        raw = b'{ "id":"EVENT", "bookmakers":[{"key":"fanduel", "markets":[{"key":"prop", "last_update":"2020-01-01T00:00:00Z", "outcomes":[], "unknown_field":true}]}] }\n'
        collector = self.collector(api_key="secret-never-in-index", transport=lambda *_: (
            200, {"Date": "Wed, 01 Jan 2020 00:00:02 GMT", "Set-Cookie": "do-not-save"}, raw))
        for _ in range(2):
            collector.fetch("the_odds_api", "/v4/sports/x/events/y/odds")
        rows = [row for row in self.rows() if row["kind"] == "response"]
        self.assertNotEqual(rows[0]["raw_file"], rows[1]["raw_file"])
        for row in rows:
            self.assertEqual((self.output / row["raw_file"]).read_bytes(), raw)
            self.assertEqual(row["raw_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(row["clocks"]["market_clocks"][0]["market_last_update"], "2020-01-01T00:00:00Z")
            self.assertIsNone(row["clocks"]["market_clocks"][0]["bookmaker_last_update"])
            self.assertIsNone(row["clocks"]["provider_snapshot_at"])
            self.assertLessEqual(row["collector_request_started_at"], row["collector_response_received_at"])
            self.assertNotEqual(row["collector_response_received_at"], row["provider_http_date"])
        index = (self.output / "index.jsonl").read_text()
        self.assertNotIn("secret-never-in-index", index)
        self.assertNotIn("do-not-save", index)

    def test_discovered_props_alts_and_started_events_are_all_requested(self):
        calls = []
        def get(url, timeout):
            calls.append(url)
            return demo_get(url, timeout)
        collector = Collector(self.output, {"sports": ["baseball_mlb"], "mlb_game_state": True,
                                           "market_batch_size": 2}, transport=get, synthetic=True)
        summary = collector.run()
        self.assertEqual(summary["stop_reason"], "cycles_complete")
        self.assertEqual(summary["real_odds_responses"], 0)
        self.assertEqual(summary["credit_upper_reserved"], 4)
        self.assertEqual(summary["mlb_feed_responses"], 1)
        odds_calls = [parse_qs(urlsplit(url).query) for url in calls if urlsplit(url).path.endswith("/odds")]
        self.assertEqual({market for call in odds_calls for market in call["markets"][0].split(",")},
                         {"alternate_totals", "batter_hits", "h2h"})
        self.assertTrue(all(call["bookmakers"] == ["fanduel,pinnacle"] for call in odds_calls))
        feeds = [row for row in self.rows() if row.get("context", {}).get("game_pk")]
        self.assertEqual(feeds[0]["clocks"]["feed_time_stamp"], "20200101_120504")
        self.assertIsNone(feeds[0]["clocks"]["odds_event_id"])

    def test_http_denial_raw_body_retained_and_no_retry(self):
        calls = []
        def denied(*args):
            calls.append(args)
            return 403, {"Retry-After": "60"}, b"<html>denied</html>"
        summary = self.collector(api_key="test", transport=denied).run()
        self.assertEqual(summary["stop_reason"], "http_403")
        self.assertEqual(len(calls), 1)
        row = next(row for row in self.rows() if row["kind"] == "response")
        self.assertEqual((self.output / row["raw_file"]).read_bytes(), b"<html>denied</html>")

    def test_invalid_json_and_network_errors_are_recorded(self):
        def fail(*_):
            raise URLError("https://source/?apiKey=do-not-log")
        for transport, expected in ((lambda *_: (200, {}, b"not json"), "invalid_json"), (fail, "URLError")):
            with self.subTest(expected=expected):
                summary = self.collector(api_key="test", transport=transport).run()
                self.assertEqual(summary["stop_reason"], expected)
                self.assertEqual(summary["odds_responses"], 0)
        self.assertNotIn("do-not-log", (self.output / "index.jsonl").read_text())

    def test_credit_cap_blocks_request_before_transport(self):
        calls = []
        collector = Collector(self.output, {"max_credits": 1}, api_key="test",
                              transport=lambda *_: calls.append(True))
        with self.assertRaisesRegex(StopCollection, "credit_cap"):
            collector.fetch("the_odds_api", "/unused", credit_upper=2)
        self.assertEqual(calls, [])

    def test_provider_balance_blocks_request_before_transport(self):
        collector = self.collector(api_key="test", transport=lambda *_: (200, {"x-requests-remaining": "1"}, b"[]"))
        collector.fetch("the_odds_api", "/v4/sports")
        with self.assertRaisesRegex(StopCollection, "provider_credit_balance"):
            collector.fetch("the_odds_api", "/unused", credit_upper=2)
        self.assertEqual(collector.requests, 1)


if __name__ == "__main__":
    unittest.main()
