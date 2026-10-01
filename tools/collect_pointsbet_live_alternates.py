#!/usr/bin/env python3
"""Live NFL alternate-line monitor: PointsBet Ontario against Pinnacle and FanDuel Ontario.

One cycle pulls every pregame NFL event from the three public endpoints, normalises full-game spreads
and totals to team-view rows, and records every pair where 1/PointsBet + 1/other(opposite side) < 1,
together with PointsBet's own priceLastUpdated age. Snapshots and arb rows are appended as JSON lines
under data/live/pointsbet-alt-monitor/. Read-only: it never logs in, places, or touches a betslip.

Ontario regions must run from a Canadian residential connection with curl_cffi (browser TLS profile).
The au/nj regions answer plain clients from cloud addresses and were verified against Ontario on 2026-09-30:
FanDuel NJ vs ON 99.3% identical prices on 1,666 rungs; PointsBet AU vs ON identical rungs and rung ages,
prices identical on 53% of rungs and within 0.3–0.6% on average (max ~3%) because of different price-point rounding.

python tools/collect_pointsbet_live_alternates.py            # one cycle
python tools/collect_pointsbet_live_alternates.py --loop 5   # every 5 minutes until interrupted
PB_REGION=au FD_REGION=nj python tools/collect_pointsbet_live_alternates.py --threshold 0.98 --state data/live/pointsbet-alt-monitor/state.json --no-snapshot
    # cloud-safe screen with NEW_GAPS output: same PointsBet engine,
    # but Australia rounds to a decimal price ladder while Ontario uses American price points, so core rungs differ by
    # up to ~3%; confirm any flagged pair on the Ontario board before staking.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import os

try:  # Ontario hosts need a browser TLS profile; Australia / New Jersey / Pinnacle answer plain HTTP clients
    from curl_cffi import requests as _cffi
    HAVE_CFFI = True
except ImportError:  # cloud sandboxes without curl_cffi run the au/nj regions only, on the standard library
    import urllib.request
    HAVE_CFFI = False

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/live/pointsbet-alt-monitor"
PB_REGION = os.environ.get("PB_REGION", "on")  # on = PointsBet Ontario (the bettable board); au = PointsBet Australia, same engine, reachable from the cloud
FD_REGION = os.environ.get("FD_REGION", "on")  # on = FanDuel Ontario; nj = FanDuel New Jersey, 99% identical alternates, reachable from the cloud
PB_CFG = {"on": ("https://api.on.pointsbet.com/api", {"Accept": "application/json", "Origin": "https://on.pointsbet.com", "Referer": "https://on.pointsbet.com/"}, "6"),
          "au": ("https://api.au.pointsbet.com/api", {"Accept": "application/json"}, "11444")}
FD_CFG = {"on": ("https://sbapi.on.sportsbook.fanduel.ca/api", {"Accept": "application/json", "Origin": "https://sportsbook.fanduel.ca", "Referer": "https://sportsbook.fanduel.ca/"}),
          "nj": ("https://sbapi.nj.sportsbook.fanduel.com/api", {"Accept": "application/json", "Origin": "https://sportsbook.fanduel.com", "Referer": "https://sportsbook.fanduel.com/"})}
PB, PB_H, PB_NFL_COMPETITION = PB_CFG[PB_REGION]
FD, FD_H = FD_CFG[FD_REGION]
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_H = {"Accept": "application/json", "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"}  # public key embedded in Pinnacle's web client
FD_AK = "FhMFpcPWXMeyZxOx"  # public key embedded in FanDuel's web client
if PB_REGION == "on" and not HAVE_CFFI:
    sys.exit("PB_REGION=on needs curl_cffi (pip install curl_cffi); set PB_REGION=au FD_REGION=nj for a plain-client run")
PIN_NFL_LEAGUE = 889
ARB_NEAR = 1.01


def now():
    return datetime.now(timezone.utc)


def get(url, headers, tries=3):
    last = None
    for i in range(tries):
        try:
            if HAVE_CFFI:
                r = _cffi.get(url, headers=headers, impersonate="chrome", timeout=25)
                if r.status_code == 200:
                    return r.json()
                status = r.status_code
            else:
                req = urllib.request.Request(url, headers={**headers, "Accept-Encoding": "identity", "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"})
                try:
                    with urllib.request.urlopen(req, timeout=25) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    status = e.code
            last = f"HTTP {status}"
            if status == 429:
                time.sleep(3 * (i + 1))
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(1)
    raise RuntimeError(f"{url}: {last}")


def ts(s):
    if not s:
        return None
    s = s.replace("Z", "")
    if "." in s:
        a, b = s.split(".")
        s = f"{a}.{b[:6]}"
    return datetime.fromisoformat(s + "+00:00")


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)


# ---------------- PointsBet Ontario ----------------
def pointsbet(t0):
    ev = get(f"{PB}/v2/competitions/{PB_NFL_COMPETITION}/events/featured?includeLive=false&page=1", PB_H)
    rows, errors = [], []
    for e in ev["events"]:
        try:
            d = get(f"{PB}/mes/v3/events/{e['key']}", PB_H)
        except RuntimeError as err:
            errors.append(str(err))
            continue
        if d.get("isLive"):
            continue
        home, away = d["homeTeam"], d["awayTeam"]
        for m in d["fixedOddsMarkets"]:
            nm = m.get("eventName", "").strip()
            kind = {"Moneyline": "moneyline", "Point Spread": "spread", "Pick Your Own Line": "spread", "Total": "total", "Alternate Totals": "total"}.get(nm)
            if not kind:
                continue
            for o in m["outcomes"]:
                if o["isHidden"] or not o["isOpenForBetting"]:
                    continue
                upd = ts(o.get("priceLastUpdated"))
                row = dict(book=f"pointsbet_{PB_REGION}", home=home, away=away, start=d["startsAt"], kind=kind, price=float(o["price"]), main=(nm in ("Point Spread", "Total", "Moneyline")),
                           updated=upd.isoformat() if upd else None, age_min=round((t0 - upd).total_seconds() / 60, 1) if upd else None, event=d["key"])
                if kind == "spread":
                    row.update(team=home if o["side"] == "Home" else away, line=float(o["points"]))
                elif kind == "total":
                    row.update(team="Over" if o["name"].startswith("Over") else "Under", line=float(o["points"]))
                else:
                    row.update(team=home if o["side"] == "Home" else away, line=0.0)
                rows.append(row)
        time.sleep(0.3)
    return rows, errors


# ---------------- Pinnacle guest ----------------
def pinnacle(t0):
    mu = get(f"{PIN}/leagues/{PIN_NFL_LEAGUE}/matchups", PIN_H)
    mk = get(f"{PIN}/leagues/{PIN_NFL_LEAGUE}/markets/straight", PIN_H)
    games = {}
    for m in mu:
        if m.get("type") != "matchup" or m.get("parentId"):
            continue
        p = {x["alignment"]: x["name"] for x in m["participants"]}
        if "home" in p and "away" in p:
            games[m["id"]] = dict(home=p["home"], away=p["away"], start=m["startTime"], live=bool(m.get("isLive")))
    rows = []
    for m in mk:
        g = games.get(m["matchupId"])
        if not g or g["live"] or m.get("period") != 0 or m.get("status") != "open" or m["type"] not in ("spread", "total", "moneyline"):
            continue
        limit = next((l["amount"] for l in m.get("limits", []) if l["type"] == "maxRiskStake"), None)
        for pr in m["prices"]:
            row = dict(book="pinnacle", home=g["home"], away=g["away"], start=g["start"], kind=m["type"], price=round(american_to_decimal(pr["price"]), 4), main=not m.get("isAlternate", False),
                       updated=None, age_min=None, limit=limit)
            if m["type"] == "spread":
                row.update(team=g["home"] if pr["designation"] == "home" else g["away"], line=float(pr["points"]))
            elif m["type"] == "total":
                row.update(team="Over" if pr["designation"] == "over" else "Under", line=float(pr["points"]))
            else:
                row.update(team=g["home"] if pr["designation"] == "home" else g["away"], line=0.0)
            rows.append(row)
    return rows, []


# ---------------- FanDuel Ontario ----------------
LINE_RE = re.compile(r"\(([+-]?\d+(?:\.\d)?)\)\s*$")


def fanduel(t0):
    page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId=nfl&pbHorizontal=false&_ak={FD_AK}&timezone=America%2FToronto", FD_H)
    events = {k: v for k, v in page["attachments"]["events"].items() if " @ " in v.get("name", "")}
    horizon = (t0 + timedelta(days=8)).isoformat()  # the page also lists later weeks
    events = {k: v for k, v in events.items() if (v.get("openDate") or "") <= horizon}
    rows, errors = [], []
    for eid, e in events.items():
        away, home = [x.strip() for x in e["name"].split(" @ ")]
        if e.get("inPlay"):
            continue
        try:
            d = get(f"{FD}/event-page?_ak={FD_AK}&eventId={eid}&tab=popular", FD_H)
        except RuntimeError as err:
            errors.append(str(err))
            continue
        for m in d["attachments"]["markets"].values():
            mt = m.get("marketType") or ""
            if m.get("marketStatus") != "OPEN":
                continue
            kind = {"MATCH_HANDICAP_(2-WAY)": "spread", "ALTERNATE_HANDICAP": "spread", "TOTAL_POINTS_(OVER/UNDER)": "total", "ALTERNATE_TOTAL_POINTS": "total", "MONEY_LINE": "moneyline"}.get(mt)
            if not kind:
                continue
            for rn in m.get("runners", []):
                if rn.get("runnerStatus") != "ACTIVE":
                    continue
                price = rn.get("winRunnerOdds", {}).get("trueOdds", {}).get("decimalOdds", {}).get("decimalOdds")
                if not price:
                    continue
                name = rn.get("runnerName", "")
                mline = LINE_RE.search(name)
                line = float(mline.group(1)) if mline else float(rn.get("handicap") or 0)
                team = LINE_RE.sub("", name).strip()
                if kind == "total":
                    team = "Over" if team.lower().startswith("over") else "Under"
                elif kind == "moneyline":
                    line = 0.0
                rows.append(dict(book=f"fanduel_{FD_REGION}", home=home, away=away, start=e.get("openDate"), kind=kind, price=round(float(price), 4), main=not mt.startswith("ALTERNATE"),
                                 updated=None, age_min=None, team=team, line=line, event=eid))
        time.sleep(0.3)
    return rows, errors


# ---------------- pairing ----------------
def opposite(row):
    if row["kind"] == "total":
        return ("Under" if row["team"] == "Over" else "Over", row["line"])
    other = row["away"] if row["team"] == row["home"] else row["home"]
    return (other, -row["line"])


def pairs(pb_rows, other_rows):
    idx = {}
    for r in other_rows:
        if r["kind"] in ("spread", "total"):
            idx.setdefault((r["home"], r["away"], r["kind"], r["team"], r["line"]), []).append(r)
    out = []
    for r in pb_rows:
        if r["kind"] not in ("spread", "total"):
            continue
        team, line = opposite(r)
        for o in idx.get((r["home"], r["away"], r["kind"], team, line), []):
            s = 1 / r["price"] + 1 / o["price"]
            out.append(dict(home=r["home"], away=r["away"], kind=r["kind"], pb_leg=f"{r['team']} {r['line']:+g}" if r["kind"] == "spread" else f"{r['team']} {r['line']}",
                            pb_price=r["price"], pb_main=r["main"], pb_age_min=r["age_min"], other_book=o["book"], other_leg=f"{team} {line:+g}" if r["kind"] == "spread" else f"{team} {line}",
                            other_price=o["price"], other_limit=o.get("limit"), inv_sum=round(s, 4)))
    return out


def new_gaps(arbs, threshold, state_path, t0):
    """Pairs at or below threshold that were not reported in the last 24h, or improved by >= 0.005 since."""
    state = json.load(open(state_path)) if state_path and Path(state_path).exists() else {}
    fresh = []
    for p in arbs:
        if p["inv_sum"] > threshold:
            continue
        key = f"{p['away']} @ {p['home']} | {p['kind']} | {p['pb_leg']} | {p['other_book']}"
        prev = state.get(key)
        recent = prev and (t0 - datetime.fromisoformat(prev["reported"])).total_seconds() < 86400
        if not recent or p["inv_sum"] <= prev["inv_sum"] - 0.005:
            fresh.append(p)
            state[key] = dict(reported=t0.isoformat(), inv_sum=p["inv_sum"], pb_price=p["pb_price"], other_price=p["other_price"])
    # drop state older than 7 days
    state = {k: v for k, v in state.items() if (t0 - datetime.fromisoformat(v["reported"])).total_seconds() < 7 * 86400}
    if state_path:
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        json.dump(state, open(state_path, "w"), indent=1)
    return fresh


def cycle(threshold=None, state_path=None, snapshot=True):
    t0 = now()
    stamp = t0.strftime("%Y%m%dT%H%M%SZ")
    day = OUT / t0.strftime("%Y%m%d")
    day.mkdir(parents=True, exist_ok=True)
    snap, errors, status = [], [], {}
    for name, fn in ((f"pointsbet_{PB_REGION}", pointsbet), ("pinnacle", pinnacle), (f"fanduel_{FD_REGION}", fanduel)):
        t = time.time()
        try:
            rows, errs = fn(t0)
            snap += rows
            errors += errs
            status[name] = dict(rows=len(rows), games=len({r["home"] for r in rows}), seconds=round(time.time() - t, 1), errors=len(errs))
        except Exception as e:  # noqa: BLE001
            status[name] = dict(rows=0, games=0, seconds=round(time.time() - t, 1), error=f"{type(e).__name__}: {e}")
    t1 = now()
    pb_rows = [r for r in snap if r["book"] == f"pointsbet_{PB_REGION}"]
    allpairs = []
    for book in ("pinnacle", f"fanduel_{FD_REGION}"):
        allpairs += pairs(pb_rows, [r for r in snap if r["book"] == book])
    arbs = sorted([p for p in allpairs if p["inv_sum"] < 1], key=lambda p: p["inv_sum"])
    near = [p for p in allpairs if 1 <= p["inv_sum"] < ARB_NEAR]
    if snapshot:
        with open(day / f"snapshot-{stamp}.jsonl", "w") as f:
            for r in snap:
                f.write(json.dumps(dict(captured=t0.isoformat(), **r)) + "\n")
    with open(OUT / "arbs.jsonl", "a") as f:
        for p in arbs:
            f.write(json.dumps(dict(captured=t0.isoformat(), capture_span_s=round((t1 - t0).total_seconds(), 1), **p)) + "\n")
    with open(OUT / "cycles.jsonl", "a") as f:
        f.write(json.dumps(dict(captured=t0.isoformat(), regions=dict(pb=PB_REGION, fd=FD_REGION), span_s=round((t1 - t0).total_seconds(), 1), status=status, pairs=len(allpairs), arbs=len(arbs), near=len(near), errors=errors[:5])) + "\n")
    ages = [r["age_min"] for r in pb_rows if r["age_min"] is not None]
    med_age = sorted(ages)[len(ages) // 2] if ages else None
    print(f"{t0:%Y-%m-%d %H:%M:%S}Z span {(t1 - t0).total_seconds():.0f}s | {status} | pairs {len(allpairs)} arbs {len(arbs)} near {len(near)} | PB median rung age {med_age} min")
    for p in arbs:
        print(f"  ARB {p['inv_sum']:.4f}  {p['away']} @ {p['home']}: PB {p['pb_leg']} {p['pb_price']} (age {p['pb_age_min']} min, main={p['pb_main']})  vs {p['other_book']} {p['other_leg']} {p['other_price']} limit {p['other_limit']}")
    for p in sorted(near, key=lambda p: p["inv_sum"])[:5]:
        print(f"  near {p['inv_sum']:.4f}  {p['away']} @ {p['home']}: PB {p['pb_leg']} {p['pb_price']} (age {p['pb_age_min']} min)  vs {p['other_book']} {p['other_leg']} {p['other_price']}")
    if threshold is not None:
        fresh = new_gaps(arbs, threshold, state_path, t0)
        print(f"NEW_GAPS {len(fresh)} (threshold sum <= {threshold}, not reported in 24h)")
        for p in fresh:
            margin = (1 / p["inv_sum"] - 1) * 100
            print(f"  NEW {p['inv_sum']:.4f} ({margin:.1f}% margin)  {p['away']} @ {p['home']} [{p['kind']}]: PointsBet {p['pb_leg']} @ {p['pb_price']} (rung age {p['pb_age_min']} min, main={p['pb_main']})  vs {p['other_book']} {p['other_leg']} @ {p['other_price']} limit {p['other_limit']}")
    return arbs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=float, default=0, help="minutes between cycles; 0 = single cycle")
    ap.add_argument("--threshold", type=float, default=None, help="report NEW_GAPS with reciprocal sum at or below this (e.g. 0.98 = 2%% margin)")
    ap.add_argument("--state", default=None, help="JSON file remembering reported gaps across runs (needed for 'new')")
    ap.add_argument("--no-snapshot", action="store_true", help="skip the full per-cycle snapshot file (cloud mode)")
    a = ap.parse_args()
    while True:
        try:
            cycle(a.threshold, a.state, not a.no_snapshot)
        except Exception as e:  # noqa: BLE001
            print(f"cycle failed: {type(e).__name__}: {e}", file=sys.stderr)
        if not a.loop:
            break
        time.sleep(a.loop * 60)


if __name__ == "__main__":
    main()
