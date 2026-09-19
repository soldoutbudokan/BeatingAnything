# Additional first-basket source check

The pinned [vishaalram02/odds repository](https://github.com/vishaalram02/odds/tree/756e4f02344422f192694a11a0122932343a48ef) adds a small price-movement sample, not a verified additional research cohort. [Capture hashes and measured counts](nba-first-basket-additional-source-2026-09-19.json) preserve the evidence.

| File | FanDuel games | Snapshots | Price rows | Timing evidence |
| --- | ---: | ---: | ---: | --- |
| `data/first_basket.json` | 7 | 159 | 1,567 | January 31, 2025 market updates retain `Z`; no collection timestamp. 136 ten-runner and 23 nine-runner boards. |
| `data/first_basket_2.json` | 10 | 10 | 100 | February 2025 integer clocks; no collection timestamp or explicit market key. Host timezone unverified. |

Sixteen of the 17 game event IDs already occur in the earlier FanDuel price inventory; eight are in the now-inspected forecast cohort. The first file retains the literal `player_first_basket` key and `Yes` outcome label. Current collector code produces a different schema; its UTC-looking string parser creates naive datetimes before Unix conversion. Do not silently assume that proves the second file's clock semantics.

The published frontend points to a public Modal historical-data endpoint. One ordinary request for February 3, 2025 returned **404, invalid function call**; the failed body/receipt were retained and it was not retried. No publisher code, embedded credential, notification function or schedule was executed.

A bounded follow-up checked three more repository trees. `vanessagyapong/first-basket` is a grocery website. `ijl7/First-Basket-Sim` contains season game CSVs and simulation summaries; no named price archive was identified. `quigs-barstool/GamblingModel` contains a 1,566-row first-shot cache with game/team/shot/time/count fields, not bookmaker odds. Their pinned tree captures and inspected source headers are retained under ignored `data/raw/first-basket-next-sources-2026-09-19/`. A public JediBets tracker exposes later-season outcomes/statistics, but the pages inspected did not establish a historical, timestamped FanDuel price archive; its predictions were not used. Some 2025–26 aggregate statistics and example outcomes were visible during that source check, so do not represent the entire season as independently untouched.

The Odds API [documents historical player-prop endpoints](https://the-odds-api.com/liveapi/guides/v4/) and lists `player_first_basket` in its [market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html). Paid historical access is a possible acquisition route, not proof that a particular requested book/date/market is populated. No configured odds credential or workspace `.env` was found. An optional question about existing access/export is pending; no subscription or purchase was made.
