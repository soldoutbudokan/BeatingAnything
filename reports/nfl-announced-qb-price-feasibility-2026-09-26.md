# Announced backup quarterback: retained price feasibility

**A two-game Miami Huntley announcement/price match exists, but it is not ready for an edge test.** The retained export reports both receiving-yard and reception prices. Raw offered-price authenticity remains unresolved, and this episode supplies at most **nine yard receiver-games**, versus the unchanged card's 100-observation sport-side gate. No model was fitted, threshold changed, or target-outcome dataset projected or evaluated. The [JSON audit](nfl-announced-qb-price-feasibility-2026-09-26.json) contains every Miami price, clock, source hash and limitation.

## Retained coverage

`data/raw/nfl-qb-kneel-props-2026-09-26/prices.csv` is the pinned `firstandthirty/nfl-tools@e919241eb9fc17f057005348c7869a37b23e7675` processed export, SHA-256 `a99887894fec9cd7c3e216a74c53a14d3ef1cc03528a04693076fb084f2a1c26`. It reports 2,424 paired FanDuel `player_reception_yds` rows and 2,253 `player_receptions` rows, across 222 events in 2024 only. Respectively 1,794 and 1,663 pairs have both update clocks between zero and 300 seconds before the returned archive snapshot. These are inventory counts, not a final eligible cohort.

The previously audited 2023–25 `fanduel_receptions_history.csv` and `fanduel_pass_yds_history.csv` are absent locally. Their documented coverage cannot establish currently retained 2023 receiving-yard offers. Thus Browning's 2023 replacement episode is unavailable for this bounded route. No additional prices were acquired.

## Miami episode and exact clocks

Independent retained NFL fixture metadata agrees with these three source starts. All listed Miami quote pairs have valid American prices, one returned snapshot per fixture, and nonfuture book/market updates.

| Fixture | Returned snapshot UTC | Scheduled start UTC | Book/market age | Miami paired yards/receptions |
| --- | --- | --- | --- | --- |
| TEN at MIA, September 30 | 22:55:38 | 23:30:00 | 80 / 45 seconds | 4 / 4 |
| MIA at NE, October 6 | 16:25:37 | 17:00:00 | 53 / 33 seconds | 5 / 4 |
| MIA at IND, October 20 | 16:25:38 | 17:00:00 | 13 / 22 seconds | 4 / 4 |

The first two games include Hill, Waddle, Smith and Achane in both markets; Beckham adds a yard line against New England. That is nine yard receiver-games including running backs, seven for WR/TE only, and eight reception pairs. Prior air-yard roles were not computed. Beckham's PUP return prevents treating his availability and role as automatically comparable.

The [team's Tua injured-reserve announcement](https://www.miamidolphins.com/news/miami-dolphins-make-roster-moves-x4585) has source metadata publication `2024-09-17T20:48:24.790Z`, revision `20:51:09.718Z`. The [official NFL report quoting McDaniel's Huntley confirmation against Tennessee](https://www.nfl.com/news/dolphins-to-start-qb-tyler-huntley-against-titans-on-monday) was published `2024-09-28T16:29:54.075Z`, revised `17:09:57.270Z`. The [New England starter confirmation](https://www.nfl.com/news/dolphins-to-start-qb-tyler-huntley-in-week-5-vs-patriots-odell-beckham-to-have-practice-window-opened) was published `2024-10-01T21:24:49.634Z`, revised `2024-10-02T13:26:13.829Z`. Even the later revision clocks precede the two quotes by 53.76 and 98.99 hours. These are source-asserted timestamps, not archived original-publication receipts. October 20 has price coverage but was not promoted to the strict announcement-matched cohort.

## Material limits and disposition

There are **2,339 −110/−110 yard pairs out of 2,424**, with 85 differing pairs and 13 distinct price combinations. The retained collector directly copies API `outcome.price`; available merge code does not replace missing prices. No imputation defect was found. However, original API responses and the unmerged odds CSV are absent. These are publisher-reported offers, not independently certified executable prices. The collector groups by event/book/market/player/line without clocks: duplicate same-side outcomes could overwrite a price while preserving the first metadata. Raw absence prevents determining whether any such collision actually occurred. The earlier [kneel-prop report](nfl-qb-kneel-props-2026-09-26.md), using the same file, already discloses absent raw responses and unverified authenticity; duplicate-key overwrite is an additional caveat. This audit supplies no basis for a numerical correction.

Each Miami fixture has only one quote time, days after the news. There is no before/after announcement price path, and generated publisher team-total columns cannot stand in for actual offered team-total prices. The retained roster supplies identity leads but is season-end metadata, so it cannot establish prequote membership or availability. Freeze whether this is one original-starter absence episode or successive replacement events: Huntley follows Thompson, and shared receivers/games do not supply independent episode evidence.

Keep this as feasibility only. A substantive test needs verified receiving-yard offers and a fixed broader set of timestamped changes sufficient for the existing gate. Receptions cannot silently replace the yard-share hypothesis, nor should the closed short-reception underdog or observed in-game QB-switch screens be reused. No outcome performance was calculated; search results and later pregame reporting incidentally displayed retrospective Miami results, so this episode must not be described as an untouched holdout.
