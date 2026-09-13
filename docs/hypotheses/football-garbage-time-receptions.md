# Garbage-time receptions

**Sport / market / book:** Football / live remaining receiver receptions over / FanDuel.

**Structural fact:** A trailing offense can trade short completions for clock while the defense protects against long gains.

**Predicted behavior (measurable):** Short-target receivers get more receptions per offensive snap when trailing >=17 in the fourth quarter than in close fourth quarters.

**Why FanDuel's price ignores it:** Unverified hypothesis: live reception props scale mainly with remaining time and pregame usage, missing the change in pass mix.

**Trigger (observable, timestamped):** Start of an offensive possession in quarter four, deficit >=17 and >=6 minutes remaining; receiver remains active. First exposure per player-game.

**Sport-side test: data source, cost, kill criterion:** Retained nflverse play-by-play and prior target-depth roles; free, <=1 hour. Compare receptions per snap with deficits <=8 at similar clock/field states; also report remaining snaps. Kill if >=200 exposures show <20% relative reception-rate increase; substitutions must remain in the outcome.

**Book-side test: what odds at trigger time, forward or historical:** Forward live reception lines with accrued catches, possession/clock and suspension state; inspect archive for matching markets without assuming coverage.

**Status:** idea

**Result:** Not tested. A rate increase need not increase total opportunity if drives or playing time fall.
