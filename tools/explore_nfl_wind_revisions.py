"""One-parameter NFL MOS-revision test, declared before outcome analysis.

Phases: prepare (metadata/weather), forecast (early labels only), grade (later).
Each phase preserves its first output instead of silently overwriting it.
"""
from collections import Counter
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit, logit

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nfl-wind-revisions-2026-09-26"
PRICES = RAW / "fanduel-totals-pregame.csv"
VENUES = RAW / "venue-map.json"
SCORES = ROOT / "data/raw/nfl-fixture-feasibility/fixture-source-uninspected-results.csv"
CARD = ROOT / "docs/hypotheses/football-wind-forecast-revisions.md"
REPORT = ROOT / "reports/nfl-wind-revisions-2026-09-26.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def verify(entries):
    for e in entries:
        assert source(ROOT / e["path"])["sha256"] == e["sha256"], e["path"]


def untouched(*paths):
    if any(p.exists() for p in paths):
        raise FileExistsError("Original phase output exists; preserve it")


def mean_wind(run, start, end):
    """Integrate the piecewise-linear forecast; never extrapolate/mask gaps."""
    t = np.array([pd.Timestamp(r["ftime"], tz="UTC").timestamp() for r in run])
    w = np.array([float(r["wsp"]) if r["wsp"] is not None else np.nan for r in run])
    order = np.argsort(t)
    t, w = t[order], w[order]
    if len(set(t)) != len(t):
        raise ValueError("Duplicate forecast-valid times")
    a, b = start.timestamp(), end.timestamp()
    if not len(t) or a < t[0] or b > t[-1]:
        raise ValueError("Forecast does not span game window")
    lo, hi = np.searchsorted(t, a, side="right") - 1, np.searchsorted(t, b, side="left")
    if np.any(~np.isfinite(w[lo:hi + 1])) or np.any((w[lo:hi + 1] < 0) | (w[lo:hi + 1] > 98)):
        raise ValueError("Missing/invalid wind inside window")
    x = np.r_[a, t[(t > a) & (t < b)], b]
    y = np.interp(x, t, w)
    return float(np.trapezoid(y, x) / (b - a))


def prepare():
    path, meta_path = RAW / "weather-entries.csv", RAW / "weather-preparation.json"
    untouched(path, meta_path)
    mapping = json.loads(VENUES.read_text())
    games = {r["game_id"]: r for r in mapping["eligible_games"]}
    prices = pd.read_csv(PRICES)
    prices = prices[prices.game_type.eq("REG") & prices.game_id.isin(games) &
                    prices.flag_existing_quality_gates.eq(True) & prices.line_type.eq("half_point") &
                    prices.lead_to_boundary_seconds.between(12 * 3600, 24 * 3600)].copy()
    prices = prices.sort_values(["captured_at_utc", "game_id"]).drop_duplicates("game_id")
    weather, files, inventory = {}, [PRICES, VENUES, SCORES, CARD, Path(__file__)], []
    for station in sorted({r["station"] for r in games.values()}):
        body, receipt = RAW / "mos" / (station + ".json"), RAW / "mos" / (station + ".receipt.json")
        meta = json.loads(receipt.read_text())
        assert meta["http_status"] == 200 and source(body)["sha256"] == meta["sha256"]
        raw = json.loads(body.read_text())
        runs = {}
        for row in raw:
            assert row["station"] == station and row["model"] == "GFS"
            runtime = pd.Timestamp(row["runtime"], tz="UTC")
            runs.setdefault(runtime, []).append(row)
        weather[station] = runs
        files += [body, receipt]
        inventory.append({"station": station, "rows": len(raw), "runs": len(runs)})
    rows, rejects = [], []
    for _, r in prices.iterrows():
        game = games[r.game_id]
        station = game["station"]
        entry = pd.Timestamp(r.captured_at_utc)
        kickoff = pd.Timestamp(r.independent_kickoff_utc)
        runtime = (entry - pd.Timedelta(hours=8)).floor("6h")
        previous = runtime - pd.Timedelta(hours=24)
        try:
            current = mean_wind(weather[station][runtime], kickoff, kickoff + pd.Timedelta(hours=3))
            old = mean_wind(weather[station][previous], kickoff, kickoff + pd.Timedelta(hours=3))
        except (KeyError, ValueError) as exc:
            rejects.append({"game_id": r.game_id, "station": station, "reason": str(exc), "new_runtime": str(runtime)})
            continue
        q = (1 / r.under_decimal) / (1 / r.under_decimal + 1 / r.over_decimal)
        rows.append({**r.to_dict(), "station": station, "gameday": game["gameday"],
                     "new_runtime": runtime.isoformat(), "old_runtime": previous.isoformat(),
                     "assumed_available": (runtime + pd.Timedelta(hours=8)).isoformat(),
                     "new_wind_knots": current, "old_wind_knots": old, "wind_revision_knots": current - old,
                     "x": (current - old) / 5, "q_under": q,
                     "period": "train_weeks_1_8" if r.week <= 8 else "later_weeks_9_18"})
    frame = pd.DataFrame(rows)
    assert not frame.empty and not frame.game_id.duplicated().any()
    frame.to_csv(path, index=False)
    data = {"phase": "weather_prepared_without_game_results", "created_at_utc": now(),
            "eligible_venue_games": len(games), "games_with_fixed_entry": len(prices),
            "weather_rows": len(frame), "periods": frame.period.value_counts().to_dict(),
            "weather_rejects": rejects, "mos_inventory": inventory,
            "sources": [source(p) for p in files], "prepared": source(path)}
    dump(meta_path, data)
    print(json.dumps({k: data[k] for k in ["eligible_venue_games", "games_with_fixed_entry", "weather_rows", "periods", "weather_rejects"]}, indent=2))


