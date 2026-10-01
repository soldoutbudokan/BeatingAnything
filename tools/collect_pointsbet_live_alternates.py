#!/usr/bin/env python3
"""Live cross-book gap monitor: PointsBet against Pinnacle (fair-price reference) and FanDuel, every PointsBet SGM league.

One cycle pulls every pregame event in the leagues below from PointsBet, Pinnacle's guest API and FanDuel, normalises
each board to one row per (game, period, market, selection, line) and reports two kinds of gap on PointsBet rungs:

  EDGE  PointsBet price x Pinnacle no-vig probability - 1, where Pinnacle quotes both sides of the same line
        (fair = reciprocal-price share of the two-sided, or three-sided, Pinnacle market). This is the primary screen.
  ARB   1/PointsBet + 1/other book (opposite side, same line) < 1, against Pinnacle and FanDuel.

Markets covered: moneylines (2- and 3-way, draw no bet), spreads and alternate ladders, totals and alternate ladders,
team totals, the same for halves / quarters / hockey periods / first five innings, and player-prop over/unders
(yards, receptions, touchdowns, shots, goals, assists, points, hits, home runs, bases, strikeouts, rebounds, threes ...).
Everything is keyed by PointsBet's own event, so a Pinnacle or FanDuel event that cannot be matched by team names and
start time is dropped and counted. Snapshots, arb rows and edge rows are appended as JSON lines under
data/live/pointsbet-alt-monitor/. Read-only: it never logs in, places, or touches a betslip.

Ontario regions must run from a Canadian residential connection with curl_cffi (browser TLS profile). The au/nj
regions answer plain clients from cloud addresses (verified against Ontario on 2026-09-30: FanDuel NJ vs ON 99.3%
identical prices; PointsBet AU vs ON identical rungs and rung ages, prices within 0.3-0.6% on average, max ~3%,
because Australia rounds to a decimal ladder while Ontario uses American price points).

python tools/collect_pointsbet_live_alternates.py                      # one cycle, all leagues
python tools/collect_pointsbet_live_alternates.py --leagues nfl,nhl    # subset
python tools/collect_pointsbet_live_alternates.py --loop 5             # every 5 minutes until interrupted
PB_REGION=au FD_REGION=nj python tools/collect_pointsbet_live_alternates.py --threshold 0.98 --ev-threshold 0.03 \\
    --state data/live/pointsbet-alt-monitor/state.json --no-snapshot
    # cloud-safe screen with NEW_GAPS output; confirm any flagged rung on the Ontario board before staking.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

try:  # Ontario hosts need a browser TLS profile; Australia / New Jersey / Pinnacle answer plain HTTP clients
    from curl_cffi import requests as _cffi
    HAVE_CFFI = True
except ImportError:  # cloud sandboxes without curl_cffi run the au/nj regions only, on the standard library
    import urllib.error
    import urllib.request
    HAVE_CFFI = False

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/live/pointsbet-alt-monitor"
PB_REGION = os.environ.get("PB_REGION", "on")  # on = PointsBet Ontario (the bettable board); au = PointsBet Australia, same engine, reachable from the cloud
FD_REGION = os.environ.get("FD_REGION", "on")  # on = FanDuel Ontario; nj = FanDuel New Jersey, 99% identical, reachable from the cloud
PB_CFG = {"on": ("https://api.on.pointsbet.com/api", {"Accept": "application/json", "Origin": "https://on.pointsbet.com", "Referer": "https://on.pointsbet.com/"}),
          "au": ("https://api.au.pointsbet.com/api", {"Accept": "application/json"})}
FD_CFG = {"on": ("https://sbapi.on.sportsbook.fanduel.ca/api", {"Accept": "application/json", "Origin": "https://sportsbook.fanduel.ca", "Referer": "https://sportsbook.fanduel.ca/"}),
          "nj": ("https://sbapi.nj.sportsbook.fanduel.com/api", {"Accept": "application/json", "Origin": "https://sportsbook.fanduel.com", "Referer": "https://sportsbook.fanduel.com/"})}
PB, PB_H = PB_CFG[PB_REGION]
FD, FD_H = FD_CFG[FD_REGION]
PIN = "https://guest.api.arcadia.pinnacle.com/0.1"
PIN_H = {"Accept": "application/json", "X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"}  # public key embedded in Pinnacle's web client
FD_AK = "FhMFpcPWXMeyZxOx"  # public key embedded in FanDuel's web client
FD_TZ = "America%2FToronto"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
ARB_NEAR = 1.01
PB_BOOK = f"pointsbet_{PB_REGION}"
FD_BOOK = f"fanduel_{FD_REGION}"

# Every league PointsBet Ontario runs same-game multis on and Pinnacle quotes. PointsBet competition keys differ per
# region, so they are resolved by name at run time; Pinnacle league ids are resolved by name with these as fallback.
LEAGUES = {
    "nfl": dict(sport="football", pb_sport="american-football", pb_names=["NFL"], pin_sport=15, pin_league=889, pin_name="NFL", fd_page="nfl"),
    "ncaaf": dict(sport="football", pb_sport="american-football", pb_names=["NCAAF", "NCAA Football", "College Football"], pin_sport=15, pin_league=880, pin_name="NCAA", fd_page="ncaaf"),
    "cfl": dict(sport="football", pb_sport="american-football", pb_names=["CFL"], pin_sport=15, pin_league=876, pin_name="Canadian Football", fd_page="cfl"),
    "nba": dict(sport="basketball", pb_sport="basketball", pb_names=["NBA"], pin_sport=4, pin_league=487, pin_name="NBA", fd_page="nba"),
    "wnba": dict(sport="basketball", pb_sport="basketball", pb_names=["WNBA"], pin_sport=4, pin_league=578, pin_name="WNBA", fd_page="wnba"),
    "ncaab": dict(sport="basketball", pb_sport="basketball", pb_names=["NCAAB", "NCAA Basketball", "College Basketball"], pin_sport=4, pin_league=493, pin_name="NCAA", fd_page="ncaab"),
    "nhl": dict(sport="hockey", pb_sport="ice-hockey", pb_names=["NHL"], pin_sport=19, pin_league=1456, pin_name="NHL", fd_page="nhl"),
    "mlb": dict(sport="baseball", pb_sport="baseball", pb_names=["MLB"], pin_sport=3, pin_league=246, pin_name="MLB", fd_page="mlb"),
    "epl": dict(sport="soccer", pb_sport="soccer", pb_names=["English Premier League", "Premier League", "EPL"], pin_sport=29, pin_league=1980, pin_name="England - Premier League", fd_comp=10932509),
    "laliga": dict(sport="soccer", pb_sport="soccer", pb_names=["Spanish La Liga", "La Liga"], pin_sport=29, pin_league=2196, pin_name="Spain - La Liga", fd_comp=117),
    "seriea": dict(sport="soccer", pb_sport="soccer", pb_names=["Italian Serie A", "Serie A"], pin_sport=29, pin_league=2436, pin_name="Italy - Serie A", fd_comp=81),
    "bundesliga": dict(sport="soccer", pb_sport="soccer", pb_names=["German Bundesliga", "Bundesliga"], pin_sport=29, pin_league=1842, pin_name="Germany - Bundesliga", fd_comp=59),
    "ligue1": dict(sport="soccer", pb_sport="soccer", pb_names=["French Ligue 1", "Ligue 1"], pin_sport=29, pin_league=2036, pin_name="France - Ligue 1", fd_comp=55),
    "ucl": dict(sport="soccer", pb_sport="soccer", pb_names=["UEFA Champions League", "Champions League"], pin_sport=29, pin_league=2627, pin_name="UEFA - Champions League", fd_comp=228),
    "uel": dict(sport="soccer", pb_sport="soccer", pb_names=["UEFA Europa League", "Europa League"], pin_sport=29, pin_league=2630, pin_name="UEFA - Europa League", fd_comp=2005),
    "mls": dict(sport="soccer", pb_sport="soccer", pb_names=["MLS", "Major League Soccer"], pin_sport=29, pin_league=2663, pin_name="USA - Major League Soccer", fd_comp=141),
}
FD_SOCCER_EVENT_TYPE = 1
TWO_WAY = ("spread", "total", "moneyline", "team_total", "prop", "dnb")


def now():
    return datetime.now(timezone.utc)


def get(url, headers, tries=3):
    last = None
    for i in range(tries):
        try:
            if HAVE_CFFI:
                r = _cffi.get(url, headers=headers, impersonate="chrome", timeout=25)
                if r.status_code == 200:
                    return r.json()
                status = r.status_code
            else:
                req = urllib.request.Request(url, headers={**headers, "Accept-Encoding": "identity", "User-Agent": UA})
                try:
                    with urllib.request.urlopen(req, timeout=25) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    status = e.code
            last = f"HTTP {status}"
            if status == 404:
                break
            if status == 429:
                time.sleep(3 * (i + 1))
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(1)
    raise RuntimeError(f"{url}: {last}")


def ts(s):
    if not s:
        return None
    s = s.replace("Z", "")
    if "." in s:
        a, b = s.split(".")
        s = f"{a}.{b[:6]}"
    if "+" not in s[10:] and "-" not in s[10:]:
        s += "+00:00"
    return datetime.fromisoformat(s)


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100 if a > 0 else 100 / -a)


# ---------------- names ----------------
TEAM_ALIASES = {  # normalised prefix -> canonical; both books pass through this before comparison
    "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united", "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur", "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers", "nottm forest": "nottingham forest",
    "psg": "paris saint germain", "paris sg": "paris saint germain", "inter": "inter milan", "internazionale": "inter milan", "atletico": "atletico madrid",
    "atletico de madrid": "atletico madrid", "athletic club": "athletic bilbao", "sporting lisbon": "sporting cp", "sporting": "sporting cp",
    "bayern munchen": "bayern munich", "fc koln": "cologne", "koln": "cologne", "leverkusen": "bayer leverkusen", "gladbach": "borussia monchengladbach",
    "ole miss": "mississippi", "miami fl": "miami", "miami florida": "miami", "miami oh": "miami ohio", "ul lafayette": "louisiana lafayette",
    "la": "los angeles", "british columbia": "bc", "uconn": "connecticut", "umass": "massachusetts", "pitt": "pittsburgh",
    "smu": "southern methodist", "tcu": "texas christian", "byu": "brigham young", "usc": "southern california", "ucf": "central florida",
    "lsu": "louisiana state", "utsa": "texas san antonio", "utep": "texas el paso", "unlv": "nevada las vegas", "fiu": "florida international",
    "fau": "florida atlantic", "nc state": "north carolina state", "app state": "appalachian state", "ul monroe": "louisiana monroe",
    "southern miss": "southern mississippi", "uab": "alabama birmingham", "cal": "california",
}
TEAM_STOP = {"fc", "cf", "sc", "afc", "the", "club"}
PLAYER_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def ascii_fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def norm_team(s):
    s = ascii_fold(s).lower()
    s = re.sub(r"\(.*?\)", " ", s).replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for k, v in TEAM_ALIASES.items():
        if s == k or s.startswith(k + " "):
            if v.startswith(k) and (s == v or s.startswith(v + " ")):
                break  # already the expanded form ("tottenham hotspur" must not become "tottenham hotspur hotspur")
            s = v + s[len(k):]
            break
    return " ".join(t for t in s.split() if t not in TEAM_STOP)


def team_sim(a, b):
    na, nb = norm_team(a), norm_team(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return 0.9
    ratio = SequenceMatcher(None, na, nb).ratio()
    return ratio if na.split()[-1] == nb.split()[-1] else min(ratio, 0.7)  # "New York Giants" vs "New York Jets" share a prefix, not a team


def norm_player(s):
    s = ascii_fold(s).lower().replace(".", " ").replace("'", "").replace(",", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t not in PLAYER_SUFFIX]
    return " ".join(toks)


def resolve_player(key, candidates):
    """Exact normalised match, else an initial form ('a bohm') against a unique full name ('alec bohm')."""
    if key in candidates:
        return key
    toks = key.split()
    if len(toks) < 2:
        return None
    hits = [c for c in candidates if c.split()[-1] == toks[-1] and c.split()[0][:1] == toks[0][:1]
            and (len(toks[0]) == 1 or len(c.split()[0]) == 1 or c.split()[0] == toks[0])]
    return hits[0] if len(hits) == 1 else None


# ---------------- stats ----------------
STAT_SYNONYMS = {
    "passing yards": ["passing yards", "pass yards", "passing yds", "pass yds"],
    "passing touchdowns": ["passing touchdowns", "touchdown passes", "passing tds", "pass tds", "td passes", "passing touchdown"],
    "rushing yards": ["rushing yards", "rush yards", "rushing yds", "rush yds"],
    "receiving yards": ["receiving yards", "rec yards", "receiving yds", "rec yds"],
    "receptions": ["receptions", "catches", "reception"],
    "rushing + receiving yards": ["rushing + receiving yards", "rush + rec yards", "rushing + receiving yds", "rushing and receiving yards"],
    "pass attempts": ["pass attempts", "passing attempts"],
    "pass completions": ["pass completions", "passing completions", "completions"],
    "interceptions": ["interceptions", "interceptions thrown", "ints thrown", "interception"],
    "rush attempts": ["rush attempts", "rushing attempts", "carries"],
    "field goals": ["field goals", "field goals made", "fgs made", "field goal"],
    "touchdowns": ["touchdowns", "touchdown", "tds", "td"],
    "shots on goal": ["shots on goal", "shots", "sog", "shot on goal"],
    "goals": ["goals", "goal", "goalscorer", "goal scorer"],
    "assists": ["assists", "assist"],
    "points": ["points", "point"],
    "home runs": ["home runs", "home run", "hr", "homers"],
    "bases": ["bases", "total bases", "base"],
    "hits": ["hits", "hit"],
    "rbis": ["rbis", "runs batted in", "rbi"],
    "runs": ["runs", "run", "runs scored"],
    "strikeouts": ["strikeouts", "ks", "strikeout"],
    "pitching outs": ["pitching outs", "outs", "outs recorded"],
    "rebounds": ["rebounds", "rebound"],
    "threes made": ["threes made", "threes", "3 pointers made", "three pointers made", "3pt made", "3 pointers", "three pointers", "3 point field goals made", "three point field goals made"],
    "pts + rebs + asts": ["pts + rebs + asts", "points + rebounds + assists", "pra", "points rebounds assists", "points rebounds and assists"],
    "pts + rebs": ["pts + rebs", "points + rebounds", "points rebounds"],
    "pts + asts": ["pts + asts", "points + assists", "points assists"],
    "rebs + asts": ["rebs + asts", "rebounds + assists", "rebounds assists"],
    "steals": ["steals", "steal"],
    "blocks": ["blocks", "block", "blocked shots"],
    "turnovers": ["turnovers", "turnover"],
    "saves": ["saves", "goalie saves", "goaltender saves"],
}
STAT_LOOKUP = {alias: canon for canon, aliases in STAT_SYNONYMS.items() for alias in aliases}
STAT_DROP = re.compile(r"\b(?:player|players|alternate|alt|quarterback|qb|pitcher|total|totals|made|anytime|any time|scorer|to score|to record|to hit a|to hit|recorded|over/under|o/u|the|a|an|at least|or more)\b")


def canon_stat(s):
    s = ascii_fold(s).lower().replace("&", " + ").replace(" and ", " + ")
    s = re.sub(r"\d+\s*\+", " ", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = STAT_DROP.sub(" ", s)
    s = re.sub(r"[^a-z0-9+ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*\+\s*", " + ", s)
    return STAT_LOOKUP.get(s)


# ---------------- periods and market names ----------------
PERIOD_PATTERNS = [
    (re.compile(r"\b(?:1st|first) half\b|\bhalf[- ]time\b|\b1h\b"), 1),
    (re.compile(r"\b(?:2nd|second) half\b|\b2h\b"), 2),
    (re.compile(r"\b(?:1st|first) quarter\b|\b1q\b"), 3),
    (re.compile(r"\b(?:2nd|second) quarter\b|\b2q\b"), 4),
    (re.compile(r"\b(?:3rd|third) quarter\b|\b3q\b"), 5),
    (re.compile(r"\b(?:4th|fourth) quarter\b|\b4q\b"), 6),
    (re.compile(r"\b(?:1st|first) period\b"), 1),
    (re.compile(r"\b(?:2nd|second) period\b"), 2),
    (re.compile(r"\b(?:3rd|third) period\b"), 3),
    (re.compile(r"\b(?:1st|first) (?:5|five) innings\b|\bf5\b"), 1),
    (re.compile(r"\b(?:1st|first) inning\b"), 3),
]
THREE_WAY = re.compile(r"\(?\b(?:3|three)[- ]way\b\)?")
ML_NAMES = {"moneyline", "money line", "match result", "result", "full time result", "match winner", "winner", "fight result", "fight winner", "1x2",
            "head to head", "match betting", "to win", "moneyline no push", "money line no push", "match odds"}
DNB_NAMES = {"draw no bet", "tie no bet"}
SPREAD_NAMES = {"point spread", "spread", "spreads", "puck line", "puckline", "run line", "runline", "pick your own line", "alternate spread", "alternate spreads",
                "alternate point spread", "alternate run line", "alternate run lines", "alternate puck line", "alt spread", "alt run line", "alt puck line", "handicap",
                "asian handicap", "alternate handicap", "alternate handicaps", "line", "goal handicap", "alternate goal handicap", "point spread including overtime"}
TOTAL_NAMES = {"total", "totals", "total points", "total runs", "total goals", "total points over/under", "alternate total", "alternate totals", "alternative total",
               "alternative totals", "alternative total goals", "alternate total runs", "alternate total goals", "alternate total points", "alt total", "alt totals",
               "pick your own total", "pick your own totals", "over/under", "game total", "total goals over/under", "goals", "match goals", "total match goals",
               "total points over/under including overtime", "alternate total goals over/under"}
SKIP_WORDS = ("odd", "even", "exact", "band", "range", "race", "margin", "double", "correct score", "both", "every", "each", "to nil", "clean sheet",
              "overtime", "score first", "scores first", "first team", "team to score", "first to", "1st team", "highest", "lowest", "last ", "first ", "1st ",
              "2nd ", "3rd ", "4th ", "tied", "leader", "most ", "scoring", "scored", "to score", "squares", "parlay", "&", " and ", "either", "win to", "wins",
              "touchdown", "goalscorer", "goal scorer", "punt", "field goal", "drive", "number of", "/full", "extra", "shutout", "no bet half", "listed",
              "next ", "minute", "mins", "inning", "winning", "method", "round", "specials")
PROP_SKIP = ("first", "last", "1st", "2nd", "3rd", "4th", "to record the win", "both halves", "hat-trick", "hat trick", "each", "every", "most ", "top ",
             "race", " and ", "&", "in a row", "consecutive", "drive", "overtime", "milestone", "double double", "triple double", "double-double", "triple-double")


def parse_period(low):
    for pat, p in PERIOD_PATTERNS:
        if pat.search(low):
            return p, pat.sub(" ", low)
    return 0, low


def clean_residual(low, three):
    if three:
        low = THREE_WAY.sub(" ", low)
    low = re.sub(r"\((?:2|two)[- ]way\)", " ", low)
    low = re.sub(r"\(.*?\)", " ", low)
    low = re.sub(r"\s+", " ", low).strip(" -:")
    return re.sub(r"\s+", " ", low)


def classify_team_market(name, home, away, sport, outcomes):
    """PointsBet market name -> (kind, period, side) for game-line style markets, or None."""
    low = ascii_fold(name).lower().strip()
    low = re.sub(r"\s[+-]?\d+(?:\.\d+)?$", "", low)  # "4th Quarter Point Spread -5.5"
    low = re.sub(r"\(including overtime\)|including overtime|incl\. ot|\(incl ot\)", " ", low)
    three = bool(THREE_WAY.search(low))
    period, low = parse_period(low)
    low = clean_residual(low, three)
    if any(w in low for w in SKIP_WORDS):
        return None
    names = {ascii_fold(o.get("name", "")).lower().strip() for o in outcomes}
    has_draw = bool(names & {"draw", "tie", "the draw"})
    if low in DNB_NAMES:
        return "dnb", (6 if sport == "hockey" and period == 0 else period), None
    if low in ML_NAMES:
        if three or has_draw:
            return "moneyline3", (6 if sport == "hockey" and period == 0 else period), None
        return "moneyline", period, None
    if three:
        return None
    if low in SPREAD_NAMES:
        return "spread", period, None
    if low in TOTAL_NAMES:
        return "total", period, None
    m = re.match(r"^(?P<team>.+?)\s+total(?:\s+(?:points|runs|goals))?(?:\s+over/under)?$", low)
    if m:
        t = m.group("team")
        if t in ("home", "hometeam", "home team"):
            return "team_total", period, "home"
        if t in ("away", "awayteam", "away team"):
            return "team_total", period, "away"
        sh, sa = team_sim(t, home), team_sim(t, away)
        if max(sh, sa) >= 0.8:
            return "team_total", period, ("home" if sh >= sa else "away")
    return None


NUM_TAIL = re.compile(r"\s*\(?([+-]?\d+(?:\.\d+)?)\)?\s*(?:goals?|points?|runs?|yards?|yds)?\s*$")
OU_RE = re.compile(r"\b(over|under)\b\s*\(?([+-]?\d+(?:\.\d+)?)?\)?")
PLUS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+")


def side_from_name(text, home, away):
    sh, sa = team_sim(text, home), team_sim(text, away)
    if max(sh, sa) < 0.75:
        return None
    return "home" if sh >= sa else "away"


def parse_team_outcome(name, side_field, points, kind, home, away):
    """-> (sel, line) for a PointsBet/FanDuel game-line outcome, or None."""
    low = ascii_fold(name).lower().strip()
    side = {"home": "home", "away": "away"}.get((side_field or "").lower())
    if kind in ("total", "team_total"):
        m = OU_RE.search(low)
        if not m:
            return None
        line = float(m.group(2)) if m.group(2) is not None else (float(points) if points is not None else None)
        return (m.group(1), line) if line is not None else None
    if kind in ("moneyline", "moneyline3", "dnb"):
        if low in ("draw", "tie", "the draw"):
            return ("draw", 0.0) if kind == "moneyline3" else None
        sel = side or side_from_name(low, home, away)
        return (sel, 0.0) if sel else None
    if kind == "spread":
        m = NUM_TAIL.search(low)
        team_text = NUM_TAIL.sub("", low) if m else low
        line = float(m.group(1)) if m else (float(points) if points is not None else None)
        if line is None:
            return None
        sel = side or side_from_name(team_text, home, away)
        return (sel, line) if sel else None
    return None


def parse_prop_outcome(name, points, market_line):
    """-> (player, sel, line) for a player-prop outcome such as 'Aaron Rodgers Over 215.5', 'Aaron Rodgers 170+', 'Jaylen Warren'."""
    text = ascii_fold(name).strip()
    low = text.lower()
    m = OU_RE.search(low)
    if m:
        player = text[: m.start()].strip(" -")
        line = float(m.group(2)) if m.group(2) is not None else (float(points) if points else None)
        return (player, m.group(1), line) if player and line is not None else None
    m = PLUS_RE.search(low)
    if m:
        player = text[: m.start()].strip(" -")
        return (player, "over", float(m.group(1)) - 0.5) if player else None
    player = re.sub(r"\s+(?:yes|to score|anytime)$", "", text).strip()
    if market_line is not None:
        return player, "over", market_line
    if points is None:
        return None
    p = float(points)
    if p % 1 == 0.5:
        return player, "over", p
    if p >= 1 and p % 1 == 0:
        return player, "over", p - 0.5
    return None


# ---------------- PointsBet ----------------
def pb_competitions(sport_key):
    j = get(f"{PB}/v2/sports/{sport_key}/competitions", PB_H)
    out = {}
    for loc in j.get("locales", []):
        for c in loc.get("competitions", []):
            out.setdefault(c["name"].strip().lower(), c["key"])
    return out


def pb_resolve(leagues):
    """league key -> PointsBet competition key, by name within the sport."""
    found, cache = {}, {}
    for lg in leagues:
        cfg = LEAGUES[lg]
        if cfg["pb_sport"] not in cache:
            try:
                cache[cfg["pb_sport"]] = pb_competitions(cfg["pb_sport"])
            except RuntimeError:
                cache[cfg["pb_sport"]] = {}
        comps = cache[cfg["pb_sport"]]
        for nm in cfg["pb_names"]:
            if nm.lower() in comps:
                found[lg] = comps[nm.lower()]
                break
        else:
            if lg == "nfl" and PB_REGION == "on":
                found[lg] = "6"  # verified Ontario key, used when the competition list cannot be read
    return found


def pb_events(comp_key, t0, horizon):
    evs = []
    for page in range(1, 8):
        j = get(f"{PB}/v2/competitions/{comp_key}/events/featured?includeLive=false&page={page}", PB_H)
        batch = j.get("events", [])
        evs += batch
        if not batch or not j.get("nextPage"):
            break
    out = []
    for e in evs:
        st = ts(e.get("startsAt"))
        if e.get("isLive") or not st or st < t0 - timedelta(minutes=5) or st > horizon:
            continue
        out.append(e)
    return out


def pb_market_rows(d, league, sport, t0):
    home, away = d["homeTeam"], d["awayTeam"]
    rows, unknown = [], []
    base = dict(book=PB_BOOK, league=league, game=d["key"], home=home, away=away, start=d["startsAt"], event=d["key"], sgm=d.get("sgmStatus"))
    for m in d.get("fixedOddsMarkets", []):
        nm = m.get("eventName", "").strip()
        outs = [o for o in m.get("outcomes", []) if not o.get("isHidden") and o.get("isOpenForBetting", True)]
        if not outs or (m.get("groupName") or "").lower() == "listed pitchers":
            continue
        lowname = nm.lower()
        is_alt = any(w in lowname for w in ("alternate", "alternative", "pick your own", "alt "))
        if any(o.get("playerId") for o in outs):
            low = ascii_fold(nm).lower()
            period, low = parse_period(low)
            if period or any(w in low for w in PROP_SKIP):
                continue
            mk = PLUS_RE.search(low)
            market_line = float(mk.group(1)) - 0.5 if mk else None
            stat = canon_stat(low)
            if not stat:
                unknown.append(nm)
                continue
            for o in outs:
                p = parse_prop_outcome(o.get("name", ""), o.get("points"), market_line)
                if not p:
                    continue
                player, sel, line = p
                upd = ts(o.get("priceLastUpdated"))
                rows.append(dict(base, period=0, kind="prop", sel=sel, side=None, line=line, price=float(o["price"]), main=not is_alt, player=player,
                                 player_key=norm_player(player), stat=stat, team=player, updated=upd.isoformat() if upd else None,
                                 age_min=round((t0 - upd).total_seconds() / 60, 1) if upd else None, limit=None))
            continue
        c = classify_team_market(nm, home, away, sport, outs)
        if not c:
            unknown.append(nm)
            continue
        kind, period, side = c
        for o in outs:
            p = parse_team_outcome(o.get("name", ""), o.get("side"), o.get("points"), kind, home, away)
            if not p:
                continue
            sel, line = p
            if kind == "team_total" and side is None:
                side = {"home": "home", "away": "away"}.get((o.get("side") or "").lower())
                if side is None:
                    continue
            upd = ts(o.get("priceLastUpdated"))
            team = {"home": home, "away": away, "draw": "Draw"}.get(sel) if kind != "total" and kind != "team_total" else sel.capitalize()
            rows.append(dict(base, period=period, kind=kind, sel=sel, side=side if kind == "team_total" else None, line=line, price=float(o["price"]),
                             main=(not is_alt and period == 0), player=None, player_key=None, stat=None, team=team,
                             updated=upd.isoformat() if upd else None, age_min=round((t0 - upd).total_seconds() / 60, 1) if upd else None, limit=None))
    return rows, unknown


def pointsbet(leagues, t0, horizon, workers):
    comps = pb_resolve(leagues)
    rows, errors, status, unknown, events = [], [], {}, {}, {}
    todo = []
    for lg, key in comps.items():
        try:
            evs = pb_events(key, t0, horizon)
        except RuntimeError as err:
            errors.append(str(err))
            status[lg] = dict(events=0, error=str(err)[:120])
            continue
        status[lg] = dict(events=len(evs), rows=0)
        for e in evs:
            events[e["key"]] = dict(id=e["key"], league=lg, home=e["homeTeam"], away=e["awayTeam"], start=ts(e["startsAt"]), sgm=e.get("sgmStatus"))
            todo.append((lg, e["key"]))
    for lg in leagues:
        if lg not in comps:
            status[lg] = dict(events=0, error="competition not found on this PointsBet board")

    def fetch(item):
        lg, key = item
        try:
            d = get(f"{PB}/mes/v3/events/{key}", PB_H)
        except RuntimeError as err:
            return lg, key, None, str(err)
        time.sleep(0.15)
        return lg, key, d, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for lg, key, d, err in ex.map(fetch, todo):
            if err:
                errors.append(err)
                continue
            if d.get("isLive"):
                events.pop(key, None)
                continue
            r, unk = pb_market_rows(d, lg, LEAGUES[lg]["sport"], t0)
            rows += r
            status[lg]["rows"] = status[lg].get("rows", 0) + len(r)
            for u in unk:
                unknown[f"{lg}|{u}"] = unknown.get(f"{lg}|{u}", 0) + 1
    return rows, errors, status, unknown, events


# ---------------- Pinnacle ----------------
def pin_resolve(leagues):
    found, cache = {}, {}
    for lg in leagues:
        cfg = LEAGUES[lg]
        if cfg["pin_sport"] not in cache:
            try:
                cache[cfg["pin_sport"]] = {l["name"].strip().lower(): l["id"] for l in get(f"{PIN}/sports/{cfg['pin_sport']}/leagues?all=false", PIN_H)}
            except RuntimeError:
                cache[cfg["pin_sport"]] = {}
        found[lg] = cache[cfg["pin_sport"]].get(cfg["pin_name"].lower(), cfg["pin_league"])
    return found


def pinnacle_league(lg, league_id, t0, horizon):
    mu = get(f"{PIN}/leagues/{league_id}/matchups", PIN_H)
    mk = get(f"{PIN}/leagues/{league_id}/markets/straight", PIN_H)
    games, specials = {}, {}
    for m in mu:
        if m.get("type") == "matchup" and not m.get("parentId"):
            p = {x["alignment"]: x["name"] for x in m.get("participants", [])}
            st = ts(m.get("startTime"))
            if "home" in p and "away" in p and st and not m.get("isLive") and t0 - timedelta(minutes=5) <= st <= horizon:
                games[m["id"]] = dict(id=m["id"], league=lg, home=p["home"], away=p["away"], start=st)
        elif m.get("type") == "special" and m.get("parentId") and (m.get("special") or {}).get("category") == "Player Props":
            specials[m["id"]] = m
    rows = []
    for m in mk:
        limit = next((l["amount"] for l in m.get("limits", []) if l["type"] == "maxRiskStake"), None)
        g = games.get(m["matchupId"])
        if g:
            if m.get("status") not in (None, "open") or m["type"] not in ("spread", "total", "moneyline", "team_total"):
                continue
            period = m.get("period", 0)
            prices = m.get("prices", [])
            kind = m["type"]
            if kind == "moneyline" and any(pr.get("designation") == "draw" for pr in prices):
                kind = "moneyline3"
            base = dict(book="pinnacle", league=lg, game=g["id"], home=g["home"], away=g["away"], start=g["start"].isoformat(), event=g["id"], period=period, kind=kind,
                        main=(not m.get("isAlternate", False) and period == 0), updated=None, age_min=None, limit=limit, player=None, player_key=None, stat=None)
            for pr in prices:
                sel = pr.get("designation")
                line = float(pr.get("points") or 0.0)
                if kind in ("spread", "total", "team_total") and pr.get("points") is None:
                    continue
                team = {"home": g["home"], "away": g["away"], "draw": "Draw"}.get(sel) if kind.startswith("moneyline") or kind == "spread" else sel.capitalize()
                rows.append(dict(base, sel=sel, side=m.get("side") if kind == "team_total" else None, line=line, price=round(american_to_decimal(pr["price"]), 4), team=team))
            continue
        s = specials.get(m["matchupId"])
        if not s or m["type"] != "total":
            continue
        pg = games.get(s["parentId"])
        if not pg:
            continue
        units = s.get("units") or ""
        desc = s["special"].get("description", "")
        stat = canon_stat(units)
        if not stat:
            continue
        cut = re.search(r"\s+total\s+", desc, flags=re.I)  # "Josh Allen Total Passing Yards" -> "Josh Allen"
        player = desc[: cut.start()].strip() if cut else desc.strip()
        pname = {p["id"]: (p.get("name") or "").lower() for p in s.get("participants", [])}
        base = dict(book="pinnacle", league=lg, game=pg["id"], home=pg["home"], away=pg["away"], start=pg["start"].isoformat(), event=pg["id"], period=0, kind="prop",
                    main=True, updated=None, age_min=None, limit=limit, player=player, player_key=norm_player(player), stat=stat, side=None, team=player)
        for pr in m.get("prices", []):
            sel = pname.get(pr.get("participantId"))
            if sel not in ("over", "under") or pr.get("points") is None:
                continue
            rows.append(dict(base, sel=sel, line=float(pr["points"]), price=round(american_to_decimal(pr["price"]), 4)))
    return rows, games


def pinnacle(leagues, t0, horizon, workers):
    ids = pin_resolve(leagues)
    rows, errors, status, events = [], [], {}, {}

    def fetch(lg):
        try:
            r, games = pinnacle_league(lg, ids[lg], t0, horizon)
            return lg, r, games, None
        except RuntimeError as err:
            return lg, [], {}, str(err)

    with ThreadPoolExecutor(max_workers=min(workers, 4)) as ex:
        for lg, r, games, err in ex.map(fetch, leagues):
            if err:
                errors.append(err)
                status[lg] = dict(events=0, rows=0, error=err[:120])
                continue
            rows += r
            events.update(games)
            status[lg] = dict(events=len(games), rows=len(r))
    return rows, errors, status, events


# ---------------- FanDuel ----------------
FD_PERIODS = [(re.compile(r"(?:^|_)(?:1ST|FIRST)_HALF(?:_|$)|HALF-TIME|HALFTIME"), 1), (re.compile(r"(?:^|_)(?:2ND|SECOND)_HALF"), 2),
              (re.compile(r"(?:^|_)(?:1ST|FIRST)_QUARTER|(?:^|_)1ST_QTR"), 3), (re.compile(r"(?:^|_)2ND_QUARTER|(?:^|_)2ND_QTR"), 4),
              (re.compile(r"(?:^|_)3RD_QUARTER|(?:^|_)3RD_QTR"), 5), (re.compile(r"(?:^|_)4TH_QUARTER|(?:^|_)4TH_QTR"), 6),
              (re.compile(r"(?:^|_)1ST_PERIOD"), 1), (re.compile(r"(?:^|_)2ND_PERIOD"), 2), (re.compile(r"(?:^|_)3RD_PERIOD"), 3),
              (re.compile(r"1ST_INNINGS?|FIRST_INNING"), 3)]
FD_SKIP = ("PARLAY", "DOUBLE", "SQUARES", "SPECIAL", "COMBINATION", "_2_UP", "EARLY", "BOTH_", "MARGIN", "CORRECT", "LEAD_AT", "MULTIGOL", "EXACT", "ODD", "RANGE",
           "RACE", "DRIVE", "MOST_", "FIRST_", "LAST_", "SECOND_GOAL", "THIRD_GOAL", "OVERTIME", "MINUTES", "EACH_", "EVERY_", "_X_TEAM", "X_TOUCHDOWN", "X_HOME", "X_AWAY",
           "TEASER", "WIN_BOTH", "WINNING_AT", "TO_WIN_TO_NIL", "CLEAN_SHEET", "PENALTY", "CARDS", "CORNERS", "BOOKING", "SHOTS_ON_TARGET", "NO_PUSH_HALF")
FD_PROP_DROP = {"PLAYER", "PITCHER", "X", "Y", "C", "LOW", "MEDIUM", "HIGH", "ALT", "ALTERNATE", "TOTAL", "CFB", "WNBA", "NBA", "NFL", "NHL", "MLB", "TO", "RECORD",
                "SCORE", "A", "AN", "ANY", "TIME", "SCORER", "THE", "OF", "GAME", "MATCH", "IN"}
FD_YES_ONLY = re.compile(r"ANY_?TIME|_A_|SCORER$|TO_HIT_A|TO_RECORD_A")


def classify_fd_market(mt, runners, sport):
    t = (mt or "").upper()
    if not t or any(w in t for w in FD_SKIP):
        return None
    period = 0
    for pat, p in FD_PERIODS:
        if pat.search(t):
            period, t = p, pat.sub("_", t)
            break
    if "INNING" in t:
        return None
    names = {(r.get("runnerName") or "").strip().lower() for r in runners}
    has_draw = bool(names & {"draw", "tie", "the draw"})
    if "PLAYER" in t or t.startswith("PITCHER") or re.match(r"^TO_(?:HIT|RECORD|SCORE)_", t) or "SCORER" in t:
        if period:
            return None  # Pinnacle player props are full-game only
        mk = PLUS_RE.search(t)
        core = re.sub(r"^TO_HIT_(?:A_)?", "", t)
        words = [w for w in re.split(r"[_\-/ ]+", re.sub(r"\d+\+", " ", core)) if w and w not in FD_PROP_DROP and not w[0].isdigit()]
        stat = canon_stat(" ".join(words))
        if not stat:
            return None
        market_line = float(mk.group(1)) - 0.5 if mk else (0.5 if FD_YES_ONLY.search(t) else None)
        return "prop", 0, None, stat, market_line
    hockey_reg = 6 if sport == "hockey" and period == 0 else period
    if "DRAW_NO_BET" in t or "TIE_NO_BET" in t:
        return "dnb", hockey_reg, None, None, None
    if "WIN-DRAW-WIN" in t or "RESULT" in t or "MATCH_BETTING" in t or "3-WAY" in t or "THREE_WAY" in t or "(3_WAY)" in t:
        return ("moneyline3", hockey_reg, None, None, None) if (has_draw or "3" in t or "THREE" in t) else ("moneyline", period, None, None, None)
    if "MONEY_LINE" in t or "MONEYLINE" in t or t.endswith("WINNER") or t == "WINNER":
        return ("moneyline3", hockey_reg, None, None, None) if has_draw else ("moneyline", period, None, None, None)
    if "TOTAL" in t or "OVER_UNDER" in t or "OVER/UNDER" in t:
        side = "home" if re.search(r"(?:^|_)HOME_", t) else "away" if re.search(r"(?:^|_)AWAY_", t) else None
        return ("team_total", period, side, None, None) if side else ("total", period, None, None, None)
    if "HANDICAP" in t or "PUCK_LINE" in t or "PUCKLINE" in t or "RUN_LINE" in t or "SPREAD" in t or re.search(r"_[+-]\d+\.5_GOALS", t):
        return "spread", period, None, None, None
    return None


def fd_page_events(cfg_pages, t0, horizon):
    """-> {league: [event dict]} from FanDuel custom pages (US sports) and the soccer sport page (filtered by competition)."""
    out, errors = {}, []
    soccer = None
    for lg, cfg in cfg_pages.items():
        try:
            if "fd_page" in cfg:
                page = get(f"{FD}/content-managed-page?page=CUSTOM&customPageId={cfg['fd_page']}&pbHorizontal=false&_ak={FD_AK}&timezone={FD_TZ}", FD_H)
                evs = page["attachments"].get("events", {}).values()
            else:
                if soccer is None:
                    soccer = get(f"{FD}/content-managed-page?page=SPORT&eventTypeId={FD_SOCCER_EVENT_TYPE}&_ak={FD_AK}&timezone={FD_TZ}", FD_H)
                evs = [v for v in soccer["attachments"].get("events", {}).values() if v.get("competitionId") == cfg["fd_comp"]]
        except RuntimeError as err:
            errors.append(str(err))
            out[lg] = None
            continue
        lst = []
        for e in evs:
            nm = e.get("name", "")
            sep = " @ " if " @ " in nm else " v " if " v " in nm else None
            if not sep or e.get("inPlay"):
                continue
            a, b = [re.sub(r"\s*\(.*?\)", "", x).strip() for x in nm.split(sep, 1)]
            home, away = (b, a) if sep == " @ " else (a, b)
            st = ts(e.get("openDate"))
            if not st or st < t0 - timedelta(minutes=5) or st > horizon:
                continue
            lst.append(dict(id=str(e.get("eventId") or ""), league=lg, home=home, away=away, start=st))
        out[lg] = lst
    return out, errors


def fd_event_rows(d, ev, sport):
    rows = []
    home, away = ev["home"], ev["away"]
    base = dict(book=FD_BOOK, league=ev["league"], game=ev["id"], home=home, away=away, start=ev["start"].isoformat(), event=ev["id"], updated=None, age_min=None, limit=None)
    for m in d["attachments"].get("markets", {}).values():
        if m.get("marketStatus") != "OPEN":
            continue
        runners = [r for r in m.get("runners", []) if r.get("runnerStatus") == "ACTIVE"]
        c = classify_fd_market(m.get("marketType"), runners, sport)
        if not c:
            continue
        kind, period, side, stat, market_line = c
        mt = (m.get("marketType") or "").upper()
        is_alt = "ALT" in mt
        for rn in runners:
            price = rn.get("winRunnerOdds", {}).get("trueOdds", {}).get("decimalOdds", {}).get("decimalOdds")
            if not price:
                continue
            name = rn.get("runnerName", "")
            hcap = rn.get("handicap")
            hcap = float(hcap) if hcap not in (None, 0, "0") else None
            if kind == "prop":
                p = parse_prop_outcome(name, hcap, market_line)
                if not p and OU_RE.search(name.lower()):  # runner is just "Over" / "Under"; the player sits in "Aaron Nola - Strikeouts"
                    p = parse_prop_outcome(f"{(m.get('marketName') or '').split(' - ')[0].strip()} {name}", hcap, market_line)
                if not p:
                    continue
                player, sel, line = p
                rows.append(dict(base, period=0, kind="prop", sel=sel, side=None, line=line, price=round(float(price), 4), main=not is_alt, player=player,
                                 player_key=norm_player(player), stat=stat, team=player))
                continue
            p = parse_team_outcome(name, None, hcap, kind, home, away)
            if not p:
                continue
            sel, line = p
            team = {"home": home, "away": away, "draw": "Draw"}.get(sel) if kind not in ("total", "team_total") else sel.capitalize()
            rows.append(dict(base, period=period, kind=kind, sel=sel, side=side, line=line, price=round(float(price), 4), main=(not is_alt and period == 0),
                             player=None, player_key=None, stat=None, team=team))
    return rows


def fanduel(leagues, t0, horizon, workers):
    pages = {lg: LEAGUES[lg] for lg in leagues if "fd_page" in LEAGUES[lg] or "fd_comp" in LEAGUES[lg]}
    by_league, errors = fd_page_events(pages, t0, horizon)
    rows, status, events = [], {}, {}
    todo = []
    for lg, evs in by_league.items():
        if evs is None:
            status[lg] = dict(events=0, rows=0, error="page failed")
            continue
        status[lg] = dict(events=len(evs), rows=0)
        for e in evs:
            events[e["id"]] = e
            todo.append(e)

    def fetch(ev):
        try:
            d = get(f"{FD}/event-page?_ak={FD_AK}&eventId={ev['id']}&tab=popular", FD_H)
        except RuntimeError as err:
            return ev, None, str(err)
        time.sleep(0.15)
        return ev, d, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ev, d, err in ex.map(fetch, todo):
            if err:
                errors.append(err)
                continue
            r = fd_event_rows(d, ev, LEAGUES[ev["league"]]["sport"])
            rows += r
            status[ev["league"]]["rows"] += len(r)
    return rows, errors, status, events


# ---------------- event matching and pairing ----------------
def match_events(pb_events, other_events, max_gap_s=2 * 3600):
    """other event id -> PointsBet event key, by league, team names (both sides >= 0.75) and start time."""
    by_league = {}
    for e in pb_events.values():
        by_league.setdefault(e["league"], []).append(e)
    out = {}
    for oe in other_events.values():
        best = None
        for pe in by_league.get(oe["league"], []):
            if abs((oe["start"] - pe["start"]).total_seconds()) > max_gap_s:
                continue
            hs, as_ = team_sim(oe["home"], pe["home"]), team_sim(oe["away"], pe["away"])
            score = min(hs, as_), hs + as_
            if min(hs, as_) < 0.75:
                hs2, as2 = team_sim(oe["home"], pe["away"]), team_sim(oe["away"], pe["home"])
                if min(hs2, as2) >= 0.75:
                    score = min(hs2, as2), hs2 + as2 - 0.3
            if score[0] >= 0.75 and (best is None or score[1] > best[0]):
                best = (score[1], pe["id"])
        if best:
            out[oe["id"]] = best[1]
    return out


def opposite(r):
    if r["kind"] in ("total", "team_total", "prop"):
        return ("under" if r["sel"] == "over" else "over"), r["line"]
    if r["kind"] == "spread":
        return ("away" if r["sel"] == "home" else "home"), -r["line"]
    if r["kind"] in ("moneyline", "dnb"):
        return ("away" if r["sel"] == "home" else "home"), 0.0
    return None


def row_key(r, sel=None, line=None):
    return (r["game"], r["period"], r["kind"], r.get("side"), r.get("player_key"), r.get("stat"), float(line if line is not None else r["line"]), sel or r["sel"])


def index_rows(rows):
    idx, players = {}, {}
    for r in rows:
        idx.setdefault(row_key(r), r)
        if r["kind"] == "prop":
            players.setdefault((r["game"], r["stat"]), set()).add(r["player_key"])
    return idx, players


def lookup(idx, players, r, sel, line=None):
    """Other-book row matching a PointsBet row's selection (resolving abbreviated player names), or None."""
    if r["kind"] == "prop":
        pk = resolve_player(r["player_key"], players.get((r["game"], r["stat"]), ()))
        if not pk:
            return None
        return idx.get((r["game"], r["period"], "prop", None, pk, r["stat"], float(line if line is not None else r["line"]), sel))
    return idx.get(row_key(r, sel, line))


