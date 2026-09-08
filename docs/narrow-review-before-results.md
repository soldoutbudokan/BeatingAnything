# Independent review before N1 results

Recorded 2026-09-08 while the 42-file acquisition was running, before inspecting validation or holdout outputs. The reviewer identified the following points; these clarify the frozen protocol rather than add outcome-selected strategies.

- Calibration includes the early market logit as a feature in addition to the offset: `logit(p) = logit(m) + b0 + b1 * z(logit(m))`. Thus the effective slope can be recalibrated. Consensus and goal structure add their registered discrepancy features. The old MLB calibration-only model was intercept-only; N1 is explicitly different. Training-only standardization applies to every feature.
- The primary closing benchmark is market average, with Bet365 closing as robustness. The average can include the entry bookmaker and changes composition over time; it is neither independent sport evidence nor an executable book.
- The entry-valid universe and predictions never depend on closing availability. Missing closing data must remain visible in turnover and outcome evaluation and block favorable evidence when selected-bet closing coverage is incomplete.
- The protocol's 'no contradictory negative Bet365-closing replication' means the selected bets' 2025/26 mean Bet365 closing EV must be nonnegative, with complete coverage. It does not mean merely failing to reject a negative number. The evaluator reports this cross-period condition separately from individual period components.
- Poisson inversion bounds, initialization, tolerance and fit failures are fixed before testing. Unfittable early distributions are excluded from all candidates on the same feature-valid universe; no result or close enters that decision.
- Six lower divisions were specified before any outcome testing to address sample accumulation. League breakdowns remain descriptive; no best-league selection is permitted.
- Eight-model correction is finite. New hypotheses require a separately recorded untouched evaluation; repeated research cannot manufacture an untouched holdout.
- No historical Bet365 model can be promoted as FanDuel evidence. A new entry-book feature and verified FanDuel quote process require their own frozen prospective cohort.

The reviewer found no inherent outcome leakage in the design. Snapshot synchronization, quote availability and transfer to FanDuel remain unresolved historical limitations.
