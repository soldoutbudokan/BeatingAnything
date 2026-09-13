# Tennis fixed follow-up — September 13, 2026

Exploratory sport-side evidence only. No model fit, bookmaker prices, returns or betting edge.

Source: [Tennis Abstract Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject/tree/2c59eef194967e688b69e73df344184a06322cd8), pinned `2c59eef194967e688b69e73df344184a06322cd8`. Jeff Sackmann and volunteer contributors; source and derived data reports are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). This is noncommercial research, not a licensed commercial betting feed.

## Fixed scope and coverage

The men's 2010s file repeats only the unresolved long-service-game and fourth-set definitions from September 12, with the same parser, thresholds and summaries. The men's 2020s file screens the already written rank-5 failed-serve-for-set card. No thresholds, directions or subgroup filters were tuned after results. The 2010s and 2020s accepted match IDs do not overlap. This earlier-period follow-up was chosen after the first screen; it is not an untouched holdout, independent source, independent license or confirmation.

| File | Accepted / input matches | Regular service games | Accepted date range |
| --- | ---: | ---: | --- |
| Men's 2010s | 2,164/2,232 | 54,852 | 20100108–20191124 |
| Men's 2020s | 3,250/3,337 | 84,108 | 20200103–20260521 |

Incomplete, noncontiguous or score-inconsistent matches are excluded as whole matches. That can omit fatigue and retirement tails. This curated, nonrandom sample favors top-level men's matches; it is not a tour census. Tour level is not a verified source field. Exact exclusions, surface/best-of splits and all returner strata for rank 5 are retained in JSON.

## Results

| Fixed screen | Exposed breaks / games | Control breaks / games | Raw difference | Within-match residual difference |
| --- | ---: | ---: | ---: | ---: |
| long service game carryover 2010s | 79/291 (27.15%) | 2155/10704 (20.13%) | +7.02 pp | +4.83 pp |
| fourth set concession 2010s | 4/13 (30.77%) | 7/18 (38.89%) | -8.12 pp | -4.50 pp |
| failed serve for set 2020s | 78/294 (26.53%) | 389/2087 (18.64%) | +7.89 pp | -2.04 pp |

Definitions:

- Long service game: first next same-set service game per player-set/group after a held game of at least 16 points versus 4–8 points, with the intervening return game at most eight points. Prewritten screen: at least 100 exposures and at least +3 percentage points.
- Fourth set: first service game at least two net breaks down in set four of best-of-five, leading 2–1 versus trailing 1–2 in sets. Prewritten screen: at least 50 exposures and at least +5 points.
- Failed serve for set: opponent's service game at 5–5 immediately after the returner was broken serving at 5–4, versus after the returner held serving at 4–5. All outcomes are the target server being broken. Prewritten screen: at least 100 exposures and at least 3 points lower break probability after the failed close.

The within-match residual contrasts subtract the same server's break rate in other regular games against the same opponent, excluding all selected target games and requiring at least three baseline games. The same player-match comparison also fixes the returner. These retrospective baselines use outcomes that can occur later; they are descriptive strength checks, not real-time predictors or causal adjustments. Other-set baselines and paired same-player/match contrasts are retained in JSON. The reported intervals use the unchanged match-clustered normal approximation; they have no multiplicity correction.

## Decisions and limitations

- **long service game carryover 2010s:** raw screen passes; mechanism and pricing remain unconfirmed. Raw descriptive 95% interval: +1.79 to +12.24 pp.
- **fourth set concession 2010s:** unresolved: below prewritten exposure minimum. Raw descriptive 95% interval: -42.39 to +26.15 pp.
- **failed serve for set 2020s:** specified direction fails the prewritten raw screen. Raw descriptive 95% interval: +2.50 to +13.28 pp.

Long-service carryover remains the surviving unresolved lead. Its earlier-period raw difference is +7.02 pp, following +5.00 pp in the September 12 sample. The unchanged within-match residual contrast is +4.83 pp (descriptive 95% interval -0.29 to +9.94 pp). The exposed players' other-set break rate is 24.48%, versus 27.15% in target games. Replication of the raw association warrants seeking matched game prices and a prospective strength-aware comparison; it does not establish fatigue or mispricing.

Fourth-set concession supplies only 13 additional exposures (42 across both screened files), still below the original 50-case minimum even if counted together. The earlier-period direction is opposite, with wide uncertainty. Leave unresolved and stop source expansion for this batch.

Kill the prewritten failed-close direction in this exploratory sample: the raw break-rate difference is +7.89 pp across 294 exposures, opposite to the predicted reduction. The within-match residual contrast is -2.04 pp; the sign change highlights strength and score-path selection, not a confirmed psychological effect. Do not promote the reverse direction.

No card is sport-side confirmed. Read each period separately; no pooled effect threshold or subgroup rescue is used. Mechanism replication and market mispricing remain separate requirements.

Long games select players/opponents having difficult service games; fourth-set deficits select earlier poor serving and may reflect injury, form and match dynamics. The failed-close groups condition on different score paths and opposite preceding outcomes (break versus hold). Differences in strength, serving order and mean reversion can mimic or hide the proposed psychological effect. None of these comparisons isolates intent or fatigue.

No FanDuel hold/break prices or quote/state timestamps are present. Passing a sport-side threshold cannot establish mispricing after vig. Any retained mechanism needs separately timestamped quotes, state, event identity and settlement rules before a betting claim.

## Reproduce

```bash
python tools/explore_tennis_followup.py --download
```

The September 12 script and reports remain unchanged. Raw files stay ignored; pinned URLs, sizes and SHA-256 hashes are in the adjacent JSON.
