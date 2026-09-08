# Narrow-market odds source investigation

Audited September 8, 2026. The requested change was to smaller models, usable historical closing prices, and sports with substantial season runway. Source feasibility and profitable-model evidence are separate questions. The completed soccer experiment failed; the next frozen experiment is Challenger tennis total games. No source in this investigation establishes executable historical FanDuel profits.

## Sources that support further research

| Source and market | What was actually obtained | Closing-value capability | Decision |
|---|---|---|---|
| Football-Data, lower-division soccer total 2.5 | 42 season files, 18,023 rows; 17,968 accepted using early inputs | Paired Bet365 early prices and source-designated Bet365/average closes at the same fixed line | Used in N1; all three learned candidates failed |
| TennisExplorer, Challenger total games | 20 development match pages; 103 eligible paired total-price histories across 18 matches | Literal opening prices/times plus active final prices and last-change times at the same line | Selected for N2, fixed 21.5 games; no N2 model result reported here |
| NBA GitHub prop archive | 102 daily CSVs spanning March 2024–January 2025; real paired FanDuel observations | Useful entries, but no adequate closing series recovered | Retain as a source lead; not an eligible CLV backtest |

### Football-Data: genuine early/closing columns, no individual capture times

[Football-Data's documentation](https://football-data.co.uk/data.php) distinguishes its first prices, collected **after market opening**, from closing columns containing `C`. They must not be called opening odds. It also warns that Pinnacle data became unreliable from July 23, 2025; N1 uses no Pinnacle fields. The [column notes](https://football-data.co.uk/notes.txt) describe the price families.

The six fixed leagues are Championship, League One, Bundesliga 2, Ligue 2, Serie B and Segunda. All 42 files from 2019/20 through 2025/26 were pinned to [mirror commit c9b05a3](https://github.com/huhao930422-debug/football-odds-mirror/tree/c9b05a30eef50fe34abbf4134e6333fc5376d136), then matched byte-for-byte to their primary Football-Data downloads. [The source audit](../reports/soccer-source-audit.json) records every URL, hash, row count and fixture-completeness exception. Fifty-five rows failed early-price requirements; outcomes and closing availability did not decide acceptance.

This source makes historical same-line no-vig closing EV calculable. It does not establish the exact time an entry price was available, simultaneous availability of multiple markets, an accepted stake, or transfer to FanDuel. The [N1 report](../reports/soccer-research-report.md) preserves the negative result and all benchmarks.

### TennisExplorer: narrower market with literal price histories

The public [March 22, 2022 results archive](https://www.tennisexplorer.com/results/?type=atp-single&year=2022&month=03&day=22) contains 37 Challenger matches and their detail IDs. A predetermined sample of 16 IDs plus four independent spot checks produced this development-only audit:

| Measure | Count |
|---|---:|
| Requested / parsed match pages | 20 / 20 |
| Pinnacle game-total rows | 125 |
| Active rows with paired literal opening/final prices and all recorded times before reported start | 103 |
| Matches with an eligible total history | 18 |
| Deactivated odds rows across audited markets | 30 |
| Observed quote records at/after reported start | 0 |

The 103 rows are alternate lines, not 103 independent matches or bets. They are not all 21.5-game lines. N2 fixes 21.5 before acquisition and records a missing market rather than choosing a substitute.

For [Ritschard–Moreno De Alboran](https://www.tennisexplorer.com/match-detail/?id=2057624), the 21-game Pinnacle line displays paired opening prices 1.79/2.03 and final prices 1.72/2.14, with literal dated changes. The 20.5 line is deactivated. This example validates extraction, not N2's chosen line or a bet. An [October 2021 match](https://www.tennisexplorer.com/match-detail/?id=1989192) independently confirmed that this archive format predates 2022.

The page exposes only opening and last change, not every intraday observation. Last-change times can differ between sides and do not prove fresh capture. Displayed historical start is not independently verified first serve. Raw local timestamps are retained and converted using the displayed Prague/Berlin timezone and daylight-saving rules. Final active cells provide a source-designated closing reference, not proof of execution. Current rankings and current-year summaries embedded in old pages are excluded from historical features. Tiebreak superscripts must be removed before interpreting set game scores.

The [N2 protocol](protocol-tennis-v1.md) freezes one line, synchronized opening totals/moneyline inputs, lagged score-derived set shape and workload, chronological splits, and three candidates before holdout acquisition. Entry acceptance must not depend on final activity or results. Missing closes and ambiguous settlements remain visible. This is Pinnacle research; FanDuel price and settlement equivalence remain unverified.

Challenger market availability was independently indexed on FanDuel for [Seville](https://sportsbook.fanduel.com/tennis/seville-challenger-2026/felix-gill-v-sebastian-ofner-36037190), [Cassis](https://sportsbook.fanduel.com/tennis/cassis-challenger-2026), and [Shanghai](https://sportsbook.fanduel.com/tennis/shanghai-challenger-2026). These links establish market coverage, not fresh executable quotes. The [official ATP Challenger calendar](https://www.atptour.com/en/atp-challenger-tour/calendar) and its [August 18, 2026 calendar PDF](https://www.atptour.com/-/media/files/calendar-pdfs/2026/2026-27-atp-challenger-calendar-as-of-18-aug-2026.pdf) provide the season-runway evidence.

## Audited sources that did not qualify

### NBA archive and its Git history

[btam-ny/EV-Bets-NBA](https://github.com/btam-ny/EV-Bets-NBA) contains 102 daily prop CSVs totaling 161,128,053 bytes. The [March 13 sample](https://github.com/btam-ny/EV-Bets-NBA/blob/master/data/prop_data/data_points_2024-03-13.csv) has 502 paired FanDuel props with event identity, player, market, line, two prices and market-update timestamps. Its updates precede tip by 4.16–7.18 hours. No explicit data license was found; raw data is not republished here.

The full Git history has 54 commits; only six daily paths have multiple content versions. Nine versions across March 10, 11 and 13 yielded 1,774 event/player/market/line keys, 1,179 with repeated snapshots and 947 with changed prices. **Zero audited pairs had a quote update within 30 minutes before start.** March 10 afternoon versions also contained 51 pair observations timestamped after scheduled start, which cannot qualify as pregame. These are sample findings, not a claim that all 102 dates have no near-start quotes.

A deleted historical aggregate contains one night, eight NBA events and 1,252 FanDuel outcome rows; no repeated event/player/market/line/side keys. Git history therefore recovers some price evolution but not a multi-month closing benchmark. NBA threes remains a candidate only if that missing evidence is obtained.

### ParlayAPI public prop-close sample

The [50,000-row downloadable sample](https://github.com/JacobiusMakes/sports-odds-datasets) is real and openly licensed, but its contents fail this use case. Of 42,870 rows with explicit timezone-aware start and snapshot times, 27,604 were captured at or after scheduled start. NBA has 269 paired FanDuel records, of which only 12 have pre-start snapshots; NHL and NFL have zero such qualifying pairs. No earlier entries are supplied. One observed −115 price is assigned an impossible implied probability of 7.6667, so supplied probability fields also cannot be trusted. A closing label does not resolve timestamp, pairing or coverage failures.

### LineTerminal public closing logs

[LineTerminal](https://lineterminal.com/methodology) documents historical closes from FanDuel, DraftKings and BetMGM. Its public [Curry 2023/24 endpoint](https://lineterminal.com/api/players/stephen-curry/props?sport=basketball_nba&season=2023-24) returned 74 games and 461 market/line records. The response contains `bestOdds` and `bestUnderOdds`, but no bookmaker identities, per-book paired prices, event IDs or quote timestamps. Combining those best prices cannot establish FanDuel or same-book no-vig closing EV. The potentially useful line-level reference is insufficient for promotion evidence.

### Valuebetennis tennis CSVs

[Valuebetennis open data](https://www.valuebetennis.com/en/donnees.htm) publishes Pinnacle-labelled opening/closing CSVs. The downloaded 2021 file has 63,728 rows and zero complete opening/closing pairs; the 2022 file has 83,381 rows and 34,202 complete pairs. ATP Challenger 2022 supplies 4,644 pairs, but only 3,935 have internally coherent completed best-of-three scores. Missing/truncated scores cannot safely distinguish retirement from a bad scrape.

Independent checks invalidated its precise timing: [Halys–Vavassori on TennisExplorer](https://www.tennisexplorer.com/match-detail/?id=2044302) is dated March 2, 2022 at 14:40 local, while the [Valuebetennis record](https://www.valuebetennis.com/tournaments/2022/turin-challenger-9552/matchs/quentin-halys-vs-andrea-vavassori-461685.htm) dates it 49 hours 40 minutes earlier and truncates the final set. A 48-hour feature lag would not cure that error. N2 excludes this source's dates and scores and uses the stronger independent archive.

### Other dead ends

- [Predicting-NHL](https://github.com/RasmusRynell/Predicting-NHL) advertises roughly 5,000 shots odds, but its current public tree contains no odds database or exported archive.
- [NFL historical spreads](https://github.com/bvansoelen/get_historical_nfl_odds) supplies 12,894 team-game rows without paired prices or quote times; it does not solve prop CLV.
- [QuantGalore's receptions project](https://github.com/quantgalore/nfl-props) supplies code and requires an external odds key, rather than providing historical odds.
- [Owls Insight](https://owlsinsight.com/docs) and [PropLine](https://prop-line.com/docs) restrict the needed history to subscription tiers. No subscriptions, purchases, accounts, or requests to other people were used.

Source audits do not change the [prospective qualification protocol](protocol.md). Every new FanDuel cohort still needs independently reviewed model/protocol hashes, the recorded prospective sample and corrected statistical bounds, and fresh verified paired executable quotes before an alert can be sent.
