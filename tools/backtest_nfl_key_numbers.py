#!/usr/bin/env python3
"""Fixed key-margin spread backtest; prices freeze before evaluation outcomes.

Run with PYTHONPATH=state/runtime/nfl-audit-lib from the repository root.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from explore_nfl_prices import load as load_pairs, fair, excess, PIN as ODDS_PIN

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nfl-key-number"
GAMES = RAW / "games.csv"
GAMES_PIN = "0c34a519753ada6b5b37f5e8be246021813484adb15ae7c067af9c3aca534d2d"
GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/55430687825bbdd8640d639b9aaaa0d886778e95/data/games.csv"
CARD = ROOT / "docs/nfl-key-number-declaration-2026-09-13.md"
CARD_PIN = "5c30b68015a676fab1c38376d202419a6576d4b2c3fbbc8e5054384360deb953"
FREEZE = RAW / "frozen-selection.json"
OUT = ROOT / "reports/nfl-key-number-backtest-2026-09-13.json"
NAMES = dict(zip([
    "Arizona Cardinals","Atlanta Falcons","Baltimore Ravens","Buffalo Bills","Carolina Panthers","Chicago Bears",
    "Cincinnati Bengals","Cleveland Browns","Dallas Cowboys","Denver Broncos","Detroit Lions","Green Bay Packers",
    "Houston Texans","Indianapolis Colts","Jacksonville Jaguars","Kansas City Chiefs","Las Vegas Raiders",
    "Los Angeles Chargers","Los Angeles Rams","Miami Dolphins","Minnesota Vikings","New England Patriots",
    "New Orleans Saints","New York Giants","New York Jets","Philadelphia Eagles","Pittsburgh Steelers",
    "San Francisco 49ers","Seattle Seahawks","Tampa Bay Buccaneers","Tennessee Titans","Washington Commanders"],
    ["ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN","DET","GB","HOU","IND","JAX","KC","LV","LAC","LA",
     "MIA","MIN","NE","NO","NYG","NYJ","PHI","PIT","SF","SEA","TB","TEN","WAS"]))


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def wilson(k,n):
    z=1.959963984540054
    p=k/n
    denom=1+z*z/n
    mid=(p+z*z/(2*n))/denom
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return [mid-half,mid+half]


def bridge(fd_line, pin_line):
    """One-point improvement, both half-points, crossing one exact key margin."""
    if not math.isclose(fd_line-pin_line,1,abs_tol=1e-9):
        return None
    midpoint=(fd_line+pin_line)/2
    if midpoint not in {-7.,-3.,3.,7.}:
        return None
    return int(abs(midpoint))


def calibration_and_metadata():
    assert sha(GAMES)==GAMES_PIN
    counts={3:[0,0],7:[0,0]}
    fixtures=[]
    # 2025 score values are never accessed during preparation. Only prior-season
    # fields calibrate the mass; 2025 rows supply fixture metadata at this stage.
    with GAMES.open() as f:
        for r in csv.DictReader(f):
            year=int(r['season'])
            if 2010<=year<=2024 and r['game_type']=='REG' and r['result'] and r['spread_line']:
                line=float(r['spread_line'])
                if line==0:
                    continue
                favorite_margin=float(r['result'])*(1 if line>0 else -1)
                for key in counts:
                    if key-1<=abs(line)<=key+1:
                        counts[key][1]+=1
                        counts[key][0]+=int(favorite_margin==key)
            elif year==2025 and r['game_type'] in {'REG','WC','DIV','CON','SB'}:
                start=datetime.fromisoformat(r['gameday']+'T'+r['gametime']).replace(
                    tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).replace(tzinfo=None)
                fixtures.append({k:r[k] for k in ['game_id','home_team','away_team','game_type','week']}|{'start':start})
    calibrated={str(key):{'hits':hits,'games':n,'mass':hits/n,'wilson_95':wilson(hits,n)}
                for key,(hits,n) in counts.items()}
    assert all(x['games']>=200 for x in calibrated.values())
    return calibrated,fixtures


def stamp(t):
    return t.replace(tzinfo=timezone.utc).isoformat()


def prepare():
    if FREEZE.exists():
        raise FileExistsError('Selection is already frozen; do not overwrite')
    assert sha(CARD)==CARD_PIN
    calibrated,fixtures=calibration_and_metadata()
    pairs,rejected,nrows,boundaries=load_pairs()
    counts=Counter()
    mapped={}
    for event,start in boundaries.items():
        examples=[x for x in pairs.values() if x['event']==event]
        if not examples:
            continue
        home,away=examples[0]['home'],examples[0]['away']
        if home not in NAMES or away not in NAMES:
            continue
        found=[f for f in fixtures if f['home_team']==NAMES[home] and f['away_team']==NAMES[away]
               and abs((f['start']-start).total_seconds())<=900]
        if len(found)==1:
            mapped[event]=found[0]|{'boundary':min(start,found[0]['start'])}
    counts['mapped_events']=len(mapped)
    comparisons=[]
    for (event,captured,book,market),p in pairs.items():
        if book!='fanduel' or market!='spreads' or event not in mapped:
            continue
        fixture=mapped[event]
        lead=(fixture['boundary']-captured).total_seconds()
        if not 3600<=lead<=86400:
            continue
        counts['fanduel_entry_pairs']+=1
        ref=pairs.get((event,captured,'pinnacle','spreads'))
        if ref is None or any(p[k]!=ref[k] for k in ['home','away','sides']):
            counts['missing_reference_or_identity_mismatch']+=1
            continue
        prop,power=fair(ref['prices'])
        for side in [0,1]:
            fdline=p['line']*(1 if side==0 else -1)
            pinline=ref['line']*(1 if side==0 else -1)
            key=bridge(fdline,pinline)
            if key is None:
                continue
            counts['cross_key_comparisons']+=1
            price=p['prices'][side]
            if not 1.2<=price<=6:
                continue
            mass=calibrated[str(key)]['mass']
            lower=calibrated[str(key)]['wilson_95'][0]
            probs=[prop[side]+mass,power[side]+mass]
            if not all(0<=x<=1 for x in probs):
                counts['invalid_bridged_probability']+=1
                continue
            ev=min(excess(price,prob) for prob in probs)
            ev_lower=min(excess(price,prob+lower) for prob in [prop[side],power[side]])
            row={'event_id':event,'game_id':fixture['game_id'],'game_type':fixture['game_type'],
                'week':int(fixture['week']),'team':p['sides'][side],'team_code':NAMES[p['sides'][side]],
                'home':p['home'],'away':p['away'],'side_index':side,'key':key,
                'fanduel_line':fdline,'pinnacle_line':pinline,'decimal_price':price,
                'pinnacle_decimal_prices':ref['prices'],'captured_at':stamp(captured),
                'fanduel_updated_at':stamp(p['update']),'pinnacle_updated_at':stamp(ref['update']),
                'boundary':stamp(fixture['boundary']),'scheduled_kickoff':stamp(fixture['start']),
                'lead_seconds':lead,'historical_margin_mass':mass,
                'reference_probabilities':{'proportional':prop[side],'power':power[side]},
                'reference_expected_return':ev,'wilson_lower_mass_expected_return':ev_lower,
                'qualifies':ev>=.03 and ev_lower>0}
            comparisons.append(row)
    selected={}
    for row in sorted((r for r in comparisons if r['qualifies']),key=lambda x:(x['captured_at'],-x['reference_expected_return'],x['team'])):
        selected.setdefault(row['game_id'],row.copy())
    for row in selected.values():
        later=[]
        boundary=datetime.fromisoformat(row['boundary']).replace(tzinfo=None)
        captured=datetime.fromisoformat(row['captured_at']).replace(tzinfo=None)
        for (event,t,book,market),p in pairs.items():
            if event!=row['event_id'] or book!='pinnacle' or market!='spreads' or not captured<t<boundary:
                continue
            if (boundary-t).total_seconds()>1800:
                continue
            side=row['side_index']
            line=p['line']*(1 if side==0 else -1)
            k=bridge(row['fanduel_line'],line)
            if line!=row['fanduel_line'] and k is None:
                continue
            mass=0 if line==row['fanduel_line'] else calibrated[str(k)]['mass']
            prop,power=fair(p['prices'])
            if max(prop[side],power[side])+mass>1:
                continue
            later.append({'captured_at':stamp(t),'pinnacle_line':line,
                'lead_seconds':(boundary-t).total_seconds(),
                'reference_expected_return':min(excess(row['decimal_price'],q[side]+mass) for q in [prop,power]),
                'uses_margin_bridge':bool(mass)})
        row['near_start_reference']=max(later,key=lambda r:r['captured_at']) if later else None
    frozen={'prepared_at':now(),'declaration_sha256':CARD_PIN,'odds_sha256':ODDS_PIN,
        'games_sha256':GAMES_PIN,'games_url':GAMES_URL,'calibration':calibrated,
        'calibration_years':[2010,2024],'evaluation_season':2025,'price_pair_rejections':dict(rejected),
        'counts':dict(counts),'comparisons':comparisons,'selected':list(selected.values()),
        'evaluation_outcomes_used_for_selection':False}
    dump(FREEZE,frozen)
    dump(RAW/'freeze-hash.json',{'sha256':sha(FREEZE),'prepared_at':frozen['prepared_at']})
    print(json.dumps({'calibration':calibrated,'counts':dict(counts),'qualifying_snapshots':sum(r['qualifies'] for r in comparisons),
                      'selected_games':len(selected),'selection_sha256':sha(FREEZE)},indent=2))


def settle():
    assert sha(FREEZE)==json.loads((RAW/'freeze-hash.json').read_text())['sha256']
    frozen=json.loads(FREEZE.read_text())
    assert sha(GAMES)==GAMES_PIN and sha(CARD)==CARD_PIN
    ids={x['game_id'] for x in frozen['selected']}
    outcomes={}
    with GAMES.open() as f:
        for r in csv.DictReader(f):
            if r['game_id'] in ids:
                assert int(r['season'])==2025
                outcomes[r['game_id']]=r
    settled=[]
    for row in frozen['selected']:
        r=outcomes.get(row['game_id'])
        if r is None or not r['home_score'] or not r['away_score']:
            settled.append(row|{'settlement':'missing','net_profit_units':None})
            continue
        margin=float(r['home_score'])-float(r['away_score'])
        team_margin=margin if row['side_index']==0 else -margin
        adjusted=team_margin+row['fanduel_line']
        assert adjusted!=0, 'Half-point line unexpectedly pushes'
        win=adjusted>0
        net=.98*(row['decimal_price']-1) if win else -1.
        settled.append(row|{'home_score':int(r['home_score']),'away_score':int(r['away_score']),
            'team_margin':team_margin,'adjusted_margin':adjusted,'settlement':'win' if win else 'loss','net_profit_units':net})
    values=np.array([r['net_profit_units'] for r in settled if r['net_profit_units'] is not None])
    rng=np.random.default_rng(20260913)
    draws=[float(rng.choice(values,len(values),replace=True).mean()) for _ in range(5000)] if len(values) else []
    interval=np.quantile(draws,[.025,.975]).tolist() if draws else None
    cumulative=np.r_[0,np.cumsum(values)]
    summary={'selected_games':len(settled),'settled_games':len(values),
        'wins':sum(r['settlement']=='win' for r in settled),'losses':sum(r['settlement']=='loss' for r in settled),
        'missing_settlements':sum(r['settlement']=='missing' for r in settled),
        'net_profit_units':float(values.sum()),'roi':float(values.mean()) if len(values) else None,
        'bootstrap_95_roi_interval':interval,'maximum_drawdown_units':float((np.maximum.accumulate(cumulative)-cumulative).max()),
        'with_near_start_reference':sum(r['near_start_reference'] is not None for r in settled),
        'decision':'unresolved_fewer_than_50_settled_games' if len(values)<50 else
            'exploratory_positive_candidate' if values.mean()>0 and interval[0]>0 else 'fails_positive_backtest_gate',
        'verified_edge':False}
    report=frozen|{'evaluated_at':now(),'frozen_selection_sha256':sha(FREEZE),'summary':summary,'settled':settled,
        'limitations':['New rule on an already-inspected season: not an untouched holdout.',
            'Historical favorite-margin mass is a transported closing-spread proxy, not known conditional probability at the current Pinnacle quote.',
            'Archived freshness does not establish fill, limits or original collector receipt; historical jurisdiction-specific settlement rules not reconstructed.',
            'Near-start references use the conservative archive/scheduled boundary and may use the same margin bridge; not verified CLV.',
            'Bootstrap omits model-selection and calibration uncertainty; no independent or forward FanDuel validation.']}
    dump(OUT,report)
    print(json.dumps(summary,indent=2))


def self_test():
    assert bridge(-2.5,-3.5)==3 and bridge(3.5,2.5)==3
    assert bridge(-6.5,-7.5)==7 and bridge(7.5,6.5)==7
    assert bridge(2.5,3.5) is None and bridge(4.5,3.5) is None
    assert bridge(3,2) is None
    assert .98*(2.-1)==.98 and excess(2.,.55)>0
    print('Eight bridge/payout checks passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--settle',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.prepare and args.settle:
        parser.error('Freeze selection and settle in separate calls')
    if args.self_test:
        self_test()
    if args.prepare:
        prepare()
    if args.settle:
        settle()
