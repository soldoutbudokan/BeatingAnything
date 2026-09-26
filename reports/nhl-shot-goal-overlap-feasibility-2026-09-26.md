# NHL same-clock shot/goal price feasibility

**2,184 paired player-games cover 239 games.** The fixed100-game gate passes in both periods: **True**. This is a price-only inventory; no shot/goal histories, conversion rates, old model probabilities or outcomes were read.

| Conservative-start UTC period | Paired player-games | Games | Players |
|---|---:|---:|---:|
| early_nov_dec | 1208 | 132 | 193 |
| later_january | 976 | 107 | 190 |

All285 pinned raw files and the unchanged roster/fixture metadata hashes pass. Pairing requires one FanDuel node, literal main-goal0.5 and main-shot half-lines0.5–8.5, exact full-name equality, valid American sides and overround0–15% for each pair. Shot-line selection occurs before goal overlap, by nearest normalized balance then lower line. Goal and shot market times must be identical and within72hours before the earlier provider/independent start. Debug game2024020345 and unresolved identities remain excluded.

Event exclusions: `{'publisher_error_payload': 12, 'missing_or_duplicate_main_shot_or_goal_market': 2, 'original_debug_game_excluded': 1, 'goal_shot_market_clock_mismatch': 30, 'fixture_unresolved': 1}`. Pair exclusions: `{'no_exact_literal_name_shot_anchor': 280, 'unresolved_player_identity': 28}`. Unresolved names: `{'Nicholas Paul': 3, 'Sebastian Aho': 13, 'Yegor Chinakhov': 1, 'Elias Pettersson': 11}`.

Detailed literal pairs and clocks: `data/raw/nhl-shot-goal-overlap-2026-09-26/paired-prices.csv`, SHA `682018f651fd789ee35a3671b39340eda055917d03124d8ce12be9a864a379d3`. The [JSON](nhl-shot-goal-overlap-feasibility-2026-09-26.json) pins metadata and the ignored raw event/source ledger.

A coverage pass only permits a separate prior-only model declaration; it does not establish shooting-history availability, fair probabilities, execution or an edge. A failure ends the exact clock/scope cohort before performance work. The market clock is an entry proxy, and these inspected archive periods are exploratory.
