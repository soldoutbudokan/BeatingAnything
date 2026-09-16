# 2025 cut-rule source map — G4 prerequisite

**Follow-up completed:** the [applied-cut audit](../reports/golf-applied-cut-audit-2026-09-14.md) reconciles 22 thresholds and leaves a 20-event wave/venue upper bound. The sections below record the preceding planned-rule source check; its proposed audit has now been carried out. Exact approval clocks and G4's model prerequisites remain unresolved.

**Scope:** the 40 events already fixed in the [group inventory](../reports/golf-weather-group-inventory-2026-09-14.json). This is a planned-rule map, with no cut-line comparison, weather result or market estimate. Six targeted web searches were used; subsequent reads followed primary-source documents.

The [configuration](../config/golf-cut-rules-2025.json) contains event IDs, rules, verification levels, source URLs, PDF page indices, retrieval clocks and retained-file hashes. It separates scheduled rules from the still-unperformed audit of each event's actual cut.

## Coverage

| Planned format | Events | Evidence |
| --- | ---: | --- |
| Ordinary top 65 and ties after 36 holes | 25 | 2025 PGA TOUR default; event-specific overrides still require an audit |
| Hosted Signature: top 50 and ties, or within 10 strokes of the lead | 3 | Explicit 2025 event notes |
| No cut | 8 | Explicit 2025 event or playoff rules |
| Major, rule number verified | 3 | PGA Championship 70; U.S. Open 60; The Open 70, each with ties |
| Major, rule number unresolved | 1 | Masters; kept separate from the PGA TOUR default |

The 25 ordinary-rule candidates exceed G4's planning requirement of 20 events. **The comparable-event sample gate is not passed:** official cut outcomes and any agreement, weather, withdrawal or disqualification adjustments have not been audited. Scottish Open and ISCO are additionally flagged as co-sanctioned events.

A metadata-only join to the [scheduled-wave preparation](../reports/golf-wave-preparation-2026-09-14.json) and [venue map](../config/golf-weather-venues-2025.json) leaves **22 of those 25** with two scheduled waves in both rounds and an unambiguous venue. CJ CUP Byron Nelson lacks two classified wave rounds; Rocket and World Wide Technology have ambiguous venues. This is an upper bound before weather and outcome availability, not an effect result or completed sample gate. No scores or weather values were used for this count.

## 2025 TOUR rules and exceptions

The [original 2025 handbook](https://caddies.pgatourhq.com/static-assets/uploads/2025-PGA%20TOUR%20Player%20Handbook%20and%20Regulations-FINAL.pdf), §IV.A.5, PDF page index 129, and [August 1 edition](https://caddies.pgatourhq.com/static-assets/uploads/2025-PGA%20TOUR%20Player%20Handbook%20and%20Regulations-8.1.2025.pdf), index 130, have identical cut provisions. The ordinary rule counts **amateurs as well as professionals**. Agreement or referee discretion can override it. The final-36-holes-in-one-day provision uses the score closest to 60 players, selecting the higher score for an equal-distance tie. Once the cut and next-round groupings are approved, subsequent WD/DQ does not change the cut line. Earlier withdrawal timing still needs verification.

The same handbooks explicitly identify Genesis, Arnold Palmer and Memorial's special cuts; Sentry, RBC Heritage, Truist and Travelers as no-cut events; and the no-cut playoff class. The August edition records TOUR Championship's 2025 change to unadjusted stroke play. The [2025 Signature fact sheet](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/rbcheritage/preTournamentNotes/SE%20Fact%20Sheet-RBC%20Heritage%202025.pdf), page index 0, corroborates the distinction. A current evergreen FAQ mixing 2025 prose with a Cadillac-containing schedule was not used.

Baycurrent's [2025 media guide](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/baycurrentclassic/shotlinkAnalysis/2025%20Baycurrent%20Classic%20Media%20Guide.pdf), page index 3, explicitly specifies four rounds without a cut. Its 78-player field size was not used to infer that rule.

## Majors and remaining uncertainty

- **The Open:** the [153rd Open entry terms](https://www.theopen.com/-/media/1891b197a3a54031a92d7d08d1190520.ashx), A.3, explicitly specify 70 and ties after 36 holes. A qualifying posted total still counts toward the threshold if the player withdraws either before or after the third-round draw. Keep this separate from the TOUR timing provision.
- **PGA Championship:** an [official May 16, 2025 article](https://www.pgachampionship.com/news-media/articles/bets-to-consider-heading-into-the-weekend-at-the-pga-championship) expressly states the 70-and-ties rule. It was published during the event, so it does not prove pre-event publication. No cut count was inferred from finishing statuses.
- **U.S. Open:** the primary search index for [2025 Fast Facts](https://www.usopen.com/2025/articles/fast-facts-for-2025-us-open.html) explicitly specifies 60 and ties after 36 holes. Direct acquisition returned HTTP 403; the retained body is an error response, not the article. This event has a separate `official_2025_search_index_only` evidence level. No restriction was bypassed.
- **Masters:** the sampled 2025 TOUR notes did not verify the rule number. The 2025 Masters media guide is linked from the official media index, but the web reader rejected its size; a slow ordinary download was terminated to keep this source task bounded. No guide content was retained or inspected. Its rule remains unresolved. The observed number of survivors is not used to reconstruct the rule.

These are 2025-labelled documents retrieved in September 2026. Their hashes make this source check reproducible; they do not prove what was available at a historical betting decision. Other major-specific WD/DQ and weather provisions remain unverified. All 40 actual-cut audits are unperformed, and no forecast archive or FanDuel make/miss prices were acquired by this task.

## Proposed applied-cut audit — not executed

All 25 ordinary-rule events have cached ESPN detailed score pages and official opening-round tee-group files. There are **zero retained official round-note PDFs for these 25 events**. Previously cited Travelers final notes concern an excluded no-cut event.

A bounded audit is practical with up to 25 official event-index reads and 25 linked second-round notes, plus at most 10 final-round or referee-note follow-ups for missing cut statements, suspensions or WD/DQ ambiguities: **60 new source files maximum, zero additional search queries**. Record the official threshold, players/amateurs making the cut, cut timing, and explicit exceptions. Reconcile against complete cached 36-hole totals and statuses only after the official statement establishes the cut. An unmatched or ambiguous event stays unresolved; do not change its rule to fit scores. This audit would provide labels, not test G4.

G4 also needs an independently declared, prior-only conversion from wind exposure to scoring impact, a baseline and validation design before any weather/cut-line comparison. Planned rules and an applied-cut audit alone do not make that comparison runnable.
