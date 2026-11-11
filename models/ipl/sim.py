"""Vectorised ball-by-ball T20 match simulator driven by the exported sim_params.json.

The JS engine (docs/models/ipl/sim.js) implements the same logic; keep the two in step.
"""
# %% imports
import json

import numpy as np

from models.ipl.config import CLASSES, EXPORT

C = {c: i for i, c in enumerate(CLASSES)}
NC = len(CLASSES)
BAT_RUNS = np.array([0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 6])
TOP_THRESH = [10, 20, 30, 40, 50, 75, 100]


# %% params


class Params:
    def __init__(self, raw):
        self.raw = raw
        self.base = np.asarray(raw["base"], float).reshape(2, 20, 8, NC)
        self.bf = np.asarray(raw["bf"], float).reshape(3, 9, NC)
        self.chase = np.asarray(raw["chase"], float).reshape(3, 8, NC)
        self.bf_edges = np.asarray(raw["bf_edges"])
        self.rrr_edges = np.asarray(raw["rrr_edges"], float)
        self.early_bf = raw["early_bf"]
        self.sub = {k: np.asarray(v, float) for k, v in raw["sub"].items()}
        self.sub_lhb = {k: np.asarray(v, float) for k, v in raw["sub_lhb"].items()}
        self.env = {k: np.asarray(v, float) for k, v in raw["env"].items()}
        self.ex = raw["extras"]

    @classmethod
    def load(cls, path=None):
        return cls(json.loads((path or EXPORT / "sim_params.json").read_text()))

    def batter(self, pid):
        b = self.raw["batters"].get(pid)
        if b is None:
            b = self.raw["batter_priors"]["middle"]
        return b

    def bowler(self, pid):
        w = self.raw["bowlers"].get(pid)
        if w is None:
            w = self.raw["bowler_priors"]["pace_reg"]
        return w


# %% bowling schedule (captain heuristic; mirrored in sim.js)
PHASE_OF = [0] * 6 + [1] * 9 + [2] * 5


