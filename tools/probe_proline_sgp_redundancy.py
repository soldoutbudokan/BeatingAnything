#!/usr/bin/env python3
"""Proline+ (OLG; Kambi platform since January 2026) same-game-parlay redundant-leg probe.

A redundant leg is already implied by the other legs of the construction: over 24.5 points when over 29.5 points is
in, the moneyline when -3.5 is in, receiving over 34.5 when 90+ rushing-plus-receiving and rushing under 54.5 are
in. A correct SGP engine prices it at no change. theScore Bet raised the quote instead
(reports/sgp-rush-receive-2026-10-08). This tool looks for the same behaviour on Proline+.

Steps (positional command):
  discover  find the Kambi operator code and host that answer for Proline+ (public offering API, GET only)
  scan      pull boards for upcoming NHL / NBA / NFL / MLB events and enumerate base + redundant constructions
  price     price each construction's base, then base plus the redundant leg, through the Bet Builder endpoint
  record    append one manually observed pair of quotes (UI capture) to the observation file
  report    print every observation and flag those where the redundant leg raised the price

The offering API shape (listView, betoffer/event, odds and lines scaled by 1000) is verified against other Kambi
books. The operator code for Proline+ and the Bet Builder pricing call are NOT verified: `discover` finds the first,
and `price` needs --price-url / --price-body copied from the browser network tab while building an SGP on
proline.ca. Read-only: never logs in, places, or touches a betslip. Proline+ geofences Ontario; the Kambi CDN is
usually not geofenced, but run from an Ontario connection to be safe.

python tools/probe_proline_sgp_redundancy.py discover
python tools/probe_proline_sgp_redundancy.py scan --operator olg --host eu-offering-api.kambicdn.com --leagues nhl,nba
python tools/probe_proline_sgp_redundancy.py price --price-url 'https://.../{eventId}/price.json' \\
    --price-body '{"outcomeIds": {outcomeIds}}'
python tools/probe_proline_sgp_redundancy.py record --event "SF@SEA 2026-10-11" --base "CMC rush+rec 90+; CMC rush U54.5; CMC rec 40+" \\
    --added "CMC rec O34.5" --reason "40+ receiving implies over 34.5" --base-odds +483 --with-odds +854
python tools/probe_proline_sgp_redundancy.py report
"""
# %% imports and configuration
import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/proline-sgp-redundancy-2026-10-23"
OBS = ROOT / "reports/proline-sgp-redundancy-2026-10-23.json"
# Kambi offering hosts seen across operators; the Canadian lotteries' host is unconfirmed, so `discover` tries each.
HOSTS = ["eu-offering-api.kambicdn.com", "eu-offering.kambicdn.org", "ctn-api.kambi.com", "us1-api.aws.kambicdn.com"]
# Candidate operator path segments (Unibet Canada is "ubca", DraftKings NJ was "dkusnj"); none is confirmed for OLG.
OPERATORS = ["olg", "olgca", "olgon", "proline", "prolineplus", "olgproline", "plca"]
QS = "lang=en_CA&market=CA&client_id=2&channel_id=1&includeParticipants=true"
LEAGUES = {"nhl": ("ice_hockey", "NHL"), "nba": ("basketball", "NBA"), "nfl": ("american_football", "NFL"), "mlb": ("baseball", "MLB")}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
GAME = "GAME"
# Yes/No markets that are occurrence counts in disguise: label regex -> (stat, implied over line)
YES_ALIASES = [(r"anytime (goal ?scorer|scorer)", "goals", 0.5), (r"anytime (touchdown|td) scorer", "touchdowns", 0.5),
               (r"(\d+)\s*(\+|or more)\s*(goals?|points?|assists?|touchdowns?|shots?|hits?|rebounds?|threes?)", None, None)]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def http(url, data=None, headers=None, timeout=25):
    """GET (or POST when data is given). Returns (status, json) or (None, error text) for transport failures."""
    h = {"Accept": "application/json", "User-Agent": UA, **(headers or {})}
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"{type(e).__name__}: {e}"


