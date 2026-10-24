# Cricket win-probability model plan

Written October 24, 2026; revision 2 the same day after four independent reviews (cricket strategy, statistics, simulation engineering, and a data audit run against the raw files). Goal: a bottom-up, ball-by-ball Monte Carlo model of men's and women's T20, ODI and Test cricket that rates players, pitch, venue, home conditions, umpires, DRS rules and weather, plus an interactive static web page that runs the same simulator in the browser.

This file is the contract between components. Every module, parameter file and the browser engine follows it. An implementation that must deviate records the deviation, with a reason, under "Deviations" at the bottom (only the coordinating session edits this file; agents report deviations in their final reports).

## 1. Principles

- **Bottom-up.** Win probability is never fitted directly. It emerges from simulating every delivery: delivery type, on-field outcome, dismissal kind, the DRS review process, strike rotation, bowler choice, declarations, weather interruptions, target revisions and tie-breaks.
- **No lookahead, no match-day leakage.** Every fitted quantity used for a match is estimated from data dated strictly before its first day. Pre-match inputs are restricted to what is known at the toss: the starting XIs (not their realized batting order), the toss, venue, officials and climatology-based weather. Realized batting order, the impact substitute actually used, and observed weather appear only in labelled "oracle" diagnostics.
- **Shrinkage everywhere.** Player, venue, umpire and season effects are random effects with Gaussian priors whose scales are estimated by empirical Bayes, per class.
- **Carry the variance the model fits.** Match-level and innings-level latent effects and player-parameter uncertainty are drawn inside each simulation, not set to zero.
- **One semantics, two engines.** The JavaScript engine (`docs/cricket/engine.js`) is the fast engine: it runs the page in Web Workers and the bulk evaluation through a Node command-line wrapper (`docs/cricket/cli.js`). The Python engine (`beating/cricket/sim.py`) is a scalar, readable twin with identical formulas, transition rules and random-number consumption, used for parity checks and for interactive analysis. Parity tests compare exact feature levels, probability vectors, transitions and full seeded trajectories, so a result from either engine is a result from both.
- **Measured, not assumed.** A component is called helpful only when its held-out improvement interval excludes zero. Components that do not earn their place stay available as what-if inputs on the page with their fitted (possibly near-zero) coefficients, and the report says so.

## 2. Data sources (verified reachable October 24, 2026)

| Source | What | Access |
| --- | --- | --- |
| Cricsheet `all_json.zip` (created 2026-10-14; 22,978 files at data version 1.2.0 and 154 at 1.3.0) | 23,132 matches, 11.69M deliveries; officials, toss, listed players, powerplays, replacements (impact player, concussion, supersub), 17,153 DRS reviews with reviewing team, umpire, decision and an umpire's-call flag | `https://cricsheet.org/downloads/all_json.zip` |
| Cricsheet people register | identifiers including Cricinfo keys | `https://cricsheet.org/register/people.csv`, `names.csv` |
| cricketdata `player_meta` | 16,101 players: batting hand, bowling style, role, DOB, country, keyed by Cricsheet id | `git clone https://github.com/robjhyndman/cricketdata` (`data/player_meta.rda`, read with `pyreadr`) |
| NOAA ISD-lite (AWS open data) | hourly temperature, dew point, pressure, wind, sky cover, precipitation | `https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data/{YYYY}/{USAF}-{WBAN}-{YYYY}.gz`; stations `isd-history.csv` |
| NOAA GSOD (AWS open data) | daily summaries with rain/thunder flags | `https://noaa-gsod-pds.s3.amazonaws.com/{YYYY}/{USAF}{WBAN}.csv` |

Blocked from this container: Open-Meteo, ESPNcricinfo, Cricbuzz, Wikipedia, Kaggle, Zenodo, Betfair, The Odds API and CDNs. No historical odds source is reachable, so market comparison is out of scope for this build.

Raw downloads: `data/raw/cricsheet/`, `data/raw/noaa/` (git-ignored). Processed tables: `data/processed/cricket/` (git-ignored, parquet). Small derived files needed for reproducibility or the page: `data/derived/cricket/`, `config/`, `docs/cricket/data/` (committed).

Known data limits: no ball timestamps, no session or day markers in Tests, no match start times, no ball-tracking, no boundary dimensions, no record of appeals turned down and not reviewed, only the final revised target of a chase. Cricsheet withholds about 380 Afghanistan men's matches (zip README): Afghanistan international XIs are unsupported on the page and opponents' histories have that gap.

## 3. Repository layout

```
beating/cricket/glm.py          penalized multinomial logit with random-effect groups (done)
beating/cricket/baselines.py    Elo and XI-aware logistic baselines
beating/cricket/venues.py       venue canonicalisation, coordinates, station matching
beating/cricket/weather.py      ISD-lite/GSOD acquisition and per-match-day features
beating/cricket/players.py      player metadata and bowling-type inference
beating/cricket/competitions.py event -> competition_id, tier, season_key, series key
beating/cricket/rules.py        playing-conditions timeline lookup
beating/cricket/ingest.py       Cricsheet -> matches / balls / events / officials tables
beating/cricket/teams.py        team lineage (renames) and home-venue table
beating/cricket/features.py     the shared feature definitions (mirrored line for line in engine.js)
beating/cricket/resource.py     fitted resource table Z(u, w) (chase pressure and DLS-style targets)
beating/cricket/fit_ball.py     delivery-type, outcome and dismissal-kind fits per (family, gender, cutoff)
beating/cricket/drs.py          DRS review-process estimation
beating/cricket/tactics.py      bowler choice, batting order, toss, declaration, follow-on, new ball
beating/cricket/time_rain.py    Test clock, limited-overs interruptions, no-result
beating/cricket/params.py       parameter bundle assembly and export
beating/cricket/rng.py          shared xoshiro128** stream generator (done; twin docs/cricket/rng.js)
beating/cricket/sim.py          scalar reference engine (float64, own PRNG), exact twin of engine.js
beating/cricket/evaluate.py     walk-forward evaluation, calibration, ablations
tools/*.py                      runnable pipelines, split into "# %%" cells
docs/cricket/                   index.html, app.js, engine.js, provider.js, rng.js, worker.js, cli.js, data/*.json (static page, ES modules, no external libraries)
tests/test_cricket_*.py         unit, recovery and parity tests (parity tests call node; skip if absent)
tests/data/cricket_parity/      prng_kat.json, features.jsonl, transitions.jsonl, trajectories.jsonl
config/cricket-venues.csv, config/cricket-rules.json, config/cricket-teams.csv, config/cricket-day-night.csv
requirements-cricket.txt        optional extras (pyarrow, pyreadr)
reports/cricket-*.md|json       evaluation outputs
```

