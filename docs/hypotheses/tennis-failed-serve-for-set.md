# Failed serve for the set

**Sport / market / book:** Tennis / live next service-game break / FanDuel.

**Structural fact:** A player who serves unsuccessfully for a set loses a concrete opportunity to end it; the match still follows ordinary game scoring.

**Predicted behavior (measurable):** After being broken when serving at 5–4, the failed closer breaks the opponent at 5–5 less often than comparable returners at 5–5 following a hold.

**Why FanDuel's price ignores it:** Unverified hypothesis: an unchanged hold-rate formula misses immediate carryover from the failed close. Ability and score-path selection could explain the whole association.

**Trigger (observable, timestamped):** Break ending the 5–4 game; target is the opponent's next service game at 5–5. Record game-end, server and quote timestamps.

**Sport-side test: data source, cost, kill criterion:** Sackmann point-by-point; free, <=1 hour. Compare break rates at 5–5 by whether the preceding game was a failed serve for set or a hold, with returner/tour strata where supported. Kill if >=100 exposed games show <3 percentage points lower break rate; otherwise unresolved when sparse.

**Book-side test: what odds at trigger time, forward or historical:** Forward paired 5–5 hold/break odds and the pre-5–4 baseline. Require a price discrepancy after known ability and actual serving order.

**Status:** idea

**Result:** Not tested; a psychological explanation is speculation.
