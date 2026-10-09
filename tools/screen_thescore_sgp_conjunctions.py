#!/usr/bin/env python3
"""Price every conjunction construction on theScore Bet Parlay+: a two-leg base whose outcomes force further legs, with those
implied legs stacked on top. A fair engine returns the base price for the stack; a higher price means the implied legs were
multiplied in. Every draft is read with the eligibility and error checks, so refused drafts never count as quotes.

Per construction the tool prices: the base; the base plus each stacked implied leg on its own; and the base plus the whole
stack (one leg per implied market, the highest threshold of each). Rows go to data/live/thescore-sgp-conjunctions/<stamp>.jsonl
and a summary JSON to reports/.

python tools/screen_thescore_sgp_conjunctions.py --sports football            # NFL, NCAAF, CFL
python tools/screen_thescore_sgp_conjunctions.py --competitions /competition/wnba,/competition/mlb
"""
# %% imports and configuration
import argparse
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.thescore import TheScore  # noqa: E402
from beating.thescore_conjunctions import constructions  # noqa: E402

OUT_DIR = ROOT / "data/live/thescore-sgp-conjunctions"
REPORTS = ROOT / "reports"
ELIGIBLE_SPORTS = {"football", "basketball", "baseball", "hockey", "soccer"}  # Parlay+ is refused outright in the others
EXCLUDED_PATH_WORDS = ("Futures", "Draft", "Specials", "Awards", "Season Wins", "Pre-Season", "Preseason")


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def pregame(ev, now, horizon_h):
    st = ev.get("startTime")
    if ev.get("status") != "PRE_GAME" or not st:
        return False
    try:
        start = datetime.fromisoformat(st.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - 300 < start.timestamp() <= now + horizon_h * 3600


# %% pricing one construction
def quote(client, atoms):
    r = client.price_parlay([a.sel for a in atoms], max_wait=8)
    return {"decimal": r.get("decimal"), "formatted": r.get("formatted"), "eligible": r.get("eligible"), "draft_decimal": r.get("draft_decimal"), "error": r.get("error"), "waited": r.get("waited")}


def price_construction(client, con, singles=True):
    base, stack = con["base"], con["stack"]
    out = {"base_quote": quote(client, base), "single_quotes": {}, "stack_quote": None}
    if not out["base_quote"]["decimal"]:
        return out
    cheap = all((a.decimal or 1) < 1.10 for a in stack)
    if singles and not cheap:
        for a in stack[:4]:
            out["single_quotes"][a.key] = quote(client, base + [a])
    out["stack_quote"] = quote(client, base + stack) if len(stack) > 1 or not out["single_quotes"] else out["single_quotes"][stack[0].key]
    return out


def row_for(comp, ev, con, priced):
    b, s = priced["base_quote"], priced["stack_quote"] or {}
    product = 1.0
    for a in con["stack"]:
        product *= (a.decimal or 1.0)
    uplift = (s["decimal"] / b["decimal"] - 1.0) if (b.get("decimal") and s.get("decimal")) else None
    best_single = None
    for k, q in priced["single_quotes"].items():
        if q.get("decimal") and b.get("decimal"):
            u = q["decimal"] / b["decimal"] - 1.0
            if best_single is None or u > best_single[1]:
                best_single = (k, u)
    return {
        "captured": datetime.now(timezone.utc).isoformat(timespec="seconds"), "board": None, "sport": comp["sport"], "competition": comp["path"][-1], "competition_url": comp["url"],
        "event_id": ev.get("id"), "event": ev.get("name"), "start": ev.get("startTime"), "event_url": (ev.get("deepLink") or {}).get("webUrl"),
        "space": con["space"], "player": con["player"], "feasible_outcomes": con["feasible"],
        "base": [a.record() for a in con["base"]], "implied": [a.record() for a in con["implied"]], "stack": [a.record() for a in con["stack"]],
        "base_quote": b, "single_quotes": {k: v for k, v in priced["single_quotes"].items()}, "stack_quote": s,
        "uplift": uplift, "stack_product": product, "vs_independent": (s["decimal"] / (b["decimal"] * product) - 1.0) if (uplift is not None and product) else None,
        "best_single_uplift": best_single[1] if best_single else None, "best_single_key": best_single[0] if best_single else None,
    }


# %% main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sports", default="", help="comma list of theScore sport slugs (default: football, basketball, baseball, hockey, soccer)")
    ap.add_argument("--competitions", default="", help="comma list of competition URL substrings to keep")
    ap.add_argument("--max-events", type=int, default=20, help="per competition")
    ap.add_argument("--max-constructions", type=int, default=120, help="per event")
    ap.add_argument("--max-per-player", type=int, default=40)
    ap.add_argument("--max-team-pairs", type=int, default=60)
    ap.add_argument("--horizon-hours", type=float, default=96)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-singles", action="store_true", help="price only base and full stack")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ") + (f"-{args.tag}" if args.tag else "")
    out_path = OUT_DIR / f"{stamp}.jsonl"
    nav = TheScore()
    region, rerr = nav.regional_metadata()
    log(f"board {nav.region} regional={region} err={rerr}")
    wanted = set(args.sports.split(",")) if args.sports else ELIGIBLE_SPORTS
    comps = [c for c in nav.competitions() if c["sport"] in wanted and not any(w in " ".join(c["path"]) for w in EXCLUDED_PATH_WORDS)]
    if args.competitions:
        keys = args.competitions.split(",")
        comps = [c for c in comps if any(k in c["url"] for k in keys)]
    log(f"{len(comps)} competitions in scope")
    now = time.time()
    jobs = []
    for c in comps:
        rows, err = nav.competition_events(c["url"])
        for r in (rows or []):
            if pregame(r["event"], now, args.horizon_hours):
                jobs.append((c, r["event"]))
        jobs_c = [j for j in jobs if j[0] is c][: args.max_events]
        jobs = [j for j in jobs if j[0] is not c] + jobs_c
    log(f"{len(jobs)} pregame events")

    local = threading.local()
    lock = threading.Lock()
    stats = Counter()

    def work(job):
        comp, ev = job
        client = getattr(local, "client", None)
        if client is None:
            client = local.client = TheScore(sleep=0.05)
        try:
            data, err = client.event_markets(ev["deepLink"]["webUrl"])
            if not data:
                with lock:
                    stats["event_errors"] += 1
                return 0
            cons = constructions(data.get("event") or ev, data["markets"], comp["sport"], args.max_per_player, args.max_team_pairs)[: args.max_constructions]
        except Exception as e:  # noqa: BLE001
            with lock:
                stats["event_errors"] += 1
            log(f"enumerate failed {ev.get('name')}: {type(e).__name__}: {e}")
            return 0
        n = 0
        for con in cons:
            try:
                priced = price_construction(client, con, singles=not args.no_singles)
            except Exception as e:  # noqa: BLE001
                log(f"price failed {ev.get('name')}: {type(e).__name__}: {e}")
                continue
            row = row_for(comp, ev, con, priced)
            row["board"] = client.region
            with lock:
                with open(out_path, "a") as f:
                    f.write(json.dumps(row) + "\n")
                stats["constructions"] += 1
                stats["base_quoted"] += 1 if row["base_quote"].get("decimal") else 0
                stats["stack_quoted"] += 1 if (row["stack_quote"] or {}).get("decimal") else 0
                stats["uplift"] += 1 if (row["uplift"] or 0) > 0.005 else 0
            n += 1
        with lock:
            stats["events"] += 1
            log(f"{stats['events']}/{len(jobs)} events | {ev.get('name')[:40]}: {len(cons)} constructions | totals: {stats['constructions']} constructions, {stats['base_quoted']} base quoted, {stats['stack_quoted']} stack quoted, {stats['uplift']} uplifted")
        return n

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, jobs))

    # %% summary
    rows = [json.loads(l) for l in open(out_path)] if out_path.exists() else []
    by = defaultdict(lambda: {"constructions": 0, "stack_quoted": 0, "uplifted": 0, "refused": 0, "max_uplift": 0.0})
    for r in rows:
        k = (r["sport"], r["competition"], r["space"])
        b = by[k]
        b["constructions"] += 1
        sq = r.get("stack_quote") or {}
        if sq.get("decimal"):
            b["stack_quoted"] += 1
            if (r["uplift"] or 0) > 0.005:
                b["uplifted"] += 1
                b["max_uplift"] = max(b["max_uplift"], r["uplift"])
        elif sq.get("error"):
            b["refused"] += 1
    summary = {"captured": stamp, "board": nav.region, "regional_metadata": region, "events": stats["events"], "constructions": len(rows),
               "stack_quoted": sum(1 for r in rows if (r.get("stack_quote") or {}).get("decimal")), "uplifted": sum(1 for r in rows if (r["uplift"] or 0) > 0.005),
               "rows_path": str(out_path.relative_to(ROOT)), "by_competition_space": {" | ".join(k): v for k, v in by.items()},
               "uplifted_rows": sorted([r for r in rows if (r["uplift"] or 0) > 0.005], key=lambda r: -r["uplift"])}
    rp = REPORTS / f"thescore-sgp-conjunctions-{stamp}.json"
    rp.write_text(json.dumps(summary, indent=1))
    log(f"done: {stats['events']} events, {len(rows)} constructions, {summary['stack_quoted']} stacks quoted, {summary['uplifted']} uplifted -> {rp.relative_to(ROOT)}")
    for k, v in sorted(by.items()):
        log(f"  {' | '.join(k):60s} n={v['constructions']:4d} quoted={v['stack_quoted']:4d} uplifted={v['uplifted']:4d} refused={v['refused']:4d} max={v['max_uplift']:.3f}")


if __name__ == "__main__":
    main()
