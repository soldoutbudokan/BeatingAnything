#!/usr/bin/env python3
"""PointsBet NFL alternate-spread / alternate-total ladder audit against Pinnacle and historical margins.

Reads only the pinned September 28-29, 2026 captures in data/raw/pointsbet-nfl-alt-2026-09-28/
(PointsBet AU public event API; OddsPapi Pinnacle response) plus the pinned nflverse games.csv already
held under data/raw/nfl-teaser-review-2026-09-26/. No network, wagers, alerts or schedules.

PointsBet has no fixed-price teaser product: a "teaser" there is a parlay of Pick Your Own Line
alternates, so the per-leg alternate price is the teaser-leg price under test.

python tools/audit_pointsbet_nfl_alternates.py
"""
import json
import math
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/pointsbet-nfl-alt-2026-09-28"
GAMES = ROOT / "data/raw/nfl-teaser-review-2026-09-26/games.csv"
OUT_JSON = ROOT / "reports/pointsbet-nfl-alternate-audit-2026-09-28.json"
EMP_FROM_SEASON = 2010
EMP_TOL = 0.5            # closing-line bucket half-width for the empirical benchmark
PIN_FRESH_HOURS = 1.0    # Pinnacle alternate rung must be at most this much older than the game's freshest Pinnacle update
SPREAD_MARKETS = {"Point Spread", "Pick Your Own Line"}
TOTAL_MARKETS = {"Total", "Alternate Totals"}


def load_pointsbet():
    rows = []
    for f in sorted(p for p in (RAW / "pointsbet-au").glob("*.json") if p.name != "nfl_events.json"):
        d = json.load(open(f))
        for m in d["fixedOddsMarkets"]:
            nm = m.get("eventName", "").strip()
            if nm not in SPREAD_MARKETS | TOTAL_MARKETS | {"Moneyline"}:
                continue
            for o in m["outcomes"] + m.get("hiddenOutcomes", []):
                rows.append(dict(event=d["key"], home=d["homeTeam"], away=d["awayTeam"], start=d["startsAt"], isLive=d["isLive"],
                                 market=nm, team=o["name"], side=o["side"], points=float(o["points"]), price=float(o["price"]),
                                 open=bool(o["isOpenForBetting"]), hidden=bool(o["isHidden"]), updated=o.get("priceLastUpdated")))
    return pd.DataFrame(rows)


def load_pinnacle():
    cat = {int(k): v for k, v in json.load(open(RAW / "oddspapi/markets-sport14.json")).items()}
    d = json.load(open(RAW / "oddspapi/odds_pinnacle.json"))
    rows = []
    for ev in d:
        bo = ev["bookmakerOdds"].get("pinnacle")
        if not bo:
            continue
        for mid, mk in bo["markets"].items():
            c = cat.get(int(mid), {})
            if c.get("period") != "result" or c.get("marketType") not in ("spreads", "totals", "moneyline"):
                continue
            names = {str(y["outcomeId"]): y["outcomeName"] for y in c.get("outcomes", [])}
            for oid, o in mk["outcomes"].items():
                for pk, p in o["players"].items():
                    rows.append(dict(p1=ev["participant1Name"], p2=ev["participant2Name"], marketType=c["marketType"], handicap=float(c["handicap"]),
                                     outcome=names.get(oid), price=float(p["price"]), active=bool(p["active"]), mainLine=bool(p["mainLine"]),
                                     changedAt=datetime.fromisoformat(p["changedAt"].replace("Z", "+00:00")).timestamp()))  # epoch seconds; tz-aware pandas Timestamps segfault under Python 3.14
    return pd.DataFrame(rows)


def wilson_half(p, n):
    return 1.96 * math.sqrt(p * (1 - p) / n) if n else float("nan")


