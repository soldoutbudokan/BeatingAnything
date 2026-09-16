# G8 — Public shot publication versus derivative update

**Declared:** September 14, 2026, before this batch’s sport-side comparisons.

**Sport / market / book:** Golf / live matchups and hole markets / FanDuel; outside current policy.

**Structural fact:** A shot can become known before an aggregate score updates; public and bookmaker feeds can have different latency.

**Predicted behavior (measurable):** A public penalty-shot event precedes a still-executable derivative price by at least 30 seconds.

**Why FanDuel's price ignores it:** Unverified and unlikely: an odds derivative uses a slower score feed. Vendor integration may give the book earlier information.

**Trigger (observable, timestamped):** Actual public shot publication and quote timestamps, plus collector times and suspension states.

**Sport-side test: data source, cost, kill criterion:** Park until the pre-round research produces a lead. A one-minute collector cannot reliably establish a sub-minute lead; obtain event timestamps and appropriate authorized resolution. Require >=100 penalty events across five events; timing gaps/suspensions do not count as stale prices.

**Book-side test: what odds at trigger time, forward or historical:** Forward only; measure joint timestamps and market availability without executing wagers. Kill if median usable lead <30 seconds or no tradable markets at the trigger. No live protocol is authorized by this card.

**Status:** idea (parked)

**Result:** Not tested in this declaration. All criteria are exploratory triage, not evidence of executable prices. Unknown inputs or inadequate samples leave the card unresolved. See [rules and source corrections](../golf-rules-and-sources.md).
