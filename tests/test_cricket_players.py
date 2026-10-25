from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from beating.cricket import players as P


class StyleTest(unittest.TestCase):
    def test_bowling_styles(self):
        cases = {
            "Right arm Offbreak": ("off_spin", "none", "R"), "Right-arm offbreak": ("off_spin", "none", "R"),
            "Right arm Fast": ("pace_fast", "none", "R"), "Right-arm fast-medium": ("pace_fast", "none", "R"),
            "Left arm Medium fast": ("pace_fast", "none", "L"), "Right-arm medium-fast": ("pace_fast", "none", "R"),
            "Right arm Medium": ("pace_medium", "none", "R"), "Right arm Slow medium": ("pace_medium", "none", "R"),
            "Left-arm medium": ("pace_medium", "none", "L"), "Legbreak": ("leg_spin", "none", "R"),
            "Legbreak Googly": ("leg_spin", "none", "R"), "Slow Left arm Orthodox": ("left_orth", "none", "L"),
            "Slow left-arm orthodox": ("left_orth", "none", "L"), "Left arm Wrist spin": ("left_wrist", "none", "L"),
            "Left-arm wrist-spin": ("left_wrist", "none", "L"), "Left arm chinaman": ("left_wrist", "none", "L"),
            "Right arm Medium, Right arm Offbreak": ("pace_medium", "off_spin", "R"),
            "Left arm Medium, Slow Left arm Orthodox": ("pace_medium", "left_orth", "L"),
            "Slow Left arm Orthodox, Slow Left arm Orthodox": ("left_orth", "none", "L"),
            "Right arm Medium, Right arm Slow": ("pace_medium", "unknown", "R"),
            "Right arm Slow, Right arm Offbreak": ("off_spin", "none", "R"),
            "Right arm Bowler": ("unknown", "none", "R"), "Left arm Bowler": ("unknown", "none", "L"),
            "Right-arm bowler": ("unknown", "none", "R"), "Right arm Slow": ("unknown", "none", "R"),
            "(Unknown Arm) Slow": ("unknown", "none", "U"), "Slow": ("unknown", "none", "U"),
            None: ("none", "none", "U"),
        }
        for s, (t, t2, arm) in cases.items():
            r = P.parse_bowling(s)
            self.assertEqual((r["bowl_type"], r["bowl_type_2"], r["bowl_arm"]), (t, t2, arm), s)
            self.assertEqual(r["vague"], t == "unknown", s)

    def test_hand(self):
        self.assertEqual([P.parse_hand(s) for s in ("Right hand Bat", "Left-hand bat", "Right-arm fast", None)],
                         ["R", "L", "U", "U"])
        self.assertTrue(P.looks_like_bowling("Left-arm wrist-spin"))
        self.assertFalse(P.looks_like_bowling("Right-hand bat"))


def meta_row(cid, csid, bat="Right hand Bat", bowl=None, role=None):
    return dict(cricinfo_id=cid, cricsheet_id=csid, unique_name=csid, full_name=csid, name=csid, country="X",
                dob=None, batting_style=bat, bowling_style=bowl, birthplace=None, playing_role=role)


class MetaTest(unittest.TestCase):
    def test_dedupe_prefers_key_cricinfo(self):
        meta = pd.DataFrame([meta_row("1", "a", bowl="Right arm Medium"), meta_row("2", "a", bowl="Legbreak"),
                             meta_row("3", "b"), meta_row("4", "b", bowl="Right arm Fast")])
        people = pd.DataFrame(dict(identifier=["a", "b"], key_cricinfo=["2", "9"], key_cricinfo_2=[None, "3"],
                                   key_cricinfo_3=[None, None]))
        m, log = P.dedupe_meta(meta, people)
        self.assertEqual(dict(zip(m.cricsheet_id, m.cricinfo_id)), {"a": "2", "b": "3"})
        self.assertEqual(len(log), 2)

    def test_style_table_shift_and_vague(self):
        pi = pd.DataFrame(dict(person_id=[0, 1, 2, 3], identifier=["p0", "p1", "p2", "p3"], name=list("abcd"),
                               unique_name=list("abcd"), key_cricinfo=None, n_matches_player=1, first_date=None,
                               last_date=None))
        meta = pd.DataFrame([meta_row("1", "p0", bat="Left-arm wrist-spin"), meta_row("2", "p1", bowl="Right arm Slow"),
                             meta_row("3", "p2", bat="Left hand Bat", bowl="Right-arm offbreak", role="Wicketkeeper Batter")])
        st = P.style_table(pi, meta)
        self.assertEqual(st.bowl_type.tolist(), ["left_wrist", "unknown", "off_spin", "none"])
        self.assertEqual(st.bat_hand.tolist(), ["U", "R", "L", "U"])
        self.assertEqual(st.bowl_class.tolist(), ["spin", "unknown", "spin", "none"])
        self.assertEqual(st.style_note.tolist(), ["bowling_style_in_batting_column", "vague_style", "", ""])
        self.assertEqual(st.meta_source.tolist(), ["cricinfo_meta", "none", "cricinfo_meta", "none"])
        self.assertEqual(st.has_meta.tolist(), [True, True, True, False])


