"""Free MLB Stats API acquisition and conservative historical normalization.

The API is an official *retrospective* source, not an archived pregame feed.
Schedule probable pitchers, weather, lineups, and season-to-date records are
deliberately not used as model inputs. Source JSON is cached without alteration.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

API = "https://statsapi.mlb.com/api/v1"
TEAM_IDS = [108,109,110,111,112,113,114,115,116,117,118,119,120,121,
            133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,158]


def _download(url: str, path: Path) -> None:
    if path.exists():
        try:
            json.loads(path.read_text())
            return
        except (ValueError, UnicodeError):
            pass
    for attempt in range(3):
        try:
            with urlopen(url, timeout=120) as response:
                raw = response.read()
            json.loads(raw)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(raw)
            temporary.replace(path)
            return
        except Exception:
            if attempt == 2:
                raise


def download(source_dir: str | Path, years=range(2021, 2026), workers=4) -> dict:
    """Batch pitcher logs, repairing incomplete historical full-season rosters."""
    years = list(years)
    root = Path(source_dir)
    root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for year in years:
        jobs.append((f"{API}/schedule?sportId=1&startDate={year}-01-01"
                     f"&endDate={year}-12-31&gameType=R"
                     "&hydrate=probablePitcher,linescore,venue",
                     root / f"schedule_{year}.json"))
        # Existing roster batches remain auditable but are insufficient alone:
        # MLB omits several historical pitchers from the fullSeason roster.
        for team in TEAM_IDS:
            roster_path = root / f"pitching_{year}_{team}.json"
            if roster_path.exists():
                jobs.append((f"{API}/teams/{team}/roster?rosterType=fullSeason"
                             f"&season={year}&hydrate=person(stats(type=gameLog,"
                             f"group=pitching,season={year}))", roster_path))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda args: _download(*args), jobs))
    index_jobs = [(f"{API}/stats?stats=season&group=pitching&season={year}"
                   "&gameType=R&sportIds=1&playerPool=ALL&limit=2000",
                   root/f"pitcher_index_{year}.json") for year in years]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda args: _download(*args), index_jobs))
    jobs.extend(index_jobs)
    from collections import Counter
    counts = Counter((a["season"], a["pitcher_id"]) for a in load_appearances(root))
    people_jobs = []
    for year, (_, index_path) in zip(years, index_jobs):
        index = json.loads(index_path.read_text())
        expected = {}
        for group in index.get("stats", []):
            for split in group.get("splits", []):
                pid = split["player"]["id"]
                expected[pid] = max(expected.get(pid, 0), split["stat"].get("gamesPitched", 0))
        missing = [pid for pid, n in sorted(expected.items()) if counts[year, pid] < n]
        # Name includes IDs: retries and later corrections never overwrite a
        # different batch through an unstable sequence number.
        for offset in range(0, len(missing), 50):
            ids = missing[offset:offset+50]
            digest = hashlib.sha256(",".join(map(str, ids)).encode()).hexdigest()[:12]
            people_jobs.append((f"{API}/people?personIds={','.join(map(str, ids))}"
                                f"&hydrate=stats(type=gameLog,group=pitching,season={year})",
                                root/f"people_{year}_{digest}.json"))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda args: _download(*args), people_jobs))
    jobs.extend(people_jobs)
    # Preserve source URLs for cached people batches on repeated invocations.
    known_paths = {path.name for _, path in jobs}
    for path in sorted(root.glob("people_*.json")):
        if path.name not in known_paths:
            year = int(path.name.split("_")[1])
            people = json.loads(path.read_text()).get("people", [])
            ids = [p["id"] for p in people]
            jobs.append((f"{API}/people?personIds={','.join(map(str, ids))}"
                         f"&hydrate=stats(type=gameLog,group=pitching,season={year})", path))
    venue_ids = sorted({game["venue_id"] for game in load_games(root)})
    venue_job = (f"{API}/venues?venueIds={','.join(map(str, venue_ids))}"
                 "&hydrate=location,timezone", root / "venues.json")
    _download(*venue_job)
    jobs.append(venue_job)
    manifest = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "MLB Advanced Media Stats API",
        "timestamp_status": "Retrospective official results; no pregame vintage",
        "files": [{"file": p.name, "url": u, "bytes": p.stat().st_size,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for u, p in jobs],
    }
    (root / "source_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def load_games(source_dir: str | Path) -> list[dict]:
    """One actual completed regular-season game per gamePk.

    MLB marks old postponed entries abstractGameState=Final and attaches the
    rescheduled game's final scores. Filtering that field alone causes leakage.
    Suspended games appear twice; their full outcome is available only on the
    completion date. They are flagged and should not be evaluation targets.
    """
    grouped = {}
    for path in sorted(Path(source_dir).glob("schedule_*.json")):
        source = json.loads(path.read_text())
        for day in source.get("dates", []):
            for game in day.get("games", []):
                if game.get("gameType") != "R":
                    continue
                if game["status"].get("detailedState") not in {"Final", "Completed Early"}:
                    continue
                if "rescheduleDate" in game:
                    continue
                sides = game.get("teams", {})
                if any("score" not in sides.get(side, {}) for side in ("home", "away")):
                    continue
                g = {
                    "game_pk": game["gamePk"],
                    "date": game["officialDate"],
                    "available_date": max(day["date"], game.get("resumeGameDate", "")),
                    "start_time": game.get("resumedFrom", game["gameDate"]),
                    "season": int(game["season"]),
                    "venue_id": game["venue"]["id"],
                    "scheduled_innings": game.get("scheduledInnings", 9),
                    "innings": game.get("linescore", {}).get("currentInning", 9),
                    "double_header": game.get("doubleHeader", "N") != "N",
                    "game_number": game.get("gameNumber", 1),
                    "suspended": bool(game.get("resumeDate") or game.get("resumedFrom")),
                    "completed_early": game["status"]["detailedState"] == "Completed Early",
                }
                for side in ("home", "away"):
                    team = sides[side]
                    g.update({f"{side}_team_id": team["team"]["id"],
                              f"{side}_team_name": team["team"]["name"],
                              f"{side}_score": team["score"]})
                g["home_win"] = int(g["home_score"] > g["away_score"])
                old = grouped.get(g["game_pk"])
                if old is None or g["available_date"] >= old["available_date"]:
                    if old:
                        g["suspended"] |= old["suspended"]
                    grouped[g["game_pk"]] = g
    return sorted(grouped.values(), key=lambda g: (g["date"], g["start_time"], g["game_pk"]))


def load_appearances(source_dir: str | Path, games=None) -> list[dict]:
    """Deduplicate full-season roster overlap; use a player's actual game team.

    A traded player's hydrated person log contains both clubs, so it must not
    inherit the team whose roster endpoint returned it. Future roster membership
    is used only to enumerate records; no roster membership is a feature.
    """
    if games is None:
        games = load_games(source_dir)
    game_index = {g["game_pk"]: g for g in games}
    result = {}
    paths = sorted(Path(source_dir).glob("pitching_*.json")) + sorted(Path(source_dir).glob("people_*.json"))
    for path in paths:
        source = json.loads(path.read_text())
        people = source.get("people", []) + [r["person"] for r in source.get("roster", [])]
        for person in people:
            for group in person.get("stats", []):
                if group.get("group", {}).get("displayName") != "pitching":
                    continue
                for split in group.get("splits", []):
                    pk = split.get("game", {}).get("gamePk")
                    if split.get("gameType") != "R" or pk not in game_index:
                        continue
                    stat = split["stat"]
                    g = game_index[pk]
                    a = {"game_pk": pk, "pitcher_id": person["id"],
                         "team_id": split["team"]["id"], "date": g["date"],
                         "available_date": g["available_date"],
                         "suspended": g["suspended"], "season": g["season"],
                         "started": bool(stat.get("gamesStarted", 0)),
                         "pitches": stat.get("numberOfPitches", 0),
                         "outs": stat.get("outs", 0), "runs": stat.get("runs", 0),
                         "earned_runs": stat.get("earnedRuns", 0),
                         "strikeouts": stat.get("strikeOuts", 0),
                         "walks": stat.get("baseOnBalls", 0),
                         "batters_faced": stat.get("battersFaced", 0),
                         "holds": stat.get("holds", 0), "saves": stat.get("saves", 0)}
                    result[(pk, person["id"])] = a
    return sorted(result.values(), key=lambda a: (a["available_date"], a["game_pk"], a["pitcher_id"]))


def load_venues(source_dir: str | Path) -> dict:
    source = json.loads((Path(source_dir) / "venues.json").read_text())
    return {v["id"]: v for v in source["venues"]}


def load_upcoming(source_dir: str | Path, day: str) -> list[dict]:
    """Normalize scheduled target games without fabricating final outcomes."""
    source = json.loads((Path(source_dir)/f"schedule_{day[:4]}.json").read_text())
    targets = {}
    for date_entry in source.get("dates", []):
        if date_entry["date"] != day:
            continue
        for g in date_entry.get("games", []):
            if g.get("gameType") != "R" or g["status"].get("abstractGameState") != "Preview":
                continue
            if g["status"].get("detailedState") not in {"Scheduled", "Pre-Game", "Warmup"}:
                continue
            if g.get("resumeDate") or g.get("resumedFrom") or g.get("rescheduleDate"):
                continue
            target = {"game_pk": g["gamePk"], "date": g["officialDate"],
                      "start_time": g["gameDate"], "season": int(g["season"]),
                      "venue_id": g["venue"]["id"], "scheduled_innings": g.get("scheduledInnings", 9),
                      "double_header": g.get("doubleHeader", "N") != "N", "suspended": False}
            for side in ("home", "away"):
                target[f"{side}_team_id"] = g["teams"][side]["team"]["id"]
                target[f"{side}_team_name"] = g["teams"][side]["team"]["name"]
            targets[g["gamePk"]] = target
    return sorted(targets.values(), key=lambda g: (g["start_time"], g["game_pk"]))


def assert_prior_games_complete(day: str, lookback_days: int = 3,
                                schedule: dict | None = None) -> None:
    """Refuse a daily snapshot while recent prior games are still unfinished.

    This uncached check must precede source-cache creation. A West Coast game
    whose official date is yesterday can still be active after midnight today;
    omitting it from completed-game history would falsely imply rest. Recent
    suspended games also fail closed until their physical-workload window ends.
    The optional schedule argument makes the temporal rule directly testable.
    """
    target = date.fromisoformat(day)
    first = (target-timedelta(days=lookback_days)).isoformat()
    last = (target-timedelta(days=1)).isoformat()
    if schedule is None:
        url = (f"{API}/schedule?sportId=1&startDate={first}&endDate={last}"
               "&gameType=R")
        for attempt in range(3):
            try:
                with urlopen(url, timeout=60) as response:
                    schedule = json.load(response)
                break
            except Exception:
                if attempt == 2:
                    raise
    if not isinstance(schedule, dict) or "dates" not in schedule:
        raise RuntimeError("Cannot verify recent MLB game completion; retry before creating a snapshot")
    pending = []
    safe_states = {"Final", "Completed Early", "Postponed", "Cancelled"}
    for entry in schedule["dates"]:
        if not first <= entry["date"] <= last:
            continue
        for game in entry.get("games", []):
            if game.get("gameType") != "R" or game.get("rescheduleDate"):
                continue
            state = game.get("status", {}).get("detailedState", "Unknown")
            if state not in safe_states:
                pending.append(f"{game.get('gamePk')} ({entry['date']}: {state})")
    if pending:
        raise RuntimeError("Recent MLB games are unfinished; no daily snapshot was cached. "
                           "Retry after completion: " + ", ".join(pending))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?", choices=["download"], default="download")
    parser.add_argument("--source-dir", default="data/raw/mlb")
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2021, 2026)))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    m = download(args.source_dir, args.years, args.workers)
    print(f"Cached {len(m['files'])} official source files in {args.source_dir}")
