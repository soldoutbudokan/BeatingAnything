# Bounded forward market collection

The collector is ready for provider-supported markets with an existing
authorized The Odds API key. **No real FanDuel or Pinnacle prices have been
collected in this restart:** this
environment has no `ODDS_API_KEY`. The offline example is synthetic. One official
MLB schedule and one scheduled-game feed were successfully retrieved; that is
game-state access, not live odds coverage or a completed odds/game-state join.
**A key is not the only blocker for the tennis hypotheses:** the required
next-game hold/break and set correct-score markets are not documented by this
provider, and no usable FanDuel source for them has been verified.

## Run locally

From the repository root, with Python 3.12 and `ODDS_API_KEY` already set in the
environment:

```bash
python -m beating.forward_collect --config config/forward-collection.example.json
```

This makes one bounded pass: at most 500 HTTP requests and 100 reserved API
credits. It can stop partway through the board. Nothing runs in the background.
There are no new dependencies. The key is read from the environment; request
URLs saved by the collector omit it.

For a longer, explicit collection window, adjust the sports and allowance to
your existing subscription. For example, this requests up to twenty passes,
waiting three minutes after each completed pass:

```bash
python -m beating.forward_collect --sports baseball_mlb,americanfootball_nfl --cycles 20 --interval-seconds 180 --max-credits 1000 --max-requests 2000 --mlb-game-state
```

Those caps apply to the whole process, not to each cycle. This command can
consume up to 1,000 subscription credits; it does not purchase credits. A small
cap does not provide broad continuous coverage. Narrow the sport list to the
current research question if credits are scarce. `--sports '*'` discovers active
sport keys and omits outright/futures sports. Selected events are shuffled using
the recorded run ID and cycle as the seed, so restarting with a small cap does
not always spend the allowance on the first sport. The exact event order is
saved. This changes coverage order, not quote content.

Without a key, demonstrate the complete acquisition path offline:

```bash
python -m beating.forward_collect --demo
```

The built-in fixture uses `SYNTHETIC` names and 2020 clocks. Its summary and every
response record say `synthetic: true`; `real_odds_responses` is zero. It makes no
network requests, overrides cycles to one, and writes to `data/raw/forward-demo`.

To collect only official MLB state without any odds subscription:

```bash
python -m beating.forward_collect --mlb-only --cycles 20 --interval-seconds 180
```

## NFL/NBA priority after the September 13 user update

The focused configuration follows the user's preference for more season runway:

```bash
python -m beating.forward_collect --config config/forward-collection.nfl-nba.json
```

It uses the existing collector and the same one-cycle, 100-credit allowance,
selects NFL/NBA events and leaves MLB state collection off. An existing authorized
`ODDS_API_KEY` is still required; none was available for this checkpoint, so this
configuration has not collected real odds. A future research run may use it only
with an already authorized key and allowance. Preseason/offseason availability
and live coverage must be established from actual responses.

The provider's [market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html),
checked September 13, documents these relevant keys:

| Hypothesis | Documented key | Remaining market question |
| --- | --- | --- |
| NFL wind/long kicks | `player_field_goals`, `player_kicking_points` | No longest-field-goal key is listed. A 50+ yard effect does not establish an all-distance field-goal-count effect. |
| NFL garbage-time/backup-QB receivers | `player_receptions`, `player_reception_yds` | A full-game total is not a remaining-only total; verify live availability, accrued statistics and settlement. |
| NBA missing creator | `player_assists`, `player_assists_alternate` | Verify actual FanDuel pairs before/after an issue-stamped absence announcement. |

Documented keys do not establish FanDuel/Pinnacle pairs, a particular bookmaker's
inventory, an executable quote or stale pricing. Keep the exact market identity
and clocks with each observation. The NFL archive already inventoried in this
repo contains none of these props; do not repeat that search.

## Provider coverage and credit units

The documented v4 flow is sports → events → event markets → event odds. Events
include scheduled and in-play games. Event-market discovery gives recently seen
keys, not every supported market. Event odds can request props, alternate lines,
and other supported markets; availability varies by sport and bookmaker. The
collector requests the union for `fanduel,pinnacle` without dropping one-sided,
unmatched, started, or unfamiliar markets.

