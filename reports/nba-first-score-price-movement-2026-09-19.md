# Later prices weaken the first-score lead

**The seven original selections do not beat margin-normalized later FanDuel prices.** Their average hypothetical EV against that reference is **−13.19%** after the existing winning-profit haircut. BetMGM still implies **+10.43%** on average. This leaves a persistent disagreement between bookmakers, not demonstrated convergence toward an independently supported fair price. The earlier +3.80-unit simulated return remains unchanged.

## One fixed comparison

The [diagnostic declaration](../docs/nba-first-score-price-movement-diagnostic-2026-09-19.md) was written after outcomes were known and before computing this comparison. All sixteen frozen forecast games are retained. The comparison time is exactly one minute before the same earlier verified scheduled start; no selection or original decision time changes. This is a later provider-price diagnostic, **not verified closing-line value**, and is not independent confirmation.

Both books retain the same complete ten-player sets in all sixteen games. All seven original selections remain active in the reconstructed FanDuel state. Five receive a new provider entry, but only four change numerical price. Three shorten, one lengthens, and three are unchanged. Mean raw price movement (`entry/later − 1`) is +2.73%; median is zero. Raw movement does not remove bookmaker margin.

| Original selection | Entry decimal | Later decimal | Raw price movement | Entry EV against normalized later FanDuel |
| --- | ---: | ---: | ---: | ---: |
| Donovan Clingan | 10.50 | 10.50 | 0.00% | −14.75% |
| RJ Barrett | 11.00 | 10.00 | +10.00% | −7.64% |
| Daniss Jenkins | 11.00 | 10.50 | +4.76% | −12.35% |
| Austin Reaves | 10.00 | 10.00 | 0.00% | −14.55% |
| Julian Champagnie | 12.00 | 11.00 | +9.09% | −7.68% |
| Kelly Oubre Jr. | 11.00 | 11.00 | 0.00% | −15.12% |
| Jayson Tatum | 10.00 | 10.50 | −4.76% | −20.26% |

The reference EV uses `p_later * (1 + .98*(entry_decimal−1)) − 1`. Every original selection remains in the denominator; there are no missing cases. All seven still have positive EV under the unchanged conversion applied to later BetMGM prices. Neither bookmaker's normalized probabilities are established truth.

Twelve FanDuel boards and five BetMGM boards receive at least one new entry between the two cutoffs. Three later FanDuel boards have all ten entries within 300 seconds; no BetMGM board does. Historical execution, feed completeness, original quote labels and jurisdiction remain unresolved. These scheduled-start cutoffs are not asserted to be the final tradable prices or actual tip-off times. [Full data and hashes](nba-first-score-price-movement-2026-09-19.json).

## Separate additional-book check

A [bounded price-only declaration](../docs/nba-first-score-reference-diagnostic-2026-09-19.md) requested the same sixteen fixtures at bet365, DraftKings and Pinnacle, using one targeted history call per fixture. It completed **16 calls: four HTTP 200 and twelve explicit no-history responses**. No account endpoint, upgrade or alternate bookmaker route was used.

- Bet365 and Pinnacle returned no first-scorer history in this sample. This is sample/account evidence, not proof of provider-wide absence.
- DraftKings returned four ten-player boards at the original decision. Two have the exact original candidate set, but neither has an original selection. The two games containing original selections have different candidate sets. Thus **zero of the seven original bets has a matching complete third-book board**.
- The regulator-hosted [DraftKings rulebook](https://massgaming.com/wp-content/uploads/DraftKings-House-Rules-8.18.25.pdf), implemented August 26, 2025, separately lists first-point and first-field-goal products (pages 42–43). Its free-throw distinction does not identify which product these normalized quotes represent. The pages were extracted and visually checked. No conversion or fair-EV assumption is assigned to DraftKings.
- The [bet365 rules](https://help.bet365.com/s/en/sportsrules/basketball) describe free throws counting in first basket, but the opened page redirects to its Brazil site. That page cannot establish the historical jurisdiction of the generic provider slug. No bet365 prices were returned anyway.

The [reference diagnostic](nba-first-score-reference-diagnostic-2026-09-19.json) retains all response hashes, literal available prices, candidate-set mismatches and source limitations. It does not recalculate outcomes, returns, or an optimized consensus.

## Remaining metadata route checked once

The provider's [current-odds documentation](https://oddspapi.io/en/docs/get-odds) exposes bookmaker market/outcome IDs, fixture links, a provider change clock and a nullable bookmaker change clock. A single read-only request for the first frozen fixture, requesting FanDuel/BetMGM/DraftKings with verbosity 3, returned HTTP 200 and completed-fixture metadata, **but no bookmaker odds**. The raw 889-byte body and receipt are retained under the reference acquisition's `metadata-check/` directory. It therefore cannot restore the historical market identity or quote clocks. No retry was made. A reported actual start later than the scheduled start does not change either frozen comparison cutoff.

## Consequence for the search

Confidence in the lead is lower than the profitable seven-bet result alone suggests. Keep the recorded positive results, but do not call the prices independently corroborated or claim a verified advantage. Further repetition of these histories will not supply original receipts or matching third-book boards.

The next useful evidence is a genuinely new archive with those fields or prospective paired captures with original market verification. The next NBA regular season starts **October 20, 2026**, according to the [official schedule](https://www.nba.com/news/2026-27-nba-regular-season-schedule); that establishes an upcoming collection opportunity, not posted first-scorer prices. No schedule or watch was enabled. All acquisition processes are finished. The overall goal remains incomplete.
