"""Fixed NHL shot-count shape test. See the pre-result hypothesis card.

Run --phase forecast, then --phase grade. Raw prices and per-row diagnostics
remain local; tracked reports contain aggregate results and reproducible hashes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unicodedata
import re

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import nbinom, poisson

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-shot-archive-2026-09-26"
SPORT = RAW / "outcomes"
FORECASTS = RAW / "dispersion-forecasts.csv"
FREEZE = RAW / "dispersion-forecast-freeze.json"
OUT = ROOT / "reports/nhl-shot-dispersion-2026-09-26"
WINDOW, MIN_HISTORY, PRIOR, MIN_EV = 80, 40, 40, .03
DEBUG_GAME = 2024020345  # Nov 26 BOS–VAN, outcome inspected in source check.


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def norm(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    return re.sub("[^a-z0-9]", "", value)


def decimal(american):
    a = float(american)
    if not np.isfinite(a) or abs(a) < 100:
        raise ValueError("Invalid American price")
    return 1 + (a / 100 if a > 0 else 100 / abs(a))


def shape_forecast(q_under, line, prior):
    """Change dispersion only; leave the price-implied Poisson mean fixed."""
    k = int(np.floor(line))
    mu = brentq(lambda m: poisson.cdf(k, m) - q_under, 1e-8, 100, xtol=1e-12)
    hist_mean = float(np.mean(prior))
    hist_variance = float(np.var(prior, ddof=1))
    raw_alpha = max(0., (hist_variance - hist_mean) / hist_mean**2) if hist_mean else 0.
    alpha = min(1., raw_alpha * (len(prior) - 1) / (len(prior) - 1 + PRIOR))
    p_under = float(nbinom.cdf(k, 1 / alpha, 1 / (1 + alpha * mu))) if alpha > 0 else q_under
    return mu, hist_mean, hist_variance, alpha, p_under


def load_sport():
    boxes = pd.concat([pd.read_csv(SPORT / f"player_box_{y}.csv") for y in [2024, 2025]], ignore_index=True)
    boxes = boxes[boxes.position.isin(["C", "L", "R", "D"]) &
                  (boxes.game_id.astype(str).str[4:6] == "02")].copy()
    if boxes.duplicated(["game_id", "player_id"]).any():
        raise ValueError("Duplicate sport identity")
    boxes["available"] = pd.to_datetime(boxes.game_date, utc=True) + pd.Timedelta(hours=72)
    boxes = boxes.sort_values(["available", "game_id", "player_id"])
    return boxes


def run_forecast():
    if FREEZE.exists() or FORECASTS.exists():
        raise FileExistsError("Forecast already exists; preserve it rather than silently overwrite")
    files = sorted(RAW.glob("icehockey_nhl_player_props_*.json"))
    if len(files) != 285:
        raise ValueError(f"Incomplete fixed source acquisition: {len(files)}/285")
    boxes = load_sport()
    rosters = pd.concat([pd.read_csv(SPORT / f"rosters_{y}.csv") for y in [2024, 2025]], ignore_index=True)
    rosters["name_key"] = rosters.full_name.map(norm)
    names = rosters.groupby("name_key").player_id.agg(lambda x: sorted(set(x)))
    schedules = pd.read_csv(SPORT / "schedule_2025_metadata.csv")
    schedules = schedules[schedules.game_type == "R"].copy()
    schedules["home_key"] = schedules.home_team_name.map(norm)
    schedules["away_key"] = schedules.away_team_name.map(norm)
    schedules["start"] = pd.to_datetime(schedules.game_time, utc=True)
    history = {int(pid): g for pid, g in boxes.groupby("player_id")}
    rows, attrition, unrecognized = [], Counter(), Counter()
    seen = set()
    for path in files:
        raw = json.loads(path.read_text())
        if "bookmakers" not in raw:
            attrition["source_error_or_no_bookmakers"] += 1
            continue
        if raw.get("sport_key") != "icehockey_nhl":
            raise ValueError("Unexpected sport")
        provider_start = pd.Timestamp(raw["commence_time"])
        games = schedules[(schedules.home_key == norm(raw["home_team"])) &
                          (schedules.away_key == norm(raw["away_team"])) &
                          ((schedules.start - provider_start).abs() <= pd.Timedelta(days=1))]
        if len(games) != 1:
            attrition["game_unresolved"] += 1
            continue
        game = games.iloc[0]
        gid = int(game.game_id)
        if gid == DEBUG_GAME:
            attrition["source_debug_game_excluded"] += 1
            continue
        if raw["id"] in seen:
            raise ValueError("Repeated event payload; resolve before analysis")
        seen.add(raw["id"])
        boundary = min(provider_start, game.start)
        found = False
        for book in raw["bookmakers"]:
            if book["key"] != "fanduel":
                continue
            for market in book["markets"]:
                if market["key"] != "player_shots_on_goal":
                    continue
                found = True
                if not market.get("last_update"):
                    attrition["missing_market_update"] += 1
                    continue
                entry = pd.Timestamp(market["last_update"])
                if not boundary - pd.Timedelta(hours=72) <= entry < boundary:
                    attrition["market_update_not_eligible"] += 1
                    continue
                pairs = {}
                for o in market["outcomes"]:
                    if o.get("name") not in ["Over", "Under"]:
                        continue
                    key = (o.get("description"), o.get("point"))
                    side = o["name"]
                    pair = pairs.setdefault(key, {})
                    if side in pair and pair[side] != o["price"]:
                        raise ValueError("Conflicting duplicate outcome")
                    pair[side] = o["price"]
                eligible = []
                for (name, line), pair in pairs.items():
                    if set(pair) != {"Over", "Under"}:
                        attrition["unpaired_player_line"] += 1
                        continue
                    if not isinstance(line, (int, float)) or not .5 <= line <= 8.5 or line % 1 != .5:
                        attrition["non_half_point_or_outside_line_range"] += 1
                        continue
                    od, ud = decimal(pair["Over"]), decimal(pair["Under"])
                    margin = 1 / od + 1 / ud - 1
                    if not 0 <= margin <= .15:
                        attrition["overround_outside_range"] += 1
                        continue
                    q = (1 / ud) / (1 / od + 1 / ud)
                    eligible.append({"player": name, "line": line, "over_decimal": od,
                                     "under_decimal": ud, "q_under": q, "overround": margin})
                # Same-source paired main line, closest to balanced probability.
                eligible.sort(key=lambda r: (r["player"], abs(r["q_under"] - .5), r["line"]))
                chosen_names = set()
                for candidate in eligible:
                    name = candidate["player"]
                    if name in chosen_names:
                        attrition["extra_line_same_player"] += 1
                        continue
                    chosen_names.add(name)
                    ids = names.get(norm(name), [])
                    if len(ids) != 1:
                        attrition["player_identity_unresolved"] += 1
                        unrecognized[name] += 1
                        continue
                    pid = int(ids[0])
                    prior = history.get(pid, boxes.iloc[:0])
                    prior = prior[(prior.available < entry) & (prior.game_id != gid)].tail(WINDOW)
                    if len(prior) < MIN_HISTORY:
                        attrition["fewer_than_40_prior_games"] += 1
                        continue
                    shots = prior.shots_on_goal.to_numpy(dtype=float)
                    if np.any(~np.isfinite(shots)) or np.any(shots < 0) or np.any(shots % 1 != 0):
                        raise ValueError("Invalid prior counts")
                    mu, hm, hv, alpha, pred = shape_forecast(candidate["q_under"], candidate["line"], shots)
                    rows.append({**candidate, "game_id": gid, "player_id": pid,
                                 "event_id": raw["id"], "source_file": path.name,
                                 "entry": entry.isoformat(), "boundary": boundary.isoformat(),
                                 "period": "later_january" if boundary.year == 2025 else "early_nov_dec",
                                 "n_prior": len(prior), "latest_prior_available": prior.available.max().isoformat(),
                                 "poisson_mean": mu, "history_mean": hm, "history_variance": hv,
                                 "alpha": alpha, "p_under": pred})
        if not found:
            attrition["no_fanduel_main_shots_market"] += 1
    frame = pd.DataFrame(rows)
    if frame.empty or frame.duplicated(["game_id", "player_id"]).any():
        raise ValueError("Empty or duplicate forecasts")
    frame["ev_under"] = frame.p_under * (1 + .98 * (frame.under_decimal - 1)) - 1
    frame["ev_over"] = (1 - frame.p_under) * (1 + .98 * (frame.over_decimal - 1)) - 1
    frame["selected_side"] = ""
    for gid, group in frame.groupby("game_id"):
        candidates = []
        for idx, r in group.iterrows():
            for side in ["Over", "Under"]:
                key = side.lower()
                if 1.2 <= r[key + "_decimal"] <= 6 and r["ev_" + key] >= MIN_EV:
                    candidates.append((-r["ev_" + key], r.player, side, idx))
        if candidates:
            _, _, side, idx = sorted(candidates)[0]
            frame.loc[idx, "selected_side"] = side
    frame.to_csv(FORECASTS, index=False)
    meta = {"phase": "forecast_frozen_before_target_grading", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "script": source(Path(__file__)), "forecasts": source(FORECASTS),
            "forecast_rows": len(frame), "games": int(frame.game_id.nunique()),
            "selections": int(frame.selected_side.ne("").sum()), "attrition": dict(attrition),
            "unrecognized_names": dict(unrecognized), "price_sources": [source(p) for p in files],
            "sport_sources": [source(SPORT / n) for n in ["player_box_2024.csv", "player_box_2025.csv", "rosters_2024.csv", "rosters_2025.csv", "schedule_2025_metadata.csv"]]}
    FREEZE.write_text(json.dumps(meta, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: meta[k] for k in ["frozen_at_utc", "forecast_rows", "games", "selections", "attrition"]}, indent=2))


def confidence(frame, column):
    if frame.empty:
        return {"n": 0, "games": 0, "mean": None, "game_bootstrap_95pct": None}
    groups = frame.groupby("game_id")[column].agg(["sum", "count"])
    rng = np.random.default_rng(1729)
    ix = rng.integers(len(groups), size=(10000, len(groups)))
    means = groups["sum"].to_numpy()[ix].sum(axis=1) / groups["count"].to_numpy()[ix].sum(axis=1)
    return {"n": len(frame), "games": len(groups), "mean": float(frame[column].mean()),
            "game_bootstrap_95pct": np.quantile(means, [.025, .975]).tolist()}


def summarize(frame):
    known = frame[frame.settlement == "graded"].copy()
    y = (known.shots_on_goal < known.line).to_numpy(dtype=float)
    for name in ["q_under", "p_under"]:
        p = np.clip(known[name].to_numpy(), 1e-12, 1 - 1e-12)
        known[name + "_loss"] = -(y * np.log(p) + (1 - y) * np.log1p(-p))
        known[name + "_brier"] = (p - y) ** 2
    known["loss_change"] = known.p_under_loss - known.q_under_loss
    known["brier_change"] = known.p_under_brier - known.q_under_brier
    selected = frame[frame.selected_side.fillna("") != ""]
    settled = selected[selected.settlement.isin(["graded", "void_zero_toi"])]
    missing = len(selected) - len(settled)
    return {"forecasts": len(frame), "graded": len(known), "games": int(frame.game_id.nunique()),
            "settlement_status": frame.settlement.value_counts().to_dict(),
            "market_loss": float(known.q_under_loss.mean()) if len(known) else None,
            "model_loss": float(known.p_under_loss.mean()) if len(known) else None,
            "loss_change": confidence(known, "loss_change"), "brier_change": confidence(known, "brier_change"),
            "mean_alpha": float(frame.alpha.mean()), "zero_alpha": int(frame.alpha.eq(0).sum()),
            "selections": len(selected), "selection_status": selected.settlement.value_counts().to_dict(),
            "selected_under": int(selected.selected_side.eq("Under").sum()),
            "selected_over": int(selected.selected_side.eq("Over").sum()),
            "units": float(settled.profit.sum()) if len(settled) else None,
            "selected_roi": confidence(settled, "profit"),
            "roi_missing_as_losses": float((settled.profit.sum() - missing) / len(selected)) if len(selected) else None,
            "selected_mean_forecast_ev": float(selected.selected_ev.mean()) if len(selected) else None}


def run_grade():
    meta = json.loads(FREEZE.read_text())
    for entry in [meta["forecasts"]] + meta["sport_sources"] + meta["price_sources"]:
        if sha(ROOT / entry["path"]) != entry["sha256"]:
            raise ValueError("Frozen input mismatch: " + entry["path"])
    frame = pd.read_csv(FORECASTS)
    boxes = load_sport()[["game_id", "player_id", "shots_on_goal", "toi"]]
    frame = frame.merge(boxes, on=["game_id", "player_id"], how="left", validate="one_to_one")
    frame["settlement"] = np.where(frame.shots_on_goal.notna(), "graded", "unknown_no_box_row")
    frame.loc[frame.toi.isin(["0:00", "00:00"]), "settlement"] = "void_zero_toi"
    frame["profit"], frame["selected_ev"] = np.nan, np.nan
    for idx, r in frame.iterrows():
        if pd.isna(r.selected_side) or r.selected_side == "":
            continue
        key = r.selected_side.lower()
        frame.loc[idx, "selected_ev"] = r["ev_" + key]
        if r.settlement == "void_zero_toi":
            frame.loc[idx, "profit"] = 0
        elif r.settlement == "graded":
            win = r.shots_on_goal < r.line if key == "under" else r.shots_on_goal > r.line
            frame.loc[idx, "profit"] = .98 * (r[key + "_decimal"] - 1) if win else -1
    graded_path = RAW / "dispersion-graded.csv"
    frame.to_csv(graded_path, index=False)
    report = {"status": "exploratory, not proof of executable edge", "specification": "docs/hypotheses/hockey-shots-count-dispersion.md",
              "forecast_freeze": source(FREEZE), "frozen_at_utc": meta["frozen_at_utc"],
              "graded_at_utc": datetime.now(timezone.utc).isoformat(), "graded_artifact": source(graded_path),
              "forecast_inventory": {k: meta[k] for k in ["forecast_rows", "games", "selections", "attrition", "unrecognized_names"]},
              "pooled": summarize(frame), "periods": {k: summarize(g) for k, g in frame.groupby("period")},
              "limitations": ["No original receipt clock or executable fill; source market-update timestamps are a historical entry proxy.",
              "Retrospective NHL data published in2026; past publication vintage and revisions not verified.",
              "Distribution hypothesis assumes Poisson-like bookmaker mapping and may double-count already priced dispersion.",
              "Sampling consists of33 irregular archive dates with missing-provider/credit errors; not a complete league universe.",
              "One source-debug game was excluded; no January outcomes were used to choose model parameters.",
              "Exact historical jurisdiction/settlement terms unverified; unknown participation remains unresolved.",
              "Intervals are exploratory whole-game resamples, uncorrected for prior searches; no prospective promotion claimed."]}
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"pooled": report["pooled"], "periods": report["periods"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["forecast", "grade"], required=True)
    args = parser.parse_args()
    run_forecast() if args.phase == "forecast" else run_grade()
