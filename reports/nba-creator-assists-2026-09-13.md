# NBA creator absence and secondary assists — 2026-09-13

**Result: unresolved.** The fixed 2024–25 preceding-day-report screen produced only **25 exposed player-games**, below the card's minimum of 100. Secondary handlers averaged **4.960 assists versus a same-player prior baseline of 4.000**, a difference of **+0.960 assists**. The descriptive team-cluster 95% interval was **−0.229 to +2.219**. This is neither sport-side confirmation nor evidence of a FanDuel edge. No alternate role threshold, later report window or additional season was tried after this result.

The [choices were written separately before the comparison](../docs/nba-creator-assists-screen-declaration-2026-09-13.md), at `2026-09-13T04:09:23.224038+00:00`, SHA-256 `6589cc9a2c58f8317488aa88fd17ec5ddd3c5359f8c5524fd0730ebc462400f3`. The prior-only cohort was saved at `2026-09-13T04:13:14.261355+00:00`, SHA-256 `c71d2144122ff12cb99d7e3986fee48a62f7d7b6ff8c19a980c1bbd7881df27d`, before the injury join and outcome comparison. These records document sequencing; this remains an exploratory screen.

## What was executed

All 1,230 regular-season games were considered. For each team-game, the ten most recent team games dated strictly before the preceding report day defined the roles. Candidates needed eight appearances, an average of at least 20 minutes across those ten games, presence in the latest prior team boxscore and no intervening known team change. The top prior assist producer needed at least five assists per game; the second needed at least 2.5. This is an operational ball-handler proxy, not proof of who initiated each possession.

The exposure required an explicit **Out** row for that preselected creator in the latest archived report from the preceding calendar day. The actual PDF issue header, game date, matchup, team and player were parsed; context was retained across page breaks. Secondaries explicitly Out or Doubtful were excluded using that same report. A missing row remained unknown, never inferred Available. The comparator was the selected secondary's mean in the prior ten-game window's creator-present games, with at least five such games required.

There were 163 distinct game dates. **158 preceding-day PDFs were downloaded**, all with exact pinned Git-blob hashes and consistent in-document issue times; five preceding dates were absent from the pinned archive: October 21, 2024 and January 9–12, 2025. All selected PDFs had filename hour `11PM` but actual issue time **11:30 PM**. No same-day or later report was substituted. The parser read 23,442 status rows across the reports; many concern the report date's games rather than the target next day, and do not constitute independent exposures. No missing-context or conflicting-status row was flagged.

| Cohort step | Team-games |
| --- | ---: |
| All regular-season team-games | 2,460 |
| Fewer than ten eligible prior games | 308 |
| No qualifying creator/secondary pair | 623 |
| Prior-role-eligible | 1,529 |
| Missing validated preceding-day report | 33 |
| Team explicitly not yet submitted | 292 |
| Creator not explicitly listed; status remains unknown | 973 |
| Creator listed Questionable / Probable / Doubtful / Available | 90 / 95 / 9 / 7 |
| Creator Out, but secondary explicitly Out or Doubtful | 5 |
| Final exposed player-games | **25** |

The preceding-day cutoff is a substantial sample restriction. The prior-role requirement also excludes players after several missed games. This screen therefore tests a narrow set of newly absent, previously active creators; it does not estimate all creator absences or an intraday announcement effect.

Independent review matched all 23,442 raw name/status lines to parsed rows and checked page continuations and conservative player identities. Review also tightened the roster-change lookup to exclude games on the report date, whose completion times are unavailable. This changed **zero prior-role records**: the saved cohort hash remained identical, so no outcome comparison was repeated.

## Outcome and opportunity

| Measure | Creator Out exposure | Same-player prior creator-present baseline |
| --- | ---: | ---: |
| Mean assists | 4.960 | 4.000 |
| Mean minutes | 31.318 | 29.441 |
| Aggregate assists per 36 minutes | 5.702 | 4.891 |

The 25 exposures cover **17 teams and 23 secondary players**. Their prior baselines contain **230 distinct secondary-player games**; reused controls retain the predeclared equal-exposure weighting. One secondary had no player row and was retained as **zero minutes, zero assists** after the complete team boxscore matched the schedule's assist total and minute total. That secondary had been listed Questionable, so the retained zero matters. None of the creators listed Out the preceding day actually played. No outcome-based creator or secondary exclusion was applied.

The bootstrap resampled the 17 teams, preserving exposures within each sampled team, with 5,000 draws and seed 1729. Its interval is descriptive and not adjusted for the research program's many exploratory ideas. Same-player prior baselines reduce player mix but leave opponent changes, trends, season-end rest, other absences and the reason for the creator's absence uncontrolled. The observed rate and minute increases cannot by themselves establish the card's expected-assist threshold.

## Inputs and reproduction

The report [JSON](nba-creator-assists-2026-09-13.json) records all 25 derived observations, attrition, source URLs, report hashes and acquisition timestamps. The raw PDFs, extracted text and role cohort remain ignored. Sources:

- Original NBA PDFs preserved by the [pinned akng8 injury archive](https://github.com/akng8/nba-injury-scraper/tree/02cfe44f7453182eb4a29283285a7af64f5e3c9a/pdfs). The historical archive is secondary custody of original league reports; a file's later retrieval timestamp is not the original public posting time.
- NBA Stats-derived [SportsDataverse player boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_boxscores), `player_boxscores_2025.csv`, SHA-256 `7371d222692fee1c083913d813b125f885c4e53b6f3daaecb7270299913e9716`.
- NBA Stats-derived schedule, `nba_stats_schedule_2024.csv`, SHA-256 `ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26`; its filename uses the season's starting year, whereas the boxscore filename uses the ending year. Exact input recovery is described in the [source checkpoint](../docs/season-runway-2026-09-13.md).

With the pinned boxscore and schedule files in `data/raw/nba-source-feasibility/`, pandas, NumPy, pypdf and `pdftotext` available:

```bash
python tools/explore_nba_creator_assists.py prepare
python tools/acquire_nba_injury_reports.py
python tools/explore_nba_creator_assists.py evaluate
```

The script checks input and declaration hashes. `prepare` preserves the existing cohort if it matches. `evaluate` requires the full fixed acquisition to have completed, so a partial download does not silently define the sample. It writes the JSON; this Markdown explains the resulting decision.

**Next decision:** retain this card as unresolved and proceed to other hypotheses. A later NBA test would need a separately declared, adequate sample with reliable scheduled tip times and same-day report cutoffs, or prospective observations of the actual announcement. Collecting additional archive pages without fixing that sampling question is not the next task. Any pricing test still requires actual FanDuel assist lines, both prices, suspension state and clocks around an official availability update. None were collected here.
