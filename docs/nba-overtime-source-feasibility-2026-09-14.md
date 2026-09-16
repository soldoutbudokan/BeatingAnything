# NBA prior-night overtime source prerequisite — September 14, 2026

**The proposed points-Under test is not ready to select exposures.** This bounded local inventory found reusable source pins and schemas, but the documented NBA price, box-score and PBP payloads are absent from this checkout. Two schedules were restored concurrently by the root agent and independently rehashed here. The metadata does not establish an absolute prior-game completion time before an original FanDuel snapshot. This inventory made no network request, executed no publisher code and calculated no subgroup comparison or return.

## Current local availability

At the initial inventory, all four documented raw directories were absent:

- `data/raw/nba-source-feasibility/`: NBA Stats schedules and the 2024–25 player boxes.
- `data/raw/nba-consensus-price/`: full points-price archive, event mapping, 2025–26 boxes, ESPN schedules and original acquisition manifest.
- `data/raw/nba-blowout-source/`: 2024–25 processed play-by-play and lineups.
- `data/raw/new-prop-archive-sample/`: the original bounded price-source sample.

A workspace filename inventory, including ignored files, found no replacement NBA payloads. Before this note was finalized, the root agent restored `data/raw/nba-source-feasibility/nba_stats_schedule_2024.csv` and `data/raw/nba-consensus-price/nba_schedule_2025.csv`. Both match their prior SHA-256 pins below; their full CSV headers were inspected. The price archive, player boxes, mapping, 2025–26 schedules, PBP and lineups remain absent. The scripts and completed reports remain. Their earlier acquisition statements do not imply that all raw data is present in this checkout. Existing results were not edited or rerun.

## Reusable exact sources

The seven support-file pins below are retained in [the completed selection report](../reports/nba-points-consensus-2026-09-13-selection.json) and `INPUTS` in [the backtest script](../tools/backtest_nba_points_consensus.py). The two restored 2024–25 schedules were rehashed successfully; the other five pins remain saved prior checksums for absent files.

