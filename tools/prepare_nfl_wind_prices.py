#!/usr/bin/env python3
"""Extract all independently mapped pregame FanDuel totals without reading scores.

Inventory only: no weather, outcomes, model, EV, betting threshold, or selection.
Retain stale nonfuture book updates and all integer/half-point lines; flag the
existing source-audit quality gates rather than select a betting cohort.
Run with PYTHONPATH=state/runtime/nfl-audit-lib and the research Python runtime.
"""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/nfl-wind-revisions-2026-09-26"
REPORT = ROOT / "reports/nfl-wind-price-inventory-2026-09-26.md"
DB = ROOT / "data/raw/nfl-source-audit/nfl_odds.duckdb"
FIXTURES = ROOT / "data/raw/nfl-fixture-feasibility/fixture-metadata.json"
ENTRIES = ROOT / "data/raw/nfl-fixture-feasibility/entry-metadata.json"
AUDIT = ROOT / "reports/nfl-fixture-feasibility.json"
PINS = {
    DB: "b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c",
    FIXTURES: "dc89d29530a2b7afe29103d9c8a9b492c0bd269a16b0e7f21172452062de0632",
    ENTRIES: "f88d26d409c2a158631d6c69c5c84afeb2580ef7779ad99a452868ba5285d6d6",
}


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # Publisher explicitly uses UTC; DuckDB TIMESTAMP drops timezone metadata.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def write_csv(path, rows):
    assert rows
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def decimal(price):
    if price is None or not math.isfinite(price) or abs(price) < 100:
        raise ValueError("invalid_american_price")
    return 1 + price / 100 if price > 0 else 1 + 100 / abs(price)


def distribution(values):
    if not values:
        return {"count": 0}
    x = sorted(values)
    def q(p):
        at = p * (len(x)-1)
        low, high = math.floor(at), math.ceil(at)
        return x[low] + (x[high]-x[low])*(at-low)
    return {"count": len(x), "minimum": x[0], "p10": q(.1), "median": statistics.median(x),
            "p90": q(.9), "maximum": x[-1]}


