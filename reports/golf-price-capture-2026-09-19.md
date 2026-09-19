# September 19: actual FanDuel-linked golf prices acquired

**The public PGA route now supplies derivative prices. No edge has been established.** This supersedes the September 14 empty-price observation for current source availability, while preserving those earlier runs. It does not reopen any failed sport-side screen.

## Capture

One bounded manual cycle ran on September 19, 2026, **14:37:36–14:42:51 UTC** (10:37–10:42 Toronto), with the unchanged Biltmore configuration. Run ID: `c677434604d04c5f9a10b33f250f9ab2`. All **158 requests returned HTTP 200**, with no failures; the process exited normally. It requested 149 player drawers, of which 84 contained prices and 65 did not. Official field metadata contained 139 players and ten alternates; these are source lists, not 149 tournament starters.

The collector recorded **870 recognized price-field observations**, all with direct FanDuel selection-link attribution, and zero with an explicit book label on the price's own enclosing object. The market catalog separately names FanDuel. Its label is not inherited to establish quote attribution. Another 155 fields remain unvalidated; they are not silently added to the price count. These include three invalid zero-price sentinels in Nick Taylor finish markets and 152 generically named `odds` fields in the HTML/GraphQL outright views.

The [offline audit](../tools/audit_golf_price_capture.py) verified the byte count and SHA-256 of **323 request, response and decoded artifacts**, reproduced the REST price inventory from the raw bodies, and kept each complete pair inside a single response. The [machine-readable report](golf-price-capture-2026-09-19.json) pins the run records, source manifest, script and local derived inventory. Raw and detailed derived data remain ignored under `data/raw/golf-forward/c677434604d04c5f9a10b33f250f9ab2/`.

## What the prices cover

The REST player drawers contain **794 attributed observations**, which reduce to **702 distinct market/selection combinations across 26 market IDs**. The remaining 76 recognized observations are in the HTML page and are not added again to this REST inventory.

| REST market type | Observations | Distinct market IDs | Distinct market/selection combinations |
| --- | ---: | ---: | ---: |
| Finish | 438 | 6 | 438 |
| Group props | 85 | 5 | 17 |
| Matchup props | 48 | 12 | 24 |
| Outright winner | 76 | 1 | 76 |
| Player props | 147 | 2 | 147 |

These counts do not prove complete full-field markets. In particular, tournament group props are not automatically round three-balls. `THREE_BALL` and `NATIONALITY` appear in the catalog, but no corresponding player-market prices appeared in this capture. That is a coverage observation, not proof the sportsbook offers none.

### Complete two-player matchups

There are **24 complete response-level pair observations representing 12 distinct markets**: ten displayed as round-three 18-hole matchbets and two as 72-hole matchbets. Each observation contains both attributed sides with distinct selection IDs and player IDs. The twelve market IDs have consistent selection identities across the duplicate drawers.

Their observed two-way overrounds range from **5.278% to 7.619%**, computed as `1/decimal_price_A + 1/decimal_price_B - 1`. This is a price diagnostic, not expected return. Seven of the twelve first complete observations have both prices inside the existing 1.20–6.00 band; that alone supplies no eligibility or edge.

Examples below use the first complete response for each named market, not best prices selected from different responses:

| Displayed market | Prices | Overround |
| --- | --- | ---: |
| R3 Chris Kirk / Kevin Roy | −250 / +187 | 6.272% |
| R3 Austin Eckroat / Zecheng Dou | +125 / −163 | 6.422% |
| R3 Takumi Kanaya / Davis Chatfield | −188 / +150 | 5.278% |
| 72-hole Eric Cole / Marco Penge | +110 / −138 | 5.602% |

Eckroat/Dou has two price versions during this five-minute cycle. Both complete observations are retained; the audit never constructs a synthetic pair using the best side from each version.

## Why this is not yet a G11 price test

- **Same course:** official metadata and every matched assignment identify The Cliffs at Walnut Cove, course `942`. All ten round matchups pair players from different official groups on that same course. There are zero cross-course round pairs in this event capture. Applying the pooled +1.709 relative-to-par contrast here would be invalid.
- **Play had started:** all round-three groups were scheduled between 11:33 and 13:45 UTC. The independent official leaderboard response retained before the price requests shows completed holes for both players in all ten round matchups, including back-nine `thru` values with an asterisk. The 72-hole tournament was also already in progress. None of these is a pre-start observation for its displayed market period.
- **Period metadata is inconsistent:** four round-three market IDs have a non-null numeric `bettingPeriod` of 1 or 2 in at least one drawer, despite their displayed round-three title. The same market can carry different values in its two players' drawers. The audit retains every value and treats the title as an explicitly labeled interpretation; it does not repair the numeric field or assume it is a reliable round number.
- **Three clocks remain distinct:** request/receipt clocks, HTTP server dates, and official tee times are retained. No player-price payload supplies a quote-update clock. HTTP `Date` and a 60-second cache policy are not bookmaker publication times. Earlier sport-state responses are attached only within the same capture cycle and cannot be backfilled from a later cycle.
- **Terms remain unresolved:** a FanDuel selection link establishes the destination and selection IDs, not the quote's jurisdiction, scoring convention, settlement rules, current tradability or an accepted price. The partner's Ontario configuration is not sufficient verification.

No outcome grading, model fit, EV estimate, CLV estimate, paper entry, alert or wager was performed. No paid archive was acquired and no denied endpoint was retried.

## Continue from here

The binding question is now **coverage of suitable pre-round, cross-course offers with usable terms and clocks**, rather than whether the PGA route can return any actual FanDuel-linked price. Keep the source and this inventory for subsequent bounded manual captures. A later capture after the next round's actual tee times and markets post is a distinct checkpoint; do not relabel this live snapshot as an opening price or keep polling the same board merely to accumulate rows.

G11 still needs the declared multi-course price comparison, using an appropriately accessible historical archive or future multi-course event. Same-course offers cannot test it. Its gross-versus-relative scoring distinction and event-specific effects remain essential. All closed sport-side results and the 13-test confirmatory allowance remain unchanged. Scheduled jobs and watches stay paused.

Reproduce the audit offline:

```sh
state/runtime/research-venv/bin/python tools/audit_golf_price_capture.py c677434604d04c5f9a10b33f250f9ab2 --report reports/golf-price-capture-2026-09-19.json
state/runtime/research-venv/bin/python -m unittest tests.test_golf_price_capture tests.test_golf_collect
```

The focused suite passes 41 tests and the full suite passes **231 tests**. Tests cover incomplete pairs, inconsistent IDs, conflicting book labels, altered artifacts, numeric-period conflicts, and prevention of later sport state leaking into earlier quotes. A separate raw-body calculation reproduced all twelve market identities, both-side prices and overrounds without calling the audit's extraction functions; it also reconciled the three rejected zero-price sentinels.
