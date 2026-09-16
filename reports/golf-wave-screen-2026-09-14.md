# G1 forecast wave-direction screen

**sport-side dead at fixed directional screen.** Forecast-harder-minus-forecast-easier ability-adjusted scoring: **+0.259 strokes**, averaged equally across 25 events and their 49 contributing opening rounds. The fixed gates require +0.3 strokes and 20 events.

The [declaration](golf-wave-declaration-2026-09-14.md) fixes schedule-only wave identification, five-hour player exposure, every nonzero forecast direction, prior-only ability, event weighting and the bootstrap. Event-bootstrap 95% interval: [-0.0041966769096248415, 0.5071460903744573]. Full source hashes, every excluded round, per-wave player counts, signed results and diagnostic forecast gaps are in [the JSON report](golf-wave-screen-2026-09-14.json).

This tests **forecast direction**, not calibrated predicted stroke magnitude. No km/h-to-strokes coefficient or numerical pre-round stroke prediction was fitted. No G10 volatile-weather filter was used, and negative directional results remain in the average. The original forecast-revision response and numerical predicted-shift claims remain untested.

The operational run and archive clock checks come from the shared GFS acquisition. Retrospectively fetched tee sheets may reflect rescheduling; scheduled five-hour windows approximate actual play. Weather, firmness, player composition and imperfect ability control remain confounded. Recurring players and venues limit event-bootstrap interpretation. These observations do not prove historical quote-time availability.

No FanDuel markets, prices, settlement-aware returns or internal formula were tested. No betting edge is established. A directional pass requires separately declared magnitude calibration and actual timestamped offers before a book-side claim.

Reproduce offline: `state/runtime/research-venv/bin/python tools/explore_golf_wave.py --compare`.
