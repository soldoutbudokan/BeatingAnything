# Missing creator and teammate assists

**Sport / market / book:** Basketball / secondary ball-handler assists / FanDuel.

**Structural fact:** Removing a primary creator redistributes initiation duties as well as shot attempts.

**Predicted behavior (measurable):** A preidentified backup ball-handler's assists per minute and expected minutes rise when the primary creator is officially ruled out.

**Why FanDuel's price ignores it:** Unverified hypothesis: an assist prop lags availability news longer than team or scorer markets.

**Trigger (observable, timestamped):** Official injury-report update rules the creator out, before tip; backup role defined from earlier lineups/minutes, not the eventual box score.

**Sport-side test: data source, cost, kill criterion:** NBA official injury reports and play-by-play/box scores via nba_api where accessible; free, <=1 hour. Compare role-defined players across creator-in/out games and report minutes and assist rate separately. Kill if >=100 player-games show <1 additional expected assist; unavailable historical report times unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward assist line and both prices immediately before/after official update, with source and collector clocks. Reposted suspended lines count only after availability returns.

**Status:** idea

**Result:** Sport-side comparison pending; a known role change may already be fully priced. September 13 source work located 3,970 archived injury PDFs dated within 2024–25 and downloaded NBA Stats-derived player boxscores covering all 1,230 regular-season games. The PDF count is an archive inventory, not 3,970 downloaded or validated reports. One official PDF matched its pinned archive copy exactly. Its filename said `05PM` while its header said `05:30 PM`, so use in-document issue times. A schedule/boxscore filename-year mismatch was also caught before outcome analysis. See [source hashes, timing limits and the next bounded test](../season-runway-2026-09-13.md). This is an active longer-season research candidate; it has no measured assist effect or FanDuel pricing evidence yet.
