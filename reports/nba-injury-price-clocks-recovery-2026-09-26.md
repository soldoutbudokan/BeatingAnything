# NBA injury-report / price-clock inventory

**Two source matches succeed: January and April supply 22 actual paired prices with fixture-specific official reports about 95 minutes earlier.** The October request returned HTTP 403 and stopped, without trying other filenames. The initial three DNS failures and this separately declared recovery remain distinct; a DNS error was not an HTTP response or evidence of missing PDFs.

The subsequent [independent fixture audit](nba-injury-price-clock-fixture-audit-2026-09-26.json) restores the already-pinned ESPN 2026 schedule using metadata only. It uniquely matches all three fixtures and resolves the two printed AM/PM ambiguities described below: both starts are 23:00 UTC. January and April entries precede those independent starts by 11.91 hours. Provider starts at 23:10 are preserved separately. These are scheduled starts, not actual-tip or historical release receipts; the publisher NBA-ID crosswalk and player IDs remain preliminary.

Root visually reviewed January page 1 and April pages 1–2: report headers, dates, ordered matchups and all extracted status rows agree, including Washington's continuation onto page 2. Neither these checks nor the source matches establish an eligible absent star, a forecast or a betting edge.

The [independent recovery audit](nba-injury-price-clocks-recovery-audit-2026-09-26.json) verifies 26 reference hashes, all six first-pass/recovery receipts, all 35 unchanged price pairs, and the report clocks from all 12 PDF page headers. Its printed-time ambiguity observation describes the frozen recovery output; the separate schedule audit above supplies the subsequent resolution. The publisher NBA-ID crosswalk remains unverified.

The fixed three-event sample was checked in declared URL order. Report selection stopped at the first clock-qualified PDF, before using its statuses or fixture content. This is source feasibility, not a star-absence test or forecast.

| Month | Publisher fixture (away at home) | Preliminary pairs | Requests | Report clock gate | Fixture/status result |
|---|---|---:|---:|---|---|
| 2025-10 | Golden State Warriors at Los Angeles Lakers | 13 | 1 | access_denial_or_server_response_stop | not inspected; no clock-qualified PDF |
| 2026-01 | Houston Rockets at Brooklyn Nets | 10 | 1 | first_clock_qualified_pdf | both_teams_have_submitted_status_rows |
| 2026-04 | Philadelphia 76ers at Washington Wizards | 12 | 1 | first_clock_qualified_pdf | both_teams_have_submitted_status_rows |

## 2025-10

Entry: `2025-10-21T13:55:39Z`. Provider start retained as `2025-10-22T02:00:00Z`.
- [Injury-Report_2025-10-21_08_00AM.pdf](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2025-10-21_08_00AM.pdf): HTTP 403; new receipt; event stopped on the denied request. No missing-file conclusion follows.

## 2026-01

Entry: `2026-01-01T11:05:37Z`. Provider start retained as `2026-01-01T23:10:00Z`.
- [Injury-Report_2026-01-01_04_30AM.pdf](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_04_30AM.pdf): HTTP 200; new receipt; clock qualified.

Available-after bound: `2026-01-01T09:30:59.999999Z`; 94.616667 minutes before entry.

Printed Game Time (ET): 06:00. UTC candidates: 2026-01-01T11:00:00Z, 2026-01-01T23:00:00Z.

Independent printed-start status: `unresolved_printed_AM_PM`. Snapshot before provider and the earliest printed candidate: `False`. No provider-assisted PM choice is called independent.

- Houston Rockets: Adams, Steven — Questionable; Capela, Clint — Questionable; Crawford, Isaiah — Out; Eason, Tari — Questionable; Sengun, Alperen — Questionable; Smith, Tyler — Out; VanVleet, Fred — Out.
- Brooklyn Nets: Demin, Egor — Out; Etienne, Tyson — Out; Highsmith, Haywood — Out; Johnson, Chaney — Out; Liddell, E.J. — Out; Mann, Terance — Questionable; Porter Jr., Michael — Questionable; Saraf, Ben — Out.

Rendered pages: [page 1](../data/raw/nba-injury-price-clocks-recovery-2026-09-26/rendered/2026-01-page-1.png).

## 2026-04

Entry: `2026-04-01T11:05:38Z`. Provider start retained as `2026-04-01T23:10:00Z`.
- [Injury-Report_2026-04-01_05_30AM.pdf](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-04-01_05_30AM.pdf): HTTP 200; new receipt; clock qualified.

Available-after bound: `2026-04-01T09:30:59.999999Z`; 94.633333 minutes before entry.

Printed Game Time (ET): 07:00. UTC candidates: 2026-04-01T11:00:00Z, 2026-04-01T23:00:00Z.

Independent printed-start status: `unresolved_printed_AM_PM`. Snapshot before provider and the earliest printed candidate: `False`. No provider-assisted PM choice is called independent.

- Philadelphia 76ers: Broome, Johni — Out; Maxey, Tyrese — Available.
- Washington Wizards: Black, Leaky — Questionable; Coulibaly, Bilal — Questionable; Davis, Anthony — Out; George, Kyshawn — Out; Johnson, Tre — Questionable; Reese, Julian — Out; Russell, D'Angelo — Out; Sarr, Alex — Questionable; Whitmore, Cam — Out; Young, Trae — Out.

Rendered pages: [page 1](../data/raw/nba-injury-price-clocks-recovery-2026-09-26/rendered/2026-04-page-1.png), [page 2](../data/raw/nba-injury-price-clocks-recovery-2026-09-26/rendered/2026-04-page-2.png).

## Limits

- Three predetermined monthly samples do not establish whole-season availability or a qualified star-absence cohort.
- Report header timezone is corroborated from offset-bearing CreationDate; Game Time (ET) alone is not publication-time evidence. The header minute’s upper endpoint is included conservatively in the clock maximum.
- CreationDate is generation, not last revision. All interpretable modification/XMP/HTTP Last-Modified clocks are retained and maximized; a later clock cannot be discarded. Current source assertions are not original contemporaneous receipts or proof of immutable wording.
- A 403, other denial, server/transport failure or non-PDF response stops that event; failed events are not rescued by alternate hosts or expanded searches.
- Publisher NBA IDs and provider starts remain preliminary. Printed ordered matchup/date is reported separately and does not independently certify the NBA ID crosswalk. A printed time without AM/PM remains ambiguous; both UTC candidates are retained.
- Status extraction uses PDFium visual-order text and retains raw lines plus rendered pages. An unlisted player is unknown, not healthy. Player name/ID and contemporaneous target-team membership joins have not been established.
- No player scoring/minute values, star classifications, sporting outcomes, forecasts, selections, returns or threshold changes are included.

The [JSON audit](nba-injury-price-clocks-recovery-2026-09-26.json) retains every preliminary pair, original quote clocks, candidate URL order, receipts, clock components, literal fixture rows and source hashes. No box score or performance file was read.

This is the separately declared transport recovery after three DNS failures. The [original attempt](nba-injury-price-clocks-2026-09-26.md) is preserved.
