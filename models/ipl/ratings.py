"""Turn the fitted logit model into (a) sim_params tables and (b) context-adjusted player/venue/league metrics."""
# %% imports
import json
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import CLASSES, COMP_NAMES, EXPORT, K, PEOPLE, PROC, PROJ_DATE, REF, TIERS
from models.ipl.fit import TYPES6, build_design, predict_eta, probs_from_eta
from models.ipl.prep import AGE_LABELS, BF_EDGES, BF_LABELS, EARLY_BF, RRR_EDGES, RRR_LABELS, SUBTYPES, age_bucket

C = {c: i for i, c in enumerate(CLASSES)}
ROLES_BAT = ["open", "top", "middle", "lower"]
ROLES_BOWL = ["pace_part", "pace_reg", "pace_front", "spin_part", "spin_reg", "spin_front"]
POOL_SINCE = pd.Timestamp("2024-01-01")
POOL_MIN_BALLS = 150
IPL_RECENT = ("2024", "2025", "2026")


# %% model access


class Model:
    def __init__(self, path=None):
        with open(path or (PROC / "model.pkl"), "rb") as fh:
            m = pickle.load(fh)
        self.m = m
        self.W = np.insert(m["W"], REF, 0.0, axis=1)        # p x 11
        self.SD = np.insert(m["sd"], REF, 0.0, axis=1)
        self.blocks = m["blocks"]
        self.idx = m["idx"]
        self.players_bat, self.players_bowl, self.venues, self.comps, self.comp_seasons = self.idx
        self.bat_pos = {p: i for i, p in enumerate(self.players_bat)}
        self.bowl_pos = {p: i for i, p in enumerate(self.players_bowl)}
        self.venue_pos = {v: i for i, v in enumerate(self.venues)}

    def blk(self, name, sd=False):
        o, labels, _ = self.blocks[name]
        return (self.SD if sd else self.W)[o:o + len(labels)]

    def base_table(self):
        io, ipw, cell = self.blk("io"), self.blk("ipw"), self.blk("cell")
        T = np.zeros((2, 20, 8, K))
        for i in range(2):
            for o in range(20):
                ph = 0 if o < 6 else (1 if o < 15 else 2)
                for w in range(8):
                    T[i, o, w] = io[i * 20 + o] + ipw[i * 24 + ph * 8 + w] + cell[i * 160 + o * 8 + w]
        return T


def load_people():
    p = pd.read_csv(PEOPLE, dtype=str)
    return p.set_index("identifier")["name"].to_dict()


# %% folded player vectors


INACTIVE_GRACE, INACTIVE_TAU = 1.0, 2.0  # years: deviations decay as exp(-(gap - grace)/tau) after a top-league gap


def last_top_league(f):
    top = f[f["tier"].astype(str).isin(["ipl", "intl", "top_fr", "fr2"])]
    return pd.concat([top.groupby("batter")["date"].max(), top.groupby("bowler")["date"].max()]).groupby(level=0).max()


def folded_players(M, cov, styles, last_top=None, ref_date=None, proj_date=PROJ_DATE):
    """Batter / bowler logit vectors for projection: individual deviation (decayed after long top-league
    inactivity) + hierarchical prior mean (role, league mix, current experience) + age term at the projection
    date. Also returns per-player pieces needed to rebuild the *row-specific* terms of real deliveries."""
    bat_role, bat_tier = M.blk("bat_role"), M.blk("bat_tier")
    bowl_role, bowl_tier = M.blk("bowl_role"), M.blk("bowl_tier")
    na = len(AGE_LABELS)
    has_age = "bat_age" in M.blocks
    pdate = pd.Timestamp(proj_date)
    ref_date = pd.Timestamp(ref_date) if ref_date is not None else pd.Timestamp(M.m["ref_date"])
    def inact(ids):
        if last_top is None:
            return np.ones(len(ids))
        gap = (ref_date - last_top.reindex(ids)).dt.days.to_numpy() / 365.25
        gap = np.nan_to_num(gap, nan=10.0)
        return np.exp(-np.clip(gap - INACTIVE_GRACE, 0, None) / INACTIVE_TAU)
    cb = cov.reindex(M.players_bat)
    rb = cb["role_bat"].map({r: i for i, r in enumerate(ROLES_BAT)}).fillna(3).astype(int).to_numpy()
    tb = cb[["bat_tier_" + t for t in TIERS]].fillna(0).to_numpy()
    eb = cb["exp_bat"].fillna(0).astype(int).to_numpy()
    ne = len(M.blocks["bat_exp"][1]) // len(ROLES_BAT)
    exp_b = M.blk("bat_exp")[rb * ne + eb]
    base_prior_b = bat_role[rb] + tb[:, 1:] @ bat_tier[1:]
    dob_b = cb["dob"] if "dob" in cb else pd.Series(pd.NaT, index=cb.index)
    age_b = age_bucket(((pdate - pd.to_datetime(dob_b)).dt.days / 365.25).to_numpy())
    age_proj_b = M.blk("bat_age")[age_b] if has_age else np.zeros((len(rb), K))
    fb = inact(M.players_bat)[:, None]
    prior_b = base_prior_b + exp_b + age_proj_b
    BAT = {"b": M.blk("bat") * fb + prior_b, "pp": M.blk("bat_pp") * fb, "de": M.blk("bat_death") * fb,
           "sp": M.blk("bat_spin") * fb, "ea": M.blk("bat_early") * fb, "prior": prior_b, "inactive_factor": fb[:, 0],
           "role_i": rb, "exp_cur": exp_b, "age_proj": age_proj_b, "age_bucket_proj": age_b,
           "sd_b": M.blk("bat", True), "sd_pp": M.blk("bat_pp", True), "sd_de": M.blk("bat_death", True),
           "sd_sp": M.blk("bat_spin", True), "sd_ea": M.blk("bat_early", True)}
    cw = cov.reindex(M.players_bowl)
    rw = cw["role_bowl"].map({r: i for i, r in enumerate(ROLES_BOWL)}).fillna(0).astype(int).to_numpy()
    tw = cw[["bowl_tier_" + t for t in TIERS]].fillna(0).to_numpy()
    ew = cw["exp_bowl"].fillna(0).astype(int).to_numpy()
    exp_w = M.blk("bowl_exp")[rw * ne + ew]
    st = styles.reindex(M.players_bowl)
    spin = st["bowl_group"].eq("spin").to_numpy()
    dob_w = cw["dob"] if "dob" in cw else pd.Series(pd.NaT, index=cw.index)
    age_w = age_bucket(((pdate - pd.to_datetime(dob_w)).dt.days / 365.25).to_numpy())
    age_proj_w = M.blk("bowl_age")[spin.astype(int) * na + age_w] if has_age else np.zeros((len(rw), K))
    fw = inact(M.players_bowl)[:, None]
    prior_w = bowl_role[rw] + tw[:, 1:] @ bowl_tier[1:] + exp_w + age_proj_w
    BOWL = {"b": M.blk("bowl") * fw + prior_w, "pp": M.blk("bowl_pp") * fw, "de": M.blk("bowl_death") * fw,
            "lh": M.blk("bowl_lhb") * fw, "prior": prior_w, "inactive_factor": fw[:, 0],
            "role_i": rw, "exp_cur": exp_w, "age_proj": age_proj_w, "age_bucket_proj": age_w,
            "sd_b": M.blk("bowl", True), "sd_pp": M.blk("bowl_pp", True), "sd_de": M.blk("bowl_death", True),
            "sd_lh": M.blk("bowl_lhb", True)}
    BOWL["sub"] = st["bowl_subtype"].fillna("pace_U").map({s: i for i, s in enumerate(SUBTYPES)}).to_numpy()
    BOWL["spin"] = spin
    BAT["lhb"] = styles.reindex(M.players_bat)["bat_hand"].eq("L").to_numpy()
    nb_ = len(M.players_bat)
    BAT["ty_raw"] = M.blk("bat_type").reshape(nb_, len(TYPES6), K) if "bat_type" in M.blocks else np.zeros((nb_, len(TYPES6), K))
    BAT["ty"] = BAT["ty_raw"] * fb[:, :, None]
    # priors for players the model has never seen: role mean, IPL tier, least-experienced bucket, unknown age
    au = na - 1
    ab = M.blk("bat_age")[au] if has_age else 0
    priors_bat = {r: bat_role[i] + M.blk("bat_exp")[i * ne] + ab for i, r in enumerate(ROLES_BAT)}
    priors_bowl = {r: bowl_role[i] + M.blk("bowl_exp")[i * ne]
                      + (M.blk("bowl_age")[int(r.startswith("spin")) * na + au] if has_age else 0)
                   for i, r in enumerate(ROLES_BOWL)}
    return BAT, BOWL, priors_bat, priors_bowl


