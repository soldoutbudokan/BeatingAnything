#!/usr/bin/env python3
"""Card 40 source-only FanDuel main/alternate payoff consistency; no outcomes."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import backtest_nba_points_consensus as source39

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/nba-consensus-price'
DECLARATION = ROOT / 'docs/nba-points-payoff-coverage-declaration-2026-09-13.md'
DECLARATION_SHA = '4f4711a658e2d6d15746a1b718dcd04e0e248d3f1d26f1c1efccd0f05aa5e7bf'
OUTPUT = ROOT / 'reports/nba-points-payoff-coverage-2026-09-13.json'


def eligible_offers(book, snapshot, identities, counts):
    markets = book.get('markets', [])
    keys = Counter(m.get('key') for m in markets)
    offers = []
    for market in markets:
        key = market.get('key')
        if key not in ('player_points', 'player_points_alternate'):
            continue
        counts[f'{key}_market_objects'] += 1
        if keys[key] != 1:
            counts['duplicate_market_objects_rejected'] += 1
            continue
        try:
            ages = [(snapshot - source39.dt(value)).total_seconds()
                    for value in (book.get('last_update'), market.get('last_update'))]
        except (ValueError, TypeError):
            counts['missing_or_invalid_clock_markets'] += 1
            continue
        if any(age < 0 for age in ages):
            counts['future_update_markets'] += 1
            continue
        if any(age > 300 for age in ages):
            counts['stale_update_markets'] += 1
            continue
        groups = defaultdict(list)
        for outcome in market.get('outcomes', []):
            person_ids = identities.get(source39.norm(outcome.get('description')), set())
            if len(person_ids) != 1:
                counts['unresolved_identity_outcome_rows'] += 1
                continue
            if outcome.get('name') not in ('Over', 'Under'):
                counts['invalid_side_rows'] += 1
                continue
            try:
                line, price = float(outcome['point']), float(outcome['price'])
            except (KeyError, TypeError, ValueError):
                counts['invalid_line_or_price_rows'] += 1
                continue
            if not math.isfinite(line) or line % 1 != .5:
                counts['non_half_point_rows'] += 1
                continue
            # Group before price-range rejection so a conflicting invalid-price
            # duplicate cannot leave behind an apparently unique valid offer.
            groups[(next(iter(person_ids)), line, outcome['name'])].append((outcome, price))
        for (person, line, side), rows in groups.items():
            if len(rows) != 1:
                counts['ambiguous_same_market_person_line_side_groups'] += 1
                continue
            outcome, price = rows[0]
            if not math.isfinite(price) or not 1.20 <= price <= 6.00:
                counts['out_of_bounds_decimal_offers'] += 1
                continue
            effective = 1 + .98 * (price - 1)
            offers.append({'person_id': person, 'player_name': outcome['description'],
                'market_key': key, 'line': line, 'side': side, 'decimal_price': price,
                'effective_decimal_after_haircut': effective,
                'book_last_update': book['last_update'], 'market_last_update': market['last_update'],
                'book_age_seconds': ages[0], 'market_age_seconds': ages[1]})
            counts[f'eligible_{key}_{side}_offers'] += 1
    return offers


def main():
    assert source39.sha(DECLARATION) == DECLARATION_SHA, 'Card 40 declaration changed'
    assert not OUTPUT.exists(), 'Preserve existing result; do not overwrite'
    inputs = source39.checked_inputs()
    selection = json.loads((ROOT / 'reports/nba-points-consensus-2026-09-13-selection.json').read_text())
    assert source39.sha(RAW / 'frozen_selections.json') == selection['frozen_selections_sha256']
    assert source39.sha(RAW / 'file_screen_ledger.json') == selection['file_screen_ledger_sha256']
    identities, fixtures = source39.identities_and_fixtures()  # Identity/date columns only.
    ledger = json.loads((RAW / 'file_screen_ledger.json').read_text())
    fixed = [r for r in ledger if r['status'] in ('qualifying_candidates', 'no_qualifying_candidate')]
    assert len(fixed) == 2446
    counts, seasons, candidates = Counter(), defaultdict(Counter), []
    best = None
    source_pins = []
    for item in fixed:
        gid = item['game_id']
        fixture = fixtures[gid]
        year = fixture['season']
        path = RAW / 'archive' / Path(item['source_path']).name
        assert source39.sha(path) == item['source_sha256']
        obj = json.loads(path.read_text())
        event = obj['data']
        assert event['id'] == item['event_id'] and obj['timestamp'] == item['source_snapshot']
        assert source39.team(event['home_team']) == source39.team(fixture['home_team'])
        assert source39.team(event['away_team']) == source39.team(fixture['away_team'])
        snapshot = source39.dt(obj['timestamp'])
        assert snapshot < source39.dt(event['commence_time'])
        assert fixture['independent_start'] and snapshot < source39.dt(fixture['independent_start'])
        counts['fixed_independently_verified_quote_files'] += 1
        seasons[year]['verified_quote_files'] += 1
        books = [b for b in event.get('bookmakers', []) if b['key'] == 'fanduel']
        if len(books) != 1:
            counts['missing_or_duplicate_fanduel_book_objects'] += 1
            continue
        offers = eligible_offers(books[0], snapshot, identities, counts)
        counts['eligible_offers'] += len(offers)
        by_player = defaultdict(list)
        for offer in offers:
            by_player[offer['person_id']].append(offer)
        event_candidates = 0
        for player_offers in by_player.values():
            overs = [o for o in player_offers if o['side'] == 'Over']
            unders = [o for o in player_offers if o['side'] == 'Under']
            for over in overs:
                for under in unders:
                    if over['line'] > under['line']:
                        counts['non_covering_over_under_pairs_excluded'] += 1
                        continue
                    counts['eligible_covering_offer_pairs'] += 1
                    seasons[year]['eligible_covering_offer_pairs'] += 1
                    q_over, q_under = 1 / over['effective_decimal_after_haircut'], 1 / under['effective_decimal_after_haircut']
                    q_sum = q_over + q_under
                    guaranteed_net = 1 / q_sum - 1
                    if best is None or guaranteed_net > best:
                        best = guaranteed_net
                    if guaranteed_net < .01:
                        counts['covering_pairs_below_one_percent_gate'] += 1
                        continue
                    s_over, s_under = q_over / q_sum, q_under / q_sum
                    # Boundary score states suffice: Over-only, Under-only,
                    # and both-winning. Half-points exclude pushes.
                    assert math.isclose(s_over + s_under, 1)
                    assert math.isclose(s_over * over['effective_decimal_after_haircut'] - 1, guaranteed_net)
                    assert math.isclose(s_under * under['effective_decimal_after_haircut'] - 1, guaranteed_net)
                    candidates.append({'game_id': gid, 'season': year, 'event_id': event['id'],
                        'person_id': over['person_id'], 'player_name': over['player_name'],
                        'home_team': fixture['home_team'], 'away_team': fixture['away_team'],
                        'game_date': fixture['game_date'], 'original_snapshot': obj['timestamp'],
                        'reported_start': event['commence_time'], 'independent_scheduled_start': fixture['independent_start'],
                        'over_offer': over, 'under_offer': under,
                        'over_fraction_total_stake': s_over, 'under_fraction_total_stake': s_under,
                        'minimum_theoretical_net_return': guaranteed_net,
                        'both_legs_win_net_return_if_overlap_hit': 2 / q_sum - 1,
                        'source_path': item['source_path'], 'source_sha256': item['source_sha256']})
                    event_candidates += 1
                    seasons[year]['candidate_offer_pairs'] += 1
        if event_candidates:
            seasons[year]['candidate_games'] += 1
        source_pins.append({'source_path': item['source_path'], 'sha256': item['source_sha256']})
    counts['candidate_offer_pairs'] = len(candidates)
    counts['candidate_games'] = len({r['game_id'] for r in candidates})
    out = {'completed_utc': datetime.now(timezone.utc).isoformat(), 'declaration_sha256': DECLARATION_SHA,
        'status': 'source_payoff_inconsistency_requires_execution_evidence' if candidates else 'failed_fixed_source_payoff_gate',
        'source_only_gate_passed': bool(candidates), 'no_player_outcomes_loaded': True,
        'source39_frozen_selections_sha256': selection['frozen_selections_sha256'],
        'source39_file_screen_ledger_sha256': selection['file_screen_ledger_sha256'],
        'source39_selection_report_sha256': source39.sha(ROOT / 'reports/nba-points-consensus-2026-09-13-selection.json'),
        'source_pins': inputs, 'attrition': dict(counts),
        'by_season': {str(y): dict(c) for y, c in seasons.items()},
        'maximum_minimum_theoretical_return_observed': best, 'candidates': candidates,
        'coverage_proof': 'For half-points L<=H and every integer x: if x>L the Over wins; otherwise x<=L<=H and x<H, so Under wins. No push exists. With q_i=1/D_i and stake q_i/sum(q), each sole-winning leg pays 1/sum(q) on unit total stake.',
        'limitations': ['Original snapshots do not verify simultaneous availability, reception time, suspension or both accepted fills.',
            'The payoff calculation requires both legs to settle identically on the same full-game points total; historical jurisdiction/void terms are not verified.',
            'Source includes previously inspected card39 prices and third-party archive selection, not untouched or forward evidence.',
            'An apparent source inconsistency is not executable arbitrage or a verified edge. No wager or alert.']}
    source39.dump(OUTPUT, out)
    print(json.dumps({k: v for k, v in out.items() if k not in ('source_pins', 'candidates', 'limitations')}, indent=2))


if __name__ == '__main__':
    main()
