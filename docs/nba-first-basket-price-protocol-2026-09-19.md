# NBA first-basket price protocol — September 19, 2026

Declared after the fixed 2019–2024 sport screen, before generating forecasts, comparing current-season conditional roles or inspecting strategy returns. Three source-validation outcomes were previously inspected; their game IDs are excluded from primary price evaluation: `202412030DAL`, `202502100OKC`, `202505110IND`. This third-party archive has been studied by its publisher, so the historical analysis is exploratory and no period is represented as independently untouched.

## Hypothesis and fixed candidates

Opening possession materially changes first-score probability. The fixed screen gives `c = 4941/7520 = 0.6570478723` for the opening-possession team. The price question is whether the current likely jumper matchup and possession-specific player roles improve on FanDuel's allocation.

Fit no generic regression and choose no strategy by retrospective ROI. Evaluate both candidates and the market baseline:

1. **Tip adjustment:** preserve FanDuel's normalized player probabilities within each team. Replace its team allocation with `q*c + (1-q)*(1-c)` for the home team, where `q` is the pregame probability of home opening possession.
2. **Tip and role adjustment:** use the same `q` and `c`, but estimate player shares separately when their team wins/loses opening possession. For each candidate player, use the last 50 recorded starts completed before the quote. In each possession state, count that player's first scores `k` and his team's first scores `n` while he started. Shrink toward his current FanDuel within-team share `s` with `(k + 20*s)/(n + 20)`, then normalize across that team's five offered players. Home-player probability is `q*c*share_when_home_possession + (1-q)*(1-c)*share_when_away_possession`; use the symmetric mixture for away players. Missing possession records contribute no role exposure.

Both candidates use the same fixed jumper process. Initialize each player's Elo at 1500; update after a completed historical opening jump with K=24 and the standard base-10, 400-point logistic probability. At each new NBA season label in the source, regress ratings 25% toward 1500 (the source season handles the displaced 2020 calendar). Within each current team, infer possible jumpers from its last ten observed jumps among currently quoted players, plus two pseudo-jumps allocated in proportion to each quoted player's cumulative prior jump appearances (uniform when none exist). Normalize these weights and average Elo matchup probabilities over all home/away jumper pairs. Do not insert the target game's realized jumpers or possession winner.

## Inputs, chronology and eligibility

- Use the hash-pinned archive and source audit's 580 fresh, pregame ten-runner boards. The market is `player_first_basket`; the collector's literal book key must be `fanduel`. Keep the earliest accepted board per game.
- A forecast needs a unique stable player-ID match for all ten quotes. Determine team membership from each player's most recent **prior** roster observation. Require five candidates on each current fixture team; otherwise report the failed join. Do not use target-game roster flags or the publisher's unzoned lineup times for selection.
- Historical jump data cover 2019–2025; role rosters cover 2023–2025. For current-season history, require independently matched ESPN play-by-play completion (`max(wallclock)`) before the quote and source game-date agreement. Exclude same-local-calendar-day histories even if they appear completed. Earlier-season histories end before the priced season.
- Retrospectively collected/corrected historical records are a source limitation, not contemporaneous publication proof. No future target-game labels may enter a forecast.
- Historical records without valid first-score/jump team identities or without matching role rosters do not update role counts. Report attrition. Price eligibility cannot depend on the target winner, target participation, settlement or profit.
- Do not silently repair names, clocks, event mappings, duplicate rows or ambiguous starts. Any implementation correction must preserve the specification and be recorded.

## Fixed price evaluation

Discovery: accepted quotes through **February 28, 2025**. Chronological replication: **March 1–May 12, 2025**. Parameters and thresholds are identical in both periods; no tuning on either period is permitted. Sequentially incorporating already completed earlier games as declared history is allowed. Freeze every probability and bet selection before loading target outcomes for grading.

For each candidate, select at most one runner per game: the greatest expected return after a 2% haircut to net winnings, provided it is at least **5%**. Ties use stable player ID. Allow decimal prices **1.20–26.00**, appropriate to this scorer market; this research range does not change the existing operational betting policy. Report the market's overround, but do not select games on a favorable hold inferred after outcomes. Flat one-unit stakes only. ROI uses all originally selected one-unit stakes, including zero-profit voids; report nonvoid turnover separately.

Grade first score including made free throws. A selected nonstarter is a void under the cited FanDuel convention, not an excluded observation. Use independent ESPN first-score events and source roster starter flags, reconciling publisher outcomes where present. Unknown starter status or inconsistent outcome identity remains unresolved with all-loss/all-void sensitivity; never drop it for profitability. Quote jurisdiction and historical rule version remain unverified, so report returns as historical simulations.

For log loss/Brier, report complete-board outcome coverage explicitly. Score a fixed eleven-category distribution: the ten priced players receive 99% of each model's probabilities and an unlisted-scorer category receives 1%, identically for the market baseline and both candidates. This avoids deleting games when the eventual scorer was unlisted. The 1% reserve is a fixed scoring convention, not a claim that the market quoted an Other selection. Bet EV uses the unscaled, conditional-on-start forecast; unknown lineup/void states remain a limitation. Report a sensitivity with the same reserve also applied to betting probabilities.

Report both candidates in both periods: forecasts, selected bets, wins/losses/voids/unresolved, haircut ROI, weekly block-bootstrap intervals, and paired scoring differences versus the normalized FanDuel baseline. Use 10,000 week-block draws and seed 1729; if fewer than eight weeks are available, do not issue an inferential interval. Add these two declared candidates to the previous thirteen-comparison research family for conservative historical claims: two-sided confidence `1 - 0.05/15 = 99.6666667%`. Preserve old protocols' original results; the expanded allowance does not license repeated retuning.

An exploratory lead requires positive haircut ROI in both periods, at least 50 settled nonvoid bets in each, and improved pooled paired log loss. A claimed historical pricing advantage additionally needs a positive corrected lower ROI bound and negative corrected upper paired-loss bound in replication. These sample gates are triage, not a proof of durability. A positive estimate alone is not an edge.

## Promotion remains separate

There is no general closing-price series in this archive. Actual quote jurisdiction and original odds JSON bodies are missing. Nothing in this protocol enables wagers, alerts or schedules. The prospective requirement remains at least 1,000 settled paper bets across 90 days with fixed models, verified FanDuel entry/closing prices and corrected positive return/closing-EV and scoring evidence. Do not claim that a historical result satisfies those requirements.
