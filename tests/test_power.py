import json
import math
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from beating import power as pw

NOW = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)
ESPN_TEAMS = [dict(abbreviation="LAC", displayName="LA Clippers", name="Clippers", location="LA"),
              dict(abbreviation="LAL", displayName="Los Angeles Lakers", name="Lakers", location="Los Angeles"),
              dict(abbreviation="PHI", displayName="Philadelphia 76ers", name="76ers", location="Philadelphia"),
              dict(abbreviation="POR", displayName="Portland Trail Blazers", name="Trail Blazers", location="Portland"),
              dict(abbreviation="GS", displayName="Golden State Warriors", name="Warriors", location="Golden State"),
              dict(abbreviation="MTL", displayName="Montreal Canadiens", name="Canadiens", location="Montreal"),
              dict(abbreviation="SAC", displayName="Sacramento Kings", name="Kings", location="Sacramento"),
              dict(abbreviation="MIN", displayName="Minnesota Vikings", name="Vikings", location="Minnesota")]


def row(home, away, start, **kw):
    r = {k: "" for k in pw.FIELDS}
    r.update(league="nba", event_id=f"{home}{away}{start:%m%d%H}", start_utc=pw.iso(start), season_type=2, home=home, away=away,
             neutral=0, state="final" if start < NOW else "pre")
    r.update(kw)
    return r


class Prices(unittest.TestCase):
    def test_american(self):
        self.assertEqual(pw.american("-148"), -148)
        self.assertEqual(pw.american("+124"), 124)
        self.assertEqual(pw.american("EVEN"), 100)
        self.assertIsNone(pw.american("o50.5"))
        self.assertIsNone(pw.american(None))
        self.assertAlmostEqual(pw.american_to_prob(-150), 0.6)
        self.assertAlmostEqual(pw.american_to_prob(150), 0.4)

    def test_devig_sums_to_one_and_leans_to_the_favourite(self):
        for h, a in ((-690, 490), (-110, -110), (-1440, 850), (150, -180)):
            imp = [pw.american_to_prob(h), pw.american_to_prob(a)]
            fair = pw.devig(imp)
            self.assertAlmostEqual(sum(fair), 1.0, places=9)
            fav = 0 if imp[0] >= imp[1] else 1
            self.assertGreaterEqual(fair[fav] + 1e-12, imp[fav] / sum(imp))  # more of the margin comes off the long shot
        self.assertEqual(pw.devig([0.5, 0.5]), [0.5, 0.5])
        self.assertAlmostEqual(pw.devig([0.3, 0.6])[0], 1 / 3)  # no margin to remove: scale only

    def test_book_mid_needs_a_tight_two_sided_book(self):
        self.assertAlmostEqual(pw.book_mid("0.5400", "0.5600"), 0.55)
        self.assertIsNone(pw.book_mid(0.30, 0.59))   # wide
        self.assertIsNone(pw.book_mid(0, 0.01))      # no bid
        self.assertIsNone(pw.book_mid(None, 0.4))

    def test_two_sided_normalises_both_teams(self):
        self.assertAlmostEqual(pw.two_sided(0.55, 0.47), 0.55 / 1.02)
        self.assertAlmostEqual(pw.two_sided(None, 0.4), 0.6)
        self.assertIsNone(pw.two_sided(None, None))

    def test_consensus_is_mean_log_odds_of_available_sources(self):
        r = row("LAL", "LAC", NOW, kalshi_p="0.6000", draftkings_home="-150", draftkings_away="130")
        ps = pw.source_probs(r)
        self.assertEqual(set(ps), {"kalshi", "draftkings"})
        self.assertAlmostEqual(pw.consensus(r), (pw.logit(0.6) + pw.logit(ps["draftkings"])) / 2)
        self.assertIsNone(pw.consensus(row("LAL", "LAC", NOW)))


