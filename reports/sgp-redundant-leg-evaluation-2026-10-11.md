# Redundant-leg SGP: PR 5 evaluation, back test and analogues

**Verdict.** The repricing mechanism is real and reproducible: theScore Bet's SGP engine paid more for 21 of 28 October 8 constructions after a logically implied leg was added, by a median factor of 1.51, and quoted the identical McCaffrey event at four prices from +869 to +1064 on October 9 depending on which implied milestone was attached. The positive-EV claim is not established. It rests on one FanDuel four-cell partition with 20.5% overround and on the de-vig model chosen for it. A population back test on 9,272 running-back games from 2015 to 2026 brackets the quoted event between about 8% and 17% depending on how much the posted line is assumed to know, with the 10.5% break-even inside the bracket. PR 5's arithmetic is right and its tests pass, but it cannot run live, its candidate generator cannot build the construction the census found positive, and its reference should not stay a single book's de-vigged partition.

Files: [back test script](../tools/backtest_sgp_redundant_leg.py), [results JSON](sgp-redundant-leg-backtest-2026-10-11.json), [October 8 census](sgp-rush-receive-2026-10-08/README.md), [PR 5](https://github.com/soldoutbudokan/BeatingAnything/pull/5).

## 1. The claim

theScore Bet quoted a Christian McCaffrey SGP for SF at SEA (October 11) at +483 with three legs: 90+ rushing plus receiving yards (S), under 54.5 rushing yards (R), 40+ receiving yards (C). Adding "over 34.5 receiving yards", which 40+ receiving already implies, moved the quote to +854. The event did not change. A FanDuel four-cell partition on S 91.5 and R 51.5 priced the over/under cell, a strict subset of the Score event, at +515. After power de-vig that cell is 11.82%, so +854 (break-even 10.48%) shows a +12.8% EV lower bound, or +6.1% under additive de-vig.

## 2. What the census shows about the engine

The October 8 census recorded 105 observations across 28 constructions. From `prices-and-ev.json`:

| Measure | Value |
|---|---:|
| Constructions with a base and a best price | 28 |
| Best price above base after redundant legs | 21 |
| Median payout multiplier when raised | 1.51 |
| Largest multiplier (McCaffrey >94.5 / 54.5, +428 to +1087) | 2.25 |
| Median conditional probability the engine assigned to a certain leg | 0.66 |

The engine treats a leg that is implied with probability one as if it had conditional probability about two thirds. That is consistent with a pairwise-correlation model, such as a Gaussian copula over separate market types, that does not know "Total Receiving Yards" over 34.5 and the "40+ receiving" milestone describe the same stat. The October 9 chain shows the pattern cleanly. With S 90+ and R under 49.5, every receiving milestone from 10+ to 40+ is implied, so all four tickets are one event, yet the quotes were +869 (C 10+), +997 (C 20+), +1059 (C 30+) and +1064 (C 40+). The boost grows with how unlikely the implied leg looks on its own. The best redundant leg is the highest milestone that is still forced by the base.

Two limits also appear in the census. Adding a third same-stat leg was sometimes rejected with no price (McCaffrey C >34.5, C 10+, C 20+). And an added S milestone below the S line lowered the price (Bijan Robinson S 100+ moved +770 to +648), so the boost is not monotone in leg count.

## 3. Why the EV number is fragile

The whole EV claim is the gap between 10.48% (break-even at +854) and the reference probability of the FanDuel over/under cell. That cell's probability depends on how the 20.5% overround is distributed across four cells, which the data do not reveal.

| Reference | FanDuel OU cell P(S>91.5, R<51.5) | Score event P(S≥90, R≤54, C≥40) | EV at +854 |
|---|---:|---:|---:|
| FanDuel raw implied | 16.3% | at least 16.3% | at least +55% |
| Multiplicative de-vig | 13.5% | at least 13.5% | at least +29% |
| Iterative fit to 50/50 single-leg marginals | 13.1% | at least 13.1% | at least +25% |
| Power de-vig (report's headline) | 11.8% | at least 11.8% | at least +13% |
| Additive de-vig | 11.1% | at least 11.1% | at least +6% |
| Break-even | | 10.5% | 0% |
| Back test, trailing-feature lines (section 4) | 5.5–9.0% | 7.7–10.3% | −27% to −2% |
| Back test, usage-oracle lines (section 4) | 12.8–14.1% | 16.8–17.1% | +60% to +63% |

A posted line knows more than trailing statistics and less than the game's actual usage, so the truth sits between the last two rows, and that range straddles break-even. The power de-vig passes one consistency check: its implied marginals are 50.0% S over and 50.8% R under, which matches main lines set at the median. Nothing in the data picks between power, additive and the marginal fit.

Two further points. First, theScore's base two-leg prices sit far below FanDuel's de-vigged fair. The McCaffrey base +391 has a −42% power lower bound; across the census, base constructions range from −42% to −69%. The redundant-leg boost mostly returns a badly priced ticket toward fair. Only the McCaffrey constructions crossed fair under both de-vig models, and only because the boost was large and the base was the least bad. Second, the "lower bound" framing favors narrower constructions. The +790 ticket (S 90+, R under 54.5, C >34.5, C 30+) covers the broader event {S≥90, R≤54} but shows a smaller bound (+5.2% power) than the +854 ticket, whose extra 40+ receiving leg removes real probability (C of 36 to 39). In the back test cohort the broad event occurs 9.7% versus 9.0% for the narrow one, so +790 on the broad event and +854 on the narrow one are about equally good, which the bound comparison hides.

## 4. Back test

Historical FanDuel SGP partitions do not exist in any public archive found, and no archive of rushing or receiving yardage lines was found either. The back test therefore estimates the quoted event's probability directly from outcomes, in a cohort of games whose expected usage resembles McCaffrey's October 2026 lines.

**Data.** nflverse weekly player stats, regular season 2015 through week 5 of 2026, running backs only, 9,272 games with at least six prior qualifying games (10 or more carries plus targets). The script makes no network calls once the files are present.

**Pseudo-lines.** A trailing median overshoots badly: only 32% of games go over a six-game median because the window selects on past usage. The script instead fits each stat on trailing features and shifts the fit inside each of 20 predicted-value bins so the over rate is 50% in every bin. A second "usage-oracle" fit adds the game's own carries and targets, which no book knows beforehand, to bracket how much a better-informed line changes the joint cells.

**Line gap.** Fitted S lines sit 5.1 yards above the fitted R and C lines added together (1.5 yards with the oracle fit). The October 8 quotes show the same gap: FanDuel S 91.5 and R 51.5 against theScore's main receiving line of 34.5. So "C ≥ 41" is forced only inside the FanDuel over/under cell; it is not the receiving line. All cohorts and local estimates below are therefore defined on the (S line, R line) pair, which is also what the FanDuel partition uses.

**Calibration and cell shares.**

| Lines | Games | S over | R over | OO | OU | UO | UU |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trailing-feature fit, all backs | 9,272 | 50.0% | 50.0% | 42.4% | 7.6% | 7.6% | 42.4% |
| Usage-oracle fit, all backs | 9,272 | 50.0% | 50.0% | 40.3% | 9.7% | 9.7% | 40.4% |
| Trailing-feature fit, cohort (S line 83.5–99.5, R line 43.5–59.5) | 155 | 56.8% | 55.5% | 47.1% | 9.7% | 8.4% | 34.8% |
| Usage-oracle fit, same cohort box | 191 | 49.7% | 49.2% | 34.6% | 15.2% | 14.7% | 35.6% |

The OU cell that FanDuel priced at 11.1–13.5% after de-vig sits between the trailing-feature estimate and the usage-oracle estimate for this cohort. That is the right bracket for a book's line, so FanDuel's de-vigged price is not contradicted. FanDuel's raw 16.3% is above even the oracle figure for the whole population and should not be read as a probability.

**The quoted events at their actual thresholds.** Three estimators, each run with both line types. The box cohort grades games whose lines fall in the box. The kernel estimate weights every game by a Gaussian in (S line, R line) distance from (91.5, 51.5), bandwidth 6 by 5 yards. The scaled estimate rescales each cohort game's S and R to the McCaffrey lines by ratio and grades the result.

| Estimator | Lines | Oct 8 event (+854, break-even 10.5%) | 95% CI | Oct 9 event (+1064, break-even 8.6%) |
|---|---|---:|---|---:|
| Box cohort, 155 games, 39 backs | trailing-feature | 9.0% | 5.5–14.6% | 6.5% |
| Kernel, effective n 477 | trailing-feature | 7.7% | 5.6–10.4% | 5.3% |
| Scaled, cohort box, 155 games | trailing-feature | 10.3% | 6.5–16.1% | 7.1% |
| Kernel, effective n 297 | usage-oracle | 17.1% | 13.3–21.8% | 12.3% |
| Scaled, cohort box, 191 games | usage-oracle | 16.8% | 12.1–22.7% | 13.6% |

At +854 the trailing-feature estimates give −27% to −2% EV and the oracle estimates +60% to +63%. For the October 9 event at +1064 the range is −38% to +58%. The FanDuel over/under cell itself (S≥92, R≤51) runs 5.5–9.0% under trailing-feature lines and 12.8–14.1% under oracle lines, so FanDuel's +515 on that cell is a losing price under every estimate, which is what a 20% overround predicts. The tighter box cohort (S line 87.5–95.5, R line 47.5–55.5, 33 games) gives 12.1% for both events with intervals of 4.8–27.3%. Requiring ten or more touches in the graded game changes rates by under one point. By period the wide-cohort rate for the October 8 event is 5.8% (2015–19, n=69), 12.7% (2020–24, n=63) and 8.7% (2025–26, n=23).

**McCaffrey himself.** Across 116 regular-season games the October 8 event occurred 20 times (17%), but most came in seasons with far higher lines (2019 median S of 160). In his 21 games whose fitted lines fall in the cohort box it occurred 4 times. In his four 2026 games (S of 88, 66, 116, 70; C of 20, 43, 41, 18) it occurred zero times. The population fit would post S 77.5 and R 51.5 for his next game; FanDuel posted S 91.5 and R 51.5, so the book expected about 14 more yards, presumably from game script against Seattle. The October 11 game was in progress when this was written and is not graded here.

**Limits.** Pseudo-lines are noisier than book lines, which inflates the diagonal cells and understates the OU cell; the oracle variant bounds that effect from the other side. The cohorts are cohorts of similar usage profiles, not similar matchups. The kernel estimate drifts down as its bandwidth widens because most backs have lower lines and the thresholds are absolute, so the narrow bandwidth is the relevant one. The intervals are the main result: nothing here separates the +13% headline from a −14% loss on the one quote, and both line types together say the true probability is near break-even.

## 5. PR 5 code evaluation

PR 5 adds `beating/sgp`: about 1,600 lines of code, 720 lines of replay fixtures and 1,100 lines of tests. All 71 SGP tests pass on Python 3.13, and `python -m beating.sgp demo` replays the October 9 fixtures as documented: 41 candidates planned, four priced, one FanDuel partition reused on the second run. The PR is a draft and says so.

What it does well: exact selection identities are preserved through hashing, so a redundant construction is never collapsed into its equivalent event when requesting a quote; integer reference lines are rejected because pushes break the four-cell partition; historical and live modes cannot mix; stale, future and incoherent partition clocks are gated; the SQLite ledger is append-only with epoch invalidation.

A separate review pass over the geometry, de-vig, runner, store, provider and CLI code, with brute-force checks of the integer geometry against 2,500 random boxes, found no error in the arithmetic. It did find these, ranked:

1. **The candidate generator cannot produce the October 8 construction** (`math.py` `generate_candidates`). Bases are one S leg plus one R or C leg, and redundant legs are only those implied by that two-leg base. The +854 ticket is a three-leg base (S 90+, R under 54.5, C 40+) plus a redundant C over 34.5. S≥90 and R≤54 force only C≥36, so C 40+ is not redundant and the four-leg ticket is never enumerated. Verified on the October 8 inventory: 36 candidates, the +854 construction absent. It appears in the packaged October 9 fixture only because R under 49.5 forces C≥41. Bases of R and C legs with an implied S leg are also never built. A live scan would not re-price the one construction the census found positive.
2. **A mapping's `side` override discards the provider's selection side** (`normalize.py`). With a milestone market mapped to `at_least`, an "under" or "no" selection at 20 becomes a C≥20 leg with no rejection, is judged implied by bases, and is priced and evaluated with inverted geometry. The override should require the provider side to be absent, "over" or "yes".
3. **`normalize` can emit a manifest that `plan` rejects wholesale.** A null provider name passes normalization and then fails manifest validation for every board instead of being quarantined as one leg.
4. **One duplicate FanDuel selection aborts planning for every board** (`pipeline.py` `reference_partitions`). Two legs sharing stat, line, market and side with different selection IDs are legal in the manifest but raise during planning. This should be a per-board gap.
5. **Integer target lines ignore pushes.** `evaluate` rejects integer reference lines but accepts integer target legs, grading "over 90" as ≥91 with a push counted as a loss. The lower bound stays valid for the strict-win event, but the upper bound and the exact flag ignore the reduced-payout settlement.
6. Minor: a budget-exhausted stub stamps construction time as its receipt time in live mode (never cached, so harmless); a cache TTL above the partition skew would make a half-cached partition fail until expiry with nothing forcing a re-quote (defaults avoid this); the `capture` command writes an empty evidence file before the missing-key check fires.

Verified correct: `extrema`, `contained` and `intersection` for integer R, C and S=R+C including negative and unbounded sides; over 34.5 and at-least 35 share one event key; the October 8 McCaffrey comparison returns the OU cell as the single included cell, 11.82% power and 11.12% additive lower bounds, +12.77% and +6.13% EV, and +746 and +799 minimum profitable prices, matching the census exactly; the power bisection and additive validity rule; historical rows can never be labelled live; cache hits require active revision, matching epoch, collector token, mode and TTL; late responses cannot overwrite newer attempts; the provider keeps the key out of URLs, logs and raw evidence.

Design observations, separate from correctness:

- **It cannot run live.** There is no FanDuel SGP source and no theScore source other than an OpticOdds adapter that the PR itself says does not establish FanDuel coverage, Ontario provenance or source freshness. Without a FanDuel partition the runner skips every candidate. The pipeline as merged would collect nothing until a capture worker exists.
- **The reference is one book's SGP model.** `evaluate` bounds the target with FanDuel's de-vigged cells only, and `both_models_positive` gates on power and additive. Section 3 shows the sign of the EV moves with that choice. A third gate on an outcome-based estimate (the cohort rates above, or a fitted joint model) and a second book's partition would make "positive" mean something.
- **Only one cell and one direction are searched.** Beyond finding 1, `generate_candidates` builds S-versus-R/C bases only, which are the OU and UO style cells. The OO and UU cells, and R-versus-C bases, are never quoted. If theScore's correlation model is miscalibrated on one cell it is miscalibrated on others, possibly in the bettor's favor without needing the redundant-leg trick.
- **The plan quotes every redundant construction.** The October 9 chain shows the boost grows with the implied milestone's threshold. Quoting the highest implied milestone first and the rest only under spare budget would cut provider spend by most of the 41-request plan.
- **No settlement or account-risk checks.** theScore's house rules on related contingencies, maximum SGP payout and account limiting are not recorded anywhere in the PR or the census.

## 6. Similar edges

No public source describes a book paying more for an implied leg. The sources found describe the opposite: builders gray out duplicate outcomes, correlated legs are discounted, and markets whose correlation cannot be priced are excluded from SGP. The Northern Territory regulator's Sportsbet decision confirms that a same-game multi price comes from "a software pricing scheme" rather than multiplication. So this is not a known trick, which cuts both ways: it may persist, and a book that notices may void or limit.

The structural recipe is: find an engine that stores correlation by market type, then stack legs from different market types on the same stat so every added leg is forced by the base. Candidates, with the implied chain in each:

- **NFL.** Rushing or receiving yards over N (O/U market) plus the "N+" milestone market, as here. Longest reception over 19.5 forces receiving yards over 19.5. Receptions over 4.5 plus "5+ receptions". Passing yards over 299.5 plus "300+ passing yards". 2+ touchdowns forces anytime touchdown; first touchdown scorer forces anytime. Team total over 24.5 plus "team to score 25+". Both team totals over forces the game total over their sum.
- **NBA.** Points over 24.5 plus "25+ points"; the same for rebounds, assists and threes (over 2.5 plus "3+ made"). 10+ points plus 10+ rebounds forces double-double; triple-double forces double-double. Points, rebounds and assists each over their lines force PRA over the sum.
- **NHL.** Shots on goal over 2.5 plus "3+ shots". 2+ goals forces anytime goal; hat trick forces 2+. Goalie saves over 29.5 plus "30+ saves".
- **MLB.** A home run forces 1+ hit, 1+ run, 1+ RBI and 4+ total bases, so one HR leg can carry four implied legs. 2+ hits forces 1+ hit. Strikeouts over 6.5 plus "7+ strikeouts".
- **Soccer.** 2+ goals forces anytime scorer, which forces 1+ shot on target and 1+ shot. Win to nil forces the win, clean sheet and BTTS no. A correct score forces the result, the total and BTTS. Over 3.5 forces over 2.5 and over 1.5 on the alternate-total ladder.
- **Tennis.** Straight-sets win forces the match win; alternate game totals nest.

Which engines are exposed depends on method. A simulation engine, which draws whole games and grades every leg on the same draw, cannot be fooled by an implied leg: the leg wins on every draw where the base wins. A copula or pairwise-correlation engine over market types can. theScore runs an in-house trading stack and introduced its correlated product in 2022; the census behavior says its player-prop SGP is of the second kind. The test for any other book is cheap: quote a two-leg base, add the highest implied milestone, and see whether the price moves. One rejected combination or one unchanged price answers it.

Two related edges that need no redundant leg:

- **Other cells, cross-book.** A miscalibrated correlation model that underpays the OU cell must overpay somewhere. Quote all four cells of the S-by-R partition at theScore and compare each to FanDuel's de-vigged cell and to the back-test rates.
- **Alternate-ladder arbitrage.** Where an engine prices "over 34.5" and "35+" as different markets, the same stat has two prices; the earlier PointsBet alternate-ladder audit in this repository is the same idea on single legs.

## 7. Recommended next steps

1. Fix `generate_candidates` so a base may hold three legs (S, R and C) and so R-plus-C bases with an implied S leg are built; without that the pipeline cannot re-price the construction it was written for.
2. Change the reference before scanning more. Add an outcome-based probability (the cohort method here, or a fitted bivariate model of R and C given lines) as a third gate beside power and additive, and record a second book's partition when one exists.
3. Scan all four cells and both base directions, and quote the highest implied milestone first.
4. Record theScore single-leg prices alongside each SGP quote so the engine's conditional-probability rule can be fitted. If the boost is a stable function of the implied leg's standalone price, the best constructions can be predicted without quoting all of them.
5. Read theScore's rules on related contingencies and SGP settlement before any stake. Its US sibling ESPN BET voids winning SGPs and lets losing ones stand when a leg voids, an asymmetry that matters for a ticket built from redundant legs.
6. Grade the October 11 McCaffrey outcome into the census for the record; one result changes no estimate here.

## Sources consulted

- Tony's Picks, [why sportsbooks block certain SGP combos](https://www.tonyspicks.com/2026/05/13/same-game-parlay-correlation-why-sportsbooks-block-certain-combos/): duplicate-outcome legs are grayed out.
- OddsPapi, [same-game parlay correlation](https://oddspapi.io/blog/same-game-parlay-correlation-python/): naive multiplication over-pays positively correlated legs.
- MatterOfStats, [why some same game multis are not allowed](https://www.matterofstats.com/mafl-stats-journal/2020/8/14/why-are-some-same-game-multis-not-allowed-by-bookmakers): conditional-probability framing.
- Northern Territory Racing Commission, [decision on Sportsbet same game multi dispute](https://dth.nt.gov.au/__data/assets/pdf_file/0017/1300922/g-v-sportsbet-pty-ltd.pdf): SGM odds come from a software pricing scheme.
- Caesars, [same game parlay guide](https://www.caesars.com/sportsbook-and-casino/betting-guide/same-game-parlay): markets excluded when correlation cannot be priced.
- iGaming Business, [inside theScore's tech stack](https://igamingbusiness.com/sports-betting/inside-thescores-amped-up-tech-stack/): in-house risk and trading platform, correlated parlay product from 2022.
- Action Network, [ESPN BET SGP void rules](https://www.actionnetwork.com/general/why-espn-bet-has-worse-rules-for-sgps-than-fanduel-draftkings-caesars-betmgm): winning SGPs voided, losing ones stand, when a leg voids.
- OpticOdds, [SGP pricer documentation](https://developer.opticodds.com/docs/same-game-parlay-sgp-pricer-bet-builder): vendor pricer, no FanDuel SGP coverage stated.
- nflverse, [weekly player stats releases](https://github.com/nflverse/nflverse-data/releases): back test data.
