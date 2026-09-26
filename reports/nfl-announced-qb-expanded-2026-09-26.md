# Expanded announced-QB source/price feasibility

The ten announcement-qualified fixtures contain **100 distinct priced player-games across both teams**. The declared prior-team proxy retains **47 matching** and **2 unresolved**, a conservative coverage bound of **49**, below the unchanged **100-receiver-game** gate. 51 latest prior clubs are opponents and 0 are other clubs. The exact retained cohort therefore stops before receiver-role extraction, modeling or grading; the underlying hypothesis remains unresolved.

| Fixture | Offense | All teams | Matching | Opposite | Other | Unknown | Matching + unknown |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024_02_IND_GB | GB | 9 | 6 | 3 | 0 | 0 | 6 |
| 2024_03_GB_TEN | GB | 11 | 6 | 5 | 0 | 0 | 6 |
| 2024_03_MIA_SEA | MIA | 9 | 4 | 5 | 0 | 0 | 4 |
| 2024_04_TEN_MIA | MIA | 10 | 4 | 6 | 0 | 0 | 4 |
| 2024_05_MIA_NE | MIA | 12 | 4 | 6 | 0 | 2 | 6 |
| 2024_06_TB_NO | NO | 8 | 4 | 4 | 0 | 0 | 4 |
| 2024_08_CAR_DEN | CAR | 10 | 5 | 5 | 0 | 0 | 5 |
| 2024_11_JAX_DET | JAX | 11 | 5 | 6 | 0 | 0 | 5 |
| 2024_12_SF_GB | SF | 11 | 5 | 6 | 0 | 0 | 5 |
| 2024_15_ATL_LV | LV | 9 | 4 | 5 | 0 | 0 | 4 |

The generous inclusive bound retains Las Vegas despite a possible discovery query-cap deviation across overlapping injuries. Excluding LV gives **9 fixtures / 91 both-team player-games** and **43 matching + 2 unknown = 45** under the proxy. Even the strict both-team ceiling is below 100. No further source query was used to resolve the LV episode boundary.

The source search covered all 32 teams with 32 standardized and 40 targeted queries (72 total). These ten fixtures form seven absence groups: Miami's three quotes share Tua's absence, Green Bay's two share Love's injury, and Las Vegas is one nested episode. Seven groups are not proof of independent forecast errors. The LV discovery is not certified as fully protocol-compliant.

Each quote is the earliest qualifying snapshot strictly after all required announcement evidence for that game/player. Ambiguous multiple lines at that exact time are omitted. The candidate prices retain legal American odds, both decimal sides 1.20–6, paired margin 0–12%, both recorded updates 0–300 seconds before entry, and entry before the earlier independent/provider start. No later quote rescues an earlier row's failed clock.

Membership uses only the latest 2024 REG weekly player club whose independently matched fixture start plus 72 hours is strictly before entry. The JSON records every player's prior fixture, club, kickoff and availability time. It also preserves the 47 retrospective roster matches separately; those were provisional diagnostics, not the causal eligibility rule.

Odell Beckham Jr. and Kendrick Bourne at MIA–NE have no available 2024 REG club record under that clock and remain unresolved. Both count toward the conservative bound; no current-game appearance or later club assignment resolves them.

All input, source-ledger, declaration and retained source hashes are in the JSON. Reproduce in an isolated output location with `state/runtime/research-venv/bin/python tools/inventory_nfl_announced_qb_expanded.py --output-stem /tmp/nfl-announced-qb-expanded-check`; the script refuses to overwrite outputs.

The [independent audit](nfl-announced-qb-expanded-audit-2026-09-26.json) matches all 100 original price rows and prior-club classifications, verifies 19 input/source/artifact hashes, and independently checks exact odds/margin and quote-clock gates. All prior fixture IDs, clubs, starts and 72-hour availability boundaries agree; the smallest prior-start lead is 136.18 hours. The guarded script also passes compilation, exact isolated reproduction and overwrite refusal. No target outcomes or receiver-role values were read for these checks.

Rules: [inventory declaration](../docs/nfl-announced-qb-expanded-inventory-declaration-2026-09-26.md), [quote deduplication](../docs/nfl-announced-qb-quote-dedup-addendum-2026-09-26.md), [prior-team proxy](../docs/nfl-announced-qb-prior-team-addendum-2026-09-26.md). Sources: [NFC](nfl-announced-qb-source-nfc-2026-09-26.json), [AFC North/South](nfl-announced-qb-source-afc-north-south-2026-09-26.json), [AFC East/West](nfl-announced-qb-source-afc-east-west-2026-09-26.json).

Material limitations:

- This is a bounded source-and-price feasibility inventory, not a model, forecast, return test or edge claim.
- Latest available prior club is the declared proxy, not transaction-proof target-game membership. Unknown clubs remain in the conservative bound; opposite/other prior clubs fail the proxy.
- The 72-hour start-based availability delay is a fixed assumption applied to a retrospective weekly metadata file; no contemporaneous historical release receipt establishes actual publication latency.
- Official pages were retrieved retrospectively. Their maximum publication/revision clock is source-asserted; reused Miami sources retain metadata/hash evidence but not full HTML.
- There were 32 standardized team queries and 40 targeted queries, 72 total. LV injury follow-ups were budgeted separately for overlapping O'Connell thumb, Minshew collarbone and O'Connell knee absences, a potential per-episode query-cap deviation. The inclusive cohort retains LV only as a generous coverage check; strict sensitivity excludes it. Other unresolved weekly replacement confirmations are not carried forward. This is not an exhaustive injury-episode census.
- Published processed prices lack original upstream raw JSON/unmerged sides. Publisher code passes odds through, but duplicate key omits snapshot time and can overwrite side prices while retaining first-row clocks. Literal row-clock eligibility cannot independently authenticate side-price/clock association.
- Retrospective roster team compatibility is diagnostic only. No target-game appearance, receiver-role, air-yard-share, target outcome, score or actual-starter column was used in this computation.
- Official-source searches exposed incidental outcome snippets, and earlier research inspected some NFL labels. This inventory makes no globally uninspected or fresh-holdout claim.
- LV's nested O'Connell injury occurs within the broader Minshew absence; the grouping is not an independence claim.
