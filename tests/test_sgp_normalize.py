"""Synthetic provider snapshots only; these fixtures are not betting evidence."""
import copy
from datetime import datetime
import unittest

from beating.sgp.normalize import normalize_snapshots


CAPTURED = "2026-10-09T21:00:01Z"
MAPPING = {
    "Player Rushing Yards": {"stat": "R"},
    "Player Receiving Yards": {"stat": "C"},
    "Player Rushing + Receiving Yards": {"stat": "S"},
    "Player Receiving Yards Milestones": {"stat": "C", "side": "at_least"},
}


def odd(**changes):
    value = {
        "id": "odd-r", "sportsbook": "theScore", "market": "Player Rushing Yards",
        "market_id": "player_rushing_yards", "player_id": "player-1",
        "selection": "Example Player", "selection_line": "under", "points": 49.5,
        "price": -110, "timestamp": 1791579600,
        "name": "Example Player Under 49.5", "is_main": True,
    }
    value.update(changes)
    return value


def snapshot(odds=None, **changes):
    fixture = {
        "id": "event-1", "start_date": "2026-10-11T17:00:00Z",
        "status": "unplayed", "league": {"id": "nfl"},
        "odds": [odd()] if odds is None else odds,
    }
    fixture.update(changes)
    return {"data": [fixture]}


def normalize(snapshots, **changes):
    args = {"market_map": MAPPING, "region": "ON", "settlement": "including_overtime",
            "captured_at": CAPTURED}
    args.update(changes)
    return normalize_snapshots(snapshots, **args)


