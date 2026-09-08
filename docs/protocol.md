# Evaluation protocol v1

Written before inspecting strategy returns. The source audit necessarily views some historical records. This is a retrospective time split, not a preregistered prospective trial.

## Market and hypotheses

MLB regular-season, full-game, two-way FanDuel moneyline. Use the archive's openingLine as the historical offer, with an explicit unresolved availability timestamp. Never use currentLine: it can include in-play prices. No measured historical CLV is possible from these files.

Hypothesis: lagged physical workload, schedule disruption, directional travel, and pitcher workload provide incremental information beyond the no-vig market. A market probability is a demanding baseline and prevents credit for simply identifying favorites. Team results/Elo are controls, not the proposed edge.

## Splits and selection

- Development: 2021–2022.
- Validation: calendar year 2023; select regularization by paired log loss only.
- Historical holdout: 2024 and 2025 through the archive's end. No tuning, feature removal, threshold changes, or strategy selection on those outcomes.
- Refit before each holdout year on previous years only, with the validation-selected hyperparameter frozen. The 2025 fit can use 2024 outcomes; this is a specified annual walk-forward procedure.
- Evaluate market baseline, a calibration-only control, and the physical-feature residual model. Report every candidate. Comparing both learned models incurs a two-comparison confidence correction.
- The final fitted artifact uses all available past data, after evaluation, and remains marked `unproven`.

## Point-in-time controls

Use official MLB game IDs and outcomes. Exclude ambiguous doubleheaders, suspended/resumed games, nonregular-season games, mismatched scores and duplicated records. Update lagged performance only after the previous calendar date, conservatively excluding same-day results. Feature chronology is necessary but insufficient: current historical datasets can contain corrections and exact FanDuel opener timestamps were stripped by the source scraper. Availability of the actual opener at the reconstructed decision time is unverified. Report results as an exploratory opening-price simulation, never realized ROI.

Do not condition inclusion on whether a particular bet won. Do not use current-game actual weather, actual lineup, final probable-pitcher assignments, late scratches, or terminal odds as opening-time features. Venue/travel locations must come from official venue metadata, with missingness explicit.

## Fixed execution simulation

One unit per eligible event; choose only the side with maximum model EV when EV >= 3%, decimal odds between 1.20 and 6.00, and two-sided overround between 0 and 8%. No parlays, best-book substitution, bonus pricing, staking optimization, or compounding. Report all-event log loss/Brier, betting sample size, turnover, profit, ROI, price-haircut sensitivity, yearly splits and max drawdown. Haircut sensitivity reduces decimal net winnings by 2%.

Uncertainty: block-bootstrap by calendar week for profit/turnover and paired per-game loss differences. Report 97.5% intervals for the two learned-model comparisons, rather than selecting the prettiest nominal 95% result. Weekly blocks approximate dependence; they do not remove source bias or make overlapping samples independent.

## Promotion gate

No model is promoted on retrospective opening-price results. Promotion requires a separately registered forward trial on timestamped, paired, actually observable FanDuel quotes, verified prestart closing quotes and immutable predictions, with no changes after the trial starts. Minimum 1,000 settled paper bets across at least 90 days; fixed analysis checkpoints (avoid repeated significance fishing); positive lower confidence bounds for ROI after execution allowance, mean no-vig closing-price EV and paired out-of-sample log-loss improvement. Any data-quality failure blocks promotion. Paper performance is not a fill guarantee.

## Research record

The archive was selected for FanDuel coverage, not profitability. Tennis was considered but its accessible free odds source lacks FanDuel and capture timestamps. No sport was selected after comparing profitable backtests. Any subsequent iteration must log its hypothesis and open a new untouched forward cohort; continuing to modify a model until a historical holdout becomes profitable invalidates that holdout.
