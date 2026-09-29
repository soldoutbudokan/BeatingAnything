# PointsBet Ontario NFL alternate prices: historical test

**Result: a small player-prop lead, but no demonstrated current or systematic edge.** A newly recovered Ontario archive permits actual price arithmetic. Thirty distinct alternate player offers across 14 games yield two discrepancies above the declared 3% threshold, both in the same Bears–Texans game. A separate raw Buffalo–Miami board supplies 26 matched alternate spread/total sides; none has positive conservative reference-implied EV. Missing original cross-book observation clocks exclude all comparisons from the strict cohort. These are September **2024** prices, not current offers.

Work was requested September 28 Toronto time and performed September 29, 2026 UTC. The [declaration](../docs/pointsbet-nfl-alternate-test-declaration-2026-09-29.md) was committed as `c9ef56cb0653765815c6b0a73f4f0ab95db65407` before alternate-price comparisons. No game outcomes were read, no realized ROI was calculated, and no rule was tuned after results.

## Actual data recovered

The public [mykolafc/betsmart repository](https://github.com/mykolafc/betsmart/tree/55d1ae445add653a0a462fc4de0b889ec8698c59) contains an Ontario-specific collector whose hostname is `api.on.pointsbet.com`, a raw NFL event response, and separate book CSVs. Eight source files, **6,301,010 bytes**, were recovered through GitHub and verified against their Git blob hashes. Exact paths, commits, sizes and SHA-256 hashes are in the [source manifest](pointsbet-nfl-alternates-2026-09-29-sources.json). Raw third-party files are not republished here.

| Source | Coverage used | Limitation |
| --- | --- | --- |
| Raw Buffalo Bills at Miami Dolphins event | 95 markets; 64 alternate spread outcomes, 70 alternate total outcomes, plus player/period markets | One game, scheduled 2024-09-13 00:15 UTC; event metadata timestamp 2024-09-11 21:13:57 UTC is not a verified collector clock |
| September 12 commit, PointsBet CSV | 3,158 NFL rows across 16 games | Derived data; no original clocks or player IDs |
| September 12 commit, Pinnacle CSV | 3,122 NFL rows across 16 games | Same missing timing/identity evidence |
| September 30 commit, PointsBet CSV | 588 NFL rows across 12 games | Same limitation; distinct later version, not a prospective replication |
| September 30 commit, Pinnacle CSV | 974 NFL rows across 12 games | Same limitation |

The two PointsBet CSVs contain 2,317 alternate-player rows before reference, price-range, and identity filters. They omit the full-game alternate spread/total ladders; the raw event response preserves them. The source parser's category filter explains why searching only its CSVs would miss those game ladders.

A FanDuel CSV was inventoried but not substituted for the declared Pinnacle reference. The contemporaneous-version DraftKings CSV had zero NFL rows. A separate PointsBet Canada archive search found two ten-event dumps with zero NFL games. The current PointsBet page returned HTTP 403 from this runtime, and a public Ontario API URL was inaccessible through the web reader. No configured The Odds API or OddsPapi key was available. No access restriction was bypassed.

## Price-comparison results

We rebuilt joins from date, literal fixture label, statistic, player label, threshold and side, ignoring the publisher's join key, fair-odds and arbitrage columns. Spread pairs require opposite signs for the two teams. Player names are abbreviated in both CSVs; these are provisional literal matches, not independently established identities.

The diagnostic requires half-point contracts, selected/reference decimal prices 1.20–6.00, a unique two-sided reference with 0–12% overround, and at least 3% EV under **both proportional and power de-vigging**, after a 2% haircut to net winnings. Duplicate identical target prices are collapsed; conflicting target prices and duplicate reference sides are excluded. Alternates at the same threshold as PointsBet's own main market are reported separately and do not count as distinct alternates.

| Diagnostic | Compared sides | Games | Positive under both methods | At least +3% under both |
| --- | ---: | ---: | ---: | ---: |
| All matched CSV markets, including main controls | 357 | 26 | 16 | 5 |
| Distinct alternate player thresholds only | 30 | 14 | 5 | 2 |
| Earlier CSV version, distinct alternates | 25 | 12 | 4 | 2 |
| Later CSV version, distinct alternates | 5 | 2 | 1 | 0 |
| Raw Buffalo–Miami alternate spreads versus retained Pinnacle CSV | 12 | 1 | 0 | 0 |
| Raw Buffalo–Miami alternate totals versus retained Pinnacle CSV | 14 | 1 | 0 | 0 |

The two player candidates are from **Chicago at Houston, September 15, 2024**:

| Contract | PointsBet | Pinnacle same-line Over / Under | Conservative reference-implied EV after haircut |
| --- | ---: | ---: | ---: |
| C. Stroud over 23.5 completions (24+) | 2.25 / +125 | 1.90909 / 1.90909 (−110 / −110) | +11.25% |
| S. Diggs over 4.5 receptions (5+) | 1.8334 / approximately −120 | 1.67568 / 2.21 (−148 / +121) | +3.33% |

These are **two offers on one game**, not two independent confirmations. PointsBet's Stroud main threshold was 22.5; its Diggs main threshold was 5.5, so both flagged contracts are genuinely different alternate thresholds. The raw candidate rows and Pinnacle opposites were checked directly. Neither has the original bookmaker/capture clocks or full raw event response needed to establish that the compared prices coexisted. Stale references, different capture times, settlement differences and parser errors remain plausible explanations.

For Stroud, a symmetric −110/−110 reference yields 50% under either de-vig method. The arithmetic is `0.5 × (1 + 0.98 × 1.25) − 1 = 11.25%`. This does not establish a true 50% chance or an executable 11.25% edge.

The 26 raw alternate spread/total comparisons range from **−13.40% to −4.54%** using the smaller of the two EV estimates. Their reference clocks are also unknown, so they do not prove fair PointsBet pricing. They supply no positive discrepancy in this particular historical board. Two additional main-spread control sides bring the raw-to-CSV total to 28; neither is positive.

## Does the raw ladder ignore NFL key numbers?

No simple linear point-cost error appears in this board. Incorporating the raw main spread pair, which is omitted from the alternate tab, gives these implied exact-margin masses:

| Miami winning margin | Proportional de-vig difference | Power de-vig difference |
| --- | ---: | ---: |
| +3 | 6.33% | 6.97% |
| +7 | 4.03% | 4.38% |
| −3, meaning Buffalo wins by 3 | 6.07% | 6.87% |
| −7, meaning Buffalo wins by 7 | 5.05% | 5.72% |

For example, Miami −2.5 / Buffalo +2.5 both pay 1.9091. Miami −3.5 pays 2.15 while Buffalo +3.5 pays 1.6667. The ladder does charge materially for crossing three. Those implied masses do not prove calibration, and subtracting separately de-vigged market probabilities depends on the margin-removal assumption. They must not be compared mechanically with the repo's pooled historical 8.93%/5.89% estimates for different conditioning sets.

Across all supported raw half-point game/player contracts, **3,006 nested-price comparisons show zero strict price reversals**. There are **1,286 opposite-side covering pairs and zero with positive minimum return after the haircut**. The best minimum return is −5.45%, on the ordinary main spread pair. These are payout-structure calculations, not independent observations or a performance backtest.

There is one identical-threshold inconsistency: **Dalton Kincaid over 4.5 receptions pays 1.9524 in the main market but 1.9091 for 5+ in the alternate market**. The alternate pays less. This supports checking equivalent contracts before choosing a tab, not a claim of positive EV. The labels and numeric thresholds agree, but some other raw market-info templates are imprecise; all 95 markets carry `includesOverTime: false` and null periods. Historical settlement rules were not established, so all cross-market equivalence remains conditional.

## What this establishes and what it does not

The source search succeeded: actual Ontario NFL alternate data exist and can be analyzed reproducibly. The first test does not support a blanket claim that alternate spreads/totals are badly priced. Player alternates remain worth investigating, with one unusually large historical completion-price discrepancy. The evidence cannot establish current mispricing, an accepted price, systematic positive EV, or positive realized returns. The strict comparable cohort is **zero**, not a zero-percent betting return.

The next useful acquisition is fresh Ontario full-event responses with both sides of matching reference lines and separate collector/book/market clocks, followed by direct offer verification. The Odds API documents `pointsbetca` and event-level alternate markets, but actual Ontario alternate coverage has not been verified. Its Pinnacle feed also carries a public-site-delay caveat. The repo's existing collector requests only FanDuel/Pinnacle and would need explicit bookmaker configuration before a bounded authorized capture. The OddsPapi PointsBet guide identifies the Australian book; do not silently substitute it for Ontario. No purchase, new account, schedule, alert or wager was created.

## Reproduction and checks

Run from the repository root with Python 3.12; this tool uses only the standard library:

```sh
python tools/test_pointsbet_nfl_alternates.py --self-test
python tools/test_pointsbet_nfl_alternates.py --download
```

`--download` reads only pinned public GitHub source URLs and verifies Git blob and SHA-256 hashes. Without that flag the tool uses verified local files and makes no network request. Every eligible arithmetic comparison, filter count, raw ladder, candidate and explicit null ROI is retained in [the JSON result](pointsbet-nfl-alternates-2026-09-29.json).

Nine analytical checks cover de-vigging, haircut arithmetic, opposite-sign spread pairing, duplicate references and integer-line exclusion. A separate audit recalculated all 357 CSV proportional EVs with Decimal arithmetic, all four key-margin masses directly from raw prices, both positive alternate joins, and integer-outcome payoffs for the best coverage pair. All passed. All 1,089 raw selection price-change clocks precede the event metadata time to its one-second precision; this is internal consistency, not proof of quote freshness. No outcomes were used.

Primary provider references checked during the search: [The Odds API bookmaker catalog](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html), [market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html), and [OddsPapi's Australia-specific guide](https://oddspapi.io/blog/pointsbet-api-odds-access/).
