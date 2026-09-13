# Medical-timeout serve dip

**Sport / market / book:** Tennis / next service-game break after treatment / FanDuel.

**Structural fact:** A medical interruption identifies an acute condition that may affect serving before it affects final match outcome.

**Predicted behavior (measurable):** A treated player's first subsequent service-game break rate exceeds their pre-interruption baseline, especially for explicitly reported serving-arm conditions.

**Why FanDuel's price ignores it:** Unverified hypothesis: a derivative market resumes from a stale pre-timeout hold parameter. Markets may suspend or fully reprice instead.

**Trigger (observable, timestamped):** Official or authorized timestamped feed records timeout completion and treated player; record any reported condition without inferring a diagnosis.

**Sport-side test: data source, cost, kill criterion:** Official play feeds and Match Charting Project annotations if they contain usable timeout labels; free availability check, <=1 hour. Compare first-post-timeout break rate to earlier service games and untreated opponent; kill if >=100 cases show <5 percentage points increase. Missing timeout labels means unresolved.

**Book-side test: what odds at trigger time, forward or historical:** First available post-timeout hold/break pair with suspension and reactivation history. A suspended quote is unavailable, not stale value.

**Status:** idea

**Result:** Not tested. Timestamped timeout coverage and relevant offered markets remain unknown.
