# NFL 2025 fixture and quote feasibility

This is a metadata-only feasibility check, not a registered experiment. All 285
2025 NFL regular-season and postseason fixtures have an eligible FanDuel entry
under the fixed timing and quote-quality rules below. Only 77/285 (27.0%) have a
qualifying last prestart FanDuel or Pinnacle reference within 30 minutes of the
independent scheduled kickoff. No game-result labels, forecasts, EV, returns,
CLV values, or significance tests were inspected or computed.

The independent public schedule is [nflverse/nfldata's games.csv](https://github.com/nflverse/nfldata),
maintained by Lee Sharpe according to the publisher's
[schedule loader](https://github.com/nflverse/nflreadr/blob/main/R/load_schedules.R).
Its [data dictionary](https://github.com/nflverse/nfldata/blob/master/DATASETS.md)
defines Eastern kickoff times and assigns January/February playoff fixtures to
the preceding regular season. This is a public schedule source independent of
the odds archive, not an official NFL execution or first-play feed. The projection
contains 272 REG, 6 WC, 4 DIV, 2 CON and 1 SB fixtures, dated September 4, 2025
through February 8, 2026.

The raw schedule bytes were hashed and retained without displaying result fields.
Before any row analysis, the CSV was projected to `game_id`, `season`,
`game_type`, `week`, `gameday`, `gametime`, `home_team`, `away_team`, `old_game_id`,
`gsis`, and `nfl_detail_id`. The odds query reads only quote identities, prices,
and timestamps from `raw_odds`; it never reads derived game/season summaries.
Here, `outcome_name` denotes the quoted team selection, not the game result.

The fixed rules are:

- Match exact full team names through an explicit 32-team code map, preserving
  home/away order, to a unique independent fixture within 15 minutes. Exclude
  ambiguous fixtures, conflicting team identities, and source IDs mapping to
  multiple fixtures. No manual fixture repairs were used.
- Set the timing boundary to the earliest independent kickoff or source scheduled
  start observed for a uniquely bound, stable event identity. Even an earlier
  out-of-tolerance revision can tighten this boundary; its own snapshot stays
  excluded. Later revisions cannot extend the cutoff.
- Pair the two FanDuel h2h sides at exactly the same event, capture, scheduled
  start, and home/away identity. Require valid American prices, no point line,
  no conflicting side prices, a common book update, update age from 0 through
  90 seconds, and paired overround from 0 through 8%.
- Choose the first eligible capture whose lead to that boundary is from 1 hour
  through 24 hours, inclusive. Entry acceptance does not require a closing quote
  or Pinnacle coverage. Pinnacle happens to meet the same gates at all 285
  selected entry captures.
- For reference coverage, find the last quote meeting the same quality gates
  strictly before the earliest boundary. Measure its lead to the independent
  scheduled kickoff, so an obsolete early source schedule cannot manufacture a
  close. Keep all entries when the 30-minute reference is missing.

There are 23,754 FanDuel h2h rows, 11,877 snapshot groups and 11,190 valid fresh
prestart pairs. Of the latter, 10,079 precede the 24-hour entry window, 1,023 are
inside it and 88 lie inside the final hour. The earliest eligible selection
retains all 285 events. Snapshot rejection reasons are 322 without a unique
fixture within 15 minutes, 163 outside the update-age limit, and 208 at or after
the earliest boundary; reasons can overlap. There are no malformed fixture or
raw identity rows, no ambiguous event exclusions, and no missing entry fixtures.
Source scheduled starts vary for 258 fixtures, and 52 fixtures have a source
boundary earlier than the independent schedule.

| Maximum reference lead | FanDuel / 285 | Pinnacle / 285 |
|---|---:|---:|
| 90 seconds | 0 | 0 |
| 5 minutes | 77 | 77 |
| 15 minutes | 77 | 77 |
| 30 minutes | 77 | 77 |
| 1 hour | 79 | 79 |
| 3 hours | 139 | 141 |

FanDuel's median last-prestart lead is 3h 4m 21s, with a range of 4m 20s to
21h 4m 21s. Every entry has some valid prestart Pinnacle reference, but 208 lack
one within 30 minutes. Coverage is uneven by NFL week:

| NFL week | Entries / fixtures | FanDuel <=30m | Pinnacle <=30m |
|---|---:|---:|---:|
| 1 | 16 / 16 | 0 | 0 |
| 2 | 16 / 16 | 1 | 1 |
| 3 | 16 / 16 | 0 | 0 |
| 4 | 16 / 16 | 0 | 0 |
| 5 | 14 / 14 | 0 | 0 |
| 6 | 15 / 15 | 0 | 0 |
| 7 | 15 / 15 | 0 | 0 |
| 8 | 13 / 13 | 0 | 0 |
| 9 | 14 / 14 | 8 | 8 |
| 10 | 14 / 14 | 7 | 7 |
| 11 | 15 / 15 | 7 | 7 |
| 12 | 14 / 14 | 7 | 7 |
| 13 | 16 / 16 | 8 | 8 |
| 14 | 14 / 14 | 8 | 8 |
| 15 | 16 / 16 | 8 | 8 |
| 16 | 16 / 16 | 8 | 8 |
| 17 | 16 / 16 | 8 | 8 |
| 18 | 16 / 16 | 6 | 6 |
| 19 (WC) | 6 / 6 | 1 | 1 |
| 20 (DIV) | 4 / 4 | 0 | 0 |
| 21 (CON) | 2 / 2 | 0 | 0 |
| 22 (SB) | 1 / 1 | 0 | 0 |

The four-daily UTC capture cadence offers much better nearstart coverage from
week 9 onward than in weeks 1–8. That timing pattern is consistent with changing
Eastern/UTC alignment; it is not evidence about betting performance. No closing
window has been relaxed to improve this count. Historical schedule publication
vintage and actual kickoff are unverified, and publisher `last_update` cannot
prove an executable local FanDuel price. A subsequent registered experiment
would need to state how these timing limits affect its evidence requirements.

The machine-readable [audit](../reports/nfl-fixture-feasibility.json) contains
all source/projection hashes, the full identity map, week counts, and exclusions.
The [audit script](../tools/audit_nfl_fixtures.py) reruns only this metadata check.
Ignored files under `data/raw/nfl-fixture-feasibility/` retain the raw source,
strict fixture projection, every rejected snapshot/window reason, selected-entry
metadata, and `candidate-quote-projection.json`. That last file contains the
fixed entries, exact FanDuel/Pinnacle paired price rows and timestamps, and last
prestart reference rows; it contains no result fields. Missing references remain
explicit and never filter the entry population.

Pinned raw SHA-256 hashes:

- Fixture CSV: `5a346edf3e36421cf02b4d059085e29a5a8229a74a637c921f8df95f16086aaf`.
- Odds DuckDB: `b03c4e7f1cf885e9f20ea808ee538c26c21df4065b342fe04c50d09b808c344c`.

This check changes no protocol, family correction, model, or notification state.

Reproduction uses `python tools/audit_nfl_fixtures.py` with DuckDB 1.5.5
(the latest verified run used Python 3.12.13). The script reads the durable local database
`data/raw/nfl-source-audit/nfl_odds.duckdb` and retained fixture CSV above; it
does not need the original `/tmp` downloads or network access. The current
session's persistent isolated DuckDB installation is under `state/runtime/nfl-audit-lib`;
use `PYTHONPATH=state/runtime/nfl-audit-lib state/runtime/research-venv/bin/python tools/audit_nfl_fixtures.py`,
or install that pinned DuckDB version in a separate audit environment. The model environment need not change. Ignored raw
files remain local and are not included in Git pushes; a fresh clone needs those
same hash-verified input files before reproduction.
