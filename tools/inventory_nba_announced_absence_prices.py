#!/usr/bin/env python3
"""Existing 2025-26 price census, with no injury or performance inputs."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

from select_nba_injury_clock_samples import ROOT, RAW, NY, dt, sha

OUT = ROOT / 'data/raw/nba-announced-absence-2026-09-26/prices.json'
REPORT = ROOT / 'reports/nba-announced-absence-price-inventory-2026-09-26.json'
SCHEDULE = RAW / 'nba_schedule_2026.csv'
SCHEDULE_SHA = '5a4a7473fce1c49d56382211c5955ad405f421d59869143b1d501e997e79223e'


def norm(s):
    s = re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower())
    return 'laclippers' if s == 'losangelesclippers' else s


def main():
    assert not OUT.exists() and not REPORT.exists(), 'Preserve frozen price census'
    assert sha(SCHEDULE) == SCHEDULE_SHA
    # csv.DictReader accesses row metadata below only; no performance values used.
    import pandas as pd
    schedule = pd.read_csv(SCHEDULE, dtype=str, usecols=['game_id', 'game_date', 'start_date',
        'home_display_name', 'away_display_name', 'season_type'])
    fixtures = defaultdict(set)
    for r in schedule.to_dict('records'):
        if r['season_type'] == '2':
            fixtures[(dt(r['start_date']).astimezone(NY).strftime('%Y-%m-%d'),
                      norm(r['away_display_name']), norm(r['home_display_name']))].add((r['game_id'], r['start_date']))
    with (RAW / 'game_event_bijection.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len({r['event_id'] for r in rows})
    mapping = {r['event_id']: r['game_id'].zfill(10) for r in rows}
    manifest = json.loads((RAW / 'acquisition_manifest.json').read_text())
    specs = [s for s in manifest['files'] if s['source_path'].startswith('data/historical_points/')]
    assert len(specs) == 3394
    counts, bymonth, events, excluded = Counter(), defaultdict(Counter), [], []
    for spec in specs:
        gid = mapping.get(spec['event_id'], '')
        if not gid.startswith('00225'):
            continue
        path = ROOT / spec['local_path']
        assert sha(path) == spec['sha256']
        obj = json.loads(path.read_text())
        e, snap = obj['data'], dt(obj['timestamp'])
        assert e['id'] == spec['event_id']
        start = dt(e['commence_time'])
        day = start.astimezone(NY).strftime('%Y-%m-%d')
        month = day[:7]
        counts['source_events'] += 1
        bymonth[month]['source_events'] += 1
        reason = None
        match = fixtures.get((day, norm(e['away_team']), norm(e['home_team'])), set())
        books = [b for b in e['bookmakers'] if b['key'] == 'fanduel']
        if len(match) != 1:
            reason = 'missing_or_ambiguous_independent_fixture'
        elif len(books) != 1:
            reason = 'missing_or_duplicate_book'
        elif snap >= min(start, dt(next(iter(match))[1])):
            reason = 'entry_not_before_both_starts'
        if reason is None:
            b = books[0]
            markets = [m for m in b['markets'] if m['key'] == 'player_points']
            if len(markets) != 1:
                reason = 'missing_or_duplicate_market'
        if reason is None:
            m = markets[0]
            try:
                ages = [(snap - dt(v)).total_seconds() for v in [b['last_update'], m['last_update']]]
                if not all(0 <= a <= 300 for a in ages):
                    reason = 'invalid_quote_age'
            except (KeyError, ValueError, TypeError):
                reason = 'invalid_update_clock'
        pairs = []
        if reason is None:
            groups = defaultdict(list)
            for r in m['outcomes']:
                name, line = r.get('description'), r.get('point')
                if not isinstance(name, str) or not name.strip():
                    continue
                try:
                    line = float(line)
                except (ValueError, TypeError):
                    continue
                if math.isfinite(line) and line % 1 == .5:
                    groups[(name, line)].append(r)
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
                if 0 <= margin <= .12:
                    pairs.append({'player': name, 'line': line, 'over_decimal': prices['Over'],
                                  'under_decimal': prices['Under'], 'overround': margin})
            if not pairs:
                reason = 'no_paired_main_points'
        if reason:
            counts[reason] += 1
            bymonth[month][reason] += 1
            excluded.append({'event_id': e['id'], 'nba_game_id': gid, 'reason': reason})
            continue
        espn, indep = next(iter(match))
        counts['eligible_price_events'] += 1
        counts['paired_player_lines'] += len(pairs)
        bymonth[month]['eligible_price_events'] += 1
        bymonth[month]['paired_player_lines'] += len(pairs)
        events.append({'event_id': e['id'], 'nba_game_id': gid, 'espn_game_id': espn,
            'home_team': e['home_team'], 'away_team': e['away_team'], 'game_date_et': day,
            'source_snapshot_utc': obj['timestamp'], 'provider_start_utc': e['commence_time'],
            'independent_start_utc': indep, 'book_last_update': b['last_update'], 'market_last_update': m['last_update'],
            'book_age_seconds': ages[0], 'market_age_seconds': ages[1], 'source_path': str(path.relative_to(ROOT)),
            'source_sha256': spec['sha256'], 'preliminary_pairs': sorted(pairs, key=lambda r:(r['player'],r['line']))})
    # Multiple publisher IDs for a fixture cannot silently multiply independent games.
    duplicates = {k:v for k,v in Counter(e['espn_game_id'] for e in events).items() if v > 1}
    assert not duplicates, duplicates
    events.sort(key=lambda e:(dt(e['source_snapshot_utc']),e['event_id']))
    periods = {}
    for label, take_early in [('calibration',True),('evaluation',False)]:
        g = [e for e in events if (dt(e['source_snapshot_utc']) < dt('2026-01-01T00:00:00Z')) == take_early]
        periods[label] = {'price_events':len(g),'paired_player_lines':sum(len(e['preliminary_pairs']) for e in g),
            'unique_quote_dates_et':len({dt(e['source_snapshot_utc']).astimezone(NY).date() for e in g})}
    result = {'scope':'Price and independent fixture metadata only; no statuses or player performance.',
        'counts':dict(counts),'by_month':{k:dict(v) for k,v in sorted(bymonth.items())},'periods':periods,
        'inputs':{str(p.relative_to(ROOT)):sha(p) for p in [RAW/'acquisition_manifest.json',RAW/'game_event_bijection.csv',SCHEDULE]},
        'tool_sha256':sha(Path(__file__)),'excluded_events':excluded,'events':events}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    brief = {k:v for k,v in result.items() if k not in {'events','excluded_events'}}
    brief['frozen_inventory'] = {'path':str(OUT.relative_to(ROOT)),'sha256':sha(OUT)}
    REPORT.write_text(json.dumps(brief,indent=2)+'\n')
    print(json.dumps(brief,indent=2))


if __name__ == '__main__':
    main()
