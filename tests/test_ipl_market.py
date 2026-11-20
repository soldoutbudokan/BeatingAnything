"""IPL market join: the price read for a forecast must predate its information state."""
import unittest
from datetime import timedelta

import numpy as np
import pandas as pd

try:
    from models.ipl.market.prices import STATE_OFFSET, back_odds, join, price_at, team_in, two_way
    from models.ipl.market.score import BETFAIR_COMMISSION, bets
except ImportError:
    join = None


def history(book, quotes):
    """An OddsPapi historical-odds response: quotes = {outcome: [(createdAt, price, active), ...]}."""
    outcomes = {o: {"players": {"0": [{"createdAt": t, "price": px, "limit": 100.0, "active": a, "exchangeMeta": None}
                                      for t, px, a in rows]}} for o, rows in quotes.items()}
    return {"fixtureId": "f", "bookmakers": {book: {"markets": {"271": {"outcomes": outcomes}}}}}


@unittest.skipIf(join is None, "model dependencies not installed")
class MarketJoin(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2026-04-01 14:00", tz="UTC")
        t = [self.start + timedelta(hours=h) for h in (-30, -4, -1, -0.1, 1)]
        self.s = pd.DataFrame({"source": "kalshi", "market_id": "m", "team": "Mumbai Indians",
                               "teams": "Mumbai Indians|Chennai Super Kings", "ts": t,
                               "price": [0.50, 0.55, 0.60, 0.70, 0.95], "start": self.start, "spread": 0.02})

    def test_price_never_from_after_the_state(self):
        self.assertEqual(price_at(self.s, self.start + STATE_OFFSET["pre_news"]), 0.55)
        self.assertEqual(price_at(self.s, self.start + STATE_OFFSET["post_toss"]), 0.60)

    def test_stale_quote_is_missing(self):
        self.assertTrue(np.isnan(price_at(self.s.iloc[:1], self.start + STATE_OFFSET["pre_news"])))

    def test_join_by_teams_and_date(self):
        p = pd.DataFrame({"match_id": ["1", "1", "2"], "date": pd.Timestamp("2026-04-01"),
                          "x": 0}, index=[0, 0, 0])   # duplicate index, as after concatenating seasons
        p = p.assign(**{"team1": "Mumbai Indians", "team2": ["Chennai Super Kings", "Chennai Super Kings", "Gujarat Titans"],
                        "state": ["pre_news", "post_toss", "pre_news"]})
        j = join(p, self.s)
        self.assertEqual(j["market_p_team1"].tolist()[:2], [0.55, 0.60])
        self.assertTrue(np.isnan(j["market_p_team1"].iloc[2]))
        p = pd.DataFrame({"match_id": ["1", "1", "2"], "date": pd.Timestamp("2025-04-01"),
                          "team1": ["Mumbai Indians", "Mumbai Indians", "Mumbai Indians"],
                          "team2": ["Chennai Super Kings", "Chennai Super Kings", "Gujarat Titans"],
                          "state": ["pre_news", "post_toss", "pre_news"]})
        self.assertTrue(join(p, self.s)["market_p_team1"].isna().all())   # same sides, a year apart

    def test_one_row_per_source(self):
        p = pd.DataFrame({"match_id": ["1"], "date": pd.Timestamp("2026-04-01"), "team1": "Mumbai Indians",
                          "team2": "Chennai Super Kings", "state": "post_toss"})
        both = pd.concat([self.s, self.s.assign(source="betfair", price=self.s["price"] + 0.01)])
        j = join(p, both)
        self.assertEqual(sorted(j["market_source"]), ["betfair", "kalshi"])
        self.assertEqual(sorted(j["market_p_team1"].round(2)), [0.60, 0.61])

    def test_decimal_odds_to_price(self):
        # two requests per fixture at Betfair Exchange, one outcome each
        r = [history("betfair-ex", {"271": [("2026-04-01T09:00:00.000Z", 2.0, True), ("2026-04-01T12:00:00.000Z", 1.6, True),
                                            ("2026-04-01T15:00:00.000Z", 1.1, True)]}),
             history("betfair-ex", {"272": [("2026-04-01T10:00:00.000Z", 2.5, True), ("2026-04-01T13:00:00.000Z", 2.5, False)]})]
        q = two_way(back_odds(r, "betfair-ex", "271"), back_odds(r, "betfair-ex", "272"), self.start)
        self.assertEqual(q["ts"].dt.hour.tolist(), [10, 12, 13])   # from the first two-sided quote to the first ball
        np.testing.assert_allclose(q["price"][:2], [(0.5 + 0.6) / 2, (0.625 + 0.6) / 2])   # mid of ask 1/o1, bid 1 - 1/o2
        np.testing.assert_allclose(q["spread"][:2], [0.0, 0.025])                          # ask - bid, never negative
        self.assertEqual(price_at(q, self.start + timedelta(hours=-1.5)), 0.6125)
        self.assertTrue(np.isnan(price_at(q, self.start + STATE_OFFSET["post_toss"])))     # withdrawn an hour earlier

    def test_betfair_commission_on_winnings_only(self):
        m = pd.DataFrame({"team1_won": [1.0, 0.0], "p_team1": 0.7, "market_p_team1": 0.49, "market_spread": 0.02,
                          "market_source": "betfair", "state": "post_toss", "year": 2026})
        np.testing.assert_allclose(bets(m, 0.0)["ret"], [(1 - BETFAIR_COMMISSION) * 0.5 / 0.5, -1.0])

    def test_team_names(self):
        self.assertEqual(team_in("Mumbai Indians vs Chennai Super Kings"), ["Mumbai Indians", "Chennai Super Kings"])
        self.assertEqual(team_in("Will RCB beat KKR ?"), ["Royal Challengers Bengaluru", "Kolkata Knight Riders"])


if __name__ == "__main__":
    unittest.main()
