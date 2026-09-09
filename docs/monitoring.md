# Paper monitoring and forward evaluation

`beating.monitor` is a standard-library SQLite audit ledger and notification outbox for paired FanDuel MLB full-game moneylines. It does not place bets. The fitted research models remain **unproven**. No validated betting alert or webhook has been enabled.

A normalized quote import is not a live FanDuel connection. The separate public-page collector records observations without certifying execution, bookmaker freshness or local availability. Missing FanDuel rows produce no quotes. An aggregator observation is always unverified until a separate acquisition process checks the actual current FanDuel offer. Do not relabel an aggregator timestamp as the bookmaker's timestamp.

## Command interface

Run from the repository root:

```bash
python -m beating.monitor --db state/monitor.sqlite3 --config config/monitor.json init
python -m beating.monitor --db state/monitor.sqlite3 ingest state/quotes.json
python -m beating.monitor --db state/monitor.sqlite3 register-model state/model-registration.json
python -m beating.monitor --db state/monitor.sqlite3 predict state/predictions.json
python -m beating.monitor --db state/monitor.sqlite3 outbox
python -m beating.monitor --db state/monitor.sqlite3 settle state/settlements.json
python -m beating.monitor --db state/monitor.sqlite3 report
```

Input files can contain one object or an array. `Monitor.ingest_quote`, `register_model`, `predict`, `settle`, `pending`, `dispatch`, `forecast_report` and `report` provide the equivalent Python API. `beating.predict` connects the fitted artifact and point-in-time features to this API. The optional `now` argument is for deterministic tests; production commands use the actual UTC clock.

`examples/synthetic_quote.json` is visibly synthetic and intentionally becomes stale. It is a schema example, not market data or an active opportunity. Do not refresh its timestamps and present it as a real observation.

## Paired quote schema

| Field | Requirement |
|---|---|
| `event_id` | Stable event identifier; explicitly distinguish doubleheaders |
| `sport`, `bookmaker`, `market` | Exactly `MLB`, `FanDuel`, `moneyline` |
| `home_team`, `away_team` | Different, nonempty names; event identity cannot be silently changed |
| `starts_at` | Scheduled first pitch, ISO 8601 with timezone |
| `observed_at` | Actual paired observation time, ISO 8601 with timezone |
| `status` | `open`, `suspended` or `closed`; unknown states must not be mapped to open |
| `is_live` | Boolean; live markets are blocked |
| `decimal_home`, `decimal_away` | Finite numbers greater than one from the same book, event and snapshot |
| `source.uri`, `source.provider` | Traceable original source and acquisition provider |
| `source.verified` | Boolean operator assertion of a directly checked, current offer |
| `source.verification_method` | Nonempty explanation required when verified |
| `source.synthetic`, `source.historical` | Optional flags; either true prohibits verified=true |

The paired schema intentionally cannot ingest a single side, mix sportsbooks or silently substitute spread/run-line prices. The source's two sides must correspond to the same full-game settlement rules. Postponed starts may be appended as new quotes; old pending notifications expire on that change. Resumed or ambiguous games should be excluded upstream.

`source.verified` is an assertion supplied by a trusted acquisition process, **not a verification performed by this module**. A string or boolean cannot establish executable availability. Keep it false for public aggregators, scraped archive data and sources without a reliable current quote check. Raw acquisition evidence should be retained with its source URI and content hash.

Every accepted quote is content-addressed by `quote_id`; exact reimports are idempotent. The server capture time is stored separately from the supplied observation time. Models, quotes, predictions, decisions, outbox items, dispatch claims, delivery attempts and settlements prohibit SQL updates and deletes through triggers. This is an operational audit log, not protection against an administrator rewriting the database.

## Prediction schema and signal policy

```json
{
  "event_id": "stable-event-id",
  "model_id": "immutable-model-version",
  "artifact_sha256": "64-character-lowercase-SHA256",
  "cohort_id": "preregistered-forward-cohort",
  "probability_home": 0.55,
  "generated_at": "2026-09-08T18:00:01Z",
  "feature_cutoff_at": "2026-09-08T18:00:00Z",
  "market_quote_id": "quote_id-returned-by-ingest"
}
```

`artifact_sha256`, `cohort_id` and `market_quote_id` are optional for exploratory imports. They are needed for the relevant evidence gates. A market-conditioned model must bind the exact quote used for its market baseline. Registrations with `market_conditioned: true` or `baseline: "paired_fanduel_no_vig_moneyline"` require `market_quote_id`; any provided quote ID must match the latest snapshot. The repository prediction runner always provides it. A `research_status` claim inside a prediction never promotes the model.

The module calculates no-vig home probability as `(1 / home_odds) / (1 / home_odds + 1 / away_odds)`, and side EV as `model_probability * decimal_odds - 1`. It selects the side with the higher EV, then applies the fixed execution policy:

- Quote age at most 90 seconds and prediction age at most 15 minutes; future clock tolerance at most five seconds.
- Open, pregame market; prediction and capture must precede first pitch for forward scoring.
- Two-sided overround from 0% through 8%.
- Selected side decimal price from 1.20 through 6.00.
- Selected side estimated EV at least 3%.
- Feature cutoff no later than prediction generation.

