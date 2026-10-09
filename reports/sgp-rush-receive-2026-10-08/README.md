# NFL redundant-leg SGP prices against FanDuel

Adding an already-implied leg sometimes changed theScore Bet SGP prices. This report records every observed NFL main-line rushing-plus-receiving over / rushing under pair and evaluates the quotes against FanDuel using power and additive devig.

The census covers 24 player/line pairs across 13 of the 15 listed October 8–12, 2026 games. No combined market was observed in CLE–NYJ or BUF–LAR. Four historical or targeted constructions bring the full table to 28 constructions and 105 recorded observations. This is a census of posted main lines, not every alternate-line combination.

## Result

McCaffrey 90+ combined yards, under 54.5 rushing and 40+ receiving was quoted at +483. Adding over 34.5 receiving, already implied by 40+, repeatedly raised the quote to +854. The refreshed FanDuel partition gives model EV lower bounds of **+12.77% power** and **+6.13% additive**. The 40+ receiving leg remains part of the three-leg base; it is not redundant in the two-leg combined/rushing event.

- [McCaffrey result and containment proof](CMC-EDGE.md)
- [Every construction and recorded variant](EV-TABLE.md)
- [Sanitized numerical inputs and results](prices-and-ev.json)
- [Independent standard-library calculation](recompute_ev.py)
- [Workbook generator](build_ev_workbook.mjs)

Only derived odds, selections, calculation results and timestamps are published here. Raw sportsbook UI snapshots and screenshots are excluded. The full workbook and evidence package were delivered separately.

## Interpret the table

Exact lines give model estimates. A stricter FD event gives a lower bound; a broader FD event gives an upper bound. Crossed thresholds produce N/A. A positive upper bound does not establish an edge, and a negative lower bound does not establish negative EV. References are selected per observation, preferring complete exact-line partitions and then the nearest complete capture window. The best-quote comparison uses its nearest observed baseline.

The main-line Harvey result is positive only as an upper bound. The McCaffrey construction above is positive as a lower bound under both requested methods. These are historical quotes from October 8, not current availability or guaranteed returns. Bounds assume the devig probabilities, common yardage definitions and normal completed-game settlement.

## Reproduce

Python 3.10+ and its standard library:

```bash
python3 recompute_ev.py
```

The script makes no network requests. It independently solves the power exponent at 60-digit precision, calculates additive probabilities, checks every published EV, verifies census coverage, and checks that the FD event implies every McCaffrey base leg.

Workbook generation uses the supplied JavaScript with the Codex primary Node runtime and `@oai/artifact-tool` available:

```bash
node build_ev_workbook.mjs prices-and-ev.json ./outputs
```

The workbook contains editable odds, visible power-solver steps, additive calculations, reference times and model-bound labels. The generator verifies formula agreement, input-driven recalculation and formula-error absence.
