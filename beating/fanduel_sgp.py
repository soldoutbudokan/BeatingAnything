"""FanDuel same-game-parlay quotes and two-way markets, standard library only.

The FanDuel web client prices a same-game parlay the moment two selections from one event sit in the betslip. Captured on
sportsbook.fanduel.com (New Jersey board, no login):

    POST https://sib.nj.sportsbook.fanduel.com/api/sports/fixedodds/transactional/v1/implyBets?pricePolicy=SUGGESTED
    x-application: FhMFpcPWXMeyZxOx
    {"betLegs": [{"legType": "SIMPLE_SELECTION", "betRunners": [{"runner": {"marketId": "734.188988167", "selectionId": 43010249}}]}, ...]}

The client bundle maps the response to betCombinations (the same-game parlay is the entry with isSGM true, priced in
winAvgOdds.americanDisplayOdds.americanOdds and winAvgOdds.trueOdds.decimalOdds.decimalOdds), betFailures (failureCode such as
INVALID_COMBINATION or IMPOSSIBLE_SAME_PLAYER_UNDER_COMBINATION when FanDuel refuses the pair) and winRunnerOdds per leg.
Market and selection ids come from the public event page on sbapi.<region>.sportsbook.fanduel.com.

The sib host is outside this container's network policy at the time of writing, so quote() raises HostBlocked here; the
parser is covered by tests against the captured shape so the pipeline runs unchanged once the host is reachable.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

REGION = os.environ.get("FD_REGION", "nj")
APP_KEY = "FhMFpcPWXMeyZxOx"  # public key embedded in FanDuel's web client
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
SPORT_IDS = {"football": 6423, "basketball": 7522, "hockey": 7524, "baseball": 7511, "soccer": 1, "tennis": 2, "mma": 26420387, "boxing": 6,
             "rugby-league": 1477, "rugby-union": 5, "cricket": 4, "handball": 468328, "australian-rules": 61420}


class FanDuelError(RuntimeError):
    pass


class HostBlocked(FanDuelError):
    """The environment's network policy refused the CONNECT to the host."""


def sbapi(region=None):
    return f"https://sbapi.{region or REGION}.sportsbook.fanduel.com/api"


def sib(region=None):
    return f"https://sib.{region or REGION}.sportsbook.fanduel.com/api/sports/fixedodds/transactional/v1/implyBets?pricePolicy=SUGGESTED"


def headers(json_body=False):
    h = {"Accept": "application/json", "Origin": "https://sportsbook.fanduel.com", "Referer": "https://sportsbook.fanduel.com/", "User-Agent": UA,
         "x-application": APP_KEY, "Accept-Encoding": "identity"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def request_json(url, data=None, timeout=25, tries=3):
    body = json.dumps(data).encode() if data is not None else None
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=body, headers=headers(json_body=body is not None), method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:500]
            if e.code == 403 and "CONNECT" in text.upper() or e.code == 403 and "tunnel" in text.lower():
                raise HostBlocked(f"{urllib.parse.urlsplit(url).hostname}: {e.code} {text[:120]}")
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                last = e
                time.sleep(1.5 * (i + 1))
                continue
            raise FanDuelError(f"{e.code} {url[:120]}: {text[:200]}")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            reason = str(getattr(e, "reason", e))
            if "403" in reason and ("tunnel" in reason.lower() or "connect" in reason.lower()):
                raise HostBlocked(f"{urllib.parse.urlsplit(url).hostname}: {reason}")
            last = e
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise FanDuelError(f"{url[:120]}: {last}")


# %% public event data
def _ts(s):
    from datetime import datetime, timezone
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (AttributeError, ValueError):
        return None


def sport_events(sport, region=None):
    """Pregame fixtures FanDuel lists on the sport front page: [{id, name, home, away, start, competition}]."""
    et = SPORT_IDS.get(sport)
    if not et:
        return []
    d = request_json(f"{sbapi(region)}/content-managed-page?page=SPORT&eventTypeId={et}&_ak={APP_KEY}&timezone=America%2FNew_York")
    out = []
    for e in (d.get("attachments") or {}).get("events", {}).values():
        nm = e.get("name") or ""
        sep = " @ " if " @ " in nm else " v " if " v " in nm else None
        if not sep or e.get("inPlay"):
            continue
        a, b = [re.sub(r"\s*\(.*?\)", "", x).strip() for x in nm.split(sep, 1)]
        home, away = (b, a) if sep == " @ " else (a, b)
        out.append(dict(id=str(e.get("eventId")), name=nm, home=home, away=away, start=_ts(e.get("openDate")), competition=e.get("competitionId")))
    return out


