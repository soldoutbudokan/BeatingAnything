# Next steps: creativity for the edge, brute force for the data

Written September 9, 2026. This file sets the research direction. It supersedes the "next research decision" in [PROGRESS.md](PROGRESS.md). PROGRESS.md stays accurate about what was done, where files live, which holdouts are spent and which gates must hold before any alert or wager. Read it for those things only.

## Why the first two days found nothing

Four experiments ran. All four were negative, and none of them had a reason to be positive.

Each one fitted a generic feature set (rest, travel, bullpen use, Elo, form) as a correction to a main-line price from the sharpest source available: Pinnacle openings or FanDuel no-vig moneylines. Those prices already contain public lagged stats. Regressing public stats against a sharp main line tests whether the market is efficient. It is.

The tennis experiments made Pinnacle the target. Pinnacle is the book the other books copy. The target was always FanDuel.

Most of the budget went to rigor around negative results: frozen protocols, provenance gates, a verifier that ran 32,556 checks on a model that placed four bets. That rigor is right once a hypothesis has shown something. Spent on hypotheses with no mechanism behind them, it bought nothing.

In short: brute force went into modeling, and creativity went nowhere. Reverse it.

## What an edge looks like

Here is the template, from a sharp bettor describing a tennis angle he used for years. Whether it still exists does not matter. Its shape matters.

1. **A structural fact about the sport.** Tennis is scored by sets. Games inside a lost set count for nothing. A player two breaks down in a non-final set gains nothing by fighting for it and loses energy he needs for the next set.
2. **A behavioral consequence you can measure.** Once double-broken, a big server gets broken again far more often than his baseline. The set ends 6-0 or 6-1 far more often than a static hold model says.
3. **A pricing model that ignores it.** The book priced "next game break" from the server's static hold rate. The same +500 before the match and at 0-4.
4. **An observable trigger before the price moves.** The second break.

Notice what is missing: no regression, no feature set, no walk-forward fit. The model is one conditional probability. The work was noticing.

Notice where it lives: a niche live market, not the match moneyline. Main lines get sharp flow and careful pricing. Niche, live, derivative and prop markets get a formula and little attention. Edges concentrate where the book's model is simplest and the sport's structure is most conditional.

## The rule

**Creativity finds the hypothesis. Brute force tests it.**

- Do not fit a model until you can write one sentence stating why FanDuel's price is wrong for a specific situation. No sentence, no fit.
- Collect data wide and greedy. Every market FanDuel posts, every timestamp, every game-state stream you can reach, before you know which hypothesis needs it. Collecting a market you never use is cheap. Missing the one you need costs a season.

## How to generate hypotheses

Work through each sport with these questions. Every hypothesis should trace back to one of them.

| Family | Question to ask | Examples of where it bites |
| --- | --- | --- |
| Scoring structure | Where does the scoreboard quantity diverge from what wins? | Sets vs games; aggregate vs leg; cut lines; tiebreak rules; overtime inclusion |
| Incentives | Who benefits from not trying, right now? | Dead rubbers, clinched seeds, bullpen preservation, position players pitching, week 18 rest, cup rotation, ranking points, prize thresholds |
| Information timing | What becomes public between the book's last reprice and the event? | Lineups, goalie confirmation, umpire assignment, weather, scratches, depth charts, tee times |
| Pricing-model simplicity | Which markets does the book price by formula? | Alt lines, player props, live game/set markets, correct scores, race-to markets, team totals derived from total and spread |
| Settlement rules | Where do FanDuel's rules differ from the fair price's assumptions? | Retirement voids, postponements, dead heats, "must complete" conditions |
| Attention | Which markets get no sharp flow? | Challenger game markets, WNBA props, lower-league corners, doubles |
| Correlation | Where does the book price legs as independent when they are not? | QB yards and team total; set score and total games; wind and every passing prop |

### Hypothesis card

One card per idea, under `docs/hypotheses/`, named `<sport>-<short-name>.md`. Keep each under a page.

