"""Turn the fitted logit model into (a) sim_params.json and (b) context-adjusted player / venue metrics.

Ratings are stated in reference conditions: every recent delivery between full members is re-evaluated with
the player swapped in (as batter or bowler), keeping the real opponent, ground, era and match state.
"""
# %% imports
import json
import pickle
import sys

import numpy as np
import pandas as pd

from models.intl.config import (AGE_LABELS, CLASSES, FORMATS, FULL_MEMBERS, K, LEAD2_EDGES, LEAD3_EDGES, MO_EDGES,
                                NEED4_EDGES, PEOPLE, REF, REM4_EDGES, ROLES_BAT, ROLES_BOWL, RR4_EDGES, RRR_EDGES,
                                RRR_LABELS, SCORE1_EDGES, SPELL_EDGES, SUBTYPES, TYPES6)
from models.intl.fit import XF_LEVELS, build_design, load
from models.intl.prep import age_bucket, xfmt_current

C = {c: i for i, c in enumerate(CLASSES)}
INACTIVE_GRACE, INACTIVE_TAU = 1.0, 2.0   # years: individual deviations decay as exp(-(gap - grace)/tau)
BAT_BLOCKS = ["bat", "bat_pp", "bat_death", "bat_spin", "bat_early", "bat_away", "bat_type", "bat_role", "bat_exp",
              "bat_age", "bat_team", "bat_xf", "sub_lhb", "bowl_lhb", "tail"]
BOWL_BLOCKS = ["bowl", "bowl_pp", "bowl_death", "bowl_lhb", "bowl_away", "bowl_role", "bowl_exp", "bowl_age", "bowl_team",
               "bowl_xf", "sub", "sub_lhb", "sub_ph", "bat_spin", "bat_type", "venue_spin", "comp_spin", "cs_spin",
               "gs_spin", "mo_spin", "spell"]
ENV_BLOCKS = ["comp", "comp_spin", "comp_ph", "cs", "cs_spin", "venue", "venue_late", "venue_spin"]
REF_ROWS = 40000


def r3(x, d=3):
    return np.round(np.asarray(x, float), d).tolist()


