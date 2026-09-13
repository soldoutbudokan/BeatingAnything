#!/usr/bin/env python3
"""Fixed exploratory wind/long-kick screen; no odds, model fit, or betting action."""
# %% Definitions were set before inspecting kick outcomes on September 13, 2026.
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nfl-wind-kicks"
OUT = ROOT / "reports/nfl-wind-kicks-2026-09-13"
PINS = {
    2021: "e8743a568f99667a8bdcd29ba12224ee1782ad2b7916bee78ee335c099383739",
    2022: "0c69a71eb39498956c7b1d5c1ca52ce7fe679934a95d1af249facb5ea9829ea4",
    2023: "4649804ee0f0a40b41e51ec75a1ce921949d7fab5459213488656b92f78560e8",
    2024: "23370d5d10f8104d80d46a1fc5e61f4f6f5a3263fe96fe2dd629913cfcb08c06",
    2025: "2f135887790a013fd004e609e37096bb4816d5cc80b9f19122e1bad478961978",
}
COLS = ["game_id", "play_id", "season", "season_type", "posteam", "fixed_drive",
        "yardline_100", "down", "play_type", "field_goal_attempt",
        "field_goal_result", "kick_distance", "roof", "wind"]
VALID_TYPES = {"pass", "run", "field_goal", "punt", "qb_kneel", "qb_spike"}
METRICS = ["long_attempts", "long_makes", "all_attempts", "all_makes"]


def load(download):
    frames, sources = [], []
    RAW.mkdir(parents=True, exist_ok=True)
    for year, pin in PINS.items():
        path = RAW / f"play_by_play_{year}.csv.gz"
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/{path.name}"
        if not path.exists() and download:
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != pin:
            raise ValueError(f"Changed source {path.name}; preserve this screen and label a new input.")
        df = pd.read_csv(path, usecols=COLS, low_memory=False)
        assert not df.duplicated(["game_id", "play_id"]).any()
        assert set(df.season.unique()) == {year}
        sources.append({"season": year, "url": url, "sha256": digest,
                        "bytes": path.stat().st_size, "rows": len(df)})
        frames.append(df)
    return pd.concat(frames, ignore_index=True), sources


# %% Eligible drives, game weather, and separate decision/accuracy outcomes.
def project(pbp):
    canceled = "2022_17_BUF_CIN"  # Abandoned game, excluded before any outcome comparison.
    initial_games = pbp.game_id.nunique()
    pbp = pbp.loc[pbp.game_id.ne(canceled)].copy()
    weather_conflicts = pbp.groupby("game_id")[["roof", "wind"]].nunique(dropna=True)
    if weather_conflicts.gt(1).any().any():
        raise ValueError("Conflicting within-game roof/wind: resolve before screening.")
    games = pbp.groupby("game_id").agg(season=("season", "first"),
        roof=("roof", "first"), wind=("wind", "first"))
    games["weather_eligible"] = games.roof.isin(["outdoors", "open"]) & games.wind.between(0, 100)
    games["exposed"] = games.weather_eligible & games.wind.ge(15)
    coverage = {
        "input_games": int(initial_games), "completed_games": len(games),
        "abandoned_games_excluded": int(initial_games - len(games)),
        "roof_game_counts": games.roof.fillna("missing").value_counts().to_dict(),
        "outdoor_or_open_games": int(games.roof.isin(["outdoors", "open"]).sum()),
        "outdoor_or_open_missing_wind_games": int((games.roof.isin(["outdoors", "open"]) & games.wind.isna()).sum()),
        "outdoor_or_open_invalid_wind_games": int((games.roof.isin(["outdoors", "open"]) & games.wind.notna() & ~games.wind.between(0, 100)).sum()),
        "eligible_weather_games": int(games.weather_eligible.sum()),
        "high_wind_games": int(games.exposed.sum()),
        "wind_missingness_by_season_and_roof": [],
    }
    for (season, roof), block in games.groupby(["season", "roof"], dropna=False):
        coverage["wind_missingness_by_season_and_roof"].append({"season": int(season),
            "roof": roof if pd.notna(roof) else None, "games": len(block),
            "missing_wind_games": int(block.wind.isna().sum()),
            "high_wind_games": int(block.exposed.sum())})
    valid = pbp.play_type.isin(VALID_TYPES) & pbp.posteam.notna() & pbp.down.notna()
    opportunity = valid & pbp.yardline_100.between(25, 40)
    keys = ["game_id", "fixed_drive", "posteam"]
    triggers = (pbp.loc[opportunity].groupby(keys).play_id.min().rename("trigger_play_id").reset_index())
    plays = pbp.merge(triggers, on=keys, how="inner")
    plays = plays.loc[plays.play_id.ge(plays.trigger_play_id)].copy()
    # play_type=no_play is not a valid attempt; do not count nullified kicks.
    fg = plays.play_type.eq("field_goal") & plays.field_goal_attempt.eq(1)
    made = fg & plays.field_goal_result.eq("made")
    coverage["eligible_drive_valid_field_goal_attempts_missing_distance_before_weather_filter"] = int((fg & plays.kick_distance.isna()).sum())
    coverage["eligible_drive_valid_field_goal_attempts_missing_result_before_weather_filter"] = int((fg & plays.field_goal_result.isna()).sum())
    plays["long_attempts"] = (fg & plays.kick_distance.ge(50)).astype(int)
    plays["long_makes"] = (made & plays.kick_distance.ge(50)).astype(int)
    plays["all_attempts"] = fg.astype(int)
    plays["all_makes"] = made.astype(int)
    drives = plays.groupby(keys)[METRICS].sum().join(games, on="game_id").reset_index()
    coverage["all_eligible_drives_before_weather_filter"] = len(drives)
    coverage["eligible_drives_with_outdoor_or_open_roof_but_missing_wind"] = int(
        (drives.roof.isin(["outdoors", "open"]) & drives.wind.isna()).sum())
    drives = drives.loc[drives.weather_eligible].copy()
    drives["drives"] = 1
    return drives, coverage