class Names(unittest.TestCase):
    def setUp(self):
        self.t = pw.Teams(ESPN_TEAMS)

    def test_names_and_nicknames(self):
        self.assertEqual(self.t.name("Los Angeles Clippers"), "LAC")   # Pinnacle spells the city out
        self.assertEqual(self.t.name("Trail Blazers"), "POR")          # Polymarket uses nicknames
        self.assertEqual(self.t.name("76ers"), "PHI")
        self.assertEqual(self.t.name("Montréal Canadiens"), "MTL")
        self.assertEqual(self.t.name("Minnesota Vikings"), "MIN")      # "vikings" must not match "kings"
        self.assertIsNone(self.t.name("Home Goals (12 Games)"))
        self.assertIsNone(self.t.name("Yes"))

    def test_kalshi_codes(self):
        alias = pw.LEAGUES["nba"]["kalshi_alias"]
        self.assertEqual(self.t.code("GSW", alias), "GS")
        self.assertEqual(self.t.code("LAL", alias), "LAL")
        self.assertIsNone(self.t.code("LIO", alias))                   # London Lions exhibition


class Espn(unittest.TestCase):
    def test_dk_from_odds(self):
        block = {"provider": {"name": "DraftKings"}, "spread": -2.5, "moneyline": {"home": {"close": {"odds": "-148"}}, "away": {"close": {"odds": "+124"}}}}
        self.assertEqual(pw.dk_from_odds(block), (-148, 124, -2.5))
        legacy = {"provider": {"name": "DraftKings"}, "homeTeamOdds": {"moneyLine": -166}, "awayTeamOdds": {"moneyLine": 140}}
        self.assertEqual(pw.dk_from_odds(legacy), (-166, 140, None))
        self.assertIsNone(pw.dk_from_odds(dict(block, provider={"name": "Other Book"})))
        self.assertIsNone(pw.dk_from_odds({"provider": {"name": "DraftKings"}}))

    def test_parse_time_formats(self):
        want = datetime(2026, 11, 20, 1, 15, tzinfo=timezone.utc)
        for s in ("2026-11-20T01:15Z", "2026-11-20T01:15:00Z", "2026-11-20 01:15:00+00"):
            self.assertEqual(pw.parse_time(s), want)


