# %% Shared paths, constants and small helpers
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "wnba"
PROC = ROOT / "data" / "processed" / "wnba"
EXPORT = ROOT / "docs" / "models" / "wnba" / "data"
for _d in (RAW, PROC, EXPORT):
    _d.mkdir(parents=True, exist_ok=True)

SEASONS = list(range(2017, 2027))
CURRENT_SEASON = 2026
CUTOFF_DATE = "2026-11-11"

ZONES = ["rim", "short_mid", "long_mid", "corner3", "above_break3"]
ZONE_PTS = np.array([2, 2, 2, 3, 3])

WEHOOP = "https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-data/main/wnba"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

# Team home cities (lat, lon, UTC offset in summer) used for travel distance / time-zone features.
CITY = {
    "ATL": (33.757, -84.396, -4), "CHI": (41.865, -87.617, -5), "CON": (41.491, -72.090, -4),
    "DAL": (32.733, -97.111, -5), "IND": (39.764, -86.156, -4), "LA": (34.043, -118.267, -7),
    "LV": (36.090, -115.184, -7), "MIN": (44.980, -93.276, -5), "NY": (40.682, -73.975, -4),
    "PHX": (33.446, -112.071, -7), "SEA": (47.622, -122.354, -7), "WSH": (38.866, -76.987, -4),
    "GS": (37.768, -122.388, -7), "POR": (45.532, -122.667, -7), "TOR": (43.643, -79.379, -4),
    "SA": (29.427, -98.438, -5),  # San Antonio Stars (2017) -> Las Vegas Aces from 2018
    "TUL": (36.153, -95.993, -5),
}


def haversine_miles(a, b):
    lat1, lon1 = map(math.radians, a[:2])
    lat2, lon2 = map(math.radians, b[:2])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def write_json(path: Path, obj, digits: int | None = None):
    """Minified JSON writer that rounds floats and turns NaN into null."""

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, np.ndarray):
            return clean(o.tolist())
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (float, np.floating)):
            f = float(o)
            if not math.isfinite(f):
                return None
            if digits is not None:
                r = round(f, digits)
                return int(r) if r == int(r) and abs(r) < 1e15 else r
            return f
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if o is pd.NaT:
            return None
        return o

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(clean(obj), f, separators=(",", ":"), allow_nan=False)


OFFSEASON_GAP = 0.25  # an offseason counts as a quarter of a season of "skill drift" time


def season_bounds(games: pd.DataFrame) -> dict:
    d = pd.to_datetime(games.date)
    g = pd.DataFrame({"season": games.season.values, "d": d.values})
    return {s: (x.d.min(), x.d.max()) for s, x in g.groupby("season")}


def tau(season, date, bounds) -> np.ndarray:
    """Continuous 'season time': season*(1+gap) + fraction of that season elapsed."""
    season = np.asarray(season)
    date = pd.to_datetime(pd.Series(date)).values
    lo = np.array([bounds[s][0] for s in season], dtype="datetime64[ns]")
    hi = np.array([bounds[s][1] for s in season], dtype="datetime64[ns]")
    frac = (date - lo) / np.maximum(hi - lo, np.timedelta64(1, "D"))
    return season * (1 + OFFSEASON_GAP) + np.clip(frac.astype(float), 0, 1)


def tau_end(season: int) -> float:
    return season * (1 + OFFSEASON_GAP) + 1.0


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def expit(x):
    return 1.0 / (1.0 + np.exp(-x))
