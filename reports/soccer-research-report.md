# N1 result: lower-division soccer total 2.5

**No demonstrated edge. All three learned models selected zero bets in both the 5,184-event holdout and the 2,557-event replication.** None improved paired out-of-sample log loss with the required corrected confidence bound. Alerts remain disabled. This experiment establishes a working historical closing-value calculation; it does not establish profitable Bet365 or FanDuel execution.

Recorded September 8, 2026. Evidence: [metrics](soccer-metrics.json), [fit and selection record](soccer-fit.json), [source audit](soccer-source-audit.json), [forecasts](soccer-forecasts.csv), [frozen protocol](../docs/protocol-narrow-v1.md), and [review before results](../docs/narrow-review-before-results.md).

## Fixed question and historical data

The test pooled Championship, League One, Bundesliga 2, Ligue 2, Serie B and Segunda regular-season matches, with one shared model and one market: full-time over/under 2.5 goals. League choice, features, selection, splits and bet thresholds were recorded before examining the new holdout results. This was a retrospective specification, not prospective registration.

[Football-Data](https://football-data.co.uk/data.php) supplies paired Bet365 early prices and separate closing prices, plus early and closing market averages. The first snapshot is collected after opening; calling it an opener would be inaccurate. Neither snapshot has an individual capture timestamp. No Pinnacle field was used. Source-designated closing comparisons are supported; simultaneous market availability, execution at the early price, and FanDuel transfer are not verified.

All 42 pinned source files matched the primary downloads byte-for-byte. Of 18,023 source rows, 17,968 passed the early-input requirements. The 55 exclusions were invalid early prices. Acceptance did not depend on realized results or closing availability.

| Period | Seasons | Accepted events | Role |
|---|---|---:|---|
| Development | 2019/20–2021/22 | 7,600 | Fit candidate models |
| Validation | 2022/23 | 2,627 | Choose penalties and one research candidate |
| Holdout | 2023/24–2024/25 | 5,184 | Report frozen-policy results |
| Replication | 2025/26 | 2,557 | Separate additional period |

The fixture audit records curtailed 2019/20 League One and Ligue 2 seasons and one source-omitted abandoned Troyes–Valenciennes fixture in 2023/24. These source omissions remain disclosed. One accepted replication event lacks a usable outcome: all-event outcome metrics use 2,556 settled events, with missingness retained. There are 2,551 replication events with a valid closing pair and 2,550 with both that pair and a known outcome.

## Models and selection

The baseline is proportional no-vig early Bet365 probability. Every learned model uses its logit as a fixed offset and training-only normalization:

1. **Calibration:** intercept plus a correction to the early market logit.
2. **Consensus discrepancy:** calibration plus early average-minus-Bet365 logit.
3. **Goal structure:** consensus plus a total-goals probability inferred from the early Bet365 home/draw/away prices through a bounded independent-Poisson approximation.

The third feature tests consistency between related markets; it is not independent team-performance information. The assumption can fail because goals are dependent and bookmaker margins differ. Undocumented within-row snapshot synchronization is another limitation.

Penalties were chosen from 0.001, 0.01, 0.1 and 1 using validation log loss only. Calibration selected 0.1; the other two selected 1. Calibration was the best learned validation candidate at 0.677219 log loss, compared with 0.677420 for early Bet365 and 0.677171 for the untrained early-average control. Models were refit before each test season using preceding seasons only. The untrained control was descriptive and ineligible for promotion from this experiment.

The fixed decision required at least 3% estimated EV, decimal odds 1.20–6.00, and valid paired early overround no greater than 10%. At most one unit per event was allowed. The execution sensitivity reduces net winnings by 2%. No threshold, league, side, or model was chosen using holdout returns.

## Results

Lower log loss is better. The replication column evaluates its 2,556 known outcomes; selection covers all 2,557 accepted events.

| Forecast | Holdout log loss | Holdout bets | Replication log loss | Replication bets |
|---|---:|---:|---:|---:|
| Early Bet365 no-vig baseline | 0.680516 | 0 | 0.684530 | 0 |
| Early average, untrained control | 0.680514 | 3 | 0.684070 | 2 |
| Calibration, selected on validation | 0.680616 | 0 | 0.684400 | 0 |
| Consensus discrepancy | 0.680652 | 0 | 0.684497 | 0 |
| Goal structure | 0.680637 | 0 | 0.684558 | 0 |

All learned models underperformed early Bet365 on holdout point estimates. Some replication point estimates improve slightly, but every corrected interval crosses zero:

| Learned model | Holdout loss difference versus early Bet365, 99.375% interval | Replication difference, 99.375% interval |
|---|---|---|
| Calibration | +0.000100; [−0.000439, +0.000692] | −0.000130; [−0.000691, +0.000394] |
| Consensus discrepancy | +0.000136; [−0.000121, +0.000411] | −0.000033; [−0.000176, +0.000099] |
| Goal structure | +0.000121; [−0.000145, +0.000404] | +0.000028; [−0.000134, +0.000189] |

Intervals use 10,000 calendar-week block-bootstrap samples and the registered eight-model comparison allowance, which includes earlier research and the reserved N2 candidates. This protects a finite family; it does not justify unlimited repeated testing.

With zero learned-model bets, their ROI and selected-bet CLV are **undefined**, not zero-return evidence or proof of safety. All three fail the retrospective screen and prospective promotion gate.

## Historical CLV works; its measured result is not an edge

For a selected side at entry decimal price $d$, paired closing decimal prices $c_s,c_o$ give proportional no-vig closing probability and closing EV:

$$
p_{\mathrm{close}}=\frac{1/c_s}{1/c_s+1/c_o},\qquad
\mathrm{closing\ EV}=d\,p_{\mathrm{close}}-1.
$$

Both prices must refer to the same 2.5-goal contract. The primary reference is the market-average pair; Bet365 closing and power-method de-vig are reported sensitivities. Raw price-ratio CLV, $d/c_s-1$, is a separate statistic and must not be confused with no-vig closing EV. Every holdout event has a valid closing pair, so missing closing data is not why the learned models have no measured selected-bet CLV. They simply did not select bets.

The untrained early-average control illustrates the calculation and its limitations:

| Control result | Holdout | Replication |
|---|---:|---:|
| Bets | 3 | 2 |
| Simulated profit | −0.95 units | −2.00 units |
| ROI | −31.67% | −100.00% |
| ROI after winnings haircut | −32.37% | −100.00% |
| Mean no-vig average-closing EV | +3.57% | +6.04% |
| Mean no-vig Bet365-closing EV | +0.22% | +7.05% |
| Mean raw average-price ratio | +9.93% | +14.09% |

The holdout control's corrected ROI interval is **[−100.00%, +105.00%]**, haircut-ROI interval **[−100.00%, +102.90%]**, and primary closing-EV interval **[−5.76%, +16.67%]**. Its paired log-loss interval also crosses zero. With only two replication bets, the report does not provide a usable bet-level confidence interval. Under power de-vig, holdout average-closing EV changes to **−1.73%**. These positive proportional-CLV point estimates, negative returns, tiny samples and benchmark sensitivity do not qualify as a successful strategy.

The primary average changes bookmaker composition and can include Bet365 itself. It is a reference distribution, not an independently executable sportsbook. Even statistically favorable historical results would still require a separately reviewed prospective FanDuel cohort.

## Reproduction and disposition

```sh
python -m beating.soccer run
python -m beating.soccer_evaluate
```

| Artifact | SHA-256 |
|---|---|
| Frozen N1 protocol | `21c3d81b4fb9db4f38423435e0121719549835d1fc4e05880741a304f5a0e85f` |
| Model artifact | `4a24ce1efac9c0c4016049c58c41539f8688350f88223cd5ca3036a8458b1fdf` |
| Forecast CSV | `028426d0f5dcc5540db97519fe2b2485050cbda59bc1202d5084770d0670b0c8` |

N1 is retained as failed evidence. Its holdout will not be reused as untouched data for a revised hypothesis. The next separately frozen investigation is [N2 Challenger 21.5-game totals](../docs/protocol-tennis-v1.md), using the timestamped TennisExplorer archive and a small score-process model. No N2 model result is asserted here. The [source investigation](../docs/odds-source-investigation.md) explains that choice and the rejected alternatives.
