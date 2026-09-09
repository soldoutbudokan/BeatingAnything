"""Prior-2024 charting input feasibility. No target-season results or model fit."""
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    'ftn_charting_2024.csv': '6faae8118cc13ce62589210d553733128ed35e558671009b4a7a8fc5c674c2cb',
    'play_by_play_2024-feature-projection.csv': 'f129cef7e21d1e294b60e47e92d0c6b355065358e90f7ee531211f973319908d',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    result = float(value)
    if not result.is_integer():
        raise ValueError('Noninteger count or identifier')
    return int(result)


def flag(value):
    if value in ('1', '1.0', 'TRUE', 'True', 'true'):
        return True
    if value in ('0', '0.0', 'FALSE', 'False', 'false'):
        return False
    raise ValueError('Unknown boolean value')


def summarize(rows):
    groups = {}
    for name, values in [('all', rows), ('zero_rushers', [r for r in rows if r['rushers'] == 0]),
                         ('one_to_four', [r for r in rows if 1 <= r['rushers'] <= 4]),
                         ('five_to_eleven', [r for r in rows if 5 <= r['rushers'] <= 11])]:
        groups[name] = {
            'dropbacks': len(values), 'games': len({r['game'] for r in values}),
            'passer_or_scramble_identities': len({r['player'] for r in values}),
            'scrambles': sum(r['scramble'] for r in values),
            'charted_interception_worthy': sum(r['interception_worthy'] for r in values),
            'charted_qb_fault_sack': sum(r['fault_sack'] for r in values),
            'either_charted_risk_flag': sum(r['interception_worthy'] or r['fault_sack'] for r in values),
        }
    return groups


def audit():
    raw = ROOT/'data/raw/nfl-source-audit'
    for name, expected in INPUTS.items():
        if sha(raw/name) != expected:
            raise ValueError('Pinned input changed: '+name)
    with (raw/'ftn_charting_2024.csv').open(newline='') as handle:
        charting = list(csv.DictReader(handle))
    with (raw/'play_by_play_2024-feature-projection.csv').open(newline='') as handle:
        pbp = list(csv.DictReader(handle))
    if any(row['season'] != '2024' for row in charting) or any(not row['game_id'].startswith('2024_') for row in pbp):
        raise ValueError('Only prior-2024 input is permitted')
    lookup = {(r['nflverse_game_id'], number(r['nflverse_play_id'])): r for r in charting}
    if len(lookup) != len(charting) or len({(r['game_id'], number(r['play_id'])) for r in pbp}) != len(pbp):
        raise ValueError('Duplicate play identities')
    rows, reasons, marker_games, zero_games, marker_pairs = [], Counter(), Counter(), Counter(), Counter()
    for play in pbp:
        if play['qb_dropback'] in ('', 'NA', 'NaN') or not flag(play['qb_dropback']):
            continue
        record = lookup.get((play['game_id'], number(play['play_id'])))
        if record is None:
            raise ValueError('Prior dropback missing charting join')
        scramble, sack = flag(play['qb_scramble']), flag(play['sack'])
        player = play['rusher_player_id'] if scramble else play['passer_player_id']
        rushers = number(record['n_pass_rushers'])
        iw, fs = flag(record['is_interception_worthy']), flag(record['is_qb_fault_sack'])
        errors = []
        if record['starting_hash'] not in {'L', 'M', 'R'} or record['qb_location'] not in {'U', 'S', 'P'}:
            errors.append('unknown_hash_or_qb_location')
            marker_games[play['game_id']] += 1
            marker_pairs[record['starting_hash']+'|'+record['qb_location']] += 1
        if not 0 <= rushers <= 11:
            errors.append('impossible_pass_rusher_count')
        if not player:
            errors.append('missing_passer_or_scramble_identity')
        if play['play_type'] not in {'pass', 'run'}:
            errors.append('unexpected_dropback_play_type')
        if not play['posteam'] or not play['defteam'] or play['posteam'] == play['defteam']:
            errors.append('invalid_possession_identity')
        conflicts = []
        if fs and not sack:
            conflicts.append('charted_fault_sack_without_pbp_sack')
        if iw and sack:
            conflicts.append('charted_interception_worthy_on_pbp_sack')
        if iw and fs:
            conflicts.append('both_charted_risk_flags')
        reasons.update(errors+conflicts)
        if rushers == 0:
            zero_games[play['game_id']] += 1
        rows.append({'game': play['game_id'], 'player': player, 'scramble': scramble,
                     'rushers': rushers, 'interception_worthy': iw, 'fault_sack': fs,
                     'errors': errors, 'conflicts': conflicts, 'defense': play['defteam']})
    compatible = [row for row in rows if not row['errors']]
    strict = [row for row in compatible if not row['conflicts']]
    return {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'Input feasibility only; no NFL experiment or model registered',
        'scope': 'Two pinned prior-2024 inputs only; no 2025 outcome labels, odds, forecasts or betting returns read',
        'input_sha256': INPUTS, 'audit_script_sha256': sha(Path(__file__)),
        'pbp_rows': len(pbp), 'charting_rows': len(charting),
        'all_dropbacks_joined': len(rows), 'play_issue_counts_overlapping': dict(reasons),
        'unknown_marker_combinations': dict(marker_pairs),
        'unknown_marker_games': dict(sorted(marker_games.items())),
        'zero_rusher_games': dict(sorted(zero_games.items())),
        'diagnostic_masks': {
            'all_joined': summarize(rows), 'schema_compatible': summarize(compatible),
            'schema_and_cross_source_risk_consistency': summarize(strict),
        },
        'schema_compatible_defense_teams': len({r['defense'] for r in compatible}),
        'interpretation': [
            'Diagnostic masks are not a frozen feature definition or eligibility choice.',
            'Zero is physically possible for pass-rusher count and is not by itself treated as missing; unknown categorical markers and impossible counts are separate issues.',
            'Prior scramble identities use rusher_player_id; missing passer identity on a scramble is not evidence of an unknown player.',
            'Unique passer/rusher identities include occasional non-quarterback passers. No position or rookie status is inferred.',
            'Charted risk flags describe prior plays and are not target-season game results. Cross-source sack disagreement is retained explicitly, not silently repaired.',
        ],
        'field_dictionaries': [
            'https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html',
            'https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_pbp.csv',
        ],
    }


if __name__ == '__main__':
    result = audit()
    (ROOT/'reports/nfl-pressure-input-feasibility.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: result[k] for k in ('all_dropbacks_joined', 'play_issue_counts_overlapping', 'diagnostic_masks')}, indent=2))
