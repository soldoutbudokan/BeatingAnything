from __future__ import annotations

import json
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from beating.cricket import ingest as ig


def dl(bat, ns, bowl, runs=0, extras=None, wickets=None, review=None, repl=None, non_boundary=False):
    ex = extras or {}
    d = {"batter": bat, "bowler": bowl, "non_striker": ns,
         "runs": {"batter": runs, "extras": sum(ex.values()), "total": runs + sum(ex.values())}}
    if ex:
        d["extras"] = ex
    if non_boundary:
        d["runs"]["non_boundary"] = True
    if wickets:
        d["wickets"] = wickets
    if review:
        d["review"] = review
    if repl:
        d["replacements"] = repl
    return d


def match(innings, teams=("A", "B"), players=None, match_type="T20", bpo=6, overs=20, date="2023-05-01",
          outcome=None, umpires=("U1", "U2"), extra_info=None):
    names = {"U1", "U2", "TV", "REF"}
    for inn in innings:
        for ov in inn.get("overs", []):
            for d in ov["deliveries"]:
                names |= {d["batter"], d["non_striker"], d["bowler"]}
                for w in d.get("wickets", []):
                    names.add(w.get("player_out") or w.get("playeer_out"))
                    names |= {f["name"] for f in w.get("fielders", []) if "name" in f}
                for lst in d.get("replacements", {}).values():
                    names |= {x[k] for x in lst for k in ("in", "out") if x.get(k)}
    for pl in (players or {}).values():
        names |= set(pl)
    info = {"balls_per_over": bpo, "city": "Leeds", "dates": [date], "event": {"name": "Test Cup", "match_number": 1},
            "gender": "male", "match_type": match_type, "officials": {"umpires": list(umpires), "tv_umpires": ["TV"],
                                                                      "match_referees": ["REF"]},
            "outcome": outcome or {"winner": teams[0], "by": {"runs": 1}}, "players": players or {},
            "registry": {"people": {n: f"id_{n}" for n in sorted(names)}}, "season": 2023, "team_type": "club",
            "teams": list(teams), "toss": {"decision": "bat", "winner": teams[0]}, "venue": "Headingley"}
    if overs is not None:
        info["overs"] = overs
    info.update(extra_info or {})
    return {"meta": {"data_version": "1.2.0"}, "info": info, "innings": innings}


def t20_fixture():
    """Two 2-over innings reduced equally before the match (no method), with most special cases."""
    a = [f"a{i}" for i in range(1, 13)]
    b = [f"b{i}" for i in range(1, 12)]
    o0 = [
        dl("a1", "a2", "b1", 1),
        dl("a2", "a1", "b1", extras={"wides": 1}),
        dl("a2", "a1", "b1", 4, extras={"noballs": 1}),
        dl("a2", "a1", "b1", extras={"wides": 1}),
        dl("a2", "a1", "b1", 0),
        dl("a2", "a1", "b1", 5),
        dl("a1", "a2", "b1", 0, wickets=[{"kind": "caught", "player_out": "a1", "fielders": [{"name": "b2"}]}],
           review={"by": "A", "umpire": "U1", "batter": "a1", "decision": "struck down", "umpires_call": True}),
        dl("a3", "a2", "b1", 4, non_boundary=True),
        dl("a3", "a2", "b1", 0, wickets=[{"kind": "retired hurt", "player_out": "a2"}]),
    ]
    o1 = [
        dl("a4", "a3", "b2", 2),
        dl("a4", "a3", "b2", 0, wickets=[{"kind": "lbw", "player_out": "a4"}],
           review={"by": "B", "umpire": "U2", "batter": "a4", "decision": "upheld"}),
        dl("a5", "a3", "b3", 1, repl={"role": [{"in": "b3", "reason": "injury", "role": "bowler"}]}),
        dl("a3", "a5", "b3", 0, review={"by": "B", "umpire": "U2", "batter": "a3", "decision": "struck down"}),
        dl("a3", "a5", "b3", 0, wickets=[{"kind": "bowled", "playeer_out": "a3"}]),
        dl("a6", "a5", "b3", 0),
    ]
    p0 = [
        dl("b1", "b2", "a7", 0, review={"by": "B", "umpire": "U2", "batter": "b1", "decision": "upheld"}),
        dl("b3", "b2", "a7", 6, repl={"role": [{"in": "b3", "out": "b1", "reason": "injury", "role": "batter"}]}),
        dl("b3", "b2", "a7", 1),
        dl("b2", "b3", "a7", 0),
        dl("b2", "b3", "a7", 0, wickets=[{"kind": "caught", "player_out": "b2", "fielders": [{"substitute": True}]}]),
        dl("b1", "b3", "a7", 4),
    ]
    p1 = [dl("b3", "b1", "a8", 0, repl={"match": [{"in": "a12", "out": "a11", "reason": "impact_player", "team": "A"}]})]
    so = [dl("b1", "b3", "a8", 1), dl("b3", "b1", "a8", 0, wickets=[{"kind": "bowled", "player_out": "b3"}])]
    innings = [
        {"team": "A", "overs": [{"over": 0, "deliveries": o0}, {"over": 1, "deliveries": o1}],
         "powerplays": [{"from": 0.1, "to": 0.9, "type": "mandatory"}]},
        {"team": "B", "overs": [{"over": 0, "deliveries": p0}, {"over": 1, "deliveries": p1}],
         "target": {"runs": 21, "overs": 2}},
        {"team": "B", "overs": [{"over": 0, "deliveries": so}], "super_over": True},
    ]
    return match(innings, players={"A": a, "B": b}, outcome={"winner": "A", "by": {"runs": 9}})


