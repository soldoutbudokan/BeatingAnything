# OddsPapi first-basket coverage: completed live check

**The key works, but the fixed sample supplies no first-basket or other player-prop history. No new replication or betting edge is established.**

Run on September 19, 2026 (Toronto; September 20 UTC). [Machine-readable audit](nba-first-basket-oddspapi-coverage-2026-09-19.json).

## Results

The first three NBA fixtures in the predeclared March 2–4 UTC interval were selected by start and ID before any historical prices were fetched. Both books returned HTTP 200 for each game. All returned market IDs reconcile to the saved catalog.

| Game | Start (UTC) | FanDuel markets | BetMGM markets | First-scorer / player-prop markets |
| --- | --- | ---: | ---: | --- |
| Dallas Mavericks vs Oklahoma City Thunder | 2026-03-02T01:00:00.000Z | 113 | 58 | 0 / 0 at both books |
| Boston Celtics vs Philadelphia 76ers | 2026-03-02T01:00:00.000Z | 98 | 56 | 0 / 0 at both books |
| LA Clippers vs New Orleans Pelicans | 2026-03-02T02:00:00.000Z | 107 | 61 | 0 / 0 at both books |

All 493 book/game market entries are moneylines, spreads or totals. Every returned player timeline uses the team/unidentified ID `0`. Catalog market `112604`, **Player First Point**, is absent from all six histories. Its presence in the catalog cannot establish quote availability or identical settlement rules. No player forecasts, target outcomes, strategy selections or returns were computed.

## Access and accounting

The six successful data calls comprise three catalog/fixture calls and three historical calls. The [quota documentation](https://oddspapi.io/en/docs/requests-and-quota) counts the former and exempts the latter. No subscription or account setting was changed and no purchase was made. A first sandbox attempt failed before any HTTP response.

A separate account diagnostic was attempted because all player props were absent. The first attempt reported only a generic failure; a second diagnostic exposed only HTTP status 403. Raw account responses and credentials were not printed or retained. The [account documentation](https://oddspapi.io/en/docs/get-account) describes a per-bookmaker `has_player_props` entitlement, but its value for this key remains unknown. No further account requests or alternate routes were tried.

## Probe corrections and retained evidence

The provider returned one fixture exactly at the upper date bound. The initial parser stopped; the correction excludes that exact boundary while preserving the original half-open interval and first-three rule. The catalog matcher also now excludes first-quarter totals and first-three-pointer markets. These are source-parsing corrections, not changes based on winning outcomes.

The continuation reuses the three original responses only after verifying the fixed plan, expected URLs, HTTP status, byte length and SHA-256 receipts. It refuses cache reuse following a history request and writes the fixture selection before fetching prices. Six successful data calls in total were sufficient; the catalogs were not downloaded twice. The JSON audit retains all six acquisition hashes and receipt paths. Raw data stays ignored.

## Conclusion and next action

This is a negative source check for three games under this key. It does **not** establish that first-basket history is absent provider-wide, that a paid plan is required, or that an upgrade would supply it. Before another acquisition, obtain explicit evidence of historical FanDuel/BetMGM first-scorer coverage under the account and a concrete example fixture. No third-party message was sent. Preserve the profitable but underpowered 2025 experiment and its failed advancement gates. Schedules remain paused.
