# Golf source screen — September 13, 2026

**Unresolved: the fixed 2025 variance test could not run.** No sport-side effect or FanDuel price discrepancy was measured. The new [card](../docs/hypotheses/golf-sunday-chasing-variance.md) was written before outcome comparisons.

The official PGA TOUR schedule pages were downloaded and parsed: 50 historical 2025 entries and 49 current 2026 entries. The first historical leaderboard request returned 403. No further historical leaderboards were requested.

Data Golf's [raw archive](https://datagolf.com/raw-data-archive) expressly requires paid annual access. Its linked free 2021 Masters sample was successfully downloaded: 88 players, 284 scored rounds, and 54 complete four-round players. The sample contains round scores, course par, tee times and strokes gained. It supplies neither the fixed 2025 season nor earlier events for the prior-ability baseline. It was inspected for schema/coverage only; it was not substituted into the test.

The [current official schedule](https://www.pgatour.com/schedule/2026) has eight fall stroke-play events from September 17 through November 22, followed by December events. Golf therefore has more runway than the deferred MLB season, though this PGA TOUR fall alone is only about ten weeks. The live schedule calls the November 12–15 event **Austin Championship**; older launch articles called it Good Good Championship.

| Event | Dates |
| --- | --- |
| Biltmore Championship Asheville | Sep 17 - 20, 2026 |
| Presidents Cup | Sep 24 - 27, 2026 |
| Bank of Utah Championship | Oct 1 - 4, 2026 |
| Baycurrent Classic | Oct 8 - 11, 2026 |
| Butterfield Bermuda Championship | Oct 22 - 25, 2026 |
| VidantaWorld Mexico Open | Oct 29 - Nov 1, 2026 |
| World Wide Technology Championship | Nov 5 - 8, 2026 |
| Austin Championship | Nov 12 - 15, 2026 |
| The RSM Classic | Nov 19 - 22, 2026 |
| Hero World Challenge | Dec 3 - 6, 2026 |
| PGA TOUR Q-School presented by Korn Ferry | Dec 10 - 13, 2026 |
| Grant Thornton Invitational | Dec 11 - 13, 2026 |

The PGA TOUR schedule includes team and qualifying events. This table is a calendar inventory, not a statement that all entries qualify for the card's individual stroke-play test.

**Next concrete input:** permitted 2025 individual event round scores, stable player IDs, event dates, format/starting-stroke flags and at least ten prior-event rounds for each eligible player. The existing card fixes the 4–6 versus 8–10 stroke groups, sample gate and 1.15 variance-ratio gate. Do not retune them or call a source failure a negative result.

No FanDuel round-score market was verified for a current event and no executable quote was recovered. Data Golf documents historical FanDuel odds in several markets, but that authenticated archive was not acquired and does not establish coverage for alternative player round-score lines.

Reproduce the cached inventory with `python tools/explore_golf_sources.py`; `--fetch` downloads only missing copies of the three permitted inputs once. The script is a source checkpoint, **not an implemented variance estimator**. Source URLs, SHA-256 hashes, sizes, sample schema and the exact 403 are in the [JSON report](golf-source-screen-2026-09-13.json). Raw publisher data stays ignored.
