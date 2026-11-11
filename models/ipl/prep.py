"""Model frame: context features, player styles (with pace/spin inference), player covariates."""
# %% imports
import numpy as np
import pandas as pd

from models.ipl.config import CLASSES, PEOPLE, PROC, STYLES, TIER_OF, TIERS

BF_EDGES = [0, 1, 3, 6, 10, 15, 20, 30, 45, 10**6]   # balls-faced buckets: 0,1-2,3-5,6-9,10-14,15-19,20-29,30-44,45+
BF_LABELS = ["0", "1-2", "3-5", "6-9", "10-14", "15-19", "20-29", "30-44", "45+"]
RRR_EDGES = [-1e9, 6, 7.5, 9, 10.5, 12, 14, 17, 1e9]
RRR_LABELS = ["<6", "6-7.5", "7.5-9", "9-10.5", "10.5-12", "12-14", "14-17", "17+"]
SUBTYPES = ["pace_R", "pace_L", "OB", "LB", "SLA", "SLW", "pace_U", "spin_U"]
EARLY_BF = 10  # settling split: first 10 balls of an innings


def subtype_of(bowl_type, group):
    bt = (bowl_type or "")
    if bt in ("RF", "RFM", "RM", "RMF", "RS"):
        return "pace_R"
    if bt in ("LF", "LFM", "LM", "LMF", "LS"):
        return "pace_L"
    if bt in ("OB", "LB", "SLA", "SLW"):
        return bt
    if group == "pace":
        return "pace_U"
    if group == "spin":
        return "spin_U"
    return "pace_U"


def bucket(x, edges):
    return np.searchsorted(np.asarray(edges), x, side="right") - 1


# %% load styles and infer missing pace/spin


def bowler_features(b):
    g = b.groupby("bowler")
    legal = b["legal"].astype(float)
    f = pd.DataFrame({
        "balls": g.size(),
        "pp": g["phase"].apply(lambda s: (s == 0).mean()),
        "death": g["phase"].apply(lambda s: (s == 2).mean()),
        "wide": g["cls"].apply(lambda s: (s == "wide").mean()),
        "nb": g["cls"].apply(lambda s: (s == "noball").mean()),
        "byes": g["cls"].apply(lambda s: (s == "byes").mean()),
        "dot": g["cls"].apply(lambda s: (s == "r0").mean()),
        "six": g["cls"].apply(lambda s: (s == "r6").mean()),
        "four": g["cls"].apply(lambda s: (s == "r4").mean()),
        "wkt": g["cls"].apply(lambda s: (s == "wicket").mean()),
    })
    wk = b[b["cls"] == "wicket"].groupby("bowler")["wicket_kind"].agg(
        st=lambda s: (s == "stumped").mean(), lbw=lambda s: (s == "lbw").mean(),
        bwd=lambda s: (s == "bowled").mean(), n="size")
    f = f.join(wk).fillna({"st": 0, "lbw": 0, "bwd": 0, "n": 0})
    return f


def load_styles(b):
    s = pd.read_csv(STYLES, dtype=str).drop_duplicates("cricsheet_id").set_index("cricsheet_id")
    bowlers = pd.Index(b["bowler"].unique())
    batters = pd.Index(pd.unique(np.concatenate([b["batter"].unique(), b["non_striker"].unique()])))
    allp = bowlers.union(batters)
    st = pd.DataFrame(index=allp)
    st["bat_hand"] = s["bat_hand"].reindex(allp)
    st["bowl_type"] = s["bowl_type"].reindex(allp)
    st["bowl_group"] = s["bowl_group"].reindex(allp)
    st["style_source"] = s["source"].reindex(allp)
    st["style_inferred"] = False
    # classifier for bowlers lacking a pace/spin label
    from sklearn.ensemble import GradientBoostingClassifier
    bf = bowler_features(b)
    lab = st["bowl_group"].reindex(bf.index)
    train = bf[lab.isin(["pace", "spin"]) & (bf["balls"] >= 60)]
    y = (lab[train.index] == "spin").astype(int)
    feats = ["pp", "death", "wide", "nb", "byes", "dot", "six", "four", "wkt", "st", "lbw", "bwd"]
    clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=0)
    from sklearn.model_selection import cross_val_score
    acc = cross_val_score(clf, train[feats], y, cv=4, scoring="accuracy").mean()
    clf.fit(train[feats], y)
    need = bf.index[~lab.isin(["pace", "spin"])]
    if len(need):
        p = clf.predict_proba(bf.loc[need, feats])[:, 1]
        st.loc[need, "bowl_group"] = np.where(p > 0.5, "spin", "pace")
        st.loc[need, "style_inferred"] = True
        st.loc[need, "p_spin"] = p
    st["bowl_subtype"] = [subtype_of(t if isinstance(t, str) else "", g) for t, g in zip(st["bowl_type"], st["bowl_group"])]
    st.attrs["clf_acc"] = float(acc)
    return st, float(acc)


