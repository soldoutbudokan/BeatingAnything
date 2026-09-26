# NFL quarterback kneel-down props — September 26, 2026

**The fixed kneel correction worsened forecasting loss, and its low-line Under cohort lost 19.32% before costs.** There are only 16 offers across 15 games, so this exploratory test cannot demonstrate an edge. The fixed trigger was quarterback rushing Under at a positive half-point line no higher than 5.5. Every quote passed both nonfuture book/market clocks and an independent pregame fixture check. No favorite filter was applied because a timely 2024 moneyline was unavailable.

| Measure | All fixed-trigger offers | Fixed gross model-EV≥3% subset |
| --- | ---: | ---: |
| Offers | 16 | 2 |
| Settled | 16 | 2 |
| Under wins | 7 | 1 |
| Gross ROI | -19.32% (game-bootstrap 95% -63.22% to +23.72%) | -6.14% (game-bootstrap 95% -100.00% to +87.72%) |
| ROI with 2% net-winnings haircut | -20.06% (game-bootstrap 95% -63.56% to +22.58%) | -7.02% (game-bootstrap 95% -100.00% to +85.96%) |

Normalized market Under log loss was 0.688952; the kneel correction produced 0.709805. The paired change was +0.020853 (game-bootstrap 95% -0.008231 to +0.053140). Brier losses were 0.247910 and 0.258258; paired change +0.010348 (game-bootstrap 95% -0.004086 to +0.026371). There were 8 nonzero corrections, 15 forecasts with at least 8 prior games, and 0 actual line-crossings caused by kneels. Insufficient history leaves the market probability unchanged and does not remove the bet.

The cost sensitivity reduces each winning profit by 2% and keeps losing stakes at −1 unit. The gross EV≥3% selection remains frozen; neither eligibility nor probabilities change. Two selected bets cannot support a reliable return interval.

## Mechanism and frozen calculation

NFL kneel-down losses count toward a quarterback's rushing total. At a very low line, a small negative movement can change an Over into an Under. From the previous 16 regular-season games with at least 10 recorded pass plays, count games where total rushing yards finished below today's line but non-kneel rushing yards exceeded it. Require 8 previous games, divide the crossing count by n+20, and add that probability to the paired-price normalized Under probability, capped at 0.99. This assumes the market underweights those losses and **can double-count an effect already in the price**.

The line cutoff, shrinkage, history and model-EV threshold were chosen before this test's returns. Every history game predates the quote by at least two calendar dates. No current-game statistics, future lines, final spread, publisher favorite flags, or publisher outcomes enter a forecast. The frozen selection/prediction hash is `890dc0e28383c244729be31733522e63f314733ec75e77d125d13c57137fd901`. A half-point line cannot push.

## Source evidence and limits

Prices come from the [pinned firstandthirty/nfl-tools merged export](https://github.com/firstandthirty/nfl-tools/blob/e919241eb9fc17f057005348c7869a37b23e7675/player_props/data/processed/merged_props_with_context.csv): 6,224 rows including 1,103 rushing quotes. The 1,094 rushing rows in the later analysis export reproduce those prices and clocks exactly. The [publisher backfill](https://github.com/firstandthirty/nfl-tools/blob/e919241eb9fc17f057005348c7869a37b23e7675/player_props/scripts/01_build/backfill_closing_props.py) directly copies `outcome.price`; no fabricated/default price was found. Most quotes are −110/−110, which is disclosed but not treated as proof of synthesis. Original API JSONs and the unmerged odds CSV are absent, so raw authenticity and executable fills are unverified. Publisher outcome/context transformations are ignored; price coverage may still depend on their earlier result join.

Independent nflverse fixture dates/team identities and roster name/IDs match offers. Valid non-null rushing plays, including `qb_kneel` and excluding two-point attempts, are summed from [nflverse PBP](https://github.com/nflverse/nflverse-data/releases/tag/pbp). Every settled total agrees with the [separately published weekly rushing statistic](https://github.com/nflverse/nflverse-data/releases/tag/player_stats). Settlement assumes full-game rushing yards including kneels; historical jurisdiction and exact participation/void terms are unverified. Unknown participation/stat conflicts remain selected with loss-versus-void bounds; none occurred. Recorded attrition: `{'outside_fixed_half_point_line': 1072, 'future_or_stale_quote_clock': 9, 'not_unique_roster_quarterback': 6, 'ambiguous_same_time_offer': 0}`.

This is a small retrospective price test, not a new independent holdout. No line expansion or parameter search follows this result. Full source hashes, forecasts and outcomes are in the [JSON](nfl-qb-kneel-props-2026-09-26.json). No schedules, alerts or wagers were enabled.

Run `state/runtime/research-venv/bin/python tools/explore_nfl_qb_kneel_props.py` with the retained raw files.
