# Golf price-source continuation

Checked September 14, 2026 in Toronto; captures occurred September 15 UTC. **Two public historical price samples were found. Neither establishes an edge or supplies a usable historical quote series.** The machine-readable [source report](../reports/golf-price-source-continuation.json) includes request/receipt clocks, raw-file SHA-256 hashes, normalized selections and limitations.

## A complete FanDuel editorial three-ball

A freely accessible [FanDuel Research article](https://www.fanduel.com/research/best-prop-bets-for-the-british-open-championship-first-round-leader-3-balls-and-finishing-positions) contains all three first-round prices for one group at the 2025 Open Championship:

| Player | American odds | Decimal odds |
| --- | ---: | ---: |
| Daniel Berger | +185 | 2.85 |
| Keegan Bradley | +160 | 2.60 |
| Sungjae Im | +200 | 3.00 |

The article explicitly attributes its markets to FanDuel. Its structured metadata gives publication and modification as **2025-07-16T14:07:04Z**, with `isAccessibleForFree=true`. The three reciprocal prices sum to **1.068826**, a quoted overround of **6.8826%**. This is arithmetic on a published example, not measured model value.

The historical bookmaker update time, original group ID, jurisdiction and governing settlement terms are absent. The article is editorially selected and was retrieved in 2026. Its date metadata does not prove the exact text available at a 2025 decision time. Thus it supports price/schema inspection, with **no assigned settlement, ROI or CLV**. No article recommendation or strokes-gained column was adopted as our model.

## PGA wrapper fixtures contain derivative selections

The public [pgatouR repository](https://github.com/WalrusQuant/pgatouR) includes binary RDS fixtures, not just endpoint documentation. Three small odds fixtures and their capture code were retained from tree `74551e5bebc9e189781d75a88d57c68c87ec4860`. The [capture code](https://github.com/WalrusQuant/pgatouR/blob/74551e5bebc9e189781d75a88d57c68c87ec4860/data-raw/capture-new-fixtures.R) specifies tournament `R2026027` and player `46046`; the fixture's betting-profile URL identifies the 2026 FedEx St. Jude Championship.

The [player fixture](https://github.com/WalrusQuant/pgatouR/blob/74551e5bebc9e189781d75a88d57c68c87ec4860/tests/testthat/fixtures/odds_player.rds) contains **14 price rows**. One two-selection round-three market has Scottie Scheffler **-163** and Tommy Fleetwood **+125**, market ID `42.599903063`, and `bettingPeriod=3`. Each quote has its own FanDuel bet-slip URL with market and selection identifiers. The separate catalog also labels its markets `fanduel`. These are stronger attribution evidence than a generic partner link; the price objects themselves have no explicit `book` field, so they do not satisfy the collector's existing ancestor-book-field counter.

The fixture has no original request/receipt or provider quote clock. Its only [file-history commit](https://github.com/WalrusQuant/pgatouR/commit/f99fd279e504313e36718c72a768c3ef1ff8fd90) is dated **2026-08-15T14:12:17Z** and describes recaptured fixtures. A commit date is not a quote timestamp. No jurisdiction or historical tie rule is retained. Two shown selections alone do not prove push-on-tie settlement.

The schema needs care: a three-hole matchup is stored under `GROUP`; a group title and group ID disagree; and a third-round-leader title has `bettingPeriod=1`. Preserve these fields rather than silently reconciling them. The catalog advertises `THREE_BALL`, but this player fixture has no three-ball price rows. The separate GraphQL odds fixture belongs to **R2024003**, so it cannot be joined to the 2026 REST prices.

## Collector follow-through

The [collector](golf-collection.md) now preserves direct selection-link evidence separately from explicit book labels. A link must belong to the price object itself, use the exact FanDuel host and bet-slip path, carry valid market/selection IDs, and agree with any corresponding object IDs. Conflicting book labels remain conflicts. Generic partner links do not qualify. Offline replay of the actual fixture yields 14 price fields and 14 direct selection-link attributions; the explicit-book-field count stays zero. These counters can overlap and must not be added together. Thirty collector tests and the full 205-test suite pass. This fixes the attribution limitation above without supplying missing jurisdiction or historical clocks.

## Search decision

The bounded search used **10 targeted web queries** and retained **12 small public responses**, including repository metadata and capture instructions. It did not discover a representative free FanDuel derivative archive. Search exhaustion here means this bounded search ended; it is not proof that no other source exists.

The [Odds API's own golf documentation](https://the-odds-api.com/sports/golf-odds.html) describes tournament-winner futures for the four majors, with historical access paid. That product's general bookmaker coverage does not establish golf round-market coverage. An unaffiliated aggregation service surfaced, but no permitted golf sample or provenance was established, so its endpoint was not invoked.

A new ordinary request to the public New Jersey rules page returned 403 and was retained without retry. No direct sportsbook or current ESPN denial was retried. Data Golf subscription-restricted tables were not extracted.

**Next source step:** retain actual posted selections through the existing PGA collector, preserving explicit book evidence, market IDs, clocks and terms. A user-supplied lawful book export or an entitled historical archive is another route. Neither sample warrants a return-fitting exercise; future price work still needs representative predecision data and verified settlement.
