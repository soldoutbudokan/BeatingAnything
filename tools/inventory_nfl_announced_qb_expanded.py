#!/usr/bin/env python3
"""Score-free announcement/price join and the declared prior-club coverage proxy.

This deliberately reads only explicit metadata columns from mixed NFL exports.
It neither extracts receiver roles nor loads target sporting outcomes.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/nfl-qb-kneel-props-2026-09-26"
PRICE = ROOT / "data/raw/nfl-announced-qb-expanded-price-inventory-2026-09-26/eligible-price-rows.csv"
REPORT = ROOT / "reports/nfl-announced-qb-expanded-2026-09-26"
LEDGERS = {region: ROOT / f"reports/nfl-announced-qb-source-{region}-2026-09-26.json"
           for region in ("nfc", "afc-north-south", "afc-east-west")}
DECLARATIONS = [ROOT / f"docs/{name}-2026-09-26.md" for name in (
    "nfl-announced-qb-expanded-inventory-declaration",
    "nfl-announced-qb-quote-dedup-addendum", "nfl-announced-qb-prior-team-addendum")]
PRICE_COLS = ["game_id", "player_id", "player", "actual_snapshot_time", "event_id", "line",
              "over_price", "under_price", "over_decimal", "under_decimal", "overround",
              "bookmaker_last_update", "market_last_update", "bookmaker_key", "market_key",
              "independent_start", "commence_time", "boundary", "week", "season",
              "home_team_abbr", "away_team_abbr", "roster_compatible_fixture_team"]
GAME_COLS = ["game_id", "season", "game_type", "week", "gameday", "gametime", "home_team", "away_team"]
HISTORY_COLS = ["player_id", "season", "week", "season_type", "recent_team"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


def club(value):
    return {"LAR": "LA"}.get(value, value)


def record_file(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}


def announced_cases(ledgers):
    cases = []
    receipts = {}
    reused = {}

    def receipt(row):
        path = row.get("path") or row.get("receipt_path")
        if path:
            actual = record_file(ROOT / path)
            assert actual["sha256"] == row["sha256"], (path, "source hash mismatch")
            receipts[path] = actual
        if row.get("reuse_from_report"):
            path = row["reuse_from_report"]
            actual = record_file(ROOT / path)
            assert actual["sha256"] == row["reuse_report_sha256"], (path, "reused audit hash mismatch")
            reused[path] = actual

    for row in ledgers["nfc"]["cases"]:
        if not row.get("qualifies_announcement_and_any_price"):
            continue
        receipt(row["source_receipt"])
        meta = row["article_metadata"]
        time = max(stamp(meta[k]) for k in ("datePublished", "dateModified") if meta.get(k))
        assert time == stamp(row["evidence_time_utc"])
        for game_id in row["qualified_game_ids"]:
            cases.append(dict(game_id=game_id, team=row["team"], episode=row["episode_id"],
                              evidence_time=iso(time), region="nfc", source_urls=[meta.get("url", row["url"])],
                              source_ids=[row["id"]]))
    north = ledgers["afc-north-south"]
    ns_receipts = {r["id"]: r for r in north["primary_receipts"]}
    for row in north["qualified"]:
        receipt(ns_receipts[row["source_id"]])
        time = max(stamp(t) for t in row["source_published_utc"] + row["source_modified_utc"])
        assert time == stamp(row["latest_source_clock_utc"])
        cases.append(dict(game_id=row["game_id"], team=row["team"], episode=row["episode"],
                          evidence_time=iso(time), region="afc-north-south", source_urls=[row["source_url"]],
                          source_ids=[row["source_id"]]))
    east = ledgers["afc-east-west"]
    ew_sources = {r["id"]: r for r in east["sources"]}
    for row in east["qualified_announcements"]:
        sources = [ew_sources[k] for k in row["required_source_ids"]]
        for source in sources:
            receipt(source)
        time = max(stamp(s["conservative_clock_utc"]) for s in sources)
        assert time == stamp(row["announcement_clock_utc"])
        # No assertion that the nested LV injuries are independent episodes.
        episode = "LV_Minshew_absence_nested_OConnell_knee" if row["team"] == "LV" else row["absence_episode_candidate"]
        cases.append(dict(game_id=row["game_id"], team=row["team"], episode=episode,
                          evidence_time=iso(time), region="afc-east-west",
                          source_urls=[s["canonical_url"] for s in sources], source_ids=row["required_source_ids"]))
    assert len({(c["game_id"], c["team"]) for c in cases}) == len(cases)
    return sorted(cases, key=lambda r: (r["game_id"], r["team"])), list(receipts.values()), list(reused.values())


def load_history():
    # Explicit projections are essential: both source files contain outcomes.
    games = pd.read_csv(DATA / "games.csv", usecols=GAME_COLS, dtype=str, keep_default_na=False)
    games = games[(games.season == "2024") & (games.game_type == "REG")]
    fixtures = {}
    by_id = {}
    for row in games.to_dict("records"):
        start = datetime.fromisoformat(row["gameday"] + "T" + row["gametime"]).replace(
            tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        item = dict(game_id=row["game_id"], week=int(row["week"]), independent_start=iso(start),
                    available_after=iso(start + timedelta(hours=72)))
        by_id[row["game_id"]] = item
        for team in (row["home_team"], row["away_team"]):
            key = (int(row["season"]), int(row["week"]), club(team))
            assert key not in fixtures, (key, "ambiguous fixture")
            fixtures[key] = item
    history = pd.read_csv(DATA / "player_stats_2024.csv", usecols=HISTORY_COLS, dtype=str, keep_default_na=False)
    history = history[(history.season == "2024") & (history.season_type == "REG")]
    players = defaultdict(list)
    unmatched = []
    for row in history.to_dict("records"):
        team = club(row["recent_team"])
        key = (int(row["season"]), int(row["week"]), team)
        if key not in fixtures:
            unmatched.append(row)
            continue
        players[row["player_id"]].append({**fixtures[key], "team": team})
    return players, by_id, unmatched, len(history)


def price_assertions(row):
    entry = stamp(row["actual_snapshot_time"])
    assert row["bookmaker_key"] == "fanduel" and row["market_key"] == "player_reception_yds"
    assert row["season"] == "2024"
    for side in ("over", "under"):
        a = float(row[f"{side}_price"])
        assert abs(a) >= 100
        d = 1 + a / 100 if a > 0 else 1 - 100 / a
        assert 1.2 <= d <= 6 and abs(d - float(row[f"{side}_decimal"])) < 1e-12
    margin = 1 / float(row["over_decimal"]) + 1 / float(row["under_decimal"]) - 1
    assert 0 <= margin <= .12 and abs(margin - float(row["overround"])) < 1e-12
    for field in ("bookmaker_last_update", "market_last_update"):
        assert 0 <= (entry - stamp(row[field])).total_seconds() <= 300
    assert stamp(row["boundary"]) == min(stamp(row["independent_start"]), stamp(row["commence_time"]))
    assert entry < stamp(row["boundary"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-stem", type=Path, default=REPORT)
    args = parser.parse_args()
    outputs = [args.output_stem.with_suffix(ext) for ext in (".json", ".md")]
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing output: {path}")
    ledgers = {key: json.loads(path.read_text()) for key, path in LEDGERS.items()}
    cases, receipts, reused = announced_cases(ledgers)
    price = pd.read_csv(PRICE, usecols=PRICE_COLS, dtype=str, keep_default_na=False).to_dict("records")
    history, fixtures, unmapped_history, history_count = load_history()
    # An unmappable club cannot silently acquire a favorable temporal attribution.
    assert not unmapped_history, "Unmapped history rows require explicit uncertainty handling before proceeding"
    rows, omitted, preannouncement = [], [], 0
    for case in cases:
        candidates = defaultdict(list)
        for row in price:
            if row["game_id"] != case["game_id"]:
                continue
            price_assertions(row)
            assert stamp(row["independent_start"]) == stamp(fixtures[row["game_id"]]["independent_start"])
            if stamp(row["actual_snapshot_time"]) <= stamp(case["evidence_time"]):
                preannouncement += 1
                continue
            candidates[row["player_id"]].append(row)
        for player_id, quotes in candidates.items():
            first = min(stamp(q["actual_snapshot_time"]) for q in quotes)
            earliest = [q for q in quotes if stamp(q["actual_snapshot_time"]) == first]
            if len({float(q["line"]) for q in earliest}) != 1:
                omitted.append(dict(game_id=case["game_id"], player_id=player_id, reason="multiline_at_earliest_entry"))
                continue
            # Exact duplicate rows may collapse; conflicting literal pairs must not be selected arbitrarily.
            assert len({(q["event_id"], q["line"], q["over_price"], q["under_price"],
                        q["bookmaker_last_update"], q["market_last_update"]) for q in earliest}) == 1
            quote = earliest[0]
            prior = [r for r in history[player_id] if stamp(r["available_after"]) < first]
            assert all(r["game_id"] != case["game_id"] for r in prior)
            latest = max((stamp(r["available_after"]) for r in prior), default=None)
            evidence = [r for r in prior if stamp(r["available_after"]) == latest]
            evidence = [dict(t) for t in {tuple(sorted(r.items())) for r in evidence}]
            evidence.sort(key=lambda r: (r["game_id"], r["team"]))
            teams = {r["team"] for r in evidence}
            previous_team = next(iter(teams)) if len(teams) == 1 else None
            if not previous_team:
                classification = "unresolved"
            elif previous_team == case["team"]:
                classification = "matching"
            elif previous_team in (quote["home_team_abbr"], quote["away_team_abbr"]):
                classification = "opposite"
            else:
                classification = "other"
            rows.append({**quote, "announced_team": case["team"], "episode": case["episode"],
                         "announcement_evidence_time": case["evidence_time"],
                         "prior_team_classification": classification, "latest_prior_team": previous_team,
                         "prior_evidence": evidence, "prior_available_records": len(prior),
                         "unresolved_reason": ("no_available_2024_REG_record" if not evidence else
                                               "multiple_latest_clubs") if classification == "unresolved" else None,
                         "retrospective_roster_matching": quote["roster_compatible_fixture_team"] == case["team"],
                         "retrospective_roster_unknown": not quote["roster_compatible_fixture_team"]})
    rows.sort(key=lambda r: (r["game_id"], r["player_id"]))
    counts = Counter(r["prior_team_classification"] for r in rows)
    by_fixture = []
    for case in cases:
        cohort = [r for r in rows if r["game_id"] == case["game_id"] and r["announced_team"] == case["team"]]
        c = Counter(r["prior_team_classification"] for r in cohort)
        by_fixture.append({**case, "all_team_player_games": len(cohort), **{k: c[k] for k in ("matching", "opposite", "other", "unresolved")},
                           "matching_plus_unresolved": c["matching"] + c["unresolved"],
                           "retrospective_roster_matching": sum(r["retrospective_roster_matching"] for r in cohort),
                           "retrospective_roster_unknown": sum(r["retrospective_roster_unknown"] for r in cohort),
                           "entry_times": sorted({r["actual_snapshot_time"] for r in cohort})})
    bound = counts["matching"] + counts["unresolved"]
    strict_rows = [r for r in rows if r["announced_team"] != "LV"]
    strict_counts = Counter(r["prior_team_classification"] for r in strict_rows)
    strict = dict(team_games=len({(r["game_id"], r["announced_team"]) for r in strict_rows}),
                  all_team_unique_player_games=len(strict_rows),
                  **{k: strict_counts[k] for k in ("matching", "opposite", "other", "unresolved")},
                  conservative_player_game_bound_under_proxy=strict_counts["matching"] + strict_counts["unresolved"],
                  explanation="Exclude LV because overlapping injury episode discovery may exceed the per-episode query cap.")
    nfc_queries = Counter(r["phase"] for r in ledgers["nfc"]["queries"]["queries"])
    search_counts = dict(
        standardized_team_queries=nfc_queries["standardized_team_discovery"] +
        ledgers["afc-north-south"]["search_counts"]["standardized_team_queries"] +
        ledgers["afc-east-west"]["summary"]["standardized_queries"],
        targeted_queries=nfc_queries["targeted_episode_followup"] +
        ledgers["afc-north-south"]["search_counts"]["targeted_followups"] +
        ledgers["afc-east-west"]["summary"]["targeted_queries"])
    search_counts["total_queries"] = sum(search_counts.values())
    summary = dict(announcement_price_team_games=len(cases), unique_fixtures=len({r["game_id"] for r in rows}),
                   absence_episode_groups=len({c["episode"] for c in cases}),
                   all_team_unique_player_games=len(rows), **{k: counts[k] for k in ("matching", "opposite", "other", "unresolved")},
                   conservative_player_game_bound_under_proxy=bound, required_player_games=100,
                   below_original_gate=bound < 100,
                   retrospective_roster_matching=sum(r["retrospective_roster_matching"] for r in rows),
                   retrospective_roster_unknown=sum(r["retrospective_roster_unknown"] for r in rows),
                   preannouncement_price_rows_omitted=preannouncement, earliest_multiline_player_games_omitted=len(omitted))
    limitations = [
        "This is a bounded source-and-price feasibility inventory, not a model, forecast, return test or edge claim.",
        "Latest available prior club is the declared proxy, not transaction-proof target-game membership. Unknown clubs remain in the conservative bound; opposite/other prior clubs fail the proxy.",
        "The 72-hour start-based availability delay is a fixed assumption applied to a retrospective weekly metadata file; no contemporaneous historical release receipt establishes actual publication latency.",
        "Official pages were retrieved retrospectively. Their maximum publication/revision clock is source-asserted; reused Miami sources retain metadata/hash evidence but not full HTML.",
        "There were 32 standardized team queries and 40 targeted queries, 72 total. LV injury follow-ups were budgeted separately for overlapping O'Connell thumb, Minshew collarbone and O'Connell knee absences, a potential per-episode query-cap deviation. The inclusive cohort retains LV only as a generous coverage check; strict sensitivity excludes it. Other unresolved weekly replacement confirmations are not carried forward. This is not an exhaustive injury-episode census.",
        "Published processed prices lack original upstream raw JSON/unmerged sides. Publisher code passes odds through, but duplicate key omits snapshot time and can overwrite side prices while retaining first-row clocks. Literal row-clock eligibility cannot independently authenticate side-price/clock association.",
        "Retrospective roster team compatibility is diagnostic only. No target-game appearance, receiver-role, air-yard-share, target outcome, score or actual-starter column was used in this computation.",
        "Official-source searches exposed incidental outcome snippets, and earlier research inspected some NFL labels. This inventory makes no globally uninspected or fresh-holdout claim.",
        "LV's nested O'Connell injury occurs within the broader Minshew absence; the grouping is not an independence claim."
    ]
    payload = dict(schema_version=1, status="insufficient_coverage_under_declared_prior_team_proxy" if bound < 100 else "role_gate_pending",
                   prepared_at_utc=iso(datetime.now(timezone.utc)),
                   script=record_file(Path(__file__)), declarations=[record_file(p) for p in DECLARATIONS],
                   source_ledgers={k: record_file(p) for k, p in LEDGERS.items()},
                   inputs=[record_file(p) for p in (PRICE, DATA / "games.csv", DATA / "player_stats_2024.csv")],
                   explicit_usecols={"price_entries": PRICE_COLS, "independent_fixtures": GAME_COLS, "weekly_player_metadata": HISTORY_COLS},
                   source_receipts_verified=receipts, reused_source_audits_verified=reused,
                   history_projection=dict(regular_season_metadata_rows=history_count, unmapped_fixture_rows=len(unmapped_history),
                                           availability_rule="independent UTC fixture start + 72 hours strictly before entry"),
                   summary=summary, strict_without_lv=strict, search_counts=search_counts,
                   by_fixture=by_fixture, omitted_player_games=omitted, rows=rows,
                   target_outcomes_loaded=False, receiver_role_values_loaded=False, model_fitted=False,
                   forecasts_or_returns_computed=False, limitations=limitations)
    args.output_stem.parent.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(payload, indent=2) + "\n")
    md = ["# Expanded announced-QB source/price feasibility", "",
          f"The ten announcement-qualified fixtures contain **{len(rows)} distinct priced player-games across both teams**. The declared prior-team proxy retains **{counts['matching']} matching** and **{counts['unresolved']} unresolved**, a conservative coverage bound of **{bound}**, below the unchanged **100-receiver-game** gate. {counts['opposite']} latest prior clubs are opponents and {counts['other']} are other clubs. The exact retained cohort therefore stops before receiver-role extraction, modeling or grading; the underlying hypothesis remains unresolved.", "",
          "| Fixture | Offense | All teams | Matching | Opposite | Other | Unknown | Matching + unknown |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in by_fixture:
        md.append(f"| {r['game_id']} | {r['team']} | {r['all_team_player_games']} | {r['matching']} | {r['opposite']} | {r['other']} | {r['unresolved']} | {r['matching_plus_unresolved']} |")
    md += ["", f"The generous inclusive bound retains Las Vegas despite a possible discovery query-cap deviation across overlapping injuries. Excluding LV gives **{strict['team_games']} fixtures / {strict['all_team_unique_player_games']} both-team player-games** and **{strict['matching']} matching + {strict['unresolved']} unknown = {strict['conservative_player_game_bound_under_proxy']}** under the proxy. Even the strict both-team ceiling is below 100. No further source query was used to resolve the LV episode boundary.", "",
           f"The source search covered all 32 teams with {search_counts['standardized_team_queries']} standardized and {search_counts['targeted_queries']} targeted queries ({search_counts['total_queries']} total). These ten fixtures form seven absence groups: Miami's three quotes share Tua's absence, Green Bay's two share Love's injury, and Las Vegas is one nested episode. Seven groups are not proof of independent forecast errors. The LV discovery is not certified as fully protocol-compliant.", "",
           "Each quote is the earliest qualifying snapshot strictly after all required announcement evidence for that game/player. Ambiguous multiple lines at that exact time are omitted. The candidate prices retain legal American odds, both decimal sides 1.20–6, paired margin 0–12%, both recorded updates 0–300 seconds before entry, and entry before the earlier independent/provider start. No later quote rescues an earlier row's failed clock.", "",
           "Membership uses only the latest 2024 REG weekly player club whose independently matched fixture start plus 72 hours is strictly before entry. The JSON records every player's prior fixture, club, kickoff and availability time. It also preserves the 47 retrospective roster matches separately; those were provisional diagnostics, not the causal eligibility rule.", "",
           "Odell Beckham Jr. and Kendrick Bourne at MIA–NE have no available 2024 REG club record under that clock and remain unresolved. Both count toward the conservative bound; no current-game appearance or later club assignment resolves them.", "",
           "All input, source-ledger, declaration and retained source hashes are in the JSON. Reproduce in an isolated output location with `state/runtime/research-venv/bin/python tools/inventory_nfl_announced_qb_expanded.py --output-stem /tmp/nfl-announced-qb-expanded-check`; the script refuses to overwrite outputs.", "",
           "Rules: [inventory declaration](../docs/nfl-announced-qb-expanded-inventory-declaration-2026-09-26.md), [quote deduplication](../docs/nfl-announced-qb-quote-dedup-addendum-2026-09-26.md), [prior-team proxy](../docs/nfl-announced-qb-prior-team-addendum-2026-09-26.md). Sources: [NFC](nfl-announced-qb-source-nfc-2026-09-26.json), [AFC North/South](nfl-announced-qb-source-afc-north-south-2026-09-26.json), [AFC East/West](nfl-announced-qb-source-afc-east-west-2026-09-26.json).", "",
           "Material limitations:", ""] + ["- " + x for x in limitations]
    outputs[1].write_text("\n".join(md) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
