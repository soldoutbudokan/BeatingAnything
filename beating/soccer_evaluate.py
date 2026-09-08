"""Frozen N1 evaluation: entry decisions cannot depend on closing availability."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .evaluate import block_interval
from .model import losses

CONFIDENCE = .99375
CANDIDATES = ("calibration", "consensus", "structure")


def fair_pair(a, b, power=False):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r, s = 1/a, 1/b
        vig = r+s-1
        valid = np.isfinite(a) & np.isfinite(b) & (a > 1) & (b > 1)
        valid &= (vig >= -1e-10) & (vig <= .15 + 1e-10)
        p = np.where(valid, r/(r+s), np.nan)
    if power:
        for i in np.flatnonzero(valid):
            k = brentq(lambda z: r[i]**z+s[i]**z-1, .01, 100)
            p[i] = r[i]**k
    return p


def decisions(frame, p):
    """Uses no closing, result, season or league field."""
    p = np.asarray(p, float)
    a, b = frame.odds_a.to_numpy(float), frame.odds_b.to_numpy(float)
    if not (np.isfinite(p).all() and ((p > 0) & (p < 1)).all()):
        raise ValueError("Every forecast must be finite and strictly probabilistic")
    over = p*a-1 >= (1-p)*b-1
    odds = np.where(over, a, b)
    ev = np.maximum(p*a-1, (1-p)*b-1)
    vig = 1/a+1/b-1
    selected = (ev >= .03) & (odds >= 1.2) & (odds <= 6)
    selected &= (vig >= -1e-10) & (vig <= .10+1e-10)
    return {"over":over, "odds":odds, "ev":ev, "selected":selected}


def interval(frame, numerator, denominator=None):
    return block_interval(frame.date, numerator, denominator,
                          confidence=CONFIDENCE, n_boot=10000, seed=1729)


def describe(frame, p, with_ci=True):
    p = np.asarray(p, float)
    y = frame.y.to_numpy(float)
    settled = np.isfinite(y)
    if not np.isin(y[settled], [0, 1]).all():
        raise ValueError("Known soccer outcomes must be binary 2.5-goal results")
    d = decisions(frame, p)
    selected, over, odds = d["selected"], d["over"], d["odds"]
    n = int(selected.sum())
    ns = int((selected & settled).sum())
    unresolved = selected & ~settled
    wins = (over == (y == 1)) & settled
    profit = np.where(selected & settled, np.where(wins, odds-1, -1), 0.)
    haircut = np.where(selected & settled, np.where(wins, .98*(odds-1), -1), 0.)
    daily_profit = pd.DataFrame({"day":frame.date.dt.normalize(), "profit":profit}).groupby("day").profit.sum()
    cumulative = np.r_[0., np.cumsum(daily_profit)]
    delta = losses(y[settled], p[settled])-losses(y[settled], frame.market_p.to_numpy()[settled])
    result = {
        "events":len(frame), "bets":n, "turnover_units":n,
        "settled_events":int(settled.sum()), "missing_event_outcomes":int((~settled).sum()),
        "settled_bets":ns, "unsettled_bets":n-ns,
        "profit_units_settled":float(profit.sum()),
        "roi":float(profit.sum()/n) if n and n == ns else None,
        "roi_settled_only":float(profit.sum()/ns) if ns else None,
        "roi_unresolved_outcome_bounds":[float((profit.sum()-(n-ns))/n), float((profit.sum()+(odds[unresolved]-1).sum())/n)] if n else [None, None],
        "haircut_roi":float(haircut.sum()/n) if n and n == ns else None,
        "log_loss":float(losses(y[settled], p[settled]).mean()),
        "market_log_loss":float(losses(y[settled], frame.market_p.to_numpy()[settled]).mean()),
        "brier":float(np.mean((p[settled]-y[settled])**2)),
        "paired_log_loss_delta":float(delta.mean()),
        "max_drawdown_daily_units":float(np.max(np.maximum.accumulate(cumulative)-cumulative)),
        "drawdown_scope":"end-of-day; excludes intraday fluctuations and unsettled exposure",
        "bet_days":int(frame.loc[selected, "date"].nunique()),
        "calendar_span_days":int((frame.loc[selected, "date"].max()-frame.loc[selected, "date"].min()).days+1) if n else 0,
        "max_model_ev":float(d["ev"].max()) if len(frame) else None,
        "execution_verified":False, "entry_book":"Bet365", "fanduel_evidence":False,
    }
    if with_ci:
        result.update(roi_ci=interval(frame, profit, selected) if n == ns else [None, None],
                      haircut_roi_ci=interval(frame, haircut, selected) if n == ns else [None, None],
                      paired_log_loss_delta_ci=interval(frame.loc[settled], delta))
    for key, cols, power in (
        ("closing_average", ("close_a", "close_b"), False),
        ("closing_bet365", ("book_close_a", "book_close_b"), False),
        ("closing_average_power", ("close_a", "close_b"), True),
        ("closing_bet365_power", ("book_close_a", "book_close_b"), True),
    ):
        q = fair_pair(frame[cols[0]], frame[cols[1]], power)
        valid = np.isfinite(q)
        covered = selected & valid
        nq = int(covered.sum())
        side_q = np.where(over, q, 1-q)
        clv = np.where(covered, odds*side_q-1, 0.)
        close_price = np.where(over, frame[cols[0]], frame[cols[1]])
        ratio = np.where(covered, odds/close_price-1, 0.)
        comparable = valid & settled
        loss_delta = losses(y[comparable], p[comparable])-losses(y[comparable], q[comparable])
        node = {"covered_bets":nq, "missing_bets":n-nq,
                "all_event_close_coverage":int(valid.sum()),
                "mean_closing_ev":float(clv.sum()/nq) if nq else None,
                "mean_raw_price_ratio":float(ratio.sum()/nq) if nq else None,
                "paired_loss_events":int(comparable.sum()),
                "close_log_loss_on_available":float(losses(y[comparable], q[comparable]).mean()) if comparable.any() else None,
                "paired_log_loss_delta_vs_close":float(loss_delta.mean()) if comparable.any() else None}
        if with_ci:
            node["mean_closing_ev_ci"] = interval(frame, clv, covered)
            node["paired_log_loss_delta_vs_close_ci"] = interval(frame.loc[comparable], loss_delta)
        result[key] = node
    return result


def gates(result):
    """A research screen; even a pass never qualifies an executable bet."""
    def lower(v):
        return v and v[0] is not None and v[0] > 0
    def upper(v):
        return v and v[1] is not None and v[1] < 0
    clv = result["closing_average"]
    return {
        "positive_corrected_haircut_roi":bool(lower(result.get("haircut_roi_ci"))),
        "positive_corrected_closing_ev":bool(lower(clv.get("mean_closing_ev_ci"))),
        "negative_corrected_paired_loss":bool(upper(result.get("paired_log_loss_delta_ci"))),
        "complete_selected_close_coverage":result["bets"] > 0 and clv["missing_bets"] == 0,
        "complete_selected_settlements":result["bets"] > 0 and result["unsettled_bets"] == 0,
    }


def run(root):
    reports = root/"reports"
    frame = pd.read_csv(reports/"soccer-forecasts.csv", dtype={"season":str})
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None)
    frame = frame.sort_values(["date", "event_id"]).reset_index(drop=True)
    if frame.event_id.duplicated().any():
        raise ValueError("Duplicate events in forecast file")
    fit = json.loads((reports/"soccer-fit.json").read_text())
    output = {
        "status":"unproven", "alerts_enabled":False,
        "protocol_sha256":hashlib.sha256((root/"docs/protocol-narrow-v1.md").read_bytes()).hexdigest(),
        "model_sha256":hashlib.sha256((reports/"soccer-model.json").read_bytes()).hexdigest(),
        "forecast_sha256":hashlib.sha256((reports/"soccer-forecasts.csv").read_bytes()).hexdigest(),
        "confidence":CONFIDENCE, "bootstrap_samples":10000,
        "multiple_comparison_allowance":8,
        "primary_closing_reference":"proportional no-vig market average, fixed total 2.5",
        "historical_execution":"unverified Bet365 early snapshot; not FanDuel",
        "selection_record":fit,
        "periods":{},
    }
    masks = {"holdout":frame.season.isin(["2324", "2425"]),
             "replication":frame.season.eq("2526")}
    for period, mask in masks.items():
        subset = frame.loc[mask].copy()
        if subset.empty:
            raise ValueError(f"Missing {period} forecasts")
        models = {}
        for name in ("market", "average", *CANDIDATES):
            p = subset.market_p if name == "market" else subset[f"p_{name}"]
            models[name] = describe(subset, p)
            models[name]["research_screen"] = gates(models[name])
            models[name]["by_season"] = {str(s):describe(g, p.loc[g.index], False) for s,g in subset.groupby("season")}
            models[name]["by_league"] = {str(s):describe(g, p.loc[g.index], False) for s,g in subset.groupby("league")}
        output["periods"][period] = models
    output["protocol_screens"] = {}
    for name in CANDIDATES:
        holdout = output["periods"]["holdout"][name]
        replication = output["periods"]["replication"][name]
        close = replication["closing_bet365"]
        # Clarified before examining outputs: contradiction means negative mean,
        # not only statistical significance. Missing replication CLV also blocks.
        no_contradiction = (close["mean_closing_ev"] is not None
                            and close["mean_closing_ev"] >= 0
                            and close["missing_bets"] == 0)
        checks = dict(holdout["research_screen"])
        checks["no_negative_bet365_closing_replication"] = bool(no_contradiction)
        checks["complete_replication_primary_close_coverage"] = (
            replication["bets"] > 0 and replication["closing_average"]["missing_bets"] == 0)
        output["protocol_screens"][name] = {"checks":checks,
            "passes_retrospective_screen":all(checks.values()),
            "passes_forward_promotion":False}
    (reports/"soccer-metrics.json").write_text(json.dumps(output, indent=2, allow_nan=False)+"\n")
    print(json.dumps({period:{name:{k:v for k,v in node.items() if k in (
        "events", "bets", "roi", "haircut_roi", "haircut_roi_ci", "paired_log_loss_delta", "paired_log_loss_delta_ci", "research_screen")}
        | {"clv":node["closing_average"]["mean_closing_ev"], "clv_ci":node["closing_average"]["mean_closing_ev_ci"]}
        for name,node in models.items()} for period,models in output["periods"].items()}, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    run(parser.parse_args().root)
