import json
import os
import unittest

import numpy as np
import pandas as pd

from beating.cricket import features as FX, glm

SPEC = FX.load_spec()
LV = FX._cat_levels(SPEC)
NUMS = ["innings", "max_balls", "balls_remaining", "wkts", "runs_required", "target_known", "striker_balls",
        "striker_arrival", "nonstriker_arrival", "field_restr", "striker_overseas", "bowler_overseas", "elevation",
        "ball_age_overs", "second_new_ball", "est_day", "est_overs_into_day", "exp_overs_left", "lead", "striker_exp",
        "bowler_exp", "striker_role_pos", "free_hit", "free_hit_p", "drs", "bowl_end_umpire_p", "temp", "rh", "cloud",
        "precip", "dew_dep", "depth", "outcome_class", "onfield_class"]
CATS = ["fam", "dtype", "target_timing", "bat_home", "bowl_home", "start_slot", "bowl_class", "bowl_type", "bat_hand",
        "region", "ball_brand", "wk", "onfield_wk"]
IDENT = np.array([f"p{i}" for i in range(20)], dtype=object)

# a fake resource table: Z = P * G / 1000 = 50 runs everywhere except wickets 10
RES = {"tables": {t: {g: {"N": n, "G": 100.0, "P": [[500] * 10 + [0] for _ in range(n + 1)]}
                      for g in ("male", "female")} for t, n in (("T20", 120), ("ODI", 300))}}


def row(**kw):
    r = dict(match=0, innings=1, fam="T20", dtype="legal", max_balls=120, balls_remaining=120, wkts=0,
             runs_required=None, target_known=0, target_timing=None, striker_balls=0, striker_arrival=1,
             nonstriker_arrival=2, field_restr=2, bat_home="home", bowl_home="away", start_slot="night",
             bowl_class="pace", bowl_type="pace_fast", bat_hand="R", striker_overseas=None, bowler_overseas=None,
             region="subcontinent", ball_brand=None, elevation=10.0, ball_age_overs=None, second_new_ball=None,
             est_day=None, est_overs_into_day=None, exp_overs_left=None, lead=0, striker_exp=0, bowler_exp=0,
             striker_role_pos=1.0, free_hit=0, free_hit_p=0.0, drs=1, bowl_end_umpire_p=0.5, temp=25.0, rh=60.0,
             cloud=4.0, precip=0.0, dew_dep=5.0, depth=5, outcome_class=0, onfield_class=0, wk=None, onfield_wk=None,
             batter=1, bowler=2)
    r.update(kw)
    return r


def make_slice(fit_fam, rows, matches):
    """Synthetic field-ready slice: rows reference matches by position."""
    b = {}
    for k in NUMS:
        b[k] = np.array([np.nan if r[k] is None else float(r[k]) for r in rows], dtype=np.float32)
    for k in CATS:
        b[k] = np.array([LV[k].index(r[k]) if r[k] is not None else -1 for r in rows], dtype=np.int16)
    b["mi"] = np.array([r["match"] for r in rows], dtype=np.int32)
    m = pd.DataFrame(matches)
    b["match_id"] = m.match_id.to_numpy(np.int32)[b["mi"]]
    b["batter_id"] = np.array([r["batter"] for r in rows], dtype=np.int32)
    b["bowler_id"] = np.array([r["bowler"] for r in rows], dtype=np.int32)
    b["innings"] = b["innings"].astype(np.int8)
    return FX.Slice(fit_fam, "male", b, m, IDENT)


def match(mid, date, comp="c1", season=None, venue="v1", u1=10, u2=11, days=1, dates=None, awarded=False, fam="T20"):
    return dict(match_id=mid, start_date=date, dates_played=json.dumps(dates or [date]), fam=fam, venue_id=venue,
                competition_id=comp, season_key=season or f"{comp}:{date[:4]}", umpire1_id=u1, umpire2_id=u2,
                awarded=awarded, scheduled_days=days)


