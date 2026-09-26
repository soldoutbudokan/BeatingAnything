"""Same-clock paired-goal/Anytime price screen; never reads sport outcomes."""
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from inventory_nhl_powerplay_goals import audit, decimal, stamp, RAW as PRICES, ROOT

RAW = ROOT / "data/raw/nhl-goal-contract-screen-2026-09-26"
OUT = ROOT / "reports/nhl-goal-contract-screen-2026-09-26.json"
CARD = ROOT / "docs/hypotheses/hockey-goal-contract-price-consistency.md"


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run():
    rows_path = RAW / "price-reference-rows.csv"
    if OUT.exists() or rows_path.exists():
        raise FileExistsError("Preserve original screen outputs")
    base, coverage = audit()  # Read-only function; do not invoke the older main writer.
    cached, rows, rejects = {}, [], Counter()
    for row in base:
        file = row["source_file"]
        if file not in cached:
            raw = json.loads((PRICES / file).read_text())
            book = [b for b in raw["bookmakers"] if b["key"] == "fanduel"]
            assert len(book) == 1
            cached[file] = [m for m in book[0]["markets"] if m["key"] == "player_goal_scorer_anytime"]
        market = cached[file]
        if len(market) != 1:
            rejects["missing_or_duplicate_anytime_market"] += 1
            continue
        market = market[0]
        try:
            update = stamp(market["last_update"])
        except (KeyError, ValueError, TypeError):
            rejects["missing_or_invalid_anytime_clock"] += 1
            continue
        if update != stamp(row["market_update"]):
            rejects["unequal_contract_update_times"] += 1
            continue
        outcomes = [o for o in market["outcomes"] if o.get("description") == row["player"] and o.get("name") == "Yes"]
        if len(outcomes) != 1:
            rejects["missing_or_duplicate_literal_anytime_yes"] += 1
            continue
        try:
            anytime = decimal(outcomes[0]["price"])
        except (KeyError, ValueError):
            rejects["invalid_anytime_american"] += 1
            continue
        probability = (1 / row["over_decimal"]) / (1 / row["over_decimal"] + 1 / row["under_decimal"])
        ev = probability * (1 + .98 * (anytime - 1)) - 1
        direction = "higher" if anytime > row["over_decimal"] else "lower" if anytime < row["over_decimal"] else "equal"
        rows.append({**row, "anytime_american": outcomes[0]["price"], "anytime_decimal": anytime,
                     "anytime_update": update.isoformat(), "price_direction": direction,
                     "p_goal_reference": probability, "conditional_ev_after_cost": ev,
                     "within_decimal_range": 1.2 <= anytime <= 6, "selected": False})
    by_game = {}
    for index, row in enumerate(rows):
        if row["within_decimal_range"] and row["conditional_ev_after_cost"] >= .03:
            by_game.setdefault(row["game_id"], []).append((-row["conditional_ev_after_cost"], row["player"], index))
    for candidates in by_game.values():
        rows[min(candidates)[2]]["selected"] = True
    assert len(rows) + sum(rejects.values()) == len(base)
    RAW.mkdir(parents=True, exist_ok=True)
    with rows_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = PRICES / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    eligible = [r for r in rows if r["within_decimal_range"]]
    report = {
        "status": "conditional price-reference screen; no independent sporting forecast or execution claim",
        "screened_at_utc": datetime.now(timezone.utc).isoformat(), "declaration_commit": "9f65d05",
        "base_paired_goal_rows": len(base), "same_clock_rows": len(rows),
        "games": len({r["game_id"] for r in rows}), "price_direction": dict(Counter(r["price_direction"] for r in rows)),
        "rejections_from_base": dict(rejects), "rows_in_decimal_range": len(eligible),
        "positive_conditional_ev_rows_any_odds": sum(r["conditional_ev_after_cost"] > 0 for r in rows),
        "candidate_rows_before_one_per_game": sum(r["within_decimal_range"] and r["conditional_ev_after_cost"] >= .03 for r in rows),
        "selections": sum(r["selected"] for r in rows),
        "best_conditional_ev_any_odds": max(r["conditional_ev_after_cost"] for r in rows),
        "best_conditional_ev_in_decimal_range": max(r["conditional_ev_after_cost"] for r in eligible),
        "periods": {p: {"rows": len(g := [r for r in rows if r["period"] == p]),
                         "games": len({r["game_id"] for r in g}), "selections": sum(r["selected"] for r in g),
                         "best_conditional_ev": max(r["conditional_ev_after_cost"] for r in g)} for p in sorted({r["period"] for r in rows})},
        "target_outcomes_read": False, "forecast_loss": None, "roi": None,
        "sources": coverage["source_pins"] + [source(CARD), source(Path(__file__)),
                    source(ROOT / "tools/inventory_nhl_powerplay_goals.py")] +
                   [{"path": r["path"], "sha256": r["sha256"]} for r in manifest["files"]],
        "rows_artifact": source(rows_path),
        "limitations": ["Settlement equivalence is a hypothesis qualified by source rules and historical jurisdiction uncertainty.",
                        "Reference probabilities come from the same bookmaker's paired contract, not an independent fitted forecast.",
                        "Original receipt, accepted fills, suspension status and complete historical product terms are absent.",
                        "Repeated exploratory comparison in an already inspected archive; no untouched validation claim."]}
    OUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ["sources", "limitations"]}, indent=2))


if __name__ == "__main__":
    run()
