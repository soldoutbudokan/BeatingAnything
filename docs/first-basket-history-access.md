# First-basket historical access: bounded next check

**No FanDuel edge is established.** The profitable [2025 conditional test](../reports/nba-first-score-wedge-backtest-2026-09-19.md) needs additional price evidence. The [complete 2021 inventory](../reports/nba-first-basket-2021-inventory-2026-09-19.md) cannot supply the required clocks or BetMGM player boards. Eight additional public repositories were checked in a [bounded source search](../reports/nba-first-basket-expanded-source-search-2026-09-19.json), without another qualified first-basket cohort.

## Latest: historical first-scorer coverage found

User screenshots show pregame/player-prop access enabled for both books. The [later-date follow-up](../reports/nba-first-basket-oddspapi-followup-2026-09-19.md) retrieves first-scorer history at **both FanDuel and BetMGM in May and June 2026**, without an upgrade. May has ten matching player IDs active five minutes before scheduled tip-off; June has eight. April has BetMGM-only first-scorer history. The original March negative below is date-specific, not a provider-wide absence. No further account-endpoint request is needed to establish that these examples can be retrieved.

Actual coverage now makes player identity, fixture clocks, complete-board history and bookmaker settlement semantics the next audit. The provider's `createdAt` is still not established as a bookmaker update clock. The prior strategy excludes playoffs and requires ten runners, so do not silently substitute these later examples into its frozen replication rules. A fixed eligible acquisition declaration must precede new outcome grading. The earlier checkpoint below records what was known before the screenshots and later-date queries.

## Live result, September 19, 2026 (Toronto)

The user configured a private local key and the [three-game probe completed](../reports/nba-first-basket-oddspapi-coverage-2026-09-19.md). Both target books returned historical odds with HTTP 200, but **zero first-score markets and zero player-prop markets** appeared in all six book/game histories. Returned markets were moneylines, spreads and totals. This is a negative coverage result for the fixed sample under this key, not evidence that the provider has no first-basket data anywhere.

The catalog includes `112604`, **Player First Point**. Its presence alone does not establish historical prices or equivalent settlement rules. A separate account-entitlement diagnostic returned HTTP 403, so missing archive coverage versus subscription filtering remains unresolved. Do not buy or upgrade based on the catalog or marketing claims; first obtain confirmation that this key can access historical FanDuel/BetMGM first-scorer props and an exact example fixture. No account settings or subscription were changed.

The data check made six successful API requests, with three documented quota-consuming catalog/fixture calls. One earlier sandbox connection failed before a response. The separate account check was inconclusive; two diagnostic attempts were made, the second recording HTTP 403 (the first retained only a generic failure). Credentials and raw account responses were never printed or retained. The key remains in ignored `state/credentials/` with mode `0600`.

## Concrete provider lead

OddsPapi's [historical endpoint documentation](https://oddspapi.io/en/docs/get-historical-odds) describes per-player price histories, active flags and timezone-qualified `createdAt` fields, with retained history from January 2026. `createdAt` denotes provider history-entry creation; it must not automatically be relabelled as a bookmaker update timestamp. This is documentation, not evidence that the desired FD/BetMGM first-basket quotes are present.

The provider's [player-props article](https://oddspapi.io/blog/player-props-api-nfl-nba-mlb-odds-python/) says historical props are available on its free tier and lists FanDuel prop coverage. Its [scanner article](https://oddspapi.io/blog/player-props-value-scanner-python/) lists NBA first basket as a catalog market. Neither verifies historical first-basket coverage for both target books. A price premium over another book is not automatically positive expected value; the articles' marketing claims are not a substitute for a backtest.

The [API overview](https://oddspapi.io/en/docs/api) requires a key. The [quota documentation](https://oddspapi.io/en/docs/requests-and-quota) says each catalog/fixture request consumes one request and historical-odds calls consume none; exhausted accounts can still be blocked. These source pages and hashes are retained locally under `data/raw/nba-first-basket-archive-search-2026-09-19/oddspapi-docs/`. Local key setup and the live result now supersede the earlier access blocker.

## Ready-to-run coverage probe

[tools/probe_first_basket_history.py](../tools/probe_first_basket_history.py) performs a small source check, without fitting a model or grading any outcome:

1. Retrieve bookmaker and market catalogs. Require the literal FanDuel slug; retain BetMGM only if present. Identify basketball player first-score markets by their catalog labels, without assuming identical settlement rules.
2. Retrieve fixtures for March 2–4, 2026. Freeze the first three NBA fixtures by zoned start and ID before requesting prices, without filtering on odds availability or outcomes.
3. Request each fixture's history for the available target books, at least 5.1 seconds between history calls. Inventory literal first-score price entries and their clocks.

The maximum is **six read-only requests, three documented quota-consuming calls**. Every HTTP failure stops the run without retry; redirects are disabled. Responses and acquisition receipts go into a new ignored directory. Credentials are omitted from saved URLs and logs; echoed credentials cause the response body to be withheld and the run to stop. A successful probe establishes coverage only. Player identities, contemporaneous offers, freshness and exact settlement semantics still require verification before replication.

Show the fixed plan without network access:

```bash
state/runtime/research-venv/bin/python tools/probe_first_basket_history.py
```

After configuring `ODDSPAPI_API_KEY` locally, run:

```bash
state/runtime/research-venv/bin/python tools/probe_first_basket_history.py --fetch
```

Alternatively, keep a private key file under ignored `state/credentials/`, restrict its permissions to your user, and pass its path rather than its contents:

```bash
state/runtime/research-venv/bin/python tools/probe_first_basket_history.py --fetch --api-key-file state/credentials/oddspapi-api-key.txt
```

Do not paste a key into chat or put it in a command argument. The probe has synthetic regression checks and the completed live source check above. It does not resume any schedule, send an alert or place a wager.

### Reusing catalogs after a local parsing stop

The live fixture response included a game exactly at the requested upper bound. The probe now excludes that boundary game while preserving its original half-open interval and first-three selection. Its market filter also excludes first-quarter totals and first-three-pointer markets. Neither correction used prices or outcomes to select fixtures.

`--resume-catalogs PATH` reuses the three original successful catalog/fixture responses after verifying their plan, URL, status, byte length and SHA-256 receipts. It refuses a source directory with any attempted historical request. It writes a new receipt and freezes selected fixtures before fetching history, preserving the six-request total without another three catalog calls. The completed run used this option; do not rerun the same sample without a concrete change in access or coverage evidence.
