#!/usr/bin/env python3
"""Value of bet365's standing moneyline Early Payout (NFL/NCAAF 17+, NBA 20+) from play-by-play.

python tools/explore_early_payout.py
First run downloads nflverse NFL pbp 2006-2025, ESPN NBA pbp 2012-2025 (sportsdataverse) and
cfbfastR college pbp 2012-2021 (streamed; only per-game max leads are kept), plus college lines.
Writes reports/early-payout-2026-09-22.json. No wagers.

A bet that loses or ties but whose team led by the threshold at any point pays as a win, so the
promo adds P(lead >= threshold and not win). A bet is +EV when decimal * (p_fair + extra) > 1.
"""
# %% setup
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/early-payout"
NFL_GAMES = ROOT / "data/raw/nfl-teasers/games.csv"  # from tools/explore_nfl_teasers.py (nflverse 62997a7)
CFB_COMMIT = "3fd6249bd5eee46cbadec294e21f72e0f6bcc3d8"
OUT = ROOT / "reports/early-payout-2026-09-22.json"
BINS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]


def get(url, dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sS", "-L", "--fail", "-o", str(dest), url], check=True)
    return dest


def implied(ml):
    return np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))


def decimal(ml):
    return np.where(ml < 0, 1 + 100 / (-ml), 1 + ml / 100)


def american(dec):
    return int(round(100 * (dec - 1))) if dec >= 2 else int(round(-100 / (dec - 1)))


def two_sides(p_home, home_max, home_min, res, season, **extra_cols):
    """One row per team: fair win prob, largest lead reached, won (ties count as not won)."""
    home = pd.DataFrame(dict(season=season, p=p_home, maxlead=home_max, won=res > 0, **{k: v[0] for k, v in extra_cols.items()}))
    away = pd.DataFrame(dict(season=season, p=1 - p_home, maxlead=-home_min, won=res < 0, **{k: v[1] for k, v in extra_cols.items()}))
    return pd.concat([home, away], ignore_index=True)


def curve(S, threshold):
    """Promo conversion rate by fair-probability bucket and the lowest bet365 price that still breaks even."""
    S = S.assign(extra=(S.maxlead >= threshold) & ~S.won)
    rows = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        x = S[(S.p > lo) & (S.p <= hi)]
        p, e = x.p.mean(), x.extra.mean()
        rows.append({"fair_prob": f"{lo:.1f}-{hi:.1f}", "team_games": len(x), "extra": round(e, 4),
                     "se": round(np.sqrt(e * (1 - e) / len(x)), 4), "lift_vs_win_prob": round(e / p, 3),
                     "fair_odds": american(1 / p), "breakeven_bet365_odds": american(1 / (p + e)),
                     "max_price_discount": round(e / (p + e), 3)})
    return rows


