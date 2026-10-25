#!/usr/bin/env python3
"""Acquire NOAA ISD-lite and GSOD station-years for every Cricsheet match and build the weather tables.

PYTHONPATH=. flock <scratchpad>/cricket-heavy.lock .venv/bin/python tools/acquire_cricket_weather.py
Streams data/raw/cricsheet/all_json.zip, ranks stations per venue-year with beating/cricket/venues.py,
fetches station-years in rounds (first candidate, then alternates only where needed; ISD-lite first,
GSOD where ISD-lite precipitation or temperature is missing) into data/raw/noaa/{isd-lite,gsod}/{YYYY}/
(cached; 404s recorded in missing.txt), then writes data/processed/cricket/weather_match_day.parquet,
weather_venue_day.parquet, data/derived/cricket/weather_match.csv.gz, docs/cricket/data/venue_climate.json
and reports/cricket-weather-coverage.json. Method and limits: beating/cricket/weather.py. A full run from
an empty cache downloads about 1 GB and takes roughly half an hour; from a warm cache a few minutes.
"""
# %% setup
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from beating.cricket import venues as V  # noqa: E402
from beating.cricket import weather as W  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--every", type=int, default=1, help="use every N-th match (development slices)")
parser.add_argument("--limit", type=int, default=None, help="use only the first N matches by match_id")
parser.add_argument("--workers", type=int, default=4, help="concurrent downloads (at most 4)")
parser.add_argument("--no-download", action="store_true", help="use only the cache")
parser.add_argument("--climate-from", type=int, default=W.CLIMATE_FROM)
parser.add_argument("--out-dir", type=Path, default=None, help="write outputs here instead of their homes")
args, _ = parser.parse_known_args()
workers = max(1, min(args.workers, 4))
t0, timing, downloads = time.time(), {}, {}


def lap(name):
    timing[name] = round(time.time() - t0, 1)
    print(f"[{timing[name]:7.1f} s] {name}", flush=True)


def out_path(p: Path) -> Path:
    return p if args.out_dir is None else args.out_dir / p.name


# %% matches and scheduled days
matches = W.scan_matches(limit=args.limit)
matches = matches.iloc[::args.every].reset_index(drop=True)
days = W.match_days(matches).merge(matches[["match_id", "venue_id"]], on="match_id")
venues = V.load_venues()
isd_hist = V.load_isd_history()
station_years = V.load_station_years()
end = V.isd_data_end(isd_hist)
listed = W.listed_station_years()
lap(f"{len(matches)} matches, {len(days)} match days, data end {end.date()}")

# %% venue-years and candidate stations
climate_venues = set(matches.venue_id[matches.start_date >= f"{args.climate_from}-01-01"].dropna())
plan = W.plan_venue_years(days, venues, end, isd_hist, station_years, listed, climate_venues, args.climate_from)
n_c = Counter(len(p["cands"]) for p in plan.values())
lap(f"{len(plan)} venue-years ({sum(p['climate'] for p in plan.values())} climatology), candidates {dict(n_c)}")

# %% ISD-lite rounds: first candidate everywhere, alternates where a field is still missing
store = W.StationStore()
pending = set(plan)
for k in range(W.N_CANDIDATES):
    jobs, pending = W.round_jobs(plan, store, "isd", k, pending, listed)
    c = Counter() if args.no_download else W.fetch(jobs, W.ISD_LITE_DIR, workers)
    downloads[f"isd_lite_round{k + 1}"] = dict(venue_years=len(pending), jobs=len(set(jobs)), **c)
    store.refresh()
    lap(f"ISD-lite round {k + 1}: {downloads[f'isd_lite_round{k + 1}']}")

# %% GSOD rounds: where ISD-lite precipitation (or temperature) is missing
pending = set(plan)
for k in range(W.N_CANDIDATES):
    jobs, pending = W.round_jobs(plan, store, "gsod", k, pending, listed)
    c = Counter() if args.no_download else W.fetch(jobs, W.GSOD_DIR, workers)
    downloads[f"gsod_round{k + 1}"] = dict(venue_years=len(pending), jobs=len(set(jobs)), **c)
    store.refresh()
    lap(f"GSOD round {k + 1}: {downloads[f'gsod_round{k + 1}']}")

# %% venue-days and match-days
vdays = W.venue_days(plan, store)
rows = W.match_day_rows(days, vdays, venues)
summary = W.match_summary(rows, matches)
lap(f"{len(vdays)} venue-days, {len(rows)} match-day rows")

