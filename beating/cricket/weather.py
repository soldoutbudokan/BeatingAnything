"""NOAA ISD-lite / GSOD weather for Cricsheet matches: acquisition, per match-day features, venue climatology.

Matches. `load_matches` takes the ingest `matches` table (match_id, file_stem, dates_played, venue_id,
fam, result, method); scheduled days come from the rules timeline (`rules_for_match` on the match's info
block, read from the zip for Test/MDM only), never from len(dates). Match days are every scheduled day
from the start date plus played dates outside them (reserve days); summaries use scheduled days only.

Stations. Every venue-year with a match day gets up to four candidate stations from
`venues.station_candidates` ranked on that year's days (the `stations_on` ranking: distance plus the
data-cover, ICAO and height penalties of `venues.py`), keeping only stations with an ISD-lite file that
year in the bucket listing. Optionally (`climate_venues`) whole years are assembled too; the default
climatology does not use them. Files are fetched in rounds: the first candidate for every venue-year,
then the next candidate only where a needed day still lacks a field (any match day; more than 10% of the
days of a whole year). Fields fall back independently, in candidate order: the temperature block
(temperature, dew point, RH, evening dew depression, wind), pressure, cloud, precipitation and the GSOD
rain/thunder flags, so Lord's mostly takes temperature from St James's Park, cloud from Northolt and
precipitation from either. `station`/`distance_km` name the station of the temperature block,
`cloud_station` and `precip_station` the others.

Local time. Hourly UTC observations go to the venue clock with `utc_offset_hours` plus
`venues.dst_shift(dst_region, date)` (together `venues.utc_offset_on`) looked up on the standard-time
local date, so a changeover day takes the new offset all day (changes happen at night, outside every
window used). Half-hour offsets put observations at :30 local. Day window 10:00-22:00 and evening window
18:00-23:00 are inclusive on that clock; each station's years are concatenated before conversion, so
evenings that cross the UTC year are whole when both files are present (match days fetch the adjacent
year when the local day spans it).

Fields (per local day). `temp_c_mean`, `dewpt_c_mean`, `rh_mean` (mean of hourly Magnus RH, a=17.625,
b=243.04, over hours with both values), `wind_ms_mean`, `pressure_hpa_mean` (sea level) and
`cloud_oktas_mean` over the day window; `dew_depression_evening` = mean hourly T - Td over the evening
window; `n_obs` hourly temperatures in the day window (at least 3, else the block is missing). Sky cover
codes 0-8 are oktas, 9 (obscured / not estimable) and 10 (partial obscuration) are missing, the old
tenths-based codes map like ISD-lite's own METAR mapping (11-13 scattered -> 4, 14-16 broken -> 7, 17-19
overcast -> 8); a station-year whose valid codes are almost never non-zero (under 5%, typical of METAR
stations that only code CLR/NSC as 0 and layers as 9) has no cloud. Precipitation: hourly amounts are the
1-hour values plus non-overlapping 6-hour reports (greedy by end time) spread over the hours a window
lacks, never counting an hour twice; trace (-1) is 0 mm but a wet hour; 1-hour values are ignored in a
station-year where they are never non-zero although 6-hour reports are. A local-day total (hours whose
midpoint falls on the day) needs at least 20 known hours, otherwise GSOD: PRCP in inches -> mm, 99.99
missing, flags D/F/G (four 6-hour, two 12-hour or one 24-hour report) taken as the day total, A/B/C/E
(partial sums) only when positive, H (zero with precipitation reported) 0 mm and wet, I (nothing
reported) missing. GSOD totals are filed under the UTC date of the report, so where the single 24-hour
report (flag G) is read in the morning (UK 06 UTC, India 03 UTC, South Africa, Sri Lanka) the amount on
date d+1 is mostly the rain of d: per station, G amounts move back one day when the rank correlation of
log1p(amount) on d+1 with the FRSHTT rain flag of d beats that on d by 0.05 (60 or more days; at
Heathrow, whose hourly ISD-lite totals are complete, the d+1 amount correlates 0.81 with day d against
0.47 on d); sums of sub-daily reports (flags A-F, H) stay on their date. `precip_hours` counts wet 1-hour
values between 10:00 and 22:00 and exists only where 9 of those 12 hours have a 1-hour value (mostly US
and some UK/airport METARs). `rain_flag`/`thunder_flag` are GSOD's FRSHTT digits for the UTC day (a
station-year with no rain flag despite five days of 1 mm or more has none); `wet_day` is precipitation
>= 1 mm when the amount is known, else the rain flag. When no ISD-lite station has the temperature block
the GSOD daily means (UTC day, all hours) fill it with `source = 'gsod'`. `elevation_m` is the venue's
(curated or best-station) height from `config/cricket-venues.csv`, `utc_offset` the local offset used.

Climatology. `climatology(cutoff_date)` uses only scheduled match days dated strictly before the cutoff
(one row per venue-date, so double-headers count once). Each venue x calendar-month mean is shrunk with K
pseudo-days toward a prior built top-down from the same days, each level shrunk to the one above with K
pseudo-days: all-days mean -> calendar month -> region x month -> (region, country) x month -> that plus
the venue's offset (its mean residual over all its days, shrunk with K). At the region, country and venue
levels the prior is first smoothed into a day-weighted annual harmonic (mean, cosine, sine) whose seasonal
terms are ridge-penalised with 30 days toward the parent's shape, wherever the group has data in at least
four months, so months without cricket are extrapolated from the group's own season (Lord's in January
about 5 C, not the global January) instead of borrowed from another hemisphere's. K is per field
(`CLIM_K`: 5 for temperature and dew point, 10 for RH, cloud and wind, 20 for evening dew depression, 100
for the precipitation fields), chosen on the 2023 validation window only (cutoff 2023-01-01, scored on
2023 match days). `clim_level` says what the venue-month rests on (venue_month, venue, country, region,
global). Match days are the right base rate for the simulator (it is conditioned on a match being on
Cricsheet, which omits most matches abandoned without a ball) but they under-sample off-season months and
sunny days, so the extrapolated months run warm (MCG in July about 17 C). rain_day_freq is per match day.
`impute` fills a frame's missing fields from a climatology and adds `*_missing` flags.

Quality. Hourly values outside gross limits (temperature -40..60 C, dew point above temperature by more
than 1 C, pressure 900..1080 hPa, wind over 60 m/s) are dropped; a station-day whose mean temperature is
outside -10..50 C or mean RH above 100.5% is flagged and dropped whole (RH is then capped at 100), and one
whose mean dew point is more than 25 C below the station's median for that calendar month (a failed
hygrometer: Pershore read -30 C in September 2023) loses its dew point, RH and dew depression (`bad_dewpt`;
real dry spells at Windhoek, the Highveld and Karachi sit within 23 C).

Limits. The NOAA AWS mirror ends on `venues.isd_data_end()` (2025-08-24; the 2026 prefixes are empty):
later matches (2,988 of 23,132) have `source = 'none'` and must use climatology. Some grounds have no
station with data for years (Seddon Park, Hamilton, before 2021). ISD-lite has no present weather, so
outside hourly-precipitation stations rain intensity within the day is unknown and `wet_day` from flags
counts drizzle days. GSOD means and flags are UTC days, a good proxy for 10:00-22:00 local only between
about UTC-5 and UTC+13. Station data are airport or synoptic sites up to 60 km from the ground; sea
breezes, altitude and urban heat make them a proxy for the ground, not a measurement at it. Cloud is
missing at most New Zealand and many English stations (METARs that report layers only).
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gzip
import http.client
import io
import json
from pathlib import Path
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import zipfile

import numpy as np
import pandas as pd

from beating.cricket import venues as V

ROOT = V.ROOT
RAW_NOAA = ROOT / "data" / "raw" / "noaa"
ISD_LITE_DIR = RAW_NOAA / "isd-lite"
GSOD_DIR = RAW_NOAA / "gsod"
OUT_DIR = ROOT / "data" / "processed" / "cricket"
MATCH_DAY_PATH = OUT_DIR / "weather_match_day.parquet"
VENUE_DAY_PATH = OUT_DIR / "weather_venue_day.parquet"
MATCH_PATH = ROOT / "data" / "derived" / "cricket" / "weather_match.csv.gz"
CLIMATE_PATH = ROOT / "docs" / "cricket" / "data" / "venue_climate.json"
REPORT_PATH = ROOT / "reports" / "cricket-weather-coverage.json"
RULES_PATH = ROOT / "config" / "cricket-rules.json"
ISD_LITE_URL = "https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data/{y}/{s}-{y}.gz"
GSOD_URL = "https://noaa-gsod-pds.s3.amazonaws.com/{y}/{s}.csv"

DAY_WINDOW, EVENING_WINDOW = (10.0, 22.0), (18.0, 23.0)
MIN_OBS, MIN_EVENING_OBS, MIN_CLOUD_OBS, MIN_AUX_OBS = 3, 1, 2, 2
MIN_PRECIP_COVER_H, MIN_PRECIP_HOURS_COVER = 20, 9
N_CANDIDATES = 4
CLIMATE_FROM = 2015
CLIMATE_GAP_SHARE = 0.10
WET_MM = 1.0
MAGNUS_A, MAGNUS_B = 17.625, 243.04
TEMP_OK, RH_MAX, DEWPT_LOW_ANOM = (-10.0, 50.0), 100.5, 25.0
CLOUD_MIN_NONZERO, CLOUD_MIN_VALID = 0.05, 100
LAG_MIN_N, LAG_MIN_GAIN = 60, 0.05
SKY_OKTAS = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, np.nan, np.nan, 4, 4, 4, 7, 7, 7, 8, 8, 8])
GSOD_FULL, GSOD_PARTIAL = set("DFG"), set("ABCE")
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}

CORE = ["temp_c_mean", "dewpt_c_mean", "rh_mean", "n_obs", "dew_depression_evening", "n_obs_evening",
        "wind_ms_mean"]
ISD_COLS = CORE + ["cloud_oktas_mean", "n_cloud", "pressure_hpa_mean", "isd_precip_mm", "isd_precip_cover",
                   "precip_hours", "bad", "bad_dewpt"]
GSOD_COLS = ["g_temp", "g_dewp", "g_n", "g_slp", "g_wind", "g_prcp", "g_flag", "rain_flag", "thunder_flag", "g_bad"]
DAY_COLS = ["station", "station_rank", "distance_km", "source", "n_obs", "temp_c_mean", "rh_mean", "dewpt_c_mean",
            "dew_depression_evening", "n_obs_evening", "cloud_oktas_mean", "cloud_station", "precip_mm_day",
            "precip_source", "precip_station", "precip_hours", "rain_flag", "thunder_flag", "wet_day",
            "wind_ms_mean", "pressure_hpa_mean", "elevation_m", "utc_offset"]
CLIMATE_FIELDS = {"temp_c": "temp_c_mean", "rh": "rh_mean", "dewpt_c": "dewpt_c_mean",
                  "dew_depression_evening": "dew_depression_evening", "cloud_oktas": "cloud_oktas_mean",
                  "wind_ms": "wind_ms_mean", "precip_mm": "precip_mm_day", "rain_day_freq": "wet_day",
                  "precip_mm_rain_day": "rain_mm"}
CLIMATE_RANGE = {"rh": (0, 100), "cloud_oktas": (0, 8), "rain_day_freq": (0, 1), "precip_mm": (0, None),
                 "precip_mm_rain_day": (WET_MM, None), "wind_ms": (0, None), "dew_depression_evening": (0, None)}
HARM_MIN_MONTHS, HARM_RIDGE = 4, 30.0
CLIM_K = {"temp_c": 5.0, "rh": 10.0, "dewpt_c": 5.0, "dew_depression_evening": 20.0, "cloud_oktas": 10.0,
          "wind_ms": 10.0, "precip_mm": 100.0, "rain_day_freq": 100.0, "precip_mm_rain_day": 100.0}
MATCH_COLS = ["match_id", "file_stem", "start_date", "dates_played", "venue_id", "fam", "gender", "match_type",
              "team_type", "result", "method"]
MATCH_KEYS = ["start_date", "venue_id", "fam", "match_type", "gender", "scheduled_days"]


# ---------------------------------------------------------------- matches

def _info(b: bytes) -> dict:
    k = b.find(b'"innings"')  # Cricsheet writes meta and info before the long innings list
    if k > 0:
        try:
            return json.loads(b[:k].rstrip().rstrip(b",") + b"}")["info"]
        except (ValueError, KeyError):
            pass
    return json.loads(b)["info"]


def _overrides() -> dict:
    try:
        return json.loads(RULES_PATH.read_text()).get("match_overrides", {})
    except (OSError, ValueError):
        return {}


def scheduled_days(info: dict, match_id: str, overrides: dict | None = None) -> tuple[int, str]:
    """Scheduled match days from the rules timeline (never len(dates)); 1 for limited overs, and when the
    timeline cannot be read, the config's match override or 5 (men's Tests) / 4 (women's Tests, MDM)."""
    if info.get("match_type") not in ("Test", "MDM"):
        return 1, "limited_overs"
    try:
        from beating.cricket.rules import rules_for_match
        r = rules_for_match(info, match_id=match_id)
        d = r.get("scheduled_days") or r.get("test_days")
        if d:
            return int(d), "rules"
    except Exception:  # the timeline is optional here; fall back below
        pass
    d = (_overrides() if overrides is None else overrides).get(str(match_id), {}).get("scheduled_days")
    if d:
        return int(d), "override"
    return (5 if info["match_type"] == "Test" and info.get("gender") == "male" else 4), "default"


def load_matches(matches: pd.DataFrame | None = None, zip_path: Path | str = V.CRICSHEET_ZIP) -> pd.DataFrame:
    """Ingest matches with `dates` (list), `start_date` (str) and rules-timeline `scheduled_days` /
    `scheduled_source`; a `scheduled_days` column already present is kept (fixtures)."""
    if matches is None:
        from beating.cricket.ingest import read_table
        matches = read_table("matches", columns=MATCH_COLS)
    m = matches.reset_index(drop=True).copy()
    m["dates"] = [json.loads(d) if isinstance(d, str) else list(d) for d in m.dates_played]
    m["start_date"] = m.start_date.astype(str).str[:10]
    if "scheduled_days" in m:
        m["scheduled_source"] = m.get("scheduled_source", "given")
        return m
    sched, how = np.ones(len(m), dtype=int), np.full(len(m), "limited_overs", dtype=object)
    multi = np.flatnonzero(m.match_type.isin(["Test", "MDM"]).to_numpy())
    if len(multi):
        ov = _overrides()
        with zipfile.ZipFile(zip_path) as z:
            names = {Path(n).stem: n for n in z.namelist() if n.endswith(".json")}
            for i in multi:
                info = _info(z.read(names[str(m.file_stem.iat[i])]))
                sched[i], how[i] = scheduled_days(info, int(m.match_id.iat[i]), ov)
    m["scheduled_days"], m["scheduled_source"] = sched, how
    return m


def match_days(matches: pd.DataFrame) -> pd.DataFrame:
    """Long (match_id, day, date): every scheduled day from the start date plus any played date outside
    them (reserve days); `scheduled` and `played` flag each."""
    rows = []
    for m in matches.itertuples():
        start = pd.Timestamp(m.start_date)
        played = {pd.Timestamp(d) for d in m.dates}
        sched = {start + pd.Timedelta(days=k) for k in range(m.scheduled_days)}
        for d in sorted(sched | played):
            rows.append((m.match_id, (d - start).days + 1, d, d in sched, d in played))
    return pd.DataFrame(rows, columns=["match_id", "day", "date", "scheduled", "played"])


# ---------------------------------------------------------------- stations

def listed_station_years(path: Path | str = V.ISD_LITE_SIZES) -> set | None:
    if not Path(path).exists():
        return None
    s = pd.read_csv(path, dtype={"station": str})
    return set(zip(s.station, s.year.astype(int)))


def _ref_elev(v) -> float | None:
    return float(v["elevation_m"]) if v.get("elevation_source") == "curated" and pd.notna(v["elevation_m"]) else None


def venue_year_candidates(v: pd.Series, year: int, end: pd.Timestamp, isd: pd.DataFrame, sy: pd.DataFrame,
                          listed: set | None, k: int = N_CANDIDATES) -> list[tuple[str, float]]:
    """Up to k (station, distance_km) best first for the venue on that year's days, keeping stations with
    an ISD-lite file that year when the bucket listing is known."""
    if year > end.year:
        return []
    days = pd.date_range(f"{year}-01-01", min(pd.Timestamp(f"{year}-12-31"), end))
    c = V.station_candidates(v["lat"], v["lon"], days, isd, V.MAX_KM, _ref_elev(v), sy)
    if listed is not None:
        c = c[np.array([(s, year) in listed for s in c.station], dtype=bool)]
    return [(s, round(float(d), 1)) for s, d in zip(c.station.head(k), c.distance_km.head(k))]


def local_day_utc_years(day: pd.Timestamp, offset: float) -> set[int]:
    """UTC years the local day [00:00, 24:00) touches."""
    a, b = day - pd.Timedelta(hours=offset), day + pd.Timedelta(hours=24 - offset)
    return {a.year, (b - pd.Timedelta(seconds=1)).year}


# ---------------------------------------------------------------- download

def isd_lite_path(station: str, year: int, root: Path = ISD_LITE_DIR) -> Path:
    return root / str(year) / f"{station}-{year}.gz"


def gsod_path(station: str, year: int, root: Path = GSOD_DIR) -> Path:
    return root / str(year) / f"{station.replace('-', '')}.csv"


def isd_lite_url(station: str, year: int) -> str:
    return ISD_LITE_URL.format(y=year, s=station)


def gsod_url(station: str, year: int) -> str:
    return GSOD_URL.format(y=year, s=station.replace("-", ""))


def _missing_file(root: Path) -> Path:
    return root / "missing.txt"


def read_missing(root: Path) -> set[str]:
    p = _missing_file(root)
    return set(p.read_text().split()) if p.exists() else set()


def _get_bytes(url: str, tries: int = 5, timeout: float = 60.0) -> tuple[str, bytes]:
    for k in range(tries):
        try:
            with urlopen(url, timeout=timeout) as r:
                return "ok", r.read()
        except HTTPError as e:
            if e.code == 404:
                return "404", b""
            if e.code not in TRANSIENT_HTTP or k == tries - 1:
                return f"http_{e.code}", b""
        except (URLError, OSError, http.client.HTTPException):
            if k == tries - 1:
                return "error", b""
        time.sleep(min(30.0, 2.0 ** k) * (0.75 + 0.5 * random.random()))
    return "error", b""


def fetch(jobs, root: Path, workers: int = 4, get=_get_bytes, log_every: int = 250) -> Counter:
    """Download (url, path) jobs under root that are neither cached nor recorded 404s, at most `workers` at
    a time with retry and backoff on transient errors; new 404s are appended to root/missing.txt."""
    missing = read_missing(root)
    todo = sorted({(u, Path(p)) for u, p in jobs if not Path(p).exists()
                   and Path(p).relative_to(root).as_posix() not in missing}, key=lambda j: str(j[1]))
    counts, new404, t0 = Counter(), [], time.time()

    def one(job):
        url, path = job
        status, body = get(url)
        if status == "ok":
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            tmp.write_bytes(body)
            tmp.replace(path)
        return status, len(body)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, ((url, path), (status, n)) in enumerate(zip(todo, ex.map(one, todo)), 1):
            counts[status] += 1
            counts["bytes"] += n
            if status == "404":
                new404.append(path.relative_to(root).as_posix())
            if log_every and i % log_every == 0:
                print(f"  {i}/{len(todo)} {dict(counts)} {time.time() - t0:.0f} s", flush=True)
    if new404:
        root.mkdir(parents=True, exist_ok=True)
        with _missing_file(root).open("a") as f:
            f.write("".join(k + "\n" for k in new404))
    counts["requested"] = len(todo)
    return counts


# ---------------------------------------------------------------- ISD-lite

def read_isd_lite(raw: bytes) -> np.ndarray:
    """ISD-lite text (gzipped or not) -> int array (n, 12): year month day hour T Td SLP dir speed sky p1 p6."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    a = np.array(raw.split(), dtype=np.int64)
    return a.reshape(-1, 12)


def utc_hours(a: np.ndarray) -> np.ndarray:
    """Hours since 1970-01-01 00 UTC for ISD-lite rows."""
    ym = (a[:, 0] - 1970) * 12 + a[:, 1] - 1
    d = ym.astype("datetime64[M]").astype("datetime64[D]").astype(np.int64) + a[:, 2] - 1
    return d * 24 + a[:, 3]


def local_clock(hours: np.ndarray, offset: float, dst_region: str) -> np.ndarray:
    """Local clock (hours since local 1970-01-01) for UTC hours: standard offset plus the DST shift of the
    standard-time local date."""
    std = hours + float(offset)
    if dst_region in ("", "none"):
        return std
    day = np.floor(std / 24).astype(np.int64)
    u, inv = np.unique(day, return_inverse=True)
    shift = np.array([V.dst_shift(dst_region, np.datetime64(int(x), "D")) for x in u])
    return std + shift[inv]


def magnus_rh(t, td):
    return 100.0 * np.exp(MAGNUS_A * td / (MAGNUS_B + td) - MAGNUS_A * t / (MAGNUS_B + t))


def _grid(a: np.ndarray, j: int, g: np.ndarray, n: int, lo: float, hi: float, scale: float = 10.0) -> np.ndarray:
    x = np.full(n, np.nan)
    v = a[:, j] / scale
    ok = (a[:, j] != -9999) & (v >= lo) & (v <= hi)
    x[g[ok]] = v[ok]
    return x


def _by_day(idx: np.ndarray, x: np.ndarray, mask: np.ndarray, m: int) -> tuple[np.ndarray, np.ndarray]:
    ok = mask & ~np.isnan(x)
    c = np.bincount(idx[ok], minlength=m)
    s = np.bincount(idx[ok], weights=x[ok], minlength=m)
    with np.errstate(invalid="ignore", divide="ignore"):
        return s / np.where(c > 0, c, np.nan), c


def hourly_precip(p1: np.ndarray, p6: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hourly amounts on a contiguous UTC grid from 1-hour values and 6-hour reports at window ends (mm,
    NaN missing): non-overlapping 6-hour windows taken greedily by end hour, each window's total spread
    over the hours it lacks (or over all six when the 1-hour values undercount it). Returns (amount, known)."""
    amt = p1.copy()
    last = -10
    for e in np.flatnonzero(~np.isnan(p6)):
        if e < 5 or e - 5 <= last:
            continue
        last = e
        seg = amt[e - 5:e + 1]
        miss = np.isnan(seg)
        resid = max(p6[e] - np.nansum(seg), 0.0)
        if miss.any():
            seg[miss] = resid / miss.sum()
        elif resid > 0.05:
            seg += resid / 6
    return amt, ~np.isnan(amt)


def isd_days(a: np.ndarray, offset: float, dst_region: str = "none") -> pd.DataFrame:
    """Per local date features from ISD-lite rows of one station (any years, any order)."""
    cols = ISD_COLS
    if len(a) == 0:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))
    h, first = np.unique(utc_hours(a), return_index=True)
    a = a[first]
    h0, n = int(h[0]), int(h[-1] - h[0] + 1)
    g = h - h0
    t, td = _grid(a, 4, g, n, -40, 60), _grid(a, 5, g, n, -60, 60)
    td[td > t + 1.0] = np.nan
    slp, ws = _grid(a, 6, g, n, 900, 1080), _grid(a, 8, g, n, 0, 60)
    sky = np.full(n, np.nan)
    ok = (a[:, 9] >= 0) & (a[:, 9] <= 19)
    sky[g[ok]] = SKY_OKTAS[a[ok, 9]]
    p1, p6 = _grid(a, 10, g, n, -0.1, 500), _grid(a, 11, g, n, -0.1, 500)
    wet1 = p1 < 0  # trace
    p1[wet1], p6[p6 < 0] = 0.0, 0.0
    wet1 |= p1 > 0
    year = (np.arange(h0, h0 + n).astype("datetime64[h]").astype("datetime64[Y]").astype(np.int64) + 1970)
    for y in np.unique(year):
        iy = year == y
        valid = ~np.isnan(sky[iy])
        if valid.sum() < CLOUD_MIN_VALID or (sky[iy][valid] > 0).mean() < CLOUD_MIN_NONZERO:
            sky[iy] = np.nan
        if (~np.isnan(p1[iy])).any() and not wet1[iy].any() and (p6[iy] > 0).sum() >= 5:
            p1[iy], wet1[iy] = np.nan, False
    known1 = ~np.isnan(p1)
    amt, known = hourly_precip(p1, p6)

    loc = local_clock(np.arange(h0, h0 + n), offset, dst_region)
    day = np.floor(loc / 24).astype(np.int64)
    hr = loc - 24 * day
    mid = loc - 0.5  # precipitation amounts are for the hour ending at the observation
    pday = np.floor(mid / 24).astype(np.int64)
    phr = mid - 24 * pday
    d0 = min(day.min(), pday.min())
    di, pi = day - d0, pday - d0
    m = int(max(di.max(), pi.max()) + 1)
    win = (hr >= DAY_WINDOW[0]) & (hr <= DAY_WINDOW[1])
    eve = (hr >= EVENING_WINDOW[0]) & (hr <= EVENING_WINDOW[1])
    both = ~np.isnan(t) & ~np.isnan(td)

    out = {}
    out["temp_c_mean"], n_obs = _by_day(di, t, win, m)
    out["dewpt_c_mean"], n_both = _by_day(di, np.where(both, td, np.nan), win, m)
    out["rh_mean"], _ = _by_day(di, np.where(both, magnus_rh(t, td), np.nan), win, m)
    out["dew_depression_evening"], n_eve = _by_day(di, np.where(both, t - td, np.nan), eve, m)
    out["wind_ms_mean"], n_wind = _by_day(di, ws, win, m)
    out["cloud_oktas_mean"], n_cloud = _by_day(di, sky, win, m)
    out["pressure_hpa_mean"], n_slp = _by_day(di, slp, win, m)
    out["n_obs"], out["n_obs_evening"], out["n_cloud"] = n_obs, n_eve, n_cloud
    cover = np.bincount(pi[known], minlength=m)
    out["isd_precip_mm"] = np.where(cover >= MIN_PRECIP_COVER_H, np.bincount(pi[known], amt[known], m), np.nan)
    out["isd_precip_cover"] = cover
    pw = (phr >= DAY_WINDOW[0]) & (phr <= DAY_WINDOW[1])
    c1 = np.bincount(pi[pw & known1], minlength=m)
    out["precip_hours"] = np.where(c1 >= MIN_PRECIP_HOURS_COVER, np.bincount(pi[pw & wet1], minlength=m), np.nan)
    df = pd.DataFrame(out, index=pd.DatetimeIndex((np.arange(m) + d0).astype("datetime64[D]"), name="date"))
    df.loc[n_obs < MIN_OBS, CORE] = np.nan
    df.loc[n_both < MIN_OBS, ["dewpt_c_mean", "rh_mean"]] = np.nan
    df.loc[n_eve < MIN_EVENING_OBS, "dew_depression_evening"] = np.nan
    df.loc[n_wind < MIN_AUX_OBS, "wind_ms_mean"] = np.nan
    df.loc[n_cloud < MIN_CLOUD_OBS, "cloud_oktas_mean"] = np.nan
    df.loc[n_slp < MIN_AUX_OBS, "pressure_hpa_mean"] = np.nan
    df["n_obs"], df["n_obs_evening"], df["n_cloud"] = n_obs, n_eve, n_cloud
    df["bad"] = impossible(df.temp_c_mean, df.rh_mean)
    med = df.dewpt_c_mean.where(~df.bad).groupby(df.index.month).transform("median")
    df["bad_dewpt"] = (df.dewpt_c_mean < med - DEWPT_LOW_ANOM).to_numpy() & ~df.bad.to_numpy()
    df.loc[df.bad_dewpt, ["dewpt_c_mean", "rh_mean", "dew_depression_evening"]] = np.nan
    df.loc[df.bad, [c for c in cols if c not in ("bad", "bad_dewpt")]] = np.nan
    df["rh_mean"] = df.rh_mean.clip(upper=100.0)
    keep = (n_obs > 0) | (cover > 0) | (n_cloud > 0) | (n_slp > 0) | df.bad.to_numpy()
    return df.loc[keep, cols]


