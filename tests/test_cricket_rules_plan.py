"""Plan section 4.2 / 5 contract: field names, derived tables, series keys and per-match DRS."""
from __future__ import annotations

import unittest

import pandas as pd

from beating.cricket.competitions import (CLUB, competition_for, competition_meta, competitions_for_matches,
                                          drs_available_for_matches, series_key)
from beating.cricket.rules import (LEGACY_ALIASES, PLAN_FIELDS, _annotate, check_drs, check_reduced_powerplays,
                                   follow_on_threshold, is_knockout, load_config, reduced_powerplay, reduced_quota,
                                   rules_for, scan_match)
from tests.test_cricket_rules import ball, info, innings, match

ODI = lambda d, teams=("England", "Australia"), **kw: rules_for("intl_odi_m", "ODI", "male", d, teams=list(teams),
                                                               event_id=kw.pop("event_id", "bilateral"), **kw)
T20I = lambda d, **kw: rules_for("intl_t20_m", "T20", "male", d, teams=["England", "Australia"],
                                 event_id="bilateral", **kw)


class PlanFieldTests(unittest.TestCase):
    def test_every_plan_field_and_alias(self):
        ids = list(CLUB) + [f"intl_{f}_{g}" for f in ("t20", "odi", "test") for g in "mw"]
        for cid in ids:
            meta = competition_meta(cid)
            for date in ("2006-01-01", "2016-06-01", "2026-06-01"):
                r = rules_for(cid, meta["fmt"], meta["gender"], date)
                self.assertFalse(set(PLAN_FIELDS) - set(r), cid)
                for old, new in LEGACY_ALIASES.items():
                    if old not in ("balls_in_use", "super_over", "super_over_this_match"):
                        self.assertEqual(r[old], r[new], (cid, old))
                self.assertIn(r["tie_break"], ("none", "bowl_out", "so_boundary_count", "so_repeat"))

    def test_tie_break_values(self):
        self.assertEqual([T20I(d)["tie_break"] for d in ("2007-01-01", "2012-01-01", "2020-01-01")],
                         ["bowl_out", "so_boundary_count", "so_repeat"])
        self.assertEqual(T20I("2012-01-01")["super_over_this_match"], "single")
        final = ODI("2019-07-14", ("England", "New Zealand"), event_id="icc_cwc", stage="Final")
        self.assertEqual((final["tie_break"], final["tie_break_rule"]), ("so_boundary_count", "knockout_only"))
        self.assertEqual(ODI("2019-06-14", event_id="icc_cwc", stage=None)["tie_break"], "none")
        self.assertEqual(ODI("2023-10-14", event_id="icc_cwc")["tie_break"], "so_repeat")

    def test_free_hit_probability(self):
        self.assertEqual([ODI(d)["p_free_hit_given_nb"] for d in ("2006-01-01", "2010-01-01", "2016-01-01")],
                         [0.0, 0.71, 1.0])
        cfg = load_config()["p_free_hit_given_nb"]
        w = rules_for("intl_t20_w", "T20", "female", "2012-01-01")
        self.assertEqual((w["free_hit"], w["p_free_hit_given_nb"]), ("front_foot", cfg["default"]))
        self.assertTrue(all(0 <= v <= 1 and competition_meta(k) for k, v in cfg["by_competition"].items()))

    def test_follow_on_by_days(self):
        r = rules_for("intl_test_m", "TEST", "male", "2021-01-01", teams=["England", "India"])
        self.assertEqual(r["follow_on_lead_by_days"], {"1": 75, "2": 100, "3": 150, "4": 150, "5": 200})
        self.assertEqual([follow_on_threshold(r, d) for d in (0, 1, 2, 3, 4, 5, 6)], [75, 75, 100, 150, 150, 200, 200])
        self.assertEqual(r["follow_on_lead"], 200)
        self.assertIsNone(T20I("2021-01-01")["follow_on_lead"])

    def test_ucall_zone_and_drs_allowed(self):
        self.assertEqual([ODI(d)["ucall_zone_era"] for d in ("2015-01-01", "2018-01-01", "2022-01-01")],
                         ["pre_2016", "2016_wider", "2021_higher"])
        z = ODI("2015-06-01", ("Zimbabwe", "Pakistan"))
        self.assertEqual((z["drs_available"], z["drs_scope"], z["drs_allowed"]), (False, "selected", True))
        self.assertTrue(ODI("2019-06-01", ("Zimbabwe", "England"), event_id="icc_cwc")["drs_available"])
        self.assertFalse(ODI("2012-06-01", ("Bangladesh", "Pakistan"))["drs_available"])
        self.assertTrue(ODI("2018-06-01", ("Bangladesh", "Pakistan"))["drs_available"])

    def test_reduced_tables(self):
        self.assertEqual([reduced_quota("fifth_min2", n) for n in (8, 17, 20)], [[2, 0, 12], [3, 2, 18], [4, 0, 24]])
        self.assertEqual([reduced_quota("hundred_balls", n, 5) for n in (13, 20)], [[3, 0, 15], [4, 0, 20]])
        t20 = [[1, 6, 2], [7, 20, 5]]
        self.assertEqual(reduced_powerplay("t20_overs", 8, 6, t20), {"mandatory": [[1, 12]],
                                                                     "field_restr": [[1, 12, 2], [13, 48, 5]]})
        self.assertEqual(reduced_powerplay("t20_balls", 5, 6, t20)["mandatory"], [[1, 9]])
        self.assertEqual(reduced_powerplay("t20_surge", 5, 6, [[1, 4, 2], [5, 20, 5]])["mandatory"], [[1, 12]])
        odi = reduced_powerplay("odi_p123_men", 40, 6, [[1, 10, 2], [11, 40, 4], [41, 50, 5]])
        self.assertEqual(odi["field_restr"], [[1, 48, 2], [49, 192, 4], [193, 240, 5]])
        r = T20I("2019-01-01")
        self.assertEqual((r["bowler_quota_reduced"]["17"], r["pp_windows_reduced"]["8"]["mandatory"]),
                         ([3, 2, 18], [[1, 12]]))
        self.assertEqual(sorted(map(int, r["bowler_quota_reduced"])), list(range(1, 21)))
        self.assertEqual(T20I("2026-01-01")["pp_windows_reduced"]["5"]["mandatory"], [[1, 9]])
        self.assertIsNone(rules_for("intl_test_m", "TEST", "male", "2021-01-01")["bowler_quota_reduced"])