Configuration can tighten these limits. It cannot relax them beyond `config/monitor.json`. An absent, stale, suspended, started or mismatched quote produces `BLOCKED`. Otherwise, an unproven model or unverified quote produces an explicit `PAPER` record. Only a reviewed, prospectively validated, matching artifact and verified quote can produce `ALERT_CANDIDATE`.

One outbox item is allowed per event for the lifetime of the ledger. Exact prediction reimports return the original decision. Later attempts do not create repeated signals. An outbox item expires after at most 60 seconds, sooner if the original quote becomes stale or first pitch arrives. A change to either price, event time, status or live state invalidates the pending item permanently, even if the line subsequently returns. An unchanged fresh heartbeat does not extend its expiry. No repricing retry creates a second signal in this conservative first version.

## Registering a forward cohort

A useful prospective record requires registration before data collection begins, while the model is still unproven:

```json
{
  "model_id": "frozen-research-v1",
  "research_status": "unproven",
  "artifact_sha256": "64-character-lowercase-SHA256",
  "baseline": "paired_fanduel_no_vig_moneyline",
  "trial": {
    "cohort_id": "forward-v1",
    "protocol_sha256": "64-character-lowercase-SHA256",
    "model_frozen_at": "2026-09-08T12:00:00Z",
    "starts_at": "2026-09-09T00:00:00Z"
  }
}
```

Hash strings above are placeholders, not valid input. Supply hashes of the actual immutable artifact and protocol. Register after freezing the model and before the trial starts. Registration also binds the monitor policy. New registrations store `trial.policy_sha256`, covering every monitor configuration field except `webhook_enabled`; changing delivery transport does not change the statistical policy. Decisions retain both the complete configuration hash and this policy hash. Older immutable registrations containing `trial.config_sha256` retain their original full-configuration binding, including transport; they are not silently reclassified.

Predictions must match the artifact, cohort and policy. Any model, decision policy or feature change requires a new version and forward cohort. Exact registration reimports remain idempotent after the trial starts. Store raw feature inputs with their actual availability timestamps; this ledger cannot establish the availability of features it never observed.

Promotion uses a new immutable registration with `research_status: "prospectively_validated"`. Its `evidence` object must contain report/protocol URIs and SHA-256 hashes, `reviewed_by`, `reviewed_at`, `model_frozen_at`, prospective start/end timestamps, matching `artifact_sha256`, `n_events` and `n_settled_bets`. It must satisfy the protocol's gates:

- At least 1,000 settled paper bets and 90 days; event count cannot be below settled-bet count.
- Explicit true flags: `forward_only`, `verified_entry_quotes`, `verified_prestart_closes`, `immutable_predictions`, `fixed_analysis_checkpoints`, `data_quality_passed`, `frozen_model_and_policy`, `multiplicity_corrected` and `approved_for_alerts`.
- `confidence_level` at least 0.975, below 1; `execution_net_winnings_haircut` at least 0.02.
- `roi_after_haircut_ci_lower > 0`, `no_vig_close_ev_ci_lower > 0`, and `paired_log_loss_delta_ci_upper < 0`.

These are enforced metadata gates, not an automatic statistical audit. A reviewer must verify the referenced evidence and cohort before asserting the flags. The module does not independently recompute confidence intervals from a claimed report or certify an uploaded report's contents. No such evidence currently exists for this project.

## Notifications

`outbox` defaults to JSON output and sends nothing. PAPER items never go to a webhook. For an eventual approved candidate-only integration, the operator must both set `webhook_enabled` in a local config and supply `BETTING_ALERT_WEBHOOK_URL` through the process environment. Then `outbox --send-webhook` explicitly attempts delivery. Never commit the webhook URL or credentials. No webhook has been configured or contacted by this work.

The sender rechecks expiry, current pricing, settlement status and the decision policy immediately before sending. A policy change suppresses the old pending item; changing webhook transport alone leaves a new-policy item intact. An atomic append-only dispatch claim permits at most one network attempt per outbox item across workers. The outbox ID is also sent as an idempotency key. A timeout is ambiguous, so this version does not retry it; the delivery ledger records the failure type without leaking URL credentials. A process crash after claiming can lose a notification. This favors preventing duplicates over guaranteed delivery. The recipient should still verify the current offer before taking any action.

## Settlements and scoring

A settlement requires `event_id`, `status: "final"` or `"void"`, `settled_at`, a verified result `source`, and boolean `home_won` for a final. Use official MLB results and verify event identity. A final cannot precede the event start. An explicitly verified cancellation may be recorded as a void before start; it cancels a pending notification. Void records return zero hypothetical profit and do not enter ROI/log-loss denominators. Exact reimports are idempotent; conflicting results require an explicit audited correction process outside this first version. Reports requested as of an earlier time exclude results that had not yet been recorded in the ledger.

