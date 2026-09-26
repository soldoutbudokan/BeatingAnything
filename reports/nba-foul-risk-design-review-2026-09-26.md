# NBA pregame foul-risk points correction: design review

September 26, 2026. Mathematical and source-design review only. No sporting data, target labels, probability fit, data join, return calculation or network request was used. Root is separately checking the official disqualification rule and source schema.

**An automatic pregame Under adjustment is not justified by a high historical foul rate.** Prior average minutes and points already include historical foul-related losses. A market line based on those averages may include them too. Applying an additional expected foul loss to that baseline can count the same effect twice. An injury-like truncation mechanism does not by itself determine the probability correction at a mean-adjusted points line.

Let `F0(L)` be the probability of scoring at most line `L` without a foul-loss event, and `F1(L)` the corresponding probability with one. If those component distributions remain fixed and the loss is nonnegative under a common counterfactual, then `F1(L) >= F0(L)`. Increasing event probability from `r0` to `r1` gives:

`Delta P(Under) = (r1 - r0) * (F1(L) - F0(L)) >= 0` when `r1 >= r0`.

This is a defensible Under direction **only for incremental risk relative to the baseline already priced**, holding the no-foul scoring opportunity distribution fixed. Neither a player's raw prior foul rate nor his probability of reaching the disqualification threshold identifies `r1 - r0`. The book need not expose an explicit foul model to account for its effects through observed minutes or the posted line.

A fixed-mean counterexample shows the sign problem. Define `X = m + r*d + epsilon - d*B`, where `B` is Bernoulli(`r`), `d > 0`, and independent noise `epsilon` has mean zero and CDF `F`. Then `E[X] = m` for every `r`, while:

`P(X <= L) = (1-r) F(L-m-r*d) + r F(L-m+(1-r)*d)`.

At `r=0`, the derivative with respect to `r` is `F(z+d) - F(z) - d*f(z)`, where `z=L-m`. At `L=m` for symmetric unimodal noise, this is nonpositive, and negative when the density decreases over the interval: the small lower-tail mixture is offset by the larger no-loss group's location moving above the line. With standard normal noise, `r=0.1` and `d=2`, the Under probability at `m` is about `0.4751`, and Over is about `0.5249`. This is a synthetic illustration, not an NBA estimate. More generally, nonidentical distributions with the same finite mean cannot have strict first-order stochastic dominance everywhere; the relevant line and distribution shape matter.

## What would be needed

- A scoring/minutes baseline that distinguishes no-foul opportunities from the foul-adjusted historical mixture. Trailing points or minutes alone does not do this. Actual foul-outs also do not reveal how long that player would otherwise have remained on court.
- A prior-observable reason that the coming game's loss distribution differs from the baseline's: for example, a verified matchup or assignment that changes foul exposure. Its availability, player role, projected workload and membership must be known before the quote. Eventual opponents defended, realized starters, actual minutes and target foul trouble cannot define the forecast feature.
- A model of lost scoring conditional on the relevant event, not just an expected foul count. Reduced minutes before formal disqualification, changed aggression, rotation decisions and overtime can matter. Fouls, minutes, pace and scoring are not independent, and foul-related stopping makes naive fouls-per-minute extrapolation potentially misleading.
- A clear way to avoid double counting. Either compare a complete independent conditional score distribution directly with the bookmaker, or apply a demonstrably incremental adjustment to a declared reference distribution. Treating the quoted no-vig probability as a no-foul probability would be an unsupported assumption.

The first alternative is a substantial joint opportunity/score modeling task, not a cheap one-feature truncation correction. Even a correctly specified sports mechanism need not produce residual mispricing when a public opponent and a player's history are already known to the bookmaker. A pregame snapshot cannot establish repricing lag without an independently timed new-information trigger and an appropriate price path.

## What the retained prices can establish

The retained archive has actual paired FanDuel main-points prices; the completed source census verifies 666 events and 8,286 pairs in 2025–26 before any foul-risk qualification. Such a pair supplies one margin-normalized CDF value at its line. It does not identify a mean, variance, foul-free distribution, baseline event probability, or conditional lost-minutes distribution. Many incompatible mixtures can reproduce that same probability while implying opposite corrections.

The archive also contains alternate-points quotes, as documented by earlier completed work. A complete, clock-qualified ladder could constrain more of the market's CDF, but cannot on its own label which part is foul risk or recover the no-foul counterfactual. One-sided alternate prices cannot simply be normalized as paired probabilities. Interpolating a ladder, deconvolving a mixture or inventing an unpriced counterfactual would introduce additional assumptions requiring a separate prior declaration. The closed payoff-coverage result is not evidence for this new forecast mechanism.

**Recommendation:** do not declare an automatic Under offset from historical foul rate with the present baseline. The directional mechanism is unresolved, not disproved. A useful source check can establish prior foul/rotation clocks and price coverage, but must not be promoted into a probability correction without the observable baseline above. If the real question is empirical residual prediction by a foul-risk feature, its coefficient cannot be constrained Under merely from the truncation story; that would be a separately justified exploratory hypothesis. No parameter, cohort or cutoff should be chosen from target results.

The relevant information is the number of independent changes in foul-loss exposure, not merely the number of priced player rows. Repeated players and uncommon loss events can leave an apparently large cohort weakly informative. The 2025–26 archive has already been inspected in other research, so a distinct frozen model would still be retrospective exploratory work, not an untouched confirmation sample.
