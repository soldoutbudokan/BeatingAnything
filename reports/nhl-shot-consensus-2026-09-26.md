# NHL fixed shots consensus — September 26, 2026

**The fixed consensus worsened forecasting loss and lost 11.78% on its five selections after costs. No edge is demonstrated.** Of 1,299 forecasts, 1,290 grade and nine remain unresolved; none of the unresolved rows was selected. The card, code and forecast-hash checkpoint were committed as `9ebeee9` before this model's grading. The archive's outcomes were already inspected in the dispersion test, so this is explicitly exploratory.

Normalized FanDuel log loss is 0.683901; fixed consensus loss is 0.685785. Paired change +0.001884, game-bootstrap 95% [−0.000109, +0.003942]. Brier loss changes 0.245392 → 0.246338; paired change +0.000946. The uncertainty does not establish a population loss difference, and the point estimate supplies no forecasting improvement.

Selected settled bets: 2 wins / 3 losses, -0.5888 units after a 2% net-winnings haircut. Graded/void ROI is -11.78%. Full selected-cohort unresolved loss/void/win bounds are -11.78% / -11.78% / -11.78%. Selection statuses: `{'graded': 5}`. Every unresolved selection stays in these bounds.

| UTC-start diagnostic period | Forecasts / graded | Log-loss change | Selected / wins / losses | Settled units | Full-cohort loss–win ROI bounds |
| --- | ---: | ---: | ---: | ---: | ---: |
| early_nov_dec | 592 / 587 | +0.004030 | 4 / 1 / 3 | -2.0392 | -50.98% to -50.98% |
| later_january | 707 / 703 | +0.000092 | 1 / 1 / 0 | +1.4504 | +145.04% to +145.04% |

January contains just one selected bet. Its identical loss/win bounds mean that its settlement is known; they do not measure sampling uncertainty. The singleton bootstrap interval in the JSON is degenerate and has no inferential value. The five-bet pooled return interval is also very wide: −100.00% to +86.24%.

The fixed forecast is the median normalized Under probability from at least three of DraftKings, BetMGM, ESPN BET and Hard Rock Bet, at the exact FanDuel main player/line. Each reference update is no later than FanDuel and at most 300 seconds earlier. Full [declaration](../docs/hypotheses/hockey-shots-crossbook-consensus.md) specifies margin, identity, fixture, entry, line and exposure rules. There is no sporting-history minimum. At most one bet per game clears +3% EV after costs; ties follow the declared order.

Forecast file SHA-256: `23e65b425d5f7da5b6f07df24145dabff567b7aca3dd2c79c4ab0fc87ca82a24`. Grading verifies the frozen declaration, both code dependencies, prices, identities, schedule, outcomes and predictions. Full attrition, paired intervals and selected exposure are in the adjacent JSON; retained per-row predictions and settlements remain local under `data/raw/nhl-shot-archive-2026-09-26/`.

Independent review reconstructed all 1,299 predictions from the 285 raw files with a separate parser before grading, matching every probability, EV and selection exactly. A separate boxscore join then reproduced every settlement, paired loss, period aggregate, unresolved bound and bootstrap interval within 4.44e−16. All 294 frozen hashes remained unchanged.

Market updates lack receipt/execution proof. Exact historical participation and jurisdiction terms remain unverified. Distinct book keys do not demonstrate independent errors. January and pooled intervals are exploratory and uncorrected for prior searches; do not change the pool, threshold or model in response. No wager, alert or schedule.

Reproduce grading with `state/runtime/research-venv/bin/python tools/explore_nhl_shot_consensus.py --phase grade`; the forecast phase refuses overwrite.
