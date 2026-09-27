#!/usr/bin/env python3
"""Synthetic-only verification; no empirical file or source access."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import scipy
from scipy.integrate import quad
from scipy.special import beta, betaln, roots_jacobi
from scipy.stats import nbinom, poisson

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import nhl_shot_goal_kernel as kernel


def near(actual, expected, tolerance=1e-11):
    error = abs(actual - expected)
    assert math.isfinite(error) and error <= tolerance, (actual, expected, tolerance)
    return error


def must_exclude(function):
    try:
        function()
    except kernel.NumericalExclusion as exc:
        return str(exc)
    raise AssertionError("Expected an explicit numerical exclusion")


def main():
    checks = {}
    alpha_cases = [([0] * 40, 0.0), ([3] * 40, 0.0), ([0, 2], 1 / 41),
                   ([0, 2] * 20, 1 / 79), ([0] * 79 + [80], 1.0)]
    checks["dispersion_hand_calculations"] = {
        "cases": len(alpha_cases),
        "max_absolute_error": max(near(kernel.estimate_alpha(x), answer, 1e-14) for x, answer in alpha_cases)}
    assert kernel.beta_parameters(12, 120, 0.1) == (22.0, 198.0)
    assert kernel.beta_parameters(0, 0, 0.1) == (10.0, 90.0)

    errors = []
    for alpha in [0.0, 0.025, 0.2, 1.0]:
        for mean in [1e-10, 0.03, 0.3, 1.0, 4.0, 12.0, 40.0, 1000.0]:
            for cutoff in range(9):
                ref = poisson.cdf(cutoff, mean) if alpha == 0 else nbinom.cdf(cutoff, 1 / alpha, 1 / (1 + alpha * mean))
                errors.append(near(kernel.shot_cdf(mean, cutoff, alpha), float(ref), 2e-13))
    checks["cdf_against_scipy_distributions"] = {"cases": len(errors), "max_absolute_error": max(errors)}

    errors, inversion_errors = [], []
    for alpha in [0.0, 1e-12, 1e-8, 0.025, 0.2, 1.0]:
        for cutoff in range(9):
            for probability in [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98]:
                mean = kernel.invert_shot_mean(cutoff + 0.5, probability, alpha)
                errors.append(near(kernel.shot_cdf(mean, cutoff, alpha), probability, 5e-11))
                if alpha == 0 and cutoff == 0:
                    inversion_errors.append(near(mean, -math.log(probability), 2e-11))
                if alpha == 1:
                    exact = -1 / math.expm1(math.log1p(-probability) / (cutoff + 1)) - 1
                    inversion_errors.append(near(mean, exact, 2e-11))
    checks["shot_market_anchor"] = {"cases": len(errors), "max_probability_residual": max(errors),
                                    "closed_form_inverse_cases": len(inversion_errors),
                                    "max_closed_form_mean_error": max(inversion_errors)}
    tiny_errors = [near(kernel.shot_cdf(mean, k, 1e-12), float(poisson.cdf(k, mean)), 1e-10)
                   for mean in [0.1, 1, 4, 12] for k in range(9)]
    checks["small_positive_alpha_poisson_limit"] = {"cases": len(tiny_errors), "max_absolute_error": max(tiny_errors)}

    moment_errors, root_errors = [], []
    for a, b in [(0.2, 0.3), (0.5, 0.5), (1, 1), (2.5, 4), (10, 90), (80, 920), (1e6, 3e6)]:
        for count in [64, 128]:
            points, weights = kernel._normalized_beta_rule(a, b, count)
            near(float(weights.sum()), 1, 1e-14)
            for degree in [1, 2, 3, 5]:
                exact = math.prod((a + j) / (a + b + j) for j in range(degree))
                moment_errors.append(near(float(np.dot(weights, points ** degree)), exact, 2e-13))
            if a + b < 100:
                x, w = roots_jacobi(count, b - 1, a - 1)
                root_errors.append(near(float(np.max(np.abs(points - (x + 1) / 2))), 0, 2e-13))
                root_errors.append(near(float(np.max(np.abs(weights - w / w.sum()))), 0, 2e-11))
    checks["normalized_gauss_jacobi"] = {"moment_cases": len(moment_errors), "max_moment_error": max(moment_errors),
                                          "scipy_rule_comparisons": len(root_errors), "max_node_or_weight_error": max(root_errors),
                                          "large_shape_case": {"a": 1e6, "b": 3e6, "finite_normalized_weights": True}}

    closed_errors, convergence = [], []
    for mean in [0.0, 1e-8, 0.1, 1.0, 4.0, 20.0, 80.0]:
        for alpha in [0.0, 0.1, 0.5, 1.0]:
            answer = kernel.zero_goal_probability(mean, alpha, 1, 1)
            if mean == 0:
                exact = 1.0
            elif alpha == 0:
                exact = -math.expm1(-mean) / mean
            elif alpha == 1:
                exact = math.log1p(mean) / mean
            else:
                exact = math.expm1((1 - 1 / alpha) * math.log1p(alpha * mean)) / (mean * (alpha - 1))
            closed_errors.append(near(answer["probability"], exact, 2e-12))
            convergence.append(answer["absolute_difference"])
    checks["uniform_beta_closed_forms"] = {"cases": len(closed_errors), "max_absolute_error": max(closed_errors),
                                            "max_128_64_difference": max(convergence)}

    adaptive = []
    for mean, alpha, a, b in [(0.3, 0, 0.2, 0.3), (4, 0, 1, 1), (10, 0.2, 2, 7),
                              (12, 1, 5, 45), (80, 0, 10, 90), (1000, 0.1, 80, 920),
                              (1000, 1, 10, 90), (3, 1e-12, 10, 90)]:
        def pgf(p):
            return math.exp(-mean * p) if alpha == 0 else math.exp(-math.log1p(alpha * mean * p) / alpha)
        if min(a, b) < 1:
            raw, err = quad(pgf, 0, 1, weight="alg", wvar=(a - 1, b - 1), epsabs=1e-13, epsrel=1e-13)
            ref, error_estimate = raw / beta(a, b), err / beta(a, b)
        else:
            def integrand(p):
                if not 0 < p < 1:
                    return 0.0
                log_density = (a - 1) * math.log(p) + (b - 1) * math.log1p(-p) - betaln(a, b)
                return math.exp(log_density) * pgf(p)
            ref, error_estimate = quad(integrand, 0, 1, points=[a / (a + b)], epsabs=1e-13, epsrel=1e-12, limit=500)
        answer = kernel.zero_goal_probability(mean, alpha, a, b)
        adaptive.append({"synthetic_parameters": {"mean": mean, "alpha": alpha, "a": a, "b": b},
                         "absolute_error": near(answer["probability"], ref, 2e-11), "quad_reported_error": error_estimate,
                         "difference_128_64": answer["absolute_difference"]})
    checks["independent_adaptive_integration"] = {"cases": len(adaptive), "max_absolute_error": max(x["absolute_error"] for x in adaptive), "details": adaptive}

    mixture_errors, tail_bounds = [], []
    for mean in [0.2, 3, 12]:
        for alpha in [0, 0.1, 1]:
            law = poisson(mean) if alpha == 0 else nbinom(1 / alpha, 1 / (1 + alpha * mean))
            last = int(law.ppf(1 - 1e-14)) + 1
            counts = np.arange(last + 1)
            ref = float(np.dot(law.pmf(counts), np.exp(betaln(2, 18 + counts) - betaln(2, 18))))
            tail_bounds.append(float(law.sf(last)))
            mixture_errors.append(near(kernel.zero_goal_probability(mean, alpha, 2, 18)["probability"], ref, 2e-12))
    checks["independent_discrete_thinning_identity"] = {"cases": len(mixture_errors), "max_absolute_error": max(mixture_errors), "max_omitted_tail_probability": max(tail_bounds)}

    monotonic_checks = 0
    for alpha in [0, 0.1, 1]:
        for k in [0, 3, 8]:
            values = [kernel.shot_cdf(mu, k, alpha) for mu in [0.1, 1, 4, 12, 40]]
            assert all(x > y for x, y in zip(values, values[1:]))
            roots = [kernel.invert_shot_mean(k + 0.5, q, alpha) for q in [0.1, 0.3, 0.5, 0.9]]
            assert all(x > y for x, y in zip(roots, roots[1:]))
            monotonic_checks += 2
        values = [kernel.zero_goal_probability(mu, alpha, 10, 90)["probability"] for mu in [0, 0.1, 1, 4, 20]]
        assert all(x > y for x, y in zip(values, values[1:]))
        values = [kernel.zero_goal_probability(4, alpha, a, 100-a)["probability"] for a in [1, 5, 10, 25, 50, 99]]
        assert all(x > y for x, y in zip(values, values[1:]))
        integrated = kernel.zero_goal_probability(4, alpha, 10, 90)["probability"]
        plug_in = math.exp(-0.4) if alpha == 0 else math.exp(-math.log1p(alpha * 0.4) / alpha)
        assert integrated >= plug_in
        monotonic_checks += 3
    values = [kernel.zero_goal_probability(4, alpha, 10, 90)["probability"] for alpha in [0, 0.05, 0.2, 0.5, 1]]
    assert all(x < y for x, y in zip(values, values[1:]))
    checks["monotonicity_and_jensen"] = {"checks": monotonic_checks + 1, "passed": True}

    invalid = {
        "too_short_history": lambda: kernel.estimate_alpha([0]),
        "fractional_count": lambda: kernel.estimate_alpha([0, 0.5]),
        "negative_count": lambda: kernel.estimate_alpha([0, -1]),
        "nonfinite_count": lambda: kernel.estimate_alpha([0, float("nan")]),
        "boolean_count": lambda: kernel.estimate_alpha([0, True]),
        "string_count": lambda: kernel.estimate_alpha([0, "1"]),
        "goals_exceed_shots": lambda: kernel.beta_parameters(2, 1, 0.1),
        "improper_prior": lambda: kernel.beta_parameters(0, 0, 0),
        "invalid_line": lambda: kernel.invert_shot_mean(2, 0.5, 0),
        "invalid_probability": lambda: kernel.invert_shot_mean(2.5, 1, 0),
        "invalid_dispersion": lambda: kernel.invert_shot_mean(2.5, 0.5, 1.1),
        "unbracketed_high_mean": lambda: kernel.invert_shot_mean(8.5, 0.001, 1),
        "unbracketed_low_mean": lambda: kernel.invert_shot_mean(0.5, 1-1e-12, 0),
        "invalid_beta_shape": lambda: kernel.zero_goal_probability(3, 0, 0, 1),
        "nonfinite_mean": lambda: kernel.zero_goal_probability(float("inf"), 0, 1, 1),
        "declared_quadrature_disagreement": lambda: kernel.zero_goal_probability(1000, 0, 1, 1),
    }
    checks["explicit_exclusions"] = {name: must_exclude(call) for name, call in invalid.items()}
    declaration = ROOT / "docs/nhl-shot-to-goal-declaration-2026-09-26.md"
    kernel_path = ROOT / "tools/nhl_shot_goal_kernel.py"
    report = {"status": "all_synthetic_checks_passed", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Synthetic numerical values only; no empirical data, prices, source requests, target labels, forecasts or returns.",
              "declaration_sha256": hashlib.sha256(declaration.read_bytes()).hexdigest(),
              "kernel_sha256": hashlib.sha256(kernel_path.read_bytes()).hexdigest(),
              "verification_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
              "fixed_settings": {"mean_bracket": kernel.MEAN_BRACKET, "absolute_root_tolerance": kernel.ROOT_ABSOLUTE_TOLERANCE,
                                 "quadrature_nodes": [128, 64], "quadrature_absolute_tolerance": kernel.QUADRATURE_ABSOLUTE_TOLERANCE},
              "checks": checks,
              "limitations": ["Finite synthetic checks establish implementation agreement on the stated cases, not universal numerical accuracy or forecasting validity.",
                              "History length, chronology, identities and goal/shot validation per appearance remain caller responsibilities; aggregated beta_parameters validates totals only.",
                              "The declared absolute 64/128 comparison is not a relative-error guarantee for extremely small probabilities; disagreements are excluded without fallback."]}
    output = ROOT / "reports/nhl-shot-goal-kernel-verification-2026-09-26.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "kernel_sha256": report["kernel_sha256"],
                      "max_anchor_residual": checks["shot_market_anchor"]["max_probability_residual"],
                      "max_independent_integral_error": checks["independent_adaptive_integration"]["max_absolute_error"],
                      "report": str(output.relative_to(ROOT))}))


if __name__ == "__main__":
    main()
