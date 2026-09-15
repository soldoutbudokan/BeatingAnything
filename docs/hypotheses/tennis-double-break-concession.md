# Double-break concession

**Sport / market / book:** Tennis / live next regular service-game break, set correct score, set games under / FanDuel.

**Structural fact:** Losing a set by a larger margin has no extra match-score cost if another set remains.

**Predicted behavior (measurable):** The next service-game break rate rises after a player falls two net service breaks behind in a set they can afford to lose.

**Why FanDuel's price ignores it:** Unverified hypothesis: a next-game price based on a static hold rate misses an abrupt reduction in effort. Whether FanDuel actually uses or misses this adjustment is unknown.

**Trigger (observable, timestamped):** First regular service game per player-set beginning with service games lost minus return games won >=2. Opponent sets won must be < sets required to win the match minus 1. Record completion time of the preceding game and quote/state receipt times.

**Sport-side test: data source, cost, kill criterion:** Sackmann point-by-point repositories; free, <=1 hour first pass. Compare break rate with first one-net-break-down service opportunities under the same set-survival condition; show tour/player and match-phase composition. Advance only if >=100 exposures and increase >=5 percentage points. Otherwise kill for small effect or leave unresolved for inadequate coverage. Completed games only; disclose retirement/missing-data selection.

**Book-side test: what odds at trigger time, forward or historical:** Forward paired next-game hold/break odds immediately before and after second break; also set totals/correct scores if offered. Join to actual set/server state; require a state-matched price discrepancy beyond vig and quote-age uncertainty.

**Status:** sport-side dead

**Result:** September 12 exploratory screen: 181/600 exposed games were breaks (30.17%) versus 955/3,738 controls (25.55%), +4.62 percentage points, below the prewritten +5-point screen. The exposed players' other-set break baseline was 31.76%, so the raw association does not establish concession. Deprioritized in this sample; a prior-high-hold proxy has only 60 exposed games and leaves the narrower big-server idea unresolved. The curated men's Match Charting Project sample excludes incomplete matches and is not a Challenger sample or untouched holdout. No FanDuel quotes were tested. See [results and limitations](../../reports/tennis-state-exploration.md).
