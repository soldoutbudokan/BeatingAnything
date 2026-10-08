import unittest

from beating.thescore import decimal_odds, devig_multiplicative, devig_power, ev, event_sides, implied_pairs, mentions, name_variants, threshold


def sel(sid, name, stype, price_num, price_den, points=None):
    return {"id": f"MarketSelection:{sid}", "rawId": sid, "status": "OPEN", "type": stype, "name": {"fullName": name},
            "points": {"decimalPoints": points} if points is not None else None, "odds": {"numeratorLong": str(price_num), "denominatorLong": str(price_den), "formattedOdds": "x"}}


def market(mid, name, mtype, selections):
    return {"id": f"Market:{mid}", "name": name, "type": mtype, "status": "OPEN", "selections": selections}


class OddsTests(unittest.TestCase):
    def test_decimal_odds_is_numerator_over_denominator(self):
        self.assertAlmostEqual(decimal_odds(sel("a", "x", "HOME_MONEYLINE", 13, 11)), 13 / 11)
        self.assertIsNone(decimal_odds({"odds": None}))

    def test_threshold_parses_plus_ladders(self):
        self.assertEqual(threshold(sel("a", "275+", "LIST", 2, 1)), 275.0)
        self.assertIsNone(threshold(sel("a", "Over", "OVER", 2, 1)))

    def test_devig_methods(self):
        probs, hold = devig_multiplicative([1.909, 1.909])
        self.assertAlmostEqual(sum(probs), 1.0)
        self.assertAlmostEqual(hold, 2 / 1.909)
        probs, k = devig_power([1.5, 3.0, 8.0])
        self.assertAlmostEqual(sum(probs), 1.0, places=6)
        self.assertGreater(k, 1.0)
        # power devig trims the long shot more than multiplicative does
        mult, _ = devig_multiplicative([1.5, 3.0, 8.0])
        self.assertLess(probs[2], mult[2])
        self.assertAlmostEqual(ev(2.0, 0.5), 0.0)


