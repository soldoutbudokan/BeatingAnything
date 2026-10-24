from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from beating.cricket.competitions import CLUB, competition_for, competition_meta, scan_events, season_key
from beating.cricket.rules import (FIELDS, check_drs, check_follow_on, check_free_hit, check_powerplays,
                                   check_replacements, check_review_limits, check_super_overs, is_knockout,
                                   load_config, rules_for, rules_for_match, scan_match, validate, _annotate)


def info(event=None, match_type="T20", gender="male", team_type="club", date="2023-04-01", teams=("A", "B"),
         stage=None, season=None, overs=20, bpo=6):
    ev = {} if event is None else {"name": event}
    if stage:
        ev["stage"] = stage
    return {"event": ev, "match_type": match_type, "gender": gender, "team_type": team_type, "dates": [date],
            "teams": list(teams), "season": season or date[:4], "overs": overs, "balls_per_over": bpo,
            "outcome": {"winner": teams[0], "by": {"runs": 1}}}


def ball(runs=0, extras=None, wicket=None, review=None, bowler="b1", repl=None):
    d = {"batter": "x", "bowler": bowler, "non_striker": "y", "runs": {"batter": runs, "extras": 0, "total": runs}}
    if extras:
        d["extras"] = extras
        d["runs"]["extras"] = d["runs"]["total"] = sum(extras.values()) + runs
    if wicket:
        d["wickets"] = [{"kind": wicket, "player_out": "x"}]
    if review:
        d["review"] = review
    if repl:
        d["replacements"] = {"match": [repl]}
    return d


def innings(team, n_overs=20, bpo=6, specials=None, **kw):
    """n_overs plain overs, alternating bowlers; ``specials`` maps (over, i) to an extra delivery list."""
    overs = []
    for o in range(n_overs):
        balls = [ball(1, bowler=f"b{o % 2}") for _ in range(bpo)]
        for (so, si), extra in (specials or {}).items():
            if so == o:
                balls[si:si] = extra
        overs.append({"over": o, "deliveries": balls})
    return {"team": team, "overs": overs, **kw}


def match(inf, inns):
    return {"meta": {}, "info": inf, "innings": inns}


