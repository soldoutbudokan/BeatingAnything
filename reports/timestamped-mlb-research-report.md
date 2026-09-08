# F1: Fresh timestamped FanDuel MLB pilot

Research date: September 8, 2026. **No betting edge demonstrated.** The unchanged physical model generated 100 forecasts and no bets at the fixed 3% EV threshold. Its probability accuracy was worse than the contemporaneous FanDuel baseline on the available settled outcomes. The Pinnacle pricing control also generated no qualifying FanDuel bets.

The [protocol](../docs/protocol-mlb-timestamped-v1.md) was committed as `d00e288`, with pre-result clarifications in `a4a897b`, on the public `research/fanduel-timestamped-tennis` branch before scoring. This is a new retrospective period, not a prospective trial. The model remains `a7ceefe2db3c13ea`, trained through August 16, 2025; no coefficient, feature, threshold or candidate was chosen from this pilot's returns.

## Fixed data and timing

One [The Odds Gap research export](https://theoddsgap.com/data) contained 67,902 MLB moneyline rows captured September 1–8, 2026, including 1,935 paired FanDuel observations. The [source audit](../docs/source-search-v2.md) records the URL, response headers, SHA-256 and publisher limitations. The raw file is preserved locally under `data/raw/oddsgap-mlb-f1.csv` and is not redistributed. A later seven-day export is different data and cannot replace it in this experiment.

Independent official schedule reconciliation produced 100 unique eligible game IDs. Doubleheaders, ambiguous identities and after-start observations were excluded using the fixed metadata/timing rules. The first eligible FanDuel observation six hours to thirty minutes before source scheduled start was selected on the official local game date; EV and future prices played no part in choosing the observation. There were 20 paired observations at/after the official start despite preceding the source's revised start, illustrating why the independent schedule check matters.

The 21 existing physical features were reconstructed from 21 cached official MLB source files, with same-day results withheld. There were no physical-input blocks in the accepted population. Independent pitch-event feeds covered 111 fixtures; 103 had a recorded first pitch, and 92 of the 100 accepted forecasts had such a timestamp. Recorded first-pitch times can only tighten prestart checks. The official schedule/feature snapshot contained 85 completed ordinary outcomes; the remaining 15 forecasts stay ungraded. This report freezes that outcome snapshot rather than silently refreshing it.

The paired Pinnacle control exists in exactly the same publisher scan for 97 of the 100 entries. Results below use that common population; separate own-population results remain in [complete metrics](timestamped-mlb-metrics.json).

## Common-population results

All three rows cover 97 forecasts and the same 82 settled outcomes. Lower log loss is better.

| Forecast | Log loss | Difference vs FanDuel | Brier score | Bets |
|---|---:|---:|---:|---:|
| FanDuel no-vig baseline | 0.68263097 | 0 | 0.24473732 | 0 |
| Frozen physical model | 0.68386684 | +0.00123587 | 0.24535724 | 0 |
| Synchronized Pinnacle no-vig control | 0.68389973 | +0.00126877 | 0.24536307 | 0 |

On the physical model's full population of 100 forecasts / 85 settled outcomes, log loss is 0.68070333 against 0.67942882 for FanDuel, a +0.00127451 difference. The physical model's greatest offered EV is −1.3334%; Pinnacle's greatest implied EV at the FanDuel offer is +0.8400%, below the unchanged 3% threshold. Zero selected bets mean ROI, haircut ROI and selected-bet CLV are undefined, not zero.

## Closing evidence and inference

The primary near-start Pinnacle benchmark is available on 78 of the 97 common events, including 71 with settled outcomes. FanDuel near-start prices and power-method de-vig are separately reported. Each benchmark is a paired observation from thirty minutes to one minute before the earliest applicable prestart boundary; it is not an exact closing tick. Missing closing data does not remove entry forecasts or hypothetical turnover.

The source has publisher capture times but omits upstream bookmaker-update times. Unchanged valid offers cannot be distinguished from cached stale prices, and there is no execution or stake-limit verification. Current official historical endpoints may also contain revisions. These limits preclude an executable-profit claim.

The sample spans only two calendar-week blocks. Following the predeclared minimum of eight blocks, no bootstrap confidence intervals are produced. The observed accuracy difference is a point estimate, not reliable evidence that one probability source is better. No model is promoted and no alert or wager is enabled.

## Reproduction

Use Python 3.12.13 and `requirements-lock.txt`. With the preserved raw odds and official snapshots:

```bash
python -m beating.timestamped_mlb
python -m unittest tests.test_timestamped_mlb -v
```

[Forecasts](timestamped-mlb-forecasts.csv), [reconstructed features](timestamped-mlb-features.json) and [metrics with complete source manifests](timestamped-mlb-metrics.json) preserve the numerical evidence. The command rejects different odds-export or model bytes. Fresh official downloads can differ; compare all recorded hashes rather than treating a rerun as the same source vintage.
