# Research runway and NBA source feasibility — 2026-09-13

**Subsequent execution completed:** this document preserves the earlier source checkpoint. The [NBA result](../reports/nba-creator-assists-2026-09-13.md) is now unresolved with 25 exposures and +0.96 assists. The broadened golf/tennis/rugby/CFL batch and current next action are in [PROGRESS.md](../PROGRESS.md); do not restart the completed experiment from the historical plan below.

The user's latest instruction changes the active queue: research markets with substantial season ahead. Preserve the positive MLB position-player pitching result, but defer its 2026 price-collection priority. NFL's season is underway; NBA props offer a second pathway for the coming season. Calendar runway is an operational choice, not evidence of an edge.

| Market | Verified calendar | Runway from September 13 |
| --- | --- | --- |
| NFL | Week 18: January 9–10, 2027; Super Bowl: February 14. [NFL Football Operations](https://operations.nfl.com/calendar-events/nfl-important-dates) | 119 days to the final regular-season date |
| NBA | Regular season: October 20, 2026–April 11, 2027. [NBA key dates](https://www.nba.com/news/key-dates) | 37 days until opening; 210 days until the regular-season end |

Dates were checked on September 13, 2026. The NBA page is an official release updated August 19. The NFL calendar says dates are subject to change. Do not let the earlier MLB queue regain priority merely because its sport-side result was positive.

## NBA missing-creator assists: a concrete historical path

The existing [hypothesis card](hypotheses/basketball-star-out-assists.md) predicts more assists for a secondary ball-handler preidentified from earlier games when the primary creator is officially ruled out. Its fixed cheap-screen threshold remains at least 100 player-games and at least one additional expected assist, with minutes and assist rate reported separately. No assist-effect comparison was run in this source-feasibility batch.

The historical report-timestamp prerequisite is now partly resolved. The [akng8 injury-report archive](https://github.com/akng8/nba-injury-scraper/tree/02cfe44f7453182eb4a29283285a7af64f5e3c9a/pdfs) contains 12,168 original PDF files on 509 distinct dates across the 2022–23, 2023–24 and 2024–25 seasons. There are 3,970 PDFs in the 2024–25 date range. This is a file inventory, not a claim of complete hourly coverage or 3,970 independent exposures. Pin the archive at commit `02cfe44f7453182eb4a29283285a7af64f5e3c9a`; its recursive tree was not truncated.

One [original NBA report](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2024-10-22_05PM.pdf) downloaded directly with HTTP 200. Its 69,637 bytes have SHA-256 `9a2b6d1a55f100a03c519e3bb725fdf941c204b070197952d734479c8e18a42c`. Its Git blob SHA-1 `e3360f049de9e56687ee2075eba7cc05a66129fe` exactly matches the pinned archive copy. The PDF was text-extracted and visually inspected.

**Use the timestamp inside each PDF.** The sample filename says `05PM`, but every page's header says **10/22/24 05:30 PM**. Treating the URL hour as the report time would invent a 30-minute information advantage. The sample also contains tomorrow's games, multi-page rows and `NOT YET SUBMITTED` teams. File presence is not proof a particular team's information was available, and an archive downloaded today does not establish the original public posting latency.

The [official injury-report page](https://official.nba.com/nba-injury-report-2025-26-season/) also downloaded directly with HTTP 200. The old 2024–25 page redirects to the current season; use pinned PDF URLs for historical inputs. Retain raw reports privately in ignored `data/raw/`; do not copy their contents into the public repository.

## Player results are also accessible

The NBA Stats-derived [SportsDataverse boxscore release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_boxscores) supplies a compact historical outcome and prior-role input. Its publisher identifies the original endpoint as `boxscoretraditionalv3` in the [dataset documentation](https://github.com/sportsdataverse/hoopR-nba-stats-data/blob/85371cb7901e9a53437c87b26f11576d8450be9a/docs/datasets/player_boxscores.md).

| Downloaded input | Bytes | SHA-256 |
| --- | ---: | --- |
| `player_boxscores_2025.csv` | 5,507,594 | `7371d222692fee1c083913d813b125f885c4e53b6f3daaecb7270299913e9716` |
| `nba_stats_schedule_2024.csv` | 426,838 | `ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26` |

Both ordinary downloads returned HTTP 200 and matched their GitHub release-asset SHA-256 digests. The boxscore asset ID is `513303584`, last updated August 13, 2026. The schedule asset ID is `488098414`. Local copies are in ignored `data/raw/nba-source-feasibility/`.

The boxscore file contains 34,928 player rows in 1,314 games. Filtering IDs beginning `00224` gives **32,515 rows in all 1,230 regular-season games**, two teams per game and no duplicate game-player rows. It contains stable NBA person IDs, team IDs, minutes, assists, positions and non-playing comments. Of these rows, 6,209 have blank minutes. Positions are populated for the five starters and blank for many bench players: do not equate a blank position with absence, infer a backup's role from the eventual starting lineup, or exclude a zero-minute outcome after selecting a player in advance.

The [schedule release](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_schedules) supplies a game-date and team join: `nba_stats_schedule_2024.csv` has 2,460 regular-season team rows for the same 1,230 games, dated October 22, 2024–April 13, 2025. These are retrospective team game logs with calendar dates, not precise tip times.

**Check game IDs, not matching filename years.** The current boxscore naming uses season-ending years, while this legacy schedule asset uses the starting year. The downloaded `nba_stats_schedule_2025.csv` instead contains `00225`/`00425` games from 2025–26 and is unsuitable for the 2024–25 join. This mismatch was caught before outcome analysis. Keep ten-character game IDs as strings. A direct historical NBA CDN boxscore sample returned HTTP 403; there is no reason to retry that blocked route when these publisher assets already work.

## Next bounded experiment

1. Before reading outcome differences, predeclare one fixed 2024–25 regular-season cohort and prior-role rule. A suitable implementation must select a creator and secondary handler using only games completed before each prospective trigger, require a minimum prior sample, reset or exclude roster changes, and freeze that pair before the injury-status join. Prior minutes and assist involvement may define a role; eventual game minutes, assists and starting status may not.
2. Parse a small fixed batch of archived reports first and validate the PDF header time, game date, team, player, status and cross-page continuation. Resolve NBA person IDs conservatively. Exclude unresolved names, unsubmitted teams and ambiguous timestamps. Match the report's game date, not merely the PDF's calendar date. Do not infer `Available` from a missing row without a documented complete team report.
3. Freeze the exposed/control definitions and timing window before expansion. The exposure requires an official `Out` entry known before tip. A conservative initial sample can use reports dated the preceding calendar day, avoiding false precision from the game-log source's missing tip time; that narrower estimand must be explicit. To study same-day changes or price response, first obtain a reliable scheduled tip time and verify the report clock's timezone. A previous-day snapshot tests role redistribution, not a late-news trading window.
4. Preserve selected secondary players who do not play as zero opportunity, separating them from missing boxscore data. Report total assists, minutes, assists per minute, cohort attrition and uncertainty; do not turn a rate change into an expected-assist increase without the minutes calculation. Keep the card's sample/effect threshold. Missing timing or insufficient samples remain unresolved.
5. Only an advancing sport-side result warrants the existing focused NBA assist-price collection path. Real FanDuel lines and both prices around the **actual** official update are still required; no historical FanDuel quotes were acquired here, and the report archive alone cannot show the book lagged news.

The next run can begin with these pinned inputs and a small parser, rather than searching again for a generic injury archive or downloading whole play-by-play seasons. The source feasibility result advances this card's readiness, not its evidence status: **idea, sport-side test pending**.
