# Market data inventory — September 12, 2026

**The NFL archive contains main game lines, not the niche markets sought in NEXT-STEPS.** The Odds Gap's game-line export has the same limitation. Its separate prop export is a possible sport-side reference, but cannot reconstruct paired FanDuel and Pinnacle prop prices.

## NFL: exact archive recovered and queried

The ignored original data was absent from this checkout. The [v1.1.1 release asset](https://github.com/bobby-king3/nfl-market-movement-tracker/releases/tag/v1.1.1) was downloaded successfully without an account or paid API request. Its **137,375,744 bytes** match the existing pin: SHA-256 `b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c`. This recovers the same historical input; it does not replace it with a newer season. The database is at ignored `data/raw/nfl-source-audit/nfl_odds.duckdb`.

Fresh queries of `raw_odds` found **1,856,036 rows, 38 books, 286 event IDs and 634 distinct capture times**. The complete market list is:

| Market key | All-book rows | FanDuel rows / events | Pinnacle rows / events |
| --- | ---: | ---: | ---: |
| `h2h` | 638,528 | 23,754 / 285 | 16,224 / 285 |
| `h2h_lay` | 28,392 | 0 / 0 | 0 / 0 |
| `spreads` | 601,526 | 23,756 / 285 | 16,224 / 285 |
| `totals` | 587,590 | 23,780 / 286 | 16,224 / 285 |

`h2h_lay` belongs only to Betfair Exchange EU and Matchbook. **No player props, team totals, alternate-line market keys or period markets occur.** At each FanDuel event/capture/selection, spreads and totals have at most one distinct line: changing main lines over time do not form simultaneous alternate-line ladders. The publisher's [versioned configuration](https://github.com/bobby-king3/nfl-market-movement-tracker/blob/v1.1.1/extract/config.py) requests `spreads`, `totals` and `h2h`.

Capture times span **2025-09-04 01:55:38 to 2026-02-09 03:35:37 UTC**; database load times span February 15–20, 2026. The [extraction script](https://github.com/bobby-king3/nfl-market-movement-tracker/blob/v1.1.1/extract/historical_extract.py) retrospectively requests The Odds API history four times daily. Distinct-capture gaps have a **4-hour median and approximately 12-hour maximum**. `captured_at` is the upstream archive snapshot time, `bookmaker_last_update` is the book update, and `loaded_at` is the later database import; there is no original collector reception clock.

There are **1,234 FanDuel rows at or after their own reported start**: 412 moneyline, 414 spread and 408 total rows. These are sparse possible in-play observations, not a usable live trigger series: no score, game clock, status or suspension fields exist. Scheduled starts also change. Do not infer confirmed live execution from the timestamp comparison. **286 raw IDs are not 286 verified games**: the existing [fixture report](../reports/nfl-fixture-feasibility.json) maps all 285 FanDuel moneyline IDs to 285 fixtures; an extra Rams–Commanders ID remains in raw totals. The existing [source investigation](source-search-v2.md) explains this artifact.

FanDuel update age is median **18 seconds**, p99 **92 seconds**, maximum **814 seconds across all raw rows**; before each row's own start the maximum is **334 seconds**, matching the earlier report. No FanDuel or Pinnacle update timestamps are missing or later than capture. Freshness of a sampled quote does not supply the missing hours between samples.

Reproduce the aggregate inventory with DuckDB 1.5.5 available:

```bash
PYTHONPATH=state/runtime/nfl-audit-lib python tools/inventory_nfl_markets.py
```

The output is recorded in [market-data-inventory.json](../reports/market-data-inventory.json). This script only counts markets and clocks; it evaluates no outcomes or betting rule.

## The Odds Gap: two different exports

The original September 8 MLB CSV is absent here. Its recorded hash is `3f433cc28f0a2789dc2dff59f46718ee385181ca9e6fc5e460706fa93585a14e`. Prior measured coverage was **67,902 moneyline rows**, including **3,870 FanDuel rows**, across **193 scans** on September 1–8. Those counts come from the [retained report](source-search-v2.md), not a fresh requery. A current rolling export cannot recover that exact input.

Current [export documentation](https://theoddsgap.com/data), checked September 12, distinguishes:

| Export | Markets and price identity | Timing | Research consequence |
| --- | --- | --- | --- |
| `/api/odds-export.csv` | `ml`, `spread`, `total`; per-book rows | `snapshot_ts` and scheduled `commence_time` | Main game lines; no props, period markets or alternate-line ladders documented |
| `/api/props-export` | Player props; consensus fair Over probability, best Over price/book, quoting-book count; no per-book ladder | First seen, roughly 6 hours out, roughly 1 hour out, last pre-start scan | Cannot isolate FanDuel unless it is the named best book, or recover both FanDuel/Pinnacle sides at a trigger |

Prop history reportedly begins in August 2026; close means the last hourly scan before start. Neither documented export supplies the book-update and game-state clocks needed for live timing. A single bounded prop sample request returned **HTTP 403**; no current prop row counts, market-key list or FanDuel coverage were measured. No access workaround or repeated polling was attempted. [The Odds Gap](https://theoddsgap.com/data).

The public [API documentation](https://theoddsgap.com/api-docs) describes hourly upcoming-game boards and permits attributed personal/assistant reading, while prohibiting feed repackaging and sustained high-frequency/bulk collection. It is not the source for the wide recurring collector without additional permission.

## What this changes

Do not spend further acquisition time expecting NFL derivatives inside this database. It can support specific pregame main-line hypotheses or help align historical book movements, with its coarse sampling made explicit. NFL props, live scoring triggers and tennis game/set markets still require a permitted forward source carrying market identity, both books' prices, source timestamps and separate game-state timestamps. The original Odds Gap MLB file still requires transfer from the original machine if that exact spent experiment is needed; no old holdout or promotion gate changes here.