def impossible(temp, rh) -> np.ndarray:
    temp, rh = np.asarray(temp, float), np.asarray(rh, float)
    return (temp < TEMP_OK[0]) | (temp > TEMP_OK[1]) | (rh > RH_MAX)


# ---------------------------------------------------------------- GSOD

def read_gsod(raw: bytes) -> pd.DataFrame:
    """GSOD station-year CSV -> per UTC date: daily means (C, hPa, m/s), precipitation (mm, by the flag
    rules in the module docstring), its flag and the FRSHTT rain/thunder digits."""
    d = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    if d.empty or "DATE" not in d:
        return pd.DataFrame(columns=GSOD_COLS, index=pd.DatetimeIndex([], name="date"))
    num = lambda c, miss: pd.to_numeric(d[c].str.strip(), errors="coerce").where(lambda x: x < miss)
    out = pd.DataFrame(index=pd.DatetimeIndex(pd.to_datetime(d.DATE.str.strip()), name="date"))
    out["g_temp"] = ((num("TEMP", 9999) - 32) * 5 / 9).to_numpy()
    out["g_dewp"] = ((num("DEWP", 9999) - 32) * 5 / 9).to_numpy()
    out["g_n"] = pd.to_numeric(d.TEMP_ATTRIBUTES.str.strip(), errors="coerce").fillna(0).to_numpy()
    out["g_slp"] = num("SLP", 9999).where(lambda x: x.between(900, 1080)).to_numpy()
    out["g_wind"] = (num("WDSP", 999) * 0.514444).to_numpy()
    p = (num("PRCP", 99.99) * 25.4).to_numpy()
    flag = d.PRCP_ATTRIBUTES.str.strip().to_numpy()
    full, part = np.isin(flag, list(GSOD_FULL)), np.isin(flag, list(GSOD_PARTIAL))
    p = np.where(full | (part & (p > 0)), p, np.where(flag == "H", 0.0, np.nan))
    out["g_prcp"], out["g_flag"] = p, flag
    fr = d.FRSHTT.str.strip().str.zfill(6)
    rain = (fr.str[1] == "1").astype(float).to_numpy()
    thunder = (fr.str[4] == "1").astype(float).to_numpy()
    rain = np.where(flag == "H", 1.0, rain)
    if rain.sum() == 0 and (p >= WET_MM).sum() >= 5:
        rain[:], thunder[:] = np.nan, np.nan
    out["rain_flag"], out["thunder_flag"] = rain, thunder
    out["g_bad"] = impossible(out.g_temp, magnus_rh(out.g_temp, out.g_dewp))
    out.loc[out.g_bad, ["g_temp", "g_dewp", "g_n"]] = [np.nan, np.nan, 0]
    return out[~out.index.duplicated()][GSOD_COLS]


