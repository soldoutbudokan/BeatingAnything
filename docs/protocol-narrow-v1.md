# Narrow-market research protocol v1

Recorded 2026-09-08 before examining the new holdout outcomes or strategy returns. This is a retrospective research specification, not a prospective registration. The earlier failed MLB experiment remains in the record. The user requested narrower models, usable historical closing prices, and sports with a longer season ahead.

## Experiment N1: Lower-division soccer fixed total 2.5

English Championship and League One, German Bundesliga 2, French Ligue 2, Italian Serie B and Spanish Segunda: regular-season full-time over/under 2.5 goals, excluding playoffs. These six leagues are fixed before any strategy result inspection; no profitable-league selection is allowed. Fit one shared model without team or league parameters. Pooling is based on source coverage and sample accumulation: Championship alone has only 552 regular-season matches per year. Football-Data files 2019/20–2025/26 supply paired Bet365 early snapshots and paired Bet365 closing prices. These are explicitly early snapshots AFTER opening, not opening prices. The early feed has no individual capture timestamps. Historical returns are therefore an indicative Bet365 simulation, not verified execution and not FanDuel returns. The line is always 2.5; never compare prices at different goal thresholds.

Source selection used schema/coverage only. The initial Championship audit found 3,864 matches, 3,863 complete early/closing Bet365 totals pairs; three sampled seasons in each of the other five leagues have the needed column families. Fetch all 42 files from the same pinned mirror commit c9b05a30eef50fe34abbf4134e6333fc5376d136 and verify against primary files where available. Retain their SHA-256 hashes and record missingness without outcome-based exclusions. Do not publish raw third-party files. Source notes: https://football-data.co.uk/data.php and https://football-data.co.uk/notes.txt. Pinnacle is explicitly unreliable after 2025-07-23; no Pinnacle field enters this experiment at any date.

### Chronology and candidates

Development: 2019/20–2021/22. Validation: 2022/23. Holdout: 2023/24 and 2024/25. Separate replication: 2025/26. Before each test season, refit on previous seasons only, with validation-selected hyperparameters fixed. Publish both holdout and replication regardless of their results. Neither new features nor new bet thresholds may be selected from either.

Probability baseline: proportional no-vig early Bet365 totals probability. Also report the untrained early market-average probability on the same universe.

Three learned candidates, each a residual logistic model with the early Bet365 logit as a fixed offset:

1. Calibration: intercept and early Bet365 logit.
2. Consensus discrepancy: calibration plus early average totals logit minus early Bet365 totals logit.
3. Goal structure: consensus discrepancy plus the logit difference between a goal-process probability inferred from early Bet365 1X2 prices and early Bet365 totals.

The goal-process feature estimates two independent Poisson goal rates from proportional no-vig early home/draw/away prices. Fit rates within [0.05, 6] by deterministic bounded least squares, starting at [1.4, 1.1], with solver tolerances 1e-10; compute P(total goals > 2.5) from their sum. This is a testable approximation: low-score dependence and bookmaker margins can violate it. Reject nonconvergent or materially mismatched inversions (maximum 1X2 probability error > 0.02), record counts, and use the same accepted universe for all candidates. No outcome, closing price, final referee, current-game statistic, or retrospectively published lineup enters any feature. Within-row bookmaker snapshot synchronization is undocumented, so discrepancies are source-price research signals with unresolved simultaneous availability.

For each learned candidate choose L2 penalty from [0.001, 0.01, 0.1, 1] using validation paired outcome log loss only. Fit normalization on training rows only; use the existing ResidualLogistic implementation's intercept penalty weight 0.1 and feature penalty weight 1. The prospective research candidate, if any, is the lowest validation-log-loss candidate; never select the prettiest holdout result. Report every candidate and penalty's validation result. Do not automatically promote the selected candidate. Per-league splits are descriptive; no league-specific winner can be promoted from them.

### Fixed betting and closing evaluation

At most one unit per event, selecting the side with greatest estimated EV if EV >= 0.03, chosen decimal odds in [1.20, 6], and early two-sided overround in [0, 0.10]. Ties choose over. No maximum-book odds, alternate threshold, compounding or optimized staking. Reduce net winnings by 2% for execution sensitivity. Event selection uses only entry odds and predictions; closing availability and realized closing overround cannot decide whether a bet was selected.

For each selected side calculate closing EV = entry decimal price * no-vig closing probability - 1. Primary closing benchmark: paired market-average closing prices. Robustness benchmark: paired Bet365 closing prices. Also report power-method de-vig sensitivity. The average has changing bookmaker composition and is a benchmark, not an executable price. A missing/invalid closing benchmark remains a selected bet with CLV missing; explicitly report coverage and block any favorable-evidence declaration unless coverage is complete. Closing overround must be in [0, 0.15], both decimal prices finite and > 1. Closing prices are source-designated prestart prices; exact timestamps remain unverified.

Report all-event log loss/Brier, paired loss difference versus early Bet365 and market-average close, selected count, turnover, profit/ROI, haircut ROI, drawdown, mean no-vig closing EV, price-ratio CLV separately, and season splits. Use 10,000 calendar-week block-bootstrap samples, seed 1729, with 99.375% two-sided intervals: a conservative eight-model comparison allowance covering the two earlier MLB models and six reserved new models. This protects the fixed family, not unlimited repeated research. Any additional family requires a new recorded correction before inspection. Confidence bounds do not cure source bias.

A promising retrospective result requires positive corrected lower bounds for haircut ROI and primary closing EV, negative corrected upper bound for paired log-loss difference versus the early market, and no contradictory negative Bet365-closing replication. Report paired loss against closing separately as a tougher benchmark. The untrained market-average control is descriptive and cannot be selected for promotion from this experiment. This screen does not authorize a bet.

## Further experiments and forward qualification

Three further model slots are reserved but unspecified. They cannot be run until their market, sources, features, splits, selection and settlement rules are recorded in a separate protocol before outcome inspection. Candidate archives for tennis and NBA props are being audited. No automatic switch to a profitable subgroup is allowed.

The original forward promotion gate remains intact: separately reviewed prospective FanDuel evidence, at least 1,000 settled bets over at least 90 days, fixed checkpoints, positive corrected lower bounds for ROI after execution allowance and no-vig closing EV, and a negative corrected upper bound for paired out-of-sample log-loss difference. Model and protocol hashes, timestamped predictions, verified paired executable prices, starts/status, settlement rules and closing capture are required. A historical Bet365 or Pinnacle signal is never treated as an executable FanDuel quote. No bets or paid requests are authorized by this research protocol.
