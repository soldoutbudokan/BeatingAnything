# G6 Fall exemption source checkpoint

**G6 remains unresolved: the required Monday standings and complete next-season exemption labels were not recovered.** Eight targeted queries and four official field-PDF samples established useful source limits. No scores, incentives effect or FanDuel prices were compared. The [source report](../reports/golf-fall-exemption-source.json) retains URLs, request/receipt clocks, hashes, inspected schemas and missing fields.

## What the samples contain

The top-125 era was sampled at early and final Fall events in 2024; the top-100 era at the corresponding 2025 events. Separate official announcements establish the [2023 top-125 rule](https://www.pgatour.com/article/news/latest/2023/04/12/pga-tour-announces-reimagined-2023-fedexcup-fall) and its [continuation in 2024](https://www.pgatour.com/article/news/latest/2023/08/07/pga-tour-announces-full-2024-fedexcup-schedule-calendar-including-eight-signature-events-playoffs). This task did not acquire 2023 field snapshots.

| Official sample | Printed field-list date | Field count | Monday snapshot needed |
| --- | --- | ---: | --- |
| [2024 Procore](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2024/pgatour/procore-championship/updatedTournamentField/Current%20Field.pdf) | Sep 11, 1:15 p.m. | 144 | Sep 9 |
| [2024 RSM](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2024/pgatour/thersmclassic/updatedTournamentField/Current%20Field.pdf) | Nov 20, 11:24 p.m. | 156 | Nov 18 |
| [2025 Procore](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/procorechampionship/updatedTournamentField/Friday.pdf) | Sep 5, 5:10 p.m. | 144 | Sep 8 |
| [2025 RSM](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/thersmclassic/updatedTournamentField/Current%20Field.pdf) | Nov 18, 3:24 p.m. | 156 | Nov 17 |

The headings do not specify timezones. PDF creation/modification clocks and today's collector clocks are retained separately; neither proves the original public availability of a Monday snapshot. The 2024 PDFs were visually checked because their text extraction was empty.

All four are alphabetic entry lists, with alternates and markers for routes such as sponsor exemption or open qualifying. They contain no complete FedExCup Fall rank/points table and no complete exemption ledger for the following season. A sponsor marker concerns entry into that tournament. Its absence does not establish that a player must regain a card through the Fall standings. The [2025 Procore media index](https://pgatourmedia.pgatourhq.com/tours/2025/pgatour/procorechampionship) also records changes after the sampled Friday list, so that list cannot simply be called the Monday field.

## Why ranks alone are insufficient

Official [pre-2025-Procore notes](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/procorechampionship/preTournamentNotes/Pre-Tournament%20Notes.pdf) identify Max Homa at **No. 111**, already exempt through **2028**. A rank-only assignment would incorrectly include him in G6's 2025 comparison band. The same notes identify Patton Kizzire at No. 180, exempt through 2026. These are source examples, not an exhaustive player classification.

The [2026 eligibility overview](https://pgatourmedia.pgatourhq.com/static-assets/page/files/tours/2025/pgatour/procorechampionship/preTournamentNotes/Overview%20of%20eligibility%20changes%20for%202026.pdf) confirms that **2025 Fall uses top 100 for 2026 status**. Its priority categories also show why removing recent winners alone is insufficient: prior top-30 second-year status, career-money categories, life membership, PGA TOUR University and other earned pathways can matter. Medical and conditional categories have different access and require explicit treatment. A player's qualifying route for the current season does not by itself establish eligibility for the next one.

The official [November 13, 2023 RSM preview](https://www.pgatour.com/article/news/latest/2023/11/13/2022-2023-pga-tour-season-concludes-at-the-rsm-classic-whats-at-stake) supplies pre-event ranks 121–140. That is useful partial coverage, but not the full 95–155 bands, points and exemptions needed for the declared top-125-era comparison. Later projected or final standings were not substituted. The 2025 [pre-RSM release](https://pgatourmedia.pgatourhq.com/static-assets/page/files/pressreleases/2025/11/11.17.25_2025_Season_Concludes.pdf) likewise confirms the applicable top-100 rule; it does not resolve this task's full input requirements.

The already-cached current Biltmore Field API response contains identity, participation flags, `status`, `owgr` and `rankingPoints` in the collector-selected schema. Those fields do not supply historical Monday FedExCup Fall points and a dated next-season exemption ledger. `rankingPoints` was not relabeled as FedExCup points. Other historical ranking/eligibility API schemas were not probed within this bounded task.

## Required before the fixed screen

- Complete official Monday ranks and points for every target event, using stable player IDs: ranks **95–155** in 2023–24 and **70–130** in 2025, including the actual cutoff's points.
- A same-time ledger of all applicable next-season exemptions, with effective/expiry dates and any election or utilization status. This includes multi-year tournament/major exemptions, prior top-30 second-year status, career-money and life-member categories, PGA TOUR University, earned tour/qualifying pathways, and relevant medical terms.
- Monday field/change history and a consistent policy for later entries, withdrawals, conditional categories and ambiguous exemptions.

Do not classify the remaining players as non-exempt after removing only the known winners. Unknown exemptions stay unknown. G6's original exposure bands, separate eras, 200-exposure/five-event sample minimum and 0.15-stroke screen remain untested. This checkpoint does not reject the mechanism or establish that a suitable archive cannot exist.

All four PDF requests returned HTTP 200. Raw files remain local under `data/raw/golf-fall-source/`; no paid request, scheduled process or external message was created.
