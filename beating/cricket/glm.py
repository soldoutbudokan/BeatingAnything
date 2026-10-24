"""Penalized multinomial logit with random-effect groups.

eta[i, 0] = 0 and, for classes 1..K-1,
eta[i, 1:] = intercept + sum_g (w_g[i] * theta_g[idx_g[i]] + w2_g[i] * theta_g[idx2_g[i]]) @ basis_g
           + X[i] @ C + mask[i]
A group's levels carry Gaussian priors with one SD per dimension. An ordinary group
centres each level on its prior mean (zero by default); a random-walk group centres each
level on its predecessor (rw_prev), with the root levels centred on zero under
sigma_root. Rows carry observation weights (time decay). An index of -1 contributes
nothing for that row. A basis of shape (d, K-1) restricts a group to a d-dimensional
subspace, e.g. one row selecting the wicket class. Masks add -30 to a class on chosen
rows, making it impossible there (the same offset the simulators use).

The objective is the weighted negative log-likelihood plus the Gaussian penalties,
minimised by L-BFGS in a diagonally preconditioned parameterisation (scale from the
Hessian diagonal plus prior precision at the start point). Groups are packed into sparse
one-hot matrices, split into row chunks and spread across forked worker processes that
inherit them copy-on-write. Prior SDs are re-estimated by MacKay's empirical-Bayes
update sigma^2 = sum(delta^2) / sum(gamma), gamma = 1 - v / sigma^2, with v the
diagonal posterior variance, so weakly identified levels do not drag the scale down.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import multiprocessing as mp
import os
import time

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

MASK_OFFSET = -30.0


@dataclass
class Group:
    name: str
    index: np.ndarray
    n_levels: int
    sigma: float | np.ndarray
    weight: np.ndarray | None = None
    index2: np.ndarray | None = None
    weight2: np.ndarray | None = None
    basis: np.ndarray | None = None
    labels: list | None = None
    fixed_sigma: bool = False
    prior_mean: np.ndarray | None = None
    rw_prev: np.ndarray | None = None
    sigma_root: float | np.ndarray = 1.0

    def dim(self, k1: int) -> int:
        return k1 if self.basis is None else self.basis.shape[0]

    def sigma_vec(self, k1: int) -> np.ndarray:
        return np.broadcast_to(np.asarray(self.sigma, dtype=np.float64), (self.dim(k1),)).copy()

    def root_vec(self, k1: int) -> np.ndarray:
        return np.broadcast_to(np.asarray(self.sigma_root, dtype=np.float64), (self.dim(k1),)).copy()


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
    masks: list[tuple[np.ndarray, int]] = field(default_factory=list)

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
    basis: list[tuple[sp.csr_matrix, sp.csc_matrix]]
    masks: list[tuple[np.ndarray, int]]


class _Prepared:
    def __init__(self, design: Design, chunk: int = 400_000):
        self.design = design
        self.layout = _Layout(design)
        self.full_groups = [g for g in design.groups if g.basis is None]
        self.basis_groups = [g for g in design.groups if g.basis is not None]
        self.chunks = []
        for lo in range(0, design.n, chunk):
            rows = slice(lo, min(lo + chunk, design.n))
            full = _one_hot(self.full_groups, rows) if self.full_groups else None
            basis = []
            for g in self.basis_groups:
                m = _one_hot([g], rows)
                basis.append((m, m.T))
            masks = [(np.flatnonzero(r[rows]), k - 1) for r, k in design.masks]
            self.chunks.append(_Chunk(rows, full, None if full is None else full.T, basis, masks))

    def stack_full(self, params: dict) -> np.ndarray | None:
        return np.vstack([params[g.name] for g in self.full_groups]) if self.full_groups else None

    def eta(self, params: dict, c: _Chunk, full_theta: np.ndarray | None) -> np.ndarray:
        """Linear predictor for classes 1..K-1 (class 0 is the implicit zero)."""
        d = self.design
        n = c.rows.stop - c.rows.start
        inner = c.full @ full_theta if c.full is not None else np.zeros((n, d.n_classes - 1))
        inner += params["intercept"]
        for (m, _), g in zip(c.basis, self.basis_groups):
            inner += (m @ params[g.name]) @ g.basis
        if d.dense is not None:
            inner += d.dense[c.rows] @ params["dense"]
        for rows, k in c.masks:
            inner[rows, k] += MASK_OFFSET
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
            gp["intercept"] += prob.sum(axis=0)
            if c.full is not None:
                full_grad += c.full_t @ prob
            for (m, mt), g in zip(c.basis, self.basis_groups):
                gp[g.name] += mt @ (prob @ g.basis.T)
            if d.dense is not None:
                gp["dense"] += d.dense[c.rows].T @ prob
        if full_grad is not None:
            pos = 0
            for g in self.full_groups:
                gp[g.name] += full_grad[pos:pos + g.n_levels]
                pos += g.n_levels
        return loss, grad

    def hessian_diag(self, params: dict) -> dict[str, np.ndarray]:
        """Diagonal of the data Hessian for every parameter block (prior excluded)."""
        d = self.design
        k1 = d.n_classes - 1
        full_theta = self.stack_full(params)
        out = {k: np.zeros(s) for k, s in self.layout.shapes.items()}
        full_h = np.zeros_like(full_theta) if full_theta is not None else None
        for c in self.chunks:
            prob = _softmax(self.eta(params, c, full_theta))[0]
            w = np.ones(len(prob)) if d.weights is None else d.weights[c.rows].astype(np.float64)
            # Curvature along basis direction b: sum_k b_k^2 p_k - (b . p)^2.
            curv_full = (prob - prob**2) * w[:, None]
            out["intercept"] += curv_full.sum(axis=0)
            if c.full is not None:
                full_h += c.full_t.multiply(c.full_t) @ curv_full
            for (m, mt), g in zip(c.basis, self.basis_groups):
                b = g.basis
                curv = ((prob @ (b.T ** 2)) - (prob @ b.T) ** 2) * w[:, None]
                out[g.name] += mt.multiply(mt) @ curv
            if d.dense is not None:
                x = d.dense[c.rows].astype(np.float64)
                out["dense"] += (x**2).T @ curv_full
        if full_h is not None:
            pos = 0
            for g in self.full_groups:
                out[g.name] += full_h[pos:pos + g.n_levels]
                pos += g.n_levels
        return out


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


def _deviation(g: Group, th: np.ndarray) -> np.ndarray:
    """Penalized deviation of each level: from its predecessor, prior mean or zero."""
    if g.rw_prev is not None:
        prev = np.asarray(g.rw_prev)
        has = prev >= 0
        out = th.copy()
        out[has] -= th[prev[has]]
        return out
    if g.prior_mean is not None:
        return th - g.prior_mean
    return th


def _level_scales(g: Group, k1: int) -> np.ndarray:
    """SD of each level's deviation, shape (n_levels, d)."""
    s = np.tile(g.sigma_vec(k1), (g.n_levels, 1))
    if g.rw_prev is not None:
        roots = np.asarray(g.rw_prev) < 0
        s[roots] = g.root_vec(k1)
    return s


