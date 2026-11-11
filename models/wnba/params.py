# %% Assemble simulator parameters: league constants, player sim rates + impacts, pace, team context
"""
Builds data/processed/wnba/sim_params.json - the single parameter object shared by sim.py and sim.js.
Also fits the player pace model:
    first-play seconds = lg + sum_off po_i + sum_def pd_j  (ridge, recency H=1 season)
  on possessions outside late-game/garbage situations, plus a team (coach) residual for 2026 shrunk
  with 800 pseudo-possessions.
Impacts are re-centred so that the 2026 possession-weighted mean O and D are exactly zero; the league
average offensive rating is then the 2026 regular-season points per 100 possessions.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from models.wnba.common import PROC, ZONES, season_bounds, tau, tau_end
from models.wnba.rapm import design, player_index, ridge, weights

CUR = 2026


def shrink_coef(c, se):
    t2 = (c / se) ** 2
    return c * t2 / (1 + t2)


def league_constants(poss, shots, pg):
    p = poss[(poss.season == CUR) & (poss.season_type == 2)]
    s = shots[(shots.season == CUR) & (shots.season_type == 2)]
    g = pg[(pg.season == CUR) & (pg.season_type == 2)]
    n = len(p)
    L = {}
    L["ortg"] = float(p.pts.sum() / n * 100)
    L["poss_per_team_game"] = float(n / p.game_id.nunique() / 2)
    L["tov_per_poss"] = float(p.tov.clip(upper=1).mean())
    L["ft_trips_per_poss"] = float((p.fta / 2).mean())
    # rebounds
    fg_miss = (s.made == 0).sum()
    L["orb_rate"] = float(p.orb.sum() / p.orb_opp.sum())
    tot_orb_ev, tot_drb_ev = p.orb.sum(), (p.orb_opp - p.orb).sum()
    L["orb_player_credit"] = float(min(1.0, g.orb.sum() / tot_orb_ev))
    L["drb_player_credit"] = float(min(1.0, g.drb.sum() / tot_drb_ev))
    # blocks / assists by zone
    L["blk_given_miss_zone"] = [float(s[(s.zone == z) & (s.made == 0)].blocked.mean()) for z in range(5)]
    lg_astd = s[s.made == 1].assisted.mean()
    L["astd_zone_offset"] = [float(np.log(a / (1 - a)) - np.log(lg_astd / (1 - lg_astd)))
                             for a in [s[(s.zone == z) & (s.made == 1)].assisted.mean() for z in range(5)]]
    tov = g.turnovers.sum()
    L["steal_share_of_tov"] = float(g.stl.sum() / tov)
    L["tech_ft_per_poss"] = float(g.tfta.sum() / n)
    L["tech_ft_pct"] = float(g.tftm.sum() / max(g.tfta.sum(), 1))
    # ORB on missed final FT: estimated from player-games is not separable; use 0.13 (typical) scaled by league ORB
    L["orb_rate_ft"] = float(0.13 * L["orb_rate"] / 0.27)
    L["fg_by_zone"] = [float(s[s.zone == z].made.mean()) for z in range(5)]
    L["mix_by_zone"] = [float((s.zone == z).mean()) for z in range(5)]
    L["n_poss_2026"] = int(n)
    L["lg_player_stl"] = float(g.stl.sum() / g.def_poss.sum())
    L["lg_player_blk"] = float(g.blk.sum() / g.opp_fga_on.sum())
    return L


def pace_model(poss, pidx, bounds):
    t_end = tau_end(CUR)
    q = poss[(poss.orb == 0) & ~((poss.period >= 4) & ((poss.t_end > 2280) | (poss.margin.abs() >= 15))) &
             (poss.dur > 2) & (poss.dur < 30)].reset_index(drop=True)
    X = design(q, pidx)
    X = abs(X)  # pace: both ends enter with +1
    y = q.dur.values.astype(float)
    w = weights(q.tau.values, t_end, 1.0, np.zeros(len(q), bool))
    P = len(pidx)
    extra = np.c_[np.ones(len(q))]
    b = ridge(X, y, w, 1500.0, extra=extra)
    po, pd_ = b[:P], b[P:2 * P]
    # 2026 team residuals (coach / system), shrunk
    q26 = q[q.season == CUR]
    X26 = abs(design(q26, pidx))
    r = q26.dur.values - X26 @ b[:2 * P] - b[2 * P]
    ro = pd.Series(r).groupby(q26.off_team.values).agg(["sum", "size"])
    rd = pd.Series(r).groupby(q26.def_team.values).agg(["sum", "size"])
    k = 800.0
    team_off = (ro["sum"] / (ro["size"] + k)).to_dict()
    team_def = (rd["sum"] / (rd["size"] + k)).to_dict()
    # recentre player pace coefficients on 2026 usage
    return dict(po=pd.Series(po, index=pidx), pd=pd.Series(pd_, index=pidx), intercept=float(b[2 * P]),
                team_off=team_off, team_def=team_def)


def usage_strength(players, poss):
    """Context-free usage strength. Observed usage is measured alongside real teammates, so a plain
    u_i / sum(u) share double-penalises players who share the floor with other high-usage players.
    Fit a_i so that, over the actual 2025-26 lineups (recency weighted), sum_poss plays_p * exp(a_i) /
    sum_lineup exp(a_j) reproduces each player's projected usage x on-court possessions (fixed point)."""
    q = poss[poss.season >= CUR - 1]
    L = q[[f"o{k}" for k in range(5)]].values
    plays = (q.fga + q.ft_trips - 0 + q.tov.clip(upper=1)).values.astype(float)
    plays = np.where(plays > 0, plays, 1.0)
    w = np.where(q.season.values == CUR, 1.0, 0.4)
    ids = np.unique(L)
    pos = {p: i for i, p in enumerate(ids)}
    Li = np.vectorize(pos.get)(L)
    n_on = np.bincount(Li.ravel(), weights=np.repeat(w, 5), minlength=len(ids))
    U = {p["id"]: p["usg"] for p in players}
    # league usage per possession for unknown ids (players not exported): position-free mean
    u_mean = float(np.mean(list(U.values())))
    u = np.array([U.get(int(p), u_mean) for p in ids])
    # scale target so totals match observed plays
    target = u * n_on
    target *= (plays * w).sum() / target.sum()
    a = np.log(u)
    for _ in range(60):
        e = np.exp(a)[Li]
        sh = e / e.sum(1, keepdims=True)
        pred = np.bincount(Li.ravel(), weights=(sh * (plays * w)[:, None]).ravel(), minlength=len(ids))
        a += 0.8 * np.log(np.maximum(target, 1e-9) / np.maximum(pred, 1e-9))
        a -= a.mean()
    A = dict(zip(ids.astype(int), a))
    have = [(A[p["id"]], np.log(p["usg"])) for p in players if p["id"] in A and n_on[pos[p["id"]]] > 200]
    off = float(np.mean([x - y for x, y in have])) if have else 0.0
    for p in players:
        ok = p["id"] in A and n_on[pos[p["id"]]] > 200
        # blend with log(u) by sample size (200 weighted possessions ~ half weight)
        if p["id"] in A:
            nn = n_on[pos[p["id"]]]
            lam = nn / (nn + 200.0)
            p["usg_w"] = float(np.exp(lam * A[p["id"]] + (1 - lam) * (np.log(p["usg"]) + off)))
        else:
            p["usg_w"] = float(np.exp(np.log(p["usg"]) + off))
        del ok


