#!/usr/bin/env python3
"""Card 38: fixed FanDuel pregame prop test, with selection before settlement.

PBP: nflverse/nflfastR, CC BY 4.0. Participation: FTN via nflverse,
CC BY-SA 4.0; derived participation identity records retain that attribution.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nfl-short-receptions'
CARD = ROOT / 'docs/hypotheses/football-underdog-short-receptions.md'
CARD_PIN = 'e05f4250b7d30867be75f51b3202b659688ed2ebe7144db419dd6de51914e82d'
FREEZE = RAW / 'frozen-selection.json'
OUT = ROOT / 'reports/nfl-short-receptions-backtest-2026-09-13.json'
PINS = {
    'props': ('data/raw/new-prop-archive-sample/nfl/fanduel_receptions_history.csv', '795ae85ed74b0b1ad4971f8e2951a61704e79aff3138b760d3ec8fe802a2282d'),
    'games': ('data/raw/nfl-key-number/games.csv', '0c34a519753ada6b5b37f5e8be246021813484adb15ae7c067af9c3aca534d2d'),
    'pbp': ('data/raw/nfl-wind-kicks/play_by_play_2025.csv.gz', '2f135887790a013fd004e609e37096bb4816d5cc80b9f19122e1bad478961978'),
    'participation': ('data/raw/nfl-garbage-receptions/pbp_participation_2025.csv', '59069adfee7b0f464befba8a5e8be331e523633cc6a7ab403d37bcbcdfbe66ac'),
    'spreads': ('data/raw/nfl-source-audit/nfl_odds.duckdb', 'b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c'),
}
NAMES = dict(zip([
    'Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears',
    'Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Denver Broncos','Detroit Lions','Green Bay Packers',
    'Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Las Vegas Raiders',
    'Los Angeles Chargers','Los Angeles Rams','Miami Dolphins','Minnesota Vikings','New England Patriots',
    'New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers',
    'San Francisco 49ers','Seattle Seahawks','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders'],
    ['ARI','ATL','BAL','BUF','CAR','CHI','CIN','CLE','DAL','DEN','DET','GB','HOU','IND','JAX','KC','LV','LAC','LA',
     'MIA','MIN','NE','NO','NYG','NYJ','PHI','PIT','SF','SEA','TB','TEN','WAS']))


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def stamp(value):
    return value.isoformat()


def date(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def norm(value):
    words = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    words = re.sub(r'\b(jr|sr|ii|iii|iv)\.?$', '', words.strip())
    return re.sub('[^a-z0-9]', '', words)


def verified_sources():
    assert sha(CARD) == CARD_PIN, 'Declaration changed'
    sources = {}
    for key, (name, pin) in PINS.items():
        path = ROOT / name
        assert sha(path) == pin, name
        sources[key] = {'path': name, 'sha256': pin, 'bytes': path.stat().st_size}
    return sources


def fixtures():
    result = []
    with (ROOT / PINS['games'][0]).open() as f:
        for row in csv.DictReader(f):
            if row['season'] != '2025' or row['game_type'] != 'REG':
                continue
            start = datetime.fromisoformat(row['gameday'] + 'T' + row['gametime']).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
            result.append({k: row[k] for k in ['game_id', 'home_team', 'away_team', 'week']} | {'start': start})
    assert len(result) == 272
    return result


def match_fixture(home, away, start, games):
    home, away = NAMES.get(home), NAMES.get(away)
    matched = [f for f in games if f['home_team'] == home and f['away_team'] == away and abs((f['start'] - start).total_seconds()) <= 900]
    return matched[0] if len(matched) == 1 else None


def valid_snap(pbp):
    return pbp.play_type.isin(['pass', 'run', 'qb_kneel', 'qb_spike']) & pbp.down.notna() & ~pbp.two_point_attempt.eq(1) & pbp.posteam.notna()


def identities_and_targets():
    cols = ['game_id', 'play_id', 'season_type', 'posteam', 'play_type', 'down', 'two_point_attempt', 'receiver_player_id', 'air_yards']
    pbp = pd.read_csv(ROOT / PINS['pbp'][0], usecols=cols, low_memory=False)
    assert not pbp.duplicated(['game_id', 'play_id']).any()
    pbp = pbp.loc[pbp.season_type.eq('REG') & valid_snap(pbp)]
    target = pbp.loc[pbp.play_type.eq('pass') & pbp.receiver_player_id.notna()]
    totals = target.groupby(['game_id', 'posteam', 'receiver_player_id']).agg(targets=('air_yards', 'size'), observed=('air_yards', 'count'), depth_sum=('air_yards', 'sum')).to_dict('index')
    parts = pd.read_csv(ROOT / PINS['participation'][0], usecols=['nflverse_game_id', 'play_id', 'possession_team', 'offense_players', 'offense_names', 'n_offense'], low_memory=False).rename(columns={'nflverse_game_id': 'game_id'})
    assert not parts.duplicated(['game_id', 'play_id']).any()
    merged = pbp[['game_id', 'play_id', 'posteam']].merge(parts, on=['game_id', 'play_id'], how='inner', validate='one_to_one')
    names = defaultdict(lambda: defaultdict(set))
    appearance = defaultdict(set)
    for r in merged.itertuples():
        if r.posteam != r.possession_team or r.n_offense != 11 or not isinstance(r.offense_players, str) or not isinstance(r.offense_names, str):
            continue
        ids, labels = r.offense_players.split(';'), r.offense_names.split(';')
        if len(ids) != 11 or len(set(ids)) != 11 or len(labels) != 11 or not all(re.fullmatch(r'00-\d{7}', x) for x in ids):
            continue
        for pid, label in zip(ids, labels):
            names[r.game_id, r.posteam][norm(label)].add(pid)
            appearance[r.game_id, r.posteam].add(pid)
    return totals, names, appearance


def spread_pairs(games):
    db = duckdb.connect(str(ROOT / PINS['spreads'][0]), read_only=True)
    rows = db.execute("""SELECT DISTINCT event_id, captured_at, commence_time, bookmaker_last_update,
        home_team, away_team, outcome_name, outcome_price, outcome_point
        FROM raw_odds WHERE bookmaker_key='fanduel' AND market_key='spreads' ORDER BY captured_at""").fetchall()
    db.close()
    grouped = defaultdict(list)
    for r in rows:
        grouped[r[0], r[1]].append(r)
    accepted = defaultdict(list)
    rejected = Counter()
    for (event, clock), group in grouped.items():
        if len(group) != 2 or len({r[2:6] for r in group}) != 1:
            rejected['ambiguous_pair_metadata'] += 1
            continue
        r = group[0]
        captured, start, updated = date(clock), date(r[2]), date(r[3]) if r[3] else None
        f = match_fixture(r[4], r[5], start, games)
        if f is None:
            rejected['unmatched_regular_season_fixture'] += 1
            continue
        if updated is None or not 0 <= (captured - updated).total_seconds() <= 300 or captured >= min(start, f['start']):
            rejected['stale_future_or_poststart_spread'] += 1
            continue
        sides = {x[6]: x for x in group}
        if set(sides) != {r[4], r[5]} or any(x[7] is None or abs(x[7]) < 100 or x[8] is None for x in group):
            rejected['invalid_spread_side_or_price'] += 1
            continue
        if sides[r[4]][8] != -sides[r[5]][8]:
            rejected['nonopposite_spread_lines'] += 1
            continue
        prices = [1 + x[7] / 100 if x[7] > 0 else 1 + 100 / abs(x[7]) for x in group]
        vig = sum(1 / x for x in prices) - 1
        if not -1e-12 <= vig <= .08 + 1e-12:
            rejected['spread_overround_outside_gate'] += 1
            continue
        accepted[f['game_id']].append({'event_id': event, 'captured': captured, 'reported_start': start,
              'updated': updated, 'lines': {NAMES[x[6]]: x[8] for x in group}, 'overround': vig})
    for key, group in accepted.items():
        clocks = Counter(r['captured'] for r in group)
        accepted[key] = [r for r in group if clocks[r['captured']] == 1]
    return accepted, dict(rejected)


def prepare():
    if FREEZE.exists():
        raise FileExistsError('Selection is frozen; do not overwrite')
    sources = verified_sources()
    games = fixtures()
    totals, aliases, _ = identities_and_targets()
    spreads, spread_reject = spread_pairs(games)
    with (ROOT / PINS['props'][0]).open() as f:
        # Deliberately ignore publisher team/context fields and all estimated-week fields.
        props = [{k: r[k] for k in ['event_id', 'home_team', 'away_team', 'commence_time', 'requested_snapshot_time',
                  'bookmaker_key', 'market_key', 'bookmaker_last_update', 'market_last_update', 'player', 'line', 'over_price', 'under_price']}
                 for r in csv.DictReader(f)]
    prices_seen = Counter(tuple(r[k] for k in ['event_id', 'requested_snapshot_time', 'player', 'line']) for r in props)
    counts = Counter({'source_prop_rows_all_seasons': len(props)})
    eligible = []
    for r in props:
        start, captured = date(r['commence_time']), date(r['requested_snapshot_time'])
        f = match_fixture(r['home_team'], r['away_team'], start, games)
        if f is None:
            counts['not_mapped_to_2025_regular_season'] += 1
            continue
        counts['mapped_2025_prop_rows'] += 1
        if r['bookmaker_key'] != 'fanduel' or r['market_key'] != 'player_receptions' or captured >= min(start, f['start']):
            counts['wrong_book_market_or_poststart'] += 1
            continue
        key = tuple(r[k] for k in ['event_id', 'requested_snapshot_time', 'player', 'line'])
        if prices_seen[key] != 1:
            counts['duplicate_prop_key'] += 1
            continue
        try:
            line, over, under = map(float, (r['line'], r['over_price'], r['under_price']))
            updated, market_updated = date(r['bookmaker_last_update']), date(r['market_last_update'])
        except (ValueError, TypeError):
            counts['missing_or_invalid_prop_fields'] += 1
            continue
        if not all(math.isfinite(x) for x in (line, over, under)) or line <= 0 or not math.isclose(line * 2, round(line * 2)) or round(line * 2) % 2 != 1 or not all(1.2 <= x <= 6 for x in (over, under)):
            counts['invalid_halfpoint_or_price_range'] += 1
            continue
        if not 0 <= (captured - updated).total_seconds() <= 300 or not 0 <= (captured - market_updated).total_seconds() <= 300:
            counts['stale_or_future_prop_clock'] += 1
            continue
        vig = 1 / over + 1 / under - 1
        if not -1e-12 <= vig <= .08 + 1e-12:
            counts['prop_overround_outside_gate'] += 1
            continue
        counts['valid_pregame_prop_price_rows'] += 1
        identities = []
        prior_map = {}
        for team in (f['home_team'], f['away_team']):
            previous = sorted((g for g in games if team in (g['home_team'], g['away_team']) and g['start'].date() < captured.date()), key=lambda g: g['start'])[-3:]
            if len(previous) != 3:
                continue
            ids = {pid for g in previous for pid in aliases.get((g['game_id'], team), {}).get(norm(r['player']), set())}
            prior_map[team] = [g['game_id'] for g in previous]
            identities.extend((team, pid) for pid in ids)
        if len(identities) != 1:
            counts['no_unique_prior_fullname_team_identity'] += 1
            continue
        team, pid = identities[0]
        previous = prior_map[team]
        stats = [totals.get((gid, team, pid)) for gid in previous]
        stats = [s for s in stats if s is not None]
        total = sum(s['targets'] for s in stats)
        observed = sum(s['observed'] for s in stats)
        depth = sum(s['depth_sum'] for s in stats)
        if observed < 10 or total == 0 or observed / total < .9 or depth / observed > 8 or len(stats) < 2:
            counts['failed_fixed_prior_short_target_role'] += 1
            continue
        counts['short_role_prop_rows'] += 1
        earlier = [s for s in spreads.get(f['game_id'], []) if 0 < (captured - s['captured']).total_seconds() <= 21600]
        if not earlier:
            counts['no_fresh_earlier_spread_within_six_hours'] += 1
            continue
        spread = max(earlier, key=lambda s: s['captured'])
        if spread['lines'][team] < 6.5:
            counts['not_substantial_underdog_at_prior_quote'] += 1
            continue
        eligible.append({'game_id': f['game_id'], 'week': int(f['week']), 'event_id': r['event_id'], 'team': team, 'player_id': pid,
            'player': r['player'], 'line': line, 'over_decimal_price': over, 'under_decimal_price': under, 'overround': vig,
            'snapshot_utc': stamp(captured), 'book_update_utc': stamp(updated), 'market_update_utc': stamp(market_updated),
            'prop_reported_start_utc': stamp(start), 'independent_scheduled_start_utc': stamp(f['start']),
            'prior_games': previous, 'prior_targets': int(total), 'prior_observed_depths': int(observed),
            'prior_mean_depth': depth / observed, 'prior_target_games': len(stats),
            'spread_line': spread['lines'][team], 'spread_event_id': spread['event_id'],
            'spread_snapshot_utc': stamp(spread['captured']), 'spread_book_update_utc': stamp(spread['updated']),
            'spread_reported_start_utc': stamp(spread['reported_start']), 'spread_overround': spread['overround']})
    first = {}
    for row in sorted(eligible, key=lambda r: r['snapshot_utc']):
        first.setdefault((row['game_id'], row['player_id']), row)
    selected = {}
    for row in sorted(first.values(), key=lambda r: (r['prior_mean_depth'], -r['prior_targets'], r['player_id'])):
        selected.setdefault(row['game_id'], row)
    counts['eligible_price_rows'] = len(eligible)
    counts['unique_eligible_player_games'] = len(first)
    counts['selected_games'] = len(selected)
    result = {'prepared_at_utc': now(), 'declaration_sha256': CARD_PIN, 'sources': sources,
              'outcomes_used_for_selection': False, 'attrition': dict(counts), 'spread_pair_rejections': spread_reject,
              'eligible_price_rows': eligible, 'selected': sorted(selected.values(), key=lambda r: r['snapshot_utc'])}
    dump(FREEZE, result)
    dump(RAW / 'freeze-hash.json', {'sha256': sha(FREEZE), 'prepared_at_utc': result['prepared_at_utc']})
    print(json.dumps({'phase': 'selection_frozen', 'selection_sha256': sha(FREEZE), 'attrition': dict(counts)}, indent=2))


def settle():
    verified_sources()
    pin = json.loads((RAW / 'freeze-hash.json').read_text())
    assert sha(FREEZE) == pin['sha256']
    frozen = json.loads(FREEZE.read_text())
    cols = ['game_id', 'play_id', 'season_type', 'posteam', 'play_type', 'down', 'two_point_attempt',
            'receiver_player_id', 'complete_pass', 'rusher_player_id', 'passer_player_id']
    pbp = pd.read_csv(ROOT / PINS['pbp'][0], usecols=cols, low_memory=False)
    pbp = pbp.loc[pbp.season_type.eq('REG') & valid_snap(pbp)]
    _, _, appearances = identities_and_targets()
    results = []
    for row in frozen['selected']:
        block = pbp.loc[pbp.game_id.eq(row['game_id']) & pbp.posteam.eq(row['team'])]
        pid = row['player_id']
        statistical = bool(block.receiver_player_id.eq(pid).any() or block.rusher_player_id.eq(pid).any() or block.passer_player_id.eq(pid).any())
        verified = pid in appearances.get((row['game_id'], row['team']), set()) or statistical
        catches = int((block.play_type.eq('pass') & block.receiver_player_id.eq(pid) & block.complete_pass.eq(1)).sum())
        profit = (.98 * (row['over_decimal_price'] - 1) if catches > row['line'] else -1.) if verified else None
        results.append(row | {'participation_verified': verified, 'credited_receptions': catches if verified else None,
                             'outcome': ('win' if catches > row['line'] else 'loss') if verified else 'unknown', 'profit_units': profit})
    settled = [r['profit_units'] for r in results if r['profit_units'] is not None]
    unknown = len(results) - len(settled)
    rng = np.random.default_rng(1738)
    ci = np.quantile(rng.choice(settled, size=(10000, len(settled)), replace=True).mean(axis=1), [.025, .975]).tolist() if settled else None
    roi = float(np.mean(settled)) if settled else None
    pessimistic = (sum(settled) - unknown) / len(results) if results else None
    void = sum(settled) / len(settled) if settled else None
    passed = len(settled) >= 50 and roi > 0 and ci[0] > 0 and pessimistic > 0
    status = 'unresolved_below_50_settled_games' if len(settled) < 50 else 'exploratory_gate_pass' if passed else 'failed_fixed_return_gate'
    report = {'completed_at_utc': now(), 'card': 38, 'declaration_sha256': CARD_PIN, 'selection_sha256': pin['sha256'],
              'prepared_at_utc': frozen['prepared_at_utc'], 'sources': frozen['sources'], 'status': status,
              'attrition': frozen['attrition'], 'spread_pair_rejections': frozen['spread_pair_rejections'],
              'summary': {'selected_games': len(results), 'settled_games': len(settled), 'unknown_settlements': unknown,
                          'wins': sum(r['outcome'] == 'win' for r in results), 'losses': sum(r['outcome'] == 'loss' for r in results),
                          'stake_units': len(settled), 'profit_units': float(sum(settled)), 'roi': roi,
                          'game_bootstrap_95_roi': ci, 'pessimistic_unknown_loss_roi': pessimistic,
                          'unknown_void_roi_settled_stake_denominator': void,
                          'unknown_void_return_per_selected_game': sum(settled) / len(results) if results else None,
                          'haircut_fraction_of_net_winnings': .02}, 'rows': results,
              'limitations': ['Exploratory 2025 sample already inspected for other questions; not independent confirmation.',
                  'Archived listed prices, no accepted wagers or original collector reception clocks.',
                  'No source for same-line closing comparison; no closing-line-value claim.',
                  'Historical jurisdiction-specific settlement and injury-protection rules unverified.',
                  'PBP reception accounting includes overtime and excludes nullified plays and two-point attempts.',
                  'Prior participation aliases are identity evidence, not current availability; selected unknown cases remain visible.'],
              'attribution': 'nflverse/nflfastR PBP CC BY 4.0; FTN participation via nflverse CC BY-SA 4.0. No third-party raw data redistributed.'}
    dump(OUT, report)
    print(json.dumps({'status': status, 'summary': report['summary']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'settle'])
    args = parser.parse_args()
    prepare() if args.phase == 'prepare' else settle()
