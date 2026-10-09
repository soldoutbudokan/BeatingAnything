#!/usr/bin/env python3
"""Devig theScore Parlay+ conjunction instances against FanDuel same-game partitions.

A conjunction instance is a two-leg base (for example rushing+receiving yards 90+ and rushing under 54.5) with implied legs
stacked on it; theScore's stacked price pays for the base event only. The fair reference is FanDuel's same-game price for a
cell of its own two-market partition that is a *subset* of the base event (then its probability is a lower bound), devigged
across the four cells (over/over, over/under, under/over, under/under) as PR 4 did.

FanDuel prices those cells through its same-game quote service on api.sportsbook.fanduel.com. When that host is reachable,
`--fetch` quotes the four cells directly; otherwise the tool writes a worksheet listing, per instance, the FanDuel lines whose
four-cell prices are needed, and `--partitions <json>` reads prices entered from the FanDuel site in the form
{"<instance_id>": {"lines": {"S": 91.5, "R": 51.5}, "OO": 127, "OU": 515, "UO": 550, "UU": 123}} (American odds, S first).

python tools/devig_thescore_sgp_conjunctions.py                       # worksheet for the latest rows
python tools/devig_thescore_sgp_conjunctions.py --partitions reports/fd-partitions.json
"""
# %% imports and configuration
import argparse
import glob
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.thescore import devig_multiplicative, devig_power, ev as ev_of  # noqa: E402
from beating.thescore_conjunctions import PLAYER_SPACES, TEAM_RANGE  # noqa: E402

os.environ.setdefault("FD_REGION", "nj")
os.environ.setdefault("PB_REGION", "au")
spec = importlib.util.spec_from_file_location("pb_monitor", ROOT / "tools/collect_pointsbet_live_alternates.py")
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)
spec2 = importlib.util.spec_from_file_location("devig2", ROOT / "tools/devig_thescore_sgp_instances.py")
dv = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(dv)  # FanDuel fixture matching and event-page markets

REPORTS = ROOT / "reports"
FD_STAT_WORDS = {"R": ("rushing", "rush"), "C": ("receiving", "rec"), "S": ("rushing+receiving", "rush + rec", "rushing + receiving", "rush/rec", "rushing & receiving"),
                 "P": ("points",), "RB": ("rebounds",), "AS": ("assists",), "PRA": ("pts + reb + ast", "points + rebounds + assists", "pra"), "PRB": ("pts + reb", "points + rebounds"),
                 "PAS": ("pts + ast", "points + assists"), "ASRB": ("reb + ast", "rebounds + assists", "ast + reb"), "H": ("hits",), "HR": ("home run",), "TB": ("total bases", "bases"), "RBI": ("rbi",),
                 "G": ("goals",), "PTS": ("points",), "SOG": ("shots on goal", "shots")}


def instance_id(row):
    key = "|".join([row["event_id"]] + sorted(a["id"] for a in row["base"]) + sorted(a["id"] for a in row["stack"]))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# %% outcome algebra: is the FanDuel cell a subset of the theScore base event?
def atom_pred(a):
    var, op, thr = a["var"], a["op"], a["threshold"]
    if var is None:
        return None
    if var.startswith("margin_"):
        side = var[-1]
        return (lambda v: (v["H"] - v["A"] if side == "H" else v["A"] - v["H"]) >= thr)
    if var == "total":
        return (lambda v: v["H"] + v["A"] >= thr) if op == ">=" else (lambda v: v["H"] + v["A"] <= thr)
    if var.startswith("team_"):
        side = var[-1]
        return (lambda v: v[side] >= thr) if op == ">=" else (lambda v: v[side] <= thr)
    if var == "result":
        return {">": lambda v: v["H"] > v["A"], "<": lambda v: v["A"] > v["H"], "==": lambda v: v["H"] == v["A"]}[op]
    if var in ("btts",):
        return (lambda v: v["H"] > 0 and v["A"] > 0) if thr == 1 else (lambda v: v["H"] == 0 or v["A"] == 0)
    if var.startswith("dc_"):
        side = var[-1]
        return (lambda v: v["H"] >= v["A"]) if side == "H" else (lambda v: v["A"] >= v["H"])
    if var.startswith("dnb_"):
        side = var[-1]
        return (lambda v: v["H"] > v["A"]) if side == "H" else (lambda v: v["A"] > v["H"])
    if var == "score":
        h, a_ = [int(x) for x in str(thr).split("-")]
        return lambda v: v["H"] == h and v["A"] == a_
    return (lambda v: v[var] >= thr) if op in (">=", ">") else (lambda v: v[var] <= thr)


