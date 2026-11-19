"""Raw capture of IPL match-winner markets from Kalshi and Polymarket (public read endpoints, no key).

Every response is saved verbatim with its fetch time under data/raw/markets/<source>/, so the normaliser
(prices.py) can change without re-fetching. Checked against live responses on 2026-11-19:
  Kalshi      series KXIPLGAME, 75 events from 2025-04-29 (all of IPL 2026). Settled markets and their
              one-minute candles (bid, ask, last) live under /historical/.
  Polymarket  tag `ipl`, 89 closed events with a game start time, all IPL 2025; minute price history per
              outcome token from the CLOB.

python -m models.ipl.market.collect kalshi|polymarket
"""
# %% imports
import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from models.ipl.config import ROOT
from models.ipl.team import SHORT, TEAM_ALIASES

RAW = ROOT / "data" / "raw" / "markets"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
KALSHI_SERIES = ("KXIPLGAME",)   # also listed: KXIPLTOTAL, KXIPLTEAMTOTAL, KXIPLFIRST6, KXIPLSIX, KXIPLFOUR
FRANCHISES = set(SHORT) | set(TEAM_ALIASES)
PAUSE = 0.3                      # seconds between requests
CANDLE_SPAN = 2 * 86400          # seconds of one-minute candles per request


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"User-Agent": "research-client", "Accept": "application/json",
                                               "Accept-Encoding": "gzip"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            time.sleep(PAUSE)
            return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            time.sleep(2.0 * (attempt + 1))   # rate limited or a server error: back off and retry
    raise RuntimeError(f"gave up on {url}")


def save(source, name, url, payload):
    d = RAW / source
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "url": url,
                                                "payload": payload}))


def epoch(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00").replace(" ", "T").replace("+00", "+00:00")
                                      .replace("+00:00:00", "+00:00")).timestamp())


def paged(url, params, key):
    out, cursor = [], None
    while True:
        r = get(url, dict(params, cursor=cursor))
        out += r.get(key, [])
        cursor = r.get("cursor")
        if not cursor or not r.get(key):
            return out


# %% Kalshi: events -> markets (historical first, live for unsettled) -> one-minute candles


def kalshi(refresh=False):
    for st in KALSHI_SERIES:
        events = paged(f"{KALSHI}/events", {"series_ticker": st, "limit": 200}, "events")
        save("kalshi", f"events_{st}", f"{KALSHI}/events?series_ticker={st}", events)
        n = 0
        for ev in events:
            et = ev["event_ticker"]
            hist = paged(f"{KALSHI}/historical/markets", {"event_ticker": et, "limit": 200}, "markets")
            live = [] if hist else paged(f"{KALSHI}/markets", {"event_ticker": et, "limit": 200}, "markets")
            for mk in hist or live:
                tk = mk["ticker"]
                if (RAW / "kalshi" / f"market_{tk}.json").exists() and not refresh and hist:
                    continue   # settled and already captured
                base = f"{KALSHI}/historical/markets/{tk}/candlesticks" if hist else f"{KALSHI}/series/{st}/markets/{tk}/candlesticks"
                a, end = epoch(mk["open_time"]), min(epoch(mk["close_time"]), int(time.time()))
                candles = []
                while a < end:
                    b = min(a + CANDLE_SPAN, end)
                    candles += get(base, {"start_ts": a, "end_ts": b, "period_interval": 1}).get("candlesticks", [])
                    a = b + 60
                save("kalshi", f"market_{tk}", base, {"market": mk, "event": ev, "settled": bool(hist), "candlesticks": candles})
                n += 1
        print(f"kalshi {st}: {len(events)} events, {n} markets captured")


# %% Polymarket: tagged events -> markets -> CLOB minute price history per outcome token


def polymarket(refresh=False):
    events, seen = [], set()
    for tag in ("ipl", "cricket"):
        for closed in ("true", "false"):
            off = 0
            while True:
                try:
                    r = get(f"{GAMMA}/events", {"tag_slug": tag, "closed": closed, "limit": 100, "offset": off})
                except urllib.error.HTTPError:   # 422 once the offset passes the API's paging limit
                    break
                if not isinstance(r, list) or not r:
                    break
                events += [e for e in r if e["id"] not in seen]
                seen |= {e["id"] for e in r}
                off += 100
    save("polymarket", "events", f"{GAMMA}/events?tag_slug=ipl|cricket", events)
    n = 0
    for ev in events:
        for mk in ev.get("markets", []):
            if not mk.get("gameStartTime") or not mk.get("clobTokenIds"):
                continue   # season-long and prop markets without a fixture time
            title = f" {ev.get('title', '')} ".lower()
            if sum(n.lower() in title for n in FRANCHISES) < 2:
                continue   # the cricket tag covers every league: keep fixtures between two IPL franchises
            path = RAW / "polymarket" / f"market_{mk['id']}.json"
            if path.exists() and not refresh and mk.get("closed"):
                continue
            start = epoch(mk["gameStartTime"])
            hist = {}
            for tok in json.loads(mk["clobTokenIds"]):
                # the two days before the first ball to six hours after; fidelity is in minutes
                h = get(f"{CLOB}/prices-history", {"market": tok, "startTs": start - 2 * 86400, "endTs": start + 6 * 3600,
                                                   "fidelity": 1})
                hist[tok] = h.get("history", [])
            save("polymarket", f"market_{mk['id']}", f"{GAMMA}/markets/{mk['id']}",
                 {"market": mk, "event": {k: v for k, v in ev.items() if k != "markets"}, "history": hist})
            n += 1
    print(f"polymarket: {len(events)} events, {n} markets captured")


if __name__ == "__main__":
    {"kalshi": kalshi, "polymarket": polymarket}[sys.argv[1]](refresh="--refresh" in sys.argv)
