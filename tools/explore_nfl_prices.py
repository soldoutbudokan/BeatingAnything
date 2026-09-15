#!/usr/bin/env python3
"""A fixed, outcome-free same-line price screen; no fitted model or betting action."""
# %% Read the exact archive and normalize paired half-point lines.
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import duckdb

DB = Path('data/raw/nfl-source-audit/nfl_odds.duckdb')
PIN = 'b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c'
OUT = Path('reports/nfl-price-screen-2026-09-13')


def fair(prices):
    inverse = [1 / p for p in prices]
    total = sum(inverse)
    low, high = 1., 10.
    for _ in range(60):
        mid = (low + high) / 2
        if sum(q ** mid for q in inverse) > 1:
            low = mid
        else:
            high = mid
    return [q / total for q in inverse], [q ** ((low + high) / 2) for q in inverse]


def excess(price, probability):
    return probability * (1 + .98 * (price - 1)) - 1


def load():
    with DB.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    if digest != PIN:
        raise ValueError('Different archive; preserve the source pin and label a new screen')
    db = duckdb.connect(str(DB), read_only=True)
    # A h2h-backed ID removes the known extra raw-total event artifact. No result labels read.
    boundaries = dict(db.execute('''SELECT event_id, min(commence_time) FROM raw_odds
        WHERE event_id IN (SELECT event_id FROM raw_odds WHERE bookmaker_key='fanduel'
          AND market_key='h2h') GROUP BY event_id''').fetchall())
    rows = db.execute('''SELECT DISTINCT event_id, captured_at, bookmaker_key, market_key,
        bookmaker_last_update, home_team, away_team, outcome_name, outcome_price, outcome_point
        FROM raw_odds WHERE bookmaker_key IN ('fanduel','pinnacle')
        AND market_key IN ('spreads','totals') ORDER BY captured_at''').fetchall()
    db.close()
    groups = defaultdict(list)
    for event, captured, book, market, update, home, away, side, price, point in rows:
        groups[event, captured, book, market].append((update, home, away, side, price, point))
    rejected, pairs = Counter(), {}
    for (event, captured, book, market), group in groups.items():
        reason = None
        if event not in boundaries:
            reason = 'no_h2h_backed_event'
        elif len(group) != 2:
            reason = 'not_exactly_two_unambiguous_sides'
        elif len({(g[0], g[1], g[2]) for g in group}) != 1:
            reason = 'inconsistent_pair_metadata_or_update'
        if reason:
            rejected[reason] += 1
            continue
        update, home, away = group[0][:3]
        age = (captured - update).total_seconds() if update else None
        sides = {g[3]: g for g in group}
        names = ['Over', 'Under'] if market == 'totals' else [home, away]
        if set(sides) != set(names) or len(sides) != 2:
            rejected['unexpected_outcome_names'] += 1
            continue
        ordered = [sides[name] for name in names]
        american, points = [g[4] for g in ordered], [g[5] for g in ordered]
        # Publisher v1.1.1 extract/config.py explicitly sets odds_format='american'.
        if any(p is None or not math.isfinite(p) or abs(p) < 100 for p in american):
            rejected['invalid_price'] += 1
            continue
        prices = [1 + p / 100 if p > 0 else 1 + 100 / abs(p) for p in american]
        if any(p is None or not math.isfinite(p) for p in points):
            rejected['invalid_line'] += 1
            continue
        if (points[0] != points[1] if market == 'totals' else points[0] != -points[1]):
            rejected['inconsistent_opposite_lines'] += 1
            continue
        if abs(points[0] * 2 - round(points[0] * 2)) > 1e-8 or round(points[0] * 2) % 2 != 1:
            rejected['not_half_point_line'] += 1
            continue
        if age is None or not 0 <= age <= 90:
            rejected['not_fresh_0_to_90_seconds'] += 1
            continue
        vig = sum(1 / p for p in prices) - 1
        if not -1e-12 <= vig <= .08 + 1e-12:
            rejected['outside_0_to_8pct_overround'] += 1
            continue
        lead = (boundaries[event] - captured).total_seconds()
        if lead <= 0:
            rejected['not_before_conservative_source_start'] += 1
            continue
        pairs[event, captured, book, market] = dict(
            event=event, captured=captured, market=market, line=points[0],
            home=home, away=away, sides=names, prices=prices, lead=lead,
            update=update, vig=vig)
    return pairs, rejected, len(rows), boundaries


