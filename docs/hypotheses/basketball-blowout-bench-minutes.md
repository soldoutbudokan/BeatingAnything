# Blowout bench minutes

**Sport / market / book:** Basketball / live bench-player points and starter unders / FanDuel.

**Structural fact:** Coaches can replace starters late in a lopsided game, changing remaining minutes abruptly.

**Predicted behavior (measurable):** Bench players receive more remaining minutes when the margin first reaches >=25 with 6–10 minutes left in quarter four than at margins <=10.

**Why FanDuel's price ignores it:** Unverified hypothesis: live props extrapolate earlier rotation minutes before discretionary substitutions are priced.

**Trigger (observable, timestamped):** First qualifying dead ball in the clock/margin window; actual current lineup is part of the observed state.

**Sport-side test: data source, cost, kill criterion:** Official NBA play-by-play/substitutions via nba_api; free, <=1 hour. Compare remaining bench minutes by player role and clock, including zero-minute cases. Kill if >=200 eligible player-games show <3 additional bench minutes; inconsistent lineup reconstruction unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Forward live props with accrued stats and all on-court IDs before/after the dead ball; check whether bench markets are offered at all.

**Status:** idea

**Result:** Not tested. A margin trigger is probabilistic; it does not guarantee substitution.
