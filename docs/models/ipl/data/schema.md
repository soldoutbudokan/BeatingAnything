# IPL model exports — schema

All files are minified JSON in `docs/models/ipl/data/`. Numbers are rounded to 3 decimals. `null` means
"not available" (e.g. a batter with no bowling record has no `bowl` block). Player ids are cricsheet register
identifiers (8 hex chars). Venue ids are canonical lowercase venue keys (e.g. `"wankhede stadium"`).
Team ids are full franchise names (e.g. `"Mumbai Indians"`).

Conventions used throughout:

* **Phases**: `pp` = overs 1-6, `mid` = overs 7-15, `death` = overs 16-20.
* **Rates** are per 100 balls unless the name says otherwise (`econ` and `*_per_over` are per 6 legal balls).
* **"IPL conditions"**: model ratings are evaluated on every real IPL delivery of 2024-26 with the player
  swapped in (real opponent, venue, season, match situation). See `method.md` §4.
* **Outcome classes** (order used in every 11-vector): `["wide","noball","byes","wicket","runout","r0","r1","r2","r3","r4","r6"]`.

---------------------------------------------------------------------------------------------------------

## meta.json

| field | type | meaning |
|---|---|---|
| build_utc | string | build timestamp (UTC) |
| data_source | string | data provenance |
| data_cutoff | date | last match date in the data |
| ipl_latest_season | int | latest IPL season in the data (squads come from it) |
| ipl_last_match | date | last IPL match date |
| counts.matches / deliveries | int | all ingested 20-over men's T20 matches / deliveries |
| counts.deliveries_modelled | int | deliveries in the final fit (non-reduced, non-super-over, weight > 0.01) |
| counts.matches_reduced_or_dls_excluded | int | matches excluded from the fit |
| counts.by_comp[code] | object | `{matches, deliveries, first, last}` per competition code (see leagues.json) |
| model.half_life_years | float | time-decay half-life of delivery weights |
| model.penalties | object | ridge penalties per term block (`bat`, `bowl`, `bat_split`, `bowl_split`, `venue`, `venue2`, `cs` (league-season), `comp`, `cell`, `cov`, `l0`) |
| model.lbfgs_iterations, n_coefficients, ref_date | | fit details |
| styles.players_with_style / bowling_group_inferred | int | style coverage; how many pace/spin labels were inferred |
| sim.python_sec_per_10k / js_node_sec_per_10k | float | sim speed for 10,000 matches |
| sim.parity | object | JS vs Python check: `comparisons`, `max_abs_z`, `share_abs_z_gt_2`, `mean_abs_z`, `pass` |
| sim.runs_to_win_prob | float | win-probability change per run of expected margin (used for `varp_wp`) |
| files_bytes, total_bytes | | export sizes |

## players.json

`{players: [Player], avg_bat, avg_bowl, settling_avg, settling_buckets, replacement, slot_balls, runs_to_wp}`

