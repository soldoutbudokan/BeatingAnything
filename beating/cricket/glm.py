"""Penalized multinomial logit with random-effect groups.

eta[i, 0] = 0 and, for classes 1..K-1,
eta[i, 1:] = intercept + sum_g (w_g[i] * theta_g[idx_g[i]] + w2_g[i] * theta_g[idx2_g[i]]) @ basis_g
           + X[i] @ C
Each group has a Gaussian prior N(0, sigma_g^2) on every entry of theta_g; the dense
coefficients C share sigma_dense. Rows carry observation weights (time decay). An
index of -1 contributes nothing for that row. A basis of shape (d, K-1) restricts a
group to a d-dimensional subspace, e.g. a single row selecting the wicket class.

The objective is the weighted negative log-likelihood plus the Gaussian penalties,
minimised by L-BFGS. Groups are packed into sparse one-hot matrices (one matrix for
all full-dimensional groups, one per basis group), split into row chunks and spread
across forked worker processes that inherit them copy-on-write.
Prior SDs can be re-estimated by approximate empirical Bayes:
sigma_g^2 = mean(theta^2 + posterior variance) over levels that carry data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import multiprocessing as mp
import os
import time

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize


@dataclass
class Group:
    name: str
    index: np.ndarray
    n_levels: int
    sigma: float
    weight: np.ndarray | None = None
    index2: np.ndarray | None = None
    weight2: np.ndarray | None = None
    basis: np.ndarray | None = None
    labels: list | None = None
    fixed_sigma: bool = False

    def dim(self, k1: int) -> int:
        return k1 if self.basis is None else self.basis.shape[0]


@dataclass
class Design:
    y: np.ndarray
    n_classes: int
    groups: list[Group]
    weights: np.ndarray | None = None
    dense: np.ndarray | None = None
    dense_names: list[str] = field(default_factory=list)
    sigma_dense: float = 1.0
    sigma_intercept: float = 10.0

    @property
    def n(self) -> int:
        return len(self.y)


class _Layout:
    def __init__(self, design: Design):
        k1 = design.n_classes - 1
        self.k1 = k1
        self.slices = {"intercept": slice(0, k1)}
        self.shapes = {"intercept": (k1,)}
        pos = k1
        for g in design.groups:
            size = g.n_levels * g.dim(k1)
            self.slices[g.name] = slice(pos, pos + size)
            self.shapes[g.name] = (g.n_levels, g.dim(k1))
            pos += size
        p = 0 if design.dense is None else design.dense.shape[1]
        self.slices["dense"] = slice(pos, pos + p * k1)
        self.shapes["dense"] = (p, k1)
        self.size = pos + p * k1

    def unpack(self, theta: np.ndarray) -> dict[str, np.ndarray]:
        return {k: theta[s].reshape(self.shapes[k]) for k, s in self.slices.items()}


def _one_hot(groups: list[Group], rows: slice) -> sp.csr_matrix:
    """Sparse matrix whose columns are the concatenated levels of `groups`."""
    n = rows.stop - rows.start
    cols, vals, rid = [], [], []
    offset = 0
    base = np.arange(n, dtype=np.int64)
    for g in groups:
        for idx_arr, w_arr in ((g.index, g.weight), (g.index2, g.weight2)):
            if idx_arr is None:
                continue
            idx = idx_arr[rows]
            keep = idx >= 0
            w = np.ones(n) if w_arr is None else w_arr[rows].astype(np.float64)
            keep &= w != 0
            rid.append(base[keep])
            cols.append(idx[keep].astype(np.int64) + offset)
            vals.append(w[keep])
        offset += g.n_levels
    m = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rid), np.concatenate(cols))),
                      shape=(n, offset))
    m.sum_duplicates()
    return m


@dataclass
class _Chunk:
    rows: slice
    full: sp.csr_matrix | None
    full_t: sp.csc_matrix | None
    basis: list[tuple[int, sp.csr_matrix, sp.csc_matrix]]


class _Prepared:
    def __init__(self, design: Design, chunk: int = 500_000):
        self.design = design
        self.layout = _Layout(design)
        self.full_groups = [g for g in design.groups if g.basis is None]
        self.basis_groups = [(i, g) for i, g in enumerate(design.groups) if g.basis is not None]
        self.chunks = []
        for lo in range(0, design.n, chunk):
            rows = slice(lo, min(lo + chunk, design.n))
            full = _one_hot(self.full_groups, rows) if self.full_groups else None
            basis = []
            for i, g in self.basis_groups:
                m = _one_hot([g], rows)
                basis.append((i, m, m.T))
            self.chunks.append(_Chunk(rows, full, None if full is None else full.T, basis))

    def stack_full(self, params: dict) -> np.ndarray:
        return np.vstack([params[g.name] for g in self.full_groups]) if self.full_groups else None

    def eta(self, params: dict, c: _Chunk, full_theta: np.ndarray | None) -> np.ndarray:
        """Linear predictor for classes 1..K-1 (class 0 is the implicit zero)."""
        d = self.design
        n = c.rows.stop - c.rows.start
        inner = c.full @ full_theta if c.full is not None else np.zeros((n, d.n_classes - 1))
        inner += params["intercept"]
        for (i, m, _), (_, g) in zip(c.basis, self.basis_groups):
            inner += (m @ params[g.name]) @ g.basis
        if d.dense is not None:
            inner += d.dense[c.rows] @ params["dense"]
        return inner

    def loss_grad(self, theta: np.ndarray, chunk_ids) -> tuple[float, np.ndarray]:
        d = self.design
        lay = self.layout
        params = lay.unpack(theta)
        full_theta = self.stack_full(params)
        grad = np.zeros(lay.size)
        gp = lay.unpack(grad)
        full_grad = np.zeros_like(full_theta) if full_theta is not None else None
        loss = 0.0
        for ci in chunk_ids:
            c = self.chunks[ci]
            eta = self.eta(params, c, full_theta)
            prob, lse = _softmax(eta)
            y = d.y[c.rows]
            w = np.ones(len(y)) if d.weights is None else d.weights[c.rows].astype(np.float64)
            pos = y > 0
            picked = np.zeros(len(y))
            picked[pos] = eta[pos, y[pos] - 1]
            loss += float(np.dot(w, lse - picked))
            prob[pos, y[pos] - 1] -= 1.0
            prob *= w[:, None]
            gr = prob
            gp["intercept"] += gr.sum(axis=0)
            if c.full is not None:
                full_grad += c.full_t @ gr
            for (i, m, mt), (_, g) in zip(c.basis, self.basis_groups):
                gp[g.name] += mt @ (gr @ g.basis.T)
            if d.dense is not None:
                gp["dense"] += d.dense[c.rows].T @ gr
        if full_grad is not None:
            pos = 0
            for g in self.full_groups:
                gp[g.name] += full_grad[pos:pos + g.n_levels]
                pos += g.n_levels
        return loss, grad


def _softmax(eta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Probabilities of classes 1..K-1 and log-sum-exp including the zero class.

    Penalized linear predictors stay far below exp overflow; the clip only guards."""
    e = np.exp(np.minimum(eta, 60.0))
    s = 1.0 + e.sum(axis=1)
    e /= s[:, None]
    return e, np.log(s)


