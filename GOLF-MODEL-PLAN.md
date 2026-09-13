# Golf model plan

Written September 13, 2026. Status: plan only. No golf data has been collected and no card has been tested. The rules in [NEXT-STEPS.md](NEXT-STEPS.md) apply: no fit without a one-sentence mechanism, sport-side tests before book-side tests, no verifier for a card that has not shown an effect. The gates in [PROGRESS.md](PROGRESS.md) and [docs/monitoring.md](docs/monitoring.md) stand. No alert or wager is enabled.

## Short answer

Golf is worth doing. The reason given is not the reason to do it.

The premise has three parts. Two need correcting.

**"Courses and flight paths are public."** Partly. Ball flight (launch, apex, curve) is captured by radar on a few holes and is not public in bulk. Shot start and end coordinates, lie and distance are visible per player-round through the PGA Tour website's own API, which an open R client ([pgatouR](https://github.com/WalrusQuant/pgatouR)) wraps. That is undocumented site data, not a licensed dataset. Bulk ShotLink is not public; the academic ShotLink Intelligence program has been discontinued. Course geometry exists as OpenStreetMap polygons (fairway, green, bunker, water, hole path) at uneven quality, plus published yardages. Shot data from the DP World Tour, Korn Ferry Tour and LPGA is thinner still.

**"A sophisticated public-data model may beat the market."** This is the wrong target, and it is the same target the four failed experiments in this repo chose. Golf already has a sophisticated public model: Data Golf. The market has converged on it. Data Golf's own published test of its model against 11 books' closing lines since 2019 found 72-hole matchups at 0.1% ROI and single-round matchups at 1.7% at the threshold that maximised profit, and put the best blend at about 45% its model, 55% the market. A strokes-gained model built here would converge on Data Golf and then test whether the market is efficient against it. It is.

The same study found 3-balls at 9.7% ROI over 3,542 bets. That is the pattern NEXT-STEPS.md predicts: main lines are sharp, formula-priced derivatives are not. Golf's edge, if one remains, lives in how FanDuel turns a player's skill into 3-ball, 2-ball, matchup, finishing-position and cut prices under its own tie, dead-heat and withdrawal rules, and in what changes after those prices post: tee times, wind forecasts, withdrawals, and where a player stands on Saturday night.

**"Assuming the betting info is available."** Right to flag it. No free historical FanDuel golf odds exist. Two routes exist that the tennis and MLB work did not have. The PGA Tour site exposes odds, markets, matchups, finishes, props and 3-balls through the same API as scores and tee times, and FanDuel is the Tour's official betting operator; the book label in that feed has to be verified on your machine. Data Golf sells opening and closing lines from 11 books since 2019 for 72-hole matchups, round matchups and 3-balls on the $270-per-year Scratch Plus annual plan. The forward route is free and golf's calendar makes it fast: a full-field event posts roughly 250 to 350 derivative prices, the fall series has eight events starting Thursday, and the tours run nearly year-round.

So: yes to golf, no to ShotLink golf. Build the smallest fair-price engine that prices FanDuel's derivative golf markets correctly from the book's own main line, and test where the book's formula is wrong.

## What is public, checked September 13, 2026

