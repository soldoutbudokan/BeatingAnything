# NHL shots-on-goal dispersion — September 26, 2026

**The fixed dispersion correction modestly improved forecast accuracy, but did not identify profitable bets.** Across 3,380 graded props, log loss improved from 0.680894 to 0.679741. The 12 selections include 11 graded bets (3 wins, 8 losses, −4.3544 units after the winnings haircut) and one unresolved outcome. Even grading that unresolved bet as a win leaves the full cohort negative. No betting edge is demonstrated.

## Frozen forecast and actual prices

The [hypothesis card](../docs/hypotheses/hockey-shots-count-dispersion.md), script and [forecast freeze](nhl-shot-dispersion-freeze-2026-09-26.json) were committed in `dfaf458` before target grading. Forecasts were frozen at `2026-09-26T20:25:30.737844+00:00`; their SHA-256 remains `e44bb37cdad1bae8b1ede7dd05a0419169c11b4e0677e89f320822b17169b9c2`. No parameter or selection changed after results.

The mechanism was that variable ice time, possession and game state make player shot counts more dispersed than a fixed-rate Poisson. For each paired FanDuel main line, the model keeps the mean implied by its normalized Under probability and replaces the Poisson shape with a negative binomial. Dispersion uses the player's previous 80 regular-season appearances, at least 40, with fixed shrinkage and cap. Each history date plus 72 hours must precede the quote; the current game is excluded. This is a hypothesis about the sportsbook's distribution, not evidence of its actual pricing method, and may double-count dispersion already priced.

The [new raw-price archive](new-derivative-source-search-2026-09-26.md) supplies actual paired American prices from 33 irregular dates. The [independent sporting source](nhl-shot-outcome-source-2026-09-26.md) supplies NHL IDs, shots and scheduled starts. The model produced 3,419 forecasts across 270 games; 39 have no matched player box row and remain unresolved. One previously inspected source-debug game was excluded before forecasting. Source errors, unresolved identities and insufficient history were retained in the attrition record rather than filled with substitutes.

Identity clarification: forecasts use a globally unique normalized full-name-to-NHL-ID crosswalk and independently matched fixture teams/start. They do not claim verified pregame player-team membership. Postgame roster presence is not an eligibility filter. This preserves the 39 missing outcomes, including one selection, instead of selecting the cohort using realized participation.

## Forecast results

Lower loss is better. Changes are model minus the paired, proportionally normalized FanDuel probability. Intervals resample whole games and are exploratory, unadjusted for the project's prior searches.

| Period by event start UTC | Forecasts / graded | Market log loss | Model log loss | Paired change, 95% game-bootstrap interval |
| --- | ---: | ---: | ---: | ---: |
| Before January 1, 2025 | 1,852 / 1,827 | 0.677488 | 0.676273 | −0.001215 [−0.002305, −0.000172] |
| January 1 onward | 1,567 / 1,553 | 0.684900 | 0.683821 | −0.001079 [−0.002410, +0.000256] |
| Pooled | 3,419 / 3,380 | 0.680894 | 0.679741 | −0.001153 [−0.001993, −0.000296] |

Pooled Brier change is **−0.000570**, interval **[−0.000984, −0.000148]**. The later period has the same favorable direction, but its uncertainty includes no improvement. Mean dispersion alpha is 0.03848; 1,023 forecasts retain the market probability exactly. No fitting or model choice used either period's target outcomes. Both periods nevertheless come from one retrospectively published archive, not independent prospective evidence. The UTC split includes Ryan Strome's December 31 local fixture in the later period.

## Selected returns

The fixed rule selected at most one bet per game, maximum modeled EV, with at least 3% EV **after a 2% haircut to net winnings**. All 12 selections are Unders at actual prices +120 to +154; seven concern Stefan Noesen. Average forecast EV was +6.50%, which was not realized.

| Period | Selected / graded | Wins / losses | Known profit | ROI on graded bets only |
| --- | ---: | ---: | ---: | ---: |
| Before January 1 UTC | 5 / 5 | 0 / 5 | −5.0000 units | −100.00% |
| January 1 onward | 7 / 6 | 3 / 3 | +0.6456 units | +10.76% |
| Pooled | 12 / 11 | 3 / 8 | −4.3544 units | −39.59% |

The unresolved selection is Stefan Noesen Under 1.5, January 14, game `2024020695`, at +134. It remains selected and unresolved; no missing player is silently assigned zero shots. Over all 12 selected stakes, treating it as a loss or as a full winning settlement gives **−44.62% to −25.34%**. Treating it as void gives −36.29% over all selected stakes, or −39.59% over the 11 nonvoid stakes. Overall settlement-specific ROI remains undefined until its treatment is established. Even the most favorable outcome cannot make the cohort profitable.

The graded-only return interval is −100.00% to +21.36%, and the later graded-only interval is −63.73% to +86.23%. These tiny samples and the repeated-player concentration limit the intervals; an all-loss sample's degenerate bootstrap interval is not certainty about the true win probability. The later period becomes −5.06% when its missing selection is counted as a loss. It must not be advertised as a profitable replication by omitting the unresolved bet.

## Checks, limits and reproduction

Independent review matched all 3,419 rows to their original raw FanDuel pairs and fixture metadata, verified 287 price/script/forecast hashes, and checked the distribution, history cutoff and selection arithmetic. A separate stdlib calculation reproduced every graded status/profit and the aggregate log-loss/Brier results within 1e-12. Market updates precede the conservative start by 40.1–805.78 minutes. The minimum gap from the latest allowed history availability to entry is 13.66 hours. A metadata-only participation check found the same 39 missing players before grading; it did not remove them. Three numerical/price tests were added, including the negative binomial's geometric closed form; all 312 repository tests pass.

Raw payloads have market update clocks but no original collector receipts or accepted fills. NHL tables were published retrospectively in 2026 and do not certify historical stat revisions. Exact historical jurisdiction and void terms are unverified. Game-cluster intervals do not fully capture repeated-player dependence or broad hypothesis-search multiplicity. These limitations apply even to the favorable forecasting result.

The [machine-readable results](nhl-shot-dispersion-2026-09-26.json) and frozen source hashes are tracked. Raw prices, full forecasts and grades remain local under `data/raw/nhl-shot-archive-2026-09-26/`. `tools/explore_nhl_shot_dispersion.py --phase forecast` refuses to overwrite the original freeze. To reproduce grading with the retained files:

```bash
state/runtime/research-venv/bin/python tools/explore_nhl_shot_dispersion.py --phase grade
```

Verify the script against its frozen SHA-256 before replaying; the grade phase checks price, sport and forecast hashes. Preserve the original result timestamp rather than representing a replay as a fresh test. The exact selection model is finished without retuning. The forecasting improvement is a research observation, not a promotion, alert or wager.
