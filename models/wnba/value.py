# %% Bottom-up team ratings and player value above replacement
"""
Team rating (per 100 possessions) from a rotation m_i (minutes, sum 200):
    ORtg = lg + sum_i (m_i/40) O_i,   DRtg = lg - sum_i (m_i/40) D_i,   Net = ORtg - DRtg
Replacement level = minutes-weighted mean total impact (O+D) of players ranked 166th+ in 2026 minutes
(beyond ~11 per team). VARP/100 = (O + D) - replacement.
Season value: points = VARP/100 * on-court possessions (proj minutes/40 * team possessions * 44 games);
wins = points / points-per-win (slope of team wins on season point differential, 2017-2026).
Game impact of removing a player: rotation re-allocated (sim.reallocate), team net change, and the
win-probability change vs a league-average opponent on a neutral floor, using a normal margin
approximation with the simulator's margin SD.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from models.wnba.common import PROC
from models.wnba.sim import Team, reallocate

GAMES = 44


def team_rating(prm, T):
    lg = prm["league"]["ortg"]
    w = T.minutes / 40.0
    o = lg + float((w * T.O).sum())
    d = lg - float((w * T.D).sum())
    return o, d, o - d


def analytic_pace(prm, T):
    """Possessions per 40 minutes vs a league-average opponent (first play + ORB plays)."""
    w = T.minutes / 40.0
    tid = str(T.tid)
    fp = prm["pace"]["first_play_sec"] + float((w * T.pace_o).sum()) + prm["pace"]["team_off"].get(tid, 0)
    fd = prm["pace"]["first_play_sec"] + float((w * T.pace_d).sum()) + prm["pace"]["team_def"].get(tid, 0)
    orb = prm["league"]["orb_rate"] * 0.55  # ~ORB plays per possession
    sec = 0.5 * (fp + fd) + orb * prm["pace"]["orb_play_sec"]
    return 2400.0 / sec / 2.0  # possessions per team per 40 minutes (the two teams alternate)


def pts_per_win():
    g = pd.read_parquet(PROC / "games.parquet").dropna(subset=["home_pts"])
    g = g[g.season_type == 2]
    rows = []
    for side, opp in (("home", "away"), ("away", "home")):
        rows.append(pd.DataFrame({"team": g[side], "season": g.season, "diff": g[f"{side}_pts"] - g[f"{opp}_pts"],
                                  "win": (g[f"{side}_pts"] > g[f"{opp}_pts"]).astype(float)}))
    t = pd.concat(rows).groupby(["team", "season"]).agg(diff=("diff", "sum"), win=("win", "sum"), n=("win", "size"))
    x = t["diff"].values
    y = t.win.values - t.n.values / 2
    slope = float(np.sum(x * y) / np.sum(x * x))
    return 1.0 / slope


def replacement_level(prm):
    pg = pd.read_parquet(PROC / "player_games.parquet")
    m26 = pg[pg.season == 2026].groupby("pid").minutes.sum().sort_values(ascending=False)
    P = {p["id"]: p for p in prm["players"]}
    tail = m26.iloc[165:]
    tail = tail[tail.index.isin(P.keys()) & (tail > 0)]
    tot = np.array([P[i]["O"] + P[i]["D"] for i in tail.index])
    return float(np.average(tot, weights=tail.values)), int(len(tail))


def player_values(prm, margin_sd=13.0):
    repl, n_repl = replacement_level(prm)
    ppw = pts_per_win()
    P = prm["players"]
    poss = prm["league"]["poss_per_team_game"]
    out = {}
    teams = {}
    for t in prm["teams"]:
        T = Team(prm, t["id"])
        teams[t["id"]] = (T, team_rating(prm, T))
    for p in P:
        tot = p["O"] + p["D"]
        varp = tot - repl
        on_poss = p["min"] / 40.0 * poss * GAMES
        pts = varp / 100.0 * on_poss
        rec = dict(varp100=varp, varp_pts=pts, varp_wins=pts / ppw)
        if p["team"] in teams and p["min"] > 0:
            T, (o, d, n) = teams[p["team"]]
            outm = T.ids == p["id"]
            m2 = reallocate(T.minutes, T.posg, outm, cap=prm["sim"]["realloc_cap"])
            w = m2 / 40.0
            lg = prm["league"]["ortg"]
            o2 = lg + float((w * T.O).sum())
            d2 = lg - float((w * T.D).sum())
            rec.update(off_delta=o2 - o, def_delta=d2 - d, net_delta=(o2 - d2) - n)
            mu1 = n * poss / 100.0
            mu2 = (o2 - d2) * poss / 100.0
            rec["winp_delta"] = float(norm.cdf(mu2 / margin_sd) - norm.cdf(mu1 / margin_sd))
        out[p["id"]] = rec
    return out, dict(replacement_per100=repl, n_replacement_players=n_repl, pts_per_win=ppw, games=GAMES), teams
