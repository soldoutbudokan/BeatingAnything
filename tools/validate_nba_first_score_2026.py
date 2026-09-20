"""Freeze the unchanged Card 42 model on 2026 provider histories, then grade."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from beating.first_score_wedge import convert, normalized_prices, prior_rates, select_bet
from tools import backtest_nba_first_basket as old
from tools import backtest_nba_first_score_wedge as wedge
from tools.acquire_nba_first_score_2026 import PLAN, resume_history
from tools.audit_nba_first_basket_archive import RAW, clock, csv_rows, first_score, norm, verify

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "data/raw/nba-first-score-2026-prices/20260920T011853699664Z"
SOURCES = ROOT / "data/raw/oddspapi-first-basket-audit-2026-09-19"
OUT = ROOT / "data/raw/nba-first-score-2026-validation-2026-09-19"
PROTOCOL = ROOT / "docs/nba-first-score-2026-validation-protocol-2026-09-19.md"
MANIFEST = ROOT / "reports/nba-first-score-2026-forecast-freeze-2026-09-19.json"
FORECASTS = OUT / "forecasts.json"
REPORT = ROOT / "reports/nba-first-score-2026-validation-2026-09-19.json"
PBP = SOURCES / "play_by_play_2026.parquet"
BOX = SOURCES / "player_box_2026.parquet"
PINNED = {
    PBP: "f2d1ccc1a80febd90791d02390504d4a5331f2041169e3a85a4f052df27a0ffd",
    BOX: "29a29dc9efd055a93e069a0382ac830d98a13274bee655beba69d95cff099713",
    SOURCES / "players.json": "8b39c3e47925ec9b96ee607bd3890961a3b4042059e84dfea8b9ca494a3c1b05",
}
CODE = list(dict.fromkeys([Path(__file__), *wedge.CODE, ROOT / "tools/acquire_nba_first_score_2026.py",
                          ROOT / "tools/probe_first_basket_history.py", ROOT / "tools/probe_first_basket_history_followup.py"]))
digest, encoded = old.digest, old.encoded


def state_at(players, decision):
    """Latest state, including suspensions; never select an older valid quote."""
    active = {}
    for player, entries in players.items():
        dated = []
        for entry in entries:
            try:
                stamp = clock(entry["createdAt"])
            except (KeyError, ValueError, TypeError):
                return None, "unorderable_history_clock"
            if stamp <= decision:
                dated.append((stamp, entry))
        if not dated:
            continue
        latest = max(t for t, _ in dated)
        states = [r for t, r in dated if t == latest]
        if len({json.dumps([r.get("active"), r.get("price")], sort_keys=True) for r in states}) != 1:
            return None, "conflicting_latest_state"
        row = states[0]
        price = row.get("price")
        if (row.get("active") is not True or isinstance(price, bool) or not isinstance(price, (int, float))
                or not math.isfinite(price) or price <= 1):
            continue
        active[str(player)] = {"decimal": float(price), "entry_time": latest.isoformat(),
                               "entry_age_seconds": (decision-latest).total_seconds()}
    return active, None


def map_board(states, identities):
    if len(states) != 10:
        return None, "not_ten_active_players"
    if any(p not in identities for p in states):
        return None, "unresolved_player_identity"
    rows = [{**value, **identities[p], "provider_player_id": p} for p, value in states.items()]
    if len({r["espn_athlete_id"] for r in rows}) != 10 or len({r["player_id"] for r in rows}) != 10:
        return None, "duplicate_person"
    return sorted(rows, key=lambda r: r["player_id"]), None


def identity_inputs():
    """Read player names only from the target-season box file, never starts/stats."""
    import pyarrow.parquet as pq
    for path, sha in PINNED.items():
        if digest(path) != sha:
            raise ValueError("Pinned independent source changed")
    raw, prior_source = verify(RAW / "lefirstbasket/data/rosters.nosync/rosters_2024.csv")
    rates, league, counts = prior_rates(csv_rows(raw, ("game_id", "player_id", "starter", "FG", "FT")), date(2026, 3, 14))
    raw, name_source = verify(RAW / "lefirstbasket/data/player_metadata.csv")
    previous = json.loads(wedge.MANIFEST.read_text())
    expected_prior = next(s for s in previous["sources"] if s["sha256"] == prior_source["sha256"])
    if prior_source != expected_prior:
        raise ValueError("Prior source differs from original experiment")
    publisher = defaultdict(set)
    for row in csv_rows(raw, ("player_id", "name")):
        publisher[norm(row["name"])].add(row["player_id"])
    espn, espn_names = defaultdict(set), defaultdict(set)
    for r in pq.read_table(BOX, columns=["athlete_id", "athlete_display_name"]).to_pylist():
        if r["athlete_id"] is not None and r["athlete_display_name"]:
            player = str(r["athlete_id"])
            espn[norm(r["athlete_display_name"])].add(player)
            espn_names[player].add(r["athlete_display_name"])
    provider = defaultdict(set)
    for team in json.loads((SOURCES / "players.json").read_text())["participants"].values():
        for player in team["players"]:
            name = player["playerName"]
            parts = name.split(",", 1)
            full = (parts[1] + " " + parts[0]).strip() if len(parts) == 2 else name
            provider[str(player["playerId"])].add(norm(full))
    identities = {}
    for provider_id, names in provider.items():
        if len(names) != 1:
            continue
        key = next(iter(names))
        if len(espn[key]) != 1:
            continue
        eid = next(iter(espn[key]))
        if len(espn_names[eid]) != 1:
            continue
        pid = next(iter(publisher[key])) if len(publisher[key]) == 1 else "espn:" + eid
        identities[provider_id] = {"espn_athlete_id": eid, "player_id": pid, "name": next(iter(espn_names[eid]))}
    return identities, rates, league, counts, [prior_source, name_source]


def prepare():
    import pyarrow.parquet as pq
    if FORECASTS.exists() or MANIFEST.exists():
        raise FileExistsError("Never overwrite frozen forecasts")
    if json.loads((PRICES / "result.json").read_text())["status"] != "acquisition_complete":
        raise ValueError("Wait for complete fixed acquisition")
    catalog = ROOT / PLAN["catalog_path"]
    if digest(catalog) != PLAN["catalog_sha256"]:
        raise ValueError("Market catalog changed")
    fixtures, coverage, calls = resume_history(PRICES, json.loads(catalog.read_text()))
    if len(fixtures) != 221 or len(coverage) != len(fixtures):
        raise ValueError("Incomplete frozen cohort")
    identities, rates, league, counts, prior_sources = identity_inputs()
    links = {r["fixture_id"]: r for r in json.loads((SOURCES / "regular-season-fixture-links.json").read_text())}
    teams = defaultdict(set)
    for r in pq.read_table(PBP, columns=["game_id", "home_team_id", "away_team_id"]).to_pylist():
        teams[str(r["game_id"])].add((str(r["home_team_id"]), str(r["away_team_id"])))
    histories, source_paths = {}, [catalog, SOURCES / "regular-season-fixture-links.json", *PINNED]
    for path in sorted(PRICES.glob("[0-9]*-*.meta.json")):
        meta = json.loads(path.read_text())
        body = path.with_name(path.name.replace(".meta.json", ".json"))
        source_paths.extend([path, body])
        if "-historical-odds." in path.name and meta["status"] == 200:
            history = json.loads(body.read_text())
            if history["fixtureId"] in histories:
                raise ValueError("Repeated successful history")
            histories[history["fixtureId"]] = history
    source_paths.extend(PRICES / f for f in ("plan.json", "selected-fixtures.json", "result.json"))
    forecasts, exclusions = [], []
    for fixture in fixtures:
        fid = fixture["fixtureId"]
        link = links.get(fid)
        reason = None
        if not link or link["season_type"] != 2 or link["provider_start"] != fixture["startTime"]:
            reason = "unverified_regular_season_fixture"
        elif len(teams[link["espn_game_id"]]) != 1:
            reason = "ambiguous_independent_teams"
        if reason:
            exclusions.append({"fixture_id": fid, "reason": reason})
            continue
        start = min(clock(link["provider_start"]), clock(link["independent_start"]))
        day = start.astimezone(ZoneInfo("America/New_York")).date()
        decision = start - timedelta(minutes=5)
        if day.weekday() == 4:
            reason = "friday_promotion_day"
        elif fid not in histories:
            reason = "provider_explicit_no_history"
        boards = {}
        if reason is None:
            for book in ("fanduel", "betmgm"):
                players = histories[fid].get("bookmakers", {}).get(book, {}).get("markets", {}).get("112604", {}).get("outcomes", {}).get("112604", {}).get("players", {})
                states, issue = state_at(players, decision)
                if issue is None:
                    boards[book], issue = map_board(states, identities)
                if issue:
                    reason = book + ":" + issue
                    break
        if reason is None and {r["espn_athlete_id"] for r in boards["fanduel"]} != {r["espn_athlete_id"] for r in boards["betmgm"]}:
            reason = "candidate_sets_differ"
        if reason:
            exclusions.append({"fixture_id": fid, "reason": reason})
            continue
        fd, mgm = boards["fanduel"], boards["betmgm"]
        q = normalized_prices(mgm)
        p = convert(q, rates, league)
        home, away = next(iter(teams[link["espn_game_id"]]))
        forecasts.append({"fixture_id": fid, "espn_game_id": link["espn_game_id"],
            "home_team_id": home, "away_team_id": away, "start": start.isoformat(), "decision": decision.isoformat(),
            "week": day.strftime("%G-W%V"), "runners": fd, "reference_runners": mgm,
            "strict_entry_age_300s": all(r["entry_age_seconds"] <= 300 for r in fd + mgm),
            "probabilities": {"converted": p, "reference": q, "market": normalized_prices(fd)},
            "unseen_prior_players": sorted(pid for pid in q if pid not in rates),
            "bet": select_bet(fd, p, q), "reserve_bet": select_bet(fd, p, q, reserve=True)})
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": datetime.now(timezone.utc).isoformat(), "forecasts": forecasts, "exclusions": exclusions}
    with FORECASTS.open("xb") as handle:
        handle.write(encoded(payload))
    manifest = {"created_at": payload["created_at"], "phase": "frozen before independent 2026 target scores and starter flags",
        "protocol_sha256": digest(PROTOCOL), "forecast_path": str(FORECASTS.relative_to(ROOT)), "forecast_sha256": digest(FORECASTS),
        "code_sha256": {str(path.relative_to(ROOT)): digest(path) for path in CODE},
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in source_paths},
        "prior_sources": prior_sources, "prior_rates": counts, "input_games": len(fixtures), "requests": calls,
        "forecast_games": len(forecasts), "selected_bets": sum(f["bet"] is not None for f in forecasts),
        "reserve_bets": sum(f["reserve_bet"] is not None for f in forecasts),
        "strict_entry_age_300s_games": sum(f["strict_entry_age_300s"] for f in forecasts),
        "exclusions": dict(Counter(r["reason"] for r in exclusions))}
    with MANIFEST.open("xb") as handle:
        handle.write(encoded(manifest))
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("code_sha256", "input_sha256", "prior_sources")}, indent=2))


def outcome_for(forecast, plays, names):
    try:
        first = first_score(plays)
    except (StopIteration, ValueError, TypeError, KeyError):
        return {"status": "unresolved", "reason": "invalid_independent_first_score"}
    eid = str(first.get("athlete_id_1"))
    if eid in ("None", "", "nan"):
        return {"status": "unresolved", "reason": "missing_scorer_identity"}
    if names.get(eid) != {norm(first.get("athlete_name_1") or "")}:
        return {"status": "unresolved", "reason": "scorer_id_name_conflict"}
    match = [r for r in forecast["runners"] if r["espn_athlete_id"] == eid]
    if match and norm(match[0]["name"]) != norm(first.get("athlete_name_1") or ""):
        return {"status": "unresolved", "reason": "scorer_id_name_conflict"}
    scorer = match[0]["player_id"] if len(match) == 1 else "unlisted-espn:" + eid
    return {"status": "resolved", "scorer": scorer, "espn_athlete_id": eid, "name": first.get("athlete_name_1"),
            "points": first["score_value"], "game_clock": first["clock_display_value"], "listed": bool(match)}


def settle(bet, forecast, outcome, roster):
    if bet is None:
        return {"status": "no_bet", "profit": 0.0}
    invalid = {"status": "unresolved", "profit": None, "reason": "starter_status_unknown"}
    sides = {forecast["home_team_id"], forecast["away_team_id"]}
    if (not roster or len({str(r["athlete_id"]) for r in roster}) != len(roster)
            or any(r["athlete_id"] is None or not isinstance(r["starter"], bool) or str(r["team_id"]) not in sides for r in roster)):
        return invalid
    starters = Counter(str(r["team_id"]) for r in roster if r["starter"])
    if starters != Counter({team: 5 for team in sides}):
        return invalid
    selected = next(r for r in forecast["runners"] if r["player_id"] == bet["player_id"])
    matches = [r for r in roster if str(r["athlete_id"]) == selected["espn_athlete_id"]]
    if len(matches) != 1:
        return invalid
    if not matches[0]["starter"]:
        return {"status": "void", "profit": 0.0}
    if outcome["status"] != "resolved":
        return {"status": "unresolved", "profit": None, "reason": outcome["reason"]}
    won = outcome["scorer"] == bet["player_id"]
    return {"status": "win" if won else "loss", "profit": .98 * (bet["decimal"]-1) if won else -1.0}


def grade():
    import pyarrow.parquet as pq
    manifest = json.loads(MANIFEST.read_text())
    if digest(FORECASTS) != manifest["forecast_sha256"] or digest(PROTOCOL) != manifest["protocol_sha256"]:
        raise ValueError("Frozen forecasts/protocol changed")
    for path, expected in {**manifest["code_sha256"], **manifest["input_sha256"]}.items():
        if digest(ROOT / path) != expected:
            raise ValueError("Frozen source or code changed: " + path)
    forecasts = json.loads(FORECASTS.read_text())["forecasts"]
    ids = [int(f["espn_game_id"]) for f in forecasts]
    columns = ["game_id", "sequence_number", "period_number", "clock_display_value", "scoring_play", "score_value",
               "home_score", "away_score", "athlete_name_1", "athlete_id_1"]
    plays = old.unique_index(pq.read_table(PBP, columns=columns, filters=[("game_id", "in", ids)]).to_pylist(), "game_id") if ids else {}
    rosters = old.unique_index(pq.read_table(BOX, columns=["game_id", "athlete_id", "athlete_display_name", "team_id", "starter"],
        filters=[("game_id", "in", ids)]).to_pylist(), "game_id") if ids else {}
    rows = []
    for f in forecasts:
        eid = int(f["espn_game_id"])
        names = defaultdict(set)
        for r in rosters.get(eid, []):
            if r["athlete_id"] is not None and r["athlete_display_name"]:
                names[str(r["athlete_id"])].add(norm(r["athlete_display_name"]))
        outcome = outcome_for(f, plays.get(eid, []), names)
        rows.append({"fixture_id": f["fixture_id"], "week": f["week"], "outcome": outcome,
            "strict_entry_age_300s": f["strict_entry_age_300s"],
            "settlement": settle(f["bet"], f, outcome, rosters.get(eid, [])),
            "reserve_settlement": settle(f["reserve_bet"], f, outcome, rosters.get(eid, [])),
            "bet_diagnostics": {"settlement": f["bet"], "reserve_settlement": f["reserve_bet"]},
            "scores": {m: old.scoring(p, outcome["scorer"]) for m, p in f["probabilities"].items()} if outcome["status"] == "resolved" else None})
    graded = OUT / "graded.json"
    with graded.open("xb") as handle:
        handle.write(encoded(rows))
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "forecast_sha256": manifest["forecast_sha256"],
        "protocol_sha256": manifest["protocol_sha256"], "input_games": manifest["input_games"],
        "forecast_games": len(rows), "exclusions": manifest["exclusions"], "comparisons": 16,
        "results": wedge.summarize(rows, "settlement"), "reserve_sensitivity": wedge.summarize(rows, "reserve_settlement"),
        "strict_entry_age_300s_diagnostic": wedge.summarize([r for r in rows if r["strict_entry_age_300s"]], "settlement"),
        "outcomes": dict(Counter(r["outcome"]["status"] for r in rows)),
        "unlisted_scorers": sum(r["outcome"].get("listed") is False for r in rows),
        "graded_path": str(graded.relative_to(ROOT)), "graded_sha256": digest(graded),
        "edge_established": False,
        "limitations": ["Conditional original market identity; quote jurisdiction/display labels unavailable",
            "Latest provider entry assumed to persist; historical execution and bookmaker freshness unverified",
            "One fixed month cannot provide the required eight calendar weeks for inference",
            "No prospective evidence; no wagers, alerts or scheduled collectors enabled"]}
    with REPORT.open("xb") as handle:
        handle.write(encoded(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "grade"))
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else grade()
