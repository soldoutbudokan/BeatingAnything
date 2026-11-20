"""Model frame for one format: match-state buckets, player styles, and the prior covariates.

Every prior covariate is measured as of the delivery (role so far, experience so far, age, the other
format's record before that date), so a forward holdout never sees a player's future.
"""
# %% imports
import json
import sys

import numpy as np
import pandas as pd

from models.intl.config import (AGE_EDGES, CLASSES, FORMATS, IPL_STYLES, LEAD2_EDGES, LEAD3_EDGES, META_RDA, MO_EDGES,
                                NEED4_EDGES, REM4_EDGES, RR4_EDGES, RRR_EDGES, SCORE1_EDGES, SPELL_EDGES,
                                TEST_OVERS_NOMINAL)

XF_K = 300.0   # prior balls for the shrunk other-format rates
XF_EDGES = [0, 1, 300, 1500]   # other-format experience: none, <300, 300-1499, 1500+ balls


def bucket(x, edges):
    return np.searchsorted(np.asarray(edges, float), np.asarray(x, float), side="right") - 1


def age_bucket(age):
    a = np.asarray(age, float)
    b = np.searchsorted(AGE_EDGES, np.nan_to_num(a, nan=-1), side="right") - 1
    return np.where(np.isnan(a) | (b < 0), len(AGE_EDGES), b).astype(np.int8)


def subtype_of(bowl_type, group):
    bt = bowl_type if isinstance(bowl_type, str) else ""
    if bt in ("RF", "RFM", "RM", "RMF", "RS"):
        return "pace_R"
    if bt in ("LF", "LFM", "LM", "LMF", "LS"):
        return "pace_L"
    if bt in ("OB", "LB", "SLA", "SLW"):
        return bt
    return "spin_U" if group == "spin" else "pace_U"


# %% player metadata (styles, dates of birth, country)


def load_meta():
    """cricketdata::player_meta keyed by cricsheet id: dob, batting hand, bowling type."""
    if not META_RDA.exists():
        return pd.DataFrame(columns=["dob", "bat_hand", "bowl_type", "country"])
    import pyreadr
    from models.ipl.static.build_player_styles import norm_bat, norm_bowl
    m = list(pyreadr.read_r(str(META_RDA)).values())[0]
    m = m.dropna(subset=["cricsheet_id"]).drop_duplicates("cricsheet_id").set_index("cricsheet_id")
    out = pd.DataFrame(index=m.index)
    out["dob"] = pd.to_datetime(m["dob"], errors="coerce")
    out["bat_hand"] = [norm_bat(x) for x in m["batting_style"]]
    out["bowl_type"] = [norm_bowl(x)[0] for x in m["bowling_style"]]
    out["country"] = m["country"]
    return out


def bowler_features(b):
    g = b.groupby("bowler")
    cls = b["cls"]
    f = pd.DataFrame({"balls": g.size()})
    for c, lab in (("wide", "wide"), ("noball", "nb"), ("byes", "byes"), ("r0", "dot"), ("r6", "six"), ("r4", "four"),
                   ("wicket", "wkt")):
        f[lab] = (cls == c).groupby(b["bowler"]).mean()
    for p, lab in ((0, "p0"), (2, "p2")):
        f[lab] = (b["phase"] == p).groupby(b["bowler"]).mean()
    wk = b[cls == "wicket"]
    for kind, lab in (("stumped", "st"), ("lbw", "lbw"), ("bowled", "bwd")):
        f[lab] = (wk["wicket_kind"].astype(str) == kind).groupby(wk["bowler"]).mean()
    return f.fillna(0.0)


