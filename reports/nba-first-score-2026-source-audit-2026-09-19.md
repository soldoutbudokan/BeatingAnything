# 2026 first-score sources: identity and settlement audit

## What is established

The completed manual acquisition retained **226 responses / 10,619,280 bytes**: four fixture calls, 148 successful history calls, 73 explicit missing-history responses and one rate-limit rejection followed by the declared retry. The documented metered charge is four fixture calls. FanDuel has active pregame first-scorer entries in **92/221** games, BetMGM in **129/221**, and both in **73/221**. Presence is not yet a complete usable board.

The fixed five-minute decision procedure admits **16 games**, with seven primary selections and five under the original probability-reserve sensitivity. Exclusions, evaluated in declared order: 40 Fridays, 67 explicit absences, 90 FanDuel boards without exactly ten active players, three unresolved FanDuel player identities and five BetMGM boards without exactly ten active players. None of the 16 has all twenty entries within 300 seconds of decision. These are source-state forecasts, not proof of the previous quote-freshness gate. Their [freeze manifest](nba-first-score-2026-forecast-freeze-2026-09-19.json) precedes outcome grading.

The fixed [acquisition declaration](../docs/nba-first-score-2026-acquisition-plan-2026-09-19.md) selects **221 NBA fixtures**, March 15 through April 12 UTC, before requesting individual histories. Every fixture uniquely matches the independent ESPN-derived 2026 play-by-play archive by full team names and scheduled start within 12 hours. All are regular-season type 2. **220 start times agree exactly**; `id1100013262924677` / ESPN `401810913` differs by 12 minutes (provider 01:30, independent 01:42 UTC, March 26). The validation uses the earlier start.

The authenticated provider player directory supplies 13,262 distinct player IDs across 747 participant groups. Unique full normalized names match **598 provider IDs** to ESPN identities. Multiple provider IDs can refer to the same person; a price board must still contain ten distinct people. Current team groupings are not historical lineup evidence. The ten players in the earlier May sample all resolve. No suffix removal, current-team rescue or outcome-driven aliases were used.

Independent first-score and starter labels were **not read during this source audit**. The retained box-score file exposes starter flags for later settlement. Identity preparation reads only player ID/name columns; fixture matching reads only game/team/date/type metadata. Outcome access is separated by the [2026 validation protocol](../docs/nba-first-score-2026-validation-protocol-2026-09-19.md) and a committed forecast freeze.

## Dated rules and the remaining identity limit

The Massachusetts regulator's [obsolete-rule archive](https://massgaming.com/about/sports-wagering-in-massachusetts/sports-wagering-licensees/archive-sports-wagering-licensees-obsolete-house-rules/) provides dated versions spanning the cohort:

| Book/version | Relevant page | Definition |
| --- | --- | --- |
| [BetMGM November 24, 2025](https://massgaming.com/wp-content/uploads/BetMGM-House-Rules-11.24.25.pdf) | 25 | First field goal excludes free throws. Archive marks obsolete April 22, 2026. |
| [FanDuel December 16, 2025](https://massgaming.com/wp-content/uploads/FanDuel-House-Rules-12.16.25.pdf) | 30 | First basket includes free throws; selected nonstarter void. Archive marks obsolete March 30, 2026. |
| [FanDuel March 30, 2026](https://massgaming.com/wp-content/uploads/FanDuel-House-Rules-3.30.26.pdf) | 30 | Same first-basket definition and nonstarter rule; obsolete July 30, 2026. |

These pages were extracted, rendered and visually checked. The December FanDuel PDF contains an approval-date placeholder; its regulator archive date is the evidence for version placement. The separately retained April 22 BetMGM book repeats the relevant definition. A February regulator meeting packet initially searched contains Penn Sports Interactive rules at its first-basket hit, and is **not** attributed to FanDuel.

This supports a conditional distinction between the books, but the historical OddsPapi payload retains a normalized Player First Point key rather than original displayed labels/jurisdictions. Exact quote-level settlement identity remains unverified.

## History clocks

The provider's [history explanation](https://oddspapi.io/blog/dynamic-odds-price-movement-python/) distinguishes current-odds `changedAt` from historical `createdAt`, which records a snapshot. Latest-entry reconstruction is an explicit provider-state assumption. An old last entry alone neither proves the price is stale nor establishes continued bookmaker availability. The old experiment's bookmaker-update/collector-receipt freshness evidence is not recovered by renaming this clock. All entry ages remain reported; the five-minute age diagnostic is separate from the main conditional reconstruction.

## Pinned local evidence

Raw files and receipts remain Git-ignored under `data/raw/oddspapi-first-basket-audit-2026-09-19/`:

| File | SHA-256 |
| --- | --- |
| `players.json` | `8b39c3e47925ec9b96ee607bd3890961a3b4042059e84dfea8b9ca494a3c1b05` |
| `play_by_play_2026.parquet` | `f2d1ccc1a80febd90791d02390504d4a5331f2041169e3a85a4f052df27a0ffd` |
| `player_box_2026.parquet` | `29a29dc9efd055a93e069a0382ac830d98a13274bee655beba69d95cff099713` |
| `betmgm-2025-11-24.pdf` | `5d6c06d7b590438ac08882162adafde88e0c51979199bb57507209895d0b6131` |
| `fanduel-2025-12-16.pdf` | `75c3c4fd43feee895008c95fb8a487efd310da1e935623ec1c950e102d7ce976` |
| `fanduel-2026-03-30.pdf` | `3b63090070ba1e633d4a579ca08d8ae5ee91b7ea4121841f0d8eab0f11eb0e86` |

The independent files come from sportsdataverse's [ESPN NBA PBP release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_pbp) and [player box-score release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_nba_player_boxscores); downloaded bytes match the published release digests. They are retrospective archives, not proof of contemporaneous lineup publication. The [hoopR loader documentation](https://github.com/sportsdataverse/hoopR/blob/master/R/load_nba.R) identifies the ESPN-derived source and fields.

The API credential is read privately from the existing ignored file. The bounded manual acquisition uses four fixture queries and one targeted history request per fixture. Exact provider `NOT_FOUND` responses remain missing-history rows. One historical-endpoint rate-limit response prompted a correction to wait at least 5.1 seconds **after response completion**, and one declared retry of the pending fixture. Original responses and stop/resume records are retained. No account endpoint was retried, account changed, subscription bought, wager submitted or scheduled task resumed.
