# Goalie news and team totals

**Sport / market / book:** Hockey / opposing team total and goal props / FanDuel.

**Structural fact:** Confirming a different starting goalie changes the scoring matchup before puck drop.

**Predicted behavior (measurable):** Goals allowed per shot differ for the newly confirmed goalie enough to change the opponent's scoring distribution at the same shot opportunities.

**Why FanDuel's price ignores it:** Unverified hypothesis: team-total or goal-prop repricing lags the more visible match market after goalie confirmation.

**Trigger (observable, timestamped):** Official team/league confirmation replaces the previously recorded expected starter; morning-skate speculation alone is not confirmation.

**Sport-side test: data source, cost, kill criterion:** Official NHL goalie starts, shots and confirmations; free, <=1 hour availability screen. Use only prior goalie results for a coarse expected goal difference at typical shot count. Kill if no plausible >=0.3-goal shift or no timed expectation/confirmation history; sparse histories unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward team-total ladders and relevant paired goal markets before/after news, with same-time reference prices. A match-moneyline response is a comparison, not the target model.

**Status:** idea

**Result:** Not tested; goalie ability estimates and derivative-market lag remain unverified.