class CompetitionFixTests(unittest.TestCase):
    def test_knockout_and_event_ids(self):
        self.assertEqual([is_knockout(s) for s in ("Race to the Final", "Final", "Qualifier 1", "Eliminator")],
                         [False, True, True, True])
        intl = lambda name: competition_for(info(name, "T20", team_type="international", teams=("A", "B"))).event_id
        self.assertEqual([intl("Asia Cup Rising Stars"), intl("Trans-Tasman Twenty20 Trophy")],
                         ["multi_nation", "multi_nation"])
        club = lambda name: competition_for(info(name)).competition_id
        self.assertEqual([club("T20"), club("T20 Blast"), club("Vitality Blast Men")],
                         ["other_t20_m", "blast", "blast"])


def frame(rows, cols=("competition_id", "event_id", "event_name", "season", "start_date", "team1", "team2")):
    return pd.DataFrame([dict(zip(cols, r)) for r in rows])


class SeriesKeyTests(unittest.TestCase):
    def test_bilateral_pairs_and_gap(self):
        b = ("intl_odi_m", "bilateral", "ICC Cricket World Cup Super League", "2021")
        df = frame([b + ("2021-01-01", "A", "B"), b + ("2021-01-05", "B", "A"), b + ("2021-04-01", "A", "B"),
                    b + ("2021-01-03", "A", "C")])
        k = series_key(df).tolist()
        self.assertEqual(k[0], k[1])
        self.assertEqual(len(set(k)), 3)
        self.assertTrue(k[0].endswith("|A v B|2021-01-01") and k[2].endswith("|A v B|2021-04-01"))

    def test_multi_nation_kept_and_split_names(self):
        tri = ("intl_odi_m", "multi_nation", "Tri-Series", "2014")
        df = frame([tri + ("2014-01-01", "A", "B"), tri + ("2014-01-03", "B", "C"), tri + ("2014-01-05", "A", "C")])
        self.assertEqual(set(series_key(df)), {"intl_odi_m|tri-series|2014"})
        late = frame([tri + ("2014-01-01", "A", "B"), tri + ("2014-05-01", "B", "C")])
        self.assertEqual(len(set(series_key(late))), 2)
        nw = lambda y: ("intl_odi_m", "multi_nation", "NatWest Series", y)
        df = frame([nw("2011") + ("2011-06-28", "England", "Sri Lanka"),
                    nw("2011") + ("2011-09-03", "England", "India"),
                    nw("2004") + ("2004-07-01", "England", "New Zealand"),
                    nw("2004") + ("2004-07-03", "New Zealand", "West Indies")])
        k = series_key(df).tolist()
        self.assertNotEqual(k[0], k[1])
        self.assertEqual(k[2], k[3])
        wc = ("intl_odi_w", "icc_womens_championship", "ICC Women's Championship", "2023")
        k = series_key(frame([wc + ("2023-06-27", "A", "B"), wc + ("2023-07-01", "C", "D")])).tolist()
        self.assertNotEqual(k[0], k[1])

    def test_derived_from_ingest_columns(self):
        tour = "England tour of Australia"
        df = pd.DataFrame(dict(event_name=[tour, tour, "Indian Premier League"],
                               gender="male", team_type=["international", "international", "club"],
                               match_type=["ODI", "ODI", "T20"], start_date=["2022-11-17", "2022-11-22", "2023-04-01"],
                               team1_raw=["Australia", "England", "Gujarat Titans"],
                               team2_raw=["England", "Australia", "Chennai Super Kings"],
                               season=["2022/23", "2022/23", "2023"], balls_per_over=6))
        comp = competitions_for_matches(df)
        self.assertEqual(comp.competition_id.tolist(), ["intl_odi_m", "intl_odi_m", "ipl"])
        k = series_key(df).tolist()
        self.assertEqual((k[0] == k[1], k[2]), (True, "ipl|indian premier league|2023"))