def fields_of(sl, i, extra=None):
    """Scalar canonical fields of synthetic row i (what view_fields would give)."""
    b, m = sl.b, sl.m.iloc[int(sl.b["mi"][i])]

    def num(k):
        x = float(b[k][i])
        return None if x != x else (int(x) if x.is_integer() else x)

    def cat(k):
        c = int(b[k][i])
        return LV[k][c] if c >= 0 else None
    fam, tk = cat("fam"), num("target_known") == 1
    rr = num("runs_required") if tk else None
    mb, br = num("max_balls"), num("balls_remaining")
    f = {"fam": fam, "innings": num("innings"), "super_over": 0, "max_balls": mb, "balls_remaining": br,
         "elapsed": None if mb is None or br is None else mb - br, "wkts": num("wkts"), "runs_required": rr,
         "chase_ok": fam != "TEST" and rr is not None and num("innings") == 2 and cat("target_timing") in ("original", "pre_inn2"),
         "striker_balls": num("striker_balls"), "field_restr": num("field_restr"), "bat_home": cat("bat_home"),
         "bowl_home": cat("bowl_home"), "start_slot": cat("start_slot"), "bowl_class": cat("bowl_class") or "unknown",
         "bowl_type": cat("bowl_type"), "bat_hand": cat("bat_hand") or "U",
         "striker_overseas": None if num("striker_overseas") is None else bool(num("striker_overseas")),
         "bowler_overseas": None if num("bowler_overseas") is None else bool(num("bowler_overseas")),
         "region": cat("region"), "ball_brand": cat("ball_brand"), "elevation": num("elevation"),
         "ball_age_overs": num("ball_age_overs"),
         "second_new_ball": None if num("second_new_ball") is None else bool(num("second_new_ball")),
         "est_day": num("est_day"), "scheduled_days": int(m.scheduled_days),
         "overs_into_day": None if num("est_overs_into_day") is None else int(np.floor(num("est_overs_into_day"))),
         "exp_overs_left": None if num("exp_overs_left") is None else float(b["exp_overs_left"][i]),
         "lead": num("lead"), "striker_exp": num("striker_exp"), "bowler_exp": num("bowler_exp"),
         "striker_role_pos": num("striker_role_pos"), "depth": num("depth"),
         "free_hit": None if num("free_hit") is None else bool(num("free_hit")),
         "free_hit_p": float(b["free_hit_p"][i]), "is_noball": cat("dtype") == "noball",
         "drs": None if num("drs") is None else bool(num("drs")), "year": int(m.start_date[:4]),
         "temp": num("temp"), "rh": num("rh"), "cloud": num("cloud"), "precip": num("precip"), "dew_dep": num("dew_dep"),
         "_st": IDENT[b["batter_id"][i]], "_bw": IDENT[b["bowler_id"][i]], "_venue": m.venue_id,
         "_competition": m.competition_id, "_season": m.season_key, "_gender": "male", "_ub": None,
         "_ums": [IDENT[m.umpire1_id], IDENT[m.umpire2_id]], "_ump_p": float(b["bowl_end_umpire_p"][i])}
    for k in ("temp", "rh", "cloud", "dew_dep", "elevation", "free_hit_p"):
        if f[k] is not None:
            f[k] = float(b[k][i])
    f.update(extra or {})
    return f


