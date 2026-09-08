"""Frozen N2/N3 evaluation of same-line Pinnacle total-games forecasts.

The caller supplies an early-feature-valid event universe and already audited
same-line closing pairs. Missing outcomes are ungraded, not losses or voids.
No current-match result or closing field participates in selecting a bet.
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .evaluate import block_interval
from .model import losses

CONFIDENCE = 1 - .05 / 13
BOOTSTRAP_SAMPLES = 10000
BOOTSTRAP_SEED = 1729


def _probabilities(values, size, name):
    p = np.asarray(values, dtype=float)
    if p.shape != (size,) or not np.isfinite(p).all() or not ((p > 0) & (p < 1)).all():
        raise ValueError(f"{name} must contain one finite probability strictly between 0 and 1 per event")
    return p


def fair_pair(a, b, power=False):
    """Over probability from an audited closing pair; invalid pairs stay missing."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.ndim != 1 or a.shape != b.shape:
        raise ValueError("Closing prices must be equally sized one-dimensional arrays")
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        r, s = 1 / a, 1 / b
        vig = r + s - 1
        valid = np.isfinite(a) & np.isfinite(b) & (a > 1) & (b > 1)
        valid &= (vig >= -1e-10) & (vig <= .15 + 1e-10)
        p = np.where(valid, r / (r + s), np.nan)
    if power:
        for i in np.flatnonzero(valid):
            exponent = brentq(lambda k: r[i] ** k + s[i] ** k - 1, .01, 100)
            p[i] = r[i] ** exponent
    return p


def decisions(frame, p):
    """Apply the fixed entry policy using only forecasts and early paired odds."""
    p = _probabilities(p, len(frame), "Forecasts")
    a, b = frame.odds_a.to_numpy(float), frame.odds_b.to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        ev_a, ev_b = p * a - 1, (1 - p) * b - 1
        over = ev_a >= ev_b
        odds = np.where(over, a, b)
        ev = np.maximum(ev_a, ev_b)
        vig = 1 / a + 1 / b - 1
        valid_pair = np.isfinite(a) & np.isfinite(b) & (a > 1) & (b > 1)
        selected = valid_pair & (ev >= .03 - 1e-12) & (odds >= 1.2) & (odds <= 6)
        selected &= (vig >= -1e-10) & (vig <= .10 + 1e-10)
    return {"over": over, "odds": odds, "ev": ev, "selected": selected}


def interval(frame, numerator, denominator=None):
    """Resample calendar weeks, preserving all events within each sampled week."""
    return block_interval(frame.date, numerator, denominator,
                          confidence=CONFIDENCE, n_boot=BOOTSTRAP_SAMPLES,
                          seed=BOOTSTRAP_SEED)


def _mean(values):
    return float(np.mean(values)) if len(values) else None


def _bounds(known_profit, unresolved_winnings, turnover):
    if not turnover:
        return [None, None]
    return [float((known_profit - len(unresolved_winnings)) / turnover),
            float((known_profit + unresolved_winnings.sum()) / turnover)]