def cat(values, cats):
    return pd.Categorical(values, categories=cats)


def synth(n_known=60, n_unknown=8, balls_each=90, seed=0):
    """Players: 0 = keeper (bats only), 1 = left-handed batter, then bowlers. Spinners have stumpings and fewer
    no-balls and bowl in the middle; pacemen bowl the powerplay and death with no-balls."""
    rng = np.random.default_rng(seed)
    nb = n_known + n_unknown
    types = [P.TYPES[i % 6] if i % 6 != 5 else "off_spin" for i in range(nb)]
    rows = []
    for j in range(nb):
        pid, spin = j + 2, P.CLASS_OF[types[j]] == "spin"
        for k in range(balls_each):
            mid = 1000 + (j * balls_each + k) // 120
            over = int(rng.integers(6, 16)) if spin else int(rng.choice([0, 1, 2, 3, 16, 17, 18, 19]))
            r = rng.random()
            dtype = "noball" if (not spin and r < 0.06) else "wide" if r < 0.09 else "legal"
            kind, fl = None, None
            if dtype == "legal" and rng.random() < 0.06:
                kind = "stumped" if (spin and rng.random() < 0.3) else "caught"
                fl = json.dumps([0]) if kind == "stumped" or rng.random() < 0.3 else json.dumps([pid])
                kind = "caught and bowled" if fl == json.dumps([pid]) else kind
            rows.append(dict(match_id=mid, innings=1, over=over, batter_id=int(rng.integers(0, 2)), bowler_id=pid,
                             runs_batter=0 if kind else int(rng.choice([0, 1, 4])), non_boundary=False, byes=0,
                             legbyes=int(not spin and rng.random() < 0.05), penalty=0,
                             wides=int(dtype == "wide"), noballs=int(dtype == "noball"), dtype=dtype,
                             wicket_kind_raw=kind, fielders=fl, fam="T20", gender="male", ball_age_overs=None,
                             bowler_spell_overs=int(rng.integers(0, 4 if spin else 2))))
    b = pd.DataFrame(rows)
    b["runs_total"] = b.runs_batter + b.wides + b.noballs + b.legbyes
    b["dtype"] = cat(b.dtype, ["legal", "wide", "noball"])
    b["wicket_kind_raw"] = cat(b.wicket_kind_raw, ["caught", "caught and bowled", "bowled", "lbw", "stumped", "run out"])
    b["fam"], b["gender"] = cat(b.fam, P.FAMS), cat(b.gender, ["male", "female"])
    b["bowler_id"] = b.bowler_id.astype("Int32")
    b["ball_age_overs"] = pd.array([None] * len(b), dtype="Int16")
    ids = [f"id{i:03d}" for i in range(nb + 2)]
    pi = pd.DataFrame(dict(person_id=range(nb + 2), identifier=ids, name=ids, unique_name=ids, key_cricinfo=None,
                           n_matches_player=1, first_date="2020-01-01", last_date="2020-02-01"))
    style = {"pace_fast": "Right arm Fast", "pace_medium": "Right arm Medium", "off_spin": "Right arm Offbreak",
             "leg_spin": "Legbreak", "left_orth": "Slow Left arm Orthodox"}
    meta = [meta_row("0", ids[0], role="Wicketkeeper"), meta_row("x", ids[1], bat="Left hand Bat")]
    meta += [meta_row(str(10 + j), ids[j + 2], bowl=style[types[j]] if j < n_known else None) for j in range(nb)]
    meta = pd.DataFrame(meta)
    people = pd.DataFrame(dict(identifier=ids, key_cricinfo=None, key_cricinfo_2=None, key_cricinfo_3=None))
    matches = pd.DataFrame(dict(match_id=sorted(b.match_id.unique()), start_date="2020-01-01", team_type="club"))
    return b, matches, pi, meta, people, types


class UsageInferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b, cls.m, cls.pi, cls.meta, cls.people, cls.types = synth()

    def test_usage_counts(self):
        st = P.style_table(self.pi, self.meta)
        u = P.usage(self.b, self.m, st.bat_hand.to_numpy(str), st.role.fillna("").str.contains("keeper").to_numpy())
        bw = self.b[self.b.bowler_id == 5]
        self.assertEqual(u.n_del[5], len(bw))
        self.assertEqual(u.n_legal[5], (bw.dtype == "legal").sum())
        self.assertEqual(u.n_nb[5], (bw.dtype == "noball").sum())
        self.assertEqual(u.n_pp[5], (bw.over < 6).sum())
        self.assertEqual(u.n_death[5], (bw.over >= 16).sum())
        self.assertEqual(u.n_stumpings_fielded[0], (self.b.wicket_kind_raw == "stumped").sum())
        self.assertEqual(u.w_keeper_caught[5], ((bw.wicket_kind_raw == "caught") & (bw.fielders == "[0]")).sum())
        self.assertEqual(u.w_caught[5], bw.wicket_kind_raw.isin(["caught", "caught and bowled"]).sum())
        self.assertEqual(u.n_faced.sum(), (self.b.dtype == "legal").sum())
        lhb = (bw.dtype == "legal") & (bw.batter_id == 1)
        self.assertEqual(u.n_lhb[5], lhb.sum())
        self.assertEqual(int(u.balls_since_2019.sum()), len(self.b))

    def test_softmax_and_cv(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(300, 3))
        y = (X[:, 0] > 0).astype(int) + 2 * (X[:, 1] > 0.5)
        cv = P.cross_validate(X, y, 4, P.fold_of(range(300)), lambdas=(1e-3, 1.0))
        self.assertEqual(cv["lam"], 1e-3)
        self.assertGreater((cv["oof"].argmax(axis=1) == y).mean(), 0.85)
        np.testing.assert_allclose(cv["oof"].sum(axis=1), 1.0)

    def test_arm_constraint(self):
        lik = P.arm_likelihood(np.array([0] * 12 + [2] * 20 + [4] * 20), np.array(["R"] * 10 + ["L"] * 22 + ["L"] * 20))
        lik["off_spin"] = {"R": 0.99, "L": 0.01}
        Q = P.apply_arm(np.full((2, 6), 1 / 6), np.array(["R", "U"]), lik)
        self.assertLess(Q[0, 4], 0.05)
        self.assertGreater(Q[0, 2], Q[0, 4])
        np.testing.assert_allclose(Q[1], 1 / 6)

    def test_build_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            p, rep = P.build(meta_path=self.meta, out=d / "players.parquet", csv=d / "types.csv",
                             report=d / "rep.json", balls=self.b, matches=self.m, people_index=self.pi,
                             people=self.people)
            self.assertTrue((d / "players.parquet").exists() and (d / "types.csv").exists())
            back = json.loads((d / "rep.json").read_text())
            self.assertEqual(back["rows"]["players"], len(self.pi))
        self.assertEqual(p.person_id.tolist(), list(range(len(self.pi))))
        self.assertTrue(p.keeper[0])
        self.assertEqual(p.keeper_source[0], "role+stumping")
        unk = p.iloc[2 + 60:]
        self.assertTrue((unk.meta_source == "inferred").all())
        truth = np.array([P.CLASS_OF[t] for t in self.types[60:]])
        self.assertGreaterEqual((unk.bowl_class.to_numpy() == truth).mean(), 0.75)
        self.assertTrue(((unk.infer_confidence >= 0.5) & (unk.infer_confidence <= 1)).all())
        self.assertTrue(unk.bowl_type.isin(P.TYPES + ("unknown",)).all())
        self.assertGreater(rep["inference"]["cv_no_arm"]["class_accuracy"], 0.8)
        self.assertAlmostEqual(rep["coverage"]["overall"]["cls_meta"] + rep["coverage"]["overall"]["cls_inferred"], 1.0, places=3)
        self.assertEqual(p.bat_hand[1], "L")
        self.assertTrue(set(p.bowl_class) <= {"pace", "spin", "none", "unknown"})


if __name__ == "__main__":
    unittest.main()
