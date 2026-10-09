#!/usr/bin/env python3
"""Devig theScore Parlay+ conjunction instances against FanDuel same-game prices and rank them by EV.

A conjunction instance is a two-leg base (for example rushing+receiving yards 90+ and rushing under 54.5) with implied legs
stacked on it; theScore's stacked price pays for the base event only. The fair reference is FanDuel's same-game price for a
cell of a two-market partition (over/over, over/under, under/over, under/under of two FanDuel two-way markets), devigged
across the four cells as PR 4 did. The cell is compared with the base event by enumerating the outcome space:

    exact     the FanDuel cell is the base event                  -> EV estimate
    subset    every outcome of the cell satisfies the base        -> the cell probability is a lower bound, so is the EV
    superset  every base outcome lies in the cell                 -> upper bound
    crossed   neither; the nearest cell is quoted as an estimate  -> approximate

FanDuel's cell prices come from the betslip's implyBets call (beating/fanduel_sgp.py). When that host is outside the network
policy the tool still writes the coverage (which instances have a FanDuel partition and which cell it would quote) and marks
every quote host_blocked; `--partitions <json>` takes prices read from the FanDuel site instead, keyed by instance id:
{"<instance_id>": {"OO": 127, "OU": 515, "UO": 550, "UU": 123}} (American odds, cells in the order written in the worksheet).

python tools/devig_thescore_sgp_conjunctions.py --fetch                # quote every instance's four cells on FanDuel
python tools/devig_thescore_sgp_conjunctions.py --partitions prices.json
"""
# %% imports and configuration
import argparse
import glob
import hashlib
import importlib.util
import itertools
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating import fanduel_sgp as fd  # noqa: E402
from beating.thescore import devig_multiplicative, devig_power, ev as ev_of  # noqa: E402
from beating.thescore_conjunctions import PLAYER_SPACES, TEAM_RANGE  # noqa: E402

os.environ.setdefault("FD_REGION", "nj")
os.environ.setdefault("PB_REGION", "au")
spec2 = importlib.util.spec_from_file_location("devig2", ROOT / "tools/devig_thescore_sgp_instances.py")
dv = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(dv)  # FanDuel fixture matching

REPORTS = ROOT / "reports"
CELLS = ("OO", "OU", "UO", "UU")
CONSTITUENTS = {"S": ("R", "C"), "PRA": ("P", "RB", "AS"), "PRB": ("P", "RB"), "PAS": ("P", "AS"), "ASRB": ("AS", "RB"), "result": ("margin_H",), "margin_H": ("result",), "margin_A": ("margin_H", "result")}
CAP_STACK, CAP_BASE = "+100000", "+8000"  # theScore display caps seen on the Ohio board
RELATION_RANK = {"exact": 0, "subset": 1, "superset": 2, "crossed": 3}


def instance_id(row):
    key = "|".join([row["event_id"]] + sorted(a["id"] for a in row["base"]) + sorted(a["id"] for a in row["stack"]))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def american(decimal):
    if decimal is None:
        return None
    return f"+{round((decimal - 1) * 100)}" if decimal >= 2 else f"{round(-100 / (decimal - 1))}"


# %% outcome algebra
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


def fd_atom_pred(atom, direction):
    """Predicate for one side of a FanDuel two-way market: 'O' = over / home, 'U' = under / away."""
    var, line = atom["var"], atom["line"]
    if var == "result":
        return (lambda v: v["H"] > v["A"]) if direction == "O" else (lambda v: v["A"] > v["H"])
    hi, lo = math.ceil(line), math.floor(line)
    if var == "total":
        return (lambda v: v["H"] + v["A"] >= hi) if direction == "O" else (lambda v: v["H"] + v["A"] <= lo)
    if var.startswith("team_"):
        side = var[-1]
        return (lambda v: v[side] >= hi) if direction == "O" else (lambda v: v[side] <= lo)
    if var == "margin_H":
        return (lambda v: v["H"] - v["A"] >= hi) if direction == "O" else (lambda v: v["H"] - v["A"] <= lo)
    return (lambda v: v[var] >= hi) if direction == "O" else (lambda v: v[var] <= lo)


_POINTS = {}


def space_points(space, sport):
    key = (space, sport if space == "team" else None)
    if key in _POINTS:
        return _POINTS[key]
    pts = []
    if space == "team":
        lo, hi = TEAM_RANGE.get(sport, (0, 100))
        pts = [{"H": h, "A": a} for h in range(lo, hi + 1) for a in range(lo, hi + 1)]
    else:
        spec_ = PLAYER_SPACES[space]
        names = list(spec_["vars"])
        for combo in itertools.product(*[range(spec_["vars"][n][0], spec_["vars"][n][1] + 1) for n in names]):
            v = dict(zip(names, combo))
            if any(not c(v) for c in spec_["constraints"]):
                continue
            for d, f in spec_["derived"].items():
                v[d] = f(v)
            pts.append(v)
    _POINTS[key] = pts
    return pts


