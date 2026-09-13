# Prolonged service-game carryover

**Sport / market / book:** Tennis / live next service-game hold or break / FanDuel.

**Structural fact:** An extended deuce game adds effort without adding extra games to the scoreboard.

**Predicted behavior (measurable):** A player is broken more often in their next service game after a >=16-point service hold than after a 4–8-point hold.

**Why FanDuel's price ignores it:** Unverified hypothesis: a game-score/static-hold formula misses recent point volume. Long games can also signal opponent strength; the mechanism is not established.

**Trigger (observable, timestamped):** A completed service hold lasting >=16 points; evaluate the player's next regular service game in the same set, only if the intervening return game has <=8 points. First qualifying exposure per player-set. Log both game-completion times and quote times.

**Sport-side test: data source, cost, kill criterion:** Sackmann point-by-point; free, <=1 hour. Compare next-game break rates after 4–8-point holds using the same intervening-game rule; describe player/tour/surface and score differences where available. Kill if >=100 exposures show <3 percentage points increase; smaller samples unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward hold/break pair before the target game, prior-game quote, and timestamped intervening state. Test whether any sport-side difference survives current FanDuel prices and vig.

**Status:** idea

**Result:** September 12 exploratory screen: 102/417 exposed games were breaks (24.46%) versus 3,207/16,478 controls (19.46%), +5.00 percentage points. The raw screen passes, but the within-match residual difference falls to +2.39 points (descriptive 95% interval −1.83 to +6.61); the exposed players' other-set baseline is 23.89%. Keep as an unresolved idea, not sport-side confirmed: ability, match conditions and score selection may explain the association. Data are curated men's Match Charting Project matches, excluding incomplete records; no untouched holdout or FanDuel price evidence. See [results and limitations](../../reports/tennis-state-exploration.md).

September 13 fixed-definition follow-up in the same pinned source's men's 2010s file: 79/291 exposed games were breaks (27.15%) versus 2,155/10,704 controls (20.13%), +7.02 points. The raw association repeats in an earlier period. The unchanged within-match residual contrast is +4.83 points (descriptive 95% interval −0.29 to +9.94); exposed players' other-set break rate is 24.48%. Remains an unresolved idea: strength and score selection still matter, the residual interval includes zero, and the source is the same curated project. This is exploratory replication, not an untouched holdout or sport-side confirmation. Next useful evidence is matching timestamped hold/break prices and a prospective strength-aware comparison; no edge is demonstrated. See [fixed follow-up](../../reports/tennis-followup-2026-09-13.md).
