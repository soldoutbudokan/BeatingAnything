# BeatingAnything

**No betting edge demonstrated.** Active research has moved to smaller models and markets with a longer season ahead. Completed failures remain visible; no betting alert or wager is enabled.

Use Python 3.12 and the pinned `requirements-lock.txt` dependencies for the research commands below.

The new [timestamped FanDuel MLB pilot](reports/timestamped-mlb-research-report.md) tested the unchanged physical model on 100 September 2026 forecasts. It produced zero qualifying bets and worse log loss than FanDuel on available settled outcomes. Unlike the original archive, this source permits a limited near-start price comparison, but bookmaker freshness remains unverified and one week cannot establish an edge.

The next experiment models **ATP Challenger total games at 21.5**, reconstructing serving and match-length tendencies from historical set scores. The [tennis protocol](docs/protocol-tennis-v1.md) was committed before holdout acquisition. Its exact scoring kernel accounts for service order and tiebreaks. Historical data collection and the frozen backtest are in progress; this is not a profitable-model claim.

Both registered tennis experiments now have a collector, chronological score-history engine and annual evaluation pipeline. [N3](docs/protocol-tennis-independent-v1.md) uses independent prior set Elo; N2 uses synchronized opening moneyline information. The [implementation review](docs/tennis-implementation-review.md) records source and label-availability checks before results. Collection is resumable and preserves failed requests and missing markets; it is currently a local process, not a deployed betting monitor.

All 1,826 required daily pages have been collected. Their frozen sample contains 5,453 match-detail pages; detail acquisition is still in progress. The pipeline will produce a combined report showing every candidate, both holdout years, missing folds and unresolved selected exposure. Actual tennis strategy results have not yet been evaluated. A [current quote-source check](docs/fanduel-tennis-monitoring-source.md) has not verified a usable free FanDuel Challenger 21.5 feed.

An [independent scoring-kernel check](docs/tennis-kernel-review.md) compared the exact distribution with 200,000 synthetic point-by-point matches. This validates the scoring implementation; historical calibration and profitability still require the frozen data tests.

```bash
python -m beating.tennis_source daily
python -m beating.tennis_source details
python -m beating.tennis_pipeline
```

The [additional source audit](docs/source-search-v2.md) also identifies a free 2025 NFL archive with FanDuel capture and bookmaker-update timestamps. It is an untested research lead. [Pitch-level MLB source research](docs/matchup-research-v2.md) verifies a free route to pitch movement and matchup data, while documenting historical lineup-publication limits.

[NFL film-charting research](docs/football-charting-feasibility.md) verifies free play-level pressure and passing-quality fields, but its retained files have later retrieval dates that cannot be treated as timely early-season features. No NFL model or betting return has been tested.

The completed [six-league soccer totals experiment](reports/soccer-research-report.md) tested three small pricing models on **7,741 holdout/replication forecasts**. None produced a bet at the fixed 3% EV threshold. Unlike the earlier MLB archive, its source provides usable same-line historical closing benchmarks. All 42 pinned files match primary source downloads. See [metrics](reports/soccer-metrics.json), [protocol](docs/protocol-narrow-v1.md), [pre-result review](docs/narrow-review-before-results.md) and [source investigation](docs/odds-source-investigation.md).

```bash
python -m beating.soccer run
python -m beating.soccer_evaluate
```

## Archived MLB experiment

On 4,141 historical test games, the physical model scored log loss **0.6771583** against **0.6772104** for FanDuel's paired, no-vig opening probabilities. The model-minus-market difference is −0.0000521, with a 97.5% weekly-block interval of [−0.0003879, +0.0002895]. It improves in 2024 and worsens in 2025. Both learned models produce **zero bets** at the fixed 3% expected-value threshold. ROI is undefined and historical CLV is unavailable; both remain `null` in the results.

Read the [research report](reports/research-report.md), [complete metrics](reports/metrics.json), [review](docs/review.md) and [research log](docs/research-log.md). No wager or betting notification has been sent.

## Reproduce

Use Python 3.12 and run from the repository root:

```bash
python -m pip install -r requirements-lock.txt
python -m beating.pipeline --download
python -m unittest discover -s tests -v
```