def gsod_lag(g: pd.DataFrame) -> tuple[int, dict]:
    """0 or 1: whether the station's one-report 24-hour totals (flag G) on date d+1 hold the rain of date d
    (read the next morning), from the rank correlation of log1p(amount) with the FRSHTT rain flag of d."""
    g = g.asfreq("D") if len(g) else g
    y = np.log1p(g.g_prcp.where(g.g_flag.eq("G")))
    stats = {}
    for lag in (0, 1):
        yl = y.shift(-lag)
        m = yl.notna() & g.rain_flag.notna()
        c = yl[m].corr(g.rain_flag[m], method="spearman") if m.sum() > 2 else np.nan
        stats[lag] = (int(m.sum()), np.nan if c is None else float(c))
    n, c0, c1 = min(stats[0][0], stats[1][0]), stats[0][1], stats[1][1]
    lag = int(n >= LAG_MIN_N and not np.isnan(c0 + c1) and c1 - c0 >= LAG_MIN_GAIN)
    r = lambda x: None if np.isnan(x) else round(x, 3)
    return lag, dict(n=n, corr0=r(c0), corr1=r(c1))


def lagged_precip(g: pd.DataFrame, lag: int) -> pd.DataFrame:
    """Precipitation per day d: the flag-G total filed on d+lag, else the other full or partial sums on d."""
    p = g[["g_prcp", "g_flag"]].dropna(subset=["g_prcp"])
    is_g = p.g_flag.eq("G")
    shifted = p[is_g].set_axis(p.index[is_g] - pd.Timedelta(days=lag))
    rest = p[~is_g]
    return pd.concat([shifted, rest[~rest.index.isin(shifted.index)]]).sort_index()


