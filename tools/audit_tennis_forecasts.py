"""Independent stdlib-only arithmetic/chronology audit of frozen N2/N3 outputs.

Run only after the complete frozen evaluation exists. This does not fit models,
read source pages, reconstruct training histories, or reproduce bootstrap draws.
"""
import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

CANDIDATES = {
    "calibration": ["market_logit"],
    "set_shape": ["market_logit", "structure_gap"],
    "workload": ["market_logit", "structure_gap", "workload_total", "workload_difference"],
}
PENALTIES = [.001, .01, .1, 1.]
CONFIDENCE = 1-.05/13
SOURCE_BLOCKS = {
    "failed_daily_dates": "incomplete_daily_source_coverage",
    "daily_parse_errors": "daily_history_parse_errors",
    "failed_sampled_detail_events": "incomplete_sampled_detail_coverage",
    "sample_detail_identity_mismatches": "sample_detail_identity_mismatches",
    "sample_detail_date_discrepancies": "sample_detail_date_revisions",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    def invalid(value):
        raise ValueError(f"Non-finite JSON literal: {value}")
    return json.loads(path.read_text(), parse_constant=invalid)


def numeric(value):
    if value is None or str(value).strip().lower() in {"", "nan", "na", "none"}:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite numeric field")
    return result


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Chronology timestamp lacks timezone")
    return result.astimezone(timezone.utc)


def day(value):
    return date.fromisoformat(str(value)[:10])


def week_count(rows):
    return len({day(r["date"])-timedelta(days=day(r["date"]).weekday()) for r in rows})


def mean(values):
    return math.fsum(values)/len(values) if values else None


def logit(p):
    p = min(1-1e-6, max(1e-6, p))
    return math.log(p)-math.log1p(-p)


def loss(y, p):
    p = min(1-1e-6, max(1e-6, p))
    return -math.log(p) if y == 1 else -math.log1p(-p)


def predict(row, model, columns):
    if not (len(model["mean"]) == len(model["scale"]) == len(columns)
            and len(model["coef"]) == len(columns)+1):
        raise ValueError("Annual coefficient dimensions disagree with frozen features")
    if any(not math.isfinite(float(v)) for key in ("mean", "scale", "coef") for v in model[key]):
        raise ValueError("Annual model contains non-finite coefficients")
    if any(v <= 0 for v in model["scale"]):
        raise ValueError("Annual model has nonpositive feature scale")
    eta = logit(row["market_p"])+model["coef"][0]
    eta += math.fsum((row[col]-mu)/scale*coef for col, mu, scale, coef in
                     zip(columns, model["mean"], model["scale"], model["coef"][1:]))
    return 1/(1+math.exp(-eta)) if eta >= 0 else math.exp(eta)/(1+math.exp(eta))


def closing_probability(a, b, power=False):
    if a is None or b is None or a <= 1 or b <= 1:
        return None
    u, v = 1/a, 1/b
    if not -1e-10 <= u+v-1 <= .15+1e-10:
        return None
    if not power:
        return u/(u+v)
    # Independent monotone bisection, rather than scipy's Brent solver.
    low, high = .01, 100.
    for _ in range(90):
        middle = (low+high)/2
        if u**middle+v**middle > 1:
            low = middle
        else:
            high = middle
    return u**((low+high)/2)


def choose(row, p):
    a, b = row["odds_a"], row["odds_b"]
    over_ev, under_ev = p*a-1, (1-p)*b-1
    over = over_ev >= under_ev
    odds, ev = (a, over_ev) if over else (b, under_ev)
    selected = (ev >= .03-1e-12 and 1.2 <= odds <= 6
                and -1e-10 <= 1/a+1/b-1 <= .10+1e-10)
    return over, odds, ev, selected


def summarize(rows, probabilities):
    """Recompute point estimates without importing the production evaluator."""
    selected, graded, selected_graded, unresolved = [], [], [], []
    profit, haircut, model_loss, market_loss, brier, market_brier, all_ev = [], [], [], [], [], [], []
    daily = defaultdict(float)
    for row, p in zip(rows, probabilities):
        over, odds, ev, bet = choose(row, p)
        all_ev.append(ev)
        daily[day(row["date"])] += 0.
        if row["y"] is not None:
            graded.append((row, p))
            model_loss.append(loss(row["y"], p))
            market_loss.append(loss(row["y"], row["market_p"]))
            brier.append((p-row["y"])**2)
            market_brier.append((row["market_p"]-row["y"])**2)
        if bet:
            selected.append((row, over, odds))
            if row["y"] is None:
                unresolved.append(odds)
            else:
                selected_graded.append(row)
                win = over == (row["y"] == 1)
                profit.append(odds-1 if win else -1.)
                haircut.append(.98*(odds-1) if win else -1.)
                daily[day(row["date"])] += profit[-1]
    n, ns = len(selected), len(selected_graded)
    total, adjusted = math.fsum(profit), math.fsum(haircut)
    peak, cumulative, drawdown = 0., 0., 0.
    for _, value in sorted(daily.items()):
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak-cumulative)
    bet_days = {day(row["date"]) for row, _, _ in selected}

    def outcome_bounds(known, multiplier):
        if not n:
            return [None, None]
        return [(known-len(unresolved))/n,
                (known+math.fsum(multiplier*(odds-1) for odds in unresolved))/n]

    result = {
        "events": len(rows), "settled_events": len(graded), "missing_event_outcomes": len(rows)-len(graded),
        "bets": n, "turnover_units": n, "settled_bets": ns, "unsettled_bets": n-ns,
        "profit_units_settled": total, "haircut_profit_units_settled": adjusted,
        "roi": total/n if n and n == ns else None, "roi_settled_only": total/ns if ns else None,
        "haircut_roi": adjusted/n if n and n == ns else None,
        "haircut_roi_settled_only": adjusted/ns if ns else None,
        "roi_unresolved_outcome_bounds": outcome_bounds(total, 1.),
        "haircut_roi_unresolved_outcome_bounds": outcome_bounds(adjusted, .98),
        "complete_match_simulation": {"bets": ns, "turnover_units": ns, "profit_units": total,
                                      "roi": total/ns if ns else None, "haircut_roi": adjusted/ns if ns else None},
        "log_loss": mean(model_loss), "market_log_loss": mean(market_loss),
        "brier": mean(brier), "market_brier": mean(market_brier),
        "paired_log_loss_delta": mean([a-b for a, b in zip(model_loss, market_loss)]),
        "paired_brier_delta": mean([a-b for a, b in zip(brier, market_brier)]),
        "paired_loss_events": len(graded), "max_drawdown_daily_units": drawdown,
        "bet_days": len(bet_days),
        "calendar_span_days": (max(bet_days)-min(bet_days)).days+1 if bet_days else 0,
        "max_model_ev": max(all_ev) if all_ev else None,
        "confidence": CONFIDENCE, "bootstrap_samples": 10000, "bootstrap_seed": 1729,
        "bootstrap_block": "calendar week ending Sunday", "multiple_comparison_allowance": 13,
        "execution_verified": False, "fanduel_evidence": False, "entry_book": "Pinnacle",
        "market": "ATP Challenger full-match total 21.5 games",
    }
    for name, power in (("closing_pinnacle", False), ("closing_pinnacle_power", True)):
        fair = [closing_probability(row["close_a"], row["close_b"], power) for row in rows]
        closing_ev, ratios, close_losses, model_close_losses = [], [], [], []
        for row, p, q in zip(rows, probabilities, fair):
            if q is None:
                continue
            over, odds, _, bet = choose(row, p)
            if bet:
                closing_ev.append(odds*(q if over else 1-q)-1)
                ratios.append(odds/(row["close_a"] if over else row["close_b"])-1)
            if row["y"] is not None:
                close_losses.append(loss(row["y"], q))
                model_close_losses.append(loss(row["y"], p))
        result[name] = {
            "covered_bets": len(closing_ev), "missing_bets": n-len(closing_ev),
            "selected_close_coverage": len(closing_ev)/n if n else None,
            "all_event_close_coverage": sum(q is not None for q in fair),
            "all_event_missing_closes": sum(q is None for q in fair),
            "mean_closing_ev": mean(closing_ev), "mean_raw_price_ratio": mean(ratios),
            "paired_loss_events": len(close_losses), "close_log_loss_on_available": mean(close_losses),
            "model_log_loss_on_close_available": mean(model_close_losses),
            "paired_log_loss_delta_vs_close": mean([a-b for a, b in zip(model_close_losses, close_losses)]),
            "devig": "power" if power else "proportional",
        }
    return result