def _penalty(design: Design, layout: _Layout, theta: np.ndarray) -> tuple[float, np.ndarray]:
    k1 = layout.k1
    grad = np.zeros(layout.size)
    gp = layout.unpack(grad)
    params = layout.unpack(theta)
    pen = 0.5 * float(params["intercept"] @ params["intercept"]) / design.sigma_intercept**2
    gp["intercept"][:] = params["intercept"] / design.sigma_intercept**2
    dense = params["dense"]
    pen += 0.5 * float((dense**2).sum()) / design.sigma_dense**2
    gp["dense"][:] = dense / design.sigma_dense**2
    for g in design.groups:
        th = params[g.name]
        dev = _deviation(g, th)
        r = dev / _level_scales(g, k1) ** 2
        pen += 0.5 * float((dev * r).sum())
        gp[g.name][:] = r
        if g.rw_prev is not None:
            prev = np.asarray(g.rw_prev)
            has = prev >= 0
            np.subtract.at(gp[g.name], prev[has], r[has])
    return pen, grad


def _prior_precision_diag(design: Design, layout: _Layout) -> np.ndarray:
    k1 = layout.k1
    out = np.zeros(layout.size)
    o = layout.unpack(out)
    o["intercept"][:] = 1 / design.sigma_intercept**2
    o["dense"][:] = 1 / design.sigma_dense**2
    for g in design.groups:
        prec = 1 / _level_scales(g, k1) ** 2
        if g.rw_prev is not None:
            prev = np.asarray(g.rw_prev)
            has = prev >= 0
            np.add.at(prec, prev[has], prec[has])
        o[g.name][:] = prec
    return out


