# NFL historical forecast availability — September 26, 2026

**Historical operational wind forecasts are accessible through IEM.** Three bounded requests recovered GFS MOS runs covering NFL fixtures in September 2025, November 2025 and January 2026. This replaces the earlier broad statement that forecast-archive access was blocked. It does not establish a wind betting edge or reopen the failed long-kick screen.

The [Iowa Environmental Mesonet archive](https://mesonet.agron.iastate.edu/mos/) provides operational Model Output Statistics, with separate model initialization (`runtime`) and forecast-valid (`ftime`) fields. Its [documented bulk endpoint](https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py?help) accepts station, model and run ranges. Wind speed `wsp` is in knots, not mph; temperature is Fahrenheit. These are predictions from past runs, not realized game weather or a retrospective reanalysis.

Selection used the earliest home Philadelphia fixture in each of September, November and January in the retained fixture-only projection. The station was KPHL, an airport proxy. For each existing entry time, select the latest six-hour model run initialized at least eight hours earlier. No football result was used to choose the three examples.

| Fixture | Model initialization UTC | Existing quote entry UTC | Initialization lead | Forecasts around game: wind knots |
| --- | --- | --- | ---: | --- |
| DAL–PHI, September 4 local | September 3, 12:00 | September 4, 01:55 | 13.93 h | 9, 6 |
| DET–PHI, November 16 local | November 15, 12:00 | November 16, 01:55 | 13.93 h | 19, 17 |
| WAS–PHI, January 4 local | January 3, 12:00 | January 3, 21:55 | 9.93 h | 11, 7 |

All three returned 21 forecast rows. The [JSON record](nfl-mos-availability-2026-09-26.json) preserves exact URLs, forecast fields, fixture boundaries and raw body hashes. The first curl request did not retain original request/receipt times; those clocks were not fabricated afterward. Two subsequent responses have acquisition receipts. The files remain local under `data/raw/nfl-mos-source-2026-09-26/`.

**Initialization is not dissemination.** The [NWS glossary](https://forecast.weather.gov/glossary.php?word=model+output+statistics) describes approximately four hours between 00/12 UTC initialization and public alphanumeric guidance. An eight-hour buffer is a conservative working assumption, not per-run evidence of original delivery. The API does not supply a contemporaneous bookmaker-facing receipt clock. A future test must preserve this limitation or recover original issuance evidence.

The quote times here come from the earlier moneyline metadata audit; no total or prop entry was selected. A future price test must independently select actual paired totals before outcomes, map venues to representative stations, handle roof/neutral-site games, and define calibration and evaluation periods. Stadium exposure can differ substantially from airport wind. No model, outcomes, new wind threshold, ROI, schedule, alert or wager was evaluated in this source check.