def load_styles(b):
    """Hand and bowling type per player: curated T20 file first, then cricketdata; bowlers still without a
    pace/spin label are classed by a classifier on how their deliveries behave (flagged style_inferred)."""
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    meta = load_meta()
    ipl = pd.read_csv(IPL_STYLES, dtype=str).drop_duplicates("cricsheet_id").set_index("cricsheet_id")
    allp = pd.Index(pd.unique(np.concatenate([b["batter"].unique(), b["non_striker"].unique(), b["bowler"].unique()])))
    st = pd.DataFrame(index=allp)
    blank = lambda s: s.where(s.notna() & (s != ""))
    st["bat_hand"] = blank(ipl["bat_hand"].reindex(allp)).fillna(blank(meta["bat_hand"].reindex(allp)))
    bt = blank(ipl["bowl_type"].reindex(allp)).fillna(blank(meta["bowl_type"].reindex(allp)))
    st["bowl_type"] = bt.where(bt != "none")
    grp = st["bowl_type"].map(lambda t: "pace" if isinstance(t, str) and t[0] in "RL" and t not in ("LB",) and t not in ("OB", "SLA", "SLW")
                              else ("spin" if isinstance(t, str) else None))
    st["bowl_group"] = grp
    st["style_inferred"] = False
    bf = bowler_features(b)
    lab = st["bowl_group"].reindex(bf.index)
    train = bf[lab.isin(["pace", "spin"]) & (bf["balls"] >= 120)]
    feats = [c for c in bf.columns if c != "balls"]
    clf = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=0)
    y = (lab[train.index] == "spin").astype(int)
    acc = float(cross_val_score(clf, train[feats], y, cv=4, scoring="accuracy").mean())
    clf.fit(train[feats], y)
    need = bf.index[~lab.isin(["pace", "spin"])]
    if len(need):
        p = clf.predict_proba(bf.loc[need, feats])[:, 1]
        st.loc[need, "bowl_group"] = np.where(p > 0.5, "spin", "pace")
        st.loc[need, "style_inferred"] = True
    st["bowl_subtype"] = [subtype_of(t, g) for t, g in zip(st["bowl_type"], st["bowl_group"])]
    st["dob"] = meta["dob"].reindex(allp)
    st["meta_country"] = meta["country"].reindex(allp)
    return st, acc


# %% other-format record before each delivery


def _xfmt_cum(other, who):
    """Cumulative other-format totals per player at the start of each of his match dates."""
    cls = other["cls"].astype(str)
    if who == "batter":
        d = pd.DataFrame({"p": other["batter"], "date": other["date"], "n": (cls != "wide").astype(float),
                          "a": np.where(cls.isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), other["runs_bat"], 0).astype(float),
                          "b": ((cls == "wicket") | ((cls == "runout") & (other["player_out"] == other["batter"]))).astype(float)})
    else:
        d = pd.DataFrame({"p": other["bowler"], "date": other["date"], "n": (~cls.isin(["wide", "noball"])).astype(float),
                          "a": (other["runs_total"] - other["byes"]).astype(float), "b": (cls == "wicket").astype(float)})
    g = d.groupby(["p", "date"], sort=True)[["n", "a", "b"]].sum().reset_index()
    g[["n", "a", "b"]] = g.groupby("p")[["n", "a", "b"]].cumsum() - g[["n", "a", "b"]]   # totals before that date
    mu_a, mu_b = d["a"].sum() / d["n"].sum(), d["b"].sum() / d["n"].sum()
    last = d.groupby("p")[["n", "a", "b"]].sum()
    last_date = d.groupby("p")["date"].max()
    return g, (mu_a, mu_b), last, last_date


def xfmt_join(b, other, who):
    """For each row: the player's other-format experience bucket and shrunk log-rate ratios before the date."""
    if other is None or not len(other):
        z = np.zeros(len(b))
        return z.astype(np.int8), z, z, None
    g, (mu_a, mu_b), _, _ = _xfmt_cum(other, who)
    key = pd.DataFrame({"p": b[who].to_numpy(), "date": b["date"].to_numpy(), "i": np.arange(len(b))}).sort_values("date", kind="stable")
    m = pd.merge_asof(key, g.sort_values("date", kind="stable"), on="date", by="p", direction="backward", allow_exact_matches=True)
    m = m.sort_values("i")
    n, a, bb = (m[c].fillna(0.0).to_numpy() for c in ("n", "a", "b"))
    # merge_asof took the last other-format date <= this date; its row holds totals *before* that date, so the
    # other-format match on that same day (never the same match) is excluded: conservative
    xa = np.log((a + XF_K * mu_a) / (n + XF_K)) - np.log(mu_a)
    xb = np.log((bb + XF_K * mu_b) / (n + XF_K)) - np.log(mu_b)
    return bucket(n, XF_EDGES).astype(np.int8), xa, xb, (mu_a, mu_b)


