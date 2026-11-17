"""Raw capture of IPL match-winner markets from Kalshi and Polymarket (public read endpoints, no key).

NOT YET RUN: both hosts are outside this cloud environment's network allowlist, so the endpoint paths and
field names below come from the public API documentation and have not been checked against live responses.
Every response is saved verbatim with its fetch time, so the normaliser (prices.py) can be corrected without
re-fetching. Hosts needed: api.elections.kalshi.com, gamma-api.polymarket.com, clob.polymarket.com.

python -m models.ipl.market.collect kalshi|polymarket [--from 2024-03-01] [--to 2026-06-05]
"""
# %% imports
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from models.ipl.config import ROOT

RAW = ROOT / "data" / "raw" / "markets"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
WORDS = ("indian premier league", "ipl")
PAUSE = 0.25  # seconds between requests


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"User-Agent": "research-client", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    time.sleep(PAUSE)
    return url, json.loads(body)


def save(source, name, url, payload):
    d = RAW / source
    d.mkdir(parents=True, exist_ok=True)
    rec = {"fetched_at": datetime.now(timezone.utc).isoformat(), "url": url, "payload": payload}
    (d / f"{name}.json").write_text(json.dumps(rec))
    return payload


def is_ipl(*texts):
    """League name, or IPL as a word or inside a ticker / slug (KXIPLGAME, ipl-mi-csk)."""
    t = " ".join(str(x or "") for x in texts).lower()
    return WORDS[0] in t or re.search(r"(^|[^a-z])(kx)?ipl", t) is not None


def ts(date):
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())


# %% Kalshi: series -> events -> markets -> candlesticks + trades


def kalshi(start, end):
    url, s = get(f"{KALSHI}/series", {"category": "Sports"})
    save("kalshi", "series", url, s)
    series = [x for x in s.get("series", []) if is_ipl(x.get("title"), x.get("ticker"), " ".join(x.get("tags") or []))]
    print("kalshi IPL series:", [(x["ticker"], x.get("title")) for x in series])
    for sr in series:
        st, events, cursor = sr["ticker"], [], None
        while True:
            url, e = get(f"{KALSHI}/events", {"series_ticker": st, "limit": 200, "cursor": cursor,
                                              "with_nested_markets": "true"})
            events += e.get("events", [])
            cursor = e.get("cursor")
            if not cursor:
                break
        save("kalshi", f"events_{st}", f"{KALSHI}/events?series_ticker={st}", events)
        for ev in events:
            for mk in ev.get("markets", []):
                tk = mk["ticker"]
                # one-minute candles cap the range per call, so page by day across the market's life
                o = ts((mk.get("open_time") or f"{start}T00:00:00")[:19])
                c = ts((mk.get("close_time") or f"{end}T00:00:00")[:19])
                candles, a = [], max(o, ts(start))
                while a < min(c, ts(end)) + 1:
                    b = min(a + 86400 - 60, c)
                    url, k = get(f"{KALSHI}/series/{st}/markets/{tk}/candlesticks",
                                 {"start_ts": a, "end_ts": b, "period_interval": 1})
                    candles += k.get("candlesticks", [])
                    a = b + 60
                trades, cursor = [], None
                while True:
                    url, t = get(f"{KALSHI}/markets/trades", {"ticker": tk, "limit": 1000, "cursor": cursor})
                    trades += t.get("trades", [])
                    cursor = t.get("cursor")
                    if not cursor:
                        break
                save("kalshi", f"market_{tk}", f"{KALSHI}/markets/{tk}", {"market": mk, "event": {k: v for k, v in ev.items() if k != "markets"},
                                                                         "candlesticks": candles, "trades": trades})
        print(f"kalshi {st}: {len(events)} events")


# %% Polymarket: gamma events -> markets -> CLOB price history per outcome token


def polymarket(start, end):
    events, seen = [], set()
    for q in ("IPL", "Indian Premier League"):
        page = 1
        while page <= 50:
            url, r = get(f"{GAMMA}/public-search", {"q": q, "limit_per_type": 100, "page": page, "events_status": "all"})
            got = [e for e in r.get("events", []) if e.get("id") not in seen and is_ipl(e.get("title"), e.get("slug"))]
            if not r.get("events"):
                break
            events += got
            seen |= {e.get("id") for e in got}
            page += 1
    save("polymarket", "events", f"{GAMMA}/public-search", events)
    n = 0
    for ev in events:
        for mk in ev.get("markets", []):
            toks = json.loads(mk.get("clobTokenIds") or "[]")
            hist = {}
            for tok in toks:
                url, h = get(f"{CLOB}/prices-history", {"market": tok, "startTs": ts(start), "endTs": ts(end), "fidelity": 1})
                hist[tok] = h.get("history", [])
            save("polymarket", f"market_{mk.get('id')}", f"{GAMMA}/markets/{mk.get('id')}",
                 {"market": mk, "event": {k: v for k, v in ev.items() if k != "markets"}, "history": hist})
            n += 1
    print(f"polymarket: {len(events)} events, {n} markets")


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    {"kalshi": kalshi, "polymarket": polymarket}[a[0]](opt("--from", "2024-03-01"), opt("--to", "2026-06-05"))
