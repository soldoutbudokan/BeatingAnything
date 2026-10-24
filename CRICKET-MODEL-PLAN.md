# Cricket win-probability model plan

Written October 24, 2026. Goal: a bottom-up, ball-by-ball Monte Carlo model of cricket matches (T20, ODI, Test; men's and women's) that rates players, pitch, venue, umpires, DRS rules and weather, and an interactive static web page that runs the same simulator in the browser.

This file is the contract between components. Every module, parameter file and the browser engine follows it. When an implementation must deviate, it records the deviation in the "Deviations" section at the bottom with a reason.

## 1. Principles

- **Bottom-up.** Win probability is never fitted directly. It emerges from simulating every delivery: delivery type (legal/wide/no-ball), outcome (dot, 1, 2, 3, 4, 6, wicket, byes), dismissal kind, the DRS review process, bowler choice, declarations, weather interruptions and target revisions.
- **No lookahead.** Every fitted quantity used to forecast a match is estimated from data dated strictly before that match's first day. Walk-forward fits use explicit cutoffs.
- **Shrinkage everywhere.** Player, venue, umpire and season effects are random effects (Gaussian priors, i.e. penalized maximum likelihood) so a player with 40 balls stays near their role prior.
- **One semantics, two engines.** The Python engine (`beating/cricket/sim.py`) is the reference used for evaluation. The browser engine (`docs/cricket/engine.js`) implements the same formulas. Parity tests compare exact per-ball probability vectors from shared test vectors and statistical agreement of simulated outputs.
- **Measured, not assumed.** Every component (weather, umpire, pitch effect, matchups) must earn its place on held-out log loss. Components that do not improve held-out log loss are still exposed on the web page as user-adjustable what-if inputs but carry a fitted coefficient near zero, and the report says so.

## 2. Data sources (verified reachable October 24, 2026)

| Source | What | Access |
| --- | --- | --- |
| Cricsheet `all_json.zip` (data version 1.3.0, created 2026-10-14) | 23,132 matches, 11.69M deliveries, all formats, men and women; officials, toss, XIs, powerplays, replacements (impact player, concussion), 17,153 DRS reviews with reviewing team, umpire, decision and umpire's-call flag | `https://cricsheet.org/downloads/all_json.zip` |
| Cricsheet people register | identifiers including Cricinfo keys | `https://cricsheet.org/register/people.csv`, `names.csv` |
| cricketdata R package `player_meta` | 16,101 players: batting hand, bowling style, playing role, DOB, country, keyed by Cricsheet id | `git clone https://github.com/robjhyndman/cricketdata` (`data/player_meta.rda`, read with `pyreadr`) |
| NOAA ISD-lite (AWS open data) | hourly temperature, dew point, sea-level pressure, wind, sky cover, 1h/6h precipitation per station-year | `https://noaa-isd-pds.s3.amazonaws.com/isd-lite/data/{YYYY}/{USAF}-{WBAN}-{YYYY}.gz`, station list `isd-history.csv` |
| NOAA GSOD (AWS open data) | daily summaries with fog/rain/thunder flags; fallback when ISD-lite is sparse | `https://noaa-gsod-pds.s3.amazonaws.com/{YYYY}/{USAF}{WBAN}.csv` |

Blocked from this container (do not retry): Open-Meteo, ESPNcricinfo, Cricbuzz, Wikipedia, Kaggle, Zenodo, Betfair, The Odds API, CDNs. No historical odds source is reachable, so market comparison is out of scope for this build and is listed as the next step.

Raw downloads live under `data/raw/cricket/` (git-ignored). Processed tables live under `data/processed/cricket/` (git-ignored, parquet via `pyarrow`). Small curated or derived files that the page or reproducibility needs are committed under `config/` or `docs/cricket/data/`.

Known data limits: Cricsheet has no ball timestamps, no day/session markers in Tests, no match start times (day/night), no ball-tracking, no boundary dimensions, and no record of appeals that were turned down and not reviewed.

## 3. Repository layout

