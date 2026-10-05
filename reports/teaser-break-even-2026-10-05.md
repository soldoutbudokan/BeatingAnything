# Wong teaser break-even prices, October 5, 2026

**If Wong legs win 73.5% of the time, the low end of the backtest interval, a 2-team teaser breaks even at −118 and a 3-team at +152.** At the 77.2% point estimate those limits loosen to −147 and +118. Any price better than the break-even is +EV at that win rate.

The break-even decimal price is **1 / p^k**, where p is the per-leg win rate and k is the number of legs.

## Break-even price by per-leg win rate

| Per-leg win rate | Basis | 2-team break-even | 3-team break-even |
| ---: | --- | ---: | ---: |
| 73.5% | Low end of 2015–2025 bootstrap interval | −118 | +152 |
| 73.85% | 1999–2014 training rate | −120 | +148 |
| 75.0% | Rule of thumb | −129 | +137 |
| **77.2%** | **2015–2025 point estimate** | **−147** | **+118** |
| 80.7% | High end of 2015–2025 bootstrap interval | −187 | −111 |

Win rates come from the [September 22 teaser backtest](edge-search-2026-09-22.md): six-point legs crossing both 3 and 7 in games with a closing total of 49 or less, 613 decided legs. The rule was fixed on 1999–2014 data before 2015–2025 was scored.

## Win rate each quoted price requires

| Ticket | Price | Where quoted | Required per-leg win rate |
| --- | ---: | --- | ---: |
| 2-team | −110 | Pinnacle published table | 72.4% |
| 2-team | −120 | Old DraftKings assumption | 73.9% |
| 2-team | −130 | BetMGM, secondary sources | 75.2% |
| 2-team | −135 | DraftKings public support table | 75.8% |
| 3-team | +180 | Standard chart | 71.0% |
| 3-team | +160 | Old DraftKings assumption | 72.7% |
| 3-team | +140 | DraftKings public support table | 74.7% |

## Limits

- **Independence.** The formula assumes every leg wins independently at the same rate. Correlated or uneven legs change the answer.
- **Pushes.** The formula ignores them. The original cohort had 2 pushes in 615 legs, so the effect is small. Rules differ by book: DraftKings refunds a two-leg ticket on a push if no leg loses and drops larger tickets by one leg; FanDuel Ontario voids a two-team ticket; Pinnacle voids a teaser left with one selection.
- **Prices are not betslips.** None of the prices above is a captured Ontario ticket. See the [price check](teaser-price-check-2026-09-26.md) and the [capture attempt](teaser-current-capture-attempt-2026-09-26.md).
- **Pinnacle's base line.** Pinnacle [can move a teaser's base line](https://pinnaclesports.freshdesk.com/support/solutions/articles/1000118554-why-are-my-nfl-teaser-points-incorrect-) away from the main spread, for example listing a −7.5 favourite as −9 +110. That stops the tease from crossing 3, so a −110 price only helps on legs whose teaser line still matches the main line.
- **Planning rate.** The 2015–2025 result held out of sample, but its interval is wide. Plan on the low end: about −118 or better for two legs, +152 or better for three.
