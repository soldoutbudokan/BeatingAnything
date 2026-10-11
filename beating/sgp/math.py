"""Integer-yard event geometry and bounds from an exhaustive SGP partition.

This module never estimates dependence from individual prop odds. A reference
must contain four actual joint quotes on S=R+C and either R or C. Probability
bounds are conditional on the chosen de-vig model, not guarantees of true EV.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from functools import lru_cache
from itertools import combinations
import math

CELLS = ("OO", "OU", "UO", "UU")
STATS = ("R", "C", "S")
MODELS = ("power", "additive")
INF = float("inf")


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def decimal_odds(american):
    """Convert conventional American odds; reject malformed prices."""
    price = _number(american, "American odds")
    if abs(price) < 100:
        raise ValueError("American odds must be <= -100 or >= +100")
    return 1 + price / 100 if price > 0 else 1 + 100 / -price


def parse_leg(leg):
    """Return (R/C/S, lower-or-upper index, inclusive integer threshold)."""
    if not isinstance(leg, dict):
        raise ValueError("A leg must be an object")
    stat = leg.get("stat", leg.get("market"))
    if stat not in STATS:
        raise ValueError("Leg stat/market must be R, C, or S")
    if "stat" in leg and "market" in leg and leg["market"] in STATS and leg["stat"] != leg["market"]:
        raise ValueError("Conflicting leg stat and market")
    line = _number(leg.get("line"), "Leg line")
    side = leg.get("side")
    if side == "over":
        return stat, 0, math.floor(line) + 1
    if side == "under":
        return stat, 1, math.ceil(line) - 1
    if side in ("at_least", ">="):
        return stat, 0, math.ceil(line)
    if side in ("at_most", "<="):
        return stat, 1, math.floor(line)
    raise ValueError("Leg side must be over, under, at_least, or at_most")


def polytope(legs):
    """Bounds for integer R,C and S=R+C; negative yards are allowed."""
    bounds = {stat: [-INF, INF] for stat in STATS}
    for leg in legs:
        stat, end, threshold = parse_leg(leg)
        bounds[stat][end] = (max(bounds[stat][end], threshold) if end == 0
                             else min(bounds[stat][end], threshold))
    return bounds


def feasible(bounds):
    if any(low > high for low, high in bounds.values()):
        return False
    (a, b), (c, d), (e, f) = (bounds[stat] for stat in STATS)
    return max(e, a + c) <= min(f, b + d)


def extrema(bounds):
    """Tight coordinate bounds, exact for these integer constraints."""
    if not feasible(bounds):
        return None
    (a, b), (c, d), (e, f) = (bounds[stat] for stat in STATS)
    return {"R": [max(a, e - d), min(b, f - c)],
            "C": [max(c, e - b), min(d, f - a)],
            "S": [max(e, a + c), min(f, b + d)]}


def contained(left, right):
    """Whether every integer point satisfying left also satisfies right."""
    ext = extrema(left)
    return ext is None or all(ext[stat][0] >= right[stat][0]
                              and ext[stat][1] <= right[stat][1] for stat in STATS)


def intersection(left, right):
    return {stat: [max(left[stat][0], right[stat][0]),
                   min(left[stat][1], right[stat][1])] for stat in STATS}


def event_key(legs):
    """Canonical event geometry, independent of redundant leg identities.

    Use this for sharing probability calculations, never for removing legs from
    a sportsbook quote request. Event/player identity must be keyed separately.
    """
    ext = extrema(polytope(legs))
    if ext is None:
        return "empty"
    def label(value):
        return str(int(value)) if math.isfinite(value) else ("-inf" if value < 0 else "+inf")
    return "|".join(f"{stat}:{label(ext[stat][0])}:{label(ext[stat][1])}" for stat in STATS)


@lru_cache(maxsize=1024)
def _devig_cached(prices):
    with localcontext() as ctx:
        ctx.prec = 60
        raw = []
        for price in prices:
            a = Decimal(str(price))
            decimal = 1 + a / 100 if a > 0 else 1 + 100 / -a
            raw.append(1 / decimal)
        low, high = Decimal(0), Decimal(2)
        while sum(ctx.power(value, high) for value in raw) > 1:
            high *= 2
        for _ in range(150):
            exponent = (low + high) / 2
            if sum(ctx.power(value, exponent) for value in raw) > 1:
                low = exponent
            else:
                high = exponent
        exponent = (low + high) / 2
        power = tuple(float(ctx.power(value, exponent)) for value in raw)
        additive = tuple(value - (sum(raw) - 1) / 4 for value in raw)
        valid = all(0 <= value <= 1 for value in additive)
        return float(sum(raw)), float(exponent), power, tuple(map(float, additive)), valid


def devig(prices):
    """De-vig four exhaustive joint prices; invalid additive results stay invalid."""
    if not isinstance(prices, dict) or set(prices) != set(CELLS):
        raise ValueError("Reference prices require exactly OO, OU, UO, and UU")
    values = tuple(_number(prices[cell], f"{cell} odds") for cell in CELLS)
    for value in values:
        decimal_odds(value)
    total, exponent, power, additive, valid = _devig_cached(values)
    return {"raw_implied_sum": total, "power_exponent": exponent,
            "power": dict(zip(CELLS, power)),
            "additive": dict(zip(CELLS, additive)) if valid else None,
            "additive_valid": valid,
            "additive_unclipped": dict(zip(CELLS, additive)),
            "warning": None if valid else "Additive probabilities are outside [0,1]; not clipped."}


def _minimum_profitable_american(probability):
    if not 0 < probability < 1:
        return None
    fair = 100 * (1 / probability - 1) if probability <= .5 else -100 * probability / (1 - probability)
    # A tiny tolerance prevents a floating representation of exactly fair odds
    # from being reported as strictly profitable.
    answer = math.floor(fair + 1e-10) + 1
    if -100 < answer < 100:
        answer = 100 if probability > .5 else 101
    return answer


def evaluate(legs, american, reference):
    """Bound a quoted event using an actual four-cell SGP reference.

    Cells are ordered by (S side, other side). Integer reference lines are
    rejected because pushes make four over/under prices non-exhaustive. No
    interpolation is performed for differing thresholds or strict subsets.
    """
    decimal = decimal_odds(american)
    if reference.get("other") not in ("R", "C"):
        raise ValueError("Reference other must be R or C")
    sum_line = _number(reference.get("sum_line"), "Reference sum line")
    other_line = _number(reference.get("other_line"), "Reference other line")
    if sum_line.is_integer() or other_line.is_integer():
        raise ValueError("Integer reference line has a push state; four cells are not exhaustive")
    distribution = devig(reference.get("prices"))
    target = polytope(legs)
    cells = {cell: polytope([
        {"stat": "S", "side": "over" if cell[0] == "O" else "under", "line": sum_line},
        {"stat": reference["other"], "side": "over" if cell[1] == "O" else "under", "line": other_line},
    ]) for cell in CELLS}
    included = [cell for cell in CELLS if contained(cells[cell], target)]
    intersecting = [cell for cell in CELLS if feasible(intersection(cells[cell], target))]
    models = {}
    for method in MODELS:
        probabilities = distribution[method]
        if probabilities is None:
            models[method] = None
            continue
        low = min(1.0, sum(probabilities[cell] for cell in included))
        high = min(1.0, sum(probabilities[cell] for cell in intersecting))
        models[method] = {"probability_lower": low, "probability_upper": high,
                          "ev_lower": decimal * low - 1, "ev_upper": decimal * high - 1,
                          "min_profitable_american": _minimum_profitable_american(low)}
    both_valid = all(models[method] is not None for method in MODELS)
    lower = min(models[method]["probability_lower"] for method in MODELS) if both_valid else None
    upper = max(models[method]["probability_upper"] for method in MODELS) if both_valid else None
    return {"event_key": event_key(legs), "feasible": feasible(target),
            "included_cells": included, "intersecting_cells": intersecting,
            "exact": included == intersecting, "models": models,
            "conservative_probability_lower": lower, "conservative_probability_upper": upper,
            "conservative_ev_lower": decimal * lower - 1 if lower is not None else None,
            "min_profitable_american": _minimum_profitable_american(lower) if lower is not None else None,
            "both_models_positive": both_valid and all(models[method]["ev_lower"] > 1e-12 for method in MODELS),
            "devig": distribution, "warning": distribution["warning"]}


def generate_candidates(legs, max_legs=4, max_candidates=5000):
    """Enumerate S/component bases and redundant extensions for one player/game.

    All direction pairs are covered. Original inventory order and every original
    leg dictionary are preserved, including differently identified equivalent
    markets. The search is breadth-first in leg count, not price-pruned. The
    returned coverage applies only to this structural family and max_legs.
    """
    if isinstance(max_legs, bool) or not isinstance(max_legs, int) or not 2 <= max_legs <= 4:
        raise ValueError("max_legs must be an integer from 2 through 4")
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError("max_candidates must be a positive integer")
    offered = list(legs)
    parsed = [parse_leg(leg) for leg in offered]
    single = [polytope([leg]) for leg in offered]
    sums = [i for i, leg in enumerate(parsed) if leg[0] == "S"]
    components = [i for i, leg in enumerate(parsed) if leg[0] in ("R", "C")]
    candidates, seen, bases = [], set(), []
    counts = {str(size): 0 for size in range(2, max_legs + 1)}
    examined, extensions_examined, truncated, reason = 0, 0, False, None
    # Also bound work on heavily duplicated inventories. Report incomplete
    # coverage explicitly even if this limit fires before the output cap.
    search_budget = max(10000, max_candidates * 100)

    def add(indices):
        key = tuple(sorted(indices))
        if key in seen:
            return True
        if len(candidates) >= max_candidates:
            return False
        seen.add(key)
        candidates.append([offered[i] for i in key])
        counts[str(len(key))] += 1
        return True

    for sum_index in sums:
        if truncated:
            break
        for component_index in components:
            examined += 1
            if examined > search_budget:
                truncated, reason = True, "search_budget"
                break
            base_indices = (sum_index, component_index)
            base = intersection(single[sum_index], single[component_index])
            if not feasible(base):
                continue
            if not add(base_indices):
                truncated, reason = True, "max_candidates"
                break
            bases.append((base_indices, base))
    for size in range(3, max_legs + 1):
        if truncated:
            break
        for indices, base in bases:
            redundant = [i for i in range(len(offered)) if i not in indices and contained(base, single[i])]
            for extras in combinations(redundant, size - 2):
                extensions_examined += 1
                if examined + extensions_examined > search_budget:
                    truncated, reason = True, "search_budget"
                    break
                if not add((*indices, *extras)):
                    truncated, reason = True, "max_candidates"
                    break
            if truncated:
                break
    return {"candidates": candidates, "truncated": truncated,
            "truncation_reason": reason, "coverage_complete": not truncated,
            "coverage_scope": "S-versus-R/C two-leg bases plus logically redundant additions; one player/game",
            "inventory_leg_count": len(offered), "candidate_count": len(candidates),
            "counts_by_leg_count": counts, "max_legs": max_legs,
            "max_candidates": max_candidates, "search_budget": search_budget,
            "base_pairs_examined": examined, "extension_sets_examined": extensions_examined,
            "unique_event_count": len({event_key(candidate) for candidate in candidates})}
