#!/usr/bin/env python3
"""Acquire NOAA ISD-lite and GSOD station-years for every Cricsheet match day and build the weather tables.

PYTHONPATH=. flock <scratchpad>/cricket-heavy.lock .venv/bin/python tools/acquire_cricket_weather.py
Reads data/processed/cricket/matches.parquet (scheduled days from the rules timeline), ranks stations per
venue-year with beating/cricket/venues.py, fetches station-years in rounds (first candidate, then
alternates only where a match day still lacks a field; ISD-lite first, GSOD where ISD-lite precipitation
or temperature is missing) into data/raw/noaa/{isd-lite,gsod}/{YYYY}/ (cached; 404s recorded in
missing.txt), then writes data/processed/cricket/weather_match_day.parquet,
data/derived/cricket/weather_match.csv.gz, docs/cricket/data/venue_climate.json (climatology from all
match days) and reports/cricket-weather-coverage.json. `--climate-from YEAR` also assembles whole years
since YEAR for venues with a match since then (weather_venue_day.parquet; not used by `climatology`).
Method and limits: beating/cricket/weather.py.
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
parser.add_argument("--climate-from", type=int, default=None, help="also assemble whole years from this year")
parser.add_argument("--out-dir", type=Path, default=None, help="write outputs here instead of their homes")
args, _ = parser.parse_known_args()
workers = max(1, min(args.workers, 4))
t0, timing, downloads = time.time(), {}, {}
CUTOFFS = ["2023-01-01", "2024-01-01", "2024-07-01", "2025-01-01", "2025-07-01", "2026-01-01", "2026-07-01"]


def lap(name):
    timing[name] = round(time.time() - t0, 1)
    print(f"[{timing[name]:7.1f} s] {name}", flush=True)


def out_path(p: Path) -> Path:
    return p if args.out_dir is None else args.out_dir / p.name


# %% matches and scheduled days
matches = W.load_matches().sort_values("match_id").reset_index(drop=True)
matches = matches.iloc[:args.limit].iloc[::args.every].reset_index(drop=True)
days = W.match_days(matches).merge(matches[["match_id", "venue_id"]], on="match_id")
venues = V.load_venues()
isd_hist = V.load_isd_history()
station_years = V.load_station_years()
end = V.isd_data_end(isd_hist)
listed = W.listed_station_years()
lap(f"{len(matches)} matches, {len(days)} match days, data end {end.date()}")

# %% venue-years and candidate stations
climate_venues = set() if args.climate_from is None else \
    set(matches.venue_id[matches.start_date >= f"{args.climate_from}-01-01"].dropna())
plan = W.plan_venue_years(days, venues, end, isd_hist, station_years, listed, climate_venues,
                          args.climate_from or W.CLIMATE_FROM)
n_c = Counter(len(p["cands"]) for p in plan.values())
lap(f"{len(plan)} venue-years ({sum(p['climate'] for p in plan.values())} whole years), candidates {dict(n_c)}")

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
rows = rows[day_cols].sort_values(["match_id", "day"]).reset_index(drop=True)
rows.to_parquet(out_path(W.MATCH_DAY_PATH), index=False)
if climate_venues:
    vdays.to_parquet(out_path(W.VENUE_DAY_PATH), index=False)
summary.to_csv(out_path(W.MATCH_PATH), index=False, compression="gzip")

# %% climatology for the page (all match days) and at the evaluation cutoffs
clim = W.climatology(None, rows, venues)
meta = dict(version=2, generated=time.strftime("%Y-%m-%d"), isd_data_end=str(end.date()),
            months="arrays index 0 = January", shrinkage_days=W.CLIM_K,
            source="NOAA ISD-lite hourly (10:00-22:00 local; evening 18:00-23:00) and GSOD daily on scheduled "
                   "Cricsheet match days, via beating/cricket/weather.py climatology(); venue-months shrunk "
                   "toward country, region and global month values",
            fields=dict(temp_c="mean air temperature, C", rh="mean relative humidity, %",
                        dewpt_c="mean dew point, C", dew_depression_evening="mean temperature minus dew point "
                        "18:00-23:00, C", cloud_oktas="mean total cloud, oktas", wind_ms="mean wind, m/s",
                        precip_mm="mean precipitation per match day, mm", rain_day_freq="share of match days with "
                        ">= 1 mm (rain flag where the amount is unknown)", precip_mm_rain_day="mean mm on days "
                        ">= 1 mm", n="venue-month days with temperature", n_precip="with a wet/dry value",
                        n_cloud="with cloud", level="what the value rests on: venue_month, venue (other months "
                        "plus country seasonality), country, region, global"))
cj = W.climate_json(clim, venues, meta)
out_path(W.CLIMATE_PATH).write_text(json.dumps(W.clean_json(cj), separators=(",", ":"), allow_nan=False) + "\n")
lap(f"climatology: {len(cj['venues'])} venues, {out_path(W.CLIMATE_PATH).stat().st_size // 1000} kB")


def clim_skill(cutoff: str, until: str | None) -> dict:
    """Climatology at the cutoff against observed scheduled match days in [cutoff, until)."""
    c = W.climatology(cutoff, rows, venues)
    obs = W.climate_days(rows)
    obs = obs[(obs.date >= cutoff) & ((obs.date < until) if until else True)]
    j = obs.merge(c.rename(columns=lambda x: x if x in ("venue_id", "month") else f"clim_{x}"),
                  on=["venue_id", "month"], how="left")
    used = W.climate_days(rows, cutoff)
    out = dict(train_days=int(len(used)), train_max_date=str(used.date.max().date()) if len(used) else None,
               test_days=int(len(j)))
    w = j.dropna(subset=["wet_day", "clim_rain_day_freq"])
    if len(w) and len(used):
        base = float(used.wet_day.mean())
        out |= dict(brier_wet_day=round(float(((w.clim_rain_day_freq - w.wet_day) ** 2).mean()), 4),
                    brier_wet_day_constant=round(float(((base - w.wet_day) ** 2).mean()), 4))
    for f, col in (("temp_c", "temp_c_mean"), ("rh", "rh_mean"), ("dew_depression_evening", "dew_depression_evening")):
        t = j.dropna(subset=[f"clim_{f}", col])
        if len(t) > 2:
            out[f"{f}_rmse"] = round(float(np.sqrt(((t[f"clim_{f}"] - t[col]) ** 2).mean())), 2)
            out[f"{f}_corr"] = round(float(np.corrcoef(t[f"clim_{f}"], t[col])[0, 1]), 3)
    out["levels"] = j.clim_clim_level.value_counts().to_dict()
    return out


skill = {c: clim_skill(c, n) for c, n in zip(CUTOFFS, CUTOFFS[1:] + [None])}
lap("climatology at evaluation cutoffs")

# %% coverage report and sanity checks
report = W.coverage_report(matches, rows, summary, venues, end)
lags = pd.DataFrame.from_dict(store.lags, orient="index")
bad_isd = sum(int(f.bad.sum()) for _, f in store._isd.values() if f is not None)
bad_dewpt = sum(int(f.bad_dewpt.sum()) for _, f in store._isd.values() if f is not None)
n_isd = sum(len(f) for _, f in store._isd.values() if f is not None)
bad_gsod = sum(int(g.g_bad.sum()) for _, g in store._gsod.values() if g is not None and "g_bad" in g)
report |= dict(
    generated=time.strftime("%Y-%m-%d %H:%M"), slice=dict(every=args.every, limit=args.limit),
    venue_years=len(plan), whole_year_venue_years=sum(p["climate"] for p in plan.values()),
    venue_years_without_candidate=sum(not p["cands"] for p in plan.values() if len(p["match_days"])),
    files_on_disk=dict(isd_lite=sum(len(v) for v in store.files["isd"].values()),
                       gsod=sum(len(v) for v in store.files["gsod"].values()),
                       isd_lite_404=len(W.read_missing(W.ISD_LITE_DIR)), gsod_404=len(W.read_missing(W.GSOD_DIR))),
    downloads=downloads,
    quality=dict(isd_station_days=n_isd, isd_station_days_flagged_dropped=bad_isd,
                 isd_station_days_dewpoint_dropped=bad_dewpt, gsod_station_days_flagged_dropped=bad_gsod,
                 rule="station-day mean temperature outside -10..50 C or mean RH > 100.5% (hourly gross limits "
                      "first: T -40..60 C, Td <= T + 1 C, SLP 900..1080 hPa, wind <= 60 m/s); dew point, RH and "
                      "dew depression dropped when the day's mean dew point is > 25 C below the station-month median"),
    gsod_lag=dict(stations=int(len(lags)), lag1=int(lags.lag.sum()) if len(lags) else 0,
                  lag1_by_country=(lags[lags.lag.eq(1)].index.map(
                      isd_hist.set_index("station").ctry).value_counts().to_dict() if len(lags) else {}),
                  lag0_with_g_reports=int(((lags.lag == 0) & (lags.n >= W.LAG_MIN_N)).sum()) if len(lags) else 0),
    venue_climate=dict(venues=len(cj["venues"]), levels=clim.clim_level.value_counts().to_dict(),
                       venue_month_days=int(clim.n.sum()), shrinkage_days=W.CLIM_K,
                       harmonic=dict(min_months=W.HARM_MIN_MONTHS, ridge_days=W.HARM_RIDGE),
                       k_chosen_on="2023 validation window only (cutoff 2023-01-01, scored on 2023 match days)"),
    climatology_by_cutoff=skill,
    sanity=W.sanity_checks(summary, matches, rows, venues),
    timing_s=timing,
)
out_path(W.REPORT_PATH).write_text(json.dumps(W.clean_json(report), indent=1, default=str, allow_nan=False) + "\n")
lap("done")
print(json.dumps(W.clean_json({k: report[k] for k in ("match_share_with_weather", "after_data_end", "day_source",
                                                       "precip_source", "station_distance_km", "quality")}),
                 indent=1, default=str))
print(json.dumps(W.clean_json({k: report["sanity"][k] for k in ("limited_overs", "india_monsoon", "english_summer")}),
                 indent=1, default=str))
