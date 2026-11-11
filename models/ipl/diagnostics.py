"""Diagnostics (not a backtest): held-out per-ball calibration and aggregate realism of the simulator."""
# %% imports
import json
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import CLASSES, EXPORT, PROC
from models.ipl.final_fit import best_hyper
from models.ipl.fit import build_design, fit_model, indices, load, predict_eta, probs_from_eta
from models.ipl.sim import Params, bowling_schedule, sim_innings
from models.ipl.tune import CUTOFF, map_env

REPLAY_SEASONS = (2025, 2026)
REPLAY_SIMS = 400


# %% held-out calibration


def holdout_predictions():
    cache = PROC / "holdout_pred.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    f, cov = load()
    idx = indices(f)
    train = f[f["date"] < CUTOFF].reset_index(drop=True)
    test = map_env(train, f[f["date"] >= CUTOFF].reset_index(drop=True))
    H, lam, _ = best_hyper()
    fitr, D, _ = fit_model(train, cov, lam, H, train["date"].max(), maxiter=500, idx=idx)
    _, Xt = build_design(test, cov, *idx)
    P = probs_from_eta(predict_eta(Xt, fitr.W))
    out = pd.DataFrame(P.astype("float32"), columns=[f"p_{c}" for c in CLASSES])
    out["y"] = test["y"].to_numpy()
    out["comp"] = test["comp"].astype(str).to_numpy()
    out["match_id"] = test["match_id"].to_numpy()
    out["innings"] = test["innings"].to_numpy()
    out["runs_total"] = test["runs_total"].to_numpy()
    out.to_parquet(cache, index=False)
    return out


def calibration(h, ex):
    res = {}
    for scope, d in (("all", h), ("ipl", h[h["comp"] == "IPL"])):
        y = d["y"].to_numpy()
        P = d[[f"p_{c}" for c in CLASSES]].to_numpy().astype(float)
        ll = float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))))
        freq = np.bincount(y, minlength=len(CLASSES)) / len(y)
        ll_marg = float(-np.mean(np.log(freq[y])))
        cls = {}
        for k, c in enumerate(CLASSES):
            p = P[:, k]
            obs = (y == k).astype(float)
            q = np.unique(np.quantile(p, np.linspace(0, 1, 11)))
            b = np.clip(np.searchsorted(q, p, side="right") - 1, 0, len(q) - 2)
            g = pd.DataFrame({"b": b, "p": p, "o": obs}).groupby("b").agg(pred=("p", "mean"), obs=("o", "mean"), n=("o", "size"))
            cls[c] = {"mean_pred": float(p.mean()), "obs_rate": float(obs.mean()), "bins": g.reset_index(drop=True).to_dict(orient="list")}
        # expected vs actual runs per innings (sum over the real deliveries)
        exp_runs = (P[:, CLASSES.index("r1")] + 2 * P[:, CLASSES.index("r2")] + 3 * P[:, CLASSES.index("r3")]
                    + 4 * P[:, CLASSES.index("r4")] + 6 * P[:, CLASSES.index("r6")]
                    + P[:, 0] * ex["wide_mean"] + P[:, 1] * (1 + ex["nb_bat_mean"]) + P[:, 2] * ex["bye_mean"]
                    + P[:, 4] * ex["ro_runs_mean"])
        inn = pd.DataFrame({"k": d["match_id"].astype(str) + d["innings"].astype(str), "x": exp_runs,
                            "a": d["runs_total"].to_numpy(), "w": P[:, 3] + P[:, 4], "wa": np.isin(y, [3, 4])}).groupby("k").sum()
        res[scope] = {"n_balls": int(len(y)), "logloss": ll, "logloss_marginal": ll_marg,
                      "classes": cls, "innings_runs_expected": float(inn["x"].mean()), "innings_runs_actual": float(inn["a"].mean()),
                      "innings_wkts_expected": float(inn["w"].mean()), "innings_wkts_actual": float(inn["wa"].mean())}
    return res


# %% simulator replay of recent IPL seasons


