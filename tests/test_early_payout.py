import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from beating import early_payout as ep

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
CFG = json.loads(ep.CONFIG.read_text())
CURVES = json.loads(ep.CURVES.read_text())["sports"]


def sel(participant, label, books, selection=""):
    return {"participant": participant, "label": label, "selection": selection,
            "books": [{"id": b, "lines": [{"cost": c, "main": True, "active": True, "is_off": False,
                                           "updated": "2026-09-24 11:30:00", "link": f"https://book/{b}"}]}
                      for b, c in books.items()]}


NFL_EVENT = {"id": 1, "scheduled": "2026-09-25 00:15:00", "home": "GB", "visitor": "ATL"}
# FanDuel (10) and bet365 (24) quote the dog; Novig (60) and Kalshi (68) are the fair reference.
NFL_OFFER = {"selections": [sel("GB", "Packers", {10: -270, 24: -290, 60: -257, 68: -257}),
                            sel("ATL", "Falcons", {10: 220, 24: 250, 60: 251, 68: 245})]}
SOC_EVENT = {"id": 2, "scheduled": "2026-09-26 23:30:00", "home": "6665", "visitor": "8281"}
SOC_OFFER = {"selections": [sel("6665", "Atlanta United", {2: 150, 10: 145}),
                            sel("8281", "New York City", {2: 175, 10: 190}),
                            sel(None, "Draw", {2: 255, 10: 240}, selection="draw")]}


class Pricing(unittest.TestCase):
    def test_odds_conversions(self):
        self.assertAlmostEqual(ep.american_to_decimal(-250), 1.4)
        self.assertAlmostEqual(ep.american_to_decimal(250), 3.5)
        self.assertEqual(ep.decimal_to_american(3.5), 250)
        self.assertEqual(ep.decimal_to_american(1.4), -250)

    def test_devig_sums_to_one(self):
        p = ep.devig([1.4, 3.3])
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], p[1])

    def test_extra_interpolates_and_shrinks_outside_range(self):
        pts = [{"p": 0.2, "extra": 0.02}, {"p": 0.4, "extra": 0.01}]
        self.assertAlmostEqual(ep.extra_for(0.3, pts), 0.015)
        self.assertAlmostEqual(ep.extra_for(0.1, pts), 0.01)
        self.assertAlmostEqual(ep.extra_for(0.7, pts), 0.005)

    def test_ev_matches_formula(self):
        self.assertAlmostEqual(ep.expected_value(3.5, 0.28, 0.02), 3.5 * 0.30 - 1)

    def test_stake_is_zero_without_edge_and_capped(self):
        rules = {"kelly_fraction": 0.25, "max_stake_fraction": 0.02, "bankroll": 1000}
        self.assertEqual(ep.kelly_stake(2.0, 0.40, 0.01, rules), 0.0)
        self.assertEqual(ep.kelly_stake(5.0, 0.40, 0.02, rules), 20.0)


class Parsing(unittest.TestCase):
    def test_draw_is_keyed_and_never_bet(self):
        quotes, labels = ep.book_quotes(SOC_OFFER)
        self.assertIn("draw", labels)
        rows = ep.evaluate(SOC_EVENT, SOC_OFFER, "SOCCER", CFG, CURVES, NOW)
        self.assertTrue(rows)
        self.assertNotIn("Draw", {r["team"] for r in rows})

    def test_pinnacle_is_preferred_reference(self):
        rows = ep.evaluate(SOC_EVENT, SOC_OFFER, "SOCCER", CFG, CURVES, NOW)
        self.assertTrue(all(r["fair_source"] == "pinnacle" for r in rows))

    def test_exchanges_used_when_pinnacle_missing(self):
        rows = ep.evaluate(NFL_EVENT, NFL_OFFER, "NFL", CFG, CURVES, NOW)
        self.assertTrue(rows)
        self.assertTrue(all(r["fair_source"].startswith("exchanges (2)") for r in rows))

    def test_ev_uses_fair_probability_plus_payout(self):
        rows = {(r["book"], r["team"]): r for r in ep.evaluate(NFL_EVENT, NFL_OFFER, "NFL", CFG, CURVES, NOW)}
        r = rows[("bet365", "Falcons")]
        self.assertAlmostEqual(r["ev"], r["decimal"] * (r["fair_p"] + r["extra"]) - 1, places=3)
        self.assertGreater(r["ev"], r["ev_without_payout"])
        # FanDuel has no NFL payout rule in the config, so it produces no NFL rows.
        self.assertNotIn(("fanduel", "Falcons"), rows)

    def test_started_and_stale_quotes_are_blocked(self):
        late = datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc)
        rows = ep.evaluate(NFL_EVENT, NFL_OFFER, "NFL", CFG, CURVES, late)
        self.assertTrue(all(not r["play"] for r in rows))
        self.assertTrue(all({"STARTED", "STALE_QUOTE"} <= set(r["flags"]) for r in rows))

    def test_wrong_number_of_selections_is_skipped(self):
        self.assertEqual(ep.evaluate(NFL_EVENT, NFL_OFFER, "SOCCER", CFG, CURVES, NOW), [])


class Writing(unittest.TestCase):
    def test_new_keys_and_history_dedupe(self):
        rows = ep.evaluate(NFL_EVENT, NFL_OFFER, "NFL", CFG, CURVES, NOW)
        for r in rows:
            r["play"] = True
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ep, "LIVE", Path(tmp)):
            result = {"generated_utc": NOW.isoformat(), "events": {}, "errors": [], "rows": rows}
            self.assertEqual(len(ep.write(dict(result))), len(rows))
            self.assertEqual(ep.write(dict(result)), [])
            lines = (Path(tmp) / "history.csv").read_text().strip().splitlines()
            self.assertEqual(len(lines), 1 + len(rows))


if __name__ == "__main__":
    unittest.main()