| Intended local file | Source URL | SHA-256 |
| --- | --- | --- |
| `data/raw/nba-source-feasibility/nba_stats_schedule_2024.csv` | [NBA Stats schedule 2024](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_schedules/nba_stats_schedule_2024.csv) | `ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26` |
| `data/raw/nba-source-feasibility/nba_stats_schedule_2025.csv` | [NBA Stats schedule 2025](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_schedules/nba_stats_schedule_2025.csv) | `e78976dfe77bc2137acf9e6cf5b10516593f2a476d74847336181a40c75b97a6` |
| `data/raw/nba-source-feasibility/player_boxscores_2025.csv` | [Player boxes 2025](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_player_boxscores/player_boxscores_2025.csv) | `7371d222692fee1c083913d813b125f885c4e53b6f3daaecb7270299913e9716` |
| `data/raw/nba-consensus-price/player_boxscores_2026.csv` | [Player boxes 2026](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_player_boxscores/player_boxscores_2026.csv) | `6ee53f72a953fc42c17cb7e9797af303cb102b853b67ca0b51cbc82c2260b270` |
| `data/raw/nba-consensus-price/nba_schedule_2025.csv` | [ESPN schedule 2025](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2025.csv) | `a7a5b6607a256c84a324f819e4461248bdff90a78b1ddb675a5a117a9a94e74f` |
| `data/raw/nba-consensus-price/nba_schedule_2026.csv` | [ESPN schedule 2026](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_schedules/nba_schedule_2026.csv) | `5a4a7473fce1c49d56382211c5955ad405f421d59869143b1d501e997e79223e` |
| `data/raw/nba-consensus-price/game_event_bijection.csv` | [Pinned event mapping](https://raw.githubusercontent.com/devlincorrigan/nba-props-threshold-app/233dbbc86b9c6e13df04d4e8b063581b3aa15abb/data/game_event_bijection.csv) | `23f27cc66b8b333fffd7b25d756f530d79dff0cafd69ff397cf16638000ed64c` |

The price archive is pinned to [`devlincorrigan/nba-props-threshold-app@233dbbc86b9c6e13df04d4e8b063581b3aa15abb`](https://github.com/devlincorrigan/nba-props-threshold-app/tree/233dbbc86b9c6e13df04d4e8b063581b3aa15abb/data/historical_points). Its `data/historical_points/<event-id>.json` files map to local `data/raw/nba-consensus-price/archive/<event-id>.json`. The earlier full inventory was 3,394 files / 397,273,601 bytes. [The acquisition script](../tools/acquire_nba_prop_archive.py) preserves the fixed commit, expected counts and Git-blob verification; it was not executed here. The saved [20-file selection](../reports/new-prop-archive-source-selection-2026-09-13.json) and [source audit](../reports/new-prop-archive-source-audit-2026-09-13.json) retain sample blob hashes and capture clocks.

For reference, the [prior PBP source check](../reports/nba-blowout-source-check-2026-09-13.json) pins `data/raw/nba-blowout-source/nba_play_by_play_2025.csv.gz` to [this release file](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_pbp/nba_play_by_play_2025.csv.gz), SHA-256 `534ceac1914ec3b38b51594748fcbddd34f3183a3c47dcf1c04ae53bbe04bcd1`. Its lineup companion is [nba_lineups_2025.csv.gz](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_game_lineups/nba_lineups_2025.csv.gz), SHA-256 `ff90b4e040664812ae741ef02718575ed826e3ac7cb7da7df63385842f5fef0d`. The failed lineup-to-minute interpretation need not be reopened for this mechanism.

## Documented usable fields and their limits

| Input | Retained schema evidence | Relevance and limitation |
| --- | --- | --- |
| Player boxes | `game_id`, `team_id`, `person_id`, `first_name`, `family_name`, `minutes`, `comment`, `position` | Stable player/team identity and direct `minutes` values in minutes:seconds can define a predeclared heavy-minute trigger. Blank minutes and explicit non-playing comments must remain distinguishable. Positions do not establish prior role. These files do not provide a verified game-completion clock in the retained evidence. |
| NBA Stats schedule | `game_id`, `game_date`, `team_id`, `team_name`, `matchup`, team-total `min` | Date/team joins can identify consecutive calendar-date fixtures. Team-minute totals can corroborate overtime length after reconciliation, but cannot establish wall-clock duration or completion. These are retrospective team logs. |
| ESPN schedule | `game_id`, `game_date`, `date`, `start_date`, `game_date_time`, `status_clock`, `status_period`, `status_type_completed`, `status_type_name`, home/away identities and `season_type` | The restored 2025 file supplies scheduled starts and retrospective final status, but no explicit end timestamp. Its date/time fields refer to the start; `status_clock` is a basketball clock. ESPN IDs differ from NBA IDs. The 2026 file remains absent. |
| Processed NBA PBP | `game_id`, `order_index`, `action_number`, `action_id`, `period`, `clock`, `seconds_remaining`, `action_type`, `sub_type`, `description`, `is_period` | `period > 4` can establish that overtime occurred. The complete 2025 schema retained in the source-check report has **no absolute event timestamp**. A final basketball clock of zero does not establish when the game ended in UTC. |
| Points-price JSON | Original `timestamp`, `previous_timestamp`, `next_timestamp`; event `id`, `commence_time`, home/away names; bookmaker `key`/`title` and `last_update`; market `key` and `last_update`; outcome `description`, `name`, `point`, `price` | Preserve the original snapshot and both quote clocks. `fanduel` / `FanDuel` and literal `player_points` identify the intended offers. Player names require conservative person-ID joins. Future market updates were observed previously and cannot be repaired by moving the snapshot. No original receipt clock, suspension state, accepted fill or later same-line close is established. |

The schedule filenames use season-start years, while boxes use season-end years: regular-season NBA game IDs beginning `00224` correspond to 2024–25 and `00225` to 2025–26. Preserve ten-character IDs as strings. No current trigger counts or price-eligible subset were calculated.

The restored ESPN schedule also contains `game_json`, `PBP`, `team_box` and `player_box` availability flags, plus `game_json_url`. The inspected row contains `true` flags and a URL to a separate final-game JSON, not an embedded primary event stream or its completion timestamp. These references are source leads, not verified clocks.

## Missing primary clock prerequisite

The required additional evidence is an **absolute, timezone-bearing timestamp for a clearly identified final/game-end action**, joined to the same official NBA game ID. A primary PBP wall-clock field such as `timeActual`, **if actually present and semantically verified in the planned official response**, is a candidate; its presence is not established by the retained processed schema. It must refer to the game's completion, not scheduled start, a period-relative clock, current download time or an undifferentiated later correction.

Before selecting an overtime/heavy-minute exposure, verify that this prior-game completion timestamp strictly precedes the original price `timestamp`, with the quote's own book and market clocks also eligible. The primary final marker, game identity, timestamp timezone and source semantics still need one bounded source check. No local primary response currently resolves that requirement. Reacquiring the old processed PBP alone would not add the missing clock.

This note leaves the proposed mechanism untested. It preserves the [NEXT-STEPS](../NEXT-STEPS.md) prerequisite and the existing completed NBA/golf results; it does not authorize a new threshold or claim an edge.
