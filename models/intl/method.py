"""Write docs/models/<format>/data/method.md from the build's own numbers, so the page never quotes a stale figure.

Usage: python -m models.intl.method odi|test
"""
# %% imports
import json
import pickle
import sys

import pandas as pd

from models.intl.config import FORMATS
from models.intl.final_fit import hyper


def tuning_lines(rows):
    out = []
    for r in rows:
        if r.get("d_vs_base") is None:
            continue
        d, se = r["d_vs_base"], r["d_se"]
        verdict = "better" if d < -2 * se else ("worse" if d > 2 * se else "no clear difference")
        out.append(f"| {r['name']} | {r['half_life']:g} | {r['ll']:.5f} | {d:+.5f} | {se:.5f} | {verdict} |")
    return "\n".join(out)


def main(key):
    fmt = FORMATS[key]
    test = key == "test"
    ex = fmt.export
    m = pd.read_parquet(fmt.proc / "matches.parquet")
    with open(fmt.proc / "model.pkl", "rb") as fh:
        MD = pickle.load(fh)
    dg = json.loads((ex / "diagnostics.json").read_text()) if (ex / "diagnostics.json").exists() else {}
    H, lam = hyper(fmt)
    ho, rp = dg.get("holdout") or {}, dg.get("replay") or {}
    n_teams = len(json.loads((ex / "teams.json").read_text())["teams"])
    name = "Test" if test else "ODI"
    other = "ODI" if test else "Test"
    phases = ("new ball (the ball's first 20 overs), middle (21-55) and old ball (56-80); the second new ball at 80 overs starts the cycle again"
              if test else "powerplay (overs 1-10), middle (11-40) and death (41-50)")
    rp_rows = "\n".join(f"| {r['metric']} | {r['actual']:.1f} | {r['sim']:.1f} |" for r in rp.get("rows", []))
    cal = "\n".join(f"| {c['bin']} | {c['n']} | {100 * c['pred']:.0f}% | {100 * c['obs']:.0f}% |" for c in rp.get("result_calibration", []))
    shock = "\n".join(f"* {a}: {b}" for a, b in (dg.get("shock") or {}).get("rows", []))
    flow = "\n".join(f"* {a}: {b}" for a, b in (dg.get("flow") or {}).get("rows", []))
    used = lambda k: k in lam
    holdout_line = "" if not ho else (
        f"On the holdout the adopted model scores {ho['logloss']:.4f} nats per ball against {ho['logloss_marginal']:.4f} for outcome\n"
        f"frequencies alone. It expected {ho['innings_runs_expected']:.1f} runs and {ho['innings_wkts_expected']:.2f} wickets per innings; the innings\n"
        f"produced {ho['innings_runs_actual']:.1f} and {ho['innings_wkts_actual']:.2f}.")

    situation_odi = """| innings x over, innings x phase x wickets, innings x over x wickets | match situation: the intent and risk at every point of a 50-over innings (cell terms shrink toward the additive ones) |
| phase x required-rate bucket (second innings) | **chase pressure** |"""
    situation_test = """| innings (1-4) x over bucket, innings x ball phase x wickets, innings x over bucket x wickets | match situation: new ball, old ball, second new ball, top order or tail, in each innings of the match |
| overs already bowled in the match; the same x spin | **pitch wear**: batting changes as the surface ages, and spin gains more than pace |
| first innings: runs on the board x wickets; second innings: lead x wickets | **position**: sides bat differently at 450 for 3 than at 150 for 3 |
| third innings: lead x wickets | setting a target, including the push before a declaration |
| fourth innings: runs needed x wickets; runs needed per over left x overs left | **the chase or the block**: going for a target, or batting out time |
| pace / spin x overs the bowler has already bowled in the innings | **spell length** |
| a recognised batter with 7, 8 or 9 wickets down | batting with the tail |"""

    text = f"""# {name} ball-by-ball projection model: method

This page explains every step that produces the numbers on the site, what the columns mean and where the model
is weak. It is written by the build, so the figures below are this build's.

The model extends the T20 (IPL) workbook's approach to {'five-day' if test else '50-over'} cricket: one model of what happens on a single
delivery, fitted on every delivery at once, then a simulator that plays those deliveries out as whole matches.

## 1. Data

* Every men's {name} on cricsheet.org with ball-by-ball data: {len(m):,} matches from {m['date'].min().date()} to
  {m['date'].max().date()}, {MD['n']:,} deliveries in the fit{'' if test else f" ({int(m['reduced'].sum())} rain-shortened or abandoned matches are left out of the fit: an over means something else in a shortened game)"}.
  Cricsheet withholds Afghanistan's matches, so Afghanistan cannot be rated or simulated.
* One row per delivery with the state before it: innings, over, wickets, score, {'lead, target, overs bowled in the match so far, ' if test else 'target, '}striker,
  non-striker, bowler, balls the striker has faced, {'overs the bowler has bowled in the innings, ' if test else ''}outcome, extras and dismissal.
* Grounds are merged across spellings and renamings and mapped to a host country. Batting hand and bowling type come
  from the T20 workbook's curated file, then cricketdata's player table. Bowlers with no label are classed pace or
  spin by a classifier on how their deliveries behave and flagged as inferred.
* Upcoming fixtures and announced XIs come from ESPN's public cricket scoreboard API (section 9).

## 2. Outcome classes

Each delivery is one of 11 classes: wide, no-ball, bye or leg-bye, bowler wicket (bowled, caught, lbw, stumped, hit
wicket), run out, and bat runs 0, 1, 2, 3, 4, 6 (fives count as fours). How many runs a wide, no-ball, bye or run
out is worth, and which batter a run out removes, come from small tables of recent {name}s.

## 3. The probability model (one model, fitted jointly)

The chance of each class is a softmax over 11 logits (the dot ball is the reference). Each logit is a **sum of
additive terms**, all estimated together in one penalised multinomial logistic regression:

| term | what it captures |
|---|---|
{situation_test if test else situation_odi}
| phase x balls-faced bucket | the **settling curve**: a new batter scores slower and gets out more |
| bowling type; type x phase; type x left-handed batter | pace against spin overall and by phase, and the hand match-up |
| calendar year; year x phase; year x spin | the **era**: how the game as a whole has moved ({'more attacking batting, shorter matches' if test else 'two new balls, fielding rules, higher scoring'}). A random walk: each year is tied to the one before |
| host country; country x spin; country x phase | the **conditions** of a country: its pitches, its ball, its climate |
| host country x season; the same x spin | how a country's conditions drift. A random walk from that country's previous season |
| ground; ground x {'third and fourth innings' if test else 'second innings'}; ground x spin | ground effects on top of the country, {'late in the match' if test else 'chasing'}, and for spin |
| batting side at home; bowling side at home; each x spin | **home advantage** (a neutral ground is the reference) |
| batter: overall, {'v the new ball, v the old ball' if test else 'powerplay, death'}, v spin, first {fmt.early_bf} balls, away from home; v each of six bowling types | batter skill and its splits. The by-type split is shrunk hardest |
| bowler: overall, {'new ball, old ball' if test else 'powerplay, death'}, v left-handers, away from home | bowler skill and its splits |
| batter role, role x experience, age, team{', other-format record' if used('xf') else ''}; the same for bowlers | the **prior** a small sample shrinks toward |

Phases are the {phases}.

Because batter, bowler, ground, country, season and era terms are fitted at the same time, each is measured net of
the others. A batter's rating is adjusted for the bowlers he faced, where he faced them and when.

**Shrinkage.** Every term carries a ridge penalty. A player with few balls is pulled toward players like him: the
same batting role (from his batting position) or bowling role (pace or spin, by workload), the same experience, the
same age band and the same national side. The team term matters in internationals: an unknown Australian is a
better bet than an unknown player from a side that loses more. {'A player new to ' + name + 's also inherits a prior from his ' + other + ' record.' if used('xf') else 'A prior from the player' + chr(39) + 's ' + other + ' record was tested and did not improve the holdout, so it is left out.'}

**Nothing looks ahead.** Role, experience, age and team are measured as of each delivery (role from the innings he
has played so far, experience from the balls he has faced or bowled so far). The holdout therefore never sees a
player's future, and "inexperienced" is not defined by players who failed and were dropped.

**Recency.** Each delivery is weighted by 0.5^(age / {H:g} years).

**Inactivity.** A player with no international in either format for over a year has his individual rating decayed
toward his prior by exp(-(gap - 1) / 2), gap in years.

**Uncertainty.** A diagonal Laplace approximation gives a posterior SD for every coefficient. The ± on a player's
rating redraws his own coefficients from it. It ignores the other terms, so it is somewhat too small.

## 4. How the settings were chosen

Two walk-forward folds: train on everything before a cut-off, score per-ball log loss on the window after it
({'; '.join(f"{f['from']} to {f['to']}: {f['balls']:,} balls, {f['matches']} matches" for f in ho.get('folds', []))}). An unseen
season takes its country's latest training season, which is what a projection does. Each variant is compared with
the base ball by ball, with a standard error clustered by match. This is a check of fit quality, not a betting
backtest.

| variant | half-life | log loss | v base | SE | verdict |
|---|---|---|---|---|---|
{tuning_lines(dg.get('tuning', []))}

Adopted: {dg.get('adopted', '')}.

{holdout_line}

## 5. Conditions the model cannot see

Both sides of a match share a pitch and weather. The model measures that as the covariance between the two sides'
residual scoring and wicket rates (actual minus expected, per ball), on the holdout so that fitted ground and season
terms cannot soak it up. It becomes a match-level shock on two axes of the logits, scoring shots and wickets, drawn
once per simulated match and applied to every ball. What is left of the variance of a single innings after
sampling noise and the shared part becomes an innings-level shock. This build:

{shock}

**Pitch dial.** The simulator's pitch options move along those axes: *flat* is one match SD easier to score on and
harder to take wickets on, *hard to bat on* the reverse, *green seamer* adds the pace-wicket gap between the most
seam-friendly fifth of grounds and the average, *dry, turning* the same for spin. {'' if test else '**Dew** shifts second-innings scoring by the 90th or 10th percentile of the real match-level chase advantage. '}These are scenario
dials, not forecasts for a match.
"""
    if test:
        text += f"""
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

{flow}
"""
    text += f"""
## {'7' if test else '6'}. Player ratings ("true" stats)

Ratings are stated in **reference conditions**: every delivery between full members since {fmt.ref_since} is
re-evaluated with the player swapped in (as batter or bowler), keeping the real opponent, ground, era and match
state, and the model's probabilities are averaged. That gives context-neutral, opposition-adjusted rates.

* Batters: `avg` (runs per dismissal), `sr` (runs per 100 balls), balls per dismissal, boundary and dot rates.
  Bowlers: `avg` (runs per wicket), `econ`, balls per wicket.
* **Value** is runs against the average player on the same deliveries, with a dismissal priced in runs:
  {'the reference runs per wicket' if test else 'the drop in expected runs still to come at that over and wickets down, from a resources table of recent first innings'}.
* Splits: *all* uses the player's own recency-weighted mix of phases; phase columns use every reference delivery of
  that phase; pace / spin, right / left-hander and home / away restrict to those deliveries.

## {'8' if test else '7'}. Teams

* The default XI is a side's most recent XI. Sides pick differently by conditions, so each also carries its most
  recent XI in Asia, in SENA-type conditions and elsewhere, used for fixtures there when it is under two years old.
  The batting order is each player's mean order of appearance over his last ten innings.
* {'Bowling shares are each bowler' + chr(39) + 's share of the side' + chr(39) + 's overs by ball phase over its last 30 matches, weighted to the recent ones.' if test else 'Bowling plans turn each bowler' + chr(39) + 's usual overs by phase (last 30 matches, weighted to the recent ones) into whole overs that fill 10 / 30 / 10 with at most 10 a bowler. A captain rule then assigns the overs so nobody bowls two in a row.'}
* Team strength is not a sum of player ratings: the Teams sheet plays every pair of the {n_teams} sides on neutral
  ground.

## {'9' if test else '8'}. Simulator

One engine, `docs/models/cricket/sim.js`, runs in the browser and in the build (under node), so a published number
and a number you re-run come from the same code. Ball by ball: the class probabilities are the softmax of the sum of
the tables above for the current striker, bowler, over, wickets and match state, plus the match and innings shocks
and any dials. Strikers rotate on odd runs and at the end of each over; a wicket brings in the next batter.
{'An innings ends all out, on a declaration, when the target is reached or when time runs out; the follow-on, innings victories, ties and draws follow the laws.' if test else 'A no-ball gives a free hit; the chase stops at the target; a tie stands as a tie.'}

Outputs: {'win, draw and tie probabilities, first-innings totals and lead, second-innings totals, match runs, overs and the day the match ends,' if test else 'win and tie probabilities, totals batting first, first-ten-over runs, margins,'} fall of the first wicket, fours and sixes, and for every player the distribution of
runs, boundaries, wickets and runs conceded, plus the chance of being his side's top scorer or top wicket-taker in
its first innings.

## {'10' if test else '9'}. Schedule

Fixtures are read from ESPN's cricket scoreboard API: series are found by scanning the calendar ahead, then each
match is read from its series. A fixture is mapped to the model's sides and ground (by name, then by city), the home
side is the one whose country hosts, and each side gets the announced XI once ESPN has it (within three days of the
start) or its most recent XI in comparable conditions. Each fixture is simulated before play; a match in progress
keeps its pre-match view. Sides without data are listed and not simulated.

## {'11' if test else '10'}. Simulator replay

{rp.get('note', '')}

{rp.get('matches', 0)} matches since {rp.get('since', '')}, {rp.get('sims', 0)} simulations each:

| quantity | real | simulated |
|---|---|---|
{rp_rows}

Pre-match win probability of the side batting first, in fifths:

| model said | matches | mean prediction | won |
|---|---|---|---|
{cal}

## {'12' if test else '11'}. Known weaknesses

* No market comparison has been run. Nothing here shows the model beats a price.
* Afghanistan is missing from the data. Associates play few matches and lean on their priors.
* No ball tracking: "expected" means expected given the situation, opposition, ground and era, not line and length.
* Fielding, keeping and captaincy are not modelled separately.
* {'Day-night Tests are not flagged in the data and are treated like any other.' if test else 'Day and day-night matches are not distinguished beyond each ground' + chr(39) + 's second-innings term.'}
* {'The time model is in overs, not clock time: no sessions, no bad light, no new-day effect. A captain is taken to know how many overs the match has left.' if test else 'Rain is not simulated: every match runs its full 50 overs, with no DLS.'}
* {'Bowling changes follow shares and spell lengths, not the match: a captain does not turn to his best bowler when a stand builds. Batting orders do not flex (no nightwatchman).' if test else 'Bowling plans are fixed before the match and do not react to it. Batting orders do not flex.'}
* Default XIs are the last XI a side picked. Injuries, rest and retirements since then are not known until an
  announced XI arrives.
* A player's rating in a format rests on that format alone{' plus a prior from his ' + other + ' record' if used('xf') else ''}. T20 form is not used.
* The season and year environments are frozen at their latest values for projections.
* Uncertainty bands understate the true uncertainty.
"""
    (ex / "method.md").write_text(text)
    (ex / "schema.md").write_text(schema(test))
    print(f"{key}: method.md written ({len(text):,} chars)")