| Source | What it gives | Cost and terms | Reachable from the cloud session |
| --- | --- | --- | --- |
| PGA Tour site API (pgatour.com GraphQL, wrapped by pgatouR) | Leaderboards, hole-by-hole scores, scorecards, fields with withdrawn and alternate flags, tee times with start tee and groups, shot-by-shot coordinates and distances, live group locations, hole-level scoring, hourly site weather forecast, betting odds and markets from the Tour's book partner, stats 2004–2026, past results for decades | Free, undocumented, no stated licence; polite rates only | No, blocked |
| ESPN golf pages and site API | Leaderboards, round scores, tee times | Free, undocumented | HTML yes, API no |
| Data Golf free pages | Rankings and skill estimates, live model, partial pre-tournament predictions, tools that show book prices | Free to read; full predictions need Scratch ($20/mo, $190/yr); API and historical odds archives need Scratch Plus ($30/mo, $270/yr; archives on the annual plan) | No, blocked |
| Data Golf API | Historical odds for outrights and for 72-hole, round matchups and 3-balls across 11 books since 2019 with opening and closing lines; historical round-level scoring, strokes gained and tee times for 22 tours; live odds from its tools; pre-tournament and live predictions | Scratch Plus; personal use | No, blocked |
| Open-Meteo | Forecast, ERA5 historical weather, and Previous Runs (the forecast as issued 1–7 days before each hour; most models archived from January 2024; historical forecasts from about 2022) | Free, no key, non-commercial | No, blocked |
| OpenStreetMap golf features | `golf=hole` path, `golf=fairway`, `golf=green`, `golf=bunker`, `golf=tee`, `golf=rough`, water | Free, ODbL; coverage varies by course | Overpass blocked |
| Kaggle PGA Tour sets (2010–2018; 2015–2022) | Round-level scoring and strokes gained | Free; check each licence | Not tested |
| The Odds API | Golf outrights only, FanDuel included | 500 free credits per month; history paid | Blocked |
| The Odds Gap board | Full-board snapshot, hourly; golf coverage unknown | Free personal reading; no sustained polling or redistribution | Blocked |
| FanDuel sportsbook | Everything | PerimeterX denial from the cloud, as in the tennis check | No |
| ShotLink bulk | Every shot, every event | Not available; academic program discontinued | — |

Every sport and odds host that matters is blocked from this container. Collection runs on your machine, as NEXT-STEPS.md already assumed. Do not bypass blocks, challenges or terms. Take ordinary denials as denials.

## Why not the shot-level model first

Three reasons, in order of weight.

1. **It reproduces the market.** Data Golf's blend test put the optimal weight on its own model at about 45%, the market at 55%. A public model built from less data than Data Golf has will not out-weight the market.
2. **The data rights are weak and the engineering is large.** Per-event shot pulls from an undocumented site API, digitised OSM polygons of uneven quality, no ball flight. Months of work before the first sentence about a wrong price.
3. **Course fit is small.** Data Golf runs a course-specific model and reports modest gains over its baseline. Any effect that survives is already in the book's price through that model.

Park it as card G9. Return to it only if a card that used the book's own skill line shows a residual that course geometry could explain.

## FanDuel golf markets and the fixed policy

FanDuel's dead-heat, withdrawal and tie rules below come from its published house rules and secondary summaries. Re-verify each on the current FanDuel rules page before freezing anything.

| Market | How FanDuel prices it | Settlement rule that matters | Fits the fixed policy (1.20–6.00, two-way overround 0–8%, 3% EV) | Role |
| --- | --- | --- | --- | --- |
| Outright winner | Full-field simulation, heavy overround | Withdrawal before teeing off: void | No: multiway, long prices | Skill source only (invert to per-player mean) |
| Top 5 / 10 / 20 | Same simulation, place terms | Dead heat: stake divided by players tied, times places | No: multiway | Later, needs a multiway policy |
| Make / miss cut | Simulation against projected cut | Cut rule varies: top 65 and ties for full-field events; top 50 and ties plus within 10 shots at the three player-hosted Signature Events; no cut at the other five | Two-way, yes, if overround ≤ 8% | Card G4 |
| First-round leader | Simulation, wave split, heavy overround | Dead heat | No: long prices | Wave signal check only |
| 72-hole matchup | Skill difference plus a formula | Withdrawal after starting: player completing more holes wins; before starting: void | Two-way, yes | Card G2, control for G3 |
| Round matchup (2-ball) | Skill difference for one round | Tie: push (two-way, no tie price) | Two-way, yes | Cards G1, G2, G5 |
| 3-ball | Skill for the three players in a pairing | Ties: dead heat, stake split by players tied for low | Three-way; the policy has no three-way overround rule yet | Cards G2, G3; the largest market |
| Live hole-by-hole, closest to pin, longest drive, birdies | IMG Arena Golf Event Centre on the official ShotLink feed | Various | Blocked: live | Card G8, low priority |

Two policy points to settle before any golf card reaches confirmation, and to register in writing before collection of its cohort:

