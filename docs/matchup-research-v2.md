# MLB pitcher arsenal and lineup research v2

Written 2026-09-08. This is a source-feasibility audit and proposed experiment, not an implemented model or evidence of betting edge. The workload model's failed experiment remains unchanged. Its inspected 2024–2025 outcomes cannot become a fresh holdout for this proposal.

## Hypothesis and market

Test whether an opponent's particular pitch shapes and recent arsenal changes interact with the available hitters in ways that a game-level market misses. For example, a starter who recently increased a high-velocity, high-ride fastball may be a different matchup for a replacement-heavy lineup than his season pitching average suggests. Estimate a hitter's response to similar pitches across many pitchers; do not use tiny head-to-head batter/pitcher records.

The first market should remain FanDuel's two-way, full-game MLB moneyline because the repository already has event matching, settlement, paired probabilities and execution controls for that contract. Pitcher strikeouts or first-five markets would be more directly connected to the mechanism, but they require their own verified free FanDuel price archive and rules. Full-game moneyline prices cannot backtest those markets.

The proposed process observes lineup publication and changes, recalculates the interaction with the currently listed starters, then acquires a fresh paired FanDuel quote. This is a test of both player matchup information and the market's reaction to new lineups. It cannot be simulated using an untimestamped opener paired with the final batting order.

## Sources actually checked

The machine-readable [source audit](../reports/matchup-source-audit.json) retains request and receipt times, URLs, response sizes and SHA-256 hashes. Raw responses are cached locally under the ignored `data/raw/matchup-source-audit/`; no subscription, key or new dependency was used. Endpoint access is verified only for these samples, not guaranteed for a full season or sustained polling.