def load_totals(ids):
    """Only access score fields for explicitly requested IDs (early in fit)."""
    out = {}
    with SCORES.open() as handle:
        for r in csv.DictReader(handle):
            if r["game_id"] not in ids:
                continue
            if r["game_id"] in out:
                raise ValueError("Duplicate game result")
            try:
                h, a = float(r["home_score"]), float(r["away_score"])
                if not np.isfinite(h + a) or min(h, a) < 0 or h % 1 or a % 1:
                    raise ValueError("Invalid score")
                out[r["game_id"]] = h + a
            except (ValueError, TypeError):
                out[r["game_id"]] = np.nan
    return out


def fit_beta(q, x, y):
    """Convex summed offset-logistic loss +0.5*beta^2, beta>=0."""
    offset = logit(q)
    def derivative(beta):
        return float(np.sum(x * (expit(offset + beta * x) - y)) + beta)
    if derivative(0) >= 0:
        return 0., derivative(0)
    upper = 1.
    while derivative(upper) < 0:
        upper *= 2
    beta = float(brentq(derivative, 0, upper, xtol=1e-13))
    return beta, derivative(beta)


def forecast():
    path, freeze_path = RAW / "wind-forecasts.csv", RAW / "wind-forecast-freeze.json"
    untouched(path, freeze_path)
    preparation = json.loads((RAW / "weather-preparation.json").read_text())
    verify(preparation["sources"] + [preparation["prepared"]])
    frame = pd.read_csv(RAW / "weather-entries.csv")
    early = frame[frame.period.eq("train_weeks_1_8")].copy()
    later = frame[frame.period.eq("later_weeks_9_18")]
    assert len(later)
    earliest_entry = pd.to_datetime(later.captured_at_utc, utc=True).min()
    early["available"] = pd.to_datetime(early.gameday, utc=True) + pd.Timedelta(hours=72)
    if not early.available.lt(earliest_entry).all():
        raise ValueError("Training label not available before all later entries")
    early["actual_total"] = early.game_id.map(load_totals(set(early.game_id)))
    known = early[early.actual_total.notna()].copy()
    if len(known) < 30:
        raise ValueError("Fewer than30 observed training games")
    q, x = known.q_under.to_numpy(), known.x.to_numpy()
    y = (known.actual_total < known.line).to_numpy(dtype=float)
    beta, derivative = fit_beta(q, x, y)
    train_p = expit(logit(q) + beta * x) if beta else q
    training_metrics = {
        "status": "in-sample calibration only; excluded from later evidence",
        "market_log_loss": float(np.mean(-(y * np.log(q) + (1 - y) * np.log1p(-q)))),
        "model_log_loss": float(np.mean(-(y * np.log(train_p) + (1 - y) * np.log1p(-train_p)))),
        "market_brier": float(np.mean((q - y) ** 2)),
        "model_brier": float(np.mean((train_p - y) ** 2)),
    }
    frame["p_under"] = expit(logit(frame.q_under) + beta * frame.x) if beta else frame.q_under
    frame["ev_under"] = frame.p_under * (1 + .98 * (frame.under_decimal - 1)) - 1
    frame["ev_over"] = (1 - frame.p_under) * (1 + .98 * (frame.over_decimal - 1)) - 1
    frame["selected_side"] = ""
    for idx, r in frame[frame.period.eq("later_weeks_9_18")].iterrows():
        eligible = [(-r["ev_" + s.lower()], s) for s in ["Over", "Under"]
                    if 1.2 <= r[s.lower() + "_decimal"] <= 6 and r["ev_" + s.lower()] >= .03]
        if eligible:
            frame.loc[idx, "selected_side"] = sorted(eligible)[0][1]
    frame.to_csv(path, index=False)
    training_path = RAW / "early-training-labels.csv"
    early[["game_id", "available", "actual_total"]].to_csv(training_path, index=False)
    data = {"phase": "predictions_frozen_before_later_result_grading", "frozen_at_utc": now(),
            "beta": beta, "penalized_gradient_at_beta": derivative, "training_games": len(early),
            "training_graded": len(known), "training_metrics": training_metrics,
            "latest_training_label_available": early.available.max().isoformat(),
            "earliest_later_entry": earliest_entry.isoformat(), "later_forecasts": len(later),
            "later_selections": int(frame.selected_side.ne("").sum()),
            "sources": preparation["sources"] + [preparation["prepared"], source(training_path)],
            "forecast": source(path), "preparation": source(RAW / "weather-preparation.json")}
    dump(freeze_path, data)
    dump(ROOT / "reports/nfl-wind-revisions-freeze-2026-09-26.json", data)
    print(json.dumps({k: data[k] for k in ["frozen_at_utc", "beta", "training_games", "training_graded", "later_forecasts", "later_selections", "latest_training_label_available", "earliest_later_entry"]}, indent=2))


