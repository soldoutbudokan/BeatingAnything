#!/usr/bin/env python3
"""Cheap, offline-replayable G3/G2 exploration from public ESPN golf data.

Fetch: python tools/explore_golf_sport.py --fetch --acquire-only
Screen: python tools/explore_golf_sport.py
No odds, fitted pricing model, confirmation cohort, alerts or wagers.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import time
import unicodedata
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/golf-sport"
REPORT = ROOT / "reports/golf-sport-screen-2026-09-14"
YEARS = (2024, 2025)
# Whole-event exclusions keep course identity and scoring format unambiguous.
EXCLUSIONS = {
    "The American Express": "multiple courses",
    "Farmers Insurance Open": "multiple courses",
    "AT&T Pebble Beach Pro-Am": "multiple courses",
    "The RSM Classic": "multiple courses",
    "PGA TOUR Q-School presented by Korn Ferry": "multiple courses / qualifying",
    "Zurich Classic of New Orleans": "team competition",
    "Ryder Cup": "team match play",
    "Presidents Cup": "team match play",
    "Barracuda Championship": "modified Stableford",
    "TOUR Championship": "starting-stroke format changed between years",
    "Crypto.com Showdown": "team exhibition / mixed formats",
}


def fetch(name: str, url: str) -> None:
    path = RAW / name
    if path.exists():
        return
    # Stop at an ordinary denial. No retries, credentials or challenge handling.
    with urlopen(url, timeout=45) as response:
        body = response.read()
        path.write_bytes(body)
        meta = {"url": url, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": response.status, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest()}
        path.with_suffix(path.suffix + ".capture.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"fetched {name} ({len(body)} bytes)", flush=True)
    time.sleep(1)


def events() -> list[dict]:
    result = []
    for year in YEARS:
        source = json.loads((RAW / f"scoreboard-{year}.json").read_text())
        result.extend(source["events"])
    return sorted(result, key=lambda e: (e["date"], e["id"]))


def acquire_history() -> None:
    inventory = []
    for year in range(2015, 2026):
        url = f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={year}"
        path = RAW / f"scoreboard-{year}.json"
        fetch(path.name, url)
        body = path.read_bytes()
        observed = json.loads(body)["events"]
        dated = [e for e in observed if e.get("date")]
        if not dated or any(int(e["date"][:4]) != year for e in dated):
            raise ValueError(f"Calendar event dates do not match requested year {year}")
        competitors = [c for e in observed for comp in e.get("competitions", []) for c in comp.get("competitors", [])]
        inventory.append({"year": year, "raw_event_entries": len(observed), "events": sum(bool(e.get("id")) for e in observed),
                          "dated_events": len(dated), "entries_missing_date": len(observed) - len(dated),
                          "entries_missing_event_id": sum(not e.get("id") for e in observed),
                          "player_event_records": sum(c.get("type") == "athlete" for c in competitors),
                          "round_records": sum(1 <= r.get("period", 0) <= 4 for c in competitors for r in c.get("linescores", [])),
                          "season_labels": dict(Counter(str(e.get("season", {}).get("year")) for e in observed)),
                          "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                          "url": url, "file": str(path.relative_to(ROOT))})
    result = {"as_of": "2026-09-14", "scope": "Calendar-year 2015–2025 ESPN scoreboard acquisition only; no additional outcomes compared. Declared screens remain 2025 with 2024 warmup.",
              "validation": "Every available event start date is in the requested calendar year. Missing/empty event entries are counted separately. Season labels can differ for historical fall events.",
              "calendar_years": inventory, "events": sum(r["events"] for r in inventory),
              "raw_event_entries": sum(r["raw_event_entries"] for r in inventory),
              "entries_missing_date": sum(r["entries_missing_date"] for r in inventory),
              "bytes": sum(r["bytes"] for r in inventory),
              "player_event_records": sum(r["player_event_records"] for r in inventory),
              "round_records": sum(r["round_records"] for r in inventory)}
    path = ROOT / "reports/golf-history-inventory-2026-09-14.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "calendar_years"}, indent=2))


def exclusion(event: dict) -> str | None:
    if event["name"] in EXCLUSIONS:
        return EXCLUSIONS[event["name"]]
    if not event.get("competitions", [{}])[0].get("competitors"):
        return "no competitor records"
    if not event.get("status", {}).get("type", {}).get("completed"):
        return "not completed"
    return None


def statuses(event: dict) -> dict[str, dict]:
    path = RAW / f"leaderboard-{event['id']}.html"
    if not path.exists():
        return {}
    html = path.read_text()
    prefix = "window['__espnfitt__']="
    start = html.find(prefix)
    if start < 0:
        raise ValueError(f"Missing ESPN page data: {path}")
    page, _ = json.JSONDecoder().raw_decode(html[start + len(prefix):])
    leaderboard = page["page"]["content"]["leaderboard"]
    competitors = leaderboard.get("competitors", [])
    if not competitors:
        return {}
    # Some ESPN pages use query defaults; verify stable participant IDs against API.
    expected = {str(c["id"]) for c in event["competitions"][0]["competitors"]}
    actual = {str(c["id"]) for c in competitors}
    if not actual or len(actual & expected) / len(expected) < 0.95:
        raise ValueError(f"HTML/API participant mismatch: {event['id']}")
    return {str(c["id"]): c for c in competitors}


def round_record(raw: dict) -> dict:
    holes = [h for h in raw.get("linescores", [])
             if isinstance(h.get("value"), (int, float)) and h["value"] > 0
             and 1 <= h.get("period", 0) <= 18]
    hole_ids = [h["period"] for h in holes]
    complete = (len(holes) == 18 and len(set(hole_ids)) == 18
                and raw.get("value") == sum(h["value"] for h in holes))
    times = [s["displayValue"] for cat in raw.get("statistics", {}).get("categories", [])
             for s in cat.get("stats", [])
             if re.fullmatch(r"\w{3} \w{3} \d{2} \d{2}:\d{2}:\d{2} \w+ \d{4}", s.get("displayValue", ""))]
    return {"round": raw["period"], "score": raw.get("value"), "holes": len(holes),
            "complete": complete, "tee_time_as_published": times[0] if len(times) == 1 else None,
            "start_hole": hole_ids[0] if hole_ids else None}


def sony_group_spotcheck(all_events: list[dict]) -> dict:
    path = ROOT / "data/raw/golf-source-check/sony-2025-teetimes.decoded.json"
    if not path.exists():
        return {"status": "optional official Sony source not cached"}
    def norm(value: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if c.isalnum())
    official = json.loads(path.read_text())["data"]["teeTimesCompressedV2"]["payload"]
    published = {(r["roundInt"], g["startTee"], tuple(sorted(norm(p["displayName"]) for p in g["players"])))
                 for r in official["rounds"] for g in r["groups"]}
    event = next(e for e in all_events if e["id"] == "401703490")
    inferred = defaultdict(list)
    for c in event["competitions"][0]["competitors"]:
        for raw in c.get("linescores", []):
            if not 1 <= raw["period"] <= 4:
                continue
            r = round_record(raw)
            if r["tee_time_as_published"] and r["start_hole"] in (1, 10):
                inferred[(r["round"], r["start_hole"], r["tee_time_as_published"])].append((c["athlete"]["displayName"], r["complete"]))
    count, unmatched = Counter(), []
    for (rnd, tee, clock), group in inferred.items():
        matched = (rnd, tee, tuple(sorted(norm(name) for name, _ in group))) in published
        count["inferred_groups"] += 1
        count["exact_normalized_membership_matches"] += matched
        if len(group) == 3 and all(ok for _, ok in group):
            count["complete_triples"] += 1
            count["matched_complete_triples"] += matched
        if not matched:
            unmatched.append({"round": rnd, "start_tee": tee, "names": [name for name, _ in group]})
    return {"official_event": "R2025006", "espn_event": event["id"], "official_groups": len(published),
            **count, "unmatched": unmatched, "source_file": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "scope": "One event only; normalized names, round and start tee, no fuzzy aliases or cross-provider ID rewrite. Time-zone labels not validated."}


def g3_stats(groups: list[dict]) -> dict:
    n = len(groups)
    if not n:
        return {"groups": 0}
    strict = [0.0] * 3
    shares = [0.0] * 3
    ties = Counter()
    for group in groups:
        scores = group["scores_by_prior_ability"]
        winners = [i for i, score in enumerate(scores) if score == min(scores)]
        ties[len(winners)] += 1
        for i in winners:
            shares[i] += 1 / len(winners)
            strict[i] += len(winners) == 1
    unique = ties[1]
    p_eff = [v / n for v in shares]
    q_strict = [v / unique if unique else None for v in strict]
    correction = [100 * (p - q) if q is not None else None for p, q in zip(p_eff, q_strict)]
    return {"groups": n, "events": len({g["event_id"] for g in groups}),
            "unique_winner_groups": unique, "two_way_low_ties": ties[2], "three_way_ties": ties[3],
            "tie_for_low_rate": (ties[2] + ties[3]) / n,
            "dead_heat_effective_probabilities_best_middle_worst": p_eff,
            "normalized_strict_win_probabilities_best_middle_worst": q_strict,
            "correction_percentage_points_best_middle_worst": correction,
            "max_absolute_correction_percentage_points": max(abs(v) for v in correction if v is not None)}


def cluster_intervals(groups: list[dict], reps: int = 1500) -> list[list[float]]:
    """Event bootstrap keeps paired rounds and all players from an event together."""
    by_event = defaultdict(list)
    for group in groups:
        by_event[group["event_id"]].append(group)
    keys = sorted(by_event)
    if len(keys) < 2:
        return []
    rng = random.Random(73109)
    draws = [[] for _ in range(3)]
    for _ in range(reps):
        sample = [g for key in rng.choices(keys, k=len(keys)) for g in by_event[key]]
        vals = g3_stats(sample)["correction_percentage_points_best_middle_worst"]
        for dest, value in zip(draws, vals):
            dest.append(value)
    return [[sorted(v)[int(reps * .025)], sorted(v)[int(reps * .975)]] for v in draws]


def rate_info(rows: list[dict]) -> dict:
    n = len(rows)
    wd = sum(row["after_start_wd"] for row in rows)
    if not n:
        return {"starts": 0, "after_start_withdrawals": 0, "rate": None, "wilson_95_interval": None}
    p = wd / n
    den = 1 + 1.96 ** 2 / n
    mid = (p + 1.96 ** 2 / (2 * n)) / den
    half = 1.96 * math.sqrt(p * (1 - p) / n + 1.96 ** 2 / (4 * n ** 2)) / den
    return {"starts": n, "after_start_withdrawals": wd, "rate": p,
            "events": len({r["event_id"] for r in rows}), "wilson_95_interval": [mid - half, mid + half]}


def wd_cluster_interval(rows: list[dict], cluster_key: str, reps: int = 1500) -> list[float] | None:
    totals = defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        offset = 0 if row["exposed_prior90_observed_after_start_wd"] else 2
        totals[row[cluster_key]][offset] += 1
        totals[row[cluster_key]][offset + 1] += row["after_start_wd"]
    values = list(totals.values())
    if len(values) < 2 or not any(v[0] for v in values) or not any(v[2] for v in values):
        return None
    rng, draws = random.Random(73902), []
    for _ in range(reps):
        selected = rng.choices(values, k=len(values))
        en, ew, bn, bw = (sum(v[i] for v in selected) for i in range(4))
        if en and bn:
            draws.append(100 * (ew / en - bw / bn))
    draws.sort()
    return [draws[int(len(draws) * .025)], draws[int(len(draws) * .975)]] if draws else None


def screen(all_events: list[dict]) -> dict:
    history = defaultdict(list)
    wd_history = defaultdict(list)
    unknown_wd_history = defaultdict(list)
    all_groups, ranked_groups, starts = [], [], []
    attrition = Counter()
    attrition_by_year = {str(y): Counter() for y in YEARS}
    event_inventory = []
    event_sds, residuals, complete_rounds = [], [], []
    withdrawal_records = []
    coverage_start = date.fromisoformat(all_events[0]["date"][:10])
    for event in all_events:
        previous_counts = attrition.copy()
        event_year = event["date"][:4]
        why = exclusion(event)
        if why:
            event_inventory.append({"id": event["id"], "name": event["name"], "excluded": why})
            attrition["excluded_events"] += 1
            attrition_by_year[event_year]["excluded_events"] += 1
            continue
        stamp = date.fromisoformat(event["date"][:10])
        end_stamp = date.fromisoformat(event["endDate"][:10])
        finals = statuses(event)
        players = []
        for c in event["competitions"][0]["competitors"]:
            if c.get("type") != "athlete":
                attrition["non_athlete_records"] += 1
                continue
            pid = str(c["id"])
            rounds = [round_record(r) for r in c.get("linescores", []) if 1 <= r.get("period", 0) <= 4]
            prior = [score for day, score in history[pid] if day < stamp][-20:]
            skill = statistics.mean(prior) if len(prior) >= 10 else None
            final = finals.get(pid)
            detail = final.get("detail", "") if final else None
            holes = sum(r["holes"] for r in rounds)
            player = {"id": pid, "name": c["athlete"]["displayName"], "rounds": rounds,
                      "prior_skill": skill, "prior_rounds": len(prior), "detail": detail}
            players.append(player)
            attrition["player_event_records"] += 1
            # At least one completed scored hole proves starting. Zero holes does not
            # prove a pre-start WD: a player may hit a stroke then WD on the first hole.
            is_wd = detail in {"WD", "W/D"}
            if is_wd:
                withdrawal_records.append({"event_id": event["id"], "event": event["name"],
                                           "date": str(stamp), "player_id": pid, "player": player["name"],
                                           "completed_holes": holes,
                                           "timing": "after_start_proven" if holes else "unknown_zero_recorded_holes"})
            if not final:
                attrition["g2_missing_final_status"] += 1
                if stamp.year == 2025:
                    attrition["g2_missing_final_status_primary"] += 1
                elif end_stamp >= date(2024, 10, 4):
                    attrition["g2_missing_final_status_required_warmup"] += 1
            elif holes == 0:
                attrition["g2_zero_holes_unknown_start"] += 1
            elif stamp.year != 2025:
                attrition["g2_warmup_not_outcome"] += 1
            elif stamp - coverage_start < timedelta(days=90):
                attrition["g2_first_90_days_censored"] += 1
            else:
                prior_wds = [day for day in wd_history[pid] if stamp - timedelta(days=90) <= day < stamp]
                prior_unknown = [day for day in unknown_wd_history[pid] if stamp - timedelta(days=90) <= day < stamp]
                row = {"event_id": event["id"], "date": str(stamp), "player_id": pid,
                       "exposed_prior90_observed_after_start_wd": bool(prior_wds),
                       "prior90_unknown_timing_wd": bool(prior_unknown),
                       "after_start_wd": is_wd, "completed_holes": holes,
                       "fall_calendar_proxy": stamp.month >= 9}
                starts.append(row)
            if is_wd:
                (wd_history if holes else unknown_wd_history)[pid].append(end_stamp)
        groups_here = defaultdict(list)
        future_history = []
        for rnd in range(1, 5):
            valid = [(p, r) for p in players for r in p["rounds"] if r["round"] == rnd and r["complete"]]
            if len(valid) >= 2:
                avg = statistics.mean(r["score"] for _, r in valid)
                sd = statistics.stdev(r["score"] for _, r in valid)
                if stamp.year == 2025:
                    event_sds.append({"event_id": event["id"], "round": rnd, "n": len(valid), "sd": sd})
                for p, r in valid:
                    future_history.append((p["id"], end_stamp, r["score"] - avg))
                    if stamp.year != 2025:
                        continue
                    complete_rounds.append({"event_id": event["id"], "round": rnd,
                                            "player_id": p["id"], "score": r["score"],
                                            "field_round_residual": r["score"] - avg,
                                            "prior_skill": p["prior_skill"]})
                    if p["prior_skill"] is not None:
                        residuals.append(r["score"] - avg - p["prior_skill"])
            for p in players:
                for r in p["rounds"]:
                    if r["round"] != rnd:
                        continue
                    attrition["round_records"] += 1
                    if not r["tee_time_as_published"] or r["start_hole"] not in {1, 10}:
                        attrition["g3_missing_time_or_start_hole"] += 1
                        continue
                    key = (rnd, r["tee_time_as_published"], r["start_hole"])
                    groups_here[key].append((p, r))
        for (rnd, tee, hole), group in groups_here.items():
            attrition[f"g3_source_groups_size_{len(group)}"] += 1
            if len(group) != 3:
                continue
            if not all(r["complete"] for _, r in group):
                attrition["g3_triples_incomplete_scores"] += 1
                continue
            rec = {"event_id": event["id"], "event": event["name"], "year": stamp.year,
                   "round": rnd, "tee_time_as_published": tee, "start_hole": hole,
                   "player_ids": [p["id"] for p, _ in group],
                   "scores_by_prior_ability": [r["score"] for _, r in group]}
            if stamp.year == 2025:
                all_groups.append(rec)
            if any(p["prior_skill"] is None for p, _ in group):
                attrition["g3_triples_insufficient_prior_rounds"] += 1
                continue
            ordered = sorted(group, key=lambda item: item[0]["prior_skill"])
            means = [p["prior_skill"] for p, _ in ordered]
            if len(set(means)) != 3:
                attrition["g3_triples_tied_prior_ability"] += 1
                continue
            rec = dict(rec, player_ids=[p["id"] for p, _ in ordered],
                       scores_by_prior_ability=[r["score"] for _, r in ordered],
                       prior_skill=means, prior_round_counts=[p["prior_rounds"] for p, _ in ordered],
                       skill_gap=means[2] - means[0])
            if stamp.year == 2025:
                ranked_groups.append(rec)
        for pid, day, score in future_history:
            history[pid].append((day, score))
        event_inventory.append({"id": event["id"], "name": event["name"], "date": str(stamp),
                                "players": len(players), "html_status_rows": len(finals)})
        attrition_by_year[event_year].update(attrition - previous_counts)
    g3 = g3_stats(ranked_groups)
    g3["official_group_spotcheck"] = sony_group_spotcheck(all_events)
    g3["event_bootstrap_95_correction_percentage_points"] = cluster_intervals(ranked_groups)
    g3["complete_actual_triples_before_ability_filter"] = len(all_groups)
    g3["complete_actual_triples_tie_rate_before_ability_filter"] = g3_stats(all_groups).get("tie_for_low_rate")
    g3["by_year"] = {str(y): g3_stats([g for g in ranked_groups if g["year"] == y]) for y in YEARS}
    g3["by_round"] = {str(r): g3_stats([g for g in ranked_groups if g["round"] == r]) for r in range(1, 5)}
    g3["by_skill_gap"] = {label: g3_stats([g for g in ranked_groups if lo <= g["skill_gap"] < hi])
                          for label, lo, hi in [("under_1_stroke", 0, 1), ("1_to_2_strokes", 1, 2), ("2_plus_strokes", 2, math.inf)]}
    g3["passes_sample_gate"] = g3["groups"] >= 300 and g3["events"] >= 5
    g3["passes_pooled_correction_gate"] = g3["max_absolute_correction_percentage_points"] > 1
    g3["decision"] = "dead_pooled_screen" if g3["passes_sample_gate"] and not g3["passes_pooled_correction_gate"] else "unresolved_or_needs_book_side"
    denom = sum(r["n"] - 1 for r in event_sds)
    dispersion = {"complete_player_rounds": len(complete_rounds), "course_round_cells": len(event_sds),
                  "pooled_within_course_round_sd": math.sqrt(sum((r["n"] - 1) * r["sd"] ** 2 for r in event_sds) / denom),
                  "prior_ability_adjusted_residual_sd": statistics.stdev(residuals),
                  "prior_ability_adjusted_rounds": len(residuals),
                  "median_course_round_sd": statistics.median(r["sd"] for r in event_sds),
                  "interpretation": "Observed score dispersion, not identified intrinsic player sigma. Field strength, noisy ability, weather/waves and survivor selection remain."}
    clean = [r for r in starts if not r["prior90_unknown_timing_wd"]]
    exposed = [r for r in clean if r["exposed_prior90_observed_after_start_wd"]]
    base = [r for r in clean if not r["exposed_prior90_observed_after_start_wd"]]
    exp_stats, base_stats = rate_info(exposed), rate_info(base)
    g2 = {"data_complete": not (attrition["g2_missing_final_status_primary"] or attrition["g2_missing_final_status_required_warmup"]),
          "observed_started_player_events": len(starts), "prior_unknown_timing_excluded": len(starts) - len(clean),
          "overall": rate_info(clean), "prior90_after_start_wd": exp_stats, "no_observed_prior90_after_start_wd": base_stats,
          "rate_difference_percentage_points": 100 * (exp_stats["rate"] - base_stats["rate"]) if exposed and base else None,
          "relative_risk": exp_stats["rate"] / base_stats["rate"] if exposed and base_stats["rate"] else None,
          "event_bootstrap_95_rate_difference_percentage_points": wd_cluster_interval(clean, "event_id"),
          "player_bootstrap_95_rate_difference_percentage_points": wd_cluster_interval(clean, "player_id"),
          "wd_timing_counts": dict(Counter(r["timing"] for r in withdrawal_records)),
          "passes_sample_gate": bool(exposed and exp_stats["starts"] >= 100 and exp_stats["after_start_withdrawals"] >= 10 and exp_stats["events"] >= 5),
          "passes_rate_gate": bool(exposed and exp_stats["rate"] >= .03 and exp_stats["rate"] > base_stats["rate"]),
          "by_year": {str(y): {"exposed": rate_info([r for r in exposed if r["date"].startswith(str(y))]),
                                "unexposed": rate_info([r for r in base if r["date"].startswith(str(y))])} for y in YEARS},
          "fall_calendar_proxy": {"fall": rate_info([r for r in clean if r["fall_calendar_proxy"]]),
                                  "other": rate_info([r for r in clean if not r["fall_calendar_proxy"]])},
          "limitations": ["Prior withdrawal means observed in retained single-course PGA events; excluded formats, other tours and unlisted pre-start entrants are not covered.",
                          "Zero-hole withdrawals have unknown timing; they are not asserted pre-start and their next-90-day starts are censored.",
                          "At least one completed hole proves a start, but first-hole withdrawals after a stroke are missing from this lower-bound after-start sample.",
                          "Final historical WD labels are used retrospectively with event-end dates; no as-published injury news or pre-round snapshot was recovered.",
                          "Age and true FedExCup status-position effects untested; calendar fall is a descriptive proxy only.",
                          "This is withdrawal incidence, not matchup settlement or an executable book-side discrepancy."]}
    g2["decision"] = ("unresolved_inadequate_sample_or_status_coverage" if not g2["passes_sample_gate"] or not g2["data_complete"]
                      else "sport_side_only_needs_book_screen" if g2["passes_rate_gate"] else "dead_screen")
    (RAW / "screen-groups.json").write_text(json.dumps(ranked_groups, indent=2) + "\n")
    (RAW / "screen-withdrawals.json").write_text(json.dumps(withdrawal_records, indent=2) + "\n")
    (RAW / "screen-starts.json").write_text(json.dumps(starts, indent=2) + "\n")
    (RAW / "screen-rounds.json").write_text(json.dumps(complete_rounds, indent=2) + "\n")
    used_names = {f"scoreboard-{y}.json" for y in YEARS} | {f"leaderboard-{e['id']}.html" for e in all_events if not exclusion(e)}
    return {"as_of": "2026-09-14", "history_years": list(YEARS), "primary_screen_year": 2025, "source": "ESPN public season scoreboards and event leaderboard HTML",
            "scope": "2025 exploratory outcomes with 2024 warmup; not the planned full 2015–2025 archive or the separate fixed 2025 Sunday-variance card",
            "event_inventory": event_inventory, "attrition": dict(attrition), "attrition_by_year": attrition_by_year,
            "dispersion": dispersion, "g3": g3, "g2": g2,
            "source_files": [{"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(RAW.iterdir())
                              if p.name in used_names]}


def write_report(result: dict) -> None:
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    g3, g2, sd = (result[k] for k in ("g3", "g2", "dispersion"))
    exp, base = g2["prior90_after_start_wd"], g2["no_observed_prior90_after_start_wd"]
    primary_attrition = result["attrition_by_year"]["2025"]
    spot = g3["official_group_spotcheck"]
    spot_text = (f"Official PGA TOUR Sony Open spot-check: {spot['exact_normalized_membership_matches']}/{spot['inferred_groups']} "
                 f"source groups and {spot['matched_complete_triples']}/{spot['complete_triples']} complete triples matched by normalized "
                 "player names, round and starting tee. The two unmatched groups contain ESPN's Kristoffer Ventura versus PGA TOUR's Kris Ventura; "
                 "that name was not rewritten. This supports the reconstruction at one event and does not certify all events' group IDs."
                 if "inferred_groups" in spot else "Official Sony group spot-check input is not cached.")
    lines = ["# Golf sport-side screens — September 14, 2026", "",
             "Exploration only. No FanDuel discrepancy, confirmation cohort, alert or wager is established.", "",
             "## Inputs and scope", "",
             "The public [2024 ESPN season scoreboard](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2024) and "
             "[2025 scoreboard](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025) returned HTTP 200 on this machine. "
             "They supply stable player IDs, round scores, ordered hole scores and per-round tee-time strings. "
             "Public event leaderboard HTML supplies final WD/CUT/DQ labels. This is a bounded 2025 exploration with 2024 warmup, not the proposed full 2015–2025 archive. "
             "The separate historical Sunday-variance card has not been run or redefined.", "",
             f"Included {sum('excluded' not in e for e in result['event_inventory'])} events across the two input years "
             f"({sum(e.get('date', '').startswith('2025') for e in result['event_inventory'])} in the primary 2025 screen); excluded {result['attrition']['excluded_events']} "
             "for multiple courses, team/match play, Stableford, changing starting-stroke formats, qualifying, missing records or incomplete event status. "
             "Whole-event exclusions make course identity unambiguous. Detailed event exclusions and row attrition are in the JSON report.", "",
             "## G3: 3-ball dead-heat correction", "",
             "Groups are the source's identical event/round/tee-time/start-hole combinations, with exactly three players and three complete 18-hole scores. "
             "These are observed tee-group proxies: ESPN does not supply an explicit group ID in this response. "
             "Starting hole is the first hole in the source's ordered score list. Groups were never fabricated by shuffling players. "
             "Time-zone labels in the tee strings are not trusted as absolute timestamps; only equality within an event-round is used. "
             "Multi-course exclusions prevent simultaneous groups at different courses being merged. Non-three-player, partial and missing-key groups are dropped.", "",
             spot_text, "",
             "Ability rank uses each player's mean field-round-centered score from their previous 20 rounds in completed earlier events, requiring at least ten earlier rounds. "
             "Current-event rounds never enter that event's rank. This is an exploratory ordering proxy; field strength and course fit remain confounded. "
             "Strict-win probabilities are normalized by the number of unique-winner groups before comparison with dead-heat shares. "
             "Raw strict-win probabilities would exaggerate the correction.", "",
             f"Recovered {g3['complete_actual_triples_before_ability_filter']:,} complete tee-group triples; "
             f"{g3['groups']:,} triples across {g3['events']} events have eligible prior-ability ranks. "
             f"Tie for low: **{g3['tie_for_low_rate']:.2%}** ({g3['two_way_low_ties']} two-way; {g3['three_way_ties']} three-way).", "",
             f"2025 attrition: {primary_attrition['round_records']:,} player-round records, "
             f"{primary_attrition['g3_missing_time_or_start_hole']} missing usable time/start-hole keys; "
             f"{primary_attrition['g3_source_groups_size_3']:,} three-player source groups, of which "
             f"{primary_attrition['g3_triples_incomplete_scores']} have incomplete scores. "
             f"The ability filter then removes {primary_attrition['g3_triples_insufficient_prior_rounds']:,} groups with insufficient earlier rounds "
             f"and {primary_attrition['g3_triples_tied_prior_ability']} with tied prior-ability ranks. "
             "Two-player and singleton groups are outside G3; their counts are retained in JSON.", "",
             "| Prior ability rank | Normalized strict win | Dead-heat effective probability | Correction (percentage points) | Event bootstrap 95% interval |",
             "| --- | ---: | ---: | ---: | --- |"]
    for i, rank in enumerate(("Best", "Middle", "Worst")):
        ci = g3["event_bootstrap_95_correction_percentage_points"][i]
        lines.append(f"| {rank} | {g3['normalized_strict_win_probabilities_best_middle_worst'][i]:.3%} | "
                     f"{g3['dead_heat_effective_probabilities_best_middle_worst'][i]:.3%} | "
                     f"{g3['correction_percentage_points_best_middle_worst'][i]:+.3f} | [{ci[0]:+.3f}, {ci[1]:+.3f}] |")
    lines += ["", f"Pooled >1-point correction gate: **{'passes' if g3['passes_pooled_correction_gate'] else 'does not pass'}**. "
              f"Sample gate (300 triples / 5 events): {'passes' if g3['passes_sample_gate'] else 'does not pass'}. "
              "Year, round and pre-event skill-gap splits are exploratory diagnostics in JSON; a sparse subgroup maximum is not a surviving mechanism by itself.", "",
              "## Observed round-score spread", "",
              f"{sd['complete_player_rounds']:,} complete player-rounds in {sd['course_round_cells']} course-round cells: "
              f"pooled within-course-round SD **{sd['pooled_within_course_round_sd']:.3f} strokes**; "
              f"median cell SD {sd['median_course_round_sd']:.3f}. "
              f"After subtracting the prior-ability proxy, residual SD is {sd['prior_ability_adjusted_residual_sd']:.3f} "
              f"over {sd['prior_ability_adjusted_rounds']:,} rounds. "
              "These describe observed dispersion. They do not isolate intrinsic player spread: noisy ability, weather/waves, course fit and weekend survival remain. "
              "The baseline three-stroke scale is plausible; fitting a distribution kernel cannot itself establish a book error.", "",
              "## G2: recent withdrawal and after-start withdrawal incidence", "",
              "An observed completed hole proves a player started. A WD with zero recorded holes has unknown timing, since a withdrawal can occur after one stroke before finishing a hole. "
              "Those WDs are never labeled pre-start. Their subsequent 90-day starts are censored in the primary comparison. "
              "First 90 calendar days of archive starts are also censored. Prior exposure uses only an earlier event's completed date and an observed after-start WD.", "",
              "| Prior 90-day history | Observed starts | After-start WDs | Rate | Wilson 95% interval |",
              "| --- | ---: | ---: | ---: | --- |"]
    if not g2["data_complete"] or not exp["starts"] or not base["starts"]:
        lines = lines[:-2] + ["**Pending: historical final-status coverage is incomplete. No G2 effect conclusion is available.**", "",
                              "The scoreboard supports G3; G2 also needs every retained event's leaderboard HTML status rows. "
                              "Missing labels are excluded, not assumed non-withdrawals. "
                              "Run `python3 tools/explore_golf_sport.py --fetch --acquire-only` to acquire missing public pages; "
                              "then `python3 tools/explore_golf_sport.py` to replay both screens. "
                              "Raw inputs stay ignored under `data/raw/golf-sport/`; the "
                              "[JSON report](golf-sport-screen-2026-09-14.json) contains G3 diagnostics and partial G2 coverage.", ""]
        REPORT.with_suffix(".md").write_text("\n".join(lines))
        return
    for label, stats in (("Observed after-start WD", exp), ("No observed after-start WD", base)):
        ci = stats["wilson_95_interval"]
        lines.append(f"| {label} | {stats['starts']:,} | {stats['after_start_withdrawals']} | {stats['rate']:.2%} | [{ci[0]:.2%}, {ci[1]:.2%}] |")
    lines += ["", f"Difference: **{g2['rate_difference_percentage_points']:+.2f} percentage points**; "
              f"relative risk {g2['relative_risk']:.2f}×. "
              f"Conditional-rate gate (≥3% and above baseline): **{'passes' if g2['passes_rate_gate'] else 'does not pass'}**. "
              f"Sample gate (100 exposed starts, 10 exposed WDs, 5 events): **{'passes' if g2['passes_sample_gate'] else 'does not pass'}**.", "",
              f"**G2 decision: {g2['decision'].replace('_', ' ')}.** "
              f"There are {exp['after_start_withdrawals']} exposed withdrawals against the declared minimum of ten.", "",
              f"WD timing across included 2024–2025 events: {json.dumps(g2['wd_timing_counts'], sort_keys=True)}. "
              f"{g2['prior_unknown_timing_excluded']} started player-events were censored because of a prior WD of unknown timing.", "",
              *[f"- {item}" for item in g2["limitations"]], "",
              f"Rate-difference 95% bootstrap intervals (percentage points): event-cluster [{g2['event_bootstrap_95_rate_difference_percentage_points'][0]:+.3f}, {g2['event_bootstrap_95_rate_difference_percentage_points'][1]:+.3f}]; "
              f"player-cluster [{g2['player_bootstrap_95_rate_difference_percentage_points'][0]:+.3f}, {g2['player_bootstrap_95_rate_difference_percentage_points'][1]:+.3f}]. "
              "These are separate one-way clustering checks, not a two-way cluster confidence interval. "
              "Binomial Wilson intervals in the table are descriptive and do not account for repeat players. "
              "The fall split is calendar-only; age, injury-news and actual status-point effects remain untested. "
              "Current Ontario house rules must govern settlement: the old plan's three-hole/generic more-holes shortcut is not used here.", "",
              "## Reproduce and next step", "",
              "`python3 tools/explore_golf_sport.py` replays cached inputs. "
              "`python3 tools/explore_golf_sport.py --fetch --acquire-only` acquires only missing public inputs at one request per second, stopping on denial. "
              "Raw inputs and intermediate groups/rounds/withdrawals remain under ignored `data/raw/golf-sport/`. "
              "The [JSON report](golf-sport-screen-2026-09-14.json) records inputs, hashes, exclusions, dispersion and diagnostic splits. "
              "The declared pooled G3 mechanism fails its effect gate and is parked; exploratory subgroup maxima do not revive it. "
              "G2 needs adequate withdrawal counts and timestamped matchup availability before any book-side conclusion.", ""]
    REPORT.with_suffix(".md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--acquire-only", action="store_true")
    parser.add_argument("--fetch-history-only", action="store_true", help="Bank calendar years 2015–2025 and write an inventory; do not run a screen")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    if args.fetch_history_only:
        acquire_history()
        return
    if args.fetch:
        for year in YEARS:
            fetch(f"scoreboard-{year}.json", f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={year}")
    all_events = events()
    if args.fetch:
        for event in all_events:
            if not exclusion(event):
                fetch(f"leaderboard-{event['id']}.html", f"https://www.espn.com/golf/leaderboard/_/tournamentId/{event['id']}")
    if args.acquire_only:
        print("Acquisition complete; no outcome comparison run.")
        return
    result = screen(all_events)
    write_report(result)
    print(json.dumps({"g3": result["g3"], "g2": result["g2"], "dispersion": result["dispersion"]}, indent=2))


if __name__ == "__main__":
    main()
