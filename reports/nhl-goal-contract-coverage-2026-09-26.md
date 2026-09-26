# NHL goal-contract price coverage — 2026-09-26

**Yes: 15 literal common-player offers have a higher Anytime Yes price at exactly the same market-update timestamp**, across 3 events. This is a quoted-price discrepancy, not evidence of an executable edge or confirmed historical payoff equivalence.

| Clock cohort | Offers | Events | Equal prices | Anytime higher | Anytime lower |
| --- | ---: | ---: | ---: | ---: | ---: |
| All common offers | 2,826 | 272 | 2,791 | 30 | 5 |
| Exact equal market clocks | 2,657 | 255 | 2,638 | 15 | 4 |
| Unequal market clocks | 169 | 17 | 153 | 15 | 1 |

The 285 source files contain 12 publisher error payloads, 273 FanDuel Anytime markets and 272 paired goal markets. All 2,826 complete goal-0.5 pairs have an exact same-description Anytime Yes counterpart. The raw labels are 2,826 Over, 2,826 Under and 9,378 Anytime Yes; no Anytime No is present. The Anytime-only event is Anaheim–Vegas, December 4, 2024. There are 6,517 additional Anytime names within events containing both markets, plus 35 in that event.

Matching requires the same raw event, bookmaker, literal player description, and complete unique Over/Under 0.5 pair. No aliases, roster identities, participation, or outcome-based filtering are used. All compared prices pass finite American-price validation. Both update clocks precede the provider start by at most 72 hours for every common offer; independent fixture starts were not reread. This full price inventory includes the original debug fixture and differs from the model cohort.

Unequal clocks occur in 17 events/169 offers; Anytime is always later, by 2–195 seconds. The JSON preserves every event's clocks and all 35 non-equal offers. Exact-equal-clock price-difference histogram (decimal return, Anytime minus goal Over): `[{"anytime_minus_over_decimal":-0.1,"offers":1},{"anytime_minus_over_decimal":-0.05,"offers":3},{"anytime_minus_over_decimal":0.0,"offers":2638},{"anytime_minus_over_decimal":0.05,"offers":2},{"anytime_minus_over_decimal":0.1,"offers":12},{"anytime_minus_over_decimal":0.4,"offers":1}]`.

| Event / source filename | Exact-clock higher offers | Exact-clock lower offers |
| --- | ---: | ---: |
| `icehockey_nhl_player_props_Boston Bruins_Buffalo Sabres_20241221.json` | 0 | 3 |
| `icehockey_nhl_player_props_Boston Bruins_Colorado Avalanche_20250125.json` | 9 | 0 |
| `icehockey_nhl_player_props_Minnesota Wild_Vegas Golden Knights_20241215.json` | 1 | 0 |
| `icehockey_nhl_player_props_New York Islanders_Carolina Hurricanes_20250125.json` | 0 | 1 |
| `icehockey_nhl_player_props_Washington Capitals_New York Rangers_20250104.json` | 5 | 0 |

Examples below illustrate source offers without selecting a betting threshold:

| Player / source event | Goal Over 0.5 | Anytime Yes | Equal UTC update |
| --- | ---: | ---: | --- |
| Ross Colton / Colorado Avalanche at Boston Bruins | +290 | +300 | 2025-01-25T16:16:23+00:00 |
| Brad Marchand / Buffalo Sabres at Boston Bruins | +200 | +195 | 2024-12-21T13:47:50+00:00 |

The [Odds API market list](https://the-odds-api.com/sports-odds-data/betting-markets.html) identifies these separate NHL keys as Goals (Over/Under) and Anytime Goal Scorer (Yes/No). No displayed update date; checked September 26, 2026. It does not certify historical operator settlement.

The [FanDuel Ontario document dated July 30, 2026](https://d38ayms4az88sz.cloudfront.net/SB/ON/2026-07-30T12-50-49.html) §§22.1/22.5 includes regulation and overtime in NHL player propositions unless expressly restricted, excludes shootout statistics unless specified, and voids full-game player bets for zero time on ice. These are generic player-proposition rules; the hockey section does not explicitly map the two API keys. The current rules and names are consistent with a shared goal event under ordinary full-game mapping, but historical 2024–25 terms, jurisdiction and market exceptions remain unverified. Soccer Anytime rules from other sections were not applied.

Equal provider clocks do not prove an atomic capture, accepted wager, availability, limits or persistent discrepancy. There is no Anytime No side here. No sporting outcomes/features, forecast, fair probability, EV, selection, settlement or return was read or computed. Only the two linked primary URLs were reviewed.

All 285 file hashes and sizes match the retained manifest (SHA-256 `869d4a6ddfd1473ece6e59a3aed023cedb6899b988fdb5cb6ede29c7b37552da`). The [JSON companion](nhl-goal-contract-coverage-2026-09-26.json) contains all source pins, distinct price inventories, exact deltas, non-equal offer details, and canonical comparison hash `c78973771fea35a9fadbb6aff6c04b3bdbff1e1e216f4f6855521e3807c98b26`. Source commit: `42cf1f81bc302642ddcc9e88ce2e98c1057bc74d`.