class Ledger(unittest.TestCase):
    def game(self, state, start, dk=(-150, 130, -3.0)):
        return dict(event_id="1", start=start, season_type=2, home="LAL", away="LAC", neutral=0, state=state, home_score="", away_score="", dk=dk)

    def test_prices_are_frozen_at_the_start(self):
        ledger = {}
        pw.upsert(ledger, "nba", self.game("pre", NOW + timedelta(hours=2)), NOW)
        r = ledger[("nba", "1")]
        self.assertEqual((r["draftkings_home"], r["draftkings_away"], r["draftkings_spread"]), ("-150", "130", -3.0))
        later = NOW + timedelta(hours=3)
        pw.upsert(ledger, "nba", self.game("live", NOW + timedelta(hours=2), dk=(-900, 600, -12.5)), later)  # in-play price
        self.assertEqual(r["draftkings_home"], "-150")
        self.assertEqual(r["state"], "live")
        self.assertFalse(pw.open_for_quotes(r, later))
        # scheduled start passed but ESPN still says "pre": still closed to new prices
        pw.upsert(ledger, "nba", self.game("pre", NOW + timedelta(hours=2), dk=(-900, 600, -12.5)), later)
        self.assertEqual(r["draftkings_home"], "-150")

    def test_round_trip_drops_derived_keys(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(pw, "LEDGER", Path(d) / "games.csv"):
            r = row("LAL", "LAC", NOW, kalshi_p="0.6000")
            r["_b2b"] = 1
            pw.save_ledger({("nba", r["event_id"]): r})
            back = pw.load_ledger()
            self.assertEqual(back[("nba", r["event_id"])]["kalshi_p"], "0.6000")
            self.assertNotIn("_b2b", back[("nba", r["event_id"])])
            self.assertFalse(list(Path(d).glob("*.tmp")))

    def test_index_matches_pair_and_time(self):
        a, b = row("LAL", "LAC", NOW), row("LAC", "LAL", NOW + timedelta(days=1))
        idx = pw.Index([a, b])
        self.assertIs(idx.find("LAC", "LAL", NOW + timedelta(hours=2)), a)
        self.assertIs(idx.find("LAL", "LAC", NOW + timedelta(hours=20)), b)
        self.assertIsNone(idx.find("LAL", "LAC", NOW + timedelta(days=5)))
        self.assertIsNone(idx.find("LAL", "PHI", NOW))

    def test_scan_dates(self):
        cfg = pw.LEAGUES["nba"]
        days, st = pw.scan_dates({}, "nba", cfg, NOW)
        today = NOW.astimezone(pw.ET).date()
        self.assertEqual(days[0], today - timedelta(days=cfg["backfill_days"]))
        self.assertEqual(days[-1], today + timedelta(days=cfg["lookahead_days"]))
        self.assertEqual(len(days), cfg["backfill_days"] + cfg["lookahead_days"] + 1)
        days2, _ = pw.scan_dates({"nba": st}, "nba", cfg, NOW + timedelta(hours=1))
        self.assertEqual(days2[0], today - timedelta(days=2))
        self.assertEqual(len(days2), cfg["lookahead_days"] + 3)
        gap, _ = pw.scan_dates({"nba": st}, "nba", cfg, NOW + timedelta(days=9))     # job was off for a week: no hole
        self.assertEqual(gap[0], today - timedelta(days=2))


class Kalshi(unittest.TestCase):
    def test_events_need_two_known_teams(self):
        t = pw.Teams(ESPN_TEAMS)
        mk = lambda e, c: dict(ticker=f"{e}-{c}", event_ticker=e, occurrence_datetime="2026-11-20T04:00:00Z")  # noqa: E731
        ev = pw.kalshi_events([mk("G-26NOV19GSWLAL", "GSW"), mk("G-26NOV19GSWLAL", "LAL"), mk("G-26OCT05LIOPHI", "LIO"), mk("G-26OCT05LIOPHI", "PHI")],
                              pw.LEAGUES["nba"], t)
        self.assertEqual(list(ev), ["G-26NOV19GSWLAL"])
        self.assertEqual(set(ev["G-26NOV19GSWLAL"]["mk"]), {"GS", "LAL"})
        self.assertEqual(ev["G-26NOV19GSWLAL"]["t"], datetime(2026, 11, 20, 1, 0, tzinfo=timezone.utc))

    def test_candle_mid_takes_the_last_candle_before_the_start(self):
        c = lambda ts, b, a, last: dict(end_period_ts=ts, yes_bid={"close_dollars": b}, yes_ask={"close_dollars": a}, price={"close_dollars": last})  # noqa: E731
        candles = [c(1000, "0.60", "0.62", "0.61"), c(4600, "0.66", "0.68", "0.67"), c(8200, "0.95", "0.97", "0.96")]  # the third is in play
        self.assertEqual(pw.candle_mid(candles, 5000), (0.67, 4600))
        self.assertEqual(pw.candle_mid(candles, 900), (None, None))
        self.assertEqual(pw.candle_mid([c(1000, "0.10", "0.90", "0.58")], 5000), (0.58, 1000))  # wide book: last trade


class Model(unittest.TestCase):
    def league(self, n=10, seed=1, days=30, noise=0.0):
        rng = random.Random(seed)
        teams = [f"T{i}" for i in range(n)]
        true = {t: rng.gauss(0, 0.6) for t in teams}
        mean = sum(true.values()) / n
        true = {t: v - mean for t, v in true.items()}
        games = []
        for d in range(days):
            order = teams[:]
            rng.shuffle(order)
            for i in range(0, n - 1, 2):
                h, a = order[i], order[i + 1]
                games.append(dict(home=h, away=a, neutral=0, start=NOW - timedelta(days=d, hours=1), b2b=0, y=true[h] - true[a] + 0.25 + rng.gauss(0, noise)))
        return teams, true, games

    def test_fit_recovers_ratings_and_home_advantage(self):
        teams, true, games = self.league()
        m = pw.fit(games, teams, NOW, half_life=10.0)
        self.assertAlmostEqual(sum(m["ratings"].values()), 0.0, places=9)
        self.assertAlmostEqual(m["home"], 0.25, places=2)
        for t in teams:
            self.assertAlmostEqual(m["ratings"][t], true[t], delta=0.03)
        self.assertLess(m["rmse"], 0.02)
        self.assertAlmostEqual(pw.predict(m, "T0", "T1"), pw.sigmoid(true["T0"] - true["T1"] + 0.25), delta=0.01)
        self.assertAlmostEqual(pw.predict(m, "T0", "T1", neutral=1), pw.sigmoid(true["T0"] - true["T1"]), delta=0.01)

    def test_recent_prices_outweigh_old_ones(self):
        teams, true, games = self.league(noise=0.0)
        for g in games:  # T0 became much better a week ago
            if (NOW - g["start"]).days < 7 and "T0" in (g["home"], g["away"]):
                g["y"] += 1.0 if g["home"] == "T0" else -1.0
        short, long = (pw.fit(games, teams, NOW, half_life=hl)["ratings"]["T0"] for hl in (3.0, 60.0))
        self.assertGreater(short, long)
        self.assertGreater(short - true["T0"], 0.6)

    def test_team_without_games_sits_at_average(self):
        teams, _, games = self.league()
        m = pw.fit(games, teams + ["NEW"], NOW, half_life=10.0)
        self.assertEqual(m["n_eff"]["NEW"], 0.0)
        self.assertAlmostEqual(m["ratings"]["NEW"], -sum(v for t, v in m["ratings"].items() if t != "NEW"), places=9)

    def test_back_to_back_is_separated_from_the_rating(self):
        teams, true, games = self.league()
        rng = random.Random(7)
        for g in games:
            g["b2b"] = rng.choice((-1, 0, 0, 1))
            g["y"] -= 0.3 * g["b2b"]
        m = pw.fit(games, teams, NOW, half_life=10.0, b2b=True)
        self.assertAlmostEqual(m["b2b"], -0.3, delta=0.03)
        self.assertAlmostEqual(m["ratings"]["T3"], true["T3"], delta=0.04)

    def test_add_b2b(self):
        rows = [row("LAL", "LAC", NOW - timedelta(days=3)), row("PHI", "LAL", NOW - timedelta(days=2)), row("LAL", "GS", NOW)]
        pw.add_b2b(rows)
        self.assertEqual([r["_b2b"] for r in rows], [0, -1, 0])  # LAL, away, played the night before; two days of rest is not one

    def test_enough_is_false_out_of_season(self):
        teams, _, games = self.league()
        self.assertTrue(pw.enough(games, teams, NOW, 10.0))
        self.assertFalse(pw.enough(games, teams, NOW + timedelta(days=120), 10.0))
        rows = [row("LAL", "LAC", NOW - timedelta(days=200), kalshi_p="0.6")]
        self.assertEqual(pw.fit_inputs(rows, NOW, 4, 5.0), [])

    def test_fit_inputs_window(self):
        rows = [row("LAL", "LAC", NOW - timedelta(days=1), kalshi_p="0.6"), row("LAL", "PHI", NOW + timedelta(days=2), kalshi_p="0.6"),
                row("LAL", "GS", NOW + timedelta(days=9), kalshi_p="0.6"), row("PHI", "GS", NOW - timedelta(days=1)),
                row("POR", "GS", NOW - timedelta(days=1), kalshi_p="0.6", state="off"), row("POR", "PHI", NOW - timedelta(days=3), kalshi_p="0.6", state="pre")]
        got = pw.fit_inputs(rows, NOW, 4, 5.0)
        self.assertEqual([(g["home"], g["away"]) for g in got], [("LAL", "LAC"), ("LAL", "PHI")])


class Title(unittest.TestCase):
    def setUp(self):
        self.ratings = {f"T{i}": 0.9 - 0.12 * i for i in range(16)}
        self.playoff = {t: min(0.97, 0.3 + pw.sigmoid(3 * r) * 0.7) for t, r in self.ratings.items()}
        raw = {t: self.playoff[t] * math.exp(2.0 * r) for t, r in self.ratings.items()}
        total = sum(raw.values())
        self.title = {t: v / total for t, v in raw.items()}

    def test_on_the_line_means_no_adjustment(self):
        blend, info = pw.title_blend(self.ratings, self.title, self.playoff, {})
        self.assertAlmostEqual(info["slope"], 2.0, places=6)
        self.assertTrue(all(abs(b["gap"]) < 1e-6 for b in blend.values()))

    def test_team_priced_above_the_line_is_pulled_up_by_a_bounded_amount(self):
        title = dict(self.title, T6=self.title["T6"] * 2.5)
        blend, info = pw.title_blend(self.ratings, title, self.playoff, {})
        self.assertGreater(blend["T6"]["gap"], 0.2)
        self.assertLess(blend["T6"]["gap"], math.log(2.5) / info["slope"] + 1e-9)
        self.assertTrue(all(0 < b["weight"] <= pw.TITLE_WEIGHT and abs(b["gap"]) <= pw.TITLE_CAP for b in blend.values()))
        self.assertGreater(blend["T0"]["weight"], blend["T12"]["weight"])  # long shots count for less

    def test_tick_floor_prices_are_ignored(self):
        title = dict(self.title, T15=0.0018)
        playoff = dict(self.playoff, T14=0.02)
        blend, _ = pw.title_blend(self.ratings, title, playoff, {})
        self.assertNotIn("T15", blend)
        self.assertNotIn("T14", blend)

    def test_skipped_when_futures_do_not_track_ratings(self):
        flat = {t: 1 / 16 for t in self.ratings}
        blend, why = pw.title_blend(self.ratings, flat, {}, {})
        self.assertIsNone(blend)
        self.assertIn("slope", why)
        self.assertIsNone(pw.title_blend(self.ratings, {"T0": 0.5}, {}, {})[0])

    def test_normalise_needs_most_of_the_league(self):
        self.assertIsNone(pw.normalise({"A": 0.2, "B": 0.1}, 30))
        n = pw.normalise({f"T{i}": 0.05 for i in range(24)}, 30)
        self.assertAlmostEqual(sum(n.values()), 1.0)


class Block(unittest.TestCase):
    def test_league_block_shapes_page_data(self):
        teams = pw.Teams(ESPN_TEAMS)
        rng = random.Random(3)
        true = dict(zip(teams.abbrs, (0.8, 0.5, 0.2, 0.0, -0.2, -0.3, -0.4, -0.6)))
        rows = []
        for d in range(-3, 25):
            order = teams.abbrs[:]
            rng.shuffle(order)
            for i in range(0, 8, 2):
                h, a = order[i], order[i + 1]
                p = pw.sigmoid(true[h] - true[a] + 0.2)
                rows.append(row(h, a, NOW - timedelta(days=d, hours=3), kalshi_p=f"{p:.4f}", polymarket_p=f"{p:.4f}"))
        raw = {t: math.exp(2 * r) for t, r in true.items()}
        board = {t: v / sum(raw.values()) for t, v in raw.items()}
        hist = {}
        with mock.patch.dict(pw.LEAGUES["nba"], {"points": False}):
            b = pw.league_block("nba", pw.LEAGUES["nba"], rows, teams, {t: dict(conf="West", record="5-5") for t in teams.abbrs},
                                {"kalshi": board, "polymarket": board, "pinnacle": {}}, {}, hist, NOW)
        json.dumps(b)
        self.assertEqual([t["rank"] for t in b["teams"]], list(range(1, 9)))
        self.assertEqual([t["abbr"] for t in b["teams"]], sorted(true, key=true.get, reverse=True))
        self.assertTrue(all(0 < t["wp"] < 1 and t["spark"] for t in b["teams"]))
        self.assertAlmostEqual(sum(pw.logit(t["wp"]) for t in b["teams"]), 0.0, places=2)
        self.assertEqual(b["title"]["sources"], ["kalshi", "polymarket"])
        self.assertEqual(b["games_upcoming"], len(b["games"]))
        self.assertTrue(all(g["start_utc"] > pw.iso(NOW) for g in b["games"]))
        self.assertEqual(len({d for d, _, _ in hist}), len({k[0] for k in hist}))
        self.assertIn((NOW.strftime("%Y-%m-%d"), "nba", "LAL"), hist)

    def test_too_few_priced_games_returns_none(self):
        teams = pw.Teams(ESPN_TEAMS)
        rows = [row("LAL", "LAC", NOW - timedelta(days=1), kalshi_p="0.6")]
        self.assertIsNone(pw.league_block("nba", pw.LEAGUES["nba"], rows, teams, {}, {}, {}, {}, NOW))


if __name__ == "__main__":
    unittest.main()
