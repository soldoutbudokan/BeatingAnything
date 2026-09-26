# NBA foul-risk proposal: identity-only feasibility

**8,038 of 8,286 paired offers map uniquely** across the frozen 666-game price universe. There are 248 unmatched and 0 ambiguous offers. All 666 events retain at least one unique name; 446 have every offered name uniquely mapped.

The 370 literal offered names contain 359 unique matches, 11 unmatched names and 0 ambiguous names. They map to 359 distinct ESPN athlete IDs. Normalization removes accents, punctuation and whitespace while retaining all suffixes. No fuzzy or short-name aliases were introduced.

Only `athlete_id` and `athlete_display_name` were materialized from the player parquet. The entire retained identity universe was used; a target-game appearance was never required. The source hash matches both metadata and the retained GitHub asset digest. No minutes, fouls, points, participation flags, roles or history counts were read or computed.

| Period | Events | Unique pairs | Unknown pairs | Ambiguous pairs |
|---|---:|---:|---:|---:|
| calibration | 293 | 3589 | 114 | 0 |
| evaluation | 373 | 4449 | 134 | 0 |

Unresolved literal names:

- Carlton Carrington: unknown, 37 pairs / 37 events; candidate IDs [].
- Derrick Jones: unknown, 26 pairs / 26 events; candidate IDs [].
- Herb Jones: unknown, 32 pairs / 32 events; candidate IDs [].
- Isaiah Stewart II: unknown, 23 pairs / 23 events; candidate IDs [].
- Jimmy Butler: unknown, 27 pairs / 27 events; candidate IDs [].
- Moe Wagner: unknown, 4 pairs / 4 events; candidate IDs [].
- Nicolas Claxton: unknown, 38 pairs / 38 events; candidate IDs [].
- Paul Reed Jr: unknown, 7 pairs / 7 events; candidate IDs [].
- Robert Williams: unknown, 19 pairs / 19 events; candidate IDs [].
- Ron Holland: unknown, 19 pairs / 19 events; candidate IDs [].
- Vincent Williams Jr: unknown, 16 pairs / 16 events; candidate IDs [].

The schema also contains stable game/team/athlete IDs, game date/time, season/type, ordered side and opponent IDs for a later declared prior-history join. Those fields were inspected as schema names, not used to infer current team membership. `minutes`, `fouls` and `points` exist in the schema but their values remain unread.

This establishes identity coverage only. Retrospective names do not prove prequote membership or adequate history, and no foul-risk exposure, effect or forecasting model is established. Source pins, every offered-name mapping and per-event counts are in the [JSON](nba-foul-risk-identity-feasibility-2026-09-26.json). The isolated tool refuses to overwrite outputs.
