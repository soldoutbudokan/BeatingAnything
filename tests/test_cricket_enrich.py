from __future__ import annotations

import json
import unittest

import numpy as np
import pandas as pd

from beating.cricket import enrich as E, resource as RT, rules as R


def _rules(cid, fmt, gender, date, **kw):
    return R.rules_for(cid, fmt, gender, date, **kw)


class FreeHitTest(unittest.TestCase):
    def test_probability_and_flag(self):
        chain = np.array([0, 1, 2, 1, 1, 0])
        p = np.array([1.0, 1.0, 0.7, 0.7, 0.0, 0.7])
        fp, fh = E.free_hit(chain, p)
        np.testing.assert_allclose(fp, [0, 1, 0.91, 0.7, 0, 0], atol=1e-6)
        self.assertEqual(fh.tolist(), [0, 1, -1, -1, 0, 0])


class ReviewsTest(unittest.TestCase):
    def test_exclusive_cumsum_restarts_per_group(self):
        x = np.array([1, 0, 1, 1, 0, 1])
        starts = np.array([0, 0, 0, 3, 3, 3])
        self.assertEqual(E.exclusive_cumsum(x, starts).tolist(), [0, 1, 1, 0, 1, 1])

    def test_topup_after_80_and_umpires_call(self):
        over = np.array([10, 50, 79, 80, 81, 90])
        fails = np.array([0, 1, 2, 2, 2, 3])            # failed non-umpire's-call reviews before the ball
        ucall = np.array([0, 0, 0, 0, 1, 1])            # failed umpire's-call reviews before the ball
        inn = np.zeros(6, dtype=int)
        n = np.full(6, 2)
        keep = E.reviews_left(n, fails, ucall, np.ones(6, bool), np.ones(6, bool), over, inn)
        self.assertEqual(keep.tolist(), [2, 1, 0, 2, 2, 1])
        lose = E.reviews_left(n, fails, ucall, np.zeros(6, bool), np.ones(6, bool), over, inn)
        self.assertEqual(lose.tolist(), [2, 1, 0, 2, 1, 0])
        plain = E.reviews_left(n, fails, ucall, np.ones(6, bool), np.zeros(6, bool), over, inn)
        self.assertEqual(plain.tolist(), [2, 1, 0, 0, 0, -1])   # negative left: an anomaly the report counts
        none = E.reviews_left(np.full(6, -1), fails, ucall, np.ones(6, bool), np.zeros(6, bool), over, inn)
        self.assertTrue((none == -E.BIG).all())


class PowerplayTest(unittest.TestCase):
    def test_recorded_levels(self):
        full = [_rules("intl_odi_m", "ODI", "male", "2016-02-01", event_id="bilateral", teams=["India", "Australia"]),
                _rules("ipl", "T20", "male", "2023-04-10", event_id="ipl"),
                _rules("intl_odi_m", "ODI", "male", "2013-02-01", event_id="bilateral", teams=["India", "Australia"])]
        a = E.match_pp_arrays(full)
        PP = E.PP
        lvl = np.array([PP["pp1"], PP["pp2"], PP["pp3"], PP["pp1"], PP["none"], PP["pp2"], PP["batting"], PP["none"],
                        PP["none"]])
        over1 = np.array([3, 20, 45, 2, 12, 5, 30, 25, 5])
        mi = np.array([0, 0, 0, 1, 1, 1, 2, 2, 2])
        fr = E.recorded_field_restr(lvl, over1, a, mi)
        # ODI 2016: 2/4/5; IPL: pp1 2, outside 5, a split second window keeps 2; ODI 2013: batting pp 3, else 4
        self.assertEqual(fr.tolist(), [2, 4, 5, 2, 5, 2, 3, 4, 4])

    def test_rules_reduced_innings(self):
        r = _rules("ipl", "T20", "male", "2023-04-10", event_id="ipl")
        ball1 = np.arange(1, 61)
        over1 = (ball1 - 1) // 6 + 1
        lvl, fr = E.rules_powerplay(r, over1, ball1, np.full(60, 60))   # a 10-over innings
        n_pp = int((lvl == E.PP["pp1"]).sum())
        self.assertEqual(n_pp, 18)                                        # 3 overs in a 10-over T20
        self.assertTrue((fr[:n_pp] == 2).all() and (fr[n_pp:] == 5).all())
        lvl, fr = E.rules_powerplay(r, over1, ball1, np.full(60, 120))  # full length: overs 1-6
        self.assertEqual(int((lvl == E.PP["pp1"]).sum()), 36)


