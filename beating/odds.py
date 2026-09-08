"""Audit and normalize a public MLB odds archive without assuming quote times.

The source's ``currentLine`` can contain in-play prices. It is deliberately
absent from returned modeling data. Opening prices are retrospective research
inputs, with unknown capture times and no claim of historical executability.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Iterable
from urllib.request import Request, urlopen

import pandas as pd

ARCHIVE_URL = "https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/download/dataset/mlb_odds_dataset.json"
ARCHIVE_SHA256 = "3f952fd0bfae9f4f2d17e66692cb936ce6e1a5f6b415318012090c85933b882b"
ARCHIVE_BYTES = 80120813
TEAM_IDS = {
    "ARI": 109, "AZ": 109, "ATL": 144, "BAL": 110, "BOS": 111,
    "CHC": 112, "CHW": 145, "CWS": 145, "CIN": 113, "CLE": 114,
    "COL": 115, "DET": 116, "HOU": 117, "KC": 118, "KCR": 118,
    "LAA": 108, "LAD": 119, "MIA": 146, "MIL": 158, "MIN": 142,
    "NYM": 121, "NYY": 147, "OAK": 133, "ATH": 133, "PHI": 143,
    "PIT": 134, "SD": 135, "SDP": 135, "SEA": 136, "SF": 137,
    "SFG": 137, "STL": 138, "TB": 139, "TBR": 139, "TEX": 140,
    "TOR": 141, "WAS": 120, "WSH": 120, "WSN": 120,
}


def american_to_decimal(price: float) -> float:
    """Reject zero, nonfinite and malformed American prices."""
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ValueError("American odds must be numeric")
    if not math.isfinite(price) or abs(price) < 100:
        raise ValueError("American odds must be finite and have magnitude >= 100")
    return 1.0 + (price / 100.0 if price > 0 else 100.0 / -price)


def opening_pair(book: dict) -> tuple[float, float, float, float]:
    line = book.get("openingLine") or {}
    home = american_to_decimal(line.get("homeOdds"))
    away = american_to_decimal(line.get("awayOdds"))
    overround = 1 / home + 1 / away
    # Structural bound, fixed before evaluating outcomes. No selected odds range.
    if not 1.0 <= overround <= 1.25:
        raise ValueError("Implausible two-way opening market overround")
    return home, away, (1 / home) / overround, overround


def fetch_archive(destination: str | Path) -> dict:
    """Download a publicly offered release asset, pin its bytes, write provenance."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".part")
        request = Request(ARCHIVE_URL, headers={"User-Agent": "BeatingAnything-research/0.1"})
        try:
            with urlopen(request, timeout=60) as response, temporary.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if digest != ARCHIVE_SHA256:
                raise ValueError("Archive checksum changed: review source before use")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    payload = target.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != ARCHIVE_SHA256:
        raise ValueError("Existing archive does not match the audited release")
    manifest = {
        "url": ARCHIVE_URL, "sha256": digest, "bytes": len(payload),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "ArnavSaraogi public release; original odds attributed to SportsbookReview",
        "license": "No explicit repository or dataset license found; raw data not redistributed",
        "first_date": "2021-04-01", "last_date": "2025-08-16",
        "quote_timestamps_available": False,
        "current_line_status": "Unverified archival terminal price; may be in-play; prohibited as close or model input",
    }
    target.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _schedule_index(paths: Iterable[str | Path]) -> dict:
    index: dict = defaultdict(dict)
    for path in paths:
        obj = json.loads(Path(path).read_text())
        for day in obj.get("dates", []):
            for game in day.get("games", []):
                key = (
                    game.get("officialDate", day["date"]),
                    game["teams"]["away"]["team"]["id"],
                    game["teams"]["home"]["team"]["id"],
                )
                index[key][game["gamePk"]] = game
    return index


