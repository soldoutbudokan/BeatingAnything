#!/usr/bin/env python3
"""Offline inventory of a completed golf capture; never a price/return model.

Keep complete matchups within one HTTP body. Repeated player drawers are
observations, not independent markets or a pool from which to pick best odds.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.golf_collect import payload_inventory  # noqa: E402


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def verified_bytes(root, artifact):
    path = (root / artifact["file"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Artifact outside capture root")
    raw = path.read_bytes()
    if len(raw) != artifact["bytes"] or digest(raw) != artifact["sha256"]:
        raise ValueError(f"Artifact hash/length mismatch: {path}")
    return raw


def decimal_american(value):
    if not isinstance(value, str) or not re.fullmatch(r"[+-]\d+", value):
        raise ValueError("Expected signed integer American odds")
    n = int(value)
    if abs(n) < 100:
        raise ValueError("Invalid American odds")
    return 1 + (n / 100 if n > 0 else 100 / -n)


def extract_drawers(payload, record):
    """Use the collector's exact-path attribution, not a catalog book label."""
    quotes = {q["path"]: q for q in record["quote_observations"]}
    selections, pairs, rejected = [], [], []
    for mi, market in enumerate(payload.get("playerMarkets", [])):
        for gi, group in enumerate(market.get("oddsDataGroup", [])):
            prefix = f"$.playerMarkets[{mi}].oddsDataGroup[{gi}]"
            base = {
                "tournament_id": record["context"]["tournament_id"],
                "cycle": record["context"]["cycle"],
                "drawer_player_id": record["context"]["player_id"],
                "market_type": market.get("marketType"),
                "title": group.get("title"), "group_id": group.get("groupId"),
                "betting_period_raw": market.get("bettingPeriod"),
                "response": record["response"], "source_url": record["source_url"],
                "request_at": record["collector_request_started_at"],
                "received_at": record["collector_response_received_at"],
                "provider_http_date": record.get("provider_http_date"),
                "source_clocks": record.get("source_clocks", []),
            }
            for di, data in enumerate(group.get("oddsData", [])):
                members = []
                for si, side in enumerate(data.get("group", [])):
                    path = f"{prefix}.oddsData[{di}].group[{si}].oddsValue"
                    quote = quotes.get(path, {})
                    link = quote.get("fanduel_selection_link", {})
                    if link.get("status") != "attributed":
                        continue
                    # Multi-player combination selections remain combinations.
                    players = side.get("players", [])
                    member = {"market_id": link["market_id"],
                              "selection_id": link["selection_id"],
                              "players": players, "american": side["oddsValue"],
                              "decimal": decimal_american(side["oddsValue"]),
                              "source_path": path, "book_labels": quote["book_labels"],
                              "selection_link": link}
                    members.append(member)
                    selections.append({**base, **member})
                if market.get("marketType") != "MATCHUP_PROPS":
                    continue
                valid = (data.get("type") == "GROUP" and data.get("groupCount") == 2
                         and len(data.get("group", [])) == len(members) == 2
                         and len({m["market_id"] for m in members}) == 1
                         and len({m["selection_id"] for m in members}) == 2
                         and all(len(m["players"]) == 1 and
                                 m["players"][0].get("playerId") for m in members))
                if valid:
                    valid = len({m["players"][0]["playerId"] for m in members}) == 2
                if not valid:
                    rejected.append({**base, "source_path": f"{prefix}.oddsData[{di}]",
                                     "reason": "not_a_complete_attributed_two_player_group"})
                    continue
                pairs.append({**base, "market_id": members[0]["market_id"],
                              "sides": sorted(members, key=lambda m: m["selection_id"]),
                              "overround": sum(1 / m["decimal"] for m in members) - 1})
    return selections, pairs, rejected


