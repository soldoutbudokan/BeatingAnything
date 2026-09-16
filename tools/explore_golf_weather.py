#!/usr/bin/env python3
"""G10: predeclared opening-round weather covariance screen, offline only.

--prepare builds source-joined player rounds. --compare requires completed
weather acquisition; it does not fetch, tune or replace missing weather.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import random
from statistics import mean, variance
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.golf_collect import decode_payloads
from explore_golf_sunday import complete_score, format_exclusion

RAW = ROOT / "data/raw/golf-weather"
GROUPS = ROOT / "data/raw/golf-weather-groups"
INVENTORY = ROOT / "reports/golf-weather-group-inventory-2026-09-14.json"
REPORT = ROOT / "reports/golf-weather-screen-2026-09-14"
MULTICOURSE = {"The American Express", "Farmers Insurance Open",
               "AT&T Pebble Beach Pro-Am", "The RSM Classic"}


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def norm(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if c.isalnum())


def source(path):
    return {"file": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare():
    inventory = json.loads(INVENTORY.read_text())
    targets = {e["espn_id"]: e for e in inventory["events"]}
    if len(targets) != 40:
        raise ValueError("Declared event cohort changed")
    sources = [source(INVENTORY)]
    events = []
    for year in (2024, 2025):
        path = ROOT / f"data/raw/golf-sport/scoreboard-{year}.json"
        sources.append(source(path))
        events.extend(json.loads(path.read_text())["events"])
    histories = defaultdict(list)
    rows, omissions, history_exclusions, audit = [], [], [], []
    for event in sorted(events, key=lambda e: (e.get("date", ""), e.get("id", ""))):
        if not all(event.get(k) for k in ("date", "endDate", "id", "name")):
            history_exclusions.append({"event_id": event.get("id"), "reason": "missing metadata"})
            continue
        start, end = dt(event["date"]), dt(event["endDate"])
        if end < start:
            raise ValueError("Event ends before it starts")
        reason = format_exclusion(event["name"], start.year)
        if event["name"] in MULTICOURSE:
            reason = "multiple courses"
        if len(event.get("competitions", [])) != 1 or not event.get("status", {}).get("type", {}).get("completed"):
            reason = "not one completed competition"
        if reason:
            history_exclusions.append({"event_id": event["id"], "name": event["name"], "reason": reason})
            continue
        players = event["competitions"][0].get("competitors", [])
        if any(p.get("type") != "athlete" or not p.get("id") for p in players):
            raise ValueError("Retained player lacks individual identity")
        if len({p["id"] for p in players}) != len(players):
            raise ValueError("Duplicate player in event")
        scores = {}
        for p in players:
            rs = [r for r in p.get("linescores", []) if r.get("period") in (1, 2, 3, 4)]
            if len({r["period"] for r in rs}) != len(rs):
                raise ValueError("Duplicate raw round")
            scores[p["id"]] = {r["period"]: v for r in rs if (v := complete_score(r)) is not None}
        means = {r: mean(rs[r] for rs in scores.values() if r in rs)
                 for r in (1, 2, 3, 4) if any(r in rs for rs in scores.values())}
        if event["id"] in targets:
            target = targets[event["id"]]
            path = GROUPS / (target["pga_id"] + "-teetimes.json")
            sources.append(source(path))
            payload = decode_payloads(json.loads(path.read_text()))["data"]["teeTimesCompressedV2"]["payload"]
            if payload["id"] != target["pga_id"]:
                raise ValueError("Wrong official event")
            names = defaultdict(list)
            for p in players:
                names[norm(p["athlete"]["displayName"])].append(p)
            count = Counter()
            for rnd in payload["rounds"]:
                if rnd["roundInt"] not in (1, 2):
                    continue
                official_names = Counter(norm(p["displayName"]) for g in rnd["groups"] for p in g["players"])
                official_ids, used_espn_ids = set(), set()
                for group in rnd["groups"]:
                    if not group.get("courseId") or not isinstance(group.get("teeTime"), (int, float)):
                        raise ValueError("Group lacks course/time")
                    group_id = f"{rnd['roundInt']}:{group['groupNumber']}:{group['startTee']}"
                    for official in group["players"]:
                        if official["id"] in official_ids:
                            raise ValueError("Duplicate official player round")
                        official_ids.add(official["id"])
                        count["official_player_rounds"] += 1
                        key = norm(official["displayName"])
                        matches = names.get(key, [])
                        reason = None
                        if len(matches) != 1 or official_names[key] != 1:
                            reason = "unmatched_or_ambiguous_name"
                        else:
                            player = matches[0]
                            if player["id"] in used_espn_ids:
                                raise ValueError("Nonunique cross-source player join")
                            used_espn_ids.add(player["id"])
                            score = scores[player["id"]].get(rnd["roundInt"])
                            prior = sorted((h for h in histories[player["id"]] if h[0] < start),
                                           key=lambda h: (h[0], h[1], h[2]))[-20:]
                            if score is None:
                                reason = "incomplete_or_inconsistent_round"
                            elif len(prior) < 10:
                                reason = "insufficient_prior_rounds"
                        if reason:
                            count[reason] += 1
                            omissions.append({"pga_id": target["pga_id"], "round": rnd["roundInt"],
                                              "pga_player_id": official["id"], "name": official["displayName"], "reason": reason})
                            continue
                        count["joined_complete_prior_eligible"] += 1
                        rows.append({"pga_id": target["pga_id"], "event_id": event["id"], "event_name": event["name"],
                                     "round": rnd["roundInt"], "course_id": str(group["courseId"]),
                                     "group_id": group_id, "tee_time_ms": group["teeTime"],
                                     "player_id": str(player["id"]), "pga_player_id": str(official["id"]),
                                     "name": player["athlete"]["displayName"], "score": score,
                                     "prior_ability": mean(h[3] for h in prior), "prior_count": len(prior),
                                     "latest_prior_end": prior[-1][0].isoformat(), "event_start": event["date"]})
            audit.append({"pga_id": target["pga_id"], "event_id": event["id"], "counts": dict(count)})
        # All verified completed rounds contribute, including shortened events.
        for pid, rs in scores.items():
            for r, score in rs.items():
                histories[pid].append((end, event["id"], r, score - means[r]))
    if {a["event_id"] for a in audit} != set(targets):
        raise ValueError("Declared target event omitted")
    if any(dt(r["latest_prior_end"]) >= dt(r["event_start"]) for r in rows):
        raise ValueError("Prior chronology violation")
    prepared = {"rows": rows, "omissions": omissions, "event_audit": audit,
                "history_exclusions": history_exclusions, "sources": sources,
                "scope": "Preparation only; no weather classification or pair variance compared"}
    (RAW / "prepared.json").write_text(json.dumps(prepared, indent=2) + "\n")
    print(json.dumps({"prepared_player_rounds": len(rows), "events": len(audit), "omissions": len(omissions)}))


def pool(cells):
    total = sum(c["same_pairs"] for c in cells)
    if not total:
        return {"same_variance": None, "different_time_variance": None, "variance_reduction": None}
    same = sum(c["same_pairs"] * c["same_variance"] for c in cells) / total
    different = sum(c["same_pairs"] * c["different_time_variance"] for c in cells) / total
    return {"same_variance": same, "different_time_variance": different,
            "variance_reduction": 1 - same / different if different > 0 else None,
            "same_pair_mean": sum(c["same_pairs"] * c["same_mean"] for c in cells) / total,
            "different_time_pair_mean": sum(c["same_pairs"] * c["different_time_mean"] for c in cells) / total}


def compare():
    weather_path = RAW / "rounds.json"
    acquisition_path = ROOT / "reports/golf-weather-acquisition-2026-09-14.json"
    acquisition = json.loads(acquisition_path.read_text())
    if (acquisition.get("complete") is not True or acquisition.get("pending_event_hours") != 0
            or acquisition.get("stop_reason") is not None):
        raise ValueError("Finish the declared acquisition before comparing scores")
    plan_path = ROOT / acquisition["plan_file"]
    plan = json.loads(plan_path.read_text())
    for path, expected_hash in (
        (plan_path, acquisition.get("plan_sha256")),
        (weather_path, acquisition.get("rounds_sha256")),
        (RAW / "hours.json", acquisition.get("hours_sha256")),
        (ROOT / plan["inventory"]["path"], plan["inventory"]["sha256"]),
        (ROOT / plan["venues"]["path"], plan["venues"]["sha256"]),
        (ROOT / "reports/golf-weather-declaration-2026-09-14.md", plan["declaration_sha256"]),
    ):
        if source(path)["sha256"] != expected_hash:
            raise ValueError(f"Changed acquisition input or output: {path}")
    weather = json.loads(weather_path.read_text())
    expected = {(e["pga_id"], r["round"]) for e in json.loads(INVENTORY.read_text())["events"] for r in e["rounds"]}
    observed = {(r["pga_id"], r["round"]) for r in weather}
    if len(weather) != 80 or observed != expected:
        raise ValueError("Weather acquisition must account for all 80 declared rounds")
    if any(r.get("reason") in {"pending", "acquisition_incomplete", "budget_exhausted"} for r in weather):
        raise ValueError("Complete bounded acquisition before scoring comparison")
    prepared_path = RAW / "prepared.json"
    prepared = json.loads(prepared_path.read_text())
    for record in prepared["sources"]:
        if source(ROOT / record["file"])["sha256"] != record["sha256"]:
            raise ValueError(f"Prepared score/group source changed: {record['file']}")
    players = defaultdict(list)
    for r in prepared["rows"]:
        players[(r["pga_id"], r["round"], r["course_id"])].append(r)
    cells, skipped, contributing_groups, contributing_players = [], [], set(), set()
    for w in weather:
        if not w["classified"] or not w["volatile"]:
            continue
        rr = players.get((w["pga_id"], w["round"], str(w["course_id"])), [])
        buckets = defaultdict(lambda: {"same": [], "different": [], "groups": set(), "players": set()})
        for a, b in combinations(sorted(rr, key=lambda r: int(r["player_id"])), 2):
            same = a["group_id"] == b["group_id"]
            if not same and abs(a["tee_time_ms"] - b["tee_time_ms"]) < 180 * 60000:
                continue
            gap = a["prior_ability"] - b["prior_ability"]
            bucket = buckets[math.floor(abs(gap) / .5)]
            bucket["same" if same else "different"].append(a["score"] - b["score"] - gap)
            if same:
                bucket["groups"].add((a["pga_id"], a["group_id"]))
            bucket["players"].update((a["player_id"], b["player_id"]))
        for bin_id, bucket in sorted(buckets.items()):
            base = {"pga_id": w["pga_id"], "round": w["round"], "course_id": str(w["course_id"]),
                    "ability_gap_bin": bin_id, "same_pairs": len(bucket["same"]), "different_time_pairs": len(bucket["different"])}
            if min(base["same_pairs"], base["different_time_pairs"]) < 2:
                skipped.append(base)
                continue
            cells.append({**base, "same_variance": variance(bucket["same"]),
                          "different_time_variance": variance(bucket["different"]),
                          "same_mean": mean(bucket["same"]), "different_time_mean": mean(bucket["different"])})
            contributing_groups.update(bucket["groups"])
            contributing_players.update(bucket["players"])
    result = pool(cells)
    by_event = defaultdict(list)
    for c in cells:
        by_event[c["pga_id"]].append(c)
    keys, draws = sorted(by_event), []
    rng = random.Random(20260915)
    if len(keys) >= 2:
        for _ in range(5000):
            sampled = [c for k in rng.choices(keys, k=len(keys)) for c in by_event[k]]
            draws.append(pool(sampled)["variance_reduction"])
    draws = sorted(d for d in draws if d is not None)
    enough = len(contributing_groups) >= 300 and len(keys) >= 10
    effect = result["variance_reduction"]
    status = "unresolved: insufficient sample" if not enough or effect is None else "sport-side advance to price investigation" if effect >= .1 else "sport-side dead at fixed screen"
    report = {"as_of_local_date": "2026-09-14", "status": status, **result,
              "actual_groups": len(contributing_groups), "events": len(keys), "players": len(contributing_players),
              "same_pairs": sum(c["same_pairs"] for c in cells), "different_time_pairs": sum(c["different_time_pairs"] for c in cells),
              "sample_gate_met": enough, "volatile_rounds": sum(w["classified"] and w["volatile"] for w in weather),
              "unclassified_rounds": [w for w in weather if not w["classified"]],
              "event_bootstrap_95_interval": [draws[int(.025 * len(draws))], draws[int(.975 * len(draws))]] if draws else None,
              "bootstrap": {"seed": 20260915, "requested_replicates": 5000,
                            "valid_replicates": len(draws),
                            "conditioning": "Resample contributing events and retain their course-round cells; weather labels and original sample gate remain fixed."},
              "cells": cells, "omitted_cells": skipped, "event_results": [{"pga_id": k, **pool(by_event[k])} for k in keys],
              "sources": [source(acquisition_path), source(plan_path), source(weather_path), source(prepared_path), *prepared["sources"]],
              "player_attrition": prepared["event_audit"], "market_prices_compared": False}
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    shown = "undefined" if effect is None else f"{100*effect:.3f}%"
    REPORT.with_suffix(".md").write_text(f"""# G10 weather covariance screen

