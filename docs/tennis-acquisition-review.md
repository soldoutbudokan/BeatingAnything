# Tennis acquisition review before evaluation

The nine daily parse errors are genuine ambiguities in the saved source identity
cells. No correctable parser defect was identified. Keep the existing source
quality blocks and strict identity exclusions; no parser, raw source, sample pin
or parsed cache was changed during this review.

All nine fixtures appear under **UTR Pro Tennis Series 5** in pages whose selected
filter is ATP singles. For each fixture, one identity cell contains a
`/doubles-team/...` link and the other contains only a display name followed by
`/`. Neither side supplies a `/player/...` identity link. Five doubles-style
links repeat the same player slug in both positions. This markup does not
establish two stable singles identities, or establish whether the underlying
fixture itself was singles. Extracting a convenient name or one member of a
doubles-style URL would invent an identity mapping.

| Source date | Event ID | Parser error |
|---|---|---|
| 2024-06-04 | te:2632789 | missing_or_ambiguous_player_id |
| 2024-06-05 | te:2633399 | missing_or_ambiguous_player_id |
| 2024-06-06 | te:2634043 | missing_or_ambiguous_player_id |
| 2024-06-07 | te:2634579 | missing_or_ambiguous_player_id |
| 2024-06-09 | te:2637711 | missing_or_ambiguous_player_id |
| 2024-07-01 | te:2657087 | missing_or_ambiguous_player_id |
| 2024-07-02 | te:2658413 | missing_or_ambiguous_player_id |
| 2024-07-03 | te:2659223 | missing_or_ambiguous_player_id |
| 2024-07-05 | te:2660415 | missing_or_ambiguous_player_id |

The errors remove nine ambiguous fixtures from normalized player history. None
is a Challenger fixture, and a direct check against every immutable sample pin
confirms **zero affected sampled events**. This does not prove that historical
features for later sampled players are complete: the omitted identities and
their possible history contribution remain unknown. No performance or feature
impact was estimated.

The read-only consistency rehearsal started at **2026-09-09 22:26:32 UTC** and
finished at **22:27:59 UTC**. Its initial append-only ledger snapshot contained
13,049 complete lines and 4,636 successfully acquired detail sources. It checked
all **1,826 daily files and sample pins**, all **1,826 daily parsed caches**, and
all **4,636 completed detail files and parsed caches**: 6,462 raw sources in
total. The daily pins define 5,453 unique sampled events.

The rehearsal found **zero** raw/meta/ledger hash mismatches, source URL or byte
count mismatches, sample selection mismatches, current-parser/cache differences,
or sampled-fixture/detail identity or date discrepancies. First consistency
failure: none. These nine source errors already appear identically in the frozen
daily caches; they are not a live collector process-version discrepancy.

Rehearsal parser SHA-256:
`6e67796f00951dfa159b7e76efc351bbdaea2c352a0de5ccda4e6ef749f3fdbb`.
Initial ledger snapshot SHA-256:
`6955b3b612283686fd4f1ad306db542de61be219f844603ce3a86b446a3f06b9`.
The temporary script and detailed rehearsal summary are retained locally under
ignored `state/audit_tennis_parser_rehearsal.py` and
`state/tennis-parser-rehearsal.json`.

This was a partial-acquisition rehearsal, not the final acquisition gate. It
covered only detail sources completed at the initial ledger snapshot, while the
single existing collector continued. All 5,453 frozen detail selections must
still be accounted for before evaluation. The rehearsal compares source parses
for equality; it does not assess betting eligibility, closing coverage, model
features, forecasts, labels, returns or performance. No full pipeline was
launched, and no model data, model output or evidence threshold was changed.

[The metadata-only audit](../reports/tennis-source-quality.json) retains each
date/event, identity-cell text and links, raw SHA-256, parsed-cache SHA-256 and
sample-membership check. Only identity cells were inspected for this diagnosis;
scores, strategy returns and outcome performance were not inspected. The saved
raw bytes were verified against their existing acquisition metadata hashes.
