# FanDuel first-basket test: no edge established

Both fixed candidates fail the [declared advancement gates](../docs/nba-first-basket-price-protocol-2026-09-19.md). The opening-possession signal is real in the sport-side data, but this test does not show a reliable FanDuel pricing advantage. Do not tune these models on the inspected periods to rescue them.

## Forecasts were frozen before independent grading

The [forecast manifest](nba-first-basket-forecast-freeze-2026-09-19.json) was written at **2026-09-19 23:22:28 UTC**, then committed at `80abaa4` before grading. Forecast SHA-256: `99900cee748540e74fbc51cc2da34af666d0c516a4f47f945fc8bbd7ed14742a`. It pins the protocol, implementation and source receipts. The runner refuses to overwrite the forecast cohort or grade changed code/inputs.

Of 580 audited boards, 473 produce forecasts: **296 discovery** (through February 28) and **177 replication** (March 1–May 12). Exclusions are three previously inspected source-validation games, 98 incomplete/ambiguous name joins and six failed prior-roster team assignments. Target outcomes and actual starters do not determine forecast eligibility.

Historical features use completed prior games only. Current-season history requires a matched NBA/ESPN fixture, consistent game date and independent play-by-play completion before the market quote; same-New-York-calendar-day games are excluded. Earlier seasons precede the priced season. Tests confirm that altering target-game scorers, possession winners and starters cannot change a forecast. All 473 saved chronology boundaries, probability totals and selections reconcile. Median board overround is **15.88%** (range 13.72–23.22%).

## Returns at the original selection rule

Flat one-unit stakes; net winnings receive a 2% haircut. Every selected stake stays in the denominator, including voids. The two ROI columns are the declared unresolved-as-loss and unresolved-as-void **sensitivity scenarios**, not a complete range of possible results.

| Model / period | Bets | Wins | Losses | Voids | Unresolved | ROI: unresolved lose | ROI: unresolved void |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tip / discovery | 3 | 0 | 3 | 0 | 0 | −100.00% | −100.00% |
| Tip / replication | 2 | 1 | 1 | 0 | 0 | +342.00% | +342.00% |
| Tip + role / discovery | 204 | 13 | 150 | 20 | 21 | −30.74% | −20.45% |
| Tip + role / replication | 126 | 14 | 98 | 12 | 2 | +0.98% | +2.57% |

The tip-only model has five bets total, below the 50 settled nonvoid bets required in each period. Its one winning long-priced selection cannot establish an edge. Fewer than eight active weeks means no inferential ROI interval is issued.

The role model has adequate settled counts (163 and 112), but discovery is negative in both declared unresolved-settlement scenarios. Replication's corrected 99.6667% week-bootstrap ROI interval is **−56.42% to +66.48%** with unresolved bets counted as losses; counting them as voids gives **−54.78% to +67.13%**. Neither demonstrates a positive return. Pooled role-model ROI is −18.63% or −11.66% under the two scenarios.

Applying the predeclared 1% reserve to betting probabilities reduces role selections to 191 discovery /121 replication. Discovery remains negative (−27.07% /−17.13%), and replication becomes negative (−4.44% /−2.79%). The conclusion is unchanged. Full counts, intervals and sensitivities are in the [machine-readable report](nba-first-basket-backtest-2026-09-19.json).

## Forecast quality and settlement coverage

Independent first scores resolve **467/473 games**, including **30 unlisted scorers** retained in the fixed eleven-category scoring distribution. Of these resolved outcomes, 434 also reconcile to publisher scorer, points and game clock. Five scorer names fail the fixed unique-name join (Jimmy Butler III or Robert Williams III); one game has an invalid/incomplete first-score sequence. They remain unresolved without aliases or favorable deletion. Of 23 unresolved role-model bets, 20 lack complete starter evidence and three have unresolved scoring evidence.

Lower paired log loss means improvement over the normalized FanDuel baseline:

| Model | Discovery difference | Replication difference | Pooled difference |
| --- | ---: | ---: | ---: |
| Tip | +0.002681 | −0.009632 | −0.001959 |
| Tip + role | +0.006715 | +0.000938 | +0.004538 |

The role model is worse on pooled log loss and Brier score. The tip model's small pooled improvement has a corrected interval of **−0.014201 to +0.009989**; replication's interval also crosses zero. These are paired calendar-week bootstraps, 10,000 draws, seed 1729, with the declared 15-comparison allowance. The full report retains Brier scores and descriptive 95% intervals as well.

## Interpretation and next action

This rejects advancement of the **two specific frozen specifications**, not every possible first-basket mechanism. The fixed sport-screen advantage does not translate automatically into enough price error to overcome these margins. Both periods are now inspected. Further work needs a distinct, declared mechanism or genuinely additional data; do not reduce the EV gate, select a profitable player subset, alter role windows or relabel this replication period as untouched.

The next concrete source lead is the already located `vishaalram02/odds` first-basket JSON archive. Inspect its actual book keys, market labels, timestamps and dates before proposing another experiment. It has not yet been established as an additional usable FanDuel cohort.

Returns are historical simulations: quote jurisdiction/historical rule version, original odds JSON and general closing prices remain unverified or absent. The source publisher has studied the archive. The fixed 1% unlisted reserve is a scoring convention, not calibrated coverage; the 30 unlisted outcomes illustrate that limitation. No prospective validation, promotion, wager, alert or schedule is enabled.

## Reproduce

With the retained ignored raw captures and `requirements-first-basket.txt` installed:

```sh
state/runtime/research-venv/bin/python -m unittest discover -s tests
# Only in a fresh output location before any independent grading:
state/runtime/research-venv/bin/python tools/backtest_nba_first_basket.py prepare
# Existing immutable forecasts are already present; grade them directly:
state/runtime/research-venv/bin/python tools/backtest_nba_first_basket.py grade
```

All **259 tests pass**. Raw forecasts, exclusions and individual settlements remain under ignored `data/raw/nba-first-basket-backtest-2026-09-19/`; aggregate reports, hashes and code are tracked.