def softmax(eta):
    e = np.exp(eta - eta.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


# %% model access


class Model:
    def __init__(self, key, name="model.pkl"):
        self.fmt = FORMATS[key]
        with open(self.fmt.proc / name, "rb") as fh:
            m = pickle.load(fh)
        self.m = m
        self.lam = m["lam"]
        self.W = np.insert(m["W"], REF, 0.0, axis=1)
        self.SD = np.insert(m["sd"], REF, 0.0, axis=1)
        self.blocks = m["blocks"]
        self.idx = m["idx"]
        self.pos = {k: {v: i for i, v in enumerate(self.idx[k])} for k in ("bat", "bowl", "venues", "comps", "comp_seasons", "years", "teams")}

    def blk(self, name, sd=False):
        if name not in self.blocks:
            return None
        o, labels, _ = self.blocks[name]
        return (self.SD if sd else self.W)[o:o + len(labels)]

    def cols(self, names):
        out = []
        for nme in names:
            if nme in self.blocks:
                o, labels, _ = self.blocks[nme]
                out.append(np.arange(o, o + len(labels)))
        return np.concatenate(out)

    def latest_season(self, country):
        labs = [l for l in self.idx["comp_seasons"] if l.split("|")[0] == country]
        return labs[-1] if labs else None

    def env(self, country):
        """Projection environment for a host country: latest year + country + its latest season."""
        z = np.zeros(K)
        gs, gsp, gss = self.blk("gs"), self.blk("gs_ph"), self.blk("gs_spin")
        ny = len(self.idx["years"])
        allv, spin, ph0, ph2 = gs[ny - 1].copy(), gss[ny - 1].copy(), gsp[2 * (ny - 1)].copy(), gsp[2 * (ny - 1) + 1].copy()
        season = None
        if country in self.pos["comps"]:
            ci = self.pos["comps"][country]
            allv += self.blk("comp")[ci]
            spin += self.blk("comp_spin")[ci]
            ph0 += self.blk("comp_ph")[2 * ci]
            ph2 += self.blk("comp_ph")[2 * ci + 1]
            season = self.latest_season(country)
            if season:
                k = self.pos["comp_seasons"][season]
                allv += self.blk("cs")[k]
                spin += self.blk("cs_spin")[k]
        return {"all": allv, "spin": spin, "ph": [ph0, z, ph2], "season": season}


def load_people():
    p = pd.read_csv(PEOPLE, dtype=str)
    return p.set_index("identifier")["name"].to_dict(), p


# %% projection vectors


def last_played(key):
    """Last international (either format) per player."""
    out = []
    for k in ("odi", "test"):
        p = FORMATS[k].proc / "balls.parquet"
        if p.exists():
            b = pd.read_parquet(p, columns=["batter", "non_striker", "bowler", "date"])
            out += [b.groupby(c)["date"].max() for c in ("batter", "non_striker", "bowler")]
    return pd.concat(out).groupby(level=0).max()


def current_covariates(f, fmt, styles, proj_date):
    """Each player's prior covariates today: role over his last ten innings / matches, experience bucket,
    latest team, age at the projection date, the other format's record."""
    first = f.drop_duplicates(["match_id", "inn", "batter"])
    pos = first.groupby("batter")["bat_pos"].apply(lambda s: s.tail(10).mean())
    cb = pd.DataFrame({"pos": pos})
    cb["role"] = np.select([cb["pos"] <= 2.5, cb["pos"] <= 4.5, cb["pos"] <= 7.5, cb["pos"] <= 9.5], [0, 1, 2, 3], 4)
    nb = f[f["cls"].astype(str) != "wide"].groupby("batter").size()
    cb["balls"] = nb.reindex(cb.index).fillna(0)
    cb["exp"] = np.searchsorted(np.asarray(fmt.exp_edges), cb["balls"].to_numpy(), side="right") - 1
    cb["team"] = f.groupby("batter")["bat_team"].last().astype(str).reindex(cb.index)
    lg = f[f["legal"]]
    pm = lg.groupby(["bowler", "match_id"], sort=False).size() / 6.0
    opm = pm.groupby(level=0).apply(lambda s: s.tail(10).mean())
    cw = pd.DataFrame({"opm": opm})
    spin = styles["bowl_group"].reindex(cw.index).eq("spin")
    lo, hi = fmt.role_overs
    cw["role"] = spin.astype(int) * 3 + np.select([cw["opm"] < lo, cw["opm"] < hi], [0, 1], 2)
    cw["balls"] = lg.groupby("bowler").size().reindex(cw.index).fillna(0)
    cw["exp"] = np.searchsorted(np.asarray(fmt.exp_edges), cw["balls"].to_numpy(), side="right") - 1
    cw["team"] = f.groupby("bowler")["bowl_team"].last().astype(str).reindex(cw.index)
    cw["spin"] = spin
    pdate = pd.Timestamp(proj_date)
    for c in (cb, cw):
        c["age_b"] = age_bucket(((pdate - styles["dob"].reindex(c.index)).dt.days / 365.25).to_numpy())
    okey = "test" if fmt.key == "odi" else "odi"
    op = FORMATS[okey].proc / "balls.parquet"
    other = pd.read_parquet(op, columns=["batter", "bowler", "date", "cls", "runs_bat", "runs_total", "byes", "player_out"]) if op.exists() else None
    for c, who in ((cb, "batter"), (cw, "bowler")):
        x = xfmt_current(other, who).reindex(c.index)
        c["xb"], c["xa"], c["xo"] = x["xb"].fillna(0).astype(int), x["xa"].fillna(0.0), x["xo"].fillna(0.0)
    return cb, cw


def xf_term(blk, xb, xa, xo):
    """Other-format prior for arrays of (bucket, log-rate ratios)."""
    if blk is None:
        return 0.0
    lvl = np.vstack([np.zeros((1, K)), blk[:XF_LEVELS - 1]])
    return lvl[np.asarray(xb, int)] + np.asarray(xa)[:, None] * blk[XF_LEVELS - 1] + np.asarray(xo)[:, None] * blk[XF_LEVELS]


def folded_players(M, f, styles, proj_date):
    """Projection logit vectors per batter / bowler: individual deviation (decayed after long inactivity) plus the
    prior mean at today's covariates. Splits are decayed the same way."""
    fmt = M.fmt
    cb, cw = current_covariates(f, fmt, styles, proj_date)
    lp = last_played(fmt.key)
    ref = pd.Timestamp(M.m["ref_date"])
    ne, na = len(fmt.exp_edges), len(AGE_LABELS)

    def inact(ids):
        gap = (ref - lp.reindex(ids)).dt.days.to_numpy() / 365.25
        return np.exp(-np.clip(np.nan_to_num(gap, nan=10.0) - INACTIVE_GRACE, 0, None) / INACTIVE_TAU)

    ids = M.idx["bat"]
    c = cb.reindex(ids)
    role = c["role"].fillna(3).astype(int).to_numpy()
    ti = c["team"].map(M.pos["teams"]).fillna(-1).astype(int).to_numpy()
    team_b = np.where((ti >= 0)[:, None], M.blk("bat_team")[np.maximum(ti, 0)], 0.0)
    prior = (M.blk("bat_role")[role] + M.blk("bat_exp")[role * ne + c["exp"].fillna(0).astype(int).to_numpy()]
             + M.blk("bat_age")[c["age_b"].fillna(na - 1).astype(int).to_numpy()] + team_b
             + xf_term(M.blk("bat_xf"), c["xb"].fillna(0), c["xa"].fillna(0.0), c["xo"].fillna(0.0)))
    fb = inact(ids)[:, None]
    nbat = len(ids)
    BAT = {"b": M.blk("bat") * fb + prior, "pp": M.blk("bat_pp") * fb, "de": M.blk("bat_death") * fb,
           "sp": M.blk("bat_spin") * fb, "ea": M.blk("bat_early") * fb, "aw": M.blk("bat_away") * fb,
           "ty": M.blk("bat_type").reshape(nbat, len(TYPES6), K) * fb[:, :, None], "prior": prior, "inact": fb[:, 0],
           "role": role, "team": c["team"].to_numpy(), "lhb": styles["bat_hand"].reindex(ids).eq("L").to_numpy(),
           "pos": c["pos"].to_numpy(), "cov": c}
    for k, blkname in (("b", "bat"), ("pp", "bat_pp"), ("de", "bat_death"), ("sp", "bat_spin"), ("ea", "bat_early"), ("aw", "bat_away")):
        BAT["sd_" + k] = M.blk(blkname, True)
    ids = M.idx["bowl"]
    c = cw.reindex(ids)
    spin = styles["bowl_group"].reindex(ids).eq("spin").to_numpy()
    role = c["role"].fillna(pd.Series(spin.astype(int) * 3, index=ids)).astype(int).to_numpy()
    ti = c["team"].map(M.pos["teams"]).fillna(-1).astype(int).to_numpy()
    team_w = np.where((ti >= 0)[:, None], M.blk("bowl_team")[np.maximum(ti, 0)], 0.0)
    prior = (M.blk("bowl_role")[role] + M.blk("bowl_exp")[role * ne + c["exp"].fillna(0).astype(int).to_numpy()]
             + M.blk("bowl_age")[spin.astype(int) * na + c["age_b"].fillna(na - 1).astype(int).to_numpy()] + team_w
             + xf_term(M.blk("bowl_xf"), c["xb"].fillna(0), c["xa"].fillna(0.0), c["xo"].fillna(0.0)))
    fw = inact(ids)[:, None]
    BOWL = {"b": M.blk("bowl") * fw + prior, "pp": M.blk("bowl_pp") * fw, "de": M.blk("bowl_death") * fw,
            "lh": M.blk("bowl_lhb") * fw, "aw": M.blk("bowl_away") * fw, "prior": prior, "inact": fw[:, 0], "role": role,
            "team": c["team"].to_numpy(), "spin": spin, "opm": c["opm"].to_numpy(), "cov": c,
            "sub": styles["bowl_subtype"].reindex(ids).fillna("pace_U").map({s: i for i, s in enumerate(SUBTYPES)}).to_numpy()}
    for k, blkname in (("b", "bowl"), ("pp", "bowl_pp"), ("de", "bowl_death"), ("lh", "bowl_lhb"), ("aw", "bowl_away")):
        BOWL["sd_" + k] = M.blk(blkname, True)
    # priors for players the model has not seen: role mean at the least-experienced bucket and unknown age;
    # the simulator adds the team term
    au = na - 1
    pri_b = {r: M.blk("bat_role")[i] + M.blk("bat_exp")[i * ne] + M.blk("bat_age")[au] for i, r in enumerate(ROLES_BAT)}
    pri_w = {r: M.blk("bowl_role")[i] + M.blk("bowl_exp")[i * ne] + M.blk("bowl_age")[int(i >= 3) * na + au]
             for i, r in enumerate(ROLES_BOWL)}
    return BAT, BOWL, pri_b, pri_w


# %% reference sample and player substitution


class Ref:
    """Real deliveries whose logits can be re-evaluated with another batter or bowler swapped in."""

    def __init__(self, M, f, BAT, BOWL):
        fmt = M.fmt
        self.M, self.f, self.BAT, self.BOWL = M, f, BAT, BOWL
        D, X = build_design(f, M.idx, fmt, M.lam)
        X = X.tocsc()
        self.eta = np.asarray(X @ M.W)
        cb, cw = M.cols(BAT_BLOCKS), M.cols(BOWL_BLOCKS)
        ha_o = M.blocks["ha"][0]
        cw = np.concatenate([cw, [ha_o + 2, ha_o + 3]])
        self.eta_nobat = self.eta - np.asarray(X[:, cb] @ M.W[cb])
        self.eta_nobowl = self.eta - np.asarray(X[:, cw] @ M.W[cw])
        ce = M.cols(ENV_BLOCKS)
        self.eta_noenv = self.eta - np.asarray(X[:, ce] @ M.W[ce])
        self.ph = f["phase"].to_numpy()
        self.early = f["bf_before"].to_numpy() < fmt.early_bf
        self.spin = f["bowl_spin"].to_numpy().astype(bool)
        self.lhb = (f["bat_hand"].astype(str) == "L").to_numpy()
        self.bat_away = ~f["bat_home"].to_numpy()
        self.bowl_away = ~f["bowl_home"].to_numpy()
        self.wk = f["wk_b"].to_numpy()
        self.inn = f["inn"].to_numpy()
        self.late = self.inn >= (2 if fmt.key == "odi" else 3)
        self.bi = f["batter"].map(M.pos["bat"]).fillna(-1).astype(int).to_numpy()
        self.wi = f["bowler"].map(M.pos["bowl"]).fillna(-1).astype(int).to_numpy()
        self.sub = f["bowl_subtype"].astype(str).map({s: i for i, s in enumerate(SUBTYPES)}).to_numpy()
        self.ti = f["bowl_subtype"].astype(str).map({t: i for i, t in enumerate(TYPES6)}).fillna(-1).astype(int).to_numpy()
        self.vi = f["venue"].astype(str).map(M.pos["venues"]).fillna(-1).astype(int).to_numpy()
        self.ci = f["country"].astype(str).map(M.pos["comps"]).fillna(-1).astype(int).to_numpy()
        self.csi = f["comp_season"].astype(str).map(M.pos["comp_seasons"]).fillna(-1).astype(int).to_numpy()
        self.yi = f["year"].astype(str).map(M.pos["years"]).fillna(-1).astype(int).to_numpy()
        z = lambda a, i: np.where((i >= 0)[:, None], a[np.maximum(i, 0)], 0.0)
        self._z = z
        # row terms that involve the *other* player of the delivery (raw fitted coefficients)
        self.lterm = M.blk("sub_lhb")[self.sub] + z(M.blk("bowl_lhb"), self.wi)
        self.spterm = (z(M.blk("bat_spin"), self.bi) + z(M.blk("venue_spin"), self.vi) + z(M.blk("comp_spin"), self.ci)
                       + z(M.blk("cs_spin"), self.csi) + z(M.blk("gs_spin"), self.yi)
                       + M.blk("ha")[2] * f["bat_home"].to_numpy()[:, None] + M.blk("ha")[3] * f["bowl_home"].to_numpy()[:, None])
        if fmt.key == "test":
            self.spterm = self.spterm + M.blk("mo_spin")[f["mo_b"].to_numpy()]
            self.spell_b = f["spell_b"].to_numpy()
            self.tail_row = np.where((self.wk >= 7)[:, None], M.blk("tail")[np.clip(self.wk - 7, 0, 2)], 0.0)
        self.bty = M.blk("bat_type").reshape(len(M.idx["bat"]), len(TYPES6), K)

    def with_batter(self, v, lhb, tail, rows=None):
        """v: dict of 11-vectors b, pp, de, sp, ea, aw and ty (6 x 11)."""
        r = slice(None) if rows is None else rows
        ph = self.ph[r]
        t = (v["b"] + v["pp"] * (ph == 0)[:, None] + v["de"] * (ph == 2)[:, None] + v["sp"] * self.spin[r][:, None]
             + v["ea"] * self.early[r][:, None] + v["aw"] * self.bat_away[r][:, None])
        ti = self.ti[r]
        t = t + np.where((ti >= 0)[:, None], v["ty"][np.maximum(ti, 0)], 0.0)
        if lhb:
            t = t + self.lterm[r]
        if self.M.fmt.key == "test" and not tail:
            t = t + self.tail_row[r]
        return self.eta_nobat[r] + t

    def with_bowler(self, v, sub, spin, rows=None):
        r = slice(None) if rows is None else rows
        M, ph, lhb = self.M, self.ph[r], self.lhb[r]
        sph = np.vstack([M.blk("sub_ph"), np.zeros((1, K))])
        t = (v["b"] + v["pp"] * (ph == 0)[:, None] + v["de"] * (ph == 2)[:, None] + v["lh"] * lhb[:, None]
             + v["aw"] * self.bowl_away[r][:, None] + M.blk("sub")[sub] + M.blk("sub_lhb")[sub] * lhb[:, None]
             + sph[np.where(ph == 1, len(sph) - 1, sub * 3 + ph)])
        if spin:
            t = t + self.spterm[r]
        tnew = TYPES6.index(SUBTYPES[sub]) if SUBTYPES[sub] in TYPES6 else -1
        if tnew >= 0:
            t = t + np.where((self.bi[r] >= 0)[:, None], self.bty[np.maximum(self.bi[r], 0), tnew], 0.0)
        if M.fmt.key == "test":
            t = t + M.blk("spell")[int(spin) * len(SPELL_EDGES) + self.spell_b[r]]
        return self.eta_nobowl[r] + t


# %% metrics from class probabilities


def extras_dists(f, since):
    r = f[f["date"] >= since]
    cls = r["cls"].astype(str)

    def dist(s, vals, default):
        s = s.where(s.isin(vals), default)
        cnt = s.value_counts()
        return {"v": vals, "p": [float(cnt.get(v, 0) + 0.5) for v in vals]}

    wide = dist(r.loc[cls == "wide", "runs_total"], [1, 2, 3, 5], 1)
    nb = dist(r.loc[cls == "noball", "runs_bat"], [0, 1, 2, 3, 4, 6], 4)
    bye = dist(r.loc[cls == "byes", "byes"], [1, 2, 3, 4], 1)
    ro = r[cls == "runout"]
    ror = dist(ro["runs_bat"].clip(upper=3), [0, 1, 2, 3], 0)
    q = float((ro["player_out"] == ro["batter"]).mean())
    ex = {"wide_runs": wide, "nb_bat": nb, "bye_runs": bye, "runout_runs": ror, "runout_striker": q}
    mean = lambda d: float(np.dot(d["v"], d["p"]) / np.sum(d["p"]))
    return ex, {"wide_mean": mean(wide), "nb_bat_mean": mean(nb), "ro_runs_mean": mean(ror), "runout_striker": q,
                "bye_mean": mean(bye)}


def bat_runs_row(P, ex):
    return (P[..., C["r1"]] + 2 * P[..., C["r2"]] + 3 * P[..., C["r3"]] + 4 * P[..., C["r4"]] + 6 * P[..., C["r6"]]
            + P[..., C["noball"]] * ex["nb_bat_mean"] + P[..., C["runout"]] * ex["ro_runs_mean"])


def bat_outs_row(P, ex):
    return P[..., C["wicket"]] + ex["runout_striker"] * P[..., C["runout"]]


def conceded_row(P, ex):
    return (P[..., C["r1"]] + 2 * P[..., C["r2"]] + 3 * P[..., C["r3"]] + 4 * P[..., C["r4"]] + 6 * P[..., C["r6"]]
            + P[..., C["wide"]] * ex["wide_mean"] + P[..., C["noball"]] * (1 + ex["nb_bat_mean"])
            + P[..., C["runout"]] * ex["ro_runs_mean"])


def total_row(P, ex):
    return conceded_row(P, ex) + P[..., C["byes"]] * ex["bye_mean"]


def bat_stats(P, w, ex, wv):
    """P: (..., rows, 11); w: row weights; wv: run value of a wicket per row. Returns dict of scalars / arrays."""
    w = w / w.sum()
    m = np.tensordot(P, w, axes=([-2], [0]))
    faced = 1 - m[..., C["wide"]]
    runs = bat_runs_row(m, ex)
    outs = bat_outs_row(m, ex)
    rv = np.tensordot(bat_runs_row(P, ex) - bat_outs_row(P, ex) * wv, w, axes=([-1], [0]))
    return {"sr": 100 * runs / faced, "out_pct": 100 * outs / faced, "avg": runs / outs,
            "bnd_pct": 100 * (m[..., C["r4"]] + m[..., C["r6"]]) / faced, "six_pct": 100 * m[..., C["r6"]] / faced,
            "dot_pct": 100 * (m[..., C["r0"]] + m[..., C["wicket"]] + m[..., C["byes"]]) / faced, "rv100": 100 * rv / faced}


def bowl_stats(P, w, ex, wv):
    w = w / w.sum()
    m = np.tensordot(P, w, axes=([-2], [0]))
    legal = 1 - m[..., C["wide"]] - m[..., C["noball"]]
    conc = conceded_row(m, ex)
    wk = m[..., C["wicket"]]
    rv = np.tensordot(conceded_row(P, ex) - P[..., C["wicket"]] * wv, w, axes=([-1], [0]))
    return {"econ": 6 * conc / legal, "wkt_pct": 100 * wk / legal, "sr": legal / wk, "avg": conc / wk,
            "dot_pct": 100 * (m[..., C["r0"]] + m[..., C["wicket"]] + m[..., C["byes"]]) / legal,
            "bnd_pct": 100 * (m[..., C["r4"]] + m[..., C["r6"]]) / legal, "rv_over": 6 * rv / legal}


def resources_table(f, fmt, since):
    """ODI: expected runs still to come in a first innings from the start of over o with w wickets down
    (full-member matches since `since`), smoothed to be monotone. The value of a wicket is the drop to w + 1."""
    r = f[(f["inn"] == 1) & (f["date"] >= since)]
    tot = r.groupby("match_id")["runs_total"].sum()
    st = r[r["legal_before"] % 6 == 0].drop_duplicates(["match_id", "legal_before"])
    st = st.assign(rem=tot.reindex(st["match_id"]).to_numpy() - st["score_before"].to_numpy(),
                   o=st["legal_before"] // 6, w=st["wkts_before"].clip(upper=9))
    g = st.groupby(["o", "w"])["rem"].agg(["mean", "size"])
    n_ov = fmt.max_overs
    rate = tot.mean() / (n_ov * 6)
    ER = np.zeros((n_ov, 11))
    for o in range(n_ov):
        for w in range(10):
            fb = (n_ov - o) * 6 * rate * 1.15 * max(0.05, 1 - w / 10) ** 1.2
            if (o, w) in g.index:
                mu, n = g.loc[(o, w), "mean"], g.loc[(o, w), "size"]
                ER[o, w] = (mu * n + fb * 20) / (n + 20)
            else:
                ER[o, w] = fb
    for o in range(n_ov):
        for w in range(1, 11):
            ER[o, w] = min(ER[o, w], ER[o, w - 1])
    for w in range(11):
        for o in range(1, n_ov):
            ER[o, w] = min(ER[o, w], ER[o - 1, w])
    ER[:, 10] = 0
    return ER


def wicket_values(f, fmt, ER, rpw):
    """Run value of a wicket for each row: ODI from the resources table, Test = reference runs per wicket."""
    if fmt.key == "test":
        return np.full(len(f), rpw)
    ERp = np.vstack([ER, np.zeros((1, 11))])
    x = np.clip(f["legal_before"].to_numpy() / 6.0, 0, fmt.max_overs - 0.001)
    o = x.astype(int)
    t = x - o
    w = np.clip(f["wkts_before"].to_numpy(), 0, 9).astype(int)
    return (ERp[o, w] * (1 - t) + ERp[o + 1, w] * t) - (ERp[o, w + 1] * (1 - t) + ERp[o + 1, w + 1] * t)


# %% main: ratings


def reference_rows(f, fmt, n=REF_ROWS, seed=0):
    fm = set(FULL_MEMBERS)
    r = f[(f["date"] >= fmt.ref_since) & f["bat_team"].astype(str).isin(fm) & f["bowl_team"].astype(str).isin(fm)]
    if len(r) > n:
        r = r.sample(n=n, random_state=seed)
    return r.sort_values(["date", "match_id", "inn", "over", "legal_before"]).reset_index(drop=True)


def pool_players(f, fmt, M):
    rec = f[f["date"] >= fmt.pool_since]
    ids = set(rec["batter"]) | set(rec["bowler"]) | set(rec["non_striker"])
    return sorted(p for p in ids if p in M.pos["bat"] or p in M.pos["bowl"])


def main(key):
    fmt = FORMATS[key]
    M = Model(key)
    f = load(key)
    styles = pd.read_parquet(fmt.proc / "styles.parquet")
    names, _ = load_people()
    proj_date = (pd.Timestamp(M.m["ref_date"]) + pd.Timedelta(days=90)).date()
    BAT, BOWL, pri_b, pri_w = folded_players(M, f, styles, proj_date)
    ex, exs = extras_dists(f, fmt.ref_since)
    ref = reference_rows(f, fmt)
    R = Ref(M, ref, BAT, BOWL)
    P_act = softmax(R.eta)
    rpw = float(total_row(P_act, exs).sum() / (P_act[:, C["wicket"]] + P_act[:, C["runout"]]).sum())
    ER = resources_table(f[f["bat_team"].astype(str).isin(FULL_MEMBERS)], fmt, fmt.ref_since) if key == "odi" else None
    wv = wicket_values(ref, fmt, ER, rpw)
    ph = R.ph
    ph_count = np.bincount(ph, minlength=3).astype(float)
    strata_bat = {"all": None, "p0": ph == 0, "p1": ph == 1, "p2": ph == 2, "pace": ~R.spin, "spin": R.spin,
                  "home": ~R.bat_away, "away": R.bat_away}
    strata_bowl = {"all": None, "p0": ph == 0, "p1": ph == 1, "p2": ph == 2, "rhb": ~R.lhb, "lhb": R.lhb,
                   "home": ~R.bowl_away, "away": R.bowl_away}
    age = (f["date"].max() - f["date"]).dt.days.to_numpy() / 365.25
    fw = f.assign(wt=0.5 ** (age / M.m["half_life"]))
    mix_bat = fw.groupby(["batter", "phase"], observed=True)["wt"].sum().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0)
    mix_bowl = fw[fw["legal"]].groupby(["bowler", "phase"], observed=True)["wt"].sum().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0)
    role_mix = ref.groupby(["role_bat_row", "phase"]).size().unstack(fill_value=0).reindex(index=range(5), columns=[0, 1, 2], fill_value=1)

    def row_weights(mix, mask):
        mix = np.asarray(mix, float)
        mix = mix / mix.sum() if mix.sum() > 0 else ph_count / ph_count.sum()
        w = mix[ph] / np.maximum(ph_count[ph], 1)
        return w if mask is None else w * mask

    pool = pool_players(f, fmt, M)
    rng = np.random.default_rng(0)
    sub_rows = np.sort(rng.choice(len(ref), size=min(4000, len(ref)), replace=False))
    BK = ("sr", "out_pct", "avg", "bnd_pct", "six_pct", "dot_pct", "rv100")
    WK = ("econ", "wkt_pct", "sr", "avg", "dot_pct", "bnd_pct", "rv_over")
    # group sums: every stratum x phase is one column of Z, so a player's stats in every split come from one
    # sparse product Z' [P, run value] instead of a pass over the rows per split
    import scipy.sparse as sp

    def groups(strata):
        names, cols = [], []
        for s, mask in strata.items():
            for p in range(3):
                names.append((s, p))
                cols.append(((ph == p) if mask is None else (mask & (ph == p))).astype(np.float64))
        Z = sp.csr_matrix(np.column_stack(cols))
        return names, Z.T.tocsr(), np.asarray(Z.sum(axis=0)).ravel()

    gb = {"all": None, "pace": ~R.spin, "spin": R.spin, "home": ~R.bat_away, "away": R.bat_away}
    gb.update({"t_" + t: R.ti == k for k, t in enumerate(TYPES6) if (R.ti == k).sum() >= 300})
    gw = {"all": None, "rhb": ~R.lhb, "lhb": R.lhb, "home": ~R.bowl_away, "away": R.bowl_away}
    nb_, Zb, cb_ = groups(gb)
    nw_, Zw, cw_ = groups(gw)

    def ext_bat(P):
        return np.column_stack([P, bat_runs_row(P, exs) - bat_outs_row(P, exs) * wv])

    def ext_bowl(P):
        return np.column_stack([P, conceded_row(P, exs) - P[:, C["wicket"]] * wv])

    def bat_from(m):
        faced = 1 - m[C["wide"]]
        runs, outs = bat_runs_row(m, exs), bat_outs_row(m, exs)
        return {"sr": 100 * runs / faced, "out_pct": 100 * outs / faced, "avg": runs / outs,
                "bnd_pct": 100 * (m[C["r4"]] + m[C["r6"]]) / faced, "six_pct": 100 * m[C["r6"]] / faced,
                "dot_pct": 100 * (m[C["r0"]] + m[C["wicket"]] + m[C["byes"]]) / faced, "rv100": 100 * m[K] / faced}

    def bowl_from(m):
        legal = 1 - m[C["wide"]] - m[C["noball"]]
        conc, wk_ = conceded_row(m, exs), m[C["wicket"]]
        return {"econ": 6 * conc / legal, "wkt_pct": 100 * wk_ / legal, "sr": legal / wk_, "avg": conc / wk_,
                "dot_pct": 100 * (m[C["r0"]] + m[C["wicket"]] + m[C["byes"]]) / legal,
                "bnd_pct": 100 * (m[C["r4"]] + m[C["r6"]]) / legal, "rv_over": 6 * m[K] / legal}

    def split_stats(G, cnt, names, mix, conv, own_mix, keys, rec, infix=""):
        """G: groups x 12 sums. Splits in own_mix are weighted to the player's phase mix; phases use every row."""
        mix = np.asarray(mix, float)
        mix = mix / mix.sum() if mix.sum() > 0 else ph_count / ph_count.sum()
        wph = mix / np.maximum(ph_count, 1)
        ix = {nm: k for k, nm in enumerate(names)}
        for s in own_mix:
            if (s, 0) not in ix:
                continue
            g = [ix[(s, p)] for p in range(3)]
            wsum = float(np.sum(wph * cnt[g]))
            if wsum <= 0:
                continue
            st = conv((wph[:, None] * G[g]).sum(0) / wsum)
            for k in keys:
                rec[f"{s}_{infix}{k}"] = float(st[k])
        for p in range(3):
            st = conv(G[ix[("all", p)]] / max(cnt[ix[("all", p)]], 1))
            for k in keys:
                rec[f"p{p}_{infix}{k}"] = float(st[k])

    Gb_act, Gw_act = np.asarray(Zb @ ext_bat(P_act)), np.asarray(Zw @ ext_bowl(P_act))
    own_b = ["all", "pace", "spin", "home", "away"] + ["t_" + t for t in TYPES6]
    own_w = ["all", "rhb", "lhb", "home", "away"]
    rows_b, rows_w = [], []
    free = (np.arange(K) != REF)
    for pid in pool:
        if pid in M.pos["bat"]:
            i = M.pos["bat"][pid]
            v = {k: BAT[k][i] for k in ("b", "pp", "de", "sp", "ea", "aw", "ty")}
            lh, tail = bool(BAT["lhb"][i]), bool(BAT["role"][i] >= 3)
            P = softmax(R.with_batter(v, lh, tail))
            mix = mix_bat.loc[pid].to_numpy() if pid in mix_bat.index else role_mix.loc[BAT["role"][i]].to_numpy()
            rec = {"id": pid}
            split_stats(np.asarray(Zb @ ext_bat(P)), cb_, nb_, mix, bat_from, own_b, BK, rec)
            split_stats(Gb_act, cb_, nb_, mix, bat_from, own_b, BK, rec, infix="avg_")
            nd = 16   # posterior draws of the player's own coefficients
            dr = [dict(v, **{k: v[k] + rng.standard_normal(K) * BAT["sd_" + k][i] * BAT["inact"][i] * free
                             for k in ("b", "pp", "de", "sp", "ea", "aw")}) for _ in range(nd)]
            Pd = softmax(np.stack([R.with_batter(d, lh, tail, sub_rows) for d in dr]))
            sd = bat_stats(Pd, row_weights(mix, None)[sub_rows], exs, wv[sub_rows])
            rec.update({"sd_" + k: float(np.std(sd[k])) for k in ("sr", "avg", "out_pct", "rv100")})
            rows_b.append(rec)
        if pid in M.pos["bowl"]:
            j = M.pos["bowl"][pid]
            v = {k: BOWL[k][j] for k in ("b", "pp", "de", "lh", "aw")}
            sub, spin = int(BOWL["sub"][j]), bool(BOWL["spin"][j])
            P = softmax(R.with_bowler(v, sub, spin))
            mix = mix_bowl.loc[pid].to_numpy() if pid in mix_bowl.index else ph_count
            rec = {"id": pid}
            split_stats(np.asarray(Zw @ ext_bowl(P)), cw_, nw_, mix, bowl_from, own_w, WK, rec)
            split_stats(Gw_act, cw_, nw_, mix, bowl_from, own_w, WK, rec, infix="avg_")
            dr = [{k: v[k] + rng.standard_normal(K) * BOWL["sd_" + k][j] * BOWL["inact"][j] * free for k in v} for _ in range(16)]
            Pd = softmax(np.stack([R.with_bowler(d, sub, spin, sub_rows) for d in dr]))
            sd = bowl_stats(Pd, row_weights(mix, None)[sub_rows], exs, wv[sub_rows])
            rec.update({"sd_" + k: float(np.std(sd[k])) for k in ("econ", "avg", "wkt_pct", "rv_over")})
            rows_w.append(rec)
    bat_df, bowl_df = pd.DataFrame(rows_b).set_index("id"), pd.DataFrame(rows_w).set_index("id")
    avg_bat = {s: {k: float(v) for k, v in bat_stats(P_act, np.ones(len(ref)) if m is None else m.astype(float), exs, wv).items()}
               for s, m in strata_bat.items()}
    avg_bowl = {s: {k: float(v) for k, v in bowl_stats(P_act, np.ones(len(ref)) if m is None else m.astype(float), exs, wv).items()}
                for s, m in strata_bowl.items()}
    venues = venue_table(M, R, exs)
    shock = estimate_shock(M, f, exs)
    out = dict(bat=bat_df, bowl=bowl_df, avg_bat=avg_bat, avg_bowl=avg_bowl, venues=venues, shock=shock, ex=ex, exs=exs,
               pool=pool, names=names, ER=ER, rpw=rpw, mix_bat=mix_bat, mix_bowl=mix_bowl, proj_date=str(proj_date),
               BAT_cov=BAT["cov"], BOWL_cov=BOWL["cov"], bat_inact=pd.Series(BAT["inact"], index=M.idx["bat"]),
               bowl_inact=pd.Series(BOWL["inact"], index=M.idx["bowl"]))
    with open(fmt.proc / "ratings.pkl", "wb") as fh:
        pickle.dump(out, fh)
    write_sim_params(M, f, BAT, BOWL, pri_b, pri_w, ex, pool, venues, shock, styles)
    print(f"{key}: ratings pool={len(pool)} batters={len(bat_df)} bowlers={len(bowl_df)} venues={len(venues)} "
          f"runs/wicket ref={rpw:.1f} shock={shock['summary']}")