def late_foul_table(poss):
    """Empirical P(defence fouls intentionally) by offence lead (1..15) and seconds left (bins edged at
    15/30/45/60/90) in the 4th quarter / OT. A foul possession = no FGA, no TOV, FTs, <= 8 s. The background
    rate of such possessions when the offence is not leading (ordinary bonus fouls, already in the player
    rates) is removed; cells are shrunk toward their lead-neighbours with 15 pseudo-possessions."""
    p = poss[(poss.period >= 4)].copy()
    pend = np.where(p.period == 4, 2400, 2400 + 300 * (p.period - 4))
    p["rem"] = pend - p.t_start
    q = p[p.rem <= 90].copy()
    q["foul"] = ((q.fga == 0) & (q.fta > 0) & (q.tov == 0) & (q.dur <= 8)).astype(float)
    bg = float(q[q.margin <= 0].foul.mean())
    edges = [0, 15, 30, 45, 60, 90]
    q["rb"] = np.digitize(q.rem, edges[1:-1], right=True)
    tab = np.zeros((15, 5))
    cnt = np.zeros((15, 5))
    for L in range(1, 16):
        for b in range(5):
            d = q[(q.margin.clip(upper=15) == L) & (q.rb == b)]
            tab[L - 1, b], cnt[L - 1, b] = (d.foul.mean() if len(d) else 0.0), len(d)
    sm = tab.copy()
    for L in range(15):
        nb = tab[max(L - 1, 0):L + 2].mean(0)
        sm[L] = (cnt[L] * tab[L] + 15 * nb) / (cnt[L] + 15)
    pint = np.clip((sm - bg) / (1 - bg), 0, 0.97)
    return dict(rem_edges=edges[1:], lead_max=15, p=pint.round(4).tolist(), background=bg)


