# Empty-net exposure

**Sport / market / book:** Hockey / live remaining-goals over and leading-team next goal / FanDuel.

**Structural fact:** A trailing team can remove its goalie for an extra attacker, changing scoring risk in both directions.

**Predicted behavior (measurable):** Combined goals per minute rise after a goalie pull at a one-goal deficit in the final three minutes.

**Why FanDuel's price ignores it:** Unverified hypothesis: a live derivative market temporarily extrapolates ordinary late-game goal intensity or lags goalie-status changes.

**Trigger (observable, timestamped):** Official feed indicates goalie off ice with one-goal deficit and <=180 seconds left; capture score, possession if available, and all timestamps.

**Sport-side test: data source, cost, kill criterion:** Official NHL play-by-play with goalie/empty-net fields; free, <=1 hour. Compare goal hazard per exposed second to same score/clock with both goalies present; report both teams separately and note pull-selection bias. Kill if >=200 pull segments show <50% relative combined-rate increase; ambiguous goalie timing unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward next-goal and total pairs before/after pull with exact clock and market suspension state; include any reprice preceding the observed feed update.

**Status:** idea

**Result:** Not tested; a large sport effect may be routine in FanDuel pricing.
