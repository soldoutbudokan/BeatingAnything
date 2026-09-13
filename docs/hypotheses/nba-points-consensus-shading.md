# 39. NBA points: FanDuel versus paired reference prices

**Sport / market / book:** NBA full-game `player_points` half-point lines / FanDuel.

**Structural fact:** Books can shade or update individual props differently while posting the same player and line.

**Prediction and trigger:** A contemporaneous median reference probability, devigged two ways, implies at least 3% net return at FanDuel after a 2% haircut to winnings. Reference consensus can be wrong; realized returns must test it.

**Fixed test:** See the immutable [declaration](../nba-points-consensus-declaration-2026-09-13.md). FanDuel plus at least three other paired books, strict original snapshot clocks, one selection per independently matched game. 2024–25 regular season first; freeze and reserve represented 2025–26 regular season separately. No outcome-based eligibility, aliases or threshold tuning.

**Gate:** At least 100 settled games and positive haircut ROI with game-bootstrap 95% lower bound above zero. Actual FanDuel archived prices are used, but consensus and simulated settlement alone do not establish current execution or the project's independent/forward edge gate.

**Status:** Executed; underpowered at fixed settings, no demonstrated edge.

**Result:** All 3,394 original quote files were verified. Across 2,446 matched games in the fixed 2024–25 and 2025–26 regular seasons, 6,071 FanDuel player/line pairs had at least three eligible reference books. Exactly one side cleared the fixed score; it occurred in 2025–26 and won (+0.9212 units after haircut). Zero first-period selections and one later-period selection both fail the 100-settled-game gate. The one-game ROI/bootstrap is uninformative; no subgroup or threshold rescue. See the [executed report](../../reports/nba-points-consensus-2026-09-13.md). Raw publisher files remain ignored.
