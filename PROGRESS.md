# Research progress and continuation handoff

Updated September 12, 2026. Latest instruction: restart from this file and NEXT-STEPS.md, avoiding the repeated work that stalled the earlier sessions. Preserve completed work in GitHub and keep the research goal open until evidence supports an edge. This file is maintained as the continuation handoff.

**Direction change (September 9, 2026):** [NEXT-STEPS.md](NEXT-STEPS.md) now sets the research direction and withdraws the NFL charting model as the next step. Read it first. This file remains the record of completed work, file locations, runtime setup and the standing gates.

## Read this first

**No betting edge has been demonstrated. No wager or betting notification has been sent.** The original objective remains unfinished: find a FanDuel market with free historical odds, develop a model using useful sport-specific information, backtest it honestly, and build a process for current prices, news, predictions, ROI, CLV and out-of-sample log loss. The user gave broad freedom over sports and markets and asked to keep working until an edge is demonstrated.

The goal remains **active and unfinished**. Do not mark it complete because code is committed or tests pass. All frozen tennis acquisition, both backtests and their independent audits have now completed. The old collector and evaluation supervisor exited normally; no research job is intentionally left running at this checkpoint.

The active work is the mechanism-first queue in [NEXT-STEPS.md](NEXT-STEPS.md): rank hypotheses, screen sport-side conditional effects, and acquire the exact FanDuel markets needed to test pricing. The NFL charting model is a historical lead, **not the next assignment**. Do not tune the completed tennis models on their inspected 2024/2025 holdouts or substitute more infrastructure cleanup for a useful new test.

