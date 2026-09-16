# G4 — Cut threshold and wave-dependent cut mass

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / pre-tournament make/miss cut / FanDuel.

**Structural fact:** The field’s score distribution and tournament-specific cut rule determine who qualifies; integer ties produce mass at the threshold.

**Predicted behavior (measurable):** Wave conditions explain >=20% of cut-line variation within comparable event/rule groups.

**Why FanDuel's price ignores it:** Unverified: a cut derivative uses average weather or the wrong rule when conditions or tournament format change.

**Trigger (observable, timestamped):** Official event rule, field and Wednesday as-issued forecast. Friday in-play observations are descriptive only under current policy.

**Sport-side test: data source, cost, kill criterion:** Use official cut outcomes, scoring and tee times for >=20 comparable events. Label event-specific rules and all no-cut/team/Stableford formats before comparisons. Compare actual threshold with field-adjusted baseline plus wave exposure; kill below 20% explained variation. Threshold movement alone does not establish player-specific price error; sparse rare-rule events remain unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Compare FanDuel make/miss probabilities to a joint field model with ties and the verified rule. Require both sides and <=8% two-way overround. Record DNS/WD handling; eliminate no-cut events.

**Status:** idea

**Result:** Untested. The [planned-rule source map](../golf-cut-rule-source.md) covers the fixed 40-event weather cohort: 25 ordinary top-65-and-ties candidates, three hosted Signature exceptions, eight no-cut events, three sourced major rules and one unresolved Masters rule. Twenty-two ordinary-rule events also have two scheduled waves in both rounds and a resolved venue, before weather/outcome attrition. This is an upper bound, not a passed sample gate.

The [applied-cut audit](../../reports/golf-applied-cut-audit-2026-09-14.md) now reconciles 22 official thresholds with complete cached 36-hole scores; 20 also meet the existing wave/venue prerequisites. World Wide Technology's published gross/relative cutoff conflicts, while Myrtle Beach and Bank of Utah lack source labels. Exact cut-approval and some WD/DQ timings remain unknown. Twenty is still an upper bound before complete weather and final model eligibility.

The shared operational forecast acquisition is complete. G4 still needs a declared prior-only wind-to-scoring conversion and baseline/validation design; G1's completed directional screen failed and does not supply a calibrated stroke shift. That result does not automatically decide the distinct cut-line mechanism. No cut-line variance estimate or FanDuel make-cut comparison was performed, so G4 remains untested; the current batch does not justify building a larger weather model for it.
