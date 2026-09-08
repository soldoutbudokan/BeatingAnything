# Research log

## Experiment 1 — MLB moneyline physical availability

The market was chosen for actual FanDuel historical coverage before comparing any strategy returns. Data selection and model policy are recorded in protocol.md. Only two learned candidates were evaluated: calibration-only and physical-feature correction. Four regularization values per candidate were selected on 2023 only.

The first historical feature reconstruction used MLB fullSeason roster hydration to enumerate pitching logs. It yielded 104,328 appearances and omitted some pitchers entirely in some seasons. First holdout physical-model log loss was 0.67712684 against 0.67721041 for FanDuel; interval crossed zero and no bets cleared 3% EV. The complete preliminary output is retained in reports/initial-source-results.json.

An independent coverage audit found missing starters, including Framber Valdez. The source enumeration was repaired using MLB's complete season pitching index and missing-player game logs. This is a source correctness repair, applied to all affected records independent of outcomes. Feature formulas, candidate set, selection year, test years and EV threshold remain unchanged. Final results are in reports/metrics.json; the preliminary result is not used to choose a strategy.

No terminal archive price entered either run. No threshold was lowered after seeing zero bets. No claim of executable historical profit or historical CLV is made.

## Forward observations

SportsbookReview's public response naturally omitted FanDuel in this environment. A separate public Covers moneyline table exposes explicit paired FanDuel prices without location overrides or account access. The forward collector records those as aggregator observations. An observation timestamp is not evidence that a bookmaker would accept a wager at that price.

The frozen historical model can be monitored prospectively using new lagged MLB inputs and contemporaneous quoted market probabilities. All-event log loss uses the earliest valid pregame forecast per event/model; bet selection keeps the fixed 3% EV policy. Aggregator observations remain separate from execution-verified evidence, and actual betting alerts remain disabled.

An initial integration run at 20:56 UTC recorded 15 forecasts with the preliminary-source artifact c3fefccfc56032ef while the corrected fit was finishing. Those system-check rows are retained in their own model cohort and are not the final model. Final corrected model a7ceefe2db3c13ea is archived with its coefficients and hash in the ledger and reports. No cohort is pooled across model versions.

## Next new research, not evaluated here

The current model does not capture today's lineup changes or starter news. A stronger next hypothesis would estimate batter-vs-pitch-arsenal run value from pitch-level data, simulate the inning distribution of fresh relievers, and update on confirmed lineups and starter changes. That requires historical publication timestamps or a new forward cohort. No result from that unbuilt model is implied. The now-observed 2024–2025 outcomes cannot be reused as untouched evidence for it.
