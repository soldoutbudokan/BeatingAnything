# Doubles match-tiebreak totals

**Sport / market / book:** Tennis doubles / match total games and alternative totals / FanDuel.

**Structural fact:** Some formats use a deciding match tiebreak instead of a full final set; its treatment in game totals is market-rule dependent.

**Predicted behavior (measurable):** The total-games distribution has a different upper tail from a full deciding-set distribution.

**Why FanDuel's price ignores it:** Unverified hypothesis: an alternative-total template occasionally carries the wrong deciding-format or settlement assumption.

**Trigger (observable, timestamped):** Official event format and market rules known before entry; optional live trigger at one set all. Archive both rule texts and quote times.

**Sport-side test: data source, cost, kill criterion:** Official tournament rules and Sackmann doubles scores where covered; free, <=1 hour. Count total games under the actual settlement mapping and a full-set counterfactual. Kill if no offered line separates the distributions materially or rules/coverage cannot be verified; no model fit needed.

**Book-side test: what odds at trigger time, forward or historical:** Forward full alternative-total ladder and paired sides at identical match state; verify match-tiebreak inclusion and line identity before pricing discrepancies.

**Status:** idea

**Result:** Not tested; no assertion of a current FanDuel format error.
