import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from beating.golf_collect import payload_inventory
from tools.audit_golf_price_capture import (
    decimal_american, extract_drawers, pair_context, verified_bytes,
)


def fixture():
    def side(pid, selection, odds):
        return {"players": [{"playerId": pid, "displayName": f"Player {pid}"}],
                "oddsValue": odds, "optionId": "42.123", "entityId": pid,
                "url": "https://account.sportsbook.fanduel.com/sportsbook/addToBetslip"
                       f"?marketId=42.123&selectionId={selection}"}
    payload = {"playerMarkets": [{"marketType": "MATCHUP_PROPS", "bettingPeriod": 2,
        "oddsDataGroup": [{"title": "18 Hole Matchbet - Round 3", "groupId": "(Round 3) A vs B",
            "oddsData": [{"type": "GROUP", "groupCount": 2,
                          "group": [side("1", "11", "-125"), side("2", "12", "+105")]}]}]}]}
    record = {"context": {"cycle": 1, "tournament_id": "R2026001", "player_id": "1"},
              "source_url": "https://example.com/fixture", "response": {"file": "fixture.body"},
              "collector_request_started_at": "2026-09-19T12:00:00+00:00",
              "collector_response_received_at": "2026-09-19T12:00:01+00:00",
              **payload_inventory(payload, odds=True)}
    return payload, record


class GolfPriceCaptureTests(unittest.TestCase):
    def test_two_sides_in_one_response_and_exact_overround(self):
        selections, pairs, rejected = extract_drawers(*fixture())
        self.assertEqual((len(selections), len(pairs), len(rejected)), (2, 1, 0))
        self.assertAlmostEqual(pairs[0]["overround"], 1 / 1.8 + 1 / 2.05 - 1)

    def test_complementary_partial_drawers_do_not_form_a_pair(self):
        payload, record = fixture()
        other = copy.deepcopy(payload)
        payload["playerMarkets"][0]["oddsDataGroup"][0]["oddsData"][0]["group"].pop()
        other["playerMarkets"][0]["oddsDataGroup"][0]["oddsData"][0]["group"].pop(0)
        for partial in (payload, other):
            selections, pairs, rejected = extract_drawers(partial, {**record, **payload_inventory(partial, odds=True)})
            self.assertEqual((len(selections), len(pairs), len(rejected)), (1, 0, 1))

    def test_different_market_ids_reject_pair(self):
        payload, record = fixture()
        side = payload["playerMarkets"][0]["oddsDataGroup"][0]["oddsData"][0]["group"][1]
        side["optionId"] = "42.124"
        side["url"] = side["url"].replace("42.123", "42.124")
        self.assertEqual(len(extract_drawers(payload, {**record, **payload_inventory(payload, odds=True)})[1]), 0)

    def test_conflicting_book_label_not_overridden_by_link(self):
        payload, record = fixture()
        payload["playerMarkets"][0]["book"] = "Another Book"
        selections, pairs, rejected = extract_drawers(payload, {**record, **payload_inventory(payload, odds=True)})
        self.assertEqual((len(selections), len(pairs), len(rejected)), (0, 0, 1))

    def test_distinct_selections_for_same_player_are_not_a_matchup(self):
        payload, record = fixture()
        sides = payload["playerMarkets"][0]["oddsDataGroup"][0]["oddsData"][0]["group"]
        sides[1]["players"] = copy.deepcopy(sides[0]["players"])
        self.assertFalse(extract_drawers(payload, record)[1])

    def state(self, cycle=1):
        tees, leaderboard = {}, {}
        for pid, course, thru in (("1", "A", "5*"), ("2", "B", "3")):
            tees[("R2026001", cycle, 3, pid)] = [{"course_id": course, "group_number": int(pid),
                "tee_time": "2026-09-19T11:00:00+00:00", "state_received_at": "2026-09-19T11:59:00+00:00"}]
            leaderboard[("R2026001", cycle, pid)] = {"currentRound": 3, "thru": thru,
                "state_received_at": "2026-09-19T11:59:00+00:00"}
        return tees, leaderboard

    def test_title_period_conflict_and_started_back_nine_are_preserved(self):
        pair = extract_drawers(*fixture())[1][0]
        context = pair_context(pair, *self.state())
        self.assertTrue(context["raw_period_disagrees_with_title"])
        self.assertTrue(context["cross_course_under_title"])
        self.assertFalse(context["received_before_both_scheduled_starts"])
        self.assertTrue(context["both_have_completed_holes_in_state_capture"])
        self.assertEqual(pair["betting_period_raw"], 2)

    def test_later_cycle_sport_state_cannot_backfill_earlier_quote(self):
        pair = extract_drawers(*fixture())[1][0]
        context = pair_context(pair, *self.state(cycle=2))
        self.assertIsNone(context["cross_course_under_title"])
        self.assertIsNone(context["received_before_both_scheduled_starts"])
        self.assertFalse(context["both_have_completed_holes_in_state_capture"])

    def test_completed_back_nine_marker_is_recognized(self):
        pair = extract_drawers(*fixture())[1][0]
        tees, leaderboard = self.state()
        leaderboard[("R2026001", 1, "1")]["thru"] = "F*"
        leaderboard[("R2026001", 1, "2")]["thru"] = "F"
        self.assertTrue(pair_context(pair, tees, leaderboard)["both_have_completed_holes_in_state_capture"])

    def test_future_state_in_same_cycle_is_not_used(self):
        pair = extract_drawers(*fixture())[1][0]
        tees, leaderboard = self.state()
        for values in tees.values():
            values[0]["state_received_at"] = "2026-09-19T12:10:00+00:00"
        for state in leaderboard.values():
            state["state_received_at"] = "2026-09-19T12:10:00+00:00"
        context = pair_context(pair, tees, leaderboard)
        self.assertIsNone(context["received_before_both_scheduled_starts"])
        self.assertFalse(context["both_have_completed_holes_in_state_capture"])

    def test_later_round_holes_do_not_prove_an_earlier_quote_state(self):
        pair = extract_drawers(*fixture())[1][0]
        tees, leaderboard = self.state()
        for state in leaderboard.values():
            state["currentRound"] = 4
        self.assertFalse(pair_context(pair, tees, leaderboard)["both_have_completed_holes_in_state_capture"])

    def test_bytes_and_hash_both_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.body").write_bytes(b"original")
            artifact = {"file": "source.body", "bytes": 8,
                        "sha256": hashlib.sha256(b"original").hexdigest()}
            self.assertEqual(verified_bytes(root, artifact), b"original")
            (root / "source.body").write_bytes(b"changed!")
            with self.assertRaises(ValueError):
                verified_bytes(root, artifact)

    def test_american_conversion_rejects_unsigned_and_sentinel_prices(self):
        for value in ("125", "-99", "+0", True):
            with self.assertRaises(ValueError):
                decimal_american(value)


if __name__ == "__main__":
    unittest.main()
