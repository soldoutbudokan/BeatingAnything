#!/usr/bin/env python3
"""Select declared newer-season price metadata samples without player outcomes."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nba-consensus-price'
OUT = ROOT / 'data/raw/nba-injury-price-clocks-2026-09-26/selected-price-samples.json'
DECL = ROOT / 'docs/nba-injury-price-clock-inventory-declaration-2026-09-26.md'
MONTHS = {'2025-10', '2026-01', '2026-04'}
NY = ZoneInfo('America/New_York')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dt(x):
    d = datetime.fromisoformat(x.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Missing timezone')
    return d


def main():
    assert not OUT.exists(), 'Preserve selected sample; use a separate output for audit'
    with (RAW / 'game_event_bijection.csv').open() as f:
        mapping_rows = list(csv.DictReader(f))
    assert len({r['event_id'] for r in mapping_rows}) == len(mapping_rows)
    mapping = {r['event_id']: r['game_id'].zfill(10) for r in mapping_rows}
    manifest = json.loads((RAW / 'acquisition_manifest.json').read_text())
    files = [r for r in manifest['files'] if r['source_path'].startswith('data/historical_points/')]
    assert len(files) == 3394 and sum(r['bytes'] for r in files) == 397273601
    counts = Counter()
    candidates = defaultdict(list)
    for spec in files:
        gid = mapping.get(spec['event_id'], '')
        if not gid.startswith('00225'):
            continue
        start = dt(spec['reported_start_utc'])
        month = start.astimezone(NY).strftime('%Y-%m')
        if month not in MONTHS:
            continue
        counts[month + ':source_events'] += 1
        p = ROOT / spec['local_path']
        assert sha(p) == spec['sha256']
        obj = json.loads(p.read_text())
        e = obj['data']
        snap = dt(obj['timestamp'])
        if snap >= start:
            counts[month + ':entry_not_before_provider_start'] += 1
            continue
        books = [b for b in e['bookmakers'] if b['key'] == 'fanduel']
        if len(books) != 1:
            counts[month + ':missing_or_duplicate_book'] += 1
            continue
        b = books[0]
        markets = [m for m in b['markets'] if m['key'] == 'player_points']
        if len(markets) != 1:
            counts[month + ':missing_or_duplicate_market'] += 1
            continue
        m = markets[0]
        try:
            ages = [(snap - dt(v)).total_seconds() for v in [b['last_update'], m['last_update']]]
        except (KeyError, ValueError, TypeError):
            counts[month + ':invalid_update_clock'] += 1
            continue
        if not all(0 <= a <= 300 for a in ages):
            counts[month + ':invalid_quote_age'] += 1
            continue
        groups = defaultdict(list)
        for row in m['outcomes']:
            name, line = row.get('description'), row.get('point')
            if not isinstance(name, str) or not name.strip():
                continue
            try:
                line = float(line)
            except (ValueError, TypeError):
                continue
            if not math.isfinite(line) or line % 1 != .5:
                continue
            groups[(name, line)].append(row)
        pairs = []
        for (name, line), g in groups.items():
            if len(g) != 2 or {r['name'] for r in g} != {'Over', 'Under'}:
                continue
            try:
                prices = {r['name']: float(r['price']) for r in g}
            except (ValueError, TypeError):
                continue
            if not all(math.isfinite(v) and 1.2 <= v <= 6 for v in prices.values()):
                continue
            margin = sum(1 / v for v in prices.values()) - 1
            if not 0 <= margin <= .12:
                continue
            pairs.append({'player': name, 'line': line, 'over_decimal': prices['Over'],
                          'under_decimal': prices['Under'], 'overround': margin})
        if not pairs:
            counts[month + ':no_preliminary_pairs'] += 1
            continue
        counts[month + ':preliminary_price_events'] += 1
        candidates[month].append({'event_id': e['id'], 'nba_game_id': gid,
            'home_team': e['home_team'], 'away_team': e['away_team'],
            'source_snapshot_utc': obj['timestamp'], 'provider_start_utc': e['commence_time'],
            'book_last_update': b['last_update'], 'market_last_update': m['last_update'],
            'book_age_seconds': ages[0], 'market_age_seconds': ages[1],
            'source_path': str(p.relative_to(ROOT)), 'source_sha256': spec['sha256'],
            'preliminary_pairs': sorted(pairs, key=lambda r: (r['player'], r['line']))})
    selected = {month: min(rows, key=lambda r: (dt(r['source_snapshot_utc']), r['event_id']))
                for month, rows in candidates.items()}
    result = {'selected_at_utc': datetime.now(timezone.utc).isoformat(),
        'declaration': {'path': str(DECL.relative_to(ROOT)), 'sha256': sha(DECL)},
        'source_manifest': {'path': str((RAW / 'acquisition_manifest.json').relative_to(ROOT)),
                            'sha256': sha(RAW / 'acquisition_manifest.json')},
        'source_mapping_sha256': sha(RAW / 'game_event_bijection.csv'),
        'counts': dict(sorted(counts.items())), 'selected': selected,
        'missing_declared_months': sorted(MONTHS - selected.keys()),
        'scope': 'Preliminary prices only; no player IDs, independent fixture qualification, sporting outcomes, star membership, models or returns.'}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({month: {k: v for k, v in row.items() if k != 'preliminary_pairs'} |
                     {'pairs': len(row['preliminary_pairs'])} for month, row in selected.items()}, indent=2))


if __name__ == '__main__':
    main()