def totals(df):
    result = {m: int(df[m].sum()) for m in ["drives"] + METRICS}
    result["games"] = int(df.game_id.nunique())
    for metric in METRICS:
        result[metric + "_per_drive"] = result[metric] / result["drives"] if result["drives"] else None
    result["long_success_given_attempt"] = result["long_makes"] / result["long_attempts"] if result["long_attempts"] else None
    return result


# %% Season/roof standardization, with descriptive game-cluster uncertainty.
def compare(drives):
    strata, arrays, matched = [], [], []
    for (season, roof), block in drives.groupby(["season", "roof"]):
        high, low = block.loc[block.exposed], block.loc[~block.exposed]
        entry = {"season": int(season), "roof": roof, "high": totals(high), "low": totals(low)}
        entry["matched"] = bool(len(high) and len(low))
        strata.append(entry)
        if entry["matched"]:
            matched.append(block)
            arrays.append([group.groupby("game_id")[["drives"] + METRICS].sum().to_numpy()
                           for group in [high, low]])
    if not arrays:
        raise ValueError("No matched wind strata.")
    matched = pd.concat(matched)

    def estimates(blocks):
        high_sum = np.zeros(5)
        counterfactual = np.zeros(4)
        for high, low in blocks:
            h, l = high.sum(axis=0), low.sum(axis=0)
            high_sum += h
            counterfactual += h[0] * l[1:] / l[0]
        exposed_rates = high_sum[1:] / high_sum[0]
        control_rates = counterfactual / high_sum[0]
        return exposed_rates, control_rates, 1 - exposed_rates / control_rates

    exposed, baseline, reduction = estimates(arrays)
    rng = np.random.default_rng(20260913)
    draws = []
    for _ in range(2000):
        sample = [[group[rng.integers(0, len(group), size=len(group))] for group in pair] for pair in arrays]
        draws.append(estimates(sample)[2])
    ci = np.percentile(np.array(draws), [2.5, 97.5], axis=0)
    result = {metric: {"high_rate": float(exposed[i]),
                      "season_roof_standardized_low_rate": float(baseline[i]),
                      "relative_reduction": float(reduction[i]),
                      "relative_reduction_game_cluster_95pct_interval": ci[:, i].tolist()}
              for i, metric in enumerate(METRICS)}
    return {"high": totals(drives.loc[drives.exposed]), "low": totals(drives.loc[~drives.exposed]),
            "matched_high": totals(matched.loc[matched.exposed]),
            "unmatched_high_drives": int(drives.exposed.sum() - matched.exposed.sum()),
            "strata": strata, "standardized": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download missing pinned public inputs")
    args = parser.parse_args()
    pbp, sources = load(args.download)
    drives, coverage = project(pbp)
    result = compare(drives)
    effect = result["standardized"]["long_makes"]["relative_reduction"]
    enough = result["matched_high"]["drives"] >= 200
    gate = "passes descriptive magnitude screen" if enough and effect >= .20 else (
        "fails descriptive magnitude screen" if enough else "insufficient exposed drives")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_date": "2026-09-13", "hypothesis": "football-wind-long-kicks",
        "status": "idea; timely pregame wind trigger unresolved",
        "exploratory_screen": gate,
        "definition": {"seasons": list(PINS), "season_types": "regular and postseason",
            "eligible_drive": "First valid non-kickoff snap with ball at opponent 40–25 inclusive; subsequent >=50-yard kicks in the same game/fixed_drive/offense",
            "exposure": "Retrospective recorded game wind >=15 mph; roof outdoors/open",
            "control": "Recorded game wind 0–<15 mph; standardized within season and roof using exposed-drive weights",
            "minimum_exposed_drives": 200, "minimum_relative_reduction_in_long_makes": .20,
            "secondary_diagnostics": "All-distance attempts and makes; no additional pass gate",
            "uncertainty": "2000 game-cluster bootstrap draws within exposure × season × roof, seed 20260913; descriptive, uncorrected for hypothesis selection"},
        "sources": sources, "coverage": coverage, "result": result,
        "limitations": [
            "Wind and roof are retrospective game metadata, not issue-stamped forecasts or proof of prequote availability.",
            "Season and roof do not adjust teams, kickers, stadium geometry, precipitation, temperature, field position, score state or month.",
            "Drive eligibility conditions on reaching a field-position band that weather itself may affect; this is a per-eligible-drive screen, not a causal effect or full-game kicker-prop probability.",
            "A drive that skips the 40–25 band between snaps is excluded, as is one starting deeper and never returning to that band.",
            "All five historical seasons are now inspected exploration for this card, not an untouched confirmatory holdout.",
            "No FanDuel kicker quotes, settlement probabilities, prices, CLV or returns are present."
        ],
        "attribution": "Derived from nflverse/nflfastR play-by-play, nflverse-data release pbp; source repository CC BY 4.0. Raw files remain ignored.",
    }
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    hi, lo = result["high"], result["low"]
    rows = []
    for metric in METRICS:
        item = result["standardized"][metric]
        interval = item["relative_reduction_game_cluster_95pct_interval"]
        rows.append(f"| {metric.replace('_', ' ')} | {hi[metric]}/{hi['drives']} ({item['high_rate']:.3%}) | {item['season_roof_standardized_low_rate']:.3%} | {item['relative_reduction']:.1%} [{interval[0]:.1%}, {interval[1]:.1%}] |")
    text = f"""# NFL wind and long kicks: September 13, 2026

**{gate.capitalize()}.** The fixed >=15 mph screen has {hi['drives']:,} exposed eligible drives across {hi['games']} games. The season/roof-standardized reduction in successful >=50-yard kicks per eligible drive is {effect:.1%}; the card requires at least 200 exposed drives and a 20% reduction. **The card remains unresolved for its timely pregame trigger, and there is no book-side edge evidence.**

The sample was fixed before kick outcomes were read: complete 2021–2025 regular seasons and playoffs. The canceled 2022 Buffalo–Cincinnati game is excluded if present. A qualifying drive has a valid snap with the ball on the opponent's 40–25 yard lines, inclusive. Attempts and makes are counted separately after the first such snap, within the same `game_id`, `fixed_drive` and offense. Nullified plays and extra points are excluded. Kicks >=50 yards are the primary outcome; all-distance totals below are secondary diagnostics, not a replacement gate.

| Outcome per eligible drive | >=15 mph count/rate | <15 mph rate, season/roof standardized | Relative reduction [descriptive 95% interval] |
| --- | --- | --- | --- |
{chr(10).join(rows)}

Low-wind raw sample: {lo['drives']:,} drives across {lo['games']} games, {lo['long_attempts']} long attempts and {lo['long_makes']} long makes. Long-kick success conditional on trying is {hi['long_success_given_attempt']:.1%} in the exposed group and {lo['long_success_given_attempt']:.1%} in raw controls. This separates the decision to attempt from observed accuracy, without claiming either is causal. Standardization weights each season/roof control rate by exposed drives; {result['unmatched_high_drives']} exposed drives lack a same-season/roof comparison. The interval uses 2,000 bootstrap resamples of whole games within exposure/season/roof strata, seed 20260913. It is descriptive and uncorrected for hypothesis selection.

There are {coverage['completed_games']:,} completed games in the five inputs; {coverage['outdoor_or_open_games']:,} have an outdoor/open roof and {coverage['outdoor_or_open_missing_wind_games']} of those have no recorded wind. The weather-complete sample has {coverage['eligible_weather_games']} games; missing wind is not imputed. Exact season/roof counts, all aggregates and source hashes are in the [JSON report](nfl-wind-kicks-2026-09-13.json).

The [nflfastR source](https://nflfastr.com/) describes game-level weather metadata; it does not supply the weather forecast issue time required by this card. Roof state is also retrospective. Stadium, kicker, season timing and other weather can confound this comparison. Conditioning on reaching the 40–25 band may itself select on weather-sensitive offense; drives skipping that band between snaps do not enter. These rates do not directly price longest-field-goal or total-made-field-goal props.

No FanDuel prices were collected. The current provider catalog documents NFL made-field-goal and kicking-points markets, but does not document a longest-field-goal key; the long-distance result cannot silently become an all-distance pricing claim. A useful next step must establish issue-stamped wind/roof observations and exact available FanDuel kicker markets before testing price disagreement. Do not lower the 15 mph/20% cutoffs or call these inspected seasons a new holdout.

Run `python tools/explore_nfl_wind_kicks.py --download` from the repository. The script verifies the five SHA-256 pins before analysis. Data: [nflverse-data pbp release](https://github.com/nflverse/nflverse-data/releases/tag/pbp), derived from nflverse/nflfastR, [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md); raw files remain ignored. No model, odds backtest or alert was enabled.
"""
    OUT.with_suffix(".md").write_text(text)
    print(json.dumps({"screen": gate, "high": hi, "low": lo, "standardized": result["standardized"], "coverage": coverage}, indent=2))


if __name__ == "__main__":
    main()
