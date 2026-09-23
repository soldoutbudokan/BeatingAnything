# Edge search, September 23: seven more routes, one thin lead

The early-payout scanner is parked at the owner's request (routine `trig_01UHusCXLyAry36A9XDudAoU` disabled; every firing had stopped at the missing BettingPros key). This round looked for a different edge. None clears the bar; one golf lead is worth a live price check.

| Route | Data | Result |
| --- | --- | --- |
| Pinnacle early-to-close drift | football-data mirror, 80,362 matches × 3 outcomes, 2012–2025 | Early prices sit about 3% below the closing fair price in every segment, which is just the margin. No predictable drift. Favourite–longshot bias is clear (1.0–1.5 odds −0.2% ROI, 8.0+ odds −14% to −19%) but never positive. |
| Big underdogs against the spread | nflverse 1999–2025, college consensus 2006–2025, ESPN NBA 2013–2025 | Cover rates run 46–58% by spread size, the extremes in the smallest buckets; no bucket holds in both eras. Closing spreads are efficient. |
| MLB run line, home vs away favourite | ArnavSaraogi archive, 55,038 book-games, opening lines 2021–2025 | The walk-off effect exists (home dog +1.5 covers 57.0% vs 56.1% implied) but books price it; every side loses 2.5–6% after vig. |
| Soft-book college moneylines vs Pinnacle | cfbfastR multi-book lines 2006–2019 | Predicted +6% to +20% EV, realized −5% to −17%. The captured prices are not simultaneous across books, so the file cannot test this. |
| Soccer finishing luck (goals minus xG) | Understat xG, 18,195 top-five-league matches, Pinnacle close | No effect: residual vs Pinnacle's close is ±1 point with no trend by quintile (t ≈ 1). |
| MLB home-plate umpire vs opening total | Retrosheet game logs 2021–2025 joined to opening totals (6,620 test games) | Walk-forward umpire effect does not predict runs over the opener (t = 0.54). |
| **Golf birdie over/under** | alpha-caddie `odds.csv` (exchange-style prices, no vig), 863 distinct lines 2023–2025, results from 97,609 PGA rounds | **Unders hit 54.0% against 50.0% implied, +8.1% ROI at the posted price (SE 3.4%), every year 53.5–55.8%.** |

## The golf lead

Birdie counts per round are low and skewed (tour mean 3.75, median 4). The venue priced nearly every line close to even money wherever the line sat. When the line was within half a birdie of the player's trailing 40-round average or above it, the under won 52–59% (+5% to +17% ROI by bucket); when the line sat well below the average, it lost 5.6%. That points to a pricing rule that ignores where the line sits, not to one lucky season.

Limits: 719–863 lines is a small sample (t ≈ 2.4). The source is a third party's file with instrument IDs and no vig, most likely an exchange such as Sporttrade or Novig, neither available in Ontario. Whether FanDuel or bet365 post round birdie props, and at what prices, is unknown. The next step is a live check: if an available book prices birdie unders near even money at lines at or above a player's average, the same rule applies.

Exploratory only; no committed script.
