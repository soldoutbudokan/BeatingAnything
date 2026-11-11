# %% Minutes / rotation projection
"""
For each player on an end-of-2026 roster:
  avail      decayed share of healthy team games played (coach's-decision DNPs count, injury DNPs don't)
  role_min   decayed mean minutes in games she played for her current team (half-life 6 games, 2026 only;
             falls back to all 2026 games, then to 2025, then 0)
  start_rate decayed share of those games started (half-life 6 games)
  min_sd     sd of game minutes around the decayed mean (shrunk toward 5.5 with 8 pseudo-games)
Default rotation: allocate 200 minutes as c*(role_min*avail)**gamma with a 38-minute cap (see allocate);
starters = top-5 start_rate with at least one guard and at most two centres.
Also exports the most-used five-player lineups per team in 2026 (possessions, net per 100).
Output: data/processed/wnba/rotations.parquet, lineups.parquet
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from models.wnba.common import PROC

CUR = 2026
HL_GAMES = 6.0
CAP = 38.0


def scale_to_total(m, total=200.0, cap=CAP):
    m = np.asarray(m, float)
    if m.sum() <= 0:
        return m
    lo, hi = 0.0, 10.0
    for _ in range(60):
        s = (lo + hi) / 2
        if np.minimum(m * s, cap).sum() > total:
            hi = s
        else:
            lo = s
    return np.minimum(m * lo, cap)


def allocate(x, total=200.0, cap=CAP):
    """m = c * x**gamma (capped), gamma the smallest value in [1, 2] that keeps the team's top-3 players at
    >= 95% of their role minutes: when everyone is healthy, bench minutes (inflated by injuries to others)
    are squeezed more than starters'."""
    x = np.asarray(x, float)
    top = np.argsort(-x)[:3]
    for gam in np.arange(1.0, 2.01, 0.1):
        m = scale_to_total(np.where(x > 0, x ** gam, 0.0), total, cap)
        if np.all(m[top] >= 0.95 * np.minimum(x[top], cap)):
            return m, float(gam)
    return m, 2.0


def pick_starters(df):
    d = df.sort_values(["start_rate", "role_min"], ascending=False)
    chosen = []
    for r in d.itertuples():
        if len(chosen) == 5:
            break
        grp = [x.pos_group for x in chosen]
        if r.pos_group == "C" and grp.count("C") >= 2:
            continue
        if len(chosen) == 4 and "G" not in grp and r.pos_group != "G":
            continue
        chosen.append(r)
    return {r.pid for r in chosen}


def main(force=False):
    out = PROC / "rotations.parquet"
    if out.exists() and not force:
        print("minutes: cached")
        return
    pg = pd.read_parquet(PROC / "player_games.parquet")
    games = pd.read_parquet(PROC / "games.parquet")[["game_id", "dt", "season"]]
    pg = pg[pg.pid > 0].drop(columns=["season"]).merge(games, on="game_id")
    bio = pd.read_parquet(PROC / "players_bio.parquet")
    from models.wnba.common import RAW
    rb = pd.read_parquet(RAW / f"player_box_{CUR}.parquet")[["game_id", "athlete_id", "team_id", "minutes", "did_not_play", "reason"]]
    rb = rb.merge(games, on="game_id").sort_values("dt")
    rb["coach_dnp"] = rb.did_not_play.fillna(False) & rb.reason.fillna("").str.startswith("COACH")
    rb["played"] = rb.minutes.fillna(0) > 0
    rb = rb[rb.played | rb.coach_dnp]  # healthy-and-available games only
    ros = bio[bio.team.notna()].copy()
    ros["team"] = ros.team.astype(int)
    rows = []
    for r in ros.itertuples():
        g = pg[(pg.pid == r.pid) & (pg.minutes.fillna(0) > 0)].sort_values("dt")
        src = "none"
        for sel, lab in ((g[(g.season == CUR) & (g.team_id == r.team)], "2026_team"), (g[g.season == CUR], "2026_any"),
                         (g[g.season == CUR - 1], "2025")):
            if len(sel):
                g2, src = sel, lab
                break
        else:
            g2 = g.iloc[0:0]
        if len(g2):
            n = len(g2)
            w = 0.5 ** ((n - 1 - np.arange(n)) / HL_GAMES)
            mins = g2.minutes.values.astype(float)
            role = float(np.sum(w * mins) / w.sum())
            st = float(np.sum(w * g2.starter.fillna(False).astype(float).values) / w.sum())
            var = float(np.sum(w * (mins - role) ** 2) / w.sum())
            neff = w.sum() ** 2 / np.sum(w ** 2)
            sd = float(np.sqrt((var * neff + 5.5 ** 2 * 8) / (neff + 8)))
            gp_cur = int(((g.season == CUR) & (g.team_id == r.team)).sum())
        else:
            role, st, sd, gp_cur = 0.0, 0.0, 5.5, 0
        # healthy availability: decayed share of healthy team games (played or coach's-decision DNP) she played
        hb = rb[(rb.athlete_id == r.pid) & (rb.team_id == r.team)]
        if len(hb):
            n = len(hb)
            w = 0.5 ** ((n - 1 - np.arange(n)) / 10.0)
            avail = float(np.sum(w * hb.played.values) / w.sum())
        else:
            avail = 1.0 if role > 0 else 0.0
        rows.append(dict(pid=r.pid, team=r.team, name=r.name, pos_group=r.pos_group, role_min=role, start_rate=st,
                         min_sd=sd, gp_2026_team=gp_cur, minutes_source=src, avail=avail))
    R = pd.DataFrame(rows)
    # role minutes from 2025 only (players who missed 2026) are discounted by half: role is stale
    R.loc[R.minutes_source == "2025", "role_min"] *= 0.5
    out_rows = []
    for t, d in R.groupby("team"):
        d = d.copy()
        d["proj_min"], d["gamma"] = allocate(d.role_min.values * d.avail.values)
        st = pick_starters(d[d.proj_min > 0])
        d["starter"] = d.pid.isin(st)
        out_rows.append(d)
    R = pd.concat(out_rows)
    R.to_parquet(out)
    # lineups used in 2026
    poss = pd.read_parquet(PROC / "possessions.parquet")
    poss = poss[(poss.season == CUR) & ~poss.is_empty & poss.lineup_ok]
    rows = []
    for side, team_col, sgn in (("o", "off_team", 1), ("d", "def_team", -1)):
        L = np.sort(poss[[f"{side}{k}" for k in range(5)]].values, axis=1)
        key = pd.Series([",".join(map(str, x)) for x in L], index=poss.index)
        rows.append(pd.DataFrame({"team": poss[team_col].astype(int).values, "lineup": key.values,
                                  "pts": sgn * poss.pts.values, "off": side == "o"}))
    L = pd.concat(rows)
    agg = L.groupby(["team", "lineup"]).agg(poss=("pts", "size"), net=("pts", "sum")).reset_index()
    agg["net100"] = agg.net / agg.poss * 100 * 2  # both ends counted -> per 100 of each
    agg["poss"] = agg.poss / 2
    agg = agg.sort_values(["team", "poss"], ascending=[True, False]).groupby("team").head(10)
    agg.to_parquet(PROC / "lineups.parquet")
    print(f"minutes: {len(R)} roster players, teams={R.team.nunique()}, rotation players (>=10 min): {(R.proj_min >= 10).sum()}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
