# Same-day workload

**Sport / market / book:** Tennis / second-match late-set game totals and break markets / FanDuel.

**Structural fact:** Rain rescheduling can require two singles matches in one day with limited recovery.

**Predicted behavior (measurable):** Players completing >=120 minutes earlier that day lose service games more often in set two of the later match than comparable players without an earlier match.

**Why FanDuel's price ignores it:** Unverified hypothesis: derivative prices update underlying ability less than the match price after exceptional same-day load.

**Trigger (observable, timestamped):** Official first-match completion and second-match start establish same local calendar day and elapsed recovery; observe set-two start before quoting.

**Sport-side test: data source, cost, kill criterion:** Sackmann match/point records plus official schedules; free where available, <=1 hour availability screen. Compare set-two break rates by player/tour/surface, distinguish earlier retirements. Kill if >=100 eligible matches show <4 percentage points increase; missing reliable times means unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward later-match set-two game markets, pre-match odds and source-stamped schedule updates. Use actual completed earlier load, not an eventual schedule reconstructed after the fact.

**Status:** idea

**Result:** Not tested; point-by-point files alone may not resolve wall-clock recovery.
