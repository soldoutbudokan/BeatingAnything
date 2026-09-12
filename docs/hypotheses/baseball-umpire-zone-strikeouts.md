# Umpire-zone strikeouts

**Sport / market / book:** Baseball / starting-pitcher strikeout props / FanDuel.

**Structural fact:** Called strikes near the zone boundary depend partly on the home-plate umpire, under the applicable competition rules.

**Predicted behavior (measurable):** Pitchers with many prior called-edge pitches show larger strikeout differences across umpires with different prior called-strike tendencies.

**Why FanDuel's price ignores it:** Unverified hypothesis: strikeout props lag a newly published umpire assignment or omit this interaction.

**Trigger (observable, timestamped):** Official plate-umpire assignment publication, before entry; archive any later crew change.

**Sport-side test: data source, cost, kill criterion:** MLB StatsAPI assignments and available pitch-location/call data; free, <=1 hour feasibility screen. Use prior-season edge-pitch/umpire bins and current-game strikeouts, with starter opportunity separated. Kill if >=200 eligible starts show <0.5 strikeout conditional difference; unavailable pitch coordinates unresolved. No match-moneyline fit.

**Book-side test: what odds at trigger time, forward or historical:** Paired strikeout prices and line immediately before/after assignment, alongside same-time reference quotes. Determine whether news was already reflected.

**Status:** idea

**Result:** Not tested; future umpire statistics must not be used as pregame information.
