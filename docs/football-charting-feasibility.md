# NFL film-charting source feasibility

Audited September 8–9, 2026. This is a source and information-time audit; no NFL game-result labels, fitted probabilities or betting returns were examined. The [timestamped FanDuel odds archive](source-search-v2.md) remains an untested lead. No additional statistical comparison has been registered or evaluated.

## Useful detail, with a timing constraint

[FTN Data via nflverse](https://nflreadr.nflverse.com/reference/load_ftn_charting.html) provides free manual charting from 2022 onward under CC BY-SA 4.0. The publisher describes charting within 48 hours after games. The [field dictionary](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html) includes blitzers, pass rushers, quarterback-fault sacks, motion, play action, screen passes, interception-worthy throws, catchable balls, drops and quarterback reads. Stable game/play IDs allow a join to play-by-play for possession, quarterback and actual play type. Zero blitzers on a punt must not become an unpressured quarterback dropback.

These fields support a narrower hypothesis than overall team strength: does an offense's prior response to extra pass rushers interact with its opponent's tendency to send them? Separately, charted interception-worthy passes and receiver drops could help distinguish recent results from underlying passing quality. These are hypotheses, not demonstrated market mistakes. Feature definitions, shrinkage, lookback, player changes, label availability and test splits still need a protocol before testing.

## Downloaded evidence

| Asset | Rows / games | Retrieval-time finding |
| --- | ---: | --- |
| Current 2024 CSV | 48,031 / 285 | Mixed row retrieval dates; 18,295 rows dated September 1, 2025 |
| Current 2025 CSV | 47,316 / 285 | Every row's `date_pulled` is September 1, 2026 |
| Older 2025 QS asset | 47,316 / 285 | Row retrieval dates range December 11, 2025–February 10, 2026 |

Each asset has 29 fields and unique `(nflverse_game_id, nflverse_play_id)` keys. The selected charting fields contain no empty/NA cells in the CSVs; that does not establish their applicability to every play. The older QS file and current 2025 CSV have identical keys and identical normalized values in all 28 non-timestamp columns. Their retrieval-time fields differ. The machine-readable [audit](../reports/nfl-charting-source-audit.json) records hashes, missingness, week coverage and exact per-week retrieval ranges.

The older [QS asset](https://github.com/nflverse/nflverse-data/releases/download/ftn_charting/ftn_charting_2025.qs) was created and last updated February 10, 2026, according to GitHub release metadata. Its SHA-256 is `192244d833e9566d051c72ee9d4d6319488449d0d2ffceede369c9c0b3d80970`, also matching GitHub's asset digest as checked in the original source audit. Weeks 1–12 carry December 11 retrieval dates; weeks 13–14 carry December 12. Some earlier weeks have later retrieval dates than subsequent weeks: week 19 is dated January 28, while week 20 is dated January 20. These timestamps do not distinguish delayed retrieval from correction. Thus even this earlier retained format does **not** prove that first-half-season rows were available the following week. A generic “game plus 48 hours” rule would invent historical availability.

For a strict future experiment, recorded source retrieval time is a necessary lower bound on availability, and downstream publication must also be supported. The current 2025 CSV would provide no within-2025 charting history under that rule. The QS row timestamps suggest potentially usable late-season history **only if contemporaneous publication of those versions can be corroborated**. The retained QS asset's February 10 creation date does not itself prove public availability in December. Likewise, 2024 charting is a prior-season input candidate subject to publication verification. Neither file justifies relabeling the whole 2025 season as timely weekly features. Publisher retrieval dates remain assertions, not independently archived publication timestamps.

## Reproduction and next step

Original downloads, HTTP metadata and a derived QS-to-CSV conversion are retained in ignored `data/raw/nfl-source-audit/`; third-party rows are not republished here. The conversion used R 4.5.0, archived `qs` 0.27.3 and compatible `stringfish` 0.16.0 in a temporary audit-only library. `qs::qread()` read the original file; `date_pulled` was rendered explicitly in UTC before `write.csv()`. The newer `qs2` format cannot read legacy QS files; the [maintainer documents that incompatibility](https://github.com/qsbase/qs2/issues/24). None of these R packages was added to the project's modeling environment.

An independent offline check reproduced 145 schema, hash, identity and date checks with zero failures, and compared 1,324,848 normalized non-date cells across the two 2025 versions without a difference. A separate read of the original QS reproduced every field and formatted UTC date in the converted CSV. Exact earliest retrieval times are `2024-11-13T12:29:59.804047Z` for the 2024 CSV, `2026-09-01T03:30:08.743555Z` for the current 2025 CSV, and `2025-12-11T12:41:10.599765Z` for the older QS. Reproduce the CSV/hash/date checks with `python3 tools/audit_nfl_charting.py`. The report now records each download's source URL and capture time. The raw GitHub release-metadata response was not retained with these files, so its creation/update claims were not independently rechecked offline.

The [nflverse schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) distinguishes periodically updated FTN charting from participation data released after the season. It also reports that its former injury source stopped after 2024. Do not substitute either for contemporaneous 2025 injury or formation news. Timestamped depth-chart snapshots are another available lead, but their actual files have not yet been audited here.

Before registering an NFL experiment, join independent fixture metadata and raw play-by-play, measure the charting history available at each fixed odds timestamp, and decide whether the usable chronology supports a meaningful untouched test. Preserve source gaps and revised timestamps. If it does not, use this source for new prospective collection rather than manufacturing a historical information advantage.
