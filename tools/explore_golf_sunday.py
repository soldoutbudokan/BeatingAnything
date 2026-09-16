#!/usr/bin/env python3
"""Replay the prewritten 2025 Sunday chasing variance screen, without prices.

See reports/golf-sunday-declaration-2026-09-14.md for choices frozen before
outcome comparison. No regression, threshold search, or confirmatory cohort.
"""
from __future__ import annotations

# %% Inputs and declared format rules
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, variance

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FORMAT_SOURCES = [
    "https://www.pgatour.com/article/news/latest/2025/05/28/what-do-top-players-think-of-tour-championship-changes-scottie-scheffler",
    "https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/heroworldchallenge/roundInfo/R2_Notes.pdf",
    "https://www.pgatour.com/article/news/how-it-works/pga-tour-q-school-presented-by-korn-ferry-schedule-registration-dates-sites-locations-benefits-status-eligibility",
]


def canonical_name(value: str) -> str:
    value = value.casefold().replace("pres.", "presented")
    return "the open championship" if value == "the open" else value


def format_exclusion(name: str, year: int) -> str | None:
    name = name.casefold()
    if "match play" in name or "presidents cup" in name or "ryder cup" in name or name.startswith("the match"):
        return "match/team format"
    if "zurich classic" in name and year >= 2017:
        return "team format since 2017"
    if "grant thornton" in name or "showdown" in name:
        return "team/exhibition format"
    if "barracuda" in name:
        return "modified Stableford"
    if "hero world" in name:
        return "unofficial event"
    if "q-school" in name:
        return "qualifying event"
    if "tour championship" in name and 2019 <= year <= 2024:
        return "starting-stroke format"
    return None


def complete_score(raw: dict) -> int | None:
    holes = raw.get("linescores", [])
    if len(holes) != 18 or {h.get("period") for h in holes} != set(range(1, 19)):
        return None
    values = [h.get("value") for h in holes]
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool)
               and 1 <= v <= 20 and int(v) == v for v in values):
        return None
    score = raw.get("value")
    if not isinstance(score, (int, float)) or sum(values) != score:
        return None
    return int(score)


