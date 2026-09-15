# CFL rouge-rule screen — September 13, 2026

**Unresolved: kick trajectories/touches are absent and one scoring total differs.** The fixed 2024–25 source reports 154 single points in 162 games. Conditional on those counts, removing every single would subtract 0.951 points per game; removing none gives zero. This arithmetic range is not an estimated effect or a validated bound on true scoring. It cannot pass the card's 100-classified-kick/0.5-point screen.

| Season | Regular-season games | All scored singles | Removed points per game, possible range |
| --- | ---: | ---: | ---: |
| 2024 | 81 | 81 | 0–1.000 |
| 2025 | 81 | 73 | 0–0.901 |

Seventeen of eighteen team-season aggregate point totals match regular-season fixtures. **Montreal 2024 is 455 in fixtures versus 453 in the aggregate; the two-point discrepancy remains unresolved.** Singles scored reconcile to singles allowed at league level in both years, but that is not independent validation of each kick. Missing punt/kickoff subcategories remain null, and all singles must not be reclassified as abolished. No counterfactual score was reconstructed.

The official public [CFL Stats endpoint](https://api.stats.cfl.ca/stats/teams) supplies the historical aggregates. Its URL is referenced by the public [CFL Stats site](https://stats.cfl.ca/). The older SDK endpoint requested with `season_id=33` returned only **2026** records, so it was rejected as 2024 evidence. The newer endpoint's explicit nested season/year fields were checked before aggregation. Complete fixture lists were recovered from [CFL's public fixture service](https://echo.pims.cfl.ca/api/seasons/33/fixtures?limit=100).

Current official fixtures put the regular-season end on **2026-10-24**, only **41 days** from this screen. CFL is included at the user's suggestion, but this season does not solve the short-runway concern. Preserve this study and use the longer NBA/rugby calendars for active work. Further announced field and goalpost changes mean these definitions must not be carried unchanged into 2027.

The [new card](../docs/hypotheses/cfl-rouge-rule-scoring.md) was saved before historical scoring aggregation. Public rule-change descriptions identify untouched end-zone exits as removed singles while preserving returner concessions. CFL article reads returned 403 and the linked rulebook web reader returned 405; no repeated requests or alternate authenticated route was used to overcome those denials. Primary calendar fixtures and aggregate stats were available through their separately published ordinary public services.

Next missing input: permitted event records that explicitly distinguish untouched boundary exits, return touches and concessions for the pinned 2024–25 games. Do not build a game-total model from these bounds or infer book error from a public rule change. No FanDuel market prices were collected.

Run `python tools/explore_cfl_rouge.py`; `--fetch` retrieves missing public inputs once and verifies their pinned hashes. A changed live source is rejected, not silently substituted. [JSON results and source hashes](cfl-rouge-screen-2026-09-13.json). Raw third-party files remain ignored.
