#!/usr/bin/env python3
"""Build the canonical Cricsheet tables and the ingest validation report.

flock <scratchpad>/cricket-heavy.lock .venv/bin/python tools/build_cricket_tables.py [--workers 3] [--limit N]
Reads data/raw/cricsheet/all_json.zip (streamed) and people.csv. Writes data/processed/cricket/{balls,
matches,innings,events,super_overs,player_innings,people_index}.parquet and
reports/cricket-ingest-validation.json. The full build takes a few minutes with 3 workers and peaks at
about 4 GB in the main process, so it runs under the shared heavy-job lock. Competition, rules, team,
home and weather columns are added later by the enrichment step (see beating/cricket/ingest.py).
"""
# %% setup
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.cricket import ingest as ig  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--workers", type=int, default=3)
parser.add_argument("--limit", type=int, default=None, help="parse only the first N matches (by match_id)")
parser.add_argument("--out", type=Path, default=ig.OUT_DIR)
parser.add_argument("--report", type=Path, default=ig.REPORT_PATH)
args, _ = parser.parse_known_args()
timing, t0 = {}, time.time()


def lap(name, start):
    timing[name] = round(time.time() - start, 1)
    print(f"{name}: {timing[name]} s, memory {ig._rss_mb()}", flush=True)


# %% pass 1: people index from the info blocks
start = time.time()
people = ig.scan_people(ig.CRICSHEET_ZIP)
lap("people_s", start)
print(len(people), "people")

# %% pass 2: parse every match (forked workers, at most 3)
start = time.time()
t = ig.parse_zip(ig.CRICSHEET_ZIP, people, workers=args.workers, limit=args.limit)
lap("parse_s", start)
print(len(t["matches"]), "matches", len(t["balls"]), "deliveries", len(t["failures"]), "failures")

# %% whole-table steps: team names, player context, overturned-kind imputation
start = time.time()
ig.enrich(t)
lap("enrich_s", start)

# %% write parquet
start = time.time()
sizes = ig.write_all(t, args.out)
lap("write_s", start)
print(json.dumps(sizes))

# %% validation report
start = time.time()
report = ig.validate(t)
lap("validate_s", start)
timing["total_s"] = round(time.time() - t0, 1)
report["build"] = dict(timing=timing, memory=ig._rss_mb(), tables=sizes, workers=args.workers, limit=args.limit,
                       balls_in_memory_mb=round(t["balls"].memory_usage(deep=False).sum() / 2 ** 20, 1))
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=1, default=str))
print(json.dumps(report["build"], indent=1))