```
Sport / market / book:
Structural fact:
Predicted behavior (measurable):
Why FanDuel's price ignores it:
Trigger (observable, timestamped):
Sport-side test: data source, cost, kill criterion
Book-side test: what odds at trigger time, forward or historical
Status: idea | sport-side confirmed | sport-side dead | book-side confirmed | book-side dead | forward test
Result (one paragraph, when dead or confirmed):
```

Rank cards by effect size times frequency times book-model simplicity times data availability. Test in that order.

## Seed hypotheses

None of these is verified. Some are well known and surely priced by now. They show the shape and start the queue. Generate more of your own; aim for thirty cards before testing any.

**Tennis**

- Double-break concession in a non-final set. Next-game break, set correct score 6-0/6-1, set total games under. Sport side is testable now on point-by-point data. Book side needs live FanDuel game and set markets.
- Fourth-set concession in best-of-five when up 2-1. Set 4 correct score, set 5 winner.
- Retirement settlement. FanDuel voids some match bets on retirement where other books pay. The fair price for the healthy player differs by rule. Compare FanDuel to Pinnacle after adjusting for each book's rule, for players with retirement history.
- Qualifier fatigue: main-draw first round after three qualifying matches in three days.
- Second match of the day after a rain backlog.

**Baseball**

- Position player pitching. Live over, team total, HR props. The trigger is margin, inning and yesterday's bullpen use; get in before the substitution, since the book's live model reprices after.
- Blowout substitutions. Stars pulled in the seventh have fewer plate appearances. Hit and total-base prop unders once the margin is large.
- Doubleheader game two. Props posted on the assumed regulars; the actual lineup rests them.
- Umpire assignment, published day-of. Strikeout props for pitchers who live on the edge of the zone; totals.
- Wind at Wrigley. Books move the total. Check whether HR props move as much.
- Openers. Strikeout props and first-five-innings markets on a listed starter who throws one inning.
- September. Eliminated teams, call-ups, resting veterans. Props posted on names not in the lineup.

**Football**

- Wind above 15 mph. Kicker field-goal props, long passing props, alt-total tails.
- Backup quarterback. The spread adjusts. Do receiver props adjust as much?
- Garbage time. Trailing-team receptions, live.
- Same-game parlay correlation. Compare FanDuel's SGP price for a combination to a simulated joint probability.

**Basketball**

- Star ruled out ninety minutes before tip. Secondary-usage props on FanDuel lag the news.
- Garbage time. Bench props, live, once the margin passes a threshold in the fourth.
- Late-season tanking.

**Hockey**

- Backup goalie confirmed at the morning skate. Moneyline and total lag.
- Empty net. Live over in the last two minutes when trailing by one; leading team's goal-scorer props.

**Soccer**

- Rotated lineups posted 60 to 75 minutes before kickoff in cup and dead-rubber matches. Player props, cards, corners.
- Long stoppage time since 2023. Live over after minute 85 if the book's clock model still assumes short added time.
- Red card. Live totals and cards.

**Book-side mechanisms, no sport model needed**

- FanDuel versus Pinnacle on derivative markets, continuously. Where FanDuel lags a Pinnacle move on a niche market, the lag is the edge. This is pure data brute force and may be the highest-probability route.
- Derived markets. Team totals and alt lines derived from the total and spread with a fixed distribution. Compare the implied distribution to the empirical one.
- Promotions and boosts. A boosted price above fair is positive expected value against FanDuel by construction. It is not modeling, but it is an edge against FanDuel and belongs in the record.

## Data: brute force here

Every hypothesis has two tests. Run them separately.

**Sport side** asks whether the phenomenon exists. It needs no odds, uses free historical data, and should kill or confirm an idea in an hour.

- Tennis point-by-point: Jeff Sackmann's `tennis_pointbypoint`, `tennis_slam_pointbypoint` and `tennis_MatchChartingProject` on GitHub. Check coverage years and tour levels before relying on them.
- MLB: the official statsapi feed already used in `beating/mlb.py` carries play-by-play, substitutions, umpires and weather. Retrosheet for deep history.
- NFL: the retained nflverse play-by-play, which carries weather and score state.
- NBA: `nba_api` play-by-play; the league's injury report.
- NHL: the league API's play-by-play, including empty-net flags.
- Soccer: understat, FBref, football-data.co.uk.