def test_fixture():
    """Four-innings Test: England 30, Australia 10 and following on 25 (with an over 81), England need 6."""
    i1 = [dl("a1", "a2", "b1", 6) for _ in range(5)] + [dl("a1", "a2", "b1", 0)]
    i2 = [dl("b1", "b2", "a1", 1) for _ in range(6)] + [dl("b2", "b1", "a2", 1) for _ in range(4)] + \
         [dl("b2", "b1", "a2", 0, wickets=[{"kind": "bowled", "player_out": "b2"}]) for _ in range(1)] + \
         [dl("b3", "b1", "a2", 0)]
    i3 = [dl("b1", "b3", "a1", 4) for _ in range(6)] + [dl("b1", "b3", "a2", 1)] + [dl("b3", "b1", "a2", 0)] * 5
    i4 = [dl("a1", "a2", "b1", 1) for _ in range(6)]
    innings = [
        {"team": "England", "overs": [{"over": 0, "deliveries": i1}]},
        {"team": "Australia", "overs": [{"over": 0, "deliveries": i2[:6]}, {"over": 1, "deliveries": i2[6:]}]},
        {"team": "Australia", "overs": [{"over": 0, "deliveries": i3[:6]}, {"over": 81, "deliveries": i3[6:]}]},
        {"team": "England", "overs": [{"over": 0, "deliveries": i4}]},
    ]
    return match(innings, match_type="Test", overs=None, date="2023-06-01",
                 outcome={"winner": "A", "by": {"wickets": 10}}, teams=("England", "Australia"),
                 extra_info={"dates": ["2023-06-01", "2023-06-02", "2023-06-03"], "team_type": "international"})


def hundred_fixture():
    sets = []
    for s in range(5):
        bowler = {0: "h1", 1: "h1", 2: "h2", 3: "h3", 4: "h1"}[s]
        dels = [dl("x1", "x2", bowler, 1 if j % 2 == 0 else 0) for j in range(5)]
        if s == 2:
            dels[0]["review"] = {"by": "H", "umpire": "U1", "batter": "x1", "decision": "struck down"}
        sets.append({"over": s, "deliveries": dels})
    innings = [{"team": "G", "overs": sets}, {"team": "H", "overs": [{"over": 0, "deliveries": [dl("y1", "y2", "g1", 1)]}],
                                                  "target": {"runs": 30, "overs": 8.4}}]
    return match(innings, teams=("G", "H"), bpo=5, overs=20, date="2023-08-01",
                 outcome={"winner": "G", "by": {"runs": 20}, "method": "D/L"})


def parse(d, stem="1000"):
    pid = {v: i for i, v in enumerate(sorted(d["info"]["registry"]["people"].values()))}
    return ig.parse_match(d, int(stem), pid, stem), {k: pid[v] for k, v in d["info"]["registry"]["people"].items()}


def rows_frame(p):
    cols = ig.assemble([p])
    return ig.to_frame(cols)


