# Rugby price-market check — September 13, 2026

The [yellow-card screen](../reports/rugby-yellow-card-2026-09-13.md) passed its exploratory sport-side gate. **No matching FanDuel live quote has been obtained.** A scoring effect does not establish a betting edge.

| Checked primary source | Finding | Consequence |
| --- | --- | --- |
| [FanDuel Colorado house rules](https://www.fanduel.com/fanduel-sportsbook-house-rules-co), effective July 22, 2026 | Rugby union and several try-related settlement rules are documented. The phrase “next try” also appears in position-scorer settlement examples. | This does not verify a live next-try-team or team-try-total offer for PREM/URC. Colorado rules do not establish another jurisdiction's rules. |
| [The Odds API sports catalog](https://the-odds-api.com/sports-odds-data/sports-apis.html) | Union coverage lists Six Nations; PREM and URC are not listed. Rugby-league NRL/NRLW coverage is separate. | No documented sport key for the actual screened competition. Do not pass a guessed league key to the collector. |
| [The Odds API market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html) | Try-scorer props are described for NRL and selected Australian books. | These are neither union coverage nor verified FanDuel live next-try-team quotes. An API key alone does not close this gap. |

The existing provider collector remains useful for supported markets. No rugby collector was added for an unverified endpoint, and the already denied direct FanDuel route was not retried. These checks establish a concrete coverage gap, not proof that the market is unavailable everywhere.

The next price observation needs the competition, fixture, exact market and outcome labels, all offered prices including any no-further-try outcome, settlement rules, source/update/receipt clocks and open/suspended state around the card. Team-try totals require the line and accrued tries. Player and position try markets must not be substituted for team outcomes.

The historical ten-minute opponent try rate cannot directly price a next-try market: the opponent's competing hazard and remaining match time also matter. The current screen excludes entire red-card games using future information, so it is not a deployable trigger. Any prospective rule must be declared using only information available at the card before independent validation. Keep this requirement separate from the completed descriptive screen.

Continue other accessible mechanisms while this exact price source is unresolved. Do not spend recurring runs rechecking the same catalogs, expanding the positive historical sample or claiming FanDuel lag from league rules alone.
