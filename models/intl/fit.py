"""Joint penalised multinomial logit for Test and ODI deliveries.

Same machinery as the T20 model (models/ipl/fit.py: sparse design, numba kernels, L-BFGS, ridge penalties,
random-walk season terms), with the blocks an international format needs: host-country environment, home
advantage, team-level priors, the other format's record, and for Tests the state of a five-day match
(ball age, pitch wear, lead, target, time left, spell length).
"""
# %% imports
import sys
import time

import numpy as np
import pandas as pd
import scipy.sparse as sp

from models.intl.config import (AGE_LABELS, CLASSES, FORMATS, K, LEAD3_EDGES, MO_EDGES, NEED4_EDGES, REF, REM4_EDGES,
                                ROLES_BAT, ROLES_BOWL, RR4_EDGES, RRR_EDGES, SPELL_EDGES, SUBTYPES, TYPES6)
from models.ipl.fit import Design, Fitter, predict_eta, probs_from_eta, weights  # noqa: F401  (re-exported)

KM = K - 1
RW_BLOCKS = {"cs": 1, "cs_spin": 1, "gs": 1, "gs_ph": 2, "gs_spin": 1}   # block -> columns per season label
XF_LEVELS = 4


# %% design


def indices(f):
    players_bat = np.sort(f["batter"].unique())
    players_bowl = np.sort(f["bowler"].unique())
    venues = sorted(f["venue"].astype(str).unique())
    comps = sorted(f["country"].astype(str).unique())
    comp_seasons = sorted(f["comp_season"].astype(str).unique())
    years = sorted(f["year"].astype(str).unique())
    teams = sorted(set(f["bat_team"].astype(str).unique()) | set(f["bowl_team"].astype(str).unique()))
    return dict(bat=players_bat, bowl=players_bowl, venues=venues, comps=comps, comp_seasons=comp_seasons, years=years,
                teams=teams)


