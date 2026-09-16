# G11 course rotation screen declaration — September 14, 2026

Written after source metadata/tee-time schema inspection and before first-round score/course comparisons. This is an exploratory sport-side screen, not confirmation or a price model.

## Fixed cohort and direction

| Edition | PGA TOUR tournament ID | ESPN event ID | Predicted harder minus easier course IDs |
| --- | --- | --- | --- |
| Farmers Insurance Open 2023 | R2023004 | 401465516 | 004 South − 104 North |
| Farmers Insurance Open 2024 | R2024004 | 401580332 | 004 South − 104 North |
| Farmers Insurance Open 2025 | R2025004 | 401703492 | 004 South − 104 North |
| AT&T Pebble Beach Pro-Am 2023 | R2023005 | 401465517 | 205 Spyglass Hill − 005 Pebble Beach |
| AT&T Pebble Beach Pro-Am 2024 | R2024005 | 401580333 | 205 Spyglass Hill − 005 Pebble Beach |
| AT&T Pebble Beach Pro-Am 2025 | R2025005 | 401703493 | 205 Spyglass Hill − 005 Pebble Beach |
| The RSM Classic 2024 | R2024493 | 401693943 | 776 Seaside − 889 Plantation |
| The RSM Classic 2025 | R2025493 | 401738559 | 776 Seaside − 889 Plantation |

Official course identities are in the PGA TOUR `Tournaments` response cached at `data/raw/golf-rotation/tournaments.json`. Source operation is `query Tournaments($ids: [ID!]) { tournaments(ids: $ids) { id tournamentName displayDate courses { id courseName courseCode } } }` at `https://orchestrator.pgatour.com/graphql`. The [official 2025 schedule](https://www.pgatour.com/schedule/2025) and tournament pages identify event IDs. ESPN event IDs and dates were read from the cached annual feeds without course-level score comparisons.

The 2023 Pebble edition also has Monterey Peninsula course 769. Its players will appear in assignment attrition but are excluded from this single Spyglass-minus-Pebble contrast. No alternative contrast will be selected. The candidate RSM ID R2023493 is November 2022, outside this calendar-year cohort. Calendar 2023 RSM is unresolved at declaration and will not be substituted after seeing results. Eight named accessible editions already exceed the six-edition gate.

## Fixed screen

- First rounds only. Exact official `TeeTimesCompressedV2` course IDs assign each PGA player. A source-identifiable unique normalized full-name match joins PGA player to ESPN ID within the declared event; no fuzzy aliases, initials expansion or manual name replacement. Report every unmatched/ambiguous record and reject conflicting assignments.
- Gross score must equal the sum of 18 ordered, unique ESPN hole scores. Primary outcome is gross score minus that edition/course's verified par. Relative-to-par differences will never be interpreted as gross-score differences. Report both conventions; lack of verified course par leaves that edition unresolved.
- Ability uses the previous 20 complete field-round-centered rounds, minimum 10, from single-course individual stroke-play events ending before the event starts. Use 2022 as warmup and 2023–25 sequentially; exclude multi-course rotations, team/match play, Stableford, starting-stroke TOUR Championships, qualifying and exhibitions. Current-event scores cannot enter its own ability.
- Group ability by fixed one-stroke bins `floor(prior_ability)`. Within edition and ability bin require at least one eligible player on each named course. Compare mean `(gross − course_par − prior_ability)` between the predicted harder and easier course, weighting each bin by `n_harder × n_easier / (n_harder + n_easier)`. Pool editions using the sum of those weights. No abs-value, post-hoc sign reversal, tuned binning or best-event selection.
- Report per-edition and pooled signed contrasts, unique players, player-events, and a deterministic 5,000-draw event bootstrap percentile 95% interval (seed 20260914). Only the declared pooled effect is the gate: at least 200 unique eligible paired-bin players, at least six editions, and at least +0.5 strokes. Below +0.5 with adequate sample kills this card's declared screen; do not rescue it with a subgroup. An insufficient sample or unknown course IDs/par leaves it unresolved.
- A positive sport effect only advances to the book-side test. To establish an edge still requires actual pre-round FanDuel cross-course lines, both sides and displayed scoring convention; a market already reflecting at least 70% of the offset or no offered relevant market kills the book-side claim. No bet or alert follows from this screen.

Historical tee times fetched now are retrospective assignments. They do not prove the exact assignment was already visible before an old betting decision.