def relation_of(cell_mask, base_mask):
    cell_not_base = base_not_cell = 0
    for c, b in zip(cell_mask, base_mask):
        if c and not b:
            cell_not_base += 1
        elif b and not c:
            base_not_cell += 1
    if not cell_not_base and not base_not_cell:
        return "exact", 0, 0
    if not cell_not_base:
        return "subset", cell_not_base, base_not_cell
    if not base_not_cell:
        return "superset", cell_not_base, base_not_cell
    return "crossed", cell_not_base, base_not_cell


def cell_relation(row, cell_preds):
    """Relation of an arbitrary cell (list of predicates) to the base event: 'exact', 'subset', 'superset' or 'crossed'."""
    base_preds = [atom_pred(a) for a in row["base"]]
    if any(p is None for p in base_preds):
        return "unknown"
    pts = space_points(row["space"], row["sport"])
    base_mask = [all(p(v) for p in base_preds) for v in pts]
    cell_mask = [all(p(v) for p in cell_preds) for v in pts]
    return relation_of(cell_mask, base_mask)[0]


# %% FanDuel partition for an instance
def _norm_name(s):
    s = re.sub(r"[.'’\-]", "", (s or "").lower())
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return s.split()


def same_person(a, b):
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    return na == nb or (na[-1] == nb[-1] and na[0][0] == nb[0][0])


