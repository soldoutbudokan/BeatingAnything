#!/usr/bin/env python3
"""Screen theScore Bet's Parlay+ (same-game parlay) engine for redundant legs that raise the price.

For every pregame event in every competition the board lists (optionally restricted to sports FanDuel also carries), build
pairs (A, B) where winning A guarantees winning B, price the two-leg Parlay+ on an anonymous betslip, and compare with A's
straight price. A fair engine returns exactly A's price; a price above it means the redundant leg B was multiplied in.

Rows go to data/live/thescore-sgp-redundant/<stamp>.jsonl (one per priced pair) and a summary JSON to reports/.

python tools/screen_thescore_sgp_redundant_legs.py                      # all shared sports
python tools/screen_thescore_sgp_redundant_legs.py --sports mma,tennis  # subset
THESCORE_REGION=ca-default python tools/screen_thescore_sgp_redundant_legs.py   # Ontario board; needs an Ontario IP for prices
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
from beating.thescore import TheScore, implied_pairs, REGION  # noqa: E402

OUT_DIR = ROOT / "data/live/thescore-sgp-redundant"
REPORTS = ROOT / "reports"
# theScore sport slugs that FanDuel (NJ) also lists with pregame events; golf/motorsports/cricket pages carry no lined events here
SHARED_SPORTS = {"football", "basketball", "hockey", "baseball", "soccer", "tennis", "mma", "boxing", "rugby-league", "rugby-union", "cricket",
                 "handball", "australian-rules", "darts", "snooker", "golf", "motorsports"}
EXCLUDED_PATH_WORDS = ("Futures", "Draft", "Specials", "Awards", "Season Wins", "Oscars", "Grammys")


# %% helpers
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


def price_event(client, comp, row, max_pairs, max_per_rule):
    ev = row["event"]
    url = (ev.get("deepLink") or {}).get("webUrl")
    data, err = client.event_markets(url)
    if not data:
        return [], {"event": ev.get("name"), "error": str(err)[:200]}
    event = data.get("event") or ev
    pairs = implied_pairs(event, data["markets"], max_per_rule=max_per_rule)[:max_pairs]
    rows = []
    for p in pairs:
        res = client.price_parlay([p["a_sel"], p["b_sel"]])
        a_dec = p["a"]["decimal"]
        rows.append({
            "captured": datetime.now(timezone.utc).isoformat(timespec="seconds"), "board": client.region, "sport": comp["sport"], "competition": comp["path"][-1],
            "competition_url": comp["url"], "event_id": ev.get("id"), "event": ev.get("name"), "start": ev.get("startTime"), "event_url": url,
            "rule": p["rule"], "a": p["a"], "b": p["b"], "sgp_decimal": res.get("decimal"), "sgp_formatted": res.get("formatted"), "eligible": res.get("eligible"),
            "waited_s": res.get("waited"), "error": res.get("error"), "errors": res.get("errors"),
            "improvement": (res["decimal"] / a_dec - 1.0) if res.get("decimal") and a_dec else None,
            "vs_independent": (res["decimal"] / (a_dec * p["b"]["decimal"]) - 1.0) if res.get("decimal") and a_dec and p["b"]["decimal"] else None,
        })
    return rows, None


# %% main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sports", default="", help="comma list of theScore sport slugs (default: every shared sport)")
    ap.add_argument("--max-events", type=int, default=12, help="per competition")
    ap.add_argument("--max-pairs", type=int, default=14, help="per event")
    ap.add_argument("--max-per-rule", type=int, default=2)
    ap.add_argument("--horizon-hours", type=float, default=72)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--competitions", default="", help="comma list of competition URL substrings to keep")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_path = OUT_DIR / f"{stamp}.jsonl"
    nav = TheScore()
    region, rerr = nav.regional_metadata()
    log(f"board {nav.region} regional={region} err={rerr}")
    comps = nav.competitions()
    wanted = set(args.sports.split(",")) if args.sports else SHARED_SPORTS
    comps = [c for c in comps if c["sport"] in wanted and not any(w in " ".join(c["path"]) for w in EXCLUDED_PATH_WORDS)]
    if args.competitions:
        keys = args.competitions.split(",")
        comps = [c for c in comps if any(k in c["url"] for k in keys)]
    log(f"{len(comps)} competitions in scope")

    now = time.time()
    jobs = []
    for c in comps:
        rows, err = nav.competition_events(c["url"])
        if not rows:
            continue
        evs = [r for r in rows if pregame(r["event"], now, args.horizon_hours)][: args.max_events]
        for r in evs:
            jobs.append((c, r))
    log(f"{len(jobs)} pregame events to price")

    local = threading.local()  # one anonymous betslip per worker thread; sharing a slip across threads mixes legs
    lock = threading.Lock()
    stats = Counter()
    errors = []

    def work(idx_job):
        i, (c, r) = idx_job
        client = getattr(local, "client", None)
        if client is None:
            client = local.client = TheScore(sleep=0.05)
        try:
            rows, err = price_event(client, c, r, args.max_pairs, args.max_per_rule)
        except Exception as e:  # noqa: BLE001
            rows, err = [], {"event": r["event"].get("name"), "error": f"{type(e).__name__}: {e}"[:200]}
        with lock:
            if err:
                errors.append(err)
            with open(out_path, "a") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            stats["events"] += 1
            stats["pairs"] += len(rows)
            stats["priced"] += sum(1 for x in rows if x["sgp_decimal"])
            stats["improved"] += sum(1 for x in rows if x["improvement"] is not None and x["improvement"] > 0.005)
            if stats["events"] % 10 == 0:
                log(f"{stats['events']}/{len(jobs)} events, {stats['pairs']} pairs, {stats['priced']} priced, {stats['improved']} improved")
        return len(rows)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, enumerate(jobs)))

    # %% summary
    rows = [json.loads(l) for l in open(out_path)] if out_path.exists() else []
    by_rule = defaultdict(lambda: {"pairs": 0, "priced": 0, "exact": 0, "below": 0, "improved": 0, "max_improvement": None, "errors": Counter()})
    by_sport = defaultdict(lambda: {"events": set(), "pairs": 0, "priced": 0, "improved": 0})
    for r in rows:
        br = by_rule[r["rule"]]
        bs = by_sport[r["sport"]]
        br["pairs"] += 1
        bs["pairs"] += 1
        bs["events"].add(r["event_id"])
        if r["sgp_decimal"]:
            br["priced"] += 1
            bs["priced"] += 1
            imp = r["improvement"]
            if imp > 0.005:
                br["improved"] += 1
                bs["improved"] += 1
                br["max_improvement"] = max(br["max_improvement"] or 0, imp)
            elif imp < -0.005:
                br["below"] += 1
            else:
                br["exact"] += 1
        else:
            br["errors"][str(r["error"])] += 1
    summary = {
        "captured": stamp, "board": nav.region, "regional_metadata": region, "competitions": len(comps), "events": stats["events"], "pairs": stats["pairs"],
        "priced": stats["priced"], "improved": stats["improved"], "rows_path": str(out_path.relative_to(ROOT)),
        "by_rule": {k: dict(v, errors=dict(v["errors"])) for k, v in by_rule.items()},
        "by_sport": {k: dict(v, events=len(v["events"])) for k, v in by_sport.items()},
        "improved_rows": sorted([r for r in rows if r["improvement"] is not None and r["improvement"] > 0.005], key=lambda r: -r["improvement"]),
        "errors": errors[:50],
    }
    rp = REPORTS / f"thescore-sgp-redundant-legs-{stamp[:10]}.json"
    rp.write_text(json.dumps(summary, indent=1))
    log(f"done: {stats['events']} events, {stats['pairs']} pairs, {stats['priced']} priced, {stats['improved']} improved -> {rp.relative_to(ROOT)}")
    for k, v in sorted(by_rule.items()):
        log(f"  {k:26s} pairs={v['pairs']:4d} priced={v['priced']:4d} exact={v['exact']:4d} below={v['below']:4d} improved={v['improved']:4d} max={v['max_improvement']} errors={dict(v['errors'])}")


if __name__ == "__main__":
    main()
