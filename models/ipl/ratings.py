"""Turn the fitted logit model into (a) sim_params tables and (b) context-adjusted player/venue/league metrics."""
# %% imports
import json
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import CLASSES, COMP_NAMES, EXPORT, K, PEOPLE, PROC, REF, TIERS
from models.ipl.fit import build_design, predict_eta, probs_from_eta
from models.ipl.prep import BF_EDGES, BF_LABELS, EARLY_BF, RRR_EDGES, RRR_LABELS, SUBTYPES

C = {c: i for i, c in enumerate(CLASSES)}
ROLES_BAT = ["open", "top", "middle", "lower"]
ROLES_BOWL = ["pace_part", "pace_reg", "pace_front", "spin_part", "spin_reg", "spin_front"]
POOL_SINCE = pd.Timestamp("2024-01-01")
POOL_MIN_BALLS = 150
IPL_RECENT = ("2024", "2025", "2026")


# %% model access


class Model:
    def __init__(self):
        with open(PROC / "model.pkl", "rb") as fh:
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


def folded_players(M, cov, styles):
    """Batter / bowler logit vectors with the hierarchical prior mean folded in."""
    bat_role, bat_tier = M.blk("bat_role"), M.blk("bat_tier")
    bowl_role, bowl_tier = M.blk("bowl_role"), M.blk("bowl_tier")
    nbt = len(M.players_bat)
    cb = cov.reindex(M.players_bat)
    rb = cb["role_bat"].map({r: i for i, r in enumerate(ROLES_BAT)}).fillna(3).astype(int).to_numpy()
    tb = cb[["bat_tier_" + t for t in TIERS]].fillna(0).to_numpy()
    eb = cb["exp_bat"].fillna(0).astype(int).to_numpy()
    prior_b = bat_role[rb] + tb[:, 1:] @ bat_tier[1:] + M.blk("bat_exp")[eb]
    BAT = {"b": M.blk("bat") + prior_b, "pp": M.blk("bat_pp"), "de": M.blk("bat_death"),
           "sp": M.blk("bat_spin"), "ea": M.blk("bat_early"), "prior": prior_b,
           "sd_b": M.blk("bat", True), "sd_pp": M.blk("bat_pp", True), "sd_de": M.blk("bat_death", True),
           "sd_sp": M.blk("bat_spin", True), "sd_ea": M.blk("bat_early", True)}
    cw = cov.reindex(M.players_bowl)
    rw = cw["role_bowl"].map({r: i for i, r in enumerate(ROLES_BOWL)}).fillna(0).astype(int).to_numpy()
    tw = cw[["bowl_tier_" + t for t in TIERS]].fillna(0).to_numpy()
    ew = cw["exp_bowl"].fillna(0).astype(int).to_numpy()
    prior_w = bowl_role[rw] + tw[:, 1:] @ bowl_tier[1:] + M.blk("bowl_exp")[ew]
    BOWL = {"b": M.blk("bowl") + prior_w, "pp": M.blk("bowl_pp"), "de": M.blk("bowl_death"),
            "lh": M.blk("bowl_lhb"), "prior": prior_w,
            "sd_b": M.blk("bowl", True), "sd_pp": M.blk("bowl_pp", True), "sd_de": M.blk("bowl_death", True),
            "sd_lh": M.blk("bowl_lhb", True)}
    st = styles.reindex(M.players_bowl)
    BOWL["sub"] = st["bowl_subtype"].fillna("pace_U").map({s: i for i, s in enumerate(SUBTYPES)}).to_numpy()
    BOWL["spin"] = st["bowl_group"].eq("spin").to_numpy()
    BAT["lhb"] = styles.reindex(M.players_bat)["bat_hand"].eq("L").to_numpy()
    # priors for players the model has never seen: role mean, IPL tier, least-experienced bucket
    priors_bat = {r: bat_role[i] + M.blk("bat_exp")[0] for i, r in enumerate(ROLES_BAT)}
    priors_bowl = {r: bowl_role[i] + M.blk("bowl_exp")[0] for i, r in enumerate(ROLES_BOWL)}
    return BAT, BOWL, priors_bat, priors_bowl


# %% reference sample and term substitution