# ---------------------------------------------------------------- station-day store

class StationStore:
    """Parsed station-days, cached per (station, offset, dst_region) for ISD-lite and per station for GSOD,
    recomputed when new years appear on disk."""

    def __init__(self, isd_root: Path = ISD_LITE_DIR, gsod_root: Path = GSOD_DIR):
        self.isd_root, self.gsod_root = isd_root, gsod_root
        self._isd, self._gsod, self.lags = {}, {}, {}
        self.refresh()

    def refresh(self) -> None:
        """Rescan the caches for station-year files (call after downloading)."""
        self.files = {}
        for kind, root, pat in (("isd", self.isd_root, "*.gz"), ("gsod", self.gsod_root, "*.csv")):
            got = {}
            for d in (root.iterdir() if root.exists() else ()):
                if d.is_dir() and d.name.isdigit():
                    for f in d.glob(pat):
                        st = f.name[:12] if kind == "isd" else f"{f.stem[:6]}-{f.stem[6:]}"
                        got.setdefault(st, []).append(int(d.name))
            self.files[kind] = {k: tuple(sorted(v)) for k, v in got.items()}

    def _years(self, kind: str, station: str) -> tuple[int, ...]:
        return self.files[kind].get(station, ())

    def isd(self, station: str, offset: float, dst_region: str) -> pd.DataFrame | None:
        years = self._years("isd", station)
        key = (station, float(offset), dst_region)
        if key not in self._isd or self._isd[key][0] != years:
            arrs = [read_isd_lite(isd_lite_path(station, y, self.isd_root).read_bytes()) for y in years]
            arrs = [x for x in arrs if len(x)]
            df = isd_days(np.concatenate(arrs), offset, dst_region).astype("float32") if arrs else None
            self._isd[key] = (years, df)
        return self._isd[key][1]

    def gsod(self, station: str) -> pd.DataFrame | None:
        years = self._years("gsod", station)
        if station not in self._gsod or self._gsod[station][0] != years:
            frames = [read_gsod(gsod_path(station, y, self.gsod_root).read_bytes()) for y in years]
            frames = [f for f in frames if len(f)]
            g = pd.concat(frames).sort_index() if frames else None
            if g is not None:
                g = g[~g.index.duplicated()]
                lag, stats = gsod_lag(g)
                self.lags[station] = dict(lag=lag, **stats)
                g = g.drop(columns=["g_prcp", "g_flag"]).join(lagged_precip(g, lag), how="outer")
            self._gsod[station] = (years, g)
        return self._gsod[station][1]


