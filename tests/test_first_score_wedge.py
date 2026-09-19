import unittest

from tools.screen_nba_first_score_wedge import score_pair


class FirstScoreWedgeTests(unittest.TestCase):
    def play(self, sequence, player, points, kind, total=None):
        return {"sequence_number": sequence, "athlete_id_1": player, "score_value": points,
                "type_text": kind, "period_number": 1, "scoring_play": True,
                "home_score": points if total is None else total, "away_score": 0}

    def test_free_throw_changes_winner_only_when_field_goal_scorer_differs(self):
        free_throw = self.play(1, 10, 1, "Free Throw - 1 of 2")
        for player, changed in ((10, False), (20, True)):
            field_goal = self.play(2, player, 2, "Layup Shot", total=3)
            result = score_pair([field_goal, free_throw])
            self.assertTrue(result["first_score_is_free_throw"])
            self.assertEqual(result["different_scorer"], changed)

    def test_opening_field_goal_is_same_outcome_under_both_definitions(self):
        self.assertEqual(score_pair([self.play(1, 10, 3, "Three Point Jumper")]),
                         {"first_score_is_free_throw": False, "different_scorer": False})

    def test_unknown_scorer_duplicate_sequence_and_incomplete_scoreboard_fail(self):
        for plays in ([self.play(1, None, 2, "Layup Shot")],
                      [self.play(1, 10, 1, "Free Throw"), self.play(1, 20, 2, "Layup Shot", 3)],
                      [self.play(2, 10, 2, "Layup Shot", 5)],
                      [self.play(1, 10, 1, "Unknown"), self.play(2, 20, 2, "Layup Shot", 3)]):
            with self.subTest(plays=plays), self.assertRaises(ValueError):
                score_pair(plays)


if __name__ == "__main__":
    unittest.main()
