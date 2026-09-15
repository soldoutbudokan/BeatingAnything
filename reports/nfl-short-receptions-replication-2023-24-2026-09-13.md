# Card 38 — Separate 2023–24 price replication

**The replication lost 33.87% and did not reproduce the positive 2025 estimate.** It selected 26 games, below the unchanged minimum of 50. The formal status remains unresolved because of sample size, but these new results weaken the strategy rather than support an edge.

| Fixed period | Games | Wins / losses | Profit | ROI after haircut |
| --- | ---: | ---: | ---: | ---: |
| 2023 regular season | 14 | 4 / 10 | −6.5210 units | −46.58% |
| 2024 regular season | 12 | 5 / 7 | −2.2862 units | −19.05% |
| Predeclared combined 2023–24 | 26 | 9 / 17 | −8.8072 units | −33.87% |

The combined 95% game-bootstrap ROI interval is **−67.28% to +2.58%**, using 10,000 resamples and seed 1738. Each game risks one unit; winners earn 98% of quoted decimal net winnings. All 26 participants have evidence of playing; zero unknown settlements were excluded, so the unknown-as-loss and unknown-as-void sensitivity results coincide.

The original [2025 test](nfl-short-receptions-backtest-2026-09-13.md) remains separate: 34 games and +15.46% ROI with a wide interval. No 2025 results were pooled into the replication gate, and no source, year or cutoff was added after grading.

## Fixed rule and source adaptation

The [replication declaration](../docs/nfl-short-receptions-replication-declaration-2026-09-13.md) froze combined 2023–24 as the evaluation period before preparing its selections. Roles still require exactly the three previous regular-season games within the player's season, ten observed target depths, 90% coverage, mean depth at most eight yards and at least two target games. Full names in prior participation records establish a unique player ID/team; current-game catches or participation cannot select the bet.

The listed FanDuel reception Over still requires paired half-point prices with the original clock and vig gates. The latest earlier FanDuel spread must make the same team an underdog of at least +6.5 and occur within six hours. A new [pinned raw-board source](../docs/nfl-receptions-replication-source-2026-09-13.md) supplies original American spread prices and archive, bookmaker and market clocks. Both quote updates must be nonfuture and at most 300 seconds old; each raw start and team pair independently matches the fixture. The source adapter rejects gaps instead of using closing spreads or publisher context guesses.

| Selection step | 2023 | 2024 |
| --- | ---: | ---: |
| Mapped reception pairs | 2,005 | 2,175 |
| Valid pregame prop price and clocks | 1,770 | 1,730 |
| Unique prior full-name/player/team identity | 1,448 | 1,316 |
| Fixed short-target role | 538 | 404 |
| Earlier fresh spread within six hours | 174 | 162 |
| Team spread at least +6.5 | 22 | 19 |
| One player per game under the original ranking rule | 14 | 12 |

The 17:00 UTC-request boards generally contain 16:55 UTC archive snapshots. That coverage loses 606 otherwise eligible short-role pairs at the six-hour spread join. It is especially incomplete for early Sunday and some primetime entries. This selected sample does not represent every 2023–24 underdog opportunity.

## Freeze, grading and interpretation

The original 2025 implementation is unchanged. The [wrapper](../tools/replicate_nfl_short_receptions.py) reuses its preparation and grading functions with explicit source/year configuration. Each year's same-season selection froze separately, then **all 26 selected prices froze together at 2026-09-13 18:46:41.465260 UTC**, before either year's completion fields were loaded for grading.

- Declaration SHA-256: `adb66658ac223620e161b119adb1f292c64cca042bb3d5043e667ec56fb0d241`.
- Combined selection SHA-256: `c979193d3127dddb8f178f4b576c6c8bc1e0a256fd937284bab26468fac4a9cd`.
- Original 2025 implementation SHA-256: `eedc26dee14c4b3d8f74bb8d02b0bce0a2dd25996e2bb306f053e239a1073483`.

Grading includes credited receptions in overtime and excludes nullified plays and two-point attempts. Valid participation or credited statistical plays verify every selected player. Historical jurisdiction-specific FanDuel settlement and injury protection remain unverified. These are archived listed prices with no proof of accepted wagers or a same-line closing series.

This is a separate exploratory prior-period replication, not an untouched or forward holdout. Previous project work inspected these seasons' sport outcomes, and the publishers analyzed their archives. Preserve the negative result and limited coverage. Do not relabel the formal sample-size result as a profitable strategy, rescue a year/player subgroup, or combine 2025 merely to reach the minimum. **Deprioritize Card 38 and test another hypothesis next.** Do not add seasons or boards to rescue this result.

The [JSON report](nfl-short-receptions-replication-2023-24-2026-09-13.json) retains all selected rows, source pins, year results and attrition. Reproduce with `PYTHONPATH=state/runtime/nfl-audit-lib python tools/replicate_nfl_short_receptions.py settle`; preparation refuses to replace the combined freeze. On a fresh checkout, first recover the hash-pinned input files listed in the result and run `python tools/acquire_nfl_replication_spreads.py`, then the wrapper's separate `source-audit`, `prepare` and `settle` phases in that order. The existing source audit's `--fetch` option recovers the pinned reception CSV; the existing NFL source loaders identify and verify the PBP/participation release files.

Source and wrapper compilation passed. An independent review verified all 114 board Git blob hashes, both year freezes, the combined freeze and the unchanged original 2025 implementation. It checked all 26 selections' prior-only roles, raw spread signs/starts and quote clocks; three predetermined rows independently reproduced full-name IDs, target depths and final receptions/profits. No material defect was found, and no freeze changed.

PBP attribution: nflverse/nflfastR, CC BY 4.0. Participation-derived identities: FTN Data via nflverse, CC BY-SA 4.0. Original third-party quote bodies remain ignored.
