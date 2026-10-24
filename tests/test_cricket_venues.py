from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from beating.cricket import venues as V

VENUES = pd.DataFrame([
    dict(venue_id="county_ground_bristol", name="County Ground, Bristol", city="Bristol", country="England",
         cricket_country="England", aliases="County Ground @ Bristol|County Ground, Bristol @ Bristol|The Royal & Sun Alliance County Ground, Bristol @ Bristol",
         lat=51.474, lon=-2.584, elevation_m=20.0, elevation_source="curated", notes="sponsored name (2003)"),
    dict(venue_id="county_ground_taunton", name="County Ground, Taunton", city="Taunton", country="England",
         cricket_country="England", aliases="County Ground @ Taunton", lat=51.020, lon=-3.100, elevation_m=None, elevation_source="", notes=""),
    dict(venue_id="queens_park_invercargill", name="Queen's Park", city="Invercargill", country="New Zealand",
         cricket_country="New Zealand", aliases="Queen's Park @|Queen's Park @ Invercargill", lat=-46.400, lon=168.357, elevation_m=None,
         elevation_source="", notes="no-city row assigned from teams"),
    dict(venue_id="queens_park_chesterfield", name="Queen's Park", city="Chesterfield", country="England",
         cricket_country="England", aliases="Queen's Park @ Chesterfield", lat=53.233, lon=-1.430, elevation_m=None, elevation_source="", notes=""),
    dict(venue_id="eden_park", name="Eden Park", city="Auckland", country="New Zealand",
         cricket_country="New Zealand", aliases="Eden Park @ Auckland|Eden Park @|Eden Park, Auckland @ Auckland|Westpac Eden Park @ Auckland", lat=-36.875, lon=174.745,
         elevation_m=None, elevation_source="", notes=""),
    dict(venue_id="kingston_twin_ovals", name="Kingston Twin Ovals", city="Hobart", country="Australia",
         cricket_country="Australia", aliases="Kingston Twin Ovals, Hobart @ Hobart", lat=-42.976, lon=147.302, elevation_m=50.0,
         elevation_source="curated", notes=""),
])

ISD_ROWS = [  # USAF, WBAN, name, CTRY, ICAO, lat, lon, elev, begin, end
    ("037243", "99999", "BRISTOL", "UK", "EGGD", 51.383, -2.717, 189.6, "19730101", "20250824"),
    ("037249", "99999", "BRISTOL NEW", "UK", "", 51.470, -2.580, 15.0, "20200101", "20250824"),
    ("038530", "99999", "YEOVILTON", "UK", "EGDY", 51.006, -2.640, 22.9, "19730101", "20250824"),
    ("949700", "99999", "HOBART (ELLERSLIE ROAD)", "AS", "", -42.890, 147.330, 51.0, "19730101", "20250824"),
    ("949750", "99999", "MT WELLINGTON", "AS", "", -42.900, 147.240, 1260.5, "19730101", "20250824"),
    ("931190", "99999", "AUCKLAND INTL", "NZ", "NZAA", -37.008, 174.792, 7.0, "19730101", "20250824"),
    ("938440", "99999", "INVERCARGILL", "FR", "NZNV", -46.417, 168.313, 0.0, "19730101", "20250824"),
    ("931730", "99999", "HAMILTON AWS", "NZ", "", -37.850, 175.333, 53.0, "20210817", "20250824"),
    ("931670", "99999", "RAGLAN", "NZ", "", -37.800, 174.870, 12.0, "20041212", "20250530"),
]
NO_SIZES = pd.DataFrame()  # no file-size cache: every station falls back to BEGIN..END
SEDDON = pd.DataFrame([dict(venue_id="seddon_park", name="Seddon Park", country="New Zealand", lat=-37.787,
                            lon=175.274, elevation_m=40.0, elevation_source="curated")])


def sizes(rows: dict) -> pd.DataFrame:
    """Station-year kB table in the cached layout from {station: {year: kB}}."""
    w = pd.DataFrame(rows).T.astype(float)
    w.columns = w.columns.astype(int)
    return w.sort_index(axis=1)


def write_isd(path: Path) -> None:
    rows = [dict(USAF=a, WBAN=b, **{"STATION NAME": n, "CTRY": c, "STATE": "", "ICAO": i, "LAT": f"{la:+.3f}",
                 "LON": f"{lo:+.3f}", "ELEV(M)": f"{e:+.1f}", "BEGIN": bg, "END": en})
            for a, b, n, c, i, la, lo, e, bg, en in ISD_ROWS]
    pd.DataFrame(rows).to_csv(path, index=False)


