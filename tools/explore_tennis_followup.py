#!/usr/bin/env python3
"""Fixed September 13 tennis follow-up; no fitted model or bookmaker claims.

Reuse the September 12 parser, definitions and summaries. Replicate only the
unresolved long-service-game and fourth-set cards in the pinned men's 2010s
file, then screen the prewritten failed-serve-for-set card in the 2020s file.
Source and derived reports: Tennis Abstract MCP, CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

import explore_tennis_states as initial

POINT_FILES = {"2010s": "charting-m-points-2010s.csv",
               "2020s": "charting-m-points-2020s.csv"}
REPORT = Path("reports/tennis-followup-2026-09-13")


def acquire(download: bool) -> list[dict]:
    sources = initial.acquire(download)
    name = POINT_FILES["2010s"]
    path = initial.RAW / name
    if not path.exists():
        if not download:
            raise SystemExit(f"Missing {path}; rerun with --download")
        with urllib.request.urlopen(initial.BASE + name, timeout=60) as response:
            path.write_bytes(response.read())
    data = path.read_bytes()
    sources.append({"file": str(path), "url": initial.BASE + name,
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return sources


def load_period(period: str) -> tuple[list[dict], dict]:
    # Reuse the original loader unchanged, selecting just its point-input file.
    original_files = initial.FILES
    initial.FILES = original_files[:-1] + [POINT_FILES[period]]
    try:
        games, coverage = initial.load_games()
    finally:
        initial.FILES = original_files
    with (initial.RAW / "charting-m-matches.csv").open(encoding="utf-8-sig") as handle:
        metadata = {row["match_id"]: row for row in csv.DictReader(handle)}
    for game in games:
        game["returner"] = metadata[game["match"]][f"Player {3 - game['server']}"]
    return games, coverage


def failed_serve_for_set(games: list[dict]) -> tuple[list[dict], list[dict]]:
    cohorts: tuple[list[dict], list[dict]] = ([], [])
    by_match = collections.defaultdict(list)
    for game in games:
        by_match[game["match"]].append(game)
    for match_games in by_match.values():
        for previous, target in zip(match_games, match_games[1:]):
            if (target["tiebreak"] or previous["tiebreak"]
                    or target["set"] != previous["set"]
                    or target["score"] != [5, 5]
                    or target["server"] == previous["server"]):
                continue
            server = previous["server"]
            preceding_score = (previous["score"][server - 1], previous["score"][2 - server])
            if preceding_score == (5, 4) and previous["winner"] != server:
                cohorts[0].append(target)
            elif preceding_score == (4, 5) and previous["winner"] == server:
                cohorts[1].append(target)
    return cohorts


def failed_summary(games: list[dict]) -> dict:
    exposed, control = failed_serve_for_set(games)
    result = initial.summarize(exposed, control, games)
    result["by_returner"] = {
        player: {"exposed": initial.rate([g for g in exposed if g["returner"] == player]),
                 "control": initial.rate([g for g in control if g["returner"] == player])}
        for player in sorted({g["returner"] for g in exposed + control})}
    result["returner_counts"] = {
        "exposed": len({g["returner"] for g in exposed}),
        "control": len({g["returner"] for g in control}),
        "both": len({g["returner"] for g in exposed} & {g["returner"] for g in control})}
    return result


def screen_decision(result: dict, minimum: int, threshold: float, lower: bool = False) -> str:
    if result["exposed"]["games"] < minimum:
        return "unresolved: below prewritten exposure minimum"
    difference = result["raw_contrast"]["difference"]
    if difference is None:
        return "unresolved: no control observations"
    passes = difference <= -threshold if lower else difference >= threshold
    return ("raw screen passes; mechanism and pricing remain unconfirmed" if passes else
            "specified direction fails the prewritten raw screen")


def interpretation(screens: dict) -> str:
    long = screens["long_service_game_carryover_2010s"]
    fourth = screens["fourth_set_concession_2010s"]
    failed = screens["failed_serve_for_set_2020s"]
    residual = long["within_match_residual_contrast"]
    ci = residual["descriptive_95pct_interval"]
    return (
        "Long-service carryover remains the surviving unresolved lead. Its earlier-period raw "
        f"difference is {initial.points(long['raw_contrast']['difference'])}, following +5.00 pp in "
        "the September 12 sample. The unchanged within-match residual contrast is "
        f"{initial.points(residual['difference'])} (descriptive 95% interval "
        f"{100 * ci[0]:+.2f} to {100 * ci[1]:+.2f} pp). The exposed players' other-set break rate "
        f"is {initial.pct(long['other_sets_same_player_match_baseline']['exposed']['other_sets_break_rate'])}, "
        f"versus {initial.pct(long['exposed']['break_rate'])} in target games. Replication of the raw "
        "association warrants seeking matched game prices and a prospective strength-aware comparison; "
        "it does not establish fatigue or mispricing.\n\n"
        f"Fourth-set concession supplies only {fourth['exposed']['games']} additional exposures "
        "(42 across both screened files), still below the original 50-case minimum even if counted "
        "together. The earlier-period direction is opposite, with wide uncertainty. Leave unresolved "
        "and stop source expansion for this batch.\n\n"
        "Kill the prewritten failed-close direction in this exploratory sample: the raw break-rate "
        f"difference is {initial.points(failed['raw_contrast']['difference'])} across "
        f"{failed['exposed']['games']} exposures, opposite to the predicted reduction. The "
        f"within-match residual contrast is {initial.points(failed['within_match_residual_contrast']['difference'])}; "
        "the sign change highlights strength and score-path selection, not a confirmed psychological "
        "effect. Do not promote the reverse direction.\n\n"
        "No card is sport-side confirmed. Read each period separately; no pooled effect threshold or "
        "subgroup rescue is used. Mechanism replication and market mispricing remain separate requirements."
    )


def markdown(report: dict) -> str:
    lines = ["# Tennis fixed follow-up — September 13, 2026", "",
        "Exploratory sport-side evidence only. No model fit, bookmaker prices, returns or betting edge.", "",
        f"Source: [Tennis Abstract Match Charting Project]({initial.SOURCE}/tree/{initial.COMMIT}), "
        f"pinned `{initial.COMMIT}`. Jeff Sackmann and volunteer contributors; source and derived data "
        "reports are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). "
        "This is noncommercial research, not a licensed commercial betting feed.", "",
        "## Fixed scope and coverage", "",
        "The men's 2010s file repeats only the unresolved long-service-game and fourth-set definitions "
        "from September 12, with the same parser, thresholds and summaries. The men's 2020s file screens "
        "the already written rank-5 failed-serve-for-set card. No thresholds, directions or subgroup "
        "filters were tuned after results. The 2010s and 2020s accepted match IDs do not overlap. "
        "This earlier-period follow-up was chosen after the first screen; it is not an untouched "
        "holdout, independent source, independent license or confirmation.", "",
        "| File | Accepted / input matches | Regular service games | Accepted date range |", 
        "| --- | ---: | ---: | --- |"]
    for period, cov in report["coverage"].items():
        lines.append(f"| Men's {period} | {cov['accepted_matches']:,}/{cov['input_matches']:,} "
                     f"| {cov['regular_games']:,} | {cov['date_min']}–{cov['date_max']} |")
    lines.extend(["", "Incomplete, noncontiguous or score-inconsistent matches are excluded as whole "
        "matches. That can omit fatigue and retirement tails. This curated, nonrandom sample favors "
        "top-level men's matches; it is not a tour census. Tour level is not a verified source field. "
        "Exact exclusions, surface/best-of splits and all returner strata for rank 5 are retained in JSON.", "",
        "## Results", "",
        "| Fixed screen | Exposed breaks / games | Control breaks / games | Raw difference | Within-match residual difference |",
        "| --- | ---: | ---: | ---: | ---: |"])
    for name, result in report["screens"].items():
        e, c = result["exposed"], result["control"]
        lines.append(f"| {name.replace('_', ' ')} | {e['breaks']}/{e['games']} "
                     f"({initial.pct(e['break_rate'])}) | {c['breaks']}/{c['games']} "
                     f"({initial.pct(c['break_rate'])}) | {initial.points(result['raw_contrast']['difference'])} "
                     f"| {initial.points(result['within_match_residual_contrast']['difference'])} |")
    lines.extend(["", "Definitions:", "",
        "- Long service game: first next same-set service game per player-set/group after a held game "
        "of at least 16 points versus 4–8 points, with the intervening return game at most eight points. "
        "Prewritten screen: at least 100 exposures and at least +3 percentage points.",
        "- Fourth set: first service game at least two net breaks down in set four of best-of-five, "
        "leading 2–1 versus trailing 1–2 in sets. Prewritten screen: at least 50 exposures and at least +5 points.",
        "- Failed serve for set: opponent's service game at 5–5 immediately after the returner was "
        "broken serving at 5–4, versus after the returner held serving at 4–5. All outcomes are the "
        "target server being broken. Prewritten screen: at least 100 exposures and at least 3 points "
        "lower break probability after the failed close.", "",
        "The within-match residual contrasts subtract the same server's break rate in other regular "
        "games against the same opponent, excluding all selected target games and requiring at least "
        "three baseline games. The same player-match comparison also fixes the returner. These "
        "retrospective baselines use outcomes that can occur later; they are descriptive strength "
        "checks, not real-time predictors or causal adjustments. Other-set baselines and paired "
        "same-player/match contrasts are retained in JSON. The reported intervals use the unchanged "
        "match-clustered normal approximation; they have no multiplicity correction.", "",
        "## Decisions and limitations", ""])
    for name, decision in report["decisions"].items():
        result = report["screens"][name]
        ci = result["raw_contrast"]["descriptive_95pct_interval"]
        interval = "n/a" if ci is None else f"{100 * ci[0]:+.2f} to {100 * ci[1]:+.2f} pp"
        lines.append(f"- **{name.replace('_', ' ')}:** {decision}. Raw descriptive 95% interval: {interval}.")
    lines.extend(["", report["interpretation"], "",
        "Long games select players/opponents having difficult service games; fourth-set deficits select "
        "earlier poor serving and may reflect injury, form and match dynamics. The failed-close groups "
        "condition on different score paths and opposite preceding outcomes (break versus hold). "
        "Differences in strength, serving order and mean reversion can mimic or hide the proposed "
        "psychological effect. None of these comparisons isolates intent or fatigue.", "",
        "No FanDuel hold/break prices or quote/state timestamps are present. Passing a sport-side "
        "threshold cannot establish mispricing after vig. Any retained mechanism needs separately "
        "timestamped quotes, state, event identity and settlement rules before a betting claim.", "",
        "## Reproduce", "", "```bash", "python tools/explore_tennis_followup.py --download", "```", "",
        "The September 12 script and reports remain unchanged. Raw files stay ignored; pinned URLs, "
        "sizes and SHA-256 hashes are in the adjacent JSON.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use the project's Python 3.12 research runtime.")
    sources = acquire(args.download)
    older, older_coverage = load_period("2010s")
    current, current_coverage = load_period("2020s")
    overlap = {g["match"] for g in older} & {g["match"] for g in current}
    if overlap:
        raise SystemExit(f"Period match IDs unexpectedly overlap: {len(overlap)}")
    cohorts = initial.select(older)
    screens = {f"{name}_2010s": initial.summarize(*cohorts[name], older)
               for name in ("long_service_game_carryover", "fourth_set_concession")}
    screens["failed_serve_for_set_2020s"] = failed_summary(current)
    decisions = {
        "long_service_game_carryover_2010s": screen_decision(screens["long_service_game_carryover_2010s"], 100, .03),
        "fourth_set_concession_2010s": screen_decision(screens["fourth_set_concession_2010s"], 50, .05),
        "failed_serve_for_set_2020s": screen_decision(screens["failed_serve_for_set_2020s"], 100, .03, lower=True)}
    report = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "phase": "exploration",
              "source_commit": initial.COMMIT,
              "license": "CC BY-NC-SA 4.0; attribution to Tennis Abstract Match Charting Project",
              "sources": sources, "coverage": {"2010s": older_coverage, "2020s": current_coverage},
              "overlapping_accepted_match_ids": len(overlap), "screens": screens,
              "decisions": decisions,
              "interpretation": interpretation(screens)}
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    REPORT.with_suffix(".md").write_text(markdown(report))
    print(json.dumps({"coverage": report["coverage"], "decisions": decisions, "screens": {
        name: {k: v for k, v in result.items() if not k.startswith("by_")}
        for name, result in screens.items()}}, indent=2))


if __name__ == "__main__":
    main()