# %% venues


def venue_table(M, R, exs):
    """Each ground's scoring and wicket rates on the reference deliveries (its country's projection environment
    plus its own terms) against the average full-member environment."""
    fmt = M.fmt
    mm = pd.read_parquet(fmt.proc / "matches.parquet")
    cnt = mm.groupby("venue").agg(matches=("match_id", "size"), last=("date", "max"), country=("country", "first"),
                                  name=("venue_raw", lambda s: s.value_counts().index[0]),
                                  city=("city", lambda s: s.value_counts().index[0] if (s != "").any() else ""))
    rec = mm[mm["date"] >= "2019-01-01"].groupby("venue").size()
    VB, VL, VS = M.blk("venue"), M.blk("venue_late"), M.blk("venue_spin")
    ph, spin, late = R.ph, R.spin, R.late
    base = R.eta_noenv

    def env_eta(country, vi=None):
        e = M.env(country)
        gs_part = M.env("__none__")  # global-year part is already in eta_noenv
        allv = e["all"] - gs_part["all"]
        sp = e["spin"] - gs_part["spin"]
        p0, p2 = e["ph"][0] - gs_part["ph"][0], e["ph"][2] - gs_part["ph"][2]
        eta = base + allv + spin[:, None] * sp + (ph == 0)[:, None] * p0 + (ph == 2)[:, None] * p2
        if vi is not None:
            eta = eta + VB[vi] + late[:, None] * VL[vi] + spin[:, None] * VS[vi]
        return eta

    def summ(P, mask):
        m = P[mask].mean(0)
        legal = 1 - m[C["wide"]] - m[C["noball"]]
        wk = m[C["wicket"]] + m[C["runout"]]
        return dict(rpo=6 * total_row(m, exs) / legal, wpo=6 * wk / legal, rpw=total_row(m, exs) / wk,
                    spo=6 * m[C["r6"]] / legal)

    masks = {"all": np.ones(len(ph), bool), "pace": ~spin, "spin": spin, "early": ~late, "late": late}
    # neutral reference: reference rows as they were (the mix of grounds full members actually played on)
    Pn = softmax(R.eta)
    neutral = {k: summ(Pn, m) for k, m in masks.items()}
    rows = []
    for v, vi in M.pos["venues"].items():
        if v not in cnt.index or cnt.loc[v, "matches"] < 2 or cnt.loc[v, "last"] < pd.Timestamp("2015-01-01"):
            continue
        c = cnt.loc[v, "country"]
        P = softmax(env_eta(c, vi))
        r = dict(venue=v, name=cnt.loc[v, "name"], city=cnt.loc[v, "city"], country=c, matches=int(cnt.loc[v, "matches"]),
                 matches_since_2019=int(rec.get(v, 0)), last_match=str(cnt.loc[v, "last"].date()))
        for k, m in masks.items():
            s = summ(P, m)
            for q, val in s.items():
                r[f"{k}_{q}"] = float(val)
                r[f"{k}_{q}_mult"] = float(val / neutral[k][q])
        rows.append(r)
    df = pd.DataFrame(rows)
    crow = []
    for c in M.idx["comps"]:
        P = softmax(env_eta(c))
        r = dict(country=c, season=M.latest_season(c))
        for k, m in masks.items():
            s = summ(P, m)
            for q, val in s.items():
                r[f"{k}_{q}"] = float(val)
                r[f"{k}_{q}_mult"] = float(val / neutral[k][q])
        crow.append(r)
    df.attrs["neutral"] = neutral
    df.attrs["countries"] = crow
    return df


