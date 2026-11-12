"""Out-of-sample checks with the pre-June-2025 holdout model:
(a) shrinkage calibration by sample size (do small-sample, extreme ratings regress more than the model says?),
(b) player- and match-level calibration of the simulator on IPL 2026 with real XIs."""
# %% imports
import json
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.ratings import (Model, RefSample, extras_dists, folded_players, last_top_league, load_people,
                                outs_per_row, runs_per_row, softmax, write_sim_params)
from models.ipl.replay import aggregate_rows, match_calibration, phase_table, player_calibration, run
from models.ipl.sim import Params
from models.ipl.tune import CUTOFF

BUCKETS = [0, 100, 300, 500, 1500, 10**9]
BLABELS = ["<100", "100-299", "300-499", "500-1499", "1500+"]


def holdout_model():
    Mh = Model(PROC / "model_holdout.pkl")
    f = pd.read_parquet(PROC / "frame.parquet")
    f = f[~f["reduced"]].reset_index(drop=True)
    cov = pd.read_parquet(PROC / "covariates.parquet")
    styles = pd.read_parquet(PROC / "styles.parquet")
    train = f[f["date"] < CUTOFF]
    BAT, BOWL, pb, pw = folded_players(Mh, cov, styles, last_top=last_top_league(train), ref_date=CUTOFF,
                                       proj_date="2026-04-15")
    return Mh, f, cov, styles, train, BAT, BOWL, pb, pw


