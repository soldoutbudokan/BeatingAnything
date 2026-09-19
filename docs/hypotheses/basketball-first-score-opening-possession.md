# Card 41 — NBA first scorer and opening-possession mismatch

**Declared:** September 19, 2026, after price-source verification and a three-game outcome reconciliation, before any conditional-effect estimate, probability fit or ROI calculation. This is exploratory research; the publisher has already studied the archive.

**Sport / market / book:** NBA / first-basket scorer (`player_first_basket`, including free throws under the cited FanDuel rules) / FanDuel.

**Structural fact:** The opening jump gives one team the first opportunity to score. The player targeted by a team's opening offense need not be its highest full-game scorer. A different jumper can change possession probabilities without materially changing full-game scoring projections.

**Predicted behavior:** First-possession team scores first at least 10 percentage points more often than the other team, measured on the 2019–2024 opening-possession history with at least 1,000 valid games. Missing jumpers or possession identities are unresolved, not presumed losses. This cheap descriptive screen does not establish an edge.

**Why FanDuel's price might ignore it:** Unverified: a first-scorer allocation based mainly on player/team scoring frequencies could underweight the current jump-ball matchup and opening-offense roles.

**Trigger:** A historical, timestamped pregame FanDuel first-scorer board. Determine candidate players from the offered market; use only completed prior-game information to estimate likely jumpers and opening roles. Do not use the target game's realized jump winner or actual starter flags as forecast features. The publisher's unzoned lineup timestamps are not proof of timely lineup news.

**Data already acquired:** [Source audit](../../reports/nba-first-basket-source-2026-09-19.md): 7,673 FanDuel prices across 799 games; 580 verified pregame ten-runner boards; 449 games with complete quoted-player IDs, first-score outcomes and roster/starter records. Independent play-by-play covers all 580 price games; three fixed outcomes reconcile. Earlier opening-possession histories contain 7,583 rows.

**Book-side test:** After the cheap screen, freeze an exact estimator and chronological split before inspecting conditional results. Estimate first-score probabilities as a mixture of the two possible opening-possession states, including free throws, misses, turnovers and second chances. Compare against FanDuel's prices and a declared simpler first-score-frequency baseline. Use one fixed selection rule per game, actual quoted decimal prices and nonstarter voids. Do not compare raw first-field-goal prices as though their outcomes were identical; do not promote a one-snapshot source into closing-line evidence.

**Status:** data available; sport-side and book-side untested.

**Remaining work:** execute the declared cheap screen, then freeze and run the actual price comparison if it passes. The archive supports exploratory testing now; unknown quote jurisdiction and publisher outcome inspection remain explicit, and prospective promotion requirements are unchanged.
