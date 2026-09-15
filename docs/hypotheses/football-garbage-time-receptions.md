# Garbage-time receptions

**Sport / market / book:** Football / live remaining receiver receptions over / FanDuel.

**Structural fact:** A trailing offense can trade short completions for clock while the defense protects against long gains.

**Predicted behavior (measurable):** Short-target receivers get more receptions per offensive snap when trailing >=17 in the fourth quarter than in close fourth quarters.

**Why FanDuel's price ignores it:** Unverified hypothesis: live reception props scale mainly with remaining time and pregame usage, missing the change in pass mix.

**Trigger (observable, timestamped):** Start of an offensive possession in quarter four, deficit >=17 and >=6 minutes remaining; receiver remains active. First exposure per player-game.

**Sport-side test: data source, cost, kill criterion:** Retained nflverse play-by-play and prior target-depth roles; free, <=1 hour. Compare receptions per snap with deficits <=8 at similar clock/field states; also report remaining snaps. Kill if >=200 exposures show <20% relative reception-rate increase; substitutions must remain in the outcome.

**Book-side test: what odds at trigger time, forward or historical:** Forward live reception lines with accrued catches, possession/clock and suspension state; inspect archive for matching markets without assuming coverage.

**Status:** idea

**Result:** [Fixed 2023–2025 screen completed September 13](../../reports/nfl-garbage-receptions-2026-09-13.md). Historical on-field participation was acquired and roles frozen before comparison. The 72 matched exposures show 106 catches in 1,172 remaining team snaps, 9.044 per 100 versus 6.395 standardized controls (+41.4%). Only 72 of the required 200 matched cases qualify, so this remains unresolved. Fourteen source-level reception/lineup inconsistencies in two games add a selection caveat. No live FanDuel quotes or edge. Do not widen matching, append seasons or rerun the completed assignment; a rate increase alone need not raise total opportunity. The [declaration](../nfl-garbage-receptions-declaration-2026-09-13.md) fixes roles, first-snap timing and post-trigger outcomes.