Repository: `https://github.com/soldoutbudokan/BeatingAnything`. The September 9 budget checkpoint was published to **`main`**. Its retained research branch is `research/fanduel-timestamped-tennis`, originally from main commit `343d7b4`; the pre-evaluation checkpoint is `a4d4701`. [PR #1](https://github.com/soldoutbudokan/BeatingAnything/pull/1) contains that research description. The September 12 restart is on `research/mechanism-first-restart` in [draft PR #2](https://github.com/soldoutbudokan/BeatingAnything/pull/2); it is not merged. Use Git's actual current state rather than assuming publication or merge occurred.

## September 12 restart

Started from `main` commit `75964993e3ee2e0ac7648a8db0e0ef1b6dbd7661`; its existing GitHub checks passed. NEXT-STEPS.md is the active research direction. Contradictory NFL-model assignments in this handoff have been withdrawn explicitly.

The restart's implementation/results commit is `133cdc06a91f1104c371bc06496b3bbb4a885bae`, retained in draft PR #2. Automatic approval review rejected moving `main` because the current restart request did not explicitly authorize default-branch publication. The work was saved on a separate branch instead. Do not retry that publication without new user authorization; review the draft's actual changes first.

All [30 hypothesis cards](docs/hypotheses/README.md) were saved and counted before the first new sport-side test. Their ranks are subjective priorities, not estimated returns. One `# %%` script, [tools/explore_tennis_states.py](tools/explore_tennis_states.py), screened the first tennis ideas without fitting a model or altering any old holdout. The [results](reports/tennis-state-exploration.md) cover **3,250 complete matches and 84,108 regular service games** from 2020 through May 2026; 87 of 3,337 input matches were excluded.

| Card | Observed next-service break rates | Decision |
| --- | --- | --- |
| Double-break concession | 30.17% in 600 exposed games versus 25.55% in 3,738 one-break controls | +4.62 percentage points misses the prewritten +5-point screen. Same players' other-set break rate is 31.76%; no clear extra concession effect. Deprioritized; the narrower high-hold subset has only 60 exposures and remains unresolved. |
| Long service-game carryover | 24.46% in 417 exposed games versus 19.46% in 16,478 controls | Raw +5.00 points passes the cheap screen, but within-match residual difference is +2.39 points with descriptive interval −1.83 to +6.61. Keep as an unconfirmed idea. |
| Long-tiebreak loser carryover | 17.90% in 162 exposed games versus 22.03% in 817 controls | −4.13 points opposes the prediction. Deprioritized; do not reverse the hypothesis because the winner diagnostic has the opposite sign. |
| Fourth-set concession | 31.03% in 29 exposed games versus 23.08% in 39 controls | Only 29 exposures against the prewritten minimum of 50; descriptive difference interval −13.61 to +29.53 points. Unresolved, not confirmed. |

These are exploratory comparisons on a curated sample, with retrospective strength checks and selection limitations. They neither prove a behavioral cause nor show that FanDuel misprices it. The paired one-break/two-break comparison is particularly selection-biased and cannot support a causal conclusion. The unchanged confirmatory comparison allowance remains 13; no new confirmatory strategy, alert, wager or claimed edge was created.

The exact NFL odds database was recovered from its pinned public release: the SHA-256 remains `b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c`. [The new inventory](docs/market-data-inventory.md) answers the outstanding question: FanDuel and Pinnacle contain only main moneylines, spreads and totals. There are no player props, period markets or alternate-line ladders. A four-hour median capture gap cannot measure short live repricing lags. Do not reopen this source as a presumed derivative archive.

The [bounded forward collector](docs/forward-market-collection.md) is implemented in `beating.forward_collect`. It discovers provider-supported FanDuel/Pinnacle markets, retains raw responses, and separates provider, bookmaker, market and collector clocks. An existing authorized The Odds API key enables the documented local command; none was available here. **No real odds were collected.** The provider does not document tennis next-game hold/break or tennis set correct-score keys, so supplying a key alone does not resolve the leading tennis cards' coverage gap.

The synthetic collector demonstration passed. A real, two-request official MLB check retrieved the September 11–12 schedule and game 822685's scheduled/preview feed; it establishes game-state access, not a verified odds join. It stopped at its request cap. **Nothing is left collecting or running in the background.** All **175 unit tests** passed under the current runtime; six new tests cover only the collector's raw retention, clocks, traversal and failure/cap behavior. No new card verifier, workflow or model audit was built.

The original ignored tennis pages, F1 CSV and runtime from the user's machine were not present in this fresh checkout. No old experiment was rerun or silently given replacement inputs. New sport-side exploration uses the active Match Charting Project at commit `2c59eef194967e688b69e73df344184a06322cd8`, with source files under ignored `data/raw/tennis-state-exploration/`. The older `JeffSackmann/tennis_pointbypoint` URL returned 404. Source coverage and exclusions belong to the new exploration report; they do not establish representative Challenger coverage.

The current workspace provides Python **3.12.14**, NumPy **2.3.5**, pandas **2.2.3**, SciPy **1.17.0**, and lxml **6.1.1**. Run new commands with `python` from the repository root. The original-machine runtime paths below remain historical reproduction instructions.

**Next bounded work:** the long-service card needs replication under the same definitions and better separation of player strength/score selection before calling its sport side confirmed. The fourth-set and high-hold ideas need more relevant observations, not relaxed sample thresholds. Before any recurring tennis odds acquisition, verify one authorized source that actually returns the required FanDuel market and timestamped game state. The current collector's API-key path is useful for documented markets but is not a verified next-game tennis feed. Do not respond to this gap by reopening the NFL derivative search, tuning old main-line models, or adding another audit framework.

## Runtime and local data

Workspace on the original machine: `/Users/tirthbhatt/Documents/BeatingAnything`.

Use **Python 3.12**, with `requirements-lock.txt`, for modeling and evaluation. The original `.venv` and Homebrew default Python are **3.14.6**. That environment's source-built pandas 2.2.3 segfaulted on `pd.to_datetime`; it is not the verified research runtime. The completed tennis collector used only stdlib/lxml and ran successfully under that original `.venv`. Use the verified Python 3.12 environment for future research commands.

A persistent local Python 3.12.13 runtime and research virtual environment have been prepared under the ignored `state/runtime/` directory for the handoff:

```bash
state/runtime/research-venv/bin/python --version
state/runtime/research-venv/bin/python -m unittest discover -s tests -v
```

Earlier verified fallback: `/tmp/beating-venv312/bin/python`. A fresh checkout on another machine will not contain ignored runtimes or data. Recreate a virtual environment with Python 3.12, install `requirements-lock.txt`, then run `python -m pip install --no-deps .`. The locked research versions include NumPy 2.3.5, pandas 2.2.3, SciPy 1.17.0 and lxml 6.1.1.

DuckDB 1.5.5 is an **audit-only** dependency in `state/runtime/nfl-audit-lib`; it is not added to the model dependency lock. Run the NFL fixture audit as:

```bash
PYTHONPATH=state/runtime/nfl-audit-lib state/runtime/research-venv/bin/python tools/audit_nfl_fixtures.py
```

R 4.5.0 is installed on the original machine. The optional legacy QS conversion uses `qs` 0.27.3 and `stringfish` 0.16.0, preserved in `state/runtime/r-audit-lib`:

```bash
BEATING_R_AUDIT_LIB=state/runtime/r-audit-lib Rscript tools/project_nfl_pbp_2024.R .
```

`qs2` cannot read original QS files. Installing current `stringfish` with archived `qs` failed; the versions above compiled and read the retained files. The CSV projections already exist locally, so routine Python audits do not require repeating R conversion.

Raw third-party data, virtual environments, SQLite databases and local runtime state are intentionally ignored by Git. **Pushing all project changes does not upload those files.** They remain on the original machine. Their source URLs, hashes and limitations are recorded in the tracked reports. The important NFL odds database was copied out of `/tmp` to `data/raw/nfl-source-audit/nfl_odds.duckdb` so temporary-directory cleanup does not erase the only copy. Do not replace pinned historical inputs with a newer download and silently call it the same experiment.

## Completed tennis collection and evaluation

All **1,826 daily pages** for 2021–2025 finished at `2026-09-09T00:01:44.781008+00:00`. All **5,453 unique frozen detail pages** finished at `2026-09-09T22:40:08.861688+00:00`, with **zero terminal failures and zero unknown sample dates**. Final metadata checks found no duplicate IDs, missing/extra statuses, mismatched event IDs or missing raw/meta/parsed files. The 91 transient detail request failures across 88 URLs all recovered; their attempts remain in the ledger.

| Source year | Selected detail IDs |
| --- | ---: |
| 2021 | 1,030 |
| 2022 | 1,090 |
| 2023 | 1,105 |
| 2024 | 1,121 |
| 2025 | 1,107 |

The full `acquisition_inputs` gate then verified every pinned raw file, saved parse, sample and identity. Both N2/N3 ran successfully from code commit **`a4d47010d71279f9751f6299bf1e355ff95aca7f`**, beginning at **22:42:05 UTC**. The independent forecast audit finished at **22:44:06 UTC**. The original collector (PID 50494, agent-local session 52897) and root supervisor (PID 57105, session 71790) exited normally. **Do not restart them or recollect this completed sample.** Verify current OS state before drawing conclusions from old process IDs.

The final full-range `daily-summary.json` and `details-summary.json` are authoritative completion summaries. The old 12-page development summary has been replaced. Source layout under `data/raw/tennisexplorer/`:

- `daily/`, `details/`: fixed raw responses and acquisition metadata.
- `sample/`: immutable fixture-only daily sample pins.
- `parsed-daily/`, `parsed-details/`: normalized caches verified against raw sources.
- `daily-status/`, `detail-status/`: final per-file status.
- `acquisition.jsonl`: append-only attempts with timestamps and hashes.

The tracked [run record](reports/tennis-run.json), [combined results](reports/tennis-research-report.md), metrics and audits preserve the experiment. Local operational records are `state/tennis-final-acquisition-audit.json`, `state/tennis-evaluation-run.json`, `state/tennis-evaluation.log` and `state/finish_frozen_tennis.py`. The local wrapper used an exclusive-create output log and is not meant to be rerun blindly. Its installed parser/pipeline hashes matched the repository at launch; the backtest itself ran from the repository root.

Raw pages and runtimes remain local and ignored. A different machine needs the exact pinned inputs to reproduce these results. A newer download may revise historical pages; never substitute it silently. The collector's cache-preserving commands remain available for deliberate recovery, with the same sample and ordinary pacing, but collection is already complete.

## Frozen tennis experiments: do not change them from results

Read [N2](docs/protocol-tennis-v1.md), [N3](docs/protocol-tennis-independent-v1.md) and the [pre-result implementation review](docs/tennis-implementation-review.md). Both target standard men's ATP Challenger best-of-three **full-match total games 21.5**, using historical **Pinnacle**, not historical FanDuel execution.

Key fixed choices:

- Daily ATP singles history covers 2021–2025. Detail sampling uses every Tuesday/Friday, at most 12 Challenger IDs per date, ordered by SHA-256 of `N2-v1|match_id`; missing markets do not get replacements.
- N2 requires paired total and moneyline opening timestamps synchronized to the source's minute resolution and before start. N3 requires only paired total openings, using prior set Elo instead of moneyline.
- Historical set data becomes available after Prague-local source-date end plus 48 elapsed hours. Preceding-365-day tiebreak rate is shrunk with 50 sets at 0.12. Set Elo starts at 1500, K=16, denominator 400, with causal ordering and current-event exclusion.
- The exact service/tiebreak/best-of-three kernel infers serving strengths. Workload uses the fixed prior-seven-day completed-match game counts and caps. See the protocol for numerical tolerances and all features.
- Development is 2021–2022; validation is 2023; holdout is 2024 and 2025, with prior-year-only annual refits. Calibration, set-shape and workload candidates all remain in the report. L2 choices are `[0.001, 0.01, 0.1, 1]`, chosen from validation only.
- Training labels and validation selection must have been available before each forecast. Early new-year quotes preceding final validation-label availability are explicitly model-unavailable, not fitted using future labels.
- At most one flat unit per event, maximum-EV side, EV at least 3%, selected decimal price 1.20–6.00, entry overround 0–10%; ties choose over. Apply a 2% haircut to net winnings.
- Closing evidence is the same 21.5 line and paired prestart Pinnacle prices. Missing closes remain missing on selected exposure. Retired/unclear outcomes remain ungraded, with worst/best exposure bounds and separately labeled complete-match sensitivity.
- The current finite comparison allowance is **13**, with 10,000 calendar-week bootstrap draws, seed 1729. **No NFL experiment or additional comparison allowance has been registered.** Do not silently change this number based on an idea discussed during the interrupted session.

Implementation:

| File | Responsibility |
| --- | --- |
| `beating/tennis_source.py` | Acquisition, sample pins, score/market parsing and timestamp checks |
| `beating/tennis_history.py` | Causal prior set history, Elo, tiebreak and workload features |
| `beating/tennis_kernel.py` | Exact scoring distribution and serving-rate inversion |
| `beating/tennis_pipeline.py` | Full-acquisition/provenance gate, features, chronological fitting and all candidate forecasts |
| `beating/tennis_evaluate.py` | Fixed entry policy, ROI/exposure/CLV/loss and corrected intervals |
| `beating/tennis_report.py` | Combined human-readable report, including missing years and unresolved exposure |

**Both real tennis strategy evaluations are complete.** Their now-inspected holdouts must not be treated as untouched evidence for a revised model. Parser development examples and synthetic tests preceded the single full frozen evaluation; no partial-sample strategy tests were run.

The completed provenance gate can be reproduced, if needed, with:

```bash
state/runtime/research-venv/bin/python - <<'PY'
from beating.tennis_pipeline import acquisition_inputs
history, details, audit = acquisition_inputs('data/raw/tennisexplorer')
print({k: audit[k] for k in (
    'daily_dates_required', 'sampled_unique_events', 'parsed_details',
    'failed_daily_dates', 'failed_sampled_detail_events')})
PY
```

It binds raw files to successful acquisition hashes, reparses normalized records, verifies immutable sampling and detail identities, and refuses unattempted pages. If a genuine parser defect is found, correct it uniformly from raw evidence, document the change before reviewing results and preserve the original sources. Some parser-hardening changes were made while the daily collector's older process image was live; a reparse discrepancy must be investigated, not waved away or fixed by overwriting raw data.

A read-only rehearsal checked all 1,826 daily files/pins/caches and the 4,636 completed detail files in its September 9, 22:26:32 UTC ledger snapshot. All source hashes and current parser/cache comparisons matched, with no sampled identity/date mismatch. Nine daily history entries lack stable player identities in the saved source; they are UTR Pro Tennis Series 5 rows with doubles-style/plain-text identity cells, outside the frozen Challenger sample. Their possible history contribution remains unknown. Preserve the source-quality blocks; no parser or cache change was justified. See [pre-evaluation source review](docs/tennis-acquisition-review.md) and [identity-only audit](reports/tennis-source-quality.json).

The original evaluation command ran both experiments together:

```bash
state/runtime/research-venv/bin/python -m beating.tennis_pipeline \
  --source-dir data/raw/tennisexplorer --output reports
```

Produced outputs are `tennis-n2-*` and `tennis-n3-*` features, forecasts, fit and metrics files, plus `reports/tennis-research-report.md`. Both declared holdout years fitted. No original forecast, coefficient or metric was changed during independent review. Rerunning records a new final-fit timestamp; preserve the original outputs and hashes instead of silently replacing the original run.

The independent stdlib-only arithmetic/chronology checker passed ten synthetic corruption/edge-case tests before evaluation and **32,556 checks with zero failures** on the completed real outputs. Reproduce its audit with:

```bash
state/runtime/research-venv/bin/python -S tools/audit_tennis_forecasts.py \
  --output reports --report reports/tennis-independent-audit.json
```

It reproduces annual-coefficient probabilities, validation-grid choices, all candidate/year point estimates, betting returns and ungraded bounds, proportional/power closing arithmetic, recorded chronology, hashes and evidence flags. It explicitly does not replay bootstrap endpoints, reconstruct model training/normalization or raw-history features, or independently identify markets from raw pages. It handles insufficient data without treating stale forecast files as current evidence. Its real-output audit is saved in `reports/tennis-independent-audit.json`. A separate [training review](docs/tennis-training-review.md) reconstructed eligible rows and verified all 18 annual/final normalizers and stored-fit score gradients, with zero mismatches. Run `state/runtime/research-venv/bin/python -B tools/audit_tennis_training.py` to reproduce that review. It does not refit models; development normalization cannot be independently verified from artifacts because development coefficients were not exported.

## Completed results that must remain visible

| Experiment | Result and practical interpretation |
| --- | --- |
| Original MLB physical model | 4,141 test games; log loss 0.6771583 versus FanDuel 0.6772104. Paired delta −0.0000521 with interval crossing zero. Zero qualifying bets; no usable historical CLV. No edge. |
| N1 six lower-division soccer totals | Three candidates, 7,741 holdout/replication forecasts; all zero qualifying bets. Historical Bet365, not FanDuel execution. No edge. |
| F1 timestamped 2026 FanDuel MLB replication | 100 forecasts, 85 settled in the frozen outcome snapshot. All zero qualifying bets. On 97 shared forecasts / 82 settled, physical loss 0.6838668355 versus FanDuel 0.6826309661: delta **+0.0012358694**, worse. Pinnacle control also worse. No edge. |
| N2 Challenger total 21.5 | 824 forecasts / 780 graded; all zero qualifying bets. Validation-selected workload loss 0.6940656655 versus Pinnacle opening 0.6942150287, delta −0.0001493632; corrected interval crosses zero. No edge. |
| N3 independent-history Challenger total 21.5 | 1,130 forecasts / 1,076 graded. Validation-selected workload has four bets / three graded / one unresolved, loss delta **+0.0004357701**, worse; mean selected closing EV **−4.7791%**. Overall ROI undefined; haircut-return bounds −48.54% to +3.655%. No edge. |

F1 used the unchanged MLB artifact `a7ceefe2db3c13ea`, trained through August 16, 2025, file SHA-256 `c035a7a44c70dc7f16db6624ffebe1b691f2bd76177dfeaf1548813003540f5f`. Its protocol and timing clarifications were pushed before scoring. It did not refit on the new week.

Pinned F1 input: `data/raw/oddsgap-mlb-f1.csv`, SHA-256 `3f433cc28f0a2789dc2dff59f46718ee385181ca9e6fc5e460706fa93585a14e`, downloaded September 8, 2026 at 23:10:42 UTC. Official MLB inputs and first-pitch evidence are under `data/raw/mlb-2026-f1/`. The seven-day export is mutable at its source URL: a fresh request is a different dataset.

F1 supplies publisher capture times, not bookmaker freshness. It has only two week blocks, so the registered minimum block count prevents interval claims. Zero-bet ROI and selected CLV remain null, not zero. See [F1 report](reports/timestamped-mlb-research-report.md), [independent review](docs/timestamped-mlb-review.md) and [original MLB report](reports/research-report.md). Their inspected outcomes cannot be recycled as untouched tests for revised strategies.

Both tennis experiments selected workload from validation and penalty **1.0 for every candidate**. N2 has 1,714 accepted feature rows; N3 has 2,950. N2 annual forecasts are 451 (2024) and 373 (2025); N3 has 636 and 494. All candidates' corrected paired log-loss intervals cross zero. The N3 workload's four selected bets all occur in 2024; all four have same-line closing evidence. Its three graded bets return −31.3867% after the winnings haircut, but that sensitivity excludes the fourth unresolved bet and must not be reported as full-cohort ROI. The four-bet closing sample is very small. No candidate qualifies even apart from the retained source-quality block; do not attribute the negative conclusion solely to nine ambiguous history rows.

The separate training audit verified 44 N2 and 54 N3 ungraded forecasts and two missing-close forecasts in each experiment remain included. The latest validation label predates the earliest 2024 quote. All annual training labels precede their first forecast quote; normalizers agree within 2.5e-15 and maximum regularized score gradient is below 9.49e-9. These checks support correct implementation, not profitability.

Independent checks already completed:

```bash
state/runtime/research-venv/bin/python tools/audit_timestamped_mlb.py
state/runtime/research-venv/bin/python tools/audit_nfl_charting.py
```

The F1 verifier passed 6,222 checks. The tennis kernel was separately compared with 200,000 synthetic point-by-point matches; all 16 comparisons were within 1.78 Monte Carlo standard errors. See `tools/validate_tennis_kernel.py`, `reports/tennis-kernel-independent-check.json` and its review. This expensive simulation need not be repeated unless the kernel changes or a new concern appears.

## Historical NFL lead: no registered model; withdrawn as the next task

Read [price-source audit](docs/source-search-v2.md), [film-charting feasibility](docs/football-charting-feasibility.md), [fixture feasibility](docs/nfl-fixture-feasibility.md), [charting audit](reports/nfl-charting-source-audit.json), [depth-chart audit](reports/nfl-depth-chart-source-audit.json) and [fixture audit](reports/nfl-fixture-feasibility.json).

Important retained files under `data/raw/nfl-source-audit/`:

| File | SHA-256 / provenance |
| --- | --- |
| `nfl_odds.duckdb` | `b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c`; NFL Market Tracker v1.1.1 public release; 1,856,036 raw rows |
| `ftn_charting_2024.csv` | `6faae8118cc13ce62589210d553733128ed35e558671009b4a7a8fc5c674c2cb`; exact GitHub asset created/updated September 1, 2025 |
| `play_by_play_2024.qs` | `c61a0fc53b0cd212bb07ffbe99da83efaa0e63c22e8790fd61293b53412ebdd9`; exact GitHub asset created/updated September 3, 2025 |
| `play_by_play_2024-feature-projection.csv` | `f129cef7e21d1e294b60e47e92d0c6b355065358e90f7ee531211f973319908d`; derived 16-column projection, 49,492 rows, no scores/EPA/odds/result labels |
| `depth_charts_2025.csv.gz` | `5cbc4d088a05c1c7b047ebdd2bacb480c97aac5849d46fc631fa041d09dd8ef7`; partial depth-chart source audit only |

Both exact 2024 charting and play-by-play assets predate the first 2025 NFL game. Their local hashes match the retained GitHub release digests. All 48,031 charting keys join the PBP file. The older QS format was useful because newer 2024 PBP CSV/Parquet assets were replaced in 2026.

Do not use current 2025 FTN charting as timely weekly input: every row has a September 2026 retrieval date. An older 2025 QS version has December 2025–February 2026 retrieval dates; those do not independently prove earlier public availability. The publisher ETL stamps retrieval time before publishing. The expanded source audit passed 175 checks before handoff.

The metadata-only fixture audit maps all 285 2025-season fixtures (272 regular season, 13 postseason). Fixed first paired FanDuel entry between 24 hours and one hour before a conservative prestart boundary, book-update age 0–90 seconds and vig 0–8%, yields 285 entries. All have valid synchronized Pinnacle entry pairs. Only **77/285** have a valid last reference within 30 minutes of the independent kickoff; none within 90 seconds. This supersedes preliminary counts of 78. Winter/weekly coverage is in the report. Do not relax the closing definition to manufacture a useful CLV sample.

Fixture inputs/projections are in `data/raw/nfl-fixture-feasibility/`. `fixture-source-uninspected-results.csv` contains scores in unused columns; the tool projects metadata before analysis and has not used those result labels. `candidate-quote-projection.json` contains fixed entries and references, no realized results. The fixture source is public nflverse/nfldata, independent of the odds archive but not an official execution feed; kickoff publication vintage is unresolved.

The 2025 depth archive has 554,215 rows, 221 timestamps from August 3, 2025 through March 14, 2026, and 7,071 first-ranked QB entries, with no missing GSIS ID or conflicting first-QB snapshot in the initial check. First rank is a depth-chart listing, **not the actual starter**. Publisher code prepends new snapshots but can remap GSIS IDs and normalize names across older rows. Verify exact prequote coverage, player identity and publication assumptions before using it. The partial audit and source URL/hash are in `reports/nfl-depth-chart-source-audit.json`.

Unregistered idea under discussion: prior-2024 QB rates of charted interception-worthy throws or QB-fault sacks, split by five-or-more versus fewer pass rushers, interacted with the opponent's prior rush tendency; choose the QB from the last available depth snapshot before the odds observation, never from the eventual game's starter. Include scrambles in the denominator using `rusher_player_id`; otherwise the feature conditions on failure to escape pressure. No feature coefficients, priors, lookbacks, split dates, candidates or fourth experiment were frozen. No NFL model has been fitted and no NFL betting returns computed. A public tie example appeared incidentally while checking FanDuel settlement rules; it was not used to select a cohort or strategy.

Prior-2024 feature exploration found 21,139 QB dropbacks, all joined to FTN; 1,133 are scrambles with missing passer ID but available rusher identity. There are 263 zero/impossible pass-rusher counts, including one value of 45; 10 charted QB-fault sacks lack a PBP sack flag, and one row has both risk flags. These require a documented uniform quality rule before model registration. Do not silently repair values or tune handling on 2025 outcomes. `no_play` is absent from the projection/source schema requested; use documented `play_type`/dropback semantics instead of assuming the column exists.

The earlier proposed NFL action was a metadata/feature-availability audit followed by a separately frozen model. NEXT-STEPS.md withdrew that assignment. The source details above remain available if a specific new hypothesis eventually justifies using them; they are not evidence of profitability.

## Current monitoring capability and limits

`beating.monitor` is an append-only SQLite quote/prediction/decision/settlement ledger and outbox. `beating.forward` remains an **MLB observational runner**, not a tennis adapter. It now uses one cumulative `forward.sql`/`forward.sqlite3` across dates and fresh-runner restores, preserving the model registry and earliest forecast. Existing daily archives and unexported local daily databases remain separate legacy evidence; their events cannot be recounted in the new ledger.

New observations can fail while existing results still get graded. Local and shared-export writer locks coordinate concurrent runs. Atomic restores cannot publish partial databases. New trial policy hashes exclude webhook transport; old immutable full-config bindings retain their original meaning. Pending outbox items recheck policy, current price, expiry and settlement status. All changes have synthetic regression coverage.

Remaining limitations are explicit in [monitoring documentation](docs/monitoring.md): existing local databases are authoritative relative to an externally newer archive, locks coordinate only a shared filesystem, legacy cohorts are not merged, and evidence promotion still relies on independently reviewed assertions. Fifteen-minute polling cannot assure a five-minute closing snapshot or a sixty-second notification lifetime. The MLB workflow is manual only; do not reenable its old schedule just because the code merges.

A current source check found no usable free paired FanDuel Challenger 21.5 feed: ordinary FanDuel and Oddspedia requests were denied, and the accessible Odds Gap board had US Open moneylines but no relevant FanDuel totals. An ordinary CUA browser was unavailable. No challenges, location restrictions or paid access were bypassed. See [source audit](docs/fanduel-tennis-monitoring-source.md). The Odds Gap's allowed one-off research export is not permission to run an unrestricted downstream feed.

No model currently meets the unchanged prospective promotion requirements: frozen model/cohort/policy, verified paired FanDuel entry and nearstart reference evidence, immutable forecasts, at least 1,000 settled paper bets over 90 days at fixed checkpoints, positive corrected haircut-ROI and closing-EV lower bounds, and negative paired-loss upper bound. Do not fabricate evidence flags, interpret an aggregator quote as executable, enable an unproven betting alert, or treat a historical Pinnacle result as verified FanDuel execution.

## Validation and next-session checklist

The persistent local Python 3.12.13 environment passed all **169 unit tests**, including ten synthetic tests for the independent tennis forecast auditor. It also passed the F1 audit (6,222 checks), expanded NFL charting audit (175 checks), and NFL fixture reproduction (285 entries, 77 nearstart references). The two pre-evaluation CI runs on `a4d4701` passed (34412677883 and 34412673065). Both actual tennis runs and their independent audits also passed implementation checks. Inspect GitHub checks for the final result checkpoint and `main`; passing CI is not evidence of an edge. Local final-check logs are under `state/final-*`.

1. Read NEXT-STEPS.md and the latest checkpoint here. Verify actual Git status and GitHub checks.
2. Continue from the ranked [hypothesis queue](docs/hypotheses/README.md) and its recorded results. Do not rewrite the queue or repeat completed screens without a concrete new question.
3. For a surviving sport-side effect, obtain FanDuel prices for the exact market at the observable trigger, with game-state and quote clocks. A sport-side effect alone is not an edge.
4. Treat cards and cheap descriptive tests as exploration. Freeze a new confirmation only after both sport behavior and a pricing discrepancy are observed; the existing confirmatory comparison allowance stays 13 until a new protocol is registered.
5. Preserve existing holdouts, promotion gates, and disabled betting alerts. The archived MLB runner is not the new collector or a substitute for a new edge.
6. Record what was learned, what was ruled out, the exact next test, and what is actually collecting. Preserve completed work in GitHub and leave the original goal unfinished while no edge is demonstrated.

Local `state/continuation.json` is a convenient pointer file but may be stale. The OS process, source ledger, pinned files, actual test output, Git history and completed reports are authoritative.
