#!/usr/bin/env python3
"""G1 predeclared directional wave screen, offline only.

--prepare classifies official tee schedules and freezes hashes. It reads no
forecast values or prepared scores. --compare requires the complete, verified
shared GFS acquisition. Do not compare until root review of the declaration.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
from statistics import mean
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from explore_golf_weather import ROOT, GROUPS, INVENTORY, RAW as WEATHER_RAW, dt, source
from beating.golf_collect import decode_payloads

RAW = ROOT / "data/raw/golf-wave"
DECLARATION = ROOT / "reports/golf-wave-declaration-2026-09-14.md"
REPORT = ROOT / "reports/golf-wave-screen-2026-09-14"
PREPARATION_REPORT = ROOT / "reports/golf-wave-preparation-2026-09-14.json"
PREPARED_SCORES = WEATHER_RAW / "prepared.json"


def scheduled_wave_round(event: dict, rnd: dict) -> dict:
    """Classify schedule alone; never inspect wind, ability, or scores."""
    result = {"pga_id": event["pga_id"], "event_id": event["espn_id"],
              "event_name": event["name"], "round": rnd["roundInt"],
              "timezone": event.get("timezone"), "scheduled_two_waves": False,
              "reason": None, "groups": []}
    courses = {str(c["id"]) for c in event.get("courses", [])}
    if len(courses) != 1:
        result["reason"] = "not_one_declared_course"
        return result
    result["course_id"] = next(iter(courses))
    try:
        zone = ZoneInfo(event["timezone"])
    except (KeyError, ZoneInfoNotFoundError, TypeError):
        result["reason"] = "missing_or_invalid_timezone"
        return result
    player_ids, group_ids, dates = set(), set(), set()
    for group in rnd.get("groups", []):
        tee = group.get("teeTime")
        if (not isinstance(tee, (int, float)) or isinstance(tee, bool)
                or not math.isfinite(tee) or tee <= 0):
            result["reason"] = "missing_or_invalid_tee_time"
            return result
        if (str(group.get("courseId")) not in courses
                or not isinstance(group.get("startTee"), int)
                or isinstance(group.get("startTee"), bool)
                or group["startTee"] not in range(1, 19)
                or not isinstance(group.get("groupNumber"), int)
                or isinstance(group.get("groupNumber"), bool)
                or group["groupNumber"] < 1):
            result["reason"] = "missing_or_conflicting_group_course_identity"
            return result
        gid = f"{rnd['roundInt']}:{group['groupNumber']}:{group['startTee']}"
        ids = [str(p["id"]) for p in group.get("players", []) if p.get("id")]
        if not ids or len(ids) != len(group.get("players", [])):
            result["reason"] = "missing_group_player_identity"
            return result
        if gid in group_ids or len(set(ids)) != len(ids) or player_ids.intersection(ids):
            result["reason"] = "duplicate_official_player_or_group_identity"
            return result
        player_ids.update(ids)
        group_ids.add(gid)
        try:
            local = datetime.fromtimestamp(tee / 1000, timezone.utc).astimezone(zone)
        except (ValueError, OverflowError, OSError):
            result["reason"] = "out_of_range_tee_time"
            return result
        dates.add(local.date().isoformat())
        result["groups"].append({"group_id": gid, "tee_time_ms": tee,
                                 "start_tee": group["startTee"],
                                 "pga_player_ids": ids, "scheduled_players": len(ids),
                                 "local_tee_time": local.isoformat(), "wave": None})
    result["scheduled_players"] = len(player_ids)
    result["scheduled_groups"] = len(group_ids)
    result["local_dates"] = sorted(dates)
    times = sorted({g["tee_time_ms"] for g in result["groups"]})
    if len(times) < 2:
        result["reason"] = "fewer_than_two_distinct_tee_times"
        return result
    gaps = [b - a for a, b in zip(times, times[1:])]
    largest = max(gaps)
    indices = [i for i, value in enumerate(gaps) if value == largest]
    result["largest_gap_minutes"] = largest / 60000
    result["largest_gap_ties"] = len(indices)
    if len(dates) != 1:
        result["reason"] = "scheduled_tees_span_multiple_local_dates"
        return result
    if largest < 60 * 60000:
        result["reason"] = "no_60_minute_schedule_gap"
        return result
    if len(indices) != 1:
        result["reason"] = "ambiguous_largest_schedule_gap"
        return result
    last_early, first_late = times[indices[0]], times[indices[0] + 1]
    early = sum(g["scheduled_players"] for g in result["groups"] if g["tee_time_ms"] <= last_early)
    late = result["scheduled_players"] - early
    result.update(early_scheduled_players=early, late_scheduled_players=late,
                  last_early_tee_time_ms=last_early, first_late_tee_time_ms=first_late)
    if min(early, late) / result["scheduled_players"] < .25:
        result["reason"] = "wave_has_under_25_percent_of_scheduled_players"
        return result
    for group in result["groups"]:
        group["wave"] = "early" if group["tee_time_ms"] <= last_early else "late"
    result["scheduled_two_waves"] = True
    return result


def prepare() -> None:
    inventory = json.loads(INVENTORY.read_text())
    if len(inventory["events"]) != 40 or len({e["pga_id"] for e in inventory["events"]}) != 40:
        raise ValueError("Declared 40-event cohort changed")
    # Hash only: do not parse scores or open any weather outputs in preparation.
    sources = [source(DECLARATION), source(INVENTORY), source(PREPARED_SCORES)]
    rounds = []
    for event in inventory["events"]:
        path = GROUPS / (event["pga_id"] + "-teetimes.json")
        sources.append(source(path))
        if source(path)["sha256"] != event["source"]["sha256"]:
            raise ValueError("Official tee source changed from inventory")
        payload = decode_payloads(json.loads(path.read_text()))["data"]["teeTimesCompressedV2"]["payload"]
        if payload["id"] != event["pga_id"]:
            raise ValueError("Wrong official tee event")
        opening = [r for r in payload["rounds"] if r["roundInt"] in (1, 2)]
        if len(opening) != 2 or {r["roundInt"] for r in opening} != {1, 2}:
            raise ValueError("Declared event lacks opening-round schedule accounting")
        rounds.extend(scheduled_wave_round(event, r) for r in opening)
    scheduled = [r for r in rounds if r["scheduled_two_waves"]]
    counts = {"declared_events": 40, "declared_rounds": len(rounds),
              "two_wave_schedule_rounds": len(scheduled),
              "two_wave_schedule_events": len({r["pga_id"] for r in scheduled}),
              "schedule_exclusion_reasons": dict(Counter(r["reason"] for r in rounds if not r["scheduled_two_waves"]))}
    if counts["two_wave_schedule_rounds"] != 53 or counts["two_wave_schedule_events"] != 27:
        raise ValueError("Pre-score metadata audit changed; inspect before any comparison")
    prepared = {"scope": "Tee-schedule preparation only; forecast values and prepared scores were not read",
                "sources": sources, "rounds": rounds, "counts": counts,
                "created_utc": datetime.now(timezone.utc).isoformat()}
    path = RAW / "prepared.json"
    if path.exists():
        old = json.loads(path.read_text())
        if old["sources"] != sources or old["rounds"] != rounds:
            raise ValueError("Frozen G1 preparation changed; do not overwrite it silently")
        prepared = old
    else:
        path.write_text(json.dumps(prepared, indent=2) + "\n")
    PREPARATION_REPORT.write_text(json.dumps({"scope": prepared["scope"], "counts": counts,
        "prepared_source": source(path), "sources": sources,
        "rounds": [{k: v for k, v in r.items() if k != "groups"} for r in rounds]}, indent=2) + "\n")
    print(json.dumps(counts, indent=2))


def require_hash(path: Path, expected: str) -> None:
    if source(path)["sha256"] != expected:
        raise ValueError(f"Frozen input or output changed: {path}")


def validated_inputs() -> tuple[dict, list[dict], dict, dict, list[dict]]:
    prepared_path = RAW / "prepared.json"
    prepared = json.loads(prepared_path.read_text())
    for item in prepared["sources"]:
        require_hash(ROOT / item["file"], item["sha256"])
    acquisition_path = ROOT / "reports/golf-weather-acquisition-2026-09-14.json"
    acquisition = json.loads(acquisition_path.read_text())
    if (acquisition.get("complete") is not True or acquisition.get("pending_event_hours") != 0
            or acquisition.get("stop_reason") is not None):
        raise ValueError("Finish the shared weather acquisition before G1 comparison")
    plan_path = ROOT / acquisition["plan_file"]
    plan = json.loads(plan_path.read_text())
    weather_path, hours_path = WEATHER_RAW / "rounds.json", WEATHER_RAW / "hours.json"
    for path, expected in (
        (plan_path, acquisition.get("plan_sha256")),
        (weather_path, acquisition.get("rounds_sha256")),
        (hours_path, acquisition.get("hours_sha256")),
        (ROOT / plan["inventory"]["path"], plan["inventory"]["sha256"]),
        (ROOT / plan["venues"]["path"], plan["venues"]["sha256"]),
        (ROOT / "reports/golf-weather-declaration-2026-09-14.md", plan["declaration_sha256"]),
    ):
        require_hash(path, expected)
    weather = json.loads(weather_path.read_text())
    expected = {(r["pga_id"], r["round"]) for r in prepared["rounds"]}
    if len(weather) != 80 or {(r["pga_id"], r["round"]) for r in weather} != expected:
        raise ValueError("Shared acquisition must account for all 80 rounds")
    if any(r.get("reason") in {"pending", "acquisition_incomplete", "budget_exhausted"} for r in weather):
        raise ValueError("Shared weather acquisition still has pending rounds")
    scores = json.loads(PREPARED_SCORES.read_text())
    for item in scores["sources"]:
        require_hash(ROOT / item["file"], item["sha256"])
    keys = [(r["pga_id"], r["round"], r["pga_player_id"]) for r in scores["rows"]]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate prepared official player-round")
    if any(not 10 <= r["prior_count"] <= 20 or dt(r["latest_prior_end"]) >= dt(r["event_start"])
           for r in scores["rows"]):
        raise ValueError("Prepared prior count or chronology changed")
    sources = [source(Path(__file__)), source(prepared_path), source(acquisition_path), source(plan_path),
               source(weather_path), source(hours_path), *prepared["sources"], *scores["sources"]]
    return prepared, weather, json.loads(hours_path.read_text()), scores, sources


def round_wind(w: dict, hours: dict) -> dict[float, float]:
    samples = {}
    for valid in w["valid_times_utc"]:
        hour = hours.get(w["pga_id"] + "/" + valid)
        if (not hour or hour.get("success") is not True or hour["valid_time_utc"] != valid
                or hour["run_utc"] != w["run_utc"]
                or dt(hour["object_last_modified_utc"]) >= dt(w["decision_cutoff_utc"])):
            raise ValueError("Classified round contradicts hourly identity or clock")
        value = hour["wind_kmh"]
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0
                or not math.isclose(value, 3.6 * math.hypot(hour["u_mps"], hour["v_mps"]), rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError("Invalid hourly wind magnitude")
        t = dt(valid).timestamp()
        if t % 3600 or t in samples:
            raise ValueError("Duplicate or non-hourly forecast timestamp")
        samples[t] = value
    times = sorted(samples)
    if not times or any(b - a != 3600 for a, b in zip(times, times[1:])):
        raise ValueError("Classified forecast window is incomplete")
    return samples


def five_hour_exposure(samples: dict[float, float], tee_ms: float) -> float:
    """Exact integral of piecewise-linear hourly wind speed over [tee,tee+5h]."""
    start, end = tee_ms / 1000, tee_ms / 1000 + 5 * 3600
    first, last = min(samples), max(samples)
    if start < first or end > last:
        raise ValueError("Full five-hour exposure lies outside the classified forecast window")

    def at(t):
        if t in samples:
            return samples[t]
        left = math.floor(t / 3600) * 3600
        return samples[left] + (samples[left + 3600] - samples[left]) * (t - left) / 3600

    breaks = [start, *sorted(t for t in samples if start < t < end), end]
    return sum((b - a) * (at(a) + at(b)) / 2 for a, b in zip(breaks, breaks[1:])) / (5 * 3600)


def compare() -> None:
    prepared, weather, hours, scores, sources = validated_inputs()
    weather_by_round = {(r["pga_id"], r["round"]): r for r in weather}
    scored = {(r["pga_id"], r["round"], r["pga_player_id"]): r for r in scores["rows"]}
    audits, contributing = [], []
    for scheduled in prepared["rounds"]:
        w = weather_by_round[(scheduled["pga_id"], scheduled["round"])]
        audit = {k: v for k, v in scheduled.items() if k != "groups"}
        audit.update(weather_classified=w["classified"], weather_reason=w["reason"],
                     contributed=False, forecast_stroke_magnitude=None)
        if not scheduled["scheduled_two_waves"]:
            audits.append(audit)
            continue
        if str(w["course_id"]) != scheduled["course_id"]:
            raise ValueError("Wave and forecast course identity differs")
        if not w["classified"]:
            audit["reason"] = "unclassified_weather"
            audits.append(audit)
            continue
        samples = round_wind(w, hours)
        exposures, wave_scores, groups = {"early": [], "late": []}, {"early": [], "late": []}, []
        for group in scheduled["groups"]:
            value = five_hour_exposure(samples, group["tee_time_ms"])
            # Forecast direction is weighted by all scheduled players, independent of score attrition.
            exposures[group["wave"]].extend([value] * group["scheduled_players"])
            joined = []
            for pid in group["pga_player_ids"]:
                row = scored.get((scheduled["pga_id"], scheduled["round"], pid))
                if row is None:
                    continue
                if (row["course_id"] != scheduled["course_id"] or row["group_id"] != group["group_id"]
                        or row["tee_time_ms"] != group["tee_time_ms"]):
                    raise ValueError("Prepared score differs from frozen official group/time")
                joined.append(row)
                wave_scores[group["wave"]].append(row)
            groups.append({"group_id": group["group_id"], "wave": group["wave"],
                           "scheduled_players": group["scheduled_players"], "joined_players": len(joined),
                           "forecast_five_hour_wind_kmh": value})
        winds = {wave: mean(values) for wave, values in exposures.items()}
        gap = winds["late"] - winds["early"]
        audit.update(early_wind_kmh=winds["early"], late_wind_kmh=winds["late"],
                     late_minus_early_wind_kmh=gap,
                     early_scored_players=len(wave_scores["early"]), late_scored_players=len(wave_scores["late"]),
                     early_missing_score_or_history=scheduled["early_scheduled_players"] - len(wave_scores["early"]),
                     late_missing_score_or_history=scheduled["late_scheduled_players"] - len(wave_scores["late"]),
                     group_exposures=groups)
        if gap == 0:
            audit["reason"] = "exactly_zero_forecast_wave_difference"
        elif min(map(len, wave_scores.values())) < 2:
            audit["reason"] = "fewer_than_two_eligible_scored_players_in_a_wave"
        else:
            residuals = {wave: mean(r["score"] - r["prior_ability"] for r in rows)
                         for wave, rows in wave_scores.items()}
            score_gap = residuals["late"] - residuals["early"]
            signed = score_gap if gap > 0 else -score_gap
            audit.update(reason=None, contributed=True, forecast_harder_wave="late" if gap > 0 else "early",
                         late_minus_early_adjusted_strokes=score_gap, signed_directional_strokes=signed,
                         contributing_espn_player_ids=sorted({r["player_id"] for rows in wave_scores.values() for r in rows}, key=int))
            contributing.append(audit)
        audits.append(audit)
    by_event = defaultdict(list)
    for r in contributing:
        by_event[r["pga_id"]].append(r)
    event_results = [{"pga_id": key, "event_name": rows[0]["event_name"],
                      "contributing_rounds": [r["round"] for r in rows],
                      "directional_strokes": mean(r["signed_directional_strokes"] for r in rows)}
                     for key, rows in sorted(by_event.items())]
    effect = mean(e["directional_strokes"] for e in event_results) if event_results else None
    rng, draws = random.Random(20260916), []
    if len(event_results) >= 2:
        for _ in range(5000):
            draws.append(mean(e["directional_strokes"] for e in rng.choices(event_results, k=len(event_results))))
    draws.sort()
    enough = len(event_results) >= 20
    status = ("unresolved: insufficient directional sample" if not enough or effect is None else
              "directional sport-side gate passes; magnitude and prices untested" if effect >= .3 else
              "sport-side dead at fixed directional screen")
    interval = [draws[int(.025 * len(draws))], draws[int(.975 * len(draws))]] if draws else None
    report = {"as_of_local_date": "2026-09-14", "card": "G1", "status": status,
              "pooled_directional_strokes": effect, "sample_gate_met": enough,
              "effect_gate_met": effect is not None and effect >= .3,
              "contributing_events": len(event_results), "contributing_rounds": len(contributing),
              "contributing_player_rounds": sum(r["early_scored_players"] + r["late_scored_players"] for r in contributing),
              "unique_players": len({p for r in contributing for p in r["contributing_espn_player_ids"]}),
              "event_bootstrap_95_interval": interval,
              "bootstrap": {"seed": 20260916, "replicates": len(draws),
                            "conditioning": "Equal-weight whole contributing events; retain original R1/R2 means and source attrition"},
              "forecast_stroke_magnitude": None, "forecast_revision_response_tested": False,
              "market_prices_compared": False, "weather_volatility_filter_used": False,
              "preparation_counts": prepared["counts"], "round_attrition": dict(Counter(r["reason"] for r in audits if not r["contributed"])),
              "rounds": audits, "event_results": event_results,
              "shared_player_attrition": scores["event_audit"], "sources": sources}
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    shown = "undefined" if effect is None else f"{effect:+.3f} strokes"
    REPORT.with_suffix(".md").write_text(f"""# G1 forecast wave-direction screen

