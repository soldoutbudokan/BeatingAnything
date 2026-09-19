import unittest

from beating.first_basket import FirstBasketState, select_bet


class FirstBasketModelTests(unittest.TestCase):
    def setUp(self):
        self.state = FirstBasketState()
        self.runners = [{"player_id": f"p{i}", "decimal": 8.0 + i} for i in range(10)]
        self.roster = [(f"p{i}", "H" if i < 5 else "A", True) for i in range(10)]
        self.event = {
            "game_id": "prior", "season": 2024, "home": "H", "away": "A",
            "roster": self.roster, "valid_role": False, "valid_jump": False,
        }
        self.state.observe(self.event)

    def test_without_role_history_both_models_agree_and_conserve_probability(self):
        result = self.state.forecast("H", "A", self.runners)
        for model in ("market", "tip", "tip_role"):
            self.assertAlmostEqual(sum(result[model].values()), 1)
            self.assertTrue(all(p > 0 for p in result[model].values()))
        self.assertAlmostEqual(result["home_possession_probability"], .5)
        self.assertAlmostEqual(sum(result["tip"][f"p{i}"] for i in range(5)), .5)
        for player in result["tip"]:
            self.assertAlmostEqual(result["tip"][player], result["tip_role"][player])

    def test_swapping_home_and_away_preserves_player_probabilities(self):
        self.state.observe({**self.event, "game_id": "jump", "valid_jump": True,
                            "valid_role": True, "jumper_home": "p0", "jumper_away": "p5",
                            "possession_team": "H", "scorer_team": "H", "scorer": "p1"})
        original = self.state.forecast("H", "A", self.runners)
        swapped = self.state.forecast("A", "H", self.runners)
        self.assertGreater(original["home_possession_probability"], .5)
        self.assertAlmostEqual(original["home_possession_probability"],
                               1 - swapped["home_possession_probability"])
        for model in ("market", "tip", "tip_role"):
            for player in original[model]:
                self.assertAlmostEqual(original[model][player], swapped[model][player])

    def test_incomplete_identity_or_team_assignment_and_invalid_prices_fail(self):
        with self.assertRaises(ValueError):
            self.state.forecast("H", "A", self.runners[:-1] + [self.runners[0]])
        for price in (1, float("nan"), float("inf")):
            with self.subTest(price=price), self.assertRaises(ValueError):
                self.state.forecast("H", "A", [{**self.runners[0], "decimal": price}] + self.runners[1:])
        self.state.player_team["p0"] = "OTHER"
        with self.assertRaises(ValueError):
            self.state.forecast("H", "A", self.runners)

    def test_new_season_regresses_ratings_and_duplicate_games_are_rejected(self):
        self.state.ratings["p0"] = 1700
        self.state.observe({**self.event, "game_id": "next_season", "season": 2025})
        self.assertEqual(self.state.ratings["p0"], 1650)
        with self.assertRaises(ValueError):
            self.state.observe(self.event)
        with self.assertRaises(ValueError):
            self.state.observe({**self.event, "game_id": "out_of_order"})

    def test_reserve_can_remove_a_marginal_bet_and_ties_use_player_id(self):
        runners = [{"player_id": "b", "decimal": 10}, {"player_id": "a", "decimal": 10}]
        probabilities = {"a": .108, "b": .108}
        self.assertEqual(select_bet(runners, probabilities)["player_id"], "a")
        self.assertIsNone(select_bet(runners, probabilities, reserve=True))
        self.assertIsNone(select_bet([{"player_id": "a", "decimal": 27}], {"a": .5}))


if __name__ == "__main__":
    unittest.main()
