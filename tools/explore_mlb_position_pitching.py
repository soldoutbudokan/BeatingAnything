"""Exploratory 2025 position-player pitching screen; no fitted betting model.

Run: python tools/explore_mlb_position_pitching.py
Raw official responses are cached under the existing ignored data/raw tree.
"""
from __future__ import annotations

# %% Fixed scope and acquisition
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEASON = 2025  # Chosen before computing run comparisons; do not tune on outcomes.
STAMP = "2026-09-13"
API = "https://statsapi.mlb.com/api/v1"
POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH"}
RULE_URL = "https://www.mlb.com/news/mlb-two-way-player-rules"


def cached(root, name, url):
    path = root / name
    if not path.exists():
        for attempt in range(3):
            try:
                with urlopen(url, timeout=45) as response:
                    raw = response.read()
                json.loads(raw)
                path.write_bytes(raw)
                break
            except Exception:
                if attempt == 2:
                    raise
    return json.loads(path.read_text())


def eligible(inning, margin):
    # Regulation only: excludes automatic/inherited runners in extra innings.
    return inning <= 9 and (margin <= -8 or (inning == 9 and margin >= 10))


def acquire(root, workers):
    root.mkdir(parents=True, exist_ok=True)
    index = cached(root, f"pitcher-index-{SEASON}.json",
                   f"{API}/stats?stats=season&group=pitching&season={SEASON}"
                   "&gameType=R&sportIds=1&playerPool=ALL&limit=2000")
    splits = index["stats"][0]["splits"]
    # Use an independently supplied position, never low velocity / bad results.
    identities = {s["player"]["id"]: {"name": s["player"]["fullName"],
                  "position": s.get("position", {}).get("abbreviation")}
                  for s in splits}
    ids = sorted(pid for pid, p in identities.items() if p["position"] in POSITIONS)
    logs = {}
    for offset in range(0, len(ids), 40):
        data = cached(root, f"people-{SEASON}-{offset}.json",
                      f"{API}/people?personIds={','.join(map(str, ids[offset:offset+40]))}"
                      f"&hydrate=stats(type=gameLog,group=pitching,season={SEASON})")
        for person in data["people"]:
            for group in person.get("stats", []):
                if group.get("group", {}).get("displayName") != "pitching":
                    continue
                for s in group.get("splits", []):
                    if s.get("gameType") == "R":
                        logs[(s["game"]["gamePk"], person["id"])] = s["stat"]
    schedule = cached(root, f"schedule-{SEASON}.json",
                      f"{API}/schedule?sportId=1&season={SEASON}&gameType=R&hydrate=linescore")
    games = {g["gamePk"]: g for day in schedule["dates"] for g in day["games"]
             if g["status"]["detailedState"] == "Final" and "rescheduleDate" not in g
             and not any(k in g for k in ("resumeDate", "resumedFrom", "resumeGameDate"))}
    selected = set()
    for pk, game in games.items():
        home = away = 0
        for inning in game["linescore"]["innings"]:
            for side in ("away", "home"):
                if "runs" not in inning[side]:
                    continue
                margin = home-away if side == "away" else away-home
                if eligible(inning["num"], margin):
                    selected.add(pk)
                if side == "away":
                    away += inning[side]["runs"]
                else:
                    home += inning[side]["runs"]
    # Also retain appearances that began mid-inning or outside clean-start states.
    selected.update(pk for pk, _ in logs if pk in games)
    def fetch(pk):
        cached(root, f"feed-{pk}.json",
               f"https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch, sorted(selected)))
    return identities, logs, games, selected


# %% Inning-start comparison and separate inherited-runner records
def extract(root, identities, logs, games, selected):
    innings, appearances, exclusions = [], [], Counter()
    for pk in sorted(selected):
        feed = json.loads((root / f"feed-{pk}.json").read_text())
        plays = feed["liveData"]["plays"]["allPlays"]
        players = feed["gameData"]["players"]
        def kind(pid):
            # Agreement of season-index and game-feed identity fields required.
            a = identities.get(pid, {}).get("position")
            b = players.get(f"ID{pid}", {}).get("primaryPosition", {}).get("abbreviation")
            if a in POSITIONS and b in POSITIONS:
                return "position"
            if a == b == "P":
                return "pitcher"
            return "excluded_identity"
        grouped = defaultdict(list)
        starters = {}
        before = {}
        home = away = 0
        for play in plays:
            key = play["about"]["inning"], play["about"]["halfInning"]
            before[play["about"]["atBatIndex"]] = (home, away)
            starters.setdefault(key[1], play["matchup"]["pitcher"]["id"])
            grouped[key].append(play)
            home, away = play["result"]["homeScore"], play["result"]["awayScore"]
        for (inning, half), group in grouped.items():
            first, last = group[0], group[-1]
            home, away = before[first["about"]["atBatIndex"]]
            margin = home-away if half == "top" else away-home
            if not eligible(inning, margin):
                continue
            pid = first["matchup"]["pitcher"]["id"]
            category = kind(pid)
            if category == "excluded_identity":
                exclusions[category] += 1
                continue
            if pid == starters[half]:
                exclusions["starter_at_inning_start"] += 1
                continue
            if last["count"]["outs"] != 3:
                exclusions["incomplete_half_inning"] += 1
                continue
            score_key = "awayScore" if half == "top" else "homeScore"
            runs = last["result"][score_key] - (away if half == "top" else home)
            inning_pitchers = sorted({p["matchup"]["pitcher"]["id"] for p in group})
            innings.append({"game_pk": pk, "date": games[pk]["officialDate"],
                            "inning": inning, "half": half, "defensive_margin": margin,
                            "pitcher_id": pid, "pitcher_name": identities[pid]["name"],
                            "kind": category, "runs": runs,
                            "inherited_runners_at_inning_start": 0,
                            "pitchers_used": inning_pitchers,
                            "control_later_used_position_player": category == "pitcher" and
                            any(kind(p) == "position" for p in inning_pitchers),
                            "first_at_bat_time": first["about"].get("startTime")})
        seen = set()
        for i, play in enumerate(plays):
            pid = play["matchup"]["pitcher"]["id"]
            if kind(pid) != "position" or pid in seen:
                continue
            seen.add(pid)
            key = play["about"]["inning"], play["about"]["halfInning"]
            prior = plays[i-1] if i and (plays[i-1]["about"]["inning"],
                                       plays[i-1]["about"]["halfInning"]) == key else None
            bases = {b: prior["matchup"][b]["id"] for b in
                     ("postOnFirst", "postOnSecond", "postOnThird")
                     if prior and b in prior["matchup"]}
            events = play["playEvents"]
            changes = [e for e in events if e.get("isSubstitution") and
                       e.get("player", {}).get("id") == pid and
                       e.get("position", {}).get("code") == "1"]
            pitches = [e for e in events if e.get("isPitch")]
            substitution = changes[-1] if changes else {}
            first_pitch = next((e for e in pitches if
                                e["index"] > substitution.get("index", -1)), {})
            st = logs.get((pk, pid), {})
            home, away = before[play["about"]["atBatIndex"]]
            appearances.append({"game_pk": pk, "date": games[pk]["officialDate"],
                                "pitcher_id": pid, "pitcher_name": identities[pid]["name"],
                                "primary_position": identities[pid]["position"],
                                "inning": key[0], "half": key[1],
                                "defensive_margin": home-away if key[1] == "top" else away-home,
                                "outs_at_entry": prior["count"]["outs"] if prior else 0,
                                "bases_before_entry_pa": bases,
                                "entered_mid_pa": any(e["index"] < substitution.get("index", -1)
                                                      for e in pitches),
                                "substitution_event_type": substitution.get("details", {}).get("eventType"),
                                "substitution_start_time": substitution.get("startTime"),
                                "substitution_end_time": substitution.get("endTime"),
                                "first_pitch_start_time": first_pitch.get("startTime"),
                                "official_outs": st.get("outs"),
                                "official_runs_charged": st.get("runs"),
                                "official_inherited_runners": st.get("inheritedRunners"),
                                "official_inherited_runners_scored": st.get("inheritedRunnersScored"),
                                "source_url": f"https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"})
    return innings, appearances, dict(exclusions)


# %% Fixed exact-state weights; descriptive game-cluster uncertainty
def comparison(innings):
    exposed = [r for r in innings if r["kind"] == "position"]
    controls = [r for r in innings if r["kind"] == "pitcher"]
    key = lambda r: (r["inning"], r["half"], r["defensive_margin"])
    cells = defaultdict(lambda: {"position": [], "pitcher": []})
    for row in innings:
        cells[key(row)][row["kind"]].append(row)
    matched, weighted_controls, strata = [], [], []
    for k, cell in sorted(cells.items()):
        e, c = cell["position"], cell["pitcher"]
        if not e or not c:
            continue
        matched.extend(e)
        weight = len(e)/len(c)
        weighted_controls.extend((r, weight) for r in c)
        strata.append({"inning": k[0], "half": k[1], "defensive_margin": k[2],
                       "exposed_n": len(e), "control_n": len(c),
                       "exposed_mean": float(np.mean([r["runs"] for r in e])),
                       "control_mean": float(np.mean([r["runs"] for r in c]))})
    def mean(rows):
        return float(np.mean([r["runs"] for r in rows])) if rows else None
    result = {"all_clean_exposed_n": len(exposed), "all_ordinary_reliever_n": len(controls),
              "all_exposed_mean_runs": mean(exposed), "all_control_mean_runs": mean(controls),
              "matched_exposed_n": len(matched), "matched_control_n": len(weighted_controls),
              "unmatched_exposed_n": len(exposed)-len(matched), "exact_strata": strata,
              "controls_later_using_position_player": sum(r["control_later_used_position_player"]
                                                          for r in controls)}
    if not matched:
        return result
    denominator = len(matched)
    e_mean = mean(matched)
    c_mean = sum(r["runs"]*w for r, w in weighted_controls)/denominator
    groups = defaultdict(lambda: np.zeros(4))
    for r in matched:
        groups[r["game_pk"]] += [r["runs"], 1, 0, 0]
    for r, w in weighted_controls:
        groups[r["game_pk"]] += [0, 0, r["runs"]*w, w]
    matrix = np.array(list(groups.values()))
    rng = np.random.default_rng(20260913)
    weights = rng.multinomial(len(matrix), np.full(len(matrix), 1/len(matrix)), size=2000)
    totals = weights @ matrix
    diffs = totals[:, 0]/totals[:, 1] - totals[:, 2]/totals[:, 3]
    result.update({"matched_exposed_mean_runs": e_mean, "matched_control_mean_runs": c_mean,
                   "matched_difference_runs": e_mean-c_mean,
                   "game_cluster_bootstrap_95pct": np.quantile(diffs, [.025, .975]).tolist(),
                   "matched_games": len(groups),
                   "matched_exposed_at_least_one_run": sum(r["runs"] >= 1 for r in matched)/denominator,
                   "matched_weighted_control_at_least_one_run":
                   sum(w*(r["runs"] >= 1) for r, w in weighted_controls)/denominator})
    return result


# %% Reports: the sport-side screen is not evidence of a stale FanDuel price.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache", type=Path, default=ROOT/"data/raw/mlb-position-pitching")
    args = parser.parse_args()
    identities, logs, games, selected = acquire(args.cache, args.workers)
    innings, appearances, exclusions = extract(args.cache, identities, logs, games, selected)
    summary = comparison(innings)
    clean_controls = [r for r in innings if not r["control_later_used_position_player"]]
    sensitivity = comparison(clean_controls)
    gaps = []
    for row in appearances:
        a, b = row["substitution_start_time"], row["first_pitch_start_time"]
        if a and b:
            gaps.append((datetime.fromisoformat(b.replace("Z", "+00:00")) -
                         datetime.fromisoformat(a.replace("Z", "+00:00"))).total_seconds())
    official = {field: sum(r[field] or 0 for r in appearances) for field in
                ("official_outs", "official_runs_charged", "official_inherited_runners",
                 "official_inherited_runners_scored")}
    manifest = [{"file": p.name, "bytes": p.stat().st_size,
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in sorted(args.cache.glob("*.json"))]
    difference = summary.get("matched_difference_runs", 0)
    enough = summary["matched_exposed_n"] >= 100
    verdict = ("sport-side dead" if difference < .5 else "sport-side confirmed") if enough else "idea"
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "season": SEASON,
              "status": verdict, "fixed_kill_threshold_runs": .5, "minimum_exposed_innings": 100,
              "eligible_completed_games": len(games), "downloaded_game_feeds": len(selected),
              "position_player_identities": sum(p["position"] in POSITIONS for p in identities.values()),
              "two_way_players_excluded": [p for p in identities.values() if p["position"] == "TWP"],
              "summary": summary, "sensitivity_excluding_later_position_players": sensitivity,
              "exclusions": exclusions, "appearance_count": len(appearances),
              "official_appearance_totals": official,
              "appearance_log_count_in_selected_games": sum(pk in selected for pk, _ in logs),
              "mid_inning_entries": sum(bool(r["outs_at_entry"] or r["bases_before_entry_pa"])
                                         for r in appearances),
              "inherited_runner_entries": sum((r["official_inherited_runners"] or 0) > 0
                                               for r in appearances),
              "timestamp_pairs": len(gaps),
              "substitution_to_first_pitch_seconds": {"minimum": min(gaps) if gaps else None,
                 "median": float(np.median(gaps)) if gaps else None,
                 "maximum": max(gaps) if gaps else None,
                 "at_most_one_second": sum(g <= 1 for g in gaps)},
              "rule_source": RULE_URL, "source_manifest": manifest,
              "innings": innings, "position_player_appearances": appearances}
    out = ROOT/"reports"/f"mlb-position-pitching-{STAMP}"
    out.with_suffix(".json").write_text(json.dumps(report, indent=2)+"\n")
    ci = summary.get("game_cluster_bootstrap_95pct", [0, 0])
    text = f"""# MLB position-player pitching: 2025 sport-side screen

**Result: {verdict}.** The exact-state comparison has {summary['matched_exposed_n']} exposed innings and {summary['matched_control_n']} ordinary-reliever controls. Position-player innings scored {summary.get('matched_exposed_mean_runs', 0):.3f} runs versus {summary.get('matched_control_mean_runs', 0):.3f} in controls weighted to the exposed inning/margin distribution: **{difference:+.3f} runs per inning** (descriptive game-cluster bootstrap 95% interval {ci[0]:+.3f} to {ci[1]:+.3f}). The card's fixed screen is 100 exposed innings and 0.5 additional runs. {'The minimum sample is reached.' if enough else 'The exact-matched sample is below the minimum; the card remains unresolved.'} No FanDuel pricing edge is established.

## Scope and comparison

The complete 2025 regular season was chosen before computing the run comparisons. Official schedule inning scores enumerate every regulation inning starting with a defensive deficit of at least eight, or a ninth-inning lead of at least ten. Only preceding inning scores select states; final margins do not. Suspended/resumed, postponed, and incomplete games are excluded. {len(games)} completed games remain; {len(selected)} full game feeds cover eligible states plus every identified position-player appearance in those games.

Exposure means a position player **starts the inning**. Controls start with ordinary relievers; game starters and two-way players are excluded. Both groups start with zero outs and empty bases. The outcome is all runs in that half-inning, including subsequent pitching changes. Exact matching uses inning number, top/bottom, and signed defensive margin. Each control gets its cell's exposed/control count weight. This avoids comparing blowouts with competitive innings. It does not control batter substitutions, reliever ability, prior bullpen use, or manager selection, so it is descriptive rather than a causal estimate. The 2025 data are now inspected exploration, not an untouched holdout.

| Sample | Innings | Mean runs |
|---|---:|---:|
| All qualifying position-player starts | {summary['all_clean_exposed_n']} | {summary['all_exposed_mean_runs']:.3f} |
| All qualifying ordinary-reliever starts | {summary['all_ordinary_reliever_n']} | {summary['all_control_mean_runs']:.3f} |
| Matched position-player starts | {summary['matched_exposed_n']} | {summary.get('matched_exposed_mean_runs', 0):.3f} |
| Matched controls, exposed-state weights | {summary['matched_control_n']} | {summary.get('matched_control_mean_runs', 0):.3f} |

{summary['unmatched_exposed_n']} exposed innings have no exact control and do not enter the adjusted contrast. {summary['controls_later_using_position_player']} control innings later used a position player; retaining them avoids excluding controls because of an ensuing pitching change. Removing these contaminated controls as a sensitivity yields {sensitivity.get('matched_difference_runs', 0):+.3f} runs with {sensitivity['matched_exposed_n']} matched exposures. The primary probability of at least one run is {summary.get('matched_exposed_at_least_one_run', 0):.1%} versus {summary.get('matched_weighted_control_at_least_one_run', 0):.1%}; this is an empirical rate, not a wager recommendation.

## Identity, inherited runners, and clocks

The season pitching index supplies non-pitcher position fields, checked against each game's `gameData.players.primaryPosition`. Neither low pitch speed nor poor outcomes define a position player. `TWP` excludes Shohei Ohtani. These are retrospective identity fields, not an archived active-roster designation at announcement time.

{len(appearances)} distinct position-player appearances contribute {official['official_outs']/3:.3f} official innings and {official['official_runs_charged']} charged runs. These aggregate rates are not used as the matched result. There are {report['mid_inning_entries']} mid-inning entries and {report['inherited_runner_entries']} appearances with inherited runners: {official['official_inherited_runners']} inherited, {official['official_inherited_runners_scored']} scored. Official charged runs and inherited-runner scoring are retained separately in the JSON; inherited runs are not incorrectly charged to the incoming pitcher. The clean-start comparison excludes those entry states and extra innings.

{len(gaps)} appearances have both a substitution-action timestamp and a first-pitch timestamp. Their recorded start-time gap has median {float(np.median(gaps)) if gaps else 0:.3f} seconds; {sum(g <= 1 for g in gaps)} are at most one second. These retrospective event fields do **not** establish when an announcement became available to a collector or bettor. Full event times, types, IDs, entry outs, and base occupancy are retained for future live alignment.

Eligibility: extra innings; trailing by eight or more; or leading by ten or more in inning nine. See [MLB's April 2026 explanation]({RULE_URL}).

## What advances this card

Capture FanDuel live inning/team totals, prices and suspension status on both sides of an incoming-position-player announcement, together with independently observed game-feed publication times and first pitch. Demonstrate an available stale quote before testing return. No historical feed timestamp here proves that opportunity, and no alert or wagering gate changes.

Reproduce with `python tools/explore_mlb_position_pitching.py`. Raw official responses remain in ignored `data/raw/mlb-position-pitching/`; this report's JSON contains rows and source hashes. Sources are the [official 2025 pitching index]({API}/stats?stats=season&group=pitching&season=2025&gameType=R&sportIds=1&playerPool=ALL&limit=2000), [schedule]({API}/schedule?sportId=1&season=2025&gameType=R&hydrate=linescore), per-player game logs, and per-game feed URLs retained in each appearance row.
"""
    out.with_suffix(".md").write_text(text)
    print(json.dumps({k: v for k, v in report.items() if k not in
                      {"source_manifest", "innings", "position_player_appearances"}}, indent=2))


if __name__ == "__main__":
    main()
