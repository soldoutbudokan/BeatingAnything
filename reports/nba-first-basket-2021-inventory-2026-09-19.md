# Full 2021 first-basket price inventory

**The 2021 archive contains actual FanDuel prices, but cannot replicate the timed FD/BetMGM player-price test.** All 339 nonempty historical JSON files at the [pinned source](https://github.com/ellache/nba-tipoff-scraper/tree/b1fb92f10d61b94e44bb3d760e9ac269c706a7ab) have now been acquired and checked against their Git blob hashes: 15,939,784 bytes. The previous three-file source sample is preserved. [Full measured inventory](nba-first-basket-2021-inventory-2026-09-19.json).

| Book | Top-level records | Complete literal ten-player boards | Distinct collection-date/team pairs |
|---|---:|---:|---:|
| FanDuel | 904 | 749 | 312 |
| DraftKings | 993 | 630 | 264 |
| PointsBet | 389 | 389 | 170 |
| Unibet | 334 | 332 | 147 |
| Barstool | 363 | 362 | 148 |
| Bovada | 1,453 | 2 | 1 |
| MGM | 1,148 | 0 | 0 |
| Betfair | 82 | 0 | 0 |

A complete board here means ten distinct literal player names and finite nonzero American odds. It does **not** certify fixture identity, market rules, opening-lineup coverage or pregame availability. Nested quarter objects and serialized Python reference directives were not resolved or treated as additional independent boards.

Every top-level collection clock is timezone-free, every retained `gameDatetime` is null, and no bookmaker update time survives. No original FanDuel response file was identified in the pinned tree. Source code creates collection clocks with local `datetime.now()` and drops retrieved game-start fields in its intermediate builder. The resulting date/team groups are therefore not independently verified game IDs, especially because the collector supports tomorrow's games too.

The corpus also illustrates why publisher flags cannot replace actual market identity: DraftKings records usually have `isFirstFieldGoal: false`, while the inspected retrieval code selects the displayed **First Field Goal** market. That false value comes from a default, not verified settlement terms. MGM has no complete player board and its inspected parser selects a team-first-points market.

No target scores, model probabilities, bet selections or strategy returns were computed. The data remains useful as a historical source, but **zero boards qualify under the existing timestamp requirements**. Close this corpus as a route to the declared FD/BetMGM replication; do not infer a timezone, manufacture a quote-update clock, or substitute a team market to enlarge the sample.

The subsequent [eight-repository search](nba-first-basket-expanded-source-search-2026-09-19.json) likewise finds no additional qualified cohort. The concrete next access lead is the [bounded OddsPapi probe](../docs/first-basket-history-access.md), pending a locally configured key.
