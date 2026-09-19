#!/usr/bin/env python3
"""Audit a real first-basket price archive; do not fit or grade a strategy."""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/creative-market-search-2026-09-19"
PIN = "b8130671558c6d5b33d6cfbc6a8410d986d6b3ff"
NBA = ROOT / "data/raw/nba-source-feasibility/nba_stats_schedule_2024.csv"
ESPN = ROOT / "data/raw/nba-consensus-price/nba_schedule_2025.csv"
SUPPORT = {
    NBA: "ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26",
    ESPN: "a7a5b6607a256c84a324f819e4461248bdff90a78b1ddb675a5a117a9a94e74f",
}
NY = ZoneInfo("America/New_York")
VALIDATION = ROOT / "reports/nba-first-basket-validation-selection-2026-09-19.json"
VALIDATION_SHA = "5512dbf57edb64e4c8136ce8a1fa15f972999774187009eda65afbe02b626112"


def norm(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower())


def team_name(value):
    key = norm(value)
    return "laclippers" if key == "losangelesclippers" else key


def clock(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.utcoffset() is None:
        raise ValueError("Unzoned price clock")
    return value


def csv_rows(raw, fields=None):
    for row in csv.DictReader(io.StringIO(raw.decode())):
        yield {k: row[k] for k in fields} if fields else row


def verify(path, pin=None):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if pin:
        if digest != pin:
            raise ValueError(f"Support hash mismatch: {path}")
        receipt = json.loads(path.with_name(path.name + ".acquisition.json").read_text())
    else:
        receipt = json.loads(path.with_name(path.name + ".meta.json").read_text())
        if digest != receipt["sha256"] or len(raw) != receipt["bytes"]:
            raise ValueError(f"Source hash/size mismatch: {path}")
        if receipt["status"] != 200:
            raise ValueError("Failed source capture")
        if "expected_git_blob" in receipt:
            blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            if blob != receipt["expected_git_blob"]:
                raise ValueError("Git blob mismatch")
    return raw, {"path": str(path.relative_to(ROOT)), **receipt, "sha256": digest, "bytes": len(raw)}


def board_status(rows, start):
    if len(rows) != 10 or len({norm(r["name"]) for r in rows}) != 10:
        return "not_ten_unique_runners"
    if any(not math.isfinite(float(r["price"])) or float(r["price"]) <= 1 for r in rows):
        return "invalid_price"
    if len({r["update_time"] for r in rows}) != 1:
        return "mixed_market_clocks"
    for row in rows:
        quote, receipt = clock(row["update_time"]), clock(row["insert_timestamp_utc"])
        if quote > receipt:
            return "future_quote_update"
        if receipt >= start - timedelta(seconds=60):
            return "receipt_within_minute_of_or_after_start"
        if (receipt - quote).total_seconds() > 300:
            return "quote_older_than_five_minutes"
    return "pregame_ten_runner_board"


def first_score(plays):
    rows = sorted(plays, key=lambda r: r["sequence_number"])
    first = next(r for r in rows if r["scoring_play"] and r["score_value"] > 0)
    if first["period_number"] != 1 or first["home_score"] + first["away_score"] != first["score_value"]:
        raise ValueError("First scoring row is inconsistent with the scoreboard")
    return first


def validate_sample(report, history, metadata, earliest):
    import pyarrow.parquet as pq  # Optional, pinned in requirements-first-basket.txt.
    selected_raw = VALIDATION.read_bytes()
    if hashlib.sha256(selected_raw).hexdigest() != VALIDATION_SHA:
        raise ValueError("The pre-outcome validation selection changed")
    selection = json.loads(selected_raw)
    pbp_path = RAW / "play_by_play_2025.parquet"
    raw, source = verify(pbp_path)
    if hashlib.sha256(raw).hexdigest() != "e3a61b57e491b71379abd1ad4c0b2617500a3921deadd3319ee9362d49d2a9dc":
        raise ValueError("Independent play-by-play release changed")
    ids = [int(r["espn_game_id"]) for r in selection["sample"]]
    columns = ["game_id", "sequence_number", "period_number", "clock_display_value", "scoring_play",
               "score_value", "home_score", "away_score", "athlete_name_1", "athlete_id_1", "wallclock"]
    groups = defaultdict(list)
    for row in pq.read_table(pbp_path, columns=columns, filters=[("game_id", "in", ids)]).to_pylist():
        groups[str(row["game_id"])].append(row)
    id_names = {r["player_id"]: r["name"] for r in metadata}
    outcomes = {r["game_id"]: r for r in history[2025]}
    checks = []
    for sample in selection["sample"]:
        gid = sample["game_id"]
        independent = first_score(groups[sample["espn_game_id"]])
        published = outcomes[gid]
        minutes, seconds = independent["clock_display_value"].split(":")
        elapsed = 720 - 60*int(minutes) - float(seconds)
        published_name = id_names[published["first_basket"]]
        checks.append({**sample, "published_scorer": published_name,
            "independent_scorer": independent["athlete_name_1"],
            "independent_athlete_id": independent["athlete_id_1"],
            "scorer_matches": norm(published_name) == norm(independent["athlete_name_1"]),
            "points_match": float(published["pts_scored"]) == independent["score_value"],
            "game_clock_matches": float(published["time_elapsed"]) == elapsed,
            "first_points": independent["score_value"], "elapsed_seconds": elapsed,
            "quote_receipt_precedes_first_pbp_wallclock": clock(earliest[gid]["received_at"]) <
                min(clock(r["wallclock"]) for r in groups[sample["espn_game_id"]] if r["wallclock"])})
    all_ids = set(pq.read_table(pbp_path, columns=["game_id"]).column("game_id").to_pylist())
    report["independent_validation"] = {"source": source, "selection_path": str(VALIDATION.relative_to(ROOT)),
        "selection_sha256": VALIDATION_SHA, "selection_written_at": "2026-09-19T22:35:02.114523+00:00",
        "sample_rule": selection["selection_rule"], "checks": checks,
        "all_three_pass": all(all(r[k] for k in ("scorer_matches", "points_match", "game_clock_matches",
                "quote_receipt_precedes_first_pbp_wallclock")) for r in checks),
        "independent_pbp_games": len(all_ids),
        "pregame_price_games_with_independent_pbp": sum(int(r["espn_game_id"]) in all_ids for r in earliest.values()),
        "scope_note": "Only the three fixed first-score outcomes were reconciled; other games were checked for ID coverage only."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="Reconcile the frozen three-game PBP sample")
    args = parser.parse_args()
    tree_raw, tree_source = verify(RAW / "lefirstbasket-tree.json")
    tree = json.loads(tree_raw)
    if tree["sha"] != PIN or tree["truncated"]:
        raise ValueError("Unpinned or incomplete tree")
    entries = {e["path"]: e for e in tree["tree"]}
    sources = [tree_source]

    def publisher(path, fields=None):
        raw, source = verify(RAW / "lefirstbasket" / path)
        if source["expected_git_blob"] != entries[path]["sha"]:
            raise ValueError("Source differs from pinned tree")
        sources.append(source)
        return list(csv_rows(raw, fields)) if path.endswith(".csv") else raw

    prices = publisher("data/odds_first_basket.csv")
    games = publisher("data/games.csv")
    metadata = publisher("data/player_metadata.csv", ("player_id", "name"))
    rosters = publisher("data/rosters.nosync/rosters_2025.csv", ("game_id", "player_id", "Team", "starter"))
    history = {}
    for year in range(2019, 2026):
        history[year] = publisher(f"data/first_basket_{year}.csv",
                                 ("game_id", "first_basket", "jumpball_home", "jumpball_away", "jumpball_possession_tm",
                                  "pts_scored", "time_elapsed"))
    for path in ("run_before_game.py", "schedule_today_games.py", "helpers/scrape.py", "README.md"):
        publisher(path)
    schedule_raw, schedule_source = verify(NBA, SUPPORT[NBA])
    espn_raw, espn_source = verify(ESPN, SUPPORT[ESPN])
    sources.extend([schedule_source, espn_source])
    nba_games = defaultdict(list)
    for row in csv_rows(schedule_raw, ("game_id", "game_date", "team_abbreviation", "team_name", "matchup")):
        nba_games[row["game_id"]].append(row)
    fixtures = defaultdict(list)
    aliases = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
    for gid, sides in nba_games.items():
        home = [r for r in sides if "vs." in r["matchup"]]
        away = [r for r in sides if " @ " in r["matchup"]]
        if len(sides) == 2 and len(home) == len(away) == 1 and home[0]["game_date"] == away[0]["game_date"]:
            h, a = home[0], away[0]
            key = (h["game_date"], aliases.get(h["team_abbreviation"], h["team_abbreviation"]),
                   aliases.get(a["team_abbreviation"], a["team_abbreviation"]))
            fixtures[key].append({"nba_game_id": gid, "home": h["team_name"], "away": a["team_name"]})
    espn_starts = defaultdict(list)
    for row in csv_rows(espn_raw, ("game_id", "game_date", "home_display_name", "away_display_name", "start_date")):
        key = (row["game_date"], team_name(row["home_display_name"]), team_name(row["away_display_name"]))
        espn_starts[key].append((row["start_date"], row["game_id"]))
    games_by_id, names = defaultdict(list), defaultdict(set)
    for game in games:
        games_by_id[game["game_id"]].append(game)
    for player in metadata:
        names[norm(player["name"])].add(player["player_id"])
    groups = defaultdict(list)
    fd = [r for r in prices if r["bookmaker"] == "fanduel"]
    for row in fd:
        groups[(row["game_id"], row["event_id"], row["insert_timestamp_utc"])].append(row)
    ledger, leads, ages = [], [], []
    for (gid, eid, received), rows in sorted(groups.items()):
        item = {"game_id": gid, "event_id": eid, "received_at": received, "runners": len(rows)}
        candidates = games_by_id[gid]
        if len(candidates) != 1:
            item["status"] = "publisher_game_not_unique"
        else:
            game = candidates[0]
            matches = fixtures[(game["Date"], game["Home"], game["Away"])]
            if game["event_id"] != eid:
                item["status"] = "publisher_event_mismatch"
            elif len(matches) != 1:
                item["status"] = "nba_fixture_not_unique"
            else:
                fixture = matches[0]
                starts = espn_starts[(game["Date"], team_name(fixture["home"]), team_name(fixture["away"]))]
                if len(starts) != 1:
                    item["status"] = "espn_fixture_not_unique"
                else:
                    publisher_start = datetime.fromisoformat(game["Time"]).replace(tzinfo=NY)
                    independent_start = clock(starts[0][0])
                    start = min(publisher_start, independent_start)
                    item.update(fixture, espn_game_id=starts[0][1], independent_start=starts[0][0],
                                publisher_start=publisher_start.isoformat(),
                                status=board_status(rows, start),
                                lead_minutes=(start - clock(received)).total_seconds() / 60,
                                max_quote_age_seconds=max((clock(received)-clock(r["update_time"])).total_seconds() for r in rows))
                    if item["status"] == "pregame_ten_runner_board":
                        leads.append(item["lead_minutes"])
                        ages.append(item["max_quote_age_seconds"])
        item["players_with_unique_metadata_id"] = sum(len(names[norm(r["name"])]) == 1 for r in rows)
        item["prices"] = [{"name": r["name"], "decimal": float(r["price"]), "quote_time": r["update_time"]} for r in rows]
        ledger.append(item)
    valid = [r for r in ledger if r["status"] == "pregame_ten_runner_board"]
    # One earliest qualifying board per game, without inspecting a scoring result.
    first = {}
    for row in sorted(valid, key=lambda r: (r["received_at"], r["event_id"])):
        first.setdefault(row["game_id"], row)
    outcome_presence = Counter(r["game_id"] for r in history[2025] if r["first_basket"])
    roster_presence = Counter(r["game_id"] for r in rosters if r["starter"] in ("True", "1", "1.0"))
    selected = sorted(first.values(), key=lambda r: (r["independent_start"], r["nba_game_id"]))
    sample = [selected[i] for i in (0, len(selected)//2, len(selected)-1)] if selected else []
    inventory = RAW / "first-basket-board-inventory.json"
    inventory.write_text(json.dumps(ledger, indent=2) + "\n")
    report = {
        "repository": "https://github.com/martinbog19/LeFirstBasket", "commit": PIN,
        "market": "player_first_basket", "purpose": "Source feasibility only; no strategy graded or fitted",
        "sources": sources, "all_book_rows": len(prices), "book_counts": dict(Counter(r["bookmaker"] for r in prices)),
        "fanduel_rows": len(fd), "fanduel_games": len({r["game_id"] for r in fd}),
        "fanduel_players": len({r["name"] for r in fd}), "fanduel_snapshots": len(ledger),
        "quote_range": [min(r["update_time"] for r in fd), max(r["update_time"] for r in fd)],
        "snapshot_classifications": dict(Counter(r["status"] for r in ledger)),
        "pregame_ten_runner_snapshots": len(valid), "pregame_distinct_games": len(first),
        "pregame_prices": 10*len(first),
        "pregame_games_with_all_ten_unique_player_ids": sum(r["players_with_unique_metadata_id"] == 10 for r in first.values()),
        "pregame_games_with_one_nonempty_publisher_outcome": sum(outcome_presence[g] == 1 for g in first),
        "pregame_games_with_ten_publisher_starters": sum(roster_presence[g] == 10 for g in first),
        "pregame_games_with_all_ids_outcome_and_starters": sum(r["players_with_unique_metadata_id"] == 10
             and outcome_presence[g] == 1 and roster_presence[g] == 10 for g, r in first.items()),
        "receipt_lead_minutes_min_median_max": [min(leads), statistics.median(leads), max(leads)] if leads else [],
        "quote_age_seconds_min_median_max": [min(ages), statistics.median(ages), max(ages)] if ages else [],
        "historical_opening_possession_rows": {str(y): len(r) for y, r in history.items()},
        "price_board_examples": sample,
        "derived_inventory": {"path": str(inventory.relative_to(ROOT)), "sha256": hashlib.sha256(inventory.read_bytes()).hexdigest()},
        "limitations": ["Third-party CSV export; original odds response bodies and market jurisdiction absent.",
            "Market identity and UTC receipt semantics traced to pinned collector code.",
            "Ten quoted runners do not by themselves prove ten actual starters or accepted bets.",
            "Independent start is a reported scheduled start, not an observed actual-tip clock.",
            "Lineup update_time is unzoned and excluded from chronology assertions.",
            "Single snapshot for nearly every game; no general closing-price series.",
            "Publisher has researched these data; no claim of an untouched confirmatory holdout.",
            "No explicit repository license; original prices remain ignored."]}
    if args.validate:
        validate_sample(report, history, metadata, first)
    output = ROOT / "reports/nba-first-basket-source-2026-09-19.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k,v in report.items() if k not in ("sources", "price_board_examples", "limitations")}, indent=2))


if __name__ == "__main__":
    main()
