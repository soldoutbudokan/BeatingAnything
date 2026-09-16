# Golf research execution — September 14, 2026

**The first three golf screens do not establish an edge.** The lead dead-heat card fails its pooled effect threshold; withdrawal and weekend-information comparisons remain underpowered. The useful deliverables are real historical data, explicit results, corrected settlement assumptions and a working raw collector. The pricing-engine and confirmation stages remain conditional on a surviving effect and actual FanDuel prices.

## Executed

| Work | Result |
| --- | --- |
| [Hypothesis queue](../docs/hypotheses/GOLF-QUEUE.md) | Added the plan's nine golf cards plus three original mechanisms; ranked before comparisons. Preserved all 40 earlier cards and their completed research. |
| [Historical acquisition](golf-history-inventory-2026-09-14.json) | Recovered ESPN calendar-year scoreboards for 2015–2025: 548 dated event entries and six undated/empty entries retained as unknown. This is an available-source inventory, not proof of complete official tour coverage. Additional history was banked without expanding the inspected screens. |
| [G3: dead-heat allocation](golf-sport-screen-2026-09-14.md) | 2,651 eligible 2025 reconstructed three-player groups / 35 events. Ties for low: **15.843%**. Largest pooled correction against normalized strict wins: **0.470 percentage points**, below the prewritten 1-point gate. |
| [G2: repeat withdrawal](golf-sport-screen-2026-09-14.md) | **4/199 (2.010%)** exposed starts versus **48/4,641 (1.034%)** comparisons. The exposed rate is below 3%, only four repeat WDs occur against ten required, and both clustered difference intervals cross zero. No advance. |
| [G5: weekend information](golf-weekend-screen-2026-09-14.md) | R3 contrast: 0.1597 later strokes per early residual stroke; R4: 0.0836. The primary comparison has 200 player-events but just **11 events**, below 15 required; cut attrition is substantial. Unresolved. |
| [Live collector](../docs/golf-collection.md) | Final bounded run: **nine PGA HTTP 200 responses, zero failures, zero quotes**. Field: 135 players + 10 alternates. Biltmore tee times and market catalog were not posted. No process remains collecting. |
| [Rules and source checks](../docs/golf-rules-and-sources.md) | Corrected withdrawal rules, original-stake EV, weather information timing, status-era assumptions and the age of the cited Data Golf study. |

The G3 and G2 primary comparisons use 2025, with 2024 warming history; G5 also uses a prior-only 2024/2025 history. None is an untouched confirmatory experiment. Raw inputs and player-level intermediate records remain local under ignored `data/raw/golf-sport/`.

## What the findings mean

Ties are common, but their frequency is not the proposed mispricing. Once strict-win probabilities are normalized to sum to one, the pooled correction is small: best-ranked player −0.470 points, middle +0.397, worst +0.073. A favorable inspected skill-gap or round diagnostic cannot replace the failed pooled test. FanDuel's actual internal conversion remains unknown; no book error was measured.

ESPN groups are reconstructed from exact shared tee-time strings and the starting hole in ordered score records, excluding multiple-course ambiguity. They are not explicit official group IDs. A separate official PGA Sony Open 2025 response matched 138/140 complete reconstructed triples on membership/round/start tee; two differ by a player-name abbreviation and remain unmatched. This checks one event, not the whole dataset. The 2025 observed within-course/round score SD is 2.899 strokes across 15,088 complete rounds; it does not isolate intrinsic player variance.

The withdrawal comparison proves a start only when a scored hole is present. Zero-hole withdrawals can occur after a stroke, so they remain unknown. Omitted formats/tours and retrospective final-status publication constrain prior-history coverage. An incidence difference is not a matchup payout: verified Ontario settlement depends on cut/placing states, not a generic more-holes rule.

The weekend contrast is an association conditional on complete later rounds. Noisy prior ability, field strength and who survives the cut can create persistence. The prewritten event minimum was not met; bins and years were not changed to improve the result.

## Current data access

The [source checkpoint](golf-source-check-2026-09-14.json) records ordinary requests. PGA HTML, REST and GraphQL work on this machine. The provider default still names completed TOUR Championship `R2026060`; the checked-in configuration explicitly selects upcoming Biltmore `R2026557`. A FanDuel widget link is only configuration, not a bookmaker-tagged executable quote. The first optional current ESPN request returned 403 and was disabled; dated historical requests are separately accessible. Direct FanDuel also returned 403 and was not retried.

Data Golf advertises historical FanDuel archive coverage, but the needed full data requires appropriate paid access. No subscription was purchased and no restricted table values were used. The free route currently supplies sport data and empty PGA market responses, not a historical FanDuel derivative-price series.

Current GFS Single Runs and Previous Runs probes contain wind speed, gusts and direction. They establish schema access only. A fixed-lead series is not one Wednesday forecast, initialization is not publication, and earlier ECMWF hindcasts are not evidence of historical operational availability. G1/G10 need correctly joined venue, group and forecast clocks; G4 also needs event-specific cut rules. G6 requires the correct status era and exemption flags. G11 needs course assignments for named multiple-course event editions. G7/G8/G9/G12 remain conditional or parked.

## Run and continue

One bounded manual capture:

```sh
state/runtime/research-venv/bin/python -m beating.golf_collect --config config/golf-collection.json
```

Replay the completed screens from cache:

```sh
state/runtime/research-venv/bin/python tools/explore_golf_sport.py
state/runtime/research-venv/bin/python tools/explore_golf_weekend.py
```

The [collector instructions](../docs/golf-collection.md) cover finite multi-cycle runs and changing event IDs. Make further manual captures when groups and derivatives post. Before any price test, require actual book/market identities, all outcomes, clocks and applicable settlement terms. Empty responses do not qualify. Future events, forecast releases and access-dependent price tests cannot be completed from today's snapshots.

No golf kernel, monitor schema, three-way confirmation policy, alert or wager was added because no card has reached confirmation. The existing comparison allowance remains 13. Scheduled research and watches remain paused; no cron or background collector was installed.

**Validation:** 200 repository unit tests pass on Python 3.12.13, including 25 collector tests. Bounded review fixed nested book attribution, invalid/sentinel-price counting and elapsed-cap handling before the final capture. G5 arithmetic and prior-event chronology were separately checked. No card verifier or new CI workflow was built. Results and code are on the local `research/golf-derivative-exploration` branch; no remote default-branch publication occurred.
