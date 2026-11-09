"""Offline tests for the FanDuel-against-Pinnacle screen: devig maths, tab slugs, reference lookup and closing-line grading."""
import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("PB_REGION", "au")
os.environ.setdefault("FD_REGION", "nj")

from tools import screen_fanduel_vs_pinnacle as S  # noqa: E402

T0 = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)


def row(sel, line, price, book="pinnacle", kind="total", period=0):
    return dict(book=book, league="nba", game="g1", home="H", away="A", start="2026-11-10T00:00:00+00:00", period=period, kind=kind, sel=sel, side=None,
                line=line, price=price, main=True, player=None, player_key=None, stat=None, team=sel.capitalize(), limit=500, age_min=None)


class Devig(unittest.TestCase):
    def test_methods_sum_to_one_and_agree_on_even_market(self):
        d = S.devig([1.9091, 1.9091])
        for probs in d.values():
            self.assertAlmostEqual(sum(probs), 1, places=6)
            self.assertAlmostEqual(probs[0], 0.5, places=6)

    def test_power_and_additive_shade_long_shot_below_multiplicative(self):
        d = S.devig([4.0, 1.2105])
        self.assertLess(d["power"][0], d["mult"][0])
        self.assertLess(d["add"][0], d["mult"][0])
        self.assertAlmostEqual(sum(d["power"]), 1, places=6)

    def test_additive_falls_back_when_negative(self):
        d = S.devig([1.02, 21.0, 101.0])
        self.assertEqual(d["add"], d["mult"])


class Lookup(unittest.TestCase):
    def test_fair_needs_both_sides_at_same_line(self):
        idx, players = S.c.index_rows([row("over", 104.5, 1.7812), row("under", 104.5, 2.1), row("over", 105.5, 1.9174)])
        f = S.fair_from(idx, players, row("over", 104.5, 1.9091, book="fanduel_nj"))
        self.assertAlmostEqual(f["probs"]["mult"], (1 / 1.7812) / (1 / 1.7812 + 1 / 2.1), places=4)
        self.assertEqual(f["prices"], [1.7812, 2.1])
        self.assertIsNone(S.fair_from(idx, players, row("over", 105.5, 2.04, book="fanduel_nj")))

    def test_tab_slug(self):
        self.assertEqual(S.tab_slug("Points/Assists"), "points-assists")
        self.assertEqual(S.tab_slug("Same Game Parlay™"), "same-game-parlay")


class Grade(unittest.TestCase):
    def test_entry_price_against_current_fair(self):
        flag = dict(league="nba", game="A @ H", market="nba total 1H", leg="Over 104.5", start="2026-11-10T00:00:00+00:00", captured=T0.isoformat(),
                    fd_price=1.9091, ev_worst=0.033, pin_prices=[1.7812, 2.1])
        cur = dict(flag, fd_price=1.8, pin_prices=[1.7, 2.2], pin_fair=dict(mult=0.564, add=0.566, power=0.567))
        gone = dict(flag, leg="Over 99.5")
        graded, n = S.grade([flag, dict(flag, fd_price=1.5), gone], [cur], T0)
        self.assertEqual((len(graded), n), (1, 2))
        self.assertEqual(graded[0]["entry_price"], 1.9091)  # first sighting, not the later lower price
        self.assertAlmostEqual(graded[0]["clv_worst"], round(1.9091 * 0.564 - 1, 4))
        self.assertEqual(graded[0]["hours_to_start"], 5.0)
        self.assertEqual(S.grade([flag], [cur], T0, max_hours=2)[0], [])


if __name__ == "__main__":
    unittest.main()
