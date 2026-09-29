"""Fixed exploratory PointsBet Ontario price diagnostics; no outcomes or wagers.

Run from the repo root. Sources are pinned in the adjacent report manifest.
Raw files stay uncommitted. Missing source clocks exclude every CSV comparison
from the strict cohort; arithmetic diagnostics are explicitly conditional.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/pointsbet-alt-2026-09-29'
OUT = ROOT / 'reports'
PREFIX = 'pointsbet-nfl-alternates-2026-09-29'
MAP = {
    'Point Spread': 'spread', 'spread': 'spread',
    'Pick Your Own Line': 'spread', 'Total': 'total', 'total': 'total',
    'Alternate Totals': 'total',
    'Passing Yards': 'passing_yards', 'Quarterback To Get': 'passing_yards',
    'Quarterback Passing Touchdowns': 'passing_tds', 'TD Passes': 'passing_tds',
    'Alternate Passing TDs': 'passing_tds',
    'Pass Attempts': 'pass_attempts', 'Alternate Pass Attempts': 'pass_attempts',
    'Quarterback Pass Completions': 'completions', 'Completions': 'completions',
    'Alternate Pass Completions': 'completions',
    'Rushing Yards': 'rushing_yards', 'Running Back To Get': 'rushing_yards',
    'Rushing Attempts Over/Under': 'rush_attempts',
    'Alternate Rush Attempts': 'rush_attempts',
    'Receiving Yards': 'receiving_yards', 'Receiver To Get': 'receiving_yards',
    'Player Receptions': 'receptions', 'Receptions': 'receptions',
    'Alternate Receptions': 'receptions',
}
ALT = {x for x in MAP if x.startswith('Alternate') or 'To Get' in x} | {'Pick Your Own Line'}


def halfpoint(x):
    return math.isfinite(x) and abs(x % 1 - .5) < 1e-8


def devig(a, b):
    q, r = 1 / a, 1 / b
    prop = q / (q + r)
    lo, hi = 0., 128.
    for _ in range(100):
        k = (lo + hi) / 2
        if q ** k + r ** k > 1:
            lo = k
        else:
            hi = k
    return prop, q ** ((lo + hi) / 2)


def ev(p, d):
    return p * (1 + .98 * (d - 1)) - 1


def groupkey(r):
    line = r['point']
    if r['family'] == 'spread' and r['side'] == 'away':
        line = -line
    return r['date'], r['event'], r['family'], r['player'], line


def read_csv(name, book):
    original = list(csv.DictReader((RAW / name).open()))
    nfl = [r for r in original if r['League'] == 'NFL']
    rows = []
    for n, r in enumerate(nfl):
        family = MAP.get(r['Category'])
        if not family:
            continue
        try:
            point, price = float(r['Points']), float(r[f'{book} Decimal Odds'])
        except (ValueError, KeyError):
            continue
        if not (math.isfinite(price) and price > 1 and math.isfinite(point)):
            continue
        side = r['Side'].lower() if family == 'spread' else r['Designation'].lower()
        if side not in ({'home', 'away'} if family == 'spread' else {'over', 'under'}):
            continue
        rows.append(dict(date=r['Date'], event=r['Teams'], family=family,
                         player=r['Name'] if family not in {'spread', 'total'} else '',
                         point=point, price=price, side=side,
                         alternate=r['Category'] in ALT, category=r['Category'],
                         source=name, source_nfl_row=n + 1))
    return rows, dict(file=name, nfl_rows=len(nfl),
                     nfl_events=len({(r['Date'], r['Teams']) for r in nfl}),
                     categories=dict(Counter(r['Category'] for r in nfl)),
                     supported_rows=len(rows),
                     clock_columns=[x for x in original[0] if 'time' in x.lower() or 'update' in x.lower()])


def pairs(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[groupkey(r)].append(r)
    result, rejected = {}, Counter()
    for key, values in groups.items():
        sides = {'home', 'away'} if key[2] == 'spread' else {'over', 'under'}
        if len(values) != 2 or {v['side'] for v in values} != sides:
            rejected['missing_or_duplicate_side'] += 1
            continue
        if not halfpoint(key[-1]):
            rejected['integer_line'] += 1
            continue
        if any(not 1.2 <= v['price'] <= 6 for v in values):
            rejected['price_range'] += 1
            continue
        overround = sum(1 / v['price'] for v in values) - 1
        if not -1e-10 <= overround <= .12:
            rejected['overround'] += 1
            continue
        result[key] = {v['side']: v for v in values}
    return result, dict(rejected)


def compare(pb, pn, snapshot):
    reference, rejects = pairs(pn)
    mains = {groupkey(r) for r in pb if not r['alternate']}
    pb_group = defaultdict(list)
    for r in pb:
        pb_group[groupkey(r) + (r['side'],)].append(r)
    out, exclusions = [], Counter()
    for key, values in pb_group.items():
        if len({r['price'] for r in values}) != 1:
            exclusions['conflicting_duplicate_target'] += 1
            continue
        r = dict(values[0])
        r['alternate'] = any(x['alternate'] for x in values)
        r['distinct_alternate'] = r['alternate'] and key[:-1] not in mains
        if not halfpoint(r['point']):
            exclusions['integer_target'] += 1
            continue
        if not 1.2 <= r['price'] <= 6:
            exclusions['target_price_range'] += 1
            continue
        pair = reference.get(groupkey(r))
        if not pair:
            exclusions['no_eligible_exact_reference_pair'] += 1
            continue
        a = pair[r['side']]
        b = next(v for k, v in pair.items() if k != r['side'])
        p, power = devig(a['price'], b['price'])
        r.update(snapshot=snapshot, reference_price=a['price'], reference_opposite_price=b['price'],
                 proportional_p=p, power_p=power, proportional_ev=ev(p, r['price']),
                 power_ev=ev(power, r['price']),
                 min_ev=min(ev(p, r['price']), ev(power, r['price'])),
                 strict_eligible=False,
                 timing='unknown; snapshot label is source version, not a capture clock',
                 identity='literal abbreviated names only' if r['player'] else 'literal fixture label/date only')
        r['clears_3pct_both'] = r['min_ev'] >= .03
        out.append(r)
    return out, dict(reference_pair_count=len(reference), reference_exclusions=rejects,
                     target_exclusions=dict(exclusions))


def raw_rows(d):
    rows, excluded = [], Counter()
    for m in d['fixedOddsMarkets']:
        family = MAP.get(m['eventClass'])
        if not family:
            continue
        for o in m['outcomes']:
            if not m.get('isOpenForBetting') or not o.get('isOpenForBetting') or o.get('isHidden'):
                excluded['closed_or_hidden'] += 1
                continue
            name = o['name']
            side = o['side'].lower() if family == 'spread' else ('under' if 'Under ' in name else 'over')
            player = o.get('playerId') or ''
            if family not in {'total', 'spread'} and not player:
                excluded['missing_player_id'] += 1
                continue
            rows.append(dict(date=d['startsAt'][:10], event=d['name'], family=family,
                             player=player, side=side, point=float(o['points']),
                             price=float(o['price']), category=m['eventClass'],
                             alternate=m['eventClass'] in ALT, name=name,
                             selection_id=o['optionId'],
                             market_timestamp=m.get('timestamp'),
                             price_last_updated=o.get('priceLastUpdated')))
    return rows, dict(excluded)


def raw_diagnostics(d, rows):
    group = defaultdict(list)
    for r in rows:
        if halfpoint(r['point']):
            group[(r['family'], r['player'], r['side'])].append(r)
    inversions, duplicates = [], []
    comparisons = 0
    for key, values in group.items():
        for a, b in itertools.combinations(values, 2):
            if a['point'] == b['point']:
                if a['price'] != b['price']:
                    duplicates.append([a, b])
                continue
            comparisons += 1
            low, high = sorted([a, b], key=lambda r: r['point'])
            easy, hard = (low, high) if key[2] == 'over' else (high, low)
            if easy['price'] > hard['price'] + 1e-10:
                inversions.append(dict(easy=easy, hard=hard))
    coverage = []
    for a, b in itertools.combinations([r for r in rows if halfpoint(r['point'])], 2):
        if (a['family'], a['player']) != (b['family'], b['player']) or a['side'] == b['side']:
            continue
        if a['family'] == 'spread':
            covers = a['point'] + b['point'] >= 0
        else:
            over, under = (a, b) if a['side'] == 'over' else (b, a)
            covers = over['point'] <= under['point']
        if covers:
            da, db = (1 + .98 * (r['price'] - 1) for r in (a, b))
            coverage.append(dict(a=a, b=b, minimum_roi_after_haircut=1 / (1 / da + 1 / db) - 1,
                                 minimum_roi_gross=1 / (1 / a['price'] + 1 / b['price']) - 1))
    ladder = [r for r in rows if r['category'] == 'Pick Your Own Line']
    # A book may omit its featured line from the alternate tab. Include that
    # exact raw main pair so crossing 3 is not accidentally dropped.
    paired, _ = pairs([r for r in rows if r['family'] == 'spread'])
    probs, spreads = {}, []
    for key, pair in sorted(paired.items()):
        home, away = pair['home'], pair['away']
        p, pw = devig(home['price'], away['price'])
        probs[home['point']] = p, pw
        spreads.append(dict(home_line=home['point'], home_price=home['price'], away_price=away['price'],
                            home_proportional_p=p, home_power_p=pw))
    jumps = []
    for margin in (3, 7, -3, -7):
        easier, harder = -margin + .5, -margin - .5
        if easier in probs and harder in probs:
            jumps.append(dict(home_winning_margin=margin,
                              proportional_mass=probs[easier][0] - probs[harder][0],
                              power_mass=probs[easier][1] - probs[harder][1],
                              easier_line=easier, harder_line=harder))
    best = max(coverage, key=lambda r: r['minimum_roi_after_haircut']) if coverage else None
    return dict(market_count=len(d['fixedOddsMarkets']), supported_rows=len(rows),
                spread_alt_outcomes=len(ladder),
                total_alt_outcomes=sum(r['category'] == 'Alternate Totals' for r in rows),
                nested_price_comparisons=comparisons, strict_price_reversals=inversions,
                identical_contract_price_differences=duplicates,
                covering_pair_count=len(coverage),
                positive_coverage_count=sum(r['minimum_roi_after_haircut'] > 0 for r in coverage),
                best_coverage=best, key_number_masses=jumps, paired_spread_ladder=spreads,
                raw_event_timestamp=datetime.fromtimestamp(d['timestamp'], timezone.utc).isoformat(),
                source_start=d['startsAt'],
                source_live=d['isLive'],
                overtime_flag_values=list({m.get('includesOverTime') for m in d['fixedOddsMarkets']}),
                caveat='Conditional on raw contract semantics. All includesOverTime fields are false and periods null; original jurisdictional rules/capture clocks not verified.')


def summarize(rows):
    return dict(comparisons=len(rows), events=len({(r['date'], r['event']) for r in rows}),
                clears_3pct_both=sum(r['clears_3pct_both'] for r in rows),
                positive_both=sum(r['min_ev'] > 0 for r in rows),
                best_min_ev=max((r['min_ev'] for r in rows), default=None),
                worst_min_ev=min((r['min_ev'] for r in rows), default=None),
                by_family=dict(Counter(r['family'] for r in rows)))


def run():
    d = json.loads((RAW / 'pointsbet_raw_buf_mia.json').read_text())
    raw, raw_exclusions = raw_rows(d)
    inv, csv_rows, filters = [], [], {}
    for snapshot in ['sep12', 'sep30']:
        pb, pbi = read_csv(f'{snapshot}_PointsBetGigaDump.csv', 'PB')
        pn, pni = read_csv(f'{snapshot}_PinnacleGigaDump.csv', 'PN')
        inv.extend([pbi, pni])
        rows, filt = compare(pb, pn, snapshot)
        csv_rows.extend(rows)
        filters[snapshot] = filt
    pn12, _ = read_csv('sep12_PinnacleGigaDump.csv', 'PN')
    # Raw event is September 13 UTC / September 12 Toronto. Only game markets
    # are matched here; no abbreviated player identities are manufactured.
    raw_games = [dict(r, date='2024-09-12', event='BUF(away) vs MIA(home)', source='pointsbet_raw_buf_mia.json')
                 for r in raw if r['family'] in {'spread', 'total'}]
    cross_raw, raw_filters = compare(raw_games, pn12, 'raw_event_vs_sep12_csv_unknown_clock_gap')
    distinct = [r for r in csv_rows if r['distinct_alternate']]
    result = dict(status='historical conditional diagnostics only; hypothesis unresolved',
                  strict_comparisons=0,
                  strict_exclusion='CSV files omit observation/update clocks, original IDs and settlement rules. Raw event has no verified collector receipt clock; no same-time raw reference was recovered.',
                  raw=raw_diagnostics(d, raw), raw_exclusions=raw_exclusions,
                  inventory=inv, filters=filters,
                  csv_summary=summarize(csv_rows),
                  csv_distinct_alternates_summary=summarize(distinct),
                  csv_distinct_alternates_by_snapshot={s:summarize([r for r in distinct if r['snapshot']==s]) for s in ['sep12','sep30']},
                  csv_comparisons=sorted(csv_rows, key=lambda r:r['min_ev'], reverse=True),
                  raw_to_csv_summary=summarize(cross_raw),
                  raw_to_csv_distinct_alternates_summary=summarize([r for r in cross_raw if r['distinct_alternate']]),
                  raw_to_csv_filters=raw_filters,
                  raw_to_csv_comparisons=sorted(cross_raw, key=lambda r:r['min_ev'], reverse=True),
                  no_game_outcomes_read=True, realized_roi=None,
                  declaration_sha256=hashlib.sha256((ROOT/'docs/pointsbet-nfl-alternate-test-declaration-2026-09-29.md').read_bytes()).hexdigest())
    OUT.mkdir(exist_ok=True)
    (OUT / f'{PREFIX}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k] for k in ['status','strict_comparisons','csv_summary','csv_distinct_alternates_summary','csv_distinct_alternates_by_snapshot','raw_to_csv_summary']}, indent=2))
    print('Raw key jumps:', result['raw']['key_number_masses'])
    print('Structural:', {k:result['raw'][k] for k in ['nested_price_comparisons','covering_pair_count','positive_coverage_count']})
    print('Strict price reversals:',len(result['raw']['strict_price_reversals']))
    print('Duplicate contract price differences:',len(result['raw']['identical_contract_price_differences']))
    print('Best coverage:', result['raw']['best_coverage']['minimum_roi_after_haircut'])


def verify_sources(allow_download=False):
    manifest=json.loads((OUT/f'{PREFIX}-sources.json').read_text())
    RAW.mkdir(parents=True,exist_ok=True)
    for r in manifest['files']:
        path=RAW/r['local_name']
        if path.exists():
            data=path.read_bytes()
        elif allow_download:
            req=Request(r['url'],headers={'User-Agent':'BeatingAnything-source-reproduction/1.0'})
            with urlopen(req,timeout=30) as response:
                data=response.read()
        else:
            raise FileNotFoundError(str(path)+'; use --download to recover pinned public sources')
        sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if sha!=r['git_blob_sha'] or hashlib.sha256(data).hexdigest()!=r['sha256']:
            raise ValueError('Source hash mismatch: '+r['local_name'])
        if not path.exists():
            path.write_bytes(data)
        print('Verified',r['local_name'])


def self_test():
    assert halfpoint(-3.5) and not halfpoint(-3)
    assert all(abs(p-.5)<1e-12 for p in devig(1.91,1.91))
    assert all(abs(p-2/3)<1e-12 for p in devig(1.5,3))
    assert abs(ev(.5,2.0)+.01)<1e-12
    base=dict(date='x',event='y',family='spread',player='')
    assert groupkey(dict(base,side='home',point=-3.5))==groupkey(dict(base,side='away',point=3.5))
    assert groupkey(dict(base,side='home',point=-3.5))!=groupkey(dict(base,side='away',point=-3.5))
    pair=[dict(base,side='home',point=-3.5,price=1.91),dict(base,side='away',point=3.5,price=1.91)]
    assert len(pairs(pair)[0])==1
    assert len(pairs(pair+[pair[0]])[0])==0
    assert len(pairs([dict(r,point=int(r['point'])) for r in pair])[0])==0
    print('9 analytical checks passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        self_test()
    else:
        verify_sources(allow_download=args.download)
        run()
