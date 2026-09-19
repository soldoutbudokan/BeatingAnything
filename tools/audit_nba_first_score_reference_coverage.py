#!/usr/bin/env python3
"""Count fresh matched reference boards without treating market rules as equal."""
from collections import Counter, defaultdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_nba_first_basket_archive import RAW, board_status, clock, csv_rows, norm, verify
from tools.backtest_nba_first_basket import INVENTORY, INVENTORY_SHA


def main():
    if hashlib.sha256(INVENTORY.read_bytes()).hexdigest() != INVENTORY_SHA:
        raise ValueError("Audited FanDuel inventory changed")
    raw, source = verify(RAW / "lefirstbasket/data/odds_first_basket.csv")
    prices = list(csv_rows(raw))
    fd = {}
    for b in sorted(json.loads(INVENTORY.read_text()), key=lambda b: clock(b["received_at"])):
        if b["status"] == "pregame_ten_runner_board":
            fd.setdefault(b["game_id"], b)
    groups = defaultdict(list)
    for r in prices:
        if r["bookmaker"] in ("draftkings", "betmgm", "betrivers", "bovada"):
            groups[(r["bookmaker"], r["game_id"], r["event_id"], r["insert_timestamp_utc"])].append(r)
    counts, accepted = defaultdict(Counter), defaultdict(dict)
    for (book, gid, eid, receipt), rows in sorted(groups.items()):
        if gid not in fd:
            continue
        b = fd[gid]
        counts[book]["boards_against_fixed_fd_cohort"] += 1
        start = min(clock(b["independent_start"]), clock(b["publisher_start"]))
        decision = max(clock(receipt), clock(b["received_at"]))
        status = board_status(rows, start)
        reason = None
        if eid != b["event_id"]:
            reason = "event_mismatch"
        elif status != "pregame_ten_runner_board":
            reason = "reference_" + status
        elif decision >= start - timedelta(seconds=60):
            reason = "joint_decision_too_late"
        elif (max((decision-clock(r["update_time"])).total_seconds() for r in rows) > 300 or
              max((decision-clock(r["quote_time"])).total_seconds() for r in b["prices"]) > 300):
            reason = "joint_price_stale"
        elif {norm(r["name"]) for r in rows} != {norm(r["name"]) for r in b["prices"]}:
            reason = "candidate_sets_differ"
        if reason:
            counts[book][reason] += 1
        else:
            counts[book]["matched_same_candidate_fresh_boards"] += 1
            accepted[book].setdefault(gid, {"game_id": gid, "event_id": eid, "decision": decision.isoformat()})
    report = {"purpose": "Source coverage only; no cross-book probabilities, predictions, selections or returns calculated",
        "fanduel_source_boards": len(fd), "source": source,
        "join_rule": "Same event ID and exact normalized ten-player name set; each complete board fresh within 300 seconds at joint receipt and at least 60 seconds pregame. Earliest accepted FD board fixed by prior audit.",
        "book_counts": {k: dict(v) for k, v in counts.items()},
        "distinct_matched_games": {k: len(v) for k, v in accepted.items()},
        "market_identity_status": "Normalized player_first_basket requests verified, but historical displayed definition/jurisdiction not recovered for each reference quote. Counts do not imply same settlement or an established first-field-goal reference.",
        "outcome_independent": True}
    output = ROOT / "reports/nba-first-score-wedge-price-coverage-2026-09-19.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    ledger = ROOT / "data/raw/nba-first-score-wedge-2026-09-19/reference-coverage.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({k: list(v.values()) for k, v in accepted.items()}, indent=2) + "\n")
    print(json.dumps(report["distinct_matched_games"], indent=2))


if __name__ == "__main__":
    main()
