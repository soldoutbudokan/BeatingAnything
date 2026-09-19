#!/usr/bin/env python3
"""Inventory a pinned public price export against G11's fixed R1 assignments.

Offline source audit only. Publisher predictions, picks and results are discarded;
unqualified timestamps and unknown settlement rules never become eligible bets.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import csv
from datetime import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from explore_golf_rotation import EDITIONS  # noqa: E402

PIN = "5508f6f35830f09d0b1e0c06abed0b2b489dde04"
EXPORTS = ("alpha-caddie-web/data/matchup_backtest_detail.csv",
           "tracker-pages-test/data/matchup_backtest_detail.csv")
EVENTS = {"004": "Farmers Insurance Open", "005": "AT&T Pebble Beach Pro-Am",
          "493": "The RSM Classic"}
FIELDS = ("event_name", "year", "round", "book", "bet_type", "market", "dg_id",
          "player_name", "opponent_dg_id", "opponent_name", "opponent2_dg_id",
          "opponent2_name", "open_time", "close_time", "p1_open_dec", "p2_open_dec",
          "p3_open_dec", "p1_close_dec", "p2_close_dec", "p3_close_dec", "book_odds_source")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def name_key(value, surname_first=False):
    if surname_first:
        parts = value.split(",")
        if len(parts) != 2 or not all(p.strip() for p in parts):
            return None
        value = parts[1].strip() + " " + parts[0].strip()
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold()
                   if c.isalnum())


def classify(row, names, pair):
    fields = ["player_name", "opponent_name"]
    if row["market"] == "3-balls":
        fields.append("opponent2_name")
    players, unmatched = [], []
    for field in fields:
        matches = names.get(name_key(row[field], surname_first=True), [])
        if len(matches) == 1:
            players.append(matches[0])
        else:
            unmatched.append({"name": row[field], "matches": len(matches)})
    if unmatched:
        status = "unmatched_or_ambiguous"
    elif len({p["pga_player_id"] for p in players}) != len(players):
        status = "duplicate_player"
    elif any(not p["course_id"] for p in players):
        status = "missing_course"
    elif any(p["course_id"] not in pair for p in players):
        status = "outside_declared_pair"
    elif len({p["course_id"] for p in players}) == 1:
        status = "same_course"
    else:
        status = "cross_course"
    return {"classification": status, "assignments": players, "unmatched": unmatched}


def clock_status(value):
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return "missing_or_invalid"
    return "offset_aware" if stamp.utcoffset() is not None else "timezone_missing"


def verified(path, suffix=".meta.json"):
    raw = path.read_bytes()
    meta = json.loads(path.with_name(path.name + suffix).read_text())
    if digest(raw) != meta["sha256"] or len(raw) != meta.get("bytes", len(raw)):
        raise ValueError(f"Hash/size mismatch: {path}")
    if "expected_git_blob" in meta:
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if blob != meta["expected_git_blob"]:
            raise ValueError(f"Git blob mismatch: {path}")
    return raw, {"path": str(path.relative_to(ROOT)), **meta}


def audit(raw_dir, rotation_dir):
    sources, exports, datasets = [], [], []
    tree_raw, source = verified(raw_dir / "alpha-tree.json")
    sources.append(source)
    tree = json.loads(tree_raw)
    if tree["sha"] != PIN or tree["truncated"]:
        raise ValueError("Unexpected or incomplete repository tree")
    entries = {r["path"]: r for r in tree["tree"]}
    for path in EXPORTS:
        raw, source = verified(raw_dir / "alpha" / path)
        if source["expected_git_blob"] != entries[path]["sha"]:
            raise ValueError("Export differs from pinned repository tree")
        sources.append(source)
        reader = csv.DictReader(io.StringIO(raw.decode()))
        missing = set(FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing price columns: {missing}")
        rows = [{f: r[f] for f in FIELDS} for r in reader]
        fd = [r for r in rows if r["book"] == "fanduel"]
        keys = {tuple(r[f] for f in FIELDS) for r in fd}
        datasets.append((fd, keys))
        exports.append({"path": path, "total_rows": len(rows),
                        "book_counts": dict(Counter(r["book"] for r in rows)),
                        "fanduel_market_counts": dict(Counter(r["market"] for r in fd)),
                        "fanduel_year_counts": dict(sorted(Counter(r["year"] for r in fd).items())),
                        "fanduel_duplicate_price_rows": len(fd) - len(keys),
                        "open_clock_status": dict(Counter(clock_status(r["open_time"]) for r in fd)),
                        "close_clock_status": dict(Counter(clock_status(r["close_time"]) for r in fd))})
    first, second = datasets
    # One copy per identical price record; never select a better price across files.
    rows = [dict(zip(FIELDS, key)) for key in sorted(first[1] | second[1])]
    targets, editions, unmatched = [], [], Counter()
    for ident, _, hard, easy in EDITIONS:
        raw, source = verified(rotation_dir / f"{ident}-tee.json", ".capture.json")
        sources.append(source)
        wire = json.loads(raw)["data"]["teeTimesCompressedV2"]
        payload = json.loads(gzip.decompress(base64.b64decode(wire["payload"], validate=True)))
        if payload["id"] != ident:
            raise ValueError("Official tournament ID mismatch")
        rounds = [r for r in payload["rounds"] if r["roundInt"] == 1]
        if len(rounds) != 1:
            raise ValueError("Ambiguous official R1")
        names, seen = defaultdict(list), set()
        for group in rounds[0]["groups"]:
            for p in group["players"]:
                if p["id"] in seen:
                    raise ValueError("Duplicate official player assignment")
                seen.add(p["id"])
                names[name_key(p["displayName"])].append({
                    "pga_player_id": p["id"], "name": p["displayName"],
                    "course_id": group.get("courseId"), "group_number": group.get("groupNumber"),
                    "tee_time_epoch_ms": group.get("teeTime")})
        selected = [r for r in rows if r["event_name"] == EVENTS[ident[-3:]]
                    and r["year"] == ident[1:5] and r["round"] == "1"]
        counts = Counter()
        for r in selected:
            context = classify(r, names, (hard, easy))
            counts[r["market"] + "/" + context["classification"]] += 1
            unmatched.update(u["name"] for u in context["unmatched"])
            targets.append({**r, "pga_tournament_id": ident, **context,
                            "backtest_eligible": False})
        editions.append({"pga_tournament_id": ident, "event_name": EVENTS[ident[-3:]],
                         "year": ident[1:5], "counts": dict(sorted(counts.items()))})
    result = {"scope": "source inventory only; no predictions, outcomes, ROI or eligibility inferred",
              "repository": "https://github.com/jriordan55/alpha-caddie", "commit": PIN,
              "sources": sources, "exports": exports,
              "fanduel_distinct_price_records": len(rows),
              "first_export_only": len(first[1] - second[1]),
              "second_export_only": len(second[1] - first[1]),
              "target_rows": len(targets), "editions": editions,
              "target_classifications": dict(Counter(r["classification"] for r in targets)),
              "unmatched_names": dict(sorted(unmatched.items())),
              "eligible_g11_bets": 0,
              "limitations": ["Third-party export; original DataGolf response not retained in repository.",
                  "Publisher export filters graded outcomes and available model estimates; incomplete market universe.",
                  "Exporter can replace missing close_time with open_time; timestamps lack timezone.",
                  "No original quote receipt/update clocks, event IDs, tie_rule, WD terms, jurisdiction or score convention.",
                  "Historical official tee assignments were acquired retrospectively.",
                  "No verified cross-course offer in matched fixed-cohort rows; unmatched rows remain unresolved.",
                  "Repository license is unspecified; downloaded publisher data remain ignored."]}
    for path in ("historical_odds.R", ".gitignore", "data/odds.csv",
                 "alpha-caddie-web/scripts/export-matchup-backtest-csv.mjs",
                 "alpha-caddie-web/scripts/odds-csv-props.mjs"):
        raw, source = verified(raw_dir / "alpha" / path)
        if source["expected_git_blob"] != entries[path]["sha"]:
            raise ValueError("Context source differs from pinned tree")
        sources.append(source)
        if path == "data/odds.csv":
            other = list(csv.DictReader(io.StringIO(raw.decode())))
            result["separate_odds_csv"] = {
                "rows": len(other), "bookmaker_named_by_publisher_parser": "Hard Rock",
                "bookmaker_column_present": False, "quote_timestamp_columns_present": False,
                "target_tournament_score_rows": sum(
                    any(s in r["COMPETITION"].lower() for s in ("farmers", "pebble", "rsm"))
                    and r["MARKET_TYPE"] in ("GOLF:FT:CTSTR", "GOLF:P:ROUND1OUSCORE") for r in other)}
    for path in ("alpha-repository.json", "alpha-raw-matchups-history.json"):
        raw, source = verified(raw_dir / path)
        sources.append(source)
        value = json.loads(raw)
        if path == "alpha-repository.json":
            result["repository_license"] = value.get("license")
        else:
            result["raw_matchups_file_visible_history_entries"] = len(value)
    return result, targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw/golf-historical-price-search-2026-09-19")
    parser.add_argument("--rotation-dir", type=Path, default=ROOT / "data/raw/golf-rotation")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/golf-historical-price-audit-2026-09-19.json")
    args = parser.parse_args()
    result, targets = audit(args.raw_dir, args.rotation_dir)
    derived = args.raw_dir / "g11-price-assignment-inventory.json"
    data = (json.dumps(targets, indent=2) + "\n").encode()
    derived.write_bytes(data)
    result["derived_inventory"] = {"path": str(derived.relative_to(ROOT)), "sha256": digest(data), "rows": len(targets)}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ["fanduel_distinct_price_records", "target_rows", "target_classifications", "eligible_g11_bets"]}, indent=2))


if __name__ == "__main__":
    main()
