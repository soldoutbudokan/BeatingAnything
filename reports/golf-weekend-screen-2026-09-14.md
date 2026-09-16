# G5 weekend information screen — September 14, 2026

**Primary round-three result: unresolved: sample below gate.** No FanDuel prices were tested.

The [prewritten card](../docs/hypotheses/golf-weekend-state.md) uses previous-20-round ability (minimum 10), fixed ±2-stroke early-residual bins, and a 0.1-stroke-per-stroke screen. The script specifies event exclusions and within-event standardization before comparison. 2024 supplies history; 2025 is inspected exploration, not untouched confirmation.

| Later round | Matched player-events | Events | Early gap | Later gap | Later/early |
| --- | ---: | ---: | ---: | ---: | ---: |
| round3_residual | 200 | 11 | 6.0975 | 0.9735 | 0.1597 |
| round4_residual | 197 | 11 | 6.0633 | 0.5069 | 0.0836 |

## Interpretation and limits

Low means better-than-prior early scoring; high means worse. Differences are calculated within events and weighted by n_low × n_high / (n_low + n_high). Both later rounds are reported; round three is primary. A positive contrast can reflect a noisy prior skill estimate as well as event-specific state. It does not establish motivation, causation, or book mispricing.

Current scores are centered on their round's completed-score field mean; this is an outcome normalization, not a pre-round predictor. Every player's ability uses only events ending before the new event's recorded start. Field strengths vary and survivors change after the cut. Players missing later scores are retained in attrition, not scored as zero: the comparison is conditional on observed complete later rounds, so cut/withdrawal selection can bias it. No timestamped live trigger is reconstructed from these retrospective feeds.

Excluded: named multi-course rotations, team/match-play/Stableford events, TOUR Championship, Q-School, exhibition and Hero fields; events without four complete scored rounds. Playoff holes and incomplete/mismatched hole sums are excluded uniformly. The script does not revisit the earlier Sunday-variance card.

Full denominators, bin counts, missing later scores, per-event contrasts and source hashes are in [golf-weekend-screen-2026-09-14.json](golf-weekend-screen-2026-09-14.json). Sources: [ESPN 2024](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2024), [ESPN 2025](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025).

Reproduce: `state/runtime/research-venv/bin/python tools/explore_golf_weekend.py`. Raw publisher responses stay local and ignored.