def pair_context(pair, tees, leaderboard):
    title = pair.get("title") or ""
    match = re.fullmatch(r"18 Hole Matchbet - Round ([1-4])", title)
    round_no = int(match[1]) if match else 1 if title == "72 Hole Matchbet" else None
    kind = "round_matchup" if match else "tournament_matchup" if round_no else "unknown"
    # The displayed title is recorded as a candidate interpretation. A conflicting
    # numeric period remains a conflict, never silently repaired from tee times.
    period_disagrees = bool(match and pair["betting_period_raw"] not in (None, round_no))
    group_match = re.match(r"\(Round ([1-4])\)", pair.get("group_id") or "")
    group_disagrees = bool(match and group_match and int(group_match[1]) != round_no)
    assignments = []
    for side in pair["sides"]:
        pid = side["players"][0]["playerId"]
        found = tees.get((pair["tournament_id"], pair["cycle"], round_no, pid), [])
        found = [x for x in found if datetime.fromisoformat(x["state_received_at"])
                 <= datetime.fromisoformat(pair["request_at"])]
        scoring = leaderboard.get((pair["tournament_id"], pair["cycle"], pid), {})
        if scoring and datetime.fromisoformat(scoring["state_received_at"]) > datetime.fromisoformat(pair["request_at"]):
            scoring = {}
        assignments.append({"player_id": pid,
                            "tee_assignment": found[0] if len(found) == 1 else None,
                            "assignment_count": len(found), "scoring_at_state_capture": scoring})
    known = all(x["tee_assignment"] for x in assignments)
    courses = sorted({x["tee_assignment"]["course_id"] for x in assignments}) if known else []
    receipt = datetime.fromisoformat(pair["received_at"])
    pre_scheduled_start = (all(receipt < datetime.fromisoformat(x["tee_assignment"]["tee_time"])
                               for x in assignments) if known else None)
    played = []
    for x in assignments:
        state = x["scoring_at_state_capture"]
        thru = str(state.get("thru", ""))
        holes = re.fullmatch(r"(\d{1,2})\*?", thru)
        played.append(bool(match and state.get("currentRound") == round_no
                           and (thru in ("F", "F*") or (holes and 1 <= int(holes[1]) <= 18))))
    return {"title_interpretation": kind, "title_round": round_no if match else None,
            "raw_period_disagrees_with_title": period_disagrees,
            "group_label_disagrees_with_title": group_disagrees,
            "assignments": assignments, "course_ids": courses,
            "cross_course_under_title": len(courses) > 1 if known else None,
            "same_official_group_under_title": (
                len({x["tee_assignment"]["group_number"] for x in assignments}) == 1
                if known else None),
            "received_before_both_scheduled_starts": pre_scheduled_start,
            "both_have_completed_holes_in_state_capture": all(played) if match else None}


