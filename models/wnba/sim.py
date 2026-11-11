# %% Possession-level Monte Carlo simulator (vectorised across simulations)
"""
The same algorithm is implemented in docs/models/wnba/sim.js (scalar per simulation). Keep them in sync.

Game flow
  * Per simulation, each player's minutes target M ~ N(min, sd') clipped to [0, 40], sd' = min(sd, 0.5*min + 2),
    then rescaled so the team sums to 200.
  * Regulation = 20 segments of 120 s (5 per quarter); OT = 2 segments of 150 s. At each segment start a
    five is chosen per team greedily (see choose_lineups): need-to-play, starters at the start of each half,
    top-minute closers in a close 4th quarter / OT, a fatigue penalty after 3 straight segments, <=2 centres,
    >=1 guard, bench emptying in blowouts.
  * Lineup calibration (calibrate): for offence five L vs defence five M the target points per possession is
        pi* = (lg_ortg + sum_L O - sum_M D + context) / 100.
    Turnover and FT-trip probabilities start from the offensive players' projected rates and are moved by
    the defenders' four-factor RAPM (forced TOV, fouls); ORB chance = sum ORB rates / (sum ORB + sum DRB);
    a common logit shift on every make probability is then solved (Newton) so the analytic expected
    points per possession equals pi*.
  * Possession: first play duration ~ Gamma(3, mu/3), mu from player + team pace; each play: user ~ usage
    among the five, outcome TOV / shooting-foul trip / FGA, zone ~ shooter mix, make ~ calibrated prob,
    and-one, assist (shooter's assisted share x zone), block on misses, rebound contest (team-level ORB chance,
    individual credit by ORB/DRB rates), FTs. ORB -> new play (Gamma(2) mean 6 s). Steals by defender rates.
  * Late game (4th quarter/OT, last 2 min): leader milks clock, trailer hurries and shoots more threes,
    intentional fouls when trailing by 1-9 in the last 45 s. Technical FTs at the league rate.
"""
from __future__ import annotations

import json
import time

import numpy as np

from models.wnba.common import PROC

