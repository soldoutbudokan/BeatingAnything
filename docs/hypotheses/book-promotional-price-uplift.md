# Promotional price uplift

**Sport / market / book:** Multiple sports / explicitly boosted prices / FanDuel.

**Structural fact:** A boost changes the payout while eligibility, stake limits and settlement may restrict its value.

**Predicted behavior (measurable):** Some eligible boosted prices may exceed a defensible fair-price estimate after rules and uncertainty are accounted for.

**Why FanDuel's price ignores it:** Unverified hypothesis: acquisition/retention spending occasionally produces positive customer expected value. A boost relative to an ordinary price is not sufficient evidence.

**Trigger (observable, timestamped):** A published offer is available to the relevant account/jurisdiction; capture full terms, price, cap, expiry and cash/credit settlement without enrolling or wagering.

**Sport-side test: data source, cost, kill criterion:** No new sport model. <=1 hour check for matched liquid reference outcomes and compatible settlement; use a joint reference for parlays. Kill if rules prevent valuation or even the optimistic fair-probability bound yields nonpositive expected value.

**Book-side test: what odds at trigger time, forward or historical:** Record contemporaneous boosted and unboosted prices plus paired reference markets. Advance only if conservative expected value is >3% after promotion restrictions; archive all offers sampled, not just attractive ones.

**Status:** idea

**Result:** Not tested. No offer availability, account eligibility, or profitable boost has been established.
