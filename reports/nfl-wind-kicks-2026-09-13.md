# NFL wind and long kicks: September 13, 2026

**Fails descriptive magnitude screen.** The fixed >=15 mph screen has 785 exposed eligible drives across 95 games. The season/roof-standardized reduction in successful >=50-yard kicks per eligible drive is -14.4%; the card requires at least 200 exposed drives and a 20% reduction. **The card remains unresolved for its timely pregame trigger, and there is no book-side edge evidence.**

The sample was fixed before kick outcomes were read: complete 2021–2025 regular seasons and playoffs. The canceled 2022 Buffalo–Cincinnati game is excluded if present. A qualifying drive has a valid snap with the ball on the opponent's 40–25 yard lines, inclusive. Attempts and makes are counted separately after the first such snap, within the same `game_id`, `fixed_drive` and offense. Nullified plays and extra points are excluded. Kicks >=50 yards are the primary outcome; all-distance totals below are secondary diagnostics, not a replacement gate.

| Outcome per eligible drive | >=15 mph count/rate | <15 mph rate, season/roof standardized | Relative reduction [descriptive 95% interval] |
| --- | --- | --- | --- |
| long attempts | 62/785 (7.898%) | 8.283% | 4.6% [-25.0%, 30.8%] |
| long makes | 49/785 (6.242%) | 5.456% | -14.4% [-54.1%, 19.3%] |
| all attempts | 286/785 (36.433%) | 37.396% | 2.6% [-7.7%, 12.7%] |
| all makes | 249/785 (31.720%) | 30.844% | -2.8% [-13.7%, 8.0%] |

Low-wind raw sample: 6,249 drives across 732 games, 535 long attempts and 356 long makes. Long-kick success conditional on trying is 79.0% in the exposed group and 66.5% in raw controls. This separates the decision to attempt from observed accuracy, without claiming either is causal. Standardization weights each season/roof control rate by exposed drives; 0 exposed drives lack a same-season/roof comparison. The interval uses 2,000 bootstrap resamples of whole games within exposure/season/roof strata, seed 20260913. It is descriptive and uncorrected for hypothesis selection.

There are 1,424 completed games in the five inputs; 979 have an outdoor/open roof and 152 of those have no recorded wind. The weather-complete sample has 827 games; missing wind is not imputed. Exact season/roof counts, all aggregates and source hashes are in the [JSON report](nfl-wind-kicks-2026-09-13.json).

The [nflfastR source](https://nflfastr.com/) describes game-level weather metadata; it does not supply the weather forecast issue time required by this card. Roof state is also retrospective. Stadium, kicker, season timing and other weather can confound this comparison. Conditioning on reaching the 40–25 band may itself select on weather-sensitive offense; drives skipping that band between snaps do not enter. These rates do not directly price longest-field-goal or total-made-field-goal props.

No FanDuel prices were collected. The current provider catalog documents NFL made-field-goal and kicking-points markets, but does not document a longest-field-goal key; the long-distance result cannot silently become an all-distance pricing claim. A useful next step must establish issue-stamped wind/roof observations and exact available FanDuel kicker markets before testing price disagreement. Do not lower the 15 mph/20% cutoffs or call these inspected seasons a new holdout.

Run `python tools/explore_nfl_wind_kicks.py --download` from the repository. The script verifies the five SHA-256 pins before analysis. Data: [nflverse-data pbp release](https://github.com/nflverse/nflverse-data/releases/tag/pbp), derived from nflverse/nflfastR, [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md); raw files remain ignored. No model, odds backtest or alert was enabled.