# ---------------------------------------------------------------- assembly

def _fill(out: pd.DataFrame, need: np.ndarray, frame: pd.DataFrame, cols, src_cols) -> None:
    for c, s in zip(cols, src_cols):
        out[c] = np.where(need, frame[s].to_numpy(float), out[c].to_numpy(float))


def assemble(days: pd.DatetimeIndex, cands: list[tuple[str, float]], isd: list, gsod: list) -> pd.DataFrame:
    """Venue-day fields with independent field-group fallback over the candidate stations (best first).
    `isd`/`gsod` are the candidates' station-day frames (None when absent)."""
    n = len(days)
    out = pd.DataFrame(index=days)
    for c in DAY_COLS:
        out[c] = np.nan
    for c in ("station", "source", "cloud_station", "precip_source", "precip_station"):
        out[c] = None
    out["source"], out["precip_source"] = "none", "none"
    I = [None if f is None else f.reindex(days) for f in isd]
    G = [None if f is None else f.reindex(days) for f in gsod]
    for k, (st, dist) in enumerate(cands):
        f = I[k]
        if f is None:
            continue
        need = out.source.eq("none").to_numpy() & f.temp_c_mean.notna().to_numpy()
        _fill(out, need, f, CORE, CORE)
        out.loc[need, ["station", "source"]] = [st, "isd_lite"]
        out.loc[need, ["station_rank", "distance_km"]] = [k + 1, dist]
        need = out.cloud_oktas_mean.isna().to_numpy() & f.cloud_oktas_mean.notna().to_numpy()
        _fill(out, need, f, ["cloud_oktas_mean"], ["cloud_oktas_mean"])
        out.loc[need, "cloud_station"] = st
        need = out.pressure_hpa_mean.isna().to_numpy() & f.pressure_hpa_mean.notna().to_numpy()
        _fill(out, need, f, ["pressure_hpa_mean"], ["pressure_hpa_mean"])
    for k, (st, dist) in enumerate(cands):
        g = G[k]
        if g is None:
            continue
        need = out.source.eq("none").to_numpy() & g.g_temp.notna().to_numpy() & (g.g_n.to_numpy(float) >= 4)
        _fill(out, need, g, ["temp_c_mean", "dewpt_c_mean", "wind_ms_mean", "n_obs"],
              ["g_temp", "g_dewp", "g_wind", "g_n"])
        out.loc[need, "rh_mean"] = np.minimum(magnus_rh(out.temp_c_mean[need], out.dewpt_c_mean[need]), 100.0)
        out.loc[need, ["station", "source"]] = [st, "gsod"]
        out.loc[need, ["station_rank", "distance_km"]] = [k + 1, dist]
        need = out.pressure_hpa_mean.isna().to_numpy() & g.g_slp.notna().to_numpy()
        _fill(out, need, g, ["pressure_hpa_mean"], ["g_slp"])
        need = out.rain_flag.isna().to_numpy() & g.rain_flag.notna().to_numpy()
        _fill(out, need, g, ["rain_flag", "thunder_flag"], ["rain_flag", "thunder_flag"])
    for k, (st, dist) in enumerate(cands):
        for src, f, col in (("isd_lite", I[k], "isd_precip_mm"), ("gsod", G[k], "g_prcp")):
            if f is None:
                continue
            need = out.precip_mm_day.isna().to_numpy() & f[col].notna().to_numpy()
            _fill(out, need, f, ["precip_mm_day"], [col])
            if src == "isd_lite":
                _fill(out, need, f, ["precip_hours"], ["precip_hours"])
            out.loc[need, ["precip_source", "precip_station"]] = [src, st]
    known = out.precip_mm_day.notna()
    out["wet_day"] = np.where(known, (out.precip_mm_day >= WET_MM).astype(float), out.rain_flag)
    return out


def needs(frame: pd.DataFrame, match_days: pd.DatetimeIndex, climate: bool, cols) -> bool:
    """True when a match day, or more than 10% of a climatology year, still lacks any of cols."""
    miss = frame[cols].isna().any(axis=1)
    if len(match_days) and miss.reindex(match_days).fillna(True).any():
        return True
    return bool(climate and len(miss) and miss.mean() > CLIMATE_GAP_SHARE)


# ---------------------------------------------------------------- plan and rounds

TRIGGER_ISD = ["temp_c_mean", "rh_mean", "dew_depression_evening", "cloud_oktas_mean"]
TRIGGER_GSOD = ["temp_c_mean", "precip_mm_day"]


def plan_venue_years(days: pd.DataFrame, venues: pd.DataFrame, end: pd.Timestamp, isd: pd.DataFrame,
                     sy: pd.DataFrame, listed: set | None, climate_venues=(), climate_from: int = CLIMATE_FROM,
                     k: int = N_CANDIDATES) -> dict:
    """(venue_id, year) -> candidates, the days to assemble (every day of a climatology year, else the
    match days), the match days, and the station-years a match day's local 00-24 h touches."""
    vt = venues.set_index("venue_id")
    d = days[days.venue_id.notna() & (days.date <= end)]
    by = {key: pd.DatetimeIndex(sorted(set(g))) for key, g in d.groupby([d.venue_id, d.date.dt.year]).date}
    keys = set(by) | {(v, y) for v in climate_venues if v in vt.index for y in range(climate_from, end.year + 1)}
    listed_years = {y for _, y in listed} if listed else set()
    plan = {}
    for v, y in sorted(keys):
        row = vt.loc[v]
        lst = listed if listed is not None and y in listed_years else None
        md = by.get((v, y), pd.DatetimeIndex([]))
        climate = v in climate_venues and y >= climate_from
        span = pd.date_range(f"{y}-01-01", min(pd.Timestamp(f"{y}-12-31"), end)) if climate else md
        years = {y} | {u for day in md for u in local_day_utc_years(day, row.utc_offset_hours)}
        years |= {y + 1} if any((x.month, x.day) == (12, 31) for x in md) else set()
        plan[(v, y)] = dict(cands=venue_year_candidates(row, y, end, isd, sy, lst, k), days=span, match_days=md,
                            climate=climate, years=sorted(u for u in years if u <= end.year),
                            offset=float(row.utc_offset_hours), dst=row.dst_region or "none")
    return plan


def venue_year_frame(p: dict, store: StationStore, k_isd: int = N_CANDIDATES, k_gsod: int = N_CANDIDATES):
    isd = [store.isd(s, p["offset"], p["dst"]) if i < k_isd else None for i, (s, _) in enumerate(p["cands"])]
    gsod = [store.gsod(s) if i < k_gsod else None for i, (s, _) in enumerate(p["cands"])]
    return assemble(p["days"], p["cands"], isd, gsod)


