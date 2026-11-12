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
    if not cache.exists():
        from models.ipl import holdout
        holdout.main()
    return pd.read_parquet(cache)


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


def replay_insample(P):
    from models.ipl import replay as rp
    R = rp.run(P, REPLAY_SEASONS, n_sims=REPLAY_SIMS, seed=7)
    rows = rp.aggregate_rows(R)
    isim = R["ind_sim"]
    b = R["bat"]
    def ind_sim(x):
        r, o = x[:, 0], x[:, 1].astype(bool)
        return {"duck_pct": float(100 * np.mean(o & (r == 0))), "ge30_pct": float(100 * np.mean(r >= 30)),
                "ge50_pct": float(100 * np.mean(r >= 50)), "mean": float(r.mean())}
    # actual individual innings: batters who came to the crease
    f = pd.read_parquet(PROC / "frame.parquet", columns=["match_id", "innings", "batter", "non_striker", "runs_bat", "cls",
                                                         "player_out", "comp", "date", "reduced"])
    f = f[(f["comp"].astype(str) == "IPL") & (~f["reduced"]) & f["date"].dt.year.isin(REPLAY_SEASONS)]
    f = f[f["match_id"].isin(R["matches"]["match_id"])]
    acts = []
    for (mid, inn), g in f.groupby(["match_id", "innings"]):
        cls = g["cls"].astype(str)
        runs = g.assign(r=np.where(cls.isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), g["runs_bat"], 0)).groupby("batter")["r"].sum()
        outs = set(g["player_out"].astype(str)) - {""}
        for p in set(g["batter"]) | set(g["non_striker"]):
            acts.append((runs.get(p, 0), p in outs))
    iact = np.array(acts, float)
    M = R["matches"]
    hist = lambda x: np.histogram(x, bins=np.arange(80, 301, 10))[0]
    t1s = np.concatenate([a["sim_score"] for a in R["agg"] if a["innings"] == 1])
    return {"seasons": list(REPLAY_SEASONS), "matches": int(len(M)), "sims_per_match": REPLAY_SIMS, "rows": rows,
            "individual": {"sim": ind_sim(isim), "actual": ind_sim(iact), "n_actual": int(len(iact))},
            "t1_hist": {"edges": list(range(80, 301, 10)), "sim": (hist(t1s) / len(t1s)).tolist(),
                        "actual": (hist(M["t1_actual"]) / len(M)).tolist()},
            "players": rp.player_calibration(R), "phase": rp.phase_table(R), "match": rp.match_calibration(R)}


def main():
    P = Params.load()
    with open(PROC / "ratings.pkl", "rb") as fh:
        R = pickle.load(fh)
    h = holdout_predictions()
    cal = calibration(h, R["exs"])
    tuning = json.loads((PROC / "tuning.json").read_text()) if (PROC / "tuning.json").exists() else []
    tuning2 = json.loads((PROC / "tuning_r2.json").read_text()) if (PROC / "tuning_r2.json").exists() else []
    rep = replay_insample(P)
    from models.ipl import oos
    o = oos.main()
    diag = {"holdout": {"cutoff": str(CUTOFF.date()), **cal},
            "tuning": [{k: r.get(k) for k in ("half_life", "lam", "iters", "ll_all", "ll_ipl", "n_test", "n_ipl")} for r in tuning],
            "tuning_round2": [{k: r.get(k) for k in ("half_life", "lam", "iters", "ll_all", "ll_ipl", "n_test", "n_ipl")} for r in tuning2],
            "replay": rep, "oos": o, "match_shock": R.get("match_shock")}
    (EXPORT / "diagnostics.json").write_text(json.dumps(diag, separators=(",", ":"), default=float))
    for r in rep["rows"]:
        print(f"{r['metric']:30s} sim {r['sim_mean']:7.2f} ({r['sim_sd']:5.1f})  actual {r['actual_mean']:7.2f} ({r['actual_sd']:5.1f})")
    print("individual", rep["individual"])
    print("phase", rep["phase"])
    print("holdout ll", cal["all"]["logloss"], cal["ipl"]["logloss"])


if __name__ == "__main__":
    main()
