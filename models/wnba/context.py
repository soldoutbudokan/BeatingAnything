# %% Home court, rest / back-to-back and travel effects from game results (2017-2026)
"""
margin_home = HCA*(not neutral) + b2b*(B2B_h - B2B_a) + rest*(R_h - R_a) + travel*(miles_h - miles_a)/1000
              + tz*(|tz shift|_h - |tz shift|_a) + s_home,season - s_away,season + e
Team-season strengths are ridge-penalised (lambda = 4 games). R = min(days since last game, 4) - 1.
miles / tz shift = distance and time-zone change from the city of the team's previous game.
Output: data/processed/wnba/context.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from models.wnba.common import CITY, PROC, haversine_miles


def city_of(abbr, team_id, season):
    if team_id == 17 and season == 2017:
        return CITY["SA"]
    return CITY.get({"CONN": "CON"}.get(abbr, abbr))


def main(force=False):
    out = PROC / "context.json"
    if out.exists() and not force:
        print("context: cached")
        return
    g = pd.read_parquet(PROC / "games.parquet").dropna(subset=["home_pts", "away_pts"])
    g["dt"] = pd.to_datetime(g.dt, utc=True)
    g["day"] = g.dt.dt.tz_convert("America/New_York").dt.normalize()
    g["host_city"] = [city_of(a, h, s) for a, h, s in zip(g.home_abbr, g.home, g.season)]
    tg = pd.concat([g.assign(team=g.home, side="h"), g.assign(team=g.away, side="a")]).sort_values("dt")
    tg["prev_day"] = tg.groupby(["team", "season"]).day.shift(1)
    tg["prev_city"] = tg.groupby(["team", "season"]).host_city.shift(1)
    tg["rest_days"] = (tg.day - tg.prev_day).dt.days
    tg["b2b"] = (tg.rest_days == 1).astype(float)
    tg["rest"] = tg.rest_days.fillna(4).clip(1, 4) - 1
    tg["miles"] = [haversine_miles(p, c) if isinstance(p, tuple) else 0.0 for p, c in zip(tg.prev_city, tg.host_city)]
    tg["tz"] = [abs(c[2] - p[2]) if isinstance(p, tuple) else 0.0 for p, c in zip(tg.prev_city, tg.host_city)]
    f = tg.pivot_table(index="game_id", columns="side", values=["b2b", "rest", "miles", "tz"])
    f.columns = [f"{a}_{b}" for a, b in f.columns]
    g = g.set_index("game_id").join(f).reset_index()
    y = (g.home_pts - g.away_pts).values.astype(float)
    ts_h = g.home.astype(str) + "_" + g.season.astype(str)
    ts_a = g.away.astype(str) + "_" + g.season.astype(str)
    idx = pd.Index(sorted(set(ts_h) | set(ts_a)))
    n, T = len(g), len(idx)
    Xt = np.zeros((n, T))
    Xt[np.arange(n), idx.get_indexer(ts_h)] = 1
    Xt[np.arange(n), idx.get_indexer(ts_a)] = -1
    neutral = g.neutral_site.fillna(False).astype(bool).values
    Xc = np.c_[(~neutral).astype(float), g.b2b_h - g.b2b_a, g.rest_h - g.rest_a, (g.miles_h - g.miles_a) / 1000.0, g.tz_h - g.tz_a]
    names = ["hca", "b2b", "rest_day", "travel_per_1000mi", "tz_shift"]
    X = np.c_[Xc, Xt]
    L = np.r_[np.zeros(Xc.shape[1]) + 1e-6, np.full(T, 4.0)]
    A = X.T @ X + np.diag(L)
    beta = np.linalg.solve(A, X.T @ y)
    resid = y - X @ beta
    s2 = resid.var()
    se = np.sqrt(np.diag(np.linalg.inv(A)) * s2)
    res = {k: dict(coef=float(beta[i]), se=float(se[i])) for i, k in enumerate(names)}
    # totals: does home/b2b change total scoring?
    yt = (g.home_pts + g.away_pts).values.astype(float)
    Xtot = np.c_[np.ones(n), g.b2b_h + g.b2b_a, g.season.values - 2026.0]
    bt = np.linalg.lstsq(Xtot, yt, rcond=None)[0]
    res["total_b2b_per_team"] = float(bt[1])
    res["n_games"] = int(n)
    res["home_win_rate"] = float((y > 0).mean())
    res["home_margin_mean"] = float(y.mean())
    res["b2b_share"] = float(((g.b2b_h + g.b2b_a) > 0).mean())
    res["resid_sd"] = float(np.sqrt(s2))
    out.write_text(json.dumps(res, indent=1))
    print("context:", {k: (round(v["coef"], 2), round(v["se"], 2)) for k, v in res.items() if isinstance(v, dict)})


if __name__ == "__main__":
    main(force="--force" in sys.argv)
