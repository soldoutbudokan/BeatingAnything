# Edge search, September 22: NFL 6-point teasers clear break-even out of sample

**Result.** One structural edge holds up on data it was not built from: 6-point NFL teaser legs that cross both 3 and 7, in games with a closing total of 49 or less. From 2015 to 2025 those legs won **77.2% of 613** (block-bootstrap 95% CI 73.5–80.7%). DraftKings' reported fixed prices need 73.9% per leg for a 2-team -120 teaser and 72.7% for a 3-team +160. The rule was fixed from 1999–2014 data before the 2015–2025 period was scored. The edge exists only at books that sell teasers at fixed prices. At FanDuel's reported 2-team price of up to -134 (break-even 75.7%) it is close to nothing.

Four other routes were tested this session and did not produce a usable edge; they are summarized at the end.

## The mechanism

- **Structural fact.** NFL final margins cluster on 3 and 7. Moving a line from +1.5/+2.5 to +7.5/+8.5, or from -7.5/-8.5 to -1.5/-2.5, captures both key numbers. Six points bought anywhere else captures far less probability.
- **Why the price ignores it.** A fixed-price teaser charges every leg the same, whatever the six points are worth for that leg. Legs outside the Wong window won 69.2% from 2015 to 2025, well below break-even. The book prices the average leg; the bettor picks the best ones.
- **Why totals matter.** Lower totals mean fewer points and a tighter margin spread, so six points covers more of the distribution. The training period showed this clearly (73.9% at totals ≤ 49 against 63.6% above), so the filter was carried into the test.
- **Trigger.** The posted spread and total, known days before kickoff. No speed or live data is needed.

## Method

Data: nflverse `games.csv` at commit `62997a7`, closing spread, closing total and final score for 7,300+ games, 1999–2026. Every game gives two legs, one per side. A leg wins if the team's margin plus its line plus 6 is positive. Whole-number teased lines can push; the 2015–2025 test had none.

1. **Wong window, published 2001:** team line from -8.5 to -7.5 or from +1.5 to +2.5.
2. **Filter choice on 1999–2014 only:**

   | Wong legs, 1999–2014 | Legs | Win rate |
   | --- | ---: | ---: |
   | All | 644 | 73.0% |
   | Total ≤ 49 | 589 | 73.9% |
   | Total > 49 | 55 | 63.6% |
   | Underdogs | 409 | 73.1% |
   | Favorites | 235 | 72.8% |

   The total filter separates in training; underdog versus favorite does not. The selected rule is **Wong window and total ≤ 49**.
3. **Test on 2015–2025**, untouched by that choice. 2015 is also when the extra-point distance changed, which altered the margin distribution.

## Results, 2015–2025

| Legs | Count | Win rate | 95% CI |
| --- | ---: | ---: | --- |
| **Selected rule (Wong, total ≤ 49)** | **613** | **77.2%** | 73.8–80.5% |
| Wong, any total | 747 | 76.2% | 73.1–79.2% |
| Wong underdogs only (diagnostic) | 491 | 77.6% | 73.9–81.3% |
| Wong favorites only (diagnostic) | 256 | 73.4% | 68.0–78.9% |
| All other legs | 5,230 | 69.2% | 67.9–70.4% |

The Wong window alone, over the full post-publication period 2001–2025, won 75.0% of 1,298 legs.

**By season (selected rule):** 2015 77.8%, 2016 86.5%, 2017 74.6%, 2018 72.9%, 2019 76.5%, 2020 81.6%, 2021 87.0%, 2022 70.7%, 2023 76.7%, 2024 75.0%, 2025 74.7%. Nine of eleven seasons clear the -120 break-even. The first two weeks of 2026 went 4 of 10.

**Break-even and expected value at the 77.2% test rate:**

| Teaser price | Per-leg break-even | EV per teaser |
| --- | ---: | ---: |
| 2-team -110 (no longer common) | 72.4% | +13.7% |
| 2-team -120 (DraftKings, reported) | 73.9% | +9.2% |
| 2-team -134 (FanDuel, reported upper end) | 75.7% | +4.0% |
| 3-team +160 (DraftKings, reported) | 72.7% | +19.4% |

**Realized record**, grouping qualifying legs in kickoff order within each week (leftover legs unbet):

| Price | Teasers | Won | Units | ROI | Max drawdown | Losing seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2-team -120 | 254 | 149 | +19.2 | +7.6% | 8.0 u | 4 of 11 |
| 2-team -134 | 254 | 149 | +6.2 | +2.4% | 9.6 u | 5 of 11 |
| 3-team +160 | 132 | 69 | +47.4 | +35.9% | 6.0 u | 1 of 11 |

The 3-team record ran above its +19% expectation; the leg rate, not the record, is the estimate to plan on. A season-week block bootstrap puts the chance that the true leg rate is below the -120 break-even at **3.5%**, and below the +160 3-team break-even at **1.0%**.