The test is whether the conditional probability differs from baseline by enough to matter at typical prices. If the effect is small at any plausible price, the card dies there.

**Book side** asks whether FanDuel's price ignores it at the trigger. This is the scarce resource.

- Free historical live and derivative FanDuel odds barely exist. Do not spend a week looking. Check two things already in hand: the retained NFL odds archive at `data/raw/nfl-source-audit/nfl_odds.duckdb` has 1.86 million rows for 285 games, so it likely carries many markets and time series; find out which. And check which derivative markets the Odds Gap export covers.
- Build the wide forward collector now, before the hypotheses are ready. Full snapshots of every FanDuel market, including props, alt lines and live game and set markets, every few minutes. The same markets from Pinnacle as the fair reference. A game-state feed with its own timestamps, so a trigger can be placed on the odds timeline. Store raw responses. `beating/monitor.py` is an append-only ledger that can hold this; `beating/covers.py` and `beating/timestamped_mlb.py` show how quotes were paired with official IDs.
- Cloud requests to FanDuel and Oddspedia were denied in the last session. A residential connection on the user's own machine may be allowed. Do not bypass blocks, challenges or terms. If collection needs to run locally, write the collector, test it on whatever is reachable, and hand it to the user with a one-line command.
- Live triggers need two clocks that agree: the game-state timestamp and the odds timestamp. Record both, and record the collector's own clock.

## Process: explore first, then confirm

Keep the rigor. Move it to where it earns its place.

**Exploration** is most of the effort. Many cards, cheap tests, look at the data freely, no frozen protocol, no audit script. A card dies in an hour or advances. Write the negative result in one paragraph on the card and move on. The comparison allowance in PROGRESS.md governs confirmatory tests, not this.

**Confirmation** starts when a card shows both a real conditional effect and a stale FanDuel price at the trigger. Then freeze the rule, run it forward on FanDuel paper bets with the existing ledger, and apply the promotion gates in [docs/monitoring.md](docs/monitoring.md) unchanged. Forward data is fresh for each card, so spent holdouts are not an issue.

Do not build verifiers, provenance gates or CI for a card that has not shown an effect.

## Do not

- Fit another regression of lagged public stats against a main line.
- Use Pinnacle as the target book. It is the fair-price reference.
- Reuse the inspected MLB, soccer or tennis holdouts as untouched tests.
- Spend budget on audit tooling for negative results.
- Enable any alert or wager. The gates in PROGRESS.md and docs/monitoring.md stand.

## What in this repo is worth reusing

- `beating/tennis_kernel.py` computes exact set and match distributions from hold rates. Extend it to take a game state (score in set, server, sets won) and return the remaining distribution. That is the fair-price engine for live tennis game, set and total markets, and it is most of the sport-side model for the tennis cards.
- `beating/monitor.py` for the forward ledger.
- `beating/covers.py`, `beating/timestamped_mlb.py`, `beating/tennis_source.py` for collector patterns and official-ID matching.
- `beating/mlb.py` for the statsapi client.
- The retained NFL odds DuckDB, local only, for whatever derivative markets it holds.

## First week

1. Read this file. Skim PROGRESS.md for file locations, runtime setup and the standing gates.
2. Write thirty hypothesis cards in one sitting. Do not test any yet. Rank them.
3. Pull the Sackmann point-by-point data and run the sport-side tests for the top tennis cards. One script, `# %%` cells.
4. Inventory the markets and timestamps in the NFL odds DuckDB and the Odds Gap export.
5. Start the wide forward collector, or hand the user a local one to run. Let it collect from day one, whatever else is happening.
6. Report: which cards show a sport-side effect, what book-side data each needs, and what is collecting.

If the account limit approaches, push the cards, the sport-side results and the collector. Those are the assets. Verifiers are not.
