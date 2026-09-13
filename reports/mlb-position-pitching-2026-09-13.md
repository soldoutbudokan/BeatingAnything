# MLB position-player pitching: 2025 sport-side screen

**Result: sport-side confirmed.** The exact-state comparison has 112 exposed innings and 237 ordinary-reliever controls. Position-player innings scored 1.304 runs versus 0.639 in controls weighted to the exposed inning/margin distribution: **+0.664 runs per inning** (descriptive game-cluster bootstrap 95% interval +0.173 to +1.155). The card's fixed screen is 100 exposed innings and 0.5 additional runs. The minimum sample is reached. No FanDuel pricing edge is established.

## Scope and comparison

The complete 2025 regular season was chosen before computing the run comparisons. Official schedule inning scores enumerate every regulation inning starting with a defensive deficit of at least eight, or a ninth-inning lead of at least ten. Only preceding inning scores select states; final margins do not. Suspended/resumed, postponed, and incomplete games are excluded. 2421 completed games remain; 245 full game feeds cover eligible states plus every identified position-player appearance in those games.

Exposure means a position player **starts the inning**. Controls start with ordinary relievers; game starters and two-way players are excluded. Both groups start with zero outs and empty bases. The outcome is all runs in that half-inning, including subsequent pitching changes. Exact matching uses inning number, top/bottom, and signed defensive margin. Each control gets its cell's exposed/control count weight. This avoids comparing blowouts with competitive innings. It does not control batter substitutions, reliever ability, prior bullpen use, or manager selection, so it is descriptive rather than a causal estimate. The 2025 data are now inspected exploration, not an untouched holdout.

| Sample | Innings | Mean runs |
|---|---:|---:|
| All qualifying position-player starts | 128 | 1.266 |
| All qualifying ordinary-reliever starts | 561 | 0.578 |
| Matched position-player starts | 112 | 1.304 |
| Matched controls, exposed-state weights | 237 | 0.639 |

16 exposed innings have no exact control and do not enter the adjusted contrast. 4 control innings later used a position player; retaining them avoids excluding controls because of an ensuing pitching change. Removing these contaminated controls as a sensitivity yields +0.781 runs with 112 matched exposures. The primary probability of at least one run is 46.4% versus 30.8%; this is an empirical rate, not a wager recommendation.

## Identity, inherited runners, and clocks

The season pitching index supplies non-pitcher position fields, checked against each game's `gameData.players.primaryPosition`. Neither low pitch speed nor poor outcomes define a position player. `TWP` excludes Shohei Ohtani. These are retrospective identity fields, not an archived active-roster designation at announcement time.

131 distinct position-player appearances contribute 142.000 official innings and 181 charged runs. These aggregate rates are not used as the matched result. There are 25 mid-inning entries and 16 appearances with inherited runners: 27 inherited, 7 scored. Official charged runs and inherited-runner scoring are retained separately in the JSON; inherited runs are not incorrectly charged to the incoming pitcher. The clean-start comparison excludes those entry states and extra innings.

131 appearances have both a substitution-action timestamp and a first-pitch timestamp. Their recorded start-time gap has median 27.108 seconds; 24 are at most one second. These retrospective event fields do **not** establish when an announcement became available to a collector or bettor. Full event times, types, IDs, entry outs, and base occupancy are retained for future live alignment.

Eligibility: extra innings; trailing by eight or more; or leading by ten or more in inning nine. See [MLB's April 2026 explanation](https://www.mlb.com/news/mlb-two-way-player-rules).

## What advances this card

Capture FanDuel live inning/team totals, prices and suspension status on both sides of an incoming-position-player announcement, together with independently observed game-feed publication times and first pitch. Demonstrate an available stale quote before testing return. No historical feed timestamp here proves that opportunity, and no alert or wagering gate changes.

Reproduce with `python tools/explore_mlb_position_pitching.py`. Raw official responses remain in ignored `data/raw/mlb-position-pitching/`; this report's JSON contains rows and source hashes. Sources are the [official 2025 pitching index](https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season=2025&gameType=R&sportIds=1&playerPool=ALL&limit=2000), [schedule](https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2025&gameType=R&hydrate=linescore), per-player game logs, and per-game feed URLs retained in each appearance row.
