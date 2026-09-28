# NHL anytime-scorer normalized consensus: frozen screen

Status: **frozen_before_target_grading**. Prior constant T = 5.4306 distinct scorers per game from 1312 completed 2023–24 games. 8,597 FanDuel anytime rows across 260 games have at least three literal reference ladders; 5 qualify and 5 are selected, one per game. No target outcome was read.

| Period | Rows / games | Qualifying rows | Selections | Best score | FD total implied | Reference total (median) |
|---|---:|---:|---:|---:|---:|---:|
| early_nov_dec | 4488 / 136 | 3 | 3 | 0.6427 | 6.065 | 6.973 |
| later_january | 4109 / 124 | 2 | 2 | 0.3536 | 6.050 | 6.590 |

Event exclusions: `{'event:fixture_unresolved': 1, 'event:original_debug_game_excluded': 1, 'event:publisher_error_payload': 12, 'prior:not_skater_position': 5247, 'prior:not_type_02': 3520}`. Row exclusions: `{'fewer_than_three_literal_references': 578, 'reference:power_root_unbracketed': 1, 'unresolved_player_identity': 134}`.

Rows: `data/raw/nhl-anytime-consensus-2026-09-28/reference-rows.csv`, SHA-256 `a7a6f7c2a5ddfd6ac2c7dab1ea5a9cbb28d7d675c635763737746e3f0a1bfbe8`. The [JSON](nhl-anytime-consensus-freeze-2026-09-28.json) pins the card, tool, inputs, every raw payload and the outputs.

The grader must verify those hashes and refuse zero selections. This is a price-reference screen in an inspected archive, not evidence of independent forecasting skill or executable prices.