# %% Compare exact same snapshots/lines; keep the first qualifying event only.
def screen(pairs):
    counts = Counter()
    comparisons, qualifying, closes = [], [], defaultdict(list)
    for (event, captured, book, market), pair in pairs.items():
        if book == 'pinnacle' and pair['lead'] <= 1800:
            closes[event, market, pair['line'], pair['home'], pair['away']].append(pair)
        if book != 'fanduel' or not 3600 <= pair['lead'] <= 86400:
            continue
        counts['eligible_fanduel_pairs_in_entry_window'] += 1
        reference = pairs.get((event, captured, 'pinnacle', market))
        if reference is None:
            counts['missing_fresh_paired_reference'] += 1
            continue
        if any(pair[k] != reference[k] for k in ('line', 'home', 'away', 'sides')):
            counts['different_line_or_identity'] += 1
            continue
        counts['matched_pairs'] += 1
        prop, power = fair(reference['prices'])
        for side in range(2):
            price = pair['prices'][side]
            if not 1.2 <= price <= 6:
                continue
            row = dict(event=event, market=market, line=pair['line'], side=pair['sides'][side],
                       captured_at=captured, home=pair['home'], away=pair['away'],
                       price=price, side_index=side, source_start_lead_seconds=pair['lead'],
                       proportional_excess=excess(price, prop[side]), power_excess=excess(price, power[side]))
            row['conservative_excess'] = min(row['proportional_excess'], row['power_excess'])
            comparisons.append(row)
            if row['conservative_excess'] >= .03:
                qualifying.append(row)
    selected = {}
    for row in sorted(qualifying, key=lambda r: (r['captured_at'], -r['conservative_excess'], r['market'], r['side'])):
        selected.setdefault(row['event'], row.copy())
    for row in selected.values():
        later = [p for p in closes[row['event'], row['market'], row['line'], row['home'], row['away']]
                 if p['captured'] > row['captured_at']]
        row['closing_reference'] = None
        if later:
            last = max(later, key=lambda p: p['captured'])
            prop, power = fair(last['prices'])
            row['closing_reference'] = dict(captured_at=last['captured'],
                lead_seconds=last['lead'], conservative_excess=min(
                    excess(row['price'], prop[row['side_index']]), excess(row['price'], power[row['side_index']])))
    return counts, comparisons, qualifying, list(selected.values())


def mean(values):
    return sum(values) / len(values) if values else None


