# Early payout scanner: routine and site

The scanner prices every moneyline covered by a book's early-payout rule and publishes the playable ones to the site at `docs/index.html` (GitHub Pages). The analysis behind it is in the [early payout report](../reports/early-payout-2026-09-22.md).

## What one scan does

1. Pulls today's and the next two days' events and moneylines from BettingPros (FanDuel, bet365, Pinnacle when listed, the prediction-market exchanges and the other US books).
2. For each team at a book with a payout rule (`config/early_payout.json`):
   - **fair win probability**: Pinnacle de-vigged if quoted, otherwise the median of the exchanges (Novig, ProphetX, Kalshi, Polymarket), otherwise the median of the other sportsbooks;
   - **payout extra**: looked up from `config/early_payout_curves.json`;
   - **EV** = book decimal odds × (fair + extra) − 1.
3. Marks a row playable when EV is at least 2% and it passes the gates: quote under three hours old, game not started, claim not above 15% (large claims are usually a stale or mismatched quote).
4. Suggests a stake: a quarter of Kelly on the payout-adjusted win probability, capped at 2% of the bankroll in the config.
5. Writes `live/early-payout/picks.json`, appends new or moved playable prices to `live/early-payout/history.csv`, and rebuilds `docs/index.html`.

```bash
BETTINGPROS_API_KEY=... python3 -m beating.early_payout scan
python3 site/build_early_payout.py
```

The key is the one BettingPros' own website sends, the same one `beating-the-opener` uses. Set it as `BETTINGPROS_API_KEY` in the cloud environment's variables (claude.ai/code, environment settings), not in the repository.

## Coverage today

BettingPros lists NFL, college football, NBA and MLS. It does not list Pinnacle for NFL moneylines, so NFL prices against the exchanges. Soccer is MLS only; the payout curve comes from the top five European leagues, so treat MLS numbers as approximate. European soccer needs another odds source.

## Routine

`trig_01UHusCXLyAry36A9XDudAoU`, created 2026-09-22 and enabled: hourly at :17, 10:00–00:00 Eastern (`17 14-23,0-4 * * *` UTC; an hour earlier in winter). Notifications are off at the routine level; the session sends one push notification only when new playable prices appear. Manage it at https://claude.ai/code/routines/.

Setup still needed before it produces anything:

1. Add `BETTINGPROS_API_KEY` to the routine's environment variables. Until then each firing replies with the missing-key line and commits nothing.
2. Attach `soldoutbudokan/BeatingAnything` to the routine as a repository source, so fired sessions can push to main. It was created without one.
3. Turn on GitHub Pages: repository Settings → Pages → Deploy from a branch → `main`, folder `/docs`. The site then lives at https://soldoutbudokan.github.io/BeatingAnything/.

Prompt:

```text
You are the early-payout scanner routine for soldoutbudokan/BeatingAnything. Read docs/early-payout-routine.md first. Each firing, from the repo root on main:

1. Run `python3 -m beating.early_payout scan`. If it prints that BETTINGPROS_API_KEY is not set, reply with that single line and stop without committing.
2. Run `python3 site/build_early_payout.py`.
3. Read live/early-payout/picks.json. For each key in new_keys, the matching row is a new playable price. If there are any, send exactly ONE PushNotification listing each: team, book, price, break-even price, EV, stake, start time in Eastern. Never notify a key that is not in new_keys.
4. Commit live/early-payout/ and docs/index.html with the message "early-payout: <n> playable, <m> new" and push to main. If nothing changed, do not commit.
5. Reply with a table of every playable row (team, sport, book, price, break-even, EV, stake, start ET, matchup), then the scan summary line, then any scan errors.

Never place bets. Never edit picks.json, history.csv, config/ or the payout curves by hand. Times are Eastern.
```
