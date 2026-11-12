"""Re-simulate real IPL matches with their real XIs, batting order of appearance, bowling usage, venue and
batting-first side; collect match-, phase- and player-level projections next to what actually happened."""
# %% imports
import json

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.sim import bowling_schedule, sim_innings

QS = (10, 25, 50, 75, 90)


def _specs(g, players, cov):
    specs = {}
    for inn in (1, 2):
        gi = g[g["innings"] == inn]
        team = str(gi["bat_team"].iloc[0])
        gs = gi.sort_values(["over", "legal_before"], kind="stable")
        seen = list(dict.fromkeys(np.column_stack([gs["batter"].to_numpy(), gs["non_striker"].to_numpy()]).ravel()))
        rest = [p for p in players.get(team, []) if p not in seen]
        rest = sorted(rest, key=lambda p: cov["bat_pos_med"].get(p, 10) if p in cov.index else 10)
        order = (seen + rest)[:11]
        while len(order) < 11:
            order.append(order[-1])
        ov = gi.drop_duplicates("over")[["over", "bowler", "phase"]]
        plan = {}
        for _, r in ov.iterrows():
            plan.setdefault(r["bowler"], [0, 0, 0])[int(r["phase"])] += 1
        specs[inn] = dict(team=team, order=order,
                          plan=[{"id": b, "pp": v[0], "mid": v[1], "death": v[2]} for b, v in plan.items()])
    return specs


def _actual_players(gi, order):
    cls = gi["cls"].astype(str)
    bat_runs = gi.assign(r=np.where(cls.isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), gi["runs_bat"], 0))
    runs = bat_runs.groupby("batter")["r"].sum()
    balls = gi[cls != "wide"].groupby("batter").size()
    f4 = gi[cls == "r4"].groupby("batter").size()
    f6 = gi[cls == "r6"].groupby("batter").size()
    outs = set(gi["player_out"].astype(str)) - {""}
    bat = {p: dict(runs=int(runs.get(p, 0)), balls=int(balls.get(p, 0)), fours=int(f4.get(p, 0)), sixes=int(f6.get(p, 0)),
                   out=p in outs) for p in order}
    legal = gi[~cls.isin(["wide", "noball"])].groupby("bowler").size()
    conc = (gi["runs_total"] - gi["byes"]).groupby(gi["bowler"]).sum()
    wk = gi[cls == "wicket"].groupby("bowler").size()
    bowl = {b: dict(overs=float(legal.get(b, 0)) / 6, conc=int(conc.get(b, 0)), wkts=int(wk.get(b, 0)))
            for b in gi["bowler"].unique()}
    return bat, bowl


