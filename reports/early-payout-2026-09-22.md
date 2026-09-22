# bet365 Early Payout: a standing edge on underdog moneylines

**Result.** bet365 settles a pre-game moneyline as a win once the team leads by 17 points (NFL, college football) or 20 points (NBA), even if it later loses. Play-by-play shows how often that rescues a bet: for underdogs with a 20–30% chance to win, it adds 6–7% to their win probability in the NFL and college football and about 5% in the NBA since 2019. A bet365 underdog price can therefore sit that far below the fair price and still break even. On actual 2012–2019 college moneylines, bet365's underdog prices sat 3.0–4.5% below Pinnacle's no-vig price, which leaves an expected **+1.2% to +4.4% per bet for teams with a 10–50% win chance**. In Ontario both books are available, so the check can be run live on every game.

The promotion is a fixed rule applied to every game regardless of price. That is the same shape as the teaser edge: one rule, uneven value, and the bettor picks where the value is largest.

## How much the payout is worth

The payout adds the probability that the team reaches the lead and then fails to win. Measured from 5,295 NFL games (2006–2025, nflverse play-by-play and closing moneylines), 6,755 college games (2012–2021, cfbfastR play-by-play and consensus moneylines) and 16,728 NBA games (2012–2025, ESPN play-by-play; win probability from the pregame spread):

| Fair win prob | NFL fair → break-even at bet365 | College fair → break-even | NBA 2019–25 fair → break-even |
| --- | --- | --- | --- |
| 10–20% | +531 → **+491** (6.3% below fair) | +561 → **+513** (7.2%) | +533 → **+499** (5.4%) |
| 20–30% | +295 → **+271** (6.1%) | +299 → **+272** (6.7%) | +299 → **+279** (5.0%) |
| 30–40% | +184 → **+176** (3.0%) | +185 → **+172** (4.4%) | +183 → **+172** (3.9%) |
| 40–50% | +124 → **+119** (2.3%) | +124 → **+115** (4.0%) | +128 → **+124** (1.7%) |
| 50–60% | -125 → **-132** (2.5%) | -124 → **-135** (3.7%) | -128 → **-136** (2.5%) |
| 60–70% | -184 → **-190** (1.1%) | -185 → **-196** (2.0%) | -183 → **-195** (2.1%) |

Read it as: if Pinnacle's no-vig price says an NFL team is +295, a bet365 price of +271 or longer is break-even or better. The conversion rates have standard errors of 0.2–0.4 percentage points per row. The NBA rate has risen: 1.19% of all team-games since 2019 against 0.69% before, consistent with more comebacks in the three-point era. The NFL 10–20% row is thinner since 2016 (2.6%, 244 team-games), so treat the NFL edge as strongest from about +200 to +400.

## Evidence the lift is real and priced low enough

**NFL, at closing consensus prices.** Every underdog of +130 or longer, 2006–2025: 4,169 bets returned -2.9% as plain moneylines and +1.7% with the payout applied. The +4.6-point lift matches the table.

**College football, at bet365's actual prices.** The file holds bet365 and Pinnacle moneylines captured together for 4,883 games in 2012–2019:

| Pinnacle fair prob | Team-games | bet365 vs fair | Payout adds | Expected EV with payout |
| --- | ---: | ---: | ---: | ---: |
| 10–20% | 1,169 | -4.5% | 1.37 pts | +4.4% |
| 20–30% | 1,234 | -4.4% | 1.86 pts | +2.9% |
| 30–40% | 1,067 | -3.0% | 1.69 pts | +1.7% |
| 40–50% | 895 | -3.2% | 2.01 pts | +1.2% |
| 50–60% | 867 | -4.2% | 2.31 pts | -0.1% |
| 60–70% | 1,067 | -3.6% | 1.31 pts | -1.6% |

With the payout curve fitted on 2012–2015 only, bets on 2016–2019 where the model showed positive EV (2,005 bets, predicted +4.6%) returned -4.6% plain and **+1.3% with the payout** (standard error 4.4%). The realized lift again matches. Moneyline returns on 2,000 bets cannot confirm a 2–5% edge by themselves; the case rests on the two measured components, price shading and conversion rate.

## How to use it

1. For each NFL, college football or NBA game, take Pinnacle's two moneylines and remove the vig to get the fair win probability.
2. Find the row in the table and compare bet365's price with the break-even price. Bet when bet365 is at or above it, ideally by a point or two of EV.
3. Focus on underdogs from about +150 to +500. Favorites rarely clear it because the payout adds little to a price that is already short.
4. Check the terms in the Ontario app: pre-game moneylines only, and confirm which sports and leagues qualify there. College football and MLB were not confirmed for Ontario in the sources found.
5. Expect long losing runs. Underdog moneylines at a 2–4% edge need several hundred bets before results mean much.

## Limits

- The college bet365 prices are from 2012–2019, before the offer existed. bet365 may now shade underdog prices further to pay for it. Compare live prices with Pinnacle before relying on the historical shading.
- bet365 limits accounts that win. Expect the useful life to be finite.
- MLB (5+ runs), NHL (3+ goals) and soccer (2+ goals) were not sized. For soccer, half-time scores give only a lower bound on the payout (about 0.6% of bets). That is too small against bet365's 5–6% 1X2 shading, so soccer was left out.

## Other routes checked this round

These were exploratory passes and are not in a committed script:

- **bet365 vs Pinnacle, soccer 1X2** (football-data mirror, 84,500 matches, 2012–2025): bet365 prices above Pinnacle's fair value returned +1.2% over 14,500 bets (SE 1.65%). Adding the 2-goal payout at the half-time lower bound gave +2.6% out of sample (9,841 bets, SE 2.2%), negative since 2023. Not usable.
- **College football 6-point teasers** (14,666 games, 2006–2025): legs mostly win 60–72%; even the best underdog windows sit at or below 73.9% out of sample.
- **College opener model** (ratings from prior closing lines vs DraftKings, Bovada and 5Dimes openers): the model misses the close by 5+ points against the opener's 1.8, and where it disagrees the line moves against it (48% ATS).
- **NBA points middles across books**: one-point gaps lose 2.8%; two-point gaps break even (+0.4%, 285 cases).
- **NBA star Unders** (line 28.5+, best US price): +5.7% over 1,181 bets, falling each season to +3.9% in 2025–26; at 26.5+ it went +9.4%, +3.3%, +0.9%. Fading.
- **NBA players back from a 3–10 game absence, Unders**: seasons range from -6.7% to +9.8%. Noise.
- **NFL wind Unders**: recorded wind over 10 mph went under 54% (1999–2014) and 58% (2015–2025), but a bettor sees forecasts, and historical forecast archives were blocked here. Using each stadium's usual wind for that month from earlier seasons gives 53.1% and 56.5% (about 920 games, about 1.5 standard errors). A lead only.

## Reproduce

```bash
python tools/explore_nfl_teasers.py      # provides data/raw/nfl-teasers/games.csv
python tools/explore_early_payout.py     # downloads ~700 MB of play-by-play; writes reports/early-payout-2026-09-22.json
```

Early Payout terms: [bet365 rules by sport](https://news.bet365.com/en-us/article/bet365-early-payouts-rules-for-mlb-nfl-wnba-ncaaf-nhl-nba-ncaab-soccer-cfl/2025111918544324796), [VegasInsider summary](https://www.vegasinsider.com/sportsbooks/bet365/early-payout/), [Pikkit explainer](https://pikkit.com/blog/bet365-early-payout). These were read as search summaries; the pages were blocked here.
