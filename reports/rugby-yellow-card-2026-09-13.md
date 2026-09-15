# Rugby yellow-card exploration — September 13, 2026

**Sport-side confirmed:** 133 matched first-yellow-card windows across 306 published Premiership fixtures produced 122 opponent tries in 1,330 playing minutes. The rate was **0.917 tries per ten minutes versus 0.419 standardized control tries**, a **+119.2%** difference. The gate remains at least 100 matched windows and at least a 30% increase. It is a sport-side exploratory result; zero FanDuel quotes were obtained and no betting edge is confirmed.

| Season | Published fixtures | Eligible matches | Matched card windows | Opponent tries / 10 min | Standardized control tries / 10 min | Relative change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024-25 | 93 | 83 | 44 | 0.750 | 0.524 | +43.2% |
| 2023-24 | 93 | 87 | 37 | 1.054 | 0.422 | +149.5% |
| 2022-23 | 120 | 103 | 52 | 0.962 | 0.327 | +194.1% |

## What ran

The card was written before outcome inspection. The official URC stats landing request returned HTTP 403, which was respected. PREM’s own public frontend explicitly references the InCrowd rugby-union match feed. An ordinary unauthenticated request recovered complete fixtures and match-event responses; no API key, account, header impersonation or blocked-source workaround was used. The fixed fallback was 2024–25. Its 93-game ceiling was known before the conditional result, so 2023–24 was added before either season’s effect was seen. After seeing the 44-window positive 2024–25 pilot, one final 2022–23 coverage extension was declared if the first two seasons had fewer than 100 matches; they had 81. The fixed stop was all three seasons regardless of result. The 2022–23 source retains seven played Worcester/Wasps fixtures; those games remain in the published-list sample instead of being removed to reproduce a later league table. The pooled result is exploration, not an untouched confirmation sample.

The trigger is the first isolated yellow card, with at least ten regulation minutes left in that half. Red-card matches and a penalty try at the card’s exact clock time are excluded. The exposed outcome is every opponent try in the next ten playing minutes, including any further cards. Tries at the trigger’s exact timestamp are not counted. Every accepted event stream reconstructed the published final scores. Across the three seasons, 32 red-card matches and one score-mismatch match were excluded; match 271699 reconstructs Bath 10–London Irish 23 from events against a 10–25 scoreboard and was not repaired. There were 134 qualifying first-card windows, of which 133 had matching controls. The parser uses half plus minute/second, so first-half overrun and the second-half clock reset do not create negative time. The feed’s terminal `Post Game / End` marker was normalized after the initial schema pass excluded every match; no valid conditional comparison existed at that point.

Controls are ten-minute aligned windows free of an active or newly occurring yellow. A late first-half yellow also removes the first ten minutes of second-half control exposure. Exposed windows match controls from other matches in the same season, team, ten-minute start bin and score band (more than seven behind, within seven, more than seven ahead). Each exposure receives its stratum’s control mean; the combined estimate averages these within-season comparisons. Later cards in an exposed window remain counted.

## What the result does and does not show

The conditional scoring difference is large enough to investigate an actual live price. A yellow card often follows sustained pressure near the try line. Field position and possession are absent from this small event feed, so the difference cannot be attributed solely to the missing defender. Clock bins are coarse; exposed windows begin at the actual card second while control windows start on ten-minute boundaries. Entire red-card matches were excluded using later information. These choices make this an exploratory screening sample, not a deployable betting rule.

The fixed ten-minute denominator measures an outcome window after a published trigger; it is not a claim that the teams remained exactly 15 versus 14 throughout. Return-to-field delays and later cards can change the actual headcount. An actual next-try market also needs the other team’s competing scoring rate and the no-further-try outcome; an opponent try-rate increase alone is insufficient to price it.

There were 19 additional yellow-card events inside the matched exposed windows. No confidence interval or causal inference is being claimed from the exploratory point estimates. The individual reports preserve every matched exposure and source response hash. An independent review reconstructed all 133 exposure clocks, margins and outcomes without discrepancies and checked the control-matching logic; the mismatched-score exclusion was confirmed from the raw feed.

## Calendar and next concrete step

Both candidate northern-hemisphere competitions have a full season ahead. [Irish Rugby’s official URC calendar](https://www.irishrugby.ie/2026/05/19/bkt-urc-fixtures-released-for-2026-27-season) starts September 25, 2026 and ends June 19, 2027. [PREM’s official announcement](https://www.premiershiprugby.com/content/gallagher-prem-2026-27-start-and-final-dates-confirmed) starts September 25–27, 2026 and ends June 19, 2027. [World Rugby law 9.29](https://passport.world.rugby/laws-of-the-game/laws-by-number/9-foul-play/) specifies ten-minute yellow cards; law 9.30 separately distinguishes permanent red cards from qualifying twenty-minute replacement reds. Do not transfer this estimate to rugby league or a red-card market.

Next, verify whether FanDuel actually offers a live next-try-team or team-try-total market for PREM/URC and whether it remains open following a card. Obtain paired quotes, market rules, suspension state, exact trigger timing and a matched settlement reference. General rugby coverage or a rulebook mention does not establish a specific league’s live derivative availability. Do not expand this historical sample again merely because the conditional effect is positive.

The [subsequent price-source check](../docs/rugby-market-access-2026-09-13.md) found general FanDuel rugby rules but no verified live quote route for these markets and competitions. It records the provider's coverage gap so the next run can move to a new permitted source or another hypothesis.

## Reproduce

Run the existing script for each fixed season. Without `--download`, it uses cached public inputs. Raw match data and site assets remain ignored; only derived rows and hashes are published.

```sh
python tools/explore_rugby_yellow_cards.py --download --season 202401
python tools/explore_rugby_yellow_cards.py --download --season 202301
python tools/explore_rugby_yellow_cards.py --download --season 202201
python tools/explore_rugby_yellow_cards.py --summary
```

The feed entry point is [the published PREM match list](https://rugby-union-feeds.incrowdsports.com/v1/matches?provider=rugbyviz&season=202401&compId=1011&sort=date&form=true&images=false), referenced by [PREM’s fixture page](https://www.premiershiprugby.com/fixtures-results/). Each match uses `/v1/matches/{id}?provider=rugbyviz`. Reports retain exact SHA256 values; fresh responses may differ because the publisher refreshes metadata or corrects events.
