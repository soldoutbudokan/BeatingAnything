# Frozen ATP Challenger total-games research

No candidate demonstrated an unblocked historical edge under the recorded research screen.
No prospective FanDuel qualification, betting notification or wager is enabled.

Both experiments concern standard best-of-three men's Challenger matches at exactly 21.5 total games. N2 infers serving rates from prior tiebreak history and synchronized opening moneyline prices; N3 replaces that moneyline input with prior set Elo. Entries and closes are historical Pinnacle prices. All candidate and annual results below are retained; validation chooses the research candidate before holdout evaluation.

[N2 protocol](../docs/protocol-tennis-v1.md), [N3 protocol](../docs/protocol-tennis-independent-v1.md), [pre-result implementation review](../docs/tennis-implementation-review.md).

## N2

Required daily pages: 1826; frozen unique sampled events: 5453; parsed details: 5453; entry-feature-valid events: 1714.

Source evidence blocks: daily_history_parse_errors.

Declared holdout-year status:

- **2024:** `fitted`; forecasts / graded: 451 / 428; quotes unavailable at model selection: 0; graded comparison available: yes.
- **2025:** `fitted`; forecasts / graded: 373 / 352; quotes unavailable at model selection: 0; graded comparison available: yes.

Validation-selected research candidate: **workload**. Validation selection was available at 2023-12-03T23:00:00+00:00. The final post-holdout refits are separate from the annual models that generated these forecasts.

| Candidate | Forecasts / graded | Bets / graded | Model log loss | Paired loss delta | Haircut ROI | Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| market | 824 / 780 | 0 / 0 | 0.694215 | 0.000000 | unavailable | unavailable |
| calibration | 824 / 780 | 0 / 0 | 0.694148 | -0.000067 | unavailable | unavailable |
| set_shape | 824 / 780 | 0 / 0 | 0.693978 | -0.000237 | unavailable | unavailable |
| workload | 824 / 780 | 0 / 0 | 0.694066 | -0.000149 | unavailable | unavailable |

Corrected intervals use 99.61538462% confidence and calendar-week resampling. A negative paired loss delta favors the model. ROI is unavailable when there are no bets or unresolved selected outcomes. Closing EV uses only covered selected bets; its missing coverage can block the research screen.

| Candidate | Paired loss interval | Haircut ROI interval | Closing EV interval | Selected closes | Historical screen unblocked |
| --- | --- | --- | --- | ---: | --- |
| market | [0.000000, 0.000000] | unavailable | unavailable | 0 / 0 | False |
| calibration | [-0.003142, 0.003067] | unavailable | unavailable | 0 / 0 | False |
| set_shape | [-0.003129, 0.002786] | unavailable | unavailable | 0 / 0 | False |
| workload | [-0.003107, 0.002846] | unavailable | unavailable | 0 / 0 | False |

Selected turnover includes unresolved outcomes. The bounds below assign every unresolved selected bet a loss or a win; they are outcome bounds, not confidence intervals. The complete-match simulation uses its smaller settled denominator.

| Candidate | Turnover units | Ungraded bets | Haircut ROI worst / best | Complete-match bets | Complete-match haircut ROI |
| --- | ---: | ---: | --- | ---: | ---: |
| market | 0 | 0 | unavailable | 0 | unavailable |
| calibration | 0 | 0 | unavailable | 0 | unavailable |
| set_shape | 0 | 0 | unavailable | 0 | unavailable |
| workload | 0 | 0 | unavailable | 0 | unavailable |

### Annual holdout results

| Year | Candidate | Forecasts / graded | Bets / graded | Paired loss delta | Haircut ROI | Closing EV |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | market | 451 / 428 | 0 / 0 | 0.000000 | unavailable | unavailable |
| 2025 | market | 373 / 352 | 0 / 0 | 0.000000 | unavailable | unavailable |
| 2024 | calibration | 451 / 428 | 0 / 0 | -0.001681 | unavailable | unavailable |
| 2025 | calibration | 373 / 352 | 0 / 0 | 0.001896 | unavailable | unavailable |
| 2024 | set_shape | 451 / 428 | 0 / 0 | -0.001756 | unavailable | unavailable |
| 2025 | set_shape | 373 / 352 | 0 / 0 | 0.001609 | unavailable | unavailable |
| 2024 | workload | 451 / 428 | 0 / 0 | -0.001447 | unavailable | unavailable |
| 2025 | workload | 373 / 352 | 0 / 0 | 0.001428 | unavailable | unavailable |

Quotes preceding completed validation selection: 0; these remain explicitly model-unavailable in the fit audit. Ungraded selected exposure stays in turnover, with worst/best outcome bounds in the metrics. The complete-match-only sensitivity excludes that exposure and is labeled separately.

[Full metrics](tennis-n2-metrics.json), [fit and validation trials](tennis-n2-fit.json), [annual forecasts](tennis-n2-forecasts.csv).

