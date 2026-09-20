# First-basket historical access: bounded next check

**No FanDuel edge is established.** The profitable [2025 conditional test](../reports/nba-first-score-wedge-backtest-2026-09-19.md) needs additional price evidence. The [complete 2021 inventory](../reports/nba-first-basket-2021-inventory-2026-09-19.md) cannot supply the required clocks or BetMGM player boards. Eight additional public repositories were checked in a [bounded source search](../reports/nba-first-basket-expanded-source-search-2026-09-19.json), without another qualified first-basket cohort.

## Concrete provider lead

OddsPapi's [historical endpoint documentation](https://oddspapi.io/en/docs/get-historical-odds) describes per-player price histories, active flags and timezone-qualified `createdAt` fields, with retained history from January 2026. `createdAt` denotes provider history-entry creation; it must not automatically be relabelled as a bookmaker update timestamp. This is documentation, not evidence that the desired FD/BetMGM first-basket quotes are present.

The provider's [player-props article](https://oddspapi.io/blog/player-props-api-nfl-nba-mlb-odds-python/) says historical props are available on its free tier and lists FanDuel prop coverage. Its [scanner article](https://oddspapi.io/blog/player-props-value-scanner-python/) lists NBA first basket as a catalog market. Neither verifies historical first-basket coverage for both target books. A price premium over another book is not automatically positive expected value; the articles' marketing claims are not a substitute for a backtest.

The [API overview](https://oddspapi.io/en/docs/api) requires a key. The [quota documentation](https://oddspapi.io/en/docs/requests-and-quota) says each catalog/fixture request consumes one request and historical-odds calls consume none; exhausted accounts can still be blocked. No key is configured, no account was created, and no authenticated request or purchase was made. These source pages and hashes are retained locally under `data/raw/nba-first-basket-archive-search-2026-09-19/oddspapi-docs/`.

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

Do not paste a key into chat or put it in a command argument. The probe has been checked with synthetic responses and run in dry-run mode; **live provider coverage remains untested**. It does not resume any schedule, send an alert or place a wager.
