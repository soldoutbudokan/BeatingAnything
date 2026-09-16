#!/usr/bin/env python3
"""Acquire official 2025 group/course identities for G1/G10, without scoring tests.

Run with --fetch once; subsequent runs replay the retained sources offline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.golf_collect import (PUBLIC_PGA_KEY, QUERIES, decode_payloads,
                                 http_request, parse_pga_html)

RAW = ROOT / "data/raw/golf-weather-groups"
SCHEDULE = ROOT / "data/raw/golf-weather-source/schedule-2025.html"
SCORES = ROOT / "data/raw/golf-sport/scoreboard-2025.json"
REPORT = ROOT / "reports/golf-weather-group-inventory-2026-09-14.json"
EXCLUDED = {
    "The American Express": "multiple courses",
    "Farmers Insurance Open": "multiple courses",
    "AT&T Pebble Beach Pro-Am": "multiple courses",
    "The RSM Classic": "multiple courses",
    "Zurich Classic of New Orleans": "team competition",
    "Ryder Cup": "team match play",
    "Barracuda Championship": "modified Stableford",
    "Hero World Challenge": "unofficial event",
    "PGA TOUR Q-School presented by Korn Ferry": "qualifying / multiple courses",
    "Grant Thornton Invitational": "team competition",
}
# Publisher spelling differences only. Schedule start dates are also checked.
NAMES = {
    "Arnold Palmer Invitational pres. by Mastercard":
        "Arnold Palmer Invitational presented by Mastercard",
    "the Memorial Tournament pres. by Workday":
        "the Memorial Tournament presented by Workday",
    "The Open": "The Open Championship",
}


def digest(path):
    return {"file": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def acquire(name, operation, variables, enabled):
    path = RAW / f"{name}.json"
    if not path.exists():
        if not enabled:
            return None
        request = {"query": QUERIES[operation], "operationName": operation,
                   "variables": variables}
        started = datetime.now(timezone.utc).isoformat()
        status, headers, body = http_request(
            "POST", "https://orchestrator.pgatour.com/graphql",
            json.dumps(request).encode(),
            {"Content-Type": "application/json", "x-api-key": PUBLIC_PGA_KEY}, 30)
        received = datetime.now(timezone.utc).isoformat()
        path.write_bytes(body)
        path.with_suffix(".meta.json").write_text(json.dumps({
            "url": "https://orchestrator.pgatour.com/graphql", "request": request,
            "request_started_utc": started, "received_utc": received,
            "status": status, **digest(path),
            "response_headers": {k: v for k, v in headers.items()
                                 if k.lower() in {"date", "last-modified", "etag", "content-type"}},
        }, indent=2) + "\n")
        print(f"{name}: HTTP {status}", flush=True)
        if status != 200:
            raise RuntimeError("Source failure; stop without retry")
        time.sleep(2)
    raw = json.loads(path.read_text())
    if raw.get("errors"):
        raise RuntimeError(f"GraphQL error in {path}; no replacement source")
    return decode_payloads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    queries = parse_pga_html(SCHEDULE.read_bytes())["props"]["pageProps"]["dehydratedState"]["queries"]
    schedule = next(q["state"]["data"]["tournaments"] for q in queries
                    if q["queryKey"][0] == "schedule")
    by_name = {e["name"].casefold(): e for e in schedule}
    included, excluded = [], []
    events = json.loads(SCORES.read_text())["events"]
    for event in events:
        name = event.get("name", "")
        reason = EXCLUDED.get(name)
        if not event.get("id") or not event.get("date"):
            reason = "missing event identity or date"
        elif not event.get("status", {}).get("type", {}).get("completed"):
            reason = "not completed"
        if reason:
            excluded.append({"espn_id": event.get("id"), "name": name, "reason": reason})
            continue
        official = by_name.get(NAMES.get(name, name).casefold())
        if official is None:
            raise ValueError(f"Unresolved official event identity: {name}")
        start = datetime.strptime(official["displayDate"].split(" - ")[0] + " 2025", "%b %d %Y").date()
        if str(start) != event["date"][:10]:
            raise ValueError(f"Official/ESPN start-date mismatch: {name}")
        included.append({"espn_id": event["id"], "pga_id": official["tournamentId"],
                         "name": name, "start_date": str(start),
                         "official_name": official["name"], "venue": official["courseData"]})
    if len(included) != 40:
        raise ValueError("Declared 40-event identity cohort changed; inspect before any scoring comparison")
    ids = [e["pga_id"] for e in included]
    metadata = {}
    for offset in range(0, len(ids), 10):
        result = acquire(f"tournaments-{offset // 10}", "Tournaments", {"ids": ids[offset:offset+10]}, args.fetch)
        if result is not None:
            metadata.update({e["id"]: e for e in result["data"]["tournaments"]})
    for event in included:
        tid = event["pga_id"]
        info = metadata.get(tid)
        if info:
            event["timezone"] = info["timezone"]
            event["courses"] = info["courses"]
            event["format_type"] = info["formatType"]
        result = acquire(tid + "-teetimes", "TeeTimesCompressedV2",
                         {"teeTimesCompressedV2Id": tid}, args.fetch)
        if result is None:
            event["group_source_status"] = "not acquired"
            continue
        payload = result["data"]["teeTimesCompressedV2"]["payload"]
        if payload["id"] != tid:
            raise ValueError(f"Wrong tee-time event: {tid}")
        event["rounds"] = []
        for rnd in payload.get("rounds", []):
            if rnd["roundInt"] not in (1, 2):
                continue
            groups = rnd.get("groups", [])
            event["rounds"].append({"round": rnd["roundInt"], "groups": len(groups),
                "players": sum(len(g.get("players", [])) for g in groups),
                "missing_tee_time": sum(not isinstance(g.get("teeTime"), (int, float)) for g in groups),
                "course_ids": sorted({str(g.get("courseId")) for g in groups})})
        event["group_source_status"] = "present" if event["rounds"] else "empty"
        event["source"] = digest(RAW / f"{tid}-teetimes.json")
    report = {"as_of_local_date": "2026-09-14", "scope": "Identity/group acquisition only; no weather classification, player score joins or outcome comparison.",
              "cohort": "2025 official PGA individual single-course medal events, rounds 1–2; TOUR Championship included under its unadjusted 2025 format.",
              "sources": [digest(SCHEDULE), digest(SCORES)],
              "events": included, "excluded": excluded,
              "event_count": len(included),
              "events_with_r1_r2": sum(len(e.get("rounds", [])) == 2 for e in included),
              "groups_r1_r2": sum(r["groups"] for e in included for r in e.get("rounds", []))}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("event_count", "events_with_r1_r2", "groups_r1_r2")}, indent=2))


if __name__ == "__main__":
    main()