# %% reference sample and term substitution


class RefSample:
    """A set of real deliveries whose logits we can re-evaluate with a different batter or bowler."""

    def __init__(self, M, f, cov, BAT, BOWL):
        self.M, self.BAT, self.BOWL = M, BAT, BOWL
        D, X = build_design(f, cov, *M.idx, opts=M.m.get("opts"))
        self.eta = np.insert(predict_eta(X, M.m["W"]), REF, 0.0, axis=1)
        self.f = f
        self.ph = f["phase"].to_numpy()
        self.early = (f["bf_before"].to_numpy() < EARLY_BF)
        self.bi = f["batter"].map(M.bat_pos).fillna(-1).astype(int).to_numpy()
        self.wi = f["bowler"].map(M.bowl_pos).fillna(-1).astype(int).to_numpy()
        self.sub = f["bowl_subtype"].astype(str).map({s: i for i, s in enumerate(SUBTYPES)}).to_numpy()
        self.spin = f["bowl_spin"].to_numpy()
        self.lhb = (f["bat_hand"].astype(str) == "L").to_numpy()
        self.vi = f["venue"].astype(str).map(M.venue_pos).fillna(-1).astype(int).to_numpy()
        self.SUBL = M.blk("sub_lhb")
        self.SUB = M.blk("sub")
        self.SUBPH = np.vstack([M.blk("sub_ph"), np.zeros((1, K))])  # last row = middle overs (reference)
        self.VSP = M.blk("venue_spin")
        self.ti = f["bowl_subtype"].astype(str).map({t: i for i, t in enumerate(TYPES6)}).fillna(-1).astype(int).to_numpy()
        # batter's own bowling-type split on this row (full, undecayed coefficient for the real delivery)
        self.ty_row = np.zeros((len(self.ph), K))
        okt = (self.bi >= 0) & (self.ti >= 0)
        self.ty_row[okt] = BAT["ty_raw"][self.bi[okt], self.ti[okt]]
        # batter x bowler head-to-head on this row
        self.pair_row = np.zeros((len(self.ph), K))
        opts = M.m.get("opts") or {}
        if "pair" in M.blocks and opts.get("pairs") is not None:
            pairs = pd.Index(opts["pairs"])
            pi = pairs.get_indexer((f["batter"].astype(str) + "|" + f["bowler"].astype(str)).to_numpy())
            okp = pi >= 0
            self.pair_row[okp] = M.blk("pair")[pi[okp]]
        self.bterm_actual = (self._bterm_rows(self.bi, self.lhb) + self._row_corr_bat(M, f) + self.ty_row
                             + self.pair_row)
        self.wterm_actual = (self._wterm_rows(self.wi, self.sub, self.spin) + self._row_corr_bowl(M, f) + self.ty_row
                             + self.pair_row)

    def _bterm_rows(self, bi, lhb, B=None):
        """Batter-dependent logit terms for each row (vectorised over rows)."""
        B = B or self.BAT
        z = np.zeros((len(self.ph), K))
        ok = bi >= 0
        b = bi[ok]
        z[ok] = (B["b"][b] + B["pp"][b] * (self.ph[ok] == 0)[:, None] + B["de"][b] * (self.ph[ok] == 2)[:, None]
                 + B["sp"][b] * self.spin[ok][:, None] + B["ea"][b] * self.early[ok][:, None])
        wi = np.maximum(self.wi, 0)
        lterm = self.SUBL[self.sub] + np.where((self.wi >= 0)[:, None], self.BOWL["lh"][wi], 0)
        return z + lhb[:, None] * lterm

    def _row_corr_bat(self, M, f):
        """The fit used experience and age *at the delivery*; projection vectors use current experience,
        projection-date age and inactivity decay. Convert back to the row's own terms."""
        B = self.BAT
        z = np.zeros((len(self.ph), K))
        ok = self.bi >= 0
        b = self.bi[ok]
        ne = len(M.blocks["bat_exp"][1]) // len(ROLES_BAT)
        row_exp = M.blk("bat_exp")[B["role_i"][b] * ne + f["exp_bat_row"].to_numpy()[ok].astype(int)]
        z[ok] = row_exp - B["exp_cur"][b] - B["age_proj"][b]
        if "bat_age" in M.blocks:
            z[ok] += M.blk("bat_age")[f["age_bat_b"].to_numpy()[ok].astype(int)]
        fb = B["inactive_factor"][b][:, None]
        ph, sp, ea = self.ph[ok], self.spin[ok], self.early[ok]
        dev = (M.blk("bat")[b] + M.blk("bat_pp")[b] * (ph == 0)[:, None] + M.blk("bat_death")[b] * (ph == 2)[:, None]
               + M.blk("bat_spin")[b] * sp[:, None] + M.blk("bat_early")[b] * ea[:, None])
        z[ok] += dev * (1 - fb)
        return z

    def _row_corr_bowl(self, M, f):
        W = self.BOWL
        z = np.zeros((len(self.ph), K))
        ok = self.wi >= 0
        w = self.wi[ok]
        ne = len(M.blocks["bowl_exp"][1]) // len(ROLES_BOWL)
        row_exp = M.blk("bowl_exp")[W["role_i"][w] * ne + f["exp_bowl_row"].to_numpy()[ok].astype(int)]
        z[ok] = row_exp - W["exp_cur"][w] - W["age_proj"][w]
        if "bowl_age" in M.blocks:
            na = len(AGE_LABELS)
            z[ok] += M.blk("bowl_age")[self.spin[ok].astype(int) * na + f["age_bowl_b"].to_numpy()[ok].astype(int)]
        fw = W["inactive_factor"][w][:, None]
        ph, lhb = self.ph[ok], self.lhb[ok]
        dev = (M.blk("bowl")[w] + M.blk("bowl_pp")[w] * (ph == 0)[:, None] + M.blk("bowl_death")[w] * (ph == 2)[:, None]
               + M.blk("bowl_lhb")[w] * lhb[:, None])
        z[ok] += dev * (1 - fw)
        return z

    def _subph(self, sub, ph):
        return self.SUBPH[np.where(ph == 1, len(self.SUBPH) - 1, sub * 3 + ph)]

    def _wterm_rows(self, wi, sub, spin, W=None):
        W = W or self.BOWL
        z = np.zeros((len(self.ph), K))
        ok = wi >= 0
        w = wi[ok]
        z[ok] = (W["b"][w] + W["pp"][w] * (self.ph[ok] == 0)[:, None] + W["de"][w] * (self.ph[ok] == 2)[:, None]
                 + W["lh"][w] * self.lhb[ok][:, None])
        z += self.SUB[sub] + self.SUBL[sub] * self.lhb[:, None] + self._subph(sub, self.ph)
        bi = np.maximum(self.bi, 0)
        spterm = np.where((self.bi >= 0)[:, None], self.BAT["sp"][bi], 0) + np.where((self.vi >= 0)[:, None], self.VSP[np.maximum(self.vi, 0)], 0)
        return z + spin[:, None] * spterm

    def eta_with_batter(self, vecs, lhb, rows=None):
        """vecs: dict of 11-vectors (b, pp, de, sp, ea) for one batter."""
        r = slice(None) if rows is None else rows
        ph, sp, ea = self.ph[r], self.spin[r], self.early[r]
        t = (vecs["b"] + vecs["pp"] * (ph == 0)[:, None] + vecs["de"] * (ph == 2)[:, None]
             + vecs["sp"] * sp[:, None] + vecs["ea"] * ea[:, None])
        wi = np.maximum(self.wi[r], 0)
        lterm = self.SUBL[self.sub[r]] + np.where((self.wi[r] >= 0)[:, None], self.BOWL["lh"][wi], 0)
        if "ty" in vecs:
            ti = self.ti[r]
            t = t + np.where((ti >= 0)[:, None], vecs["ty"][np.maximum(ti, 0)], 0)
        return self.eta[r] - self.bterm_actual[r] + t + float(lhb) * lterm

    def eta_with_bowler(self, vecs, sub, spin, rows=None):
        r = slice(None) if rows is None else rows
        ph, lhb = self.ph[r], self.lhb[r]
        t = (vecs["b"] + vecs["pp"] * (ph == 0)[:, None] + vecs["de"] * (ph == 2)[:, None]
             + vecs["lh"] * lhb[:, None]) + self.SUB[sub] + self.SUBL[sub] * lhb[:, None] + self._subph(np.full(len(ph), sub), ph)
        bi = np.maximum(self.bi[r], 0)
        spterm = np.where((self.bi[r] >= 0)[:, None], self.BAT["sp"][bi], 0) + np.where((self.vi[r] >= 0)[:, None], self.VSP[np.maximum(self.vi[r], 0)], 0)
        t = t + float(spin) * spterm
        tnew = TYPES6.index(SUBTYPES[sub]) if SUBTYPES[sub] in TYPES6 else -1
        if tnew >= 0:  # the real batter's split against the substituted bowler's type
            t = t + np.where((self.bi[r] >= 0)[:, None], self.BAT["ty"][np.maximum(self.bi[r], 0), tnew], 0)
        return self.eta[r] - self.wterm_actual[r] + t