def main():
    pb = load_pointsbet()
    pin = load_pinnacle()
    games = pd.read_csv(GAMES)
    live = sorted(pb[pb.isLive].event.unique())
    pb = pb[~pb.isLive].copy()
    pb["updated"] = pb.updated.fillna("")

    # ---- empirical legs (team view: line = points the team receives; margin = team margin) ----
    g = games[games.result.notna() & games.spread_line.notna() & (games.season >= EMP_FROM_SEASON)]
    legs = pd.concat([
        pd.DataFrame(dict(season=g.season, line=-g.spread_line, margin=g.result)),
        pd.DataFrame(dict(season=g.season, line=g.spread_line, margin=-g.result))], ignore_index=True)

    def emp_cover(s, L):
        sub = legs[(legs.line - s).abs() <= EMP_TOL]
        x = np.sign(sub.margin.values + L)
        w, l = int((x > 0).sum()), int((x < 0).sum())
        n = w + l
        return (w / n if n else np.nan), n

    def emp_mass(s, n_margin):
        sub = legs[(legs.line - s).abs() <= EMP_TOL]
        return float((sub.margin == n_margin).mean()) if len(sub) else np.nan

    # ---- Pinnacle freshness + team-view no-vig spreads ----
    fresh_cut = pin.groupby("p1").changedAt.max() - 3600 * PIN_FRESH_HOURS
    pin["fresh"] = pin.changedAt >= pin.p1.map(fresh_cut)
    stale_pin_lines = int((~pin.fresh).sum())
    pin = pin[pin.fresh & pin.active]
    prow = []
    for (p1, h), grp in pin[pin.marketType == "spreads"].groupby(["p1", "handicap"]):
        d = dict(zip(grp.outcome, grp.price))
        if "1" not in d or "2" not in d:
            continue
        q1, q2 = 1 / d["1"], 1 / d["2"]
        prow.append(dict(home=p1, side="Home", line=h, pin_price=d["1"], pin_fair=q1 / (q1 + q2), pin_over=q1 + q2, main=bool(grp.mainLine.any())))
        prow.append(dict(home=p1, side="Away", line=-h, pin_price=d["2"], pin_fair=q2 / (q1 + q2), pin_over=q1 + q2, main=bool(grp.mainLine.any())))
    pin_sp = pd.DataFrame(prow)
    pin_main = pin_sp[pin_sp.main].groupby(["home", "side"]).line.first()
    trow = []
    for (p1, h), grp in pin[pin.marketType == "totals"].groupby(["p1", "handicap"]):
        d = dict(zip(grp.outcome, grp.price))
        if "Over" not in d or "Under" not in d:
            continue
        o, u = 1 / d["Over"], 1 / d["Under"]
        trow.append(dict(home=p1, points=h, pin_over_price=d["Over"], pin_under_price=d["Under"], pin_p_over=o / (o + u), pin_tot_over=o + u))
    pin_t = pd.DataFrame(trow)

    # ---- PointsBet spreads ----
    sp = pb[pb.market.isin(SPREAD_MARKETS) & pb.open & ~pb.hidden].copy()
    sp["line"] = sp.points
    sp["q"] = 1 / sp.price
    opp = sp[["home", "side", "line", "price"]].rename(columns={"price": "opp_price"})
    opp["side"] = opp.side.map({"Home": "Away", "Away": "Home"})
    opp["line"] = -opp.line
    sp = sp.merge(opp.drop_duplicates(["home", "side", "line"]), on=["home", "side", "line"], how="left")
    sp["pb_over"] = sp.q + 1 / sp.opp_price
    sp["pb_fair"] = sp.q / sp.pb_over
    sp = sp.merge(pin_sp[["home", "side", "line", "pin_price", "pin_fair", "pin_over"]], on=["home", "side", "line"], how="left")
    pb_main = sp[sp.market == "Point Spread"].groupby(["home", "side"]).line.first()
    sp["pb_main"] = [pb_main.get((h, s), np.nan) for h, s in zip(sp.home, sp.side)]
    sp["pin_main"] = [pin_main.get((h, s), np.nan) for h, s in zip(sp.home, sp.side)]
    sp["main_src"] = np.where(sp.pin_main.notna(), "pinnacle", "pointsbet")
    sp["anchor"] = sp.pin_main.fillna(sp.pb_main)
    sp["offset"] = sp.line - sp.anchor
    sp["ev_vs_pin"] = sp.price * sp.pin_fair - 1
    ec = [emp_cover(s, L) for s, L in zip(sp.anchor, sp.line)]
    sp["emp_p"] = [e[0] for e in ec]
    sp["emp_n"] = [e[1] for e in ec]
    sp["ev_vs_emp"] = sp.price * sp.emp_p - 1
    sp = sp.drop_duplicates(["home", "side", "line", "price"])

    out = dict(
        inputs=dict(raw_dir=str(RAW.relative_to(ROOT)), games_csv=str(GAMES.relative_to(ROOT)), empirical_from_season=EMP_FROM_SEASON,
                    empirical_bucket_half_width=EMP_TOL, pinnacle_freshness_hours=PIN_FRESH_HOURS, live_events_excluded=live,
                    pointsbet_pregame_games=int(pb.home.nunique()), pinnacle_games_with_result_markets=int(pin.p1.nunique()),
                    pinnacle_stale_rungs_dropped=stale_pin_lines),
    )

    # 1. main-line agreement
    ml = pb[pb.market == "Moneyline"].pivot_table(index="home", columns="side", values="price", aggfunc="first")
    pm = pin[pin.marketType == "moneyline"].pivot_table(index="p1", columns="outcome", values="price", aggfunc="first")
    j = ml.join(pm, how="left")
    j["pb_p_home"] = (1 / j.Home) / (1 / j.Home + 1 / j.Away)
    j["pin_p_home"] = (1 / j["1"]) / (1 / j["1"] + 1 / j["2"])
    j["pb_main_home"] = [pb_main.get((h, "Home"), np.nan) for h in j.index]
    j["pin_main_home"] = [pin_main.get((h, "Home"), np.nan) for h in j.index]
    out["main_lines"] = j.reset_index().rename(columns={"Home": "pb_ml_home", "Away": "pb_ml_away", "1": "pin_ml_home", "2": "pin_ml_away"}).round(4).to_dict("records")
    out["moneyline_no_vig_gap_abs_mean"] = float((j.pb_p_home - j.pin_p_home).abs().mean())

    # 2. ladder vs Pinnacle
    m = sp[sp.pin_fair.notna()]
    out["spreads_vs_pinnacle"] = dict(
        matched_lines=int(len(m)), games=int(m.home.nunique()), mean_ev=float(m.ev_vs_pin.mean()), median_ev=float(m.ev_vs_pin.median()),
        n_positive=int((m.ev_vs_pin > 0).sum()), max_ev=float(m.ev_vs_pin.max()),
        mean_pb_two_sided_overround=float(sp.pb_over.mean()), mean_pin_overround=float(pin_sp.pin_over.mean()),
        by_offset=m.assign(off=m.offset.round()).groupby("off").agg(n=("ev_vs_pin", "size"), mean_ev=("ev_vs_pin", "mean")).reset_index().round(4).to_dict("records"),
        buy_points=dict(n=int((m.offset > 0).sum()), mean_ev=float(m[m.offset > 0].ev_vs_pin.mean())),
        sell_points=dict(n=int((m.offset < 0).sum()), mean_ev=float(m[m.offset < 0].ev_vs_pin.mean())),
        top=m.sort_values("ev_vs_pin", ascending=False).head(8)[["home", "away", "team", "line", "price", "pin_price", "pin_fair", "ev_vs_pin", "offset"]].round(4).to_dict("records"))

    # 3. ladder vs empirical
    e = sp[sp.emp_p.notna()]
    out["spreads_vs_empirical"] = dict(
        lines=int(len(e)), games=int(e.home.nunique()), mean_ev=float(e.ev_vs_emp.mean()),
        buy_points=dict(n=int((e.offset > 0).sum()), mean_ev=float(e[e.offset > 0].ev_vs_emp.mean())),
        sell_points=dict(n=int((e.offset < 0).sum()), mean_ev=float(e[e.offset < 0].ev_vs_emp.mean())),
        by_offset=e.assign(off=e.offset.round()).groupby("off").agg(n=("ev_vs_emp", "size"), mean_ev=("ev_vs_emp", "mean")).reset_index().round(4).to_dict("records"),
        caveat="Benchmark conditions on the closing-line bucket only, not on the total or the matchup; single-game values are noisy, aggregates are informative.")

    # 4. Wong-teased legs: anchor in [-8.5,-7.5] or [1.5,2.5], six points bought
    w = sp[(sp.anchor.between(-8.5, -7.5) | sp.anchor.between(1.5, 2.5)) & sp.offset.between(5.5, 6.5)].copy()
    hist = legs[(legs.line.between(-8.5, -7.5) | legs.line.between(1.5, 2.5))]
    x = np.sign(hist.margin.values + hist.line.values + 6)
    wong_p, wong_n = float((x > 0).sum() / ((x > 0).sum() + (x < 0).sum())), int(((x > 0) | (x < 0)).sum())
    parlay2 = float(w.price.prod() ** (2 / len(w))) if len(w) else None  # geometric-mean two-leg price
    out["wong_legs"] = dict(
        legs=w[["home", "away", "team", "anchor", "main_src", "line", "price", "pb_fair", "pin_price", "pin_fair", "emp_p", "emp_n", "ev_vs_pin", "ev_vs_emp", "updated"]].round(4).to_dict("records"),
        n=int(len(w)), mean_price=float(w.price.mean()) if len(w) else None, mean_pb_no_vig=float(w.pb_fair.mean()) if len(w) else None,
        mean_pin_fair=float(w.pin_fair.mean()) if w.pin_fair.notna().any() else None,
        historical_wong_leg_win_rate=dict(p=wong_p, n=wong_n, ci95_half=wilson_half(wong_p, wong_n), seasons=f"{EMP_FROM_SEASON}-2026 to date"),
        mean_ev_vs_bucket_empirical=float(w.ev_vs_emp.mean()) if len(w) else None,
        mean_ev_vs_pinnacle=float(w.ev_vs_pin.mean()) if w.ev_vs_pin.notna().any() else None,
        two_leg_parlay_price_geomean=parlay2,
        two_leg_parlay_ev_at_historical_rate=(parlay2 * wong_p ** 2 - 1) if parlay2 else None,
        fixed_chart_reference=dict(minus_135_ev_at_historical_rate=(100 / 135 + 1) * wong_p ** 2 - 1, minus_120_ev_at_historical_rate=(100 / 120 + 1) * wong_p ** 2 - 1))

    # 5. key-number step mass
    steps = []
    for (h, side), grp in sp[sp.pb_fair.notna()].groupby(["home", "side"]):
        fair = dict(zip(grp.line, grp.pb_fair))
        pf = dict(zip(grp.line, grp.pin_fair))
        s = grp.anchor.iloc[0]
        for L in grp.line:
            if abs(L - round(L)) == 0.5 and (L + 1) in fair:
                n = int(L + 0.5)  # team loses by n
                steps.append(dict(home=h, side=side, anchor=s, lose_by=n, pb_mass=fair[L + 1] - fair[L], pin_mass=pf.get(L + 1, np.nan) - pf.get(L, np.nan), emp_mass=emp_mass(s, -n)))
    st = pd.DataFrame(steps)
    st["m"] = st.lose_by.abs()
    bym = st.groupby("m").agg(n=("pb_mass", "size"), pb=("pb_mass", "mean"), pin=("pin_mass", "mean"), pin_n=("pin_mass", "count"), emp=("emp_mass", "mean")).reset_index()
    k3, k7 = st[st.m == 3], st[st.m == 7]
    out["key_number_mass"] = dict(
        by_margin=bym[bym.m <= 14].round(4).to_dict("records"),
        margin3=dict(n=int(len(k3)), pb=float(k3.pb_mass.mean()), emp=float(k3.emp_mass.mean()), pin=float(k3.pin_mass.mean()), pin_n=int(k3.pin_mass.count()),
                     share_pb_below_emp=float((k3.pb_mass < k3.emp_mass).mean()), gap_min=float((k3.pb_mass - k3.emp_mass).min()), gap_max=float((k3.pb_mass - k3.emp_mass).max())),
        margin7=dict(n=int(len(k7)), pb=float(k7.pb_mass.mean()), emp=float(k7.emp_mass.mean()), pin=float(k7.pin_mass.mean()), pin_n=int(k7.pin_mass.count()),
                     share_pb_below_emp=float((k7.pb_mass < k7.emp_mass).mean())),
        note="Mass is the no-vig two-sided PointsBet cover probability difference between adjacent half-point rungs; empirical mass conditions on the closing-line bucket.")

    # 6. alternate totals vs Pinnacle
    tt = pb[pb.market.isin(TOTAL_MARKETS) & pb.open & ~pb.hidden].copy()
    tt["ou"] = np.where(tt.team.str.startswith("Over"), "Over", "Under")
    piv = tt.pivot_table(index=["home", "away", "points"], columns="ou", values="price", aggfunc="first").reset_index().merge(pin_t, on=["home", "points"], how="inner")
    piv["ev_over"] = piv.Over * piv.pin_p_over - 1
    piv["ev_under"] = piv.Under * (1 - piv.pin_p_over) - 1
    piv["pb_tot_over"] = 1 / piv.Over + 1 / piv.Under
    evs = pd.concat([piv.ev_over, piv.ev_under])
    top_t = pd.concat([piv.assign(side="Over", price=piv.Over, pin_price=piv.pin_over_price, ev=piv.ev_over),
                       piv.assign(side="Under", price=piv.Under, pin_price=piv.pin_under_price, ev=piv.ev_under)])
    out["totals_vs_pinnacle"] = dict(matched_lines=int(len(piv)), games=int(piv.home.nunique()), mean_ev=float(evs.mean()), n_positive=int((evs > 0).sum()), max_ev=float(evs.max()),
                                     mean_pb_overround=float(piv.pb_tot_over.mean()), mean_pin_overround=float(piv.pin_tot_over.mean()),
                                     top=top_t.sort_values("ev", ascending=False).head(6)[["home", "away", "points", "side", "price", "pin_price", "ev"]].round(4).to_dict("records"))

    OUT_JSON.write_text(json.dumps(out, indent=1, default=str))
    pd.set_option("display.width", 250)
    print(json.dumps(out["inputs"], indent=1))
    print("moneyline no-vig |gap| mean:", round(out["moneyline_no_vig_gap_abs_mean"], 4))
    print("spreads vs pinnacle:", {k: v for k, v in out["spreads_vs_pinnacle"].items() if k not in ("by_offset", "top")})
    print("spreads vs empirical:", {k: v for k, v in out["spreads_vs_empirical"].items() if k not in ("by_offset",)})
    print("wong:", {k: v for k, v in out["wong_legs"].items() if k != "legs"})
    print(pd.DataFrame(out["wong_legs"]["legs"]).to_string())
    print("key numbers:", out["key_number_mass"]["margin3"], out["key_number_mass"]["margin7"])
    print(pd.DataFrame(out["key_number_mass"]["by_margin"]).to_string())
    print("totals vs pinnacle:", {k: v for k, v in out["totals_vs_pinnacle"].items() if k != "top"})
    print(pd.DataFrame(out["totals_vs_pinnacle"]["top"]).to_string())
    print(pd.DataFrame(out["spreads_vs_pinnacle"]["top"]).to_string())
    print("wrote", OUT_JSON.relative_to(ROOT))


if __name__ == "__main__":
    main()
