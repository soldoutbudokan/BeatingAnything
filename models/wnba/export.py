# %% Export site JSON: meta, players, teams, sim_params, matchups
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date

import numpy as np
import pandas as pd

from models.wnba.common import CUTOFF_DATE, EXPORT, PROC, SEASONS, ZONES, season_bounds, tau, tau_end, write_json
from models.wnba.sim import Team, game_summary, load_params, player_summary, simulate
from models.wnba.value import analytic_pace, player_values, team_rating

N_SIMS = int(os.environ.get("WNBA_NSIMS", "10000"))
SIM_KEYS = ["id", "name", "team", "pos_group", "O", "D", "usg", "usg_w", "tov", "sfd", "trip3", "and1", "ftp", "ast", "astd", "orb", "drb",
            "stl", "blk", "pace_o", "pace_d", "ff_tov_D", "ff_ftr_D", "min", "min_sd", "starter"] + \
           [f"mix_{z}" for z in ZONES] + [f"fg_{z}" for z in ZONES]
RATE_KEYS = ["usg", "tov", "sfd", "trip3", "and1", "ftp", "ast", "astd", "orb", "drb", "stl", "blk", "pf"] + \
            [f"mix_{z}" for z in ZONES] + [f"fg_{z}" for z in ZONES]


def rnd(x, d=4):
    if isinstance(x, dict):
        return {k: rnd(v, d) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rnd(v, d) for v in x]
    if isinstance(x, (float, np.floating)):
        return round(float(x), d)
    return x


def trim_player(p, d=2):
    """Compact per-player matchup record: stat -> [mean, sd, q(10,25,50,75,90), first_line, p_over(5 lines)]."""
    out = dict(id=p["id"], min_proj=round(p["proj_min"], 1))
    for k in ["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pra", "pr", "pa"]:
        s = p[k]
        lines, po = np.array(s["lines"]), np.array(s["p_over"])
        keep = np.argsort(np.abs(lines - s["mean"]), kind="stable")[:5]
        keep.sort()
        out[k] = [round(s["mean"], 2), round(s["sd"], 2), [round(v, 1) for v in s["q"][1:6]], float(lines[keep[0]]),
                  [round(float(v), 3) for v in po[keep]]]
    out["fga"], out["fg3a"], out["fta"], out["p_dd"] = round(p["fga"], 2), round(p["fg3a"], 2), round(p["fta"], 2), round(p["p_dd"], 3)
    return out


def trim_hist(h):
    p = np.array(h["p"])
    nz = np.nonzero(p)[0]
    a, b = (nz[0], nz[-1]) if len(nz) else (0, 0)
    return [int(h["lo"] + a), [round(float(v), 4) for v in p[a:b + 1]]]


def trim_game(g):
    o = dict(home_win=round(g["home_win"], 4), p_ot=round(g["p_ot"], 4), poss=round(g["poss_per_team"], 1))
    for k in ["margin", "total", "home_pts", "away_pts"]:
        o[k] = [round(g[k]["mean"], 2), round(g[k]["sd"], 2), [round(v, 1) for v in g[k]["q"]]]
    o["margin_hist"] = trim_hist(g["margin_hist"])
    o["total_hist"] = trim_hist(g["total_hist"])
    o["quarters"] = [[round(q["home"], 2), round(q["away"], 2), round(q["home_win"], 3), round(q["tie"], 3), round(q["margin_sd"], 2),
                      round(q["total_sd"], 2)] for q in g["quarters"]]
    o["halves"] = [[round(h["home"], 2), round(h["away"], 2), round(h["home_win"], 3), round(h["tie"], 3), round(h["margin_sd"], 2),
                    round(h["total_sd"], 2)] for h in g["halves"]]
    return o


# %% matchups (cached: the slow part)
PMF_STATS = ["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pra", "pr", "pa"]


def pmf(x, tail=0.0005):
    """Integer pmf [lo, [p...]] with each tail trimmed below `tail` cumulative probability."""
    v = np.round(np.asarray(x)).astype(int)
    lo = v.min()
    c = np.bincount(v - lo) / len(v)
    cs = np.cumsum(c)
    a = int(np.searchsorted(cs, tail))
    b = int(len(c) - np.searchsorted(np.cumsum(c[::-1]), tail))
    b = max(b, a + 1)
    return [int(lo + a), [round(float(q), 4) for q in c[a:b]]]