| Check | Observed result |
| --- | --- |
| [Current pregame feed, game 823092](https://statsapi.mlb.com/api/v1.1/game/823092/feed/live) | Received 2026-09-08 23:12:13 UTC, before the scheduled 2026-09-09 01:40 UTC start. Status was `Preview` / `Pre-Game`; both teams had nine batting-order IDs and listed starters. There were zero pitch events. |
| [2024 final pitch feed, game 746817](https://statsapi.mlb.com/api/v1.1/game/746817/feed/live) | 277 pitch events, each containing `pitchData`. This game ended early due to rain; it is a schema sample, not an eligible model test event. |
| [2026 final pitch feed, game 823415](https://statsapi.mlb.com/api/v1.1/game/823415/feed/live) | 227 pitch events, each containing `pitchData`; a sampled ball in play also contained exit velocity and launch angle. |
| [Historical timecodes, game 746817](https://statsapi.mlb.com/api/v1.1/game/746817/feed/live/timestamps) | 448 codes, beginning at `20240401_145353`, earlier than the scheduled 18:10 UTC start. |
| [Feed at that first historical timecode](https://statsapi.mlb.com/api/v1.1/game/746817/feed/live?timecode=20240401_145353) | Matching metadata timestamp, pregame status, zero pitches, and nine-player lineups **but also final attendance, 149-minute game duration and 64-minute delay duration**. The response mixes historical and final fields. |
| [Single-game Savant CSV request](https://baseballsavant.mlb.com/statcast_search/csv?all=true&type=details&game_pk=746817&game_date_gt=2024-04-01&game_date_lt=2024-04-01) | HTTP 403. Automated CSV acquisition from this environment is unverified. Do not claim that a Statcast download has succeeded. |

The historical timecode result is especially important. A matching `metaData.timeStamp` does not certify the entire response as an untouched archive. Its lineups may be correct, but this sample does not prove when they became public. Historical lineup-based game-price results must therefore remain exploratory unless field-level vintage behavior is independently established. Our own pregame acquisition time supplies direct prospective availability evidence.

The official [Savant CSV documentation](https://baseballsavant.mlb.com/csv-docs) lists pitch shape, batter/pitcher IDs, handedness, event outcomes and trajectory fields. It also documents a 2026 measurement change: plate locations move from the front to the middle of the plate, and strike-zone bounds become ABS-defined. A location model must explicitly handle this change. The [official swing-path leaderboard](https://baseballsavant.mlb.com/leaderboard/bat-tracking/swing-path-attack-angle) describes bat tracking coverage beginning in the second half of 2023. Swing geometry is a possible later extension; its automated extraction and historical completeness were not verified here.

## Exact initial input contract

Use the official MLB game feed as the initial pitch source. A source-specific adapter must preserve raw units and names until conversions have been checked; similar names are not sufficient proof of equivalence with Savant.

| Role | MLB JSON path / extraction |
| --- | --- |
| Game identity and scheduled start | `gamePk`, `gameData.datetime.dateTime`, `gameData.datetime.officialDate`, `gameData.teams.{home,away}.id` |
| Current starter identities | `gameData.probablePitchers.{home,away}.id`, only from our own pregame snapshots |
| Current ordered lineup | `liveData.boxscore.teams.{home,away}.battingOrder`; validate nine unique IDs and corresponding `players.ID{id}.battingOrder` slots |
| Roster/hand metadata | `gameData.players.ID{id}` and current boxscore player identity/status fields; do not treat current full-season team membership as historical membership |
| Pitcher, batter, hands | `liveData.plays.allPlays[].matchup.{pitcher.id,batter.id,pitchHand.code,batSide.code}` |
| Pitch event key | Game ID plus `allPlays[].atBatIndex` plus `playEvents[].index`; retain `playId` and `pitchNumber` for checks |
| Time and event type | `playEvents[].startTime`, `endTime`, `isPitch`, `details.type.code`, `details.call.code` |
| Velocity and movement | `pitchData.startSpeed`, `coordinates.{pfxX,pfxZ}`, `breaks.{breakVerticalInduced,breakHorizontal,spinRate,spinDirection}`, `extension` |
| Trajectory for a later geometry extension | `pitchData.coordinates.{x0,y0,z0,vX0,vY0,vZ0,aX,aY,aZ}`; `x0/z0` here are coordinates near the reported `y0=50`, not verified release positions |
| Location for diagnostics, not initial cross-era fitting | `pitchData.coordinates.{pX,pZ}`, `strikeZoneTop`, `strikeZoneBottom`; 2026 sample also contains `strikeZoneWidth/Depth` |
| Pitch and PA response labels | `playEvents[].details` and parent `allPlays[].result.eventType`; use pitch calls for contact/whiff and the PA result only once per completed PA |
| Batted-ball observations | `playEvents[].hitData.{launchSpeed,launchAngle,trajectory}` when present; missing tracking is not an out or zero exit velocity |

`playEvents[].count` is the count **after** that event in the sampled feed. The first 2024 foul has strikes equal to one. Reconstruct pre-pitch count by replaying every event in order, including automatic balls/strikes and non-pitch actions. Never silently treat it as the Savant pre-pitch count.

Store every acquisition in an append-only manifest with `requested_at`, `received_at`, source URL, SHA-256, parser version, source geometry version, and normalized IDs. Do not train on `seasonStats`, hot/cold-zone summaries, game duration, attendance, actual current-game pitches or final lineup substitutions. Final feeds are acceptable for past pitch history and outcome labels after their availability cutoff, subject to unarchived correction risk.

## Proposed model, specified before new outcome inspection

The primary target remains `home_win`; the final probability uses the existing `ResidualLogistic` market offset:

`logit(p_home) = logit(p_market_no_vig) + intercept + beta * X`.

Build the new inputs from pitch-level representations, using these fixed engineering choices for an initial implementation:

1. **Pitch shapes.** Fit 12 standardized shape clusters on development pitches using velocity, the two source-native movement coordinates and extension, with throwing hand made consistent and a fixed random seed. Fit scaling and centers only on training data. Keep pitch-type codes for diagnostics. Do not refit clusters on validation or test pitches. Spin and location are diagnostic fields initially, avoiding several extra feature families before basic feasibility is known.
2. **Batter response.** For each batter, batting side and shape cluster, estimate whiffs per swing and hard contact per tracked ball in play using the preceding 365 days. Shrink toward the corresponding league hand/shape rate using 200 prior swings and 100 prior tracked balls in play. Hard contact means measured exit velocity at least 95 mph; do not classify missing tracking. Classify swing calls explicitly, distinguish foul tips and bunts, and publish excluded-call counts. Switch hitters have separate batting-side profiles. No batter/pitcher pair parameter is fitted.
3. **Starter arsenal.** Estimate shape-cluster mix versus each batting side from the prior 365 days, with a 200-pitch league hand prior. Estimate a second mix from the previous three starts with the long-window distribution as a 200-pitch prior. Only previous completed appearances can update either mix; yesterday is the latest permitted game date for the initial version. New pitches and poor tracking increase uncertainty rather than being silently zeroed.
4. **Matchup interaction.** For each hitter, weight his shrunk shape-specific whiff and hard-contact deviations by the opposing starter's projected cluster mix. Subtract that hitter's score against the league cluster mix for the same pitcher hand. This subtraction isolates the opponent-specific interaction from generic hitter quality. Aggregate over the lineup with equal weights for the initial version, then calculate home offense minus away offense. Also calculate the change caused by using the recent rather than long-window starter mix.
5. **Lineup information.** Save an expected-lineup distribution before first observing a complete current lineup, using only prior starts against the currently listed starter's hand and an observed active roster. Compare its matchup score with the first observed complete lineup score. A later replacement creates a new immutable version. Never infer the expectation by removing an inconvenient hitter from the final lineup. If no prior expectation was captured, the lineup-change feature is missing and that experiment is ineligible.

The first pitch-only candidate uses four new home-minus-away features: matchup whiff interaction, matchup hard-contact interaction, and the recent-arsenal change in each. A separately registered prospective lineup-change candidate adds the two corresponding lineup-surprise features. Use observed starter and lineup IDs; unknown starter, incomplete order or insufficient capture history blocks lineup-based eligibility. Do not replace them with the actual eventual starter or actual batters faced.

Keep market-only, calibration-only, the frozen workload model and the new pitch candidate in the report. A generic lineup-quality control is needed before attributing improvement specifically to interactions. Fit all normalization on training rows. Select regularization using validation log loss from the existing fixed grid, not ROI or a profitable subgroup. Freeze representation, shrinkage, lookbacks, candidate set and thresholds before a fresh forward cohort; expanding them consumes a new experiment.

This design does not claim that clustering or shrinkage creates an edge. It tests a specific source of additional information with adequate pooling. A later approach-angle/swing-path model would need its own preregistered extension, reliable swing data, coordinate validation and a new cohort.

## Minimum data and chronology

**Prototype minimum:** two complete prior regular seasons of pitch feeds, with the first providing warm-up and the second development/validation; enough earlier games to give established hitters a 365-day profile. Estimate transfer size from cached game bytes before a broad download. Download schedules first, then final eligible feeds with a resumable manifest and at most two concurrent requests. Audit a fixed set of dates across parks and years before scaling. The two successful game samples do not establish season-wide completeness.

At minimum audit unique event keys, pitch-call taxonomy, plausible velocities, observed tracking coverage by team/date, traded-player assignment, two-way players, postseason exclusions, doubleheaders, rescheduled games, and replayed counts. Include final-game pitch-count reconciliation. Warm-up and rookie profiles may use league priors, with explicit coverage features; they are not observed player skill. Use a minimum 200 historical tracked pitches for each projected starter and 100 historical swings for at least seven hitters per side as an initial eligibility rule. These are engineering choices, not power calculations.

**Historical development:** all already inspected 2021–2025 game-price outcomes are development evidence for this new idea. Chronological pitch-response checks can establish whether the representation predicts future pitch outcomes, but that alone is not a betting result. Historical final lineups can be used for a plainly labeled conditional-on-actual-lineup diagnostic, never for a claim about an available opening quote. Historic timecode lineups remain unverified vintages as described above.

**Fresh evaluation:** the cohort starts after implementation, model freeze, collector validation and a recorded start timestamp. Predictions require both an immutable model/input hash and a paired FanDuel quote acquired after the inputs. For the first implementation, use a single fixed decision per event: the first complete eligible snapshot within 120 to 15 minutes of scheduled start. Record every event and every exclusion. Later lineup changes may generate diagnostic forecasts but do not change that event's selected paper bet. This prevents selecting the most favorable of many quotes after seeing results.

For lineup-driven latency research, capture game feeds every two minutes in that window, save only changes plus heartbeat observations, and acquire quotes after an input change. A 15-minute scheduled workflow cannot resolve two-minute reactions; measure the actual achievable delay before testing a latency hypothesis. A collector's HTTP receipt time is the observable timestamp; an event time or unchanged feed metadata timestamp is not a verified lineup-publication time.

Follow the existing fixed stake, 3% EV threshold, price/overround limits, execution haircut and weekly dependence-aware uncertainty calculation. Measure selected-bet ROI, chosen-side entry-price EV at paired no-vig closing probability, and paired all-event out-of-sample log loss against the entry and closing markets. Retain bets lacking a valid close and report coverage. Do not relabel the last stored quote as closing unless it is independently verified prestart and sufficiently close to start. Follow the existing promotion gate of at least 1,000 settled paper bets across 90 days and positive lower confidence bounds at fixed checkpoints. This is a minimum evidence gate, not a guarantee of adequate power or success.

## Repository integration and completion status

`beating.features.build_features` currently accepts lagged game/team history, and its daily `build_live_snapshot` cache deliberately contains no lineups or starters. Reusing that immutable daily cache for changing lineups would be incorrect. Implement the pitch history and pregame observation collector separately, then join by official `game_pk` into a versioned feature artifact. `ResidualLogistic` and `Monitor` can support the final game-probability and paper-evaluation layer. `beating.predict` already accepts explicit event-matched feature snapshots, but v2 must additionally bind starter/lineup version, observation timestamp and all raw source hashes to each forecast.

Verified now: free official pitch fields in two eras, a current pregame lineup source, and a concrete historical timecode leakage trap. Unfinished: season coverage audit, pitch and lineup parsers, source-unit validation, collectors, model training, meaningful chronology tests, game-level backtest and a new prospective cohort. No profitable model, CLV advantage, notification trigger or promotion is established by this document.
