# Blowout removal of hitters

**Sport / market / book:** Baseball / live remaining hits or total bases under / FanDuel.

**Structural fact:** Replacing a hitter removes their future plate appearances even though the team continues batting.

**Predicted behavior (measurable):** Regular starters in games with a >=7-run margin after six innings receive fewer remaining plate appearances than in <=3-run games.

**Why FanDuel's price ignores it:** Unverified hypothesis: remaining-production props project regular batting-order opportunities without enough substitution probability.

**Trigger (observable, timestamped):** End of sixth inning, margin >=7, player still active; record lineup position, current prop progress and all timestamps.

**Sport-side test: data source, cost, kill criterion:** MLB StatsAPI substitutions and plate appearances; free, <=1 hour. Tabulate remaining PA by margin, lineup slot, home/away and team-leading/trailing status. Kill if >=200 exposed player-games show <0.4 fewer PA after those comparisons; distinguish shortened games.

**Book-side test: what odds at trigger time, forward or historical:** Forward player prop lines/prices and current accrued stats at trigger; verify the prop remains offered and its participation/substitution settlement rules.

**Status:** idea

**Result:** Not tested. Lower future opportunity is not automatically an under at a repriced line.