def event_markets(event_id, region=None, sleep=0.1):
    """Every open market on every tab of the event page, with the ids the betslip needs."""
    base = f"{sbapi(region)}/event-page?_ak={APP_KEY}&eventId={event_id}&useCombinedTouchdownsVirtualMarket=true&useQuickBets=true"
    d = request_json(f"{base}&tab=popular")
    markets = dict((d.get("attachments") or {}).get("markets", {}))
    for tid in ((d.get("layout") or {}).get("tabs") or {}):
        try:
            dd = request_json(f"{base}&tab={tid}")
        except FanDuelError:
            continue
        markets.update((dd.get("attachments") or {}).get("markets", {}))
        time.sleep(sleep)
    out = []
    for m in markets.values():
        if m.get("marketStatus") != "OPEN":
            continue
        runners = []
        for r in m.get("runners", []):
            if r.get("runnerStatus") != "ACTIVE":
                continue
            odds = r.get("winRunnerOdds") or {}
            dec = ((odds.get("trueOdds") or {}).get("decimalOdds") or {}).get("decimalOdds")
            if not dec:
                continue
            h = r.get("handicap")
            runners.append({"selectionId": r.get("selectionId"), "name": r.get("runnerName") or "", "handicap": float(h) if h not in (None, "") else None,
                            "decimal": float(dec), "american": (odds.get("americanDisplayOdds") or {}).get("americanOdds")})
        if runners:
            out.append({"marketId": m.get("marketId"), "type": (m.get("marketType") or "").upper(), "name": m.get("marketName") or "", "sgm": bool(m.get("sgmMarket")),
                        "runners": runners})
    return out


# %% two-way markets in the conjunction outcome spaces
PLAYER_TYPES = [  # (regex on marketType, space variable); the first match wins, so combined stats come before their parts
    (re.compile(r"RUSHING_\+_RECEIVING|RUSH_\+_REC|RUSHING_AND_RECEIVING|RUSH_REC"), "S"),
    (re.compile(r"RUSHING_Y(AR)?DS"), "R"), (re.compile(r"RECEIVING_Y(AR)?DS"), "C"),
    (re.compile(r"PTS?_\+_REB_\+_AST|POINTS_\+_REBOUNDS_\+_ASSISTS|PRA\b"), "PRA"), (re.compile(r"PTS?_\+_REB(?!_\+_AST)|POINTS_\+_REBOUNDS(?!_\+)"), "PRB"),
    (re.compile(r"PTS?_\+_AST|POINTS_\+_ASSISTS"), "PAS"), (re.compile(r"REB_\+_AST|AST_\+_REB|REBOUNDS_\+_ASSISTS|ASSISTS_\+_REBOUNDS"), "ASRB"),
    (re.compile(r"MADE_THREES|3_POINTERS|THREE_POINTERS|3PT"), "TPM"), (re.compile(r"(^|_)POINTS(_|$)"), "P"), (re.compile(r"REBOUNDS"), "RB"), (re.compile(r"ASSISTS"), "AS"),
    (re.compile(r"TOTAL_BASES"), "TB"), (re.compile(r"HOME_RUNS?"), "HR"), (re.compile(r"(^|_)HITS(_|$)"), "H"), (re.compile(r"RBI"), "RBI"),
    (re.compile(r"SHOTS_ON_GOAL"), "SOG"), (re.compile(r"(^|_)GOALS(_|$)"), "G"),
]
SPACE_VARS = {"football_yards": {"R", "C", "S"}, "basketball": {"P", "RB", "AS", "PRA", "PRB", "PAS", "ASRB"}, "basketball_threes": {"P", "TPM"},
              "baseball_bat": {"H", "HR", "TB", "RBI"}, "hockey_skater": {"G", "PTS", "SOG"}}
OVER_RE = re.compile(r"\bover\b", re.I)
UNDER_RE = re.compile(r"\bunder\b", re.I)
PAREN_LINE = re.compile(r"\((-?\d+(?:\.\d+)?)\)")
NAMED_LINE = re.compile(r"\b(?:over|under)\s+(-?\d+(?:\.\d+)?)\b", re.I)  # 'Over 2.5 Goals'



def _player_of(market_name):
    return market_name.split(" - ")[0].strip() if " - " in market_name else None


def _pair_over_under(runners):
    """-> {line: (over_runner, under_runner)} for runners named Over/Under, either on the handicap or on a '(19.5)' suffix."""
    by_line = {}
    for r in runners:
        line = r["handicap"]
        m = PAREN_LINE.search(r["name"]) or NAMED_LINE.search(r["name"])
        if m:
            line = float(m.group(1))
        if line is None:
            continue
        if OVER_RE.search(r["name"]):
            by_line.setdefault(line, [None, None])[0] = r
        elif UNDER_RE.search(r["name"]):
            by_line.setdefault(line, [None, None])[1] = r
    return {k: tuple(v) for k, v in by_line.items() if v[0] and v[1]}


