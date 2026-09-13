# 40. NBA points: FanDuel main/alternate payoff coverage

**Sport / market / book:** NBA full-game player-points main and alternate half-point lines / FanDuel.

**Structural fact:** Separately produced main and alternate ladders can contain incompatible payouts for overlapping Over and Under legs on the same player.

**Trigger and prediction:** Over at L plus Under at H, L <= H, covers every integer scoring result. After a 2% haircut to each leg's net winnings, inverse-payout stake weights imply a minimum return of at least 1% on total stake.

**Fixed test:** Same original snapshot, both update clocks aged 0–300 seconds, exact person/fixture matching, decimal odds 1.20–6.00 and unambiguous literal market outcomes. Reuse card 39's independently verified two-season source cohort, but make no cross-book probability assumption. See the immutable [declaration](../nba-points-payoff-coverage-declaration-2026-09-13.md).

**Book-side gate:** At least one source pair clears the +1% minimum payoff requirement; actual simultaneous fills and equal settlement would still need independent verification. No sport-side model or outcome selection is involved.

**Status:** Book-side source screen failed at fixed settings.

**Result:** Across 2,446 independently matched games, 40,166 eligible covering offer pairs produced zero +1% candidates. The best minimum theoretical return was −4.49% after the fixed haircut. No outcomes were loaded and no thresholds changed. See the [executed report](../../reports/nba-points-payoff-coverage-2026-09-13.md). This specification is closed; no executable arbitrage or betting edge is claimed.
