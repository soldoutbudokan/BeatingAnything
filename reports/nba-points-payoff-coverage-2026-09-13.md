# NBA FanDuel main/alternate payoff coverage — September 13, 2026

**No eligible pair showed a positive minimum payoff.** The fixed screen checked **40,166 covering Over/Under offer pairs** across 2,446 independently matched NBA games. Zero reached the preset +1% threshold. Even the best minimum theoretical return was **−4.49%** after the fixed haircut. This specification is closed; no player outcomes, scoring subgroups or lower thresholds were used.

This is [card 40](../docs/hypotheses/nba-points-payoff-coverage.md), a distinct internal price-consistency question following card 39's cross-book comparison. The [immutable declaration](../docs/nba-points-payoff-coverage-declaration-2026-09-13.md) preceded these comparisons. The [JSON result](nba-points-payoff-coverage-2026-09-13.json) preserves counts, input hashes and the coverage proof. This uses actual archived FanDuel offers but does not demonstrate historical fills or an executable strategy.

## Fixed comparison

Pair an Over at half-point line L with an Under at half-point line H for the same player, game and original snapshot, requiring **L ≤ H**. The literal market keys can be `player_points` or `player_points_alternate`. A market need not contain both sides; valid one-sided alternate offers can be used. Distinct offers in the main and alternate markets remain separate records. Ambiguous duplicate outcomes within a market are excluded.

For each leg with quoted decimal price d, apply a 2% haircut to net winnings: effective decimal payout **D = 1 + 0.98(d − 1)**. Put the fraction `(1/D_i) / (1/D_over + 1/D_under)` of total stake on each leg. Under identical full-game settlement, at least one leg wins at every integer point total: if points exceed L, Over wins; otherwise points are below the half-point H, so Under wins. A score in the overlap can win both. The minimum theoretical net return on total stake is:

`1 / (1/D_over + 1/D_under) − 1`.

The fixed gate was at least **+1%**. Every leg required decimal odds from 1.20 through 6.00, a half-point line, an unambiguous player identity, and both FanDuel book and market updates aged **0–300 seconds** against the original snapshot. Future update clocks were excluded; no timestamp was moved forward.

## Results and coverage

| Fixed cohort | Independently matched quote games | Covering offer pairs | Pairs passing +1% |
| --- | ---: | ---: | ---: |
| 2024–25 regular season | 1,222 | 16,197 | 0 |
| 2025–26 regular season | 1,224 | 23,969 | 0 |
| Total | 2,446 | 40,166 | 0 |

The cohort preserves card 39's NBA Stats game/person identity and fixture-date matching, with separate ESPN-derived scheduled-start checks. Both source starts follow the snapshots; actual tip times remain unverified. There are 1,230 NBA regular-season games per year, so mapped original quotes cover 99.35% and 99.51%, respectively. Missing games and the five ambiguous neutral-site fixtures per year remain as recorded in the [earlier coverage report](nba-points-consensus-2026-09-13.md). No player scoring or participation columns were loaded for this card.

The screen admitted **65,402 offer records**: 13,966 main Overs, 13,966 main Unders, 35,271 alternate Overs and 2,199 alternate Unders. It excluded 32,325 possible Over/Under pairs because L > H would leave some scores uncovered. At earlier stages it excluded 2,075 market objects with future updates, 80 with stale updates, 451 ambiguous same-market player/line/side groups, 2,235 unresolved player outcome rows, and 32,311 out-of-range decimal offers. Twenty-two fixed events lacked a unique FanDuel book object. These counts describe different stages and units; they must not be added together as a single attrition denominator.

No source pair advances to execution research. Even a positive source discrepancy would require proof that both quotes were simultaneously available, both stakes could be accepted, and both legs shared identical settlement and void rules. The archive has no verified reception time, suspension history, accepted fills, limits or historical jurisdiction-specific terms. Overlapping-market restrictions could also matter. No arbitrage or live edge is claimed; no wager or alert occurred.

## Reproduce and continue

After acquiring card 39's pinned sources and preserving its frozen original-file ledger, run:

```bash
python tools/screen_nba_points_payoff_coverage.py
```

The [script](../tools/screen_nba_points_payoff_coverage.py) reuses only identity and fixture preparation from the earlier backtest; it never invokes outcome evaluation. It rechecks each source hash and refuses to overwrite this saved result. Use an isolated reproduction while preserving archived reports. The declaration SHA-256 is `4f4711a658e2d6d15746a1b718dcd04e0e248d3f1d26f1c1efccd0f05aa5e7bf`.

Continue with a distinct mechanism. Do not lower the threshold or revisit these same two-leg combinations to obtain a positive result.
