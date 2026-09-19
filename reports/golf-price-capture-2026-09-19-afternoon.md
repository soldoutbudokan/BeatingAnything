# September 19 afternoon: round-three prices cleared; no next-round sample

**The new capture supplies no pre-round or cross-course matchup.** It establishes a source transition after round three became official, without changing any hypothesis result.

Run `55fce77a66444be4837401fba11add62` used the unchanged Biltmore configuration for one manual cycle, **18:59:23–19:04:38 UTC** (14:59–15:04 Toronto), more than four hours after the morning capture. All **158 requests returned HTTP 200**, with zero failures, and the process exited normally. The [offline audit](../tools/audit_golf_price_capture.py) verified all **323** request/body/decoded artifacts; its [JSON report](golf-price-capture-2026-09-19-afternoon.json) pins the source and derived inventory hashes.

| Observation | Morning capture | Afternoon capture |
| --- | ---: | ---: |
| Recognized FanDuel-linked price fields | 870 | 728 |
| REST selection observations | 794 | 652 |
| Distinct REST market/selection combinations | 702 | 580 |
| Distinct REST market IDs | 26 | 15 |
| Complete two-player market IDs | 12 | 2 |
| Displayed round-three matchup IDs | 10 | 0 |
| Official round-three status | In progress | Official |
| Posted round-four tee groups | 0 | 0 |

Both snapshots requested the same 149 player drawers, with prices in 84 and no prices in 65. All ten earlier round-three matchup IDs and the third-round-leader market are absent from the afternoon REST responses. The next round's tee times and matchup prices have not appeared in this captured view; that does not establish their absence from the entire sportsbook.

The remaining complete pairs are **72-hole tournament matchbets**, each retained in two player drawers with consistent prices:

| Market ID | First complete pair | Overround |
| --- | --- | ---: |
| `42.608134213` | Eric Cole −250 / Marco Penge +200 | 4.762% |
| `42.608134225` | J.T. Poston −2000 / Corey Conners +800 | 6.349% |

Both belong to the already-started tournament, on the same course. The snapshots are not designated entries or closes. There is no model comparison, outcome grading, ROI or CLV calculation. The 152 generically named price fields remain unvalidated; the direct-link attribution count does not verify execution or jurisdiction. A recursive field-name check of all REST player payloads found no timestamp, publication, update, suspension, status or tradability field. Provider HTTP dates remain separate from the missing bookmaker quote-update clock.

The official leaderboard uses `F*` for completed back-nine starts. The offline audit now recognizes this alongside `F`, with a regression test. Both source snapshots were re-audited with the same code, and all prior morning counts and pair classifications remain unchanged. The audit also retains each tee-time round's status, group count, receipt clock and exact source artifact in its report.

**Remaining dependency:** G11 still needs actual pre-round cross-course FanDuel prices with applicable terms and usable clocks. This single-course event cannot supply that contrast. The prepared RSM configuration and historical-archive access question remain the available routes; this capture does not reopen a failed screen or restart a scheduled job.

Reproduce locally:

```sh
state/runtime/research-venv/bin/python tools/audit_golf_price_capture.py 55fce77a66444be4837401fba11add62 --report reports/golf-price-capture-2026-09-19-afternoon.json
state/runtime/research-venv/bin/python -m unittest discover -s tests
```

Validation: **232 tests pass**. The two remaining pairs' odds and margins, the removed round-market IDs, and the three posted tee-time rounds were also checked directly against retained raw bodies. No further capture was started.