def leg_label(r):
    k = r["kind"]
    if k == "spread":
        return f"{r['team']} {r['line']:+g}"
    if k == "total":
        return f"{r['team']} {r['line']:g}"
    if k == "team_total":
        return f"{r['home'] if r['side'] == 'home' else r['away']} {r['sel'].capitalize()} {r['line']:g}"
    if k == "prop":
        return f"{r['player']} {r['sel'].capitalize()} {r['line']:g} {r['stat']}"
    if k == "dnb":
        return f"{r['team']} DNB"
    return r["team"]


PERIOD_LABEL = {"football": {1: "1H", 2: "2H", 3: "Q1", 4: "Q2", 5: "Q3", 6: "Q4"}, "basketball": {1: "1H", 2: "2H", 3: "Q1", 4: "Q2", 5: "Q3", 6: "Q4"},
                "hockey": {1: "P1", 2: "P2", 3: "P3", 6: "REG"}, "baseball": {1: "F5", 3: "1st inn"}, "soccer": {1: "1H", 2: "2H"}}


def market_label(r):
    sport = LEAGUES[r["league"]]["sport"]
    p = PERIOD_LABEL[sport].get(r["period"], str(r["period"]) if r["period"] else "")
    return f"{r['league']} {r['kind']}{' ' + p if p else ''}"