def describe(frame, p, with_ci=True):
    """Describe one fixed cohort; returns JSON-safe values even when empty.

    Required columns: event_id, date, y, odds_a, odds_b, market_p, close_a,
    close_b. ``a`` always denotes Over 21.5; ``b`` denotes Under 21.5.
    Closing activity, timestamp and same-line checks belong to acquisition:
    rejected or unavailable closing evidence must arrive here as NaN.
    """
    required = {"event_id", "date", "y", "odds_a", "odds_b", "market_p", "close_a", "close_b"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing evaluation columns: {', '.join(sorted(missing))}")
    if frame.event_id.isna().any() or frame.event_id.duplicated().any():
        raise ValueError("Evaluation requires unique, nonmissing event IDs")
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="raise").dt.tz_localize(None)
    if frame.date.isna().any():
        raise ValueError("Every event needs a calendar date")
    p = _probabilities(p, len(frame), "Forecasts")
    market = _probabilities(frame.market_p, len(frame), "Market forecasts")
    y = frame.y.to_numpy(float)
    settled = ~np.isnan(y)
    if not np.isin(y[settled], [0, 1]).all():
        raise ValueError("Outcomes must be completed-match binary Over 21.5 results or NaN")

    d = decisions(frame, p)
    selected, over, odds = d["selected"], d["over"], d["odds"]
    selected_settled = selected & settled
    unresolved = selected & ~settled
    n, ns = int(selected.sum()), int(selected_settled.sum())
    wins = (over == (y == 1)) & settled
    profit = np.zeros(len(frame), dtype=float)
    haircut = np.zeros(len(frame), dtype=float)
    profit[selected_settled] = np.where(wins[selected_settled], odds[selected_settled] - 1, -1)
    haircut[selected_settled] = np.where(wins[selected_settled], .98 * (odds[selected_settled] - 1), -1)
    known_profit, haircut_profit = float(profit.sum()), float(haircut.sum())
    daily = pd.DataFrame({"day": frame.date.dt.normalize(), "profit": profit}).groupby("day").profit.sum()
    cumulative = np.r_[0., np.cumsum(daily.to_numpy())]
    model_losses = losses(y[settled], p[settled])
    market_losses = losses(y[settled], market[settled])
    delta = model_losses - market_losses
    brier = (p[settled] - y[settled]) ** 2
    market_brier = (market[settled] - y[settled]) ** 2
    bet_dates = frame.loc[selected, "date"].dt.normalize()
    finite_ev = d["ev"][np.isfinite(d["ev"])]

    result = {
        "events": len(frame), "bets": n, "turnover_units": n,
        "settled_events": int(settled.sum()), "missing_event_outcomes": int((~settled).sum()),
        "settled_bets": ns, "unsettled_bets": n - ns,
        "profit_units_settled": known_profit, "haircut_profit_units_settled": haircut_profit,
        "roi": known_profit / n if n and n == ns else None,
        "roi_settled_only": known_profit / ns if ns else None,
        "roi_unresolved_outcome_bounds": _bounds(known_profit, odds[unresolved] - 1, n),
        "haircut_roi": haircut_profit / n if n and n == ns else None,
        "haircut_roi_settled_only": haircut_profit / ns if ns else None,
        "haircut_roi_unresolved_outcome_bounds": _bounds(haircut_profit, .98 * (odds[unresolved] - 1), n),
        "complete_match_simulation": {
            "bets": ns, "turnover_units": ns, "profit_units": known_profit,
            "roi": known_profit / ns if ns else None,
            "haircut_roi": haircut_profit / ns if ns else None,
            "scope": "Selected completed normal matches only; excludes ungraded selected exposure",
        },
        "log_loss": _mean(model_losses), "market_log_loss": _mean(market_losses),
        "brier": _mean(brier), "market_brier": _mean(market_brier),
        "paired_log_loss_delta": _mean(delta),
        "paired_brier_delta": _mean(brier - market_brier),
        "paired_loss_events": int(settled.sum()),
        "max_drawdown_daily_units": float(np.max(np.maximum.accumulate(cumulative) - cumulative)),
        "drawdown_scope": "End-of-day settled profit; excludes intraday fluctuations and ungraded exposure",
        "bet_days": int(bet_dates.nunique()),
        "calendar_span_days": int((bet_dates.max() - bet_dates.min()).days + 1) if n else 0,
        "max_model_ev": float(finite_ev.max()) if len(finite_ev) else None,
        "confidence": CONFIDENCE, "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_block": "calendar week ending Sunday",
        "multiple_comparison_allowance": 13,
        "execution_verified": False, "entry_book": "Pinnacle", "fanduel_evidence": False,
        "market": "ATP Challenger full-match total 21.5 games",
        "closing_evidence": "Source-designated historical same-line Pinnacle final paired prices; execution unverified",
    }
    if with_ci:
        result.update(
            roi_ci=interval(frame, profit, selected) if n == ns else [None, None],
            haircut_roi_ci=interval(frame, haircut, selected) if n == ns else [None, None],
            paired_log_loss_delta_ci=interval(frame.loc[settled], delta),
            paired_brier_delta_ci=interval(frame.loc[settled], brier - market_brier),
        )
        result["complete_match_simulation"].update(
            roi_ci=interval(frame, profit, selected_settled),
            haircut_roi_ci=interval(frame, haircut, selected_settled),
        )

    for key, power in (("closing_pinnacle", False), ("closing_pinnacle_power", True)):
        q = fair_pair(frame.close_a, frame.close_b, power)
        valid = np.isfinite(q)
        covered = selected & valid
        nq = int(covered.sum())
        side_q = np.where(over, q, 1 - q)
        close_price = np.where(over, frame.close_a.to_numpy(float), frame.close_b.to_numpy(float))
        clv, ratio = np.zeros(len(frame)), np.zeros(len(frame))
        clv[covered] = odds[covered] * side_q[covered] - 1
        ratio[covered] = odds[covered] / close_price[covered] - 1
        comparable = valid & settled
        close_losses = losses(y[comparable], q[comparable])
        loss_delta = losses(y[comparable], p[comparable]) - close_losses
        node = {
            "covered_bets": nq, "missing_bets": n - nq,
            "selected_close_coverage": nq / n if n else None,
            "all_event_close_coverage": int(valid.sum()),
            "all_event_missing_closes": int((~valid).sum()),
            "mean_closing_ev": float(clv.sum() / nq) if nq else None,
            "mean_raw_price_ratio": float(ratio.sum() / nq) if nq else None,
            "paired_loss_events": int(comparable.sum()),
            "close_log_loss_on_available": _mean(close_losses),
            "model_log_loss_on_close_available": _mean(losses(y[comparable], p[comparable])),
            "paired_log_loss_delta_vs_close": _mean(loss_delta),
            "devig": "power" if power else "proportional",
            "scope": "Selected bets with available valid same-line closing pairs; missing closes remain in total turnover",
        }
        if with_ci:
            node.update(
                mean_closing_ev_ci=interval(frame, clv, covered),
                mean_raw_price_ratio_ci=interval(frame, ratio, covered),
                paired_log_loss_delta_vs_close_ci=interval(frame.loc[comparable], loss_delta),
            )
        result[key] = node
    return result


def gates(result):
    """Fixed historical screen; it can never promote a FanDuel betting alert."""
    def lower(value):
        return value is not None and value[0] is not None and np.isfinite(value[0]) and value[0] > 0

    def upper(value):
        return value is not None and value[1] is not None and np.isfinite(value[1]) and value[1] < 0

    close = result["closing_pinnacle"]
    return {
        "positive_corrected_haircut_roi": bool(lower(result.get("haircut_roi_ci"))),
        "positive_corrected_closing_ev": bool(lower(close.get("mean_closing_ev_ci"))),
        "negative_corrected_paired_loss": bool(upper(result.get("paired_log_loss_delta_ci"))),
        "complete_selected_close_coverage": result["bets"] > 0 and close["missing_bets"] == 0,
        "complete_selected_settlements": result["bets"] > 0 and result["unsettled_bets"] == 0,
    }
