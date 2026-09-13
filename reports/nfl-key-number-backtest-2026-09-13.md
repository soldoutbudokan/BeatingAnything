# NFL key-margin price backtest — September 13, 2026

**No eligible bets; ROI is undefined.** The fixed rule sought a one-point better FanDuel half-point spread than Pinnacle crossing a final margin of exactly three or seven. No qualifying price pair was present. This is an executed empty backtest, not evidence of a profitable strategy, a zero-percent return or a negative sporting effect. Park this exact archive/rule combination without adding integer lines, changing the key margins or loosening entry rules.

The new [card 37](../docs/hypotheses/book-nfl-key-number-bridge.md) differs from the earlier identical-line screen: it prices the probability mass between two different half-point lines. The [pre-comparison declaration](../docs/nfl-key-number-declaration-2026-09-13.md) is an exact preserved copy of the original card before its result annotation, SHA-256 `5c30b68015a676fab1c38376d202419a6576d4b2c3fbbc8e5054384360deb953`. No rule changed after inspection.

## Calibration and entry

The fixed 2010–2024 regular-season calibration uses [nflverse's pinned games file](https://github.com/nflverse/nfldata/blob/55430687825bbdd8640d639b9aaaa0d886778e95/data/games.csv). A positive recorded spread means the home team is favored, per the [publisher's dictionary](https://github.com/nflverse/nflreadr/blob/main/data-raw/dictionary_schedules.csv). For each key, the eligible historical closing-spread magnitude is within one point of it. The counted outcome is the favorite winning by exactly that margin, including overtime.

| Key margin | Historical games | Exact-margin games | Estimated mass | Wilson 95% interval |
| --- | ---: | ---: | ---: | ---: |
| 3 | 1,590 | 142 | 8.93% | 7.63–10.43% |
| 7 | 849 | 50 | 5.89% | 4.50–7.68% |

That historical closing-spread mass is only a modeling proxy for the mass at a particular Pinnacle quote. The rule would add it to proportional and power no-vig probabilities, requiring at least +3% expected return after a 2% haircut to winnings under both methods, plus positive return when using the Wilson lower mass. There is no generic team-strength fit.

The existing tested parser requires two unambiguous sides, half-point lines, nonfuture updates at most 90 seconds old and overround between zero and eight percent. Entry is one to 24 hours before the conservative earlier source/scheduled start. The current independently downloaded fixture metadata maps 226 archive events under the exact team/15-minute start check; unmatched events stay excluded. There are 687 eligible FanDuel entry pairs in mapped events, with 252 lacking an eligible paired reference, leaving 435 paired comparisons before the key-margin requirement. **None crosses three or seven.**

A separate price-only diagnostic checked all 526 fresh paired half-point spread observations in the source entry window before fixture filtering. Of these, 455 have identical lines and 71 differ by one point. The midpoint of every one-point difference lies outside three and seven. This confirms that the fixture attrition did not hide an eligible key-margin pair. Integer-line observations were deliberately outside this definition and were not added after the empty result.

## Settlement, limits and continuation

Preparation froze the calibration and zero selected rows before settlement. The settlement phase ran and found zero selected or settled games, zero staked units and no defined ROI, uncertainty interval or closing comparison. Its 50-settled-game gate is unmet. The [JSON result](nfl-key-number-backtest-2026-09-13.json) preserves both clocks, source hashes, calibration, attrition, empty selection and explicit null ROI. The frozen selection hash is `c00e9401768a53f236d55833bf1dd47df8783f9609cd21b641b4b02a1e6091fb`.

The proposed settlement uses the final score including overtime; this agrees with the [current FanDuel Colorado football rules](https://www.fanduel.com/fanduel-sportsbook-house-rules-co), effective July 22, 2026. These current rules do not establish every archived bet's historical jurisdiction, acceptance or treatment. Source snapshots do not prove an executable fill. This already-inspected 2025 season is exploratory evidence, never a newly untouched holdout. No exposure or outcome-based selection is introduced by the diagnostic.

The newly recovered [FanDuel prop archives](../docs/new-prop-archives-2026-09-13.md) now offer a more useful next price-testing path. Continue with declared prop mechanisms and actual prices; do not return to repeatedly screening the same main-line archive.

Run in a fresh preparation directory:

```sh
PYTHONPATH=state/runtime/nfl-audit-lib python tools/backtest_nfl_key_numbers.py --self-test
PYTHONPATH=state/runtime/nfl-audit-lib python tools/backtest_nfl_key_numbers.py --prepare
PYTHONPATH=state/runtime/nfl-audit-lib python tools/backtest_nfl_key_numbers.py --settle
```

Preparation refuses to overwrite a frozen selection. The immutable declaration and both data hashes are checked. `games.csv` has SHA-256 `0c34a519753ada6b5b37f5e8be246021813484adb15ae7c067af9c3aca534d2d`; the odds database retains its existing `b03c4e7f…c344c` pin. Raw inputs remain ignored. NFL schedule/results attribution: nflverse; original odds archive: bobby-king3, collected from The Odds API. Eight bridge/payout checks and compilation pass.
