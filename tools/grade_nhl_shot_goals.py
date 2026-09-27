"""Grade only already-frozen NHL shot-to-goal forecasts; never refit/select."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-shot-goal-2026-09-26"
FREEZE = ROOT / "reports/nhl-shot-goal-forecast-freeze-2026-09-26.json"
REPORT = ROOT / "reports/nhl-shot-goal-results-2026-09-26.json"
MARKDOWN = REPORT.with_suffix(".md")
PERIODS = ["early_nov_dec", "later_january"]
BOOTSTRAPS = 10_000
SEED = 970026


def source(path):
    return {"path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def verify(ref):
    assert source(ROOT / ref["path"])["sha256"] == ref["sha256"], ref["path"]


def integer(value):
    try:
        number = float(value)
        return int(number) if np.isfinite(number) and number >= 0 and number % 1 == 0 else None
    except (ValueError, TypeError):
        return None


def seconds(value):
    match = re.fullmatch(r"(\d+):([0-5]\d)", str(value))
    return int(match[1]) * 60 + int(match[2]) if match else None


def target_grade(rows):
    """Return status, Under label, reason; unknowns never disappear."""
    if len(rows) != 1:
        return "unknown", None, "absent_target" if not len(rows) else "duplicate_target"
    row = rows.iloc[0]
    toi, goals, shots = seconds(row.toi), integer(row.goals), integer(row.shots_on_goal)
    if toi is None or goals is None or shots is None or goals > shots:
        return "unknown", None, "invalid_target_counts_or_time"
    if toi == 0:
        if goals == 0 and shots == 0:
            return "void", None, "named_zero_time_zero_counts"
        return "unknown", None, "zero_time_with_nonzero_counts"
    return "settled", int(goals == 0), "valid_positive_time"


def interval(values):
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return {"lower": float(np.quantile(finite, .025)) if len(finite) else None,
            "upper": float(np.quantile(finite, .975)) if len(finite) else None,
            "defined_draws": int(len(finite)), "total_draws": BOOTSTRAPS}


def drawdown(profits):
    running = np.r_[0., np.cumsum(profits)]
    return float(np.max(np.maximum.accumulate(running) - running))


def binary_loss(p, label):
    return -label * np.log(p) - (1 - label) * np.log1p(-p)


def paired_losses(frame, rng):
    known = frame[frame.status.eq("settled")].copy()
    y = known.y_under.to_numpy(dtype=float)
    p, q = known.p_under.to_numpy(dtype=float), known.goal_q_under.to_numpy(dtype=float)
    known["model_log_loss"] = binary_loss(p, y)
    known["market_log_loss"] = binary_loss(q, y)
    known["model_brier"] = (p - y) ** 2
    known["market_brier"] = (q - y) ** 2
    columns = ["model_log_loss", "market_log_loss", "model_brier", "market_brier"]
    games = known.groupby("game_id")[columns].mean()
    log_gain = (games.market_log_loss - games.model_log_loss).to_numpy()
    brier_gain = (games.market_brier - games.model_brier).to_numpy()
    result = {"graded_forecasts": int(len(known)), "graded_games": int(len(games))}
    if len(games):
        indices = rng.integers(0, len(games), size=(BOOTSTRAPS, len(games)))
        result.update({**{c: float(games[c].mean()) for c in columns},
                       "log_loss_gain_market_minus_model": float(log_gain.mean()),
                       "brier_gain_market_minus_model": float(brier_gain.mean()),
                       "log_loss_gain_ci95": interval(log_gain[indices].mean(axis=1)),
                       "brier_gain_ci95": interval(brier_gain[indices].mean(axis=1))})
    # Keep unknown forecasts in the full nonvoid denominator. Bound each label
    # separately; positive gain always means the new model has lower loss.
    nonvoid = frame[~frame.status.eq("void")].copy()
    if not len(nonvoid):
        return result
    p, q = nonvoid.p_under.to_numpy(), nonvoid.goal_q_under.to_numpy()
    y = nonvoid.y_under.to_numpy(dtype=float)
    unknown = nonvoid.status.eq("unknown").to_numpy()
    for metric in ["log_loss", "brier"]:
        gain0 = binary_loss(q, 0) - binary_loss(p, 0) if metric == "log_loss" else q*q - p*p
        gain1 = binary_loss(q, 1) - binary_loss(p, 1) if metric == "log_loss" else (q-1)**2 - (p-1)**2
        known_gain = np.where(y == 1, gain1, gain0)
        nonvoid["low"] = np.where(unknown, np.minimum(gain0, gain1), known_gain)
        nonvoid["high"] = np.where(unknown, np.maximum(gain0, gain1), known_gain)
        by_game = nonvoid.groupby("game_id")[["low", "high"]].mean()
        result[metric + "_gain_full_nonvoid_unknown_label_bounds"] = {
            "lower": float(by_game.low.mean()), "upper": float(by_game.high.mean()),
            "forecasts": int(len(nonvoid)), "games": int(len(by_game))}
    return result


def returns(frame, rng):
    selected = frame[frame.selected_side.ne("")].copy()
    assert not selected.game_id.duplicated().any()
    known = selected[selected.status.eq("settled")]
    wins = int(known.won.sum())
    result = {"selections": int(len(selected)), "settled": int(len(known)),
              "wins": wins, "losses": int(len(known) - wins),
              "voids": int(selected.status.eq("void").sum()),
              "unknowns": int(selected.status.eq("unknown").sum()),
              "selected_games": int(selected.game_id.nunique()),
              "selected_players": int(selected.player_id.nunique()),
              "selection_sides": selected.selected_side.value_counts().to_dict()}
    count = selected.groupby(["player_id", "player"]).size().sort_values(ascending=False)
    result["player_concentration"] = {
        "largest_selection_share": float(count.max() / len(selected)) if len(selected) else None,
        "hhi": float(((count / len(selected)) ** 2).sum()) if len(selected) else None,
        "top_ten": [{"player_id": int(key[0]), "player": key[1], "selections": int(n)}
                    for key, n in count.head(10).items()]}
    # The bootstrap universe includes every forecast game, including games that
    # produced no selection, voids, or unknowns. ROI is profit / settled stake.
    games = sorted(frame.game_id.unique())
    indices = rng.integers(0, len(games), size=(BOOTSTRAPS, len(games)))
    stakes = known.groupby("game_id").size().reindex(games, fill_value=0).to_numpy()
    resampled_stakes = stakes[indices].sum(axis=1)
    for convention in ["raw", "haircut"]:
        column = convention + "_profit"
        profit = float(known[column].sum())
        result[convention + "_profit_units"] = profit
        result[convention + "_roi"] = profit / len(known) if len(known) else None
        game_profits = known.groupby("game_id")[column].sum().reindex(games, fill_value=0).to_numpy()
        numerators = game_profits[indices].sum(axis=1)
        draws = np.divide(numerators, resampled_stakes, out=np.full(BOOTSTRAPS, np.nan),
                          where=resampled_stakes > 0)
        result[convention + "_roi_ci95"] = interval(draws)
        result[convention + "_drawdown_settled_units"] = drawdown(known[column].to_numpy())
        unknown = selected[selected.status.eq("unknown")]
        low = profit - len(unknown)
        wins_payoff = unknown.selected_decimal - 1
        high = profit + float(wins_payoff.sum()) * (1 if convention == "raw" else .98)
        denominator = len(known) + len(unknown)
        result[convention + "_unknown_settlement_bounds"] = {
            "lower_profit_units": low, "upper_profit_units": high,
            "lower_roi": low / denominator if denominator else None,
            "upper_roi": high / denominator if denominator else None,
            "stake_denominator": denominator,
            "assumption": "All unknown selections settled as losses / wins; named voids excluded."}
        low_sequence = selected[column].fillna(0).to_numpy()
        high_sequence = low_sequence.copy()
        mask = selected.status.eq("unknown").to_numpy()
        low_sequence[mask] = -1
        high_sequence[mask] = (selected.loc[mask, "selected_decimal"].to_numpy() - 1) * (1 if convention == "raw" else .98)
        result[convention + "_drawdown_unknown_scenarios"] = {
            "all_unknown_losses": drawdown(low_sequence),
            "all_unknown_wins": drawdown(high_sequence)}
    return result


def summarize(frame, rng):
    stamps = pd.to_datetime(frame.boundary, utc=True).dt.isocalendar()
    return {"forecasts": int(len(frame)), "games": int(frame.game_id.nunique()),
            "players": int(frame.player_id.nunique()),
            "calendar_weeks_utc": int(stamps[["year", "week"]].drop_duplicates().shape[0]),
            "target_statuses": frame.status.value_counts().to_dict(),
            "target_reasons": frame.target_reason.value_counts().to_dict(),
            "forecast_accuracy": paired_losses(frame, rng), "returns": returns(frame, rng)}


def main():
    output = RAW / "graded-forecasts.csv"
    if any(path.exists() for path in [REPORT, MARKDOWN, output]):
        raise FileExistsError("Preserve the original frozen grading outputs")
    frozen = json.loads(FREEZE.read_text())
    assert frozen["both_periods_pass"]
    assert frozen["selections"] > 0, "Declared zero-selection stop: no target grading"
    for ref in frozen["sources"] + [frozen["forecast"]]:
        verify(ref)
    frame = pd.read_csv(ROOT / frozen["forecast"]["path"], keep_default_na=False)
    assert not frame.duplicated(["game_id", "player_id"]).any()
    assert set(frame.period) == set(PERIODS)
    assert all(frame.loc[frame.period.eq(period), "game_id"].nunique() >= 100 for period in PERIODS)
    assert frame.selected_side.isin(["", "Over", "Under"]).all()
    assert int(frame.selected_side.ne("").sum()) == frozen["selections"]
    assert ((frame.p_under > 0) & (frame.p_under < 1)).all()
    assert ((frame.goal_q_under > 0) & (frame.goal_q_under < 1)).all()
    assert not frame.loc[frame.selected_side.ne(""), "game_id"].duplicated().any()
    frame = frame.sort_values(["entry", "game_id", "player_id"]).reset_index(drop=True)
    sport = ROOT / "data/raw/nhl-shot-archive-2026-09-26/outcomes"
    paths = [sport / f"player_box_{year}.csv" for year in [2024, 2025]]
    source_pins = {ref["path"]: ref["sha256"] for ref in frozen["sources"]}
    for path in paths:
        assert source_pins[str(path.relative_to(ROOT))] == source(path)["sha256"]
    # First target-label join happens here, after verifying immutable forecasts.
    boxes = pd.concat([pd.read_csv(path, usecols=["game_id", "player_id", "toi", "goals", "shots_on_goal"])
                       for path in paths], ignore_index=True)
    target_groups = {key: group for key, group in boxes.groupby(["game_id", "player_id"])}
    grades = [target_grade(target_groups.get((row.game_id, row.player_id), boxes.iloc[:0]))
              for row in frame.itertuples()]
    frame[["status", "y_under", "target_reason"]] = pd.DataFrame(grades, index=frame.index)
    frame["selected_decimal"] = np.where(frame.selected_side.eq("Under"), frame.goal_under_decimal,
                                           np.where(frame.selected_side.eq("Over"), frame.goal_over_decimal, np.nan))
    selected = frame.selected_side.ne("")
    known = selected & frame.status.eq("settled")
    frame["won"] = np.nan
    frame.loc[known, "won"] = (frame.loc[known, "y_under"].eq(1)
                                == frame.loc[known, "selected_side"].eq("Under")).astype(int)
    for column, multiplier in [("raw_profit", 1.), ("haircut_profit", .98)]:
        frame[column] = np.nan
        frame.loc[known, column] = np.where(frame.loc[known, "won"].eq(1),
                                            multiplier * (frame.loc[known, "selected_decimal"] - 1), -1.)
        frame.loc[selected & frame.status.eq("void"), column] = 0.
    rng = np.random.default_rng(SEED)
    summaries = {"all": summarize(frame, rng)}
    summaries.update({period: summarize(frame[frame.period.eq(period)], rng) for period in PERIODS})
    late_accuracy = summaries["later_january"]["forecast_accuracy"]
    late_gain = late_accuracy.get("log_loss_gain_ci95", {}).get("lower")
    gates = {"later_log_loss_gain_lower_above_zero": late_gain is not None and late_gain > 0}
    for period in PERIODS:
        value = summaries[period]["returns"]
        gates[period + "_100_settled_selected_games"] = value["settled"] >= 100
        gates[period + "_positive_haircut_roi"] = value["haircut_roi"] is not None and value["haircut_roi"] > 0
        low = value["haircut_roi_ci95"]["lower"]
        gates[period + "_positive_roi_lower"] = low is not None and low > 0
    passes = all(gates.values())
    frame.to_csv(output, index=False)
    data = {"status": "exploratory_lead_unconfirmed" if passes else "fixed_model_closed_no_demonstrated_edge",
            "graded_at_utc": datetime.now(timezone.utc).isoformat(),
            "freeze": source(FREEZE), "tool": source(Path(__file__)), "graded_forecasts": source(output),
            "bootstrap": {"draws": BOOTSTRAPS, "seed": SEED, "unit": "game",
                          "accuracy": "Mean within each graded game, then equal game weight; percentile interval.",
                          "roi": "Profit / settled stakes, resampling all forecast games including zero-selection games.",
                          "group_order": ["all"] + PERIODS},
            "summaries": summaries, "declared_gates": gates, "passes_exploratory_gates": passes,
            "limitations": ["Previously inspected archive; no untouched or prospective confirmation.",
                            "Game resampling does not resolve shared-player, weekly or model-search dependence.",
                            "Original receipt, accepted execution and jurisdiction-specific contract terms unverified.",
                            "Unknowns retained; complete-case accuracy and ROI are conditional.",
                            "No parameter, side, period, threshold or subgroup changed after outcomes."]}
    REPORT.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    lines = ["# NHL shot-to-goal model: frozen result", "", f"Status: **{data['status']}**.", "",
             "All forecasts and selections were frozen before this target-label join. Gains below are market loss minus model loss; positive favors the model.", "",
             "| Period | Forecasts / games | Log-loss gain (95% game interval) | Settled bets W–L | Haircut ROI (95% game interval) |",
             "|---|---:|---:|---:|---:|"]
    for group, summary in summaries.items():
        accuracy, bets = summary["forecast_accuracy"], summary["returns"]
        ci, ri = accuracy.get("log_loss_gain_ci95", {}), bets["haircut_roi_ci95"]
        fmt = lambda x: "n/a" if x is None else f"{x:.6f}"
        percent = lambda x: "n/a" if x is None else f"{x:.2%}"
        lines.append(f"| {group} | {summary['forecasts']} / {summary['games']} | {fmt(accuracy.get('log_loss_gain_market_minus_model'))} ({fmt(ci.get('lower'))}, {fmt(ci.get('upper'))}) | {bets['settled']}: {bets['wins']}–{bets['losses']} | {percent(bets['haircut_roi'])} ({percent(ri['lower'])}, {percent(ri['upper'])}) |")
    lines += ["", "The declared exploratory gates " + ("pass, but independent confirmation is still required." if passes else "fail; this exact model is closed without retuning."), "",
              "The JSON retains Brier scores, raw and haircut returns, unknown/void counts and settlement bounds, drawdowns, player concentration, week counts and every gate. Loss intervals give equal weight to games; return resampling includes games with no selections.", "",
              "This short archive was inspected by previous studies. The intervals do not correct repeated model searches or dependence across shared players and weeks. Historical quote clocks and assumed participation rules do not verify accepted execution or jurisdiction-specific terms. No wager, alert or schedule was enabled.", "",
              "Frozen model: [declaration](../docs/nhl-shot-to-goal-declaration-2026-09-26.md). Full results: [JSON](nhl-shot-goal-results-2026-09-26.json)."]
    MARKDOWN.write_text("\n".join(lines) + "\n")
    print(json.dumps({"status": data["status"], "gates": gates, "summaries": summaries}, indent=2))


if __name__ == "__main__":
    main()
