import base64
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError

from beating.golf_collect import (
    Collector, StopCollection, decode_payloads, json_bytes, parse_pga_html,
    payload_inventory, player_ids, retry_not_before,
)


PAGE = "https://www.pgatour.com/tournaments/2026/biltmore-championship-asheville/R2026557/odds"
SELECTION_URL = ("https://account.sportsbook.fanduel.com/sportsbook/addToBetslip"
                 "?marketId=42.599903063&selectionId=14753599&shareBetId=partner_sportstechinc")


class FakeTime:
    def __init__(self):
        self.tick = 0.0
        self.sleeps = []

    def now(self):
        return (datetime(2026, 9, 14, tzinfo=timezone.utc) + timedelta(seconds=self.tick)).isoformat()

    def monotonic(self):
        return self.tick

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.tick += seconds


def page_state(data):
    return json_bytes({"props": {"pageProps": {"dehydratedState": {"queries": [
        {"queryKey": ["oddsMarketTournament", {"tournamentId": "R2026557"}],
         "state": {"dataUpdatedAt": 1789340400000, "data": data}}
    ]}}}})


def html(data):
    return b'<html><script type="application/json" id="__NEXT_DATA__">' + page_state(data) + b'</script></html>'


class GolfCollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.time = FakeTime()
        self.calls = []

    def make_collector(self, config=None, responses=None):
        responses = list(responses or [])

        def transport(method, url, body, headers, timeout):
            self.calls.append({"method": method, "url": url, "body": body,
                               "headers": headers, "tick": self.time.tick, "timeout": timeout})
            self.time.tick += 0.25
            response = responses.pop(0) if responses else (200, {}, b'{"events":[]}')
            if isinstance(response, Exception):
                raise response
            return response

        return Collector(self.output, {"espn_state": True, **(config or {})}, transport=transport,
                         clock=self.time.now, monotonic=self.time.monotonic,
                         sleep=self.time.sleep, api_key="DO-NOT-LOG-THIS-KEY")

    def records(self):
        return [json.loads(line) for line in (self.output / "index.jsonl").read_text().splitlines()]

    def test_exact_raw_and_request_bytes_hashed_and_clocks_separate(self):
        raw = b'{"lastUpdated":"2026-09-14T11:00:00Z", "teeTime": 1789392000000, "players": []}\n'
        collector = self.make_collector(responses=[(200, {"Date": "Mon, 14 Sep 2026 11:01:00 GMT", "Set-Cookie": "secret"}, raw)])
        collector.fetch("pga_rest", "/odds/tournament/R2026557", odds=True)
        row = next(x for x in self.records() if x["kind"] == "response")
        self.assertEqual((self.output / row["response"]["file"]).read_bytes(), raw)
        for key in ("request", "response"):
            entry = row[key]
            self.assertEqual(entry["sha256"], hashlib.sha256((self.output / entry["file"]).read_bytes()).hexdigest())
        self.assertEqual(row["collector_request_started_at"], "2026-09-14T00:00:00+00:00")
        self.assertEqual(row["collector_response_received_at"], "2026-09-14T00:00:00.250000+00:00")
        self.assertEqual([x["kind"] for x in row["source_clocks"]], ["source_update", "event_or_forecast"])
        self.assertNotIn("set-cookie", row["response_headers"])
        self.assertEqual(row["quote_status"], "no_quotes")

    def test_empty_html_partner_config_is_not_a_quote_or_book(self):
        raw = html({"availableMarkets": [], "oddsUrl": "https://sportsbook.fanduel.com/navigation/pga",
                    "message": {"header": "Odds are unavailable"}, "oddsEnabled": False})
        collector = self.make_collector({"pga_pages": [PAGE], "espn_state": False}, [(200, {}, raw)])
        summary = collector.run()
        self.assertEqual(summary["requests"], 1)
        self.assertEqual(summary["quote_status"], "no_quotes")
        self.assertEqual(summary["explicitly_fanduel_price_field_observations"], 0)
        row = next(x for x in self.records() if x["kind"] == "response")
        self.assertEqual(row["book_labels"], [])
        self.assertEqual(row["source_clocks"][0]["kind"], "page_cache_update")
        self.assertEqual(json.loads((self.output / row["decoded"]["file"]).read_bytes()), parse_pga_html(raw))

    def test_quotes_keep_actual_book_without_partner_or_sibling_inference(self):
        inventory = payload_inventory({"oddsUrl": "https://sportsbook.fanduel.com/",
            "availableMarkets": [
                {"book": "DraftKings", "group": [{"oddsValue": "+250"}]},
                {"book": "FanDuel", "group": [{"oddsValue": "-110"}]},
                {"group": [{"decimalOdds": 2.5}]},
            ], "empty": [{"oddsValue": "-"}, {"oddsValue": 0}, {"oddsValue": True}]}, odds=True)
        quotes = inventory["quote_observations"]
        self.assertEqual(len(quotes), 3)
        self.assertEqual([q["book_labels"] for q in quotes], [["DraftKings"], ["FanDuel"], []])

    def test_nested_book_overrides_ancestor_and_conflict_is_not_fanduel(self):
        inventory = payload_inventory({"book": "FanDuel", "market": {"book": "Pinnacle", "decimalOdds": 2.0}}, odds=True)
        self.assertEqual(inventory["quote_observations"][0]["book_labels"], ["Pinnacle"])
        inventory = payload_inventory({"book": "FanDuel", "market": {"book": None, "decimalOdds": 2.0}}, odds=True)
        self.assertEqual(inventory["quote_observations"][0]["book_labels"], [])
        collector = self.make_collector(responses=[(200, {}, b'{"book":"FanDuel","sportsbook":"Pinnacle","decimalOdds":2.0}')])
        collector.fetch("pga_rest", "/odds/test", odds=True)
        self.assertEqual(collector.fanduel_price_fields, 0)

    def test_actual_rest_group_schema_has_separate_selection_link_attribution(self):
        # Shape and two sample prices from the public pgatouR odds_player.rds
        # fixture at 74551e5bebc9e189781d75a88d57c68c87ec4860.
        value = {"playerMarkets": [{"marketType": "MATCHUP_PROPS", "bettingPeriod": 3,
            "oddsDataGroup": [{"title": "18 Hole Matchbet - Round 3",
                "oddsData": [{"type": "GROUP", "groupCount": 2, "group": [
                    {"players": [{"playerId": "46046", "displayName": "Scottie Scheffler"}],
                     "oddsValue": "-163", "optionId": "42.599903063", "entityId": "46046", "url": SELECTION_URL},
                    {"players": [{"playerId": "30911", "displayName": "Tommy Fleetwood"}],
                     "oddsValue": "+125", "optionId": "42.599903063", "entityId": "30911",
                     "url": SELECTION_URL.replace("14753599", "13496408")},
                ]}]}]}]}
        original = json_bytes(value)
        inventory = payload_inventory(value, odds=True)
        quotes = inventory["quote_observations"]
        self.assertEqual(json_bytes(value), original)
        self.assertEqual([q["book_labels"] for q in quotes], [[], []])
        self.assertEqual([q["fanduel_selection_link"]["status"] for q in quotes], ["attributed", "attributed"])
        self.assertEqual([q["fanduel_selection_link"]["selection_id"] for q in quotes], ["14753599", "13496408"])
        self.assertTrue(quotes[0]["fanduel_selection_link"]["path"].endswith(".group[0].url"))
        collector = self.make_collector({"pga_pages": [PAGE], "espn_state": False}, [(200, {}, html(value))])
        summary = collector.run()
        self.assertEqual(summary["price_field_observations"], 2)
        self.assertEqual(summary["explicitly_fanduel_price_field_observations"], 0)
        self.assertEqual(summary["fanduel_selection_link_price_field_observations"], 2)

    def test_selection_link_is_not_inherited_from_parent_sibling_or_catalog(self):
        value = {"url": SELECTION_URL, "catalog": [{"url": SELECTION_URL}],
                 "groups": [{"decimalOdds": 2.5}, {"url": SELECTION_URL}],
                 "partner": {"url": "https://account.sportsbook.fanduel.com/navigation/pga", "decimalOdds": 2.0}}
        quotes = payload_inventory(value, odds=True)["quote_observations"]
        self.assertEqual(len(quotes), 2)
        self.assertTrue(all("fanduel_selection_link" not in q for q in quotes))

    def test_selection_link_rejects_lookalike_hosts_generic_paths_and_invalid_ids(self):
        for url in (
            SELECTION_URL.replace("https://", "http://"),
            SELECTION_URL.replace("account.sportsbook.fanduel.com", "account.sportsbook.fanduel.com.evil.invalid"),
            SELECTION_URL.replace("account.sportsbook.fanduel.com", "evil.invalid@account.sportsbook.fanduel.com"),
            SELECTION_URL.replace("account.sportsbook.fanduel.com", "account.sportsbook.fanduel.com@evil.invalid"),
            SELECTION_URL.replace("account.sportsbook.fanduel.com", "account.sportsbook.fanduel.com:444"),
            SELECTION_URL.replace("/sportsbook/addToBetslip", "/navigation/pga"),
            SELECTION_URL.replace("marketId=42.599903063", "marketId="),
            SELECTION_URL.replace("marketId=42.599903063", "marketId=not-a-market"),
            SELECTION_URL.replace("selectionId=14753599", "selectionId=-1"),
            SELECTION_URL.replace("selectionId=14753599", "selectionId="),
            SELECTION_URL + "&marketId=42.599903064", SELECTION_URL + "&selectionId=14753599",
            "\n" + SELECTION_URL, SELECTION_URL + "#ignored", "https://[malformed",
        ):
            with self.subTest(url=url):
                quote = payload_inventory({"url": url, "oddsValue": "+125"}, odds=True)["quote_observations"][0]
                self.assertNotIn("fanduel_selection_link", quote)

    def test_selection_link_preserves_conflicting_book_and_identifier_evidence(self):
        for fields, expected in (
            ({"optionId": "42.111"}, "market_id_mismatch"),
            ({"marketId": "42.111"}, "market_id_mismatch"),
            ({"marketId": None}, "market_id_mismatch"),
            ({"selectionId": "222"}, "selection_id_mismatch"),
            ({"book": "DraftKings"}, "conflicting_book_labels"),
            ({"book": "FanDuel", "sportsbook": "Pinnacle"}, "conflicting_book_labels"),
        ):
            with self.subTest(fields=fields):
                value = {"url": SELECTION_URL, "oddsValue": "+125", **fields}
                collector = self.make_collector(responses=[(200, {}, json_bytes(value))])
                collector.fetch("pga_rest", "/odds/test", odds=True)
                row = self.records()[-1]
                quote = row["quote_observations"][0]
                self.assertEqual(quote["fanduel_selection_link"]["status"], expected)
                self.assertEqual(collector.fanduel_selection_link_price_fields, 0)
                if expected == "conflicting_book_labels":
                    self.assertEqual(collector.fanduel_price_fields, 0)
                    self.assertTrue(quote["book_labels"])

    def test_book_label_and_selection_link_counts_can_overlap_without_relabeling(self):
        value = {"book": "FanDuel", "url": SELECTION_URL, "oddsValue": "+125", "optionId": "42.599903063"}
        collector = self.make_collector({"pga_pages": [PAGE], "espn_state": False}, [(200, {}, html(value))])
        summary = collector.run()
        self.assertEqual(summary["explicitly_fanduel_price_field_observations"], 1)
        self.assertEqual(summary["fanduel_selection_link_price_field_observations"], 1)
        self.assertEqual(summary["price_field_observations"], 1)
        quote = next(r for r in self.records() if r["kind"] == "response")["quote_observations"][0]
        self.assertEqual(quote["book_labels"], ["FanDuel"])

    def test_sentinels_and_ambiguous_format_never_count_as_quotes(self):
        inventory = payload_inventory({"book": "FanDuel", "odds": -1,
                                       "decimalOdds": 0.5, "americanOdds": 2,
                                       "other": {"oddsValue": -1}}, odds=True)
        self.assertEqual(inventory["quote_observations"], [])
        self.assertEqual(len(inventory["unvalidated_price_fields"]), 4)
        inventory = payload_inventory({"odds": 2.0, "oddsValue": 2.5}, odds=True)
        self.assertEqual(inventory["quote_status"], "no_quotes")

    def test_request_timeout_is_clamped_to_remaining_budget(self):
        collector = self.make_collector({"max_seconds": 1, "timeout_seconds": 30})
        collector.run()
        self.assertEqual(self.calls[0]["timeout"], 1)

    def test_response_overrunning_budget_is_saved_then_reports_elapsed_cap(self):
        collector = self.make_collector({"max_seconds": 1})
        self.time.tick = 0.9
        summary = collector.run()
        self.assertEqual(summary["stop_reason"], "elapsed_time_cap")
        self.assertAlmostEqual(self.calls[0]["timeout"], 0.1)
        self.assertTrue(any(row["kind"] == "response" for row in self.records()))

    def test_absent_source_clocks_stay_absent(self):
        self.assertEqual(payload_inventory({"players": []})["source_clocks"], [])

    def test_compressed_raw_saved_before_decode(self):
        inner = {"lastUpdated": "2026-09-14T01:00:00Z", "players": [{"id": "123", "oddsValue": "+200"}]}
        raw = json_bytes({"data": {"oddsToWinCompressed": {"payload": base64.b64encode(gzip.compress(json_bytes(inner))).decode()}}})
        collector = self.make_collector(responses=[(200, {}, raw)])
        result = collector.graphql("oddsToWinCompressed", {"tournamentId": "R2026557"}, {}, odds=True)
        self.assertEqual(result["data"]["oddsToWinCompressed"]["payload"], inner)
        row = next(x for x in self.records() if x["kind"] == "response")
        self.assertEqual((self.output / row["response"]["file"]).read_bytes(), raw)
        self.assertEqual(row["quote_observations"][0]["value"], "+200")
        self.assertNotIn("DO-NOT-LOG-THIS-KEY", (self.output / row["request"]["file"]).read_text())
        self.assertEqual(self.calls[0]["headers"]["x-api-key"], "DO-NOT-LOG-THIS-KEY")

    def test_malformed_compression_retained_and_source_stops(self):
        raw = b'{"data":{"leaderboardCompressedV3":{"payload":"broken"}}}'
        collector = self.make_collector(responses=[(200, {}, raw)])
        self.assertIsNone(collector.graphql("LeaderboardCompressedV3", {}, {}))
        self.assertIsNone(collector.graphql("TeeTimesCompressedV2", {}, {}))
        self.assertEqual(len(self.calls), 1)
        row = next(x for x in self.records() if x["kind"] == "response")
        self.assertEqual((self.output / row["response"]["file"]).read_bytes(), raw)
        self.assertEqual(row["error"], "invalid_json_or_compressed_payload")

    def test_http_denial_disables_source_for_all_cycles_but_espn_continues(self):
        collector = self.make_collector({"pga_pages": [PAGE], "cycles": 2}, [
            (403, {}, b"denied"), (200, {}, b'{"events":[]}'), (200, {}, b'{"events":[]}')])
        summary = collector.run()
        self.assertEqual(len([x for x in self.calls if "pgatour.com" in x["url"]]), 1)
        self.assertEqual(len([x for x in self.calls if "espn.com" in x["url"]]), 2)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["disabled_sources"], {"pga_html": "http_403"})

    def test_429_backoff_recorded_no_retry_on_new_cycle(self):
        collector = self.make_collector({"cycles": 2}, [(429, {"Retry-After": "3600"}, b"slow down")])
        summary = collector.run()
        self.assertEqual(len(self.calls), 1)
        disabled = next(x for x in self.records() if x["kind"] == "source_disabled")
        self.assertEqual(disabled["retry_not_before"], "2026-09-14T01:00:00.250000+00:00")
        self.assertEqual(summary["disabled_sources"], {"espn": "http_429"})

    def test_redirect_is_a_terminal_source_failure(self):
        collector = self.make_collector(responses=[(302, {"Location": "https://elsewhere.invalid"}, b"")])
        collector.fetch("espn", "/scoreboard")
        collector.fetch("espn", "/scoreboard")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(collector.disabled_sources["espn"], "http_302")

    def test_request_cap_applies_across_cycles_and_default_api_is_off(self):
        collector = self.make_collector({"cycles": 4, "max_requests": 2})
        summary = collector.run()
        self.assertEqual(summary["stop_reason"], "request_cap")
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all("espn.com" in x["url"] for x in self.calls))

    def test_elapsed_cap_stops_before_a_sleep_or_request_exceeds_allowance(self):
        collector = self.make_collector({"cycles": 3, "max_seconds": 10})
        summary = collector.run()
        self.assertEqual(summary["stop_reason"], "elapsed_time_cap")
        self.assertEqual(len(self.calls), 1)
        self.assertLess(self.time.tick, 10)

    def test_request_starts_obey_minimum_interval(self):
        collector = self.make_collector({"request_interval_seconds": 3})
        collector.fetch("espn", "/one")
        collector.fetch("espn", "/two")
        collector.fetch("espn", "/three")
        self.assertEqual([x["tick"] for x in self.calls], [0, 3, 6])

    def test_append_only_across_runs_and_no_body_overwrite(self):
        first = self.make_collector()
        first.run()
        previous = (self.output / "index.jsonl").read_bytes()
        before = {p: p.read_bytes() for p in (self.output / first.run_id).rglob("*") if p.is_file()}
        second = self.make_collector()
        second.run()
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertTrue((self.output / "index.jsonl").read_bytes().startswith(previous))
        self.assertTrue(all(path.read_bytes() == raw for path, raw in before.items()))
        with self.assertRaises(FileExistsError):
            first.save("000001.body", b"overwrite")

    def test_graphql_schema_error_disables_operation_only(self):
        collector = self.make_collector(responses=[(200, {}, b'{"errors":[{"message":"Unknown field"}]}'),
                                                   (200, {}, b'{"data":{"field":{"players":[]}}}')])
        collector.graphql("Weather", {}, {})
        collector.graphql("Weather", {}, {})
        collector.graphql("Field", {}, {})
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn("pga_graphql", collector.disabled_sources)
        self.assertIn("Weather", collector.disabled_operations)

    def test_graphql_unauthorized_disables_host(self):
        collector = self.make_collector(responses=[(200, {}, b'{"errors":[{"message":"Unauthorized"}]}')])
        collector.graphql("Weather", {}, {})
        collector.graphql("Field", {}, {})
        self.assertEqual(len(self.calls), 1)
        self.assertIn("pga_graphql", collector.disabled_sources)

    def test_network_exception_does_not_log_credentials(self):
        collector = self.make_collector(responses=[URLError("DO-NOT-LOG-THIS-KEY")])
        collector.run()
        self.assertNotIn("DO-NOT-LOG-THIS-KEY", (self.output / "index.jsonl").read_text())

    def test_invalid_limits_and_arbitrary_urls_rejected_before_output(self):
        for config in ({"cycles": 0}, {"max_requests": 5001}, {"interval_seconds": 59},
                       {"request_interval_seconds": 0}, {"max_seconds": float("inf")},
                       {"max_seconds": float("nan")}, {"max_players_per_tournament": 201},
                       {"api_enabled": "yes"}, {"pga_pages": ["https://example.com/private"]},
                       {"pga_pages": [PAGE + "?apiKey=secret"]}, {"tournament_ids": ["../../bad"]}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.make_collector(config)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_player_inventory_accepts_field_leaderboard_and_site_status_ids(self):
        value = {"field": {"players": [{"id": "200"}, {"id": "100"}]},
                 "board": {"players": [{"player": {"id": "200"}}, {"player": {"id": "300"}}]},
                 "status": {"players": [{"playerId": "400"}, {"playerId": None}]}}
        self.assertEqual(player_ids(value), ["100", "200", "300", "400"])

    def test_retry_after_http_date_and_invalid_value(self):
        self.assertEqual(retry_not_before({"retry-after": "Mon, 14 Sep 2026 12:00:00 GMT"}, self.time.now()),
                         "2026-09-14T12:00:00+00:00")
        self.assertIsNone(retry_not_before({"retry-after": "not a date"}, self.time.now()))
        self.assertIsNone(retry_not_before({"retry-after": "1e200"}, self.time.now()))

    def test_empty_market_catalog_does_not_fan_out_to_players(self):
        responses = [(200, {}, b'{}'), (200, {}, b'{"availableMarkets":[]}')]
        responses += [(200, {}, b'{"data":{"field":{"players":[{"id":"100"},{"id":"200"}]}}}')] * 6
        collector = self.make_collector({"api_enabled": True, "espn_state": False,
                                         "tournament_ids": ["R2026557"]}, responses)
        summary = collector.run()
        self.assertEqual(summary["requests"], 8)
        self.assertFalse(any("/player/" in x["url"] for x in self.calls))
        inventory = next(x for x in self.records() if x["kind"] == "player_odds_inventory")
        self.assertEqual(inventory["reason"], "no_available_markets")

    def test_available_catalog_player_fanout_is_capped_and_omissions_recorded(self):
        responses = [(200, {}, b'{}'), (200, {}, b'{"availableMarkets":[{"id":"3ball","book":"FanDuel"}]}')]
        responses += [(200, {}, b'{"data":{"field":{"players":[{"id":"100"},{"id":"200"},{"id":"300"}]}}}')] * 6
        responses += [(200, {}, b'{"playerMarkets":[{"book":"FanDuel","oddsValue":"+200"}]}')] * 2
        collector = self.make_collector({"api_enabled": True, "espn_state": False,
                                         "tournament_ids": ["R2026557"],
                                         "max_players_per_tournament": 2}, responses)
        summary = collector.run()
        self.assertEqual(summary["requests"], 10)
        self.assertEqual(len([x for x in self.calls if "/player/" in x["url"]]), 2)
        inventory = next(x for x in self.records() if x["kind"] == "player_odds_inventory")
        self.assertEqual(inventory["omitted_by_cap"], ["300"])
        self.assertEqual(summary["explicitly_fanduel_price_field_observations"], 2)


if __name__ == "__main__":
    unittest.main()
