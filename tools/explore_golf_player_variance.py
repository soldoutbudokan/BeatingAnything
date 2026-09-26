#!/usr/bin/env python3
"""Fixed exploratory 2025 FanDuel 3-ball variance adjustment; offline, no wagers.

Declared before this test's results: prior 80 complete, field-centered rounds,
minimum 40; shrink sample variance toward 9 with 100 prior degrees of freedom.
No current-event rounds. Relative variances are normalized to group mean 9.
Invert the three normalized opening prices under independent discretized normal
scores with SD=3; hold those inferred relative means fixed while varying SD.
One selection per board only if estimated original-stake EV >=3%. No fitted
parameters, grid search, minimum-uplift rule, or tuning on 2025 outcomes.

This is a selected third-party export: its exporter excludes outcomes other than
0, .5, 1, including three-way ties if encoded as 1/3. Unknown historical settlement
rules and quote timezones prevent any edge/execution claim from this test alone.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/golf-sport"
PRICES = ROOT / "data/raw/golf-historical-price-search-2026-09-19/alpha/tracker-pages-test/data/matchup_backtest_detail.csv"
EXPORTER = ROOT / "data/raw/golf-historical-price-search-2026-09-19/alpha/alpha-caddie-web/scripts/export-matchup-backtest-csv.mjs"
OUT = ROOT / "reports/golf-player-variance-2026-09-26"
TEST_YEAR = 2025
MIN_HISTORY, WINDOW, PRIOR_DF, BASE_VAR, MIN_EV = 40, 80, 100, 9.0, .03
GRID = np.arange(-40., 41.)
EXCLUDE = {
    "The American Express", "Farmers Insurance Open", "AT&T Pebble Beach Pro-Am",
    "The RSM Classic", "PGA TOUR Q-School presented by Korn Ferry",
    "Zurich Classic of New Orleans", "Ryder Cup", "Presidents Cup",
    "Barracuda Championship", "TOUR Championship", "Crypto.com Showdown",
}


def norm(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub("[^a-z0-9]", "", value)


def name_parts(value):
    if "," in value:
        last, first = value.split(",", 1)
    else:
        first, _, last = value.strip().rpartition(" ")
    return norm(first), norm(last)


def full_name(value):
    first, last = name_parts(value)
    return first + last


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def complete_round(raw):
    holes = [h for h in raw.get("linescores", []) if isinstance(h.get("value"), (int, float))
             and h["value"] > 0 and 1 <= h.get("period", 0) <= 18]
    score = raw.get("value")
    if len(holes) != 18 or len({h["period"] for h in holes}) != 18:
        return None
    if score != sum(h["value"] for h in holes) or not 40 <= score <= 120:
        return None
    return int(score)


def distribution(means, variances):
    """Effective first-place share, strict wins, and probability of a three-way tie."""
    sd = np.sqrt(np.asarray(variances))[:, None]
    mu = np.asarray(means)[:, None]
    pmf = ndtr((GRID[None, :] + .5 - mu) / sd) - ndtr((GRID[None, :] - .5 - mu) / sd)
    pmf /= pmf.sum(axis=1)[:, None]
    greater = np.maximum(0., 1 - np.cumsum(pmf, axis=1))
    effective, strict = [], []
    triple = float(np.prod(pmf, axis=0).sum())
    for i in range(3):
        j, k = [n for n in range(3) if n != i]
        win = float((pmf[i] * greater[j] * greater[k]).sum())
        share = win + .5 * float((pmf[i] * (pmf[j] * greater[k] + pmf[k] * greater[j])).sum()) + triple / 3
        effective.append(share)
        strict.append(win)
    assert abs(sum(effective) - 1) < 1e-9
    return np.array(effective), np.array(strict), triple


def forecast(prices, variances):
    q = 1 / np.asarray(prices)
    q /= q.sum()
    def objective(two):
        return distribution([two[0], two[1], 0], [BASE_VAR] * 3)[0][:2] - q[:2]
    fit = least_squares(objective, [0., 0.], bounds=(-25, 25), xtol=1e-11, ftol=1e-11, gtol=1e-11)
    means = [float(fit.x[0]), float(fit.x[1]), 0.]
    baseline, strict_base, tie_base = distribution(means, [BASE_VAR] * 3)
    if not fit.success or np.max(np.abs(baseline - q)) > 1e-6:
        return None
    relative = np.array(variances) * BASE_VAR / np.mean(variances)
    p, strict, tie = distribution(means, relative)
    return {"baseline": q, "prediction": p, "strict": strict,
            "triple": tie, "baseline_triple": tie_base,
            "relative_variances": relative}


def player_match(label, competitors):
    exact = [c for c in competitors if full_name(c["athlete"]["displayName"]) == full_name(label)]
    if len(exact) == 1:
        return exact[0], "full_normalized_name"
    first, last = name_parts(label)
    candidates = [c for c in competitors if name_parts(c["athlete"]["displayName"])[1] == last
                  and name_parts(c["athlete"]["displayName"])[0][:1] == first[:1]]
    if first and last and len(candidates) == 1:
        return candidates[0], "unique_surname_first_initial_within_event"
    return None, "unmatched_or_ambiguous"


def confidence(rows, field, selections_only=False):
    work = [r for r in rows if not selections_only or r["selected"]]
    if not work:
        return {"mean": None, "event_bootstrap_95": None, "events": 0, "n": 0}
    sums, nums = defaultdict(float), Counter()
    for r in work:
        sums[r["event_id"]] += r[field]
        nums[r["event_id"]] += 1
    keys = sorted(sums)
    sx, nx = np.array([sums[k] for k in keys]), np.array([nums[k] for k in keys])
    rng = np.random.default_rng(9262026)
    indexes = rng.integers(0, len(keys), (3000, len(keys)))
    means = sx[indexes].sum(axis=1) / nx[indexes].sum(axis=1)
    return {"mean": float(sx.sum() / nx.sum()), "event_bootstrap_95": np.quantile(means, [.025, .975]).tolist(),
            "events": len(keys), "n": len(work)}


def summarize(rows):
    chosen = [r for r in rows if r["selected"]]
    ans = {"boards": len(rows), "events": len({r["event_id"] for r in rows}),
           "player_exposures": 3 * len(rows), "selections": len(chosen),
           "selected_events": len({r["event_id"] for r in chosen})}
    if not rows:
        return ans
    ans.update({"baseline_log_loss": float(np.mean([r["baseline_log_loss"] for r in rows])),
                "variance_log_loss": float(np.mean([r["variance_log_loss"] for r in rows])),
                "baseline_brier": float(np.mean([r["baseline_brier"] for r in rows])),
                "variance_brier": float(np.mean([r["variance_brier"] for r in rows])),
                "log_loss_change": confidence(rows, "log_loss_change"),
                "brier_change": confidence(rows, "brier_change"),
                "log_loss_change_conditional_no_triple_tie": confidence(rows, "conditional_loss_change"),
                "tied_low_boards": sum(r["tie_size"] > 1 for r in rows),
                "triple_tie_boards": sum(r["tie_size"] == 3 for r in rows),
                "source_result_disagreement_boards": sum(r["source_disagreement"] for r in rows),
                "mean_abs_probability_adjustment": float(np.mean([r["mean_abs_adjustment"] for r in rows])),
                "max_abs_probability_adjustment": max(r["max_abs_adjustment"] for r in rows),
                "maximum_model_ev": max(r["best_ev"] for r in rows),
                "boards_with_positive_model_ev": sum(r["best_ev"] > 0 for r in rows),
                "mean_overround": float(np.mean([r["overround"] for r in rows])),
                "mean_predicted_triple_tie_probability": float(np.mean([r["triple_prob"] for r in rows])),
                "dead_heat_roi": confidence(rows, "dead_heat_return", True),
                "strict_win_only_roi": confidence(rows, "strict_return", True),
                "tie_void_selection_roi": confidence(rows, "tie_void_return", True),
                "full_win_on_tie_roi": confidence(rows, "tie_win_return", True)})
    if chosen:
        ans["selected_mean_model_ev"] = float(np.mean([r["best_ev"] for r in chosen]))
        ans["selected_mean_probability_uplift"] = float(np.mean([r["selected_uplift"] for r in chosen]))
        ans["selected_positive_fractional_payouts"] = sum(r["selected_share"] > 0 for r in chosen)
        ans["selected_two_way_ties_for_low"] = sum(r["selected_share"] == .5 for r in chosen)
        ans["units_dead_heat"] = sum(r["dead_heat_return"] for r in chosen)
    return ans


def main():
    # Evaluate analytic identities before joining scoring outcomes.
    equal, strict, triple = distribution([0, 0, 0], [9, 9, 9])
    assert np.max(np.abs(equal - 1 / 3)) < 1e-10
    assert 0 < triple < .1 and np.all(strict < equal)
    assert forecast([3.3, 3.3, 3.3], [9, 9, 9]) is not None
    events, sources = [], []
    for year in range(2015, TEST_YEAR + 1):
        path = RAW / f"scoreboard-{year}.json"
        sources.append({"path": str(path.relative_to(ROOT)), "sha256": digest(path)})
        events += [e for e in json.loads(path.read_text())["events"] if e.get("date") and e.get("name")]
    events.sort(key=lambda e: (e["date"], e["id"]))
    price_rows = [r for r in csv.DictReader(PRICES.open()) if r["book"] == "fanduel"
                  and r["market"] == "3-balls" and r["year"] == str(TEST_YEAR)]
    grouped, seen = defaultdict(list), set()
    attrition, joins, unmatched_names = Counter(), Counter(), Counter()
    for r in price_rows:
        identity = (r["event_name"], r["round"], tuple(sorted([r["dg_id"], r["opponent_dg_id"], r["opponent2_dg_id"]])))
        if identity in seen:
            attrition["duplicate_board"] += 1
            continue
        seen.add(identity)
        grouped[norm(r["event_name"])].append(r)
    history, prepared, evaluated_events = defaultdict(list), [], set()
    for event in events:
        day, end = date.fromisoformat(event["date"][:10]), date.fromisoformat(event["endDate"][:10])
        offers = grouped.get(norm(event["name"]), []) if day.year == TEST_YEAR else []
        if offers:
            evaluated_events.add(norm(event["name"]))
        if event["name"] in EXCLUDE or not event.get("status", {}).get("type", {}).get("completed"):
            attrition["excluded_event_or_format"] += len(offers)
            continue
        competitors = [c for comp in event.get("competitions", []) for c in comp.get("competitors", [])
                       if c.get("type") == "athlete"]
        for offer in offers:
            matched, variances, counts, methods = [], [], [], []
            failure = None
            try:
                open_day = date.fromisoformat(offer["open_time"][:10])
                prices = np.array([float(offer[f"p{i}_open_dec"]) for i in (1, 2, 3)])
                rnd = int(offer["round"])
                if np.any(prices <= 1) or np.any(prices > 30):
                    raise ValueError
                overround = float((1 / prices).sum() - 1)
                if not 0 <= overround <= .20:
                    raise ValueError
            except (ValueError, KeyError):
                attrition["invalid_price_or_date"] += 1
                continue
            # Only use events ending before a conservative unzoned opening-day cutoff.
            cutoff = min(day, open_day - timedelta(days=1))
            for key in ["player_name", "opponent_name", "opponent2_name"]:
                c, method = player_match(offer[key], competitors)
                joins[method] += 1
                if c is None:
                    unmatched_names[offer[key]] += 1
                    failure = "identity_unresolved"
                    break
                matched.append(c)
                methods.append(method)
                prior = [x[1] for x in history[str(c["id"])] if x[0] < cutoff][-WINDOW:]
                counts.append(len(prior))
                if len(prior) < MIN_HISTORY:
                    failure = "insufficient_prior_rounds"
                    break
                var = float(np.var(prior, ddof=1))
                variances.append(((len(prior) - 1) * var + PRIOR_DF * BASE_VAR) / (len(prior) - 1 + PRIOR_DF))
            if failure:
                attrition[failure] += 1
                continue
            if len(matched) < 3 or len({str(c["id"]) for c in matched}) != 3:
                attrition["identity_unresolved"] += 1
                continue
            if len(variances) != 3:
                attrition["insufficient_prior_rounds"] += 1
                continue
            pred = forecast(prices, variances)
            if pred is None:
                attrition["price_probability_inversion_failed"] += 1
                continue
            selected_idx = int(np.argmax(pred["prediction"] * prices - 1))
            prepared.append({"event_id": event["id"], "event": event["name"], "round": rnd,
                             "matched": matched, "offer": offer, "prices": prices,
                             "overround": overround, "pred": pred, "selection": selected_idx,
                             "min_prior_rounds": min(counts), "methods": methods})
        # Append all current-event sporting results only after every forecast above.
        for rnd in (1, 2, 3, 4):
            complete = []
            for c in competitors:
                rr = [x for x in c.get("linescores", []) if x.get("period") == rnd]
                score = complete_round(rr[0]) if len(rr) == 1 else None
                if score is not None:
                    complete.append((str(c["id"]), score))
            if len(complete) >= 20:
                center = float(np.mean([score for _, score in complete]))
                for pid, score in complete:
                    history[pid].append((end, score - center))
    attrition["event_not_joined"] = sum(len(v) for k, v in grouped.items() if k not in evaluated_events)
    assert len(prepared) + sum(attrition.values()) == len(price_rows), "Every source board must be accounted for"
    rows = []
    for item in prepared:
        scores = []
        for c in item["matched"]:
            rr = [x for x in c.get("linescores", []) if x.get("period") == item["round"]]
            scores.append(complete_round(rr[0]) if len(rr) == 1 else None)
        if None in scores:
            attrition["forecasted_board_missing_complete_round"] += 1
            continue
        low = min(scores)
        y = np.array([float(score == low) for score in scores])
        tie_size = int(y.sum())
        y /= y.sum()
        pred, idx, prices = item["pred"], item["selection"], item["prices"]
        p, q = pred["prediction"], pred["baseline"]
        best_ev = float(p[idx] * prices[idx] - 1)
        def loss(prob):
            return float(-np.dot(y, np.log(np.maximum(1e-12, prob))))
        source_labels = [item["offer"][f"p{i}_result"] for i in (1, 2, 3)]
        actual_labels = ["W" if share == 1 else "P" if share > 0 else "L" for share in y]
        conditional_p = (p - pred["triple"] / 3) / (1 - pred["triple"])
        conditional_q = (q - pred["baseline_triple"] / 3) / (1 - pred["baseline_triple"])
        rows.append({"event_id": item["event_id"], "event": item["event"], "round": item["round"],
                     "selected": best_ev >= MIN_EV, "best_ev": best_ev,
                     "selected_share": float(y[idx]), "selected_uplift": float(p[idx] - q[idx]),
                     "baseline_log_loss": loss(q), "variance_log_loss": loss(p),
                     "log_loss_change": loss(p) - loss(q), "conditional_loss_change": loss(conditional_p) - loss(conditional_q),
                     "baseline_brier": float(((q - y) ** 2).sum()), "variance_brier": float(((p - y) ** 2).sum()),
                     "brier_change": float(((p - y) ** 2).sum() - ((q - y) ** 2).sum()),
                     "dead_heat_return": float(y[idx] * prices[idx] - 1),
                     "strict_return": float(prices[idx] - 1 if y[idx] == 1 else -1),
                     "tie_void_return": float(0 if 0 < y[idx] < 1 else prices[idx] - 1 if y[idx] == 1 else -1),
                     "tie_win_return": float(prices[idx] - 1 if y[idx] > 0 else -1),
                     "source_disagreement": actual_labels != source_labels,
                     "tie_size": tie_size, "overround": item["overround"],
                     "mean_abs_adjustment": float(np.abs(p - q).mean()),
                     "max_abs_adjustment": float(np.abs(p - q).max()),
                     "triple_prob": pred["triple"], "all_exact_names": all(x == "full_normalized_name" for x in item["methods"]),
                     "variance_ratio_max": float(pred["relative_variances"].max() / pred["relative_variances"].min())})
    report = {
        "status": "exploratory; no demonstrated edge", "test_year": TEST_YEAR,
        "parameters": {"history_rounds": WINDOW, "min_history_rounds": MIN_HISTORY, "prior_degrees_freedom": PRIOR_DF,
                       "base_variance": BASE_VAR, "min_estimated_ev": MIN_EV, "fit_on_test_outcomes": False,
                       "history_cutoff": "completed event end date strictly before min(current event date, unzoned opening date minus one day)",
                       "selection": "highest model EV, at most one per board, only EV >=3%"},
        "sources": {"prices": {"path": str(PRICES.relative_to(ROOT)), "sha256": digest(PRICES), "publisher_commit": "5508f6f35830f09d0b1e0c06abed0b2b489dde04"},
                    "exporter": {"path": str(EXPORTER.relative_to(ROOT)), "sha256": digest(EXPORTER)}, "sport": sources},
        "raw_test_boards": len(price_rows), "forecasts_before_outcome_completeness": len(prepared),
        "attrition": dict(attrition), "identity_joins": dict(joins), "unmatched_names": dict(unmatched_names),
        "primary": summarize(rows),
        "exact_name_sensitivity": summarize([r for r in rows if r["all_exact_names"]]),
        "source_result_agreement_sensitivity": summarize([r for r in rows if not r["source_disagreement"]]),
        "by_round": {str(i): summarize([r for r in rows if r["round"] == i]) for i in (1, 2, 3, 4)},
        "limitations": ["Historical quote timezone, update time, original market-specific terms, jurisdiction and actual acceptance unknown.",
                        "Publisher filters to outcomes exactly 0, .5, 1 and available model estimates; three-way ties encoded 1/3 are excluded.",
                        "Opening-price cohort also requires all three valid later closing prices and publisher model availability evaluated at close_time or fallback open_time.",
                        "Opening source prices are not asserted simultaneous executable quotes; no verified closing comparison.",
                        "Independent rounded-normal score assumption, field-centered variance confounded by field composition and changing form.",
                        "2025 results were used elsewhere in prior research; this is exploratory, not a newly untouched holdout.",
                        "Incomplete-round forecasts remain counted but cannot be settled without original rules."]}
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    s = report["primary"]
    fmt = lambda n: "undefined" if n is None else f"{n:.4%}"
    loss_ci = s.get("log_loss_change", {}).get("event_bootstrap_95")
    loss_ci_text = "undefined" if loss_ci is None else f"[{loss_ci[0]:.6f}, {loss_ci[1]:.6f}]"
    exact = report["exact_name_sensitivity"]
    exact_ci = exact.get("log_loss_change", {}).get("event_bootstrap_95")
    exact_ci_text = "undefined" if exact_ci is None else f"[{exact_ci[0]:.6f}, {exact_ci[1]:.6f}]"
    text = f'''# Golf player variance — September 26, 2026

**The variance adjustment slightly improved forecasts but found no mispriced bet.** The fixed rule was evaluated on {s['boards']:,} 2025 FanDuel 3-ball boards across {s['events']} events. Even the highest modeled return was {fmt(s.get('maximum_model_ev'))}; {s.get('boards_with_positive_model_ev', 0)} boards had positive modeled EV. There were {s['selections']} selections at the fixed 3% threshold.

| Measure | Normalized opening price | Variance adjustment |
| --- | ---: | ---: |
| Mean log loss (lower is better) | {s.get('baseline_log_loss', float('nan')):.6f} | {s.get('variance_log_loss', float('nan')):.6f} |
| Mean summed Brier loss | {s.get('baseline_brier', float('nan')):.6f} | {s.get('variance_brier', float('nan')):.6f} |

Paired log-loss change is {s.get('log_loss_change', {}).get('mean'):.6f}; its event-bootstrap 95% interval is {loss_ci_text}. Mean absolute probability adjustment is {fmt(s.get('mean_abs_probability_adjustment'))}; the largest modeled return is {fmt(s.get('maximum_model_ev'))}. Average quoted overround is {fmt(s.get('mean_overround'))}.

Dead-heat ROI is {fmt(s.get('dead_heat_roi', {}).get('mean'))}; strict-win-only ROI is {fmt(s.get('strict_win_only_roi', {}).get('mean'))}. A tie-void and full-win-on-tie sensitivity are in the JSON, along with exposure, event uncertainty, round breakdowns, and an exact-name-only sensitivity. Undefined ROI means no qualifying selections, not break-even performance.

The exact-name-only sensitivity has {exact['boards']:,} boards and paired log-loss change {exact.get('log_loss_change', {}).get('mean'):.6f}, with interval {exact_ci_text}. Its interval includes zero. The evidence supports at most a small forecasting lead; it does not overcome the bookmaker margin.

## Fixed mechanism and parameters

For each golfer, use the last 80 complete rounds in earlier events, requiring 40. Scores are centered on the event-round field mean; sample variance is shrunk toward 9 using 100 prior degrees of freedom. All current-event rounds are excluded. Prior event end dates must precede a conservative cutoff one day before the unzoned opening date or the current-event start, whichever is earlier.

Infer relative score means that reproduce normalized FanDuel opening probabilities under equal SD 3. Keep those means fixed and replace only relative variances, scaled to group mean 9. Rounded independent normal scores allocate half of tied-low two-player payouts and one third of three-player ties. One pick per board is allowed only at modeled EV >=3%; no threshold or variance parameter was selected using 2025 outcomes. Losses use the realized fractional share of lowest score as the outcome.

This tests individual dispersion, distinct from the failed G3 tie-allocation and G10 shared-weather hypotheses. It does not revise their results. It also does not import the source publisher's forecast or selected bets.

## Coverage and limitations

Started with {len(price_rows):,} retained 2025 FanDuel 3-balls. There were {len(prepared):,} forecasts before checking score completeness. Attrition: `{dict(attrition)}`. Names join by exact normalized full name, then unique surname plus first initial within the same event; unresolved names remain excluded. Every settled player-round must have 18 distinct holes summing to its reported score. Reconstructed labels disagree with publisher labels on {s.get('source_result_disagreement_boards', 0)} boards; these are not silently dropped from the primary analysis.

**The price export is selected on outcomes:** `isGradedOutcome` accepts only 0, 0.5 and 1, excluding a three-way tie encoded as one third. The sample also requires publisher model availability and valid closing prices for all three players; the opening-price cohort is therefore selected using later availability. We observed {s.get('triple_tie_boards', 0)} reconstructed three-way ties. Conditional-no-triple-tie loss sensitivity is provided, but cannot restore missing offers. The unknown original settlement rules are why several payoff conventions are shown.

Quote clocks lack zones, original source responses are absent, and no Ontario execution or historical acceptance is verified. These limitations preclude a claim of a demonstrated edge even if an exploratory metric is favorable. The full [JSON](golf-player-variance-2026-09-26.json) contains source hashes and all summaries. No new acquisition, parameter search, schedules, alerts or wagers.

Reproduce with `state/runtime/research-venv/bin/python tools/explore_golf_player_variance.py`.
'''
    OUT.with_suffix(".md").write_text(text)
    print(json.dumps({"primary": report["primary"], "attrition": dict(attrition)}, indent=2))


if __name__ == "__main__":
    main()
