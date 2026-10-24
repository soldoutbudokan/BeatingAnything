"""Venue canonicalisation, coordinates, NOAA ISD station matching, local time and the default Test ball.

`config/cricket-venues.csv` holds one row per ground: `venue_id` (slug), display `name`, pipe-separated
`aliases`, location (`city`, `country`, `cricket_country`, `region`, `lat`, `lon`, `coord_confidence`,
`elevation_m`), time (`utc_offset_hours` at standard time plus a `dst_region` rule), `ball_brand_default`,
the matched ISD stations and the venue's Cricsheet match count and date range. Each alias is a Cricsheet
`venue` string qualified by the Cricsheet `city` it appeared with, written `venue @ city` (`venue @` when
Cricsheet gave no city). Qualifying every alias is what keeps the six 'County Ground's, the two 'Queen's
Park's and the two 'National Stadium's apart. `venue_id_for(venue, city)` looks up the
whitespace-normalised pair exactly. For an unseen pair it falls back to the venue string alone only when
that string belongs to one ground and the city is blank or one that ground is already known by; anything
else raises KeyError, so new Cricsheet grounds get curated rather than guessed.

Grouping was curated by hand from all (venue, city) pairs in Cricsheet using city, teams, event and
dates: city-suffix and spelling variants, sponsor renames (Westpac Stadium -> Sky Stadium, Goodyear Park
-> Mangaung Oval), same-site renames or rebuilds (Feroz Shah Kotla -> Arun Jaitley Stadium, Sardar Patel
-> Narendra Modi Stadium) and historic names Cricsheet uses for a current ground (Racecourse Ground,
Derby; Royal Brunswick and New County Ground, Hove) share an id. Cricsheet city strings that name the
same place differently (Hove/Brighton, Chittagong/Chattogram, Port Elizabeth/Gqeberha, Mohali/New
Chandigarh) do not split a ground. Separate fields of one complex (Alur I/II/III, ICC Academy Ovals 1/2,
Willowmoore A/B/C) keep their own ids. A string that does not say which field it means goes to the main
field when one is clearly meant ('ICC Academy' and 'ICC Global Cricket Academy' -> ICC Academy Oval 1,
'Alur Cricket Stadium' -> Alur I) and otherwise keeps its own id ('KSCA Cricket Ground, Alur'). Each
merge's reason is in `notes`, the per-alias trail in `data/derived/cricket/venue_aliases_audit.csv`.

Coordinates come from the curator's knowledge of each ground, not from a survey or geocoder: `high`
is the ground itself (about 1 km), `medium` the suburb or complex (1-5 km), `low` the town. That is
enough to choose a weather station, not for anything finer. Elevation is curated where altitude matters
or the station is unrepresentative (Highveld, Harare, Nairobi, Dharamsala, upland English airfields)
and otherwise copied from the station that best represents the site, ranked as below but on BEGIN..END
cover (50 km per unit) instead of file sizes, so a primary chosen farther away for its data does not
move the venue's height; isd-history heights can themselves be wrong.

Stations: every ISD station within 60 km (haversine) is a candidate. isd-history's BEGIN..END says when
a station reported at all, not how much, so the decision uses the ISD-lite station-year file sizes from
the AWS bucket listing (cached for every candidate in `data/derived/cricket/isd_station_years.csv`, in
kB). A station is usable on a day inside its BEGIN..END when that year's file holds at least 15 kB (about
1,800 observations) pro rata to the share of the year BEGIN..END covers. Candidates are ranked by an
effective distance `d + 100 km * (1 - share of the venue's match days the station is usable on) + 5 km
without an ICAO code + 0.05 km per metre of height difference beyond 100 m` (height against the curated
elevation, else the candidates' median; it keeps mountain stations such as Mt Wellington above Hobart
out). The best is `isd_station` (USAF-WBAN), the next three `isd_station_alts`; `station_data_cover` and
`alts_data_cover` are the shares of match days covered by the primary and by the primary or an alternate.
The NOAA mirror stops at `isd_data_end()` (the modal END in isd-history, 2025-08-24 for the current
files): later match days are left out of the shares since no station has them, and a venue with no
earlier match is ranked on its match dates moved back one to three years. `stations_on(venue_id, date)`
re-ranks for one date and returns only stations with data that day (usable first, then thin files), so
it is empty after the data end, where weather code must fall back to climatology. A station missing
from the cache falls back to BEGIN..END. ISD's country code (mostly FIPS 10-4, sometimes ISO alpha-2) of
the chosen and the nearest station is checked against the venue country; mismatches, venues with no
station and venues whose primary and alternates cover under 80% of match days go to `station_flag`.

`ball_brand_default` is derived from `cricket_country` on every refresh: Dukes in England (with Wales),
Ireland (with Northern Ireland), Scotland and the West Indies, SG in India, Kookaburra elsewhere. It is
the Test default only; exceptions such as Afghanistan's home Tests in India or the year the West Indies
took up the Dukes ball belong in the rules timeline or at series level.

`dst_shift` implements the civil daylight-saving rules that touch matches in the data (EU, North
America with its 2007 change, south-east Australia and New Zealand with their 2007-08 changes, the 2006
Commonwealth Games extension, Tasmania's early October start from 2001, Western Australia's 2006-09
trial, Mexico until 2022, Samoa 2010-21, Fiji approximately, Namibian winter time until 2017, Pakistan
2008-09, Bangladesh 2009, Sri Lanka at UTC+6 before April 2006), resolved to the day: a match on a
changeover day gets the new offset all day.

Run `python -m beating.cricket.venues` to refresh match counts, stations, elevations and ball brands in
the config and rewrite the audit from the Cricsheet zip (about 15 s; it reads only each file's info
block). `--list-isd-lite` relists the bucket first (about 330 requests, a minute); otherwise the raw
listing `data/raw/noaa/isd-lite-sizes.csv` or, failing that, the committed cache is used.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from functools import lru_cache
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import urlopen
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "cricket-venues.csv"
AUDIT = ROOT / "data" / "derived" / "cricket" / "venue_aliases_audit.csv"
STATION_YEARS = ROOT / "data" / "derived" / "cricket" / "isd_station_years.csv"
CRICSHEET_ZIP = ROOT / "data" / "raw" / "cricsheet" / "all_json.zip"
ISD_HISTORY = ROOT / "data" / "raw" / "noaa" / "isd-history.csv"
ISD_LITE_SIZES = ROOT / "data" / "raw" / "noaa" / "isd-lite-sizes.csv"
ISD_LITE_BUCKET = "https://noaa-isd-pds.s3.amazonaws.com/"
MAX_KM = 60.0
COVER_PENALTY_KM = 100.0
SITE_COVER_KM = 50.0
NO_ICAO_PENALTY_KM = 5.0
ELEV_FREE_M = 100.0
ELEV_PENALTY_KM_PER_M = 0.05
USABLE_KB = 15.0  # a full station-year file this large holds about 1,800 observations
MIN_YEAR_SHARE = 0.1
LOW_COVER = 0.8
REGIONS = ("subcontinent", "sena_eng", "sena_aus", "sena_nz", "sena_sa", "west_indies", "uae_gulf", "other")
BALL_BRANDS = {"England": "dukes", "Ireland": "dukes", "Scotland": "dukes", "West Indies": "dukes", "India": "sg"}
DST_REGIONS = ("none", "eu", "us", "mx", "au_south", "au_tas", "wa", "nz", "ws", "fj", "na", "pk", "bd", "lk")
NUMERIC_COLS = ("lat", "lon", "elevation_m", "utc_offset_hours", "station_distance_km", "station_data_cover",
                "alts_data_cover", "n_matches")
COLUMNS = ["venue_id", "name", "aliases", "city", "country", "cricket_country", "region", "lat", "lon",
           "coord_confidence", "elevation_m", "elevation_source", "utc_offset_hours", "dst_region",
           "ball_brand_default", "isd_station", "isd_station_name", "isd_station_alts", "station_distance_km",
           "station_data_cover", "alts_data_cover", "station_country", "station_flag", "n_matches",
           "first_match", "last_match", "notes"]

# ISD CTRY is mostly FIPS 10-4, but some stations carry ISO alpha-2 codes (AU, ZA, BD, EE...), British
# ones also appear as GB and the Hong Kong Observatory as CH, so each venue country accepts all of them.
COUNTRY_CODES = {k: set(v.split()) for k, v in {
    "United Arab Emirates": "AE TC", "Oman": "MU OM", "Qatar": "QA", "Kuwait": "KU KW", "Pakistan": "PK",
    "India": "IN", "Bangladesh": "BG BD", "Sri Lanka": "CE LK", "Nepal": "NP", "Bhutan": "BT",
    "Australia": "AS AU", "New Zealand": "NZ", "South Africa": "SF ZA", "Zimbabwe": "ZI ZW", "Namibia": "WA NA",
    "Kenya": "KE", "Uganda": "UG", "Rwanda": "RW", "Tanzania": "TZ", "Nigeria": "NI NG", "Ghana": "GH",
    "Botswana": "BC BW", "Malawi": "MI MW", "Eswatini": "WZ SZ", "Antigua and Barbuda": "AC AG",
    "Barbados": "BB", "Dominica": "DO DM", "Grenada": "GJ GD", "Guyana": "GY", "Jamaica": "JM",
    "Saint Kitts and Nevis": "SC KN", "Saint Lucia": "ST LC", "Saint Vincent and the Grenadines": "VC",
    "Trinidad and Tobago": "TD TT", "Cayman Islands": "CJ KY", "Bermuda": "BD BM", "United States": "US",
    "Canada": "CA", "Panama": "PM PA", "Costa Rica": "CS CR", "Mexico": "MX", "Argentina": "AR", "Brazil": "BR",
    "Colombia": "CO", "Malaysia": "MY", "Singapore": "SN SG", "Thailand": "TH", "Hong Kong": "HK CH",
    "China": "CH CN", "Japan": "JA JP", "South Korea": "KS KR", "Indonesia": "ID", "Philippines": "RP PH",
    "Cambodia": "CB KH", "Papua New Guinea": "PP PG", "Vanuatu": "NH VU", "Samoa": "WS", "Fiji": "FJ",
    "New Caledonia": "NC", "England": "UK GB", "Wales": "UK GB", "Scotland": "UK GB",
    "Northern Ireland": "UK GB", "Ireland": "EI IE", "Jersey": "UK JE", "Guernsey": "UK GK GG",
    "Netherlands": "NL", "Denmark": "DA DK", "Germany": "GM DE", "Belgium": "BE", "France": "FR",
    "Spain": "SP ES", "Portugal": "PO PT", "Italy": "IT", "Austria": "AU AT", "Czech Republic": "EZ CZ",
    "Hungary": "HU", "Croatia": "HR", "Serbia": "RI SR RS", "Bulgaria": "BU BG", "Romania": "RO",
    "Greece": "GR", "Cyprus": "CY", "Malta": "MT", "Gibraltar": "GI UK", "Luxembourg": "LU",
    "Sweden": "SW SE", "Norway": "NO", "Finland": "FI", "Estonia": "EN EE",
}.items()}


def norm(s) -> str:
    return "" if s is None or (not isinstance(s, str) and pd.isna(s)) else " ".join(str(s).split())


def alias_key(venue, city) -> str:
    return f"{norm(venue)} @ {norm(city)}".rstrip()


def parse_alias(a: str) -> tuple[str, str]:
    v, _, c = a.rpartition(" @")
    return norm(v), norm(c)


def ball_brand_default(cricket_country) -> str:
    return BALL_BRANDS.get(norm(cricket_country), "kookaburra")


def _mtime(path) -> int:
    return Path(path).stat().st_mtime_ns


def load_venues(path: Path | str = CONFIG) -> pd.DataFrame:
    return _load(str(path), _mtime(path)).copy()


@lru_cache(maxsize=4)
def _load(path: str, mtime: int) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, na_values={k: [""] for k in NUMERIC_COLS})


def alias_pairs(venues: pd.DataFrame) -> pd.DataFrame:
    """Long table (venue_id, venue, city) of every alias; raises if a pair maps to two venues."""
    rows = [(vid, *parse_alias(a)) for vid, als in zip(venues.venue_id, venues.aliases)
            for a in str(als).split("|") if a.strip()]
    out = pd.DataFrame(rows, columns=["venue_id", "venue", "city"])
    dup = out[out.duplicated(["venue", "city"], keep=False)]
    if not dup.empty:
        raise ValueError(f"aliases mapped to more than one venue: {dup.values.tolist()}")
    return out


@lru_cache(maxsize=4)
def _lookup(path: str, mtime: int):
    df = _load(path, mtime)
    pairs = alias_pairs(df)
    exact = dict(zip(zip(pairs.venue, pairs.city), pairs.venue_id))
    by_venue = pairs.groupby("venue").venue_id.agg(set).to_dict()
    cities = pairs.groupby("venue_id").city.agg(set).to_dict()
    for vid, city in zip(df.venue_id, df.city):
        cities.setdefault(vid, set()).add(norm(city))
    return exact, by_venue, cities


def venue_id_for(venue_raw, city=None, path: Path | str = CONFIG) -> str:
    exact, by_venue, cities = _lookup(str(path), _mtime(path))
    v, c = norm(venue_raw), norm(city)
    if (v, c) in exact:
        return exact[(v, c)]
    ids = by_venue.get(v, set())
    if len(ids) == 1 and (not c or c in cities[next(iter(ids))]):
        return next(iter(ids))
    raise KeyError(f"unknown Cricsheet venue {venue_raw!r} (city {city!r}); curate it in {Path(path).name}")


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(np.subtract(lon2, lon1)) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def load_isd_history(path: Path | str = ISD_HISTORY) -> pd.DataFrame:
    return _isd(str(path), _mtime(path)).copy()


@lru_cache(maxsize=2)
def _isd(path: str, mtime: int) -> pd.DataFrame:
    h = pd.read_csv(path, dtype=str, keep_default_na=False)
    h = h.rename(columns={"STATION NAME": "name", "CTRY": "ctry", "ICAO": "icao", "ELEV(M)": "elev"})
    h["lat"], h["lon"] = pd.to_numeric(h.LAT, errors="coerce"), pd.to_numeric(h.LON, errors="coerce")
    h["elev"] = pd.to_numeric(h.elev, errors="coerce").where(lambda e: e > -400)
    h["begin"], h["end"] = pd.to_numeric(h.BEGIN, errors="coerce"), pd.to_numeric(h.END, errors="coerce")
    h["begin_day"] = pd.to_datetime(h.BEGIN, format="%Y%m%d", errors="coerce")
    h["end_day"] = pd.to_datetime(h.END, format="%Y%m%d", errors="coerce")
    h["station"] = h.USAF + "-" + h.WBAN
    h = h[h.lat.notna() & h.lon.notna() & ~((h.lat == 0) & (h.lon == 0)) & h.begin_day.notna() & h.end_day.notna()]
    h = h.drop_duplicates("station")
    return h[["station", "name", "ctry", "icao", "lat", "lon", "elev", "begin", "end", "begin_day",
              "end_day"]].reset_index(drop=True)


def isd_data_end(isd: pd.DataFrame | None = None) -> pd.Timestamp:
    """Last day of the NOAA mirror: the most common END among stations that reported in its last 30 days."""
    isd = load_isd_history() if isd is None else isd
    e = isd.end_day[isd.end_day >= isd.end_day.max() - pd.Timedelta(days=30)]
    return e.mode().max()


def list_isd_lite_sizes(years, base: str = ISD_LITE_BUCKET) -> pd.DataFrame:
    """(station, year, bytes) of every ISD-lite station-year file, from the public bucket's paged listing."""
    rows = []
    for y in years:
        token = None
        while True:
            q = {"list-type": "2", "prefix": f"isd-lite/data/{y}/"} | ({"continuation-token": token} if token else {})
            x = _get(f"{base}?{urlencode(q)}")
            rows += [(s, int(y), int(n)) for s, n in re.findall(
                r"<Key>isd-lite/data/\d{4}/(\d{6}-\d{5})-\d{4}\.gz</Key>.*?<Size>(\d+)</Size>", x)]
            m = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", x)
            if not m:
                break
            token = m.group(1)
    return pd.DataFrame(rows, columns=["station", "year", "bytes"])