class Checker:
    def __init__(self):
        self.checks = 0
        self.failures = []

    def check(self, condition, label):
        self.checks += 1
        if not condition and len(self.failures) < 100:
            self.failures.append(label)

    def compare(self, actual, expected, label):
        if isinstance(expected, dict):
            self.check(isinstance(actual, dict), label+" is an object")
            if isinstance(actual, dict):
                for key, value in expected.items():
                    self.check(key in actual, label+" contains "+key)
                    if key in actual:
                        self.compare(actual[key], value, label+"."+key)
        elif isinstance(expected, list):
            self.check(isinstance(actual, list) and len(actual) == len(expected), label+" list shape")
            if isinstance(actual, list) and len(actual) == len(expected):
                for n, (a, b) in enumerate(zip(actual, expected)):
                    self.compare(a, b, f"{label}[{n}]")
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            self.check(isinstance(actual, (int, float)) and not isinstance(actual, bool)
                       and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=2e-9, abs_tol=2e-10), label)
        else:
            self.check(type(actual) is type(expected) and actual == expected, label)

    def intervals(self, node, rows, label):
        graded = [row for row in rows if row["y"] is not None]
        required = [(node, "roi_ci", not node["bets"] or node["unsettled_bets"] > 0 or week_count(rows) < 2),
                    (node, "haircut_roi_ci", not node["bets"] or node["unsettled_bets"] > 0 or week_count(rows) < 2),
                    (node, "paired_log_loss_delta_ci", week_count(graded) < 2),
                    (node, "paired_brier_delta_ci", week_count(graded) < 2)]
        completed = node["complete_match_simulation"]
        required += [(completed, key, not completed["bets"] or week_count(rows) < 2)
                     for key in ("roi_ci", "haircut_roi_ci")]
        for key in ("closing_pinnacle", "closing_pinnacle_power"):
            close = node[key]
            comparable = [r for r in graded if closing_probability(r["close_a"], r["close_b"]) is not None]
            required += [(close, field, not close["covered_bets"] or week_count(rows) < 2)
                         for field in ("mean_closing_ev_ci", "mean_raw_price_ratio_ci")]
            required.append((close, "paired_log_loss_delta_vs_close_ci", week_count(comparable) < 2))
        for parent, key, must_be_null in required:
            value = parent.get(key)
            valid = isinstance(value, list) and len(value) == 2
            valid = valid and (value == [None, None] or
                              all(isinstance(x, (int, float)) and math.isfinite(x) for x in value)
                              and value[0] <= value[1])
            self.check(valid, label+" "+key+" interval shape")
            if must_be_null:
                self.compare(value, [None, None], label+" "+key+" requires null")


