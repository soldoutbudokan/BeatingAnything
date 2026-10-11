"""Collection safety checks using synthetic inventories and no network calls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from beating.sgp.models import book_revision, quote_request, validate_request
from beating.sgp.pipeline import CaptureProvider, Runner, plan
from beating.sgp.store import QuoteStore


NOW = "2026-10-09T21:00:00+00:00"
PRICES = {"OO": 128, "OU": 506, "UO": 521, "UU": 126}


def leg(book, stat, side, line, suffix=""):
    market = f"{book}-{stat}{suffix}"
    return {"selection_id": f"{market}-{side}-{line}", "market_id": market,
            "stat": stat, "side": side, "line": line,
            "provider": {"fixture_id": "fixture", "market": market,
                         "name": f"Example Player {side} {line}"},
            "source_at": NOW, "single_price": -110}


def manifest(mode="live"):
    board = {"event_id": "event", "player_id": "player", "player_name": "Example Player",
             "league": "nfl", "region": "CA-ON", "settlement": "full-game-including-ot",
             "starts_at": "2026-10-11T17:00:00+00:00", "books": {}}
    board["books"]["thescore"] = {"sportsbook": "theScore", "fixture_id": "fixture",
        "captured_at": NOW, "legs": [leg("tsb", "S", "at_least", 90),
        leg("tsb", "R", "under", 49.5), leg("tsb", "C", "over", 34.5),
        leg("tsb", "C", "at_least", 40, "-milestone")]}
    board["books"]["fanduel"] = {"sportsbook": "FanDuel", "fixture_id": "fixture",
        "captured_at": NOW, "legs": [leg("fd", stat, side, line)
            for stat, line in (("S", 89.5), ("R", 49.5)) for side in ("over", "under")]}
    return {"schema_version": 1, "mode": mode, "captured_at": NOW, "boards": [board]}


def cell_for(request):
    return "".join("O" if item["side"] == "over" else "U" for item in request["legs"])


class SyntheticCollector:
    """Complete, explicit source evidence; mutations model individual failures."""
    cache_token = "synthetic-v1"

    def __init__(self, mode="live", mutate=None):
        self.mode, self.mutate, self.calls = mode, mutate, []

    def collect(self, request, now):
        self.calls.append(request)
        result = {"status": "priced", "american": PRICES[cell_for(request)]
                  if request["book"] == "fanduel" else 1064,
                  "received_at": now, "source_at": now, "mode": self.mode,
                  "source": "synthetic-book-capture", "exact_legs_verified": True,
                  "confirmed": True, "region_verified": True, "freshness_verified": True,
                  "evidence": "synthetic-test-evidence"}
        if self.mutate:
            self.mutate(request, result)
        return result


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = QuoteStore(Path(self.temp.name) / "quotes.sqlite")
        self.addCleanup(self.store.close)

    def runner(self, collector=None, **options):
        collector = collector or SyntheticCollector()
        options = {"now": NOW, "mode": "live", **options}
        options.setdefault("clock", lambda: options["now"])
        return Runner(self.store, {"thescore": collector, "fanduel": collector}, **options)

    def request(self, data=None):
        board = (data or manifest())["boards"][0]
        return quote_request(board, "thescore", board["books"]["thescore"]["legs"], purpose="candidate")

    def test_exact_quote_keys_change_with_legs_order_scope_and_line(self):
        data = manifest()
        original = self.request(data)
        for field, replacement in (("region", "US-NJ"), ("settlement", "regulation-only"),
                                   ("event_id", "another-event"), ("player_id", "another-player")):
            changed = deepcopy(data)
            changed["boards"][0][field] = replacement
            with self.subTest(field=field):
                self.assertNotEqual(original["key"], self.request(changed)["key"])
        board = data["boards"][0]
        legs = board["books"]["thescore"]["legs"]
        for selection in (legs[:-1], list(reversed(legs))):
            self.assertNotEqual(original["key"], quote_request(board, "thescore", selection, purpose="candidate")["key"])
        self.assertNotEqual(original["key"], quote_request(board, "fanduel", legs, purpose="candidate")["key"])
        changed = deepcopy(data)
        changed["boards"][0]["books"]["thescore"]["legs"][1]["line"] = 54.5
        self.assertNotEqual(original["key"], self.request(changed)["key"])
        changed = deepcopy(original)
        changed["legs"][0]["line"] = 80
        with self.assertRaisesRegex(ValueError, "exact selections"):
            validate_request(changed)

    def test_clock_refresh_keeps_identity_but_inventory_change_invalidates(self):
        data = manifest()
        board = data["boards"][0]
        request = self.request(data)
        self.store.register(board, "thescore")
        attempt = self.store.begin(request, NOW)
        self.store.finish(attempt, {"status": "priced", "american": 1064, "received_at": NOW})
        self.assertIsNotNone(self.store.get(request, NOW, 30))
        changed = deepcopy(board)
        changed["books"]["thescore"]["captured_at"] = "2026-10-09T21:00:01+00:00"
        self.assertEqual(book_revision(board["books"]["thescore"]), book_revision(changed["books"]["thescore"]))
        self.assertFalse(self.store.register(changed, "thescore"))
        changed["books"]["thescore"]["legs"].pop()
        changed["books"]["thescore"]["captured_at"] = "2026-10-09T21:00:02+00:00"
        self.assertTrue(self.store.register(changed, "thescore"))
        self.assertIsNone(self.store.get(request, NOW, 30))

    def test_equal_instant_inventory_conflict_is_rejected_across_timezones(self):
        board = manifest()["boards"][0]
        self.store.register(board, "thescore")
        changed = deepcopy(board)
        changed["books"]["thescore"]["captured_at"] = "2026-10-09T17:00:00-04:00"
        changed["books"]["thescore"]["legs"].pop()
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.store.register(changed, "thescore")

    def test_restored_inventory_cannot_revive_price_from_before_suspension(self):
        data = manifest()
        board = data["boards"][0]
        request = self.request(data)
        self.store.register(board, "thescore")
        attempt = self.store.begin(request, NOW)
        self.store.finish(attempt, {"status": "priced", "american": 1064, "received_at": NOW})
        self.assertEqual(self.store.get(request, NOW, 30)["american"], 1064)

        unavailable = deepcopy(board)
        unavailable["books"]["thescore"]["legs"].pop()
        unavailable["books"]["thescore"]["captured_at"] = "2026-10-09T21:00:01+00:00"
        self.assertTrue(self.store.register(unavailable, "thescore"))
        self.assertIsNone(self.store.get(request, "2026-10-09T21:00:01+00:00", 30))

        restored = deepcopy(board)
        restored_at = "2026-10-09T21:00:02+00:00"
        restored["books"]["thescore"]["captured_at"] = restored_at
        self.assertTrue(self.store.register(restored, "thescore"))
        restored_request = quote_request(restored, "thescore", restored["books"]["thescore"]["legs"], purpose="candidate")
        self.assertEqual(request["key"], restored_request["key"])
        self.assertIsNone(self.store.get(restored_request, restored_at, 30))

        new_attempt = self.store.begin(restored_request, restored_at)
        self.store.finish(new_attempt, {"status": "priced", "american": 900, "received_at": restored_at})
        self.assertEqual(self.store.get(restored_request, restored_at, 30)["american"], 900)

    def test_suspended_manifest_selection_or_book_is_rejected(self):
        for level in ("book", "leg"):
            for field, value in (("status", "suspended"), ("is_active", False),
                                 ("is_suspended", True)):
                data = manifest()
                target = data["boards"][0]["books"]["thescore"]
                if level == "leg":
                    target = target["legs"][0]
                target[field] = value
                with self.subTest(level=level, field=field), self.assertRaises(ValueError):
                    plan(data)

    def test_late_success_cannot_replace_newer_suspension(self):
        data = manifest()
        request = self.request(data)
        self.store.register(data["boards"][0], "thescore")
        first = self.store.begin(request, NOW)
        later = self.store.begin(request, NOW)
        self.store.finish(later, {"status": "unavailable", "reason": "suspended", "received_at": NOW})
        self.store.finish(first, {"status": "priced", "american": 1064, "received_at": NOW})
        self.assertEqual(self.store.get(request, NOW, 30)["status"], "unavailable")
        pending = self.store.begin(request, NOW)
        self.assertIsNone(self.store.get(request, NOW, 30))
        self.store.finish(pending, {"status": "error", "received_at": NOW})
        self.assertEqual(self.store.get(request, NOW, 30)["status"], "error")

    def test_cache_rejects_future_or_expired_result(self):
        data = manifest()
        request = self.request(data)
        self.store.register(data["boards"][0], "thescore")
        attempt = self.store.begin(request, NOW)
        self.store.finish(attempt, {"status": "priced", "american": 1064, "received_at": NOW})
        self.assertIsNone(self.store.get(request, "2026-10-09T20:59:59+00:00", 30))
        self.assertIsNone(self.store.get(request, "2026-10-09T21:00:31+00:00", 30))
        self.assertIsNotNone(self.store.get(request, "2026-10-09T21:00:30+00:00", 30))

    def test_one_fd_partition_serves_all_candidate_variants_and_cache(self):
        work = plan(manifest())
        collector = SyntheticCollector()
        first = self.runner(collector).run(work)
        self.assertTrue(first["opportunities"])
        self.assertEqual(sum(r["book"] == "fanduel" for r in collector.calls), 4)
        self.assertEqual(first["stats"]["collection_calls"], len(work["requests"]))
        self.assertGreater(len(first["opportunities"]), first["stats"]["positive_underlying_events"])
        second = self.runner(collector).run(work)
        self.assertEqual(second["stats"]["cache_hits"], len(work["requests"]))
        self.assertEqual(len(collector.calls), len(work["requests"]))

    def test_incomplete_fd_inventory_never_collects_candidates(self):
        data = manifest()
        data["boards"][0]["books"]["fanduel"]["legs"].pop()
        work = plan(data)
        self.assertEqual(work["stats"]["reference_partitions"], 0)
        collector = SyntheticCollector()
        result = self.runner(collector).run(work)
        self.assertEqual(collector.calls, [])
        self.assertEqual(result["opportunities"], [])
        self.assertTrue(result["gaps"])

    def test_quote_budget_is_hard_limit_and_partial_scan_is_visible(self):
        collector = SyntheticCollector()
        result = self.runner(collector, max_quotes=4).run(plan(manifest()))
        self.assertEqual(len(collector.calls), 4)
        self.assertTrue(all(request["book"] == "fanduel" for request in collector.calls))
        self.assertEqual(result["opportunities"], [])
        self.assertGreater(result["stats"]["budget_skips"], 0)
        self.assertIn("quote_budget_exhausted", [gap.get("reason") for gap in result["gaps"]])

    def test_provider_error_does_not_escape_or_expose_exception_details(self):
        class BrokenCollector:
            def collect(self, request, now):
                raise RuntimeError("private-token-in-provider-url")

        result = self.runner(BrokenCollector()).run(plan(manifest()))
        self.assertEqual(result["opportunities"], [])
        self.assertEqual(result["stats"]["collection_calls"], 4)
        self.assertNotIn("private-token", json.dumps(result))
        self.assertEqual(result["gaps"][-1]["reasons"], ["RuntimeError"])

    def test_missing_or_incoherent_fd_quote_stops_candidate_collection(self):
        for failure in ("missing", "receipt_skew", "source_skew"):
            def mutate(request, result):
                if request["book"] == "fanduel" and cell_for(request) == "UU":
                    if failure == "missing":
                        result.update(status="unavailable", american=None, reason="suspended")
                    elif failure == "receipt_skew":
                        result["received_at"] = "2026-10-09T20:59:00+00:00"
                    else:
                        result["source_at"] = "2026-10-09T20:59:00+00:00"
            collector = SyntheticCollector(mutate=mutate)
            # Each scenario is a new collector evidence revision.
            collector.cache_token = failure
            with self.subTest(failure=failure):
                result = self.runner(collector).run(plan(manifest()))
                self.assertEqual(result["opportunities"], [])
                self.assertFalse(any(r["book"] == "thescore" for r in collector.calls))

    def test_historical_evidence_never_becomes_live_from_shared_cache(self):
        work = plan(manifest("historical"))
        historical = SyntheticCollector("historical")
        result = self.runner(historical, mode="historical").run(work)
        self.assertEqual(result["opportunities"], [])
        self.assertTrue(result["historical_opportunities"])
        collector = SyntheticCollector("historical")
        result = self.runner(collector).run(plan(manifest()))
        self.assertEqual(result["opportunities"], [])
        self.assertTrue(collector.calls)
        self.assertEqual(result["evaluations"], [])
        with self.assertRaisesRegex(ValueError, "mode mismatch"):
            self.runner().run(work)

    def test_stale_or_future_quote_never_qualifies(self):
        for field in ("received_at", "source_at"):
            for bad in ("2026-10-09T20:57:59+00:00", "2026-10-09T21:00:01+00:00"):
                collector = SyntheticCollector(mutate=lambda request, result: result.update({field: bad}))
                collector.cache_token = field + bad
                with self.subTest(field=field, value=bad):
                    result = self.runner(collector).run(plan(manifest()))
                    self.assertEqual(result["opportunities"], [])
                    self.assertEqual(result["evaluations"], [])

    def test_stale_or_future_inventory_does_not_trigger_collection(self):
        for index, bad in enumerate(("2026-10-09T20:57:59+00:00", "2026-10-09T21:00:01+00:00")):
            data = manifest()
            data["captured_at"] = bad
            for inventory in data["boards"][0]["books"].values():
                inventory["captured_at"] = bad
            collector = SyntheticCollector()
            with self.subTest(value=bad):
                # This test needs independent inventory clocks in the store.
                store = QuoteStore(Path(self.temp.name) / f"inventory-clock-{index}.sqlite")
                try:
                    result = Runner(store, {"thescore": collector, "fanduel": collector},
                                    now=NOW, mode="live", clock=lambda: NOW).run(plan(data))
                finally:
                    store.close()
                self.assertEqual(collector.calls, [])
                self.assertEqual(result["opportunities"], [])
                self.assertIn("stale_or_future_inventory", [gap.get("reason") for gap in result["gaps"]])

    def test_clock_advancing_during_scan_expires_old_fd_comparison(self):
        clock = [NOW]

        def mutate(request, result):
            if request["book"] == "thescore":
                clock[0] = "2026-10-09T21:02:01+00:00"
                result["received_at"] = result["source_at"] = clock[0]

        collector = SyntheticCollector(mutate=mutate)
        result = self.runner(collector, clock=lambda: clock[0]).run(plan(manifest()))
        self.assertEqual(result["opportunities"], [])
        self.assertIn("quote_expired_during_scan", [gap.get("reason") for gap in result["gaps"]])

    def test_cross_book_source_skew_rejects_otherwise_fresh_quotes(self):
        def mutate(request, result):
            if request["book"] == "thescore":
                result["source_at"] = "2026-10-09T20:59:00+00:00"

        result = self.runner(SyntheticCollector(mutate=mutate), comparison_skew=30).run(plan(manifest()))
        self.assertEqual(result["opportunities"], [])
        self.assertIn("cross_book_source_skew", [gap.get("reason") for gap in result["gaps"]])

    def test_missing_source_or_confirmation_never_actionable(self):
        for field in ("source_at", "confirmed", "region_verified", "freshness_verified", "evidence", "exact_legs_verified"):
            collector = SyntheticCollector(mutate=lambda request, result: result.pop(field, None))
            collector.cache_token = field
            with self.subTest(field=field):
                result = self.runner(collector).run(plan(manifest()))
                self.assertEqual(result["opportunities"], [])
                self.assertEqual(result["historical_opportunities"], [])

    def test_capture_newest_suspension_replaces_old_price(self):
        request = self.request()
        path = Path(self.temp.name) / "capture.json"
        priced = {"request": request, "received_at": NOW, "status": "priced", "american": 1064}
        suspended = {"request": request, "received_at": "2026-10-09T21:00:01+00:00", "status": "unavailable"}
        path.write_text(json.dumps({"mode": "historical", "observations": [suspended, priced]}))
        collector = CaptureProvider(path)
        self.assertEqual(collector.collect(request, NOW)["status"], "unavailable")

    def test_changed_capture_content_invalidates_recent_cached_price(self):
        data = manifest()
        request = self.request(data)
        self.store.register(data["boards"][0], "thescore")
        path = Path(self.temp.name) / "capture.json"
        result = SyntheticCollector().collect(request, NOW)
        path.write_text(json.dumps({"mode": "live", "observations": [{"request": request, **result}]}))
        first = self.runner(CaptureProvider(path)).quote(request)
        self.assertEqual(first["status"], "priced")
        result.update(status="unavailable", american=None, reason="suspended")
        path.write_text(json.dumps({"mode": "live", "observations": [{"request": request, **result}]}))
        second = self.runner(CaptureProvider(path)).quote(request)
        self.assertEqual(second["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
