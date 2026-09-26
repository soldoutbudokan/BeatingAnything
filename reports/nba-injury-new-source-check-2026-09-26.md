# New NBA injury-report source: two bounded samples

**Official 2025–26 timestamped injury PDFs are recoverable.** Exactly two web queries and two distinct direct NBA PDF samples were checked. Both returned HTTP 200 with `application/pdf`; no season download, quote join, outcome extraction, forecast, effect calculation or card change followed.

| Official sample | Printed report time | PDF creation time | HTTP Last-Modified | Size / pages |
|---|---|---|---|---|
| [October 25, 2025](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2025-10-25_12PM.pdf) | 12:30 PM | 12:30:03 −04:00 | 16:30:05 UTC | 67,869 bytes / 3 |
| [February 5, 2026](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-02-05_10_30AM.pdf) | 10:30 AM | 10:30:08 −05:00 | 15:30:10 UTC | 76,466 bytes / 6 |

Both sampled first pages contain the expected Game Date, Game Time, Matchup, Team, Player Name, Current Status and Reason columns, including literal `Out` statuses. Game times are labeled ET. This establishes a concrete newer-season status source; it does not establish which reports or Out statuses predate any retained quote.

The [existing script](../tools/explore_nba_props_edges.py) pins `akng8/nba-injury-scraper@02cfe44f7453182eb4a29283285a7af64f5e3c9a`. Its parser at line 133 recognizes hourly names such as `_12PM.pdf` and does not recognize the February `_10_30AM.pdf` format. The October sample also contains a **12:30 PM header despite a `_12PM` filename**. A filename-only clock is therefore 30 minutes early for this sample and does not satisfy a nominal one-hour-before-entry rule without checking the actual printed/metadata time. No old script or result was changed.

Current filename inventory found no retained NBA injury payloads in this checkout. The new bytes, response headers and metadata receipts are now preserved in [the new raw directory](../data/raw/nba-injury-new-source-check-2026-09-26/), with exact URLs, queries and hashes in the [JSON audit](nba-injury-new-source-check-2026-09-26.json). The October PDF SHA-256 is `d45934e94ac012104ecd685345017cb8da439828d88e8ffbd0849acb7aa2cdea`; February is `2245d9bb54b3b94d8644831fe4afdbceceef276b009e0caf2ebc05de315f915e`.

These are retrospective downloads. Printed dates, PDF creation times and HTTP Last-Modified are source assertions, not independently preserved original receipts. Two available reports do not establish whole-season coverage, revision immutability or adequate pre-snapshot sample size. `Out` also includes reasons beyond injury, so status and reason require their eventual declared treatment. A third-party search result claimed all 2026 PDFs were unavailable; the February sample disproves that blanket claim, without proving complete 2026 coverage.
