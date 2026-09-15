# NFL same-line price screen — September 13, 2026

This screen compares historical prices only. It reads no game outcomes and demonstrates no betting edge.

The exact [NFL archive](https://github.com/bobby-king3/nfl-market-movement-tracker/releases/tag/v1.1.1) is unchanged from the market inventory. Unlike the unavailable derivative route, this asks whether FanDuel offered better main spread/total prices than a same-time, same-line Pinnacle reference. No sport model is fitted.

Rules were written on [the card](../docs/hypotheses/book-nfl-same-line-disagreement.md) before reading differences. Both pairs must be fresh (0–90 seconds), have 0–8% overround and an identical half-point line. Entry is one to 24 hours before the earliest source start. Require at least +3% after a 2% haircut to net winnings under both proportional and power no-vig methods; keep only the first qualifying snapshot per event and its best side. This is a reference-implied score, not an estimated true return.

| Market | Compared sides | Qualifying sides / events | Selected events | Nearstart same-line references |
| --- | ---: | ---: | ---: | ---: |
| spreads | 910 | 0 / 0 | 0 | 0 |
| totals | 906 | 0 / 0 | 0 | 0 |

Selected **0 distinct events**. No observation clears the prewritten +3% requirement; deprioritize this exact half-point, fresh-pair, one-to-24-hour archive route without lowering the threshold.

American prices are converted to decimal using the publisher's versioned configuration. An initial schema check incorrectly assumed decimal units and rejected every pair before producing any valid comparison; the units were corrected uniformly before this result. No thresholds changed.

All selected exposure stays counted when a closing reference is absent. The 30-minute reference uses the conservative archive start, not independently verified actual kickoff; its scores are not certified closing-line value. Full aggregate counts and reference scores are in the adjacent JSON. Candidate rows remain in ignored `data/processed/nfl-price-screen-candidates.json`.

Reproduce with the pinned database and DuckDB 1.5.5:

```bash
PYTHONPATH=state/runtime/nfl-audit-lib python tools/explore_nfl_prices.py
```

No price-disagreement result by itself establishes accurate probabilities, executable FanDuel offers, settlement equivalence, positive realized ROI, or the required prospective evidence. No wager or alert.