Sports/events discovery is quota-free. Each event-market discovery costs one
credit. Event odds cost the number of distinct markets returned times the
region-equivalent count; up to ten explicitly selected bookmakers count as one
region. Thus twenty market keys for these two books reserve twenty credits.
Empty/partial odds responses may cost less. Actual usage headers are retained.
See the [official v4 reference](https://the-odds-api.com/liveapi/guides/v4/).

The tennis coverage check on September 12, 2026 found:

| Market needed | Published key / coverage | Research consequence |
| --- | --- | --- |
| Next service game hold/break | No documented key | No verified source for the direct double-break test |
| Exact set score, e.g. 6–0 or 6–1 | No tennis key; `correct_score` is listed for soccer | Cannot claim coverage for set-concession tails |
| First-set games total | `totals_s1`, `alternate_totals_s1` | Possible related market; FanDuel availability at a live trigger still unverified |
| First/second-set winner | `h2h_s1`, `h2h_s2` | Published support; no current paired FanDuel/Pinnacle response inspected |
| First-set game handicap | `spreads_s1` | Published support; bookmaker/live coverage unverified |
| Challenger events | Not in the published tournament coverage | No verified coverage for the earlier Challenger research target |

The [market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html)
provides the keys. The [tennis coverage page](https://the-odds-api.com/sports/tennis-odds.html)
describes Grand Slams and ATP/WTA 500/1000 events, mainly match-winner prices and
limited game spreads/totals. Published keys do not establish specific bookmaker
availability at the required state. Absent keys are a documented coverage gap,
not a claim about every future provider release.

Credit reservations use requested keys and are not refunded locally after a
timeout or smaller response. The collector also checks the provider's remaining
balance before another charged request. A stopped/partial run exits with code 2;
the saved summary gives its reason. HTTP failures, malformed JSON, and network
errors stop the run without retries. An access denial is never bypassed.

## What is saved

Normal output is `data/raw/forward-markets/`. Each invocation gets a new run ID:

- `<run-id>/raw/*.body`: every complete response body, byte for byte, including
  discovery responses, all odds fields, and HTTP error bodies.
- `index.jsonl`: append-only response metadata, request context, inventories,
  coverage order, SHA-256, errors, and per-run summaries.
- `<run-id>/summary.json`: stop reason, completed cycles, request counts, reserved
  and reported credits, synthetic status, odds/game-state response counts.

The record stores collector request start and response receipt in UTC, monotonic
request duration, and HTTP `Date` separately. Provider `timestamp`, bookmaker
`last_update`, and market `last_update` stay distinct; absent fields stay null.
Event-odds responses normally supply market-level update clocks. HTTP `Date` and
collector receipt time do not establish when a bookmaker changed its price.

MLB collection retains the unfiltered official schedule and full game feed for
non-final games scheduled today or yesterday in UTC. Its clock index preserves
`gamePk`, `metaData.timeStamp`, and current-play start/end times as supplied. All
play events, substitutions, and other timestamps remain in the raw response.
It explicitly records `join_status: unmapped` and a null odds event ID. A later
verified mapping must handle schedule changes and doubleheaders; name matching
alone is not supplied as proof.

Raw data remain ignored by Git, like the repo's existing research data. Copy
them to durable storage on the collection machine. Do not run multiple writers
against the same output directory.

## Current verification and limits

On September 12, 2026, the six focused unit tests and the offline CLI demo passed.
They cover raw-byte retention, independent/missing clocks, props/alternate
market traversal, source failures, and allowance enforcement:

```bash
python -m unittest tests.test_forward_collect -v
```

An actual `--mlb-only --max-requests 2` smoke run retrieved:

| Resource | Received UTC | Result |
| --- | --- | --- |
| Official September 11–12 MLB schedule | 2026-09-12 14:34:47.888705 | HTTP 200; 38,557 bytes |
| Official game 822685 full feed | 2026-09-12 14:34:54.239537 | HTTP 200; 192,237 bytes; scheduled/preview |

The game's feed timestamp was `20260912_143444`; play timestamps were absent
because the game had not started. The next request stopped at the explicit
two-request cap. No polling process was left running. Local evidence is under
`data/raw/forward-mlb-smoke/1d05e1828d914ce49f784046b2cdba62/` with its entries in
the adjacent index.

This adapter cannot promise FanDuel's complete board, live tennis game/set
markets, Challenger coverage, executable prices, suspension state, or identical
FanDuel/Pinnacle settlement rules. Response capture alone proves none of those.
The Odds Gap is not used for polling. No direct FanDuel endpoint is called.
Existing monitoring behavior and promotion gates are unchanged; this module
never imports the monitor or produces predictions, betting alerts, or wagers.