class SmallParsers(unittest.TestCase):
    def test_overs_notation(self):
        self.assertEqual(ig.overs_to_balls(40.2, 6), 242)
        self.assertEqual(ig.overs_to_balls(8.4, 5), 44)
        self.assertEqual(ig.overs_to_balls("8.4", 5), 44)
        self.assertEqual(ig.overs_to_balls(50, 6), 300)

    def test_match_id_stems(self):
        self.assertEqual(ig.match_id_of("1152847"), 1152847)
        self.assertEqual(ig.match_id_of("wi_201706"), 90_201_706)

    def test_powerplay_levels_and_tenth_delivery(self):
        w = ig.powerplay_windows([{"from": 10.1, "to": 39.6, "type": "mandatory"},
                                  {"from": 0.1, "to": 9.6, "type": "mandatory"},
                                  {"from": 40.1, "to": 49.1, "type": "mandatory"}], "ODI", {49: 10})
        self.assertEqual([x[4] for x in w], [ig.PP_CODE[k] for k in ("pp1", "pp2", "pp3")])
        self.assertEqual(w[2][3], 10)
        self.assertEqual(ig.pp_level(w, 49, 10), ig.PP_CODE["pp3"])
        self.assertEqual(ig.pp_level(w, 9, 6), ig.PP_CODE["pp1"])
        self.assertEqual(ig.pp_level(w, 9, 7), ig.PP_CODE["none"])
        surge = ig.powerplay_windows([{"from": 12.1, "to": 13.6, "type": "batting"}], "T20", {})
        self.assertEqual(surge[0][4], ig.PP_CODE["power_surge"])
        self.assertEqual(ig.powerplay_windows([{"from": 30.1, "to": 34.6, "type": "batting"}], "ODI", {})[0][4],
                         ig.PP_CODE["batting"])

    def test_outcome_classes(self):
        self.assertEqual(ig.outcome_class(0, 5, 0, ig.NA), 4)
        self.assertEqual(ig.outcome_class(0, 7, 0, ig.NA), 5)
        self.assertEqual(ig.outcome_class(0, 4, 0, ig.NA), 4)
        self.assertEqual(ig.outcome_class(0, 0, 2, ig.NA), 8)
        self.assertEqual(ig.outcome_class(0, 1, 0, ig.WK_OF["run out"]), 7)
        self.assertEqual(ig.outcome_class(0, 0, 0, ig.WK_OF["lbw"]), 6)
        self.assertEqual(ig.outcome_class(1, 0, 0, ig.NA), ig.NA)
        self.assertEqual(ig.outcome_class(2, 6, 0, ig.NA), 5)

    def test_reconstruction_table(self):
        lbw, caught = ig.WK_OF["lbw"], ig.WK_OF["caught"]
        rc = lambda *a: ig.reconstruct(*a)
        self.assertEqual(rc(0, 6, lbw, 0, 1, 1), (1, True, 6, lbw, True))       # batting review struck down
        self.assertEqual(rc(0, 0, ig.NA, 0, 0, ig.NA), (2, True, 6, ig.NA, False))  # batting review upheld
        self.assertEqual(rc(0, 6, caught, 1, 0, 1), (3, False, 0, ig.NA, True))  # fielding review upheld
        self.assertEqual(rc(0, 1, ig.NA, 1, 1, ig.NA), (4, False, 1, ig.NA, False))  # fielding struck down
        self.assertEqual(rc(1, ig.NA, ig.NA, 0, 0, ig.NA)[0], ig.RECON.index("ignored_extra"))
        self.assertEqual(rc(0, 6, lbw, 0, 2, 1)[0], ig.RECON.index("technical"))
        self.assertEqual(rc(0, 6, lbw, 0, 1, 0), (7, True, 6, lbw, True))       # review of another batter
        self.assertEqual(rc(0, 7, ig.WK_OF["run out"], 1, 1, 1)[0], ig.RECON.index("ignored_other"))

    def test_umpire_end_votes(self):
        p, a, b = ig.umpire_end_p([(0, "U1")], "U1", "U2")
        self.assertAlmostEqual(p, 0.98)
        p, a, b = ig.umpire_end_p([(0, "U1"), (1, "U2"), (0, "U1")], "U1", "U2")
        self.assertAlmostEqual(p, 0.98 ** 3 / (0.98 ** 3 + 0.02 ** 3))
        self.assertEqual((a, b), (3, 0))
        self.assertAlmostEqual(ig.umpire_end_p([(0, "U2")], "U1", "U2")[0], 0.02)
        self.assertEqual(ig.umpire_end_p([(0, "U1"), (0, "U2")], "U1", "U2")[0], 0.5)
        self.assertEqual(ig.umpire_end_p([(0, "X")], "U1", "U2")[0], 0.5)
        self.assertEqual(ig.umpire_end_p([], None, None)[0], 0.5)

    def test_est_rate(self):
        opd, r = ig.est_rate(36, 6, 3, "win", 5)
        self.assertEqual(opd, 90)
        self.assertAlmostEqual(r, 6 / 2.5)
        self.assertEqual(ig.est_rate(6 * 600, 6, 5, "draw", 4), (98, 98))
        self.assertAlmostEqual(ig.est_rate(6 * 300, 6, 5, "draw", 5)[1], 60.0)


