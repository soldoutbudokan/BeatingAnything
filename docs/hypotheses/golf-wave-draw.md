# G1 — Forecast revision and cross-wave round prices

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / pre-round cross-wave 2-balls and make-cut / FanDuel.

**Structural fact:** Players encounter different weather at different hours; a same-group additive wave shift cancels from relative scores.

**Predicted behavior (measurable):** A forecast available before the quote predicts >=0.3 strokes of the subsequent wave scoring difference after prior-ability adjustment.

**Why FanDuel's price ignores it:** Unverified: derivative prices update less than main prices after a public forecast revision.

**Trigger (observable, timestamped):** Tee-time release plus a named forecast run actually available by Wednesday quote time; retain initialization, publication/availability and collector time separately.

**Sport-side test: data source, cost, kill criterion:** Use historical tee times, prior-round ability and realized weather for descriptive feasibility. Then 2024–26 archived genuinely as-issued runs, >=20 events with both waves. Compare forecast-implied and realized field-adjusted wave differences, withholding later runs. Kill below 0.3 strokes average predicted/realized directional separation. Fixed Previous Runs offsets are not a Wednesday snapshot; hindcasts are not historical public forecasts.

**Book-side test: what odds at trigger time, forward or historical:** Capture Tuesday and Wednesday/Thursday pre-start 2-ball and make-cut prices. Compare movement to the independently estimated weather effect; kill if >=70% is reflected. Separate first-round-leader exploration because it is outside current policy.

**Status:** closed at the fixed directional sport-side screen; numerical forecast magnitude and revisions untested

**Source advance before comparison:** [NOAA's operational GFS archive](../golf-weather-archive-source.md) supplied a genuine 2025 Wednesday forecast with decoded initialization/valid times and retained archive-object clocks. Forty 2025 official event tee sheets were cached. This resolved archive existence and group access before the completed directional screen below; a historical FanDuel decision clock remains unverified. G10's variance comparison is a separate screen.

**Initial source checkpoint:** The [September 14 source probes](../../reports/golf-source-check-2026-09-14.json) returned HTTP 200 from current GFS Single Runs and Previous Runs, including wind speed and gusts. These were schema checks at approximate Asheville coordinates, without validated venue coordinates or joined group tee clocks. They did not recover an operational 2024–25 Wednesday information set or measure a wave effect.

**Completed execution:** The [directional screen](../../reports/golf-wave-screen-2026-09-14.md) finds **+0.2586 strokes** for the forecast-windier wave, below the fixed +0.3 requirement, across **25 events /49 rounds /5,929 player-rounds**. The sample gate passes. The 5,000-draw event-bootstrap interval is **−0.0042 to +0.5071 strokes**, so this does not establish that the effect is zero. It fails the declared point-effect screen.

The [declaration](../../reports/golf-wave-declaration-2026-09-14.md) used all nonzero forecast differences with no G10 volatility filter, five-hour exposure weighted by all scheduled players, and equal event weights. Four prepared wave rounds lacked a resolved venue. Calibrated numerical stroke magnitude, forecast revisions and FanDuel response remain distinct, untested claims. Do not lower the gate, select larger wind gaps or replace forecasts/years to rescue this inspected screen.
