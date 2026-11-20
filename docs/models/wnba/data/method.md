# WNBA bottom-up projection model — method

A possession-level Monte Carlo model of WNBA games built only from public play-by-play (ESPN via the
sportsdataverse/wehoop parquet files, 2017–2026) and ESPN's public roster endpoint. Its goal is the most
accurate projection we can build from public data. It is **not** fitted to betting prices. Prices are used only to score it: the
ESPN-listed spread in the walk-forward test (§11) and Kalshi game-winner markets in the process test (§12). All numbers below are in `diagnostics.json` / `meta.json`; this file explains what they mean.

Rebuild everything: `python -m models.wnba.run_all` (each step caches; `--force` rebuilds, `--from STEP`
rebuilds from a step, `--refresh` re-downloads the current season and rosters).

---

## 1. Data and parsing (`parse_pbp.py`)
* Seasons 2017–2026, regular season + playoffs, all-star / exhibition teams excluded. ~2,440 games,
  ~380k possessions, ~333k field-goal attempts. 2026 is complete (last game 2026-10-29).
* Fixes applied to the raw files: older seasons (2017–2021) record made free throws with
  `score_value = 0` and clear-path FTs under a different type label; three-point attempts are derived
  from text/shot distance where the `points_attempted` column is missing (99.9% agreement on 2026).
* **Lineups.** Starters come from the box score; substitutions are applied event by event. At each
  period start the five on court are inferred from who acts (or is subbed out) before being subbed in.
  When a player acts while not on court she is inserted, removing the teammate whose next appearance is
  a sub-in or furthest away. Reconciliation: share of player-games whose reconstructed minutes are within
  1 minute of the box score is ~99% in most seasons (95–97% in 2018–19); ~99.9% of possessions have
  five known players per side (see `meta.lineup_recon`).
