#!/usr/bin/env python3
"""Replay the predeclared G11 eight-edition first-round course screen, offline.

See reports/golf-rotation-declaration-2026-09-14.md. No fitted model, odds,
aliases, alternative course selection, or outcome-directed thresholds.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean
import unicodedata

from explore_golf_weekend import complete_score, iso_date

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = (
    ("R2023004", "401465516", "004", "104"),
    ("R2024004", "401580332", "004", "104"),
    ("R2025004", "401703492", "004", "104"),
    ("R2023005", "401465517", "205", "005"),
    ("R2024005", "401580333", "205", "005"),
    ("R2025005", "401703493", "205", "005"),
    ("R2024493", "401693943", "776", "889"),
    ("R2025493", "401738559", "776", "889"),
)
HISTORY_EXCLUSIONS = (
    "american express", "farmers insurance", "pebble beach", "rsm classic",
    "zurich classic", "presidents cup", "ryder cup", "barracuda",
    "tour championship", "q-school", "showdown", "hero world challenge",
    "match play", "match-play", "grant thornton", "the match",
)


def normalized_name(value: str) -> str:
    """Case/diacritics/punctuation only; no aliases or fuzzy similarity."""
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold()
                   if c.isalnum())


def read_json(path: Path, sources: list) -> dict:
    raw = path.read_bytes()
    sources.append({"path": str(path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(raw).hexdigest()})
    return json.loads(raw)


def prior_abilities(events: list[dict], target_ids: set[str]) -> tuple[dict, dict]:
    histories = defaultdict(list)
    priors, exclusions = {}, []
    counts = Counter()
    for e in sorted(events, key=lambda v: (v.get("date", ""), v["id"])):
        if not e.get("date") or not e.get("endDate") or not e.get("name"):
            exclusions.append({"id": e["id"], "reason": "missing event metadata"})
            continue
        start, end = iso_date(e["date"]), iso_date(e["endDate"])
        if len(e.get("competitions", [])) != 1:
            exclusions.append({"id": e["id"], "reason": "not one competition"})
            continue
        players = e["competitions"][0].get("competitors", [])
        if e["id"] in target_ids:
            for p in players:
                prior = sorted((x for x in histories[p["id"]] if x[0] < start),
                               key=lambda x: (x[0], x[1], x[2]))[-20:]
                priors[(e["id"], p["id"])] = {
                    "prior_rounds": len(prior),
                    "prior_ability": mean(x[3] for x in prior) if len(prior) >= 10 else None,
                    "latest_prior_end": prior[-1][0].isoformat() if prior else None,
                }
        reason = next((s for s in HISTORY_EXCLUSIONS if s in e["name"].lower()), None)
        if not e.get("status", {}).get("type", {}).get("completed"):
            reason = "event not completed"
        if reason:
            exclusions.append({"id": e["id"], "name": e["name"], "reason": reason})
            continue
        scores = {}
        for p in players:
            if p.get("type") != "athlete":
                continue
            if p["id"] in scores:
                raise ValueError(f"duplicate historical player {e['id']} {p['id']}")
            rs = {}
            for r in p.get("linescores", []):
                if r.get("period") not in range(1, 5):
                    continue
                score = complete_score(r)
                if score is None:
                    counts["incomplete_or_inconsistent_history_rounds"] += 1
                    continue
                if r["period"] in rs:
                    raise ValueError("duplicate historical player round")
                rs[r["period"]] = score
            scores[p["id"]] = rs
        round_means = {r: mean(rs[r] for rs in scores.values() if r in rs)
                       for r in range(1, 5) if any(r in rs for rs in scores.values())}
        if not round_means:
            exclusions.append({"id": e["id"], "name": e["name"],
                               "reason": "no complete observed stroke-play rounds"})
            continue
        counts["included_history_events"] += 1
        for pid, rs in scores.items():
            for rnd, score in rs.items():
                histories[pid].append((end, e["id"], rnd, score - round_means[rnd]))
                counts["included_history_rounds"] += 1
    return priors, {"counts": dict(counts), "excluded_events": exclusions}


def assignments(payload: dict) -> tuple[dict, dict]:
    rounds = [r for r in payload.get("rounds", []) if r.get("roundInt") == 1]
    if len(rounds) != 1:
        raise ValueError("missing or ambiguous official round one")
    players, by_name = {}, defaultdict(list)
    for group in rounds[0].get("groups", []):
        for p in group.get("players", []):
            if p["id"] in players:
                raise ValueError(f"duplicate official round assignment {p['id']}")
            row = {"pga_player_id": p["id"], "pga_name": p["displayName"],
                   "course_id": group.get("courseId"), "group_number": group.get("groupNumber"),
                   "tee_time_epoch_ms": group.get("teeTime"), "start_tee": group.get("startTee")}
            players[p["id"]] = row
            by_name[normalized_name(p["displayName"])].append(row)
    return players, by_name


def course_pars(data: dict, ident: str) -> dict:
    value = data["data"]["courseStats"]
    if value["tournamentId"] != ident:
        raise ValueError("course metadata belongs to another tournament")
    pars = {}
    for c in value["courses"]:
        if c["tournamentId"] != ident or c["courseId"] in pars:
            raise ValueError("conflicting official course identity")
        rows = [r for r in c["roundHoleStats"] if r["roundNum"] == 1]
        if len(rows) != 1:
            continue
        holes = [h for h in rows[0]["holeStats"] if h.get("courseHoleNum") in range(1, 19)]
        if len(holes) != 18 or {h["courseHoleNum"] for h in holes} != set(range(1, 19)):
            continue
        hole_pars = [int(h["parValue"]) for h in holes]
        if any(p not in (3, 4, 5, 6) for p in hole_pars):
            raise ValueError("invalid official hole par")
        if sum(hole_pars) != c["par"]:
            raise ValueError("official round-one hole pars disagree with course par")
        pars[c["courseId"]] = {"name": c["courseName"], "par": c["par"]}
    return pars


def build_rows(edition: tuple, event: dict, tee: dict, pars: dict, priors: dict) -> tuple[list, dict]:
    ident, eid, harder, easier = edition
    official, name_index = assignments(tee)
    counts = Counter(official_r1_players=len(official))
    attrition, rows, joined_pga = [], [], set()
    event_names = Counter(normalized_name(p["athlete"]["displayName"])
                          for p in event["competitions"][0]["competitors"])
    for p in event["competitions"][0]["competitors"]:
        counts["espn_players"] += 1
        name = p["athlete"]["displayName"]
        key = normalized_name(name)
        matches = name_index.get(key, [])
        reason = None
        if len(matches) != 1 or event_names[key] != 1:
            reason = "ambiguous_name_join" if len(matches) > 1 or event_names[key] > 1 else "unmatched_name"
        if reason:
            counts[reason] += 1
            attrition.append({"espn_player_id": p["id"], "name": name, "reason": reason})
            continue
        assignment = matches[0]
        if assignment["pga_player_id"] in joined_pga:
            raise ValueError("two ESPN players joined to one PGA player")
        joined_pga.add(assignment["pga_player_id"])
        counts["unique_name_join"] += 1
        course = assignment["course_id"]
        if course not in (harder, easier):
            reason = "outside_declared_course_pair"
        elif course not in pars:
            reason = "unknown_verified_course_par"
        r1 = [r for r in p.get("linescores", []) if r.get("period") == 1]
        score = complete_score(r1[0]) if len(r1) == 1 else None
        prior = priors.get((eid, p["id"]))
        if not reason and score is None:
            reason = "missing_complete_r1"
        if not reason and (not prior or prior["prior_ability"] is None):
            reason = "insufficient_prior_rounds"
        if reason:
            counts[reason] += 1
            attrition.append({"espn_player_id": p["id"], "name": name,
                              "course_id": course, "reason": reason})
            continue
        ability = prior["prior_ability"]
        counts["eligible_before_paired_bins"] += 1
        rows.append({"event_id": eid, "pga_tournament_id": ident, "event_name": event["name"],
                     "event_start": event["date"], "espn_player_id": p["id"], "espn_name": name,
                     **assignment, **prior, "course_par": pars[course]["par"],
                     "course_side": "harder" if course == harder else "easier",
                     "gross_score": score, "score_to_par": score - pars[course]["par"],
                     "ability_bin": math.floor(ability), "gross_residual": score - ability,
                     "relative_residual": score - pars[course]["par"] - ability})
    unmatched_official = [p for pid, p in official.items() if pid not in joined_pga]
    counts["official_not_joined_to_espn"] = len(unmatched_official)
    return rows, {"counts": dict(counts), "excluded_espn_rows": attrition,
                  "official_not_joined_to_espn": unmatched_official}


def compare(rows: list[dict]) -> tuple[dict, list]:
    events, eligible = [], []
    for ident, eid, harder, easier in EDITIONS:
        rr = [r for r in rows if r["event_id"] == eid]
        bins = []
        for b in sorted({r["ability_bin"] for r in rr}):
            hard = [r for r in rr if r["ability_bin"] == b and r["course_side"] == "harder"]
            easy = [r for r in rr if r["ability_bin"] == b and r["course_side"] == "easier"]
            if not hard or not easy:
                continue
            eligible.extend(hard + easy)
            bins.append({"ability_bin": b, "harder_n": len(hard), "easier_n": len(easy),
                         "weight": len(hard) * len(easy) / (len(hard) + len(easy)),
                         "relative_gap": mean(r["relative_residual"] for r in hard) - mean(r["relative_residual"] for r in easy),
                         "gross_gap": mean(r["gross_residual"] for r in hard) - mean(r["gross_residual"] for r in easy)})
        weight = sum(b["weight"] for b in bins)
        if not weight:
            continue
        events.append({"pga_tournament_id": ident, "event_id": eid, "event_name": rr[0]["event_name"],
                       "harder_course": harder, "easier_course": easier,
                       "eligible_before_paired_bins": len(rr),
                       "paired_player_events": sum(b["harder_n"] + b["easier_n"] for b in bins),
                       "weight": weight, "ability_bins": bins,
                       **{k: sum(b["weight"] * b[k] for b in bins) / weight for k in ("relative_gap", "gross_gap")}})
    total = sum(e["weight"] for e in events)
    pooled = {k: sum(e["weight"] * e[k] for e in events) / total if total else None
              for k in ("relative_gap", "gross_gap")}
    unique_players = len({r["espn_player_id"] for r in eligible})
    sample_pass = unique_players >= 200 and len(events) >= 6
    rng = random.Random(20260914)
    draws = []
    if events:
        for _ in range(5000):
            sample = rng.choices(events, k=len(events))
            draws.append(sum(e["weight"] * e["relative_gap"] for e in sample) / sum(e["weight"] for e in sample))
    draws.sort()
    intervals = [draws[124], draws[4874]] if draws else None
    return {"events": events, "pooled": pooled, "unique_paired_players": unique_players,
            "paired_player_events": len(eligible), "paired_editions": len(events),
            "relative_gap_event_bootstrap_95": intervals,
            "sample_gate_pass": sample_pass,
            "effect_gate_pass": pooled["relative_gap"] is not None and pooled["relative_gap"] >= .5,
            "status": "unresolved: sample below gate" if not sample_pass else
                      "sport-side effect: investigate prices" if pooled["relative_gap"] >= .5 else
                      "sport-side dead at fixed pooled screen"}, eligible


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/golf-rotation-screen-2026-09-14")
    args = parser.parse_args()
    sources, events, malformed_events = [], [], []
    raw_dir = ROOT / "data/raw/golf-rotation"
    declaration_path = ROOT / "reports/golf-rotation-declaration-2026-09-14.md"
    sources.append({"path": str(declaration_path.relative_to(ROOT)),
                    "sha256": hashlib.sha256(declaration_path.read_bytes()).hexdigest()})
    metadata = read_json(raw_dir / "tournaments.json", sources)
    metadata_by_id = {t["id"]: t for t in metadata["data"]["tournaments"]}
    for year in range(2022, 2026):
        data = read_json(ROOT / f"data/raw/golf-sport/scoreboard-{year}.json", sources)
        for index, event in enumerate(data["events"]):
            if not event.get("id"):
                malformed_events.append({"source_year": year, "source_index": index,
                                         "reason": "missing event ID", "keys": sorted(event)})
            else:
                events.append(event)
    by_id = {e["id"]: e for e in events}
    if len(by_id) != len(events):
        raise ValueError("duplicate event ID in annual inputs")
    priors, history_attrition = prior_abilities(events, {e[1] for e in EDITIONS})
    history_attrition["malformed_source_events"] = malformed_events
    rows, attrition, course_metadata = [], {}, {}
    for edition in EDITIONS:
        ident, eid, harder, easier = edition
        event = by_id[eid]
        official_event = metadata_by_id[ident]
        if event["name"] != official_event["tournamentName"] or str(iso_date(event["date"]).year) != official_event["seasonYear"]:
            raise ValueError("cross-source tournament name or year mismatch")
        if {harder, easier} - {c["id"] for c in official_event["courses"]}:
            raise ValueError("declared course missing from official event")
        tee = read_json(raw_dir / f"{ident}-tee-decoded.json", sources)["data"]["teeTimesCompressedV2"]["payload"]
        wire = read_json(raw_dir / f"{ident}-tee.json", sources)["data"]["teeTimesCompressedV2"]
        if json.loads(gzip.decompress(base64.b64decode(wire["payload"], validate=True))) != tee:
            raise ValueError("decoded tee cache differs from publisher wire response")
        if tee["id"] != ident:
            raise ValueError("tee payload identity mismatch")
        pars = course_pars(read_json(raw_dir / f"{ident}-course-par.json", sources), ident)
        course_metadata[ident] = pars
        rr, attrition[ident] = build_rows(edition, event, tee, pars, priors)
        rows.extend(rr)
    results, eligible = compare(rows)
    rows_bytes = (json.dumps(rows, indent=2) + "\n").encode()
    row_path = raw_dir / "screen-rotation-rows.json"
    row_path.write_bytes(rows_bytes)
    result = {"card": "G11", "scope": "exploratory; eight predeclared editions; first rounds; no prices",
              "declaration": "reports/golf-rotation-declaration-2026-09-14.md",
              "sources": sources, "course_metadata": course_metadata, "history_attrition": history_attrition,
              "target_attrition": attrition, "results": results,
              "derived_rows": {"path": str(row_path.relative_to(ROOT)), "sha256": hashlib.sha256(rows_bytes).hexdigest(),
                               "count_before_paired_bins": len(rows), "count_after_paired_bins": len(eligible)},
              "fanduel_price_test": None}
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# G11 course rotation screen — September 14, 2026", "",
             f"**{results['status']}.** No FanDuel prices were tested.", "",
             f"The signed, ability-adjusted harder-minus-easier first-round contrast is **{results['pooled']['relative_gap']:+.3f} strokes relative to par**, across {results['paired_player_events']} player-events, {results['unique_paired_players']} unique players and {results['paired_editions']} editions. The declared effect gate is +0.5 strokes; the sample gate is 200 unique players and six editions.", "",
             f"Event-bootstrap 95% interval: [{results['relative_gap_event_bootstrap_95'][0]:+.3f}, {results['relative_gap_event_bootstrap_95'][1]:+.3f}] strokes. This is an exploratory interval across eight editions of only three recurring tournaments; it does not account for all repeat-player or shared-venue dependence.", "",
             "| Edition | Course contrast | Paired player-events | Relative-to-par gap | Gross-score gap |",
             "| --- | --- | ---: | ---: | ---: |"]
    for e in results["events"]:
        courses = course_metadata[e["pga_tournament_id"]]
        hard, easy = courses[e["harder_course"]], courses[e["easier_course"]]
        lines.append(f"| {e['event_name']} {e['pga_tournament_id'][1:5]} | {e['harder_course']} (par {hard['par']}) − {e['easier_course']} (par {easy['par']}) | {e['paired_player_events']} | {e['relative_gap']:+.3f} | {e['gross_gap']:+.3f} |")
    counts = Counter()
    for value in attrition.values():
        counts.update(value["counts"])
    lines += ["", "## Identity and attrition", "",
              "Official PGA TOUR round-one group records supply course ID, player ID, group number, start tee and timestamp. CourseStats supplies edition-specific par, checked against 18 first-round hole pars. ESPN supplies first-round gross strokes checked against all 18 hole scores; prior ability remains keyed by ESPN player ID.", "",
              "Cross-source joins require a unique full name after case, accents and punctuation are normalized. No fuzzy matching, nickname substitution or surname-only match is used. Historical fetched-now assignments do not prove their original pre-round publication time.", "",
              f"Across eight events: {counts['espn_players']} ESPN competitors; {counts['unique_name_join']} unique PGA name joins; {counts['unmatched_name']} unmatched and {counts['ambiguous_name_join']} ambiguous ESPN names; {counts['outside_declared_course_pair']} outside the fixed course pairs; {counts['missing_complete_r1']} without a verified complete R1; {counts['insufficient_prior_rounds']} with inadequate prior history; {counts['unknown_verified_course_par']} with unknown par. {len(rows)} player-events remain before paired ability bins; {len(rows)-len(eligible)} then lack an opposite-course comparison within their fixed ability bin. Official players not joined to ESPN: {counts['official_not_joined_to_espn']}.", "",
              "2023 Pebble's Monterey Peninsula course is excluded as declared. R2023493 is November 2022; calendar 2023 RSM was not substituted after the cohort was fixed. The JSON records each excluded row and all per-bin denominators.", "",
              "## Method and interpretation", "",
              "The [pre-score declaration](golf-rotation-declaration-2026-09-14.md) fixes the cohort, course direction, one-stroke prior-ability bins, pooled weighting, thresholds and exclusions. Ability is the average of at most 20 completed rounds (at least ten) in earlier single-course events ending before this event, each centered on its field-round score. 2022 supplies warmup. Current-event scores never enter current-event ability. Within every edition/ability bin with both courses, compare score minus course par minus prior ability and weight by n_harder × n_easier / (n_harder + n_easier).", "",
              "Assignment groups can differ in player strength, start times, weather and other unmeasured factors. Prior ability is noisy and field strength varies. This screen estimates an observational course-assignment contrast, not a causal course-design effect or a profitable forecast. No probability kernel or FanDuel price has been fitted.", "",
              "Implementation audit: the first run additionally required four observed historical rounds. That was stricter than the declaration. The rule was removed, and the three affected source events were all editions of the exhibition `The Match`, excluded explicitly under the already declared exhibition rule. No legitimate shortened event was affected; the result, 963 pre-bin rows, 950 paired rows and all prior abilities are unchanged. The initial +1.709 estimate and corrected estimate are the same; this correction is not a fresh comparison.", "",
              "Different pars matter: Seaside is par 70 and Plantation is par 72. Their relative-to-par contrast exceeds their gross-strokes contrast by exactly two. The pooled relative contrast must never be inserted into a gross-score matchup. Any later price comparison must preserve each named course pair, the displayed market convention and actual offer times.", "",
              "A surviving sport effect requires a separate book-side test: pre-round FanDuel cross-course derivative markets, both sides, price clocks and settlement terms; compare offered mean shifts with the measured course-pair offsets. At least 70% reflection, or absent relevant markets, kills that book-side claim. This report establishes no betting edge.", "",
              "Reproduce: `state/runtime/research-venv/bin/python tools/explore_golf_rotation.py`. Raw responses and player-level rows remain local under ignored `data/raw/`. Full hashes, attrition, course pars and per-bin contrasts are in [the JSON report](golf-rotation-screen-2026-09-14.json).", "",
              "Sources: [PGA TOUR public GraphQL](https://orchestrator.pgatour.com/graphql), [public course-stat query schema](https://github.com/WalrusQuant/pgatouR/blob/main/inst/graphql/CourseStats.graphql), [ESPN 2022](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2022), [2023](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2023), [2024](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2024), [2025](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025)."]
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in results.items() if k != "events"}, indent=2))


if __name__ == "__main__":
    main()
