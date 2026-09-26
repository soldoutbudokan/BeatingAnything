# Golf player variance — September 26, 2026

**The variance adjustment slightly improved forecasts but found no mispriced bet.** The fixed rule was evaluated on 1,323 2025 FanDuel 3-ball boards across 23 events. Even the highest modeled return was -1.0809%; 0 boards had positive modeled EV. There were 0 selections at the fixed 3% threshold.

| Measure | Normalized opening price | Variance adjustment |
| --- | ---: | ---: |
| Mean log loss (lower is better) | 1.082199 | 1.081453 |
| Mean summed Brier loss | 0.579203 | 0.578761 |

Paired log-loss change is -0.000747; its event-bootstrap 95% interval is [-0.001390, -0.000124]. Mean absolute probability adjustment is 0.3419%; the largest modeled return is -1.0809%. Average quoted overround is 7.8364%.

Dead-heat ROI is undefined; strict-win-only ROI is undefined. A tie-void and full-win-on-tie sensitivity are in the JSON, along with exposure, event uncertainty, round breakdowns, and an exact-name-only sensitivity. Undefined ROI means no qualifying selections, not break-even performance.

The exact-name-only sensitivity has 1,248 boards and paired log-loss change -0.000589, with interval [-0.001286, 0.000063]. Its interval includes zero. The evidence supports at most a small forecasting lead; it does not overcome the bookmaker margin.

## Fixed mechanism and parameters

For each golfer, use the last 80 complete rounds in earlier events, requiring 40. Scores are centered on the event-round field mean; sample variance is shrunk toward 9 using 100 prior degrees of freedom. All current-event rounds are excluded. Prior event end dates must precede a conservative cutoff one day before the unzoned opening date or the current-event start, whichever is earlier.

Infer relative score means that reproduce normalized FanDuel opening probabilities under equal SD 3. Keep those means fixed and replace only relative variances, scaled to group mean 9. Rounded independent normal scores allocate half of tied-low two-player payouts and one third of three-player ties. One pick per board is allowed only at modeled EV >=3%; no threshold or variance parameter was selected using 2025 outcomes. Losses use the realized fractional share of lowest score as the outcome.

This tests individual dispersion, distinct from the failed G3 tie-allocation and G10 shared-weather hypotheses. It does not revise their results. It also does not import the source publisher's forecast or selected bets.

## Coverage and limitations

Started with 1,945 retained 2025 FanDuel 3-balls. There were 1,323 forecasts before checking score completeness. Attrition: `{'excluded_event_or_format': 288, 'insufficient_prior_rounds': 264, 'identity_unresolved': 70, 'event_not_joined': 0}`. Names join by exact normalized full name, then unique surname plus first initial within the same event; unresolved names remain excluded. Every settled player-round must have 18 distinct holes summing to its reported score. Reconstructed labels disagree with publisher labels on 0 boards; these are not silently dropped from the primary analysis.

**The price export is selected on outcomes:** `isGradedOutcome` accepts only 0, 0.5 and 1, excluding a three-way tie encoded as one third. The sample also requires publisher model availability and valid closing prices for all three players; the opening-price cohort is therefore selected using later availability. We observed 0 reconstructed three-way ties. Conditional-no-triple-tie loss sensitivity is provided, but cannot restore missing offers. The unknown original settlement rules are why several payoff conventions are shown.

Quote clocks lack zones, original source responses are absent, and no Ontario execution or historical acceptance is verified. These limitations preclude a claim of a demonstrated edge even if an exploratory metric is favorable. The full [JSON](golf-player-variance-2026-09-26.json) contains source hashes and all summaries. No new acquisition, parameter search, schedules, alerts or wagers.

Reproduce with `state/runtime/research-venv/bin/python tools/explore_golf_player_variance.py`.
