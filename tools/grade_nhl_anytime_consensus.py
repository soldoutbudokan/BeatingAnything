#!/usr/bin/env python3
"""Grade the frozen NHL anytime-scorer consensus screen; never reselect or renormalize."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-anytime-consensus-2026-09-28"
FREEZE = ROOT / "reports/nhl-anytime-consensus-freeze-2026-09-28.json"
REPORT = ROOT / "reports/nhl-anytime-consensus-results-2026-09-28.json"
MARKDOWN = REPORT.with_suffix(".md")
BOX = ROOT / "data/raw/nhl-shot-archive-2026-09-26/outcomes/player_box_2025.csv"
BOX_PIN = "511f58b09996be6165c7ad2a0f475ac029f0206653ce4e11665e1ff8088516b0"
PERIODS = ["early_nov_dec", "later_january"]
BOOTSTRAPS = 10_000
SEED = 970028


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


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
    """Return status, scored label (1 = at least one goal), reason."""
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
    return "settled", int(goals >= 1), "valid_positive_time"


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
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -label * np.log(p) - (1 - label) * np.log1p(-p)


def accuracy(frame, rng, reference, fanduel):
    known = frame[frame.status.eq("settled")].copy()
    y = known.y_scored.to_numpy(dtype=float)
    p, q = known[reference].to_numpy(dtype=float), known[fanduel].to_numpy(dtype=float)
    known["reference_log_loss"], known["fanduel_log_loss"] = binary_loss(p, y), binary_loss(q, y)
    known["reference_brier"], known["fanduel_brier"] = (p - y) ** 2, (q - y) ** 2
    columns = ["reference_log_loss", "fanduel_log_loss", "reference_brier", "fanduel_brier"]
    games = known.groupby("game_id")[columns].mean()
    result = {"graded_rows": int(len(known)), "graded_games": int(len(games))}
    if len(games):
        log_gain = (games.fanduel_log_loss - games.reference_log_loss).to_numpy()
        brier_gain = (games.fanduel_brier - games.reference_brier).to_numpy()
        indices = rng.integers(0, len(games), size=(BOOTSTRAPS, len(games)))
        result.update({**{c: float(games[c].mean()) for c in columns},
                       "log_loss_gain_fanduel_minus_reference": float(log_gain.mean()),
                       "brier_gain_fanduel_minus_reference": float(brier_gain.mean()),
                       "log_loss_gain_ci95": interval(log_gain[indices].mean(axis=1)),
                       "brier_gain_ci95": interval(brier_gain[indices].mean(axis=1))})
    return result


def returns(frame, rng, mask_column):
    selected = frame[frame[mask_column]].copy()
    known = selected[selected.status.eq("settled")]
    wins = int(known.won.sum())
    result = {"selections": int(len(selected)), "settled": int(len(known)), "wins": wins,
              "losses": int(len(known) - wins), "voids": int(selected.status.eq("void").sum()),
              "unknowns": int(selected.status.eq("unknown").sum()),
              "selected_games": int(selected.game_id.nunique()), "selected_players": int(selected.player_id.nunique())}
    if len(selected):
        count = selected.groupby(["player_id", "player"]).size().sort_values(ascending=False)
        result["player_concentration"] = {
            "largest_selection_share": float(count.max() / len(selected)),
            "hhi": float(((count / len(selected)) ** 2).sum()),
            "top_ten": [{"player_id": int(k[0]), "player": k[1], "selections": int(n)} for k, n in count.head(10).items()]}
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
        draws = np.divide(numerators, resampled_stakes, out=np.full(BOOTSTRAPS, np.nan), where=resampled_stakes > 0)
        result[convention + "_roi_ci95"] = interval(draws)
        result[convention + "_drawdown_settled_units"] = drawdown(known[column].to_numpy())
        unknown = selected[selected.status.eq("unknown")]
        low = profit - len(unknown)
        high = profit + float((unknown.fd_decimal - 1).sum()) * (1 if convention == "raw" else .98)
        denominator = len(known) + len(unknown)
        result[convention + "_unknown_settlement_bounds"] = {
            "lower_profit_units": low, "upper_profit_units": high,
            "lower_roi": low / denominator if denominator else None, "upper_roi": high / denominator if denominator else None}
    return result


def summarize(frame, rng):
    stamps = pd.to_datetime(frame.boundary, utc=True).dt.isocalendar()
    return {"rows": int(len(frame)), "games": int(frame.game_id.nunique()), "players": int(frame.player_id.nunique()),
            "calendar_weeks_utc": int(stamps[["year", "week"]].drop_duplicates().shape[0]),
            "target_statuses": frame.status.value_counts().to_dict(),
            "target_reasons": frame.target_reason.value_counts().to_dict(),
            "accuracy_power": accuracy(frame, rng, "p_reference_power", "fd_p_power"),
            "accuracy_proportional": accuracy(frame, rng, "p_reference_proportional", "fd_p_proportional"),
            "returns_selected_one_per_game": returns(frame, rng, "selected"),
            "returns_all_qualifying_rows": returns(frame, rng, "qualifies")}


def main():
    output = RAW / "graded-rows.csv"
    if any(path.exists() for path in [REPORT, MARKDOWN, output]):
        raise FileExistsError("Preserve the original frozen grading outputs")
    frozen = json.loads(FREEZE.read_text())
    assert frozen["status"] == "frozen_before_target_grading", "Declared zero-selection stop: no target grading"
    for ref in [frozen["card"], frozen["tool"], frozen["rows_artifact"], frozen["event_status"]] + frozen["metadata_inputs"] + frozen["sources"]:
        assert source(ROOT / ref["path"])["sha256"] == ref["sha256"], ref["path"]
    assert source(BOX)["sha256"] == BOX_PIN
    frame = pd.read_csv(ROOT / frozen["rows_artifact"]["path"], keep_default_na=False)
    for column in ("selected", "qualifies", "within_decimal_range"):
        frame[column] = frame[column].astype(str).eq("True")
    assert not frame.duplicated(["game_id", "player_id"]).any()
    assert set(frame.period) == set(PERIODS)
    assert int(frame.selected.sum()) == frozen["all"]["selections"] > 0
    assert not frame.loc[frame.selected, "game_id"].duplicated().any()
    assert (frame.reference_books >= 3).all()
    frame = frame.sort_values(["entry", "game_id", "player_id"]).reset_index(drop=True)
    # First target-label join happens here, after verifying immutable rows.
    boxes = pd.read_csv(BOX, usecols=["game_id", "player_id", "toi", "goals", "shots_on_goal"])
    groups = {key: group for key, group in boxes.groupby(["game_id", "player_id"])}
    grades = [target_grade(groups.get((row.game_id, row.player_id), boxes.iloc[:0])) for row in frame.itertuples()]
    frame[["status", "y_scored", "target_reason"]] = pd.DataFrame(grades, index=frame.index)
    known = frame.status.eq("settled")
    frame["won"] = np.nan
    frame.loc[known, "won"] = frame.loc[known, "y_scored"].eq(1).astype(int)
    for column, multiplier in [("raw_profit", 1.), ("haircut_profit", .98)]:
        frame[column] = np.nan
        frame.loc[known, column] = np.where(frame.loc[known, "won"].eq(1), multiplier * (frame.loc[known, "fd_decimal"] - 1), -1.)
        frame.loc[frame.status.eq("void"), column] = 0.
    rng = np.random.default_rng(SEED)
    summaries = {"all": summarize(frame, rng)}
    summaries.update({period: summarize(frame[frame.period.eq(period)], rng) for period in PERIODS})
    late = summaries["later_january"]["accuracy_power"].get("log_loss_gain_ci95", {}).get("lower")
    gates = {"later_reference_log_loss_gain_lower_above_zero": late is not None and late > 0}
    for period in PERIODS:
        value = summaries[period]["returns_selected_one_per_game"]
        gates[period + "_100_settled_selected_games"] = value["settled"] >= 100
        gates[period + "_positive_haircut_roi"] = value["haircut_roi"] is not None and value["haircut_roi"] > 0
        low = value["haircut_roi_ci95"]["lower"]
        gates[period + "_positive_roi_lower"] = low is not None and low > 0
    passes = all(gates.values())
    frame.to_csv(output, index=False)
    data = {"status": "exploratory_lead_unconfirmed" if passes else "fixed_screen_closed_no_demonstrated_edge",
            "graded_at_utc": datetime.now(timezone.utc).isoformat(), "freeze": source(FREEZE), "tool": source(Path(__file__)),
            "target_source": {"path": str(BOX.relative_to(ROOT)), "sha256": BOX_PIN}, "graded_rows": source(output),
            "bootstrap": {"draws": BOOTSTRAPS, "seed": SEED, "unit": "game"},
            "summaries": summaries, "declared_gates": gates, "passes_exploratory_gates": passes,
            "limitations": ["Previously inspected archive; no untouched or prospective confirmation.",
                            "Game resampling does not resolve shared-player, weekly or model-search dependence.",
                            "Original receipt, accepted execution and jurisdiction-specific contract terms unverified.",
                            "Reference books share platforms and feeds; the consensus is not an independent forecast.",
                            "No parameter, reference set, threshold, period or subgroup changed after outcomes."]}
    REPORT.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    lines = ["# NHL anytime-scorer normalized consensus: frozen result", "", f"Status: **{data['status']}**.", "",
             "All rows and selections were frozen before this target-label join. Gains are FanDuel loss minus reference loss under the power normalization; positive favors the consensus.", "",
             "| Period | Rows / games | Log-loss gain (95% game interval) | Settled bets W–L | Haircut ROI (95% game interval) | All qualifying rows W–L, haircut ROI |",
             "|---|---:|---:|---:|---:|---:|"]
    fmt = lambda x: "n/a" if x is None else f"{x:.6f}"
    percent = lambda x: "n/a" if x is None else f"{x:.2%}"
    for group, summary in summaries.items():
        acc, bets, every = summary["accuracy_power"], summary["returns_selected_one_per_game"], summary["returns_all_qualifying_rows"]
        ci, ri = acc.get("log_loss_gain_ci95", {}), bets["haircut_roi_ci95"]
        lines.append(f"| {group} | {summary['rows']} / {summary['games']} | {fmt(acc.get('log_loss_gain_fanduel_minus_reference'))} ({fmt(ci.get('lower'))}, {fmt(ci.get('upper'))}) | "
                     f"{bets['settled']}: {bets['wins']}–{bets['losses']} | {percent(bets['haircut_roi'])} ({percent(ri['lower'])}, {percent(ri['upper'])}) | "
                     f"{every['settled']}: {every['wins']}–{every['losses']}, {percent(every['haircut_roi'])} |")
    lines += ["", "The declared exploratory gates " + ("pass, but independent confirmation is still required." if passes else "fail; this exact screen is closed without retuning."), "",
              "The JSON retains Brier scores, the proportional-method comparison, raw and haircut returns, unknown/void counts and settlement bounds, drawdowns, player concentration, week counts and every gate.", "",
              "Frozen screen: [card](../docs/hypotheses/hockey-anytime-scorer-normalized-consensus.md), [freeze](nhl-anytime-consensus-freeze-2026-09-28.md). Full results: [JSON](nhl-anytime-consensus-results-2026-09-28.json)."]
    MARKDOWN.write_text("\n".join(lines) + "\n")
    print(json.dumps({"status": data["status"], "gates": gates,
                      "periods": {g: {"accuracy": s["accuracy_power"], "returns": {k: v for k, v in s["returns_selected_one_per_game"].items() if k != "player_concentration"}}
                                  for g, s in summaries.items()}}, indent=2))


if __name__ == "__main__":
    main()
