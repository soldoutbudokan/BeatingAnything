# ODI ball-by-ball projection model: method

This page explains every step that produces the numbers on the site, what the columns mean and where the model
is weak. It is written by the build, so the figures below are this build's.

The model extends the T20 (IPL) workbook's approach to 50-over cricket: one model of what happens on a single
delivery, fitted on every delivery at once, then a simulator that plays those deliveries out as whole matches.

## 1. Data

* Every men's ODI on cricsheet.org with ball-by-ball data: 2,617 matches from 2002-06-27 to
  2026-11-02, 1,230,608 deliveries in the fit (395 rain-shortened or abandoned matches are left out of the fit: an over means something else in a shortened game).
  Cricsheet withholds Afghanistan's matches, so Afghanistan cannot be rated or simulated.
* One row per delivery with the state before it: innings, over, wickets, score, target, striker,
  non-striker, bowler, balls the striker has faced, outcome, extras and dismissal.
* Grounds are merged across spellings and renamings and mapped to a host country. Batting hand and bowling type come
  from the T20 workbook's curated file, then cricketdata's player table. Bowlers with no label are classed pace or
  spin by a classifier on how their deliveries behave and flagged as inferred.
* Upcoming fixtures and announced XIs come from ESPN's public cricket scoreboard API (section 9).

## 2. Outcome classes

Each delivery is one of 11 classes: wide, no-ball, bye or leg-bye, bowler wicket (bowled, caught, lbw, stumped, hit
wicket), run out, and bat runs 0, 1, 2, 3, 4, 6 (fives count as fours). How many runs a wide, no-ball, bye or run
out is worth, and which batter a run out removes, come from small tables of recent ODIs.

## 3. The probability model (one model, fitted jointly)

The chance of each class is a softmax over 11 logits (the dot ball is the reference). Each logit is a **sum of
additive terms**, all estimated together in one penalised multinomial logistic regression:

| term | what it captures |
|---|---|
| innings x over, innings x phase x wickets, innings x over x wickets | match situation: the intent and risk at every point of a 50-over innings (cell terms shrink toward the additive ones) |
| phase x required-rate bucket (second innings) | **chase pressure** |
| phase x balls-faced bucket | the **settling curve**: a new batter scores slower and gets out more |
| bowling type; type x phase; type x left-handed batter | pace against spin overall and by phase, and the hand match-up |
| calendar year; year x phase; year x spin | the **era**: how the game as a whole has moved (two new balls, fielding rules, higher scoring). A random walk: each year is tied to the one before |
| host country; country x spin; country x phase | the **conditions** of a country: its pitches, its ball, its climate |
| host country x season; the same x spin | how a country's conditions drift. A random walk from that country's previous season |
| ground; ground x second innings; ground x spin | ground effects on top of the country, chasing, and for spin |
| batting side at home; bowling side at home; each x spin | **home advantage** (a neutral ground is the reference) |
| batter: overall, powerplay, death, v spin, first 15 balls, away from home; v each of six bowling types | batter skill and its splits. The by-type split is shrunk hardest |
| bowler: overall, powerplay, death, v left-handers, away from home | bowler skill and its splits |
| batter role, role x experience, age, team; the same for bowlers | the **prior** a small sample shrinks toward |

Phases are the powerplay (overs 1-10), middle (11-40) and death (41-50).

Because batter, bowler, ground, country, season and era terms are fitted at the same time, each is measured net of
the others. A batter's rating is adjusted for the bowlers he faced, where he faced them and when.

**Shrinkage.** Every term carries a ridge penalty. A player with few balls is pulled toward players like him: the
same batting role (from his batting position) or bowling role (pace or spin, by workload), the same experience, the
same age band and the same national side. The team term matters in internationals: an unknown Australian is a
better bet than an unknown player from a side that loses more. A prior from the player's Test record was tested and did not improve the holdout, so it is left out.

**Nothing looks ahead.** Role, experience, age and team are measured as of each delivery (role from the innings he
has played so far, experience from the balls he has faced or bowled so far). The holdout therefore never sees a
player's future, and "inexperienced" is not defined by players who failed and were dropped.

**Recency.** Each delivery is weighted by 0.5^(age / 9 years).

**Inactivity.** A player with no international in either format for over a year has his individual rating decayed
toward his prior by exp(-(gap - 1) / 2), gap in years.

**Uncertainty.** A diagonal Laplace approximation gives a posterior SD for every coefficient. The ± on a player's
rating redraws his own coefficients from it. It ignores the other terms, so it is somewhat too small.

## 4. How the settings were chosen

Two walk-forward folds: train on everything before a cut-off, score per-ball log loss on the window after it
(2024-07-01 to 2025-06-12: 56,537 balls, 104 matches; 2025-07-01 to 2026-11-02: 74,639 balls, 135 matches). An unseen
season takes its country's latest training season, which is what a projection does. Each variant is compared with
the base ball by ball, with a standard error clustered by match. This is a check of fit quality, not a betting
backtest.

