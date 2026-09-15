# NBA FanDuel points consensus backtest — September 13, 2026

**The fixed rule did not produce enough bets to indicate an edge.** Across two almost complete regular seasons, only **one** FanDuel player-points side cleared the preset price-discrepancy threshold. It won, but one result provides no useful evidence of repeatable profitability. The 100-settled-game gate failed in both periods. No threshold, reference-book requirement, clock rule or player alias was changed to increase the sample.

This executes [card 39](../docs/hypotheses/nba-points-consensus-shading.md) with actual archived FanDuel prices, rather than inferring an edge from a sporting effect. The [declaration](../docs/nba-points-consensus-declaration-2026-09-13.md) preceded price comparisons. Both periods' selections were frozen at **18:37:12 UTC**; the [2024–25 report](nba-points-consensus-2026-09-13-2025.json) was written at 18:38:35 before the [2025–26 report](nba-points-consensus-2026-09-13-2026.json) was evaluated at 18:38:43. Those first-period outcomes were previously examined for unrelated research; the later period is a chronological replication within a third-party archive already analyzed by its publisher. Neither is prospective market evidence.

## Inputs and coverage

The [pinned publisher archive](https://github.com/devlincorrigan/nba-props-threshold-app/tree/233dbbc86b9c6e13df04d4e8b063581b3aa15abb) supplied **3,394 original JSON files**, 397,273,601 bytes, representing 3,394 distinct events. Every original matched its published Git blob hash and SHA-256. The separately verified event/game mapping has 3,354 unique pairs. Forty events lacked that mapping; 908 mapped files fell outside the two fixed regular seasons. Both exclusions preceded any bet selection.

| Coverage | 2024–25 | 2025–26 |
| --- | ---: | ---: |
| NBA Stats regular-season games | 1,230 | 1,230 |
| Games with mapped original quote files | 1,222 | 1,224 |
| Missing mapped quote games | 8 | 6 |
| Independent home/away fixtures constructible | 1,225 | 1,225 |
| Quote games passing independent fixture/start checks | 1,222 | 1,224 |

The five fixture ambiguities each year are neutral-site games where both NBA Stats matchup rows say `@`; none had mapped quotes here. No home side was inferred. The machine-readable period reports enumerate every missing game ID. Independent NBA Stats team/date/game IDs came from the [schedule release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_schedules). Additional ESPN-derived exact scheduled starts came from the [separate schedule release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_schedules); actual tip times remain unverified. Identity-only columns from the [NBA Stats boxscore release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_boxscores) mapped full player names to person IDs before scores were loaded. Fifteen unresolved name variants were excluded, including suffix differences; no manual aliases were inferred.

## Fixed price screen

Use the literal `player_points` market and an identical player/half-point line with one Over and one Under. Each pair needs decimal odds 1.20–6.00, overround 0–12%, and both book and market updates no more than 300 seconds old and never later than the **original** archive timestamp. FanDuel is excluded from the reference set. Include every qualifying other book, requiring at least three. Median proportional-devig and power-devig reference probabilities yield two expected returns at the FanDuel price, each after a 2% haircut to net winnings. The smaller must reach 3%. Select at most one side per game at the earliest qualifying snapshot, with predeclared deterministic ties.

| Attrition across the fixed periods | Count |
| --- | ---: |
| FanDuel paired player/line quotes surviving identity, clocks and price checks | 13,966 |
| Pairs with fewer than three eligible reference books | 7,895 |
| Pairs with three or more references | 6,071 |
| Evaluated sides | 12,142 |
| Sides below the fixed score threshold | 12,141 |
| Qualifying sides / selected games | 1 / 1 |

FanDuel had 1,027 book/market objects rejected for a future update, 44 for an update older than 300 seconds, and 26 with a missing or duplicate main market. Its 784 unresolved player outcome rows were excluded before pairing. These are different stages and units, not additive player-pair counts. The [selection report](nba-points-consensus-2026-09-13-selection.json) preserves every book's attrition, unresolved names and source pins. Complete original-file and candidate ledgers remain with the ignored raw inputs, with their hashes saved publicly.

## Settlement results

| Fixed period | Selected | Settled | Wins | Losses | Voids | Unsettled | Haircut profit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024–25 exploratory | 0 | 0 | 0 | 0 | 0 | 0 | 0 units |
| 2025–26 chronological check | 1 | 1 | 1 | 0 | 0 | 0 | +0.9212 units |

The sole selection was **Luke Kornet Over 7.5 points**, San Antonio versus Portland on **April 8, 2026**, FanDuel decimal **1.94**. The original snapshot was 12:05:38 UTC. The three qualifying references were BetOnline, Bovada and Caesars (`williamhill_us`), producing proportional and power median probabilities of 54.38% and 54.84%; conservative haircut expected return was 4.47%. Kornet's independently matched NBA box row recorded **10 points in 26:01**. Full-game team points reconciled exactly and player minutes were within the pre-result one-minute team-total tolerance.

The odds archive reported 00:10 UTC as the event start; the separate schedule reports 01:30 UTC. Both are on April 8 in New York time and both follow the price snapshot by more than 12 hours. This start-time discrepancy is retained explicitly, rather than replacing either clock.

With one settled bet, raw ROI is +94% and haircut ROI +92.12%, with zero observed drawdown. **Those percentages describe a single win and do not estimate a strategy's edge.** The mechanical one-game bootstrap has the same result in every resample; its degenerate interval supplies no statistical evidence. The independently required minimum of 100 settled games prevents advancement. There are no same-line closes, accepted fills or verified suspension states. Settlement assumes full-game points including overtime and explicit DNP voids, not verified historical jurisdiction-specific terms. Missing or ambiguous player rows remain unknown; they are never silently voided. No wager was placed.

Independent review verified all 3,395 original quote/mapping blobs, recomputed the price screen with a separate grouping method and root solver, reproduced the sole selection and settlement, and confirmed the five neutral-site fixture ambiguities per year. Both new scripts compile.

## Reproduce and continue

```bash
python tools/acquire_nba_prop_archive.py --fetch
python tools/backtest_nba_points_consensus.py fetch-support
python tools/backtest_nba_points_consensus.py prepare
python tools/backtest_nba_points_consensus.py evaluate --season 2025
python tools/backtest_nba_points_consensus.py evaluate --season 2026
```

These are the original execution commands. Run a reproduction in an isolated checkout while retaining the saved reports separately; do not overwrite the archived results. The acquisition step retrieves missing pinned public inputs only; changed bytes fail. Preparation and evaluation refuse to overwrite existing frozen selections or period reports. Keep original quote and box data out of the public repo. The new [acquisition script](../tools/acquire_nba_prop_archive.py) and [backtest](../tools/backtest_nba_points_consensus.py) are reusable assets for a distinctly declared question, not a reason to retune this completed screen. The declaration SHA-256 is `c97142492881b0a2616944bbdcb5a24e409717f643431f70057f77cbcfb50747`; frozen selection SHA-256 is `a5b074270f02ba21d145ab0b8d57642107a57469352a58fac4aacaf49b973cfe`.

**Next:** close this specification as underpowered at its fixed settings. Pursue a distinct mechanism or genuinely new independent price evidence. Do not expand or retune this sample because its single selected bet won.