class NameTests(unittest.TestCase):
    def test_name_variants_and_mentions(self):
        v = name_variants({"fullName": "Brendan Allen", "mediumName": "B. Allen", "abbreviation": "ALL"})
        self.assertIn("B. Allen", v)
        self.assertIn("Allen", v)
        self.assertTrue(mentions("B. Allen By KO/TKO/DQ", v))
        self.assertFalse(mentions("C. Duncan By Submission", v))
        self.assertFalse(mentions("Allentown", {"Allen"}))

    def test_event_sides_from_name(self):
        sides = event_sides({"name": "Tampa Bay Buccaneers @ Dallas Cowboys"})
        self.assertIn("Cowboys", sides["home"])
        self.assertIn("Buccaneers", sides["AWAY"])


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.event = {"name": "Brendan Allen vs Christian Leroy Duncan", "homeParticipant": {"fullName": "Brendan Allen", "mediumName": "B. Allen"},
                      "awayParticipant": {"fullName": "Christian Leroy Duncan", "mediumName": "C. Duncan"}}
        self.markets = [
            market("ml", "Moneyline", "MONEYLINE", [sel("h", "Brendan Allen", "HOME_MONEYLINE", 9, 5), sel("a", "Christian Leroy Duncan", "AWAY_MONEYLINE", 41, 20)]),
            market("mov", "Method Of Victory", "LIST", [sel("ko", "B. Allen By KO/TKO/DQ", "LIST", 19, 2), sel("pts", "B. Allen By Points", "LIST", 13, 4), sel("dko", "C. Duncan By KO/TKO/DQ", "LIST", 29, 10)]),
            market("rb", "Round Betting", "LIST", [sel("r1", "B. Allen In Round 1", "LIST", 17, 2), sel("r3", "C. Duncan In Round 3", "LIST", 12, 1)]),
            market("tr", "Total Rounds", "TOTAL", [sel("o45", "Over 4.5", "OVER", 43, 20, 4.5), sel("u45", "Under 4.5", "UNDER", 37, 20, 4.5), sel("u25", "Under 2.5", "UNDER", 23, 10, 2.5)]),
        ]

    def test_win_type_round_and_decision_rules(self):
        pairs = implied_pairs(self.event, self.markets, max_per_rule=4)
        rules = {p["rule"] for p in pairs}
        self.assertIn("win_type_moneyline", rules)
        self.assertIn("round_under_rounds", rules)
        self.assertIn("decision_over_rounds", rules)
        ko = next(p for p in pairs if p["rule"] == "win_type_moneyline" and "Allen" in p["a"]["selection"])
        self.assertEqual(ko["b"]["selection"], "Brendan Allen")
        duncan = next(p for p in pairs if p["rule"] == "win_type_moneyline" and "Duncan" in p["a"]["selection"])
        self.assertEqual(duncan["b"]["selection_type"], "AWAY_MONEYLINE")
        r1 = next(p for p in pairs if p["rule"] == "round_under_rounds")
        self.assertEqual(r1["b"]["points"], 2.5)  # the tightest Under above round 1 is still implied
        dec = next(p for p in pairs if p["rule"] == "decision_over_rounds")
        self.assertEqual(dec["b"]["selection_type"], "OVER")

    def test_team_sports_rules(self):
        event = {"name": "Tampa Bay Buccaneers @ Dallas Cowboys"}
        markets = [
            market("ml", "Moneyline", "MONEYLINE", [sel("h", "DAL Cowboys", "HOME_MONEYLINE", 13, 11), sel("a", "TB Buccaneers", "AWAY_MONEYLINE", 24, 5)]),
            market("sp1", "Game Spread", "SPREAD", [sel("hs", "DAL Cowboys -9.5", "HOME_SPREAD", 21, 11, -9.5), sel("as", "TB Buccaneers +9.5", "AWAY_SPREAD", 21, 11, 9.5)]),
            market("sp2", "Game Spread", "SPREAD", [sel("hs2", "DAL Cowboys +3.5", "HOME_SPREAD", 16, 15, 3.5), sel("as2", "TB Buccaneers -3.5", "AWAY_SPREAD", 29, 4, -3.5)]),
            market("tp", "Total Points", "TOTAL", [sel("o", "Over 49.5", "OVER", 41, 21, 49.5), sel("u", "Under 49.5", "UNDER", 20, 11, 49.5)]),
            market("tt", "DAL Cowboys Total Points", "TOTAL", [sel("to", "Over 50.5", "OVER", 3, 1, 50.5), sel("tu", "Under 50.5", "UNDER", 4, 3, 50.5)]),
            market("ry", "Javonte Williams Total Rushing Yards", "LIST", [sel("ry50", "50+", "LIST", 3, 2), sel("ry100", "100+", "LIST", 5, 1)]),
            market("rry", "Javonte Williams Total Rushing + Receiving Yards", "LIST", [sel("rry75", "75+", "LIST", 2, 1), sel("rry125", "125+", "LIST", 4, 1)]),
            market("rryou", "Javonte Williams Total Rushing + Receiving Yards", "TOTAL", [sel("rryo", "Over 84.5", "OVER", 20, 11, 84.5), sel("rryu", "Under 84.5", "UNDER", 20, 11, 84.5)]),
            market("ftd", "First Touchdown Scorer", "LIST", [sel("f1", "Javonte Williams", "LIST", 9, 2)]),
            market("td", "Javonte Williams Touchdowns Scored", "LIST", [sel("td1", "1+", "LIST", 20, 13), sel("td2", "2+", "LIST", 7, 2)]),
        ]
        pairs = implied_pairs(event, markets, max_per_rule=4)
        by_rule = {}
        for p in pairs:
            by_rule.setdefault(p["rule"], []).append(p)
        ml = by_rule["ml_spread"]
        self.assertTrue(any(p["a"]["selection"] == "DAL Cowboys" and p["b"]["points"] == 3.5 for p in ml))  # ML implies the +3.5 cover
        self.assertTrue(any(p["a"]["points"] == -9.5 and p["b"]["selection"] == "DAL Cowboys" for p in ml))  # -9.5 cover implies ML
        self.assertFalse(any(p["a"]["selection"] == "DAL Cowboys" and p["b"]["points"] == -9.5 for p in ml))
        tt = by_rule["team_total_game_total"]
        self.assertTrue(any(p["a"]["market"] == "DAL Cowboys Total Points" and p["b"]["points"] == 49.5 and p["b"]["selection_type"] == "OVER" for p in tt))
        cs = by_rule["cross_stat_ladder"]
        self.assertTrue(any(p["a"]["selection"] == "100+" and p["b"]["selection"] == "75+" for p in cs))
        self.assertTrue(any(p["a"]["selection"] == "100+" and p["b"]["points"] == 84.5 for p in cs))
        fs = by_rule["first_scorer_anytime"]
        self.assertEqual(fs[0]["b"]["selection"], "1+")

    def test_soccer_rules(self):
        event = {"name": "Arsenal vs Leeds United"}
        markets = [
            market("mr", "Match Result", "THREE_WAY_MONEYLINE", [sel("h", "Arsenal", "HOME_MONEYLINE", 18, 13), sel("d", "Draw", "DRAW", 9, 2), sel("a", "Leeds", "AWAY_MONEYLINE", 9, 1)]),
            market("cs", "Correct Score", "LIST", [sel("cs10", "Arsenal 1-0", "LIST", 13, 2), sel("cs21", "Leeds 2-1", "LIST", 30, 1)]),
            market("tg", "Total Goals", "TOTAL", [sel("o15", "Over 1.5", "OVER", 5, 4, 1.5), sel("u15", "Under 1.5", "UNDER", 37, 10, 1.5), sel("o25", "Over 2.5", "OVER", 177, 100, 2.5), sel("u25", "Under 2.5", "UNDER", 2, 1, 2.5)]),
            market("btts", "Both Teams To Score", "MONEYLINE", [sel("y", "Yes", "AWAY_MONEYLINE", 7, 4), sel("n", "No", "HOME_MONEYLINE", 5, 3)]),
            market("att", "Arsenal Total Goals", "TOTAL", [sel("ao15", "Over 1.5", "OVER", 154, 100, 1.5), sel("au15", "Under 1.5", "UNDER", 23, 10, 1.5)]),
            market("dc", "Double Chance", "LIST", [sel("dc1", "Arsenal Or Draw", "LIST", 51, 50), sel("dc2", "Leeds Or Draw", "LIST", 29, 10)]),
        ]
        pairs = implied_pairs(event, markets, max_per_rule=4)
        labels = {(p["rule"], p["a"]["selection"], p["b"]["selection"]) for p in pairs}
        self.assertIn(("win_type_moneyline", "Arsenal 1-0", "Arsenal"), labels)
        self.assertIn(("win_type_moneyline", "Leeds 2-1", "Leeds"), labels)
        self.assertIn(("correct_score_totals", "Arsenal 1-0", "Under 1.5"), labels)
        self.assertIn(("correct_score_totals", "Arsenal 1-0", "No"), labels)
        self.assertIn(("correct_score_totals", "Leeds 2-1", "Over 2.5"), labels)
        self.assertIn(("correct_score_totals", "Leeds 2-1", "Yes"), labels)
        self.assertIn(("team_total_game_total", "Over 1.5", "Over 1.5"), labels)
        self.assertIn(("moneyline_double_chance", "Arsenal", "Arsenal Or Draw"), labels)


if __name__ == "__main__":
    unittest.main()
