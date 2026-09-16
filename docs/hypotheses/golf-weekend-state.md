# G5 — Weekend prices and information from early rounds

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / pre-round weekend 2-balls / FanDuel.

**Structural fact:** Completed early rounds reveal event-specific scoring conditions and player state before weekend pairings are posted.

**Predicted behavior (measurable):** Early-round residuals predict later-round residuals by >=0.1 strokes per prior stroke, or a prewritten position contrast exceeds 0.2 strokes.

**Why FanDuel's price ignores it:** Unverified: the weekend derivative uses an insufficient update from its pre-tournament skill input.

**Trigger (observable, timestamped):** Official final round-two/three scores and posted next-round pairing, captured before its first tee time.

**Sport-side test: data source, cost, kill criterion:** Use 2025 individual four-round events and each player’s pre-event previous-20-round ability (minimum 10). First compare later residual means in fixed early-residual bins <=-2, (-2,2), >=2 strokes/round, >=200 players across 15 events. Describe regression-to-mean and cut selection; no future ability baseline. Kill if contrast per prior stroke <0.1. Any distinct leaderboard-position test must declare its contrast before outcomes; the existing Sunday-dispersion card retains its original cohort.

**Book-side test: what odds at trigger time, forward or historical:** Compare implied weekend mean changes with the sport-side update. Kill if >=70% already appears. Book-implied changes depend on the assumed score distribution, which must be reported.

**Status:** idea (sport-side unresolved)

**Result:** The [September 14 screen](../../reports/golf-weekend-screen-2026-09-14.md) used 2024 history and the fixed 2025 bins. Round three: 200 matched player-events across 11 events, later/early contrast 0.1597 (0.9735 / 6.0975 strokes); round four: 197 across 11, contrast 0.0836. Both miss the 15-event gate and remain unresolved. Cut selection is substantial: only 102 of 616 high-bin players had a complete round three. No FanDuel prices were tested; no bin changes or season expansion rescue this result. The older Sunday-variance cohort remains unchanged.
