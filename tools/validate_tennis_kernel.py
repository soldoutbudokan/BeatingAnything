"""Independent, synthetic point-by-point validation of the exact tennis kernel.

No historical data, prices, fitted artifacts or outcomes are read. The four
hold pairs, sample size, seed and five-standard-error diagnostic limit were
fixed before executing this validation. This is a structural check, not a
test that a constant-hold model describes real tennis or beats a bookmaker.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from beating.tennis_kernel import match_distribution, serve_point_probability

HOLD_PAIRS = ((.50, .50), (.72, .86), (.96, .60), (.995, .995))
MATCHES_PER_PAIR = 50_000
BASE_SEED = 20260908
Z_LIMIT = 5.0


def markov_game_win_probability(point_p: float) -> float:
    """Solve an 18-state game hitting-probability system by elimination.

    Ordinary point scores 0..3 plus server/receiver advantage are transient.
    The implementation neither uses nor repeats the production closed form.
    """
    states = [(a, b) for a in range(4) for b in range(4)] + [(4, 3), (3, 4)]
    index = {state: position for position, state in enumerate(states)}
    n = len(states)
    augmented = [[0.0] * (n + 1) for _ in states]
    for row, (a, b) in enumerate(states):
        augmented[row][row] = 1.0
        for server_wins, probability in ((True, point_p), (False, 1 - point_p)):
            next_a, next_b = a + int(server_wins), b + int(not server_wins)
            if max(next_a, next_b) >= 4 and abs(next_a - next_b) >= 2:
                augmented[row][-1] += probability * (next_a > next_b)
                continue
            if min(next_a, next_b) >= 3:
                state = (3, 3) if next_a == next_b else (4, 3) if next_a > next_b else (3, 4)
            else:
                state = next_a, next_b
            augmented[row][index[state]] -= probability
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        denominator = augmented[column][column]
        if abs(denominator) < 1e-14:
            raise ArithmeticError("singular independent game chain")
        augmented[column] = [value / denominator for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            multiplier = augmented[row][column]
            if multiplier:
                augmented[row] = [a - multiplier * b for a, b in zip(augmented[row], augmented[column])]
    return augmented[index[0, 0]][-1]


@lru_cache(maxsize=32)
def independent_serve_point_probability(hold: float) -> float:
    left, right = 0.0, 1.0
    for _ in range(60):
        middle = (left + right) / 2
        if markov_game_win_probability(middle) < hold:
            left = middle
        else:
            right = middle
    return (left + right) / 2


def simulate_game(point_p: float, draw) -> tuple[bool, int]:
    server_points = receiver_points = 0
    while max(server_points, receiver_points) < 4 or abs(server_points - receiver_points) < 2:
        if draw() < point_p:
            server_points += 1
        else:
            receiver_points += 1
    return server_points > receiver_points, server_points + receiver_points


def simulate_tiebreak(point_ps, first_server: int, draw) -> tuple[int, int]:
    """Literal first-one, alternate-two service turns; no deuce shortcut."""
    scores = [0, 0]
    server, remaining_in_turn = first_server, 1
    while max(scores) < 7 or abs(scores[0] - scores[1]) < 2:
        winner = server if draw() < point_ps[server] else 1 - server
        scores[winner] += 1
        remaining_in_turn -= 1
        if remaining_in_turn == 0:
            server = 1 - server
            remaining_in_turn = 2
    return int(scores[1] > scores[0]), sum(scores)


def simulate_matches(hold1: float, hold2: float, count: int, seed: int) -> dict:
    point_ps = (independent_serve_point_probability(hold1), independent_serve_point_probability(hold2))
    random_source = random.Random(seed)
    draw = random_source.random
    win_count = first_set_tiebreaks = point_count = boundary_checks = tb_boundary_checks = 0
    totals, first_servers = Counter(), Counter()
    for _ in range(count):
        # This is the only randomized initial-server decision in a match.
        server = int(draw() >= .5)
        first_servers[server] += 1
        sets, total_games, set_number = [0, 0], 0, 0
        while max(sets) < 2:
            set_first_server = server
            games = [0, 0]
            set_number += 1
            tiebreak = False
            while True:
                if games == [6, 6]:
                    tiebreak = True
                    tb_first_server = server
                    winner, played_points = simulate_tiebreak(point_ps, tb_first_server, draw)
                    point_count += played_points
                    games[winner] += 1
                    # ITF Rule 5b: the first tiebreak server receives next set.
                    server = 1 - tb_first_server
                    break
                held, played_points = simulate_game(point_ps[server], draw)
                point_count += played_points
                winner = server if held else 1 - server
                games[winner] += 1
                server = 1 - server
                if max(games) >= 6 and abs(games[0] - games[1]) >= 2:
                    break
            winner = int(games[1] > games[0])
            sets[winner] += 1
            length = sum(games)
            total_games += length
            if set_number == 1 and tiebreak:
                first_set_tiebreaks += 1
            if max(sets) < 2:
                # A diagnostic assertion, not the state-transition implementation.
                assert server == (set_first_server if length % 2 == 0 else 1 - set_first_server)
                boundary_checks += 1
                tb_boundary_checks += tiebreak
        assert 12 <= total_games <= 39
        win_count += sets[0] == 2
        totals[total_games] += 1
    return {"independent_serve_point_ps": list(point_ps), "matches": count,
            "player_one_wins": win_count, "first_set_tiebreaks": first_set_tiebreaks,
            "total_games_counts": [totals[index] for index in range(40)],
            "initial_server_counts": {str(k + 1): v for k, v in first_servers.items()},
            "simulated_points": point_count, "set_boundary_checks": boundary_checks,
            "tiebreak_to_next_set_checks": tb_boundary_checks}


def _comparison(exact, observed, reference_variance, sample_variance, count):
    se = math.sqrt(reference_variance / count)
    difference = observed - exact
    z = difference / se if se else 0.0 if difference == 0 else math.copysign(float("inf"), difference)
    return {"exact": exact, "monte_carlo": observed, "difference": difference,
            "null_mc_standard_error": se, "empirical_mc_standard_error": math.sqrt(sample_variance / count),
            "standardized_difference": z, "within_five_standard_errors": abs(z) <= Z_LIMIT}


def validate_pair(hold1, hold2, count, seed):
    simulated = simulate_matches(hold1, hold2, count, seed)
    exact = match_distribution(hold1, hold2)
    pmf = exact["total_games_pmf"]
    histogram = simulated["total_games_counts"]
    mean_exact = sum(i * float(p) for i, p in enumerate(pmf))
    mean_mc = sum(i * n for i, n in enumerate(histogram)) / count
    variance_exact = sum((i - mean_exact) ** 2 * float(p) for i, p in enumerate(pmf))
    variance_mc = sum((i - mean_mc) ** 2 * n for i, n in enumerate(histogram)) / (count - 1)
    comparisons = {}
    for name, probability, wins in (
        ("match_win_p", exact["match_win_p"], simulated["player_one_wins"]),
        ("over_21_5_p", exact["over_21_5_p"], sum(histogram[22:])),
        ("first_set_tiebreak_p", exact["set_tiebreak_p"], simulated["first_set_tiebreaks"]),
    ):
        estimate = wins / count
        comparisons[name] = _comparison(probability, estimate, probability * (1 - probability),
                                         estimate * (1 - estimate) * count / (count - 1), count)
    comparisons["mean_total_games"] = _comparison(mean_exact, mean_mc, variance_exact, variance_mc, count)
    inversion = [{"hold": hold, "independent_point_p": point, "production_point_p": serve_point_probability(hold),
                  "independent_chain_hold_residual": markov_game_win_probability(point) - hold,
                  "point_probability_difference": point - serve_point_probability(hold)}
                 for hold, point in zip((hold1, hold2), simulated["independent_serve_point_ps"])]
    return {"hold1": hold1, "hold2": hold2, "seed": seed, "simulation": simulated,
            "inversion": inversion, "comparisons": comparisons,
            "exact_total_games_pmf": [float(p) for p in pmf],
            "pmf_l1_distance": sum(abs(float(p) - n / count) for p, n in zip(pmf, histogram)),
            "passed": all(c["within_five_standard_errors"] for c in comparisons.values())
                      and all(abs(i["point_probability_difference"]) < 1e-11 for i in inversion)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tennis-kernel-independent-check.json")
    args = parser.parse_args()
    start = time.monotonic()
    results = []
    for offset, pair in enumerate(HOLD_PAIRS):
        result = validate_pair(*pair, MATCHES_PER_PAIR, BASE_SEED + offset)
        results.append(result)
        print(json.dumps({"holds": pair, "matches": MATCHES_PER_PAIR, "passed": result["passed"],
                          "max_abs_z": max(abs(c["standardized_difference"]) for c in result["comparisons"].values())}), flush=True)
    kernel = ROOT / "beating/tennis_kernel.py"
    script = Path(__file__)
    report = {"synthetic_only": True, "historical_data_read": False,
              "created_at": datetime.now(timezone.utc).isoformat(), "python_version": platform.python_version(),
              "python_executable": sys.executable, "numpy_version": version("numpy"), "scipy_version": version("scipy"),
              "kernel_sha256": hashlib.sha256(kernel.read_bytes()).hexdigest(),
              "validation_script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
              "elapsed_seconds": time.monotonic() - start, "total_matches": MATCHES_PER_PAIR * len(HOLD_PAIRS),
              "fixed_hold_pairs": [list(p) for p in HOLD_PAIRS], "base_seed": BASE_SEED,
              "diagnostic_limit_standard_errors": Z_LIMIT, "comparisons_per_pair": 4,
              "method": "Independent 18-state game linear system and bisection; literal point simulation; initial server randomized once and carried; seven-point win-by-two tiebreak at 6-6 in every set",
              "limitation": "Finite synthetic checks support scoring implementation only; no real-data calibration or betting edge demonstrated",
              "results": results, "passed": all(r["passed"] for r in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": report["passed"], "elapsed_seconds": report["elapsed_seconds"], "output": str(args.output)}), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