* **Possessions** are runs of one team's offensive events (FGA, non-technical FT, turnover, live
  rebound); offensive rebounds continue the possession. The lineup credited is the one on court at the
  possession's first event (so FTs after a mid-trip substitution go to the earlier lineup). Technical FTs
  are excluded from possession points. Dead-ball rebounds after a non-final FT are ignored. The margin at
  the start of a possession is the score before its first event (ESPN's score columns are the score *after*
  each event; the first build used them directly, which added a made first shot or free throw to the
  offence's lead on 26% of possessions).
* **Shots** are classified into five zones from ESPN coordinates (hoop at raw (25, 0)): rim < 4 ft,
  short mid 4–14 ft, long mid ≥ 14 ft twos, corner three (≤ 9 ft above the hoop line), above-the-break three.

## 2. Shot-quality model (`shot_model.py`)
Gradient-boosted classifier for make probability (xFG) on distance, angle, x/y, three-point flag, shot
family (layup, dunk, tip, hook, floater, pull-up, step-back, fade, bank, alley-oop, jumper), put-back flag,
seconds left in the period and season. Cross-fitted by game (5 folds) so every shot's xFG comes from a
model that never saw that game. Expected points = xFG × shot value.
* **Shot making** = points above expected per shot (recency-weighted, half-life 1 season, shrunk with
  150 pseudo-shots). **Shot selection** = expected points per shot minus league average.
* **Defensive shot quality**: ridge regressions on every FGA of the defensive five's effect on expected
  points (`def_xpts_allowed`) and on make-over-expected (`def_making_allowed`).

## 3. Player impact: prior-informed RAPM (`rapm.py`)
Possession-level ridge regression, points × 100:
`y = season intercept + home + Σ O(offence five) − Σ D(defence five)`. D > 0 means better defence.
Weights decay with "season time" (each off-season counts as a quarter season) with half-life H, and
garbage time (|margin| ≥ 20 in Q4/OT) gets half weight.
1. **Long-run RAPM** (slow decay, all seasons) gives targets for the box prior.
2. **Statistical plus-minus (SPM) prior**: weighted ridge of long-run O and D on per-100 features
   (points, FGA by zone, FTA, assists, turnovers, ORB%, DRB%, steals, blocks, fouls, shot making,
   assisted share, minutes per game). Features are shrunk toward the population mean with 250 pseudo-
   possessions; fringe players with no information get 8 mpg. Weighted R² ≈ 0.68 (O), 0.40 (D).
3. **Prior-informed RAPM**: the same ridge, but shrinking toward the SPM prediction (built from
   recency-weighted features) instead of toward zero. This is the `impact.O / impact.D` used everywhere.
4. Tuning by forward holdout (train on all seasons before S, score every possession of S, for S =
   2024, 2025, 2026): data half-life **H = 1.0 season**, feature half-life **1.0**, prior strength
   **λ = 6000**; plain RAPM H = 1.5, λ = 1500. All four sit inside their grids. In each fold the SPM
   coefficients are also fitted only on data before the fold's cut-off; the first build fitted them on all
   seasons, which let the test season leak into its own forecast and overstated the gain (MSE 13,794
   reported, 13,798 without the leak; plain RAPM 13,803, constant 13,832). Prior-informed RAPM still beats
   plain RAPM out of sample. The ridge penalty of the long-run RAPM that the SPM is trained on is fixed at
   1500: a heavier one compresses the prior and every rating built on it.
5. Ratings are re-centred so the 2026 possession-weighted mean O and D are 0 (league average = 0).
6. Uncertainty: posterior SD from the ridge (residual variance × (X'WX + λ)^-1). Typical rotation
   player ≈ ±1.3 per 100 on each end.
7. **Four-factor RAPM** (both ends, ridge toward 0, same weights): turnovers per possession, FT trips per
   possession, ORB per rebound chance (weighted by chances), eFG per FGA (shot level), plus expected
   points and make-over-expected per FGA (shot quality created / allowed).

## 4. Skill projections (`skills.py`) — DARKO-style
For every rate the simulator needs (`players.json → rates`; list in `schema.md`):
`p = (Σ w·num + k·p0) / (Σ w·den + k)`, with exponential decay `w = 0.5^(Δt/H)`, a group prior (position,
or position × role tier <12 / 12–24 / 24+ minutes per game — chosen per rate by the holdout; role tiers won
only for turnovers, fouls, short-mid and long-mid shot share and long-mid FG%)
`p0` (recency-weighted G/F/C mean before the cut-off) and an **age adjustment** in logit space from a
delta-method age curve (season-over-season changes of players with known birth dates, linear in age,
capped at ±0.4 logit and scaled by the data share of the estimate). H and k are tuned separately for each
rate on forward holdouts (cut-offs at the start and middle of 2024, 2025, 2026; predict the next half
season; binomial deviance). Examples of the tuned values: usage H = 0.5 seasons / k = 50 possessions;
turnovers 2 / 100; 3P% above the break 8 / 320 attempts (threes are noisy, so heavy regression);
shot-zone mix 0.5–1 / 6–12 FGA (shot diet is stable and player-specific); steals 4 / 800 possessions.
The holdout deviance gain over the position prior is 0.1–7% depending on the rate
(`diagnostics.skills_holdout`). `rates.<r>.sd` is the posterior SD.

**Usage strength.** Observed usage is measured next to real teammates, so the simulator does not use
`u_i / Σu` directly (that double-penalises stars who share the floor with other stars). A context-free
strength `usg_w` is fitted so that, over the actual 2025–26 lineups, each player's simulated share of
plays reproduces her projected usage.

## 5. Minutes and rotation (`minutes.py`)
`role_min` = decayed (half-life 6 games) mean minutes in 2026 games played for her current team;
`avail` = decayed share of healthy team games played (coach's-decision DNPs count against, injury DNPs
do not). Default rotation minutes = `c · (role_min · avail)^γ`, capped at 38 and summing to 200, with γ the
smallest value in [1, 2] that keeps the team's top three at ≥ 95% of their role minutes (when everyone
is healthy, bench minutes inflated by injuries are squeezed first). Starters = top five by recent start
rate (≥ 1 guard, ≤ 2 centres). Game-to-game minute SD from the player's history, shrunk to 5.5.
`teams.top_lineups_2026` lists who actually played together.

## 6. Team strength, pace, context
* **Bottom-up ratings**: `ORtg = lg + Σ (min/40)·O`, `DRtg = lg − Σ (min/40)·D`; lg = 2026 league
  points per 100 possessions (110.0). Removing a player and re-allocating minutes changes the rating.
* **Pace**: ridge of first-play seconds on the ten players (offensive and defensive pace terms), plus a
  2026 team (coach/system) residual shrunk with 800 pseudo-possessions. The league first-play time is
  then calibrated so simulated possessions match the 2026 league rate (78.8 per team).
* **Home court, rest, travel** (`context.py`): game-margin regression with ridge team-season strengths
  (2017–26): home court +1.62 ± 0.28 points (the team-season ridge absorbs part of it; the raw home
  margin outside the 2020 bubble is +2.13). The 2020 season was played in one building, so its games are
  neutral with no travel; the first build treated ESPN's nominal home teams as hosts. The simulator uses
  the possession-level RAPM home coefficient (2.63 per 100 × 78.8 possessions ≈ **+2.07** points), because
  re-simulating 2025–26 with the game-level value under-shot the real home win rate.
  Back-to-back −1.44 ± 1.14, extra rest day +0.29 ± 0.27,
  travel −1.25 ± 0.60 per 1,000 miles from the previous game city (time-zone change was not
  significant and has the wrong sign, so it is not used). Effects are shrunk by t²/(1+t²) before use and
  split equally between the two teams' offensive targets.

## 7. Simulator (`sim.py`, `sim.js` — identical algorithm)
* **Minutes per sim**: target = projection × a mean-preserving log-normal factor (SD = the player's
  game-to-game SD, limited near the 40-minute ceiling), rescaled to 200. Round 2 fixed a bias here: the old
  truncated-normal draw plus an indiscriminate fatigue rule and aggressive bench-emptying cost 36-minute
  players ~2.5 minutes a game and gave deep-bench players ~1 extra; realised minutes now match targets
  within ~0.5 min at every level (calibration slope 1.01).
* **Rotation**: game split into 2-minute segments (OT: 2 × 2.5 min). At each segment start each coach
  picks five by "need to play" (remaining target minutes / remaining time), with starters forced at the
  start of each half, top-minute closers in a close game's last 4 minutes and in OT, a fatigue penalty
  after three straight segments (scaled down for high-minute players: zero at 40 target minutes),
  ≤ 2 centres and ≥ 1 guard, and bench-emptying in blowouts (Q4: 22+ with 5 min left, or 17+ with 2.5 min
  left; projected minutes already include real blowouts, so this is deliberately mild).
* **Lineup calibration (impact anchoring)**: for each offence five vs defence five the target points per
  possession is `(lg + ΣO − ΣD + context)/100`. Turnover and FT-trip probabilities start from the
  offensive players' projected rates and are moved by the **defenders' four-factor RAPM** (forced
  turnovers, fouls committed); the offensive-rebound chance is `ΣORB / (ΣORB + ΣDRB)` of the ten players.
  A common logit shift on every make probability is then solved (Newton) so that the analytic expected
  points per possession equals the target. So box-score rates decide *who* does what, and the
  RAPM blend decides *how efficient* the lineup is (capturing defence and off-ball value).
* **Possession**: first-play time ~ Gamma(3) around the lineup's pace; each play: user by usage strength
  among the five; outcome turnover / shooting-foul trip (2 or 3 FTs) / FGA; zone by the shooter's mix;
  make by calibrated zone probability; and-ones; assists (shooter's assisted share × zone, assister by
  assist rate); blocks on misses (defenders' block rates × league zone block rate); rebound contest
  (team ORB chance, individual credit by ORB/DRB rates, team rebounds at the league share); offensive
  rebound → new play (~6 s). Steals by defenders' steal rates; possessions after steals are faster.
  Technical FTs at the league rate.
* **Late game**: last 2 minutes of Q4/OT — the leader milks the clock (~21 s), the trailer hurries (~9 s)
  and shoots more threes when down 3+. Two end-game behaviours are set from 2017–26 Q4/OT possessions: an
  offence down 3–6 that starts inside 24 s takes 65–88% of its shots from three (three-zone weights × 8), and
  a tied or trailing offence that starts inside 12 s scores 0.58–0.74 points per possession against ~1.05
  normally (make probabilities × 0.65). Together they moved one-point games from 4.4% to 3.4% of simulated
  games (real 3.4%) and overtime from 2.8% to 3.2% (real 4.1%). **Intentional fouls** come from an empirical table
  (`sim.late_foul_table`): the probability that the trailing defence fouls at the start of a possession, by
  the offence's lead (1–15) and seconds left (≤15, 30, 45, 60, 90), measured on 2017–26 play-by-play as
  quick FT-only possessions minus the background rate of such possessions when the offence is not ahead,
  smoothed across neighbouring leads. E.g. up 1 with ≤15 s ≈ 90%, up 4 with ≤15 s ≈ 92%, up 1 with 15–30 s ≈ 59%,
  up 1 with 30–45 s ≈ 0, up 10 with 15–30 s ≈ 20%, up 13+ ≈ 0 (the first build, with the lead measured after
  the first free throw, had 67% for up 1 with ≤15 s). Fouls give 2 FTs to an offensive player weighted by usage × FT%. This replaced a hard
  "trailing by 1–9 in the last 45 s" rule that put artificial mass on 10-point margins. OT: 5-minute periods
  until decided (max 6).
* **Shared game-level shocks** (same draw for both teams in a simulated game), sized from data
  (`game_effects.py`, `diagnostics.game_effects`): re-simulating 2026 games with the shocks off, the two
  teams' residual points per possession (real − simulated mean) still covary more in real games
  (cov 0.0033 vs 0.0020 within simulations, corr 0.21): officiating, conditions, shooting nights. The
  excess sets an efficiency shock with SD ≈ 4.1 per 100 possessions added to both offensive targets.
  The FTA residuals covary the same way, giving a "whistle" shock (SD ≈ 0.15 on the log FT-trip rate,
  composition only — the efficiency solve keeps points per possession on target). A shared pace shock
  was estimated too, but real possession residuals are *less* variable than the simulator's own
  within-game possession variance, so its SD is 0.
* **Score effect**: every make probability is multiplied by `1 − 0.0025 × (lead − expected lead)`
  (capped at ±25), where the expected lead is the analytic expected final margin × elapsed time / 40 min. Independent possessions give a within-game margin SD of ~15–16 points, far above what real
  games show (the residual SD of a team-strength model is 11.8); real games mean-revert (leaders relax,
  trailers press). The coefficient was tuned so re-simulated 2026 games reproduce the real margin SD.
  It cannot be estimated directly from possession data because leading teams are also better teams.
  Pulling toward the expected trajectory (not toward a tie) keeps expected margins intact: the round-1
  version pulled toward 0 and compressed projected margins (out-of-sample margin slope 1.12 → 0.98 now).
* **Outputs**: win probability, margin and total (mean, SD, quantiles, full histogram), team points,
  quarter and half lines, and per-player minutes, points, rebounds, assists, threes, steals, blocks,
  turnovers, PRA/PR/PA (mean, SD, quantiles, P(over) ladders, double-double probability). All player
  lines come from the same simulated games as the team scores, so they are correlated correctly.
* `sim.js` re-implements the same algorithm for the browser (seeded RNG); `models/wnba/parity_check.js`
  verifies means, SDs and win probabilities agree within Monte-Carlo error.

## 8. Player value (`value.py`)
* Replacement level = minutes-weighted mean total impact of players ranked 166th+ in 2026 minutes
  (outside ~11 per team). `varp100 = O + D − replacement`.
* Season value: `varp_pts = varp100/100 × on-court possessions` (projected minutes, 44 games);
  `varp_wins = varp_pts / points-per-win` (slope of team wins on season point differential, 2017–26).
* Minutes re-allocation (`reallocate`, identical in sim.js): each teammate can absorb at most
  `min(38 − m, 1 + 8·(1 − m/38))` extra minutes (a 34-minute star ~2, a 10-minute backup ~7, deep bench ~9),
  water-filled in proportion to that headroom ×3 for the same position group. Round 1 handed minutes out
  pro rata to minutes (mostly to stars), which made removing some positive players *improve* their team.
  No fatigue cost for the extra minutes is modelled.
* Game impact: remove the player, re-allocate minutes, recompute the team's ratings; `winp_delta` uses a
  normal approximation with the simulator's margin SD vs a league-average opponent on a neutral floor.

## 9. Column glossary
See `schema.md` for every field. Key ones: `impact.O/D/total` (per 100, prior-informed RAPM),
`impact.*_rapm` (data only), `impact.*_prior` (box prior only), `four_factor.*`, `shot_quality.*`,
`rates.*` (projected skills), `minutes.*`, `value.*`, `pct.*` (percentiles among rotation players).

## 10. Weaknesses and shortcuts (read before trusting a number)
* **Public PBP only.** No tracking data, no shot-clock, no defender distance; "shot quality" knows only
  location and shot type. Defensive ratings remain the noisiest piece (SPM R² for D ≈ 0.4).
* **RAPM is noisy** for low-minute players and collinear for players who always share the floor
  (posterior SD ≈ 1.3 per 100 for regulars, more for fringe players). The prior mitigates but does not
  remove this. Players never seen in the data get a fringe-player prior.
* **Possessions vs sim plays**: the possession definition (ORB continues possession) and lineup credit
  at the first event are standard but imperfect around FT trips with substitutions.
* **Off-season rosters.** A player's team is her last 2026 team if she is still on an ESPN roster;
  players missing from their last team's ESPN roster (waived, released, expired hardship deals: 24 players)
  are free agents with no default minutes. The first build kept them, which gave e.g. New York 19 and
  Toronto 16 default minutes a game to players no longer there. Connecticut has no ESPN roster or team-list
  entry, so its roster is everyone who appeared for it in 2026. ESPN's injury flags are not used. Free
  agency, expansion and the draft are not reflected. Ages for players without an ESPN birth date are imputed.
* **Minutes model** is a heuristic, not a fitted rotation model; foul trouble and injuries within a game
  are not simulated. Lineups change only on a 2-minute grid.
* **Calibration lever**: the efficiency gap between box composition and RAPM is closed by a common
  make-probability shift; defensive four-factor RAPM moves turnovers and FT trips, but zone-specific
  defence (e.g. rim protection lowering rim FG% specifically) is not modelled separately.
* **Score effect is a tuned fudge**, not a structural model of end-game behaviour.
* **Player projections are still slightly compressed**: in re-simulated games with actual minutes, actual
  points on simulated points has slope ≈ 1.06 in-sample and ≈ 1.10 out-of-sample. The upper half of
  the projection deciles is within ~1–5%, but low-minute players are over-projected (bottom deciles 10–40%,
  under 1–2 points in absolute terms). Out-of-sample FTA is the worst stat (slope 1.17). Checked and
  ruled out: shooting-foul shrinkage, technical/and-one/bonus FT assignment, and the lineup make-shift (simulated
  efficiency within ±1% of projection at every usage level). Skill projections are tuned rate by rate on
  binomial deviance, which is dominated by high-volume players. See `player_calibration_*`.
* **Scoring environment**: forward projections assume the **2026 league environment** (110.0 points per 100
  possessions, 78.8 possessions per team, 2026 FT rate, ~173.5 total points per game). 2026 scored ~10
  points a game more than 2017–25; to project another environment, scale `league.ortg`/pace accordingly.
  The 2025 rows in the diagnostics are simulated in the 2026 environment; use `season_2026` as the headline.
* **Context effects** (rest, travel) are small, estimated with large standard errors, and shrunk.
* **Age curves** come from players with known birth dates (survivor bias) and are applied only in
  proportion to the data share of each estimate.
* **Diagnostics are calibration checks, not backtests**: the 2025–26 re-simulation uses end-of-2026
  parameters (in-sample). The out-of-sample checks are the forward holdouts of the skill projections and
  RAPM, the 2026 team-rating test fitted only on 2017–25 data, and the 2026 walk-forward (§11). Even
  those are not pure: hyper-parameters were tuned on 2024–26 holdouts, and the out-of-sample player
  calibration keeps the full-sample four-factor defence, pace terms and league constants.
* **Overtime is under-produced**: 3.2% of simulated 2026 games against 4.1% of real games (2017–26).
* **No backtest of the minutes model.** The default rotation is a heuristic that has never been scored
  against the minutes players went on to play.
* No market data were used to fit anything.

## 11. Walk-forward test and the market yardstick
`diagnostics.team_ratings_walkforward_2026`: ratings refitted ten times through 2026 (about every 2.5 weeks)
on data before each cut-off, predicting the next block of games from bottom-up ratings and home court.
Minutes shares are either those actually played or, knowable before tip-off, each active player's decayed
minutes from her earlier games.

| forecast of the home margin, 353 games | RMSE | corr. | slope | winner |
|---|---|---|---|---|
| ESPN-listed spread | 12.61 | 0.49 | 0.95 | 70.0% |
| refitted ratings, earlier minutes | 12.84 | 0.46 | 1.06 | 68.6% |
| refitted ratings, actual minutes | 12.85 | 0.46 | 1.05 | 67.7% |
| pre-season ratings, earlier minutes | 13.06 | 0.43 | 1.04 | 65.2% |
| home court only | 14.48 | – | – | 55.2% |

The spread is the listed line in ESPN's play-by-play feed (real values in 2026 only; earlier files carry a
placeholder). The model is told who was active; the spread also reflects injuries, rest and news. Regressing
the real margin on both gives 0.80 × spread + 0.19 × model: the model adds little beyond the line.
Across 2024–26 the walk-forward RMSE is 12.47 and its slope is 0.99–1.06.

## 12. Process test against Kalshi (`kalshi.py`, `process.py`, `snapshot.py`)
What gets tested against a market is a process, not a model: at decision time T we know some things, project
a lineup from them, the lineup and the ratings give a forecast, and the forecast misses. `process.py` replays
that chain for all 649 games with a Kalshi game-winner market (May 2025 to October 2026) and keeps each link
(`data/markets/wnba/process_ledger.csv.gz`, `process_lineups.csv.gz`, summary in `market_test.json`).

**Prices.** `kalshi.py` reads public candlesticks and takes the home-team quote 24 h, 6 h, 1 h and 10 min
before the ESPN tip and at tip (Kalshi's own close is the end of the game). Books are one cent wide from an
hour out. Median volume per game was 0.1m contracts in 2025 and 1.3m in 2026.

**Information tiers** for the lineup:
* `box`: box scores of games finished by T, nothing else. P(active) depends on how many of the team's latest
  games the player missed, with rates from earlier seasons. The only tier that is point-in-time for past
  seasons, because no injury-report archive exists for them.
* `oracle_active`: told who played; minutes shares still from earlier games. What perfect availability news
  would be worth.
* `oracle_minutes`: told the minutes played. A ceiling, not a process.
* `news`: box + an availability report captured before T. Empty until `snapshot.py` has run through a season.

Ratings are the walk-forward RAPM of §11. Win probability is a normal with SD 12.5 around the bottom-up margin.

| home-win log loss | n | box only | told who played | Kalshi |
|---|---|---|---|---|
| 2025, 24 h before tip | 267 | 0.620 | 0.607 | 0.652 |
| 2025, at tip | 297 | 0.609 | 0.597 | 0.608 |
| 2026, 24 h before tip | 350 | 0.613 | 0.598 | 0.592 |
| 2026, at tip | 350 | 0.613 | 0.598 | 0.582 |

* In 2026 the market beats the box-only process by 0.031 at tip (95% interval 0.011 to 0.052). Being told who
  played closes about half of that (0.016 left, interval −0.004 to 0.035). The rest is the market having
  better ratings or other information.
* The 2025 market was thin and no better than the box-only process. Flat bets against it at a 3-cent edge
  show a profit, but the books would not have filled much; 2026 is the regime that matters, and there the
  same bets lose 12–15% of stake (intervals include zero).
* Lineup error an hour before tip: 9% of projected minutes went to players who did not play; 2% of real
  minutes went to players projected for under a minute. Not knowing who plays adds 4.4 points² to a margin
  MSE of 170. The lineup changes the projected margin by 1.7 points (SD) a game.
* The market's move over the last day correlates 0.26 with the gap between our told-who-played and box-only
  forecasts: part of what it learns is the availability we lack.

**Forward capture.** `snapshot.py capture` stores ESPN injuries, transactions, rosters and schedule with
every open Kalshi WNBA market and Polymarket event under one UTC stamp. `snapshot.py freeze` appends, for
each game within 36 h, the box and news lineups, their forecasts and the Kalshi quote to
`forecast_ledger.csv`. Grading reads only that ledger. The status-to-probability map (Out 0, Doubtful 0.1,
Questionable 0.5, Day-To-Day 0.7, Probable 0.9) is a placeholder until a season of captures measures it.

**Limits.** Hyper-parameters were tuned on 2024–26 holdouts. Home court and the 12.5 SD are full-sample
constants. Ratings are refitted every 2.5 weeks, not daily. Player props are captured going forward only. The 2026 Finals Game 7 (Oct 31) is
missing from the play-by-play source and from every number here.

## 13. Model test against Kalshi: win, spread, total (`market_test.py`)
News set aside: each team's active list is who appeared, minutes from earlier games. The full simulator runs
2,000 times per game with ratings, skills, usage and the league scoring environment (points per 100 and pace,
half-life a quarter season) refitted on data before one of ten cut-offs a season. Scored at the last quote
before tip. Summary in `market_model_test.json`; forecasts in `data/markets/wnba/sim_forecasts.csv.gz`.

| 2026, 352 games | markets | model log loss | Kalshi log loss | gap (95% interval) | weight on model in a blend | flat-bet return |
|---|---|---|---|---|---|---|
| game winner | 352 | 0.597 | 0.582 | 0.016 (−0.004 to 0.036) | 0.18 | −11% (−27 to +5) |
| spread, all strikes | 3,153 | 0.565 | 0.555 | 0.010 (−0.005 to 0.024) | 0.24 | −3% (−15 to +9) |
| total, all strikes | 2,669 | 0.624 | 0.613 | 0.010 (−0.009 to 0.028) | 0.33 | +2% (−9 to +14) |

* As a point forecast the market's central spread has RMSE 12.66 against the model's 12.81 (correlation
  0.92; regressing the margin on both gives 0.69 × market + 0.31 × model). For totals 18.63 against 18.97.
* The model is behind on all three by a similar, small amount, and no gap is distinguishable from zero on
  one season. Nor is any bet return. This is the model with a perfect active list, so a real process does worse.
* Totals ran 2.9 points under in 2026 because the scoring environment rose through the year and the
  trailing estimate lagged it; the market's line was 1.4 under.
* 2025 game winners (297 games, thin books): model 0.599, Kalshi 0.608. Spread and total markets start in 2026.
* Still full-sample: four-factor defence, pace terms, home court, shock sizes, score effect, hyper-parameters.

**Player props** ("Player: N+ stat", 2026, same simulations, last quote before tip; books about 3 cents wide):

| stat | markets | players | model log loss | Kalshi log loss | gap (95% interval) | weight on model in a blend | flat-bet return |
|---|---|---|---|---|---|---|---|
| points | 4,981 | 88 | 0.566 | 0.557 | 0.008 (0.001 to 0.016) | 0.45 | +2.3% (−1.6 to +6.3) |
| rebounds | 3,184 | 64 | 0.601 | 0.592 | 0.009 (−0.001 to 0.019) | 0.36 | +1.5% (−3.5 to +6.7) |
| threes | 2,439 | 60 | 0.642 | 0.629 | 0.012 (0.004 to 0.021) | 0.12 | −3.6% (−10.2 to +2.0) |
| assists | 1,330 | 47 | 0.722 | 0.693 | 0.029 (0.013 to 0.046) | 0.21 | −1.8% (−7.4 to +4.2) |

* Behind the price on all four, and the gap is distinguishable from zero for points, threes and assists.
  No bet return is.
* The model is low on the players who have markets: 0.76 points, 0.33 assists, 0.12 rebounds and 0.07 threes
  a game under what they produced. In every price band from 20 to 80 cents the model's probability sits 2–7
  points under the market's, and the market is the one closer to what happened. This is the compression
  already listed in §10 (actual on projected points slope 1.10) plus the lagging scoring environment.
* Points is where the model adds most to the price (blend weight 0.45). Assists is the weakest stat.
* Prop markets exist only for regular rotation players, and void when the player does not appear.