```
beating/cricket/__init__.py
beating/cricket/ingest.py        Cricsheet -> matches/balls/players/officials tables
beating/cricket/players.py       player metadata (hand, bowling type) + fallback inference
beating/cricket/venues.py        venue canonicalisation, coordinates, station matching
beating/cricket/weather.py       ISD-lite/GSOD download + per-match weather features
beating/cricket/rules.py         playing-conditions timeline (overs, powerplays, quotas, DRS, free hit, follow-on)
beating/cricket/features.py      state -> context indices (THE shared feature definitions, mirrored in engine.js)
beating/cricket/glm.py           penalized multinomial logit with random-effect groups (numpy/scipy)
beating/cricket/fit_ball.py      fits delivery-type, outcome and dismissal-kind models
beating/cricket/drs.py           DRS review-process estimation
beating/cricket/tactics.py       bowler choice, toss, declaration, follow-on, batting order defaults
beating/cricket/time_rain.py     Test overs-available model, limited-overs rain interruptions, DLS-style resource table
beating/cricket/params.py        assembles and exports parameter bundles (JSON) for both engines
beating/cricket/sim.py           reference vectorized Monte Carlo engine
beating/cricket/evaluate.py      walk-forward evaluation, baselines, calibration, ablations
tools/build_cricket_site_data.py exports docs/cricket/data/*.json for the web page
docs/cricket/index.html, app.js, engine.js, worker.js, styles inline   static interactive page (no external libraries)
tests/test_cricket_*.py          unit + parity tests (parity tests call `node` and skip if absent)
config/cricket-venues.csv        curated venue table
config/cricket-rules.json        playing-conditions timeline
requirements-cricket.txt         pinned optional extras (pyarrow, pyreadr)
reports/cricket-*.md|json        evaluation outputs
```

Python scripts under `tools/` use `# %%` cell markers so they run in chunks in VS Code. Package modules follow the existing `beating/` style.

## 4. Canonical tables

### 4.1 `matches` (one row per Cricsheet match)

`match_id` (int, Cricsheet file stem), `start_date`, `end_date`, `n_days`, `season`, `match_type` (Cricsheet: T20, IT20, ODI, ODM, Test, MDM), `fmt` (family: `T20`, `ODI`, `TEST`; plus `HUNDRED` when the event is The Hundred), `gender`, `team_type`, `event_name`, `competition_id` (canonical competition string, see 4.5), `match_number`, `venue_raw`, `city`, `venue_id` (canonical, from `config/cricket-venues.csv`), `team1`, `team2`, `toss_winner`, `toss_decision`, `winner`, `result` (`win`, `tie`, `draw`, `no_result`), `method` (e.g. `D/L`), `win_by_runs`, `win_by_wickets`, `eliminator` (super-over winner), `scheduled_overs`, `balls_per_over`, `umpire1_id`, `umpire2_id`, `tv_umpire_id`, `referee_id`, `xi_team1`, `xi_team2` (JSON lists of player ids as listed), `bat_order_team1`, `bat_order_team2` (actual arrival order), `impact_or_sub_events` (JSON), `reviews_missing` (bool, from `info.missing`), `drs_observed` (any review recorded), `n_innings`, `super_over` (bool).

### 4.2 `balls` (one row per delivery, super overs excluded and stored separately)

Identity: `match_id`, `innings` (1..4), `bat_team`, `bowl_team`, `over` (0-based), `ball_seq` (0-based delivery index within innings), `legal_ball_index` (0-based count of legal balls before this one in the innings), `ball_in_over` (legal balls already bowled in this over), `batter_id`, `non_striker_id`, `bowler_id`.

Recorded outcome: `runs_batter`, `runs_extras`, `runs_total`, `wides`, `noballs`, `byes`, `legbyes`, `penalty`, `dtype` (`legal`, `wide`, `noball`), `wicket` (bool), `wicket_kind` (raw), `wk` (canonical: `caught`, `bowled`, `lbw`, `run_out`, `stumped`, `other`; caught-and-bowled -> caught; hit wicket/obstructing/handled/hit twice/timed out -> other; retired hurt/retired not out are not wickets and are stored in `retired` columns), `player_out_id`, `out_is_striker`, `second_wicket` (bool, rare).

