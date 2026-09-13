# Failed serve for the set

**Sport / market / book:** Tennis / live next service-game break / FanDuel.

**Structural fact:** A player who serves unsuccessfully for a set loses a concrete opportunity to end it; the match still follows ordinary game scoring.

**Predicted behavior (measurable):** After being broken when serving at 5–4, the failed closer breaks the opponent at 5–5 less often than comparable returners at 5–5 following a hold.

**Why FanDuel's price ignores it:** Unverified hypothesis: an unchanged hold-rate formula misses immediate carryover from the failed close. Ability and score-path selection could explain the whole association.

**Trigger (observable, timestamped):** Break ending the 5–4 game; target is the opponent's next service game at 5–5. Record game-end, server and quote timestamps.

**Sport-side test: data source, cost, kill criterion:** Sackmann point-by-point; free, <=1 hour. Compare break rates at 5–5 by whether the preceding game was a failed serve for set or a hold, with returner/tour strata where supported. Kill if >=100 exposed games show <3 percentage points lower break rate; otherwise unresolved when sparse.

**Book-side test: what odds at trigger time, forward or historical:** Forward paired 5–5 hold/break odds and the pre-5–4 baseline. Require a price discrepancy after known ability and actual serving order.

**Status:** sport-side dead

**Result:** September 13 exploratory screen of the prewritten direction in the pinned men's 2020s file: after a failed 5–4 close, the opponent was broken at 5–5 in 78/294 games (26.53%), versus 389/2,087 (18.64%) after the returner held at 4–5. The +7.89 percentage-point difference (descriptive 95% interval +2.50 to +13.28) is opposite to the predicted reduction and fails the original ≥100-exposure / ≥3-point-lower raw screen. The within-match residual difference changes sign to −2.04 points (−7.41 to +3.32), showing why the raw opposite direction is not a new edge: the groups condition on different score paths and opposite preceding outcomes, with different server/returner strength. Same-player/match, other-set and individual-returner summaries remain descriptive. Kill this specified hypothesis in this exploratory sample; do not reverse it into a strategy. No untouched holdout or FanDuel prices were tested. See [fixed follow-up](../../reports/tennis-followup-2026-09-13.md).