def player_pmfs(r, side):
    from models.wnba.sim import SI
    T = r["home"] if side == 0 else r["away"]
    off = 0 if side == 0 else r["home"].n
    b = r["box"]
    out = {}
    for i in range(T.n):
        k = off + i
        d = dict(min=b[SI["sec"], :, k] / 60, pts=b[SI["pts"], :, k], reb=b[SI["orb"], :, k] + b[SI["drb"], :, k],
                 ast=b[SI["ast"], :, k], fg3m=b[SI["fg3m"], :, k], stl=b[SI["stl"], :, k], blk=b[SI["blk"], :, k],
                 tov=b[SI["tov"], :, k])
        d["pra"], d["pr"], d["pa"] = d["pts"] + d["reb"] + d["ast"], d["pts"] + d["reb"], d["pts"] + d["ast"]
        out[int(T.ids[i])] = {s: pmf(d[s]) for s in PMF_STATS}
    return out


def run_matchups(prm, force=False):
    path = PROC / "matchups_raw.json"
    if path.exists() and not force:
        return json.loads(path.read_text())
    teams = [t["id"] for t in prm["teams"]]
    TM = {t: Team(prm, t) for t in teams}
    out = {}
    t0 = time.time()
    for h in teams:
        for a in teams:
            if h == a:
                continue
            r = simulate(prm, TM[h], TM[a], n_sims=N_SIMS, seed=(h * 7919 + a) % 2 ** 31)
            g = game_summary(r)
            hp = [trim_player(p) for p in player_summary(r, 0) if p["proj_min"] >= 1.0]
            ap = [trim_player(p) for p in player_summary(r, 1) if p["proj_min"] >= 1.0]
            gm = trim_game(g)
            gm["home_pts_hist"] = pmf(r["score"][:, 0], 0.0)
            gm["away_pts_hist"] = pmf(r["score"][:, 1], 0.0)
            pm = {**player_pmfs(r, 0), **player_pmfs(r, 1)}
            for p in hp + ap:
                p["pmf"] = pm[p["id"]]
            out[f"{h}_{a}"] = dict(home=h, away=a, game=gm, home_players=hp, away_players=ap)
    secs = time.time() - t0
    out = dict(n_sims=N_SIMS, seconds=secs, pairs=out)
    path.write_text(json.dumps(out))
    return out


# %% shot-making metrics
def shot_metrics():
    s = pd.read_parquet(PROC / "shots_xfg.parquet")
    games = pd.read_parquet(PROC / "games.parquet")
    b = season_bounds(games)
    s["tau"] = tau(s.season.values, s.game_date.values, b)
    w = pd.Series(0.5 ** ((tau_end(2026) - s.tau.values) / 1.0), index=s.index)
    s["w"] = w
    g = s.groupby("shooter")
    n = g.w.sum()
    k = 150.0
    res = pd.DataFrame({
        "shots_w": n,
        "shots_2026": s[s.season == 2026].groupby("shooter").size(),
        "pts_per_shot": (s.pts * w).groupby(s.shooter).sum() / n,
        "xpts_per_shot": (s.xpts * w).groupby(s.shooter).sum() / n,
        "smoe_per_shot": ((s.pts - s.xpts) * w).groupby(s.shooter).sum() / (n + k),
        "rim_xfg": (s.xfg * w)[s.zone == 0].groupby(s.shooter[s.zone == 0]).sum() / w[s.zone == 0].groupby(s.shooter[s.zone == 0]).sum(),
    })
    lg_x = float(np.average(s[s.season == 2026].xpts))
    res["shot_selection"] = res.xpts_per_shot - lg_x  # >0: takes better-than-average shots
    res["fg3_smoe_per_shot"] = ((s.pts - s.xpts) * w)[s.pts3 == 1].groupby(s.shooter[s.pts3 == 1]).sum() / (w[s.pts3 == 1].groupby(s.shooter[s.pts3 == 1]).sum() + k)
    return res, lg_x


def pct_rank(x, mask):
    v = x[mask]
    out = np.full(len(x), np.nan)
    if mask.sum() > 1:
        r = v.rank(pct=True) * 100
        out[mask.values] = r.values
    return out


