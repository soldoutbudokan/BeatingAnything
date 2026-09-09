# Independent N2/N3 training artifact review

After the completed pipeline notification on September 9, 2026, the independent
[artifact audit](../tools/audit_tennis_training.py) checked the exported feature,
fit and forecast files. It found **zero mismatches** for both N2 and N3. It did
not refit any model, rerun the pipeline, change any experiment output, or assess
strategy returns. The [JSON report](../reports/tennis-training-audit.json) records
input-file hashes, reconstructed training-ID hashes, cutoffs and numeric errors.

| Experiment | Accepted features | Development labels | Validation labels | Final-refit labels |
|---|---:|---:|---:|---:|
| N2 | 1,714 | 405 | 443 | 1,628 |
| N3 | 2,950 | 1,124 | 614 | 2,814 |

| Experiment / year | Eligible prior-year training labels | Forecasts | Model unavailable |
|---|---:|---:|---:|
| N2 / 2024 | 848 | 451 | 0 |
| N2 / 2025 | 1,274 | 373 | 0 |
| N3 / 2024 | 1,738 | 636 | 0 |
| N3 / 2025 | 2,337 | 494 | 0 |

The checks independently reconstructed membership from exported source years,
opening quotes and delayed label timestamps:

- Every graded label is binary and becomes available exactly 48 elapsed hours
  after its source date ends at Europe/Prague midnight. Ungraded rows carry no
  invented label timestamp. Every exported entry quote precedes its match start.
- Development uses only 2021/2022 labels available before the first 2023 quote,
  **2023-01-01 06:46 UTC**. All twelve declared candidate/penalty combinations
  are present, their development/validation counts match, and the selected
  penalties and research candidate match the recorded validation-loss minima.
- Both experiments finish receiving their validation labels at
  **2023-12-03 23:00 UTC**, before the first 2024-match opening quote on
  **2023-12-31 09:41 UTC**. Their 2024 training labels have the same maximum
  availability timestamp. The latest 2025-training label is available at
  **2024-12-01 23:00 UTC**, before their first 2025 quotes on January 2:
  10:44 UTC for N2 and 09:12 UTC for N3. All annual training years, counts and
  maximum availability timestamps agree with the fit artifacts.
- All **824 N2** and **1,130 N3** eligible holdout IDs appear exactly once, with
  unchanged feature values. This includes **44 N2 / 54 N3 ungraded forecasts**
  and **two missing-close forecasts in each experiment**. These are forecast
  population counts, not selected-bet counts.
- For all **18 annual/final model artifacts**, means and population standard
  deviations match the reconstructed eligible training features. The maximum
  absolute normalization difference is below **2.5e-15**. The regularized logistic
  score gradient at each stored coefficient vector is below **9.49e-9**, checked
  against those same rows without optimization or refitting.
- Final-refit membership, source-date maximum and label-availability metadata
  agree. Final fits are dated **2026-09-09 22:43:50.549493 UTC** for N2 and
  **22:44:05.476384 UTC** for N3; every included label precedes that timestamp.
  These later fits are separate from the annual historical-forecast artifacts.

The development/validation fit coefficients and normalizers are not exported,
so their eligible-row counts and reported selection minima can be checked, but
their actual development normalization cannot be independently verified from
artifacts without refitting. Annual/final membership is reconstructed rather
than read from a historical per-row training log; matching normalizers and
stationary stored coefficients provide supporting checks. This review starts
with accepted exported features and does not decide whether rejected raw events
should have produced features. It does not certify historical source publication
times or executable prices, remove source-quality blocks, or establish an edge.

Reproduce with:

```sh
state/runtime/research-venv/bin/python -B tools/audit_tennis_training.py
```

The command reads the six original feature/fit/forecast files, writes only its
own audit report, and exits unsuccessfully if a checked mismatch is found.
