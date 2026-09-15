# New FanDuel prop archives — September 13, 2026

**Two new public archives contain usable historical FanDuel price fields.** This source audit inspected prices, identities and clocks, without loading scoring outcomes into analysis or evaluating a betting rule. It does not establish profitability. The [fixed selection](../reports/new-prop-archive-source-selection-2026-09-13.json), [measured audit](../reports/new-prop-archive-source-audit-2026-09-13.json), and [runnable audit](../tools/audit_new_prop_archives.py) preserve the evidence. Raw inputs remain ignored.

## NBA: paired main points prices and alternate ladders

The pinned [NBA Props Threshold App repository](https://github.com/devlincorrigan/nba-props-threshold-app/tree/233dbbc86b9c6e13df04d4e8b063581b3aa15abb) contains **3,394 historical JSON files totaling 397,273,601 bytes**. Those are tree inventory counts, not verified independent games. A fixed sample selected 20 equally spaced lexicographic paths, including the first and last, before sample counts or outcomes were inspected. All downloaded bytes match the published Git blob hashes.

All 20 sampled files identify `fanduel` / `FanDuel`, distinct event IDs, team names and reported starts. Sample starts span **January 30, 2024–January 7, 2026**. Returned archive snapshots precede those starts by **724.35–1,089.37 minutes**; these are early pregame prices, not closes. No repeated event snapshot appears in this sample. The repository advertises a frozen project, not a continuing feed.

| FanDuel market in the fixed sample | Measured content |
| --- | --- |
| `player_points` | 180 player/line groups, all with exactly one Over and one Under; 360 valid decimal prices; no duplicate player/line/side rows |
| `player_points_alternate` | 1,030 outcome rows, 944 player/line groups; only 54 unambiguous paired groups; 890 unpaired or ambiguous groups; 20 duplicate player/line/side rows; two invalid decimal prices of exactly 1.0 |

Alternates are predominantly one-sided Overs, but some files contain paired alternatives. Preserve the literal market key, player, threshold and side; do not treat all alternate prices as paired or deduplicate conflicting records by arbitrarily keeping one row. Player identity is a name string, not a stable NBA person ID.

The original JSON supplies archive `timestamp`, `previous_timestamp`, `next_timestamp`, reported `commence_time`, book `last_update`, and market `last_update`. **Six of 20 FanDuel markets have market updates later than the archive timestamp, by up to 55 seconds.** Book updates are earlier by 12–152 seconds. Requiring both update clocks to be no later than the original snapshot leaves **119 main-market paired observations in 14 events**. Reject the other 61 pairs under strict chronology; do not move the archive clock forward to accommodate them. A book timestamp alone would miss this defect.

The pinned [publisher event mapping](https://github.com/devlincorrigan/nba-props-threshold-app/blob/233dbbc86b9c6e13df04d4e8b063581b3aa15abb/data/game_event_bijection.csv) contains `game_id,event_id` and maps all 20 sampled events to NBA game IDs. This is a useful join lead, not independent fixture verification. Scheduled starts still need an independent schedule/actual-start check. Source raw JSONs expose no market suspension, accepted stake or original collector reception clock. A single early snapshot cannot produce closing-line value.

## NFL: three seasons of receptions and passing-yard prices

The pinned [NFL Tools repository](https://github.com/firstandthirty/nfl-tools/tree/e919241eb9fc17f057005348c7869a37b23e7675) publishes two manageable processed CSVs with exact FanDuel identity and paired decimal prices:

| File / market | Rows | Events | Players | Rows with nonfuture quote clocks |
| --- | ---: | ---: | ---: | ---: |
| `fanduel_pass_yds_history.csv` / `player_pass_yds` | 1,538 | 779 | 96 | 1,122 |
| `fanduel_receptions_history.csv` / `player_receptions` | 6,901 | 741 | 407 | 4,962 |

Reported starts span **September 8, 2023–January 4, 2026**. All rows have two prices greater than 1.0. No duplicate event/player/market/line/snapshot keys or repeated snapshots per player/line key occur. Passing-yard snapshots lead start by 90.28–99.30 minutes; receptions by 89.38–99.30 minutes. Some season/week values are explicitly estimates in the publisher code; use independently matched fixtures to establish NFL season and week.

The publisher's [flattening code](https://github.com/firstandthirty/nfl-tools/blob/e919241eb9fc17f057005348c7869a37b23e7675/player_props/scripts/01_build/backfill_fanduel_receptions_history.py) assigns the returned archive `timestamp` to the misleadingly named `requested_snapshot_time` column. It is not a local download clock. Retain that distinction. **416 passing-yard rows and 1,939 reception rows have market updates after that snapshot, by up to 48 seconds.** Book updates alone are nonfuture throughout. The table's final column excludes these chronology failures; it is not a final betting-eligibility count.

The downloaded CSV SHA-256 pins are:

- Passing yards, 453,328 bytes: `2425eb9c949aeefde21fc2b0abfc435f383902931d3c84d69552142f47e8045a`.
- Receptions, 2,464,468 bytes: `795ae85ed74b0b1ad4971f8e2951a61704e79aff3138b760d3ec8fe802a2282d`.

CSV context features are publisher transformations and were not accepted as verified facts. The collector contains fallback team/spread guesses and estimated weeks, so reconstruct required context independently. Its external API collection code was read but never executed. No key, account or purchase was used. These files lack raw response verification and a later same-line close; stronger provenance remains available for the NBA raw-JSON sample.

## Next executable work

**Later September 13 execution:** the full NBA archive was acquired and used in the completed [main-points consensus backtest](../reports/nba-points-consensus-2026-09-13.md) and [main/alternate payoff check](../reports/nba-points-payoff-coverage-2026-09-13.md). Neither advanced. The [2025 NFL reception rule](../reports/nfl-short-receptions-backtest-2026-09-13.md) was positive, but its unchanged [2023–24 replication](../reports/nfl-short-receptions-replication-2023-24-2026-09-13.md), using a [new raw spread-board source](nfl-receptions-replication-source-2026-09-13.md), lost 33.87%. Deprioritize that lead. The instruction below describes the original source-audit checkpoint; follow latest PROGRESS for a distinct next mechanism, not a repeat of these tests.

Declare a new mechanism and chronological split before joining outcomes. These archives permit an actual FanDuel prop-price screen; neither fixes the existing live rugby or garbage-time price gaps. Prefer valid paired NBA main points or the nonfuture-clock NFL subset for a first test. Independently join fixture/player identity, preserve all attrition, verify settlement rules and reserve an untouched chronological period. A historical result can be a lead without satisfying the project's independent/forward edge gate.

No explicit license was present in either inspected repository tree. Keep original data out of this public repository. Metadata, hashes and new audit code are saved here. Reproduce with `python tools/audit_new_prop_archives.py --fetch` only if the pinned files are missing; subsequent runs need no network.

Other newly checked leads were discarded quickly: `flancast90/sportsbookreview-scraper` has legacy anonymous-book archives; `WFord26/BetTrack` has application code without a tracked odds export; `Gavinl2706/NBA-Odds-Data` has a notebook/report without a separate odds dataset; the indexed `kennyhyder/sportsbookish-daily-odds` repository returned 404. Do not repeat those checks as a substitute for testing the recovered props.
