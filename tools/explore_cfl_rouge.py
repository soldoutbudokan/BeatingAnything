#!/usr/bin/env python3
"""Bound the fixed CFL rouge adjustment; aggregates cannot classify kick paths."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/cfl-source-screen"
OUT = ROOT / "reports/cfl-rouge-screen-2026-09-13"
SOURCES = {
    "fixtures-2024.json": ("https://echo.pims.cfl.ca/api/seasons/33/fixtures?limit=100", "e17e3b1f381cd5281499a86bf3e44310d396c18f7615eb2af70c5c836cc35749"),
    "fixtures-2025.json": ("https://echo.pims.cfl.ca/api/seasons/34/fixtures?limit=100", "f905213cfcb73b1f1d78c6b05d730c2b915f70897c7870ed587394ceb5d91a24"),
    "fixtures-2026.json": ("https://echo.pims.cfl.ca/api/seasons/75/fixtures?limit=100", "1fe037922c8850284e3663222dac4d335878487f01dc86c28efc67382f69298a"),
    "official-team-stats.json": ("https://api.stats.cfl.ca/stats/teams", "7cf7638b6341aa697851f57912d7158e40c522f1711e8a0de57922a5934b8f58"),
    "teamrecords-2024.json": ("https://echo.pims.cfl.ca/api/stats/teamrecords?season_id=33", "cdbd1d8580370faa56e1a1ba651b3f28ac589daeaad3d44c1640289fe127c567"),
}


def load(fetch):
    RAW.mkdir(parents=True, exist_ok=True)
    data, provenance = {}, []
    for name, (url, expected) in SOURCES.items():
        path = RAW / name
        if not path.exists() and fetch:
            # Ordinary public GET once. Errors propagate; there is no retry.
            with urllib.request.urlopen(url, timeout=30) as response:
                path.write_bytes(response.read())
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if digest != expected:
            raise ValueError(f"Changed input {name}; preserve this result and label a new source version")
        data[name] = json.loads(body)
        provenance.append({"file": name, "url": url, "bytes": len(body), "sha256": digest})
    return data, provenance


def analyze(data):
    seasons = []
    for year in (2024, 2025):
        games = [g for g in data[f"fixtures-{year}.json"] if g["game_type_id"] == 1]
        assert len(games) == 81 and len({g["ID"] for g in games}) == 81
        assert all(g["game_status"] == "Finished" for g in games)
        teams = []
        for team in data["official-team-stats.json"]:
            rows = [s for s in team["seasons"] if s.get("season") == year and s.get("year") == year]
            assert len(rows) == 1
            row = rows[0]
            assert row["gamesPlayed"] == 18
            assert isinstance(row["singles"], int) and row["singles"] >= 0
            scored = sum(g["home_team_score"] if g["home_team_id"] == team["team_id"] else g["away_team_score"]
                         for g in games if team["team_id"] in (g["home_team_id"], g["away_team_id"]))
            teams.append({"team": team["abbreviation"], "team_games": row["gamesPlayed"],
                          "singles": row["singles"], "singles_allowed": row["singlesAllowed"],
                          "punt_singles": row.get("singlesPunts"),
                          "kickoff_singles": row.get("singlesKickoffs"),
                          "fixture_points_scored": scored, "aggregate_points_scored": row["pointsScored"],
                          "fixture_minus_aggregate_points": scored - row["pointsScored"]})
        assert len(teams) == 9
        singles = sum(t["singles"] for t in teams)
        assert singles == sum(t["singles_allowed"] for t in teams)
        seasons.append({"year": year, "games": len(games), "teams": teams,
                        "all_scored_singles": singles, "classified_abolished_singles": 0,
                        "removed_points_per_game_bounds": [0, singles / len(games)]})
    games = sum(s["games"] for s in seasons)
    singles = sum(s["all_scored_singles"] for s in seasons)
    calendar = [g for g in data["fixtures-2026.json"] if g["game_type_id"] == 1]
    final = max(g["start_at_local"][:10] for g in calendar)
    rejected = sorted({s.get("year") for t in data["teamrecords-2024.json"] for s in t["seasons"]})
    return {"seasons": seasons, "games": games, "scored_singles": singles,
            "classified_abolished_singles": 0, "removed_points_per_game_bounds": [0, singles / games],
            "point_total_discrepancies": [{"year": s["year"], **t} for s in seasons for t in s["teams"]
                                          if t["fixture_minus_aggregate_points"] != 0],
            "removed_points_per_team_game_bounds": [0, singles / (games * 2)],
            "requested_2024_legacy_endpoint_returned_years": rejected,
            "2026_regular_season_end": final,
            "days_to_2026_regular_season_end_from_screen": (date.fromisoformat(final) - date(2026, 9, 13)).days}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Fetch missing pinned public inputs once")
    args = parser.parse_args()
    data, sources = load(args.fetch)
    result = analyze(data)
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "hypothesis": "cfl-rouge-rule-scoring", "status": "unresolved: kick trajectories/touches absent",
              "fixed_screen": {"seasons": [2024, 2025], "minimum_classified_single_kicks": 100,
                               "minimum_game_coverage": .90, "minimum_removed_points_per_game": .5},
              "sources": sources, "result": result,
              "limitations": ["These arithmetic bounds condition on reported single counts; they are not effect estimates or confidence intervals.",
                              "Montreal 2024 aggregate points are two below the fixture sum. Reconcile before treating the source as exact scoring truth.",
                              "Season totals cannot distinguish untouched end-zone exits from still-valid returner concessions.",
                              "Null punt/kickoff subcategories remain null; they are not silently zero-filled.",
                              "2026 behavior can change, and further 2027 field/goalpost rules require a new definition.",
                              "No FanDuel prices, score-distribution fit, expected return or edge were calculated."]}
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    rows = "\n".join(f"| {s['year']} | {s['games']} | {s['all_scored_singles']} | 0–{s['removed_points_per_game_bounds'][1]:.3f} |" for s in result["seasons"])
    text = f"""# CFL rouge-rule screen — September 13, 2026

