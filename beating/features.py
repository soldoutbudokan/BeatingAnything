"""Lagged schedule, travel, and individual relief-pitcher workload features.

Every historical record is selected by its result-availability date, strictly
before the target date. Same-day doubleheaders never update each other. These
are retrospective reconstructions: an untimestamped sportsbook opening price
cannot establish that yesterday's game had finished when that price appeared.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .mlb import (download, load_games, load_appearances, load_venues,
                  load_upcoming, assert_prior_games_complete)

FEATURE_VERSION = "mlb_lagged_workload_v1"
TRAVEL_NAMES = ["rest_days", "travel_km", "eastward_hours", "westward_hours",
                "short_rest_travel_km", "games_last3", "games_last7",
                "innings_last3", "extra_innings_last3"]
BULLPEN_NAMES = ["bullpen_pitches_1d", "bullpen_pitches_3d", "bullpen_outs_3d",
                "bullpen_used_1d", "bullpen_used_3d", "bullpen_back_to_back",
                "bullpen_heavy_3d", "bullpen_unavailable_quality",
                "bullpen_kbb_45d", "bullpen_recent_missing"]
FORM_NAMES = ["run_diff_28d", "pitching_kbb_28d"]
SIDE_NAMES = TRAVEL_NAMES + BULLPEN_NAMES + FORM_NAMES
DIFF_FEATURES = ["diff_" + name for name in SIDE_NAMES]
TRAVEL_FEATURES = ["diff_" + name for name in TRAVEL_NAMES]
BULLPEN_FEATURES = ["diff_" + name for name in BULLPEN_NAMES]
FORM_FEATURES = ["diff_" + name for name in FORM_NAMES]


def _ordinal(value):
    return date.fromisoformat(value).toordinal()


def _distance(a, b):
    if a is None or b is None:
        return 0.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, h)))


def _coordinates(venue):
    c = venue.get("location", {}).get("defaultCoordinates", {})
    if "latitude" not in c or "longitude" not in c:
        return None
    return c["latitude"], c["longitude"]


def _offset(venue, start_time):
    zone = venue.get("timeZone", {}).get("id")
    if not zone:
        return None
    try:
        d = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        return d.astimezone(ZoneInfo(zone)).utcoffset().total_seconds() / 3600
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _travel_complete(game, history, venues, at):
    needed = [game]
    for team in (game["home_team_id"], game["away_team_id"]):
        previous = [g for g in history[team] if not g["suspended"] and 0 < at-g["_available"] <= 14]
        if previous:
            needed.append(previous[-1])
    return all(_coordinates(venues.get(g["venue_id"], {})) is not None
               and _offset(venues.get(g["venue_id"], {}), game["start_time"]) is not None
               for g in needed)


def pitching_coverage(games, appearances):
    """Return game-team keys whose pitcher logs cover a plausible full game.

    A complete-game starter omitted from an API roster is easy to notice; a
    missing starter with several relief appearances is subtler. Check outs and
    exactly one starter as well as the existence of any record. For rain-ended
    games only the starter check is defensible without play-by-play.
    """
    grouped = defaultdict(list)
    for a in appearances:
        grouped[a["game_pk"], a["team_id"]].append(a)
    good = set()
    for game in games:
        for side in ("home", "away"):
            key = game["game_pk"], game[f"{side}_team_id"]
            apps = grouped[key]
            innings = game["innings"]
            minimum_outs = innings*3
            if side == "away" and game["home_score"] > game["away_score"]:
                minimum_outs = max(0, (innings-1)*3)
            if game.get("completed_early"):
                minimum_outs = 0
            if (sum(a["started"] for a in apps) == 1
                    and sum(a["outs"] for a in apps) >= minimum_outs):
                good.add(key)
    return good


def _side_features(team, game, history, pitching, venues, at, appearances_by_game):
    h = [g for g in history[team] if 0 < at-g["_available"] <= 45]
    # Suspended-game aggregate innings and pitch counts cannot be allocated to
    # their actual days from a game log, so exclude them from physical workload.
    physical = [g for g in h if not g["suspended"]]
    last = physical[-1] if physical else None
    gap = at-last["_available"] if last else 14
    rest = min(7, max(0, gap-1))
    travel = shift = 0.0
    if last and gap <= 14:
        origin = venues.get(last["venue_id"], {})
        destination = venues.get(game["venue_id"], {})
        travel = _distance(_coordinates(origin), _coordinates(destination))
        old_offset = _offset(origin, game["start_time"])
        new_offset = _offset(destination, game["start_time"])
        if old_offset is not None and new_offset is not None:
            shift = (new_offset-old_offset+12) % 24 - 12
    last3 = [g for g in physical if at-g["_available"] <= 3]
    last7 = [g for g in physical if at-g["_available"] <= 7]
    form = [g for g in h if at-g["_available"] <= 28]
    p = [a for a in pitching[team] if 0 < at-a["_available"] <= 45]
    relief = [a for a in p if not a["started"]]
    workload = [a for a in relief if not a["suspended"] and at-a["_available"] <= 3]
    p1 = [a for a in workload if at-a["_available"] == 1]
    pitcher_recent = defaultdict(list)
    pitcher_long = defaultdict(list)
    for a in workload:
        pitcher_recent[a["pitcher_id"]].append(a)
    for a in relief:
        pitcher_long[a["pitcher_id"]].append(a)
    # Exposure and role come only from prior appearances. Saves/holds identify
    # scarce late-inning arms, while a 100-batter prior stabilizes K-BB quality.
    importance = {pid: sum(a["outs"]+3*a["saves"]+2*a["holds"] for a in apps)
                  for pid, apps in pitcher_long.items()}
    importance_total = max(1.0, sum(importance.values()))
    unavailable_quality = back_to_back = heavy = 0.0
    for pid, apps in pitcher_recent.items():
        day_pitches = {lag: sum(a["pitches"] for a in apps if at-a["_available"] == lag)
                       for lag in (1, 2, 3)}
        days = {at-a["_available"] for a in apps}
        b2b = 1 in days and 2 in days
        back_to_back += b2b
        heavy += sum(day_pitches.values()) >= 40
        fatigue = min(2.0, day_pitches[1]/25 + day_pitches[2]/60 + day_pitches[3]/100 + .35*b2b)
        past = pitcher_long[pid]
        kbb = (14 + sum(a["strikeouts"]-a["walks"] for a in past)) / (100+sum(a["batters_faced"] for a in past))
        quality = max(.5, min(1.7, 1+3*(kbb-.14)))
        unavailable_quality += importance[pid] / importance_total * quality * fatigue
    relief_kbb = (28+sum(a["strikeouts"]-a["walks"] for a in relief)) / (200+sum(a["batters_faced"] for a in relief))
    p28 = [a for a in p if at-a["_available"] <= 28]
    missing = sum((g["game_pk"], team) not in appearances_by_game or g["suspended"] for g in h if at-g["_available"] <= 3)
    run_diff = sum((g["home_score"]-g["away_score"])*(1 if g["home_team_id"] == team else -1) for g in form)
    return {
        "rest_days": float(rest), "travel_km": travel,
        "eastward_hours": max(0.0, shift), "westward_hours": max(0.0, -shift),
        "short_rest_travel_km": travel if gap == 1 else 0.0,
        "games_last3": float(len(last3)), "games_last7": float(len(last7)),
        "innings_last3": float(sum(g["innings"] for g in last3)),
        "extra_innings_last3": float(sum(max(0,g["innings"]-g["scheduled_innings"]) for g in last3)),
        "bullpen_pitches_1d": float(sum(a["pitches"] for a in p1)),
        "bullpen_pitches_3d": float(sum(a["pitches"] for a in workload)),
        "bullpen_outs_3d": float(sum(a["outs"] for a in workload)),
        "bullpen_used_1d": float(len({a["pitcher_id"] for a in p1})),
        "bullpen_used_3d": float(len(pitcher_recent)),
        "bullpen_back_to_back": float(back_to_back), "bullpen_heavy_3d": float(heavy),
        "bullpen_unavailable_quality": unavailable_quality,
        "bullpen_kbb_45d": relief_kbb, "bullpen_recent_missing": float(missing),
        "run_diff_28d": run_diff/(20+len(form)),
        "pitching_kbb_28d": (42+sum(a["strikeouts"]-a["walks"] for a in p28))/(300+sum(a["batters_faced"] for a in p28)),
    }


def build_features(games: list[dict], appearances: list[dict], venues: dict,
                   lag_days: int = 1, target_games: list[dict] | None = None) -> list[dict]:
    """Produce home-minus-away features with an explicit source-date cutoff.

    lag_days=1 permits yesterday's completed outcomes. Larger lags provide a
    conservative timing sensitivity test when historical opening timestamps are
    absent. Scheduled target venue is known; today's final data never enters X.
    """
    if lag_days < 1:
        raise ValueError("lag_days must be at least one calendar day")
    targets = sorted(games if target_games is None else target_games,
                     key=lambda g: (g["date"], g["start_time"], g["game_pk"]))
    results = sorted(({**g, "_available": _ordinal(g["available_date"])} for g in games),
                     key=lambda g: (g["_available"], g["start_time"], g["game_pk"]))
    apps = sorted(({**a, "_available": _ordinal(a["available_date"])} for a in appearances),
                  key=lambda a: (a["_available"], a["game_pk"], a["pitcher_id"]))
    app_coverage = pitching_coverage(games, appearances)
    history = defaultdict(list)
    pitching = defaultdict(list)
    ri = ai = 0
    output = []
    for game in targets:
        at = _ordinal(game["date"])
        cutoff = at-lag_days
        while ri < len(results) and results[ri]["_available"] <= cutoff:
            prior = results[ri]
            for team in (prior["home_team_id"], prior["away_team_id"]):
                history[team].append(prior)
            ri += 1
        while ai < len(apps) and apps[ai]["_available"] <= cutoff:
            prior = apps[ai]
            pitching[prior["team_id"]].append(prior)
            ai += 1
        home = _side_features(game["home_team_id"], game, history, pitching, venues, at, app_coverage)
        away = _side_features(game["away_team_id"], game, history, pitching, venues, at, app_coverage)
        row = dict(game)
        row.update({"model_feature_version": FEATURE_VERSION,
                    "feature_cutoff_date": date.fromordinal(cutoff).isoformat(),
                    "feature_lag_days": lag_days,
                    "feature_travel_complete": _travel_complete(game, history, venues, at)})
        for name in SIDE_NAMES:
            row["home_"+name] = home[name]
            row["away_"+name] = away[name]
            row["diff_"+name] = home[name]-away[name]
        output.append(row)
    return output


def write_features(source_dir: str | Path, output: str | Path, lag_days=1) -> list[dict]:
    games = load_games(source_dir)
    rows = build_features(games, load_appearances(source_dir, games), load_venues(source_dir), lag_days)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with Path(output).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def build_live_snapshot(source_dir: str | Path, day: str) -> list[dict]:
    """Create a cached daily feature snapshot for unplayed MLB games.

    Call before collecting the prediction's odds quote. The acquisition time,
    not a guessed end-of-day time, is the availability timestamp. Returning an
    ineligible record is intentional: callers must block incomplete inputs.
    """
    date.fromisoformat(day)
    root = Path(source_dir) / day
    snapshot_path = root / "live-features.json"
    if snapshot_path.exists():
        return json.loads(snapshot_path.read_text())
    # Run against a fresh official response before creating any daily source
    # cache: a retry must not reuse an early, unfinished previous-day snapshot.
    assert_prior_games_complete(day)
    root.mkdir(parents=True, exist_ok=True)
    download(root, years=[int(day[:4])], workers=4)
    games = load_games(root)
    appearances = load_appearances(root, games)
    venues = load_venues(root)
    targets = load_upcoming(root, day)
    # The full season's schedule includes every target venue; if a new venue
    # has not hosted a completed game yet, explicitly acquire it too.
    missing = sorted({g["venue_id"] for g in targets} - venues.keys())
    if missing:
        from .mlb import API, _download
        path = root / "target_venues.json"
        _download(f"{API}/venues?venueIds={','.join(map(str,missing))}&hydrate=location,timezone", path)
        venues.update({v["id"]: v for v in json.loads(path.read_text())["venues"]})
    rows = build_features(games, appearances, venues, target_games=targets)
    observed_at = datetime.now(timezone.utc).isoformat()
    result = []
    for row in rows:
        reasons = []
        if not row["feature_travel_complete"]:
            reasons.append("Missing target or origin venue coordinates/time zone")
        if row["home_bullpen_recent_missing"] or row["away_bullpen_recent_missing"]:
            reasons.append("Incomplete or suspended recent pitching history")
        if row["double_header"]:
            reasons.append("Doubleheader is outside the fitted market contract")
        result.append({"event_id": f"mlb:{row['game_pk']}", "game_pk": row["game_pk"],
                       "home_team_id": row["home_team_id"], "away_team_id": row["away_team_id"],
                       "home_team_name": row["home_team_name"], "away_team_name": row["away_team_name"],
                       "start_time": row["start_time"], "feature_cutoff_at": observed_at,
                       "feature_result_max_date": row["feature_cutoff_date"],
                       "model_feature_version": FEATURE_VERSION,
                       "input_data_complete": not reasons, "data_quality_reasons": reasons,
                       **{name: row[name] for name in DIFF_FEATURES}})
    temporary = root / "live-features.tmp"
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(snapshot_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default="data/raw/mlb")
    parser.add_argument("--output", default="data/processed/mlb_features.csv")
    parser.add_argument("--lag-days", type=int, default=1)
    args = parser.parse_args()
    result = write_features(args.source_dir, args.output, args.lag_days)
    print(f"Wrote {len(result)} game rows with {len(DIFF_FEATURES)} difference features")
