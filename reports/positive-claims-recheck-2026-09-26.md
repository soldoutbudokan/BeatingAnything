# Earlier positive claims rechecked — September 26, 2026

**The teaser and early-payout reports identify structural leads, but neither currently demonstrates an executable forecasting edge.** Their favorable historical numbers remain in the record. Price, timing and settlement qualifications prevent treating those numbers as confirmed mispricing.

## NFL six-point teasers

The earlier [teaser study](edge-search-2026-09-22.md) reports 77.16% wins on 613 qualifying 2015–2025 legs, using the Wong windows and total≤49 filter. The saved season-week bootstrap interval is **73.51%–80.74%**. These are per-leg sporting outcomes, not observed combined ticket prices.

On September 26, [DraftKings' official public teaser table](https://support.draftkings.com/dk/en-us/what-is-a-teaser?id=kb_article_view&sysparm_article=KB0010765) lists **NFL six-point two-pick −135 and three-pick +140**, replacing the old report's assumed −120/+160 for current public-price comparisons. The page is a generic support table; it is not an Ontario account betslip, a historical price archive, or proof that a particular combination was accepted. The separate [jurisdiction/rule check](teaser-price-check-2026-09-26.md) records that distinction.

| Current public table | Per-leg break-even under independent equal-probability legs | With 2% net-winnings haircut |
| --- | ---: | ---: |
| Two picks, six points, −135 | 75.79% | 76.12% |
| Three picks, six points, +140 | 74.69% | 74.98% |

The reported 77.16% point estimate still exceeds both thresholds. Its interval crosses both, however, and the `p**k` conversion assumes independent, homogeneous legs. Applying the rounded **early-training** rate of 73.85% to these current public prices gives approximately **−5.06% /−3.34%** EV before costs. Applying the higher later rate gives positive estimates, but that later result cannot be retroactively treated as the probability forecast used to select the old bets.

The old script also computes actual grouped ticket outcomes: it orders qualifying legs by kickoff within a week and groups consecutive games. This avoids using independence to count winning combinations, but takes **each constituent game's own closing spread and total**. A later game's closing number may not have existed before the earliest leg began. Grouped returns therefore do not establish a causally available ticket. The fixed assumed ticket prices likewise have no captured combined offer behind them.

The [exact-source reproduction](teaser-original-cohort-audit-2026-09-26.json) makes that timing issue concrete: **151 of 255 two-leg tickets and 98 of 133 three-leg tickets span different kickoff times**. Even the remaining simultaneous games lack captured combined quotes. This counts the original grouping; no newly selected subgroup return was calculated.

It also corrects the old claim that there were no pushes. The original qualifying cohort contains **615 legs: 473 wins, 140 losses and two pushes**, including 97 integer original lines. The reported 613-leg win rate excludes the two pushes. One push appears in each original ticket grouping; the other is an unused leftover. The two-leg ticket has one win plus a push, while the three-leg ticket has two wins plus a push. Current DraftKings rules make the former no action and reduce the latter to a winning two-leg ticket. The old script drops both tickets, so its three-leg settlement is incomplete. This small omission does not explain away the favorable historical returns; it does prevent treating the old settlement accounting as complete.

The retained NFL price database contains ordinary moneylines, spreads and totals; it has **no teaser contract market**. It can establish simultaneous constituent-line availability for a repaired historical selection, but cannot supply the missing actual combined price. The next meaningful validation requires that price plus all legs and their clocks before any selected game starts. Do not reconstruct an unavailable teaser offer from later closing numbers.

## Early payout

The [early-payout study](early-payout-2026-09-22.md) measures how often a team reaches a specified lead and fails to win. That settlement benefit is economically relevant, but the historical price comparisons have specific limits:

- College bet365 moneylines date from **before the offer existed**, as the original report itself discloses. Applying a later promotion to them is a counterfactual return, not an observed promotional bet. The script pivots by game and book without enforcing common quote timestamps, so its “same capture” claim is not established by the code.
- NFL returns use consensus closing moneylines, not authenticated bet365 promotional contracts. Two-way normalization also needs explicit treatment of the tie/void outcome when converting ordinary win probabilities to payout probabilities.
- NBA sizes the lead-reversal benefit without an offered moneyline-price backtest.
- Soccer has historical ordinary prices and reconstructed lead paths, but no verified game-by-game promotion eligibility, terms or synchronized quote receipts. The positive sample is therefore a conditional model result.

These results do not establish that current promotional prices leave the estimated benefit uncharged, or that a forecast outperforms the relevant priced event independently. Current eligible offers, contemporaneous fair-reference quotes, correct payout/void definitions and independent forecast validation remain necessary.

## Authoritative state and disposition

The original `data/raw/nfl-teasers/` and `data/raw/early-payout/` directories were absent at review start. A **single 2,180,006-byte request** subsequently recovered the exact pinned teaser schedule in `data/raw/nfl-teaser-review-2026-09-26/games.csv`, matching original SHA-256 `6048e3576f195d6000fe5304625c5a1284f1ca42b778b19b3331f1a276e05f0b`. The receipt and original cohort/push/timing reproduction are preserved; no expensive play-by-play download or new strategy backtest was run. The early-payout raw inputs remain absent. The retained `nfl_odds.duckdb` has no bet365 rows or teaser markets. Green repository tests cannot repair those evidence gaps.

Preserve the sporting mechanisms and favorable historical estimates as leads. Correct claims that they are already established edges, do not assign current Ontario execution from a generic support page, and do not silently replace the old assumed prices in the historical output. This review changes interpretation and the next validation requirement; it does not erase or retune the original studies.
