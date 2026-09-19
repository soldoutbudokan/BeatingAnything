# Golf: rules, source coverage and corrections

Checked September 14, 2026 (America/Toronto). This note corrects assumptions in [GOLF-MODEL-PLAN.md](../GOLF-MODEL-PLAN.md); the [12-card queue](hypotheses/GOLF-QUEUE.md) is exploratory. No paid subscription, wager or alert was enabled.

**September 19 version checkpoint:** the [Ontario page](https://www.fanduel.com/fanduel-sportsbook-house-rules-on) header now reports July 30, 2026. A follow-up retrieval of its golf section returned 403 and stopped. The June 2 archived terms referenced below must not be silently treated as the current version for a new quote. This check neither proves the golf clauses changed nor verifies the captured prices' jurisdiction. Preserve the earlier dated findings; acquire the applicable market terms before grading. See the [source record](../reports/golf-next-price-opportunity-2026-09-19.json).

## Decisions that change the implementation

- Use market-specific settlement states. The plan’s three-hole requirement and generic more-holes-wins tournament rule are incorrect for the Ontario rules checked below.
- A 2-ball probability conditional on no push is useful for displaying fair odds; its EV is not return per original stake without a non-push multiplier.
- Previous Runs values for different valid hours do not constitute one Wednesday forecast. A named run also needs evidence of when its output became available.
- Top-100 status already governed the **2025** Fall for the 2026 season. Do not use 2025 as a top-125 historical control.
- Data Golf’s cited pricing study analyzes **2019–2020**. It motivates research; it does not establish a current FanDuel error or reveal its pricing algorithm.

## FanDuel: jurisdiction and market rules

Ontario is a relevant rules reference because the workspace uses Toronto time. Timezone does **not** establish the user’s residence, account, physical location or applicable betting jurisdiction. Every future quote must identify its actual jurisdiction and market terms. Public rules access does not establish sportsbook-price access.

The [Ontario house rules](https://www.fanduel.com/fanduel-sportsbook-house-rules-on), also included in FanDuel’s [June 2, 2026 Ontario terms](https://d38ayms4az88sz.cloudfront.net/SB/ON/2026-06-02T12-05-39.html), establish these distinctions:

| Section | Verified rule |
| --- | --- |
| 19.1 | One stroke establishes participation. Tournament settlement generally requires 36 holes and an official result; already-decided markets can stand. |
| 19.3 | No-start by any group member voids the 2/3-ball. Three-ball ties use dead heat; two-ball ties push when no tie selection exists. If all fail to finish, the market voids. Rearrangements retain original groups. |
| 19.7 | Tournament matchups use placing. Both miss cut: lower score wins. WD/DQ before cut loses; a player withdrawing after making cut beats an opponent who missed it. Ties refund. |
| 19.5 / 19.9 | Standard top-X uses dead heat. Make-cut settlement depends on cut-stage completion and official result. |
| 19.23 / 19.24 | Top-X OddsBoosts/Specials can include ties without ordinary dead-heat reduction. |

**Unresolved cases:** the text is not an exhaustive algorithm for simultaneous withdrawals, ambiguous signed scores, or every shortened event. Do not invent an outcome for an unspecified case. Snapshot the actual rules/offer and leave unresolved settlements unknown. These rules do not justify bypassing price-page access restrictions.

## Return calculations: distinguish stakes and conditioning

These are payout identities, not a fitted golf model. Let `d` be decimal odds, with one unit originally staked.

**Two-ball with a push.** Let `W`, `L`, and `R` be mutually exclusive win, loss and full-refund probabilities, summing to one. Then

```text
EV per original stake = (d - 1) W - L = d W + R - 1
q = W / (W + L)                     # only if W + L > 0
EV per decided stake = d q - 1
EV per original stake = (W + L) (d q - 1)
```

For example, `W=.46`, `L=.44`, `R=.10`, `d=2` produces 2.0% original-stake EV and 2.22% decided-stake EV. Apply any 3% admission threshold to its registered stake basis; a conditional value must not silently replace original-stake return. Refunds can include ties and valid voids but must follow the actual rule.

**Three-ball dead heat.** Conditional on a valid market, define

```text
p_eff(i) = P(i alone lowest)
         + P(i tied for low with exactly one other) / 2
         + P(all three tied) / 3
EV conditional on a valid market = d p_eff(i) - 1
```

The three effective probabilities sum to one when all non-void states are covered. With full-refund probability `V`, original-stake EV is `(1-V)*(d*p_eff(i)-1)` if `p_eff` is conditional on non-void. Equivalently use unconditional payout mass: `d*p_eff_unconditional(i) + V - 1`.

**Why ties alone do not prove G3.** Compare `p_eff(i)` with `q_i = P(i alone lowest) / P(any unique winner)`, not with raw strict-win probability. The raw strict-win probabilities fail to sum to one. For three exchangeable players, symmetry gives both `q_i` and `p_eff(i)` equal to one third, however frequent ties are. Thus a high overall tie rate can coexist with zero allocation error. Actual unequal-player corrections and the book’s quoted residual must both be measured.

**Withdrawal risk.** Enumerate disjoint outcomes covering participation, completion, cut and ties. Adding an opponent-withdrawal probability to an existing win probability can double-count wins; a generic holes-completed function can settle against the rule. Withdrawals also affect conditioning and available-market selection.

**Means from main-market odds.** Outrights alone do not identify each player’s scoring mean without assumptions about variance, dependence, field, cut, withdrawal and vig. Matchups can identify differences only within connected comparison groups after a distribution is specified; an absolute score level needs an anchor. Recovered means are model-dependent inputs, not revealed FanDuel skill estimates. A residual may reflect a bad inversion rather than a book error.

## Current PGA TOUR runway

The official [2026 schedule](https://www.pgatour.com/schedule/2026) and individual event pages list these competition dates. Some search-indexed schedule labels lag later announcements.

| Dates, 2026 | Event | Primary confirmation |
| --- | --- | --- |
| September 17–20 | Biltmore Championship Asheville | [Schedule](https://www.pgatour.com/schedule/2026) |
| October 1–4 | Bank of Utah Championship | [Event](https://www.pgatour.com/tournaments/2026/bank-of-utah-championship/R2026554/past-results) |
| October 8–11 | Baycurrent Classic | [Schedule](https://www.pgatour.com/schedule/2026) |
| October 22–25 | Butterfield Bermuda Championship | [Event](https://www.pgatour.com/tournaments/2026/butterfield-bermuda-championship/R2026528/overview) |
| October 29–November 1 | VidantaWorld Mexico Open | [Event](https://www.pgatour.com/tournaments/2026/vidantaworld-mexico-open/R2026540/past-results) |
| November 5–8 | World Wide Technology Championship | [Event](https://www.pgatour.com/tournaments/2026/world-wide-technology-championship/R2026457/overview) |
| November 12–15 | Austin event, previously Good Good Championship | [August 27 PGA TOUR statement](https://beta.pgatour.com/article/news/latest/2026/08/27/good-good-golf-statement-press-release-2026) |
| November 19–22 | The RSM Classic | [Event](https://www.pgatour.com/tournaments/2026/the-rsm-classic/R2026493/past-results) |

The August 27 statement says Good Good withdrew sponsorship while the Austin dates remain scheduled. The statement was accessible in the search index; a direct page open returned 403. Do not interpret the old sponsor label as current. The September 24–27 Presidents Cup is team match play, outside the individual stroke-play screen. Schedule dates do not prove any FanDuel derivative will be offered, and eight events do not guarantee 1,000 eligible independent bets.

The TOUR’s [Fall explainer](https://www.pgatour.com/article/news/how-it-works/fedexcup-fall-playoffs-standings-how-it-works-51-70-125) explicitly describes top 100 and conditional 101–125 for the **2026 season from 2025 results**. Its URL still contains “125”; the URL is not the rule. The [2026 FedExCup overview](https://beta.pgatour.com/fedexcup/overview) states that eight fall tournaments finalize top 100 for the following season. G6 must additionally identify exemptions; rank near 100 alone does not mean a player risks losing status. The [Signature Events page](https://www.pgatour.com/signature-events) confirms the three player-hosted events’ top-50-and-ties plus within-ten rule. Other formats need their own event rule, not one universal cut assumption.

## Data Golf: what a subscription would and would not buy

The current [subscription page](https://datagolf.com/subscribe) lists Scratch Basic at $20/month or $190/year, Scratch Plus at $30/month or $270/year. It explicitly excludes historical archive endpoints from Plus monthly: **Plus annual is required for archives**. These are the site’s displayed dollar amounts; Canadian checkout currency, tax and final charge were not verified. No checkout or purchase was performed.

The [API documentation](https://datagolf.com/api-access) lists round scoring/stats/tee times across 22 tours, historical opening/closing odds, and `fanduel` as an accepted bookmaker for matchups and outright/finish markets. It describes matchup history as 12 books while its option list contains more legacy names; a fixed “11 books since 2019” is not a reliable coverage specification. The [terms](https://datagolf.com/terms-and-conditions) restrict use to personal non-commercial purposes and prohibit redistribution. Paid data should remain local and ignored.

Ordinary public HTML from the [coverage page](https://datagolf.com/api-historical-coverage) contains its table data in `reload_data`. The page’s last update is **August 21, 2023**. Its FanDuel PGA row lists matchup start **2020-10-06** and outright start **2019-01-23**, then active with no end. This is evidence of listed historical starts, not a current completeness warranty.

The public [matchup archive index](https://datagolf.com/matchup-odds-archive), updated **2026-09-14T08:04:18Z**, advertises FanDuel in 270 PGA event rows (2020–2026), 201 European rows and five “alt” rows. PGA counts by year: 8, 45, 46, 42, 47, 46, 36. Its earliest PGA row is the event ending October 11, 2020; newest is August 30, 2026. Those are index entries, not downloaded wagers. They establish advertised event/book coverage; they do **not** establish per-round 3-ball coverage, original group identifiers, current Ontario prices or executable timestamps.

The archive’s explicitly [free Pinnacle 2021 Masters sample](https://feeds.datagolf.com/historical-odds/matchups-sample?odds_format=decimal&file_format=json) returned 190 records with `bet_type`, player IDs, open/close prices, `open_time`, `close_time`, tie-rule text and outcomes. Times are plain minute strings without explicit offsets in the sample. It is Pinnacle, not FanDuel; it verifies schema only. Confirm timezones, sampling cadence, missing rows and jurisdiction before using the paid archive as trigger-time evidence.

Data Golf’s [December 18, 2020 study](https://datagolf.com/how-sharp-are-bookmakers) explicitly analyzes 2019–2020. “Opening” and “closing” mean first/last scraping attempts, not official book endpoints. Its favorable 3-ball result and model/market blend are selected historical analyses, not evidence of a 2026 FanDuel settlement mistake. The author also discusses selection in reported results. A purchase could shorten historical exploration, but cannot guarantee all G1–G5 tests or replace forward evidence.

## Open-Meteo: forecast clocks and coverage

[Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) aligns forecasts at fixed offsets from each **valid hour**: day1 is 24 hours earlier, day2 48 hours earlier, through day7. Consequently Thursday 08:00 and Friday 16:00 values at day1 originate from different available-information times. Combining them does not reconstruct one Wednesday decision. Most models start in January 2024, with exceptions and shorter histories. The page explicitly directs a complete named-run workflow to Single Runs. A bounded [GFS Previous Runs query](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=35.5&longitude=-82.6&start_date=2026-09-10&end_date=2026-09-10&hourly=wind_speed_10m_previous_day1,wind_gusts_10m_previous_day1,wind_direction_10m_previous_day1,precipitation_previous_day1&models=gfs_seamless&timezone=UTC) returned all 24 non-null hourly values for day1 speed, gusts, direction and precipitation near Asheville on September 10, 2026. This verifies these variables for one model/day/lead only; it does not establish historical coverage or a Wednesday information set.

[Single Runs](https://open-meteo.com/en/docs/single-runs-api) uses `run=YYYY-MM-DDTHH:MM` for UTC **initialization**, not public availability. Documentation gives typical delays of 4–6 hours for global models and 1–3 hours for regional models. Most model archives begin April 2, 2026. Earlier ECMWF coverage beginning March 14, 2024 is labeled Cycle 49R1 **hindcasts**; do not present those as the operational forecast actually public in 2024. Document model/cycle, forecast valid hours and actual availability, using [model update schedules](https://open-meteo.com/en/docs/model-updates) only as an availability estimate. Retained forward responses with capture clocks are strongest evidence for what this collector could see.

The [free API terms](https://open-meteo.com/en/terms) require non-commercial use and attribution, with stated rate limits; data licensing and hosted-service permission are separate. The [pricing page](https://open-meteo.com/en/pricing) permits free evaluation/prototyping and lists historical/Previous/Single Runs on Professional rather than Standard paid access. No broad future commercial-use entitlement or user betting-account status is inferred. This research should retain attribution and revisit service terms before any different use.

## Requirements answered versus still open

| Requirement | Finding |
| --- | --- |
| Current golf settlement | Ontario rules verified with material corrections; actual quote jurisdiction and edge cases still required. |
| PGA 2026 Fall dates/status era | Verified; Austin sponsor label corrected; exemption-aware G6 exposures still need inputs. |
| Data Golf annual product/FanDuel presence | Verified advertised coverage and sample schema; no paid FanDuel rows inspected. |
| Historical open/close definition | First/last scrape per publisher’s historical methodology; current timezone/cadence and execution remain unverified. |
| One Wednesday weather information set | Previous Runs alone does not answer it; Single Runs needs real availability and operational-vs-hindcast verification. |
| PGA odds partner and offered derivatives | A commercial partnership is insufficient; collector must read the response’s bookmaker identity. |
| FanDuel overround, update lag and quote execution | Not established by public rules, archive catalogs or mathematical payout identities. |
| Historical rounds and group coverage | Answer through the batch’s retained acquisition and sport-side report; neither the prior cloud denial nor an API wrapper proves present coverage. |

Public pages were read through web search/direct opens and ordinary `curl -L`; denials were retained as denials. No challenge or location restriction was bypassed. Source access varies by host and path, so the original blanket “every host is blocked” statement is obsolete once reachable responses are actually observed.
