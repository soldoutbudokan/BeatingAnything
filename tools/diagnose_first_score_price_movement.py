"""Exploratory later-price check; never changes the frozen 2026 selections."""
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import statistics

from beating.first_score_wedge import convert, normalized_prices
from tools.validate_nba_first_score_2026 import (
    ROOT, PRICES, FORECASTS, MANIFEST, state_at, clock, digest, encoded, identity_inputs,
)

PLAN = ROOT / "docs/nba-first-score-price-movement-diagnostic-2026-09-19.md"
REPORT = ROOT / "reports/nba-first-score-price-movement-2026-09-19.json"


def later_book(history, book, original, decision, later):
    players = history.get("bookmakers", {}).get(book, {}).get("markets", {}).get("112604", {}).get("outcomes", {}).get("112604", {}).get("players", {})
    states, reason = state_at(players, later)
    expected = {r["provider_player_id"]: r for r in original}
    same = states is not None and set(states) == set(expected)
    probabilities = None
    if same:
        probabilities = normalized_prices([{**row, **states[pid]} for pid, row in expected.items()])
    return {"status": reason or ("same_complete_candidate_set" if same else "candidate_set_missing_or_changed"),
        "active_player_count": len(states) if states is not None else None,
        "new_entries_since_decision": sum(clock(row["entry_time"]) > decision for row in (states or {}).values()),
        "max_entry_age_seconds": max((row["entry_age_seconds"] for row in (states or {}).values()), default=None),
        "states": states, "probabilities": probabilities}


def main():
    if REPORT.exists():
        raise FileExistsError("Diagnostic already recorded")
    manifest = json.loads(MANIFEST.read_text())
    if digest(FORECASTS) != manifest["forecast_sha256"]:
        raise ValueError("Frozen forecast changed")
    for path, sha in {**manifest["input_sha256"], **manifest["code_sha256"]}.items():
        if digest(ROOT / path) != sha:
            raise ValueError("Original source/code changed: " + path)
    forecasts = json.loads(FORECASTS.read_text())["forecasts"]
    histories = {}
    for path in PRICES.glob("*-historical-odds.json"):
        data = json.loads(path.read_text())
        if "bookmakers" in data:
            histories[data["fixtureId"]] = data
    _, rates, league, _, _ = identity_inputs()
    rows = []
    for f in forecasts:
        decision = clock(f["decision"])
        later = clock(f["start"]) - timedelta(seconds=60)
        books = {book: later_book(histories[f["fixture_id"]], book, f[key], decision, later)
                 for book, key in (("fanduel", "runners"), ("betmgm", "reference_runners"))}
        selected = None
        if f["bet"]:
            bet = f["bet"]
            player = bet["player_id"]
            entry = next(r for r in f["runners"] if r["player_id"] == player)
            selected = {"player_id": player, "name": entry["name"], "entry_decimal": bet["decimal"],
                        "entry_converted_ev": bet["ev"], "entry_unconverted_ev": bet["unconverted_ev"]}
            fd = books["fanduel"]
            state = (fd["states"] or {}).get(entry["provider_player_id"])
            selected.update({"later_selected_active": state is not None,
                "later_decimal": state["decimal"] if state else None,
                "later_entry_age_seconds": state["entry_age_seconds"] if state else None,
                "new_selected_entry": clock(state["entry_time"]) > decision if state else None,
                "selected_price_changed": state["decimal"] != bet["decimal"] if state else None,
                "price_movement": bet["decimal"] / state["decimal"] - 1 if state else None})
            p = fd["probabilities"]
            selected.update({"fd_normalized_probability_change": p[player] - f["probabilities"]["market"][player] if p else None,
                "fd_later_no_vig_entry_ev": p[player] * (1 + .98 * (bet["decimal"] - 1)) - 1 if p else None})
            q = books["betmgm"]["probabilities"]
            p = convert(q, rates, league) if q else None
            selected["mgm_later_converted_entry_ev"] = p[player] * (1 + .98 * (bet["decimal"] - 1)) - 1 if p else None
        rows.append({"fixture_id": f["fixture_id"], "decision": f["decision"], "later_cutoff": later.isoformat(),
            "books": {b: {k: v for k, v in data.items() if k != "states"} for b, data in books.items()},
            "selection": selected})
    bets = [r["selection"] for r in rows if r["selection"] is not None]
    metrics = {}
    for metric in ("price_movement", "fd_normalized_probability_change", "fd_later_no_vig_entry_ev", "mgm_later_converted_entry_ev"):
        values = [r[metric] for r in bets if r[metric] is not None]
        metrics[metric] = {"observed": len(values), "missing": len(bets)-len(values),
            "mean": statistics.mean(values) if values else None, "median": statistics.median(values) if values else None,
            "positive": sum(x > 1e-12 for x in values), "negative": sum(x < -1e-12 for x in values),
            "zero": sum(abs(x) <= 1e-12 for x in values)}
    report = {"purpose": "Exploratory later provider-price diagnostic, not verified CLV or a new betting strategy",
        "plan_sha256": digest(PLAN), "script_sha256": digest(Path(__file__)), "forecast_sha256": digest(FORECASTS),
        "source_manifest_sha256": digest(MANIFEST), "later_seconds_before_start": 60,
        "forecast_games": len(rows), "original_selections": len(bets),
        "book_board_status": {b: dict(Counter(r["books"][b]["status"] for r in rows)) for b in ("fanduel", "betmgm")},
        "selected_active_later": sum(r["later_selected_active"] for r in bets),
        "new_selected_entries": sum(r["new_selected_entry"] is True for r in bets),
        "selected_prices_changed": sum(r["selected_price_changed"] is True for r in bets),
        "metrics": metrics, "rows": rows,
        "limitations": ["Outcomes already inspected before diagnostic declaration; no new outcome test",
            "Provider state persistence assumed; original market identity and executable availability unverified",
            "Fixed pregame comparison is not the last tradable bookmaker close; missing boards retained",
            "Only seven original bets, no inference or advancement; no new wager/alert/schedule"]}
    REPORT.write_bytes(encoded(report))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