# %% match and innings shocks (conditions the per-ball model cannot see)


def shock_rows(M, f):
    """Deliveries and logits for the shock estimate. Out-of-sample where a walk-forward holdout exists (the
    fitted season and ground terms absorb part of a match's conditions in-sample, which would understate the
    match-level spread); otherwise recent in-sample deliveries."""
    fmt = M.fmt
    hp = fmt.proc / "holdout_eta.npz"
    if hp.exists():
        z = np.load(hp, allow_pickle=True)
        rows = f.iloc[z["row"]].reset_index(drop=True)
        return rows, np.insert(z["eta"], REF, 0.0, axis=1), "walk-forward holdout"
    r = f[f["date"] >= "2019-01-01"].reset_index(drop=True)
    D, X = build_design(r, M.idx, fmt, M.lam)
    return r, np.asarray(X @ M.W), "in-sample since 2019"


def estimate_shock(M, f, exs):
    """Both sides of a match share a pitch and weather the model cannot see. Two shock axes on the logits: a
    scoring axis (every scoring shot against the dot ball) and a wicket axis (the bowler-wicket class). Their
    match-level covariance is solved from the cross-team covariance of innings residuals (runs and wickets per
    ball, actual minus expected); the innings-level part is what is left of the within-innings variance after
    sampling noise and the shared part."""
    fmt = M.fmt
    r, eta, source = shock_rows(M, f)
    fm = (r["bat_team"].astype(str).isin(FULL_MEMBERS) & r["bowl_team"].astype(str).isin(FULL_MEMBERS)).to_numpy()
    r, eta = r[fm].reset_index(drop=True), eta[fm]
    P = softmax(eta)
    xr = total_row(P, exs)
    xw = P[:, C["wicket"]] + P[:, C["runout"]]
    rv = np.array([exs["wide_mean"], 1 + exs["nb_bat_mean"], exs["bye_mean"], 0, exs["ro_runs_mean"], 0, 1, 2, 3, 4, 6])
    var_r = (P * rv ** 2).sum(1) - xr ** 2
    var_w = xw * (1 - xw)
    cov_rw = -xr * xw + P[:, C["runout"]] * exs["ro_runs_mean"]
    d = pd.DataFrame({"m": r["match_id"], "i": r["inn"], "t": r["bat_team"].astype(str), "n": 1.0, "ar": r["runs_total"].astype(float),
                      "aw": r["cls"].astype(str).isin(["wicket", "runout"]).astype(float), "xr": xr, "xw": xw,
                      "vr": var_r, "vw": var_w, "vrw": cov_rw})
    g = d.groupby(["m", "i", "t"]).sum().reset_index()
    g = g[g["n"] >= 120]
    g["er"], g["ew"] = (g["ar"] - g["xr"]) / g["n"], (g["aw"] - g["xw"]) / g["n"]
    pairs = g.merge(g, on="m", suffixes=("_a", "_b"))
    pairs = pairs[(pairs["i_a"] < pairs["i_b"]) & (pairs["t_a"] != pairs["t_b"])]
    Cm = np.array([[np.mean(pairs["er_a"] * pairs["er_b"]), np.mean(pairs["er_a"] * pairs["ew_b"] + pairs["ew_a"] * pairs["er_b"]) / 2],
                   [0, np.mean(pairs["ew_a"] * pairs["ew_b"])]])
    Cm[1, 0] = Cm[0, 1]
    Ct = np.cov(np.vstack([g["er"], g["ew"]]))
    noise = np.array([[np.mean(g["vr"] / g["n"] ** 2), np.mean(g["vrw"] / g["n"] ** 2)], [0, np.mean(g["vw"] / g["n"] ** 2)]])
    noise[1, 0] = noise[0, 1]
    Ci = Ct - noise - Cm
    # shock axes
    dir_r = np.zeros(K)
    dir_r[[C["r1"], C["r2"], C["r3"], C["r4"], C["r6"]]] = 1.0
    dir_w = np.zeros(K)
    dir_w[C["wicket"]] = 1.0
    h = 0.05
    G = np.zeros((2, 2))   # d(runs, wickets per ball) / d(z_r, z_w)
    for k, dv in enumerate((dir_r, dir_w)):
        Ph = softmax(eta + h * dv)
        G[0, k] = np.mean(total_row(Ph, exs) - xr) / h
        G[1, k] = np.mean(Ph[:, C["wicket"]] + Ph[:, C["runout"]] - xw) / h
    Gi = np.linalg.inv(G)

    def to_z(Cx):
        S = Gi @ Cx @ Gi.T
        S = (S + S.T) / 2
        val, vec = np.linalg.eigh(S)
        S = (vec * np.clip(val, 0, None)) @ vec.T
        L = np.linalg.cholesky(S + 1e-9 * np.eye(2))
        return S, L

    Sm, Lm = to_z(Cm)
    Si, Li = to_z(Ci)
    summary = {"match_sd_r": round(float(np.sqrt(Sm[0, 0])), 3), "match_sd_w": round(float(np.sqrt(Sm[1, 1])), 3),
               "inn_sd_r": round(float(np.sqrt(Si[0, 0])), 3), "inn_sd_w": round(float(np.sqrt(Si[1, 1])), 3)}
    # chase residual (ODI): second minus first innings scoring residual, noise removed -> size of the dew dial
    chase_sd = 0.0
    if fmt.key == "odi":
        w = g.pivot_table(index="m", columns="i", values="er").dropna()
        nz = g.assign(v=g["vr"] / g["n"] ** 2).pivot_table(index="m", columns="i", values="v").reindex(w.index)
        dvar = float(np.var(w[2] - w[1], ddof=1) - nz[1].mean() - nz[2].mean())
        chase_sd = float(np.sqrt(max(dvar, 0.0)) / G[0, 0])
    return {"dir_r": dir_r, "dir_w": dir_w, "L_match": Lm, "L_inn": Li, "S_match": Sm, "S_inn": Si, "G": G,
            "C_match": Cm, "C_total": Ct, "C_noise": noise, "n_innings": int(len(g)), "n_pairs": int(len(pairs)),
            "chase_sd": chase_sd, "summary": summary, "source": source}


