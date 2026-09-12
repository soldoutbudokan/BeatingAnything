# Tennis state exploration

Exploratory sport-side evidence only. No FanDuel prices, returns, model fit, alert or wager.

Source: [Tennis Abstract Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject/tree/2c59eef194967e688b69e73df344184a06322cd8), pinned `2c59eef194967e688b69e73df344184a06322cd8`. Jeff Sackmann and volunteer contributors; source data and derived data reports are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). This is noncommercial research; this source is not a licensed commercial betting feed.

## Sample

Men's 2020s file: 3,250 accepted complete matches, 84,108 regular service games, 20200103–20260521. Excluded 87 of 3,337 matches and 12,438 of 547,478 points. This is a curated, nonrandom charting sample, dominated by top-level men's matches. It is not an ATP census or Challenger sample. Tournament names are not a verified tour-level field. Only 198 accepted match IDs/tournament names contain an explicit Challenger marker.

Incomplete, noncontiguous and inconsistent matches are excluded as whole matches. This can omit retirement and fatigue tails. Pre-point score reconstruction checks game boundaries and winners; it does not independently verify volunteer charting.

Exclusions: `{"incomplete_final_game": 32, "incomplete_match": 29, "invalid literal for int() with base 10: ''": 2, "partial_or_noncontiguous_points": 2, "points_after_match_end": 17, "unsupported_best_of": 1, "unsupported_match_tiebreak_or_scoring": 4}`.

## Results

| Screen | Exposed breaks / games | Control breaks / games | Raw difference | Within-match residual difference |
| --- | ---: | ---: | ---: | ---: |
| double break concession | 181/600 (30.17%) | 955/3738 (25.55%) | +4.62 pp | -3.79 pp |
| long service game carryover | 102/417 (24.46%) | 3207/16478 (19.46%) | +5.00 pp | +2.39 pp |
| post tiebreak loser | 29/162 (17.90%) | 180/817 (22.03%) | -4.13 pp | -4.30 pp |
| post tiebreak winner | 38/162 (23.46%) | 147/817 (17.99%) | +5.46 pp | +4.84 pp |
| fourth set concession | 9/29 (31.03%) | 9/39 (23.08%) | +7.96 pp | +20.54 pp |
| double break prior high hold proxy | 11/60 (18.33%) | 86/501 (17.17%) | +1.17 pp | -7.61 pp |

Definitions:

- Double break: first completed service game per player-set beginning at least two net breaks down, versus first beginning one net break down. Opponent must not already be one set from winning the match.
- Long service game: next same-set service game following a held game of at least 16 points, versus a held game of 4–8 points; the intervening return game has at most eight points. Use the first opportunity per player-set in each exposure/control group.
- Tiebreak: loser's first regular service game in the next set after a tiebreak of at least 16 points, versus tiebreaks of 7–12 points. The winner comparison is a diagnostic.
- Fourth set: first service game at least two net breaks down in set four of a best-of-five match while leading 2–1 in sets, versus the same state while trailing 1–2. The prewritten card requires 50 exposed cases and +5 pp before keeping the hypothesis on raw effect size.
- Prior high hold proxy: at least 100 completed charted service games on earlier dates and at least 85% holds, across surfaces. Same-day observations are withheld. This is a sparse prior hold-rate proxy, not a direct big-server classification.

Within-match residual difference compares each outcome with that player's other completed service games against the same opponent in that match; all selected exposure/control outcomes are removed from the baseline, and at least three other games are required. It then contrasts exposed and control residuals. A further diagnostic retained in JSON restricts comparison to players with both types of opportunity in the same match, averages each type within player-match, and weights those pairs equally. These retrospective baselines partly address player/opponent strength; they are not deployable forecasts and do not isolate concession or fatigue from within-match form, selection or score-state effects. In particular, selecting two breaks down conditions on earlier poor serving.

The JSON also compares each group's outcome rate with the same player's service games in other sets of that match, requiring at least three such games. This is an additional descriptive strength check. The paired one-break comparison is especially selection-sensitive: reaching two breaks down often requires losing the earlier one-break-down control game. It must not be read causally.

The JSON includes sample splits and descriptive 95% normal intervals with match-clustered standard errors. These are exploratory intervals without multiplicity correction; no untouched holdout or confirmatory inference is claimed. The 2020s file was the single initial screen sample, with no post-result threshold tuning or model fitting.

## Decision

Deprioritize the broad double-break screen: its +4.62 pp raw difference misses the card's prewritten +5 pp / 100-exposure screen. The exposed break rate is 30.17%, versus 31.76% for those same players in other sets of the same matches. This does not show extra concession beyond the selected players' poor serving in these matches. The specific big-server claim remains unresolved: the prior high-hold proxy supplies only 60 exposures.

Keep long-service-game carryover as an unconfirmed lead, not a sport-side confirmation. The raw difference is +5.00 pp across 417 exposures, exceeding the prewritten +3 pp / 100-exposure screen. But the within-match residual contrast falls to +2.39 pp (descriptive 95% interval -1.83 to +6.61 pp), and exposed players' other-set break rate is 23.89%, close to the observed 24.46%. Player/opponent and match-form selection explain much of the raw association. It may justify a cheap independently licensed replication and collecting the matching live next-service-game prices; it does not justify a model fit or promotion.

Kill the specified extended-tiebreak-loser direction in this exploratory sample: -4.13 pp across 162 exposures is opposite to the card's prewritten +3 pp prediction. The winner diagnostic points the other way but is uncertain and was not the target hypothesis; do not turn it into a confirmed reversed strategy.

Fourth-set concession remains unresolved: 9/29 exposed games versus 9/39 controls (+7.96 pp). The sample is below the card's 50-exposure minimum. This does not confirm or kill the incentive mechanism.

None of these cards is sport-side confirmed, no FanDuel pricing mismatch has been measured, and no betting edge has been demonstrated.

## Book-side data needed

A retained FanDuel two-sided next-game hold/break quote at the trigger, both quote and receipt timestamps, event/player identity, exact pre-game score and server, plus an independent timestamped game-state stream. Also collect the paired reference quote and settlement rules. Set correct-score and totals markets need their own quotes and outcomes; this screen does not verify those markets. No actual FanDuel stale-price claim follows from these sport-side results.

## Reproduce

```bash
python tools/explore_tennis_states.py --download
```

Raw CSVs remain ignored; pinned URLs, sizes and SHA-256 hashes are in the adjacent JSON. The original `tennis_pointbypoint` repository returned GitHub 404 during source discovery; this screen uses the available Match Charting Project instead.
