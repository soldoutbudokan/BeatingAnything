# %% Re-simulation of real games with actual players/minutes + calibration tables
"""
resim(): simulate each real game with the players who played, their actual minutes (scaled to 200) and
actual starters; returns per player-game simulated means (and per-game score draws).
player_calibration(): bins player-games by projected (simulated mean) value -> deciles and usage tiers,
compares simulated vs actual means, OLS slope/intercept of actual on projected.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models.wnba.common import PROC
from models.wnba.sim import SI, simulate

CAL_STATS = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "three_point_field_goals_made",
             "fta": "free_throws_attempted", "fga": "field_goals_attempted", "tov": "turnovers", "stl": "steals",
             "blk": "blocks", "min": "minutes"}


def game_specs(prm, pg, gid, home, away):
    known = {p["id"] for p in prm["players"]}
    specs = []
    for tid in (home, away):
        d = pg[(pg.game_id == gid) & (pg.team_id == tid) & (pg.minutes.fillna(0) > 0) & pg.pid.isin(known)]
        if len(d) < 5:
            return None
        m = d.minutes.values.astype(float)
        m = m * 200.0 / m.sum()
        specs.append({"team": int(tid), "players": [{"id": int(i), "min": float(x), "starter": bool(s)}
                                                     for i, x, s in zip(d.pid, m, d.starter.fillna(False))]})
    return specs


def resim(prm, games, n_sims=300, keep_draws=True):
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[pg.game_id.isin(games.game_id)]
    prow, grow = [], []
    for g in games.itertuples():
        sp = game_specs(prm, pg, g.game_id, g.home, g.away)
        if sp is None:
            continue
        neutral = bool(g.neutral_site) if pd.notna(g.neutral_site) else False
        r = simulate(prm, sp[0], sp[1], n_sims=n_sims, seed=int(g.game_id) % 100000, opts={"neutral": neutral})
        sc = r["score"]
        q = r["quarters"]
        grow.append(dict(game_id=g.game_id, season=g.season, h=sc[:, 0].astype(np.int16), a=sc[:, 1].astype(np.int16),
                         poss=r["n_poss"] / 2, ot=(q[:, 4:].sum((1, 2)) > 0),
                         q1=q[:, 0].sum(1), h1=q[:, :2].sum((1, 2)), h2=q[:, 2:].sum((1, 2)),
                         hq=q[:, :4, 0], aq=q[:, :4, 1]))
        b = r["box"]
        for side, T in ((0, r["home"]), (1, r["away"])):
            off = 0 if side == 0 else r["home"].n
            for i in range(T.n):
                k = off + i
                x = dict(pts=b[SI["pts"], :, k], reb=b[SI["orb"], :, k] + b[SI["drb"], :, k], ast=b[SI["ast"], :, k],
                         fg3m=b[SI["fg3m"], :, k], fta=b[SI["fta"], :, k], fga=b[SI["fga"], :, k], tov=b[SI["tov"], :, k],
                         stl=b[SI["stl"], :, k], blk=b[SI["blk"], :, k], min=b[SI["sec"], :, k] / 60)
                rec = dict(game_id=g.game_id, season=g.season, pid=int(T.ids[i]), team=T.tid, spec_min=float(T.minutes[i]))
                for s, v in x.items():
                    rec[f"sim_{s}"] = float(v.mean())
                rec["sim_pts_sd"] = float(x["pts"].std())
                rec["sim_p20"] = float((x["pts"] >= 20).mean())
                rec["sim_p30"] = float((x["pts"] >= 30).mean())
                if keep_draws:
                    rec["draw_pts"] = x["pts"][:40].astype(np.int16)
                prow.append(rec)
    P = pd.DataFrame(prow)
    act = pg[["game_id", "pid"] + list(CAL_STATS.values())].rename(columns={v: f"act_{k}" for k, v in CAL_STATS.items()})
    P = P.merge(act, on=["game_id", "pid"], how="left")
    return P, grow


def player_calibration(P, usg):
    """Tables by decile of projected value and by usage tier. usg: {pid: projected usage}."""
    out = {}
    P = P.copy()
    P["usg"] = P.pid.map(usg).fillna(0.18)
    P["tier"] = pd.cut(P.usg, [0, 0.16, 0.20, 0.24, 0.28, 1.0], labels=["<16%", "16-20%", "20-24%", "24-28%", "28%+"])
    for s in CAL_STATS:
        x, y = P[f"sim_{s}"].values, P[f"act_{s}"].values
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = x[ok], y[ok]
        slope, icpt = np.polyfit(x, y, 1)
        d = P[ok].assign(dec=pd.qcut(x, 10, labels=False, duplicates="drop"))
        dec = d.groupby("dec").agg(sim=(f"sim_{s}", "mean"), act=(f"act_{s}", "mean"), n=(f"sim_{s}", "size"))
        dec["ratio"] = dec.act / dec.sim.replace(0, np.nan)
        tier = d.groupby("tier", observed=True).agg(sim=(f"sim_{s}", "mean"), act=(f"act_{s}", "mean"), n=(f"sim_{s}", "size"))
        tier["ratio"] = tier.act / tier.sim.replace(0, np.nan)
        out[s] = dict(slope=float(slope), intercept=float(icpt), mean_sim=float(x.mean()), mean_act=float(y.mean()),
                      deciles=dec.reset_index().round(4).to_dict("list"), usage_tiers=tier.reset_index().astype({"tier": str}).round(4).to_dict("list"))
    # tails of points given minutes: players with >= 25 actual min
    d = P[P.act_min >= 25]
    out["pts_tails_25min"] = dict(n=int(len(d)), act_sd_resid=float((d.act_pts - d.sim_pts).std()),
                                  sim_sd_mean=float(np.sqrt((d.sim_pts_sd ** 2).mean())),
                                  share20=[float((d.act_pts >= 20).mean()), float(d.sim_p20.mean())],
                                  share30=[float((d.act_pts >= 30).mean()), float(d.sim_p30.mean())])
    return out


# %% out-of-sample parameters: skills projected at a cut-off, impacts from the pre-2026 RAPM fit
def oos_params(prm, t_cut, age_shift=0.4):
    """Copy of prm whose player skill rates come from data before t_cut (season-time) and whose O/D come
    from the RAPM fit on 2017-25 (rapm_pre2026). Usage strength refit on lineups before t_cut."""
    import copy
    import json

    from models.wnba import skills
    from models.wnba.params import usage_strength
    from models.wnba.common import ZONES, season_bounds, tau
    p2 = copy.deepcopy(prm)
    f, pos, bio = skills.load()
    meta = json.loads((PROC / "skills_meta.json").read_text())
    S = skills.project(f, pos, meta["tuned"], meta["age_curves"], bio, t_cut=t_cut, age_shift=age_shift)
    pre = pd.read_parquet(PROC / "rapm_pre2026.parquet").set_index("pid")
    poss = pd.read_parquet(PROC / "possessions.parquet")
    poss = poss[~poss.is_empty & poss.lineup_ok]
    games = pd.read_parquet(PROC / "games.parquet")
    poss["tau"] = tau(poss.season.values, poss.date.values, season_bounds(games))
    p25 = poss[poss.season == 2025]
    wo = pd.Series(p25[[f"o{k}" for k in range(5)]].values.ravel()).value_counts()
    wd = pd.Series(p25[[f"d{k}" for k in range(5)]].values.ravel()).value_counts()
    O = pre.O - np.average(pre.O.reindex(wo.index).fillna(0), weights=wo.values)
    D = pre.D - np.average(pre.D.reindex(wd.index).fillna(0), weights=wd.values)
    keys = ["usg", "tov", "sfd", "trip3", "and1", "ftp", "ast", "astd", "orb", "drb", "stl", "blk", "pf"] + \
           [f"mix_{z}" for z in ZONES] + [f"fg_{z}" for z in ZONES]
    for p in p2["players"]:
        i = p["id"]
        if i in S.index:
            for k in keys:
                p[k] = float(S.loc[i, k])
        p["O"] = float(O.get(i, -1.0))
        p["D"] = float(D.get(i, -0.5))
    usage_strength(p2["players"], poss[poss.tau < t_cut])
    return p2
