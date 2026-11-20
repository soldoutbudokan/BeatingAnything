"""Normalise captured markets to one price series per (match, team), and read the price at an information state.

Kalshi prices are dollars (0-1): the mid of bid and ask when both are quoted, else the last trade. Pinnacle and
Betfair Exchange (through OddsPapi) quote decimal odds on each side: backing team 1 costs 1 / odds1 (the ask) and
backing team 2 leaves 1 - 1 / odds2 for team 1 (the bid). The price is their mid and the spread is ask - bid, which
is Pinnacle's margin and, on the exchange, the gap between the two best back prices.
"""
# %% imports
import json
import re
from datetime import timedelta

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.market.collect import RAW, load
from models.ipl.team import SHORT, TEAM_ALIASES

# when each information state closes, relative to the scheduled first ball. The toss is 30 minutes before the
# start and XIs are named at it, so "pre_news" must end well before the toss and "post_toss" after it.
STATE_OFFSET = {"pre_news": timedelta(hours=-3), "post_toss": timedelta(minutes=-10)}
MAX_STALE = timedelta(hours=6)   # a quote older than this at the state time is not a price


ODDSPAPI_SOURCE = {"pinnacle": "pinnacle", "betfair-ex": "betfair"}   # bookmaker slug -> source name
WINNER = "271"                # OddsPapi market: winner including a super over
WINNER_SIDES = ("271", "272")  # its outcomes: participant 1, participant 2

NAMES = {**{n: n for n in SHORT}, **TEAM_ALIASES}   # every spelling -> current franchise name


def team_in(text):
    """Franchises named in a market title or outcome, in order of appearance."""
    t = f" {text} ".lower().replace("?", " ").replace(".", " ")
    hits = {}
    for name, canon in NAMES.items():
        k = t.find(name.lower())
        if k >= 0:
            hits[canon] = min(k, hits.get(canon, k))
    for canon, short in SHORT.items():
        k = t.find(f" {short.lower()} ")
        if k >= 0 and canon not in hits:
            hits[canon] = k
    return sorted(hits, key=hits.get)


def kalshi_start(mk, ev):
    """Scheduled first ball (UTC). 2026 tickers carry the US Eastern start (KXIPLGAME-26MAY291000RRGT; IPL runs in
    daylight time, UTC-4). Earlier tickers do not, and the expected expiration is three to four hours after the
    start, so the estimate is snapped to the two IPL start times: 10:00 and 14:00 UTC (15:30 and 19:30 IST)."""
    m = re.match(r"^[A-Z0-9]+-(\d{2}[A-Z]{3}\d{2})(\d{4})[A-Z]", ev["event_ticker"])
    if m:
        t = pd.to_datetime(m.group(1) + m.group(2), format="%y%b%d%H%M", utc=True) + timedelta(hours=4)
    else:
        t = pd.to_datetime(mk["expected_expiration_time"], utc=True) - timedelta(hours=3, minutes=30)
    return t.normalize() + timedelta(hours=10 if t.hour < 12 else 14)


def back_odds(responses, book, outcome):
    """One outcome's decimal odds over time from OddsPapi historical-odds responses, indexed by ts (UTC). NaN from
    the moment a quote is withdrawn (`active` false) until the next one."""
    rows = []
    for resp in responses:
        o = resp.get("bookmakers", {}).get(book, {}).get("markets", {}).get(WINNER, {}).get("outcomes", {}).get(outcome, {})
        rows += o.get("players", {}).get("0", [])
    if not rows:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    d = pd.DataFrame(rows)
    d["ts"] = pd.to_datetime(d["createdAt"], utc=True, format="ISO8601")
    d["price"] = d["price"].astype(float).where(d["active"].astype(bool) & (d["price"] > 1))
    return d.sort_values("ts", kind="stable").drop_duplicates("ts", keep="last").set_index("ts")["price"]


def two_way(odds1, odds2, start):
    """Team 1's price from the decimal odds on each side (see the module docstring): ts, price, spread at every
    change before `start`. Nothing reads a price after the first ball, and the exchange's in-play ticks are most
    of a capture. The price is NaN while either side has no standing quote, so a withdrawn price is not read."""
    idx = odds1.index.union(odds2.index)
    idx = idx[idx < start]
    ask, bid = 1 / odds1.reindex(idx, method="ffill"), 1 - 1 / odds2.reindex(idx, method="ffill")
    out = pd.DataFrame({"ts": idx, "price": ((ask + bid) / 2).to_numpy(), "spread": (ask - bid).clip(lower=0).to_numpy()})
    return out[out["price"].notna().cummax()].reset_index(drop=True)   # from the first two-sided quote on


