#!/usr/bin/env python3
"""Normalized multi-book anytime-scorer screen of FanDuel prices; never reads target outcomes.

Implements docs/hypotheses/hockey-anytime-scorer-normalized-consensus.md. The only
sporting values read are 2023-24 skater goals, used once for the prior constant T.
"""
from __future__ import annotations

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
import statistics
import unicodedata

from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nhl-shot-archive-2026-09-26"
OUTDIR = ROOT / "data/raw/nhl-anytime-consensus-2026-09-28"
REPORT = ROOT / "reports/nhl-anytime-consensus-freeze-2026-09-28"
CARD = ROOT / "docs/hypotheses/hockey-anytime-scorer-normalized-consensus.md"
PINS = {
    "manifest.json": "9b43fc27fe396a7b37dd07af3e7f01ab56acb209578b2c5b0defb2bdfbeeed2f",
    "outcomes/rosters_2024.csv": "0e70a12579b25af0532d00a0cf8bb5fda7d9eb33a23d76234ca26f2fff4ca4ba",
    "outcomes/rosters_2025.csv": "cff04536329e7a7f3cdf9034786226e6644a7d222486eb70d4a799d12c1f80ba",
    "outcomes/schedule_2025_metadata.csv": "320643ed83428e28671c7508c667026ab65c46b85bcf312d173c2b025d98e855",
    "powerplay-feature-audit/schedule_2024_metadata.csv": "59afa78de1b51e0ceb7bda66207896801fc080505a0ace27cc6ed41e6397b588",
    "outcomes/player_box_2024.csv": "889d439dae5b5a2e831496a3a0dcbea4d385883d68d55b70d55a554169ff6e74",
}
SOURCE_COMMIT = "42cf1f81bc302642ddcc9e88ce2e98c1057bc74d"
MARKET = "player_goal_scorer_anytime"
EXCLUDED_REFERENCES = {"fanduel", "ballybet"}
DEBUG_GAME = "2024020345"
CUT = datetime(2025, 1, 1, tzinfo=timezone.utc)
PERIODS = ("early_nov_dec", "later_january")
WINDOW = timedelta(hours=72)
REFERENCE_WINDOW = timedelta(hours=3)
MIN_REFERENCES = 3
ODDS = (1.2, 6.0)
THRESHOLD = .03
HAIRCUT = .98
POWER_BRACKET = (.25, 4.)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}


