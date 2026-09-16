# G12 — Weather restart and remaining-hole exposure

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / pre-restart round matchups / FanDuel; original addition, live-policy parked.

**Structural fact:** After suspension, players have different numbers and sequences of holes left; the same remaining weather is not equal exposure.

**Predicted behavior (measurable):** Remaining-hole weather exposure changes pairwise expected final-round score by >=0.3 strokes beyond a single round-wide wave adjustment.

**Why FanDuel's price ignores it:** Unverified: restart quotes reuse a tee-time or round-wide weather offset after the playing schedule changes.

**Trigger (observable, timestamped):** Official suspension/restart notice, each player’s completed holes and next hole, and a forecast already available before the restart quote.

**Sport-side test: data source, cost, kill criterion:** First retain raw schedules/state only. If later authorized for live exploration, declare >=20 suspended rounds with exact hole state, then compare weather-by-remaining-hole difficulty against a round-wide offset. Kill below 0.3 strokes; reconstructed finish order without clock times cannot test this.

**Book-side test: what odds at trigger time, forward or historical:** Only after sport-side effect and a separate live protocol. Compare pre-restart executable prices, suspensions and quote clocks. A lead caused by stale display or retrospective weather fails.

**Status:** idea (parked)

**Result:** Not tested in this declaration. All criteria are exploratory triage, not evidence of executable prices. Unknown inputs or inadequate samples leave the card unresolved. See [rules and source corrections](../golf-rules-and-sources.md).
