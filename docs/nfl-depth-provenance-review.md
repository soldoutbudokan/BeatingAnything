# 2025 depth-chart publication and identity review

**Conditional support for research using a recorded publication proxy; insufficient proof of every row's original public version.** Of 221 retained timestamps, 219 map uniquely to a successful public publishing workflow. `dt` alone remains a load timestamp, as the [publisher dictionary](https://nflreadr.nflverse.com/articles/dictionary_depth_charts.html) states. No model, game-result labels or returns were examined, and no protocol was changed.

Three source routes were checked:

1. **Release vintage:** the [public depth release metadata](https://api.github.com/repos/nflverse/nflverse-data/releases/tags/depth_charts) lists all five 2025 formats, including QS, as created March 14, 2026. The retained gzip's SHA-256, `5cbc4d088a05c1c7b047ebdd2bacb480c97aac5849d46fc631fa041d09dd8ef7`, matches GitHub's asset digest exactly. This route yields no immutable in-season file version.
2. **Historical publisher code:** the [August 18 code](https://github.com/nflverse/nflverse-rosters/blob/140739bf9c6f80bbe435db1d058f92514141c337/exec/update-depth-charts.R), three sampled in-season run versions, and the previously recorded later version are byte-identical: SHA-256 `fd52589abef6be6dea3de21d92eb42af42b13527b3c295d88d93d91107262801`. They prepend new rows to history. The top-level transformations preserve timestamp/team/ESPN ID/depth-role fields but deliberately recompute historical GSIS IDs and clean names. The complete historical dependency chain, including the name helper, was not reconstructed. Present GSIS/name values cannot automatically be called their original as-published versions.
3. **Workflow history:** three pages of the [specific workflow's public runs](https://api.github.com/repos/nflverse/nflverse-rosters/actions/workflows/14022139/runs?created=2025-08-01..2026-03-15&per_page=100&page=1) contain 230 unique runs: 219 successes and 11 failures. Each of 219 archive timestamps falls inside exactly one successful run's start-to-update interval. The run's recorded `updated_at` occurs 9–56 seconds after `dt`. The only unmatched timestamps are `2025-08-03T10:09:07Z` and `2025-08-11T19:01:03Z`; their publication remains unresolved.

Three job-level spot checks corroborate the mapping:

| Run | Snapshot `dt` UTC | Job completed UTC | Run updated UTC |
| --- | --- | --- | --- |
| [September 4](https://github.com/nflverse/nflverse-rosters/actions/runs/17456255781) | 07:21:47 | 07:22:01 | 07:22:02 |
| [October 15](https://github.com/nflverse/nflverse-rosters/actions/runs/18520873494) | 07:17:51 | 07:18:12 | 07:18:13 |
| [December 15](https://github.com/nflverse/nflverse-rosters/actions/runs/20223784789) | 07:21:22 | 07:21:53 | 07:21:54 |

The [September workflow](https://github.com/nflverse/nflverse-rosters/blob/aa0388373e2749075412ae6729e78a38b41c2c07/.github/workflows/update_depth_charts.yaml) invokes the depth-update script daily. Retained old job responses have empty step arrays. An ordinary anonymous request for detailed September logs returned HTTP 403 and was not bypassed. Success metadata therefore corroborates processing and intended publication, without binding the archived rows to an original uploaded content hash. Only sampled code versions were inspected across the 11 distinct run commits.

For a prospective **research protocol decision**, the concrete candidate availability rule is to join selected snapshots to their successful-run completion proxy and require entry strictly after that time. The retained mapping uses `availability_proxy_at = run.updated_at`, preserves both unresolved timestamps, and changes no selection rules itself. Stable ESPN identities and the retrospective GSIS mapping still need explicit treatment. A universal 56-second or 24-hour publication bound is not established; the per-run timestamps are the actual recovered evidence. A first-ranked QB remains a listed role, not proof of who started.

The [machine-readable review](../reports/nfl-depth-provenance-review.json) records exact source URLs, capture times, hashes, failures and assumptions. Raw evidence and `depth-snapshot-run-matches.json` are retained under ignored `data/raw/nfl-source-audit/`; the mapping predicate is recorded in the report. This review supports the next narrow coverage/identity decision, without claiming an executable edge or a fully immutable historical depth archive.
