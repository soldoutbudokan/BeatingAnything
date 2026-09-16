# G2 — Withdrawal risk by settlement state

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / tournament matchups, round 2-balls and 3-balls / FanDuel.

**Structural fact:** Withdrawal effects depend on when play starts, whether the cut has occurred, and the specific market rule; a final WD flag does not resolve those states.

**Predicted behavior (measurable):** A prior-90-day in-play withdrawal identifies a higher subsequent in-play withdrawal rate than starts without that history.

**Why FanDuel's price ignores it:** Unverified: the quoted derivative carries a scoring skill adjustment but omits a conditional failure-to-finish component. The main price may already include it.

**Trigger (observable, timestamped):** Prior WD record known before the next tournament starts. Injury news is a separate future variant requiring its original publication time.

**Sport-side test: data source, cost, kill criterion:** Use official 2025 PGA starts plus the preceding 90 days; separate WD, DQ, DNS, missed cut and unknown timing. Compare starts with a prior-90-day confirmed in-play WD against other starts. Require >=100 exposed starts, >=10 exposed in-play WDs and >=5 events. Kill if exposed WD rate is <3% or does not exceed baseline with adequate data; report event/player clustering. Preserve ambiguous outcomes as unknown; neither age nor fall-position subgroups may rescue this screen. A rate alone cannot settle any particular matchup.

**Book-side test: what odds at trigger time, forward or historical:** If sport-side advances, retain FanDuel quotes for flagged and unflagged players before tee-off, identify rule/jurisdiction, and enumerate mutually exclusive settlement states. Kill if corrected residual disappears or flagged players have no posted market. No generic additive opponent-WD term or more-holes-wins rule.

**Status:** idea (sport-side unresolved)

**Result:** The [September 14 screen](../../reports/golf-sport-screen-2026-09-14.md) found 4,840 eligible 2025 starts across 40 events. Prior-90-day proven in-play WD exposures had 4/199 subsequent WDs (2.010%), versus 48/4,641 (1.034%) without observed prior WD: +0.976 percentage points, with both event- and player-cluster intervals spanning zero. The conditional rate is below 3%, but only four exposed WDs miss the ten-outcome minimum: unresolved, with no advancement or proven absence. Across 2024–25 there were 122 proven in-play WDs and two zero-hole unknowns; two later starts were censored. No injury-news, age, status-incentive or FanDuel-price test was performed.
