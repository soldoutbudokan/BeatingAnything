# Market selection

Research date: 2026-09-08. Selection is based on usable evidence and deployment feasibility; it is not a claim of a profitable strategy.

| Candidate | Free historical prices | Public sport data | Main limitation | Decision |
| --- | --- | --- | --- | --- |
| MLB pregame moneyline | A downloaded archive identifies FanDuel and five other books, with opening and latest price fields, 2021–2025 | MLB schedules, results, probable pitchers and play-by-play; public pitch-level data can support further work | Price capture times are missing; archive merges doubleheaders | Selected for an initial historical test and prospective monitoring |
| ATP tennis match moneyline | Tennis-Data has bookmaker prices, including Pinnacle and Bet365; accessible mirrors contain 2021–2023 | Match results and serve statistics; Match Charting Project has shot-level records | No FanDuel column or intraday timestamps in the verified files; charting availability can lag matches | Useful fallback, weaker evidence for the requested FanDuel test |
| Tennis set scores, spreads and totals | FanDuel offers such markets, but this investigation did not establish a sufficiently broad, free historical archive | The same tennis data could support a match-scoring model | Historical executable prices remain unverified | Deferred |
| NHL pregame markets | No comparable free FanDuel history verified in this investigation | MoneyPuck provides shot-level and goalie data | Odds history and permitted production use need resolution | Deferred |

## Why MLB moneyline

The user's target is a test against FanDuel prices. A history that names FanDuel is more relevant than treating another bookmaker's prices as interchangeable. Moneyline also provides a directly scored probability target for log loss and a simple settlement definition for historical analysis. This choice does not imply that moneyline is an easy market to beat.

The [MLB archive release](https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/tag/dataset) provides a [JSON download](https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/download/dataset/mlb_odds_dataset.json). The inspected file contains 13,121 records spanning 1,097 dates, from 2021-04-01 to 2025-08-16. Its fields include named bookmakers, `openingLine`, `currentLine`, results, scheduled start, teams, venue and game type. The downloaded 80,120,813-byte file has SHA-256 `3f952fd0bfae9f4f2d17e66692cb936ce6e1a5f6b415318012090c85933b882b`.

Two limitations affect what a backtest can establish:

- The release describes current prices as closing prices, but the scraper removes source timestamps and inspection found strong evidence of in-play contamination. Exclude every `currentLine` field from modeling, closing-line value and opening-to-close movement calculations. Opening prices also lack capture timestamps, so their availability at a reconstructed historical decision time is unverified.
- The scraper's same-date, same-team key can collapse doubleheaders. Exclude every team/date identified as a doubleheader from an independent MLB schedule; do not attempt to guess which game's odds survived.

The archive repository has no declared license in the inspected metadata. Fetch the data for analysis with source attribution; do not copy its implementation or commit the raw archive into this repository.

[FanDuel's MLB page](https://www.fanduel.com/research/mlb) links to moneyline, spread and totals markets and discusses additional props. Direct sportsbook access returned 403 during the investigation. Current market availability in editorial pages does not establish an automated live-quote connection.

Useful enrichment sources are [Baseball Savant's CSV documentation](https://baseballsavant.mlb.com/csv-docs), which describes pitch movement, location, speed, spin, extension, exit velocity, launch angle and player/game identifiers, and [Retrosheet game logs](https://www.retrosheet.org/gamelogs/index.html), which include starting pitchers and umpires. Test hypotheses such as opponent-specific pitch repertoire matchups, fatigue-dependent velocity or command changes, and recent bullpen availability. Lag these features before the decision time and isolate changes in measurement: Savant documents a 2026 change in the plate-location reference point. [Pybaseball's documentation](https://github.com/jldbc/pybaseball) also notes retrospective data revisions, so today's historical file is not a complete record of what was available then.

For comparison, [MoneyPuck](https://moneypuck.com/data.htm) offers substantial NHL shot data but distinguishes noncommercial from commercial use. [The Odds API's history](https://the-odds-api.com/historical-odds-data/) is paid-only, so it does not satisfy the zero-cost constraint.

## Verified tennis fallback

[FanDuel's tennis page](https://www.fanduel.com/research/tennis) links to its sportsbook markets. An inspected [FanDuel match article](https://www.fanduel.com/research/wimbledon-mens-final-prediction-pick-and-odds-for-sinner-vs-zverev) identifies a correct-set-score price as coming from FanDuel and states prices can change after publication. This verifies that the market family is offered; an article is not a live quote feed.

The [Tennis-Data original archive](https://www.tennis-data.co.uk/alldata.php) and its annual download endpoint were unavailable during this investigation, returning timeouts or server errors. An accessible [mirror of its data and notes](https://github.com/sitrucp/tennis_data_co_uk_echartsjs_viz/tree/main/tennis_data_co_uk) contains men's and women's 2021–2023 files plus partial 2024 files. For example, [2023 men's CSV](https://raw.githubusercontent.com/sitrucp/tennis_data_co_uk_echartsjs_viz/main/tennis_data_co_uk/2023m.csv) was successfully read.

The mirrored [source notes](https://github.com/sitrucp/tennis_data_co_uk_echartsjs_viz/blob/main/tennis_data_co_uk/tennis-data-notes.txt) define `B365W/L`, `PSW/L`, `MaxW/L` and `AvgW/L`, alongside match date, surface, court, round, ranking and result. The notes describe prices as generally the most recent before play starts. The verified schema has no FanDuel price or intraday capture time. Maximum prices across bookmakers must not be presented as obtainable FanDuel prices.

The original Jeff Sackmann ATP repository returned 404 during this investigation. An accessible [ATP data mirror](https://github.com/Kadantte/tennis_atp) contains annual main-draw, qualifying/Challenger and Futures files through 2026. Its [data dictionary](https://github.com/Kadantte/tennis_atp/blob/master/matches_data_dictionary.txt) confirms that `tourney_date` is usually the Monday of the tournament week and that `match_num` can be arbitrary. Neither establishes match chronology. A backtest must join independently dated results or restrict updates to completed earlier tournaments.

The [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject) provides match metadata, shot-by-shot records and aggregates for serve direction, return depth, return outcomes and shot direction. These could test specific matchup hypotheses: a player's serve placement against an opponent's return weakness, opponent-adjusted long-rally performance, and changes in second-serve vulnerability. These are hypotheses, not demonstrated edges. Historical features require the chart's publication time, ideally its first available repository commit, rather than the played date: contributors can chart an old match later.

The ATP mirror and Match Charting Project attribute their data to Jeff Sackmann/Tennis Abstract under CC BY-NC-SA 4.0. Free access does not confer unrestricted commercial use.

## Evidence required before a betting claim

Use chronological training and validation, preserve a final untouched historical test, and record every model and strategy variant tried. Compare probability accuracy with a margin-adjusted market baseline. Evaluate returns at one named book and state the settlement rules, missing-price filters and execution assumptions. Prospectively record timestamped FanDuel quotes, model versions and predictions before outcomes become known. Only that prospective record can resolve the historical archive's timing and execution gaps.
