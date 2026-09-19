# Historical golf prices recovered — September 19, 2026

**Later identity follow-up:** [public player profiles](golf-price-identity-followup-2026-09-19.md) resolve all 28 unmatched rows below as same-course. The final classification is 311 same-course, seven outside the declared pair and zero cross-course. The original name-only audit is preserved here.

**Found: 18,568 distinct FanDuel-labelled historical price records for 2022–26. G11 still has zero verified cross-course offers.** This supersedes the earlier blanket absence of a free historical price file. It does not establish a usable G11 backtest or an edge.

## Source and coverage

The public [alpha-caddie repository](https://github.com/jriordan55/alpha-caddie/tree/5508f6f35830f09d0b1e0c06abed0b2b489dde04) contains two matchup exports. Both were downloaded at that exact commit and verified against its complete Git tree by byte size, Git blob hash and SHA-256. Publisher files remain in ignored `data/raw/golf-historical-price-search-2026-09-19/`; the repository declares no license.

| Export | All books | FanDuel | Round matchups | 3-balls |
| --- | ---: | ---: | ---: | ---: |
| `alpha-caddie-web/data/matchup_backtest_detail.csv` | 43,381 | 15,990 | 8,438 | 7,552 |
| `tracker-pages-test/data/matchup_backtest_detail.csv` | 50,733 | 18,568 | 10,040 | 8,528 |

The smaller file's FanDuel price records are an exact subset of the larger file, ignoring publisher model estimates, picks, results and export time. Neither contains duplicate price records under this comparison. The union is 18,568, not the sum. FanDuel annual counts in the union: 2022 **2,537**, 2023 **3,155**, 2024 **5,360**, 2025 **4,668**, 2026 **2,848**.

The publisher's [collector](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/historical_odds.R) identifies DataGolf's historical matchup API as its source. That [API documents opening/closing lines and outcomes](https://datagolf.com/api-access). The recovered records have a `fanduel` book label, DataGolf player IDs, event name/year, round, decimal opening/closing odds for each listed player, and unzoned opening/closing timestamp strings. They are third-party exports, not independently recovered original FanDuel or DataGolf responses.

## Fixed G11 cohort

The [existing declaration](golf-rotation-declaration-2026-09-14.md) fixes eight editions, first rounds and named course pairs. The new audit reads the original retained PGA TOUR compressed tee responses, verifies their capture hashes, and joins unique full names within each event. It reverses DataGolf's explicit `surname, given name` notation, then normalizes case, accents and punctuation. No nickname substitution, initials expansion or fuzzy matching is used.

| Edition | Round matchups | 3-balls | Same course | Unresolved names | Outside declared pair | Verified cross-course |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Farmers 2023 | 0 | 19 | 18 | 1 | 0 | 0 |
| Farmers 2024 | 9 | 28 | 30 | 7 | 0 | 0 |
| Farmers 2025 | 10 | 28 | 34 | 4 | 0 | 0 |
| Pebble 2023 | 28 | 0 | 20 | 1 | 7 | 0 |
| Pebble 2024 | 51 | 0 | 47 | 4 | 0 | 0 |
| Pebble 2025 | 54 | 0 | 49 | 5 | 0 | 0 |
| RSM 2024 | 7 | 35 | 37 | 5 | 0 | 0 |
| RSM 2025 | 10 | 39 | 48 | 1 | 0 | 0 |
| **Total** | **169** | **149** | **283** | **28** | **7** | **0** |

The two exports have the same fixed-cohort price rows. The seven outside-pair rows include Monterey Peninsula, excluded in the original declaration. Unknown names remain unresolved; the detailed local inventory records each partial join and exclusion. A common course offset cancels within a same-course matchup, so the 283 matched offers cannot test G11's proposed error.

As an independent limited check, a [January 21, 2025 BettingPros article](https://widgets.bettingpros.com/articles/2025-farmers-insurance-open-golf-odds-picks-head-to-head-matchups/) explicitly attributes McNealy's R1 price versus Bradley to FanDuel at +100. The export's opening decimal price is 2.00. Both players' official assignments are on the North course. This supports one quoted selection, not the completeness, clocks or terms of the archive.

## Limitations that matter for a backtest

- The [exporter](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/alpha-caddie-web/scripts/export-matchup-backtest-csv.mjs) retains graded outcomes and players for whom its model produces estimates. It also supports date/row/market filters and merges older exports. This is a selected sample, not a complete market catalog. Missing cross-course offers here do not prove FanDuel never offered them.
- Every retained opening/closing clock lacks a timezone. The exporter can fill absent `close_time` with `open_time`. Its `exported_at` is file-generation time, not an original quote or availability clock. No timezone or pre-start eligibility has been invented.
- The collector keeps `tie_rule`, but the export drops it along with source event IDs. Jurisdiction, WD rules and displayed gross-versus-relative score convention are absent. Two player prices alone do not establish a ties-void market or justify normalizing their implied probabilities to one.
- The full `historical_matchups_outcomes.csv` is excluded by the publisher's `.gitignore`; a pinned public file-history query returned zero entries. It was not recovered. No third-party credential or paid API was used.
- Official tee assignments were fetched retrospectively. They establish the recorded course, not the historical publication time of the assignment.
- Publisher model outputs, picks and performance were discarded from this audit. No ROI, probability model or new sport-side screen was run.

## Other checked leads

The same repository's `data/odds.csv` contains 9,397 records, including round-score markets. Its [own parser](https://github.com/jriordan55/alpha-caddie/blob/5508f6f35830f09d0b1e0c06abed0b2b489dde04/alpha-caddie-web/scripts/odds-csv-props.mjs) identifies it as **Hard Rock**. It has no bookmaker label or quote-time columns, and no round-score rows for Farmers, Pebble or RSM. Numeric `PRICE_CHAN_ID` values were not reinterpreted as bookmakers.

Additional GitHub code leads were inspected at pinned commits: `chrisdell88/birdiex` has no matching saved price-data files in its complete tree; `jposhie1777/nba-prop-analyzer` has a FanDuel PGA scraper but no matching saved data in the fully inspected `mobile_api` subtree (its full recursive tree was truncated). Repository tree responses are retained locally. A scraper implementation is not a historical archive.

The [matchup-terminal snapshot](https://github.com/travismangone/matchup-terminal/blob/e6747d001e9f4adc43997839e5fed77ac99ede49/data/matchups.json) contains 116 pair records, nine with two FanDuel prices and a tie label. It has no event, round or timestamp fields, so those nine are not added to the historical cohort. Alpha-caddie's `prior_event_live_archive.json` contains only Wyndham, St. Jude and BMW 2026 bundles; none is a G11 target. Both additional files were retained and checked against their pinned Git blobs.

## Reproduce and next step

```bash
state/runtime/research-venv/bin/python tools/audit_golf_historical_prices.py
state/runtime/research-venv/bin/python -m unittest tests.test_golf_historical_prices
```

The [JSON audit](golf-historical-price-audit-2026-09-19.json) records source hashes, request/receipt times, per-edition attrition, unresolved names and the hash of the local price/assignment inventory. Seven focused tests cover cross-course classification, three-player completeness, excluded courses, ambiguous names and unzoned clocks.

Retain this archive as a concrete price-source lead. To execute G11, still recover an actual cross-course matchup or relevant FanDuel round-score series, original timing semantics and applicable settlement terms. Do not reopen the failed sport screens or promote the source discovery into an edge. Scheduled work remains paused.