def pin_fair(idx, players, r):
    """Pinnacle no-vig probability for a PointsBet row's selection at the same line, with the Pinnacle prices used."""
    if r["kind"] == "moneyline3":
        sides = ["home", "away", "draw"]
        rows = [idx.get(row_key(r, s)) for s in sides]
        own_i = sides.index(r["sel"])
    elif r["kind"] == "dnb":
        rows = [idx.get((r["game"], r["period"], "moneyline3", None, None, None, 0.0, s)) for s in ("home", "away")]
        own_i = 0 if r["sel"] == "home" else 1
    else:
        opp = opposite(r)
        rows = [lookup(idx, players, r, r["sel"]), lookup(idx, players, r, opp[0], opp[1])]
        own_i = 0
    if any(x is None for x in rows):
        return None
    inv = [1 / x["price"] for x in rows]
    own = rows[own_i]
    fair = inv[own_i] / sum(inv)
    others = [x["price"] for i, x in enumerate(rows) if i != own_i]
    return dict(fair=round(fair, 4), pin_price=own["price"], pin_prices=[own["price"]] + others, limit=own.get("limit"))


def compare(pb_rows, other_rows_by_book):
    """-> (arb pairs vs each book, Pinnacle-fair EV for every PointsBet row with a two-sided Pinnacle quote at the same line)."""
    indexes = {book: index_rows(rows) for book, rows in other_rows_by_book.items()}
    pairs, edges = [], []
    for r in pb_rows:
        label = leg_label(r)
        common = dict(league=r["league"], home=r["home"], away=r["away"], start=r["start"], period=r["period"], kind=r["kind"], market=market_label(r),
                      pb_leg=label, pb_price=r["price"], pb_main=r["main"], pb_age_min=r["age_min"], sgm=r.get("sgm"))
        if r["kind"] in TWO_WAY:
            opp = opposite(r)
            for book, (idx, players) in indexes.items():
                o = lookup(idx, players, r, opp[0], opp[1])
                if o is None:
                    continue
                s = 1 / r["price"] + 1 / o["price"]
                pairs.append(dict(common, other_book=book, other_leg=leg_label(o), other_price=o["price"], other_limit=o.get("limit"), inv_sum=round(s, 4)))
        if "pinnacle" in indexes:
            f = pin_fair(indexes["pinnacle"][0], indexes["pinnacle"][1], r)
            if f:
                edges.append(dict(common, pin_fair=f["fair"], pin_price=f["pin_price"], pin_prices=f["pin_prices"], pin_limit=f["limit"], ev=round(r["price"] * f["fair"] - 1, 4)))
    return pairs, edges


