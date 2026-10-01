# PointsBet NFL alternate-line and teaser-leg audit — 2026-09-28 (staleness follow-up 2026-09-29)

**Follow-up, September 29:** the ladder-shape conclusion below stands, but a second, simultaneous three-book capture found that PointsBet leaves rungs and even a main total unrepriced for a day or more. The 49ers–Broncos total sat at 46.5 (1.90/1.90, last repriced 33 hours earlier) while Pinnacle had moved to 48.5, so PointsBet Over 46.5 against Pinnacle Under 46.5 at 2.20 summed to 0.981, a 1.9% arb, with three adjacent rungs within 0.2%. Cross-book near-arbs against PointsBet are therefore real but come from staleness, not from the alternate-line shape. See the section at the end.

**PointsBet's NFL alternate ladders are not badly mispriced.** Against Pinnacle's fresh alternate rungs the Pick Your Own Line ladder returns **−6.4% on average across 140 matched lines in 10 games**, with 7 lines above zero and none above **+1.1%**. Alternate totals return **−6.0% across 75 matched lines**, with 3 above zero and none above +1.0%. PointsBet's two-sided hold on both ladders is about **6.3%** against Pinnacle's **3.6–4.0%**.

**The Wong-window teaser legs are priced close to their historical win rate, not badly off.** PointsBet has no fixed-price teaser: a "teaser" there is a parlay of Pick Your Own Line alternates, so the alternate price at the teased number *is* the leg price. Six such legs were on the board (favourites −7.5 to −8.5 or underdogs +1.5 to +2.5 moved six points): mean price **1.35 (about −286)**, implying 74.1% with vig and 69.6% no-vig. The 2010–2026 historical win rate for those legs is **75.3% ± 2.7% on 960 legs**. Per leg that is **+1.4%** against the closing-line bucket benchmark and **−3.5%** against Pinnacle on the two legs Pinnacle also quoted. A two-leg parlay at the geometric-mean price of **1.82 (about −122)** returns +3.3% at the historical rate, which is better than a fixed −135 chart (−1.3%) and slightly worse than −120 (+4.0%). None of this survives Pinnacle's game-specific fair prices, and six legs cannot establish an edge.

## What was captured

| Source | Content | Clock |
| --- | --- | --- |
| PointsBet AU public event API (`api.au.pointsbet.com/api/mes/v3/events/{key}`), 15 NFL events | Point Spread, Pick Your Own Line (23–47 rungs per side), Total, Alternate Totals, Moneyline, per-outcome `priceLastUpdated` | Fetched 2026-09-29 03:04–03:06 UTC; receipts in `.time` files |
| OddsPapi `odds-by-tournaments`, tournament 31, bookmaker `pinnacle`, verbosity 3 | Full-game spreads, totals, moneyline with per-outcome `changedAt`; 18 events | Fetched 2026-09-29 ~03:00 UTC |
| OddsPapi bookmaker catalog | `fanatics` is listed as `cloneOf: pointsbet.com.au`; no separate PointsBet Canada entry; OddsPapi's PointsBet feed carries no spread markets at all | — |
| Pinned nflverse `games.csv` (already held, SHA `6048e357…`) | Closing spread, total and final margin, 1999–2026 | — |

All files and SHA-256 hashes are in `data/raw/pointsbet-nfl-alt-2026-09-28/manifest.json` (40 files, 18,036,129 bytes; ignored by git like other raw data). The live Eagles–Bears game was excluded. The PointsBet Ontario host is behind a Cloudflare challenge and the browser extension was not connected, so the Australian ladder of the same pricing engine was used; Ontario margins may differ.

## Tests and results

**Main lines agree.** PointsBet and Pinnacle no-vig moneyline probabilities differ by **0.7 points** on average across 11 games, so neither book's main was stale at capture.

**Ladder versus Pinnacle.** Only Pinnacle rungs updated within one hour of that game's freshest Pinnacle update were used; 118 stale rungs were dropped. One of them (Giants–Cardinals Under 35.5, 22 hours old and non-monotone against its neighbours) had produced an apparent +11% that disappears with the freshness filter.

| Move | Lines | Mean return vs Pinnacle fair |
| --- | ---: | ---: |
| Buying points (offset > 0) | 65 | −3.3% |
| At Pinnacle's main (offset 0, half-point rungs) | 30 | −5.4% |
| Selling points (offset < 0) | 65 | −9.7% |
| Six points bought | 9 | −2.2% |
| Six points sold | 9 | −14.7% |

The best lines were New England +14.5 at 1.36 (+1.1%), Pittsburgh +3.5 at 1.42 (+0.5%) and Cleveland +4.5 at 1.67 (+0.5%). These are inside ordinary book-to-book noise.

