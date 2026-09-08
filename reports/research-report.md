# MLB moneyline experiment 1

Research date: 2026-09-08. Final corrected model: `a7ceefe2db3c13ea`.

**No exploitable edge demonstrated.** The physical model's pooled log loss is slightly lower than FanDuel's no-vig baseline, but uncertainty includes no improvement and the direction reverses between test years. No learned model clears the fixed 3% expected-value threshold on any historical test game. There is no ROI estimate or verified historical CLV.

## Data and design

MLB regular-season full-game moneyline was selected because a free archive explicitly identifies FanDuel opening prices. Tennis offered useful public sport data but the verified free odds source lacked FanDuel; comparable usable free history was not established for the other candidates. Selection preceded comparing strategy returns. See the [market-selection record](../docs/market-selection.md).

The [archive release](https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/tag/dataset) contains 13,121 rows spanning April 1, 2021 through August 16, 2025. Official MLB IDs, teams, dates, starts and final scores yield 11,043 accepted games. FanDuel pairs are never substituted with another bookmaker. Ambiguous doubleheaders and identity/result mismatches are excluded; source outliers are audited without filtering according to outcomes. The archive is pinned by SHA-256 in the [data audit](data-audit.json).

| Period | Role | Games |
| --- | --- | ---: |
| 2021 | Development | 2,280 |
| 2022 | Development | 2,275 |
| 2023 | Regularization selection | 2,347 |
| 2024 | Annual walk-forward test | 2,355 |
| 2025 through August 16 | Annual walk-forward test | 1,786 |

The baseline removes the two-sided margin proportionally. The calibration model fits an intercept correction; the physical model fits that intercept plus 21 standardized home-minus-away features. Market log odds enter with coefficient fixed at one. Features describe travel and schedule, recent innings, individual relief-pitcher workload and role-weighted fatigue, bullpen quality/coverage, and lagged form. No current-game actual starter, lineup, weather or outcome enters the predictors.

Normalization is fitted on training rows only. Each learned model selects a penalty on 2023 log loss, then refits before each test year using prior years only. The final all-history artifact is separate from historical scoring fits. The [protocol](../docs/protocol.md) was written before strategy returns were inspected; this remains a retrospective split, not a prospective preregistration.

## Selection

Both candidates choose penalty 1.0, the strongest declared value. Physical features do not improve validation log loss over the calibration control. No alternative penalty or threshold was selected from test returns.

| L2 penalty | Calibration: 2023 log loss | Physical: 2023 log loss |
| ---: | ---: | ---: |
| 0.001 | 0.6775487 | 0.6803953 |
| 0.01 | 0.6775481 | 0.6801253 |
| 0.1 | 0.6775416 | 0.6790891 |
| **1.0 — selected** | **0.6774983** | **0.6778299** |

## Historical test results

Lower log loss is better. Delta is model loss minus FanDuel loss; negative favors the model. Intervals resample calendar weeks and use 97.5% coverage for two learned-model comparisons. This approximates dependence but cannot remove source bias or price-timing uncertainty.

| Test period | Candidate | Log loss | Brier score | Loss delta | 97.5% interval for delta | Bets |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| 2024 | FanDuel baseline | 0.6760355 | 0.2415768 | 0 | Reference | 0 |
| 2024 | Calibration | 0.6760352 | 0.2415767 | −0.0000003 | [−0.0000072, +0.0000064] | 0 |
| 2024 | Physical | 0.6756922 | 0.2414091 | −0.0003433 | [−0.0006997, +0.0000255] | 0 |
| 2025 partial | FanDuel baseline | 0.6787596 | 0.2430234 | 0 | Reference | 0 |
| 2025 partial | Calibration | 0.6787767 | 0.2430318 | +0.0000171 | [−0.0000048, +0.0000389] | 0 |
| 2025 partial | Physical | 0.6790914 | 0.2431824 | +0.0003318 | [−0.0002402, +0.0008926] | 0 |
| Pooled: 4,141 games | FanDuel baseline | 0.6772104 | 0.2422007 | 0 | Reference | 0 |
| Pooled: 4,141 games | Calibration | 0.6772176 | 0.2422042 | +0.0000072 | [−0.0000032, +0.0000176] | 0 |
| Pooled: 4,141 games | Physical | 0.6771583 | 0.2421739 | −0.0000521 | [−0.0003879, +0.0002895] | 0 |

