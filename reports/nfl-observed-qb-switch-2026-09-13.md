# NFL observed QB switch: short-target usage

**The fixed screen failed.** Across 124 matched quarterback-change team-games, the adjusted short-pool target rate rose **10.12%**, below the prewritten **20%** gate. The sample clears the 100-window minimum. This exploratory sporting association does not establish a FanDuel edge. Do not select a favorable year, require the new QB to stay, relax roles or enlarge this same comparison after its result.

This is new [card 36](../docs/hypotheses/football-observed-qb-switch-short-targets.md), distinct from the untested pregame-announced backup-QB card. A QB change is observed through a valid lineup containing exactly one QB after ten consecutive snaps with the same different QB. No injury or depth-chart reason is inferred. Prior-role short-target WR/TE/RB/FB players on field at that snap form a frozen pool. Targets strictly after the trigger are compared with the preceding ten offensive snaps; the trigger's outcome enters neither period. All later QB returns and receiver substitutions remain.

| Fixed comparison | Before trigger | After trigger |
| --- | ---: | ---: |
| Exposed short-pool targets | 145 | 147 |
| Exposed team snaps | 1,240 | 1,185 |
| Exposed targets per 100 team snaps | 11.694 | 12.405 |
| Standardized control targets per 100 team snaps | 14.493 | 13.961 |
| Exposed pool receptions, secondary description | 98 | 106 |

The raw target-rate change is +6.08%; matched unchanged-QB controls change −3.67%. Their ratio gives **+10.12% adjusted change**. A 2,000-resample exposed-game bootstrap, keeping control rates fixed, gives a descriptive 95% interval of **−12.54% to +39.35%**. It omits uncertainty in controls and repeated-team dependence; it is not independent validation. The secondary reception counts do not determine this card's gate.

Controls come from other games with the same team, season, quarter and broad signed-score band. The first eligible unchanged-QB snap in each team-game/quarter/score band is retained. Matching uses 613 unique control windows from 381 games. Exposures cover 118 distinct games; six games contribute both teams. By year, matched exposures are 50/41/33 for 2023/2024/2025; adjusted changes are +9.92%, +29.81% and −14.64%. These inspected year splits are descriptions, not independent retests.

**Coverage and attrition.** The six pinned publisher files cover all 816 regular-season games and 100,943 regulation offensive snaps. There are 100,348 valid sole-QB lineups, 502 dual-QB lineups, 76 with no QB and 17 invalid eleven-player lists. Unverified snapshots cannot establish QB continuity. There are 257 first qualifying QB changes before receiver eligibility: 32 lack three prior team games, and 93 have no eligible short-target receiver on field, leaving 132 frozen exposures. There are 5,500 frozen control windows. Eight exposures lack other-game matching controls, leaving 124.

Forty-six matched post windows have zero targets to the frozen pool; all remain. Sixteen have fewer than ten remaining regulation team snaps. Of 1,185 post-window snaps, the newly observed QB is the sole QB on 772, the previous QB on 411, and another/unknown QB on two. A future-persistence requirement would change the question using information unavailable at the trigger, so none was imposed. Package changes and brief relief appearances therefore remain in this observed-change screen.

**Known source disagreement is retained.** The earlier [source diagnostic](nfl-garbage-receptions-source-check-2026-09-13.json) found fourteen completed passes in two 2025 games whose receiver is missing from participation. Those games contribute twelve frozen control windows here and no exposed windows. No discordant play is a trigger. Two discordant-play occurrences fall in pre windows and three in post windows; none is a directly counted catch by a selected pool member. This does not rule out omitted eligible receivers or other identity errors. No IDs or games were repaired or selectively removed.

Quarter/score matching leaves field position, opponent, the reason for substitution, receiver mix and pre-trigger trends uncontrolled. Prior roles and observed lineups are retrospective source records, without live receipt timestamps. A ten-team-snap horizon has an unknown real-time duration. Targets are not receptions, and this study contains no offered FanDuel line, executable price, market suspension, settlement comparison, return or expected-value estimate.

The [declaration](../docs/nfl-observed-qb-switch-declaration-2026-09-13.md) was written at 18:14:52 UTC on September 13, 2026; the cohort was frozen at 18:19:12 UTC and evaluated at 18:20:05 UTC. No definition changed after comparison. Source URLs, exact hashes and byte counts, exposure rows, matched-control identities/rates and limitations are in the [JSON result](nfl-observed-qb-switch-2026-09-13.json). Full control-window outcomes remain reproducible from the pinned inputs and are retained in the ignored local cache.

A separate source-row calculation checked all 5,632 windows' QB triggers, prior-role totals, strict trigger exclusion and target/reception counts, and reproduced all 124 matched-control rates. The script compiles and the diff has no whitespace errors.

| Checkpoint | SHA-256 |
| --- | --- |
| Declaration | `06c7d97d3691bc70e2d96b30da2bb58717440e61773840ddb86c4baa567753e3` |
| Frozen cohort | `b173d4ed9a39c2f556c2789eb8ffae61e87da98331cd571b99880688638db052` |
| Complete window outcomes | `df0d9ae5a2e5fc3050ef450495cad8ecc63861f0dc10f69f841dc6921788c260` |

Reproduce in a clean checkout with the pinned source files present, or add `--download` to fetch each absent public file once; changed bytes are rejected:

```bash
python tools/explore_nfl_observed_qb_switch.py --prepare
python tools/explore_nfl_observed_qb_switch.py --evaluate
```

Preparation refuses to overwrite a frozen cohort. In an existing prepared checkout, run only `--evaluate`. The declaration hash stays fixed; a newly reproduced cohort has a new preparation clock and therefore a different cohort hash, while its selected windows and outcomes should agree.

Attribution: **FTN Data via nflverse, CC BY-SA 4.0**, including published derived participation rows; **nflverse/nflfastR PBP, CC BY 4.0**. Raw publisher data is excluded from the public repository. Continue with a different mechanism or actual eligible FanDuel pricing evidence; this card is closed under its declared screen.
