from datetime import date
import math
import unittest

from beating.first_score_wedge import convert, normalized_prices, prior_rates, select_bet
from tools.backtest_nba_first_score_wedge import bootstrap_ratios, match_reference, restriction, summarize


class WedgePriceTests(unittest.TestCase):
    def test_conversion_conserves_probability_and_uniform_rates_make_no_change(self):
        runners = [{"player_id": str(i), "decimal": i + 6} for i in range(10)]
        q = normalized_prices(runners)
        uniform = convert(q, {}, .3)
        for player in q:
            self.assertAlmostEqual(uniform[player], q[player])
        p = convert(q, {"0": 1.2}, .3)
        self.assertAlmostEqual(sum(p.values()), 1)
        self.assertGreater(p["0"], q["0"])
        self.assertTrue(all(p[x] < q[x] for x in q if x != "0"))
        self.assertTrue(all(math.isfinite(x) and x > 0 for x in p.values()))

    def test_prior_rates_shrink_use_only_starts_and_reject_future_or_duplicates(self):
        rows = [{"game_id": "202404010H", "player_id": "a", "starter": "True", "FG": "10", "FT": "10"},
                {"game_id": "202404020H", "player_id": "b", "starter": "True", "FG": "30", "FT": "0"},
                {"game_id": "202404030H", "player_id": "c", "starter": "False", "FG": "100", "FT": "100"},
                {"game_id": "202404040H", "player_id": "a", "starter": "True", "FG": "", "FT": "100"}]
        before = date(2024, 12, 1)
        rates, league, counts = prior_rates(rows, before)
        self.assertEqual(league, .25)
        self.assertAlmostEqual(rates["a"], 35 / 110)
        self.assertAlmostEqual(rates["b"], 25 / 130)
        self.assertNotIn("c", rates)
        self.assertEqual(counts["missing_numeric_starts"], 1)
        for bad in ([*rows, rows[0]], [{**rows[0], "game_id": "202412010H"}],
                    [{**rows[0], "FG": "nan"}], [{**rows[0], "FT": "-1"}],
                    [{**rows[0], "FG": "", "FT": "inf"}]):
            with self.assertRaises(ValueError):
                prior_rates(bad, before)

    def test_selection_requires_positive_adjustment_ties_and_reserve(self):
        runners = [{"player_id": "b", "decimal": 10}, {"player_id": "a", "decimal": 10},
                   {"player_id": "c", "decimal": 26}]
        p = {"a": .107, "b": .107, "c": .2}
        q = {"a": .10, "b": .10, "c": .21}
        self.assertEqual(select_bet(runners, p, q)["player_id"], "a")
        self.assertIsNone(select_bet(runners, p, q, reserve=True))
        self.assertIsNone(select_bet(runners, q, q))

    def board(self):
        rows = [{"name": f"Player {i}", "price": "10", "game_id": "202502030H", "event_id": "event",
                 "update_time": "2025-02-03T20:00:00Z", "insert_timestamp_utc": "2025-02-03T20:01:00Z"}
                for i in range(10)]
        board = {"game_id": "202502030H", "event_id": "event", "received_at": "2025-02-03T20:01:00Z",
                 "independent_start": "2025-02-03T20:10:00Z", "publisher_start": "2025-02-03T20:10:00Z",
                 "prices": [{"name": r["name"], "decimal": 10, "quote_time": r["update_time"]} for r in rows]}
        return board, rows

    def test_matching_rejects_joint_staleness_even_if_each_board_fresh_at_receipt(self):
        board, rows = self.board()
        self.assertIsNone(match_reference(board, rows))
        later = [{**r, "update_time": "2025-02-03T20:05:00Z", "insert_timestamp_utc": "2025-02-03T20:05:01Z"} for r in rows]
        self.assertEqual(match_reference(board, later), "joint_price_stale")
        future = [{**r, "update_time": "2025-02-03T20:01:01Z"} for r in rows]
        self.assertEqual(match_reference(board, future), "future_quote_update")
        self.assertEqual(match_reference(board, [{**r, "event_id": "other"} for r in rows]), "event_mismatch")
        wrong_names = [{**r, "name": "Wrong"} if i == 0 else r for i, r in enumerate(rows)]
        self.assertEqual(match_reference(board, wrong_names), "candidate_sets_differ")

    def test_one_minute_lead_and_five_minute_age_boundaries_and_day_restrictions(self):
        board, rows = self.board()
        board = {**board, "independent_start": "2025-02-03T20:06:00Z"}
        rows = [{**r, "insert_timestamp_utc": "2025-02-03T20:05:00Z"} for r in rows]
        self.assertIsNone(match_reference(board, rows))
        later = [{**r, "insert_timestamp_utc": "2025-02-03T20:05:01Z"} for r in rows]
        self.assertEqual(match_reference(board, later), "joint_decision_too_late")
        self.assertIsNone(restriction("202502030H", {"regular-season"}))
        self.assertEqual(restriction("202502070H", {"regular-season"}), "friday_promotion_day")
        self.assertEqual(restriction("202502030H", {"playoffs"}), "not_verified_regular_season")

    def test_unknowns_and_voids_remain_in_stake_denominator(self):
        outcomes = [("win", 8.82), ("loss", -1), ("void", 0), ("unresolved", None)]
        rows = [{"week": "2025-W01", "settlement": {"status": status, "profit": profit, "reason": "missing"},
                 "bet_diagnostics": {"settlement": {"unconverted_ev": .02}}, "scores": None}
                for status, profit in outcomes]
        result = summarize(rows, "settlement")
        self.assertEqual(result["original_stake_turnover"], 4)
        self.assertEqual(result["nonvoid_settled_turnover"], 2)
        self.assertAlmostEqual(result["unresolved_all_loss_roi"], 6.82 / 4)
        self.assertAlmostEqual(result["unresolved_all_void_roi"], 7.82 / 4)
        self.assertIsNone(result["roi_bootstrap_all_loss"]["corrected_interval"])

    def test_corrected_interval_uses_sixteen_comparisons_and_week_blocks(self):
        rows = [(f"week{i}", 2, 4) for i in range(8)]
        result = bootstrap_ratios(rows)
        self.assertEqual(result["confidence"], 1 - .05 / 16)
        self.assertEqual(result["corrected_interval"], [.5, .5])
        self.assertIsNone(bootstrap_ratios(rows[:-1])["corrected_interval"])


if __name__ == "__main__":
    unittest.main()
