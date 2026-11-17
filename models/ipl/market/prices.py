"""Normalise captured markets to one price series per (match, team), and read the price at an information state.

Field names follow collect.py's caveat: unverified until the first live capture.
"""
# %% imports
import json
from datetime import timedelta

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.market.collect import RAW
from models.ipl.team import SHORT, canon_team

# when each information state closes, relative to the scheduled first ball. The toss is 30 minutes before the
# start and XIs are named at it, so "pre_news" must end well before the toss and "post_toss" after it.
STATE_OFFSET = {"pre_news": timedelta(hours=-3), "post_toss": timedelta(minutes=-10)}
MAX_STALE = timedelta(hours=6)   # a quote older than this at the state time is not a price


def team_in(text):
    """Franchises named in a market title, in order of appearance."""
    t = f" {text} ".lower()
    hits = [(t.find(n.lower()), n) for n in SHORT if n.lower() in t]
    hits += [(t.find(f" {s.lower()} "), n) for n, s in SHORT.items() if f" {s.lower()} " in t and n not in [h[1] for h in hits]]
    return [n for _, n in sorted(hits)]


def load_series():
    """Long table: source, market_id, team (the side the price is for), ts (UTC), price (0-1), start (UTC or NaT)."""
    rows = []
    for p in sorted((RAW / "kalshi").glob("market_*.json")):
        rec = json.loads(p.read_text())["payload"]
        mk, ev = rec["market"], rec["event"]
        teams = team_in(ev.get("title", "") + " " + mk.get("title", ""))
        side = team_in(mk.get("yes_sub_title") or mk.get("subtitle") or "")
        if not side:
            continue
        start = pd.to_datetime(mk.get("expected_expiration_time") or mk.get("close_time"), utc=True)
        for c in rec.get("candlesticks", []):
            bid, ask = (c.get("yes_bid") or {}).get("close"), (c.get("yes_ask") or {}).get("close")
            last = (c.get("price") or {}).get("close")
            px = (bid + ask) / 2 if bid is not None and ask is not None and ask > bid > 0 else last
            if px is not None:
                rows.append(("kalshi", mk["ticker"], side[0], "|".join(teams), pd.to_datetime(c["end_period_ts"], unit="s", utc=True),
                             px / 100.0, start, None if bid is None or ask is None else (ask - bid) / 100.0))
    for p in sorted((RAW / "polymarket").glob("market_*.json")):
        rec = json.loads(p.read_text())["payload"]
        mk, ev = rec["market"], rec["event"]
        outs, toks = json.loads(mk.get("outcomes") or "[]"), json.loads(mk.get("clobTokenIds") or "[]")
        teams = team_in(ev.get("title", "") + " " + mk.get("question", ""))
        start = pd.to_datetime(mk.get("gameStartTime") or ev.get("startTime"), utc=True, errors="coerce")
        for o, tok in zip(outs, toks):
            side = team_in(o)
            if not side:
                continue
            for h in rec.get("history", {}).get(tok, []):
                rows.append(("polymarket", str(mk.get("id")), side[0], "|".join(teams), pd.to_datetime(h["t"], unit="s", utc=True),
                             float(h["p"]), start, None))
    return pd.DataFrame(rows, columns=["source", "market_id", "team", "teams", "ts", "price", "start", "spread"])


def price_at(series, when, max_stale=MAX_STALE):
    """Last price at or before `when` (series: ts-sorted frame with ts, price); NaN if none or too old."""
    s = series[series["ts"] <= when]
    if not len(s) or when - s["ts"].iloc[-1] > max_stale:
        return np.nan
    return float(s["price"].iloc[-1])


def join(process, series):
    """Add market_p_team1 (and its source) to process-backtest rows: match on the two franchises and a market
    start within a day of the match date; the price is read at the row's information state."""
    out = process.copy()
    out["market_p_team1"], out["market_source"] = np.nan, None
    if not len(series):
        return out
    series = series.dropna(subset=["start"]).sort_values("ts")
    for i, r in out.iterrows():
        c = series[(series["team"] == r.team1) & series["teams"].str.contains(r.team2, regex=False)
                   & ((series["start"].dt.tz_localize(None) - r.date).abs() <= timedelta(days=1, hours=6))]
        for src, g in c.groupby("source"):  # first source with a usable quote
            when = g["start"].iloc[0] + STATE_OFFSET[r.state]
            px = price_at(g, when)
            if not np.isnan(px):
                out.loc[i, ["market_p_team1", "market_source"]] = px, src
                break
    return out


if __name__ == "__main__":
    from models.ipl.process import summary
    s = load_series()
    print(f"price rows={len(s):,} markets={s['market_id'].nunique() if len(s) else 0}")
    files = sorted(PROC.glob("process_*.parquet"))
    if files and len(s):
        d = join(pd.concat([pd.read_parquet(f) for f in files]), s)
        m = d.dropna(subset=["market_p_team1"])
        print(f"matches with a market price: {m['match_id'].nunique()} of {d['match_id'].nunique()}")
        if len(m):
            print(summary(m, ref="market_p_team1").round(4).to_string(index=False))
