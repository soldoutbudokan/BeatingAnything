# Position-player pitching

**Sport / market / book:** Baseball / live inning or team total over / FanDuel.

**Structural fact:** A team may preserve its bullpen by using a position player in a lopsided game, subject to current league eligibility rules.

**Predicted behavior (measurable):** Runs per remaining inning rise sharply once the announced incoming pitcher is a position player.

**Why FanDuel's price ignores it:** Unverified hypothesis: live derivative prices lag the substitution announcement or retain an ordinary reliever run rate.

**Trigger (observable, timestamped):** Official incoming-pitcher announcement and identity, before the first pitch. Score alone is a prediction of substitution, not a confirmed trigger.

**Sport-side test: data source, cost, kill criterion:** Existing MLB StatsAPI play-by-play and roster positions; free, <=1 hour. Compare runs in exposed innings to same inning/margin states with ordinary relievers, separating inherited runners. Kill if >=100 exposed innings show <0.5 additional runs; sparse cases unresolved. [Current eligibility verified from MLB](https://www.mlb.com/news/mlb-two-way-player-rules).

**Book-side test: what odds at trigger time, forward or historical:** Timestamped pre/post-announcement live team/inning totals and suspension state, with inning/base/out context. Availability before the first pitch must be demonstrated.

**Status:** sport-side confirmed

**Operational priority, September 13 user update:** deferred for the remainder of the 2026 MLB season. The user requested markets with more season runway; NFL and upcoming NBA props take priority. The result and untested book-side requirements below are preserved for a later season.

**Result:** September 13, 2026: [2025 official-feed exploration](../../reports/mlb-position-pitching-2026-09-13.md) found 112 clean position-player inning starts with exact inning/half/signed-margin controls (237 ordinary-reliever innings): 1.304 versus weighted 0.639 runs, **+0.664 runs**, above the fixed 0.5 screen. The descriptive game-cluster 95% interval is +0.173 to +1.155, so the effect's size remains uncertain. Across 131 appearances, 27 inherited runners (7 scored) were tracked separately; two-way players were excluded. Substitution/first-pitch times exist for all 131 entries but do not prove public availability or an open FanDuel quote. The next scientific stage would be book-side collection when this card becomes active again; neither an early substitution forecast nor FanDuel lag is established.
