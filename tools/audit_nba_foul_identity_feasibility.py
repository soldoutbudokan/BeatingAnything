#!/usr/bin/env python3
"""Identity-only feasibility for a proposed NBA foul-risk study; no performance reads."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "data/raw/oddspapi-first-basket-audit-2026-09-19/player_box_2026.parquet"
BOX_META = Path(str(BOX) + ".meta.json")
RELEASE = BOX.with_name("espn-nba-player-box-release.json")
PRICES = ROOT / "data/raw/nba-announced-absence-2026-09-26/prices.json"
DEFAULT_OUT = ROOT / "reports/nba-foul-risk-identity-feasibility-2026-09-26"
BOX_SHA = "29a29dc9efd055a93e069a0382ac830d98a13274bee655beba69d95cff099713"
PRICE_SHA = "f44b4d42fc168e434776a7fd89a2cc9bd09bd470adb13189de7b4270ac048372"
IDENTITY_COLUMNS = ["athlete_id", "athlete_display_name"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path), "bytes": path.stat().st_size}


def normalize(value):
    # Accents/punctuation/whitespace only; keep Jr/Sr/II/III/IV and every other word.
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", no_accents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-stem", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    outputs = [args.output_stem.with_suffix(ext) for ext in (".json", ".md")]
    for p in outputs:
        if p.exists():
            raise SystemExit(f"Refusing to overwrite {p}")
    assert digest(BOX) == BOX_SHA
    assert digest(PRICES) == PRICE_SHA
    metadata = json.loads(BOX_META.read_text())
    release = json.loads(RELEASE.read_text())
    asset = next(r for r in release["assets"] if r["name"] == BOX.name)
    assert metadata["digest"] == asset["digest"] == "sha256:" + BOX_SHA
    assert metadata["size"] == asset["size"] == BOX.stat().st_size
    parquet = pq.ParquetFile(BOX)
    by_name, spellings, names_by_id = defaultdict(set), defaultdict(set), defaultdict(set)
    invalid_identity_rows = 0
    # Only these two columns are materialized; no game, participation or statistic value.
    for r in pq.read_table(BOX, columns=IDENTITY_COLUMNS).to_pylist():
        name, identifier = r["athlete_display_name"], r["athlete_id"]
        if not isinstance(name, str) or not name.strip() or identifier is None or not normalize(name):
            invalid_identity_rows += 1
            continue
        identifier = str(identifier)
        if identifier in ("", "nan", "None"):
            invalid_identity_rows += 1
            continue
        key = normalize(name)
        by_name[key].add(identifier)
        spellings[key].add(name)
        names_by_id[identifier].add(name)
    frozen = json.loads(PRICES.read_text())
    events = frozen["events"]
    assert len(events) == 666
    assert sum(len(r["preliminary_pairs"]) for r in events) == 8286
    offered = defaultdict(lambda: {"pairs": 0, "events": set(), "periods": Counter()})
    counts = Counter()
    period_counts = defaultdict(Counter)
    event_rows = []
    boundary = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for event in events:
        entry = datetime.fromisoformat(event["source_snapshot_utc"].replace("Z", "+00:00"))
        period = "calibration" if entry < boundary else "evaluation"
        c = Counter()
        ids = set()
        for pair in event["preliminary_pairs"]:
            name = pair["player"]
            candidates = by_name.get(normalize(name), set())
            status = "unique" if len(candidates) == 1 else "unknown" if not candidates else "ambiguous"
            c[status] += 1
            counts[status + "_pairs"] += 1
            period_counts[period][status + "_pairs"] += 1
            offered[name]["pairs"] += 1
            offered[name]["events"].add(event["event_id"])
            offered[name]["periods"][period] += 1
            if status == "unique":
                ids.update(candidates)
        counts["events_with_any_unique_pair"] += int(c["unique"] > 0)
        counts["events_with_all_pairs_unique"] += int(c["unknown"] + c["ambiguous"] == 0)
        period_counts[period]["events"] += 1
        period_counts[period]["events_with_all_pairs_unique"] += int(c["unknown"] + c["ambiguous"] == 0)
        event_rows.append({"event_id": event["event_id"], "nba_game_id": event["nba_game_id"],
                           "espn_game_id": event["espn_game_id"], "period": period,
                           "unique_pairs": c["unique"], "unknown_pairs": c["unknown"],
                           "ambiguous_pairs": c["ambiguous"], "unique_athlete_ids": len(ids)})
    offered_rows = []
    for name, data in sorted(offered.items()):
        key = normalize(name)
        candidates = sorted(by_name.get(key, set()))
        offered_rows.append({"offered_name": name, "normalized_name": key,
                             "status": "unique" if len(candidates) == 1 else "unknown" if not candidates else "ambiguous",
                             "candidate_athlete_ids": candidates, "source_display_names": sorted(spellings.get(key, set())),
                             "paired_offer_count": data["pairs"], "distinct_events": len(data["events"]),
                             "pair_counts_by_period": dict(data["periods"])})
    counts.update({"events": len(events), "paired_offers": 8286, "distinct_offered_names": len(offered_rows),
                   "distinct_uniquely_mapped_athlete_ids": len({r["candidate_athlete_ids"][0] for r in offered_rows if r["status"] == "unique"})})
    for status in ("unique", "unknown", "ambiguous"):
        counts[status + "_offered_names"] = sum(r["status"] == status for r in offered_rows)
        counts.setdefault(status + "_pairs", 0)
        for period in period_counts.values():
            period.setdefault(status + "_pairs", 0)
    unresolved = [r for r in offered_rows if r["status"] != "unique"]
    payload = {"status": "identity_only_inventory_complete", "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
               "tool": pin(Path(__file__)), "inputs": [pin(p) for p in (PRICES, BOX, BOX_META, RELEASE)],
               "source_asset": {k: asset.get(k) for k in ("id", "name", "size", "digest", "created_at", "updated_at", "browser_download_url")},
               "schema_columns_only": parquet.schema.names, "materialized_box_columns": IDENTITY_COLUMNS,
               "source_identity_universe": {"parquet_footer_rows": parquet.metadata.num_rows,
                   "distinct_athlete_ids": len(names_by_id), "distinct_normalized_names": len(by_name),
                   "invalid_identity_rows": invalid_identity_rows,
                   "ambiguous_normalized_names": {k: sorted(v) for k, v in by_name.items() if len(v) > 1}},
               "normalization": "Unicode NFKD/casefold, remove combining accents and non-alphanumeric punctuation/whitespace; all suffix words retained; no fuzzy aliases, suffix removal, short-name matching or target-appearance requirement.",
               "summary": dict(counts), "by_period": dict(period_counts), "offered_name_mapping": offered_rows,
               "unresolved_offered_names": unresolved, "by_event": event_rows,
               "metadata_fields_for_future_prior_join": ["game_id", "season", "season_type", "game_date", "game_date_time", "athlete_id", "athlete_display_name", "team_id", "team_abbreviation", "home_away", "opponent_team_id"],
               "future_stat_fields_schema_present_not_materialized": ["minutes", "fouls", "points"],
               "target_appearance_required": False, "performance_values_read": False,
               "role_history_counts_computed": False, "network_requests": 0,
               "limitations": ["A retrospective identity universe supplies names/IDs only; it does not establish prequote club, role, availability or contemporaneous name coverage.",
                   "The retained file uses ESPN athlete/game IDs. Publisher NBA game IDs must retain the independently matched ESPN fixture mapping; no official NBA person-ID equivalence is inferred.",
                   "All unknown/ambiguous offered names remain unresolved. A plausible spelling or omitted suffix is not authorization for an alias.",
                   "A unique identity match does not prove adequate prior positive-minute history, foul observations, sample size for a trigger or any mispricing. No performance or role calculation is made here."]}
    args.output_stem.parent.mkdir(parents=True, exist_ok=True)
    outputs[0].write_text(json.dumps(payload, indent=2) + "\n")
    md = ["# NBA foul-risk proposal: identity-only feasibility", "",
          f"**{counts['unique_pairs']:,} of 8,286 paired offers map uniquely** across the frozen 666-game price universe. There are {counts['unknown_pairs']} unmatched and {counts['ambiguous_pairs']} ambiguous offers. All {counts['events_with_any_unique_pair']} events retain at least one unique name; {counts['events_with_all_pairs_unique']} have every offered name uniquely mapped.", "",
          f"The {counts['distinct_offered_names']} literal offered names contain {counts['unique_offered_names']} unique matches, {counts['unknown_offered_names']} unmatched names and {counts['ambiguous_offered_names']} ambiguous names. They map to {counts['distinct_uniquely_mapped_athlete_ids']} distinct ESPN athlete IDs. Normalization removes accents, punctuation and whitespace while retaining all suffixes. No fuzzy or short-name aliases were introduced.", "",
          "Only `athlete_id` and `athlete_display_name` were materialized from the player parquet. The entire retained identity universe was used; a target-game appearance was never required. The source hash matches both metadata and the retained GitHub asset digest. No minutes, fouls, points, participation flags, roles or history counts were read or computed.", "",
          "| Period | Events | Unique pairs | Unknown pairs | Ambiguous pairs |", "|---|---:|---:|---:|---:|"]
    for period, c in sorted(period_counts.items()):
        md.append(f"| {period} | {c['events']} | {c['unique_pairs']} | {c['unknown_pairs']} | {c['ambiguous_pairs']} |")
    md += ["", "Unresolved literal names:", ""]
    for r in unresolved:
        md.append(f"- {r['offered_name']}: {r['status']}, {r['paired_offer_count']} pairs / {r['distinct_events']} events; candidate IDs {r['candidate_athlete_ids']}.")
    if not unresolved:
        md.append("None.")
    md += ["", "The schema also contains stable game/team/athlete IDs, game date/time, season/type, ordered side and opponent IDs for a later declared prior-history join. Those fields were inspected as schema names, not used to infer current team membership. `minutes`, `fouls` and `points` exist in the schema but their values remain unread.", "",
           "This establishes identity coverage only. Retrospective names do not prove prequote membership or adequate history, and no foul-risk exposure, effect or forecasting model is established. Source pins, every offered-name mapping and per-event counts are in the [JSON](nba-foul-risk-identity-feasibility-2026-09-26.json). The isolated tool refuses to overwrite outputs."]
    outputs[1].write_text("\n".join(md) + "\n")
    print(json.dumps({"summary": dict(counts), "by_period": dict(period_counts), "unresolved": unresolved}, indent=2))


if __name__ == "__main__":
    main()