def candidate_atoms(row, two_way, per_var=5):
    """FanDuel two-way atoms that can bound the base: the base variables and their constituents, lines nearest the base thresholds."""
    wanted = {}
    for a in row["base"]:
        if a["var"] == "margin_A":  # FanDuel spreads are kept as home margins: margin_A >= t  <=>  margin_H <= -t
            wanted.setdefault("margin_H", []).append(-a["threshold"])
        else:
            wanted.setdefault(a["var"], []).append(a["threshold"])
        for c in CONSTITUENTS.get(a["var"], ()):
            wanted.setdefault(c, [])
    out = []
    for var, thrs in wanted.items():
        atoms = [t for t in two_way if t["var"] == var and (row["space"] == "team") == (t["player"] is None)]
        if row.get("player"):
            atoms = [t for t in atoms if same_person(t["player"], row["player"])]
        atoms = [t for t in atoms if t["line"] is None or t["line"] != int(t["line"])]  # whole lines push and break the partition
        if not thrs and atoms:  # a constituent variable: centre on the main line (the median of the posted lines; the margin at zero)
            lines = sorted(t["line"] for t in atoms if t["line"] is not None)
            thrs = [0.0] if var == "margin_H" else ([lines[len(lines) // 2]] if lines else [])
        if thrs and len(atoms) > per_var:
            atoms.sort(key=lambda t: min(abs((t["line"] or 0) - x) for x in thrs))
            atoms = atoms[:per_var]
        out.extend(atoms)
    return out


def best_cell(row, two_way, per_var=5):
    """Pick the FanDuel market pair and cell closest to the base event. -> dict or None."""
    base_preds = [atom_pred(a) for a in row["base"]]
    if any(p is None for p in base_preds):
        return None
    cands = candidate_atoms(row, two_way, per_var)
    if len(cands) < 2:
        return None
    pts = space_points(row["space"], row["sport"])
    base_mask = [all(p(v) for p in base_preds) for v in pts]
    masks = {}
    for i, atom in enumerate(cands):
        for d in "OU":
            pred = fd_atom_pred(atom, d)
            masks[(i, d)] = [pred(v) for v in pts]
    best = None
    for i, j in itertools.combinations(range(len(cands)), 2):
        a1, a2 = cands[i], cands[j]
        if a1["var"] == a2["var"] or a1["marketId"] == a2["marketId"]:
            continue
        for d1, d2 in itertools.product("OU", "OU"):
            m1, m2 = masks[(i, d1)], masks[(j, d2)]
            cell = [x and y for x, y in zip(m1, m2)]
            if not any(cell):
                continue
            rel, cnb, bnc = relation_of(cell, base_mask)
            key = (RELATION_RANK[rel], cnb + bnc)
            if best is None or key < best["key"]:
                best = {"key": key, "atoms": (a1, a2), "target": d1 + d2, "relation": rel, "cell_not_base": cnb, "base_not_cell": bnc}
    if best is None:
        return None
    a1, a2 = best["atoms"]
    return {"relation": best["relation"], "target": best["target"], "cell_not_base": best["cell_not_base"], "base_not_cell": best["base_not_cell"],
            "markets": [{"var": a["var"], "line": a["line"], "name": a["name"], "marketId": a["marketId"],
                         "over": {"selectionId": a["over"]["selectionId"], "name": a["over"]["name"], "decimal": a["over"]["decimal"]},
                         "under": {"selectionId": a["under"]["selectionId"], "name": a["under"]["name"], "decimal": a["under"]["decimal"]}} for a in (a1, a2)]}


def cell_runners(cell, code):
    return [{"marketId": m["marketId"], "selectionId": m["over" if d == "O" else "under"]["selectionId"]} for m, d in zip(cell["markets"], code)]


def cell_label(cell, code):
    return " & ".join(f"{m['name']} {m['over' if d == 'O' else 'under']['name']}" + (f" {m['line']}" if m["line"] is not None and "(" not in m["over"]["name"] else "") for m, d in zip(cell["markets"], code))


# %% devig
def devig_cells(decimals, target_index):
    """Four-cell devig: multiplicative, power and additive fair probabilities of the target cell."""
    mult, hold = devig_multiplicative(decimals)
    power, k = devig_power(decimals)
    q = [1 / d for d in decimals]
    additive = [x - (sum(q) - 1) / len(q) for x in q]
    return {"hold": hold, "power_k": k, "p_mult": mult[target_index], "p_power": power[target_index], "p_additive": additive[target_index] if all(0 <= x <= 1 for x in additive) else None}


def attach_ev(rec, cell, prices):
    """prices: {cell code: decimal}; fills rec['devig'] with fair probabilities, EVs and the bound the relation allows."""
    decs = [prices[c] for c in CELLS]
    i = CELLS.index(cell["target"])
    d = devig_cells(decs, i)
    stack = (rec.get("stack_quote") or {}).get("decimal")
    base = (rec.get("base_quote") or {}).get("decimal")
    d.update(relation=cell["relation"], target=cell["target"], fd_cells={c: american(prices[c]) for c in CELLS},
             bound={"subset": "lower bound", "exact": "estimate", "superset": "upper bound"}.get(cell["relation"], "approximate (nearest lines)"))
    if stack:
        d.update(stack_ev_power=ev_of(stack, d["p_power"]), stack_ev_mult=ev_of(stack, d["p_mult"]), stack_ev_additive=ev_of(stack, d["p_additive"]) if d["p_additive"] is not None else None)
    if base:
        d["base_ev_power"] = ev_of(base, d["p_power"])
    rec["devig"] = d
    return d


def partition_ev(row, part):
    """Manual path: {"lines": {var: line}, "OO": american, ..., "target": "OU"}; kept for prices read from the site."""
    prices = {c: (1 + float(part[c]) / 100 if float(part[c]) > 0 else 1 + 100 / -float(part[c])) for c in CELLS}
    preds = []
    for a, d in zip(row["base"], part.get("target", "OU")):
        line = part["lines"].get(a["var"])
        preds.append(fd_atom_pred({"var": a["var"], "line": line}, d) if (line is not None or a["var"] == "result") else atom_pred(a))
    cell = {"relation": cell_relation(row, preds), "target": part.get("target", "OU")}
    rec = dict(row)
    return attach_ev(rec, cell, prices)


# %% main
def load_rows(path):
    files = [path] if path else sorted(glob.glob(str(ROOT / "data/live/thescore-sgp-conjunctions/*.jsonl")))
    return [json.loads(l) for f in files for l in open(f) if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="", help="conjunction JSONL (default: every file under data/live/thescore-sgp-conjunctions)")
    ap.add_argument("--fetch", action="store_true", help="quote the four FanDuel cells of every instance")
    ap.add_argument("--partitions", default="", help="JSON of FanDuel four-cell prices keyed by instance id (manual path)")
    ap.add_argument("--min-uplift", type=float, default=0.005)
    ap.add_argument("--per-var", type=int, default=5, help="FanDuel lines kept per variable, nearest the base threshold")
    ap.add_argument("--sleep", type=float, default=0.4, help="pause between FanDuel quote calls")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    rows = load_rows(args.rows)
    inst = [r for r in rows if (r.get("stack_quote") or {}).get("decimal") and (r.get("uplift") or 0) > args.min_uplift]
    inst.sort(key=lambda r: -r["uplift"])
    parts = json.load(open(args.partitions)) if args.partitions else {}
    print(f"{len(rows)} constructions, {len(inst)} uplifted instances, {len(parts)} manual partitions")

    fd_events, fd_two_way, fd_names = {}, {}, {}
    host_blocked = None
    out = []
    t0 = time.time()
    for n, r in enumerate(inst, 1):
        iid = instance_id(r)
        rec = dict(r, instance_id=iid, capped=(r["stack_quote"].get("formatted") == CAP_STACK or (r.get("base_quote") or {}).get("formatted") == CAP_BASE))
        sport = r["sport"]
        if sport not in fd_events:
            try:
                fd_events[sport] = fd.sport_events(sport)
            except fd.FanDuelError as e:
                print(f"  FanDuel {sport} front page: {e}")
                fd_events[sport] = []
        fe = dv.match_event(r, fd_events[sport])
        rec["fd_event"] = fe["name"] if fe else None
        rec["fd_cell"] = None
        rec["fd_status"] = "no FanDuel fixture"
        if fe:
            if fe["id"] not in fd_two_way:
                try:
                    fd_two_way[fe["id"]] = fd.two_way_markets(fd.event_markets(fe["id"]), fe)
                except fd.FanDuelError as e:
                    print(f"  FanDuel event {fe['id']}: {e}")
                    fd_two_way[fe["id"]] = []
            cell = best_cell(r, fd_two_way[fe["id"]], args.per_var)
            rec["fd_cell"] = cell
            if cell is None:
                mine = (lambda t: t["player"] is None) if r.get("player") is None else (lambda t: bool(t["player"]) and same_person(t["player"], r["player"]))
                have = sorted({(t["var"], t["line"]) for t in fd_two_way[fe["id"]] if mine(t)}, key=str)
                rec["fd_status"] = "no FanDuel two-way pair for the base variables"
                rec["fd_two_way_available"] = [f"{v} {l}" for v, l in have][:20]
            else:
                rec["fd_status"] = f"partition found ({cell['relation']})"
                rec["fd_cells"] = {c: cell_label(cell, c) for c in CELLS}
                if iid in parts:
                    attach_ev(rec, cell, {c: (1 + float(parts[iid][c]) / 100 if float(parts[iid][c]) > 0 else 1 + 100 / -float(parts[iid][c])) for c in CELLS})
                    rec["fd_status"] = "quoted (manual)"
                elif args.fetch and host_blocked is None:
                    prices, statuses = {}, {}
                    for c in CELLS:
                        try:
                            q = fd.quote(cell_runners(cell, c))
                        except fd.HostBlocked as e:
                            host_blocked = str(e)
                            break
                        except fd.FanDuelError as e:
                            statuses[c] = f"error: {e}"[:160]
                            continue
                        statuses[c] = q["status"] if q["status"] == "quoted" else f"{q['status']}: {[f['code'] for f in q['failures']]}"
                        if q["decimal"]:
                            prices[c] = q["decimal"]
                        time.sleep(args.sleep)
                    rec["fd_quote_status"] = statuses
                    if len(prices) == 4:
                        attach_ev(rec, cell, prices)
                        rec["fd_status"] = "quoted"
                    elif host_blocked:
                        rec["fd_status"] = "host_blocked"
                    else:
                        rec["fd_status"] = "FanDuel refused or failed a cell"
                elif args.fetch:
                    rec["fd_status"] = "host_blocked"
        out.append(rec)
        if n % 25 == 0:
            print(f"  {n}/{len(inst)} instances, {time.time() - t0:.0f}s")

    def sort_key(o):
        d = o.get("devig") or {}
        e = d.get("stack_ev_power")
        return (0 if e is not None and not o["capped"] else 1, -(e if e is not None else -9), RELATION_RANK.get((o.get("fd_cell") or {}).get("relation"), 9), -o["uplift"])
    out.sort(key=sort_key)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quoted = [o for o in out if o.get("devig")]
    summary = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fd_region": fd.REGION, "quote_host": fd.sib().split("/api")[0], "host_blocked": host_blocked,
               "constructions": len(rows), "instances": len(inst), "capped": sum(1 for o in out if o["capped"]),
               "fd_fixture_matched": sum(1 for o in out if o.get("fd_event")), "fd_partition_found": sum(1 for o in out if o.get("fd_cell")),
               "fd_partition_by_relation": {k: sum(1 for o in out if (o.get("fd_cell") or {}).get("relation") == k) for k in RELATION_RANK},
               "quoted": len(quoted), "positive_ev_power": sum(1 for o in quoted if (o["devig"].get("stack_ev_power") or 0) > 0 and not o["capped"]),
               "positive_lower_bounds": sum(1 for o in quoted if o["devig"]["relation"] in ("subset", "exact") and (o["devig"].get("stack_ev_power") or 0) > 0 and not o["capped"]),
               "instances_ranked": [slim(o) for o in out]}
    suffix = f"-{args.tag}" if args.tag else ""
    rp = REPORTS / f"thescore-sgp-conjunctions-fanduel-devig-{stamp}{suffix}.json"
    rp.write_text(json.dumps(summary, indent=1, default=str))
    (REPORTS / f"thescore-sgp-conjunctions-fanduel-devig-{stamp}{suffix}.md").write_text(markdown(summary))
    print(f"wrote {rp.relative_to(ROOT)}: {summary['fd_fixture_matched']} with a FanDuel fixture, {summary['fd_partition_found']} with a partition "
          f"{summary['fd_partition_by_relation']}, {len(quoted)} quoted, {summary['positive_ev_power']} positive EV" + (f"; quote host blocked: {host_blocked}" if host_blocked else ""))


def slim(o):
    keep = ("instance_id", "sport", "competition", "event", "start", "player", "space", "capped", "fd_event", "fd_status", "fd_cell", "fd_cells", "fd_quote_status", "fd_two_way_available", "devig")
    d = {k: o.get(k) for k in keep if k in o}
    d["base"] = [{"market": a["market"], "selection": a["selection"], "price": a["price"], "var": a["var"], "op": a["op"], "threshold": a["threshold"]} for a in o["base"]]
    d["stack"] = [{"market": a["market"], "selection": a["selection"], "price": a["price"]} for a in o["stack"]]
    d["base_quote"] = o["base_quote"].get("formatted")
    d["stack_quote"] = o["stack_quote"].get("formatted")
    d["stack_decimal"] = o["stack_quote"].get("decimal")
    d["multiplier"] = o["stack_quote"]["decimal"] / o["base_quote"]["decimal"] if o.get("base_quote", {}).get("decimal") else None
    return d


def markdown(s):
    L = [f"# theScore conjunction instances devigged against FanDuel ({s['generated'][:10]})", "",
         f"FanDuel board: {s['fd_region'].upper()}. Quote host: `{s['quote_host']}`" + (f" — **blocked by this container's network policy** (`{s['host_blocked']}`); no cell was priced." if s["host_blocked"] else "."), "",
         f"- {s['instances']} instances ({s['capped']} at theScore's display caps, excluded from the EV ranking)",
         f"- {s['fd_fixture_matched']} matched to a FanDuel fixture; {s['fd_partition_found']} have a FanDuel two-way partition for the base: {s['fd_partition_by_relation']}",
         f"- {s['quoted']} quoted on FanDuel; {s['positive_ev_power']} positive EV (power devig), {s['positive_lower_bounds']} of them lower bounds (subset or exact cells)", ""]
    quoted = [o for o in s["instances_ranked"] if o.get("devig")]
    if quoted:
        L += ["## Ranked by EV of theScore's stacked price (power devig of FanDuel's four cells)", "",
              "| # | EV (power) | EV (mult) | bound | event | player | base | theScore stack | FanDuel cell | FD cells OO/OU/UO/UU | p (power) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for i, o in enumerate(quoted, 1):
            d = o["devig"]
            base = "; ".join(f"{a['market']} {a['selection']} ({a['price']})" for a in o["base"])
            cells = "/".join(str(d["fd_cells"][c]) for c in CELLS)
            L.append(f"| {i} | {d['stack_ev_power']:+.1%} | {d['stack_ev_mult']:+.1%} | {d['bound']} | {o['event']} ({o['competition']}) | {o.get('player') or '—'} | {base} | {o['stack_quote']}"
                     f"{' (capped)' if o['capped'] else ''} | {o['fd_cells'][d['target']]} | {cells} | {d['p_power']:.4f} |")
        L.append("")
    rest = [o for o in s["instances_ranked"] if not o.get("devig")]
    if rest:
        L += ["## Instances without a FanDuel quote", "", "| # | status | relation | event | player | base | theScore base → stack | FanDuel cell to quote |", "|---|---|---|---|---|---|---|---|"]
        for i, o in enumerate(rest, 1):
            base = "; ".join(f"{a['market']} {a['selection']} ({a['price']})" for a in o["base"])
            cell = o.get("fd_cell") or {}
            L.append(f"| {i} | {o['fd_status']} | {cell.get('relation') or '—'} | {o['event']} ({o['competition']}) | {o.get('player') or '—'} | {base} | {o['base_quote']} → {o['stack_quote']}"
                     f"{' (capped)' if o['capped'] else ''} | {(o.get('fd_cells') or {}).get(cell.get('target'), '—') if cell else '—'} |")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
