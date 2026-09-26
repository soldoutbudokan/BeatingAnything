"""Fixed >10-mph MOS-level correction; early fit then immutable later grading."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from explore_nfl_wind_revisions import (
    ROOT, RAW as PREVIOUS, dump, fit_beta, interval, load_totals, now, source,
    untouched, verify,
)

RAW = ROOT / "data/raw/nfl-absolute-wind-2026-09-26"
CARD = ROOT / "docs/hypotheses/football-absolute-forecast-wind.md"
REPORT = ROOT / "reports/nfl-absolute-wind-2026-09-26.json"


def metric_frame(frame):
    known = frame[frame.actual_total.notna()].copy()
    y = (known.actual_total < known.line).to_numpy(dtype=float)
    for col in ["q_under", "p_under"]:
        p = known[col].to_numpy()
        known[col + "_loss"] = -(y * np.log(p) + (1 - y) * np.log1p(-p))
        known[col + "_brier"] = (p - y) ** 2
    known["loss_change"] = known.p_under_loss - known.q_under_loss
    known["brier_change"] = known.p_under_brier - known.q_under_brier
    return known


def metrics(frame, weeks):
    known = metric_frame(frame)
    return {
        "forecasts": len(frame), "graded": len(known),
        "unknown": int(frame.actual_total.isna().sum()),
        "under_wins": int((known.actual_total < known.line).sum()),
        "market_log_loss": float(known.q_under_loss.mean()) if len(known) else None,
        "model_log_loss": float(known.p_under_loss.mean()) if len(known) else None,
        "paired_loss_change": interval(known, "loss_change", weeks),
        "paired_brier_change": interval(known, "brier_change", weeks),
    }


def forecast():
    RAW.mkdir(exist_ok=True)
    out, freeze = RAW / "forecasts.csv", RAW / "forecast-freeze.json"
    report_freeze = ROOT / "reports/nfl-absolute-wind-freeze-2026-09-26.json"
    untouched(out, freeze, report_freeze)
    prep_path = PREVIOUS / "weather-preparation.json"
    prep = json.loads(prep_path.read_text())
    verify(prep["sources"] + [prep["prepared"]])
    old_freeze_path = PREVIOUS / "wind-forecast-freeze.json"
    old_freeze = json.loads(old_freeze_path.read_text())
    verify(old_freeze["sources"] + [old_freeze["forecast"], old_freeze["preparation"]])
    frame = pd.read_csv(PREVIOUS / "weather-entries.csv")
    assert not frame.game_id.duplicated().any()
    assert np.allclose(frame.q_under, (1 / frame.under_decimal) /
                       (1 / frame.under_decimal + 1 / frame.over_decimal), atol=1e-15, rtol=0)
    frame["wind_mph"] = frame.new_wind_knots * 1.852 / 1.609344
    frame["x"] = frame.wind_mph.gt(10).astype(int)
    early = frame[frame.period.eq("train_weeks_1_8")].copy()
    later = frame[frame.period.eq("later_weeks_9_18")]
    assert len(later)
    early["available"] = pd.to_datetime(early.gameday, utc=True) + pd.Timedelta(hours=72)
    earliest = pd.to_datetime(later.captured_at_utc, utc=True).min()
    assert early.available.lt(earliest).all()
    labels_path = PREVIOUS / "early-training-labels.csv"
    labels = pd.read_csv(labels_path).set_index("game_id")
    assert set(labels.index) == set(early.game_id) and not labels.index.duplicated().any()
    early["actual_total"] = early.game_id.map(labels.actual_total)
    known = early[early.actual_total.notna()]
    if len(known) < 30 or not known.x.sum():
        raise ValueError("Insufficient calibration coverage under declaration")
    y = (known.actual_total < known.line).to_numpy(dtype=float)
    beta, gradient = fit_beta(known.q_under.to_numpy(), known.x.to_numpy(), y)
    frame["p_under"] = frame.q_under
    exposed = frame.x.eq(1)
    if beta:
        frame.loc[exposed, "p_under"] = expit(logit(frame.loc[exposed, "q_under"]) + beta)
    assert frame.loc[~exposed, "p_under"].equals(frame.loc[~exposed, "q_under"])
    frame["ev_under"] = frame.p_under * (1 + .98 * (frame.under_decimal - 1)) - 1
    frame["ev_over"] = (1 - frame.p_under) * (1 + .98 * (frame.over_decimal - 1)) - 1
    frame["selected_side"] = ""
    for idx, row in frame[frame.period.eq("later_weeks_9_18")].iterrows():
        candidates = [(-row["ev_" + side.lower()], side) for side in ["Over", "Under"]
                      if 1.2 <= row[side.lower() + "_decimal"] <= 6 and row["ev_" + side.lower()] >= .03]
        if candidates:
            frame.loc[idx, "selected_side"] = sorted(candidates)[0][1]
    early["p_under"] = early.game_id.map(frame.set_index("game_id").p_under)
    frame.to_csv(out, index=False)
    data = {
        "phase": "predictions_frozen_before_later_labels", "frozen_at_utc": now(),
        "beta": beta, "penalized_gradient_at_beta": gradient,
        "training_games": len(early), "training_graded": len(known),
        "training_high_wind": int(known.x.sum()),
        "training_metrics_in_sample_only": metrics(early, early.week),
        "training_high_wind_metrics_in_sample_only": metrics(early[early.x.eq(1)], early.week),
        "latest_training_availability": early.available.max().isoformat(),
        "earliest_later_entry": earliest.isoformat(), "later_forecasts": len(later),
        "later_high_wind": int(later.x.sum()),
        "later_selections": int(frame.selected_side.ne("").sum()),
        "sources": prep["sources"] + [prep["prepared"], source(prep_path),
                    source(old_freeze_path), source(labels_path), source(CARD), source(Path(__file__))],
        "forecast": source(out),
    }
    dump(freeze, data)
    dump(report_freeze, data)
    print(json.dumps({k: v for k, v in data.items() if k not in ["sources", "forecast"]}, indent=2))


def grade():
    freeze_path, out = RAW / "forecast-freeze.json", RAW / "later-graded.csv"
    untouched(out, REPORT)
    frozen = json.loads(freeze_path.read_text())
    verify(frozen["sources"] + [frozen["forecast"]])
    if frozen["beta"] == 0:
        raise ValueError("Identical forecasts: do not open later labels merely to grade zeros")
    frame = pd.read_csv(RAW / "forecasts.csv")
    frame = frame[frame.period.eq("later_weeks_9_18")].copy()
    frame["actual_total"] = frame.game_id.map(load_totals(set(frame.game_id)))
    assert frame.line.mod(1).eq(.5).all()
    frame["settlement"] = np.where(frame.actual_total.notna(), "graded", "unknown")
    frame["profit"] = np.nan
    selected = frame.selected_side.notna()
    for idx, row in frame[selected & frame.actual_total.notna()].iterrows():
        win = row.actual_total < row.line if row.selected_side == "Under" else row.actual_total > row.line
        frame.loc[idx, "profit"] = .98 * (row[row.selected_side.lower() + "_decimal"] - 1) if win else -1
    selections = frame[selected]
    known = selections[selections.profit.notna()]
    unknown = selections[selections.profit.isna()]
    upper = sum(.98 * (r[r.selected_side.lower() + "_decimal"] - 1) for _, r in unknown.iterrows())
    n = len(selections)
    frame.to_csv(out, index=False)
    report = {
        "status": "completed exploratory specification; independent validation required for edge claim",
        "graded_at_utc": now(), "forecast_freeze": source(freeze_path), "graded_artifact": source(out),
        "beta": frozen["beta"], "training_high_wind": frozen["training_high_wind"],
        "all_later_metrics": metrics(frame, frame.week),
        "high_wind_later_metrics": metrics(frame[frame.x.eq(1)], frame.week),
        "selected": n, "selected_graded": len(known), "selected_unknown": len(unknown),
        "selected_wins": int(known.profit.gt(0).sum()), "selected_losses": int(known.profit.lt(0).sum()),
        "selected_units": float(known.profit.sum()) if len(known) else None,
        "selected_roi": interval(known, "profit", frame.week),
        "full_cohort_roi_bounds": [(float(known.profit.sum()) - len(unknown)) / n,
                                  (float(known.profit.sum()) + upper) / n] if n else None,
    }
    dump(REPORT, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["forecast", "grade"], required=True)
    args = parser.parse_args()
    {"forecast": forecast, "grade": grade}[args.phase]()
