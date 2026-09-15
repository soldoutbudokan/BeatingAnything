# Qualifier workload

**Sport / market / book:** Tennis / main-draw first-round second-set break and game totals / FanDuel.

**Structural fact:** Qualifying rounds can create a concentrated workload immediately before the main draw.

**Predicted behavior (measurable):** A qualifier completing three matches in the prior three days has a larger first-to-second-set drop in hold rate than other first-round entrants.

**Why FanDuel's price ignores it:** Unverified hypothesis: derivative set prices reuse a match-level strength estimate without enough workload dependence. Qualifier status itself is public and may already be priced.

**Trigger (observable, timestamped):** Official draw/schedule and completed qualifying results establish three completed matches on three preceding dates before entry; set-two start for live quotes.

**Sport-side test: data source, cost, kill criterion:** Sackmann match and point records, qualifying files and official dates; free, <=1 hour coverage check. Compare within-player first-to-second-set hold changes with other first rounds, report tour/surface differences. Kill if >=100 eligible matches show <4 percentage points additional decline; missing qualifying coverage unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward first-round set markets and next-game pairs; retain qualifying timestamps and paired main prices only as references.

**Status:** idea

**Result:** Not tested. No generic workload regression against a match moneyline is proposed.
