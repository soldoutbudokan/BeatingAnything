# Added-time exposure

**Sport / market / book:** Soccer / live remaining-match goals over after minute 85 / FanDuel.

**Structural fact:** Additional playing time expands scoring exposure beyond the nominal 90-minute clock.

**Predicted behavior (measurable):** At 90 minutes, a publicly announced >=8 minutes of added time produces more further goals than an announcement <=4 minutes, conditional on score state.

**Why FanDuel's price ignores it:** Unverified hypothesis: a live total briefly retains a shorter default remaining-time assumption after the board is shown.

**Trigger (observable, timestamped):** Official added-time announcement and current clock/score, captured when public; do not use the eventual final whistle as advance information.

**Sport-side test: data source, cost, kill criterion:** Official competition match timelines with announced added time and goal times; football-data/FBref only if those required fields exist. Free, <=1 hour availability check. Compare goal probability before final whistle by announced time and score. Kill if >=200 cases show <3 percentage points difference; missing announcement field unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward paired live total at minute 85, before/after added-time announcement, and reliable event times. Verify inclusion of normal added time versus extra time under market rules.

**Status:** idea

**Result:** Not tested; broad historical changes in stoppage time alone cannot establish a current price error.