def norm(value):
    return re.sub("[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower())


def stamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Unzoned clock")
    return parsed.astimezone(timezone.utc)


def decimal(price):
    if not isinstance(price, (int, float)) or isinstance(price, bool) or not math.isfinite(price) or abs(price) < 100:
        raise ValueError("Invalid American price")
    price = Fraction(str(price))
    return 1 + price / 100 if price > 0 else 1 - 100 / price


def seconds(value):
    match = re.fullmatch(r"(\d+):([0-5]\d)", str(value))
    return int(match[1]) * 60 + int(match[2]) if match else None


def integer(value):
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def read_csv(path, columns):
    with (RAW / path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(columns) <= set(reader.fieldnames):
            raise ValueError(f"Unexpected schema: {path}")
        return [{key: row[key] for key in columns} for row in reader]


def prior_constant(exclusions):
    """Mean number of distinct 2023-24 skater goal scorers per completed regular-season game."""
    schedule = read_csv("powerplay-feature-audit/schedule_2024_metadata.csv", ["game_id", "game_type", "game_state"])
    counts = Counter(row["game_id"] for row in schedule)
    completed = {row["game_id"] for row in schedule
                 if counts[row["game_id"]] == 1 and row["game_type"] == "R" and row["game_state"] in ("OFF", "FINAL")}
    scorers = Counter()
    games = set()
    for row in read_csv("outcomes/player_box_2024.csv", ["game_id", "player_id", "position", "toi", "goals"]):
        game = row["game_id"]
        if len(game) != 10 or game[4:6] != "02":
            exclusions["prior:not_type_02"] += 1
        elif game not in completed:
            exclusions["prior:not_completed_regular_schedule"] += 1
        elif row["position"] not in ("C", "L", "R", "D"):
            exclusions["prior:not_skater_position"] += 1
        elif (toi := seconds(row["toi"])) is None or toi <= 0:
            exclusions["prior:nonpositive_ice_time"] += 1
        elif (goals := integer(row["goals"])) is None:
            exclusions["prior:invalid_goals"] += 1
        else:
            games.add(game)
            scorers[game] += goals >= 1
    if not games:
        raise ValueError("Empty prior universe")
    value = sum(scorers[game] for game in games) / len(games)
    return {"season_prefix": "202302", "games": len(games), "distinct_scorers": sum(scorers.values()),
            "mean_distinct_scorers_per_game": value, "source": "outcomes/player_box_2024.csv"}


def ladder(market, reasons, label):
    """Return {description: decimal} or None when the ladder is invalid under the card."""
    prices, seen = {}, Counter()
    for outcome in market.get("outcomes", []):
        if outcome.get("name") != "Yes":
            reasons[f"{label}:outcome_not_yes"] += 1
            continue
        name = outcome.get("description")
        if not isinstance(name, str) or not name.strip():
            reasons[f"{label}:blank_description"] += 1
            continue
        try:
            prices[name] = decimal(outcome.get("price"))
        except ValueError:
            reasons[f"{label}:invalid_american"] += 1
            continue
        seen[name] += 1
    if any(n > 1 for n in seen.values()):
        reasons[f"{label}:repeated_description_ladder_dropped"] += 1
        return None
    return prices or None


def normalize(prices, target, reasons, label):
    raw = {name: 1 / float(value) for name, value in prices.items()}
    total = sum(raw.values())
    proportional = {name: value * target / total for name, value in raw.items()}
    function = lambda k: sum(value ** k for value in raw.values()) - target
    low, high = function(POWER_BRACKET[0]), function(POWER_BRACKET[1])
    if not (math.isfinite(low) and math.isfinite(high)) or low * high > 0:
        reasons[f"{label}:power_root_unbracketed"] += 1
        return None
    k = brentq(function, *POWER_BRACKET, xtol=1e-12, rtol=1e-12, maxiter=500)
    power = {name: value ** k for name, value in raw.items()}
    return {"raw": raw, "total": total, "proportional": proportional, "power": power, "k": k, "players": len(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTDIR)
    parser.add_argument("--report-stem", type=Path, default=REPORT)
    args = parser.parse_args()
    rows_path = args.output_dir / "reference-rows.csv"
    details_path = args.output_dir / "event-status.json"
    json_path, md_path = args.report_stem.with_suffix(".json"), args.report_stem.with_suffix(".md")
    for path in (rows_path, details_path, json_path, md_path):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite {path}")
    for rel, expected in PINS.items():
        if sha(RAW / rel) != expected:
            raise ValueError(f"Pinned input hash mismatch: {rel}")
    exclusions, pair_reasons = Counter(), Counter()
    prior = prior_constant(exclusions)
    target = prior["mean_distinct_scorers_per_game"]
    names = defaultdict(set)
    for year in (2024, 2025):
        for row in read_csv(f"outcomes/rosters_{year}.csv", ["full_name", "player_id"]):
            names[norm(row["full_name"])].add(row["player_id"])
    fixtures = []
    for row in read_csv("outcomes/schedule_2025_metadata.csv",
                        ["game_id", "game_type", "home_team_name", "away_team_name", "game_time", "home_team_abbr", "away_team_abbr"]):
        if row["game_type"] == "R":
            fixtures.append({**row, "home_key": norm(row["home_team_name"]), "away_key": norm(row["away_team_name"]),
                             "start": stamp(row["game_time"])})
    manifest = json.loads((RAW / "manifest.json").read_text())
    assert manifest["source_commit"] == SOURCE_COMMIT and len(manifest["files"]) == 285
    payloads, sources, starts, identities = [], [], defaultdict(set), defaultdict(set)
    for spec in manifest["files"]:
        path = ROOT / spec["path"]
        assert sha(path) == spec["sha256"] and path.stat().st_size == spec["bytes"]
        sources.append({"path": spec["path"], "sha256": spec["sha256"]})
        raw = json.loads(path.read_text())
        if "bookmakers" not in raw:
            exclusions["event:publisher_error_payload"] += 1
            continue
        assert raw["sport_key"] == "icehockey_nhl"
        starts[raw["id"]].add(stamp(raw["commence_time"]))
        identities[raw["id"]].add((norm(raw["home_team"]), norm(raw["away_team"])))
        payloads.append((path, raw))
    rows, event_status, unresolved = [], [], Counter()
    for path, raw in payloads:
        event = raw["id"]
        status = {"event_id": event, "source_path": str(path.relative_to(ROOT))}
        provider = stamp(raw["commence_time"])
        matched = [g for g in fixtures if g["home_key"] == norm(raw["home_team"]) and g["away_key"] == norm(raw["away_team"])
                   and abs((g["start"] - provider).total_seconds()) <= 86400]
        reason = None
        if len(identities[event]) != 1 or not starts[event]:
            reason = "conflicting_identity_or_missing_start"
        elif len(matched) != 1:
            reason = "fixture_unresolved"
        elif matched[0]["game_id"] == DEBUG_GAME:
            reason = "original_debug_game_excluded"
        books = [b for b in raw["bookmakers"] if b.get("key") == "fanduel"]
        if reason is None and len(books) != 1:
            reason = "missing_or_duplicate_fd_node"
        markets = [m for m in books[0].get("markets", []) if m.get("key") == MARKET] if reason is None else []
        if reason is None and len(markets) != 1:
            reason = "missing_or_duplicate_fd_anytime_market"
        if reason is None:
            fixture = matched[0]
            boundary = min(fixture["start"], *starts[event])
            try:
                entry = stamp(markets[0]["last_update"])
            except (KeyError, ValueError, TypeError):
                reason = "invalid_fd_market_clock"
            else:
                if not boundary - WINDOW <= entry < boundary:
                    reason = "fd_update_outside_fixed_pregame_window"
        if reason is None:
            fd_prices = ladder(markets[0], pair_reasons, "fanduel")
            if fd_prices is None:
                reason = "fd_ladder_invalid"
        if reason is None:
            fd_norm = normalize(fd_prices, target, pair_reasons, "fanduel")
            if fd_norm is None:
                reason = "fd_ladder_unnormalizable"
        if reason is not None:
            exclusions[f"event:{reason}"] += 1
            event_status.append({**status, "reason": reason})
            continue
        references = {}
        book_reasons = Counter()
        for book in raw["bookmakers"]:
            key = book.get("key")
            if key in EXCLUDED_REFERENCES:
                continue
            nodes = [m for m in book.get("markets", []) if m.get("key") == MARKET]
            if len(nodes) != 1:
                book_reasons["missing_or_duplicate_market"] += len(nodes) > 1
                continue
            try:
                update = stamp(nodes[0]["last_update"])
            except (KeyError, ValueError, TypeError):
                book_reasons["invalid_clock"] += 1
                continue
            if not (update < boundary and abs((update - entry).total_seconds()) <= REFERENCE_WINDOW.total_seconds()):
                book_reasons["clock_outside_reference_window"] += 1
                continue
            prices = ladder(nodes[0], pair_reasons, "reference")
            if prices is None:
                book_reasons["ladder_invalid"] += 1
                continue
            normalized = normalize(prices, target, pair_reasons, "reference")
            if normalized is None:
                book_reasons["ladder_unnormalizable"] += 1
                continue
            references[key] = normalized
        before = len(rows)
        for name, price in fd_prices.items():
            ids = names.get(norm(name), set())
            if len(ids) != 1:
                pair_reasons["unresolved_player_identity"] += 1
                unresolved[name] += 1
                continue
            listing = {key: value for key, value in references.items() if name in value["raw"]}
            if len(listing) < MIN_REFERENCES:
                pair_reasons["fewer_than_three_literal_references"] += 1
                continue
            fd_decimal = float(price)
            payout = 1 + HAIRCUT * (fd_decimal - 1)
            reference = {method: statistics.median(value[method][name] for value in listing.values())
                         for method in ("proportional", "power")}
            ev = {method: reference[method] * payout - 1 for method in reference}
            score = min(ev.values())
            within = ODDS[0] <= fd_decimal <= ODDS[1]
            rows.append({
                "game_id": fixture["game_id"], "event_id": event, "player_id": next(iter(ids)), "player": name,
                "home_team_abbr": fixture["home_team_abbr"], "away_team_abbr": fixture["away_team_abbr"],
                "entry": entry.isoformat(), "provider_start": provider.isoformat(),
                "independent_start": fixture["start"].isoformat(), "boundary": boundary.isoformat(),
                "lead_seconds": (boundary - entry).total_seconds(),
                "period": PERIODS[0] if boundary < CUT else PERIODS[1],
                "source_path": str(path.relative_to(ROOT)), "source_sha256": sha(path),
                "fd_decimal": fd_decimal, "fd_raw_implied": fd_norm["raw"][name],
                "fd_ladder_players": fd_norm["players"], "fd_ladder_total_implied": fd_norm["total"],
                "fd_power_k": fd_norm["k"], "fd_p_proportional": fd_norm["proportional"][name],
                "fd_p_power": fd_norm["power"][name],
                "reference_books": len(listing), "reference_keys": "|".join(sorted(listing)),
                "reference_total_implied_median": statistics.median(value["total"] for value in listing.values()),
                "p_reference_proportional": reference["proportional"], "p_reference_power": reference["power"],
                "ev_proportional": ev["proportional"], "ev_power": ev["power"], "score": score,
                "within_decimal_range": within, "qualifies": within and score >= THRESHOLD, "selected": False})
        status.update(reason="rows_written" if len(rows) > before else "no_reference_rows", rows=len(rows) - before,
                      reference_books=sorted(references), reference_exclusions=dict(book_reasons))
        event_status.append(status)
    assert len({(r["game_id"], r["player_id"]) for r in rows}) == len(rows), "duplicate game/player row"
    by_game = defaultdict(list)
    for index, row in enumerate(rows):
        if row["qualifies"]:
            by_game[row["game_id"]].append((-row["score"], int(row["player_id"]), row["player"], index))
    for candidates in by_game.values():
        rows[min(candidates)[3]]["selected"] = True
    rows.sort(key=lambda r: (r["entry"], r["game_id"], int(r["player_id"])))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with rows_path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    details_path.write_text(json.dumps({"event_status": event_status}, indent=2) + "\n")

    def summary(group):
        return {"rows": len(group), "games": len({r["game_id"] for r in group}),
                "players": len({r["player_id"] for r in group}),
                "rows_in_decimal_range": sum(r["within_decimal_range"] for r in group),
                "qualifying_rows": sum(r["qualifies"] for r in group),
                "selections": sum(r["selected"] for r in group),
                "best_score": max((r["score"] for r in group), default=None),
                "mean_fd_ladder_total_implied": statistics.mean(r["fd_ladder_total_implied"] for r in group) if group else None,
                "mean_reference_total_implied_median": statistics.mean(r["reference_total_implied_median"] for r in group) if group else None}

    selections = [r for r in rows if r["selected"]]
    periods = {p: summary([r for r in rows if r["period"] == p]) for p in PERIODS}
    status_label = "frozen_before_target_grading" if selections else "closed_zero_selections_no_target_grading"
    report = {
        "status": status_label, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "card": pin(CARD), "tool": pin(Path(__file__)), "metadata_inputs": [pin(RAW / p) for p in PINS],
        "source_commit": SOURCE_COMMIT, "raw_files_verified": len(sources), "event_payloads": len(payloads),
        "prior_constant": prior, "all": summary(rows), "periods": periods,
        "selection_sides": "Yes only; one-sided market", "selected_players": len({r["player_id"] for r in selections}),
        "reference_book_counts": dict(sorted(Counter(r["reference_books"] for r in rows).items())),
        "reference_key_counts": dict(Counter(key for r in rows for key in r["reference_keys"].split("|"))),
        "event_exclusions": dict(sorted(exclusions.items())), "row_exclusions": dict(sorted(pair_reasons.items())),
        "unresolved_names": dict(unresolved), "rows_artifact": pin(rows_path), "event_status": pin(details_path),
        "rules": {"reference_books": "every non-FanDuel node except ballybet", "minimum_references": MIN_REFERENCES,
                  "fd_window_hours": 72, "reference_window_hours": 3, "odds": ODDS, "threshold": THRESHOLD,
                  "haircut": HAIRCUT, "power_bracket": POWER_BRACKET, "score": "min(proportional EV, power EV)",
                  "selection": "one per game: greatest score, ascending NHL ID, lexical name"},
        "sources": sources, "target_outcomes_read": False, "previous_model_predictions_read": False,
        "limitations": ["Price-reference screen in an already inspected archive; no independent forecast or execution claim.",
                        "Ladders normalized as listed; shorter ladders are slightly inflated by construction.",
                        "Market updates are entry proxies, not receipts, suspensions or accepted fills.",
                        "Reference books share platforms and data sources; they are not independent signals."]}
    args.report_stem.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# NHL anytime-scorer normalized consensus: frozen screen", "",
             f"Status: **{status_label}**. Prior constant T = {target:.4f} distinct scorers per game from {prior['games']} completed 2023–24 games. "
             f"{len(rows):,} FanDuel anytime rows across {report['all']['games']} games have at least three literal reference ladders; "
             f"{report['all']['qualifying_rows']} qualify and {len(selections)} are selected, one per game. No target outcome was read.", "",
             "| Period | Rows / games | Qualifying rows | Selections | Best score | FD total implied | Reference total (median) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for period, value in periods.items():
        lines.append(f"| {period} | {value['rows']} / {value['games']} | {value['qualifying_rows']} | {value['selections']} | "
                     f"{value['best_score']:.4f} | {value['mean_fd_ladder_total_implied']:.3f} | {value['mean_reference_total_implied_median']:.3f} |")
    lines += ["", f"Event exclusions: `{dict(sorted(exclusions.items()))}`. Row exclusions: `{dict(sorted(pair_reasons.items()))}`.", "",
              f"Rows: `{report['rows_artifact']['path']}`, SHA-256 `{report['rows_artifact']['sha256']}`. The [JSON](nhl-anytime-consensus-freeze-2026-09-28.json) pins the card, tool, inputs, every raw payload and the outputs.",
              "", "The grader must verify those hashes and refuse zero selections. This is a price-reference screen in an inspected archive, not evidence of independent forecasting skill or executable prices."]
    md_path.write_text("\n".join(lines) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "prior_constant", "all", "periods", "event_exclusions", "row_exclusions", "reference_book_counts")}, indent=2))


if __name__ == "__main__":
    main()
