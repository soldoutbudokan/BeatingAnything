# 2026 first-score validation: positive small sample, no established edge

**The unchanged candidate earns +3.80 simulated units over seven selections (+54.29% ROI): one win, six losses, no voids or unresolved settlements.** One decimal-11.0 winner supplies all winnings. This is another positive exploratory observation, with too little evidence and insufficient quote-timing assurance to establish an edge.

## Frozen experiment

The [source audit](nba-first-score-2026-source-audit-2026-09-19.md) checks 221 predetermined regular-season fixtures. Both books have active pregame history in 73; the [fixed evaluation rules](../docs/nba-first-score-2026-validation-protocol-2026-09-19.md) retain **16 games**, March 22–April 9, spanning three calendar weeks. The original 2024 prior statistics, probability conversion and selection kernel are unchanged. Twenty-nine player appearances lack a 2024 rate and use the declared league fallback.

Forecasts were frozen and pushed to main as **`4046681` before target scoring/starter columns were read**. The [manifest](nba-first-score-2026-forecast-freeze-2026-09-19.json) records forecast SHA-256 `354eeaaa23e6cf1534b43e910ac0198466c88384830ea6309ff5e9863130c8bf`, input/code hashes, all exclusions and seven primary/five reserve selections. The [full result](nba-first-score-2026-validation-2026-09-19.json) retains outcome and settlement counts plus the graded artifact hash. All 16 independent first scores resolve; all are listed players. Realized starters enter settlement only.

| Fixed rule | Selections | Wins / losses / voids / unknown | Profit | ROI over every original stake |
| --- | ---: | --- | ---: | ---: |
| Original conversion | 7 | 1 / 6 / 0 / 0 | +3.80 | +54.29% |
| Original 0.99 probability reserve | 5 | 1 / 4 / 0 / 0 | +5.80 | +116.00% |
| All twenty history entries at most 300 seconds old | 0 | 0 / 0 / 0 / 0 | — | — |

Winning profits include the predeclared 2% haircut. Both unresolved-settlement sensitivities coincide because none is unknown. The reserve result shares the same winner; it is not an independent discovery. The winner is Daniss Jenkins, Detroit–Minnesota on April 2, at decimal 11.0; the independent first score is a two-point basket at 11:45 of the first quarter. These are retrospective simulated bets, not wagers.

## Forecast quality and mechanism

Lower is better. Scores use the original 1% unlisted-scorer bucket across all 16 games.

| Probability source | Mean log loss | Mean Brier score |
| --- | ---: | ---: |
| Converted BetMGM | 2.325586 | 0.902581 |
| Unconverted BetMGM | 2.325957 | 0.902488 |
| Normalized FanDuel | 2.386775 | 0.911564 |

Conversion improves mean log loss by only **0.000371** versus raw BetMGM and slightly worsens Brier score. Its larger log-loss improvement versus FanDuel is **0.061189**. All seven selections already have positive modeled EV using unconverted BetMGM. The result therefore does not isolate free-throw conversion as the reason for the apparent opportunity. BetMGM itself is an imperfect reference, not established fair value.

There are only seven settled selections across two betting weeks, below the previous sample gates and the eight-week minimum for any declared bootstrap interval. No confidence interval is reported. Do not pool source-incompatible 2025 and 2026 records to manufacture one. The original comparison family remains 16 and all advancement requirements remain in force.

## Why this remains conditional

- The historical API records provider entries. The experiment assumes each last active state persists to the fixed five-minute pregame decision. Historical executable availability, latency and bookmaker-update clocks are unverified. None of the 16 boards has all twenty entries within 300 seconds. Median last-entry age is about 261 seconds at FanDuel and 1,195 seconds at BetMGM; maximum ages are about 3.6 and 12.6 hours respectively.
- Dated rules support FanDuel first basket including free throws and BetMGM first field goal excluding them. The original quote's jurisdiction and displayed label are still absent, so the mapping is conditional.
- Coverage is sparse. Among 114 non-Friday fixtures with successful histories, FanDuel has exactly ten active players at decision in 24, zero in 44, one through nine in 39, and more than ten in seven. Three identity exclusions and five incomplete reference boards reduce the 24 to 16. The main loss of coverage is absent/incomplete boards; selecting realized starters or renormalizing partial boards would change the experiment.
- This is historical research with no prospective evidence. No wagers, alerts or scheduled collectors are enabled.

## Next action

Preserve this positive, underpowered result. The acquisition and validation are complete, with no process left running. The next useful evidence is **complete paired first-score/first-field-goal boards observed before tip, with original labels and contemporaneous receipt/update clocks**, either from a genuinely new dated archive or a separately declared prospective manual collection. Do not rerun the same month, relax its candidate count or adjust the cutoff after these outcomes. The promising lead remains a FanDuel/BetMGM price discrepancy; the free-throw explanation and any actionable edge remain unconfirmed. All **287 tests pass**.