def load_archive(archive_path: str | Path, schedule_paths: Iterable[str | Path]) -> tuple[pd.DataFrame, dict]:
    """Return uniquely matched MLB regular-season games and structural audit.

    Team/date doubleheaders are excluded because the source merges their rows.
    Schedules are authoritative for IDs and results. As-of flags remain explicit;
    they cannot be repaired by retrospectively joining final schedules.
    """
    path = Path(archive_path)
    raw_bytes = path.read_bytes()
    archive = json.loads(raw_bytes)
    schedule = _schedule_index(schedule_paths)
    drops: Counter = Counter()
    all_flags: Counter = Counter()
    source_types: Counter = Counter()
    rows = []
    candidate_counts: Counter = Counter()
    raw_open_holds, raw_other_gaps = [], []
    source_count = 0
    for date, games in archive.items():
        for game in games:
            v = game.get("gameView", {})
            candidate_counts[(date, v.get("awayTeam", {}).get("shortName"), v.get("homeTeam", {}).get("shortName"))] += 1
    for date, games in sorted(archive.items()):
        for raw in games:
            source_count += 1
            v = raw.get("gameView", {})
            source_types[str(v.get("gameType"))] += 1
            books = raw.get("odds", {}).get("moneyline", [])
            fd_books = [b for b in books if b.get("sportsbook") == "fanduel"]
            if len(fd_books) != 1:
                drops["missing_or_duplicate_fanduel_moneyline"] += 1
                continue
            try:
                home_decimal, away_decimal, p_home, hold = opening_pair(fd_books[0])
            except ValueError:
                drops["invalid_opening_price_or_overround"] += 1
                continue
            raw_open_holds.append(hold)
            consensus = []
            for book in books:
                if book.get("sportsbook") == "fanduel":
                    continue
                try:
                    consensus.append(opening_pair(book)[2])
                except ValueError:
                    pass
            other_p = statistics.median(consensus) if consensus else float("nan")
            gap = abs(other_p - p_home) if consensus else float("nan")
            if consensus:
                raw_other_gaps.append(gap)
                if gap > 0.10:
                    all_flags["opening_cross_book_gap_gt_0_10"] += 1
            away_abbr = v.get("awayTeam", {}).get("shortName")
            home_abbr = v.get("homeTeam", {}).get("shortName")
            away_id, home_id = TEAM_IDS.get(away_abbr), TEAM_IDS.get(home_abbr)
            if not away_id or not home_id:
                drops["unknown_team"] += 1
                continue
            if candidate_counts[(date, away_abbr, home_abbr)] != 1:
                drops["duplicate_source_date_team_pair"] += 1
                continue
            matches = list(schedule.get((date, away_id, home_id), {}).values())
            if len(matches) != 1:
                drops["ambiguous_schedule_date_team_pair" if matches else "unmatched_schedule"] += 1
                continue
            official = matches[0]
            if official.get("gameType") != "R":
                drops["not_regular_season"] += 1
                continue
            if official.get("doubleHeader", "N") != "N":
                drops["doubleheader_source_merge_risk"] += 1
                continue
            # Resumed games can mix original dates, new quotes and final results.
            if any(official.get(k) for k in ("resumeDate", "resumeGameDate", "resumedFrom", "resumedFromDate")):
                drops["resumed_game"] += 1
                continue
            if official.get("rescheduleDate"):
                drops["rescheduled_game"] += 1
                continue
            if official.get("status", {}).get("detailedState") not in {"Final", "Completed Early"} or not v.get("gameStatusText", "").startswith("Final"):
                drops["not_final"] += 1
                continue
            score_h = official["teams"]["home"].get("score")
            score_a = official["teams"]["away"].get("score")
            if score_h is None or score_a is None or score_h == score_a:
                drops["missing_or_tied_result"] += 1
                continue
            if score_h != v.get("homeTeamScore") or score_a != v.get("awayTeamScore"):
                drops["score_disagrees_with_mlb"] += 1
                continue
            try:
                source_start = datetime.fromisoformat(v["startDate"].replace("Z", "+00:00"))
                official_start = datetime.fromisoformat(official["gameDate"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                drops["invalid_start_time"] += 1
                continue
            # Not an odds filter: protects joins across date/time changes.
            if abs((source_start - official_start).total_seconds()) > 12 * 3600:
                drops["start_time_disagrees_gt_12h"] += 1
                continue
            rows.append({
                "game_pk": official["gamePk"], "date": date,
                "start_time": official_start.isoformat(), "season": int(date[:4]),
                "home_team_id": home_id, "away_team_id": away_id,
                "home_team": official["teams"]["home"]["team"]["name"],
                "away_team": official["teams"]["away"]["team"]["name"],
                "home_win": int(score_h > score_a),
                "fd_home_open_decimal": home_decimal, "fd_away_open_decimal": away_decimal,
                "fd_home_open_prob": p_home, "fd_open_overround": hold,
                "other_open_consensus_prob": other_p, "other_open_book_count": len(consensus),
                "other_open_absolute_gap": gap,
                "other_open_as_of_unverified": True,
                "opening_quote_as_of_unverified": True,
                "opening_quote_time": None,
                "archival_terminal_usable_for_clv": False,
            })
    frame = pd.DataFrame(rows)
    if not frame.empty:
        if frame.game_pk.duplicated().any():
            duplicate = frame.game_pk.duplicated(keep=False)
            drops["duplicate_mlb_game_id"] += int(duplicate.sum())
            frame = frame.loc[~duplicate].copy()
        frame = frame.sort_values(["date", "start_time", "game_pk"]).reset_index(drop=True)
    audit = {
        "source_url": ARCHIVE_URL, "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source_bytes": len(raw_bytes), "source_dates": len(archive),
        "source_game_rows": source_count, "source_game_types": dict(source_types),
        "accepted_rows": len(frame), "structural_exclusions": dict(drops),
        "diagnostic_flags_not_exclusions": dict(all_flags),
        "odds_range_filter": None,
        "accepted_by_year": {str(k): int(v) for k, v in frame.groupby("season").size().items()} if not frame.empty else {},
        "opening_overround_all_valid": {"min": min(raw_open_holds), "median": statistics.median(raw_open_holds), "max": max(raw_open_holds)} if raw_open_holds else {},
        "other_book_open_gap_all_valid": {"max": max(raw_other_gaps), "gt_0_05": sum(x > .05 for x in raw_other_gaps), "gt_0_10": sum(x > .10 for x in raw_other_gaps), "gt_0_20": sum(x > .20 for x in raw_other_gaps)} if raw_other_gaps else {},
        "quote_time_provenance": "Missing; opening executable timing not established",
        "clv_available": False,
        "archival_terminal_in_play_warning": {
            "date": "2021-04-01", "game": "Cleveland at Detroit",
            "fanduel_open_home_american": 158, "fanduel_open_away_american": -192,
            "fanduel_archival_terminal_home_american": -1100,
            "fanduel_archival_terminal_away_american": 620,
            "result": "Detroit 3, Cleveland 2",
            "interpretation": "Strong in-play contamination signal; no quote timestamp; all currentLine fields excluded",
        },
    }
    assert len(frame) + sum(drops.values()) == source_count
    return frame, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data/raw/mlb_odds_dataset.json"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--schedules", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=Path("data/processed/odds.csv"))
    parser.add_argument("--audit", type=Path, default=Path("reports/data-audit.json"))
    args = parser.parse_args()
    if args.fetch:
        print(json.dumps(fetch_archive(args.archive), indent=2))
    if args.schedules:
        frame, audit = load_archive(args.archive, args.schedules)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False)
        args.audit.write_text(json.dumps(audit, indent=2) + "\n")
        print(json.dumps(audit, indent=2))
    elif not args.fetch:
        parser.error("provide --fetch and/or --schedules")


if __name__ == "__main__":
    main()
