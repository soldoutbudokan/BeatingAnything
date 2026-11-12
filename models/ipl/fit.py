"""Joint penalised multinomial logit: context baseline + league/season/venue + batter/bowler effects.

Every term is an additive logit offset on 10 outcome classes (r0 = dot ball is the reference), so the
fitted model is a set of compact lookup tables the browser simulator can evaluate.
"""
# %% imports
import json
import time

import numba as nb
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import minimize

from models.ipl.config import CLASSES, K, PROC, REF, TIERS
from models.ipl.prep import SUBTYPES, EARLY_BF, EXP_LABELS

KM = K - 1
FREE = [k for k in range(K) if k != REF]

# %% numba kernels


@nb.njit(parallel=True, fastmath=True)
def _xw(indptr, indices, data, W, out):
    n = indptr.shape[0] - 1
    k = W.shape[1]
    for i in nb.prange(n):
        for c in range(k):
            out[i, c] = 0.0
        for jj in range(indptr[i], indptr[i + 1]):
            j = indices[jj]
            v = data[jj]
            for c in range(k):
                out[i, c] += v * W[j, c]


@nb.njit(parallel=True, fastmath=True)
def _xtg(indptr, indices, data, G, out):
    p = indptr.shape[0] - 1
    k = G.shape[1]
    for j in nb.prange(p):
        for c in range(k):
            out[j, c] = 0.0
        for ii in range(indptr[j], indptr[j + 1]):
            i = indices[ii]
            v = data[ii]
            for c in range(k):
                out[j, c] += v * G[i, c]


@nb.njit(parallel=True, fastmath=True)
def _softmax_grad(eta, y, w, ref, G, H, want_h):
    """eta: n x (K-1) free logits. Writes G = w*(P-Y) (free classes), returns weighted NLL."""
    n, km = eta.shape
    loss = np.zeros(n)
    for i in nb.prange(n):
        m = 0.0
        for c in range(km):
            if eta[i, c] > m:
                m = eta[i, c]
        s = np.exp(-m)
        for c in range(km):
            s += np.exp(eta[i, c] - m)
        yi = y[i]
        lse = m + np.log(s)
        for c in range(km):
            p = np.exp(eta[i, c] - lse)
            cls = c if c < ref else c + 1
            G[i, c] = w[i] * (p - (1.0 if cls == yi else 0.0))
            if want_h:
                H[i, c] = w[i] * p * (1 - p)
        if yi == ref:
            loss[i] = w[i] * lse
        else:
            cc = yi if yi < ref else yi - 1
            loss[i] = w[i] * (lse - eta[i, cc])
    return loss.sum()


def probs_from_eta(eta):
    full = np.insert(eta, REF, 0.0, axis=1)
    full -= full.max(axis=1, keepdims=True)
    e = np.exp(full)
    return e / e.sum(axis=1, keepdims=True)


# %% design matrix


class Design:
    """Column registry: block name -> (offset, labels, penalty key)."""

    def __init__(self):
        self.blocks = {}
        self.p = 0

    def add(self, name, labels, pen):
        self.blocks[name] = (self.p, list(labels), pen)
        self.p += len(labels)

    def off(self, name):
        return self.blocks[name][0]