def load_forecasts(path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    numbers = {"year", "y", "odds_a", "odds_b", "market_p", "market_logit", "kernel_p", "structure_gap",
               "workload_total", "workload_difference", "close_a", "close_b", *["p_"+c for c in CANDIDATES]}
    for row in rows:
        for key in numbers:
            row[key] = numeric(row[key])
        if row["y"] not in (0., 1., None):
            raise ValueError("Outcome must be binary or ungraded")
        if any(row[k] is None or row[k] <= 1 for k in ("odds_a", "odds_b")):
            raise ValueError("Forecast lacks valid finite paired entry prices")
        if any(row[k] is None or not 0 < row[k] < 1 for k in ("market_p", "kernel_p", *["p_"+c for c in CANDIDATES])):
            raise ValueError("Forecast probabilities must be finite and strictly between zero and one")
    return rows


def audit_experiment(output, root, experiment, check, hashes):
    metrics_path = output/f"tennis-{experiment}-metrics.json"
    record = read_json(metrics_path)
    hashes[str(metrics_path)] = digest(metrics_path)
    tag = experiment.upper()
    check.compare(record["experiment"], tag, tag+" experiment")
    check.compare({k: record[k] for k in ("entry_book", "fanduel_execution_evidence", "alerts_enabled", "passes_forward_promotion")},
                  {"entry_book": "Pinnacle", "fanduel_execution_evidence": False, "alerts_enabled": False,
                   "passes_forward_promotion": False}, tag+" execution flags")
    for field, name in (("protocol_sha256", "protocol-tennis-v1.md"),
                        ("independent_protocol_sha256", "protocol-tennis-independent-v1.md"),
                        ("implementation_review_sha256", "tennis-implementation-review.md")):
        check.compare(record[field], digest(root/"docs"/name), tag+" "+field)
    blocks = [reason for key, reason in SOURCE_BLOCKS.items() if record["acquisition"].get(key)]
    check.compare(record["source_evidence_blocks"], blocks, tag+" source failure blocks")
    if record["status"] == "insufficient_evaluable_data":
        check.check(bool(record.get("reason")), tag+" insufficient-data reason")
        check.check("models" not in record and "fit" not in record, tag+" no fitted claims in insufficient record")
        return {"status": "insufficient_evaluable_data", "reason": record.get("reason"),
                "scope": "No forecast arithmetic to audit; any older fit/forecast files are ignored."}
    check.compare(record["status"], "unproven", tag+" status")
    fit_path, csv_path = output/f"tennis-{experiment}-fit.json", output/f"tennis-{experiment}-forecasts.csv"
    fit, rows = read_json(fit_path), load_forecasts(csv_path)
    hashes.update({str(fit_path): digest(fit_path), str(csv_path): digest(csv_path)})
    check.compare(record["fit"], fit, tag+" embedded fit matches file")
    check.compare(record["forecasts_sha256"], digest(csv_path), tag+" forecast hash")
    check.compare(fit["features"], CANDIDATES, tag+" frozen feature definitions")
    check.check(len(rows) > 0, tag+" nonempty forecasts")
    check.check(all(r["event_id"] for r in rows) and len({r["event_id"] for r in rows}) == len(rows), tag+" unique event IDs")
    check.compare(sorted(record["models"]), sorted(["market", *CANDIDATES]), tag+" all candidates present")
    check.compare(sorted(fit["annual_models"]), ["2024", "2025"], tag+" both annual fold records")
    selection, final_time = instant(fit["selection_available_at"]), instant(fit["final_fit_as_of"])
    check.check(instant(fit["final_maximum_label_available_at"]) < final_time, tag+" final fit label chronology")
    check.check("never used for reported holdout forecasts" in fit["final_models_scope"], tag+" final refit scope")
    check.compare(sorted(fit["final_models"]), sorted(CANDIDATES), tag+" final artifacts retained")
    trials = fit["validation_trials"]
    check.check(len(trials) == len(CANDIDATES)*len(PENALTIES)
                and {r["candidate"] for r in trials} == set(CANDIDATES), tag+" complete frozen validation grid")
    check.compare(sorted(fit["selected_penalties"]), sorted(CANDIDATES), tag+" all selected penalties")
    chosen = {}
    for name in CANDIDATES:
        subset = [r for r in trials if r["candidate"] == name]
        check.compare([r["penalty"] for r in subset], PENALTIES, tag+" validation grid "+name)
        check.check(all(math.isfinite(r["validation_log_loss"]) and r["development_events"] > 0
                        and r["validation_events"] > 0 for r in subset), tag+" valid validation rows "+name)
        chosen[name] = min(subset, key=lambda r: r["validation_log_loss"])
        check.compare(fit["selected_penalties"][name], chosen[name], tag+" validation penalty "+name)
        check.compare(fit["final_models"][name]["penalty"], chosen[name]["penalty"], tag+" final refit fixed penalty "+name)
    check.compare(fit["selected_research_candidate"], min(chosen, key=lambda n: chosen[n]["validation_log_loss"]),
                  tag+" candidate chosen from validation")
    predicted = {"market": [row["market_p"] for row in rows], **{name: [] for name in CANDIDATES}}
    by_year = defaultdict(list)
    for row in rows:
        year = str(int(row["year"]))
        check.check(year in {"2024", "2025"} and int(row["year"]) == day(row["date"]).year,
                    tag+" registered forecast year "+row["event_id"])
        by_year[year].append(row)
        quote, start = instant(row["opening_at"]), instant(row["start_at"])
        check.check(selection < quote < start, tag+" selection/entry/start chronology "+row["event_id"])
        check.compare(row["market_p"], (1/row["odds_a"])/(1/row["odds_a"]+1/row["odds_b"]), tag+" entry no-vig "+row["event_id"])
        check.compare(row["market_logit"], logit(row["market_p"]), tag+" entry logit "+row["event_id"])
        check.compare(row["structure_gap"], logit(row["kernel_p"])-logit(row["market_p"]), tag+" kernel gap "+row["event_id"])
        if row["y"] is not None:
            label = instant(row["label_available_at"])
            check.check(label < final_time, tag+" settled label precedes audit fit time "+row["event_id"])
            source_end = datetime.combine(day(row["label_source_date"])+timedelta(days=1), datetime.min.time(),
                                          ZoneInfo("Europe/Prague"))
            check.check(label == source_end.astimezone(timezone.utc)+timedelta(hours=48),
                        tag+" date-end plus48h label availability "+row["event_id"])
        check.check(str(row["closing_valid"]).lower() in {"true", "false"}, tag+" explicit closing flag "+row["event_id"])
        valid_close = str(row["closing_valid"]).lower() == "true"
        if valid_close:
            check.check(closing_probability(row["close_a"], row["close_b"]) is not None,
                        tag+" valid closing pair "+row["event_id"])
            for key in ("close_a_at", "close_b_at"):
                check.check(instant(row[key]) < start, tag+" prestart "+key+" "+row["event_id"])
        else:
            check.check(row["close_a"] is None and row["close_b"] is None,
                        tag+" rejected close remains missing "+row["event_id"])
        for name, columns in CANDIDATES.items():
            p = predict(row, fit["annual_models"][year]["models"][name], columns)
            predicted[name].append(p)
            check.compare(row["p_"+name], p, tag+" annual coefficient prediction "+name+" "+row["event_id"])
    for year, fold in fit["annual_models"].items():
        subset = by_year.get(year, [])
        excluded = fold["model_unavailable_event_ids"]
        check.check(len(excluded) == len(set(excluded)) and not set(excluded) & {r["event_id"] for r in rows},
                    tag+" model-unavailable IDs excluded "+year)
        if not subset:
            check.compare(fold["status"], "missing_feature_valid_test_events", tag+" explicit empty fold "+year)
            continue
        check.compare(fold["status"], "fitted", tag+" fitted fold "+year)
        first = min(instant(r["opening_at"]) for r in subset)
        check.check(instant(fold["first_forecast_quote"]) == first, tag+" earliest annual quote "+year)
        check.check(instant(fold["maximum_label_available_at"]) < first, tag+" annual training precedes quote "+year)
        check.check(fold["training_events"] > 0 and bool(fold["training_years"])
                    and all(2021 <= y < int(year) for y in fold["training_years"]), tag+" prior-year training "+year)
        check.compare(sorted(fold["models"]), sorted(CANDIDATES), tag+" annual candidates "+year)
        for name in CANDIDATES:
            check.compare(fold["models"][name]["penalty"], chosen[name]["penalty"], tag+" annual fixed penalty "+year+name)
    counts = {}
    for name, probabilities in predicted.items():
        node = record["models"][name]
        check.compare(node, summarize(rows, probabilities), tag+" overall "+name)
        check.intervals(node, rows, tag+" overall "+name)
        check.compare(sorted(node["by_year"]), sorted(by_year), tag+" annual metric coverage "+name)
        for year in by_year:
            indices = [i for i, row in enumerate(rows) if str(int(row["year"])) == year]
            annual_rows = [rows[i] for i in indices]
            check.compare(node["by_year"][year], summarize(annual_rows, [probabilities[i] for i in indices]),
                          tag+" annual "+year+" "+name)
            check.intervals(node["by_year"][year], annual_rows, tag+" annual "+year+" "+name)
        def endpoint(ci, index, positive):
            return bool(isinstance(ci, list) and len(ci) == 2 and ci[index] is not None
                        and (ci[index] > 0 if positive else ci[index] < 0))
        screen = {"positive_corrected_haircut_roi": endpoint(node.get("haircut_roi_ci"), 0, True),
                  "positive_corrected_closing_ev": endpoint(node["closing_pinnacle"].get("mean_closing_ev_ci"), 0, True),
                  "negative_corrected_paired_loss": endpoint(node.get("paired_log_loss_delta_ci"), 1, False),
                  "complete_selected_close_coverage": node["bets"] > 0 and node["closing_pinnacle"]["missing_bets"] == 0,
                  "complete_selected_settlements": node["bets"] > 0 and node["unsettled_bets"] == 0}
        check.compare(node["research_screen"], screen, tag+" reported-interval screen "+name)
        check.compare(node["source_evidence_blocks"], blocks, tag+" candidate source blocks "+name)
        check.compare(node["favorable_evidence_unblocked"], all(screen.values()) and not blocks, tag+" unblocked screen "+name)
        counts[name] = {k: node[k] for k in ("events", "settled_events", "bets", "settled_bets", "unsettled_bets")}
    return {"status": record["status"], "candidates": counts, "forecast_years": sorted(by_year)}


def audit(output, root=None):
    output = Path(output).resolve()
    root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    check, hashes, experiments = Checker(), {}, {}
    for name in ("n2", "n3"):
        try:
            experiments[name] = audit_experiment(output, root, name, check, hashes)
        except (ValueError, KeyError, TypeError, IndexError, FileNotFoundError, OverflowError) as exc:
            check.check(False, name+" structural failure: "+str(exc))
    return {"audited_at_utc": datetime.now(timezone.utc).isoformat(), "checks": check.checks,
            "failed_checks": check.failures, "passed": not check.failures, "experiments": experiments,
            "input_sha256": hashes, "auditor_sha256": digest(Path(__file__)),
            "scope": "Independent stdlib point-estimate, annual-coefficient, artifact and reported-chronology checks. "
                     "Both experiments and every frozen candidate are retained; no fitting or selection changes.",
            "limitations": ["Bootstrap configuration, interval shapes/null requirements and screen logic are checked; "
                            "the 10,000 NumPy bootstrap draws and numerical interval endpoints are not independently replayed.",
                            "Annual predictions use the recorded coefficients/normalizers. Training row membership, optimizer "
                            "solutions, validation losses and normalization estimation are not reconstructed without development features.",
                            "Recorded fit chronology is checked against forecast times; raw score-history feature engineering and "
                            "first-publication times are not reconstructed.",
                            "Closing arithmetic and recorded flags/timestamps are checked. Raw-page identification of the "
                            "same full-match 21.5 market, synchronized entry pairs, and executable offers remain acquisition assumptions."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports"), help="Directory containing completed evaluation outputs")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, help="Optional independent JSON audit output")
    args = parser.parse_args()
    result = audit(args.output, args.root)
    payload = json.dumps(result, indent=2, allow_nan=False)+"\n"
    if args.report:
        args.report.write_text(payload)
    print(payload, end="")
    raise SystemExit(0 if result["passed"] else 1)
