"""IPL model: random-walk season penalty."""
import unittest

import numpy as np

try:
    import scipy.sparse as sp
    from models.ipl.fit import KM, Design, Fitter, rw_pairs
except ImportError:  # numba is not in the locked test requirements
    Fitter = None

SEASONS = ["IPL|2024", "IPL|2025", "IPL|2026", "PSL|2025", "PSL|2026"]
LAM = {"l0": 1.0, "cs": 5.0, "cs_rw": 5.0}


def toy(empty=False):
    D = Design()
    D.add("io", ["a", "b"], "l0")
    D.add("cs", SEASONS, "cs_rw")
    D.add("cs_ph", [f"{c}_p{p}" for c in SEASONS for p in (0, 2)], "cs_rw")
    rng = np.random.default_rng(0)
    n = 400
    rows = np.repeat(np.arange(n), 3)
    cs = rng.integers(0, 5, n)
    cols = np.column_stack([rng.integers(0, 2, n), 2 + cs, 7 + 2 * cs + rng.integers(0, 2, n)]).ravel()
    vals = np.zeros(3 * n, np.float32) if empty else np.ones(3 * n, np.float32)
    X = sp.csr_matrix((vals, (rows, cols)), shape=(n, D.p))
    return D, Fitter(X, rng.integers(0, KM + 1, n), np.ones(n), D, LAM)


@unittest.skipIf(Fitter is None, "numba / scipy not installed")
class RandomWalkSeasonPenalty(unittest.TestCase):
    def test_pairs_stay_within_a_league(self):
        D, _ = toy()
        prev, cur = rw_pairs(D.blocks)
        o, op = D.blocks["cs"][0], D.blocks["cs_ph"][0]
        self.assertEqual(sorted(zip((prev[:3] - o).tolist(), (cur[:3] - o).tolist())), [(0, 1), (1, 2), (3, 4)])
        self.assertEqual(len(prev), 9)
        self.assertEqual(set((cur[3:] - op).tolist()), {2, 3, 4, 5, 8, 9})

    def test_gradient_matches_finite_differences(self):
        _, F = toy()
        th = np.random.default_rng(1).normal(size=F.p * KM) * 0.3
        g = F.fg(th)[1].copy()
        for j in (2 * KM + 1, 4 * KM + 3, 9 * KM + 5, 15 * KM):
            e = np.zeros_like(th)
            e[j] = 1e-5
            num = (F.fg(th + e)[0] - F.fg(th - e)[0]) / 2e-5
            self.assertAlmostEqual(num, g[j], delta=1e-5 * max(1.0, abs(num)))

    def test_level_shift_costs_only_the_first_season(self):
        D, F = toy(empty=True)  # no data term: the loss differences below are the penalty alone
        o = D.blocks["cs"][0]
        self.assertEqual(F.pen[o, 0], 5.0)       # first season of a league keeps the ridge
        self.assertEqual(F.pen[o + 1, 0], 0.0)   # later seasons: difference penalty only
        zero = F.fg(np.zeros(F.p * KM))[0]
        flat = np.zeros((F.p, KM))
        flat[o:o + 3] = 0.7                      # IPL shifted in every season, no season-to-season change
        self.assertAlmostEqual(F.fg(flat.ravel())[0] - zero, 0.5 * 5.0 * 0.7 ** 2 * KM, places=6)
        step = np.zeros((F.p, KM))
        step[o + 2] = 0.7                        # only IPL 2026 moves: one difference is penalised
        self.assertAlmostEqual(F.fg(step.ravel())[0] - zero, 0.5 * 5.0 * 0.7 ** 2 * KM, places=6)


if __name__ == "__main__":
    unittest.main()
