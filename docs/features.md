# MLB workload and travel reconstruction

The free official sources are the [MLB schedule API](https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2024&gameType=R&hydrate=probablePitcher,linescore,venue), [season pitcher index](https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season=2024&gameType=R&sportIds=1&playerPool=ALL&limit=2000), [individual pitcher game logs](https://statsapi.mlb.com/api/v1/people?personIds=664285&hydrate=stats(type=gameLog,group=pitching,season=2024)), and [venue coordinates and time zones](https://statsapi.mlb.com/api/v1/venues?venueIds=1,3,5340&hydrate=location,timezone). Downloading costs nothing and requires no key. Usage remains subject to MLB's terms returned in every response. Raw responses are cached; `source_manifest.json` records URLs, retrieval observation time, sizes, and SHA-256 hashes. Existing valid cached responses are not downloaded again.

```sh
python -m beating.mlb download --source-dir data/raw/mlb --years 2021 2022 2023 2024 2025
python -m beating.features --source-dir data/raw/mlb --output data/processed/mlb_features.csv
```

The downloader uses at most four concurrent requests by default, three attempts, a 120-second timeout, and atomic cache writes. It enumerates pitchers using the season index, then hydrates 50 pitcher game logs per batch, rather than requesting every box score. Existing full-season roster batches remain readable and are checked against the season index; missing or incomplete pitcher logs are repaired. The index is solely an enumeration/completeness source: its season totals are not predictors.

The initial roster-based download omitted 11 pitcher-seasons, including 2021 Blake Treinen and 2022/2023 Framber Valdez. Index-based repair added 299 appearances, producing 104,627 appearances with exactly one starter for each of 24,296 game-team pairs. This matters: seeing some relief pitchers for a game is insufficient proof that the starting pitcher or another reliever was captured. `pitching_coverage` checks exactly one starter and plausible total outs, and incomplete prior games are flagged. The source repair audit lists every supplemented pitcher-season.

Logs hydrated through a traded player's former and new teams overlap: deduplication uses `(gamePk, pitcherId)` and team assignment uses each appearance's actual `split.team.id`. Neither full-season roster membership nor season-index membership is a predictor. This avoids using future transactions to infer the active roster.

## Timing and exclusions

Features for a game on date D use records whose completion date is at most D−1. All games on the same date share the same cutoff, including doubleheaders. `--lag-days 2` provides an additional timing sensitivity test. Each output row records its cutoff and feature version. Current final scores, current probable starters, weather, final lineups, and API season-to-date records are excluded from predictors.

Historical sportsbook openers lack reliable quote timestamps. Yesterday's final results may have occurred after an archived opening price was first offered. These features therefore support an exploratory retrospective study, not a proven executable opening-price strategy. The future monitor must collect timestamped quotes and timestamped model inputs before a claim of real betting edge is possible.

MLB's `abstractGameState=Final` also labels postponed and cancelled schedule entries, sometimes with future rescheduled scores. The loader instead accepts detailed states `Final` or `Completed Early`, excludes `rescheduleDate` copies, and deduplicates by `gamePk`. Suspended games become available on their actual completion date, not their original `officialDate`. Their aggregate innings and pitches cannot be allocated to each day from these logs, so they are excluded from physical workload calculations and counted as missing workload. Evaluation should exclude suspended games themselves. Historical statistical corrections have no archived publication timestamp; reconstruction cannot eliminate that limitation.

Venue metadata is retrospective but consists of geographic coordinates and IANA time-zone names. Offsets are recalculated for the target date, including historical daylight saving rules. Missing coordinates or time zones produce `feature_travel_complete=False` for both games at that venue and later travel from it. Numeric distance is then zero as a placeholder; incomplete rows must be flagged or excluded from travel-model evaluation. A venue's current timezone offset is never reused for a historical date. No weather or future park factors enter the model.

## Feature definitions

All model inputs are home minus away. Separate home and away values are retained for audit. The exported lists `TRAVEL_FEATURES`, `BULLPEN_FEATURES`, and `FORM_FEATURES` permit fixed ablations. The construction constants below were engineering choices, not fitted to holdout results.

| Signal | Definition |
|---|---|
| Rest | Days since the last completed nonsuspended game, minus one, clipped to 0–7. |
| Travel | Great-circle kilometers from the last played venue to today's venue; resets after a gap above 14 days. This approximates travel and does not claim to know charter itineraries. |
| East/west | Positive and negative components of destination minus origin UTC offset, wrapped to ±12 hours. |
| Short-rest travel | Travel kilometers when the previous game was yesterday. |
| Schedule load | Games in the past 3/7 days; total game innings and innings beyond scheduled length in the past 3 days. Seven-inning doubleheaders use their scheduled length. |
| Relief pitch load | Actual pitches thrown by pitchers whose appearance had `gamesStarted=0`, over 1 and 3 days; plus relief outs over 3 days. |
| Relief availability | Distinct relievers used over 1 and 3 days, count used on both of the previous two days, and count with at least 40 pitches over 3 days. |
| Recent missing workload | Prior 3-day games whose pitcher logs lack exactly one starter or plausible innings coverage, or which have suspended-game timing ambiguity. |
| Relief quality | Prior 45-day relief K−BB divided by batters faced, with a 200-batter prior centered at 14%. |
| Team controls | Prior 28-day run differential per game shrunk by 20 scoreless prior games; pitching K−BB rate with a 300-batter prior at 14%. |

`bullpen_unavailable_quality` combines workload with demonstrated role. For each reliever with a prior 45-day appearance for the team:

1. Role weight is prior outs + 3 × saves + 2 × holds, normalized across relievers on that team.
2. Quality rate is `(14 + strikeouts − walks) / (100 + batters_faced)` over prior 45-day relief appearances. The quality multiplier is `clip(1 + 3 × (rate − 0.14), 0.5, 1.7)`.
3. Fatigue is `min(2, pitches_yesterday/25 + pitches_two_days_ago/60 + pitches_three_days_ago/100 + 0.35 × consecutive_day_use)`.
4. The feature sums role weight × quality multiplier × fatigue across relievers.

This is a continuous proxy for unavailable relief quality, not a medical fatigue estimate or an assertion that a manager will withhold a pitcher. Role weights are backward-looking and may retain recently traded or injured pitchers for 45 days; prospective roster/news monitoring should improve this. Starting pitchers' relief appearances count as relief on the day they occurred. No expected starter for today's game is inferred from the final record.

The first season starts without prior-year warm-up. Missing past activity therefore means zero observed workload and a prior-centered quality estimate, not proof that a team or pitcher had no workload. Spring training and postseason activity are outside this initial regular-season source set.

## Prospective snapshots

`build_features(..., target_games=[scheduled_game])` calculates features for a future target using only the separately supplied completed-game history. A future game needs no fake outcome or completion date and never enters result history.

`build_live_snapshot(source_dir, day)` downloads the current season into a date-specific directory and atomically saves `live-features.json`. Repeated calls reuse that immutable daily snapshot. It records its actual acquisition time as `feature_cutoff_at`, separately from the previous official-date cutoff. Yesterday's West Coast game can finish today in UTC, so a guessed previous-day UTC timestamp would misstate input availability. Collect a quote after the snapshot is available. The model has no same-day lineup or starter input, so fixed daily historical features can be reused with later quotes.

Live records expose `input_data_complete` and reasons. Missing venue metadata, incomplete recent pitching history, suspended recent games, and doubleheader targets block eligibility. The downstream quote collector must also reject started games and stale or unverified prices. The snapshot does not itself send bet notifications.

Before creating a daily cache, an uncached official schedule check verifies that all games in the prior three calendar days are final, completed early, postponed, or cancelled. An active late-night game, pending game, or suspension raises a retryable error before any daily files are created. A later attempt therefore fetches fresh state. This prevents an early run from freezing missing West Coast workload for the rest of the day. The conservative guard blocks the whole snapshot while a recent suspension is unresolved.