def enumerate_space(space, sport):
    if space == "team":
        lo, hi = TEAM_RANGE.get(sport, (0, 100))
        for h in range(lo, hi + 1):
            for a in range(lo, hi + 1):
                yield {"H": h, "A": a}
        return
    spec_ = PLAYER_SPACES[space]
    names = list(spec_["vars"])
    import itertools
    for combo in itertools.product(*[range(spec_["vars"][n][0], spec_["vars"][n][1] + 1) for n in names]):
        v = dict(zip(names, combo))
        if any(not c(v) for c in spec_["constraints"]):
            continue
        for d, f in spec_["derived"].items():
            v[d] = f(v)
        yield v


def cell_relation(row, cell_preds):
    """'subset' if every outcome of the FanDuel cell satisfies the theScore base; 'superset' if the reverse; else 'crossed'."""
    base_preds = [atom_pred(a) for a in row["base"]]
    if any(p is None for p in base_preds):
        return "unknown"
    fd_in_base, base_in_fd = True, True
    for v in enumerate_space(row["space"], row["sport"]):
        cell = all(p(v) for p in cell_preds)
        base = all(p(v) for p in base_preds)
        if cell and not base:
            fd_in_base = False
        if base and not cell:
            base_in_fd = False
        if not fd_in_base and not base_in_fd:
            break
    if fd_in_base and base_in_fd:
        return "exact"
    if fd_in_base:
        return "subset"
    if base_in_fd:
        return "superset"
    return "crossed"


def cell_preds_from_lines(row, lines):
    """FanDuel cell for the base's two variables at FanDuel's lines, same directions as the base legs."""
    preds = []
    for a in row["base"]:
        var = a["var"]
        if var not in lines:
            return None
        line = float(lines[var])
        if var.startswith("margin_") or var.startswith("team_") or var == "total":
            if var == "total":
                preds.append((lambda v, t=math.ceil(line): v["H"] + v["A"] >= t) if a["op"] == ">=" else (lambda v, t=math.floor(line): v["H"] + v["A"] <= t))
            elif var.startswith("team_"):
                side = var[-1]
                preds.append((lambda v, s=side, t=math.ceil(line): v[s] >= t) if a["op"] == ">=" else (lambda v, s=side, t=math.floor(line): v[s] <= t))
            else:
                side = var[-1]
                thr = math.floor(-line) + 1
                preds.append((lambda v, s=side, t=thr: (v["H"] - v["A"] if s == "H" else v["A"] - v["H"]) >= t))
        else:
            preds.append((lambda v, k=var, t=math.ceil(line): v[k] >= t) if a["op"] in (">=", ">") else (lambda v, k=var, t=math.floor(line): v[k] <= t))
    return preds


# %% FanDuel straight lines (reachable): which lines FanDuel offers for the base variables
def fd_lines_for(row, markets):
    """-> {var: [handicaps]} from FanDuel's two-way markets for the player's / team's stats."""
    out = {}
    player = (row.get("player") or "").lower()
    for a in row["base"]:
        var = a["var"]
        words = FD_STAT_WORDS.get(var.split("_")[0] if var and var.startswith(("margin", "team")) is False else var, ())
        for m in markets:
            name = m["name"].lower()
            if player and player.split()[-1] not in name:
                continue
            if var and not var.startswith(("margin", "team", "total", "result")) and not any(w in name for w in words):
                continue
            hs = sorted({r["handicap"] for r in m["runners"] if r.get("handicap") is not None})
            if hs:
                out.setdefault(var, set()).update(hs)
    return {k: sorted(v) for k, v in out.items()}


