# Position-player pitching

**Sport / market / book:** Baseball / live inning or team total over / FanDuel.

**Structural fact:** A team may preserve its bullpen by using a position player in a lopsided game, subject to current league eligibility rules.

**Predicted behavior (measurable):** Runs per remaining inning rise sharply once the announced incoming pitcher is a position player.

**Why FanDuel's price ignores it:** Unverified hypothesis: live derivative prices lag the substitution announcement or retain an ordinary reliever run rate.

**Trigger (observable, timestamped):** Official incoming-pitcher announcement and identity, before the first pitch. Score alone is a prediction of substitution, not a confirmed trigger.

**Sport-side test: data source, cost, kill criterion:** Existing MLB StatsAPI play-by-play and roster positions; free, <=1 hour. Compare runs in exposed innings to same inning/margin states with ordinary relievers, separating inherited runners. Kill if >=100 exposed innings show <0.5 additional runs; sparse cases unresolved. Verify current eligibility rules before forward use.

**Book-side test: what odds at trigger time, forward or historical:** Timestamped pre/post-announcement live team/inning totals and suspension state, with inning/base/out context. Availability before the first pitch must be demonstrated.

**Status:** idea

**Result:** Not tested; neither an early substitution forecast nor FanDuel lag is established.