## N3

Required daily pages: 1826; frozen unique sampled events: 5453; parsed details: 5453; entry-feature-valid events: 2950.

Source evidence blocks: daily_history_parse_errors.

Declared holdout-year status:

- **2024:** `fitted`; forecasts / graded: 636 / 606; quotes unavailable at model selection: 0; graded comparison available: yes.
- **2025:** `fitted`; forecasts / graded: 494 / 470; quotes unavailable at model selection: 0; graded comparison available: yes.

Validation-selected research candidate: **workload**. Validation selection was available at 2023-12-03T23:00:00+00:00. The final post-holdout refits are separate from the annual models that generated these forecasts.

| Candidate | Forecasts / graded | Bets / graded | Model log loss | Paired loss delta | Haircut ROI | Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| market | 1130 / 1076 | 0 / 0 | 0.690497 | 0.000000 | unavailable | unavailable |
| calibration | 1130 / 1076 | 0 / 0 | 0.690248 | -0.000249 | unavailable | unavailable |
| set_shape | 1130 / 1076 | 0 / 0 | 0.690218 | -0.000279 | unavailable | unavailable |
| workload | 1130 / 1076 | 4 / 3 | 0.690933 | 0.000436 | unavailable | -0.047791 |

Corrected intervals use 99.61538462% confidence and calendar-week resampling. A negative paired loss delta favors the model. ROI is unavailable when there are no bets or unresolved selected outcomes. Closing EV uses only covered selected bets; its missing coverage can block the research screen.

| Candidate | Paired loss interval | Haircut ROI interval | Closing EV interval | Selected closes | Historical screen unblocked |
| --- | --- | --- | --- | ---: | --- |
| market | [0.000000, 0.000000] | unavailable | unavailable | 0 / 0 | False |
| calibration | [-0.002758, 0.002207] | unavailable | unavailable | 0 / 0 | False |
| set_shape | [-0.002740, 0.002186] | unavailable | unavailable | 0 / 0 | False |
| workload | [-0.002117, 0.003067] | unavailable | [-0.089594, -0.014613] | 4 / 4 | False |

Selected turnover includes unresolved outcomes. The bounds below assign every unresolved selected bet a loss or a win; they are outcome bounds, not confidence intervals. The complete-match simulation uses its smaller settled denominator.

| Candidate | Turnover units | Ungraded bets | Haircut ROI worst / best | Complete-match bets | Complete-match haircut ROI |
| --- | ---: | ---: | --- | ---: | ---: |
| market | 0 | 0 | unavailable | 0 | unavailable |
| calibration | 0 | 0 | unavailable | 0 | unavailable |
| set_shape | 0 | 0 | unavailable | 0 | unavailable |
| workload | 4 | 1 | [-0.485400, 0.036550] | 3 | -0.313867 |

### Annual holdout results

| Year | Candidate | Forecasts / graded | Bets / graded | Paired loss delta | Haircut ROI | Closing EV |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | market | 636 / 606 | 0 / 0 | 0.000000 | unavailable | unavailable |
| 2025 | market | 494 / 470 | 0 / 0 | 0.000000 | unavailable | unavailable |
| 2024 | calibration | 636 / 606 | 0 / 0 | -0.001223 | unavailable | unavailable |
| 2025 | calibration | 494 / 470 | 0 / 0 | 0.001007 | unavailable | unavailable |
| 2024 | set_shape | 636 / 606 | 0 / 0 | -0.001213 | unavailable | unavailable |
| 2025 | set_shape | 494 / 470 | 0 / 0 | 0.000926 | unavailable | unavailable |
| 2024 | workload | 636 / 606 | 4 / 3 | -0.000437 | unavailable | -0.047791 |
| 2025 | workload | 494 / 470 | 0 / 0 | 0.001562 | unavailable | unavailable |

Quotes preceding completed validation selection: 0; these remain explicitly model-unavailable in the fit audit. Ungraded selected exposure stays in turnover, with worst/best outcome bounds in the metrics. The complete-match-only sensitivity excludes that exposure and is labeled separately.

[Full metrics](tennis-n3-metrics.json), [fit and validation trials](tennis-n3-fit.json), [annual forecasts](tennis-n3-forecasts.csv).

## Evidence limits

Historical source timestamps and final-price labels do not prove that an offer was executable, nor that a present-day FanDuel market uses the same retirement rules. Retirements and unclear scores remain ungraded instead of being assigned convenient outcomes. Complete acquisition attempts do not guarantee complete underlying history. See the individual source failures, identities, timestamp checks and content hashes in the metrics.

Any promising historical candidate still requires a frozen prospective FanDuel cohort with verified entry and closing quotes, immutable predictions, and the unchanged ROI, closing-EV and log-loss promotion gates. These results cannot authorize a betting alert.
