#!/usr/bin/env python3
"""Audit a fixed source sample; never evaluate outcomes, returns, or a betting rule."""
import argparse
import csv
import hashlib
import io
import json
import statistics
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / 'reports/new-prop-archive-source-selection-2026-09-13.json'
RAW = ROOT / 'data/raw/new-prop-archive-sample'
OUT = ROOT / 'reports/new-prop-archive-source-audit-2026-09-13.json'


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def download(spec):
    sport, repo, commit, item, fetch = spec
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{item['path']}"
    path = RAW / sport / Path(item['path']).name
    path.parent.mkdir(parents=True, exist_ok=True)
    sidecar = path.with_suffix(path.suffix + '.acquisition.json')
    if not path.exists():
        if not fetch:
            raise FileNotFoundError(f'{path}: use --fetch for the pinned public file')
        started = datetime.now(timezone.utc).isoformat()
        with urlopen(url, timeout=45) as response:
            data = response.read()
        ended = datetime.now(timezone.utc).isoformat()
        path.write_bytes(data)
        sidecar.write_text(json.dumps({'request_started_utc': started, 'response_complete_utc': ended}, indent=2))
    data = path.read_bytes()
    blob_sha = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    assert blob_sha == item['git_blob_sha'], (path, blob_sha)
    assert len(data) == item['expected_bytes'], path
    return sport, path, {'url': url, 'source_path': item['path'], 'local_path': str(path.relative_to(ROOT)),
                        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'git_blob_sha': blob_sha, **json.loads(sidecar.read_text())}


def nba_audit(path):
    obj = json.loads(path.read_text())
    event = obj['data']
    captured = dt(obj['timestamp'])
    start = dt(event['commence_time'])
    fd = [b for b in event['bookmakers'] if b['key'] == 'fanduel']
    details = []
    for book in fd:
        for market in book['markets']:
            groups = defaultdict(list)
            for row in market['outcomes']:
                groups[(row.get('description'), row.get('point'))].append(row)
            pairs = sum(len(v) == 2 and {x['name'] for x in v} == {'Over', 'Under'} for v in groups.values())
            details.append({'market_key': market['key'], 'outcome_rows': len(market['outcomes']),
                            'player_line_groups': len(groups), 'paired_over_under_groups': pairs,
                            'unpaired_groups': len(groups) - pairs,
                            'book_update_utc': book.get('last_update'), 'market_update_utc': market.get('last_update'),
                            'book_age_seconds': (captured - dt(book['last_update'])).total_seconds(),
                            'market_age_seconds': (captured - dt(market['last_update'])).total_seconds(),
                            'invalid_decimal_prices': sum(not isinstance(x['price'], (float, int)) or x['price'] <= 1 for x in market['outcomes']),
                            'duplicate_player_line_side_rows': sum(max(0, n - 1) for n in Counter((x.get('description'), x.get('point'), x.get('name')) for x in market['outcomes']).values()),
                            'invalid_price_rows': [x for x in market['outcomes'] if not isinstance(x['price'], (float, int)) or x['price'] <= 1]})
    return {'event_id': event['id'], 'sport_key': event['sport_key'], 'home_team': event['home_team'],
            'away_team': event['away_team'], 'source_snapshot_utc': obj['timestamp'],
            'reported_start_utc': event['commence_time'], 'snapshot_lead_minutes': (start - captured).total_seconds() / 60,
            'fanduel_book_objects': len(fd), 'fanduel_markets': details,
            'all_book_keys': [b['key'] for b in event['bookmakers']]}