def run(P, seasons, n_sims=400, seed=7, env_fmt="IPL|{}"):
    f = pd.read_parquet(PROC / "frame.parquet")
    m = pd.read_parquet(PROC / "matches.parquet").set_index("match_id")
    cov = pd.read_parquet(PROC / "covariates.parquet")
    f = f[(f["comp"].astype(str) == "IPL") & (~f["reduced"]) & f["date"].dt.year.isin(seasons)]
    rng = np.random.default_rng(seed)
    mrows, prow_b, prow_w, phrows, agg = [], [], [], [], []
    ind_sim = []
    for mid, g in f.groupby("match_id", sort=False):
        if g["innings"].nunique() < 2:
            continue
        season = int(g["date"].iloc[0].year)
        ek = env_fmt.format(season)
        env = P.env.get(ek, P.env[P.raw["default_env"]])
        eph = P.env_phase.get(ek)
        venue = str(g["venue"].iloc[0])
        V = P.raw["venues"].get(venue, P.raw["venue_neutral"])
        specs = _specs(g, json.loads(m.loc[mid, "players"]), cov)
        # specs[inn]["plan"] = the bowlers who actually bowled in innings inn
        s1, s2 = bowling_schedule(specs[1]["plan"]), bowling_schedule(specs[2]["plan"])
        n = n_sims
        shock = rng.standard_normal(n) * P.shock_sd if P.shock_sd > 0 else None
        from models.ipl.sim import innings_shocks
        sh1, sh2 = innings_shocks(P, rng, n, shock)
        i1 = sim_innings(P, rng, n, specs[1]["order"], s1, V, env, 1, env_ph=eph, shock=sh1)
        i2 = sim_innings(P, rng, n, specs[2]["order"], s2, V, env, 2, target=i1["score"] + 1, env_ph=eph, shock=sh2)
        winner = str(m.loc[mid, "winner"])
        a1, a2 = g[g["innings"] == 1], g[g["innings"] == 2]
        t1, t2 = int(a1["runs_total"].sum()), int(a2["runs_total"].sum())
        p_bf = float(np.mean((i1["score"] > i2["score"]) + 0.5 * (i1["score"] == i2["score"])))
        mrows.append(dict(match_id=mid, season=season, venue=venue, bat1=specs[1]["team"], bat2=specs[2]["team"],
                          p_bat1_win=p_bf, bat1_won=float(winner == specs[1]["team"]) if winner else 0.5,
                          t1_actual=t1, t1_mean=float(i1["score"].mean()),
                          **{f"t1_q{q}": float(v) for q, v in zip(QS, np.percentile(i1["score"], QS))},
                          t2_actual=t2, t2_mean=float(i2["score"].mean()),
                          match_total_actual=t1 + t2, match_total_mean=float((i1["score"] + i2["score"]).mean()),
                          **{f"mt_q{q}": float(v) for q, v in zip(QS, np.percentile(i1["score"] + i2["score"], QS))}))
        for inn, res, gi in ((1, i1, a1), (2, i2, a2)):
            for ph in range(3):
                gp = gi[gi["phase"] == ph]
                phrows.append(dict(innings=inn, phase=ph, sim_runs=float(res["ph_runs"][:, ph].mean()),
                                   act_runs=int(gp["runs_total"].sum()), sim_wkts=float(res["ph_wkts"][:, ph].mean()),
                                   act_wkts=int(gp["wicket_kind"].astype(str).isin(["", "retired hurt", "retired not out"]).__invert__().sum())))
            agg.append(dict(innings=inn, sim_score=res["score"], act_score=int(gi["runs_total"].sum()),
                            sim_wk=res["wk"], act_wk=int((~gi["wicket_kind"].astype(str).isin(["", "retired hurt", "retired not out"])).sum()),
                            sim_pp=res["pp"], act_pp=int(gi[gi["over"] < 6]["runs_total"].sum()),
                            sim_wides=res["wides"], act_wides=int((gi["cls"].astype(str) == "wide").sum()),
                            sim_six=res["sixes"], act_six=int((gi["cls"].astype(str) == "r6").sum()),
                            sim_four=res["fours"], act_four=int((gi["cls"].astype(str) == "r4").sum())))
            order = specs[inn]["order"]
            abat, abowl = _actual_players(gi, order)
            bt = res["batted"]
            ind_sim.append(np.stack([res["bat_runs"][bt], res["bat_out"][bt]], 1))
            for k, pid in enumerate(order):
                if order.index(pid) != k:
                    continue  # padded duplicate
                r = res["bat_runs"][:, k]
                a = abat[pid]
                prow_b.append(dict(match_id=mid, innings=inn, id=pid, bat_pos=k + 1, proj_runs=float(r.mean()),
                                   proj_balls=float(res["bat_balls"][:, k].mean()), proj_4=float(res["bat_4"][:, k].mean()),
                                   proj_6=float(res["bat_6"][:, k].mean()), proj_p30=float((r >= 30).mean()),
                                   proj_p50=float((r >= 50).mean()),
                                   proj_pduck=float((res["bat_out"][:, k] & (r == 0)).mean()),
                                   act_runs=a["runs"], act_balls=a["balls"], act_4=a["fours"], act_6=a["sixes"],
                                   act_p30=float(a["runs"] >= 30), act_p50=float(a["runs"] >= 50),
                                   act_pduck=float(a["out"] and a["runs"] == 0)))
            for j, bid in enumerate(res["bowl_ids"]):
                w = res["bowl_wkts"][:, j]
                a = abowl.get(bid, dict(overs=0, conc=0, wkts=0))
                prow_w.append(dict(match_id=mid, innings=inn, id=bid, proj_wkts=float(w.mean()),
                                   proj_conc=float(res["bowl_runs"][:, j].mean()),
                                   proj_overs=float(res["bowl_balls"][:, j].mean() / 6), proj_p2w=float((w >= 2).mean()),
                                   act_wkts=a["wkts"], act_conc=a["conc"], act_overs=a["overs"], act_p2w=float(a["wkts"] >= 2)))
    return dict(matches=pd.DataFrame(mrows), bat=pd.DataFrame(prow_b), bowl=pd.DataFrame(prow_w),
                phase=pd.DataFrame(phrows), agg=agg, ind_sim=np.concatenate(ind_sim), n_sims=n_sims, seasons=list(seasons))


# %% summaries


