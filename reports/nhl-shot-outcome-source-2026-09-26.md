# NHL player shots source audit — September 26, 2026

**Recoverable:** complete 2023–24 and 2024–25 regular-season skater game tables, NHL player IDs, full-name crosswalks, and independent 2024–25 scheduled UTC starts. No model or price-return evaluation was performed in this source audit.

SportsDataverse publishes these tables from NHL API inputs; this is a public publisher archive, not an NHL-operated download. Its [source repository](https://github.com/sportsdataverse/fastRhockey-nhl-data) documents the raw-to-compiled pipeline and links the [player boxscore](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nhl_player_boxscores), [roster](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nhl_rosters), and [schedule](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nhl_schedules) releases. Previously blocked NHL endpoints were not retried.

All acquired inputs, GitHub release metadata, hashes, and structural checks are retained under `data/raw/nhl-shot-archive-2026-09-26/outcomes/`; `source_audit.json` contains the machine-readable source pins. Ending-year filenames identify the season: `2024` means 2023–24 and `2025` means 2024–25.

| Boxscore source | All player rows | All games | Regular-season skater rows | Regular-season games | Regular-season skaters |
| --- | ---: | ---: | ---: | ---: | ---: |
| [player_box_2024.csv](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_player_boxscores/player_box_2024.csv) | 55,988 | 1,400 | 47,221 | 1,312 | 924 |
| [player_box_2025.csv](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_player_boxscores/player_box_2025.csv) | 55,913 | 1,398 | 47,225 | 1,312 | 920 |

The exact outcome field is `shots_on_goal`. Both files contain `game_id`, stable NHL `player_id`, `game_date`, `team_abbrev`, `home_away`, `position`, and `toi`. Select skaters with `position` in `C/L/R/D`; blank-position goalie rows do not carry skater shots. Select regular season using the `02` game-type component, e.g. `game_id[4:6] == "02"` when IDs are strings. Both files have zero duplicate `(game_id, player_id)` pairs and zero missing skater shot values. Date ranges are 2023-10-10 through 2024-06-24 and 2024-10-04 through 2025-06-17. November 2024 through January 2025 contains 658 regular-season games, 23,687 skater rows, and 825 players.

Boxscore names are abbreviated. [rosters_2024.csv](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_rosters/rosters_2024.csv) and [rosters_2025.csv](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_rosters/rosters_2025.csv) provide `full_name`, `player_id`, `game_date`, and `team_abbr`. Each boxscore row in both seasons joins uniquely on date, player ID, and team: zero missing or duplicate joins. One 2024–25 player ID has multiple full-name spellings across the season, so retain the date-specific crosswalk and audit aliases rather than treating names as permanent IDs.

`schedule_2025_metadata.csv` is a score-free projection of [nhl_schedule_2025.csv](https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_schedules/nhl_schedule_2025.csv). It contains 1,398 unique `game_id` values, `game_time` as UTC ISO8601, both team abbreviations, and `game_state`. There are no missing game times, unmatched boxscore game IDs, or mismatched teams. **Join on `game_id`: schedule `game_date` uses the UTC calendar date, while boxscore `game_date` is the local game date.**

The retained ESPN summary for Vancouver at Boston on November 26, 2024, matches all 36 skaters' shot values. NHL game `2024020345` and ESPN event `401687944` agree on the scheduled start, `2024-11-27T00:00:00Z`. David Pastrnak (`8477956`), for example, has three in both sources. The ESPN field used is `shotsTotal` (label `S`); ESPN `shootoutGoals` (label `SOG`) is a different statistic. Raw evidence and the comparison are saved as `espn_summary_401687944.json` and `nov26_espn_crosscheck.json`.

SHA-256 pins, verified against GitHub's asset digests:

```text
889d439dae5b5a2e831496a3a0dcbea4d385883d68d55b70d55a554169ff6e74  player_box_2024.csv
511f58b09996be6165c7ad2a0f475ac029f0206653ce4e11665e1ff8088516b0  player_box_2025.csv
0e70a12579b25af0532d00a0cf8bb5fda7d9eb33a23d76234ca26f2fff4ca4ba  rosters_2024.csv
cff04536329e7a7f3cdf9034786226e6644a7d222486eb70d4a799d12c1f80ba  rosters_2025.csv
017f89619c13857e8b7f2f52ccbf7c1ea20fcef46f5bc90de719ea12475d1e00  original nhl_schedule_2025.csv
320643ed83428e28671c7508c667026ab65c46b85bcf312d173c2b025d98e855  retained schedule_2025_metadata.csv
```

**Retrospective limitation:** the boxscore and roster assets were published June 3, 2026; the schedule asset was published July 18, 2026. They can support historical final counts, stable identity, strictly earlier game-date histories, and comparisons to the archived scheduled starts. They do not prove when individual stat corrections, names, or schedule revisions became available in 2024–25. The single ESPN comparison verifies parsing for one game, not every historical row. Roster presence is recorded after the game and must not be treated as proof of pregame participation knowledge.