def xfmt_current(other, who):
    """Current other-format covariates per player (all of his other-format record)."""
    if other is None or not len(other):
        return pd.DataFrame(columns=["xb", "xa", "xo"])
    _, (mu_a, mu_b), tot, _ = _xfmt_cum(other, who)
    out = pd.DataFrame(index=tot.index)
    out["xb"] = bucket(tot["n"], XF_EDGES)
    out["xa"] = np.log((tot["a"] + XF_K * mu_a) / (tot["n"] + XF_K)) - np.log(mu_a)
    out["xo"] = np.log((tot["b"] + XF_K * mu_b) / (tot["n"] + XF_K)) - np.log(mu_b)
    return out


# %% Test time model: overs available in a match


def overs_available(matches):
    """Kaplan-Meier estimate of the overs a Test has room for, by host country. A draw shows the overs that
    were available (time ran out); a result only shows that at least that many were. Countries with few Tests
    are shrunk toward the pooled curve. Returns {country: quantile table} and the typical (median) overs."""
    m = matches[matches["date"] >= "2010-01-01"]
    grid = np.arange(0, TEST_OVERS_NOMINAL + 1)

    def km(d):
        t = np.clip(np.round(d["m_legal"].to_numpy() / 6).astype(int), 1, TEST_OVERS_NOMINAL)
        ev = (d["result"].astype(str) == "draw").to_numpy()
        S = np.ones(len(grid))
        s = 1.0
        for k in grid[1:]:
            at_risk = (t >= k).sum()
            if at_risk > 0:
                s *= 1 - (ev & (t == k)).sum() / at_risk
            S[k] = s
        return S

    pooled = km(m)
    out = {}
    for c, d in m.groupby("country"):
        w = len(d) / (len(d) + 40.0)
        out[c] = w * km(d) + (1 - w) * pooled
    out["_pooled"] = pooled
    qs = (np.arange(40) + 0.5) / 40   # 40 equally likely values; the simulator draws one per match

    def quantiles(S):
        # survivors past 450 overs get the full five days
        cdf = 1 - S
        return [int(grid[min(np.searchsorted(cdf, q, side="left"), len(grid) - 1)]) if q < cdf[-1] else TEST_OVERS_NOMINAL
                for q in qs]

    return {c: quantiles(S) for c, S in out.items()}


# %% build


