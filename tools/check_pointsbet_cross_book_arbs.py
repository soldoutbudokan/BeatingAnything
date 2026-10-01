#!/usr/bin/env python3
"""Two-book arb check: PointsBet (TBS engine, AU public API) alternates against Pinnacle / FanDuel via OddsPapi.

Reads only pinned captures. Reports pairs where 1/PointsBet + 1/other opposite side < 1, with PointsBet rung age.
The OddsPapi FanDuel NFL feed mixes markets from different fixtures (several full-game "main" spreads and
moneylines per fixture), so its pairs are reported but flagged unusable. No network, wagers, alerts or schedules.

python tools/check_pointsbet_cross_book_arbs.py [capture_dir]
"""
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "data/raw/pointsbet-nfl-alt-2026-09-29-sim")
CATALOG = ROOT / "data/raw/pointsbet-nfl-alt-2026-09-28/oddspapi/markets-sport14.json"
OUT = ROOT / "reports/pointsbet-cross-book-arb-check-2026-09-29.json"


def ts(s):
    if not s:
        return float("nan")
    s = s.replace("Z", "")
    if "." in s:
        a, b = s.split(".")
        s = f"{a}.{b[:6]}"
    return datetime.fromisoformat(s + "+00:00").timestamp()


def load_pointsbet():
    rows = []
    for f in glob.glob(str(RAW / "pointsbet-au/*.json")):
        try:
            d = json.load(open(f))
        except json.JSONDecodeError:
            continue
        if "fixedOddsMarkets" not in d or d["isLive"] or f.endswith("_refetch.json"):
            continue
        for m in d["fixedOddsMarkets"]:
            nm = m.get("eventName", "").strip()
            kind = {"Moneyline": "moneyline", "Point Spread": "spreads", "Pick Your Own Line": "spreads", "Total": "totals", "Alternate Totals": "totals"}.get(nm)
            if not kind:
                continue
            for o in m["outcomes"]:
                if o["isHidden"] or not o["isOpenForBetting"]:
                    continue
                rows.append(dict(home=d["homeTeam"], mt=kind, side=o["side"], line=float(o["points"]), price=float(o["price"]), team=o["name"],
                                 ou=("Over" if o["name"].startswith("Over") else "Under" if o["name"].startswith("Under") else None), upd=ts(o.get("priceLastUpdated"))))
    return pd.DataFrame(rows)


def load_other(book, cat):
    rows = []
    for ev in json.load(open(RAW / f"oddspapi/odds_{book}.json")):
        bo = ev["bookmakerOdds"].get(book)
        if not bo or ev["statusName"] != "Pre-Game":
            continue
        for mid, mk in bo["markets"].items():
            c = cat.get(int(mid), {})
            if c.get("period") != "result" or c.get("marketType") not in ("spreads", "totals", "moneyline"):
                continue
            names = {str(y["outcomeId"]): y["outcomeName"] for y in c.get("outcomes", [])}
            for oid, o in mk["outcomes"].items():
                for p in o["players"].values():
                    if p["active"]:
                        rows.append(dict(home=ev["participant1Name"], mt=c["marketType"], h=float(c["handicap"]), out=names.get(oid), price=float(p["price"]), changed=ts(p["changedAt"])))
    return pd.DataFrame(rows)


def main():
    cat = {int(k): v for k, v in json.load(open(CATALOG)).items()}
    pb = load_pointsbet()
    cap = ts(open(RAW / "finished.time").read().strip())
    pb["age_h"] = (cap - pb.upd) / 3600
    out = dict(capture_dir=str(RAW.relative_to(ROOT)), pointsbet_games=int(pb.home.nunique()),
               pointsbet_rung_age_hours=dict(median=float(pb.age_h.median()), p90=float(pb.age_h.quantile(0.9)), max=float(pb.age_h.max())), books={})
    for book in ("pinnacle", "fanduel"):
        ob = load_other(book, cat)
        ob = ob[ob.home.isin(pb.home.unique())]
        dup = ob[ob.mt == "moneyline"].groupby("home").size()
        s, t = ob[ob.mt == "spreads"], ob[ob.mt == "totals"]
        res = []
        for r in pb[pb.mt == "spreads"].itertuples():
            opp = s[(s.home == r.home) & (s.h == r.line) & (s.out == "2")] if r.side == "Home" else s[(s.home == r.home) & (s.h == -r.line) & (s.out == "1")]
            for o in opp.itertuples():
                res.append(dict(home=r.home, leg=r.team, pb=r.price, other=o.price, inv_sum=1 / r.price + 1 / o.price, pb_age_h=r.age_h, other_age_h=(cap - o.changed) / 3600))
        for r in pb[pb.mt == "totals"].itertuples():
            opp = t[(t.home == r.home) & (t.h == r.line) & (t.out == ("Under" if r.ou == "Over" else "Over"))]
            for o in opp.itertuples():
                res.append(dict(home=r.home, leg=f"{r.ou} {r.line}", pb=r.price, other=o.price, inv_sum=1 / r.price + 1 / o.price, pb_age_h=r.age_h, other_age_h=(cap - o.changed) / 3600))
        R = pd.DataFrame(res).sort_values("inv_sum")
        out["books"][book] = dict(
            games=int(ob.home.nunique()), pairs=int(len(R)), arbs=int((R.inv_sum < 1).sum()), within_1pct=int((R.inv_sum < 1.01).sum()), within_2pct=int((R.inv_sum < 1.02).sum()),
            median_inv_sum=float(R.inv_sum.median()), other_rows_per_fixture_moneyline_max=int(dup.max()) if len(dup) else None,
            feed_usable=bool(book == "pinnacle"), arb_rows=R[R.inv_sum < 1].round(4).to_dict("records"), best=R.head(10).round(4).to_dict("records"))
        print(f"{book}: games {ob.home.nunique()} pairs {len(R)} arbs {(R.inv_sum < 1).sum()} within1% {(R.inv_sum < 1.01).sum()} within2% {(R.inv_sum < 1.02).sum()} median {R.inv_sum.median():.4f}")
        print(R.head(8).round(4).to_string(index=False))
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
