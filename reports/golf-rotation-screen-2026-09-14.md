# G11 course rotation screen — September 14, 2026

**sport-side effect: investigate prices.** No FanDuel prices were tested.

The signed, ability-adjusted harder-minus-easier first-round contrast is **+1.709 strokes relative to par**, across 950 player-events, 311 unique players and 8 editions. The declared effect gate is +0.5 strokes; the sample gate is 200 unique players and six editions.

Event-bootstrap 95% interval: [+1.111, +2.192] strokes. This is an exploratory interval across eight editions of only three recurring tournaments; it does not account for all repeat-player or shared-venue dependence.

| Edition | Course contrast | Paired player-events | Relative-to-par gap | Gross-score gap |
| --- | --- | ---: | ---: | ---: |
| Farmers Insurance Open 2023 | 004 (par 72) − 104 (par 72) | 143 | +2.507 | +2.507 |
| Farmers Insurance Open 2024 | 004 (par 72) − 104 (par 72) | 134 | +2.509 | +2.509 |
| Farmers Insurance Open 2025 | 004 (par 72) − 104 (par 72) | 131 | +2.315 | +2.315 |
| AT&T Pebble Beach Pro-Am 2023 | 205 (par 72) − 005 (par 72) | 93 | +1.641 | +1.641 |
| AT&T Pebble Beach Pro-Am 2024 | 205 (par 72) − 005 (par 72) | 76 | -0.429 | -0.429 |
| AT&T Pebble Beach Pro-Am 2025 | 205 (par 72) − 005 (par 72) | 79 | +1.480 | +1.480 |
| The RSM Classic 2024 | 776 (par 70) − 889 (par 72) | 146 | +1.534 | -0.466 |
| The RSM Classic 2025 | 776 (par 70) − 889 (par 72) | 148 | +1.147 | -0.853 |

## Identity and attrition

Official PGA TOUR round-one group records supply course ID, player ID, group number, start tee and timestamp. CourseStats supplies edition-specific par, checked against 18 first-round hole pars. ESPN supplies first-round gross strokes checked against all 18 hole scores; prior ability remains keyed by ESPN player ID.

Cross-source joins require a unique full name after case, accents and punctuation are normalized. No fuzzy matching, nickname substitution or surname-only match is used. Historical fetched-now assignments do not prove their original pre-round publication time.

Across eight events: 1095 ESPN competitors; 1089 unique PGA name joins; 6 unmatched and 0 ambiguous ESPN names; 52 outside the fixed course pairs; 2 without a verified complete R1; 72 with inadequate prior history; 0 with unknown par. 963 player-events remain before paired ability bins; 13 then lack an opposite-course comparison within their fixed ability bin. Official players not joined to ESPN: 6.

2023 Pebble's Monterey Peninsula course is excluded as declared. R2023493 is November 2022; calendar 2023 RSM was not substituted after the cohort was fixed. The JSON records each excluded row and all per-bin denominators.

## Method and interpretation

The [pre-score declaration](golf-rotation-declaration-2026-09-14.md) fixes the cohort, course direction, one-stroke prior-ability bins, pooled weighting, thresholds and exclusions. Ability is the average of at most 20 completed rounds (at least ten) in earlier single-course events ending before this event, each centered on its field-round score. 2022 supplies warmup. Current-event scores never enter current-event ability. Within every edition/ability bin with both courses, compare score minus course par minus prior ability and weight by n_harder × n_easier / (n_harder + n_easier).

Assignment groups can differ in player strength, start times, weather and other unmeasured factors. Prior ability is noisy and field strength varies. This screen estimates an observational course-assignment contrast, not a causal course-design effect or a profitable forecast. No probability kernel or FanDuel price has been fitted.

Implementation audit: the first run additionally required four observed historical rounds. That was stricter than the declaration. The rule was removed, and the three affected source events were all editions of the exhibition `The Match`, excluded explicitly under the already declared exhibition rule. No legitimate shortened event was affected; the result, 963 pre-bin rows, 950 paired rows and all prior abilities are unchanged. The initial +1.709 estimate and corrected estimate are the same; this correction is not a fresh comparison.

Different pars matter: Seaside is par 70 and Plantation is par 72. Their relative-to-par contrast exceeds their gross-strokes contrast by exactly two. The pooled relative contrast must never be inserted into a gross-score matchup. Any later price comparison must preserve each named course pair, the displayed market convention and actual offer times.

A surviving sport effect requires a separate book-side test: pre-round FanDuel cross-course derivative markets, both sides, price clocks and settlement terms; compare offered mean shifts with the measured course-pair offsets. At least 70% reflection, or absent relevant markets, kills that book-side claim. This report establishes no betting edge.

Reproduce: `state/runtime/research-venv/bin/python tools/explore_golf_rotation.py`. Raw responses and player-level rows remain local under ignored `data/raw/`. Full hashes, attrition, course pars and per-bin contrasts are in [the JSON report](golf-rotation-screen-2026-09-14.json).

Sources: [PGA TOUR public GraphQL](https://orchestrator.pgatour.com/graphql), [public course-stat query schema](https://github.com/WalrusQuant/pgatouR/blob/main/inst/graphql/CourseStats.graphql), [ESPN 2022](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2022), [2023](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2023), [2024](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2024), [2025](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025).
