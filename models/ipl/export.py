"""Team defaults, player value, precomputed matchups, and the site JSON exports."""
# %% imports
import json
import pickle
import time
from datetime import date

import numpy as np
import pandas as pd

from models.ipl.config import CLASSES, COMP_NAMES, EXPORT, PROC, TIERS
from models.ipl.ratings import IPL_RECENT, ROLES_BAT
from models.ipl.sim import Params, bowling_schedule, sim_match, summarize
from models.ipl.team import SHORT, build as build_teams, canon_team

N_SIMS = 10000


def rnd(x, d=3):
    if isinstance(x, dict):
        return {k: rnd(v, d) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rnd(v, d) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), d)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def dump(name, obj, d=3):
    (EXPORT / name).write_text(json.dumps(rnd(obj, d), separators=(",", ":"), allow_nan=False))


# %% player value (VARP)


def slot_balls(f):
    """Average balls faced per IPL innings by batting position 1..11 (did-not-bat counts as 0), IPL 2024-26,
    and the phase mix of those balls."""
    r = f[(f["comp"].astype(str) == "IPL") & f["season"].astype(str).isin(IPL_RECENT) & (f["cls"].astype(str) != "wide")]
    n_inn = r.groupby(["match_id", "innings"]).ngroups
    bp = r.groupby("bat_pos").size().reindex(range(1, 12), fill_value=0) / n_inn
    mix = r.groupby(["bat_pos", "phase"]).size().unstack(fill_value=0).reindex(range(1, 12), fill_value=0)
    mix = mix.div(mix.sum(axis=1), axis=0).fillna(1 / 3)
    return bp, mix


def player_value(R, cov, f, teams_pos, plan_overs=None):
    bat, bowl = R["bat"], R["bowl"]
    bp, mix = slot_balls(f)
    ipl = f[(f["comp"].astype(str) == "IPL") & f["season"].astype(str).isin(IPL_RECENT)]
    balls_b = ipl[ipl["cls"].astype(str) != "wide"].groupby("batter").size()
    balls_w = ipl[ipl["legal"]].groupby("bowler").size()
    first = ipl.drop_duplicates(["match_id", "innings", "batter"])
    ipl_pos = first.groupby("batter")["bat_pos"].median()
    pos = ipl_pos.reindex(bat.index).fillna(cov["bat_pos_med"].reindex(bat.index)).fillna(9).round().clip(1, 11).astype(int)
    for pid, p in teams_pos.items():  # default batting order position for squad players
        if pid in pos.index:
            pos[pid] = p
    role = pd.cut(pos, [0, 2, 4, 7, 11], labels=ROLES_BAT).astype(str)
    # replacement level: mean per-phase run value of fringe IPL batters/bowlers (bottom third of playing time)
    rep_b = {}
    for r in ROLES_BAT:
        ids = [i for i in bat.index if role.get(i) == r and i in balls_b.index]
        if not ids:
            continue
        nb = balls_b.reindex(ids)
        fringe = nb[nb <= nb.quantile(1 / 3)].index
        rep_b[r] = {ph: float(bat.loc[fringe, f"{ph}_rv100"].mean()) for ph in ("pp", "mid", "death")}
    out_b = pd.DataFrame(index=bat.index)
    out_b["slot"] = pos
    out_b["role_slot"] = role
    exp_balls = bp.reindex(pos.to_numpy()).to_numpy()
    m = mix.reindex(pos.to_numpy()).to_numpy()
    rv_p = sum(m[:, k] * bat[f"{ph}_rv100"].to_numpy() for k, ph in enumerate(("pp", "mid", "death")))
    rv_r = np.array([sum(m[i, k] * rep_b[role.iloc[i]][ph] for k, ph in enumerate(("pp", "mid", "death")))
                     for i in range(len(role))])
    out_b["exp_balls"] = exp_balls
    out_b["bat_rv100_slot"] = rv_p
    out_b["bat_rep_rv100"] = rv_r
    out_b["bat_varp"] = (rv_p - rv_r) * exp_balls / 100.0
    # bowling
    st = R["styles"]
    grp = st["bowl_group"].reindex(bowl.index).fillna("pace").replace("none", "pace")
    rep_w = {}
    for g in ("pace", "spin"):
        ids = [i for i in bowl.index if grp.get(i) == g and i in balls_w.index]
        nw = balls_w.reindex(ids)
        opm = cov["overs_per_match"].reindex(ids)
        spec = nw[(opm >= 2.0).to_numpy()]
        fringe = spec[spec <= spec.quantile(1 / 3)].index
        rep_w[g] = {ph: float(bowl.loc[fringe, f"{ph}_rv_over"].mean()) for ph in ("pp", "mid", "death")}
    mixw = R["mix_bowl"].reindex(bowl.index)
    mixw = mixw.div(mixw.sum(axis=1), axis=0).fillna(1 / 3).to_numpy()
    rvw = sum(mixw[:, k] * bowl[f"{ph}_rv_over"].to_numpy() for k, ph in enumerate(("pp", "mid", "death")))
    rvr = np.array([sum(mixw[i, k] * rep_w[grp.iloc[i]][ph] for k, ph in enumerate(("pp", "mid", "death")))
                    for i in range(len(bowl))])
    out_w = pd.DataFrame(index=bowl.index)
    out_w["bowl_rv_over_mix"] = rvw
    out_w["bowl_rep_rv_over"] = rvr
    # projected overs in the current role: the team bowling plan for squad players; otherwise overs per match
    # in matches played since 2024 (all T20s); players who have not bowled since 2024 project to zero
    rec = f[f["date"] >= "2024-01-01"]
    apps = pd.concat([rec[["match_id", "batter"]].rename(columns={"batter": "id"}),
                      rec[["match_id", "non_striker"]].rename(columns={"non_striker": "id"}),
                      rec[["match_id", "bowler"]].rename(columns={"bowler": "id"})]).drop_duplicates()
    n_apps = apps.groupby("id").size()
    ov_rec = rec[rec["legal"]].groupby("bowler").size() / 6
    usage = (ov_rec.reindex(bowl.index).fillna(0) / n_apps.reindex(bowl.index).clip(lower=1)).fillna(0).clip(0, 4)
    in_plan = pd.Series(False, index=bowl.index)
    if plan_overs:
        for pid, ov in plan_overs.items():
            if pid in in_plan.index and ov > 0.05:
                in_plan[pid] = True
    is_bowler = in_plan | ((ov_rec.reindex(bowl.index).fillna(0) * 6 >= 60) & (usage >= 0.5))
    if plan_overs:  # default-12 players: the current team role decides
        for pid, ov in plan_overs.items():
            if pid in is_bowler.index:
                is_bowler[pid] = ov > 0.05
    usage = usage.where(is_bowler, 0.0)
    if plan_overs:
        for pid, ov in plan_overs.items():
            if pid in usage.index:
                usage[pid] = ov
    exp_ov = usage.to_numpy()
    out_w["exp_overs"] = exp_ov
    out_w["is_bowler"] = is_bowler.to_numpy()
    out_w["bowl_varp_4ov"] = (rvr - rvw) * 4.0   # per 4 overs
    out_w["bowl_varp"] = (rvr - rvw) * exp_ov   # per match at his usual workload
    return out_b, out_w, rep_b, rep_w, bp, mix