def interval(frame, column, weeks):
    weeks = sorted(set(weeks))
    if frame.empty:
        return {"games": 0, "weeks": len(weeks), "weeks_with_observations": 0,
                "mean": None, "week_bootstrap_95pct": None, "zero_stake_or_label_resamples": 10000}
    groups = frame.groupby("week")[column].agg(["sum", "count"]).reindex(weeks, fill_value=0)
    rng = np.random.default_rng(1729)
    ix = rng.integers(len(groups), size=(10000, len(groups)))
    numerator, denominator = groups["sum"].to_numpy()[ix].sum(1), groups["count"].to_numpy()[ix].sum(1)
    draws = numerator[denominator > 0] / denominator[denominator > 0]
    return {"games": len(frame), "weeks": len(groups), "weeks_with_observations": int(frame.week.nunique()),
            "mean": float(frame[column].mean()), "week_bootstrap_95pct": np.quantile(draws, [.025, .975]).tolist(),
            "zero_stake_or_label_resamples": int(np.sum(denominator == 0))}


def grade():
    path = RAW / "wind-later-graded.csv"
    untouched(path, REPORT)
    frozen = json.loads((RAW / "wind-forecast-freeze.json").read_text())
    verify(frozen["sources"] + [frozen["forecast"], frozen["preparation"]])
    f = pd.read_csv(RAW / "wind-forecasts.csv")
    f = f[f.period.eq("later_weeks_9_18")].copy()
    f["actual_total"] = f.game_id.map(load_totals(set(f.game_id)))
    f["settlement"] = np.where(f.actual_total.notna(), "graded", "unknown")
    f["profit"] = np.nan
    known = f[f.actual_total.notna()].copy()
    y = (known.actual_total < known.line).to_numpy(dtype=float)
    for name in ["q_under", "p_under"]:
        p = known[name].to_numpy()
        known[name + "_loss"] = -(y * np.log(p) + (1 - y) * np.log1p(-p))
        known[name + "_brier"] = (p - y) ** 2
    known["loss_change"] = known.p_under_loss - known.q_under_loss
    known["brier_change"] = known.p_under_brier - known.q_under_brier
    for idx, r in f[f.selected_side.notna()].iterrows():
        if pd.isna(r.actual_total):
            continue
        win = r.actual_total < r.line if r.selected_side == "Under" else r.actual_total > r.line
        f.loc[idx, "profit"] = .98 * (r[r.selected_side.lower() + "_decimal"] - 1) if win else -1
    selected = f[f.selected_side.notna()]
    settled = selected[selected.profit.notna()]
    unknown = selected[selected.profit.isna()]
    best_missing = sum(.98 * (r[r.selected_side.lower() + "_decimal"] - 1) for _, r in unknown.iterrows())
    prices = pd.read_csv(PRICES)
    prices = prices[prices.flag_existing_quality_gates.eq(True)]
    diagnostics = []
    for _, r in f.iterrows():
        later = prices[(prices.game_id == r.game_id) & (prices.captured_at_utc > r.captured_at_utc)].sort_values("captured_at_utc")
        if later.empty:
            diagnostics.append({"game_id": r.game_id, "status": "no_later_fresh_prestart_pair"})
        else:
            end = later.iloc[-1]
            diagnostics.append({"game_id": r.game_id, "status": "available", "later_capture": end.captured_at_utc,
                                "lead_to_independent_start_seconds": float(end.lead_to_independent_kickoff_seconds),
                                "line_change": float(end.line - r.line), "wind_revision_knots": float(r.wind_revision_knots),
                                "same_line": bool(end.line == r.line)})
    f.to_csv(path, index=False)
    n = len(selected)
    report = {"status": "completed exploratory price test; no prospective/executable edge claim", "graded_at_utc": now(),
              "forecast_freeze": source(RAW / "wind-forecast-freeze.json"), "graded_artifact": source(path),
              "beta": frozen["beta"], "training_graded": frozen["training_graded"],
              "training_metrics": frozen["training_metrics"], "later_forecasts": len(f),
              "later_graded": len(known), "later_unknown": int(f.actual_total.isna().sum()),
              "market_log_loss": float(known.q_under_loss.mean()), "model_log_loss": float(known.p_under_loss.mean()),
              "paired_loss_change": interval(known, "loss_change", f.week), "paired_brier_change": interval(known, "brier_change", f.week),
              "selected": n, "selected_graded": len(settled), "selected_unknown": len(unknown),
              "selected_wins": int(settled.profit.gt(0).sum()), "selected_losses": int(settled.profit.lt(0).sum()),
              "selected_units": float(settled.profit.sum()) if len(settled) else None,
              "selected_roi": interval(settled, "profit", f.week),
              "full_cohort_roi_bounds": [(float(settled.profit.sum()) - len(unknown)) / n,
                                          (float(settled.profit.sum()) + best_missing) / n] if n else None,
              "price_response_diagnostics": diagnostics,
              "limitations": ["Exploratory one-season test; earlier archive analyses and broad search multiplicity.",
                              "Eight-hour MOS initialization buffer is an assumption, not a historical receipt.",
                              "Airport wind is a proxy for stadium exposure; fixed/open roof exclusions reduce coverage.",
                              "Odds capture/update metadata are provider records, not accepted fills; historical settlement terms unverified.",
                              "Sparse price cadence cannot resolve reactions within minutes; late pairs are not guaranteed closing quotes.",
                              "Ten later week blocks provide limited uncertainty estimation."]}
    dump(REPORT, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ["price_response_diagnostics", "limitations"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["prepare", "forecast", "grade"], required=True)
    args = parser.parse_args()
    {"prepare": prepare, "forecast": forecast, "grade": grade}[args.phase]()