def shrinkage_calibration(Mh, f, cov, train, BAT, BOWL, exs):
    test = f[f["date"] >= CUTOFF].reset_index(drop=True)
    from models.ipl.tune import map_env
    test = map_env(train, test)
    R = RefSample(Mh, test, cov, BAT, BOWL)
    ipl = (test["comp"].astype(str) == "IPL").to_numpy()
    avgB = np.stack([R.bterm_actual[ipl & (R.ph == p)].mean(0) for p in range(3)])
    avgW = np.stack([R.wterm_actual[ipl & (R.ph == p)].mean(0) for p in range(3)])
    Pf = softmax(R.eta)
    Pb = softmax(R.eta - R.bterm_actual + avgB[R.ph])
    Pw = softmax(R.eta - R.wterm_actual + avgW[R.ph])
    cls = test["cls"].astype(str).to_numpy()
    faced = cls != "wide"
    act_runs = np.where(np.isin(cls, ["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), test["runs_bat"], 0)
    act_out = ((cls == "wicket") | ((cls == "runout") & (test["player_out"] == test["batter"]))).to_numpy()
    nb_train = train[train["cls"].astype(str) != "wide"].groupby("batter").size()
    d = pd.DataFrame({"id": test["batter"], "faced": faced, "pred_r": runs_per_row(Pf, exs) - runs_per_row(Pb, exs),
                      "act_r": act_runs - runs_per_row(Pb, exs), "pred_o": outs_per_row(Pf, exs) - outs_per_row(Pb, exs),
                      "act_o": act_out - outs_per_row(Pb, exs)})
    g = d.groupby("id").agg(balls=("faced", "sum"), pred_r=("pred_r", "sum"), act_r=("act_r", "sum"),
                            pred_o=("pred_o", "sum"), act_o=("act_o", "sum"))
    g = g[g["balls"] >= 30]
    g["train_balls"] = nb_train.reindex(g.index).fillna(0).to_numpy()
    g["bucket"] = pd.cut(g["train_balls"], BUCKETS, labels=BLABELS, right=False)
    out = {"bat": []}
    for b, x in g.groupby("bucket", observed=True):
        w = x["balls"].to_numpy()
        pr, ar = x["pred_r"] / x["balls"], x["act_r"] / x["balls"]
        po, ao = x["pred_o"] / x["balls"], x["act_o"] / x["balls"]
        def wslope(p, a):
            p, a = p.to_numpy(), a.to_numpy()
            pm, am = np.average(p, weights=w), np.average(a, weights=w)
            v = np.average((p - pm) ** 2, weights=w)
            return float(np.average((p - pm) * (a - am), weights=w) / v) if v > 0 else None
        top = x[pr >= pr.quantile(0.8)]
        out["bat"].append(dict(bucket=str(b), n_players=int(len(x)), test_balls=int(w.sum()),
                               slope_runs=wslope(pr, ar), slope_outs=wslope(po, ao),
                               top20_pred_runs_per100=float(100 * top["pred_r"].sum() / top["balls"].sum()),
                               top20_act_runs_per100=float(100 * top["act_r"].sum() / top["balls"].sum()),
                               pred_runs_per100=float(100 * x["pred_r"].sum() / w.sum()),
                               act_runs_per100=float(100 * x["act_r"].sum() / w.sum())))
    # bowlers: runs conceded and wickets vs average-bowler expectation
    from models.ipl.ratings import conceded_per_row
    legal = ~np.isin(cls, ["wide", "noball"])
    conc = test["runs_total"].to_numpy() - test["byes"].to_numpy()
    nw_train = train[train["legal"]].groupby("bowler").size()
    d = pd.DataFrame({"id": test["bowler"], "legal": legal,
                      "pred_c": conceded_per_row(Pf, exs) - conceded_per_row(Pw, exs), "act_c": conc - conceded_per_row(Pw, exs),
                      "pred_w": Pf[:, 3] - Pw[:, 3], "act_w": (cls == "wicket") - Pw[:, 3]})
    g = d.groupby("id").agg(balls=("legal", "sum"), pred_c=("pred_c", "sum"), act_c=("act_c", "sum"),
                            pred_w=("pred_w", "sum"), act_w=("act_w", "sum"))
    g = g[g["balls"] >= 30]
    g["train_balls"] = nw_train.reindex(g.index).fillna(0).to_numpy()
    g["bucket"] = pd.cut(g["train_balls"], BUCKETS, labels=BLABELS, right=False)
    out["bowl"] = []
    for b, x in g.groupby("bucket", observed=True):
        w = x["balls"].to_numpy()
        def wslope(p, a):
            p, a = (p / x["balls"]).to_numpy(), (a / x["balls"]).to_numpy()
            pm, am = np.average(p, weights=w), np.average(a, weights=w)
            v = np.average((p - pm) ** 2, weights=w)
            return float(np.average((p - pm) * (a - am), weights=w) / v) if v > 0 else None
        out["bowl"].append(dict(bucket=str(b), n_players=int(len(x)), test_balls=int(w.sum()),
                                slope_conceded=wslope(x["pred_c"], x["act_c"]), slope_wkts=wslope(x["pred_w"], x["act_w"])))
    return out


def venue_baseline(train):
    i1 = train[(train["comp"].astype(str) == "IPL") & (train["innings"] == 1) & (train["date"] >= "2023-01-01")]
    tot = i1.groupby(["match_id", "venue"], observed=True)["runs_total"].sum().reset_index()
    overall = float(tot["runs_total"].mean())
    g = tot.groupby("venue", observed=True)["runs_total"].agg(["sum", "size"])
    k = 5.0
    return {"overall": overall, "venue": ((g["sum"] + k * overall) / (g["size"] + k)).to_dict()}


def main(n_sims=400):
    Mh, f, cov, styles, train, BAT, BOWL, pb, pw = holdout_model()
    with open(PROC / "ratings.pkl", "rb") as fh:
        RT = pickle.load(fh)
    exs, ex = RT["exs"], RT["ex"]
    shrink = shrinkage_calibration(Mh, f, cov, train, BAT, BOWL, exs)
    # holdout sim params: every player the holdout model knows (unseen players fall back to priors)
    ipl26 = f[(f["comp"].astype(str) == "IPL") & (f["date"].dt.year == 2026)]
    pool = sorted(set(ipl26["batter"]) | set(ipl26["bowler"]) | set(ipl26["non_striker"]) | set(RT["pool"]))
    pool = [p for p in pool if p in Mh.bat_pos or p in Mh.bowl_pos]
    sp_path = PROC / "sim_params_holdout.json"
    final_params = json.loads((PROC.parent.parent.parent / "docs/models/ipl/data/sim_params.json").read_text())
    write_sim_params(Mh, BAT, BOWL, pb, pw, ex, pool, list(Mh.venue_pos), styles, RT["names"], path=sp_path,
                     env_alias={"IPL|2026": "IPL|2025"}, default_env="IPL|2025",
                     match_shock=final_params.get("match_shock"))
    P = Params.load(sp_path)
    R = run(P, (2026,), n_sims=n_sims, seed=11)
    res = {"model_cutoff": str(CUTOFF.date()), "season": 2026, "sims_per_match": n_sims,
           "env_note": "IPL 2026 uses the IPL 2025 season environment (the latest the holdout model saw)",
           "shrinkage_calibration": shrink, "players": player_calibration(R), "phase": phase_table(R),
           "match": match_calibration(R, venue_baseline(train)), "rows": aggregate_rows(R)}
    with open(PROC / "oos.pkl", "wb") as fh:
        pickle.dump(dict(res=res, R=R), fh)
    (PROC / "oos.json").write_text(json.dumps(res, default=float))
    m = res["match"]
    print(f"OOS 2026: matches={m['n_matches']} wp_ll={m['wp_logloss']:.4f} brier={m['wp_brier']:.4f} "
          f"t1 rmse model={m['t1_rmse_model']:.1f} venue={m.get('t1_rmse_venue_mean', float('nan')):.1f} "
          f"cover={m['t1_quantile_coverage']}")
    for k in ("runs", "balls", "fours", "sixes"):
        print("bat fit", k, res["players"]["bat_fit"][k])
    for k in ("wkts", "conceded", "overs"):
        print("bowl fit", k, res["players"]["bowl_fit"][k])
    for b in shrink["bat"]:
        print("shrink bat", b)
    for b in shrink["bowl"]:
        print("shrink bowl", b)
    return res


if __name__ == "__main__":
    main()
