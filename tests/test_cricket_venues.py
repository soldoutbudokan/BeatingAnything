from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import pandas as pd

from beating.cricket import venues as V

VENUES = pd.DataFrame([
    dict(venue_id="county_ground_bristol", name="County Ground, Bristol", city="Bristol", country="England",
         aliases="County Ground @ Bristol|County Ground, Bristol @ Bristol|The Royal & Sun Alliance County Ground, Bristol @ Bristol",
         lat=51.474, lon=-2.584, elevation_m=20.0, elevation_source="curated", notes="sponsored name (2003)"),
    dict(venue_id="county_ground_taunton", name="County Ground, Taunton", city="Taunton", country="England",
         aliases="County Ground @ Taunton", lat=51.020, lon=-3.100, elevation_m=None, elevation_source="", notes=""),
    dict(venue_id="queens_park_invercargill", name="Queen's Park", city="Invercargill", country="New Zealand",
         aliases="Queen's Park @|Queen's Park @ Invercargill", lat=-46.400, lon=168.357, elevation_m=None,
         elevation_source="", notes="no-city row assigned from teams"),
    dict(venue_id="queens_park_chesterfield", name="Queen's Park", city="Chesterfield", country="England",
         aliases="Queen's Park @ Chesterfield", lat=53.233, lon=-1.430, elevation_m=None, elevation_source="", notes=""),
    dict(venue_id="eden_park", name="Eden Park", city="Auckland", country="New Zealand",
         aliases="Eden Park @ Auckland|Eden Park @|Eden Park, Auckland @ Auckland", lat=-36.875, lon=174.745,
         elevation_m=None, elevation_source="", notes=""),
    dict(venue_id="kingston_twin_ovals", name="Kingston Twin Ovals", city="Hobart", country="Australia",
         aliases="Kingston Twin Ovals, Hobart @ Hobart", lat=-42.976, lon=147.302, elevation_m=50.0,
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
]


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
        c = V.station_candidates(51.474, -2.584, 2003, 2026, self.isd)
        self.assertEqual(c.station.iloc[0], "037243-99999")  # 14 km, full cover, beats 0.5 km since 2020
        self.assertEqual(c.station.iloc[1], "037249-99999")
        self.assertTrue((c.distance_km <= V.MAX_KM).all())
        recent = V.station_candidates(51.474, -2.584, 2021, 2026, self.isd)
        self.assertEqual(recent.station.iloc[0], "037249-99999")

    def test_height_penalty_skips_mountain_station(self):
        c = V.station_candidates(-42.976, 147.302, 2025, 2025, self.isd, ref_elev=50.0)
        self.assertEqual(c.station.iloc[0], "949700-99999")
        self.assertGreater(c.set_index("station").at["949750-99999", "score_km"], 50)

    def test_match_stations_flags_and_elevation(self):
        v = VENUES.assign(first_match="2015-01-01", last_match="2024-12-31")
        out = V.match_stations(v, self.isd).set_index("venue_id")
        self.assertEqual(out.at["county_ground_bristol", "station_flag"], "")
        self.assertEqual(out.at["county_ground_bristol", "elevation_m"], 20.0)  # curated value kept
        self.assertEqual(out.at["county_ground_taunton", "isd_station"], "038530-99999")
        self.assertEqual(out.at["county_ground_taunton", "elevation_source"], "station")
        self.assertIn("country_mismatch:FR", out.at["queens_park_invercargill", "station_flag"])
        self.assertEqual(out.at["queens_park_chesterfield", "station_flag"], "no_station_60km")
        self.assertEqual(out.at["queens_park_chesterfield", "isd_station"], "")
        self.assertEqual(out.at["eden_park", "station_country"], "NZ")
        stats = V.validate(out.reset_index().assign(region="other", coord_confidence="high"))
        self.assertEqual(stats["no_station"], ["queens_park_chesterfield"])
        self.assertEqual(len(stats["country_mismatches"]), 1)
        self.assertEqual(stats["problems"], [])

    def test_stations_on_filters_by_date(self):
        v = V.match_stations(VENUES.assign(first_match="2003-01-01", last_match="2026-01-01"), self.isd)
        early = V.stations_on("county_ground_bristol", "2015-06-01", v, self.isd)
        self.assertNotIn("037249-99999", set(early.station))
        late = V.stations_on("county_ground_bristol", "2024-06-01", v, self.isd)
        self.assertEqual(late.station.iloc[0], "037249-99999")

    def test_scan_and_audit(self):
        z = Path(self.tmp.name) / "all_json.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("1.json", match_json("County Ground", "Bristol", "2010-06-01"))
            f.writestr("2.json", match_json("County Ground, Bristol", "Bristol", "2020-06-01"))
            f.writestr("3.json", match_json("The Royal & Sun Alliance County Ground, Bristol", "Bristol", "2003-06-01"))
            f.writestr("4.json", match_json("Queen's Park", None, "2020-03-01", innings_first=True))
            f.writestr("5.json", match_json("County Ground", "Taunton", "2012-06-01"))
            f.writestr("README.txt", "not a match")
        scan = V.scan_cricsheet_venues(z)
        self.assertEqual(len(scan), 5)
        self.assertEqual(set(scan.match_id), {"1", "2", "3", "4", "5"})
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
        r = V.refresh(VENUES, scan, self.isd, self.cfg).set_index("venue_id")
        self.assertEqual(r.at["county_ground_bristol", "n_matches"], 3)
        self.assertEqual(r.at["county_ground_bristol", "first_match"], "2003-06-01")
        self.assertEqual(r.at["eden_park", "n_matches"], 0)
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
        v = VENUES.assign(utc_offset_hours=[0, 0, 12, 0, 12, 10], dst_region=["eu", "eu", "nz", "eu", "nz", "au_south"])
        self.assertEqual(V.utc_offset_on("eden_park", "2025-01-15", v), 13.0)


class CommittedConfigTests(unittest.TestCase):
    """Checks on the committed config and audit (small files, no network, no zip)."""

    def test_config_is_consistent(self):
        v = V.load_venues()
        stats = V.validate(v)
        self.assertEqual(stats["problems"], [])
        self.assertTrue(v.isd_station.str.fullmatch(r"(\d{6}-\d{5})?").all())
        self.assertTrue(set(v.dst_region) <= {"none", "eu", "us", "mx", "au_south", "wa", "nz", "ws", "fj", "na", "pk", "bd", "lk"})
        far = v.station_distance_km > V.MAX_KM
        self.assertFalse(far.any())
        self.assertTrue((v.station_flag[v.isd_station.eq("")] == "no_station_60km").all())
        elev = v.set_index("venue_id").elevation_m
        self.assertGreater(elev["wanderers_johannesburg"], 1700)
        self.assertGreater(elev["hpca_dharamsala"], 1400)

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