def build_design(f, idx, fmt, lam):
    """Design registry and CSR matrix for frame f. Optional blocks are on when their penalty key is in lam."""
    D = Design()
    n = len(f)
    ar = np.arange(n, dtype=np.int64)
    rows, cols, vals = [], [], []

    def put(name, ix, mask=None, v=None):
        o = D.off(name)
        ix = np.asarray(ix, dtype=np.int64)
        ok = ix >= 0 if mask is None else (mask & (ix >= 0))
        rows.append(ar[ok])
        cols.append(o + ix[ok])
        vals.append(np.ones(int(ok.sum()), np.float32) if v is None else np.asarray(v, np.float32)[ok])

    def cat(col, labels):
        return f[col].astype(str).map({c: i for i, c in enumerate(labels)}).fillna(-1).to_numpy().astype(np.int64)

    ni, nb = fmt.n_inn, fmt.n_ovb
    inn = f["inn"].to_numpy().astype(np.int64) - 1
    ovb = f["ovb"].to_numpy().astype(np.int64)
    ph = f["phase"].to_numpy().astype(np.int64)
    wk = f["wk_b"].to_numpy().astype(np.int64)
    bfb = f["bf_b"].to_numpy().astype(np.int64)
    spin = f["bowl_spin"].to_numpy().astype(bool)
    lhb = (f["bat_hand"].astype(str) == "L").to_numpy()
    # ---- match situation
    D.add("io", [f"i{i + 1}_o{o}" for i in range(ni) for o in range(nb)], "l0")
    put("io", inn * nb + ovb)
    D.add("ipw", [f"i{i + 1}_p{p}_w{w}" for i in range(ni) for p in range(3) for w in range(10)], "l0")
    put("ipw", inn * 30 + ph * 10 + wk)
    D.add("cell", [f"i{i + 1}_o{o}_w{w}" for i in range(ni) for o in range(nb) for w in range(10)], "cell")
    put("cell", (inn * nb + ovb) * 10 + wk)
    nbf = len(fmt.bf_edges)
    D.add("bf", [f"p{p}_bf{b}" for p in range(3) for b in range(nbf)], "l0")
    put("bf", ph * nbf + bfb)
    if fmt.key == "odi":
        nr = len(RRR_EDGES) - 1
        rrr = f["rrr_b"].to_numpy().astype(np.int64)
        D.add("chase", [f"p{p}_rrr{r}" for p in range(3) for r in range(nr)], "l0")
        put("chase", np.where(rrr >= 0, ph * nr + rrr, -1))
        if "chase_w" in lam:   # chase pressure x wickets in hand (1-3, 4-6, 7-10)
            D.add("chase_w", [f"p{p}_rrr{r}_wih{w}" for p in range(3) for r in range(nr) for w in range(3)], "chase_w")
            put("chase_w", np.where(rrr >= 0, (ph * nr + rrr) * 3 + f["wih_b"].to_numpy(), -1))
        if "pp_old" in lam:    # batting / fielding powerplays of the 2005-2015 rules (never simulated)
            pt = f["pp_type"].to_numpy().astype(np.int64)
            D.add("pp_old", ["batting_pp", "fielding_pp"], "pp_old")
            put("pp_old", np.where(pt >= 2, pt - 2, -1), mask=f["over"].to_numpy() >= 10)
    else:
        nm = len(MO_EDGES)
        mo = f["mo_b"].to_numpy().astype(np.int64)
        D.add("mo", [f"mo{k}" for k in range(nm)], "sit")
        put("mo", mo)
        D.add("mo_spin", [f"mo{k}_spin" for k in range(nm)], "sit")
        put("mo_spin", mo, mask=spin)
        wkg = f["wkg"].to_numpy().astype(np.int64)
        nl, nn = len(LEAD3_EDGES) - 1, len(NEED4_EDGES) - 1
        l3 = f["lead3_b"].to_numpy().astype(np.int64)
        D.add("lead3", [f"lead{b}_wk{g}" for b in range(nl) for g in range(3)], "sit")
        put("lead3", np.where(l3 >= 0, l3 * 3 + wkg, -1))
        p12 = f["pos12_b"].to_numpy().astype(np.int64)
        D.add("pos12", [f"pos{b}_wk{g}" for b in range(10) for g in range(3)], "sit")
        put("pos12", np.where(p12 >= 0, p12 * 3 + wkg, -1))
        n4 = f["need4_b"].to_numpy().astype(np.int64)
        D.add("need4", [f"need{b}_wk{g}" for b in range(nn) for g in range(3)], "sit")
        put("need4", np.where(n4 >= 0, n4 * 3 + wkg, -1))
        nrr = (len(RR4_EDGES) - 1) * (len(REM4_EDGES) - 1)
        D.add("rr4", [f"rr{b}" for b in range(nrr)], "sit")
        put("rr4", f["rr4_b"].to_numpy())
        ns = len(SPELL_EDGES)
        D.add("spell", [f"{g}_sp{k}" for g in ("pace", "spin") for k in range(ns)], "sit")
        put("spell", spin.astype(np.int64) * ns + f["spell_b"].to_numpy())
        # a recognised batter left with the tail changes his game
        rb_row = f["role_bat_row"].to_numpy().astype(np.int64)
        D.add("tail", ["wk7", "wk8", "wk9"], "sit")
        put("tail", np.where((wk >= 7) & (rb_row <= 2), wk - 7, -1))
    # ---- bowling type
    sub = cat("bowl_subtype", SUBTYPES)
    D.add("sub", SUBTYPES, "l0")
    put("sub", sub)
    D.add("sub_lhb", [s + "_vsLHB" for s in SUBTYPES], "l0")
    put("sub_lhb", sub, mask=lhb)
    D.add("sub_ph", [f"{s}_p{p}" for s in SUBTYPES for p in range(3)], "cov")
    put("sub_ph", np.where(ph != 1, sub * 3 + ph, -1))
    # ---- environment: global year, host country, host country x season (random walks), venue
    yi = cat("year", idx["years"])
    D.add("gs", idx["years"], "gs")
    put("gs", yi)
    D.add("gs_ph", [f"{y}_p{p}" for y in idx["years"] for p in (0, 2)], "gs")
    put("gs_ph", np.where(ph != 1, yi * 2 + (ph == 2), -1))
    D.add("gs_spin", [f"{y}_spin" for y in idx["years"]], "gs")
    put("gs_spin", yi, mask=spin)
    ci = cat("country", idx["comps"])
    D.add("comp", idx["comps"], "comp")
    put("comp", ci)
    D.add("comp_spin", [c + "_spin" for c in idx["comps"]], "comp")
    put("comp_spin", ci, mask=spin)
    D.add("comp_ph", [f"{c}_p{p}" for c in idx["comps"] for p in (0, 2)], "comp")
    put("comp_ph", np.where(ph != 1, ci * 2 + (ph == 2), -1))
    csi = cat("comp_season", idx["comp_seasons"])
    D.add("cs", idx["comp_seasons"], "cs")
    put("cs", csi)
    D.add("cs_spin", [c + "_spin" for c in idx["comp_seasons"]], "cs")
    put("cs_spin", csi, mask=spin)
    vi = cat("venue", idx["venues"])
    late = inn >= (1 if fmt.key == "odi" else 2)   # ODI: the chase; Test: third and fourth innings
    D.add("venue", idx["venues"], "venue")
    put("venue", vi)
    D.add("venue_late", idx["venues"], "venue2")
    put("venue_late", vi, mask=late)
    D.add("venue_spin", idx["venues"], "venue2")
    put("venue_spin", vi, mask=spin)
    # ---- home advantage
    bh, wh = f["bat_home"].to_numpy(), f["bowl_home"].to_numpy()
    if fmt.key == "test":
        # Tests are almost never played on neutral ground, so a batting-home and a bowling-home term cannot be told
        # apart from the intercept (their sum is 1 on nearly every ball). One signed home edge instead: +1 when
        # the batting side is at home, -1 when the bowling side is, and a neutral ground sits half-way.
        edge = bh.astype(np.float32) - wh.astype(np.float32)
        D.add("ha", ["home_edge", "home_edge_spin"], "l0")
        put("ha", np.zeros(n, np.int64), mask=edge != 0, v=edge)
        put("ha", np.ones(n, np.int64), mask=(edge != 0) & spin, v=edge)
    else:
        D.add("ha", ["bat_home", "bowl_home", "bat_home_spin", "bowl_home_spin"], "l0")
        put("ha", np.zeros(n, np.int64), mask=bh)
        put("ha", np.ones(n, np.int64), mask=wh)
        put("ha", np.full(n, 2), mask=bh & spin)
        put("ha", np.full(n, 3), mask=wh & spin)
    # ---- priors: role, experience by role, age, team, the other format's record
    rb = f["role_bat_row"].to_numpy().astype(np.int64)
    rw = f["role_bowl_row"].to_numpy().astype(np.int64)
    ne = len(fmt.exp_edges)
    D.add("bat_role", ROLES_BAT, "cov")
    put("bat_role", rb)
    D.add("bowl_role", ROLES_BOWL, "cov")
    put("bowl_role", rw)
    D.add("bat_exp", [f"{r}_e{e}" for r in ROLES_BAT for e in range(ne)], "cov")
    put("bat_exp", rb * ne + f["exp_bat_row"].to_numpy())
    D.add("bowl_exp", [f"{r}_e{e}" for r in ROLES_BOWL for e in range(ne)], "cov")
    put("bowl_exp", rw * ne + f["exp_bowl_row"].to_numpy())
    na = len(AGE_LABELS)
    D.add("bat_age", AGE_LABELS, "cov")
    put("bat_age", f["age_bat_b"].to_numpy())
    D.add("bowl_age", [f"{g}_{a}" for g in ("pace", "spin") for a in AGE_LABELS], "cov")
    put("bowl_age", spin.astype(np.int64) * na + f["age_bowl_b"].to_numpy())
    D.add("bat_team", idx["teams"], "team")
    put("bat_team", cat("bat_team", idx["teams"]))
    D.add("bowl_team", idx["teams"], "team")
    put("bowl_team", cat("bowl_team", idx["teams"]))
    if "xf" in lam:
        for pre, name in (("xb", "bat_xf"), ("xw", "bowl_xf")):
            D.add(name, [f"x{k}" for k in range(1, XF_LEVELS)] + ["rate_a", "rate_o"], "xf")
            xb = f[pre + "_b"].to_numpy().astype(np.int64)
            put(name, xb - 1)
            put(name, np.full(n, XF_LEVELS - 1), v=f[pre + "_a"].to_numpy())
            put(name, np.full(n, XF_LEVELS), v=f[pre + "_o"].to_numpy())
    # ---- players
    bi = pd.Series(np.arange(len(idx["bat"])), index=idx["bat"]).reindex(f["batter"].to_numpy()).fillna(-1).to_numpy().astype(np.int64)
    wi = pd.Series(np.arange(len(idx["bowl"])), index=idx["bowl"]).reindex(f["bowler"].to_numpy()).fillna(-1).to_numpy().astype(np.int64)
    early = f["bf_before"].to_numpy() < fmt.early_bf
    D.add("bat", idx["bat"], "bat")
    put("bat", bi)
    for s, msk in (("bat_pp", ph == 0), ("bat_death", ph == 2), ("bat_spin", spin), ("bat_early", early), ("bat_away", ~bh)):
        D.add(s, idx["bat"], "bat_split")
        put(s, bi, mask=msk)
    D.add("bowl", idx["bowl"], "bowl")
    put("bowl", wi)
    for s, msk in (("bowl_pp", ph == 0), ("bowl_death", ph == 2), ("bowl_lhb", lhb), ("bowl_away", ~wh)):
        D.add(s, idx["bowl"], "bowl_split")
        put(s, wi, mask=msk)
    ti = cat("bowl_subtype", TYPES6)
    D.add("bat_type", [f"{p}_{t}" for p in idx["bat"] for t in TYPES6], "bat_type")
    put("bat_type", np.where((bi >= 0) & (ti >= 0), bi * 6 + ti, -1))
    X = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, D.p), dtype=np.float32)
    return D, X


