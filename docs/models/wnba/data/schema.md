# WNBA model data — file and field schema

All files are minified JSON in `docs/models/wnba/data/`. Floats are rounded (4–5 significant decimals).
`null` = not available. IDs are ESPN ids (players: athlete id; teams: ESPN team id).
Units: ratings are **points per 100 possessions**; rates are **probabilities (0–1)** unless stated; minutes are per 40-minute game.

Conventions used everywhere:
* `O` > 0 = better offence. `D` > 0 = **better** defence (fewer points allowed). Total impact = `O + D`.
* "Possession" = a run of one team's offensive actions ending in a made FG / last FT, defensive rebound, turnover or period end (≈79 per team-game in 2026). Offensive rebounds do **not** start a new possession.
* "Play" = a sub-unit of a possession that ends in a FGA, a shooting-foul FT trip or a turnover; an offensive rebound starts a new play.
* Zone order (index 0–4): `rim` (<4 ft), `short_mid` (4–14 ft), `long_mid` (14 ft+ twos), `corner3` (three, ≤9 ft above the hoop line), `above_break3`.

---

## meta.json
| field | type | meaning |
|---|---|---|
| build_date | str | date files were built (YYYY-MM-DD) |
| data_cutoff | str | analysis date; all data up to this date |
| last_game_date | str | date of last game in the data |
| seasons | int[] | seasons parsed (2017–2026) |
| n_games, n_games_by_season | int, {season: int} | games parsed (regular season + playoffs; all-star excluded) |
| n_possessions, n_shots | int | parsed possessions (non-empty) and field-goal attempts |
| n_players_exported, n_teams | int | rows in players.json / teams.json |
| lineup_recon | {season: {...}} | lineup reconstruction stats per season: `games`, `possessions`, `poss_lineup_ok` (share of possessions with five known players each side), `player_games`, `min_within_1` / `min_within_2` (share of player-games whose reconstructed minutes are within 1 / 2 min of the box score), `min_mae`, repair counters (`phantom_fix`: player acted while not on court → inserted; `sub_out_missing`: subbed-out player was not on court; `period_fill`: period starters had to be filled from the previous period) |
| recon_minutes_within_1, recon_poss_lineup_ok | float | pooled over seasons |
| hyper | obj | tuned hyper-parameters: `rapm` {H_seasons, H_feat, lambda_prior, lambda_plain}; `skills` {rate: {H, k}} |
| matchup_sims, matchup_seconds | int, float | sims per matchup in matchups.json; Python wall time for all of them |
| value | obj | `replacement_per100`, `n_replacement_players`, `pts_per_win`, `games` (season length used) |
| centre | {O, D} | constant subtracted from raw RAPM so the 2026 possession-weighted mean O and D are 0 |
| files | str[] | file list |

## players.json
`{ players: Player[], value_meta: {...same as meta.value}, league_xpts_per_shot: float }`

