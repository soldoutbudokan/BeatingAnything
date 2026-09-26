# First-round course assignment and birdie-price feasibility

**The retained source does not support a first-round course comparison.** Across Farmers, Pebble and RSM, there is only **one first-round paired offer**, on Torrey Pines South, and zero editions with first-round prices on both declared courses. This is metadata feasibility only; no birdies, scores, finishes, strokes gained, forecast columns or returns were inspected or calculated. The [JSON audit](golf-birdie-course-price-feasibility-2026-09-26.json) records projected columns, file hashes, exact joins and all-round coverage.

| Original G11 edition | First-round Under offers | Valid paired opening offers | Course coverage |
| --- | ---: | ---: | --- |
| Farmers 2023 | 0 | 0 | None |
| Farmers 2024 | 1 | 1 | South only; North 0 |
| Farmers 2025 | 0 | 0 | None |
| Pebble 2023 | 0 | 0 | None |
| Pebble 2024 | 0 | 0 | None |
| Pebble 2025 | 0 | 0 | None |
| RSM 2024 | 0 | 0 | None |
| RSM 2025 | 0 | 0 | None |

The one offer is **Tony Finau, Farmers 2024 round 1, birdies 3.5: Under −120 / Over −110**. The exact `(2024, event_id=4, dg_id=11676, round=1)` join is unique and identifies Torrey Pines South, course 4, par 72. Both American prices are valid; their implied probabilities sum to approximately 1.0693. The stored `2024-01-24T18:40:00Z` is a fixture/tee time, not a quote timestamp. Actual opening-time availability and prequote visibility of the retrospective course assignment remain unverified.

Across all rounds, the three named tournaments contribute 32 Under rows, 18 with valid stored opposite opening prices. Twenty-six have unique course joins; six RSM-labelled round-four rows lack event/player identities and remain unmatched. Farmers 2024 round two has four paired offers—one North and three South—but is outside this first-round scope. Pebble's three rows are round three. Later rounds were not substituted for missing first-round coverage.

A course-conditioned birdie forecast would be a distinct mechanism from the closed trailing birdie-average forecast and G11's original score/cross-course two-ball test. However, a course's score difficulty does not determine its birdie probability: bogeys and other scoring components can drive the stroke contrast. The original G11 score effect cannot supply an assumed birdie adjustment.

Hard Rock attribution still rests on the previously audited publisher parser; the inspected rows lack explicit bookmaker and quote-time columns. Stored opposing opening fields do not prove simultaneity or executable offers, and historical plain-birdies versus birdies-or-better terms remain unresolved. The derived Under-led file also does not establish the full offered market universe.

Stop this retained-source first-round route at feasibility. It supplies no comparative cohort, forecast validation or edge claim, and does not change the original G11 result. No source was downloaded or old file changed.

An [independent metadata audit](golf-birdie-course-price-feasibility-audit-2026-09-26.json) verifies both input hashes, all eight edition counts, the unique Finau/South join and exact implied probability. No outcomes or forecast columns were projected.
