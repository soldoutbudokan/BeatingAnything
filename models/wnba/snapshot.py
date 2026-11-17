# %% Forward capture: what we knew, what we projected and what the market said, stamped before tip
"""
python -m models.wnba.snapshot            capture news + markets now, then freeze forecasts for upcoming games
python -m models.wnba.snapshot capture    capture only
python -m models.wnba.snapshot freeze     freeze only (uses the latest capture)

Past seasons can only be replayed with box scores (models.wnba.process, tier "box"): nobody archived the
injury reports. From here on each run stores, under one UTC timestamp:
  capture   ESPN injuries, transactions, rosters and the next 8 days of the scoreboard; every open Kalshi
            WNBA market (game, spread, total, player points / rebounds / assists / threes) with its book
            top; open Polymarket WNBA events.              -> data/markets/wnba/snapshots/<stamp>.json.gz
  freeze    for each game tipping within 36 h: the lineup projected from box scores alone and from box
            scores + the captured report, the forecast each gives, and the Kalshi quote at that moment.
            Rows are appended and never rewritten.         -> data/markets/wnba/forecast_ledger.csv
Grading later reads the ledger, so a forecast can only use what was on disk before the game.

The freeze step needs a current build (python -m models.wnba.run_all --refresh) for box scores and ratings.
STATUS_P are placeholders: once a season of captures exists, replace them with the measured share of players
at each status who played.
"""
from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from scipy.stats import norm

from models.wnba import kalshi
from models.wnba.common import ESPN, PROC, ROOT

OUT = ROOT / "data" / "markets" / "wnba"
SNAP = OUT / "snapshots"
LEDGER = OUT / "forecast_ledger.csv"
KALSHI_SERIES = ["KXWNBAGAME", "KXWNBASPREAD", "KXWNBATOTAL", "KXWNBAPTS", "KXWNBAREB", "KXWNBAAST", "KXWNBA3PT"]
STATUS_P = {"Out": 0.0, "Doubtful": 0.1, "Questionable": 0.5, "Day-To-Day": 0.7, "Probable": 0.9}
FREEZE_WITHIN_H = 36.0


def curl_json(url):
    r = subprocess.run(["curl", "-sS", "--compressed", "-m", "40", url], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": r.stdout[:200] or r.stderr[:200]}


def scoreboard(start, days):
    """ESPN's scoreboard refuses date ranges, so one call per day."""
    ev, seen = [], set()
    for k in range(days):
        d = curl_json(f"{ESPN}/scoreboard?dates={(start + timedelta(days=k)).strftime('%Y%m%d')}")
        for e in d.get("events", []):
            if e["id"] not in seen:
                seen.add(e["id"])
                ev.append(e)
    return {"events": ev}


def stamp(t):
    return t.strftime("%Y%m%dT%H%M%SZ")


# %% capture
def capture(now=None):
    now = now or datetime.now(timezone.utc)
    teams = curl_json(f"{ESPN}/teams")
    ids = [t["team"]["id"] for t in teams.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])]
    snap = dict(
        captured_at=now.isoformat(),
        espn=dict(injuries=curl_json(f"{ESPN}/injuries"), transactions=curl_json(f"{ESPN}/transactions?limit=100"),
                  scoreboard=scoreboard(now, 8),
                  rosters={i: curl_json(f"{ESPN}/teams/{i}/roster") for i in ids}),
        kalshi={s: kalshi.paged("/markets", {"series_ticker": s, "status": "open"}) for s in KALSHI_SERIES},
        polymarket=curl_json("https://gamma-api.polymarket.com/events?series_id=10105&closed=false&limit=200"))
    SNAP.mkdir(parents=True, exist_ok=True)
    f = SNAP / f"{stamp(now)}.json.gz"
    with gzip.open(f, "wt") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    nk = sum(len(v) for v in snap["kalshi"].values())
    ni = sum(len(t.get("injuries", [])) for t in snap["espn"]["injuries"].get("injuries", []))
    ng = len(snap["espn"]["scoreboard"].get("events", []))
    print(f"snapshot {f.name}: {ni} injury lines, {ng} games on the board, {nk} open Kalshi markets, "
          f"{len(snap['polymarket']) if isinstance(snap['polymarket'], list) else 0} Polymarket events")
    return f


def latest_snapshot(before):
    """Newest capture taken at or before `before` (UTC datetime), or None."""
    fs = sorted(SNAP.glob("*.json.gz")) if SNAP.exists() else []
    fs = [f for f in fs if f.name[:16] <= stamp(before)]
    if not fs:
        return None
    with gzip.open(fs[-1], "rt") as fh:
        return json.load(fh)


# %% the availability report as P(active)
def athlete_id(a):
    for ln in a.get("links", []):
        m = re.search(r"/id/(\d+)", ln.get("href", ""))
        if m:
            return int(m.group(1))
    return int(a["id"]) if str(a.get("id", "")).isdigit() else None


def news_from(snap, team_id):
    """{pid: P(active)} for one team: listed players by status, plus rostered players (0.9 if unlisted) so a
    signing we have never seen play for the team still gets minutes."""
    out = {}
    ros = snap["espn"]["rosters"].get(str(team_id), {})
    for a in ros.get("athletes", []):
        if str(a.get("id", "")).isdigit():
            out[int(a["id"])] = 0.9
    for t in snap["espn"]["injuries"].get("injuries", []):
        if str(t.get("id")) != str(team_id):
            continue
        for i in t.get("injuries", []):
            pid = athlete_id(i.get("athlete", {}))
            if pid:
                out[pid] = STATUS_P.get(i.get("status"), 0.5)
    return out


