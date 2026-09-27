"""Pure numerical kernel for the frozen NHL shot-to-goal declaration.

No source, file, price or outcome access occurs here. The caller must enforce
history availability, membership, valid goals <= shots, and the 40--80 appearance
gate. Numerical failures are explicit exclusions; no market-dependent fallback.
"""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

import numpy as np
from scipy.linalg import eigh_tridiagonal
from scipy.optimize import brentq
from scipy.special import gammaincc, logsumexp

MEAN_BRACKET = (1e-10, 1000.0)
ROOT_ABSOLUTE_TOLERANCE = 1e-11
QUADRATURE_ABSOLUTE_TOLERANCE = 1e-10


class NumericalExclusion(ValueError):
    """The declared numerical calculation cannot admit this input."""


def _real(value: Real, label: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise NumericalExclusion(f"{label}: finite real number required")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise NumericalExclusion(f"{label}: nonfinite value") from exc
    if not math.isfinite(result):
        raise NumericalExclusion(f"{label}: nonfinite value")
    return result


def _count(value: Real, label: str) -> float:
    result = _real(value, label)
    if result < 0 or not result.is_integer():
        raise NumericalExclusion(f"{label}: nonnegative integer required")
    return result


def _alpha(value: Real) -> float:
    result = _real(value, "alpha")
    if not 0 <= result <= 1:
        raise NumericalExclusion("alpha: outside declared [0, 1] range")
    if result > 0 and not math.isfinite(1.0 / result):
        raise NumericalExclusion("alpha: nonfinite negative-binomial size")
    return result


def estimate_alpha(shots: Sequence[int]) -> float:
    """Declared unbiased-variance estimator, shrinkage 40 and cap 1.

    At least two counts are necessary for sample variance. The caller separately
    enforces the declared latest-80/minimum-40 history rule.
    """
    try:
        values = [_count(value, "shots") for value in shots]
    except TypeError as exc:
        raise NumericalExclusion("shots: one-dimensional count sequence required") from exc
    n = len(values)
    if n < 2:
        raise NumericalExclusion("shots: at least two observations required")
    try:
        mean = math.fsum(values) / n
        if mean == 0:
            return 0.0
        variance = math.fsum((value - mean) ** 2 for value in values) / (n - 1)
        excess = (variance - mean) / (mean * mean)
        result = max(0.0, excess) * (n - 1) / (n - 1 + 40)
    except (OverflowError, ZeroDivisionError) as exc:
        raise NumericalExclusion("alpha: nonfinite moment calculation") from exc
    if not all(math.isfinite(v) for v in (mean, variance, excess, result)):
        raise NumericalExclusion("alpha: nonfinite moment calculation")
    return min(1.0, result)


def beta_parameters(total_goals: int, total_shots: int, league_rate: float) -> tuple[float, float]:
    """Return (G + 100*r, T - G + 100*(1-r)); no fitted prior strength."""
    goals, shots = _count(total_goals, "total_goals"), _count(total_shots, "total_shots")
    rate = _real(league_rate, "league_rate")
    if goals > shots:
        raise NumericalExclusion("total_goals exceeds total_shots")
    if not 0 < rate < 1:
        raise NumericalExclusion("league_rate must give a proper positive Beta prior")
    a, b = goals + 100.0 * rate, shots - goals + 100.0 * (1.0 - rate)
    _beta_shapes(a, b)
    return a, b


def shot_cdf(mean: float, k: int, alpha: float) -> float:
    """P(S <= k) for Poisson or NB(size=1/alpha, mean=mean).

    The NB CDF is the finite PMF sum through k, evaluated in log space. This
    avoids an ill-conditioned incomplete-beta call for tiny positive alpha.
    """
    mean, alpha = _real(mean, "mean"), _alpha(alpha)
    cutoff = _count(k, "k")
    if mean < 0:
        raise NumericalExclusion("mean must be nonnegative")
    if mean == 0:
        return 1.0
    if alpha == 0:
        result = float(gammaincc(cutoff + 1.0, mean))
    else:
        log_denom = math.log1p(alpha * mean)
        log_mass = -log_denom / alpha
        log_masses = [log_mass]
        for j in range(int(cutoff)):
            log_mass += math.log(mean) + math.log1p(alpha * j) - math.log(j + 1) - log_denom
            log_masses.append(log_mass)
        log_cdf = float(logsumexp(log_masses))
        # Summing a CDF arbitrarily close to 1 can overshoot by a few ulps.
        # Only this bounded roundoff is normalized; larger violations exclude.
        if 0 < log_cdf <= 8 * (int(cutoff) + 1) * np.finfo(float).eps:
            log_cdf = 0.0
        result = math.exp(log_cdf)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise NumericalExclusion("shot CDF is nonfinite or outside [0, 1]")
    return result


def invert_shot_mean(shot_line: float, q_under: float, alpha: float) -> float:
    """Invert the declared shot CDF on [1e-10, 1000], with xtol=1e-11."""
    line, q, alpha = _real(shot_line, "shot_line"), _real(q_under, "q_under"), _alpha(alpha)
    if not 0.5 <= line <= 8.5 or not (2 * line).is_integer() or int(2 * line) % 2 != 1:
        raise NumericalExclusion("shot_line must be a half point from 0.5 to 8.5")
    if not 0 < q < 1:
        raise NumericalExclusion("q_under must lie strictly between 0 and 1")
    k = math.floor(line)

    def residual(mean):
        return shot_cdf(mean, k, alpha) - q

    low, high = MEAN_BRACKET
    lo, hi = residual(low), residual(high)
    if lo < 0 or hi > 0:
        raise NumericalExclusion("shot mean root is outside declared bracket")
    try:
        result = float(brentq(residual, low, high, xtol=ROOT_ABSOLUTE_TOLERANCE,
                              rtol=4 * np.finfo(float).eps, maxiter=200))
    except (ValueError, RuntimeError, OverflowError) as exc:
        raise NumericalExclusion("shot mean inversion failed") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise NumericalExclusion("shot mean solution is nonfinite or outside bracket")
    return result


def _beta_shapes(a: float, b: float) -> tuple[float, float]:
    a, b = _real(a, "a"), _real(b, "b")
    if a <= 0 or b <= 0 or not math.isfinite(a + b):
        raise NumericalExclusion("a and b must be positive with finite sum")
    return a, b


def _normalized_beta_rule(a: float, b: float, nodes: int) -> tuple[np.ndarray, np.ndarray]:
    """Normalized Gauss--Jacobi rule on [0,1] for Beta(a,b).

    Golub--Welsch diagonalizes the shifted Jacobi recurrence. Squared first
    eigenvector components give probability weights directly, avoiding the
    potentially overflowing factor 2**(a+b-1)*B(a,b). Jacobi exponents in the
    conventional [-1,1] parameterization are (b-1, a-1).
    """
    a, b = _beta_shapes(a, b)
    if nodes not in (64, 128):
        raise NumericalExclusion("only the declared 64/128-node rules are allowed")
    total = a + b
    diagonal = np.empty(nodes)
    diagonal[0] = a / total
    n = np.arange(1, nodes, dtype=float)
    d = 2.0 * (n - 1.0) + total
    diagonal[1:] = 0.5 * (1.0 + ((a - b) / d) * ((total - 2.0) / (2.0 * n + total)))
    off = np.empty(nodes - 1)
    # The first coefficient has an analytically canceled (a+b-1) factor.
    off[0] = math.sqrt((a / total) * (b / total) / (total + 1.0))
    n = np.arange(2, nodes, dtype=float)
    d = 2.0 * (n - 1.0) + total
    off[1:] = np.sqrt((n / d) * (((n - 1.0) + a) / d)
                     * (((n - 1.0) + b) / (d - 1.0))
                     * (((n - 2.0) + total) / (d + 1.0)))
    if not np.all(np.isfinite(diagonal)) or not np.all(np.isfinite(off)):
        raise NumericalExclusion("nonfinite Jacobi recurrence")
    try:
        points, vectors = eigh_tridiagonal(diagonal, off, check_finite=True)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise NumericalExclusion("Jacobi eigensystem failed") from exc
    weights = vectors[0, :] ** 2
    norm = math.fsum(weights)
    if (not math.isfinite(norm) or norm <= 0 or not np.all(np.isfinite(points))
            or np.any(points < 0) or np.any(points > 1)):
        raise NumericalExclusion("invalid normalized Jacobi rule")
    return points, weights / norm


def _zero_goal_at_nodes(mean: float, alpha: float, a: float, b: float, nodes: int) -> float:
    points, weights = _normalized_beta_rule(a, b, nodes)
    log_p0 = -mean * points if alpha == 0 else -np.log1p(alpha * mean * points) / alpha
    probability = math.fsum(weights * np.exp(log_p0))
    if not math.isfinite(probability) or not 0 < probability <= 1:
        raise NumericalExclusion("zero-goal probability is nonfinite, underflowed or outside (0, 1]")
    return probability


def zero_goal_probability(mean: float, alpha: float, a: float, b: float) -> dict[str, float]:
    """128-node posterior-predictive P0, checked against 64 nodes (atol=1e-10).

    Returns probability, probability_64, and absolute_difference. The declared
    128-node answer is always used; disagreement excludes rather than selecting
    an alternate quadrature or replacing the Beta distribution with its mean.
    """
    mean, alpha = _real(mean, "mean"), _alpha(alpha)
    a, b = _beta_shapes(a, b)
    if mean < 0:
        raise NumericalExclusion("mean must be nonnegative")
    p128 = _zero_goal_at_nodes(mean, alpha, a, b, 128)
    p64 = _zero_goal_at_nodes(mean, alpha, a, b, 64)
    difference = abs(p128 - p64)
    if difference > QUADRATURE_ABSOLUTE_TOLERANCE:
        raise NumericalExclusion(f"64/128-node disagreement: {difference:.17g}")
    return {"probability": p128, "probability_64": p64, "absolute_difference": difference}
