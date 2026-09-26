# NHL shots consensus coverage — September 26, 2026

**A fixed four-book pool supplies at least three timely exact-line references for 1,318 FanDuel pairs across 110 games.** The proposed pool is DraftKings, BetMGM, ESPN BET and Hard Rock Bet. Both 300-second and 600-second age limits produce the same coverage. This choice uses source availability only; no new forecasts, outcomes, returns or price-disagreement scores were computed.

All 285 retained raw files match their acquisition-manifest hashes: 273 event payloads and 12 publisher errors. FanDuel has 3,584 complete main shots pairs across 272 events. Each reference uses the same event, normalized full player name and exact main line, with both literal Over and Under prices. No alternate-line interpolation, alias mapping or reconstructed side is used. Repeated or conflicting pairs are rejected.

| Book | Main-market events | Valid paired lines | Exact FD-line pairs | Later update than FD | Age 0–300s pairs | Age 0–600s pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ballybet | 259 | 2545 | 2182 | 1131 | 1051 | 1051 |
| betmgm | 272 | 3513 | 3261 | 1323 | 1938 | 1938 |
| betonlineag | 273 | 3581 | 3320 | 1672 | 1648 | 1648 |
| betrivers | 247 | 2427 | 2081 | 1138 | 943 | 943 |
| bovada | 173 | 2228 | 2053 | 770 | 1100 | 1230 |
| draftkings | 259 | 3338 | 3090 | 1524 | 1566 | 1566 |
| espnbet | 271 | 3501 | 3252 | 1709 | 1543 | 1543 |
| fanduel | 272 | 3584 | 0 | 0 | 0 | 0 |
| fliff | 270 | 3493 | 3242 | 1816 | 1426 | 1426 |
| hardrockbet | 271 | 3504 | 3251 | 1617 | 1634 | 1634 |
| williamhill_us | 0 | 0 | 0 | 0 | 0 | 0 |

Reference age is `FanDuel market last_update − reference market last_update`. Negative ages are later quotes and are excluded. Increasing the window to 600 seconds adds only Bovada coverage; all nonfuture updates from the proposed four-book pool already lie within 300 seconds. Core coverage by provider-start month: {"2024-11": {"pairs": 18, "games": 2}, "2024-12": {"pairs": 580, "games": 47}, "2025-01": {"pairs": 720, "games": 61}}.

Do not equate distinct book keys with independent forecasts. [Kambi's August 2024 RSI disclosure](https://www.kambi.com/investors/news-pr/kambi-group-plc-and-rush-street-interactive-agree-to-a-multi-year-sportsbook-partnership-extension/) establishes BetRivers' platform/trading relationship, while [Bally's July 2024 announcement](https://s29.q4cdn.com/580102441/files/doc_news/2024/Jul/31/bally-bet-app-maryland-press-release-final.pdf) identifies Kambi as a sportsbook partner. Excluding both from the proposed core avoids counting these brands as separate independent signals. Statistical independence of the four proposed operators is still unproven.

No explicit capture/receipt or book-wide update clock is present. Reference-market timestamps preceding the FanDuel update are necessary chronology evidence, not proof of executable availability. The completed dispersion experiment has already exposed this archive's outcomes; any subsequent consensus test must remain exploratory. This inventory includes all source events and does not apply participant/history filters or the earlier debug-game exclusion.

The adjacent JSON includes per-book timing ranges, unusual-overround counts and cohort counts. The reusable score-free local projection is `data/raw/nhl-shot-archive-2026-09-26/consensus-price-coverage.csv`. Reproduce with `python3 tools/inventory_nhl_shot_consensus.py`. No wager or alert.
