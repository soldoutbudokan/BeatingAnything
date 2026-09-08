"""Observe a public odds page without substituting books or spoofing a region.

This adapter does not certify the page's odds as executable at FanDuel. The
observer timestamp proves when the response was received, not price freshness.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


class NextData(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__': self.active=True
    def handle_endtag(self,tag):
        if tag == 'script': self.active=False
    def handle_data(self,data):
        if self.active: self.parts.append(data)


def decimal(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or abs(value)<100:
        raise ValueError('Invalid American price')
    result = 1+value/100 if value>0 else 1+100/-value
    if not 1<result<1000: raise ValueError('Invalid decimal price')
    return result


def parse_page(html, observed_at, source_uri):
    parser = NextData(); parser.feed(html)
    if not parser.parts: raise ValueError('Expected structured public page data absent')
    props = json.loads(''.join(parser.parts))['props']['pageProps']
    books = Counter(); quotes=[]; games=set(); seen=set()
    for table in props.get('oddsTables',[]):
        for row in table.get('oddsTableModel',{}).get('gameRows',[]):
            game = row.get('gameView',{}); event = game.get('gameId')
            if event is not None: games.add(event)
            for offer in row.get('oddsViews',[]):
                if offer.get('viewType') != 'MoneyLineDataOpeningAndLatestOddsDataView': continue
                book = offer.get('sportsbook','unknown'); books[book]+=1
                if book != 'fanduel' or event in seen: continue
                line = offer.get('currentLine') or {}
                try: home,away=decimal(line.get('homeOdds')),decimal(line.get('awayOdds'))
                except ValueError: continue
                seen.add(event)
                # Only observed source status 6 corresponds to pregame. Unknown states block.
                pregame = str(game.get('status')) == '6'
                quotes.append({
                    'event_id':f'sbr:{event}', 'sport':'MLB','bookmaker':'FanDuel','market':'moneyline',
                    'home_team':game['homeTeam']['fullName'],'away_team':game['awayTeam']['fullName'],
                    'starts_at':game['startDate'],'observed_at':observed_at,
                    'status':'open' if pregame else 'closed','is_live':not pregame,
                    'decimal_home':home,'decimal_away':away,
                    'source':{'uri':source_uri,'provider':'SportsbookReview public page',
                              'verified':False,'verification_method':'Unverified aggregator; no bookmaker quote timestamp',
                              'historical':False,'synthetic':False},
                })
    status = {'observed_at':observed_at,'source_uri':source_uri,
              'response_sha256':hashlib.sha256(html.encode()).hexdigest(),
              'country_code':props.get('countryCode'),'region_code':props.get('regionCode'),
              'events':len(games),'bookmaker_rows':dict(sorted(books.items())),
              'fanduel_quotes':len(quotes),'verified_fanduel_quotes':0,
              'status':'blocked','betting_alerts_enabled':False,
              'reason':'fanduel_absent_from_public_response' if not quotes else 'aggregator_quotes_require_direct_verification',
              'research_status':'unproven', 'notifications_sent':0}
    return quotes,status


def collect(date, output, source_file=None):
    root = Path(output); root.mkdir(parents=True,exist_ok=True)
    uri = f'https://www.sportsbookreview.com/betting-odds/mlb-baseball/?date={date}'
    try:
        if source_file:
            html=Path(source_file).read_text()
        else:
            with urlopen(Request(uri,headers={'User-Agent':'BeatingAnything-research/0.1'}),timeout=30) as response:
                html=response.read(12*1024*1024).decode('utf-8')
        now=datetime.now(timezone.utc).isoformat()
        quotes,status=parse_page(html,now,uri)
        if source_file:
            status['reason']='offline_fixture_not_live'; status['offline_fixture']=True
            for quote in quotes:
                quote['source']['historical']=True
    except Exception as exc:
        quotes=[]
        status={'observed_at':datetime.now(timezone.utc).isoformat(),'source_uri':uri,
                'status':'blocked','reason':'source_unavailable','error_type':type(exc).__name__,
                'fanduel_quotes':0,'verified_fanduel_quotes':0,'betting_alerts_enabled':False,
                'research_status':'unproven','notifications_sent':0}
    (root/'live-status.json').write_text(json.dumps(status,indent=2)+'\n')
    (root/'quotes.json').write_text(json.dumps(quotes,indent=2)+'\n')
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--output',default='state')
    parser.add_argument('--source-file',help='Offline parser check; never treated as live')
    args=parser.parse_args()
    datetime.strptime(args.date,'%Y-%m-%d')
    print(json.dumps(collect(args.date,args.output,args.source_file),indent=2))


if __name__=='__main__': main()
