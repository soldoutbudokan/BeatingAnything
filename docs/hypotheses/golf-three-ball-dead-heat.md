# G3 — Three-ball dead-heat allocation

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / pre-round 3-balls / FanDuel; local market availability remains to be verified.

**Structural fact:** Integer round scores create tied-low outcomes. Their fractional payout must be allocated to the players involved.

**Predicted behavior (measurable):** The rank-specific dead-heat effective probability differs by more than 0.01 from strict-win probability normalized across the three players.

**Why FanDuel's price ignores it:** Unverified: a derivative conversion normalizes strict wins and omits unequal tie shares. Correct settlement alone does not imply that FanDuel omits it.

**Trigger (observable, timestamped):** Published group plus all three pre-round quotes, before any member tees off; preserve original group and source/capture clocks.

**Sport-side test: data source, cost, kill criterion:** Use official completed rounds and actual group IDs; rank players by pre-event mean field-adjusted score from their previous 20 rounds (minimum 10), never final score. First screen: available 2025 individual PGA stroke-play rounds, excluding team/Stableford/starting-stroke events. Require 300 complete three-player groups across five events. For each prior-ability rank calculate strict wins, two-/three-way tied-low shares, and p_eff minus normalized strict wins. Kill if every absolute correction is <=0.01 with adequate coverage; otherwise advance only as sport-side association. Report tie rate, score spread, missing groups and event-cluster uncertainty. Synthetic groups or the free 2021 sample establish math/schema only.

**Book-side test: what odds at trigger time, forward or historical:** After the sport screen, compare signed corrections with FanDuel three-way no-vig residuals using contemporaneous main-market inputs and declared spread/correlation assumptions. No unique skill inversion is presumed. Mean absolute residual below 0.01 without a signed pattern kills the book screen. Three-way confirmation policy is not yet registered.

**Status:** sport-side dead in pooled reconstructed-group screen

**Result:** The [September 14 screen](../../reports/golf-sport-screen-2026-09-14.md) found 2,651 eligible 2025 triples across 35 events. Tied-low rate was 15.843% (381 two-way and 39 three-way ties). Dead-heat minus normalized strict-win probabilities by prior-ability best/middle/worst were −0.470, +0.397 and +0.073 percentage points: all below the declared one-point gate, so the pooled mechanism fails this screen. Groups were reconstructed from identical event/round tee time plus starting hole, excluding multi-course events and non-three-player tuples; explicit official group IDs and FanDuel offered groups were unavailable. A one-event Sony spot-check matched 138/140 complete triples to official membership/round/start-tee records; two unmatched name aliases were left unchanged. A 491-group large-gap diagnostic reached 1.417 points but is inspected exploration and cannot rescue this pooled declaration. No FanDuel price error was tested.
