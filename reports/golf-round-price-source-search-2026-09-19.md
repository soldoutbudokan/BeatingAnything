# FanDuel historical round-score source search — September 19, 2026

**No additional offer qualifies for G11.** The earlier [18,568-record matchup archive](golf-historical-price-audit-2026-09-19.md) remains useful, but its fixed-cohort matches do not supply a verified cross-course market. This continuation searched the alternative: FanDuel player round-score props.

## Public price leads

An indexed [January 23, 2025 forum post, number 146](https://cappingthegame.com/threads/2025-golf-handicapping-thread.171495/page-3) labels two Farmers round-two selections as FD: Tony Finau under 69.5 at −150 and Shane Lowry under 69.5 at −140. These are self-reported selections with no opposing prices, original bookmaker clock or settlement terms. Round two is outside the fixed first-round cohort.

A [January 31 Pebble reply, number 176](https://cappingthegame.com/threads/2025-golf-handicapping-thread.171495/page-4) says three of four listed round-two score selections were found at FD, without identifying which three. It cannot establish exact bookmaker attribution for each price. Nearby first-round posts either name other books or leave the book unspecified.

Both direct forum downloads returned HTTP 200 **browser-challenge pages**, not article bodies. They were retained as failed captures; no challenge was bypassed. The web-index excerpts are leads, not archived original market evidence. No prices from these posts entered a backtest.

## Provider checks

| Source | Verified scope or restriction | Consequence |
| --- | --- | --- |
| [The Odds API](https://the-odds-api.com/sports/golf-odds.html) | Golf coverage lists tournament-winner futures for the four majors. | Does not supply the target round-score props. |
| [OpticOdds historical endpoint](https://developer.opticodds.com/reference/get_fixtures-odds-historical) | Standard endpoint retains a rolling two months; time series require additional key permission. | Does not establish access to 2023–25 offers. A separate older export would need confirmation. |
| [PropLine](https://prop-line.com/docs) | Documents archive beginning April 2026. | Does not establish target-year coverage. |
| [ParlayAPI](https://parlay-api.com/docs) | Free historical access is limited to 48 hours; deeper history is separately tier-gated. | A free key would not unlock the declared historical cohort. |
| [SportsDataIO golf workflow](https://sportsdata.io/developers/workflow-guide/golf) | Documents golf player/round props and timestamped price changes. | Concrete provider lead; exact FanDuel market coverage and access remain unverified. |

ParlayAPI's [public historical summary](https://parlay-api.com/v1/historical/stats) returned eleven golf entries, all labelled Pinnacle/Pinnacle opening, for April 30 or May 7, 2026. Its own generation timestamp is **May 15, 2026**, despite being retrieved September 19. This stale summary does not prove the absence of current historical prop coverage. Global snapshot counts and advertised archive depth do not establish FanDuel coverage for the target events.

SportsDataIO's [historical integration guide](https://sportsdata.io/help/historical-data-integration-guide) specifically says historical golf odds remain in its production API and that access is controlled through account settings. Its broad archive description is not proof that a particular FanDuel market was captured. No relevant provider key was found in the current environment or workspace `.env`/`.env.local` files. The user was asked whether existing access or another archive is available; no reply had arrived when this report was written.

## Concrete SportsDataIO retrieval route

The public [golf API documentation](https://sportsdata.io/developers/api-documentation/golf) embeds these actual endpoint templates:

```text
https://api.sportsdata.io/v3/golf/odds/json/BettingMetadata
https://api.sportsdata.io/v3/golf/odds/json/BettingEvents/{season}
https://api.sportsdata.io/v3/golf/odds/json/BettingMarketsByTournamentID/{tournamentid}
https://api.sportsdata.io/v3/golf/odds/json/BettingMarket/{marketId}
```

With appropriate access: resolve provider tournament IDs for Farmers 2023–25, Pebble 2023–25 and RSM 2024–25; inspect actual Round 1 market/period labels; select FanDuel outcomes; retrieve full line movement by market ID. Preserve both sides, score thresholds, raw clocks/timezone, player IDs and applicable terms. Calendar-year RSM identities must not be inferred from the provider's season label. The documentation's `StartDate` for a betting event means its last betting day, so it must not automatically replace a golfer's tee time. The [data dictionary](https://sportsdata.io/developers/data-dictionary/golf) also distinguishes actual sportsbook outcomes from consensus outcomes.

Required evidence is **unscrambled archived records for the named markets**, plus timestamp semantics and gross/relative, push/tie, WD and jurisdiction rules. A schema, trial fixture or subscription alone is insufficient. No account was created, purchase made or provider contacted.

## Other bounded leads and retained evidence

- `0xAidan/golf-model`, pinned at `cb868501ec68333a280461cded7b3750c5f87345`, has a complete 1,441-entry tree. Its 602,112-byte `tests/fixtures/golf_2026_one_event.db` contains a tournament named *Fixture Invitational* at *Fixture Country Club*, dated March 1, 2026. This is a test fixture, not a historical price archive. It was inspected read-only and not ingested.
- The alpha-caddie player-map builder reports name-based match methods. It was not used to replace the original audit's unresolved names with unverified aliases.
- Seventeen retained source artifacts passed byte-size and SHA-256 checks. Raw files and extracted API-operation metadata are under ignored `data/raw/golf-round-price-search-2026-09-19/`. The [JSON source record](golf-round-price-source-search-2026-09-19.json) preserves URLs, request/receipt clocks, hashes, the public golf-coverage response and exact missing evidence.

**Next dependency:** existing archive access, a source export with the required offers, or a new independently verifiable public archive. The historical-price objective remains incomplete. No sport screen was reopened, no probability model or ROI was fitted, and scheduled jobs remain paused.
