# A different market with real data: NBA first-basket scorer

**Found and acquired: historical FanDuel first-basket prices, opening-possession history and scoring outcomes.** This is a player-to-score-first market, separate from the previously tested NBA points markets. The source supports an exploratory price test now; no profitability claim has been made.

## What is actually available

The public [LeFirstBasket archive](https://github.com/martinbog19/LeFirstBasket/tree/b8130671558c6d5b33d6cfbc6a8410d986d6b3ff) contains a real `data/odds_first_basket.csv`. All downloaded publisher files match their pinned Git blob hashes and retained SHA-256 receipts. The [measured audit](nba-first-basket-source-2026-09-19.json) records every source and exclusion.

| Evidence | Measured coverage |
| --- | ---: |
| All-book first-basket price rows | 35,303 |
| FanDuel prices / games / players | 7,673 / 799 / 362 |
| FanDuel quote dates | December 1, 2024–May 12, 2025 |
| Distinct games with ten-runner, fresh pregame FanDuel boards | **580** |
| Prices on those boards | **5,800** |
| Those games with complete unique player IDs, a first-score result and ten recorded starters | **449** |
| Those 580 games present in an independent play-by-play archive | **580** |

The archive also supplies 2019–2025 season files with first scorer, first-point value, opening jumpers and possession winner; the six earlier files contain 7,583 game rows. These are source rows, not a claim that every field is complete. Starter flags and stable Basketball Reference player IDs are available in the roster data. Three fixed sample outcomes were independently reconciled; the full cohort has not been graded or modelled.

## Why this market is worth testing

First score depends on **who gets the opening possession and whom the opening play targets**. A player's full-game scoring share can miss that distinction. A center change can alter the opening-possession probability while the team's leading scorer remains the same. The concrete, unproven hypothesis is that FanDuel's first-scorer allocation does not fully reflect that matchup-specific change.

[Card 41](../docs/hypotheses/basketball-first-score-opening-possession.md) records the proposed test. Use prior-game jump-ball and first-score histories to price the two possession scenarios, then compare against the actual pregame FanDuel board. Do not condition a pregame forecast on the target game's realized jump-ball winner, actual first shooter or eventual starting lineup.

## Price timing and market identity

The pinned [collector](https://github.com/martinbog19/LeFirstBasket/blob/b8130671558c6d5b33d6cfbc6a8410d986d6b3ff/run_before_game.py) requests `player_first_basket` in decimal format. It saves the literal bookmaker key, market update time, event ID, Basketball Reference game ID and a UTC local collection timestamp. Its code was read, not executed.

The 580-board subset requires ten distinct named runners, valid decimal prices, one market-update clock, a nonfuture quote no more than five minutes old, and collection at least one minute before the earlier of the publisher's Eastern-time start and an independently matched ESPN start. NBA Stats-derived home/away/date identities also agree. Median collection lead is **73.0 minutes**; median quote age is **40.4 seconds**.

Of 801 FanDuel snapshots, 187 do not have ten unique runners, 25 arrive within a minute of or after start, six have stale quotes, two lack an unambiguous NBA fixture match and one has duplicate publisher game records. These are ordered, mutually exclusive audit classifications. Partial boards remain retained; they are not silently completed using other books or collection times.

This market has competing named scorers, rather than an Over/Under pair. Ten quoted players do not prove ten actual starters; settlement must retain nonstarter voids. Actual starter flags may be used for settlement, not retrospective selection.

## Independent outcome check

A [three-game selection](nba-first-basket-validation-selection-2026-09-19.json) was saved at **22:35:02 UTC**, before outcome values were inspected: first, middle and last chronologically among the 449 games with the required source coverage. A separate [ESPN-derived play-by-play release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_pbp), 21.6 MB and hash-verified against GitHub's asset digest, agrees on the scorer, scoring value and game clock in **all three**. Their quote receipts also precede the first recorded play's wall clock. Game-ID coverage was verified for all 580 games; this is not a full-cohort outcome reconciliation.

Direct NBA CDN and ESPN summary requests returned 403 and were stopped. The independent public release supplied the validation data. Those failed captures remain recorded locally; no restriction was bypassed.

## Terms and limits

FanDuel's published [Indiana house rules](https://www.fanduel.com/fanduel-sportsbook-house-rules-in) define first basket as the first score, including free throws. The [Maryland operator rule document](https://maryland.livecasinohotel.com/-/media/files/maryland/fanduel/houserulessportsv2.ashx) also states that rule and voids a selected player who does not start. The publisher's outcome collector stops at the first positive score. Other books' first-field-goal markets must not be treated as interchangeable probability references. The Indiana page's June 11, 2025 effective date is after this archive's final quote, and the archive omits jurisdiction: these documents support the proposed research convention, not the terms attached to every historical quote.

Other limits: original odds JSON bodies are absent; nearly every game has one snapshot, so there is no general closing-price series; lineup timestamps are unzoned and excluded from timing claims; the publisher has already studied the data. These limits permit exploratory research but do not meet the project's prospective promotion or executable-bet gates. No edge, alert or wager is established.

## Reproduce with the retained local captures

```sh
state/runtime/research-venv/bin/python -m pip install -r requirements-first-basket.txt
state/runtime/research-venv/bin/python tools/audit_nba_first_basket_archive.py --validate
state/runtime/research-venv/bin/python -m unittest discover -s tests
```

Bulk source files and the detailed board inventory remain under ignored `data/raw/creative-market-search-2026-09-19/`. The report contains source URLs, pins, hashes and three price-board examples. **246 tests pass.** No fitted model or ROI calculation ran, and scheduled jobs remain paused.
