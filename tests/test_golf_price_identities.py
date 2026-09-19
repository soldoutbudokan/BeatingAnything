import unittest

from tools.resolve_golf_price_identities import profile_name, resolve


class GolfPriceIdentityTests(unittest.TestCase):
    def test_profile_must_echo_the_requested_id_and_one_name(self):
        raw = (b'<meta property="og:url" content="https://datagolf.com/player_profiles?dg_id=42">'
               b'<meta property="og:title" content="Sam Stevens Stats | Data Golf">')
        self.assertEqual(profile_name(raw, "42"), "Sam Stevens")
        with self.assertRaises(ValueError):
            profile_name(raw, "43")
        with self.assertRaises(ValueError):
            profile_name(raw + raw, "42")

    def test_alias_requires_the_actual_dg_id(self):
        row = {"market": "Round matchups", "player_name": "Stevens, Samuel", "dg_id": "42",
               "opponent_name": "Player, Other", "opponent_dg_id": "43"}
        names = {"samstevens": [{"name": "Sam Stevens", "pga_player_id": "1", "course_id": "004"}],
                 "otherplayer": [{"name": "Other Player", "pga_player_id": "2", "course_id": "104"}]}
        pair = ("004", "104")
        self.assertEqual(resolve(row, names, {"99": "Sam Stevens"}, pair)["classification"],
                         "unmatched_or_ambiguous")
        self.assertEqual(resolve(row, names, {"42": "Sam Stevens"}, pair)["classification"],
                         "cross_course")

    def test_transliteration_cannot_resolve_a_collision(self):
        row = {"market": "Round matchups", "player_name": "Hojgaard, Rasmus", "dg_id": "42",
               "opponent_name": "Player, Other", "opponent_dg_id": "43"}
        names = {"rasmushøjgaard": [{"name": "Rasmus Højgaard", "pga_player_id": "1", "course_id": "004"}],
                 "otherplayer": [{"name": "Other Player", "pga_player_id": "2", "course_id": "104"}]}
        profiles = {"42": "Rasmus Hojgaard"}
        pair = ("004", "104")
        self.assertEqual(resolve(row, names, profiles, pair)["classification"], "cross_course")
        names["rasmushøjgaard"].append({"name": "Rasmus Højgaard", "pga_player_id": "3", "course_id": "104"})
        self.assertEqual(resolve(row, names, profiles, pair)["classification"], "unmatched_or_ambiguous")


if __name__ == "__main__":
    unittest.main()