def inn(legal, total, allout=False, target=None):
    return dict(legal=legal, total=total, allout=allout, target_raw=target)


class Targets(unittest.TestCase):
    def test_original_full_length(self):
        per, meta = ig.limited_targets([inn(120, 150), inn(100, 151, target={"runs": 151, "overs": 20})], 120, 6, None)
        self.assertEqual((per[1]["target"], per[1]["timing"], per[1]["max_balls"]), (151, 0, 120))
        self.assertEqual(meta["target_timing"], "original")

    def test_pre_match_equal_reduction(self):
        per, _ = ig.limited_targets([inn(60, 80), inn(40, 70, target={"runs": 81, "overs": 10})], 120, 6, None)
        self.assertEqual((per[1]["timing"], per[1]["max_balls"], per[0]["max_balls"]), (1, 60, 60))

    def test_dl_innings1_cut_keeps_scheduled_length_for_innings1(self):
        per, meta = ig.limited_targets([inn(242, 200), inn(100, 150, target={"runs": 230, "overs": 40.2})], 300, 6, "D/L")
        self.assertEqual((per[1]["timing"], per[1]["max_balls"], per[0]["max_balls"]), (1, 242, 300))
        self.assertTrue(meta["inn1_cut"])

    def test_dl_after_full_innings1_is_unknown(self):
        per, _ = ig.limited_targets([inn(300, 250), inn(150, 180, target={"runs": 200, "overs": 35})], 300, 6, "D/L")
        self.assertEqual((per[1]["timing"], per[1]["max_balls"], per[1]["target"]), (2, 300, 200))

    def test_reduction_after_full_innings1_without_method(self):
        per, _ = ig.limited_targets([inn(300, 250), inn(150, 180, target={"runs": 251, "overs": 45})], 300, 6, None)
        self.assertEqual((per[1]["timing"], per[1]["max_balls"], per[0]["max_balls"]), (1, 270, 300))

    def test_missing_target(self):
        per, _ = ig.limited_targets([inn(120, 150), inn(110, 151)], 120, 6, None)
        self.assertEqual((per[1]["target"], per[1]["timing"]), (151, 0))
        per, _ = ig.limited_targets([inn(120, 150), inn(30, 40)], 120, 6, None)
        self.assertEqual((per[1]["target"], per[1]["timing"], per[1]["known"]), (ig.NA, 2, False))
        per, _ = ig.limited_targets([inn(120, 150), inn(110, 160)], 120, 6, "D/L")
        self.assertEqual(per[1]["timing"], 2)