# %% matchups


def team_spec(t):
    return {"name": t["name"], "order": t["order"], "plan": t["plan"]}


def pmf(x, tail=1e-4):
    """Exact sim distribution of an integer quantity, full mass kept: {o, p, t, tl, th}.
    p[i] = P(value = o + i) for interior values; each tail with cumulative probability <= `tail` is cut and
    folded into the end bucket, so p[0] = P(value <= o) and p[-1] = P(value >= o + len(p) - 1);
    tl / th = mass folded into the first / last bucket; t = tl + th (sum(p) == 1)."""
    x = np.asarray(x, int)
    lo = int(x.min())
    c = np.bincount(x - lo) / len(x)
    cl, ch = np.cumsum(c), np.cumsum(c[::-1])[::-1]
    a = int(np.searchsorted(cl, tail, side="right"))          # first index whose cumulative mass > tail
    b = len(c) - int(np.searchsorted(np.cumsum(c[::-1]), tail, side="right"))  # one past the last kept index
    a, b = min(a, len(c) - 1), max(b, a + 1)
    p = c[a:b].copy()
    tl, th = float(c[:a].sum()), float(c[b:].sum())
    p[0] += tl
    p[-1] += th
    return {"o": lo + a, "p": [round(float(v), 5) for v in p], "t": round(tl + th, 6), "tl": round(tl, 6),
            "th": round(th, 6)}