def build_conditions(M, venues, shock):
    """User dials as logit shifts sized from the data: pitch options move along the shock axes by one match
    standard deviation, or by the gap between the most pace- / spin-friendly fifth of grounds and the average."""
    fmt = M.fmt
    v = venues[venues["matches_since_2019"] >= 4].copy()
    v["i"] = v["venue"].map(M.pos["venues"])
    VB, VS = M.blk("venue"), M.blk("venue_spin")

    def gap(block, col):
        sel = v[v[col] >= v[col].quantile(0.8)]
        return block[sel["i"].to_numpy()].mean(0) - block[v["i"].to_numpy()].mean(0)

    sr, sw = float(np.sqrt(shock["S_match"][0, 0])), float(np.sqrt(shock["S_match"][1, 1]))
    dr, dw = shock["dir_r"], shock["dir_w"]
    cond = {"pitch": {
        "normal": {},
        "flat": {"all": r3(sr * dr - sw * dw)},
        "green": {"all": r3(-0.5 * sr * dr), "pace": r3(gap(VB, "pace_wpo_mult") + 0.5 * sw * dw)},
        "turning": {"all": r3(-0.5 * sr * dr), "spin": r3(gap(VS, "spin_wpo_mult") + sw * dw)},
        "tough": {"all": r3(-sr * dr + sw * dw)},
    }}
    if fmt.key == "odi":
        cs = 1.2816 * shock["chase_sd"]
        cond["dew"] = {"normal": {}, "heavy": {"i2": r3(cs * dr)}, "none": {"i2": r3(-cs * dr)}}
    return cond


