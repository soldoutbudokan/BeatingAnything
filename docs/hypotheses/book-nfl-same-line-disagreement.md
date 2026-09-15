# NFL same-line price disagreement

**Sport / market / book:** NFL / full-game half-point spreads and totals / FanDuel, Pinnacle reference.

**Structural fact:** Separate books can quote different payouts for an identical outcome and line.

**Predicted behavior (measurable):** Some fresh FanDuel prices offer at least 3% reference-implied excess return after a 2% haircut to net winnings, using both proportional and power de-vigging of the paired Pinnacle market.

**Why FanDuel's price ignores it:** Unverified hypothesis: book-specific shading or delayed adjustment leaves a better price. Pinnacle error or archive timing can also explain disagreement. This tests price differences, not a sport model or proven repricing lag.

**Trigger (observable, timestamped):** First qualifying archived snapshot per event, one to 24 hours before the earliest recorded source start; both books' updates at most 90 seconds old, exact same half-point line and two sides, each book overround 0–8%, FanDuel decimal price 1.20–6.00. Select the largest qualifying score at that first snapshot, then alphabetical market/side for ties.

**Sport-side test: data source, cost, kill criterion:** No sport model. Use the already pinned NFL DuckDB; no outcomes or fitting. This is a new direct price screen, distinct from the unavailable derivative archive. If no qualifying observations exist, deprioritize this specific route; fewer than 100 distinct events leaves the lead too sparse for confirmation.

**Book-side test: what odds at trigger time, forward or historical:** Count all comparisons and first qualifying event observations. Check the selected price against the last fresh same-line Pinnacle pair within 30 minutes before the conservative source start; retain missing closes. These are archive-clock diagnostics, not verified official-start CLV or executable offers. Fresh direct evidence and settlement compatibility remain necessary.

**Status:** book-side dead

**Result:** Defined September 13 before inspecting price differences. [The fixed price screen](../../reports/nfl-price-screen-2026-09-13.md) found 908 matched pairs / 1,816 compared sides, with zero observations clearing +3%. Maximum conservative reference excess was +1.13% for spreads and +1.69% for totals after the winnings haircut. Deprioritize this exact half-point, fresh-pair, one-to-24-hour archive route; do not lower the threshold or treat omitted integer lines as already tested. No outcomes, realized returns or executable-price claims were used.
