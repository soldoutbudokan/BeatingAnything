"""F1: unchanged MLB artifact, fixed entries, publisher-timestamped odds pilot.

This command reads the single frozen export and cached official data. It never
downloads another odds snapshot, fits coefficients, sends alerts or places bets.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .features import build_features, DIFF_FEATURES
from .mlb import load_games, load_appearances, load_venues
from .model import ResidualLogistic, losses
from .odds import american_to_decimal
from .soccer_evaluate import fair_pair

EXPORT_SHA = "3f433cc28f0a2789dc2dff59f46718ee385181ca9e6fc5e460706fa93585a14e"
ARTIFACT_SHA = "c035a7a44c70dc7f16db6624ffebe1b691f2bd76177dfeaf1548813003540f5f"
MODEL_ID = "a7ceefe2db3c13ea"
SOURCE_URL = "https://theoddsgap.com/api/odds-export.csv?sport=baseball_mlb&market=ml"
EASTERN = ZoneInfo("America/New_York")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string with timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(timezone.utc)


def canonical_team(name):
    # The official 2026 MLB schedule and feeds use 'Athletics'.
    return "Athletics" if name == "Oakland Athletics" else name


def paired_snapshots(rows):
    """Pair exact scan/event/book identities; never trust supplied probabilities."""
    groups = defaultdict(list)
    invalid_groups = set()
    audit = Counter()
    for row in rows:
        audit["source_rows"] += 1
        if row.get("sport") != "baseball_mlb" or row.get("market") != "ml" or row.get("line"):
            audit["out_of_scope_rows"] += 1
            continue
        if row.get("book") not in {"fanduel", "pinnacle"}:
            audit["other_book_rows"] += 1
            continue
        try:
            observed, start = utc(row["snapshot_ts"]), utc(row["commence_time"])
            home, away = row["home"], row["away"]
            if any(not isinstance(name, str) or not name.strip() for name in (home, away)) or home == away:
                raise ValueError("Invalid team identities")
            key = (canonical_team(home), canonical_team(away), start, observed, row["book"])
        except (KeyError, ValueError, TypeError, OverflowError):
            audit["invalid_rows"] += 1
            continue
        try:
            price = float(row["american_odds"])
            if not math.isfinite(price) or abs(price) < 100:
                raise ValueError("Invalid American odds")
            decimal = american_to_decimal(price)
            if row["side"] not in {"home", "away"}:
                raise ValueError("Invalid side")
            groups[key].append((row["side"], decimal))
        except (KeyError, ValueError, TypeError, OverflowError):
            audit["invalid_rows"] += 1
            invalid_groups.add(key)
    result = []
    for (home, away, start, observed, book), values in sorted(groups.items()):
        if (home, away, start, observed, book) in invalid_groups:
            audit["invalid_side_row_pairs"] += 1
            continue
        sides = defaultdict(set)
        for side, price in values:
            sides[side].add(price)
        if set(sides) != {"home", "away"} or any(len(v) != 1 for v in sides.values()):
            audit["incomplete_or_conflicting_pairs"] += 1
            continue
        h, a = next(iter(sides["home"])), next(iter(sides["away"]))
        if observed >= start:
            audit["at_or_after_source_start_pairs"] += 1
            continue
        result.append({"home": home, "away": away, "source_start": start,
                       "observed": observed, "book": book, "odds_a": h, "odds_b": a,
                       "vig": 1/h+1/a-1, "probability_home": (1/h)/(1/h+1/a)})
        audit["identical_duplicate_side_rows"] += len(values)-2
    audit["paired_snapshots"] = len(result)
    return result, dict(audit)


def schedule_targets(schedule):
    """Metadata for every scheduled fixture, including missing/unclear outcomes."""
    records = {}
    def identity(game):
        teams = game.get("teams", {})
        return (game.get("gameDate"), game.get("officialDate"), game.get("gameType"),
                game.get("scheduledInnings"), game.get("doubleHeader"), game.get("venue", {}).get("id"),
                *((teams.get(side, {}).get("team", {}).get("id"),
                   canonical_team(teams.get(side, {}).get("team", {}).get("name"))) for side in ("home", "away")))
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            pk = game["gamePk"]
            prior = records.get(pk)
            ambiguous = bool(prior and (prior.get("_ambiguous_schedule") or identity(prior) != identity(game)))
            records[pk] = {**game, "_ambiguous_schedule": ambiguous}
    return records


def map_pairs(pairs, schedule, first_pitch_times=None):
    first_pitch_times = first_pitch_times or {}
    by_teams = defaultdict(list)
    targets = schedule_targets(schedule)
    for pk, game in targets.items():
        sides = game["teams"]
        names = tuple(canonical_team(sides[side]["team"]["name"]) for side in ("home", "away"))
        by_teams[names].append((pk, utc(game["gameDate"])))
    mapped, audit = [], Counter()
    for pair in pairs:
        candidates = [(pk, start) for pk, start in by_teams[pair["home"], pair["away"]]
                      if abs((start-pair["source_start"]).total_seconds()) <= 900]
        if len(candidates) != 1:
            audit["unmatched_or_ambiguous_schedule_pairs"] += 1
            continue
        pk, official_start = candidates[0]
        game = targets[pk]
        if (game.get("gameType") != "R" or game.get("scheduledInnings") != 9
                or game.get("doubleHeader") != "N" or game.get("_ambiguous_schedule")):
            audit["outside_model_fixture_contract_pairs"] += 1
            continue
        if pair["observed"] >= official_start:
            audit["at_or_after_official_start_pairs"] += 1
            continue
        first_pitch_at = first_pitch_times.get(pk)
        if first_pitch_at and pair["observed"] >= first_pitch_at:
            audit["at_or_after_recorded_first_pitch_pairs"] += 1
            continue
        mapped.append({**pair, "game_pk": pk, "official_start": official_start,
                       "first_pitch_at": first_pitch_at,
                       "date": game["officialDate"]})
    audit["mapped_pairs"] = len(mapped)
    return mapped, targets, dict(audit)


def select_entries(pairs):
    """First eligible scan per official event, independent of EV and future data."""
    eligible = defaultdict(list)
    audit = Counter()
    for pair in pairs:
        if pair["book"] != "fanduel":
            continue
        audit["fanduel_mapped_pairs"] += 1
        lead = (pair["source_start"]-pair["observed"]).total_seconds()
        if not 1800 <= lead <= 21600:
            audit["outside_entry_time_window_pairs"] += 1
        elif pair["observed"].astimezone(EASTERN).date().isoformat() != pair["date"]:
            audit["entry_not_on_official_calendar_date_pairs"] += 1
        elif not -1e-10 <= pair["vig"] <= .08+1e-10:
            audit["entry_overround_invalid_pairs"] += 1
        else:
            eligible[pair["game_pk"]].append(pair)
    entries = []
    for pk, values in sorted(eligible.items()):
        first_time = min(row["observed"] for row in values)
        first = [row for row in values if row["observed"] == first_time]
        signatures = {(r["source_start"], r["odds_a"], r["odds_b"]) for r in first}
        if len(signatures) != 1:
            audit["conflicting_first_event_snapshot"] += 1
            continue
        entries.append(first[0])
    audit["entry_events"] = len(entries)
    return entries, dict(audit)


def near_start_pair(pairs, entry, book):
    """Require a later, near-start pair; never use after-start observations."""
    candidates = []
    for pair in pairs:
        if pair["game_pk"] != entry["game_pk"] or pair["book"] != book:
            continue
        boundary = min(pair["official_start"], pair["source_start"], entry["source_start"])
        if pair.get("first_pitch_at"):
            boundary = min(boundary, pair["first_pitch_at"])
        lead = (boundary-pair["observed"]).total_seconds()
        if 60 <= lead <= 1800 and pair["observed"] >= entry["observed"] and -1e-10 <= pair["vig"] <= .15+1e-10:
            candidates.append(pair)
    if not candidates:
        return None
    last_time = max(p["observed"] for p in candidates)
    last = [p for p in candidates if p["observed"] == last_time]
    if len({(p["odds_a"], p["odds_b"]) for p in last}) != 1:
        return None
    return last[0]


def target_metadata(pk, game):
    result = {"game_pk": pk, "date": game["officialDate"], "start_time": game["gameDate"],
              "venue_id": game["venue"]["id"], "scheduled_innings": game.get("scheduledInnings", 9),
              "double_header": game.get("doubleHeader", "N") != "N"}
    for side in ("home", "away"):
        result[f"{side}_team_id"] = game["teams"][side]["team"]["id"]
    return result


def outcome(game):
    status = game.get("status", {}).get("detailedState")
    innings = game.get("linescore", {}).get("currentInning")
    if (status != "Final" or any(game.get(k) for k in ("rescheduleDate", "resumeDate", "resumedFrom"))
            or type(innings) is not int or innings < 9):
        return np.nan
    h, a = (game["teams"][side].get("score") for side in ("home", "away"))
    return float(h > a) if all(type(score) is int and score >= 0 for score in (h, a)) and h != a else np.nan


def make_forecasts(pairs, entries, targets, features, artifact):
    by_pk = {row["game_pk"]: row for row in features}
    model = ResidualLogistic.from_dict(artifact["model"])
    rows = []
    for entry in entries:
        pk = entry["game_pk"]
        row = {"event_id": f"mlb:{pk}", "game_pk": pk, "date": entry["date"],
               "home": entry["home"], "away": entry["away"],
               "source_start_at_entry": entry["source_start"].isoformat(),
               "official_start": entry["official_start"].isoformat(),
               "recorded_first_pitch_at": entry["first_pitch_at"].isoformat() if entry.get("first_pitch_at") else "",
               "entry_observed_at": entry["observed"].isoformat(),
               "odds_a": entry["odds_a"], "odds_b": entry["odds_b"],
               "market_p": entry["probability_home"], "y": outcome(targets[pk]),
               "official_status": targets[pk].get("status", {}).get("detailedState"),
               "p_physical": np.nan, "p_pinnacle": np.nan, "physical_block": "",
               "feature_sha256": "", "feature_cutoff_date": ""}
        feature = by_pk.get(pk)
        if feature is None:
            row["physical_block"] = "missing_features"
        elif not feature["feature_travel_complete"]:
            row["physical_block"] = "incomplete_travel"
        elif feature["home_bullpen_recent_missing"] or feature["away_bullpen_recent_missing"]:
            row["physical_block"] = "incomplete_recent_bullpen"
        else:
            x = np.array([[feature[c] for c in artifact["feature_columns"]]], float)
            row["p_physical"] = float(model.predict_proba(x, [row["market_p"]])[0])
            saved = {c: feature[c] for c in DIFF_FEATURES}
            row["feature_sha256"] = hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()
            row["feature_cutoff_date"] = feature["feature_cutoff_date"]
        controls = [p for p in pairs if p["game_pk"] == pk and p["book"] == "pinnacle"
                    and p["observed"] == entry["observed"] and p["source_start"] == entry["source_start"]
                    and -1e-10 <= p["vig"] <= .15+1e-10]
        if len({(p["odds_a"], p["odds_b"]) for p in controls}) == 1:
            row["p_pinnacle"] = controls[0]["probability_home"]
        for book in ("pinnacle", "fanduel"):
            close = near_start_pair(pairs, entry, book)
            row[f"{book}_close_a"] = close["odds_a"] if close else np.nan
            row[f"{book}_close_b"] = close["odds_b"] if close else np.nan
            row[f"{book}_close_at"] = close["observed"].isoformat() if close else ""
        rows.append(row)
    return pd.DataFrame(rows)


def describe(frame, column):
    """Point estimates only: F1 has too few independent weeks for inference."""
    p = frame[column].to_numpy(float)
    y = frame.y.to_numpy(float)
    m = frame.market_p.to_numpy(float)
    a, b = frame.odds_a.to_numpy(float), frame.odds_b.to_numpy(float)
    home = p*a-1 >= (1-p)*b-1
    odds = np.where(home, a, b)
    ev = np.maximum(p*a-1, (1-p)*b-1)
    vig = 1/a+1/b-1
    chosen = (ev >= .03) & (odds >= 1.2) & (odds <= 6) & (vig >= -1e-10) & (vig <= .08+1e-10)
    graded = np.isfinite(y)
    won = home == (y == 1)
    profit = np.where(chosen & graded, np.where(won, odds-1, -1), 0.)
    haircut = np.where(chosen & graded, np.where(won, .98*(odds-1), -1), 0.)
    n = int(chosen.sum())
    unknown = chosen & ~graded
    complete = n > 0 and not unknown.any()
    daily = pd.DataFrame({"date": frame.date, "profit": profit}).groupby("date").profit.sum()
    curve = np.r_[0., daily.cumsum().to_numpy()]
    loss_delta = losses(y[graded], p[graded])-losses(y[graded], m[graded])
    out = {"events": len(frame), "settled_events": int(graded.sum()), "bets": n,
           "turnover_units": n, "settled_bets": int((chosen & graded).sum()),
           "ungraded_bets": int(unknown.sum()), "profit_units_settled": float(profit.sum()),
           "roi": float(profit.sum()/n) if complete else None,
           "haircut_roi": float(haircut.sum()/n) if complete else None,
           "roi_unresolved_outcome_bounds": [float((profit.sum()-unknown.sum())/n),
               float((profit.sum()+(odds[unknown]-1).sum())/n)] if n else [None, None],
           "log_loss": float(losses(y[graded], p[graded]).mean()) if graded.any() else None,
           "market_log_loss": float(losses(y[graded], m[graded]).mean()) if graded.any() else None,
           "brier": float(((p[graded]-y[graded])**2).mean()) if graded.any() else None,
           "paired_log_loss_delta": float(loss_delta.mean()) if graded.any() else None,
           "max_model_ev": float(ev.max()) if len(ev) else None,
           "max_drawdown_daily_units": float((np.maximum.accumulate(curve)-curve).max()) if not unknown.any() else None,
           "max_drawdown_daily_settled_units": float((np.maximum.accumulate(curve)-curve).max()),
           "independent_calendar_weeks": int(pd.to_datetime(frame.date).dt.to_period("W-SUN").nunique()),
           "inference_status": "insufficient_calendar_weeks", "roi_ci": [None, None],
           "paired_log_loss_delta_ci": [None, None], "execution_verified": False,
           "passes_forward_promotion": False}
    for book in ("pinnacle", "fanduel"):
        for power in (False, True):
            ca, cb = frame[f"{book}_close_a"], frame[f"{book}_close_b"]
            q = fair_pair(ca, cb, power)
            valid = np.isfinite(q)
            covered = chosen & valid
            side_q = np.where(home, q, 1-q)
            prices = np.where(home, ca, cb)
            comparable = valid & graded
            out[f"closing_{book}"+("_power" if power else "")] = {
                "covered_bets": int(covered.sum()), "missing_bets": int((chosen & ~valid).sum()),
                "all_event_close_coverage": int(valid.sum()),
                "mean_closing_ev": float((odds[covered]*side_q[covered]-1).mean()) if covered.any() else None,
                "mean_raw_price_ratio": float((odds[covered]/prices[covered]-1).mean()) if covered.any() else None,
                "paired_loss_events": int(comparable.sum()),
                "paired_log_loss_delta_vs_close": float((losses(y[comparable], p[comparable])-
                    losses(y[comparable], q[comparable])).mean()) if comparable.any() else None,
                "mean_closing_ev_ci": [None, None]}
    return out


def run(export_path, source_dir, output_dir=Path("reports")):
    export_path, source_dir, output_dir = map(Path, (export_path, source_dir, output_dir))
    raw = export_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPORT_SHA:
        raise ValueError("F1 requires the first frozen export; register a new experiment for other data")
    artifact_raw = Path("reports/physical_model.json").read_bytes()
    if hashlib.sha256(artifact_raw).hexdigest() != ARTIFACT_SHA:
        raise ValueError("Frozen model bytes changed")
    artifact = json.loads(artifact_raw)
    if artifact["model_id"] != MODEL_ID or artifact["feature_columns"] != DIFF_FEATURES:
        raise ValueError("Frozen model contract changed")
    pairs, pair_audit = paired_snapshots(csv.DictReader(raw.decode().splitlines()))
    schedule = json.loads((source_dir/"schedule_2026.json").read_text())
    pitch_manifest_path = source_dir/"first-pitch"/"manifest.json"
    pitch_manifest, pitch_times = None, {}
    if pitch_manifest_path.exists():
        from .mlb_first_pitch import first_pitch
        pitch_manifest = json.loads(pitch_manifest_path.read_text())
        for row in pitch_manifest["rows"]:
            if row["status"] != "retrieved":
                continue
            raw_pitch = (pitch_manifest_path.parent/f"{row['game_pk']}.json").read_bytes()
            if hashlib.sha256(raw_pitch).hexdigest() != row["sha256"]:
                raise ValueError("Official pitch-feed hash mismatch")
            stamp = first_pitch(json.loads(raw_pitch), row["game_pk"])
            if stamp != row["first_pitch_at"]:
                raise ValueError("Official first-pitch manifest mismatch")
            if stamp:
                pitch_times[row["game_pk"]] = utc(stamp)
    mapped, targets, map_audit = map_pairs(pairs, schedule, pitch_times)
    entries, entry_audit = select_entries(mapped)
    if not entries:
        raise ValueError("No eligible entries in the frozen source")
    games = load_games(source_dir)
    metadata = [target_metadata(e["game_pk"], targets[e["game_pk"]]) for e in entries]
    features = build_features(games, load_appearances(source_dir, games), load_venues(source_dir), target_games=metadata)
    frame = make_forecasts(mapped, entries, targets, features, artifact)
    frame = frame.sort_values(["date", "event_id"]).reset_index(drop=True)
    if frame.event_id.duplicated().any():
        raise ValueError("Event counted more than once")
    output_dir.mkdir(parents=True, exist_ok=True)
    forecast_path = output_dir/"timestamped-mlb-forecasts.csv"
    frame.to_csv(forecast_path, index=False)
    (output_dir/"timestamped-mlb-features.json").write_text(json.dumps(features, indent=2)+"\n")
    columns = {"fanduel": "market_p", "physical": "p_physical", "pinnacle": "p_pinnacle"}
    shared = frame.dropna(subset=list(columns.values()))
    metrics = {"status": "unproven", "experiment": "F1", "model_id": MODEL_ID,
               "entry_book": "FanDuel", "primary_close": "Pinnacle near-start publisher observations",
               "evidence_class": "retrospective aggregator observations, execution unverified",
               "confidence_if_sufficient_blocks": 1-.05/13, "minimum_calendar_weeks_for_ci": 8,
               "alerts_enabled": False, "audit": {**pair_audit, **map_audit, **entry_audit},
               "physical_blocks": dict(Counter(frame.loc[frame.physical_block.ne(""), "physical_block"])),
               "accepted_events_with_recorded_first_pitch": int(frame.recorded_first_pitch_at.ne("").sum()),
               "sources": {"odds_url": SOURCE_URL, "odds_sha256": EXPORT_SHA,
                   "model_sha256": ARTIFACT_SHA,
                   "protocol_sha256": hashlib.sha256(Path("docs/protocol-mlb-timestamped-v1.md").read_bytes()).hexdigest(),
                   "forecasts_sha256": hashlib.sha256(forecast_path.read_bytes()).hexdigest(),
                   "official_manifest": json.loads((source_dir/"source_manifest.json").read_text())},
               "own_available_population": {}, "shared_population": {}, "by_day": {}}
    metrics["sources"]["first_pitch_manifest"] = pitch_manifest
    for name, column in columns.items():
        available = frame.dropna(subset=[column])
        metrics["own_available_population"][name] = describe(available, column)
        metrics["shared_population"][name] = describe(shared, column)
        metrics["by_day"][name] = {str(day): describe(g, column) for day, g in available.groupby("date")}
    (output_dir/"timestamped-mlb-metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"audit": metrics["audit"], "physical_blocks": metrics["physical_blocks"],
        "shared": {name: {k: v for k, v in node.items() if k in {"events", "settled_events", "bets", "roi", "paired_log_loss_delta", "max_model_ev", "closing_pinnacle"}}
            for name, node in metrics["shared_population"].items()}}, indent=2))
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=Path("data/raw/oddsgap-mlb-f1.csv"))
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/mlb-2026-f1"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    run(args.export, args.source_dir, args.output)