def build_design(f, cov, players_bat, players_bowl, venues, comps, comp_seasons):
    """Returns design (registry) and COO pieces for the frame f."""
    D = Design()
    n = len(f)
    inn = f["innings"].to_numpy().astype(np.int64) - 1
    ov = f["over"].to_numpy().astype(np.int64)
    ph = f["phase"].to_numpy().astype(np.int64)
    wk = f["wk_b"].to_numpy().astype(np.int64)
    bfb = f["bf_b"].to_numpy().astype(np.int64)
    rrr = f["rrr_b"].to_numpy().astype(np.int64)
    rows, cols, vals = [], [], []
    ar = np.arange(n, dtype=np.int64)

    def put(name, idx, mask=None, v=None):
        o = D.off(name)
        if mask is None:
            mask = np.ones(n, bool)
        mask = mask & (idx >= 0)
        rows.append(ar[mask])
        cols.append(o + idx[mask])
        vals.append(np.ones(mask.sum(), np.float32) if v is None else v[mask].astype(np.float32))

    D.add("io", [f"i{i+1}_o{o+1}" for i in range(2) for o in range(20)], "l0")
    put("io", inn * 20 + ov)
    D.add("ipw", [f"i{i+1}_p{p}_w{w}" for i in range(2) for p in range(3) for w in range(8)], "l0")
    put("ipw", inn * 24 + ph * 8 + wk)
    D.add("cell", [f"i{i+1}_o{o+1}_w{w}" for i in range(2) for o in range(20) for w in range(8)], "cell")
    put("cell", inn * 160 + ov * 8 + wk)
    D.add("bf", [f"p{p}_bf{b}" for p in range(3) for b in range(9)], "l0")
    put("bf", ph * 9 + bfb)
    D.add("chase", [f"p{p}_rrr{r}" for p in range(3) for r in range(8)], "l0")
    put("chase", np.where(rrr >= 0, ph * 8 + rrr, -1))
    sub = f["bowl_subtype"].astype(str).map({s: i for i, s in enumerate(SUBTYPES)}).to_numpy().astype(np.int64)
    lhb = (f["bat_hand"].astype(str) == "L").to_numpy()
    D.add("sub", SUBTYPES, "l0")
    put("sub", sub)
    D.add("sub_lhb", [s + "_vsLHB" for s in SUBTYPES], "l0")
    put("sub_lhb", sub, mask=lhb)
    D.add("sub_ph", [f"{s}_p{p}" for s in SUBTYPES for p in range(3)], "cov")
    put("sub_ph", np.where(ph != 1, sub * 3 + ph, -1))  # middle overs are the reference phase
    cmap = {c: i for i, c in enumerate(comps)}
    D.add("comp", comps, "comp")
    put("comp", f["comp"].astype(str).map(cmap).fillna(-1).to_numpy().astype(np.int64))
    csmap = {c: i for i, c in enumerate(comp_seasons)}
    D.add("cs", comp_seasons, "cs")
    put("cs", f["comp_season"].astype(str).map(csmap).fillna(-1).to_numpy().astype(np.int64))
    vmap = {v: i for i, v in enumerate(venues)}
    vi = f["venue"].astype(str).map(vmap).fillna(-1).to_numpy().astype(np.int64)
    D.add("venue", venues, "venue")
    put("venue", vi)
    D.add("venue_i2", venues, "venue2")
    put("venue_i2", vi, mask=inn == 1)
    D.add("venue_spin", venues, "venue2")
    put("venue_spin", vi, mask=f["bowl_spin"].to_numpy())
    # hierarchical prior covariates
    roles_bat = ["open", "top", "middle", "lower"]
    roles_bowl = ["pace_part", "pace_reg", "pace_front", "spin_part", "spin_reg", "spin_front"]
    bat_ids = f["batter"].to_numpy()
    bowl_ids = f["bowler"].to_numpy()
    rb = cov["role_bat"].reindex(bat_ids).map({r: i for i, r in enumerate(roles_bat)}).fillna(3).to_numpy().astype(np.int64)
    rw = cov["role_bowl"].reindex(bowl_ids).map({r: i for i, r in enumerate(roles_bowl)}).fillna(0).to_numpy().astype(np.int64)
    D.add("bat_role", roles_bat, "cov")
    put("bat_role", rb)
    D.add("bowl_role", roles_bowl, "cov")
    put("bowl_role", rw)
    # experience prior, separately by role (a 20-ball opener is not a 20-ball tail-ender)
    ne = len(EXP_LABELS)
    eb = f["exp_bat_row"].to_numpy().astype(np.int64)    # experience at the time of the delivery
    ew = f["exp_bowl_row"].to_numpy().astype(np.int64)
    D.add("bat_exp", [f"{r}_{e}" for r in roles_bat for e in EXP_LABELS], "cov")
    put("bat_exp", rb * ne + eb)
    D.add("bowl_exp", [f"{r}_{e}" for r in roles_bowl for e in EXP_LABELS], "cov")
    put("bowl_exp", rw * ne + ew)
    D.add("bat_tier", TIERS, "cov")
    D.add("bowl_tier", TIERS, "cov")
    tb = cov[["bat_tier_" + t for t in TIERS]].reindex(bat_ids).fillna(0).to_numpy()
    tw = cov[["bowl_tier_" + t for t in TIERS]].reindex(bowl_ids).fillna(0).to_numpy()
    for t in range(len(TIERS)):
        if t == 0:
            continue  # ipl share is the reference
        put("bat_tier", np.full(n, t), mask=tb[:, t] > 0, v=tb[:, t])
        put("bowl_tier", np.full(n, t), mask=tw[:, t] > 0, v=tw[:, t])
    # players
    bmap = pd.Series(np.arange(len(players_bat)), index=players_bat)
    wmap = pd.Series(np.arange(len(players_bowl)), index=players_bowl)
    bi = bmap.reindex(bat_ids).fillna(-1).to_numpy().astype(np.int64)
    wi = wmap.reindex(bowl_ids).fillna(-1).to_numpy().astype(np.int64)
    D.add("bat", players_bat, "bat")
    put("bat", bi)
    for s, m in [("bat_pp", ph == 0), ("bat_death", ph == 2), ("bat_spin", f["bowl_spin"].to_numpy()),
                 ("bat_early", f["bf_before"].to_numpy() < EARLY_BF)]:
        D.add(s, players_bat, "bat_split")
        put(s, bi, mask=m)
    D.add("bowl", players_bowl, "bowl")
    put("bowl", wi)
    for s, m in [("bowl_pp", ph == 0), ("bowl_death", ph == 2), ("bowl_lhb", lhb)]:
        D.add(s, players_bowl, "bowl_split")
        put(s, wi, mask=m)
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    v = np.concatenate(vals)
    X = sp.csr_matrix((v, (r, c)), shape=(n, D.p), dtype=np.float32)
    return D, X


