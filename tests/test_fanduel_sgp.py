import unittest

from beating import fanduel_sgp as fd


def runner(sid, name, handicap, decimal):
    return {"selectionId": sid, "name": name, "handicap": handicap, "decimal": decimal, "american": None}


MARKETS = [
    {"marketId": "734.1", "type": "PLAYER_X_RUSHING_YARDS_MEDIUM", "name": "MarShawn Lloyd - Rushing Yds", "sgm": True,
     "runners": [runner(1, "MarShawn Lloyd Over", 27.5, 1.877), runner(2, "MarShawn Lloyd Under", 27.5, 1.877)]},
    {"marketId": "734.2", "type": "PLAYER_X_ALT_RUSHING_YARDS_MEDIUM", "name": "MarShawn Lloyd - Alt Rushing Yds", "sgm": True,
     "runners": [runner(3, "MarShawn Lloyd 10+ Yards", 0.0, 1.14), runner(4, "MarShawn Lloyd 15+ Yards", 0.0, 1.29)]},
    {"marketId": "734.3", "type": "PLAYER_X_RUSHING_+_RECEIVING_YDS", "name": "MarShawn Lloyd - Rush + Rec Yds", "sgm": True,
     "runners": [runner(5, "MarShawn Lloyd Over", 49.5, 1.9), runner(6, "MarShawn Lloyd Under", 49.5, 1.9)]},
    {"marketId": "734.4", "type": "TOTAL_POINTS_(OVER/UNDER)", "name": "Total Points", "sgm": True, "runners": [runner(7, "Over", 45.5, 1.91), runner(8, "Under", 45.5, 1.91)]},
    {"marketId": "734.5", "type": "ALTERNATE_TOTAL", "name": "Alternate Total Points", "sgm": True,
     "runners": [runner(9, "Over (40.5)", 0.0, 1.5), runner(10, "Under (40.5)", 0.0, 2.6), runner(11, "Over (50.5)", 0.0, 2.7)]},
    {"marketId": "734.6", "type": "HOME_TEAM_TOTAL_POINTS", "name": "GB Packers Total Points", "sgm": True, "runners": [runner(12, "Over", 22.5, 1.87), runner(13, "Under", 22.5, 1.9)]},
    {"marketId": "734.7", "type": "MONEY_LINE", "name": "Moneyline", "sgm": True, "runners": [runner(14, "Chicago Bears", 0.0, 1.82), runner(15, "Green Bay Packers", 0.0, 2.04)]},
    {"marketId": "734.8", "type": "MATCH_HANDICAP_(2-WAY)", "name": "Spread", "sgm": True, "runners": [runner(16, "Chicago Bears", -1.5, 1.91), runner(17, "Green Bay Packers", 1.5, 1.91)]},
    {"marketId": "734.9", "type": "FIRST_HALF_TOTAL", "name": "1st Half Total", "sgm": True, "runners": [runner(18, "Over", 22.5, 1.83), runner(19, "Under", 22.5, 2.0)]},
    {"marketId": "734.10", "type": "OVER_UNDER_25", "name": "Over/Under 2.5 Goals", "sgm": True, "runners": [runner(20, "Over 2.5 Goals", 0.0, 1.53), runner(21, "Under 2.5 Goals", 0.0, 2.52)]},
]
EVENT = {"home": "Green Bay Packers", "away": "Chicago Bears"}


class TwoWayTests(unittest.TestCase):
    def atoms(self):
        return {(a["var"], a["line"], a["player"]): a for a in fd.two_way_markets(MARKETS, EVENT)}

    def test_player_stats_map_to_space_variables(self):
        atoms = self.atoms()
        self.assertEqual(atoms[("R", 27.5, "MarShawn Lloyd")]["over"]["selectionId"], 1)
        self.assertEqual(atoms[("R", 27.5, "MarShawn Lloyd")]["under"]["selectionId"], 2)
        self.assertEqual(atoms[("S", 49.5, "MarShawn Lloyd")]["over"]["selectionId"], 5)
        self.assertNotIn(("R", 0.0, "MarShawn Lloyd"), atoms)  # one-sided ladders are not two-way

    def test_team_markets_and_alternates(self):
        atoms = self.atoms()
        self.assertEqual(atoms[("total", 45.5, None)]["under"]["selectionId"], 8)
        self.assertEqual(atoms[("total", 40.5, None)]["over"]["selectionId"], 9)
        self.assertNotIn(("total", 50.5, None), atoms)  # no Under (50.5) runner
        self.assertEqual(atoms[("team_H", 22.5, None)]["over"]["selectionId"], 12)
        self.assertEqual(atoms[("result", None, None)]["over"]["selectionId"], 15)  # over = home wins
        self.assertEqual(atoms[("margin_H", -1.5, None)]["over"]["selectionId"], 17)  # home +1.5 covers <=> margin_H >= -1.5
        self.assertNotIn(("total", 22.5, None), atoms)  # period markets are skipped
        self.assertEqual(atoms[("total", 2.5, None)]["under"]["selectionId"], 21)  # soccer goal totals carry the line in the runner name


class ImplyTests(unittest.TestCase):
    RESP = {"betCombinations": [
        {"betType": "SINGLE", "isSGM": False, "numLines": 1, "winAvgOdds": {"americanDisplayOdds": {"americanOdds": -104}, "trueOdds": {"decimalOdds": {"decimalOdds": 1.96}}}},
        {"betType": "DOUBLE", "isSGM": True, "numLines": 1, "betMaxPayout": 1000000, "winAvgOdds": {"americanDisplayOdds": {"americanOdds": 515}, "trueOdds": {"decimalOdds": {"decimalOdds": 6.15}}}},
    ], "betFailures": [], "winRunnerOdds": [], "wallets": []}

    def test_sgp_combination_is_the_isSGM_entry(self):
        q = fd.parse_imply(self.RESP, 2)
        self.assertEqual(q["status"], "quoted")
        self.assertAlmostEqual(q["decimal"], 6.15)
        self.assertEqual(q["american"], 515)
        self.assertEqual(q["betType"], "DOUBLE")

    def test_refusal_carries_failure_codes(self):
        resp = {"betCombinations": [self.RESP["betCombinations"][0]], "betFailures": [{"failureCode": "IMPOSSIBLE_SAME_PLAYER_UNDER_COMBINATION", "failedRunner": {"selectionId": 2}, "combinationGroups": [1]}]}
        q = fd.parse_imply(resp, 2)
        self.assertEqual(q["status"], "refused")
        self.assertEqual(q["failures"][0]["code"], "IMPOSSIBLE_SAME_PLAYER_UNDER_COMBINATION")
        self.assertIsNone(q["decimal"])

    def test_american_fallback_when_decimal_missing(self):
        resp = {"betCombinations": [{"isSGM": True, "winAvgOdds": {"americanDisplayOdds": {"americanOdds": -150}}}]}
        self.assertAlmostEqual(fd.parse_imply(resp, 2)["decimal"], 1 + 100 / 150)

    def test_legs_payload_shape(self):
        legs = fd.legs_for([{"marketId": "734.1", "selectionId": 1}, {"marketId": "734.4", "selectionId": 8}])
        self.assertEqual(legs[1], {"legType": "SIMPLE_SELECTION", "betRunners": [{"runner": {"marketId": "734.4", "selectionId": 8}}]})


if __name__ == "__main__":
    unittest.main()
