import math
import unittest

import numpy as np
from scipy.stats import poisson

from tools.explore_nhl_shot_dispersion import decimal, shape_forecast


class ShotDispersionTests(unittest.TestCase):
    def test_no_overdispersion_preserves_market(self):
        # Variance below the count mean must not invent a correction.
        for line, q in [(0.5, .25), (2.5, .5), (8.5, .9)]:
            mu, _, _, alpha, prediction = shape_forecast(q, line, np.array([1, 2] * 40))
            self.assertEqual(alpha, 0)
            self.assertEqual(prediction, q)
            self.assertAlmostEqual(poisson.cdf(int(line), mu), q, places=10)

    def test_geometric_limit_has_closed_form(self):
        # This prior forces alpha's fixed cap=1. For line .5 and baseline .5,
        # Poisson mean is log(2), and the replacement geometric P(0)=1/(1+mu).
        mu, _, _, alpha, prediction = shape_forecast(.5, .5, np.array([0] * 60 + [8] * 20))
        self.assertAlmostEqual(mu, math.log(2), places=10)
        self.assertEqual(alpha, 1)
        self.assertAlmostEqual(prediction, 1 / (1 + math.log(2)), places=10)

    def test_prices_keep_plus_and_minus_distinct(self):
        self.assertAlmostEqual(decimal(128), 2.28)
        self.assertAlmostEqual(decimal(-168), 1 + 100 / 168)
        with self.assertRaises(ValueError):
            decimal(1.9)
        with self.assertRaises(ValueError):
            decimal(float("nan"))


if __name__ == "__main__":
    unittest.main()
