# NFL absolute forecast wind — September 26, 2026

**The fixed >10-mph model produces no qualifying bets.** Only 10 of the 20 high-wind calibration games went Under. The fitted market correction is about 0.04 percentage points, leaving every later offered side with negative modeled EV after costs. This specification is closed; no edge is established. Later outcomes were not read by this experiment.

## Fixed test and result

The [declaration](../docs/hypotheses/football-absolute-forecast-wind.md) and [runner](../tools/explore_nfl_absolute_wind.py) were committed in `041cb21` before fitting. This tests the earlier absolute high-wind lead, separately from the completed wind-revision correction. It retains a strict forecast speed above 10 mph rather than searching for a favorable threshold or copying the earlier observed-weather Under percentage into new forecasts.

The existing operational-weather preparation supplies one genuine paired FanDuel half-point total per game, 12–24 hours before the conservative start boundary, at an independently mapped outdoor home venue. Forecast wind is the latest eligible GFS MOS run's integrated kickoff-to-kickoff+3h mean, with an eight-hour initialization buffer. The source and input hashes were verified; all 175 entries have complete weather. No realized wind, later line or future result determines entry.

With market Under probability `q` and `h=1[forecast mph>10]`, the model is `sigmoid(logit(q)+beta*h)`, constrained to beta≥0 with the unchanged `0.5*beta²` penalty. Weeks 1–8 fit the coefficient; all week 9–18 forecasts were then frozen before additional labels. Unexposed probabilities remain exactly q. The betting rule requires ≥3% EV after a 2% haircut to winning profits, with one flat unit maximum per game.

| Measure | Result |
| --- | ---: |
| Early calibration games | 76 |
| Early high-wind games that identify beta | 20, across 6 weeks |
| High-wind early Unders | 10 /20 |
| Fitted beta | 0.00154206 |
| Later entries / high-wind entries | 99 /42 |
| Later forecasts unchanged from q | 57 |
| Mean increase in high-wind Under probability | 0.03854 percentage points |
| Best later modeled EV after costs | −5.313% |
| Later qualifying bets | 0 |
| Later scoring losses / ROI | Unscored / undefined |

The early high-wind market log loss is 0.698471940; model loss is 0.698471524, an immaterial in-sample improvement. All 76 early games have scores, but the 56 unexposed games contribute no information about beta. Neither the coefficient nor these fit statistics count as validation.

The [forecast freeze](nfl-absolute-wind-freeze-2026-09-26.json) was recorded at `2026-09-26T21:19:28.328659+00:00` and committed in `a0fd736`. Latest early-label availability is October 30, 2025 at 00:00 UTC, before the earliest later entry at 01:55:39 UTC. The zero-selection disposition was declared beforehand. Because no bet qualifies, later outcomes are left ungraded; unlike the exact-zero revision model, the 42 changed forecasts could have nonzero scoring differences, and no claim is made about their unmeasured accuracy.

The [independent fit audit](nfl-absolute-wind-fit-audit-2026-09-26.json) reproduces beta by standard-library bisection, verifies all 52 frozen hashes and all 198 later side EVs, and confirms that no later graded artifact exists. The objective's positive Hessian confirms a unique optimum. Synthetic boundary and chronology checks passed, and all 312 repository tests pass. See the [machine-readable result](nfl-absolute-wind-2026-09-26.json). Raw forecasts and freeze are preserved under `data/raw/nfl-absolute-wind-2026-09-26/`. The runner refuses to overwrite these outputs. Do not run its grade phase to choose a replacement threshold or model.

## Separate-season price check

A bounded check of the original [NFL Market Tracker releases](https://github.com/bobby-king3/nfl-market-movement-tracker/releases) found no separate 2024 or 2026 season. The latest release remains v1.1.1, whose asset hash matches the retained database. Both the [pinned current extractor](https://github.com/bobby-king3/nfl-market-movement-tracker/blob/2024c859ac7dd999e19ad7d2b3c340f5db4b1724/extract/historical_extract.py) and first-release extractor specify September 4, 2025 through February 9, 2026. January–February 2026 rows are part of the 2025 NFL season and cannot serve as a separate season.

Five successful public metadata/code requests retrieved 33,352 bytes; no database was downloaded again and no outcome was read. Bodies, hashes, URLs and receipts are in `data/raw/nfl-price-validation-source-check-2026-09-26/check-summary.json`, hashed in the result. This source check does not imply that all possible validation sources are unavailable, and the negative fitted model does not justify acquiring more data to rescue it.

## Limits and disposition

This is another exploratory comparison within an already inspected weather family. Twenty informative calibration games have weak precision; a negligible fit cannot prove that wind is always perfectly priced. Airport/stadium exposure differences, assumed MOS delivery timing, book-wide update clocks, unknown original receipt and absent accepted fills remain limitations. The forecast inputs are reusable, but this exact model is finished. No threshold, penalty or sign change follows the result. Schedules, alerts and wagers remain inactive.
