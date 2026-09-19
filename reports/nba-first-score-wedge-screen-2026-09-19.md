# Free throws change first-basket winners in 6.07% of games

[Card 42](../docs/hypotheses/basketball-first-score-free-throw-wedge.md) passes its **sport-side settlement-difference gate**. This is a new mechanism check, not a FanDuel pricing result. Card 41's failed price models remain closed.

The declaration was saved at **23:33:30 UTC**, before downloading or reading the 2024 play-by-play pairs. The [result and source receipt](nba-first-score-wedge-screen-2026-09-19.json) pin its hash and the independent release digest. Among 1,320 source games from October 24, 2023 through June 17, 2024, one has duplicate/invalid play sequence identifiers and stays excluded.

| Fixed-screen quantity | Result |
| --- | ---: |
| Valid games | 1,319 |
| First score was a made free throw | 94 (7.13%) |
| First scorer differed from first made-field-goal scorer | **80 (6.07%)** |
| First free-throw scorer also made the first field goal | 14 |
| Calendar-week blocks | 35 |

The predeclared minimums were 1,000 valid games, 50 different winners and a 5% disagreement rate. All pass. A free throw first does **not** always change the winning player; the 14 same-player cases stay distinct. No player subgroup, forecast, cross-book probability or return was calculated.

## Prices exist; exact historical definitions still need evidence

A separate [outcome-independent coverage check](nba-first-score-wedge-price-coverage-2026-09-19.json) matches the 580 existing FanDuel boards to **214 BetMGM, 443 BetRivers, 357 Bovada and 428 DraftKings games** with the same normalized ten-player set, matching event IDs and prices fresh within five minutes at a joint pregame decision time. These are per-book overlapping counts, not additional independent games or proof of equivalent settlement. Stable-ID and full model eligibility checks would still be required.

FanDuel's [NJ rules](https://www.fanduel.com/fanduel-sportsbook-house-rules-nj) include free throws in first basket. The [July 2024 Gold Strike DraftKings rules](https://goldstrike.com/-/media/GoldStrike/Casino/Sportsbook/Betting-Rules/GS-Sportsbook-DK---Retail-House-Rules-072624-Approved.pdf), PDF page 40, exclude them in **first-field-goal** wagers. These establish two different products. They do not establish that the archive's normalized DraftKings `player_first_basket` values belong to the latter product. A later public tracker classifies DraftKings differently, reinforcing the need to verify the actual historical market rather than infer it from book name. No generic book-to-definition alias was added.

**Next action:** establish the historical reference-market definition and freeze one conversion estimator before any price comparison. Do not average first-score and first-field-goal probabilities directly, count this screen as a new pricing advantage, or call the already inspected 2024–25 periods an untouched holdout. The comparison family remains 15 until another pricing candidate is declared. Additional/prospective price validation is still required.

Reproduce with `state/runtime/research-venv/bin/python tools/screen_nba_first_score_wedge.py` and `state/runtime/research-venv/bin/python tools/audit_nba_first_score_reference_coverage.py`. All **262 tests pass** at this checkpoint. The original declaration remains unchanged; this report carries its executed status.
