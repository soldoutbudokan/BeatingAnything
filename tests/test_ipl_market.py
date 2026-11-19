"""IPL market join: the price read for a forecast must predate its information state."""
import unittest
from datetime import timedelta

import numpy as np
import pandas as pd

try:
    from models.ipl.market.prices import STATE_OFFSET, join, price_at, team_in
except ImportError:
    join = None


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

    def test_team_names(self):
        self.assertEqual(team_in("Mumbai Indians vs Chennai Super Kings"), ["Mumbai Indians", "Chennai Super Kings"])
        self.assertEqual(team_in("Will RCB beat KKR ?"), ["Royal Challengers Bengaluru", "Kolkata Knight Riders"])


if __name__ == "__main__":
    unittest.main()