def oddspapi_series():
    """Pinnacle and Betfair Exchange, one frame in the load_series layout."""
    frames = []
    for p in sorted((RAW / "oddspapi").glob("market_*.json.gz")):
        rec = load(p)["payload"]
        fx = rec["fixture"]
        sides = [team_in(fx.get("participant1Name") or ""), team_in(fx.get("participant2Name") or "")]
        if not all(len(x) == 1 for x in sides) or sides[0] == sides[1]:
            continue
        teams = [sides[0][0], sides[1][0]]
        start = pd.to_datetime(fx["startTime"], utc=True)
        for book, src in ODDSPAPI_SOURCE.items():
            q = two_way(*(back_odds(rec["odds"].get(book, []), book, o) for o in WINNER_SIDES), start)
            for side, px in ((teams[0], q["price"]), (teams[1], 1 - q["price"])):
                frames.append(pd.DataFrame({"source": src, "market_id": f"{fx['fixtureId']}:{book}", "team": side,
                                            "teams": "|".join(teams), "ts": q["ts"], "price": px, "start": start,
                                            "spread": q["spread"]}))
    return frames


def load_series():
    """Long table: source, market_id, team (the side the price is for), teams, ts (UTC), price (0-1), start (UTC),
    spread (ask - bid where quoted)."""
    rows = []
    f = lambda x: None if x in (None, "") else float(x)
    for p in sorted((RAW / "kalshi").glob("market_*.json")):
        rec = json.loads(p.read_text())["payload"]
        mk, ev = rec["market"], rec["event"]
        teams = team_in(ev.get("title", "") + " " + mk.get("title", ""))
        side = team_in(mk.get("yes_sub_title") or "")
        if not side or len(teams) != 2:
            continue
        start = kalshi_start(mk, ev)
        for c in rec.get("candlesticks", []):
            bid, ask = f((c.get("yes_bid") or {}).get("close")), f((c.get("yes_ask") or {}).get("close"))
            last = f((c.get("price") or {}).get("close"))
            two_sided = bid is not None and ask is not None and 0 < bid < ask < 1
            px = (bid + ask) / 2 if two_sided else last
            if px is not None:
                rows.append(("kalshi", mk["ticker"], side[0], "|".join(teams), pd.to_datetime(c["end_period_ts"], unit="s", utc=True),
                             px, start, ask - bid if two_sided else np.nan))
    for p in sorted((RAW / "polymarket").glob("market_*.json")):
        rec = json.loads(p.read_text())["payload"]
        mk, ev = rec["market"], rec["event"]
        outs, toks = json.loads(mk.get("outcomes") or "[]"), json.loads(mk.get("clobTokenIds") or "[]")
        sides = [team_in(o) for o in outs]
        if len(outs) != 2 or not all(len(x) == 1 for x in sides) or sides[0] == sides[1]:
            continue   # props (Yes / No) and non-IPL fixtures
        teams = [sides[0][0], sides[1][0]]
        start = pd.to_datetime(mk["gameStartTime"], utc=True)
        for side, tok in zip(teams, toks):
            for h in rec.get("history", {}).get(tok, []):
                rows.append(("polymarket", str(mk["id"]), side, "|".join(teams), pd.to_datetime(h["t"], unit="s", utc=True),
                             float(h["p"]), start, np.nan))
    cols = ["source", "market_id", "team", "teams", "ts", "price", "start", "spread"]
    frames = [x for x in [pd.DataFrame(rows, columns=cols)] + oddspapi_series() if len(x)]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)


def price_at(series, when, max_stale=MAX_STALE):
    """Last price at or before `when` (series: ts-sorted frame with ts, price); NaN if none, too old or withdrawn."""
    s = series[series["ts"] <= when]
    if not len(s) or when - s["ts"].iloc[-1] > max_stale:
        return np.nan
    return float(s["price"].iloc[-1])


def join(process, series):
    """Process-backtest rows with market_p_team1, market_source and market_spread: one row per source that has a
    usable quote, and a single row with them blank when none has. A market matches on the two franchises and a
    start within a day of the match date; the price is read at the row's information state."""
    process = process.reset_index(drop=True)
    cols = ["market_p_team1", "market_source", "market_spread"]
    quotes = []
    if len(series):
        series = series.dropna(subset=["start"]).sort_values("ts")
        by_team = dict(tuple(series.groupby("team")))
        for i, r in process.iterrows():
            c = by_team.get(r.team1)
            if c is None:
                continue
            c = c[c["teams"].str.contains(r.team2, regex=False)
                  & ((c["start"].dt.tz_localize(None) - r.date).abs() <= timedelta(days=1, hours=6))]
            for src, g in c.groupby("source"):
                when = g["start"].iloc[0] + STATE_OFFSET[r.state]
                px = price_at(g, when)
                if not np.isnan(px):
                    quotes.append((i, px, src, g[g["ts"] <= when]["spread"].iloc[-1]))
    q = pd.DataFrame(quotes, columns=["_row"] + cols).astype({"market_p_team1": float, "market_spread": float})
    out = process.merge(q, how="left", left_index=True, right_on="_row").drop(columns="_row").reset_index(drop=True)
    out["market_source"] = out["market_source"].astype(object).where(out["market_source"].notna(), None)
    return out
