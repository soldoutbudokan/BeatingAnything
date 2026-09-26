#!/usr/bin/env python3
"""Fixed exploratory quarterback rushing Under test, declared before grading.

Trigger: FanDuel full-game QB rushing half-point line 0<line<=5.5, both quote clocks
nonfuture/fresh<=300s, snapshot before independently matched kickoff. No favorite
filter: a timely 2024 moneyline is unavailable. One earliest quote/player/game.

Probability correction: previous 16 regular-season games with >=10 recorded pass
plays, completed on dates at least two days before snapshot; minimum 8. Count prior
games in which kneels moved final rushing yards from above today's line to below.
Add count/(n+20) to normalized market Under probability, capped[.01,.99]. With
<8 prior games, preserve market forecast and report insufficient history. This may
double-count kneels that FanDuel already prices. All<=5.5 returns and a fixed
model-EV>=3% subset are reported, without a search over cutoffs or parameters.
Selection uses the originally declared gross EV; a 2% haircut on net winnings
is reported separately as the standing project cost sensitivity.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nfl-qb-kneel-props-2026-09-26"
OUT = ROOT / "reports/nfl-qb-kneel-props-2026-09-26"
COMMIT = "e919241eb9fc17f057005348c7869a37b23e7675"
NET_WIN_HAIRCUT = .02
PINS = {
    "prices.csv": "a99887894fec9cd7c3e216a74c53a14d3ef1cc03528a04693076fb084f2a1c26",
    "analysis_rows.csv": "12fde972f0acd87f2ec0ea1adf8aa14d9287b5114ed036a5c92a28c51cea98a7",
    "roster_2024.csv": "97721aa9092edb15c1357f2dac359dba72f63c81cc0e69408c65c229c91f50c1",
    "games.csv": "0c34a519753ada6b5b37f5e8be246021813484adb15ae7c067af9c3aca534d2d",
    "player_stats_2024.csv": "4f1598c9a6ba396a52e256762a0d9148abd22cdf856f26fc8825fa1d1dc49631",
    "play_by_play_2022.csv.gz": "0c69a71eb39498956c7b1d5c1ca52ce7fe679934a95d1af249facb5ea9829ea4",
    "play_by_play_2023.csv.gz": "4649804ee0f0a40b41e51ec75a1ce921949d7fab5459213488656b92f78560e8",
    "play_by_play_2024_projection.csv": "cf9ba0b61a7801658f65445e4f96e365631e3bec2d64451e890af5929fd3a7cf",
    "backfill_closing_props.py": "1c56a58b38cc6ee84db0306a976d2490d9dbc8f7180e8e91d1c84981359f3a0b",
    "merge_props_with_actuals.py": "0782c1cdf2d3ec4902dc28023038aa494e8e0cb4a8872f8732a733e512dbfb01",
    "merge_game_context.py": "b51d79a5740d0eb355b06baebcd31750e5898cd5ea0a152f5a6651e22b2afbe2",
    "analyze_market.py": "34049b37f1349fb888ad4c639ac6d87fb65f9d0dac283f2aecc75b3ff76f22c9",
}
TEAMS = dict(zip([
    "Arizona Cardinals", "Atlanta Falcons", "Baltimore Ravens", "Buffalo Bills", "Carolina Panthers",
    "Chicago Bears", "Cincinnati Bengals", "Cleveland Browns", "Dallas Cowboys", "Denver Broncos",
    "Detroit Lions", "Green Bay Packers", "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars",
    "Kansas City Chiefs", "Las Vegas Raiders", "Los Angeles Chargers", "Los Angeles Rams", "Miami Dolphins",
    "Minnesota Vikings", "New England Patriots", "New Orleans Saints", "New York Giants", "New York Jets",
    "Philadelphia Eagles", "Pittsburgh Steelers", "San Francisco 49ers", "Seattle Seahawks", "Tampa Bay Buccaneers",
    "Tennessee Titans", "Washington Commanders"], [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND",
    "JAX", "KC", "LV", "LAC", "LA", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"]))


def norm(name):
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return re.sub("[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", name))


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def decimal(price):
    n = float(price)
    if abs(n) < 100:
        raise ValueError("Expected original American odds")
    return 1 + n / 100 if n > 0 else 1 + 100 / abs(n)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_audit():
    sources = []
    for fn, expected in PINS.items():
        p = RAW / fn
        observed = sha(p)
        assert observed == expected, f"Changed source {fn}"
        sources.append({"path": str(p.relative_to(ROOT)), "sha256": observed, "bytes": p.stat().st_size})
    original_qs = ROOT / "data/raw/nfl-source-audit/play_by_play_2024.qs"
    assert sha(original_qs) == "c61a0fc53b0cd212bb07ffbe99da83efaa0e63c22e8790fd61293b53412ebdd9"
    prices = list(csv.DictReader((RAW / "prices.csv").open()))
    analyzed = list(csv.DictReader((RAW / "analysis_rows.csv").open()))
    def identity(r):
        return tuple(r[k] for k in ["event_id", "player", "market_key", "line", "actual_snapshot_time"])
    indexed = defaultdict(list)
    for r in prices:
        indexed[identity(r)].append(r)
    mismatch = 0
    for r in analyzed:
        matches = indexed[identity(r)]
        if len(matches) != 1:
            mismatch += 1
            continue
        other = matches[0]
        mismatch += any(float(r[k]) != float(other[k]) for k in ["over_price", "under_price"])
        mismatch += any(r[k] != other[k] for k in ["bookmaker_key", "bookmaker_last_update", "market_last_update"])
    assert mismatch == 0, "Processed price lineage disagrees"
    backfill = (RAW / "backfill_closing_props.py").read_text()
    assert 'price = outcome.get("price")' in backfill
    return prices, {"sources": sources, "source_repository": "https://github.com/firstandthirty/nfl-tools", "source_commit": COMMIT,
                    "merged_rows": len(prices), "rushing_price_rows": sum(r["market_key"] == "player_rush_yds" for r in prices),
                    "analyzed_counterpart_rows": len(analyzed), "counterpart_quote_disagreements": mismatch,
                    "raw_api_responses_available": False,
                    "price_provenance": "Publisher backfill passes outcome.price through directly; no default price found. All 1,094 analyzed rushing quotes agree with earlier merged export. Original raw API responses and unmerged historical_closing_props.csv are absent from pinned tree; execution and upstream authenticity are not established.",
                    "ignored_fields": "All publisher outcome, ROI, position, team, spread, favorite, total and estimated week fields ignored for selection/forecasting. The full merged export avoids analysis-stage missing-outcome attrition.",
                    "pbp2024_original_qs_sha256": sha(original_qs)}


def load_game_totals():
    cols = ["game_id", "game_date", "home_team", "away_team", "posteam", "play_type", "passer_player_id",
            "rusher_player_id", "rushing_yards", "yards_gained", "qb_kneel", "pass_attempt", "two_point_attempt", "season", "season_type"]
    frames = [pd.read_csv(RAW / f"play_by_play_{y}.csv.gz", usecols=cols, low_memory=False) for y in [2022, 2023]]
    frames.append(pd.read_csv(RAW / "play_by_play_2024_projection.csv", usecols=cols, low_memory=False))
    p = pd.concat(frames, ignore_index=True)
    p = p[p.season_type.eq("REG") & p.game_id.ne("2022_17_BUF_CIN") & p.two_point_attempt.ne(1)].copy()
    meta = p.groupby("game_id").agg(game_date=("game_date", "first"), home_team=("home_team", "first"), away_team=("away_team", "first"))
    passing = p[p.play_type.eq("pass") & p.pass_attempt.eq(1) & p.passer_player_id.notna()]
    passing = passing.groupby(["game_id", "passer_player_id"]).size().rename("pass_plays")
    passing.index = passing.index.set_names(["game_id", "player_id"])
    rushing = p[p.play_type.isin(["run", "qb_kneel"]) & p.rusher_player_id.notna()].copy()
    assert rushing.rushing_yards.notna().all(), "Rushing play without credited rushing yards"
    assert rushing.loc[rushing.qb_kneel.eq(1), "rushing_yards"].eq(rushing.loc[rushing.qb_kneel.eq(1), "yards_gained"]).all()
    rushing["kneel_yards"] = np.where(rushing.qb_kneel.eq(1), rushing.rushing_yards, 0.)
    rush = rushing.groupby(["game_id", "rusher_player_id"]).agg(total_yards=("rushing_yards", "sum"), kneel_yards=("kneel_yards", "sum"), credited_rushes=("rushing_yards", "size"))
    rush.index = rush.index.set_names(["game_id", "player_id"])
    totals = pd.concat([passing, rush], axis=1).fillna(0).reset_index().join(meta, on="game_id")
    totals["nonkneel_yards"] = totals.total_yards - totals.kneel_yards
    totals["day"] = pd.to_datetime(totals.game_date).dt.date
    return totals


def prepare(prices, totals):
    roster = pd.read_csv(RAW / "roster_2024.csv", dtype=str).fillna("")
    identities = defaultdict(set)
    for _, r in roster[roster.position.eq("QB")].iterrows():
        if r.gsis_id:
            identities[norm(r.full_name)].add(r.gsis_id)
    fixtures = list(csv.DictReader((RAW / "games.csv").open()))
    fixtures = [r for r in fixtures if r["season"] == "2024" and r["game_type"] == "REG"]
    for g in fixtures:
        g["kickoff"] = datetime.fromisoformat(g["gameday"] + "T" + g["gametime"]).replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    prior_by_id = {pid: df.sort_values(["day", "game_id"]) for pid, df in totals[totals.pass_plays.ge(10)].groupby("player_id")}
    candidate, attr = [], Counter()
    for r in prices:
        if r["market_key"] != "player_rush_yds" or r["bookmaker_key"] != "fanduel":
            continue
        line = float(r["line"])
        if not 0 < line <= 5.5 or line % 1 != .5:
            attr["outside_fixed_half_point_line"] += 1
            continue
        ids = identities.get(norm(r["player"]), set())
        if len(ids) != 1:
            attr["not_unique_roster_quarterback"] += 1
            continue
        pid = next(iter(ids))
        snap, reported = stamp(r["actual_snapshot_time"]), stamp(r["commence_time"])
        if any(not 0 <= (snap - stamp(r[k])).total_seconds() <= 300 for k in ["bookmaker_last_update", "market_last_update"]):
            attr["future_or_stale_quote_clock"] += 1
            continue
        games = [g for g in fixtures if TEAMS.get(r["home_team"]) == g["home_team"] and TEAMS.get(r["away_team"]) == g["away_team"]
                 and abs((g["kickoff"] - reported).total_seconds()) <= 900]
        if len(games) != 1:
            attr["fixture_unresolved"] += 1
            continue
        g = games[0]
        if not 0 < (min(g["kickoff"], reported) - snap).total_seconds() <= 10800:
            attr["outside_pregame_window"] += 1
            continue
        try:
            over, under = decimal(r["over_price"]), decimal(r["under_price"])
            vig = 1 / over + 1 / under - 1
            if not 0 <= vig <= .12:
                raise ValueError
        except ValueError:
            attr["invalid_price"] += 1
            continue
        prior = prior_by_id.get(pid, totals.iloc[:0])
        cutoff = snap.date() - timedelta(days=1)
        prior = prior[prior.day < cutoff].tail(16)
        crossing = int((prior.total_yards.lt(line) & prior.nonkneel_yards.gt(line)).sum())
        # Fewer than eight usable prior games gives no extra forecast, never drops exposure.
        delta = crossing / (len(prior) + 20) if len(prior) >= 8 else 0.
        q = (1 / under) / (1 / under + 1 / over)
        pred = min(.99, max(.01, q + delta))
        candidate.append({"game_id": g["game_id"], "week": int(g["week"]), "season": 2024,
                          "player_id": pid, "player": r["player"], "line": line, "snapshot": snap.isoformat(),
                          "under_price": under, "over_price": over, "overround": vig, "baseline_p_under": q,
                          "model_p_under": pred, "delta": delta, "prior_games": len(prior), "prior_crossings": crossing,
                          "prior_max_game_date": str(prior.day.max()) if len(prior) else None,
                          "model_ev": pred * under - 1, "ev_selected": pred * under - 1 >= .03})
    earliest, conflicting = {}, set()
    for row in sorted(candidate, key=lambda r: (r["snapshot"], r["game_id"], r["player_id"])):
        key = row["game_id"], row["player_id"]
        if key not in earliest:
            earliest[key] = row
        elif earliest[key]["snapshot"] == row["snapshot"] and any(earliest[key][k] != row[k] for k in ["line", "under_price", "over_price"]):
            conflicting.add(key)
        else:
            attr["later_or_duplicate_offer"] += 1
    frozen = [r for k, r in earliest.items() if k not in conflicting]
    attr["ambiguous_same_time_offer"] = len(conflicting)
    payload = json.dumps(frozen, sort_keys=True, allow_nan=False)
    (RAW / "forecast-freeze.json").write_text(payload + "\n")
    return frozen, dict(attr), hashlib.sha256(payload.encode()).hexdigest()


def loss(p, y):
    return -float(y * np.log(p) + (1 - y) * np.log(1 - p))


def settle(frozen, totals):
    index = totals.set_index(["game_id", "player_id"])
    stats = pd.read_csv(RAW / "player_stats_2024.csv", dtype={"player_id": str})
    stats = stats[stats.season_type.eq("REG")]
    results = []
    for forecast in frozen:
        r = dict(forecast)
        key = r["game_id"], r["player_id"]
        matches = stats[(stats.player_id == r["player_id"]) & (stats.week == r["week"])]
        if key not in index.index or len(matches) != 1:
            r.update(status="unknown_participation_or_independent_stat", return_loss_bound=-1., return_void_bound=0.,
                     net_return_loss_bound=-1., net_return_void_bound=0.)
            results.append(r)
            continue
        actual = index.loc[key]
        independent = float(matches.iloc[0].rushing_yards)
        if actual.total_yards != independent:
            r.update(status="pbp_weekly_stat_disagreement", return_loss_bound=-1., return_void_bound=0.,
                     net_return_loss_bound=-1., net_return_void_bound=0.)
            results.append(r)
            continue
        y = float(actual.total_yards < r["line"])
        assert actual.total_yards != r["line"], "Half-point rushing line cannot push"
        ret = r["under_price"] - 1 if y else -1.
        net_ret = ret * (1-NET_WIN_HAIRCUT) if y else -1.
        r.update(status="settled", rushing_yards=float(actual.total_yards), nonkneel_yards=float(actual.nonkneel_yards),
                 kneel_yards=float(actual.kneel_yards), under_won=bool(y), kneel_changed_result=bool(y and actual.nonkneel_yards > r["line"]),
                 return_units=ret, return_loss_bound=ret, return_void_bound=ret,
                 net_return_units=net_ret, net_return_loss_bound=net_ret, net_return_void_bound=net_ret,
                 baseline_log_loss=loss(r["baseline_p_under"], y), model_log_loss=loss(r["model_p_under"], y),
                 log_loss_change=loss(r["model_p_under"], y) - loss(r["baseline_p_under"], y),
                 baseline_brier=(r["baseline_p_under"]-y)**2, model_brier=(r["model_p_under"]-y)**2,
                 brier_change=(r["model_p_under"]-y)**2-(r["baseline_p_under"]-y)**2)
        results.append(r)
    return results


def ci(rows, key):
    if not rows:
        return None
    sx, ns = defaultdict(float), Counter()
    for r in rows:
        sx[r["game_id"]] += r[key]
        ns[r["game_id"]] += 1
    keys = sorted(sx)
    a, n = np.array([sx[k] for k in keys]), np.array([ns[k] for k in keys])
    ix = np.random.default_rng(9262026).integers(0, len(keys), (10000, len(keys)))
    draws = a[ix].sum(axis=1) / n[ix].sum(axis=1)
    return {"mean": float(a.sum()/n.sum()), "game_bootstrap_95": np.quantile(draws, [.025, .975]).tolist()}


def summary(rows):
    settled = [r for r in rows if r["status"] == "settled"]
    s = {"quotes": len(rows), "games": len({r["game_id"] for r in rows}), "settled": len(settled),
         "unknown": len(rows)-len(settled), "statuses": dict(Counter(r["status"] for r in rows)),
         "minimum_history_qualified": sum(r["prior_games"] >= 8 for r in rows), "positive_correction": sum(r["delta"] > 0 for r in rows),
         "roi_pessimistic_bound": ci(rows, "return_loss_bound"), "roi_void_bound": ci(rows, "return_void_bound"),
         "net_roi_pessimistic_bound": ci(rows, "net_return_loss_bound"), "net_roi_void_bound": ci(rows, "net_return_void_bound")}
    if settled:
        s.update(wins=sum(r["under_won"] for r in settled), kneel_changed_result=sum(r["kneel_changed_result"] for r in settled),
                 baseline_log_loss=float(np.mean([r["baseline_log_loss"] for r in settled])),
                 model_log_loss=float(np.mean([r["model_log_loss"] for r in settled])),
                 log_loss_change=ci(settled,"log_loss_change"), brier_change=ci(settled,"brier_change"),
                 baseline_brier=float(np.mean([r["baseline_brier"] for r in settled])),
                 model_brier=float(np.mean([r["model_brier"] for r in settled])),
                 mean_model_ev=float(np.mean([r["model_ev"] for r in rows])), mean_correction=float(np.mean([r["delta"] for r in rows])))
    return s


def main():
    assert decimal(-110) == 1 + 100/110 and decimal(150) == 2.5
    prices, audit = source_audit()
    totals = load_game_totals()
    frozen, attrition, freeze_hash = prepare(prices, totals)
    rows = settle(frozen, totals)
    report = {"status": "exploratory negative result; insufficient sample for an edge claim", "source_audit": audit,
              "declaration": {"max_half_point_line": 5.5, "favorite_filter": False, "history_games": 16, "minimum_history": 8,
                              "shrinkage_pseudogames": 20, "ev_threshold": .03, "future_context_used": False,
                              "ev_selection_basis": "Gross EV as frozen before grading; unchanged for cost sensitivity",
                              "net_winnings_haircut": NET_WIN_HAIRCUT,
                              "missing_history_policy": "No correction; preserve selection and market baseline",
                              "prior_history": "2022–2024 regular-season games; >=10 recorded pass plays; game date at least two calendar days before quote"},
              "forecast_freeze_sha256": freeze_hash, "attrition": attrition,
              "all_fixed_trigger": summary(rows), "fixed_ev_subset": summary([r for r in rows if r["ev_selected"]]),
              "forecasts_and_settlements": rows,
              "limitations": ["The correction may double-count a kneel effect already priced by FanDuel.",
                              "One inspected 2024 season, small cohort, no untouched holdout or current Ontario execution.",
                              "Unmerged odds CSV/original API JSON absent; no evidence of a fabricated/default price found but raw authenticity remains unverified.",
                              "Source processed cohort already joined player results, with possible outcome-dependent missingness; use merged export rather than further-filtered analysis rows.",
                              "No timely moneyline used; publisher is_favorite/team_spread/context and all publisher actuals ignored.",
                              "Season roster used for name/ID/position only, not contemporaneous health or participation; prior game dates, not absolute completion timestamps, exclude games fewer than two calendar days earlier.",
                              "Settlement assumes full-game NFL rushing yards including kneels and action once participation occurs; historical jurisdiction and exact terms unverified."]}
    OUT.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    s, e = report["all_fixed_trigger"], report["fixed_ev_subset"]
    def roi(summary, net=False):
        a = summary["net_roi_pessimistic_bound" if net else "roi_pessimistic_bound"]
        return "undefined" if a is None else f"{a['mean']:+.2%} (game-bootstrap 95% {a['game_bootstrap_95'][0]:+.2%} to {a['game_bootstrap_95'][1]:+.2%})"
    def change(value):
        return f"{value['mean']:+.6f} (game-bootstrap 95% {value['game_bootstrap_95'][0]:+.6f} to {value['game_bootstrap_95'][1]:+.6f})"
    text = f'''# NFL quarterback kneel-down props — September 26, 2026

**The fixed kneel correction worsened forecasting loss, and its low-line Under cohort lost {abs(s['roi_pessimistic_bound']['mean']):.2%} before costs.** There are only {s['quotes']} offers across {s['games']} games, so this exploratory test cannot demonstrate an edge. The fixed trigger was quarterback rushing Under at a positive half-point line no higher than 5.5. Every quote passed both nonfuture book/market clocks and an independent pregame fixture check. No favorite filter was applied because a timely 2024 moneyline was unavailable.

| Measure | All fixed-trigger offers | Fixed gross model-EV≥3% subset |
| --- | ---: | ---: |
| Offers | {s['quotes']} | {e['quotes']} |
| Settled | {s['settled']} | {e['settled']} |
| Under wins | {s.get('wins', 0)} | {e.get('wins', 0)} |
| Gross ROI | {roi(s)} | {roi(e)} |
| ROI with 2% net-winnings haircut | {roi(s, net=True)} | {roi(e, net=True)} |

Normalized market Under log loss was {s.get('baseline_log_loss', float('nan')):.6f}; the kneel correction produced {s.get('model_log_loss', float('nan')):.6f}. The paired change was {change(s['log_loss_change'])}. Brier losses were {s.get('baseline_brier', float('nan')):.6f} and {s.get('model_brier', float('nan')):.6f}; paired change {change(s['brier_change'])}. There were {s['positive_correction']} nonzero corrections, {s['minimum_history_qualified']} forecasts with at least 8 prior games, and {s.get('kneel_changed_result', 0)} actual line-crossings caused by kneels. Insufficient history leaves the market probability unchanged and does not remove the bet.

The cost sensitivity reduces each winning profit by 2% and keeps losing stakes at −1 unit. The gross EV≥3% selection remains frozen; neither eligibility nor probabilities change. Two selected bets cannot support a reliable return interval.

## Mechanism and frozen calculation

NFL kneel-down losses count toward a quarterback's rushing total. At a very low line, a small negative movement can change an Over into an Under. From the previous 16 regular-season games with at least 10 recorded pass plays, count games where total rushing yards finished below today's line but non-kneel rushing yards exceeded it. Require 8 previous games, divide the crossing count by n+20, and add that probability to the paired-price normalized Under probability, capped at 0.99. This assumes the market underweights those losses and **can double-count an effect already in the price**.

The line cutoff, shrinkage, history and model-EV threshold were chosen before this test's returns. Every history game predates the quote by at least two calendar dates. No current-game statistics, future lines, final spread, publisher favorite flags, or publisher outcomes enter a forecast. The frozen selection/prediction hash is `{freeze_hash}`. A half-point line cannot push.

## Source evidence and limits

Prices come from the [pinned firstandthirty/nfl-tools merged export](https://github.com/firstandthirty/nfl-tools/blob/{COMMIT}/player_props/data/processed/merged_props_with_context.csv): 6,224 rows including 1,103 rushing quotes. The 1,094 rushing rows in the later analysis export reproduce those prices and clocks exactly. The [publisher backfill](https://github.com/firstandthirty/nfl-tools/blob/{COMMIT}/player_props/scripts/01_build/backfill_closing_props.py) directly copies `outcome.price`; no fabricated/default price was found. Most quotes are −110/−110, which is disclosed but not treated as proof of synthesis. Original API JSONs and the unmerged odds CSV are absent, so raw authenticity and executable fills are unverified. Publisher outcome/context transformations are ignored; price coverage may still depend on their earlier result join.

Independent nflverse fixture dates/team identities and roster name/IDs match offers. Valid non-null rushing plays, including `qb_kneel` and excluding two-point attempts, are summed from [nflverse PBP](https://github.com/nflverse/nflverse-data/releases/tag/pbp). Every settled total agrees with the [separately published weekly rushing statistic](https://github.com/nflverse/nflverse-data/releases/tag/player_stats). Settlement assumes full-game rushing yards including kneels; historical jurisdiction and exact participation/void terms are unverified. Unknown participation/stat conflicts remain selected with loss-versus-void bounds; none occurred. Recorded attrition: `{attrition}`.

This is a small retrospective price test, not a new independent holdout. No line expansion or parameter search follows this result. Full source hashes, forecasts and outcomes are in the [JSON](nfl-qb-kneel-props-2026-09-26.json). No schedules, alerts or wagers were enabled.

Run `state/runtime/research-venv/bin/python tools/explore_nfl_qb_kneel_props.py` with the retained raw files.
'''
    OUT.with_suffix(".md").write_text(text)
    print(json.dumps({"all_fixed_trigger": s, "fixed_ev_subset": e, "attrition": attrition}, indent=2))


if __name__ == "__main__":
    main()
