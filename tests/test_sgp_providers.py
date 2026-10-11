"""Provider contract tests with injected transports; no live or paid calls."""
import hashlib
from http.client import BadStatusLine
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from beating.sgp.providers import (
    OpticOddsProvider, ProviderError, RequestBudgetExceeded, parse_parlay_response,
)


ENTRIES = [
    {"fixture_id": "fixture-1", "market": "Player Rushing Yards", "name": "Player Under 49.5"},
    {"fixture_id": "fixture-1", "market": "Player Receiving Yards", "name": "Player Over 34.5"},
]


def priced(entries=ENTRIES, price=1064):
    return {"data": {"theScore": {"error": None, "missing_entries": None,
                                  "legs": [dict(entry, price=-110) for entry in entries],
                                  "price": price}}}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def client(self, value=None, **kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = lambda *_: (200, {}, json.dumps(value).encode())
        kwargs.setdefault("min_interval_seconds", 0)
        return OpticOddsProvider(self.directory, api_key="test-private-key", **kwargs)

    def test_request_spacing_is_shared_by_snapshots_and_quotes(self):
        ticks, sleeps, starts = [10.0], [], []

        def sleep(delay):
            sleeps.append(delay)
            ticks[0] += delay

        def request(method, url, *_):
            starts.append(ticks[0])
            ticks[0] += 0.125  # Time spent in the transport counts toward spacing.
            value = priced() if method == "POST" else {"data": []}
            return 200, {}, json.dumps(value).encode()

        client = self.client(transport=request, min_interval_seconds=0.5,
                             sleeper=sleep, monotonic=lambda: ticks[0])
        client.snapshot(["fixture-1"], ["theScore"])
        client.quote("theScore", ENTRIES)
        ticks[0] += 1  # A sufficiently long pause needs no additional sleep.
        client.quote("theScore", ENTRIES)
        self.assertEqual(starts, [10, 10.5, 11.625])
        self.assertEqual(sleeps, [0.375])
        self.assertEqual(client.requests, 3)

    def test_request_interval_is_bounded_and_finite(self):
        for interval in (-1, 60.1, True, float("inf"), float("nan"), "0.5"):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.client(min_interval_seconds=interval)
        self.assertEqual(OpticOddsProvider(self.directory).min_interval_seconds, 0.5)

    def test_quote_is_bound_to_exact_legs_and_keeps_unknown_freshness(self):
        calls = []

        def request(method, url, headers, body, timeout):
            calls.append((method, url, headers, json.loads(body), timeout))
            return 200, {"Date": "Fri, 09 Oct 2026 21:00:00 GMT"}, json.dumps(priced()).encode()

        client = self.client(transport=request)
        result = client.quote("theScore", ENTRIES)
        self.assertEqual(result["status"], "priced")
        self.assertEqual(result["american"], 1064)
        self.assertTrue(result["exact_legs_verified"])
        self.assertIsNone(result["source_timestamp"])
        self.assertEqual(result["jurisdiction"], "unverified")
        self.assertEqual(result["source_freshness"], "unverified")
        method, url, headers, body, _ = calls[0]
        self.assertEqual(method, "POST")
        self.assertNotIn("test-private-key", url)
        self.assertEqual(headers["X-Api-Key"], "test-private-key")
        self.assertEqual(body, {"sportsbooks": ["theScore"], "entries": ENTRIES})
        self.assertEqual(parse_qs(urlsplit(url).query),
                         {"odds_format": ["AMERICAN"], "allow_missing_entries": ["false"]})
        raw = (self.directory / result["raw_ref"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["raw_sha256"])

    def test_same_leg_count_does_not_validate_stale_selections(self):
        value = priced()
        value["data"]["theScore"]["legs"][0]["name"] = "Player Under 54.5"
        result = parse_parlay_response(value, "theScore", ENTRIES)
        self.assertEqual(result["error"], "returned_legs_mismatch")
        self.assertIsNone(result["american"])

    def test_duplicate_entries_must_be_returned_with_same_multiplicity(self):
        repeated = [*ENTRIES, ENTRIES[1]]
        client = self.client(priced(repeated))
        result = client.quote("theScore", repeated)
        self.assertEqual(result["entries"], repeated)
        self.assertEqual(result["status"], "priced")
        dropped = parse_parlay_response(priced(), "theScore", repeated)
        self.assertEqual(dropped["error"], "returned_legs_mismatch")

    def test_reordered_response_is_allowed_but_request_order_is_preserved(self):
        result = self.client(priced(ENTRIES[::-1])).quote("theScore", ENTRIES)
        self.assertEqual(result["status"], "priced")
        self.assertEqual(result["entries"], ENTRIES)

    def test_missing_error_and_null_price_do_not_become_quotes(self):
        for patch, expected in (({"error": "SelectionsCannotBeCombined"}, "unavailable"),
                                ({"missing_entries": [ENTRIES[0]]}, "unavailable"),
                                ({"price": None}, "error"),
                                ({"legs": None}, "error")):
            with self.subTest(patch=patch):
                value = priced()
                value["data"]["theScore"].update(patch)
                result = parse_parlay_response(value, "theScore", ENTRIES)
                self.assertEqual(result["status"], expected)
                self.assertIsNone(result["american"])

    def test_invalid_prices_fail_closed(self):
        for price in (True, 0, 99, -99, "1064", float("nan"), float("inf")):
            with self.subTest(price=price):
                result = parse_parlay_response(priced(price=price), "theScore", ENTRIES)
                self.assertEqual(result["error"], "invalid_american_price")
        self.assertEqual(parse_parlay_response(priced(price=-120), "theScore", ENTRIES)
                         ["status"], "priced")

    def test_unsupported_books_and_ai_never_send_request(self):
        calls = []
        client = self.client(transport=lambda *_: calls.append(True))
        for book in ("OpticOdds AI", "FanDuel", "thescore"):
            with self.subTest(book=book), self.assertRaises(ProviderError):
                client.quote(book, ENTRIES)
        self.assertEqual(calls, [])

    def test_no_key_never_calls_transport(self):
        calls = []
        client = OpticOddsProvider(self.directory, transport=lambda *_: calls.append(True))
        with self.assertRaisesRegex(ProviderError, "missing_OPTICODDS_API_KEY"):
            client.quote("theScore", ENTRIES)
        self.assertEqual(calls, [])
        self.assertEqual(client.requests, 0)

    def test_budget_is_reserved_before_transport(self):
        client = self.client(priced(), max_requests=1)
        client.quote("theScore", ENTRIES)
        with self.assertRaises(RequestBudgetExceeded):
            client.quote("theScore", ENTRIES)
        self.assertEqual(client.requests, 1)

    def test_denials_stop_without_retry_and_redact_echoed_keys(self):
        calls = []

        def request(*_):
            calls.append(True)
            return 429, {"Retry-After": "30", "X-Api-Key": "test-private-key"}, b'{"error":"test-private-key"}'

        client = self.client(transport=request)
        with self.assertRaisesRegex(ProviderError, "http_429"):
            client.quote("theScore", ENTRIES)
        with self.assertRaisesRegex(ProviderError, "collection_stopped"):
            client.quote("theScore", ENTRIES)
        self.assertEqual(len(calls), 1)
        for path in self.directory.rglob("*"):
            if path.is_file():
                self.assertNotIn("test-private-key", path.read_text())
        log = json.loads((self.directory / "requests.jsonl").read_text())
        self.assertTrue(log["credentials_redacted"])
        self.assertEqual(log["response_headers"], {"retry-after": "30"})

    def test_transport_exception_does_not_expose_details(self):
        def request(*_):
            raise URLError("test-private-key")

        client = self.client(transport=request)
        with self.assertRaisesRegex(ProviderError, "URLError") as caught:
            client.quote("theScore", ENTRIES)
        self.assertNotIn("test-private-key", str(caught.exception))
        self.assertNotIn("test-private-key", (self.directory / "requests.jsonl").read_text())

    def test_unusual_http_failures_are_sanitized_and_stop_collection(self):
        calls = []

        def request(*_):
            calls.append(True)
            raise BadStatusLine("test-private-key")

        client = self.client(transport=request)
        with self.assertRaisesRegex(ProviderError, "BadStatusLine") as caught:
            client.discover_fixtures()
        self.assertNotIn("test-private-key", str(caught.exception))
        with self.assertRaisesRegex(ProviderError, "collection_stopped"):
            client.discover_fixtures()
        self.assertEqual(len(calls), 1)

    def test_discovery_paginates_and_fails_on_truncation(self):
        pages = []

        def request(method, url, *_):
            query = parse_qs(urlsplit(url).query)
            page = int(query["page"][0])
            pages.append(page)
            self.assertEqual(query["league"], ["nfl", "ncaaf"])
            return 200, {}, json.dumps({"data": [{"id": f"fixture-{page}"}],
                                        "page": page, "has_more": page == 1}).encode()

        client = self.client(transport=request)
        fixtures = client.discover_fixtures(["nfl", "ncaaf"])
        self.assertEqual(pages, [1, 2])
        self.assertEqual(len(fixtures), 2)
        with self.assertRaisesRegex(ProviderError, "pagination_incomplete"):
            client.discover_fixtures(["nfl", "ncaaf"], max_pages=1)

    def test_snapshots_batch_and_preserve_source_timestamps(self):
        scopes = []

        def request(method, url, *_):
            query = parse_qs(urlsplit(url).query)
            scopes.append(query)
            data = [{"id": fixture_id, "odds": [{"timestamp": 123.456}]}
                    for fixture_id in query["fixture_id"]]
            return 200, {}, json.dumps({"data": data}).encode()

        client = self.client(transport=request)
        payloads = client.snapshots([f"f{i}" for i in range(7)], ["theScore", "FanDuel"])
        self.assertEqual([len(item["fixture_id"]) for item in scopes], [5, 2])
        self.assertEqual(scopes[0]["sportsbook"], ["theScore", "FanDuel"])
        self.assertEqual(payloads[0]["data"][0]["odds"][0]["timestamp"], 123.456)
        self.assertTrue(payloads[0]["collection"]["complete"])

    def test_failed_snapshot_does_not_return_empty_complete_snapshot(self):
        client = self.client({"data": [{"id": "other-fixture", "odds": []}]})
        with self.assertRaisesRegex(ProviderError, "invalid_snapshot_fixture"):
            client.snapshot(["f1"], ["theScore"])


if __name__ == "__main__":
    unittest.main()
