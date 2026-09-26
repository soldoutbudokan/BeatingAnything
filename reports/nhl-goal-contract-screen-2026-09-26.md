# NHL overlapping goal contracts — September 26, 2026

**None of 2,600 eligible same-clock overlaps has positive conditional EV after the fixed winnings haircut.** The 15 higher Anytime prices do not produce a qualifying candidate. Best reference EV is **−0.994%**; the later period's best is **−3.573%**. This exact price screen is closed, with no target outcome inspection by this screen or claim of demonstrated forecasting skill. Earlier experiments inspected outcomes in this archive; it is not an untouched holdout.

The [declaration](../docs/hypotheses/hockey-goal-contract-price-consistency.md) was committed in `9f65d05` after a price-only inventory found same-clock discrepancies but before any EV calculation. The [implementation](../tools/screen_nhl_goal_contracts.py) was committed in `33ab1a7` before execution. It reuses the read-only, hash-pinned fixture/player/paired-goal audit without modifying any older experiment.

## Contracts, timing and interpretation

The independent [contract inventory](nhl-goal-contract-coverage-2026-09-26.md) finds 2,826 literal same-player matches between FanDuel paired goal-0.5 and Anytime Yes across 272 raw events. Among 2,657 with exactly equal update times, 2,638 have equal Over/Anytime prices, 15 have higher Anytime prices and four have lower ones. All 15 higher prices occur in just three events. The other 169 overlaps have unequal clocks, with Anytime later by 2–195 seconds; they are not assumed simultaneous.

The [Odds API market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html) labels the keys as Goals Over/Under and Anytime Goal Scorer Yes/No. [FanDuel Ontario's July 30, 2026 rules](https://d38ayms4az88sz.cloudfront.net/SB/ON/2026-07-30T12-50-49.html), sections22.1 and22.5, ordinarily include overtime in full-game hockey player props, exclude shootout statistics, and void players with no ice time. These support the intended common goal-event interpretation; neither source explicitly crosswalks both API keys to the exact historical2024–25 contracts or proves their jurisdiction. All EV arithmetic is conditional on shared settlement. There is no accepted-fill or original-receipt evidence.

After the existing independent fixture, unique-player, original-debug-game and 0–15% paired-margin gates, 2,768 main-goal pairs remain. Requiring an exact Anytime clock and literal name match removes 168 and retains **2,600 /253 games**: 2,582 equal prices, 15 higher and three lower. The numerical screen does not condition on later participation or sporting outcomes.

## Fixed reference and result

The probability reference is proportional no-vig scoring probability from the paired goal market:

`p_goal = (1/Over_decimal) / (1/Over_decimal + 1/Under_decimal)`

The target is the literal Anytime Yes price, evaluated as `p_goal*(1+0.98*(Anytime_decimal-1))-1`. Only decimal odds1.20–6.00 and EV≥3% could qualify, with one selection per game. This is a same-book market reference, not an independently learned sporting forecast.

| Conservative UTC period | Overlaps | Games | Best conditional EV | Selections |
| --- | ---: | ---: | ---: | ---: |
| Before January1,2025 | 1,444 | 140 | −0.994% | 0 |
| January onward | 1,156 | 113 | −3.573% | 0 |
| All | 2,600 | 253 | −0.994% | 0 |

The best case is William Karlsson on December15,2024: paired goal prices **Over+340 /Under−600**, versus **Anytime+380**, all updated `2024-12-15T15:36:41Z`. The paired reference implies `p_goal=0.2095808383`. Before the declared haircut this implies only about **+0.60%**, falling to **−0.994%** after it. This preserves the favorable raw price difference without treating a same-book reference probability as proof of a small edge. No gate is relaxed to select that one case.

The [JSON result](nhl-goal-contract-screen-2026-09-26.json) preserves every gate/count and source hash. All2,600 row probabilities, literal prices and clocks remain in `data/raw/nhl-goal-contract-screen-2026-09-26/price-reference-rows.csv`, SHA-256 `7c9a310218af4f05b0e6798430f2b8e6cb6979be133e01b44bdbfadfa8d26795`. The runner refuses to overwrite original outputs and never reads sporting outcomes. Forecast loss and ROI are undefined. Do not retune clocks, references, costs or odds limits after this result.

The [independent audit](nhl-goal-contract-screen-audit-2026-09-26.json) passes: 293 source/artifact hashes, all 2,600 literal raw-price/clock matches and all 2,768 base fixture/player/window rows verified. Rational arithmetic agrees within 2.92e−16. The broader 2,657-row raw inventory reconciles through 57 existing exclusions: 10 debug-game, 12 unresolved-fixture, 27 ambiguous-name and eight unmatched-name rows; these remove 56 equal prices and one lower Anytime price. All 15 higher-price cases survive, so exclusion does not explain the negative result. All 312 repository tests pass. No target outcomes, wager or schedule followed the screen.