def gap_key(p):
    base = f"{p['away']} @ {p['home']} | {p['market']} | {p['pb_leg']}"
    return f"{base} | {p['other_book']}" if "other_book" in p else f"{base} | pinnacle-fair"


def new_gaps(arbs, edges, threshold, ev_threshold, state_path, t0):
    """Arbs at or below threshold and edges at or above ev_threshold not reported in 24h, or improved since (sum -0.005 / EV +0.01)."""
    state = json.load(open(state_path)) if state_path and Path(state_path).exists() else {}
    fresh = []
    cands = [("arb", p) for p in arbs if threshold is not None and p["inv_sum"] <= threshold]
    cands += [("edge", p) for p in edges if ev_threshold is not None and p["ev"] >= ev_threshold]
    for typ, p in cands:
        key = gap_key(p)
        prev = state.get(key)
        recent = prev and (t0 - datetime.fromisoformat(prev["reported"])).total_seconds() < 86400
        improved = prev and ((typ == "arb" and p["inv_sum"] <= prev.get("inv_sum", 9) - 0.005) or (typ == "edge" and p["ev"] >= prev.get("ev", -9) + 0.01))
        if not recent or improved:
            fresh.append((typ, p))
            state[key] = dict(reported=t0.isoformat(), type=typ, inv_sum=p.get("inv_sum"), ev=p.get("ev"), pb_price=p["pb_price"], other_price=p.get("other_price", p.get("pin_price")))
    state = {k: v for k, v in state.items() if (t0 - datetime.fromisoformat(v["reported"])).total_seconds() < 7 * 86400}
    if state_path:
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        json.dump(state, open(state_path, "w"), indent=1)
    return fresh


