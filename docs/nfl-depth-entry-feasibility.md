# Fixed NFL entry/depth-chart feasibility

All **285 retained 2025 NFL entries** have an unambiguous listed rank-one QB for
both teams in the latest strictly prequote team snapshot: **570/570 team-entry
joins**. This is metadata coverage, not confirmation of eventual starters or
historical publication availability. No entry was removed and no age, history
or model eligibility threshold was selected.

The [reproducible audit](../tools/audit_nfl_depth_entries.py) hash-checks the
retained fixed-entry projection, the 554,215-row `depth_charts_2025.csv.gz`, and
the 49,492-row prior-2024 PBP feature projection. It strips entry prices and
reference observations before analysis. The depth schema contains `dt`, team,
ESPN/GSIS IDs, position and rank, but no career-experience or rookie field.

For each home/away team it chooses the latest team `dt` **strictly before** the
already fixed entry quote, then requires a unique nonmissing GSIS identity for
`pos_abb == QB` and `pos_rank == 1` in that exact snapshot, without conflicting
ESPN IDs. An absent or ambiguous QB would stay explicit; the join never falls
back to an older convenient snapshot. None occurred in this retained population.

| Coverage item | Count |
|---|---:|
| Fixed entries retained | 285 / 285 |
| Unambiguous prequote QB team entries | 570 / 570 |
| Distinct selected QB GSIS identities | 48 |
| Selected QBs appearing as a 2024 passer | 36 |
| Selected QBs with an identified 2024 dropback | 37 |
| Selected QBs without identified 2024 dropback history | 11 |
| Team entries without that prior history | 83 / 570 |
| Entries with at least one QB without that prior history | 77 / 285 |
| Rank-one changes since a team's previous fixed entry | 21 |
| Rank-one changes since the immediately previous team snapshot | 0 |

Prior-history overlap uses a nonmissing `passer_player_id` on a 2024 row with
`qb_dropback == 1`, or `rusher_player_id` only when the dropback is explicitly a
QB scramble and the passer ID is absent. The additional identity beyond the
36 passers is therefore recovered from a labeled scramble, not inferred from
an ordinary rush. Row counts are identity-coverage diagnostics, not evidence
of sufficient pressure history; pressure-feature quality is a separate audit.

The **11 no-history QBs have unverified rookie/career status**. An absent 2024
dropback record cannot distinguish a rookie from a veteran with no prior-season
appearance, a nonpassing role, or incomplete identity/history coverage. No rookie
designation was fabricated. There are 48 selected ESPN identities, with no
selected ESPN-to-GSIS or GSIS-to-ESPN conflicts, missing ESPN IDs, or duplicate
rank-one rows.

| Age of selected snapshot at entry | Hours |
|---|---:|
| Minimum | 6.67 |
| Median | 14.69 |
| 95th percentile | 18.72 |
| Maximum | 42.59 |

These ages describe the retained snapshot timestamps; they impose no freshness
cutoff. Change counts use only observations strictly before each quote and
compare published depth roles, never eventual starters or postquote snapshots.
The [JSON audit](../reports/nfl-depth-entry-feasibility.json) also includes exact
second-based quantiles, week coverage and the hash of an ignored 285-entry
home/away join projection at
`data/raw/nfl-depth-entry-feasibility/entry-depth-metadata.json`.

The source limitations in the [depth source audit](../reports/nfl-depth-chart-source-audit.json)
remain material. `dt` records source snapshot time, not independently established
first-publication time. The retained seasonal asset was obtained later, and the
publisher can remap historical GSIS IDs. Matching current GSIS/ESPN identities
does not prove that this enrichment existed at the quote time. Listed rank-one
status is not proof of who started or played. This check neither resolves those
publication questions nor evaluates NFL outcomes, EV, CLV, returns or a model.
It freezes no experiment and changes no existing fixture or protocol.

Run with any compatible Python 3 interpreter; only the standard library is used:

```sh
python3 tools/audit_nfl_depth_entries.py
```

The script reads only retained, hash-pinned inputs, writes its audit and ignored
join projection, and performs no network acquisition.