def condition_pmfs(part, A, B):
    """PMFs for one batting-first condition (part = one sim_match(bat_first=...) output)."""
    first = part["first"][0]
    out = {"bat_first": A["name"] if first == "A" else B["name"], "n": int(len(part["winA"])),
           "p_win_A": float(part["winA"].mean()), "p_tie": float(part["tie"].mean())}
    i1 = part[first]
    i2 = part["B" if first == "A" else "A"]
    out["first_innings_total_pmf"] = pmf(i1["score"])
    out["match_total_pmf"] = pmf(i1["score"] + i2["score"])
    out["match_fours_pmf"] = pmf(i1["fours"] + i2["fours"])
    out["match_sixes_pmf"] = pmf(i1["sixes"] + i2["sixes"])
    # result margins (conditional on that result; ties excluded): side batting first wins by runs,
    # chaser wins by wickets in hand and by balls to spare
    w1 = i1["score"] > i2["score"]
    w2 = i2["score"] > i1["score"]
    out["p_bat1_win_in_20"] = float(w1.mean())
    out["p_bat2_win_in_20"] = float(w2.mean())
    out["bat1_win_runs_pmf"] = pmf(i1["score"][w1] - i2["score"][w1]) if w1.any() else None
    out["bat2_win_wkts_pmf"] = pmf(10 - i2["wk"][w2]) if w2.any() else None
    out["bat2_win_balls_pmf"] = pmf(120 - i2["legal"][w2]) if w2.any() else None
    for side, team in (("A", A), ("B", B)):
        r = part[side]
        tm = {"total_pmf": pmf(r["score"]), "pp_pmf": pmf(r["pp"]), "sixes_pmf": pmf(r["sixes"]),
              "fours_pmf": pmf(r["fours"]), "wkts_pmf": pmf(r["wk"]), "fow1_pmf": pmf(r["fow1"]), "players": {}}
        for k, pid in enumerate(team["order"][:11]):
            tm["players"][pid] = {"runs_pmf": pmf(r["bat_runs"][:, k]), "balls_pmf": pmf(r["bat_balls"][:, k]),
                                  "fours_pmf": pmf(r["bat_4"][:, k]), "sixes_pmf": pmf(r["bat_6"][:, k])}
        br, bt = r["bat_runs"], r["batted"]
        top = (br == br.max(1, keepdims=True)) & bt
        topshare = top / np.maximum(top.sum(1, keepdims=True), 1)
        for k, pid in enumerate(team["order"][:11]):
            tm["players"][pid]["mean"] = {"runs": float(br[:, k].mean()), "balls": float(r["bat_balls"][:, k].mean()),
                                          "fours": float(r["bat_4"][:, k].mean()), "sixes": float(r["bat_6"][:, k].mean()),
                                          "p_bat": float(bt[:, k].mean()), "p_out": float(r["bat_out"][:, k].mean()),
                                          "p_top_bat": float(topshare[:, k].mean())}
        o = part["B" if side == "A" else "A"]
        key = o["bowl_wkts"] * 1000 - o["bowl_runs"]
        tb = key == key.max(1, keepdims=True)
        tshare = tb / tb.sum(1, keepdims=True)
        for j, pid in enumerate(o["bowl_ids"]):
            d = tm["players"].setdefault(pid, {})
            d["wkts_pmf"] = pmf(o["bowl_wkts"][:, j])
            d["conceded_pmf"] = pmf(o["bowl_runs"][:, j])
            m_ = d.setdefault("mean", {})
            m_.update({"wkts": float(o["bowl_wkts"][:, j].mean()), "conceded": float(o["bowl_runs"][:, j].mean()),
                       "overs": float(o["bowl_balls"][:, j].mean() / 6), "p_top_bowl": float(tshare[:, j].mean())})
        out[side] = tm
    return out


def run_matchups(P, teams, n_each=N_SIMS):
    """Every pair at each side's home venue: n_each sims with A batting first and n_each with B batting
    first. The summary (matchups.json) pools both (= a 50/50 toss); pmfs are kept per condition."""
    from models.ipl.sim import _concat
    names = sorted(teams)
    res = []
    t0 = time.time()
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            A, B = teams[names[a]], teams[names[b]]
            for host in (A, B):
                v = host["home_venue"]
                k = len(res)
                rA = sim_match(P, team_spec(A), team_spec(B), v, n=n_each, seed=4 * k + 1, bat_first="A")
                rB = sim_match(P, team_spec(A), team_spec(B), v, n=n_each, seed=4 * k + 2, bat_first="B")
                s = summarize(_concat(rA, rB), team_spec(A), team_spec(B))
                res.append(dict(A=A["name"], B=B["name"], venue=v, home=host["name"], summary=s,
                                pmfs=[condition_pmfs(rA, A, B), condition_pmfs(rB, A, B)]))
    secs = time.time() - t0
    neutral = []
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            A, B = teams[names[a]], teams[names[b]]
            raw = sim_match(P, team_spec(A), team_spec(B), None, n=N_SIMS, seed=1000 + len(neutral))
            s = summarize(raw, team_spec(A), team_spec(B))
            neutral.append(dict(A=A["name"], B=B["name"], p_win_A=s["p_win_A"], runs_A=s["A"]["total_mean"],
                                runs_B=s["B"]["total_mean"], summary=s))
    return res, neutral, secs / max(2 * len(res), 1)


def runs_to_wp(P, teams, neutral, n_pairs=8, delta=0.06, n=10000):
    import copy
    from models.ipl.sim import Params as _P, _concat
    d = np.asarray(P.raw.get("match_shock", {}).get("dir") or [0] * 11, float)
    if not np.any(d):
        e = P.raw["env"]
        d = np.asarray(e["IPL|2026"]) - np.asarray(e["IPL|2021"])
        d = d / np.linalg.norm(d)
    pairs = sorted(neutral, key=lambda x: abs(x["p_win_A"] - 0.5))[:n_pairs]
    dw, dr, rows = [], [], []
    for k, pr in enumerate(pairs):
        A, B = team_spec(teams[pr["A"]]), team_spec(teams[pr["B"]])
        out = {}
        for sgn in (-1, 1):
            raw = copy.deepcopy(P.raw)
            for pid in A["order"]:
                if pid in raw["batters"]:
                    raw["batters"][pid]["b"] = (np.asarray(raw["batters"][pid]["b"]) + sgn * delta * d).tolist()
            Pp = _P(raw)
            r = summarize(sim_match(Pp, A, B, None, n=n, seed=500 + k), A, B)
            out[sgn] = (r["p_win_A"], r["A"]["total_mean"])
        dw.append(out[1][0] - out[-1][0])
        dr.append(out[1][1] - out[-1][1])
        rows.append({"A": pr["A"], "B": pr["B"], "d_win": dw[-1], "d_runs": dr[-1]})
    return {"slope": float(np.sum(dw) / np.sum(dr)), "pairs": rows, "delta": delta}


