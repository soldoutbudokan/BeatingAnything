# Redundant-leg SGP pipeline

This pipeline replaces repeated market navigation and hand calculation with
an exact quote queue, reusable FanDuel partitions, an incremental SQLite cache,
and deterministic EV bounds. It supports the NFL and NCAAF market schema.
It makes no bets and starts no background job.

## What works now

- A complete offline replay reproduces the four McCaffrey observations from
  October 9, 2026, using one FanDuel partition.
- A documented OpticOdds adapter discovers fixtures, captures markets in batches
  of up to five fixtures/books, and requests theScore's exact SGP prices.
- Market normalization preserves book, event, player, region, settlement,
  selection IDs, thresholds and provider labels. Exact market mappings are
  configuration; unsupported names remain explicit coverage gaps.
- Candidate generation enumerates S-versus-R/C two-leg bases and redundant
  additions through four legs. Equivalent events are grouped for reporting,
  while every distinct redundant-leg construction remains in the price queue.
- Quotes and FD four-cell partitions are reused. Changed selection inventories
  invalidate prior keys; clock-only refreshes do not. TTL still expires prices
  when the inventory itself has not moved.
- Late responses, incomplete FD partitions, pushes, suspensions, stale/future
  quotes, mismatched legs, source-clock skew and historical/live mixing are tested.

