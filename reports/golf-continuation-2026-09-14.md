# Golf continuation — September 14, 2026

**One sport-side lead advanced; no market edge is established.** The active instruction is to continue searching until an edge is established. Scheduled jobs and watches remain paused; this continuation uses bounded work in the active session.

## New results

| Question | Result | Decision |
| --- | --- | --- |
| [G11 course rotation](golf-rotation-screen-2026-09-14.md) | +1.709 strokes relative to par in the declared direction; 950 player-events, 311 players, eight editions; event-bootstrap interval +1.111 to +2.192 | Passes the +0.5-stroke screen; investigate actual cross-course prices |
| [Sunday chasing variance](golf-sunday-screen-2026-09-14.md) | Variance ratio 1.0327; 421 exposed final rounds across 43 events; interval 0.8673–1.1941 | Fails the fixed 1.15 screen; no new bins or replacement years |
| [G10 shared-weather variance](golf-weather-screen-2026-09-14.md) | 4.420% reduction; 1,377 actual groups, 24 events; interval −0.419% to +9.284% | Adequate sample, below the fixed 10% screen |
| [G1 forecast wave direction](golf-wave-screen-2026-09-14.md) | +0.2586 strokes; 25 events, 49 rounds; interval −0.0042 to +0.5071 strokes | Adequate sample, below the fixed +0.3-stroke screen |

G11's Seaside-versus-Plantation comparison changes sign when expressed in gross strokes because the courses have different pars. A later market comparison must preserve its displayed scoring convention. The result is an observational course-assignment contrast, not a demonstrated omission from FanDuel's prices. Review removed an extra four-round-history requirement absent from the declaration and explicitly excluded exhibition matches; all derived player rows and results were unchanged.

## Price evidence and implementation

A bounded [source search](../docs/golf-price-source-continuation.md) recovered one complete historical FanDuel three-ball from a free publisher article and 14 actual derivative price rows in a public PGA wrapper fixture. Neither is a representative, timestamped quote history. No ROI, CLV or settlement was assigned. The collector now recognizes the fixture's direct selection-specific FanDuel links separately from explicit book fields, with conflicting or generic links rejected. **220 tests pass**, including 30 collector tests.

A separate six-query search for G11's multi-course prices found no usable complete FanDuel cross-course pair. An indexed PGA article names a 2025 RSM round-two McGreevy–Bridgeman matchup at -115 for McGreevy; the retained official tee sheet places both in group 1 on Seaside (course 776), so that example has no cross-course contrast. The indexed 2023 Pebble article describes course-separated first-round-leader markets at BetMGM. Neither answers the FanDuel G11 question. Both article opens returned 403, with no retries or raw-price backtest. This bounded search does not prove relevant markets are never offered. Sources: [RSM article](https://www.pgatour.com/article/news/draws-and-fades/2025/11/20/draws-and-fades-rsm-classic-thompson), [Pebble article](https://www.pgatour.com/article/news/draws-and-fades/2023/02/01/first-round-leader-pebble-beach-pro-am-gives-three-chances-to-collect).

A fresh one-cycle [Biltmore capture](../docs/golf-collection.md), more than two hours after the previous capture, also remained empty. Run `9a4a9d0227b7463bb2829870c2966489` at September 15 02:49–02:50 UTC made nine successful PGA requests: 135 field players and 10 alternates, zero tee groups, and zero actual prices. The stale outright widget still says the tournament is complete while the official event is not started. All 25 retained artifact hashes were checked. The collector stopped after that single cycle; no scheduled polling was enabled.

## Weather acquisition and comparisons completed

A [three-request retention probe](golf-price-retention-2026-09-14.json) also checked the public REST catalog for completed 2026 St. Jude and 2025 RSM, plus the exact St. Jude player endpoint used by the historical fixture. All returned HTTP 200 with empty market arrays. The endpoint cannot supply those old prices in this sample.

