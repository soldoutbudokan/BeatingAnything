# Sunday chasing and round-score dispersion

**Sport / market / book:** Golf / final-round player score and alternative score props / FanDuel. These are target markets; current event and jurisdiction availability is unverified.

**Structural fact:** A player within plausible striking distance of the lead can accept more risk to win; a player farther back has less reason to sacrifice finishing position for a remote chance of first place.

**Predicted behavior (measurable):** Players starting round four 4–6 strokes behind the leader have greater dispersion in field-adjusted final-round scores than players 8–10 behind, after grouping by their earlier-round scoring ability.

**Why FanDuel's price ignores it:** Unverified hypothesis: alternative round-score prices retain a player-level variance when leaderboard position changes the player's risk choices. A conditional scoring effect alone does not establish mispricing.

**Trigger (observable, timestamped):** Completion of round three; compare quotes before the player's scheduled final-round tee time, with the official leaderboard and source/collector times retained. A retrospective leaderboard is not evidence of a historically available quote.

**Sport-side test: data source, cost, kill criterion:** Written September 13, 2026 before outcome comparisons. Fixed sample: official 2025 PGA TOUR individual four-round stroke-play tournaments, excluding team/match-play, Stableford and events with starting-stroke adjustments. Use the official schedule and public tournament leaderboards. Prior ability is the mean field-adjusted score in the player's most recent 20 earlier completed rounds, requiring at least 10; all baseline rounds precede the event, and no 2025 event is excluded for its observed scores. Center final-round scores on that event's final-round field mean; compare exposed (4–6 behind) against controls (8–10 behind) within 1-stroke prior-ability bins, exposure-weighting the within-bin variances. Require ≥200 exposed final rounds across ≥15 events, with a weighted variance ratio ≥1.15; below that ratio with sufficient data kills this screen, below sample minimum or unavailable required inputs stays unresolved. Report round-score means, source exclusions and tournament-cluster bootstrap uncertainty separately. No threshold tuning or reversing the direction after looking.

**Book-side test: what odds at trigger time, forward or historical:** If the sport screen advances, collect both sides of the same alternative final-round score line before tee time and the corresponding ordinary line, including settlement, suspensions and quote clocks. Demonstrate that quoted tail prices fail to reflect the observed conditional distribution. No current FanDuel quotes have been acquired.

**Status:** idea

**Result:** September 13 [source screen](../../reports/golf-source-screen-2026-09-13.md) recovered the official 2025/2026 schedules and Data Golf's explicitly free 2021 Masters sample (88 players, 284 round records, 54 complete four-round players). The first historical PGA leaderboard request returned 403; Data Golf's full archive requires paid access. Zero fixed-2025 player rounds were recovered, so no variance estimate was calculated and the card is unresolved. The 2021 sample was not substituted for the declared season. This comparison could detect a conditional distribution difference; it could not alone identify risk-taking causally. Remaining player skill, tee time/weather, and field selection can create differences even after prior-ability grouping.