**Live coverage is not established.** No OpticOdds key was available during this
implementation. Its [SGP reference](https://developer.opticodds.com/reference/post_parlay-odds)
lists theScore, but not FanDuel, and does not establish Ontario provenance.
The documented parlay response has no source timestamp. The adapter therefore
marks region, freshness and repeat confirmation unverified. It cannot emit a
confirmed live opportunity by itself. Neither a straight-prop feed nor the
provider's AI parlay price substitutes for the book's SGP price.

## Run the historical replay

From the repository root (Python 3.11+, no additional dependencies):

```bash
python -m beating.sgp demo --output data/raw/sgp-demo
python -m beating.sgp demo --output data/raw/sgp-demo
```

The second pass uses the saved cache. Inspect `plan.json` and `report.json` in
that directory. The replay plans **41** structural candidates, has recorded
prices for **four**, and uses **four FD quotes** once. The other 37 candidates
are explicitly missing observations, not ruled-out bets.

The four recorded prices are +1064, +1059, +997 and +869. The leading variant
reproduces approximately +39.97% power-model and +31.81% additive-model EV,
with minimum strictly profitable integer American odds +784 across both models.
These are historical, reference-model estimates, not current odds or an
independent calibration of the underlying probabilities. All four variants
represent one underlying event.

Fixtures live in `beating/sgp/fixtures/`. Their `replay:` IDs are local labels,
not provider IDs. Original observation clocks and evidence notes are retained.
The FD quartet had a group capture time; per-cell source clocks were not saved.
The game start time was not retained and is left null. Historical input always
produces zero live opportunities and cannot be submitted by `capture`.

## Collect a small provider sample

Use an existing authorized `OPTICODDS_API_KEY` environment variable. Do not put
keys in config files, source control or command arguments. The commands below
consume provider requests if a key is configured; they do not buy a subscription.

```bash
python -m beating.sgp discover \
  --league nfl --sportsbook theScore --sportsbook FanDuel \
  --max-fixtures 5 --max-requests 10 --request-interval 0.5 \
  --output data/raw/sgp-live
```

Requesting a book in discovery does not establish its coverage. The adapter
records the raw response and missing inventory. NCAAF is selected with
`--league ncaaf`; do not infer college coverage from NFL availability.

Review the returned market names before using
`examples/sgp/market-map.example.json`. Its names are examples, not live-verified
inventory. For a milestone market, explicitly map its exact name to
`{"stat":"C","side":"at_least"}` only after checking the contract and `points`
meaning. Do not infer milestones from names or silently convert an over line
into an at-least line. Confirm common settlement rules, including overtime and
player participation, before assigning the same settlement identity to books.

```bash
python -m beating.sgp normalize \
  --snapshots data/raw/sgp-live/snapshots.json \
  --market-map examples/sgp/market-map.example.json \
  --region CA-ON --settlement full-game-including-ot-reviewed-player-rules \
  --output data/raw/sgp-live/manifest.json

python -m beating.sgp plan \
  --manifest data/raw/sgp-live/manifest.json \
  --max-candidates 5000 --max-references 32 --max-legs 4 \
  --output data/raw/sgp-live/plan.json

python -m beating.sgp capture \
  --plan data/raw/sgp-live/plan.json --max-quotes 20 \
  --request-interval 0.5 --max-age 120 \
  --output data/raw/sgp-live/score-captures.json
```

The capture command prioritizes longer redundant constructions under its
budget. It reports truncation, checkpoints each response and retains raw hashes,
request/receipt times and exact entries. Request spacing is configurable, not a
claim about provider SGP limits. HTTP errors, including 429, stop collection
without retries. There is no AI fallback, browser session access or hidden
sportsbook endpoint in this implementation.

## FanDuel and independent confirmation handoff

The live FanDuel SGP adapter is still missing. A provider contract with the
required Ontario coverage, or a separate visible-betslip capture worker, must
supply the four exact quotes. This implementation exports the worker's queue:

```bash
python -m beating.sgp capture-template \
  --plan data/raw/sgp-live/plan.json --book fanduel \
  --output data/raw/sgp-live/fd-captures.json
```

A template contains no prices and no confirmation. Each observation must retain
the unmodified full `request`, its `key`, `status` (`priced`, `unavailable`, or
`error`), American price, receipt time, source time when actually supplied,
exact-leg verification and evidence. Do not substitute an HTTP receipt date for
a missing source timestamp. `confirmed`, `region_verified` and
`freshness_verified` are explicit capture attestations, not flags this runner
can independently establish. Unknown values stay false. A browser worker should
serialize bet-slip writes per session; multiple tabs can share one slip.

The current pipeline does **not** automate browser capture or final repeat
confirmation. Those remain an integration requirement. A useful next acceptance
test is one provider-priced McCaffrey-style ticket compared with a freshly
rebuilt Ontario bet slip, followed by a line-change and suspension test.

Once capture workers supply matching inputs:

```bash
python -m beating.sgp run \
  --manifest data/raw/sgp-live/manifest.json \
  --captures data/raw/sgp-live/score-captures.json \
  --captures data/raw/sgp-live/fd-captures.json \
  --state state/sgp.sqlite --max-quotes 100 \
  --output data/raw/sgp-live/report.json
```

The plan requires FD inventory with the same canonical event/player and reviewed
settlement identity. If the source cannot supply those fields, preserve the
coverage gap rather than inventing a match. The runner collects FD references
first and skips candidate collection when none is usable.

## Freshness, cache and report semantics

Default live limits are 120 seconds for quote/inventory age, 30 seconds across
an FD partition, 120 seconds across books, and a 30-second cache TTL. Both receipt
and available source clocks are checked. These are configuration choices, not
measured sportsbook guarantees. Started games are excluded. The current clock
advances during a run and all positive rows are checked again before reporting.

`opportunities` contains only positive rows with all required capture
attestations, a source timestamp and coherent fresh quotes. `needs_confirmation`
contains positive model comparisons missing those requirements.
`historical_opportunities` is always separate. The full `evaluations`, `gaps`
and `coverage` arrays prevent a partial scan from looking like a complete census.
Bounds use every whole FD cell contained by the target and every intersecting
cell; no probability interpolation is used. A failed additive de-vig is not
clipped and cannot qualify under the both-model rule.

The SQLite ledger preserves every request attempt. A later unavailable result
replaces the earlier price; a late response cannot overwrite a newer attempt.
Changing capture-file content also invalidates imported cache entries. Removed
selections must be omitted from a fresh inventory; explicitly inactive selections
are rejected. Revisions are scoped to one event/player/book/region/settlement,
so unchanged scopes keep their cache. Polling and rerunning these commands is
supported; streaming, automatic scheduling and distributed collection are not
implemented.

## Validation

```bash
python -m unittest discover -s tests -p 'test_sgp*.py' -v
python reports/sgp-rush-receive-2026-10-08/recompute_ev.py
```

Provider tests use synthetic HTTP responses. The historical replay tests the
real recorded arithmetic. Neither is a live scraping throughput measurement.
Benchmark live speed only after source fidelity is established, measuring
verified quotes per minute, stale/mismatch rate, covered candidates and provider
usage rather than raw request count.