# %% fitter with random-walk blocks


def rw_pairs(blocks):
    """(previous, current) coefficient rows of consecutive labels in each random-walk block. cs / cs_spin: a
    host country's seasons (labels 'country|season' are sorted, so contiguous and in time order); gs*: years."""
    prev, cur, key = [], [], []
    for name, width in RW_BLOCKS.items():
        if name not in blocks:
            continue
        o, labels, pen = blocks[name]
        m = len(labels) // width
        if name.startswith("cs"):
            grp = [l.split("|")[0] for l in labels]
            i = np.array([k for k in range(1, m) if grp[k] == grp[k - 1]], dtype=np.int64)
        else:
            i = np.arange(1, m, dtype=np.int64)
        for k in range(width):
            prev.append(o + width * (i - 1) + k)
            cur.append(o + width * i + k)
            key += [pen] * len(i)
    return np.concatenate(prev), np.concatenate(cur), np.array(key)


class RWFitter(Fitter):
    """Fitter whose season blocks are penalised on differences between consecutive seasons (a random walk).
    The first season of each chain keeps its ridge penalty; later ones are tied to the season before."""

    def __init__(self, X, y, w, D, lam):
        super().__init__(X, y, w, D, lam)
        prev, cur, key = rw_pairs(D.blocks)
        self.pen[cur] = 0.0
        self.rw_l = np.array([lam["rw"] if k == "cs" else lam.get("rw_gs", lam["rw"]) for k in key])[:, None]
        self.rw_idx = (prev, cur)

    def fg(self, theta):
        from models.ipl.fit import _softmax_grad, _xtg, _xw
        W = theta.reshape(self.p, KM)
        X, Xc = self.X, self.Xc
        _xw(X.indptr, X.indices, X.data, W, self.eta)
        loss = _softmax_grad(self.eta, self.y, self.w, REF, self.G, self.Hb, False)
        _xtg(Xc.indptr, Xc.indices, Xc.data, self.G, self.gW)
        loss += 0.5 * np.sum(self.pen * W * W)
        g = self.gW + self.pen * W
        prev, cur = self.rw_idx
        d = W[cur] - W[prev]
        loss += 0.5 * np.sum(self.rw_l * d * d)
        np.add.at(g, cur, self.rw_l * d)
        np.add.at(g, prev, -self.rw_l * d)
        self.nit += 1
        return loss, g.ravel()

    def hessian_diag(self):
        hd = super().hessian_diag()
        prev, cur = self.rw_idx
        np.add.at(hd, cur, np.broadcast_to(self.rw_l, (len(cur), KM)))
        np.add.at(hd, prev, np.broadcast_to(self.rw_l, (len(prev), KM)))
        return hd


