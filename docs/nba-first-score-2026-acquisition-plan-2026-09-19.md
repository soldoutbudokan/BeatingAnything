# Fixed 2026 regular-season price acquisition

Declared before fetching the cohort's fixture lists or computing prices/selections. This is a source inventory, not a new strategy declaration or an untouched-data claim.

## Rationale and bounds

March 2 coverage samples had no player props. April 12 had BetMGM first-score prices but no FanDuel first-scorer market; May and June playoff examples had both. The old conditional strategy excludes playoffs. Acquire the fixed final regular-season month rather than changing that strategy to include the already-inspected playoff examples.

- UTC interval: March 15, 2026 inclusive through April 13 exclusive, in four successive sub-ten-day queries.
- Include every fixture with basketball sport ID 11 and exact tournament slug `nba`, without filtering odds availability, status, teams or outcomes. Preserve fixture IDs, scheduled starts and external identity links.
- Freeze the entire chronological fixture list before requesting any first-score history. Hard cap 300 fixtures; stop instead of choosing a truncated subset if exceeded.
- Request `outcomeId=112604`, the verified Player First Point / Yes catalog outcome, for `fanduel,betmgm` once per fixture. Keep missing markets in the coverage denominator. Do not retry HTTP failures, redirects, oversized responses or credential echoes.
- Four fixture requests plus at most 300 historical requests. The documented quota charge is at most four requests. Existing per-endpoint cooldowns and 32 MiB response cap remain. This is a bounded manual run, not a schedule.
- Reuse the previously acquired SHA-verified market catalog. Store all permitted responses and credential-free receipt hashes. Inventory source counts only; no player probabilities, score labels, returns or model tuning.

The full cohort may have little FanDuel coverage; preserve that outcome. A usable cohort still needs independent fixture identity, player/starter links, original settlement semantics and justified clock interpretation. Before grading or extending to another season phase, save a separate explicit evaluation declaration. The current comparison family remains 16 until another strategy is declared.

## Explicit missing-history response amendment

The first targeted history call returned HTTP 404 with provider code `NOT_FOUND` and the exact message `No historical odds found for the specified filters.` The run stopped and retained that response. This is an explicit empty-history result, not an authentication failure. Before further requests, amend handling only for this exact endpoint/status/code/message combination: retain it as an absence in the original denominator and move to the next frozen fixture. Do not retry or change its filters. Every other HTTP failure still stops acquisition. Resume verifies all prior response hashes and ordered fixture/filter identities, preserves the original stop result and frozen selection, and continues the remaining cohort within the original total budget.

## Server cooldown amendment

After three explicit absences, request eight returned `429 RATE_LIMITED` with `retryMs=4663`. The preceding history responses took 7.6 and 11.8 seconds; spacing from request start sent the next request immediately after receipt. Correct the client to wait at least 5.1 seconds **after response receipt**, including a 404. Preserve the rejection and allow exactly one resumption of that same frozen fixture after at least the requested wait. No successful request is repeated and no fixture/filter or account is changed. A second rate-limit rejection remains a stop for review. Total attempts still cannot exceed the original 304-request hard cap. This follows the server's stated cooldown rather than evading its limit.