**Ladder versus history.** For every rung, the team's cover probability was estimated from 2010–2026 legs whose closing line was within half a point of Pinnacle's main (PointsBet's main when Pinnacle had none). This benchmark ignores the total and the matchup, so single lines are noisy; aggregates over 944 lines in 14 games are informative. Buying points returns **−2.3%**, selling points **−18.0%**. The sell side is where PointsBet's ladder is expensive, and it is the side no teaser uses.

**Key-number shape.** Implied probability mass on each losing margin, from adjacent no-vig rungs:

| Exact margin | PointsBet | Pinnacle (fresh, n) | Historical bucket |
| --- | ---: | ---: | ---: |
| 3 | **5.7%** | 8.4% (18) | 7.9% |
| 7 | 4.2% | 7.3% (4) | 4.8% |
| 2, 4, 5, 8, 9 (mean) | 2.0% | 2.6% | 2.2% |
| 0 (tie) | 0.8% | — | 0.3% |

PointsBet under-weights a margin of exactly 3 in **52 of 52** game-sides, by 0.2 to 4.0 points and 2.2 points on average; the margin of 7 is nearly right. The ladder therefore charges too little for crossing 3 and too much for the tie and the tails. The 2.2-point shortfall at 3 is the whole reason the Wong legs land near break-even instead of at PointsBet's usual −3% per side: buying six points across 3 recovers roughly the hold. It is not enough to make the legs positive against Pinnacle.

## Wong legs on the board

| Leg | Anchor | Price | PB no-vig | Pinnacle fair | Historical bucket | vs Pinnacle | vs history |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cleveland +8.5 | +2.5 | 1.36 | 0.695 | — | 0.744 (1,140) | — | +1.2% |
| Jacksonville +8.5 | +2.5 | 1.33 | 0.706 | — | 0.744 (1,140) | — | −1.1% |
| Dallas +8.5 | +2.0 | 1.36 | 0.688 | — | 0.772 (635) | — | +4.9% |
| Dallas +7.5 | +2.0 | 1.40 | 0.671 | 0.693 | 0.743 (635) | −2.9% | +4.1% |
| Arizona +7.5 | +1.5 | 1.29 | 0.725 | 0.744 | 0.759 (594) | −4.0% | −2.1% |
| Denver +8.5 | +2.5 (PB main) | 1.36 | 0.688 | — | 0.744 (1,140) | — | +1.2% |

No Wong favourite was on the board this week. The Dallas legs look best only because the historical bucket for a two-point underdog is hotter than Pinnacle's game-specific distribution; against Pinnacle the same leg is −2.9%.

## Limitations and what would change the answer

- One slate, six Wong legs, ten games with fresh Pinnacle alternates. This is a price-shape audit, not a return backtest, and no outcomes were used to grade current prices.
- The Australian ladder stands in for Ontario. The engine is the same (OddsPapi lists Fanatics US as a clone of it), but Ontario hold could differ. A direct Ontario capture through a connected browser would settle it.
- The historical benchmark conditions on the closing-line bucket only. The Pinnacle comparison is the better fair price wherever Pinnacle quotes the rung.
- Pinnacle's own alternate rungs were partly stale in the OddsPapi snapshot; the freshness filter removed them, and an unfiltered run overstates the best lines.

The claim that individual Wong teaser legs are badly mispriced at PointsBet is not supported. The one genuine structural fact is the under-weighting of margin 3, and its size is about equal to PointsBet's per-side hold. No wager, alert or schedule follows from this audit.

## Follow-up: simultaneous three-book capture, 2026-09-30 00:43 UTC

All 15 PointsBet events, then FanDuel and Pinnacle through OddsPapi, were captured within 25 seconds (`data/raw/pointsbet-nfl-alt-2026-09-29-sim/`, manifest with SHA-256). The pairing is the strict arb test: PointsBet price on one side against the other book's price on the opposite side at the same line, arb when the reciprocals sum below one. Tool: `tools/check_pointsbet_cross_book_arbs.py`; output `reports/pointsbet-cross-book-arb-check-2026-09-29.json`.

| Pair | Games | Pairs | Sum < 1 | Within 1% | Within 2% | Median sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PointsBet vs Pinnacle | 14 | 408 | 4 | 8 | 29 | 1.050 |
| PointsBet vs FanDuel (OddsPapi) | 14 | 1,844 | 25 | 46 | 109 | 1.061 |

**Pinnacle.** All four arbs are 49ers–Broncos totals. PointsBet's main total was 46.5 at 1.90/1.90, last repriced 2026-09-28 15:33 UTC; Pinnacle's main was 48.5 at 23:09 UTC the next day. PointsBet Over 46.5 (1.90) plus Pinnacle Under 46.5 (2.20) sums to 0.981; Over 47.5, 48.5 and 41.5 sum to 0.988, 0.998 and 0.999. A refetch six minutes later returned the same prices with `isOpenForBetting` true. PointsBet's spread and moneyline on that game agreed with Pinnacle, so this was a single unrepriced market, not a frozen board. Every PointsBet NFL price on the board was at least 17 hours old at capture (median 17.7 hours, maximum 48.7), which is consistent with an Australian trading desk that reprices NFL in batches.

**FanDuel.** The OddsPapi FanDuel fixtures are polluted: Commanders–Colts carries two full-game moneylines (2.66/1.51 and 1.72/2.18) and two "main" spreads (home +1.5 and home −2.5), and FanDuel's flagged main spread disagrees with Pinnacle's by 3 to 6 points in every game. Every FanDuel "arb" pairs a PointsBet rung with a row from the wrong game. The FanDuel side of the user's observation cannot be tested from this feed, and FanDuel Ontario's own API did not answer from this machine.

**What this changes.** The claim that PointsBet's alternates are badly shaped remains unsupported. The claim that near-arbs against PointsBet appear on the board is supported, in one game of fourteen, by a market PointsBet had not touched for 33 hours. Whether that is a winning test depends on acceptance and limits at the stale price, which no API capture can show. A fair test is a timed capture loop of PointsBet Ontario, Pinnacle and FanDuel Ontario through a connected browser over one week, recording every sum-below-one pair with both rung ages, followed by small-stake acceptance attempts. Nothing here is a wager, alert or schedule.

## Live monitor, 2026-09-30 00:58 UTC: PointsBet Ontario against Pinnacle and FanDuel Ontario

All three books are reachable headless from a Canadian residential connection: PointsBet Ontario answers a Chrome TLS profile (`curl_cffi`), Pinnacle's guest API returns full alternate ladders with stake limits, and FanDuel Ontario's event pages carry alternate spreads and totals under the popular tab. `tools/collect_pointsbet_live_alternates.py` captures all three in about 30 seconds, normalises 4,000 rows, pairs each PointsBet rung with the opposite side at the same line and appends every sum-below-one pair to `data/live/pointsbet-alt-monitor/arbs.jsonl` with PointsBet's rung age. `tools/analyze_pointsbet_live_monitor.py` attributes each pair against Pinnacle's two-sided fair. `config/com.beatinganything.pointsbet-alt-monitor.plist` runs it every five minutes once installed; it is not installed.

The first clean cycle (16 PointsBet games, 1,552 pairs) found **32 sum-below-one pairs of two distinct kinds.**

| Kind | Pairs | Best sum | Which leg is +EV against Pinnacle |
| --- | ---: | ---: | --- |
| PointsBet total vs Pinnacle, PointsBet main total 1–2 points behind Pinnacle and 19–33 hours old (49ers–Broncos, Rams–Eagles) | 7 | 0.978 | PointsBet leg, +2% to +7% |
| PointsBet underdog +6.5 to +16.5 vs FanDuel favourite tail (Cardinals–Giants, Jaguars–Bengals, Jets–Bears), all mains agreeing | 25 | 0.976 | FanDuel leg where Pinnacle quotes (Bengals −7.5: FanDuel +6.9%, PointsBet −1.6%); tails beyond Pinnacle's ladder unattributable |

Across all alt-spread rungs with a Pinnacle two-sided quote, PointsBet returns −7.0% (buying six or more points −2.7%, selling −13.4%) and FanDuel −5.5%; FanDuel's favourite tails at −7.5 run +4% to +8% against Pinnacle in four games. PointsBet's main spreads were within half a point of Pinnacle in all 16 games; its main totals were a point or more away in 4 of 16, with every PointsBet price on the board 17 to 36 hours old.

**Reading.** The near-arbs seen on screen between PointsBet and FanDuel are real and structural, but the mispriced leg is FanDuel's long favourite tail, not PointsBet's teased underdog rung. The near-arbs against Pinnacle come from PointsBet totals left unrepriced. Neither supports betting PointsBet's Wong legs on their own. Acceptance, limits and account life at both books remain untested; the monitor records the opportunities, not their fills.

## Cloud mode, 2026-09-30 03:10 UTC

The Ontario hosts refuse cloud addresses (PointsBet Ontario 403, FanDuel Ontario geo-fenced), but two same-engine boards answer plain clients from anywhere: PointsBet Australia and FanDuel New Jersey, plus Pinnacle. Back-to-back pulls against Ontario showed FanDuel NJ 99.3% price-identical on 1,666 rungs (differences only on a few main-line rungs, max 0.07) and PointsBet AU carrying the identical rung set and rung ages, with prices identical on 53% of rungs and within 0.3–0.6% on average; the rest is price-point rounding (Ontario quotes American points such as −160 = 1.625 where Australia shows 1.67), reaching about 3% on some core rungs. `PB_REGION=au FD_REGION=nj` runs the collector on the standard library with no third-party package; the cloud-mode cycle reproduced the same 49ers–Broncos and Rams–Eagles total pairs against Pinnacle and the same Cardinals–Giants, Jaguars–Bengals and Jets–Bears tail pairs against FanDuel. A cloud routine can therefore screen; every flagged pair still needs confirming on the Ontario board before staking, because the Australian rounding can add or remove a 1–3% margin.