**Unresolved: kick trajectories/touches are absent and one scoring total differs.** The fixed 2024–25 source reports {result['scored_singles']} single points in {result['games']} games. Conditional on those counts, removing every single would subtract {result['removed_points_per_game_bounds'][1]:.3f} points per game; removing none gives zero. This arithmetic range is not an estimated effect or a validated bound on true scoring. It cannot pass the card's 100-classified-kick/0.5-point screen.

| Season | Regular-season games | All scored singles | Removed points per game, possible range |
| --- | ---: | ---: | ---: |
{rows}

Seventeen of eighteen team-season aggregate point totals match regular-season fixtures. **Montreal 2024 is 455 in fixtures versus 453 in the aggregate; the two-point discrepancy remains unresolved.** Singles scored reconcile to singles allowed at league level in both years, but that is not independent validation of each kick. Missing punt/kickoff subcategories remain null, and all singles must not be reclassified as abolished. No counterfactual score was reconstructed.

The official public [CFL Stats endpoint](https://api.stats.cfl.ca/stats/teams) supplies the historical aggregates. Its URL is referenced by the public [CFL Stats site](https://stats.cfl.ca/). The older SDK endpoint requested with `season_id=33` returned only **2026** records, so it was rejected as 2024 evidence. The newer endpoint's explicit nested season/year fields were checked before aggregation. Complete fixture lists were recovered from [CFL's public fixture service](https://echo.pims.cfl.ca/api/seasons/33/fixtures?limit=100).

Current official fixtures put the regular-season end on **{result['2026_regular_season_end']}**, only **{result['days_to_2026_regular_season_end_from_screen']} days** from this screen. CFL is included at the user's suggestion, but this season does not solve the short-runway concern. Preserve this study and use the longer NBA/rugby calendars for active work. Further announced field and goalpost changes mean these definitions must not be carried unchanged into 2027.

The [new card](../docs/hypotheses/cfl-rouge-rule-scoring.md) was saved before historical scoring aggregation. Public rule-change descriptions identify untouched end-zone exits as removed singles while preserving returner concessions. CFL article reads returned 403 and the linked rulebook web reader returned 405; no repeated requests or alternate authenticated route was used to overcome those denials. Primary calendar fixtures and aggregate stats were available through their separately published ordinary public services.

Next missing input: permitted event records that explicitly distinguish untouched boundary exits, return touches and concessions for the pinned 2024–25 games. Do not build a game-total model from these bounds or infer book error from a public rule change. No FanDuel market prices were collected.

Run `python tools/explore_cfl_rouge.py`; `--fetch` retrieves missing public inputs once and verifies their pinned hashes. A changed live source is rejected, not silently substituted. [JSON results and source hashes](cfl-rouge-screen-2026-09-13.json). Raw third-party files remain ignored.
"""
    OUT.with_suffix(".md").write_text(text)
    print(json.dumps({k: v for k, v in result.items() if k != "seasons"}, indent=2))


if __name__ == "__main__":
    main()
