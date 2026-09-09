# FanDuel tennis monitoring source check

Audited September 8, 2026, at 23:51–23:53 UTC. **No usable current source for paired FanDuel ATP Challenger full-match total-games 21.5 quotes was verified.** This is a source-coverage finding, not a tennis model result. No tennis outcomes, model returns, or holdout selection were inspected or changed.

| Public source | Captured response | Finding |
|---|---|---|
| [FanDuel tennis](https://sportsbook.fanduel.com/tennis) | HTTP 403, 23:51:54 UTC; 5,755-byte denial page | PerimeterX access denial; no prices, event times, or status fields available. A separate public-page reader saw only a JavaScript shell. |
| [Oddspedia tennis odds](https://oddspedia.com/us/tennis/odds) | HTTP 403, 23:52:18 UTC; 5,489-byte challenge page | Cloudflare challenge; no current paired FanDuel prices recovered. Search-index labels are not executable quotes. |
| [The Odds Gap full board](https://theoddsgap.com/api/lineshop) | HTTP 200, 23:52:40 UTC; 614 events | Five tennis events, all US Open; five paired FanDuel moneylines, zero FanDuel tennis totals and zero Challenger events in this response. |

The earlier indexed FanDuel [Seville match](https://sportsbook.fanduel.com/tennis/seville-challenger-2026/felix-gill-v-sebastian-ofner-36037190), [Cassis](https://sportsbook.fanduel.com/tennis/cassis-challenger-2026), and [Shanghai](https://sportsbook.fanduel.com/tennis/shanghai-challenger-2026) links remain coverage leads. They do not establish that a full-match 21.5 market exists now. The Seville page returned 403 in this check. Ordinary access denials were accepted; no challenge solving, private API discovery, proxy, geographic override, account creation, or betslip action was attempted.

The Odds Gap's accessible response identifies each event with an internal `id`, `sport`, player names, and UTC `commence_time`. `book_odds.fanduel` has paired American `home_odds`/`away_odds`, rounded implied probabilities, a book label, and selection links containing FanDuel market/selection IDs. The links were not followed. `totals_data.all_books` exposes a total and paired `over_juice`/`under_juice` fields, but all five tennis total pairs belonged to Kalshi. Neither those prices nor moneyline quotes can substitute for the frozen FanDuel 21.5 market.

The board's `last_updated` was `2026-09-08T23:01:28.356579+00:00`, **51.19 minutes before capture**. None of the five tennis objects exposed a bookmaker update timestamp, event status, or market suspension field. The publisher documents hourly free snapshots and The Odds API as its sportsbook source; individual stale sportsbook prices may persist. Execution remains unverified. [Methodology](https://theoddsgap.com/methodology).

The documented endpoint needs no key or signup. Its usage policy permits attributed personal/assistant reading but excludes redistribution, commercial reuse, and sustained high-frequency polling/bulk scraping. This check made one board request and does not establish permission to operate a downstream feed. [The Odds Gap API documentation](https://theoddsgap.com/api-docs).

Evidence is indexed in [the machine-readable audit](../reports/fanduel-tennis-source-audit.json), including exact URLs, response dates, local capture completion times, SHA-256 hashes, schema fields, and counts. Ignored `data/raw/fanduel-tennis-source-audit/` retains the original responses and headers plus a 34,662-byte tennis-only extraction linked to the full response hash. Raw quote data and challenge cookies are not redistributed in tracked files.

**Next step:** keep FanDuel tennis monitoring ineligible. At the next planned source review, check ordinary accessible pages for one Challenger event explicitly offering both sides of full-match total games 21.5. Preserve the event identity, paired prices, exact market/line, capture time, source quote time, and pregame/open status before connecting any observation adapter. Missing fields remain a source failure; the research line, thresholds, and promotion gates stay frozen. A single snapshot cannot establish permanent absence of Challenger coverage.
