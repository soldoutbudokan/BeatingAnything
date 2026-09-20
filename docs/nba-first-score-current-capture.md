# Manual NBA first-score source capture

This captures contemporaneous provider responses for NBA tournament `132` at FanDuel and BetMGM. It makes **at most two requests**, one per book, then exits. It does not run a model, register a trial, create alerts, place bets or enable a schedule.

Run from the repository with the key already saved in the ignored `state/credentials/oddspapi-api-key.txt`:

```sh
state/runtime/research-venv/bin/python -m tools.capture_nba_first_score_current --fetch
```

Omitting `--fetch` prints the plan without network access. Each executed run consumes at most two requests from the existing monthly allowance; it does not buy access. Output goes to a unique ignored directory under `data/raw/nba-first-score-current-capture/`. Do not repeatedly invoke it against the current empty first-score inventory; resume when new relevant prices are available.

## Evidence preserved

Each book's raw body is retained with byte count, SHA-256, UTC request and receipt times, elapsed time and HTTP Date. The inventory keeps fixture IDs, starts/status, native bookmaker fixture/market/outcome IDs, fixture/betslip links, prices, player identities, provider `changedAt`, nullable `bookmakerChangedAt`, bookmaker/market/selection state flags, and every returned market. Missing clocks remain null. Only normalized target market `112604` is highlighted as first point; highlighting does not verify its original settlement wording.

The API's observed request contract differs from its [current documentation](https://oddspapi.io/en/docs/get-odds-by-tournaments): use singular `bookmaker` with exactly one book. A documented multi-book request returned HTTP 400; a separately recorded correction succeeded. The supplied endpoint and tournament filter are otherwise unchanged. The [quota page](https://oddspapi.io/en/docs/requests-and-quota) counts each call as one request.

HTTP errors, redirects, transport failures, malformed responses, scope/identity mismatches, oversized bodies and credential echoes stop the run. No automatic retries or alternate routes. Bodies that echo the key or exceed 32 MiB are not retained. No credentials are printed or included in saved URLs.

## Limits established by the September 19 check

The [actual source check](../reports/nba-first-score-current-availability-2026-09-19.json) finds five FanDuel and fourteen BetMGM NBA fixtures, starting October 20, with **no first-score markets or player prices**. Returned prices are main lines. Thus the request path works, but no first-score snapshot has been acquired by this tool yet. The capture parser was replayed against both actual retained responses; the CLI was tested dry-run and offline without repeating network calls.

Some selections are `active: true` while their containing market is `marketActive: false`. All layers remain separate; `all_provider_open_flags` requires book active, book not suspended, market active and selection active. That combined flag still does not establish a future start, fresh price, complete player field, execution, exact product definition or jurisdiction. It is not a betting-eligibility flag. Every observation remains `source_verified: false`.

FanDuel returned no bookmaker-reported change clock on its 30 main-line selections; BetMGM returned one on four of 88. A provider change clock or local receipt cannot replace a missing bookmaker clock. Original displayed first-basket/first-field-goal labels still need separate evidence once those markets post. The existing source/strategy/prospective gates remain unchanged. No foreground process or scheduled collector is left running after the check.
