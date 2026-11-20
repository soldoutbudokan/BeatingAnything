"""Match flow for Tests: when captains declare, when they enforce the follow-on, and how long spells last.

Small logistic models on over-end states; the simulator evaluates them with the coefficients exported here.
"""
# %% imports
import json

import numpy as np
import pandas as pd

from models.intl.config import FORMATS

SINCE = "2010-01-01"
MAX_SPELL = 25


def over_states(f):
    """State at the start of every over (= the end of the one before) of innings 1-3, plus each declared
    innings' closing state, labelled 1."""
    f = f[f["inn"] <= 3]
    g = f.groupby(["match_id", "inn"], sort=False)
    first = f[f["legal_before"] % 6 == 0].drop_duplicates(["match_id", "inn", "over"])
    first = first[first["over"] >= 1]
    s = pd.DataFrame({"match_id": first["match_id"].to_numpy(), "inn": first["inn"].to_numpy(),
                      "score": first["score_before"].to_numpy(), "lead": first["lead_before"].to_numpy(),
                      "wk": first["wkts_before"].to_numpy(), "ov": first["over"].to_numpy().astype(float),
                      "rem": first["rem_ov"].to_numpy(), "y": 0})
    last = g.tail(1)
    e = pd.DataFrame({"match_id": last["match_id"].to_numpy(), "inn": last["inn"].to_numpy(),
                      "score": (last["score_before"] + last["runs_total"]).to_numpy(),
                      "lead": (last["lead_before"] + last["runs_total"]).to_numpy(),
                      "wk": last["wkts_before"].to_numpy(), "ov": (last["over"] + 1).to_numpy().astype(float),
                      "rem": (last["rem_ov"] - 1.0 / 6).clip(lower=0.5).to_numpy(), "y": 1})
    return s, e


def decl_features(inn, score, lead, wk, ov, rem):
    """Feature vector of the declaration model (mirrored in sim.js: declFeatures)."""
    if inn == 1:
        return [1.0, score / 100.0, max(score - 400.0, 0.0) / 100.0, float(wk), ov / 50.0, rem / 90.0]
    if inn == 2:
        return [1.0, lead / 100.0, max(lead, 0.0) / 100.0, float(wk), ov / 50.0, rem / 90.0]
    return [1.0, lead / 100.0, max(lead - 200.0, 0.0) / 100.0, float(wk), rem / 90.0, min(lead / max(rem, 1.0), 12.0)]


def fit(key="test"):
    from sklearn.linear_model import LogisticRegression
    fmt = FORMATS[key]
    f = pd.read_parquet(fmt.proc / "frame.parquet",
                        columns=["match_id", "date", "inn", "over", "legal_before", "score_before", "lead_before",
                                 "wkts_before", "runs_total", "rem_ov", "bowler", "bowl_spin", "legal"])
    m = pd.read_parquet(fmt.proc / "matches.parquet")
    f = f[f["date"] >= SINCE]
    m = m[m["date"] >= SINCE]
    meta = {}
    for r in m.itertuples():
        for x in json.loads(r.innings):
            meta[(r.match_id, x["inn"])] = x
    s, e = over_states(f)
    declared = np.array([meta.get((a, b), {}).get("declared", False) for a, b in zip(e["match_id"], e["inn"])])
    e = e[declared]
    d = pd.concat([s, e], ignore_index=True)
    out = {"decl": {}, "decl_rate": {}}
    for inn in (1, 2, 3):
        di = d[d["inn"] == inn]
        X = np.array([decl_features(inn, *r) for r in zip(di["score"], di["lead"], di["wk"], di["ov"], di["rem"])])
        clf = LogisticRegression(C=10.0, fit_intercept=False, max_iter=2000).fit(X, di["y"])
        out["decl"][str(inn)] = [round(float(c), 4) for c in clf.coef_[0]]
        n_inn = di.drop_duplicates("match_id").shape[0]
        out["decl_rate"][str(inn)] = {"innings": int(n_inn), "declared": int(di["y"].sum()),
                                      "expected": round(float(clf.predict_proba(X)[:, 1].sum()), 1)}
    # ---- follow-on: sides 200+ ahead after both first innings
    rows = []
    for r in m.itertuples():
        inns = json.loads(r.innings)
        if len(inns) < 3:
            continue
        lead = inns[0]["runs"] - inns[1]["runs"]
        if lead < 200 or inns[1]["team"] == inns[0]["team"]:
            continue
        used = (inns[0]["legal"] + inns[1]["legal"]) / 6.0
        avail = f.loc[f["match_id"] == r.match_id, "rem_ov"]
        rem = float(avail.iloc[0]) - used if len(avail) else 450 - used
        rows.append(((lead - 200) / 100.0, inns[1]["legal"] / 300.0, rem / 90.0, int(inns[2]["team"] == inns[1]["team"])))
    fo = np.array(rows)
    clf = LogisticRegression(C=1.0, max_iter=2000).fit(fo[:, :3], fo[:, 3])
    out["follow_on"] = {"coef": [round(float(clf.intercept_[0]), 4)] + [round(float(c), 4) for c in clf.coef_[0]],
                        "n": int(len(fo)), "enforced": int(fo[:, 3].sum()), "min_lead": 200}
    # ---- spell lengths: chance a spell ends after its L-th over, pace and spin
    ob = f[f["legal"]].drop_duplicates(["match_id", "inn", "over"])[["match_id", "inn", "over", "bowler", "bowl_spin"]]
    ob = ob.sort_values(["match_id", "inn", "over"]).reset_index(drop=True)
    grp = ob.groupby(["match_id", "inn"], sort=False)
    prev2 = grp["bowler"].shift(2)
    next2 = grp["bowler"].shift(-2)
    cont = (prev2 == ob["bowler"]).to_numpy()
    L = np.ones(len(ob), int)
    key_ = (ob["match_id"].astype(str) + "|" + ob["inn"].astype(str)).to_numpy()
    for i in range(2, len(ob)):
        if cont[i] and key_[i] == key_[i - 2]:
            L[i] = L[i - 2] + 1
    known = next2.notna().to_numpy() & (ob["over"].to_numpy() % 80 < 78)   # the new ball ends spells for another reason
    ended = (next2 != ob["bowler"]).to_numpy()
    haz = {}
    for nm, sp in (("pace", False), ("spin", True)):
        sel = known & (ob["bowl_spin"].to_numpy() == sp)
        h = []
        for k in range(1, MAX_SPELL + 1):
            at = sel & (np.minimum(L, MAX_SPELL) == k)
            h.append(round(float((ended[at].sum() + 1.0) / (at.sum() + 2.0)), 4))
        haz[nm] = h
    out["spell_hazard"] = haz
    return out


if __name__ == "__main__":
    print(json.dumps(fit(), indent=1))