- **Three-way overround.** The monitor's 0–8% cap is defined for two sides. 3-balls likely run 8–12% total. Register a three-way cap before the first forward cohort. Do not pick it after seeing which cap makes bets appear.
- **Ledger schema.** `beating.monitor` fixes `sport`, `bookmaker`, `market` to MLB, FanDuel, moneyline and takes two sides. A golf cohort needs event identity of tournament, round and group, two or three sides, and settlement by round scores. Extend the ledger only when a card reaches confirmation. During exploration, store raw responses with capture times and hashes and nothing else.

## The mechanism: price the derivative from the book's own main line

Do not estimate skill. Take it from the market, then test only the step where FanDuel turns skill into a derivative price.

1. Invert FanDuel's outright and 72-hole matchup prices into a per-player expected score relative to the field for the tournament. Use Data Golf's free skill estimates as a cross-check, not as the fair price.
2. Give each player a round-score distribution: an integer score with that mean and a spread calibrated on the sport side (about three strokes per round; calibrate by tour and course, do not assume).
3. Price each derivative with FanDuel's own rules.
4. Compare the no-vig derivative price to the derived one. The residual is the test statistic. A residual that is systematic, signed and tied to a mechanism is a card. A residual that is noise is a dead card.

The rule-correct formulas, with `d` the decimal price:

- **3-ball, dead heat.** Effective probability for player i is `P(i alone lowest) + P(i in a two-way tie for low) / 2 + P(three-way tie) / 3`. These three effective probabilities sum to one, so the market is a three-way market on them. EV is `d × p_eff − 1`. Ties are common: two equal players with a three-stroke spread tie about 9% of the time, and a 3-ball has a tie for low about 13% of the time at that spread, more when the spread is tighter (a quick integer-score simulation; calibrate on real rounds). A book that prices from strict win probabilities and adds a flat shade misallocates that tie mass, and the error lands on whichever player's tie share differs most from their strict-win share.
- **2-ball, tie is a push.** Effective probability is `P(i lower) / (1 − P(tie))`. EV per unit risked is `d × p_eff − 1` on the settled stakes.
- **72-hole matchup with a withdrawal rule.** Add `P(opponent withdraws after starting) × P(i completes more holes | that)` to i's win probability, and void probability for pre-start withdrawal. A skill-difference formula ignores this term.
- **Wave adjustment.** Shift each player's round mean by the wave's expected difficulty difference from the as-issued forecast, then reprice cross-wave round matchups, make-cut and first-round leader. Within a 3-ball or same-group 2-ball the shift cancels; that is why wave bias is not a 3-ball card.

This engine is a few hundred lines, in the spirit of `beating/tennis_kernel.py`: a distribution kernel and rule-specific settlement, no regression.

## Hypothesis cards

Ranked by effect size × frequency × formula simplicity × data availability. Copy each into `docs/hypotheses/golf-<name>.md` after adding your own and re-ranking. Under a page each. Test in this order.

### G3 3-ball dead-heat pricing

```
Sport / market / book: Golf, round 1–4 3-balls, FanDuel
Structural fact: Three integer scores; ties for low are common; FanDuel settles ties by dead heat.
Predicted behavior (measurable): P(tie for low) in a 3-ball is about 13% at a three-stroke spread, higher when the spread is tighter, and each player's share of the tie mass differs from their strict-win share.
Why FanDuel's price ignores it: A skill-difference formula prices strict win probabilities and applies a flat overround; tie share is not player-specific in that formula.
Trigger (observable, timestamped): 3-ball prices post after pairings; no trigger needed, the residual is static.
Sport-side test: Tour site hole-by-hole scores 2015–2025, group assignments from tee times; compute tie rates and per-player tie shares by skill gap and round-score spread. Cost: one script. Kill: the dead-heat correction moves no player's effective probability by more than one point against a strict-win price with a flat shade.
Book-side test: Forward from the Biltmore Championship; or Data Golf's 3-ball archive if purchased. Compare FanDuel no-vig 3-ball probabilities to dead-heat-correct ones derived from FanDuel's own outright-implied skill. Kill: mean absolute residual under 1 point with no sign pattern on the middle-skill player.
Status: idea
```