class RefSample:
    """A set of real deliveries whose logits we can re-evaluate with a different batter or bowler."""

    def __init__(self, M, f, cov, BAT, BOWL):
        self.M, self.BAT, self.BOWL = M, BAT, BOWL
        D, X = build_design(f, cov, *M.idx)
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
        self.bterm_actual = self._bterm_rows(self.bi, self.lhb)
        self.wterm_actual = self._wterm_rows(self.wi, self.sub, self.spin)

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
        return self.eta[r] - self.bterm_actual[r] + t + float(lhb) * lterm

    def eta_with_bowler(self, vecs, sub, spin, rows=None):
        r = slice(None) if rows is None else rows
        ph, lhb = self.ph[r], self.lhb[r]
        t = (vecs["b"] + vecs["pp"] * (ph == 0)[:, None] + vecs["de"] * (ph == 2)[:, None]
             + vecs["lh"] * lhb[:, None]) + self.SUB[sub] + self.SUBL[sub] * lhb[:, None] + self._subph(np.full(len(ph), sub), ph)
        bi = np.maximum(self.bi[r], 0)
        spterm = np.where((self.bi[r] >= 0)[:, None], self.BAT["sp"][bi], 0) + np.where((self.vi[r] >= 0)[:, None], self.VSP[np.maximum(self.vi[r], 0)], 0)
        t = t + float(spin) * spterm
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
    BAT, BOWL, pri_b, pri_w = folded_players(M, cov, styles)
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
            # posterior uncertainty: draw the player's own coefficients
            nd = 30
            dr = {k: vec[k][None] + rng.standard_normal((nd, K)) * BAT["sd_" + k][i][None] * (np.arange(K) != REF)
                  for k in vec}
            ets = np.stack([R.eta_with_batter({k: dr[k][d] for k in dr}, lh, sub_rows) for d in range(nd)])
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
    write_sim_params(M, BAT, BOWL, pri_b, pri_w, ex, pool, venues, styles, names)
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
    disp = mm.groupby("venue")["venue_raw"].agg(lambda s: s.value_counts().index[0])
    city = mm.groupby("venue")["city"].agg(lambda s: s.value_counts().index[0] if len(s.dropna()) else "")
    rng = np.random.default_rng(1)
    sub = rng.choice(len(R.ph), size=min(6000, len(R.ph)), replace=False)
    rows = []
    for v, i in M.venue_pos.items():
        if v not in cnt.index or cnt.loc[v, "last"] < pd.Timestamp("2018-01-01") or cnt.loc[v, "matches"] < 5:
            continue
        e = eta0 + VB[i] + VI[i] * inn2[:, None] + VS[i] * R.spin[:, None]
        P = softmax(e)
        r = dict(venue=v, name=disp.get(v, v), city=city.get(v, ""), matches=int(cnt.loc[v, "matches"]),
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


# %% sim params export


def write_sim_params(M, BAT, BOWL, pri_b, pri_w, ex, pool, venues, styles, names):
    base = M.base_table()
    cs_lab = M.blocks["cs"][1]
    cs = M.blk("cs")
    env = {}
    for lab in cs_lab:
        if lab.startswith("IPL|"):
            env[lab] = r3(cs[cs_lab.index(lab)])
    recent = [l for l in cs_lab if l.startswith("IPL|") and l.split("|")[1] in IPL_RECENT]
    env["IPL|2024-26"] = r3(np.mean([cs[cs_lab.index(l)] for l in recent], axis=0))
    bats, bowls = {}, {}
    for pid in pool:
        if pid in M.bat_pos:
            i = M.bat_pos[pid]
            bats[pid] = {"b": r3(BAT["b"][i]), "pp": r3(BAT["pp"][i]), "de": r3(BAT["de"][i]),
                         "sp": r3(BAT["sp"][i]), "ea": r3(BAT["ea"][i]), "hand": "L" if BAT["lhb"][i] else "R"}
        if pid in M.bowl_pos:
            j = M.bowl_pos[pid]
            bowls[pid] = {"b": r3(BOWL["b"][j]), "pp": r3(BOWL["pp"][j]), "de": r3(BOWL["de"][j]),
                          "lh": r3(BOWL["lh"][j]), "sub": SUBTYPES[int(BOWL["sub"][j])], "spin": int(bool(BOWL["spin"][j]))}
    VB, VI, VS = M.blk("venue"), M.blk("venue_i2"), M.blk("venue_spin")
    ven = {}
    for v in venues["venue"]:
        i = M.venue_pos[v]
        ven[v] = {"base": r3(VB[i]), "i2": r3(VI[i]), "spin": r3(VS[i])}
    z = [0.0] * K
    params = {
        "version": 1, "classes": CLASSES, "ref_class": REF,
        "base": r3(base.ravel()), "base_shape": [2, 20, 8, K],
        "bf": r3(M.blk("bf").ravel()), "bf_shape": [3, 9, K], "bf_edges": BF_EDGES[:-1], "bf_labels": BF_LABELS,
        "early_bf": EARLY_BF,
        "chase": r3(M.blk("chase").ravel()), "chase_shape": [3, 8, K], "rrr_edges": RRR_EDGES[1:-1],
        "rrr_labels": RRR_LABELS,
        "sub": {s: r3(M.blk("sub")[i]) for i, s in enumerate(SUBTYPES)},
        "sub_lhb": {s: r3(M.blk("sub_lhb")[i]) for i, s in enumerate(SUBTYPES)},
        "sub_phase": {s: [r3(M.blk("sub_ph")[i * 3 + 0]), [0.0] * K, r3(M.blk("sub_ph")[i * 3 + 2])]
                      for i, s in enumerate(SUBTYPES)},
        "env": env, "default_env": "IPL|2026",
        "venues": ven, "venue_neutral": {"base": z, "i2": z, "spin": z},
        "batters": bats, "bowlers": bowls,
        "batter_priors": {r: {"b": r3(v), "pp": z, "de": z, "sp": z, "ea": z, "hand": "R"} for r, v in pri_b.items()},
        "bowler_priors": {r: {"b": r3(v), "pp": z, "de": z, "lh": z, "sub": "spin_U" if r.startswith("spin") else "pace_U",
                              "spin": int(r.startswith("spin"))} for r, v in pri_w.items()},
        "extras": ex,
    }
    (EXPORT / "sim_params.json").write_text(json.dumps(params, separators=(",", ":")))


if __name__ == "__main__":
    main()