def _ols(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.std(x) == 0:
        return {"slope": None, "intercept": None}
    b, a = np.polyfit(x, y, 1)
    return {"slope": float(b), "intercept": float(a)}


def player_calibration(R):
    out = {}
    b = R["bat"]
    mets = [("runs", "proj_runs", "act_runs"), ("balls", "proj_balls", "act_balls"), ("fours", "proj_4", "act_4"),
            ("sixes", "proj_6", "act_6"), ("p30", "proj_p30", "act_p30"), ("p50", "proj_p50", "act_p50"),
            ("pduck", "proj_pduck", "act_pduck")]
    if len(b):
        b = b.assign(decile=pd.qcut(b["proj_runs"].rank(method="first"), 10, labels=False))
        def tab(key):
            g = b.groupby(key)
            t = {"n": g.size().tolist(), key: [int(k) for k in g.size().index]}
            for name, pc, ac in mets:
                t[f"sim_{name}"] = g[pc].mean().round(4).tolist()
                t[f"act_{name}"] = g[ac].mean().round(4).tolist()
            return t
        out["bat_by_decile"] = tab("decile")
        out["bat_by_position"] = tab("bat_pos")
        out["bat_fit"] = {name: _ols(b[pc], b[ac]) for name, pc, ac in mets}
        out["bat_n"] = int(len(b))
    w = R["bowl"]
    wm = [("wkts", "proj_wkts", "act_wkts"), ("conceded", "proj_conc", "act_conc"), ("overs", "proj_overs", "act_overs"),
          ("p2w", "proj_p2w", "act_p2w")]
    if len(w):
        w = w.assign(decile=pd.qcut(w["proj_wkts"].rank(method="first"), 10, labels=False))
        g = w.groupby("decile")
        t = {"n": g.size().tolist(), "decile": list(range(len(g)))}
        for name, pc, ac in wm:
            t[f"sim_{name}"] = g[pc].mean().round(4).tolist()
            t[f"act_{name}"] = g[ac].mean().round(4).tolist()
        out["bowl_by_decile"] = t
        out["bowl_fit"] = {name: _ols(w[pc], w[ac]) for name, pc, ac in wm}
        out["bowl_n"] = int(len(w))
    return out


def phase_table(R):
    p = R["phase"].groupby(["innings", "phase"]).mean().reset_index()
    return p.round(3).to_dict(orient="list")


def match_calibration(R, baseline=None):
    M = R["matches"]
    p = np.clip(M["p_bat1_win"].to_numpy(), 1e-3, 1 - 1e-3)
    y = M["bat1_won"].to_numpy()
    ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    bins = pd.cut(p, [0, 0.35, 0.45, 0.55, 0.65, 1])
    rel = M.assign(b=bins).groupby("b", observed=True).agg(pred=("p_bat1_win", "mean"), obs=("bat1_won", "mean"),
                                                             n=("p_bat1_win", "size"))
    out = {"n_matches": int(len(M)), "wp_logloss": ll, "wp_logloss_coinflip": float(np.log(2)),
           "wp_brier": float(np.mean((p - y) ** 2)), "wp_reliability": rel.reset_index(drop=True).round(4).to_dict(orient="list"),
           "t1_rmse_model": float(np.sqrt(np.mean((M["t1_mean"] - M["t1_actual"]) ** 2))),
           "t1_bias_model": float(np.mean(M["t1_mean"] - M["t1_actual"]))}
    if baseline is not None:
        bl = M["venue"].map(baseline["venue"]).fillna(baseline["overall"])
        out["t1_rmse_venue_mean"] = float(np.sqrt(np.mean((bl - M["t1_actual"]) ** 2)))
        out["t1_rmse_overall_mean"] = float(np.sqrt(np.mean((baseline["overall"] - M["t1_actual"]) ** 2)))
    out["t1_quantile_coverage"] = {f"q{q}": float(np.mean(M["t1_actual"] < M[f"t1_q{q}"])) for q in QS}
    out["match_total_quantile_coverage"] = {f"q{q}": float(np.mean(M["match_total_actual"] < M[f"mt_q{q}"])) for q in QS}
    return out


def aggregate_rows(R):
    rows = []
    def row(label, s, a):
        rows.append({"metric": label, "sim_mean": float(np.mean(s)), "sim_sd": float(np.std(s)),
                     "actual_mean": float(np.mean(a)), "actual_sd": float(np.std(a))})
    A = R["agg"]
    for inn in (1, 2):
        x = [a for a in A if a["innings"] == inn]
        lab = "1st" if inn == 1 else "2nd"
        row(f"{lab}-innings total", np.concatenate([a["sim_score"] for a in x]), [a["act_score"] for a in x])
        row(f"{lab}-innings wickets", np.concatenate([a["sim_wk"] for a in x]), [a["act_wk"] for a in x])
        row(f"{lab}-innings powerplay runs", np.concatenate([a["sim_pp"] for a in x]), [a["act_pp"] for a in x])
    M = R["matches"]
    row("Chasing side win rate", 1 - M["p_bat1_win"], 1 - M["bat1_won"])
    row("Wides per innings", np.concatenate([a["sim_wides"] for a in A]), [a["act_wides"] for a in A])
    row("Sixes per innings", np.concatenate([a["sim_six"] for a in A]), [a["act_six"] for a in A])
    row("Fours per innings", np.concatenate([a["sim_four"] for a in A]), [a["act_four"] for a in A])
    return rows
