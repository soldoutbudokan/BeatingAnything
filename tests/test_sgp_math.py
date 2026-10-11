"""Economic and integer-event invariants for the SGP collector."""
import itertools
import json
import unittest

from beating.sgp.math import (contained, decimal_odds, devig, evaluate, event_key,
                              extrema, feasible, generate_candidates, intersection,
                              parse_leg, polytope)


def leg(stat, side, line, identity=None):
    value = {"stat": stat, "side": side, "line": line}
    if identity is not None:
        value["selection_id"] = identity
    return value


REFERENCE = {"other": "R", "sum_line": 89.5, "other_line": 49.5,
             "prices": {"OO": 128, "OU": 506, "UO": 521, "UU": 126}}
CMC = [leg("S", "at_least", 90, "sum-90"), leg("R", "under", 49.5, "rush-under"),
       leg("C", "over", 34.5, "receiving-main"), leg("C", "at_least", 40, "receiving-40")]


class SgpMathTests(unittest.TestCase):
    def test_cmc_historical_quote_reproduces_both_ev_models(self):
        result = evaluate(CMC, 1064, REFERENCE)
        self.assertTrue(result["exact"])
        self.assertEqual(result["included_cells"], ["OU"])
        self.assertAlmostEqual(result["models"]["power"]["probability_lower"], .120247601, places=8)
        self.assertAlmostEqual(result["models"]["additive"]["probability_lower"], .113236135, places=8)
        self.assertAlmostEqual(result["models"]["power"]["ev_lower"], .399682, places=5)
        self.assertAlmostEqual(result["conservative_ev_lower"], .31806861, places=7)
        self.assertEqual(result["min_profitable_american"], 784)
        self.assertTrue(result["both_models_positive"])
        self.assertGreater(evaluate(CMC, 784, REFERENCE)["conservative_ev_lower"], 0)
        self.assertLess(evaluate(CMC, 783, REFERENCE)["conservative_ev_lower"], 0)
        json.dumps(result, allow_nan=False)

    def test_strict_subset_does_not_inherit_whole_cell_probability(self):
        # C>=50 is not implied by S>=90,R<=49 (which only implies C>=41).
        strict = CMC[:2] + [leg("C", "at_least", 50)]
        result = evaluate(strict, 2000, REFERENCE)
        self.assertEqual(result["included_cells"], [])
        self.assertEqual(result["intersecting_cells"], ["OU"])
        self.assertFalse(result["exact"])
        self.assertEqual(result["conservative_probability_lower"], 0)
        self.assertEqual(result["conservative_ev_lower"], -1)
        self.assertIsNone(result["min_profitable_american"])
        self.assertFalse(result["both_models_positive"])

    def test_reference_subset_produces_lower_bound_without_interpolation(self):
        wider = [leg("S", "at_least", 80), leg("R", "under", 49.5)]
        result = evaluate(wider, 1064, REFERENCE)
        self.assertEqual(result["included_cells"], ["OU"])
        self.assertEqual(result["intersecting_cells"], ["OU", "UU"])
        self.assertFalse(result["exact"])
        self.assertGreater(result["models"]["power"]["probability_upper"],
                           result["models"]["power"]["probability_lower"])

    def test_negative_yards_are_not_silently_removed(self):
        bounds = polytope([leg("R", "at_most", -2), leg("C", "at_least", 5), leg("S", "at_most", 3)])
        self.assertTrue(feasible(bounds))
        self.assertEqual(extrema(bounds)["R"][1], -2)
        self.assertFalse(contained(polytope([leg("S", "at_least", 90)]),
                                   polytope([leg("R", "at_least", 0)])))
        self.assertEqual(parse_leg(leg("R", "under", -1.5)), ("R", 1, -2))

    def test_integer_reference_lines_reject_unrepresented_pushes(self):
        for field in ("sum_line", "other_line"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "push"):
                evaluate(CMC, 1064, {**REFERENCE, field: 90})

    def test_bad_odds_and_missing_cells_fail_closed(self):
        for bad in (0, 99, -99, None, True, float("inf"), float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                decimal_odds(bad)
        with self.assertRaises(ValueError):
            devig({"OO": 100, "OU": 200, "UO": 300})
        with self.assertRaises(ValueError):
            parse_leg(leg("R", "over", float("nan")))

    def test_invalid_additive_is_not_clipped_or_called_conservative(self):
        reference = {**REFERENCE, "prices": {"OO": -10000, "OU": -10000, "UO": -10000, "UU": 10000}}
        result = evaluate(CMC, 10000, reference)
        self.assertIsNone(result["models"]["additive"])
        self.assertIsNone(result["conservative_ev_lower"])
        self.assertFalse(result["both_models_positive"])
        self.assertIsNotNone(result["warning"])

    def test_canonical_key_groups_only_equivalent_events(self):
        self.assertEqual(event_key(CMC[:2]), event_key(CMC))
        self.assertEqual(event_key(CMC), event_key(list(reversed(CMC))))
        self.assertNotEqual(event_key(CMC), event_key(CMC[:2] + [leg("C", "at_least", 50)]))
        impossible = [leg("R", "over", 5), leg("R", "under", 5)]
        self.assertEqual(event_key(impossible), "empty")
        self.assertFalse(feasible(polytope(impossible)))

    def test_extrema_and_containment_match_exhaustive_integer_grid(self):
        # Finite boxes make exhaustive truth independent of the geometry formulas.
        for rlo, rhi, clo, chi, slo, shi in itertools.product((-2, 0), (1, 3), (-2, 0), (1, 3), (-3, 0), (1, 4)):
            bounds = {"R": [rlo, rhi], "C": [clo, chi], "S": [slo, shi]}
            points = [(r, c, r + c) for r in range(rlo, rhi + 1) for c in range(clo, chi + 1)
                      if slo <= r + c <= shi]
            self.assertEqual(feasible(bounds), bool(points))
            if not points:
                self.assertIsNone(extrema(bounds))
                continue
            expected = {stat: [min(p[i] for p in points), max(p[i] for p in points)]
                        for i, stat in enumerate(("R", "C", "S"))}
            self.assertEqual(extrema(bounds), expected)
            right = polytope([leg("C", "at_least", 0), leg("S", "at_most", 2)])
            self.assertEqual(contained(bounds, right), all(c >= 0 and s <= 2 for r, c, s in points))
            self.assertEqual(feasible(intersection(bounds, right)), any(c >= 0 and s <= 2 for r, c, s in points))

    def test_candidate_search_keeps_redundant_leg_identities_and_four_leg_ticket(self):
        offered = CMC + [leg("C", "at_least", 40, "another-receiving-40"), leg("C", "at_least", 50, "not-redundant")]
        result = generate_candidates(offered)
        self.assertFalse(result["truncated"])
        self.assertIn(CMC, result["candidates"])
        self.assertIn(CMC[:2] + [offered[4]], result["candidates"])
        self.assertNotIn(CMC[:2] + [offered[5]], result["candidates"])
        for candidate in result["candidates"]:
            self.assertTrue(all(any(item is original for original in offered) for item in candidate))
            self.assertEqual([offered.index(item) for item in candidate], sorted(offered.index(item) for item in candidate))
        self.assertGreater(result["candidate_count"], result["unique_event_count"])

    def test_candidate_caps_are_explicit_and_empty_inventory_is_complete(self):
        result = generate_candidates(CMC, max_candidates=1)
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(result["truncated"])
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["truncation_reason"], "max_candidates")
        self.assertEqual(generate_candidates([])["candidates"], [])
        self.assertTrue(generate_candidates([])["coverage_complete"])
        with self.assertRaises(ValueError):
            generate_candidates(CMC, max_legs=10)

    def test_receiving_partition_and_upper_redundancy_are_symmetric(self):
        # S<=9,C>=7 implies R<=2, including negative R.
        offered = [leg("S", "under", 9.5), leg("C", "over", 6.5), leg("R", "at_most", 2)]
        self.assertIn(offered, generate_candidates(offered)["candidates"])
        reference = {"other": "C", "sum_line": 9.5, "other_line": 6.5, "prices": dict.fromkeys(("OO", "OU", "UO", "UU"), 300)}
        result = evaluate(offered, 400, reference)
        self.assertEqual(result["included_cells"], ["UO"])
        self.assertEqual(result["conservative_ev_lower"], .25)


if __name__ == "__main__":
    unittest.main()
