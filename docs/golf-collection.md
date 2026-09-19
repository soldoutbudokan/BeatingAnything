# Golf raw collection

The collector supports the exploratory cards in [GOLF-MODEL-PLAN.md](../GOLF-MODEL-PLAN.md) and [NEXT-STEPS.md](../NEXT-STEPS.md). It stores public golf pages, market responses, fields, tee times, leaderboards and weather as received. It creates no model, ledger entries, alerts or wagers.

## Run a bounded capture

From the repository root, using the retained Python 3.12 research runtime:

```sh
state/runtime/research-venv/bin/python -m beating.golf_collect --config config/golf-collection.json
```

The checked-in configuration selects **Biltmore Championship Asheville, R2026557**, from the official 2026 schedule, and its observed public odds page. PGA's default-tournament configuration still selected a completed event during the September 14 check, so the collector does not use that default for Biltmore. Change both `tournament_ids` and `pga_pages` to observed IDs/URLs when moving to another event.

One run performs one cycle, with at least two seconds between request starts, at most 240 requests and a 30-minute elapsed-time budget. Each network timeout is capped at the smaller of 30 seconds and the remaining budget; after each response the budget is checked again. Network timeout handling and writing the final retained evidence can finish after the deadline; an overrun is recorded as `elapsed_time_cap`. No scheduler or background service is installed. For a deliberately bounded hour of collection, run:

```sh
state/runtime/research-venv/bin/python -m beating.golf_collect --config config/golf-collection.json --cycles 12 --interval-seconds 300 --max-seconds 3600 --max-requests 240
```

The first exhausted cap stops the run, so this command may collect fewer than 12 cycles if markets become available and the per-player requests consume the allowance. A request cap counts failed requests too. Hard validation limits cycles to 288, requests to 5,000, elapsed time to one day, tournaments to 10, player requests to 200 per tournament per cycle, request spacing to at least one second and cycle spacing to at least 60 seconds. Configuration keys are documented directly in [golf-collection.json](../config/golf-collection.json).

### Future G11 opportunity: RSM

One official metadata request on September 19 confirms **R2026493, November 19–22, 2026**, with Seaside `776` and Plantation `889`, the course identities in the surviving G11 screen. The [dated source record](../reports/golf-next-price-opportunity-2026-09-19.json) preserves its body hash and receipt clock. This is a calendar/course observation, not proof of future cross-course market coverage or round assignments.

The separate [RSM configuration](../config/golf-collection-rsm-2026.json) is ready for a bounded manual capture **when that event's pre-round markets actually post**:

```sh
state/runtime/research-venv/bin/python -m beating.golf_collect --config config/golf-collection-rsm-2026.json
```

It uses only the existing public API operations and the observed tournament ID; it does not retain Biltmore's HTML URL. It is one cycle, capped at 240 requests and 30 minutes. It has not been run, and nothing schedules it. The current Biltmore configuration remains separate. An appropriately accessible historical archive could supply G11 prices sooner; access and suitable coverage are not established.

The process prints a summary. Exit code 0 means all requested cycles completed without source errors; code 2 means a cap, source failure or interruption occurred. **A successful HTTP response is not evidence that odds exist:** inspect `quote_status`, `explicitly_fanduel_price_field_observations` and `fanduel_selection_link_price_field_observations`. The two attribution counters can overlap and must not be added together.

## Sources and what is actually captured

| Source | Capture | Limits |
| --- | --- | --- |
| Public `www.pgatour.com` tournament odds page | Exact HTML plus a separately hashed extraction of `__NEXT_DATA__`, with each public query key inventoried | Can contain stale widget messages and data for other featured events; retain IDs and query keys. Only the configured ordinary public pages are fetched. |
| `data-api.pgatour.com/odds/interactivity` | Widget configuration and partner link | A FanDuel link does not attribute any quote to FanDuel and does not verify jurisdiction. |
| `data-api.pgatour.com/odds/tournament/{id}` | Available-market catalog with the provider's book labels | A catalog can be empty and is not a set of prices. |
| `data-api.pgatour.com/odds/tournament/{id}/player/{playerId}` | All returned per-player markets and price fields | Requested only when the catalog contains markets, for discovered field/leaderboard/tee-time players up to the configured cap. Not a claim of complete sportsbook coverage. |
| `orchestrator.pgatour.com/graphql` | Tournament metadata, field including withdrawn players and alternates, leaderboard, tee times, outright odds and site weather | Uses the public frontend key documented in pgatouR. Raw compressed payloads are retained alongside decoded JSON. Operations can change without notice. |
| `site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard` | Optional independent PGA sport state, including whatever scores/tee-time fields ESPN returns | **Disabled in the checked-in config:** the current board returned 403 in the first integration run. ESPN event IDs remain unmapped to PGA IDs. `espn_dates` accepts a day or date range; omitted means the provider's current board. |