def t20_slice():
    ms = [match(100, "2021-05-01", season="c1:2021"), match(101, "2022-05-01", season="c1:2022", u2=12),
          match(102, "2022-06-01", comp="c2", venue="v2"), match(103, "2022-12-31", dates=["2022-12-31", "2023-01-01"]),
          match(104, "2022-07-01", awarded=True), match(105, "1990-01-01", season="c1:1990")]
    rows = []
    for el in (0, 11, 12, 35, 36, 59, 60, 89, 90, 107, 108, 119):
        rows.append(row(balls_remaining=120 - el, striker_balls=el % 20, wkts=el % 11))
    rows += [row(max_balls=42, balls_remaining=42 - 4), row(max_balls=42, balls_remaining=42 - 5),
             row(fam="HUNDRED", max_balls=100, balls_remaining=70, match=1)]
    # chases against Z = 50 runs: R = rr / 50
    for rr in (39, 40, 47, 48, 85, 84):
        rows.append(row(innings=2, target_known=1, target_timing="original", runs_required=rr, balls_remaining=60, match=1))
    rows += [row(innings=2, target_known=1, target_timing="unknown", runs_required=40, match=1),
             row(innings=2, target_known=1, target_timing="pre_inn2", runs_required=5, wkts=10, match=1),
             row(dtype="noball", outcome_class=1, onfield_class=1, match=2),
             row(free_hit=None, free_hit_p=0.4, match=2), row(free_hit=1, free_hit_p=1.0, outcome_class=4, onfield_class=4, match=2),
             row(dtype="wide", outcome_class=None, onfield_class=None, match=2),
             row(bowl_class="spin", bowl_type="left_orth", bat_hand="L", striker_overseas=1, bowler_overseas=0, match=2),
             row(bowl_class="unknown", bowl_type=None, bat_hand=None, field_restr=None, bowl_end_umpire_p=1.0, match=2),
             row(outcome_class=6, onfield_class=0, wk="caught", onfield_wk=None, drs=1, match=1),
             row(outcome_class=0, onfield_class=6, wk=None, onfield_wk="lbw", drs=1, match=1),
             row(outcome_class=6, onfield_class=0, wk="caught", onfield_wk=None, drs=0, match=1),
             row(outcome_class=6, onfield_class=6, wk="bowled", onfield_wk="bowled", drs=None, temp=None, match=0),
             row(match=3), row(match=4), row(match=5), row(striker_role_pos=2.5, striker_exp=30, bowler_exp=1001, match=0),
             row(striker_role_pos=8.5, striker_exp=31, bowler_exp=1000, start_slot="unknown", innings=2, match=0)]
    return make_slice("T20", rows, ms)


def test_slice():
    ms = [match(200, "2020-03-01", comp="t", season="t:2020", days=5, fam="TEST",
                dates=[f"2020-03-0{i}" for i in range(1, 6)]),
          match(201, "2021-03-01", comp="t", season="t:2021", days=4, fam="TEST")]
    base = dict(fam="TEST", max_balls=None, balls_remaining=None, field_restr=None, ball_brand="dukes",
                region="sena_eng", ball_age_overs=0, second_new_ball=0, est_day=1, est_overs_into_day=0.0,
                exp_overs_left=300.0)
    rows = [row(**{**base, **kw}) for kw in (
        {}, {"ball_age_overs": 9, "est_overs_into_day": 5.99}, {"ball_age_overs": 10, "est_overs_into_day": 6.0},
        {"ball_age_overs": 79, "second_new_ball": 1, "est_day": 5}, {"est_day": 7},
        {"innings": 3, "lead": -1, "exp_overs_left": 60.0}, {"innings": 3, "lead": 0, "exp_overs_left": 60.5},
        {"innings": 3, "lead": 300, "exp_overs_left": 200.00001}, {"innings": 4, "runs_required": 250, "target_known": 1,
                                                                    "target_timing": "original", "exp_overs_left": 100.0},
        {"innings": 4, "runs_required": 249, "target_known": 1, "target_timing": "original", "exp_overs_left": 100.0},
        {"innings": 4, "runs_required": 10, "target_known": 1, "target_timing": "original", "exp_overs_left": 0.0},
        {"bowl_class": "spin", "ball_brand": None, "est_day": 3, "match": 1},
        {"ball_age_overs": 15, "est_day": 4, "match": 1}, {"ball_age_overs": 16, "match": 1})]
    return make_slice("TEST", rows, ms)


