#!/usr/bin/env python3
"""Freeze and grade the single conditional Card 42 price experiment."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import statistics
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.first_score_wedge import convert, normalized_prices, prior_rates, select_bet
from tools import backtest_nba_first_basket as old
from tools.audit_nba_first_basket_archive import NBA, RAW, SUPPORT, clock, csv_rows, norm, verify

PROTOCOL = ROOT / "docs/nba-first-score-wedge-price-protocol-2026-09-19.md"
PROTOCOL_SHA = "bf501a2f88269a2cb573e56d86fd51c536ed6e945b61924d19d093f3893d5085"
OLD_FORECAST_SHA = "99900cee748540e74fbc51cc2da34af666d0c516a4f47f945fc8bbd7ed14742a"
OUT = ROOT / "data/raw/nba-first-score-wedge-2026-09-19"
FORECASTS = OUT / "price-forecasts.json"
MANIFEST = ROOT / "reports/nba-first-score-wedge-forecast-freeze-2026-09-19.json"
REPORT = ROOT / "reports/nba-first-score-wedge-backtest-2026-09-19.json"
CODE = [Path(__file__), ROOT / "beating/first_score_wedge.py", *old.CODE]
BASELINES = ("reference", "market")
digest, encoded = old.digest, old.encoded


def price_inputs():
    """Only prior stats, fixture attributes, offered prices and frozen eligibility."""
    if digest(PROTOCOL) != PROTOCOL_SHA or digest(old.FORECASTS) != OLD_FORECAST_SHA:
        raise ValueError("Declared protocol or original forecast cohort changed")
    if digest(old.INVENTORY) != old.INVENTORY_SHA:
        raise ValueError("Audited price inventory changed")
    previous = json.loads(old.MANIFEST.read_text())
    if previous["forecast_sha256"] != OLD_FORECAST_SHA:
        raise ValueError("Original manifest does not match forecast cohort")
    for path, expected in previous["code_sha256"].items():
        if digest(ROOT / path) != expected:
            raise ValueError("Original implementation changed")
    tree_raw, source = verify(RAW / "lefirstbasket-tree.json")
    tree = json.loads(tree_raw)
    if tree["sha"] != old.PIN or tree["truncated"]:
        raise ValueError("Publisher tree changed")
    entries = {r["path"]: r["sha"] for r in tree["tree"]}
    sources = [source]
    loaded = {}
    for path, fields in (
        ("data/rosters.nosync/rosters_2024.csv", ("game_id", "player_id", "starter", "FG", "FT")),
        ("data/odds_first_basket.csv", None),
    ):
        raw, source = verify(RAW / "lefirstbasket" / path)
        if source["expected_git_blob"] != entries[path]:
            raise ValueError("Publisher source differs from pinned tree")
        sources.append(source)
        loaded[path] = list(csv_rows(raw, fields))
    raw, source = verify(NBA, SUPPORT[NBA])
    sources.append(source)
    seasons = defaultdict(set)
    for r in csv_rows(raw, ("game_id", "season_type")):
        seasons[r["game_id"]].add(r["season_type"])
    original = json.loads(old.FORECASTS.read_text())["forecasts"]
    if len(original) != 473 or len({r["game_id"] for r in original}) != 473:
        raise ValueError("Original eligibility count changed")
    # Explicit whitelist: never reuse old predictions, selections or outcome labels.
    keys = ("game_id", "espn_game_id", "nba_game_id", "home", "away", "quote_time", "received_at", "runners")
    original = [{k: f[k] for k in keys} for f in original]
    boards = {}
    for b in sorted(json.loads(old.INVENTORY.read_text()), key=lambda b: clock(b["received_at"])):
        if b["status"] == "pregame_ten_runner_board":
            boards.setdefault(b["game_id"], b)
    for f in original:
        b = boards[f["game_id"]]
        if f["received_at"] != b["received_at"] or f["nba_game_id"] != b["nba_game_id"]:
            raise ValueError("Original forecast does not match audited board")
        left = sorted((norm(r["name"]), r["decimal"], r["quote_time"]) for r in f["runners"])
        right = sorted((norm(r["name"]), r["decimal"], r["quote_time"]) for r in b["prices"])
        if left != right:
            raise ValueError("Original offered prices differ from inventory")
    return original, boards, seasons, loaded, sources


def restriction(gid, season_types):
    if season_types != {"regular-season"}:
        return "not_verified_regular_season"
    if datetime.strptime(gid[:8], "%Y%m%d").weekday() == 4:
        return "friday_promotion_day"
    return None


def match_reference(board, rows):
    """Check both boards at the same decision clock, including exact boundaries."""
    if len(rows) != 10 or len({norm(r["name"]) for r in rows}) != 10:
        return "not_ten_unique_runners"
    if {r["game_id"] for r in rows} != {board["game_id"]} or {r["event_id"] for r in rows} != {board["event_id"]}:
        return "event_mismatch"
    if len({r["insert_timestamp_utc"] for r in rows}) != 1 or len({r["update_time"] for r in rows}) != 1:
        return "mixed_reference_clocks"
    if any(not math.isfinite(float(r["price"])) or float(r["price"]) <= 1 for r in rows):
        return "invalid_price"
    if {norm(r["name"]) for r in rows} != {norm(r["name"]) for r in board["prices"]}:
        return "candidate_sets_differ"
    receipt = clock(rows[0]["insert_timestamp_utc"])
    fd_receipt = clock(board["received_at"])
    decision = max(receipt, fd_receipt)
    start = min(clock(board["independent_start"]), clock(board["publisher_start"]))
    if decision > start - timedelta(seconds=60):
        return "joint_decision_too_late"
    quote_receipts = [(clock(r["update_time"]), receipt) for r in rows]
    quote_receipts += [(clock(r["quote_time"]), fd_receipt) for r in board["prices"]]
    if any(q > received for q, received in quote_receipts):
        return "future_quote_update"
    if any((decision - q).total_seconds() > 300 for q, _ in quote_receipts):
        return "joint_price_stale"
    return None


def prepare():
    if FORECASTS.exists() or MANIFEST.exists():
        raise FileExistsError("Never overwrite frozen forecasts")
    original, boards, seasons, loaded, sources = price_inputs()
    earliest = min(datetime.strptime(f["game_id"][:8], "%Y%m%d").date() for f in original)
    rates, league, rate_counts = prior_rates(loaded["data/rosters.nosync/rosters_2024.csv"], earliest)
    groups = defaultdict(list)
    for r in loaded["data/odds_first_basket.csv"]:
        if r["bookmaker"] == "betmgm":
            groups[(r["game_id"], r["insert_timestamp_utc"], r["event_id"])].append(r)
    by_game = defaultdict(list)
    for key, rows in groups.items():
        by_game[key[0]].append(rows)
    forecasts, exclusions, reference_attrition = [], [], Counter()
    for f in sorted(original, key=lambda f: f["game_id"]):
        gid = f["game_id"]
        reason = restriction(gid, seasons[f["nba_game_id"]])
        if reason:
            exclusions.append({"game_id": gid, "reason": reason})
            continue
        chosen = None
        for rows in sorted(by_game[gid], key=lambda rows: (clock(rows[0]["insert_timestamp_utc"]), rows[0]["event_id"])):
            reason = match_reference(boards[gid], rows)
            reference_attrition[reason or "accepted_earliest_snapshot"] += 1
            if reason is None:
                chosen = rows
                break
        if chosen is None:
            exclusions.append({"game_id": gid, "reason": "no_eligible_reference"})
            continue
        names = {norm(r["name"]): r["player_id"] for r in f["runners"]}
        reference = [{"name": r["name"], "player_id": names[norm(r["name"])], "decimal": float(r["price"]),
                      "quote_time": r["update_time"]} for r in chosen]
        q = normalized_prices(reference)
        p = convert(q, rates, league)
        local_date = datetime.strptime(gid[:8], "%Y%m%d").date()
        decision = max(clock(f["received_at"]), clock(chosen[0]["insert_timestamp_utc"]))
        forecasts.append({**f, "event_id": boards[gid]["event_id"], "decision": decision.isoformat(),
            "period": "discovery" if local_date <= date(2025, 2, 28) else "replication",
            "week": local_date.strftime("%G-W%V"), "reference_runners": reference,
            "reference_received_at": chosen[0]["insert_timestamp_utc"],
            "probabilities": {"converted": p, "reference": q, "market": normalized_prices(f["runners"])},
            "rates": {player: rates.get(player, league) for player in q},
            "unseen_players": sorted(player for player in q if player not in rates),
            "bet": select_bet(f["runners"], p, q), "reserve_bet": select_bet(f["runners"], p, q, reserve=True)})
    now = datetime.now(timezone.utc).isoformat()
    payload = {"created_at": now, "protocol_sha256": PROTOCOL_SHA, "forecasts": forecasts,
               "exclusions": exclusions, "reference_attrition": dict(reference_attrition), "prior_rates": rate_counts}
    OUT.mkdir(parents=True, exist_ok=True)
    with FORECASTS.open("xb") as handle:
        handle.write(encoded(payload))
    evidence = {"created_at": now, "phase": "conditional predictions frozen before grading target outcomes",
        "conditional_reference_identity": True, "protocol_sha256": PROTOCOL_SHA,
        "original_forecast_sha256": OLD_FORECAST_SHA, "original_manifest_sha256": digest(old.MANIFEST),
        "inventory_sha256": old.INVENTORY_SHA, "forecast_path": str(FORECASTS.relative_to(ROOT)),
        "forecast_sha256": digest(FORECASTS), "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in CODE},
        "sources": sources, "input_games": len(original), "forecast_games": len(forecasts),
        "period_counts": dict(Counter(f["period"] for f in forecasts)),
        "exclusions": dict(Counter(r["reason"] for r in exclusions)),
        "reference_attrition": dict(reference_attrition), "prior_rates": rate_counts,
        "selection_counts": {period: {key: sum(f[key] is not None for f in forecasts if f["period"] == period)
            for key in ("bet", "reserve_bet")} for period in ("discovery", "replication")}}
    with MANIFEST.open("xb") as handle:
        handle.write(encoded(evidence))
    print(json.dumps({k: v for k, v in evidence.items() if k not in ("sources", "code_sha256")}, indent=2))


def bootstrap_ratios(rows):
    groups = defaultdict(lambda: [0.0, 0.0])
    for week, numerator, denominator in rows:
        groups[week][0] += numerator
        groups[week][1] += denominator
    blocks = np.array([groups[k] for k in sorted(groups)], dtype=float)
    result = {"weeks": len(blocks), "confidence": 1 - .05 / 16}
    if len(blocks) < 8:
        return {**result, "corrected_interval": None, "reason": "fewer_than_eight_weeks"}
    rng = np.random.default_rng(1729)
    draws = blocks[rng.integers(0, len(blocks), size=(10000, len(blocks)))].sum(axis=1)
    if np.any(draws[:, 1] <= 0):
        raise ValueError("Bootstrap denominator is empty")
    ratios = draws[:, 0] / draws[:, 1]
    return {**result, "corrected_interval": np.quantile(ratios, [.05 / 32, 1 - .05 / 32]).tolist(),
            "descriptive_95pct_interval": np.quantile(ratios, [.025, .975]).tolist()}


def summarize(rows, key):
    selected = [r for r in rows if r[key]["status"] != "no_bet"]
    counts = Counter(r[key]["status"] for r in selected)
    n = len(selected)
    profit = sum(r[key]["profit"] or 0.0 for r in selected)
    result = {"forecast_games": len(rows), "selected_bets": n,
        **{s: counts[s] for s in ("win", "loss", "void", "unresolved")},
        "nonvoid_settled_turnover": counts["win"] + counts["loss"], "original_stake_turnover": n,
        "known_profit": profit, "unresolved_all_loss_roi": (profit-counts["unresolved"]) / n if n else None,
        "unresolved_all_void_roi": profit / n if n else None,
        "roi_bootstrap_all_loss": bootstrap_ratios([(r["week"], -1 if r[key]["profit"] is None else r[key]["profit"], 1) for r in selected]),
        "roi_bootstrap_all_void": bootstrap_ratios([(r["week"], r[key]["profit"] or 0.0, 1) for r in selected]),
        "unresolved_reasons": dict(Counter(r[key]["reason"] for r in selected if r[key]["status"] == "unresolved")),
        "selected_positive_unconverted_ev": sum(r["bet_diagnostics"][key]["unconverted_ev"] > 0 for r in selected)}
    scored = [r for r in rows if r["scores"] is not None]
    result["scored_games"] = len(scored)
    result["probability_scores"] = {}
    for metric in ("log_loss", "brier"):
        entry = {"converted_mean": statistics.mean(r["scores"]["converted"][metric] for r in scored) if scored else None}
        for baseline in BASELINES:
            deltas = [(r["week"], r["scores"]["converted"][metric] - r["scores"][baseline][metric], 1) for r in scored]
            entry[baseline] = {"baseline_mean": statistics.mean(r["scores"][baseline][metric] for r in scored) if scored else None,
                "paired_difference": statistics.mean(r[1] for r in deltas) if deltas else None,
                "paired_bootstrap": bootstrap_ratios(deltas)}
        result["probability_scores"][metric] = entry
    return result


def grade():
    import pyarrow.parquet as pq
    manifest = json.loads(MANIFEST.read_text())
    if digest(FORECASTS) != manifest["forecast_sha256"] or digest(PROTOCOL) != PROTOCOL_SHA:
        raise ValueError("Frozen predictions or protocol changed")
    for path, expected in manifest["code_sha256"].items():
        if digest(ROOT / path) != expected:
            raise ValueError(f"Code changed after forecast freeze: {path}")
    if digest(old.MANIFEST) != manifest["original_manifest_sha256"]:
        raise ValueError("Original forecast provenance changed")
    *_, sources = price_inputs()
    if sources != manifest["sources"]:
        raise ValueError("Forecast source receipts changed")
    forecasts = json.loads(FORECASTS.read_text())["forecasts"]
    names, histories, rosters, _, grading_sources = old.source_inputs()
    ids = [int(f["espn_game_id"]) for f in forecasts]
    columns = ["game_id", "sequence_number", "period_number", "clock_display_value", "scoring_play",
               "score_value", "home_score", "away_score", "athlete_name_1"]
    plays = old.unique_index(pq.read_table(old.PBP, columns=columns, filters=[("game_id", "in", ids)]).to_pylist(), "game_id")
    published = old.unique_index(histories[2025], "game_id")
    roster_games = old.unique_index(rosters[2025], "game_id")
    rows = []
    for f in forecasts:
        outcome = old.grade_outcome(f, plays[int(f["espn_game_id"])], names, published.get(f["game_id"], []))
        roster = roster_games.get(f["game_id"], [])
        rows.append({"game_id": f["game_id"], "period": f["period"], "week": f["week"], "outcome": outcome,
            "settlement": old.settle_bet(f["bet"], outcome, roster, f["home"], f["away"]),
            "reserve_settlement": old.settle_bet(f["reserve_bet"], outcome, roster, f["home"], f["away"]),
            "bet_diagnostics": {"settlement": f["bet"], "reserve_settlement": f["reserve_bet"]},
            "scores": {m: old.scoring(f["probabilities"][m], outcome["scorer"]) for m in ("converted", *BASELINES)}
                       if outcome["status"] == "resolved" else None})
    graded_path = OUT / "price-graded.json"
    graded_path.write_bytes(encoded(rows))
    results = {p: summarize([r for r in rows if p == "pooled" or r["period"] == p], "settlement")
               for p in ("discovery", "replication", "pooled")}
    sensitivity = {p: summarize([r for r in rows if p == "pooled" or r["period"] == p], "reserve_settlement")
                   for p in ("discovery", "replication", "pooled")}
    d, r, p = (results[k] for k in ("discovery", "replication", "pooled"))
    lead = all(x["nonvoid_settled_turnover"] >= 50 and x["unresolved_all_loss_roi"] is not None and
               x["unresolved_all_loss_roi"] > 0 for x in (d, r)) and all(
               p["probability_scores"]["log_loss"][b]["paired_difference"] is not None and
               p["probability_scores"]["log_loss"][b]["paired_difference"] < 0 for b in BASELINES)
    roi_interval = r["roi_bootstrap_all_loss"]["corrected_interval"]
    loss_intervals = [r["probability_scores"]["log_loss"][b]["paired_bootstrap"]["corrected_interval"] for b in BASELINES]
    gates = {"conditional_exploratory_lead": lead, "conditional_historical_advantage": bool(lead and
        roi_interval and roi_interval[0] > 0 and all(i and i[1] < 0 for i in loss_intervals)), "edge_established": False}
    report = {"protocol_sha256": PROTOCOL_SHA, "forecast_freeze": str(MANIFEST.relative_to(ROOT)),
        "forecast_sha256": manifest["forecast_sha256"], "graded_path": str(graded_path.relative_to(ROOT)),
        "graded_sha256": digest(graded_path), "grading_sources": grading_sources, "forecast_games": len(rows),
        "outcome_counts": dict(Counter(r["outcome"]["status"] for r in rows)),
        "unlisted_scorers": sum(r["outcome"].get("listed") is False for r in rows),
        "outcome_unresolved_reasons": dict(Counter(r["outcome"]["reason"] for r in rows if r["outcome"]["status"] != "resolved")),
        "results": results, "reserve_probability_sensitivity": sensitivity, "gates": gates,
        "comparisons": 16, "bootstrap_draws": 10000, "bootstrap_seed": 1729,
        "limitations": ["Conditional interpretation of BetMGM quotes; original displayed labels and jurisdictions absent.",
            "Both periods previously inspected; exploratory, not untouched confirmation.",
            "BetMGM probabilities and the transfer allocation are approximations, not established fair prices.",
            "Friday/playoff exclusions do not establish that all other prices were unaffected by promotions.",
            "Retrospective stats are not proof of contemporaneous publication; unknown starters and labels remain unresolved.",
            "Historical offered quotes, not accepted wagers; no prospective cohort, alerts, schedules or wagers."]}
    REPORT.write_bytes(encoded(report))
    print(json.dumps({"outcomes": report["outcome_counts"], "gates": gates, "results": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "grade"))
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else grade()
