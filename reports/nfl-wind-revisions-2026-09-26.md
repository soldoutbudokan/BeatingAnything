# NFL forecast-wind revisions — September 26, 2026

**The declared model selected no weather correction and no bets.** Calibration on 76 early-season games chose beta exactly zero. All 99 later forecasts therefore equal the paired FanDuel probabilities, so this model cannot improve on their forecasting loss for any possible outcomes. Later outcomes were not read for this experiment; ROI is undefined because no bets qualify. No edge is established.

## What was tested

The [declaration](../docs/hypotheses/football-wind-forecast-revisions.md) was committed as `177d92b` before any weather-to-result calculation. The mechanism was that NFL totals might respond incompletely to revisions in expected game-time wind. The forecast was `sigmoid(logit(market_under_probability) + beta * wind_revision_knots/5)`, with beta constrained nonnegative. There was one fitted coefficient, no intercept, and a fixed `0.5*beta²` penalty. Weeks 1–8 calibrated it; weeks 9–18 supplied later entry prices. No sign reversal, alternative penalty, station search or altered wind threshold followed the result.

Entry was the first genuine paired FanDuel half-point total 12–24 hours before the earlier independent/source start, with nonfuture book update aged at most 90 seconds and 0–8% overround. For each fixed outdoor home venue, the latest six-hour GFS MOS initialization at least eight hours before entry was compared with its run exactly 24 hours earlier. Both were integrated over the same independent kickoff-to-kickoff+3h window by piecewise-linear interpolation. Realized weather and game roof status were not used.

The [price inventory](nfl-wind-price-inventory-2026-09-26.md) supplies 11,357 paired pregame totals over 285 fixtures; its four captures a day cannot resolve responses within minutes. The [fixed venue map](nfl-wind-venue-map-2026-09-26.md) retains 175 regular-season games at 20 open-field venues, excluding 7 neutral/international and 90 covered/retractable-roof fixtures. Some international rows retain nominal home-stadium IDs; requiring `location=Home` prevented those false joins.

Twenty successful, bounded requests to the [IEM MOS archive](https://mesonet.agron.iastate.edu/mos/) recovered **220,143 forecast rows /10,483 station-runs**, preserving raw responses, receipts and SHA-256 hashes. All 175 fixed entries have both required forecast runs; zero weather rows were replaced or excluded. The new initialization precedes entry by **9.93–13.93 hours**. The older run is exactly 24 hours earlier. Forecast speeds are knots; no null or missing-code 99 winds occurred in the recovered bodies. The [NWS MOS description](https://www.weather.gov/media/mdl/mdltpb05-04.pdf) defines 99 as missing, which the implementation rejects rather than treating as extreme wind.

## Result and independent verification

| Measure | Result |
| --- | ---: |
| Calibration games, weeks 1–8 | 76, all graded |
| Later forecasts, weeks 9–18 | 99 |
| Fitted beta | 0 |
| Penalized objective derivative at beta=0 | +1.462318 |
| Calibration market/model log loss | 0.696116 /0.696116 |
| Calibration market/model Brier loss | 0.251484 /0.251484 |
| Later model probabilities exactly equal market | 99 /99 |
| Later qualifying bets | 0 |
| Best later modeled EV after winnings haircut | −5.38% |
| Later outcome losses / ROI | Unscored / undefined |

The derivative is positive at the allowed boundary, and the objective is strictly convex: its Hessian is at least 1 from the penalty. Thus zero is the unique constrained optimum, not an optimizer failure. The [independent fit audit](nfl-wind-revisions-fit-audit-2026-09-26.json) reproduced this from the early labels only. It verified all 198 later side-EV calculations and exact equality of each later probability to the market. Paired log-loss and Brier differences are consequently **exactly zero for every possible later outcome**; grading those results cannot make this specification demonstrate improvement.

Independent review also confirmed the first eligible quote for all 175 entries, reproduced all 350 wind-window means within 8.9e-16, and verified the frozen source hashes. Latest training-label availability was October 30 at 00:00 UTC, before the earliest later entry at 01:55:39 UTC. Two reporting fixes were made before any fitting: retaining zero-bet weeks in return bootstraps and separating calibration statistics. The pre-review preparation remains preserved locally; the recomputed entry CSV is byte-identical.

The fitted forecasts and source hashes were frozen at `2026-09-26T20:50:21.998117+00:00` and committed in `cf04932`. See the [freeze](nfl-wind-revisions-freeze-2026-09-26.json), [machine-readable result](nfl-wind-revisions-2026-09-26.json) and [runner](../tools/explore_nfl_wind_revisions.py). No later game-result or price-change diagnostic was needed or evaluated.

## Limits and disposition

This result rejects this exact positive-direction revision correction as a useful fitted model here. Seventy-six calibration games do not prove that no weather edge exists. The airport/stadium exposure mismatch, assumed eight-hour dissemination buffer, retrospective sporting metadata, book-wide rather than market-specific update clock, and absent accepted fills limit stronger conclusions. This archive has been used in other project research; later results not read by this experiment are not advertised as globally untouched data.

The fixed model is closed. Do not flip its coefficient, change station/entry timing, or open later outcomes to select a revised rule. The newly recovered forecasts remain useful inputs for a separately justified hypothesis. No scheduled task, alert or wager was enabled.

The acquisition and extraction commands are recorded in their source reports. The model runner's `prepare`, `forecast` and `grade` phases refuse to overwrite original outputs. A clean reproduction using the same pinned files can run `--phase prepare` then `--phase forecast`; **do not run grade merely to score identical probabilities**. The original local outputs are under `data/raw/nfl-wind-revisions-2026-09-26/`.
