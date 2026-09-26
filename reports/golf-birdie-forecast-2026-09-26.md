# Golf birdie forecasting diagnostic — September 26, 2026

**The historical profit survives, but the proposed forecasting mechanism does not demonstrate an advantage over the market.** The fixed trigger returns +11.05% in 2023–2025 and +1.09% in 2026. Its Poisson forecast has worse point estimates for log loss and Brier score in both periods, including on the triggered contracts alone.

The September 23 mean-versus-line idea was tested without fitting parameters or searching thresholds. The fixed Under trigger is `line >= trailing 40-round mean - 0.5`. **Poisson is a newly specified, unfitted probability model for diagnosing the original count-skew explanation; the original report did not specify a distribution.** The mean and forecast use birdies plus eagles-or-better from complete PGA rounds whose event finished before the fixture's UTC date; the whole current event is excluded. At least 40 prior rounds are required.

| Period | Observed Under universe | Bets | ROI | Mean model EV | Paired nonpush forecasts | Model minus market log loss |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2023–2025 | All eligible | 589 | 10.49% | -3.38% | 412 | +0.03898 |
| 2023–2025 | Original trigger | 402 | 11.05% | 10.54% | 254 | +0.00505 |
| 2026 | All eligible | 196 | -2.23% | -17.73% | 168 | +0.04063 |
| 2026 | Original trigger | 73 | 1.09% | -0.99% | 65 | +0.03373 |

Positive loss differences mean the Poisson forecast is worse than the opening market. Forecast scores compare both forecasts on the same observed paired contracts after removing realized pushes; the Poisson Under probability is divided by one minus its push probability. Prices are the recorded opening American prices. Returns retain pushes as zero-profit stakes. Missing opposite prices are never created, and closing columns are unused.

- **2023–2025:** trigger 226 wins, 146 losses, 30 pushes; +44.43 units across 46 events. Exploratory event-bootstrap ROI interval [1.38%, 21.31%]. All-eligible paired log-loss difference interval [+0.00164, +0.08104]; Brier difference +0.01858. Trigger-only log-loss difference interval [-0.01998, +0.03337].
- **2026:** trigger 41 wins, 32 losses, 0 pushes; +0.79 units across 10 events. Exploratory event-bootstrap ROI interval [-20.84%, 29.58%]. All-eligible paired log-loss difference interval [-0.01423, +0.09247]; Brier difference +0.01931. Trigger-only log-loss difference interval [-0.04588, +0.12791].

Input contains 873 observed Under contracts; 785 have resolved full-round outcomes and 40 prior rounds. Exclusions: source_join_ambiguous: 2; source_join_missing: 53; source_join_fixture_date_mismatch: 3; fewer_than_40_prior_complete_pga_rounds: 30.

These are descriptive diagnostics of an already inspected source. The historical contract's settlement definition, opening quote times, simultaneity, collection universe, and executable-price provenance remain unresolved. Three historical and four 2026 eligible pairs have negative opening overround, further limiting the interpretation of the source-designated market benchmark. None is removed using outcomes. Event-bootstrap intervals are not adjusted for the preceding research searches. Source hashes, cohort/year splits, and scoring details are in the [JSON report](golf-birdie-forecast-2026-09-26.json); individual probabilities and predictions remain in the ignored local raw-data directory at the path and hash recorded there.