def match_json(venue, city, day, innings_first=False) -> bytes:
    info = {"dates": [day], "venue": venue, "teams": ["A", "B"], "match_type": "T20", "gender": "male"}
    if city is not None:
        info["city"] = city
    body = {"meta": {"data_version": "1.1.0"}, "info": info, "innings": [{"team": "A", "overs": []}]}
    if innings_first:
        body = {"innings": body["innings"], "meta": body["meta"], "info": info}
    return json.dumps(body, indent=2).encode()


def _tz_ok() -> bool:
    try:
        ZoneInfo("Australia/Hobart")
        return True
    except Exception:
        return False


class VenueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.cfg = d / "venues.csv"
        VENUES.to_csv(self.cfg, index=False)
        self.isd_path = d / "isd-history.csv"
        write_isd(self.isd_path)
        self.isd = V.load_isd_history(self.isd_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lookup_is_exact_and_city_qualified(self):
        f = lambda v, c: V.venue_id_for(v, c, self.cfg)
        self.assertEqual(f("County Ground", "Bristol"), "county_ground_bristol")
        self.assertEqual(f("County Ground", "Taunton"), "county_ground_taunton")
        self.assertEqual(f("Queen's Park", None), "queens_park_invercargill")
        self.assertEqual(f("Queen's Park", float("nan")), "queens_park_invercargill")
        self.assertEqual(f("Queen's Park", "Chesterfield"), "queens_park_chesterfield")
        self.assertEqual(f("  County  Ground ", "Bristol "), "county_ground_bristol")

    def test_lookup_fallback_and_unknown(self):
        f = lambda v, c: V.venue_id_for(v, c, self.cfg)
        self.assertEqual(f("Eden Park, Auckland", ""), "eden_park")  # unique string, blank city
        with self.assertRaises(KeyError):
            f("County Ground", "Hove")  # string shared by two grounds, unseen city
        with self.assertRaises(KeyError):
            f("Eden Park", "Wellington")  # unique string but a city the ground is not known by
        with self.assertRaises(KeyError):
            f("Basin Reserve", "Wellington")

    def test_alias_pairs_rejects_conflicts(self):
        bad = pd.concat([VENUES, VENUES.iloc[[1]].assign(venue_id="dup", aliases="County Ground @ Bristol")])
        with self.assertRaises(ValueError):
            V.alias_pairs(bad)
        self.assertEqual(V.parse_alias("Eden Park @"), ("Eden Park", ""))
        self.assertEqual(V.alias_key("Eden Park", None), "Eden Park @")

    def test_haversine(self):
        self.assertAlmostEqual(float(V.haversine_km(51.5074, -0.1278, 48.8566, 2.3522)), 343.6, delta=1.0)
        self.assertEqual(float(V.haversine_km(10, 20, 10, 20)), 0.0)

    def test_ranking_prefers_full_coverage_airport(self):
        c = V.station_candidates(51.474, -2.584, range(2003, 2027), self.isd, station_years=NO_SIZES)
        # 14 km with full cover beats 0.5 km since 2020 (6 of 23 years) and even 52 km Yeovilton
        self.assertEqual(c.station.tolist(), ["037243-99999", "038530-99999", "037249-99999"])
        self.assertTrue((c.distance_km <= V.MAX_KM).all())
        recent = V.station_candidates(51.474, -2.584, range(2021, 2027), self.isd, station_years=NO_SIZES)
        self.assertEqual(recent.station.iloc[0], "037249-99999")

    def test_height_penalty_skips_mountain_station(self):
        c = V.station_candidates(-42.976, 147.302, [2025], self.isd, ref_elev=50.0, station_years=NO_SIZES)
        self.assertEqual(c.station.iloc[0], "949700-99999")
        self.assertGreater(c.set_index("station").at["949750-99999", "score_km"], 50)

    def test_data_end_and_reference_days(self):
        end = V.isd_data_end(self.isd)
        self.assertEqual(end, pd.Timestamp("2025-08-24"))  # the modal END, not RAGLAN's earlier one
        d = V.reference_days(["2024-12-01", "2025-08-24", "2025-09-01", "2026-02-01"], end)
        self.assertEqual([str(x) for x in d], ["2024-12-01", "2025-08-24"])
        back = V.reference_days(["2026-02-01"], end)
        self.assertEqual([str(x) for x in back], ["2025-02-01", "2024-02-01", "2023-02-01"])
        self.assertEqual(len(V.reference_days([], end)), 5)  # no matches: 1 July of the last five data years

    def test_file_sizes_beat_begin_end(self):
        thin_airport = sizes({"037243-99999": {y: 3 for y in range(2003, 2026)},
                              "037249-99999": {y: 40 for y in range(2020, 2026)},
                              "038530-99999": {y: 60 for y in range(2003, 2026)}})
        dates = {"county_ground_bristol": [f"{y}-06-01" for y in range(2016, 2025)]}
        v = VENUES.iloc[[0]]
        old = V.match_stations(v, self.isd, dates, NO_SIZES).iloc[0]
        self.assertEqual(old.isd_station, "037243-99999")  # BEGIN..END alone keeps the empty airport
        new = V.match_stations(v, self.isd, dates, thin_airport).iloc[0]
        self.assertEqual(new.isd_station, "037249-99999")
        self.assertEqual(new.isd_station_alts, "038530-99999|037243-99999")
        self.assertAlmostEqual(new.station_data_cover, 5 / 9, places=3)
        self.assertEqual(new.alts_data_cover, 1.0)
        self.assertEqual(new.station_flag, "")

    def test_partial_years_and_low_cover_flag(self):
        sy = sizes({"931730-99999": {2021: 6, 2022: 90, 2025: 10}, "931670-99999": {2021: 0, 2025: 0}})
        c = V.station_candidates(-37.787, 175.274, ["2021-03-01", "2021-12-20", "2025-02-01", "2025-08-20"],
                                 self.isd, station_years=sy).set_index("station")
        # AWS opens 2021-08-17: 6 kB is enough for 37% of a year and 10 kB for 2025 up to 24 August
        self.assertEqual(c.at["931730-99999", "data_cover"], 0.75)
        self.assertEqual(c.at["931730-99999", "year_cover"], 0.75)
        self.assertEqual(c.at["931670-99999", "data_cover"], 0.0)
        out = V.match_stations(SEDDON, self.isd, {"seddon_park": ["2019-01-05", "2020-01-05", "2022-01-05"]}, sy)
        self.assertEqual(out.iloc[0].isd_station, "931730-99999")
        self.assertEqual(out.iloc[0].station_flag, "low_data_cover:0.33")

    def test_stations_on_uses_file_sizes(self):
        sy = sizes({"037243-99999": {2024: 60}, "037249-99999": {2024: 5}})
        on = V.stations_on("county_ground_bristol", "2024-06-01", VENUES, self.isd, station_years=sy)
        self.assertEqual(on.station.tolist(), ["037243-99999", "038530-99999", "037249-99999"])  # Yeovilton unknown
        self.assertEqual(on.usable.tolist(), [True, True, False])  # thin file last
        sy2 = sizes({"037243-99999": {2024: 60}, "037249-99999": {2024: 5}, "038530-99999": {2023: 60}})
        on2 = V.stations_on("county_ground_bristol", "2024-06-01", VENUES, self.isd, station_years=sy2)
        self.assertEqual(on2.station.tolist(), ["037243-99999", "037249-99999"])  # no 2024 file: dropped
        self.assertTrue(V.stations_on("county_ground_bristol", "2025-09-01", VENUES, self.isd,
                                      station_years=NO_SIZES).empty)  # after the data end
        on = lambda day: V.stations_on("seddon_park", day, SEDDON, self.isd, station_years=NO_SIZES).station.tolist()
        self.assertEqual(on("2021-03-01"), ["931670-99999"])  # Hamilton AWS opens 2021-08-17
        self.assertEqual(on("2025-07-01"), ["931730-99999"])  # Raglan's END is 2025-05-30

    def test_isd_lite_listing_and_cache(self):
        page1 = ("<ListBucketResult><Contents><Key>isd-lite/data/2003/037243-99999-2003.gz</Key>"
                 "<LastModified>x</LastModified><Size>15999</Size></Contents>"
                 "<NextContinuationToken>abc+/=</NextContinuationToken></ListBucketResult>")
        page2 = ("<ListBucketResult><Contents><Key>isd-lite/data/2003/037249-99999-2003.gz</Key>"
                 "<Size>300</Size></Contents></ListBucketResult>")
        empty = "<ListBucketResult><KeyCount>0</KeyCount></ListBucketResult>"
        seen = []

        def fake_get(url):
            seen.append(url)
            return {0: page1, 1: page2}.get(len(seen) - 1, empty)

        real, V._get = V._get, fake_get
        try:
            s = V.list_isd_lite_sizes([2003, 2004])
        finally:
            V._get = real
        self.assertEqual(len(seen), 3)
        self.assertIn("continuation-token=abc%2B%2F%3D", seen[1])
        self.assertEqual(s.values.tolist(), [["037243-99999", 2003, 15999], ["037249-99999", 2003, 300]])
        s = pd.concat([s, pd.DataFrame([["037243-99999", 2005, 70000]], columns=s.columns)])
        w = V.station_year_table(s, ["037249-99999", "037243-99999", "038530-99999"])
        self.assertEqual(list(w.columns), ["station", "2003", "2004", "2005"])
        path = Path(self.tmp.name) / "station_years.csv"
        w.to_csv(path, index=False)
        t = V.load_station_years(path)
        self.assertEqual(t.at["037243-99999", 2003], 15)  # floor, so >= 15 kB means >= 15,000 bytes
        self.assertEqual(t.at["037249-99999", 2003], 0)
        self.assertTrue(t.loc["038530-99999"].isna().all())  # checked, no files
        self.assertTrue(V.load_station_years(Path(self.tmp.name) / "missing.csv").empty)

    def test_ball_brand_default(self):
        f = V.ball_brand_default
        self.assertEqual([f(c) for c in ("England", "Ireland", "Scotland", "West Indies")], ["dukes"] * 4)
        self.assertEqual((f("India"), f("Australia"), f(""), f(None)), ("sg", "kookaburra", "kookaburra", "kookaburra"))

    def test_match_stations_flags_and_elevation(self):
        v = VENUES.assign(first_match="2015-01-01", last_match="2024-12-31")
        out = V.match_stations(v, self.isd, station_years=NO_SIZES).set_index("venue_id")
        self.assertEqual(out.at["county_ground_bristol", "station_flag"], "")
        self.assertEqual(out.at["county_ground_bristol", "elevation_m"], 20.0)  # curated value kept
        self.assertEqual(out.at["county_ground_taunton", "isd_station"], "038530-99999")
        self.assertEqual(out.at["county_ground_taunton", "elevation_source"], "station")
        self.assertIn("country_mismatch:FR", out.at["queens_park_invercargill", "station_flag"])
        self.assertEqual(out.at["queens_park_chesterfield", "station_flag"], "no_station_60km")
        self.assertEqual(out.at["queens_park_chesterfield", "isd_station"], "")
        self.assertEqual(out.at["eden_park", "station_country"], "NZ")
        out = out.reset_index().assign(region="other", coord_confidence="high", dst_region="eu",
                                       ball_brand_default=lambda d: d.cricket_country.map(V.ball_brand_default))
        stats = V.validate(out)
        self.assertEqual(stats["no_station"], ["queens_park_chesterfield"])
        self.assertEqual(len(stats["country_mismatches"]), 1)
        self.assertEqual(stats["problems"], [])

    def test_stations_on_filters_by_date(self):
        v = VENUES.assign(first_match="2003-01-01", last_match="2026-01-01")
        early = V.stations_on("county_ground_bristol", "2015-06-01", v, self.isd, station_years=NO_SIZES)
        self.assertNotIn("037249-99999", set(early.station))
        late = V.stations_on("county_ground_bristol", "2024-06-01", v, self.isd, station_years=NO_SIZES)
        self.assertEqual(late.station.iloc[0], "037249-99999")
        self.assertTrue(late.usable.all())

    def test_scan_and_audit(self):
        z = Path(self.tmp.name) / "all_json.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("1.json", match_json("County Ground", "Bristol", "2010-06-01"))
            f.writestr("2.json", match_json("County Ground, Bristol", "Bristol", "2020-06-01"))
            f.writestr("3.json", match_json("The Royal & Sun Alliance County Ground, Bristol", "Bristol", "2003-06-01"))
            f.writestr("4.json", match_json("Queen's Park", None, "2020-03-01", innings_first=True))
            f.writestr("5.json", match_json("County Ground", "Taunton", "2012-06-01"))
            f.writestr("6.json", match_json("Westpac Eden Park", "Auckland", "2016-01-01"))
            f.writestr("7.json", match_json("Westpac Eden Park", "Auckland", "2017-01-01"))
            f.writestr("8.json", match_json("Eden Park, Auckland", "Auckland", "2018-01-01"))
            f.writestr("README.txt", "not a match")
        scan = V.scan_cricsheet_venues(z)
        self.assertEqual(len(scan), 8)
        self.assertEqual(set(scan.match_id), set("12345678"))
        self.assertTrue(scan.set_index("match_id").city.isna()["4"])
        a = V.alias_audit(scan, VENUES, self.cfg).set_index(["venue", "city"])
        self.assertEqual(a.at[("County Ground", "Bristol"), "merge_type"], "exact")
        self.assertEqual(a.at[("County Ground, Bristol", "Bristol"), "merge_type"], "city_suffix")
        rsa = a.loc[("The Royal & Sun Alliance County Ground, Bristol", "Bristol")]
        self.assertEqual(rsa.merge_type, "renamed_or_variant")
        self.assertTrue(rsa.nontrivial_merge)
        self.assertIn("sponsored name", rsa.reason)
        self.assertTrue(a.at[("County Ground", "Taunton"), "disambiguated_by_city"])
        self.assertIn("no city", a.at[("Queen's Park", ""), "reason"])
        # labels compare with the canonical name, even when an old name is the most frequent string
        self.assertEqual(a.at[("Westpac Eden Park", "Auckland"), "merge_type"], "renamed_or_variant")
        self.assertEqual(a.at[("Eden Park, Auckland", "Auckland"), "merge_type"], "city_suffix")
        r = V.refresh(VENUES, scan, self.isd, self.cfg, station_years=NO_SIZES).set_index("venue_id")
        self.assertEqual(r.at["county_ground_bristol", "n_matches"], 3)
        self.assertEqual(r.at["county_ground_bristol", "ball_brand_default"], "dukes")
        self.assertEqual(r.at["eden_park", "ball_brand_default"], "kookaburra")
        self.assertEqual(r.at["county_ground_taunton", "station_data_cover"], 1.0)
        self.assertEqual(r.at["county_ground_bristol", "first_match"], "2003-06-01")
        self.assertEqual(r.at["eden_park", "n_matches"], 3)
        self.assertEqual(r.at["kingston_twin_ovals", "n_matches"], 0)
        self.assertEqual(list(r.reset_index().columns), V.COLUMNS)

    def test_dst_rules(self):
        s = V.dst_shift
        self.assertEqual((s("eu", "2024-03-30"), s("eu", "2024-03-31"), s("eu", "2024-10-27")), (0, 1, 0))
        self.assertEqual((s("us", "2024-03-09"), s("us", "2024-03-10"), s("us", "2006-03-20")), (0, 1, 0))
        self.assertEqual((s("au_south", "2024-01-10"), s("au_south", "2024-04-07"), s("au_south", "2024-10-06")), (1, 0, 1))
        self.assertEqual((s("nz", "2024-09-28"), s("nz", "2024-09-29"), s("nz", "2025-03-01")), (0, 1, 1))
        self.assertEqual((s("na", "2015-06-01"), s("na", "2019-06-01")), (-1, 0))
        self.assertEqual((s("lk", "2005-08-01"), s("lk", "2010-08-01")), (0.5, 0))
        self.assertEqual((s("mx", "2022-06-01"), s("mx", "2023-06-01"), s("none", "2020-06-01")), (1, 0, 0))
        # 2006 Commonwealth Games: south-east Australia ended DST on 2 April; Tasmania starts in early October
        self.assertEqual((s("au_south", "2006-03-30"), s("au_south", "2006-04-02"), s("au_south", "2007-03-25")), (1, 0, 0))
        self.assertEqual((s("au_south", "2005-10-02"), s("au_tas", "2005-10-02"), s("au_tas", "2006-03-30")), (0, 1, 1))
        v = VENUES.assign(utc_offset_hours=[0, 0, 12, 0, 12, 10], dst_region=["eu", "eu", "nz", "eu", "nz", "au_south"])
        self.assertEqual(V.utc_offset_on("eden_park", "2025-01-15", v), 13.0)

    @unittest.skipUnless(_tz_ok(), "IANA tz database not available")
    def test_dst_rules_match_tz_database(self):
        zones = {"eu": "Europe/London", "us": "America/New_York", "au_south": "Australia/Sydney",
                 "au_tas": "Australia/Hobart", "nz": "Pacific/Auckland", "wa": "Australia/Perth"}
        std = {"eu": 0, "us": -5, "au_south": 10, "au_tas": 10, "nz": 12, "wa": 8}
        for k, z in zones.items():
            tz = ZoneInfo(z)
            for d in pd.date_range("2002-01-01", "2026-12-31", freq="D")[::3]:
                want = tz.utcoffset(datetime(d.year, d.month, d.day, 12)).total_seconds() / 3600
                self.assertEqual(std[k] + V.dst_shift(k, d), want, (k, d.date()))


class CommittedConfigTests(unittest.TestCase):
    """Checks on the committed config and audit (small files, no network, no zip)."""

    def test_config_is_consistent(self):
        v = V.load_venues()
        stats = V.validate(v)
        self.assertEqual(stats["problems"], [])
        self.assertTrue(v.isd_station.str.fullmatch(r"(\d{6}-\d{5})?").all())
        self.assertTrue(set(v.dst_region) <= set(V.DST_REGIONS))
        self.assertTrue(v.cricket_country.str.len().gt(0).all())
        brand = v.set_index("venue_id").ball_brand_default
        self.assertEqual(brand[["lords", "sophia_gardens", "stormont", "grange_edinburgh", "kensington_oval"]].unique().tolist(), ["dukes"])
        self.assertEqual((brand["eden_gardens"], brand["mcg"], brand["vra_amstelveen"]), ("sg", "kookaburra", "kookaburra"))
        cover = v[["station_data_cover", "alts_data_cover"]].dropna()
        self.assertTrue(cover.stack().between(0, 1).all() and (cover.alts_data_cover >= cover.station_data_cover).all())
        self.assertTrue(v.region[v.country.eq("Netherlands")].eq("other").all())
        self.assertTrue(v.dst_region[v.city.isin(["Hobart", "Launceston", "Burnie", "Latrobe"])].eq("au_tas").all())
        far = v.station_distance_km > V.MAX_KM
        self.assertFalse(far.any())
        self.assertTrue((v.station_flag[v.isd_station.eq("")] == "no_station_60km").all())
        elev = v.set_index("venue_id").elevation_m
        self.assertGreater(elev["wanderers_johannesburg"], 1700)
        self.assertGreater(elev["hpca_dharamsala"], 1400)

    def test_station_cache_covers_config(self):
        sy = V.load_station_years()
        used = {s for x in V.load_venues().pipe(lambda d: d.isd_station + "|" + d.isd_station_alts) for s in x.split("|") if s}
        self.assertTrue(used <= set(sy.index))
        self.assertTrue(set(sy.columns) >= set(range(2003, 2026)))
        primary = V.load_venues().set_index("venue_id").isd_station
        self.assertGreaterEqual(sy.at[primary["wankhede_stadium"], 2019], V.USABLE_KB)  # not Colaba
        self.assertEqual(primary["harare_sports_club"], "677750-99999")  # not Belvedere

    def test_audit_maps_every_pair(self):
        a = pd.read_csv(V.AUDIT, keep_default_na=False)
        self.assertEqual(a.duplicated(["venue", "city"]).sum(), 0)
        got = [V.venue_id_for(x, c) for x, c in zip(a.venue, a.city)]
        self.assertEqual(got, a.venue_id.tolist())
        self.assertEqual(V.venue_id_for("County Ground", "Chelmsford"), "county_ground_chelmsford")
        self.assertEqual(V.venue_id_for("Wankhede Stadium, Mumbai", "Mumbai"), V.venue_id_for("Wankhede Stadium", None))
        self.assertEqual(V.venue_id_for("Dubai Sports City Cricket Stadium", None), "dubai_international_stadium")
        self.assertNotEqual(V.venue_id_for("Gaddafi Stadium", "Lahore"),
                            V.venue_id_for("Lahore City Cricket Association Ground", "Lahore"))
        self.assertTrue(a.reason[a.nontrivial_merge.astype(str).eq("True")].str.len().gt(0).all())


if __name__ == "__main__":
    unittest.main()