def main(force=False):
    out = PROC / "sim_params.json"
    if out.exists() and not force:
        print("params: cached")
        return
    poss = pd.read_parquet(PROC / "possessions.parquet")
    poss = poss[~poss.is_empty & poss.lineup_ok].reset_index(drop=True)
    games = pd.read_parquet(PROC / "games.parquet")
    bounds = season_bounds(games)
    poss["tau"] = tau(poss.season.values, poss.date.values, bounds)
    nxt = poss.groupby("game_id").start_drb.shift(-1).fillna(0)
    poss["orb_opp"] = poss.orb + nxt
    shots = pd.read_parquet(PROC / "shots_xfg.parquet")
    pg = pd.read_parquet(PROC / "player_games.parquet")
    gd = games.set_index("game_id")
    pg["season"] = pg.game_id.map(gd.season)
    pg["season_type"] = pg.game_id.map(gd.season_type)
    L = league_constants(poss, shots, pg)

    rapm = pd.read_parquet(PROC / "rapm_players.parquet").set_index("pid")
    sk = pd.read_parquet(PROC / "skills.parquet").set_index("pid")
    rot = pd.read_parquet(PROC / "rotations.parquet").set_index("pid")
    bio = pd.read_parquet(PROC / "players_bio.parquet").set_index("pid")
    ctx = json.loads((PROC / "context.json").read_text())

    # ---- re-centre impacts on 2026 possession weights
    p26 = poss[poss.season == CUR]
    w_off = pd.Series(p26[[f"o{k}" for k in range(5)]].values.ravel()).value_counts()
    w_def = pd.Series(p26[[f"d{k}" for k in range(5)]].values.ravel()).value_counts()
    O = rapm.O.copy()
    D = rapm.D.copy()
    mo = np.average(O.reindex(w_off.index).fillna(0), weights=w_off.values)
    md = np.average(D.reindex(w_def.index).fillna(0), weights=w_def.values)
    centre = dict(O=float(mo), D=float(md))
    ff_cols = [c for c in rapm.columns if c.startswith("ff_")]

    # ---- pace
    pidx = player_index(poss)
    pace = pace_model(poss, pidx, bounds)
    mpo = np.average(pace["po"].reindex(w_off.index).fillna(0), weights=w_off.values)
    mpd = np.average(pace["pd"].reindex(w_def.index).fillna(0), weights=w_def.values)

    # ---- player list: all players in bio (current rosters + recent FAs)
    pids = bio.index
    # rookies / no-data players: impact prior = SPM of shrunk-to-mean features (already in rapm if seen);
    # unseen players get the mean prior of players with < 300 possessions.
    fringe = rapm[rapm.f_n_poss < 300]
    newO = float(np.average(fringe.O_prior - mo, weights=np.ones(len(fringe)))) if len(fringe) else -1.0
    newD = float(np.average(fringe.D_prior - md, weights=np.ones(len(fringe)))) if len(fringe) else -0.5
    players = []
    for pid in pids:
        b = bio.loc[pid]
        r = rapm.loc[pid] if pid in rapm.index else None
        s = sk.loc[pid] if pid in sk.index else None
        ro = rot.loc[pid] if pid in rot.index else None
        pg_ = s["pos_group"] if s is not None else b.pos_group
        rec = dict(id=int(pid), name=b["name"], team=(int(b.team) if pd.notna(b.team) else None), pos=b.pos, pos_group=pg_,
                   age=float(b.age), height=float(b.height_in))
        if r is not None:
            rec.update(O=float(r.O - mo), D=float(r.D - md), O_sd=float(r.O_sd), D_sd=float(r.D_sd))
            for c in ff_cols:
                rec[c] = float(r[c])
            rec["pace_o"] = float(pace["po"].get(pid, mpo) - mpo)
            rec["pace_d"] = float(pace["pd"].get(pid, mpd) - mpd)
        else:
            rec.update(O=newO, D=newD, O_sd=2.5, D_sd=2.5, pace_o=0.0, pace_d=0.0)
            for c in ff_cols:
                rec[c] = 0.0
        for k in ["usg", "tov", "sfd", "trip3", "and1", "ftp", "ast", "astd", "orb", "drb", "stl", "blk", "pf"] + \
                 [f"mix_{z}" for z in ZONES] + [f"fg_{z}" for z in ZONES]:
            rec[k] = float(s[k]) if s is not None else float(sk[f"{k}_prior"].median())
        rec["min"] = float(ro.proj_min) if ro is not None else 0.0
        rec["min_sd"] = float(ro.min_sd) if ro is not None else 5.5
        rec["starter"] = bool(ro.starter) if ro is not None else False
        players.append(rec)

    usage_strength(players, poss)

    teams = pd.read_parquet(PROC / "teams.parquet")
    # home court: the possession-level RAPM home coefficient (controls for the ten players on court) x league
    # pace. The game-level ridge (context.py) gives 1.53 +- 0.27 but its team-season ridge absorbs part of it;
    # raw 2017-26 home margin is 2.03. Re-simulating 2025-26 with 1.53 under-shot the real home win rate.
    rm = json.loads((PROC / "rapm_meta.json").read_text())
    hca = rm["home_coef_per100"] * L["poss_per_team_game"] / 100.0
    params = dict(
        version=1,
        league=L,
        centre=centre,
        context=dict(hca_pts=float(hca), b2b_pts=float(shrink_coef(ctx["b2b"]["coef"], ctx["b2b"]["se"])),
                     rest_day_pts=float(shrink_coef(ctx["rest_day"]["coef"], ctx["rest_day"]["se"])),
                     travel_pts_per_1000mi=float(shrink_coef(ctx["travel_per_1000mi"]["coef"], ctx["travel_per_1000mi"]["se"]))),
        pace=dict(first_play_sec=float(pace["intercept"] + mpo * 5 + mpd * 5), orb_play_sec=6.0, gamma_shape=3.0,
                  team_off={str(int(k)): float(v) for k, v in pace["team_off"].items()},
                  team_def={str(int(k)): float(v) for k, v in pace["team_def"].items()}),
        sim=dict(segment_sec=120.0, ot_segment_sec=150.0, min_cap=40.0, realloc_cap=38.0, max_c=2,
                 ff_def_weight=1.0, late_foul_sec=45.0, late_foul_max_lead=9, blowout=[[22, 300], [17, 150]], min_boost=0.0,
                 newton_iter=4, max_ot=6, score_effect=0.0025, eff_shock_sd=0.0, whistle_sd=0.0, pace_shock_sd=0.0),
        players=players,
        teams=[dict(id=int(t.team_id), abbr=t.abbr, name=t.team_display_name, color=t.team_color,
                    alt_color=t.team_alternate_color, logo=t.team_logo) for t in teams.itertuples()],
    )
    params["pace"]["steal_factor"] = 0.8
    params["sim"]["late_foul_table"] = late_foul_table(poss)
    # calibrate the league first-play time so simulated possessions match the 2026 league rate
    from models.wnba.sim import simulate
    ids = [t["id"] for t in params["teams"]]
    rng = np.random.default_rng(0)
    pairs = [tuple(rng.choice(ids, 2, replace=False)) for _ in range(14)]
    for it in range(3):
        n = np.mean([simulate(params, int(h), int(a), n_sims=1000, seed=it * 10 + k)["n_poss"].mean() / 2 for k, (h, a) in enumerate(pairs)])
        params["pace"]["first_play_sec"] *= (n / L["poss_per_team_game"]) ** 1.2
    params["pace"]["calibrated_poss"] = float(n)
    out.write_text(json.dumps(params))
    print(f"params: {len(players)} players, lg ortg {L['ortg']:.1f}, poss/g {L['poss_per_team_game']:.1f}, "
          f"first play {params['pace']['first_play_sec']:.1f}s, centre O {mo:.2f} D {md:.2f}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
