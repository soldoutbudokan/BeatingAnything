"""Tests for the scalar cricket engine (beating/cricket/sim.py), its stub provider and the parity vectors.

The invariant checks run 2,000 stub simulations per family in a small process pool (fork) so the
suite stays around a minute of wall time.
"""
from collections import Counter
import copy
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import unittest

import numpy as np

from beating.cricket import provider as P
from beating.cricket import rng, sim
from tools import make_cricket_parity_vectors as V

ROOT = Path(__file__).resolve().parents[1]
PARITY = ROOT / "tests" / "data" / "cricket_parity"
SEED = 2026
N_INV = 2000


def inv_scenario(fam: str, gender: str = "male") -> dict:
    return V.scen(fam, gender=gender, toss=None, weather={"rain_risk": 0.25 if fam != "TEST" else 0.2},
                  player_form={"A2": {"bat_runs_sd": 0.8}}, pitch={"runs_sd": -0.3})


def check_match(m: sim.Match, pr: sim.Prepared) -> list[str]:
    """Rule invariants of one finished simulation; [] when it is consistent."""
    errs = []
    res = m.result
    if res is None or res["result"] not in ("win", "tie", "draw", "no_result"):
        return [f"bad result {res}"]
    if res["result"] == "win" and res["winner"] not in (0, 1):
        errs.append("win without a winner")
    if pr.limited and res["result"] == "draw":
        errs.append("draw in limited overs")
    if not pr.limited and res["result"] == "no_result":
        errs.append("no result in a Test")
    it = m.inn_team
    if pr.fam == "TEST" and it not in ([0, 1, 0, 1], [1, 0, 1, 0], [0, 1, 1, 0], [1, 0, 0, 1]):
        errs.append(f"innings order {it}")
    if m.followed_on != (pr.fam == "TEST" and it[2] == it[1]):
        errs.append("follow-on flag inconsistent with the innings order")
    for k, c in enumerate(m.done):
        tag = f"inn {k + 1}"
        if c.team != it[k]:
            errs.append(f"{tag}: team {c.team} != innings order {it[k]}")
        if c.end not in sim.END_REASONS:
            errs.append(f"{tag}: end {c.end}")
        if not 0 <= c.wkts <= 10 or c.runs < 0:
            errs.append(f"{tag}: {c.runs}/{c.wkts}")
        outs = [p for p, b in c.bat.items() if b[3] is not None]
        if len(outs) != c.wkts:
            errs.append(f"{tag}: wickets {c.wkts} != dismissed {len(outs)}")
        if c.end == "all_out" and c.wkts < 10 and c.to_come:
            errs.append(f"{tag}: all out with batters left")
        if c.end != "all_out" and c.wkts >= 10:
            errs.append(f"{tag}: ten down but ended {c.end}")
        if c.end in ("declared", "clock") and pr.limited:
            errs.append(f"{tag}: {c.end} in limited overs")
        if c.end in ("balls", "cut", "no_result") and not pr.limited:
            errs.append(f"{tag}: {c.end} in a Test")
        if c.end == "balls" and c.legal != c.max_balls:
            errs.append(f"{tag}: balls end at {c.legal}/{c.max_balls}")
        if c.end == "target" and c.runs < c.target:
            errs.append(f"{tag}: target end short of the target")
        if c.end == "declared" and (c.number == 4 or (c.number == 3 and c.agg_bat + c.runs <= c.agg_opp)):
            errs.append(f"{tag}: illegal declaration")
        if c.max_balls is not None and c.legal > c.max_balls:
            errs.append(f"{tag}: {c.legal} legal balls > {c.max_balls}")
        if sum(b[0] for b in c.bowl.values()) != c.legal:
            errs.append(f"{tag}: bowler balls != legal balls")
        bat_runs = sum(b[0] for b in c.bat.values())
        if bat_runs + c.extras != c.runs:
            errs.append(f"{tag}: batter runs + extras != total")
        if sum(b[1] for b in c.bowl.values()) != bat_runs + c.extras - c.byes:
            errs.append(f"{tag}: bowler runs != bat runs + wides + no-ball penalties")
        ro = sum(1 for b in c.bat.values() if b[3] == "run_out")
        if sum(b[2] for b in c.bowl.values()) != c.wkts - ro:
            errs.append(f"{tag}: bowler wickets != wickets - run-outs")
        ob = c.over_bowlers
        if any(a == b for a, b in zip(ob, ob[1:])):
            errs.append(f"{tag}: consecutive overs by one bowler")
        if len(ob) != c.legal // 6:
            errs.append(f"{tag}: {len(ob)} overs for {c.legal} legal balls")
        if pr.limited and c.max_balls == pr.rules["max_balls"]:
            base, bonus = sim.quota(c.max_balls // 6, pr.qrule)
            cnt = Counter(ob)
            if max(cnt.values(), default=0) > base + (1 if bonus else 0) or \
                    sum(1 for x in cnt.values() if x > base) > bonus:
                errs.append(f"{tag}: quota exceeded {dict(cnt)}")
    if pr.fam == "TEST" and m._used() > m.A_total and not (m.cur is None and res["result"] == "draw"):
        errs.append("Test clock overrun")   # only an innings changeover may pass the end of time

    if m.stats["bowler_fallback"]:
        errs.append("bowler feasibility fallback used")
    return errs


def _inv_worker(args):
    fam, gender, lo, hi = args
    pr = sim.Prepared(inv_scenario(fam, gender))
    acc, errs = sim.Acc(pr.rules["max_balls"] // 6 if pr.limited else None), []
    for i in range(lo, hi):
        m = sim.Match(pr, i, SEED).play()
        errs += [f"sim {i}: {e}" for e in check_match(m, pr)]
        acc.add(m.record())
    return (fam, gender), errs[:20], acc


def _pool_map(tasks):
    workers = max(1, min(3, (os.cpu_count() or 2) - 1))
    if workers == 1:
        return [_inv_worker(t) for t in tasks]
    with mp.get_context("fork").Pool(workers) as pool:
        return pool.map(_inv_worker, tasks, chunksize=1)


def _brute_feasible(left: dict, past: set, last, first, remaining: int, free_bonus: int) -> bool:
    """Can `remaining` overs be bowled starting with `first`, never twice in a row, within base quotas
    `left` (overs left) plus at most `free_bonus` one-over bonuses, one per bowler not already `past` base?"""
    def go(lft, prev, rem, fb, used):
        if rem == 0:
            return True
        for b in lft:
            if b == prev:
                continue
            if lft[b] > 0:
                n = dict(lft)
                n[b] -= 1
                if go(n, b, rem - 1, fb, used):
                    return True
            elif fb > 0 and b not in used:
                if go(lft, b, rem - 1, fb - 1, used | {b}):
                    return True
        return False
    if first == last or first in past:
        return False
    if left[first] > 0:
        n = dict(left)
        n[first] -= 1
        return go(n, first, remaining - 1, free_bonus, frozenset(past))
    return free_bonus > 0 and go(left, first, remaining - 1, free_bonus - 1, frozenset(past | {first}))


class HelperTests(unittest.TestCase):
    def test_quota_matches_rules_reduced_quota(self):
        from beating.cricket.rules import reduced_quota
        for n in range(1, 51):
            q, extra, _ = reduced_quota("fifth_min2", n)
            self.assertEqual(sim.quota(n), (q, extra), n)
        self.assertEqual(sim.quota(17, "fifth"), (3, 2))

    def test_eligibility_matches_brute_force(self):
        rnd = random.Random(5)
        opts = ["a", "b", "c", "d", "e", "f"]
        checked = 0
        for _ in range(1500):
            n = rnd.choice([5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 20])
            base, bonus = sim.quota(n)
            k = rnd.randint(4, 6)
            op = opts[:k]
            done = rnd.randint(0, n - 1)
            overs, last, ok = {}, None, True
            seq = []
            for _ in range(done):        # a random legal history
                cand = [b for b in op if b != last and (overs.get(b, 0) < base or
                        (overs.get(b, 0) == base and sum(1 for x in overs.values() if x > base) < bonus))]
                if not cand:
                    ok = False
                    break
                b = rnd.choice(cand)
                overs[b] = overs.get(b, 0) + 1
                seq.append(b)
                last = b
            if not ok:
                continue
            free = bonus - sum(1 for x in overs.values() if x > base)
            left = {b: max(0, base - overs.get(b, 0)) for b in op}
            past = {b for b in op if overs.get(b, 0) > base}
            got = sim.eligible_bowlers(op, overs, last, n, done)
            for b in op:
                exp = _brute_feasible(left, past, last, b, n - done, free)
                self.assertEqual(b in got, exp, (n, overs, last, b, got))
            checked += 1
        self.assertGreater(checked, 1000)

    def test_revised_target_integer_rules(self):
        self.assertEqual(sim.revised_target(250, 1000, 1000, 250.0), 251)
        self.assertEqual(sim.revised_target(250, 1000, 852, 250.0), 250 * 852 // 1000 + 1)
        self.assertEqual(sim.revised_target(250, 800, 900, 260.0), 250 + math.floor(260.0 * 100 / 1000) + 1)

    def test_follow_on_threshold(self):
        t = P.engine_rules({"follow_on_lead_by_days": {"1": 75, "2": 100, "3": 150, "4": 150, "5": 200}},
                           "TEST")["follow_on_lead"]
        self.assertEqual([sim.follow_on_threshold(t, d) for d in (6, 5, 4, 3, 2, 1, 0)],
                         [200, 200, 150, 150, 100, 75, None])

    def test_conversions_match_vectorised_rng(self):
        st = rng.init_states(9, np.arange(4000), 1)
        u = rng.uniforms(st, 2)
        eta = np.random.default_rng(1).normal(size=(4000, 9))
        k = rng.categorical(u[:, 0], eta)
        self.assertEqual([sim.cat_eta(float(a), e.tolist()) for a, e in zip(u[:, 0], eta)], k.tolist())
        z1, z2 = rng.normal_pair(u[:, 0], u[:, 1])
        for i in range(0, 4000, 397):
            a, b = sim.normal_pair(float(u[i, 0]), float(u[i, 1]))
            self.assertAlmostEqual(a, z1[i], places=12)
            self.assertAlmostEqual(b, z2[i], places=12)
        s = rng.Stream(9, 17, 1)
        self.assertEqual(s.uniforms(2), u[17].tolist())
        self.assertEqual(sim.cat_w(0.999999, [1.0, 0.0, 0.0]), 0)
        self.assertEqual(sim.cat_w(0.49, [0.0, 2.0, 2.0]), 1)
        self.assertEqual(sim.cat_w(0.5, [0.0, 2.0, 2.0]), 2)

    def test_windows_scale_and_use_reduced_tables(self):
        pr = sim.Prepared(V.scen("T20"))
        self.assertEqual(pr.windows(120), ([(0, 36, 2), (36, 120, 5)], [(0, 36, "pp1")]))
        self.assertEqual(pr.windows(60)[1], [(0, 18, "pp1")])
        from beating.cricket import rules as R
        er = P.engine_rules(R.rules_for("intl_t20_m", "T20", "male", "2025-06-01"), "T20")
        pr = sim.Prepared(V.scen("T20", rules={"pp_reduced": er["pp_reduced"]}))
        self.assertEqual(pr.windows(102), ([(0, 30, 2), (30, 102, 5)], [(0, 30, "pp1")]))

    def test_engine_rules_from_timeline(self):
        from beating.cricket import rules as R
        t20 = P.engine_rules(R.rules_for("intl_t20_m", "T20", "male", "2025-06-01"), "T20")
        self.assertEqual((t20["max_balls"], t20["min_balls_for_result"], t20["tie_break"], t20["free_hit"]),
                         (120, 30, "so_repeat", "all_noballs"))
        test = P.engine_rules(R.rules_for("intl_test_m", "TEST", "male", "2025-06-01"), "TEST")
        self.assertEqual((test["test_days"], test["test_overs_per_day"], test["reviews_per_innings"],
                          test["max_balls"]), (5, 90, 3, None))
        self.assertEqual(sorted(P.RULE_KEYS), sorted(P.default_rules("ODI")))

    def test_affine_loglik_matches_finite_differences(self):
        stub = P.StubProvider()
        pr = sim.Prepared(V.scen("TEST"))
        views = []
        sim.Match(pr, 1, 3, views=views, stop_at=(1, 40)).play()
        v = dict(pr.view0)
        v.update(views[-1]["view"])
        nlat = len(pr.lat_m) + len(pr.lat_i)
        lat = [0.1 * (j - 2) for j in range(nlat)]
        idx = list(range(nlat))
        off = [0.0] * 9
        v["latent"] = tuple(lat)
        ll, g, h = stub.latent_loglik(v, 4, idx, off)
        eps = 1e-6
        for j in idx:
            lp = list(lat)
            lp[j] += eps
            v["latent"] = tuple(lp)
            ll2, g2, _ = stub.latent_loglik(v, 4, idx, off)
            self.assertAlmostEqual((ll2 - ll) / eps, g[j], places=4)
            for i in idx:
                self.assertAlmostEqual((g2[i] - g[i]) / eps, h[i][j], places=4)


class TransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {c["name"]: c for c in V.transition_cases()}

    def ok(self, name):
        e = self.cases[name]["expect"]
        self.assertNotIn("error", e, e.get("message"))
        return e

    def post(self, name):
        return self.ok(name)["state"]["cur"]

    def balls(self, name):
        return [ev for ev in self.ok(name)["events"] if ev["e"] == "ball"]

    def test_committed_vectors_match(self):
        text = V.dump(V.transition_cases())
        self.assertEqual((PARITY / "transitions.jsonl").read_text(), text)
        self.assertLess(len(text) + (PARITY / "trajectories.jsonl").stat().st_size, 3_200_000)

    def test_plan_cases_present(self):
        need = {"chase_one_needed_five_wide", "free_hit_wide_then_run_out", "wicket_last_ball_of_innings",
                "ten_wickets", "nine_wickets_one_absent", "run_out_one_completed", "caught_crossed_before_2022",
                "caught_after_2022", "quota_dead_end_filter", "dls_revision_mid_innings", "follow_on_enforced",
                "follow_on_innings_defeat", "fourth_innings_tie", "test_ball_80_new_ball", "super_over",
                "five_runs_rotate_strike", "four_byes_boundary", "wide_stumping", "noball_run_out",
                "free_hit_chain_two_wides", "over_end_after_last_ball_wicket", "declaration",
                "innings3_no_declaration_without_lead", "dls_par_tie"}
        self.assertFalse(need - set(self.cases))

    def test_chase_completion_crediting(self):
        e = self.ok("chase_one_needed_five_wide")
        self.assertEqual((e["result"]["result"], e["result"]["winner"]), ("win", 1))
        self.assertEqual(self.balls("chase_one_needed_five_wide")[0]["post"][0], 165)
        self.assertEqual(self.balls("chase_one_needed_wide_two_run")[0]["post"][0], 161)
        b = self.balls("chase_two_needed_three_run_wicket_void")[0]
        self.assertEqual(b["post"][:2], [161, 3])
        self.assertEqual(self.ok("chase_two_needed_three_run_wicket_void")["result"]["margin"], 7)

    def test_free_hit_rules(self):
        b = self.balls("free_hit_wide_then_run_out")
        self.assertEqual([x["post"][5] for x in b], [True, False, False])
        self.assertEqual(b[1]["post"][1], 2)
        for name in ("free_hit_wide_stumping_impossible", "free_hit_out_masked"):
            self.assertEqual(self.cases[name]["expect"]["error"], "ScriptError")
        b = self.balls("free_hit_chain_two_wides")
        self.assertEqual([x["post"][5] for x in b], [True, True, True, False, False])
        b = self.balls("front_foot_free_hit_draw")
        self.assertFalse(b[0]["post"][5])
        self.assertEqual(b[1]["kind"], "bowled")

    def test_wickets_and_all_out(self):
        e = self.ok("wicket_last_ball_of_innings")
        self.assertEqual(e["state"]["done"][0]["end"], "balls")
        self.assertEqual(e["state"]["cur"]["target"], 171)
        self.assertEqual(self.ok("ten_wickets")["state"]["done"][0]["end"], "all_out")
        d = self.ok("nine_wickets_one_absent")["state"]["done"][0]
        self.assertEqual((d["wkts"], d["end"]), (9, "all_out"))
        cur = self.post("over_end_after_last_ball_wicket")
        self.assertEqual((cur["striker"], cur["nonstriker"]), ("A4", "A5"))
        self.assertEqual(self.balls("over_end_after_last_ball_wicket")[0]["post"][3:5], ["A4", "A5"])


    def test_run_out_and_crossing(self):
        cur = self.post("run_out_one_completed")
        self.assertEqual((cur["runs"], cur["wkts"], cur["striker"], cur["nonstriker"]), (61, 3, "A4", "A5"))
        self.assertEqual(cur["batters"]["A3"]["out"], "run_out")
        self.assertEqual(cur["bowlers"]["B9"]["wkts"], 0)
        self.assertEqual(self.post("caught_crossed_before_2022")["striker"], "A4")
        self.assertEqual(self.post("caught_after_2022")["striker"], "A5")
        cur = self.post("noball_run_out")
        self.assertEqual((cur["runs"], cur["wkts"], cur["free_hit"], cur["legal_balls"]), (62, 3, True, 50))
        self.assertEqual(cur["batters"]["A3"]["balls"], 1)
        self.assertEqual(cur["batters"]["A4"]["out"], "run_out")
        cur = self.post("wide_run_out")
        self.assertEqual((cur["runs"], cur["striker"], cur["nonstriker"]), (62, "A5", "A3"))

    def test_strike_and_accounting(self):
        cur = self.post("five_runs_rotate_strike")
        self.assertEqual((cur["runs"], cur["striker"]), (65, "A4"))
        self.assertEqual(cur["batters"]["A3"]["fours"], 1)
        cur, base = self.post("four_byes_boundary"), self.cases["four_byes_boundary"]["state"]["cur"]
        self.assertEqual((cur["runs"], cur["striker"]), (64, "A3"))
        self.assertEqual(cur["bowlers"]["B9"]["runs"], base["bowlers"]["B9"]["runs"])
        self.assertEqual(self.post("three_byes_rotate")["striker"], "A4")
        cur = self.post("wide_stumping")
        self.assertEqual((cur["runs"], cur["wkts"], cur["legal_balls"], cur["striker"]), (61, 3, 50, "A5"))
        self.assertEqual(cur["bowlers"]["B9"]["wkts"], 1)
        cur = self.post("noball_four")
        self.assertEqual((cur["runs"], cur["free_hit"]), (65, True))
        self.assertEqual(cur["bowlers"]["B9"]["runs"], base["bowlers"]["B9"]["runs"] + 5)

    def test_quota_dead_end(self):
        ev = self.ok("quota_dead_end_filter")["events"][0]
        self.assertEqual(ev["elig"], ["B11"])
        self.assertIn("not eligible", self.cases["quota_dead_end_refused"]["expect"]["message"])

    def test_dls(self):
        e = self.ok("dls_revision_mid_innings")
        cur = e["state"]["cur"]
        self.assertEqual((cur["max_balls"], cur["target_timing"]), (240, "revised"))
        r = e["state"]["resources"]
        self.assertEqual(cur["target"], sim.revised_target(280, r[0], r[1], sim.Prepared(V.scen("ODI")).G))
        res = self.ok("dls_cut_par_result")["result"]
        self.assertEqual((res["result"], res["method"], res["winner"]), ("win", "par", 1))
        res = self.ok("dls_par_tie")["result"]
        self.assertEqual((res["result"], res["method"], res["super_overs"]), ("tie", "par", 0))
        st = self.ok("pre_match_reduction")["state"]
        self.assertEqual(st["lengths"], [90, 90])
        self.assertEqual(st["cur"]["max_balls"], 90)

    def test_test_structure(self):
        st = self.ok("follow_on_enforced")["state"]
        self.assertEqual((st["innings_team"], st["followed_on"], st["cur"]["team"]), ([0, 1, 1, 0], True, 1))
        self.assertEqual(self.ok("follow_on_declined")["state"]["innings_team"], [0, 1, 0, 1])
        res = self.ok("follow_on_innings_defeat")["result"]
        self.assertEqual((res["winner"], res["margin_kind"], res["margin"]), (0, "innings", 70))
        res = self.ok("innings3_all_out_behind")["result"]
        self.assertEqual((res["winner"], res["margin_kind"]), (1, "innings"))
        self.assertEqual(self.ok("innings3_all_out_level")["state"]["cur"]["target"], 1)
        ov = [x for x in self.ok("innings3_no_declaration_without_lead")["events"] if x["e"] == "over"]
        self.assertNotIn("declare", ov[0])
        self.assertIn("unused", self.cases["innings3_declaration_refused_without_lead"]["expect"]["message"])
        st = self.ok("declaration")["state"]
        self.assertEqual((st["done"][0]["end"], st["cur"]["number"], st["clock"]["changeovers"]), ("declared", 2, 1))
        self.assertEqual(self.ok("fourth_innings_tie")["result"]["result"], "tie")
        self.assertEqual(self.ok("test_clock_draw")["result"]["result"], "draw")
        cur = self.post("test_ball_80_new_ball")
        self.assertEqual((cur["ball_age_overs"], cur["second_new_ball"], cur["reviews"]), (0, True, [3, 3]))
        cur = self.post("test_ball_80_new_ball_declined")
        self.assertEqual((cur["ball_age_overs"], cur["second_new_ball"], cur["reviews"]), (80, False, [0, 1]))

    def test_tie_breaks(self):
        e = self.ok("super_over")
        self.assertEqual((e["result"]["method"], e["result"]["winner"], e["result"]["super_overs"]),
                         ("super_over", 1, 2))
        inns = [x for x in e["events"] if x["e"] == "innings"]
        self.assertEqual([x["team"] for x in inns], [1, 0, 0, 1])
        self.assertTrue(all(len(x["batters"]) == 3 for x in inns))
        self.assertEqual(self.ok("tie_no_tie_break")["result"]["result"], "tie")
        self.assertEqual(self.ok("tie_bowl_out_coin")["result"]["method"], "coin")

    def test_drs_layer(self):
        cur = self.post("drs_bat_overturned")
        self.assertEqual((cur["wkts"], cur["reviews"], cur["runs"]), (2, [2, 2], 60))
        cur = self.post("drs_bat_umpires_call")
        self.assertEqual((cur["wkts"], cur["reviews"], cur["fail_reviews"]), (3, [2, 2], [0, 0]))
        cur = self.post("drs_bat_failed")
        self.assertEqual((cur["wkts"], cur["reviews"], cur["fail_reviews"]), (3, [1, 2], [1, 0]))
        cur = self.post("drs_umpires_call_lost_pre_2017")
        self.assertEqual((cur["reviews"], cur["fail_reviews"]), ([0, 1], [0, 0]))
        cur = self.post("drs_field_success")
        self.assertEqual((cur["wkts"], cur["batters"]["A3"]["out"]), (3, "lbw"))
        cur = self.post("drs_field_speculative")
        self.assertEqual((cur["reviews"], cur["fail_reviews"]), ([2, 1], [0, 1]))
        cur = self.post("drs_disabled_missed_out_stands")
        self.assertEqual(cur["wkts"], 3)

    def test_script_chaining_equals_one_script(self):
        c = self.cases["free_hit_chain_two_wides"]
        sc, st, script = c["scenario"], c["state"], c["script"]
        a = sim.apply_script(copy.deepcopy(sc), script[:3], copy.deepcopy(st))
        b = sim.apply_script(copy.deepcopy(sc), [{"e": "resume"}] + script[3:], json.loads(json.dumps(a["state"])))
        self.assertEqual(b["state"], c["expect"]["state"])

    def test_scripts_are_strict(self):
        c = self.cases["caught_after_2022"]
        bad = copy.deepcopy(c["script"])
        bad[1]["runs"] = 3
        with self.assertRaises(sim.ScriptError):
            sim.apply_script(c["scenario"], bad, copy.deepcopy(c["state"]))


class InvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fams = [("T20", "male"), ("ODI", "female"), ("TEST", "male")]
        chunks = {"T20": 2, "ODI": 3, "TEST": 8}
        tasks = []
        for fam, g in fams:
            k = chunks[fam]
            edges = [N_INV * j // k for j in range(k + 1)]
            tasks += [(fam, g, a, b) for a, b in zip(edges, edges[1:])]
        tasks.sort(key=lambda t: t[0] != "TEST")
        cls.errs, cls.acc = {}, {}
        for key, errs, acc in _pool_map(tasks + [("T20", "female", 0, 150), ("TEST", "female", 0, 60)]):
            cls.errs.setdefault(key, []).extend(errs)
            cls.acc[key] = acc if key not in cls.acc else cls.acc[key].merge(acc)
        cls.out = {k: sim.summarize(a) for k, a in cls.acc.items()}

    def test_no_rule_violations(self):
        for key, errs in self.errs.items():
            self.assertEqual(errs, [], key)

    def test_counts_and_probabilities(self):
        for key, out in self.out.items():
            n = out["n"]
            self.assertEqual(n, self.acc[key].n)
            tot = sum(x["p"] for x in out["p_win"]) + out["p_tie"]["p"] + out["p_draw"]["p"] + out["p_no_result"]["p"]
            self.assertAlmostEqual(tot, 1.0, places=12)
            for x in out["p_win"]:
                self.assertAlmostEqual(x["se"], math.sqrt(x["p"] * (1 - x["p"]) / n), places=12)
            self.assertGreaterEqual(out["p_tie_before"]["p"], out["p_tie"]["p"])
        self.assertEqual(self.out["T20", "male"]["n"], N_INV)
        self.assertEqual(self.out["TEST", "male"]["n"], N_INV)

    def test_stub_is_realistic(self):
        t20, odi, test = self.out["T20", "male"], self.out["ODI", "female"], self.out["TEST", "male"]
        self.assertTrue(140 < t20["innings"]["1"]["runs_mean"] < 180, t20["innings"]["1"]["runs_mean"])
        self.assertTrue(4.5 < t20["innings"]["1"]["wkts_mean"] < 8)
        self.assertTrue(220 < odi["innings"]["1"]["runs_mean"] < 300, odi["innings"]["1"]["runs_mean"])
        self.assertTrue(280 < test["innings"]["1"]["runs_mean"] < 400, test["innings"]["1"]["runs_mean"])
        self.assertTrue(0.07 < test["p_draw"]["p"] < 0.25, test["p_draw"]["p"])
        self.assertGreater(t20["p_no_result"]["p"] + odi["p_no_result"]["p"], 0)
        self.assertGreater(sum(v for k, v in t20["methods"].items() if k in ("dls", "par")), 0)
        self.assertGreater(t20["super_overs"].get("1", 0), 0)
        self.assertEqual(self.out["TEST", "female"]["innings"]["1"]["n"], 60)
        for out in (t20, odi, test):
            self.assertGreater(out["drs"]["bat_reviews"], 0)
            self.assertGreater(out["dismissals"]["run_out"]["share"], 0)
            w = out["worm"]["1"]
            self.assertTrue(all(r["q10"] <= r["q50"] <= r["q90"] for r in w))

    def test_player_outputs(self):
        out = self.out["T20", "male"]
        a1, b11 = out["players"]["A1"], out["players"]["B11"]
        self.assertGreater(a1["bat_balls"], 0)
        self.assertTrue(0 < a1["p50"]["p"] < 1 and a1["p100"]["p"] <= a1["p50"]["p"])
        self.assertAlmostEqual(b11["economy"], 6 * b11["bowl_runs"] / b11["bowl_balls"])
        self.assertTrue(0 <= b11["p3w"]["p"] < 1)
        self.assertGreater(out["players"]["A2"]["bat_runs"], out["players"]["B2"]["bat_runs"] - 1.5)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_same_sim_and_independent_of_range(self):
        pr = sim.Prepared(inv_scenario("ODI"))
        r1 = sim.Match(pr, 7, 11).play().record()
        r2 = sim.Match(sim.Prepared(inv_scenario("ODI")), 7, 11).play().record()
        self.assertEqual(r1, r2)
        self.assertNotEqual(r1, sim.Match(pr, 7, 12).play().record())
        acc = sim.simulate(pr, range(5, 9), 11)
        self.assertEqual(dict(acc.codes)[7], r1["code"])

    def test_merge_equals_full_run(self):
        pr = sim.Prepared(V.scen("T20", toss=None, weather={"rain_risk": 0.3}))
        full = sim.simulate(pr, range(1000), 3)
        half = sim.simulate(pr, range(500), 3).merge(sim.simulate(pr, range(500, 1000), 3))
        self.assertEqual(sim.summarize(full), sim.summarize(half))

    def test_committed_trajectories_match(self):
        self.assertEqual((PARITY / "trajectories.jsonl").read_text(), V.dump(V.trajectories()))

    def test_random_number_consumption_is_fixed(self):
        pr = sim.Prepared(V.scen("T20", toss=None))
        m = sim.Match(pr, 4, 9).play()
        balls = m.deliveries
        ref = rng.Stream(9, 4, 0)
        ref.uniforms(12 * balls)
        self.assertEqual(m.s_ball.s, ref.s)
        ref = rng.Stream(9, 4, 4)
        ref.uniforms(4 * len(pr.slots))
        self.assertEqual(m.s_player.s, ref.s)
        ref = rng.Stream(9, 4, 3)
        ref.uniforms(64)
        self.assertEqual(m.s_match.s, ref.s)


class InPlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = V.scen("T20", toss={"winner": 0, "decision": "bat"})
        pr = sim.Prepared(cls.sc)
        views = []
        m = sim.Match(pr, 5, 99, views=views, stop_at=(1, 75)).play()
        cls.state = m.to_state()
        cls.views = views

    def test_state_invariants_checked(self):
        pr = sim.Prepared(self.sc)
        self.assertEqual(sim.check_state(self.state, pr), [])
        bad = []
        s = copy.deepcopy(self.state)
        s["cur"]["wkts"] += 1
        bad.append(s)
        s = copy.deepcopy(self.state)
        b = next(iter(s["cur"]["bowlers"]))
        s["cur"]["bowlers"][b]["balls"] += 1
        bad.append(s)
        s = copy.deepcopy(self.state)
        s["cur"]["batters"][s["cur"]["striker"]]["out"] = "bowled"
        bad.append(s)
        s = copy.deepcopy(self.state)
        s["cur"]["legal_balls"] = s["cur"]["max_balls"] = 120
        bad.append(s)
        s = copy.deepcopy(self.state)
        s["cur"]["target"] = s["cur"]["runs"]
        bad.append(s)
        for s in bad:
            self.assertNotEqual(sim.check_state(s, pr), [])
            with self.assertRaises(ValueError):
                sim.Match(pr, 0, 1, state=s).play()

    def test_impute_minimal_state(self):
        sc = V.scen("ODI")
        st = sim.impute_state({"cur": {"number": 1, "team": 0, "runs": 140, "wkts": 3, "legal_balls": 157}}, sc)
        pr = sim.Prepared(sc)
        self.assertEqual(sim.check_state(st, pr), [])
        cur = st["cur"]
        self.assertEqual((cur["striker"], cur["nonstriker"]), ("A4", "A5"))
        self.assertEqual(cur["batters"]["A4"], {"runs": 0, "balls": 0, "arrival": 4, "out": None})
        ob = cur["over_bowlers"] + [cur["bowler"]]
        self.assertTrue(all(a != b for a, b in zip(ob, ob[1:])))
        self.assertLessEqual(max(Counter(ob).values()), 10)
        self.assertEqual(sum(b["balls"] for b in cur["bowlers"].values()), 157)
        out = sim.run({**sc, "state": st}, n_sims=30, seed=1)
        self.assertEqual(out["innings"]["1"]["n"], 30)
        self.assertTrue(all(x >= 140 for x, _ in out["innings"]["1"]["runs_hist"]))

    def test_in_play_run_continues_from_state(self):
        st = copy.deepcopy(self.state)
        out = sim.run({**self.sc, "state": st}, n_sims=40, seed=2)
        cur = st["cur"]
        self.assertTrue(all(x >= cur["runs"] for x, _ in out["innings"]["1"]["runs_hist"]))
        self.assertGreaterEqual(out["innings"]["1"]["balls_mean"], cur["legal_balls"])
        tot = sum(x["p"] for x in out["p_win"]) + out["p_tie"]["p"] + out["p_no_result"]["p"]
        self.assertAlmostEqual(tot, 1.0)

    def test_latent_posterior_newton(self):
        st = copy.deepcopy(self.state)
        st["balls"] = json.loads(json.dumps(self.views))
        pr = sim.Prepared({**self.sc, "state": st})
        post = pr.posterior()
        nm = len(pr.lat_m)
        self.assertEqual(post["free"], list(range(nm + len(pr.lat_i))))
        # the mode is a fixed point: an 11th Newton step moves it by < 1e-9
        st2 = {k: v for k, v in pr.sc.items()}
        base = dict(pr.view0)
        base["toss_winner"] = 0
        mu = [float(pr.sc["pitch"].get(s["pitch"], 0.0) or 0.0) * s["sd"] for s in pr.lat_m] + [0.0] * len(pr.lat_i)
        sd = [s["sd"] for s in pr.lat_m] + [s["sd"] for s in pr.lat_i]
        recs = [{"inn": r["inn"], "cls": r["cls"], "view": dict(r["view"], striker_form=(0.0, 0.0),
                 nonstriker_form=(0.0, 0.0), bowler_form=(0.0, 0.0))} for r in st2["state"]["balls"]]
        m11, _ = sim.latent_posterior(pr.P, base, recs, 1, post["free"], mu, sd, [0.0] * len(sd), nm, iters=11)
        self.assertLess(max(abs(a - b) for a, b in zip(m11, post["mode"])), 1e-9)
        L = post["chol"]
        prec_diag = [sum(L[i][k] ** 2 for k in range(i + 1)) for i in range(len(L))]
        self.assertTrue(all(p > 1 / s ** 2 for p, s in zip(prec_diag, sd)))
        # draws centre on the mode
        draws = [sim.Match(pr, i, 5, state=pr.sc["state"]) for i in range(300)]
        for d in draws:
            d._resume(pr.sc["state"])
        mean0 = sum(d.lat_m[0] for d in draws) / len(draws)
        self.assertLess(abs(mean0 - post["mode"][0]), 4 * 0.22 / math.sqrt(len(draws)) + 0.01)
        known = sim.Prepared({**self.sc, "state": st, "pitch": {"known": True, "runs_sd": 1.0}})
        self.assertEqual(known.posterior()["free"], [nm, nm + 1])
        d = sim.Match(known, 0, 5, state=known.sc["state"])
        d._resume(known.sc["state"])
        self.assertEqual(d.lat_m[0], 1.0 * known.lat_m[0]["sd"])

    def test_resume_then_script_equals_direct_script(self):
        c = {x["name"]: x for x in V.transition_cases()}["dls_revision_mid_innings"]
        out = sim.apply_script(c["scenario"], c["script"], copy.deepcopy(c["state"]))
        st = out["state"]
        self.assertEqual(sim.check_state(st, sim.Prepared(c["scenario"])), [])
        self.assertEqual(st["cur"]["target_timing"], "revised")


class OutputTests(unittest.TestCase):
    def test_sensitivity_uses_common_random_numbers(self):
        sc = V.scen("T20", toss=None, player_form={"A1": {"bat_runs_sd": 2.5}, "A3": {"bat_runs_sd": 2.5}})
        sens = sim.sensitivity(sc, sims=range(300), seed=4,
                               factors={"null": {"neutral": False}, "forms": {"player_form": {}}})
        self.assertEqual(sens["null"]["p_win0"], {"effect": 0.0, "se": 0.0})
        eff = sens["forms"]["p_win0"]
        self.assertGreater(eff["effect"], 0)
        p = 0.5
        self.assertLess(eff["se"], math.sqrt(2 * p * (1 - p) / 300))
        self.assertIn("home", sim.default_factors(P.validate_scenario(sc)))


    def test_run_outputs_shape(self):
        out = sim.run(V.scen("T20", toss=None, sensitivity=True), n_sims=60, seed=8)
        for k in ("p_win", "p_tie", "p_tie_before", "p_draw", "p_no_result", "innings", "runs_by_over", "worm",
                  "margins", "players", "dismissals", "drs", "sensitivity", "part_timers_added"):
            self.assertIn(k, out)
        self.assertEqual(len(out["worm"]["1"]), 20)
        self.assertIn("missed_outs_lower_bound", out["drs"])
        self.assertEqual(out["part_timers_added"], [[], []])

    def test_part_timers_appended_when_options_infeasible(self):
        sc = V.scen("T20", teams=[V.team("A", True, bowlers=["A11", "A10", "A9"]), V.team("B")])
        pr = sim.Prepared(sc)
        self.assertEqual(pr.part_timer_report[0], ["A1", "A2"])
        acc = sim.simulate(pr, range(30), 1)
        self.assertEqual(acc.stats["bowler_fallback"], 0)


if __name__ == "__main__":
    unittest.main()
