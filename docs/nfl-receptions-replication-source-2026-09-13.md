# Card 38 replication price-source check — September 13, 2026

**A new free public archive supplies genuine 2023–24 FanDuel spread boards, with partial timing coverage.** It enabled a separate fixed-period replication without changing Card 38's six-hour window. The [replication result](../reports/nfl-short-receptions-replication-2023-24-2026-09-13.md) is negative; the source discovery does not validate the original positive estimate.

Source: [`bsr-0/nfl-player-projections`](https://github.com/bsr-0/nfl-player-projections/tree/ca05a001e92386484abcb02880e5ae3ecc9800f2), pinned commit `ca05a001e92386484abcb02880e5ae3ecc9800f2`. The public tree has 1,477 HTTP response-body files totaling 101,116,299 bytes, plus metadata. Only the **114 published board files corresponding to unique 2023–24 regular-season fixture dates** were acquired: **16,793,825 bytes**. Every body matches its pinned Git blob hash.

The publisher's [`odds_scraper.py`](https://github.com/bsr-0/nfl-player-projections/blob/ca05a001e92386484abcb02880e5ae3ecc9800f2/src/scrapers/odds_scraper.py) describes one historical board requested at 17:00 UTC per game date. Its public cache naming function hashes the request URL and noncredential parameters. This let us identify the exact published files from the tree; we made no provider API request, used no API key and executed none of the publisher's collector code. The returned archive snapshot is typically around 16:55 UTC, not the requested 17:00.

The actual response schema supplies archive `timestamp`, `previous_timestamp`, `next_timestamp`; event `id`, `sport_key`, `commence_time`, team names; literal `fanduel` / `FanDuel`; bookmaker and market `last_update`; market key `spreads`; and two outcome names, American prices and opposite line values. These fields support independent fixture matching and age checks. They do not supply an accepted stake, original collector receipt time or market suspension state.

| Source-only coverage, before prop freshness, role or underdog gates | 2023 | 2024 |
| --- | ---: | ---: |
| Existing mapped reception price pairs | 2,005 | 2,175 |
| Pairs with an earlier eligible spread board within six hours | 720 | 813 |
| Games represented by those timing matches | 90 | 82 |
| Valid spread board/event pairs, including repeated pregame boards | 1,313 | 1,340 |

Thus 172 of 544 regular-season fixtures have at least one existing reception pair with usable spread timing in this input. The same board is too late for early Sunday props and often more than six hours too early for post-daylight-saving primetime props. For example, the September 11, 2023 board matches that evening's reception prices about 345 minutes earlier; the November 18, 2024 board fails the same six-hour requirement. No time cutoff was widened and no later board or closing line filled the gaps.

The [114-file selection](../reports/nfl-receptions-replication-board-selection-2026-09-13.json) has SHA-256 `5f8160289fd04a8fe8b0ebde1841724b409c6f7278c9e4aa403c21742adf5f1e`. The ignored acquired manifest has SHA-256 `5c7c7c4c54ec7c2854aed4d0ea1f3ceb2f10c1a2768e9eb54053e73a1d6098bc`; it records local acquisition times and body SHA-256 hashes separately from historic archive clocks. The [source-only timing audit](../reports/nfl-receptions-replication-source-audit-2026-09-13.json) contains measured counts. Run `python tools/acquire_nfl_replication_spreads.py` to recover missing pinned boards; existing files are verified and reused. The adapter is in [replicate_nfl_short_receptions.py](../tools/replicate_nfl_short_receptions.py).

No explicit license was present in the inspected tree; original response bodies remain ignored. A second new candidate, [`MJACode/betting-model`](https://github.com/MJACode/betting-model/tree/60102a1fd6534ac0d7d6a41260282c81bdef52db), has a large raw NFL odds cache, but its inspected October 28, 2024 example is ten minutes before kickoff and therefore later than the same game's reception entry. It was not used or bulk-acquired. The receptions publisher's pinned tree has no original context-response archive and no releases; its processed guessed spreads remain excluded.

**Continuation:** the fixed BSR source subset has now been acquired and tested. Deprioritize Card 38 and test another hypothesis next. Do not repeat this search, add seasons or boards, or widen its timing/role rules to rescue the result. The precisely recorded source gap is earlier same-day paired spreads for early Sunday entries and appropriately timed primetime boards, with original book/market clocks and fixture identity. That gap does not reverse the negative 26-game replication.
