"""Regression checks from the independent verification of the venue table (committed files only, no zip)."""
from __future__ import annotations

import unittest

from beating.cricket import venues as V

# (venue_id, local date, UTC offset) checked against the IANA tz database for the ground's zone
OFFSETS = [
    ("waca", "2008-01-16", 9.0), ("waca", "2009-03-29", 8.0), ("waca", "2012-12-14", 8.0),
    ("perth_stadium", "2018-12-14", 8.0), ("adelaide_oval", "2019-01-15", 10.5), ("gabba", "2019-01-15", 10.0),
    ("lords", "2019-07-14", 1.0), ("the_oval", "2019-03-01", 0.0), ("premadasa_stadium", "2005-08-01", 6.0),
    ("premadasa_stadium", "2012-09-20", 5.5), ("national_stadium_karachi", "2008-07-01", 6.0),
    ("wanderers_windhoek", "2015-06-01", 1.0), ("wanderers_windhoek", "2019-06-01", 2.0),
    ("shere_bangla_stadium", "2009-07-01", 7.0), ("basin_reserve", "2008-01-10", 13.0),
    ("providence_stadium", "2010-05-01", -4.0), ("sabina_park", "2010-05-01", -5.0),
    ("tu_kirtipur", "2024-02-01", 5.75),
]


class VerifiedConfigTests(unittest.TestCase):
    def test_wa_daylight_saving_trial(self):
        s = V.dst_shift
        self.assertEqual((s("wa", "2006-12-02"), s("wa", "2006-12-03"), s("wa", "2007-03-25")), (0, 1, 0))
        self.assertEqual((s("wa", "2008-01-16"), s("wa", "2008-10-26"), s("wa", "2009-03-29")), (1, 1, 0))
        self.assertEqual(s("wa", "2010-01-10"), 0)

    def test_offsets_match_tz_database(self):
        v = V.load_venues()
        for vid, day, want in OFFSETS:
            self.assertEqual(V.utc_offset_on(vid, day, v), want, (vid, day))

    def test_elevations_plausible(self):
        e = V.load_venues().set_index("venue_id").elevation_m
        self.assertLess(e["cazalys_stadium"], 50)  # ISD's Cairns Racecourse row says 401 m
        self.assertTrue(e.between(-10, 2700).all())


if __name__ == "__main__":
    unittest.main()
