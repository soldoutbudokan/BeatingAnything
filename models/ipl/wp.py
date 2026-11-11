"""Win-probability model (state -> P(batting side wins)) and win-probability-added per player."""
# %% imports
import pickle

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from models.ipl.config import PROC

F1 = ["balls_left", "wkts", "score", "par"]
F2 = ["balls_left", "wkts", "need", "rrr", "par"]


def states(f):
    s = pd.DataFrame({
        "match_id": f["match_id"].to_numpy(), "innings": f["innings"].to_numpy(),
        "balls_left": (120 - f["legal_before"]).to_numpy(), "wkts": f["wkts_before"].to_numpy(),
        "score": f["score_before"].to_numpy(), "target": f["target"].to_numpy()})
    s["need"] = s["target"] - s["score"]
    s["rrr"] = s["need"] * 6 / s["balls_left"].clip(lower=1)
    return s


def par_table(f):
    i1 = f[f["innings"] == 1]
    tot = i1.groupby(["comp_season", "match_id"], observed=True)["runs_total"].sum()
    return tot.groupby(level=0, observed=True).mean()


# %% fit


def fit(f):
    par = par_table(f)
    ok = (f["winner"].astype(str) != "") & f["tier"].isin(["ipl", "intl", "top_fr", "fr2", "dom", "india_dom"])
    d = f[ok & (f["date"] >= "2015-01-01")]
    d = d.sample(n=min(len(d), 700000), random_state=0)
    s = states(d)
    s["par"] = d["comp_season"].map(par).astype(float).to_numpy()
    y = (d["winner"].astype(str) == d["bat_team"].astype(str)).to_numpy()
    models = {}
    for inn, feats, mono in ((1, F1, [1, -1, 1, -1]), (2, F2, [1, -1, -1, -1, 0])):
        m = (s["innings"] == inn).to_numpy()
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                             monotonic_cst=mono, random_state=0)
        X = s.loc[m, feats].to_numpy()
        clf.fit(X, y[m])
        models[inn] = clf
    return models, par


def predict(models, s):
    p = np.full(len(s), np.nan)
    for inn, feats in ((1, F1), (2, F2)):
        m = (s["innings"] == inn).to_numpy()
        if m.any():
            p[m] = models[inn].predict_proba(s.loc[m, feats].to_numpy())[:, 1]
    return p


# %% WPA


def wpa(f, models, par):
    s = states(f)
    s["par"] = f["comp_season"].map(par).astype(float).fillna(par.mean()).to_numpy()
    wp0 = predict(models, s)  # P(batting side wins) before the ball
    key = f["match_id"].astype(str) + "_" + f["innings"].astype(str)
    nxt = pd.Series(wp0).groupby(key.to_numpy()).shift(-1).to_numpy().copy()
    last = pd.isna(nxt)
    # end of innings 1: WP of batting side = 1 - P(chaser wins at the start of the chase)
    i1_tot = f[f["innings"] == 1].groupby("match_id")["runs_total"].sum()
    end1 = last & (f["innings"].to_numpy() == 1)
    if end1.any():
        st = pd.DataFrame({"innings": 2, "balls_left": 120, "wkts": 0,
                           "need": i1_tot.reindex(f.loc[end1, "match_id"]).to_numpy() + 1})
        st["rrr"] = st["need"] * 6 / 120
        st["par"] = s.loc[end1, "par"].to_numpy()
        nxt[end1] = 1 - predict(models, st)
    end2 = last & (f["innings"].to_numpy() == 2)
    nxt[end2] = (f.loc[end2, "winner"].astype(str) == f.loc[end2, "bat_team"].astype(str)).astype(float)
    tie = (f["winner"].astype(str) == "").to_numpy() & end2
    nxt[tie] = 0.5
    d = nxt - wp0
    return d


def main():
    f = pd.read_parquet(PROC / "frame.parquet")
    f = f[~f["reduced"]].reset_index(drop=True)
    cache = PROC / "wp_model.pkl"
    if cache.exists():
        with open(cache, "rb") as fh:
            c = pickle.load(fh)
        models, par = c["models"], c["par"]
    else:
        models, par = fit(f)
        with open(cache, "wb") as fh:
            pickle.dump(dict(models=models, par=par), fh)
    rec = f[f["date"] >= "2024-01-01"].reset_index(drop=True)
    d = wpa(rec, models, par)
    cls = rec["cls"].astype(str).to_numpy()
    bat_credit = ~np.isin(cls, ["wide", "byes"])
    df = pd.DataFrame({"match_id": rec["match_id"], "ipl": (rec["comp"].astype(str) == "IPL").to_numpy(),
                       "batter": rec["batter"], "bowler": rec["bowler"], "d": d, "bat_credit": bat_credit})
    out = {}
    for scope, x in (("all", df), ("ipl", df[df["ipl"]])):
        xb = x[x["bat_credit"]]
        b = xb.groupby("batter").agg(wpa=("d", "sum"), matches=("match_id", "nunique"))
        w = x.groupby("bowler").agg(wpa=("d", lambda v: -v.sum()), matches=("match_id", "nunique"))
        out[scope] = (b, w)
    with open(PROC / "wpa.pkl", "wb") as fh:
        pickle.dump(dict(out=out, par=par), fh)
    print("wpa done")


if __name__ == "__main__":
    main()
