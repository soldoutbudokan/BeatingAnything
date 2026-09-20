# OddsPapi follow-up: historical first-scorer prices found

**Both FanDuel and BetMGM return real first-scorer histories in the fixed May and June samples. The missing March props did not establish a provider-wide gap. This is source availability, not a demonstrated betting edge.**

[Structured report and acquisition receipts](nba-first-basket-oddspapi-followup-2026-09-19.json). The [original March negative](nba-first-basket-oddspapi-coverage-2026-09-19.md) remains valid for those fixtures.

## New access evidence

The user supplied account screenshots showing basketball access, pregame access and Player Props enabled for both FanDuel and BetMGM; Live was disabled. Screenshot copies and hashes are retained locally under ignored raw data. No plan was changed and no upgrade was made. The previously denied account endpoint was not revisited.

## Fixed later-date sample

The [follow-up declaration](../docs/first-basket-oddspapi-followup-plan-2026-09-19.md) selected one NBA fixture from each April, May and June window by start and ID, without filtering on prices, outcomes or availability. All three selections were written before any historical query.

| Fixture and scheduled UTC start | FanDuel active pregame first-scorer IDs | BetMGM active pregame first-scorer IDs |
| --- | ---: | ---: |
| Cleveland Cavaliers vs Washington Wizards, 2026-04-12T22:00:00.000Z | 0 | 10 |
| Cleveland Cavaliers vs Detroit Pistons, 2026-05-12T00:00:00.000Z | 10 | 10 |
| San Antonio Spurs vs New York Knicks, 2026-06-04T00:30:00.000Z | 8 | 8 |

The provider market is `112604`, Player First Point; its Yes outcome has the same ID. April has other FanDuel player props but lacks this first-scorer market. May has 618 FanDuel history entries (594 active pregame) and 168 BetMGM entries (148 active pregame). June has 777 FanDuel entries (744 active pregame) and 16 BetMGM entries (eight active pregame). These are timeline entries, not independent bets or games.

## June response size and recovery

The initial full-market June query returned HTTP 200 but exceeded the existing 32 MiB limit; its body was discarded and the run stopped. The receipt hash is of the discarded cap-plus-one prefix, not the full response. A [separate one-call recovery declaration](../docs/first-basket-oddspapi-june-size-recovery-2026-09-19.md) kept the same fixture and books and restricted the request to outcome `112604`. That response completed within the same size limit and supplies the June counts above. The original failure remains recorded.

The follow-up used seven read-only calls: three fixture calls and four historical calls including the oversized response. Under the [quota documentation](https://oddspapi.io/en/docs/requests-and-quota), three count toward the monthly allowance. The market catalog was reused with SHA-256 verification; all six retained response bodies also match their receipts.

## Pregame source-state diagnostic

A local diagnostic reconstructed the last reported state at five minutes before scheduled start, using only entries no later than that cutoff. It found ten matching active player IDs at both books in May and eight in June. The diagnostic cutoff was chosen after reading coverage and is not a frozen betting-selection rule.

In May, provider-entry ages at that cutoff range from 22.821 to 2,118.271 seconds for FanDuel and 1,045.322 to 47,870.614 seconds for BetMGM. These may be last-change clocks; do not equate them with bookmaker quote freshness or assume an unchanged quote was re-observed. In June, inverse-price sums over the eight retained players are below one at both books, which is a completeness warning, not evidence of an executable arbitrage.

## What this unblocks—and what remains

The account has now returned the desired historical market for both books without a plan change. Before replication, verify player names/starters, independent fixture identity, how the provider records changes and removals, whether histories capture complete offered boards, and each bookmaker’s contemporaneous first-point/first-field-goal settlement rules. The normalized label cannot establish those rules.

The earlier Card 42 protocol excludes playoffs. The late-season examples must not silently expand that cohort, relax its ten-runner requirement or retune the already-inspected model. Determine the available regular-season coverage or write a distinct, explicit declaration with appropriate interpretation before outcomes. No target outcomes, forecasts or strategy returns were computed in this source check. No messages were sent to third parties. Schedules remain paused.
