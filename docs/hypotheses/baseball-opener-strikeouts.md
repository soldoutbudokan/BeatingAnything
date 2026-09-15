# Opener workload

**Sport / market / book:** Baseball / listed starter strikeout under and first-five team totals / FanDuel.

**Structural fact:** A listed starter can be an opener with a deliberately short outing, followed by a bulk pitcher.

**Predicted behavior (measurable):** Announced openers face substantially fewer batters than ordinary starters, reducing available strikeouts.

**Why FanDuel's price ignores it:** Unverified hypothesis: a derivative price or available strikeout ladder temporarily assumes normal starter length after the opener role becomes public.

**Trigger (observable, timestamped):** Official team announcement identifies opener role and, if known, bulk pitcher before the first pitch.

**Sport-side test: data source, cost, kill criterion:** MLB StatsAPI starts/outs and archived official role announcements; free, <=1 hour. Compare batters faced and strikeouts for prospectively announced openers with ordinary starts. Kill if >=50 cases show <6 fewer batters faced or no usable published role history; sparse reliable announcements unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward strikeout line/pair and first-five totals before/after role announcement; verify pitcher identity, listed-pitcher rules and offer availability.

**Status:** idea

**Result:** Not tested. Identifying openers from eventual innings pitched would leak the outcome.
