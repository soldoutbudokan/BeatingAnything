#!/usr/bin/env python3
"""Cheap sport-side state screens, with no fitted model or bookmaker claims.

Run from the repository root with Python 3.12:
    python tools/explore_tennis_states.py --download

Source data: Tennis Abstract Match Charting Project, CC BY-NC-SA 4.0.
This script's derived data reports retain that attribution and license.
"""

# %% Source and parameters, set before inspecting the conditional results.
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sys
import urllib.request

COMMIT = "2c59eef194967e688b69e73df344184a06322cd8"
SOURCE = "https://github.com/JeffSackmann/tennis_MatchChartingProject"
BASE = f"https://raw.githubusercontent.com/JeffSackmann/tennis_MatchChartingProject/{COMMIT}/"
RAW = Path("data/raw/tennis-state-exploration")
FILES = ["README.md", "data_dictionary.txt", "charting-m-matches.csv", "charting-m-points-2020s.csv"]
REPORT = Path("reports/tennis-state-exploration")


def acquire(download: bool) -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    sources = []
    for name in FILES:
        path = RAW / name
        if not path.exists():
            if not download:
                raise SystemExit(f"Missing {path}; rerun with --download")
            with urllib.request.urlopen(BASE + name, timeout=60) as response:
                path.write_bytes(response.read())
        data = path.read_bytes()
        sources.append({"file": str(path), "url": BASE + name,
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return sources


# %% Reconstruct completed games from pre-point scores and point winners.
def regular_score(wins: list[int], server: int) -> str:
    a, b = wins[server - 1], wins[2 - server]
    if a >= 3 and b >= 3:
        return "40-40" if a == b else "AD-40" if a > b else "40-AD"
    labels = ["0", "15", "30", "40"]
    return f"{labels[min(a, 3)]}-{labels[min(b, 3)]}"


def complete(wins: list[int], minimum: int) -> bool:
    return max(wins) >= minimum and abs(wins[0] - wins[1]) >= 2


def parse_match(match_id: str, rows: list[dict], meta: dict) -> list[dict]:
    best_of = int(meta["Best of"])
    if best_of not in (3, 5):
        raise ValueError("unsupported_best_of")
    rows.sort(key=lambda row: int(row["Pt"]))
    if [int(row["Pt"]) for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("partial_or_noncontiguous_points")
    groups: list[list[dict]] = []
    for row in rows:
        key = tuple(int(row[field]) for field in ("Set1", "Set2", "Gm1", "Gm2"))
        if not groups or key != groups[-1][0]["_key"]:
            groups.append([])
        row["_key"] = key
        groups[-1].append(row)
    expected = (0, 0, 0, 0)
    games = []
    for index, points in enumerate(groups):
        first = points[0]
        state = first["_key"]
        if state != expected:
            raise ValueError("game_or_set_score_transition")
        sets = list(state[:2])
        score = list(state[2:])
        servers = {int(point["Svr"]) for point in points}
        if not servers <= {1, 2}:
            raise ValueError("invalid_server")
        tiebreak = len(servers) == 2
        if tiebreak and (score[0] != score[1] or score[0] < 6):
            raise ValueError("unsupported_match_tiebreak_or_scoring")
        wins = [0, 0]
        for offset, point in enumerate(points):
            server, winner = int(point["Svr"]), int(point["PtWinner"])
            if winner not in (1, 2):
                raise ValueError("invalid_point_winner")
            predicted = (f"{wins[server - 1]}-{wins[2 - server]}" if tiebreak
                         else regular_score(wins, server))
            if point["Pts"].strip().upper() != predicted:
                raise ValueError("point_score_mismatch")
            if not tiebreak and complete(wins, 4):
                raise ValueError("points_after_game_end")
            wins[winner - 1] += 1
        if not complete(wins, 7 if tiebreak else 4):
            raise ValueError("incomplete_final_game")
        winner = 1 if wins[0] > wins[1] else 2
        server = int(first["Svr"])
        game = {"match": match_id, "index": index, "set": sum(sets) + 1,
                "sets": sets.copy(), "score": score.copy(), "server": server,
                "winner": winner, "tiebreak": tiebreak, "points": len(points),
                "first_point": int(first["Pt"]), "last_point": int(points[-1]["Pt"]),
                "best_of": best_of, "surface": meta["Surface"] or "Unknown",
                "date": meta["Date"], "player": meta[f"Player {server}"],
                "tournament": meta["Tournament"], "round": meta["Round"]}
        score[winner - 1] += 1
        if tiebreak or (max(score) >= 6 and abs(score[0] - score[1]) >= 2):
            sets[winner - 1] += 1
            score = [0, 0]
        if max(sets) >= best_of // 2 + 1 and index != len(groups) - 1:
            raise ValueError("points_after_match_end")
        expected = tuple(sets + score)
        games.append(game)
    if max(expected[:2]) != best_of // 2 + 1:
        raise ValueError("incomplete_match")
    # Net breaks are counted inside each set, before the current service game.
    net: dict[int, list[int]] = collections.defaultdict(lambda: [0, 0])
    for game in games:
        server, set_number = game["server"], game["set"]
        game["net_breaks_down"] = net[set_number][server - 1]
        if not game["tiebreak"] and game["winner"] != server:
            net[set_number][server - 1] += 1
            net[set_number][2 - server] -= 1
    return games


def load_games() -> tuple[list[dict], dict]:
    with (RAW / "charting-m-matches.csv").open(encoding="utf-8-sig") as handle:
        metadata = {row["match_id"]: row for row in csv.DictReader(handle)}
    by_match = collections.defaultdict(list)
    with (RAW / FILES[-1]).open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            by_match[row["match_id"]].append(row)
    games, exclusions, excluded_points = [], collections.Counter(), 0
    accepted_points = 0
    for match_id, rows in by_match.items():
        try:
            parsed = parse_match(match_id, rows, metadata[match_id])
        except (ValueError, KeyError, IndexError) as error:
            exclusions[str(error)] += 1
            excluded_points += len(rows)
            continue
        games.extend(parsed)
        accepted_points += len(rows)
    coverage = {"input_matches": len(by_match), "input_points": accepted_points + excluded_points,
                "accepted_matches": len({g["match"] for g in games}),
                "accepted_points": accepted_points, "excluded_points": excluded_points,
                "excluded_matches_by_reason": dict(exclusions), "completed_games": len(games),
                "regular_games": sum(not g["tiebreak"] for g in games),
                "date_min": min(g["date"] for g in games), "date_max": max(g["date"] for g in games),
                "matches_by_surface": dict(collections.Counter(
                    metadata[mid]["Surface"] for mid in {g["match"] for g in games})),
                "matches_by_best_of": dict(collections.Counter(
                    metadata[mid]["Best of"] for mid in {g["match"] for g in games})),
                "matches_with_challenger_name_marker": sum(
                    "_CH" in mid or "challenger" in metadata[mid]["Tournament"].lower()
                    for mid in {g["match"] for g in games})}
    return games, coverage


# %% Prior-date-only hold-rate proxy, not a direct serve-speed classification.
def add_prior_hold_proxy(games: list[dict]) -> None:
    history = collections.defaultdict(lambda: [0, 0])
    days = collections.defaultdict(list)
    for game in games:
        if not game["tiebreak"]:
            days[game["date"]].append(game)
    for date in sorted(days):
        for game in days[date]:
            held, n = history[game["player"]]
            game["prior_hold_n"] = n
            game["prior_hold_rate"] = held / n if n else None
            game["prior_high_hold"] = n >= 100 and held / n >= .85
        for game in days[date]:
            history[game["player"]][0] += int(game["winner"] == game["server"])
            history[game["player"]][1] += 1


# %% Exposures are observable before the measured outcome game starts.
def select(games: list[dict]) -> dict[str, tuple[list[dict], list[dict]]]:
    cohorts = {name: ([], []) for name in (
        "double_break_concession", "long_service_game_carryover", "post_tiebreak_loser",
        "post_tiebreak_winner", "fourth_set_concession")}
    by_match = collections.defaultdict(list)
    for game in games:
        by_match[game["match"]].append(game)
    for match_games in by_match.values():
        seen = set()
        for i, game in enumerate(match_games):
            if game["tiebreak"]:
                if game["points"] >= 16:
                    group = 0
                elif 7 <= game["points"] <= 12:
                    group = 1
                else:
                    continue
                for role, player in (("loser", 3 - game["winner"]), ("winner", game["winner"])):
                    following = next((g for g in match_games[i + 1:] if g["set"] == game["set"] + 1
                                      and not g["tiebreak"] and g["server"] == player), None)
                    if following:
                        cohorts[f"post_tiebreak_{role}"][group].append(following)
                continue
            server = game["server"]
            key = (game["set"], server)
            if game["best_of"] == 5 and game["set"] == 4 and game["net_breaks_down"] >= 2:
                group = 0 if game["sets"][server - 1] == 2 else 1
                tag = ("fourth", group, *key)
                if tag not in seen:
                    cohorts["fourth_set_concession"][group].append(game)
                    seen.add(tag)
            nondeciding = game["sets"][2 - server] < game["best_of"] // 2
            if nondeciding and game["net_breaks_down"] >= 1:
                group = 0 if game["net_breaks_down"] >= 2 else 1
                tag = ("double", group, *key)
                if tag not in seen:
                    cohorts["double_break_concession"][group].append(game)
                    seen.add(tag)
            if i < 2:
                continue
            previous, intervening = match_games[i - 2], match_games[i - 1]
            if (previous["tiebreak"] or intervening["tiebreak"]
                    or previous["set"] != game["set"]
                    or previous["server"] != server
                    or intervening["server"] == server
                    or previous["winner"] != server or intervening["points"] > 8):
                continue
            if previous["points"] >= 16:
                group = 0
            elif 4 <= previous["points"] <= 8:
                group = 1
            else:
                continue
            tag = ("long", group, *key)
            if tag not in seen:
                cohorts["long_service_game_carryover"][group].append(game)
                seen.add(tag)
    return cohorts


# %% Simple conditional probabilities and within-player/opponent comparisons.
def broken(game: dict) -> int:
    return int(game["winner"] != game["server"])


def rate(rows: list[dict]) -> dict:
    n = len(rows)
    wins = sum(broken(row) for row in rows)
    return {"games": n, "breaks": wins, "break_rate": wins / n if n else None,
            "matches": len({row["match"] for row in rows}),
            "players": len({row["player"] for row in rows}),
            "starting_server_game_score_counts": dict(collections.Counter(
                f"{row['score'][row['server'] - 1]}-{row['score'][2 - row['server']]}"
                for row in rows))}


def contrast(exposed: list[tuple[str, float]], control: list[tuple[str, float]]) -> dict:
    if not exposed or not control:
        return {"difference": None, "descriptive_95pct_interval": None,
                "exposed_games": len(exposed), "control_games": len(control)}
    me = sum(v for _, v in exposed) / len(exposed)
    mc = sum(v for _, v in control) / len(control)
    influence = collections.defaultdict(float)
    for mid, value in exposed:
        influence[mid] += (value - me) / len(exposed)
    for mid, value in control:
        influence[mid] -= (value - mc) / len(control)
    clusters = len(influence)
    se = math.sqrt(sum(v * v for v in influence.values()) * clusters / (clusters - 1)) if clusters > 1 else None
    diff = me - mc
    return {"difference": diff, "descriptive_95pct_interval":
            [diff - 1.96 * se, diff + 1.96 * se] if se is not None else None,
            "exposed_games": len(exposed), "control_games": len(control), "match_clusters": clusters}


def summarize(exposed: list[dict], control: list[dict], games: list[dict]) -> dict:
    selected = {(g["match"], g["index"]) for g in exposed + control}
    others = collections.defaultdict(list)
    for game in games:
        if not game["tiebreak"] and (game["match"], game["index"]) not in selected:
            others[(game["match"], game["server"])].append(broken(game))
    residuals = [[], []]
    for bucket, group in zip(residuals, (exposed, control)):
        for game in group:
            baseline = others[(game["match"], game["server"])]
            if len(baseline) >= 3:
                bucket.append((game["match"], broken(game) - sum(baseline) / len(baseline)))
    paired = collections.defaultdict(lambda: [[], []])
    for group_id, group in enumerate((exposed, control)):
        for game in group:
            paired[(game["match"], game["server"])][group_id].append(broken(game))
    differences = [(mid, sum(e) / len(e) - sum(c) / len(c))
                   for (mid, _), (e, c) in paired.items() if e and c]
    paired_result = contrast(differences, [(mid, 0.) for mid, _ in differences])
    paired_result["player_match_pairs"] = len(differences)
    other_sets = collections.defaultdict(list)
    for game in games:
        if not game["tiebreak"]:
            other_sets[(game["match"], game["server"])].append(game)
    other_set_summary = {}
    for label, group in (("exposed", exposed), ("control", control)):
        outcomes, baselines = [], []
        for game in group:
            baseline = [broken(g) for g in other_sets[(game["match"], game["server"])]
                        if g["set"] != game["set"]]
            if len(baseline) >= 3:
                outcomes.append((game["match"], broken(game)))
                baselines.append((game["match"], sum(baseline) / len(baseline)))
        other_set_summary[label] = {
            "games": len(outcomes),
            "break_rate": sum(v for _, v in outcomes) / len(outcomes) if outcomes else None,
            "other_sets_break_rate": sum(v for _, v in baselines) / len(baselines) if baselines else None,
            "excess_vs_other_sets": contrast(outcomes, baselines)}
    return {"exposed": rate(exposed), "control": rate(control),
            "raw_contrast": contrast([(g["match"], broken(g)) for g in exposed],
                                     [(g["match"], broken(g)) for g in control]),
            "within_match_residual_contrast": contrast(*residuals),
            "paired_same_player_match_contrast": paired_result,
            "other_sets_same_player_match_baseline": other_set_summary,
            "by_surface": {surface: {"exposed": rate([g for g in exposed if g["surface"] == surface]),
                                      "control": rate([g for g in control if g["surface"] == surface])}
                           for surface in sorted({g["surface"] for g in exposed + control})},
            "by_best_of": {str(bo): {"exposed": rate([g for g in exposed if g["best_of"] == bo]),
                                     "control": rate([g for g in control if g["best_of"] == bo])}
                           for bo in (3, 5)}}


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def points(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:+.2f} pp"


def interpret(screens: dict) -> str:
    """Retain the initial screen interpretation on reproduction of pinned inputs."""
    double = screens["double_break_concession"]
    long_game = screens["long_service_game_carryover"]
    tb = screens["post_tiebreak_loser"]
    proxy = screens["double_break_prior_high_hold_proxy"]
    fourth = screens["fourth_set_concession"]
    fourth_decision = (
        "Fourth-set concession remains unresolved: "
        f"{fourth['exposed']['breaks']}/{fourth['exposed']['games']} exposed games "
        f"versus {fourth['control']['breaks']}/{fourth['control']['games']} controls "
        f"({points(fourth['raw_contrast']['difference'])}). The sample is below the card's "
        "50-exposure minimum. This does not confirm or kill the incentive mechanism.\n\n"
    )
    interval = long_game['within_match_residual_contrast']['descriptive_95pct_interval']
    return (
        f"Deprioritize the broad double-break screen: its {points(double['raw_contrast']['difference'])} "
        "raw difference misses the card's prewritten +5 pp / 100-exposure screen. The exposed break rate "
        f"is {pct(double['exposed']['break_rate'])}, versus "
        f"{pct(double['other_sets_same_player_match_baseline']['exposed']['other_sets_break_rate'])} "
        "for those same players in other sets of the same matches. This does not show extra concession "
        "beyond the selected players' poor serving in these matches. The specific big-server claim remains "
        f"unresolved: the prior high-hold proxy supplies only {proxy['exposed']['games']} exposures.\n\n"
        "Keep long-service-game carryover as an unconfirmed lead, not a sport-side confirmation. "
        f"The raw difference is {points(long_game['raw_contrast']['difference'])} across "
        f"{long_game['exposed']['games']} exposures, exceeding the prewritten +3 pp / 100-exposure screen. "
        "But the within-match residual contrast falls to "
        f"{points(long_game['within_match_residual_contrast']['difference'])} "
        f"(descriptive 95% interval {100 * interval[0]:+.2f} to {100 * interval[1]:+.2f} pp), "
        "and exposed players' other-set break rate is "
        f"{pct(long_game['other_sets_same_player_match_baseline']['exposed']['other_sets_break_rate'])}, "
        f"close to the observed {pct(long_game['exposed']['break_rate'])}. "
        "Player/opponent and match-form selection explain much of the raw association. "
        "It may justify a cheap independently licensed replication and collecting the matching live "
        "next-service-game prices; it does not justify a model fit or promotion.\n\n"
        "Kill the specified extended-tiebreak-loser direction in this exploratory sample: "
        f"{points(tb['raw_contrast']['difference'])} across {tb['exposed']['games']} exposures "
        "is opposite to the card's prewritten +3 pp prediction. The winner diagnostic points the other "
        "way but is uncertain and was not the target hypothesis; do not turn it into a confirmed reversed "
        "strategy.\n\n" + fourth_decision +
        "None of these cards is sport-side confirmed, no FanDuel pricing mismatch has been "
        "measured, and no betting edge has been demonstrated."
    )


def markdown(report: dict) -> str:
    cov = report["coverage"]
    lines = ["# Tennis state exploration", "",
             "Exploratory sport-side evidence only. No FanDuel prices, returns, model fit, alert or wager.", "",
             f"Source: [Tennis Abstract Match Charting Project]({SOURCE}/tree/{COMMIT}), pinned `{COMMIT}`. "
             "Jeff Sackmann and volunteer contributors; source data and derived data reports are "
             "[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). "
             "This is noncommercial research; this source is not a licensed commercial betting feed.", "",
             "## Sample", "",
             f"Men's 2020s file: {cov['accepted_matches']:,} accepted complete matches, "
             f"{cov['regular_games']:,} regular service games, {cov['date_min']}–{cov['date_max']}. "
             f"Excluded {cov['input_matches'] - cov['accepted_matches']:,} of {cov['input_matches']:,} matches "
             f"and {cov['excluded_points']:,} of {cov['input_points']:,} points. "
             "This is a curated, nonrandom charting sample, dominated by top-level men's matches. "
             "It is not an ATP census or Challenger sample. Tournament names are not a verified tour-level field. "
             f"Only {cov['matches_with_challenger_name_marker']} accepted match IDs/tournament names contain "
             "an explicit Challenger marker.", "",
             "Incomplete, noncontiguous and inconsistent matches are excluded as whole matches. "
             "This can omit retirement and fatigue tails. Pre-point score reconstruction checks game boundaries "
             "and winners; it does not independently verify volunteer charting.", "",
             "Exclusions: `" + json.dumps(cov["excluded_matches_by_reason"], sort_keys=True) + "`.", "",
             "## Results", "",
             "| Screen | Exposed breaks / games | Control breaks / games | Raw difference | Within-match residual difference |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for name, result in report["screens"].items():
        e, c = result["exposed"], result["control"]
        lines.append(f"| {name.replace('_', ' ')} | {e['breaks']}/{e['games']} ({pct(e['break_rate'])}) "
                     f"| {c['breaks']}/{c['games']} ({pct(c['break_rate'])}) "
                     f"| {points(result['raw_contrast']['difference'])} "
                     f"| {points(result['within_match_residual_contrast']['difference'])} |")
    lines.extend(["", "Definitions:", "",
        "- Double break: first completed service game per player-set beginning at least two net breaks down, "
        "versus first beginning one net break down. Opponent must not already be one set from winning the match.",
        "- Long service game: next same-set service game following a held game of at least 16 points, "
        "versus a held game of 4–8 points; the intervening return game has at most eight points. "
        "Use the first opportunity per player-set in each exposure/control group.",
        "- Tiebreak: loser's first regular service game in the next set after a tiebreak of at least 16 points, "
        "versus tiebreaks of 7–12 points. The winner comparison is a diagnostic.",
        "- Fourth set: first service game at least two net breaks down in set four of a best-of-five match "
        "while leading 2–1 in sets, versus the same state while trailing 1–2. The prewritten card requires "
        "50 exposed cases and +5 pp before keeping the hypothesis on raw effect size.",
        "- Prior high hold proxy: at least 100 completed charted service games on earlier dates and at least "
        "85% holds, across surfaces. Same-day observations are withheld. This is a sparse prior hold-rate "
        "proxy, not a direct big-server classification.", "",
        "Within-match residual difference compares each outcome with that player's other completed service "
        "games against the same opponent in that match; all selected exposure/control outcomes are removed "
        "from the baseline, and at least three other games are required. It then contrasts exposed and control "
        "residuals. A further diagnostic retained in JSON restricts comparison to players with both types of opportunity in the same "
        "match, averages each type within player-match, and weights those pairs equally. These retrospective "
        "baselines partly address player/opponent strength; they are not deployable forecasts and do not isolate "
        "concession or fatigue from within-match form, selection or score-state effects. In particular, selecting "
        "two breaks down conditions on earlier poor serving.", "",
        "The JSON also compares each group's outcome rate with the same player's service games in other "
        "sets of that match, requiring at least three such games. This is an additional descriptive strength "
        "check. The paired one-break comparison is especially selection-sensitive: reaching two breaks down "
        "often requires losing the earlier one-break-down control game. It must not be read causally.", "",
        "The JSON includes sample splits and descriptive 95% normal intervals with match-clustered standard "
        "errors. These are exploratory intervals without multiplicity correction; no untouched holdout or "
        "confirmatory inference is claimed. The 2020s file was the single initial screen sample, with no "
        "post-result threshold tuning or model fitting.", "", "## Decision", "",
        report["decision"], "", "## Book-side data needed", "",
        "A retained FanDuel two-sided next-game hold/break quote at the trigger, both quote and receipt "
        "timestamps, event/player identity, exact pre-game score and server, plus an independent timestamped "
        "game-state stream. Also collect the paired reference quote and settlement rules. Set correct-score "
        "and totals markets need their own quotes and outcomes; this screen does not verify those markets. "
        "No actual FanDuel stale-price claim follows from these sport-side results.", "",
        "## Reproduce", "", "```bash", "python tools/explore_tennis_states.py --download", "```", "",
        "Raw CSVs remain ignored; pinned URLs, sizes and SHA-256 hashes are in the adjacent JSON. "
        "The original `tennis_pointbypoint` repository returned GitHub 404 during source discovery; "
        "this screen uses the available Match Charting Project instead.", ""])
    return "\n".join(lines)


# %% One cheap exploratory run. No provenance/CI/verifier framework.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use the project's Python 3.12 research runtime.")
    cards = list(Path("docs/hypotheses").glob("*.md"))
    if sum(path.name != "README.md" for path in cards) < 30:
        raise SystemExit("NEXT-STEPS.md requires 30 hypothesis cards before testing.")
    sources = acquire(args.download)
    games, coverage = load_games()
    add_prior_hold_proxy(games)
    cohorts = select(games)
    screens = {name: summarize(exposed, control, games)
               for name, (exposed, control) in cohorts.items()}
    exposed, control = cohorts["double_break_concession"]
    screens["double_break_prior_high_hold_proxy"] = summarize(
        [g for g in exposed if g["prior_high_hold"]],
        [g for g in control if g["prior_high_hold"]], games)
    report = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "phase": "exploration", "source_commit": COMMIT,
              "license": "CC BY-NC-SA 4.0; attribution to Tennis Abstract Match Charting Project",
              "sources": sources, "coverage": coverage, "screens": screens,
              "decision": interpret(screens)}
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    REPORT.with_suffix(".md").write_text(markdown(report))
    print(json.dumps({"coverage": coverage, "screens": {
        name: {k: value for k, value in result.items() if not k.startswith("by_")}
        for name, result in screens.items()}}, indent=2))


if __name__ == "__main__":
    main()
