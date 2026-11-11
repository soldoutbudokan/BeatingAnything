# WNBA bottom-up projection model — method

A possession-level Monte Carlo model of WNBA games built only from public play-by-play (ESPN via the
sportsdataverse/wehoop parquet files, 2017–2026) and ESPN's public roster endpoint. Its goal is the most
accurate projection we can build from public data. It is **not** fitted to, or tested against, betting
prices. All numbers below are in `diagnostics.json` / `meta.json`; this file explains what they mean.

Rebuild everything: `python -m models.wnba.run_all` (each step caches; `--force` rebuilds, `--from STEP`
rebuilds from a step, `--refresh` re-downloads the current season and rosters).

---

## 1. Data and parsing (`parse_pbp.py`)
* Seasons 2017–2026, regular season + playoffs, all-star / exhibition teams excluded. ~2,440 games,
  ~380k possessions, ~333k field-goal attempts. 2026 is complete (Finals ended 2026-10-31).
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
  are excluded from possession points. Dead-ball rebounds after a non-final FT are ignored.
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
   **λ = 6000**; plain RAPM λ = 1500. Prior-informed RAPM beats plain RAPM out of sample.
5. Ratings are re-centred so the 2026 possession-weighted mean O and D are 0 (league average = 0).
6. Uncertainty: posterior SD from the ridge (residual variance × (X'WX + λ)^-1). Typical rotation
   player ≈ ±1.3 per 100 on each end.
7. **Four-factor RAPM** (both ends, ridge toward 0, same weights): turnovers per possession, FT trips per
   possession, ORB per rebound chance (weighted by chances), eFG per FGA (shot level), plus expected
   points and make-over-expected per FGA (shot quality created / allowed).

## 4. Skill projections (`skills.py`) — DARKO-style
For every rate the simulator needs (`players.json → rates`; list in `schema.md`):
`p = (Σ w·num + k·p0) / (Σ w·den + k)`, with exponential decay `w = 0.5^(Δt/H)`, a position-group prior
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
  (2017–26): home court +1.53 ± 0.27 points (the team-season ridge absorbs part of it; the raw home
  margin is +2.03). The simulator uses the possession-level RAPM home coefficient (2.58 per 100 × 78.8
  possessions ≈ **+2.03** points), because re-simulating 2025–26 with 1.53 under-shot the real home win
  rate. Back-to-back −1.46 ± 1.14, extra rest day +0.29 ± 0.26,
  travel −1.28 ± 0.58 per 1,000 miles from the previous game city (time-zone change was not
  significant and has the wrong sign, so it is not used). Effects are shrunk by t²/(1+t²) before use and
  split equally between the two teams' offensive targets.

## 7. Simulator (`sim.py`, `sim.js` — identical algorithm)
* **Minutes per sim**: target ~ N(projection, sd) truncated to [0, 40], rescaled to 200.
* **Rotation**: game split into 2-minute segments (OT: 2 × 2.5 min). At each segment start each coach
  picks five by "need to play" (remaining target minutes / remaining time), with starters forced at the
  start of each half, top-minute closers in a close game's last 4 minutes and in OT, a fatigue penalty
  after three straight segments, ≤ 2 centres and ≥ 1 guard, and bench-emptying in blowouts (Q4: 20+ with
  6 min left, or 15+ with 3 min left).
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
  and shoots more threes when down 3+; in the last 45 s a team trailing by 1–9 fouls (2 FTs, shooter
  weighted toward good FT shooters). OT: 5-minute periods until decided (max 6).
* **Score effect**: every make probability is multiplied by `1 − 0.0025 × lead` (offence's lead, capped
  at ±25). Independent possessions give a within-game margin SD of ~15–16 points, far above what real
  games show (the residual SD of a team-strength model is 11.8); real games mean-revert (leaders relax,
  trailers press). The coefficient was tuned so re-simulated 2026 games reproduce the real margin SD.
  It cannot be estimated directly from possession data because leading teams are also better teams.
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
* **Off-season rosters.** Rosters are each player's last 2026 team (the ESPN off-season roster endpoint
  is incomplete; Connecticut has no current ESPN roster or team-list entry). Free agency, the 2027
  expansion and draft are not reflected. Ages for players without an ESPN birth date are imputed.
* **Minutes model** is a heuristic, not a fitted rotation model; foul trouble and injuries within a game
  are not simulated. Lineups change only on a 2-minute grid.
* **Calibration lever**: the efficiency gap between box composition and RAPM is closed by a common
  make-probability shift; defensive four-factor RAPM moves turnovers and FT trips, but zone-specific
  defence (e.g. rim protection lowering rim FG% specifically) is not modelled separately.
* **Score effect is a tuned fudge**, not a structural model of end-game behaviour.
* **High-usage stars score ~5–8% below their 2026 output** when 2025–26 games are re-simulated with their
  actual minutes (mostly fewer FT trips and slightly fewer shots: rates are regressed toward position
  priors and the usage model spreads plays). See `diagnostics.star_scoring_by_player`.
* **Context effects** (rest, travel) are small, estimated with large standard errors, and shrunk.
* **Age curves** come from players with known birth dates (survivor bias) and are applied only in
  proportion to the data share of each estimate.
* **Diagnostics are calibration checks, not backtests**: the 2025–26 re-simulation uses end-of-2026
  parameters (in-sample). The genuinely out-of-sample checks are the forward holdouts of the skill
  projections and RAPM and the 2026 team-rating test fitted only on 2017–25 data.
* No market data were used anywhere.