def main():
    for path, expected in PINS.items():
        assert sha(path) == expected, f"Changed pinned source: {path}"
    audit = json.loads(AUDIT.read_text())
    names = audit["team_identity_map"]
    assert len(names) == 32 and len(set(names.values())) == 32
    fixtures = {}
    for row in json.loads(FIXTURES.read_text()):
        assert set(row) <= {"game_id", "season", "game_type", "week", "gameday", "gametime",
                            "home_team", "away_team", "old_game_id", "gsis", "nfl_detail_id"}
        assert row["season"] == "2025" and row["game_id"] not in fixtures
        kickoff = datetime.fromisoformat(row["gameday"]+"T"+row["gametime"])
        kickoff = kickoff.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        fixtures[row["game_id"]] = {**row, "kickoff": kickoff}
    entries = json.loads(ENTRIES.read_text())
    event_to_game = {row["event_id"]: row["game_id"] for row in entries}
    assert len(entries) == len(event_to_game) == len(fixtures) == 285
    assert set(event_to_game.values()) == set(fixtures)
    boundaries = {row["game_id"]: min(utc(row["boundary"]), fixtures[row["game_id"]]["kickoff"])
                  for row in entries}

    con = duckdb.connect(str(DB), read_only=True)
    schema = {r[0]: r[1] for r in con.execute("DESCRIBE raw_odds").fetchall()}
    # Quote metadata only. Never query derived summaries or result/score columns.
    metadata = con.execute("""SELECT DISTINCT event_id, home_team, away_team, commence_time
        FROM raw_odds WHERE sport_key='americanfootball_nfl'""").fetchall()
    cols = ["event_id", "captured_at", "commence_time", "home_team", "away_team",
            "bookmaker_last_update", "outcome_name", "outcome_price", "outcome_point"]
    raw = con.execute("SELECT " + ",".join(cols) + """ FROM raw_odds
        WHERE sport_key='americanfootball_nfl' AND bookmaker_key='fanduel' AND market_key='totals'
        ORDER BY captured_at,event_id,outcome_name""").fetchall()
    loads = con.execute("""SELECT min(loaded_at),max(loaded_at) FROM raw_odds
        WHERE sport_key='americanfootball_nfl' AND bookmaker_key='fanduel' AND market_key='totals'""").fetchone()
    con.close()

    event_teams, event_starts = defaultdict(set), defaultdict(set)
    for event, home, away, start in metadata:
        event_teams[event].add((home, away))
        if start is not None:
            event_starts[event].add(utc(start))
    unstable_events = set()
    tightened_from_prior_audit = []
    for event, game in event_to_game.items():
        fixture = fixtures[game]
        identity = {(names.get(h), names.get(a)) for h, a in event_teams[event]}
        if len(event_teams[event]) != 1 or identity != {(fixture["home_team"], fixture["away_team"])}:
            unstable_events.add(event)
            continue
        before = boundaries[game]
        boundaries[game] = min(before, *event_starts[event])
        if boundaries[game] < before:
            tightened_from_prior_audit.append(game)

    groups, rejected, reasons = defaultdict(list), [], Counter()
    for values in raw:
        r = dict(zip(cols, values))
        groups[r["event_id"], r["captured_at"]].append(r)
    rows, exact_duplicates = [], 0
    for (event, capture_raw), group in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0])):
        def reject(reason):
            reasons[reason] += 1
            rejected.append({"event_id": event, "captured_at_utc": utc(capture_raw).isoformat() if capture_raw else None,
                             "game_id": event_to_game.get(event), "reason": reason, "raw_rows": len(group)})
        game = event_to_game.get(event)
        if game is None:
            reject("absent_from_independent_fixture_audit_mapping")
            continue
        if event in unstable_events:
            reject("conflicting_event_team_identity")
            continue
        fixture = fixtures[game]
        unique = {tuple(r[k] for k in cols): r for r in group}
        exact_duplicates += len(group) - len(unique)
        pair = list(unique.values())
        if len(pair) != 2 or {r["outcome_name"] for r in pair} != {"Over", "Under"}:
            reject("incomplete_or_conflicting_pair")
            continue
        common = {tuple(r[k] for k in ["commence_time", "home_team", "away_team", "bookmaker_last_update"]) for r in pair}
        if len(common) != 1:
            reject("inconsistent_pair_identity_or_clock")
            continue
        start_raw, home, away, update_raw = next(iter(common))
        if any(x is None for x in (capture_raw, start_raw, update_raw)):
            reject("missing_quote_or_start_clock")
            continue
        capture, start, update = utc(capture_raw), utc(start_raw), utc(update_raw)
        if (names.get(home), names.get(away)) != (fixture["home_team"], fixture["away_team"]):
            reject("pair_identity_disagrees_with_independent_fixture")
            continue
        if abs((start-fixture["kickoff"]).total_seconds()) > 900:
            reject("source_start_outside_independent_15_minute_tolerance")
            continue
        if capture >= boundaries[game]:
            reject("not_before_conservative_pregame_boundary")
            continue
        age = (capture-update).total_seconds()
        if age < 0:
            reject("future_book_update")
            continue
        sides = {r["outcome_name"]: r for r in pair}
        line = sides["Over"]["outcome_point"]
        if line is None or not math.isfinite(line) or line <= 0 or line != sides["Under"]["outcome_point"]:
            reject("invalid_or_inconsistent_total_line")
            continue
        if abs(line*2-round(line*2)) > 1e-8:
            reject("line_not_integer_or_half_point")
            continue
        try:
            over, under = decimal(sides["Over"]["outcome_price"]), decimal(sides["Under"]["outcome_price"])
        except ValueError as exc:
            reject(str(exc))
            continue
        vig = 1/over + 1/under - 1
        integer = round(line*2) % 2 == 0
        fresh, vig_gate = age <= 90, -1e-12 <= vig <= .08+1e-12
        rows.append({"game_id": game, "event_id": event, "game_type": fixture["game_type"], "week": int(fixture["week"]),
                     "home_team": fixture["home_team"], "away_team": fixture["away_team"],
                     "bookmaker_key": "fanduel", "market_key": "totals", "captured_at_utc": capture.isoformat(),
                     "bookmaker_last_update_utc": update.isoformat(), "book_update_age_seconds": age,
                     "source_commence_utc": start.isoformat(), "independent_kickoff_utc": fixture["kickoff"].isoformat(),
                     "conservative_boundary_utc": boundaries[game].isoformat(),
                     "lead_to_boundary_seconds": (boundaries[game]-capture).total_seconds(),
                     "lead_to_independent_kickoff_seconds": (fixture["kickoff"]-capture).total_seconds(),
                     "source_start_delta_seconds": (start-fixture["kickoff"]).total_seconds(),
                     "line": line, "line_type": "integer" if integer else "half_point", "push_possible": integer,
                     "over_american": sides["Over"]["outcome_price"], "under_american": sides["Under"]["outcome_price"],
                     "over_decimal": over, "under_decimal": under, "overround": vig,
                     "flag_fresh_0_to_90s": fresh, "flag_overround_0_to_8pct": vig_gate,
                     "flag_existing_quality_gates": fresh and vig_gate})

    assert len(rows) + len(rejected) == len(groups)
    assert len({(r["game_id"], r["captured_at_utc"]) for r in rows}) == len(rows)
    per_game = defaultdict(list)
    for r in rows:
        per_game[r["game_id"]].append(r)
    coverage, gaps = [], []
    for game, fixture in sorted(fixtures.items()):
        quotes = sorted(per_game[game], key=lambda r: r["captured_at_utc"])
        fresh_quotes = [r for r in quotes if r["flag_existing_quality_gates"]]
        for left, right in zip(quotes, quotes[1:]):
            gaps.append((utc(right["captured_at_utc"])-utc(left["captured_at_utc"])).total_seconds())
        coverage.append({"game_id": game, "game_type": fixture["game_type"], "week": int(fixture["week"]),
                         "home_team": fixture["home_team"], "away_team": fixture["away_team"],
                         "independent_kickoff_utc": fixture["kickoff"].isoformat(), "conservative_boundary_utc": boundaries[game].isoformat(),
                         "paired_snapshots": len(quotes), "existing_quality_gate_snapshots": len(fresh_quotes),
                         "first_capture_utc": quotes[0]["captured_at_utc"] if quotes else None,
                         "last_capture_utc": quotes[-1]["captured_at_utc"] if quotes else None,
                         "last_capture_lead_to_independent_kickoff_seconds": quotes[-1]["lead_to_independent_kickoff_seconds"] if quotes else None,
                         "last_quality_gate_capture_lead_to_independent_kickoff_seconds": fresh_quotes[-1]["lead_to_independent_kickoff_seconds"] if fresh_quotes else None})
    by_week = []
    for week in sorted({r["week"] for r in coverage}):
        games = [r for r in coverage if r["week"] == week]
        qs = [r for r in rows if r["week"] == week]
        by_week.append({"week": week, "fixtures": len(games), "covered_fixtures": sum(r["paired_snapshots"] > 0 for r in games),
                        "pairs": len(qs), "quality_gate_pairs": sum(r["flag_existing_quality_gates"] for r in qs)})
    OUT.mkdir(parents=True, exist_ok=True)
    price_path, fixture_path = OUT/"fanduel-totals-pregame.csv", OUT/"totals-fixtures.csv"
    reject_path = OUT/"totals-price-rejections.json"
    write_csv(price_path, rows)
    write_csv(fixture_path, coverage)
    dump(reject_path, rejected)
    report = {
        "scope": "Complete score-free paired FanDuel pregame totals inventory; no weather/model/outcomes/returns/strategy thresholds",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "outcomes_read": False,
        "sources": [{"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size} for path in PINS],
        "odds_url": "https://github.com/bobby-king3/nfl-market-movement-tracker/releases/download/v1.1.1/nfl_odds.duckdb",
        "fixture_source_url": audit["sources"]["fixture_url"], "fixture_full_raw_sha256": audit["sources"]["fixture_raw_sha256"],
        "script_sha256": sha(Path(__file__)), "duckdb_version": duckdb.__version__, "raw_odds_schema": schema,
        "clock_semantics": {"captured_at": "Returned historical Odds API snapshot in UTC, not local receipt or accepted fill.",
                            "bookmaker_last_update": "Book-wide provider update, not a separately preserved total-market update.",
                            "commence_time": "Provider scheduled start; revisions preserved.",
                            "independent_kickoff": "nflverse metadata Eastern schedule converted with America/New_York; actual first play and publication vintage unverified.",
                            "conservative_boundary": "Minimum of independent kickoff, existing audited boundary, and every observed source start for stable mapped identity. Archive-wide metadata only tightens eligibility; it is not a prequote covariate.",
                            "loaded_at": "Retrospective database ingestion, not pregame availability; stored as naive TIMESTAMP and original ingestion timezone unverified."},
        "database_load_range_naive": [x.isoformat() for x in loads],
        "rules": {"pair": "Unique Over/Under at same event/capture/start/ordered teams/book update and same positive integer or half-point line; finite actual American odds.",
                  "fixture": "Reuse all 285 prior audited mappings and independently recheck ordered team identities and source start within 15 minutes of kickoff.",
                  "pregame": "Nonfuture book update and capture strictly before conservative boundary; no lead-window or stale-age strategy filter.",
                  "flags_only": "Existing audit age 0–90 seconds and overround 0–8%; flags do not remove otherwise valid quotes.",
                  "pushes": "Integer lines retained and push_possible=true; observed inventory has no integers."},
        "counts": {"raw_total_rows": len(raw), "raw_source_events": len({r[0] for r in raw}), "raw_event_capture_groups": len(groups),
                   "raw_distinct_captures": len({r[1] for r in raw}), "deduplicated_exact_rows": exact_duplicates,
                   "retained_pairs": len(rows), "covered_games": len(per_game), "expected_fixtures": len(fixtures),
                   "retained_distinct_captures": len({r["captured_at_utc"] for r in rows}),
                   "integer_pairs": sum(r["push_possible"] for r in rows), "half_point_pairs": sum(not r["push_possible"] for r in rows),
                   "existing_quality_gate_pairs": sum(r["flag_existing_quality_gates"] for r in rows),
                   "stale_over_90s_retained": sum(not r["flag_fresh_0_to_90s"] for r in rows),
                   "overround_outside_existing_gate_retained": sum(not r["flag_overround_0_to_8pct"] for r in rows)},
        "mutually_exclusive_rejection_counts": dict(reasons), "boundary_tightened_from_prior_audit_games": tightened_from_prior_audit,
        "retained_capture_range_utc": [rows[0]["captured_at_utc"], rows[-1]["captured_at_utc"]],
        "fixture_kickoff_range_utc": [min(f["kickoff"] for f in fixtures.values()).isoformat(), max(f["kickoff"] for f in fixtures.values()).isoformat()],
        "per_game_snapshot_count": distribution([r["paired_snapshots"] for r in coverage]),
        "within_game_capture_gap_seconds": distribution(gaps),
        "within_game_gap_rounded_minutes_counts": dict(sorted(Counter(round(g/60) for g in gaps).items())),
        "book_update_age_seconds": distribution([r["book_update_age_seconds"] for r in rows]),
        "lead_to_independent_kickoff_seconds": distribution([r["lead_to_independent_kickoff_seconds"] for r in rows]),
        "last_pregame_quote_lead_seconds": distribution([r["last_capture_lead_to_independent_kickoff_seconds"] for r in coverage if r["paired_snapshots"]]),
        "games_with_last_quote_within_seconds": {str(n): sum(r["paired_snapshots"] > 0 and r["last_capture_lead_to_independent_kickoff_seconds"] <= n for r in coverage) for n in [90,300,1800,3600,10800]},
        "coverage_by_week": by_week,
        "outputs": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p), "bytes": p.stat().st_size} for p in [price_path, fixture_path, reject_path]],
        "limitations": ["Historical snapshot and book update do not verify jurisdiction, tradability, receipt, limits, or accepted execution.",
                        "No separate market update, suspension/status, or original JSON response is retained in this database.",
                        "Typical 4/12-hour gaps cannot establish intrahour reaction to forecast changes.",
                        "No score, weather, probability forecast, selection, ROI or CLV was computed; repeated quotes are not independent games."]}
    dump(OUT/"totals-price-inventory.json", report)
    c = report["counts"]
    REPORT.write_text(f'''# NFL wind-route price inventory — September 26, 2026

**{c['retained_pairs']:,} paired pregame FanDuel totals cover all {c['covered_games']} independently mapped fixtures.** This is a score-free source extraction for a possible operational wind-revision test. No weather, scores, predictions, betting thresholds, bets, returns, or closing-line values were evaluated.

The [pinned NFL Market Tracker v1.1.1 archive]({report['odds_url']}) contains {c['raw_total_rows']:,} FanDuel total rows in {c['raw_event_capture_groups']:,} two-sided snapshots across {c['raw_source_events']} source event IDs. The extra Rams–Washington Week 5 artifact cannot match the independent fixture audit and stays excluded. Valid pairs use one event, capture, scheduled start, ordered team identity, common book update and exact total line. Every capture is strictly before the earliest independent/audited/source start boundary; every book update is nonfuture. Matching uses the previous hash-pinned 285-fixture projection, with a fresh ordered-team and 15-minute schedule check.

The output preserves {c['stale_over_90s_retained']} stale pairs above 90 seconds and flags the earlier audit's age and 0–8% overround gates. Those flags identify {c['existing_quality_gate_pairs']:,} pairs; they do not select a betting cohort. Integer lines are supported with an explicit push flag, but all {c['half_point_pairs']:,} retained lines are half-points and there are zero integer quotes. Scanning every book's source-start metadata tightened the prior moneyline audit boundary for {len(tightened_from_prior_audit)} fixtures; the affected identities remain explicit in the inventory.

Fixtures run {report['fixture_kickoff_range_utc'][0]} through {report['fixture_kickoff_range_utc'][1]}. Retained snapshots run {report['retained_capture_range_utc'][0]} through {report['retained_capture_range_utc'][1]}. Games have a median {report['per_game_snapshot_count']['median']:g} snapshots, range {report['per_game_snapshot_count']['minimum']}–{report['per_game_snapshot_count']['maximum']}. Typical captures are around 01:55, 13:55, 17:55 and 21:55 UTC, with four- and twelve-hour gaps. Only {report['games_with_last_quote_within_seconds']['1800']} games have a last valid pair within 30 minutes of independent kickoff; none has one within 90 seconds. This series cannot resolve minute-by-minute price adjustment.

`captured_at` is the returned historical API snapshot; `bookmaker_last_update` is the provider's book-wide update. The database has no separate market update. `loaded_at` is February 2026 retrospective ingestion and cannot establish pregame receipt. Scheduled kickoff publication vintage and actual kickoff remain unverified. Archive-wide earlier starts only tighten eligibility; they are not forecast inputs. Original JSON payloads, simultaneous fills, jurisdiction and execution remain unverified.

Reusable local artifacts under `data/raw/nfl-wind-revisions-2026-09-26/` are `fanduel-totals-pregame.csv`, `totals-fixtures.csv`, `totals-price-rejections.json` and `totals-price-inventory.json`. The inventory records all input/output hashes, exact schema, mutually exclusive rejection counts, cadence, clock meanings and weekly coverage. The raw files remain ignored. Reproduce with `PYTHONPATH=state/runtime/nfl-audit-lib state/runtime/research-venv/bin/python tools/prepare_nfl_wind_prices.py`.
''')
    print(json.dumps({"counts": c, "rejections": dict(reasons), "cadence": report["within_game_capture_gap_seconds"],
                      "last_quote_coverage": report["games_with_last_quote_within_seconds"], "outputs": report["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