# %% NFL: nflverse pbp max leads + closing consensus moneylines
leads = []
for y in range(2006, 2026):
    f = get(f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{y}.parquet", RAW / f"nfl-pbp/pbp_{y}.parquet")
    t = pq.read_table(f, columns=["game_id", "total_home_score", "total_away_score"]).to_pandas()
    leads.append(t.assign(d=t.total_home_score - t.total_away_score).groupby("game_id").d.agg(home_max="max", home_min="min"))
g = pd.read_csv(NFL_GAMES)
g = g[g.result.notna() & g.home_moneyline.notna() & g.away_moneyline.notna()].merge(pd.concat(leads).reset_index(), on="game_id")
ph, pa = implied(g.home_moneyline), implied(g.away_moneyline)
nfl = two_sides(ph / (ph + pa), g.home_max, g.home_min, np.sign(g.result), g.season,
                d=(decimal(g.home_moneyline), decimal(g.away_moneyline)), tie=((g.result == 0).values,) * 2)
nfl["trig"] = nfl.maxlead >= 17
nfl["ret_plain"] = np.where(nfl.won, nfl.d - 1, np.where(nfl.tie, 0.0, -1.0))
nfl["ret_promo"] = np.where(nfl.won | nfl.trig, nfl.d - 1, np.where(nfl.tie, 0.0, -1.0))
dogs = nfl[nfl.d >= 2.3]  # +130 and longer
nfl_consensus_prices = {"bets": len(dogs), "roi_plain": round(dogs.ret_plain.mean(), 4), "roi_with_payout": round(dogs.ret_promo.mean(), 4),
                        "se": round(dogs.ret_promo.std() / np.sqrt(len(dogs)), 4)}
print("NFL dogs +130+, consensus closing prices:", nfl_consensus_prices)

# %% NBA: ESPN pbp (pregame spread on every play row); win prob from a logistic fit on the spread
leads = []
for y in range(2012, 2026):
    f = get(f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_pbp/play_by_play_{y}.parquet", RAW / f"nba-pbp/pbp_{y}.parquet")
    t = pq.read_table(f, columns=["game_id", "season", "season_type", "home_score", "away_score", "game_spread", "home_favorite", "game_spread_available"]).to_pandas()
    t["d"] = t.home_score - t.away_score
    leads.append(t.groupby("game_id").agg(season=("season", "first"), st=("season_type", "first"), home_max=("d", "max"), home_min=("d", "min"),
                                          hs=("home_score", "max"), as_=("away_score", "max"), spread=("game_spread", "first"),
                                          hfav=("home_favorite", "first"), avail=("game_spread_available", "first")))
G = pd.concat(leads).reset_index()
G = G[G.st.isin([2, 3]) & G.avail.fillna(False).astype(bool) & (G.hs != G.as_) & (G.hs > 50)]
home_line = np.where(G.hfav, -G.spread.abs(), G.spread.abs())  # points the home team receives
won = (G.hs > G.as_).values
def nll(b):
    p = 1 / (1 + np.exp(b[0] * home_line))
    return -np.sum(np.log(np.clip(np.where(won, p, 1 - p), 1e-9, 1)))


slope = minimize(nll, [0.1]).x[0]
nba = two_sides(1 / (1 + np.exp(slope * home_line)), G.home_max.values, G.home_min.values, np.sign(G.hs - G.as_).values, G.season.values)
print("NBA games", len(G), "logit slope per point", round(slope, 4))

# %% NCAAF: cfbfastR pbp max leads (streamed), consensus moneylines across books, bet365 vs Pinnacle prices
cfb_dir = RAW / "cfb"
lines = get(f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/{CFB_COMMIT}/betting/csv/cfb_line_odds.csv.gz", cfb_dir / "cfb_line_odds.csv.gz")
sched = pd.concat([pd.read_csv(get(f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/{CFB_COMMIT}/schedules/csv/cfb_schedules_{y}.csv", cfb_dir / f"cfb_sched_{y}.csv"))
                   for y in range(2012, 2022)])[["game_id", "season", "home_points", "away_points"]]
max_leads = cfb_dir / "cfb_max_leads_2012_2021.csv"
if not max_leads.exists():
    out = []
    for y in range(2012, 2022):
        f = get(f"https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/{CFB_COMMIT}/pbp/parquet/play_by_play_{y}.parquet", cfb_dir / f"pbp_{y}.parquet")
        t = pq.read_table(f, columns=["game_id", "homeScore", "awayScore"]).to_pandas()
        t["d"] = t.homeScore - t.awayScore
        out.append(t.groupby("game_id").d.agg(home_max="max", home_min="min").reset_index().assign(season=y))
        os.remove(f)  # ~56 MB each; only max leads are kept
    pd.concat(out).to_csv(max_leads, index=False)
d = pd.read_csv(lines)
pairs = pd.concat([d[["game_id", "abbr", "home_team_id"]].rename(columns={"home_team_id": "tid"}),
                   d[["game_id", "abbr", "away_team_id"]].rename(columns={"away_team_id": "tid"})]).drop_duplicates()
d["tid"] = d.abbr.map(pairs.groupby(["abbr", "tid"]).size().reset_index(name="n").sort_values("n", ascending=False).drop_duplicates("abbr").set_index("abbr").tid)
ml = d[(d.market_type == "money_line") & d.odds.notna()].copy()
ml["is_home"] = ml.tid == ml.home_team_id
ml = ml[ml.is_home | (ml.tid == ml.away_team_id)]
w = ml.pivot_table(index=["game_id", "book"], columns="is_home", values="odds", aggfunc="first").dropna().reset_index()
w.columns = ["game_id", "book", "away_ml", "home_ml"]
w["ph"], w["pa"] = implied(w.home_ml), implied(w.away_ml)
w = w[(w.ph + w.pa - 1).between(0, 0.15)]
w["p_home"] = w.ph / (w.ph + w.pa)
games = pd.read_csv(max_leads).merge(sched, on=["game_id", "season"])
games = games[games.home_points.notna()]
cons = games.merge(w.groupby("game_id").p_home.median().reset_index(), on="game_id")
cfb = two_sides(cons.p_home, cons.home_max, cons.home_min, np.sign(cons.home_points - cons.away_points), cons.season)

# bet365's actual college prices (2012-2019) against Pinnacle's no-vig price at the same capture
b = w[w.book.isin(["bet365", "PINNACLE"])].pivot_table(index="game_id", columns="book", values=["home_ml", "away_ml"]).dropna()
b.columns = [f"{m}_{bk}" for m, bk in b.columns]
b = b.reset_index().merge(games, on="game_id")
pin_h, pin_a = implied(b.home_ml_PINNACLE), implied(b.away_ml_PINNACLE)
b = b[((pin_h + pin_a - 1) >= 0) & ((pin_h + pin_a - 1) <= 0.08)]
pin_h, pin_a = implied(b.home_ml_PINNACLE), implied(b.away_ml_PINNACLE)
B = two_sides(pin_h / (pin_h + pin_a), b.home_max, b.home_min, np.sign(b.home_points - b.away_points), b.season,
              d=(decimal(b.home_ml_bet365), decimal(b.away_ml_bet365)))
B["trig"] = B.maxlead >= 17
B["shade"] = B.d * B.p - 1
B["ret_plain"] = np.where(B.won, B.d - 1, -1.0)
B["ret_promo"] = np.where(B.won | B.trig, B.d - 1, -1.0)
train = cfb[cfb.season <= 2015].assign(extra=lambda x: (x.maxlead >= 17) & ~x.won)
edges = np.linspace(0, 1, 11)
rate = train.groupby(pd.cut(train.p, edges), observed=False).extra.mean().values
B["ev_hat"] = (B.p + np.interp(B.p, (edges[:-1] + edges[1:]) / 2, rate)) * B.d - 1
bet365_by_prob = []
for lo, hi in zip(BINS[:-1], BINS[1:]):
    x = B[(B.p > lo) & (B.p <= hi)]
    e = ((x.maxlead >= 17) & ~x.won).mean()
    bet365_by_prob.append({"fair_prob": f"{lo:.1f}-{hi:.1f}", "team_games": len(x), "bet365_vs_fair": round(x.shade.mean(), 4),
                           "extra": round(e, 4), "expected_ev_with_payout": round(((x.p + e) * x.d - 1).mean(), 4),
                           "realized_roi_plain": round(x.ret_plain.mean(), 4), "realized_roi_with_payout": round(x.ret_promo.mean(), 4)})
test = B[B.season >= 2016]
bet365_test = {}
for thr in (0.0, 0.02, 0.04):
    x = test[test.ev_hat > thr]
    bet365_test[f"ev_hat>{thr}"] = {"bets": len(x), "mean_ev_hat": round(x.ev_hat.mean(), 4), "roi_plain": round(x.ret_plain.mean(), 4),
                                    "roi_with_payout": round(x.ret_promo.mean(), 4), "se": round(x.ret_promo.std() / np.sqrt(len(x)), 4)}
print(pd.DataFrame(bet365_by_prob).to_string(index=False))
print(json.dumps(bet365_test, indent=1))

# %% decision tables
tables = {"NFL 17+ (2006-2025)": curve(nfl, 17), "NFL 17+ (2016-2025)": curve(nfl[nfl.season >= 2016], 17),
          "NCAAF 17+ (2012-2021)": curve(cfb, 17), "NBA 20+ (2012-2025)": curve(nba, 20), "NBA 20+ (2019-2025)": curve(nba[nba.season >= 2019], 20)}
for k, v in tables.items():
    print(k)
    print(pd.DataFrame(v).to_string(index=False))

# %% save
OUT.write_text(json.dumps({
    "rules": "bet365 standing Early Payout on pre-game moneylines: NFL/NCAAF 17+, NBA 20+ (verify current terms in-app)",
    "sources": {"nfl": "nflverse pbp releases + nfldata games.csv 62997a7 closing moneylines",
                "nba": "sportsdataverse espn_nba_pbp releases (pregame spread per game)",
                "ncaaf": f"sportsdataverse/cfbfastR-data {CFB_COMMIT}: pbp, schedules, cfb_line_odds"},
    "decision_tables": tables, "nfl_dogs_at_consensus_prices": nfl_consensus_prices,
    "ncaaf_bet365_vs_pinnacle_2012_2019": bet365_by_prob, "ncaaf_bet365_test_2016_2019": bet365_test}, indent=2, default=float) + "\n")
print("wrote", OUT.relative_to(ROOT))