def replay(P):
    f = pd.read_parquet(PROC / "frame.parquet")
    m = pd.read_parquet(PROC / "matches.parquet")
    cov = pd.read_parquet(PROC / "covariates.parquet")
    f = f[(f["comp"].astype(str) == "IPL") & (~f["reduced"])]
    f = f[f["date"].dt.year.isin(REPLAY_SEASONS)]
    mm = m.set_index("match_id")
    rng = np.random.default_rng(7)
    sims, acts = [], []
    ind_sim, ind_act = [], []
    for mid, g in f.groupby("match_id", sort=False):
        if g["innings"].nunique() < 2:
            continue
        season = str(g["date"].iloc[0].year)
        env = P.env.get(f"IPL|{season}", P.env[P.raw["default_env"]])
        V = P.raw["venues"].get(str(g["venue"].iloc[0]), P.raw["venue_neutral"])
        players = json.loads(mm.loc[mid, "players"])
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
            specs[inn] = dict(order=order, plan=[{"id": b, "pp": v[0], "mid": v[1], "death": v[2]} for b, v in plan.items()])
        s1 = bowling_schedule(specs[2]["plan"])
        s2 = bowling_schedule(specs[1]["plan"])
        n = REPLAY_SIMS
        i1 = sim_innings(P, rng, n, specs[1]["order"], s1, V, env, 1)
        i2 = sim_innings(P, rng, n, specs[2]["order"], s2, V, env, 2, target=i1["score"] + 1)
        a1 = g[g["innings"] == 1]
        a2 = g[g["innings"] == 2]
        winner = str(mm.loc[mid, "winner"])
        sims.append(dict(t1=i1["score"], t2=i2["score"], w1=i1["wk"], w2=i2["wk"], pp1=i1["pp"],
                         chase=(i2["score"] > i1["score"]) + 0.5 * (i2["score"] == i1["score"]),
                         wides=np.concatenate([i1["wides"], i2["wides"]]), six=np.concatenate([i1["sixes"], i2["sixes"]]),
                         four=np.concatenate([i1["fours"], i2["fours"]])))
        acts.append(dict(t1=a1["runs_total"].sum(), t2=a2["runs_total"].sum(), w1=(a1["wicket_kind"].astype(str).isin(["", "retired hurt", "retired not out"]) == False).sum(),
                         w2=(a2["wicket_kind"].astype(str).isin(["", "retired hurt", "retired not out"]) == False).sum(),
                         pp1=a1[a1["over"] < 6]["runs_total"].sum(),
                         chase=float(winner == str(a2["bat_team"].iloc[0])) if winner else 0.5,
                         wides=[(a1["cls"] == "wide").sum(), (a2["cls"] == "wide").sum()],
                         six=[(a1["cls"] == "r6").sum(), (a2["cls"] == "r6").sum()],
                         four=[(a1["cls"] == "r4").sum(), (a2["cls"] == "r4").sum()]))
        for inn, res in ((1, i1), (2, i2)):
            bt = res["batted"]
            ind_sim.append(np.stack([res["bat_runs"][bt], res["bat_out"][bt]], 1))
            gi = g[g["innings"] == inn]
            runs = gi.groupby("batter")["runs_bat"].sum()
            batted = set(gi["batter"]) | set(gi["non_striker"])
            outs = set(gi["player_out"].astype(str)) - {""}
            ind_act += [(runs.get(b, 0), b in outs) for b in batted]
    S = {k: np.concatenate([s[k] for s in sims]) for k in sims[0]}
    A = {k: np.array([a[k] for a in acts], float) for k in ("t1", "t2", "w1", "w2", "pp1", "chase")}
    A.update({k: np.concatenate([np.array(a[k], float) for a in acts]) for k in ("wides", "six", "four")})
    isim = np.concatenate(ind_sim)
    iact = np.array(ind_act, float)
    def ind(x):
        r, o = x[:, 0], x[:, 1].astype(bool)
        return {"duck_pct": float(100 * np.mean(o & (r == 0))), "ge30_pct": float(100 * np.mean(r >= 30)),
                "ge50_pct": float(100 * np.mean(r >= 50)), "mean": float(r.mean())}
    out = {"seasons": list(REPLAY_SEASONS), "matches": len(sims), "sims_per_match": REPLAY_SIMS,
           "rows": []}
    def row(label, s, a):
        out["rows"].append({"metric": label, "sim_mean": float(np.mean(s)), "sim_sd": float(np.std(s)),
                            "actual_mean": float(np.mean(a)), "actual_sd": float(np.std(a))})
    row("1st-innings total", S["t1"], A["t1"])
    row("2nd-innings total", S["t2"], A["t2"])
    row("1st-innings wickets", S["w1"], A["w1"])
    row("2nd-innings wickets", S["w2"], A["w2"])
    row("1st-innings powerplay runs", S["pp1"], A["pp1"])
    row("Chasing side win rate", S["chase"], A["chase"])
    row("Wides per innings", S["wides"], A["wides"])
    row("Sixes per innings", S["six"], A["six"])
    row("Fours per innings", S["four"], A["four"])
    out["individual"] = {"sim": ind(isim), "actual": ind(iact), "n_actual": int(len(iact))}
    hist = lambda x: np.histogram(x, bins=np.arange(80, 301, 10))[0]
    out["t1_hist"] = {"edges": list(range(80, 301, 10)), "sim": (hist(S["t1"]) / len(S["t1"])).tolist(),
                      "actual": (hist(A["t1"]) / len(A["t1"])).tolist()}
    return out


def main():
    P = Params.load()
    with open(PROC / "ratings.pkl", "rb") as fh:
        R = pickle.load(fh)
    h = holdout_predictions()
    cal = calibration(h, R["exs"])
    tuning = json.loads((PROC / "tuning.json").read_text()) if (PROC / "tuning.json").exists() else []
    rep = replay(P)
    diag = {"holdout": {"cutoff": str(CUTOFF.date()), **cal},
            "tuning": [{k: r[k] for k in ("half_life", "lam", "iters", "ll_all", "ll_ipl", "n_test", "n_ipl")} for r in tuning],
            "replay": rep}
    (EXPORT / "diagnostics.json").write_text(json.dumps(diag, separators=(",", ":")))
    for r in rep["rows"]:
        print(f"{r['metric']:30s} sim {r['sim_mean']:7.2f} ({r['sim_sd']:5.1f})  actual {r['actual_mean']:7.2f} ({r['actual_sd']:5.1f})")
    print("individual", rep["individual"])
    print("holdout ll", cal["all"]["logloss"], cal["ipl"]["logloss"])


if __name__ == "__main__":
    main()
