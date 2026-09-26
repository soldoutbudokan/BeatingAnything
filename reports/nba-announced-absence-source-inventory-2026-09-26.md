# NBA announced-star absence: source gate cannot pass

**This fixed source route cannot support the declared forecasting test.** The earlier-period coverage is at most **46 games**, even treating every clock-qualified report and every initially unchecked game as eligible. That is below the 100-game minimum before star identification, teammate membership or settlement. No player scoring/minute inputs were restored or joined, no model was fitted, and no returns were calculated. This is insufficient source coverage, not evidence that the basketball effect is absent.

The [declaration](../docs/nba-announced-absence-declaration-2026-09-26.md), committed in `4acb250`, defines all qualifying announced Out absences, including continuing absences; at least eight prior current-season appearances and a prior 20-PPG average; a fixed quote-minus-60-minute information cutoff; strict prior completion clocks; and one nonnegative market-logit correction. It requires 100 exposed fixtures in each period before fitting and separate forecasting/return gates afterward. The old positive return summaries are not probability inputs, and these already inspected seasons are not an untouched holdout.

## Actual prices and fixed source result

The [price census](nba-announced-absence-price-inventory-2026-09-26.json) finds 666 unique independently matched regular-season games /8,286 FanDuel price pairs in the pinned archive. There are 293 earlier and 373 later price games. The [independent audit](nba-announced-absence-price-audit-2026-09-26.json) reconstructs all 666 events, every pair and all 558 exclusions without importing the census implementation. This is price eligibility only.

| Earlier-period result | Games |
|---|---:|
| Previously denied October event excluded before lookup | 1 |
| Stopped on retained HTTP 403 response | 246 |
| First clock-qualified PDF obtained | 11 |
| Unacquired, retained as unknown | 35 |
| Total price-qualified games | 293 |

The 197 new requests comprise 190 HTTP 403 responses and seven HTTP 200 PDFs. Shared URLs were reused; every attempted event stopped at its first URL. No denied URL was retried, and no alternate filename was tried after a denial. These responses do not prove that historical reports are absent. They establish that this **fixed filename order and access rule** did not recover sufficient evidence; it would be invalid to present this as a ceiling on all available injury reports or the frequency of star absences.

The acquisition process stopped on an implementation error after 257 event records: provider “Los Angeles Clippers” differed from source “LA Clippers.” At that point ten games had clock-qualified PDFs and 36 remained unprocessed, including the crashing event. **10 + 36 = 46** is a decisive upper bound even if every report/fixture/status parser rejection is ignored. Further network acquisition therefore stopped. The [execution repair record](../docs/nba-announced-absence-execution-repair-2026-09-26.md) preserves the original script, log, partial ledger and all receipts; the repair was committed in `348a94c`.

Offline completion used the already downloaded eleventh event's PDF and made **zero new requests**. It fixed the Clippers normalization and two independently identified ambiguity checks: contradictory fixture times and a player assigned to both teams now reject the fixture. Five of the eleven reports qualify at the fixture/submission level and have at least one explicit Out row. Counting all 35 unacquired games as qualifying gives the tighter parsed bound **5 + 35 = 40**. The conclusion uses the more generous, parser-independent 46-game bound.

All eleven report bounds are about 64.62 minutes before their quotes. The five coherent submitted fixtures are Orlando–Golden State on December 22, then Toronto–Miami, Chicago–Atlanta, Lakers–Phoenix and Houston–Clippers on December 23. Six other clock-qualified events lack both teams' submitted rows. None of these Out players has been classified as a prior star, and no paired quote has become a forecast or bet. Current PDF/header/server timestamps are retrospective source assertions, not contemporaneous publication receipts.

The [frozen JSON](nba-announced-absence-source-inventory-2026-09-26.json) retains original prices/clocks, candidate order, receipts, literal report rows, unknowns, source and code hashes, both coverage bounds and the failed source gate. The later period remains unacquired by this study; the two earlier three-sample feasibility matches remain separately preserved and cannot repair the failed calibration gate.

## Completion metadata and validation

The separate [completion-clock projection](nba-announced-absence-completion-feasibility-2026-09-26.md) supplies 1,294 usable ESPN fixtures, including 1,204 regular-season games. It preserves missing/duplicate final markers, later conflicting play clocks, and 16 unsupported timestamps roughly a day after their scheduled games. No day subtraction was inferred. Completion plus 24 hours is a declared conservative statistical-availability assumption, not proof of historical boxscore release time. These metadata were not joined to player performance because the source gate failed.

The [source audit](nba-announced-absence-source-audit-2026-09-26.json) records independent receipt, clock, candidate-order, fixture and visual checks. Compilation, parser ambiguity regressions and frozen-output refusal are the relevant implementation checks. The older full repository suite was not rerun for this source-only research.

Stop this exact source/cohort route without fitting, expanding filenames/periods or lowering the gate. The underlying announced-absence hypothesis remains unresolved. The overall research objective remains active and incomplete; no wager, alert or schedule was enabled.