def _full_proba(eta: np.ndarray) -> np.ndarray:
    p1 = _softmax(eta)[0]
    return np.column_stack([1.0 - p1.sum(axis=1), p1])


_WORK: dict = {}


def _worker(args):
    theta, chunk_ids = args
    return _WORK["prep"].loss_grad(theta, chunk_ids)


def _penalty(design: Design, layout: _Layout, theta: np.ndarray) -> tuple[float, np.ndarray]:
    grad = np.zeros(layout.size)
    pen = 0.0
    sigmas = [("intercept", design.sigma_intercept)] + [(g.name, g.sigma) for g in design.groups]
    sigmas.append(("dense", design.sigma_dense))
    for name, sigma in sigmas:
        s = layout.slices[name]
        v = theta[s]
        pen += 0.5 * float(v @ v) / sigma**2
        grad[s] = v / sigma**2
    return pen, grad


@dataclass
class FitResult:
    params: dict[str, np.ndarray]
    sigmas: dict[str, float]
    loss: float
    n_iter: int
    seconds: float
    converged: bool
    message: str


def fit(design: Design, theta0: np.ndarray | None = None, *, processes: int | None = None,
        maxiter: int = 400, tol: float = 1e-8, verbose: bool = False,
        prepared: _Prepared | None = None) -> FitResult:
    prep = prepared or _Prepared(design)
    layout = prep.layout
    theta = np.zeros(layout.size) if theta0 is None else np.asarray(theta0, dtype=np.float64).copy()
    if theta0 is None:
        counts = np.bincount(design.y, weights=design.weights, minlength=design.n_classes) + 0.5
        theta[layout.slices["intercept"]] = np.log(counts[1:] / counts[0])
    processes = max(1, min(processes or (os.cpu_count() or 1), len(prep.chunks)))
    parts = [list(range(i, len(prep.chunks), processes)) for i in range(processes)]
    total_w = float(design.n if design.weights is None else design.weights.sum())
    t0 = time.time()
    calls = [0]
    pool = None
    if processes > 1:
        _WORK["prep"] = prep
        pool = mp.get_context("fork").Pool(processes)

    def objective(th):
        calls[0] += 1
        if pool is None:
            loss, grad = prep.loss_grad(th, range(len(prep.chunks)))
        else:
            res = pool.map(_worker, [(th, p) for p in parts])
            loss = sum(r[0] for r in res)
            grad = np.sum([r[1] for r in res], axis=0)
        pen, pgrad = _penalty(design, layout, th)
        if verbose and calls[0] % 25 == 0:
            print(f"  eval {calls[0]}: nll/w={loss / total_w:.6f} pen/w={pen / total_w:.6f} "
                  f"{time.time() - t0:.0f}s", flush=True)
        return (loss + pen) / total_w, (grad + pgrad) / total_w

    try:
        res = minimize(objective, theta, jac=True, method="L-BFGS-B",
                       options={"maxiter": maxiter, "maxcor": 30, "ftol": tol, "gtol": 1e-7})
    finally:
        if pool is not None:
            pool.close()
            pool.join()
            _WORK.clear()
    params = layout.unpack(res.x.copy())
    sigmas = {g.name: g.sigma for g in design.groups}
    sigmas["dense"] = design.sigma_dense
    return FitResult(params, sigmas, float(res.fun), int(res.nit), time.time() - t0,
                     bool(res.success), str(res.message))


