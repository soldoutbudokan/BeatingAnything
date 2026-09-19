#!/usr/bin/env python3
"""Card 42: fixed prior-season first-score/first-field-goal disagreement screen."""
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_nba_first_basket_archive import first_score, verify

RAW = ROOT / "data/raw/nba-first-score-wedge-2026-09-19"
DECLARATION_SHA = "b6e29430a178f5e985d053c01c637e7cbaa5dbdf5eef733198721add2e088723"
PBP_SHA = "62b609ea487d23aec11e6756d7477a8b1df3a1e57e97fc90c7230b62a5835af1"


def score_pair(plays):
    sequence = [r["sequence_number"] for r in plays]
    if any(s is None for s in sequence) or len(sequence) != len(set(sequence)):
        raise ValueError("invalid_or_duplicate_sequence")
    rows = sorted(plays, key=lambda r: r["sequence_number"])
    try:
        first = first_score(rows)
        field_goal = next(r for r in rows if r["scoring_play"] and r["score_value"] in (2, 3))
    except (ValueError, StopIteration):
        raise ValueError("missing_or_inconsistent_first_score_or_field_goal")
    if field_goal["period_number"] != 1 or field_goal["sequence_number"] < first["sequence_number"]:
        raise ValueError("invalid_first_field_goal_period_or_order")
    if any(not r["athlete_id_1"] or r["athlete_id_1"] <= 0 for r in (first, field_goal)):
        raise ValueError("missing_scorer_id")
    free_throw = first["score_value"] == 1
    if free_throw:
        if "free throw" not in (first["type_text"] or "").lower() or first["sequence_number"] == field_goal["sequence_number"]:
            raise ValueError("one_point_score_not_verified_free_throw")
    elif first["score_value"] not in (2, 3) or first["sequence_number"] != field_goal["sequence_number"]:
        raise ValueError("non_free_throw_first_score_disagreement")
    return {"first_score_is_free_throw": free_throw,
            "different_scorer": first["athlete_id_1"] != field_goal["athlete_id_1"]}


def main():
    import pyarrow.parquet as pq
    declaration = json.loads((RAW / "declaration.json").read_text())
    if declaration["sha256"] != DECLARATION_SHA or hashlib.sha256((ROOT / declaration["path"]).read_bytes()).hexdigest() != DECLARATION_SHA:
        raise ValueError("Fixed declaration changed")
    path = RAW / "play_by_play_2024.parquet"
    _, source = verify(path)
    if source["sha256"] != PBP_SHA:
        raise ValueError("Pinned prior-season source changed")
    columns = ["game_id", "game_date", "sequence_number", "period_number", "scoring_play", "score_value",
               "home_score", "away_score", "athlete_id_1", "type_text"]
    groups = defaultdict(list)
    for row in pq.read_table(path, columns=columns).to_pylist():
        groups[row["game_id"]].append(row)
    valid, exclusions = [], []
    for gid, plays in sorted(groups.items()):
        dates = {str(r["game_date"]) for r in plays}
        try:
            if len(dates) != 1:
                raise ValueError("inconsistent_game_date")
            day = date.fromisoformat(next(iter(dates)))
            result = score_pair(plays)
            valid.append({"game_id": gid, "date": day.isoformat(), "week": day.strftime("%G-W%V"), **result})
        except ValueError as exc:
            exclusions.append({"game_id": gid, "reason": str(exc)})
    n = len(valid)
    switched = sum(r["different_scorer"] for r in valid)
    free_throws = sum(r["first_score_is_free_throw"] for r in valid)
    ledger = RAW / "screen-ledger.json"
    ledger.write_text(json.dumps({"valid": valid, "excluded": exclusions}, indent=2) + "\n")
    report = {"card": 42, "purpose": "Descriptive settlement-difference screen; no prices, model or ROI",
        "declaration": declaration, "source": source, "source_games": len(groups), "valid_games": n,
        "exclusions": dict(Counter(r["reason"] for r in exclusions)),
        "date_range": [min(r["date"] for r in valid), max(r["date"] for r in valid)],
        "calendar_week_blocks": len({r["week"] for r in valid}),
        "free_throw_first_scores": free_throws, "free_throw_first_score_rate": free_throws / n,
        "different_first_score_and_field_goal_winners": switched, "different_winner_rate": switched / n,
        "free_throw_first_score_same_field_goal_winner": free_throws - switched,
        "fixed_gate": {"minimum_games": 1000, "minimum_different_winners": 50, "minimum_different_winner_rate": .05,
                       "passed": n >= 1000 and switched >= 50 and switched / n >= .05},
        "ledger_path": str(ledger.relative_to(ROOT)), "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "interpretation": "Market definitions differ materially only if the fixed gate passes; this does not establish that FanDuel prices ignore the difference."}
    out = ROOT / "reports/nba-first-score-wedge-screen-2026-09-19.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
