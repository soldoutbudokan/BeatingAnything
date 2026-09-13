#!/usr/bin/env python3
"""Resume official NHL input acquisition; the hazard analysis is still pending.

From the repository root, on a connection where the public endpoints are allowed:
    python tools/explore_nhl_empty_net.py --last-game 1312

Defaults to one source/schema probe from the 2024-25 regular season. Cached
responses are reused. Stops the run on an HTTP denial, timeout, or missing input;
does not retry, rotate connections, or treat partial data as a completed test.
"""

# %% Fixed sample and ordinary public requests; raw responses stay out of git.
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def acquire(url: str, path: Path, offline: bool) -> dict:
    if path.exists():
        try:
            json.loads(path.read_bytes())
        except (ValueError, UnicodeDecodeError) as exc:
            return {"url": url, "status": "invalid_cached_json", "error": str(exc)}
        return {"url": url, "status": "cached", "path": str(path)}
    if offline:
        return {"url": url, "status": "not_downloaded"}
    try:
        with urlopen(url, timeout=20) as response:
            body = response.read()
            json.loads(body)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        return {"url": url, "status": "downloaded", "path": str(path)}
    except HTTPError as exc:
        return {"url": url, "status": "http_error", "http_status": exc.code}
    except (URLError, TimeoutError, ValueError) as exc:
        return {"url": url, "status": "error", "error": str(exc)}


# %% Record input completeness, never a sport-side or pricing conclusion.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--first-game", type=int, default=1)
    parser.add_argument("--last-game", type=int, default=1)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/nhl-empty-net"))
    parser.add_argument("--report", type=Path, default=Path("reports/nhl-empty-net-inputs.json"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.first_game <= args.last_game <= 9999:
        parser.error("game range must satisfy 1 <= first <= last <= 9999")

    records = []
    paired_games = 0
    for number in range(args.first_game, args.last_game + 1):
        game_id = int(f"{args.season_start}02{number:04d}")
        endpoints = {
            "play_by_play": f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play",
            "shifts": f"https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId={game_id}&limit=-1",
        }
        pair = {"game_id": game_id}
        for kind, url in endpoints.items():
            pair[kind] = acquire(url, args.raw_dir / f"{game_id}-{kind}.json", args.offline)
            if pair[kind]["status"] not in {"cached", "downloaded"}:
                break
        records.append(pair)
        if all(pair.get(kind, {}).get("status") in {"cached", "downloaded"} for kind in endpoints):
            paired_games += 1
        else:
            break
    planned = args.last_game - args.first_game + 1
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": f"{args.season_start}{args.season_start + 1}",
        "game_type": "regular_season",
        "planned_game_numbers": [args.first_game, args.last_game],
        "planned_games": planned,
        "cached_or_downloaded_pairs": paired_games,
        "inputs_complete_for_requested_range": paired_games == planned,
        "sport_side_status": "unresolved_analysis_not_run",
        "book_side_status": "not_tested",
        "records": records,
        "next_analysis": [
            "Inspect actual response schemas and shift pagination/completeness before analysis.",
            "Identify roster goalies and union their shift start/end times separately by team.",
            "Reconstruct score before each goal; update it only after assigning that goal.",
            "Intersect one-goal-deficit intervals in period 3, seconds 1020-1200, with goalie shifts.",
            "Split at scores, goalie transitions, and clock strata; accumulate elapsed exposure seconds.",
            "Use event goalie state to resolve goal/shift boundaries; leave inconsistent timing unresolved.",
            "Compare combined and leading/trailing goal hazards to both-goalies control at matching clocks.",
            "Report pull segments, selection/manpower confounding, and the card's 200-segment threshold.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{paired_games}/{planned} paired inputs; sport-side analysis NOT RUN; {args.report}")


if __name__ == "__main__":
    main()