### G2 Withdrawal risk in matchups and 3-balls

```
Sport / market / book: Golf, 72-hole matchups, round 2-balls, 3-balls, FanDuel
Structural fact: Withdrawal after starting loses the bet (after three holes per the house rules); pre-start withdrawal voids. Injury and illness withdrawals cluster on players with recent withdrawals, recent injury news, and late-season low-status players.
Predicted behavior (measurable): P(withdraw after starting) for flagged players is several times the field base rate.
Why FanDuel's price ignores it: Matchup formulas use skill difference only; withdrawal enters the outright by field renormalisation, not the matchup.
Trigger (observable, timestamped): Field withdrawn flags, news items and the previous week's mid-round withdrawal, all timestamped on the Tour site API before the round.
Sport-side test: Field and leaderboard status 2015–2025; base rate of mid-round withdrawal overall and conditional on prior-90-day withdrawal, age, and fall-series status position. Kill: conditional rate under 3% or no separation from base.
Book-side test: FanDuel matchup and 3-ball prices for flagged players versus the derived price with the withdrawal term. Kill: the book's price already carries the term, or flagged players are absent from matchups (books often pull them).
Status: idea
```

### G1 Wave draw against cross-wave round markets

```
Sport / market / book: Golf, round 1 and 2 cross-wave 2-balls, make-cut, first-round leader, FanDuel
Structural fact: Half the field plays the morning wave Thursday and the afternoon Friday, the other half the reverse. Wind and green firmness differ by wave. Data Golf fits wave splits from tee-time residuals; splits of several strokes across two rounds occur.
Predicted behavior (measurable): The wave with the calmer as-issued forecast scores better by an amount predictable on Wednesday.
Why FanDuel's price ignores it: Round markets post soon after tee times with a skill formula; repricing to a forecast requires a manual trader or a model that reads weather. Whether FanDuel does is the question.
Trigger (observable, timestamped): Tee times (Tuesday evening) and the Wednesday forecast run. Open-Meteo Previous Runs gives the forecast as issued 1–7 days ahead from January 2024; the Tour site's hourly forecast is a second, timestamped source.
Sport-side test: 2015–2025 realised wind by wave from ERA5 versus wave residual scoring; then 2024–2026 as-issued Wednesday forecast versus realised wave split. Kill: as-issued forecast explains under 0.3 strokes of wave split on average.
Book-side test: Do FanDuel cross-wave 2-ball, make-cut and first-round-leader prices move between Tuesday post and Thursday open by at least 70% of the derived shift? If yes, dead. If no, forward paper on cross-wave 2-balls and make-cut.
Status: idea
```

### G5 Weekend markets and in-tournament state

```
Sport / market / book: Golf, round 3 and 4 2-balls and matchups, FanDuel
Structural fact: Weekend pairings are set by score. Groups late on Saturday contain the leaders; groups early contain players far back, some with nothing to play for and some chasing a top-10 or a FedExCup threshold.
Predicted behavior (measurable): Round 1–2 strokes gained carries information about round 3 beyond pre-tournament skill, and position relative to money and points thresholds predicts round 4 residuals.
Why FanDuel's price ignores it: Weekend 2-balls post late Friday and Saturday from a skill formula with at most a small form term.
Trigger (observable, timestamped): Round 2 and 3 final scores and the posted pairings.
Sport-side test: Round-level scores 2015–2025: regress round 3 and 4 residual on rounds 1–2 residual and on position bands, with pre-tournament skill fixed. Kill: coefficient under 0.1 strokes per stroke of prior residual and no position effect above 0.2 strokes.
Book-side test: Compare FanDuel weekend 2-ball no-vig probabilities to derived prices with and without the in-tournament term. Kill: the book's implied means already move with rounds 1–2 residual at 70% or more of the sport-side coefficient.
Status: idea
```

### G6 Fall-series incentives under the new top-100 line

