# F1 independent result review

Reviewed September 8, 2026 against the frozen [F1 protocol](protocol-mlb-timestamped-v1.md), the actual downloaded odds and MLB source files, the saved physical model, and the generated forecasts and metrics. **No numerical or reconciliation discrepancy was found. The experiment remains unproven and generated zero qualifying bets.**

The [machine-readable audit](../reports/timestamped-mlb-independent-audit.json) records artifact hashes, 6,222 checks, zero failures, accepted canonical event IDs, unresolved events, missing reference prices, timing ranges, and recomputed results. Its [independent verifier](../tools/audit_timestamped_mlb.py) uses Python's standard library only: separate CSV/JSON grouping, American-to-decimal conversion, scalar logistic prediction, log loss, Brier scores, and bisection for power de-vig. It does not import the production evaluator or any other `beating` module, NumPy, pandas, or SciPy. Thresholds, features, candidate definitions, source data, and outputs were not adjusted during review.

With the frozen raw source files present, rerun from the repository using `python tools/audit_timestamped_mlb.py`. An alternate repository root can be provided with `--root /path/to/BeatingAnything`. The command rewrites only the independent audit JSON, records the verifier's own hash, and exits nonzero on any failed comparison. The raw publisher feed is intentionally excluded from Git; its acquisition URL and required hash appear below.

## Results reproduced

| Population and model | Forecasts | Graded outcomes | Log loss | Brier | Paired loss change versus FanDuel | Bets |
|---|---:|---:|---:|---:|---:|---:|
| Own population: FanDuel | 100 | 85 | 0.6794288220 | 0.2431573224 | 0 | 0 |
| Own population: physical model | 100 | 85 | 0.6807033347 | 0.2437958546 | +0.0012745127 | 0 |
| Shared population: FanDuel | 97 | 82 | 0.6826309661 | 0.2447373185 | 0 | 0 |
| Shared population: physical model | 97 | 82 | 0.6838668355 | 0.2453572424 | +0.0012358694 | 0 |
| Shared/own population: Pinnacle control | 97 | 82 | 0.6838997331 | 0.2453630724 | +0.0012687671 | 0 |

Positive loss changes mean worse predictions on the matched outcomes. The physical model and Pinnacle control both performed slightly worse than FanDuel in this small sample. Their maximum estimated betting EVs were −1.3334% and +0.8400%, respectively, below the frozen 3% trigger. FanDuel's own normalized baseline also selected no bets. Full ROI, haircut ROI, selected closing EV, and selected raw price-ratio CLV correctly remain null rather than being presented as zero-return evidence.

## Source and timing reconciliation

The original [The Odds Gap export](https://theoddsgap.com/api/odds-export.csv?sport=baseball_mlb&market=ml) still matches SHA-256 `3f433cc28f0a2789dc2dff59f46718ee385181ca9e6fc5e460706fa93585a14e`. Its 67,902 rows yield 3,346 exact FanDuel/Pinnacle paired snapshots; the remaining 61,210 rows belong to other books. There are no identical duplicate side rows in the relevant pairs.

Independent official-fixture matching excluded 17 unmatched/ambiguous snapshot pairs, 55 outside the regular-season nine-inning non-doubleheader contract, and 20 at or after the official start. The remaining 3,254 pairs include 1,885 FanDuel pairs. Of those, 1,416 lie outside the entry time window. The remaining eligible observations reproduce exactly 100 earliest-entry events, identified uniquely as `mlb:<official gamePk>`. No game is duplicated through changing source start times.

All 21 files in the official-data manifest and all 111 retrieved first-pitch source files match their recorded hashes. First pitches independently reconstructed from actual pitch-event `startTime` values match the manifest: 103 source fixtures have a recorded pitch, including 92 accepted events. Non-pitch event timestamps were excluded. Source, official, entry-frozen, and available first-pitch times reproduce the conservative closing boundaries.

Entry snapshots precede their source starts by 37.43–358.24 minutes, within the registered 30-minute–six-hour range, and fall on the official game's Eastern calendar date. Every selected entry is the earliest qualifying pair before examining EV. For each book, 80 of the 100 events have a valid near-start pair; their observations precede the conservative boundary by 1.04–25.18 minutes. Missing closes remain missing and do not remove forecasts. On the shared population, each book has 78 such pairs, including 71 graded outcomes. The audit reproduced proportional and power-method paired loss differences against all four reference variants and all per-day result tables.

## Frozen model, feature integrity, and grading

The model bytes match SHA-256 `c035a7a44c70dc7f16db6624ffebe1b691f2bd76177dfeaf1548813003540f5f`, artifact ID `a7ceefe2db3c13ea`, trained through August 16, 2025. All 100 physical forecasts have complete recorded travel/recent-bullpen inputs. Every saved 21-feature vector matches its per-event hash; every difference equals its recorded home input minus away input. Cutoff dates are the day before the official game date and precede the entry. Directly evaluating the frozen standardized residual-logistic equation reproduces all physical probabilities with maximum absolute error `3.33e-16`.

The 85 final ordinary nine-inning-or-longer games reproduce their binary outcomes. Seven pre-game, six in-progress, and two warmup events stay ungraded in all applicable forecast populations. They are not silently settled as losses, voided, or removed. Because none of the models selected any bets, this particular dataset contains no selected unresolved turnover; that policy is tested separately with synthetic cases.

There are only two calendar weeks. The reports correctly suppress confidence intervals under the eight-week requirement and retain `alerts_enabled: false`, `execution_verified: false`, and `passes_forward_promotion: false`.

## Limits of this review

The audit verifies the saved feature vectors, their chronology metadata and arithmetic, and their use in the frozen model; it does not independently reimplement every raw travel/workload feature calculation. Official records are retrospective and do not establish publication vintage. The Odds Gap provides publisher capture times without upstream bookmaker-update times, so historical price freshness and executable stakes remain unverified. Near-start observations are not guaranteed closing ticks. These limitations and the seven-day window prevent a claim of an established betting edge regardless of the direction of the point estimates.
