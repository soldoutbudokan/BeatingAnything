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
| pace_analytic | float | approx. possessions per team per 40 min vs average opponent from player + team pace terms |
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
| sim | engine settings: `segment_sec` (lineup re-selection interval), `ot_segment_sec`, `min_cap` (per-sim minutes cap), `realloc_cap` (cap when re-allocating minutes), `max_c` (max centres on floor), `ff_def_weight`, `late_foul_sec`, `late_foul_max_lead`, `blowout` [[margin, seconds left]], `newton_iter`, `max_ot`, `score_effect` (make prob × (1 − score_effect × offence lead, lead capped ±25)) |
| teams | {id, abbr, name, color, alt_color, logo}[] |
| players | per player: `id, name, team, pos_group, O, D, usg, usg_w` (context-free usage strength used for play shares), `tov, sfd, trip3, and1, ftp, ast, astd, orb, drb, stl, blk, pace_o, pace_d` (seconds added to first-play time when on offence / defence), `ff_tov_D, ff_ftr_D` (defensive four-factor RAPM used for TOV/FT levers), `min, min_sd, starter, mix_<zone>×5, fg_<zone>×5` |

## matchups.json
`{ n_sims, pairs: { "<homeId>_<awayId>": Matchup }, player_fields: ["mean","sd","q","lines","p_over"] }`
Every ordered pair of the 15 teams (210), default rotations, home team at home, both teams rested (2 days), no travel.

Matchup: `{ home, away, game, home_players: P[], away_players: P[] }`

`game`:
| field | meaning |
|---|---|
| home_win | P(home wins) incl. OT |
| p_ot | P(overtime) |
| poss | mean possessions per team |
| margin, total, home_pts, away_pts | `[mean, sd, q]` where `q` = quantiles at [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]; margin = home − away (final, incl. OT) |
| margin_hist | `[lo, p[]]`: P(margin = lo + i), i = 0..100 (lo = −50; tails clipped into the end bins) |
| total_hist | `[lo, p[]]`: P(total = lo + i), lo = 110, up to 240 (clipped) |
| quarters | 4 × `[home_mean, away_mean, P(home wins quarter), P(quarter tied), margin_sd, total_sd]` |
| halves | 2 × same; 2nd half **includes OT** |

Player record P (players with projected minutes > 0):
`{ id, min_proj, min, pts, reb, ast, fg3m, stl, blk, tov, pra, pr, pa, fga, fg3a, fta, p_dd }`
Each stat (`min` … `pa`) is `[mean, sd, q[7], lines[], p_over[]]`: `lines` are half-point thresholds around the mean (step 1 for reb/ast/3pm/stl/blk/tov, step 2 for min/pts/combos); `p_over[i]` = P(stat > lines[i]). `fga, fg3a, fta` are means; `p_dd` = P(double-double). All player stats come from the same simulated games as the team scores (correlated).

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