# %% build model frame


def build():
    b = pd.read_parquet(PROC / "balls.parquet")
    b = b[(b["innings"].isin([1, 2])) & (~b["super_over"])].copy()
    b["cls"] = b["cls"].astype(str)
    b["y"] = b["cls"].map({c: i for i, c in enumerate(CLASSES)}).astype(np.int8)
    b["legal"] = ~b["cls"].isin(["wide", "noball"])
    b["phase"] = np.select([b["over"] < 6, b["over"] < 15], [0, 1], 2).astype(np.int8)
    b["wk_b"] = np.minimum(b["wkts_before"], 7).astype(np.int8)
    b["bf_b"] = bucket(b["bf_before"].to_numpy(), BF_EDGES).astype(np.int8)
    balls_left = (120 - b["legal_before"]).clip(lower=1)
    need = b["target"] - b["score_before"]
    rrr = need * 6 / balls_left
    b["rrr"] = rrr.astype("float32")
    b["rrr_b"] = np.where(b["innings"] == 2, bucket(rrr.fillna(8).to_numpy(), RRR_EDGES), -1).astype(np.int8)
    # season labels: IPL "2007/08" etc -> calendar year of the matches
    b["season"] = b["season"].astype(str)
    ipl = b["comp"] == "IPL"
    b.loc[ipl, "season"] = b.loc[ipl, "date"].dt.year.astype(str)
    b["comp_season"] = b["comp"].astype(str) + "|" + b["season"]
    st, acc = load_styles(b)
    b["bat_hand"] = b["batter"].map(st["bat_hand"]).fillna("U")
    b["bowl_subtype"] = b["bowler"].map(st["bowl_subtype"]).fillna("pace_U")
    b["bowl_spin"] = b["bowler"].map(st["bowl_group"]).eq("spin")
    b["tier"] = b["comp"].astype(str).map(TIER_OF).fillna("assoc")
    # player covariates (career, unweighted)
    cov = player_covariates(b, st)
    cols = ["match_id", "comp", "comp_season", "season", "date", "venue", "innings", "over", "phase",
            "legal_before", "wk_b", "bf_b", "bf_before", "rrr_b", "rrr", "batter", "non_striker", "bowler",
            "bat_hand", "bowl_subtype", "bowl_spin", "y", "cls", "legal", "runs_bat", "runs_extras",
            "runs_total", "wides", "noballs", "byes", "wicket_kind", "player_out", "wkts_before",
            "score_before", "target", "bat_pos", "bat_team", "bowl_team", "reduced", "tier",
            "brun_before", "winner", "toss_winner", "toss_decision", "non_boundary", "ns_bf_before"]
    b = b[cols].reset_index(drop=True)
    for c in ["comp", "comp_season", "season", "venue", "bat_hand", "bowl_subtype", "cls", "tier"]:
        b[c] = b[c].astype("category")
    b.to_parquet(PROC / "frame.parquet", index=False)
    st.to_parquet(PROC / "styles.parquet")
    cov.to_parquet(PROC / "covariates.parquet")
    return acc


def player_covariates(b, st):
    # batter role from median batting position (first ball of each innings)
    first = b.drop_duplicates(["match_id", "innings", "batter"])
    pos = first.groupby("batter")["bat_pos"].median()
    role_bat = pd.cut(pos, [0, 2.5, 4.5, 7.5, 20], labels=["open", "top", "middle", "lower"]).astype(str)
    # bowler role: overs per match bowled
    ov = b[b["legal"]].groupby(["bowler", "match_id"]).size().groupby("bowler").mean() / 6
    grp = st["bowl_group"].reindex(ov.index).fillna("pace").replace("none", "pace")
    lvl = pd.cut(ov, [-1, 1.5, 2.75, 10], labels=["part", "reg", "front"]).astype(str)
    role_bowl = grp + "_" + lvl
    # tier shares
    tb = b.groupby(["batter", "tier"], observed=True).size().unstack(fill_value=0).reindex(columns=TIERS, fill_value=0)
    tw = b.groupby(["bowler", "tier"], observed=True).size().unstack(fill_value=0).reindex(columns=TIERS, fill_value=0)
    tb = tb.div(tb.sum(axis=1), axis=0)
    tw = tw.div(tw.sum(axis=1), axis=0)
    allp = st.index
    cov = pd.DataFrame(index=allp)
    cov["role_bat"] = role_bat.reindex(allp).fillna("lower")
    cov["bat_pos_med"] = pos.reindex(allp)
    cov["role_bowl"] = role_bowl.reindex(allp).fillna("pace_part")
    cov["overs_per_match"] = ov.reindex(allp)
    for t in TIERS:
        cov["bat_tier_" + t] = tb[t].reindex(allp).fillna(0)
        cov["bowl_tier_" + t] = tw[t].reindex(allp).fillna(0)
    return cov


if __name__ == "__main__":
    acc = build()
    print(f"frame built; pace/spin classifier CV accuracy={acc:.3f}")
