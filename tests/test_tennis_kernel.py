import unittest
from unittest.mock import patch

import numpy as np

from beating.tennis_kernel import (fit_hold_probabilities, game_hold_probability,
                                   match_distribution, match_metrics,
                                   serve_point_probability, tiebreak_win_probability,
                                   _SetLaw, _match_probability)


class TennisKernelTests(unittest.TestCase):
    def test_advantage_game_point_inversion(self):
        for point_p in (.05, .25, .5, .65, .85, .95):
            hold = game_hold_probability(point_p)
            self.assertAlmostEqual(serve_point_probability(hold), point_p, places=10)
            self.assertAlmostEqual(game_hold_probability(1-point_p), 1-hold, places=12)

    def test_total_probability_mass_and_support(self):
        for hold1, hold2 in ((.5, .5), (.75, .82), (.95, .6), (.995, .995)):
            law = match_distribution(hold1, hold2)
            pmf = law["total_games_pmf"]
            self.assertEqual(len(pmf), 40)
            self.assertAlmostEqual(pmf.sum(), 1, places=12)
            self.assertTrue((pmf >= 0).all())
            self.assertEqual(pmf[:12].sum(), 0)
            self.assertAlmostEqual(law["over_21_5_p"], pmf[22:].sum(), places=14)
            fast_match, fast_tb = match_metrics(hold1, hold2)
            self.assertAlmostEqual(law["match_win_p"], fast_match, places=13)
            self.assertAlmostEqual(law["set_tiebreak_p"], fast_tb, places=13)

    def test_player_swap_equivariance(self):
        first = match_distribution(.91, .74)
        swapped = match_distribution(.74, .91)
        self.assertAlmostEqual(first["match_win_p"], 1-swapped["match_win_p"], places=12)
        np.testing.assert_allclose(first["total_games_pmf"], swapped["total_games_pmf"], atol=1e-13)
        np.testing.assert_allclose(first["player_one_win_games_pmf"],
                                   swapped["player_two_win_games_pmf"], atol=1e-13)

    def test_high_holds_raise_tiebreak_probability(self):
        low = match_distribution(.6, .6)
        high = match_distribution(.95, .95)
        self.assertGreater(high["set_tiebreak_p"], low["set_tiebreak_p"])
        self.assertGreater(high["over_21_5_p"], low["over_21_5_p"])

    def test_equal_players_fair_even_with_extreme_point_holds(self):
        for p in (.000001, .1, .5, .9, .999999):
            for server in (1, 2):
                self.assertAlmostEqual(tiebreak_win_probability(p, p, server), .5, places=11)
        self.assertAlmostEqual(tiebreak_win_probability(1, 0), 1)
        self.assertAlmostEqual(tiebreak_win_probability(0, 1), 0)
        with self.assertRaisesRegex(ValueError, "does not absorb"):
            tiebreak_win_probability(1, 1)

    def test_tiebreak_service_order_against_explicit_point_tree(self):
        p1, p2 = .72, .59
        service_order = (1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1)
        deuce = p1*(1-p2) / (p1*(1-p2) + (1-p1)*p2)

        def enumerate_points(score1, score2, first_server):
            if max(score1, score2) >= 7 and abs(score1-score2) >= 2:
                return float(score1 > score2)
            if score1 == score2 == 6:
                return deuce
            server = service_order[score1+score2]
            if first_server == 2:
                server = 3-server
            win = p1 if server == 1 else 1-p2
            return (win * enumerate_points(score1+1, score2, first_server)
                    + (1-win) * enumerate_points(score1, score2+1, first_server))

        for first_server in (1, 2):
            self.assertAlmostEqual(tiebreak_win_probability(p1, p2, first_server),
                                   enumerate_points(0, 0, first_server), places=12)

    def test_initial_server_is_sampled_once_and_carried_after_tiebreak(self):
        # A deterministic artificial set law isolates service-order plumbing:
        # server 1 wins a 13-game set; server 2 wins a 6-game set. Starting
        # with server 1 changes server for set two, then keeps server 2; the
        # match lasts 25 games. Starting with server 2 gives 12 games.
        one = np.zeros(14); one[13] = 1
        two = np.zeros(14); two[6] = 1
        zero = tuple(np.zeros(14))
        laws = (_SetLaw(tuple(one), zero, 1), _SetLaw(zero, tuple(two), 0))
        with patch("beating.tennis_kernel._set_laws", return_value=laws):
            result = match_distribution(.8, .8)
        expected = np.zeros(40); expected[12] = .5; expected[25] = .5
        np.testing.assert_allclose(result["total_games_pmf"], expected, atol=0)
        self.assertEqual(result["match_win_p"], 0)
        self.assertEqual(_match_probability(laws), 0)

    def test_known_targets_recover_holds_and_total_distribution(self):
        expected = match_distribution(.87, .79)
        fitted = fit_hold_probabilities(expected["match_win_p"], expected["set_tiebreak_p"])
        np.testing.assert_allclose([fitted["hold1"], fitted["hold2"]], [.87, .79], atol=1e-5)
        self.assertLess(fitted["max_probability_error"], 1e-6)
        np.testing.assert_allclose(fitted["distribution"]["total_games_pmf"],
                                   expected["total_games_pmf"], atol=1e-6)

    def test_unreachable_targets_rejected(self):
        with self.assertRaisesRegex(ValueError, "probability_mismatch"):
            fit_hold_probabilities(.99, .99)


if __name__ == "__main__":
    unittest.main()