STATS = ["pts", "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "orb", "drb", "ast", "stl", "blk", "tov", "sec"]
SI = {k: i for i, k in enumerate(STATS)}
ZV = np.array([2.0, 2.0, 2.0, 3.0, 3.0])
POSG = {"G": 0, "F": 1, "C": 2}


def expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


# %% minutes handling (mirrored in JS)
def scale_fill(m, fixed, total, cap):
    """Scale the non-fixed entries so the sum hits total (bisection on a multiplier, entries capped)."""
    m = np.asarray(m, float).copy()
    free = ~fixed & (m > 0)
    target = total - m[fixed].sum()
    if free.sum() == 0 or target <= 0:
        return m
    lo, hi = 0.0, 20.0
    base = m[free].copy()
    for _ in range(50):
        s = 0.5 * (lo + hi)
        if np.minimum(base * s, cap).sum() > target:
            hi = s
        else:
            lo = s
    m[free] = np.minimum(base * lo, cap)
    return m


def reallocate(minutes, pos_group, out, fixed=None, cap=38.0, total=200.0):
    """Remove 'out' players and hand their minutes to teammates: weight = minutes x 1.5 for the same
    position group; overflow above cap re-distributed; finally non-fixed minutes rescaled to total."""
    m = np.asarray(minutes, float).copy()
    out = np.asarray(out, bool)
    fixed = np.zeros(len(m), bool) if fixed is None else np.asarray(fixed, bool)
    pg = np.asarray(pos_group)
    for p in np.nonzero(out)[0]:
        R = m[p]
        m[p] = 0.0
        if R <= 0:
            continue
        rec = (~out) & (m > 0) & ~fixed
        if rec.sum() == 0:
            rec = (~out) & ~fixed
        if rec.sum() == 0:
            continue
        w = np.where(rec, np.maximum(m, 0.5) * np.where(pg == pg[p], 1.5, 1.0), 0.0)
        m = m + R * w / w.sum()
        for _ in range(10):
            over = rec & (m > cap)
            if not over.any():
                break
            ex = (m[over] - cap).sum()
            m[over] = cap
            r2 = rec & (m < cap)
            if r2.sum() == 0:
                break
            w2 = np.where(r2, w, 0.0)
            m = m + ex * w2 / w2.sum()
    m[out] = 0.0
    return scale_fill(m, fixed | out, total, 40.0)


# %% team preparation
class Team:
    def __init__(self, params, spec):
        """spec: {'team': id, 'players': [{'id', 'min'(optional override), 'out'(bool)}]} or just team id."""
        P = {p["id"]: p for p in params["players"]}
        if isinstance(spec, (int, np.integer)):
            spec = {"team": int(spec)}
        tid = spec.get("team")
        plist = spec.get("players")
        if plist is None:
            plist = [{"id": p["id"]} for p in params["players"] if p["team"] == tid]
        rows = [P[x["id"]] for x in plist]
        self.ids = np.array([r["id"] for r in rows])
        self.names = [r["name"] for r in rows]
        self.tid = tid
        g = lambda k: np.array([float(r[k]) for r in rows])  # noqa: E731
        for k in ["O", "D", "usg", "tov", "sfd", "trip3", "and1", "ftp", "ast", "astd", "orb", "drb", "stl", "blk",
                  "pace_o", "pace_d", "ff_tov_D", "ff_ftr_D", "min_sd"]:
            setattr(self, k, g(k))
        from models.wnba.common import ZONES
        self.mix = np.array([[r[f"mix_{z}"] for z in ZONES] for r in rows])
        self.fg = np.array([[r[f"fg_{z}"] for z in ZONES] for r in rows])
        self.posg = np.array([POSG.get(r["pos_group"], 1) for r in rows])
        base_min = np.array([float(x.get("min", P[x["id"]]["min"])) if x.get("min") is not None else P[x["id"]]["min"] for x in plist])
        fixed = np.array([x.get("min") is not None for x in plist])
        out = np.array([bool(x.get("out", False)) for x in plist])
        default = np.array([P[x["id"]]["min"] for x in plist])
        m = np.where(fixed, base_min, default)
        self.minutes = reallocate(m, self.posg, out, fixed=fixed, cap=params["sim"]["realloc_cap"])
        self.starter = np.zeros(len(rows), bool)
        # starters: flagged starters still active, topped up by minutes
        flag = np.array([bool(r["starter"]) for r in rows]) & ~out
        order = np.lexsort((-self.minutes, -flag.astype(int)))
        self.starter[order[:5]] = True
        self.out = out
        self.n = len(rows)


# %% calibration of a lineup matchup (vectorised over sims)
def calibrate(prm, Toff, Tdef, L, M, ctx_pts100, team_off_pace, team_def_pace, trail3=None):
    """L, M: (S,5) indices into Toff/Tdef. Returns dict of per-sim arrays."""
    lg = prm["league"]
    u = Toff.usg[L]
    w = u / u.sum(1, keepdims=True)
    dT = -Tdef.ff_tov_D[M].sum(1) / 100.0 * prm["sim"]["ff_def_weight"]
    dF = -Tdef.ff_ftr_D[M].sum(1) / 100.0 * prm["sim"]["ff_def_weight"]
    sT = np.log(np.clip((lg["tov_per_poss"] + dT) / lg["tov_per_poss"], 0.5, 1.6))
    sF = np.log(np.clip((lg["ft_trips_per_poss"] + dF) / lg["ft_trips_per_poss"], 0.5, 1.6))
    t = expit(logit(Toff.tov[L]) + sT[:, None])
    f = expit(logit(Toff.sfd[L]) + sF[:, None])
    tf = t + f
    sc = np.where(tf > 0.9, 0.9 / tf, 1.0)
    t, f = t * sc, f * sc
    g = 1.0 - t - f
    A = Toff.orb[L].sum(1) / lg["orb_player_credit"]
    B = Tdef.drb[M].sum(1) / lg["drb_player_credit"]
    porb = A / (A + B)
    porb_ft = porb * lg["orb_rate_ft"] / lg["orb_rate"]
    mix = Toff.mix[L]  # (S,5,5)
    lf = logit(Toff.fg[L])
    a1 = Toff.and1[L]
    ftp = Toff.ftp[L]
    tr3 = Toff.trip3[L]
    target = (lg["ortg"] + Toff.O[L].sum(1) - Tdef.D[M].sum(1) + ctx_pts100) / 100.0
    d = np.zeros(len(L))
    fixed_pts = (w * f * (2 + tr3) * ftp).sum(1)
    fixed_c = (w * f * (1 - ftp)).sum(1) * porb_ft
    for _ in range(prm["sim"]["newton_iter"]):
        q = expit(lf + d[:, None, None])
        val = ZV[None, None, :] + (a1 * ftp)[:, :, None]
        E = (w * g * (mix * q * val).sum(2)).sum(1) + fixed_pts
        C = (w * g * (mix * (1 - q)).sum(2)).sum(1) * porb + fixed_c
        dq = q * (1 - q)
        Ep = (w * g * (mix * dq * val).sum(2)).sum(1)
        Cp = -(w * g * (mix * dq).sum(2)).sum(1) * porb
        ppp = E / (1 - C)
        dppp = (Ep * (1 - C) + E * Cp) / (1 - C) ** 2
        d = np.clip(d - (ppp - target) / dppp, -1.5, 1.5)
    q = expit(lf + d[:, None, None])
    blkf = Tdef.blk[M].sum(1) / (5 * lg["lg_player_blk"])
    stlp = np.clip(lg["steal_share_of_tov"] * Tdef.stl[M].sum(1) / (5 * lg["lg_player_stl"]), 0, 0.95)
    mu = prm["pace"]["first_play_sec"] + Toff.pace_o[L].sum(1) + Tdef.pace_d[M].sum(1) + team_off_pace + team_def_pace
    return dict(w=w, t=t, f=f, q=q, mix=mix, porb=porb, porb_ft=porb_ft, blkf=blkf, stlp=stlp, mu=np.clip(mu, 8, 22),
                shift=d, target=target)


# %% lineup choice (vectorised)
def choose_lineups(T, M, played, consec, seg, nseg_reg, margin, period, rem_reg_sec, prm, ot):
    S = M.shape[0]
    n = T.n
    rem_min = np.maximum(rem_reg_sec / 60.0, 2.0)
    need = (M - played / 60.0) / rem_min[:, None]
    pri = need.copy()
    if ot:
        pri = M / 40.0 + 0.0 * need
    else:
        if seg in (0, nseg_reg // 2):
            pri = pri + 2.0 * T.starter[None, :]
        close = (np.abs(margin) <= 10)[:, None]
        if seg >= nseg_reg - 2:
            pri = pri + np.where(close, 0.6 * M / 40.0, 0.0)
        pri = pri - np.where(consec >= 3, 0.25 * (consec - 2), 0.0)
        # blowout: 4th quarter
        blow = np.zeros(S, bool)
        if period == 4:
            for mar, sec in prm["sim"]["blowout"]:
                blow |= (np.abs(margin) >= mar) & (rem_reg_sec <= sec)
        if blow.any():
            gb = np.where(M > 0, 100.0 - M, -50.0)
            pri = np.where(blow[:, None], gb, pri)
    pri = np.where(M > 0, pri, -100.0)
    pri = np.where(T.out[None, :], -1e9, pri)
    picked = np.zeros((S, n), bool)
    out = np.zeros((S, 5), int)
    isC = (T.posg == 2)[None, :]
    isG = (T.posg == 0)[None, :]
    for k in range(5):
        cand = np.where(picked, -np.inf, pri)
        nC = (picked & isC).sum(1)
        cand = np.where((nC >= prm["sim"]["max_c"])[:, None] & isC, cand - 1000.0, cand)
        if k == 4:
            noG = ~(picked & isG).any(1)
            cand = np.where(noG[:, None] & ~isG, cand - 1000.0, cand)
        j = np.argmax(cand, 1)
        out[:, k] = j
        picked[np.arange(S), j] = True
    return out, picked


def cat_sample(w, r):
    """w: (n,k) probabilities (rows sum to ~1), r: (n,) uniforms -> index."""
    c = np.cumsum(w, 1)
    c = c / c[:, -1:]
    return np.minimum((c < r[:, None]).sum(1), w.shape[1] - 1)


# %% the game simulator
def context_pts100(prm, opts):
    """Per-100 offensive adjustments for (home, away)."""
    c = prm["context"]
    P = prm["league"]["poss_per_team_game"]
    mh = 0.0
    if not opts.get("neutral", False):
        mh += c["hca_pts"]
    mh += c["b2b_pts"] * (float(opts.get("home_b2b", False)) - float(opts.get("away_b2b", False)))
    rh = min(max(opts.get("home_rest_days", 2), 1), 4) - 1
    ra = min(max(opts.get("away_rest_days", 2), 1), 4) - 1
    mh += c["rest_day_pts"] * (rh - ra)
    mh += c["travel_pts_per_1000mi"] * (opts.get("home_travel_miles", 0.0) - opts.get("away_travel_miles", 0.0)) / 1000.0
    return (mh / 2) / P * 100, -(mh / 2) / P * 100


def simulate(prm, home, away, n_sims=10000, seed=1, opts=None, keep_games=False):
    opts = opts or {}
    rng = np.random.default_rng(seed)
    H = home if isinstance(home, Team) else Team(prm, home)
    A = away if isinstance(away, Team) else Team(prm, away)
    TM = [H, A]
    S = n_sims
    sim = prm["sim"]
    lg = prm["league"]
    ctx = context_pts100(prm, opts)
    pace_off = [prm["pace"]["team_off"].get(str(T.tid), 0.0) if T.tid is not None else 0.0 for T in TM]
    pace_def = [prm["pace"]["team_def"].get(str(T.tid), 0.0) if T.tid is not None else 0.0 for T in TM]
    # minutes targets
    Ms = []
    for T in TM:
        sd = np.minimum(T.min_sd, 0.5 * T.minutes + 2.0)
        Mt = np.clip(T.minutes[None, :] + sd[None, :] * rng.standard_normal((S, T.n)), 0, sim["min_cap"])
        Mt = np.where(T.minutes[None, :] > 0, Mt, 0.0)
        for _ in range(3):
            Mt = np.minimum(Mt * (200.0 / np.maximum(Mt.sum(1, keepdims=True), 1e-9)), sim["min_cap"])
        Ms.append(Mt)
    NP = H.n + A.n
    off_idx = [0, H.n]
    box = np.zeros((len(STATS), S, NP))
    score = np.zeros((S, 2))
    qs = np.zeros((S, 4 + sim["max_ot"], 2))
    played = [np.zeros((S, T.n)) for T in TM]
    consec = [np.zeros((S, T.n)) for T in TM]
    poss_team = (rng.random(S) < 0.5).astype(int)
    first_team = poss_team.copy()
    n_poss = np.zeros(S)
    seg_len = sim["segment_sec"]
    nseg_reg = int(2400 / seg_len)
    ar = np.arange(S)
    steal_flag = np.zeros(S, bool)
    clock = np.zeros(S)
    lineup_log = []

    def run_segment(active_sims, t0, t1, period, seg, ot):
        nonlocal poss_team, steal_flag
        idx = np.nonzero(active_sims)[0]
        if len(idx) == 0:
            return
        margin_h = score[idx, 0] - score[idx, 1]
        rem_reg = np.full(len(idx), max(2400.0 - t0, 0.0))
        lus, picks = [], []
        for ti, T in enumerate(TM):
            mar = margin_h if ti == 0 else -margin_h
            lu, pk = choose_lineups(T, Ms[ti][idx], played[ti][idx], consec[ti][idx], seg, nseg_reg, mar, period, rem_reg, prm, ot)
            consec[ti][idx] = np.where(pk, consec[ti][idx] + 1, 0)
            lus.append(lu)
            picks.append(pk)
        if keep_games:
            lineup_log.append((idx, t0, t1, lus[0].copy(), lus[1].copy()))
        cal = [calibrate(prm, TM[0], TM[1], lus[0], lus[1], ctx[0], pace_off[0], pace_def[1]),
               calibrate(prm, TM[1], TM[0], lus[1], lus[0], ctx[1], pace_off[1], pace_def[0])]
        pend = period_end(period)
        t = np.maximum(clock[idx], t0)
        live = (t < t1 - 1e-9) & (t < pend - 1e-9)
        while live.any():
            j = np.nonzero(live)[0]
            gs = idx[j]
            o = poss_team[gs]
            d_ = 1 - o
            rem = pend - t[j]
            # gather per-sim matchup params by offence side
            def gat(key):
                a0, a1 = cal[0][key][j], cal[1][key][j]
                sh = (o == 0).reshape((-1,) + (1,) * (a0.ndim - 1))
                return np.where(sh, a0, a1)
            W, Tt, Ff, Q, MIX = gat("w"), gat("t"), gat("f"), gat("q"), gat("mix")
            porb, porbft, blkf, stlp, mu = gat("porb"), gat("porb_ft"), gat("blkf"), gat("stlp"), gat("mu")
            offL = np.where((o == 0)[:, None], lus[0][j], lus[1][j])
            defL = np.where((o == 0)[:, None], lus[1][j], lus[0][j])
            offG = offL + np.where(o == 0, 0, H.n)[:, None]
            defG = defL + np.where(o == 0, H.n, 0)[:, None]
            so = score[gs, o]
            sd_ = score[gs, d_]
            lead = so - sd_
            late = (period >= 4) & (rem <= 120)
            mu = np.where(steal_flag[gs], mu * 0.7, mu)
            mu = np.where(late & (lead > 0) & (rem > 24), 21.0, mu)
            mu = np.where(late & (lead < 0), 9.0, mu)
            foul = (period >= 4) & (rem <= sim["late_foul_sec"]) & (lead >= 1) & (lead <= sim["late_foul_max_lead"])
            dur = rng.gamma(prm["pace"]["gamma_shape"], mu / prm["pace"]["gamma_shape"])
            dur = np.where(foul, 2.0 + rng.gamma(2.0, 1.0, len(j)), dur)
            dur = np.minimum(dur, rem)
            trail3 = late & (lead <= -3)
            steal_flag[gs] = False
            n_poss[gs] += 1
            # technical FT
            tech = rng.random(len(j)) < lg["tech_ft_per_poss"]
            if tech.any():
                k = np.nonzero(tech)[0]
                FTPo = np.where((o[k] == 0)[:, None], H.ftp[lus[0][j[k]]], A.ftp[lus[1][j[k]]])
                best = np.argmax(FTPo, 1)
                made = rng.random(len(k)) < lg["tech_ft_pct"]
                pidg = offG[k, best]
                box[SI["pts"], gs[k], pidg] += made
                box[SI["fta"], gs[k], pidg] += 1
                box[SI["ftm"], gs[k], pidg] += made
                score[gs[k], o[k]] += made
            elapsed = dur.copy()
            alive = np.ones(len(j), bool)
            first = True
            for play in range(6):
                if not alive.any():
                    break
                k = np.nonzero(alive)[0]
                nk = len(k)
                gk = gs[k]
                ok = o[k]
                r = rng.random((nk, 8))
                u = cat_sample(W[k], r[:, 0])
                pid = offG[k, u]
                tv = Tt[k, u]
                fv = Ff[k, u]
                isfoul = foul[k] & first
                if isfoul.any():
                    # intentional foul: FT shooter by usage x FT%
                    wf = W[k] * np.where(ok[:, None] == 0, H.ftp[lus[0][j[k]]], A.ftp[lus[1][j[k]]])
                    uf = cat_sample(wf, r[:, 0])
                    u = np.where(isfoul, uf, u)
                    pid = offG[k, u]
                ftp = np.where(ok == 0, H.ftp[np.minimum(pid, H.n - 1)], A.ftp[np.clip(pid - H.n, 0, A.n - 1)])
                is_to = (r[:, 1] < tv) & ~isfoul
                is_sf = ((r[:, 1] >= tv) & (r[:, 1] < tv + fv)) | isfoul
                is_fga = ~is_to & ~is_sf
                cont = np.zeros(nk, bool)
                # --- turnovers
                if is_to.any():
                    m = np.nonzero(is_to)[0]
                    box[SI["tov"], gk[m], pid[m]] += 1
                    st = r[m, 2] < stlp[k[m]]
                    if st.any():
                        mm = m[st]
                        dl = defL[k[mm]]
                        ws = np.where((ok[mm] == 0)[:, None], A.stl[np.minimum(dl, A.n - 1)], H.stl[np.minimum(dl, H.n - 1)])
                        sj = cat_sample(ws, r[mm, 3])
                        box[SI["stl"], gk[mm], defG[k[mm], sj]] += 1
                        steal_flag[gk[mm]] = True
                # --- shooting-foul trips (and intentional fouls)
                if is_sf.any():
                    m = np.nonzero(is_sf)[0]
                    tr3 = np.where(ok[m] == 0, H.trip3[np.minimum(pid[m], H.n - 1)], A.trip3[np.clip(pid[m] - H.n, 0, A.n - 1)])
                    nft = np.where(isfoul[m], 2, np.where(r[m, 2] < tr3, 3, 2))
                    rr = rng.random((len(m), 3))
                    mk = (rr < ftp[m, None]) & (np.arange(3)[None, :] < nft[:, None])
                    pts = mk.sum(1)
                    last_made = mk[np.arange(len(m)), nft - 1]
                    box[SI["pts"], gk[m], pid[m]] += pts
                    box[SI["fta"], gk[m], pid[m]] += nft
                    box[SI["ftm"], gk[m], pid[m]] += pts
                    score[gk[m], ok[m]] += pts
                    miss = ~last_made
                    if miss.any():
                        mm = m[miss]
                        orb = r[mm, 4] < porbft[k[mm]]
                        cont[mm[orb]] = True
                        _rebound(box, gk, mm, orb, r, k, offL, defL, offG, defG, ok, H, A, lg)
                # --- field-goal attempts
                if is_fga.any():
                    m = np.nonzero(is_fga)[0]
                    mx = MIX[k[m], u[m]]
                    if trail3[k[m]].any():
                        mx = np.where(trail3[k[m]][:, None], mx * np.array([1, 1, 1, 1.8, 1.8]), mx)
                    z = cat_sample(mx, r[m, 2])
                    qz = Q[k[m], u[m], z]
                    made = r[m, 3] < qz
                    three = z >= 3
                    box[SI["fga"], gk[m], pid[m]] += 1
                    box[SI["fg3a"], gk[m], pid[m]] += three
                    mm = m[made]
                    if len(mm):
                        v = np.where(three[made], 3, 2)
                        box[SI["fgm"], gk[mm], pid[mm]] += 1
                        box[SI["fg3m"], gk[mm], pid[mm]] += three[made]
                        box[SI["pts"], gk[mm], pid[mm]] += v
                        score[gk[mm], ok[mm]] += v
                        # and-one
                        a1 = np.where(ok[mm] == 0, H.and1[np.minimum(pid[mm], H.n - 1)], A.and1[np.clip(pid[mm] - H.n, 0, A.n - 1)])
                        ia = r[mm, 4] < a1
                        if ia.any():
                            m2 = mm[ia]
                            ft_ok = rng.random(len(m2)) < ftp[m2]
                            box[SI["fta"], gk[m2], pid[m2]] += 1
                            box[SI["ftm"], gk[m2], pid[m2]] += ft_ok
                            box[SI["pts"], gk[m2], pid[m2]] += ft_ok
                            score[gk[m2], ok[m2]] += ft_ok
                        # assist
                        astd = np.where(ok[mm] == 0, H.astd[np.minimum(pid[mm], H.n - 1)], A.astd[np.clip(pid[mm] - H.n, 0, A.n - 1)])
                        pa = expit(logit(astd) + np.array(lg["astd_zone_offset"])[z[made]])
                        ia = r[mm, 5] < pa
                        if ia.any():
                            m2 = mm[ia]
                            ol = offL[k[m2]]
                            wa = np.where((ok[m2] == 0)[:, None], H.ast[np.minimum(ol, H.n - 1)], A.ast[np.minimum(ol, A.n - 1)])
                            wa[np.arange(len(m2)), u[m2]] = 0.0
                            aj = cat_sample(wa, r[m2, 6])
                            box[SI["ast"], gk[m2], offG[k[m2], aj]] += 1
                    mm = m[~made]
                    if len(mm):
                        zm = z[~made]
                        pb = np.clip(np.array(lg["blk_given_miss_zone"])[zm] * blkf[k[mm]], 0, 0.6)
                        ib = r[mm, 4] < pb
                        if ib.any():
                            m2 = mm[ib]
                            dl = defL[k[m2]]
                            wb = np.where((ok[m2] == 0)[:, None], A.blk[np.minimum(dl, A.n - 1)], H.blk[np.minimum(dl, H.n - 1)])
                            bj = cat_sample(wb, r[m2, 6])
                            box[SI["blk"], gk[m2], defG[k[m2], bj]] += 1
                        orb = r[mm, 7] < porb[k[mm]]
                        cont[mm[orb]] = True
                        _rebound(box, gk, mm, orb, rng.random((len(mm), 8)), k, offL, defL, offG, defG, ok, H, A, lg, local=True)
                # continuation after offensive rebounds
                cidx = k[cont]
                if len(cidx):
                    extra = rng.gamma(2.0, prm["pace"]["orb_play_sec"] / 2.0, len(cidx))
                    room = rem[cidx] - elapsed[cidx]
                    ok_c = room > 0.5
                    elapsed[cidx] = np.minimum(elapsed[cidx] + extra, rem[cidx])
                    cont_ok = np.zeros(len(j), bool)
                    cont_ok[cidx[ok_c]] = True
                    alive = cont_ok
                else:
                    alive = np.zeros(len(j), bool)
                first = False
            # possession over: time, minutes, switch
            t[j] = t[j] + elapsed
            for ti in (0, 1):
                L_ = lus[ti][j]
                off0 = 0 if ti == 0 else H.n
                for c in range(5):
                    box[SI["sec"], gs, off0 + L_[:, c]] += elapsed
                    played[ti][gs, L_[:, c]] += elapsed
            poss_team[gs] = 1 - poss_team[gs]
            live[j] = (t[j] < t1 - 1e-9) & (t[j] < pend - 1e-9)
        clock[idx] = t

    def period_end(p):
        return 600.0 * p if p <= 4 else 2400.0 + 300.0 * (p - 4)

    # regulation
    for seg in range(nseg_reg):
        t0 = seg * seg_len
        period = int(t0 // 600) + 1
        if t0 % 600 == 0 and period > 1:
            # quarter possession arrow: team that lost the opening tip starts Q2 and Q3; winner starts Q4
            poss_team = np.where(period in (2, 3), 1 - first_team, first_team)
        run_segment(np.ones(S, bool), t0, t0 + seg_len, period, seg, False)
        if (t0 + seg_len) % 600 == 0:
            qs[:, period - 1] = score - qs[:, :period - 1].sum(1)
    # overtime
    for ot in range(sim["max_ot"]):
        tied = score[:, 0] == score[:, 1]
        if not tied.any():
            break
        period = 5 + ot
        base = 2400.0 + 300.0 * ot
        poss_team = np.where(tied, (rng.random(S) < 0.5).astype(int), poss_team)
        before = score.copy()
        nseg_ot = int(300 / sim["ot_segment_sec"])
        for s2 in range(nseg_ot):
            run_segment(tied, base + s2 * sim["ot_segment_sec"], base + (s2 + 1) * sim["ot_segment_sec"], period, 0, True)
        qs[:, 4 + ot] = np.where(tied[:, None], score - before, 0)
    # unresolved after max OT (vanishingly rare): coin flip point
    tied = score[:, 0] == score[:, 1]
    if tied.any():
        wpt = (rng.random(S) < 0.5).astype(int)
        score[tied, wpt[tied]] += 1
    res = dict(score=score, quarters=qs, box=box, n_poss=n_poss, home=H, away=A)
    if keep_games:
        res["lineups"] = lineup_log
    return res


def _rebound(box, gk, mm, orb, r, k, offL, defL, offG, defG, ok, H, A, lg, local=False):
    """Credit individual rebounds. mm indexes the play arrays; r random matrix (rows aligned with mm if local)."""
    rr = r if local else r[mm]
    o_m = ok[mm]
    # offensive
    io = np.nonzero(orb)[0]
    if len(io):
        cred = rr[io, 5] < lg["orb_player_credit"]
        if cred.any():
            ii = io[cred]
            ol = offL[k[mm[ii]]]
            w = np.where((o_m[ii] == 0)[:, None], H.orb[np.minimum(ol, H.n - 1)], A.orb[np.minimum(ol, A.n - 1)])
            pj = cat_sample(w, rr[ii, 6])
            box[SI["orb"], gk[mm[ii]], offG[k[mm[ii]], pj]] += 1
    idr = np.nonzero(~orb)[0]
    if len(idr):
        cred = rr[idr, 5] < lg["drb_player_credit"]
        if cred.any():
            ii = idr[cred]
            dl = defL[k[mm[ii]]]
            w = np.where((o_m[ii] == 0)[:, None], A.drb[np.minimum(dl, A.n - 1)], H.drb[np.minimum(dl, H.n - 1)])
            pj = cat_sample(w, rr[ii, 6])
            box[SI["drb"], gk[mm[ii]], defG[k[mm[ii]], pj]] += 1


# %% summaries
LADDER_STEP = {"min": 2, "pts": 2, "reb": 1, "ast": 1, "fg3m": 1, "stl": 1, "blk": 1, "tov": 1, "pra": 2, "pr": 2, "pa": 2}
QS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]


def ladder(x, step):
    m = x.mean()
    c = np.floor(m / step) * step + (0.5 if step == 1 else 1.0)
    if step == 2:
        c = np.round(m) + 0.5
    lines = [c + step * k for k in range(-3, 4)]
    lines = [ln for ln in lines if ln > 0]
    return lines, [float((x > ln).mean()) for ln in lines]


def player_summary(res, team_idx):
    box = res["box"]
    T = res["home"] if team_idx == 0 else res["away"]
    off0 = 0 if team_idx == 0 else res["home"].n
    out = []
    for i in range(T.n):
        g = off0 + i
        st = {k: box[SI[k], :, g] for k in STATS}
        d = dict(min=st["sec"] / 60.0, pts=st["pts"], reb=st["orb"] + st["drb"], ast=st["ast"], fg3m=st["fg3m"],
                 stl=st["stl"], blk=st["blk"], tov=st["tov"])
        d["pra"] = d["pts"] + d["reb"] + d["ast"]
        d["pr"] = d["pts"] + d["reb"]
        d["pa"] = d["pts"] + d["ast"]
        rec = dict(id=int(T.ids[i]), name=T.names[i], proj_min=float(T.minutes[i]), out=bool(T.out[i]))
        for k, x in d.items():
            lines, po = ladder(x, LADDER_STEP[k])
            rec[k] = dict(mean=float(x.mean()), sd=float(x.std()), q=[float(v) for v in np.quantile(x, QS)], lines=lines, p_over=po)
        rec["fga"] = float(st["fga"].mean())
        rec["fg3a"] = float(st["fg3a"].mean())
        rec["fta"] = float(st["fta"].mean())
        rec["p_dd"] = float((((d["pts"] >= 10).astype(int) + (d["reb"] >= 10) + (d["ast"] >= 10)) >= 2).mean())
        out.append(rec)
    return out


def hist(x, lo, hi):
    x = np.clip(np.round(x).astype(int), lo, hi)
    c = np.bincount(x - lo, minlength=hi - lo + 1)
    return dict(lo=lo, hi=hi, p=(c / c.sum()).tolist())


def game_summary(res):
    sc = res["score"]
    h, a = sc[:, 0], sc[:, 1]
    mar = h - a
    tot = h + a
    q = res["quarters"]
    out = dict(n_sims=int(len(h)), home_win=float((mar > 0).mean()),
               margin=dict(mean=float(mar.mean()), sd=float(mar.std()), q=[float(v) for v in np.quantile(mar, QS)]),
               total=dict(mean=float(tot.mean()), sd=float(tot.std()), q=[float(v) for v in np.quantile(tot, QS)]),
               home_pts=dict(mean=float(h.mean()), sd=float(h.std()), q=[float(v) for v in np.quantile(h, QS)]),
               away_pts=dict(mean=float(a.mean()), sd=float(a.std()), q=[float(v) for v in np.quantile(a, QS)]),
               p_ot=float((q[:, 4:].sum((1, 2)) > 0).mean()),
               poss_per_team=float(res["n_poss"].mean() / 2),
               margin_hist=hist(mar, -50, 50), total_hist=hist(tot, 110, 240))
    per = []
    for k in range(4):
        qm = q[:, k, 0] - q[:, k, 1]
        qt = q[:, k].sum(1)
        per.append(dict(home=float(q[:, k, 0].mean()), away=float(q[:, k, 1].mean()), home_win=float((qm > 0).mean()),
                        tie=float((qm == 0).mean()), margin_sd=float(qm.std()), total_sd=float(qt.std())))
    out["quarters"] = per
    halves = []
    for hh in (0, 1):
        hs = q[:, 2 * hh:2 * hh + 2].sum(1)
        if hh == 1:
            hs = hs + q[:, 4:].sum(1)  # second half includes OT (common settlement convention)
        hm = hs[:, 0] - hs[:, 1]
        halves.append(dict(home=float(hs[:, 0].mean()), away=float(hs[:, 1].mean()), home_win=float((hm > 0).mean()),
                           tie=float((hm == 0).mean()), margin_mean=float(hm.mean()), margin_sd=float(hm.std()),
                           total_mean=float(hs.sum(1).mean()), total_sd=float(hs.sum(1).std())))
    out["halves"] = halves
    return out


def load_params():
    p = json.loads((PROC / "sim_params.json").read_text())
    return p


# %% quick check
if __name__ == "__main__":
    prm = load_params()
    t = time.time()
    r = simulate(prm, 17, 9, n_sims=10000)
    dt = time.time() - t
    g = game_summary(r)
    print(f"sim 10k: {dt:.2f}s  home win {g['home_win']:.3f} margin {g['margin']['mean']:.1f}±{g['margin']['sd']:.1f} "
          f"total {g['total']['mean']:.1f}±{g['total']['sd']:.1f} poss {g['poss_per_team']:.1f} OT {g['p_ot']:.3f}")
