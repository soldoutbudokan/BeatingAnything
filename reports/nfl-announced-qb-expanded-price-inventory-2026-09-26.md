# Expanded announced-QB receiving-yard price inventory — September 26, 2026

**The retained file supplies 1,770 price-qualified receiving-yard pairs across 164 regular-season fixtures and 282 uniquely mapped players.** These are feasibility upper bounds before any injury announcement, prior receiver-role or availability requirement. No eventual starter, target performance, participation, fitted model or return was read or calculated.

The source is the [pinned firstandthirty/nfl-tools processed export](https://github.com/firstandthirty/nfl-tools/blob/e919241eb9fc17f057005348c7869a37b23e7675/player_props/data/processed/merged_props_with_context.csv). Its 2,424 receiving-yard pairs cover 222 events from 2024-09-08 17:00:00+00:00 through 2024-12-31 01:16:00+00:00. Independent NFL fixture metadata supplies weeks and scheduled kickoff; publisher outcome/context/week columns are ignored. The [JSON inventory](nfl-announced-qb-expanded-price-inventory-2026-09-26.json) records every source hash, projected column, fixture/team/week count, and exclusion.

| Week | Scheduled REG games | Games with reported prices | Games passing price gates | Usable pairs |
| --- | ---: | ---: | ---: | ---: |
| 1 | 16 | 14 | 14 | 163 |
| 2 | 16 | 16 | 12 | 135 |
| 3 | 16 | 16 | 14 | 163 |
| 4 | 16 | 16 | 12 | 128 |
| 5 | 14 | 12 | 7 | 79 |
| 6 | 14 | 11 | 8 | 85 |
| 7 | 15 | 12 | 10 | 101 |
| 8 | 16 | 13 | 10 | 108 |
| 9 | 15 | 12 | 6 | 55 |
| 10 | 14 | 12 | 11 | 115 |
| 11 | 14 | 13 | 10 | 110 |
| 12 | 13 | 13 | 10 | 111 |
| 13 | 16 | 16 | 9 | 96 |
| 14 | 13 | 13 | 8 | 87 |
| 15 | 16 | 13 | 9 | 87 |
| 16 | 16 | 11 | 8 | 82 |
| 17 | 16 | 9 | 6 | 65 |
| 18 | 16 | 0 | 0 | 0 |

Gates are legal American prices, both decimal odds 1.20–6.00, paired overround 0–12%, both book/market updates 0–300 seconds before the original snapshot, snapshot strictly before the earlier provider/independent start, uniquely matched ordered fixture within the existing 15-minute tolerance, and one GSIS ID under unchanged full-name normalization. Integer lines remain flagged for pushes; 0 survive, versus 1770 half-point lines. Mutually exclusive first failures are `{'future_book_or_market_clock': 630, 'player_identity_not_unique': 24}`. No line, price, role or sample rule was optimized.

There are 328 potential fixture-team opportunities, of which 328 have at least one price name whose retrospective roster team uniquely matches that side. This latter attribution is **not evidence of prequote team membership**; 48 otherwise price-qualified rows have unresolved roster-to-fixture team context and remain retained. Per-team tables and unresolved names are in JSON. Roster-compatible team counts are provisional, not guaranteed complete upper bounds: unresolved traded-player rows may belong to either side. Until prior team membership is proven, the full fixture distinct-player count is the conservative team-game ceiling. No player was removed for failing to appear in a target game. There are 1,764 distinct priced player-games and 6 extra quote rows across six repeated player-games.

A score-free reusable CSV is saved at `data/raw/nfl-announced-qb-expanded-price-inventory-2026-09-26/eligible-price-rows.csv`, SHA-256 `a6c788a97b861d14c36f1e26d3f894c79ca226ad8ff13916c2bf97fe01326beb`. It contains literal source prices/clocks, fixture IDs/weeks, identity IDs, and clearly labeled retrospective roster metadata. It contains no QB-event classification or sporting values. A future episode join must preserve all candidate and missing-identity/announcement counts instead of treating these prices as a selected cohort.

Available prior-role inputs are `data/raw/nfl-qb-kneel-props-2026-09-26/player_stats_2024.csv` (header includes targets, receiving air yards, air-yard share, player/team/season/week/position) and the original `data/raw/nfl-source-audit/play_by_play_2024.qs`. Only schemas/hashes were inspected here. The kneel-oriented PBP projection omits receiver/air-yard fields, so it cannot by itself supply receiving roles. The existing score-free `data/raw/nfl-fixture-feasibility/fixture-metadata.json` covers 2025 only; this audit safely projects 2024 fixture columns from `games.csv`. The weekly stats lack game IDs and publication/availability clocks. The full 2024 QS was released in September 2025, so its source vintage is retrospective for this study. Prior-role calculations still need strict prequote game availability and independent receiver health/team evidence; roster season-end context is insufficient.

Original API bodies and the unmerged odds CSV remain absent. Published collector code directly copies prices, but duplicate same-side keys can overwrite a price while preserving initial clock metadata; whether this affected any row is unknown. Most events have one snapshot, but six reported receiving-yard events contain multiple times. Three retain repeat qualified player-games: ATL–PHI September 16, JAX–BUF September 23, and CLE–DEN December 2. Their six repeated player-games have different lines/times. All six events and their distinct qualified timestamp sets are listed in JSON. The inventory preserves every qualifying row. The separately committed [quote-deduplication addendum](../docs/nfl-announced-qb-quote-dedup-addendum-2026-09-26.md) (`800ae48`) fixes the earliest qualified post-announcement entry per game/player and excludes exact-time multiline conflicts before any cohort/model use; no later failed-clock rescue or duplicate receiver-game counting is allowed. These sparse snapshots do not establish a causal announcement response, actual receipt, suspension state or an accepted fill. Existing sporting outcomes were inspected in unrelated work; this price-only inventory does not create a new untouched holdout. No new source request, schedule, alert or wager occurred.
