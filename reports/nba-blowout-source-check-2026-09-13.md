# NBA bench-minutes source check — September 13, 2026

**Inputs recovered, but not ready for the conditional test.** SportsDataverse's public [NBA Stats PBP release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_pbp) and [game-lineup release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_game_lineups) each cover all **1,230 regular-season games in 2024–25**, with 606,536 event rows. Both downloads matched publisher SHA-256 digests. These are processed publisher datasets, not newly acquired official live observations. The previously blocked direct NBA endpoint was not retried.

The PBP carries clocks, scores, substitutions and inferred offensive/defensive player lists. The separate lineup file carries home/away player IDs at event rows. It is not a clean interval table despite the release's broad “stints” description. The ending-year filename `2025` corresponds to game IDs starting `00224`; raw files also contain other game types and must be filtered.

## Concrete validation result

The initial strict game/action-number join failed. There are **32,179 extra repeated action-number keys in each regular-season file**, including distinct shot/block and turnover/steal records. These are not all accidental duplicates: the PBP has zero exact duplicate rows. Do not use a many-to-many join or drop distinct events. Game plus `order_index` is unique in PBP. The two complete game/action/period row sequences agree, allowing a **source diagnostic** by retained row order, not proof of the semantic timing of each lineup.

The lineup file has 1,192 rows without ten distinct positive player IDs. On 90,427 row-aligned events, the two files do not supply matching complete ten-player sets; that count includes missing PBP IDs as well as differing sets. After exact duplicate lineup rows are removed for inspection only, 73 repeated game/action keys still have nonidentical lineup records. No source rows were removed for a sport-side estimate.

Before computing minute discrepancies, the check was fixed to the first six regular-season games by schedule date/game ID, every player, with a two-second tolerance. The lineup at each event was assigned the playing-time interval to the next event, using unique PBP order and period-aware clocks. All six games have nonnegative intervals, a 2,880-second end and no lineup ID outside the box-score roster. **All six nevertheless fail minute reconciliation:** 66 of 172 player-box rows differ by more than two seconds. The largest absolute difference is 159 seconds, and three players with positive official minutes receive zero derived minutes in the sixth game.

This rejects the tested interval interpretation as ready-to-use. It does not isolate whether each discrepancy comes from lineup reconstruction, event timing, source corrections or interpretation. The complete differences, source hashes and schemas are in the [JSON report](nba-blowout-source-check-2026-09-13.json). No alternative shift alignment, margin threshold, bench definition or conditional effect was tried after this result.

## Decision and next use

The existing [blowout bench-minutes card](../docs/hypotheses/basketball-blowout-bench-minutes.md) remains unresolved; its 200-player-game/+3-minute gate is unchanged. **No blowout/minute effect was measured.** Park this derived-lineup route unless a specific source-semantic correction or independently validated lineup source becomes available. Do not repeat these downloads or turn the problem into an open-ended reconstruction project. The raw score/event stream may support a different mechanism that does not depend on exact player minutes, but that would need a separate prewritten definition.

Run `python tools/inspect_nba_blowout_sources.py --download` to reproduce. The source check also uses the already pinned 2024–25 schedule and player box scores from the NBA assists work. Raw publisher files remain ignored. Attribution: NBA Stats-derived data distributed and processed by SportsDataverse. No raw PBP or player lists are redistributed.
