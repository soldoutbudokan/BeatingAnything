# Data audit

The usable archive contains **11,043 uniquely matched MLB regular-season games** with FanDuel opening moneylines from April 2021 through August 16, 2025. This is a retrospective research dataset. It does not establish when any quoted price could have been executed.

## Source and reproduction

The [public release](https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/tag/dataset) offers an [80,120,813-byte JSON archive](https://github.com/ArnavSaraogi/mlb-odds-scraper/releases/download/dataset/mlb_odds_dataset.json). It attributes the odds to SportsbookReview. Its SHA256 is `3f952fd0bfae9f4f2d17e66692cb936ce6e1a5f6b415318012090c85933b882b`.

The file contains 13,121 game rows across 1,097 dates, from 2021-04-01 to 2025-08-16. It includes named sportsbooks, opening and archival terminal moneyline/spread/total prices, teams, start dates, venue names and results. No quote observation timestamp survives in the archive. No explicit repository or dataset license was found; this project provides a downloader and provenance rather than redistributing the raw archive or copying its scraper.

Download and verify:

```bash
python -m beating.odds --fetch --archive data/raw/mlb_odds_dataset.json
```

Normalize against downloaded MLB schedule JSON files:

```bash
python -m beating.odds --archive data/raw/mlb_odds_dataset.json \
  --schedules data/raw/schedule_2021.json data/raw/schedule_2022.json \
  data/raw/schedule_2023.json data/raw/schedule_2024.json data/raw/schedule_2025.json
```

Schedule files use the public MLB Stats API format at `https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2021-01-01&endDate=2021-12-31&hydrate=probablePitcher`, changing the year as needed. MLB numeric team IDs resolve archive aliases such as AZ/ARI, ATH/OAK, CHW and WAS. Each retained row must match a unique official date and home/away team pair, have a completed regular-season game and agree with MLB's scores. Source `gameType` is not authoritative: 312 source rows say `Unknown`.

## Two defects that matter

**Archival terminal prices are not closing prices.** On April 1, 2021, Cleveland at Detroit has a FanDuel opener of Detroit +158 / Cleveland -192. Its `currentLine` is Detroit -1100 / Cleveland +620; Detroit won 3–2. Other books' terminal prices still place Detroit around +155 to +160. FanDuel's archived spread has also moved from Detroit +1.5 to -2.5 and total from 7.5 to 5.5. This is strong evidence of an in-play quote surviving in the historical table. Without timestamps, its precise timing cannot be established. **Every `currentLine` field is excluded from modeling output; no CLV calculation is permitted from this archive.**

**Doubleheaders are merged incorrectly upstream.** The published scraper keys games by date plus away/home names without game ID or game number. It keeps the first game's metadata while later game prices can overwrite earlier prices. The normalizer excludes all ambiguous schedule date/team pairs and any explicitly flagged doubleheader, including cases where only one doubleheader game appears in the schedule query. Resumed games and rescheduled entries are also rejected if identified. Postponed/cancelled MLB entries can have `abstractGameState=Final`, so the normalizer requires `detailedState` to be `Final` or `Completed Early` and rejects `rescheduleDate`.

## Structural exclusions

These counts come from the pinned archive and full-calendar MLB schedules obtained during the audit. Exclusions are sequential and disjoint. All filters concern validity, identity, completion or market structure; none chooses games based on a model's profit. Cross-book deviations are diagnostics and are not exclusion rules.

| Exclusion | Rows |
|---|---:|
| Missing or duplicate FanDuel moneyline | 530 |
| Ambiguous schedule date/team pair | 147 |
| Explicit doubleheader flag | 4 |
| Score disagreement with MLB | 19 |
| Unknown MLB team, including All-Star teams | 4 |
| No matching official schedule game | 3 |
| Not an official regular-season game | 1,369 |
| Invalid opening prices | 2 |
| **Total excluded** | **2,078** |
| **Retained** | **11,043** |

Both invalid opening pairs are 0/0, dated July 8 and July 9, 2025. Valid FanDuel opening overround ranges from 1.03456 to 1.06079, with median 1.04050. No valid opening price has American magnitude above 1,000. The parser requires finite American odds of magnitude at least 100 and a two-way implied-probability sum between 1 and 1.25. It applies no selected odds-range restriction.

| Season | Retained games |
|---|---:|
| 2021 | 2,280 |
| 2022 | 2,275 |
| 2023 | 2,347 |
| 2024 | 2,355 |
| 2025 through August 16 | 1,786 |

Machine-readable counts and source identity are in `reports/data-audit.json`. Rebuilt counts may change if MLB corrects its historical schedule; pin the raw schedule files and their hashes for an exact replay.

## Opening-price limits

Opening labels are plausible, but not independently certified pregame observations. No public snapshot proves when these prices appeared. The retained frame explicitly marks `opening_quote_as_of_unverified=True` and leaves `opening_quote_time` empty. It must not imply that a feature calculated the morning of a game was already available at its opening price. Lineup, probable-pitcher, weather and injury fields fetched retrospectively require separate availability evidence.

Other books' opening prices have the same timing problem and need not be simultaneous with FanDuel's opener. Across all valid source moneylines, 128 FanDuel probabilities differ by more than five percentage points from the other-book median; 18 differ by more than ten points and four by more than twenty points. Those differences can reflect timing, lineup changes or errors. The optional `other_open_consensus_prob` is an unsynchronized diagnostic with an explicit availability flag. It is not proof of an executable arbitrage or a contemporaneous market benchmark.

FanDuel opening implied probabilities are normalized by the sum of the two implied probabilities. Returns use the offered decimal price, including the vig. Any reported historical return remains provisional until a frozen prospective model predicts against timestamped, available prices.

## Public monitoring access checked

A single ordinary request to [SportsbookReview's MLB table for September 8, 2026](https://www.sportsbookreview.com/betting-odds/mlb-baseball/?date=2026-09-08) succeeded. Its embedded public JSON includes game IDs, start times, starters, status, bookmaker names and opening/current prices. Quote timestamps and price histories were absent. The response naturally resolved to Ontario, Canada and did **not** include FanDuel; the visible Canadian books must not be relabeled as FanDuel. No region override, proxy, login bypass or bot-protection bypass was attempted. Direct FanDuel sportsbook access returned HTTP 403. FanDuel's [official research page](https://www.fanduel.com/research/mlb) confirms moneyline, run-line, total, NRFI and player-prop market coverage but does not establish a usable high-frequency quote feed.

Subsequent research found explicit FanDuel pairs on [Covers' public odds page](https://www.covers.com/sport/baseball/mlb/odds), available through an ordinary request without location changes. The implemented `beating.covers` collector captured 15 current-day pregame pairs, mapped them to official MLB game IDs and saved raw responses and observation timestamps. See [live-feed.md](live-feed.md). These support prospective paper research; aggregator execution and bookmaker jurisdiction remain unverified. The historical archive still cannot supply quote timing or CLV.
