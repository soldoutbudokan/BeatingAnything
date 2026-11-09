#!/usr/bin/env python3
"""FanDuel board priced against Pinnacle's no-vig line, with PointsBet as a second opinion.

One cycle pulls every pregame event in the chosen leagues from FanDuel (every event-page tab, not only Popular),
Pinnacle's guest API and PointsBet, matches Pinnacle / PointsBet events to FanDuel's, and prices each FanDuel
selection that Pinnacle quotes two-sided at the same line. FanDuel "X+" ladders map to Over X-0.5.

Three devig methods run on the Pinnacle pair (multiplicative, additive, power); the screen ranks on the WORST of
the three, because multiplicative devig flatters long shots. A row is flagged when worst-case EV clears
--ev-threshold. PointsBet's same-line two-sided fair is printed beside it when available; a flag PointsBet
contradicts is more likely a Pinnacle prop error or a stale FanDuel quote than an edge.

Read-only. FD_REGION=nj and PB_REGION=au answer from cloud addresses (see collect_pointsbet_live_alternates.py);
confirm any flagged price on the Ontario board before staking.

--grade re-prices earlier flags at their FanDuel entry price against Pinnacle's current fair line. Run close to
start, that is closing-line value: the test of whether the flags were edges or noise in a low-limit reference.

FD_REGION=nj PB_REGION=au python tools/screen_fanduel_vs_pinnacle.py --leagues nhl,nba,nfl --out data/live/fanduel-screen
FD_REGION=nj PB_REGION=au python tools/screen_fanduel_vs_pinnacle.py --leagues nhl,nba --grade data/live/fanduel-screen/flags.jsonl
"""
# %% imports
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("FD_REGION", "nj")
os.environ.setdefault("PB_REGION", "au")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_pointsbet_live_alternates as c  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# %% devig
def devig(prices):
    """-> {method: [probabilities]} for a complete market's decimal prices."""
    q = [1 / p for p in prices]
    s = sum(q)
    out = {"mult": [x / s for x in q]}
    add = [x - (s - 1) / len(q) for x in q]
    out["add"] = add if min(add) > 0 else out["mult"]
    lo, hi = 1.0, 3.0  # power: sum(q^k) = 1
    for _ in range(80):
        k = (lo + hi) / 2
        if sum(x ** k for x in q) > 1:
            lo = k
        else:
            hi = k
    out["power"] = [x ** k for x in q]
    return out


def fair_from(idx, players, r):
    """Reference book's devigged probabilities for FanDuel row r at the same line, or None."""
    if r["kind"] == "moneyline3":
        sides = ["home", "away", "draw"]
        rows = [idx.get(c.row_key(r, s)) for s in sides]
        own = sides.index(r["sel"])
    elif r["kind"] in c.TWO_WAY:
        opp = c.opposite(r)
        rows = [c.lookup(idx, players, r, r["sel"]), c.lookup(idx, players, r, opp[0], opp[1])]
        own = 0
    else:
        return None
    if any(x is None for x in rows):
        return None
    d = devig([x["price"] for x in rows])
    return dict(probs={m: round(v[own], 4) for m, v in d.items()}, prices=[rows[own]["price"]] + [x["price"] for i, x in enumerate(rows) if i != own],
                limit=rows[own].get("limit"), age_min=rows[own].get("age_min"))


# %% FanDuel, every tab
def tab_slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower().replace("™", "")).strip("-")


