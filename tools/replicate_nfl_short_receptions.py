#!/usr/bin/env python3
"""Run Card 38 unchanged on fixed 2023–24 inputs through source/year adapters.

The original 2025 implementation and outputs are never edited. Its tested
prepare/settle functions receive explicit module configuration here. Both
year selections and the combined selection freeze before either is graded.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import backtest_nfl_short_receptions as core

ROOT = core.ROOT
RAW = ROOT / 'data/raw/nfl-receptions-replication'
FREEZE = RAW / 'combined-frozen-selection.json'
OUT = ROOT / 'reports/nfl-short-receptions-replication-2023-24-2026-09-13.json'
DECL = ROOT / 'docs/nfl-short-receptions-replication-declaration-2026-09-13.md'
DECL_PIN = 'adb66658ac223620e161b119adb1f292c64cca042bb3d5043e667ec56fb0d241'
CORE_PIN = 'eedc26dee14c4b3d8f74bb8d02b0bce0a2dd25996e2bb306f053e239a1073483'
SELECTION = ROOT / 'reports/nfl-receptions-replication-board-selection-2026-09-13.json'
SELECTION_PIN = '5f8160289fd04a8fe8b0ebde1841724b409c6f7278c9e4aa403c21742adf5f1e'
PBP_PINS = {2023: '4649804ee0f0a40b41e51ec75a1ce921949d7fab5459213488656b92f78560e8',
            2024: '23370d5d10f8104d80d46a1fc5e61f4f6f5a3263fe96fe2dd629913cfcb08c06'}
PART_PINS = {2023: 'ad01aeb4045ee19a4f086ff38b52b14c8f427d3401e529c3078a4545921650a9',
             2024: 'b1f436a98b2a7759eb4ed1181e072a35c2666f9aeb356a49c943d28d6be6b0b9'}
ORIGINAL_PINS = dict(core.PINS)
ORIGINAL_VERIFY = core.verified_sources
ORIGINAL_DUMP = core.dump
ACTIVE_YEAR = None


def games_for(year):
    result = []
    with (ROOT / ORIGINAL_PINS['games'][0]).open() as f:
        for row in csv.DictReader(f):
            if row['season'] != str(year) or row['game_type'] != 'REG':
                continue
            start = datetime.fromisoformat(row['gameday'] + 'T' + row['gametime']).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(core.timezone.utc)
            result.append({k: row[k] for k in ['game_id', 'home_team', 'away_team', 'week']} | {'start': start})
    assert len(result) == 272
    return result


def boards():
    assert core.sha(SELECTION) == SELECTION_PIN
    selection = json.loads(SELECTION.read_text())
    loaded, manifest = [], []
    for item in selection['files']:
        path = RAW / 'boards' / (item['fixture_date'] + '.json')
        data = path.read_bytes()
        assert len(data) == item['size']
        assert hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest() == item['sha'], path
        value = json.loads(data)
        loaded.append(value)
        manifest.append({'path': str(path.relative_to(ROOT)), 'source_path': item['path'],
                         'sha256': hashlib.sha256(data).hexdigest(), 'git_blob_sha': item['sha'], 'bytes': len(data)})
    return loaded, {'source_repository': selection['source_repository'], 'source_commit': selection['source_commit'],
                    'selection_sha256': SELECTION_PIN, 'boards': len(loaded), 'files': manifest}


def verify():
    assert core.sha(Path(core.__file__)) == CORE_PIN, 'Original Card 38 implementation changed'
    sources = ORIGINAL_VERIFY()
    _, metadata = boards()
    sources['spread_boards'] = metadata
    return sources


def paired_spreads(games):
    loaded, _ = boards()
    accepted, rejected = defaultdict(list), Counter()
    for board in loaded:
        captured = core.date(board['timestamp'])
        for event in board['data']:
            if event.get('sport_key') != 'americanfootball_nfl':
                rejected['wrong_sport'] += 1
                continue
            start = core.date(event['commence_time'])
            f = core.match_fixture(event['home_team'], event['away_team'], start, games)
            if f is None:
                rejected['not_this_year_regular_fixture'] += 1
                continue
            fd = [b for b in event.get('bookmakers', []) if b.get('key') == 'fanduel']
            if len(fd) != 1:
                rejected['not_one_fanduel_book'] += 1
                continue
            book = fd[0]
            markets = [m for m in book.get('markets', []) if m.get('key') == 'spreads']
            if len(markets) != 1 or len(markets[0].get('outcomes', [])) != 2:
                rejected['not_exactly_one_paired_spread_market'] += 1
                continue
            market = markets[0]
            try:
                updated, market_updated = core.date(book['last_update']), core.date(market['last_update'])
            except (KeyError, ValueError):
                rejected['missing_or_invalid_quote_clock'] += 1
                continue
            if not all(0 <= (captured - x).total_seconds() <= 300 for x in (updated, market_updated)) or captured >= min(start, f['start']):
                rejected['stale_future_or_poststart_spread'] += 1
                continue
            outcomes = market['outcomes']
            sides = {x['name']: x for x in outcomes}
            if set(sides) != {event['home_team'], event['away_team']} or any(x.get('price') is None or abs(x['price']) < 100 or x.get('point') is None for x in outcomes):
                rejected['invalid_spread_side_or_american_price'] += 1
                continue
            if sides[event['home_team']]['point'] != -sides[event['away_team']]['point']:
                rejected['nonopposite_spread_lines'] += 1
                continue
            prices = [1 + x['price'] / 100 if x['price'] > 0 else 1 + 100 / abs(x['price']) for x in outcomes]
            vig = sum(1 / x for x in prices) - 1
            if not -1e-12 <= vig <= .08 + 1e-12:
                rejected['spread_overround_outside_gate'] += 1
                continue
            accepted[f['game_id']].append({'event_id': event['id'], 'captured': captured, 'reported_start': start,
                'updated': updated, 'market_updated': market_updated, 'lines': {core.NAMES[x['name']]: x['point'] for x in outcomes}, 'overround': vig})
    for key, group in accepted.items():
        clocks = Counter(r['captured'] for r in group)
        rejected['ambiguous_game_capture_pairs'] += sum(clocks[r['captured']] > 1 for r in group)
        accepted[key] = [r for r in group if clocks[r['captured']] == 1]
    return accepted, dict(rejected)


def adapted_dump(path, value):
    # Metadata labels are generalized; no eligibility or outcome logic changes.
    if 'attrition' in value:
        value['attrition'] = {k.replace('2025', 'evaluation_year'): v for k, v in value['attrition'].items()}
        value['evaluation_season'] = ACTIVE_YEAR
    if 'limitations' in value:
        value['limitations'] = [s.replace('2025', str(ACTIVE_YEAR)) for s in value['limitations']]
    for collection in ('eligible_price_rows', 'selected', 'rows'):
        if isinstance(value.get(collection), list):
            for row in value[collection]:
                row['evaluation_season'] = ACTIVE_YEAR
    ORIGINAL_DUMP(path, value)


def configure(year):
    global ACTIVE_YEAR
    ACTIVE_YEAR = year
    core.CARD, core.CARD_PIN = DECL, DECL_PIN
    core.RAW = RAW / str(year)
    core.FREEZE = core.RAW / 'frozen-selection.json'
    core.OUT = core.RAW / 'graded-result.json'
    core.PINS = {'props': ORIGINAL_PINS['props'], 'games': ORIGINAL_PINS['games'],
                 'pbp': (f'data/raw/nfl-wind-kicks/play_by_play_{year}.csv.gz', PBP_PINS[year]),
                 'participation': (f'data/raw/nfl-garbage-receptions/pbp_participation_{year}.csv', PART_PINS[year])}
    core.fixtures = lambda: games_for(year)
    core.spread_pairs = paired_spreads
    core.verified_sources = verify
    core.dump = adapted_dump


def source_audit():
    summary = {}
    for year in (2023, 2024):
        games = games_for(year)
        spreads, rejection = paired_spreads(games)
        with (ROOT / ORIGINAL_PINS['props'][0]).open() as f:
            props = list(csv.DictReader(f))
        mapped = matched = 0
        eligible_games = set()
        for p in props:
            f = core.match_fixture(p['home_team'], p['away_team'], core.date(p['commence_time']), games)
            if not f:
                continue
            mapped += 1
            captured = core.date(p['requested_snapshot_time'])
            earlier = [s for s in spreads.get(f['game_id'], []) if 0 < (captured - s['captured']).total_seconds() <= 21600]
            if earlier:
                matched += 1
                eligible_games.add(f['game_id'])
        summary[str(year)] = {'mapped_reception_pairs': mapped, 'pairs_with_time_eligible_spread_before_role_and_prop_filters': matched,
                              'games_with_time_eligible_spread': len(eligible_games), 'valid_spread_board_pairs': sum(map(len, spreads.values())), 'spread_rejections': rejection}
    result = {'completed_at_utc': core.now(), 'source_selection_sha256': SELECTION_PIN, 'source_only_no_outcomes': True, 'by_year': summary}
    ORIGINAL_DUMP(ROOT / 'reports/nfl-receptions-replication-source-audit-2026-09-13.json', result)
    print(json.dumps(result, indent=2))


def prepare():
    if FREEZE.exists():
        raise FileExistsError('Combined replication selection is already frozen')
    years, selected = {}, []
    for year in (2023, 2024):
        configure(year)
        if not core.FREEZE.exists():
            core.prepare()
        freeze_hash = json.loads((core.RAW / 'freeze-hash.json').read_text())['sha256']
        assert core.sha(core.FREEZE) == freeze_hash
        data = json.loads(core.FREEZE.read_text())
        assert data['declaration_sha256'] == DECL_PIN
        years[str(year)] = {'selection_sha256': freeze_hash, 'prepared_at_utc': data['prepared_at_utc'], 'attrition': data['attrition']}
        selected.extend(data['selected'])
    assert len(selected) == len({r['game_id'] for r in selected})
    result = {'prepared_at_utc': core.now(), 'declaration_sha256': DECL_PIN, 'original_2025_core_sha256': CORE_PIN,
              'period': [2023, 2024], 'year_freezes': years, 'selected': selected, 'outcomes_used_for_selection': False}
    ORIGINAL_DUMP(FREEZE, result)
    ORIGINAL_DUMP(RAW / 'combined-freeze-hash.json', {'sha256': core.sha(FREEZE), 'prepared_at_utc': result['prepared_at_utc']})
    print(json.dumps({'combined_frozen_games': len(selected), 'combined_selection_sha256': core.sha(FREEZE)}, indent=2))


def combined_summary(rows):
    known = [r['profit_units'] for r in rows if r['profit_units'] is not None]
    unknown = len(rows) - len(known)
    rng = np.random.default_rng(1738)
    ci = np.quantile(rng.choice(known, size=(10000, len(known)), replace=True).mean(axis=1), [.025, .975]).tolist() if known else None
    roi = float(np.mean(known)) if known else None
    pessimistic = (sum(known) - unknown) / len(rows) if rows else None
    passed = len(known) >= 50 and roi > 0 and ci[0] > 0 and pessimistic > 0
    status = 'unresolved_below_50_settled_games' if len(known) < 50 else 'exploratory_replication_gate_pass' if passed else 'failed_fixed_return_gate'
    return {'selected_games': len(rows), 'settled_games': len(known), 'unknown_settlements': unknown,
            'wins': sum(r['outcome'] == 'win' for r in rows), 'losses': sum(r['outcome'] == 'loss' for r in rows),
            'profit_units': float(sum(known)), 'stake_units': len(known), 'roi': roi,
            'game_bootstrap_95_roi': ci, 'pessimistic_unknown_loss_roi': pessimistic,
            'unknown_void_roi': roi, 'haircut_fraction_of_net_winnings': .02, 'status': status}


def settle():
    pin = json.loads((RAW / 'combined-freeze-hash.json').read_text())['sha256']
    assert core.sha(FREEZE) == pin
    combined = json.loads(FREEZE.read_text())
    assert combined['declaration_sha256'] == DECL_PIN
    all_rows, years = [], {}
    sources = {}
    for year in (2023, 2024):
        configure(year)
        assert core.sha(core.FREEZE) == combined['year_freezes'][str(year)]['selection_sha256']
        core.settle()
        graded = json.loads(core.OUT.read_text())
        all_rows.extend(graded['rows'])
        years[str(year)] = {'summary': graded['summary'], 'status': graded['status'], 'attrition': graded['attrition']}
        sources[str(year)] = graded['sources']
    assert {(r['game_id'], r['player_id'], r['line']) for r in all_rows} == {(r['game_id'], r['player_id'], r['line']) for r in combined['selected']}
    summary = combined_summary(all_rows)
    report = {'completed_at_utc': core.now(), 'declaration_sha256': DECL_PIN, 'selection_sha256': pin,
              'prepared_at_utc': combined['prepared_at_utc'], 'evaluation_period': [2023, 2024],
              'original_2025_result_preserved_and_not_pooled': True, 'summary': summary, 'by_year': years,
              'sources': sources, 'rows': all_rows,
              'limitations': ['Separate prior-period exploratory replication; not forward or untouched confirmation.',
                  'The fixed 16:55 UTC archive boards produce incomplete timing coverage, especially early Sunday games and some post-DST primetime.',
                  'No prices from the future, later closing spreads, source-guessed teams, or outcome-fitted thresholds fill gaps.',
                  'Historical FanDuel jurisdiction and injury-protection settlement equivalence and executable stakes remain unverified.',
                  'The combined 2023–24 period was fixed before selection and before either year was graded; 2025 was not pooled.'],
              'attribution': 'nflverse/nflfastR PBP CC BY 4.0; FTN participation via nflverse CC BY-SA 4.0. Original third-party odds files remain ignored.'}
    ORIGINAL_DUMP(OUT, report)
    print(json.dumps({'combined': summary}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['source-audit', 'prepare', 'settle'])
    args = parser.parse_args()
    {'source-audit': source_audit, 'prepare': prepare, 'settle': settle}[args.phase]()
