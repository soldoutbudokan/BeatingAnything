# Current FanDuel paper observations

`python -m beating.covers --output state` reads [Covers' public MLB odds page](https://www.covers.com/sport/baseball/mlb/odds) and the public MLB schedule. It needs no paid API key or sportsbook login. On September 8, 2026, ordinary requests returned explicit FanDuel home/away moneyline pairs; the page naturally returned CA/ON settings. No location override, proxy or access-control bypass is used.

The capture at 20:49:58 UTC displayed Cleveland +102 / Baltimore -120 for their 22:35 UTC game, and Colorado +290 / New York Yankees -360 for their 23:05 UTC game. Covers displayed a page update of 4:49 p.m. ET. These are observations of the aggregator, with unknown sportsbook jurisdiction and execution status. [FanDuel's own Yankees–Rockies article](https://www.fanduel.com/research/yankees-vs-rockies-mlb-odds-prediction-point-spread-over-under-and-betting-trends-for-9-8-2026) separately showed Yankees -335 / Rockies +270 and an odds update of 4:11 p.m.; the differing timestamps and prices reinforce that sources cannot be treated as synchronized.

## Exact boundary

- Select `table#moneyline-table` and cells whose `data-book` equals `FanDuel`. Parse one American home quote and one American away quote from their labeled cells and moneyline anchors. The page's `data-type` incorrectly says `spread` on moneyline cells, so it is not used to identify the market.
- Match each cell's game ID to a `SportsEvent` JSON-LD object. Its start time includes a UTC offset but uses month-day-year formatting. Ignore rows with no structured metadata; on the observed page this excluded tomorrow's rows.
- Resolve team abbreviations to MLB numeric IDs; require one official schedule game for the date and teams, a matching start within five minutes, regular-season status and no doubleheader ambiguity. Require both the source and official schedule to say pregame, and require the start to remain in the future.
- Record receipt time immediately after receiving the odds response. Preserve the raw response hash, source page update, source line timestamp, schedule response and event identity. A page timestamp over fifteen minutes old blocks new observations. The per-cell line timestamp is retained separately and never interpreted as a heartbeat: an unchanged price may legitimately carry yesterday's timestamp.
- Every emitted quote has `source.verified=false`. Observations are eligible for paper research only. No quote is certified executable, and this collector sends no betting notification.

Covers states that supplied odds may have a small delay. Its generic opening column is from an international sportsbook, not a named FanDuel opener; this adapter never uses that column. The source page update is not proof that FanDuel reaffirmed an individual quote. Manual bookmaker verification remains necessary before any real bet.

## Files and failure behavior

`state/quotes.json` and `state/live-status.json` show the latest result. Each successful fetch also writes a uniquely named compressed HTML response, schedule JSON and observation record under `state/snapshots/`. `state/quote-observations.jsonl` appends every eligible pair for forward analysis. Keep these files between runs; overwriting the workspace loses the prospective record.

Network errors, unexpected HTML, missing metadata, invalid prices, ambiguous matches and nonpregame games yield no eligible observation. A source or schedule file supplied on the command line is an offline parser check and marks quotes historical, so it cannot masquerade as a live collection. The parser depends on `lxml`.

Use a modest polling interval, such as five minutes, and stop on access failures rather than trying alternate identities or locations. A prospective CLV metric may use the last captured eligible pregame observation from this same source, clearly labeled **Covers FanDuel quote at the last observed pregame time**. It is not a certified FanDuel closing line; gaps and timing must be reported.