def fanduel_all_tabs(leagues, t0, horizon, workers, skip_tabs=("same-game-parlay", "quick-hits")):
    pages = {lg: c.LEAGUES[lg] for lg in leagues if "fd_page" in c.LEAGUES[lg] or "fd_comp" in c.LEAGUES[lg]}
    by_league, errors = c.fd_page_events(pages, t0, horizon)
    events = {e["id"]: e for evs in by_league.values() if evs for e in evs}

    def fetch(ev):
        markets, errs = {}, []
        try:
            d = c.get(f"{c.FD}/event-page?_ak={c.FD_AK}&eventId={ev['id']}&tab=popular", c.FD_H)
        except RuntimeError as err:
            return ev, markets, [str(err)]
        markets.update(d["attachments"].get("markets", {}))
        slugs = [tab_slug(t.get("title", "")) for t in d.get("layout", {}).get("tabs", {}).values()]
        for slug in slugs:
            if slug in ("popular", "") or slug in skip_tabs:
                continue
            try:
                dd = c.get(f"{c.FD}/event-page?_ak={c.FD_AK}&eventId={ev['id']}&tab={slug}", c.FD_H, tries=2)
                markets.update(dd["attachments"].get("markets", {}))
            except RuntimeError as err:
                errs.append(f"{slug}: {err}")
            time.sleep(0.1)
        return ev, markets, errs

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ev, markets, errs in ex.map(fetch, events.values()):
            errors += errs
            rows += c.fd_event_rows({"attachments": {"markets": markets}}, ev, c.LEAGUES[ev["league"]]["sport"])
    seen, uniq = set(), []
    for r in rows:  # the same market can sit on two tabs
        k = c.row_key(r)
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq, errors, events


# %% one cycle
def cycle(leagues, max_days, workers, use_pb=True):
    t0 = c.now()
    horizon = t0 + timedelta(days=max_days)
    fd_rows, fd_errs, fd_events = fanduel_all_tabs(leagues, t0, horizon, workers)
    refs, status = {}, dict(fanduel=dict(rows=len(fd_rows), games=len(fd_events), errors=len(fd_errs)))
    jobs = [("pinnacle", lambda: c.pinnacle(leagues, t0, horizon, workers))]
    if use_pb:
        jobs.append(("pointsbet", lambda: c.pointsbet(leagues, t0, horizon, workers)))
    for name, fn in jobs:
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001
            status[name] = dict(error=f"{type(e).__name__}: {e}")
            continue
        rows, events = res[0], res[-1]
        mapping = c.match_events(fd_events, events)
        kept = [dict(r, game=mapping[r["game"]]) for r in rows if r["game"] in mapping]
        refs[name] = c.index_rows(kept)
        status[name] = dict(rows=len(kept), games=len(set(mapping.values())), unmatched=len(events) - len(mapping))
    out = []
    for r in fd_rows:
        if "pinnacle" not in refs:
            break
        f = fair_from(*refs["pinnacle"], r)
        if not f:
            continue
        evs = {m: round(r["price"] * p - 1, 4) for m, p in f["probs"].items()}
        row = dict(captured=t0.isoformat(), league=r["league"], game=f"{r['away']} @ {r['home']}", start=r["start"], market=c.market_label(r), leg=c.leg_label(r),
                   main=r["main"], fd_price=r["price"], pin_prices=f["prices"], pin_limit=f["limit"], pin_fair=f["probs"], ev=evs, ev_worst=min(evs.values()))
        if "pointsbet" in refs:
            g = fair_from(*refs["pointsbet"], r)
            if g:
                row.update(pb_prices=g["prices"], pb_fair=g["probs"]["mult"], pb_age_min=g["age_min"], ev_pb=round(r["price"] * g["probs"]["mult"] - 1, 4))
        out.append(row)
    out.sort(key=lambda x: -x["ev_worst"])
    return t0, status, out, fd_errs


def fmt(x):
    pb = f" | PB fair {x['pb_fair']:.3f} EV {x['ev_pb'] * 100:+.1f}% (age {x['pb_age_min']} min)" if "pb_fair" in x else ""
    return (f"{x['ev_worst'] * 100:+5.1f}% worst ({x['ev']['mult'] * 100:+.1f} mult / {x['ev']['add'] * 100:+.1f} add / {x['ev']['power'] * 100:+.1f} power)  "
            f"{x['game']} [{x['market']}] {x['leg']} FD {x['fd_price']} | Pinnacle {'/'.join(str(p) for p in x['pin_prices'])} limit {x['pin_limit']}{pb}")


# %% closing-line grade
def flag_key(x):
    return x["league"], x["game"], x["market"], x["leg"]


