# Golf birdie source audit — September 26, 2026

**The September 23 report does not establish an executable golf edge.** Its exchange attribution conflicts with the publisher's Hard Rock attribution; its near-zero-margin closing columns have unresolved provenance; and the number of stored Under contracts is smaller than its claimed 863 bets. These are source findings, not a fresh performance backtest.

Audit input: the locally retained [odds.csv](../data/raw/golf-historical-price-search-2026-09-19/alpha/data/odds.csv), retrieved September 19 from publisher commit `5508f6f35830f09d0b1e0c06abed0b2b489dde04`. The saved metadata records SHA-256 `d2a9b733b9d0f45d20cf8593056ef343cd6c6bb7e07b4aae29b4ac9ad2a52e97`, Git blob `104ab16b9657800309f45d8e102132b835e70459`, and 1,854,042 bytes. The CSV has 9,397 rows, including 4,381 birdie rows. The relevant 2023–2025 subset is all 3,230 `GOLF:FT:CTBIR` rows; the remaining 1,151 birdie rows are 2026 `GOLF:FT:ROUNDNUMBIRDIES`.

## Book and timestamp provenance

The publisher's [shared parser](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/alpha-caddie-web/scripts/odds-csv-props.mjs) and [pre-round loader](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/alpha-caddie-web/scripts/hr-pre-round-props-from-odds-csv.mjs) both identify this as **Hard Rock**. That attribution was already documented in the repository's [September 19 source audit](golf-historical-price-audit-2026-09-19.md). It is publisher evidence, not independent bookmaker authentication. The CSV itself contains no book name; numeric instrument/channel IDs do not establish an exchange.

There is **no quote timestamp**. `EVENT_START_TIME_UTC` is the listed event/group tee time. The shared parser assigns it to `bet_time_ms`; the loader then assigns that value to both `capturedMs` and `openCapturedMs`. Those names do not make it a collection timestamp. The later GitHub download time establishes file retrieval only. Opening/closing chronology, prestart status, and simultaneous availability cannot be verified from this file.

## Price columns and missing sides

For all 3,230 pre-2026 birdie rows, closing American odds match conversion of `CLOSING_IMPLIED_PROB`, rounded to one American-odds point, allowing 0.501 for six-decimal probability rounding and treating +100/-100 as equivalent. They do **not** all equal conversion of the opening probability: 986 rows show changed probabilities. In the other 2,244 rows, opening and closing probabilities are identical and the declared movement is zero. Nevertheless, 2,992 of all 3,230 rows have better payouts at the alleged close than at the open.

Grouping by raw competition, sport event/group, market type, market name, and numeric line gives:

| 2023–2025 source inventory | Count |
| --- | ---: |
| Raw birdie rows | 3,230 |
| Unique instrument IDs | 1,583 |
| Distinct raw line keys | 1,082 |
| Keys with both sides stored | 501 |
| Over-only keys | 411 |
| Under-only keys | 170 |
| Keys with an actual stored Under | **671** |
| Integer-line keys | 314 |

Across the 501 pairs, opening overround averages **7.8679%**, closing overround **0.1908%**; 423 pairs have exactly complementary closing probabilities to numerical precision. The mean absolute difference between opening American odds' implied probability and `OPENING_IMPLIED_PROB` is **3.9060 percentage points**. Thus even the field called opening implied probability is not the ordinary implied probability of its opening American price.

These arithmetic patterns strongly suggest probabilities/closing values have been adjusted or represent a different pricing object. **They do not prove the exact transformation**, and the inspected publisher readers provide no export schema or generating pipeline that establishes executable closing prices. Ordinary proportional, additive, and power removal of margin from paired opening prices do not reproduce all stored probabilities. Treat closing-price ROI and apparent closing value as unverified; recompute descriptive returns separately at the stored opening American prices.

The pre-round loader also fabricates a missing counterpart at **-110**. That fallback must never count as an observed bet. The 671 stored-Under bound precedes outcome matching, which can only reduce it under this key definition; the September 23 claim of 863 distinct Under bets requires explicit reconciliation. Do not infer an available Under merely from an Over quote or invert a fair probability into an executable opposite price.

## Duplication, settlement, and selection

There are no exact duplicate whole rows, but many repeats of the same instrument/contract across channels or `AMERICAN_ODDS_AT_PERIOD`. Within the pre-2026 raw line/side keys, opening and closing prices never conflict. Deduplicate contracts before grading; channels and intermediate rows are not independent bets. Multiple lines or players in one tournament remain dependent even after deduplication.

The historical label is plain `Total Birdies`; the 2026 type explicitly says birdies or better. Both the [publisher backtest](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/alpha-caddie-web/scripts/backtest-odds-csv.mjs) and [stat helper](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/alpha-caddie-web/scripts/round-projection-mu.mjs) grade birdies plus eagles-or-better, falling back to eagles. This is evidence of publisher intent, **not proof of the historical Hard Rock contract**. Current [Hard Rock Florida rules](https://www.hardrock.bet/fl/house-rules/), loaded from the official page's embedded [rules document](https://docs.google.com/document/d/1LohHmj-8bnU9wnJO8yMsi6Ttvee_EZf3RWg4bfUul7s/edit), do not define this birdie-count contract. An applicable historical rule/market receipt was not recovered. Report both grading definitions as sensitivities until resolved. Integer lines require pushes; incomplete rounds and withdrawals need contract-specific treatment. Missing statistics must not become zero birdies.

The file's collection/selection process is undocumented, covers 70 pre-2026 competition labels unevenly, includes non-PGA events, and includes generic competition labels such as `PGA Tour 2024`. The first-initial/surname and fuzzy-event joins in publisher code are not sufficient identity verification. Preserve ambiguous and unmatched cases in an exclusion ledger. A reported count of 97,609 historical rounds does not establish coverage of the chosen betting contracts.

The direction, trailing-window rule, and threshold were selected after looking across many routes and buckets. A nominal t-statistic around 2.4 and same-sign annual results are exploratory; repeated golfers and shared course/weather conditions further weaken an independent-bet standard error. Retrospective threshold selection cannot demonstrate better out-of-sample forecasting.

## Disposition

**Fatal to the existing claim:** unknown executable closing-price semantics; no quote times; potentially invented opposite sides; unresolved grading; no untouched forecast evaluation. The source can support a diagnostic recheck, not the assertion that the same rule applies to another book.

**Resolvable work:** deduplicate and retain only stored sides; calculate opening-price returns with push/void accounting; grade both birdie definitions; audit identity joins and exclusions; obtain the exporter/schema and historical Hard Rock rules. Any surviving forecasting hypothesis needs a frozen rule evaluated on later, genuinely timestamped prices and outcomes, with the exact settlement contract and a market-probability baseline. Publisher backtest summaries should not substitute for that test.
