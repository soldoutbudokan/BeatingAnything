# Card 42: conditional FanDuel price test against BetMGM

Declared September 19, 2026, after the 2024 settlement screen and source-only reference coverage counts, before computing converted probabilities or this strategy's selections/returns. Card 41's two failed candidates remain unchanged. Both 2024–25 price periods were already inspected; this is exploratory, with no untouched-holdout claim.

## Evidence and scope of inference

The [BetMGM Massachusetts rulebook revised November 27, 2024](https://massgaming.com/wp-content/uploads/BetMGM-House-Rules-11.21.24.pdf), page 25, identifies its basketball player-first-statistic product as first field goal. BetMGM's [January 7, 2025 announcement](https://sports.betmgm.com/en/blog/betmgm-expands-second-chance-offer-ice-courts/) explicitly describes its NBA first-field-goal market and a Friday second-scorer cash-refund promotion. Both documents are retained with hashes under `data/raw/nba-first-score-wedge-2026-09-19/rules/`.

These contemporaneous primary sources support a **conditional research interpretation** of the archive's `betmgm` first-basket quotes as first-field-goal prices. They do not restore each original quote's displayed label or jurisdiction. Card 42's exact market-identity prerequisite remains unmet for an unconditional pricing claim. This follow-up permits a fixed conditional experiment to test whether the candidate is useful even under the supported interpretation; a positive result still requires original market-identity evidence and additional/prospective validation. No silent bookmaker-to-definition alias is introduced. DraftKings and BetRivers are not substituted based on the outcome.

Use only NBA Stats-labelled **regular-season games, excluding all Fridays** by the fixture's New York local date. This excludes the stated recurring refund day and avoids playoff promotion regimes. It does not prove that every remaining quote was unaffected by other offers. No BetMGM wager or promotional refund is simulated; FanDuel remains the sole target.

## One fixed conversion candidate

Use the entire pinned 2024 publisher roster file's recorded starts, all completed before the price cohort. For each player, sum made field goals `FG_i` and made free throws `FT_i`. Reject duplicate player/game rows and invalid negative/nonfinite counts. Missing numeric rows contribute neither numerator nor denominator and remain in attrition. The league reference `L` is pooled `FT/FG` over those valid prior starts. Use the fixed shrunk ratio:

`v_i = (FT_i + 100*L) / (FG_i + 100)`.

An unseen player gets `L`. No current-season target statistics, outcomes or eventual starters enter this calculation. The 100 pseudo-field-goals are fixed now, not fitted to returns.

Let `q_i` be BetMGM inverse-decimal prices normalized across the matched ten players. Let `h_i = q_i*v_i / sum_j(q_j*v_j)`. The prior screen's fixed winner-transfer fraction is `r = 80/1319`. Convert with:

`p_i = (1-r)*q_i + r*h_i`.

This is an approximation: it assumes the same outgoing transfer fraction across field-goal scorers and allocates incoming first-score mass by prior free-throw production relative to field-goal production. Whole-game free throws include situations unlike the opening possession. The screen does not establish either assumption, or that BetMGM probabilities are accurate. Report paired scoring against both unconverted `q` and normalized FanDuel prices to test the conversion instead of attributing all cross-book differences to free throws.

## Cohort and selection

Start from the existing immutable 473 forecast-eligible FanDuel games. Reuse only their verified identities, offered prices and prior-roster eligibility, not card 41's model probabilities or bets. The three earlier source-validation games remain excluded. Choose the earliest BetMGM snapshot with the exact normalized ten-player candidate set and event ID; require both complete boards' market updates no later than their receipts, all quotes at most 300 seconds old at their joint receipt, and joint receipt at least 60 seconds before the earlier verified fixture start. Do not backfill a reference with later quotes. Apply the regular-season/non-Friday restriction before any grading. Missing target outcomes or starters do not change eligibility.

Keep the same date split: discovery through February 28, 2025; chronological replication March 1–May 12, 2025 (actual eligibility ends with the regular season). Use fixed one-unit FanDuel bets, at most one per game, decimal odds 1.20–26.00. Only candidates with `p_i > q_i + 1e-12` qualify for this positive free-throw adjustment hypothesis. Among them choose the largest `p_i*(1 + 0.98*(decimal_i-1)) - 1`, requiring at least 5%; ties use stable player ID. No overround or player-subgroup tuning.

Freeze all probabilities, selections, input hashes and code hashes before joining independent target scores. Report the unchanged-rule sensitivity with probabilities multiplied by 0.99. Also report whether selected bets' modeled EV stays positive under unconverted `q`; this is an interpretation diagnostic, not another optimized betting strategy.

## Grading and gates

Reuse the independent ESPN first-score definition, source roster nonstarter void convention, unresolved-label treatment and one-percent unlisted-scorer scoring bucket from the first-basket price protocol. Every original selected stake, including voids, remains in ROI denominators. Unknown settlements retain unresolved-as-loss and unresolved-as-void sensitivity scenarios, not favorable deletion. These scenarios are not a complete range of possible results.

Report both periods and pooled results; wins/losses/voids/unresolved; ROI; log loss and Brier score against both baselines. Use 10,000 calendar-week block draws, seed 1729, with no inferential interval below eight weeks. Add this single candidate to the previous 15-comparison family: corrected two-sided confidence is `1 - 0.05/16 = 99.6875%`. Preserve old results under their original allowances.

A conditional exploratory lead requires positive ROI in both periods even with unresolved bets treated as losses, at least 50 settled nonvoid bets in each, and improved pooled log loss against **both** baselines. A conditional historical advantage also requires positive corrected replication ROI lower bound and negative corrected replication paired-loss upper bounds against both baselines. A conditional success is insufficient for an edge claim while exact quote definitions, additional validation and the standing prospective evidence gates remain missing. No wagers, alerts or schedules are enabled.
