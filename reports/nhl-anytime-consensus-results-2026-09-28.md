# NHL anytime-scorer normalized consensus: frozen result

Status: **fixed_screen_closed_no_demonstrated_edge**.

All rows and selections were frozen before this target-label join. Gains are FanDuel loss minus reference loss under the power normalization; positive favors the consensus.

| Period | Rows / games | Log-loss gain (95% game interval) | Settled bets W–L | Haircut ROI (95% game interval) | All qualifying rows W–L, haircut ROI |
|---|---:|---:|---:|---:|---:|
| all | 8597 / 260 | 0.000544 (-0.000637, 0.001709) | 5: 0–5 | -100.00% (-100.00%, -100.00%) | 5: 0–5, -100.00% |
| early_nov_dec | 4488 / 136 | 0.000466 (-0.001275, 0.002222) | 3: 0–3 | -100.00% (-100.00%, -100.00%) | 3: 0–3, -100.00% |
| later_january | 4109 / 124 | 0.000629 (-0.000917, 0.002163) | 2: 0–2 | -100.00% (-100.00%, -100.00%) | 2: 0–2, -100.00% |

The declared exploratory gates fail; this exact screen is closed without retuning.

The JSON retains Brier scores, the proportional-method comparison, raw and haircut returns, unknown/void counts and settlement bounds, drawdowns, player concentration, week counts and every gate.

Frozen screen: [card](../docs/hypotheses/hockey-anytime-scorer-normalized-consensus.md), [freeze](nhl-anytime-consensus-freeze-2026-09-28.md). Full results: [JSON](nhl-anytime-consensus-results-2026-09-28.json).
