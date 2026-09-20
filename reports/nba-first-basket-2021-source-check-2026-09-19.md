# Additional first-basket prices: 2021 source check

The pinned [ellache/nba-tipoff-scraper repository](https://github.com/ellache/nba-tipoff-scraper/tree/b1fb92f10d61b94e44bb3d760e9ac269c706a7ab) contains **418 historical JSON files, 339 nonempty, across 55 dates from February 24–April 28, 2021**. The nonempty files total about 15.9 MB. This is a concrete additional odds archive, but no qualified replication cohort has been established.

The [retained source record](nba-first-basket-2021-source-check-2026-09-19.json) includes the complete tree, pinned source hashes and three predetermined schema samples: first, middle and last nonempty filename by date. Only those three historical files and relevant publisher source files were downloaded. No target-game outcomes were joined and no strategy or returns were calculated.

| Sample | Top-level records | Observed books | FanDuel ten-player boards |
|---|---:|---|---:|
| February 24 | 1 | DraftKings | 0 |
| March 17 | 20 | Bovada | 0 |
| April 28 | 29 | FanDuel, DraftKings, MGM | 9 |

The April 28 FanDuel boards contain literal American odds, player names and team assignments. The inspected FanDuel parser selects the displayed **First Basket** market; DraftKings selects **First Field Goal**. The `mgm` parser selects **Which team will score the first points?**, and all ten sampled MGM records are team-only. Those MGM quotes cannot be substituted for the individual-player reference used in the 2025 test.

The clock limitations are concrete:

- `fetchedDatetime` comes from host-local `datetime.now()` during object construction, with no timezone.
- The sampled FanDuel records have `gameDatetime: null`. Current retrieval code reads `tsstart`, but the intermediate builder drops it unless passed through optional fields; the default caller supplies none.
- No bookmaker update clock survives in the sampled objects.
- `gameCode` uses the collection date, and the collector supports both today's and tomorrow's games. A collection-date/team string alone cannot establish the correct fixture.

These records are JSON containing jsonpickle object directives. They were read with `json.loads` only. Do not deserialize the directives or execute the publisher code. Ignore the publisher's model predictions, fitted outputs and Kelly stakes when examining prices.

**Next source work:** determine whether other retained records or pinned source history preserve usable fixture and timezone/update evidence before treating the corpus as a timed price test. A full inventory can quantify literal price coverage, but cannot manufacture the missing clocks. No further copy of the already closed 2025 models should be fitted to rescue their results. Historical BetMGM and FanDuel market terms and additional validation remain necessary for a claimed edge.
