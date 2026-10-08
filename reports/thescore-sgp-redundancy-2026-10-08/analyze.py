#!/usr/bin/env python3
"""Reproduce this study from observed joint SGP prices (standard library only).

The four cells must form an exhaustive, disjoint partition under the same
settlement assumptions. Vig allocation is a model, not a true probability.
"""

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def decimal(american):
    if not math.isfinite(american) or abs(american) < 100:
        raise ValueError("Expected valid American odds with absolute value >= 100")
    return 1 + (american / 100 if american > 0 else 100 / -american)


def devig_partition(cells):
    if set(cells) != {"UU", "OU", "OO", "UO"}:
        raise ValueError("All four joint outcomes are required")
    q = {cell: 1 / decimal(odds) for cell, odds in cells.items()}
    total = sum(q.values())
    proportional = {cell: value / total for cell, value in q.items()}
    lo, hi = 0.0, 1.0
    while sum(value ** hi for value in q.values()) > 1:
        hi *= 2
    for _ in range(100):
        exponent = (lo + hi) / 2
        if sum(value ** exponent for value in q.values()) > 1:
            lo = exponent
        else:
            hi = exponent
    exponent = (lo + hi) / 2
    power = {cell: value ** exponent for cell, value in q.items()}
    assert math.isclose(sum(proportional.values()), 1.0, abs_tol=1e-12)
    assert math.isclose(sum(power.values()), 1.0, abs_tol=1e-12)
    return {"raw_implied_sum": total, "overround": total - 1,
            "proportional": proportional, "power": power,
            "power_exponent": exponent}


def analyze():
    raw = json.loads((ROOT / "raw-observations.json").read_text())
    reference = {}
    cells = {}
    for cell, index in {"UU": 4, "OU": 5, "OO": 6, "UO": 7}.items():
        row = raw["fanduel"][index]
        snap = row["snapshot"]
        rush, receive = ["Under" if side == "U" else "Over" for side in cell]
        assert f"Javonte Williams {rush} 68.5, Javonte Williams - Rushing Yds" in snap
        assert f"Javonte Williams {receive} 14.5, Javonte Williams - Receiving Yds" in snap
        odds = int(re.search(r'Same Game Parlay, Tampa Bay Buccaneers @ Dallas Cowboys, ([+-]\d+) Odds', snap).group(1))
        cells[cell] = odds
        reference[cell] = {"raw_index": index, "captured_at": row["captured_at"],
                           "american": odds, "decimal": decimal(odds)}
    sequence = []
    for index in [15, 16, 18, 19, 24, 25]:
        row = raw["score"][index]
        slip = row["slip"]
        assert "Under\n64.5\n\nJavonte Williams Total Rushing Yards" in slip
        assert "Under\n14.5\n\nJavonte Williams Total Receiving Yards" in slip
        added = "Javonte Williams Total Rushing + Receiving Yards" in slip
        if added:
            assert "Under\n84.5" in slip
        odds = int(re.search(r'\nPARLAY\n([+-]\d+)\nBet', slip).group(1))
        sequence.append({"raw_index": index, "captured_at": row["captured_at"],
                         "variant": "B" if added else "A", "american": odds})
    assert [row["american"] for row in sequence] == [193, 194, 193, 194, 193, 194]
    assert 64 + 14 < 84.5  # Exact implication for integer final yard totals.
    result = devig_partition(cells)
    offered = decimal(sequence[-1]["american"])
    result.update({
        "study_date": "2026-10-08", "reference_book": "FanDuel Ontario",
        "reference_cells": reference, "score_sequence": sequence,
        "reference_relation": "superset_of_target_completed_game_win_event",
        "target_decimal": offered,
        "target_break_even_probability": 1 / offered,
        "gross_payout_improvement_fraction": offered / decimal(sequence[0]["american"]) - 1,
        "ev_bound_type": "model_dependent_upper_bound_conditional_on_common_settlement",
        "proportional_ev_upper_bound": offered * result["proportional"]["UU"] - 1,
        "power_ev_upper_bound": offered * result["power"]["UU"] - 1,
        "exact_target_ev": None,
    })
    return result


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, allow_nan=False))
