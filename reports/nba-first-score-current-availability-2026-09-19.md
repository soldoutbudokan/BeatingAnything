# Current NBA prices do not supply first-score evidence

At 02:05 UTC on September 20 (September 19 Toronto), two corrected OddsPapi current-odds requests succeeded: **five FanDuel fixtures / 30 selections and fourteen BetMGM fixtures / 88 selections**. All fixtures are NBA tournament `132`, pregame, starting October 20–23 UTC. All returned markets are moneyline, spread or total. **Neither book returns a first-score market or any player selection.** The [complete source record](nba-first-score-current-availability-2026-09-19.json) retains identities, source hashes, receipts and counts.

The initial request followed the documentation's plural `bookmakers` parameter and returned HTTP 400. Its error explicitly required one bookmaker via singular `bookmaker`. A separately recorded correction made one request per book and succeeded. Three attempts were made in total; no account request, purchase, upgrade, denial bypass or automatic retry occurred.

## A concrete limitation in the historical interpretation

Seventy of BetMGM's 88 returned selections say `active: true` while their containing market says `marketActive: false`. The selection flag alone therefore cannot establish that the market is open. Historical entry payloads do not preserve this separate market flag. This observation does not retroactively prove any particular old selection was closed, but it supplies a concrete reason to retain the historical execution caveat.

All returned prices have provider `changedAt` values. FanDuel has **zero bookmaker-reported change clocks out of 30**; BetMGM has four out of 88. Native bookmaker fixture/market/outcome IDs and links are available on these main lines. They are useful for future verification, but do not supply missing historical first-score labels, clocks or executable offers.

## Ready for a future bounded capture

The [manual capture tool](../tools/capture_nba_first_score_current.py) preserves raw bytes, all state flags, native IDs, distinct source/receipt clocks and missing fields. It defaults to dry-run; `--fetch` makes at most two calls. [Usage and limits](../docs/nba-first-score-current-capture.md).

The parser was replayed against both actual source responses without another network request. Tests cover the observed market/selection flag conflict, missing clocks, fixture scope, the corrected query, raw retention and secret/error handling. **291 tests pass.** No forecast, betting alert, wager, registered forward trial, background process or schedule was created.

## Goal audit

The full goal remains unachieved: the prior simulated profits, contrary later-price evidence, conditional market definitions and missing quote verification do not establish an edge. The previous goal turn was **progress**, and this turn also supplies new evidence and a bounded capture capability.

The same external data dependency nevertheless persists across three consecutive goal turns: the 2026 validation (`411eb52`), later-price/reference work (`d1cb010`), and this actual current-market check. The investigated historical sources cannot restore original quote identity/timing; the checked current source has no first-score offers. There is no live process to wait on and no outstanding internal implementation needed to execute the next bounded capture. Further repetition of the completed checks cannot resolve those missing facts.

Research is now blocked on **new qualified historical prices, or newly posted first-score markets that can be captured and independently verified**. Reaching that condition does not establish an edge; it enables further testing. Keep existing results and gates unchanged. Do not restart polling solely because the goal continues, or relabel main-line odds as first-score data. Scheduled work remains paused.
