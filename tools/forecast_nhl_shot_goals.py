"""Forecast-only implementation of the frozen NHL shot-to-goal declaration.

Import and --help do not read sporting data. Only the explicit --forecast action
executes the declared prior-history calculation. There is no target grading API.
The independent grader consumes forecasts.csv and the hashed freeze JSON.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from nhl_shot_goal_kernel import (
    NumericalExclusion, beta_parameters, estimate_alpha, invert_shot_mean,
    zero_goal_probability,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "data/raw/nhl-shot-archive-2026-09-26"
CARD = "docs/nhl-shot-to-goal-declaration-2026-09-26.md"
COVERAGE = "reports/nhl-shot-goal-overlap-feasibility-2026-09-26.json"
PRICE = "data/raw/nhl-shot-goal-overlap-2026-09-26/paired-prices.csv"
MANIFEST = f"{ARCHIVE}/manifest.json"
BOXES = [f"{ARCHIVE}/outcomes/player_box_{year}.csv" for year in (2024, 2025)]
SCHEDULES = [f"{ARCHIVE}/powerplay-feature-audit/schedule_2024_metadata.csv",
             f"{ARCHIVE}/outcomes/schedule_2025_metadata.csv"]
PERIODS = ("early_nov_dec", "later_january")
SPLIT = datetime(2025, 1, 1, tzinfo=timezone.utc)
PINNED = {
    CARD: "ad937404c14860f1b7c24015cdaaa8f600fb8dafc54df2e427ae2dd54a0c907f",
    COVERAGE: "5a8eef61146038b89ba51704550ed280bb28fc9a59db43bb089d0291c7141e7c",
    PRICE: "682018f651fd789ee35a3671b39340eda055917d03124d8ce12be9a864a379d3",
    # September 28, 2026: manifest, source audit and inventory-tool pins point at the deterministic
    # rebuild (tools/rebuild_nhl_shot_archive.py) after the uncommitted data directory was lost.
    # Every raw payload, box, roster and schedule hash below is unchanged from September 26.
    MANIFEST: "9b43fc27fe396a7b37dd07af3e7f01ab56acb209578b2c5b0defb2bdfbeeed2f",
    f"{ARCHIVE}/outcomes/source_audit.json": "0680f23b515a05483264df58fcf4212dbe0af80dc4f49377ad7b0abb2fd0da00",
    BOXES[0]: "889d439dae5b5a2e831496a3a0dcbea4d385883d68d55b70d55a554169ff6e74",
    BOXES[1]: "511f58b09996be6165c7ad2a0f475ac029f0206653ce4e11665e1ff8088516b0",
    SCHEDULES[0]: "59afa78de1b51e0ceb7bda66207896801fc080505a0ace27cc6ed41e6397b588",
    SCHEDULES[1]: "320643ed83428e28671c7508c667026ab65c46b85bcf312d173c2b025d98e855",
    f"{ARCHIVE}/outcomes/rosters_2024.csv": "0e70a12579b25af0532d00a0cf8bb5fda7d9eb33a23d76234ca26f2fff4ca4ba",
    f"{ARCHIVE}/outcomes/rosters_2025.csv": "cff04536329e7a7f3cdf9034786226e6644a7d222486eb70d4a799d12c1f80ba",
    "tools/inventory_nhl_shot_goal_overlap.py": "ef90aaf397b16a22ba46d852352123ace268128bc352ef8042a56a6c296896ce",
}
BOX_METADATA_COLUMNS = ("game_id", "player_id", "position", "toi", "team_abbrev")
SCHEDULE_COLUMNS = ("game_id", "game_type", "game_state", "game_time",
                    "home_team_abbr", "away_team_abbr")
ADDED_COLUMNS = [
    "prior_team", "prior_count", "prior_goals", "prior_shots", "prior_shot_mean",
    "prior_shot_variance", "prior_game_ids", "latest_prior_available",
    "latest_prior_independent_start", "alpha", "shot_implied_mean", "beta_a",
    "beta_b", "league_conversion", "p_under", "p_over", "p_under_64",
    "quadrature_absolute_difference", "ev_under", "ev_over", "selected_side",
]


def source(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    return {"path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def verify_sources():
    """Verify historical pins and every original raw file before reading values."""
    refs = []
    for name, expected in PINNED.items():
        ref = source(name)
        if ref["sha256"] != expected:
            raise ValueError(f"Frozen input hash mismatch: {name}")
        refs.append(ref)
    manifest = json.loads((ROOT / MANIFEST).read_text())
    if len(manifest["files"]) != 285:
        raise ValueError("Expected the original 285-file price archive")
    for item in manifest["files"]:
        ref = source(item["path"])
        if ref["sha256"] != item["sha256"]:
            raise ValueError(f"Raw price hash mismatch: {item['path']}")
        refs.append(ref)
    for name in ("tools/forecast_nhl_shot_goals.py", "tools/nhl_shot_goal_kernel.py"):
        refs.append(source(name))
    by_path = {}
    for ref in refs:
        if ref["path"] in by_path and by_path[ref["path"]] != ref["sha256"]:
            raise ValueError("Conflicting source pins")
        by_path[ref["path"]] = ref["sha256"]
    return [{"path": name, "sha256": by_path[name]} for name in sorted(by_path)]


def integer(value):
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def identifier(value):
    value = str(value)
    return value if re.fullmatch(r"[0-9]+", value) else None


def seconds(value):
    match = re.fullmatch(r"(\d+):([0-5]\d)", str(value))
    return int(match[1]) * 60 + int(match[2]) if match else None


def utc(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Clock lacks timezone")
    return stamp.astimezone(timezone.utc)


def projected_rows(path, columns):
    """Access only named metadata fields; no incidental sporting-field values."""
    with (ROOT / path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if len(reader.fieldnames) != len(set(reader.fieldnames)) or not set(columns) <= set(reader.fieldnames):
            raise ValueError(f"Unexpected source schema: {path}")
        for number, raw in enumerate(reader, 2):
            yield {key: raw[key] for key in columns} | {"source": path, "source_row": number}


def schedule_index(rejections):
    rows = [row for path in SCHEDULES for row in projected_rows(path, SCHEDULE_COLUMNS)]
    duplicates = {key for key, n in Counter(row["game_id"] for row in rows).items() if n != 1}
    result = {}
    for row in rows:
        reason = None
        if not identifier(row["game_id"]):
            reason = "invalid_schedule_game_id"
        elif row["game_id"] in duplicates:
            reason = "duplicate_schedule_game_id"
        elif row["game_type"] != "R" or row["game_state"] not in ("OFF", "FINAL"):
            reason = "schedule_not_completed_regular_season"
        else:
            try:
                start = utc(row["game_time"])
            except (TypeError, ValueError):
                reason = "missing_or_invalid_independent_start"
        if reason:
            rejections.append({"stage": "schedule", "reason": reason, **row})
        else:
            result[row["game_id"]] = {**row, "start": start,
                                      "available": start + timedelta(hours=72)}
    return result


def structural_history(schedule, latest_entry, rejections):
    """Count values are deliberately absent while the history universe is built."""
    rows = [row for path in BOXES for row in projected_rows(path, BOX_METADATA_COLUMNS)]
    multiplicity = Counter((row["game_id"], row["player_id"]) for row in rows)
    result = []
    for row in rows:
        key = (row["game_id"], row["player_id"])
        reason = None
        if not all(identifier(value) for value in key):
            reason = "invalid_box_identity"
        elif multiplicity[key] != 1:
            reason = "duplicate_game_player_identity"
        elif len(row["game_id"]) != 10 or row["game_id"][4:6] != "02":
            reason = "not_type_02_regular_game"
        elif row["position"] not in ("C", "L", "R", "D"):
            reason = "not_declared_skater_position"
        elif (toi := seconds(row["toi"])) is None or toi <= 0:
            reason = "invalid_or_nonpositive_ice_time"
        elif row["game_id"] not in schedule:
            reason = "no_unique_completed_regular_schedule"
        elif schedule[row["game_id"]]["available"] >= latest_entry:
            reason = "not_available_before_any_candidate_entry"
        if reason:
            rejections.append({"stage": "history_structure", "reason": reason, **row})
            continue
        fixture = schedule[row["game_id"]]
        result.append({**row, "key": key, "toi_seconds": toi,
                       "independent_start": fixture["start"], "available": fixture["available"]})
    return sorted(result, key=lambda r: (r["available"], int(r["game_id"]), int(r["player_id"])))


def choose_prior(history, entry, target_game):
    """Choose latest 80 before count validation; invalid counts cannot be backfilled."""
    return [row for row in history if row["available"] < entry and row["game_id"] != target_game][-80:]


def selected_counts(keys):
    """Read G/S only for preselected prior/league identities, never target grading.

    CSV parsing necessarily scans the retained files; unselected goal/shot strings
    are neither accessed, converted, retained nor emitted. Earlier candidate games
    may enter later histories solely under the declared availability rule.
    """
    result = {}
    for path in BOXES:
        with (ROOT / path).open(newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"game_id", "player_id", "goals", "shots_on_goal"}
            if not required <= set(reader.fieldnames):
                raise ValueError(f"Missing count columns: {path}")
            for raw in reader:
                key = (raw["game_id"], raw["player_id"])
                if key not in keys:
                    continue
                if key in result:
                    raise ValueError(f"Selected count key is not unique: {key}")
                goals, shots = integer(raw["goals"]), integer(raw["shots_on_goal"])
                valid = goals is not None and shots is not None and goals <= shots
                result[key] = {"goals": goals, "shots": shots, "valid": valid,
                               "raw_goals": raw["goals"], "raw_shots_on_goal": raw["shots_on_goal"]}
    if result.keys() != keys:
        raise ValueError("A metadata-selected prior identity has no count row")
    return result


def period_counts(rows):
    return {period: {"games": len({r["game_id"] for r in rows if r["period"] == period}),
                     "forecasts": sum(r["period"] == period for r in rows)} for period in PERIODS}


def passes(periods):
    return all(periods[period]["games"] >= 100 for period in PERIODS)


def load_prices():
    with (ROOT / PRICE).open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns, rows = list(reader.fieldnames), list(reader)
    if not rows or len({(r["game_id"], r["player_id"]) for r in rows}) != len(rows):
        raise ValueError("Empty or duplicate frozen price cohort")
    numeric = [c for c in columns if c.endswith(("_american", "_decimal", "_overround", "_q_under"))]
    numeric += ["shot_line", "goal_line", "lead_seconds"]
    for row in rows:
        if not identifier(row["game_id"]) or not identifier(row["player_id"]) or row["game_id"] == "2024020345":
            raise ValueError("Invalid or original debug identity in frozen prices")
        for col in numeric:
            row[col] = float(row[col])
            if not math.isfinite(row[col]):
                raise ValueError("Nonfinite frozen price")
        entry, boundary = utc(row["entry"]), utc(row["boundary"])
        if not (entry == utc(row["shot_market_update"]) == utc(row["goal_market_update"])):
            raise ValueError("Shot/goal update mismatch")
        if boundary != min(utc(row["provider_start"]), utc(row["independent_start"])):
            raise ValueError("Conservative fixture boundary mismatch")
        if not 0 < (boundary - entry).total_seconds() <= 72 * 3600:
            raise ValueError("Frozen price is outside declared time window")
        period = PERIODS[0] if boundary < SPLIT else PERIODS[1]
        if row["period"] != period or row["goal_line"] != .5:
            raise ValueError("Unexpected period or goal line")
        if not .5 <= row["shot_line"] <= 8.5 or row["shot_line"] % 1 != .5:
            raise ValueError("Invalid shot half-line")
        for market in ("shot", "goal"):
            over, under = [row[f"{market}_{side}_decimal"] for side in ("over", "under")]
            for side, decimal in (("over", over), ("under", under)):
                american = row[f"{market}_{side}_american"]
                expected = 1 + (american / 100 if american > 0 else 100 / -american)
                if abs(american) < 100 or not math.isclose(decimal, expected, abs_tol=1e-13, rel_tol=0):
                    raise ValueError("Invalid American-to-decimal conversion")
            margin = 1 / over + 1 / under - 1
            q = (1 / under) / (1 / over + 1 / under)
            if not -1e-14 <= margin <= .15 + 1e-14:
                raise ValueError("Invalid paired margin")
            if abs(q - row[f"{market}_q_under"]) > 1e-14 or abs(margin - row[f"{market}_overround"]) > 1e-14:
                raise ValueError("Invalid normalized price probability")
    return columns, rows


def select_bets(rows):
    """Modify rows in place; one/game, fixed cost/odds/EV gates and numeric-ID tie."""
    groups = defaultdict(list)
    for row in rows:
        row["selected_side"] = ""
        groups[row["game_id"]].append(row)
    for group in groups.values():
        choices = [(-row[f"ev_{side.lower()}"], int(row["player_id"]), side, row)
                   for row in group for side in ("Over", "Under")
                   if 1.2 <= row[f"goal_{side.lower()}_decimal"] <= 6
                   and row[f"ev_{side.lower()}"] >= .03]
        if choices:
            choice = min(choices, key=lambda value: value[:3])
            choice[3]["selected_side"] = choice[2]


def json_ready(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items() if key != "key"}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def dump(path, value):
    path.write_text(json.dumps(json_ready(value), indent=2, allow_nan=False) + "\n")


def forecast(output_dir, report_stem):
    output = output_dir / "forecasts.csv"
    evidence_path = output_dir / "history-evidence.json"
    rejections_path = output_dir / "exclusions.json"
    freeze_path, md_path = report_stem.with_suffix(".json"), report_stem.with_suffix(".md")
    for path in (output, evidence_path, rejections_path, freeze_path, md_path):
        if path.exists():
            raise FileExistsError(f"Preserve frozen artifact: {path}")
    sources = verify_sources()
    columns, prices = load_prices()
    pre_periods = period_counts(prices)
    if not passes(pre_periods):
        raise ValueError("Frozen price cohort fails 100 games in each period; no history read")
    rejections, histories, forecasts, league_rows = [], [], [], []
    evidence = {"count_access": "Only preselected league/prior keys; no target grading or participation join.",
                "league": [], "history_count_rows": []}
    status, history_periods, numerical_periods = "not_run", period_counts([]), period_counts([])
    league = None
    schedule = schedule_index(rejections)
    first_entry, last_entry = min(utc(r["entry"]) for r in prices), max(utc(r["entry"]) for r in prices)
    structural = structural_history(schedule, last_entry, rejections)
    league_rows = [r for r in structural if r["game_id"].startswith("202302")]
    # A 2023-24 availability anomaly is not repaired by using a partial league season.
    if any(r["available"] >= first_entry for r in league_rows):
        status = "stopped_league_availability_gate"
        for row in league_rows:
            if row["available"] >= first_entry:
                rejections.append({"stage": "league", "reason": "league_not_available_before_first_entry", **row})
    elif not league_rows:
        status = "stopped_empty_league_history"
    else:
        player_history = defaultdict(list)
        for row in structural:
            player_history[row["player_id"]].append(row)
        windows = []
        for price in prices:
            prior = choose_prior(player_history[price["player_id"]], utc(price["entry"]), price["game_id"])
            if len(prior) < 40:
                rejections.append({"stage": "price_history", "reason": "fewer_than_40_prior_appearances",
                                   "game_id": price["game_id"], "player_id": price["player_id"],
                                   "prior_count": len(prior), "prior_game_ids": [r["game_id"] for r in prior]})
            else:
                windows.append((price, prior))
        requested = {r["key"] for r in league_rows}
        requested.update(r["key"] for _, prior in windows for r in prior)
        counts = selected_counts(requested)
        evidence["history_count_rows"] = [{**row, **counts[row["key"]]} for row in structural if row["key"] in requested]
        valid_league = []
        for row in league_rows:
            count = counts[row["key"]]
            if not count["valid"]:
                rejections.append({"stage": "league", "reason": "invalid_goals_or_shots", **row, **count})
            else:
                valid_league.append(row)
        total_goals = sum(counts[r["key"]]["goals"] for r in valid_league)
        total_shots = sum(counts[r["key"]]["shots"] for r in valid_league)
        evidence["league"] = [{"game_id": r["game_id"], "player_id": r["player_id"]} for r in valid_league]
        if not 0 < total_goals < total_shots:
            status = "stopped_invalid_league_conversion"
        else:
            rate = total_goals / total_shots
            league = {"season_prefix": "202302", "valid_rows": len(valid_league),
                      "games": len({r["game_id"] for r in valid_league}), "goals": total_goals,
                      "shots": total_shots, "conversion": rate,
                      "latest_available": max(r["available"] for r in valid_league).isoformat(),
                      "first_candidate_entry": first_entry.isoformat()}
            for price, prior in windows:
                bad = [r["game_id"] for r in prior if not counts[r["key"]]["valid"]]
                if bad:
                    rejections.append({"stage": "price_history", "reason": "invalid_selected_prior_goals_or_shots",
                                       "game_id": price["game_id"], "player_id": price["player_id"],
                                       "invalid_prior_game_ids": bad, "prior_game_ids": [r["game_id"] for r in prior]})
                    continue
                if prior[-1]["team_abbrev"] not in (price["home_team_abbr"], price["away_team_abbr"]):
                    rejections.append({"stage": "price_history", "reason": "latest_prior_team_not_in_fixture",
                                       "game_id": price["game_id"], "player_id": price["player_id"],
                                       "prior_team": prior[-1]["team_abbrev"], "latest_prior_game_id": prior[-1]["game_id"]})
                    continue
                shots = [counts[r["key"]]["shots"] for r in prior]
                goals = sum(counts[r["key"]]["goals"] for r in prior)
                histories.append({**price, "prior_team": prior[-1]["team_abbrev"], "prior_count": len(prior),
                                  "prior_goals": goals, "prior_shots": sum(shots), "prior_shot_mean": statistics.mean(shots),
                                  "prior_shot_variance": statistics.variance(shots),
                                  "prior_game_ids": json.dumps([r["game_id"] for r in prior], separators=(",", ":")),
                                  "latest_prior_available": prior[-1]["available"].isoformat(),
                                  "latest_prior_independent_start": prior[-1]["independent_start"].isoformat(),
                                  "_prior_shots": shots})
            history_periods = period_counts(histories)
            if not passes(history_periods):
                status = "stopped_post_history_coverage_gate"
            else:
                for row in histories:
                    try:
                        alpha = estimate_alpha(row["_prior_shots"])
                        a, b = beta_parameters(row["prior_goals"], row["prior_shots"], rate)
                        mean = invert_shot_mean(row["shot_line"], row["shot_q_under"], alpha)
                        result = zero_goal_probability(mean, alpha, a, b)
                    except NumericalExclusion as exc:
                        rejections.append({"stage": "numerical", "reason": str(exc),
                                           "game_id": row["game_id"], "player_id": row["player_id"]})
                        continue
                    probability = result["probability"]
                    if not 0 < probability < 1:
                        rejections.append({"stage": "numerical", "reason": "goal_probability_not_strictly_interior",
                                           "game_id": row["game_id"], "player_id": row["player_id"]})
                        continue
                    forecasts.append({key: value for key, value in row.items() if key != "_prior_shots"} | {
                        "alpha": alpha, "shot_implied_mean": mean, "beta_a": a, "beta_b": b,
                        "league_conversion": rate, "p_under": probability, "p_over": 1 - probability,
                        "p_under_64": result["probability_64"],
                        "quadrature_absolute_difference": result["absolute_difference"],
                        "ev_under": probability * (1 + .98 * (row["goal_under_decimal"] - 1)) - 1,
                        "ev_over": (1 - probability) * (1 + .98 * (row["goal_over_decimal"] - 1)) - 1,
                        "selected_side": ""})
                numerical_periods = period_counts(forecasts)
                if not passes(numerical_periods):
                    status = "stopped_post_numerical_coverage_gate"
                else:
                    select_bets(forecasts)
                    status = ("frozen_before_target_grading" if any(r["selected_side"] for r in forecasts)
                              else "closed_zero_selections_no_target_grading")
    # Prior features remain auditable even when a declared coverage gate stops probabilities.
    evidence["eligible_price_histories"] = [{k: v for k, v in r.items() if k != "_prior_shots"} for r in histories]
    output_dir.mkdir(parents=True, exist_ok=True)
    report_stem.parent.mkdir(parents=True, exist_ok=True)
    forecasts.sort(key=lambda r: (utc(r["entry"]), int(r["game_id"]), int(r["player_id"])))
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns + ADDED_COLUMNS)
        writer.writeheader()
        writer.writerows(forecasts)
    dump(evidence_path, evidence)
    dump(rejections_path, rejections)
    selected = [r for r in forecasts if r["selected_side"]]
    both_pass = passes(history_periods) and passes(numerical_periods)
    data = {
        "status": status, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": "42cf1f81bc302642ddcc9e88ce2e98c1057bc74d", "sources": sources,
        "forecast": source(output), "history_evidence": source(evidence_path), "exclusions": source(rejections_path),
        "price_rows": len(prices), "price_periods": pre_periods, "post_history_periods": history_periods,
        "periods": numerical_periods, "forecasts": len(forecasts), "games": len({r["game_id"] for r in forecasts}),
        "minimum_games_per_period": 100, "both_periods_pass": both_pass,
        "league_prior": league, "selections": len(selected),
        "period_selections": {p: sum(r["period"] == p for r in selected) for p in PERIODS},
        "selection_sides": dict(Counter(r["selected_side"] for r in selected)),
        "best_after_cost_ev": max((max(r["ev_under"], r["ev_over"]) for r in forecasts), default=None),
        "exclusion_counts": dict(sorted(Counter(f"{r['stage']}:{r['reason']}" for r in rejections).items())),
        "target_grading_performed": False, "target_participation_filter": False,
        "previous_model_predictions_read": False, "uninspected_holdout": False,
        "output_schema": {"price_columns": columns, "added_columns": ADDED_COLUMNS,
                          "prior_game_ids": "JSON array of NHL game-ID strings in ascending availability order",
                          "selection": "Over/Under or blank; one/game, EV >= .03 after 2% net-win haircut; decimal 1.2..6",
                          "grader": "Verify all sources and forecast hash; require both_periods_pass and selections > 0."},
        "limitations": ["Exploratory previously inspected archive, not independent confirmation.",
                        "Source update and start+72h availability are retrospective operational assumptions.",
                        "Prior individual appearances may include earlier candidate games only after strict availability.",
                        "No original receipt, suspension, accepted fill or jurisdiction-specific settlement proof."]}
    dump(freeze_path, data)
    md_path.write_text(
        "# NHL shot-to-goal forecast freeze\n\n"
        f"Status: **{status}**. No target grading or target-participation filtering was performed. "
        "This archive was previously inspected; it is exploratory.\n\n"
        "| Stage | Early games / rows | Later games / rows |\n|---|---:|---:|\n" +
        "".join(f"| {label} | {values[PERIODS[0]]['games']} / {values[PERIODS[0]]['forecasts']} | "
                f"{values[PERIODS[1]]['games']} / {values[PERIODS[1]]['forecasts']} |\n"
                for label, values in (("Prices", pre_periods), ("Prior history", history_periods),
                                      ("Numerical forecasts", numerical_periods))) +
        f"\nBoth post-history and post-numerical 100-game period gates pass: **{both_pass}**. "
        f"Selections: **{len(selected)}**, early {data['period_selections'][PERIODS[0]]}, "
        f"later {data['period_selections'][PERIODS[1]]}. "
        f"Best after-cost EV across all forecast sides: {data['best_after_cost_ev']}.\n\n"
        "Latest 80 eligible appearances are chosen before validating goals/shots; invalid selected counts "
        "exclude the offered row without older replacements. Source boxes are scanned for metadata first; "
        "only the union of selected prior identities and the declared 2023–24 league identities has "
        "goal/shot count fields accessed. All exclusions, prior IDs, availability bounds, aggregates and "
        "numerical checks are retained in hashed raw artifacts.\n\n"
        f"Forecast: `{data['forecast']['path']}`; SHA-256 `{data['forecast']['sha256']}`. "
        f"History: `{data['history_evidence']['path']}`; SHA-256 `{data['history_evidence']['sha256']}`. "
        f"Exclusions: `{data['exclusions']['path']}`; SHA-256 `{data['exclusions']['sha256']}`.\n\n"
        "The companion JSON pins every input, source price payload, code file and output. "
        "The independent grader must verify those hashes and refuse failed period gates or zero selections. "
        "Actual historical availability, executable prices and contract terms remain unverified.\n")
    print(json.dumps({k: data[k] for k in ("status", "forecasts", "games", "post_history_periods", "periods",
                                         "both_periods_pass", "selections", "period_selections", "best_after_cost_ev")}, indent=2))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", action="store_true", help="Run the frozen prior-only forecast; never grade targets")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/raw/nhl-shot-goal-2026-09-26")
    parser.add_argument("--report-stem", type=Path, default=ROOT / "reports/nhl-shot-goal-forecast-freeze-2026-09-26")
    args = parser.parse_args()
    if not args.forecast:
        parser.error("Explicit --forecast is required; no empirical computation was run")
    forecast(args.output_dir.resolve(), args.report_stem.resolve())


if __name__ == "__main__":
    main()
