"""Offline tests for the Proline+ (Kambi) SGP redundant-leg probe: leg normalisation, implication rules, construction
enumeration, exclusivity, odds arithmetic and Bet Builder response parsing. No network."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools import probe_proline_sgp_redundancy as P

TOR, BOS, AM, WN = "Toronto Maple Leafs", "Boston Bruins", "Auston Matthews", "William Nylander"
EV = {"id": 1, "homeName": TOR, "awayName": BOS, "start": "2026-10-24T23:00Z", "sport": "ICE_HOCKEY", "group": "NHL"}


def bo(id_, typ, crit, outcomes, **extra):
    return {"id": id_, "eventId": 1, "betOfferType": {"englishName": typ}, "criterion": {"englishLabel": crit}, "outcomes": outcomes, **extra}


def oc(id_, typ, odds, line=None, participant=None, status="OPEN"):
    o = {"id": id_, "type": typ, "odds": odds, "status": status}
    if line is not None:
        o["line"] = line
    if participant:
        o["participant"] = participant
    return o


BOARD = {"events": [EV], "betOffers": [
    bo(10, "Match", "Moneyline - Including Overtime", [oc(101, "OT_ONE", 1750), oc(102, "OT_TWO", 2100)]),
    bo(11, "Handicap", "Puck Line - Including Overtime", [oc(111, "OT_ONE", 2600, -1500), oc(112, "OT_TWO", 1500, 1500)]),
    bo(12, "Handicap", "Puck Line - Including Overtime", [oc(121, "OT_ONE", 1300, 1500), oc(122, "OT_TWO", 3300, -1500)]),
    bo(13, "Over/Under", "Total Goals - Including Overtime", [oc(131, "OT_OVER", 1900, 5500), oc(132, "OT_UNDER", 1900, 5500)]),
    bo(14, "Over/Under", "Total Goals - Including Overtime", [oc(141, "OT_OVER", 2600, 6500), oc(142, "OT_UNDER", 1450, 6500)]),
    bo(15, "Over/Under", f"Total Goals by {TOR} - Including Overtime", [oc(151, "OT_OVER", 1800, 2500, TOR), oc(152, "OT_UNDER", 1950, 2500, TOR)]),
    bo(16, "Over/Under", f"Total Goals by {BOS} - Including Overtime", [oc(161, "OT_OVER", 2700, 3500, BOS), oc(162, "OT_UNDER", 1400, 3500, BOS)]),
    bo(17, "Player Occurrence Line", "Shots on Goal by Player - Over/Under", [oc(171, "OT_OVER", 1850, 3500, AM), oc(172, "OT_UNDER", 1850, 3500, AM)]),
    bo(18, "Player Occurrence Line", "Shots on Goal by Player - Over/Under", [oc(181, "OT_OVER", 3000, 4500, AM), oc(182, "OT_UNDER", 1300, 4500, AM)]),
    bo(19, "Yes/No", "Anytime Goalscorer", [oc(191, "OT_YES", 2500, participant=AM), oc(192, "OT_NO", 1450, participant=AM)]),
    bo(20, "Player Occurrence Line", "Goals by Player - Over/Under", [oc(201, "OT_OVER", 7000, 1500, AM), oc(202, "OT_UNDER", 1080, 1500, AM)]),
    bo(21, "Yes/No", "To Score 2 or More Goals", [oc(211, "OT_YES", 7500, participant=AM), oc(212, "OT_NO", 1050, participant=AM)]),
    bo(22, "Player Occurrence Line", "Shots on Goal by Player - Over/Under", [oc(221, "OT_OVER", 1900, 2500, WN), oc(222, "OT_UNDER", 1900, 2500, WN, status="SUSPENDED")]),
    bo(23, "Over/Under", "Total Goals - Including Overtime", [oc(231, "OT_OVER", 1500, 4500), oc(232, "OT_UNDER", 2500, 4500)], suspended=True),
]}

NFL_EV = {"id": 2, "homeName": "Seattle Seahawks", "awayName": "San Francisco 49ers", "group": "NFL"}
CMC = "Christian McCaffrey"
NFL = {"events": [NFL_EV], "betOffers": [
    dict(bo(30, "Player Occurrence Line", "Rushing + Receiving Yards by Player - Over/Under", [oc(301, "OT_OVER", 2000, 89500, CMC)]), eventId=2),
    dict(bo(31, "Player Occurrence Line", "Rushing Yards by Player - Over/Under", [oc(311, "OT_UNDER", 1900, 54500, CMC)]), eventId=2),
    dict(bo(32, "Player Occurrence Line", "Receiving Yards by Player - Over/Under", [oc(321, "OT_OVER", 1850, 34500, CMC)]), eventId=2),
    dict(bo(33, "Player Occurrence Line", "Receiving Yards by Player - Over/Under", [oc(331, "OT_OVER", 2200, 39500, CMC)]), eventId=2),
]}


def legs(board):
    return {l["oid"]: l for l in P.board_legs(board)}


class Normalisation(unittest.TestCase):
    def test_stat_keys_merge_game_team_and_player_markets(self):
        L = legs(BOARD)
        self.assertEqual(L[131]["stat"], "goals")
        self.assertEqual(L[151]["stat"], "goals")
        self.assertEqual(L[201]["stat"], "goals")
        self.assertEqual(L[171]["stat"], "shots on goal")
        self.assertEqual((L[131]["subject"], L[151]["subject"], L[171]["subject"]), (P.GAME, TOR, AM))

    def test_match_handicap_and_yes_markets(self):
        L = legs(BOARD)
        self.assertEqual((L[101]["dir"], L[101]["subject"]), ("win", TOR))
        self.assertEqual((L[111]["dir"], L[111]["subject"], L[111]["line"]), ("cover", TOR, -1.5))
        self.assertEqual((L[122]["subject"], L[122]["line"]), (BOS, -1.5))
        self.assertEqual((L[191]["stat"], L[191]["dir"], L[191]["line"]), ("goals", "over", 0.5))
        self.assertEqual((L[211]["stat"], L[211]["line"]), ("goals", 1.5))
        self.assertAlmostEqual(L[101]["dec"], 1.75)

    def test_team_total_without_participant_field_is_not_a_game_total(self):
        board = {"events": [EV], "betOffers": [bo(40, "Over/Under", f"Total Goals by {BOS} - Including Overtime", [oc(401, "OT_OVER", 2000, 2500)]),
                                                bo(41, "Over/Under", "Total Goals - Including Overtime", [oc(411, "OT_OVER", 1900, 5500)])]}
        L = legs(board)
        self.assertEqual((L[401]["stat"], L[401]["subject"]), ("goals", BOS))
        self.assertIsNone(P.implied([L[411]], L[401]))   # game over 5.5 does not imply Boston over 2.5

    def test_suspended_offers_and_outcomes_are_dropped(self):
        L = legs(BOARD)
        self.assertNotIn(222, L)
        self.assertNotIn(231, L)
        self.assertIn(221, L)

    def test_combined_parts(self):
        self.assertEqual(P.combined_parts("rushing + receiving yards"), ["rushing yards", "receiving yards"])
        self.assertEqual(P.stat_key("Points and Rebounds by Player - Over/Under"), "points + rebounds")
        self.assertIsNone(P.combined_parts("points"))


class Implications(unittest.TestCase):
    def setUp(self):
        self.L = legs(BOARD)

    def imp(self, base, cand):
        return P.implied([self.L[b] for b in base], self.L[cand])

    def test_total_ladders(self):
        self.assertTrue(self.imp([141], 131))   # over 6.5 implies over 5.5
        self.assertIsNone(self.imp([131], 141))
        self.assertTrue(self.imp([132], 142))   # under 5.5 implies under 6.5
        self.assertIsNone(self.imp([142], 132))

    def test_spread_and_moneyline(self):
        self.assertTrue(self.imp([111], 101))   # -1.5 covers implies win
        self.assertTrue(self.imp([101], 121))   # win implies +1.5 covers
        self.assertTrue(self.imp([111], 121))   # -1.5 covers implies +1.5 covers
        self.assertIsNone(self.imp([121], 101))
        self.assertIsNone(self.imp([101], 111))
        self.assertIsNone(self.imp([111], 102))

    def test_player_ladders_and_yes_markets(self):
        self.assertTrue(self.imp([181], 171))   # 4.5 shots implies 3.5 shots
        self.assertIsNone(self.imp([171], 181))
        self.assertIsNone(self.imp([181], 221))  # different player
        self.assertIsNone(self.imp([181], 131))  # shots do not imply goals
        self.assertTrue(self.imp([201], 191))   # 2+ goals implies anytime
        self.assertTrue(self.imp([211], 191))
        self.assertIsNone(self.imp([191], 201))

    def test_team_totals_bound_game_total(self):
        self.assertIsNone(self.imp([161], 131))          # Boston over 3.5 alone does not reach 5.5
        self.assertTrue(self.imp([151, 161], 131))       # 3 + 4 = 7 > 5.5
        self.assertTrue(self.imp([151, 161], 141))       # 7 > 6.5
        self.assertIsNone(self.imp([151, 152], 131))     # same team twice is not two teams

    def test_combined_stat_rule_matches_the_score_pattern(self):
        L = legs(NFL)
        self.assertEqual(L[301]["stat"], "rushing + receiving yards")
        self.assertIn("force receiving yards >= 36", P.implied([L[301], L[311]], L[321]))
        self.assertIsNone(P.implied([L[301], L[311]], L[331]))   # 40+ is not implied
        self.assertIsNone(P.implied([L[301]], L[321]))
        self.assertIsNone(P.implied([L[311]], L[321]))


class Constructions(unittest.TestCase):
    def test_bases_get_a_consistent_unrelated_anchor(self):
        cons = P.constructions(P.board_legs(BOARD))
        by_added = {}
        for c in cons:
            by_added.setdefault((tuple(l["oid"] for l in c["base"][1:]), c["added"]["oid"]), c)
        c = by_added[((141,), 131)]
        self.assertEqual(c["base"][0]["oid"], 101)
        c = by_added[((111,), 101)]                      # Toronto -1.5 plus redundant Toronto ML
        self.assertNotEqual(c["base"][0]["oid"], 102)    # Boston ML would contradict the base
        self.assertNotEqual(c["base"][0]["oid"], 101)
        for c in cons:
            for i, a in enumerate(c["base"]):
                for b in c["base"][i + 1:]:
                    self.assertFalse(P.exclusive(a, b), (a["label"], b["label"]))
            self.assertTrue(P.implied(c["base"], c["added"]), c)

    def test_combined_rule_constructions_need_both_base_legs(self):
        cons = [c for c in P.constructions(P.board_legs(NFL)) if c["added"]["oid"] == 321]
        bases = sorted(sorted(l["oid"] for l in c["base"]) for c in cons)
        self.assertEqual(bases, [[301, 311], [331]])   # the combined rule, and the plain receiving ladder

    def test_exclusive(self):
        L = legs(BOARD)
        self.assertTrue(P.exclusive(L[101], L[102]))
        self.assertTrue(P.exclusive(L[111], L[122]))     # both teams -1.5
        self.assertTrue(P.exclusive(L[111], L[112]))     # same offer
        self.assertTrue(P.exclusive(L[102], L[111]))     # Boston win vs Toronto -1.5
        self.assertFalse(P.exclusive(L[102], L[121]))    # Boston win vs Toronto +1.5
        self.assertFalse(P.exclusive(L[121], L[112]))    # both +1.5
        self.assertTrue(P.exclusive(L[141], L[132]))     # over 6.5 vs under 5.5
        self.assertFalse(P.exclusive(L[131], L[142]))    # over 5.5 vs under 6.5


class OddsAndRecords(unittest.TestCase):
    def test_american_round_trip_and_change(self):
        self.assertEqual(P.american(P.parse_american("+483")), 483)
        self.assertEqual(P.american(1.75), -133)
        row = P.observation("record", "SF@SEA", ["a", "b", "c"], "d", "r", P.parse_american("+483"), P.parse_american("+854"))
        self.assertEqual((row["base_american"], row["with_american"], row["change_pct"]), ("+483", "+854", 63.64))
        self.assertIsNone(P.observation("price", "x", [], "d", "r", 5.83, None)["change_pct"])

    def test_find_odds(self):
        self.assertEqual(P.find_odds({"price": {"odds": 9540, "line": 5500}}), 9.54)
        self.assertEqual(P.find_odds({"result": [{"totalOdds": "9540"}]}), 9.54)
        self.assertEqual(P.find_odds({"decimalOdds": 9.54}), 9.54)
        self.assertIsNone(P.find_odds({"error": "not combinable"}))

    def test_record_and_report_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            old = P.OBS
            P.OBS = Path(d) / "obs.json"
            try:
                P.main(["record", "--event", "SF@SEA 2026-10-11", "--base", "x; y", "--added", "z", "--reason", "r",
                        "--base-odds", "+483", "--with-odds", "+854", "--note", "test"])
                saved = json.loads(P.OBS.read_text())["observations"]
                self.assertEqual(saved[0]["base"], ["x", "y"])
                self.assertEqual(saved[0]["change_pct"], 63.64)
                P.main(["report"])
            finally:
                P.OBS = old


if __name__ == "__main__":
    unittest.main()
