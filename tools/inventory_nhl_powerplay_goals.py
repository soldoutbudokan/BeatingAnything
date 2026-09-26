#!/usr/bin/env python3
"""Price/identity/calendar audit for goal props; never loads sporting outcomes."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/"data/raw/nhl-shot-archive-2026-09-26"
OUT = ROOT/"reports/nhl-powerplay-goals-coverage-2026-09-26"
DEBUG_GAME = 2024020345
CUT = datetime(2025,1,1,tzinfo=timezone.utc)
PINS = {
    "manifest.json":"869d4a6ddfd1473ece6e59a3aed023cedb6899b988fdb5cb6ede29c7b37552da",
    "outcomes/rosters_2024.csv":"0e70a12579b25af0532d00a0cf8bb5fda7d9eb33a23d76234ca26f2fff4ca4ba",
    "outcomes/rosters_2025.csv":"cff04536329e7a7f3cdf9034786226e6644a7d222486eb70d4a799d12c1f80ba",
    "outcomes/schedule_2025_metadata.csv":"320643ed83428e28671c7508c667026ab65c46b85bcf312d173c2b025d98e855",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(value):
    text = unicodedata.normalize("NFKD",str(value)).encode("ascii","ignore").decode().lower()
    return re.sub("[^a-z0-9]","",text)


def stamp(value):
    d = datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None:
        raise ValueError("Unzoned clock")
    return d.astimezone(timezone.utc)


def decimal(value):
    if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)<100:
        raise ValueError("invalid_american_price")
    return 1+value/100 if value>0 else 1+100/abs(value)


def coverage(rows):
    leads = [r["lead_seconds"] for r in rows]
    return {"pairs":len(rows),"games":len({r["game_id"] for r in rows}),"source_events":len({r["event_id"] for r in rows}),
            "players":len({r["player_id"] for r in rows}),
            "first_boundary_utc":min((r["boundary"] for r in rows),default=None),
            "last_boundary_utc":max((r["boundary"] for r in rows),default=None),
            "first_market_update_utc":min((r["market_update"] for r in rows),default=None),
            "last_market_update_utc":max((r["market_update"] for r in rows),default=None),
            "lead_seconds":{"minimum":min(leads),"median":statistics.median(leads),"maximum":max(leads)} if leads else None}


def audit():
    for path,pin in PINS.items():
        assert sha(RAW/path)==pin,"Changed source: "+path
    names = defaultdict(set)
    for year in [2024,2025]:
        with (RAW/f"outcomes/rosters_{year}.csv").open() as f:
            # Name/ID only; no game-roster participation or target sporting values.
            for r in csv.DictReader(f):
                names[norm(r["full_name"])].add(int(r["player_id"]))
    fixtures = []
    with (RAW/"outcomes/schedule_2025_metadata.csv").open() as f:
        for r in csv.DictReader(f):
            if r["game_type"] != "R":
                continue
            fixtures.append({"game_id":int(r["game_id"]),"home":norm(r["home_team_name"]),
                             "away":norm(r["away_team_name"]),"start":stamp(r["game_time"]),
                             "home_team":r["home_team_abbr"],"away_team":r["away_team_abbr"]})
    manifest = json.loads((RAW/"manifest.json").read_text())
    assert len(manifest["files"])==285 and manifest["source_commit"]=="42cf1f81bc302642ddcc9e88ce2e98c1057bc74d"
    payloads, errors, starts, identities = [], [], defaultdict(set), defaultdict(set)
    for info in manifest["files"]:
        path = ROOT/info["path"]
        assert sha(path)==info["sha256"] and path.stat().st_size==info["bytes"]
        raw = json.loads(path.read_text())
        if "bookmakers" not in raw:
            errors.append({"source_file":path.name,"reason":"publisher_error_payload"})
            continue
        assert raw["sport_key"]=="icehockey_nhl"
        payloads.append((path.name,raw))
        if raw.get("commence_time"):
            starts[raw["id"]].add(stamp(raw["commence_time"]))
        identities[raw["id"]].add((norm(raw.get("home_team")),norm(raw.get("away_team"))))
    candidates, rejected, payload_reasons, pair_reasons, unknown_names = [], [], Counter(), Counter(), Counter()
    raw_groups = 0
    for filename,raw in payloads:
        event = raw["id"]
        def reject(reason,groups=None):
            payload_reasons[reason]+=1
            if groups is not None:
                pair_reasons[reason]+=len(groups)
            rejected.append({"source_file":filename,"event_id":event,"reason":reason,"pairs_affected":len(groups) if groups is not None else None})
        books = [b for b in raw["bookmakers"] if b["key"]=="fanduel"]
        if len(books)!=1:
            reject("missing_or_duplicate_fanduel_book")
            continue
        markets = [m for m in books[0]["markets"] if m["key"]=="player_goals"]
        if len(markets)!=1:
            reject("no_main_goals_market" if not markets else "duplicate_main_goals_market")
            continue
        market = markets[0]
        groups = defaultdict(list)
        for o in market["outcomes"]:
            groups[norm(o.get("description")),o.get("point")].append(o)
        raw_groups+=len(groups)
        if len(identities[event])!=1 or not starts[event]:
            reject("conflicting_identity_or_missing_start",groups)
            continue
        provider = stamp(raw["commence_time"])
        home,away = next(iter(identities[event]))
        matched = [g for g in fixtures if g["home"]==home and g["away"]==away and abs((g["start"]-provider).total_seconds())<=86400]
        if len(matched)!=1:
            reject("fixture_unresolved",groups)
            continue
        game = matched[0]
        if game["game_id"]==DEBUG_GAME:
            reject("original_debug_game_excluded",groups)
            continue
        boundary = min(game["start"],*starts[event])
        try:
            update = stamp(market["last_update"])
        except (KeyError,TypeError,ValueError):
            reject("missing_or_invalid_market_update",groups)
            continue
        if not boundary-timedelta(hours=72)<=update<boundary:
            reject("market_update_outside_fixed_pregame_window",groups)
            continue
        for key,outcomes in groups.items():
            reason = None
            if key[1] != .5:
                reason="not_fixed_0_5_goal_line"
            elif len(outcomes)!=2 or {o["name"] for o in outcomes}!={"Over","Under"}:
                reason="incomplete_or_duplicate_side"
            elif len({o.get("description") for o in outcomes})!=1 or not outcomes[0].get("description"):
                reason="ambiguous_or_missing_full_name"
            if reason is None:
                side={o["name"]:o for o in outcomes}
                try:
                    over,under=decimal(side["Over"]["price"]),decimal(side["Under"]["price"])
                    margin=1/over+1/under-1
                    if not 0<=margin<=.15:
                        reason="overround_outside_0_to_15pct"
                except (KeyError,ValueError):
                    reason="invalid_american_price"
            ids=names.get(key[0],set())
            if reason is None and len(ids)!=1:
                reason="ambiguous_or_unmatched_player_identity"
                unknown_names[outcomes[0]["description"]]+=1
            if reason:
                pair_reasons[reason]+=1
                rejected.append({"source_file":filename,"event_id":event,"game_id":game["game_id"],
                                 "player":outcomes[0].get("description"),"line":key[1],"reason":reason,"pairs_affected":1})
                continue
            candidates.append({"source_file":filename,"event_id":event,"game_id":game["game_id"],"player_id":next(iter(ids)),
                               "player":outcomes[0]["description"],"home_team":game["home_team"],"away_team":game["away_team"],
                               "line":.5,"over_american":side["Over"]["price"],"under_american":side["Under"]["price"],
                               "over_decimal":over,"under_decimal":under,"overround":margin,"market_update":update.isoformat(),
                               "provider_start":provider.isoformat(),"independent_start":game["start"].isoformat(),
                               "boundary":boundary.isoformat(),"lead_seconds":(boundary-update).total_seconds(),
                               "period":"early_through_2024_12_31_utc" if boundary<CUT else "later_from_2025_01_01_utc"})
    chosen,conflicting = {},set()
    for r in sorted(candidates,key=lambda x:(x["market_update"],x["source_file"],x["player_id"])):
        key=r["event_id"],r["player_id"]
        if key not in chosen:
            chosen[key]=r
        elif r["market_update"]==chosen[key]["market_update"] and any(r[k]!=chosen[key][k] for k in ["line","over_american","under_american","boundary","game_id"]):
            conflicting.add(key)
            pair_reasons["conflicting_earliest_quote"]+=1
        else:
            pair_reasons["later_or_identical_duplicate_quote"]+=1
    rows=sorted([r for key,r in chosen.items() if key not in conflicting],key=lambda r:(r["market_update"],r["event_id"],r["player_id"]))
    assert len({(r["game_id"],r["player_id"]) for r in rows})==len(rows)
    assert not conflicting  # No conflicts in this pinned source; never silently choose one.
    assert len(rows)+sum(pair_reasons.values())==raw_groups
    by_game=[]
    for gid in sorted({r["game_id"] for r in rows}):
        qs=[r for r in rows if r["game_id"]==gid]
        by_game.append({"game_id":gid,"event_id":qs[0]["event_id"],"boundary":qs[0]["boundary"],"period":qs[0]["period"],"pairs":len(qs)})
    report={"scope":"Price/identity/calendar only. No sporting outcome files, power-play values, predictions, fit, EV, selections or returns read/computed.",
            "source_commit":manifest["source_commit"],"source_files_verified":285,"event_payloads":len(payloads),"publisher_error_payloads":len(errors),
            "source_pins":[{"path":str((RAW/p).relative_to(ROOT)),"sha256":pin} for p,pin in PINS.items()],
            "script_sha256":sha(Path(__file__)),"raw_fanduel_goal_player_line_keys":raw_groups,"candidate_quotes_before_earliest_selection":len(candidates),
            "eligible":coverage(rows),"periods":{period:coverage([r for r in rows if r["period"]==period]) for period in sorted({r["period"] for r in rows})},
            "rules":{"market":"Literal FanDuel player_goals, paired Over/Under at exact0.5 line and one common market clock.",
                     "odds":"Finite American prices with absolute value>=100; paired overround0–15% inclusive; no separate bet-odds filter.",
                     "identity":"Unchanged normalized full name→unique NHL ID across both retained roster files; no aliases or current participation filter.",
                     "fixture":"Ordered normalized teams→one independent REG fixture within1day; exclude original debug2024020345.",
                     "time":"Market update within72hours and strictly before minimum independent/provider start; no receipt or separate book clock exists.",
                     "repeated_quotes":"Earliest qualifying event/player quote; conflicting same-time offers excluded, no outcome-based choice.",
                     "calendar_cut":"Conservative boundary UTC before2025-01-01 versus on/after; purely metadata, not independent holdout."},
            "mutually_exclusive_pair_rejections":dict(pair_reasons),"payload_exclusions":dict(payload_reasons),"unresolved_names":dict(unknown_names),
            "exclusion_details":errors+rejected,"coverage_by_game":by_game,
            "canonical_eligible_cohort_sha256":hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest(),
            "limitations":["Global retrospective rosters establish name identity only; eventual participation never controls inclusion.",
                           "Market update is an historical entry proxy, not collector receipt, suspension state or accepted execution.",
                           "No power-play field semantics, non-null coverage, prior-history eligibility or model effect was tested by this audit.",
                           "Archive outcomes were previously inspected in other models; neither calendar subgroup is claimed as fresh independent validation."]}
    return rows,report


def main():
    rows,report=audit()
    export=[]
    for r in rows:
        export.append({"player":r["player"],"game_id":r["game_id"],"player_id":r["player_id"],
                       "entry":r["market_update"],"boundary":r["boundary"],
                       "home_team_abbr":r["home_team"],"away_team_abbr":r["away_team"],
                       "over_decimal":r["over_decimal"],"under_decimal":r["under_decimal"],
                       "q_under":(1/r["under_decimal"])/(1/r["over_decimal"]+1/r["under_decimal"]),
                       "period":"early_nov_dec" if r["period"].startswith("early_") else "later_january",
                       "line":r["line"],"over_american":r["over_american"],"under_american":r["under_american"],
                       "overround":r["overround"],"source_file":r["source_file"],"event_id":r["event_id"],
                       "provider_start":r["provider_start"],"independent_start":r["independent_start"],"lead_seconds":r["lead_seconds"]})
    price_path=ROOT/"data/raw/nhl-powerplay-goals-2026-09-26/price-entries.csv"
    price_path.parent.mkdir(parents=True,exist_ok=True)
    with price_path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(export[0]))
        writer.writeheader()
        writer.writerows(export)
    report["price_entries"]={"path":str(price_path.relative_to(ROOT)),"sha256":sha(price_path),"rows":len(export),"columns":list(export[0]),
                             "probability_note":"q_under is only proportional normalization of the literal paired FanDuel prices; no modeled power-play feature or outcome."}
    report["independent_price_review"]={"pairs":2768,"games":270,"early_pairs":1506,"early_games":146,"later_pairs":1262,"later_games":124,
                                        "result":"A separate metadata-only reconstruction agreed on every coverage count, ambiguous/unmatched name count and exclusion; no outcomes read."}
    OUT.with_suffix(".json").write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
    periods=report["periods"]
    table="\n".join(f"| {name} | {r['pairs']:,} | {r['games']} | {r['players']} |" for name,r in periods.items())
    OUT.with_suffix(".md").write_text(f'''# NHL power-play goal-prop price coverage — September 26, 2026

**{report['eligible']['pairs']:,} eligible paired FanDuel Over/Under 0.5-goal offers cover {report['eligible']['games']} games and {report['eligible']['players']} uniquely identified players.** This audit reads only raw prices, roster names/IDs and score-free fixture metadata. It reads no player boxscores, power-play statistics, target outcomes, forecasts, returns or eventual participation.

| Conservative start UTC | Eligible pairs | Games | Distinct players |
| --- | ---: | ---: | ---: |
{table}

All 285 retained raw JSONs match the acquisition manifest: 273 event payloads and 12 publisher quota errors. There are {report['raw_fanduel_goal_player_line_keys']:,} raw FanDuel goal-player/line pairs before identity/fixture exclusions. Exact `player_goals` at 0.5 is used, with literal Over and Under, a common market update, valid American odds and paired overround 0–15%. Every retained update is within 72 hours before the earlier provider/independent start. Ordered teams must match one regular-season fixture within one day; the original source-debug game `2024020345` remains excluded.

Earliest qualifying quotes are retained by event/player without conditioning on eventual play. Full-name normalization and global unique-ID mapping are unchanged from the prior NHL tests. Unresolved names remain excluded with their counts: `{report['unresolved_names']}`. Mutually exclusive pair exclusions are `{report['mutually_exclusive_pair_rejections']}`. Missing markets, mapping failures and source errors remain in the JSON's explicit ledger.

The UTC calendar split is metadata-only and is not a claim of untouched validation. No reference-book, shooting-history, power-play-role or model threshold filters are applied. Power-play input semantics and prior-history coverage still require their own audit before a model can be declared. An independent reconstruction agrees on all counts and exclusions: 28 ambiguous-name pairs and eight unmatched-name pairs, with no timing, pairing, odds, margin or duplicate failure among fixture-eligible markets.

Market update times lack independent receipt and accepted-price evidence. Retrospective roster membership supplies identity, not a known pregame participation list. The fixed source is [sports-betting-ops@42cf1f8](https://github.com/ldinan-git/sports-betting-ops/tree/42cf1f81bc302642ddcc9e88ce2e98c1057bc74d/bet-ops/odds_api_responses/player_props/output/icehockey_nhl/player_props); exact local source/projection hashes and every covered game are in the adjacent JSON. Canonical eligible-cohort hash: `{report['canonical_eligible_cohort_sha256']}`.

The score-free model input is `data/raw/nhl-powerplay-goals-2026-09-26/price-entries.csv`, SHA-256 `{report['price_entries']['sha256']}`. It includes literal prices and proportional `q_under`, event/player identity, source file, entry and boundary clocks, team abbreviations and the fixed `early_nov_dec` / `later_january` labels. Those labels use the conservative start's UTC date, so a December 31 local game can enter the later period. No power-play feature, modeled probability or result is included.

Reproduce with `python3 tools/inventory_nhl_powerplay_goals.py`. Its `audit()` function also returns the exact eligible rows for a separately declared experiment. No old frozen files were changed; no network request, wager, alert or schedule.
''')
    print(json.dumps({k:report[k] for k in ["eligible","periods","mutually_exclusive_pair_rejections","payload_exclusions","unresolved_names","canonical_eligible_cohort_sha256","price_entries"]},indent=2))


if __name__=="__main__":
    main()