# %% main


def main():
    f = pd.read_parquet(PROC / "frame.parquet")
    f = f[~f["reduced"]].reset_index(drop=True)
    cov = pd.read_parquet(PROC / "covariates.parquet")
    styles = pd.read_parquet(PROC / "styles.parquet")
    with open(PROC / "ratings.pkl", "rb") as fh:
        R = pickle.load(fh)
    with open(PROC / "model.pkl", "rb") as fh:
        MD = pickle.load(fh)
    with open(PROC / "wpa.pkl", "rb") as fh:
        WPA = pickle.load(fh)["out"]
    R["styles"] = styles
    age = (f["date"].max() - f["date"]).dt.days.to_numpy() / 365.25
    fw = f.assign(wt=0.5 ** (age / MD["half_life"]))
    R["mix_bowl"] = fw[fw["legal"]].groupby(["bowler", "phase"])["wt"].sum().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0)
    R["mix_bowl"].columns = [0, 1, 2]
    names = R["names"]
    P = Params.load()
    teams, nat, smat = build_teams()
    teams_pos = {}
    for t in teams.values():
        for k, pid in enumerate(t["order"]):
            teams_pos[pid] = k + 1
    # projected overs per match for the default 12: last season's recency-weighted overs per match *played*,
    # scaled so the 12 share exactly 20 overs (each capped at 4); squad players outside the 12 keep their usage
    plan_overs = {}
    for t in teams.values():
        sq = t["squad"].set_index("id")
        u = sq.loc[t["xii"], "overs_pm"].clip(0, 4)
        tot = float(u.sum())
        if tot > 0:
            u = u * (20.0 / tot)
            for _ in range(5):  # re-cap and redistribute
                over = (u - 4).clip(lower=0).sum()
                u = u.clip(upper=4)
                room = (u < 4) & (u > 0)
                if over <= 1e-9 or not room.any():
                    break
                u[room] += over * u[room] / u[room].sum()
        for pid, v in u.items():
            plan_overs[pid] = float(v)
    vb, vw, rep_b, rep_w, slot_bp, slot_mix = player_value(R, cov, f, teams_pos, plan_overs)

    # ---------------- matchups
    res, neutral, sec_per = run_matchups(P, teams)
    # runs -> win probability: perturb one side's batting (logit shift along the scoring direction) in
    # near-even neutral matchups and measure d P(win) / d (that side's expected total)
    rtw = runs_to_wp(P, teams, neutral)
    slope = rtw["slope"]
    pdf_slope = slope

    # ---------------- players.json
    bat, bowl = R["bat"], R["bowl"]
    pool = R["pool"]
    obs_all_b, obs_all_w = R["obs"]["all"]
    obs_ipl_b, obs_ipl_w = R["obs"]["ipl"]
    wpa_all_b, wpa_all_w = WPA["all"]
    wpa_ipl_b, wpa_ipl_w = WPA["ipl"]
    # team history (IPL) and latest franchise
    ipl_f = f[f["comp"].astype(str) == "IPL"]
    hist = pd.concat([ipl_f[["batter", "bat_team", "date"]].rename(columns={"batter": "id", "bat_team": "team"}),
                      ipl_f[["bowler", "bowl_team", "date"]].rename(columns={"bowler": "id", "bowl_team": "team"})])
    hist["team"] = hist["team"].astype(str).map(canon_team)
    hist["year"] = hist["date"].dt.year
    team_years = hist.groupby(["id", "team"])["year"].agg(["min", "max"]).reset_index()
    cur_team = {}
    for t in teams.values():
        for pid in t["squad"]["id"]:
            cur_team[pid] = t["name"]
    # recent raw counts (all comps since 2024, and IPL career)
    def raw_counts(d):
        cls = d["cls"].astype(str)
        faced = cls != "wide"
        out = (cls == "wicket") | ((cls == "runout") & (d["player_out"] == d["batter"]))
        brun = np.where(cls.isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), d["runs_bat"], 0)
        b = pd.DataFrame({"id": d["batter"], "faced": faced, "runs": brun, "out": out, "m": d["match_id"]}).groupby("id").agg(
            balls=("faced", "sum"), runs=("runs", "sum"), outs=("out", "sum"), inns=("m", "nunique"))
        legal = ~cls.isin(["wide", "noball"])
        w = pd.DataFrame({"id": d["bowler"], "legal": legal, "conc": d["runs_total"] - d["byes"], "wkt": cls == "wicket",
                          "m": d["match_id"]}).groupby("id").agg(balls=("legal", "sum"), conc=("conc", "sum"),
                                                                    wkts=("wkt", "sum"), inns=("m", "nunique"))
        return b, w
    rc_b, rc_w = raw_counts(f[f["date"] >= "2024-01-01"])
    last_played = pd.concat([f.groupby("batter")["date"].max(), f.groupby("non_striker")["date"].max(),
                             f.groupby("bowler")["date"].max()]).groupby(level=0).max()
    last_ipl = pd.concat([ipl_f.groupby("batter")["date"].max(), ipl_f.groupby("non_striker")["date"].max(),
                          ipl_f.groupby("bowler")["date"].max()]).groupby(level=0).max()
    s26_b, s26_w = raw_counts(ipl_f[ipl_f["date"].dt.year == int(next(iter(teams.values()))["season"])])
    # projected per-match line at the default role: mean over that team's 18 home/away matchups
    proj = {}
    for m in res:
        for side in ("A", "B"):
            for pid, d in m["summary"][side]["players"].items():
                proj.setdefault(pid, []).append(d)
    ic_b, ic_w = raw_counts(ipl_f)
    pct_base_b = bat.index.intersection(obs_ipl_b.index[obs_ipl_b["balls"] >= 100].union(rc_b.index[rc_b["balls"] >= 300]))
    pct_base_w = bowl.index.intersection(obs_ipl_w.index[obs_ipl_w["balls"] >= 100].union(rc_w.index[rc_w["balls"] >= 300]))

    def pct(series, base, higher_better=True):
        b = series.reindex(base).dropna().to_numpy()
        s = np.sort(b if higher_better else -b)
        vals = series if higher_better else -series
        return pd.Series(np.searchsorted(s, vals.to_numpy(), side="right") / max(len(s), 1) * 100, index=series.index)

    pr_b = {k: pct(bat[k], pct_base_b) for k in ("all_sr", "all_avg", "all_rv100", "death_sr", "pp_sr", "spin_sr", "pace_sr")}
    pr_b["bat_varp"] = pct(vb["bat_varp"], pct_base_b)
    pr_w = {k: pct(bowl[k], pct_base_w, False) for k in ("all_econ", "all_rv_over", "death_econ", "pp_econ")}
    pr_w["all_wkt_pct"] = pct(bowl["all_wkt_pct"], pct_base_w)
    pr_w["bowl_varp"] = pct(vw["bowl_varp"], pct_base_w)

    BATK = ["sr", "avg", "out_pct", "bnd_pct", "four_pct", "six_pct", "dot_pct", "nbsr", "rv100"]
    BOWK = ["econ", "wkt_pct", "sr", "avg", "dot_pct", "bnd_pct", "six_pct", "wides_per_over", "rv_over", "nb_per_over"]
    players = []
    for pid in pool:
        st = styles.loc[pid] if pid in styles.index else None
        c = cov.loc[pid] if pid in cov.index else None
        ty = team_years[team_years["id"] == pid]
        d = {"id": pid, "name": names.get(pid, pid), "team": cur_team.get(pid),
             "ipl_teams": [{"team": r.team, "from": int(r["min"]), "to": int(r["max"])} for _, r in ty.iterrows()],
             "overseas": bool(nat.get(pid, "India") != "India") if pid in nat.index else False,
             "country": nat.get(pid) if pid in nat.index else None,
             "bat_hand": None if st is None or pd.isna(st["bat_hand"]) else st["bat_hand"],
             "bowl_type": None if st is None or pd.isna(st["bowl_type"]) else st["bowl_type"],
             "bowl_group": None if st is None or pd.isna(st["bowl_group"]) else st["bowl_group"],
             "bowl_subtype": None if st is None else st["bowl_subtype"],
             "style_inferred": bool(st["style_inferred"]) if st is not None else False,
             "role_bat": None if c is None else c["role_bat"], "role_bowl": None if c is None else c["role_bowl"],
             "bat_pos_career": None if c is None else c["bat_pos_med"],
             "overs_per_match_career": None if c is None else c["overs_per_match"],
             "league_mix": None if c is None else {t: float(c["bat_tier_" + t] if pid in bat.index else c["bowl_tier_" + t]) for t in TIERS}}
        if pid in bat.index:
            b = bat.loc[pid]
            d["bat"] = {s: {k: b[f"{s}_{k}"] for k in BATK} for s in ("all", "pp", "mid", "death", "pace", "spin")}
            d["bat"]["vs_avg"] = {s: {k: b[f"{s}_{k}"] - b[f"{s}_avg_{k}"] for k in ("sr", "out_pct", "rv100", "bnd_pct", "dot_pct")}
                                  for s in ("all", "pp", "mid", "death", "pace", "spin")}
            bt_ = {}
            for t in ("pace_R", "pace_L", "OB", "LB", "SLA", "SLW"):
                if f"t_{t}_sr" in b.index and pd.notna(b[f"t_{t}_sr"]):
                    bt_[t] = {k: b[f"t_{t}_{k}"] for k in ("sr", "out_pct", "rv100", "bnd_pct", "dot_pct")}
                    bt_[t]["vs_avg"] = {k: b[f"t_{t}_{k}"] - b[f"t_{t}_avg_{k}"] for k in ("sr", "out_pct", "rv100")}
            d["bat"]["by_type"] = bt_
            d["bat"]["sd"] = {"sr": b["sd_sr"], "out_pct": b["sd_out_pct"], "avg": b["sd_avg"], "rv100": b["sd_rv100"]}
            d["bat"]["settling"] = R["settle"].get(pid)
            v = vb.loc[pid]
            d["bat"]["value"] = {"slot": int(v["slot"]), "exp_balls": v["exp_balls"], "rv100_slot": v["bat_rv100_slot"],
                                 "rep_rv100": v["bat_rep_rv100"], "varp_runs": v["bat_varp"],
                                 "varp_wp": v["bat_varp"] * pdf_slope}
            d["bat"]["pct"] = {k: float(s.get(pid, np.nan)) for k, s in pr_b.items()}
            for scope, ob, wp in (("obs_2024", obs_all_b, wpa_all_b), ("obs_ipl_2024", obs_ipl_b, wpa_ipl_b)):
                if pid in ob.index and ob.loc[pid, "balls"] > 0:
                    o = ob.loc[pid]
                    d["bat"][scope] = {"balls": int(o["balls"]), "runs": int(o["runs"]), "outs": int(o["outs"]),
                                       "sr": 100 * o["runs"] / o["balls"], "xsr": 100 * o["xruns"] / o["balls"],
                                       "rae100": 100 * (o["runs"] - o["xruns"]) / o["balls"],
                                       "outs_vs_x": o["outs"] - o["xouts"],
                                       "avg": o["runs"] / o["outs"] if o["outs"] else None,
                                       "xavg": o["xruns"] / o["xouts"] if o["xouts"] else None,
                                       "fours": int(o["fours"]), "sixes": int(o["sixes"]), "x4": o["x4"], "x6": o["x6"],
                                       "wpa": float(wp["wpa"].get(pid, np.nan)) if pid in wp.index else None,
                                       "wpa_per_match": float(wp.loc[pid, "wpa"] / wp.loc[pid, "matches"]) if pid in wp.index else None}
            if pid in ic_b.index:
                o = ic_b.loc[pid]
                d["bat"]["ipl_career"] = {"inns": int(o["inns"]), "balls": int(o["balls"]), "runs": int(o["runs"]),
                                          "outs": int(o["outs"]), "sr": 100 * o["runs"] / max(o["balls"], 1)}
        if pid in bowl.index:
            b = bowl.loc[pid]
            d["bowl"] = {s: {k: b[f"{s}_{k}"] for k in BOWK} for s in ("all", "pp", "mid", "death", "rhb", "lhb")}
            d["bowl"]["vs_avg"] = {s: {k: b[f"{s}_{k}"] - b[f"{s}_avg_{k}"] for k in ("econ", "wkt_pct", "rv_over", "dot_pct")}
                                   for s in ("all", "pp", "mid", "death", "rhb", "lhb")}
            d["bowl"]["sd"] = {"econ": b["sd_econ"], "wkt_pct": b["sd_wkt_pct"], "rv_over": b["sd_rv_over"]}
            v = vw.loc[pid]
            mixw = R["mix_bowl"].loc[pid] if pid in R["mix_bowl"].index else None
            d["bowl"]["phase_mix"] = None if mixw is None else (mixw / mixw.sum()).round(3).tolist()
            d["bowl"]["is_bowler"] = bool(v["is_bowler"])
            d["bowl"]["value"] = {"rv_over_mix": v["bowl_rv_over_mix"], "rep_rv_over": v["bowl_rep_rv_over"],
                                  "exp_overs": v["exp_overs"], "varp_4ov": v["bowl_varp_4ov"],
                                  "varp_runs": v["bowl_varp"], "varp_wp": v["bowl_varp"] * pdf_slope}
            d["bowl"]["pct"] = {k: float(s.get(pid, np.nan)) for k, s in pr_w.items()}
            for scope, ob, wp in (("obs_2024", obs_all_w, wpa_all_w), ("obs_ipl_2024", obs_ipl_w, wpa_ipl_w)):
                if pid in ob.index and ob.loc[pid, "balls"] > 0:
                    o = ob.loc[pid]
                    d["bowl"][scope] = {"balls": int(o["balls"]), "conc": int(o["conc"]), "wkts": int(o["wkts"]),
                                        "econ": 6 * o["conc"] / o["balls"], "xecon": 6 * o["xconc"] / o["balls"],
                                        "runs_saved": o["xconc"] - o["conc"], "wkts_vs_x": o["wkts"] - o["xwkts"],
                                        "dot_pct": 100 * o["dots"] / o["balls"], "xdot_pct": 100 * o["xdots"] / o["balls"],
                                        "wpa": float(wp["wpa"].get(pid, np.nan)) if pid in wp.index else None,
                                        "wpa_per_match": float(wp.loc[pid, "wpa"] / wp.loc[pid, "matches"]) if pid in wp.index else None}
            if pid in ic_w.index:
                o = ic_w.loc[pid]
                d["bowl"]["ipl_career"] = {"inns": int(o["inns"]), "balls": int(o["balls"]), "conc": int(o["conc"]),
                                           "wkts": int(o["wkts"]), "econ": 6 * o["conc"] / max(o["balls"], 1)}
        season_ = int(next(iter(teams.values()))["season"])
        line = {"season": season_}
        if pid in s26_b.index:
            o = s26_b.loc[pid]
            line.update(bat_inns=int(o["inns"]), runs=int(o["runs"]), balls=int(o["balls"]), outs=int(o["outs"]),
                        sr=100 * o["runs"] / o["balls"] if o["balls"] else None,
                        avg=o["runs"] / o["outs"] if o["outs"] else None)
        if pid in s26_w.index:
            o = s26_w.loc[pid]
            line.update(bowl_inns=int(o["inns"]), wkts=int(o["wkts"]), overs=float(o["balls"]) / 6, conceded=int(o["conc"]),
                        econ=6 * o["conc"] / o["balls"] if o["balls"] else None)
        apps26 = sum(1 for t in teams.values() for _, r in t["squad"].iterrows() if r["id"] == pid)
        line["matches"] = int(next((r["apps"] for t in teams.values() for _, r in t["squad"].iterrows() if r["id"] == pid), 0)) if apps26 else 0
        d["ipl_last_season"] = line if (pid in s26_b.index or pid in s26_w.index) else None
        if pid in proj:
            L = proj[pid]
            g = lambda k: float(np.mean([x[k] for x in L if x.get(k) is not None])) if any(x.get(k) is not None for x in L) else None
            d["proj_match"] = {"matchups": len(L), "bat_pos": g("bat_pos"), "runs": g("runs_mean"), "balls": g("balls_mean"),
                               "fours": g("fours_mean"), "sixes": g("sixes_mean"),
                               "p30": float(np.mean([x["p_runs"]["30"] for x in L if "p_runs" in x])) if any("p_runs" in x for x in L) else None,
                               "p50": float(np.mean([x["p_runs"]["50"] for x in L if "p_runs" in x])) if any("p_runs" in x for x in L) else None,
                               "overs": g("overs_mean"), "wkts": g("wkts_mean"), "conceded": g("conceded_mean"),
                               "econ": g("econ")}
        else:
            d["proj_match"] = None
        d["last_played"] = str(last_played[pid].date()) if pid in last_played.index else None
        d["last_played_ipl"] = str(last_ipl[pid].date()) if pid in last_ipl.index else None
        d["style_defaulted"] = {"bat_hand": d["bat_hand"] is None,
                                "bowl_type": bool(d.get("bowl", {}).get("is_bowler")) and (d["bowl_type"] in (None, "") )}
        if d["bat_hand"] is None:
            d["bat_hand_used"] = "R"   # simulator default when the hand is unknown
        bv = d.get("bat", {}).get("value", {}).get("varp_runs", 0) or 0
        wv = d.get("bowl", {}).get("value", {}).get("varp_runs", 0) or 0
        d["varp_runs"] = bv + wv
        d["varp_wp"] = (bv + wv) * pdf_slope
        players.append(d)
    dump("players.json", {"players": players, "avg_bat": R["avg_bat"], "avg_bowl": R["avg_bowl"],
                          "settling_avg": R["settle_avg"], "settling_buckets": json.loads((EXPORT / "sim_params.json").read_text())["bf_labels"],
                          "replacement": {"bat": rep_b, "bowl": rep_w},
                          "slot_balls": slot_bp.tolist(), "runs_to_wp": pdf_slope,
                          "slot_phase_mix": slot_mix.reindex(range(1, 12)).to_numpy().round(4).tolist()})

    # ---------------- teams.json
    pmap = {p["id"]: p for p in players}
    team_rows = []
    for t in sorted(teams.values(), key=lambda x: x["name"]):
        mine = [m for m in res if t["name"] in (m["A"], m["B"])]
        wins, rf, ra = [], [], []
        for m in mine:
            s = m["summary"]
            me = "A" if m["A"] == t["name"] else "B"
            op = "B" if me == "A" else "A"
            wins.append(s["p_win_A"] if me == "A" else 1 - s["p_win_A"])
            rf.append(s[me]["total_mean"]); ra.append(s[op]["total_mean"])
        nwin = [n["p_win_A"] if n["A"] == t["name"] else 1 - n["p_win_A"] for n in neutral if t["name"] in (n["A"], n["B"])]
        sq = t["squad"]
        xi_bat = sum((pmap.get(p, {}).get("bat", {}).get("value", {}).get("varp_runs") or 0) for p in t["order"])
        xi_bowl = sum((pmap.get(p["id"], {}).get("bowl", {}).get("value", {}).get("varp_4ov") or 0) * (sum([p["pp"], p["mid"], p["death"]]) / 4)
                      for p in t["plan"])
        team_rows.append({
            "name": t["name"], "short": t["short"], "season": t["season"], "matches_in_season": t["matches"],
            "home_venue": t["home_venue"], "venues_used": t["venues_used"],
            "xii": t["xii"], "order": t["order"], "impact_player": t["impact"], "plan": t["plan"],
            "schedule": bowling_schedule(t["plan"]),
            "squad": [{"id": r["id"], "name": names.get(r["id"], r["id"]), "apps": int(r["apps"]), "last_app": r["last"],
                       "overseas": bool(r["overseas"]), "bat_pos": None if pd.isna(r["bat_pos"]) else float(r["bat_pos"]),
                       "overs_pm": float(r["overs_pm"]), "ov_pp": float(r["ov_pp"]), "ov_mid": float(r["ov_mid"]),
                       "ov_death": float(r["ov_death"]), "in_pool": r["id"] in pmap} for _, r in sq.iterrows()],
            "rating": {"win_pct_home_away": float(np.mean(wins)), "win_pct_neutral": float(np.mean(nwin)),
                       "runs_for": float(np.mean(rf)), "runs_against": float(np.mean(ra)),
                       "net_runs": float(np.mean(rf) - np.mean(ra)), "xi_bat_varp": xi_bat, "xi_bowl_varp": xi_bowl,
                       "xi_varp": xi_bat + xi_bowl},
        })
    ranks = sorted(team_rows, key=lambda r: -r["rating"]["win_pct_neutral"])
    for k, r in enumerate(ranks):
        r["rating"]["rank"] = k + 1
    dump("teams.json", {"season": int(next(iter(teams.values()))["season"]), "teams": team_rows})

    # ---------------- head_to_head.json (notable batter x bowler terms that the simulator applies)
    poolset = set(pool)
    h2h = [h for h in R.get("h2h", []) if h["batter"] in poolset and h["bowler"] in poolset]
    dump("head_to_head.json", {"n_pairs_fitted": R.get("n_pairs_fitted", 0), "n_exported": len(h2h),
                               "threshold": {"abs_d_sr": 5.0, "abs_d_out_pct": 0.5},
                               "pairs": sorted(h2h, key=lambda h: -abs(h["d_sr"]))})

    # ---------------- matchups.json
    mrows = []
    for m in res:
        s = m["summary"]
        mrows.append({"A": m["A"], "B": m["B"], "venue": m["venue"], "home": m["home"], "n": s["n"],
                      "p_win_A": s["p_win_A"], "p_tie": s["p_tie"], "A_stats": s["A"], "B_stats": s["B"]})
    # ---------------- exact distributions: one file per home team (its 9 home matchups)
    mdir = EXPORT / "matchups"
    mdir.mkdir(exist_ok=True)
    index = []
    for t in sorted(teams.values(), key=lambda x: x["name"]):
        rows = [{"A": m["A"], "B": m["B"], "venue": m["venue"], "home": m["home"], "conditions": m["pmfs"]}
                for m in res if m["home"] == t["name"]]
        fn = f"{t['short']}.json"
        dump(f"matchups/{fn}", {"home": t["name"], "venue": t["home_venue"], "n_sims_per_condition": N_SIMS,
                                "trim": 1e-4, "tail_fold": 1e-4, "matchups": rows}, d=5)
        index.append({"file": f"matchups/{fn}", "home": t["name"], "venue": t["home_venue"],
                      "pairs": [[r["A"], r["B"]] for r in rows]})
    dump("matchups/index.json", {"files": index})
    dump("matchups.json", {"n_sims": 2 * N_SIMS, "toss": "half the sims with each side batting first (n_sims/2 each); per-condition pmfs in matchups/<home>.json", "env": P.raw["default_env"],
                           "matchups": mrows,
                           "neutral": [{k: v for k, v in n.items() if k != "summary"} for n in neutral],
                           "neutral_full": [{"A": n["A"], "B": n["B"], "venue": None, "n": n["summary"]["n"],
                                             "p_win_A": n["summary"]["p_win_A"], "p_tie": n["summary"]["p_tie"],
                                             "A_stats": n["summary"]["A"], "B_stats": n["summary"]["B"]} for n in neutral]})

    # ---------------- venues.json / leagues.json
    ven = R["venues"]
    vrows = ven.to_dict(orient="records")
    neutral_v = ven.attrs.get("neutral", {})
    dump("venues.json", {"neutral_reference": neutral_v, "venues": vrows,
                         "home_of": {t["name"]: t["home_venue"] for t in teams.values()},
                         "resources": {"overs": list(range(20)), "er": R["ER"].tolist(), "wicket_value": R["WV"].tolist(),
                                       "scale_to_ipl": R["er_scale"]}})
    lg = R["leagues"].copy()
    lg["tier"] = lg["comp"].map(lambda c: __import__("models.ipl.config", fromlist=["TIER_OF"]).TIER_OF.get(c, "assoc"))
    dump("leagues.json", {"leagues": lg.to_dict(orient="records"),
                          "env_ipl": {k: v for k, v in P.raw["env"].items()}})
    with open(PROC / "export_state.pkl", "wb") as fh:
        pickle.dump(dict(sec_per_matchup=sec_per, slope=pdf_slope, teams=teams, runs_to_wp=rtw), fh)
    print(f"export: players={len(players)} teams={len(team_rows)} matchups={len(mrows)} sim {sec_per:.2f}s/10k")


if __name__ == "__main__":
    main()
