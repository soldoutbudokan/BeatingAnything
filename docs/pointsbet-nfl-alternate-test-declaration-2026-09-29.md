# PointsBet Ontario NFL alternate-line source and price test — September 29, 2026 UTC

Requested September 28 Toronto time. Base repo commit: 06debd7279de4f3d200af273e4b7287de4d652c8.

## Question and scope

Do actual PointsBet Ontario NFL alternate spreads, totals, or player thresholds show a robust positive reference-implied expected return? Separate each market family. Australian and former US PointsBet quotes cannot stand in for Ontario. This is a new exploratory source/price study, not an untouched outcome backtest.

## Declaration before alternate-price comparisons

The source search found mykolafc/betsmart at 55d1ae445add653a0a462fc4de0b889ec8698c59: a raw Buffalo–Miami event payload, an NFL listing, and multi-book derived CSVs. Main-line examples and schema/counts have been inspected; alternate-line relative prices and returns have not been computed. The raw event has a 2024-09-13 start. The CSVs concern 2024-09-30 onward. Historical provenance and applicability to current prices remain separate questions.

1. Inventory exact sport/book, fixture, market family, line, side, player identity, event/market/selection flags, and all original clocks. Keep game metadata timestamp, price-change timestamp, Git commit time, and collector receipt distinct. An old price-change time does not alone prove a stale displayed price; an absent capture clock cannot certify freshness.
2. Strict cross-book test: same fixture/start, full-game settlement-compatible half-point lines, exact player identity where relevant, actual two-sided reference, paired overround 0–12%, decimal odds 1.20–6.00, captured pregame, book/market observations no older than 90 seconds and cross-book observation gap at most 90 seconds. Missing original timing or ambiguous identity excludes certified comparisons. Do not infer that snapshots in one Git commit were simultaneous.
3. Reference: Pinnacle first; if unavailable use a separately reported three-book median, excluding PointsBet. De-vig each reference pair with proportional and power methods. Require reference-implied EV >=3% under both after a 2% haircut to net winnings. This is a discrepancy score, not demonstrated true EV.
4. Derived CSVs lacking source clocks may support a separately labeled arithmetic diagnostic using the same half-point/paired-price/arithmetic rules. Do not promote those rows to the strict cohort. Do not use a publisher's precomputed fair-odds, join key, or arb-ROI column as ground truth; reconstruct joins and pairs.
5. Within-book structural checks: identical-contract differing-price offers, monotonicity across nested half-point outcomes, and opposite-side payoff coverage. More favorable spreads or lower Over thresholds at at least the same price dominate harder contracts, but do not by themselves prove positive EV. Opposite sides at the same half-point line are exhaustive/disjoint. For integer lines, retain in inventory but exclude this first EV test to avoid treating pushes as losses.
6. Key-number diagnostic: when a raw simultaneous spread ladder supplies opposing pairs at both half-point lines, calculate the change in de-vigged cover probability across 3 and 7. Do not transplant the repo's old pooled 8.93%/5.89% into every matchup or force a normal distribution to price the tails.
7. Report every eligible comparison, exclusions, highest and lowest scores, and independent fixture count. Numerous nested alternate lines from the same game are correlated. No outcome grading, ROI backtest, threshold tuning, schedule, alert or wager.
8. If strict data are insufficient, report the source failure and conditional diagnostic separately. Preserve reproducible parsing and a concrete capture path; a lack of eligible data does not reject the hypothesis.