def audit(root, run_id):
    records = [json.loads(line) for line in (root / "index.jsonl").read_text().splitlines()
               if line.strip()]
    records = [r for r in records if r.get("run_id") == run_id]
    ends = [r for r in records if r["kind"] == "run_end"]
    if len(ends) != 1:
        raise ValueError("Require one completed run")
    summary_bytes = (root / run_id / "summary.json").read_bytes()
    if json.loads(summary_bytes) != ends[0]:
        raise ValueError("Summary and index disagree")
    responses = [r for r in records if r["kind"] == "response"]
    artifacts, parsed = {}, []
    for record in responses:
        for key in ("request", "response", "decoded"):
            if record.get(key):
                verified_bytes(root, record[key])
                artifacts[record[key]["file"]] = record[key]
        if record.get("status") != 200 or record.get("error"):
            continue
        raw = verified_bytes(root, record.get("decoded") or record["response"])
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        parsed.append((record, payload))
    tees, leaderboard, tournaments, fields, catalogs = defaultdict(list), {}, [], [], []
    tee_rounds = []
    selections, pairs, rejected, drawer_counts = [], [], [], Counter()
    for record, payload in parsed:
        data = payload.get("data", {})
        tournaments.extend(data.get("tournaments", []))
        if "field" in data:
            field = data["field"]
            fields.append({"id": field["id"], "players": len(field.get("players", [])),
                           "alternates": len(field.get("alternates", [])),
                           "last_updated_raw": field.get("lastUpdated")})
        if "availableMarkets" in payload:
            catalogs.append({"context": record["context"], "markets": payload["availableMarkets"]})
        if "teeTimesCompressedV2" in data:
            state = data["teeTimesCompressedV2"]["payload"]
            for rd in state.get("rounds", []):
                tee_rounds.append({"tournament_id": state["id"], "cycle": record["context"]["cycle"],
                                   "round": rd["roundInt"], "round_status": rd["roundStatus"],
                                   "groups": len(rd.get("groups", [])),
                                   "state_received_at": record["collector_response_received_at"],
                                   "source_artifact": record["decoded"]})
                for group in rd.get("groups", []):
                    for player in group.get("players", []):
                        tees[(state["id"], record["context"]["cycle"], rd["roundInt"], player["id"])].append({
                            "course_id": group["courseId"], "group_number": group["groupNumber"],
                            "tee_time": datetime.fromtimestamp(group["teeTime"] / 1000, timezone.utc).isoformat(),
                            "start_tee": group["startTee"], "round_status": rd["roundStatus"],
                            "state_received_at": record["collector_response_received_at"]})
        if "leaderboardCompressedV3" in data:
            state = data["leaderboardCompressedV3"]["payload"]
            for player in state.get("players", []):
                scoring = player.get("scoringData", {})
                leaderboard[(state["id"], record["context"]["cycle"], player["id"])] = {
                    **{k: scoring.get(k) for k in ("currentRound", "thru", "thruSort", "backNine", "playerState", "roundStatus")},
                    "state_received_at": record["collector_response_received_at"]}
        if record["provider"] == "pga_rest" and record.get("context", {}).get("player_id"):
            inventory = payload_inventory(payload, odds=True)
            for key in ("quote_observations", "source_clocks", "unvalidated_price_fields"):
                if inventory[key] != record[key]:
                    raise ValueError(f"Index inventory disagrees with raw body: {key}")
            drawer_counts["requested"] += 1
            drawer_counts["with_prices" if inventory["quote_observations"] else "without_prices"] += 1
            a, b, c = extract_drawers(payload, record)
            selections.extend(a); pairs.extend(b); rejected.extend(c)
    for pair in pairs:
        pair["sport_context"] = pair_context(pair, tees, leaderboard)
    by_market = defaultdict(list)
    for pair in pairs:
        by_market[(pair["tournament_id"], pair["market_id"])].append(pair)
    matchups = []
    for (tid, mid), observations in sorted(by_market.items()):
        first = min(observations, key=lambda p: p["received_at"])
        sets = {tuple((s["selection_id"], s["players"][0]["playerId"]) for s in p["sides"])
                for p in observations}
        matchups.append({"tournament_id": tid, "market_id": mid,
                         "observations": len(observations),
                         "selection_identity_consistent": len(sets) == 1,
                         "price_versions": len({tuple(s["american"] for s in p["sides"]) for p in observations}),
                         "period_values": sorted({p["betting_period_raw"] for p in observations}, key=str),
                         "titles": sorted({p["title"] for p in observations}),
                         "any_period_title_disagreement": any(p["sport_context"]["raw_period_disagrees_with_title"] for p in observations),
                         "first_received_at": first["received_at"],
                         "last_received_at": max(p["received_at"] for p in observations),
                         "overround_min": min(p["overround"] for p in observations),
                         "overround_max": max(p["overround"] for p in observations),
                         "first_complete_observation": first})
    by_type = defaultdict(list)
    for side in selections:
        by_type[side["market_type"]].append(side)
    report = {
        "run": ends[0], "audit_script_sha256": digest(Path(__file__).read_bytes()),
        "summary_sha256": digest(summary_bytes), "run_index_records_sha256": digest(canonical(records)),
        "verified_artifacts": len(artifacts), "artifact_manifest_sha256": digest(canonical(artifacts)),
        "http_status_counts": dict(Counter(str(r.get("status")) for r in responses)),
        "tournaments": tournaments, "fields": fields, "catalogs": catalogs,
        "tee_time_rounds": tee_rounds,
        "player_drawers": dict(drawer_counts),
        "rest_selection_observations": len(selections),
        "unique_rest_market_selections": len({(s["tournament_id"], s["market_id"], s["selection_id"]) for s in selections}),
        "unique_rest_markets": len({(s["tournament_id"], s["market_id"]) for s in selections}),
        "market_types": {k: {"observations": len(v),
                              "market_ids": len({(s["tournament_id"], s["market_id"]) for s in v}),
                              "market_selections": len({(s["tournament_id"], s["market_id"], s["selection_id"]) for s in v})}
                         for k, v in sorted(by_type.items())},
        "complete_pair_observations": len(pairs), "distinct_complete_matchup_markets": len(matchups),
        "rejected_matchup_groups": rejected, "matchups": matchups,
        "jurisdiction_verified": False, "settlement_verified": False,
        "book_quote_update_clock_verified": False, "tradability_verified": False,
        "price_test_performed": False, "edge_established": False,
        "limitations": ["Catalog coverage is not sportsbook coverage.",
                        "All sides of each measured pair come from one response; responses are not atomic book snapshots.",
                        "Prices in different responses are not combined or chosen for a best-price synthetic pair.",
                        "Title interpretation does not repair inconsistent numeric bettingPeriod fields.",
                        "Unknown publisher source clocks, market jurisdiction, scoring convention and settlement remain unknown.",
                        "This inventory cannot demonstrate offer availability, EV, closing value or a betting edge."]}
    return report, {"artifact_manifest": artifacts, "selections": selections, "pairs": pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--root", type=Path, default=ROOT / "data/raw/golf-forward")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report, details = audit(args.root, args.run_id)
    derived = args.root / args.run_id / "price-inventory.json"
    derived.write_text(json.dumps(details, indent=2, sort_keys=True) + "\n")
    report["derived_inventory"] = {"file": str(derived.relative_to(args.root)),
                                   "sha256": digest(derived.read_bytes())}
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("verified_artifacts", "player_drawers",
          "rest_selection_observations", "unique_rest_market_selections", "unique_rest_markets",
          "market_types", "complete_pair_observations", "distinct_complete_matchup_markets")}, indent=2))


if __name__ == "__main__":
    main()