# %% devig a four-cell partition
def partition_ev(row, part):
    cells = ("OO", "OU", "UO", "UU")
    prices = [float(part[c]) for c in cells]
    decs = [1 + p / 100 if p > 0 else 1 + 100 / -p for p in prices]
    mult, hold = devig_multiplicative(decs)
    power, k = devig_power(decs)
    q = [1 / d for d in decs]
    additive = [x - (sum(q) - 1) / 4 for x in q]
    target = part.get("target", "OU")
    i = cells.index(target)
    preds = cell_preds_from_lines(row, part["lines"])
    rel = cell_relation(row, preds) if preds else "unknown"
    stack = (row.get("stack_quote") or {}).get("decimal")
    base = (row.get("base_quote") or {}).get("decimal")
    res = {"relation": rel, "fd_lines": part["lines"], "fd_cells": {c: p for c, p in zip(cells, prices)}, "hold": hold, "power_k": k,
           "p_mult": mult[i], "p_power": power[i], "p_additive": additive[i] if all(0 <= x <= 1 for x in additive) else None}
    if stack:
        res.update(stack_ev_mult=ev_of(stack, mult[i]), stack_ev_power=ev_of(stack, power[i]), stack_ev_additive=ev_of(stack, additive[i]) if res["p_additive"] is not None else None)
    if base:
        res.update(base_ev_power=ev_of(base, power[i]))
    res["bound"] = {"subset": "lower bound", "exact": "estimate", "superset": "upper bound"}.get(rel, "not comparable")
    return res


# %% main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="", help="conjunction JSONL (default: all files from the latest day)")
    ap.add_argument("--partitions", default="", help="JSON of FanDuel four-cell prices keyed by instance id")
    ap.add_argument("--min-uplift", type=float, default=0.005)
    args = ap.parse_args()
    files = [args.rows] if args.rows else sorted(glob.glob(str(ROOT / "data/live/thescore-sgp-conjunctions/*.jsonl")))
    rows = [json.loads(l) for f in files for l in open(f) if l.strip()]
    inst = [r for r in rows if (r.get("stack_quote") or {}).get("decimal") and (r.get("uplift") or 0) > args.min_uplift]
    inst.sort(key=lambda r: -r["uplift"])
    parts = json.load(open(args.partitions)) if args.partitions else {}
    print(f"{len(rows)} constructions, {len(inst)} uplifted instances, {len(parts)} partitions supplied")

    fd_events, fd_markets = {}, {}
    out = []
    for r in inst:
        iid = instance_id(r)
        rec = dict(r, instance_id=iid)
        sport = r["sport"]
        if sport not in fd_events:
            try:
                fd_events[sport] = dv.fd_sport_events(sport)
            except RuntimeError:
                fd_events[sport] = []
        fe = dv.match_event(r, fd_events[sport])
        if fe:
            if fe["id"] not in fd_markets:
                try:
                    fd_markets[fe["id"]] = dv.fd_event_markets(fe["id"])
                except RuntimeError:
                    fd_markets[fe["id"]] = []
            rec["fd_event"] = fe["name"]
            rec["fd_lines_available"] = fd_lines_for(r, fd_markets[fe["id"]])
        else:
            rec["fd_event"] = None
        if iid in parts:
            rec["devig"] = partition_ev(r, parts[iid])
        out.append(rec)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    devigged = [o for o in out if o.get("devig")]
    summary = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "constructions": len(rows), "instances": len(inst), "fd_fixture_matched": sum(1 for o in out if o.get("fd_event")),
               "devigged": len(devigged), "positive_lower_bounds": sum(1 for o in devigged if o["devig"]["relation"] in ("subset", "exact") and (o["devig"].get("stack_ev_power") or 0) > 0),
               "instances_ranked": sorted(out, key=lambda o: -((o.get("devig") or {}).get("stack_ev_power") if (o.get("devig") or {}).get("stack_ev_power") is not None else -9 + o["uplift"] / 1e6))}
    rp = REPORTS / f"thescore-sgp-conjunctions-fanduel-devig-{stamp}.json"
    rp.write_text(json.dumps(summary, indent=1, default=str))
    print(f"wrote {rp.relative_to(ROOT)}: {summary['fd_fixture_matched']} with a FanDuel fixture, {len(devigged)} devigged, {summary['positive_lower_bounds']} positive lower bounds")


if __name__ == "__main__":
    main()
