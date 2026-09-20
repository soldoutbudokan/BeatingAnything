# OddsPapi later-date coverage follow-up

Declared September 19, 2026 (Toronto), before this follow-up's fixture or historical calls. This is source acquisition only, not a strategy test.

## New evidence and question

The user supplied account screenshots showing basketball access and **Pregame enabled / Player Props enabled / Live disabled** for both FanDuel and BetMGM. These are displayed account entitlements; they do not prove an exact first-scorer archive. The original three March fixtures returned no player props. Preserve that result. Do not repeat the denied account endpoint.

Check later calendar windows to distinguish a March-only gap from a repeated coverage problem. The April window is also used in the provider's [player-prop tutorial](https://oddspapi.io/blog/player-props-api-nfl-nba-mlb-odds-python/); May and June extend this source check later in the NBA season. This rationale does not depend on any target price or outcome.

## Fixed acquisition

- UTC half-open windows: April 12–15, May 12–15, and June 4–7, 2026.
- For each window, select the first fixture with sport ID 11 and exact tournament slug `nba`, ordered by zoned start and fixture ID. No availability, price, team, result or status filter. Keep an empty window empty.
- Retrieve all three fixture lists and freeze all selected fixtures before the first history request.
- Request each selected fixture once for `fanduel,betmgm`. Use no outcome/player/active filter, so absence is not created by a market-specific query.
- At most six read-only requests, three documented quota-consuming fixture calls. Reuse the SHA-verified market catalog from the earlier run. Wait at least 2.1 seconds between fixture calls and 5.1 seconds between history calls. Stop on HTTP errors, redirects, oversized responses or credential echoes, without retries.
- Inventory all markets and first-score player timelines, including active pregame entries. Preserve full permitted response bodies, receipt clocks, SHA-256 hashes and original provider labels. Unknown market IDs remain explicit.
- No forecasts, target settlements, strategy returns, purchases, account changes or scheduled jobs.

Use `python -m tools.probe_first_basket_history_followup` for the dry plan and add `--fetch` for the bounded acquisition. The key is read from the existing private local file.

## Interpretation

Actual first-score prices would justify an identity/clock/settlement audit before any replication declaration. If these later windows also contain no props, preserve the negative samples and ask the provider for a concrete historical example or coverage explanation; do not infer that an upgrade would fix it or continue an open-ended date search.
