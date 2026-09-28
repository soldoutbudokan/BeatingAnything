# NHL shot-to-goal model: frozen result

Status: **fixed_model_closed_no_demonstrated_edge**.

All forecasts and selections were frozen before this target-label join. Gains below are market loss minus model loss; positive favors the model.

| Period | Forecasts / games | Log-loss gain (95% game interval) | Settled bets W–L | Haircut ROI (95% game interval) |
|---|---:|---:|---:|---:|
| all | 2107 / 239 | -0.002760 (-0.006413, 0.000942) | 161: 63–98 | -0.31% (-23.40%, 23.59%) |
| early_nov_dec | 1158 / 132 | -0.001000 (-0.005570, 0.003490) | 92: 33–59 | -8.57% (-37.52%, 21.87%) |
| later_january | 949 / 107 | -0.004931 (-0.010875, 0.000759) | 69: 30–39 | 10.72% (-24.43%, 48.84%) |

The declared exploratory gates fail; this exact model is closed without retuning.

The JSON retains Brier scores, raw and haircut returns, unknown/void counts and settlement bounds, drawdowns, player concentration, week counts and every gate. Loss intervals give equal weight to games; return resampling includes games with no selections.

This short archive was inspected by previous studies. The intervals do not correct repeated model searches or dependence across shared players and weeks. Historical quote clocks and assumed participation rules do not verify accepted execution or jurisdiction-specific terms. No wager, alert or schedule was enabled.

Frozen model: [declaration](../docs/nhl-shot-to-goal-declaration-2026-09-26.md). Full results: [JSON](nhl-shot-goal-results-2026-09-26.json).
