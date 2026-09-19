import unittest

from tools.audit_nba_first_basket_archive import board_status, clock, first_score


class FirstBasketArchiveTests(unittest.TestCase):
    def setUp(self):
        self.start = clock("2025-01-01T20:00:00Z")
        self.rows = [{"name": "Player " + chr(65+i), "price": "11.0",
                      "update_time": "2025-01-01T19:49:00Z",
                      "insert_timestamp_utc": "2025-01-01T19:50:00Z"} for i in range(10)]

    def test_full_board_requires_distinct_runners(self):
        self.assertEqual(board_status(self.rows, self.start), "pregame_ten_runner_board")
        self.rows[-1]["name"] = self.rows[0]["name"]
        self.assertEqual(board_status(self.rows, self.start), "not_ten_unique_runners")

    def test_future_updates_and_late_receipts_are_excluded(self):
        for row in self.rows:
            row["update_time"] = "2025-01-01T19:51:00Z"
        self.assertEqual(board_status(self.rows, self.start), "future_quote_update")
        for row in self.rows:
            row["insert_timestamp_utc"] = "2025-01-01T20:00:00Z"
        self.assertEqual(board_status(self.rows, self.start), "receipt_within_minute_of_or_after_start")

    def test_stale_and_unzoned_quotes_do_not_gain_eligibility(self):
        for row in self.rows:
            row["update_time"] = "2025-01-01T19:40:00Z"
        self.assertEqual(board_status(self.rows, self.start), "quote_older_than_five_minutes")
        with self.assertRaises(ValueError):
            clock("2025-01-01 19:40:00")

    def test_first_score_includes_free_throws_and_checks_scoreboard(self):
        free_throw = {"sequence_number": 3, "period_number": 1, "scoring_play": True,
                      "score_value": 1, "home_score": 1, "away_score": 0}
        field_goal = {"sequence_number": 4, "period_number": 1, "scoring_play": True,
                      "score_value": 2, "home_score": 1, "away_score": 2}
        self.assertEqual(first_score([field_goal, free_throw]), free_throw)
        with self.assertRaises(ValueError):
            first_score([field_goal])


if __name__ == "__main__":
    unittest.main()
