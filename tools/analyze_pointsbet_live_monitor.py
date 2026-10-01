#!/usr/bin/env python3
"""Attribute live PointsBet arbs (from collect_pointsbet_live_alternates.py) to the book that deviates from Pinnacle.

For the latest snapshot: Pinnacle two-sided no-vig fair at every quoted line; EV of each PointsBet and FanDuel rung;
per-arb attribution (which leg is +EV against Pinnacle); PointsBet main-line distance from Pinnacle with rung age.
Read-only over data/live/pointsbet-alt-monitor/.

python tools/analyze_pointsbet_live_monitor.py [--all-cycles]
"""
import argparse
import glob
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
MON = ROOT / "data/live/pointsbet-alt-monitor"
pd.set_option("display.width", 240)


def load_snapshot(path):
    s = pd.DataFrame([json.loads(l) for l in open(path)])
    if "period" in s.columns:  # the collector now also records halves / quarters / periods, team totals and player props
        s = s[(s.period == 0) & s.kind.isin(["spread", "total", "moneyline"])].copy()
    s["game"] = s.away + " @ " + s.home
    return s


def book_names(s):
    """Region-suffixed PointsBet / FanDuel book names present in a snapshot (on from a Canadian connection, au/nj from the cloud)."""
    books = set(s.book)
    pb = next((b for b in books if b.startswith("pointsbet")), "pointsbet_on")
    fd = next((b for b in books if b.startswith("fanduel")), "fanduel_on")
    return pb, fd


def attach_pinnacle_fair(s):
    pin = s[(s.book == "pinnacle") & s.kind.isin(["spread", "total"])]
    price = {(r.game, r.kind, r.team, r.line): r.price for r in pin.itertuples()}
    homes = dict(zip(s.game, s.home))
    aways = dict(zip(s.game, s.away))

    def fair(game, kind, team, line):
        p = price.get((game, kind, team, line))
        if kind == "total":
            o = ("Under" if team == "Over" else "Over", line)
        else:
            o = (aways[game] if team == homes[game] else homes[game], -line)
        q = price.get((game, kind) + o)
        return np.nan if p is None or q is None else (1 / p) / (1 / p + 1 / q)

    s["pin_fair"] = [fair(r.game, r.kind, r.team, r.line) if r.kind in ("spread", "total") else np.nan for r in s.itertuples()]
    s["ev"] = s.price * s.pin_fair - 1
    return s


def leg_label(kind, team, line):
    return f"{team} {line:+g}" if kind == "spread" else f"{team} {line}"


def analyze(snapshot_path, arbs):
    s = attach_pinnacle_fair(load_snapshot(snapshot_path))
    pb_book, fd_book = book_names(s)
    captured = s.captured.iloc[0]
    a = arbs[arbs.captured == captured].copy()
    print(f"\n=== cycle {captured[:19]}  rows {len(s)}  arbs {len(a)} ===")
    s["leg"] = [leg_label(r.kind, r.team, r.line) if r.kind != "moneyline" else r.team for r in s.itertuples()]
    ev = {(r.book, r.game, r.kind, r.leg): r.ev for r in s.itertuples()}
    if len(a):
        if "period" in a.columns:
            a = a[(a.period == 0) & a.kind.isin(["spread", "total"])].copy()
        a["game"] = a.away + " @ " + a.home
        a["pb_ev_vs_pin"] = [ev.get((pb_book, r.game, r.kind, r.pb_leg), np.nan) for r in a.itertuples()]
        a["other_ev_vs_pin"] = [ev.get((r.other_book, r.game, r.kind, r.other_leg), np.nan) for r in a.itertuples()]
        a["attribution"] = np.where(a.pb_ev_vs_pin > 0, "pointsbet leg +EV", np.where(a.other_ev_vs_pin > 0, "other book leg +EV", "no Pinnacle quote"))
        print(a.sort_values("inv_sum")[["game", "kind", "pb_leg", "pb_price", "pb_age_min", "pb_main", "other_book", "other_leg", "other_price", "inv_sum", "pb_ev_vs_pin", "other_ev_vs_pin", "attribution"]].round(3).to_string(index=False))
        print(a.groupby(["other_book", "attribution"]).size().to_string())
    mains = s[s.main & (s.kind != "moneyline") & ((s.team == "Over") | (s.team == s.home))]
    m = mains.pivot_table(index=["game", "kind"], columns="book", values="line", aggfunc="first")
    age = mains[mains.book == pb_book].set_index(["game", "kind"]).age_min / 60
    m["pb_minus_pin"] = m.get(pb_book) - m.get("pinnacle")
    m["pb_main_age_h"] = age
    m = m.dropna(subset=["pb_minus_pin"])
    print("\nPointsBet main minus Pinnacle main (points), PointsBet main age (hours):")
    print(m[m.pb_minus_pin.abs() >= 1].round(1).to_string())
    print(f"games with PB main >= 1 point from Pinnacle: spreads {int((m.xs('spread', level='kind').pb_minus_pin.abs() >= 1).sum())} / {len(m.xs('spread', level='kind'))}, totals {int((m.xs('total', level='kind').pb_minus_pin.abs() >= 1).sum())} / {len(m.xs('total', level='kind'))}")
    for b in (pb_book, fd_book):
        sub = s[(s.book == b) & (s.kind == "spread") & s.ev.notna() & ~s.main].copy()
        pm = s[(s.book == "pinnacle") & s.main & (s.kind == "spread")].set_index(["game", "team"]).line
        sub["off"] = [r.line - pm.get((r.game, r.team), np.nan) for r in sub.itertuples()]
        print(f"\n{b}: alt-spread rungs with a Pinnacle two-sided quote n={len(sub)} mean EV {sub.ev.mean():+.4f}; buy>=6 n={(sub.off >= 6).sum()} EV {sub[sub.off >= 6].ev.mean():+.4f}; sell>=6 n={(sub.off <= -6).sum()} EV {sub[sub.off <= -6].ev.mean():+.4f}; rungs +EV {(sub.ev > 0).sum()}")
        print(sub.sort_values("ev", ascending=False).head(5)[["game", "team", "line", "price", "pin_fair", "ev", "off"]].round(3).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-cycles", action="store_true")
    args = ap.parse_args()
    arbs = pd.DataFrame([json.loads(l) for l in open(MON / "arbs.jsonl")]) if (MON / "arbs.jsonl").exists() else pd.DataFrame(columns=["captured"])
    snaps = sorted(glob.glob(str(MON / "*/snapshot-*.jsonl")))
    for p in (snaps if args.all_cycles else snaps[-1:]):
        analyze(p, arbs)
    if (MON / "cycles.jsonl").exists():
        c = pd.DataFrame([json.loads(l) for l in open(MON / "cycles.jsonl")])
        print(f"\ncycles logged: {len(c)}; arbs per cycle mean {c.arbs.mean():.1f}; span mean {c.span_s.mean():.0f}s")


if __name__ == "__main__":
    main()