The fixed simulation chooses the highest-EV side, requires EV ≥3%, selected decimal odds from 1.20 through 6.00, and paired overround from 0% through 8%. Stakes are one unit per eligible event. The physical model's maximum test EV is about **0.432%**, below the threshold.

Every candidate has zero turnover and profit. ROI, ROI intervals, the 2% net-winnings haircut sensitivity and historical CLV are `null`; maximum drawdown is zero because nothing is wagered. These are not profitable trading results. [metrics.json](metrics.json) contains all machine-readable values and validation trials.

## Source correction and checks

Initial full-season roster queries supplied 104,328 pitching appearances but omitted 11 player-seasons. A complete season pitching index exposed the missing records, including 2021 Blake Treinen and 2022/2023 Framber Valdez. Supplemental official player logs added **299 appearances**, producing 104,627 appearances over 12,148 games and coverage of 24,296 game-team sides. The [repair audit](pitcher-source-repair.json) lists the affected players and seasons.

Every side now has exactly one starter. Independent reconciliation of pitcher outs against game innings and home/away results found no discrepancy in games without suspension or early completion. The repair applies to affected records independent of outcomes. Candidate definitions, selected years and EV threshold remain fixed. Original output is preserved in [initial-source-results.json](initial-source-results.json); its physical log loss was 0.6771268, with an interval crossing zero and no qualifying bets.

Independent arithmetic from the corrected prediction CSV reproduces the reported no-vig probabilities, losses and bet counts. Chronology tests cover same-day/future outcomes, suspended games, postponed score copies and traded-pitcher deduplication. Odds tests cover doubleheader ambiguity, result mismatches and terminal-price exclusion. Monitoring tests cover freshness, identities, model binding, probability-scoring populations, evidence gates and notification behavior. The [review](../docs/review.md) records the assessment.

Eight accepted historical rows have incomplete travel metadata, covering games at Mexico City's incompletely described venue and subsequent travel from it. They remain flagged in this exploratory reconstruction; zero-filled components are placeholders, not observed absence of travel. Live scoring blocks incomplete travel inputs.

## Forward process

The public [Covers moneyline page](https://www.covers.com/sport/baseball/mlb/odds) exposes paired prices explicitly labeled FanDuel. Ordinary access required no account or location override. The collector matches official identities and starts, captures response time and hash, and records publisher update time separately. Execution verification stays false: a refreshed aggregator page does not prove that FanDuel will accept those prices.

The runner builds dated MLB features before obtaining the forecast's quote, scores the frozen model, binds quote/model/feature hashes, and appends ledger rows. Official outcomes support hypothetical grading. Reports score the earliest valid pregame probability per model/event even when no bet is selected, keeping model versions and source classes separate. CLV requires verified closing quotes; aggregator observations cannot create it.

An initial integration run at 20:56 UTC recorded 15 forecasts with preliminary artifact `c3fefccfc56032ef`. Those rows remain a separate system-check cohort. Corrected artifact `a7ceefe2db3c13ea` subsequently recorded 15 forecasts with no qualifying bets. The [research log](../docs/research-log.md) preserves the sequence. Neither cohort has triggered a betting alert.

The included workflow is configured every 15 minutes on a public repository's standard GitHub runner, persisting text ledgers and reports through git. It uploads no Actions artifacts or caches and invokes no webhook. The configuration alone does not prove a completed cloud run; inspect Actions history and [live status](live-status.json). See [monitoring documentation](../docs/monitoring.md) for the operating contract.

## Remaining limits

Opening-price capture timestamps are absent. Yesterday's official results may have become available after an opener; reconstructed records may include later corrections. Terminal archive fields show in-play contamination and are unusable for closing comparisons. These limits preclude executable historical ROI or CLV claims even if an exploratory run later looks profitable.

The current model omits same-day lineups, starter changes, injuries and news. Those are future hypotheses requiring timestamped inputs and new frozen cohorts. The inspected 2024–2025 outcomes cannot be reused as untouched evidence. Promotion requires a frozen forward trial, verified entry/closing quotes, at least 1,000 settled paper bets over 90 days, and favorable corrected confidence bounds for execution-adjusted ROI, no-vig closing EV and paired log-loss improvement. No model meets those conditions.