class DrsAvailableTests(unittest.TestCase):
    def test_plan_formula(self):
        df = pd.DataFrame(dict(match_id=[1, 2, 3, 4, 5, 6, 7], series_key=["s1", "s1", "s2", "s1", "s1", "s3", "s3"],
                               drs_allowed=[True, True, True, False, True, True, True],
                               reviews_missing=[False, False, False, False, True, True, False]))
        out = drs_available_for_matches(df, {1: 3, 6: 1})
        self.assertEqual(out.drs_available.tolist(), [True, True, False, False, None, None, False])
        self.assertEqual(out.drs_source.tolist(),
                         ["match", "series", "series", "rules", "unknown", "unknown", "series"])

    def test_rules_computed_for_ingest_rows(self):
        df = pd.DataFrame(dict(match_id=[10, 11, 12], file_stem=["10", "11", "12"],
                               event_name=["Indian Premier League", "Vitality Blast", "Vitality Blast"],
                               event_stage=[None, None, "Final"], gender="male", team_type="club", match_type="T20",
                               start_date=["2023-04-01", "2023-06-01", "2023-07-15"], team1_raw=["A", "C", "E"],
                               team2_raw=["B", "D", "F"], season="2023", balls_per_over=6, reviews_missing=False))
        out = drs_available_for_matches(df, pd.Series({10: 2}))
        self.assertEqual(out.drs_available.tolist(), [True, False, False])
        self.assertEqual(out.drs_source.tolist(), ["match", "rules", "series"])


class CheckTests(unittest.TestCase):
    def summaries(self, matches):
        return _annotate([scan_match(m, str(i)) for i, m in enumerate(matches)])

    def odis(self, teams, n=5, date="2022-06-17"):
        rev = {"by": teams[0], "decision": "struck down", "umpire": "u"}
        return [match(info(f"{teams[1]} tour of {teams[0]}", "ODI", team_type="international", date=date, teams=teams,
                           overs=50), [innings(teams[0], n_overs=50, specials={(3, 0): [ball(review=rev)]}),
                                       innings(teams[1], n_overs=50)]) for _ in range(n)]

    def test_check_drs_selected_vs_none(self):
        sel = check_drs(self.summaries(self.odis(("England", "Netherlands"))))
        self.assertEqual((sel[0]["status"], sel[0]["reviews_where_scope_none"]), ("partial_selected", 0))
        none = check_drs(self.summaries(self.odis(("Netherlands", "Scotland"))))
        self.assertEqual(none[0]["status"], "conflict_rules_off_data_on")

    def test_reduced_powerplay_timing(self):
        def m(pp_to):
            return match(info("Indian Premier League", date="2019-04-01"),
                         [innings("A"), innings("B", n_overs=10, target={"runs": 90, "overs": 10},
                                                powerplays=[{"from": 0.1, "to": pp_to, "type": "mandatory"}])])
        rows = check_reduced_powerplays(self.summaries([m(2.6), m(3.6), m(5.6)]))
        ipl = next(r for r in rows if r["competition_id"] == "ipl")
        self.assertEqual((ipl["matching"], ipl["cut_during_powerplay"], ipl["cut_after_powerplay"], ipl["status"]),
                         (1, 1, 1, "ok"))
        self.assertTrue(any(r["competition_id"] == "_all" and r["rule"] == "t20_overs" for r in rows))


if __name__ == "__main__":
    unittest.main()