Review: `review_by` (`bat`, `bowl`, null), `review_decision` (`upheld`, `struck_down`, `technical`), `review_umpires_call` (bool or null when the field predates recording), `review_umpire_id`, `review_batter_id`.

On-field reconstruction (section 6.4): `onfield_out` (bool), `onfield_wk` (canonical kind or `unknown_reviewable`), `final_out` (= `wicket`).

State before the delivery: `inn_runs`, `inn_wkts`, `inn_legal_balls`, `striker_balls`, `striker_runs`, `nonstriker_balls`, `nonstriker_runs`, `partnership_runs`, `partnership_balls`, `striker_position` (arrival order 1..11), `bowler_balls_inn` (legal balls by this bowler so far in innings), `bowler_spell_overs` (consecutive-alternate-over spell length, Tests), `free_hit` (bool), `powerplay` (`none`, `mandatory`/`pp1`, `batting`, `fielding`, from Cricsheet `powerplays`), `balls_remaining` (limited overs, using the innings' effective scheduled/revised balls), `target` (chase innings), `runs_required`, `match_legal_balls` (cumulative legal balls in match before this ball, Tests), `ball_age_overs` (overs since the current ball was taken, Tests: resets when the new ball is due at 80 overs and the bowling side is assumed to take it), `est_day` (Tests: `1 + floor(match_overs / overs_per_day)`, capped at the scheduled days), `lead` (batting side's runs minus opponent's, Tests, before this ball), `test_overs_left_est` (scheduled match overs minus overs bowled, Tests), `bowl_end_umpire_id` (section 6.5), `bowl_end_umpire_known` (bool), `bat_reviews_left`, `bowl_reviews_left` (reconstructed per section 6.4), `drs_available` (bool).

Indexing: the training code maps string ids to dense int32 indices (`players.idx`, `venues.idx`, ...). Use int8/int16/int32/float32 dtypes; the full table must fit in about 3 GB of RAM.

### 4.3 `players`

`player_id` (Cricsheet registry hex id), `name`, `unique_name`, `cricinfo_id`, `bat_hand` (`R`, `L`, `U`), `bowl_type` (one of `pace_fast`, `pace_medium`, `off_spin`, `leg_spin`, `left_orth`, `left_wrist`, `none`, `unknown`), `bowl_arm` (`R`, `L`, `U`), `bowl_class` (`pace`, `spin`, `none`, `unknown`), `role`, `dob`, `country`, `meta_source` (`cricinfo_meta`, `inferred`, `none`), `infer_confidence`.

Mapping: "Right arm Fast", "Right arm Fast medium", "Left arm Fast", "Left arm Fast medium", "Right arm Medium fast", "Left arm Medium fast" -> `pace_fast`; "Medium", "Slow medium", "Medium" variants -> `pace_medium`; "Offbreak" -> `off_spin`; "Legbreak", "Legbreak Googly" -> `leg_spin`; "Slow Left arm Orthodox" -> `left_orth`; "Left arm Wrist spin" / "chinaman" -> `left_wrist`. Multiple styles: use the first listed, record the second. Unmatched bowlers who bowled at least 60 balls are inferred from data (stumping share of their dismissals, phase usage, wide/no-ball rates, keeper-standing-up proxy) with a classifier trained on players whose type is known; record `infer_confidence`.

### 4.4 `venues` (`config/cricket-venues.csv`, curated and committed)

`venue_id` (slug), `name`, `aliases` (pipe-separated Cricsheet `venue` strings), `city`, `country`, `region` (`subcontinent`, `sena_eng`, `sena_aus`, `sena_nz`, `sena_sa`, `west_indies`, `uae_gulf`, `other`), `lat`, `lon`, `elevation_m`, `utc_offset_hours` (standard time), `isd_station` (USAF-WBAN), `station_distance_km`, `coord_confidence` (`high`, `medium`, `low`). Every venue string that appears in Cricsheet maps to exactly one `venue_id`. Coordinates must be checked against the matched station's country and a distance under 60 km; violations are flagged, not silently accepted.

### 4.5 Competitions and seasons

`competition_id` is a canonical slug per gender and format (`intl_t20_m`, `intl_odi_m`, `intl_test_m`, `ipl`, `bbl`, `psl`, `cpl`, `sa20`, `ilt20`, `mlc`, `blast`, `hundred_m`, `wpl`, `wbbl`, `county_championship`, `sheffield_shield`, ...). International matches between associate members share the international competition id but carry an `assoc_match` flag. The `season_key` is `competition_id` plus the Cricsheet season.

### 4.6 `weather_match` (derived; committed as a compact CSV for the page and reproducibility)

Per match and per scheduled day: `station`, `distance_km`, `n_obs`, `temp_c_mean`, `rh_mean`, `dewpt_c_mean`, `dew_depression_evening` (temperature minus dew point averaged over local 18:00 to 23:00 using `utc_offset_hours`), `cloud_oktas_mean` (if the station reports sky cover), `precip_mm_day`, `precip_hours`, `wind_ms_mean`, `pressure_hpa_mean`, `elevation_m`. Missing is NaN; models impute to the venue-month climatology, then the global mean, and carry a missing indicator.

## 5. Rules timeline (`config/cricket-rules.json`)

For each (`competition_id` or `fmt`/`gender` default, date range): `overs_per_innings`, `balls_per_over`, `bowler_quota_overs` (T20 4, ODI 10, Hundred 20 balls), `powerplay_overs` (mandatory/batting/fielding windows), `free_hit` (`none`, `front_foot`, `all_noballs`), `noball_extra_runs` (1, or 2 in some domestic competitions), `drs_available`, `reviews_per_innings`, `umpires_call_retains_review` (true from October 2017), `review_topup_after_80` (Tests 2013 to 2017), `test_overs_per_day`, `test_days`, `follow_on_lead` (200 for five-day, 150 for shorter), `new_ball_after_overs` (80), `impact_player` (IPL 2023+), `super_over` (limited overs ties), `min_overs_for_result` (T20 5, ODI 20).

Facts must be validated against the data: for example, the maximum count of unsuccessful, non-umpire's-call reviews by one team in one innings is 3 in Tests from 2020 onward and 2 in ODIs from 2020 onward, while T20 shows 1 until 2018 and 2 from 2019. Where memory and data disagree, data wins and the disagreement is recorded.

## 6. Delivery models

All three delivery models are multinomial logits fitted by `glm.py` with this structure:

```
eta[k] = intercept[k]
       + sum over categorical groups g:  B_g[level_g(row), k]
       + sum over dense features j:      x_j(row) * C_j[k]
       + player and official terms (below)
P(k)   = softmax(eta)[k]
```

Class 0 is the reference and is fixed at eta = 0. Every group has a Gaussian prior with its own standard deviation `sigma_g` (one hyperparameter per group, tuned on the validation year). Observations carry time-decay weights `w = 0.5 ** (age_days / half_life_fmt)` relative to the fit cutoff, with half-lives tuned per format family. Rows with weight under 0.02 are dropped.

### 6.1 Delivery type model `dtype`: classes `legal`, `wide`, `noball`

Groups: `fmt_gender x phase`, `competition season`, `bowl_type`, bowler (global), bowler x fmt, bowl-end umpire (or average of the two umpires when unknown, see 6.5), venue. Dense: free-hit flag is irrelevant here; weather wind if available.

### 6.2 Outcome model `outcome` (legal deliveries and the bat-runs part of no-balls): classes

`0 dot, 1 one, 2 two, 3 three, 4 four, 5 six, 6 wicket(on-field out), 7 byes/leg-byes`

Runs 5 map to class 4 and runs 7 map to class 5, with the exact runs drawn from the conditional empirical distribution. A wicket ball's runs (run-outs while running) and the bye/leg-bye run count come from empirical conditional tables by format.

Groups (levels computed by `features.py`; identical code paths in `engine.js`):

1. `ctx_main`: limited overs: `fmt_gender x innings(1|2) x phase6 x wkts(0..9)`; Tests: `gender x innings(1..4) x wkts(0..9)`.
2. `powerplay`: `fmt x powerplay type`.
3. `chase` (limited overs second innings): `fmt x rrr_bucket x wkts_bucket3`. `rrr = 6 * runs_required / balls_remaining`. T20 buckets: <6, 6-7.5, 7.5-9, 9-10.5, 10.5-12, 12-14, 14-18, >=18. ODI: <4, 4-5, 5-6, 6-7, 7-8, 8-10, >=10. `wkts_bucket3`: 0-3, 4-6, 7-9.
4. `set`: `fmt x striker_balls bucket` with buckets 0, 1-3, 4-7, 8-15, 16-30, 31-60, 61-120, 121+.
5. `position`: `fmt x striker_position bucket` with buckets 1-2, 3, 4-5, 6-7, 8, 9-11. This gives role priors so unknown players start near their slot.
6. `test_ball`: Tests: `ball_age bucket (0-9, 10-24, 25-49, 50-79, 80+) x bowl_class`.
7. `test_wear`: Tests: `region x est_day(1..5) x bowl_class`.
8. `test_situation`: Tests: innings 3 and 4 by lead/target bucket x overs-left bucket (to capture batting-for-a-draw and declaration-chasing intent).
9. `competition season`: `season_key`. For future matches, the most recent `season_key` of the competition is used, shrunk toward the competition mean.
10. `venue`: `venue_id x fmt`, and `venue_id x bowl_class` (shrunk harder).
11. `matchup`: `fmt x bat_hand x bowl_type`.
12. `match` (2-dimensional random effect per match, the latent "pitch on the day"): enters as `m_runs * s + m_wkt * e_W`, where `s` is a fixed scoring direction (`s = [0, 0.25, 0.5, 0.75, 1, 1.5, 0, 0]` before normalisation by its fitted scale) and `e_W` is the wicket indicator. `sigma_match_runs` and `sigma_match_wkt` are fitted. In simulation the pre-match value is 0 (or the user's pitch slider in standard-deviation units); in-play it is updated from the balls already bowled (section 9.3).
13. `umpire` (bowl-end umpire) on the wicket class only.

Dense features, each multiplied by `is_pace` and `is_spin` indicators separately: standardized `rh`, `cloud`, `temp`, `precip_flag`, `elevation`, and (limited overs second innings only) `dew_evening = -dew_depression_evening` standardized. The fit standardizes with training means and SDs and exports them.

Player terms:

- Batter: `bat[b]` + `bat_fmt[b, fmt]` + `is_spin * bat_spin[b]` + `is_death * bat_death[b]` (death = last 4 overs of a T20 innings or last 10 overs of an ODI innings).
- Bowler: `bowl[w]` + `bowl_fmt[w, fmt]` + `is_death * bowl_death[w]`.
- Non-striker: none.

All player vectors have 7 free entries (classes 1..7). Unknown players in simulation get zero vectors, so their prior is their position, format and context.

Free hit: on a free-hit ball the wicket class is restricted to run-outs. The engine multiplies `P(wicket)` by the run-out share and renormalizes.

### 6.3 Dismissal-kind model `wk`: classes `caught, bowled, lbw, run_out, stumped, other`

Fitted on on-field out events with known kind. Groups: `fmt x phase6`, `bowl_type`, `bat_hand x bowl_type`, bowler, batter, bowl-end umpire (lbw-sensitive), venue, `drs_available x fmt`. Also: empirical `P(non-striker out | run_out)` by format and phase, and the runs completed on run-outs.

### 6.4 On-field reconstruction and the DRS process

The outcome model predicts the **on-field umpire's decision**, not the final result. Reconstruction from Cricsheet reviews:

| Recorded | On-field | Final |
| --- | --- | --- |
| wicket, no review | out | out |
| batting review, struck down (incl. umpire's call) | out | out |
| batting review, upheld (no wicket recorded) | out (kind `unknown_reviewable`) | not out |
| fielding review, upheld (wicket recorded) | not out | out |
| fielding review, struck down | not out | not out |

`drs.py` estimates, by `fmt x era` (era boundaries from the rules timeline) and with umpire random effects where data allows:

- `q_bat(state)`: probability the batting side reviews an on-field out of a reviewable kind (`lbw`, `caught`, `stumped`... not `run_out` or `bowled`), as a logistic function of reviews left, striker position, striker runs, wickets down, phase and kind.
- `p_overturn_bat(kind, umpire)`: probability a batting review succeeds. `p_ucall_bat`: share of failed batting reviews that are umpire's call (review retained when the rules say so).
- `r_missed(state, umpire, bowl_class)`: per-ball rate of on-field not-out decisions that are actually out. Identification: compare the per-ball rate of successful fielding reviews when the fielding side has reviews left versus none left. `q_field` is the share of such missed outs the fielding side reviews when it can.
- `r_spec(state)`: per-ball rate of unsuccessful speculative fielding reviews, and their umpire's-call share.
- Kind split of overturned outs (`unknown_reviewable` rows): estimated so that the reconstructed on-field kind mix is consistent with batting-review struck-down kinds and era LBW rates.

Simulation of each delivery with the DRS layer (rules from the scenario):

1. Draw delivery type, then the on-field outcome from the outcome model, then the kind if out.
2. If on-field out with a reviewable kind and DRS is on and the batting side has reviews left: review with `q_bat`; if reviewed, overturn with `p_overturn_bat` -> not out (the ball becomes a dot ball, or leg-byes per the empirical table). A failed review costs a review unless it was umpire's call and the rules retain reviews.
3. If on-field not out (and not a wicket): with probability `r_missed` the decision is a missed out. If DRS is on and the fielding side has reviews left, it reviews with `q_field` and the batter is out (kind drawn from the missed-out kind mix, mostly lbw/caught). Otherwise the batter survives. Separately, with probability `r_spec` the fielding side burns a review on a not-out that stands.
4. With DRS off: on-field outs stand and missed outs stand. Umpire behavior also shifts: `drs_available` enters the dismissal-kind model, so LBW shares follow the no-DRS era.

The web page exposes: DRS on/off, reviews per innings, umpire's call retains review, an umpire-accuracy multiplier on `r_missed` and `p_overturn_bat`, and a "ball-tracking margin" multiplier on the umpire's-call share.

### 6.5 Umpire end assignment

Two on-field umpires each keep one end; the bowler's-end umpire therefore alternates by over parity within an innings. For each innings, the assignment (umpire 1 on even or odd overs) is identified when a review in that innings names an umpire; reviews in other innings of the same day/match propagate through ends (bowlers usually bowl from the same end in consecutive spells). When unidentified, the bowl-end umpire feature is the average of both umpires' effects (`bowl_end_umpire_known = False`). Report the share of balls with identified ends.

## 7. Tactics and match-structure models (`tactics.py`, `time_rain.py`)

- **Bowler choice per over:** conditional logit over eligible bowlers (not the previous over's bowler; quota not exhausted in limited overs). Utilities: bowler's shrunk log share of overs in this phase (from history, by format), spell-continuation bonus (bowled the over before last), quota pressure (overs needed to finish the quota vs overs left), new-ball bonus for opening bowlers (Tests: first overs and after 80), spinner-by-ball-age and by match day (Tests), fatigue by spell length (Tests). Validate: simulated distribution of overs per bowler and phase vs actual.
- **Batting order:** scenario order; next batter is the next unused player in order (nightwatchman not modeled in v1; record as a deviation if added).
- **Toss decision:** logistic `P(bat first)` by format, competition, venue, dew, season trend. Pre-toss simulations flip a fair coin then draw the decision.
- **Declarations (Tests):** discrete-time hazard at each over end: lead, innings number, estimated overs left in the match, wickets down, current run rate, day. **Follow-on:** `P(enforce | lead >= threshold)` with era trend.
- **Test time:** total available overs `A = days * overs_per_day - L`, with weather loss `L` modeled from precipitation features; fitted with censoring (drawn matches reveal `A`; results only bound it). Innings changeovers cost 2 overs. The engine ends the match as a draw when available overs run out.
- **Limited-overs rain:** interruption probability and overs lost from precipitation features; minimum overs for a result; revised targets from a fitted DLS-style resource table `Z(u, w) = Z0(w) * (1 - exp(-b(w) * u))` estimated from data (not the proprietary DLS Professional Edition; document this). No-result when the minimum is not reached.
- **Ties:** limited-overs ties go to a simulated super over (top three batters by rating, best death bowler); Tests can tie (rare).

## 8. Parameter bundles

`params.py` writes `docs/cricket/data/params-{gender}.json` (and a full-precision `data/processed/cricket/params-*.json` for evaluation). Schema (all arrays as nested lists, numbers rounded to 4 decimals for the page):

```
{
  "version", "fit_cutoff", "gender", "classes": {...},
  "feature_spec_version",
  "dtype":    {"intercept", "groups": {name: {"levels": [...], "B": [[...]]}}, "dense": {...}, "standardize": {...}},
  "outcome":  same + "players": {"bat": {id: [7]}, "bat_fmt": {id: {fmt: [7]}}, "bat_spin": {...}, "bat_death": {...}, "bowl": {...}, "bowl_fmt": {...}, "bowl_death": {...}},
  "wk":       same layout,
  "empirical": {"bye_runs", "wide_runs", "noball_extra", "runout_runs", "runout_nonstriker", "runs5_7"},
  "drs":      {...section 6.4 parameters by fmt/era...},
  "tactics":  {"bowler_choice": {...}, "toss": {...}, "declare": {...}, "follow_on": {...}},
  "time_rain": {"test_overs": {...}, "lo_rain": {...}, "resource_table": {...}},
  "rules":    {...},
  "match_effect": {"sigma_runs", "sigma_wkt", "scoring_direction"}
}
```

Site support files: `players-{gender}.json` (id, name, country, hand, bowl type, recent teams, balls faced/bowled, display ratings), `venues.json`, `umpires.json` (id, name, matches, LBW tendency, wide tendency, accuracy), `teams-{gender}.json` (latest XIs in batting order by team and format), `evaluation.json` (model card numbers and calibration bins).

The page payload stays under 12 MB in total. Players with no delivery since 2019 are dropped from the page bundle (they remain in the evaluation bundle).

## 9. Simulation engine semantics (both engines)

### 9.1 Scenario input

```
{
  "fmt": "T20"|"ODI"|"TEST", "gender": "male"|"female", "competition_id", "date",
  "venue_id", "teams": [{"name", "batting_xi": [ids in order], "bowling_xi": [ids] (defaults to batting_xi)}, {...}],
  "toss": null | {"winner": 0|1, "decision": "bat"|"field"},
  "umpires": [id, id] | null, "drs": {"enabled", "reviews_per_innings", "umpires_call_retains", "accuracy_mult", "ucall_mult"},
  "weather": {"temp_c", "rh", "cloud_oktas", "dew_depression_evening", "precip_risk", "expected_overs_lost"} (null fields -> venue climatology),
  "pitch": {"runs_sd", "wkt_sd", "spin_sd", "pace_sd", "wear_mult"} (defaults 0 / 1),
  "player_form": {id: {"bat_runs", "bat_wkt", "bowl_runs", "bowl_wkt"}} (SD units, optional),
  "state": null | {in-play state: innings so far (runs, wkts, legal balls), current innings detail (striker/non-striker ids, their runs/balls, bowler overs used per bowler, last bowler, reviews left per side, free hit), match_legal_balls, balls bowled so far this match as a list for the pitch update (optional)},
  "n_sims", "seed"
}
```

### 9.2 Output

`p_win` per team, `p_tie`, `p_draw`, `p_no_result`, Monte Carlo standard errors, per-innings score and wicket distributions, mean and 10/50/90% runs by over (worm), margin distribution, per-player distributions (runs, balls, P(50+), P(100+), wickets, P(3+ wkts), economy), dismissal-kind mix, DRS counters (reviews used, overturns, umpire's calls, missed outs standing), and when requested, a sensitivity table that reruns with each factor reset to neutral using common random numbers.

### 9.3 In-play pitch update

Given balls already bowled in the current match, the engine computes the posterior mode of the 2-dimensional match effect `(m_runs, m_wkt)` by a few Newton steps on the outcome-model likelihood of those balls (all other terms fixed) with the fitted prior SDs. The page shows the inferred "pitch reading" in SD units.

### 9.4 Random numbers and parity

Both engines use a documented PRNG (xoshiro128** seeded by splitmix32 from `seed`) so a fixed seed produces reproducible runs inside each engine. Cross-engine parity is checked on (a) exact per-ball probability vectors for exported test states (tolerance 1e-9) and (b) win probability and mean innings totals within Monte Carlo error for fixed scenarios.

## 10. Evaluation protocol (declared before any test-window result is computed)

- **Validation for hyperparameters:** fit cutoff 2023-01-01, validate on matches dated 2023-01-01 to 2023-12-31. Hyperparameters (prior SDs, half-lives) are frozen after this step.
- **Walk-forward tests:** cutoffs 2024-01-01, 2025-01-01, 2026-01-01; each test window runs to the next cutoff (the last ends 2026-10-14). Nothing from a test window informs its own fit.
- **Ball level:** mean log loss of each delivery model versus nested baselines: (B0) context-only (`ctx_main` + `powerplay` + `chase` + `set`), (B1) + players, (B2) + venue and competition season, (Full) + umpire, weather, matchups, match effect. Ablations remove one component at a time from Full.
- **Match level, pre-match at the toss** (XIs and toss known, which is when lineups are announced): win probability from 2,000 simulations per match. Metrics: log loss and Brier (decisive results; ties counted as half), calibration in ten bins, with match-bootstrap 95% intervals. Baselines: coin flip; team Elo fitted walk-forward on the same cutoffs with a toss/home term. Samples: men's internationals and major men's T20 leagues; women's reported separately; Tests use three-way (win/draw/loss) log loss.
- **In-play:** win probability at the start of each innings and every 5 overs (limited overs) or every 30 overs (Tests), from the actual state, versus the outcome; baseline is a logistic model on runs, wickets, balls and target fitted on pre-cutoff data.
- **Distribution calibration:** probability integral transform of first-innings totals (limited overs) and Test match length.
- **Reporting:** every number with its sample size; no component is described as helpful unless its held-out improvement interval excludes zero.

## 11. Web page requirements (`docs/cricket/`)

Static, self-contained (no CDN; hand-written SVG charts), works offline, loads in under 3 s on a laptop, light and dark themes, usable at phone width. Simulations run in a Web Worker with a progress bar and a cancel button.

Inputs: format and gender; team and XI pickers with search (defaulting to the latest XI per team and format), drag or arrow reorder of batting order, bowling options, per-player form sliders; venue picker with its pitch profile (venue effects shown as runs/wicket tendencies vs average) plus pitch sliders (batting ease, wicket-taking, spin help, pace help, wear rate); weather (temperature, humidity, cloud, evening dew, rain risk/overs lost) prefilled from venue climatology for the chosen month; umpire pickers showing LBW and wide tendencies and accuracy; DRS settings; toss (unknown or set); live state entry (innings, score, wickets, overs, batters at the crease, target); number of simulations and seed.

Outputs: headline win probabilities (with tie/draw/no result) and their MC error; innings score histograms; worm chart with bands; margin distribution; player projection table; dismissal-kind and DRS summaries; "what moved the needle" sensitivity bars (pitch, weather, umpires, DRS, toss, each player's form); saved-scenario comparison; a model-card tab with the evaluation numbers, calibration chart and data provenance.

## 12. Compute constraints for this build

4 CPUs, 15 GB RAM, shared by parallel agents. Any job that needs over 1.5 GB of RAM or more than two CPU-minutes runs under `flock /tmp/claude-0/-home-user-BeatingAnything/dca149a3-fa9a-5e66-94bf-d6c38ea6be14/scratchpad/cricket-heavy.lock <command>`. Develop and test on small slices (one season, one competition) first. Use the virtual environment at `/home/user/BeatingAnything/.venv` (Python 3.12, numpy 2.3.5, pandas 2.2.3, scipy 1.17.0, pyarrow 21.0.0, pyreadr).

## Deviations

(Record any departure from this contract here with a one-line reason.)