## 4. Canonical tables

### 4.1 Format families

`fam` ∈ {`T20`, `HUNDRED`, `ODI`, `TEST`}: T20 = Cricsheet T20 and IT20 with `balls_per_over` 6; HUNDRED = `balls_per_over` 5 (exactly the 389 Hundred matches; detect by `balls_per_over`, not event name); ODI = ODI and ODM; TEST = Test and MDM. Fits run per fitting family {T20+HUNDRED, ODI, TEST} × gender. HUNDRED balls enter the T20 fit with their own context levels; the engines do not simulate the Hundred in v1 (deviation D1).

### 4.2 `matches`

`match_id` (int, file stem), `start_date`, `dates_played` (JSON), `scheduled_days` (from rules, never from `len(dates)`, which leaks the result), `season` (string), `match_type`, `fam`, `gender`, `team_type`, `event_name`, `competition_id`, `tier`, `season_key`, `series_key` (event + season; bilateral series = same teams within 60 days), `match_number`, `venue_raw`, `city_raw`, `venue_id`, `team1`, `team2` (lineage-canonical names) and `team1_raw`, `team2_raw`, `home_status1`, `home_status2` (`home`, `away`, `neutral`), `toss_winner`, `toss_decision`, `toss_uncontested`, `winner`, `result` (`win`, `tie`, `draw`, `no_result`), `method`, `win_by_runs`, `win_by_wickets`, `win_by_innings`, `eliminator`, `bowl_out`, `tie_break_used`, `scheduled_overs` (corrected when inconsistent with the match type; log fixes), `balls_per_over`, `umpire1_id`, `umpire2_id`, `tv_umpire_id`, `referee_id`, `squad_listed_team{1,2}` (raw lists), `xi_start_team{1,2}` (listed players minus replacement "in" players), `subs` (JSON of replacements with reason, team, in, out, delivery), `bat_order_team{1,2}_inn{k}` (actual arrival order per innings), `reviews_missing`, `drs_available` (true/false/null), `drs_source` (`match`, `series`, `rules`, `unknown`), `start_slot` (`day`, `day_night`, `night`, `unknown`, from `config/cricket-day-night.csv` and competition defaults), `follow_on` (derived), `n_innings`, `super_over`, `awarded`.

### 4.3 `balls` (one row per delivery in main innings; super overs stored separately)

Keys: `match_id`, `innings` (1..4), `ball_seq` (0-based delivery index in innings; the unique key), `over` (0-based; HUNDRED = 5-ball set index), `ball_in_over` (legal balls already bowled in this over; may reach 6 or 7), `legal_ball_index` (legal balls before this one in the innings), `bat_team`, `bowl_team`, `batter_id`, `non_striker_id`, `bowler_id`.

Outcome as recorded: `runs_batter`, `non_boundary`, `wides`, `noballs`, `byes`, `legbyes`, `penalty`, `runs_total`, `dtype` (`legal`, `wide`, `noball`), `wicket_kind_raw`, `wk` (`caught` incl. caught-and-bowled, `bowled`, `lbw`, `stumped`, `run_out`, `other` = hit wicket, obstructing, handled, hit twice, timed out), `player_out_id` (handle the misspelt key `playeer_out`), `out_role` (`striker`, `non_striker`, `neither`), `second_wicket`, `retire_event` (`retired_hurt`, `retired_not_out`, `retired_out`, or null; recorded on the delivery it is attached to, which still counts), `fielders` (JSON).

