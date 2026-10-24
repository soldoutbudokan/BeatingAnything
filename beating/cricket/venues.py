"""Venue canonicalisation, coordinates and NOAA ISD station matching.

`config/cricket-venues.csv` holds one row per ground: `venue_id` (slug), display `name`, pipe-separated
`aliases`, location (`city`, `country`, `cricket_country`, `region`, `lat`, `lon`, `coord_confidence`,
`elevation_m`), time (`utc_offset_hours` at standard time plus a `dst_region` rule), the matched ISD
station and the venue's Cricsheet match count and date range. Each alias is a Cricsheet `venue` string
qualified by the Cricsheet `city` it appeared with, written `venue @ city` (`venue @` when Cricsheet gave
no city). Qualifying every alias is what keeps the six 'County Ground's, the two 'Queen's Park's and the
two 'National Stadium's apart. `venue_id_for(venue, city)` looks up the whitespace-normalised pair
exactly. For an unseen pair it falls back to the venue string alone only when that string belongs to
one ground and the city is blank or one that ground is already known by; anything else raises KeyError,
so new Cricsheet grounds get curated rather than guessed.

Grouping was curated by hand from all 984 (venue, city) pairs in Cricsheet using city, teams, event
and dates: city-suffix and spelling variants, sponsor renames (Westpac Stadium -> Sky Stadium, Goodyear
Park -> Mangaung Oval) and same-site renames or rebuilds (Feroz Shah Kotla -> Arun Jaitley Stadium,
Sardar Patel -> Narendra Modi Stadium) share an id. Separate fields of one complex (Alur I/II/III,
ICC Academy Ovals 1/2, Willowmoore A/B/C) and strings that do not say which field they mean keep their
own ids. Each merge's reason is in `notes`, the per-alias trail in
`data/derived/cricket/venue_aliases_audit.csv`.

Coordinates come from the curator's knowledge of each ground, not from a survey or geocoder: `high`
is the ground itself (about 1 km), `medium` the suburb or complex (1-5 km), `low` the town. That is
enough to choose a weather station, not for anything finer. Elevation is curated where altitude matters
or the station is unrepresentative (Highveld, Harare, Nairobi, Dharamsala, upland English airfields)
and otherwise copied from the matched station.

Stations: every ISD station within 60 km (haversine) is a candidate, ranked by an effective distance
`d + 50 km * (1 - share of the venue's match years inside the station's BEGIN..END) + 5 km if the
station has no ICAO code + 0.05 km per metre of height difference beyond 100 m`. Non-airport stations
more often report sparsely; the height term keeps mountain-top stations such as Mt Wellington above
Hobart out (height is compared with the curated elevation, else the candidates' median). The best is
`isd_station` (USAF-WBAN), the next three `isd_station_alts`. BEGIN/END only say when a station reported
at all, not how completely, so weather code must still walk the alternates, or `stations_on(venue_id,
date)` which re-ranks for one date, when a station-year file is missing or thin. ISD's country code
(mostly FIPS 10-4, sometimes ISO alpha-2) of both the chosen and the nearest station is checked against
the venue country; mismatches and venues with no station are written to `station_flag`, not accepted.

`dst_shift` implements the civil daylight-saving rules that touch matches in the data (EU, North
America with its 2007 change, south-east Australia and New Zealand with their 2007-08 changes, Western
Australia's 2006-09 trial, Mexico
until 2022, Samoa 2010-21, Fiji approximately, Namibian winter time until 2017, Pakistan 2008-09,
Bangladesh 2009, Sri Lanka at UTC+6 before April 2006), resolved to the day: a match on a changeover
day gets the new offset all day.

Run `python -m beating.cricket.venues` to refresh match counts, stations and elevations in the config
and rewrite the audit file from the Cricsheet zip (about 10 s; it reads only each file's info block).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "cricket-venues.csv"
AUDIT = ROOT / "data" / "derived" / "cricket" / "venue_aliases_audit.csv"
CRICSHEET_ZIP = ROOT / "data" / "raw" / "cricsheet" / "all_json.zip"
ISD_HISTORY = ROOT / "data" / "raw" / "noaa" / "isd-history.csv"
MAX_KM = 60.0
YEAR_PENALTY_KM = 50.0
NO_ICAO_PENALTY_KM = 5.0
ELEV_FREE_M = 100.0
ELEV_PENALTY_KM_PER_M = 0.05
ISD_CURRENT = 20250601  # an isd-history END on or after this date means the station still reports
REGIONS = ("subcontinent", "sena_eng", "sena_aus", "sena_nz", "sena_sa", "west_indies", "uae_gulf", "other")
NUMERIC_COLS = ("lat", "lon", "elevation_m", "utc_offset_hours", "station_distance_km", "station_year_cover",
                "n_matches")
COLUMNS = ["venue_id", "name", "aliases", "city", "country", "cricket_country", "region", "lat", "lon",
           "coord_confidence", "elevation_m", "elevation_source", "utc_offset_hours", "dst_region",
           "isd_station", "isd_station_name", "isd_station_alts", "station_distance_km", "station_year_cover",
           "station_country", "station_flag", "n_matches", "first_match", "last_match", "notes"]

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
    h["station"] = h.USAF + "-" + h.WBAN
    h = h[h.lat.notna() & h.lon.notna() & ~((h.lat == 0) & (h.lon == 0)) & h.begin.notna() & h.end.notna()]
    return h[["station", "name", "ctry", "icao", "lat", "lon", "elev", "begin", "end"]].reset_index(drop=True)


def station_candidates(lat: float, lon: float, first_year: int | None = None, last_year: int | None = None,
                       isd: pd.DataFrame | None = None, max_km: float = MAX_KM,
                       ref_elev: float | None = None) -> pd.DataFrame:
    """ISD stations within max_km of (lat, lon), best first, with distance, year coverage and score."""
    isd = load_isd_history() if isd is None else isd
    d = haversine_km(lat, lon, isd.lat.to_numpy(), isd.lon.to_numpy())
    c = isd[d <= max_km].assign(distance_km=d[d <= max_km])
    y0 = int(first_year or 2002)
    y1 = max(int(last_year or y0), y0)
    b = (c.begin // 10000).astype(int)
    e = np.where(c.end >= ISD_CURRENT, 9999, c.end // 10000).astype(int)
    c["year_cover"] = (np.minimum(e, y1) - np.maximum(b, y0) + 1).clip(lower=0) / (y1 - y0 + 1)
    c["score_km"] = c.distance_km + YEAR_PENALTY_KM * (1 - c.year_cover) + _site_penalty(c, ref_elev)
    return c.sort_values(["score_km", "distance_km"]).drop_duplicates("station").reset_index(drop=True)


def _site_penalty(c: pd.DataFrame, ref_elev: float | None) -> pd.Series:
    ref = c.elev.median() if ref_elev is None or np.isnan(ref_elev) else ref_elev
    dz = (c.elev - ref).abs().sub(ELEV_FREE_M).clip(lower=0).fillna(0)
    return NO_ICAO_PENALTY_KM * (c.icao == "") + ELEV_PENALTY_KM_PER_M * dz


def _year(s) -> int | None:
    return int(str(s)[:4]) if str(s)[:4].isdigit() else None


def _ref_elev(v) -> float | None:
    return float(v["elevation_m"]) if v.get("elevation_source") == "curated" else None


def _venue(venue_id: str, venues: pd.DataFrame | None) -> pd.Series:
    return (load_venues() if venues is None else venues).set_index("venue_id").loc[venue_id]


def venue_station_candidates(venue_id: str, venues: pd.DataFrame | None = None,
                             isd: pd.DataFrame | None = None, max_km: float = MAX_KM) -> pd.DataFrame:
    v = _venue(venue_id, venues)
    return station_candidates(v.lat, v.lon, _year(v.get("first_match")), _year(v.get("last_match")), isd,
                              max_km, _ref_elev(v))


def stations_on(venue_id: str, day, venues: pd.DataFrame | None = None, isd: pd.DataFrame | None = None,
                max_km: float = MAX_KM) -> pd.DataFrame:
    """Candidates whose BEGIN..END covers this date, best first: the fallback order for one match."""
    v = _venue(venue_id, venues)
    ymd = int(pd.Timestamp(day).strftime("%Y%m%d"))
    c = station_candidates(v.lat, v.lon, ymd // 10000, ymd // 10000, isd, max_km, _ref_elev(v))
    return c[(c.begin <= ymd) & ((c.end >= ymd) | (c.end >= ISD_CURRENT))].reset_index(drop=True)


def match_stations(venues: pd.DataFrame, isd: pd.DataFrame | None = None) -> pd.DataFrame:
    """Fill the station columns, station_flag and (unless curated) elevation_m for every venue."""
    isd = load_isd_history() if isd is None else isd
    out = venues.copy()
    if "elevation_source" not in out:
        out["elevation_source"] = ""
    rows = []
    for _, v in out.iterrows():
        c = station_candidates(v.lat, v.lon, _year(v.get("first_match")), _year(v.get("last_match")), isd,
                               ref_elev=_ref_elev(v))
        if c.empty:
            rows.append(dict(isd_station="", isd_station_name="", isd_station_alts="", station_distance_km=np.nan,
                             station_year_cover=np.nan, station_country="", station_elev=np.nan,
                             station_flag=f"no_station_{MAX_KM:.0f}km"))
            continue
        best, near = c.iloc[0], c.loc[c.distance_km.idxmin()]
        codes = COUNTRY_CODES.get(v.country, set())
        flag = ";".join(f"{k}:{s.ctry}" for k, s in (("country_mismatch", best), ("nearest_country_mismatch", near))
                        if s.ctry not in codes)
        rows.append(dict(isd_station=best.station, isd_station_name=best["name"],
                         isd_station_alts="|".join(c.station.iloc[1:4]),
                         station_distance_km=round(float(best.distance_km), 1),
                         station_year_cover=round(float(best.year_cover), 2), station_country=best.ctry,
                         station_elev=best.elev, station_flag=flag))
    s = pd.DataFrame(rows, index=out.index)
    for k in s.columns.drop("station_elev"):
        out[k] = s[k]
    curated = out.elevation_source.eq("curated")
    out["elevation_m"] = np.where(curated, out.get("elevation_m", np.nan), s.station_elev)
    out["elevation_source"] = np.where(curated, "curated", np.where(s.station_elev.notna(), "station", ""))
    return out


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
    main = g.assign(k=-g.venue.str.len()).sort_values(["n_matches", "k"]).groupby("venue_id").venue.last()
    g["merge_type"] = [_merge_type(v, n, (meta.at[i, "name"], main[i]))
                       for v, n, i in zip(g.venue, n_strings, g.venue_id)]
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


def _merge_type(venue: str, n_strings: int, refs: tuple[str, str]) -> str:
    if n_strings == 1:
        return "single"
    if _base(venue) in {_base(r) for r in refs}:
        return "city_suffix" if "," in norm(venue) else "exact"
    if any(_close(_base(venue), _base(r)) for r in refs):
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
            path: Path | str = CONFIG) -> pd.DataFrame:
    """Recompute match counts, date ranges, stations and elevations for the curated table."""
    s = scan.assign(venue_id=[venue_id_for(v, c, path) for v, c in zip(scan.venue, scan.city)])
    agg = s.groupby("venue_id").agg(n_matches=("match_id", "size"), first_match=("date", "min"),
                                    last_match=("date", "max"))
    out = venues.drop(columns=[c for c in agg.columns if c in venues]).join(agg, on="venue_id")
    out["n_matches"] = out.n_matches.fillna(0).astype(int)
    out = match_stations(out, isd)
    return out.reindex(columns=COLUMNS).sort_values("venue_id").reset_index(drop=True)


def validate(venues: pd.DataFrame, scan: pd.DataFrame | None = None, path: Path | str = CONFIG) -> dict:
    """Structural checks plus the coverage numbers reported for the curated table."""
    problems = []
    if venues.venue_id.duplicated().any():
        problems.append(f"duplicate venue_id: {venues.venue_id[venues.venue_id.duplicated()].tolist()}")
    if (~venues.venue_id.str.fullmatch(r"[a-z0-9_]+")).any():
        problems.append("venue_id is not a lowercase slug")
    for col, ok in (("region", REGIONS), ("coord_confidence", ("high", "medium", "low"))):
        bad = ~venues[col].isin(ok)
        if bad.any():
            problems.append(f"bad {col}: {venues.venue_id[bad].tolist()}")
    if venues[["lat", "lon"]].isna().any().any() or (venues.lat.abs() > 90).any() or (venues.lon.abs() > 180).any():
        problems.append("missing or out-of-range coordinates")
    try:
        alias_pairs(venues)
    except ValueError as e:
        problems.append(str(e))
    unmapped, n_pairs = [], None
    if scan is not None:
        pairs = set(zip(scan.venue, scan.city.map(norm)))
        n_pairs = len(pairs)
        for v, c in sorted(pairs):
            try:
                venue_id_for(v, c, path)
            except KeyError:
                unmapped.append((v, c))
    d = venues.station_distance_km
    flagged = venues[venues.station_flag.str.contains("mismatch")]
    return dict(n_venues=len(venues), n_alias_pairs=n_pairs, unmapped=unmapped,
                station_within_30km=int((d <= 30).sum()), station_within_60km=int((d <= 60).sum()),
                no_station=venues.venue_id[venues.isd_station.eq("")].tolist(),
                coord_confidence=venues.coord_confidence.value_counts().to_dict(),
                region=venues.region.value_counts().to_dict(),
                elevation_source=venues.elevation_source.value_counts().to_dict(),
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
    if dst_region == "au_south":  # southern hemisphere: on from spring, off in autumn of the same year
        on = _nth_sunday(y, 10, 1) if y >= 2008 else _last_sunday(y, 10)
        off = _nth_sunday(y, 4, 1) if y >= 2008 else _last_sunday(y, 3)
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


def main() -> None:
    scan = scan_cricsheet_venues()
    venues = refresh(load_venues(), scan)
    venues.to_csv(CONFIG, index=False)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    alias_audit(scan, venues).to_csv(AUDIT, index=False)
    print(json.dumps(validate(load_venues(), scan), indent=1, default=str))


if __name__ == "__main__":
    main()