def two_way_markets(markets, event=None):
    """Two-way markets as outcome-space atoms.

    -> [{"var", "line", "player", "marketId", "name", "over": runner, "under": runner}] where for player stats var is the space
    variable and over/under are the Over/Under runners; for team markets var is total / team_H / team_A (over/under),
    margin_H (over = home covers -line, under = away covers) or result (over = home wins, under = away wins)."""
    out = []
    home = (event or {}).get("home") or ""
    away = (event or {}).get("away") or ""
    for m in markets:
        t = m["type"]
        if any(w in t for w in ("1ST", "2ND", "3RD", "4TH", "FIRST_", "SECOND_", "HALF", "QUARTER", "PERIOD", "INNING", "SPECIAL", "ALT_", "_ALT")) and "ALTERNATE" not in t:
            continue
        if t.startswith("PLAYER") or " - " in m["name"]:
            var = next((v for rx, v in PLAYER_TYPES if rx.search(t)), None)
            if not var or "ALT" in t:
                continue
            player = _player_of(m["name"])
            for line, (o, u) in _pair_over_under(m["runners"]).items():
                out.append({"var": var, "line": line, "player": player, "marketId": m["marketId"], "name": m["name"], "over": o, "under": u})
            continue
        if t in ("TOTAL_POINTS_(OVER/UNDER)", "TOTAL_GOALS_(OVER/UNDER)", "TOTAL_RUNS_(OVER/UNDER)", "ALTERNATE_TOTAL", "ALTERNATE_TOTAL_POINTS", "TOTAL_MATCH_GOALS") or t.startswith("TOTAL_POINTS") or t.startswith("TOTAL_GOALS") or t.startswith("TOTAL_RUNS") or re.fullmatch(r"OVER_UNDER_\d+", t):
            for line, (o, u) in _pair_over_under(m["runners"]).items():
                out.append({"var": "total", "line": line, "player": None, "marketId": m["marketId"], "name": m["name"], "over": o, "under": u})
        elif re.match(r"(HOME|AWAY)_TEAM_(ALTERNATE_)?TOTAL", t):
            side = "H" if t.startswith("HOME") else "A"
            for line, (o, u) in _pair_over_under(m["runners"]).items():
                out.append({"var": f"team_{side}", "line": line, "player": None, "marketId": m["marketId"], "name": m["name"], "over": o, "under": u})
        elif t in ("MONEY_LINE", "MONEYLINE") and home and away:
            hr = next((r for r in m["runners"] if r["name"] == home), None)
            ar = next((r for r in m["runners"] if r["name"] == away), None)
            if hr and ar and len(m["runners"]) == 2:
                out.append({"var": "result", "line": None, "player": None, "marketId": m["marketId"], "name": m["name"], "over": hr, "under": ar})
        elif (t.startswith("MATCH_HANDICAP") or t in ("ALTERNATE_HANDICAP", "ALTERNATE_HANDICAPS", "SPREAD", "RUN_LINE", "PUCK_LINE")) and home and away:
            by_line = {}
            for r in m["runners"]:
                mm = re.match(r"(.+?)\s*\(?([+-]\d+(?:\.\d+)?)\)?$", r["name"])
                team, hcap = (mm.group(1).strip(), float(mm.group(2))) if mm else (r["name"], r["handicap"])
                if hcap is None:
                    continue
                if team == home:
                    by_line.setdefault(-hcap, [None, None])[0] = r  # home covers -line  <=> margin_H >= line
                elif team == away:
                    by_line.setdefault(hcap, [None, None])[1] = r
            for line, (o, u) in by_line.items():
                if o and u:
                    out.append({"var": "margin_H", "line": line, "player": None, "marketId": m["marketId"], "name": m["name"], "over": o, "under": u})
    return out


# %% quoting
def legs_for(runners):
    return [{"legType": "SIMPLE_SELECTION", "betRunners": [{"runner": {"marketId": str(r["marketId"]), "selectionId": int(r["selectionId"])}}]} for r in runners]


def parse_imply(resp, n_legs):
    """-> {"decimal", "american", "status", "failures"}; status is 'quoted', 'refused' (betFailures) or 'no_sgp'."""
    combos = resp.get("betCombinations") or []
    failures = [{"code": f.get("failureCode"), "runner": f.get("failedRunner"), "groups": f.get("combinationGroups")} for f in (resp.get("betFailures") or [])]
    sgp = next((c for c in combos if c.get("isSGM") and (c.get("numLines") in (None, 1))), None)
    if sgp is None:
        sgp = next((c for c in combos if c.get("isSGM")), None)
    if sgp is None:
        return {"decimal": None, "american": None, "status": "refused" if failures else "no_sgp", "failures": failures, "legs": n_legs}
    odds = sgp.get("winAvgOdds") or {}
    dec = ((odds.get("trueOdds") or {}).get("decimalOdds") or {}).get("decimalOdds")
    am = (odds.get("americanDisplayOdds") or {}).get("americanOdds")
    if dec is None and am is not None:
        am = float(am)
        dec = 1 + am / 100 if am > 0 else 1 + 100 / -am
    return {"decimal": float(dec) if dec is not None else None, "american": am, "status": "quoted" if dec else "no_price", "failures": failures, "legs": n_legs,
            "betType": sgp.get("betType"), "maxPayout": sgp.get("betMaxPayout")}


def quote(runners, region=None):
    """Same-game parlay price for runners [{marketId, selectionId}, ...] from one event."""
    resp = request_json(sib(region), data={"betLegs": legs_for(runners)})
    return parse_imply(resp, len(runners))