Player:
| field | type | meaning |
|---|---|---|
| id, name | int, str | |
| team, team_abbr | int\|null, str\|null | end-of-2026 team (last 2026 team played for; ESPN current roster if no 2026 games); null = free agent (played 2025, not 2026, on no ESPN roster) |
| pos, pos_group | str | ESPN position (G/F/C) and group used by the model (G/F/C) |
| age, age_imputed | float, bool | age at data cutoff; imputed from first season when ESPN has no birth date |
| height_in, height_imputed | float, bool | inches; imputed = position mean |
| roster_source | str | `last_2026_team` \| `espn_current_roster` \| `free_agent` |
| on_espn_roster | bool | on an ESPN team roster at cutoff (off-season) |
| sample | obj | `poss_w` recency-weighted offensive possessions in the RAPM; `career_poss` raw offensive possessions 2017–26; `career_gp`; `gp_2026`; `min_2026`; `shots_2026` |
| box_2026 | obj | 2026 per-game `mpg`, `ppg`, `rpg`, `apg` (context only) |
| impact | obj | `O`, `D`, `total` (prior-informed RAPM blend, centred), `O_sd`, `D_sd`, `total_sd` (posterior SD, independence assumed for total), `O_rapm`/`D_rapm` (same data, ridge toward 0, no prior), `O_prior`/`D_prior` (box-score SPM prior alone), `O_longrun`/`D_longrun` (all-seasons slow-decay RAPM used to train the prior; not centred) |
| four_factor | obj | four-factor RAPM, per 100 possessions (or per 100 rebound chances / shots): `tov_O` (+ = her offence commits more TOV), `tov_D` (+ = her defence lets opponents commit fewer TOV → negative is good), `orb_O` (+ = more own ORB%), `orb_D` (+ = opponent ORB% lower), `ftr_O` / `ftr_D` (FT trips per 100 poss; D + = fewer opponent trips), `efg_O` / `efg_D` (eFG points ×100 per FGA; D + = lower opponent eFG), `xpts_O` / `xpts_D` (shot quality generated / suppressed, expected pts ×100 per FGA), `moe_O` / `moe_D` (make over expected) |
| shot_quality | obj | `shots_w` recency-weighted FGA; `pts_per_shot`, `xpts_per_shot` (expected points per FGA from the xFG model); `shot_making` (points over expected per shot, shrunk with 150 pseudo-shots; + = makes more than location/type predicts); `shot_making_3pt` (same, threes only); `shot_selection` = xpts_per_shot − league mean (+ = takes better shots); `def_xpts_allowed` (on-court opponent expected pts ×100/FGA vs average, RAPM-style; negative = suppresses shot quality); `def_making_allowed` (opponent make-over-expected ×100/FGA; negative = good contest) |
| rates | {rate: {p, sd, n, raw, prior}} | projected skill rates (see list below). `p` projection (age-adjusted), `sd` posterior SD, `n` recency-weighted denominator, `raw` recency-weighted raw rate, `prior` position-group prior |
| minutes | obj | `proj` default minutes (team sums to 200), `sd` game-to-game SD, `starter`, `role_min` (recent minutes when playing), `avail` (share of healthy games played) |
| value | obj | `varp100` (total impact − replacement level, per 100), `varp_pts` (season points above replacement at projected minutes, 44 games), `varp_wins` (= varp_pts / pts_per_win), `off_delta` / `def_delta` / `net_delta` (change in team ORtg / DRtg / Net per 100 when she is removed and minutes re-allocated; DRtg up = worse), `winp_delta` (change in win probability vs a league-average opponent, neutral floor, normal approximation) |
| pct | {field: 0–100\|null} | percentile among qualified players (on a roster, ≥10 projected min) for O, D, total, varp100, shot_making, shot_selection and every rate |
| qualified_for_pct | bool | |
| actual_2026 | obj | 2026 actual per-game line in games played (regular season + playoffs): `games, min, pts, reb, ast, fg3m, stl, blk, tov` (only `games: 0` if she did not play) — new in round 2 |
| proj_per_game | obj\|null | projected per-game line at default minutes: mean over her team's 28 matchups in matchups.json of `min, pts, reb, ast, fg3m, stl, blk, tov, pra`; null if she has < 1 projected minute — new in round 2 |

Rates (`rates` keys; numerator / denominator):
`usg` plays used (FGA + non-and-one FT trips + TOV) / team possessions on court ·
`tov` TOV / plays used · `sfd` shooting-foul (incl. bonus) FT trips drawn / plays used · `trip3` 3-shot trips / trips ·
`and1` and-ones / made FG · `ftp` FT% · `ast` assists / teammate made FGs on court · `astd` share of own makes assisted ·
`orb` ORB / own-team rebound chances on court · `drb` DRB / opponent rebound chances on court ·
`stl` steals / defensive possessions · `blk` blocks / opponent FGA on court · `pf` personal fouls / defensive possessions ·
`mix_<zone>` share of FGA from zone (sums to 1) · `fg_<zone>` FG% in zone.

## teams.json
`{ teams: Team[] (sorted by net desc), league_ortg: float }`