## How to use it

1. Midweek, list every leg with a line of +1.5 to +2.5 or -7.5 to -8.5 in a game totaling 49 or less. Expect 50–80 legs a season, a handful a week.
2. Tease them 6 points in 2- or 3-team teasers at a book with fixed teaser prices. Check the price in the app before each bet: DraftKings was reported at -120 (2-team) and +160 (3-team) in 2025. The break-even table above shows what any other price is worth.
3. Skip teasers priced at -130 or worse, including FanDuel's reported range: their break-even (75.2% and up) sits inside the confidence interval. Books that price teasers dynamically from alternate lines remove the mechanism.
4. Bet the line you get, not the closing line. The backtest uses closing lines; a leg that moves off +2.5 to +3 no longer crosses 3.
5. Stake small. At the lower end of the confidence interval (73.5%) the 2-team teaser at -120 loses about 1%. One to two percent of bankroll per teaser stays below quarter-Kelly at the point estimate.

Expected yield is modest: about 30–40 two-team teasers a season at +9%, or about 20 three-teamers at +19%, roughly 3–4 units a season. Books can reprice teasers or limit accounts that only bet Wong legs.

**Week 3 candidates at the data pull** (nflverse lines; confirm the live number): CLE +2.5 vs CAR (total 42.5), IND +2.5 vs HOU (43.5), SF -8.5 vs ARI (47.5), TB +1.5 vs MIN (42.5), DEN +2.5 vs LA (45.5).

## Other routes tested this session

The consensus-model and star-absence numbers come from `tools/explore_nba_props_edges.py`. The line-gap, alternate-ladder and NFL-prop checks were quick exploratory passes and are not in a committed script.

**NBA player-points props, cross-book consensus.** A public archive holds main and alternate points lines from 11 US books about 12 hours before tip for 3,378 games (January 2024–April 2026), with box scores. Books that post a line one point off consensus also move the price; their no-vig probabilities stay calibrated, and betting the favorable side of a one-point gap returned -10.2% to +4.0% by book (-7.7% at FanDuel). A consensus model with an Under-bias correction, fitted only on earlier seasons and bet once per player at the best-priced US book, returned -0.1% (5,668 bets, EV > 2%), +1.3% (2,338, EV > 4%), +5.2% (972, EV > 6%) and -0.2% (397, EV > 8%). Returns do not rise with predicted edge, 86–94% of picks are Unders, and the fitted Under bias fell from 0.37 to 0.13 points between fits. Not an edge.

**NBA alternate-points ladders.** No blanket mispricing; long-shot rungs lose 38–54% at FanDuel. Rungs that a consensus-distribution model flagged as positive EV lost 4.0% over 8,113 bets.

**NBA teammates of an absent star.** When a 20+ point scorer sits for the first time, teammates' morning Overs hit 57.3% against 49.9% implied (548 player-games). The absence is mostly unknown when the line is captured: of 174 star absences with an official injury report issued at least an hour before the snapshot, only 58 were listed Out. Using only that pre-snapshot status, teammate Overs hit 57.9% against 49.8% implied, +8.7% ROI, but over only 56 team-games (clustered SE 5.3%, t ≈ 1.65). The ex-post effect fell from +22% (2023–24) to +10% (2024–25) to +0.2% (2025–26), which suggests books now adjust before the morning line. Unconfirmed and fading; worth a prospective check only if a 2025–26 injury-report source appears.

**FanDuel NFL receptions and passing-yard props, 2023–25** (8,195 settled props, quoted about 90 minutes before kickoff). Average vig is about 6%. Unders returned -2.5% and Overs -9.7% on receptions. The no-vig prices are close to calibrated; there is no blanket side to take.

## Reproduce

```bash
python tools/explore_nfl_teasers.py        # seconds; writes reports/nfl-teasers-2026-09-22.json
python tools/explore_nba_props_edges.py    # ~5 min; clones the prop archive, fetches ~920 injury PDFs; writes reports/nba-props-edges-2026-09-22.json
```

The NBA script needs `pdfplumber`. Raw data stay under the ignored `data/raw/`.

Teaser price sources (web search summaries; the pages themselves were blocked here, so verify in the app): [OddsShopper on Wong teasers](https://www.oddsshopper.com/articles/betting-101/wong-teaser-strategy), [BettingUSA teaser guide](https://www.bettingusa.com/sports/teaser/), [Action Network teaser price comparison](https://www.actionnetwork.com/education/which-sportsbooks-have-the-best-nfl-teaser-prices), [Covers teaser strategy](https://www.covers.com/nfl/teaser-strategy), [Sports Handle on dynamic teaser pricing](https://sportshandle.com/sportsbooks-dynamic-pricing-teaser-bets/), [DraftKings teaser help](https://support.draftkings.com/dk/en-ca/what-is-a-teaser?id=kb_article_view&sysparm_article=KB0010765).
