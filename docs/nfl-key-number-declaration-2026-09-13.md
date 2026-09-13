# NFL half-point lines across key margins

Registry ID 37. Written September 13, 2026 before this rule's price differences or returns were computed.

**Sport / market / book:** NFL full-game half-point spread, FanDuel; same-snapshot Pinnacle reference.

**Structural fact:** Final scoring margins are discrete. Crossing a field-goal or touchdown margin can add substantial win probability; a continuous point-value approximation misses that mass.

**Predicted behavior:** When FanDuel offers a one-point better spread crossing exactly three or seven than Pinnacle, some quotes have positive expected return after accounting for the historical frequency of that exact margin.

**Why FanDuel's price ignores it:** Unverified mechanism: its main line can sit on the favorable side of a key margin while another book has moved, without enough payout adjustment. Book disagreement, calibration mismatch and archive artifacts are alternatives. This is distinct from the completed identical-line screen and is not a generic strength regression.

**Fixed calibration:** NFL 2010–2024 completed regular-season games only. Separately for keys three and seven, count the closing favorite winning by exactly the key among games with absolute recorded spread within one point of that key, inclusive. Use the empirical proportion and its 95% Wilson interval. Require >=200 historical calibration games per key. The schedule's spread is a historical closing-market proxy, not verified Pinnacle odds; transporting that margin mass to the reference quote is an explicit modeling assumption.

**Trigger and entry:** Use the pinned 2025-season NFL archive. Retain the existing strict two-sided, 0–90-second freshness and 0–8% overround parser; entry is 1–24 hours before the earlier of the independently mapped scheduled kickoff and conservative source start. Both books must name the same fixture and quote half-point spreads. For the selected team, FanDuel's spread is exactly one point higher, and the midpoint of the two spreads has absolute value three or seven. Require FanDuel decimal odds 1.20–6.00. Add the corresponding prior key-margin mass to each of proportional and power de-vigged Pinnacle probabilities. Reject probabilities outside [0,1]. Require >=3% excess return after a 2% haircut to net winnings under both methods, and positive excess under both methods using the Wilson lower mass. Keep the first qualifying snapshot per fixture; take the highest conservative score at that time, alphabetical team on ties. No threshold changes after results.

**Backtest:** Freeze calibration and selected rows before loading 2025 outcome fields. Settle against final score including overtime; half-point lines cannot push. One unit per selected game, 2% net-winnings haircut, no actual bets. Report all selected rows, missing settlements, wins/losses, profit, ROI, drawdown and a 5,000-resample game bootstrap (seed 20260913). An advancing exploratory result needs >=50 settled games, positive ROI and a bootstrap lower bound above zero. Below 50 is unresolved even if profitable. Report near-start Pinnacle comparisons separately with the same declared calibration; do not call them verified closing-line value.

**Limits and stopping:** This archive and its season were inspected for other questions, so this is a newly specified exploratory backtest, not an untouched holdout or confirmation. Quote freshness does not prove a fill or historical settlement equivalence. Stop after this fixed rule; do not tune line gaps, key choices, entry windows, calibration range or threshold. Any lead still needs independent/forward FanDuel evidence under the unchanged project gates.

**Status:** idea

**Sources:** [Pinned odds release](https://github.com/bobby-king3/nfl-market-movement-tracker/releases/tag/v1.1.1); [nflverse schedule dictionary](https://github.com/nflverse/nflreadr/blob/main/data-raw/dictionary_schedules.csv). Calibration/results use a separately pinned `nflverse/nfldata` games file. Raw third-party files remain ignored.
