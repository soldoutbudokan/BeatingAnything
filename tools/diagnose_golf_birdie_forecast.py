"""Fixed, exploratory forecast diagnostic of the September 23 birdie lead.

No fitting or threshold search: prior 40 complete PGA rounds, Poisson count
forecast, and the original line >= mean - 0.5 Under trigger. Input joins and
offered prices come from recheck_golf_birdie_prices.py. These are source-designated
opening prices; the file has fixture times, not verified quote timestamps.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / "data/raw/golf-birdie-recheck-2026-09-26/under-diagnostic.csv"
HISTORY = ROOT / "data/raw/golf-birdie-recheck-2026-09-26/historical_rounds_all.csv"
PREDICTIONS = ROOT / "data/raw/golf-birdie-recheck-2026-09-26/forecast-diagnostic.csv"
JSON_OUT = ROOT / "reports/golf-birdie-forecast-2026-09-26.json"
MD_OUT = ROOT / "reports/golf-birdie-forecast-2026-09-26.md"


def decimal(american):
    a = np.asarray(american, dtype=float)
    if np.any(~np.isfinite(a)) or np.any(np.abs(a) < 100):
        raise ValueError("Invalid stored American odds")
    return np.where(a > 0, 1 + a / 100, 1 + 100 / np.abs(a))


def poisson_probs(mu, line):
    """Under, push, over for the stated count threshold; no fitted parameters."""
    if not np.isfinite(mu) or mu < 0 or not np.isfinite(line) or line < 0:
        raise ValueError("Invalid Poisson mean or line")
    mass = math.exp(-mu)
    under = 0.0
    push = 0.0
    for k in range(math.floor(line) + 1):
        if k < line:
            under += mass
        elif k == line:
            push = mass
        mass *= mu / (k + 1)
    over = 1 - under - push
    if min(under, push, over) < -1e-12:
        raise ValueError("Invalid Poisson probability sum")
    return under, push, max(0.0, over)


def interval(frame, value):
    """Event block bootstrap, descriptive 95%; no multiple-search adjustment."""
    if frame.empty:
        return None
    groups = frame.groupby(["year", "event_id"])[value].agg(["sum", "count"])
    rng = np.random.default_rng(1729)
    draws = rng.integers(len(groups), size=(10000, len(groups)))
    means = groups["sum"].to_numpy()[draws].sum(axis=1) / groups["count"].to_numpy()[draws].sum(axis=1)
    return np.quantile(means, [0.025, 0.975]).tolist()


def summarize(frame):
    if frame.empty:
        return {"n": 0}
    paired = frame[frame.market_under_conditional.notna()].copy()
    overround = (1 / decimal(paired.opening_under_american) +
                 1 / decimal(paired.opening_over_american) - 1)
    losses = paired[paired.result != "push"].copy()
    y = (losses.result == "win").astype(float)
    for name, p in [("model", losses.model_under_conditional), ("market", losses.market_under_conditional)]:
        p = np.clip(p.to_numpy(), 1e-12, 1 - 1e-12)
        losses[name + "_logloss"] = -(y * np.log(p) + (1 - y) * np.log1p(-p))
        losses[name + "_brier"] = (p - y) ** 2
    losses["logloss_difference"] = losses.model_logloss - losses.market_logloss
    losses["brier_difference"] = losses.model_brier - losses.market_brier
    scored = {"n_nonpush_paired": len(losses),
              "paired_boards_including_pushes": int(frame.market_under_conditional.notna().sum()),
              "events": int(losses.groupby(["year", "event_id"]).ngroups),
              "negative_opening_overround_pairs": int((overround < 0).sum()),
              "opening_overround_range": [float(overround.min()), float(overround.max())] if len(overround) else None}
    for name in ["model_logloss", "market_logloss", "model_brier", "market_brier",
                 "logloss_difference", "brier_difference"]:
        scored[name] = float(losses[name].mean()) if len(losses) else None
    scored["logloss_difference_event_bootstrap_95pct"] = interval(losses, "logloss_difference")
    scored["brier_difference_event_bootstrap_95pct"] = interval(losses, "brier_difference")
    return {
        "n": len(frame), "events": int(frame.groupby(["year", "event_id"]).ngroups),
        "wins": int((frame.result == "win").sum()), "losses": int((frame.result == "loss").sum()),
        "pushes": int((frame.result == "push").sum()),
        "units": float(frame.profit.sum()), "roi": float(frame.profit.mean()),
        "roi_event_bootstrap_95pct": interval(frame, "profit"),
        "mean_model_ev": float(frame.model_ev.mean()),
        "mean_bob_forecast": float(frame.mean40.mean()), "mean_actual_bob": float(frame.actual_birdies_or_better.mean()),
        "mean_p_under": float(frame.p_under.mean()), "mean_p_push": float(frame.p_push.mean()),
        "mean_p_over": float(frame.p_over.mean()),
        "forecast_vs_market": scored,
        "by_year": {str(int(year)): {"n": len(g), "units": float(g.profit.sum()),
                    "roi": float(g.profit.mean()), "mean_model_ev": float(g.model_ev.mean())}
                    for year, g in frame.groupby("year")},
    }


def main():
    detail_bytes = DETAIL.read_bytes()
    history_bytes = HISTORY.read_bytes()
    d = pd.read_csv(DETAIL)
    h = pd.read_csv(HISTORY)
    h = h[h.tour == "pga"].copy()
    h["completed_date"] = pd.to_datetime(h.event_completed, format="mixed", errors="raise")
    stats = ["birdies", "eagles_or_better", "pars", "bogies", "doubles_or_worse"]
    h["holes"] = h[stats].sum(axis=1, min_count=len(stats))
    h = h[(h.holes == 18) & (h[stats] >= 0).all(axis=1)].copy()
    h["bob"] = h.birdies + h.eagles_or_better
    if h.duplicated(["year", "event_id", "dg_id", "round_num"]).any():
        raise ValueError("Repeated historical player round")
    h = h.sort_values(["completed_date", "round_num", "year", "event_id"])
    history_by_player = {int(k): g for k, g in h.groupby("dg_id", sort=False)}
    records = []
    exclusions = {}
    for _, row in d.iterrows():
        if row.join_status != "complete":
            reason = "source_join_" + row.join_status
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        date = pd.Timestamp(row.EVENT_START_TIME_UTC).tz_localize(None).normalize()
        prior = history_by_player.get(int(row.dg_id))
        if prior is None:
            prior = h.iloc[0:0]
        else:
            prior = prior[(prior.completed_date < date) &
                          ~((prior.year == row.year) & (prior.event_id == row.event_id))]
        if len(prior) < 40:
            exclusions["fewer_than_40_prior_complete_pga_rounds"] = exclusions.get("fewer_than_40_prior_complete_pga_rounds", 0) + 1
            continue
        prior = prior.tail(40)
        if not (prior.completed_date < date).all() or ((prior.year == row.year) & (prior.event_id == row.event_id)).any():
            raise ValueError("Future/current-event information in forecast")
        mu = float(prior.bob.mean())
        pu, pp, po = poisson_probs(mu, float(row.line))
        dec = float(decimal([row.OPENING_AMERICAN_ODDS])[0])
        actual = float(row.actual_birdies_or_better)
        result = "win" if actual < row.line else "loss" if actual > row.line else "push"
        market_p = None
        if pd.notna(row.over_OPENING_AMERICAN_ODDS):
            implied_under = 1 / dec
            implied_over = 1 / float(decimal([row.over_OPENING_AMERICAN_ODDS])[0])
            market_p = implied_under / (implied_under + implied_over)
        records.append({
            "year": int(row.year), "event_id": int(row.event_id), "dg_id": int(row.dg_id),
            "player": row.matched_player, "event": row.matched_event,
            "round": int(row.round_num), "fixture_time": row.EVENT_START_TIME_UTC,
            "instrument_id": str(row.INSTRUMENT_ID), "line": float(row.line),
            "opening_under_american": float(row.OPENING_AMERICAN_ODDS),
            "opening_over_american": float(row.over_OPENING_AMERICAN_ODDS) if pd.notna(row.over_OPENING_AMERICAN_ODDS) else None,
            "history_last_completed": prior.completed_date.max().date().isoformat(),
            "history_first_completed": prior.completed_date.min().date().isoformat(),
            "history_rounds": 40, "mean40": mu,
            "trigger": bool(row.line >= mu - 0.5),
            "p_under": pu, "p_push": pp, "p_over": po,
            "model_under_conditional": pu / (1 - pp), "market_under_conditional": market_p,
            "model_ev": pu * (dec - 1) - po,
            "actual_birdies_or_better": actual, "result": result,
            "profit": dec - 1 if result == "win" else -1.0 if result == "loss" else 0.0,
        })
    f = pd.DataFrame(records)
    results = {}
    for label, mask in [("2023_2025", f.year.between(2023, 2025)), ("2026", f.year == 2026)]:
        cohort = f[mask]
        results[label] = {"all_history_eligible_observed_unders": summarize(cohort),
                          "original_fixed_trigger": summarize(cohort[cohort.trigger]),
                          "complement_of_trigger": summarize(cohort[~cohort.trigger])}
    f.to_csv(PREDICTIONS, index=False)
    report = {
        "status": "exploratory fixed-rule forecast diagnostic; no demonstrated forecasting edge",
        "analysis_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sources": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(b).hexdigest()}
                    for p, b in [(DETAIL, detail_bytes), (HISTORY, history_bytes)]],
        "rule": {"stat": "birdies + eagles_or_better", "history_rounds": 40,
                 "minimum_history_rounds": 40, "trigger": "line >= mean40 - 0.5",
                 "forecast": "Poisson(lambda=mean40); no fitted parameters",
                 "history_availability": "event_completed strictly earlier than fixture UTC calendar date; whole current event excluded",
                 "ordering": "event_completed then round_num; deterministic year/event_id tie-breaks",
                 "market_baseline": "proportionally normalized actual opening Under/Over implied probabilities, conditional on nonpush",
                 "selection": "original trigger only; no EV filter, new threshold, or parameter search"},
        "probability_model_scope": "Poisson is a newly specified, unfitted diagnostic of the count-skew explanation; the original report did not define a probability distribution.",
        "inventory": {"offered_input_rows": len(d), "history_eligible_graded_rows": len(f),
                      "exclusions": exclusions, "by_year": f.groupby("year").size().to_dict()},
        "results": results,
        "limitations": [
            "Historical returns and periods are exploratory; neither period is an untouched holdout.",
            "Actual opening quote times and simultaneous availability of paired sides are absent; fixture time is only an availability proxy.",
            "Seven history-eligible paired boards have negative opening overround; normalized comparisons are descriptive and do not authenticate simultaneous quotes. No outcome-dependent filter removes them.",
            "Source collection/selection and executable-price provenance are unresolved; input is a retrospective third-party export.",
            "Historical Hard Rock plain birdies versus birdies-or-better contract remains unverified; birdies-or-better is the declared primary diagnostic.",
            "Source join exclusions and fewer-than-40-round exclusions are reported; forecasts and scores require resolved complete outcomes.",
            "All 95% intervals resample whole events and are uncorrected for the earlier searches.",
            "The Poisson model omits course, weather, player changes and dispersion; it tests only the proposed trailing-mean/count-skew mechanism.",
        ],
        "predictions": {"path": str(PREDICTIONS.relative_to(ROOT)), "rows": len(f),
                        "sha256": hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest()},
    }
    if DETAIL.read_bytes() != detail_bytes:
        raise RuntimeError("Input detail changed during run; rerun after upstream completes")
    JSON_OUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Golf birdie forecasting diagnostic — September 26, 2026", "",
             "**The historical profit survives, but the proposed forecasting mechanism does not demonstrate an advantage over the market.** The fixed trigger returns +11.05% in 2023–2025 and +1.09% in 2026. Its Poisson forecast has worse point estimates for log loss and Brier score in both periods, including on the triggered contracts alone.", "",
             "The September 23 mean-versus-line idea was tested without fitting parameters or searching thresholds. The fixed Under trigger is `line >= trailing 40-round mean - 0.5`. **Poisson is a newly specified, unfitted probability model for diagnosing the original count-skew explanation; the original report did not specify a distribution.** The mean and forecast use birdies plus eagles-or-better from complete PGA rounds whose event finished before the fixture's UTC date; the whole current event is excluded. At least 40 prior rounds are required.", "",
             "| Period | Observed Under universe | Bets | ROI | Mean model EV | Paired nonpush forecasts | Model minus market log loss |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, res in results.items():
        for key, caption in [("all_history_eligible_observed_unders", "All eligible"), ("original_fixed_trigger", "Original trigger")]:
            value = res[key]
            scores = value["forecast_vs_market"]
            lines.append(f"| {label.replace('_', '–')} | {caption} | {value['n']} | {value['roi']:.2%} | {value['mean_model_ev']:.2%} | {scores['n_nonpush_paired']} | {scores['logloss_difference']:+.5f} |")
    lines += ["", "Positive loss differences mean the Poisson forecast is worse than the opening market. Forecast scores compare both forecasts on the same observed paired contracts after removing realized pushes; the Poisson Under probability is divided by one minus its push probability. Prices are the recorded opening American prices. Returns retain pushes as zero-profit stakes. Missing opposite prices are never created, and closing columns are unused.", ""]
    for label, res in results.items():
        all_ = res["all_history_eligible_observed_unders"]
        trig = res["original_fixed_trigger"]
        scores = all_["forecast_vs_market"]
        ci = trig["roi_event_bootstrap_95pct"]
        lci = scores["logloss_difference_event_bootstrap_95pct"]
        trigger_lci = trig["forecast_vs_market"]["logloss_difference_event_bootstrap_95pct"]
        lines.append(f"- **{label.replace('_', '–')}:** trigger {trig['wins']} wins, {trig['losses']} losses, {trig['pushes']} pushes; {trig['units']:+.2f} units across {trig['events']} events. Exploratory event-bootstrap ROI interval [{ci[0]:.2%}, {ci[1]:.2%}]. All-eligible paired log-loss difference interval [{lci[0]:+.5f}, {lci[1]:+.5f}]; Brier difference {scores['brier_difference']:+.5f}. Trigger-only log-loss difference interval [{trigger_lci[0]:+.5f}, {trigger_lci[1]:+.5f}].")
    lines += ["", f"Input contains {len(d)} observed Under contracts; {len(f)} have resolved full-round outcomes and 40 prior rounds. Exclusions: " + "; ".join(f"{k}: {v}" for k, v in exclusions.items()) + ".", "",
              "These are descriptive diagnostics of an already inspected source. The historical contract's settlement definition, opening quote times, simultaneity, collection universe, and executable-price provenance remain unresolved. Three historical and four 2026 eligible pairs have negative opening overround, further limiting the interpretation of the source-designated market benchmark. None is removed using outcomes. Event-bootstrap intervals are not adjusted for the preceding research searches. Source hashes, cohort/year splits, and scoring details are in the [JSON report](golf-birdie-forecast-2026-09-26.json); individual probabilities and predictions remain in the ignored local raw-data directory at the path and hash recorded there."]
    MD_OUT.write_text("\n".join(lines) + "\n")
    print(json.dumps({"inventory": report["inventory"], "results": results}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
