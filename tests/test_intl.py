"""Test and ODI models: bowling plans, schedule mapping, the random-walk fitter and the simulator engine."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from models.intl.config import FORMATS, REGION
from models.intl.flow import decl_features
from models.intl.schedule import lineup, local_date, map_venue, norm_country, norm_team, venue_index
from models.intl.team import integer_plan, share_plan

ROOT = Path(__file__).resolve().parents[1]

try:
    import scipy.sparse as sp
    from models.intl.fit import KM, Design, RWFitter, rw_pairs
except ImportError:  # numba is not in the locked test requirements
    RWFitter = None


class BowlingPlans(unittest.TestCase):
    def test_odi_plan_fills_the_phases_within_the_cap(self):
        q = {"a": [3, 5, 2], "b": [4, 3, 3], "c": [0, 9, 1], "d": [2, 6, 1], "e": [1, 5, 2], "f": [0, 2, 0]}
        plan = integer_plan(q)
        tot = [sum(p[k] for p in plan) for k in ("pp", "mid", "death")]
        self.assertEqual(tot, [10, 30, 10])
        self.assertTrue(all(p["pp"] + p["mid"] + p["death"] <= 10 for p in plan))
        self.assertTrue(all(p["pp"] <= 5 and p["death"] <= 5 for p in plan))

    def test_odi_plan_tops_up_a_short_attack(self):
        plan = integer_plan({k: [1, 3, 1] for k in "abcde"})   # usual workloads sum to 25 overs only
        self.assertEqual(sum(p["pp"] + p["mid"] + p["death"] for p in plan), 50)

    def test_test_shares_sum_to_100_per_phase(self):
        plan = share_plan({"a": [0.3, 0.2, 0.1], "b": [0.25, 0.25, 0.2], "c": [0.05, 0.3, 0.4], "d": [0.001, 0.002, 0.003]})
        self.assertEqual([p["id"] for p in plan], ["a", "b", "c"])   # a share under 1% is dropped
        for k in ("nb", "mid", "old"):
            self.assertAlmostEqual(sum(p[k] for p in plan), 100.0, delta=0.2)


class ScheduleMapping(unittest.TestCase):
    def test_countries_and_sides(self):
        self.assertEqual(norm_country("Barbados"), "West Indies")
        self.assertEqual(norm_country("Wales"), "England")
        self.assertEqual(norm_team("U.S.A."), "United States of America")
        self.assertEqual(REGION["India"], "asia")

    def test_start_is_dated_on_the_grounds_own_calendar(self):
        self.assertEqual(local_date("2026-11-26T22:00Z", "New Zealand", "x"), "2026-11-27")   # 11:00 next day in Christchurch
        self.assertEqual(local_date("2027-03-01T14:00Z", "West Indies", "x"), "2027-03-01")
        self.assertEqual(local_date(None, "India", "2027-01-05"), "2027-01-05")

    def test_ground_falls_back_to_the_city(self):
        venues = [{"venue": "lords", "city": "London", "country": "England", "matches": 40},
                  {"venue": "kennington oval", "city": "London", "country": "England", "matches": 30}]
        by_id, by_city = venue_index(venues)
        self.assertEqual(map_venue({"venue_name": "Lord's, London", "city": "London"}, by_id, by_city, "England"), "lords")
        self.assertEqual(map_venue({"venue_name": "Some New Ground", "city": "London"}, by_id, by_city, "England"), "lords")
        self.assertIsNone(map_venue({"venue_name": "Some New Ground", "city": "Leeds"}, by_id, by_city, "England"))

    def test_lineup_prefers_the_announced_xi_and_keeps_unrated_players(self):
        fmt = FORMATS["test"]
        base = {"order": [f"p{k}" for k in range(11)], "plan": [{"id": "p9", "nb": 50, "mid": 50, "old": 50}, {"id": "p10", "nb": 50, "mid": 50, "old": 50}],
                "date": "2026-01-01", "country": "India"}
        team = {"name": "India", "default": base, "by_region": {"asia": base},
                "squad": [{"id": f"p{k}", "usage": [0.25, 0.25, 0.25] if k >= 7 else None} for k in range(11)]}
        self.assertIn("most recent XI", lineup(fmt, team, "India", None, {})["source"])
        ann = [{"cricinfo": str(100 + k), "name": f"N{k}", "pos": "Bowler" if k >= 8 else "Batter"} for k in range(11)]
        ids = {str(100 + k): f"p{k}" for k in range(10)}   # the eleventh has no rating
        lu = lineup(fmt, team, "India", ann, ids)
        self.assertEqual(lu["source"], "announced XI")
        self.assertEqual(lu["order"][10], "espn:110")
        self.assertEqual(lu["roles"]["espn:110"], {"bat": "tail", "bowl": "pace_front"})
        self.assertIn("espn:110", [p["id"] for p in lu["plan"]])

    def test_declaration_features_match_the_engine_layout(self):
        for inn in (1, 2, 3):
            self.assertEqual(len(decl_features(inn, 420.0, 180.0, 5, 110.0, 200.0)), 6)
        self.assertEqual(decl_features(3, 0.0, 300.0, 4, 60.0, 50.0)[5], 6.0)   # runs an over the target would ask


@unittest.skipIf(RWFitter is None, "numba / scipy not installed")
class RandomWalkFitter(unittest.TestCase):
    def toy(self):
        D = Design()
        D.add("io", ["a", "b"], "l0")
        D.add("gs", ["2024", "2025", "2026"], "gs")
        D.add("gs_ph", [f"{y}_p{p}" for y in ("2024", "2025", "2026") for p in (0, 2)], "gs")
        D.add("gs_spin", ["2024s", "2025s", "2026s"], "gs")
        D.add("cs", ["Aus|2024/25", "Aus|2025/26", "Eng|2025", "Eng|2026"], "cs")
        D.add("cs_spin", ["a", "b", "c", "d"], "cs")
        rng = np.random.default_rng(0)
        n = 300
        cols = np.column_stack([rng.integers(0, 2, n), 2 + rng.integers(0, 3, n), 14 + rng.integers(0, 4, n)]).ravel()
        X = sp.csr_matrix((np.ones(3 * n, np.float32), (np.repeat(np.arange(n), 3), cols)), shape=(n, D.p))
        lam = {"l0": 1.0, "gs": 4.0, "cs": 5.0, "rw": 7.0, "rw_gs": 3.0}
        return D, RWFitter(X, rng.integers(0, KM + 1, n), np.ones(n), D, lam)

    def test_pairs_stay_within_a_country(self):
        D, _ = self.toy()
        prev, cur, key = rw_pairs(D.blocks)
        o = D.blocks["cs"][0]
        cs = [(int(a - o), int(b - o)) for a, b, k in zip(prev, cur, key) if k == "cs" and o <= b < o + 4]
        self.assertEqual(cs, [(0, 1), (2, 3)])

    def test_gradient_matches_finite_differences(self):
        _, F = self.toy()
        th = np.random.default_rng(1).normal(size=F.p * KM) * 0.3
        g = F.fg(th)[1].copy()
        for j in (3 * KM + 1, 6 * KM + 2, 12 * KM, 15 * KM + 4, 19 * KM + 7):
            e = np.zeros_like(th)
            e[j] = 1e-5
            num = (F.fg(th + e)[0] - F.fg(th - e)[0]) / 2e-5
            self.assertAlmostEqual(num, g[j], delta=1e-5 * max(1.0, abs(num)))

    def test_first_season_keeps_its_ridge_and_later_ones_do_not(self):
        D, F = self.toy()
        o = D.blocks["cs"][0]
        self.assertEqual(F.pen[o, 0], 5.0)
        self.assertEqual(F.pen[o + 1, 0], 0.0)
        self.assertEqual(F.pen[o + 2, 0], 5.0)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class Engine(unittest.TestCase):
    def run_fmt(self, key, n):
        ex = ROOT / "docs" / "models" / key / "data"
        if not (ex / "sim_params.json").exists() or not (ex / "teams.json").exists():
            self.skipTest(f"{key} exports not built")
        teams = json.loads((ex / "teams.json").read_text())["teams"]
        spec = lambda t: {"name": t["name"], "order": t["default"]["order"], "plan": t["default"]["plan"]}
        job = {"id": "x", "A": spec(teams[0]), "B": spec(teams[1]), "n": n, "seed": 5, "opts": {"country": "_default"},
               "hists": ["A.t1", "res"]}
        out = []
        with tempfile.TemporaryDirectory() as td:
            for rep in range(2):
                jp, op = Path(td) / "j.json", Path(td) / f"o{rep}.json"
                jp.write_text(json.dumps({"params": str(ex / "sim_params.json"), "jobs": [job]}))
                subprocess.run(["node", str(ROOT / "models" / "intl" / "sim_cli.js"), str(jp), str(op)], check=True)
                out.append(json.loads(op.read_text())["results"][0])
        return out

    def check(self, key, n):
        a, b = self.run_fmt(key, n)
        s = a["summary"]
        self.assertEqual(a["hists"], b["hists"])   # same seed, same counts
        self.assertEqual(sum(a["hists"]["res"].values()), n)
        self.assertAlmostEqual(s["p_A"] + s["p_B"] + s["p_draw"] + s["p_tie"], 1.0, places=9)
        self.assertEqual(sum(a["hists"]["A.t1"]), n)
        return s

    def neutral_sits_between_home_and_away(self, key, n, tol_runs):
        """A neutral ground must not be a different game from a hosted one (it once was for Tests, when separate
        batting-home and bowling-home terms absorbed a shared level that a neutral simulation then dropped)."""
        ex = ROOT / "docs" / "models" / key / "data"
        if not (ex / "sim_params.json").exists() or not (ex / "teams.json").exists():
            self.skipTest(f"{key} exports not built")
        teams = json.loads((ex / "teams.json").read_text())["teams"]
        spec = lambda t: {"name": t["name"], "order": t["default"]["order"], "plan": t["default"]["plan"]}
        jobs = [{"id": str(h), "A": spec(teams[0]), "B": spec(teams[1]), "n": n, "seed": 11,
                 "opts": {"country": "_default", "home": h, "batFirst": "A"}} for h in ("A", None, "B")]
        with tempfile.TemporaryDirectory() as td:
            jp, op = Path(td) / "j.json", Path(td) / "o.json"
            jp.write_text(json.dumps({"params": str(ex / "sim_params.json"), "jobs": jobs}))
            subprocess.run(["node", str(ROOT / "models" / "intl" / "sim_cli.js"), str(jp), str(op)], check=True)
            res = {r["id"]: r["summary"] for r in json.loads(op.read_text())["results"]}
        tot = {h: res[h]["A"]["t1_mean"] for h in res}
        win = {h: res[h]["p_A"] for h in res}
        self.assertGreater(win["A"], win["B"])   # home advantage has the right sign
        self.assertTrue(min(tot["A"], tot["B"]) - tol_runs <= tot["None"] <= max(tot["A"], tot["B"]) + tol_runs, tot)
        self.assertTrue(win["B"] - 0.04 <= win["None"] <= win["A"] + 0.04, win)

    def test_odi_neutral_ground(self):
        self.neutral_sits_between_home_and_away("odi", 4000, 8)

    def test_test_neutral_ground(self):
        self.neutral_sits_between_home_and_away("test", 1500, 15)

    def test_odi_match(self):
        s = self.check("odi", 400)
        self.assertEqual(s["p_draw"], 0.0)
        self.assertTrue(120 < s["A"]["t1_mean"] < 420)
        self.assertAlmostEqual(sum(d.get("p_top", 0) for d in s["A"]["players"].values()), 1.0, places=6)   # top-batter shares

    def test_test_match(self):
        s = self.check("test", 200)
        self.assertGreater(s["p_draw"], 0.0)
        self.assertTrue(150 < s["A"]["t1_mean"] < 600)
        self.assertLessEqual(s["overs_mean"], 451)


if __name__ == "__main__":
    unittest.main()