# %% fit helpers


def load(key):
    fmt = FORMATS[key]
    f = pd.read_parquet(fmt.proc / "frame.parquet")
    return f[~f["reduced"]].reset_index(drop=True)


def fit_model(f, fmt, lam, half_life, ref_date, idx=None, maxiter=500, tol=1e-7, W0=None, verbose=False):
    idx = idx or indices(f)
    w = weights(f["date"], ref_date, half_life)
    keep = w > 0.01
    fk = f[keep].reset_index(drop=True)
    D, X = build_design(fk, idx, fmt, lam)
    fitr = RWFitter(X, fk["y"].to_numpy(), w[keep], D, lam)
    t = time.time()
    if W0 is not None and W0.shape != (D.p, KM):
        W0 = None
    fitr.fit(W0=W0, maxiter=maxiter, tol=tol)
    if verbose:
        print(f"fit n={len(fk):,} p={D.p:,} iters={fitr.res.nit} {time.time() - t:.0f}s loss={fitr.res.fun:.1f}", flush=True)
    return fitr, D, idx


def map_env(train, test):
    """A host-country season the training data has not seen takes that country's latest training season, and an
    unseen year the latest training year: what a projection does."""
    last = train.sort_values("date").groupby("country", observed=True)["comp_season"].last().astype(str)
    seen = set(train["comp_season"].astype(str).unique())
    cs = test["comp_season"].astype(str)
    test = test.copy()
    test["comp_season"] = pd.Categorical([c if c in seen else last.get(c.split("|")[0], c) for c in cs])
    ymax = train["year"].astype(str).max()
    test["year"] = pd.Categorical(np.minimum(test["year"].astype(str).to_numpy(), ymax))
    return test


def logloss_rows(X, y, W):
    P = probs_from_eta(predict_eta(X, W))
    return -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1)), P


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "odi"
    fmt = FORMATS[key]
    f = load(key)
    fit_model(f, fmt, fmt.default_lam, fmt.default_half_life, f["date"].max(), maxiter=40, verbose=True)
