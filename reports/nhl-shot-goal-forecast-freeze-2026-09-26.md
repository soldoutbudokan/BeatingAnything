# NHL shot-to-goal forecast freeze

Status: **frozen_before_target_grading**. No target grading or target-participation filtering was performed. This archive was previously inspected; it is exploratory.

| Stage | Early games / rows | Later games / rows |
|---|---:|---:|
| Prices | 132 / 1208 | 107 / 976 |
| Prior history | 132 / 1158 | 107 / 949 |
| Numerical forecasts | 132 / 1158 | 107 / 949 |

Both post-history and post-numerical 100-game period gates pass: **True**. Selections: **164**, early 94, later 70. Best after-cost EV across all forecast sides: 0.4812541079698289.

Latest 80 eligible appearances are chosen before validating goals/shots; invalid selected counts exclude the offered row without older replacements. Source boxes are scanned for metadata first; only the union of selected prior identities and the declared 2023–24 league identities has goal/shot count fields accessed. All exclusions, prior IDs, availability bounds, aggregates and numerical checks are retained in hashed raw artifacts.

Forecast: `data/raw/nhl-shot-goal-2026-09-26/forecasts.csv`; SHA-256 `24f6d0fcdd027be40c43c27089301b536da98bc3b69b994fbd6b050eac0390a7`. History: `data/raw/nhl-shot-goal-2026-09-26/history-evidence.json`; SHA-256 `a2064bba1844a549378d086265f5b5b6dbb7a9416d4d22e0a14f4b8d3971d71d`. Exclusions: `data/raw/nhl-shot-goal-2026-09-26/exclusions.json`; SHA-256 `4c20fae79ea363bb4cfb02aa2bfadf7e1cb412a76abe4d100888f8f45e9165ac`.

The companion JSON pins every input, source price payload, code file and output. The independent grader must verify those hashes and refuse failed period gates or zero selections. Actual historical availability, executable prices and contract terms remain unverified.
