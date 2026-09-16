# Sunday chasing variance screen — September 14, 2026

**The fixed sport-side screen fails.** The variance ratio is **1.0327**, below the prewritten **1.15** threshold, with **421 exposed final rounds across 43 events**, exceeding the minimum 200 rounds and 15 events. No FanDuel prices were tested and no edge was established.

The September 13 [card](../docs/hypotheses/golf-sunday-chasing-variance.md) fixed the season, leaderboard gaps, prior-ability construction, bins, weighting and decision thresholds. The [execution declaration](golf-sunday-declaration-2026-09-14.md) fixed the remaining estimator choices before this comparison. This is an exploratory screen, and the inspected 2025 outcomes are not untouched confirmation data.

## Result

| Measure | 4–6 behind | 8–10 behind |
| --- | ---: | ---: |
| Round-three eligible positions, before prior-ability requirement | 431 | 837 |
| Insufficient prior rounds | 10 | 28 |
| Eligible after prior-ability requirement | 421 | 809 |
| Complete final-round outcomes | 421 | 807 |
| Missing final-round outcome | 0 | 2 |
| Exposure-weighted within-bin variance, strokes² | 6.623810 | 6.414124 |
| Exposure-weighted field-centered final-round mean, strokes | −0.143795 | −0.233952 |

The exposed/control variance ratio is **1.032691**; its 2,000-replicate tournament-cluster percentile 95% interval is **[0.867256, 1.194127]**. The weighted mean difference is **+0.090157 strokes**, interval **[−0.212585, +0.401611]**. All 2,000 bootstrap replicates were valid. Seven one-stroke ability bins contribute, with no target-group observations lost for lack of a matching bin. The comparison covers 44 events overall; 43 contain exposed observations.

The uncertainty interval includes effects larger than the gate. Failure of the declared point-estimate screen does not prove a conditional variance effect is absent. It closes this specified cheap screen without a price-test advance, new bins, reversed direction or replacement years.

## Cohort and method

All **44 eligible official 2025 PGA TOUR four-round individual stroke-play tournaments** matched the [official schedule](https://www.pgatour.com/schedule/2025) by normalized event name and scheduled start date. The American Express, Farmers Insurance Open, AT&T Pebble Beach Pro-Am and RSM Classic remain included. Their course rotations finish by round three. The 2025 TOUR Championship also remains included because [starting strokes were removed for that edition](https://www.pgatour.com/article/news/latest/2025/05/28/what-do-top-players-think-of-tour-championship-changes-scottie-scheffler). “Sunday” denotes the final round in this card, including a Saturday finish.

Excluded under the declared scope: Zurich Classic and Ryder Cup team formats, Barracuda Stableford, [unofficial Hero World Challenge](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/heroworldchallenge/roundInfo/R2_Notes.pdf), and [Q-School qualifying](https://www.pgatour.com/article/news/how-it-works/pga-tour-q-school-presented-by-korn-ferry-schedule-registration-dates-sites-locations-benefits-status-eligibility). The schedule's Grant Thornton team event is absent from ESPN and outside the eligible cohort. No eligible 2025 event is missing, and no event is excluded for its observed scoring pattern.

The cached [ESPN PGA scoreboards](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025) supply stable player IDs and hole-validated complete rounds. Calendar years 2015–2024 and strictly earlier 2025 events supply prior history. A player's baseline is the latest 20 eligible complete rounds, minimum 10, after subtracting each historical event-round's completed-score field mean. Complete rounds in shortened events can supply history. Nonindividual/nonstroke formats, unofficial/qualifying events and 2019–2024 starting-stroke TOUR Championships do not. Every baseline event ends before the current event starts.

Round-three cumulative gross scores reconstruct strokes behind the leader. The outcome is final-round gross score minus its event's completed-score final-round field mean. Ability bin is `floor(prior_ability)`, giving `[k,k+1)` intervals. Each bin's unbiased sample variances are weighted by its observed exposed count; the primary statistic divides the two weighted variances. Means use those same weights. The bootstrap samples eligible tournaments with replacement, retaining each tournament's players together and recomputing the full statistic; seed 20260915.

## Validation and limits

An independent pandas aggregation reproduced the variance ratio and mean difference to below 1e-12. Prior-round counts, strictly earlier event dates, and unique event/player rows passed checks. The [official Sony leaderboard](https://www.pgatour.com/tournaments/2025/sony-open-in-hawaii/R2025006/leaderboard) corroborates J.J. Spaun's 66–66–65 = 197 round-three total. The [Travelers final-round tee sheet](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/travelerschampionship/roundInfo/R4%20Tee%20Times.pdf) corroborates the 194 leader total and both missing controls at 204. [Official final-round notes](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/travelerschampionship/roundInfo/R4_Notes.pdf) identify those absences as Eric Cole withdrawing before the round and Viktor Hovland during it. These are bounded source spot-checks, not certification of every score.

Field-centered gross scores do not adjust for changing field strength, weather, tee time, or course difficulty/par in earlier multi-course rounds. Binning a noisy, sometimes old prior average does not eliminate remaining player differences. The oldest contributing baseline date among all prepared players is June 21, 2015; no unplanned age limit was added. Leaderboard-position selection and cut/withdrawal attrition can also affect dispersion. The outcome comparison therefore does not identify risk-taking causally.

The broader source inventory contains six empty/undated entries and 80 unscored 2015 Barbasol player entries without stable IDs; those supply no history and remain inventoried. Uniform complete-round validation rejects absent, partial or inconsistent scores. The retained 2025 events contain 332 such round records across periods 1–4; an absent round is not imputed as zero. The source is retrospective: event dates and reconstructed positions do not establish when a live trigger or FanDuel quote was available.

Full per-event counts, source hashes, bins and attrition are in the [JSON report](golf-sunday-screen-2026-09-14.json). Raw publisher scores and derived player rows stay local and ignored. Reproduce with `state/runtime/research-venv/bin/python tools/explore_golf_sunday.py`.
