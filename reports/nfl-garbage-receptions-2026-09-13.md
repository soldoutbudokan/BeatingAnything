# NFL garbage-time receptions — September 13, 2026

**Unresolved: 72 matched exposures, below the fixed minimum of 200.** The observed reception rate was 9.044 per 100 remaining offensive team snaps versus a standardized control rate of 6.395, a **41.4% relative increase**. This does not pass the card's sample gate and does not demonstrate FanDuel mispricing. Do not loosen matching or add seasons to promote this inspected result.

## Executed sample and comparison

The [declaration](../docs/nfl-garbage-receptions-declaration-2026-09-13.md) was written before outcome comparison and hashed `46fa89e3dbd4b38a8e23e02f608c438b743571a1d491b188b0d0aca547ab72f4`. The fixed sample is all **816 regular-season games in 2023–2025**. The prior-role and trigger cohort was frozen separately before evaluation; its hash and preparation/evaluation times are retained in the [JSON report](nfl-garbage-receptions-2026-09-13.json).

Historical participation is now accessible. [FTN Data via nflverse](https://github.com/nflverse/nflverse-data/releases/tag/pbp_participation) supplies an offensive player-ID list and corresponding positions for each snap. All 1,445 candidate possession-start snaps joined without missing participation, duplicate player IDs or mismatched possession teams. The [publisher's dictionary](https://github.com/nflverse/nflreadr/blob/main/data-raw/dictionary_participation.csv) defines these as on-field participants; it does not provide live receipt timestamps. This is retrospective lineup evidence, not a live feed or a guarantee of correct player identities.

A trigger is the first scrimmage snap of a Q4 possession with at least six minutes remaining. The exposed offense trails by at least 17; close controls have an absolute margin at most eight. Players must be on field at that snap and have a short-target role from the team's preceding three regular-season games: at least ten observed target depths, at least 90% depth coverage, mean depth at most eight yards and targets in at least two games. Current-game outcomes never select the receiver. The first qualifying trigger per player-game is retained across either category.

Outcomes start **after** the trigger snap and end at regulation. The denominator includes every subsequent offensive team snap, even when the selected receiver sits. Nullified plays, special teams, two-point tries and overtime do not count. Later substitutions, quarterback changes, score changes and zero-catch windows remain. This estimates remaining catches per team opportunity, not catches per personal route or on-field snap.

| Season | Matched receiver-game exposures | Distinct exposed games | Receptions | Remaining team snaps | Relative rate increase |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023 | 19 | 17 | 25 | 294 | +49.6% |
| 2024 | 25 | 18 | 43 | 416 | +35.7% |
| 2025 | 28 | 19 | 38 | 462 | +43.1% |
| Total | 72 | 54 | 106 | 1,172 | +41.4% |

The frozen cohort contains 990 receiver-games: 265 exposed and 725 close controls. Exact same-receiver/season, three-minute clock-bin and 20-yard field-bin matching leaves **193 exposed cases unmatched**. Matched cases involve 45 receivers and 72 distinct control windows from 61 games; some controls are reused across exposures. The largest receiver contributes five exposures. This is a selected subset, not representative evidence for every receiver or blowout.

The exposed mean is **1.472 remaining catches in 16.278 team snaps**, versus standardized control means of **0.968 catches in 15.160 snaps**. Control rates are weighted by exposed remaining team snaps; those mean counts are separately weighted by exposure windows. Twenty-six matched exposures finish with zero additional catches and remain in the result. No matched exposure has zero remaining team snaps. The snap denominator counts team opportunities per receiver-window, so shared team snaps across different receivers are deliberately repeated, not 1,172 unique NFL plays.

## Limits and decision

A separate calculation reproduced prior-date cutoffs, prior target-depth totals and remaining outcomes for all 990 frozen rows, and all 72 matched control rates. Four small state/lineup tests passed. A wider [source consistency check](nfl-garbage-receptions-source-check-2026-09-13.json) found **14 completed receptions whose receiver is absent from the participation list**, out of 34,654 completions. These involve Josh Downs in 2025 Week 9 and Khalil Shakir in Week 12. None is the frozen trigger snap or a counted catch by a selected receiver in a remaining window. However, incorrect identities elsewhere in these two games could omit an otherwise eligible receiver. This unresolved source discrepancy is recorded without repairing IDs, deleting games or recomputing a more favorable cohort. Treat the measured association as provisional as well as underpowered.

The 2,000-resample exposed-game bootstrap gives a descriptive relative-rate interval of **+1.6% to +95.5%**. It holds control rates fixed, omits uncertainty in those estimated rates and does not capture repeated-player dependence across games. It must not be presented as full inferential uncertainty, much less an independent validation. Coarse matching leaves differences in opponents, personnel and game state; using actual remaining snaps as weights is retrospective standardization, not a price available at the trigger.

The effect clears the card's +20% magnitude requirement, but **72 is below 200**. The result remains unresolved. No FanDuel live reception line, accrued-catch quote pair, executable price, suspension state or source latency was acquired. A positive conditional association cannot establish book-model error.

The fixed batch is complete. Do not repeat the participation search, widen bins, relax the prior-role definition or append seasons after seeing the result. Use this newly accessible participation source for a genuinely different prewritten question when useful. Move to another untested mechanism while exact price access remains unavailable.

## Reproduce and attribution

From the repository root, run:

```sh
python tools/explore_nfl_garbage_receptions.py --self-test
python tools/explore_nfl_garbage_receptions.py --download --prepare
python tools/explore_nfl_garbage_receptions.py --evaluate
python tools/explore_nfl_garbage_receptions.py --source-check
```

Preparation refuses to overwrite an existing frozen cohort. With a retained cohort, run only evaluation. All six downloaded/reused assets are SHA-256 pinned and their byte counts and URLs are in the JSON. The three newly acquired participation CSVs total 148,751,207 bytes and match the GitHub release digests. A fresh cohort's preparation timestamp/hash can differ, but declared definitions and source pins may not.

Participation and published derived receiver-window rows: **FTN Data via nflverse, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)**, per the [publisher's attribution instructions](https://github.com/nflverse/nflreadr/blob/main/R/load_participation.R). PBP: **nflverse/nflfastR, [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md)**. Raw inputs and the working cohort stay in ignored `data/raw/`; the public report contains derived research rows, not raw play-by-play or full player lists.
