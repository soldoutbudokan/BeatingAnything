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

## F1 — newly recovered timestamped FanDuel observations

On September 8, a separate source audit located The Odds Gap's public seven-day research CSV. Before scoring, protocol d00e288 and clarification a4a897b were pushed on the research branch. The unchanged 2025-trained physical artifact was tested on 100 reconciled September 2026 events; 85 outcomes were graded from the frozen official snapshot. There were zero qualifying bets. On 97 common forecasts / 82 common settled outcomes, physical-model log loss was 0.68386684 versus 0.68263097 for FanDuel. The synchronized Pinnacle pricing control also produced zero qualifying bets. The complete negative pilot is preserved in reports/timestamped-mlb-research-report.md.

Independent official first-pitch timestamps tighten timing checks; they do not establish bookmaker execution. The publisher export lacks bookmaker-update timestamps and covers too few calendar weeks for confidence intervals. No threshold, feature, candidate or source period was adjusted to create a bet. These newly inspected outcomes are now research knowledge and cannot become untouched evidence for another revised model.

## N2/N3 implementation and source collection

The current worktree was first updated from remote commits documenting the failed N1 soccer experiment and frozen N2/N3 tennis specifications. Those existing hypotheses remain intact. Implemented components now preserve a predetermined Challenger sample, literal paired opening histories, delayed score/Elo/workload inputs, annual fitting with label-availability checks, and missing-outcome/closing coverage. Actual tennis evaluation is deferred until all required daily pages and selected details have been attempted and their raw-source provenance checked.

The additional F1 evaluations expand the conservative family allowance from eleven to thirteen before any tennis results are inspected. This does not license indefinite testing on the same holdout. Formal numerical checks use Python 3.12.13 with the original locked dependencies; a Python 3.14/pandas 2.2.3 source-build crash was an environment failure, not a model result.
