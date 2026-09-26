# NHL power-play exposure and goal props — September 26, 2026

**The fixed model produces 2,672 forecasts and no qualifying bets.** Every offered side has negative modeled EV after costs; the best is **−2.71%**. The predeclared zero-selection rule closes this exact specification without target grading. This does not measure its forecasting accuracy or establish an edge.

## Declared mechanism and usable data

The [card](../docs/hypotheses/hockey-powerplay-goal-exposure.md), [runner](../tools/explore_nhl_powerplay_goals.py) and source audits were committed in `ad13ec4` before combining power-play features with prices. This is a new mechanism within an already inspected archive, separate from the closed shot-dispersion and cross-book tests.

The hypothesis was that a power-play-dependent scorer's goal price might underreact to an opponent's power-play shots conceded. The model decomposes market-implied scoring intensity into a smoothed historical power-play share and its remaining component, then scales only the first by opponent exposure. Both player share and opponent exposure are pulled toward fixed 2023–24 league averages. There are no fitted target-label coefficients, threshold searches or optimized shrinkage strengths. The central risk is double-counting matchup information already in the market.

The [price audit](nhl-powerplay-goals-coverage-2026-09-26.md) finds 2,768 paired FanDuel goal-0.5 offers across 270 games after fixed identity, fixture, margin and quote-clock gates. Both sides must exist in one market node; market update is within 72 hours before the earlier independent/source start. The original debug game and unresolved names remain excluded. No eventual-participation filter selects a forecast.

The [prior-data audit](nhl-powerplay-feature-feasibility-2026-09-26.md) exposed two important parsing details before forecasting: goalie positions are blank in combined boxes, and power-play shots-against strings represent **saves/shots**, not a single count. Blank positions are normalized only after their NHL IDs match roster goalie roles. All appearing goalies, including replacements, contribute the denominator; validated zero-minute backups contribute zero. Every strength split must reconcile with total shots, saves and goals against. An inconsistent row excludes the whole team-game, not just an inconvenient component.

The completed 2023–24 baseline has 8,085 skater goals, including 1,660 power-play goals: `rho=0.205318491`. Eleven inconsistent goalie team-games are excluded, leaving 2,613 valid groups with 11,907 goalie-observed power-play shots: `m=4.556831228`. These baselines are computed independently by both audit and runner and agree exactly.

## Forecast rule and result

Each player uses at most 80 prior positive-ice-time appearances, requiring 40. The latest prior team identifies the opponent within the known fixture; target boxes never establish membership. The opponent uses up to 40 prior valid team-games, requiring 20. Arizona and Utah remain separate. Every contributing game's **independent UTC start plus 72 hours** must strictly precede entry; local date-midnight is not substituted. Current game IDs are excluded explicitly, and completed regular-season schedule metadata is required.

The fixed equations are:

```
r = (player_PP_goals + 10*rho) / (player_goals + 10)
R = (opponent_PP_shots + 40*m) / ((opponent_games + 40)*m)
p_under = q_under ** ((1-r) + r*R)
```

Here q is the proportional paired market probability of zero goals. The ten-goal and forty-game priors are declared conservative heuristics. The transformation assumes independent Poisson scoring components; it does not recover the bookmaker's actual model. It applies only to the 0.5-goal line.

| Measure | All | Before January 1 UTC | January onward |
| --- | ---: | ---: | ---: |
| Forecasts | 2,672 | 1,445 | 1,227 |
| Games | 270 | 146 | 124 |
| Qualifying selections | 0 | 0 | 0 |
| Best modeled EV after costs | −2.708% | −2.708% | −3.692% |

Ninety-two price rows lack 40 prior player appearances; four lack 20 prior opponent games. No prior regular-season game is missing independent schedule metadata. Across history needed through the latest entry, 21 inconsistent goalie team-games are excluded under the fixed checks. All 270 price-cohort games retain at least one forecast.

The smoothed opponent multiplier ranges from 0.7908 to 1.1721. After applying each player's power-play share, total goal-intensity scales range from 0.9164 to 1.0562. Under probabilities change by **−1.77 to +2.04 percentage points**. None of those adjustments overcomes the offered prices and 2% winnings haircut, even before demanding the fixed +3% entry threshold. The highest EV also satisfies the declared decimal-odds range 1.20–6.00.

All forecasts and source hashes were [frozen](nhl-powerplay-goals-freeze-2026-09-26.json) at `2026-09-26T21:36:48.859074+00:00` and committed in `f9f4783`. No target grading followed; scoring loss and ROI remain undefined. Earlier candidate-game results can enter subsequent forecasts only as strictly prior history, so this is not a claim that every candidate's raw outcome remained unread throughout feature generation. The January split is a chronological diagnostic, not an independent holdout.

The [independent forecast audit](nhl-powerplay-goals-forecast-audit-2026-09-26.json) verifies 300 hash records and reproduces all 2,672 probabilities and 5,344 EVs within 1.11e−16. It independently recomputes declared prior player/opponent aggregates, league baselines and all 21 rejected groups. All 317,582 history references pass the strict clock and current-game exclusions; the minimum prior-start lead is 82.29 hours. Its scope does not separately prove last-window completeness or excluded-cohort attrition. See the [machine-readable result](nhl-powerplay-goals-2026-09-26.json).

Raw price entries, forecasts, prior-game IDs, rejected team-games and freeze remain under `data/raw/nhl-powerplay-goals-2026-09-26/`. Existing outputs cannot be overwritten; the grading phase refuses to run when zero bets qualify. Synthetic checks cover probability arithmetic, history boundaries, goalie aggregation, selection and unresolved return bounds. All 312 repository tests pass.

## Limits and disposition

Goalie-observed shots omit empty-net exposure and combine penalty frequency with shot suppression. Historical power-play goal share is a smoothed role proxy, especially for low-scoring players. Retrospective statistics and schedules do not certify original publication vintage; market-update fields do not establish contemporaneous receipt or accepted prices. Exact historical jurisdiction and goal-prop participation/settlement terms remain unverified.

Close this fixed priced specification without changing priors, history windows, team mapping, sign or subgroup. Its negative modeled EV is not evidence that all hockey matchup effects are perfectly priced. No wager, notification or scheduled collection was enabled.