def news_fn(game, team_id, T):
    """Hook for process.build: the report from the newest capture before T, if it is recent enough to trust."""
    s = latest_snapshot(T.to_pydatetime())
    if s is None or (T.to_pydatetime() - datetime.fromisoformat(s["captured_at"])) > timedelta(hours=36):
        return None
    return news_from(s, team_id)


# %% freeze forecasts for upcoming games
def freeze(now=None):
    """Append a forecast row per upcoming game x tier. `now` can be set to a past time to replay the box tier."""
    from models.wnba import process
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now
    snap = latest_snapshot(now.to_pydatetime())
    live = snap is not None and (now.to_pydatetime() - datetime.fromisoformat(snap["captured_at"])) < timedelta(hours=2)
    board = snap["espn"]["scoreboard"] if live else scoreboard(now.to_pydatetime() - timedelta(days=1), 4)
    if not (PROC / "player_games.parquet").exists():
        raise SystemExit("freeze: no build found; run python -m models.wnba.run_all --refresh first")
    games, pg = process.load()
    games, pg = games[games.tip < now], pg[pg.tip < now]  # nothing from the future, even in a replay
    L = process.Lineups(games, pg)
    prm = json.loads((PROC / "sim_params.json").read_text())
    hca = prm["context"]["hca_pts"]
    total = {p["id"]: p["O"] + p["D"] for p in prm["players"]}
    if not live:  # a replay must not use end-of-season ratings
        season = int(now.year)
        total = [t for tc, t in process.ratings_by_cut([season]) if tc <= process.tau([season], [now.strftime("%Y-%m-%d")], process.season_bounds(pd.read_parquet(PROC / "games.parquet")))[0]][-1]
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    kq = {}
    for m in (snap["kalshi"].get("KXWNBAGAME", []) if live else []):
        kq[m["ticker"]] = m
    rows = []
    for e in board.get("events", []):
        c = e["competitions"][0]
        tip = pd.Timestamp(e["date"])
        hrs = (tip - now).total_seconds() / 3600
        if not (0 < hrs <= FREEZE_WITHIN_H):
            continue
        side = {x["homeAway"]: int(x["team"]["id"]) for x in c["competitors"]}
        g = pd.Series(dict(game_id=int(e["id"]), season=int(now.year), home=side["home"], away=side["away"]))
        for tier in ("box", "news"):
            news = {t: (news_from(snap, t) if (tier == "news" and live) else None) for t in side.values()}
            if tier == "news" and not live:
                continue
            lu = {}
            for t in side.values():
                if t not in L.team_games:
                    lu[t] = None
                    continue
                lu[t], _ = L.project(t, g, now, "box", news[t])
            if lu[side["home"]] is None or lu[side["away"]] is None:
                continue
            mu = (process.net_rating(lu[side["home"]], total) - process.net_rating(lu[side["away"]], total)) * process.POSS / 100
            mu += 0.0 if c.get("neutralSite") else hca
            q = match_quote(kq, side["home"], side["away"], tip)
            rows.append(dict(
                frozen_at=now.isoformat(), game_id=int(e["id"]), tip=tip.isoformat(), hours_to_tip=round(hrs, 2), tier=tier,
                home=side["home"], away=side["away"], pred_margin=round(mu, 3), p_home=round(float(norm.cdf(mu / process.MARGIN_SD)), 4),
                kalshi_ticker=q.get("ticker"), kalshi_bid=kalshi.num(q, "yes_bid_dollars"), kalshi_ask=kalshi.num(q, "yes_ask_dollars"),
                snapshot=stamp(datetime.fromisoformat(snap["captured_at"])) if live else None, code=sha,
                home_lineup=json.dumps({int(k): round(float(v), 1) for k, v in lu[side["home"]].items() if v >= 0.5}),
                away_lineup=json.dumps({int(k): round(float(v), 1) for k, v in lu[side["away"]].items() if v >= 0.5})))
    if rows:
        pd.DataFrame(rows).to_csv(LEDGER, mode="a", header=not LEDGER.exists(), index=False)
    print(f"freeze at {now.isoformat()}: {len(rows)} forecast rows" + ("" if live else " (replay: box tier only, no market quote)"))
    return pd.DataFrame(rows)


def match_quote(markets, home, away, tip):
    """The open Kalshi game-winner market whose YES is the home team of this game (same pairing rule as
    kalshi.market_table: both teams in the rule text, Kalshi's occurrence time ~2.5 h after tip)."""
    name = {v: k for k, v in kalshi.TEAM.items()}
    for m in markets.values():
        rule = m.get("rules_primary") or ""
        if name[home] not in rule or name[away] not in rule or not (m.get("yes_sub_title") or "").startswith(name[home]):
            continue
        occ = pd.to_datetime(m.get("occurrence_datetime") or m.get("expected_expiration_time"), utc=True)
        if pd.notna(occ) and abs((occ - pd.Timedelta(hours=2.5)) - tip) < pd.Timedelta(hours=14):
            return m
    return {}


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or "capture" in a:
        capture()
    if not a or "freeze" in a:
        freeze()