def grade(flags, rows, t0, max_hours=None):
    """Entry FanDuel price x Pinnacle's current fair, for each flag still quoted two-sided at Pinnacle on the same line."""
    now_rows = {flag_key(x): x for x in rows}
    first = {}
    for x in flags:  # first sighting is the entry
        first.setdefault(flag_key(x), x)
    out = []
    for k, x in first.items():
        cur = now_rows.get(k)
        if not cur:
            continue
        hours = (c.ts(x["start"]) - t0).total_seconds() / 3600
        if max_hours is not None and hours > max_hours:
            continue
        clv = {m: round(x["fd_price"] * p - 1, 4) for m, p in cur["pin_fair"].items()}
        out.append(dict(graded=t0.isoformat(), hours_to_start=round(hours, 2), league=x["league"], game=x["game"], market=x["market"], leg=x["leg"],
                        entry_captured=x["captured"], entry_price=x["fd_price"], entry_ev_worst=x["ev_worst"], entry_pin=x["pin_prices"],
                        now_pin=cur["pin_prices"], now_fd=cur["fd_price"], clv=clv, clv_worst=min(clv.values())))
    return out, len(first)


# %% main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="nfl,nba,nhl,ncaaf,ncaab,epl,ucl")
    ap.add_argument("--max-days", type=float, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--ev-threshold", type=float, default=0.02)
    ap.add_argument("--min-fair", type=float, default=0.05)
    ap.add_argument("--no-pointsbet", action="store_true")
    ap.add_argument("--out", default=None, help="directory for priced.jsonl (every priced FanDuel row) and flags.jsonl")
    ap.add_argument("--grade", default=None, help="flags.jsonl from an earlier run: print each flag's entry price against Pinnacle's current fair")
    ap.add_argument("--grade-max-hours", type=float, default=None, help="with --grade, only flags starting within this many hours")
    ap.add_argument("--grade-out", default=None, help="append graded rows to this JSON-lines file")
    a = ap.parse_args()
    leagues = [x for x in a.leagues.split(",") if x in c.LEAGUES]
    t0, status, rows, errs = cycle(leagues, a.max_days, a.workers, not a.no_pointsbet)
    if a.grade:
        flags = [json.loads(line) for line in open(a.grade)]
        graded, n = grade(flags, rows, t0, a.grade_max_hours)
        mean = sum(g["clv_worst"] for g in graded) / len(graded) if graded else None
        print(f"{t0:%Y-%m-%d %H:%M:%S}Z graded {len(graded)} of {n} flags | mean worst-case CLV {mean} | positive {sum(g['clv_worst'] > 0 for g in graded)}")
        for g in sorted(graded, key=lambda g: -g["clv_worst"]):
            print(f"  CLV {g['clv_worst'] * 100:+5.1f}% (entry EV {g['entry_ev_worst'] * 100:+.1f}%)  {g['game']} [{g['market']}] {g['leg']} @ {g['entry_price']} | "
                  f"Pinnacle then {g['entry_pin']} now {g['now_pin']} | FD now {g['now_fd']} | {g['hours_to_start']}h to start")
        if a.grade_out:
            with open(a.grade_out, "a") as f:
                for g in graded:
                    f.write(json.dumps(g) + "\n")
        return
    flags = [x for x in rows if x["ev_worst"] >= a.ev_threshold and min(x["pin_fair"].values()) >= a.min_fair]
    evs = sorted(x["ev"]["mult"] for x in rows)
    med = evs[len(evs) // 2] if evs else None
    print(f"{t0:%Y-%m-%d %H:%M:%S}Z {status} | priced {len(rows)} median EV {med} | flags {len(flags)} | FD errors {len(errs)}")
    for x in flags:
        print("  " + fmt(x))
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        stamp = t0.strftime("%Y%m%dT%H%M%SZ")
        with open(out / f"priced-{stamp}.jsonl", "w") as f:
            for x in rows:
                f.write(json.dumps(x) + "\n")
        with open(out / "flags.jsonl", "a") as f:
            for x in flags:
                f.write(json.dumps(x) + "\n")


if __name__ == "__main__":
    main()