The API paths and GraphQL field selections follow [pgatouR's public client](https://github.com/WalrusQuant/pgatouR/tree/74551e5bebc9e189781d75a88d57c68c87ec4860), specifically its [API helpers](https://github.com/WalrusQuant/pgatouR/blob/74551e5bebc9e189781d75a88d57c68c87ec4860/R/utils-api.R), [odds functions](https://github.com/WalrusQuant/pgatouR/blob/74551e5bebc9e189781d75a88d57c68c87ec4860/R/odds.R) and [query definitions](https://github.com/WalrusQuant/pgatouR/tree/74551e5bebc9e189781d75a88d57c68c87ec4860/inst/graphql). The [Biltmore odds page](https://www.pgatour.com/tournaments/2026/biltmore-championship-asheville/R2026557/odds) is an independently observed public source. These undocumented site APIs do not grant a data redistribution licence.

`api_enabled: false` disables all PGA API requests while retaining any configured public pages and explicitly enabled ESPN source. Use the checked-in config: a bare CLI invocation has no source enabled and reports a configuration error. `--api` enables PGA APIs, and `--tournaments` selects observed tournament IDs. The bundled PGA key is a public site-client identifier, not an account credential. An optional `PGA_API_KEY` environment override is supported; the key value and sensitive response headers are omitted from request metadata and logs.

The collector does not request FanDuel directly, Data Golf paid tables or Open-Meteo. Its weather source is the PGA site forecast. The ordinary direct FanDuel page check on September 14 returned HTTP 403, and no bypass or retry was attempted. Data Golf paid or membership-only content is outside this collector.

## September 14 source check

**Later result:** the [September 19 capture](../reports/golf-price-capture-2026-09-19.md) is no longer empty: 158 successful requests, 870 recognized price observations with direct FanDuel selection links, and 12 distinct complete two-player matchups. The latter are live same-course offers with unresolved price clocks and terms, not a G11 test. The following September 14 evidence remains a dated record.

The [separate afternoon checkpoint](../reports/golf-price-capture-2026-09-19-afternoon.md), more than four hours later, records R3 official and removal of all ten round-three matchups. It retains 728 recognized observations and two 72-hole pairs, with no R4 tee groups or round matchups yet. Both completed runs and their source hashes remain separate; neither is a pre-round cross-course sample.

The local ordinary requests reached PGA's public page, the correct config host, market catalog, field and tee times. Raw checks are retained locally under `data/raw/golf-source-check/`.

- The correct config endpoint is `https://orchestrator-config.pgatour.com/web-config`. An earlier request to the wrong host/path, `data-api.pgatour.com/web-config`, returned “Missing Authentication Token”; this was not evidence that the correct PGA data endpoints were blocked.
- The field response contained 135 players and 10 alternates, with the source's `lastUpdated` value.
- Tee times had no posted rounds yet. The markets catalog had `availableMarkets: []` and “Odds are unavailable.”
- The public widget linked FanDuel but supplied no actual quote. Its outright widget also said “Tournament complete” while the selected event was upcoming. Those messages are retained as source inconsistencies, not interpreted as completed-event status or successful quote acquisition.

The first capture is useful sport-state evidence, but no FanDuel book-side test is possible until actual prices and their book attribution appear. [The current research summary](../GOLF-MODEL-PLAN.md) should record each subsequent run's observed counts rather than treating this dated check as continuing coverage.

The first collector integration run, `9abd36edec9543b7bcd03fc29659c82e`, retained 10 requests: nine successful PGA responses and an ESPN current-board 403. All three odds responses contained zero recognized price fields. ESPN was disabled immediately within that run and then disabled in the checked-in configuration, so the final default does not repeat the known denial. Successful separately dated historical ESPN research requests do not establish that its current board is reachable.

The final default-config run, `c38cc788393444059c215fa734823953`, completed one cycle with **nine HTTP 200 PGA responses, zero failures and zero quotes**, from `2026-09-15T00:29:51Z` to `00:30:07Z` (September 14 in Toronto). All three successful odds responses again had no price fields; the empty catalog caused player-market requests to be skipped. The field, tee-time state, leaderboard and weather were retained. Both run summaries and response hashes remain under `data/raw/golf-forward/`.

### Additional manual checkpoint

Run `9a4a9d0227b7463bb2829870c2966489` used the unchanged config and explicit `R2026557` from **2026-09-15 02:49:51Z to 02:50:08Z** (September 14, 22:49–22:50 in Toronto), starting 2 hours 19 minutes after the previous run ended. It completed exactly one cycle: **nine HTTP 200 responses, zero failures, 135 field players, 10 alternates, zero tee-time rounds/groups and zero actual price fields**. The public odds page, partner configuration, market catalog, tournament metadata, field, leaderboard, tee times, outright widget and PGA weather each returned HTTP 200. The empty market catalog again caused all per-player market requests to be skipped.

Both explicit FanDuel book-field attribution and direct selection-link attribution remained **zero**. The partner response contained a FanDuel navigation link and `country: CA`, `region: ON`; those fields do not verify jurisdiction or supply a quote. The outright widget still said “Tournament complete” while the official event metadata said `NOT_STARTED`. No usable derivatives appeared, so no price evaluation was performed. Current ESPN remained disabled, no direct FanDuel request was made, and collection stopped after this cycle without scheduling another run.

The [source-check record](../reports/golf-source-check-2026-09-14.json) retains this as a separate `collector_additional_runs` entry with the exact request/receipt clocks, all nine HTTP outcomes and response hashes. All 25 request, raw-body and decoded artifacts passed byte-count and SHA-256 checks; the summary and raw responses remain under `data/raw/golf-forward/9a4a9d0227b7463bb2829870c2966489/`.

## Retained evidence and clock meaning

### Offline market inventory

Once a run has completed, audit it without making another request:

```sh
state/runtime/research-venv/bin/python tools/audit_golf_price_capture.py RUN_ID --report reports/YOUR-REPORT.json
```

The audit verifies retained bytes and hashes, replays REST attribution, deduplicates market/selection identities and inventories complete two-player matchup observations. Both sides must be present in the same body with the same market ID and distinct player/selection IDs. It preserves every pair's original prices, numeric period, displayed title and timestamps; it never picks the best side from separate responses. Official tee assignments and leaderboard state are matched by IDs within the same cycle and must precede the price request. They do not replace a missing bookmaker quote-update time or verify settlement. Detailed output is local `RUN_ID/price-inventory.json`; the JSON report retains summary evidence and complete-pair examples. Its absence of cross-course offers in a single-course event is not a general coverage conclusion.

Output is local and gitignored under `data/raw/golf-forward/`:

```text
index.jsonl                       # append-only records for all runs
<unique-run-id>/summary.json
<unique-run-id>/raw/000001.request.json
<unique-run-id>/raw/000001.body    # response bytes before JSON/HTML parsing
<unique-run-id>/raw/000001.decoded.json  # when extraction/decompression applies
```

Each request and response has SHA-256, byte count and relative filename. Request metadata includes method, exact public URL, operation, variables and safe headers. Response metadata includes HTTP status, safe headers, local UTC request/receipt times and elapsed monotonic time. Bodies use exclusive creation; reruns get unique directories and append records without overwriting old captures. Bodies larger than 32 MiB and decoded compressed payloads larger than 32 MiB stop that source; any retained partial body is explicitly marked `response_size_cap_truncated`.

Clocks are stored by source path with their original value:

- `source_update`: explicit update/issue/timestamp fields returned by the provider.
- `event_or_forecast`: tee times, start dates and forecast valid times; these are not quote update times.
- `page_cache_update`: page-hydration `dataUpdatedAt`; this is not a bookmaker publication timestamp.
- `provider_http_date`: the HTTP server date, kept separately from all payload clocks.

Missing source times remain absent. Receipt time is never substituted for a missing bookmaker clock. Weather period titles such as “9PM” remain raw: they do not establish a forecast issue time or dated hourly observations. This collector alone therefore does not establish the as-issued forecast history needed by G1.

Book fields are preserved verbatim with their paths. Each recognized price field inherits only explicit book labels from its nearest enclosing object with a book declaration; a nested book replaces an ancestor. Conflicting labels do not count as explicitly FanDuel. A sibling catalog entry or generic partner URL does not label a price. The existing `explicitly_fanduel_price_field_observations` counter continues to require explicit FanDuel book fields.

The observed PGA REST player-market schema can instead place a selection-specific `url` beside `oddsValue`, `optionId` and `entityId`, with no book field. The collector records separate `fanduel_selection_link` evidence on that price observation. It requires HTTPS, the exact `account.sportsbook.fanduel.com` host, `/sportsbook/addToBetslip`, one positive decimal-form `marketId` and one positive integer `selectionId`. Credentials, other ports, fragments, whitespace, duplicate/empty IDs and lookalike hosts are rejected. The URL must be in the price object's own `url` field; it is never inherited from a parent, another selection or a catalog. If that object declares `optionId` or `marketId`, each must match the URL market ID; its `selectionId`, when present, must also match. `entityId` remains the publisher's player/entity ID and is not rewritten as a sportsbook selection ID.

Valid link evidence retains its source path, exact URL and IDs. A mismatched ID or conflicting explicit book label is retained with a non-attributed status. Only status `attributed` increments the separate `fanduel_selection_link_price_field_observations` counter. It does not rewrite `book_labels`, verify jurisdiction/settlement, prove a historical quote clock, or establish that a bet is tradable. A price can count in both attribution counters. Links are inspected as text and never opened.

The [public historical pgatouR player fixture](https://github.com/WalrusQuant/pgatouR/blob/74551e5bebc9e189781d75a88d57c68c87ec4860/tests/testthat/fixtures/odds_player.rds) exposed this schema after the empty Biltmore capture. Offline replay recovers **14 recognized price fields, zero explicit book-field attributions and 14 direct selection-link attributions**. Its raw RDS SHA-256 is `f4ddfb1b5bb3082d91aabce1d6ddd5841c043e632e70667692384b8562f2ce3b`. The [source continuation](golf-price-source-continuation.md) explains its missing original quote clock and inconsistent market metadata. The collector fix does not change the earlier zero-price live captures.

The numeric formats accepted for counting are `decimalOdds > 1`, integer `americanOdds` with absolute value at least 100, and signed American strings in the client's `oddsValue` field. Generic `odds` numbers, ambiguous unsigned values and invalid prices are retained under `unvalidated_price_fields`, without incrementing quote counts. Observation counts can duplicate a price across player endpoints or captures, and are not counts of unique markets, selections, settled bets or tradable FanDuel quotes. Unrecognized schemas and complete raw arrays remain available for later exploration.

## Denials, backoff and checks

No redirect, cookie replay, challenge solver, residential proxy or browser impersonation is used. Any HTTP error, network failure or malformed body disables that source for the rest of the run. A 429 retains `Retry-After` and its calculated earliest retry time, then makes **no more requests to that source during the run**, even if another cycle begins. Independent sources may continue. An ordinary GraphQL schema error disables the operation; authentication/access errors disable the GraphQL source. Fix source configuration deliberately before starting a new manual run after a failure.

Tests exercise exact byte/hash retention, clock separation, append-only reruns, denial suppression across cycles, 429 backoff, pacing and session caps, credential-safe metadata, compressed payloads, empty-market behavior, player request caps and explicit book attribution:

```sh
state/runtime/research-venv/bin/python -m unittest tests.test_golf_collect -v
```