# %% write tables
for p in (W.MATCH_DAY_PATH, W.MATCH_PATH, W.CLIMATE_PATH, W.REPORT_PATH):
    out_path(p).parent.mkdir(parents=True, exist_ok=True)
day_cols = ["match_id", "day", "date", "scheduled", "played", "venue_id"] + \
    [c for c in W.DAY_COLS if c in rows.columns]
rows[day_cols].to_parquet(out_path(W.MATCH_DAY_PATH), index=False)
vdays.to_parquet(out_path(W.VENUE_DAY_PATH), index=False)
summary.to_csv(out_path(W.MATCH_PATH), index=False, compression="gzip")

# %% climatology for the page
recent = set(matches.venue_id[matches.start_date >= "2015-01-01"].dropna())
clim = W.climatology(vdays[vdays.climate_year], recent)
meta = dict(version=1, generated=time.strftime("%Y-%m-%d"), isd_data_end=str(end.date()),
            years=[args.climate_from, int(end.year)], months="arrays index 0 = January",
            source="NOAA ISD-lite hourly (10:00-22:00 local; evening 18:00-23:00) and GSOD daily via "
                   "beating/cricket/weather.py",
            fields=dict(temp_c="mean air temperature, C", rh="mean relative humidity, %",
                        dew_depression_evening="mean temperature minus dew point 18:00-23:00, C",
                        cloud_oktas="mean total cloud, oktas", rain_day_freq="share of days with >= 1 mm "
                        "(rain flag where the amount is unknown)", precip_mm_rain_day="mean mm on days >= 1 mm",
                        n="days with temperature", n_precip="days with a wet/dry value"))
cj = W.climate_json(clim, venues, meta)
out_path(W.CLIMATE_PATH).write_text(json.dumps(cj, separators=(",", ":"), allow_nan=False) + "\n")
lap(f"climatology: {len(cj['venues'])} venues, {out_path(W.CLIMATE_PATH).stat().st_size // 1000} kB")

# %% coverage report and sanity checks
report = W.coverage_report(matches, rows, summary, venues, end)
lags = pd.DataFrame.from_dict(store.lags, orient="index")
bad_isd = sum(int(f.bad.sum()) for _, f in store._isd.values() if f is not None)
n_isd = sum(len(f) for _, f in store._isd.values() if f is not None)
bad_gsod = sum(int(g.g_bad.sum()) for _, g in store._gsod.values() if g is not None and "g_bad" in g)
sched = rows[rows.scheduled & rows.date.le(end)]
report |= dict(
    generated=time.strftime("%Y-%m-%d %H:%M"), slice=dict(every=args.every, limit=args.limit),
    venue_years=len(plan), climatology_venue_years=sum(p["climate"] for p in plan.values()),
    files_on_disk=dict(isd_lite=sum(len(v) for v in store.files["isd"].values()),
                       gsod=sum(len(v) for v in store.files["gsod"].values()),
                       isd_lite_404=len(W.read_missing(W.ISD_LITE_DIR)), gsod_404=len(W.read_missing(W.GSOD_DIR))),
    downloads=downloads,
    quality=dict(isd_station_days=n_isd, isd_station_days_flagged_dropped=bad_isd,
                 gsod_station_days_flagged_dropped=bad_gsod,
                 rule="station-day mean temperature outside -10..50 C or mean RH > 100.5% (hourly gross limits "
                      "first: T -40..60 C, Td <= T + 1 C, SLP 900..1080 hPa, wind <= 60 m/s)"),
    gsod_lag=dict(stations=int(len(lags)), lag1=int(lags.lag.sum()) if len(lags) else 0,
                  lag1_by_country=(lags[lags.lag.eq(1)].index.map(
                      isd_hist.set_index("station").ctry).value_counts().to_dict() if len(lags) else {}),
                  lag0_with_g_reports=int(((lags.lag == 0) & (lags.n >= W.LAG_MIN_N)).sum()) if len(lags) else 0),
    venue_climate=dict(venues=len(cj["venues"]), years=meta["years"]),
    sanity=W.sanity_checks(summary, matches, clim if len(clim) else W.climatology(vdays), venues),
    timing_s=timing,
)
out_path(W.REPORT_PATH).write_text(json.dumps(W.clean_json(report), indent=1, default=str, allow_nan=False) + "\n")
lap("done")
print(json.dumps({k: report[k] for k in ("match_share_with_weather", "day_source", "precip_source",
                                          "station_distance_km", "quality")}, indent=1, default=str))