[NOAA operational GFS](../docs/golf-weather-archive-source.md) supplied a real Wednesday 2025 forecast. GRIB metadata independently identifies operational forecast output, initialization and valid hour. Selected wind-field byte ranges avoid downloading an entire 541 MB global file. Archive object modification remains distinct from proven historical public availability.

The [official group inventory](golf-weather-group-inventory-2026-09-14.json) covers all 40 declared 2025 single-course events: 3,390 opening-round groups. Preparation retains 8,339 complete player-rounds with prior history, with 1,347 omitted official player-rounds explicitly counted. [Completed source review](golf-weather-source-coverage-2026-09-14.json) verifies all 1,027 planned event-hours and 940 unique forecast files. All 40 events remain accounted for: 76 rounds are classified, and four are missing the two previously unresolved venues. Retained hashes, request/byte counts and clocks all reconcile. Two transport interruptions were recovered under a [bounded administrative policy](golf-weather-acquisition-policy-2026-09-14.md), preserving their failed responses; total acquisition was 1,882 requests and 1.839 GB. No partial cohort was scored.

The [G10 declaration](golf-weather-declaration-2026-09-14.md) fixes runs, weather windows, ability bins, controls and gates before comparisons. Its completed screen has 3,204 same-group pairs and 104,701 different-time controls; weighted score-difference variances are 15.4296 and 16.1431. The 4.420% reduction misses the 10% screen, with both sample requirements met. Independent reproduction matches all contributing cells, counts and the bootstrap to floating-point precision.

The separately frozen [G1 declaration](golf-wave-declaration-2026-09-14.md) identified 53 two-wave rounds across 27 events from schedules alone. After the four missing-venue rounds, its comparison uses 5,929 player-rounds across 25 events and 49 rounds. The +0.2586-stroke directional result misses +0.3. Its interval still includes zero and effects above the threshold; this is a failed point-effect screen, not proof of no weather effect. Independent reproduction verifies every forecast direction, round contrast, event mean, source hash and bootstrap result. No wind-to-strokes coefficient or forecast-revision response was fitted. Both weather specifications are now inspected and closed without stronger-wind subsets, new windows or replacement years.

Older G3, G2 and G5 decisions remain unchanged. No kernel, new confirmatory comparison allowance, live policy, alert or wager was added. The allowance remains 13.

## Fall-status prerequisite

The [G6 source check](../docs/golf-fall-exemption-source.md) inspected four official field PDFs across the 2024 and 2025 rule eras. They supply entry lists and certain entry-route markers, but no complete Monday points/rank and next-season exemption ledger. Some players near the cutoff already hold multi-year exemptions. G6 remains unresolved with no scoring comparison; rank alone was not substituted for its declared non-exempt exposure.

## Cut-rule prerequisite

The [G4 source map](../docs/golf-cut-rule-source.md) identifies 25 ordinary top-65-and-ties events, three hosted Signature exceptions, eight no-cut events and three sourced major rules; Masters remains unresolved. The completed [applied-cut audit](golf-applied-cut-audit-2026-09-14.md) reconciles 22 official thresholds and leaves a 20-event upper bound after wave/venue requirements. It retains a conflicting WWT note and two missing-source events. Bermuda's explicit official leaderboard metadata supplies its cutoff; some withdrawal and cut-approval timing remains unknown. This does not pass the effect-test sample gate: a declared calibrated scoring model/baseline/validation design is still required. No cut-line effect has been calculated. G1's failed directional screen does not decide this distinct mechanism, but does not justify a larger weather model for it.

## Next decision

G11 is the surviving golf sport-side lead. Its next useful test needs actual, complete FanDuel cross-course offers and their settlement convention; the bounded search has not found them. The current Biltmore feed is empty. Preserve these completed results, retain bounded manual collection for posted offers, and require concrete new price/source evidence before extending this golf batch. G2/G5 remain underpowered, G4/G6 remain untested, and G7/G8/G9/G12 remain conditional or parked. No betting edge, ROI, CLV or promotion has been established.
