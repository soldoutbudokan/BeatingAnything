#!/usr/bin/env python3
"""Devig the redundant-leg Parlay+ instances found by tools/screen_thescore_sgp_redundant_legs.py against FanDuel.

For each row where theScore priced A+B above A alone, locate the same fixture on FanDuel (New Jersey feed; FanDuel prices are
near-identical across its jurisdictions), find the FanDuel market that contains leg A, devig that market (multiplicative and
power) to a fair probability for A, and compute EV of theScore's Parlay+ price: sgp_decimal * p_fair - 1.

One-sided FanDuel markets (anytime scorer, alternate ladders without an opposite side) cannot be devigged; those rows carry
FanDuel's raw implied probability and are flagged as an upper bound on EV.

python tools/devig_thescore_sgp_instances.py                                   # latest screen file
python tools/devig_thescore_sgp_instances.py --rows data/live/thescore-sgp-redundant/<stamp>.jsonl --min-improvement 0.01
"""
# %% imports and configuration
import argparse
import glob
import importlib.util
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.thescore import SCORE_RE, ROUND_RE, devig_multiplicative, devig_power, ev as ev_of, name_variants, mentions  # noqa: E402

os.environ.setdefault("FD_REGION", "nj")  # the New Jersey feed answers cloud callers; Ontario needs a Canadian connection
os.environ.setdefault("PB_REGION", "au")
spec = importlib.util.spec_from_file_location("pb_monitor", ROOT / "tools/collect_pointsbet_live_alternates.py")
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)  # reuses FanDuel fetch, team-name normalisation and market classification

FD_SPORT_IDS = {"football": 6423, "basketball": 7522, "hockey": 7524, "baseball": 7511, "soccer": 1, "tennis": 2, "mma": 26420387, "boxing": 6, "rugby-league": 1477,
                "rugby-union": 5, "cricket": 4, "handball": 468328, "australian-rules": 61420, "darts": 3503, "snooker": 6422, "golf": 3, "motorsports": 8}
REPORTS = ROOT / "reports"


# %% FanDuel access
def fd_get(path):
    return pb.get(f"{pb.FD}/{path}&_ak={pb.FD_AK}&timezone={pb.FD_TZ}", pb.FD_H)


def parse_fd_events(d):
    out = []
    for e in (d.get("attachments") or {}).get("events", {}).values():
        nm = e.get("name") or ""
        sep = " @ " if " @ " in nm else " v " if " v " in nm else None
        if not sep or e.get("inPlay"):
            continue
        a, b = [re.sub(r"\s*\(.*?\)", "", x).strip() for x in nm.split(sep, 1)]
        home, away = (b, a) if sep == " @ " else (a, b)
        out.append(dict(id=str(e.get("eventId")), name=nm, home=home, away=away, start=pb.ts(e.get("openDate")), competition=e.get("competitionId")))
    return out


def fd_sport_events(sport):
    """The sport front page lists every pregame fixture FanDuel carries for the coming days."""
    et = FD_SPORT_IDS.get(sport)
    if not et:
        return []
    d = fd_get(f"content-managed-page?page=SPORT&eventTypeId={et}")
    return parse_fd_events(d)


def fd_event_markets(event_id):
    """Every market across every tab of the event page."""
    d = fd_get(f"event-page?eventId={event_id}&tab=popular")
    markets = dict((d.get("attachments") or {}).get("markets", {}))
    for tid in ((d.get("layout") or {}).get("tabs") or {}):
        try:
            dd = fd_get(f"event-page?eventId={event_id}&tab={tid}")
        except RuntimeError:
            continue
        markets.update((dd.get("attachments") or {}).get("markets", {}))
        time.sleep(0.1)
    out = []
    for m in markets.values():
        if m.get("marketStatus") != "OPEN":
            continue
        runners = []
        for r in m.get("runners", []):
            if r.get("runnerStatus") != "ACTIVE":
                continue
            price = (((r.get("winRunnerOdds") or {}).get("trueOdds") or {}).get("decimalOdds") or {}).get("decimalOdds")
            if not price:
                continue
            h = r.get("handicap")
            runners.append({"name": r.get("runnerName") or "", "handicap": float(h) if h not in (None, "") else None, "decimal": float(price), "type": r.get("result", {}).get("type") if isinstance(r.get("result"), dict) else None})
        if runners:
            out.append({"type": (m.get("marketType") or "").upper(), "name": m.get("marketName") or "", "runners": runners})
    return out


