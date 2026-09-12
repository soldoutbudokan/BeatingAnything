# Announced veteran rest

**Sport / market / book:** Baseball / late-season hitter props / FanDuel.

**Structural fact:** A team may explicitly announce reduced playing time for a veteran after its competitive objective changes.

**Predicted behavior (measurable):** Players subject to a published workload reduction have fewer plate appearances when active than their normal-start baseline.

**Why FanDuel's price ignores it:** Unverified hypothesis: derivative props retain normal playing-time assumptions until the lineup or substitution becomes explicit.

**Trigger (observable, timestamped):** Dated official manager/team announcement of reduced workload, then a confirmed active lineup. Elimination status alone is insufficient.

**Sport-side test: data source, cost, kill criterion:** Official team reports plus MLB StatsAPI lineups/substitutions; free manual sample, <=1 hour. Compare PA per active start before/after an announcement and comparable lineup slots. Kill if >=50 starts show <0.5 PA reduction; unreliable archived announcements unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward props for active starters after the announcement with rule and lineup snapshots; compare available prices to documented reduced opportunity.

**Status:** idea

**Result:** Not tested. No assumption that an eliminated team stops trying.
