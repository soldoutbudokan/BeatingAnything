# Derivative repricing lag

**Sport / market / book:** Multiple sports / matched niche totals, alternative lines and props / FanDuel, Pinnacle reference.

**Structural fact:** Quotes from separate books update at distinct times; matching requires identical outcomes and settlement.

**Predicted behavior (measurable):** Following a reference probability move >=3 percentage points, a still-available FanDuel derivative sometimes remains materially better for at least one captured observation.

**Why FanDuel's price ignores it:** Unverified hypothesis: less watched derivative markets update slowly. Aggregator caching can create the same appearance without any book lag.

**Trigger (observable, timestamped):** Paired Pinnacle market moves >=3 points after vig removal; record source-update times, both receipt times, exact event state and FanDuel market status.

**Sport-side test: data source, cost, kill criterion:** No sport model needed. <=1 hour metadata check of retained NFL odds and Odds Gap export for matched derivatives, lines, clocks and book-update fields. Kill the source route if it cannot distinguish state/line or publication lag; missing data is not a negative price result.

**Book-side test: what odds at trigger time, forward or historical:** Authorized full forward snapshots; measure FanDuel/reference discrepancy, duration and subsequent correction. Advance only after >=100 matched observations with positive candidate EV beyond vig/age uncertainty, then seek execution-quality evidence and fresh confirmation.

**Status:** idea

**Result:** Not tested. Pinnacle is a fallible reference, never the target book or proof of execution.
