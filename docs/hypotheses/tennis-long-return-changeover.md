# Recovery after a long return game

**Sport / market / book:** Tennis singles / live next-game hold or break / FanDuel.

**Structural fact:** The standard rules allow a seated changeover after odd games other than a set's first game. A long return game can therefore end just before a service game with, or without, that scheduled recovery opportunity. This is a different trigger from a player's own long service game.

**Predicted behavior (measurable):** After a return game of at least 16 points, the next same-set service game has higher break risk without a scheduled changeover. The excess should exceed the corresponding no-changeover versus changeover difference after short return games of 4–8 points.

**Why FanDuel's price ignores it:** Unverified hypothesis: live next-game probabilities reuse a serving-strength estimate without conditioning on the interaction of just-completed return workload and scheduled recovery.

**Trigger (observable, timestamped):** Completion of the immediately preceding return game, its point count, and the current set's completed-game count. The upcoming service game must be regular and in the same set. Exclude the first game's side switch, all set breaks and tiebreak transitions. This is a rules-scheduled opportunity, not a claim that an actual 90-second rest was measured.

**Sport-side test: data source, cost, kill criterion:** Fix the entire pinned Match Charting Project men's 2020s file at commit `2c59eef194967e688b69e73df344184a06322cd8`, using the existing complete-match parser. This is inspected exploratory data, not an untouched holdout. Take every eligible next service game after a return game of >=16 points or 4–8 points, with at least two games already completed in that set. Odd completed-game count identifies scheduled changeover; even identifies no scheduled changeover. Before outcomes, fix a minimum of 200 long-return observations in each arm, a positive raw long-return no-changeover minus changeover break-rate difference, and a difference-in-differences of at least +3 percentage points after subtracting the corresponding short-return contrast. Below either count is unresolved; failure of the directional/effect gate kills this specification. Report match-clustered descriptive uncertainty, year/surface splits and preceding return-game outcome without choosing a favorable subgroup. No fit or threshold tuning.

**Book-side test: what odds at trigger time, forward or historical:** Actual FanDuel paired next-game hold/break quotes immediately after the return game, mapped to match, set score, server, point count and both quote/state clocks. Verify tournament timing exceptions and actual interruptions separately. A bookmaker discrepancy and fresh prospective validation are required even if the sport screen passes.

**Status:** sport-side dead

**Result:** [September 13 screen](../../reports/tennis-return-changeover-2026-09-13.md): after a >=16-point return game, the next server was broken 73/338 times without scheduled changeover (21.60%) and 52/292 with changeover (17.81%), a raw +3.79 percentage points. The corresponding short-return contrast was already +1.86 points; the fixed difference-in-differences was **+1.93 points**, below +3 (descriptive match-clustered 95% interval −4.30 to +8.16). Both long-return arms exceeded the fixed 200-game minimum. Kill this specification in this inspected sample; do not select a favorable surface or expand the archive to rescue it. No FanDuel prices or edge were measured. Card and gates preceded the conditional computation. Source rule: [ITF Rules of Tennis 2026, rules 10 and 29](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf). Scheduled rest remains a proxy for unmeasured actual recovery and event-specific exceptions.