def nfl_audit(path):
    reader = csv.DictReader(io.StringIO(path.read_text()))
    fields = list(reader.fieldnames)
    # Only metadata and price columns are inspected; no actual-value/settlement field is loaded into analysis.
    rows = [{k: v for k, v in row.items() if k in {'event_id', 'commence_time', 'home_team', 'away_team',
             'bookmaker_key', 'bookmaker_title', 'sportsbook', 'bookmaker_last_update', 'market_last_update', 'market_key', 'player',
             'line', 'price', 'over_price', 'under_price', 'snapshot_time', 'requested_snapshot_time',
             'snapshot_timestamp', 'timestamp', 'season_guess'}} for row in reader]
    metadata = {'rows': len(rows), 'columns': fields}
    for name in ('bookmaker_key', 'sportsbook', 'market_key', 'season_guess'):
        if name in fields:
            metadata[name + '_counts'] = dict(Counter(r.get(name, '') for r in rows))
    for name in ('event_id', 'player'):
        if name in fields:
            metadata[name + '_distinct'] = len({r.get(name) for r in rows})
    for name in ('commence_time', 'bookmaker_last_update', 'market_last_update', 'snapshot_time', 'requested_snapshot_time', 'snapshot_timestamp', 'timestamp'):
        if name in fields:
            values = [r[name] for r in rows if r.get(name)]
            metadata[name] = {'nonnull': len(values), 'min': min(values) if values else None, 'max': max(values) if values else None}
    valid_pairs = [r for r in rows if r.get('over_price') and r.get('under_price') and float(r['over_price']) > 1 and float(r['under_price']) > 1]
    metadata['complete_valid_decimal_price_pairs'] = len(valid_pairs)
    metadata['invalid_or_missing_price_pairs'] = len(rows) - len(valid_pairs)
    if 'requested_snapshot_time' in fields:
        leads = [(dt(r['commence_time']) - dt(r['requested_snapshot_time'])).total_seconds() / 60 for r in rows]
        metadata['snapshot_lead_minutes'] = {'min': min(leads), 'median': statistics.median(leads), 'max': max(leads)}
        metadata['at_or_after_reported_start'] = sum(x <= 0 for x in leads)
        for name in ('bookmaker_last_update', 'market_last_update'):
            ages = [(dt(r['requested_snapshot_time']) - dt(r[name])).total_seconds() for r in rows if r.get(name)]
            metadata[name + '_age_seconds'] = {'min': min(ages), 'median': statistics.median(ages), 'max': max(ages), 'future_rows': sum(x < 0 for x in ages)}
        keys = Counter(tuple(r.get(k) for k in ('event_id', 'player', 'market_key', 'line', 'requested_snapshot_time')) for r in rows)
        metadata['duplicate_event_player_market_line_snapshot_rows'] = sum(n - 1 for n in keys.values())
        snapshots = defaultdict(set)
        for r in rows:
            snapshots[(r.get('event_id'), r.get('player'), r.get('market_key'), r.get('line'))].add(r.get('requested_snapshot_time'))
        metadata['player_line_keys_with_multiple_snapshot_times'] = sum(len(v) > 1 for v in snapshots.values())
    metadata['first_price_row_metadata_only'] = rows[0] if rows else None
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    selection = json.loads(SELECTION.read_text())
    specs = [(sport, selection[f'{sport}_repository'], selection[f'{sport}_commit'], item, args.fetch)
             for sport in ('nba', 'nfl') for item in selection[f'{sport}_files']]
    with ThreadPoolExecutor(max_workers=4) as pool:
        acquired = list(pool.map(download, specs))
    results = []
    for sport, path, manifest in acquired:
        results.append({'sport': sport, **manifest, 'audit': nba_audit(path) if sport == 'nba' else nfl_audit(path)})
    nba = [r['audit'] for r in results if r['sport'] == 'nba']
    markets = defaultdict(Counter)
    for event in nba:
        for market in event['fanduel_markets']:
            for key in ('outcome_rows', 'player_line_groups', 'paired_over_under_groups', 'unpaired_groups', 'invalid_decimal_prices', 'duplicate_player_line_side_rows'):
                markets[market['market_key']][key] += market[key]
            markets[market['market_key']]['markets_with_future_quote_update'] += int(market['book_age_seconds'] < 0 or market['market_age_seconds'] < 0)
            if market['book_age_seconds'] >= 0 and market['market_age_seconds'] >= 0:
                markets[market['market_key']]['paired_groups_with_nonfuture_clocks'] += market['paired_over_under_groups']
    report = {'audit_completed_utc': datetime.now(timezone.utc).isoformat(),
              'selection_sha256': hashlib.sha256(SELECTION.read_bytes()).hexdigest(),
              'purpose': 'Source feasibility only; no outcomes, forecasts, returns or selected betting rules inspected.',
              'nba_summary': {'files': len(nba), 'distinct_events': len({r['event_id'] for r in nba}),
                              'fanduel_events': sum(r['fanduel_book_objects'] > 0 for r in nba),
                              'source_snapshot_range': [min(r['source_snapshot_utc'] for r in nba), max(r['source_snapshot_utc'] for r in nba)],
                              'reported_start_range': [min(r['reported_start_utc'] for r in nba), max(r['reported_start_utc'] for r in nba)],
                              'snapshot_lead_minutes_range': [min(r['snapshot_lead_minutes'] for r in nba), max(r['snapshot_lead_minutes'] for r in nba)],
                              'at_or_after_reported_start': sum(r['snapshot_lead_minutes'] <= 0 for r in nba),
                              'fanduel_markets': dict(markets)}, 'files': results}
    OUT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'nba_summary': report['nba_summary'], 'nfl': [r['audit'] for r in results if r['sport'] == 'nfl']}, indent=2))


if __name__ == '__main__':
    main()