```
Sport / market / book: Golf, FedExCup Fall 2-balls, 3-balls, make-cut, FanDuel
Structural fact: From 2026, full status requires the top 100 in FedExCup Fall points, down from 125; 101–125 get conditional status. Eight fall events decide it, plus Aon Next 10 and Swing 5 access to Signature Events.
Predicted behavior (measurable): Players within reach of the line play the fall harder than their skill rating implies; players safely above rest or coast; players out of reach withdraw or skip more.
Why FanDuel's price ignores it: A skill rating does not know a player's status position.
Trigger (observable, timestamped): The projected points list and bubble table on the Tour site each Monday.
Sport-side test: 2023–2025 fall residuals by distance to the then-125 line; the line moved, so treat the historical effect as shape evidence only. Kill: no residual beyond 0.15 strokes per round for bubble players.
Book-side test: Forward across the eight 2026 fall events; derived versus FanDuel 2-ball and make-cut prices for bubble players. Kill: no signed residual by end of the RSM Classic.
Status: idea
```

### G4 Make-cut markets and cut-rule variants

```
Sport / market / book: Golf, make/miss cut, FanDuel
Structural fact: The cut rule changes by event type; the cut line depends on the Friday afternoon wave's conditions; ties at the number all make it.
Predicted behavior (measurable): The projected cut line moves with the Friday wave forecast and with the rule; the tie mass at the line is large.
Why FanDuel's price ignores it: A cut price from a simulation with average weather and a fixed rule misprices bubble players on days with a strong Friday wave split or at events with the 50-and-within-10 rule.
Trigger (observable, timestamped): Wednesday forecast; event cut rule; Friday morning wave scoring.
Sport-side test: Historical cut lines versus wave split and rule. Kill: cut-line variance explained by wave under 20%.
Book-side test: Derived versus FanDuel make-cut prices; check overround first, since a cut market above 8% is blocked by policy.
Status: idea
```

### G7 Low-attention tours

```
Sport / market / book: Golf, DP World Tour, Korn Ferry Tour, LPGA 2-balls and 3-balls, FanDuel
Structural fact: Thinner fields, less data, less handle. FanDuel offers DP World Tour markets; 2-ball and 3-ball coverage on the other tours is unverified.
Predicted behavior (measurable): Larger and more variable residuals between derived and posted prices than on the PGA Tour.
Why FanDuel's price ignores it: Fewer traders on the product; a formula with a weaker skill input.
Trigger: None; static residual.
Sport-side test: Which tours have round-level scores and tee times on the Tour site API (Korn Ferry is tour code H) or elsewhere. Kill: no free round data with groups.
Book-side test: Same as G3 on those tours. Kill: FanDuel posts no 3-balls or 2-balls on the tour.
Status: idea
```

### G8 Live shot feed ahead of the book's reprice

```
Sport / market / book: Golf, live top-N, matchups and hole markets, FanDuel
Structural fact: A ball in the water is known before the hole score posts. Site group locations and shot details update through the round.
Predicted behavior: The public feed leads the book's derivative reprice by seconds to minutes on some markets.
Why it probably fails: FanDuel's live golf runs on IMG Arena's Golf Event Centre, which consumes the official ShotLink feed directly. The book sees the shot at least as early as the site does. Live markets are also blocked by the fixed policy.
Trigger: Shot event timestamp versus odds timestamp; needs both clocks and the collector's clock.
Test: Forward only, and only after a collector runs at one-minute cadence during play. Measure lag on top-20 and matchups after a penalty shot. Kill: median lag under 30 seconds or markets suspended on every shot.
Status: idea, low priority
```

### G9 Course geometry and shot-level fit

```
Sport / market / book: Golf, all markets
Structural fact: Fairway width, green size, hazard placement and approach distances interact with a player's dispersion.
Why it is parked: Data Golf's course-specific model already carries course fit into the market; effect sizes are small; data rights and effort are the largest of any card.
Revisit condition: A card above shows a residual whose sign tracks a course feature that the book's own skill line cannot see.
Status: parked
```

## Data plan

### Sport side, free, start now, on your machine