# %% fitter


class Fitter:
    def __init__(self, X, y, w, D, lam):
        self.X = X.tocsr()
        self.Xc = X.tocsc()
        self.y = y.astype(np.int64)
        self.w = w.astype(np.float64)
        self.D = D
        self.n, self.p = X.shape
        pen = np.zeros(self.p)
        for name, (o, labels, key) in D.blocks.items():
            pen[o:o + len(labels)] = lam[key]
        self.pen = pen
        self.eta = np.zeros((self.n, KM))
        self.G = np.zeros((self.n, KM))
        self.Hb = np.zeros((1, 1))
        self.gW = np.zeros((self.p, KM))
        self.nit = 0

    def fg(self, theta):
        W = theta.reshape(self.p, KM)
        X = self.X
        _xw(X.indptr, X.indices, X.data, W, self.eta)
        loss = _softmax_grad(self.eta, self.y, self.w, REF, self.G, self.Hb, False)
        Xc = self.Xc
        _xtg(Xc.indptr, Xc.indices, Xc.data, self.G, self.gW)
        loss += 0.5 * np.sum(self.pen[:, None] * W * W)
        g = self.gW + self.pen[:, None] * W
        self.nit += 1
        return loss, g.ravel()

    def fit(self, W0=None, maxiter=400, tol=1e-7):
        th0 = np.zeros(self.p * KM) if W0 is None else W0.ravel()
        res = minimize(self.fg, th0, jac=True, method="L-BFGS-B",
                       options=dict(maxiter=maxiter, maxcor=15, ftol=tol, gtol=1e-6))
        self.W = res.x.reshape(self.p, KM)
        self.res = res
        return self.W

    def hessian_diag(self):
        """Diagonal of the penalised Hessian -> Laplace posterior SDs."""
        X = self.X
        _xw(X.indptr, X.indices, X.data, self.W, self.eta)
        H = np.zeros((self.n, KM))
        _softmax_grad(self.eta, self.y, self.w, REF, self.G, H, True)
        Xc = self.Xc.copy()
        Xc.data = Xc.data ** 2
        hd = np.zeros((self.p, KM))
        _xtg(Xc.indptr, Xc.indices, Xc.data, H, hd)
        return hd + self.pen[:, None]


def predict_eta(X, W):
    X = X.tocsr()
    eta = np.zeros((X.shape[0], KM))
    _xw(X.indptr, X.indices, X.data, W, eta)
    return eta


def logloss(X, y, W):
    P = probs_from_eta(predict_eta(X, W))
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))))


# %% data prep helpers


def load():
    f = pd.read_parquet(PROC / "frame.parquet")
    f = f[~f["reduced"]].reset_index(drop=True)
    cov = pd.read_parquet(PROC / "covariates.parquet")
    return f, cov


def indices(f):
    players_bat = np.sort(f["batter"].unique())
    players_bowl = np.sort(f["bowler"].unique())
    venues = sorted(f["venue"].astype(str).unique())
    comps = sorted(c for c in f["comp"].astype(str).unique() if c != "IPL")
    comp_seasons = sorted(f["comp_season"].astype(str).unique())
    return players_bat, players_bowl, venues, comps, comp_seasons


def weights(dates, ref_date, half_life_years):
    age = (ref_date - dates).dt.days.to_numpy() / 365.25
    return np.power(0.5, np.clip(age, 0, None) / half_life_years)


DEFAULT_LAM = dict(l0=1.0, cov=2.0, cell=30.0, comp=2.0, cs=200.0, venue=300.0, venue2=600.0,
                   bat=150.0, bat_split=400.0, bowl=150.0, bowl_split=400.0)


def fit_model(f, cov, lam, half_life, ref_date, maxiter=400, idx=None, verbose=False, tol=1e-7):
    idx = idx or indices(f)
    w = weights(f["date"], ref_date, half_life)
    keep = w > 0.01
    fk = f[keep].reset_index(drop=True)
    D, X = build_design(fk, cov, *idx)
    fitr = Fitter(X, fk["y"].to_numpy(), w[keep], D, lam)
    t = time.time()
    fitr.fit(maxiter=maxiter, tol=tol)
    if verbose:
        print(f"fit n={len(fk):,} p={D.p:,} iters={fitr.res.nit} {time.time()-t:.0f}s loss={fitr.res.fun:.1f}")
    return fitr, D, idx


if __name__ == "__main__":
    f, cov = load()
    ref = f["date"].max()
    fitr, D, idx = fit_model(f, cov, DEFAULT_LAM, 2.5, ref, maxiter=60, verbose=True)