class TestClockTest(unittest.TestCase):
    def test_uniform_without_rain_matches_ingest_rule(self):
        opd, D, overs, phi = 90.0, 4, 300.0, 0.5
        cap = E.day_capacity(opd, D, overs, phi)
        r = min(opd, overs / (D - 1 + phi))
        np.testing.assert_allclose(cap, [r, r, r, r * phi])
        mo = np.array([0.0, r - 0.1, r + 0.1, 3 * r + 5])
        d, o = E.clock_position(mo, cap)
        self.assertEqual(d.tolist(), [1, 1, 2, 4])
        np.testing.assert_allclose(o, [0, r - 0.1, 0.1, 5], atol=1e-4)

    def test_rain_day_takes_the_loss(self):
        cap = E.day_capacity(90.0, 4, 250.0, 0.5, np.array([0.0, 1.0, 0.0, np.nan]))
        self.assertAlmostEqual(cap.sum(), 250.0, places=6)
        self.assertLess(cap[1], cap[0])
        self.assertAlmostEqual(cap[0], cap[2])
        washed = E.day_capacity(90.0, 3, 100.0, 1.0, np.array([0.0, 1.0, 0.0]), eps=0.0)
        np.testing.assert_allclose(washed, [50.0, 0.0, 50.0])         # loss capped at a full day

    def test_expected_overs_left(self):
        v = E.expected_overs_left(np.array([5, 5, 5, 5]), 90.0, 10.0, np.array([1, 5, 6, 3]), np.array([0, 45, 0, 100]))
        np.testing.assert_allclose(v, [400.0, 40.0, 0.0, 160.0], atol=1e-4)

    def test_expected_loss_is_as_of(self):
        m = pd.DataFrame({"match_id": [1, 2, 3, 4], "start_date": ["2020-01-01", "2020-02-01", "2020-02-01", "2021-01-01"],
                          "match_type": "Test", "region": "sena_eng", "venue_id": "lords", "opd": 90.0,
                          "overs": [300.0, 450.0, 200.0, 360.0], "n_dates": [5, 5, 3, 5],
                          "result": ["draw", "draw", "win", "draw"]})
        a = E.expected_loss(m)
        self.assertAlmostEqual(a.exp_loss_per_day[0], E.LOSS_PRIOR, places=5)
        self.assertAlmostEqual(a.exp_loss_per_day[1], a.exp_loss_per_day[2], places=6)   # same day: not each other
        np.testing.assert_allclose(a.loss_per_day_obs, [30.0, 0.0, 10.0, 18.0], atol=1e-5)
        changed = E.expected_loss(m.assign(overs=[300.0, 450.0, 200.0, 10.0]))
        np.testing.assert_allclose(changed.exp_loss_per_day[:4], a.exp_loss_per_day[:4])  # a later result is unseen
        self.assertEqual(a.exp_loss_n.tolist(), [0, 1, 1, 3])


