import json
import unittest

from beating.covers import parse_page


class CoversObservationTests(unittest.TestCase):
    def fixture(self, *, starts="9-8-2026T18:35:00-04:00", book="FanDuel", official_status="Preview", extra="", updated="4:49 PM"):
        event = {"@type": "SportsEvent", "identifier": "Cleveland vs Baltimore-123",
            "eventStatus": "https://schema.org/EventScheduled", "startDate": starts,
            "awayTeam": {"name": "CLE Guardians"}, "homeTeam": {"name": "BAL Orioles"}}
        page = f'''<html><script type="application/ld+json">{json.dumps(event)}</script>
        <div class="__updatedDate">Last updated Sep 08, 2026, {updated} ET</div>
        <table id="moneyline-table"><tr><td data-book="{book}" data-game="123" data-type="spread" data-date="1788802342">
        <div class="away-cell"><a class="odds-cta moneyline"><span class="American __american">+102</span></a></div>
        <div class="home-cell"><a class="odds-cta moneyline"><span class="American __american">-120</span></a></div>
        </td></tr>{extra}</table></html>'''
        schedule = {"dates": [{"date": "2026-09-08", "games": [{
            "gamePk": 555, "officialDate": "2026-09-08", "gameDate": "2026-09-08T22:35:00Z",
            "gameType": "R", "doubleHeader": "N", "status": {"abstractGameState": official_status},
            "teams": {"away": {"team": {"id": 114, "name": "Cleveland Guardians"}},
                      "home": {"team": {"id": 110, "name": "Baltimore Orioles"}}}}]}]}
        return page, schedule

    def parse(self, **kwargs):
        page, schedule = self.fixture(**kwargs)
        return parse_page(page, "2026-09-08T20:49:58+00:00", "https://www.covers.com/sport/baseball/mlb/odds", schedule)

    def test_verified_identity_does_not_certify_execution(self):
        quotes, status = self.parse()
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["event_id"], "mlb:555")
        self.assertEqual(quotes[0]["decimal_away"], 2.02)
        self.assertAlmostEqual(quotes[0]["decimal_home"], 1 + 100 / 120)
        self.assertFalse(quotes[0]["source"]["verified"])
        self.assertFalse(status["betting_alerts_enabled"])

    def test_old_line_change_time_does_not_mean_old_observation(self):
        quotes, _ = self.parse()
        self.assertEqual(len(quotes), 1)
        self.assertTrue(quotes[0]["source"]["source_line_time_utc"].startswith("2026-09-07"))

    def test_other_book_cannot_be_relabelled_fanduel(self):
        quotes, _ = self.parse(book="DraftKings")
        self.assertEqual(quotes, [])

    def test_inplay_and_schedule_mismatch_block_observations(self):
        for kwargs in ({"official_status": "Live"}, {"starts": "9-8-2026T18:45:00-04:00"}, {"starts": "9-8-2026T15:35:00-04:00"}):
            quotes, _ = self.parse(**kwargs)
            self.assertEqual(quotes, [])

    def test_old_page_timestamp_blocks_observations(self):
        quotes, status = self.parse(updated="3:49 PM")
        self.assertEqual(quotes, [])
        self.assertIn("missing_or_old_page_update_time", status["skipped"])

    def test_missing_metadata_is_not_guessed_from_row_position(self):
        extra = '<tr><td data-book="FanDuel" data-game="999">tomorrow</td></tr>'
        quotes, status = self.parse(extra=extra)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(status["skipped"]["missing_structured_event_metadata"], 1)


if __name__ == "__main__":
    unittest.main()
