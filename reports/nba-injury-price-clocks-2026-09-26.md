# NBA injury-report / price-clock inventory

The fixed three-event sample was checked in declared URL order. Report selection stopped at the first clock-qualified PDF, before using its statuses or fixture content. This is source feasibility, not a star-absence test or forecast.

| Month | Publisher fixture (away at home) | Preliminary pairs | Requests | Report clock gate | Fixture/status result |
|---|---|---:|---:|---|---|
| 2025-10 | Golden State Warriors at Los Angeles Lakers | 13 | 1 | transport_failure_stop | not inspected; no clock-qualified PDF |
| 2026-01 | Houston Rockets at Brooklyn Nets | 10 | 1 | transport_failure_stop | not inspected; no clock-qualified PDF |
| 2026-04 | Philadelphia 76ers at Washington Wizards | 12 | 1 | transport_failure_stop | not inspected; no clock-qualified PDF |

## 2025-10

Entry: `2025-10-21T13:55:39Z`. Provider start retained as `2025-10-22T02:00:00Z`.
- [Injury-Report_2025-10-21_08_00AM.pdf](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2025-10-21_08_00AM.pdf): HTTP 0; new receipt; event stopped or filename missing.

## 2026-01

Entry: `2026-01-01T11:05:37Z`. Provider start retained as `2026-01-01T23:10:00Z`.
- [Injury-Report_2026-01-01_04_30AM.pdf](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_04_30AM.pdf): HTTP 0; new receipt; event stopped or filename missing.

## 2026-04

Entry: `2026-04-01T11:05:38Z`. Provider start retained as `2026-04-01T23:10:00Z`.
- [Injury-Report_2026-04-01_05_30AM.pdf](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-04-01_05_30AM.pdf): HTTP 0; new receipt; event stopped or filename missing.

## Limits

- Three predetermined monthly samples do not establish whole-season availability or a qualified star-absence cohort.
- Report header timezone is corroborated from offset-bearing CreationDate; Game Time (ET) alone is not publication-time evidence. The header minute’s upper endpoint is included conservatively in the clock maximum.
- CreationDate is generation, not last revision. All interpretable modification/XMP/HTTP Last-Modified clocks are retained and maximized; a later clock cannot be discarded. Current source assertions are not original contemporaneous receipts or proof of immutable wording.
- A 403, other denial, server/transport failure or non-PDF response stops that event; failed events are not rescued by alternate hosts or expanded searches.
- Publisher NBA IDs and provider starts remain preliminary. Printed ordered matchup/date is reported separately and does not independently certify the NBA ID crosswalk. A printed time without AM/PM remains ambiguous; both UTC candidates are retained.
- Status extraction uses PDFium visual-order text and retains raw lines plus rendered pages. An unlisted player is unknown, not healthy. Player name/ID and contemporaneous target-team membership joins have not been established.
- No player scoring/minute values, star classifications, sporting outcomes, forecasts, selections, returns or threshold changes are included.

The [JSON audit](nba-injury-price-clocks-2026-09-26.json) retains every preliminary pair, original quote clocks, candidate URL order, receipts, clock components, literal fixture rows and source hashes. No box score or performance file was read.
