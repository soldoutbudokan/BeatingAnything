"""Offline tests for the PointsBet cross-book gap monitor: market parsing, name matching, fair-price maths and gap state."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("PB_REGION", "au")
os.environ.setdefault("FD_REGION", "nj")

from tools import collect_pointsbet_live_alternates as C  # noqa: E402

HOME, AWAY = "Cleveland Browns", "Pittsburgh Steelers"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def outs(*names, side=None, points=None, player=False, price=1.9):
    return [dict(name=n, side=side, points=points, price=price, playerId="1" if player else None, isHidden=False, isOpenForBetting=True) for n in names]


class MarketClassification(unittest.TestCase):
    def check(self, name, expected, sport="football", home=HOME, away=AWAY, outcomes=None):
        got = C.classify_team_market(name, home, away, sport, outcomes or outs("x"))
        self.assertEqual(got, expected, name)

    def test_game_lines_and_periods(self):
        self.check("Moneyline", ("moneyline", 0, None))
        self.check("Point Spread", ("spread", 0, None))
        self.check("Pick Your Own Line", ("spread", 0, None))
        self.check("Alternate Totals", ("total", 0, None))
        self.check("Total Points Over/Under (Including Overtime)", ("total", 0, None))
        self.check("Point Spread 1st Half", ("spread", 1, None))
        self.check("Moneyline 1st Quarter", ("moneyline", 3, None))
        self.check("4th Quarter Point Spread -5.5", ("spread", 6, None))
        self.check("3rd Quarter Total Points Over/Under +7.5", ("total", 5, None))
        self.check("Run Line - First 5 Innings", ("spread", 1, None), sport="baseball")
        self.check("Moneyline - First 3 Innings", None, sport="baseball")
        self.check("1st Period Total", ("total", 1, None), sport="hockey")

    def test_team_totals(self):
        self.check("Pittsburgh Steelers Total", ("team_total", 0, "away"))
        self.check("Cleveland Browns Total 1st Half", ("team_total", 1, "home"))
        self.check("Home Total (2-Way)", ("team_total", 0, "home"), sport="hockey")
        self.check("1st Period Away Total (2-Way)", ("team_total", 1, "away"), sport="hockey")
        self.check("Atlanta Braves Total Runs - First 5 Innings", ("team_total", 1, "home"), sport="baseball", home="Atlanta Braves", away="Philadelphia Phillies")
        self.check("Aston Villa Exact Total Goals", None, sport="soccer", home="Aston Villa", away="Brentford")

    def test_three_way_and_draw_no_bet(self):
        draw = outs("Cleveland Browns", "Draw", "Pittsburgh Steelers")
        self.check("Moneyline 3 Way", ("moneyline3", 0, None), outcomes=draw)
        self.check("Money Line (3-Way)", ("moneyline3", 6, None), sport="hockey", outcomes=draw)
        self.check("1st Period Money Line (3-Way)", ("moneyline3", 1, None), sport="hockey", outcomes=draw)
        self.check("Draw No Bet", ("dnb", 6, None), sport="hockey")
        self.check("Draw No Bet", ("dnb", 0, None), sport="soccer")
        self.check("Match Result", ("moneyline3", 0, None), sport="soccer", outcomes=draw)
        self.check("Half-Time Result", ("moneyline3", 1, None), sport="soccer", outcomes=draw)
        self.check("3 Way Spread", None, sport="soccer")
        self.check("Alternate Total Runs - 3-Way", None, sport="baseball")
        self.check("Team With Most Hits - 3-Way", None, sport="baseball")

    def test_exotics_are_skipped(self):
        for name in ("Odd or Even Total", "Winning Margin", "Race to 10 Points", "Half Time & Full Time", "Correct Score", "Double Chance",
                     "Both Teams to Score", "Will There Be Overtime?", "Highest Scoring Half", "Team To Score The 2nd Goal", "Result After 15 Mins",
                     "Moneyline & O/U 2.5 Goals", "Tied After Regulation Time", "Leader After 5 Innings", "Total Runs - Bands", "Number of Goals"):
            self.check(name, None, sport="soccer", home="Aston Villa", away="Brentford")


class OutcomeParsing(unittest.TestCase):
    def test_spread_lines_from_side_or_name(self):
        self.assertEqual(C.parse_team_outcome("Cleveland Browns -13.5", "Home", -13.5, "spread", HOME, AWAY), ("home", -13.5))
        self.assertEqual(C.parse_team_outcome("North Carolina Tar Heels +21", "Neither", 0.0, "spread", "North Carolina Tar Heels", "Notre Dame Fighting Irish"), ("home", 21.0))
        self.assertEqual(C.parse_team_outcome("Western Kentucky (+28.5)", None, None, "spread", "New Mexico State", "Western Kentucky"), ("away", 28.5))
        self.assertEqual(C.parse_team_outcome("Philadelphia Flyers", None, 1.5, "spread", "New Jersey Devils", "Philadelphia Flyers"), ("away", 1.5))
        self.assertEqual(C.parse_team_outcome("Liverpool -1.5 Goals", None, None, "spread", "Liverpool", "Man City"), ("home", -1.5))

    def test_totals_and_moneylines(self):
        self.assertEqual(C.parse_team_outcome("Over 38.5", "Neither", 38.5, "total", HOME, AWAY), ("over", 38.5))
        self.assertEqual(C.parse_team_outcome("Over +47", "Neither", 0.0, "total", HOME, AWAY), ("over", 47.0))
        self.assertEqual(C.parse_team_outcome("Under 0.5 Goals", "Home", 0.5, "team_total", HOME, AWAY), ("under", 0.5))
        self.assertEqual(C.parse_team_outcome("Atlanta Braves Over", None, 3.5, "team_total", "Atlanta Braves", "Philadelphia Phillies"), ("over", 3.5))
        self.assertEqual(C.parse_team_outcome("Over (24.5)", None, None, "total", HOME, AWAY), ("over", 24.5))
        self.assertEqual(C.parse_team_outcome("Columbus Blue Jackets", "Neither", 0.0, "moneyline", "Columbus Blue Jackets", "Buffalo Sabres"), ("home", 0.0))
        self.assertEqual(C.parse_team_outcome("Tie", None, None, "moneyline3", HOME, AWAY), ("draw", 0.0))
        self.assertIsNone(C.parse_team_outcome("Draw", None, None, "moneyline", HOME, AWAY))
        self.assertIsNone(C.parse_team_outcome("Aston Villa 0 Goals", "Home", 0.5, "team_total", "Aston Villa", "Brentford"))

    def test_player_props(self):
        self.assertEqual(C.parse_prop_outcome("Aaron Rodgers Over 215.5", 215.5, None), ("Aaron Rodgers", "over", 215.5))
        self.assertEqual(C.parse_prop_outcome("Aaron Rodgers 170+", 169.5, None), ("Aaron Rodgers", "over", 169.5))
        self.assertEqual(C.parse_prop_outcome("Jaylen Warren", 0.5, None), ("Jaylen Warren", "over", 0.5))
        self.assertEqual(C.parse_prop_outcome("Jaylen Warren", 1.5, 1.5), ("Jaylen Warren", "over", 1.5))
        self.assertEqual(C.parse_prop_outcome("Igor Thiago", 1.0, None), ("Igor Thiago", "over", 0.5))
        self.assertEqual(C.parse_prop_outcome("A. Bohm Over 0.5", 0.5, None), ("A. Bohm", "over", 0.5))
        self.assertEqual(C.parse_prop_outcome("TK King 3+ Receptions", None, None), ("TK King", "over", 2.5))
        self.assertIsNone(C.parse_prop_outcome("Nobody", None, None))

    def test_stat_canonicalisation(self):
        cases = {"Quarterback Passing Yards": "passing yards", "Alternate Passing Touchdowns": "passing touchdowns", "Touchdown Passes": "passing touchdowns",
                 "Player Receptions": "receptions", "Rushing + Receiving Yards": "rushing + receiving yards", "Anytime Touchdown Scorer": "touchdowns",
                 "To Score 2+ Touchdowns": "touchdowns", "Anytime Goalscorer": "goals", "Player To Score 2+ Goals": "goals", "Player Shots on Goal": "shots on goal",
                 "Shots On Goal": "shots on goal", "Player Runs Batted In": "rbis", "Pitcher Strikeouts": "strikeouts", "Bases": "bases", "Pts & Rebs & Asts": "pts + rebs + asts",
                 "Points + Rebounds + Assists": "pts + rebs + asts", "Threes Made": "threes made", "Rush Attempts": "rush attempts", "Pitching Outs": "pitching outs"}
        for name, canon in cases.items():
            self.assertEqual(C.canon_stat(name), canon, name)
        self.assertIsNone(C.canon_stat("Player To Record A Sack"))


class PointsBetRows(unittest.TestCase):
    def test_market_rows_cover_props_and_periods(self):
        d = dict(key="e1", homeTeam=HOME, awayTeam=AWAY, startsAt="2026-10-02T00:15:00Z", sgmStatus="Available", fixedOddsMarkets=[
            dict(eventName="Point Spread", groupName="Game Lines", outcomes=outs("Cleveland Browns +2.5", side="Home", points=2.5) + outs("Pittsburgh Steelers -2.5", side="Away", points=-2.5)),
            dict(eventName="Alternate Totals", groupName="Pick Your Own Total", outcomes=outs("Over 23.5", side="Neither", points=23.5, price=1.08)),
            dict(eventName="Anytime Touchdown Scorer", groupName="Player Touchdowns Markets", outcomes=outs("Jaylen Warren", side="Away", points=0.5, player=True, price=2.1)),
            dict(eventName="First Touchdown Scorer", groupName="Touchdowns", outcomes=outs("Jaylen Warren", side="Away", points=0.0, player=True, price=5.5)),
            dict(eventName="Alternate Receptions", groupName="Alternate Receptions", outcomes=outs("Harold Fannin 3+", side="Home", points=2.5, player=True, price=1.29)),
            dict(eventName="Moneyline (G. Holmes v A. Nola)", groupName="Listed Pitchers", outcomes=outs("Cleveland Browns", side="Home", points=0.0)),
            dict(eventName="Winning Margin", groupName="Game Props", outcomes=outs("Cleveland Browns (1-6)", side="Home", points=0.0)),
            dict(eventName="Total 1st Half", groupName="1st Half", outcomes=outs("Over 12.5", side="Neither", points=12.5, price=1.18)),
        ])
        rows, unknown = C.pb_market_rows(d, "nfl", "football", T0)
        kinds = sorted((r["kind"], r["period"], r["sel"], r["line"]) for r in rows)
        self.assertEqual(kinds, [("prop", 0, "over", 0.5), ("prop", 0, "over", 2.5), ("spread", 0, "away", -2.5), ("spread", 0, "home", 2.5), ("total", 0, "over", 23.5), ("total", 1, "over", 12.5)])
        self.assertEqual(unknown, ["Winning Margin"])
        props = {r["player"]: (r["stat"], r["main"]) for r in rows if r["kind"] == "prop"}
        self.assertEqual(props, {"Jaylen Warren": ("touchdowns", True), "Harold Fannin": ("receptions", False)})
        self.assertFalse([r for r in rows if r["kind"] == "total" and r["line"] == 23.5][0]["main"])


class FanDuelClassification(unittest.TestCase):
    def test_market_types(self):
        tie = [dict(runnerName="Tie")]
        cases = {("MATCH_HANDICAP_(2-WAY)", "football"): ("spread", 0, None, None, None), ("ALTERNATE_HANDICAPS", "basketball"): ("spread", 0, None, None, None),
                 ("1ST_PERIOD_ALTERNATE_PUCK_LINE", "hockey"): ("spread", 1, None, None, None), ("1ST_HALF_RUN_LINE", "baseball"): ("spread", 1, None, None, None),
                 ("HOME_TEAM_-1.5_GOALS", "soccer"): ("spread", 0, None, None, None), ("TOTAL_POINTS_(OVER/UNDER)", "football"): ("total", 0, None, None, None),
                 ("OVER_UNDER_25", "soccer"): ("total", 0, None, None, None), ("1ST_HALF_OVER/UNDER_1.5_GOALS", "soccer"): ("total", 1, None, None, None),
                 ("HOME_TOTAL_RUNS", "baseball"): ("team_total", 0, "home", None, None), ("1ST_PERIOD_AWAY_TEAM_ALTERNATE_TOTAL_GOALS", "hockey"): ("team_total", 1, "away", None, None),
                 ("MONEY_LINE", "football"): ("moneyline", 0, None, None, None), ("1ST_HALF_WINNER", "football"): ("moneyline", 1, None, None, None),
                 ("DRAW_NO_BET", "soccer"): ("dnb", 0, None, None, None), ("WIN-DRAW-WIN", "soccer"): ("moneyline3", 0, None, None, None),
                 ("HALF-TIME_RESULT", "soccer"): ("moneyline3", 1, None, None, None), ("***OVER/UNDER_0.5_RUNS_1ST_INNINGS", "baseball"): ("total", 3, None, None, None),
                 ("PLAYER_X_RECEPTIONS_MEDIUM", "football"): ("prop", 0, None, "receptions", None), ("PLAYER_MEDIUM_ALT_RUSHING_YARDS_CFB", "football"): ("prop", 0, None, "rushing yards", None),
                 ("ANY_TIME_TOUCHDOWN_SCORER", "football"): ("prop", 0, None, "touchdowns", 0.5), ("TO_SCORE_2+_TOUCHDOWNS", "football"): ("prop", 0, None, "touchdowns", 1.5),
                 ("PLAYER_TO_RECORD_2+_SHOTS_ON_GOAL", "hockey"): ("prop", 0, None, "shots on goal", 1.5), ("TO_HIT_A_HOME_RUN", "baseball"): ("prop", 0, None, "home runs", 0.5),
                 ("PLAYER_TO_RECORD_A_HIT", "baseball"): ("prop", 0, None, "hits", 0.5), ("PITCHER_C_TOTAL_STRIKEOUTS", "baseball"): ("prop", 0, None, "strikeouts", None)}
        for (mt, sport), exp in cases.items():
            self.assertEqual(C.classify_fd_market(mt, tie if exp and exp[0] == "moneyline3" else [], sport), exp, mt)
        self.assertEqual(C.classify_fd_market("MONEYLINE_(3-WAY)_NO_PUSH", tie, "hockey"), ("moneyline3", 6, None, None, None))
        for mt in ("MONEY_LINE_/_TOTAL_DOUBLE", "BOTH_TEAMS_TO_SCORE_4+_GOALS", "FIRST_TOUCHDOWN_SCORER", "1ST_PERIOD_ANY_TIME_GOAL_SCORER", "WINNING_MARGIN",
                   "FULL_TIME_RESULT_-_2_UP", "CORRECT_SCORE", "EXTRA_INNINGS?", "PLAYER_TO_SCORE_IN_THE_FIRST_3_MINUTES_WNBA", "TO_RECORD_1+_SACK", "AWAY_DRIVE_X_RECEIVING_YDS_-_PLAYER_Y"):
            self.assertIsNone(C.classify_fd_market(mt, [], "football"), mt)


class NameMatching(unittest.TestCase):
    def test_team_similarity(self):
        self.assertEqual(C.team_sim("North Carolina", "North Carolina Tar Heels"), 0.9)
        self.assertGreaterEqual(C.team_sim("Man City", "Manchester City"), 0.9)
        self.assertGreaterEqual(C.team_sim("Mississippi", "Ole Miss Rebels"), 0.9)
        self.assertGreaterEqual(C.team_sim("Tottenham Hotspur", "Tottenham Hotspur"), 1.0)
        self.assertGreaterEqual(C.team_sim("Brighton", "Brighton and Hove Albion"), 0.9)
        self.assertLess(C.team_sim("New York Giants", "New York Jets"), 0.75)
        self.assertLess(C.team_sim("North Carolina State", "North Carolina Tar Heels"), 0.75)
        self.assertGreaterEqual(C.team_sim("Miami Florida", "Miami Hurricanes"), 0.9)
        self.assertGreaterEqual(C.team_sim("UL Lafayette", "Louisiana-Lafayette Ragin' Cajuns"), 0.9)
        self.assertGreaterEqual(C.team_sim("LA Galaxy", "Los Angeles Galaxy"), 0.9)
        self.assertLess(C.team_sim("Napoli", "Roma"), 0.5)

    def test_event_matching_uses_both_sides_and_start(self):
        pb = {"p1": dict(id="p1", league="ncaaf", home="North Carolina Tar Heels", away="Notre Dame Fighting Irish", start=T0),
              "p2": dict(id="p2", league="ncaaf", home="Duke Blue Devils", away="Virginia Cavaliers", start=T0),
              "p3": dict(id="p3", league="mlb", home="Atlanta Braves", away="Philadelphia Phillies", start=T0)}
        other = {"o1": dict(id="o1", league="ncaaf", home="North Carolina", away="Notre Dame", start=T0 + timedelta(minutes=15)),
                 "o2": dict(id="o2", league="ncaaf", home="Virginia", away="Duke", start=T0),
                 "o3": dict(id="o3", league="mlb", home="Atlanta Braves", away="Philadelphia Phillies", start=T0 + timedelta(hours=3)),
                 "o4": dict(id="o4", league="nfl", home="Atlanta Braves", away="Philadelphia Phillies", start=T0)}
        self.assertEqual(C.match_events(pb, other), {"o1": "p1", "o2": "p2"})

    def test_player_resolution(self):
        cands = {"alec bohm", "austin riley", "aaron rodgers", "fernando tatis"}
        self.assertEqual(C.resolve_player("a bohm", cands), "alec bohm")
        self.assertEqual(C.resolve_player(C.norm_player("Fernando Tatis Jr."), cands), "fernando tatis")
        self.assertIsNone(C.resolve_player("a nola", cands))
        self.assertIsNone(C.resolve_player("a rodgers", {"aaron rodgers", "amari rodgers"}))


def row(book, kind, sel, line, price, period=0, side=None, player=None, stat=None, game="g", limit=None, age=None, main=True):
    return dict(book=book, league="nfl", game=game, home=HOME, away=AWAY, start="2026-10-02T00:15:00+00:00", period=period, kind=kind, sel=sel, side=side, line=line,
                price=price, main=main, player=player, player_key=C.norm_player(player) if player else None, stat=stat,
                team={"home": HOME, "away": AWAY, "draw": "Draw"}.get(sel, (sel or "").capitalize()) if kind != "prop" else player, limit=limit, age_min=age, updated=None, sgm="Available")


class Comparison(unittest.TestCase):
    def test_arbs_and_pinnacle_fair_edges(self):
        pb = [row("pointsbet_au", "spread", "away", 4.5, 1.69, age=12, main=False), row("pointsbet_au", "total", "over", 44.5, 1.95),
              row("pointsbet_au", "prop", "over", 0.5, 2.1, player="J. Warren", stat="touchdowns"), row("pointsbet_au", "moneyline3", "draw", 0.0, 4.1, period=6),
              row("pointsbet_au", "dnb", "home", 0.0, 2.6, period=6), row("pointsbet_au", "team_total", "over", 26.5, 1.74, side="home")]
        pin = [row("pinnacle", "spread", "home", -4.5, 2.45, limit=20000), row("pinnacle", "spread", "away", 4.5, 1.60, limit=20000),
               row("pinnacle", "total", "over", 44.5, 1.90), row("pinnacle", "total", "under", 44.5, 1.95),
               row("pinnacle", "prop", "over", 0.5, 1.95, player="Jaylen Warren", stat="touchdowns", limit=250), row("pinnacle", "prop", "under", 0.5, 1.85, player="Jaylen Warren", stat="touchdowns", limit=250),
               row("pinnacle", "moneyline3", "home", 0.0, 1.78, period=6), row("pinnacle", "moneyline3", "away", 0.0, 3.74, period=6), row("pinnacle", "moneyline3", "draw", 0.0, 4.49, period=6),
               row("pinnacle", "team_total", "under", 26.5, 2.44, side="home"), row("pinnacle", "team_total", "over", 26.5, 1.59, side="home")]
        fd = [row("fanduel_nj", "spread", "home", -4.5, 2.6), row("fanduel_nj", "prop", "under", 0.5, 1.7, player="Jaylen Warren", stat="touchdowns")]
        pairs, edges = C.compare(pb, {"pinnacle": pin, "fanduel_nj": fd})
        by = {(p["pb_leg"], p["other_book"]): p["inv_sum"] for p in pairs}
        self.assertAlmostEqual(by[("Pittsburgh Steelers +4.5", "pinnacle")], 1 / 1.69 + 1 / 2.45, places=4)
        self.assertAlmostEqual(by[("Pittsburgh Steelers +4.5", "fanduel_nj")], 1 / 1.69 + 1 / 2.6, places=4)
        self.assertAlmostEqual(by[("J. Warren Over 0.5 touchdowns", "pinnacle")], 1 / 2.1 + 1 / 1.85, places=4)
        self.assertAlmostEqual(by[(f"{HOME} Over 26.5", "pinnacle")], 1 / 1.74 + 1 / 2.44, places=4)
        self.assertNotIn(("Draw", "pinnacle"), by)
        ev = {e["pb_leg"]: e for e in edges}
        fair_away = (1 / 1.60) / (1 / 1.60 + 1 / 2.45)
        self.assertAlmostEqual(ev["Pittsburgh Steelers +4.5"]["ev"], 1.69 * fair_away - 1, places=3)
        self.assertEqual(ev["Pittsburgh Steelers +4.5"]["pin_limit"], 20000)
        inv = [1 / 1.78, 1 / 3.74, 1 / 4.49]
        self.assertAlmostEqual(ev["Draw"]["pin_fair"], inv[2] / sum(inv), places=3)
        self.assertEqual(ev["Draw"]["pin_prices"], [4.49, 1.78, 3.74])
        self.assertAlmostEqual(ev[f"{HOME} DNB"]["pin_fair"], inv[0] / (inv[0] + inv[1]), places=3)
        self.assertAlmostEqual(ev["J. Warren Over 0.5 touchdowns"]["pin_fair"], (1 / 1.95) / (1 / 1.95 + 1 / 1.85), places=3)
        self.assertEqual(ev["Over 44.5"]["market"], "nfl total")
        self.assertEqual(ev["Draw"]["market"], "nfl moneyline3 Q4")

    def test_new_gaps_state(self):
        arbs = [dict(home=HOME, away=AWAY, market="nfl spread", pb_leg="Pittsburgh Steelers +4.5", pb_price=1.69, other_book="pinnacle", other_price=2.45, inv_sum=0.975)]
        edges = [dict(home=HOME, away=AWAY, market="nfl total", pb_leg="Over 44.5", pb_price=1.95, pin_price=1.9, pin_fair=0.55, ev=0.0725)]
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state.json")
            fresh = C.new_gaps(arbs, edges, 0.98, 0.03, state, T0)
            self.assertEqual([t for t, _ in fresh], ["arb", "edge"])
            self.assertEqual(C.new_gaps(arbs, edges, 0.98, 0.03, state, T0 + timedelta(hours=1)), [])
            arbs[0]["inv_sum"] = 0.969
            edges[0]["ev"] = 0.0826
            self.assertEqual(len(C.new_gaps(arbs, edges, 0.98, 0.03, state, T0 + timedelta(hours=2))), 2)
            self.assertEqual(C.new_gaps(arbs, edges, 0.98, 0.03, state, T0 + timedelta(hours=25)), [])  # 23h since the improved report
            self.assertEqual(len(C.new_gaps(arbs, edges, 0.98, 0.03, state, T0 + timedelta(hours=27))), 2)  # 24h window elapsed
            self.assertEqual(C.new_gaps(arbs, edges, 0.98, 0.10, state, T0 + timedelta(hours=52)), [("arb", arbs[0])])
            keys = json.load(open(state))
            self.assertIn("Pittsburgh Steelers @ Cleveland Browns | nfl total | Over 44.5 | pinnacle-fair", keys)


if __name__ == "__main__":
    unittest.main()