**{status}.** Same-group score-difference variance reduction: **{shown}** across {len(contributing_groups)} actual groups and {len(keys)} events. The fixed gates require at least 10%, 300 groups and ten events.

The [declaration](golf-weather-declaration-2026-09-14.md) fixes the 40-event cohort, operational forecast run, complete weather window, prior ability, half-stroke gap bins, 180-minute control separation and event bootstrap. The [JSON report](golf-weather-screen-2026-09-14.json) retains variances, means, all contributing cells, attrition and source hashes. There were {report['volatile_rounds']} classified volatile rounds and {len(report['unclassified_rounds'])} unclassified rounds. Event-bootstrap interval: {report['event_bootstrap_95_interval']} in fractional reduction units.

This is an observational sport-side comparison. Scheduled tee windows approximate actual exposure; a round spanning dates can include nonplaying overnight hours in its fixed first-to-last wind-range window. Retrospectively fetched groups and archived model modification times do not establish a historical betting decision's complete information set. Repeated players, venue dependence, group selection and noisy ability remain limitations. The bootstrap conditions on the contributing events and preserves their original cells; its seed and requested/valid replicate counts are in the JSON. No FanDuel prices, returns or internal model were tested. No betting edge is established.

Reproduce offline: `state/runtime/research-venv/bin/python tools/explore_golf_weather.py --compare`.
""")
    print(json.dumps({k: report[k] for k in ("status", "variance_reduction", "actual_groups", "events", "same_pairs", "different_time_pairs")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--prepare", action="store_true")
    commands.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    prepare() if args.prepare else compare()


if __name__ == "__main__":
    main()
