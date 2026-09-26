# Distinct retained-price candidate: NHL relative short rest

**One distinct candidate has enough retained prices for a small exploratory falsification test: player shots on goal under unequal team rest.** Its proposed observable feature is `x = own_short_rest − opponent_short_rest`, where short rest means the team's previous scheduled regular-season UTC start was less than 36 hours earlier. This definition was proposed once, before any outcome comparison; no cutoff grid, effect estimate or model fit was run.

The proposed causal pathway is reduced recovery and preparation time changing shot opportunity. Whether any effect survives FanDuel's existing adjustment is unknown. This changes conditional shot opportunity; it is distinct from the closed dispersion, consensus, power-play-goal and goal-contract models, and from the empty-net and NBA overtime routes being reviewed separately. No corresponding rest card was found in the bounded local ledger/search review.

| Metadata cohort | Paired offers | Games | Informative offers | Informative games |
| --- | ---: | ---: | ---: | ---: |
| Before January 1, 2025 UTC | 1,282 | 145 | 230 | 27 |
| January 1 onward | 1,110 | 124 | 246 | 28 |
| Total | 2,392 | 269 | **476** | **55** |

There are 229 offers for the short-rest team against a rested opponent, and 247 for the reverse exposure. Observed short gaps span 22–31.5 hours. All **2,392 price pairs were independently matched exactly to their original FanDuel shots nodes** in 269 retained JSON files, including player, line and update time; decimal-price error is zero. The [JSON evidence](nhl-short-rest-price-feasibility-2026-09-26.json) records source hashes and projected columns.

Coverage uses only identifiers/prices from the existing shot preparation, independently retained schedule metadata, and prior-team identifiers from the closed goal preparation. No target boxes, forecast probabilities, EVs, selections or results were read. The latter metadata join leaves 1,027 shot rows unmatched; this is a feasibility subset, not a proposed final eligibility rule. A new declaration should independently define prior-team membership for the full shot-price cohort.

A minimal forecast test could separately declare `logit(pUnder) = logit(qUnder) + beta*x`, with one nonnegative coefficient and fixed regularization, calibrated only on early games and compared with the actual paired market on later games. It would preserve fixed price/selection gates and a zero-correction/no-selection stopping rule. This is a recommendation, not a new declaration or permission to retune an old model.

The limitation is substantial: 476 rows contain only 55 informative game clusters and 28 later games. That permits cheap falsification, not a strong confirmation claim. Player participation on the previous night is unverified, schedules are retrospective, rest may already be fully priced, and all archive outcomes were previously inspected under other models. Any promising result would remain exploratory and need independent validation. No edge, fitted correction or expected bet count is established.