class FactorParityTest(unittest.TestCase):
    """Vectorized and scalar factor / weight / group evaluation agree on hand-made edge cases."""

    def check(self, sl):
        F = FX.VecFields(sl, SPEC)
        ids = FX.build_ids(F)
        lk = {"ids": {k: dict(v["index"]) for k, v in ids.items()}}
        for name in SPEC["factors"]:
            if SPEC["factors"][name]["type"] == "id" and name in ("match", "match_innings", "umpire"):
                continue
            vec = FX.factor_vec(SPEC, name, F, ids, RES)
            for i in range(sl.n):
                f = fields_of(sl, i)
                self.assertEqual(int(vec[i]), FX.factor_scalar(SPEC, name, f, sl.fit_fam, "male", lk, RES), (name, i))
        for name in ("is_spin", "is_pace", "spin_sign", "is_death", "newball", "first10", "wear", "free_hit_p"):
            vec = FX.weight_vec(SPEC, name, F)
            for i in range(sl.n):
                self.assertEqual(float(vec[i]), FX.weight_scalar(SPEC, name, fields_of(sl, i), sl.fit_fam), (name, i))
        for model in SPEC["models"]:
            stats = FX.dense_stats(SPEC, model, F)
            groups = {g["name"]: (g, FX.group_levels(SPEC, g, F, ids, RES)) for g in FX.model_groups(SPEC, model, sl.fit_fam)}
            dv = FX.dense_vec(SPEC, model, F, stats) if FX.dense_columns(SPEC, model, sl.fit_fam) else None
            masks = FX.mask_vec(SPEC, model, F)
            for i in range(sl.n):
                s = FX.levels_from_fields(fields_of(sl, i), SPEC, {**lk, "standardize": stats}, model, RES)
                for name, (g, lv) in groups.items():
                    i1 = int(lv["index"][i])
                    if g.get("latent"):
                        i1 = 0 if i1 >= 0 else -1
                    got = s["groups"][name]
                    self.assertEqual(got[0], i1, (model, name, i))
                    if i1 >= 0 and lv["weight"] is not None:
                        self.assertEqual(got[1], float(lv["weight"][i]), (model, name, i))
                    if lv["index2"] is not None:
                        self.assertEqual(got[2], int(lv["index2"][i]), (model, name, i))
                if dv is not None:
                    self.assertEqual(s["dense"], dv[i].tolist(), (model, i))
                self.assertEqual(s["mask"], [k for hit, k in masks if hit[i]], (model, i))
        return F, ids

    def test_t20(self):
        F, ids = self.check(t20_slice())
        ph6 = FX.factor_vec(SPEC, "phase6", F).tolist()
        self.assertEqual(ph6[:12], [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
        self.assertEqual(ph6[12:15], [0, 1, 2])                       # reduced 42-ball innings; Hundred 30/100
        self.assertEqual(FX.factor_vec(SPEC, "phase3", F).tolist()[:12], [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2])
        rr7 = FX.factor_vec(SPEC, "rr7", F, ids, RES).tolist()
        self.assertEqual(rr7[15:21], [0, 1, 1, 2, 6, 5])             # R = 0.78, 0.80, 0.94, 0.96, 1.70, 1.68
        self.assertEqual(rr7[21:23], [1, 6])                          # unknown timing still has a ratio; P = 0 -> top
        chase = SPEC["models"]["outcome"]["groups"][[g["name"] for g in SPEC["models"]["outcome"]["groups"]].index("o_chase")]
        self.assertEqual(int(FX.group_levels(SPEC, chase, F, ids, RES)["index"][21]), -1)
        self.assertEqual(FX.factor_vec(SPEC, "fam", F).tolist()[14], 1)  # HUNDRED context level
        self.assertEqual(FX.factor_vec(SPEC, "exp6_bat", F).tolist()[-2:], [1, 2])
        self.assertEqual(FX.factor_vec(SPEC, "exp6_bowl", F).tolist()[-2:], [5, 4])
        self.assertEqual(FX.factor_vec(SPEC, "role6", F).tolist()[-2:], [1, 5])

    def test_test_family(self):
        F, ids = self.check(test_slice())
        self.assertEqual(FX.factor_vec(SPEC, "ball_age4", F).tolist()[:4], [0, 0, 1, 3])
        self.assertEqual(FX.factor_vec(SPEC, "oid4", F).tolist()[:3], [0, 0, 1])
        self.assertEqual(FX.factor_vec(SPEC, "lead5", F).tolist()[5:8], [0, 1, 4])
        self.assertEqual(FX.factor_vec(SPEC, "eol4", F).tolist()[5:8], [0, 1, 3])
        self.assertEqual(FX.factor_vec(SPEC, "rpo5", F).tolist()[8:11], [1, 0, 4])
        self.assertEqual(FX.factor_vec(SPEC, "phase6", F).tolist()[0], 0)
        wear = FX.weight_vec(SPEC, "wear", F).tolist()
        self.assertEqual(wear[:5], [0.0, 0.0, 0.0, 1.0, 1.0])         # est_day 7 of 5 capped
        self.assertAlmostEqual(wear[11], 2 / 3)
        self.assertEqual(FX.weight_vec(SPEC, "newball", F).tolist()[-2:], [1.0, 0.0])
        self.assertEqual(FX.factor_vec(SPEC, "brand4", F).tolist()[11], 3)


class ScalarSemanticsTest(unittest.TestCase):
    def view(self, **kw):
        v = {"fam": "T20", "gender": "male", "competition_id": "c1", "date": "2024-04-02", "venue_id": "v1",
             "start_slot": "night", "weather": None, "umpires": ["u1", "u2"], "drs_enabled": True, "scheduled_days": None,
             "innings": 1, "super_over": 0, "so_innings": 0, "bat_home_status": "home", "bowl_home_status": "away",
             "target_timing": None, "legal_balls": 0, "max_balls": 120, "balls_remaining": 120, "wkts": 0,
             "runs_required": None, "striker": "a", "nonstriker": "b", "bowler": "w", "striker_balls": 0,
             "striker_arrival": 1, "nonstriker_arrival": 2, "free_hit": False, "field_restr": 2, "ball_age_overs": 0,
             "second_new_ball": False, "est_day": None, "overs_into_day": None, "exp_overs_left": None, "lead": 0,
             "bowl_end_umpire": None, "to_come": ("c", "d", "e", "f", "g", "h"), "dtype": "legal"}
        v.update(kw)
        return v

    def lookups(self):
        return {"players": {"w": {"bowl_class": "spin", "bowl_type": "off_spin"}, "a": {"bat_hand": "L"}},
                "player_ctx": {"a": {"exp_bat": 50, "role_pos": None}, "c": {"role_pos": 3.0}, "d": {"role_pos": 9.0},
                               "e": {"role_pos": None}, "f": {"role_pos": None}},
                "venues": {"v1": {"region": "subcontinent", "country": "India", "elevation_m": 900.0}},
                "competitions": {"c1": {"club": True}},
                "seasons": {"c1": [["2023-03-31", "c1:2023"], ["2024-03-22", "c1:2024"]]},
                "ids": {"umpire": {"u1": 0, "u2": 1}, "season": {"c1:2023": 0, "c1:2024": 1},
                        "era": {"T20|2021": 0, "T20|2023": 1}, "batter": {"a": 0}}}

    def test_view_semantics(self):
        lk = self.lookups()
        f = FX.view_fields(self.view(), lk)
        self.assertEqual(f["depth"], 4)  # c 3.0; d 9.0 no; e, f, g fallback ranks 5, 6, 7; h rank 8 no
        self.assertEqual(f["striker_role_pos"], 1)      # no history -> arrival
        self.assertEqual(f["_season"], "c1:2024")
        self.assertEqual(FX.season_from_view(self.view(date="2024-03-21"), lk), "c1:2023")
        self.assertEqual(FX.season_from_view(self.view(season_key="x:1"), lk), "x:1")
        self.assertEqual(FX._id_scalar("era", f, lk), 1)   # 2024 not listed -> latest earlier year
        self.assertEqual(f["bowl_class"], "spin")
        lv = FX.levels_from_view(self.view(), SPEC, lk, "outcome", RES)["groups"]
        self.assertEqual(lv["o_umpire"], (0, 0.5, 1, 0.5))
        lv = FX.levels_from_view(self.view(bowl_end_umpire="u2"), SPEC, lk, "outcome", RES)["groups"]
        self.assertEqual(lv["o_umpire"], (1, 1.0, -1, 0.0))
        self.assertEqual(lv["m_spin"], (0, 1.0, -1, 0.0))
        self.assertEqual(lv["o_bowl_newball"][0], -1)    # unknown bowler id
        self.assertEqual(lv["o_bat"], (0, 1.0, -1, 0.0))
        so = FX.levels_from_view(self.view(super_over=1, so_innings=2, max_balls=6, balls_remaining=6), SPEC, lk,
                                 "outcome", RES)["groups"]
        self.assertEqual(so["o_fam_phase6"][0], 5)       # super over: last phase
        self.assertEqual(so["o_fam_innings"][0], 1)
        self.assertEqual(so["o_bat_death"][1], 1.0)
        self.assertEqual(FX.levels_from_view(self.view(free_hit=True), SPEC, lk, "outcome", RES)["mask"], [6])
        self.assertEqual(FX.levels_from_view(self.view(dtype="noball"), SPEC, lk, "outcome", RES)["mask"], [6])
        self.assertEqual(FX.levels_from_view(self.view(), SPEC, lk, "outcome", RES)["mask"], [])
        allm = FX.levels_from_view(self.view(), SPEC, {**lk, "models": {"wk": {"ids": {}}}}, res=RES)
        self.assertEqual(sorted(allm), ["dtype", "outcome", "wk"])
        self.assertEqual(allm["outcome"]["groups"]["o_bat"][0], 0)
        self.assertEqual(allm["wk"]["groups"]["w_batter"][0], -1)  # per-model ids override
        chase = FX.levels_from_view(self.view(innings=2, runs_required=40, target_timing="revised", balls_remaining=60),
                                    SPEC, lk, "outcome", RES)["groups"]["o_chase"]
        self.assertEqual(chase[0], (0 * 7 + 1) * 3 + 1)  # T20, R = 0.8, middle overs
        dew = FX.levels_from_view(self.view(innings=2, weather={"dew_depression_evening": 2.0}), SPEC,
                                  {**lk, "standardize": {"dew_dep": [5.0, 2.0]}}, "outcome", RES)["dense"]
        self.assertEqual(dew[-2:], [1.5, 0.0])

    def test_spec_consistency(self):
        k1 = {m: len(SPEC["classes"][SPEC["models"][m]["classes"]]) - 1 for m in SPEC["models"]}
        for model, mspec in SPEC["models"].items():
            names = [g["name"] for g in mspec["groups"]]
            self.assertEqual(len(names), len(set(names)))
            for g in mspec["groups"]:
                for f in g["factors"]:
                    self.assertIn(f, SPEC["factors"])
                b = FX.basis_matrix(SPEC, model, g.get("basis"))
                self.assertTrue(b is None or b.shape[1] == k1[model])
                if g.get("parent"):
                    self.assertIn(g["parent"], names)
                if g.get("weight"):
                    self.assertIn(g["weight"], SPEC["weights"])
        np.testing.assert_allclose(SPEC["directions"]["scoring"], [x / 6.5 for x in (0, 1, 2, 3, 4, 6, 0, 0, 1)], rtol=0, atol=1e-15)
        b = FX.basis_matrix(SPEC, "outcome", {"exclude": [7]})
        self.assertEqual(b.shape, (7, 8))
        self.assertEqual(b[:, 6].sum(), 0)


class DesignTest(unittest.TestCase):
    def test_build_design(self):
        sl = t20_slice()
        d = FX.build_design(sl, "outcome", "2023-01-01", 3.0, SPEC, RES)
        rows = d.meta["row_index"]
        mi = sl.b["mi"][rows]
        self.assertFalse(np.isin(mi, [3, 4]).any())        # spans the cutoff; awarded
        self.assertFalse(np.isin(mi, [5]).any())           # 33 years old: weight < 0.02
        self.assertFalse((sl.b["dtype"][rows] == 1).any())  # wides leave the outcome model
        age = (np.datetime64("2023-01-01") - np.datetime64("2022-05-01")).astype(float)
        np.testing.assert_allclose(d.weights[mi == 1], 0.5 ** (age / (365.25 * 3)))
        y = dict(zip(rows.tolist(), d.y.tolist()))
        n = sl.n
        self.assertEqual([y[n - 9], y[n - 8], y[n - 7], y[n - 6]], [0, 6, 6, 6])   # on-field where drs is true
        mask = dict(d.masks and [(6, d.masks[0][0])])[6]
        self.assertEqual(int(mask.sum()), 2)               # the no-ball and the certain free hit
        g = {x.name: x for x in d.groups}
        self.assertEqual(g["o_season"].labels, ["c1:2021", "c1:2022", "c2:2022"])
        self.assertEqual(g["o_season"].rw_prev.tolist(), [-1, 0, -1])
        self.assertEqual(g["o_season_phase"].rw_prev.tolist()[:6], [-1, -1, -1, 0, 1, 2])
        self.assertEqual(g["o_era"].labels, ["HUNDRED|2022", "T20|2021", "T20|2022"])
        self.assertEqual(g["o_bowl"].basis.shape, (7, 8))
        self.assertEqual(g["m_runs"].basis.shape, (1, 8))
        self.assertEqual(g["o_umpire"].labels, ["p10", "p11", "p12"])
        self.assertEqual(d.meta["groups"]["o_venue"]["parent"], "o_region")
        self.assertNotIn("o_test_ball", g)
        self.assertEqual(d.dense.shape[1], 12)
        wk = FX.build_design(sl, "wk", "2023-01-01", 3.0, SPEC, RES)
        self.assertEqual(sorted(wk.y.tolist()), [0, 1, 2])  # caught (recorded, drs false), bowled, lbw (on-field)

    def test_eta_matches_glm(self):
        """eta_from_levels on scalar levels equals glm's linear predictor on the design rows."""
        sl = t20_slice()
        for model in SPEC["models"]:
            d = FX.build_design(sl, model, "2023-01-01", 50.0, SPEC, RES)
            prep = glm._Prepared(d)
            rng = np.random.default_rng(3)
            theta = rng.normal(0, 0.3, prep.layout.size)
            params = prep.layout.unpack(theta)
            eta = np.vstack([prep.eta(params, c, prep.stack_full(params)) for c in prep.chunks])
            lk = FX.model_lookups(d.meta)
            for j, i in enumerate(d.meta["row_index"]):
                f = fields_of(sl, int(i))
                lv = FX.levels_from_fields(f, SPEC, lk, model, RES)
                latent = {x.name: params[x.name][x.index[j]] for x in d.groups
                          if d.meta["groups"][x.name]["latent"] and x.index[j] >= 0}
                got = FX.eta_from_levels(lv, params, SPEC, model, latent)
                np.testing.assert_allclose(got[1:], eta[j], rtol=0, atol=1e-6)  # dense stored as float32
                self.assertEqual(got[0], 0.0)


@unittest.skipIf(os.environ.get("CRICKET_SKIP_REAL_DATA") or not FX.BALLS_PATH.exists(), "real ball table not available")
class RealParityTest(unittest.TestCase):
    """Vectorized and scalar paths agree exactly on >= 5,000 real balls across every fitting family."""

    def test_real_balls(self):
        base = FX.static_lookups(SPEC)
        res = FX.load_resource()
        m = pd.read_parquet(FX.MATCHES_PATH, columns=["match_id", "fit_fam", "gender"])
        rng = np.random.default_rng(2026)
        total = 0
        for fit_fam in SPEC["fit_families"]:
            for gender in ("male", "female"):
                ids = m[(m.fit_fam == fit_fam) & (m.gender == gender)].match_id.to_numpy()
                pick = rng.choice(ids, size=min(len(ids), 8), replace=False)
                sl = FX.load_slice(fit_fam, gender, pick, full=True, spec=SPEC)
                rows = np.sort(rng.choice(sl.n, size=min(sl.n, 900), replace=False))
                rep = FX.parity(sl, rows, SPEC, base=base, res=res)
                self.assertEqual(rep["mismatches"], 0, (fit_fam, gender, rep["examples"][:3]))
                self.assertGreater(rep["checks"], 30 * len(rows))
                total += len(rows)
                if fit_fam == "TEST" and gender == "male":
                    v, lk = FX.views_from_rows(sl, rows[:1], base, SPEC)[0]
                    lk = {**lk, "players": {**lk["players"], v["bowler"]: {"bowl_class": "none"}}}
                    F = FX.VecFields(sl, SPEC, rows[:1])
                    lkm = {"ids": {k: dict(x["index"]) for k, x in FX.build_ids(F).items()}}
                    a = FX.levels_from_view(v, SPEC, {**lk, **lkm}, "outcome", res)["groups"]
                    self.assertEqual(a["o_bat_spin"][0], -1)   # perturbed lookup changes the levels
        self.assertGreaterEqual(total, 5000)


if __name__ == "__main__":
    unittest.main()
