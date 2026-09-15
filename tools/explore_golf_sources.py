#!/usr/bin/env python3
"""Recover the permitted golf sample and schedules; do not substitute for 2025.

This is a source/coverage checkpoint, not the unexecuted variance estimator.
Default operation is offline. --fetch retrieves only the three expressly listed
public inputs if absent, once each. It never requests the blocked leaderboard or
the paid Data Golf archive and does not accept credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/golf-sunday-chasing"
REPORT = ROOT / "reports/golf-source-screen-2026-09-13"
SOURCES = {
    "schedule-2025.html": "https://www.pgatour.com/schedule/2025",
    "schedule-2026.html": "https://www.pgatour.com/schedule/2026",
    "datagolf-free-sample-2021-masters.json":
        "https://feeds.datagolf.com/historical-raw-data/sample?file_format=json",
}


def schedule(path: Path, expected_year: int) -> list[dict]:
    match = re.search(
        rb'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        path.read_bytes(),
    )
    if match is None:
        raise ValueError(f"Missing public schedule page data: {path.name}")
    data = json.loads(match[1])
    queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    result = next(q["state"]["data"] for q in queries
                  if q["queryKey"][0] == "schedule")
    if int(result["season"]) != expected_year:
        raise ValueError("Schedule returned a different year")
    fields = ("tournamentId", "name", "year", "month", "displayDate", "status")
    return [{k: t[k] for k in fields} for t in result["tournaments"]]


def sample_coverage(path: Path) -> dict:
    data = json.loads(path.read_text())
    players = data["scores"]
    rounds = [p[f"round_{n}"] for p in players for n in range(1, 5)
              if isinstance(p.get(f"round_{n}"), dict)
              and isinstance(p[f"round_{n}"].get("score"), (int, float))]
    complete = [p for p in players if all(
        isinstance(p.get(f"round_{n}"), dict)
        and isinstance(p[f"round_{n}"].get("score"), (int, float))
        for n in range(1, 5))]
    return {
        "tour": data["tour"], "year": data["year"],
        "event_id_as_published": data["event_id"],
        "event_name": data["event_name"], "event_completed": data["event_completed"],
        "players": len(players), "round_records": len(rounds),
        "complete_four_round_players": len(complete),
        "round_fields": sorted(set().union(*(r.keys() for r in rounds))),
        "scope": "Schema and coverage only; 2021 sample is outside fixed 2025 test",
        "prior_event_rounds_available": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    if args.fetch:
        for name, url in SOURCES.items():
            path = RAW / name
            if not path.exists():
                with urlopen(url, timeout=45) as response:
                    path.write_bytes(response.read())
    missing = [name for name in SOURCES if not (RAW / name).exists()]
    if missing:
        raise SystemExit(f"Missing cached permitted inputs: {missing}; use --fetch once")
    inventory = [{"file": f"data/raw/golf-sunday-chasing/{name}", "url": url,
                  "bytes": (RAW / name).stat().st_size,
                  "sha256": hashlib.sha256((RAW / name).read_bytes()).hexdigest()}
                 for name, url in SOURCES.items()]
    historical = schedule(RAW / "schedule-2025.html", 2025)
    current = schedule(RAW / "schedule-2026.html", 2026)
    remaining = [t for t in current if t["month"] in
                 {"September", "October", "November", "December"}]
    sample = sample_coverage(RAW / "datagolf-free-sample-2021-masters.json")
    result = {
        "as_of": "2026-09-13", "status": "unresolved: required data unavailable",
        "card": "docs/hypotheses/golf-sunday-chasing-variance.md",
        "fixed_test_year": 2025, "sources": inventory,
        "schedule_2025_entries": len(historical),
        "schedule_2025": historical, "remaining_2026_schedule": remaining,
        "free_sample": sample,
        "sport_effect": None, "fixed_sample_player_rounds_recovered": 0,
        "fanduel_quotes_recovered": 0,
        "blockers": [
            {"source": "PGA TOUR", "url":
             "https://www.pgatour.com/tournaments/2025/the-sentry/R2025016/leaderboard",
             "result": "Ordinary web fetch returned HTTP 403; no repeat or workaround"},
            {"source": "Data Golf", "url": "https://datagolf.com/raw-data-archive",
             "result": "Publisher expressly requires Scratch PLUS annual access for archive downloads; only its linked free 2021 Masters sample was downloaded"},
        ],
        "next_input": "Permitted 2025 PGA TOUR event round scores with stable player IDs, event dates and format flags; >=10 prior-event rounds for each eligible player. Then run the existing card's fixed screen without replacing years or thresholds.",
    }
    REPORT.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Golf source screen — September 13, 2026", "",
        "**Unresolved: the fixed 2025 variance test could not run.** No sport-side effect or FanDuel price discrepancy was measured. The new [card](../docs/hypotheses/golf-sunday-chasing-variance.md) was written before outcome comparisons.", "",
        "The official PGA TOUR schedule pages were downloaded and parsed: "
        f"{len(historical)} historical 2025 entries and {len(current)} current 2026 entries. "
        "The first historical leaderboard request returned 403. No further historical leaderboards were requested.", "",
        "Data Golf's [raw archive](https://datagolf.com/raw-data-archive) expressly requires paid annual access. Its linked free 2021 Masters sample was successfully downloaded: "
        f"{sample['players']} players, {sample['round_records']} scored rounds, and "
        f"{sample['complete_four_round_players']} complete four-round players. "
        "The sample contains round scores, course par, tee times and strokes gained. It supplies neither the fixed 2025 season nor earlier events for the prior-ability baseline. It was inspected for schema/coverage only; it was not substituted into the test.", "",
        "The [current official schedule](https://www.pgatour.com/schedule/2026) has eight fall stroke-play events from September 17 through November 22, followed by December events. "
        "Golf therefore has more runway than the deferred MLB season, though this PGA TOUR fall alone is only about ten weeks. "
        "The live schedule calls the November 12–15 event **Austin Championship**; older launch articles called it Good Good Championship.", "",
        "| Event | Dates |", "| --- | --- |",
        *[f"| {t['name']} | {t['displayDate']}, 2026 |" for t in remaining], "",
        "The PGA TOUR schedule includes team and qualifying events. This table is a calendar inventory, not a statement that all entries qualify for the card's individual stroke-play test.", "",
        "**Next concrete input:** permitted 2025 individual event round scores, stable player IDs, event dates, format/starting-stroke flags and at least ten prior-event rounds for each eligible player. The existing card fixes the 4–6 versus 8–10 stroke groups, sample gate and 1.15 variance-ratio gate. Do not retune them or call a source failure a negative result.", "",
        "No FanDuel round-score market was verified for a current event and no executable quote was recovered. Data Golf documents historical FanDuel odds in several markets, but that authenticated archive was not acquired and does not establish coverage for alternative player round-score lines.", "",
        "Reproduce the cached inventory with `python tools/explore_golf_sources.py`; `--fetch` downloads only missing copies of the three permitted inputs once. The script is a source checkpoint, **not an implemented variance estimator**. Source URLs, SHA-256 hashes, sizes, sample schema and the exact 403 are in the [JSON report](golf-source-screen-2026-09-13.json). Raw publisher data stays ignored.",
    ]
    REPORT.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: result[k] for k in
                      ("status", "schedule_2025_entries", "free_sample", "sport_effect")}, indent=2))


if __name__ == "__main__":
    main()
