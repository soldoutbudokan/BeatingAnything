# N3: Independent score-history Challenger totals model

Registered 2026-09-08 while N2 detail acquisition is running, before N2 validation, holdout returns or log loss are inspected. N2's four synchronized opening timestamps are sparse in initial coverage checks (8 of the first 200 fetched pages); this is a source-coverage finding, not a strategy result. N2 remains unchanged and must still be evaluated as specified.

N3 tests the same fixed 21.5-game Pinnacle market, fixed Tuesday/Friday hash-selected sample, 2021/22 development, 2023 validation and 2024/25 holdout, but uses only the two synchronized totals opening records. No current-match moneyline or other later price is needed. Eligibility requires the literal over/under opening times to match at minute resolution and precede the reported start. All absent/invalid markets remain in the acquisition ledger. No failed sample is replaced; final-price activity, closing availability and outcomes cannot decide entry acceptance.

All chronology, source-time, missingness, settlement, 3% EV, 1.20–6.00 price, overround, flat-unit, 2% winnings haircut and no-FanDuel-execution conditions in N2 continue to apply. Closing uses the same active Pinnacle 21.5 pair and source-declared final-price timestamps, plus power de-vig sensitivity. No line substitution or favorable closing-benchmark choice is permitted.

## Independently reconstructed match strength

Maintain a chronological per-player set Elo, starting at 1500, with fixed K=16 and denominator400. A completed historical set updates the two players with equal and opposite increments using its actual winner and the probability `1/(1+10**(-(R1-R2)/400))`. Make every set in a match available only at the conservative date-end-plus48h timestamp defined in N2. Use recognized completed sets even when the historical match was not completed. Apply updates in score order, events ordered by availability time then event ID. No decay, surface split, tuned K, ranking, current player summary or current-match result is allowed.

Immediately before each opening quote, convert the two prior Elo ratings into a set-win probability s and the independent-set best-of-three match probability `3*s*s - 2*s*s*s`. Combine that target with N2's two-player, 50-prior-set-shrunk, 365-day rate of completed sets reaching6-6. Fit the same exact tennis scoring kernel under the same fixed bounds/tolerances/failure gate. The kernel produces an independent total-games distribution. This is a deliberately small model; Elo and tiebreak frequency are imperfect latent skill/serving estimates, not direct observed serve statistics.

The current event's history ID is always excluded from its predictors. If it has an impossible completed-history availability before its own opening, rebuild the relevant Elo history without that ID for that forecast and record the inconsistency; no current score can predict itself. Training and model-selection label availability must precede the relevant holdout quote, including cross-year postponements.

Three separately reported learned candidates:

1. Calibration: early totals logit as offset, plus intercept and standardized early totals logit.
2. Independent set shape: calibration plus standardized independent-kernel-over logit minus early totals logit.
3. Workload: independent set shape plus N2's two completed-match 7-day game-load features.

Choose L2 penalties [0.001,0.01,0.1,1] and the research candidate on2023 paired outcome log loss only. Refit annually on available previous-year outcomes. All three use the same early-feature-valid universe. Report each candidate regardless of result; never choose between N2 and N3 by whichever holdout is profitable.

## Expanded comparison accounting

The full recorded search now contains eleven learned candidates: two earlier MLB, three N1 soccer, three N2 synchronized-market tennis and three N3 independent-history tennis. Before either tennis experiment is evaluated, increase the primary two-sided confidence level to `1 - 0.05/11 = 99.5454545%`, using10,000 weekly block-bootstrap samples and seed1729. Retain the earlier protocols' originally reported intervals as historical records; their failures remain failures. Any favorable new claim must use the stricter eleven-candidate correction. This expansion does not permit unlimited future searching or reuse of these holdouts for newly tuned success claims.

The full prospective FanDuel promotion gate remains unchanged and separate. Historical Pinnacle evidence cannot qualify a current FanDuel bet, and no trial can manufacture90 days of prospective evidence in one research session.
