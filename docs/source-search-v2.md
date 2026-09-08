# Additional FanDuel history audit — September 8, 2026

This audit inspected downloadable odds and timestamp coverage only. It did not load game results, fit a model, or calculate betting returns. It extends [the earlier investigation](odds-source-investigation.md); it does not reverse any failed experiment or make a profitability claim.

## Ranked usable leads

| Rank | Source | Observed coverage | Appropriate use |
|---|---|---|---|
| 1 | [NFL Market Tracker v1.1.1](https://github.com/bobby-king3/nfl-market-movement-tracker/releases/tag/v1.1.1) | Full downloaded database: 1,856,036 raw rows, 286 event IDs, 634 capture timestamps; 285 FanDuel moneyline events | Fresh sport-specific chronological experiment with literal archive and book-update timestamps |
| 2 | [The Odds Gap research CSV](https://theoddsgap.com/data) | Downloaded MLB moneyline export: 67,902 rows, 3,870 FanDuel rows, September 1–8, 2026 | Short independent period and historical CLV pilot, with unresolved quote freshness |
| 3 | [SharpAPI sample](https://github.com/Sharp-API/SharpAPI-Sample-Data) | Downloaded MLB file: 3,673 rows, 1,370 FanDuel rows, one capture on July 13, 2026 | Schema/reference example only; predominantly futures, insufficient independent games |

## 1. NFL Market Tracker: strongest newly recovered archive

The [downloadable DuckDB release](https://github.com/bobby-king3/nfl-market-movement-tracker/releases/download/v1.1.1/nfl_odds.duckdb) is 137,375,744 bytes and has SHA-256 `b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c`. GitHub reports publication on February 24, 2026; its release note records removal of one bad Week 5 game. The inspected copy is `/tmp/beating-nfl-odds.duckdb`. No account or payment was needed. The public repository has no data license visible in its root, so the raw database has not been republished in this repository.

The actual `raw_odds` schema is `captured_at`, `event_id`, `sport_key`, `commence_time`, `home_team`, `away_team`, `bookmaker_key`, `bookmaker_title`, `bookmaker_last_update`, `market_key`, `outcome_name`, `outcome_price`, `outcome_point`, `loaded_at`. Thirty-eight bookmaker keys are present. Captures span September 4, 2025–February 9, 2026; load times are February 15–20, 2026. This is a retrospective download of The Odds API's historical snapshots, not evidence that the GitHub author personally collected the prices live. The [extraction code](https://github.com/bobby-king3/nfl-market-movement-tracker/blob/main/extract/historical_extract.py) requests four UTC times per day; the returned API snapshot times are slightly earlier.

Measured FanDuel coverage:

| Market | Raw rows | Event IDs | Rows before each event's earliest recorded start |
|---|---:|---:|---:|
| Moneyline (`h2h`) | 23,754 | 285 | 23,324 |
| Spread | 23,756 | 285 | 23,324 |
| Total | 23,780 | 286 | 23,354 |

After each row's own pre-start filter, all 35,028 FanDuel event/capture/market groups have exactly two sides. FanDuel bookmaker timestamps are never missing or later than capture; their measured age is median 18 seconds, 90th percentile 43 seconds, 99th percentile 92 seconds, maximum 334 seconds. The raw table contains 28 duplicate rows across all books. Do not use downstream summary tables as the source of truth: their closing definitions and rounding need independent reconstruction. Also, the stored `stg_odds` view refers to the original database catalog name `nfl_odds` and fails if the file is opened under another name; `raw_odds` is readable directly.

The archive is not a tick-level close series. After conservatively requiring capture before the earliest recorded start, only 91 of 285 FanDuel moneyline events have a last capture within 30 minutes of that start; median lead is 129.37 minutes and maximum lead 1,205.35 minutes. Start times change for 276 of all 286 event IDs. Row-level pre-start checks alone therefore do not establish chronology across versions; join an independent fixture/start source and reject ambiguous cases. The [raw JSON sample](https://github.com/bobby-king3/nfl-market-movement-tracker/blob/main/data/samples/sample_nfl_week1_data.json) explicitly contains in-play rows, so using every row would contaminate a pregame backtest. There are 1,234 FanDuel rows at or after their own reported starts.

The bad Week 5 game remains in the raw table: event `49e177e39ff23cd0596bae127b04df43`, Los Angeles Rams versus Washington Commanders, October 5, 2025 at 20:26 UTC, with FanDuel totals only. The derived `fct_line_movements` table has 285 distinct events. Thus the release's removal is a transformation, not raw-data deletion. Moneyline coverage is unaffected by this particular extra event, but the independent fixture audit remains necessary.

**Recommendation:** freeze one NFL moneyline experiment before outcomes are acquired. Use contemporaneous paired prices and bookmaker timestamps, a fixed forecast cutoff, a simple leave-FanDuel-out reference, and a small predefined set of football features with defensible information times. Preserve an untouched chronological test and cluster uncertainty by game/week. Report the last sampled pregame quote as such, with its lead time; do not call every such quote a closing price. This source improves timestamp quality and sport independence but supplies only one season, so the number of independent games remains modest.

## 2. The Odds Gap: fresh MLB history with publisher capture times

The request was [MLB moneyline CSV](https://theoddsgap.com/api/odds-export.csv?sport=baseball_mlb&market=ml), downloaded September 8, 2026 at 23:10:42 UTC. The HTTP response was 200, `X-Access-Tier: free`, `X-Window-Max-Days: 7`, `X-Window-Clamped: 0`, and a 250,000-source-row cap. The file is `/tmp/beating-oddsgap-mlb.csv`, SHA-256 `3f433cc28f0a2789dc2dff59f46718ee385181ca9e6fc5e460706fa93585a14e`; headers are `/tmp/beating-oddsgap-headers.txt`.

The schema is `snapshot_ts`, `sport`, `away`, `home`, `commence_time`, `market`, `side`, `line`, `book`, `american_odds`, `devig_fair_prob`, `best_price_flag`. There is **no event ID, bookmaker update time, market update time, stake limit, accepted wager, or live-status field**. Derive probabilities from paired American odds; do not treat the supplied fair probability or best-price flag as ground truth.

Measured checks on this exact export:

| Check | Result |
|---|---:|
| All-book rows / distinct scan timestamps | 67,902 / 193 |
| FanDuel rows / paired scan-event observations | 3,870 / 1,935 |
| FanDuel pair groups with exactly home and away | 1,935 of 1,935 |
| Exact duplicate rows / FanDuel rows at or after their reported start | 0 / 0 |
| FanDuel rows with invalid American odds | 0 |
| FanDuel pairs with a Pinnacle row at the identical scan/event key | 1,411 |
| Sequential FanDuel paired prices unchanged | 1,529 of 1,797 (85.09%) |
| Median / maximum span of an unchanged FanDuel price run | 2.00 / 29.12 hours |
| All-book scan interval, median / maximum | 47.98 / 478.24 minutes |

Rows are ordered chronologically. FanDuel capture times run from `2026-09-01T23:28:34.288391+00:00` to `2026-09-08T23:03:02.721443+00:00`. For example, a paired Philadelphia-at-Arizona row at the first capture has home +114, away −134, and reported start `2026-09-02T01:41:00Z`.

The nominal 138 distinct team/start combinations are **not** 138 independent games. Grouping teams by Eastern date gives 115 identities, of which 14 have multiple reported start times. These include minute changes and long delays; Eastern-date grouping still needs official doubleheader/reschedule resolution. Last-scan lead times and CLV counts computed before this reconciliation would be overstated.

The publisher's [methodology](https://theoddsgap.com/methodology) identifies The Odds API as its sportsbook source. Its [about page](https://theoddsgap.com/about) describes a self-funded one-person operation, The Odds Gap LLC. The research export is described as stored scan rows, without smoothing or backfilling. The observed schema, price variation, scan gaps, and changing schedule times are consistent with that description. **This inspection cannot independently prove the historical captures were immutable, that every upstream price was current, or that quotes were executable.** In particular, unchanged prices may be valid unchanged markets or cached stale feed data; the CSV lacks the upstream timestamps needed to tell. No public collector implementation or independently timestamped raw archive was recovered.

The export documentation allows attributed research/modeling, offers seven days without signup and a longer free beta window requiring an email, and prohibits sustained bulk scraping and repackaging/resale. The [API usage page](https://theoddsgap.com/api-docs) has additional restrictions on feed/product reuse. This audit made a single research CSV request and created no account. Attribute The Odds Gap and keep raw data out of a redistributed feed. It can support a one-off research pilot; it should not silently become the automated betting-alert data source.

**Recommendation:** use the 2026 week as a separate frozen replication/paper experiment, with independent event matching and an explicit publisher-capture-only label. It cannot by itself meet a fresh-book-quote or executable-bet gate. The absence of last-update fields materially weakens a stale-line strategy and should be reflected in eligibility, not hidden in a footnote after a profitable result.

## 3. SharpAPI sample: inspectable but not a backtest cohort

The [MLB CSV](https://raw.githubusercontent.com/Sharp-API/SharpAPI-Sample-Data/main/data/mlb_odds_snapshot.csv) has SHA-256 `3fe2bcb54448816d22154a394dc9e86a02e31931e08d543127288c1bed9788f9`. It contains `sportsbook`, event/market/selection IDs, American/decimal prices, scheduled start, `is_live`, and capture timestamp. All 1,370 FanDuel rows share `2026-07-13T01:45:58.346411002Z`; only four distinct FanDuel participant/start combinations occur and most rows price award/futures boards. Sixteen FanDuel rows have scheduled times before capture despite `is_live=False`, illustrating why that boolean alone is insufficient. The publisher licenses the sample CC BY 4.0, but a single futures-heavy snapshot provides neither an adequate event sample nor earlier/closing pairs.
