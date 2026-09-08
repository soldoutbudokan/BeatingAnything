import json
import unittest
from beating.collect import parse_page


class CollectorTests(unittest.TestCase):
    def test_other_book_not_substituted_and_aggregator_never_verified(self):
        def page(book):
            data={'props':{'pageProps':{'regionCode':'on','countryCode':'ca','oddsTables':[
                {'oddsTableModel':{'gameRows':[{'gameView':{'gameId':1,'status':'6',
                    'homeTeam':{'fullName':'Home'},'awayTeam':{'fullName':'Away'},
                    'startDate':'2030-01-01T20:00:00Z'},'oddsViews':[{'sportsbook':book,
                    'viewType':'MoneyLineDataOpeningAndLatestOddsDataView',
                    'currentLine':{'homeOdds':-110,'awayOdds':-110}}]}]}}]}}}
            return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>'
        q,s=parse_page(page('bet365'),'2030-01-01T19:00:00Z','https://example.invalid')
        self.assertEqual(q,[]); self.assertEqual(s['reason'],'fanduel_absent_from_public_response')
        q,s=parse_page(page('fanduel'),'2030-01-01T19:00:00Z','https://example.invalid')
        self.assertEqual(len(q),1); self.assertFalse(q[0]['source']['verified'])
        self.assertFalse(s['betting_alerts_enabled'])


if __name__=='__main__': unittest.main()