Review fields: `review_by` (`bat`, `bowl`), `review_decision` (`upheld`, `struck_down`, `technical`), `review_umpires_call` (true when the key is present; false when absent and the date is on or after that family's first recorded flag — Test 2017-08-25, ODI 2017-10-16, T20 2017-12-24, Hundred 2021-07-30; null before), `review_umpire_id` (from `review.umpire`; 1.8% missing), `review_batter_id`, `review_about_wicket` (false when `review.batter` differs from `player_out`). The `type` field carries no information and is dropped.

On-field reconstruction (section 6.5): `onfield_out` (bool), `onfield_class` (outcome class the umpire's decision implies), `final_out`.

State before the delivery (computed from the pre-ball state only): `inn_runs` (starting at `penalty_runs.pre`), `inn_wkts` (wickets including retired out), `inn_unavailable` (wickets + absent hurt + retired hurt not resumed), `striker_balls`, `striker_runs`, `nonstriker_balls`, `nonstriker_runs` (balls count legal balls and no-balls, not wides), `partnership_runs`, `partnership_balls` (reset whenever the pair changes), `striker_arrival` (rank at first appearance as batter or non-striker; resuming batters keep it), `bowler_balls_inn`, `bowler_spell_overs` (consecutive alternate overs k−2, k−4, …), `free_hit` (derived from rules and the previous delivery, including carry-over through wides and no-balls), `pp_window` (`pp1`, `pp2`, `pp3`, `batting`, `fielding`, `power_surge`, `none`), `pp_source` (`recorded`, `rules`), `field_restr` (maximum fielders allowed outside the circle, from rules and the window), `max_balls` (innings length in legal balls as known before the ball: scheduled, or the revised length when the revision is known to precede the ball; never the ex-post reduced first-innings length), `balls_remaining`, `target_runs`, `target_known`, `target_timing` (`original`, `pre_inn2`, `unknown`), `runs_required`, `match_legal_balls` (Tests), `ball_age_overs` (completed innings overs mod 80), `second_new_ball` (completed overs ≥ 80), `est_day` (section 7.5), `lead` (batting side's aggregate minus the opponent's; negative after a follow-on), `bat_fail_reviews`, `bowl_fail_reviews` (unsuccessful, non-umpire's-call reviews so far in the innings by each side), `bowl_end_umpire_p` (probability umpire 1 is at the bowler's end, section 6.6).

Pre-match player context (as of the match date, from strictly earlier matches in the same fitting family): `striker_exp`, `bowler_exp` (prior balls faced / bowled), `striker_role_pos` (median arrival position over the player's previous 10 innings; fallback this match's arrival), `striker_overseas`, `bowler_overseas` (player country ≠ venue country, franchise and domestic only).

Storage: int8/int16/int32/float32 with dense integer ids; the full table must fit in about 3 GB RAM.

### 4.4 Other tables

- `events`: one row per non-ball event (retired hurt/out/not out, absent hurt, temporary retirement and resumption, replacement, declaration, forfeiture, follow-on, interruption inferred from target revision).
- `players` (section 4.3 of revision 1, plus `bowl_type_2`, `keeper` inferred from stumping fielders, dedup rule: prefer the `player_meta` row whose `cricinfo_id` equals `people.csv` `key_cricinfo`; style strings matched case- and hyphen-insensitively; "Right/Left arm Bowler", "Slow", "Right arm Slow" -> unknown, then inferred).
- `venues` (`config/cricket-venues.csv`): aliases keyed on the (venue_raw, city_raw) pair; never merge across different non-null cities; Nursery / Academy / "No N" / "Ground A" / "B" grounds stay separate; renamed grounds merge (Feroz Shah Kotla -> Arun Jaitley Stadium; Motera -> Narendra Modi Stadium; Sheikh Zayed -> Zayed Cricket Stadium; Wanderers variants). Columns as before plus `region`, `elevation_m`, `utc_offset_hours`, `dst_region`, `ball_brand_default` (Dukes: England, Ireland, Scotland, West Indies; SG: India; Kookaburra elsewhere; Tests only — verify start years).
- `teams` (`config/cricket-teams.csv`): lineage (Kings XI Punjab -> Punjab Kings, Delhi Daredevils -> Delhi Capitals, Royal Challengers Bangalore -> Bengaluru, CPL and PSL renames, ...), country of internationals, and franchise home venues by season (derived from data: a venue is a team's home in a season when the team plays at least 30% of its matches there and the venue is not neutral for the competition that season; neutral when it hosts more than 40% of the competition's matches or the season is played abroad).
- `weather_match_day` (unchanged fields; per scheduled day).
- `climatology`: per venue × calendar month, recomputed from data before each cutoff (section 10).

## 5. Rules timeline (`config/cricket-rules.json`)

Fields per (competition, date range) with family/gender defaults: `overs_per_innings`, `balls_per_over`, `bowler_quota` (overs; reduced matches: ⌊N/5⌋ with up to N mod 5 bowlers allowed one more, validated against data), `pp_windows` (by era, including reduced-match tables), `field_restr` by window, `free_hit` (`none`, `front_foot`, `all_noballs`, with `p_free_hit_given_nb` when uncertain), `noball_penalty_runs` (1, or 2 in ECB domestic competitions through 2025; men's Blast, Hundred and One-Day Cup 1 from 2026; County Championship 2), `caught_crossing_counts` (true before 2022-10-01 internationally and before IPL 2022), `drs_allowed`, `reviews_per_innings`, `umpires_call_retains_review` (from October 2017), `review_topup_after_80` (Tests 2013-10 to 2017-09: reset to 2), `ucall_zone_era` (2016 widening, 2021 raise to top of bails; anchors only), `test_overs_per_day` (90; 98 for men's four-day Tests; women's Tests mostly four days at about 100), `scheduled_days`, `follow_on_lead` by days remaining when play starts (200 / 150 / 100 / 75 for 5+ / 3-4 / 2 / 1 days), `new_ball_after_overs` (80), `two_new_balls` (ODIs 2011-10 to 2025-07; from July 2025 two balls until over 34), `impact_player` (IPL 2023+, ILT20 2023/24+, Syed Mushtaq Ali 2022/23-2023/24, LPL 2026; BBL X-factor 2020/21-2021/22 and ODI supersub 2005-06 as `supersub`), `tie_break` (`none`, `bowl_out`, `so_boundary_count`, `so_repeat`, by competition, stage and date), `min_overs_for_result` (T20 5, ODI 20).

DRS facts validated against the data (the rules agent reconciles these with its own validation and records conflicts in `docs/cricket-rules.md`):

- Tests: 2008 trial 3 unsuccessful reviews; 2009 to 2013-10: 2; 2013-10 to 2017-09: 2 with a reset to 2 after 80 overs; 2017-10 to 2020-06: 2 with umpire's call retaining; from 2020-07-16: 3. India series 2009-2016-11 played without DRS.
- ODIs: 2 in 2011-01 to 2011-04 (including the World Cup), then 1, then 2 from 2020-08-01.
- T20Is: 1 until 2020; 2 from 2020-08-28.
- Leagues: IPL 1 (2018-21), 2 (2022+); BBL/WBBL none until 2022/23, then 1; Hundred 1 (2021+); CPL 2 from 2022 (none 2019-21); LPL 2 (2021+); SA20, ILT20, MLC, WPL 2; Blast finals only; Super Smash, CSA T20 and county none; PSL 2017-20 to verify.
- `drs_available` per match = rules allow DRS AND (any review recorded in the match OR in the same series_key) AND "reviews" not in `info.missing`; when "reviews" is missing, null and excluded from DRS fits.

## 6. Delivery models

### 6.1 Model form

All three delivery models are multinomial logits fitted by `glm.py`:

```
eta[0] = 0 (reference class)
eta[1:] = intercept + sum_g w_g(row) * theta_g[level_g(row)] @ basis_g + dense(row) @ C + mask(row)
```

- Priors: each group has a per-dimension SD vector (one SD per class), estimated by empirical Bayes (MacKay update `sigma^2 <- sum(theta^2) / sum(gamma)`, `gamma = 1 - v / sigma^2`, v the per-level posterior variance from the Hessian diagonal).
- **Random-walk groups** (competition season, umpire-by-year if used): `theta_t ~ N(theta_{t-1}, tau^2)`, root `N(0, sigma_root^2)`; the forecast for a new season is the latest level.
- **Nested groups:** region × family and then venue × family (the venue SD is the within-region spread); competition, then competition season.
- **Masks:** a per-row class mask sets eta = −30 for impossible classes, identically in the fit and both engines (bowler-credited wicket on no-balls and free hits).
- Observation weights: `w = 0.5 ** (age_days / half_life)`, with one half-life per (fitting family, gender, model), tuned on 2023 from at most three values each. Rows with w < 0.02 are dropped.
- Optimizer: L-BFGS with diagonal preconditioning (the Hessian diagonal plus prior precision at the start point), a per-group gradient-norm stopping rule, and warm starts across cutoffs.
- Fits run per (fitting family, gender, cutoff).

### 6.2 Delivery type `dtype`: classes `legal`, `wide`, `noball`

Groups:

- `fam × phase6`
- `competition season` (random walk)
- `bowl_type`
- bowler (global)
- bowler experience bucket
- bowl-end umpire (on wide and no-ball)
- venue
- `home_status` of the bowling side
- `start_slot × innings` (dew makes the ball harder to grip)

### 6.3 Outcome model: nine classes

`0 dot, 1 one, 2 two, 3 three, 4 four, 5 six, 6 out (bowler-credited: caught, bowled, lbw, stumped, other), 7 run_out, 8 byes/leg-byes`

The class is chosen from runs off the bat: runs 5 map to class 4 and runs 7 to class 5 (exact runs from `runs5_7`); runs 4 with `non_boundary` map to class 4. Wicket balls take class 6 or 7. A ball with both bye/leg-bye runs and bat runs is impossible; a ball with only bye/leg-bye runs takes class 8.

Groups, with levels computed in `features.py` and mirrored exactly in `engine.js`:

1. `phase6`: by balls remaining in the current innings length. For T20, HUNDRED and ODI, boundaries are the fractions of `max_balls` elapsed: [0, 1/10), [1/10, 3/10), [3/10, 1/2), [1/2, 3/4), [3/4, 9/10), [9/10, 1]. Compare with integers: `10*elapsed < max_balls`, ... Tests use one level.
2. `ctx_main` as main effects plus shrunk interactions:
   - `fam × innings`
   - `fam × phase6`
   - `fam × wkts(0..9)`
   - `fam × phase6 × wkts` (interaction, SD estimated)
   - `fam × phase6 × bowl_class` (pace/spin balance)
   - Tests use `innings(1..4) × wkts`.
3. `field_restr`: `fam × field_restr × phase6-coarse`.
4. `chase` (limited-overs second innings, `target_known` and timing not `unknown`): `fam × resource-ratio bucket × phase3`. The ratio is `R = runs_required / Z(balls_remaining, wkts)` from the fitted resource table (section 7.6), with buckets <0.8, 0.8-0.95, 0.95-1.05, 1.05-1.2, 1.2-1.4, 1.4-1.7, ≥1.7.
5. `set`: `fam × striker_balls bucket (0, 1-3, 4-7, 8-15, 16-30, 31-60, 61-120, 121+) × phase3`.
6. `role`: `fam × striker_role_pos bucket (1-2, 3, 4-5, 6-7, 8, 9-11)`.
7. `depth`: `fam × wickets-in-hand-quality bucket` (number of recognized batters still to come, i.e. players with role_pos ≤ 7 not yet batted).
8. Tests:
   - `ball`: ball age bucket (0-9, 10-24, 25-49, 50-79) × second_new_ball × bowl_class × ball_brand.
   - `wear`: region × est_day(1..5) × bowl_class, plus venue × daygroup{1-2, 3, 4-5} × bowl_class shrunk to it.
   - `situation`:
     - innings 3: signed lead {<0, 0-99, 100-199, 200-299, 300+} × expected overs left {≤60, 61-120, 121-200, >200};
     - innings 4: runs_required per expected over left {<2.5, 2.5-3.5, 3.5-4.5, 4.5-6, ≥6} × wkts_bucket3.
   - `session_proxy` (candidate): overs into the estimated day {0-5, 6-30, 31-60, 61+} × region × bowl_class.
9. `competition season` (random walk, under a `fam × gender × year` era walk), with a `phase3` split for the runs classes.
10. `venue` within region: `region × fam`, `venue × fam`, `venue × bowl_class`.
11. `home`: `fam × bat home_status`, `fam × bowl home_status`. Player-by-conditions terms `bat_cond[b, c]` and `bowl_cond[w, c]`, with c ∈ {subcontinent+uae_gulf, SENA, other}. Franchise and domestic: `fam × overseas` for striker and bowler.
12. `matchup`: `fam × bat_hand × bowl_type`.
13. `experience`: `fam × striker_exp bucket`, `fam × bowler_exp bucket` (0, 1-30, 31-120, 121-300, 301-1000, 1000+ prior balls in the family before the match).
14. **Match latent** (one level per match): directions
    - `m_runs` along the scoring direction `s = [0, 1, 2, 3, 4, 6, 0, 0, 1] / 6.5` (exported and used as is);
    - `m_wkt` on class 6;
    - `m_spin` on class 6 with weight +1 for spin, −1 for pace, 0 for unknown;
    - `m_wear` (Tests) on class 6 with weight `(est_day−1)/(scheduled_days−1)`.
    
    Each direction is its own group with a fitted SD.
15. **Team-innings latent** (one level per match × innings): directions `i_runs` (s) and `i_wkt` (class 6), each with a fitted SD.
16. `umpire` (bowl-end): on class 6 only. When the end is unknown the row carries both umpires, with weights p and 1−p (section 6.6). Add `region × bowl_class` on class 6 to absorb confounding.
17. `free_hit`: indicator on classes 4 and 5.
18. **Dense weather:** standardized `rh`, `cloud`, `temp`, `precip_flag` and `elevation`, each times `is_pace` and times `is_spin`. `dew = −dew_depression_evening` applies only in the second innings when `start_slot` is `night` or `day_night`; when `start_slot` is `unknown`, a separate coefficient is used. Training means and SDs are exported.

Player terms:

- Batters: `bat[b]`, `bat_spin[b]` (×is_spin), `bat_death[b]` (×is_death), `bat_start[b]` (×first 10 balls of the innings), `bat_newball[b]` (×powerplay or Test ball age ≤ 15).
- Bowlers: `bowl[w]`, `bowl_death[w]`, `bowl_newball[w]`.
- Player terms apply to all classes except that bowler terms skip class 7 (run-out).
- Unknown players get zero vectors plus their experience, role and context terms.
- Each player's posterior SD along `s` and class 6 is exported (section 8).

Masks: class 6 is masked on no-ball rows and free-hit rows. On no-balls the outcome model gives the bat runs and run-outs.

Rows excluded from the outcome fit:

- retirements without a ball outcome;
- deliveries in matches marked `awarded`;
- second-innings balls with `target_timing = unknown` (these are kept for player terms through a fit-only flag that zeros the chase group).

### 6.4 Dismissal-kind model `wk`: classes `caught, bowled, lbw, stumped, other`

Fitted on on-field bowler-credited outs (class 6) with a known kind.

Groups:

- `fam × phase6`
- `bowl_type`
- `bat_hand × bowl_type`
- bowler
- batter
- bowl-end umpire (lbw)
- venue
- `drs_available × fam` (with venue and region present, to avoid the India/subcontinent confound)
- `free-hit/no-ball`, masked to none

Empirical tables by family: `runout_who` (striker vs non-striker), `runout_runs` (runs completed), and `runout_new_on_strike[who_out][min(r, 2)][dtype]`.

### 6.5 On-field reconstruction and the DRS process

The outcome model predicts the on-field umpire's decision:

| Recorded | On-field class | Final |
| --- | --- | --- |
| wicket, no review | out (class 6, or class 7 for run-outs) | out |
| batting review struck down (umpire's call included) | class 6 (kind as recorded) | out |
| batting review upheld (no wicket recorded) | class 6, kind `lbw` or `caught` (imputed) | not out; the ball is a dot (2,457 of 2,490 are) |
| fielding review upheld (wicket recorded) | dot (all 2,203 have 0 runs) | out |
| fielding review struck down | recorded class | not out |

Reviewable kinds are `lbw` and `caught`. Reviews on wides and no-balls are ignored in the fit.

The kind of an overturned on-field out is imputed so that the reconstructed on-field kind mix stays consistent with the struck-down batting reviews and the era.

`drs.py` estimates the following by `fam × era`, with umpire random effects where the data support them. Each is a logistic function of reviews left (0, 1, 2+), phase, overs to the innings end or to the 80-over top-up, wickets down, striker role and runs, kind and bowl_class.

- `q_bat`: probability the batting side reviews an on-field out.
- `p_overturn_bat`: probability that review succeeds.
- `p_ucall_bat`: probability a failed batting review is umpire's call (LBW only).
- `lambda_field`: per-ball rate of successful fielding reviews. Only the product of missed outs and review propensity is identified. "Missed outs" displayed on the page assume `q_field = 1` and are labelled a lower bound.
- `r_spec`: per-ball rate of failed fielding reviews, and their umpire's-call share.

These apply only on legal non-wicket deliveries:

- `lambda_field` on dots and byes/leg-byes;
- `r_spec` on dots, byes/leg-byes, bat runs and wides, with class-specific rates.

Fit only matches with `drs_available = true`.

### 6.6 Umpire ends

Within an innings the bowler's-end umpire alternates by over parity. In the HUNDRED it alternates by ⌊set/2⌋ parity. Assignments do not carry across innings, because the parity match across innings is close to a coin flip.

For each innings, the probability `p` that umpire 1 stands at even-over ends is set as follows:

- Sources: named reviews and `miscounted_overs` umpire names, allowing a 2% error rate per name.
- Otherwise 0.5.
- Conflicts reset to 0.5.

In training, the umpire term uses weights p and 1−p. In simulation, each innings draws its assignment from p, and the in-play state can fix it.

## 7. Tactics and match structure

### 7.1 Bowler choice

A conditional logit over eligible bowlers, evaluated at each over (set) end.

Eligibility: not the bowler of the previous over's last delivery (HUNDRED v1 excluded), quota remaining, and feasibility. Feasibility means that after giving bowler i this over, the remaining R′ overs can still be covered: Σ_j min(q_j, cap_j) ≥ R′, where cap_j = ⌊R′/2⌋ for j = i and ⌈R′/2⌉ otherwise. Reduced-match unit bonuses are added greedily inside the test.

Utilities:

- the bowler's shrunk log share of overs in this phase;
- spell continuation;
- quota pressure;
- new-ball and opening-bowler bonus;
- Tests: spinner × ball age × day, fatigue by spell length, and second-new-ball take-up;
- a matchup utility: the bowler's predicted wicket and runs value against the current striker and non-striker, with fitted coefficients.

If the scenario's bowling options are infeasible from the start, part-timers are appended in batting order (non-keepers) with zero player vectors, and this is reported. The current bowler finishes the over in-play. Multi-bowler overs are ignored (deviation D2).

### 7.2 Batting order

Pre-match order is the starting XI sorted by each player's median batting position over the team's previous 10 matches in the family (strictly earlier), falling back to the career median and then the role. The page lets the user reorder. There are no nightwatchmen in v1 (deviation D3).

### 7.3 Toss

`P(bat first)` is a logistic in family, competition, venue, start slot, dew climatology and era. Matches with an uncontested toss are excluded from the fit. The model's implied toss value is validated against the empirical figures: toss winners win 54.5% of Tests and about 50% of ODIs and T20s.

### 7.4 Declarations and follow-on (Tests)

Declarations use a discrete-time hazard at over ends, fitted with mid-over declarations assigned to that over's end and a "wicket this over" covariate. Covariates are lead, innings number, expected overs left, wickets down, run rate and day.

- Innings 3 may declare only with lead > 0.
- There are no declarations in innings 4.

Follow-on enforcement is `P(enforce | lead, bowlers' overs just bowled, expected overs left, era)`, applied when lead ≥ the threshold for the days remaining.

### 7.5 Test clock

The availability model is fitted on drawn matches, which reveal it, with censoring for matches that ended in a result. Per-day available overs A_d = opd − L_d, where L_d covers rain and bad light (precipitation and cloud climatology × latitude/month, with capped recovery), less 2 overs per innings changeover.

The engines simulate a ball-level clock: `used = match_legal_balls + 12 × changeovers`. A match is a draw when the sum of A_d is exhausted.

Training `est_day`:

- D = `len(dates_played)`.
- Rate: r = min(opd, O_total / (D − 1 + φ)), with φ = 0.5 for results and 1 for draws.
- est_day = min(D, 1 + ⌊overs / r⌋), refined by spreading lost overs (scheduled − bowled) over days by daily precipitation hours.
- `overs_into_day` is derived the same way.

In simulation, est_day comes from the simulated clock. Expected overs left at a ball is E[remaining A] − used, using climatology and any observed day-loss in-play.

### 7.6 Limited-overs interruptions, DLS-style targets, no result

**Resource table.** Z(u, w) = Z0(w)(1 − exp(−b(w) u)) is fitted on first innings by family and gender. Resources are integer tenths of a percent: P = round(1000 Z(u, w) / Z(N_sched, 0)).

**Revised target.**

- R2 ≤ R1: T = ⌊S·R2/R1⌋ + 1.
- R2 > R1: T = S + ⌊G·(R2 − R1)/1000⌋ + 1, with G = Z(N_sched, 0).

This is a DLS-like table, not the proprietary DLS Professional Edition (deviation D4).

**Interruption schedule.** Drawn at simulation start: count, start point in scheduled match balls (with a point mass at 0 for pre-match reductions), and overs lost. Inputs are precipitation climatology or the user's rain risk.

**Applying an interruption.** It takes effect at the first over end at or after its start, via `apply_interruption(state, lost)`:

- Before innings 2: reduce both innings equally, ending innings 1 if it is already past the new length.
- During innings 2: reduce innings 2 only.

**After every revision.** Recompute `max_balls`, quotas, powerplay windows, phase and chase features.

**Results.**

- A match where innings 2 is cut short is decided against par = T − 1.
- No result when innings 2 is shorter than `min_overs_for_result` before the match is decided.

### 7.7 Ties

Limited-overs ties apply `tie_break` from the rules (deviation D5 records simplifications).

The super over:

- 6 legal balls, 2 wickets maximum; the side that batted second bats first; 1 review each.
- Context: last phase; chase group from the super-over target.
- Batters: the three highest expected runs per ball in the death context against an average bowler with zero latent effects, ties broken by order.
- Bowler: the lowest expected runs per ball, from all of the bowling XI with no quota.
- Repeat while tied, up to 5 times, then a fair coin.

`p_tie` is reported before and after tie-breaks.

In Tests, a tie needs the innings-4 side all out with scores level. Time running out level is a draw.

## 8. Parameter bundles

`params.py` writes:

- `data/processed/cricket/params/{fam}-{gender}-{cutoff}.json`: full precision, for evaluation.
- `docs/cricket/data/params-{gender}.json`: 4-decimal rounding, for the page.

A test asserts that the page bundle differs from full precision by max |Δp| < 1e-3 per ball and |Δp_win| < 0.002 on reference scenarios. The model-card numbers are computed from the page bundle.

Schema:

```
{
  "version", "feature_spec_version", "fit_cutoff", "gender",
  "fams": {
    "T20"|"ODI"|"TEST": {
      "dtype":   {"intercept", "groups": {name: {"levels", "theta", "basis"}}, "dense", "standardize"},
      "outcome": {...},
      "wk":      {...},
      "players": {id: {"bat": [8], "bat_spin", "bat_death", "bat_start", "bat_newball", "bat_cond": {c: [8]},
                       "bowl", "bowl_death", "bowl_newball", "bowl_cond", "dtype_bowl", "wk_bowl", "wk_bat",
                       "sd_runs", "sd_wkt", "exp_balls_bat", "exp_balls_bowl", "role_pos"}},
      "latent":  {"match": {"sd": {...}, "directions": {...}}, "innings": {...}},
      "calibration": {"runs_offset", "wkt_offset", "innings_sd_scale"},
      "empirical": {"bye_runs", "wide_runs", "wide_wkt", "runs5_7", "runout_who", "runout_runs",
                    "runout_new_on_strike", "p_crossed"},
      "drs", "tactics", "time_rain", "resource_table"
    }
  },
  "rules", "venues_ref", "umpires_ref"
}
```

Site support files:

- `players-{gender}.json`: id, name, country, hand, bowl type, recent teams, balls, display ratings with SDs.
- `venues.json`: venue effects in interpretable units, region, climatology.
- `umpires.json`: LBW tendency, wide tendency, DRS accuracy, each with posterior SDs.
- `teams-{gender}.json`: latest likely XIs by team and family, ordered by section 7.2.
- `evaluation.json`.

Players with no delivery since 2019 are dropped from the page bundle. The page payload stays under 12 MB.

## 9. Engine semantics (identical in both engines)

### 9.1 Scenario input

```
{
  "fam": "T20"|"ODI"|"TEST", "gender", "competition_id", "date", "venue_id", "neutral": bool,
  "start_slot": "day"|"day_night"|"night",
  "teams": [{"name", "batting_order": [ids], "bowling_xi": [ids], "home": bool}, {...}],
  "toss": null | {"winner": 0|1, "decision": "bat"|"field"},
  "umpires": [id, id] | null,
  "drs": {"enabled", "reviews_per_innings", "umpires_call_retains", "accuracy_mult", "ucall_mult"},
  "weather": {"temp_c", "rh", "cloud_oktas", "dew_depression_evening", "rain_risk", "days": [...]} | null,
  "pitch": {"known": bool, "runs_sd", "wkt_sd", "spin_sd", "wear_sd"},
  "player_form": {id: {"bat_runs_sd", "bat_wkt_sd", "bowl_runs_sd", "bowl_wkt_sd"}},
  "state": null | <canonical state, 9.3>,
  "n_sims", "seed", "sensitivity": bool
}
```

- Weather fields set to null use climatology.
- If `pitch.known`, the match latent is fixed at slider × SD. Otherwise it is drawn from N(slider × SD, SD²).
- Form sliders shift the player's effect along the exported directions by slider × player SD.

### 9.2 Delivery transition (exact order)

1. Compute every feature from the pre-ball state.
2. Draw dtype (masks applied).
3. **Wide.**
   - Draw wide runs k ∈ 1..5 from `wide_runs[fam]` (5 = boundary).
   - Draw a wicket on the wide from {none, stumped, run_out} with `wide_wkt[fam][bowl_class]`. Stumping off a wide is impossible on a free hit.
   - `ran = k − 1`. No ball is faced and the over does not advance.
4. **No-ball.**
   - Add `noball_penalty_runs` to the team and the bowler.
   - Draw the outcome with class 6 masked: bat runs, byes or a run-out.
   - Skip DRS. The striker's balls faced += 1.
5. **Legal ball.**
   - Draw the outcome class with masks (free hit masks class 6).
   - For class 6, draw the kind and then run the DRS layer (9.4).
   - For non-wicket classes, run the missed-out and speculative-review draws.
6. **Exact runs.**
   - four: 4, or 5 with `runs5_7`;
   - six: 6, or 7;
   - byes/leg-byes: 1–5 from `bye_runs` (4 = boundary);
   - run-out: runs completed from `runout_runs`;
   - other wickets and overturned decisions: 0.
7. **Chase completion.** If team runs + credited ≥ target:
   - Boundaries (bat 4/6 and 5-wide or 4-bye boundaries) count in full.
   - Other runs count as min(runs run, needed), plus any penalty extras.
   - The match ends and any wicket on that delivery is void.
8. **Wicket.**
   - wickets += 1. A run-out's victim comes from `runout_who`.
   - The next unused batter comes in; with none left, the side is all out.
   - The new batter takes the striker's end for non-run-out kinds. Exception: a catch when `caught_crossing_counts`, where the new batter goes to the non-striker's end with probability `p_crossed[fam]`.
   - Run-outs use `runout_new_on_strike`.
9. **No wicket:** swap ends iff `ran` is odd, where `ran` = bat runs + byes + leg-byes + (wides − 1), excluding no-ball penalty and penalty extras.
10. **Counters.**
    - A legal ball increments innings legal balls, `ball_in_over` and the bowler's balls.
    - The pre-ball striker's balls faced += 1 on legal balls and no-balls.
    - The bowler is charged bat runs, wides and the no-ball penalty, not byes or leg-byes.
11. **End checks, in order:** target reached; all out (unavailable = 10, or no batter left); balls exhausted; Test clock exhausted.
12. **Over end.**
    - Swap ends.
    - Over-level draws, in order: interruption application, declaration (Tests), follow-on decision (at innings end), next bowler, new-ball take-up (Tests).
13. **Free hit for the next delivery.** Set it when this delivery is a no-ball and the rules give a free hit (or with `p_free_hit_given_nb`), or when this delivery was a free hit and was a wide or no-ball. Clear it after a legal delivery.

### 9.3 Canonical state (in-play)

Per innings so far: batting team, runs, wickets, legal balls, `max_balls`, and the target.

For the current innings:

- `legal_balls` (the page's "12.3" means 75);
- striker and non-striker ids with their runs and balls;
- dismissed and unavailable ids;
- next-batter index;
- each batter's arrival rank;
- bowler balls and runs per bowler;
- current bowler (mid-over) and last bowler;
- free hit;
- reviews left per side;
- umpire end assignment;
- partnership;
- balls bowled so far as an optional list, for the latent update.

Tests also carry: `innings_team` order, used balls toward A and the remaining A, ball-age reset, and spells.

`app.js` fills unknown fields deterministically and shows them:

- batters: the next two not yet dismissed, at 0 runs and 0 balls;
- bowler overs: filled greedily, respecting the consecutive-over and quota rules.

Both engines check invariants:

- wickets = dismissed count;
- Σ bowler balls = legal balls;
- no current batter is dismissed;
- runs_required > 0;
- legal_balls < max_balls.

In-play latent update: Newton iterations from 0 for the match and current-innings latents on the outcome-model likelihood of the balls bowled. Use exactly 10 iterations, no line search, with the fitted prior SDs. Each simulation then draws from the Laplace posterior N(mode, H⁻¹), via a Cholesky factor of the small Hessian.

### 9.4 DRS layer in the engine

**On-field out (class 6) with a reviewable kind (lbw, caught), when DRS is enabled and the batting side has reviews left:**

1. The batting side reviews with probability `q_bat`.
2. A review is overturned with probability min(1, `p_overturn_bat` × accuracy_mult). An overturned review becomes a dot ball.
3. A review that is not overturned is umpire's call with probability min(1, `p_ucall_bat` × ucall_mult), on LBW only.
4. A failed review costs a review unless it was umpire's call and the rules retain reviews.

**Legal dot or bye/leg-bye with DRS enabled and the fielding side holding reviews:**

- With probability min(1, `lambda_field` × accuracy_mult), it is a successful fielding review: out, with kind from the missed-out kind mix, runs 0.
- Then, with probability `r_spec` (class-specific), the fielding side spends a review on a not-out that stands. Umpire's-call retention applies.

**DRS disabled:** on-field decisions stand, and the dismissal-kind model uses its `drs_available = false` level.

Reviews reset each innings. The Test top-up after 80 overs follows the rules.

### 9.5 Random numbers

Generator: xoshiro128**.

- `fmix32` is the murmur3 finalizer:
  ```
  x ^= x >>> 16; x = imul(x, 0x85EBCA6B);
  x ^= x >>> 13; x = imul(x, 0xC2B2AE35);
  x ^= x >>> 16
  ```
- `splitmix32` advances by the Weyl increment 0x9E3779B9 and returns `fmix32` of the state.
- The 128-bit state for (seed, sim, stream) is four `splitmix32` outputs from `key = fmix32(fmix32(seed ^ 0x243F6A88) ^ stream_id) ^ sim`. If the result is all zero, set word 0 to 1.

Streams and their fixed uniforms per event, consumed whether or not they are needed:

- 0 = ball, 12 per delivery: dtype, outcome, exact runs, kind or wide-wicket, run-out who, run-out end or crossing, bat review taken, overturn, umpire's call, missed out, field review, speculative.
- 1 = over, 4 per over end: interruption, declaration, bowler, new ball.
- 2 = innings, 4 per innings start: follow-on, umpire end, two spare.
- 3 = match, 64 per match: toss coin, toss decision, latent normals, Test day availability, interruption schedule, spares.
- 4 = player, 4 per player slot: form normals for runs and wicket, for batting and bowling.

Conversions:

- Uniform: u = x · 2⁻³².
- Categorical: running float64 sums of exp(eta_k − max) in class order; pick the first k with u·cum_last < cum_k, falling back to the last class.
- Bernoulli: u < p.
- Normal: Box–Muller with log(1 − u).

The numpy engine never calls `np.random`. The known-answer vectors in `tests/data/cricket_parity/prng_kat.json` are generated once and checked by both engines.

### 9.6 Precision, parity and performance

**Precision.** All engine arithmetic is float64. Parity tests load the page bundle in both engines.

**Test vectors:**

- `features.jsonl`: state → every group level and per-group eta contribution, `p_dtype`, raw and masked `p_outcome`, `p_wk`, the DRS probabilities, bowler eligibility and choice probabilities, and the declaration and follow-on hazards. Tolerance 1e-9.
- `transitions.jsonl`: scripted draws → exact post-state. Cases:
  - 1 run needed with a 5-wide;
  - a free hit followed by a wide, then a run-out;
  - a wicket on the last ball;
  - 10 wickets;
  - 9 wickets with one batter absent;
  - a run-out with 1 run completed;
  - a catch before and after 2022;
  - a quota dead end;
  - a DLS revision mid-innings;
  - a follow-on followed by an innings defeat;
  - a fourth-innings tie;
  - ball 80 in a Test;
  - a super over.
- `trajectories.jsonl`: seed + scenario → full ball log for sims 0–2. Results must match exactly; a mismatch is allowed only when |u·S − cum_k| < 1e-12 at the first divergence.

**JS performance targets:**

- At least 1.5M deliveries per second per worker; min(4, hardwareConcurrency − 1) workers over sim ranges.
- Defaults: 10k sims for limited overs, 4k for Tests.
- Progress every 500 sims; cancellation checked between sims.
- Precompute static eta per scenario: player pairs × innings × death × umpire parity.
- No per-ball allocation.

**Python engine:** scalar, one simulation at a time, written for clarity; it must reproduce `engine.js` trajectories exactly. Bulk evaluation calls `node docs/cricket/cli.js` with JSON-lines scenarios and reads JSON-lines results.

**Probability provider.** Both engines separate match flow (`engine.js` / `sim.py`) from probabilities (`provider.js` / `beating/cricket/provider.py`). The provider interprets the declarative feature spec and the parameter bundle. Its interface is: delivery-type, outcome and dismissal-kind probabilities for a pre-ball state; bowler-choice utilities; toss, declaration, follow-on and new-ball probabilities; DRS probabilities; empirical tables; latent-effect directions and SDs; interruption and Test-clock draws. A stub provider with small hand-set tables exists for tests.

### 9.7 Outputs

- `p_win` per team, `p_tie` (before and after tie-break), `p_draw`, `p_no_result`, each with MC standard errors.
- Per-innings score and wicket distributions.
- Runs by over: mean and 10/50/90%.
- Margin distribution.
- Per player:
  - balls faced (legal + no-balls), runs, P(50+), P(100+);
  - bowler runs (bat runs + wides + no-ball penalty), wickets (excluding run-outs, retirements, obstructing, timed out), P(3+), economy per 6 legal balls.
- Dismissal-kind mix.
- DRS counters: reviews used, overturns, umpire's calls, and missed outs standing as a lower bound.
- Sensitivity: each factor reset to neutral using common random numbers, with paired-difference SEs.

## 10. Evaluation protocol (declared before any test-window result)

**Cutoffs.** Hyperparameter validation fits at 2023-01-01, scored on 2023. Walk-forward fits every six months, at 2024-01-01, 2024-07-01, 2025-01-01, 2025-07-01, 2026-01-01 and 2026-07-01. Each window runs to the next cutoff; the last ends 2026-10-14. Fits warm-start from the previous cutoff. The final page fit uses all data.

**Clean pre-match inputs.**

- Starting XI (squad minus replacement-in players), ordered by section 7.2.
- No impact substitute in v1 (deviation D6).
- Toss as recorded; venue; officials.
- Weather from climatology computed on data before the cutoff, with an oracle-weather ablation.
- Start slot from the curated table.

**Simulator calibration.**

- Stage A, on 2023 only: per fitting family and gender, choose at most three scalars (runs offset, wicket offset, innings-latent SD scale) to match the mean and SD of first-innings totals, wickets, and Test overs. Freeze them and ship them in the bundle.
- Stage B (optional): a win-probability temperature per family (Dirichlet for Tests), fitted only on earlier windows' out-of-sample predictions. Adopt it only if earlier-window log loss improves. Report raw and calibrated results.

**Primary pre-registered family.** For each delivery model, the held-out ball-level log loss gain of each component over Full-minus-component, pooled over windows. Use a paired bootstrap resampling matches, with Holm correction. Components:

- players
- venue/region
- home/conditions
- competition season
- match/innings latents
- umpire
- weather
- matchup
- experience
- Test wear/situation

**Descriptive outcomes:**

- Innings-total PIT, with an acceptance target: simulated/actual SD of first-innings totals within 0.9–1.1.
- Match-level pre-match win probability: log loss and Brier, calibration in ten bins, match-bootstrap 95% intervals, and the minimum detectable difference stated for each sample.
- In-play win probability at each innings start and every 5 overs (limited overs) or every 30 overs (Tests), bootstrapped by match. Also score the imputed minimal state.
- Test three-way log loss (descriptive; about 110 men's Tests).

**Scoring rules.** Limited-overs ties are scored by the tie-break winner when one exists, otherwise as half. No-results and awarded matches are excluded.

**Samples, fixed now:**

- Men's: internationals (full members), associate internationals, and major T20 leagues (IPL, BBL, PSL, CPL, SA20, ILT20, MLC, Hundred excluded in v1, Blast, Super Smash, LPL, BPL).
- Women's: internationals, WPL, WBBL.

**Baselines:**

- coin flip;
- Elo continuous (updated every match);
- Elo frozen at each cutoff (same information schedule as the model);
- an XI-aware logistic on summed shrunk player ratings plus toss and home.

**Diagnostics:** the gap between leaky and clean inputs (realized batting order and realized weather) is reported once.

## 11. Web page (`docs/cricket/`)

- **Technical:** static and self-contained (no CDN; hand-written SVG charts); works offline; loads in under 3 s; light and dark themes; usable at phone width. Simulations run in Web Workers with progress and cancel.
- **Inputs:**
  - format and gender;
  - team and XI pickers with search, defaulting to the latest likely XI;
  - batting order reorder, bowling XI and impact substitute;
  - per-player form sliders;
  - venue, with its profile (venue effects in runs-per-over and wickets-per-innings units vs average) and pitch sliders (batting ease, wicket-taking, spin vs pace, wear), plus a "pitch known" toggle;
  - home / neutral;
  - start slot;
  - weather prefilled from climatology for the chosen month, with per-day rain for Tests;
  - umpire pickers showing LBW and wide tendencies and DRS accuracy with uncertainty;
  - DRS settings;
  - toss;
  - live state entry;
  - number of sims and seed.
- **Outputs:**
  - headline probabilities with MC error;
  - innings score histograms;
  - worm chart with bands;
  - margin distribution;
  - player projections;
  - dismissal-kind and DRS summaries;
  - "what moved the needle" sensitivity bars;
  - saved-scenario comparison;
  - a model-card tab with evaluation numbers, calibration charts, data provenance and limits.

## 12. Compute constraints for this build

The machine has 4 CPUs and 15 GB RAM, shared by parallel agents.

- Any job needing over 1.5 GB RAM or more than two CPU-minutes runs under `flock /tmp/claude-0/-home-user-BeatingAnything/dca149a3-fa9a-5e66-94bf-d6c38ea6be14/scratchpad/cricket-heavy.lock <command>`.
- Each agent uses its own scratch subfolder.
- Use the virtual environment `/home/user/BeatingAnything/.venv`: Python 3.12, numpy 2.3.5, pandas 2.2.3, scipy 1.17.0, pyarrow 21.0.0, pyreadr.
- Develop on small slices first.

## Deviations

- D1: The Hundred is used in T20-family training with its own context levels but is not simulated by the v1 engines.
- D2: Multi-bowler overs (0.09% of overs) are not simulated; the bowler who starts an over finishes it.
- D3: No nightwatchman or situational batting-order changes in simulation (the page allows manual reordering).
- D4: Revised targets use a fitted DLS-like resource table, not DLS Professional Edition.
- D5: Bowl-outs and boundary-count tie-breaks are simplified to a coin flip and the repeated super over respectively, where the rules call for them.
- D6: Pre-match evaluation uses no impact substitute; the page lets the user add one.
- D7: Simulated retirements (hurt) are not drawn.
