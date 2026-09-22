#!/usr/bin/env python3
"""NFL 6-point teaser legs: Wong rule (published 2001) plus a total filter chosen on 1999-2014.

python tools/explore_nfl_teasers.py
Downloads pinned nflverse games.csv (closing spread/total and final scores) if missing.
Writes reports/nfl-teasers-2026-09-22.json. No prices or wagers are placed.
"""
# %% setup
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nfl-teasers"
GAMES = RAW / "games.csv"
COMMIT = "62997a79c23f4dbc7d70b0c7cbcff94e0a7e3138"
URL = f"https://raw.githubusercontent.com/nflverse/nfldata/{COMMIT}/data/games.csv"
OUT = ROOT / "reports/nfl-teasers-2026-09-22.json"
TEASE = 6
TRAIN, TEST = (1999, 2014), (2015, 2025)
# Per-leg break-even for a fixed-price teaser: p**k * decimal = 1.
PRICES = {"2-team -110": (2, 1 + 100 / 110), "2-team -120 (DraftKings)": (2, 1 + 100 / 120),
          "2-team -134 (FanDuel, reported high)": (2, 1 + 100 / 134), "3-team +160 (DraftKings)": (3, 2.6)}

if not GAMES.exists():
    RAW.mkdir(parents=True, exist_ok=True)
    GAMES.write_bytes(urlopen(URL, timeout=120).read())
games_sha = hashlib.sha256(GAMES.read_bytes()).hexdigest()

# %% one row per team-side, closing line from that team's view
g = pd.read_csv(GAMES)
g = g[g.spread_line.notna() & g.total_line.notna()].copy()
legs = []
for side in ("home", "away"):
    d = g[["game_id", "season", "week", "game_type", "gameday", "gametime", "spread_line",
           "total_line", "result", "location"]].copy()
    d["side"] = side
    d["line"] = -d.spread_line if side == "home" else d.spread_line  # points the team receives
    d["margin"] = d.result if side == "home" else -d.result
    legs.append(d)
L = pd.concat(legs, ignore_index=True)
L["wong"] = L.line.between(-8.5, -7.5) | L.line.between(1.5, 2.5)
L["dog"] = L.line > 0
L["low_total"] = L.total_line <= 49
done = L[L.result.notna()].copy()
done["outcome"] = np.sign(done.margin + done.line + TEASE)  # 1 win, 0 push, -1 loss
graded = done[done.outcome != 0].copy()
graded["win"] = (graded.outcome == 1).astype(int)


def rate(x):
    n = len(x)
    r = x.win.mean() if n else np.nan
    se = np.sqrt(r * (1 - r) / n) if n else np.nan
    return {"legs": n, "win_rate": round(r, 4), "ci95": [round(r - 1.96 * se, 4), round(r + 1.96 * se, 4)]}


def ev(p):
    return {k: round(p ** n * dec - 1, 4) for k, (n, dec) in PRICES.items()}


breakeven = {k: round(dec ** (-1 / n), 4) for k, (n, dec) in PRICES.items()}
print("Per-leg break-even:", breakeven)

# %% training period only: which filters help Wong legs?
w_tr = graded[graded.wong & graded.season.between(*TRAIN)]
train = {"all": rate(w_tr),
         "total<=49": rate(w_tr[w_tr.low_total]), "total>49": rate(w_tr[~w_tr.low_total]),
         "underdog": rate(w_tr[w_tr.dog]), "favorite": rate(w_tr[~w_tr.dog])}
print("Training 1999-2014 Wong legs:", json.dumps(train, indent=1))
# The total filter separates in training; the dog/favorite split does not, so only the total filter is carried forward.
RULE = lambda x: x.wong & x.low_total

# %% test period 2015-2025, untouched by the filter choice
w_te = graded[graded.season.between(*TEST)]
test = {"wong": rate(w_te[w_te.wong]), "wong_total<=49 (selected rule)": rate(w_te[RULE(w_te)]),
        "diag: wong_dogs": rate(w_te[w_te.wong & w_te.dog]), "diag: wong_favorites": rate(w_te[w_te.wong & ~w_te.dog]),
        "diag: all_other_legs": rate(w_te[~w_te.wong])}