# %% main
def main(force=False):
    prm = load_params()
    t0 = time.time()
    M = run_matchups(prm, force=force)
    values, vmeta, teamobjs = player_values(prm, margin_sd=float(np.mean([v["game"]["margin"][1] for v in M["pairs"].values()])))
    rapm = pd.read_parquet(PROC / "rapm_players.parquet").set_index("pid")
    sk = pd.read_parquet(PROC / "skills.parquet").set_index("pid")
    rot = pd.read_parquet(PROC / "rotations.parquet").set_index("pid")
    bio = pd.read_parquet(PROC / "players_bio.parquet").set_index("pid")
    sm, lg_x = shot_metrics()
    pg = pd.read_parquet(PROC / "player_games.parquet")
    p26 = pg[(pg.season == 2026) & (pg.minutes.fillna(0) > 0)].groupby("pid").agg(
        gp=("minutes", "size"), mpg=("minutes", "mean"), ppg=("points", "mean"), rpg=("rebounds", "mean"), apg=("assists", "mean"),
        min_tot=("minutes", "sum"))
    car = pg[pg.minutes.fillna(0) > 0].groupby("pid").agg(career_gp=("minutes", "size"), career_poss=("off_poss", "sum"))
    cen = prm["centre"]
    # 2026 actual per-game line (regular season + playoffs, games played) and projected per-game line at
    # default minutes (mean over the player's 28 home/away matchups in matchups.json)
    a = pg[(pg.season == 2026) & (pg.minutes.fillna(0) > 0)]
    act26 = a.groupby("pid").agg(games=("minutes", "size"), min=("minutes", "mean"), pts=("points", "mean"), reb=("rebounds", "mean"),
                                 ast=("assists", "mean"), fg3m=("three_point_field_goals_made", "mean"), stl=("steals", "mean"),
                                 blk=("blocks", "mean"), tov=("turnovers", "mean"))
    acc = {}
    for v in M["pairs"].values():
        for p in v["home_players"] + v["away_players"]:
            acc.setdefault(p["id"], []).append([p[k][0] for k in ["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pra"]])
    proj_pg = {i: dict(zip(["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pra"], np.round(np.mean(v, 0), 2).tolist()))
               for i, v in acc.items()}
    abbr = {t["id"]: t["abbr"] for t in prm["teams"]}
    ff_names = ["tov", "orb", "ftr", "efg", "xpts", "moe"]
    rows = []
    for p in prm["players"]:
        i = p["id"]
        b = bio.loc[i]
        r = rapm.loc[i] if i in rapm.index else None
        rec = dict(id=i, name=p["name"], team=p["team"], team_abbr=abbr.get(p["team"]), pos=p["pos"], pos_group=p["pos_group"],
                   age=round(p["age"], 1), age_imputed=bool(b.age_imputed), height_in=p["height"], height_imputed=bool(b.height_imputed),
                   roster_source=b.roster_source, on_espn_roster=bool(b.on_espn_roster))
        rec["sample"] = dict(
            poss_w=round(float(r.wposs), 0) if r is not None else 0, career_poss=int(car.career_poss.get(i, 0)),
            career_gp=int(car.career_gp.get(i, 0)), gp_2026=int(p26.gp.get(i, 0)), min_2026=round(float(p26.min_tot.get(i, 0)), 0),
            shots_2026=int(sm.shots_2026.get(i, 0) if pd.notna(sm.shots_2026.get(i, np.nan)) else 0))
        rec["box_2026"] = dict(mpg=round(float(p26.mpg.get(i, np.nan)), 1), ppg=round(float(p26.ppg.get(i, np.nan)), 1),
                               rpg=round(float(p26.rpg.get(i, np.nan)), 1), apg=round(float(p26.apg.get(i, np.nan)), 1))
        tot_sd = float(np.hypot(p["O_sd"], p["D_sd"]))
        rec["impact"] = dict(O=p["O"], D=p["D"], total=p["O"] + p["D"], O_sd=p["O_sd"], D_sd=p["D_sd"], total_sd=tot_sd,
                             O_rapm=(float(r.O_rapm) - cen["O"]) if r is not None else None,
                             D_rapm=(float(r.D_rapm) - cen["D"]) if r is not None else None,
                             O_prior=(float(r.O_prior) - cen["O"]) if r is not None else p["O"],
                             D_prior=(float(r.D_prior) - cen["D"]) if r is not None else p["D"],
                             O_longrun=(float(r.O_longrun)) if r is not None else None,
                             D_longrun=(float(r.D_longrun)) if r is not None else None)
        rec["four_factor"] = {f"{k}_{s}": p.get(f"ff_{k}_{s}", 0.0) for k in ff_names for s in ("O", "D")}
        smr = sm.loc[i] if i in sm.index else None
        rec["shot_quality"] = dict(
            shots_w=float(smr.shots_w) if smr is not None else 0.0,
            pts_per_shot=float(smr.pts_per_shot) if smr is not None else None,
            xpts_per_shot=float(smr.xpts_per_shot) if smr is not None else None,
            shot_making=float(smr.smoe_per_shot) if smr is not None else 0.0,
            shot_making_3pt=float(smr.fg3_smoe_per_shot) if smr is not None and pd.notna(smr.fg3_smoe_per_shot) else 0.0,
            shot_selection=float(smr.shot_selection) if smr is not None else None,
            def_xpts_allowed=-p.get("ff_xpts_D", 0.0), def_making_allowed=-p.get("ff_moe_D", 0.0))
        s_ = sk.loc[i] if i in sk.index else None
        rec["rates"] = {k: dict(p=p[k], sd=float(s_[f"{k}_sd"]) if s_ is not None else None,
                                n=float(s_[f"{k}_n"]) if s_ is not None else 0.0,
                                raw=float(s_[f"{k}_raw"]) if s_ is not None and pd.notna(s_[f"{k}_raw"]) else None,
                                prior=float(s_[f"{k}_prior"]) if s_ is not None else None) for k in RATE_KEYS}
        ro = rot.loc[i] if i in rot.index else None
        rec["minutes"] = dict(proj=p["min"], sd=p["min_sd"], starter=p["starter"],
                              role_min=float(ro.role_min) if ro is not None else 0.0, avail=float(ro.avail) if ro is not None else 0.0)
        v = values[i]
        rec["value"] = {k: v.get(k) for k in ["varp100", "varp_pts", "varp_wins", "off_delta", "def_delta", "net_delta", "winp_delta"]}
        a26 = act26.loc[i] if i in act26.index else None
        rec["actual_2026"] = ({k: round(float(a26[k]), 2) for k in ["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]} | {"games": int(a26.games)}
                              if a26 is not None else {"games": 0})
        rec["proj_per_game"] = proj_pg.get(i)
        rows.append(rec)
    # percentiles among rotation players (on a roster, proj >= 10 min)
    qual = pd.Series([r["team"] is not None and r["minutes"]["proj"] >= 10 for r in rows])
    def col(f):
        return pd.Series([f(r) for r in rows], dtype=float)
    pct_fields = {"O": lambda r: r["impact"]["O"], "D": lambda r: r["impact"]["D"], "total": lambda r: r["impact"]["total"],
                  "varp100": lambda r: r["value"]["varp100"], "shot_making": lambda r: r["shot_quality"]["shot_making"],
                  "shot_selection": lambda r: r["shot_quality"]["shot_selection"]}
    for k in RATE_KEYS:
        pct_fields[k] = (lambda kk: (lambda r: r["rates"][kk]["p"]))(k)
    P = {k: pct_rank(col(f), qual) for k, f in pct_fields.items()}
    for j, r in enumerate(rows):
        r["pct"] = {k: (None if np.isnan(P[k][j]) else round(float(P[k][j]), 0)) for k in P}
        r["qualified_for_pct"] = bool(qual[j])
    write_json(EXPORT / "players.json", dict(players=rows, value_meta=vmeta, league_xpts_per_shot=lg_x), digits=4)

    # teams
    lineups = pd.read_parquet(PROC / "lineups.parquet")
    names = {p["id"]: p["name"] for p in prm["players"]}
    pairs = M["pairs"]
    trows = []
    for t in prm["teams"]:
        T, (o, d, n) = teamobjs[t["id"]]
        tid = t["id"]
        ms = [v for v in pairs.values() if v["home"] == tid or v["away"] == tid]
        winp = np.mean([v["game"]["home_win"] if v["home"] == tid else 1 - v["game"]["home_win"] for v in ms])
        pace_sim = np.mean([v["game"]["poss"] for v in ms])
        pts_for = np.mean([v["game"]["home_pts"][0] if v["home"] == tid else v["game"]["away_pts"][0] for v in ms])
        pts_ag = np.mean([v["game"]["away_pts"][0] if v["home"] == tid else v["game"]["home_pts"][0] for v in ms])
        order = np.argsort(-T.minutes)
        lu = lineups[lineups.team == tid]
        trows.append(dict(
            id=tid, abbr=t["abbr"], name=t["name"], color=t["color"], alt_color=t["alt_color"], logo=t["logo"],
            roster=[int(T.ids[k]) for k in order],
            rotation=[dict(id=int(T.ids[k]), name=T.names[k], min=float(T.minutes[k]), min_sd=float(T.min_sd[k]),
                           starter=bool(T.starter[k]), pos_group="GFC"[T.posg[k]]) for k in order],
            ortg=o, drtg=d, net=n, pace_analytic=analytic_pace(prm, T), pace_sim=float(pace_sim),
            sim_avg_win_prob=float(winp), sim_pts_for=float(pts_for), sim_pts_against=float(pts_ag),
            proj_win_pct_vs_league=float(winp),
            top_lineups_2026=[dict(ids=[int(x) for x in r.lineup.split(",")], names=[names.get(int(x), str(x)) for x in r.lineup.split(",")],
                                   poss=float(r.poss), net100=float(r.net100)) for r in lu.itertuples()],
            pace_team_residual=dict(off=prm["pace"]["team_off"].get(str(tid), 0.0), deff=prm["pace"]["team_def"].get(str(tid), 0.0))))
    trows.sort(key=lambda r: -r["net"])
    write_json(EXPORT / "teams.json", dict(teams=trows, league_ortg=prm["league"]["ortg"]), digits=4)

    # sim params (only what sim.js needs)
    sp = {k: prm[k] for k in ["version", "league", "context", "pace", "sim", "teams"]}
    sp["players"] = [{k: p[k] for k in SIM_KEYS} for p in prm["players"]]
    write_json(EXPORT / "sim_params.json", sp, digits=5)
    # per-home-team files carry everything (incl. player pmfs); the single file keeps the round-1 shape
    # (+ team score histograms) without the bulky pmfs
    import copy
    slim = copy.deepcopy(pairs)
    for v in slim.values():
        for p in v["home_players"] + v["away_players"]:
            p.pop("pmf", None)
    for t in prm["teams"]:
        sub = {k: v for k, v in pairs.items() if v["home"] == t["id"]}
        write_json(EXPORT / "matchups" / f"{t['id']}.json", dict(n_sims=M["n_sims"], home=t["id"], pairs=sub,
                                                                 player_fields=["mean", "sd", "q10_25_50_75_90", "first_line", "p_over_5_lines"],
                                                                 pmf_fields=PMF_STATS), digits=4)
    write_json(EXPORT / "matchups.json", dict(n_sims=M["n_sims"], pairs=slim,
                                              player_fields=["mean", "sd", "q10_25_50_75_90", "first_line", "p_over_5_lines"],
                                              line_step=dict(min=2, pts=2, reb=1, ast=1, fg3m=1, stl=1, blk=1, tov=1, pra=2, pr=2, pa=2)), digits=4)
    # meta
    games = pd.read_parquet(PROC / "games.parquet")
    poss = pd.read_parquet(PROC / "possessions.parquet")
    shots = pd.read_parquet(PROC / "shots.parquet")
    recon = json.loads((PROC / "recon.json").read_text())
    rm = json.loads((PROC / "rapm_meta.json").read_text())
    skm = json.loads((PROC / "skills_meta.json").read_text())
    meta = dict(
        build_date=str(date.today()), data_cutoff=CUTOFF_DATE, last_game_date=str(games.date.max()), seasons=SEASONS,
        n_games=int(len(games)), n_games_by_season=games.groupby("season").size().to_dict(),
        n_possessions=int((~poss.is_empty).sum()), n_shots=int(len(shots)), n_players_exported=len(rows),
        n_teams=len(trows), lineup_recon=recon,
        recon_minutes_within_1=float(np.average([v["min_within_1"] for v in recon.values()], weights=[v["player_games"] for v in recon.values()])),
        recon_poss_lineup_ok=float(np.average([v["poss_lineup_ok"] for v in recon.values()], weights=[v["possessions"] for v in recon.values()])),
        hyper=dict(rapm=dict(H_seasons=rm["H"], H_feat=rm["H_feat"], lambda_prior=rm["lam_prior"], lambda_plain=rm["lam_plain"]),
                   skills={k: dict(H=v["H"], k=v["k"]) for k, v in skm["tuned"].items()}),
        matchup_sims=M["n_sims"], matchup_seconds=M["seconds"], value=vmeta, centre=prm["centre"],
        files=["meta.json", "players.json", "teams.json", "sim_params.json", "matchups.json", "diagnostics.json", "method.md", "schema.md"])
    write_json(EXPORT / "meta.json", meta, digits=4)
    sizes = {f.name: round(f.stat().st_size / 1e6, 2) for f in EXPORT.glob("*.json")}
    print(f"export: {len(rows)} players, {len(trows)} teams, {len(pairs)} matchups in {time.time() - t0:.0f}s; sizes MB {sizes}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