def _fixture():
    matches = pd.DataFrame({
        "match_id": [101, 202], "file_stem": ["101", "202"], "start_date": ["2023-04-10", "2015-07-16"],
        "dates_played": [json.dumps(["2023-04-10"]), json.dumps(["2015-07-16", "2015-07-17", "2015-07-18"])],
        "season": ["2023", "2015"], "match_type": ["T20", "Test"], "fam": ["T20", "TEST"],
        "gender": ["male", "male"], "team_type": ["club", "international"], "event_name": ["Indian Premier League", None],
        "event_stage": [None, None], "team1_raw": ["Mumbai Indians", "England"], "team2_raw": ["Chennai Super Kings", "Australia"],
        "balls_per_over": np.array([6, 6], dtype=np.int8), "reviews_missing": [False, False], "venue_id": ["wankhede_stadium", "lords"],
        "result": ["win", "win"], "n_dates": np.array([1, 3], dtype=np.int8)})
    innings = pd.DataFrame({"match_id": [101, 101, 202, 202], "innings": [1, 2, 1, 2], "team_idx": [2, 1, 1, 2],
                            "legal_balls": [6, 0, 1400, 0]})
    mt = pd.DataFrame({"match_id": [101, 202], "team1_id": ["mumbai_indians_m", "england_m"],
                       "team2_id": ["chennai_super_kings_m", "australia_m"], "team1": ["Mumbai Indians", "England"],
                       "team2": ["Chennai Super Kings", "Australia"], "home_status1": ["home", "home"],
                       "home_status2": ["away", "away"], "home_source1": "x", "home_source2": "x",
                       "start_slot": ["night", "day"], "start_slot_source": "x", "start_slot_confidence": "x"})
    venues = pd.DataFrame({"venue_id": ["wankhede_stadium", "lords"], "region": ["subcontinent", "sena_eng"],
                           "cricket_country": ["India", "England"], "lat": [18.9, 51.5], "lon": [72.8, -0.17],
                           "elevation_m": [11.0, 40.0], "ball_brand_default": ["sg", "dukes"]})
    players = pd.DataFrame({"person_id": np.arange(4, dtype=np.int32), "bat_hand": ["R", "L", "R", "U"],
                            "bowl_type": ["none", "off_spin", "pace_fast", "leg_spin"],
                            "bowl_class": ["none", "spin", "pace", "spin"],
                            "country": ["India", "Australia", "England", None]})
    wx = pd.DataFrame({"match_id": [101, 202, 202, 202], "date": pd.to_datetime(["2023-04-10", "2015-07-16", "2015-07-17", "2015-07-18"]),
                       "source": "isd_lite", "temp_c_mean": [30.0, 18.0, 19.0, 20.0], "rh_mean": 60.0,
                       "cloud_oktas_mean": 4.0, "dew_depression_evening": 5.0, "precip_mm_day": [0.0, 0.0, 0.0, 0.0],
                       "precip_hours": np.nan, "rain_flag": 0.0, "wet_day": 0.0, "wind_ms_mean": 3.0})
    # match 101: six balls of innings 1 (no-ball then a free hit); match 202: three balls at overs 0, 100, 230
    n1 = 6
    b = {"match_id": np.array([101] * n1 + [202] * 3, dtype=np.int32), "innings": np.array([1] * n1 + [1, 1, 1], dtype=np.int8),
         "over": np.array([0, 0, 0, 0, 0, 0, 0, 100, 230], dtype=np.int16),
         "ball_in_over": np.array([0, 1, 1, 2, 3, 4, 0, 0, 0], dtype=np.int8),
         "legal_ball_index": np.array([0, 1, 1, 2, 3, 4, 0, 600, 1380], dtype=np.int16),
         "batter_id": np.array([1, 1, 1, 0, 0, 0, 2, 2, -1], dtype=np.int32),
         "bowler_id": np.array([2, 2, 2, 2, 2, 2, 3, 1, 1], dtype=np.int32),
         "review_by": np.full(9, -1, dtype=np.int16), "review_decision": np.full(9, -1, dtype=np.int16),
         "review_umpires_call": np.full(9, -1, dtype=np.int8),
         "bat_fail_reviews": np.zeros(9, dtype=np.int8), "bowl_fail_reviews": np.array([0, 0, 0, 0, 1, 1, 0, 0, 2], dtype=np.int8),
         "prev_free_hit_chain": np.array([0, 0, 1, 0, 0, 0, 0, 0, 0], dtype=np.int8),
         "pp_window_recorded": np.array([1, 1, 1, 1, 1, 1, -1, -1, -1], dtype=np.int16),
         "max_balls_known_before": np.array([120] * n1 + [-1] * 3, dtype=np.int16),
         "match_legal_balls": np.array([0, 1, 1, 2, 3, 4, 0, 600, 1380], dtype=np.int16),
         "est_day": np.array([-1] * n1 + [1, 2, 3], dtype=np.int8), "outcome_class": np.zeros(9, dtype=np.int8)}
    levels = {"review_by": ["bat", "bowl"], "review_decision": ["upheld", "struck_down", "technical"],
              "pp_window_recorded": ["none", "pp1"]}
    return matches, innings, mt, venues, players, wx, b, levels


class BallColumnsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        matches, innings, mt, venues, players, wx, cls.b, levels = _fixture()
        cls.m, full = E.match_table(matches, innings, mt, venues, pd.Series({202: 1}))
        days = E.played_days(cls.m, wx)
        cls.new, cls.lv = E.ball_columns(cls.b, levels, cls.m, full, innings, players, days)

    def cat(self, col):
        return [self.lv[col][c] if c >= 0 else None for c in self.new[col]]

    def test_match_level(self):
        m = self.m.set_index("match_id")
        self.assertEqual(m.at[101, "competition_id"], "ipl")
        self.assertEqual(m.at[101, "season_key"], "ipl:2023")
        self.assertEqual(int(m.at[202, "scheduled_days"]), 5)
        self.assertEqual(int(m.at[101, "scheduled_days"]), 1)
        self.assertTrue(pd.isna(m.at[101, "ball_brand"]))
        self.assertEqual(m.at[202, "ball_brand"], "dukes")
        self.assertEqual(m.at[202, "drs_source"], "match")
        self.assertTrue(bool(m.at[202, "review_topup_after_80"]))

    def test_free_hit_pp_and_restrictions(self):
        n = self.new
        self.assertEqual(n["free_hit"][:6].tolist(), [0, 0, 1, 0, 0, 0])
        self.assertEqual(self.cat("pp_window")[:6], ["pp1"] * 6)
        self.assertEqual(n["field_restr"][:6].tolist(), [2] * 6)
        self.assertEqual(n["field_restr"][6:].tolist(), [-1] * 3)
        self.assertEqual(self.cat("pp_source")[6:], ["rules"] * 3)

    def test_teams_home_players(self):
        self.assertEqual(self.cat("bat_team_id")[0], "chennai_super_kings_m")      # innings 1 batted by team2
        self.assertEqual(self.cat("bat_home_status")[0], "away")
        self.assertEqual(self.cat("bowl_home_status")[0], "home")
        self.assertEqual(self.cat("bat_team_id")[6], "england_m")
        self.assertEqual(self.cat("striker_hand")[:4], ["L", "L", "L", "R"])
        self.assertEqual(self.cat("bowler_class")[0], "pace")
        self.assertEqual(self.new["striker_overseas"].tolist(), [1, 1, 1, 0, 0, 0, -1, -1, -1])
        self.assertEqual(self.new["bowler_overseas"][0], 1)                        # English bowler in India
        self.assertEqual(self.cat("start_slot")[0], "night")

    def test_reviews_left(self):
        n = self.new
        self.assertEqual(n["bat_reviews_left"][:6].tolist(), [-1] * 6)            # IPL match: no review, no series
        self.assertEqual(n["bowl_reviews_left"][6:].tolist(), [2, 2, 0])          # 2015 Test, top-up after 80 overs
        self.assertEqual(n["drs_available"][6:].tolist(), [1, 1, 1])

    def test_clock_and_weather(self):
        n = self.new
        self.assertEqual(n["est_day"][6:].tolist(), [1, 2, 3])
        self.assertEqual(n["est_day"][:6].tolist(), [-1] * 6)
        np.testing.assert_allclose(n["wx_temp_c"], [30.0] * 6 + [18.0, 19.0, 20.0])
        self.assertTrue(np.isnan(n["exp_overs_left"][:6]).all())
        self.assertTrue((np.diff(n["exp_overs_left"][6:]) < 0).all())

    def test_climatology_fill(self):
        clim = pd.DataFrame({"venue_id": ["lords"] * 12 + ["wankhede_stadium"] * 12, "month": list(range(1, 13)) * 2})
        for f in E.WX_CLIMATE.values():
            clim[f] = np.r_[np.arange(12), 100 + np.arange(12)].astype(float)
        frame = pd.DataFrame({"match_id": [202, 101, 202], "est_day": [2, -1, 1],
                              "wx_temp_c": [np.nan, 5.0, 7.0]})
        out = E.climatology_fill(frame, self.m, "2014-01-01", replace=True, clim=clim)
        np.testing.assert_allclose(out.wx_temp_c, [6.0, 103.0, 6.0])         # July at Lord's, April in Mumbai
        out = E.climatology_fill(frame, self.m, "2014-01-01", replace=False, clim=clim)
        np.testing.assert_allclose(out.wx_temp_c, [6.0, 5.0, 7.0])
        self.assertEqual(out.wx_clim.tolist(), [1, 1, 1])                     # other wx columns were filled