# %% odds helpers
def american(d):
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))


def fmt_am(a):
    return f"+{a}" if a > 0 else str(a)


def parse_american(s):
    a = int(str(s).strip().replace("+", ""))
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


def find_odds(obj):
    """Depth-first search for the first odds-like number in a Bet Builder price response; Kambi ints are x1000."""
    if isinstance(obj, dict):
        for k in ("odds", "decimalOdds", "oddsDecimal", "totalOdds", "combinedOdds", "price"):
            v = obj.get(k)
            if isinstance(v, bool):
                continue
            if isinstance(v, int) and v >= 1000:
                return v / 1000
            if isinstance(v, (int, float)) and v >= 1:
                return float(v)
            if isinstance(v, str) and re.fullmatch(r"\d+(\.\d+)?", v):
                return float(v) / 1000 if "." not in v and int(v) >= 1000 else float(v)
        for v in obj.values():
            r = find_odds(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_odds(v)
            if r:
                return r
    return None


# %% leg normalisation: Kambi bet offer + outcome -> (stat, subject, dir, line)
def stat_key(label, names=()):
    s = label.lower()
    for n in names:
        if n:
            s = s.replace(n.lower(), " ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b(including|incl\.?|inc\.?)\s+(overtime|ot)\b", " ", s)
    s = re.sub(r"\band\b|&", " + ", s)  # "Points and Rebounds" is a combined stat like "Rushing + Receiving Yards"
    s = re.sub(r"\b(over/under|over|under|o/u|total|totals|player|team|line|regular time|full time|match odds|moneyline|by|for)\b", " ", s)
    s = re.sub(r"[^a-z0-9+ ]", " ", s)
    return " ".join(s.split())


def combined_parts(stat):
    """'rushing + receiving yards' -> ['rushing yards', 'receiving yards']; None unless exactly two components."""
    parts = [p.strip() for p in stat.split("+")]
    if len(parts) != 2 or not all(parts):
        return None
    a, b = parts[0].split(), parts[1].split()
    if a[-1] != b[-1] and len(a) < len(b):
        a = a + [b[-1]]
    elif a[-1] != b[-1] and len(b) < len(a):
        b = b + [a[-1]]
    return [" ".join(a), " ".join(b)]


def exclusive(a, b):
    """True when two legs of one event cannot both win (so they must not be combined into a base)."""
    if a["event"] != b["event"]:
        return False
    if a["bo"] == b["bo"]:
        return True
    if a["dir"] == b["dir"] == "win" and a["subject"] != b["subject"]:
        return True
    for x, y in ((a, b), (b, a)):
        if x["dir"] == "win" and y["dir"] == "cover" and x["subject"] != y["subject"] and y["line"] <= 0:
            return True
        if x["dir"] == "over" and y["dir"] == "under" and x["stat"] == y["stat"] and x["subject"] == y["subject"] and x["line"] >= y["line"]:
            return True
    if a["dir"] == b["dir"] == "cover" and a["subject"] != b["subject"] and a["line"] + b["line"] <= 0:
        return True
    return False


def leg(bo, o, ev):
    """Normalise one outcome to a leg dict, or None when the market has no implication semantics here."""
    typ = (bo.get("betOfferType") or {}).get("englishName") or (bo.get("betOfferType") or {}).get("name") or ""
    crit = (bo.get("criterion") or {}).get("englishLabel") or (bo.get("criterion") or {}).get("label") or ""
    ot = o.get("type")
    part = o.get("participant")
    home, away = ev.get("homeName"), ev.get("awayName")
    line = o.get("line")
    line = line / 1000 if isinstance(line, (int, float)) else None
    odds = o.get("odds")
    dec = odds / 1000 if isinstance(odds, (int, float)) else None
    base = dict(event=ev.get("id"), oid=o.get("id"), bo=bo.get("id"), dec=dec, crit=crit, type=typ)
    olabel = o.get("englishLabel") or o.get("label") or ""
    if ot in ("OT_OVER", "OT_UNDER") and line is not None:
        if not part:  # team totals sometimes name the team only in the criterion label
            part = next((t for t in (home, away) if t and t.lower() in crit.lower()), None)
        return dict(base, stat=stat_key(crit, (part, home, away)), subject=part or GAME, dir="over" if ot == "OT_OVER" else "under", line=line,
                    label=f"{part or 'Game'} {crit} {'O' if ot == 'OT_OVER' else 'U'}{line:g}")
    if typ == "Match" and ot in ("OT_ONE", "OT_TWO"):
        team = part or (home if ot == "OT_ONE" else away)
        return dict(base, stat="win", subject=team, dir="win", line=None, label=f"{team} ML ({crit})")
    if typ in ("Handicap", "Asian Handicap") and ot in ("OT_ONE", "OT_TWO") and line is not None:
        team = part or (home if ot == "OT_ONE" else away)
        return dict(base, stat="cover", subject=team, dir="cover", line=line, label=f"{team} {line:+g} ({crit})")
    if ot == "OT_YES":
        low = crit.lower()
        for rx, stat, ln in YES_ALIASES:
            m = re.search(rx, low)
            if m and stat:
                return dict(base, stat=stat, subject=part, dir="over", line=ln, label=f"{part} {crit} Yes")
            if m and not stat:  # "2+ goals" style: over (n - 0.5) of that stat
                return dict(base, stat=stat_key(m.group(3)), subject=part, dir="over", line=int(m.group(1)) - 0.5, label=f"{part} {crit} Yes")
        return dict(base, stat=stat_key(crit, (part, home, away)), subject=part or GAME, dir="yes", line=None, label=f"{part or 'Game'} {crit} {olabel}")
    return None


def board_legs(board):
    """Legs for every open outcome in a betoffer/event response."""
    events = {e["id"]: e for e in board.get("events", [])}
    out = []
    for bo in board.get("betOffers", []):
        ev = events.get(bo.get("eventId"), {})
        if bo.get("suspended") or bo.get("closed"):
            continue
        for o in bo.get("outcomes", []):
            if o.get("status", "OPEN") != "OPEN":
                continue
            lg = leg(bo, o, ev)
            if lg and lg["dec"]:
                out.append(lg)
    return out


# %% implication rules: is the candidate leg already implied by the base legs?
def _bounds(x):
    """Integer bounds behind a half-point line: over x needs >= floor(x)+1, under x allows <= ceil(x)-1."""
    return math.floor(x) + 1, math.ceil(x) - 1


def implied(base, cand):
    """Reason text when `cand` cannot change the winning event given `base` (same event), else None. No independence
    assumption: every rule is a set-inclusion statement on final integer stat totals and results."""
    base = [b for b in base if b["event"] == cand["event"] and b["oid"] != cand["oid"]]
    for b in base:
        same = b["stat"] == cand["stat"] and b["subject"] == cand["subject"]
        if same and b["dir"] == cand["dir"] == "over" and b["line"] >= cand["line"]:
            return f"over {b['line']:g} implies over {cand['line']:g}"
        if same and b["dir"] == cand["dir"] == "under" and b["line"] <= cand["line"]:
            return f"under {b['line']:g} implies under {cand['line']:g}"
        if same and b["dir"] == cand["dir"] == "cover" and b["line"] <= cand["line"]:
            return f"{b['line']:+g} covers implies {cand['line']:+g} covers"
        if b["subject"] == cand["subject"] and b["dir"] == "cover" and cand["dir"] == "win" and b["line"] < 0:
            return f"{b['line']:+g} covers implies win"
        if b["subject"] == cand["subject"] and b["dir"] == "win" and cand["dir"] == "cover" and cand["line"] >= 0:
            return f"win implies {cand['line']:+g} covers"
        if (b["stat"] == cand["stat"] and b["dir"] == cand["dir"] == "over" and b["subject"] != GAME and cand["subject"] == GAME
                and b["line"] >= cand["line"]):
            return f"{b['subject']} over {b['line']:g} implies game over {cand['line']:g}"
    # two participant overs of one stat bound the game total from below
    if cand["dir"] == "over" and cand["subject"] == GAME:
        overs = [b for b in base if b["dir"] == "over" and b["stat"] == cand["stat"] and b["subject"] != GAME]
        for i, b1 in enumerate(overs):
            for b2 in overs[i + 1:]:
                if b1["subject"] != b2["subject"] and _bounds(b1["line"])[0] + _bounds(b2["line"])[0] > cand["line"]:
                    return f"{b1['subject']} over {b1['line']:g} and {b2['subject']} over {b2['line']:g} imply game over {cand['line']:g}"
    # combined stat over plus one component under bounds the other component from below (the theScore pattern)
    if cand["dir"] == "over" and cand["subject"] != GAME:
        for b1 in base:
            if b1["dir"] != "over" or "+" not in b1["stat"] or b1["subject"] != cand["subject"]:
                continue
            parts = combined_parts(b1["stat"])
            if not parts or cand["stat"] not in parts:
                continue
            other = parts[1] if parts[0] == cand["stat"] else parts[0]
            for b2 in base:
                if b2["dir"] == "under" and b2["stat"] == other and b2["subject"] == cand["subject"]:
                    floor_c = _bounds(b1["line"])[0] - _bounds(b2["line"])[1]
                    if floor_c > cand["line"]:
                        return f"{b1['stat']} over {b1['line']:g} and {other} under {b2['line']:g} force {cand['stat']} >= {floor_c}, implying over {cand['line']:g}"
    return None


def constructions(legs, max_pairs=40):
    """Base + redundant-leg constructions for one event's legs. Base is the strict leg(s) plus an unrelated anchor leg
    (home moneyline, else game total over) so the base is itself a two-leg SGP. Nearest implied pairs come first."""
    by_event = {}
    for lg in legs:
        by_event.setdefault(lg["event"], []).append(lg)
    out = []
    for ev, ls in by_event.items():
        anchors = [l for l in ls if l["dir"] == "win"] + [l for l in ls if l["dir"] == "over" and l["subject"] == GAME]
        found = []
        for strict in ls:
            for weak in ls:
                if strict["oid"] == weak["oid"]:
                    continue
                r = implied([strict], weak)
                if r:
                    gap = abs((strict["line"] or 0) - (weak["line"] or 0))
                    found.append((gap, strict, weak, r))
        for b1 in ls:
            if b1["dir"] != "over" or "+" not in b1["stat"]:
                continue
            for b2 in ls:
                if b2["dir"] != "under" or b2["subject"] != b1["subject"]:
                    continue
                for weak in ls:
                    if weak["oid"] in (b1["oid"], b2["oid"]):
                        continue
                    r = implied([b1, b2], weak)
                    if r and not implied([b1], weak) and not implied([b2], weak):
                        found.append((0.0, (b1, b2), weak, r))
        found.sort(key=lambda t: t[0])
        for gap, strict, weak, r in found[:max_pairs]:
            strict_legs = list(strict) if isinstance(strict, tuple) else [strict]
            anchor = next((a for a in anchors if a["oid"] not in {s["oid"] for s in strict_legs} | {weak["oid"]}
                           and not any(exclusive(a, l) for l in strict_legs + [weak])
                           and not implied(strict_legs, a) and not any(implied([a], s) for s in strict_legs) and not implied([a], weak)), None)
            out.append(dict(event=ev, base=([anchor] if anchor else []) + strict_legs, added=weak, reason=r))
    return out


# %% network steps
def discover(args):
    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    for host in args.hosts.split(","):
        for op in args.operators.split(","):
            url = f"https://{host}/offering/v2018/{op}/listView/ice_hockey/all/all/all.json?{QS}"
            status, data = http(url)
            ok = status == 200 and isinstance(data, dict) and "events" in data
            rows.append(dict(host=host, operator=op, status=status, ok=ok, events=len(data["events"]) if ok else None, error=data if isinstance(data, str) else None))
            print(f"{host:34s} {op:16s} {status!s:6s} {'OK ' + str(len(data['events'])) + ' events' if ok else (data if isinstance(data, str) else '')}")
            if ok and not args.all:
                (RAW / "discover.json").write_text(json.dumps(dict(ts=now(), rows=rows), indent=2))
                print(f"\nUse: --host {host} --operator {op}")
                return
    (RAW / "discover.json").write_text(json.dumps(dict(ts=now(), rows=rows), indent=2))
    if not any(r["ok"] for r in rows):
        print("\nNo host/operator answered. If every status is None the network policy blocks these hosts; otherwise capture the "
              "operator code from the browser network tab on proline.ca (any request to */offering/v2018/<operator>/*).")


def scan(args):
    RAW.mkdir(parents=True, exist_ok=True)
    api = f"https://{args.host}/offering/v2018/{args.operator}"
    found = []
    for lg in args.leagues.split(","):
        slug, name = LEAGUES[lg]
        status, lst = http(f"{api}/listView/{slug}/all/all/all.json?{QS}")
        if status != 200 or not isinstance(lst, dict):
            print(f"{lg}: listView failed ({status} {lst if isinstance(lst, str) else ''})", file=sys.stderr)
            continue
        (RAW / f"listview_{lg}.json").write_text(json.dumps(lst))
        for item in lst.get("events", []):
            ev = item.get("event", {})
            names = [ev.get("group", "")] + [p.get("name", "") for p in ev.get("path", [])]
            if not any(name == n or name in n.split() for n in names) or ev.get("state") not in (None, "NOT_STARTED"):
                continue
            status, board = http(f"{api}/betoffer/event/{ev['id']}.json?{QS}")
            if status != 200 or not isinstance(board, dict):
                print(f"{lg} {ev.get('name')}: board failed ({status})", file=sys.stderr)
                continue
            (RAW / f"board_{ev['id']}.json").write_text(json.dumps(board))
            legs = board_legs(board)
            cons = constructions(legs, args.max_pairs)
            print(f"{lg} {ev.get('name')} {ev.get('start')}: {len(board.get('betOffers', []))} offers, {len(legs)} legs, {len(cons)} constructions")
            for c in cons:
                found.append(dict(league=lg, event_id=ev["id"], event=ev.get("name"), start=ev.get("start"), base=[l["label"] for l in c["base"]],
                                  base_oids=[l["oid"] for l in c["base"]], added=c["added"]["label"], added_oid=c["added"]["oid"], reason=c["reason"],
                                  base_single_dec=[l["dec"] for l in c["base"]], added_dec=c["added"]["dec"]))
            time.sleep(args.pause)
    (RAW / "constructions.json").write_text(json.dumps(dict(ts=now(), host=args.host, operator=args.operator, constructions=found), indent=2))
    print(f"\n{len(found)} constructions written to {RAW / 'constructions.json'}")


def price(args):
    cons = json.loads((RAW / "constructions.json").read_text())
    obs = load_obs()
    cache = {}
    hits = 0

    def quote(event_id, oids):
        key = (event_id, tuple(sorted(oids)))
        if key not in cache:
            url = args.price_url.replace("{eventId}", str(event_id))
            body = args.price_body.replace("{outcomeIds}", json.dumps(sorted(oids))).replace("{eventId}", str(event_id)).encode()
            status, data = http(url, data=body, headers={k.strip(): v.strip() for k, v in (h.split(":", 1) for h in args.header)})
            (RAW / f"price_{event_id}_{'_'.join(map(str, sorted(oids)))}.json").write_text(json.dumps(dict(ts=now(), status=status, response=data)))
            cache[key] = find_odds(data) if status == 200 else None
            time.sleep(args.pause)
        return cache[key]

    for c in cons["constructions"]:
        if len(c["base_oids"]) < 2 and not args.allow_single:
            continue
        b = quote(c["event_id"], c["base_oids"])
        w = quote(c["event_id"], c["base_oids"] + [c["added_oid"]])
        row = observation("price", f"{c['event']} {c['start']}", c["base"], c["added"], c["reason"], b, w, note=f"host={cons['host']} operator={cons['operator']}")
        obs["observations"].append(row)
        flag = "RAISED" if row["change_pct"] is not None and row["change_pct"] > 0 else ""
        hits += bool(flag)
        print(f"{row['event']:40s} {row['base_american'] or '?':>6} -> {row['with_american'] or '?':>6} {flag:7s} {c['added']} [{c['reason']}]")
    save_obs(obs)
    print(f"\n{hits} constructions priced higher with the redundant leg; observations in {OBS}")


# %% observation file (manual captures and priced constructions share one schema)
def load_obs():
    return json.loads(OBS.read_text()) if OBS.exists() else dict(observations=[])


def save_obs(obs):
    OBS.write_text(json.dumps(obs, indent=2) + "\n")


def observation(source, event, base, added, reason, base_dec, with_dec, note=""):
    change = (with_dec / base_dec - 1) * 100 if base_dec and with_dec else None
    return dict(ts=now(), source=source, event=event, base=base, added=added, reason=reason,
                base_decimal=base_dec, with_decimal=with_dec, base_american=fmt_am(american(base_dec)) if base_dec else None,
                with_american=fmt_am(american(with_dec)) if with_dec else None, change_pct=round(change, 2) if change is not None else None, note=note)


def record(args):
    obs = load_obs()
    row = observation("record", args.event, [s.strip() for s in args.base.split(";")], args.added, args.reason,
                      parse_american(args.base_odds), parse_american(args.with_odds), note=args.note)
    obs["observations"].append(row)
    save_obs(obs)
    print(json.dumps(row, indent=2))


def report(args):
    obs = load_obs()["observations"]
    if not obs:
        print(f"No observations recorded in {OBS}.")
        return
    raised = [o for o in obs if o["change_pct"] is not None and o["change_pct"] > 0]
    print(f"{len(obs)} observations, {len(raised)} with a higher price after adding a redundant leg\n")
    print(f"{'event':42s} {'base':>7s} {'+leg':>7s} {'change':>8s}  added leg | reason")
    for o in sorted(obs, key=lambda o: -(o["change_pct"] or -999)):
        print(f"{o['event'][:42]:42s} {o['base_american'] or '?':>7s} {o['with_american'] or '?':>7s} {('%+.1f%%' % o['change_pct']) if o['change_pct'] is not None else '?':>8s}  {o['added']} | {o['reason']}")


# %% command line
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--hosts", default=",".join(HOSTS))
    d.add_argument("--operators", default=",".join(OPERATORS))
    d.add_argument("--all", action="store_true", help="try every pair instead of stopping at the first that answers")
    s = sub.add_parser("scan")
    s.add_argument("--host", default=HOSTS[0])
    s.add_argument("--operator", required=True)
    s.add_argument("--leagues", default="nhl,nba,nfl,mlb")
    s.add_argument("--max-pairs", type=int, default=40, help="constructions per event, nearest implied pairs first")
    s.add_argument("--pause", type=float, default=0.5)
    q = sub.add_parser("price")
    q.add_argument("--price-url", required=True, help="Bet Builder price endpoint; {eventId} is substituted")
    q.add_argument("--price-body", required=True, help='JSON body template; {outcomeIds} and {eventId} are substituted')
    q.add_argument("--header", action="append", default=[], help="extra request header, Name:value (repeatable)")
    q.add_argument("--allow-single", action="store_true", help="also price constructions whose base is a single leg")
    q.add_argument("--pause", type=float, default=0.5)
    r = sub.add_parser("record")
    for name in ("--event", "--base", "--added", "--reason", "--base-odds", "--with-odds"):
        r.add_argument(name, required=True)
    r.add_argument("--note", default="")
    sub.add_parser("report")
    args = p.parse_args(argv)
    {"discover": discover, "scan": scan, "price": price, "record": record, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
