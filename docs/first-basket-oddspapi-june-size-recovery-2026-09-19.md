# Targeted June history recovery

Declared after the fixed later-date probe stopped on its third history response, and before this narrower query.

The June fixture was selected and saved before any historical prices: `id1100013270505022`, San Antonio Spurs–New York Knicks, June 4 at 00:30 UTC. Its full FanDuel/BetMGM history returned HTTP 200 but exceeded the local 32 MiB cap; only the cap-plus-one prefix hash/length and acquisition receipt survive. No June price coverage has been inferred from that partial response. Earlier April and May responses were retained, and May contains the target market at both books.

Make **one additional read-only historical call** for the same June fixture and same two books with `outcomeId=112604`, the saved catalog's Yes outcome for Player First Point. Keep the existing size cap, cooldown and credential handling. Do not substitute another fixture, change the market, request another endpoint or retry after an error. This is a narrower source query prompted by response size, not an access-control workaround or a change to fixture selection. The historical call is documented as quota-exempt.

The original full-response failure remains recorded. No account endpoint, outcomes/settlements, forecasts or strategy returns are requested. Actual coverage still requires identity, clock and settlement checks before model evaluation.
