# Test ball-by-ball projection model: method

This page explains every step that produces the numbers on the site, what the columns mean and where the model
is weak. It is written by the build, so the figures below are this build's.

The model extends the T20 (IPL) workbook's approach to five-day cricket: one model of what happens on a single
delivery, fitted on every delivery at once, then a simulator that plays those deliveries out as whole matches.

## 1. Data

* Every men's Test on cricsheet.org with ball-by-ball data: 899 matches from 2001-12-19 to
  2026-10-28, 1,730,523 deliveries in the fit.
  Cricsheet withholds Afghanistan's matches, so Afghanistan cannot be rated or simulated.
* One row per delivery with the state before it: innings, over, wickets, score, lead, target, overs bowled in the match so far, striker,
  non-striker, bowler, balls the striker has faced, overs the bowler has bowled in the innings, outcome, extras and dismissal.
* Grounds are merged across spellings and renamings and mapped to a host country. Batting hand and bowling type come
  from the T20 workbook's curated file, then cricketdata's player table. Bowlers with no label are classed pace or
  spin by a classifier on how their deliveries behave and flagged as inferred.
* Upcoming fixtures and announced XIs come from ESPN's public cricket scoreboard API (section 9).

## 2. Outcome classes

Each delivery is one of 11 classes: wide, no-ball, bye or leg-bye, bowler wicket (bowled, caught, lbw, stumped, hit
wicket), run out, and bat runs 0, 1, 2, 3, 4, 6 (fives count as fours). How many runs a wide, no-ball, bye or run
out is worth, and which batter a run out removes, come from small tables of recent Tests.

## 3. The probability model (one model, fitted jointly)

The chance of each class is a softmax over 11 logits (the dot ball is the reference). Each logit is a **sum of
additive terms**, all estimated together in one penalised multinomial logistic regression:

| term | what it captures |
|---|---|
| innings (1-4) x over bucket, innings x ball phase x wickets, innings x over bucket x wickets | match situation: new ball, old ball, second new ball, top order or tail, in each innings of the match |
| overs already bowled in the match; the same x spin | **pitch wear**: batting changes as the surface ages, and spin gains more than pace |
| first innings: runs on the board x wickets; second innings: lead x wickets | **position**: sides bat differently at 450 for 3 than at 150 for 3 |
| third innings: lead x wickets | setting a target, including the push before a declaration |
| fourth innings: runs needed x wickets; runs needed per over left x overs left | **the chase or the block**: going for a target, or batting out time |
| pace / spin x overs the bowler has already bowled in the innings | **spell length** |
| a recognised batter with 7, 8 or 9 wickets down | batting with the tail |
| phase x balls-faced bucket | the **settling curve**: a new batter scores slower and gets out more |
| bowling type; type x phase; type x left-handed batter | pace against spin overall and by phase, and the hand match-up |
| calendar year; year x phase; year x spin | the **era**: how the game as a whole has moved (more attacking batting, shorter matches). A random walk: each year is tied to the one before |
| host country; country x spin; country x phase | the **conditions** of a country: its pitches, its ball, its climate |
| host country x season; the same x spin | how a country's conditions drift. A random walk from that country's previous season |
| ground; ground x third and fourth innings; ground x spin | ground effects on top of the country, late in the match, and for spin |
| batting side at home; bowling side at home; each x spin | **home advantage** (a neutral ground is the reference) |
| batter: overall, v the new ball, v the old ball, v spin, first 30 balls, away from home; v each of six bowling types | batter skill and its splits. The by-type split is shrunk hardest |
| bowler: overall, new ball, old ball, v left-handers, away from home | bowler skill and its splits |
| batter role, role x experience, age, team, other-format record; the same for bowlers | the **prior** a small sample shrinks toward |

