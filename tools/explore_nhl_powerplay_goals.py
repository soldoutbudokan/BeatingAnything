"""Fixed prior-only power-play exposure adjustment for goal-0.5 prices."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-powerplay-goals-2026-09-26"
SPORT = ROOT / "data/raw/nhl-shot-archive-2026-09-26/outcomes"
CARD = ROOT / "docs/hypotheses/hockey-powerplay-goal-exposure.md"
REPORT = ROOT / "reports/nhl-powerplay-goals-2026-09-26.json"


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def verify(refs):
    for item in refs:
        assert source(ROOT / item["path"])["sha256"] == item["sha256"], item["path"]


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def untouched(*paths):
    if any(p.exists() for p in paths):
        raise FileExistsError("Preserve the original frozen experiment")


def seconds(value):
    match = re.fullmatch(r"(\d+):([0-5]\d)", str(value))
    return int(match[1]) * 60 + int(match[2]) if match else None


def integer(value):
    try:
        number = float(value)
        return int(number) if np.isfinite(number) and number >= 0 and number % 1 == 0 else None
    except (ValueError, TypeError):
        return None


def saves_shots(value):
    match = re.fullmatch(r"(\d+)/(\d+)", str(value))
    if not match or int(match[1]) > int(match[2]):
        return None
    return int(match[1]), int(match[2])


def goal_counts(frame):
    goals = frame.goals.map(integer)
    pp = frame.power_play_goals.map(integer)
    if goals.isna().any() or pp.isna().any() or (pp > goals).any():
        return None
    return int(goals.sum()), int(pp.sum())


def team_history(boxes):
    rows, rejected = [], []
    for (game_id, team), group in boxes[boxes.position.eq("G")].groupby(["game_id", "team_abbrev"]):
        pp_shots, appearing, issue = 0, 0, None
        for _, row in group.iterrows():
            toi = seconds(row.toi)
            parts = [saves_shots(row[c]) for c in ["even_strength_shots_against", "power_play_shots_against",
                                                   "shorthanded_shots_against"]]
            combined = saves_shots(row.save_shots_against)
            saves, shots = integer(row.saves), integer(row.shots_against)
            ga_parts = [integer(row[c]) for c in ["even_strength_goals_against", "power_play_goals_against",
                                                 "shorthanded_goals_against"]]
            ga = integer(row.goals_against)
            if toi is None or combined is None or None in parts or saves is None or shots is None or None in ga_parts or ga is None:
                issue = "missing_or_invalid_goalie_field"
                break
            if combined != (saves, shots) or tuple(sum(p[j] for p in parts) for j in [0, 1]) != combined:
                issue = "goalie_splits_do_not_reconcile"
                break
            if [p[1] - p[0] for p in parts] != ga_parts or shots - saves != ga or sum(ga_parts) != ga:
                issue = "goalie_splits_do_not_reconcile_to_goals_against"
                break
            if toi == 0 and shots != 0:
                issue = "zero_time_goalie_has_shots"
                break
            appearing += toi > 0
            pp_shots += parts[1][1]
        if not appearing and issue is None:
            issue = "no_appearing_goalie"
        if issue:
            rejected.append({"game_id": int(game_id), "team": team, "reason": issue})
        else:
            assert group.available.nunique() == 1
            rows.append({"game_id": int(game_id), "team": team, "available": group.available.iloc[0],
                         "pp_shots": pp_shots, "appearing_goalies": appearing})
    return pd.DataFrame(rows).sort_values(["available", "game_id", "team"]), rejected


def forecast():
    output, freeze = RAW / "forecasts.csv", RAW / "forecast-freeze.json"
    tracked_freeze = ROOT / "reports/nhl-powerplay-goals-freeze-2026-09-26.json"
    untouched(output, freeze, tracked_freeze)
    price_path = RAW / "price-entries.csv"
    coverage_path = ROOT / "reports/nhl-powerplay-goals-coverage-2026-09-26.json"
    coverage = json.loads(coverage_path.read_text())
    manifest_path = ROOT / "data/raw/nhl-shot-archive-2026-09-26/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    price_sources = [{"path": item["path"], "sha256": item["sha256"]} for item in manifest["files"]]
    price_pins = coverage["source_pins"] + [coverage["price_entries"]] + price_sources
    verify(price_pins)
    inventory_path = ROOT / "tools/inventory_nhl_powerplay_goals.py"
    assert source(inventory_path)["sha256"] == coverage["script_sha256"]
    prices = pd.read_csv(price_path)
    assert len(prices) and not prices.duplicated(["game_id", "player_id"]).any()
    assert prices.line.eq(.5).all()
    prices["entry_stamp"] = pd.to_datetime(prices.entry, utc=True)
    boxes = pd.concat([pd.read_csv(SPORT / f"player_box_{year}.csv") for year in [2024, 2025]], ignore_index=True)
    boxes = boxes[boxes.game_id.astype(str).str[4:6].eq("02")].copy()
    assert not boxes.duplicated(["game_id", "player_id"]).any()
    rosters = pd.concat([pd.read_csv(SPORT / f"rosters_{year}.csv", usecols=["player_id", "position_code"])
                        for year in [2024, 2025]], ignore_index=True)
    goalie_ids = set(rosters.loc[rosters.position_code.eq("G"), "player_id"])
    schedule_paths = [ROOT / "data/raw/nhl-shot-archive-2026-09-26/powerplay-feature-audit/schedule_2024_metadata.csv",
                      SPORT / "schedule_2025_metadata.csv"]
    schedule = pd.concat([pd.read_csv(p) for p in schedule_paths], ignore_index=True)
    schedule = schedule[schedule.game_type.eq("R") & schedule.game_state.isin(["OFF", "FINAL"])]
    assert not schedule.game_id.duplicated().any()
    availability = pd.Series((pd.to_datetime(schedule.game_time, utc=True) + pd.Timedelta(hours=72)).array,
                             index=schedule.game_id)
    boxes["available"] = boxes.game_id.map(availability)
    missing_history_ids = sorted(map(int, boxes.loc[boxes.available.isna(), "game_id"].unique()))
    boxes = boxes[boxes.available < prices.entry_stamp.max()].sort_values(["available", "game_id", "player_id"])
    unknown_position = boxes.position.fillna("").eq("")
    assert set(boxes.loc[unknown_position, "player_id"]).issubset(goalie_ids)
    boxes.loc[unknown_position, "position"] = "G"
    goalie_games, rejected = team_history(boxes)
    skaters = boxes[boxes.position.isin(["C", "L", "R", "D"])].copy()
    skaters["toi_seconds"] = skaters.toi.map(seconds)
    skaters = skaters[skaters.toi_seconds.gt(0)]
    league_players = skaters[skaters.game_id.astype(str).str.startswith("202302")]
    league_teams = goalie_games[goalie_games.game_id.astype(str).str.startswith("202302")]
    total_goals, total_pp_goals = goal_counts(league_players)
    assert total_goals > 0 and len(league_teams) > 0
    assert max(league_players.available.max(), league_teams.available.max()) < prices.entry_stamp.min()
    rho, league_mean = total_pp_goals / total_goals, float(league_teams.pp_shots.mean())
    assert 0 <= rho <= 1 and league_mean > 0
    player_history = {int(pid): g for pid, g in skaters.groupby("player_id")}
    opponent_history = {team: g for team, g in goalie_games.groupby("team")}
    records, attrition = [], Counter()
    for _, row in prices.iterrows():
        prior = player_history.get(int(row.player_id), skaters.iloc[:0])
        prior = prior[(prior.available < row.entry_stamp) & (prior.game_id != row.game_id)].tail(80)
        if len(prior) < 40:
            attrition["fewer_than_40_prior_player_appearances"] += 1
            continue
        counts = goal_counts(prior)
        if counts is None:
            attrition["invalid_prior_player_goal_counts"] += 1
            continue
        team = prior.team_abbrev.iloc[-1]
        if team not in [row.home_team_abbr, row.away_team_abbr]:
            attrition["latest_prior_player_team_not_in_fixture"] += 1
            continue
        opponent = row.away_team_abbr if team == row.home_team_abbr else row.home_team_abbr
        opp_prior = opponent_history.get(opponent, goalie_games.iloc[:0])
        opp_prior = opp_prior[(opp_prior.available < row.entry_stamp) & (opp_prior.game_id != row.game_id)].tail(40)
        if len(opp_prior) < 20:
            attrition["fewer_than_20_prior_opponent_games"] += 1
            continue
        goals, pp_goals = counts
        fraction = (pp_goals + 10 * rho) / (goals + 10)
        ratio = (float(opp_prior.pp_shots.sum()) + 40 * league_mean) / ((len(opp_prior) + 40) * league_mean)
        scale = (1 - fraction) + fraction * ratio
        q = (1 / row.under_decimal) / (1 / row.under_decimal + 1 / row.over_decimal)
        assert abs(q - row.q_under) < 1e-15 and 0 < q < 1
        probability = q if ratio == 1 else q ** scale
        latest = max(prior.available.max(), opp_prior.available.max())
        assert latest < row.entry_stamp
        records.append({**row.drop(labels=["entry_stamp"]).to_dict(), "prior_team": team, "opponent": opponent,
                        "prior_player_games": len(prior), "prior_player_goals": goals, "prior_player_pp_goals": pp_goals,
                        "prior_player_ids": json.dumps(prior.game_id.astype(int).tolist(), separators=(",", ":")),
                        "prior_opponent_games": len(opp_prior), "prior_opponent_pp_shots": int(opp_prior.pp_shots.sum()),
                        "prior_opponent_ids": json.dumps(opp_prior.game_id.astype(int).tolist(), separators=(",", ":")),
                        "latest_prior_available": latest.isoformat(), "pp_fraction": fraction,
                        "opponent_ratio": ratio, "goal_intensity_scale": scale, "p_under": probability})
    frame = pd.DataFrame(records)
    assert len(frame) and not frame.duplicated(["game_id", "player_id"]).any()
    frame["ev_under"] = frame.p_under * (1 + .98 * (frame.under_decimal - 1)) - 1
    frame["ev_over"] = (1 - frame.p_under) * (1 + .98 * (frame.over_decimal - 1)) - 1
    frame["selected_side"] = ""
    for _, group in frame.groupby("game_id"):
        candidates = [(-row["ev_" + side.lower()], row.player, side, idx)
                      for idx, row in group.iterrows() for side in ["Over", "Under"]
                      if 1.2 <= row[side.lower() + "_decimal"] <= 6 and row["ev_" + side.lower()] >= .03]
        if candidates:
            _, _, side, idx = sorted(candidates)[0]
            frame.loc[idx, "selected_side"] = side
    frame = frame.sort_values(["entry", "game_id", "player_id"])
    frame.to_csv(output, index=False)
    reject_path = RAW / "prior-team-game-rejections.json"
    dump(reject_path, rejected)
    sources = price_pins + [source(coverage_path), source(inventory_path), source(CARD), source(Path(__file__)),
                           *[source(p) for p in schedule_paths],
                           *[source(SPORT / f"player_box_{year}.csv") for year in [2024, 2025]]]
    data = {"phase": "frozen_prior_only_forecasts_before_target_grading", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "league_baseline": {"season": "2023-24_REG", "skater_goals": total_goals, "skater_pp_goals": total_pp_goals,
                                "rho": rho, "team_games": len(league_teams), "mean_pp_shots": league_mean},
            "price_rows": len(prices), "forecasts": len(frame), "games": int(frame.game_id.nunique()),
            "period_forecasts": frame.period.value_counts().to_dict(), "selections": int(frame.selected_side.ne("").sum()),
            "selection_sides": frame.loc[frame.selected_side.ne(""), "selected_side"].value_counts().to_dict(),
            "best_after_cost_ev": float(frame[["ev_under", "ev_over"]].max().max()), "attrition": dict(attrition),
            "history_game_ids_without_regular_schedule": missing_history_ids,
            "prior_team_game_rejection_count": len(rejected), "rejections": source(reject_path),
            "sources": sources, "forecast": source(output)}
    dump(freeze, data)
    dump(tracked_freeze, data)
    print(json.dumps({k: v for k, v in data.items() if k not in ["sources", "forecast"]}, indent=2))


def interval(frame, col, games):
    universe = sorted(set(games))
    if frame.empty:
        return {"observations": 0, "games_in_universe": len(universe), "mean": None, "game_bootstrap_95": None}
    groups = frame.groupby("game_id")[col].agg(["sum", "count"]).reindex(universe, fill_value=0)
    ix = np.random.default_rng(1729).integers(len(groups), size=(10000, len(groups)))
    numerator = groups["sum"].to_numpy()[ix].sum(1)
    denominator = groups["count"].to_numpy()[ix].sum(1)
    valid = denominator > 0
    return {"observations": len(frame), "games_in_universe": len(universe), "mean": float(frame[col].mean()),
            "game_bootstrap_95": np.quantile(numerator[valid] / denominator[valid], [.025, .975]).tolist(),
            "zero_stake_or_label_resamples": int((~valid).sum())}


def summarize(frame):
    known = frame[frame.settlement.eq("graded")].copy()
    y = known.goals.eq(0).astype(float)
    for col in ["q_under", "p_under"]:
        p = known[col]
        known[col + "_loss"] = -(y * np.log(p) + (1 - y) * np.log1p(-p))
        known[col + "_brier"] = (p - y) ** 2
    known["loss_change"] = known.p_under_loss - known.q_under_loss
    known["brier_change"] = known.p_under_brier - known.q_under_brier
    selected = frame[frame.selected_side.fillna("").ne("")]
    settled, unknown = selected[selected.profit.notna()], selected[selected.profit.isna()]
    n, profit = len(selected), float(settled.profit.sum())
    upper = sum(.98 * (row[row.selected_side.lower() + "_decimal"] - 1) for _, row in unknown.iterrows())
    return {"forecasts": len(frame), "games": int(frame.game_id.nunique()), "graded": len(known),
            "settlements": frame.settlement.value_counts().to_dict(),
            "market_log_loss": float(known.q_under_loss.mean()) if len(known) else None,
            "model_log_loss": float(known.p_under_loss.mean()) if len(known) else None,
            "loss_change": interval(known, "loss_change", frame.game_id),
            "brier_change": interval(known, "brier_change", frame.game_id),
            "selections": n, "selection_statuses": selected.settlement.value_counts().to_dict(),
            "selected_wins": int(settled.profit.gt(0).sum()), "selected_losses": int(settled.profit.lt(0).sum()),
            "selected_units": profit if len(settled) else None, "selected_roi": interval(settled, "profit", frame.game_id),
            "full_cohort_roi_bounds": [(profit - len(unknown)) / n, (profit + upper) / n] if n else None}


def grade():
    freeze_path, output = RAW / "forecast-freeze.json", RAW / "graded.csv"
    untouched(output, REPORT)
    frozen = json.loads(freeze_path.read_text())
    verify(frozen["sources"] + [frozen["forecast"], frozen["rejections"]])
    if frozen["selections"] == 0:
        raise ValueError("Declared no-bet closure: preserve target outcomes")
    frame = pd.read_csv(RAW / "forecasts.csv")
    boxes = pd.read_csv(SPORT / "player_box_2025.csv", usecols=["game_id", "player_id", "goals", "toi"])
    frame = frame.merge(boxes, on=["game_id", "player_id"], how="left", validate="one_to_one")
    frame["settlement"] = "unknown_no_valid_box_or_participation"
    counts, toi = frame.goals.map(integer), frame.toi.map(seconds)
    frame.loc[counts.notna() & toi.gt(0), "settlement"] = "graded"
    frame.loc[counts.eq(0) & toi.eq(0), "settlement"] = "void_zero_toi"
    frame["profit"] = np.nan
    for idx, row in frame[frame.selected_side.notna()].iterrows():
        if row.settlement == "void_zero_toi":
            frame.loc[idx, "profit"] = 0.
        elif row.settlement == "graded":
            win = row.goals == 0 if row.selected_side == "Under" else row.goals > 0
            frame.loc[idx, "profit"] = .98 * (row[row.selected_side.lower() + "_decimal"] - 1) if win else -1.
    frame.to_csv(output, index=False)
    report = {"status": "completed exploratory fixed power-play exposure test; no independent holdout claim",
              "frozen_at_utc": frozen["frozen_at_utc"], "graded_at_utc": datetime.now(timezone.utc).isoformat(),
              "freeze": source(freeze_path), "graded": source(output), "pooled": summarize(frame),
              "periods": {key: summarize(g) for key, g in frame.groupby("period")}}
    dump(REPORT, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["forecast", "grade"], required=True)
    args = parser.parse_args()
    {"forecast": forecast, "grade": grade}[args.phase]()
