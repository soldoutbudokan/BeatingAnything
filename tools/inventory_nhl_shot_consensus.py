#!/usr/bin/env python3
"""Price-only exact-line NHL consensus coverage; never loads outcomes or forecasts."""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-shot-archive-2026-09-26"
OUT = ROOT / "reports/nhl-shot-consensus-coverage-2026-09-26"
REFERENCE_BOOKS = ("draftkings", "betmgm", "espnbet", "hardrockbet")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp(value):
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert date.tzinfo is not None
    return date


def norm(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub("[^a-z0-9]", "", value)


def decimal(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) < 100:
        raise ValueError("invalid_american_price")
    return 1+value/100 if value > 0 else 1+100/abs(value)


def parse_main_pairs(raw, issues):
    """Return literal paired quotes; normalization changes accents/case/punctuation only."""
    books = {}
    counts = Counter(b["key"] for b in raw.get("bookmakers", []))
    for book in raw.get("bookmakers", []):
        key = book["key"]
        if counts[key] != 1:
            issues[key + ":duplicate_book"] += 1
            continue
        markets = [m for m in book["markets"] if m["key"] == "player_shots_on_goal"]
        if len(markets) != 1:
            issues[key + (":no_main_market" if not markets else ":duplicate_main_market")] += 1
            continue
        market = markets[0]
        update = stamp(market["last_update"])
        groups = defaultdict(list)
        for o in market["outcomes"]:
            if not isinstance(o.get("description"), str) or not o["description"]:
                issues[key + ":missing_player_name"] += 1
                continue
            groups[norm(o["description"]), o.get("point")].append(o)
        pairs = {}
        for identity, outcomes in groups.items():
            name, line = identity
            if len(outcomes) != 2 or {o["name"] for o in outcomes} != {"Over", "Under"}:
                issues[key + ":incomplete_or_duplicate_side"] += 1
                continue
            if len({o["description"] for o in outcomes}) != 1:
                issues[key + ":ambiguous_normalized_name"] += 1
                continue
            if not isinstance(line, (int, float)) or not math.isfinite(line) or line <= 0:
                issues[key + ":invalid_line"] += 1
                continue
            side = {o["name"]: o for o in outcomes}
            try:
                over, under = decimal(side["Over"]["price"]), decimal(side["Under"]["price"])
            except ValueError:
                issues[key + ":invalid_price"] += 1
                continue
            pairs[identity] = {"name": outcomes[0]["description"], "line": line,
                               "over_decimal": over, "under_decimal": under,
                               "overround": 1/over+1/under-1}
        books[key] = {"update": update, "pairs": pairs}
    return books


def main():
    manifest = json.loads((RAW/"manifest.json").read_text())
    assert manifest["source_commit"] == "42cf1f81bc302642ddcc9e88ce2e98c1057bc74d"
    assert len(manifest["files"]) == 285
    issues, book_counts, book_events = Counter(), defaultdict(Counter), defaultdict(set)
    lags, fd_rows, ref_hist, events = defaultdict(list), [], {300: Counter(), 600: Counter()}, set()
    raw_key_counts, raw_market_counts = Counter(), Counter()
    literal_differences = Counter()
    for info in manifest["files"]:
        path = ROOT/info["path"]
        assert sha(path) == info["sha256"] and path.stat().st_size == info["bytes"]
        raw = json.loads(path.read_text())
        if "bookmakers" not in raw:
            issues["publisher_error_payload"] += 1
            continue
        assert raw["id"] not in events
        events.add(raw["id"])
        for b in raw["bookmakers"]:
            raw_key_counts[b["key"]] += 1
            raw_market_counts[b["key"]] += sum(m["key"] == "player_shots_on_goal" for m in b["markets"])
        books = parse_main_pairs(raw, issues)
        for key, book in books.items():
            book_counts[key]["valid_paired_main_lines"] += len(book["pairs"])
            book_counts[key]["negative_overround_pairs"] += sum(p["overround"] < -1e-12 for p in book["pairs"].values())
            book_counts[key]["overround_above_15pct_pairs"] += sum(p["overround"] > .15+1e-12 for p in book["pairs"].values())
        if "fanduel" not in books:
            continue
        fd = books["fanduel"]
        assert fd["update"] < stamp(raw["commence_time"])
        for identity, price in sorted(fd["pairs"].items()):
            refs = {}
            for key, book in books.items():
                if key == "fanduel" or identity not in book["pairs"]:
                    continue
                age = (fd["update"]-book["update"]).total_seconds()
                lags[key].append(age)
                refs[key] = age
                book_counts[key]["exact_fd_player_line_pairs"] += 1
                book_counts[key]["later_than_fd_market_update"] += age < 0
                literal_differences[key] += price["name"] != book["pairs"][identity]["name"]
                for window in [300,600]:
                    if 0 <= age <= window:
                        book_counts[key][f"timely_{window}s_pairs"] += 1
                        book_events[key,window].add(raw["id"])
            row = {"source_file": path.name, "event_id": raw["id"], "provider_start": raw["commence_time"],
                   "fd_market_update": fd["update"].isoformat(), "player": price["name"], "normalized_player": identity[0],
                   "line": price["line"]}
            for window in [300,600]:
                timely = sorted(k for k, age in refs.items() if 0 <= age <= window)
                core = sorted(set(timely) & set(REFERENCE_BOOKS))
                row[f"all_timely_{window}s_books"] = "|".join(timely)
                row[f"core_timely_{window}s_books"] = "|".join(core)
                row[f"core_at_least3_{window}s"] = len(core) >= 3
                ref_hist[window][len(timely)] += 1
            fd_rows.append(row)
    summary = []
    for key in sorted(raw_key_counts):
        values = lags[key]
        summary.append({"book": key, "raw_book_payloads": raw_key_counts[key], "main_market_payloads": raw_market_counts[key],
                        **dict(book_counts[key]), "timely_300s_games": len(book_events[key,300]), "timely_600s_games": len(book_events[key,600]),
                        "normalized_not_literal_name_matches": literal_differences[key],
                        "fd_minus_reference_update_seconds": {"minimum": min(values), "median": statistics.median(values), "maximum": max(values)} if values else None})
    cohorts = {}
    for window in [300,600]:
        selected = [r for r in fd_rows if r[f"core_at_least3_{window}s"]]
        cohorts[str(window)] = {"pairs": len(selected), "games": len({r["event_id"] for r in selected}),
                               "by_provider_start_month": {m: {"pairs": sum(r["provider_start"].startswith(m) for r in selected),
                                    "games": len({r["event_id"] for r in selected if r["provider_start"].startswith(m)})}
                                    for m in sorted({r["provider_start"][:7] for r in fd_rows})}}
    coverage_path = RAW/"consensus-price-coverage.csv"
    with coverage_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fd_rows[0]))
        writer.writeheader(); writer.writerows(fd_rows)
    report = {"scope": "Source coverage only. No outcomes, probability comparison, disagreement, model, ROI or strategy selection evaluated.",
              "source_manifest_sha256": sha(RAW/"manifest.json"), "source_commit": manifest["source_commit"], "source_files_verified": len(manifest["files"]),
              "event_payloads": len(events), "fanduel_pairs": len(fd_rows), "fanduel_events": len({r["event_id"] for r in fd_rows}),
              "reference_books_proposed_from_availability_only": list(REFERENCE_BOOKS), "core_coverage_at_least3": cohorts,
              "per_book": summary, "all_brand_reference_count_histograms": {str(k): dict(v) for k,v in ref_hist.items()},
              "issues": dict(issues), "coverage_csv": str(coverage_path.relative_to(ROOT)), "coverage_csv_sha256": sha(coverage_path),
              "limitations": ["Outcomes in this archive were already inspected for the completed dispersion test; any new model is exploratory.",
                              "Same full normalized player text and exact main line only; no aliases, alternates, interpolation or fabricated sides.",
                              "Age means FanDuel market update minus reference market update; future reference timestamps are excluded, not moved.",
                              "No receipt/capture or book-wide clock exists in these payloads. Update ordering does not prove execution or original availability.",
                              "Proposed pool has distinct operators. Statistical independence and absence of shared pricing/data vendors are not established.",
                              "Bally Bet and BetRivers share Kambi services in 2024; do not count them as two independent pricing sources.",
                              "Full-pair inventory has no overround filter. Per-book unusual margins are counted for a later fixed protocol to address."]}
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    lines = ["# NHL shots consensus coverage — September 26, 2026", "",
             f"**A fixed four-book pool supplies at least three timely exact-line references for {cohorts['300']['pairs']:,} FanDuel pairs across {cohorts['300']['games']} games.** The proposed pool is DraftKings, BetMGM, ESPN BET and Hard Rock Bet. Both 300-second and 600-second age limits produce the same coverage. This choice uses source availability only; no new forecasts, outcomes, returns or price-disagreement scores were computed.", "",
             "All 285 retained raw files match their acquisition-manifest hashes: 273 event payloads and 12 publisher errors. FanDuel has 3,584 complete main shots pairs across 272 events. Each reference uses the same event, normalized full player name and exact main line, with both literal Over and Under prices. No alternate-line interpolation, alias mapping or reconstructed side is used. Repeated or conflicting pairs are rejected.", "",
             "| Book | Main-market events | Valid paired lines | Exact FD-line pairs | Later update than FD | Age 0–300s pairs | Age 0–600s pairs |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in summary:
        lines.append(f"| {r['book']} | {r['main_market_payloads']} | {r.get('valid_paired_main_lines',0)} | {r.get('exact_fd_player_line_pairs',0)} | {r.get('later_than_fd_market_update',0)} | {r.get('timely_300s_pairs',0)} | {r.get('timely_600s_pairs',0)} |")
    lines += ["", "Reference age is `FanDuel market last_update − reference market last_update`. Negative ages are later quotes and are excluded. Increasing the window to 600 seconds adds only Bovada coverage; all nonfuture updates from the proposed four-book pool already lie within 300 seconds. Core coverage by provider-start month: " + json.dumps(cohorts['300']['by_provider_start_month']) + ".", "",
              "Do not equate distinct book keys with independent forecasts. [Kambi's August 2024 RSI disclosure](https://www.kambi.com/investors/news-pr/kambi-group-plc-and-rush-street-interactive-agree-to-a-multi-year-sportsbook-partnership-extension/) establishes BetRivers' platform/trading relationship, while [Bally's July 2024 announcement](https://s29.q4cdn.com/580102441/files/doc_news/2024/Jul/31/bally-bet-app-maryland-press-release-final.pdf) identifies Kambi as a sportsbook partner. Excluding both from the proposed core avoids counting these brands as separate independent signals. Statistical independence of the four proposed operators is still unproven.", "",
              "No explicit capture/receipt or book-wide update clock is present. Reference-market timestamps preceding the FanDuel update are necessary chronology evidence, not proof of executable availability. The completed dispersion experiment has already exposed this archive's outcomes; any subsequent consensus test must remain exploratory. This inventory includes all source events and does not apply participant/history filters or the earlier debug-game exclusion.", "",
              "The adjacent JSON includes per-book timing ranges, unusual-overround counts and cohort counts. The reusable score-free local projection is `data/raw/nhl-shot-archive-2026-09-26/consensus-price-coverage.csv`. Reproduce with `python3 tools/inventory_nhl_shot_consensus.py`. No wager or alert.", ""]
    OUT.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps({"core": cohorts, "issues": dict(issues), "per_book": summary}, indent=2))


if __name__ == "__main__":
    main()