class CompetitionTests(unittest.TestCase):
    def test_club_aliases_absorb_renames(self):
        cases = [
            ("Indian Premier League", "male", "T20", "ipl"), ("Big Bash League", "male", "T20", "bbl"),
            ("Women's Big Bash League", "female", "T20", "wbbl"), ("Vitality Blast", "male", "T20", "blast"),
            ("NatWest T20 Blast", "male", "T20", "blast"), ("Friends Provident t20", "male", "T20", "blast"),
            ("Vitality Blast Men", "male", "T20", "blast"), ("Vitality Blast Women", "female", "T20", "blast_w"),
            ("The Hundred Men's Competition", "male", "T20", "hundred_m"),
            ("The Hundred Women’s Competition", "female", "T20", "hundred_w"),
            ("LV= County Championship", "male", "MDM", "county_championship"),
            ("Specsavers County Championship", "male", "MDM", "county_championship"),
            ("Bob Willis Trophy", "male", "MDM", "county_championship"),
            ("Marsh Sheffield Shield", "male", "MDM", "sheffield_shield"),
            ("Sheffield Shield", "male", "MDM", "sheffield_shield"), ("Ranji Trophy", "male", "MDM", "ranji_trophy"),
            ("Royal London One-Day Cup", "male", "ODM", "eng_one_day_cup"),
            ("One-Day Cup", "male", "ODM", "eng_one_day_cup"), ("The Marsh Cup", "male", "ODM", "aus_one_day_cup"),
            ("One-Day Cup (Australia)", "male", "ODM", "aus_one_day_cup"), ("HRV Cup", "male", "T20", "super_smash"),
            ("Ram Slam T20 Challenge", "male", "T20", "csa_t20"), ("Women's Premier League", "female", "T20", "wpl"),
            ("Rachael Heyhoe Flint Trophy", "female", "ODM", "eng_women_one_day"),
        ]
        for name, gender, mt, want in cases:
            with self.subTest(name=name):
                c = competition_for(info(name, mt, gender))
                self.assertEqual(c.competition_id, want)
                self.assertFalse(c.generic)
                self.assertEqual(c.tier, CLUB[want][1])

    def test_hundred_family_and_tiers(self):
        c = competition_for(info("The Hundred Men's Competition", bpo=5))
        self.assertEqual((c.fmt, c.tier), ("HUNDRED", "franchise_major"))
        self.assertEqual(competition_for(info("Vitality Blast")).tier, "domestic_major")

    def test_internationals(self):
        intl = dict(team_type="international")
        c = competition_for(info("England tour of India", "Test", teams=("India", "England"), **intl))
        self.assertEqual((c.competition_id, c.event_id, c.tier, c.assoc_match),
                         ("intl_test_m", "bilateral", "intl_full", False))
        self.assertEqual(competition_for(info("ICC World Cup", "ODI", team_type="international")).event_id, "icc_cwc")
        self.assertEqual(competition_for(info("ICC World Test Championship", "Test", team_type="international",
                                              teams=("India", "New Zealand"))).event_id, "icc_wtc_final")
        self.assertEqual(competition_for(info("ICC Men's T20 World Cup Europe Region Qualifier", "T20",
                                              team_type="international")).event_id, "icc_qualifier")
        self.assertEqual(competition_for(info("Australia in India ODI Series", "ODI", **intl)).event_id, "bilateral")
        ire_2016 = competition_for(info("Ireland v England", "ODI", team_type="international", date="2016-05-08",
                                        teams=("Ireland", "England")))
        ire_2018 = competition_for(info("Ireland v England", "ODI", team_type="international", date="2018-05-08",
                                        teams=("Ireland", "England")))
        self.assertEqual((ire_2016.assoc_match, ire_2016.tier), (True, "intl_assoc"))
        self.assertEqual((ire_2018.assoc_match, ire_2018.tier), (False, "intl_full"))
        it20 = competition_for(info("ICC World Twenty20 Qualifier", "IT20", team_type="international",
                                    teams=("Netherlands", "Scotland")))
        self.assertEqual((it20.competition_id, it20.official, it20.tier), ("intl_t20_m", False, "intl_assoc"))
        w = competition_for(info("ICC Women's T20 World Cup", "T20", "female", "international",
                                 teams=("India", "England")))
        self.assertEqual((w.competition_id, w.event_id), ("intl_t20_w", "icc_t20wc"))
        unnamed = competition_for(info(None, "ODI", team_type="international", teams=("India", "England")))
        self.assertEqual((unnamed.competition_id, unnamed.event_id, unnamed.generic),
                         ("intl_odi_m", "intl_unnamed", True))

    def test_generic_fallback_and_season_key(self):
        c = competition_for(info("Some Village League"))
        self.assertEqual((c.competition_id, c.generic, c.tier), ("other_t20_m", True, "domestic_minor"))
        self.assertEqual(competition_for(info(None, "ODM", "female")).competition_id, "other_odi_w")
        self.assertEqual(season_key(info("Indian Premier League", season="2023")), "ipl:2023")
        self.assertEqual(competition_meta("other_t20_m")["team_type"], "club")
        self.assertEqual(competition_meta("intl_test_w")["gender"], "female")

    def test_scan_events_streams_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.zip"
            with zipfile.ZipFile(path, "w") as z:
                for i, ev in enumerate(["Indian Premier League", "Indian Premier League", "Unknown Cup"]):
                    z.writestr(f"{i}.json", json.dumps(match(info(ev), [])))
                z.writestr("README.txt", "x")
            df = scan_events(path)
        self.assertEqual(dict(zip(df.competition_id, df.n_matches)), {"ipl": 2, "other_t20_m": 1})
        self.assertEqual(int(df.generic.sum()), 1)