class ResourceTest(unittest.TestCase):
    def test_fit_recovers_curve_and_table_rules(self):
        N, rows = 120, []
        for w in range(10):
            z0, b = 250.0 * (1 - w / 10.5), 0.008 * (1 + 0.25 * w)
            u = np.arange(5, N + 1, 5) if w < 6 else np.arange(1, 60)
            for uu in u:
                rows.append(("T20", "male", uu, w, 3.0, RT.z_curve(uu, z0, b), 1.0, 10))
        c = pd.DataFrame(rows, columns=["fam", "gender", "u", "w", "W", "mean", "sd", "n"])
        t = RT.fit(c)["T20"]["male"]
        self.assertAlmostEqual(t["Z0"][0], 250.0, delta=1.0)
        self.assertAlmostEqual(t["b"][3], 0.008 * 1.75, delta=1e-4)
        P = np.array(t["P"])
        self.assertEqual(P.shape, (N + 1, 11))
        self.assertEqual(P[N, 0], 1000)
        self.assertTrue((np.diff(P, axis=0) >= 0).all() and (np.diff(P, axis=1) <= 0).all())
        self.assertTrue((P[0] == 0).all() and (P[:, 10] == 0).all())
        tab = {"tables": {"T20": {"male": t}}}
        self.assertEqual(RT.resource(tab, "T20", "male", 500, 0), 1000)
        self.assertAlmostEqual(float(RT.z_runs(tab, "T20", "male", N, 0)), t["G"], places=6)

    def test_revised_target(self):
        self.assertEqual(RT.revised_target(250, 1000, 800, 245.0), 201)
        self.assertEqual(RT.revised_target(250, 800, 1000, 245.0), 250 + 49 + 1)
        self.assertEqual(RT.revised_target(250, 1000, 1000, 245.0), 251)

    def test_eligibility_and_states(self):
        m = pd.DataFrame({"match_id": [1, 2, 3, 4, 5], "fam": "T20", "gender": "male",
                          "start_date": ["2020-01-01", "2020-01-02", "2020-01-03", "2023-02-01", "2019-01-01"],
                          "scheduled_balls": 120, "awarded": False, "inn1_cut": [False, True, False, False, False],
                          "method": [None, None, "D/L", None, None], "target_balls": [120, 60, 120, 120, np.nan],
                          "balls_per_over": 6})
        inn = pd.DataFrame({"match_id": [1, 2, 3, 4, 5], "innings": 1, "all_out": [False, False, False, False, True],
                            "legal_balls": [120, 60, 120, 120, 50], "runs_deliveries": [160, 70, 150, 150, 90],
                            "pen_pre": [0, 0, 0, 0, 5], "declared": False, "forfeited": False})
        e = RT.eligible_innings(m, inn)
        self.assertEqual(sorted(e.match_id), [1, 5])
        balls = pd.DataFrame({"match_id": [1, 1, 1, 5], "innings": 1, "over": [0, 0, 0, 0], "ball_in_over": [0, 0, 1, 0],
                              "balls_remaining": [120, 120, 119, 120], "inn_runs": [0, 1, 2, 5], "inn_wkts": 0,
                              "max_balls_known_before": 120})
        st = RT.states(balls, e)
        self.assertEqual(len(st), 3)                                         # the wide's repeat position dropped
        self.assertEqual(st.sort_values(["match_id", "u"]).y.tolist(), [158.0, 160.0, 90.0])
        self.assertTrue((st.weight < 1).all() and (st.weight > 0).all())


if __name__ == "__main__":
    unittest.main()
