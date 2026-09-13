# Missing creator and teammate assists

**Sport / market / book:** Basketball / secondary ball-handler assists / FanDuel.

**Structural fact:** Removing a primary creator redistributes initiation duties as well as shot attempts.

**Predicted behavior (measurable):** A preidentified backup ball-handler's assists per minute and expected minutes rise when the primary creator is officially ruled out.

**Why FanDuel's price ignores it:** Unverified hypothesis: an assist prop lags availability news longer than team or scorer markets.

**Trigger (observable, timestamped):** Official injury-report update rules the creator out, before tip; backup role defined from earlier lineups/minutes, not the eventual box score.

**Sport-side test: data source, cost, kill criterion:** NBA official injury reports and play-by-play/box scores via nba_api where accessible; free, <=1 hour. Compare role-defined players across creator-in/out games and report minutes and assist rate separately. Kill if >=100 player-games show <1 additional expected assist; unavailable historical report times unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward assist line and both prices immediately before/after official update, with source and collector clocks. Reposted suspended lines count only after availability returns.

**Status:** idea — fixed preceding-day sport-side screen executed, insufficient exposures.

**Result:** The September 13 [executed 2024–25 screen](../../reports/nba-creator-assists-2026-09-13.md) used all 1,230 regular-season games, 158 exact-hash archived NBA reports and prior-only roles declared before comparison. Of 1,529 role-eligible team-games, only 25 had an explicit preceding-day creator Out entry and an eligible secondary. Mean assists were 4.960 versus a same-player prior creator-present baseline of 4.000: **+0.960**, descriptive team-cluster 95% interval **−0.229 to +2.219**. Minutes were 31.318 versus 29.441; assists per 36 were 5.702 versus 4.891. One preselected secondary DNP was retained as zero. The 100-exposure gate was not met, so this is unresolved, not confirmed or killed. No alternate cutoff, added season or role variant was tried after the result. Missing player rows were never inferred Available. The preceding-day sample does not test intraday news or FanDuel repricing.

**Next:** Move to other hypotheses; do not rerun this fixed sample or expand archive pages without a specific new sampling question. A later test needs reliable scheduled tip times and separately declared same-day report cutoffs, or a sufficiently sized prospective announcement cohort. Actual FanDuel assist quotes around the official update remain necessary before any pricing claim. The [precomparison declaration](../nba-creator-assists-screen-declaration-2026-09-13.md), [result JSON](../../reports/nba-creator-assists-2026-09-13.json), acquisition script and small analysis script preserve a runnable completed screen.
