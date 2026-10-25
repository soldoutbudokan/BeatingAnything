"""Regression checks from the independent verification of team lineage, home status and start slots."""
from __future__ import annotations

import unittest

import pandas as pd

from beating.cricket import teams as T
from beating.cricket.competitions import FULL_MEMBERS
from tests.test_cricket_teams import VENUES, frame, info, round_robin

# (Cricsheet match_id, start_slot) checked by hand against the published start times
KNOWN_SLOTS = [(1187017, "day_night"), (1359476, "day"), (1359477, "night"), (392181, "day"), (392182, "day_night"),
               (1254088, "night"), (1254101, "night"), (533284, "day"), (533285, "night")]


class CommittedTeamTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = T.load_teams()

    def test_keys_and_ids(self):
        t = self.t
        self.assertFalse(t.duplicated(["team_raw", "gender", "team_type", "competition_id"]).any())
        self.assertEqual(t.team_id.tolist(), [T.team_id_for(r, g, k) for r, g, k in zip(t.team_raw, t.gender, t.team_type)])
        self.assertTrue((t.groupby("team_id").team_name.nunique() == 1).all())
        self.assertTrue(((t.team_id.str.endswith("_w")) == t.gender.eq("female")).all())

    def test_lineage_closed(self):
        t = self.t
        ids = set(t.team_id)
        self.assertTrue(set(t.succeeds) - {""} <= ids)
        root = t.drop_duplicates("team_id").set_index("team_id")
        self.assertTrue((root.loc[sorted(set(t.lineage_id)), "succeeds"] == "").all())
        for tid, pred in t.loc[t.succeeds.ne(""), ["team_id", "succeeds"]].drop_duplicates().values:
            self.assertEqual(root.at[tid, "lineage_id"], root.at[pred, "lineage_id"])

    def test_full_members(self):
        i = self.t[self.t.team_type.eq("international") & self.t.country.ne("")]
        self.assertEqual(i.full_member_from.tolist(), [FULL_MEMBERS.get(c, "") for c in i.country])
        self.assertTrue(self.t.loc[self.t.team_type.eq("club"), "full_member_from"].eq("").all())


class CommittedSlotTableTests(unittest.TestCase):
    def test_invariants(self):
        s = T.load_start_slots()
        self.assertTrue(s.match_id.is_unique)
        self.assertTrue(s.start_slot.isin(T.SLOTS).all())
        self.assertTrue((s.confidence.eq("") == s.start_slot.eq("unknown")).all())
        self.assertEqual(int(s.source.eq("pink_ball_list").sum()), len(T.PINK_BALL_TESTS))
        self.assertEqual(sorted(s.loc[s.source.eq("pink_ball_list"), "start_date"]), sorted(p[0] for p in T.PINK_BALL_TESTS))

    def test_known_slots(self):
        for mid, want in KNOWN_SLOTS:
            self.assertEqual(T.start_slot_for(mid), want, mid)


class SlotRuleTests(unittest.TestCase):
    def test_simultaneous_league_games(self):
        m = frame([info("2021-10-08", "Sunrisers Hyderabad", "Mumbai Indians", "dubai", number=55),
                   info("2021-10-08", "Royal Challengers Bangalore", "Delhi Capitals", "dubai", number=56),
                   info("2021-10-10", "Delhi Capitals", "Chennai Super Kings", "dubai", number=57),
                   info("2021-10-10", "Mumbai Indians", "Punjab Kings", "dubai", number=58)])
        s = T.start_slots(m, VENUES)
        self.assertEqual(s.start_slot.tolist(), ["night", "night", "day", "night"])
        self.assertEqual(s.source.iloc[0], "simultaneous_league_games")


class AsOfTests(unittest.TestCase):
    def test_truncation_invariance_with_outgrounds_and_blocked_schedule(self):
        homes = {"Chennai Super Kings": "chepauk", "Mumbai Indians": "wankhede", "Kolkata Knight Riders": "eden",
                 "Royal Challengers Bangalore": "chinnaswamy"}
        s1 = round_robin("2018", homes, n_rounds=4)
        s2 = round_robin("2019", homes, n_rounds=4)
        s2[0]["venue"] = s2[6]["venue"] = "guwahati"            # an outground used twice
        s3 = sorted(round_robin("2020", homes, n_rounds=4), key=lambda x: x["venue"])   # venue-blocked fixtures
        for k, x in enumerate(s3):
            x["dates"] = [f"2020-04-{k + 1:02d}"]
        m = frame(s1 + s2 + s3)
        full, _ = T.home_status_table(m, VENUES)
        cols = ["home_status1", "home_status2", "home_source1", "home_source2"]
        for day in sorted(m.start_date.unique())[::3]:
            part, _ = T.home_status_table(m[m.start_date <= day], VENUES)
            want = full.set_index("match_id").loc[part.match_id, cols].reset_index(drop=True)
            pd.testing.assert_frame_equal(part[cols].reset_index(drop=True), want)

    def test_world_xi_is_never_home(self):
        at = T.venue_countries(VENUES)
        self.assertEqual(T.intl_status(T.intl_country("ICC World XI"), "Australia", at["scg"]), "away")
        self.assertEqual(T.intl_status(T.intl_country("World XI"), "Pakistan", at["dubai"]), "neutral")


if __name__ == "__main__":
    unittest.main()
