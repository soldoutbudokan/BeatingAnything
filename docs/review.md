# Independent review

Reviewed the data join, feature chronology, residual model, annual walk-forward evaluation and prospective monitoring design on 2026-09-08. This is an internal skeptical review, not independent certification of the source data.

## Finding

The experiment does not demonstrate a betting edge. Across 4,141 historical holdout games, the physical model's log loss is 0.67715827 versus 0.67721041 for the paired, no-vig FanDuel baseline. Its paired difference is −0.00005214, with a 97.5% weekly-block interval of [−0.00038788, +0.00028949]. It improves in 2024 and worsens in 2025. The interval includes no improvement.

Both learned models place zero simulated bets under the fixed 3% expected-value threshold. Consequently, there is no ROI estimate. The physical model's largest predicted expected value anywhere in the holdout is about 0.43%, before any execution allowance. Independently recomputing the no-vig baseline, logarithmic losses and bet eligibility from the saved predictions agrees with the reported metrics.

These are the corrected source results. The initial roster-based acquisition omitted 299 appearances across 11 player-seasons. A complete season pitching index identified the omissions; supplemental official player logs repair them without changing the candidate set or strategy-selection rule. The original results remain recorded in `reports/initial-source-results.json` and the correction is explained in `docs/research-log.md`.

## Controls inspected

- Prices and outcomes join through official MLB team IDs, date, unique game IDs, matching final scores and a start-time check. Ambiguous doubleheaders are excluded.
- The model receives no current-game outcome, final starting-pitcher assignment, actual lineup, actual weather or archived terminal price as a feature.
- Historical result and pitching records enter features only after their availability date and before the target date. Suspended-game aggregates are withheld until completion; their physical workload is excluded because its daily allocation is unknown.
- The corrected acquisition check found 12,148 completed regular-season games and 104,627 pitcher appearances. All 24,296 game-team sides have exactly one recorded starter. Independent reconciliation of pitcher outs against game innings and the home/away result found no discrepancies in games without suspension or early completion.
- Feature normalization is fitted on training rows. Regularization is selected on 2023, then frozen for the 2024 and 2025 annual walk-forward predictions. The separately saved final model is not used for historical scoring.
- All declared candidates are reported. Confidence intervals account for the two learned-model comparisons, using the stated approximate weekly dependence blocks.

## Limits that prevent promotion

Opening quotes have no capture timestamps. A feature built from yesterday's game may still have become available after a bookmaker posted today's opener. Correct feature chronology alone does not establish executable historical prices. Retrospectively corrected official records and schedule metadata also lack historical publication vintages.

The archive's `currentLine` fields show strong evidence of in-play contamination. They cannot establish closing-line value or serve as opening-to-close movement proxies and are excluded entirely.

Venue metadata and pitcher coverage have gaps that require explicit auditing. In particular, four Mexico City target games use a venue with missing coordinates or timezone metadata. Missing travel data cannot be interpreted as observed zero travel.

The Covers collector identifies explicitly labeled, paired FanDuel prices and matches them to official scheduled game IDs, teams and start times. The forward runner builds new lagged features before collecting quotes, binds each forecast to its exact quote, and preserves model versions in the ledger. These are aggregator observations, not proof of an available FanDuel offer. Actual betting alerts remain disabled.

Monitoring now separates models, artifacts, source classes and registered forward cohorts; reports the earliest eligible probability forecast independently of bet selection; and distinguishes offered-price movement from no-vig closing expected value. Promotion metadata must meet the protocol's sample, duration, uncertainty and source-quality requirements. Those checks still depend on reviewed evidence; accepting well-formed metadata is not independent verification of an edge.

Now that the holdout has been inspected, changing features, regularization choices, selection thresholds or strategy definitions and evaluating them on the same outcomes would be exploratory research. A new claim needs a separately frozen, untouched prospective cohort with timestamped predictions, paired observable FanDuel prices, verified prestart closing quotes and settled outcomes. The current artifacts must remain unproven.