Phases are the new ball (the ball's first 20 overs), middle (21-55) and old ball (56-80); the second new ball at 80 overs starts the cycle again.

Because batter, bowler, ground, country, season and era terms are fitted at the same time, each is measured net of
the others. A batter's rating is adjusted for the bowlers he faced, where he faced them and when.

**Shrinkage.** Every term carries a ridge penalty. A player with few balls is pulled toward players like him: the
same batting role (from his batting position) or bowling role (pace or spin, by workload), the same experience, the
same age band and the same national side. The team term matters in internationals: an unknown Australian is a
better bet than an unknown player from a side that loses more. A player new to Tests also inherits a prior from his ODI record.

**Nothing looks ahead.** Role, experience, age and team are measured as of each delivery (role from the innings he
has played so far, experience from the balls he has faced or bowled so far). The holdout therefore never sees a
player's future, and "inexperienced" is not defined by players who failed and were dropped.

**Recency.** Each delivery is weighted by 0.5^(age / 6 years).

**Inactivity.** A player with no international in either format for over a year has his individual rating decayed
toward his prior by exp(-(gap - 1) / 2), gap in years.

**Uncertainty.** A diagonal Laplace approximation gives a posterior SD for every coefficient. The ± on a player's
rating redraws his own coefficients from it. It ignores the other terms, so it is somewhat too small.

## 4. How the settings were chosen

Two walk-forward folds: train on everything before a cut-off, score per-ball log loss on the window after it
(). An unseen
season takes its country's latest training season, which is what a projection does. Each variant is compared with
the base ball by ball, with a standard error clustered by match. This is a check of fit quality, not a betting
backtest.

| variant | half-life | log loss | v base | SE | verdict |
|---|---|---|---|---|---|


Adopted: half-life 6 years; penalties bat 40, bat_split 100, bat_type 150, bowl 100, bowl_split 100, cell 30, comp 5, cov 2, cs 200, gs 20, l0 1, rw 200, sit 3, team 5, venue 300, venue2 600, xf 2.



## 5. Conditions the model cannot see

Both sides of a match share a pitch and weather. The model measures that as the covariance between the two sides'
residual scoring and wicket rates (actual minus expected, per ball), on the holdout so that fitted ground and season
terms cannot soak it up. It becomes a match-level shock on two axes of the logits, scoring shots and wickets, drawn
once per simulated match and applied to every ball. What is left of the variance of a single innings after
sampling noise and the shared part becomes an innings-level shock. This build:

* Match shock, scoring axis (SD, log-odds): 0.059 (about +0.13 runs per over)
* Match shock, wicket axis (SD, log-odds): 0.088 (wicket rate x 1.09 at +1 SD)
* Innings shock, scoring axis (SD): 0.184
* Innings shock, wicket axis (SD): 0.247
* Cross-team correlation of scoring residuals: 0.02 of the innings variance

**Pitch dial.** The simulator's pitch options move along those axes: *flat* is one match SD easier to score on and
harder to take wickets on, *hard to bat on* the reverse, *green seamer* adds the pace-wicket gap between the most
seam-friendly fifth of grounds and the average, *dry, turning* the same for spin. These are scenario
dials, not forecasts for a match.

## 6. Time, declarations and the follow-on

A Test is a race against time, and cricsheet does not say which ball was bowled on which day. The model therefore
works in overs.

* **Overs available.** A drawn Test shows how many overs the match had room for; a Test with a result only shows
  that it had at least that many. A Kaplan-Meier estimate by host country (shrunk toward the pooled curve) turns
  that into a distribution of overs available, which carries the country's weather and over rates. Each simulated
  match draws from it and is drawn when the overs run out. The **time** dial replaces the draw with a full 450
  overs, or removes half a day, a day or two days.
* **Declarations.** A logistic model on over-end states of the first three innings: runs or lead, wickets, overs
  left and, in the third innings, the runs per over the target would ask.
* **Follow-on.** A logistic model on the lead, the overs the bowlers have just bowled and the time left.
* **Bowling.** No fixed schedule exists in a Test. Each bowler has a share of the side's overs with the new, middle
  and old ball. Two bowlers operate at a time, one from each end; a spell ends with a chance that depends on its
  length and on pace or spin, and the next bowler is drawn by share. The second new ball at 80 overs resets both
  ends. Spell length feeds back into the per-ball model.

* Innings 1: declared / all innings since 2010: 125 / 682 (model expects 127.4)
* Innings 2: declared / all innings since 2010: 68 / 679 (model expects 73.0)
* Innings 3: declared / all innings since 2010: 202 / 672 (model expects 202.7)
* Follow-on enforced when available (since 2010): 63 of 132
* Mean spell, pace / spin (overs): 4.3 / 6.3

## 7. Player ratings ("true" stats)

Ratings are stated in **reference conditions**: every delivery between full members since 2022-01-01 is
re-evaluated with the player swapped in (as batter or bowler), keeping the real opponent, ground, era and match
state, and the model's probabilities are averaged. That gives context-neutral, opposition-adjusted rates.

* Batters: `avg` (runs per dismissal), `sr` (runs per 100 balls), balls per dismissal, boundary and dot rates.
  Bowlers: `avg` (runs per wicket), `econ`, balls per wicket.
* **Value** is runs against the average player on the same deliveries, with a dismissal priced in runs:
  the reference runs per wicket.
* Splits: *all* uses the player's own recency-weighted mix of phases; phase columns use every reference delivery of
  that phase; pace / spin, right / left-hander and home / away restrict to those deliveries.

## 8. Teams

* The default XI is a side's most recent XI. Sides pick differently by conditions, so each also carries its most
  recent XI in Asia, in SENA-type conditions and elsewhere, used for fixtures there when it is under two years old.
  The batting order is each player's mean order of appearance over his last ten innings.
* Bowling shares are each bowler's share of the side's overs by ball phase over its last 30 matches, weighted to the recent ones.
* Team strength is not a sum of player ratings: the Teams sheet plays every pair of the 11 sides on neutral
  ground.

## 9. Simulator

One engine, `docs/models/cricket/sim.js`, runs in the browser and in the build (under node), so a published number
and a number you re-run come from the same code. Ball by ball: the class probabilities are the softmax of the sum of
the tables above for the current striker, bowler, over, wickets and match state, plus the match and innings shocks
and any dials. Strikers rotate on odd runs and at the end of each over; a wicket brings in the next batter.
An innings ends all out, on a declaration, when the target is reached or when time runs out; the follow-on, innings victories, ties and draws follow the laws.

Outputs: win, draw and tie probabilities, first-innings totals and lead, second-innings totals, match runs, overs and the day the match ends, fall of the first wicket, fours and sixes, and for every player the distribution of
runs, boundaries, wickets and runs conceded, plus the chance of being his side's top scorer or top wicket-taker in
its first innings.

## 10. Schedule

Fixtures are read from ESPN's cricket scoreboard API: series are found by scanning the calendar ahead, then each
match is read from its series. A fixture is mapped to the model's sides and ground (by name, then by city), the home
side is the one whose country hosts, and each side gets the announced XI once ESPN has it (within three days of the
start) or its most recent XI in comparable conditions. Each fixture is simulated before play; a match in progress
keeps its pre-match view. Sides without data are listed and not simulated.

## 11. Simulator replay

Each match is re-simulated with the real XIs, batting order of appearance, each bowler's real share of the bowling by phase, the ground and the side that batted first. The ratings were fitted on these same matches, so this checks that the simulator turns per-ball probabilities into realistic matches. It is not evidence of predictive skill, and the win-probability table flatters the model for the same reason.

189 matches since 2022-01-01, 300 simulations each:

| quantity | real | simulated |
|---|---|---|
| First innings of the match: mean total | 325.6 | 328.9 |
| First innings of the match: SD of totals | 141.4 | 148.7 |
| First innings: wickets lost | 9.5 | 9.3 |
| First innings: all out (%) | 84.7 | 82.1 |
| First innings: overs | 91.7 | 93.0 |
| Side batting first wins (%) | 44.4 | 46.4 |
| Match runs | 1016.3 | 1013.2 |
| Second side's first innings: mean total | 310.9 | 307.5 |
| First innings: declared (%) | 15.3 | 17.8 |
| Draw (%) | 10.6 | 11.2 |
| Overs bowled in the match | 288.9 | 289.9 |
| Follow-on enforced (%) | 8.5 | 10.5 |
| Second-innings totals (third and fourth innings of the match) | 213.0 | 215.8 |

Pre-match win probability of the side batting first, in fifths:

| model said | matches | mean prediction | won |
|---|---|---|---|
| 3-21% | 38 | 14% | 16% |
| 22-39% | 40 | 31% | 25% |
| 39-52% | 35 | 45% | 49% |
| 53-71% | 38 | 62% | 50% |
| 72-97% | 38 | 80% | 84% |

## 12. Known weaknesses

* No market comparison has been run. Nothing here shows the model beats a price.
* Afghanistan is missing from the data. Associates play few matches and lean on their priors.
* No ball tracking: "expected" means expected given the situation, opposition, ground and era, not line and length.
* Fielding, keeping and captaincy are not modelled separately.
* Day-night Tests are not flagged in the data and are treated like any other.
* The time model is in overs, not clock time: no sessions, no bad light, no new-day effect. A captain is taken to know how many overs the match has left.
* Bowling changes follow shares and spell lengths, not the match: a captain does not turn to his best bowler when a stand builds. Batting orders do not flex (no nightwatchman).
* Default XIs are the last XI a side picked. Injuries, rest and retirements since then are not known until an
  announced XI arrives.
* A player's rating in a format rests on that format alone plus a prior from his ODI record. T20 form is not used.
* The season and year environments are frozen at their latest values for projections.
* Uncertainty bands understate the true uncertainty.
