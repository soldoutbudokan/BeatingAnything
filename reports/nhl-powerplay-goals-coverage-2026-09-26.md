# NHL power-play goal-prop price coverage — September 26, 2026

**2,768 eligible paired FanDuel Over/Under 0.5-goal offers cover 270 games and 255 uniquely identified players.** This audit reads only raw prices, roster names/IDs and score-free fixture metadata. It reads no player boxscores, power-play statistics, target outcomes, forecasts, returns or eventual participation.

| Conservative start UTC | Eligible pairs | Games | Distinct players |
| --- | ---: | ---: | ---: |
| early_through_2024_12_31_utc | 1,506 | 146 | 234 |
| later_from_2025_01_01_utc | 1,262 | 124 | 221 |

All 285 retained raw JSONs match the acquisition manifest: 273 event payloads and 12 publisher quota errors. There are 2,826 raw FanDuel goal-player/line pairs before identity/fixture exclusions. Exact `player_goals` at 0.5 is used, with literal Over and Under, a common market update, valid American odds and paired overround 0–15%. Every retained update is within 72 hours before the earlier provider/independent start. Ordered teams must match one regular-season fixture within one day; the original source-debug game `2024020345` remains excluded.

Earliest qualifying quotes are retained by event/player without conditioning on eventual play. Full-name normalization and global unique-ID mapping are unchanged from the prior NHL tests. Unresolved names remain excluded with their counts: `{'Nicholas Paul': 4, 'Elias Pettersson': 15, 'Sebastian Aho': 13, 'Alex Wennberg': 3, 'Yegor Chinakhov': 1}`. Mutually exclusive pair exclusions are `{'ambiguous_or_unmatched_player_identity': 36, 'original_debug_game_excluded': 10, 'fixture_unresolved': 12}`. Missing markets, mapping failures and source errors remain in the JSON's explicit ledger.

The UTC calendar split is metadata-only and is not a claim of untouched validation. No reference-book, shooting-history, power-play-role or model threshold filters are applied. Power-play input semantics and prior-history coverage still require their own audit before a model can be declared. An independent reconstruction agrees on all counts and exclusions: 28 ambiguous-name pairs and eight unmatched-name pairs, with no timing, pairing, odds, margin or duplicate failure among fixture-eligible markets.

Market update times lack independent receipt and accepted-price evidence. Retrospective roster membership supplies identity, not a known pregame participation list. The fixed source is [sports-betting-ops@42cf1f8](https://github.com/ldinan-git/sports-betting-ops/tree/42cf1f81bc302642ddcc9e88ce2e98c1057bc74d/bet-ops/odds_api_responses/player_props/output/icehockey_nhl/player_props); exact local source/projection hashes and every covered game are in the adjacent JSON. Canonical eligible-cohort hash: `798416fa24c8f9540262063fbc673f8fc40af146f0fb31138d36985b432698eb`.

The score-free model input is `data/raw/nhl-powerplay-goals-2026-09-26/price-entries.csv`, SHA-256 `207142b0331aac35b6ec6e9dd4db725e49ff683c1cf7fbd8e04197ca5c6fad41`. It includes literal prices and proportional `q_under`, event/player identity, source file, entry and boundary clocks, team abbreviations and the fixed `early_nov_dec` / `later_january` labels. Those labels use the conservative start's UTC date, so a December 31 local game can enter the later period. No power-play feature, modeled probability or result is included.

Reproduce with `python3 tools/inventory_nhl_powerplay_goals.py`. Its `audit()` function also returns the exact eligible rows for a separately declared experiment. No old frozen files were changed; no network request, wager, alert or schedule.