One script, `tools/golf_sport_side.py`, in `# %%` cells, one raw directory `data/raw/golf/` (ignored by Git; only manifests and hashes are tracked).

1. **Schedule and events.** Tour site schedule 2015–2026, tour code R; Korn Ferry (H) later if G7 survives its first check. Store tournament IDs, courses, dates, cut rule per event.
2. **Rounds.** For each event, hole-by-hole scores for the field, round totals, status flags (cut, withdrawn, disqualified, made cut but did not finish). Past results endpoints cover decades; hole-by-hole may not reach back as far. Record what each endpoint returns per year before relying on it.
3. **Tee times and groups.** Current-event tee-time endpoints are certain; historical groups may not be exposed. Check first. If the site does not keep historical tee times, the free fallback is ESPN's per-round leaderboard, and the paid fallback is Data Golf's round-level raw data with tee times.
4. **Weather.** Open-Meteo ERA5 hourly wind speed, gusts, direction and rain at each course's coordinates for 2015–2025; Previous Runs from January 2024 for the as-issued Wednesday forecast. Course coordinates from the Tour site or OSM.
5. **Fields and withdrawals.** Field lists with withdrawn and alternate flags per event, and the leaderboard status for mid-round withdrawals.
6. **Skill reference.** Data Golf's free rankings page for a per-player skill estimate, read by hand or captured weekly; Tour site strokes-gained stats as a fallback.

Sport-side runs for G1 to G6 each take under an hour once the pull exists. Write each result on its card in one paragraph.

### Book side: forward collector, plus one purchase to decide

**Forward collector, free.** `beating/golf_collect.py`, run from your machine by cron or a loop, starting this week. Every 15 minutes from Monday through Wednesday, every 5 minutes on tournament days, and every minute during play if G8 is ever pursued. Each cycle stores raw JSON with the collector's UTC clock, the response's own timestamp, the URL and a SHA-256 hash, and nothing else. Sources in priority order:

1. The Tour site's odds endpoints: outright field odds, market list, per-player lines. Verify the book label in the response first; FanDuel is the Tour's official betting operator, but the widget partner is a configuration value, not a promise. Record the label on every row.
2. FanDuel's own golf page, only if ordinary residential access returns it. Denied means denied.
3. Data Golf's free tool pages, for the sharp reference and for any FanDuel prices they show.
4. Tee times, field, weather and leaderboard from the Tour site on the same cycle, so triggers can be placed on the odds timeline.

Do not pair, normalise or ledger anything during exploration. Raw first. Pairing comes with the card that needs it.

