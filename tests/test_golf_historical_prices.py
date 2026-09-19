import unittest

from tools.audit_golf_historical_prices import classify, clock_status, name_key


class HistoricalGolfPriceTests(unittest.TestCase):
    def setUp(self):
        self.names = {
            "anaplayer": [{"pga_player_id": "1", "course_id": "004"}],
            "benother": [{"pga_player_id": "2", "course_id": "104"}],
            "christhird": [{"pga_player_id": "3", "course_id": "769"}],
        }
        self.row = {"market": "Round matchups", "player_name": "Player, Ana",
                    "opponent_name": "Other, Ben", "opponent2_name": ""}

    def result(self):
        return classify(self.row, self.names, ("004", "104"))["classification"]

    def test_distinct_courses_within_fixed_pair_are_cross_course(self):
        self.assertEqual(self.result(), "cross_course")
        self.names["benother"][0]["course_id"] = "004"
        self.assertEqual(self.result(), "same_course")

    def test_third_course_is_not_an_alternative_contrast(self):
        self.row.update(market="3-balls", opponent2_name="Third, Chris")
        self.assertEqual(self.result(), "outside_declared_pair")

    def test_every_three_ball_player_must_be_matched(self):
        self.row.update(market="3-balls", opponent2_name="Third, Christopher")
        self.assertEqual(self.result(), "unmatched_or_ambiguous")

    def test_no_nickname_or_ambiguous_name_resolution(self):
        self.row["opponent_name"] = "Other, Benjamin"
        self.assertEqual(self.result(), "unmatched_or_ambiguous")
        self.row["opponent_name"] = "Other, Ben"
        self.names["benother"].append({"pga_player_id": "4", "course_id": "104"})
        self.assertEqual(self.result(), "unmatched_or_ambiguous")

    def test_repeated_player_and_missing_course_are_not_cross_course(self):
        self.names["benother"][0]["pga_player_id"] = "1"
        self.assertEqual(self.result(), "duplicate_player")
        self.names["benother"][0].update(pga_player_id="2", course_id=None)
        self.assertEqual(self.result(), "missing_course")

    def test_surname_first_normalizes_only_spelling_format(self):
        self.assertEqual(name_key("Åberg, Ludvig", True), name_key("Ludvig Åberg"))
        self.assertNotEqual(name_key("Stevens, Samuel", True), name_key("Sam Stevens"))
        self.assertIsNone(name_key("Missing delimiter", True))

    def test_naive_clock_never_acquires_an_invented_timezone(self):
        self.assertEqual(clock_status("2025-01-22 10:30:00"), "timezone_missing")
        self.assertEqual(clock_status("2025-01-22T10:30:00Z"), "offset_aware")
        self.assertEqual(clock_status(""), "missing_or_invalid")


if __name__ == "__main__":
    unittest.main()