| variant | half-life | log loss | v base | SE | verdict |
|---|---|---|---|---|---|
| base | 5 | 1.34123 | | | |
| no player terms | 5 | 1.34281 | +0.00159 | 0.00025 | worse |
| half-life 3 | 3 | 1.34241 | +0.00118 | 0.00012 | worse |
| half-life 9 | 9 | 1.34081 | -0.00042 | 0.00010 | better |
| half-life 14 | 14 | 1.34090 | -0.00033 | 0.00016 | better |
| players looser | 5 | 1.34134 | +0.00011 | 0.00006 | no clear difference |
| players tighter | 5 | 1.34127 | +0.00004 | 0.00005 | no clear difference |
| splits looser | 5 | 1.34144 | +0.00021 | 0.00006 | worse |
| splits tighter | 5 | 1.34127 | +0.00005 | 0.00006 | no clear difference |
| season walk looser | 5 | 1.34277 | +0.00154 | 0.00016 | worse |
| season walk tighter | 5 | 1.34049 | -0.00074 | 0.00013 | better |
| no other-format prior | 5 | 1.34118 | -0.00005 | 0.00011 | no clear difference |
| venue looser | 5 | 1.34140 | +0.00017 | 0.00007 | worse |
| venue tighter | 5 | 1.34115 | -0.00008 | 0.00005 | no clear difference |
| team prior tighter | 5 | 1.34113 | -0.00010 | 0.00005 | no clear difference |
| chase x wickets in hand | 5 | 1.34135 | +0.00012 | 0.00006 | no clear difference |
| no old-powerplay terms | 5 | 1.34121 | -0.00002 | 0.00003 | no clear difference |
| round 2: combined | 9 | 1.33996 | -0.00127 | 0.00020 | better |
| round 2: combined, season walk 3000 (adopted) | 9 | 1.33982 | -0.00141 | 0.00025 | better |

Adopted: half-life 9 years; penalties bat 40, bat_split 100, bat_type 150, bowl 100, bowl_split 100, cell 30, comp 5, cov 2, cs 200, gs 20, l0 1, rw 3000, team 30, venue 1000, venue2 2000.

On the holdout the adopted model scores 1.3398 nats per ball against 1.3991 for outcome
frequencies alone. It expected 236.7 runs and 8.17 wickets per innings; the innings
produced 236.7 and 7.72.

## 5. Conditions the model cannot see

Both sides of a match share a pitch and weather. The model measures that as the covariance between the two sides'
residual runs and wickets (actual minus expected, summed over each innings), on recent matches between full members.
It becomes a match-level shock on two axes of the logits, scoring shots and wickets, drawn once per simulated match
and applied to every ball. What is left of an innings' residual variance after sampling noise and the shared part
becomes an innings-level shock. The estimate is in-sample: fitted ground and season terms absorb part of a match's
conditions, so the match-level spread is if anything understated. This build:

* Match shock, scoring axis (SD, log-odds): 0.127 (about +15.61 runs per 50 overs)
* Match shock, wicket axis (SD, log-odds): 0.055 (wicket rate x 1.06 at +1 SD)
* Innings shock, scoring axis (SD): 0.065
* Innings shock, wicket axis (SD): 0.099
* Share of the unexplained scoring variance that both sides share: 0.88
* Same calculation on the walk-forward holdout (match scoring / match wicket / innings scoring / innings wicket SD): 0.173 / 0.065 / 0.061 / 0.266 from 254 innings; noisier, and it includes the error of ratings projected forward

**Home advantage.** ODIs are played on neutral ground often enough (World Cups, the UAE, associate events) to fit a batting-at-home and a bowling-at-home term separately, each with a spin part. Each player also has his own shrunk away-from-home split.
Australia, India, England, Pakistan against each other in average conditions, 10,000 simulated matches a pairing and setting: the same two XIs with one side at home, on neutral ground, and away.

* Win probability at home / neutral / away: 57.6% / 49.6% / 41.7%
* Total batting first at home / neutral / away: 292 / 284 / 274

**Pitch dial.** The simulator's pitch options move along those axes: *flat* is one match SD easier to score on and
harder to take wickets on, *hard to bat on* the reverse, *green seamer* adds the pace-wicket gap between the most
seam-friendly fifth of grounds and the average, *dry, turning* the same for spin. **Dew** shifts second-innings scoring by the 90th or 10th percentile of the real match-level chase advantage. These are scenario
dials, not forecasts for a match.

## 6. Player ratings ("true" stats)

Ratings are stated in **reference conditions**: every delivery between full members since 2023-01-01 is
re-evaluated with the player swapped in (as batter or bowler), keeping the real opponent, ground, era and match
state, and the model's probabilities are averaged. That gives context-neutral, opposition-adjusted rates.

