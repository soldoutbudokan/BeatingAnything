"""As-of club home status: blocked fixtures, hub seasons, moved grounds and teams new to a competition."""
from __future__ import annotations

import unittest

import pandas as pd

from beating.cricket import teams as T
from tests.test_cricket_teams import VENUES, frame, info, round_robin

ENGLAND = pd.concat([VENUES, pd.DataFrame([
    dict(venue_id=v, country="England", cricket_country="England", utc_offset_hours=0.0, dst_region="eu")
    for v in ("oval", "trent_bridge", "headingley")])], ignore_index=True)
HOMES = {"Chennai Super Kings": "chepauk", "Mumbai Indians": "wankhede", "Kolkata Knight Riders": "eden",
         "Royal Challengers Bangalore": "chinnaswamy"}
COLS = ["home_status1", "home_status2", "home_source1", "home_source2"]


def redate(infos, start: str):
    for k, x in enumerate(infos):
        x["dates"] = [str((pd.Timestamp(start) + pd.Timedelta(days=k)).date())]
        x["season"] = start[:4]
        x["event"]["match_number"] = k + 1
    return infos


def season(year: str, homes=HOMES, n_rounds=2, blocked=False, hub=None, **kw):
    s = round_robin(year, homes, n_rounds=n_rounds, hub=hub, **kw)
    return redate(sorted(s, key=lambda x: x["venue"]) if blocked else s, f"{year}-04-01")


def labelled(infos, venues=VENUES):
    m = frame(infos)
    st, homes = T.home_status_table(m, venues)
    return m.merge(st, on="match_id"), homes


class BlockedFixtureTests(unittest.TestCase):
    def test_host_share_uses_the_expected_season_length(self):
        hv = T.HomeVenues({"x": "India", "y": "India"}, {"ipl": "India"})
        for k in range(11):   # 11 of the first 18 games at x, Karachi Kings-like side k in 6 of them
            hv.add("ipl", "2023", f"2023-02-{k + 1:02d}", "x", ("k", f"o{k % 5}") if k < 6 else (f"o{k % 5}", "p"))
        for k in range(7):
            hv.add("ipl", "2023", f"2023-03-{k + 1:02d}", "y", ("p", f"o{k % 5}"))
        s = hv.seasons["ipl"]["2023"]
        self.assertEqual(hv.owner("ipl", s, "x"), (None, "host_share"))       # 11/18 > 40% so far
        self.assertEqual(hv.owner("ipl", s, "x", n_expected=34), ("k", ""))   # 11/34 of the season it will be

    def test_blocked_season_matches_full_labels(self):
        m, _ = labelled(season("2019", n_rounds=6) + season("2020", n_rounds=6, blocked=True))
        cur = m[m.season.eq("2020")]
        # the first block has 9 straight games at Chepauk: not a hub, every game has a home side
        self.assertFalse(cur.home_source1.eq("season_neutral").any())
        self.assertEqual(cur.home_status1.tolist(), cur.home_status1_full.tolist())
        self.assertEqual(cur.home_status2.tolist(), cur.home_status2_full.tolist())
        self.assertTrue(cur.home_status1.eq("home").all())

    def test_true_hub_still_turns_neutral(self):
        m, _ = labelled(season("2019") + season("2020", hub="wankhede"))
        cur = m[m.season.eq("2020")]
        self.assertTrue(cur.home_status1_full.eq("neutral").all())
        # Mumbai's own early games at its ground read as home; after 8 games the hub shows
        self.assertEqual(cur.home_status2.iloc[0], "home")
        self.assertTrue(cur.home_source1.iloc[8:].eq("season_neutral").all())
        self.assertTrue(cur.home_status1.iloc[8:].eq("neutral").all())


class PriorSeasonTests(unittest.TestCase):
    def test_hub_season_skipped_and_former_ground_kept(self):
        moved = {**HOMES, "Chennai Super Kings": "guwahati"}
        m, _ = labelled(season("2016") + season("2017", moved) + season("2018", hub="motera") + season("2019"))
        cur = m[m.season.eq("2019")]
        csk = cur[cur.team1_raw.eq("Chennai Super Kings")]
        # Chennai's first 2019 game is back at Chepauk: its 2016 ground, Guwahati being its 2017 one
        self.assertEqual((csk.home_status1.iloc[0], csk.home_source1.iloc[0]), ("home", "prev:2017"))
        self.assertEqual(cur.home_status1.tolist(), cur.home_status1_full.tolist())
        first = cur.iloc[0]
        self.assertEqual(first.home_source1, "prev:2017")   # the 2018 hub season has no home grounds

    def test_lookback_limit(self):
        m, _ = labelled(season("2010") + season("2019"))
        self.assertEqual(m[m.season.eq("2019")].home_source1.iloc[0], "none")
        m, _ = labelled(season("2015") + season("2019"))
        self.assertEqual(m[m.season.eq("2019")].home_source1.iloc[0], "prev:2015")

    def test_new_competition_uses_the_team_elsewhere(self):
        counties = {"Surrey": "oval", "Nottinghamshire": "trent_bridge", "Yorkshire": "headingley",
                    "Middlesex": "lords"}
        blast = redate(round_robin("2014", counties, event="Vitality Blast"), "2014-05-01")
        odc = redate(round_robin("2014", counties, event="Royal London One-Day Cup"), "2014-07-01")
        for x in odc:
            x["match_type"] = "ODM"
        m, _ = labelled(blast + odc, ENGLAND)
        first = m[m.competition_id.eq("eng_one_day_cup")].iloc[0]
        self.assertEqual((first.home_status1, first.home_status2), ("home", "away"))
        self.assertEqual(first.home_source1, "other:blast:2014")
        self.assertEqual(m[m.competition_id.eq("blast")].home_source1.iloc[0], "none")

    def test_truncation_invariance(self):
        moved = {**HOMES, "Chennai Super Kings": "guwahati"}
        infos = season("2016") + season("2017", moved, n_rounds=4, blocked=True) + season("2018", hub="motera")
        m = frame(infos)
        full, _ = T.home_status_table(m, VENUES)
        for day in sorted(m.start_date.unique())[::5]:
            part, _ = T.home_status_table(m[m.start_date <= day], VENUES)
            want = full.set_index("match_id").loc[part.match_id, COLS].reset_index(drop=True)
            pd.testing.assert_frame_equal(part[COLS].reset_index(drop=True), want)


class HomeStatusFunctionTests(unittest.TestCase):
    def test_unknown_venue_raises(self):
        hv = T.home_venues_at(frame(season("2024")), None, VENUES)
        with self.assertRaises(KeyError):
            T.home_status("mumbai_indians_m", "chennai_super_kings_m", "club", "nowhere", "ipl", "2025",
                          "2025-03-22", homes=hv, venues=VENUES)
        with self.assertRaises(KeyError):
            T.home_status("india_m", "australia_m", "international", "nowhere", venues=VENUES,
                          team_countries=("India", "Australia"))

    def test_asof_report_section(self):
        m, homes = labelled(season("2019") + season("2020", n_rounds=4, blocked=True))
        rep = T._asof_vs_full(m)
        self.assertEqual(rep["n_matches"], len(m))
        self.assertEqual(sum(rep["by_kind"].values()), len(m))
        self.assertGreater(rep["agreement"], 0.5)
        self.assertEqual(rep["coverage_full"], 1.0)
        self.assertEqual(rep["home_win_agree"]["home_win_rate"], 1.0)   # round_robin's home sides always win


if __name__ == "__main__":
    unittest.main()
