"""IPL trend layer: the filter's arithmetic on small synthetic series."""
import unittest

import numpy as np
import pandas as pd

try:
    from models.ipl.trend import N_BANDS, frozen_forecast, kalman, stack_weights
except ImportError:
    kalman = None


def filt(v, y, dt=None, first=None, band=None, tau2=1.0, q=0.0, phi=1.0, kappa=1.0, m0=0.0, drift=None):
    n = len(v)
    out = [np.empty(n) for _ in range(3)]
    first = np.r_[True, np.zeros(n - 1, bool)] if first is None else np.asarray(first)
    ll = kalman(first, np.zeros(n) if dt is None else np.asarray(dt, float), np.zeros(n, np.int64) if band is None else band,
                np.asarray(v, float), np.asarray(y, float), tau2, q, phi, kappa, m0,
                np.zeros(N_BANDS) if drift is None else np.asarray(drift, float), *out)
    return ll, out


@unittest.skipIf(kalman is None, "model dependencies not installed")
class TrendFilter(unittest.TestCase):
    def test_constant_level_is_the_shrunk_ratio_of_sums(self):
        v, y = np.array([2.0, 30.0, 8.0, 50.0]), np.array([1.5, 2.0, -1.0, 6.0])
        _, (_, post_m, post_p) = filt(v, y, tau2=0.5)
        self.assertAlmostEqual(post_m[-1], y.sum() / (1 / 0.5 + v.sum()))
        self.assertAlmostEqual(post_p[-1], 1 / (1 / 0.5 + v.sum()))

    def test_a_duck_counts_by_its_information(self):
        # out first ball: nearly a whole dismissal above expectation on almost no information
        _, (_, post_m, _) = filt([0.05], [0.95], tau2=0.01)
        self.assertLess(post_m[0], 0.01)                      # the level moves by under tau2 * y
        _, (_, long_m, _) = filt([3.0], [0.95], tau2=0.01)    # the same surprise over a long innings moves it less
        self.assertLess(long_m[0], post_m[0])

    def test_level_decays_and_drifts_between_observations(self):
        _, (pre_m, _, _) = filt([1e6, 1.0], [2e5, 0.0], dt=[0.0, 2.0], band=np.array([1, 1]), tau2=1.0, phi=0.5,
                                drift=[0.0, 0.01, 0.0, 0.0, 0.0, 0.0])
        self.assertAlmostEqual(pre_m[1], 0.2 * 0.5 ** 2 + 0.01 * 2, places=5)

    def test_players_do_not_share_a_state(self):
        _, (pre_m, _, _) = filt([10.0, 10.0], [5.0, 0.0], first=[True, True], m0=0.1)
        self.assertEqual(pre_m.tolist(), [0.1, 0.1])

    def test_frozen_forecast_uses_only_earlier_observations(self):
        cut = pd.Timestamp("2025-06-01")
        d = pd.DataFrame({"player": ["a", "a", "a", "b"], "date": pd.to_datetime(["2024-06-01", "2025-05-31", "2025-12-01", "2025-12-01"]),
                          "first": [True, False, False, True], "dt": [0.0, 1.0, 0.5, 0.0], "band": 0,
                          "v": [100.0, 100.0, 50.0, 50.0], "y": [10.0, 10.0, 500.0, 500.0]})
        x = np.r_[np.log(1.0), np.log(1e-9), 30.0, 0.0, 0.0, np.zeros(N_BANDS)]   # constant level, no drift
        f = frozen_forecast(d, x, cut)
        self.assertAlmostEqual(f.iloc[0], 20.0 / 201.0, places=6)   # player a: his two earlier observations only
        self.assertTrue(np.isnan(f.iloc[1]))                         # player b has no earlier observation

    def test_stack_weight(self):
        rng = np.random.default_rng(0)
        s, gap = rng.normal(size=200), rng.normal(size=200)
        te = pd.DataFrame({"skill": "bat_runs", "group": "india", "s": s, "level_split": s + gap, "y": s + 0.3 * gap, "v": 2.0})
        self.assertAlmostEqual(stack_weights(te, "level_split").iloc[0], 0.3)


if __name__ == "__main__":
    unittest.main()