class ParseT20(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.pid = parse(t20_fixture())
        cls.b = rows_frame(cls.p)
        cls.i1 = cls.b[cls.b.innings == 1].reset_index(drop=True)
        cls.i2 = cls.b[cls.b.innings == 2].reset_index(drop=True)

    def test_rows_and_super_over(self):
        self.assertEqual(len(self.b), 15 + 7)
        self.assertEqual(len(self.p["super_overs"]), 2)
        self.assertEqual(self.p["match"]["n_balls"], 22)
        self.assertTrue(self.p["match"]["super_over"])

    def test_runs_wickets_and_unavailable(self):
        r = self.i1
        self.assertEqual(list(r.inn_runs[:7]), [0, 1, 2, 7, 8, 8, 13])
        self.assertEqual(r.inn_wkts[14], 3)
        self.assertEqual(r.inn_unavailable[14], 4)      # 3 wickets + a2 retired hurt
        self.assertEqual(r.inn_unavailable[9], 2)
        inns = {x["innings"]: x for x in self.p["innings"]}
        self.assertEqual((inns[1]["total"], inns[1]["state_final_runs"], inns[1]["wkts_raw"], inns[1]["state_final_wkts"]),
                         (20, 20, 3, 3))
        self.assertEqual(self.p["stats"]["playeer_out"], 1)
        self.assertEqual(r.player_out_id[13], self.pid["a3"])

    def test_batter_counters_and_partnership(self):
        r = self.i1
        self.assertEqual((r.striker_runs[4], r.striker_balls[4]), (4, 1))  # a2: no-ball counted, wides not
        self.assertEqual((r.striker_runs[6], r.striker_balls[6]), (1, 1))  # a1
        self.assertEqual((r.partnership_runs[6], r.partnership_balls[6]), (13, 4))
        self.assertEqual((r.partnership_runs[7], r.partnership_balls[7]), (0, 0))
        self.assertEqual(list(r.striker_arrival[[0, 7, 9, 11, 14]]), [1, 3, 4, 5, 6])
        self.assertEqual(r.nonstriker_arrival[0], 2)

    def test_delivery_types_and_free_hit_chain(self):
        r = self.i1
        self.assertEqual(list(r.dtype[:5].astype(str)), ["legal", "wide", "noball", "wide", "legal"])
        self.assertEqual(list(r.prev_dtype[1:6].astype(str)), ["legal", "wide", "noball", "wide", "legal"])
        self.assertTrue(pd.isna(r.prev_dtype[0]))
        self.assertEqual(list(r.prev_free_hit_chain[:6]), [0, 0, 0, 1, 1, 0])
        self.assertEqual(list(r.ball_in_over[:6]), [0, 1, 1, 1, 1, 2])
        self.assertEqual(r.legal_ball_index[9], 6)
        self.assertEqual(r.outcome_class[5], 4)          # five runs -> four class
        self.assertTrue(r.non_boundary[7])
        self.assertEqual(r.outcome_class[1], ig.NA)

    def test_bowlers_and_spells(self):
        r = self.i1
        self.assertEqual(r.bowler_balls_inn[8], 5)
        self.assertEqual((r.bowler_id[11], r.bowler_balls_inn[11]), (self.pid["b3"], 0))
        ev = pd.DataFrame(self.p["events"], columns=ig.EVENT_COLS)
        self.assertEqual(ev[ev.event == "bowler_change_mid_over"].player_id.tolist(), [self.pid["b3"]])

    def test_reviews_and_reconstruction(self):
        r = self.i1
        self.assertEqual(r.recon_case[6], "bat_struck_down")
        self.assertEqual(r.review_umpires_call[6], 1)
        self.assertEqual((r.recon_case[10], r.onfield_class[10], bool(r.final_out[10])), ("bowl_upheld", 0, True))
        self.assertEqual(list(r.bat_fail_reviews), [0] * 15)  # umpire's call keeps the review
        self.assertEqual(list(r.bowl_fail_reviews[12:15]), [0, 1, 1])
        self.assertEqual(r.review_umpires_call[12], 0)
        q = self.i2
        self.assertEqual((q.recon_case[0], q.onfield_class[0], bool(q.onfield_out[0]), bool(q.final_out[0])),
                         ("bat_upheld", 6, True, False))

    def test_umpire_end(self):
        p3 = 0.98 ** 3 / (0.98 ** 3 + 0.02 ** 3)
        self.assertAlmostEqual(float(self.i1.bowl_end_umpire_p[0]), p3, places=6)
        self.assertAlmostEqual(float(self.i1.bowl_end_umpire_p[9]), 1 - p3, places=6)
        self.assertAlmostEqual(float(self.i2.bowl_end_umpire_p[0]), 0.02, places=6)
        self.assertAlmostEqual(float(self.i2.bowl_end_umpire_p[6]), 0.98, places=6)

    def test_powerplay_and_lengths(self):
        r = self.i1
        self.assertEqual(set(r.pp_window_recorded[:9].astype(str)), {"pp1"})
        self.assertEqual(set(r.pp_window_recorded[9:].astype(str)), {"none"})
        self.assertTrue(self.i2.pp_window_recorded.isna().all())
        self.assertEqual(list(r.max_balls_known_before.unique()), [12])
        self.assertEqual((r.balls_remaining[0], r.balls_remaining[9]), (12, 6))
        self.assertEqual(r.target_runs[0], ig.NA)

    def test_chase_state(self):
        q = self.i2
        self.assertEqual(set(q.target_runs), {21})
        self.assertEqual(set(q.target_timing.astype(str)), {"pre_inn2"})
        self.assertEqual(list(q.runs_required[:3]), [21, 21, 15])
        self.assertTrue(q.target_known.all())
        self.assertEqual(self.p["match"]["target_timing"], "pre_inn2")

    def test_temporary_retirement_and_resumption(self):
        q = self.i2
        ev = pd.DataFrame(self.p["events"], columns=ig.EVENT_COLS)
        tr = ev[ev.event == "temporary_retirement"]
        self.assertEqual((tr.player_id.tolist(), tr.other_id.tolist(), tr.ball_seq.tolist()),
                         ([self.pid["b1"]], [self.pid["b3"]], [1]))
        self.assertEqual(ev[ev.event == "resumption"].ball_seq.tolist(), [5])
        self.assertEqual(list(q.inn_unavailable[:6]), [0, 1, 1, 1, 1, 1])
        self.assertEqual((q.striker_arrival[5], q.striker_runs[5], q.striker_balls[5]), (1, 0, 1))
        self.assertEqual((q.partnership_runs[1], q.partnership_balls[1]), (0, 0))
        self.assertEqual(ev[ev.event == "retired_hurt"].player_id.tolist(), [self.pid["a2"]])

    def test_match_row(self):
        m = self.p["match"]
        self.assertEqual(m["fam"], "T20")
        self.assertEqual(m["season"], "2023")
        self.assertEqual(json.loads(m["xi_start_team1"]), [self.pid[f"a{i}"] for i in range(1, 12)])
        self.assertEqual(m["n_listed_team1"], 12)
        self.assertEqual(json.loads(m["subs"])[0]["reason"], "impact_player")
        self.assertEqual(json.loads(m["bat_order_team1_inn1"]), [self.pid[f"a{i}"] for i in range(1, 7)])
        self.assertEqual(m["umpire1_id"], self.pid["U1"])
        self.assertTrue(m["inn1_cut"])
        self.assertEqual(m["target_balls"], 12)


class ParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.pid = parse(test_fixture())
        cls.b = rows_frame(cls.p)

    def test_follow_on_lead_and_target(self):
        m = self.p["match"]
        self.assertTrue(m["follow_on"])
        i3 = self.b[self.b.innings == 3].reset_index(drop=True)
        self.assertEqual(i3.lead[0], -20)
        self.assertEqual(i3.lead[6], 4)
        i4 = self.b[self.b.innings == 4].reset_index(drop=True)
        self.assertEqual((i4.target_runs[0], i4.runs_required[0], i4.runs_required[5]), (6, 6, 1))
        self.assertEqual(self.b[self.b.innings == 1].lead.tolist()[:2], [0, 6])
        self.assertTrue(self.b[self.b.innings < 4].target_runs.eq(ig.NA).all())
        self.assertTrue(self.b.max_balls_known_before.eq(ig.NA).all())

    def test_ball_age_and_days(self):
        i3 = self.b[self.b.innings == 3].reset_index(drop=True)
        self.assertEqual((i3.ball_age_overs[0], i3.ball_age_overs[6], i3.second_new_ball[0], i3.second_new_ball[6]),
                         (0, 1, 0, 1))
        r = 6 / 2.5
        mlb = self.b.match_legal_balls.to_numpy()
        expect = np.minimum(3, 1 + np.floor(mlb / 6 / r))
        self.assertEqual(self.b.est_day.tolist(), expect.astype(int).tolist())
        self.assertEqual(self.b.est_day.max(), 3)
        self.assertEqual(self.p["match"]["est_opd"], 90)

    def test_match_legal_balls_running(self):
        self.assertEqual(self.b.match_legal_balls.tolist(), list(range(len(self.b))))


class ParseOther(unittest.TestCase):
    def test_hundred(self):
        p, pid = parse(hundred_fixture())
        b = rows_frame(p)
        self.assertEqual(p["match"]["fam"], "HUNDRED")
        i1 = b[b.innings == 1].reset_index(drop=True)
        # review in set 2 (block 1) names U1 -> U1 at odd blocks
        self.assertAlmostEqual(float(i1.bowl_end_umpire_p[0]), 0.02, places=6)
        self.assertAlmostEqual(float(i1.bowl_end_umpire_p[10]), 0.98, places=6)
        self.assertAlmostEqual(float(i1.bowl_end_umpire_p[20]), 0.02, places=6)
        self.assertEqual((i1.bowler_spell_overs[5], i1.bowler_spell_overs[20]), (1, 2))
        self.assertEqual(p["match"]["target_balls"], 44)
        self.assertEqual(p["match"]["scheduled_balls"], 100)
        self.assertEqual(b[b.innings == 2].max_balls_known_before.tolist(), [100])

    def test_overs_fix_forfeit_and_uncontested_toss(self):
        d = match([{"team": "A", "overs": [{"over": 0, "deliveries": [dl("a1", "a2", "b1", 1)]}]},
                   {"team": "B", "forfeited": True}], overs=50,
                  extra_info={"toss": {"uncontested": True, "decision": "field", "winner": "B"}, "season": "2022/23"})
        p, _ = parse(d)
        self.assertEqual((p["match"]["scheduled_overs"], p["match"]["scheduled_overs_fix"]), (20, "50->20"))
        self.assertTrue(p["match"]["toss_uncontested"])
        self.assertEqual(p["match"]["season"], "2022/23")
        self.assertEqual(len(p["rows"]), 1)
        self.assertEqual([e[3] for e in p["events"]], ["forfeiture"])
        self.assertTrue(p["innings"][1]["forfeited"])

    def test_double_wicket_and_neither_role(self):
        d = match([{"team": "A", "overs": [{"over": 0, "deliveries": [
            dl("a1", "a2", "b1", 0, wickets=[{"kind": "bowled", "player_out": "a1"},
                                             {"kind": "retired out", "player_out": "a9"}]),
            dl("a3", "a2", "b1", 0, wickets=[{"kind": "timed out", "player_out": "a4"}])]}]}])
        p, pid = parse(d)
        b = rows_frame(p)
        self.assertTrue(b.second_wicket[0])
        self.assertEqual((b.wk[0], b.retire_event[0]), ("bowled", "retired_out"))
        self.assertEqual(b.inn_wkts[1], 2)
        self.assertTrue(pd.isna(b.wk[1]))
        self.assertEqual(p["innings"][0]["state_final_wkts"], 3)
        ev = [e[3] for e in p["events"]]
        self.assertEqual(ev, ["retired_out", "timed_out"])

    def test_two_ball_wickets_on_one_delivery(self):
        d = match([{"team": "A", "overs": [{"over": 0, "deliveries": [
            dl("a1", "a2", "b1", 0, wickets=[{"kind": "bowled", "player_out": "a1"},
                                             {"kind": "run out", "player_out": "a2", "fielders": [{"name": "b2"}]}]),
            dl("a3", "a4", "b1", 0)]}]}])
        p, pid = parse(d)
        b = rows_frame(p)
        self.assertEqual((b.wk[0], b.player_out_id[0], b.inn_wkts[1]), ("bowled", pid["a1"], 2))
        self.assertEqual([(e[3], e[4], e[7]) for e in p["events"]], [("second_ball_wicket", pid["a2"], "run out")])
        self.assertEqual(list(b.striker_arrival), [1, 3])


class WholeTable(unittest.TestCase):
    def test_player_context_strictly_earlier(self):
        pi = pd.DataFrame([(1, 1, 1, 7, 3, 3, 0, 0, 0), (2, 1, 1, 7, 5, 2, 0, 0, 0), (3, 1, 1, 7, 4, 1, 0, 6, 0),
                           (3, 2, 1, 7, 6, 1, 0, 0, 0), (4, 1, 1, 7, 2, 0, 0, 0, 0)], columns=ig.PI_COLS)
        matches = pd.DataFrame({"match_id": [1, 2, 3, 4],
                                "start_date": ["2020-01-01", "2020-01-01", "2020-02-01", "2020-03-01"],
                                "fit_fam": ["T20", "T20", "T20", "ODI"], "gender": ["male"] * 4})
        ctx = ig.player_context(pi, matches).set_index("match_id")
        self.assertEqual(ctx.striker_exp.tolist(), [0, 0, 5, 0])
        self.assertEqual(ctx.bowler_exp.tolist(), [0, 0, 0, 0])
        self.assertTrue(math.isnan(ctx.striker_role_pos[1]))
        self.assertEqual(ctx.striker_role_pos[3], 4.0)       # median of 3 and 5
        self.assertTrue(math.isnan(ctx.striker_role_pos[4]))  # other family

    def test_overturned_kind_imputation(self):
        n = 40
        balls = pd.DataFrame({
            "match_id": np.repeat([1, 2], n // 2), "innings": 1, "ball_seq": np.arange(n),
            "recon_case": pd.Categorical.from_codes([1] * 30 + [2] * 10, categories=list(ig.RECON)),
            "wk": pd.Categorical.from_codes([2] * 27 + [0] * 3 + [-1] * 10, categories=list(ig.WK)),
            "onfield_wk": pd.Categorical.from_codes([2] * 27 + [0] * 3 + [-1] * 10, categories=list(ig.WK))})
        matches = pd.DataFrame({"match_id": [1, 2], "start_date": ["2020-01-01", "2020-05-01"], "fit_fam": ["ODI", "ODI"]})
        info = ig.impute_overturned_kind(balls, matches)
        self.assertAlmostEqual(info["family_lbw_share"]["ODI"], 0.9)
        self.assertEqual(info["n_imputed"], 10)
        self.assertTrue(balls.onfield_wk[30:].isin(["lbw", "caught"]).all())
        self.assertTrue(np.allclose(balls.onfield_wk_p_lbw[30:], 0.9))
        again = balls.copy()
        ig.impute_overturned_kind(again, matches)
        self.assertTrue((again.onfield_wk == balls.onfield_wk).all())

    def test_zip_build_validate_and_parquet_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zp = Path(tmp) / "all.zip"
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr("1001.json", json.dumps(t20_fixture()))
                z.writestr("1002.json", json.dumps(test_fixture()))
                z.writestr("wi_201706.json", json.dumps(hundred_fixture()))
                z.writestr("README.txt", "x")
            people = ig.scan_people(zp, people_csv=None)
            self.assertEqual(people.person_id.tolist(), list(range(len(people))))
            t = ig.parse_zip(zp, people, workers=2, chunk=1)
            self.assertEqual(t["failures"], [])
            self.assertEqual(t["matches"].match_id.tolist(), [1001, 1002, 90_201_706])
            ig.enrich(t)
            self.assertEqual(len(t["balls"]), 22 + 36 + 26)
            self.assertEqual(t["balls"].bat_team.iloc[0], "A")
            self.assertEqual(t["balls"].bowl_team.iloc[0], "B")
            rep = ig.validate(t)
            for k, v in rep["1_innings_totals"].items():
                if "agree" in v and k.endswith("equal"):
                    self.assertEqual(v["agree"], v["n"], k)
            json.dumps(rep, default=str)
            sizes = ig.write_all(t, Path(tmp) / "out")
            self.assertEqual(sizes["balls"]["rows"], 84)
            back = ig.read_table(Path(tmp) / "out" / "balls.parquet")
            self.assertEqual(list(back.columns), t["ball_columns"])
            self.assertTrue(back.target_runs.isna().any() and back.target_runs.notna().any())
            self.assertEqual(str(back.target_runs.dtype), "Int16")
            self.assertEqual(str(back.dtype.dtype), "category")
            self.assertTrue(back.review_umpires_call.isna().any())
            self.assertEqual(int(back.inn_runs.sum()), int(t["balls"].inn_runs.sum()))
            self.assertEqual(len(ig.read_table(Path(tmp) / "out" / "people_index.parquet")), len(people))
            ev = ig.read_table(Path(tmp) / "out" / "events.parquet")
            self.assertTrue(ev.ball_seq.isna().any())          # innings-level events (follow-on) have no delivery
            self.assertEqual(str(ev.player_id.dtype), "Int32")
            m = ig.read_table(Path(tmp) / "out" / "matches.parquet")
            self.assertEqual(m.umpire1_id.notna().all(), True)
            self.assertEqual(str(m.match_id.dtype), "int32")
            two = ig.read_table(Path(tmp) / "out" / "balls.parquet", columns=["match_id", "wk"])
            self.assertEqual(list(two.columns), ["match_id", "wk"])


if __name__ == "__main__":
    unittest.main()
