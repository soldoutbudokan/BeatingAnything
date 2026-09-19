# G11 — Multi-course rotation and first-round derivatives

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / multi-course event pre-round cross-course 2-balls and round-score props / FanDuel; original addition.

**Structural fact:** Players rotate through different courses at some events; tournament ability can be comparable while a given round’s course difficulty differs.

**Predicted behavior (measurable):** Course assignment produces >=0.5 strokes of ability-adjusted first-round score difference at the same event.

**Why FanDuel's price ignores it:** Unverified: a round derivative inherits a tournament mean without the assigned-course offset.

**Trigger (observable, timestamped):** Official course rotation and tee times before the first round; record scoring convention (gross strokes versus relative to par).

**Sport-side test: data source, cost, kill criterion:** Before comparison name the accessible multi-course events in 2023–25 and official course IDs. Require >=200 players and six event editions; estimate within-edition course contrasts after prior-round ability grouping. Kill below 0.5 strokes; no course ID means unresolved. Different pars must be normalized consistently; event-average scores are insufficient.

**Book-side test: what odds at trigger time, forward or historical:** Acquire actual FanDuel cross-course round lines and both sides, including the displayed score convention. Kill if implied mean shifts reflect >=70% of the measured course difference or no such markets are offered.

**Status:** sport-side effect survives; book-side untested

**Price checkpoint (September 19):** [Biltmore's first nonempty capture](../../reports/golf-price-capture-2026-09-19.md) supplied 12 complete FanDuel-linked two-player markets, including ten displayed round-three pairs. Every round pair is same-course and already started. This establishes a working source but supplies zero cross-course pre-round observations for G11; the declared book-side test remains unperformed.

**Result (September 14, 2026):** The [pre-score declaration](../../reports/golf-rotation-declaration-2026-09-14.md) fixed eight 2023–25 editions, official course IDs and signed harder-minus-easier contrasts. The [screen](../../reports/golf-rotation-screen-2026-09-14.md) finds **+1.709 strokes relative to par**, event-bootstrap 95% interval [+1.111, +2.192], across 950 paired player-events, 311 unique players and eight editions. This passes the +0.5-stroke / 200-player / six-edition sport gates. Farmers South-minus-North is +2.315 to +2.509 across the three editions; Pebble 2024 reverses sign and remains included. RSM Seaside-minus-Plantation is positive relative to par but negative in gross strokes because the pars differ by two. The pooled contrast is not a universal market adjustment. Six unmatched ESPN names, two incomplete R1 scores, 72 inadequate histories and 13 unpaired-bin rows are explicitly excluded; no fuzzy aliases or post-hoc replacement events. The effect is observational and the eight editions span only three recurring tournaments. **No FanDuel cross-course prices were tested, so no betting edge is established.** Next is the declared book-side test using actual offers and their displayed score convention. See [rules and source corrections](../golf-rules-and-sources.md).
