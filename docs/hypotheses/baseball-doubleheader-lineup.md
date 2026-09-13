# Doubleheader lineup changes

**Sport / market / book:** Baseball / game-two hitter props and team totals / FanDuel.

**Structural fact:** Teams can change catchers and regular starters between doubleheader games.

**Predicted behavior (measurable):** Announced game-two lineups have fewer projected plate appearances for regulars than the pre-lineup assumed lineup.

**Why FanDuel's price ignores it:** Unverified hypothesis: player/derivative markets lag the actual lineup announcement. Nonstarter void rules can remove the apparent opportunity.

**Trigger (observable, timestamped):** Official game-two lineup publication, identified by exact game ID rather than date alone.

**Sport-side test: data source, cost, kill criterion:** MLB StatsAPI lineups, substitutions and schedule; free, <=1 hour. Count lineup omissions and changed batting slots versus game one, then remaining participation. Kill if applicable settlement voids every actionable omission or >=100 cases show <0.5 PA change; missing pre-announcement lineup assumptions unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward same-game-ID props before/after lineup release, market status and rule snapshots. Test a posted active player's revised slot or changed team total only where settlement permits comparison.

**Status:** idea

**Result:** Not tested; absence from a lineup is not a guaranteed winning under.