* Batters: `avg` (runs per dismissal), `sr` (runs per 100 balls), balls per dismissal, boundary and dot rates.
  Bowlers: `avg` (runs per wicket), `econ`, balls per wicket.
* **Value** is runs against the average player on the same deliveries, with a dismissal priced in runs:
  the drop in expected runs still to come at that over and wickets down, from a resources table of recent first innings.
* Splits: *all* uses the player's own recency-weighted mix of phases; phase columns use every reference delivery of
  that phase; pace / spin, right / left-hander and home / away restrict to those deliveries.

## 7. Teams

* The default XI is a side's most recent XI. Sides pick differently by conditions, so each also carries its most
  recent XI in Asia, in SENA-type conditions and elsewhere, used for fixtures there when it is under two years old.
  The batting order is each player's mean order of appearance over his last ten innings.
* Bowling plans turn each bowler's usual overs by phase (last 30 matches, weighted to the recent ones) into whole overs that fill 10 / 30 / 10 with at most 10 a bowler. A captain rule then assigns the overs so nobody bowls two in a row.
* Team strength is not a sum of player ratings: the Teams sheet plays every pair of the 19 sides on neutral
  ground.

## 8. Simulator

One engine, `docs/models/cricket/sim.js`, runs in the browser and in the build (under node), so a published number
and a number you re-run come from the same code. Ball by ball: the class probabilities are the softmax of the sum of
the tables above for the current striker, bowler, over, wickets and match state, plus the match and innings shocks
and any dials. Strikers rotate on odd runs and at the end of each over; a wicket brings in the next batter.
A no-ball gives a free hit; the chase stops at the target; a tie stands as a tie.

Outputs: win and tie probabilities, totals batting first, first-ten-over runs, margins, fall of the first wicket, fours and sixes, and for every player the distribution of
runs, boundaries, wickets and runs conceded, plus the chance of being his side's top scorer or top wicket-taker in
its first innings.

## 9. Schedule

Fixtures are read from ESPN's cricket scoreboard API: series are found by scanning the calendar ahead, then each
match is read from its series. A fixture is mapped to the model's sides and ground (by name, then by city), the home
side is the one whose country hosts, and each side gets the announced XI once ESPN has it (within three days of the
start) or its most recent XI in comparable conditions. Each fixture is simulated before play; a match in progress
keeps its pre-match view. Sides without data are listed and not simulated.

## 10. Simulator replay

Each match is re-simulated with the real XIs, batting order of appearance, each bowler's real share of the bowling by phase, the ground and the side that batted first. The ratings were fitted on these same matches, so this checks that the simulator turns per-ball probabilities into realistic matches. It is not evidence of predictive skill, and the win-probability table flatters the model for the same reason.

323 matches since 2023-07-01, 300 simulations each:

| quantity | real | simulated |
|---|---|---|
| First innings of the match: mean total | 259.3 | 256.4 |
| First innings of the match: SD of totals | 69.6 | 69.6 |
| First innings: wickets lost | 8.4 | 8.3 |
| First innings: all out (%) | 43.7 | 43.2 |
| First innings: overs | 47.8 | 47.6 |
| Side batting first wins (%) | 46.7 | 47.2 |
| Match runs | 480.9 | 479.5 |
| Match runs: SD | 117.3 | 122.6 |
| Tie (%) | 0.9 | 0.8 |
| First innings: runs in overs 1-10 | 48.2 | 47.0 |

Pre-match win probability of the side batting first, in fifths:

| model said | matches | mean prediction | won |
|---|---|---|---|
| 9-31% | 65 | 22% | 18% |
| 31-42% | 64 | 37% | 33% |
| 42-51% | 66 | 46% | 39% |
| 51-63% | 63 | 58% | 70% |
| 64-92% | 65 | 73% | 74% |

## 11. Known weaknesses

* No market comparison has been run. Nothing here shows the model beats a price.
* Afghanistan is missing from the data. Associates play few matches and lean on their priors. On the holdout the model expected +11% wickets in matches with an associate side and +1% in matches between full members: treat associate projections with care.
* No ball tracking: "expected" means expected given the situation, opposition, ground and era, not line and length.
* Fielding, keeping and captaincy are not modelled separately.
* Day and day-night matches are not distinguished beyond each ground's second-innings term.
* Rain is not simulated: every match runs its full 50 overs, with no DLS.
* Bowling plans are fixed before the match and do not react to it. Batting orders do not flex.
* Default XIs are the last XI a side picked. Injuries, rest and retirements since then are not known until an
  announced XI arrives.
* A player's rating in a format rests on that format alone. T20 form is not used.
* The season and year environments are frozen at their latest values for projections.
* Uncertainty bands understate the true uncertainty.