def _get(url: str, tries: int = 4) -> str:
    for k in range(tries):
        try:
            with urlopen(url, timeout=60) as r:
                return r.read().decode()
        except OSError:
            if k == tries - 1:
                raise
            time.sleep(2 ** k)


def station_year_table(sizes: pd.DataFrame, stations) -> pd.DataFrame:
    """Wide table of whole kB (bytes // 1000, station x year) for the given stations; blank means no file."""
    years = range(int(sizes.year.min()), int(sizes.year.max()) + 1)
    s = sizes[sizes.station.isin(set(stations))]
    w = s.assign(kb=s.bytes // 1000).pivot_table(index="station", columns="year", values="kb", aggfunc="max")
    w = w.reindex(index=sorted(set(stations)), columns=years).astype("Int64")
    w.columns = [str(c) for c in w.columns]
    return w.rename_axis("station").reset_index()


def load_station_years(path: Path | str = STATION_YEARS) -> pd.DataFrame:
    """The cached kB table indexed by station with int year columns; empty when the cache is missing."""
    if not Path(path).exists():
        return pd.DataFrame(dtype=float)
    return _station_years(str(path), _mtime(path)).copy()


@lru_cache(maxsize=2)
def _station_years(path: str, mtime: int) -> pd.DataFrame:
    w = pd.read_csv(path, dtype={"station": str}).set_index("station").astype(float)
    w.columns = w.columns.astype(int)
    return w


def candidate_stations(venues: pd.DataFrame, isd: pd.DataFrame | None = None, max_km: float = MAX_KM) -> list[str]:
    isd = load_isd_history() if isd is None else isd
    lat, lon = isd.lat.to_numpy(), isd.lon.to_numpy()
    near = (isd.station[haversine_km(a, b, lat, lon) <= max_km] for a, b in zip(venues.lat, venues.lon))
    return sorted({s for x in near for s in x})


def _days(dates) -> np.ndarray:
    d = pd.Series([] if dates is None else list(np.atleast_1d(dates)))
    if d.empty:
        return np.array([], dtype="datetime64[D]")
    if pd.api.types.is_integer_dtype(d):
        d = d.astype(str) + "-07-01"
    return pd.to_datetime(d).to_numpy("datetime64[D]")


def reference_days(dates, end: pd.Timestamp | None) -> np.ndarray:
    """Match days the mirror can cover: those up to `end`, else the dates moved back one to three years,
    else 1 July of the last five data years."""
    d = _days(dates)
    if end is None:
        return d
    e = np.datetime64(pd.Timestamp(end).date(), "D")
    if (d <= e).any():
        return d[d <= e]
    back = np.concatenate([(pd.DatetimeIndex(d) - pd.DateOffset(years=k)).to_numpy("datetime64[D]") for k in (1, 2, 3)])
    back = back[back <= e]
    return back if len(back) else _days(list(range(e.astype(object).year - 4, e.astype(object).year + 1)))


def _usable(c: pd.DataFrame, days: np.ndarray, sy: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per candidate x day: inside BEGIN..END, usable (a big enough file that year) and that year's kB."""
    b, e = c.begin_day.to_numpy("datetime64[D]")[:, None], c.end_day.to_numpy("datetime64[D]")[:, None]
    inside = (days[None, :] >= b) & (days[None, :] <= e)
    uy, yi = np.unique(days.astype("datetime64[Y]"), return_inverse=True)
    y0, y1 = uy.astype("datetime64[D]")[None, :], (uy + 1).astype("datetime64[D]")[None, :]
    share = (np.minimum(e + 1, y1) - np.maximum(b, y0)).astype(float).clip(0) / (y1 - y0).astype(float)
    kb = sy.reindex(index=c.station, columns=uy.astype(int) + 1970).to_numpy(float) if len(sy) else \
        np.full((len(c), len(uy)), np.nan)
    known = c.station.isin(sy.index).to_numpy()[:, None]
    ok = np.where(known, kb >= USABLE_KB * np.maximum(share, MIN_YEAR_SHARE), True)
    return inside, inside & ok[:, yi], kb[:, yi]


def _rank(lat, lon, days, isd, max_km, ref_elev, sy) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    d = haversine_km(lat, lon, isd.lat.to_numpy(), isd.lon.to_numpy())
    c = isd[d <= max_km].assign(distance_km=d[d <= max_km]).reset_index(drop=True)
    inside, usable, kb = _usable(c, days, sy)
    n = max(len(days), 1)
    c["year_cover"], c["data_cover"] = inside.sum(1) / n, usable.sum(1) / n
    c["score_km"] = c.distance_km + COVER_PENALTY_KM * (1 - c.data_cover) + _site_penalty(c, ref_elev)
    order = c.sort_values(["score_km", "distance_km"]).index.to_numpy()
    return c.loc[order].reset_index(drop=True), usable[order], kb[order]


def station_candidates(lat: float, lon: float, dates=None, isd: pd.DataFrame | None = None, max_km: float = MAX_KM,
                       ref_elev: float | None = None, station_years: pd.DataFrame | None = None) -> pd.DataFrame:
    """ISD stations within max_km of (lat, lon), best first, scored on the match dates (or years) given."""
    isd = load_isd_history() if isd is None else isd
    sy = load_station_years() if station_years is None else station_years
    return _rank(lat, lon, reference_days(dates, isd_data_end(isd)), isd, max_km, ref_elev, sy)[0]


def _site_penalty(c: pd.DataFrame, ref_elev: float | None) -> pd.Series:
    ref = c.elev.median() if ref_elev is None or np.isnan(ref_elev) else ref_elev
    dz = (c.elev - ref).abs().sub(ELEV_FREE_M).clip(lower=0).fillna(0)
    return NO_ICAO_PENALTY_KM * (c.icao == "") + ELEV_PENALTY_KM_PER_M * dz


def _year(s) -> int | None:
    return int(str(s)[:4]) if str(s)[:4].isdigit() else None


def _span(v) -> list[int] | None:
    y0, y1 = _year(v.get("first_match")), _year(v.get("last_match"))
    return None if y0 is None else list(range(y0, max(y1 or y0, y0) + 1))


def _ref_elev(v) -> float | None:
    return float(v["elevation_m"]) if v.get("elevation_source") == "curated" else None


def _venue(venue_id: str, venues: pd.DataFrame | None) -> pd.Series:
    return (load_venues() if venues is None else venues).set_index("venue_id").loc[venue_id]


def venue_station_candidates(venue_id: str, venues: pd.DataFrame | None = None, isd: pd.DataFrame | None = None,
                             max_km: float = MAX_KM, dates=None,
                             station_years: pd.DataFrame | None = None) -> pd.DataFrame:
    """Candidates for a venue on the given match dates (default: every year of its first..last span)."""
    v = _venue(venue_id, venues)
    return station_candidates(v.lat, v.lon, _span(v) if dates is None else dates, isd, max_km, _ref_elev(v),
                              station_years)


def stations_on(venue_id: str, day, venues: pd.DataFrame | None = None, isd: pd.DataFrame | None = None,
                max_km: float = MAX_KM, station_years: pd.DataFrame | None = None) -> pd.DataFrame:
    """Stations with data on this date, usable ones first then thin files, each best first: the fallback
    order for one match. Empty after the NOAA data end (and wherever no station has a file)."""
    v = _venue(venue_id, venues)
    isd = load_isd_history() if isd is None else isd
    sy = load_station_years() if station_years is None else station_years
    c, usable, kb = _rank(v.lat, v.lon, _days([day]), isd, max_km, _ref_elev(v), sy)
    c["usable"], c["year_kb"] = usable[:, 0], kb[:, 0]
    keep = (c.begin_day <= pd.Timestamp(day)) & (c.end_day >= pd.Timestamp(day)) & \
        (c.year_kb.notna() | ~c.station.isin(sy.index))
    return c[keep].sort_values(["usable", "score_km"], ascending=[False, True]).reset_index(drop=True)


def match_stations(venues: pd.DataFrame, isd: pd.DataFrame | None = None, dates: dict | None = None,
                   station_years: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fill the station columns, station_flag and (unless curated) elevation_m for every venue. `dates`
    maps venue_id to its match dates; without it each venue is scored on every year of its span."""
    isd = load_isd_history() if isd is None else isd
    sy = load_station_years() if station_years is None else station_years
    end = isd_data_end(isd)
    out = venues.copy()
    if "elevation_source" not in out:
        out["elevation_source"] = ""
    rows = []
    for _, v in out.iterrows():
        days = reference_days(_span(v) if dates is None else dates.get(v.venue_id), end)
        c, usable, _ = _rank(v.lat, v.lon, days, isd, MAX_KM, _ref_elev(v), sy)
        if c.empty:
            rows.append(dict(isd_station="", isd_station_name="", isd_station_alts="", station_distance_km=np.nan,
                             station_data_cover=np.nan, alts_data_cover=np.nan, station_country="",
                             station_elev=np.nan, station_flag=f"no_station_{MAX_KM:.0f}km"))
            continue
        best, near = c.iloc[0], c.loc[c.distance_km.idxmin()]
        codes = COUNTRY_CODES.get(v.country, set())
        flags = [f"{k}:{s.ctry}" for k, s in (("country_mismatch", best), ("nearest_country_mismatch", near))
                 if s.ctry not in codes]
        alts_cover = float(usable[:4].any(0).mean()) if usable.shape[1] else 0.0
        if alts_cover < LOW_COVER:
            flags.append(f"low_data_cover:{alts_cover:.2f}")
        rows.append(dict(isd_station=best.station, isd_station_name=best["name"],
                         isd_station_alts="|".join(c.station.iloc[1:4]),
                         station_distance_km=round(float(best.distance_km), 1),
                         station_data_cover=round(float(best.data_cover), 3), alts_data_cover=round(alts_cover, 3),
                         station_country=best.ctry, station_elev=_site_elev(c, _ref_elev(v)),
                         station_flag=";".join(flags)))
    s = pd.DataFrame(rows, index=out.index)
    for k in s.columns.drop("station_elev"):
        out[k] = s[k]
    curated = out.elevation_source.eq("curated")
    out["elevation_m"] = np.where(curated, out.get("elevation_m", np.nan), s.station_elev)
    out["elevation_source"] = np.where(curated, "curated", np.where(s.station_elev.notna(), "station", ""))
    return out


def _site_elev(c: pd.DataFrame, ref_elev: float | None) -> float:
    """Height of the station that best represents the site, ignoring data density: distance plus the ICAO and
    height terms plus 50 km per unit of BEGIN..END cover missed (the pre-density ranking)."""
    e = c[c.elev.notna()]
    if e.empty:
        return np.nan
    k = (e.distance_km + SITE_COVER_KM * (1 - e.year_cover) + _site_penalty(e, ref_elev)).idxmin()
    return float(e.elev[k])


def scan_cricsheet_venues(zip_path: Path | str = CRICSHEET_ZIP) -> pd.DataFrame:
    """One row per Cricsheet match: match_id, date, venue, city, teams, match_type, gender."""
    rows = []
    with zipfile.ZipFile(zip_path) as z:
        for i in z.infolist():
            if not i.filename.endswith(".json"):
                continue
            info = _info(z.read(i))
            rows.append(dict(match_id=Path(i.filename).stem, date=info["dates"][0], venue=info.get("venue"),
                             city=info.get("city"), teams="|".join(info.get("teams", [])),
                             match_type=info.get("match_type"), gender=info.get("gender")))
    return pd.DataFrame(rows, columns=["match_id", "date", "venue", "city", "teams", "match_type", "gender"])


def _info(b: bytes) -> dict:
    k = b.find(b'"innings"')  # Cricsheet writes meta and info before the long innings list
    if k > 0:
        try:
            return json.loads(b[:k].rstrip().rstrip(b",") + b"}")["info"]
        except (ValueError, KeyError):
            pass
    return json.loads(b)["info"]


def alias_audit(scan: pd.DataFrame, venues: pd.DataFrame | None = None, path: Path | str = CONFIG) -> pd.DataFrame:
    """Per (venue, city) pair: match count, date range, venue_id, how it was matched and why."""
    venues = load_venues(path) if venues is None else venues
    g = scan.assign(city=scan.city.map(norm)).groupby(["venue", "city"]).agg(
        n_matches=("match_id", "size"), first_match=("date", "min"), last_match=("date", "max")).reset_index()
    g["venue_id"] = [venue_id_for(v, c, path) for v, c in zip(g.venue, g.city)]
    meta = venues.set_index("venue_id")
    g["canonical_name"] = g.venue_id.map(meta["name"])
    g["canonical_city"] = g.venue_id.map(meta["city"])
    n_strings = g.groupby("venue_id").venue.transform(lambda x: x.map(norm).nunique())
    g["merge_type"] = [_merge_type(v, n, name) for v, n, name in zip(g.venue, n_strings, g.canonical_name)]
    g["nontrivial_merge"] = g.venue_id.map(g.groupby("venue_id").venue.agg(lambda x: _n_names(x) > 1))
    key = g.venue.map(norm)
    ids = g.groupby(key).venue_id.agg(lambda x: ", ".join(sorted(set(x))))
    g["disambiguated_by_city"] = key.map(ids).str.contains(",").to_numpy()
    g["reason"] = [_reason(r, meta.at[r.venue_id, "notes"], ids[norm(r.venue)]) for r in g.itertuples()]
    return g.sort_values(["venue_id", "venue", "city"]).reset_index(drop=True)


def _base(s: str) -> str:
    return "".join(ch for ch in norm(s).split(",")[0].lower().replace("the ", "") if ch.isalnum())


def _close(a: str, b: str) -> bool:
    """Edit distance of at most 2 (spelling and punctuation variants)."""
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] <= 2


def _n_names(venues) -> int:
    reps = []
    for b in sorted({_base(v) for v in venues}, key=len):
        if not any(_close(b, r) for r in reps):
            reps.append(b)
    return len(reps)


def _merge_type(venue: str, n_strings: int, name: str) -> str:
    """How a string relates to the ground's canonical (current) name."""
    if n_strings == 1:
        return "single"
    if _base(venue) == _base(name):
        return "city_suffix" if "," in norm(venue) else "exact"
    if _close(_base(venue), _base(name)):
        return "spelling"
    return "renamed_or_variant"


def _reason(r, notes: str, ids: str) -> str:
    out = [notes] if notes and (r.nontrivial_merge or r.disambiguated_by_city or not r.city) else []
    if r.merge_type == "spelling":
        out.append("spelling or punctuation variant")
    if not r.city:
        out.append("no city in Cricsheet; ground identified from name, teams and event")
    if r.disambiguated_by_city:
        out.append(f"string shared by {ids}; the city decides")
    return "; ".join(out)


def refresh(venues: pd.DataFrame, scan: pd.DataFrame, isd: pd.DataFrame | None = None,
            path: Path | str = CONFIG, station_years: pd.DataFrame | None = None) -> pd.DataFrame:
    """Recompute match counts, date ranges, stations, elevations and ball brands for the curated table."""
    s = scan.assign(venue_id=[venue_id_for(v, c, path) for v, c in zip(scan.venue, scan.city)])
    agg = s.groupby("venue_id").agg(n_matches=("match_id", "size"), first_match=("date", "min"),
                                    last_match=("date", "max"))
    out = venues.drop(columns=[c for c in agg.columns if c in venues]).join(agg, on="venue_id")
    out["n_matches"] = out.n_matches.fillna(0).astype(int)
    out["ball_brand_default"] = out.cricket_country.map(ball_brand_default)
    dates = s.groupby("venue_id").date.agg(list).to_dict()
    out = match_stations(out, isd, {k: dates.get(k, []) for k in out.venue_id}, station_years)
    return out.reindex(columns=COLUMNS).sort_values("venue_id").reset_index(drop=True)


def validate(venues: pd.DataFrame, scan: pd.DataFrame | None = None, path: Path | str = CONFIG,
             data_end: pd.Timestamp | None = None) -> dict:
    """Structural checks plus the coverage numbers reported for the curated table."""
    problems = []
    if venues.venue_id.duplicated().any():
        problems.append(f"duplicate venue_id: {venues.venue_id[venues.venue_id.duplicated()].tolist()}")
    if (~venues.venue_id.str.fullmatch(r"[a-z0-9_]+")).any():
        problems.append("venue_id is not a lowercase slug")
    checks = (("region", REGIONS), ("coord_confidence", ("high", "medium", "low")), ("dst_region", DST_REGIONS),
              ("ball_brand_default", ("dukes", "sg", "kookaburra")))
    for col, ok in checks:
        bad = ~venues[col].isin(ok) if col in venues else pd.Series(True, index=venues.index)
        if bad.any():
            problems.append(f"bad {col}: {venues.venue_id[bad].tolist()[:20]}")
    if "cricket_country" in venues and "ball_brand_default" in venues and \
            not venues.ball_brand_default.eq(venues.cricket_country.map(ball_brand_default)).all():
        problems.append("ball_brand_default disagrees with cricket_country")
    if venues[["lat", "lon"]].isna().any().any() or (venues.lat.abs() > 90).any() or (venues.lon.abs() > 180).any():
        problems.append("missing or out-of-range coordinates")
    try:
        alias_pairs(venues)
    except ValueError as e:
        problems.append(str(e))
    unmapped, n_pairs, cover = [], None, {}
    if scan is not None:
        pairs = set(zip(scan.venue, scan.city.map(norm)))
        n_pairs = len(pairs)
        for v, c in sorted(pairs):
            try:
                venue_id_for(v, c, path)
            except KeyError:
                unmapped.append((v, c))
        if not unmapped:
            s = scan.assign(venue_id=[venue_id_for(v, c, path) for v, c in zip(scan.venue, scan.city)])
            later = s.date > str(data_end.date()) if data_end is not None else pd.Series(False, index=s.index)
            n = s[~later].venue_id.value_counts().reindex(venues.venue_id).fillna(0).to_numpy()
            w = lambda col: round(float((venues[col].fillna(0).to_numpy() * n).sum() / max(n.sum(), 1)), 4)
            cover = dict(matches_to_data_end=int(n.sum()), matches_after_data_end=int(later.sum()),
                         primary_usable_share=w("station_data_cover"), primary_or_alts_usable_share=w("alts_data_cover"))
    d = venues.station_distance_km
    flagged = venues[venues.station_flag.str.contains("mismatch")]
    return dict(n_venues=len(venues), n_alias_pairs=n_pairs, unmapped=unmapped,
                station_within_30km=int((d <= 30).sum()), station_within_60km=int((d <= 60).sum()),
                no_station=venues.venue_id[venues.isd_station.eq("")].tolist(),
                low_data_cover=venues.venue_id[venues.station_flag.str.contains("low_data_cover")].tolist(),
                data_cover=cover,
                coord_confidence=venues.coord_confidence.value_counts().to_dict(),
                region=venues.region.value_counts().to_dict(),
                elevation_source=venues.elevation_source.value_counts().to_dict(),
                ball_brand_default=venues.get("ball_brand_default", pd.Series(dtype=str)).value_counts().to_dict(),
                country_mismatches=flagged[["venue_id", "country", "station_flag", "isd_station_name",
                                            "station_distance_km"]].to_dict("records"),
                problems=problems)


def _nth_sunday(y: int, m: int, n: int) -> date:
    d = date(y, m, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))


def _last_sunday(y: int, m: int) -> date:
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def dst_shift(dst_region: str, day) -> float:
    """Hours added to standard time on this local date under the region's daylight-saving rule."""
    d = pd.Timestamp(day).date()
    y = d.year
    if dst_region == "eu":
        return float(_last_sunday(y, 3) <= d < _last_sunday(y, 10))
    if dst_region == "us":
        on, off = (_nth_sunday(y, 3, 2), _nth_sunday(y, 11, 1)) if y >= 2007 else (_nth_sunday(y, 4, 1), _last_sunday(y, 10))
        return float(on <= d < off)
    if dst_region == "mx":
        return float(y <= 2022 and _nth_sunday(y, 4, 1) <= d < _last_sunday(y, 10))
    if dst_region in ("au_south", "au_tas"):  # on from spring, off in autumn of the same year
        on = _nth_sunday(y, 10, 1) if y >= 2008 or dst_region == "au_tas" else _last_sunday(y, 10)
        off = _nth_sunday(y, 4, 1) if y >= 2008 or y == 2006 else _last_sunday(y, 3)  # 2006: Commonwealth Games
        return float(d >= on or d < off)
    if dst_region == "wa":  # Western Australia's three-summer trial, December 2006 to March 2009
        return float(date(2006, 12, 3) <= d < date(2007, 3, 25) or date(2007, 10, 28) <= d < date(2008, 3, 30)
                     or date(2008, 10, 26) <= d < date(2009, 3, 29))
    if dst_region == "nz":
        on = _last_sunday(y, 9) if y >= 2007 else _nth_sunday(y, 10, 1)
        off = _nth_sunday(y, 4, 1) if y >= 2008 else _nth_sunday(y, 3, 3)
        return float(d >= on or d < off)
    if dst_region == "ws":
        return float((2010 <= y <= 2020 and d >= _last_sunday(y, 9)) or (2011 <= y <= 2021 and d < _nth_sunday(y, 4, 1)))
    if dst_region == "fj":
        return float((2009 <= y <= 2020 and d >= _nth_sunday(y, 11, 1)) or (2010 <= y <= 2021 and d < _nth_sunday(y, 1, 3)))
    if dst_region == "na":  # Namibian winter time (UTC+1) until it was abolished in 2017
        return -float(y <= 2017 and _nth_sunday(y, 4, 1) <= d < _nth_sunday(y, 9, 1))
    if dst_region == "pk":
        return float(date(2008, 6, 1) <= d < date(2008, 11, 1) or date(2009, 4, 15) <= d < date(2009, 11, 1))
    if dst_region == "bd":
        return float(date(2009, 6, 19) <= d < date(2010, 1, 1))
    if dst_region == "lk":  # UTC+6 from 1996 to 15 April 2006
        return 0.5 if d < date(2006, 4, 15) else 0.0
    return 0.0


def utc_offset_on(venue_id: str, day, venues: pd.DataFrame | None = None) -> float:
    v = _venue(venue_id, venues)
    return float(v.utc_offset_hours) + dst_shift(v.dst_region, day)


def refresh_station_years(venues: pd.DataFrame, isd: pd.DataFrame | None = None, relist: bool = False) -> pd.DataFrame:
    """Rebuild the committed kB cache for all candidate stations from the raw bucket listing (relisting it
    when asked or missing); keep the committed cache when neither is possible."""
    isd = load_isd_history() if isd is None else isd
    if relist or not ISD_LITE_SIZES.exists():
        try:
            sizes = list_isd_lite_sizes(range(2001, isd_data_end(isd).year + 2))
        except OSError:
            if not relist and STATION_YEARS.exists():
                return load_station_years()
            raise
        ISD_LITE_SIZES.parent.mkdir(parents=True, exist_ok=True)
        sizes.to_csv(ISD_LITE_SIZES, index=False)
    sizes = pd.read_csv(ISD_LITE_SIZES, dtype={"station": str})
    STATION_YEARS.parent.mkdir(parents=True, exist_ok=True)
    station_year_table(sizes, candidate_stations(venues, isd)).to_csv(STATION_YEARS, index=False)
    return load_station_years()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--list-isd-lite", action="store_true", help="relist ISD-lite file sizes from the AWS bucket")
    args = p.parse_args(argv)
    isd = load_isd_history()
    scan = scan_cricsheet_venues()
    venues = load_venues()
    sy = refresh_station_years(venues, isd, args.list_isd_lite)
    venues = refresh(venues, scan, isd, station_years=sy)
    venues.to_csv(CONFIG, index=False)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    alias_audit(scan, venues).to_csv(AUDIT, index=False)
    print(json.dumps(dict(isd_data_end=str(isd_data_end(isd).date()), station_years=len(sy),
                          **validate(load_venues(), scan, data_end=isd_data_end(isd))), indent=1, default=str))


if __name__ == "__main__":
    main()
