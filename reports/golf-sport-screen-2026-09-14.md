# Golf sport-side screens — September 14, 2026

Exploration only. No FanDuel discrepancy, confirmation cohort, alert or wager is established.

## Inputs and scope

The public [2024 ESPN season scoreboard](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2024) and [2025 scoreboard](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025) returned HTTP 200 on this machine. They supply stable player IDs, round scores, ordered hole scores and per-round tee-time strings. Public event leaderboard HTML supplies final WD/CUT/DQ labels. This is a bounded 2025 exploration with 2024 warmup, not the proposed full 2015–2025 archive. The separate historical Sunday-variance card has not been run or redefined.

Included 81 events across the two input years (40 in the primary 2025 screen); excluded 19 for multiple courses, team/match play, Stableford, changing starting-stroke formats, qualifying, missing records or incomplete event status. Whole-event exclusions make course identity unambiguous. Detailed event exclusions and row attrition are in the JSON report.

## G3: 3-ball dead-heat correction

Groups are the source's identical event/round/tee-time/start-hole combinations, with exactly three players and three complete 18-hole scores. These are observed tee-group proxies: ESPN does not supply an explicit group ID in this response. Starting hole is the first hole in the source's ordered score list. Groups were never fabricated by shuffling players. Time-zone labels in the tee strings are not trusted as absolute timestamps; only equality within an event-round is used. Multi-course exclusions prevent simultaneous groups at different courses being merged. Non-three-player, partial and missing-key groups are dropped.

Official PGA TOUR Sony Open spot-check: 146/148 source groups and 138/140 complete triples matched by normalized player names, round and starting tee. The two unmatched groups contain ESPN's Kristoffer Ventura versus PGA TOUR's Kris Ventura; that name was not rewritten. This supports the reconstruction at one event and does not certify all events' group IDs.

Ability rank uses each player's mean field-round-centered score from their previous 20 rounds in completed earlier events, requiring at least ten earlier rounds. Current-event rounds never enter that event's rank. This is an exploratory ordering proxy; field strength and course fit remain confounded. Strict-win probabilities are normalized by the number of unique-winner groups before comparison with dead-heat shares. Raw strict-win probabilities would exaggerate the correction.

Recovered 3,659 complete tee-group triples; 2,651 triples across 35 events have eligible prior-ability ranks. Tie for low: **15.84%** (381 two-way; 39 three-way).

2025 attrition: 15,394 player-round records, 275 missing usable time/start-hole keys; 3,681 three-player source groups, of which 22 have incomplete scores. The ability filter then removes 1,004 groups with insufficient earlier rounds and 4 with tied prior-ability ranks. Two-player and singleton groups are outside G3; their counts are retained in JSON.

| Prior ability rank | Normalized strict win | Dead-heat effective probability | Correction (percentage points) | Event bootstrap 95% interval |
| --- | ---: | ---: | ---: | --- |
| Best | 37.606% | 37.137% | -0.470 | [-0.883, -0.059] |
| Middle | 32.497% | 32.893% | +0.397 | [-0.019, +0.815] |
| Worst | 29.897% | 29.970% | +0.073 | [-0.386, +0.508] |

Pooled >1-point correction gate: **does not pass**. Sample gate (300 triples / 5 events): passes. Year, round and pre-event skill-gap splits are exploratory diagnostics in JSON; a sparse subgroup maximum is not a surviving mechanism by itself.

## Observed round-score spread

15,088 complete player-rounds in 160 course-round cells: pooled within-course-round SD **2.899 strokes**; median cell SD 2.837. After subtracting the prior-ability proxy, residual SD is 2.810 over 13,477 rounds. These describe observed dispersion. They do not isolate intrinsic player spread: noisy ability, weather/waves, course fit and weekend survival remain. The baseline three-stroke scale is plausible; fitting a distribution kernel cannot itself establish a book error.

## G2: recent withdrawal and after-start withdrawal incidence

An observed completed hole proves a player started. A WD with zero recorded holes has unknown timing, since a withdrawal can occur after one stroke before finishing a hole. Those WDs are never labeled pre-start. Their subsequent 90-day starts are censored in the primary comparison. First 90 calendar days of archive starts are also censored. Prior exposure uses only an earlier event's completed date and an observed after-start WD.

| Prior 90-day history | Observed starts | After-start WDs | Rate | Wilson 95% interval |
| --- | ---: | ---: | ---: | --- |
| Observed after-start WD | 199 | 4 | 2.01% | [0.78%, 5.05%] |
| No observed after-start WD | 4,641 | 48 | 1.03% | [0.78%, 1.37%] |

Difference: **+0.98 percentage points**; relative risk 1.94×. Conditional-rate gate (≥3% and above baseline): **does not pass**. Sample gate (100 exposed starts, 10 exposed WDs, 5 events): **does not pass**.

**G2 decision: unresolved inadequate sample or status coverage.** There are 4 exposed withdrawals against the declared minimum of ten.

WD timing across included 2024–2025 events: {"after_start_proven": 122, "unknown_zero_recorded_holes": 2}. 2 started player-events were censored because of a prior WD of unknown timing.

- Prior withdrawal means observed in retained single-course PGA events; excluded formats, other tours and unlisted pre-start entrants are not covered.
- Zero-hole withdrawals have unknown timing; they are not asserted pre-start and their next-90-day starts are censored.
- At least one completed hole proves a start, but first-hole withdrawals after a stroke are missing from this lower-bound after-start sample.
- Final historical WD labels are used retrospectively with event-end dates; no as-published injury news or pre-round snapshot was recovered.
- Age and true FedExCup status-position effects untested; calendar fall is a descriptive proxy only.
- This is withdrawal incidence, not matchup settlement or an executable book-side discrepancy.

Rate-difference 95% bootstrap intervals (percentage points): event-cluster [-0.598, +2.947]; player-cluster [-0.970, +3.390]. These are separate one-way clustering checks, not a two-way cluster confidence interval. Binomial Wilson intervals in the table are descriptive and do not account for repeat players. The fall split is calendar-only; age, injury-news and actual status-point effects remain untested. Current Ontario house rules must govern settlement: the old plan's three-hole/generic more-holes shortcut is not used here.

## Reproduce and next step

`python3 tools/explore_golf_sport.py` replays cached inputs. `python3 tools/explore_golf_sport.py --fetch --acquire-only` acquires only missing public inputs at one request per second, stopping on denial. Raw inputs and intermediate groups/rounds/withdrawals remain under ignored `data/raw/golf-sport/`. The [JSON report](golf-sport-screen-2026-09-14.json) records inputs, hashes, exclusions, dispersion and diagnostic splits. The declared pooled G3 mechanism fails its effect gate and is parked; exploratory subgroup maxima do not revive it. G2 needs adequate withdrawal counts and timestamped matchup availability before any book-side conclusion.
