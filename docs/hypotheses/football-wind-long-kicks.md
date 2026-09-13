# Wind and long-kick props

**Sport / market / book:** Football / longest field goal and made-field-goal props / FanDuel.

**Structural fact:** Wind can affect both kicking accuracy and coaches' decisions to attempt long field goals.

**Predicted behavior (measurable):** Outdoor games with wind >=15 mph have fewer successful >=50-yard field goals per eligible drive than lower-wind games.

**Why FanDuel's price ignores it:** Unverified hypothesis: kicker props adjust less than the game total to weather, especially the long-distance tail.

**Trigger (observable, timestamped):** A pregame weather issue time establishes >=15 mph forecast at the venue; verify roof status and subsequent updates.

**Sport-side test: data source, cost, kill criterion:** Retained nflverse play-by-play and weather fields; free, <=1 hour. Compare long-kick attempts and makes separately per drive reaching opponent 40–25, by season/roof status. Kill if >=200 exposed eligible drives show <20% relative change; missing timely wind observations unresolved.

**Book-side test: what odds at trigger time, forward or historical:** Inventory retained NFL odds for exact kicker markets; otherwise forward paired prop odds plus issue-stamped forecast. Postgame wind does not prove prequote availability.

**Status:** idea — broad retrospective screen failed/deprioritized; timely forecast variant unresolved.

**Result, September 13:** Fixed 2021–2025 nflverse data gave 785 exposed eligible drives in 95 games, versus 6,249 low-wind drives in 732 games. Successful >=50-yard kicks were 49/785 (6.24%) versus a season/roof-standardized 5.46% baseline: a **−14.4% relative reduction**, opposite prediction, with descriptive game-cluster 95% interval [−54.1%, +19.3%]. Attempts declined only 4.6%. This fails the prewritten 200-drive/20%-reduction screen; do not tune thresholds or reverse the bet. Wind is missing for 152/979 outdoor/open-roof games (all 32 open-roof games are missing), and recorded game wind has no forecast issue timestamp. The issue-stamped trigger therefore remains unresolved. All-distance makes are only a secondary diagnostic (+2.8%, not a replacement gate). No FanDuel quotes or edge evidence; the current provider catalog documents made-FG/kicking-points markets but no longest-FG key. [Report](../../reports/nfl-wind-kicks-2026-09-13.md), [runnable script](../../tools/explore_nfl_wind_kicks.py).
