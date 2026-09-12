# Fourth-set concession

**Sport / market / book:** Tennis / fourth-set next-game break and set games under / FanDuel.

**Structural fact:** A best-of-five leader at 2–1 in sets can lose set four and still contest set five.

**Predicted behavior (measurable):** Once two net breaks behind in set four, that leader's next-service break rate exceeds the comparable rate for a player down 1–2 in sets.

**Why FanDuel's price ignores it:** Unverified hypothesis: a static hold model misses the different incentive to preserve energy. The market may already condition on this state.

**Trigger (observable, timestamped):** First service game after falling >=2 net breaks behind in set four while leading 2–1 in sets; record preceding-game and quote times.

**Sport-side test: data source, cost, kill criterion:** Sackmann slam point-by-point; free, <=1 hour after parser reuse. Compare first exposed service games with set-four players trailing 1–2 at the same deficit; show player strength and score composition. Kill if >=50 exposed cases show <5 percentage points excess break probability. Too few cases means unresolved, not confirmation.

**Book-side test: what odds at trigger time, forward or historical:** Forward game hold/break and set-score quotes before/after the deficit, with best-of-five rules and current sets verified. Any set-five claim needs its own later test.

**Status:** idea

**Result:** Unresolved in the [September 12 sport-side screen](../../reports/tennis-state-exploration.md). Set-four leaders at 2–1 lost the target service game in 9/29 cases (31.03%), versus 9/39 (23.08%) for trailers at 1–2: +7.96 percentage points, with a descriptive match-clustered 95% interval of −13.61 to +29.53 points. The exposed sample is below the prewritten 50-case minimum. Other-set break rates for the same players against the same opponents were 18.19% and 30.61%, respectively; the retrospective residual contrast is large but highly uncertain (+20.54 points, interval −0.75 to +41.83). This curated complete-match sample neither confirms nor kills the incentive mechanism. No set-five outcome or FanDuel price was tested; the overlap with the broad double-break population supplies no independent replication.
