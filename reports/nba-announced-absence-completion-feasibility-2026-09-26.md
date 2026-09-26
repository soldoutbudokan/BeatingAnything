# NBA2025–26 retained completion-clock feasibility

**1,294 ESPN games supply usable completion metadata for the intended prior-only cohort.** Of1,325 PBP games,1,320 have a unique timezone-bearing End Game marker;1,310 pass the zero-clock, no-later-play-clock and unique-schedule-start checks. A further16 have unsupported multi-day end timestamps and are conservatively excluded, leaving1,294.

The retained PBP contains642,472 rows. SHA-256 `f2d1ccc1a80febd90791d02390504d4a5331f2041169e3a85a4f052df27a0ffd` matches both stored metadata and GitHub release asset digest. The independent schedule matches its prior SHA-256 pin `5a4a7473fce1c49d56382211c5955ad405f421d59869143b1d501e997e79223e`.

| Schedule season type | PBP games | Structural checks pass | Usable for intended cohort |
|---|---:|---:|---:|
| 2 | 1234 | 1220 | 1204 |
| 3 | 85 | 84 | 84 |
| 5 | 6 | 6 | 6 |

Exclusions are four games without an End Game marker, one with duplicate final markers, ten whose nonfinal play wallclock follows the final marker, and16 unsupported finals more than12hours after scheduled start. All are preserved in the projection, with no inferred or corrected finish. Five schedule IDs have no retained PBP and are listed separately.

The16 duration anomalies span26.26–26.82hours after scheduled start. Some start near the scheduled time and acquire a next-day final marker; others have all recorded clocks shifted by roughly a day. No day subtraction is justified. Root requested their conservative exclusion after metadata QA; no source time or sporting threshold was changed. The CSV separates structural checks, the duration flag and final usability.

Projection: `data/raw/nba-announced-absence-2026-09-26/completion-clocks.csv`, SHA-256 `7bf49b9186b6b97c02b299fbf0ffd527ea8a26739370915731ef34de0d620cbd`. Every PBP game is retained, including excluded rows. Read the [JSON](nba-announced-absence-completion-feasibility-2026-09-26.json) for exact column projections, raw pins, source metadata, all exclusions and detailed long-clock diagnostics.

Under [the committed declaration](../docs/nba-announced-absence-declaration-2026-09-26.md), use a valid EndGame timestamp plus24hours strictly before the quote-minus60minute cutoff. The CSV includes this `declared_available_after_utc`; invalid rows leave it blank. This buffer is a conservative operational-delay assumption for retrospective statistics, not proof of initial publication.

Only PBP game ID, period, type/end marker, wallclock and game clock were projected. Schedule reads used only game ID, start/date, ordered team names and season type. No network, free play text, boxscore restoration, target results, player minutes or performance values were used. This inventory establishes ESPN identity/clock coverage, not official NBA/person mapping, injury eligibility or model success.