The pipeline downloads public sources without an API key or paid service, audits identities, builds lagged features, selects regularization on 2023, and reruns the annual walk-forward evaluation. It writes reports, fitted artifacts and an uncommitted prediction CSV. The first run downloads the 80 MB odds archive and official MLB source batches. Mutable MLB endpoints may change; compare hashes in [reproducibility.json](reports/reproducibility.json) and [the source manifest](reports/mlb-source-manifest.json).

The archive supplies 11,043 accepted FanDuel regular-season games from April 2021 through August 16, 2025. Training uses 2021–2022; validation uses 2023; tests use 2024 and partial 2025. Each test year is fitted only on prior years. The final artifact, `a7ceefe2db3c13ea`, is fitted through August 16, 2025 and remains unproven.

## Model boundaries

A regularized logistic correction takes FanDuel's no-vig market log odds as a fixed offset. Its 21 home-minus-away inputs describe travel, directional time-zone change, rest, compressed schedules, extra innings, individual reliever pitch counts, consecutive-day use, recent role and quality, bullpen coverage, and lagged team form. A calibration-only model is the control. See [feature definitions](docs/features.md) and the [protocol](docs/protocol.md).

The current model does not capture confirmed lineups, starter changes, injuries, weather or news. It never uses the current game's actual starter, lineup, weather or outcome as a predictor. Results enter features after their recorded completion date, with same-day outcomes withheld. Opening prices have no capture timestamps, so historical feature availability at the opener cannot be established. The archive's terminal `currentLine` fields show in-play contamination and are excluded from modeling and CLV entirely.

## New observations

```bash
python -m beating.forward
```

Each cycle builds a dated official MLB feature snapshot, then collects fresh paired FanDuel-labeled moneylines from [Covers](https://www.covers.com/sport/baseball/mlb/odds), matches official game IDs and starts, applies the frozen model, and appends quotes and forecasts to the ledger. Official final results grade hypothetical outcomes. Later cycles restore the ledger, preserving forecasts and model versions.

Future cycles use one cumulative `forward.sql` archive across calendar days, preserving model registration, event deduplication and the earliest forecast. Existing daily ledgers remain separate legacy evidence. Settlement attempts continue when feature or quote refreshes fail; uncertain game identities and settlement formats remain unresolved.

[Live status](reports/live-status.json), [latest decisions](reports/latest-decisions.json) and the [forward report](reports/forward-report.json) show recorded observations. Probability scoring retains the earliest valid pregame forecast per event/model independently of bet selection, including zero-bet runs. Models and verified, aggregator, historical and synthetic sources remain separate. The preliminary model's integration-check rows remain in a separate cohort. The corrected model's first cycle recorded 15 forecasts and no qualifying bets.

Every Covers quote remains **unverified for execution**. Missing inputs, stale quotes, started games and identity mismatches block decisions. The 3% EV, 1.20–6.00 selected-price and 0–8% overround rules are fixed. The runner makes no wager and executes no webhook. An eventual betting alert requires a verified current offer and separately reviewed prospective evidence meeting the [promotion gates](docs/monitoring.md). No such evidence exists yet.

The MLB paper workflow is now **manual only**, following the request to move away from a season nearing its end. Existing ledgers remain intact. Standard public-repository runners were used; no paid service or wager was used. The separate conditional bet watch continues to require the unchanged prospective evidence gates and must remain quiet while no model qualifies.

## Audit trail

| Location | Contents |
| --- | --- |
| [docs/market-selection.md](docs/market-selection.md) | Markets considered and source selection |
| [docs/data-audit.md](docs/data-audit.md) | Odds identities, exclusions and timing limits |
| [docs/features.md](docs/features.md) | Source completeness, chronology and feature formulas |
| [docs/protocol.md](docs/protocol.md) | Fixed experiment and promotion requirements |
| [docs/monitoring.md](docs/monitoring.md) | Ledger, quote checks, scoring and notifications |
| [reports/](reports/) | Metrics, hashes, audits and observational reports |
| [forward-data/](forward-data/) | Versioned feature snapshots and append-only ledger exports |

Historical odds: [public MLB archive release](https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/tag/dataset). Sport data: official [MLB schedules](https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2024&gameType=R), [pitcher index](https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season=2024&gameType=R&sportIds=1&playerPool=ALL&limit=2000), game logs and venue metadata. The raw historical archive is fetched locally and is not redistributed here. The now-inspected holdout cannot become untouched evidence for a revised strategy.