**One purchase to decide: Data Golf Scratch Plus annual, $270.** It buys the historical odds archives (opening and closing lines for 72-hole matchups, round matchups and 3-balls across 11 books since 2019; check the per-book coverage page for FanDuel's start date), round-level raw data with tee times for 22 tours, and API access to its live odds and predictions. With it, G1 to G5's book-side tests run on history this month instead of waiting for eight fall events. Without it, they wait, and the forward sample through November is eight events. It does not replace the forward cohort: promotion gates require forward-only evidence either way. This repo has used no paid service so far. Your call. If bought: personal-use licence, raw files stay local and ignored, and check what "opening" and "closing" mean in that archive before treating them as such, as the Football-Data lesson in [docs/odds-source-investigation.md](docs/odds-source-investigation.md) requires.

### Clocks

Every book-side row carries three times: the collector's clock, the source's own update time if present, and the event's scheduled start. Every trigger row carries the site's publication time and the collector's clock. A trigger without a time before the odds row is not a trigger.

## Fair-price engine

Build `beating/golf_kernel.py` only after G3's sport-side test has produced tie rates and a spread. Contents:

- Integer round-score distribution per player from a mean and a spread; spread calibrated by tour, with a course-day multiplier from sport-side data.
- Joint distribution for two or three players in a group, with ties.
- Settlement functions: 3-ball dead heat, 2-ball push, 72-hole matchup with withdrawal and holes-completed rules, make-cut against a projected cut distribution.
- Inversion: from FanDuel's no-vig outright or 72-hole matchup probabilities to per-player means, by the same distribution.
- Wave shift as an additive term per player-round.

Keep it to pure functions and unit tests against a brute-force simulation, as `tools/validate_tennis_kernel.py` did for tennis. No regression, no feature set.

## Fit with the repo

- Cards: `docs/hypotheses/golf-*.md`, template from NEXT-STEPS.md.
- Exploration is free-form: no frozen protocol, no audit script, one paragraph per dead card.
- Confirmation for a surviving card: freeze the rule, register the three-way overround cap and the golf ledger schema, register the cohort in `beating.monitor` before the first forward event, then run paper bets under the unchanged gates: 1,000 settled paper bets over 90 days, positive lower bounds on haircut ROI and no-vig closing EV, negative upper bound on paired log-loss delta. A full-field event posts about 50 3-balls per round for two rounds and about 35 2-balls per round on the weekend, plus posted matchups, so the count is reachable in a season at a modest selection rate.
- The comparison allowance in PROGRESS.md governs confirmatory tests only. It stays at 13 until a golf protocol is registered.
- No golf alert, webhook or wager. The forward MLB runner stays manual.

## Timeline

| When | What |
| --- | --- |
| Now to Tue Sept 15 | Write the cards, add your own, re-rank. Start the collector on your machine before tee times post for the Biltmore Championship (Sept 17–20). Verify the odds book label, FanDuel page reachability, and the current FanDuel golf rules. Decide on the Data Golf purchase. |
| Sept 16–20 | Pull sport-side data (rounds, groups, fields, weather). Run G3 and G2 sport-side. Watch what the collector captures at Biltmore: markets, cadence, overround on 3-balls. |
| Sept 21–Oct 4 | G1, G5, G4 sport-side. If Data Golf was bought, run G3, G2, G5 book-side on the archive. Bank of Utah (Oct 1–4) is the second forward event. |
| Oct 5–Nov 22 | Baycurrent (Oct 8–11), Butterfield Bermuda (Oct 22–25), Mexico Open (Oct 29–Nov 1), WWT Championship (Nov 5–8), Good Good Championship (Nov 12–15), RSM Classic (Nov 19–22). Book-side residuals per event for every live card. G6 runs across all eight. Kill or advance each card by the RSM Classic. |
| Late Nov–Dec | DP World Tour season start for G7 if PGA Tour cards found residuals. Build `golf_kernel.py` for any surviving card. Register the golf protocol, ledger schema and three-way cap. |
| January 2027 | First frozen forward cohort at the season's first full-field events. The 90-day, 1,000-bet gate then runs through spring. |

## Verify on your machine before relying on any of it

These could not be checked from the cloud session.

- [ ] The Tour site odds endpoints: which book, which markets, update cadence, whether prices carry a book timestamp.
- [ ] FanDuel golf page access from ordinary residential access, and the current golf house rules: pre-start withdrawal void, three-hole withdrawal rule, 2-ball tie push, 3-ball dead heat, top-N dead heat, 72-hole matchup withdrawal rule, weather-shortened tournaments.
- [ ] Typical FanDuel overround on 3-balls, 2-balls, make-cut and 72-hole matchups.
- [ ] Whether the Tour site keeps historical tee times and groups; how far back hole-by-hole scores go.
- [ ] Open-Meteo Previous Runs availability of gusts and wind at the lead times needed; its non-commercial terms.
- [ ] Data Golf per-book historical coverage dates, whether FanDuel is in the archive, and what its opening and closing fields mean.
- [ ] Which tours FanDuel posts 2-balls and 3-balls for beyond the PGA Tour.

## Do not

- Build the shot-level or course-geometry model first.
- Fit a strokes-gained rating and regress it against FanDuel's 72-hole prices. That is experiment five of the same kind.
- Treat Data Golf's numbers as the model to bet. They are the market's anchor and a reference.
- Relax the price band or overround rule to admit outrights and top-N. Register a multiway policy first if those markets are ever wanted.
- Scrape through a block, a challenge or a location check. Record the denial and move on.
- Let the collector fall behind the calendar. Missing the Biltmore Championship costs one of eight fall events.