def softmax(eta):
    e = np.exp(eta - eta.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


# %% metrics from probabilities


def bat_metrics(P, ex, wv=None):
    """P: rows x 11 (or draws x rows x 11). Returns per-row-averaged batting metrics (dict of arrays)."""
    m = P.mean(axis=-2)
    nb_bat, ro_runs, q = ex["nb_bat_mean"], ex["ro_runs_mean"], ex["runout_striker"]
    faced = 1 - m[..., C["wide"]]
    runs = (m[..., C["r1"]] + 2 * m[..., C["r2"]] + 3 * m[..., C["r3"]] + 4 * m[..., C["r4"]] + 6 * m[..., C["r6"]]
            + m[..., C["noball"]] * nb_bat + m[..., C["runout"]] * ro_runs)
    outs = m[..., C["wicket"]] + q * m[..., C["runout"]]
    bnd = m[..., C["r4"]] + m[..., C["r6"]]
    nonb = faced - bnd
    out = {"sr": 100 * runs / faced, "out_pct": 100 * outs / faced, "avg": runs / outs,
           "bnd_pct": 100 * bnd / faced, "four_pct": 100 * m[..., C["r4"]] / faced,
           "six_pct": 100 * m[..., C["r6"]] / faced,
           "dot_pct": 100 * (m[..., C["r0"]] + m[..., C["wicket"]] + m[..., C["byes"]]) / faced,
           "nbsr": 100 * (m[..., C["r1"]] + 2 * m[..., C["r2"]] + 3 * m[..., C["r3"]]) / nonb}
    if wv is not None:   # run value per ball faced = runs - P(out) * wicket value of the state
        rv = (runs_per_row(P, ex) - outs_per_row(P, ex) * wv).mean(axis=-1)
        out["rv100"] = 100 * rv / faced
    return out


def runs_per_row(P, ex):
    return (P[..., C["r1"]] + 2 * P[..., C["r2"]] + 3 * P[..., C["r3"]] + 4 * P[..., C["r4"]] + 6 * P[..., C["r6"]]
            + P[..., C["noball"]] * ex["nb_bat_mean"] + P[..., C["runout"]] * ex["ro_runs_mean"])


def outs_per_row(P, ex):
    return P[..., C["wicket"]] + ex["runout_striker"] * P[..., C["runout"]]


def conceded_per_row(P, ex):
    return (P[..., C["r1"]] + 2 * P[..., C["r2"]] + 3 * P[..., C["r3"]] + 4 * P[..., C["r4"]] + 6 * P[..., C["r6"]]
            + P[..., C["wide"]] * ex["wide_mean"] + P[..., C["noball"]] * (1 + ex["nb_bat_mean"])
            + P[..., C["runout"]] * ex["ro_runs_mean"])


def bowl_metrics(P, ex, wv=None):
    m = P.mean(axis=-2)
    legal = 1 - m[..., C["wide"]] - m[..., C["noball"]]
    conc = conceded_per_row(m, ex)
    wk = m[..., C["wicket"]]
    out = {"econ": 6 * conc / legal, "wkt_pct": 100 * wk / legal, "sr": legal / wk, "avg": conc / wk,
           "dot_pct": 100 * (m[..., C["r0"]] + m[..., C["wicket"]] + m[..., C["byes"]]) / legal,
           "bnd_pct": 100 * (m[..., C["r4"]] + m[..., C["r6"]]) / legal,
           "six_pct": 100 * m[..., C["r6"]] / legal,
           "wides_per_over": 6 * m[..., C["wide"]] / legal, "nb_per_over": 6 * m[..., C["noball"]] / legal}
    if wv is not None:   # runs conceded minus wicket value (per legal ball), lower is better
        allw = P[..., C["wicket"]] + P[..., C["runout"]]
        rv = (conceded_per_row(P, ex) - allw * wv).mean(axis=-1)
        out["rv_over"] = 6 * rv / legal
    return out


# %% helpers for weighted aggregation


def wmean(P, w):
    """P: rows x 11 (or draws x rows x 11); w: rows. Returns aggregated probability vector(s) with a
    singleton row axis so the *_metrics functions can average over it."""
    w = w / w.sum()
    return np.tensordot(P, w, axes=([-2], [0]))[..., None, :]


def bat_stats(P, w, ex, wv):
    m = wmean(P, w)
    out = bat_metrics(m, ex)
    faced = 1 - m[..., 0, C["wide"]]
    rv = np.tensordot(runs_per_row(P, ex) - outs_per_row(P, ex) * wv, w / w.sum(), axes=([-1], [0]))
    out["rv100"] = 100 * rv / faced
    return {k: np.squeeze(v) for k, v in out.items()}


def bowl_stats(P, w, ex, wv):
    m = wmean(P, w)
    out = bowl_metrics(m, ex)
    legal = 1 - m[..., 0, C["wide"]] - m[..., 0, C["noball"]]
    rv = np.tensordot(conceded_per_row(P, ex) - P[..., C["wicket"]] * wv, w / w.sum(), axes=([-1], [0]))
    out["rv_over"] = 6 * rv / legal
    return {k: np.squeeze(v) for k, v in out.items()}


def extras_dists(f):
    r = f[(f["comp"].astype(str) == "IPL") & (f["date"] >= "2023-01-01")]
    def dist(s, vals):
        s = s.clip(upper=max(vals))
        cnt = s.value_counts()
        return {"v": vals, "p": [float(cnt.get(v, 0) + 0.5) for v in vals]}
    w = r[r["cls"] == "wide"]["runs_total"]
    wide = dist(w.where(w.isin([1, 2, 3, 5]), 1), [1, 2, 3, 5])
    nbr = r[r["cls"] == "noball"]["runs_bat"]
    nb = dist(nbr.where(nbr.isin([0, 1, 2, 3, 4, 6]), 4), [0, 1, 2, 3, 4, 6])
    by = r[r["cls"] == "byes"]["byes"]
    bye = dist(by.where(by.isin([1, 2, 3, 4]), 1), [1, 2, 3, 4])
    ro = r[r["cls"] == "runout"]
    ror = dist(ro["runs_bat"].clip(upper=3), [0, 1, 2, 3])
    q = float((ro["player_out"] == ro["batter"]).mean())
    ex = {"wide_runs": wide, "nb_bat": nb, "bye_runs": bye, "runout_runs": ror, "runout_striker": q}
    mean = lambda d: float(np.dot(d["v"], d["p"]) / np.sum(d["p"]))
    stats = {"wide_mean": mean(wide), "nb_bat_mean": mean(nb), "ro_runs_mean": mean(ror), "runout_striker": q,
             "bye_mean": mean(bye)}
    return ex, stats


def resources_table(f):
    """Expected runs remaining in a first innings from the start of over o with w wickets down.
    Empirical (IPL + full-member T20I + top franchise leagues, 2021+), scaled to recent IPL level, then
    smoothed so it is monotone in wickets and overs."""
    r = f[(f["innings"] == 1) & (f["date"] >= "2021-01-01") & f["tier"].isin(["ipl", "intl", "top_fr"])]
    tot = r.groupby("match_id")["runs_total"].sum()
    st = r[r["legal_before"] % 6 == 0].drop_duplicates(["match_id", "legal_before"])
    st = st.assign(rem=tot.reindex(st["match_id"]).to_numpy() - st["score_before"].to_numpy())
    st = st.assign(o=st["legal_before"] // 6, w=st["wkts_before"].clip(upper=9))
    g = st.groupby(["o", "w"])["rem"].agg(["mean", "size"])
    ipl_recent = f[(f["innings"] == 1) & (f["comp"].astype(str) == "IPL") & (f["season"].astype(str).isin(IPL_RECENT))]
    scale = ipl_recent.groupby("match_id")["runs_total"].sum().mean() / tot.mean()
    ER = np.zeros((20, 11))
    for o in range(20):
        for w in range(10):
            # shrink sparse cells toward a parametric fallback (resources decline with wickets)
            fb = (20 - o) * 6 * 1.45 * max(0.05, 1 - w / 10) ** 1.2
            if (o, w) in g.index:
                mu, n = g.loc[(o, w), "mean"], g.loc[(o, w), "size"]
                ER[o, w] = (mu * n + fb * 20) / (n + 20)
            else:
                ER[o, w] = fb
    ER *= scale
    for o in range(20):  # monotone non-increasing in wickets
        for w in range(1, 11):
            ER[o, w] = min(ER[o, w], ER[o, w - 1])
    for w in range(11):  # non-increasing in overs bowled
        for o in range(1, 20):
            ER[o, w] = min(ER[o, w], ER[o - 1, w])
    ER[:, 10] = 0
    WV = ER[:, :10] - ER[:, 1:]
    return ER, WV, float(scale)


def wv_rows(ER, legal_before, wk):
    """Run value of a wicket at ball level (linear interpolation of ER between over starts)."""
    ERp = np.vstack([ER, np.zeros((1, 11))])
    x = np.clip(legal_before / 6.0, 0, 19.999)
    o = x.astype(int)
    t = x - o
    w = np.clip(wk, 0, 9).astype(int)
    a = ERp[o, w] * (1 - t) + ERp[o + 1, w] * t
    b = ERp[o, w + 1] * (1 - t) + ERp[o + 1, w + 1] * t
    return a - b


# %% build everything


def r3(x, d=3):
    return np.round(np.asarray(x, float), d).tolist()


def main():
    M = Model()
    f = pd.read_parquet(PROC / "frame.parquet")
    f = f[~f["reduced"]].reset_index(drop=True)
    cov = pd.read_parquet(PROC / "covariates.parquet")
    styles = pd.read_parquet(PROC / "styles.parquet")
    names = load_people()
    last_top = last_top_league(f)
    BAT, BOWL, pri_b, pri_w = folded_players(M, cov, styles, last_top=last_top)
    ex, exs = extras_dists(f)
    ER, WV, er_scale = resources_table(f)

    # ---------------- player pool
    rec = f[(f["date"] >= POOL_SINCE) & (f["tier"].astype(str) != "assoc")]
    ipl_rows = f[(f["comp"].astype(str) == "IPL") & (f["date"] >= "2023-01-01")]
    nbat = rec["batter"].value_counts()
    nbowl = rec["bowler"].value_counts()
    pool = (set(nbat[nbat >= POOL_MIN_BALLS].index) | set(nbowl[nbowl >= POOL_MIN_BALLS].index)
            | set(ipl_rows["batter"]) | set(ipl_rows["bowler"]) | set(ipl_rows["non_striker"]))
    pool = sorted(p for p in pool if p in M.bat_pos or p in M.bowl_pos)

    # ---------------- reference sample: IPL 2024-26 deliveries
    ref = f[(f["comp"].astype(str) == "IPL") & (f["season"].astype(str).isin(IPL_RECENT))].reset_index(drop=True)
    R = RefSample(M, ref, cov, BAT, BOWL)
    wv = wv_rows(ER, ref["legal_before"].to_numpy(), ref["wkts_before"].to_numpy())
    P_act = softmax(R.eta)
    ph = R.ph
    rng = np.random.default_rng(0)
    sub_rows = rng.choice(len(ref), size=min(4000, len(ref)), replace=False)
    strata_bat = {"all": None, "pp": ph == 0, "mid": ph == 1, "death": ph == 2, "pace": ~R.spin, "spin": R.spin}
    strata_bowl = {"all": None, "pp": ph == 0, "mid": ph == 1, "death": ph == 2, "rhb": ~R.lhb, "lhb": R.lhb}
    ph_count = np.bincount(ph, minlength=3).astype(float)

    # player phase mixes (time-weighted, recent)
    age = (f["date"].max() - f["date"]).dt.days.to_numpy() / 365.25
    wt = 0.5 ** (age / M.m["half_life"])
    fw = f.assign(wt=wt)
    mix_bat = fw.groupby(["batter", "phase"])["wt"].sum().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0)
    mix_bowl = fw[fw["legal"]].groupby(["bowler", "phase"])["wt"].sum().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0)
    role_mix_bat = ref.groupby([pd.cut(ref["bat_pos"], [0, 2, 4, 7, 11], labels=ROLES_BAT), "phase"], observed=True).size().unstack(fill_value=0)

    def row_weights(mix, mask):
        mix = np.asarray(mix, float)
        mix = mix / mix.sum() if mix.sum() > 0 else np.array([0.3, 0.45, 0.25])
        w = mix[ph] / np.maximum(ph_count[ph], 1)
        if mask is not None:
            w = w * mask
        return w

    def avg_stats(kind):
        out = {}
        st = strata_bat if kind == "bat" else strata_bowl
        for s, mask in st.items():
            w = np.ones(len(ref)) if mask is None else mask.astype(float)
            out[s] = (bat_stats if kind == "bat" else bowl_stats)(P_act, w, exs, wv)
        return out

    AVG_BAT, AVG_BOWL = avg_stats("bat"), avg_stats("bowl")

    rows_bat, rows_bowl, settle = [], [], {}
    bf_blk = M.blk("bf")
    bfb_ref = ref["bf_b"].to_numpy().astype(int)
    mid_rows = rng.choice(np.flatnonzero(ph == 1), size=3000, replace=False)
    for pid in pool:
        if pid in M.bat_pos:
            i = M.bat_pos[pid]
            vec = {k: BAT[k][i] for k in ("b", "pp", "de", "sp", "ea")}
            vec["ty"] = BAT["ty"][i]
            lh = bool(BAT["lhb"][i])
            P = softmax(R.eta_with_batter(vec, lh))
            role = cov["role_bat"].get(pid, "lower")
            mix = mix_bat.loc[pid].to_numpy() if pid in mix_bat.index else role_mix_bat.loc[role].to_numpy()
            rec_ = {"id": pid}
            for s, mask in strata_bat.items():
                w = row_weights(mix, mask) if s in ("all", "pace", "spin") else mask.astype(float)
                st = bat_stats(P, w, exs, wv)
                av = bat_stats(P_act, w, exs, wv)  # average IPL batter in exactly the same deliveries
                for k, v in st.items():
                    rec_[f"{s}_{k}"] = float(v)
                    rec_[f"{s}_avg_{k}"] = float(av[k])
            # by bowling type (right/left-arm pace, off-spin, leg-spin, SLA, left-arm wrist spin)
            for t_i, t in enumerate(TYPES6):
                mask = R.ti == t_i
                if mask.sum() < 200:
                    continue
                w = row_weights(mix, mask)
                st = bat_stats(P, w, exs, wv)
                av = bat_stats(P_act, w, exs, wv)
                for k in ("sr", "out_pct", "rv100", "bnd_pct", "dot_pct"):
                    rec_[f"t_{t}_{k}"] = float(st[k])
                    rec_[f"t_{t}_avg_{k}"] = float(av[k])
            # posterior uncertainty: draw the player's own coefficients
            nd = 30
            dr = {k: vec[k][None] + rng.standard_normal((nd, K)) * BAT["sd_" + k][i][None] * (np.arange(K) != REF)
                  for k in ("b", "pp", "de", "sp", "ea")}
            ets = np.stack([R.eta_with_batter(dict({k: dr[k][d] for k in dr}, ty=vec["ty"]), lh, sub_rows)
                            for d in range(nd)])
            Pd = softmax(ets)
            wsub = row_weights(mix, None)[sub_rows]
            sd = bat_stats(Pd, wsub, exs, wv[sub_rows])
            rec_.update({"sd_sr": float(np.std(sd["sr"])), "sd_out_pct": float(np.std(sd["out_pct"])),
                         "sd_rv100": float(np.std(sd["rv100"])), "sd_avg": float(np.std(sd["avg"]))})
            rows_bat.append(rec_)
            # settling curve: force balls-faced bucket
            e0 = R.eta_with_batter(vec, lh, mid_rows)
            base_bf = bf_blk[1 * 9 + bfb_ref[mid_rows]]
            e0 = e0 - base_bf - vec["ea"] * R.early[mid_rows][:, None]
            curve = []
            for bkt in range(9):
                e = e0 + bf_blk[9 + bkt] + vec["ea"] * (BF_EDGES[bkt] < EARLY_BF)
                st = bat_stats(softmax(e), np.ones(len(mid_rows)), exs, wv[mid_rows])
                curve.append([round(float(st["sr"]), 1), round(float(st["out_pct"]), 2)])
            settle[pid] = curve
        if pid in M.bowl_pos:
            j = M.bowl_pos[pid]
            vec = {k: BOWL[k][j] for k in ("b", "pp", "de", "lh")}
            sub, spin = int(BOWL["sub"][j]), bool(BOWL["spin"][j])
            P = softmax(R.eta_with_bowler(vec, sub, spin))
            mix = mix_bowl.loc[pid].to_numpy() if pid in mix_bowl.index else np.array([0.3, 0.45, 0.25])
            rec_ = {"id": pid}
            for s, mask in strata_bowl.items():
                w = row_weights(mix, mask) if s in ("all", "rhb", "lhb") else mask.astype(float)
                st = bowl_stats(P, w, exs, wv)
                av = bowl_stats(P_act, w, exs, wv)
                for k, v in st.items():
                    rec_[f"{s}_{k}"] = float(v)
                    rec_[f"{s}_avg_{k}"] = float(av[k])
            nd = 30
            dr = {k: vec[k][None] + rng.standard_normal((nd, K)) * BOWL["sd_" + k][j][None] * (np.arange(K) != REF)
                  for k in vec}
            ets = np.stack([R.eta_with_bowler({k: dr[k][d] for k in dr}, sub, spin, sub_rows) for d in range(nd)])
            sd = bowl_stats(softmax(ets), row_weights(mix, None)[sub_rows], exs, wv[sub_rows])
            rec_.update({"sd_econ": float(np.std(sd["econ"])), "sd_wkt_pct": float(np.std(sd["wkt_pct"])),
                         "sd_rv_over": float(np.std(sd["rv_over"]))})
            rows_bowl.append(rec_)
    bat_df = pd.DataFrame(rows_bat).set_index("id")
    bowl_df = pd.DataFrame(rows_bowl).set_index("id")
    # global settling curve (average IPL batter, actual mix)
    e0 = R.eta[mid_rows] - bf_blk[9 + bfb_ref[mid_rows]]
    settle_avg = []
    for bkt in range(9):
        st = bat_stats(softmax(e0 + bf_blk[9 + bkt]), np.ones(len(mid_rows)), exs, wv[mid_rows])
        settle_avg.append([round(float(st["sr"]), 1), round(float(st["out_pct"]), 2)])

    # ---------------- observed vs expected (all comps since 2024)
    obs = observed_vs_expected(M, f, cov, BAT, BOWL, R, exs)

    # ---------------- leagues and venues
    leagues = league_strength(M, f, cov, BAT, BOWL, R, P_act, exs, wv)
    venues = venue_table(M, f, R, exs, wv)

    out = dict(bat=bat_df, bowl=bowl_df, mix_bat=mix_bat, settle=settle, settle_avg=settle_avg, avg_bat=AVG_BAT, avg_bowl=AVG_BOWL,
               obs=obs, leagues=leagues, venues=venues, ER=ER, WV=WV, er_scale=er_scale, ex=ex, exs=exs, pool=pool,
               names=names)
    with open(PROC / "ratings.pkl", "wb") as fh:
        pickle.dump(out, fh)
    # notable batter x bowler head-to-heads (only if the fit has the block)
    pair_terms, h2h = {}, []
    opts = M.m.get("opts") or {}
    if "pair" in M.blocks and opts.get("pairs") is not None:
        p0 = P_act.mean(0)
        rv = np.array([0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 6], float)
        PR = M.blk("pair")
        dP = p0[None, :] * (PR - (PR * p0[None, :]).sum(1, keepdims=True))   # first-order change in class probs
        d_runs = dP @ rv
        d_out = dP[:, C["wicket"]] + exs["runout_striker"] * dP[:, C["runout"]]
        key = f["batter"].astype(str) + "|" + f["bowler"].astype(str)
        cls = f["cls"].astype(str)
        raw = pd.DataFrame({"k": key, "faced": cls != "wide",
                            "runs": np.where(cls.isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), f["runs_bat"], 0),
                            "out": (cls == "wicket") | ((cls == "runout") & (f["player_out"] == f["batter"]))})
        rg = raw.groupby("k").agg(balls=("faced", "sum"), runs=("runs", "sum"), outs=("out", "sum"))
        for j, pk in enumerate(opts["pairs"]):
            if abs(d_runs[j]) >= 0.05 or abs(d_out[j]) >= 0.005:
                b_, w_ = pk.split("|")
                pair_terms[(b_, w_)] = PR[j]
                r_ = rg.loc[pk] if pk in rg.index else None
                h2h.append(dict(batter=b_, bowler=w_, batter_name=names.get(b_, b_), bowler_name=names.get(w_, w_),
                                balls=int(r_["balls"]) if r_ is not None else 0, runs=int(r_["runs"]) if r_ is not None else 0,
                                outs=int(r_["outs"]) if r_ is not None else 0, d_sr=float(100 * d_runs[j]),
                                d_out_pct=float(100 * d_out[j])))
    out["h2h"] = h2h
    out["n_pairs_fitted"] = int(len(opts.get("pairs", []) or []))
    shock = estimate_match_shock(M, f, cov, BAT, BOWL, exs)
    out["match_shock"] = shock
    with open(PROC / "ratings.pkl", "wb") as fh:
        pickle.dump(out, fh)
    write_sim_params(M, BAT, BOWL, pri_b, pri_w, ex, pool, venues, styles, names,
                     match_shock={"sd": round(shock["sd"], 4), "innings_sd": round(shock["innings_sd"], 4),
                                  "dir": shock["dir"]},
                     conditions=build_conditions(M, venues, shock), pair_terms=pair_terms)
    print(f"ratings: pool={len(pool)} batters={len(bat_df)} bowlers={len(bowl_df)} venues={len(venues)}")