def bowling_schedule(plan, n_overs=20):
    """plan: list of dicts {id, pp, mid, death} (overs per phase). Returns list of bowler ids, one per over.

    Greedy: each over goes to the feasible bowler with the most remaining overs planned for that phase
    (ties: most remaining overall). Feasible = not the previous over's bowler, under 4 overs, and the
    remaining quotas can still be scheduled without consecutive overs.
    """
    ids = [p["id"] for p in plan]
    nb = len(ids)
    ph_q = np.array([[p.get("pp", 0), p.get("mid", 0), p.get("death", 0)] for p in plan], float)
    cap = np.minimum(4, np.round(ph_q.sum(1))).astype(int)
    if cap.sum() < n_overs:  # top up quotas so 20 overs can be bowled
        order = np.argsort(-ph_q.sum(1), kind="stable")
        i = 0
        while cap.sum() < n_overs and i < 200:
            j = order[i % nb]
            if cap[j] < 4:
                cap[j] += 1
            i += 1
    used = np.zeros(nb, int)
    phase_used = np.zeros((nb, 3))
    sched = []
    last = -1
    for o in range(n_overs):
        ph = PHASE_OF[o] if n_overs == 20 else 2
        R = n_overs - o
        best, best_s = -1, -1e9
        for j in range(nb):
            if j == last or used[j] >= cap[j]:
                continue
            rem = cap - used
            rem[j] -= 1
            R2 = R - 1
            ok = rem.sum() >= R2
            for k in range(nb):
                lim = (R2 // 2) if k == j else ((R2 + 1) // 2)
                if rem[k] > lim:
                    ok = False
                    break
            if not ok:
                continue
            s = (ph_q[j, ph] - phase_used[j, ph]) * 10 + (cap[j] - used[j]) * 0.1 - j * 1e-4
            if s > best_s:
                best, best_s = j, s
        if best < 0:  # fallback: anyone but last
            cands = [j for j in range(nb) if j != last] or [0]
            best = min(cands, key=lambda j: used[j])
        sched.append(ids[best])
        used[best] += 1
        phase_used[best, ph] += 1
        last = best
    return sched


# %% innings engine


def _sample(p, u):
    c = np.cumsum(p, axis=1)
    return np.minimum((c < u[:, None]).sum(1), p.shape[1] - 1)


def _dist(d):
    return np.asarray(d["v"]), np.cumsum(np.asarray(d["p"], float)) / np.sum(d["p"])


def _draw(d, u):
    v, cp = d
    return v[np.minimum(np.searchsorted(cp, u, side="right"), len(v) - 1)]


def sim_innings(P, rng, n, order, sched, venue, env, inn, target=None, max_wkts=10, max_overs=20,
                track=True):
    """order: list of 11 batter ids; sched: list of bowler ids (len max_overs)."""
    nbat = len(order)
    bt = [P.batter(b) for b in order]
    BB = np.array([b["b"] for b in bt], float)
    BPH = np.stack([np.array([b["pp"] for b in bt]), np.zeros((nbat, NC)), np.array([b["de"] for b in bt])])
    BSP = np.array([b["sp"] for b in bt], float)
    BEA = np.array([b["ea"] for b in bt], float)
    LHB = np.array([1.0 if b.get("hand") == "L" else 0.0 for b in bt])
    bowl_ids = list(dict.fromkeys(sched))
    bix = {b: i for i, b in enumerate(bowl_ids)}
    nbw = len(bowl_ids)
    V = venue
    e_wide, e_nb, e_bye, e_ro = (_dist(P.ex["wide_runs"]), _dist(P.ex["nb_bat"]), _dist(P.ex["bye_runs"]),
                                  _dist(P.ex["runout_runs"]))
    q_ro_striker = P.ex["runout_striker"]
    score = np.zeros(n, int)
    wk = np.zeros(n, int)
    legal = np.zeros(n, int)
    stk = np.zeros(n, int)
    nst = np.ones(n, int)
    nxt = np.full(n, 2)
    done = np.zeros(n, bool)
    free = np.zeros(n, bool)
    bf = np.zeros((n, nbat), int)
    br = np.zeros((n, nbat), int)
    b4 = np.zeros((n, nbat), int)
    b6 = np.zeros((n, nbat), int)
    out = np.zeros((n, nbat), bool)
    batted = np.zeros((n, nbat), bool)
    batted[:, 0] = batted[:, 1] = True
    wb = np.zeros((n, nbw), int)
    wr = np.zeros((n, nbw), int)
    ww = np.zeros((n, nbw), int)
    pp_score = np.zeros(n, int)
    fow1 = np.full(n, -1)
    fours = np.zeros(n, int)
    sixes = np.zeros(n, int)
    wides = np.zeros(n, int)
    extras = np.zeros(n, int)
    ar = np.arange(n)
    tgt = target
    for o in range(max_overs):
        ph = PHASE_OF[o] if max_overs == 20 else 2
        bid = sched[o]
        bw = P.bowler(bid)
        j = bix[bid]
        spin = 1.0 if bw.get("spin") else 0.0
        const = (env + np.asarray(V["base"]) + (np.asarray(V["i2"]) if inn == 2 else 0) + spin * np.asarray(V["spin"])
                 + P.sub[bw["sub"]] + np.asarray(bw["b"]) + (np.asarray(bw["pp"]) if ph == 0 else 0)
                 + (np.asarray(bw["de"]) if ph == 2 else 0))
        lhb_o = P.sub_lhb[bw["sub"]] + np.asarray(bw["lh"])
        M = const[None, :] + BB + BPH[ph] + spin * BSP + LHB[:, None] * lhb_o[None, :]
        oo = o if max_overs == 20 else 19
        lio = np.zeros(n, int)
        for step in range(30):
            act = ~done & (lio < 6)
            if not act.any():
                break
            idx = ar[act]
            s = stk[idx]
            sbf = bf[idx, s]
            lg = P.base[inn - 1, oo, np.minimum(wk[idx], 7)] + M[s]
            lg += BEA[s] * (sbf < P.early_bf)[:, None]
            bfb = np.searchsorted(P.bf_edges, sbf, side="right") - 1
            lg += P.bf[ph, bfb]
            if tgt is not None:
                bl = np.maximum(max_overs * 6 - legal[idx], 1)
                rrr = (tgt - score[idx]) * 6.0 / bl
                rb = np.searchsorted(P.rrr_edges, rrr, side="right") - 1
                lg += P.chase[ph, np.clip(rb, 0, 7)]
            fh = free[idx]
            lg[fh, C["wicket"]] = -50
            if step >= 14:  # pathological extras run: force a legal ball
                lg[:, C["wide"]] = -50
                lg[:, C["noball"]] = -50
            lg -= lg.max(1, keepdims=True)
            p = np.exp(lg)
            p /= p.sum(1, keepdims=True)
            k = _sample(p, rng.random(len(idx)))
            runs = np.zeros(len(idx), int)     # total runs to the score
            batr = BAT_RUNS[k].copy()          # runs to batter
            ran = batr.copy()                  # runs physically run (for strike rotation)
            conc = np.zeros(len(idx), int)     # runs against bowler
            isl = k > C["noball"]              # legal delivery
            m = k == C["wide"]
            if m.any():
                wrn = _draw(e_wide, rng.random(m.sum()))
                runs[m] = wrn
                conc[m] = wrn
                ran[m] = np.where(wrn == 5, 0, wrn - 1)
            m = k == C["noball"]
            if m.any():
                nbr = _draw(e_nb, rng.random(m.sum()))
                batr[m] = nbr
                ran[m] = np.where((nbr == 4) | (nbr == 6), 0, nbr)
                runs[m] = 1 + nbr
                conc[m] = 1 + nbr
            m = k == C["byes"]
            if m.any():
                byr = _draw(e_bye, rng.random(m.sum()))
                runs[m] = byr
                ran[m] = np.where(byr == 4, 0, byr)
            m = k == C["runout"]
            if m.any():
                ror = _draw(e_ro, rng.random(m.sum()))
                batr[m] = ror
                ran[m] = ror
            bat_scoring = (k >= C["r0"]) | (k == C["noball"]) | (k == C["runout"])
            runs = np.where(bat_scoring & (k != C["noball"]), batr, runs)
            conc = np.where(bat_scoring & (k != C["noball"]), batr, conc)
            # batter stats
            br[idx, s] += np.where(bat_scoring, batr, 0)
            bf[idx, s] += (k != C["wide"]).astype(int)
            b4[idx, s] += (batr == 4) & bat_scoring & (k != C["runout"])
            b6[idx, s] += (batr == 6) & bat_scoring & (k != C["runout"])
            fours[idx] += (batr == 4) & bat_scoring & (k != C["runout"])
            sixes[idx] += (batr == 6) & bat_scoring & (k != C["runout"])
            wides[idx] += (k == C["wide"])
            extras[idx] += np.where((k <= C["byes"]), np.where(k == C["noball"], 1, runs), 0)
            score[idx] += runs
            wb[idx, j] += isl
            wr[idx, j] += conc
            ww[idx, j] += (k == C["wicket"])
            legal[idx] += isl
            lio[idx] += isl
            free[idx] = np.where(k == C["noball"], True, np.where(isl, False, free[idx]))
            # strike rotation from runs run
            sw = (ran % 2) == 1
            a, bb = stk[idx].copy(), nst[idx].copy()
            stk[idx] = np.where(sw, bb, a)
            nst[idx] = np.where(sw, a, bb)
            # dismissals
            wkt = (k == C["wicket"]) | (k == C["runout"])
            if wkt.any():
                wi = idx[wkt]
                ro = k[wkt] == C["runout"]
                # bowler wicket: striker (the batter who faced) is out; runout: striker w.p. q
                faced = s[wkt]
                ro_striker = rng.random(len(wi)) < q_ro_striker
                # after rotation the facing batter may be at either end
                victim = np.where(ro & ~ro_striker, np.where(stk[wi] == faced, nst[wi], stk[wi]), faced)
                out[wi, victim] = True
                fw = fow1[wi] < 0
                fow1[wi[fw]] = score[wi[fw]]
                wk[wi] += 1
                newb = nxt[wi]
                can = newb < nbat
                at_stk = stk[wi] == victim
                nb_ = np.minimum(newb, nbat - 1)
                stk[wi] = np.where(at_stk & can, nb_, stk[wi])
                nst[wi] = np.where(~at_stk & can, nb_, nst[wi])
                batted[wi[can], nb_[can]] = True
                nxt[wi] += 1
                done[wi] |= (wk[wi] >= min(max_wkts, nbat - 1))
            if tgt is not None:
                done[idx] |= score[idx] >= tgt
        if o == 5:
            pp_score[:] = score
        # end of over: swap strike
        a = stk.copy()
        stk = np.where(done, stk, nst)
        nst = np.where(done, nst, a)
        done |= legal >= max_overs * 6
    if max_overs < 6:
        pp_score[:] = score
    fow1 = np.where(fow1 < 0, score, fow1)
    res = dict(score=score, wk=wk, legal=legal, pp=pp_score, fow1=fow1, fours=fours, sixes=sixes,
               wides=wides, extras=extras)
    if track:
        res.update(bat_runs=br, bat_balls=bf, bat_4=b4, bat_6=b6, bat_out=out, batted=batted,
                   bowl_ids=bowl_ids, bowl_balls=wb, bowl_runs=wr, bowl_wkts=ww)
    return res


# %% match


def team_inputs(P, team):
    sched = team.get("schedule") or bowling_schedule(team["plan"])
    return team["order"][:11], sched


def sim_match(P, A, B, venue_id, n=10000, seed=0, bat_first=None, env_key=None):
    """A, B: dict(name, order=[11 ids], plan=[{id,pp,mid,death}] or schedule=[20 ids]).
    bat_first: 'A', 'B' or None (half the sims each way)."""
    rng = np.random.default_rng(seed)
    V = P.raw["venues"].get(venue_id) or P.raw["venue_neutral"]
    env = P.env[env_key or P.raw["default_env"]]
    oa, sa = team_inputs(P, A)
    ob, sb = team_inputs(P, B)
    if bat_first is None:
        h = n // 2
        r1 = sim_match(P, A, B, venue_id, h, seed * 2 + 1, "A", env_key)
        r2 = sim_match(P, A, B, venue_id, n - h, seed * 2 + 2, "B", env_key)
        return _concat(r1, r2)
    first, second = (("A", oa, sa, "B", ob, sb) if bat_first == "A" else ("B", ob, sb, "A", oa, sa))
    i1 = sim_innings(P, rng, n, first[1], second[2], V, env, 1)
    i2 = sim_innings(P, rng, n, second[1], first[2], V, env, 2, target=i1["score"] + 1)
    s1, s2 = i1["score"], i2["score"]
    first_wins = (s1 > s2).astype(float)
    tie = s1 == s2
    if tie.any():
        first_wins[tie] = super_over(P, rng, tie.sum(), first, second, V, env)
    out = {first[0]: i1, second[0]: i2, "first": np.full(n, first[0]), "winA": first_wins if first[0] == "A" else 1 - first_wins,
           "tie": tie}
    return out


def super_over(P, rng, m, first, second, V, env):
    """Simplified super over: team batting second bats first; top-3 of order; plan's top death bowler."""
    def death_bowler(team_sched):
        last5 = team_sched[15:]
        return max(set(last5), key=last5.count)
    so1 = sim_innings(P, rng, m, second[1][:3], [death_bowler(first[2])], V, env, 1, max_wkts=2, max_overs=1, track=False)
    so2 = sim_innings(P, rng, m, first[1][:3], [death_bowler(second[2])], V, env, 2, target=so1["score"] + 1,
                      max_wkts=2, max_overs=1, track=False)
    fw = (so2["score"] > so1["score"]).astype(float)
    t = so2["score"] == so1["score"]
    fw[t] = rng.random(t.sum()) < 0.5
    return fw


def _concat(r1, r2):
    out = {"winA": np.concatenate([r1["winA"], r2["winA"]]), "tie": np.concatenate([r1["tie"], r2["tie"]]),
           "first": np.concatenate([r1["first"], r2["first"]]), "parts": [r1, r2]}
    return out


# %% summaries


def _q(x, qs=(5, 25, 50, 75, 95)):
    return [float(v) for v in np.percentile(x, qs)]


def summarize(res, A, B):
    """Collapse raw sim output into the matchup summary (same structure as sim.js summarize)."""
    parts = res.get("parts", [res])
    out = {"n": int(len(res["winA"])), "p_win_A": float(res["winA"].mean()), "p_tie": float(res["tie"].mean())}
    for side, team in (("A", A), ("B", B)):
        inns = [p[side] for p in parts]
        firsts = [p["first"][0] == side for p in parts]
        cat = lambda k: np.concatenate([i[k] for i in inns])
        tot = cat("score")
        tm = {"total_mean": float(tot.mean()), "total_sd": float(tot.std()), "total_q": _q(tot),
              "wkts_mean": float(cat("wk").mean()), "pp_mean": float(cat("pp").mean()), "pp_q": _q(cat("pp")),
              "fow1_mean": float(cat("fow1").mean()), "fow1_q": _q(cat("fow1")),
              "fours_mean": float(cat("fours").mean()), "sixes_mean": float(cat("sixes").mean()),
              "sixes_q": _q(cat("sixes")), "fours_q": _q(cat("fours")),
              "wides_mean": float(cat("wides").mean()), "extras_mean": float(cat("extras").mean())}
        # batting first / second totals
        for lab, want in (("bat1", True), ("bat2", False)):
            sel = [i["score"] for i, f in zip(inns, firsts) if f == want]
            if sel:
                tm[lab + "_total_mean"] = float(np.concatenate(sel).mean())
        wins = [p["winA"] if side == "A" else 1 - p["winA"] for p in parts]
        for lab, want in (("p_win_bat1", True), ("p_win_bat2", False)):
            sel = [w for w, f in zip(wins, firsts) if f == want]
            if sel:
                tm[lab] = float(np.concatenate(sel).mean())
        # players
        order = team["order"][:11]
        br = cat("bat_runs"); bb = cat("bat_balls"); b4 = cat("bat_4"); b6 = cat("bat_6")
        bo = cat("bat_out"); bt = cat("batted")
        top = br.max(1, keepdims=True)
        istop = (br == top) & bt
        topshare = istop / np.maximum(istop.sum(1, keepdims=True), 1)
        players = {}
        for i, pid in enumerate(order):
            r = br[:, i]
            players[pid] = {"bat_pos": i + 1, "p_bat": float(bt[:, i].mean()), "runs_mean": float(r.mean()),
                            "runs_q": _q(r, (10, 25, 50, 75, 90)),
                            "p_runs": {str(t): float((r >= t).mean()) for t in TOP_THRESH},
                            "p_duck": float((bo[:, i] & (r == 0)).mean()),
                            "balls_mean": float(bb[:, i].mean()), "fours_mean": float(b4[:, i].mean()),
                            "sixes_mean": float(b6[:, i].mean()), "p_out": float(bo[:, i].mean()),
                            "p_top_bat": float(topshare[:, i].mean())}
        # bowling: this team's bowlers appear in the *other* side's innings
        other = "B" if side == "A" else "A"
        oinns = [p[other] for p in parts]
        ids = oinns[0]["bowl_ids"]
        wbb = np.concatenate([i["bowl_balls"] for i in oinns])
        wrr = np.concatenate([i["bowl_runs"] for i in oinns])
        www = np.concatenate([i["bowl_wkts"] for i in oinns])
        # top bowler: most wickets, tie-break fewest runs
        key = www * 1000 - wrr
        tb = key == key.max(1, keepdims=True)
        tshare = tb / tb.sum(1, keepdims=True)
        for j, pid in enumerate(ids):
            d = players.setdefault(pid, {"bat_pos": None})
            w = www[:, j]
            d.update({"overs_mean": float(wbb[:, j].mean() / 6), "wkts_mean": float(w.mean()),
                      "p_wkts": {str(t): float((w >= t).mean()) for t in (1, 2, 3, 4, 5)},
                      "conceded_mean": float(wrr[:, j].mean()),
                      "econ": float(wrr[:, j].sum() / max(wbb[:, j].sum(), 1) * 6),
                      "p_top_bowl": float(tshare[:, j].mean())})
        tm["players"] = players
        out[side] = tm
    out["margin_mean_A"] = float(out["A"]["total_mean"] - out["B"]["total_mean"])
    return out
