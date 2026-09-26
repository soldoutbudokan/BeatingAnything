#!/usr/bin/env python3
"""Raw paired NBA alternate-points inventory; no sporting outcomes or model."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "data/raw/nba-announced-absence-2026-09-26/prices.json"
PRICE_SHA = "f44b4d42fc168e434776a7fd89a2cc9bd09bd470adb13189de7b4270ac048372"
OUTDIR = ROOT / "data/raw/nba-paired-alternate-2026-09-26"
REPORT = ROOT / "reports/nba-paired-alternate-price-feasibility-2026-09-26"
DECL = ROOT / "docs/nba-paired-alternate-feasibility-declaration-2026-09-26.md"
IDENTITIES = ROOT / "reports/nba-foul-risk-identity-feasibility-2026-09-26.json"
IDENTITY_SHA = "e795cfe6582aebbf562bac78a88c20fbcbb4e5f71a1e99684276e06f4ce2d210"
FIELDS = ["event_id", "nba_game_id", "espn_game_id", "period", "player", "athlete_id", "identity_status",
          "home_team", "away_team", "source_snapshot_utc", "provider_start_utc",
          "independent_start_utc", "boundary_utc", "book_last_update", "main_market_last_update",
          "alt_market_last_update", "book_age_seconds", "main_market_age_seconds", "alt_market_age_seconds",
          "main_line", "main_over_decimal", "main_under_decimal", "main_overround",
          "alt_line", "alt_over_decimal", "alt_under_decimal", "alt_overround",
          "alt_minus_main_points", "absolute_distance_points", "distance_at_least_two",
          "source_path", "source_sha256"]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pin(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": digest(p), "bytes": p.stat().st_size}


def clock(s):
    value = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Missing timezone")
    return value.astimezone(timezone.utc)


def rational(x):
    return Fraction(str(x))


def literal_pairs(market, counts):
    groups = defaultdict(list)
    for outcome in market.get("outcomes", []):
        name = outcome.get("description")
        if not isinstance(name, str) or not name.strip():
            counts["invalid_name_outcome_rows"] += 1
            continue
        try:
            line = rational(outcome.get("point"))
        except (ValueError, ZeroDivisionError):
            counts["invalid_line_outcome_rows"] += 1
            continue
        groups[(name, line)].append(outcome)
    pairs = {}
    for key, sides in groups.items():
        counts["name_line_groups"] += 1
        if key[1].denominator != 2:
            counts["non_halfpoint_groups"] += 1
            continue
        if len(sides) != 2 or Counter(s.get("name") for s in sides) != Counter({"Over": 1, "Under": 1}):
            counts["missing_duplicate_or_invalid_sides_groups"] += 1
            continue
        try:
            odds = {s["name"]: rational(s.get("price")) for s in sides}
        except (ValueError, ZeroDivisionError):
            counts["invalid_odds_groups"] += 1
            continue
        if any(x < Fraction(6, 5) or x > 6 for x in odds.values()):
            counts["outside_decimal_range_groups"] += 1
            continue
        margin = 1 / odds["Over"] + 1 / odds["Under"] - 1
        if not 0 <= margin <= Fraction(3, 25):
            counts["outside_overround_range_groups"] += 1
            continue
        pairs[key] = (odds["Over"], odds["Under"], margin)
        counts["qualifying_paired_groups"] += 1
    return pairs


def cohort_summary(rows):
    return {"paired_alt_lines": len(rows), "events": len({r["event_id"] for r in rows}),
            "literal_player_names": len({r["player"] for r in rows}),
            "unique_athlete_ids": len({r["athlete_id"] for r in rows if r["athlete_id"]}),
            "event_players": len({(r["event_id"], r["player"]) for r in rows}),
            "below_main_pairs": sum(r["alt_minus_main_points"] < 0 for r in rows),
            "above_main_pairs": sum(r["alt_minus_main_points"] > 0 for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-stem", type=Path, default=REPORT)
    parser.add_argument("--output-dir", type=Path, default=OUTDIR)
    args = parser.parse_args()
    csvpath = args.output_dir / "paired-alternate-prices.csv"
    detailspath = args.output_dir / "inventory-details.json"
    jp, mdp = args.report_stem.with_suffix(".json"), args.report_stem.with_suffix(".md")
    for path in (csvpath, detailspath, jp, mdp):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite {path}")
    assert digest(PRICES) == PRICE_SHA
    assert digest(IDENTITIES) == IDENTITY_SHA
    identity_report = json.loads(IDENTITIES.read_text())
    identities = {r["offered_name"]: r for r in identity_report["offered_name_mapping"]}
    frozen = json.loads(PRICES.read_text())
    assert len(frozen["events"]) == 666
    assert sum(len(e["preliminary_pairs"]) for e in frozen["events"]) == 8286
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source_counts, group_counts, main_group_counts = Counter(), Counter(), Counter()
    rows, event_status, sources = [], [], []
    for event in sorted(frozen["events"], key=lambda x: (clock(x["source_snapshot_utc"]), x["event_id"])):
        path = ROOT / event["source_path"]
        assert digest(path) == event["source_sha256"]
        sources.append(pin(path))
        raw = json.loads(path.read_text())
        payload = raw["data"]
        assert payload["id"] == event["event_id"]
        assert raw["timestamp"] == event["source_snapshot_utc"]
        assert payload["commence_time"] == event["provider_start_utc"]
        assert payload["home_team"] == event["home_team"] and payload["away_team"] == event["away_team"]
        entry = clock(raw["timestamp"])
        boundary = min(clock(payload["commence_time"]), clock(event["independent_start_utc"]))
        assert entry < boundary
        period = "calibration" if entry < cutoff else "evaluation"
        status = {"event_id": event["event_id"], "period": period, "pairs_distinct_from_main": 0,
                  "pairs_distance_at_least_two": 0, "reason": ""}
        source_counts["source_events"] += 1
        books = [b for b in payload["bookmakers"] if b.get("key") == "fanduel"]
        assert len(books) == 1
        book = books[0]
        mains = [m for m in book["markets"] if m.get("key") == "player_points"]
        assert len(mains) == 1
        main = mains[0]
        main_ages = [(entry - clock(book["last_update"])).total_seconds(),
                     (entry - clock(main["last_update"])).total_seconds()]
        assert all(0 <= a <= 300 for a in main_ages)
        assert book["last_update"] == event["book_last_update"]
        assert main["last_update"] == event["market_last_update"]
        raw_main = literal_pairs(main, main_group_counts)
        anchors = {}
        for p in event["preliminary_pairs"]:
            name, line = p["player"], rational(p["line"])
            assert name not in anchors, "Multiple qualifying main anchors; do not select one opportunistically"
            over, under, margin = raw_main[(name, line)]
            assert over == rational(p["over_decimal"]) and under == rational(p["under_decimal"])
            assert abs(float(margin) - p["overround"]) < 1e-14
            anchors[name] = (line, over, under, margin)
        alternates = [m for m in book["markets"] if m.get("key") == "player_points_alternate"]
        if len(alternates) != 1:
            reason = "missing_alt_market" if not alternates else "duplicate_alt_market"
            source_counts[reason] += 1
            status["reason"] = reason
            event_status.append(status)
            continue
        alt = alternates[0]
        source_counts["unique_alt_market_events"] += 1
        try:
            age = (entry - clock(alt["last_update"])).total_seconds()
        except (ValueError, KeyError, TypeError):
            source_counts["invalid_alt_update_clock"] += 1
            status["reason"] = "invalid_alt_update_clock"
            event_status.append(status)
            continue
        if not 0 <= age <= 300:
            reason = "future_alt_update_clock" if age < 0 else "stale_alt_update_clock"
            source_counts[reason] += 1
            status.update(reason=reason, alt_age_seconds=age)
            event_status.append(status)
            continue
        source_counts["fresh_alt_market_events"] += 1
        alt_pairs = literal_pairs(alt, group_counts)
        for (name, line), (over, under, margin) in sorted(alt_pairs.items()):
            if name not in anchors:
                group_counts["no_exact_main_anchor_groups"] += 1
                continue
            ml, mo, mu, mm = anchors[name]
            if line == ml:
                group_counts["alt_equals_main_line_groups"] += 1
                continue
            difference = line - ml
            far = abs(difference) >= 2
            identity = identities[name]
            athlete_id = identity["candidate_athlete_ids"][0] if identity["status"] == "unique" else ""
            status["pairs_distinct_from_main"] += 1
            status["pairs_distance_at_least_two"] += int(far)
            rows.append({"event_id": event["event_id"], "nba_game_id": event["nba_game_id"],
                         "espn_game_id": event["espn_game_id"], "period": period, "player": name,
                         "athlete_id": athlete_id, "identity_status": identity["status"],
                         "home_team": payload["home_team"], "away_team": payload["away_team"],
                         "source_snapshot_utc": raw["timestamp"], "provider_start_utc": payload["commence_time"],
                         "independent_start_utc": event["independent_start_utc"], "boundary_utc": boundary.isoformat(),
                         "book_last_update": book["last_update"], "main_market_last_update": main["last_update"],
                         "alt_market_last_update": alt["last_update"], "book_age_seconds": main_ages[0],
                         "main_market_age_seconds": main_ages[1], "alt_market_age_seconds": age,
                         "main_line": float(ml), "main_over_decimal": float(mo), "main_under_decimal": float(mu),
                         "main_overround": float(mm), "alt_line": float(line), "alt_over_decimal": float(over),
                         "alt_under_decimal": float(under), "alt_overround": float(margin),
                         "alt_minus_main_points": float(difference), "absolute_distance_points": float(abs(difference)),
                         "distance_at_least_two": far, "source_path": event["source_path"], "source_sha256": event["source_sha256"]})
        status["reason"] = "has_distinct_paired_alt" if status["pairs_distinct_from_main"] else "no_distinct_qualified_paired_alt"
        event_status.append(status)
    assert len({(r["event_id"], r["player"], r["alt_line"]) for r in rows}) == len(rows)
    far_rows = [r for r in rows if r["distance_at_least_two"]]
    by_period = {p: {"all_distinct": cohort_summary([r for r in rows if r["period"] == p]),
                     "distance_at_least_two": cohort_summary([r for r in far_rows if r["period"] == p]),
                     "all_distinct_unique_identities": cohort_summary([r for r in rows if r["period"] == p and r["athlete_id"]]),
                     "distance_at_least_two_unique_identities": cohort_summary([r for r in far_rows if r["period"] == p and r["athlete_id"]])}
                 for p in ("calibration", "evaluation")}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with csvpath.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    detailspath.write_text(json.dumps({"event_status": event_status, "raw_sources": sources}, indent=2) + "\n")
    # Output paths can be outside the repo for a non-overwriting reproduction.
    projection = {"path": str(csvpath.relative_to(ROOT)) if csvpath.is_relative_to(ROOT) else str(csvpath),
                  "sha256": digest(csvpath), "bytes": csvpath.stat().st_size}
    details = {"path": str(detailspath.relative_to(ROOT)) if detailspath.is_relative_to(ROOT) else str(detailspath),
               "sha256": digest(detailspath), "bytes": detailspath.stat().st_size}
    report = {"status": "price_only_inventory_complete", "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
              "tool": pin(Path(__file__)), "declaration": pin(DECL), "identity_census": pin(IDENTITIES),
              "frozen_main_prices": pin(PRICES), "source_counts": dict(source_counts),
              "alt_group_counts_after_clock_gates": dict(group_counts),
              "all_distinct_from_main": cohort_summary(rows), "distance_at_least_two": cohort_summary(far_rows),
              "all_distinct_unique_identities": cohort_summary([r for r in rows if r["athlete_id"]]),
              "distance_at_least_two_unique_identities": cohort_summary([r for r in far_rows if r["athlete_id"]]),
              "by_period": by_period, "detailed_pairs": projection, "detailed_source_and_event_inventory": details,
              "coverage_gate": {"minimum_distinct_events_per_period": 100,
                  "both_periods_pass_all_literal_names": all(v["distance_at_least_two"]["events"] >= 100 for v in by_period.values()),
                  "both_periods_pass_unique_identities": all(v["distance_at_least_two_unique_identities"]["events"] >= 100 for v in by_period.values())},
              "rules": ["Use only the frozen666 main-quote events, raw FanDuel book and player_points_alternate node.",
                        "One unique main anchor per exact full player name; all anchors reproduce the frozen literal main pair.",
                        "One alt market; exactly one literal Over and Under per exact name/half-point line, with no duplicate sides.",
                        "Both decimal odds1.20–6.00, overround0–0.12 by exact rational arithmetic; book and alt update ages0–300seconds at original snapshot.",
                        "All retained alt lines differ from main; the separate absolute distance>=2point cohort was fixed before counts.",
                        "Jan1UTC split uses original source snapshot, not fixture start or source publication."],
              "target_outcomes_or_performance_read": False, "forecast_model_or_mispricing_test": False, "network_requests": 0,
              "limitations": ["These are same-event actual quoted pairs, not a payoff-coverage screen or evidence of fair probabilities.",
                             "Exact literal names are retained; the separately pinned identity census supplies unique ESPN IDs without target appearance filters. Role/history eligibility is not evaluated.",
                             "No alternate was selected by return or fitted gap. All qualifying distances and both directions are preserved.",
                             "Source update clocks do not establish simultaneous fills, suspension status, original receipt or jurisdiction-specific contract equivalence."]}
    args.report_stem.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(report, indent=2) + "\n")
    full, distant = report["all_distinct_from_main"], report["distance_at_least_two"]
    md = ["# NBA paired alternate-points feasibility", "",
          f"The frozen666-event /8,286-main-pair universe supplies **{full['paired_alt_lines']:,} qualifying paired alternate lines across {full['events']} events**, all distinct from the exact same-name main anchor. The pre-count **absolute distance≥2points** cohort retains **{distant['paired_alt_lines']:,} pairs /{distant['events']} events /{distant['literal_player_names']} literal player names**.", "",
          "| Period by original snapshot | All distinct alt pairs | Events | Distance≥2 pairs | Events | Player names at≥2 |",
          "|---|---:|---:|---:|---:|---:|"]
    for period, summary in by_period.items():
        a, b = summary["all_distinct"], summary["distance_at_least_two"]
        md.append(f"| {period} | {a['paired_alt_lines']} | {a['events']} | {b['paired_alt_lines']} | {b['events']} | {b['literal_player_names']} |")
    md += ["", "Among unique ESPN identities, the distance≥2 cohort is:", "",
           "| Period | Paired alt lines | Events | Athlete IDs |", "|---|---:|---:|---:|"]
    for period, summary in by_period.items():
        b = summary["distance_at_least_two_unique_identities"]
        md.append(f"| {period} | {b['paired_alt_lines']} | {b['events']} | {b['unique_athlete_ids']} |")
    md += ["", "Each raw file was rehashed, every main anchor independently reconstructed, and original snapshot/start/book/main clocks matched to the frozen inventory. FanDuel alternate nodes require exact same player spelling, a half-point line, one Over and Under, decimal prices1.20–6.00, paired overround0–12%, and book/alternate ages0–300seconds. Missing, duplicate and future/stale fields are excluded and counted. Main anchors are unique in all666 events.", "",
           f"Source-event gates: `{dict(source_counts)}`. Alternate group gates after fresh clocks: `{dict(group_counts)}`.", "",
           f"Detailed pairs and both main/alternate clocks: `{projection['path']}`; SHA-256 `{projection['sha256']}`. Raw-source hashes and every event status are in `{details['path']}`. The [JSON](nba-paired-alternate-price-feasibility-2026-09-26.json) pins those artifacts, the [pre-count declaration](../docs/nba-paired-alternate-feasibility-declaration-2026-09-26.md), and the identity census. The isolated tool refuses to overwrite outputs.", "",
           f"The fixed≥100-games-per-period gate is met for all literal names: **{report['coverage_gate']['both_periods_pass_all_literal_names']}**; for unique identities: **{report['coverage_gate']['both_periods_pass_unique_identities']}**. Failure ends this exact paired-price route before any scoring-history or target-label join; no smaller distance, unpaired side or lower gate is substituted.", "",
           "This is only an actual-price coverage inventory for a potential distinct score-distribution model. No probability comparison, payoff-coverage screen, foul-risk feature, outcome grade, player performance, model fit, new source or network request was used. Counts are preliminary price coverage, not an independent-game forecast sample or evidence of mispricing."]
    mdp.write_text("\n".join(md) + "\n")
    print(json.dumps({"all_distinct": full, "distance_at_least_two": distant, "by_period": by_period,
                      "source_counts": dict(source_counts), "alt_group_counts": dict(group_counts)}, indent=2))


if __name__ == "__main__":
    main()