def flat(design: Design, params: dict[str, np.ndarray]) -> np.ndarray:
    """Pack params into a parameter vector; missing or mis-shaped entries start at zero."""
    layout = _Layout(design)
    theta = np.zeros(layout.size)
    for k, s in layout.slices.items():
        if k in params and np.size(params[k]) == s.stop - s.start:
            theta[s] = np.asarray(params[k]).ravel()
    return theta


def predict_proba(design: Design, params: dict[str, np.ndarray], prepared: _Prepared | None = None) -> np.ndarray:
    prep = prepared or _Prepared(design)
    full_theta = prep.stack_full(params)
    out = np.empty((design.n, design.n_classes), dtype=np.float32)
    for c in prep.chunks:
        out[c.rows] = _full_proba(prep.eta(params, c, full_theta))
    return out


def log_loss(design: Design, params: dict[str, np.ndarray], prepared: _Prepared | None = None) -> float:
    """Weighted mean multinomial log loss (natural log)."""
    prep = prepared or _Prepared(design)
    full_theta = prep.stack_full(params)
    total = 0.0
    for c in prep.chunks:
        eta = prep.eta(params, c, full_theta)
        lse = _softmax(eta)[1]
        y = design.y[c.rows]
        w = np.ones(len(y)) if design.weights is None else design.weights[c.rows].astype(np.float64)
        picked = np.zeros(len(y))
        pos = y > 0
        picked[pos] = eta[pos, y[pos] - 1]
        total += float(np.dot(w, lse - picked))
    return total / float(design.n if design.weights is None else design.weights.sum())


def hessian_diag(design: Design, params: dict[str, np.ndarray],
                 prepared: _Prepared | None = None) -> dict[str, np.ndarray]:
    """Diagonal of the data Hessian for each group's parameters (prior excluded)."""
    prep = prepared or _Prepared(design)
    k1 = design.n_classes - 1
    full_theta = prep.stack_full(params)
    out = {g.name: np.zeros((g.n_levels, g.dim(k1))) for g in design.groups}
    eye = np.eye(k1)
    for c in prep.chunks:
        prob = _softmax(prep.eta(params, c, full_theta))[0]
        w = np.ones(len(prob)) if design.weights is None else design.weights[c.rows].astype(np.float64)
        # Curvature along basis direction b: sum_k b_k^2 p_k - (b . p)^2.
        if c.full is not None:
            sq = c.full_t.multiply(c.full_t)
            hc = sq @ ((prob - prob**2) * w[:, None])
            pos = 0
            for g in prep.full_groups:
                out[g.name] += hc[pos:pos + g.n_levels]
                pos += g.n_levels
        for (i, m, mt), (_, g) in zip(c.basis, prep.basis_groups):
            b = g.basis if g.basis is not None else eye
            curv = (prob @ (b.T ** 2)) - (prob @ b.T) ** 2
            out[g.name] += mt.multiply(mt) @ (curv * w[:, None])
    return out


def update_sigmas(design: Design, params: dict[str, np.ndarray], *, min_sigma: float = 0.005,
                  max_sigma: float = 3.0, prepared: _Prepared | None = None) -> dict[str, float]:
    """Approximate empirical-Bayes prior SDs; levels without data are ignored."""
    hdiag = hessian_diag(design, params, prepared)
    new = {}
    for g in design.groups:
        h = hdiag[g.name]
        used = h.sum(axis=1) > 0
        if g.fixed_sigma or not used.any():
            new[g.name] = g.sigma
            continue
        th = params[g.name][used]
        post_var = 1.0 / (h[used] + 1.0 / g.sigma**2)
        new[g.name] = float(np.clip(np.sqrt(np.mean(th**2 + post_var)), min_sigma, max_sigma))
    return new


def fit_eb(design: Design, rounds: int = 3, theta0: np.ndarray | None = None, verbose: bool = False,
           **kw) -> FitResult:
    """Alternate penalized fits with empirical-Bayes sigma updates, warm-starting each round."""
    prep = _Prepared(design)
    result = fit(design, theta0, verbose=verbose, prepared=prep, **kw)
    for r in range(rounds):
        sig = update_sigmas(design, result.params, prepared=prep)
        if verbose:
            print(f"round {r + 1} sigmas: " + ", ".join(f"{k}={v:.3f}" for k, v in sig.items()), flush=True)
        for g in design.groups:
            g.sigma = sig[g.name]
        result = fit(design, flat(design, result.params), verbose=verbose, prepared=prep, **kw)
    return result