def build(key):
    fmt = FORMATS[key]
    b = pd.read_parquet(fmt.proc / "balls.parquet")
    m = pd.read_parquet(fmt.proc / "matches.parquet")
    okey = "test" if key == "odi" else "odi"
    opath = FORMATS[okey].proc / "balls.parquet"
    other = pd.read_parquet(opath, columns=["batter", "bowler", "date", "cls", "runs_bat", "runs_total", "byes",
                                            "player_out"]) if opath.exists() else None
    b["cls"] = b["cls"].astype(str)
    b["y"] = b["cls"].map({c: i for i, c in enumerate(CLASSES)}).astype(np.int8)
    b["legal"] = ~b["cls"].isin(["wide", "noball"])
    b["phase"] = fmt.phase_of_over(b["over"].to_numpy())
    b["ovb"] = fmt.over_bucket(np.minimum(b["over"].to_numpy(), 10**6))
    b["wk_b"] = np.minimum(b["wkts_before"], 9).astype(np.int8)
    b["bf_b"] = bucket(b["bf_before"].to_numpy(), fmt.bf_edges).astype(np.int8)
    b["country"] = b["country"].astype(str)
    b["bat_home"] = (b["bat_team"].astype(str) == b["country"]).to_numpy()
    b["bowl_home"] = (b["bowl_team"].astype(str) == b["country"]).to_numpy()
    b["season"] = b["season"].astype(str)
    b["comp_season"] = b["country"] + "|" + b["season"]
    b["year"] = b["date"].dt.year.astype(str)
    # ---- format-specific match state
    if key == "odi":
        left = (fmt.max_overs * 6 - b["legal_before"]).clip(lower=1)
        rrr = (b["target"] - b["score_before"]) * 6.0 / left
        b["rrr"] = rrr.astype("float32")
        b["rrr_b"] = np.where(b["inn"] == 2, bucket(rrr.fillna(5.0).to_numpy(), RRR_EDGES), -1).astype(np.int8)
        b["wih_b"] = np.select([b["wkts_before"] >= 7, b["wkts_before"] >= 4], [0, 1], 2).astype(np.int8)  # wickets in hand 1-3, 4-6, 7-10
        avail_q = None
    else:
        avail_q = overs_available(m)
        typical = {c: float(np.median(q)) for c, q in avail_q.items()}
        mo = m["m_legal"] / 6.0
        a = np.where(m["result"].astype(str) == "draw", mo,
                     np.maximum(mo + 10, m["country"].map(typical).fillna(typical["_pooled"])))
        avail = pd.Series(np.minimum(a, TEST_OVERS_NOMINAL + 10), index=m["match_id"])
        b["avail"] = b["match_id"].map(avail).astype("float32")
        m_ov = b["m_legal_before"] / 6.0
        b["mo_b"] = bucket(m_ov.to_numpy(), MO_EDGES).astype(np.int8)
        rem = (b["avail"] - m_ov).clip(lower=1.0)
        b["rem_ov"] = rem.astype("float32")
        wkg = np.select([b["wkts_before"] <= 3, b["wkts_before"] <= 6], [0, 1], 2)
        b["wkg"] = wkg.astype(np.int8)
        b["lead3_b"] = np.where(b["inn"] == 3, bucket(b["lead_before"].to_numpy(), LEAD3_EDGES), -1).astype(np.int8)
        # first two innings: the batting side's position (runs on the board, then the lead)
        b["pos12_b"] = np.select([b["inn"] == 1, b["inn"] == 2],
                                 [bucket(b["lead_before"].to_numpy(), SCORE1_EDGES),
                                  5 + bucket(b["lead_before"].to_numpy(), LEAD2_EDGES)], -1).astype(np.int8)
        need = b["target"] - b["score_before"]
        b["need4_b"] = np.where(b["inn"] == 4, bucket(need.fillna(0).to_numpy(), NEED4_EDGES), -1).astype(np.int8)
        rr4 = need / rem
        b["rr4_b"] = np.where(b["inn"] == 4, bucket(rr4.fillna(0).to_numpy(), RR4_EDGES) * 4 + bucket(rem.to_numpy(), REM4_EDGES), -1).astype(np.int8)
        b["spell_b"] = bucket((b["bowl_legal_before"] // 6).to_numpy(), SPELL_EDGES).astype(np.int8)
    # ---- styles
    st, acc = load_styles(b)
    b["bat_hand"] = b["batter"].map(st["bat_hand"]).fillna("U")
    b["bowl_subtype"] = b["bowler"].map(st["bowl_subtype"]).fillna("pace_U")
    b["bowl_spin"] = b["bowler"].map(st["bowl_group"]).eq("spin").to_numpy()
    # ---- experience, role and age as of the delivery
    faced = (b["cls"] != "wide").astype(np.int32)
    cum_f = faced.groupby(b["batter"]).cumsum() - faced
    b["exp_bat_row"] = bucket(cum_f.to_numpy(), fmt.exp_edges).astype(np.int8)
    lg = b["legal"].astype(np.int32)
    cum_w = lg.groupby(b["bowler"]).cumsum() - lg
    b["exp_bowl_row"] = bucket(cum_w.to_numpy(), fmt.exp_edges).astype(np.int8)
    # batter role: mean batting position over his innings so far, this one included (known when he walks in)
    first = b.drop_duplicates(["match_id", "inn", "batter"])[["match_id", "inn", "batter", "bat_pos"]].copy()
    first["mpos"] = first.groupby("batter")["bat_pos"].transform(lambda s: s.expanding().mean())
    first["role"] = np.select([first["mpos"] <= 2.5, first["mpos"] <= 4.5, first["mpos"] <= 7.5, first["mpos"] <= 9.5],
                              [0, 1, 2, 3], 4).astype(np.int8)
    b = b.merge(first[["match_id", "inn", "batter", "role", "mpos"]].rename(columns={"role": "role_bat_row", "mpos": "bat_pos_mean"}),
                on=["match_id", "inn", "batter"], how="left")
    # bowler role: pace/spin x overs per match so far (this match included)
    pm = b[b["legal"]].groupby(["bowler", "match_id"], sort=False).size().rename("n").reset_index()
    pm["opm"] = pm.groupby("bowler")["n"].transform(lambda s: s.expanding().mean()) / 6.0
    lo, hi = fmt.role_overs
    pm["lvl"] = np.select([pm["opm"] < lo, pm["opm"] < hi], [0, 1], 2)
    b = b.merge(pm[["bowler", "match_id", "lvl", "opm"]], on=["bowler", "match_id"], how="left")
    b["role_bowl_row"] = (b["bowl_spin"].astype(int) * 3 + b["lvl"].fillna(0).astype(int)).astype(np.int8)
    b = b.rename(columns={"opm": "bowl_opm"}).drop(columns=["lvl"])
    for who, col in (("batter", "age_bat_b"), ("bowler", "age_bowl_b")):
        age = (b["date"] - b[who].map(st["dob"])).dt.days / 365.25
        b[col] = age_bucket(age.to_numpy())
    # ---- other-format record before the date
    for who, pre in (("batter", "xb"), ("bowler", "xw")):
        xb, xa, xo, _ = xfmt_join(b, other, who)
        b[pre + "_b"], b[pre + "_a"], b[pre + "_o"] = xb, xa.astype("float32"), xo.astype("float32")
    keep = ["match_id", "date", "season", "year", "country", "comp_season", "venue", "inn", "over", "ovb", "phase",
            "legal_before", "m_legal_before", "wk_b", "wkts_before", "bf_b", "bf_before", "batter", "non_striker", "bowler",
            "bat_team", "bowl_team", "bat_home", "bowl_home", "bat_hand", "bowl_subtype", "bowl_spin", "y", "cls", "legal",
            "runs_bat", "runs_extras", "runs_total", "wides", "noballs", "byes", "wicket_kind", "player_out",
            "score_before", "target", "lead_before", "bat_pos", "bat_pos_mean", "bowl_opm", "role_bat_row", "role_bowl_row",
            "exp_bat_row", "exp_bowl_row", "age_bat_b", "age_bowl_b", "xb_b", "xb_a", "xb_o", "xw_b", "xw_a", "xw_o",
            "bowl_legal_before", "pp_type", "reduced", "winner", "result", "brun_before"]
    keep += ["rrr", "rrr_b", "wih_b"] if key == "odi" else ["avail", "mo_b", "rem_ov", "wkg", "lead3_b", "pos12_b", "need4_b", "rr4_b", "spell_b"]
    f = b[keep].reset_index(drop=True)
    for c in ("season", "year", "country", "comp_season", "venue", "bat_hand", "bowl_subtype", "cls", "bat_team", "bowl_team"):
        f[c] = f[c].astype("category")
    f.to_parquet(fmt.proc / "frame.parquet", index=False)
    st.to_parquet(fmt.proc / "styles.parquet")
    side = {"clf_acc": acc, "avail_q": avail_q}
    (fmt.proc / "prep.json").write_text(json.dumps(side))
    print(f"{key}: frame {len(f):,} rows; pace/spin classifier CV accuracy {acc:.3f}; "
          f"hand known {100 * (f['bat_hand'].astype(str) != 'U').mean():.1f}% of balls; "
          f"bowling type known {100 * (~f['bowl_subtype'].astype(str).str.endswith('_U')).mean():.1f}% of balls")
    return acc


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        build(k)
