# Missing creator and teammate assists

**Sport / market / book:** Basketball / secondary ball-handler assists / FanDuel.

**Structural fact:** Removing a primary creator redistributes initiation duties as well as shot attempts.

**Predicted behavior (measurable):** A preidentified backup ball-handler's assists per minute and expected minutes rise when the primary creator is officially ruled out.

**Why FanDuel's price ignores it:** Unverified hypothesis: an assist prop lags availability news longer than team or scorer markets.

**Trigger (observable, timestamped):** Official injury-report update rules the creator out, before tip; backup role defined from earlier lineups/minutes, not the eventual box score.

**Sport-side test: data source, cost, kill criterion:** NBA official injury reports and play-by-play/box scores via nba_api where accessible; free, <=1 hour. Compare role-defined players across creator-in/out games and report minutes and assist rate separately. Kill if >=100 player-games show <1 additional expected assist; unavailable historical report times unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward assist line and both prices immediately before/after official update, with source and collector clocks. Reposted suspended lines count only after availability returns.

**Status:** idea

**Result:** Not tested; a known role change may already be fully priced.