for k, v in test.items():
    v["ev_per_teaser"] = ev(v["win_rate"])
print("Test 2015-2025:", json.dumps(test, indent=1))
post_pub = graded[graded.wong & graded.season.between(2001, 2025)]
print("Wong since publication (2001-2025):", rate(post_pub))
by_season = {int(s): rate(x) for s, x in graded[RULE(graded) & (graded.season >= 2015)].groupby("season")}
print(pd.DataFrame(by_season).T[["legs", "win_rate"]].to_string())

# %% realized teaser record: group qualifying legs within each week in kickoff order; leftovers are not bet
# Both sides of one game can never qualify together (+2 faces -2, -8 faces +8), so groups never share a game.
def teasers(x, k):
    rows = []
    for (season, week), wk in x.sort_values(["gameday", "gametime", "game_id"]).groupby(["season", "week"], sort=False):
        out = wk.outcome.values
        for i in range(0, len(out) - k + 1, k):
            grp = out[i:i + k]
            rows.append({"season": season, "week": week, "won": bool((grp == 1).all()), "push_leg": bool((grp == 0).any())})
    return pd.DataFrame(rows)


sel = done[RULE(done) & done.season.between(*TEST)]
record = {}
for label, (k, dec) in PRICES.items():
    t = teasers(sel, k)
    t = t[~t.push_leg]  # a push reduces the teaser; excluded here (only whole-number lines can push)
    units = np.where(t.won, dec - 1, -1.0)
    curve = np.cumsum(units)
    record[label] = {"teasers": len(t), "won": int(t.won.sum()), "units": round(units.sum(), 2),
                     "roi": round(units.mean(), 4), "max_drawdown_units": round(float(np.max(np.maximum.accumulate(curve) - curve)), 2),
                     "losing_seasons": int((t.assign(u=units).groupby("season").u.sum() < 0).sum())}
print("Realized record 2015-2025:", json.dumps(record, indent=1))

# %% block bootstrap by season-week for the selected rule's per-leg rate and 2-team -120 EV
rng = np.random.default_rng(20260922)
x = graded[RULE(graded) & graded.season.between(*TEST)]
blocks = [b.win.values for _, b in x.groupby(["season", "week"])]
boot = []
for _ in range(5000):
    pick = rng.integers(0, len(blocks), len(blocks))
    w = np.concatenate([blocks[i] for i in pick])
    boot.append(w.mean())
boot = np.array(boot)
bootstrap = {"win_rate_ci95": [round(np.quantile(boot, .025), 4), round(np.quantile(boot, .975), 4)],
             "p_below_breakeven_-120": round(float((boot < breakeven["2-team -120 (DraftKings)"]).mean()), 4),
             "p_below_breakeven_+160_3team": round(float((boot < breakeven["3-team +160 (DraftKings)"]).mean()), 4)}
print("Bootstrap:", bootstrap)

# %% current season to date (graded games only)
ytd = graded[RULE(graded) & (graded.season == 2026)]
current = {"season_2026_to_date": rate(ytd), "open_2026_candidates": int((RULE(L) & (L.season == 2026) & L.result.isna()).sum())}
print(current)

# %% save
OUT.write_text(json.dumps({
    "source": {"url": URL, "sha256": games_sha, "fields": "closing spread_line, total_line, final result"},
    "tease_points": TEASE, "breakeven_per_leg": breakeven, "training_1999_2014": train,
    "test_2015_2025": test, "wong_since_publication_2001_2025": rate(post_pub),
    "selected_rule_by_season": by_season, "realized_record_2015_2025": record,
    "bootstrap_2015_2025": bootstrap, "current": current}, indent=2) + "\n")
print("wrote", OUT.relative_to(ROOT))
