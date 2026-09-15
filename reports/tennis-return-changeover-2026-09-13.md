# Tennis recovery after a long return game — September 13, 2026

**Decision: sport-side dead: fixed direction/effect threshold failed in this sample.** This new conditional screen uses inspected exploratory data. It does not reopen the completed service-game, tiebreak or concession screens.

The proposed mechanism is that returning through a long game leaves a player more vulnerable on the next serve when the score provides no scheduled changeover. Static next-game pricing could miss this interaction, but no claim about FanDuel's actual model is verified.

## Fixed test and result

The card and definitions were written before computing these four cell rates. A long return game has at least 16 points; a short one has 4–8. Measure the immediately following regular service game in the same set, with at least two games already completed. Odd completed-game count means a scheduled changeover; even means none. First-game side switches, tiebreaks and set transitions are excluded. Every eligible target is included.

The fixed gate requires at least 200 long-return observations per arm, a positive raw no-changeover minus changeover difference, and at least +3 percentage points after subtracting the same contrast after short return games. Short-return games provide a check on serving-order and scoreboard selection; they do not make the comparison causal.

| Preceding return game | Scheduled recovery | Breaks / next service games | Break rate |
| --- | --- | ---: | ---: |
| >=16 points | No changeover | 73/338 | 21.60% |
| >=16 points | Changeover | 52/292 | 17.81% |
| 4–8 points | No changeover | 6477/31267 | 20.72% |
| 4–8 points | Changeover | 5395/28610 | 18.86% |

- Long-return raw difference: **+3.79 pp** (descriptive 95% interval -2.44 to +10.01 pp).
- Short-return difference: **+1.86 pp** (descriptive 95% interval +1.15 to +2.56 pp).
- Difference-in-differences: **+1.93 pp** (descriptive 95% interval -4.30 to +8.16 pp).

Uncertainty combines all four cell contributions within each match. These exploratory normal intervals have no multiplicity correction. All year, surface and preceding-return-result splits are in JSON; none replaces the fixed whole-sample decision.

## Coverage, timing and limitations

The unchanged complete-match parser accepted 3,250/3,337 matches and 84,108 regular service games, dated 20200103–20260521. Exclusions and source hashes are in JSON. The sample is curated men's singles, not a tour census or a representative Challenger sample. Complete-match selection excludes some retirement and interruption tails.

[ITF rules 10 and 29](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf) establish odd-game changeovers, a normal maximum of 90 seconds and no rest after a set's first game; set breaks are different. The data establishes point order and score before the target game. It has no actual rest-duration measurements or complete record of medical/weather delays. Event-specific timing exceptions are not separately verified. Consequently, this tests the standard scheduled-changeover proxy and cannot isolate the physiological effect of measured recovery.

Changeover opportunity is tied to score parity and serving order. Player strength, whether the preceding return game was won, score path, rally intensity, end-of-court conditions and unrecorded pauses may differ between groups. Point count does not measure elapsed exertion. A negative result closes this specification, not every possible fatigue mechanism; a positive subgroup is not a license to reverse or retune the rule.

## Book-side requirement and next action

No FanDuel paired next-game hold/break quotes were supplied, and no return or pricing edge was calculated. Quotes would need the same match, score, next server, just-completed point count, quote clock and independently observed game-state clock. The existing collection configuration has not verified this specific live-market coverage.

This specification failed its fixed screen. Move to another mechanism; do not expand this archive or tune a preferred surface to rescue it.

## Source and reproduction

[Tennis Abstract Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject/tree/2c59eef194967e688b69e73df344184a06322cd8), pinned `2c59eef194967e688b69e73df344184a06322cd8`. Jeff Sackmann and volunteer contributors; source and these derived data reports are [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Noncommercial research only; raw files remain ignored.

```bash
python tools/explore_tennis_return_changeover.py --download
```