class NormalizeTests(unittest.TestCase):
    def test_exact_inventory_preserves_ids_lines_source_and_receipt_clocks(self):
        data = normalize([snapshot([odd(), odd(id="fd-r", sportsbook="FanDuel")])])
        board = data["boards"][0]
        self.assertEqual(board["event_id"], "event-1")
        self.assertEqual(set(board["books"]), {"thescore", "fanduel"})
        book = board["books"]["thescore"]
        self.assertEqual(book["captured_at"], CAPTURED)
        leg = book["legs"][0]
        self.assertEqual(leg["selection_id"], "odd-r")
        self.assertEqual(leg["market_id"], "player_rushing_yards")
        self.assertEqual((leg["stat"], leg["side"], leg["line"]), ("R", "under", 49.5))
        self.assertEqual(datetime.fromisoformat(leg["source_at"]).timestamp(), 1791579600)
        self.assertNotEqual(leg["source_at"], book["captured_at"])
        self.assertEqual(leg["single_price"], -110)
        self.assertEqual(leg["provider"]["name"], "Example Player Under 49.5")
        self.assertEqual(data["coverage"]["accepted_legs"], 2)

    def test_milestones_require_explicit_side_mapping_and_keep_redundant_ids(self):
        milestone = odd(id="c20", market="Player Receiving Yards Milestones",
                        market_id="receiving_milestone", selection_line=None, points=20)
        data = normalize([snapshot([milestone, dict(milestone, id="c40", points=40)])])
        legs = data["boards"][0]["books"]["thescore"]["legs"]
        self.assertEqual([(l["selection_id"], l["side"], l["line"]) for l in legs],
                         [("c20", "at_least", 20), ("c40", "at_least", 40)])
        bad = normalize([snapshot([odd(selection_line="at_least", name="Example Player 40+")])])
        self.assertEqual(bad["boards"], [])
        self.assertEqual(bad["coverage"]["skipped"]["unsupported_side"], 1)

    def test_no_fuzzy_market_book_or_side_matching(self):
        result = normalize([snapshot([
            odd(id="a", market="Player Rushing Yards Alternate"),
            odd(id="b", sportsbook="thescore"),
            odd(id="c", selection_line="Under"),
        ])])
        self.assertEqual(result["boards"], [])
        self.assertEqual(result["coverage"]["skipped"], {
            "unmapped_market": 1, "unsupported_side": 1, "unsupported_sportsbook": 1,
        })
        self.assertEqual(result["coverage"]["unsupported_markets"], {"Player Rushing Yards Alternate": 1})

    def test_missing_fanduel_is_explicit_coverage_gap(self):
        result = normalize([snapshot()])
        self.assertEqual(len(result["boards"]), 1)
        gap = next(g for g in result["coverage"]["missing_markets"] if g["book"] == "fanduel")
        self.assertEqual(gap["stats"], ["C", "R", "S"])

    def test_repeated_identical_response_is_deduplicated_not_repriced(self):
        result = normalize([snapshot(), snapshot()])
        self.assertEqual(result["coverage"]["accepted_legs"], 1)
        self.assertEqual(result["coverage"]["skipped"]["duplicate_identical_selection"], 1)

    def test_chunk_receipt_is_preserved_without_restamping_with_batch_end(self):
        first = snapshot()
        first["collection"] = {"complete": True, "received_at": "2026-10-09T20:59:50Z"}
        second = snapshot([odd(id="second")])
        second["collection"] = {"complete": True, "received_at": "2026-10-09T20:59:59Z"}
        data = normalize([second, first])
        self.assertEqual(data["boards"][0]["books"]["thescore"]["captured_at"],
                         "2026-10-09T20:59:50Z")
        self.assertEqual(data["captured_at"], CAPTURED)

    def test_partial_or_unclocked_collection_is_not_a_complete_snapshot(self):
        for collection in ({"complete": False, "received_at": CAPTURED},
                           {"complete": True}, None):
            value = snapshot()
            value["collection"] = collection
            self.assertEqual(normalize([value])["boards"], [])

    def test_conflicting_duplicate_is_quarantined_regardless_of_order(self):
        for changed in (odd(price=-120), odd(points=50.5), odd(player_id="different-player"),
                        odd(market_id="different-market"), odd(timestamp=1791579601)):
            for rows in ([odd(), changed], [changed, odd()]):
                with self.subTest(rows=rows):
                    result = normalize([snapshot(rows)])
                    self.assertEqual(result["boards"], [])
                    self.assertEqual(result["coverage"]["quarantined_legs"], 1)

    def test_fixture_or_player_identity_conflicts_quarantine_existing_rows(self):
        result = normalize([snapshot(), snapshot(start_date="2026-10-12T17:00:00Z")])
        self.assertEqual(result["boards"], [])
        self.assertEqual(result["coverage"]["skipped"]["conflicting_fixture_identity"], 1)
        result = normalize([snapshot([odd(), odd(id="second", selection="Different Name")])])
        self.assertEqual(result["boards"], [])
        self.assertEqual(result["coverage"]["skipped"]["conflicting_player_identity"], 1)

    def test_bad_or_suspended_update_invalidates_previous_selection(self):
        for changed in (odd(is_suspended=True), odd(points=None), odd(timestamp=None),
                        odd(player_id=None), odd(selection_line=None)):
            with self.subTest(changed=changed):
                result = normalize([snapshot(), snapshot([changed])])
                self.assertEqual(result["boards"], [])

    def test_unknown_and_nonpregame_statuses_fail_closed(self):
        for status in (None, "live", "completed", "unknown", []):
            result = normalize([snapshot(), snapshot(status=status)])
            self.assertEqual(result["boards"], [])
            self.assertIn("not_confirmed_pregame", result["coverage"]["skipped"])

    def test_malformed_numbers_ids_and_times_never_invent_defaults(self):
        for changes in ({"points": "49.5"}, {"price": 1.91}, {"points": True},
                        {"price": float("nan")}, {"timestamp": "2026-10-09T21:00:00"},
                        {"id": None}, {"market_id": None}, {"player_id": ""},
                        {"selection_line": []}, {"market": []}, {"sportsbook": []}):
            with self.subTest(changes=changes):
                self.assertEqual(normalize([snapshot([odd(**changes)])])["boards"], [])

    def test_ncaaf_is_supported_without_inventing_combined_markets(self):
        result = normalize([snapshot(league={"id": "ncaaf"})])
        self.assertEqual(result["boards"][0]["league"], "ncaaf")
        self.assertEqual(result["coverage"]["missing_markets"][0]["stats"], ["C", "S"])

    def test_input_is_not_modified_and_empty_response_is_auditable(self):
        original = [snapshot()]
        saved = copy.deepcopy(original)
        normalize(original)
        self.assertEqual(original, saved)
        empty = normalize([{"data": []}, {"error": "denied"}])
        self.assertEqual(empty["boards"], [])
        self.assertEqual(empty["coverage"]["skipped"], {"malformed_snapshot": 1})

    def test_invalid_configuration_raises_before_processing(self):
        for changes in ({"region": ""}, {"settlement": ""}, {"captured_at": "2026-10-09"},
                        {"market_map": {"Wrong": {"stat": "YARDS"}}},
                        {"market_map": {"Wrong": {"stat": []}}},
                        {"market_map": {"Wrong": {"stat": "R", "line": 10}}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                normalize([], **changes)


if __name__ == "__main__":
    unittest.main()
