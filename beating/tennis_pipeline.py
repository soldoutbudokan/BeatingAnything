"""Frozen N2/N3 feature reconstruction, validation and annual prediction fits.

Acquisition is separate. A complete attempt ledger is required before examining
validation/holdout results. Missing markets, closes and outcomes stay audited.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logit

from .model import ResidualLogistic, clipped, losses
from .tennis_history import History, date_end_and_availability, fit_n2, fit_n3
from .tennis_evaluate import describe, gates
from .tennis_source import parse_fixtures, select_sample, parse_daily_results, parse_match_detail

CANDIDATES = {
    "calibration": ["market_logit"],
    "set_shape": ["market_logit", "structure_gap"],
    "workload": ["market_logit", "structure_gap", "workload_total", "workload_difference"],
}
PENALTIES = [.001, .01, .1, 1.]
YEARS = range(2021, 2026)


class InsufficientData(ValueError):
    """A declared split has no usable data; not a numerical or source failure."""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def acquisition_inputs(root):
    """Read only a complete attempted sample; never treat partial work as final."""
    root = Path(root)
    log_path = root/"acquisition.jsonl"
    logs = [json.loads(line) for line in log_path.read_text().splitlines()]
    attempted_files = {row["file"] for row in logs if "file" in row}
    source_hashes = {}
    for row in logs:
        if row.get("status") in {"downloaded", "cache_hit"} and "file" in row:
            source_hash = row.get("sha256")
            if not isinstance(source_hash, str) or len(source_hash) != 64:
                raise ValueError("Successful source acquisition lacks its SHA-256")
            prior_hash = source_hashes.setdefault(row["file"], source_hash)
            if prior_hash != source_hash:
                raise ValueError(f"Conflicting first-write source hashes: {row['file']}")

    def frozen_raw(source):
        raw = (root/source).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source_hashes.get(source):
            raise ValueError(f"Source does not match first successful acquisition hash: {source}")
        return raw
    sample, history, sources, daily_failures, missing_attempts = {}, [], [], [], []
    daily_parse_errors, unknown_sample_dates, date_discrepancies, identity_mismatches = [], [], [], []
    start, end = date(2021, 1, 1), date(2025, 12, 31)
    for n in range((end-start).days+1):
        day = (start+timedelta(days=n)).isoformat()
        source = f"daily/{day}.html"
        if source not in attempted_files:
            missing_attempts.append(source)
            continue
        pin_path, parsed_path = root/"sample"/f"{day}.json", root/"parsed-daily"/f"{day}.json"
        if not pin_path.exists():
            daily_failures.append(day)
            unknown_sample_dates.append(day)
            continue
        raw = frozen_raw(source)
        source_sha = hashlib.sha256(raw).hexdigest()
        pin = json.loads(pin_path.read_text())
        if pin["date"] != day or source_sha != pin["source_sha256"] or pin.get("protocol") != "N2-v1":
            raise ValueError(f"Daily sample/source hash mismatch: {day}")
        fixtures = parse_fixtures(raw, day)
        if pin["matches"] != select_sample(fixtures, day):
            raise ValueError(f"Frozen sample does not match source fixture selection: {day}")
        fixture_ids = {fixture["event_id"]: fixture for fixture in fixtures}
        sources.append({"file": source, "sha256": source_sha, "sample_pin_sha256": digest(pin_path)})
        for item in pin["matches"]:
            # A postponed event can occur on more than one sampled date. First
            # frozen selection owns the event; it is never counted twice.
            sample.setdefault(item["event_id"], {**item, "fixture": fixture_ids[item["event_id"]]})
        if not parsed_path.exists():
            daily_failures.append(day)
            continue
        parsed = json.loads(parsed_path.read_text())
        if parsed != parse_daily_results(raw, day):
            raise ValueError(f"Parsed daily history does not match frozen raw source: {day}")
        sources[-1]["parsed_sha256"] = digest(parsed_path)
        if parsed["errors"]:
            daily_parse_errors.append({"date": day, "errors": parsed["errors"]})
        history.extend(parsed["records"])
    if missing_attempts:
        raise ValueError(f"Acquisition incomplete: {len(missing_attempts)} daily pages not yet attempted")
    details, detail_failures = [], []
    for event_id, item in sorted(sample.items()):
        source = f"details/{item['match_id']}.html"
        if source not in attempted_files:
            missing_attempts.append(source)
            continue
        path = root/"parsed-details"/f"{item['match_id']}.json"
        if not path.exists():
            detail_failures.append(event_id)
            continue
        value = json.loads(path.read_text())
        raw = frozen_raw(source)
        source_sha = hashlib.sha256(raw).hexdigest()
        if value["event_id"] != event_id or source_sha != value["source_sha256"]:
            raise ValueError(f"Detail/source hash mismatch: {event_id}")
        reparsed = {**parse_match_detail(raw, item["match_id"]), "sample_date": item["date"], "source_sha256": source_sha}
        if value != reparsed:
            raise ValueError(f"Parsed detail does not match frozen raw source/sample: {event_id}")
        fixture = item["fixture"]
        identity_valid = (not fixture.get("identity_error")
                          and {fixture.get("player1"), fixture.get("player2")} == {value["player1"], value["player2"]})
        value["sample_fixture_identity_valid"] = identity_valid
        if not identity_valid:
            identity_mismatches.append(event_id)
        if value["date"] != item["date"]:
            date_discrepancies.append({"event_id": event_id, "sample_date": item["date"], "detail_date": value["date"]})
        details.append(value)
        sources.append({"file": source, "sha256": source_sha, "parsed_sha256": digest(path)})
    if missing_attempts:
        raise ValueError(f"Acquisition incomplete: {len(missing_attempts)} sampled detail pages not yet attempted")
    return history, details, {"daily_dates_required": (end-start).days+1,
        "failed_daily_dates": daily_failures, "sampled_unique_events": len(sample),
        "unknown_sample_dates": unknown_sample_dates, "daily_parse_errors": daily_parse_errors,
        "sample_detail_date_discrepancies": date_discrepancies, "sample_detail_identity_mismatches": identity_mismatches,
        "failed_sampled_detail_events": detail_failures, "parsed_details": len(details),
        "attempt_ledger_sha256": digest(log_path), "sources": sources}


def reconcile_history(records):
    """Conservatively date multi-day results at the latest source result date.

    Player order is canonicalized without changing set winners. Conflicting
    identities or same-date scores are errors. Every repeated event is audited;
    a latest-date record cannot become available at an earlier partial date.
    """
    grouped = defaultdict(list)
    for value in records:
        one, two = value["player1"], value["player2"]
        sets = value["sets"]
        if one > two:
            one, two = two, one
            sets = [[b, a] for a, b in sets]
        grouped[value["event_id"]].append({"event_id": value["event_id"], "date": value["date"],
            "player1": one, "player2": two, "sets": sets, "completed": value["completed"]})
    result, repeats = [], []
    for event_id, values in sorted(grouped.items()):
        if len({(v["player1"], v["player2"]) for v in values}) != 1:
            raise ValueError(f"Conflicting historical players: {event_id}")
        last_date = max(v["date"] for v in values)
        last = [v for v in values if v["date"] == last_date]
        if len({json.dumps(v, sort_keys=True) for v in last}) != 1:
            raise ValueError(f"Conflicting same-date historical scores: {event_id}")
        result.append(last[0])
        if len(values) > 1:
            repeats.append({"event_id": event_id, "source_dates": sorted({v["date"] for v in values}),
                            "records": len(values), "availability_source_date": last_date})
    return result, repeats


def prepare_features(history_records, details, experiment):
    if experiment not in {"n2", "n3"}:
        raise ValueError("Only registered N2 and N3 are supported")
    history_records, repeats = reconcile_history(history_records)
    history = History(history_records)
    outcomes = {r["event_id"]: r for r in history_records}
    rows, audit, rejected = [], Counter(), []
    for detail in sorted(details, key=lambda r: r["event_id"]):
        audit["details_examined"] += 1
        errors = list(detail.get(f"entry_errors_{experiment}", []))
        if detail.get("sample_fixture_identity_valid") is False:
            errors.append("sample_fixture_identity_mismatch_or_unknown")
        if not detail.get(f"entry_valid_{experiment}") or errors:
            rejected.append({"event_id": detail["event_id"], "reasons": errors or ["entry_invalid"]})
            audit["entry_rejected"] += 1
            continue
        if int(detail["date"][:4]) not in YEARS:
            rejected.append({"event_id": detail["event_id"], "reasons": ["outside_registered_years"]})
            audit["outside_registered_years"] += 1
            continue
        totals = detail["totals_21_5"]
        one, two = totals["side1"], totals["side2"]
        a, b = one["opening_price"], two["opening_price"]
        market = (1/a)/(1/a+1/b)
        decision = one["opening_at"]
        summary = history.features(detail["player1"], detail["player2"], detail["event_id"], decision)
        try:
            if experiment == "n2":
                money = detail["moneyline"]
                ma, mb = money["side1"]["opening_price"], money["side2"]["opening_price"]
                kernel = fit_n2(summary, (1/ma)/(1/ma+1/mb))
            else:
                kernel = fit_n3(summary)
        except (ValueError, RuntimeError) as exc:
            rejected.append({"event_id": detail["event_id"], "reasons": ["kernel_fit_failed"], "detail": str(exc)})
            audit["kernel_fit_failed"] += 1
            continue
        completed = outcomes.get(detail["event_id"])
        y, label_at = np.nan, None
        if completed is not None:
            if {completed["player1"], completed["player2"]} != {detail["player1"], detail["player2"]}:
                # Identity uncertainty cannot be converted into a convenient
                # result or quietly removed after a bet has been selected.
                audit["outcome_identity_mismatch"] += 1
            elif completed["completed"]:
                y = int(sum(sum(s) for s in completed["sets"]) > 21.5)
                label_at = date_end_and_availability(completed["date"])[1].isoformat()
        kernel_p = kernel["distribution"]["over_21_5_p"]
        row = {"event_id": detail["event_id"], "date": detail["date"], "year": int(detail["date"][:4]),
               "sample_date": detail.get("sample_date"),
               "player1": detail["player1"], "player2": detail["player2"], "start_at": detail["start_at"],
               "opening_at": decision, "y": y, "label_available_at": label_at,
               "label_source_date": completed["date"] if np.isfinite(y) else None,
               "odds_a": a, "odds_b": b, "market_p": market,
               "market_logit": float(logit(clipped([market]))[0]),
               "kernel_p": kernel_p, "structure_gap": float(logit(clipped([kernel_p]))[0]-logit(clipped([market]))[0]),
               "workload_total": summary["workload_total"], "workload_difference": summary["workload_difference"],
               "hold1": kernel["hold1"], "hold2": kernel["hold2"], "kernel_residual": kernel["max_probability_error"],
               "history_sets_player1": summary["player1_history"]["completed_sets_365d"],
               "history_sets_player2": summary["player2_history"]["completed_sets_365d"],
               "history_missing_player1": summary["player1_history"]["missing_history"],
               "history_missing_player2": summary["player2_history"]["missing_history"],
               "current_event_history_inconsistency": summary["current_event_history_inconsistency"],
               "source_sha256": detail["source_sha256"],
               "history_feature_sha256": hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest(),
               "close_a": one["final_price"] if detail["closing_valid"] else np.nan,
               "close_b": two["final_price"] if detail["closing_valid"] else np.nan,
               "closing_valid": detail["closing_valid"],
               "close_a_at": one["final_at"] if detail["closing_valid"] else None,
               "close_b_at": two["final_at"] if detail["closing_valid"] else None}
        rows.append(row)
        audit["feature_accepted"] += 1
        if not detail["closing_valid"]:
            audit["accepted_missing_close"] += 1
        if not np.isfinite(y):
            audit["accepted_missing_outcome"] += 1
    frame = pd.DataFrame(rows)
    if not frame.empty and frame.event_id.duplicated().any():
        raise ValueError("Duplicate detail event IDs")
    return frame, {"counts": dict(audit), "rejected_events": rejected, "reconciled_multiday_history": repeats}


def available_training(frame, years, before):
    return (frame.year.isin(years) & frame.y.notna() & frame.label_available_at.notna()
            & (pd.to_datetime(frame.label_available_at, utc=True) < before))


def fit_and_forecast(frame, fit_as_of=None):
    """Validation-only choice; annual fits use labels available before any quote."""
    if frame.empty:
        raise InsufficientData("No early-input-valid feature rows")
    frame = frame.sort_values(["opening_at", "event_id"]).reset_index(drop=True).copy()
    known = frame.y.notna()
    if not np.isin(frame.loc[known, "y"].to_numpy(float), [0, 1]).all():
        raise ValueError("Graded labels must be finite binary outcomes")
    label_times = pd.to_datetime(frame.label_available_at, utc=True)
    if label_times[known].isna().any():
        raise ValueError("Every graded label requires an availability timestamp")
    fit_as_of = pd.Timestamp(datetime.now(timezone.utc) if fit_as_of is None else fit_as_of)
    if fit_as_of.tzinfo is None:
        raise ValueError("fit_as_of must include a timezone")
    fit_as_of = fit_as_of.tz_convert("UTC")
    if (label_times[known] >= fit_as_of).any():
        raise ValueError("Cannot evaluate outcomes unavailable at fit_as_of")
    validation = frame.year.eq(2023) & frame.y.notna()
    if not validation.any():
        raise InsufficientData("No graded validation events; no candidate can be selected")
    validation_start = pd.to_datetime(frame.loc[frame.year.eq(2023), "opening_at"], utc=True).min()
    train = available_training(frame, [2021, 2022], validation_start)
    if not train.any():
        raise InsufficientData("No development labels available before validation quotes")
    selected, trials = {}, []
    for name, columns in CANDIDATES.items():
        candidates = []
        for penalty in PENALTIES:
            fitted = ResidualLogistic(penalty).fit(frame.loc[train, columns], frame.loc[train, "y"], frame.loc[train, "market_p"])
            p = fitted.predict_proba(frame.loc[validation, columns], frame.loc[validation, "market_p"])
            row = {"candidate": name, "penalty": penalty,
                   "validation_log_loss": float(losses(frame.loc[validation, "y"], p).mean()),
                   "development_events": int(train.sum()), "validation_events": int(validation.sum())}
            candidates.append(row)
            trials.append(row)
        selected[name] = min(candidates, key=lambda r: r["validation_log_loss"])
    research_candidate = min(selected, key=lambda name: selected[name]["validation_log_loss"])
    forecasts, folds = [], {}
    selection_available_at = pd.to_datetime(frame.loc[validation, "label_available_at"], utc=True).max()
    if pd.isna(selection_available_at):
        raise ValueError("Graded validation events lack outcome availability timestamps")
    for year in (2024, 2025):
        test = frame.year.eq(year)
        selection_unavailable = test & (pd.to_datetime(frame.opening_at, utc=True) <= selection_available_at)
        excluded_early = frame.loc[selection_unavailable, "event_id"].tolist()
        test &= ~selection_unavailable
        if not test.any():
            folds[str(year)] = {"status": "missing_feature_valid_test_events",
                               "model_unavailable_event_ids": excluded_early}
            continue
        first_quote = pd.to_datetime(frame.loc[test, "opening_at"], utc=True).min()
        training = available_training(frame, list(range(2021, year)), first_quote)
        # Model-selection labels are information too. A new-year quote cannot
        # use a penalty chosen from a validation match not yet made available.
        if not training.any():
            raise InsufficientData(f"No prior labels available at {year} fit")
        predictions = frame.loc[test].copy()
        fits = {}
        for name, columns in CANDIDATES.items():
            model = ResidualLogistic(selected[name]["penalty"]).fit(
                frame.loc[training, columns], frame.loc[training, "y"], frame.loc[training, "market_p"])
            predictions[f"p_{name}"] = model.predict_proba(predictions[columns], predictions.market_p)
            fits[name] = model.to_dict()
        folds[str(year)] = {"status": "fitted", "first_forecast_quote": first_quote.isoformat(),
            "model_unavailable_event_ids": excluded_early,
            "training_events": int(training.sum()), "training_years": sorted(frame.loc[training, "year"].unique().tolist()),
            "maximum_label_available_at": frame.loc[training, "label_available_at"].max(), "models": fits}
        forecasts.append(predictions)
    if not forecasts:
        raise InsufficientData("No historical holdout forecasts")
    predictions = pd.concat(forecasts, ignore_index=True).sort_values(["date", "event_id"])
    all_known = known & (label_times < fit_as_of)
    final_models = {name: ResidualLogistic(selected[name]["penalty"]).fit(
        frame.loc[all_known, columns], frame.loc[all_known, "y"], frame.loc[all_known, "market_p"]).to_dict()
        for name, columns in CANDIDATES.items()}
    fit = {"status": "unproven", "validation_trials": trials, "selected_penalties": selected,
           "selection_available_at": selection_available_at.isoformat(),
           "selected_research_candidate": research_candidate, "annual_models": folds,
           "final_models": final_models, "features": CANDIDATES,
           "final_fit_as_of": fit_as_of.isoformat(),
           "final_models_scope": "Post-holdout refits for future use only; never used for reported holdout forecasts",
           "final_training_events": int(all_known.sum()),
           "final_maximum_label_available_at": label_times[all_known].max().isoformat(),
           "training_through_source_date": str(frame.loc[all_known, "label_source_date"].max())
               if "label_source_date" in frame else None,
           "split_counts": {str(k): int(v) for k, v in frame.groupby("year").size().items()}}
    return predictions, fit


def run(root, output):
    root, output = Path(root), Path(output)
    history, details, acquisition = acquisition_inputs(root)
    source_blocks = []
    for key, reason in (("failed_daily_dates", "incomplete_daily_source_coverage"),
                        ("daily_parse_errors", "daily_history_parse_errors"),
                        ("failed_sampled_detail_events", "incomplete_sampled_detail_coverage"),
                        ("sample_detail_identity_mismatches", "sample_detail_identity_mismatches"),
                        ("sample_detail_date_discrepancies", "sample_detail_date_revisions")):
        if acquisition.get(key):
            source_blocks.append(reason)
    output.mkdir(parents=True, exist_ok=True)
    for experiment in ("n2", "n3"):
        frame, feature_audit = prepare_features(history, details, experiment)
        record = {"experiment": experiment.upper(), "status": "unproven", "entry_book": "Pinnacle",
                  "fanduel_execution_evidence": False, "alerts_enabled": False,
                  "acquisition": acquisition, "feature_audit": feature_audit,
                  "source_evidence_blocks": source_blocks,
                  "source_evidence_scope": "Implementation source-quality limits; not an additional originally registered selection rule",
                  "passes_forward_promotion": False,
                  "protocol_sha256": digest("docs/protocol-tennis-v1.md"),
                  "independent_protocol_sha256": digest("docs/protocol-tennis-independent-v1.md"),
                  "implementation_review_sha256": digest("docs/tennis-implementation-review.md")}
        frame.to_csv(output/f"tennis-{experiment}-features.csv", index=False)
        try:
            predictions, fit = fit_and_forecast(frame)
        except InsufficientData as exc:
            record.update(status="insufficient_evaluable_data", reason=str(exc))
            (output/f"tennis-{experiment}-metrics.json").write_text(json.dumps(record, indent=2, allow_nan=False)+"\n")
            print(json.dumps({"experiment": experiment, "status": record["status"], "reason": str(exc)}), flush=True)
            continue
        predictions["date"] = pd.to_datetime(predictions.date)
        forecast_path = output/f"tennis-{experiment}-forecasts.csv"
        predictions.to_csv(forecast_path, index=False)
        record["fit"] = fit
        record["forecasts_sha256"] = digest(forecast_path)
        record["models"] = {}
        for candidate in ("market", *CANDIDATES):
            column = "market_p" if candidate == "market" else f"p_{candidate}"
            node = describe(predictions, predictions[column])
            node["research_screen"] = gates(node)
            node["source_evidence_blocks"] = list(source_blocks)
            node["favorable_evidence_unblocked"] = bool(all(node["research_screen"].values()) and not source_blocks)
            node["by_year"] = {str(year): describe(g, g[column]) for year, g in predictions.groupby("year")}
            record["models"][candidate] = node
        (output/f"tennis-{experiment}-fit.json").write_text(json.dumps(fit, indent=2, allow_nan=False)+"\n")
        (output/f"tennis-{experiment}-metrics.json").write_text(json.dumps(record, indent=2, allow_nan=False)+"\n")
        print(json.dumps({"experiment": experiment, "selected": fit["selected_research_candidate"],
            "models": {k: {field: v[field] for field in ("events", "bets", "roi", "paired_log_loss_delta")}
                for k, v in record["models"].items()}}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("data/raw/tennisexplorer"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    run(args.source_dir, args.output)