**{status}.** Forecast-harder-minus-forecast-easier ability-adjusted scoring: **{shown}**, averaged equally across {len(event_results)} events and their {len(contributing)} contributing opening rounds. The fixed gates require +0.3 strokes and 20 events.

The [declaration](golf-wave-declaration-2026-09-14.md) fixes schedule-only wave identification, five-hour player exposure, every nonzero forecast direction, prior-only ability, event weighting and the bootstrap. Event-bootstrap 95% interval: {interval}. Full source hashes, every excluded round, per-wave player counts, signed results and diagnostic forecast gaps are in [the JSON report](golf-wave-screen-2026-09-14.json).

This tests **forecast direction**, not calibrated predicted stroke magnitude. No km/h-to-strokes coefficient or numerical pre-round stroke prediction was fitted. No G10 volatile-weather filter was used, and negative directional results remain in the average. The original forecast-revision response and numerical predicted-shift claims remain untested.

The operational run and archive clock checks come from the shared GFS acquisition. Retrospectively fetched tee sheets may reflect rescheduling; scheduled five-hour windows approximate actual play. Weather, firmness, player composition and imperfect ability control remain confounded. Recurring players and venues limit event-bootstrap interpretation. These observations do not prove historical quote-time availability.

No FanDuel markets, prices, settlement-aware returns or internal formula were tested. No betting edge is established. A directional pass requires separately declared magnitude calibration and actual timestamped offers before a book-side claim.

Reproduce offline: `state/runtime/research-venv/bin/python tools/explore_golf_wave.py --compare`.
""")
    print(json.dumps({k: report[k] for k in ("status", "pooled_directional_strokes", "contributing_events", "contributing_rounds")}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--prepare", action="store_true")
    commands.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    prepare() if args.prepare else compare()


if __name__ == "__main__":
    main()