def fmt_arb(p):
    return (f"{p['inv_sum']:.4f} ({(1 / p['inv_sum'] - 1) * 100:.1f}% margin)  {p['away']} @ {p['home']} [{p['market']}]: PointsBet {p['pb_leg']} @ {p['pb_price']} "
            f"(rung age {p['pb_age_min']} min, main={p['pb_main']})  vs {p['other_book']} {p['other_leg']} @ {p['other_price']} limit {p['other_limit']}")


def fmt_edge(p):
    return (f"{p['ev'] * 100:+.1f}% EV  {p['away']} @ {p['home']} [{p['market']}]: PointsBet {p['pb_leg']} @ {p['pb_price']} (rung age {p['pb_age_min']} min, main={p['pb_main']})"
            f"  vs Pinnacle fair {p['pin_fair']:.3f} (Pinnacle {p['pin_price']} / {'/'.join(str(x) for x in p['pin_prices'][1:])}, limit {p['pin_limit']})")


def cycle(leagues, threshold=None, ev_threshold=0.03, state_path=None, snapshot=True, workers=4, max_days=7, min_fair=0.1, books=("pinnacle", "fanduel")):
    t0 = now()
    horizon = t0 + timedelta(days=max_days)
    stamp = t0.strftime("%Y%m%dT%H%M%SZ")
    day = OUT / t0.strftime("%Y%m%d")
    day.mkdir(parents=True, exist_ok=True)
    snap, errors, status, timing = [], [], {}, {}
    results = {}

    def run(name, fn):
        t = time.time()
        try:
            results[name] = fn()
        except Exception as e:  # noqa: BLE001
            results[name] = e
        timing[name] = round(time.time() - t, 1)

    jobs = [(PB_BOOK, lambda: pointsbet(leagues, t0, horizon, workers))]
    if "pinnacle" in books:
        jobs.append(("pinnacle", lambda: pinnacle(leagues, t0, horizon, workers)))
    if "fanduel" in books:
        jobs.append((FD_BOOK, lambda: fanduel(leagues, t0, horizon, workers)))
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        list(ex.map(lambda j: run(*j), jobs))
    pb_res = results[PB_BOOK]
    if isinstance(pb_res, Exception):
        status[PB_BOOK] = dict(rows=0, games=0, seconds=timing[PB_BOOK], error=f"{type(pb_res).__name__}: {pb_res}")
        pb_rows, pb_events, unknown = [], {}, {}
    else:
        pb_rows, errs, lg_status, unknown, pb_events = pb_res
        errors += errs
        status[PB_BOOK] = dict(rows=len(pb_rows), games=len(pb_events), seconds=timing[PB_BOOK], errors=len(errs), leagues=lg_status)
    other = {}
    for name in [n for n, _ in jobs if n != PB_BOOK]:
        res = results[name]
        if isinstance(res, Exception):
            status[name] = dict(rows=0, games=0, seconds=timing[name], error=f"{type(res).__name__}: {res}")
            continue
        rows, errs, lg_status, events = res
        errors += errs
        mapping = match_events(pb_events, events)
        kept = []
        for r in rows:
            g = mapping.get(r["game"])
            if g:
                kept.append(dict(r, game=g, matched_from=r["game"]))
        other[name] = kept
        status[name] = dict(rows=len(kept), games=len(set(mapping.values())), unmatched_games=len(events) - len(mapping), seconds=timing[name], errors=len(errs), leagues=lg_status)
    t1 = now()
    snap = pb_rows + [r for rows in other.values() for r in rows]
    allpairs, edges = compare(pb_rows, other)
    arbs = sorted([p for p in allpairs if p["inv_sum"] < 1], key=lambda p: p["inv_sum"])
    near = [p for p in allpairs if 1 <= p["inv_sum"] < ARB_NEAR]
    edges.sort(key=lambda p: -p["ev"])
    pos = [p for p in edges if p["ev"] > 0]  # every positive-EV rung is logged; the console and NEW screens apply the long-shot floor
    screened = [p for p in pos if p["pin_fair"] >= min_fair]
    if snapshot:
        with open(day / f"snapshot-{stamp}.jsonl", "w") as f:
            for r in snap:
                f.write(json.dumps(dict(captured=t0.isoformat(), **r), default=str) + "\n")
    span = round((t1 - t0).total_seconds(), 1)
    with open(OUT / "arbs.jsonl", "a") as f:
        for p in arbs:
            f.write(json.dumps(dict(captured=t0.isoformat(), capture_span_s=span, **p)) + "\n")
    with open(OUT / "edges.jsonl", "a") as f:
        for p in pos:
            f.write(json.dumps(dict(captured=t0.isoformat(), capture_span_s=span, **p)) + "\n")
    top_unknown = sorted(unknown.items(), key=lambda kv: -kv[1])[:20]
    with open(OUT / "cycles.jsonl", "a") as f:
        f.write(json.dumps(dict(captured=t0.isoformat(), regions=dict(pb=PB_REGION, fd=FD_REGION), leagues=leagues, span_s=span, status=status, pairs=len(allpairs),
                                arbs=len(arbs), near=len(near), edges_checked=len(edges), edges_positive=len(pos), errors=errors[:5], unknown_markets=top_unknown)) + "\n")
    ages = [r["age_min"] for r in pb_rows if r["age_min"] is not None]
    med_age = sorted(ages)[len(ages) // 2] if ages else None
    brief = {k: {kk: v.get(kk) for kk in ("rows", "games", "unmatched_games", "seconds", "errors", "error") if v.get(kk) is not None} for k, v in status.items()}
    print(f"{t0:%Y-%m-%d %H:%M:%S}Z span {span:.0f}s | {brief} | pairs {len(allpairs)} arbs {len(arbs)} near {len(near)} | "
          f"edges checked {len(edges)} positive {len(pos)} (fair >= {min_fair}: {len(screened)}) | PB median rung age {med_age} min")
    for p in arbs:
        print(f"  ARB {fmt_arb(p)}")
    for p in sorted(near, key=lambda p: p["inv_sum"])[:5]:
        print(f"  near {fmt_arb(p)}")
    for p in screened[:10]:
        print(f"  EDGE {fmt_edge(p)}")
    if threshold is not None or ev_threshold is not None:
        fresh = new_gaps(arbs, screened, threshold, ev_threshold, state_path, t0)
        print(f"NEW_GAPS {len(fresh)} (arb reciprocal sum <= {threshold} or Pinnacle-fair EV >= {ev_threshold} with fair >= {min_fair}, not reported in 24h)")
        for typ, p in fresh:
            print(f"  NEW {typ.upper()} {fmt_arb(p) if typ == 'arb' else fmt_edge(p)}")
    return arbs, edges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=float, default=0, help="minutes between cycles; 0 = single cycle")
    ap.add_argument("--threshold", type=float, default=None, help="report NEW arb gaps with reciprocal sum at or below this (e.g. 0.98 = 2%% margin)")
    ap.add_argument("--ev-threshold", type=float, default=0.03, help="report NEW edges with PointsBet EV against Pinnacle fair at or above this (default 0.03); negative disables")
    ap.add_argument("--state", default=None, help="JSON file remembering reported gaps across runs (needed for 'new')")
    ap.add_argument("--no-snapshot", action="store_true", help="skip the full per-cycle snapshot file (cloud mode)")
    ap.add_argument("--leagues", default=",".join(LEAGUES), help="comma-separated league keys (default: all): " + ",".join(LEAGUES))
    ap.add_argument("--books", default="pinnacle,fanduel", help="comparison books to pull (default pinnacle,fanduel)")
    ap.add_argument("--workers", type=int, default=4, help="concurrent event fetches per book")
    ap.add_argument("--max-days", type=float, default=7, help="only events starting within this many days")
    ap.add_argument("--min-fair", type=float, default=0.1, help="ignore edges whose Pinnacle fair probability is below this (long-shot tails)")
    a = ap.parse_args()
    if PB_REGION == "on" and not HAVE_CFFI:
        sys.exit("PB_REGION=on needs curl_cffi (pip install curl_cffi); set PB_REGION=au FD_REGION=nj for a plain-client run")
    leagues = [x.strip() for x in a.leagues.split(",") if x.strip()]
    bad = [x for x in leagues if x not in LEAGUES]
    if bad:
        sys.exit(f"unknown league(s) {bad}; choose from {','.join(LEAGUES)}")
    books = tuple(x.strip() for x in a.books.split(",") if x.strip())
    ev_threshold = None if a.ev_threshold is not None and a.ev_threshold < 0 else a.ev_threshold
    while True:
        try:
            cycle(leagues, a.threshold, ev_threshold, a.state, not a.no_snapshot, a.workers, a.max_days, a.min_fair, books)
        except Exception as e:  # noqa: BLE001
            print(f"cycle failed: {type(e).__name__}: {e}", file=sys.stderr)
        if not a.loop:
            break
        time.sleep(a.loop * 60)


if __name__ == "__main__":
    main()