The automatic forward grader accepts only an ordinary `Final` with explicit regular-season, nine-inning, non-doubleheader metadata, at least nine innings, integer untied scores and official team IDs matching the recorded quote. Shortened, postponed, resumed, cancelled and unclear games remain unresolved until their grading rules and identity are established. The runner requests official linescore metadata; a missing score or required field never becomes a guessed result.

`report()` separates selected signals by model, artifact, cohort and forward eligibility. Synthetic, historical, unverified or unregistered records are marked excluded from forward evidence. Results are never pooled across models. Returns assume one unit at the quoted price and are hypothetical; there is no fill record.

`report()["all_forecasts"]`, also available as `forecast_report()`, scores the earliest eligible captured pregame prediction per model/artifact/event even when its EV is below the betting threshold. Bet-selection gates (EV, selected-side odds and event signal deduplication) do not alter this probability-scoring population. Structural paired implied probability must lie from 1.00 through 1.25, matching the historical all-game dataset; the stricter 8% vig rule still applies to betting signals. Stale, live, missing, mismatched and post-start observations remain excluded. This allows zero-bet runs to accumulate log loss and Brier scores. It reports paired model-minus-market loss deltas and separates `verified`, `aggregator_observational`, `synthetic` and `historical` source classes. These descriptive results do not promote a model. An observational aggregator comparison is useful research, but it does not establish executable returns or verified CLV.

CLV requires a same-book, same-event, verified, open prestart snapshot observed during the final five minutes before the recorded start, captured before start and within 90 seconds of observation. Historical backfills, live lines and unverified snapshots cannot produce CLV. The latest qualifying snapshot is a documented closing proxy, not proof of the final tradable tick. Missing closes remain null and their coverage is reported separately.

For the selected side:

| Metric | Formula | Positive means |
|---|---|---|
| Signed probability CLV | Closing no-vig probability minus entry no-vig probability | Market moved toward the selected side |
| Price CLV | Entry decimal price / closing decimal price − 1 | Entry price exceeded closing price |
| No-vig closing EV | Entry decimal price × closing no-vig probability − 1 | Entry exceeded closing fair value after removing closing vig |
| Paired log-loss delta | Model loss minus entry market loss | Worse model loss; improvement is negative |

Price CLV alone does not remove the bookmaker margin. Promotion requires positive no-vig closing EV as specified in the protocol. Full-universe forward forecast loss and selected-signal loss are reported separately; do not substitute one for the other.

## Operating process

Collect paired public observations and retain raw responses, source hashes and capture times. Map events to official MLB game IDs before resolving outcomes. Complete feature acquisition before capturing the quote used for its market baseline, then append the bound forecast and export the outbox/report. Preserve the same ledger across runs; starting an empty database resets event deduplication and destroys continuity.

Start with the frozen lagged workload/travel model. A future pitcher-scratch, lineup or weather model needs timestamped source collection and its own forward cohort; adding a news parser alone does not establish an edge. Recompute after material new information and fresh quotes, but never silently change the model in an existing trial. Obtain verified prestart snapshots for CLV and official final results for scoring. Keep unverified aggregator monitoring observational until current executable FanDuel acquisition is established.

## Durable forward runner

`python -m beating.forward` remains an observational, manual cycle. It does not enable a schedule, register a prospective trial, send a webhook or place a wager. All current artifacts remain unproven. Its state is now `state/forward.sqlite3`, with a complete durable export at `forward-data/forward.sql`. The same model registrations, event deduplication and first-forecast history persist across New York calendar dates. A fresh runner restores that export atomically; a failed restore cannot publish a partial database. The local state and shared export directory each have an exclusive writer lock. The shared `.forward.sqlite3.lock` is covered by the repository's existing SQLite ignore rule.

Old `YYYY-MM-DD.sql` archives and daily SQLite databases found in the configured state directory remain separate legacy evidence. A daily database that was never exported is discovered and exported on the next successful cycle. Events already observed in these ledgers receive `event_in_legacy_ledger` rather than being counted again in the new cumulative ledger. Their outstanding results continue to be graded. No historical model registration or evidence eligibility is silently merged or changed. The forward report now has `cumulative` and `legacy_days` sections; do not add their populations together without a separate overlap audit.

Model-file, feature-acquisition and quote-collection failures block new predictions while existing outcomes are still fetched, graded and reported. `live-status.json` distinguishes `observation_error` (including its phase), `settlement_error` and legacy-ledger errors. Feature files remain dated daily snapshots; a changed schedule or stale/incomplete feature snapshot still blocks the affected forecast.

Keep one persistent state directory, or restore a fresh one from the latest export. Do not alternate older state directories against a newer shared archive: an existing local database is authoritative and is not automatically reconciled with external edits. Locks coordinate writers sharing a filesystem, not independent machines or Git branches. Preserve the state/export together and use one external workflow writer. The SQL snapshot grows with the append-only history; no retention, remote backup or paid hosting is configured.

A fifteen-minute polling interval cannot guarantee collection during the five-minute closing window or delivery within a sixty-second notification lifetime. Fresh quote verification and an appropriately frequent, monitored acquisition process remain necessary before any eventual alert integration.