def schema(test):
    ph = "new ball / middle / old ball" if test else "powerplay / middle / death"
    return f"""# Data files

All under `data/`. Player ids are cricsheet register ids; an id starting `espn:` is a player in an announced XI
that cricsheet has no record of.

## schedule.json
`generated_utc`, `source`, `sims_per_fixture`, `fixtures[]`:

| field | meaning |
|---|---|
| `id`, `url` | ESPN event id and scorecard link |
| `date`, `start_utc`, `end_utc` | first day (local) and the feed's start and end times |
| `series`, `desc`, `status`, `status_text` | series name, "2nd Test", `pre` or `in`, the feed's status line |
| `A`, `B`, `home` | the two sides (home side first when the host is one of them) and which is at home (`A`, `B` or null) |
| `venue_name`, `city`, `country`, `venue`, `env_known` | the ground as the feed names it, its host country, the model's ground id (null if the model has no record of it) and whether the model has an environment for the country |
| `modelled`, `reason` | false with a reason when a side has no data |
| `lineups.A / .B` | `order` (11 ids, batting order), `plan` (bowling plan), `roles` and `names` for unrated players, `source` |
| `toss` | `winner`, `decision`, `bat_first` once known |
| `proj` | pre-match simulation: `p_A`, `p_B`, `p_draw`, `p_tie`, `match_runs`, `match_sixes`{', `lead1_mean`, `overs_mean`, `day[]` (share ending on each day)' if test else ''}, and per side `bat_first_total`, `t1_mean`, `t1_q` (5/25/50/75/95th percentiles), `top_bat[]`, `top_bowl[]` |
| `raw` | the feed fields kept so a later run can retain the fixture if the feed drops out |

## teams.json
`teams[]` in rating order: `name`, `short`, `region`, `matches` (last 30 months), `last_match`, `default` and
`by_region.{{asia,sena,other}}` lineups (`order`, `plan`, `date`, `country`, `from_match`), `squad[]` (`id`, `name`,
`apps`, `last_app`, `bat_pos`, `usage` = {'share of the side' + chr(39) + 's overs by ball phase' if test else 'overs per match by phase'}), and `rating`
(`rank`, `win_pct_fm`, `draw_pct_fm`, `win_pct`, `bat_first_total`, `bowl_first_total`, `net_runs`).
`pairs_neutral[]` holds every pair's neutral-ground probabilities. `region_of` maps a host country to its conditions
group. A bowling plan entry is `{{id, {'nb, mid, old' if test else 'pp, mid, death'}}}`: {'shares (%) of the overs with the ' + ph if test else 'whole overs in the ' + ph}.

## players.json
`players[]`: identity (`id`, `name`, `team`, `bat_hand`, `bowl_type`, `bowl_group`, `bowl_subtype`, `style_inferred`,
`age`, `last_played`, `in_squad`), then `bat` and `bowl` blocks. Each block has splits `all`, `p0`, `p1`, `p2`
({ph}), and `pace` / `spin` / `home` / `away` (batting) or `rhb` / `lhb` / `home` / `away` (bowling). A batting split
holds `avg`, `sr`, `out_pct`, `bnd_pct`, `six_pct`, `dot_pct`, `rv100`; a bowling split `avg`, `econ`, `sr` (balls per
wicket), `wkt_pct`, `dot_pct`, `bnd_pct`, `rv_over`. `vs_avg` is the same metric minus the average player's on the
same deliveries, `sd` the posterior SDs, `by_type` the batter's record against each bowling type, `career` and
`recent` the raw record, `role`, and `inactive_factor`. Top level: `avg_bat`, `avg_bowl` (reference averages),
`phase_labels`, `runs_per_wicket_ref`, `ref_since`, `pool_since`.

## venues.json
`venues[]`: `venue` (id), `name`, `city`, `country`, `matches`, `matches_since_2019`, `last_match`, then for
`all`, `pace`, `spin`, `early`, `late`: `*_rpo` (runs per over), `*_wpo` (wickets per over), `*_rpw` (runs per
wicket), `*_spo` (sixes per over) and each with `_mult` against the average full-member ground. `countries[]` gives
the same for each host country without a ground term; `neutral_reference` the averages.

## sim_params.json
Everything `../cricket/sim.js` needs: situation tables (`base`, `ipw`, `bf`{', `mo`, `mo_spin`, `pos12`, `lead3`, `need4`, `rr4`, `spell`, `tail`' if test else ', `chase`'}), bowling-type
tables, `env` per host country (plus `_default`), `venues`, `ha` (home advantage), `batters`, `bowlers`, role priors
and `team_prior` for unrated players, `extras`, `shock` (axes and Cholesky factors), `conditions` (pitch{'' if test else ' and dew'} dials){', `avail_q` (overs available by host country) and `flow` (declaration, follow-on and spell models)' if test else ''}.
Every vector has 11 entries in the order of `classes`.

## diagnostics.json, meta.json, ids.json, method.md
Diagnostics: `holdout`, `tuning[]`, `adopted`, `replay`, `shock`{', `flow`' if test else ''}. Meta: build stamp, counts, adopted settings,
file sizes, simulator speed. `ids.json`: `cricinfo` (ESPN / Cricinfo id to cricsheet id) and `names`.
"""


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        main(k)
