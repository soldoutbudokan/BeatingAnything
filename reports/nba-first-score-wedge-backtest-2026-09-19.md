# FanDuel first-score conversion test: profitable, underpowered, mechanism unconfirmed

**The fixed conditional test returns a large historical profit, but does not establish an edge.** The free-throw adjustment slightly worsens pooled forecasts against its unadjusted BetMGM reference. Every selected bet already has positive modeled EV using that reference alone. The cross-book price difference is worth investigating with additional data; the declared free-throw mechanism does not pass its advancement gates.

The [protocol](../docs/nba-first-score-wedge-price-protocol-2026-09-19.md) was committed as `75f7906`. [Predictions and selections](nba-first-score-wedge-forecast-freeze-2026-09-19.json) were frozen at **2026-09-19 23:57:57 UTC**, SHA-256 `8951bf7e2b062e89c747db465f4c96127f663f7693960f5e517b640dc027fec5`, and committed as `9c8001e` before independent grading. The [machine-readable results](nba-first-score-wedge-backtest-2026-09-19.json) include all counts, probability scores, uncertainty and source receipts. Both calendar periods were already inspected in earlier work; neither is an untouched holdout.

## Cohort and model

Of 473 previously eligible FanDuel games, 130 qualify: 55 discovery and 75 chronological replication. Exclusions are 239 without an eligible BetMGM board, 63 Fridays and 41 games outside verified regular-season coverage. Both ten-player boards must match exactly, share the event ID, remain within five minutes of their update at the joint receipt, and precede the earlier verified start by at least one minute. No outcomes or eventual starter labels determine eligibility.

The fixed conversion uses 12,300 recorded starts in 2023–24, ending April 14, 2024: 72,417 field goals and 30,680 free throws, with no missing numeric starts. It shrinks each player's FT/FG ratio toward the league ratio with 100 pseudo-field-goals and transfers `80/1319` of normalized BetMGM probability according to those ratios. There is no current-season statistical fitting or return-based tuning.

Interpretation of BetMGM's quotes as first-field-goal prices remains conditional. Its [contemporaneous regulator rulebook](https://massgaming.com/wp-content/uploads/BetMGM-House-Rules-11.21.24.pdf) and [January 7, 2025 announcement](https://sports.betmgm.com/en/blog/betmgm-expands-second-chance-offer-ice-courts/) support that interpretation, but the archive lacks each original label and jurisdiction. Fridays and playoffs were excluded before selection to avoid the identified recurring refund day and playoff promotion regimes; other promotional effects are not ruled out.

## Historical returns

Flat one-unit stakes, at most one FanDuel selection per game, fixed 5% modeled EV threshold and 2% winning-profit haircut. ROI denominators include every original stake, including voids. Unknown settlements remain in both scenarios below; these scenarios are not a complete range of possible results.

| Period | Bets | Wins | Losses | Voids | Unknown | ROI: unknowns lose | ROI: unknowns void |
|---|---:|---:|---:|---:|---:|---:|---:|
| Discovery | 14 | 3 | 8 | 1 | 2 | +187.57% | +201.86% |
| Replication | 21 | 4 | 13 | 3 | 1 | +176.00% | +180.76% |
| Pooled | 35 | 7 | 21 | 4 | 3 | +180.63% | +189.20% |

Only **11 and 17 settled nonvoid bets** are available, versus the fixed minimum of 50 in each period. Selected bets span four and seven calendar weeks, below the eight-week threshold for period-specific intervals. The pooled 99.6875% corrected weekly-bootstrap interval for unresolved-as-loss ROI is **−62.76% to +422.07%**. It includes losses despite the large point estimate. The family allowance is now 16; previous reports retain their original allowances.

The predetermined 1% probability-reserve sensitivity selects 14/19 bets and returns +187.57%/+205.05% with unknowns treated as losses. This is a sensitivity, not a replacement chosen after seeing returns.

## Does the free-throw adjustment help?

Independent first scores resolve 129 of 130 games. Probability scoring retains the fixed 1% unlisted-player bucket and all unlisted scorers; it does not delete inconvenient outcomes. Lower log loss and Brier scores are better.

| Period | Converted minus BetMGM log loss | Converted minus FanDuel log loss |
|---|---:|---:|
| Discovery | −0.000617 | −0.038423 |
| Replication | +0.000679 | −0.019181 |
| Pooled | +0.000126 | −0.027385 |

The pooled log-loss difference against BetMGM has corrected interval **−0.003234 to +0.003087**; against FanDuel, **−0.062356 to +0.007450**. Brier results agree in direction: the conversion is slightly worse than BetMGM and better than FanDuel, with both corrected intervals crossing zero. This does not show that the free-throw allocation adds predictive value.

All **35 selected bets already have positive unconverted BetMGM-based EV**. This diagnostic does not mean that all 35 would pass the same 5% threshold without conversion, nor does it establish a separately tested reference-only strategy. Changing selection now would be a new exploratory candidate.

## Winning-price checks

The [audit of all seven winning selections](nba-first-score-wedge-winning-price-audit-2026-09-19.json) recovers the full FanDuel and BetMGM boards from corresponding historical Git commits. All 14 complete boards match the frozen prices, identities and quote clocks. Their commit clocks fall within one second of the retained joint receipts. Git clocks are publisher-controlled and do not prove wager acceptance or independently observed publication time.

| Date | Winner | FanDuel decimal | BetMGM decimal |
|---|---|---:|---:|
| February 3 | Trey Murphy III | 13.00 | 9.75 |
| February 4 | Anfernee Simons | 9.00 | 6.75 |
| February 12 | Olivier-Maxence Prosper | 18.00 | 8.50 |
| March 2 | Immanuel Quickley | 12.00 | 9.25 |
| March 9 | Aaron Gordon | 15.00 | 9.75 |
| March 9 | Tim Hardaway Jr | 13.00 | 9.75 |
| March 23 | DaQuan Jeffries | 16.00 | 11.00 |

Six winners scored a field goal first; Murphy scored a free throw. Outcomes reconcile with the independent first-score source and the publisher records under the existing grading conventions. Two selected bets have missing starter evidence; one has an unresolved independent scorer identity. No favorable alias or starter assumption was introduced.

## Decision and continuation

Both conditional advancement gates fail: the sample is too small and pooled scoring does not beat both baselines. Preserve this profitable result alongside those failures. No edge, wager or alert is authorized by this result; schedules remain paused.

The 255 listed changes to LeFirstBasket's odds file span December 2, 2024–May 12, 2025, with no later-season file update. A newly found [2021 first-basket archive](nba-first-basket-2021-source-check-2026-09-19.md) contains actual FanDuel player quotes, but its sampled clocks and reference coverage do not yet supply a qualified replication cohort. Continue from its concrete source findings or newly available historical access; do not tune the free-throw allocation on these results.

Validation: **269 tests pass**, including conservation of probability, prior-only statistics, joint quote freshness, exact clock boundaries, positive-adjustment selection, reserve sensitivity and unresolved/void stake accounting.
