# Golf birdie price recheck — September 26, 2026

**The historical positive survives a more careful opening-price calculation, but it does not establish an edge.** Observed unders return +10.08% in 2023–25 under birdies-or-better settlement, with an event-bootstrap interval crossing zero. The later 2026 sample loses 2.73%; restricting to stored two-sided boards loses 7.72%. The September 23 reported +8.1% is not reproducible from a saved script, and its exchange attribution and zero-margin price interpretation are unsupported.

| Birdies-or-better, stored opening prices | Observed Under contracts | Graded incl. pushes | Wins / losses / pushes | Units | ROI on graded stakes |
| --- | ---: | ---: | --- | ---: | ---: |
| 2023–25, all observed unders | 671 | 618 | 344 / 232 / 42 | +62.31 | +10.08% |
| 2023–25, paired Over/Under only | 501 | 460 | 254 / 178 / 28 | +36.61 | +7.96% |
| 2026, all observed unders | 202 | 197 | 100 / 97 / 0 | −5.38 | −2.73% |
| 2026, paired Over/Under only | 173 | 169 | 83 / 86 / 0 | −13.05 | −7.72% |

The 2023–25 all-Under 95% event-bootstrap interval is **−1.06% to +20.71%**, across 53 tournaments. Its yearly returns are +31.91% (66 graded, 2023), +8.55% (409, 2024), and +4.40% (143, 2025). Counting every unresolved 2023–25 contract as a loss leaves +1.39% over all 671 stakes. This is an exposure bound, not valid settlement of missing cases. The 2026 all-Under interval is −22.34% to +13.25%, across ten tournaments. These intervals are exploratory, uncorrected for the many hypotheses and subsets already examined.

Plain-birdie settlement raises historical ROI to +14.28% and 2026 ROI to −0.78%. The older Hard Rock contract is not independently verified; the two definitions are sensitivities, not permission to select the favorable one. Current Ontario birdie-or-better rules are documented in the [product review](edge-next-route-2026-09-26.md), but do not retroactively establish historical Hard Rock terms.

## What changed

The [source audit](golf-birdie-source-audit-2026-09-26.md) traces the source to publisher-labelled Hard Rock. The 2023–25 two-sided opening prices have average margin 7.87%, whereas closing columns have 0.19%. Closing columns match transformed probabilities and are not authenticated executable quotes. The diagnostic uses **stored opening American prices**, never the source's differently defined implied-probability fields. Closing-column sensitivities remain in the JSON with an explicit limitation.

Each actual Under is counted once per event, round, named player and line. Duplicate channels and revised Masters tee times do not add bets. No missing side is synthesized from an Over, a fair probability, or a −110 fallback. Four 2026 Over groups have conflicting closes and are excluded from paired-board diagnostics; their absent/ambiguous counterparts do not create Under offers.

Identity joins use explicit event aliases and full names or unambiguous abbreviations. S-H Kim and Si Woo Kim remain distinct, as do Cameron and Carson Young. A matching historical PGA round must contain 18 recorded hole outcomes. Three superficially matching rows fall one week after their named tournament and remain unresolved. Two initials are ambiguous. No uncertain result becomes zero birdies or a loss in the primary calculation. A seven-day event-end check detects obvious date mismatches but does not independently verify every original fixture or quote.

The final file contains 873 distinct observed Under contracts: 815 complete joins, 53 missing, three date mismatches and two ambiguous names. The 97,609-row historical file was recovered from the same pinned publisher commit, and its Git blob `f71c0a71490542179633e3da556b4e7996646167` verified. Source hashes, all sensitivities and attrition are in [the JSON](golf-birdie-recheck-2026-09-26.json). Full row diagnostics remain in ignored local raw storage. Reproduce with `state/runtime/research-venv/bin/python tools/recheck_golf_birdie_prices.py`.

## Interpretation

This is an honest positive historical lead with a negative later diagnostic, unresolved acquisition selection and no demonstrated superior forecast. It is not an independently frozen replication: earlier research inspected 2023–25, and the source publisher may have inspected all years. The original quote timestamps and applicable historical rules are absent; opening-labelled prices alone cannot certify pregame executability. The original trailing-average mechanism is evaluated separately in the [forecast diagnostic](golf-birdie-forecast-2026-09-26.md). No threshold is retuned and no schedule, alert or wager is enabled.
