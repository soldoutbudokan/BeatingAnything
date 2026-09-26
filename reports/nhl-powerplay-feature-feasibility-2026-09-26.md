# NHL prior power-play feature feasibility — September 26, 2026

**The proposed features are available, but goalie shot fields require denominator parsing and 13 prior team-games fail consistency checks.** No model was fitted, and no candidate-game goal outcomes were inspected.

Inspection was restricted to completed regular-season games with independent scheduled UTC starts before November 23, 2024. This yields 1,626 games: all 1,312 from 2023–24 and 314 from early 2024–25. The added [2023–24 schedule](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_schedules/nhl_schedule_2024.csv) was projected to metadata before use; raw bytes, projection and receipt remain under `data/raw/nhl-shot-archive-2026-09-26/powerplay-feature-audit/`.

## Field semantics and aggregation

The [publisher's NHL parser](https://raw.githubusercontent.com/sportsdataverse/fastRhockey/0b68f439d8645b119d54e49fc30be78c94ba9610/R/nhl_game_boxscore.R) defines skater `power_play_goals` as an integer count and goalie `power_play_shots_against` as a **saves/total** string. For example, `8/10` means ten opponent power-play shots and eight saves. Use the denominator. The combined player table joins skaters and goalies; blank goalie positions matched roster position `G` with zero mismatches. These fields describe opponent power plays, not shots faced while the goalie's own team has the advantage.

Among 58,524 prior skater rows, goals and power-play goals have no missing values; zero remains a valid observed count. There are no duplicate game/player rows. The 6,503 goalie rows have no missing power-play split strings; 3,047 are unused backups with zero time and zero counts. **Sum all appearing goalies, including replacements, rather than only the starter.** There are 204 team-games with two appearing goalies. One Pittsburgh team-game lists just one goalie, who played 60 minutes; do not require exactly two listed goalies.

Do not replace missing or malformed splits with zero. Reject a whole team-game if any listed goalie has invalid nonnegative integer splits, saves exceeding shots, malformed time, incompatible split/total counts, shots minus saves inconsistent with goals against, or positive counters at zero ice time. Require at least one appearing goalie. Do not require 60 minutes of combined goalie time: 1,545 team-games fall below that because goalie absence is possible.

## A concrete source defect

Thirteen prior goalie rows have strength-split shot-minus-save counts inconsistent with goals against: nine even-strength and four power-play. All split numerators and denominators nevertheless reconcile to the corresponding total string, so that check alone misses the defect. Exclude the affected team-games uniformly; do not repair their counts from results.

The NHL report records Ullmark allowing three goals on 35 shots. [Official summary](https://www.nhl.com/scores/htmlreports/20232024/GS020518.HTM). The retained publisher row has 35 shots, 33 saves and three goals against, an internal inconsistency. Kuemper's NHL report records three goals on 22 shots and an empty-net goal separately. [Official summary](https://www.nhl.com/scores/htmlreports/20242025/GS020218.HTM).

## Usable priors and coverage

| Quantity | 2023–24 regular season | Early 2024–25 before cutoff |
| --- | ---: | ---: |
| Skater goals / power-play goals | 8,085 / 1,660 | 1,908 / 383 |
| Valid team-games after goalie checks | 2,613 | 626 |
| Rejected team-games | 11 | 2 |
| Goalie-observed PP shots | 11,907 | 2,657 |
| PP shots per valid team-game | 4.556831 | 4.244409 |

A prior-season league power-play goal share is `rho = 1660/8085 = 0.2053184910`. The comparable quality-filtered goalie-observed shot baseline is `m = 11907/2613 = 4.5568312285`. Both precede the quoted archive. Among 738 skaters appearing in the early 2024–25 window, 600 have at least 40 prior regular-season appearances and 424 have at least 80. Utah has 19 prior games in this cutoff; do not silently borrow Arizona history to pass a minimum.

After rejecting inconsistent goalie groups, nine team-games still have one more opponent skater PP goal than goalie-observed PP goals. This is compatible with omitted empty-net events but was not classified event by event. The feature therefore measures **goalie-observed PP shots per game**, not complete team PP shots, penalty-kill time or penalty opportunities.

## Chronology and proposed probability arithmetic

Use independent schedule `game_time + 72h <= entry` for the history buffer, joining by game ID. Boxscore `game_date` is local; adding 72 hours to its midnight is not the same condition. The independent schedules agree with regular-season ID component `02`; playoff rows were excluded and no preseason or all-star rows entered this cohort. Latest prior player-team membership can be used without target participation, but can be stale around trades or absences.

For a **0.5-goal line only**, `qUnder**((1-r)+r*R)` is algebraically consistent with independent Poisson scoring components: infer total intensity from the market zero-goal probability and scale the estimated PP component by the opponent factor. It preserves the market when `R=1`. It assumes historical PP goal share represents current role and opponent PP shots scale the player's PP goal intensity. Both are unverified forecasting assumptions, and the market may already price that matchup. Do not apply the formula unchanged to higher goal lines.

These are retrospective published statistics, not proof of contemporaneous availability or corrections. Forecasting superiority, actual goal-market terms, price advantage and returns remain untested. The adjacent JSON preserves source hashes, rejected game IDs, full coverage and quality counts. Existing frozen experiments were not modified.