# %% observed vs expected, leagues, venues


def observed_vs_expected(M, f, cov, BAT, BOWL, R, exs):
    rec = f[f["date"] >= POOL_SINCE].reset_index(drop=True)
    Q = RefSample(M, rec, cov, BAT, BOWL)
    avgB = np.stack([R.bterm_actual[R.ph == p].mean(0) for p in range(3)])
    avgW = np.stack([R.wterm_actual[R.ph == p].mean(0) for p in range(3)])
    Pb = softmax(Q.eta - Q.bterm_actual + avgB[Q.ph])
    Pw = softmax(Q.eta - Q.wterm_actual + avgW[Q.ph])
    cls = rec["cls"].astype(str).to_numpy()
    faced = cls != "wide"
    bat_runs = np.where(np.isin(cls, ["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), rec["runs_bat"], 0)
    bat_out = ((cls == "wicket") | ((cls == "runout") & (rec["player_out"] == rec["batter"]))).to_numpy()
    legal = ~np.isin(cls, ["wide", "noball"])
    conc = rec["runs_total"].to_numpy() - rec["byes"].to_numpy()
    d = pd.DataFrame({
        "batter": rec["batter"], "bowler": rec["bowler"], "ipl": (rec["comp"].astype(str) == "IPL").to_numpy(),
        "faced": faced, "runs": bat_runs, "xruns": runs_per_row(Pb, exs) * 1.0, "out": bat_out,
        "xout": outs_per_row(Pb, exs), "xfaced": 1 - Pb[:, C["wide"]],
        "legal": legal, "conc": conc, "xconc": conceded_per_row(Pw, exs), "wkt": cls == "wicket",
        "xwkt": Pw[:, C["wicket"]], "four": cls == "r4", "six": cls == "r6",
        "x4": Pb[:, C["r4"]], "x6": Pb[:, C["r6"]], "dot": np.isin(cls, ["r0", "wicket", "byes"]),
        "xdot_w": Pw[:, C["r0"]] + Pw[:, C["wicket"]] + Pw[:, C["byes"]],
    })
    out = {}
    for scope, dd in (("all", d), ("ipl", d[d["ipl"]])):
        gb = dd.groupby("batter")
        b = pd.DataFrame({"balls": gb["faced"].sum(), "runs": gb["runs"].sum(), "xruns": gb["xruns"].sum(),
                          "outs": gb["out"].sum(), "xouts": gb["xout"].sum(), "fours": gb["four"].sum(),
                          "sixes": gb["six"].sum(), "x4": gb["x4"].sum(), "x6": gb["x6"].sum()})
        gw = dd.groupby("bowler")
        w = pd.DataFrame({"balls": gw["legal"].sum(), "conc": gw["conc"].sum(), "xconc": gw["xconc"].sum(),
                          "wkts": gw["wkt"].sum(), "xwkts": gw["xwkt"].sum(), "dots": gw["dot"].sum(),
                          "xdots": gw["xdot_w"].sum()})
        out[scope] = (b, w)
    return out


def league_strength(M, f, cov, BAT, BOWL, R, P_act, exs, wv):
    rec = f[f["date"] >= "2023-01-01"].reset_index(drop=True)
    Q = RefSample(M, rec, cov, BAT, BOWL)
    comps = rec["comp"].astype(str).to_numpy()
    w = np.ones(len(R.ph))
    ipl_b = bat_stats(P_act, w, exs, wv)
    ipl_w = bowl_stats(P_act, w, exs, wv)
    comp_blk = M.blk("comp")
    cs_blk = M.blk("cs")
    cs_lab = M.blocks["cs"][1]
    env_ipl = cs_blk[cs_lab.index("IPL|2026")]
    rows = []
    for c in sorted(set(comps)):
        m = comps == c
        if m.sum() < 3000:
            continue
        mb = Q.bterm_actual[m].mean(0)
        mw = Q.wterm_actual[m].mean(0)
        sb = bat_stats(softmax(R.eta - R.bterm_actual + mb), w, exs, wv)
        sw = bowl_stats(softmax(R.eta - R.wterm_actual + mw), w, exs, wv)
        seasons = sorted({s for s in rec.loc[m, "season"].astype(str)})
        last = seasons[-1]
        env = (comp_blk[M.comps.index(c)] if c in M.comps else 0) + cs_blk[cs_lab.index(f"{c}|{last}")]
        se = bowl_stats(softmax(R.eta + env - env_ipl), w, exs, wv)
        bat_idx = float((sb["rv100"] - ipl_b["rv100"]) * 1.2)       # runs per 120 balls vs IPL batting
        bowl_idx = float((ipl_w["rv_over"] - sw["rv_over"]) * 20)    # runs saved per 20 overs vs IPL bowling
        rows.append(dict(comp=c, name=COMP_NAMES.get(c, c), balls=int(m.sum()),
                         matches=int(rec.loc[m, "match_id"].nunique()), last_season=last,
                         bat_sr=float(sb["sr"]), bat_out_pct=float(sb["out_pct"]), bat_runs_vs_ipl=bat_idx,
                         bowl_econ=float(sw["econ"]), bowl_wkt_pct=float(sw["wkt_pct"]), bowl_runs_vs_ipl=bowl_idx,
                         strength_vs_ipl=bat_idx + bowl_idx,
                         env_runs_per_over=float(se["econ"]), env_wkt_pct=float(se["wkt_pct"])))
    df = pd.DataFrame(rows)
    ipl = df[df["comp"] == "IPL"].iloc[0]
    for c in ("bat_runs_vs_ipl", "bowl_runs_vs_ipl"):  # IPL 2023-26 participants = 0 by construction
        df[c] = df[c] - ipl[c]
    df["strength_vs_ipl"] = df["bat_runs_vs_ipl"] + df["bowl_runs_vs_ipl"]
    return df.sort_values("strength_vs_ipl", ascending=False)


# current display names for grounds whose cricsheet spelling is old or inconsistent (ids stay stable)
VENUE_DISPLAY = {
    "arun jaitley stadium": "Arun Jaitley Stadium, Delhi",
    "narendra modi stadium": "Narendra Modi Stadium, Ahmedabad",
    "punjab cricket association stadium": "Punjab Cricket Association IS Bindra Stadium, Mohali",
    "zayed cricket stadium": "Zayed Cricket Stadium, Abu Dhabi",
    "maharashtra cricket association stadium": "Maharashtra Cricket Association Stadium, Pune",
    "dy patil stadium": "Dr DY Patil Sports Academy, Navi Mumbai",
    "m chinnaswamy stadium": "M Chinnaswamy Stadium, Bengaluru",
    "ma chidambaram stadium": "MA Chidambaram Stadium, Chennai",
    "rajiv gandhi international stadium": "Rajiv Gandhi International Stadium, Hyderabad",
    "ekana cricket stadium": "Bharat Ratna Shri Atal Bihari Vajpayee Ekana Cricket Stadium, Lucknow",
    "aca-vdca stadium": "Dr YS Rajasekhara Reddy ACA-VDCA Cricket Stadium, Visakhapatnam",
    "mullanpur stadium": "Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh",
    "hpca stadium": "Himachal Pradesh Cricket Association Stadium, Dharamsala",
    "barsapara stadium": "Barsapara Cricket Stadium, Guwahati",
    "sns stadium raipur": "Shaheed Veer Narayan Singh International Stadium, Raipur",
    "wankhede stadium": "Wankhede Stadium, Mumbai",
    "eden gardens": "Eden Gardens, Kolkata",
    "sawai mansingh stadium": "Sawai Mansingh Stadium, Jaipur",
    "brabourne stadium": "Brabourne Stadium, Mumbai",
    "dubai international cricket stadium": "Dubai International Cricket Stadium",
    "sharjah cricket stadium": "Sharjah Cricket Stadium",
    "holkar stadium": "Holkar Cricket Stadium, Indore",
    "st georges park": "St George's Park, Gqeberha",
    "supersport park": "SuperSport Park, Centurion",
    "the wanderers stadium": "Wanderers Stadium, Johannesburg",
    "kennington oval": "Kennington Oval, London",
    "rose bowl": "The Rose Bowl, Southampton",
    "shere bangla national stadium": "Shere Bangla National Stadium, Mirpur",
    "zahur ahmed chowdhury stadium": "Zahur Ahmed Chowdhury Stadium, Chattogram",
    "daren sammy stadium": "Daren Sammy National Cricket Stadium, Gros Islet",
    "darren sammy national cricket stadium": "Daren Sammy National Cricket Stadium, Gros Islet",
    "docklands stadium": "Docklands Stadium (Marvel Stadium), Melbourne",
    "perth stadium": "Perth Stadium (Optus Stadium), Perth",
    "bellerive oval": "Bellerive Oval, Hobart",
    "brisbane cricket ground": "Brisbane Cricket Ground (Gabba)",
}


def venue_terms(M):
    return M.blk("venue"), M.blk("venue_i2"), M.blk("venue_spin"), M.blk("venue", True), M.blk("venue_i2", True), M.blk("venue_spin", True)


def venue_table(M, f, R, exs, wv):
    VB, VI, VS, SB, SI, SS = venue_terms(M)
    inn2 = (R.f["innings"].to_numpy() == 2)
    vi = np.maximum(R.vi, 0)
    act = (VB[vi] + VI[vi] * inn2[:, None] + VS[vi] * R.spin[:, None]) * (R.vi >= 0)[:, None]
    eta0 = R.eta - act
    P0 = softmax(eta0)
    def summ(P, mask):
        m = P[mask].mean(0)
        legal = 1 - m[C["wide"]] - m[C["noball"]]
        return dict(rpo=6 * conceded_per_row(m, exs) / legal, wpo=6 * (m[C["wicket"]] + m[C["runout"]]) / legal,
                    fpo=6 * m[C["r4"]] / legal, spo=6 * m[C["r6"]] / legal)
    allm = np.ones(len(R.ph), bool)
    masks = {"all": allm, "pace": ~R.spin, "spin": R.spin, "inn1": ~inn2, "inn2": inn2}
    neutral = {k: summ(P0, m) for k, m in masks.items()}
    mm = pd.read_parquet(PROC / "matches.parquet")
    mm = mm[~mm["reduced"]]
    cnt = mm.groupby("venue").agg(matches=("match_id", "size"), last=("date", "max"),
                                  ipl=("comp", lambda s: int((s == "IPL").sum())))
    rec_cnt = mm[mm["date"] >= "2021-01-01"].groupby("venue").size()
    disp_modal = mm.groupby("venue")["venue_raw"].agg(lambda s: s.value_counts().index[0])
    latest = mm.sort_values("date").groupby("venue")["venue_raw"].last()
    disp = {v: VENUE_DISPLAY.get(v, latest.get(v, v)) for v in latest.index}
    city = mm.groupby("venue")["city"].agg(lambda s: s.value_counts().index[0] if len(s.dropna()) else "")
    rng = np.random.default_rng(1)
    sub = rng.choice(len(R.ph), size=min(6000, len(R.ph)), replace=False)
    rows = []
    for v, i in M.venue_pos.items():
        if v not in cnt.index or cnt.loc[v, "last"] < pd.Timestamp("2018-01-01") or cnt.loc[v, "matches"] < 5:
            continue
        e = eta0 + VB[i] + VI[i] * inn2[:, None] + VS[i] * R.spin[:, None]
        P = softmax(e)
        r = dict(venue=v, name=disp.get(v, v), name_raw=disp_modal.get(v, v), city=city.get(v, ""), matches=int(cnt.loc[v, "matches"]),
                 matches_since_2021=int(rec_cnt.get(v, 0)), ipl_matches=int(cnt.loc[v, "ipl"]),
                 last_match=str(cnt.loc[v, "last"].date()))
        for k, m in masks.items():
            s = summ(P, m)
            for q, val in s.items():
                r[f"{k}_{q}"] = float(val)
                r[f"{k}_{q}_mult"] = float(val / neutral[k][q])
        # uncertainty on the overall runs multiplier from the venue coefficients
        draws = []
        for _ in range(20):
            z = lambda a, s_: a + rng.standard_normal(K) * s_ * (np.arange(K) != REF)
            e = eta0[sub] + z(VB[i], SB[i]) + z(VI[i], SI[i]) * inn2[sub][:, None] + z(VS[i], SS[i]) * R.spin[sub][:, None]
            draws.append(summ(softmax(e), np.ones(len(sub), bool))["rpo"] / summ(P0[sub], np.ones(len(sub), bool))["rpo"])
        r["all_rpo_mult_sd"] = float(np.std(draws))
        rows.append(r)
    df = pd.DataFrame(rows)
    df.attrs["neutral"] = neutral
    return df


# %% match-level shock (shared pitch/day conditions)


def estimate_match_shock(M, f, cov, BAT, BOWL, exs):
    """Both innings of a match share conditions the per-ball model cannot see. Measure it as the covariance
    between the two innings' residual scoring rates (actual minus model-expected runs per delivery) in IPL
    2022-26, and express it as a match-level normal shock z*dir on the logits, where dir is the
    2021->2026 IPL scoring-environment direction (more boundaries, fewer dots). Returns {sd, dir, ...}."""
    r = f[(f["comp"].astype(str) == "IPL") & (f["date"] >= "2022-01-01")].reset_index(drop=True)
    Q = RefSample(M, r, cov, BAT, BOWL)
    P = softmax(Q.eta)
    x = conceded_per_row(P, exs) + P[:, C["byes"]] * exs["bye_mean"]
    # per-ball variance of runs under the model (class means; within-class spread ignored)
    rv = np.array([exs["wide_mean"], 1 + exs["nb_bat_mean"], exs["bye_mean"], 0, exs["ro_runs_mean"], 0, 1, 2, 3, 4, 6])
    vb = (P * rv ** 2).sum(1) - (P * rv).sum(1) ** 2
    d = pd.DataFrame({"m": r["match_id"], "i": r["innings"], "x": x, "a": r["runs_total"], "n": 1, "v": vb})
    g = d.groupby(["m", "i"]).sum()
    g["res"] = (g["a"] - g["x"]) / g["n"]
    g["noise"] = g["v"] / g["n"] ** 2
    w = g["res"].unstack().dropna()
    nz = g["noise"].unstack().reindex(w.index)
    c = float(np.cov(w[1], w[2])[0, 1])
    # innings-level excess variance beyond the shared match component and sampling noise
    exc = [float(np.var(w[i], ddof=1) - nz[i].mean() - c) for i in (1, 2)]
    # chase residual (2nd minus 1st innings), noise-corrected spread -> dew dial size
    dvar = float(np.var(w[2] - w[1], ddof=1) - nz[1].mean() - nz[2].mean())
    cs_lab = M.blocks["cs"][1]
    cs = M.blk("cs")
    dvec = cs[cs_lab.index("IPL|2026")] - cs[cs_lab.index("IPL|2021")]
    dvec = dvec / np.sqrt(np.sum(dvec ** 2))
    h = 0.05
    d1 = float(np.mean(conceded_per_row(softmax(Q.eta + h * dvec), exs) - conceded_per_row(P, exs)) / h)
    sd = float(np.sqrt(max(c, 0.0)) / d1) if d1 > 0 else 0.0
    inn_sd = float(np.sqrt(max(np.mean(exc), 0.0)) / d1) if d1 > 0 else 0.0
    chase_sd = float(np.sqrt(max(dvar, 0.0)) / d1) if d1 > 0 else 0.0
    return {"sd": sd, "innings_sd": inn_sd, "chase_sd": chase_sd, "dir": r3(dvec, 4), "residual_cov": c,
            "residual_corr": float(np.corrcoef(w[1], w[2])[0, 1]), "innings_excess_var": exc,
            "chase_residual_var_true": dvar, "runs_per_ball_per_unit": d1, "n_matches": int(len(w))}


def build_conditions(M, venues, shock):
    """Optional user inputs for the simulator, as logit shifts estimated from between-venue / between-match
    variation (documented in method.md):
      pitch: flat = +1 SD of the match-conditions shock; slow_low = -1 SD plus the spin-term gap between the
             most spin-friendly fifth of grounds and the average ground (spin deliveries); seaming = -0.5 SD plus
             the venue-term gap of the fifth of grounds where pace takes most wickets (pace deliveries); normal = 0.
      dew:   heavy / none = 2nd-innings venue-term gap of the fifth of grounds with the biggest / smallest
             2nd-vs-1st-innings scoring ratio vs the average ground; normal = 0."""
    VB, VI, VS = M.blk("venue"), M.blk("venue_i2"), M.blk("venue_spin")
    v = venues[venues["venue"].isin(M.venue_pos)].copy()
    v["i"] = v["venue"].map(M.venue_pos)
    v = v[v["matches_since_2021"] >= 10]
    def gap(block, col, top=True):
        q = v[col].quantile(0.8 if top else 0.2)
        sel = v[v[col] >= q] if top else v[v[col] <= q]
        return block[sel["i"].to_numpy()].mean(0) - block[v["i"].to_numpy()].mean(0)
    sd = float(shock.get("sd", 0.0))
    d = np.asarray(shock.get("dir", [0.0] * K), float)
    v["dew_ratio"] = v["inn2_rpo_mult"] / v["inn1_rpo_mult"]
    z = np.zeros(K)
    return {
        "pitch": {"normal": {}, "flat": {"all": r3(sd * d)},
                  "slow_low": {"all": r3(-sd * d), "spin": r3(gap(VS, "spin_wpo_mult"))},
                  "seaming": {"all": r3(-0.5 * sd * d), "pace": r3(gap(VB, "pace_wpo_mult"))}},
        # dew: 90th / 10th percentile of the (noise-corrected) match-level chase residual, on 2nd-innings balls
        "dew": {"normal": {}, "heavy": {"i2": r3(1.2816 * float(shock.get("chase_sd", 0.0)) * d)},
                "none": {"i2": r3(-1.2816 * float(shock.get("chase_sd", 0.0)) * d)}},
    }


# %% sim params export


def write_sim_params(M, BAT, BOWL, pri_b, pri_w, ex, pool, venues, styles, names, path=None, env_alias=None,
                     default_env="IPL|2026", match_shock=None, conditions=None, pair_terms=None):
    base = M.base_table()
    cs_lab = M.blocks["cs"][1]
    cs = M.blk("cs")
    csp = M.blk("cs_ph") if "cs_ph" in M.blocks else None
    env, env_phase = {}, {}
    z = [0.0] * K
    for lab in cs_lab:
        if lab.startswith("IPL|"):
            k = cs_lab.index(lab)
            env[lab] = r3(cs[k])
            env_phase[lab] = [r3(csp[2 * k]), z, r3(csp[2 * k + 1])] if csp is not None else [z, z, z]
    recent = [l for l in cs_lab if l.startswith("IPL|") and l.split("|")[1] in IPL_RECENT]
    if recent:
        ks = [cs_lab.index(l) for l in recent]
        env["IPL|2024-26"] = r3(np.mean([cs[k] for k in ks], axis=0))
        env_phase["IPL|2024-26"] = ([r3(np.mean([csp[2 * k] for k in ks], axis=0)), z,
                                     r3(np.mean([csp[2 * k + 1] for k in ks], axis=0))] if csp is not None else [z, z, z])
    env_phase_inn = {}
    if "cs_ph_inn" in M.blocks:
        cpi = M.blk("cs_ph_inn")
        for lab in cs_lab:
            if lab.startswith("IPL|"):
                k = cs_lab.index(lab)
                base_ph = env_phase[lab]
                env_phase_inn[lab] = [[r3(np.asarray(base_ph[p_]) + cpi[k * 6 + i * 3 + p_]) for p_ in range(3)] for i in range(2)]
        if recent:
            env_phase_inn["IPL|2024-26"] = [[r3(np.mean([np.asarray(env_phase_inn[l][i][p_]) for l in recent], axis=0))
                                            for p_ in range(3)] for i in range(2)]
    for a, b in (env_alias or {}).items():   # e.g. holdout model: unseen IPL|2026 -> IPL|2025
        if b in env_phase_inn:
            env_phase_inn[a] = env_phase_inn[b]
        env[a], env_phase[a] = env[b], env_phase[b]
    bats, bowls = {}, {}
    for pid in pool:
        if pid in M.bat_pos:
            i = M.bat_pos[pid]
            bats[pid] = {"b": r3(BAT["b"][i]), "pp": r3(BAT["pp"][i]), "de": r3(BAT["de"][i]),
                         "sp": r3(BAT["sp"][i]), "ea": r3(BAT["ea"][i]), "hand": "L" if BAT["lhb"][i] else "R"}
            ty = {t: r3(BAT["ty"][i, k]) for k, t in enumerate(TYPES6) if np.abs(BAT["ty"][i, k]).max() >= 0.01}
            if ty:
                bats[pid]["ty"] = ty
        if pid in M.bowl_pos:
            j = M.bowl_pos[pid]
            bowls[pid] = {"b": r3(BOWL["b"][j]), "pp": r3(BOWL["pp"][j]), "de": r3(BOWL["de"][j]),
                          "lh": r3(BOWL["lh"][j]), "sub": SUBTYPES[int(BOWL["sub"][j])], "spin": int(bool(BOWL["spin"][j]))}
    VB, VI, VS = M.blk("venue"), M.blk("venue_i2"), M.blk("venue_spin")
    ven = {}
    for v in (venues["venue"] if hasattr(venues, "columns") else venues):
        if v not in M.venue_pos:
            continue
        i = M.venue_pos[v]
        ven[v] = {"base": r3(VB[i]), "i2": r3(VI[i]), "spin": r3(VS[i])}
    pairs_out = {}
    for (b_, w_), vec in (pair_terms or {}).items():
        if b_ in bats and w_ in bowls:
            pairs_out.setdefault(b_, {})[w_] = r3(vec)
    params = {
        "pairs": pairs_out,
        "version": 1, "classes": CLASSES, "ref_class": REF,
        "base": r3(base.ravel()), "base_shape": [2, 20, 8, K],
        "bf": r3(M.blk("bf").ravel()), "bf_shape": [3, 9, K], "bf_edges": BF_EDGES[:-1], "bf_labels": BF_LABELS,
        "early_bf": EARLY_BF,
        "chase": r3(M.blk("chase").ravel()), "chase_shape": [3, 8, K], "rrr_edges": RRR_EDGES[1:-1],
        "chase_w": r3(M.blk("chase_w").ravel()) if "chase_w" in M.blocks else None, "chase_w_shape": [3, 8, 3, K],
        "chase_w_bands": ["1-3", "4-6", "7-10"],
        "chase_hi": r3(M.blk("chase_hi").ravel()) if "chase_hi" in M.blocks else None, "chase_hi_shape": [3, 2, K],
        "chase_hi_edges": [20, 24],
        "rrr_labels": RRR_LABELS,
        "sub": {s: r3(M.blk("sub")[i]) for i, s in enumerate(SUBTYPES)},
        "sub_lhb": {s: r3(M.blk("sub_lhb")[i]) for i, s in enumerate(SUBTYPES)},
        "sub_phase": {s: [r3(M.blk("sub_ph")[i * 3 + 0]), [0.0] * K, r3(M.blk("sub_ph")[i * 3 + 2])]
                      for i, s in enumerate(SUBTYPES)},
        "env": env, "default_env": default_env, "env_phase": env_phase, "env_phase_inn": env_phase_inn,
        "match_shock": match_shock or {"sd": 0.0, "dir": [0.0] * K},
        "conditions": conditions or {},
        "venues": ven, "venue_neutral": {"base": z, "i2": z, "spin": z},
        "batters": bats, "bowlers": bowls,
        "batter_priors": {r: {"b": r3(v), "pp": z, "de": z, "sp": z, "ea": z, "hand": "R"} for r, v in pri_b.items()},
        "bowler_priors": {r: {"b": r3(v), "pp": z, "de": z, "lh": z, "sub": "spin_U" if r.startswith("spin") else "pace_U",
                              "spin": int(r.startswith("spin"))} for r, v in pri_w.items()},
        "extras": ex,
    }
    (path or (EXPORT / "sim_params.json")).write_text(json.dumps(params, separators=(",", ":")))
    return params


if __name__ == "__main__":
    main()
