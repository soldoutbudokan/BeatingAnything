#!/usr/bin/env python3
"""Execute card 41's fixed 2019–2024 sport-side screen, without price fitting."""
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_nba_first_basket_archive import RAW, csv_rows, verify


def main():
    all_rows, sources = [], []
    for season in range(2019, 2025):
        path = RAW / f"lefirstbasket/data/first_basket_{season}.csv"
        raw, source = verify(path)
        sources.append(source)
        for row in csv_rows(raw):
            all_rows.append({**row, "file_season": season})
    ids = Counter(r["game_id"] for r in all_rows)
    counts, rows = Counter(), []
    for row in all_rows:
        if ids[row["game_id"]] != 1:
            counts["duplicate_game_id"] += 1
        elif any(row[k] in ("", "nan", "None", "NA") for k in
                 ("jumpball_home", "jumpball_away", "jumpball_possession", "first_basket")):
            counts["missing_jumper_possession_or_scorer"] += 1
        elif row["jumpball_home"] == row["jumpball_away"] or row["Home"] == row["Away"]:
            counts["invalid_identical_players_or_teams"] += 1
        elif row["first_basket_tm"] not in (row["Home"], row["Away"]) or row["jumpball_possession_tm"] not in (row["Home"], row["Away"]):
            counts["unidentified_team"] += 1
        elif float(row["pts_scored"]) not in (1, 2, 3):
            counts["invalid_first_score"] += 1
        else:
            played = date.fromisoformat(row["Date"][:10])
            if row["game_id"][:8] != played.strftime("%Y%m%d"):
                raise ValueError("Game date/identity disagreement")
            rows.append({"game_id": row["game_id"], "season": row["file_season"],
                         "week": played.strftime("%G-W%V"),
                         "possession_team_scored_first": row["jumpball_possession_tm"] == row["first_basket_tm"]})
    weeks = defaultdict(lambda: [0, 0])
    for row in rows:
        weeks[row["week"]][0] += int(row["possession_team_scored_first"])
        weeks[row["week"]][1] += 1
    blocks = np.array(list(weeks.values()), dtype=float)
    rng = np.random.default_rng(1729)
    draws = blocks[rng.integers(0, len(blocks), size=(10000, len(blocks)))].sum(axis=1)
    contrasts = 2 * draws[:, 0] / draws[:, 1] - 1
    wins = sum(r["possession_team_scored_first"] for r in rows)
    n = len(rows)
    contrast = 2 * wins / n - 1
    seasons = {}
    for year in range(2019, 2025):
        selected = [r for r in rows if r["season"] == year]
        seasons[str(year)] = {"games": len(selected),
            "first_possession_team_first_score_rate": sum(r["possession_team_scored_first"] for r in selected)/len(selected)}
    result = {"card": 41, "purpose": "Fixed sport-side triage; no prices or model fitted", "sources": sources,
        "input_rows": len(all_rows), "exclusions": dict(counts), "valid_games": n,
        "calendar_week_blocks": len(blocks), "first_possession_team_first_scores": wins,
        "first_possession_team_first_score_rate": wins/n,
        "other_team_first_score_rate": 1-wins/n,
        "probability_contrast": contrast,
        "descriptive_95pct_week_bootstrap_interval": np.quantile(contrasts, [.025, .975]).tolist(),
        "bootstrap_draws": 10000, "seed": 1729, "seasons": seasons,
        "fixed_gate": {"minimum_games": 1000, "minimum_probability_contrast": .10,
                       "passed": n >= 1000 and contrast >= .10},
        "interpretation": "Observed possession advantage; not evidence of FanDuel mispricing or a causal jumper effect."}
    output = ROOT / "reports/nba-first-possession-screen-2026-09-19.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k:v for k,v in result.items() if k != "sources"}, indent=2))


if __name__ == "__main__":
    main()
