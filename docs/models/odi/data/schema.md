# Data files

All under `data/`. Player ids are cricsheet register ids; an id starting `espn:` is a player in an announced XI
that cricsheet has no record of.

## schedule.json
`generated_utc`, `source`, `sims_per_fixture`, `fixtures[]`:

| field | meaning |
|---|---|
| `id`, `url` | ESPN event id and scorecard link |
| `date`, `start_utc`, `end_utc` | first day (local) and the feed's start and end times |
| `series`, `desc`, `status`, `status_text` | series name, "2nd Test", `pre` or `in`, the feed's status line |
| `A`, `B`, `home` | the two sides (home side first when the host is one of them) and which is at home (`A`, `B` or null) |
| `venue_name`, `city`, `country`, `venue`, `env_known` | the ground as the feed names it, its host country, the model's ground id (null if the model has no record of it) and whether the model has an environment for the country |
| `modelled`, `reason` | false with a reason when a side has no data |
| `lineups.A / .B` | `order` (11 ids, batting order), `plan` (bowling plan), `roles` and `names` for unrated players, `source` |
| `toss` | `winner`, `decision`, `bat_first` once known |
| `proj` | pre-match simulation: `p_A`, `p_B`, `p_draw`, `p_tie`, `match_runs`, `match_sixes`, and per side `bat_first_total`, `t1_mean`, `t1_q` (5/25/50/75/95th percentiles), `top_bat[]`, `top_bowl[]` |
| `raw` | the feed fields kept so a later run can retain the fixture if the feed drops out |

## teams.json
`teams[]` in rating order: `name`, `short`, `region`, `matches` (last 30 months), `last_match`, `default` and
`by_region.{asia,sena,other}` lineups (`order`, `plan`, `date`, `country`, `from_match`), `squad[]` (`id`, `name`,
`apps`, `last_app`, `bat_pos`, `usage` = overs per match by phase), and `rating`
(`rank`, `win_pct_fm`, `draw_pct_fm`, `win_pct`, `bat_first_total`, `bowl_first_total`, `net_runs`).
`pairs_neutral[]` holds every pair's neutral-ground probabilities. `region_of` maps a host country to its conditions
group. A bowling plan entry is `{id, pp, mid, death}`: whole overs in the powerplay / middle / death.

## players.json
`players[]`: identity (`id`, `name`, `team`, `bat_hand`, `bowl_type`, `bowl_group`, `bowl_subtype`, `style_inferred`,
`age`, `last_played`, `in_squad`), then `bat` and `bowl` blocks. Each block has splits `all`, `p0`, `p1`, `p2`
(powerplay / middle / death), and `pace` / `spin` / `home` / `away` (batting) or `rhb` / `lhb` / `home` / `away` (bowling). A batting split
holds `avg`, `sr`, `out_pct`, `bnd_pct`, `six_pct`, `dot_pct`, `rv100`; a bowling split `avg`, `econ`, `sr` (balls per
wicket), `wkt_pct`, `dot_pct`, `bnd_pct`, `rv_over`. `vs_avg` is the same metric minus the average player's on the
same deliveries, `sd` the posterior SDs, `by_type` the batter's record against each bowling type, `career` and
`recent` the raw record, `role`, and `inactive_factor`. Top level: `avg_bat`, `avg_bowl` (reference averages),
`phase_labels`, `runs_per_wicket_ref`, `ref_since`, `pool_since`.

## venues.json
`venues[]`: `venue` (id), `name`, `city`, `country`, `matches`, `matches_since_2019`, `last_match`, then for
`all`, `pace`, `spin`, `early`, `late`: `*_rpo` (runs per over), `*_wpo` (wickets per over), `*_rpw` (runs per
wicket), `*_spo` (sixes per over) and each with `_mult` against the average full-member ground. `countries[]` gives
the same for each host country without a ground term; `neutral_reference` the averages.

## sim_params.json
Everything `../cricket/sim.js` needs: situation tables (`base`, `ipw`, `bf`, `chase`), bowling-type
tables, `env` per host country (plus `_default`), `venues`, `ha` (home advantage), `batters`, `bowlers`, role priors
and `team_prior` for unrated players, `extras`, `shock` (axes and Cholesky factors), `conditions` (pitch and dew dials).
Every vector has 11 entries in the order of `classes`.

## diagnostics.json, meta.json, ids.json, method.md
Diagnostics: `holdout`, `tuning[]`, `adopted`, `replay`, `shock`. Meta: build stamp, counts, adopted settings,
file sizes, simulator speed. `ids.json`: `cricinfo` (ESPN / Cricinfo id to cricsheet id) and `names`.
