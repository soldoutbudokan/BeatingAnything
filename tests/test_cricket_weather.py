from __future__ import annotations

import gzip
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from beating.cricket import weather as W


def isd_line(y, m, d, h, t=-9999, td=-9999, slp=-9999, wd=-9999, ws=-9999, sky=-9999, p1=-9999, p6=-9999) -> str:
    return f"{y:4d} {m:02d} {d:02d} {h:02d} {t:5d} {td:5d} {slp:5d} {wd:5d} {ws:5d} {sky:5d} {p1:5d} {p6:5d}"


def hourly_fixture(over=None, days=6, start=(2023, 6, 1)) -> np.ndarray:
    """Hourly rows from 00 UTC on `start` for `days` days: T 20.0 C, Td 10.0 C, SLP 1013.0, wind 4.0 m/s,
    sky 4 oktas, 1-hour precipitation 0; `over` maps (day_index, hour) to field overrides."""
    t0 = pd.Timestamp(f"{start[0]}-{start[1]:02d}-{start[2]:02d}")
    lines = []
    for k in range(days * 24):
        ts = t0 + pd.Timedelta(hours=k)
        f = dict(t=200, td=100, slp=10130, wd=180, ws=40, sky=4, p1=0, p6=-9999)
        f.update((over or {}).get((k // 24, ts.hour), {}))
        lines.append(isd_line(ts.year, ts.month, ts.day, ts.hour, **f))
    return W.read_isd_lite("\n".join(lines).encode())


GSOD_HEAD = ('"STATION","DATE","LATITUDE","LONGITUDE","ELEVATION","NAME","TEMP","TEMP_ATTRIBUTES","DEWP",'
             '"DEWP_ATTRIBUTES","SLP","SLP_ATTRIBUTES","STP","STP_ATTRIBUTES","VISIB","VISIB_ATTRIBUTES","WDSP",'
             '"WDSP_ATTRIBUTES","MXSPD","GUST","MAX","MAX_ATTRIBUTES","MIN","MIN_ATTRIBUTES","PRCP",'
             '"PRCP_ATTRIBUTES","SNDP","FRSHTT"')


def gsod_csv(rows) -> bytes:
    """rows: (date, temp_F, dewp_F, prcp_in, flag, frshtt)."""
    out = [GSOD_HEAD]
    for d, t, td, p, fl, fr in rows:
        out.append(f'"03772099999","{d}","51.4","-0.4","25.0","HEATHROW","{t:6.1f}","24","{td:6.1f}","24",'
                   f'"1013.0","24","999.9"," 0","  7.5","24","  7.5","24"," 11.1","999.9","  73.9"," ",'
                   f'"  49.1"," ","{p:5.2f}","{fl}","999.9","{fr}"')
    return ("\n".join(out) + "\n").encode()


class ParseTests(unittest.TestCase):
    def test_read_isd_lite_plain_and_gzip(self):
        raw = (isd_line(2024, 1, 1, 0, 81, 53, 9955, 230, 88, 8, 0, 2) + "\n" +
               isd_line(2024, 1, 1, 1, -12, -9999, 9963, 240, 88, 5, -1, -9999)).encode()
        for b in (raw, gzip.compress(raw)):
            a = W.read_isd_lite(b)
            self.assertEqual(a.shape, (2, 12))
            self.assertEqual(a[1, 4], -12)
            self.assertEqual(a[1, 10], -1)

    def test_utc_hours_and_local_clock(self):
        a = W.read_isd_lite(isd_line(2023, 7, 1, 12).encode())
        h = W.utc_hours(a)
        self.assertEqual(h[0], int(pd.Timestamp("2023-07-01 12:00").value // 3_600_000_000_000))
        self.assertEqual(W.local_clock(h, 0.0, "eu")[0] - h[0], 1.0)  # British Summer Time
        self.assertEqual(W.local_clock(h, 5.5, "none")[0] - h[0], 5.5)
        winter = W.utc_hours(W.read_isd_lite(isd_line(2023, 1, 10, 12).encode()))
        self.assertEqual(W.local_clock(winter, 0.0, "eu")[0] - winter[0], 0.0)

    def test_local_day_utc_years(self):
        self.assertEqual(W.local_day_utc_years(pd.Timestamp("2024-01-01"), 13.0), {2023, 2024})
        self.assertEqual(W.local_day_utc_years(pd.Timestamp("2023-12-31"), -4.0), {2023, 2024})
        self.assertEqual(W.local_day_utc_years(pd.Timestamp("2023-06-15"), 5.5), {2023})


class IsdDayTests(unittest.TestCase):
    def test_day_window_means_and_magnus(self):
        d = W.isd_days(hourly_fixture(), 0.0, "none")
        r = d.loc["2023-06-02"]
        self.assertEqual(r.n_obs, 13)  # 10:00..22:00 inclusive
        self.assertAlmostEqual(r.temp_c_mean, 20.0)
        self.assertAlmostEqual(r.rh_mean, float(W.magnus_rh(20.0, 10.0)), places=6)
        self.assertAlmostEqual(r.rh_mean, 52.5, delta=0.3)
        self.assertAlmostEqual(r.dew_depression_evening, 10.0)
        self.assertEqual(r.n_obs_evening, 6)
        self.assertAlmostEqual(r.cloud_oktas_mean, 4.0)
        self.assertAlmostEqual(r.pressure_hpa_mean, 1013.0)
        self.assertAlmostEqual(r.wind_ms_mean, 4.0)
        self.assertEqual(r.isd_precip_mm, 0.0)
        self.assertEqual(r.precip_hours, 0)

    def test_window_follows_local_time_and_dst(self):
        over = {(1, 9): dict(t=400)}  # 09 UTC = 10:00 BST, inside the window only with DST applied
        d_dst = W.isd_days(hourly_fixture(over), 0.0, "eu").loc["2023-06-02"]
        d_std = W.isd_days(hourly_fixture(over), 0.0, "none").loc["2023-06-02"]
        self.assertGreater(d_dst.temp_c_mean, 20.0)
        self.assertAlmostEqual(d_std.temp_c_mean, 20.0)

    def test_evening_window_and_minimum_obs(self):
        over = {(1, h): dict(t=-9999) for h in range(24) if h not in (11, 12)}
        d = W.isd_days(hourly_fixture(over), 0.0, "none").loc["2023-06-02"]
        self.assertEqual(d.n_obs, 2)
        self.assertTrue(np.isnan(d.temp_c_mean) and np.isnan(d.rh_mean))
        over = {(1, h): dict(td=50) for h in (18, 19)}
        d = W.isd_days(hourly_fixture(over), 0.0, "none").loc["2023-06-02"]
        self.assertAlmostEqual(d.dew_depression_evening, (2 * 15 + 4 * 10) / 6)

    def test_sky_codes(self):
        over = {(1, h): dict(sky=c) for h, c in [(10, 9), (11, 15), (12, 18), (13, 0)]}
        d = W.isd_days(hourly_fixture(over), 0.0, "none").loc["2023-06-02"]
        self.assertEqual(d.n_cloud, 12)  # code 9 is missing
        self.assertAlmostEqual(d.cloud_oktas_mean, (9 * 4 + 7 + 8 + 0) / 12)

    def test_uninformative_cloud_station_year(self):
        over = {(k, h): dict(sky=0 if h % 2 else 9) for k in range(6) for h in range(24)}
        d = W.isd_days(hourly_fixture(over), 0.0, "none")
        self.assertTrue(d.cloud_oktas_mean.isna().all())

    def test_precip_hourly_and_six_hour_without_double_count(self):
        over = {(1, 11): dict(p1=20), (1, 12): dict(p1=-1),  # 2.0 mm, then trace
                (1, 17): dict(p1=-9999), (1, 18): dict(p1=-9999, p6=30)}  # 6 h to 18 UTC: 3.0 mm, 1-h has 0
        d = W.isd_days(hourly_fixture(over), 0.0, "none").loc["2023-06-02"]
        self.assertAlmostEqual(d.isd_precip_mm, 2.0 + 3.0)
        self.assertEqual(d.precip_hours, 2)  # 2.0 mm hour and the trace hour

    def test_precip_cover_too_low(self):
        over = {(1, h): dict(p1=-9999) for h in range(1, 24)}
        d = W.isd_days(hourly_fixture(over), 0.0, "none").loc["2023-06-02"]
        self.assertTrue(np.isnan(d.isd_precip_mm))
        self.assertTrue(np.isnan(d.precip_hours))

    def test_hourly_precip_overlapping_six_hour_reports(self):
        p1 = np.full(24, np.nan)
        p6 = np.full(24, np.nan)
        p6[5], p6[6], p6[11] = 6.0, 6.0, 1.2  # the report ending at 6 overlaps the one ending at 5
        amt, known = W.hourly_precip(p1, p6)
        self.assertAlmostEqual(np.nansum(amt), 7.2)
        self.assertEqual(known.sum(), 12)

    def test_impossible_station_days_dropped(self):
        over = {(1, h): dict(t=550) for h in range(24)}
        over |= {(2, h): dict(td=205) for h in range(24)}  # dew point 0.5 C above air temperature all day
        d = W.isd_days(hourly_fixture(over), 0.0, "none")
        self.assertTrue(d.loc["2023-06-02", "bad"] and d.loc["2023-06-03", "bad"])
        self.assertTrue(np.isnan(d.loc["2023-06-02", "temp_c_mean"]))
        self.assertTrue(np.isnan(d.loc["2023-06-03", "rh_mean"]))
        self.assertFalse(d.loc["2023-06-04", "bad"])

    def test_failed_hygrometer_day_loses_dew_point_only(self):
        over = {(3, h): dict(td=-200) for h in range(24)}  # 30 C below the month's median dew point
        over |= {(4, h): dict(td=-100) for h in range(24)}  # 20 C below: kept (real dry spells)
        d = W.isd_days(hourly_fixture(over, days=10), 0.0, "none")
        self.assertTrue(d.loc["2023-06-04", "bad_dewpt"])
        self.assertTrue(d.loc["2023-06-04", ["dewpt_c_mean", "rh_mean", "dew_depression_evening"]].isna().all())
        self.assertAlmostEqual(d.loc["2023-06-04", "temp_c_mean"], 20.0)
        self.assertFalse(d.loc["2023-06-05", "bad_dewpt"])
        self.assertAlmostEqual(d.loc["2023-06-05", "dewpt_c_mean"], -10.0)


class GsodTests(unittest.TestCase):
    def test_read_gsod_flags_and_units(self):
        g = W.read_gsod(gsod_csv([
            ("2023-06-01", 68.0, 50.0, 0.50, "G", "010000"),
            ("2023-06-02", 68.0, 50.0, 0.00, "I", "000000"),
            ("2023-06-03", 68.0, 50.0, 0.00, "H", "000010"),
            ("2023-06-04", 68.0, 50.0, 0.00, "A", "000000"),
            ("2023-06-05", 68.0, 50.0, 0.10, "A", "010000"),
            ("2023-06-06", 9999.9, 9999.9, 99.99, "", "010000"),
        ]))
        self.assertAlmostEqual(g.loc["2023-06-01", "g_temp"], 20.0)
        self.assertAlmostEqual(g.loc["2023-06-01", "g_prcp"], 12.7)
        self.assertTrue(np.isnan(g.loc["2023-06-02", "g_prcp"]))
        self.assertEqual(g.loc["2023-06-03", "g_prcp"], 0.0)
        self.assertEqual(g.loc["2023-06-03", "rain_flag"], 1.0)
        self.assertEqual(g.loc["2023-06-03", "thunder_flag"], 1.0)
        self.assertTrue(np.isnan(g.loc["2023-06-04", "g_prcp"]))
        self.assertAlmostEqual(g.loc["2023-06-05", "g_prcp"], 2.54)
        self.assertTrue(np.isnan(g.loc["2023-06-06", "g_temp"]) and np.isnan(g.loc["2023-06-06", "g_prcp"]))

    def lag_frame(self, shift: int) -> pd.DataFrame:
        rng = np.random.default_rng(1)
        idx = pd.date_range("2023-01-01", periods=200)
        rain = (rng.random(200) < 0.3).astype(float)
        amt = np.where(rain > 0, rng.uniform(1, 20, 200), 0.0)
        return pd.DataFrame(dict(g_prcp=np.roll(amt, shift), g_flag="G", rain_flag=rain), index=idx)

    def test_gsod_lag(self):
        self.assertEqual(W.gsod_lag(self.lag_frame(1))[0], 1)
        self.assertEqual(W.gsod_lag(self.lag_frame(0))[0], 0)

    def test_lagged_precip_moves_only_flag_g(self):
        g = pd.DataFrame(dict(g_prcp=[1.0, 2.0, 3.0], g_flag=["G", "F", "G"]),
                         index=pd.DatetimeIndex(["2023-01-02", "2023-01-03", "2023-01-04"]))
        p = W.lagged_precip(g, 1)
        self.assertEqual(p.loc["2023-01-01", "g_prcp"], 1.0)
        self.assertEqual(p.loc["2023-01-03", "g_prcp"], 3.0)  # G from the 4th wins over F on the 3rd
        self.assertNotIn(pd.Timestamp("2023-01-04"), p.index)


class AssembleTests(unittest.TestCase):
    def test_field_fallback(self):
        days = pd.date_range("2023-06-02", periods=2)
        a = W.isd_days(hourly_fixture({(k, h): dict(sky=9, p1=-9999) for k in range(6) for h in range(24)}),
                       0.0, "none")
        b = W.isd_days(hourly_fixture({(k, h): dict(t=250, sky=8) for k in range(6) for h in range(24)}),
                       0.0, "none")
        g = W.read_gsod(gsod_csv([("2023-06-02", 68.0, 50.0, 0.20, "D", "010000"),
                                  ("2023-06-03", 68.0, 50.0, 0.00, "I", "000000")]))
        out = W.assemble(days, [("AAA", 3.0), ("BBB", 20.0)], [a, b], [g, None])
        self.assertEqual(out.station.tolist(), ["AAA", "AAA"])
        self.assertEqual(out.source.tolist(), ["isd_lite", "isd_lite"])
        self.assertAlmostEqual(out.temp_c_mean.iloc[0], 20.0)
        self.assertEqual(out.cloud_station.tolist(), ["BBB", "BBB"])
        self.assertAlmostEqual(out.cloud_oktas_mean.iloc[0], 8.0)
        self.assertEqual(out.precip_source.tolist(), ["gsod", "isd_lite"])
        self.assertEqual(out.precip_station.tolist(), ["AAA", "BBB"])
        self.assertAlmostEqual(out.precip_mm_day.iloc[0], 5.08)
        self.assertEqual(out.wet_day.tolist(), [1.0, 0.0])
        self.assertEqual(out.rain_flag.iloc[0], 1.0)

    def test_gsod_core_when_no_isd(self):
        days = pd.date_range("2023-06-02", periods=1)
        g = W.read_gsod(gsod_csv([("2023-06-02", 68.0, 50.0, 0.20, "G", "010000")]))
        out = W.assemble(days, [("AAA", 3.0)], [None], [g])
        self.assertEqual(out.source.iloc[0], "gsod")
        self.assertAlmostEqual(out.temp_c_mean.iloc[0], 20.0)
        self.assertTrue(np.isnan(out.cloud_oktas_mean.iloc[0]))

    def test_needs(self):
        f = pd.DataFrame(dict(x=[1.0, np.nan, 1.0]), index=pd.date_range("2023-01-01", periods=3))
        self.assertTrue(W.needs(f, pd.DatetimeIndex(["2023-01-02"]), False, ["x"]))
        self.assertFalse(W.needs(f, pd.DatetimeIndex(["2023-01-01"]), False, ["x"]))
        self.assertTrue(W.needs(f, pd.DatetimeIndex([]), True, ["x"]))


class FetchTests(unittest.TestCase):
    def test_fetch_caches_and_records_404(self):
        calls = []

        def get(url):
            calls.append(url)
            return ("404", b"") if "missing" in url else ("ok", b"data")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = [("u/ok", root / "2023" / "a.gz"), ("u/missing", root / "2023" / "b.gz")]
            c = W.fetch(jobs, root, workers=2, get=get, log_every=0)
            self.assertEqual((c["ok"], c["404"]), (1, 1))
            self.assertEqual((root / "2023" / "a.gz").read_bytes(), b"data")
            self.assertEqual(W.read_missing(root), {"2023/b.gz"})
            c = W.fetch(jobs, root, workers=2, get=get, log_every=0)
            self.assertEqual(c["requested"], 0)
            self.assertEqual(len(calls), 2)

    def test_station_store_reads_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            isd_root, gsod_root = Path(tmp) / "isd", Path(tmp) / "gsod"
            raw = "\n".join(isd_line(2023, 6, 1, h, 200, 100, 10130, 0, 40, 4, 0) for h in range(24)).encode()
            p = W.isd_lite_path("037720-99999", 2023, isd_root)
            p.parent.mkdir(parents=True)
            p.write_bytes(gzip.compress(raw))
            q = W.gsod_path("037720-99999", 2023, gsod_root)
            q.parent.mkdir(parents=True)
            q.write_bytes(gsod_csv([("2023-06-01", 68.0, 50.0, 0.0, "G", "000000")]))
            s = W.StationStore(isd_root, gsod_root)
            self.assertEqual(s.files["isd"], {"037720-99999": (2023,)})
            self.assertEqual(s.files["gsod"], {"037720-99999": (2023,)})
            self.assertAlmostEqual(s.isd("037720-99999", 0.0, "none").loc["2023-06-01", "temp_c_mean"], 20.0)
            self.assertEqual(s.gsod("037720-99999").loc["2023-06-01", "g_prcp"], 0.0)
            self.assertIsNone(s.isd("000000-99999", 0.0, "none"))


class MatchTests(unittest.TestCase):
    def test_scheduled_days(self):
        odi = dict(match_type="ODI", gender="male", dates=["2023-01-01"])
        self.assertEqual(W.scheduled_days(odi, "1", {})[0], 1)
        test = dict(match_type="Test", gender="male", dates=["2023-01-01"], teams=["A", "B"])
        d, _ = W.scheduled_days(test, "99", {"99": {"scheduled_days": 4}})
        self.assertIn(d, (4, 5))  # rules timeline when it resolves, else the override

    def test_match_days(self):
        m = pd.DataFrame([dict(match_id=1, start_date="2023-01-01", dates=["2023-01-01", "2023-01-02", "2023-01-03"],
                               scheduled_days=5),
                          dict(match_id=2, start_date="2023-02-01", dates=["2023-02-01", "2023-02-02"],
                               scheduled_days=1)])
        d = W.match_days(m)
        t = d[d.match_id == 1]
        self.assertEqual(t.day.tolist(), [1, 2, 3, 4, 5])
        self.assertEqual(t.played.tolist(), [True, True, True, False, False])
        o = d[d.match_id == 2]
        self.assertEqual(o.scheduled.tolist(), [True, False])
        self.assertEqual(o.played.tolist(), [True, True])


def day_rows(venue, dates, **cols) -> pd.DataFrame:
    n = len(dates)
    base = dict(match_id=np.arange(n), venue_id=venue, date=pd.to_datetime(dates), scheduled=True, source="isd_lite",
                precip_source="gsod", temp_c_mean=20.0, rh_mean=60.0, dewpt_c_mean=12.0, dew_depression_evening=5.0,
                cloud_oktas_mean=4.0, wind_ms_mean=3.0, precip_mm_day=0.0, wet_day=0.0, rain_flag=0.0)
    base.update(cols)
    return pd.DataFrame(base)


VENUES = pd.DataFrame(dict(venue_id=["a", "b", "c", "d", "e"], name=list("ABCDE"),
                           region=["r1", "r1", "r1", "r1", "r2"], cricket_country=["X", "X", "X", "Y", "Z"]))


class ClimatologyTests(unittest.TestCase):
    def test_raw_means_counts_and_cutoff(self):
        vd = day_rows("a", ["2023-01-05", "2023-01-06", "2023-01-07", "2023-07-01"],
                      temp_c_mean=[10.0, 12.0, np.nan, 25.0],
                      rh_mean=[80.0, 70.0, np.nan, 50.0], cloud_oktas_mean=[6.0, np.nan, np.nan, 2.0],
                      wet_day=[1.0, 0.0, 1.0, 0.0], precip_mm_day=[5.0, 0.4, np.nan, 0.0])
        vd.loc[2, "source"] = "none"  # precipitation known from the rain flag only
        c = W.climatology(None, vd, VENUES, fill=False).set_index("month")
        self.assertAlmostEqual(c.loc[1, "temp_c"], 11.0)
        self.assertAlmostEqual(c.loc[1, "rain_day_freq"], 2 / 3)
        self.assertAlmostEqual(c.loc[1, "precip_mm_rain_day"], 5.0)
        self.assertEqual((c.loc[1, "n"], c.loc[1, "n_precip"], c.loc[1, "n_cloud"]), (2, 3, 1))
        self.assertEqual(len(W.climatology("2023-02-01", vd, VENUES, fill=False)), 1)
        self.assertEqual(len(W.climatology("2023-01-05", vd, VENUES, fill=False)), 0)  # strictly before

    def test_no_leakage_after_cutoff(self):
        vd = pd.concat([day_rows("a", pd.date_range("2022-01-01", periods=40, freq="7D"), temp_c_mean=15.0),
                        day_rows("b", pd.date_range("2022-03-01", periods=30, freq="5D"), temp_c_mean=25.0)])
        c1 = W.climatology("2022-06-01", vd, VENUES)
        later = vd.date >= "2022-06-01"
        vd2 = vd.copy()
        vd2.loc[later, ["temp_c_mean", "rh_mean", "wet_day", "precip_mm_day"]] = [99.0, 1.0, 1.0, 80.0]
        vd2 = pd.concat([vd2, day_rows("c", ["2022-06-01", "2023-01-01"], temp_c_mean=-5.0)])
        pd.testing.assert_frame_equal(c1, W.climatology("2022-06-01", vd2, VENUES))
        self.assertNotEqual(c1.temp_c.sum(), W.climatology(None, vd2, VENUES).temp_c.sum())

    def test_double_header_counts_once(self):
        vd = pd.concat([day_rows("a", ["2023-01-05"], temp_c_mean=10.0),
                        day_rows("a", ["2023-01-05"], temp_c_mean=10.0),
                        day_rows("a", ["2023-01-06"], temp_c_mean=20.0, scheduled=False)])
        c = W.climatology(None, vd, VENUES, fill=False)
        self.assertEqual(c.n.tolist(), [1])

    def test_hierarchy_and_levels(self):
        jan, jul = pd.date_range("2020-01-01", periods=60, freq="D"), pd.date_range("2020-07-01", periods=25, freq="D")
        vd = pd.concat([day_rows("a", jan.append(jul), temp_c_mean=[10.0] * 31 + [11.0] * 29 + [20.0] * 25),
                        day_rows("b", jan[:31], temp_c_mean=15.0)])
        c = W.climatology(None, vd, VENUES).set_index(["venue_id", "month"])
        self.assertEqual(len(c), 5 * 12)
        lv = c.clim_level
        self.assertEqual((lv["a", 1], lv["a", 3], lv["b", 7], lv["c", 7], lv["d", 7], lv["e", 7]),
                         ("venue_month", "venue", "venue", "country", "region", "global"))
        self.assertGreater(c.loc[("b", 7), "temp_c"], c.loc[("a", 7), "temp_c"])  # warm offset carried to July
        self.assertGreater(c.loc[("a", 7), "temp_c"], c.loc[("a", 1), "temp_c"])  # country seasonality
        self.assertEqual(c.loc[("a", 7), "n"], 25)
        raw = W.climatology(None, vd, VENUES, k=1e-9).set_index(["venue_id", "month"])
        self.assertAlmostEqual(raw.loc[("a", 7), "temp_c"], 20.0, places=5)
        self.assertTrue(c.rain_day_freq.between(0, 1).all() and c.rh.between(0, 100).all())
        empty = W.climatology("2000-01-01", vd, VENUES)
        self.assertTrue(empty.temp_c.isna().all() and empty.clim_level.eq("none").all())

    def test_unseen_months_follow_own_season(self):
        days = pd.date_range("2021-04-01", "2021-10-31", freq="D")
        temp = 12 + 8 * np.cos(2 * np.pi * (days.month - 7) / 12)  # July 20 C, January 4 C, Apr-Oct only
        vd = pd.concat([day_rows("a", days, temp_c_mean=temp),
                        day_rows("e", pd.date_range("2021-01-01", periods=60, freq="D"), temp_c_mean=30.0)])
        c = W.climatology(None, vd, VENUES).set_index(["venue_id", "month"]).temp_c
        self.assertLess(abs(c["a", 1] - 4.0), 2.0)  # extrapolated, not the other hemisphere's 30 C January
        self.assertLess(abs(c["a", 7] - 20.0), 0.5)
        self.assertLess(c["b", 1], 9.0)  # same country, no data of its own: still its winter
        self.assertAlmostEqual(W.seasonal_prior(pd.DataFrame({"f": [1.0]}, pd.MultiIndex.from_tuples([("g", 1)])),
                                                pd.DataFrame({"f": [1.0]}, pd.MultiIndex.from_tuples([("g", 1)])),
                                                pd.DataFrame({"f": np.arange(12.0)}, pd.MultiIndex.from_product(
                                                    [["g"], range(1, 13)]))).f.iloc[5], 5.0)  # too few months

    def test_impute_and_json(self):
        vd = day_rows("a", pd.date_range("2020-01-01", periods=20, freq="D"), temp_c_mean=10.0)
        c = W.climatology(None, vd, VENUES)
        f = pd.DataFrame(dict(venue_id=["a", "a"], date=pd.to_datetime(["2024-01-03", "2024-01-04"]),
                              temp_c_mean=[np.nan, 30.0], rh_mean=[50.0, np.nan]))
        g = W.impute(f, c)
        self.assertAlmostEqual(g.temp_c_mean[0], 10.0)
        self.assertEqual((g.temp_c_mean[1], g.temp_c_mean_missing.tolist(), g.rh_mean_missing.tolist()),
                         (30.0, [1, 0], [0, 1]))
        j = W.climate_json(c, VENUES, dict(version=2))
        self.assertEqual(len(j["venues"]["a"]["temp_c"]), 12)
        self.assertEqual((j["venues"]["a"]["n"][0], j["venues"]["a"]["n"][1]), (20, 0))
        self.assertEqual(j["venues"]["a"]["level"][:2], ["venue_month", "venue"])
        self.assertEqual(j["venues"]["e"]["level"][0], "global")


class OutputTests(unittest.TestCase):
    def test_load_matches(self):
        m = pd.DataFrame(dict(match_id=[1, 2], file_stem=["1", "2"], start_date=["2023-01-01", "2023-02-01"],
                              dates_played=['["2023-01-01", "2023-01-02"]', '["2023-02-01"]'], venue_id="v",
                              match_type="ODI", scheduled_days=[1, 1]))
        out = W.load_matches(m)
        self.assertEqual(out.dates[0], ["2023-01-01", "2023-01-02"])
        self.assertEqual(out.scheduled_source.tolist(), ["given", "given"])
        m = m.drop(columns="scheduled_days")
        self.assertEqual(W.load_matches(m).scheduled_days.tolist(), [1, 1])  # limited overs: no zip read

    def test_match_summary_uses_scheduled_days(self):
        rows = pd.DataFrame(dict(match_id=[1, 1, 1], scheduled=[True, True, False], source="isd_lite",
                                 station="S", distance_km=5.0, n_obs=[13, 13, 13], temp_c_mean=[20.0, 22.0, 40.0],
                                 rh_mean=60.0, dewpt_c_mean=10.0, dew_depression_evening=5.0, cloud_oktas_mean=4.0,
                                 precip_mm_day=[0.0, 3.0, 50.0], precip_hours=np.nan, wind_ms_mean=3.0,
                                 pressure_hpa_mean=1010.0, wet_day=[0.0, 1.0, 1.0], rain_flag=[0.0, 1.0, 1.0],
                                 thunder_flag=0.0, elevation_m=140.0))
        m = pd.DataFrame([dict(match_id=1, start_date="2023-01-01", venue_id="v", match_type="Test", gender="male",
                               scheduled_days=2), dict(match_id=2, start_date="2026-01-01", venue_id="v",
                                                       match_type="Test", gender="male", scheduled_days=5)])
        out = W.match_summary(rows, m)
        s = out.iloc[0]
        self.assertAlmostEqual(s.temp_c_mean, 21.0)
        self.assertAlmostEqual(s.precip_mm_total, 3.0)
        self.assertEqual((s.wet_days, s.days_with_weather, s.elevation_m), (1, 2, 140.0))
        self.assertEqual(s.source, "isd_lite")
        self.assertEqual((out.source[1], out.days_with_weather[1]), ("none", 0))  # no rows: after the data end

    def test_sanity_and_coverage(self):
        rng = np.random.default_rng(1)
        n = 60
        res = ["no_result"] * 8 + ["win"] * 52
        meth = [None] * 8 + ["D/L"] * 8 + [None] * 44
        p = np.r_[rng.uniform(8, 30, 16), rng.exponential(0.5, 44)]
        dates = pd.date_range("2024-01-01", periods=n, freq="5D")
        rows = day_rows("a", dates, match_id=np.arange(n), precip_mm_day=p, wet_day=(p >= 1).astype(float),
                        precip_hours=np.nan, rain_flag=(p >= 1).astype(float), thunder_flag=0.0, station="S",
                        distance_km=4.0, n_obs=13.0, pressure_hpa_mean=1010.0, played=True, station_rank=1.0,
                        cloud_station="S", elevation_m=10.0)
        rows.loc[rows.date > "2024-08-24", ["source", "precip_source"]] = "none"
        rows.loc[rows.date > "2024-08-24", W.CORE + ["precip_mm_day", "wet_day", "rain_flag"]] = np.nan
        m = pd.DataFrame(dict(match_id=np.arange(n), start_date=dates.strftime("%Y-%m-%d"), venue_id="a", fam="T20",
                              match_type="T20", gender="male", scheduled_days=1, result=res, method=meth,
                              scheduled_source="limited_overs"))
        summ = W.match_summary(rows, m)
        san = W.sanity_checks(summ, m, rows, VENUES)
        self.assertTrue(san["limited_overs"]["passed"])
        self.assertGreater(san["limited_overs"]["no_result"]["precip_mm_mean"],
                           san["limited_overs"]["completed"]["precip_mm_mean"])
        self.assertEqual(san["rain_flag_vs_amount"]["flag_given_ge1mm"], 1.0)
        cov = W.coverage_report(m, rows, summ, VENUES.assign(utc_offset_hours=0.0), pd.Timestamp("2024-08-24"))
        self.assertEqual(cov["after_data_end"]["n_with_weather"], 0)
        self.assertEqual(cov["after_data_end"]["n_matches"], int((dates > "2024-08-24").sum()))
        self.assertEqual(cov["match_share_with_weather"]["to_data_end"], 1.0)

    def test_clean_json(self):
        self.assertEqual(W.clean_json({"a": [np.nan, np.int64(2), 1.5]}), {"a": [None, 2, 1.5]})


if __name__ == "__main__":
    unittest.main()
