# IPL ball-by-ball projection model — method

This page explains, in plain language, every step that produces the numbers on the site, what each column
means, and where the model is weak. Exact field names are in `schema.md`; build-specific numbers (data cut-off,
tuned hyper-parameters, sim speed) are in `meta.json` and `diagnostics.json`.

## 1. Data

* Source: every men's 20-over T20 match on cricsheet.org with ball-by-ball data (IPL, T20 internationals,
  BBL, PSL, CPL, SA20, ILT20, MLC, T20 Blast, Syed Mushtaq Ali Trophy, BPL, LPL, Super Smash, CSA T20,
  Nepal PL, Irish inter-provincial and smaller leagues). Afghanistan matches are withheld by cricsheet.
  Players are keyed by cricsheet register identifiers.
* One row per delivery: match, competition, season, date, canonical venue, innings, over, legal-ball count,
  striker, non-striker, bowler, outcome, extras, dismissal kind and player, wickets down, score, target,
  balls the striker has faced so far, batting position, toss, result and Impact Player substitutions.
* Venue names are canonicalised (spelling variants and renamed grounds merged, e.g. Feroz Shah Kotla =
  Arun Jaitley Stadium, Motera = Narendra Modi Stadium; generic names such as "County Ground" keep their city).
* Matches with reduced overs or a DLS result are kept for counting but excluded from the model fit, because
  the over/wicket context means something different in a shortened game. Super overs are excluded from the fit.

## 2. Outcome classes

Each delivery is one of 11 classes: wide, no-ball, bye/leg-bye, bowler wicket (bowled, caught, lbw,
stumped, hit wicket), run out, and bat runs 0, 1, 2, 3, 4, 6 (5s are treated as 4s). Extras' run amounts
(e.g. 1 vs 5 wides, runs off a no-ball, runs completed before a run out, and whether the striker or the
non-striker is run out) come from small empirical tables from recent IPL seasons.

## 3. The probability model (one model, fitted jointly)

The probability of each class on a delivery is a softmax over 11 logits (dot ball is the reference class).
Each logit is a **sum of additive terms**, all estimated together in one penalised multinomial logistic
regression on ~2.3 million deliveries:

| term | what it captures |
|---|---|
| innings x over, innings x phase x wickets, innings x over x wickets | match situation: the intent/risk profile at every point of an innings (cell terms are shrunk toward the additive ones) |
| phase x balls-faced bucket | the global **settling curve**: new batters score slower and get out more |
| phase x required-rate bucket (2nd innings) | **chase pressure** |
| bowler subtype; subtype x phase; subtype x left-handed batter | pace vs spin overall and by phase (spin is hit harder at the death), and the hand matchup (e.g. off-spin to left-handers) |
| competition; competition x season | **league environment** and season run environment (e.g. the post-2023 IPL Impact Player scoring surge) |
| venue; venue x 2nd innings; venue x spin | ground effects, chasing/dew, and spin-friendliness |
| batter: overall, powerplay, death, vs spin, first 10 balls | batter skill and its splits |
| bowler: overall, powerplay, death, vs left-handers | bowler skill and its splits |
| batter role, league mix, role x experience; bowler role, league mix, role x experience | the **informed prior** that small samples shrink toward |

Because batter, bowler, venue, league and season terms are fitted at the same time, each is measured net of
the others: a batter's rating is adjusted for the bowlers he faced, the grounds, the league and the era; a
bowler's for the batters he bowled to; and so on. This is how a run in the Syed Mushtaq Ali Trophy and a run
in the IPL end up on one scale: players who appear in both connect the leagues.

**Shrinkage.** Every term has a Gaussian (ridge) penalty: a player with few balls is pulled toward the
average of players like him: same batting role (career batting position) or bowling role (pace/spin x
workload), same mix of leagues, and same experience bucket within that role. Experience is measured **at the
time of each delivery** (T20 deliveries faced/bowled before it: <60, 60-199, 200-599, 600-1499, 1500-3999,
4000+), so the term learns how debutants and young players actually perform, without the survivorship bias of
career totals (players who failed early would otherwise define "inexperienced"). A player's current rating
uses his current experience bucket. Splits (phase,
pace/spin, hand, settling) are shrunk much harder toward zero, i.e. toward the player's own overall rating.

**Recency.** Each delivery is weighted by 0.5^(age / half-life). The half-life and the penalty strengths were
chosen by fitting on data before 1 June 2025 and scoring the log loss on everything after (IPL 2026 included),
with an unseen season given its league's latest training-season environment (exactly what a projection does).
This is a fit-quality check, not a betting backtest. See `diagnostics.json.tuning`.