| field | type | meaning |
|---|---|---|
| id, abbr, name, color, alt_color, logo | | team identity (colors hex without #) |
| roster | int[] | player ids, by projected minutes |
| rotation | {id, name, min, min_sd, starter, pos_group}[] | default rotation (minutes sum to 200) |
| ortg, drtg, net | float | bottom-up ratings per 100 possessions: ORtg = lg + Σ (min/40)·O, DRtg = lg − Σ (min/40)·D |
| pace_analytic | float | approx. possessions per team per 40 min vs an average opponent from player + team pace terms (closed form; ignores late-game and FT-trip time, so it runs ~4 below `pace_sim`). Round-1 files had this doubled (~150) by mistake |
| pace_sim | float | mean simulated possessions per team in its matchups |
| sim_avg_win_prob / proj_win_pct_vs_league | float | mean win probability over its 28 home/away matchups in matchups.json |
| sim_pts_for, sim_pts_against | float | mean simulated points over those matchups |
| top_lineups_2026 | {ids, names, poss, net100}[] | ten most-used 2026 five-player lineups; `poss` offensive possessions, `net100` raw net points per 100 (not adjusted) |
| pace_team_residual | {off, deff} | shrunk team (coach/system) seconds-per-first-play residual, + = slower |

## sim_params.json (input to sim.js)
| field | meaning |
|---|---|
| version | int |
| league | league constants (2026 regular season): `ortg` points/100 poss; `poss_per_team_game`; `tov_per_poss`; `ft_trips_per_poss`; `orb_rate` (ORB per rebound chance incl. team rebounds); `orb_rate_ft` (ORB rate after a missed last FT); `orb_player_credit` / `drb_player_credit` (share of team ORB/DRB credited to a player); `blk_given_miss_zone[5]`; `astd_zone_offset[5]` (logit offset of P(assisted) by zone); `steal_share_of_tov`; `tech_ft_per_poss`, `tech_ft_pct`; `lg_player_stl`, `lg_player_blk` (average player rates); `fg_by_zone`, `mix_by_zone` (reference) |
| context | `hca_pts` home margin (pts/game), `b2b_pts` margin effect of a back-to-back, `rest_day_pts` per extra rest day (1–4), `travel_pts_per_1000mi` |
| pace | `first_play_sec` league seconds of a possession's first play; `orb_play_sec`; `gamma_shape`; `steal_factor` (pace multiplier after a steal); `calibrated_poss`; `team_off` / `team_def` {team id: seconds residual} |
| sim | engine settings: `segment_sec` (lineup re-selection interval), `ot_segment_sec`, `min_cap` (per-sim minutes cap), `realloc_cap` (cap when re-allocating minutes), `max_c` (max centres on floor), `ff_def_weight`, `late_foul_sec`, `late_foul_max_lead`, `blowout` [[margin, seconds left]], `newton_iter`, `max_ot`, `score_effect` (make prob × (1 − score_effect × (offence lead − expected lead at that time)), capped ±25; expected lead = analytic expected final margin × elapsed/2400), `min_boost` (exponent β of the minutes base m·(m/20)^β, currently 0), `eff_shock_sd` (SD per 100 possessions of a per-game efficiency shock shared by both teams), `whistle_sd` (SD of a shared per-game log FT-trip-rate shock), `pace_shock_sd` (SD of a shared per-game log pace multiplier, currently 0), `late_foul_table` (`{rem_edges[5], lead_max, p[15][5], background}`: P(the trailing defence fouls at the start of a possession) for offence lead 1..15 and seconds left ≤15/30/45/60/90 in Q4/OT; replaces `late_foul_sec`/`late_foul_max_lead`, which remain in the file but are unused) |
| teams | {id, abbr, name, color, alt_color, logo}[] |
| players | per player: `id, name, team, pos_group, O, D, usg, usg_w` (context-free usage strength used for play shares), `tov, sfd, trip3, and1, ftp, ast, astd, orb, drb, stl, blk, pace_o, pace_d` (seconds added to first-play time when on offence / defence), `ff_tov_D, ff_ftr_D` (defensive four-factor RAPM used for TOV/FT levers), `min, min_sd, starter, mix_<zone>×5, fg_<zone>×5` |

## matchups.json  and  matchups/<homeId>.json
Every ordered pair of the 15 teams (210), default rotations, home team at home, both teams on 2 days' rest, no travel,
`n_sims` (10,000) simulations each.

* `matchups.json` = `{ n_sims, pairs: { "<homeId>_<awayId>": Matchup }, player_fields, line_step }` — all 210 games,
  **without** player pmfs (≈5 MB).
* `matchups/<homeId>.json` = `{ n_sims, home, pairs: { "<homeId>_<awayId>": Matchup }, player_fields, pmf_fields }` — the
  14 games with that home team, **with** player pmfs (≈1 MB each). Same Matchup structure plus `pmf` on each player.

`player_fields` = `["mean","sd","q10_25_50_75_90","first_line","p_over_5_lines"]` (describes the 5-element player stat arrays).
`line_step` = `{min:2, pts:2, reb:1, ast:1, fg3m:1, stl:1, blk:1, tov:1, pra:2, pr:2, pa:2}`.

Matchup: `{ home, away, game, home_players: P[], away_players: P[] }`

`game`:
| field | meaning |
|---|---|
| home_win | P(home wins), OT included |
| p_ot | P(overtime) |
| poss | mean possessions per team |
| margin, total, home_pts, away_pts | `[mean, sd, q]`, `q` = quantiles at **[0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]** (7 values); margin = home − away, final incl. OT |
| margin_hist | `[lo, p[]]`: P(margin = lo + i). Only the support with non-zero mass is stored (lo ≥ −50; draws beyond ±50 are clipped into ±50) |
| total_hist | `[lo, p[]]`: P(total = lo + i), clipped to 110..240, non-zero support only |
| home_pts_hist, away_pts_hist | `[lo, p[]]`: full pmf of each team's final score, P(points = lo + i) (new in round 2) |
| quarters | 4 × `[home_mean, away_mean, P(home wins quarter), P(quarter tied), margin_sd, total_sd]` |
| halves | 2 × same 6-element form; 2nd half **includes OT** |

Player record P (players with projected minutes ≥ 1):
`{ id, min_proj, min, pts, reb, ast, fg3m, stl, blk, tov, pra, pr, pa, fga, fg3a, fta, p_dd [, pmf] }`
* each stat `min … pa` is a 5-element array `[mean, sd, q, first_line, p_over]`:
  * `q` = 5 quantiles at [0.10, 0.25, 0.50, 0.75, 0.90];
  * `first_line` = the lowest of five half-point lines; the lines are `first_line + line_step[stat] × i`, i = 0..4
    (the five lines closest to the mean; with step 2 lines are odd integers + 0.5 apart by 2, e.g. 19.5, 21.5, …);
  * `p_over[i]` = P(stat > line i).
* `fga, fg3a, fta` = means; `p_dd` = P(double-double).
* `pmf` (per-team files only): `{ stat: [lo, p[]] }` for `min, pts, reb, ast, fg3m, stl, blk, tov, pra, pr, pa`;
  P(stat = lo + i) for integer values (minutes rounded to whole minutes); each tail trimmed where its cumulative
  probability is < 0.0005, so a pmf sums to ≈ 0.999. P(over any half-point line) = sum of the pmf above it.
All player numbers come from the same simulated games as the team scores, so they are correlated correctly.

## diagnostics.json
| field | meaning |
|---|---|
| aggregate | re-simulation of 2025–26 games with actual players/minutes/starters: each value `[real, simulated]` for `total_mean, total_sd, margin_mean, margin_sd, abs_margin_mean, home_win, ot_rate, poss_per_team`; `n_games`, `n_sims_per_game` |
| by_season | same split by season (total mean/sd, margin sd) |
| total_hist, margin_hist | `{edges[], real[], sim[]}` densities per 5-point bin |
| star_scoring | high-usage players (projected usg ≥ 0.24) in games with ≥ 25 min: `[real, sim]` for mean, sd, share 20+, 30+, <10 points |
| star_scoring_by_player | per player (≥15 such games): real vs simulated mean points |
| teammate_pts_corr | teammates' points correlation (≥20 min): `real_across_games`, `sim_across_games` (pooled sims), `sim_within_game` (same matchup) |
| skills_holdout | per rate: tuned `H` (half-life, seasons), `k` (prior pseudo-count) and binomial deviance gain (%) vs position prior on forward holdouts |
| rapm_holdout | possession-level MSE (points×100) on 2024–26 forward holdouts: constant baseline, best plain RAPM, best prior-informed; SPM weighted R² |
| team_ratings_oos_2026 | ratings fit on 2017–25 only, predicting 2026 margins from actual minutes: RMSE vs HCA-only and previous-season differential, correlation, win accuracy, calibration slope |
| shot_model | xFG model log-loss / Brier (cross-fitted) vs zone-only and constant, calibration table |
| lineup_reconstruction | as meta.lineup_recon |
| sim_seconds | Python time to run the re-simulation |
| season_2026 | **headline** calibration, 2026 games only: `[real, sim]` for `total_mean, total_sd, margin_mean, margin_sd, team_pts_sd, home_win, ot_rate, poss_per_team, one_to_three_pt_games`; `n_games`, `label` |
| season_2025 | same for 2025 games — simulated in the 2026 scoring environment, so levels (totals) are not comparable; `label` says so |
| period_sd_2026 | `[real, sim]` SDs of Q1 total / Q1 margin / first-half total / first-half margin |
| abs_margin_pmf_pct | `{margin[1..25], real_2017_2026[], sim[], n_real_games}`: % of games decided by exactly k points |
| player_calibration_insample / player_calibration_oos | per stat (`pts, reb, ast, fg3m, fta, fga, tov, stl, blk, min`): `slope`, `intercept` (OLS of actual on simulated mean per player-game), `mean_sim`, `mean_act`, `deciles` {dec, sim, act, n, ratio=act/sim} by decile of simulated mean, `usage_tiers` {tier (<16%,16-20%,20-24%,24-28%,28%+ projected usage), sim, act, n, ratio}; plus `pts_tails_25min` {n, act_sd_resid, sim_sd_mean, share20 [real, sim], share30 [real, sim]} for player-games with ≥ 25 actual minutes; `note`. In-sample = 2025–26 games with end-of-2026 projections; OOS = 2026 games with projections/ratings from data before 2026 |
| winprob_reliability_oos | 2026 games, everything fitted before 2026: `n_games, logloss, brier, logloss_coinflip, logloss_home_rate, margin_slope, deciles {dec, pred, actual, n}, rating_draws_added, note` |
| game_effects | estimates behind the shared shocks: real vs simulated within-game residual covariances of the two teams' points per possession and FTA, possession residual variances, the derived `eff_shock_sd_per100`, `whistle_sd`, `pace_shock_sd` |

## sim.js API
```
WNBASim.simulate(params, homeSpec, awaySpec, opts) -> { game, home, away, meta }
  homeSpec/awaySpec: team id, or { team: id, players: [{ id, min?: number, out?: bool, starter?: bool }] }
    - omit `players` to use the default rotation;
    - `out: true` removes a player; her minutes go to teammates (same position group weighted ×1.5, cap 38);
    - `min` fixes a player's minutes; the others are rescaled so the team totals 200.
  opts: { nSims=10000, seed=1, neutral=false, home_b2b, away_b2b, home_rest_days=2, away_rest_days=2,
          home_travel_miles=0, away_travel_miles=0 }
  game: { n_sims, home_win, margin{mean,sd,q}, total{...}, home_pts{...}, away_pts{...}, p_ot, poss_per_team,
          margin_hist{lo,hi,p[]}, total_hist{lo,hi,p[]}, quarters[4]{home,away,home_win,tie,margin_sd,total_sd},
          halves[2]{home,away,home_win,tie,margin_mean,margin_sd,total_mean,total_sd} }
  home/away: [{ id, name, proj_min, out, min|pts|reb|ast|fg3m|stl|blk|tov|pra|pr|pa: {mean, sd, q[7], lines[], p_over[]},
               fga, fg3a, fta, p_dd }]
  meta: { n_sims, seed, home_minutes[], away_minutes[] }   (re-allocated minutes, roster order)
WNBASim.prepareTeam(params, spec) -> internal team object (exposes .minutes after re-allocation)
WNBASim.reallocate(minutes[], posGroup[], out[], fixed[], cap, total)
```
Note: the JS engine returns objects (`{mean, sd, q}`), while matchups.json stores the compact array form `[mean, sd, q, lines, p_over]`.