def match_event(row, fd_events, max_gap_s=3 * 3600):
    """theScore event -> FanDuel event by participant names and start time."""
    ev_name = row["event"]
    sep = " @ " if " @ " in ev_name else " vs " if " vs " in ev_name else None
    if not sep:
        return None
    a, b = [x.strip() for x in ev_name.split(sep, 1)]
    home, away = (b, a) if sep == " @ " else (a, b)
    try:
        start = datetime.fromisoformat(row["start"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        start = None
    best, best_score = None, 0
    for e in fd_events:
        if start and e["start"] and abs((e["start"] - start).total_seconds()) > max_gap_s:
            continue
        s = min(person_or_team_sim(home, e["home"]), person_or_team_sim(away, e["away"]))
        if s > best_score:
            best, best_score = e, s
    return best if best_score >= 0.75 else None


def person_or_team_sim(a, b):
    s = pb.team_sim(a, b)
    if s >= 0.75:
        return s
    na, nb = pb.norm_player(a), pb.norm_player(b)
    if na == nb:
        return 1.0
    ta, tb = na.split(), nb.split()
    if ta and tb and ta[-1] == tb[-1] and (ta[0][0] == tb[0][0]):
        return 0.9
    return s


# %% leg A -> FanDuel market and runner
def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+./ -]", " ", (s or "").lower())).strip()


def method_key(text):
    t = text.lower()
    if "ko" in t or "tko" in t:
        return "ko"
    if "sub" in t:
        return "sub"
    if "point" in t or "decision" in t:
        return "dec"
    return None


def participant_variants(row, side):
    nm = row["event"]
    sep = " @ " if " @ " in nm else " vs " if " vs " in nm else None
    if not sep:
        return set()
    a, b = [x.strip() for x in nm.split(sep, 1)]
    home, away = (b, a) if sep == " @ " else (a, b)
    return name_variants({"fullName": home if side == "home" else away})


def which_side(row, text):
    for side in ("home", "away"):
        if mentions(text, participant_variants(row, side)):
            return side
    return None


def fd_name_for_side(fd_event, side):
    return fd_event["home"] if side == "home" else fd_event["away"]


def locate(row, fd_event, markets):
    """-> (market, runner, partition: bool, note) for theScore leg A, or (None, None, False, reason)."""
    a = row["a"]
    am, asel, atype, pts = a["market"], a["selection"] or "", a["selection_type"], a["points"]
    side = which_side(row, asel) or ("home" if atype and atype.startswith("HOME") else "away" if atype and atype.startswith("AWAY") else None)
    fd_part = fd_name_for_side(fd_event, side) if side else None
    fd_part_norm = pb.norm_player(fd_part) if fd_part else None

    def runner_has_participant(r):
        return fd_part_norm and (fd_part_norm in pb.norm_player(r["name"]) or pb.norm_player(r["name"]).split()[-1:] == fd_part_norm.split()[-1:] and fd_part_norm.split()[-1] in pb.norm_player(r["name"]))

    # moneylines (2- and 3-way)
    if atype in ("HOME_MONEYLINE", "AWAY_MONEYLINE", "DRAW") and am in ("Moneyline", "Match Winner", "Match Result", "Fight Winner", "1st Set Winner", "2nd Set Winner"):
        want = {"Moneyline": ("MATCH_BETTING", "MONEY_LINE", "MONEYLINE", "WIN-DRAW-WIN"), "Match Winner": ("MATCH_BETTING",), "Match Result": ("WIN-DRAW-WIN", "MATCH_BETTING"), "Fight Winner": ("MATCH_BETTING",),
                "1st Set Winner": ("SET_1_WINNER",), "2nd Set Winner": ("SET_2_WINNER",)}[am]
        for m in markets:
            if m["type"] in want:
                for r in m["runners"]:
                    if (atype == "DRAW" and r["name"].lower() in ("draw", "tie", "the draw")) or (atype != "DRAW" and runner_has_participant(r)):
                        return m, r, True, "moneyline"
        return None, None, False, "no FD moneyline"
    # spreads, totals, team totals (two-way, same line)
    if atype in ("HOME_SPREAD", "AWAY_SPREAD", "OVER", "UNDER") and pts is not None:
        for m in markets:
            kind = pb.classify_fd_market(m["type"], [{"runnerName": r["name"], "runnerStatus": "ACTIVE"} for r in m["runners"]], row["sport"] if row["sport"] != "mma" else "mma")
            if not kind:
                continue
            k, period, tt_side, stat, _ = kind
            if period:
                continue
            is_team_total = bool(re.match(r"^(.*?) Total (Goals|Points|Runs|Games)$", am)) and am not in ("Total Goals", "Total Points", "Total Runs", "Total Games")
            if atype in ("OVER", "UNDER"):
                if is_team_total:
                    if k != "team_total" or not (tt_side and tt_side == side):
                        if not (k == "team_total" and side and fd_part and pb.team_sim(am.rsplit(" Total", 1)[0], fd_part) >= 0.75 and (tt_side == side)):
                            continue
                elif k != "total" or am == "Total Rounds" and "ROUND" not in m["type"]:
                    if not (am == "Total Rounds" and "ROUND" in m["type"]):
                        continue
                for r in m["runners"]:
                    rh = r["handicap"]
                    if rh is None:
                        mm = re.search(r"(\d+\.5)", r["name"])
                        rh = float(mm.group(1)) if mm else None
                    if rh == pts and r["name"].lower().startswith(atype.lower()):
                        return m, r, True, k
            else:
                if k != "spread":
                    continue
                for r in m["runners"]:
                    if r["handicap"] == pts and runner_has_participant(r):
                        return m, r, True, "spread"
        return None, None, False, "no FD two-way line"
    # MMA method / round / combo
    if am in ("Method Of Victory", "Method Of Victory (Double Chance)", "Round Betting", "Method & Round Combo"):
        mk = method_key(asel)
        rd = ROUND_RE.search(asel)
        for m in markets:
            if am == "Method Of Victory" and m["type"] == "METHOD_OF_VICTORY":
                for r in m["runners"]:
                    if runner_has_participant(r) and method_key(r["name"]) == mk:
                        return m, r, True, "method"
            if am == "Round Betting" and m["type"].startswith("ROUND_BETTING"):
                for r in m["runners"]:
                    rr = ROUND_RE.search(r["name"])
                    if runner_has_participant(r) and ((rd and rr and rd.group(1) == rr.group(1)) or (not rd and mk == "dec" and method_key(r["name"]) == "dec")):
                        return m, r, True, "round"
            if am == "Method & Round Combo" and m["type"].startswith("METHOD_&_ROUND"):
                for r in m["runners"]:
                    rr = ROUND_RE.search(r["name"])
                    if runner_has_participant(r) and rd and rr and rd.group(1) == rr.group(1) and method_key(r["name"]) == mk:
                        return m, r, True, "method_round"
            if am == "Method Of Victory (Double Chance)" and m["type"] == "DOUBLE_CHANCE":
                keys = {method_key(p) for p in re.split(r"\bOr\b", asel, flags=re.I)}
                for r in m["runners"]:
                    rk = {method_key(p) for p in re.split(r"\bor\b", r["name"], flags=re.I)}
                    if runner_has_participant(r) and rk == keys:
                        return m, r, True, "method_dc"
        return None, None, False, "no FD method/round market"
    # tennis set score
    if am.startswith("Correct Score - Best Of"):
        sc = SCORE_RE.search(asel)
        for m in markets:
            if m["type"] == "SET_BETTING":
                for r in m["runners"]:
                    rs = SCORE_RE.search(r["name"])
                    if runner_has_participant(r) and rs and rs.groups() == sc.groups():
                        return m, r, True, "set_betting"
        return None, None, False, "no FD set betting"
    # soccer correct score: FanDuel lists home-first scores without names
    if am == "Correct Score":
        sc = SCORE_RE.search(asel)
        if sc and side:
            g1, g2 = sc.group(1), sc.group(2)
            key = f"{g1}-{g2}" if side == "home" else f"{g2}-{g1}"
            if "Draw" in asel:
                key = f"{g1}-{g2}"
            for m in markets:
                if m["type"] == "CORRECT_SCORE":
                    for r in m["runners"]:
                        if norm(r["name"]).replace(" ", "") == key or norm(r["name"]).endswith(key):
                            return m, r, True, "correct_score"
        return None, None, False, "no FD correct score"
    if am == "Double Chance":
        for m in markets:
            if m["type"] == "DOUBLE_CHANCE":
                for r in m["runners"]:
                    if runner_has_participant(r) and ("draw" in r["name"].lower()) == ("draw" in asel.lower()):
                        return m, r, True, "double_chance"
    if am in ("Draw No Bet", "Tie No Bet"):
        for m in markets:
            if m["type"] == "DRAW_NO_BET":
                for r in m["runners"]:
                    if runner_has_participant(r):
                        return m, r, True, "dnb"
    if am == "Both Teams To Score":
        for m in markets:
            if m["type"] == "BOTH_TEAMS_TO_SCORE":
                for r in m["runners"]:
                    if r["name"].lower() == asel.lower():
                        return m, r, True, "btts"
    # first scorer (partition: every listed player plus 'no scorer' is only approximately exhaustive) and player ladders
    if am.startswith("First") and "Scorer" in am:
        for m in markets:
            if m["type"] in ("FIRST_TOUCHDOWN_SCORER", "FIRST_GOAL_SCORER", "FIRST_GOALSCORER", "FIRST_TD_SCORER"):
                for r in m["runners"]:
                    if pb.norm_player(r["name"]) == pb.norm_player(asel):
                        return m, r, True, "first_scorer"
        return None, None, False, "no FD first scorer"
    pm = re.match(r"^(?P<player>.+?) (?P<stat>Total .+?|Touchdowns Scored)$", am)
    if pm:
        player = pb.norm_player(pm.group("player"))
        stat_words = set(re.findall(r"[a-z]+", pm.group("stat").lower())) - {"total"}
        thr = None
        mt = re.match(r"^(\d+(?:\.\d+)?)\+$", asel)
        if mt:
            thr = float(mt.group(1))
        elif pts is not None and atype == "OVER":
            thr = pts + 0.5
        for m in markets:
            mname = m["name"].lower()
            if player not in pb.norm_player(mname) and not all(w in pb.norm_player(mname) for w in player.split()[-1:]):
                continue
            words = set(re.findall(r"[a-z]+", mname))
            if not (stat_words & words or ("touchdowns" in stat_words and ("td" in words or "touchdown" in words))):
                continue
            # two-sided O/U at the same line
            for r in m["runners"]:
                if r["handicap"] is not None and thr is not None and abs(r["handicap"] + 0.5 - thr) < 1e-9 and r["name"].lower().startswith("over") and len(m["runners"]) == 2:
                    return m, r, True, "player_ou"
            # one-sided ladder '100+' / '2+'
            for r in m["runners"]:
                mr = re.match(r"^(\d+(?:\.\d+)?)\+", r["name"].strip())
                if mr and thr is not None and float(mr.group(1)) == thr:
                    return m, r, False, "player_ladder_one_sided"
        return None, None, False, "no FD player market"
    return None, None, False, "unhandled leg type"


# %% devig
def fair_probs(market, runner, partition):
    """Devig only when the FanDuel market is exhaustive: its implied probabilities must sum to at least 1 (a book's hold is never
    negative). Markets that omit outcomes (a method-and-round combo without decisions, a one-sided ladder) cannot be normalised."""
    decs = [r["decimal"] for r in market["runners"]]
    idx = market["runners"].index(runner)
    implied_sum = sum(1 / d for d in decs)
    if not partition or len(decs) < 2 or implied_sum < 1.0:
        return {"p_raw": 1 / runner["decimal"], "p_mult": None, "p_power": None, "hold": implied_sum, "k": None, "n_runners": len(decs), "partition": False}
    mult, hold = devig_multiplicative(decs)
    power, k = devig_power(decs)
    return {"p_raw": 1 / runner["decimal"], "p_mult": mult[idx], "p_power": power[idx], "hold": hold, "k": k, "n_runners": len(decs), "partition": True}


# %% main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="", help="screen JSONL (default: latest)")
    ap.add_argument("--min-improvement", type=float, default=0.005)
    ap.add_argument("--all", action="store_true", help="devig every priced row, not only improved ones")
    args = ap.parse_args()
    path = Path(args.rows) if args.rows else Path(sorted(glob.glob(str(ROOT / "data/live/thescore-sgp-redundant/*.jsonl")))[-1])
    rows = [json.loads(l) for l in open(path)]
    todo = [r for r in rows if r.get("sgp_decimal") and (args.all or (r.get("improvement") or 0) > args.min_improvement)]
    print(f"{len(rows)} rows, {len(todo)} to devig from {path.name}")

    fd_cache, fd_markets_cache = {}, {}
    out, unmatched = [], defaultdict(int)
    for r in todo:
        sport = r["sport"]
        if sport not in fd_cache:
            try:
                fd_cache[sport] = fd_sport_events(sport)
            except RuntimeError as e:
                print("FD sport page failed", sport, e)
                fd_cache[sport] = []
        fe = match_event(r, fd_cache[sport])
        if not fe:
            unmatched["event:" + sport] += 1
            out.append(dict(r, fd_event=None, fd_note="no FanDuel fixture match"))
            continue
        if fe["id"] not in fd_markets_cache:
            try:
                fd_markets_cache[fe["id"]] = fd_event_markets(fe["id"])
            except RuntimeError as e:
                fd_markets_cache[fe["id"]] = []
                print("FD event failed", fe["name"], e)
        m, rn, partition, note = locate(r, fe, fd_markets_cache[fe["id"]])
        rec = dict(r, fd_event=fe["name"], fd_event_id=fe["id"], fd_note=note)
        if not m:
            unmatched["leg:" + note] += 1
            out.append(rec)
            continue
        fp = fair_probs(m, rn, partition)
        rec.update(fd_market=m["type"], fd_market_name=m["name"], fd_runner=rn["name"], fd_decimal=rn["decimal"], **fp)
        rec["fd_partition"] = fp["partition"]
        rec["ev_vs_fd_raw"] = ev_of(r["sgp_decimal"], fp["p_raw"])
        rec["ev_mult"] = ev_of(r["sgp_decimal"], fp["p_mult"]) if fp["p_mult"] else None
        rec["ev_power"] = ev_of(r["sgp_decimal"], fp["p_power"]) if fp["p_power"] else None
        rec["straight_ev_mult"] = ev_of(r["a"]["decimal"], fp["p_mult"]) if fp["p_mult"] else None
        out.append(rec)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    priced = [o for o in out if o.get("fd_decimal")]
    two_sided = [o for o in priced if o.get("fd_partition")]
    one_sided = [o for o in priced if not o.get("fd_partition")]
    summary = {
        "screen_rows": str(path.relative_to(ROOT)) if str(path).startswith(str(ROOT)) else str(path), "devigged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "candidates": len(todo), "fd_matched_legs": len(priced),
        "two_sided_reference": len(two_sided), "positive_ev_power": sum(1 for o in two_sided if o["ev_power"] > 0), "positive_ev_mult": sum(1 for o in two_sided if o["ev_mult"] > 0),
        "one_sided_reference": len(one_sided), "one_sided_positive_ev_upper_bound": sum(1 for o in one_sided if o["ev_vs_fd_raw"] > 0),
        "unmatched": dict(unmatched),
        "rows": sorted(out, key=lambda o: -(o.get("ev_power") if o.get("ev_power") is not None else -9)),
    }
    rp = REPORTS / f"thescore-sgp-redundant-legs-fanduel-devig-{stamp}.json"
    rp.write_text(json.dumps(summary, indent=1, default=str))
    print(f"matched {len(priced)}/{len(todo)} legs on FanDuel; exhaustive reference {len(two_sided)} (+EV power {summary['positive_ev_power']}, mult {summary['positive_ev_mult']}); "
          f"one-sided reference {len(one_sided)} (+EV at raw implied, upper bound: {summary['one_sided_positive_ev_upper_bound']}) -> {rp.relative_to(ROOT)}")
    print("unmatched:", dict(unmatched))
    for o in summary["rows"][:30]:
        if o.get("fd_decimal") and o.get("fd_partition"):
            print(f"  {o['sport']:9s} {o['rule']:22s} {o['event'][:38]:38s} A={o['a']['market'][:28]}|{(o['a']['selection'] or '')[:24]} {o['a']['price']:>6} SGP={o['sgp_formatted']:>6} FD={o['fd_decimal']:.2f} pmult={o['p_mult'] and round(o['p_mult'],4)} ppow={o['p_power'] and round(o['p_power'],4)} EVmult={o['ev_mult'] and round(o['ev_mult'],3)} EVpow={o['ev_power'] and round(o['ev_power'],3)} straightEV={o['straight_ev_mult'] and round(o['straight_ev_mult'],3)}")


if __name__ == "__main__":
    main()
