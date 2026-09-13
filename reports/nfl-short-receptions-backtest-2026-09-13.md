# Card 38 — Actual FanDuel short-target reception backtest

**The fixed 2025 strategy returned +15.46%, but remains unresolved.** It selected only 34 games against a preset minimum of 50, and its 95% game-bootstrap interval runs from −16.63% to +46.34%. These results do not establish a betting edge.

| Measure | Result |
| --- | ---: |
| Selected / settled games | 34 / 34 |
| Wins / losses | 21 / 13 |
| Unknown participation settlements | 0 |
| Stake | 34 units |
| Profit after haircut | +5.2574 units |
| ROI after haircut | +15.46% |
| 95% game-bootstrap ROI interval | −16.63% to +46.34% |
| Preset status | Unresolved: fewer than 50 settled games |

The rule bought a listed FanDuel reception Over for a player with a verified shallow prior target profile when an earlier FanDuel spread made his team an underdog of at least 6.5 points. The [declaration](../docs/hypotheses/football-underdog-short-receptions.md) fixed role, prices, clocks, spread matching, one-player-per-game selection and evidence gates before grading. This is an actual archived-price test, rather than a conversion of the earlier live garbage-time sport effect into a claimed probability. It uses no fitted model.

## Selection and chronology

| Sequential step | Remaining observations |
| --- | ---: |
| Public reception CSV, all published seasons | 6,901 price pairs |
| Independently mapped to a 2025 regular-season fixture | 2,721 pairs |
| Valid pregame paired price, original snapshot chronology and freshness | 1,386 pairs |
| Unique player/team from full names in prior participation | 1,153 pairs |
| Fixed short-target profile in the three prior team games | 340 pairs |
| Earlier fresh FanDuel spread available within six hours | 338 pairs |
| Same-team spread at least +6.5 | 60 player-games |
| One earliest eligible price per player/game, then fixed one-player/game cap | 34 games |

Within the mapped 2025 prices, 1,334 pairs fail the original bookmaker/market clock or 300-second freshness rule; one fails the 0–8% overround rule. No archive clock was moved to accommodate an update from its future. The 233 identity failures include insufficient prior games, absent exact normalized full-name identity, or ambiguity; the implementation does not guess a current team. The role gate then rejects 813 pairs.

Roles use exactly the three preceding 2025 regular-season team games, at least ten observed target depths, at least 90% depth coverage, mean depth at most eight yards, and targets in at least two games. Current-game catches or participation do not select a player. When multiple players qualify, the chosen player has the shallowest prior mean target depth, then the most targets, then the first stable ID. There is one observation per game.

Spread context comes from original raw DuckDB rows. Each pair must agree on teams, its actual recorded `commence_time`, capture and update; its teams and start independently match the fixture. The latest qualifying spread must strictly precede the prop snapshot by at most six hours. The CSV's guessed teams/context spreads and nflverse closing spreads never select a bet.

Declaration SHA-256: `e05f4250b7d30867be75f51b3202b659688ed2ebe7144db419dd6de51914e82d`.

Selected prices and eligibility froze at **2026-09-13 18:28:14.443320 UTC**, before the completion field was loaded for grading. Frozen selection SHA-256: `d074081bd7e5b0f26462d51c01a1b7979efa05e818f08a6b9f760b063a2ab320`. The ignored original selection and its independent hash record remain under `data/raw/nfl-short-receptions/`; the [JSON result](nfl-short-receptions-backtest-2026-09-13.json) retains selected-row details, source pins and attrition.

## Settlement and limits

Each bet risks one unit. A win earns 98% of its quoted decimal net winnings; a loss costs one unit. Credited completed passes include overtime and exclude nullified plays and two-point attempts. Valid same-team participation or an unambiguous credited statistical play verifies all 34 selected participants. No unknown case was dropped. Consequently, the unknown-as-loss and unknown-as-void sensitivity results equal the primary return. Half-point reception lines have no push.

Historical jurisdiction-specific FanDuel settlement and injury-protection rules remain unverified. These are archived listed prices, not accepted wagers. There is no same-line closing series, original live collection clock or closing-value claim. The bootstrap resamples games; it does not establish independence across repeated players or common weekly conditions.

This is an exploratory strategy on a new price source. Project work already inspected 2025 outcomes for other questions, and the source publisher analyzed its archive; 2025 cannot be called an untouched holdout. Preserve the positive point estimate and the failed evidence gate. Do not increase sample size by relaxing roles, accepting future clocks, taking multiple players per game or changing the underdog cutoff after seeing this result. Any separate replication needs its own frozen declaration and must keep this 34-game result visible.

Reproduce grading with `PYTHONPATH=state/runtime/nfl-audit-lib python tools/backtest_nfl_short_receptions.py settle`. Preparation is a separate command that refuses to overwrite its frozen cohort. Code compilation and explicit selected-row chronology checks passed. An independent review checked all 34 selections' prior dates and quote chronology and directly reconciled three predetermined rows (first, middle and last) against raw name/ID links, target depths, spread sides/start times, receptions and profits. It found no material defect; the freeze stayed unchanged. The full [source acquisition audit](../docs/new-prop-archives-2026-09-13.md) documents the new archives.

PBP attribution: nflverse/nflfastR, CC BY 4.0. Participation-derived identities: FTN Data via nflverse, CC BY-SA 4.0. Raw third-party inputs are not republished here.
