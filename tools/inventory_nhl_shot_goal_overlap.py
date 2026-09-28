#!/usr/bin/env python3
"""Strict raw-price/identity-only NHL shot-goal overlap census."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-shot-archive-2026-09-26"
OUTDIR = ROOT / "data/raw/nhl-shot-goal-overlap-2026-09-26"
REPORT = ROOT / "reports/nhl-shot-goal-overlap-feasibility-2026-09-26"
PINS = {
    # Deterministic replacement manifest from tools/rebuild_nhl_shot_archive.py (September 28, 2026);
    # the original 869d4a6d... manifest was lost with the uncommitted data directory. All 285 raw
    # payload hashes it lists equal the pins committed on September 26.
    "manifest.json": "9b43fc27fe396a7b37dd07af3e7f01ab56acb209578b2c5b0defb2bdfbeeed2f",
    "outcomes/rosters_2024.csv": "0e70a12579b25af0532d00a0cf8bb5fda7d9eb33a23d76234ca26f2fff4ca4ba",
    "outcomes/rosters_2025.csv": "cff04536329e7a7f3cdf9034786226e6644a7d222486eb70d4a799d12c1f80ba",
    "outcomes/schedule_2025_metadata.csv": "320643ed83428e28671c7508c667026ab65c46b85bcf312d173c2b025d98e855",
}
ROSTER_COLS = ["full_name", "player_id"]
FIXTURE_COLS = ["game_id", "game_type", "home_team_name", "away_team_name", "game_time", "home_team_abbr", "away_team_abbr"]
DEBUG_GAME = "2024020345"
CUT = datetime(2025, 1, 1, tzinfo=timezone.utc)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pin(p):
    return {"path": str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p), "sha256": sha(p), "bytes": p.stat().st_size}


def norm(s):
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower())


def stamp(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Unzoned clock")
    return t.astimezone(timezone.utc)


def decimal(p):
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or abs(p) < 100:
        raise ValueError("Invalid American price")
    p = Fraction(str(p))
    return 1 + p / 100 if p > 0 else 1 - 100 / p


def pairs(market, kind, reasons):
    groups = defaultdict(list)
    for o in market.get("outcomes", []):
        try:
            name, line = o.get("description"), Fraction(str(o.get("point")))
            if not isinstance(name, str) or not name.strip():
                raise ValueError
        except (ValueError, ZeroDivisionError):
            reasons[kind + ":invalid_name_or_line"] += 1
            continue
        groups[(name, line)].append(o)
    result = []
    for (name, line), outcomes in groups.items():
        if (kind == "goal" and line != Fraction(1, 2)) or (kind == "shot" and not (Fraction(1, 2) <= line <= Fraction(17, 2) and line.denominator == 2)):
            reasons[kind + ":line_outside_fixed_scope"] += 1
            continue
        if len(outcomes) != 2 or Counter(o.get("name") for o in outcomes) != Counter({"Over": 1, "Under": 1}):
            reasons[kind + ":missing_or_duplicate_sides"] += 1
            continue
        side = {o["name"]: o for o in outcomes}
        try:
            over, under = decimal(side["Over"]["price"]), decimal(side["Under"]["price"])
        except (ValueError, KeyError):
            reasons[kind + ":invalid_american"] += 1
            continue
        margin = 1 / over + 1 / under - 1
        if not 0 <= margin <= Fraction(3, 20):
            reasons[kind + ":overround_outside_scope"] += 1
            continue
        q = (1 / under) / (1 / over + 1 / under)
        result.append({"player": name, "line": line, "over_american": side["Over"]["price"],
                       "under_american": side["Under"]["price"], "over_decimal": over,
                       "under_decimal": under, "overround": margin, "q_under": q})
    return result


def summary(rows):
    return {"paired_player_games": len(rows), "games": len({r["game_id"] for r in rows}),
            "events": len({r["event_id"] for r in rows}), "players": len({r["player_id"] for r in rows})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTDIR)
    parser.add_argument("--report-stem", type=Path, default=REPORT)
    args = parser.parse_args()
    csvpath = args.output_dir / "paired-prices.csv"
    details_path = args.output_dir / "inventory-details.json"
    jp, mdp = args.report_stem.with_suffix(".json"), args.report_stem.with_suffix(".md")
    for p in (csvpath, details_path, jp, mdp):
        if p.exists():
            raise SystemExit(f"Refusing to overwrite {p}")
    for p, h in PINS.items():
        assert sha(RAW / p) == h
    names = defaultdict(set)
    for year in (2024, 2025):
        frame = pd.read_csv(RAW / f"outcomes/rosters_{year}.csv", usecols=ROSTER_COLS, dtype=str, keep_default_na=False)
        for r in frame.to_dict("records"):
            names[norm(r["full_name"])].add(r["player_id"])
    f = pd.read_csv(RAW / "outcomes/schedule_2025_metadata.csv", usecols=FIXTURE_COLS, dtype=str, keep_default_na=False)
    fixtures = [{**r, "home_key": norm(r["home_team_name"]), "away_key": norm(r["away_team_name"]),
                 "start": stamp(r["game_time"])} for r in f[f.game_type == "R"].to_dict("records")]
    manifest = json.loads((RAW / "manifest.json").read_text())
    assert manifest["source_commit"] == "42cf1f81bc302642ddcc9e88ce2e98c1057bc74d" and len(manifest["files"]) == 285
    payloads, sources = [], []
    starts, identities = defaultdict(set), defaultdict(set)
    attrition, pair_reasons, unknown = Counter(), Counter(), Counter()
    for spec in manifest["files"]:
        p = ROOT / spec["path"]
        assert sha(p) == spec["sha256"] and p.stat().st_size == spec["bytes"]
        sources.append(pin(p))
        r = json.loads(p.read_text())
        if "bookmakers" not in r:
            attrition["publisher_error_payload"] += 1
            continue
        assert r["sport_key"] == "icehockey_nhl"
        starts[r["id"]].add(stamp(r["commence_time"]))
        identities[r["id"]].add((norm(r["home_team"]), norm(r["away_team"])))
        payloads.append((p, r))
    rows, event_status = [], []
    for path, raw in payloads:
        event = raw["id"]
        status = {"event_id": event, "source_path": str(path.relative_to(ROOT))}
        reason = None
        provider = stamp(raw["commence_time"])
        matched = [g for g in fixtures if g["home_key"] == norm(raw["home_team"]) and g["away_key"] == norm(raw["away_team"]) and abs((g["start"] - provider).total_seconds()) <= 86400]
        if len(identities[event]) != 1 or not starts[event]:
            reason = "conflicting_identity_or_missing_start"
        elif len(matched) != 1:
            reason = "fixture_unresolved"
        elif matched[0]["game_id"] == DEBUG_GAME:
            reason = "original_debug_game_excluded"
        books = [b for b in raw["bookmakers"] if b.get("key") == "fanduel"]
        if reason is None and len(books) != 1:
            reason = "missing_or_duplicate_fd_node"
        if reason is not None:
            attrition[reason] += 1; event_status.append({**status, "reason": reason}); continue
        book = books[0]
        shot_nodes = [m for m in book["markets"] if m.get("key") == "player_shots_on_goal"]
        goal_nodes = [m for m in book["markets"] if m.get("key") == "player_goals"]
        if len(shot_nodes) != 1 or len(goal_nodes) != 1:
            reason = "missing_or_duplicate_main_shot_or_goal_market"
            attrition[reason] += 1; event_status.append({**status, "reason": reason}); continue
        shot, goal = shot_nodes[0], goal_nodes[0]
        # Choose the shot anchor from its own valid pairs, before any goal join.
        shot_choices = {}
        for r in sorted(pairs(shot, "shot", pair_reasons), key=lambda x: (x["player"], abs(x["q_under"] - Fraction(1, 2)), x["line"])):
            if r["player"] in shot_choices:
                pair_reasons["extra_shot_main_line"] += 1
                continue
            shot_choices[r["player"]] = r
        g = matched[0]
        boundary = min(g["start"], *starts[event])
        try:
            su, gu = stamp(shot["last_update"]), stamp(goal["last_update"])
        except (ValueError, KeyError, TypeError):
            reason = "invalid_market_clock"
        else:
            if su != gu:
                reason = "goal_shot_market_clock_mismatch"
            elif not boundary - timedelta(hours=72) <= su < boundary:
                reason = "update_outside_fixed_pregame_window"
        if reason is not None:
            attrition[reason] += 1; event_status.append({**status, "reason": reason}); continue
        goal_pairs = pairs(goal, "goal", pair_reasons)
        before = len(rows)
        for gp in goal_pairs:
            sp = shot_choices.get(gp["player"])
            if sp is None:
                pair_reasons["no_exact_literal_name_shot_anchor"] += 1
                continue
            ids = names.get(norm(gp["player"]), set())
            if len(ids) != 1:
                pair_reasons["unresolved_player_identity"] += 1
                unknown[gp["player"]] += 1
                continue
            row = {"game_id": g["game_id"], "event_id": event, "player_id": next(iter(ids)), "player": gp["player"],
                   "home_team_abbr": g["home_team_abbr"], "away_team_abbr": g["away_team_abbr"],
                   "entry": su.isoformat(), "shot_market_update": shot["last_update"], "goal_market_update": goal["last_update"],
                   "provider_start": provider.isoformat(), "independent_start": g["start"].isoformat(), "boundary": boundary.isoformat(),
                   "lead_seconds": (boundary - su).total_seconds(),
                   "period": "early_nov_dec" if boundary < CUT else "later_january",
                   "source_path": str(path.relative_to(ROOT)), "source_sha256": sha(path)}
            for prefix, pair in (("shot", sp), ("goal", gp)):
                for key in ("line", "over_american", "under_american", "over_decimal", "under_decimal", "overround", "q_under"):
                    row[prefix + "_" + key] = float(pair[key])
            rows.append(row)
        status.update(reason="has_qualified_overlap" if len(rows) > before else "no_qualified_overlap", pairs=len(rows) - before)
        event_status.append(status)
    # The pinned archive contains one event response per fixture; never hide a duplicate.
    assert len({(r["game_id"], r["player_id"]) for r in rows}) == len(rows)
    rows.sort(key=lambda r: (r["entry"], r["game_id"], r["player_id"]))
    periods = {p: summary([r for r in rows if r["period"] == p]) for p in ("early_nov_dec", "later_january")}
    gate = all(v["games"] >= 100 for v in periods.values())
    # Print the bounded coverage result before report formatting.
    print(json.dumps({"all": summary(rows), "periods": periods, "both_100_game_gates_pass": gate,
                      "event_exclusions": dict(attrition), "pair_exclusions": dict(pair_reasons), "unresolved_names": dict(unknown)}, indent=2), flush=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["game_id", "event_id", "player_id", "player"]
    with csvpath.open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(rows)
    details_path.write_text(json.dumps({"event_status": event_status, "raw_source_pins": sources}, indent=2) + "\n")
    report = {"status": "price_coverage_pass" if gate else "insufficient_price_coverage", "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
              "tool": pin(Path(__file__)), "metadata_inputs": [pin(RAW / p) for p in PINS], "source_commit": manifest["source_commit"],
              "raw_files_verified": 285, "event_payloads": len(payloads), "explicit_metadata_columns": {"roster": ROSTER_COLS, "fixture": FIXTURE_COLS},
              "eligible": summary(rows), "periods": periods, "minimum_games_per_period": 100, "both_periods_pass": gate,
              "event_exclusions": dict(attrition), "pair_exclusions": dict(pair_reasons), "unresolved_names": dict(unknown),
              "paired_prices": pin(csvpath), "details": pin(details_path),
              "rules": ["One FD node and one main goal/shot node; exact same literal player; goal line0.5, shot half-line0.5–8.5.",
                        "Exactly one Over and Under; finite legal American odds; both pair overrounds0–15% by rational arithmetic.",
                        "Shot anchor chosen first by distance of normalized Under probability to0.5, then lower line; no goal-informed line choice.",
                        "Goal/shot market timestamps must be equal; within72hours and strictly before earliest provider/independent start.",
                        "Unique ordered-team REG fixture within1day; original debug2024020345 excluded; unchanged unique normalized roster full-name mapping.",
                        "Fixed2025-01-01UTC conservative-start split; require100 distinct games in both periods before history/model work."],
              "sport_histories_or_target_performance_read": False, "previous_model_predictions_read": False, "model_or_return_computed": False, "network_requests": 0,
              "limitations": ["Raw market update is an entry proxy, not a collector receipt, suspension record or accepted fill.",
                             "Retrospective rosters supply identity only; target participation and prequote team membership are not inferred.",
                             "No shooting conversion, shot distribution, power-play exposure, prior role or forecast was estimated.",
                             "Archive outcomes were previously inspected by other studies; this is not an untouched validation sample."]}
    args.report_stem.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(report, indent=2) + "\n")
    md = ["# NHL same-clock shot/goal price feasibility", "",
          f"**{len(rows):,} paired player-games cover {summary(rows)['games']} games.** The fixed100-game gate passes in both periods: **{gate}**. This is a price-only inventory; no shot/goal histories, conversion rates, old model probabilities or outcomes were read.", "",
          "| Conservative-start UTC period | Paired player-games | Games | Players |", "|---|---:|---:|---:|"]
    for period, c in periods.items():
        md.append(f"| {period} | {c['paired_player_games']} | {c['games']} | {c['players']} |")
    md += ["", "All285 pinned raw files and the unchanged roster/fixture metadata hashes pass. Pairing requires one FanDuel node, literal main-goal0.5 and main-shot half-lines0.5–8.5, exact full-name equality, valid American sides and overround0–15% for each pair. Shot-line selection occurs before goal overlap, by nearest normalized balance then lower line. Goal and shot market times must be identical and within72hours before the earlier provider/independent start. Debug game2024020345 and unresolved identities remain excluded.", "",
           f"Event exclusions: `{dict(attrition)}`. Pair exclusions: `{dict(pair_reasons)}`. Unresolved names: `{dict(unknown)}`.", "",
           f"Detailed literal pairs and clocks: `{pin(csvpath)['path']}`, SHA `{sha(csvpath)}`. The [JSON](nhl-shot-goal-overlap-feasibility-2026-09-26.json) pins metadata and the ignored raw event/source ledger.", "",
           "A coverage pass only permits a separate prior-only model declaration; it does not establish shooting-history availability, fair probabilities, execution or an edge. A failure ends the exact clock/scope cohort before performance work. The market clock is an entry proxy, and these inspected archive periods are exploratory."]
    mdp.write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
