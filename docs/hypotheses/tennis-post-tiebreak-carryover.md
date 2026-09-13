# Post-tiebreak carryover

**Sport / market / book:** Tennis / next-set opening service-game break / FanDuel.

**Structural fact:** A tiebreak can add many points beyond a normal set ending; the scoreboard resets for the next set.

**Predicted behavior (measurable):** A >=16-point tiebreak loser is broken in their first regular service game of the next set more often than a 7–12-point tiebreak loser.

**Why FanDuel's price ignores it:** Unverified hypothesis: a reset to ordinary hold rates misses immediate carryover. Both players share the long tiebreak, so winner outcomes are a useful diagnostic.

**Trigger (observable, timestamped):** Completed >=16-point tiebreak with another set to play; next first service game of its loser. Record tiebreak completion, next-game start and odds times.

**Sport-side test: data source, cost, kill criterion:** Sackmann point-by-point; free, <=1 hour. Compare first-next-set break rates against 7–12-point tiebreak losers, excluding 13–15 points from this contrast. Report winners in parallel if available, plus tour/serving-order composition. Kill if >=100 exposures show <3 percentage points increase; insufficient sample unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward next-game hold/break pairs before the loser's first service game, with actual serving order. Reject apparent differences explained by a FanDuel reprice already made.

**Status:** sport-side dead

**Result:** September 12 exploratory screen: 29/162 exposed games were breaks (17.90%) versus 180/817 controls (22.03%), −4.13 percentage points (descriptive 95% interval −10.73 to +2.47). This fails the prewritten +3-point prediction; the within-match residual difference is also negative (−4.30 points). Deprioritized in this sample. The winner diagnostic has the opposite raw sign but does not justify reversing the hypothesis after inspection. Data are curated men's Match Charting Project matches with incomplete records excluded, not an untouched holdout. No FanDuel quotes were tested. See [results and limitations](../../reports/tennis-state-exploration.md).
