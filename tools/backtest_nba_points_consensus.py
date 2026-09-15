#!/usr/bin/env python3
"""Card 39 fixed NBA FanDuel paired-points screen; freeze prices before scores.

python tools/acquire_nba_prop_archive.py --fetch
python tools/backtest_nba_points_consensus.py fetch-support
python tools/backtest_nba_points_consensus.py prepare
python tools/backtest_nba_points_consensus.py evaluate --season 2025
python tools/backtest_nba_points_consensus.py evaluate --season 2026
Raw originals/candidate ledgers remain ignored. No orders or provider keys.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import unicodedata
from zoneinfo import ZoneInfo
from urllib.request import urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nba-consensus-price'
SOURCE = ROOT / 'data/raw/nba-source-feasibility'
DECLARATION = ROOT / 'docs/nba-points-consensus-declaration-2026-09-13.md'
DECLARATION_SHA = 'c97142492881b0a2616944bbdcb5a24e409717f643431f70057f77cbcfb50747'
PREFIX = ROOT / 'reports/nba-points-consensus-2026-09-13'
FREEZE = RAW / 'frozen_selections.json'
NY = ZoneInfo('America/New_York')
INPUTS = {
    'stats_2025': (SOURCE / 'nba_stats_schedule_2024.csv', 'ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26'),
    'stats_2026': (SOURCE / 'nba_stats_schedule_2025.csv', 'e78976dfe77bc2137acf9e6cf5b10516593f2a476d74847336181a40c75b97a6'),
    'box_2025': (SOURCE / 'player_boxscores_2025.csv', '7371d222692fee1c083913d813b125f885c4e53b6f3daaecb7270299913e9716'),
    'box_2026': (RAW / 'player_boxscores_2026.csv', '6ee53f72a953fc42c17cb7e9797af303cb102b853b67ca0b51cbc82c2260b270'),
    'espn_2025': (RAW / 'nba_schedule_2025.csv', 'a7a5b6607a256c84a324f819e4461248bdff90a78b1ddb675a5a117a9a94e74f'),
    'espn_2026': (RAW / 'nba_schedule_2026.csv', '5a4a7473fce1c49d56382211c5955ad405f421d59869143b1d501e997e79223e'),
    'mapping': (RAW / 'game_event_bijection.csv', '23f27cc66b8b333fffd7b25d756f530d79dff0cafd69ff397cf16638000ed64c'),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dt(value):
    d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Clock without timezone')
    return d


def norm(value):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', value)


def team(value):
    value = norm(value)
    return 'laclippers' if value == 'losangelesclippers' else value


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def checked_inputs():
    assert sha(DECLARATION) == DECLARATION_SHA, 'Declaration changed'
    evidence = {}
    for key, (path, pin) in INPUTS.items():
        assert sha(path) == pin, f'Input changed: {path}'
        evidence[key] = {'path': str(path.relative_to(ROOT)), 'sha256': pin, 'bytes': path.stat().st_size}
    return evidence


def fetch_support():
    """Retrieve missing pinned public support bytes, never execute publisher code."""
    tags = {'stats': 'nba_stats_schedules', 'box': 'nba_stats_player_boxscores',
            'espn': 'espn_nba_schedules'}
    for key, (path, pin) in INPUTS.items():
        if key == 'mapping':
            continue
        kind = key.split('_')[0]
        url = f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/{tags[kind]}/{path.name}'
        if not path.exists():
            started = now()
            path.parent.mkdir(parents=True, exist_ok=True)
            with urlopen(url, timeout=120) as response:
                data = response.read()
            assert hashlib.sha256(data).hexdigest() == pin, f'Publisher input changed: {url}'
            path.write_bytes(data)
            dump(path.with_suffix(path.suffix + '.acquisition.json'), {'url': url,
                'request_started_utc': started, 'response_complete_utc': now(), 'sha256': pin})
        assert sha(path) == pin, f'Existing input changed: {path}'
    print('Pinned support inputs present; no outcomes loaded.')


def identities_and_fixtures():
    # Explicit usecols prevents score/minutes/participation from entering selection.
    names = defaultdict(set)
    fixtures = {}
    for year in (2025, 2026):
        ids = pd.read_csv(INPUTS[f'box_{year}'][0], usecols=['person_id', 'first_name', 'family_name'])
        for row in ids.drop_duplicates().itertuples():
            names[norm(f'{row.first_name} {row.family_name}')].add(int(row.person_id))
        s = pd.read_csv(INPUTS[f'stats_{year}'][0], dtype={'game_id': str},
                        usecols=['game_id', 'game_date', 'team_id', 'team_name', 'matchup'])
        s = s[s.game_id.str.startswith(f'002{str(year-1)[2:]}')]
        espn = pd.read_csv(INPUTS[f'espn_{year}'][0], dtype={'game_id': str}, usecols=[
            'game_id', 'game_date', 'start_date', 'home_display_name', 'away_display_name', 'season_type'])
        starts = defaultdict(set)
        for row in espn.itertuples():
            if int(row.season_type) == 2:
                starts[(row.game_date, team(row.home_display_name), team(row.away_display_name))].add((row.start_date, row.game_id))
        for gid, g in s.groupby('game_id'):
            if len(g) != 2 or g.game_date.nunique() != 1:
                continue
            h = g[g.matchup.str.contains(' vs. ', regex=False)]
            a = g[g.matchup.str.contains(' @ ', regex=False)]
            if len(h) != 1 or len(a) != 1:
                continue
            h, a = h.iloc[0], a.iloc[0]
            key = (h.game_date, team(h.team_name), team(a.team_name))
            matches = starts.get(key, set())
            fixtures[gid] = {'season': year, 'game_date': h.game_date, 'home_team': h.team_name,
                'away_team': a.team_name, 'team_ids': [int(h.team_id), int(a.team_id)],
                'independent_start': next(iter(matches))[0] if len(matches) == 1 else None,
                'espn_game_id': next(iter(matches))[1] if len(matches) == 1 else None,
                'espn_matching_fixture_count': len(matches)}
    return names, fixtures


def devig(over, under):
    q = (1 / over, 1 / under)
    proportional = (q[0] / sum(q), q[1] / sum(q))
    lo, hi = 0.0, 20.0
    for _ in range(65):
        k = (lo + hi) / 2
        if sum(x ** k for x in q) > 1:
            lo = k
        else:
            hi = k
    power = tuple(x ** ((lo + hi) / 2) for x in q)
    assert abs(sum(power) - 1) < 1e-10
    return proportional, power


def pairs(book, snapshot, names, counts, unmapped):
    key = book['key']
    markets = [m for m in book.get('markets', []) if m.get('key') == 'player_points']
    if len(markets) != 1:
        counts['missing_or_duplicate_main_market'] += 1
        return {}
    market = markets[0]
    try:
        ages = [(snapshot - dt(x)).total_seconds() for x in (book.get('last_update'), market.get('last_update'))]
    except (ValueError, TypeError):
        counts['invalid_clock'] += 1
        return {}
    if any(x < 0 for x in ages):
        counts['future_book_or_market_clock'] += 1
        return {}
    if any(x > 300 for x in ages):
        counts['book_or_market_older_than_300_seconds'] += 1
        return {}
    groups = defaultdict(list)
    for o in market.get('outcomes', []):
        n = norm(o.get('description'))
        player_ids = names.get(n, set())
        if len(player_ids) != 1:
            counts['unknown_or_ambiguous_player_outcome_rows'] += 1
            unmapped[str(o.get('description'))] += 1
            continue
        try:
            line = float(o['point'])
        except (KeyError, ValueError, TypeError):
            counts['invalid_line_rows'] += 1
            continue
        if not math.isfinite(line) or line % 1 != .5:
            counts['non_half_point_rows'] += 1
            continue
        groups[(next(iter(player_ids)), line)].append(o)
    out = {}
    for pair_key, outcomes in groups.items():
        counts['player_line_groups_after_identity_and_halfpoint'] += 1
        if len(outcomes) != 2 or {o.get('name') for o in outcomes} != {'Over', 'Under'}:
            counts['unpaired_or_ambiguous_groups'] += 1
            continue
        values = {o['name']: o for o in outcomes}
        try:
            over, under = float(values['Over']['price']), float(values['Under']['price'])
        except (ValueError, TypeError, KeyError):
            counts['invalid_pair_prices'] += 1
            continue
        if not all(math.isfinite(x) and 1.20 <= x <= 6 for x in (over, under)):
            counts['pair_price_outside_bounds'] += 1
            continue
        overround = 1 / over + 1 / under - 1
        if not 0 <= overround <= .12:
            counts['pair_overround_outside_bounds'] += 1
            continue
        prop, power = devig(over, under)
        out[pair_key] = {'book': key, 'over': over, 'under': under, 'proportional': prop,
            'power': power, 'book_age_seconds': ages[0], 'market_age_seconds': ages[1],
            'overround': overround, 'player_name': values['Over']['description']}
        counts['eligible_pairs'] += 1
    return out


def prepare():
    assert not FREEZE.exists(), 'Frozen selection exists; preserve it, do not overwrite'
    inputs = checked_inputs()
    names, fixtures = identities_and_fixtures()
    mapping = pd.read_csv(INPUTS['mapping'][0], dtype=str)
    assert not mapping.game_id.duplicated().any() and not mapping.event_id.duplicated().any()
    events = dict(zip(mapping.event_id, mapping.game_id.str.zfill(10)))
    manifest = json.loads((RAW / 'acquisition_manifest.json').read_text())
    files = [f for f in manifest['files'] if f['source_path'].startswith('data/historical_points/')]
    assert len(files) == 3394 and sum(f['bytes'] for f in files) == 397273601
    counts, book_counts, unmatched = Counter(), defaultdict(Counter), Counter()
    for year in (2025, 2026):
        counts[f'independent_regular_season_fixtures_{year}'] = sum(f['season'] == year for f in fixtures.values())
    candidates, file_records, fixture_failures = [], [], []
    for spec in files:
        path = ROOT / spec['local_path']
        assert sha(path) == spec['sha256']
        obj = json.loads(path.read_text())
        event = obj['data']
        eid = event['id']
        gid = events.get(eid)
        counts['archive_files'] += 1
        record = {'event_id': eid, 'game_id': gid, 'source_path': spec['source_path'],
                  'source_sha256': spec['sha256'], 'source_snapshot': obj['timestamp']}
        file_records.append(record)
        if gid is None:
            counts['event_missing_publisher_mapping'] += 1
            record['status'] = 'missing_publisher_mapping'
            continue
        if not gid.startswith(('00224', '00225')):
            counts['outside_fixed_regular_seasons'] += 1
            record['status'] = 'outside_fixed_regular_seasons'
            continue
        counts['mapped_fixed_period_files'] += 1
        counts[f'mapped_archive_files_{2025 if gid.startswith("00224") else 2026}'] += 1
        fixture = fixtures.get(gid)
        if fixture is None or team(fixture['home_team']) != team(event['home_team']) or team(fixture['away_team']) != team(event['away_team']):
            counts['independent_fixture_identity_missing_or_mismatch'] += 1
            record['status'] = 'independent_fixture_identity_missing_or_mismatch'
            fixture_failures.append(record.copy())
            continue
        snapshot, start = dt(obj['timestamp']), dt(event['commence_time'])
        if start.astimezone(NY).date().isoformat() != fixture['game_date']:
            counts['independent_fixture_date_mismatch'] += 1
            record['status'] = 'independent_fixture_date_mismatch'
            fixture_failures.append(record.copy())
            continue
        independent = dt(fixture['independent_start']) if fixture['independent_start'] else None
        if snapshot >= start or (independent is not None and snapshot >= independent) or (
                independent is None and snapshot.astimezone(NY).date().isoformat() >= fixture['game_date']):
            counts['not_verified_pregame_by_independent_clock'] += 1
            record['status'] = 'not_verified_pregame_by_independent_clock'
            fixture_failures.append(record.copy())
            continue
        counts[f'verified_fixtures_{fixture["season"]}'] += 1
        books = event.get('bookmakers', [])
        duplicates = {key for key, n in Counter(b['key'] for b in books).items() if n > 1}
        by_book = {b['key']: pairs(b, snapshot, names, book_counts[b['key']], unmatched)
                   for b in books if b['key'] not in duplicates}
        if duplicates:
            counts['duplicate_book_keys_rejected'] += len(duplicates)
        fd = by_book.get('fanduel', {})
        counts['eligible_fanduel_pairs'] += len(fd)
        selected_this_file = []
        for pair_key, pair in fd.items():
            references = [v[pair_key] for k, v in by_book.items() if k != 'fanduel' and pair_key in v]
            if len(references) < 3:
                counts['fanduel_pairs_with_fewer_than_three_reference_books'] += 1
                continue
            counts['fanduel_pairs_with_three_plus_references'] += 1
            for index, side in enumerate(('Over', 'Under')):
                pprop = statistics.median(r['proportional'][index] for r in references)
                ppower = statistics.median(r['power'][index] for r in references)
                price = pair[side.lower()]
                net_win = .98 * (price - 1)
                evprop = pprop * (1 + net_win) - 1
                evpower = ppower * (1 + net_win) - 1
                conservative = min(evprop, evpower)
                if conservative < .03:
                    counts['sides_below_fixed_three_percent_score'] += 1
                    continue
                counts['qualifying_candidate_sides'] += 1
                selected_this_file.append({'game_id': gid, 'season': fixture['season'], 'event_id': eid,
                    'person_id': pair_key[0], 'player_name': pair['player_name'], 'line': pair_key[1], 'side': side,
                    'fd_decimal': price, 'source_snapshot': obj['timestamp'], 'reported_start': event['commence_time'],
                    **fixture, 'source_path': spec['source_path'], 'source_sha256': spec['sha256'],
                    'fd_book_age_seconds': pair['book_age_seconds'], 'fd_market_age_seconds': pair['market_age_seconds'],
                    'reference_books': sorted(r['book'] for r in references), 'reference_count': len(references),
                    'median_proportional_probability': pprop, 'median_power_probability': ppower,
                    'haircut_ev_proportional': evprop, 'haircut_ev_power': evpower,
                    'conservative_haircut_ev': conservative, 'reference_pair_evidence': references})
        candidates.extend(selected_this_file)
        record['status'] = 'qualifying_candidates' if selected_this_file else 'no_qualifying_candidate'
        record['candidate_count'] = len(selected_this_file)
    grouped = defaultdict(list)
    for row in candidates:
        grouped[row['game_id']].append(row)
    selections = []
    for rows in grouped.values():
        earliest = min(dt(r['source_snapshot']) for r in rows)
        same = [r for r in rows if dt(r['source_snapshot']) == earliest]
        choice = min(same, key=lambda r: (-r['conservative_haircut_ev'], r['person_id'], r['side'], r['line'], r['event_id'], r['source_path']))
        selections.append(choice)
    selections.sort(key=lambda r: (r['independent_start'] or r['reported_start'], r['game_id']))
    counts['selected_games'] = len(selections)
    for year in (2025, 2026):
        counts[f'selected_games_{year}'] = sum(r['season'] == year for r in selections)
    frozen = {'frozen_utc': now(), 'declaration_sha256': DECLARATION_SHA, 'inputs': inputs,
        'acquisition_manifest_sha256': sha(RAW / 'acquisition_manifest.json'), 'attrition': dict(counts),
        'book_pair_attrition': {k: dict(v) for k, v in book_counts.items()}, 'unmapped_or_ambiguous_player_rows': dict(unmatched),
        'fixture_failures': fixture_failures, 'selections': selections}
    frozen['fixture_ids_without_mapped_archive_by_season'] = {
        str(y): sorted(gid for gid, f in fixtures.items() if f['season'] == y and
                       gid not in {r['game_id'] for r in file_records}) for y in (2025, 2026)}
    dump(RAW / 'all_candidate_sides.json', candidates)
    dump(RAW / 'file_screen_ledger.json', file_records)
    frozen['candidate_ledger_sha256'] = sha(RAW / 'all_candidate_sides.json')
    frozen['file_screen_ledger_sha256'] = sha(RAW / 'file_screen_ledger.json')
    dump(FREEZE, frozen)
    summary = {k: v for k, v in frozen.items() if k != 'selections'}
    summary.update({'frozen_selections_sha256': sha(FREEZE), 'selected_game_ids_by_season': {
        str(y): [r['game_id'] for r in selections if r['season'] == y] for y in (2025, 2026)},
        'no_outcomes_loaded': True, 'script_sha256_at_freeze': sha(Path(__file__))})
    dump(Path(str(PREFIX) + '-selection.json'), summary)
    print(json.dumps({'frozen_utc': frozen['frozen_utc'], 'frozen_selections_sha256': sha(FREEZE), 'attrition': dict(counts)}, indent=2))


def minutes(value):
    if pd.isna(value) or value == '':
        return 0.0
    parts = str(value).split(':')
    return float(parts[0]) + float(parts[1]) / 60 if len(parts) == 2 else float(parts[0])


def evaluate(year):
    inputs = checked_inputs()
    summary = json.loads(Path(str(PREFIX) + '-selection.json').read_text())
    assert sha(FREEZE) == summary['frozen_selections_sha256'], 'Frozen price selections changed'
    output = Path(str(PREFIX) + f'-{year}.json')
    assert not output.exists(), 'Preserve existing period result; do not overwrite'
    first_report = Path(str(PREFIX) + '-2025.json')
    if year == 2026:
        assert first_report.exists(), 'Report first period before unlocking reserved outcomes'
    frozen = json.loads(FREEZE.read_text())
    selections = [r for r in frozen['selections'] if r['season'] == year]
    # This is the first point at which scoring/participation columns are loaded.
    box = pd.read_csv(INPUTS[f'box_{year}'][0], dtype={'game_id': str})
    schedule = pd.read_csv(INPUTS[f'stats_{year}'][0], dtype={'game_id': str})
    box['minutes_n'] = box.minutes.map(minutes)
    assert not box.duplicated(['game_id', 'person_id']).any()
    groups = {gid: g for gid, g in box.groupby('game_id')}
    totals = {gid: g for gid, g in schedule.groupby('game_id')}
    regular_ids = set(schedule.loc[schedule.game_id.str.startswith(f'002{str(year-1)[2:]}'), 'game_id'])
    file_ledger = json.loads((RAW / 'file_screen_ledger.json').read_text())
    archive_ids = {r['game_id'] for r in file_ledger if r['game_id'] in regular_ids}
    ambiguous_home_away_ids = []
    for gid in sorted(regular_ids):
        g = totals[gid]
        if (len(g) != 2 or g.matchup.str.contains(' vs. ', regex=False).sum() != 1 or
                g.matchup.str.contains(' @ ', regex=False).sum() != 1):
            ambiguous_home_away_ids.append(gid)
    records, settlement_counts = [], Counter()
    for selected in selections:
        row = {k: v for k, v in selected.items() if k != 'reference_pair_evidence'}
        gid = row['game_id']
        bg, sg = groups.get(gid), totals.get(gid)
        reason = None
        reconciled = (bg is not None and sg is not None and len(sg) == 2 and
                      set(bg.team_id.astype(int)) == set(row['team_ids']))
        if reconciled:
            for s in sg.itertuples():
                tb = bg[bg.team_id.eq(s.team_id)]
                if len(tb) < 5 or tb.points.isna().any() or int(tb.points.sum()) != int(s.pts) or abs(tb.minutes_n.sum() - float(s.min)) > 1:
                    reconciled = False
        if not reconciled:
            reason = 'team_box_points_or_minutes_not_reconciled'
        player = bg[bg.person_id.eq(row['person_id'])] if bg is not None else pd.DataFrame()
        if reason is None and len(player) != 1:
            reason = 'selected_player_missing_or_ambiguous_box_row'
        if reason is None and int(player.iloc[0].team_id) not in row['team_ids']:
            reason = 'selected_player_team_outside_fixture'
        if reason is not None:
            row.update({'settlement': 'unsettled', 'reason': reason, 'net_profit': None, 'raw_net_profit': None})
        else:
            p = player.iloc[0]
            actual, time = float(p.points), float(p.minutes_n)
            row.update({'actual_points': actual, 'minutes': time, 'box_comment': None if pd.isna(p.comment) else str(p.comment)})
            if time <= 0:
                explicit = actual == 0 and re.search(r'\b(DNP|DND|NWT|INACTIVE)\b', str(p.comment), re.I)
                row.update({'settlement': 'void' if explicit else 'unsettled',
                    'reason': 'explicit_DNP_reconciled_box' if explicit else 'zero_minutes_without_explicit_DNP_evidence',
                    'net_profit': 0.0 if explicit else None, 'raw_net_profit': 0.0 if explicit else None})
            elif actual != int(actual) or int(p.team_id) not in row['team_ids']:
                row.update({'settlement': 'unsettled', 'reason': 'invalid_points_or_team_identity', 'net_profit': None, 'raw_net_profit': None})
            else:
                win = (actual > row['line']) if row['side'] == 'Over' else (actual < row['line'])
                row.update({'settlement': 'win' if win else 'loss', 'reason': 'full_game_points_including_overtime',
                    'net_profit': .98 * (row['fd_decimal'] - 1) if win else -1.0,
                    'raw_net_profit': row['fd_decimal'] - 1 if win else -1.0})
        settlement_counts[row['settlement']] += 1
        if row['settlement'] == 'unsettled':
            settlement_counts['unsettled_' + row['reason']] += 1
        records.append(row)
    settled = [r for r in records if r['settlement'] in ('win', 'loss')]
    profit = np.array([r['net_profit'] for r in settled])
    raw_profit = np.array([r['raw_net_profit'] for r in settled])
    n = len(profit)
    if n:
        rng = np.random.default_rng(390013)
        bootstrap = np.array([rng.choice(profit, size=n, replace=True).mean() for _ in range(10000)])
        interval = np.quantile(bootstrap, [.025, .975]).tolist()
        cumulative = np.r_[0.0, np.cumsum(profit)]
        max_drawdown = float(np.max(np.maximum.accumulate(cumulative) - cumulative))
        roi = float(profit.mean())
    else:
        interval, max_drawdown, roi = [None, None], None, None
    gate = n >= 100 and roi > 0 and interval[0] > 0
    result = {'season': f'{year-1}-{str(year)[2:]}', 'evaluation_completed_utc': now(),
        'status': 'promising_backtest_not_verified_edge' if gate else ('underpowered' if n < 100 else 'failed_fixed_roi_gate'),
        'promising_backtest_gate_passed': bool(gate), 'declaration_sha256': DECLARATION_SHA,
        'frozen_selections_sha256': sha(FREEZE), 'selection_summary_sha256': sha(Path(str(PREFIX) + '-selection.json')),
        'first_period_report_sha256_before_reserved_unlock': sha(first_report) if year == 2026 else None,
        'inputs': inputs, 'selected_games': len(records), 'settled_games': n,
        'coverage': {'nba_stats_regular_games': len(regular_ids), 'mapped_original_quote_games': len(archive_ids),
            'regular_game_ids_without_mapped_original_quotes': sorted(regular_ids - archive_ids),
            'ambiguous_nba_stats_home_away_game_ids': ambiguous_home_away_ids,
            'ambiguous_fixture_note': 'Five neutral-site games each season have both NBA Stats team matchup rows marked @. No home side inferred; none had mapped quote files in the fixed archive.'},
        'settlement_counts': dict(settlement_counts), 'unit_profit_after_haircut': float(profit.sum()),
        'raw_unit_profit': float(raw_profit.sum()), 'haircut_roi': roi,
        'raw_roi': float(raw_profit.mean()) if n else None, 'game_bootstrap_95_roi_interval': interval,
        'maximum_chronological_drawdown_units': max_drawdown,
        'selected_start_range': [min(r['reported_start'] for r in records), max(r['reported_start'] for r in records)] if records else [],
        'closes_missing': len(records), 'accepted_fills_verified': 0, 'suspension_state_verified': 0,
        'limitations': ['Consensus is a fallible probability reference, not a verified fair value.',
            'Early pregame snapshots are not closing prices; single snapshot cannot measure CLV.',
            'Full-game including-OT and explicit-DNP voids are hypothetical settlement, not verified historical jurisdiction terms.',
            'Game boxes require exact team points and combined player minutes within one minute of published team totals; zero-minute players require explicit DNP/inactive evidence.',
            'No collector reception clock, suspension history, accepted fill, limits or current market availability.',
            'Historical NBA identities use identity-only columns from full box archives; membership/outcomes do not select players.',
            '2024-25 scores were inspected for prior unrelated studies; first period is exploratory.',
            '2025-26 chronological replication uses a third-party-selected archive already analyzed by its publisher; it is not prospective untouched-market evidence.',
            'This card is one of multiple hypotheses researched; nominal bootstrap interval does not adjust for the wider search.'],
        'selections_with_settlement': records}
    dump(output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ['inputs', 'selections_with_settlement', 'limitations']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'evaluate', 'fetch-support'])
    parser.add_argument('--season', type=int, choices=[2025, 2026])
    args = parser.parse_args()
    if args.mode == 'fetch-support':
        fetch_support()
    elif args.mode == 'prepare':
        prepare()
    else:
        assert args.season, '--season is required'
        evaluate(args.season)


if __name__ == '__main__':
    main()
