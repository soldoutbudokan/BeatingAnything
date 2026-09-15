# Weather and parlay dependence

**Sport / market / book:** Football / same-game combination of two passing-related unders / FanDuel.

**Structural fact:** A common wind or precipitation shock can affect multiple passing outcomes together.

**Predicted behavior (measurable):** The joint probability of both teams falling under comparable passing thresholds exceeds the product of marginal probabilities in severe-weather conditions.

**Why FanDuel's price ignores it:** Unverified hypothesis: FanDuel's actual SGP adjustment understates weather-conditioned dependence. It is not assumed to price legs independently.

**Trigger (observable, timestamped):** Issued outdoor-game weather forecast and simultaneously available two-leg SGP quote, with exact marginal lines captured.

**Sport-side test: data source, cost, kill criterion:** nflverse passing totals/weather plus historically available marginal thresholds if present; free, <=1 hour availability check. Tabulate joint versus product frequencies using thresholds fixed without future outcomes. Kill if >=100 comparable games show <3 percentage points joint excess; no timely lines/weather means unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Capture the actual SGP price, all leg prices and rule restrictions together. Compare joint fair probability with the quoted combined price after uncertainty; multiplying leg prices is not a substitute.

**Status:** idea

**Result:** Not tested. No simulation or parlay claim is justified until the conditional effect and real SGP offers are observed.