* `avg_bat[stratum]` / `avg_bowl[stratum]`: the average IPL 2024-26 batter/bowler metrics per stratum
  (same keys as a player's block). Batting strata: `all, pp, mid, death, pace, spin`; bowling strata:
  `all, pp, mid, death, rhb, lhb`.
* `settling_avg`: average batter's settling curve, list of 9 `[sr, out_pct]` pairs for the buckets in
  `settling_buckets` (`"0","1-2","3-5","6-9","10-14","15-19","20-29","30-44","45+"` balls faced before the delivery).
* `replacement.bat[role]` (`open, top, middle, lower`) and `replacement.bowl[group]` (`pace, spin`):
  replacement-level run value per phase (`pp, mid, death`): `rv100` for batters, `rv_over` for bowlers.
* `slot_balls[i]`: average balls faced per IPL innings by batting position i+1 (2024-26).
* `runs_to_wp`: same as `meta.sim.runs_to_win_prob`.

### Player

| field | type | meaning |
|---|---|---|
| id, name | string | cricsheet id and name |
| team | string/null | franchise in the latest IPL season (null if not in an IPL squad) |
| ipl_teams | [{team, from, to}] | IPL franchises played for, first/last season |
| overseas | bool | played T20Is for a country other than India |
| country | string/null | international team (most appearances), if any |
| bat_hand | "R"/"L"/null | batting hand |
| bowl_type | string/null | e.g. RF, RFM, RM, LF, LFM, LM, OB, LB, SLA, SLW, none |
| bowl_group | "pace"/"spin"/"none"/null | |
| bowl_subtype | string | model's bowling subtype: `pace_R, pace_L, OB, LB, SLA, SLW, pace_U, spin_U` (U = type unknown) |
| style_inferred | bool | pace/spin label came from the classifier, not the styles file |
| role_bat | string | prior group by career median batting position: `open` (1-2), `top` (3-4), `middle` (5-7), `lower` (8-11) |
| role_bowl | string | prior group: `{pace|spin}_{part|reg|front}` by career overs per match (<1.5, 1.5-2.75, >2.75) |
| bat_pos_career, overs_per_match_career | float | |
| league_mix | {tier: share} | share of the player's deliveries by tier: `ipl, intl, top_fr, fr2, india_dom, dom, assoc` |
| varp_runs | float | batting + bowling value above replacement, runs per match |
| varp_wp | float | the same in win probability per match (0.01 = 1 percentage point) |
| bat | object/null | batting block (below) |
| bowl | object/null | bowling block (below) |

#### bat block

* `bat[stratum]` for stratum in `all, pp, mid, death, pace, spin` — model ("true") rates in IPL conditions:
  `sr` (runs/100 balls), `avg` (runs per dismissal), `out_pct` (dismissals/100 balls), `bnd_pct`, `four_pct`,
  `six_pct`, `dot_pct` (balls with no bat run, incl. dismissals), `nbsr` (strike rate on non-boundary balls),
  `rv100` (run value per 100 balls = runs minus wicket cost; see method §4). `all` uses the player's own phase
  mix; `pace`/`spin` use his phase mix restricted to that bowling type.
* `bat.vs_avg[stratum]`: `{sr, out_pct, rv100, bnd_pct, dot_pct}` = player minus the average IPL batter on the
  same deliveries (positive `sr`/`rv100`/`bnd_pct` good; negative `out_pct`/`dot_pct` good).
* `bat.sd`: posterior SD of `all` `{sr, out_pct, avg, rv100}`.
* `bat.settling`: 9 `[sr, out_pct]` pairs by balls-faced bucket (middle-overs context).
* `bat.value`: `{slot, exp_balls, rv100_slot, rep_rv100, varp_runs, varp_wp}` — batting slot used (default
  team order, else IPL median position), expected balls per innings in that slot, his run value in that slot's
  phase mix, replacement's, and the resulting value per match.
* `bat.pct`: percentile ranks (0-100, higher = better) among pool batters with ≥100 IPL balls since 2024 or ≥300
  balls anywhere since 2024: `all_sr, all_avg, all_rv100, death_sr, pp_sr, spin_sr, pace_sr, bat_varp`.
* `bat.obs_2024` (all competitions since 2024-01-01) and `bat.obs_ipl_2024` (IPL only): observed vs expected,
  unshrunk: `balls, runs, outs, sr, xsr` (expected SR for an average IPL batter on the same deliveries),
  `rae100` (runs above expected per 100 balls), `outs_vs_x` (dismissals minus expected; negative good),
  `avg, xavg, fours, sixes, x4, x6, wpa` (win probability added, total), `wpa_per_match`.
* `bat.ipl_career`: raw IPL career `{inns, balls, runs, outs, sr}`.

#### bowl block

* `bowl[stratum]` for `all, pp, mid, death, rhb, lhb`: `econ` (runs per 6 legal balls incl. wides/no-balls),
  `wkt_pct` (bowler wickets per 100 legal balls), `sr` (balls per wicket), `avg` (runs per wicket), `dot_pct`,
  `bnd_pct`, `six_pct`, `wides_per_over`, `rv_over` (runs conceded minus wicket value, per over; lower good).
* `bowl.vs_avg[stratum]`: `{econ, wkt_pct, rv_over, dot_pct}` vs the average IPL bowler on the same deliveries
  (negative `econ`/`rv_over` good).
* `bowl.sd`: posterior SD of `all` `{econ, wkt_pct, rv_over}`.
* `bowl.phase_mix`: [pp, mid, death] share of his (recency-weighted) legal balls.
* `bowl.value`: `{rv_over_mix, rep_rv_over, varp_runs, varp_wp}` — value per 4 overs in his phase mix.
* `bowl.pct`: percentiles (higher = better): `all_econ, all_rv_over, death_econ, pp_econ, all_wkt_pct, bowl_varp`.
* `bowl.obs_2024`, `bowl.obs_ipl_2024`: `balls` (legal), `conc`, `wkts`, `econ`, `xecon`, `runs_saved`
  (expected minus actual conceded), `wkts_vs_x`, `dot_pct`, `xdot_pct`, `wpa`, `wpa_per_match`.
* `bowl.ipl_career`: `{inns, balls, conc, wkts, econ}`.

## teams.json

`{season, teams: [Team]}`

| field | meaning |
|---|---|
| name, short, season, matches_in_season | |
| home_venue | venue id used as home in matchups.json |
| venues_used | most-used venues (top 3) |
| xii | default 12 (XI + Impact Player), ids |
| order | default batting order (11 ids) |
| impact_player | id of the 12th player (bowls, does not bat) |
| plan | bowling plan `[{id, pp, mid, death}]` (whole overs per phase; totals 6/9/5, ≤4 per bowler) |
| schedule | the 20 bowler ids, over by over, that the captain heuristic produces from `plan` |
| squad | every player used that season: `{id, name, apps, last_app, overseas, bat_pos (weighted mean), overs_pm, ov_pp, ov_mid, ov_death (per match), in_pool}` (`in_pool` = has ratings in players.json/sim_params.json) |
| rating | `{win_pct_neutral` (mean P(win) vs the other 9 at a neutral venue), `win_pct_home_away` (mean over the 18 home/away matchups), `runs_for`, `runs_against`, `net_runs` (mean totals across those matchups), `xi_bat_varp`, `xi_bowl_varp` (bowling VARP scaled by planned overs/4), `xi_varp`, `rank` (by win_pct_neutral)}` |

## matchups.json

`{n_sims, toss, env, matchups: [Matchup], neutral: [{A, B, p_win_A, runs_A, runs_B}]}`

Matchup: `{A, B, venue, home, n, p_win_A, p_tie, A_stats, B_stats}` for every pair at each side's home venue
(90 rows). Half the sims have each side batting first. `p_tie` = share of sims tied after 20 overs (decided by
the super over inside `p_win_A`).

TeamStats (`A_stats` / `B_stats`): `total_mean, total_sd, total_q` (5/25/50/75/95th percentiles), `wkts_mean`,
`pp_mean, pp_q` (powerplay runs), `fow1_mean, fow1_q` (score when the first wicket fell; full total if none),
`fours_mean, fours_q, sixes_mean, sixes_q, wides_mean, extras_mean`, `bat1_total_mean, bat2_total_mean`
(total when batting first / second), `p_win_bat1, p_win_bat2` (win prob when batting first / second),
`players: {id: PlayerProj}`.

PlayerProj (batting keys present for the 11 in the order, bowling keys for bowlers in the plan):
`bat_pos` (null for the bowling-only Impact Player), `p_bat` (got to the crease), `runs_mean`, `runs_q`
(10/25/50/75/90th percentiles), `p_runs` (`{"10","20","30","40","50","75","100"}` → P(runs ≥ t)), `p_duck`
(out for 0), `balls_mean`, `fours_mean`, `sixes_mean`, `p_out`, `p_top_bat` (P(top run-scorer for his side),
ties split); `overs_mean`, `wkts_mean`, `p_wkts` (`{"1".."5"}` → P(wkts ≥ t)), `conceded_mean`, `econ`,
`p_top_bowl` (most wickets, fewest runs as tie-break, ties split).

## venues.json

`{neutral_reference, venues: [Venue], home_of: {team: venue}, resources}`

* Venue: `venue` (id), `name`, `city`, `matches`, `matches_since_2021`, `ipl_matches`, `last_match`; then for
  scope in `all, pace, spin, inn1, inn2` and quantity `rpo` (runs/over), `wpo` (wickets/over incl. run outs),
  `fpo` (fours/over), `spo` (sixes/over): `{scope}_{q}` (value in IPL 2024-26 conditions at this ground) and
  `{scope}_{q}_mult` (ratio to an average ground). `all_rpo_mult_sd` = posterior SD of the runs multiplier.
  E.g. `spin_wpo_mult` > 1 = spinners take more wickets here than at an average ground;
  `inn2_rpo_mult / inn1_rpo_mult` > 1 = batting second is easier (dew).
* `neutral_reference[scope]`: the average-ground `{rpo, wpo, fpo, spo}`.
* `resources`: expected runs remaining in a first innings: `er[o][w]` from the start of over o (0-19) with w
  wickets down (0-10), and `wicket_value[o][w]` = er[o][w] - er[o][w+1] (runs a wicket costs); `scale_to_ipl`.
  Only venues with ≥5 matches and a match since 2018 are listed; only listed venues exist in sim_params.

## leagues.json

`{leagues: [League], env_ipl: {season: 11-vector}}`

League: `comp` (code), `name`, `tier`, `balls`, `matches` (since 2023), `last_season`, `bat_sr`, `bat_out_pct`
(the league's average batter in IPL conditions), `bat_runs_vs_ipl` (runs per 120 balls vs the IPL's average
batter), `bowl_econ`, `bowl_wkt_pct`, `bowl_runs_vs_ipl` (runs saved per 20 overs vs the IPL's average bowler;
negative = weaker), `strength_vs_ipl` (sum; IPL = 0), `env_runs_per_over`, `env_wkt_pct` (the league's own run
environment in its latest season, IPL-situation mix). `env_ipl` = the IPL season environment logit offsets
(see sim_params).

## sim_params.json (consumed by sim.js; documented for completeness)

| field | meaning |
|---|---|
| classes, ref_class | outcome class names; index of the reference class (r0) |
| base, base_shape [2,20,8,11] | context logits by innings, over (0-19), wickets down (0-7, 7 = 7+) |
| bf, bf_shape [3,9,11], bf_edges, bf_labels | settling: logits by phase and balls-faced bucket (lower edges) |
| early_bf | balls-faced threshold for the batter's own `ea` settling term (10) |
| chase, chase_shape [3,8,11], rrr_edges, rrr_labels | 2nd innings: logits by phase and required-rate bucket (interior edges) |
| sub[subtype], sub_lhb[subtype], sub_phase[subtype][phase] | bowler subtype main effect, extra vs a left-hander, by phase (mid = 0) |
| env[key], default_env | season environment offsets (`"IPL|2026"`, ..., `"IPL|2024-26"`) |
| venues[id] | `{base, i2 (2nd innings), spin (spin deliveries)}` logit offsets; `venue_neutral` = zeros |
| batters[id] | `{b, pp, de, sp, ea, hand}`: overall (prior mean folded in), powerplay, death, vs spin, first 10 balls; hand R/L |
| bowlers[id] | `{b, pp, de, lh, sub, spin}`: overall (prior folded in), powerplay, death, vs left-hander, subtype, spin flag |
| batter_priors[role], bowler_priors[role] | vectors for players not in `batters`/`bowlers` |
| extras | `wide_runs, nb_bat, bye_runs, runout_runs` as `{v: values, p: weights}`; `runout_striker` = P(the striker is the one run out) |

Per-delivery logit = base[inn][over][min(wkts,7)] + bf[phase][bucket(balls faced)] + (2nd inns) chase[phase][rrr bucket]
+ env + venue.base + (2nd inns) venue.i2 + spin·venue.spin + sub[s] + sub_phase[s][phase] + bowler.b + (pp) bowler.pp
+ (death) bowler.de + batter.b + (pp) batter.pp + (death) batter.de + spin·batter.sp + (balls faced < 10) batter.ea
+ (left-hander) (sub_lhb[s] + bowler.lh).

## diagnostics.json

* `holdout`: `{cutoff, all, ipl}`; each scope: `n_balls, logloss` (model, trained before cutoff),
  `logloss_marginal` (no-skill class frequencies), `classes[c] = {mean_pred, obs_rate, bins: {pred, obs, n}}`
  (decile reliability bins), `innings_runs_expected/actual`, `innings_wkts_expected/actual` (per innings).
* `tuning`: every holdout fit tried: `{half_life, lam, iters, ll_all, ll_ipl, n_test, n_ipl}` (the entry with
  `lam.bat = 1e9` is the no-player-skill baseline).
* `replay`: `{seasons, matches, sims_per_match, rows: [{metric, sim_mean, sim_sd, actual_mean, actual_sd}],
  individual: {sim, actual, n_actual}` (`duck_pct, ge30_pct, ge50_pct, mean` per batting innings),
  `t1_hist: {edges, sim, actual}` (share of 1st-innings totals per 10-run bin)}.

## sim.js API

```js
const P = IPLSim.prepare(simParams);                    // once
const out = IPLSim.simMatch(P, teamA, teamB, {venue, n: 10000, seed: 1, batFirst: null, env: "IPL|2026"});
// team = {name, order: [11 ids], plan: [{id, pp, mid, death}]}  or  {name, order, schedule: [20 ids]}
IPLSim.bowlingSchedule(plan)  // -> 20 bowler ids (captain heuristic)
```

`out` has the same shape as a matchups.json row's summary: `{n, p_win_A, p_tie, margin_mean_A, A: TeamStats, B: TeamStats}`.
Players not in `sim_params.batters/bowlers` fall back to `batter_priors.middle` / `bowler_priors.pace_reg`.