# %% sim params export


def write_sim_params(M, f, BAT, BOWL, pri_b, pri_w, ex, pool, venues, shock, styles):
    fmt = M.fmt
    key = fmt.key
    ni, nb = fmt.n_inn, fmt.n_ovb
    io, cell, ipw = M.blk("io"), M.blk("cell"), M.blk("ipw")
    base = (io[:, None, :] + cell.reshape(ni * nb, 10, K)).reshape(ni, nb, 10, K)
    z = [0.0] * K
    sub_ph = M.blk("sub_ph")
    env = {}
    for c in M.idx["comps"]:
        e = M.env(c)
        env[c] = {"all": r3(e["all"]), "spin": r3(e["spin"]), "ph": [r3(e["ph"][0]), z, r3(e["ph"][2])], "season": e["season"]}
    # default (neutral ground, or a host the model has no ground in): the full-member host environments averaged
    # by how many matches each has staged since the reference date, i.e. where the format is actually played
    mm = pd.read_parquet(fmt.proc / "matches.parquet")
    hosted = mm[mm["date"] >= fmt.ref_since].groupby("country").size()
    fmc = [c for c in M.idx["comps"] if c in FULL_MEMBERS and hosted.get(c, 0) > 0]
    wts = np.array([hosted[c] for c in fmc], float)
    wts /= wts.sum()
    avg = lambda get: r3(np.sum([w * np.asarray(get(env[c])) for w, c in zip(wts, fmc)], axis=0))
    env["_default"] = {"all": avg(lambda e: e["all"]), "spin": avg(lambda e: e["spin"]),
                       "ph": [avg(lambda e: e["ph"][0]), z, avg(lambda e: e["ph"][2])], "season": None}
    bats, bowls = {}, {}
    for pid in pool:
        if pid in M.pos["bat"]:
            i = M.pos["bat"][pid]
            d = {"b": r3(BAT["b"][i]), "pp": r3(BAT["pp"][i]), "de": r3(BAT["de"][i]), "sp": r3(BAT["sp"][i]),
                 "ea": r3(BAT["ea"][i]), "aw": r3(BAT["aw"][i]), "hand": "L" if BAT["lhb"][i] else "R",
                 "tl": int(BAT["role"][i] >= 3)}
            ty = {t: r3(BAT["ty"][i, k]) for k, t in enumerate(TYPES6) if np.abs(BAT["ty"][i, k]).max() >= 0.01}
            if ty:
                d["ty"] = ty
            bats[pid] = d
        if pid in M.pos["bowl"]:
            j = M.pos["bowl"][pid]
            bowls[pid] = {"b": r3(BOWL["b"][j]), "pp": r3(BOWL["pp"][j]), "de": r3(BOWL["de"][j]), "lh": r3(BOWL["lh"][j]),
                          "aw": r3(BOWL["aw"][j]), "sub": SUBTYPES[int(BOWL["sub"][j])], "spin": int(bool(BOWL["spin"][j]))}
    VB, VL, VS = M.blk("venue"), M.blk("venue_late"), M.blk("venue_spin")
    ven = {}
    for _, r in venues.iterrows():
        i = M.pos["venues"][r["venue"]]
        ven[r["venue"]] = {"base": r3(VB[i]), "late": r3(VL[i]), "spin": r3(VS[i]), "country": r["country"]}
    ha = M.blk("ha")
    params = {
        "version": 1, "fmt": key, "classes": CLASSES, "ref_class": REF, "n_inn": ni, "max_overs": fmt.max_overs,
        "max_bowler_overs": fmt.max_bowler_overs, "over_edges": list(fmt.over_edges), "n_ovb": nb,
        "base": r3(base.ravel()), "ipw": r3(ipw.ravel()),
        "bf": r3(M.blk("bf").ravel()), "bf_edges": list(fmt.bf_edges), "bf_labels": list(fmt.bf_labels), "early_bf": fmt.early_bf,
        "sub": {s: r3(M.blk("sub")[i]) for i, s in enumerate(SUBTYPES)},
        "sub_lhb": {s: r3(M.blk("sub_lhb")[i]) for i, s in enumerate(SUBTYPES)},
        "sub_phase": {s: [r3(sub_ph[i * 3]), z, r3(sub_ph[i * 3 + 2])] for i, s in enumerate(SUBTYPES)},
        "ha": {"bat_home": r3(ha[0]), "bowl_home": r3(ha[1]), "bat_home_spin": r3(ha[2]), "bowl_home_spin": r3(ha[3])},
        "env": env, "venues": ven, "venue_neutral": {"base": z, "late": z, "spin": z, "country": None},
        "batters": bats, "bowlers": bowls,
        "batter_priors": {r: r3(v) for r, v in pri_b.items()}, "bowler_priors": {r: r3(v) for r, v in pri_w.items()},
        "team_prior": {t: {"bat": r3(M.blk("bat_team")[i]), "bowl": r3(M.blk("bowl_team")[i])} for t, i in M.pos["teams"].items()},
        "extras": ex,
        "shock": {"dir_r": r3(shock["dir_r"], 4), "dir_w": r3(shock["dir_w"], 4), "L_match": r3(shock["L_match"], 4),
                  "L_inn": r3(shock["L_inn"], 4)},
        "conditions": build_conditions(M, venues, shock),
    }
    if key == "odi":
        nr = len(RRR_EDGES) - 1
        params.update({"chase": r3(M.blk("chase").ravel()), "rrr_edges": RRR_EDGES[1:-1], "rrr_labels": RRR_LABELS, "n_rrr": nr,
                       "chase_w": r3(M.blk("chase_w").ravel()) if M.blk("chase_w") is not None else None})
    else:
        side = json.loads((fmt.proc / "prep.json").read_text())
        from models.intl import flow
        params.update({
            "mo": r3(M.blk("mo").ravel()), "mo_spin": r3(M.blk("mo_spin").ravel()), "mo_edges": MO_EDGES,
            "pos12": r3(M.blk("pos12").ravel()), "score1_edges": SCORE1_EDGES[1:-1], "lead2_edges": LEAD2_EDGES[1:-1],
            "lead3": r3(M.blk("lead3").ravel()), "lead3_edges": LEAD3_EDGES[1:-1],
            "need4": r3(M.blk("need4").ravel()), "need4_edges": NEED4_EDGES[1:-1],
            "rr4": r3(M.blk("rr4").ravel()), "rr4_edges": RR4_EDGES[1:-1], "rem4_edges": REM4_EDGES[1:-1],
            "spell": r3(M.blk("spell").ravel()), "spell_edges": SPELL_EDGES, "tail": r3(M.blk("tail").ravel()),
            "avail_q": side["avail_q"], "flow": flow.fit(key),
        })
    (fmt.export / "sim_params.json").write_text(json.dumps(params, separators=(",", ":")))
    return params


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        main(k)
