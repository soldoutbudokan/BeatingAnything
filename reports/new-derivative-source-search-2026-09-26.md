# New derivative-price sources — September 26, 2026

**A new NHL shots-on-goal archive has been acquired and passes the initial price inventory.** All 285 files match the pinned publisher hashes. They supply 3,584 distinct FanDuel paired main lines across 272 games, with valid American prices and update times before listed start. A second MLB archive contains actual pitcher-prop prices and outcomes, but only model-selected bets; it is deferred.

Existing inventories were checked first, including `docs/odds-source-investigation.md`, `reports/edge-search-2026-09-22.md`, and the NHL empty-net source report. Neither source below appears there. This search did not run publisher collectors, use credentials, purchase data, or evaluate strategies.

## 1. NHL: ldinan-git/sports-betting-ops

Repository pin: [`42cf1f81bc302642ddcc9e88ce2e98c1057bc74d`](https://github.com/ldinan-git/sports-betting-ops/tree/42cf1f81bc302642ddcc9e88ce2e98c1057bc74d). The recursive tree is complete, not truncated. The exact raw folder is:

`bet-ops/odds_api_responses/player_props/output/icehockey_nhl/player_props/`

It contains **285 files named `icehockey_nhl_player_props_*.json`, totaling 73,576,177 bytes, across 33 filename dates from November 26, 2024 through January 25, 2025**. There is also one differently named `game_odds` file; do not count it as a prop board. Twelve identical 243-byte files are quota-error responses; the other 273 parsed successfully and contain 273 distinct event IDs. The repository also contains 31 full aggregated NHL daily CSVs and 31 selected-best-prop CSVs. Use the raw JSONs, not the selected-best files.

| Raw filename month | Files before error exclusions |
| --- | ---: |
| November 2024 | 25 |
| December 2024 | 144 |
| January 2025 | 116 |

All source files were acquired from pinned public GitHub URLs with at most two concurrent transfers, rate 2/s, no retries, and all publisher error payloads retained. Each file's size, Git blob and SHA-256 were verified. The ignored local archive is `data/raw/nhl-shot-archive-2026-09-26/`. Its [manifest](../data/raw/nhl-shot-archive-2026-09-26/manifest.json) records URLs, hashes, source errors and artifact hashes; [events.csv](../data/raw/nhl-shot-archive-2026-09-26/events.csv) supplies fixture metadata; [fanduel-mainline-pairs.csv](../data/raw/nhl-shot-archive-2026-09-26/fanduel-mainline-pairs.csv) supplies the pairs.

The full FanDuel mainline inventory has **3,584 paired event/player/line keys**, with no repeated or missing side inside those markets, no invalid American price, and no negative overround. All 3,584 market timestamps precede listed start: minimum lead **40.1 minutes**, median **602.48**, maximum **805.78**. Quote counts are **183 November, 1,895 December, 1,506 January**. There are **9,881 FanDuel alternate-shot outcomes**; these are inventoried only. These counts establish price coverage, not outcome identity, settlement correctness or accepted wagers.

The [collector](https://github.com/ldinan-git/sports-betting-ops/blob/42cf1f81bc302642ddcc9e88ce2e98c1057bc74d/bet-ops/odds_api_responses/player_props/scripts/get_player_props.py) requests a day's events, loops over them with a 300-event ceiling, and dumps each response. It requests **American odds**. The [configuration](https://github.com/ldinan-git/sports-betting-ops/blob/42cf1f81bc302642ddcc9e88ce2e98c1057bc74d/bet-ops/configuration/api_parameters.json) includes US/US2 bookmakers, main and alternate shots markets. There is no bet-selection or outcome filter in this raw-response path. This establishes a substantially fuller quote universe than published picks, although it does not establish complete coverage of all NHL dates or players.

Raw schema: event `id`, `commence_time`, `home_team`, `away_team`; bookmaker `key` and `title`; market `key` and `last_update`; outcomes `description` (player), `name` (Over/Under), `point` (line), and `price`. Pair by event/book/market/player/line, never by player name alone.

Three files were downloaded and their Git blob hashes matched the pinned tree:

| Raw filename after `icehockey_nhl_player_props_` | FanDuel paired main lines | FanDuel main update UTC | Listed start UTC |
| --- | ---: | --- | --- |
| `Boston Bruins_Vancouver Canucks_20241126.json` | 11 | 2024-11-26 18:54:13 | 2024-11-27 00:00:00 |
| `Washington Capitals_Los Angeles Kings_20241222.json` | 13 | 2024-12-22 14:27:59 | 2024-12-22 22:10:00 |
| `Vancouver Canucks_Washington Capitals_20250125.json` | 14 | 2025-01-25 16:15:43 | 2025-01-26 03:00:00 |

For a concrete price example, the [Boston/Vancouver file](https://github.com/ldinan-git/sports-betting-ops/blob/42cf1f81bc302642ddcc9e88ce2e98c1057bc74d/bet-ops/odds_api_responses/player_props/output/icehockey_nhl/player_props/icehockey_nhl_player_props_Boston%20Bruins_Vancouver%20Canucks_20241126.json) contains **David Pastrnak 3.5 shots, FanDuel Over −168 / Under +128**, both in the same `player_shots_on_goal` market updated 305.8 minutes before listed start. The same board has Brock Boeser 2.5, Over +112 / Under −146. These are actual stored prices, not reconstructed opposites.

The December and January samples additionally contain **49 and 48 FanDuel `player_shots_on_goal_alternate` outcomes**, respectively, all Over-only. For example, the December board includes Adrian Kempe Over 1.5 at −460, Over 2.5 at −148, Over 3.5 at +172, and Over 4.5 at +360. This makes a main-versus-tail distribution diagnostic possible without inventing alternate Under quotes. No model or threshold has been fitted to this source.

**Verified outcome path:** ESPN's public [date scoreboard](https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=20241126) maps Vancouver at Boston, November 27 00:00 UTC, to event **401687944**. Its [summary endpoint](https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary?event=401687944) supplies team/player IDs, participation/ice time and player `shotsTotal`; Pastrnak has 3 and Boeser 0. Player `shotsTotal` sums to the displayed team totals, Boston 33 and Vancouver 15. This verifies one outcome join, not all 273 candidate payloads.

**Important schema trap:** in ESPN's hockey player statistics, the displayed label `SOG` maps to **`shootoutGoals`**, not shots on goal. The required shots field is **`shotsTotal`**, displayed `S`. Parse by the supplied `keys` array rather than abbreviations or fixed offsets.

Remaining qualification work: reconcile listed versus actual games and player identity; check overtime, participation and void settlement; retain missing outcomes; and fix any quote-age rule before outcomes. There is no explicit collector timestamp or near-start closing series in the payloads. Market update times and retrospective GitHub retention support historical research but do not prove accepted wagers or every quote's executable availability. All raw price payloads were inventoried, but only one game's outcome join was inspected. January outcome values were not opened here, so a later-period test can still be declared before those outcomes are examined; the data span remains short.

Reproducibility: full tree retained in the ignored archive as `source-tree.json`; all 285 raw files preserve their publisher filenames. The temporary inventory program is `/tmp/audit_nhl_shot_archive.py`; outcome sample `/tmp/new-derivative-nhl-espn-summary.json`. Temporary files are not durable project artifacts. Sample SHA-256 values, in table order: `0a291f2d1e77883fca8775c42cc225b0d04934676cd1c8522e443e8de9a981bf`, `6105ed0053e281fd1c598fe72bde360b4eadd554f0863ad16eeb5fed648c3f7f`, `3128626c8aa19a22dc7621c53f68ffe7987a7d23da5c6fe4b1cb7060c6a21d0b`.

## 2. MLB: s-mujtaba-haider/MLB — deferred

Repository pin: [`dbaee4f50db5aa07e26a752e64150334e9b0772e`](https://github.com/s-mujtaba-haider/MLB/tree/dbaee4f50db5aa07e26a752e64150334e9b0772e). The actual downloadable [reports/bets.parquet](https://github.com/s-mujtaba-haider/MLB/blob/dbaee4f50db5aa07e26a752e64150334e9b0772e/reports/bets.parquet) is 17,195,415 bytes. Reading it yields **45,426 rows**, including **5,158 pitcher-strikeout bets and 2,238 pitcher-outs bets**. It carries `price`, `book`, `snapshot_ts`, `commence_time`, `lead_min`, `event_id`, `espn_id`, `athlete_id`, `stat_value`, `result`, and model-selection fields. Thus this is an actual price/outcome artifact, not merely scraper code.

However, the publisher identifies it as the bets its model selected for out-of-sample evaluation. Full paired raw boards are absent from the public tree. Selected prices cannot establish a representative market calibration or independently evaluate a new selection rule. Claimed chronology and feature correctness have not been independently audited; do not inherit the publisher's forecast probabilities or conclusion as ground truth. Deferred in favor of the fuller NHL boards; no further MLB acquisition or performance analysis was performed. Download SHA-256: `4a1d904ef8f361aca1c6ccaa00bd88ff2427753b8fde52fc41cca6703d6b95d0`.
