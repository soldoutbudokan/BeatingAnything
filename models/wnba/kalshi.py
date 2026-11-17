# %% Kalshi WNBA markets: listings, game matching and pre-game quotes at fixed horizons
"""
python -m models.wnba.kalshi [ml] [spread] [total] [--refresh]

Public market data only (no key). Kalshi keeps recent markets under /markets and older ones under
/historical/markets; both are read. Game-winner markets go back to July 2025.

For every market matched to a game in games.parquet, quotes are read from candlesticks at fixed horizons
before the ESPN tip time (Kalshi's own close time is the end of the game, so it cannot be used as "close"):
    24h, 6h, 1h   last hourly candle ending at or before tip - h
    10m           last one-minute candle ending at or before tip - 10 min (game-winner markets only)
    tip           last candle ending at or before tip
Each quote keeps the candle's own timestamp, so its age is known. A candle exists only when the book or the
last price changed, so a quote can be older than its horizon; `age_min` says by how much.

Outputs (committed, small): data/markets/wnba/kalshi_markets.csv.gz, kalshi_quotes.csv.gz
Raw responses are cached under data/raw/wnba/kalshi (not committed).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from models.wnba.common import PROC, RAW, ROOT

API = "https://api.elections.kalshi.com/trade-api/v2"
RAWK = RAW / "kalshi"
OUT = ROOT / "data" / "markets" / "wnba"
SERIES = {"ml": "KXWNBAGAME", "spread": "KXWNBASPREAD", "total": "KXWNBATOTAL"}
HORIZONS_H = {"24h": 24.0, "6h": 6.0, "1h": 1.0, "tip": 0.0}
PAUSE = 0.12  # seconds between requests (well under the public read limit)

# Kalshi team label -> ESPN team id
TEAM = {"Atlanta": 20, "Chicago": 19, "Connecticut": 18, "Dallas": 3, "Golden State": 129689, "Indiana": 5,
        "Las Vegas": 17, "Los Angeles": 6, "Minnesota": 8, "New York": 9, "Phoenix": 11, "Portland": 132052,
        "Seattle": 14, "Toronto": 131935, "Washington": 16}


# %% http
def get(path, params=None, tries=7):
    q = "&".join(f"{k}={v}" for k, v in (params or {}).items() if v not in (None, ""))
    url = f"{API}{path}" + (f"?{q}" if q else "")
    wait = 1.0
    for _ in range(tries):
        r = subprocess.run(["curl", "-sS", "-m", "40", "-w", "\n%{http_code}", url], capture_output=True, text=True)
        body, _, code = r.stdout.rpartition("\n")
        time.sleep(PAUSE)
        if code == "200":
            return json.loads(body)
        if code == "404":
            return None
        time.sleep(wait)  # 429 or a transient failure
        wait = min(wait * 2, 30)
    raise RuntimeError(f"kalshi: {url} failed ({code})")


def paged(path, params, key="markets"):
    out, cursor = [], None
    while True:
        d = get(path, dict(params, cursor=cursor, limit=1000)) or {}
        out += d.get(key, [])
        cursor = d.get("cursor")
        if not cursor or not d.get(key):
            return out


# %% listings
def num(m, *names):
    for n in names:
        v = m.get(n)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return np.nan


def list_markets(kind, refresh=False):
    RAWK.mkdir(parents=True, exist_ok=True)
    f = RAWK / f"markets_{kind}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    s = SERIES[kind]
    old = paged("/historical/markets", {"series_ticker": s})
    new = paged("/markets", {"series_ticker": s})
    for m in old:
        m["tier"] = "historical"
    for m in new:
        m["tier"] = "live"
    seen, out = set(), []
    for m in new + old:
        if m["ticker"] not in seen:
            seen.add(m["ticker"])
            out.append(m)
    f.write_text(json.dumps(out))
    return out


def market_table(kind, refresh=False):
    """One row per market with the game it belongs to and what YES means."""
    ms = list_markets(kind, refresh)
    g = pd.read_parquet(PROC / "games.parquet")[["game_id", "dt", "home", "away", "home_pts", "away_pts", "season"]].reset_index(drop=True)
    g["tip"] = pd.to_datetime(g.dt, utc=True)
    rows = []
    for m in ms:
        title = m.get("title") or ""
        sub = m.get("yes_sub_title") or ""
        rule = m.get("rules_primary") or ""
        # the two teams: from the rule text "... in the A vs B women's Pro Basketball game ..."
        pair = [t for t in TEAM if f"{t} vs" in rule or f"vs {t}" in rule]
        if len(pair) != 2:
            continue
        ids = {TEAM[p] for p in pair}
        occ = pd.to_datetime(m.get("occurrence_datetime") or m.get("expected_expiration_time") or m.get("close_time"), utc=True)
        c = g[g.home.isin(ids) & g.away.isin(ids)]
        if c.empty or pd.isna(occ):
            continue
        # Kalshi's occurrence time is about the end of the game: tip is ~2.5 h earlier
        d = (c.tip - (occ - pd.Timedelta(hours=2.5))).abs()
        j = d.idxmin()
        if d[j] > pd.Timedelta(hours=14):
            continue
        gm = c.loc[j]
        yes_team = next((TEAM[t] for t in sorted(TEAM, key=len, reverse=True) if sub.startswith(t)), None)
        rows.append(dict(
            ticker=m["ticker"], event=m.get("event_ticker"), kind=kind, tier=m["tier"], game_id=int(gm.game_id), season=int(gm.season),
            tip=gm.tip, yes_team=yes_team, yes_is_home=(yes_team == gm.home) if yes_team else None,
            strike=num(m, "floor_strike"), title=title, result=m.get("result"), volume=num(m, "volume_fp", "volume"),
            open_time=m.get("open_time"), close_time=m.get("close_time")))
    return pd.DataFrame(rows)


# %% candlesticks -> quotes
def norm_candles(cs):
    rows = []
    for c in cs or []:
        p, b, a = c.get("price") or {}, c.get("yes_bid") or {}, c.get("yes_ask") or {}
        rows.append((c["end_period_ts"], num(b, "close_dollars", "close"), num(a, "close_dollars", "close"),
                     num(p, "close_dollars", "close"), num(p, "previous_dollars", "previous"),
                     num(c, "volume_fp", "volume"), num(c, "open_interest_fp", "open_interest")))
    return pd.DataFrame(rows, columns=["ts", "bid", "ask", "last", "prev", "vol", "oi"]).sort_values("ts")


def candles(row, interval, start, end):
    """Cached candlesticks for one market between two epoch seconds."""
    d = RAWK / "candles"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{row.ticker}_{interval}.json"
    if f.exists():
        return json.loads(f.read_text())
    p = dict(start_ts=int(start), end_ts=int(end), period_interval=interval)
    if row.tier == "historical":
        r = get(f"/historical/markets/{row.ticker}/candlesticks", p)
    else:
        r = get(f"/series/{SERIES[row.kind]}/markets/{row.ticker}/candlesticks", p)
        if r is None:  # moved to the historical tier since the listing was cached
            r = get(f"/historical/markets/{row.ticker}/candlesticks", p)
    cs = (r or {}).get("candlesticks", [])
    f.write_text(json.dumps(cs))
    return cs


def quote_at(c, t):
    """Last candle ending at or before epoch t. A 0/1 book side means no resting order."""
    c = c[c.ts <= t]
    if c.empty:
        return None
    r = c.iloc[-1]
    bid = r.bid if 0 < r.bid < 1 else np.nan
    ask = r.ask if 0 < r.ask < 1 else np.nan
    last = r["last"] if np.isfinite(r["last"]) else r.prev
    return dict(ts=int(r.ts), bid=bid, ask=ask, last=last, cum_vol=float(c.vol.sum()), oi=r.oi)


def quotes_for(row):
    tip = int(row.tip.timestamp())
    out = []
    hourly = norm_candles(candles(row, 60, tip - 49 * 3600, tip))
    for h, hrs in HORIZONS_H.items():
        q = quote_at(hourly, tip - hrs * 3600)
        if q:
            out.append(dict(q, horizon=h))
    if row.kind == "ml":
        minute = norm_candles(candles(row, 1, tip - 90 * 60, tip))
        for h, mins in (("10m", 10), ("tip", 0)):
            q = quote_at(minute, tip - mins * 60)
            if q:
                out = [o for o in out if o["horizon"] != h] + [dict(q, horizon=h)]
    for o in out:
        o.update(ticker=row.ticker, age_min=(tip - HORIZONS_H.get(o["horizon"], 1 / 6) * 3600 - o["ts"]) / 60)
    return out


# %% main
def main(kinds=("ml",), refresh=False, seasons=None):
    OUT.mkdir(parents=True, exist_ok=True)
    mf, qf = OUT / "kalshi_markets.csv.gz", OUT / "kalshi_quotes.csv.gz"
    M = pd.read_csv(mf, parse_dates=["tip"]) if mf.exists() else pd.DataFrame()
    Q = pd.read_csv(qf) if qf.exists() else pd.DataFrame()
    for kind in kinds:
        T = market_table(kind, refresh)
        if seasons:
            T = T[T.season.isin(seasons)]
        if kind == "ml":
            T = T[T.yes_is_home == True]  # noqa: E712  one book per game: YES = home team wins
        rows, t0 = [], time.time()
        for i, r in enumerate(T.itertuples()):
            rows += quotes_for(r)
            if i and i % 500 == 0:
                print(f"  {kind}: {i}/{len(T)} markets, {time.time() - t0:.0f}s", flush=True)
        q = pd.DataFrame(rows)
        M = pd.concat([M[M.kind != kind] if len(M) else M, T], ignore_index=True)
        if len(Q) and len(q):
            Q = Q[~Q.ticker.isin(T.ticker)]
        Q = pd.concat([Q, q], ignore_index=True)
        print(f"kalshi {kind}: {len(T)} markets on {T.game_id.nunique()} games, {len(q)} quotes")
        M.to_csv(mf, index=False)
        Q.round(4).to_csv(qf, index=False)


if __name__ == "__main__":
    a = sys.argv[1:]
    ks = tuple(k for k in a if k in SERIES) or ("ml",)
    ss = [int(x) for x in a if x.isdigit()]
    main(ks, refresh="--refresh" in a, seasons=ss or None)
