import unittest

import pandas as pd

from tools.recheck_golf_birdie_prices import decimal, event_name, name_matches, summarize


class BirdieRecheckTests(unittest.TestCase):
    def test_kims_are_distinct(self):
        self.assertTrue(name_matches("S-H Kim", "Kim, Seonghyeon"))
        self.assertFalse(name_matches("S-H Kim", "Kim, Si Woo"))
        self.assertTrue(name_matches("S.W. Kim", "Kim, Si Woo"))
        self.assertFalse(name_matches("Si Woo Kim", "Kim, Seonghyeon"))

    def test_full_names_do_not_degrade_to_initials(self):
        self.assertTrue(name_matches("Cam. Young", "Young, Cameron"))
        self.assertFalse(name_matches("Cam. Young", "Young, Carson"))
        self.assertFalse(name_matches("Cameron Young", "Young, Carson"))
        # The calling join must reject this genuinely ambiguous abbreviation.
        self.assertTrue(name_matches("C. Young", "Young, Carson"))
        self.assertTrue(name_matches("C. Young", "Young, Cameron"))

    def test_compound_names(self):
        self.assertTrue(name_matches("M. W. Lee", "Lee, Min Woo"))
        self.assertFalse(name_matches("M. W. Lee", "Lee, Danny"))
        self.assertTrue(name_matches("B.H. An", "An, Byeong Hun"))
        self.assertTrue(name_matches("E. Van Rooyen", "van Rooyen, Erik"))
        self.assertTrue(name_matches("R. Mcllroy", "McIlroy, Rory"))

    def test_event_identity(self):
        self.assertEqual(event_name("US Masters 2024"), event_name("Masters Tournament"))
        self.assertNotEqual(event_name("BMW PGA Championship"), event_name("BMW Championship"))

    def test_american_prices(self):
        self.assertEqual(decimal([100, -100, -125, 150]).tolist(), [2.0, 2.0, 1.8, 2.5])
        with self.assertRaises(ValueError):
            decimal([-90])

    def test_push_and_missing_exposure(self):
        frame = pd.DataFrame({"year": [2025]*4, "event_id": [1, 1, 2, 2],
                              "actual": [2, 5, 4, float("nan")], "line": [3.5, 3.5, 4, 4],
                              "price": [100, -125, -110, -110]})
        result = summarize(frame, "actual", "price")
        self.assertEqual((result["wins"], result["losses"], result["pushes"]), (1, 1, 1))
        self.assertEqual(result["units"], 0)
        self.assertEqual(result["roi_missing_all_losses"], -0.25)
        self.assertEqual(result["graded"], 3)
        self.assertEqual(result["offered"], 4)


if __name__ == "__main__":
    unittest.main()