# %% Record exploratory evidence; probabilities/returns are conditional on the reference.
def main():
    pairs, rejected, nrows, boundaries = load()
    counts, comparisons, qualifying, selected = screen(pairs)
    by_market = {}
    for market in ('spreads', 'totals'):
        all_rows = [r for r in comparisons if r['market'] == market]
        hits = [r for r in qualifying if r['market'] == market]
        chosen = [r for r in selected if r['market'] == market]
        close = [r['closing_reference']['conservative_excess'] for r in chosen if r['closing_reference']]
        by_market[market] = dict(compared_sides=len(all_rows), qualifying_sides=len(hits),
            qualifying_events=len({r['event'] for r in hits}), selected_events=len(chosen),
            maximum_reference_excess=max((r['conservative_excess'] for r in all_rows), default=None),
            selected_mean_reference_excess=mean([r['conservative_excess'] for r in chosen]),
            selected_with_same_line_nearstart_reference=len(close),
            mean_nearstart_reference_excess=mean(close))
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), phase='exploration',
        source_sha256=PIN, source_odds_format='american', raw_distinct_rows=nrows, h2h_backed_events=len(boundaries),
        pair_rejections=dict(rejected), pairing_counts=dict(counts), by_market=by_market,
        total_selected_events=len(selected), outcomes_read=False, verified_edge=False,
        limitations=['Pinnacle is a fallible reference; implied excess is not realized return.',
          'Coarse publisher snapshots and source starts do not prove actionable price or official-start CLV.',
          'Settlement compatibility and direct execution remain unverified; no outcomes or live quotes read.',
          'One first observation per event; repeated qualifying snapshots are not independent bets.',
          'Half-point spreads/totals only; zero-score and void treatment remain unverified.',
          'Earliest recorded source start uses archive-wide metadata and is a conservative retrospective filter.'])
    OUT.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
    local = Path('data/processed/nfl-price-screen-candidates.json')
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(json.dumps(selected, indent=2, default=str)+'\n')
    lines = ['# NFL same-line price screen — September 13, 2026', '',
        'This screen compares historical prices only. It reads no game outcomes and demonstrates no betting edge.', '',
        'The exact [NFL archive](https://github.com/bobby-king3/nfl-market-movement-tracker/releases/tag/v1.1.1) '
        'is unchanged from the market inventory. Unlike the unavailable derivative route, this asks whether '
        'FanDuel offered better main spread/total prices than a same-time, same-line Pinnacle reference. '
        'No sport model is fitted.', '',
        'Rules were written on [the card](../docs/hypotheses/book-nfl-same-line-disagreement.md) before reading differences. '
        'Both pairs must be fresh (0–90 seconds), have 0–8% overround and an identical half-point line. '
        'Entry is one to 24 hours before the earliest source start. Require at least +3% after a 2% haircut '
        'to net winnings under both proportional and power no-vig methods; keep only the first qualifying '
        'snapshot per event and its best side. This is a reference-implied score, not an estimated true return.', '',
        '| Market | Compared sides | Qualifying sides / events | Selected events | Nearstart same-line references |',
        '| --- | ---: | ---: | ---: | ---: |']
    for market, row in by_market.items():
        lines.append(f"| {market} | {row['compared_sides']} | {row['qualifying_sides']} / {row['qualifying_events']} | "
                     f"{row['selected_events']} | {row['selected_with_same_line_nearstart_reference']} |")
    decision = ('No observation clears the prewritten +3% requirement; deprioritize this exact '
                'half-point, fresh-pair, one-to-24-hour archive route without lowering the threshold.'
                if not selected else 'Fewer than the prewritten 100-event minimum is sparse exploratory evidence, not confirmation.'
                if len(selected) < 100 else 'The count screen is met; direct execution and prospective validation remain unverified.')
    lines += ['', f"Selected **{len(selected)} distinct events**. {decision}", '',
        'American prices are converted to decimal using the publisher\'s versioned configuration. '
        'An initial schema check incorrectly assumed decimal units and rejected every pair before producing '
        'any valid comparison; the units were corrected uniformly before this result. No thresholds changed.', '',
        'All selected exposure stays counted when a closing reference is absent. The 30-minute reference '
        'uses the conservative archive start, not independently verified actual kickoff; its scores are not '
        'certified closing-line value. Full aggregate counts and reference scores are in the adjacent JSON. '
        'Candidate rows remain in ignored `data/processed/nfl-price-screen-candidates.json`.', '',
        'Reproduce with the pinned database and DuckDB 1.5.5:', '', '```bash',
        'PYTHONPATH=state/runtime/nfl-audit-lib python tools/explore_nfl_prices.py', '```', '',
        'No price-disagreement result by itself establishes accurate probabilities, executable FanDuel offers, '
        'settlement equivalence, positive realized ROI, or the required prospective evidence. No wager or alert.', '']
    OUT.with_suffix('.md').write_text('\n'.join(lines))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
