# Wind and home-run props

**Sport / market / book:** Baseball at Wrigley Field / hitter home-run props / FanDuel.

**Structural fact:** Wind direction relative to the field can change airborne-ball travel.

**Predicted behavior (measurable):** Home-run frequency on fly balls differs between strong outward and inward wind, beyond any shift in total run expectation.

**Why FanDuel's price ignores it:** Unverified hypothesis: a moved game total does not fully propagate to hitter HR probabilities or their tails.

**Trigger (observable, timestamped):** Published pregame wind >=15 mph classified by stadium orientation, with roof/open-air status and forecast issue time verified.

**Sport-side test: data source, cost, kill criterion:** MLB StatsAPI game weather and batted-ball events; free, <=1 hour coverage check. Compare HR per airborne batted ball by wind direction and batter handedness/season; do not substitute postgame weather for an entry forecast. Kill if >=500 exposed airborne balls show <20% relative HR-rate difference; missing direction unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward hitter HR prices plus paired game total, after each forecast update; retain all available opposing outcomes and state margin-removal uncertainty for one-sided props.

**Status:** idea

**Result:** Not tested; a well-known physical effect may be fully priced.