def round_jobs(plan: dict, store: StationStore, kind: str, k: int, pending: set,
               listed: set | None) -> tuple[list, set]:
    """Jobs for candidate k of every pending venue-year: in ISD-lite rounds the first candidate always, later
    ones when the frame from candidates < k lacks a TRIGGER_ISD field; in GSOD rounds when the frame from
    all ISD-lite candidates plus GSOD < k lacks a TRIGGER_GSOD field. Returns (jobs, still pending)."""
    jobs, still = [], set()
    listed_years = {y for _, y in listed} if listed else set()
    for key in sorted(pending):
        p = plan[key]
        if len(p["cands"]) <= k:
            continue
        if k > 0 or kind == "gsod":
            f = venue_year_frame(p, store, k, 0) if kind == "isd" else venue_year_frame(p, store, N_CANDIDATES, k)
            if not needs(f, p["match_days"], p["climate"], TRIGGER_ISD if kind == "isd" else TRIGGER_GSOD):
                continue
        still.add(key)
        st = p["cands"][k][0]
        for y in p["years"]:
            if kind == "isd" and (listed is None or y not in listed_years or (st, y) in listed):
                jobs.append((isd_lite_url(st, y), isd_lite_path(st, y, store.isd_root)))
            elif kind == "gsod":
                jobs.append((gsod_url(st, y), gsod_path(st, y, store.gsod_root)))
    return jobs, still


def venue_days(plan: dict, store: StationStore) -> pd.DataFrame:
    frames = []
    for (v, y), p in sorted(plan.items()):
        if not len(p["days"]):
            continue
        f = venue_year_frame(p, store).rename_axis("date").reset_index()
        f.insert(0, "venue_id", v)
        f["climate_year"] = p["climate"]
        frames.append(f)
    out = pd.concat(frames, ignore_index=True).drop(columns=["utc_offset", "elevation_m"])
    return out.drop_duplicates(["venue_id", "date"], keep="first")


def match_day_rows(days: pd.DataFrame, vdays: pd.DataFrame, venues: pd.DataFrame) -> pd.DataFrame:
    """Match-day long table: the venue-day fields on each (match, day), with the local UTC offset used."""
    out = days.merge(vdays.drop(columns="climate_year"), on=["venue_id", "date"], how="left")
    out["source"] = out.source.fillna("none")
    out["precip_source"] = out.precip_source.fillna("none")
    vt = venues.set_index("venue_id")
    off = {}
    for v, d in set(zip(out.venue_id, out.date)):
        if v in vt.index:
            off[(v, d)] = float(vt.at[v, "utc_offset_hours"]) + V.dst_shift(vt.at[v, "dst_region"], d)
    out["utc_offset"] = [off.get(k, np.nan) for k in zip(out.venue_id, out.date)]
    out["elevation_m"] = out.venue_id.map(vt.elevation_m).astype(float)
    return out


def load_match_days(path: Path | str = MATCH_DAY_PATH) -> pd.DataFrame:
    d = pd.read_parquet(path)
    d["date"] = pd.to_datetime(d.date)
    return d


# ---------------------------------------------------------------- outputs

def climate_days(rows: pd.DataFrame, cutoff_date=None) -> pd.DataFrame:
    """Distinct (venue_id, date) scheduled match days with any observed field, dated strictly before the
    cutoff (all when None), with the CLIMATE_FIELDS source columns and `month`."""
    d = rows[rows.scheduled.astype(bool) & rows.venue_id.notna()]
    d = d.assign(date=pd.to_datetime(d.date))
    if cutoff_date is not None:
        d = d[d.date < pd.Timestamp(cutoff_date)]
    d = d[d.source.ne("none") | d.precip_mm_day.notna() | d.wet_day.notna()]
    d = d.sort_values(["venue_id", "date", "match_id"]).drop_duplicates(["venue_id", "date"])
    return d.assign(month=d.date.dt.month, rain_mm=d.precip_mm_day.where(d.precip_mm_day >= WET_MM))