def date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def provenance(path: Path, url: str) -> dict:
    raw = path.read_bytes()
    return {"file": str(path.relative_to(ROOT)), "url": url, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def official_schedule(path: Path) -> dict[str, dict]:
    match = re.search(rb'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', path.read_bytes())
    data = json.loads(match[1])
    queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    source = next(q["state"]["data"] for q in queries if q["queryKey"][0] == "schedule")
    assert int(source["season"]) == 2025
    result = {}
    for event in source["tournaments"]:
        key = canonical_name(event["name"])
        assert key not in result
        result[key] = event
    return result


# %% Validate each complete round before retaining compact data

def load_events(source_dir: Path, schedule: dict) -> tuple[list[dict], list[dict], dict]:
    events, sources, exclusions, missing_entries, missing_player_ids = [], [], [], [], []
    seen_ids = set()
    for year in range(2015, 2026):
        path = source_dir / f"scoreboard-{year}.json"
        sources.append(provenance(path, f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={year}"))
        for event in json.loads(path.read_bytes())["events"]:
            if not event.get("id") or not event.get("date"):
                missing_entries.append({"source_year": year, "id": event.get("id"), "date": event.get("date")})
                continue
            if int(event["date"][:4]) != year or event["id"] in seen_ids:
                raise ValueError("calendar-year/duplicate event mismatch")
            seen_ids.add(event["id"])
            reason = format_exclusion(event["name"], year)
            off = schedule.get(canonical_name(event["name"])) if year == 2025 else None
            if year == 2025 and off is None:
                reason = reason or "not matched to official 2025 schedule"
            elif year == 2025:
                # Published schedule display dates can differ at the end when play is delayed.
                start_match = re.match(r"([A-Za-z]+) (\d+)", off["displayDate"])
                expected = datetime.strptime(f"2025 {start_match[1]} {start_match[2]}", "%Y %b %d").date()
                if date(event["date"]).date() != expected:
                    raise ValueError(f"schedule/API start-date mismatch: {event['name']}")
            if not reason and (len(event.get("competitions", [])) != 1
                               or not event.get("status", {}).get("type", {}).get("completed")):
                reason = "not one completed competition"
            if reason:
                exclusions.append({"year": year, "event_id": event["id"], "name": event["name"], "reason": reason})
                continue
            players = []
            invalid = Counter()
            for player in event["competitions"][0].get("competitors", []):
                if player.get("type") != "athlete":
                    raise ValueError(f"nonindividual in retained event {event['id']}")
                scores = {}
                for raw in player.get("linescores", []):
                    rnd = raw.get("period")
                    if rnd not in (1, 2, 3, 4):
                        continue
                    if rnd in scores:
                        raise ValueError("duplicate player round")
                    value = complete_score(raw)
                    if value is None:
                        invalid[str(rnd)] += 1
                    else:
                        scores[rnd] = value
                if not player.get("id"):
                    missing_player_ids.append({"year": year, "event_id": event["id"],
                                               "name": player["athlete"]["displayName"], "complete_rounds": len(scores)})
                    if scores:
                        raise ValueError("scored player without stable identity")
                    continue
                players.append({"id": str(player["id"]), "name": player["athlete"]["displayName"], "scores": scores})
            assert len({p['id'] for p in players}) == len(players)
            means = {r: mean(p["scores"][r] for p in players if r in p["scores"])
                     for r in (1, 2, 3, 4) if any(r in p["scores"] for p in players)}
            events.append({"id": event["id"], "name": event["name"], "start": event["date"], "end": event["endDate"],
                           "year": year, "official_id": off["tournamentId"] if off else None,
                           "players": players, "means": means, "invalid_rounds": dict(invalid)})
    present_2025 = {canonical_name(e["name"]) for e in events if e["year"] == 2025}
    unmatched = [{"official_id": e["tournamentId"], "name": e["name"],
                  "format_exclusion": format_exclusion(e["name"], 2025)}
                 for key, e in schedule.items() if key not in present_2025]
    if any(not e["format_exclusion"] for e in unmatched):
        raise ValueError(f"missing eligible official 2025 event: {unmatched}")
    return sorted(events, key=lambda e: (e["start"], e["id"])), sources, {
        "excluded_events": exclusions, "entries_without_id_or_date": missing_entries,
        "unscored_player_entries_without_id": missing_player_ids,
        "official_schedule_events_outside_retained_cohort": unmatched}


# %% Prior-only ability and pre-final-round exposure, with later attrition

def prepare(events: list[dict]) -> tuple[list[dict], dict]:
    histories = defaultdict(list)
    rows, event_audit = [], []
    for event in events:
        start, end = date(event["start"]), date(event["end"])
        assert end >= start
        players, means = event["players"], event["means"]
        counts = Counter()
        ready = [p for p in players if {1, 2, 3} <= p["scores"].keys()]
        leader = min((sum(p["scores"][r] for r in (1, 2, 3)) for p in ready), default=None)
        eligible_event = event["year"] == 2025 and set(means) == {1, 2, 3, 4}
        if event["year"] == 2025:
            counts["player_entries"] = len(players)
            counts["complete_r1_r2_r3"] = len(ready)
        for player in players:
            prior = sorted((h for h in histories[player["id"]] if h[0] < start), key=lambda h: (h[0], h[1], h[2]))[-20:]
            scores = player["scores"]
            if eligible_event and {1, 2, 3} <= scores.keys():
                behind = sum(scores[r] for r in (1, 2, 3)) - leader
                group = "exposed" if 4 <= behind <= 6 else "control" if 8 <= behind <= 10 else "other"
                counts[f"r3_{group}"] += 1
                if len(prior) < 10:
                    counts[f"r3_{group}_insufficient_prior"] += 1
                else:
                    ability = mean(h[3] for h in prior)
                    row = {"event_id": event["id"], "event_name": event["name"], "official_event_id": event["official_id"],
                           "event_start": event["start"], "player_id": player["id"], "player_name": player["name"],
                           "prior_count": len(prior), "prior_ability": ability, "ability_bin": math.floor(ability),
                           "latest_prior_event_end": prior[-1][0].isoformat(), "oldest_prior_event_end": prior[0][0].isoformat(),
                           "r3_cumulative_score": sum(scores[r] for r in (1, 2, 3)), "r3_leader_score": leader,
                           "strokes_behind": behind, "group": group, "r4_score": scores.get(4),
                           "r4_field_mean": means[4], "outcome": scores[4] - means[4] if 4 in scores else None}
                    rows.append(row)
                    counts[f"eligible_{group}"] += 1
                    counts[f"eligible_{group}_r4_{'observed' if 4 in scores else 'missing'}"] += 1
            for rnd, score in scores.items():
                histories[player["id"]].append((end, event["id"], rnd, score - means[rnd]))
        if event["year"] == 2025:
            event_audit.append({"event_id": event["id"], "official_event_id": event["official_id"], "name": event["name"],
                                "eligible_four_round_event": eligible_event, "complete_round_field_means": means,
                                "r3_leader_gross": leader,
                                "r3_leaders": [p["name"] for p in ready if sum(p["scores"][r] for r in (1, 2, 3)) == leader],
                                "invalid_rounds_by_period": event["invalid_rounds"], "counts": dict(counts)})
    totals = Counter()
    for event in event_audit:
        totals.update(event["counts"])
    assert all(date(r["latest_prior_event_end"]) < date(r["event_start"]) for r in rows)
    return rows, {"counts": dict(totals), "event_count": len(event_audit), "events": event_audit}


# %% Exposure-weighted within-ability-bin variance comparison

def compare(rows: list[dict], details: bool = True) -> dict:
    observed = [r for r in rows if r["group"] in ("exposed", "control") and r["outcome"] is not None]
    buckets = defaultdict(lambda: defaultdict(list))
    for row in observed:
        buckets[row["ability_bin"]][row["group"]].append(row)
    strata, omitted, included = [], [], []
    for key in sorted(buckets):
        e, c = buckets[key]["exposed"], buckets[key]["control"]
        if min(len(e), len(c)) < 2:
            omitted.append({"ability_bin_lower": key, "exposed": len(e), "control": len(c), "reason": "fewer than two in a group"})
            continue
        strata.append({"ability_bin_lower": key, "exposed": len(e), "control": len(c), "weight": len(e),
                       "exposed_variance": variance(r["outcome"] for r in e),
                       "control_variance": variance(r["outcome"] for r in c),
                       "exposed_mean": mean(r["outcome"] for r in e), "control_mean": mean(r["outcome"] for r in c)})
        included.extend(e + c)
    total = sum(s["weight"] for s in strata)
    weighted = {key: sum(s["weight"] * s[key] for s in strata) / total if total else None
                for key in ("exposed_variance", "control_variance", "exposed_mean", "control_mean")}
    ratio = weighted["exposed_variance"] / weighted["control_variance"] if weighted["control_variance"] else None
    exposed_events = len({r["event_id"] for r in included if r["group"] == "exposed"})
    enough = total >= 200 and exposed_events >= 15
    result = {"exposed_observed_in_contributing_bins": total,
              "control_observed_in_contributing_bins": sum(s["control"] for s in strata),
              "exposed_events_in_contributing_bins": exposed_events,
              "all_contributing_events": len({r["event_id"] for r in included}),
              **weighted, "variance_ratio": ratio,
              "weighted_mean_difference": weighted["exposed_mean"] - weighted["control_mean"] if total else None,
              "sample_gate_met": enough,
              "status": "unresolved: insufficient sample" if not enough or ratio is None else
                        "sport-side advance to price investigation" if ratio >= 1.15 else "sport-side dead at fixed screen"}
    if details:
        result.update({"contributing_bins": strata, "omitted_bins": omitted,
                       "unmatched_exposed_observed": sum(s["exposed"] for s in omitted),
                       "unmatched_control_observed": sum(s["control"] for s in omitted)})
    return result


def bootstrap(rows: list[dict], event_ids: list[str]) -> dict:
    by_event = defaultdict(list)
    for row in rows:
        by_event[row["event_id"]].append(row)
    rng = np.random.default_rng(20260915)
    results = []
    for _ in range(2000):
        sampled = [r for event_id in rng.choice(event_ids, len(event_ids), replace=True) for r in by_event[event_id]]
        result = compare(sampled, details=False)
        if result["variance_ratio"] is not None:
            results.append([result["variance_ratio"], result["weighted_mean_difference"]])
    return {"unit": "tournament", "replicates_requested": 2000, "valid_replicates": len(results), "seed": 20260915,
            "percentile_method": "NumPy linear", "variance_ratio_95_interval": np.quantile(np.array(results)[:, 0], [.025, .975]).tolist(),
            "weighted_mean_difference_95_interval": np.quantile(np.array(results)[:, 1], [.025, .975]).tolist()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data/raw/golf-sport")
    parser.add_argument("--schedule", type=Path, default=ROOT / "data/raw/golf-sunday-chasing/schedule-2025.html")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/golf-sunday-screen-2026-09-14")
    args = parser.parse_args()
    schedule = official_schedule(args.schedule)
    events, sources, source_audit = load_events(args.source_dir, schedule)
    sources.append(provenance(args.schedule, "https://www.pgatour.com/schedule/2025"))
    rows, attrition = prepare(events)
    comparison = compare(rows)
    intervals = bootstrap(rows, [e["event_id"] for e in attrition["events"] if e["eligible_four_round_event"]])
    row_path = ROOT / "data/raw/golf-sunday-chasing/screen-rows.json"
    row_path.write_text(json.dumps(rows, indent=2) + "\n")
    declaration = ROOT / "reports/golf-sunday-declaration-2026-09-14.md"
    result = {"as_of": "2026-09-14 America/Toronto", "card": "golf-sunday-chasing-variance", "scope": "2025 exploratory sport-side comparison; 2015–2024 and strictly earlier 2025 events supply prior ability",
              "declaration": {"file": str(declaration.relative_to(ROOT)), "sha256": hashlib.sha256(declaration.read_bytes()).hexdigest()},
              "sources": sources, "format_sources": FORMAT_SOURCES, "source_audit": source_audit,
              "attrition": attrition, "comparison": comparison, "bootstrap": intervals,
              "derived_rows": {"file": str(row_path.relative_to(ROOT)), "count": len(rows), "sha256": hashlib.sha256(row_path.read_bytes()).hexdigest()},
              "historical_live_trigger_verified": False, "fanduel_price_test": None}
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"comparison": comparison, "bootstrap": intervals, "counts": attrition["counts"], "events": attrition["event_count"]}, indent=2))


if __name__ == "__main__":
    main()
