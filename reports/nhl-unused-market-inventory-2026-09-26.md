# Other retained NHL market availability — September 26, 2026

The 285 raw files were rechecked against their pinned hashes without reading sporting outcomes. Literal FanDuel market keys and payload counts are:

| Market | Event payloads | Outcome rows |
| --- | ---: | ---: |
| Anytime goalscorer | 273 | 9,378 |
| Goals Over/Under | 272 | 5,652 |
| Shots Over/Under | 272 | 7,168 |
| Alternate shots | 190 | 9,881 |
| First goalscorer | 36 | 1,188 |
| Last goalscorer | 36 | 1,314 |

There are no FanDuel goalie-saves, power-play-points or team-total nodes in this retained source. Those models would need a different price source; existing player boxscore fields alone cannot supply a priced test.

First and last scorer coverage runs November27–December10,2024 UTC. The 36 paired boards contain1,188 common runners, but only157 have equal first/last prices. Their complete runner sets differ. These are price distinctions, not evidence of correct probabilities, identical settlements or an edge; neither market was fitted or graded. Small and irregular coverage would limit an independent validation claim. Counts here precede fixture/player/debug exclusions.

The [JSON inventory](nhl-unused-market-inventory-2026-09-26.json) records the manifest hash and every first/last event, clock and count. The separate [goal-contract screen](nhl-goal-contract-screen-2026-09-26.md) evaluates the actual paired goal/Anytime overlap under its own prior declaration. No other new market comparison, result, wager or schedule was produced by this inventory.
