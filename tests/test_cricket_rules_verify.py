"""Regression tests for the fixes made when independently verifying the rules timeline."""
from __future__ import annotations

import unittest

from beating.cricket.competitions import competition_for
from beating.cricket.rules import (FIELDS, _annotate, check_caught_crossing, check_review_limits, rules_for,
                                   scan_match)
from tests.test_cricket_rules import ball, info, innings, match


def intl(date, teams, mt="ODI", gender="male", event="X tour of Y"):
    return info(event, mt, gender, "international", date=date, teams=teams)


class DrsAllowedTests(unittest.TestCase):
    def test_selected_scope_is_allowed(self):
        r = rules_for("intl_odi_w", "ODI", "female", "2023-07-01", teams=["England", "Ireland"], event_id="bilateral")
        self.assertEqual((r["drs_available"], r["drs_scope"], r["drs_allowed"]), (False, "selected", True))
        self.assertFalse(rules_for("blast", "T20", "male", "2023-06-01")["drs_allowed"])
        self.assertTrue(rules_for("blast", "T20", "male", "2023-07-15", knockout=True)["drs_allowed"])
        self.assertFalse(rules_for("intl_t20_m", "T20", "male", "2016-01-01", teams=["England", "India"])["drs_allowed"])

    def test_associate_v_full_member_drs(self):
        from beating.cricket.rules import rules_for_match
        r = rules_for_match(intl("2022-06-17", ("England", "Netherlands")))
        self.assertEqual((r["drs_allowed"], r["reviews_per_innings"]), (True, 2))
        league2 = rules_for_match(intl("2022-06-11", ("Nepal", "United States of America"),
                                       event="ICC Men's Cricket World Cup League 2"))
        self.assertEqual((league2["drs_allowed"], league2["reviews_per_innings"]), (False, None))
        q23 = rules_for_match(intl("2023-07-03", ("Netherlands", "Oman"), event="ICC Cricket World Cup Qualifier"))
        self.assertTrue(q23["drs_allowed"])
        cwg = rules_for_match(intl("2022-07-31", ("Barbados", "Australia"), "T20", "female",
                                   "Commonwealth Games Women's Cricket Competition"))
        self.assertTrue(cwg["drs_allowed"])
        self.assertFalse(rules_for_match(intl("2016-01-01", ("England", "Ireland"), "ODI", "female"))["drs_allowed"])


class CaughtCrossingTests(unittest.TestCase):
    def test_timeline(self):
        self.assertIn("caught_crossing_counts", FIELDS)
        c = lambda cid, fmt, d, **kw: rules_for(cid, fmt, kw.pop("gender", "male"), d, **kw)["caught_crossing_counts"]
        self.assertTrue(c("intl_t20_m", "T20", "2022-09-01", teams=["England", "Pakistan"]))
        self.assertFalse(c("intl_t20_m", "T20", "2022-10-02", teams=["England", "Pakistan"]))
        self.assertTrue(c("ipl", "T20", "2021-10-15"))
        self.assertFalse(c("ipl", "T20", "2022-03-26"))
        self.assertTrue(c("blast", "T20", "2021-09-18"))
        self.assertFalse(c("county_championship", "TEST", "2022-04-07"))
        self.assertFalse(c("hundred_w", "HUNDRED", "2021-07-21", gender="female"))
        self.assertFalse(c("aus_one_day_cup", "ODI", "2022-09-23"))
        self.assertTrue(c("bbl", "T20", "2022-01-28"))
        self.assertTrue(c("cpl", "T20", "2022-09-30"))

    def test_scan_and_check(self):
        catch = ball(0, wicket="caught")
        after = dict(ball(1), batter="y", non_striker="z")  # old non-striker on strike: batters crossed
        inn = innings("A", specials={(5, 0): [catch, after]})
        s = _annotate([scan_match(match(info("Indian Premier League", date="2023-04-01"), [inn, innings("B")]), "1")])
        self.assertEqual((s[0]["innings"][0]["catches_mid_over"], s[0]["innings"][0]["catches_crossed"]), (1, 1))
        rows = check_caught_crossing(s * 3)
        self.assertEqual((rows[0]["rule"], rows[0]["old_non_striker_on_strike"], rows[0]["status"]), (False, 3, "conflict"))


class HundredAndReviewTests(unittest.TestCase):
    def test_hundred_detected_by_balls_per_over(self):
        self.assertEqual(competition_for(info(None, bpo=5)).fmt, "HUNDRED")
        self.assertEqual(competition_for(info("The Hundred Men's Competition")).fmt, "HUNDRED")
        self.assertEqual(competition_for(info("Vitality Blast")).fmt, "T20")

    def test_failed_review_without_drs_in_rules_is_reported(self):
        fail = {"by": "Kenya", "decision": "struck down", "umpire": "u"}
        inns = [innings("Kenya", n_overs=50, specials={(3, 0): [ball(review=fail)]}), innings("Canada", n_overs=50)]
        ms = [match(intl("2014-02-0%d" % d, ("Kenya", "Canada")), inns) for d in (1, 2)]
        s = _annotate([scan_match(m, str(i)) for i, m in enumerate(ms)])
        row = check_review_limits(s)["by_competition"][0]
        self.assertEqual((row["n_failed_without_drs_in_rules"], row["status"]), (2, "conflict"))


if __name__ == "__main__":
    unittest.main()
