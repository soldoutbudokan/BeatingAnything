#!/usr/bin/env python3
"""One new tennis mechanism, fixed before its September 13 outcome comparison.

Source/derived data: Tennis Abstract Match Charting Project, CC BY-NC-SA 4.0.
This reuses inspected raw data, not an untouched holdout or bookmaker evidence.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import explore_tennis_states as initial

REPORT = Path("reports/tennis-return-changeover-2026-09-13")
RULES_URL = "https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf"
PROTOCOL = {
    "fixed_before_first_computation_utc": "2026-09-13",
    "source_commit": initial.COMMIT,
    "point_file": "charting-m-points-2020s.csv",
    "long_return_minimum_points": 16,
    "short_return_points": [4, 8],
    "minimum_completed_games_in_set": 2,
    "minimum_long_return_per_arm": 200,
    "minimum_difference_in_differences": 0.03,
    "raw_long_return_difference_must_be_positive": True,
    "observation_selection": "every eligible next service game; no subgroup selection",
    "scheduled_changeover": "odd completed games in current set, excluding first game",
    "excluded": ["tiebreaks", "set transitions", "same-server adjacent games", "first-game side switch"],
}


def select(games: list[dict]) -> dict[str, list[dict]]:
    groups = {key: [] for key in ("long_no_changeover", "long_changeover",
                                  "short_no_changeover", "short_changeover")}
    by_match = collections.defaultdict(list)
    for game in games:
        by_match[game["match"]].append(game)
    for match_games in by_match.values():
        for previous, target in zip(match_games, match_games[1:]):
            if (target["tiebreak"] or previous["tiebreak"]
                    or target["set"] != previous["set"]
                    or target["server"] == previous["server"]
                    or sum(target["score"]) < PROTOCOL["minimum_completed_games_in_set"]):
                continue
            if previous["points"] >= PROTOCOL["long_return_minimum_points"]:
                length = "long"
            elif PROTOCOL["short_return_points"][0] <= previous["points"] <= PROTOCOL["short_return_points"][1]:
                length = "short"
            else:
                continue
            scheduled = sum(target["score"]) % 2 == 1
            row = dict(target)
            row.update(previous_game_points=previous["points"],
                       previous_game_first_point=previous["first_point"],
                       previous_game_last_point=previous["last_point"],
                       previous_return_won=previous["winner"] == target["server"],
                       scheduled_changeover=scheduled)
            key = length + ("_changeover" if scheduled else "_no_changeover")
            groups[key].append(row)
    return groups


def did(groups: dict[str, list[dict]]) -> dict:
    """Four cell means, with a single influence sum per match for uncertainty."""
    signs = {"long_no_changeover": 1, "long_changeover": -1,
             "short_no_changeover": -1, "short_changeover": 1}
    if any(not groups[key] for key in signs):
        return {"difference": None, "descriptive_95pct_interval": None}
    difference = 0.0
    influence = collections.defaultdict(float)
    for key, sign in signs.items():
        rows = groups[key]
        mean = sum(initial.broken(row) for row in rows) / len(rows)
        difference += sign * mean
        for row in rows:
            influence[row["match"]] += sign * (initial.broken(row) - mean) / len(rows)
    clusters = len(influence)
    se = math.sqrt(sum(v * v for v in influence.values()) * clusters / (clusters - 1)) if clusters > 1 else None
    return {"difference": difference, "descriptive_95pct_interval":
            [difference - 1.96 * se, difference + 1.96 * se] if se is not None else None,
            "match_clusters": clusters}


def results(groups: dict[str, list[dict]]) -> dict:
    return {
        "cells": {key: initial.rate(rows) for key, rows in groups.items()},
        "long_return_contrast": initial.contrast(
            [(g["match"], initial.broken(g)) for g in groups["long_no_changeover"]],
            [(g["match"], initial.broken(g)) for g in groups["long_changeover"]]),
        "short_return_contrast": initial.contrast(
            [(g["match"], initial.broken(g)) for g in groups["short_no_changeover"]],
            [(g["match"], initial.broken(g)) for g in groups["short_changeover"]]),
        "difference_in_differences": did(groups),
    }


def decision(result: dict) -> str:
    if any(result["cells"][key]["games"] < PROTOCOL["minimum_long_return_per_arm"]
           for key in ("long_no_changeover", "long_changeover")):
        return "unresolved: fewer than 200 long-return service games in at least one arm"
    raw = result["long_return_contrast"]["difference"]
    interaction = result["difference_in_differences"]["difference"]
    if raw is None or interaction is None:
        return "unresolved: missing comparison cell"
    if raw <= 0 or interaction < PROTOCOL["minimum_difference_in_differences"]:
        return "sport-side dead: fixed direction/effect threshold failed in this sample"
    return "raw sport-side screen passes; actual recovery and bookmaker mechanism remain unconfirmed"


def interval_text(value: dict) -> str:
    interval = value["descriptive_95pct_interval"]
    return "n/a" if interval is None else f"{100 * interval[0]:+.2f} to {100 * interval[1]:+.2f} pp"


def markdown(report: dict) -> str:
    result, cov = report["result"], report["coverage"]
    lines = ["# Tennis recovery after a long return game — September 13, 2026", "",
        f"**Decision: {report['decision']}.** This new conditional screen uses inspected exploratory "
        "data. It does not reopen the completed service-game, tiebreak or concession screens.", "",
        "The proposed mechanism is that returning through a long game leaves a player more vulnerable "
        "on the next serve when the score provides no scheduled changeover. Static next-game pricing "
        "could miss this interaction, but no claim about FanDuel's actual model is verified.", "",
        "## Fixed test and result", "",
        "The card and definitions were written before computing these four cell rates. A long return "
        "game has at least 16 points; a short one has 4–8. Measure the immediately following regular "
        "service game in the same set, with at least two games already completed. Odd completed-game "
        "count means a scheduled changeover; even means none. First-game side switches, tiebreaks "
        "and set transitions are excluded. Every eligible target is included.", "",
        "The fixed gate requires at least 200 long-return observations per arm, a positive raw "
        "no-changeover minus changeover difference, and at least +3 percentage points after subtracting "
        "the same contrast after short return games. Short-return games provide a check on serving-order "
        "and scoreboard selection; they do not make the comparison causal.", "",
        "| Preceding return game | Scheduled recovery | Breaks / next service games | Break rate |",
        "| --- | --- | ---: | ---: |"]
    for key, row in result["cells"].items():
        lines.append(f"| {'>=16 points' if key.startswith('long') else '4–8 points'} | "
                     f"{'No changeover' if '_no_' in key else 'Changeover'} | "
                     f"{row['breaks']}/{row['games']} | {initial.pct(row['break_rate'])} |")
    lines.extend(["", f"- Long-return raw difference: **{initial.points(result['long_return_contrast']['difference'])}** "
        f"(descriptive 95% interval {interval_text(result['long_return_contrast'])}).",
        f"- Short-return difference: **{initial.points(result['short_return_contrast']['difference'])}** "
        f"(descriptive 95% interval {interval_text(result['short_return_contrast'])}).",
        f"- Difference-in-differences: **{initial.points(result['difference_in_differences']['difference'])}** "
        f"(descriptive 95% interval {interval_text(result['difference_in_differences'])}).", "",
        "Uncertainty combines all four cell contributions within each match. These exploratory normal "
        "intervals have no multiplicity correction. All year, surface and preceding-return-result "
        "splits are in JSON; none replaces the fixed whole-sample decision.", "",
        "## Coverage, timing and limitations", "",
        f"The unchanged complete-match parser accepted {cov['accepted_matches']:,}/{cov['input_matches']:,} "
        f"matches and {cov['regular_games']:,} regular service games, dated "
        f"{cov['date_min']}–{cov['date_max']}. Exclusions and source hashes are in JSON. "
        "The sample is curated men's singles, not a tour census or a representative Challenger sample. "
        "Complete-match selection excludes some retirement and interruption tails.", "",
        "[ITF rules 10 and 29](" + RULES_URL + ") establish odd-game changeovers, a normal maximum "
        "of 90 seconds and no rest after a set's first game; set breaks are different. "
        "The data establishes point order and score before the target game. It has no actual "
        "rest-duration measurements or complete record of medical/weather delays. Event-specific "
        "timing exceptions are not separately verified. Consequently, this tests the standard "
        "scheduled-changeover proxy and cannot isolate the physiological effect of measured recovery.", "",
        "Changeover opportunity is tied to score parity and serving order. Player strength, whether "
        "the preceding return game was won, score path, rally intensity, end-of-court conditions and "
        "unrecorded pauses may differ between groups. Point count does not measure elapsed exertion. "
        "A negative result closes this specification, not every possible fatigue mechanism; a positive "
        "subgroup is not a license to reverse or retune the rule.", "",
        "## Book-side requirement and next action", "",
        "No FanDuel paired next-game hold/break quotes were supplied, and no return or pricing edge "
        "was calculated. Quotes would need the same match, score, next server, just-completed point "
        "count, quote clock and independently observed game-state clock. The existing collection "
        "configuration has not verified this specific live-market coverage.", "",
        ("This specification failed its fixed screen. Move to another mechanism; do not expand "
         "this archive or tune a preferred surface to rescue it." if report["decision"].startswith("sport-side dead") else
         "Do not tune this specification. A passing raw screen would still require actual recovery "
         "timing and exact FanDuel market availability before a prospective test."), "",
        "## Source and reproduction", "",
        f"[Tennis Abstract Match Charting Project]({initial.SOURCE}/tree/{initial.COMMIT}), "
        f"pinned `{initial.COMMIT}`. Jeff Sackmann and volunteer contributors; source and these "
        "derived data reports are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). "
        "Noncommercial research only; raw files remain ignored.", "",
        "```bash", "python tools/explore_tennis_return_changeover.py --download", "```", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    sources = initial.acquire(args.download)
    games, coverage = initial.load_games()
    groups = select(games)
    result = results(groups)
    splits = {}
    for name, getter in (("year", lambda g: g["date"][:4]),
                         ("surface", lambda g: g["surface"]),
                         ("preceding_return_won", lambda g: str(g["previous_return_won"]))):
        values = sorted({getter(g) for rows in groups.values() for g in rows})
        splits[name] = {value: results({key: [g for g in rows if getter(g) == value]
                                       for key, rows in groups.items()}) for value in values}
    # A compact identity projection makes the selected state sequence inspectable.
    identity_fields = ("match", "index", "set", "score", "server", "winner", "points",
                       "first_point", "previous_game_first_point", "previous_game_last_point",
                       "previous_game_points", "scheduled_changeover", "previous_return_won")
    projection = {key: [{field: g[field] for field in identity_fields} for g in rows]
                  for key, rows in groups.items()}
    projection_path = Path("data/processed/tennis-return-changeover-observations.json")
    projection_path.parent.mkdir(parents=True, exist_ok=True)
    projection_path.write_text(json.dumps(projection, separators=(",", ":")) + "\n")
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "protocol": PROTOCOL, "rules_source": RULES_URL,
        "sources": sources, "coverage": coverage,
        "result": result, "descriptive_splits_not_new_tests": splits,
        "decision": decision(result),
        "local_observation_projection": {"path": str(projection_path),
            "sha256": hashlib.sha256(projection_path.read_bytes()).hexdigest()},
        "evidence": {"exploratory_inspected_sample": True, "actual_rest_timestamps": False,
                     "paired_fanduel_prices": False, "causal_fatigue_identified": False,
                     "verified_betting_edge": False},
    }
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    REPORT.with_suffix(".md").write_text(markdown(report))
    print(json.dumps({"decision": report["decision"], "result": result}, indent=2))


if __name__ == "__main__":
    main()