@dataclass
class FitResult:
    params: dict[str, np.ndarray]
    sigmas: dict[str, np.ndarray]
    loss: float
    n_iter: int
    n_eval: int
    seconds: float
    converged: bool
    message: str


def _flat_dict(layout: _Layout, d: dict) -> np.ndarray:
    out = np.zeros(layout.size)
    for k, s in layout.slices.items():
        out[s] = np.asarray(d[k]).ravel()
    return out


def fit(design: Design, theta0: np.ndarray | None = None, *, processes: int | None = None,
        maxiter: int = 600, tol: float = 1e-10, gtol: float = 1e-6, verbose: bool = False,
        prepared: _Prepared | None = None, precondition: bool = True) -> FitResult:
    prep = prepared or _Prepared(design)
    layout = prep.layout
    theta = np.zeros(layout.size) if theta0 is None else np.asarray(theta0, dtype=np.float64).copy()
    if theta0 is None:
        counts = np.bincount(design.y, weights=design.weights, minlength=design.n_classes) + 0.5
        theta[layout.slices["intercept"]] = np.log(counts[1:] / counts[0])
    if precondition:
        h = _flat_dict(layout, prep.hessian_diag(layout.unpack(theta))) + _prior_precision_diag(design, layout)
        scale = 1 / np.sqrt(np.maximum(h, 1e-12))
    else:
        scale = np.ones(layout.size)
    processes = max(1, min(processes or (os.cpu_count() or 1), len(prep.chunks)))
    parts = [list(range(i, len(prep.chunks), processes)) for i in range(processes)]
    total_w = float(design.n if design.weights is None else design.weights.sum())
    t0 = time.time()
    calls = [0]
    pool = None
    if processes > 1:
        _WORK["prep"] = prep
        pool = mp.get_context("fork").Pool(processes)

    def objective(u):
        th = u * scale
        calls[0] += 1
        if pool is None:
            loss, grad = prep.loss_grad(th, range(len(prep.chunks)))
        else:
            res = pool.map(_worker, [(th, p) for p in parts])
            loss = sum(r[0] for r in res)
            grad = np.sum([r[1] for r in res], axis=0)
        pen, pgrad = _penalty(design, layout, th)
        if verbose and calls[0] % 25 == 0:
            print(f"  eval {calls[0]}: nll/w={loss / total_w:.7f} pen/w={pen / total_w:.7f} "
                  f"{time.time() - t0:.0f}s", flush=True)
        return (loss + pen) / total_w, (grad + pgrad) * scale / total_w

    try:
        res = minimize(objective, theta / scale, jac=True, method="L-BFGS-B",
                       options={"maxiter": maxiter, "maxcor": 30, "ftol": tol,
                                "gtol": gtol / max(total_w, 1) ** 0.5})
    finally:
        if pool is not None:
            pool.close()
            pool.join()
            _WORK.clear()
    params = layout.unpack(res.x * scale)
    sigmas = {g.name: g.sigma_vec(layout.k1) for g in design.groups}
    return FitResult(params, sigmas, float(res.fun), int(res.nit), calls[0], time.time() - t0,
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


def row_log_loss(design: Design, params: dict[str, np.ndarray], prepared: _Prepared | None = None) -> np.ndarray:
    """Unweighted per-row negative log-likelihood (for match-bootstrap comparisons)."""
    prep = prepared or _Prepared(design)
    full_theta = prep.stack_full(params)
    out = np.empty(design.n)
    for c in prep.chunks:
        eta = prep.eta(params, c, full_theta)
        lse = _softmax(eta)[1]
        y = design.y[c.rows]
        picked = np.zeros(len(y))
        pos = y > 0
        picked[pos] = eta[pos, y[pos] - 1]
        out[c.rows] = lse - picked
    return out


def log_loss(design: Design, params: dict[str, np.ndarray], prepared: _Prepared | None = None) -> float:
    """Weighted mean multinomial log loss (natural log)."""
    ll = row_log_loss(design, params, prepared)
    if design.weights is None:
        return float(ll.mean())
    w = design.weights.astype(np.float64)
    return float(ll @ w / w.sum())


def hessian_diag(design: Design, params: dict[str, np.ndarray],
                 prepared: _Prepared | None = None) -> dict[str, np.ndarray]:
    """Diagonal of the data Hessian for each group's parameters (prior excluded)."""
    prep = prepared or _Prepared(design)
    h = prep.hessian_diag(params)
    return {g.name: h[g.name] for g in design.groups}


def posterior_sd(design: Design, params: dict[str, np.ndarray],
                 prepared: _Prepared | None = None) -> dict[str, np.ndarray]:
    """Diagonal Laplace posterior SD of each group level."""
    prep = prepared or _Prepared(design)
    hd = hessian_diag(design, params, prep)
    prec = prep.layout.unpack(_prior_precision_diag(design, prep.layout))
    return {g.name: 1 / np.sqrt(hd[g.name] + prec[g.name]) for g in design.groups}


def update_sigmas(design: Design, params: dict[str, np.ndarray], *, min_sigma: float = 0.003,
                  max_sigma: float = 3.0, prepared: _Prepared | None = None) -> dict[str, np.ndarray]:
    """MacKay empirical-Bayes prior SDs per dimension; levels without data are ignored."""
    prep = prepared or _Prepared(design)
    k1 = design.n_classes - 1
    hd = hessian_diag(design, params, prep)
    prec_all = prep.layout.unpack(_prior_precision_diag(design, prep.layout))
    new = {}
    for g in design.groups:
        if g.fixed_sigma:
            new[g.name] = g.sigma_vec(k1)
            continue
        sig = g.sigma_vec(k1)
        dev = _deviation(g, params[g.name])
        used = hd[g.name].sum(axis=1) > 0
        if g.rw_prev is not None:
            used &= np.asarray(g.rw_prev) >= 0
        if not used.any():
            new[g.name] = sig
            continue
        v = 1 / (hd[g.name][used] + prec_all[g.name][used])
        gamma = np.clip(1 - v / sig**2, 1e-6, 1)
        s2 = (dev[used] ** 2).sum(axis=0) / gamma.sum(axis=0)
        new[g.name] = np.clip(np.sqrt(s2), min_sigma, max_sigma)
    return new


def fit_eb(design: Design, rounds: int = 4, theta0: np.ndarray | None = None, verbose: bool = False,
           rel_tol: float = 0.02, **kw) -> FitResult:
    """Alternate penalized fits with empirical-Bayes SD updates, warm-starting each round."""
    prep = _Prepared(design)
    result = fit(design, theta0, verbose=verbose, prepared=prep, **kw)
    k1 = design.n_classes - 1
    for r in range(rounds):
        sig = update_sigmas(design, result.params, prepared=prep)
        change = max(float(np.max(np.abs(np.log(sig[g.name] / g.sigma_vec(k1))))) for g in design.groups
                     if not g.fixed_sigma) if any(not g.fixed_sigma for g in design.groups) else 0.0
        if verbose:
            print(f"round {r + 1} max log-change {change:.3f}: " + ", ".join(
                f"{k}={np.round(v, 3).tolist()}" for k, v in sig.items()), flush=True)
        for g in design.groups:
            g.sigma = sig[g.name]
        result = fit(design, flat(design, result.params), verbose=verbose, prepared=prep, **kw)
        if change < rel_tol:
            break
    return result