class RulesTests(unittest.TestCase):
    def test_every_field_for_every_competition(self):
        ids = list(CLUB) + [f"intl_{f}_{g}" for f in ("t20", "odi", "test") for g in "mw"] + ["other_test_w"]
        for cid in ids:
            meta = competition_meta(cid)
            for date in ("2004-01-01", "2012-06-01", "2018-06-01", "2026-06-01"):
                r = rules_for(cid, meta["fmt"], meta["gender"], date)
                self.assertTrue(set(FIELDS) <= set(r), cid)
                self.assertEqual(set(r["_layers"]), set(FIELDS))

    def test_config_layers_valid(self):
        cfg = load_config()
        ids = [layer["id"] for layer in cfg["layers"]]
        self.assertEqual(len(ids), len(set(ids)))
        for layer in cfg["layers"]:
            for k in ("from", "until"):
                if layer.get(k):
                    self.assertRegex(layer[k], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn(layer["source"], ("memory", "data", "memory+data"))

    def test_test_review_eras(self):
        t = lambda d: rules_for("intl_test_m", "TEST", "male", d, teams=["England", "Australia"])
        self.assertEqual((t("2012-01-01")["reviews_per_innings"], t("2012-01-01")["review_topup_after_80"]), (2, False))
        self.assertTrue(t("2015-01-01")["review_topup_after_80"])
        self.assertFalse(t("2015-01-01")["umpires_call_retains_review"])
        r18 = t("2018-01-01")
        self.assertEqual((r18["reviews_per_innings"], r18["review_topup_after_80"], r18["umpires_call_retains_review"]),
                         (2, False, True))
        self.assertEqual(t("2021-01-01")["reviews_per_innings"], 3)
        self.assertEqual((t("2021-01-01")["test_overs_per_day"], t("2021-01-01")["follow_on_lead"],
                          t("2021-01-01")["new_ball_after_overs"]), (90, 200, 80))
        self.assertFalse(t("2007-01-01")["drs_available"])

    def test_india_drs_and_icc_events(self):
        t = lambda d: rules_for("intl_test_m", "TEST", "male", d, teams=["India", "Australia"])["drs_available"]
        self.assertFalse(t("2013-03-01"))
        self.assertTrue(t("2017-03-01"))
        self.assertTrue(rules_for("intl_odi_m", "ODI", "male", "2015-03-01", teams=["India", "Pakistan"],
                                  event_id="icc_cwc")["drs_available"])

    def test_odi_eras(self):
        o = lambda d: rules_for("intl_odi_m", "ODI", "male", d, teams=["England", "Australia"], event_id="bilateral")
        self.assertEqual(o("2004-01-01")["powerplay_overs"]["mandatory"], [[1, 15]])
        r06 = o("2006-01-01")
        self.assertEqual((r06["free_hit"], r06["powerplay_overs"]["fielding"]["n"]), ("none", 2))
        self.assertEqual(o("2010-01-01")["free_hit"], "front_foot")
        self.assertEqual(o("2013-01-01")["powerplay_overs"]["batting"]["window"], [16, 40])
        self.assertIsNone(o("2013-01-01")["powerplay_overs"]["fielding"])
        r = o("2016-01-01")
        self.assertEqual((r["free_hit"], r["powerplay_overs"]["mandatory"]),
                         ("all_noballs", [[1, 10], [11, 40], [41, 50]]))
        self.assertEqual(o("2012-01-01")["balls_in_use"], "two_new_balls")
        self.assertEqual(o("2026-01-01")["balls_in_use"], "two_balls_until_34")
        self.assertEqual([o(d)["reviews_per_innings"] for d in ("2011-02-01", "2012-01-01", "2021-01-01")], [2, 1, 2])
        self.assertEqual((o("2015-01-01")["min_overs_for_result"], o("2015-01-01")["bowler_quota_overs"]), (20, 10))
        self.assertEqual(o("2005-09-01")["tactical_sub"], "supersub")

    def test_t20i(self):
        t = lambda d: rules_for("intl_t20_m", "T20", "male", d, teams=["England", "Australia"], event_id="bilateral")
        self.assertEqual((t("2016-01-01")["drs_available"], t("2016-01-01")["reviews_per_innings"]), (False, None))
        self.assertEqual((t("2018-06-01")["drs_available"], t("2018-06-01")["reviews_per_innings"]), (True, 1))
        self.assertEqual(t("2021-06-01")["reviews_per_innings"], 2)
        self.assertEqual([t(d)["free_hit"] for d in ("2010-01-01", "2016-01-01")], ["front_foot", "all_noballs"])
        self.assertEqual([t(d)["super_over"] for d in ("2007-01-01", "2012-01-01", "2020-01-01")],
                         ["bowl_out", "single", "repeat"])
        r23 = t("2023-01-01")
        self.assertEqual((r23["slow_over_rate_fielding_penalty"], r23["powerplay_overs"]["mandatory"],
                          r23["min_overs_for_result"]), (True, [[1, 6]], 5))

    def test_hundred(self):
        r = rules_for("hundred_m", "HUNDRED", "male", "2024-08-01")
        self.assertEqual((r["balls_per_over"], r["balls_per_innings"], r["bowler_quota_balls"],
                          r["max_consecutive_balls_per_end"]), (5, 100, 20, 10))
        self.assertEqual((r["powerplay_overs"]["mandatory"], r["min_balls_for_result"]), ([[1, 5]], 25))
        self.assertEqual((r["noball_extra_runs"], r["free_hit"], r["reviews_per_innings"]), (2, "front_foot", 1))
        r26 = rules_for("hundred_w", "HUNDRED", "female", "2026-08-01")
        self.assertEqual((r26["noball_extra_runs"], r26["free_hit"]), (1, "all_noballs"))

    def test_ipl(self):
        i = lambda d: rules_for("ipl", "T20", "male", d)
        self.assertFalse(i("2017-04-01")["drs_available"])
        self.assertEqual(i("2018-04-01")["reviews_per_innings"], 1)
        self.assertEqual((i("2022-04-01")["reviews_per_innings"], i("2022-04-01")["impact_player"]), (2, False))
        self.assertTrue(i("2023-04-01")["impact_player"])

    def test_scheduled_days_and_women(self):
        r = rules_for("intl_test_m", "TEST", "male", "2019-07-24", teams=["England", "Ireland"], match_id="1152839")
        self.assertEqual((r["test_days"], r["test_overs_per_day"], r["follow_on_lead"]), (4, 98, 150))
        four = rules_for("intl_test_m", "TEST", "male", "2019-07-24", scheduled_days=4)
        self.assertEqual(four["follow_on_lead"], 150)
        w = rules_for("intl_test_w", "TEST", "female", "2022-01-27")
        self.assertEqual((w["test_days"], w["test_overs_per_day"], w["follow_on_lead"]), (4, 100, 150))
        cc = rules_for("county_championship", "TEST", "male", "2023-05-01")
        self.assertEqual((cc["test_days"], cc["test_overs_per_day"], cc["follow_on_lead"], cc["noball_extra_runs"]),
                         (4, 96, 150, 2))
        self.assertEqual(rules_for("sheffield_shield", "TEST", "male", "2023-03-01", knockout=True)["test_days"], 5)

    def test_knockouts_and_associates(self):
        g = rules_for("blast", "T20", "male", "2023-06-01")
        k = rules_for("blast", "T20", "male", "2023-07-15", knockout=True)
        self.assertEqual((g["drs_available"], g["super_over_this_match"]), (False, "none"))
        self.assertEqual((k["drs_available"], k["reviews_per_innings"], k["super_over_this_match"]),
                         (True, 1, "repeat"))
        self.assertTrue(is_knockout("Semi Final") and is_knockout("Qualifier 2") and not is_knockout("Group A"))
        b22 = lambda stage: rules_for("blast", "T20", "male", "2022-07-16", stage=stage)["drs_available"]
        self.assertEqual([b22("Quarter Final"), b22("Semi Final"), b22("Final")], [False, True, True])
        self.assertFalse(rules_for("blast", "T20", "male", "2024-09-14", stage="Final")["drs_available"])
        a = dict(teams=["Nepal", "Oman"], assoc_match=True)
        t = lambda d, ev: rules_for("intl_t20_m", "T20", "male", d, event_id=ev, **a)["drs_available"]
        self.assertFalse(t("2022-06-01", "multi_nation"))
        self.assertTrue(t("2024-06-01", "icc_t20wc"))

    def test_women_drs(self):
        def wo(d, teams, ev="bilateral", f="ODI", c="intl_odi_w"):
            return rules_for(c, f, "female", d, teams=teams, event_id=ev)
        self.assertTrue(wo("2023-07-01", ["England", "Australia"])["drs_available"])
        r = wo("2023-07-01", ["England", "Ireland"])
        self.assertEqual((r["drs_available"], r["drs_scope"], r["reviews_per_innings"]), (False, "selected", 2))
        self.assertTrue(wo("2020-02-21", ["India", "Australia"], "icc_t20wc", "T20", "intl_t20_w")["drs_available"])
        self.assertEqual(wo("2016-01-01", ["England", "Australia"])["drs_scope"], "none")

    def test_rules_for_match(self):
        r = rules_for_match(info("Indian Premier League", date="2023-05-28", stage="Final"))
        self.assertTrue(r["impact_player"] and r["drs_available"])
        r = rules_for_match(info("Vitality Blast", date="2023-07-15", stage="Final"))
        self.assertTrue(r["drs_available"])


class ValidationTests(unittest.TestCase):
    def summaries(self, matches):
        return _annotate([scan_match(m, str(i)) for i, m in enumerate(matches)])

    def test_review_limit_violation_and_drs_share(self):
        fail = {"by": "A", "decision": "struck down", "umpire": "u"}
        inn = innings("A", specials={(3, 0): [ball(review=fail)], (9, 0): [ball(review=fail)]})
        s = self.summaries([match(info("Indian Premier League", date="2019-04-01"), [inn, innings("B")])])
        rows = check_review_limits(s)["by_competition"]
        self.assertEqual((rows[0]["key"], rows[0]["max_failed_non_ucall"], rows[0]["n_violations"]), ("ipl", 2, 1))
        drs = check_drs(s)
        self.assertEqual((drs[0]["n_rules_on"], drs[0]["share_obs_when_on"]), (1, 1.0))

    def test_umpires_call_does_not_count_after_2017(self):
        uc = {"by": "A", "decision": "struck down", "umpire": "u", "umpires_call": True}
        fail = {"by": "A", "decision": "struck down", "umpire": "u"}
        inn = innings("A", specials={(3, 0): [ball(review=uc)], (9, 0): [ball(review=fail)]})
        s = self.summaries([match(info("Indian Premier League", date="2019-04-01"), [inn, innings("B")])])
        self.assertEqual(check_review_limits(s)["by_competition"][0]["n_violations"], 0)

    def test_free_hit_and_powerplays(self):
        nb = ball(0, extras={"noballs": 1})
        inn = innings("A", specials={(2, 0): [nb, ball(0, wicket="bowled")]},
                      powerplays=[{"from": 0.1, "to": 5.6, "type": "mandatory"}])
        s = self.summaries([match(info("Indian Premier League", date="2020-10-01"), [inn, innings("B")])])
        fh = check_free_hit(s)
        self.assertEqual((fh[0]["rule"], fh[0]["free_hit_balls"], fh[0]["protected_dismissals"]), ("all_noballs", 1, 1))
        pp = check_powerplays(s)
        self.assertEqual((pp[0]["full_innings"], pp[0]["share_matching"]), (1, 1.0))

    def test_follow_on_and_replacements_and_super_over(self):
        big = innings("A", n_overs=60)
        small = innings("B", n_overs=20)
        third = innings("B", n_overs=30)
        t = match(info("England tour of Australia", "Test", team_type="international", date="2021-12-08",
                       teams=("Australia", "England")), [big, small, third])
        sub = {"in": "p", "out": "q", "reason": "impact_player", "team": "A"}
        ipl = match(info("Indian Premier League", date="2023-04-01"),
                    [innings("A", specials={(0, 0): [ball(repl=sub)]}), innings("B")])
        tied = dict(info("Indian Premier League", date="2023-04-02"), outcome={"result": "tie", "eliminator": "A"})
        tie = match(tied,
                    [innings("A"), innings("B"), dict(innings("B", n_overs=1), super_over=True),
                     dict(innings("A", n_overs=1), super_over=True)])
        s = self.summaries([t, ipl, tie])
        fo = check_follow_on(s)
        self.assertEqual((fo[0]["follow_ons"], fo[0]["min_lead"], fo[0]["status"]), (1, 240, "ok"))
        rep = check_replacements(s)
        self.assertEqual((rep[0]["impact_player_matches"], rep[0]["status"]), (1, "ok"))
        so = check_super_overs(s)
        self.assertEqual((so[0]["super_over_ties"], so[0]["status"]), (1, "ok"))

    def test_anomalies_mark_rows_explained(self):
        from beating.cricket.rules import explain_anomalies
        sections = {"follow_on": [{"competition_id": "x", "status": "conflict"}, {"competition_id": "y", "status": "ok"}]}
        explain_anomalies(sections, [{"section": "follow_on", "where": {"competition_id": "x"}, "explanation": "why"}])
        self.assertEqual([r["status"] for r in sections["follow_on"]], ["explained", "ok"])
        self.assertEqual(sections["follow_on"][0]["explanation"], "why")

    def test_validate_end_to_end(self):
        m = match(info("Indian Premier League", date="2023-04-01"), [innings("A"), innings("B")])
        report = validate([scan_match(m, "1")])
        self.assertEqual(report["competitions"]["matches"], 1)
        self.assertIn("status_counts", report)
        json.dumps(report, default=str)


if __name__ == "__main__":
    unittest.main()