**Uncertainty.** A Laplace (diagonal-Hessian) approximation gives a posterior SD for every coefficient. Player
uncertainty columns (`sd`) are the SD of the headline metric when the player's own coefficients are redrawn
from that posterior. They ignore correlations with other terms, so they are somewhat too small.

**Bowling styles.** Batting hand and bowling type come from `models/ipl/static/player_styles.csv`. Bowlers
without a label are classed pace/spin by a gradient-boosted classifier trained on labelled bowlers
(features: phase usage, wide/no-ball/bye rates, boundary and dot rates, share of wickets stumped / lbw /
bowled); those rows are flagged `style_inferred`.

## 4. Player ratings ("true" stats)

Ratings are expressed in **IPL 2024-26 conditions**: we take every real IPL delivery from 2024-26, swap in the
player (as batter or bowler), keep the real opposition player, venue, season and match situation, and
average the model's probabilities. This gives context-neutral, opposition-adjusted rates on the scale an
IPL fan knows.

* `sr` true strike rate (runs per 100 balls faced), `avg` true average (runs per dismissal), `out_pct`
  dismissals per 100 balls, `bnd_pct` / `four_pct` / `six_pct` boundary rates, `dot_pct`, `nbsr` non-boundary
  strike rate.
* Bowlers: `econ` true economy (runs per 6 legal balls including wides and no-balls), `wkt_pct` wickets per
  100 legal balls, `sr` balls per wicket, `avg` runs per wicket, `dot_pct`, `bnd_pct`, `wides_per_over`.
* `rv100` (batters) and `rv_over` (bowlers): **run value**. Each dismissal costs the batting side the value
  of a wicket in that situation, from an expected-runs-remaining (resources) table: losing a wicket in over
  3 with 1 down costs far more than losing one in over 19. `rv100` = (runs - wickets x wicket value) per 100
  balls; `rv_over` = (runs conceded - wickets x wicket value) per over (lower is better).
* Splits: `all` uses the player's own (recency-weighted) mix of phases; `pp`, `mid`, `death` use every IPL
  delivery of that phase; `pace` / `spin` (batters) and `rhb` / `lhb` (bowlers) restrict to deliveries of
  that type.
* `vs_avg`: the same metric minus what the average IPL player produced on exactly the same deliveries.
* `settling`: the batter's strike rate and dismissal rate by balls faced (0, 1-2, 3-5, ... 45+) in middle-over
  contexts; global curve plus his own first-10-balls deviation.
* `obs_*` blocks are **observed vs expected** (no shrinkage): his actual runs/wickets since 2024 compared
  with what an average IPL batter/bowler would have produced on the same deliveries (same opposition player,
  venue, league environment and situation). `rae100` = runs above expected per 100 balls.
* `wpa`: win probability added since 2024, from a separate gradient-boosted win-probability model of match
  state; batters get the change in their side's win probability on deliveries they faced (excluding wides and
  byes), bowlers the negative of it on every delivery they bowled.

## 5. Venues, leagues, seasons

* Venue multipliers are the model's venue terms evaluated on IPL 2024-26 deliveries, relative to an average
  ground: runs, wickets, fours, sixes per over, separately for pace and spin balls and for 1st vs 2nd innings.
  They are shrunk and recency-weighted like everything else.
* League strength (`leagues.json`): the average batter and bowler who played in each league since 2023,
  evaluated in IPL conditions, versus the IPL's own. `strength_vs_ipl` is runs per 20 overs (batting gap +
  bowling gap). `env_runs_per_over` is the league's own run environment (pitches, boundaries, ball) on its
  latest season. Associate T20Is and small leagues are in the fit but carry little weight on IPL players.
* The season environment term absorbs the 2023+ IPL scoring surge (Impact Player rule, flatter pitches), so it
  does not inflate player ratings. Projections use the **IPL 2026** environment by default.

## 6. Teams

* Squads are the players who appeared for each franchise in the latest IPL season in the data. The default
  12 (XI + Impact Player) is the 12 most-used players, weighting later matches more (half-life 5 matches),
  with at most 4 overseas players (overseas = played T20Is for a country other than India).
* Batting order: recency-weighted mean batting position. The 12th man — the Impact Player — is taken to be the
  lowest-ordered frontline bowler, who bowls but does not bat.
