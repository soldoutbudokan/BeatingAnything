# G10 weather covariance screen

**sport-side dead at fixed screen.** Same-group score-difference variance reduction: **4.420%** across 1377 actual groups and 24 events. The fixed gates require at least 10%, 300 groups and ten events.

The [declaration](golf-weather-declaration-2026-09-14.md) fixes the 40-event cohort, operational forecast run, complete weather window, prior ability, half-stroke gap bins, 180-minute control separation and event bootstrap. The [JSON report](golf-weather-screen-2026-09-14.json) retains variances, means, all contributing cells, attrition and source hashes. There were 37 classified volatile rounds and 4 unclassified rounds. Event-bootstrap interval: [-0.004190470037269023, 0.09283639679521316] in fractional reduction units.

This is an observational sport-side comparison. Scheduled tee windows approximate actual exposure; a round spanning dates can include nonplaying overnight hours in its fixed first-to-last wind-range window. Retrospectively fetched groups and archived model modification times do not establish a historical betting decision's complete information set. Repeated players, venue dependence, group selection and noisy ability remain limitations. The bootstrap conditions on the contributing events and preserves their original cells; its seed and requested/valid replicate counts are in the JSON. No FanDuel prices, returns or internal model were tested. No betting edge is established.

Reproduce offline: `state/runtime/research-venv/bin/python tools/explore_golf_weather.py --compare`.
