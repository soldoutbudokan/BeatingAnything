import unittest

import numpy as np

from beating.cricket import glm


def _synthetic(n=60_000, n_players=80, k=4, sigma=0.5, seed=7):
    rng = np.random.default_rng(seed)
    true = rng.normal(0, sigma, (n_players, k - 1))
    ctx_true = rng.normal(0, 0.4, (5, k - 1))
    ump_true = rng.normal(0, 0.6, 6)
    player = rng.integers(0, n_players, n).astype(np.int32)
    ctx = rng.integers(0, 5, n).astype(np.int32)
    ump_a = rng.integers(0, 6, n).astype(np.int32)
    ump_b = rng.integers(0, 6, n).astype(np.int32)
    spin = (rng.random(n) < 0.4).astype(np.float32)
    x = rng.normal(size=(n, 2)).astype(np.float32)
    dense_true = np.array([[0.3, -0.2, 0.0], [0.0, 0.1, 0.25]])
    basis = np.zeros((1, k - 1))
    basis[0, -1] = 1.0
    eta = np.zeros((n, k))
    eta[:, 1:] = -1.0 + true[player] + ctx_true[ctx] + x @ dense_true
    eta[:, -1] += 0.5 * ump_true[ump_a] + 0.5 * ump_true[ump_b]
    p = np.exp(eta - eta.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    y = (p.cumsum(1) < rng.random((n, 1))).sum(1).astype(np.int8)
    half = np.full(n, 0.5, dtype=np.float32)
    groups = [
        glm.Group("player", player, n_players, 1.0),
        glm.Group("ctx", ctx, 5, 1.0),
        glm.Group("umpire", ump_a, 6, 1.0, weight=half, index2=ump_b, weight2=half, basis=basis),
        glm.Group("player_spin", player, n_players, 0.3, weight=spin),
    ]
    design = glm.Design(y=y, n_classes=k, groups=groups, dense=x, sigma_dense=1.0)
    return design, true, dense_true


class GlmTests(unittest.TestCase):
    def test_gradient_matches_finite_differences(self):
        design, _, _ = _synthetic(n=3_000, n_players=10)
        prep = glm._Prepared(design, chunk=700)
        size = prep.layout.size
        rng = np.random.default_rng(1)
        theta = rng.normal(0, 0.1, size)
        chunks = range(len(prep.chunks))
        loss, grad = prep.loss_grad(theta, chunks)
        for j in rng.choice(size, 25, replace=False):
            e = np.zeros(size)
            e[j] = 1e-5
            up = prep.loss_grad(theta + e, chunks)[0]
            dn = prep.loss_grad(theta - e, chunks)[0]
            self.assertAlmostEqual((up - dn) / 2e-5, grad[j], delta=1e-4 * max(1, abs(grad[j])))

    def test_recovers_effects_and_prior_scale(self):
        design, true, dense_true = _synthetic()
        res = glm.fit_eb(design, rounds=2, processes=2)
        est = res.params["player"]
        self.assertGreater(np.corrcoef(est.ravel(), true.ravel())[0, 1], 0.9)
        self.assertLess(np.abs(design.groups[0].sigma - 0.5).max(), 0.12)
        np.testing.assert_allclose(res.params["dense"], dense_true, atol=0.06)
        self.assertLess(np.max(design.groups[3].sigma), 0.2)

    def test_parallel_and_serial_agree(self):
        design, _, _ = _synthetic(n=20_000, n_players=30)
        serial = glm.fit(design, processes=1, maxiter=60)
        parallel = glm.fit(design, processes=2, maxiter=60)
        np.testing.assert_allclose(serial.params["player"], parallel.params["player"], atol=1e-4)

    def test_hessian_diag_matches_finite_differences(self):
        design, _, _ = _synthetic(n=2_000, n_players=8)
        prep = glm._Prepared(design, chunk=600)
        rng = np.random.default_rng(3)
        theta = rng.normal(0, 0.1, prep.layout.size)
        params = prep.layout.unpack(theta)
        hd = glm.hessian_diag(design, params, prep)
        for name in ("player", "umpire", "player_spin"):
            s = prep.layout.slices[name]
            for j in (s.start, s.start + 3, s.stop - 1):
                e = np.zeros(prep.layout.size)
                e[j] = 1e-4
                gu = prep.loss_grad(theta + e, range(len(prep.chunks)))[1][j]
                gd = prep.loss_grad(theta - e, range(len(prep.chunks)))[1][j]
                self.assertAlmostEqual((gu - gd) / 2e-4, hd[name].ravel()[j - s.start], delta=1e-3)

    def test_penalty_gradient_with_random_walk_and_prior_mean(self):
        design, _, _ = _synthetic(n=2_000, n_players=8)
        rng = np.random.default_rng(5)
        design.groups.append(glm.Group("season", rng.integers(0, 6, design.n).astype(np.int32), 6,
                                       np.array([0.2, 0.3, 0.4]), rw_prev=np.array([-1, 0, 1, -1, 3, 4]),
                                       sigma_root=0.8))
        design.groups[1].prior_mean = rng.normal(0, 0.2, (5, 3))
        layout = glm._Layout(design)
        theta = rng.normal(0, 0.3, layout.size)
        pen, grad = glm._penalty(design, layout, theta)
        for j in rng.choice(layout.size, 40, replace=False):
            e = np.zeros(layout.size)
            e[j] = 1e-6
            num = (glm._penalty(design, layout, theta + e)[0] - glm._penalty(design, layout, theta - e)[0]) / 2e-6
            self.assertAlmostEqual(num, grad[j], delta=1e-5 * max(1, abs(grad[j])))

    def test_random_walk_forecast_tracks_drift(self):
        rng = np.random.default_rng(11)
        n_seasons, n = 8, 80_000
        drift = np.cumsum(rng.normal(0, 0.15, n_seasons))
        season = rng.integers(0, n_seasons, n).astype(np.int32)
        p1 = 1 / (1 + np.exp(-(-0.5 + drift[season])))
        y = (rng.random(n) < p1).astype(np.int8)
        g = glm.Group("season", season, n_seasons, 0.1, rw_prev=np.array([-1] + list(range(n_seasons - 1))),
                      sigma_root=2.0)
        design = glm.Design(y=y, n_classes=2, groups=[g], sigma_intercept=0.01)
        res = glm.fit_eb(design, processes=1)
        est = res.params["season"][:, 0] - 0.5
        self.assertGreater(np.corrcoef(est, drift)[0, 1], 0.95)
        self.assertLess(abs(np.diff(est).std() - np.diff(drift).std()), 0.08)

    def test_mask_makes_class_impossible_and_matches_offset(self):
        design, _, _ = _synthetic(n=4_000, n_players=10)
        rows = np.zeros(design.n, bool)
        rows[::3] = True
        design.y[rows & (design.y == 3)] = 0
        design.masks = [(rows, 3)]
        res = glm.fit(design, processes=1, maxiter=80)
        p = glm.predict_proba(design, res.params)
        self.assertLess(p[rows, 3].max(), 1e-10)
        self.assertGreater(p[~rows, 3].mean(), 0.05)

    def test_preconditioning_reaches_same_optimum(self):
        design, _, _ = _synthetic(n=15_000, n_players=25)
        a = glm.fit(design, processes=1, precondition=True)
        b = glm.fit(design, processes=1, precondition=False, maxiter=3000)
        self.assertLess(a.n_eval, b.n_eval)
        np.testing.assert_allclose(a.params["player"], b.params["player"], atol=2e-3)

    def test_predict_proba_sums_to_one(self):
        design, _, _ = _synthetic(n=2_000, n_players=10)
        res = glm.fit(design, processes=1, maxiter=30)
        p = glm.predict_proba(design, res.params)
        np.testing.assert_allclose(p.sum(1), 1, atol=1e-5)
        self.assertGreater(glm.log_loss(design, res.params), 0)


if __name__ == "__main__":
    unittest.main()