* Bowling plan: each bowler's overs per phase (powerplay 1-6, middle 7-15, death 16-20) are his historical
  per-match workload this season, turned into whole overs that fill 6/9/5 with at most 4 overs each.
  The simulator's "captain" then assigns overs one by one: each over goes to the bowler with the most planned
  overs left in that phase, never the previous over's bowler, never more than 4, and only if the remaining
  overs can still be bowled without anyone bowling consecutive overs.

## 7. Simulator

Ball by ball for both innings (10,000+ matches per matchup, half with each side batting first): the per-ball
class probabilities are the sum of the tables above for the current striker, bowler, over, wickets, balls
faced, required rate and venue. Strikers rotate on odd runs and at the end of each over; wickets bring in the
next batter; no-balls give a free hit (no bowler wicket possible); the chase stops when the target is reached;
a tie goes to a simplified super over (top three in the order vs each side's main death bowler; tie again =
coin flip). Outputs: win probability, totals, powerplay, score at the first wicket, fours, sixes, and per
player runs/balls/boundaries distributions, wickets, runs conceded, and the chance of being his side's top
run-scorer or top wicket-taker (most wickets, then fewest runs; ties split).

`sim.js` is the same engine in JavaScript, fed by `sim_params.json`, so any lineup, order, bowling plan,
venue or toss can be re-simulated in the browser. Python and JS agree within Monte Carlo error (see
`meta.json.sim.parity`).

## 8. Player value (VARP)

* Batting: (his run value per 100 balls - replacement-level run value) x the balls a batter in his batting
  slot faces per IPL innings, using that slot's phase mix for both him and the replacement.
* Bowling: (replacement run value per over - his) x his usual overs per match (career, capped at 4), in his
  own phase mix (`varp_4ov` gives the same per 4 overs, for comparing specialists).
* Replacement level: the average rating of fringe IPL players of the same role (bottom third of playing time
  among 2024-26 IPL batters in that batting-slot group; among specialist pace or spin bowlers).
* `varp_wp`: the run value times the win-probability-per-run slope from the simulator (about 1.2-1.5% per run
  in an even game).
* Team strength is not a sum of VARP: it comes from simulating the actual XI, so swapping a player changes it.

## 9. Diagnostics (`diagnostics.json`)

* Held-out per-ball calibration (train before June 2025, score after): log loss vs a no-skill marginal
  model, per-class reliability bins, and expected vs actual runs and wickets per innings.
* Simulator replay of IPL 2025-26: each real match re-simulated 400 times with the real XIs, batting order of
  appearance, each bowler's real overs per phase, venue and season; compares the distribution of
  1st-innings totals, wickets, powerplay runs, chase win rate, wides/sixes/fours per innings and the
  individual-score distribution (ducks, 30+, 50+). The ratings used were fitted on those same matches, so this
  tests whether the simulator turns per-ball probabilities into realistic innings, not predictive skill.

## 10. Known weaknesses

* Fielding, captaincy and keeping are not modelled separately; run outs are shared at the situation level.
* No ball-tracking: "expected" means expected given situation, opposition, venue, league and era — not given
  line and length.
* Batter-vs-bowler-type matchups are captured only through the batter's vs-spin split, the bowler's vs-LHB
  split and a global subtype x hand table; no per-player off-spin vs leg-spin split.
* Bowling plans are deterministic in the simulator (same over-by-over allocation in every sim) and do not react
  to wickets or match state; batting orders do not flex (no pinch-hitters, no promoting a finisher).
* Intent beyond the required-rate and wickets-in-hand context is not modelled (e.g. a side knowing its deep
  batting lets it attack) except via the season environment.
* Squads are the 2026 squads; auction/retention changes after the data cut-off are not known to the model.
  Overseas status is inferred from international appearances (uncapped overseas players would be missed).
* Uncertainty bands come from a diagonal Laplace approximation and understate true uncertainty.
* Venue identity: some grounds changed surfaces or boundary sizes; the recency weighting only partly handles it.
* League connectivity: leagues with few shared players (some domestic and associate competitions) have less
  reliable strength estimates.
* The super over is simplified.
* Prior covariates other than experience (career batting position, workload, league mix) are computed from
  each player's whole record. In the forward-holdout tuning this is a mild look-ahead for players who debuted
  shortly before the cut-off; it does not affect the final ratings.
* Hyper-parameters were tuned on an earlier version of the prior (career-total experience); the final model
  uses time-of-delivery experience with the same settings. Its holdout score is in `diagnostics.json.holdout`.
* Indian domestic cricket other than the Syed Mushtaq Ali Trophy (and SMAT seasons cricsheet lacks) is not in
  the data, so uncapped Indian players often have very small samples and lean heavily on the prior.
