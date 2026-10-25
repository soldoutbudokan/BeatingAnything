#!/usr/bin/env python3
"""Build the enriched cricket tables, the frozen resource table and the enrichment validation report.

flock <scratchpad>/cricket-heavy.lock .venv/bin/python tools/build_cricket_enriched.py [--skip-resource]
Reads data/processed/cricket/{balls,matches,innings,match_teams,players,weather_match_day}.parquet and
config/cricket-{rules,venues}.csv|json. Writes data/processed/cricket/{balls,matches}_enriched.parquet,
data/derived/cricket/resource_table.json and reports/cricket-enrich-validation.json. About two minutes;
the main process peaks near 2.5 GB and the load check (a subprocess reading the whole enriched ball table)
near 3 GB, so it runs under the shared heavy-job lock. See beating/cricket/enrich.py and resource.py.
"""
# %% setup
import argparse
import json
from pathlib import Path
import resource as rs
import subprocess
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.cricket import enrich as E, resource as RT, venues as V  # noqa: E402
from beating.cricket.ingest import read_table  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--skip-resource", action="store_true", help="keep the existing resource table")
parser.add_argument("--report", type=Path, default=E.REPORT_PATH)
args, _ = parser.parse_known_args()
timing, t0 = {}, time.time()


def lap(name, start):
    timing[name] = round(time.time() - start, 1)
    print(f"{name}: {timing[name]} s, peak {rs.getrusage(rs.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB", flush=True)


# %% small tables
start = time.time()
matches, innings = read_table("matches"), read_table("innings")
match_teams, players = pd.read_parquet(E.MATCH_TEAMS), read_table("players")
venues, wx = V.load_venues(), pd.read_parquet(E.WEATHER_DAYS)
lap("load_small_s", start)

# %% ball inputs (numpy, dictionary columns as codes)
start = time.time()
b, levels, n_rows = E.load_inputs()
key = b["match_id"].astype(np.int64) * 8 + b["innings"]
assert (np.diff(key) >= 0).all(), "ball table must be sorted by match_id, innings"
del key
reviews = pd.Series(b["match_id"][b["review_by"] >= 0]).value_counts()
lap("load_balls_s", start)

# %% match-level enrichment
start = time.time()
m, full = E.match_table(matches, innings, match_teams, venues, reviews)
days = E.played_days(m, wx)
lap("matches_s", start)

# %% ball-level enrichment
start = time.time()
new, lv = E.ball_columns(b, levels, m, full, innings, players, days)
lap("balls_s", start)

# %% write
start = time.time()
sizes = {"matches_enriched": E.write_matches(m), "balls_enriched": E.write_balls(new, lv)}
lap("write_s", start)
print(json.dumps(sizes))

# %% resource table (plan 7.6), frozen at 2023-01-01
start = time.time()
if args.skip_resource:
    res_report = json.loads(args.report.read_text()).get("resource") if args.report.exists() else None
else:
    _, res_report = RT.build()
lap("resource_s", start)

# %% validation
start = time.time()
report = E.validate(b, new, lv, m)
report["resource"] = res_report
lap("validate_s", start)
new_cols = [c for c in new if not c.startswith("_")]
del b, new

# %% load check: the whole enriched ball table in a fresh process
start = time.time()
code = ("import json; from beating.cricket.ingest import read_table; "
        "b = read_table('balls_enriched'); "
        "print(json.dumps({'rows': len(b), 'columns': b.shape[1], "
        "'frame_mb': round(b.memory_usage(deep=True).sum() / 2**20), "
        "'peak_rss_mb': [round(int(l.split()[1]) / 1024) for l in open('/proc/self/status') "
        "if l.startswith('VmHWM')][0]}))")
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                     env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"})
load = json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 else {"error": out.stderr[-2000:]}
lap("load_check_s", start)
print(json.dumps(load))

# %% report
timing["total_s"] = round(time.time() - t0, 1)
report["build"] = dict(timing=timing, tables=sizes, load_check=load,
                       peak_rss_mb=round(rs.getrusage(rs.RUSAGE_SELF).ru_maxrss / 1024),
                       new_ball_columns=new_cols)
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=1, default=str))
print(json.dumps(report["build"], indent=1))