def _sums(x: pd.DataFrame, keys: list[str], fields: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = x.groupby(keys)[fields]
    return g.sum(), g.count()


def _shrink(s: pd.DataFrame, n: pd.DataFrame, prior: pd.DataFrame, k: pd.Series) -> pd.DataFrame:
    s, n = s.reindex(prior.index).fillna(0.0), n.reindex(prior.index).fillna(0.0)
    return (s + k * prior) / (n + k)


_HX = np.c_[np.ones(12), np.cos(np.arange(1, 13) * np.pi / 6), np.sin(np.arange(1, 13) * np.pi / 6)]


def seasonal_prior(s: pd.DataFrame, n: pd.DataFrame, parent: pd.DataFrame, lam: float = HARM_RIDGE,
                   min_months: int = HARM_MIN_MONTHS) -> pd.DataFrame:
    """Per group (first index level; 12 months each, in order) and field: the day-weighted first annual
    harmonic of the group's month means, its cosine and sine terms ridge-penalised with `lam` days toward
    those of the parent's curve (the parent's seasonal shape unless the group's data say otherwise), where
    the group has data in at least `min_months` months; elsewhere the parent's values."""
    s, n = s.reindex(parent.index).fillna(0.0), n.reindex(parent.index).fillna(0.0)
    G = len(parent) // 12
    S, N, out = (a.to_numpy(float).reshape(G, 12, -1) for a in (s, n, parent.copy()))
    pen = np.diag([0.0, lam, lam])
    for g in range(G):
        for j in range(S.shape[2]):
            w = N[g, :, j]
            ok = w > 0
            if ok.sum() < min_months or np.isnan(out[g, :, j]).any():
                continue
            X, wy = _HX[ok], S[g, ok, j]
            shape = np.linalg.lstsq(_HX, out[g, :, j], rcond=None)[0]
            beta = np.linalg.solve(X.T @ (X * w[ok, None]) + pen, X.T @ wy + pen @ shape)
            out[g, :, j] = _HX @ beta
    return pd.DataFrame(out.reshape(G * 12, -1), parent.index, parent.columns)


def climatology(cutoff_date=None, rows: pd.DataFrame | None = None, venues: pd.DataFrame | None = None,
                k: float | dict | None = None, fill: bool = True) -> pd.DataFrame:
    """Venue x calendar-month climatology from scheduled match days strictly before `cutoff_date` (None =
    all days), the only data it touches, so it is leakage-free for matches on or after the cutoff.
    fill=True: every venue in `venues` x 12 months, fields shrunk through the hierarchy in the module
    docstring, `clim_level` the lowest level with data and `n`, `n_precip`, `n_cloud` the venue-month's own
    day counts. fill=False: only observed venue-months, raw means. `rows` defaults to the match-day table."""
    rows = load_match_days() if rows is None else rows
    venues = V.load_venues() if venues is None else venues
    d = climate_days(rows, cutoff_date)
    vt = venues.set_index("venue_id")
    fields = list(CLIMATE_FIELDS)
    k = pd.Series(CLIM_K if k is None else k if isinstance(k, dict) else dict.fromkeys(fields, float(k)))[fields]
    x = pd.DataFrame({f: d[c].to_numpy(float) for f, c in CLIMATE_FIELDS.items()}, index=d.index)
    x["venue_id"], x["month"] = d.venue_id.to_numpy(), d.month.to_numpy()
    region, country = vt.region.fillna("other"), vt.cricket_country.fillna("")
    x["region"] = x.venue_id.map(region).fillna("other").to_numpy()
    x["country"] = (x.region + "|" + x.venue_id.map(country).fillna("")).to_numpy()
    if not fill:
        s, n = _sums(x, ["venue_id", "month"], fields)
        out = (s / n.where(n > 0)).assign(n=n.temp_c, n_precip=n.rain_day_freq, n_cloud=n.cloud_oktas)
        return _clip(out).reset_index()
    months = pd.Index(range(1, 13), name="month")
    ids = pd.Index(venues.venue_id, name="venue_id")
    reg = pd.Series(sorted(set(region) | set(x.region)))
    cty = pd.Series(sorted(set(region + "|" + country) | set(x.country)))
    grid = lambda keys, name: pd.MultiIndex.from_product([keys, months], names=[name, "month"])
    up = lambda prior, parent, idx: prior.reindex(pd.MultiIndex.from_arrays([parent, idx.get_level_values(1)]))
    tot_n = x[fields].count()
    glob = (x[fields].sum() / tot_n.where(tot_n > 0)).to_numpy()[None, :]
    gm = _shrink(*_sums(x, ["month"], fields), pd.DataFrame(np.repeat(glob, 12, 0), months, fields), k)
    ri = grid(reg, "region")
    sr, nr = _sums(x, ["region", "month"], fields)
    rm = _shrink(sr, nr, seasonal_prior(sr, nr, gm.reindex(ri.get_level_values(1)).set_axis(ri)), k)
    ci = grid(cty, "country")
    cparent = ci.get_level_values(0).str.split("|").str[0]
    sc, nc = _sums(x, ["country", "month"], fields)
    cm = _shrink(sc, nc, seasonal_prior(sc, nc, up(rm, cparent, ci).set_axis(ci)), k)
    base = cm.reindex(pd.MultiIndex.from_arrays([x.country, x.month])).set_axis(x.index)
    resid = x[fields] - base
    offset = resid.groupby(x.venue_id).sum().reindex(ids).fillna(0.0) / \
        (resid.groupby(x.venue_id).count().reindex(ids).fillna(0.0) + k)
    vi = grid(ids, "venue_id")
    vid = vi.get_level_values(0)
    vprior = up(cm, vid.map(region + "|" + country), vi).set_axis(vi) + offset.reindex(vid).set_axis(vi)
    s, n = _sums(x, ["venue_id", "month"], fields)
    out = _clip(_shrink(s, n, seasonal_prior(s, n, vprior), k))
    n = n.reindex(vi).fillna(0).astype(int)
    out["n"], out["n_precip"], out["n_cloud"] = n.temp_c, n.rain_day_freq, n.cloud_oktas
    has = lambda key, by: np.asarray(pd.Series(key).map(x.groupby(by).size()).fillna(0) > 0)
    out["clim_level"] = np.select(
        [out.n.gt(0) | out.n_precip.gt(0), has(vid, "venue_id"), has(vid.map(region + "|" + country), "country"),
         has(vid.map(region), "region"), np.full(len(vi), len(x) > 0)],
        ["venue_month", "venue", "country", "region", "global"], "none")
    return out.reset_index()


def _clip(c: pd.DataFrame) -> pd.DataFrame:
    for f, (lo, hi) in CLIMATE_RANGE.items():
        if f in c:
            c[f] = c[f].clip(lo, hi)
    return c


DAY_TO_CLIMATE = {c: f for f, c in CLIMATE_FIELDS.items() if c != "rain_mm"}


def impute(frame: pd.DataFrame, clim: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Fill missing day/match fields (temp_c_mean, rh_mean, ...) from a filled climatology by venue_id and
    the month of `date` (or `start_date`), adding `<col>_missing` 0/1 flags."""
    cols = [c for c in (cols or DAY_TO_CLIMATE) if c in frame]
    month = pd.to_datetime(frame["date"] if "date" in frame else frame["start_date"]).dt.month
    c = clim.set_index(["venue_id", "month"])
    look = c.reindex(pd.MultiIndex.from_arrays([frame.venue_id, month]))
    out = frame.copy()
    for col in cols:
        miss = out[col].isna().to_numpy()
        out[f"{col}_missing"] = miss.astype("int8")
        out.loc[miss, col] = look[DAY_TO_CLIMATE[col]].to_numpy(float)[miss]
    return out


def climate_json(clim: pd.DataFrame, venues: pd.DataFrame, meta: dict) -> dict:
    """Compact page file: per venue, 12-value arrays (January first; null where no value) and the level."""
    st = venues.set_index("venue_id")
    fields = list(CLIMATE_FIELDS) + ["n", "n_precip", "n_cloud"]
    nd = {"temp_c": 1, "rh": 0, "dewpt_c": 1, "dew_depression_evening": 1, "cloud_oktas": 1, "wind_ms": 1,
          "precip_mm": 1, "rain_day_freq": 3, "precip_mm_rain_day": 1}
    out = {}
    for vid, g in clim.groupby("venue_id"):
        g = g.set_index("month").reindex(range(1, 13))
        row = {"name": st.at[vid, "name"], "region": st.at[vid, "region"]}
        for f in fields:
            if f not in g:
                continue
            vals = g[f].to_numpy(float)
            row[f] = [None if np.isnan(x) else (int(x) if f.startswith("n") and f not in nd else round(float(x), nd[f]))
                      for x in vals]
        if "clim_level" in g:
            row["level"] = [None if pd.isna(x) else x for x in g.clim_level]
        out[vid] = row
    return dict(meta, venues=out)


def match_summary(day_rows: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Compact match-level table: means over scheduled days (precipitation also summed), wet-day count."""
    s = day_rows[day_rows.scheduled]
    has = s.source.ne("none")
    s = s.assign(has=has, rain_mm=s.precip_mm_day)
    num = ["temp_c_mean", "rh_mean", "dewpt_c_mean", "dew_depression_evening", "cloud_oktas_mean",
           "precip_mm_day", "precip_hours", "wind_ms_mean", "pressure_hpa_mean"]
    g = s.groupby("match_id")
    out = g[num].mean()
    out["precip_mm_total"] = g.rain_mm.sum(min_count=1)
    out["wet_days"] = g.wet_day.sum(min_count=1)
    out["wet_day_share"] = g.wet_day.mean()
    out["rain_flag_share"] = g.rain_flag.mean()
    out["rain_flag_days"] = g.rain_flag.sum(min_count=1)
    out["thunder_days"] = g.thunder_flag.sum(min_count=1)
    out["n_obs"] = g.n_obs.sum(min_count=1)
    out["days_with_weather"] = g.has.sum()
    out["days_with_precip"] = g.precip_mm_day.count()
    out["station"] = g.station.agg(lambda x: x.mode().iloc[0] if x.notna().any() else None)
    out["distance_km"] = g.distance_km.mean()
    if "elevation_m" in s:
        out["elevation_m"] = g.elevation_m.first()
    src = s.groupby("match_id").source.agg(lambda x: "isd_lite" if (x == "isd_lite").any()
                                           else ("gsod" if (x == "gsod").any() else "none"))
    out["source"] = src
    m = matches.set_index("match_id")[[c for c in MATCH_KEYS if c in matches]]
    out = m.join(out, how="left")
    out["source"] = out.source.fillna("none")
    out["days_with_weather"] = out.days_with_weather.fillna(0).astype(int)
    out["days_with_precip"] = out.days_with_precip.fillna(0).astype(int)
    rnd = {"temp_c_mean": 1, "rh_mean": 1, "dewpt_c_mean": 1, "dew_depression_evening": 1, "cloud_oktas_mean": 2,
           "precip_mm_day": 2, "precip_mm_total": 1, "precip_hours": 2, "wind_ms_mean": 2, "pressure_hpa_mean": 1,
           "distance_km": 1, "wet_day_share": 3, "rain_flag_share": 3}
    return out.round(rnd).reset_index()


RAIN_METHODS = {"D/L", "DLS", "VJD"}
CHECK_VENUES = ["wankhede_stadium", "eden_gardens", "chepauk", "chinnaswamy_stadium", "arun_jaitley_stadium",
                "premadasa_stadium", "lords", "old_trafford", "headingley", "edgbaston", "mcg", "kensington_oval"]


def _share(m: pd.DataFrame, by) -> dict:
    g = m.groupby(by)
    out = pd.DataFrame(dict(n=g.size(), weather=g.has_weather.mean().round(4), precip=g.has_precip.mean().round(4),
                            cloud=g.has_cloud.mean().round(4)))
    out.index = ["|".join(map(str, k)) if isinstance(k, tuple) else str(k) for k in out.index]
    return out.to_dict("index")


def _group_stats(x: pd.DataFrame) -> dict:
    p = x.precip_mm_day.dropna()
    return dict(n=int(len(x)), n_precip=int(len(p)), precip_mm_mean=round(float(p.mean()), 2) if len(p) else None,
                precip_mm_median=round(float(p.median()), 2) if len(p) else None,
                wet_day_share=round(float(x.wet_day.mean()), 3) if x.wet_day.notna().any() else None,
                rain_flag_share=round(float(x.rain_flag.mean()), 3) if x.rain_flag.notna().any() else None,
                precip_hours_mean=round(float(x.precip_hours.mean()), 2) if x.precip_hours.notna().any() else None)


def _diff(a: pd.Series, b: pd.Series) -> dict:
    a, b = a.dropna(), b.dropna()
    if len(a) < 2 or len(b) < 2:
        return {}
    d, se = a.mean() - b.mean(), np.sqrt(a.var() / len(a) + b.var() / len(b))
    return dict(diff=round(float(d), 3), se=round(float(se), 3), z=round(float(d / se), 1) if se > 0 else None)


def _by_month(d: pd.DataFrame) -> dict:
    g = d.groupby("month")
    f = lambda s: [None if pd.isna(y) else round(float(y), 2) for y in s.reindex(range(1, 13))]
    return dict(temp_c=f(g.temp_c_mean.mean()), rh=f(g.rh_mean.mean()), rain_day_freq=f(g.wet_day.mean()),
                precip_mm=f(g.precip_mm_day.mean()), cloud_oktas=f(g.cloud_oktas_mean.mean()),
                n=[int(x) for x in g.temp_c_mean.count().reindex(range(1, 13)).fillna(0)])


def _mean(x: pd.Series, nd: int = 3):
    return round(float(x.mean()), nd) if x.notna().any() else None


def sanity_checks(summary: pd.DataFrame, matches: pd.DataFrame, rows: pd.DataFrame, venues: pd.DataFrame) -> dict:
    """Precipitation by outcome (no result and D/L/VJD vs completed limited-overs matches: both must be
    wetter, z > 2, for `passed`; Test draws vs results), rain flag vs amount agreement, and match-day
    monthly means at reference venues, Indian venues (monsoon) and English venues (summer)."""
    m = matches.merge(summary.drop(columns=[c for c in MATCH_KEYS if c in summary]), on="match_id")
    m = m[m.source.ne("none") | m.days_with_precip.gt(0)]
    m = m.assign(wet_day=m.wet_day_share, rain_flag=m.rain_flag_share)
    lo = m[m.fam.isin(["T20", "HUNDRED", "ODI"])]
    grp = np.where(lo.result.isin(["no_result", "no result"]), "no_result",
                   np.where(lo.method.isin(RAIN_METHODS), "dl_vjd", np.where(lo.method.isna(), "completed", "other")))
    out = dict(limited_overs={k: _group_stats(lo[grp == k]) for k in ("no_result", "dl_vjd", "completed", "other")})
    ok = []
    for k in ("no_result", "dl_vjd"):
        for f, col in (("precip_mm", "precip_mm_day"), ("wet_day", "wet_day")):
            d = _diff(lo[col][grp == k].clip(upper=1 if f == "wet_day" else None), lo[col][grp == "completed"]
                      .clip(upper=1 if f == "wet_day" else None))
            out["limited_overs"][f"{k}_minus_completed_{f}"] = d
            ok.append(bool(d) and d["diff"] > 0 and (d["z"] or 0) > 2)
    out["limited_overs"]["passed"] = all(ok)
    tw = m[m.fam.eq("TEST")]
    out["tests"] = {k: _group_stats(tw[tw.result.eq("draw") == (k == "draw")]) for k in ("draw", "result")}
    out["tests"]["draw_minus_result_precip_mm"] = _diff(tw.precip_mm_day[tw.result.eq("draw")],
                                                        tw.precip_mm_day[tw.result.ne("draw")])
    d = climate_days(rows)
    both = d[d.precip_source.ne("none") & d.rain_flag.notna()]
    out["rain_flag_vs_amount"] = dict(
        n_days=int(len(both)), flag_given_ge1mm=_mean(both.rain_flag[both.precip_mm_day >= WET_MM]),
        flag_given_0mm=_mean(both.rain_flag[both.precip_mm_day == 0]),
        ge1mm_given_flag=_mean((both.precip_mm_day[both.rain_flag == 1] >= WET_MM).astype(float)))
    vt = venues.set_index("venue_id")
    d = d.assign(country=d.venue_id.map(vt.cricket_country))
    out["reference_venues_by_month"] = {v: _by_month(d[d.venue_id.eq(v)]) for v in CHECK_VENUES
                                        if d.venue_id.eq(v).any()}
    india = d[d.country.eq("India")]
    wet, dry = india[india.month.between(6, 9)], india[india.month.isin([11, 12, 1, 2, 3])]
    out["india_monsoon"] = dict(jun_sep_days=int(len(wet)), nov_mar_days=int(len(dry)),
                                jun_sep_rain_day_freq=_mean(wet.wet_day), nov_mar_rain_day_freq=_mean(dry.wet_day),
                                jun_sep_rh=_mean(wet.rh_mean, 1), nov_mar_rh=_mean(dry.rh_mean, 1),
                                n_venues=int(india.venue_id.nunique()))
    im = out["india_monsoon"]
    im["plausible"] = None if min(len(wet), len(dry)) < 20 or None in (im["jun_sep_rain_day_freq"],
                                                                     im["nov_mar_rain_day_freq"]) else \
        bool(im["jun_sep_rain_day_freq"] > 2 * im["nov_mar_rain_day_freq"] and im["jun_sep_rh"] > im["nov_mar_rh"])
    eng = d[d.country.eq("England")]
    summer = eng[eng.month.between(5, 9)]
    out["english_summer"] = dict(may_sep_days=int(len(summer)), may_sep_temp_c=_mean(summer.temp_c_mean, 1),
                                 may_sep_rh=_mean(summer.rh_mean, 1), may_sep_rain_day_freq=_mean(summer.wet_day),
                                 may_sep_cloud_oktas=_mean(summer.cloud_oktas_mean, 2),
                                 jul_temp_c=_mean(eng.temp_c_mean[eng.month.eq(7)], 1),
                                 apr_temp_c=_mean(eng.temp_c_mean[eng.month.eq(4)], 1),
                                 n_venues=int(eng.venue_id.nunique()))
    es = out["english_summer"]
    es["plausible"] = None if not len(summer) else bool(13 <= es["may_sep_temp_c"] <= 22
                                                        and 0.2 <= es["may_sep_rain_day_freq"] <= 0.6)
    return out


def coverage_report(matches: pd.DataFrame, rows: pd.DataFrame, summary: pd.DataFrame, venues: pd.DataFrame,
                    end: pd.Timestamp) -> dict:
    """Share of matches with weather by year / format / region, sources, station distances, field-level
    missingness on scheduled match days."""
    vt = venues.set_index("venue_id")
    s = rows[rows.scheduled]
    g = s.assign(h=s.source.ne("none"), p=s.precip_mm_day.notna() | s.wet_day.notna(),
                 c=s.cloud_oktas_mean.notna()).groupby("match_id")
    m = matches.assign(year=matches.start_date.str[:4].astype(int),
                       region=matches.venue_id.map(vt.region).fillna("unmapped"),
                       has_weather=matches.match_id.map(g.h.any()).fillna(False).astype(bool),
                       has_precip=matches.match_id.map(g.p.any()).fillna(False).astype(bool),
                       has_cloud=matches.match_id.map(g.c.any()).fillna(False).astype(bool))
    upto = m.start_date <= str(end.date())
    sd = s[s.date <= end]
    w = sd[sd.source.ne("none")]
    fields = ["temp_c_mean", "rh_mean", "dewpt_c_mean", "dew_depression_evening", "cloud_oktas_mean",
              "precip_mm_day", "precip_hours", "wet_day", "rain_flag", "wind_ms_mean", "pressure_hpa_mean"]
    dist = w.distance_km
    return dict(
        isd_data_end=str(end.date()), n_matches=int(len(m)), n_matches_to_data_end=int(upto.sum()),
        after_data_end=dict(
            n_matches=int((~upto).sum()), n_with_weather=int(m.has_weather[~upto].sum()),
            first=min(m.start_date[~upto], default=None), last=max(m.start_date[~upto], default=None),
            note=f"NOAA's AWS ISD-lite and GSOD buckets end on {end.date()} (the 2026 prefixes are empty): later "
                 "match days have source 'none' and no observed weather; models and the page use climatology."),
        n_unmapped_venue=int(m.venue_id.isna().sum()),
        n_scheduled_match_days=int(len(s)), n_scheduled_match_days_to_data_end=int(len(sd)),
        match_share_with_weather=dict(all=round(float(m.has_weather.mean()), 4),
                                      to_data_end=round(float(m.has_weather[upto].mean()), 4),
                                      precip_to_data_end=round(float(m.has_precip[upto].mean()), 4),
                                      cloud_to_data_end=round(float(m.has_cloud[upto].mean()), 4)),
        by_year=_share(m, "year"), by_format=_share(m, ["fam", "gender"]), by_match_type=_share(m, "match_type"),
        by_region=_share(m[upto], "region"),
        day_source=sd.source.value_counts().to_dict(), precip_source=sd.precip_source.value_counts().to_dict(),
        station_rank=w.station_rank.value_counts().sort_index().rename(lambda k: str(int(k))).to_dict(),
        station_distance_km=dict(
            quantiles={str(q): round(float(dist.quantile(q)), 1) for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99)},
            bins=pd.cut(dist, [0, 5, 10, 20, 30, 45, 60.01], right=False).value_counts().sort_index()
            .rename(lambda k: f"{k.left:g}-{k.right:g}").to_dict()),
        cloud_from_other_station=round(float((w.cloud_station.notna() & w.cloud_station.ne(w.station)).mean()), 4),
        field_missing_share=dict(
            all_days_to_data_end={f: round(float(sd[f].isna().mean()), 4) for f in fields},
            days_with_weather={f: round(float(w[f].isna().mean()), 4) for f in fields}),
        scheduled_days_source=matches.scheduled_source.value_counts().to_dict(),
    )


def clean_json(x):
    """NaN/inf -> None and numpy scalars -> Python, recursively, for strict JSON."""
    if isinstance(x, dict):
        return {str(k): clean_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean_json(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x
