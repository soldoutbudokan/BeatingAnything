# NHL goal probabilities from shot prices and prior conversion

September 26, 2026. This fixed exploratory model is declared before computing shooting-conversion histories, new probabilities, selections or target grades. A metadata-only overlapping-price census was assigned first with the rules below; no sporting values enter it. The archive and candidate periods have been inspected in previous research and are not an untouched holdout.

**Pricing hypothesis:** a goal market may reflect recent finishing or scorer demand more strongly than sustainable conversion of anticipated shot opportunities. Use the actual paired shot market to anchor opportunity and a shrunken prior shooting rate to predict goals. Whether this improves FanDuel's goal forecast is unknown. This is a new cross-market forecast, not a modification of the closed shot bets, power-play multiplier or Anytime-versus-goals contract screen. No claim about the bookmaker's implementation is presumed.

The [NHL glossary](https://www.nhl.com/info/hockey-glossary) includes goals among shots on goal and defines shooting percentage as goals divided by shots. The stochastic thinning model below is our approximation; goals and shot quality need not be independent in reality.

## Fixed prices and source gate

Use the original 285-file NHL archive at `ldinan-git/sports-betting-ops@42cf1f81bc302642ddcc9e88ce2e98c1057bc74d`, preserving all raw hashes and quota errors. Use one unique FanDuel book object, a paired literal `player_goals` line 0.5 and a paired literal `player_shots_on_goal` half-point line 0.5–8.5 for the exact same literal player. Both pairs require one Over and one Under, valid American odds with absolute value at least 100, and overround [0,.15]. Reject duplicate markets and duplicate/conflicting sides. If multiple shot lines qualify, choose the line closest to balanced proportional no-vig probability, then the lower line, **before** joining goal offers.

Require **exactly equal goal and shot market update timestamps**. That shared update is the assumed entry clock, in the 72 hours strictly before the earlier provider/independent scheduled start. Unique full-name-to-NHL-ID and ordered-team fixture matching follow the existing metadata sources. Exclude original debug game `2024020345`, unresolved identities and fixtures; use no target-box participation or current roster filter. If duplicate event/player records exist, keep the earliest eligible entry with deterministic source-path ties and reject conflicting same-time values.

Use the original conservative-start UTC split at `2025-01-01T00:00:00Z`. Require at least **100 distinct qualifying games in each period** before any new performance join, and again after prior-history eligibility. Do not relax equal clocks, names, lines, periods or that minimum to rescue coverage. Count each game once. Source/provider timestamps are retrospective timing assumptions, not original receipt, suspension, accepted-fill or jurisdiction evidence.

## Prior history and fixed probability rule

Retain the exact existing SportsDataverse NHL player-box, roster and schedule pins used by the completed source audits. No new downloads or outcome-source substitutions. For histories use regular-season type-02 skater rows with position C/L/R/D, valid positive ice time, unique game/player identity, and a unique independent regular-season schedule entry marked OFF or FINAL. A game's **independent UTC start plus 72 hours** must be strictly before entry; exclude the target game explicitly. Sort by availability, game ID and player ID across teams. The delay is an operational assumption for retrospective statistics, not a proven original release time.

For each offered player take the latest 80 such appearances, require at least 40, and validate all selected counts as finite nonnegative integers with `0 <= goals <= shots_on_goal`. An invalid selected history excludes that price row; do not substitute zeros or selectively fill from older rows. The latest prior team's abbreviation must match one of the target fixture's two clubs. Treat Arizona/Utah as distinct codes; prior individual appearances across clubs can otherwise remain. Current target appearance and actual minutes never determine forecast eligibility.

From the completed 2023–24 regular season only, compute league conversion `r = sum(goals)/sum(shots)` across valid positive-ice-time skater rows satisfying the same count/fixture rules. Report every exclusion and require all these availability bounds before the first candidate entry. This is a fixed prior, not a rate optimized against the candidate sample.

For a player's selected history, let `n` be appearances, `G` total goals, `T` total shots, `m` the sample mean of shots and `v` their unbiased sample variance. Define

`alpha = min(1, max(0, (v-m)/m^2) * (n-1)/(n-1+40))`, with alpha zero when m is zero.

This is the previously specified 80/40-history dispersion estimator, reused without tuning; **the shot-market anchor here is different**. For alpha positive, let shot count `S` follow a negative binomial with size `1/alpha` and mean `mu`; for alpha zero use Poisson. Solve **under that chosen distribution** for the unique positive `mu` giving `P(S <= floor(shot_line)) = q_shot_under`, where q is the actual shot pair's proportional no-vig probability. This preserves the shot-market probability exactly. It does not preserve a Poisson-implied mean while changing the quoted shot probability. Use a bracket [1e-10,1000] and absolute root tolerance 1e-11; unbracketed/nonfinite solutions are explicit exclusions, never repaired using goal prices.

Model finishing probability `p` as Beta with parameters `a=G+100*r`, `b=T-G+100*(1-r)`. The 100-shot prior strength is fixed. Conditional on p and S, use independent Bernoulli scoring on those S shots. The posterior-predictive zero-goal probability is

`P0 = E_p[exp(-mu*p)]` for alpha zero, otherwise

`P0 = E_p[(1+alpha*mu*p)^(-1/alpha)]`.

Compute the Beta expectation using normalized Gauss–Jacobi quadrature at 128 nodes, check against 64 nodes with absolute tolerance 1e-10, and exclude nonfinite/disagreeing cases. No goal-market probability enters mu, alpha, r, a or b. The goal pair's proportional no-vig probability is solely the evaluation baseline and its actual prices determine offered EV. No fitted target-label coefficient, price-driven shooting-rate adjustment, alternate window, side reversal or after-result subgroup.

This model omits game-specific shot quality, named goalie, strength-state mixtures, correlated finishing and opportunity, and changes in role not conveyed by the shot quote. Prior conversion and shot dispersion are noisy. Integrating uncertainty in p avoids equating an uncertain conversion probability with a known rate but does not correct those structural omissions. Improved goal forecasts would support the complete model, not identify the popularity/recency story as a proven cause.

## Freeze, grade and evidence

After the post-history 100-game gates pass, compute every eligible probability and freeze all source/feature/code hashes and selections before joining target goals for grading. Earlier candidate observations may enter later forecasts only under the strict availability rule; the entire archive cannot be described as label-unread. Preserve each prior game ID and the latest availability bound. Existing experiment forecasts, selections and results are not model inputs.

Use a one-unit stake and effective decimal payout `1+.98*(decimal-1)`. Select at most one eligible side per game with decimal odds [1.2,6] and EV at least .03; choose the greatest EV, then ascending numeric player ID, then lexical side. If there are zero selections, close this fixed model without target grading. Do not tune a model to create bets.

For grading, a valid positive-ice-time target row with integer consistent goals/shots settles Under iff goals are zero. A named zero-ice-time row is a hypothetical void only if goals and shots are also valid zero; contradictions or absent/invalid rows remain unknown. Assume full-game goals including overtime and excluding shootout, conditional on the recorded participation convention; exact historical jurisdiction-specific contract terms remain unverified. Retain unknown forecasts and selections with adverse/favorable settlement bounds.

Compare goal log loss and Brier score with the actual paired goal-market baseline. Give each game equal total weight divided across its graded player forecasts. Report all games and each unchanged period, selections, wins/losses/voids/unknowns, raw and haircut unit return, ROI, drawdown and player concentration. Use 10,000 game-bootstrap draws with seed 970026, including zero-selection games, for paired-loss and ROI intervals. Report the number of distinct calendar weeks; game-bootstrap intervals do not resolve shared-player/week dependence in this short archive.

An exploratory lead requires improved later game-weighted log loss with its 95% lower gain bound above zero, plus at least 100 settled selected games in each period, positive haircut ROI and positive 95% lower ROI bounds. Preserve underpowered positives as underpowered. Even passing these retrospective gates cannot satisfy the objective without independent/prospective confirmation, the standing multiple-comparison/forward-evidence requirements, and qualified contract/execution evidence. No wager, alert, notification or scheduled job is enabled.

## Execution boundaries

Commit this declaration before the first performance join. Freeze and independently verify the price overlap first. Stop at a failed source/history/numerical gate; do not rewrite the protocol around the result. Preserve old NHL experiments unchanged. No new source acquisition, thresholds, periods or models are authorized as a recovery of this exact candidate.
