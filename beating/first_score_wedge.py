"""Fixed, exploratory first-field-goal to first-score probability conversion."""
from collections import Counter, defaultdict
from datetime import datetime
import math

TRANSFER = 80 / 1319
PSEUDO_FIELD_GOALS = 100


def prior_rates(rows, before):
    """Aggregate prior recorded starts; never admit a target-season row."""
    totals = defaultdict(lambda: [0.0, 0.0])
    seen, dates, counts = set(), [], Counter()
    for row in rows:
        gid, player = row["game_id"], row["player_id"]
        day = datetime.strptime(gid[:8], "%Y%m%d").date()
        if day >= before:
            raise ValueError("Prior statistics overlap price cohort")
        if not player or (gid, player) in seen:
            raise ValueError("Missing or duplicate prior player/game identity")
        seen.add((gid, player))
        dates.append(day)
        counts["input_rows"] += 1
        if row["starter"] not in ("True", "False"):
            raise ValueError("Invalid prior starter flag")
        if row["starter"] == "False":
            counts["nonstarters"] += 1
            continue
        counts["recorded_starts"] += 1
        raw = [row["FG"], row["FT"]]
        values = [None if v in ("", "NA", "None") else float(v) for v in raw]
        if any(v is not None and (not math.isfinite(v) or v < 0) for v in values):
            raise ValueError("Invalid prior scoring count")
        if None in values:
            counts["missing_numeric_starts"] += 1
            continue
        fg, ft = values
        totals[player][0] += fg
        totals[player][1] += ft
        counts["valid_starts"] += 1
    fg = sum(v[0] for v in totals.values())
    ft = sum(v[1] for v in totals.values())
    if fg <= 0 or ft <= 0:
        raise ValueError("Prior scoring totals must be positive")
    league = ft / fg
    rates = {p: (v[1] + PSEUDO_FIELD_GOALS * league) / (v[0] + PSEUDO_FIELD_GOALS)
             for p, v in totals.items()}
    return rates, league, {**dict(counts), "players": len(totals), "field_goals": fg,
        "free_throws": ft, "league_ratio": league,
        "first_date": min(dates).isoformat(), "last_date": max(dates).isoformat()}


def normalized_prices(runners):
    if len(runners) != 10 or len({r["player_id"] for r in runners}) != 10:
        raise ValueError("Expected ten unique players")
    if any(not math.isfinite(r["decimal"]) or r["decimal"] <= 1 for r in runners):
        raise ValueError("Invalid decimal price")
    inverse = {r["player_id"]: 1 / r["decimal"] for r in runners}
    total = sum(inverse.values())
    return {p: v / total for p, v in inverse.items()}


def convert(q, rates, league):
    if not q or not math.isclose(sum(q.values()), 1, abs_tol=1e-10):
        raise ValueError("Reference probabilities do not sum to one")
    if any(not math.isfinite(v) or v <= 0 for v in q.values()):
        raise ValueError("Invalid reference probability")
    v = {p: rates.get(p, league) for p in q}
    if any(not math.isfinite(x) or x <= 0 for x in v.values()):
        raise ValueError("Invalid free-throw ratio")
    normalizer = sum(q[p] * v[p] for p in q)
    return {p: (1 - TRANSFER) * q[p] + TRANSFER * q[p] * v[p] / normalizer for p in q}


def select_bet(runners, probabilities, reference, reserve=False):
    candidates = []
    for row in runners:
        player, decimal = row["player_id"], row["decimal"]
        if not 1.2 <= decimal <= 26 or probabilities[player] <= reference[player] + 1e-12:
            continue
        probability = probabilities[player] * (.99 if reserve else 1)
        payoff = 1 + .98 * (decimal - 1)
        ev = probability * payoff - 1
        if ev >= .05:
            candidates.append({"player_id": player, "decimal": decimal,
                "probability": probability, "ev": ev,
                "unconverted_ev": reference[player] * payoff - 1,
                "probability_adjustment": probabilities[player] - reference[player]})
    return min(candidates, key=lambda r: (-r["ev"], r["player_id"])) if candidates else None
