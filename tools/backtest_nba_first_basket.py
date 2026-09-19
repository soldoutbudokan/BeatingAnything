#!/usr/bin/env python3
"""Prepare immutable first-basket forecasts, then independently grade them.

The prepare phase reads PBP clocks/fixture dates only. Its only scoring inputs
are publisher records admitted by the strict prior-game history cutoff.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.first_basket import FirstBasketState, MODELS, select_bet
from tools.audit_nba_first_basket_archive import (
    ESPN, NBA, NY, PIN, RAW, SUPPORT, clock, csv_rows, first_score, norm,
    team_name, verify,
)

PROTOCOL = ROOT / "docs/nba-first-basket-price-protocol-2026-09-19.md"
PROTOCOL_SHA = "f4240fd25467d1481f0616ac11cbdf0059aa672a5995ed238c77278a0c8f27f7"
INVENTORY = RAW / "first-basket-board-inventory.json"
INVENTORY_SHA = "68c9aa2c82df2cc6f75e3129d77515d85817deecaa9901c48917ddf3e56a15b3"
PBP = RAW / "play_by_play_2025.parquet"
PBP_SHA = "e3a61b57e491b71379abd1ad4c0b2617500a3921deadd3319ee9362d49d2a9dc"
OUT = ROOT / "data/raw/nba-first-basket-backtest-2026-09-19"
FORECASTS = OUT / "forecasts.json"
MANIFEST = ROOT / "reports/nba-first-basket-forecast-freeze-2026-09-19.json"
REPORT = ROOT / "reports/nba-first-basket-backtest-2026-09-19.json"
EXCLUDED = {"202412030DAL", "202502100OKC", "202505110IND"}
ALIASES = {"BKN": "BRK", "CHA": "CHO", "PHX": "PHO"}
MISSING = {"", "nan", "None", "NA"}
CODE = [Path(__file__), ROOT / "beating/first_basket.py", ROOT / "tools/audit_nba_first_basket_archive.py"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def unique_index(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return groups


def source_inputs():
    """Hash verify inputs; do not load independent target scoring values."""
    if digest(PROTOCOL) != PROTOCOL_SHA or digest(INVENTORY) != INVENTORY_SHA:
        raise ValueError("Protocol or audited price inventory changed")
    tree_raw, tree_source = verify(RAW / "lefirstbasket-tree.json")
    tree = json.loads(tree_raw)
    if tree["sha"] != PIN or tree["truncated"]:
        raise ValueError("Unpinned publisher tree")
    entries = {r["path"]: r["sha"] for r in tree["tree"]}
    sources = [tree_source]

    def publisher(path, fields=None):
        raw, source = verify(RAW / "lefirstbasket" / path)
        if source["expected_git_blob"] != entries[path]:
            raise ValueError("Publisher input differs from pinned tree")
        sources.append(source)
        return list(csv_rows(raw, fields))

    metadata = publisher("data/player_metadata.csv", ("player_id", "name"))
    names = defaultdict(set)
    for row in metadata:
        names[norm(row["name"])].add(row["player_id"])
    histories = {year: publisher(f"data/first_basket_{year}.csv") for year in range(2019, 2026)}
    rosters = {year: publisher(f"data/rosters.nosync/rosters_{year}.csv",
                              ("game_id", "player_id", "Team", "starter")) for year in range(2023, 2026)}
    support = {}
    for path in (NBA, ESPN):
        raw, source = verify(path, SUPPORT[path])
        sources.append(source)
        support[path] = list(csv_rows(raw))
    _, source = verify(PBP)
    if source["sha256"] != PBP_SHA:
        raise ValueError("Independent PBP changed")
    sources.append(source)
    return names, histories, rosters, support, sources


def fixture_index(support):
    espn = defaultdict(list)
    for r in support[ESPN]:
        espn[(r["game_date"], team_name(r["home_display_name"]), team_name(r["away_display_name"]))].append(r)
    fixtures = defaultdict(list)
    for gid, sides in unique_index(support[NBA], "game_id").items():
        home = [r for r in sides if "vs." in r["matchup"]]
        away = [r for r in sides if " @ " in r["matchup"]]
        if len(sides) != 2 or len(home) != 1 or len(away) != 1:
            continue
        h, a = home[0], away[0]
        if h["game_date"] != a["game_date"]:
            continue
        matches = espn[(h["game_date"], team_name(h["team_name"]), team_name(a["team_name"]))]
        if len(matches) != 1:
            continue
        e = matches[0]
        habbr = ALIASES.get(h["team_abbreviation"], h["team_abbreviation"])
        aabbr = ALIASES.get(a["team_abbreviation"], a["team_abbreviation"])
        bref = h["game_date"].replace("-", "") + "0" + habbr
        fixtures[bref].append({"home": habbr, "away": aabbr, "date": h["game_date"],
                              "nba_game_id": gid, "espn_game_id": e["game_id"],
                              "start": e["start_date"], "completed": e["status_type_completed"] == "true"})
    return {g: v[0] for g, v in fixtures.items() if len(v) == 1}


def completion_clocks():
    """Read only clocks and dates, not a target scorer, starter or jump outcome."""
    import pyarrow.parquet as pq
    groups = defaultdict(lambda: {"dates": set(), "clocks": [], "bad_clock": False})
    columns = ["game_id", "wallclock", "game_date"]
    for r in pq.read_table(PBP, columns=columns).to_pylist():
        item = groups[str(r["game_id"])]
        item["dates"].add(str(r["game_date"]))
        if r["wallclock"]:
            try:
                item["clocks"].append(clock(r["wallclock"]))
            except ValueError:
                item["bad_clock"] = True
    return {gid: {"date": next(iter(r["dates"])), "completed_at": max(r["clocks"])}
            for gid, r in groups.items() if len(r["dates"]) == 1 and r["clocks"] and not r["bad_clock"]}


def roster_status(rows, home, away):
    if not rows:
        return "missing_roster"
    if len({r["player_id"] for r in rows}) != len(rows) or any(r["player_id"] in MISSING for r in rows):
        return "duplicate_or_missing_roster_player"
    if any(r["Team"] not in (home, away) or r["starter"] not in ("True", "False") for r in rows):
        return "invalid_roster_team_or_flag"
    counts = Counter(r["Team"] for r in rows if r["starter"] == "True")
    if counts != Counter({home: 5, away: 5}):
        return "incomplete_starters"
    return "valid"


def historical_events(histories, rosters, fixtures, completions):
    events, counts = [], Counter()
    last_old = max(r["Date"] for year, rows in histories.items() if year < 2025 for r in rows)
    first_current = min(r["Date"] for r in histories[2025])
    if last_old >= first_current:
        raise ValueError("Earlier seasons overlap priced season")
    for year in sorted(histories):
        scores = unique_index(histories[year], "game_id")
        roster_games = unique_index(rosters.get(year, []), "game_id")
        for gid in sorted(scores.keys() | roster_games.keys()):
            counts[f"{year}:input_games"] += 1
            rows = scores.get(gid, [])
            if len(rows) > 1:
                counts[f"{year}:duplicate_history"] += 1
                continue
            score = rows[0] if rows else {}
            roster = roster_games.get(gid, [])
            played = datetime.strptime(gid[:8], "%Y%m%d").date()
            home = gid[9:]
            teams = {r["Team"] for r in roster}
            away = score.get("Away") or (next(iter(teams - {home})) if len(teams) == 2 and home in teams else None)
            if not away or away == home or (score and (score["Date"] != played.isoformat() or
                    score["Home"] != home or int(score["season"]) != year)):
                counts[f"{year}:date_team_or_season_mismatch"] += 1
                continue
            completed_at = None
            available_at = datetime.combine(played + timedelta(days=1), time(), NY)
            if year == 2025:
                f = fixtures.get(gid)
                if not f or (f["home"], f["away"], f["date"]) != (home, away, played.isoformat()):
                    counts[f"{year}:independent_fixture_unmatched"] += 1
                    continue
                c = completions.get(f["espn_game_id"])
                if not f["completed"] or not c or c["date"] != played.isoformat() or c["completed_at"] <= clock(f["start"]):
                    counts[f"{year}:completion_unverified"] += 1
                    continue
                completed_at = c["completed_at"]
                available_at = max(available_at, completed_at)
            rstatus = roster_status(roster, home, away)
            counts[f"{year}:roster:{rstatus}"] += 1
            good_roster = roster if rstatus == "valid" else []
            valid_jump = bool(score) and all(score[k] not in MISSING for k in
                ("jumpball_home", "jumpball_away", "jumpball_possession")) and score["jumpball_home"] != score["jumpball_away"] and score["jumpball_possession_tm"] in (home, away)
            if valid_jump and good_roster:
                roster_teams = {r["player_id"]: r["Team"] for r in good_roster}
                valid_jump = (roster_teams.get(score["jumpball_home"]) == home and
                              roster_teams.get(score["jumpball_away"]) == away and
                              roster_teams.get(score["jumpball_possession"]) == score["jumpball_possession_tm"])
            valid_score = bool(score) and score["first_basket"] not in MISSING and score["first_basket_tm"] in (home, away) and score["pts_scored"] in ("1", "2", "3", "1.0", "2.0", "3.0")
            if valid_score and good_roster:
                valid_score = any(r["player_id"] == score["first_basket"] and r["Team"] == score["first_basket_tm"] for r in good_roster)
            valid_role = bool(valid_jump and valid_score and good_roster)
            counts[f"{year}:valid_jump"] += int(valid_jump)
            counts[f"{year}:valid_role"] += int(valid_role)
            events.append({"game_id": gid, "season": year, "date": played.isoformat(), "home": home, "away": away,
                "available_at": available_at.isoformat(), "completed_at": completed_at.isoformat() if completed_at else None,
                "roster": [(r["player_id"], r["Team"], r["starter"] == "True") for r in good_roster],
                "valid_jump": bool(valid_jump), "valid_role": valid_role,
                "jumper_home": score.get("jumpball_home"), "jumper_away": score.get("jumpball_away"),
                "possession_team": score.get("jumpball_possession_tm"),
                "scorer_team": score.get("first_basket_tm"), "scorer": score.get("first_basket")})
    return sorted(events, key=lambda e: (clock(e["available_at"]), e["game_id"])), dict(counts)


def history_available(event, quote):
    return (date.fromisoformat(event["date"]) < quote.astimezone(NY).date()
            and clock(event["available_at"]) < quote
            and (event["season"] < 2025 or (event["completed_at"] is not None and clock(event["completed_at"]) < quote)))


def forecast_boards(boards, events, names):
    state, index = FirstBasketState(), 0
    forecasts, exclusions = [], []
    used, current_completed = [], []
    for board in sorted(boards, key=lambda b: (clock(b["prices"][0]["quote_time"]), b["game_id"])):
        quote = clock(board["prices"][0]["quote_time"])
        while index < len(events) and clock(events[index]["available_at"]) < quote:
            event = events[index]
            if not history_available(event, quote):
                raise ValueError("History availability ordering violated")
            if event["game_id"] == board["game_id"]:
                raise ValueError("Target outcome attempted to enter forecast")
            state.observe(event)
            used.append(event)
            if event["completed_at"]:
                current_completed.append(event["completed_at"])
            index += 1
        reason = None
        runners = []
        if board["game_id"] in EXCLUDED:
            reason = "previously_inspected_source_validation"
        elif any(len(names.get(norm(r["name"]), ())) != 1 for r in board["prices"]):
            reason = "nonunique_or_missing_player_identity"
        else:
            runners = [{**r, "player_id": next(iter(names[norm(r["name"])]))} for r in board["prices"]]
            if len({r["player_id"] for r in runners}) != 10:
                reason = "duplicate_player_identity"
        if reason:
            exclusions.append({"game_id": board["game_id"], "reason": reason})
            continue
        try:
            prediction = state.forecast(board["home_abbr"], board["away_abbr"], runners)
        except ValueError as exc:
            if str(exc) != "Prior rosters do not establish five candidates per current team":
                raise
            exclusions.append({"game_id": board["game_id"], "reason": "prior_roster_team_assignment",
                               "assignments": {r["player_id"]: state.player_team.get(r["player_id"]) for r in runners}})
            continue
        local_date = quote.astimezone(NY).date()
        forecasts.append({"game_id": board["game_id"], "espn_game_id": board["espn_game_id"],
            "nba_game_id": board["nba_game_id"], "home": board["home_abbr"], "away": board["away_abbr"],
            "quote_time": quote.isoformat(), "received_at": board["received_at"],
            "period": "discovery" if local_date <= date(2025, 2, 28) else "replication",
            "week": local_date.strftime("%G-W%V"), "runners": runners, "probabilities": prediction,
            "bets": {m: select_bet(runners, prediction[m]) for m in MODELS},
            "reserve_bets": {m: select_bet(runners, prediction[m], reserve=True) for m in MODELS},
            "history_games": len(used), "max_history_date": max(e["date"] for e in used) if used else None,
            "latest_history_available_at": used[-1]["available_at"] if used else None,
            "current_season_history_games": len(current_completed),
            "max_history_completion": max(current_completed, key=clock) if current_completed else None})
    return forecasts, exclusions


def prepare():
    if FORECASTS.exists() or MANIFEST.exists():
        raise FileExistsError("Frozen forecasts already exist; never overwrite a inspected forecast cohort")
    names, histories, rosters, support, sources = source_inputs()
    fixtures = fixture_index(support)
    events, history_counts = historical_events(histories, rosters, fixtures, completion_clocks())
    earliest = {}
    for row in sorted(json.loads(INVENTORY.read_text()), key=lambda r: (clock(r["received_at"]), r["event_id"])):
        if row["status"] == "pregame_ten_runner_board":
            earliest.setdefault(row["game_id"], row)
    boards = []
    for gid, b in earliest.items():
        f = fixtures.get(gid)
        if not f or (f["nba_game_id"], f["espn_game_id"]) != (b["nba_game_id"], b["espn_game_id"]):
            raise ValueError("Audited board fixture no longer reconciles")
        boards.append({**b, "home_abbr": f["home"], "away_abbr": f["away"]})
    if len(boards) != 580:
        raise ValueError("Fixed source cohort changed")
    forecasts, exclusions = forecast_boards(boards, events, names)
    now = datetime.now(timezone.utc).isoformat()
    payload = {"created_at": now, "protocol_sha256": PROTOCOL_SHA, "forecasts": forecasts,
               "exclusions": exclusions, "history_attrition": history_counts}
    OUT.mkdir(parents=True, exist_ok=True)
    with FORECASTS.open("xb") as f:
        f.write(encoded(payload))
    evidence = {"created_at": now, "phase": "forecasts frozen before independent target scores loaded",
        "protocol_sha256": PROTOCOL_SHA, "inventory_sha256": INVENTORY_SHA,
        "forecast_path": str(FORECASTS.relative_to(ROOT)), "forecast_sha256": digest(FORECASTS),
        "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in CODE}, "sources": sources,
        "input_boards": len(boards), "forecast_count": len(forecasts),
        "forecast_periods": dict(Counter(r["period"] for r in forecasts)),
        "exclusions": dict(Counter(r["reason"] for r in exclusions)), "history_attrition": history_counts,
        "overround": {"min": min(r["probabilities"]["overround"] for r in forecasts),
                      "median": statistics.median(r["probabilities"]["overround"] for r in forecasts),
                      "max": max(r["probabilities"]["overround"] for r in forecasts)},
        "selection_counts": {p: {m: sum(r["bets"][m] is not None for r in forecasts if r["period"] == p)
                                 for m in MODELS} for p in ("discovery", "replication")}}
    with MANIFEST.open("xb") as f:
        f.write(encoded(evidence))
    print(json.dumps({k: v for k, v in evidence.items() if k not in ("sources", "code_sha256")}, indent=2))


def grade_outcome(forecast, plays, names, published):
    try:
        first = first_score(plays)
    except (StopIteration, ValueError):
        return {"status": "unresolved", "reason": "missing_or_invalid_independent_first_score"}
    ids = names.get(norm(first["athlete_name_1"] or ""), set())
    if len(ids) != 1:
        return {"status": "unresolved", "reason": "independent_scorer_identity", "name": first["athlete_name_1"]}
    scorer = next(iter(ids))
    if published:
        if len(published) != 1:
            return {"status": "unresolved", "reason": "duplicate_publisher_outcomes"}
        p = published[0]
        minutes, seconds = first["clock_display_value"].split(":")
        elapsed = 720 - 60 * int(minutes) - float(seconds)
        if p["first_basket"] not in MISSING and (p["first_basket"] != scorer or
                float(p["pts_scored"]) != first["score_value"] or float(p["time_elapsed"]) != elapsed):
            return {"status": "unresolved", "reason": "publisher_independent_mismatch",
                    "publisher_scorer": p["first_basket"], "independent_scorer": scorer}
    return {"status": "resolved", "scorer": scorer, "independent_name": first["athlete_name_1"],
            "first_points": first["score_value"], "game_clock": first["clock_display_value"],
            "listed": scorer in forecast["probabilities"]["market"],
            "publisher_compared": bool(published and published[0]["first_basket"] not in MISSING)}


def settle_bet(bet, outcome, roster, home, away):
    if bet is None:
        return {"status": "no_bet", "profit": 0.0}
    if roster_status(roster, home, away) != "valid":
        return {"status": "unresolved", "profit": None, "reason": "starter_status_unknown"}
    starters = {r["player_id"] for r in roster if r["starter"] == "True"}
    if bet["player_id"] not in starters:
        return {"status": "void", "profit": 0.0}
    if outcome["status"] != "resolved":
        return {"status": "unresolved", "profit": None, "reason": outcome["reason"]}
    won = bet["player_id"] == outcome["scorer"]
    return {"status": "win" if won else "loss", "profit": .98 * (bet["decimal"] - 1) if won else -1.0}


def scoring(probabilities, scorer):
    p = {player: .99 * value for player, value in probabilities.items()}
    p["__unlisted__"] = .01
    label = scorer if scorer in probabilities else "__unlisted__"
    return {"log_loss": -math.log(p[label]),
            "brier": sum((v - int(k == label)) ** 2 for k, v in p.items())}


def bootstrap_ratios(rows):
    """Rows contain (week, numerator, denominator), with all stakes retained."""
    groups = defaultdict(lambda: [0.0, 0.0])
    for week, numerator, denominator in rows:
        groups[week][0] += numerator
        groups[week][1] += denominator
    blocks = np.array([groups[k] for k in sorted(groups)], dtype=float)
    result = {"weeks": len(blocks), "confidence": 1 - .05 / 15}
    if len(blocks) < 8:
        return {**result, "corrected_interval": None, "reason": "fewer_than_eight_weeks"}
    rng = np.random.default_rng(1729)
    draws = blocks[rng.integers(0, len(blocks), size=(10000, len(blocks)))].sum(axis=1)
    if np.any(draws[:, 1] <= 0):
        raise ValueError("Bootstrap denominator is empty")
    ratios = draws[:, 0] / draws[:, 1]
    return {**result, "corrected_interval": np.quantile(ratios, [.05 / 30, 1 - .05 / 30]).tolist(),
            "descriptive_95pct_interval": np.quantile(ratios, [.025, .975]).tolist()}


def summarize(rows, model, key):
    selected = [r for r in rows if r[key][model]["status"] != "no_bet"]
    counts = Counter(r[key][model]["status"] for r in selected)
    n = len(selected)
    known_profit = sum(r[key][model]["profit"] or 0 for r in selected)
    lower = known_profit - counts["unresolved"]
    results = {"forecast_games": len(rows), "selected_bets": n,
        **{s: counts[s] for s in ("win", "loss", "void", "unresolved")},
        "nonvoid_settled_turnover": counts["win"] + counts["loss"],
        "original_stake_turnover": n, "known_profit": known_profit,
        "haircut_roi": known_profit / n if n and not counts["unresolved"] else None,
        "unresolved_all_loss_roi": lower / n if n else None,
        "unresolved_all_void_roi": known_profit / n if n else None,
        "roi_bootstrap_all_loss": bootstrap_ratios([(r["week"], -1.0 if r[key][model]["profit"] is None else r[key][model]["profit"], 1) for r in selected]),
        "roi_bootstrap_all_void": bootstrap_ratios([(r["week"], r[key][model]["profit"] or 0.0, 1) for r in selected])}
    scored = [r for r in rows if r["scores"] is not None]
    results["scored_games"] = len(scored)
    for metric in ("log_loss", "brier"):
        deltas = [(r["week"], r["scores"][model][metric] - r["scores"]["market"][metric], 1) for r in scored]
        results[metric] = {
            "model_mean": statistics.mean(r["scores"][model][metric] for r in scored) if scored else None,
            "market_mean": statistics.mean(r["scores"]["market"][metric] for r in scored) if scored else None,
            "paired_difference": statistics.mean(r[1] for r in deltas) if deltas else None,
            "paired_bootstrap": bootstrap_ratios(deltas)}
    return results


def grade():
    import pyarrow.parquet as pq
    manifest = json.loads(MANIFEST.read_text())
    if digest(FORECASTS) != manifest["forecast_sha256"] or digest(PROTOCOL) != PROTOCOL_SHA:
        raise ValueError("Frozen forecasts/protocol changed")
    for p, expected in manifest["code_sha256"].items():
        if digest(ROOT / p) != expected:
            raise ValueError(f"Code changed after forecast freeze: {p}")
    names, histories, rosters, _, sources = source_inputs()
    if sources != manifest["sources"]:
        raise ValueError("Source receipts changed after forecast freeze")
    forecasts = json.loads(FORECASTS.read_text())["forecasts"]
    ids = [int(r["espn_game_id"]) for r in forecasts]
    columns = ["game_id", "sequence_number", "period_number", "clock_display_value", "scoring_play",
               "score_value", "home_score", "away_score", "athlete_name_1"]
    plays = unique_index(pq.read_table(PBP, columns=columns, filters=[("game_id", "in", ids)]).to_pylist(), "game_id")
    published = unique_index(histories[2025], "game_id")
    roster_games = unique_index(rosters[2025], "game_id")
    rows = []
    for f in forecasts:
        outcome = grade_outcome(f, plays[int(f["espn_game_id"])], names, published.get(f["game_id"], []))
        roster = roster_games.get(f["game_id"], [])
        rows.append({"game_id": f["game_id"], "period": f["period"], "week": f["week"], "outcome": outcome,
            "settlements": {m: settle_bet(f["bets"][m], outcome, roster, f["home"], f["away"]) for m in MODELS},
            "reserve_settlements": {m: settle_bet(f["reserve_bets"][m], outcome, roster, f["home"], f["away"]) for m in MODELS},
            "scores": {m: scoring(f["probabilities"][m], outcome["scorer"]) for m in (*MODELS, "market")}
                       if outcome["status"] == "resolved" else None})
    graded_path = OUT / "graded.json"
    graded_path.write_bytes(encoded(rows))
    results = {period: {m: summarize([r for r in rows if period == "pooled" or r["period"] == period], m, "settlements")
                        for m in MODELS} for period in ("discovery", "replication", "pooled")}
    sensitivities = {period: {m: summarize([r for r in rows if r["period"] == period], m, "reserve_settlements")
                             for m in MODELS} for period in ("discovery", "replication")}
    gates = {}
    for model in MODELS:
        d, r, p = (results[k][model] for k in ("discovery", "replication", "pooled"))
        exploratory = all(x["nonvoid_settled_turnover"] >= 50 and x["unresolved_all_loss_roi"] is not None and
                          x["unresolved_all_loss_roi"] > 0 for x in (d, r)) and p["log_loss"]["paired_difference"] < 0
        roi_interval = r["roi_bootstrap_all_loss"]["corrected_interval"]
        loss_interval = r["log_loss"]["paired_bootstrap"]["corrected_interval"]
        gates[model] = {"exploratory_lead": exploratory,
                       "historical_advantage": bool(exploratory and roi_interval and roi_interval[0] > 0 and
                                                    loss_interval and loss_interval[1] < 0),
                       "prospective_promotion": False}
    report = {"protocol_sha256": PROTOCOL_SHA, "forecast_sha256": manifest["forecast_sha256"],
        "forecast_freeze": str(MANIFEST.relative_to(ROOT)), "graded_path": str(graded_path.relative_to(ROOT)),
        "graded_sha256": digest(graded_path), "forecast_games": len(rows),
        "outcome_counts": dict(Counter(r["outcome"]["status"] for r in rows)),
        "outcome_unresolved_reasons": dict(Counter(r["outcome"]["reason"] for r in rows if r["outcome"]["status"] != "resolved")),
        "unlisted_scorers": sum(r["outcome"].get("listed") is False for r in rows),
        "publisher_reconciled": sum(r["outcome"].get("publisher_compared", False) for r in rows),
        "bootstrap_draws": 10000, "bootstrap_seed": 1729, "comparisons": 15,
        "results": results, "reserve_probability_sensitivity": sensitivities, "gates": gates,
        "limitations": ["Historical simulations, not accepted wagers; quote jurisdiction and historical rule version unverified.",
                        "Original odds JSON and general closing prices absent; market lineup assumptions unresolved.",
                        "Publisher has studied the archive; no independently untouched holdout claimed.",
                        "Retrospective prior-game corrections are not contemporaneous publication proof.",
                        "No prospective paper cohort, closing-EV evidence, wagers, alerts or schedules."]}
    REPORT.write_bytes(encoded(report))
    print(json.dumps({"outcomes": report["outcome_counts"], "unresolved": report["outcome_unresolved_reasons"],
                      "gates": gates, "results": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "grade"))
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else grade()
