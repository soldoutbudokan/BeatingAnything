# Proline+ redundant-leg SGP capture attempt — October 23, 2026

**No Proline+ same-game-parlay quote was captured, so no redundant-leg price example exists yet.** The target is the pattern recorded against theScore Bet on October 8 ([census](sgp-rush-receive-2026-10-08/README.md)): adding a leg already implied by the construction raised the quote, in the McCaffrey case from +483 to +854. This attempt looked for the same behaviour on OLG's PROLINE+.

## What blocked it

The cloud session's network policy denied every sportsbook host: `www.proline.ca`, `proline.ca`, `www.olg.ca`, and Kambi's public offering hosts (`eu-offering-api.kambicdn.com`, `ctn-api.kambi.com`). The container proxy answered 403 to each CONNECT, and the web fetcher failed DNS on the same hosts and on `example.com`, so it shares the allowlist. Only GitHub was reachable. No browser surface was available. This is a missing capability, not evidence about Proline+ pricing.

## What was established without access

- Since January 29, 2026, PROLINE+ runs on Kambi's turnkey sportsbook (contract to 2032), replacing FDJ Gaming Solutions. The same-game product is Kambi's Bet Builder. Sources: [Kambi](https://www.kambi.com/news-insights/kambi-ontario-lottery-and-gaming-sportsbook-partner/), [Canadian Gaming Business](https://www.canadiangamingbusiness.com/2026/01/30/olgk-kambi-proline-sportsbook-launch/), [Legal Sports Report](https://www.legalsportsreport.com/253044/kambi-takes-over-in-ontario-as-olgs-sports-betting-partner/).
- Kambi's offering API is public and unauthenticated: `GET https://<host>/offering/v2018/<operator>/listView/<sport>/all/all/all.json?lang=..&market=..&client_id=2&channel_id=1&includeParticipants=true` for a league board and `.../betoffer/event/<eventId>.json` for one event. Odds and lines are integers scaled by 1000; outcome types are `OT_ONE/OT_TWO/OT_CROSS`, `OT_OVER/OT_UNDER`, `OT_YES/OT_NO`. Verified by reading two public Kambi clients ([pdmuinck/kambi-sports-book](https://github.com/pdmuinck/kambi-sports-book), [MadunaCapital/scanner-ingestion-sunbet](https://github.com/MadunaCapital/scanner-ingestion-sunbet)), not against Proline+ itself.
- Unknown and needed: OLG's operator path segment (Unibet Canada is `ubca`; candidates `olg`, `olgca`, `olgon`, `proline`, `prolineplus` are guesses) and the Bet Builder pricing request. Both are visible in the browser network tab while building an SGP on proline.ca.

## Tool

`tools/probe_proline_sgp_redundancy.py` (tests: `tests/test_proline_sgp_redundancy.py`, offline) does the search once the hosts are reachable:

1. `discover` tries each host and operator candidate until the offering API answers.
2. `scan` pulls NHL, NBA, NFL and MLB boards and enumerates base + redundant constructions. Rules are set-inclusion statements on final integer totals: over ladders, under ladders, spread ladders, spread to moneyline and back, participant totals bounding the game total, two team totals bounding the game total, and the theScore pattern (combined-stat over plus one component under forces the other component). Each base gets an unrelated, non-contradictory anchor leg so the base is itself a two-leg SGP.
3. `price` quotes base and base-plus-redundant through the Bet Builder endpoint supplied on the command line and flags any raised price.
4. `record` / `report` hold manual UI captures in the same observation file, with the multiplier change computed.

Run from an Ontario connection, or allow `*.proline.ca`, `*.olg.ca`, `*.kambicdn.com`, `*.kambicdn.org` and `*.kambi.com` in the cloud environment's network settings. Read-only; it never logs in or touches a betslip. Observations, when they exist, land in `reports/proline-sgp-redundancy-2026-10-23.json`; raw responses under `data/raw/proline-sgp-redundancy-2026-10-23/` (gitignored).

Do not repeat this attempt from the same container without a network or capability change.
