# %% Market-implied power rankings for the NFL, NBA and NHL
"""
    python -m beating.power build     refresh prices, refit, write docs/power/data/power.json
    python -m beating.power tune      walk-forward check of the half-life and ridge on the stored closing prices
    python -m beating.power calibrate strength drift for the season simulation against Kalshi's playoff prices

A team's power rating is its win probability against a league-average opponent on a neutral field. Nothing
here models football, basketball or hockey: every number is read off prices.

Game prices (home win probability, vig removed):
    kalshi       game-winner markets; mid of the two-sided book, both teams' markets normalised
    polymarket   moneyline markets; mid of best bid and ask
    pinnacle     moneyline from the guest API
    draftkings   moneyline shown on ESPN's scoreboard, and ESPN's stored close for finished games
The consensus for a game is the mean of the sources' log-odds. Ratings come from a ridge regression of those
log-odds on (home team) - (away team) + home advantage [+ back-to-back], with finished games down-weighted by
age. Upcoming games carry full weight, so a rating follows the current lines.

Title odds (Kalshi, Polymarket, Pinnacle futures) then nudge each rating. log(title probability / playoff
probability) is regressed on the game rating across teams; a team priced above that line is rated higher by
the futures market than by its game lines. Up to TITLE_WEIGHT of that gap is applied, less for long shots.

Season outlook. The rest of the regular season is played out SIMS times. A game with a market price uses it;
every other game uses the ratings, with each team's strength drifting week to week as a random walk. The weekly
drift (log-odds: NFL 0.09, NBA 0.15, NHL 0.08) sits between two estimates: how fast the stored ratings have
moved week to week (0.09, 0.17, 0.05) and the value at which simulated playoff odds best match Kalshi's playoff
prices (flat for the NFL, 0.15, about 0.11); `calibrate` re-checks the second. Final standings are seeded by
each league's rules with simplified tie-breaks, giving projected records and the odds of each seed.

Key players out. ESPN's season statistics pick each team's key players: its passing and rushing leaders and top
two receivers (NFL), its top three scorers per game (NBA), its top three point scorers and its busiest goalie
(NHL). Those names are matched against ESPN's injury report.

State kept between runs (all committed, all small):
    data/markets/power/games.csv     one row per game: schedule, result, last pre-game price per source
    data/markets/power/history.csv   one row per team per day: the rating
    data/markets/power/state.json    which schedule dates have been read
    data/markets/power/schedule.json the full regular-season schedule, re-read once a day
Prices are only written before the scheduled start. Once the game is final, the Kalshi price is replaced by the
last hourly candle before the start and the DraftKings price by ESPN's stored close, and the row is frozen.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/markets/power"
LEDGER = DATA / "games.csv"
HISTORY = DATA / "history.csv"
STATE = DATA / "state.json"
SCHEDULE = DATA / "schedule.json"
OUT = ROOT / "docs/power/data/power.json"

ET = ZoneInfo("America/New_York")
ESPN = "https://site.api.espn.com/apis"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
PINNACLE = "https://guest.api.arcadia.pinnacle.com/0.1"
PINNACLE_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # public key embedded in Pinnacle's web client

LEAGUES = {
    "nfl": dict(label="NFL", espn="football/nfl", kalshi_game="KXNFLGAME", kalshi_title="KXSB", kalshi_playoff="KXNFLPLAYOFF",
                kalshi_alias={"JAC": "JAX", "WAS": "WSH"}, pinnacle=889, polymarket_tag=450, polymarket_query="Pro Football Champion",
                half_life=14.0, backfill_days=120, lookahead_days=9, b2b=False, points=True, drift=0.09),
    "nba": dict(label="NBA", espn="basketball/nba", kalshi_game="KXNBAGAME", kalshi_title="KXNBA", kalshi_playoff="KXNBAPLAYOFF",
                kalshi_alias={"GSW": "GS", "NOP": "NO", "NYK": "NY", "SAS": "SA", "UTA": "UTAH", "WAS": "WSH"}, pinnacle=487,
                polymarket_tag=745, polymarket_query="NBA Champion", half_life=5.0, backfill_days=60, lookahead_days=4, b2b=True, points=True, drift=0.15),
    "nhl": dict(label="NHL", espn="hockey/nhl", kalshi_game="KXNHLGAME", kalshi_title="KXNHL", kalshi_playoff="KXNHLPLAYOFF",
                kalshi_alias={"UTA": "UTAH"}, pinnacle=1456, polymarket_tag=899, polymarket_query="NHL Champion",
                half_life=5.0, backfill_days=60, lookahead_days=4, b2b=True, points=False, drift=0.08),
}
SOURCES = ("kalshi", "polymarket", "pinnacle", "draftkings")

MAX_SPREAD = 0.06     # an exchange book wider than this is not a price
P_CLIP = (0.02, 0.98)
RIDGE = 0.1           # pulls a team with few priced games towards league average
B2B_RIDGE = 1.0
TITLE_WEIGHT = 0.25   # most a rating moves towards its title-implied value
TITLE_HALF = 0.02     # title probability at which half of TITLE_WEIGHT applies
TITLE_MIN = 0.003     # below this a title price is a tick-size floor, not an opinion
PLAYOFF_MIN = 0.05    # same for the playoff price
TITLE_CAP = 0.6       # largest title-implied gap, in log-odds
MIN_GAMES_PER_TEAM = 2.0  # age-weighted priced games the average team needs before a league is rated
HISTORY_DAYS = 45
TREND_DAYS = 7
SIMS = 10000
SIM_SEED = 20261119   # fixed, so hour-to-hour changes come from prices and results, not from the draw
SCHEDULE_HOURS = 20   # re-read the season schedule when the stored copy is older than this
SEEDS = {"nfl": ["1", "2", "3", "4", "5", "6", "7"], "nba": [str(i) for i in range(1, 11)], "nhl": ["D1", "D2", "D3", "WC1", "WC2"]}
STATS = "https://site.api.espn.com/apis/common/v3/sports"
# (sort key, players taken per team, positions excluded, label) for each list of key players
KEY_PLAYERS = {
    "nfl": [("passing.passingYards", 1, (), "passing leader"), ("rushing.rushingYards", 1, ("QB",), "rushing leader"),
            ("receiving.receivingYards", 2, (), "top receiver")],
    "nba": [("offensive.avgPoints", 3, (), "points a game")],
    "nhl": [("offensive.points", 3, ("G",), "points"), ("defensive.saves", 1, (), "busiest goalie")],
}
OUT_STATUSES = ("out", "injured reserve", "doubtful", "suspension")
MAYBE_STATUSES = ("day-to-day", "questionable")

FIELDS = ["league", "event_id", "start_utc", "season_type", "home", "away", "neutral", "state", "home_score", "away_score", "closed",
          "kalshi_home_ticker", "kalshi_away_ticker", "kalshi_p", "kalshi_ts", "polymarket_p", "polymarket_ts",
          "pinnacle_home", "pinnacle_away", "pinnacle_ts", "draftkings_home", "draftkings_away", "draftkings_spread", "draftkings_ts"]
HISTORY_FIELDS = ["date", "league", "team", "game_wp", "wp"]


# %% http
def get_json(url, headers=None, tries=5, pause=0.0):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Accept-Encoding": "gzip", **(headers or {})})
    wait, last = 1.0, None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            if pause:
                time.sleep(pause)
            return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (400, 401, 403):
                raise
            last = e  # 429 and 5xx are retried
        except Exception as e:  # noqa: BLE001  timeouts, resets
            last = e
        time.sleep(wait)
        wait = min(wait * 2, 20)
    raise RuntimeError(f"{url.split('?')[0]}: {last}")


def kalshi(path, **params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return get_json(f"{KALSHI}{path}?{q}", pause=0.15, tries=7)


def kalshi_markets(**params):
    out, cursor = [], None
    for _ in range(20):
        d = kalshi("/markets", limit=1000, cursor=cursor, **params) or {}
        out += d.get("markets", [])
        cursor = d.get("cursor")
        if not cursor or not d.get("markets"):
            break
    return out


# %% prices
def american(v):
    """Parse an American price; None when it is not one."""
    if v in (None, ""):
        return None
    s = str(v).strip().upper()
    if s in ("EVEN", "EV"):
        return 100.0
    try:
        x = float(s.replace("+", ""))
    except ValueError:
        return None
    return x if abs(x) >= 100 else None


def american_to_prob(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def devig(implied):
    """Shin's method for a two-way price: the margin is treated as protection against informed bettors, which puts
    more of it on the long shot. On 693 finished games it matched the Kalshi close within 0.03 log-odds at every
    favourite size; a proportional split put 80%+ favourites 0.10 too low and the power method 0.09 too high."""
    a, b = implied
    total = a + b
    if total <= 1 or min(a, b) <= 0:
        return [a / total, b / total]
    z = (total - 1) * ((a - b) ** 2 - total) / (total * ((a - b) ** 2 - 1))
    return [(math.sqrt(z * z + 4 * (1 - z) * x * x / total) - z) / (2 * (1 - z)) for x in (a, b)]


def logit(p):
    p = min(max(p, P_CLIP[0]), P_CLIP[1])
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def book_mid(bid, ask):
    """Mid of a two-sided book, or None when a side is missing or the book is wide."""
    try:
        bid, ask = float(bid), float(ask)
    except (TypeError, ValueError):
        return None
    return (bid + ask) / 2 if 0 < bid < ask < 1 and ask - bid <= MAX_SPREAD else None


def source_probs(row):
    """Home win probability by source for one ledger row."""
    out = {}
    for s in ("kalshi", "polymarket"):
        if row.get(f"{s}_p"):
            out[s] = float(row[f"{s}_p"])
    for s in ("pinnacle", "draftkings"):
        h, a = row.get(f"{s}_home"), row.get(f"{s}_away")
        if h and a:
            out[s] = devig([american_to_prob(float(h)), american_to_prob(float(a))])[0]
    return out


def consensus(row):
    """Mean log-odds across the sources that priced the game."""
    ps = source_probs(row)
    return sum(logit(p) for p in ps.values()) / len(ps) if ps else None


# %% teams
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


class Teams:
    """ESPN's team list for a league, with the lookups each source needs."""

    def __init__(self, rows):
        self.info = {t["abbreviation"]: dict(abbr=t["abbreviation"], id=t.get("id"), name=t["displayName"], nick=t["name"], location=t["location"],
                                             logo=self.logo(t, "default"), logo_dark=self.logo(t, "dark")) for t in rows}
        self.by_nick = {norm(t["nick"]): a for a, t in self.info.items()}
        self.by_name = {norm(t["name"]): a for a, t in self.info.items()}
        self.by_id = {str(t["id"]): t["abbreviation"] for t in rows if t.get("id")}
        self.abbrs = sorted(self.info)

    def espn(self, team):
        """An ESPN team object from any endpoint. Matched on id: ESPN's own abbreviations differ between endpoints
        (the NHL scoreboard says UTA where the team list says UTAH)."""
        return self.by_id.get(str(team.get("id"))) or (team.get("abbreviation") if team.get("abbreviation") in self.info else None)

    @staticmethod
    def logo(team, kind):
        """ESPN's logo for light ("default") or dark backgrounds."""
        want = {"full", kind}
        return next((x["href"] for x in team.get("logos") or [] if set(x.get("rel") or []) == want), None)

    def code(self, code, alias):
        """A Kalshi ticker code."""
        a = alias.get(code, code)
        return a if a in self.info else None

    def name(self, label):
        """A full name ("Los Angeles Clippers", "Montréal Canadiens") or a nickname ("76ers")."""
        n = norm(label)
        if n in self.by_name:
            return self.by_name[n]
        if n in self.by_nick:
            return self.by_nick[n]
        hits = [a for k, a in self.by_nick.items() if n.endswith(" " + k)]
        return hits[0] if len(hits) == 1 else None


def fetch_teams(cfg):
    d = get_json(f"{ESPN}/site/v2/sports/{cfg['espn']}/teams?limit=100")
    return Teams([t["team"] for t in d["sports"][0]["leagues"][0]["teams"]])


def record(text):
    """(wins, losses) from "5-1" or "2-1-0, 0 PTS"."""
    m = re.match(r"\s*(\d+)-(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def fetch_standings(cfg, teams):
    """{abbr: conference, division, record text and the counts the season simulation starts from}"""
    d = get_json(f"{ESPN}/v2/sports/{cfg['espn']}/standings?level=3") or {}
    out = {}
    for conf in d.get("children", []):
        for div in conf.get("children", []):
            for e in (div.get("standings") or {}).get("entries", []):
                st = {x["name"]: x.get("displayValue") for x in e.get("stats", [])}
                num = lambda k: float(st.get(k) or 0)  # noqa: E731
                out[teams.espn(e["team"])] = dict(
                    conf=conf.get("abbreviation") or conf.get("name"), div=div.get("name"),
                    record="-".join(f"{num(k):.0f}" for k in ("wins", "losses", "ties", "otLosses") if k in ("wins", "losses") or num(k) or (k == "otLosses" and k in st)),
                    w=num("wins"), l=num("losses"), t=num("ties"), otl=num("otLosses"), pts=num("points") if "otLosses" in st else 0.0, rw=num("regWins"),
                    div_rec=record(st.get("vs. Div.")), conf_rec=record(st.get("vs. Conf.")))
    return out


# %% schedule and DraftKings (ESPN)
def parse_time(s):
    s = str(s).strip().replace(" ", "T").replace("Z", "+00:00")
    if re.search(r"[+-]\d\d$", s):
        s += ":00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def dk_from_odds(o):
    """(home, away, home spread) from an ESPN odds block, when DraftKings is the provider."""
    if "draftkings" not in ((o.get("provider") or {}).get("name") or "").lower():
        return None
    ml = o.get("moneyline") or {}
    h = american(((ml.get("home") or {}).get("close") or {}).get("odds")) or american((o.get("homeTeamOdds") or {}).get("moneyLine"))
    a = american(((ml.get("away") or {}).get("close") or {}).get("odds")) or american((o.get("awayTeamOdds") or {}).get("moneyLine"))
    return (h, a, o.get("spread")) if h and a else None


def espn_day(cfg, day, teams):
    """Regular-season and playoff games on one Eastern date."""
    d = get_json(f"{ESPN}/site/v2/sports/{cfg['espn']}/scoreboard?dates={day:%Y%m%d}&limit=200") or {}
    out = []
    for e in d.get("events", []):
        if e.get("season", {}).get("type") not in (2, 3):
            continue
        c = e["competitions"][0]
        side = {t["homeAway"]: t for t in c["competitors"]}
        home, away = teams.espn(side["home"]["team"]), teams.espn(side["away"]["team"])
        if not home or not away:
            continue  # all-star and exhibition opponents
        st = e["status"]["type"]
        state = ("off" if st["name"] in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED") else
                 "final" if st.get("completed") else "live" if st.get("state") == "in" else "pre")
        odds = c.get("odds") or []
        out.append(dict(event_id=e["id"], start=parse_time(e["date"]), season_type=e["season"]["type"], home=home, away=away,
                        neutral=int(bool(c.get("neutralSite"))), state=state, home_score=side["home"].get("score", ""),
                        away_score=side["away"].get("score", ""), dk=dk_from_odds(odds[0]) if odds else None))
    return out


def fetch_key_players(lg, cfg, teams):
    """{abbr: [player]} from ESPN's season statistics, by the rules in KEY_PLAYERS."""
    out = defaultdict(dict)
    for sort, take, skip, label in KEY_PLAYERS[lg]:
        q = urllib.parse.urlencode(dict(limit=500, sort=f"{sort}:desc", isqualified="false"))
        d = get_json(f"{STATS}/{cfg['espn']}/statistics/byathlete?{q}") or {}
        cat, name = sort.split(".")
        where = {c["name"]: c.get("names") or [] for c in d.get("categories", [])}

        def value(row, c, n):
            block = next((x for x in row.get("categories", []) if x.get("name") == c), {})
            try:
                return float(str(block["totals"][where[c].index(n)]).replace(",", ""))
            except (KeyError, ValueError, IndexError):
                return 0.0
        played = "games" if lg == "nhl" else "gamesPlayed"
        most = defaultdict(float)
        for row in d.get("athletes", []):
            abbr = teams.by_id.get(str(row["athlete"].get("teamId")))
            most[abbr] = max(most[abbr], value(row, "general", played))
        taken = defaultdict(int)
        for row in d.get("athletes", []):  # already in order of the sort key
            a = row["athlete"]
            abbr, pos = teams.by_id.get(str(a.get("teamId"))), (a.get("position") or {}).get("abbreviation")
            # a per-game average needs a quarter of the team's games behind it
            thin = "avg" in name and value(row, "general", played) < max(3, 0.25 * most[abbr])
            if not abbr or pos in skip or taken[abbr] >= take or thin or value(row, cat, name) <= 0:
                continue
            taken[abbr] += 1
            v = value(row, cat, name)
            out[abbr].setdefault(str(a["id"]), dict(id=str(a["id"]), name=a.get("displayName"), short=a.get("shortName") or a.get("displayName"), pos=pos,
                                                    role=f"{v:g} {label}" if lg != "nfl" and "goalie" not in label else label))
    return {t: list(v.values()) for t, v in out.items()}


def fetch_injuries(cfg, teams):
    """{abbr: [injury]} from ESPN's league injury report."""
    d = get_json(f"{ESPN}/site/v2/sports/{cfg['espn']}/injuries") or {}
    out = defaultdict(list)
    for t in d.get("injuries", []):
        abbr = teams.by_id.get(str(t.get("id"))) or teams.name(t.get("displayName", ""))
        for i in t.get("injuries", []):
            a, det = i.get("athlete") or {}, i.get("details") or {}
            aid = next((m.group(1) for x in a.get("links") or [] if (m := re.search(r"/id/(\d+)", x.get("href", "")))), None)
            out[abbr].append(dict(id=aid, name=a.get("displayName"), status=i.get("status") or "", part=det.get("type"), ret=det.get("returnDate")))
    return out


def key_injuries(players, injuries):
    """A team's season leaders who are on the injury report, players ruled out first."""
    by_id = {i["id"]: i for i in injuries if i["id"]}
    by_name = {norm(i["name"] or ""): i for i in injuries}
    out = []
    for pl in players:
        i = by_id.get(pl["id"]) or by_name.get(norm(pl["name"] or ""))
        status = (i or {}).get("status", "").lower()
        if status in OUT_STATUSES or status in MAYBE_STATUSES:
            out.append(dict(name=pl["name"], short=pl["short"], pos=pl["pos"], role=pl["role"], status=i["status"], part=i["part"], ret=i["ret"],
                            out=status in OUT_STATUSES))
    return sorted(out, key=lambda x: not x["out"])


def fetch_schedule(cfg, teams):
    """Every regular-season game, from each team's schedule: [event_id, start, home, away, neutral]."""
    def one(abbr):
        return (get_json(f"{ESPN}/site/v2/sports/{cfg['espn']}/teams/{teams.info[abbr]['id']}/schedule?seasontype=2") or {}).get("events", [])
    games = {}
    with ThreadPoolExecutor(6) as pool:
        for events in pool.map(one, teams.abbrs):
            for e in events:
                c = e["competitions"][0]
                side = {t["homeAway"]: teams.espn(t["team"]) for t in c["competitors"]}
                if side.get("home") and side.get("away"):
                    games[e["id"]] = [e["id"], iso(parse_time(e["date"])), side["home"], side["away"], int(bool(c.get("neutralSite")))]
    return sorted(games.values(), key=lambda g: (g[1], g[0]))


def espn_close(cfg, event_id):
    """DraftKings closing prices stored on ESPN's game page."""
    d = get_json(f"{ESPN}/site/v2/sports/{cfg['espn']}/summary?event={event_id}") or {}
    pc = d.get("pickcenter") or []
    return dk_from_odds(pc[0]) if pc else None


# %% ledger
def load_ledger():
    if not LEDGER.exists():
        return {}
    with LEDGER.open() as f:
        return {(r["league"], r["event_id"]): {k: r.get(k, "") for k in FIELDS} for r in csv.DictReader(f)}


def write_csv(path, fields, rows):
    """Write to a temporary file and swap it in, so a failed run never leaves a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")  # drops derived keys such as _b2b
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def save_ledger(ledger):
    write_csv(LEDGER, FIELDS, sorted(ledger.values(), key=lambda r: (r["league"], r["start_utc"], r["event_id"])))


def upsert(ledger, lg, g, now):
    row = ledger.setdefault((lg, g["event_id"]), {k: "" for k in FIELDS})
    row.update(league=lg, event_id=g["event_id"], start_utc=iso(g["start"]), season_type=g["season_type"], home=g["home"], away=g["away"],
               neutral=g["neutral"], state=g["state"], home_score=g["home_score"], away_score=g["away_score"])
    if g["dk"] and open_for_quotes(row, now):
        set_book(row, "draftkings", g["dk"], now)
    return row


def open_for_quotes(row, now):
    """Prices are only accepted before the scheduled start."""
    return row["state"] == "pre" and parse_time(row["start_utc"]) > now


def set_book(row, source, price, ts):
    row[f"{source}_home"], row[f"{source}_away"] = f"{price[0]:.0f}", f"{price[1]:.0f}"
    if source == "draftkings" and price[2] is not None:
        row["draftkings_spread"] = price[2]
    row[f"{source}_ts"] = iso(ts)


def set_prob(row, source, p, ts):
    row[f"{source}_p"], row[f"{source}_ts"] = f"{p:.4f}", iso(ts)


class Index:
    """Find a league's ledger row by team pair and approximate start time."""

    def __init__(self, rows):
        self.pairs = defaultdict(list)
        for r in rows:
            self.pairs[frozenset((r["home"], r["away"]))].append(r)

    def find(self, a, b, t, tol_hours=18):
        best = min(self.pairs.get(frozenset((a, b)), []), key=lambda r: abs(parse_time(r["start_utc"]) - t), default=None)
        return best if best and abs(parse_time(best["start_utc"]) - t) <= timedelta(hours=tol_hours) else None


# %% Kalshi games
def kalshi_events(markets, cfg, teams):
    """{event_ticker: {"t": approximate start, "mk": {abbr: market}}} for two-team game events."""
    ev = {}
    for m in markets:
        abbr = teams.code(m["ticker"].rsplit("-", 1)[-1], cfg["kalshi_alias"])
        if abbr and m.get("occurrence_datetime"):
            # the listed occurrence time is the expected end, about three hours after the start
            e = ev.setdefault(m["event_ticker"], {"mk": {}, "t": parse_time(m["occurrence_datetime"]) - timedelta(hours=3)})
            e["mk"][abbr] = m
    return {k: v for k, v in ev.items() if len(v["mk"]) == 2}


def two_sided(mid_home, mid_away):
    """Home probability from the two teams' YES mids."""
    if mid_home and mid_away:
        return mid_home / (mid_home + mid_away)
    return mid_home if mid_home else 1 - mid_away if mid_away else None


def kalshi_live(cfg, teams, index, now, all_markets=False):
    """Attach Kalshi tickers to ledger rows and price the games that have not started."""
    markets = kalshi_markets(series_ticker=cfg["kalshi_game"], status=None if all_markets else "open")
    n = 0
    for e in kalshi_events(markets, cfg, teams).values():
        (a, ma), (b, mb) = e["mk"].items()
        row = index.find(a, b, e["t"])
        if not row:
            continue
        by = {a: ma, b: mb}
        row["kalshi_home_ticker"], row["kalshi_away_ticker"] = by[row["home"]]["ticker"], by[row["away"]]["ticker"]
        if open_for_quotes(row, now):
            p = two_sided(*(book_mid(by[t].get("yes_bid_dollars"), by[t].get("yes_ask_dollars")) for t in (row["home"], row["away"])))
            if p:
                set_prob(row, "kalshi", p, now)
                n += 1
    return n


def candle_mid(candles, start_ts):
    """Mid (or last trade) of the last hourly candle that ended by the start."""
    cs = [c for c in candles if c["end_period_ts"] <= start_ts + 60]
    if not cs:
        return None, None
    c = max(cs, key=lambda c: c["end_period_ts"])
    mid = book_mid((c.get("yes_bid") or {}).get("close_dollars"), (c.get("yes_ask") or {}).get("close_dollars"))
    if mid is None:
        try:
            last = float((c.get("price") or {}).get("close_dollars"))
            mid = last if 0 < last < 1 else None
        except (TypeError, ValueError):
            mid = None
    return mid, c["end_period_ts"]


def kalshi_close(rows):
    """Replace the Kalshi price of started games with the last pre-game hourly candle."""
    days = defaultdict(list)
    for r in rows:
        if r["kalshi_home_ticker"]:
            days[r["start_utc"][:10]].append(r)
    n = 0
    for day_rows in days.values():
        for i in range(0, len(day_rows), 20):
            chunk = day_rows[i:i + 20]
            starts = [int(parse_time(r["start_utc"]).timestamp()) for r in chunk]
            d = kalshi("/markets/candlesticks", market_tickers=",".join(t for r in chunk for t in (r["kalshi_home_ticker"], r["kalshi_away_ticker"])),
                       start_ts=min(starts) - 4 * 3600, end_ts=max(starts) + 60, period_interval=60) or {}
            candles = {m["market_ticker"]: m.get("candlesticks", []) for m in d.get("markets", [])}
            for r, start in zip(chunk, starts):
                (mh, th), (ma, ta) = (candle_mid(candles.get(r[f"kalshi_{s}_ticker"], []), start) for s in ("home", "away"))
                p = two_sided(mh, ma)
                if p:
                    set_prob(r, "kalshi", p, datetime.fromtimestamp(max(t for t in (th, ta) if t), timezone.utc))
                    n += 1
    return n


# %% Polymarket and Pinnacle games
def polymarket_live(cfg, teams, index, now):
    n = 0
    for page in range(3):
        q = urllib.parse.urlencode(dict(sports_market_types="moneyline", tag_id=cfg["polymarket_tag"], closed="false", limit=100, offset=100 * page,
                                        order="gameStartTime", ascending="true", end_date_min=iso(now)))
        ms = get_json(f"{GAMMA}/markets?{q}") or []
        for m in ms:
            if not m.get("gameStartTime"):
                continue
            pair = [teams.name(o) for o in json.loads(m.get("outcomes") or "[]")]
            if len(pair) != 2 or None in pair:
                continue
            row = index.find(pair[0], pair[1], parse_time(m["gameStartTime"]), tol_hours=6)
            p = book_mid(m.get("bestBid"), m.get("bestAsk"))  # price of the first outcome
            if row and p and open_for_quotes(row, now):
                set_prob(row, "polymarket", p if pair[0] == row["home"] else 1 - p, now)
                n += 1
        if len(ms) < 100:
            break
    return n


def pinnacle_get(path):
    return get_json(f"{PINNACLE}{path}", headers={"X-API-Key": PINNACLE_KEY}) or []


def pinnacle_live(matchups, markets, teams, index, now):
    ml = {k["matchupId"]: k for k in markets if k.get("type") == "moneyline" and k.get("period") == 0 and not k.get("isAlternate") and k.get("status") == "open"}
    n = 0
    for m in matchups:
        if m.get("type") != "matchup" or m.get("isLive") or m["id"] not in ml:
            continue
        side = {p.get("alignment"): teams.name(p.get("name", "")) for p in m.get("participants", [])}
        price = {p.get("designation"): american(p.get("price")) for p in ml[m["id"]].get("prices", [])}
        if not (side.get("home") and side.get("away") and price.get("home") and price.get("away")):
            continue
        row = index.find(side["home"], side["away"], parse_time(m["startTime"]), tol_hours=6)
        if row and open_for_quotes(row, now):
            flip = side["home"] != row["home"]  # neutral-site games can list the teams the other way round
            set_book(row, "pinnacle", (price["away" if flip else "home"], price["home" if flip else "away"], None), now)
            n += 1
    return n


# %% title and playoff odds
def normalise(q, n_teams):
    """Scale a venue's title prices to sum to one; None unless most of the league is priced."""
    q = {t: v for t, v in q.items() if v and v > 0}
    total = sum(q.values())
    return {t: v / total for t, v in q.items()} if len(q) >= 0.6 * n_teams and total > 0 else None


def kalshi_board(series, cfg, teams):
    """{abbr: price} for the open event of a per-team futures series. A one-sided book (no bid) is priced at half the ask."""
    events = (kalshi("/events", series_ticker=series, status="open", limit=20) or {}).get("events", [])
    out = {}
    for e in events:
        board = {}
        for m in kalshi_markets(event_ticker=e["event_ticker"]):
            abbr = teams.code(m["ticker"].rsplit("-", 1)[-1], cfg["kalshi_alias"])
            bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
            if abbr and m.get("status") == "active" and 0 < ask <= 1:
                board[abbr] = (bid + ask) / 2 if ask - bid <= MAX_SPREAD else float(m.get("last_price_dollars") or 0)
        if len(board) > len(out):
            out = board
    return out


def polymarket_title(cfg, teams):
    """Champion market: the highest-volume open event that prices most of the league and is not a conference,
    division or in-season cup market."""
    q = urllib.parse.urlencode(dict(q=cfg["polymarket_query"], limit_per_type=20, events_status="active"))
    best, best_vol = {}, -1.0
    for e in (get_json(f"{GAMMA}/public-search?{q}") or {}).get("events", []):
        if e.get("closed") or re.search(r"conference|division|to reach|cup championship|nba cup", e.get("title", ""), re.I):
            continue
        board = {}
        for m in e.get("markets", []):
            abbr = teams.name(m.get("groupItemTitle") or "")
            if abbr and m.get("active") and not m.get("closed") and m.get("bestAsk") is not None:
                bid, ask = float(m.get("bestBid") or 0), float(m["bestAsk"])
                if 0 < ask <= 1 and ask - bid <= MAX_SPREAD:
                    board[abbr] = (bid + ask) / 2
        vol = float(e.get("volume") or 0)
        if len(board) >= 0.6 * len(teams.info) and vol > best_vol:
            best, best_vol = board, vol
    return best


def pinnacle_title(matchups, markets, teams):
    """Champion futures: the futures special that prices most of the league (conference markets price half)."""
    prices = {k["matchupId"]: k for k in markets if k.get("type") == "moneyline"}
    best = {}
    for m in matchups:
        sp = m.get("special") or {}
        if m.get("type") != "special" or sp.get("category") != "Futures" or m["id"] not in prices:
            continue
        names = {p["id"]: teams.name(p.get("name", "")) for p in m.get("participants", [])}
        board = {}
        for p in prices[m["id"]].get("prices", []):
            abbr, a = names.get(p.get("participantId")), american(p.get("price"))
            if abbr and a:
                board[abbr] = american_to_prob(a)
        if len(board) >= 0.6 * len(teams.info) and len(board) > len(best):
            best = board
    return best


# %% model
def add_b2b(rows):
    """Flag the second night of a back-to-back: +1 home team only, -1 away team only."""
    starts = defaultdict(list)
    for r in rows:
        if r["state"] != "off":
            t = parse_time(r["start_utc"])
            starts[r["home"]].append(t)
            starts[r["away"]].append(t)
    for r in rows:
        t = parse_time(r["start_utc"])
        played = [any(timedelta(0) < t - s <= timedelta(hours=30) for s in starts[r[side]]) for side in ("home", "away")]
        r["_b2b"] = int(played[0]) - int(played[1])


def fit_inputs(rows, now, lookahead_days, half_life):
    """Priced games as of `now`: recent started games, plus games starting within the look-ahead."""
    out = []
    for r in rows:
        start = parse_time(r["start_utc"])
        if r["state"] == "off" or start > now + timedelta(days=lookahead_days) or start < now - timedelta(days=10 * half_life):
            continue
        if start < now - timedelta(hours=36) and r["state"] != "final":
            continue  # never finished (postponed without a status change)
        y = consensus(r)
        if y is not None:
            out.append(dict(home=r["home"], away=r["away"], neutral=int(r["neutral"] or 0), start=start, y=y, b2b=r.get("_b2b", 0)))
    return out


def age_weight(start, now, half_life):
    return 0.5 ** (max(0.0, (now - start).total_seconds() / 86400) / half_life)


def enough(games, teams, now, half_life):
    """True when the average team has MIN_GAMES_PER_TEAM age-weighted priced games; false out of season."""
    return 2 * sum(age_weight(g["start"], now, half_life) for g in games) >= MIN_GAMES_PER_TEAM * len(teams)


def fit(games, teams, now, half_life, ridge=RIDGE, b2b=False):
    """Weighted ridge regression of consensus log-odds on home - away + home advantage [+ back-to-back].
    Returns centred ratings (log-odds against an average team), the two game effects and fit diagnostics."""
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    X, y, w = np.zeros((len(games), n + 2)), np.zeros(len(games)), np.zeros(len(games))
    for j, g in enumerate(games):
        X[j, idx[g["home"]]], X[j, idx[g["away"]]] = 1, -1
        X[j, n], X[j, n + 1] = 1 - g["neutral"], g["b2b"] if b2b else 0
        y[j] = g["y"]
        w[j] = age_weight(g["start"], now, half_life)
    pen = np.r_[np.full(n, ridge), 1e-9, B2B_RIDGE if b2b else 1.0]
    beta = np.linalg.solve(X.T @ (X * w[:, None]) + np.diag(pen), X.T @ (w * y))
    resid = y - X @ beta
    r = beta[:n] - beta[:n].mean()
    return dict(ratings=dict(zip(teams, r.tolist())), home=float(beta[n]), b2b=float(beta[n + 1]) if b2b else 0.0,
                rmse=float(np.sqrt((w * resid ** 2).sum() / w.sum())) if len(games) else None,
                n_eff={t: float(w[np.abs(X[:, i]) > 0].sum()) for t, i in idx.items()})


def predict(model, home, away, neutral=0, b2b=0):
    r = model["ratings"]
    return sigmoid(r[home] - r[away] + model["home"] * (1 - neutral) + model["b2b"] * b2b)


def title_blend(ratings, title, playoff, conf):
    """Shift ratings towards what title odds imply.

    Among playoff teams, title probability rises roughly exponentially with strength, so
        log(title / playoff) = a + k * rating [+ conference] + e
    is fitted across teams (weight rises with title probability). e / k is the gap, in log-odds, between the
    rating the futures imply and the game rating. Returns ({team: {gap, weight}}, fit summary), or (None, why).
    """
    teams = [t for t in ratings if title.get(t, 0) >= TITLE_MIN and (not playoff or playoff.get(t, 0) >= PLAYOFF_MIN)]
    if len(teams) < 8:
        return None, "too few teams with title prices"
    q = np.array([title[t] for t in teams])
    made = np.array([min(playoff[t], 1.0) for t in teams]) if playoff else np.ones(len(teams))
    y = np.log(np.minimum(q / made, 0.99))
    om = q / (q + TITLE_HALF)
    confs = sorted({conf.get(t) for t in teams} - {None})
    X = np.column_stack([np.ones(len(teams)), [ratings[t] for t in teams], [1.0 if len(confs) == 2 and conf.get(t) == confs[0] else 0.0 for t in teams]])
    beta = np.linalg.solve(X.T @ (X * om[:, None]) + np.diag([0, 0, 0.5]), X.T @ (om * y))
    k = float(beta[1])
    if k < 0.5:
        return None, f"title odds do not track game ratings (slope {k:.2f})"
    e = y - X @ beta
    out = {t: dict(gap=float(np.clip(e[i] / k, -TITLE_CAP, TITLE_CAP)), weight=float(TITLE_WEIGHT * om[i])) for i, t in enumerate(teams)}
    return out, dict(slope=k, resid_sd=float(np.sqrt((om * e ** 2).sum() / om.sum())), conference=float(beta[2]),
                     conference_label=confs[0] if len(confs) == 2 else None, n=len(teams))


def points_scale(rows):
    """Standard deviation s such that P(home wins) = Phi(-spread / s), from DraftKings spread and moneyline pairs."""
    nd, num, den = statistics.NormalDist(), 0.0, 0.0
    for r in rows:
        p = source_probs(r).get("draftkings")
        try:
            s = float(r["draftkings_spread"])
        except (TypeError, ValueError):
            continue
        if p and 0.03 < p < 0.97 and s:
            num += -s * nd.inv_cdf(p)
            den += s * s
    return den / num if num > 0 and den > 0 else None


# %% season simulation
def remaining_games(schedule, rows, now):
    """Regular-season games still to be decided, with the market's log-odds where a game is priced."""
    by_id = {r["event_id"]: r for r in rows}
    starts = defaultdict(list)
    for _, start, home, away, _ in schedule:
        t = parse_time(start)
        starts[home].append(t)
        starts[away].append(t)
    out = []
    for eid, start, home, away, neutral in schedule:
        row, t = by_id.get(eid), parse_time(start)
        if row:
            if row["state"] == "final" or int(row["season_type"] or 2) != 2:
                continue
            t = parse_time(row["start_utc"])
        elif t < now - timedelta(hours=12):
            continue  # played before the ledger's window: already in the standings
        tired = [any(timedelta(0) < t - x <= timedelta(hours=30) for x in starts[side]) for side in (home, away)]
        out.append(dict(home=home, away=away, neutral=int(neutral), start=t, y=consensus(row) if row else None, b2b=int(tired[0]) - int(tired[1])))
    return out


def rank_desc(key):
    """Rank within each row, 0 = largest."""
    order = np.argsort(-key, axis=1)
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.broadcast_to(np.arange(key.shape[1]), key.shape), axis=1)
    return rank


def simulate(lg, abbrs, stand, games, model, drift, now, n=SIMS, seed=SIM_SEED, p_ot=0.23):
    """Play out the remaining regular season n times and seed each conference.

    Strength: rating + a random walk with one step of sd `drift` (log-odds) per week, the first step now. A priced
    game uses the market's probability unchanged. Tie-breaks are simplified, with no head-to-head:
        nfl  division: record, division record, conference record, coin. Seeds 1-4 are the division winners
             and 5-7 the wild cards, each ordered by record, conference record, coin.
        nba  record, conference record, coin; seeds 7-10 then play the play-in for the last two places.
        nhl  points, regulation wins, coin. D1-D3 are a division's top three, WC1-WC2 the next two in the conference.
    Returns {abbr: {w, l, otl, pts, playoff, seeds, div, top, playin}} with means and probabilities."""
    rng = np.random.default_rng(seed)
    T, G = len(abbrs), len(games)
    idx = {t: i for i, t in enumerate(abbrs)}
    st = [stand.get(t) or dict(conf=None, div=None, w=0, l=0, t=0, otl=0, pts=0, rw=0, div_rec=(0, 0), conf_rec=(0, 0)) for t in abbrs]
    col = lambda f: np.array([f(x) for x in st], dtype=float)  # noqa: E731
    r = np.array([model["ratings"][t] for t in abbrs])
    h, a = (np.array([idx[g[k]] for g in games], dtype=int) for k in ("home", "away"))
    week = np.array([min(60, max(0, (g["start"] - now).days // 7)) for g in games], dtype=int)
    steps = int(week.max()) + 1 if G else 1
    walk = np.cumsum(rng.normal(0, drift, (n, steps, T)), axis=1, dtype=np.float32) if drift > 0 else np.zeros((n, steps, T), np.float32)
    base = r[h] - r[a] + model["home"] * (1 - np.array([g["neutral"] for g in games])) + model["b2b"] * np.array([g["b2b"] for g in games]) if G else np.zeros(0)
    priced = np.array([g["y"] is not None for g in games], dtype=bool)
    base = np.where(priced, [g["y"] or 0.0 for g in games], base)
    shift = walk[:, week, h] - walk[:, week, a]
    shift[:, priced] = 0
    home_win = (rng.random((n, G), dtype=np.float32) < 1 / (1 + np.exp(-(base[None, :] + shift)))).astype(np.float32)
    H, A = np.zeros((G, T), np.float32), np.zeros((G, T), np.float32)
    H[np.arange(G), h], A[np.arange(G), a] = 1, 1
    tally = lambda mask: (home_win * mask) @ H + ((1 - home_win) * mask) @ A  # noqa: E731  wins in the games where mask is set
    same = lambda key: np.array([st[i][key] is not None and st[i][key] == st[j][key] for i, j in zip(h, a)], np.float32)  # noqa: E731
    one, in_conf, in_div = np.ones(G, np.float32), same("conf"), same("div") * same("conf")
    left = H.sum(0) + A.sum(0)
    add = tally(one)
    wins, losses = col(lambda x: x["w"]) + add, col(lambda x: x["l"]) + left - add
    share = lambda won, lost, mask: (won + tally(mask)) / np.maximum(1, won + lost + mask @ H + mask @ A)  # noqa: E731
    conf_pct = share(col(lambda x: x["conf_rec"][0]), col(lambda x: x["conf_rec"][1]), in_conf)
    div_pct = share(col(lambda x: x["div_rec"][0]), col(lambda x: x["div_rec"][1]), in_div)
    ties = col(lambda x: x["t"])
    pct = (wins + 0.5 * ties) / np.maximum(1, wins + losses + ties)
    coin = rng.random((n, T))
    otl = pts = None
    if lg == "nhl":
        overtime = (rng.random((n, G), dtype=np.float32) < p_ot).astype(np.float32)
        extra = ((1 - home_win) * overtime) @ H + (home_win * overtime) @ A   # losses that earn a point
        otl, losses = col(lambda x: x["otl"]) + extra, losses - extra
        pts = 2 * wins + otl
        reg_wins = col(lambda x: x["rw"]) + (home_win * (1 - overtime)) @ H + ((1 - home_win) * (1 - overtime)) @ A

    slots = len(SEEDS[lg])
    slot = np.full((n, T), -1, dtype=int)          # seed index, -1 = out
    playoff, div_win, top = np.zeros((n, T), bool), np.zeros((n, T), bool), np.zeros((n, T), bool)
    rows_ = np.arange(n)
    for c in sorted({x["conf"] for x in st if x["conf"]}):
        ci = np.array([i for i, x in enumerate(st) if x["conf"] == c])
        divs = [np.array([k for k, i in enumerate(ci) if st[i]["div"] == d]) for d in sorted({st[i]["div"] for i in ci})]
        if lg == "nfl":
            wild = pct[:, ci] + 1e-3 * conf_pct[:, ci] + 1e-6 * coin[:, ci]
            title = pct[:, ci] + 1e-3 * div_pct[:, ci] + 1e-6 * conf_pct[:, ci] + 1e-9 * coin[:, ci]
            won = np.zeros((n, len(ci)), bool)
            for d in divs:
                won[rows_, d[np.argmax(title[:, d], axis=1)]] = True
            rank = rank_desc(wild + 10 * won)
            div_win[:, ci] = won
        elif lg == "nba":
            rank = rank_desc(pct[:, ci] + 1e-4 * conf_pct[:, ci] + 1e-7 * coin[:, ci])
        else:
            key = pts[:, ci] + 1e-3 * reg_wins[:, ci] + 1e-6 * coin[:, ci]
            rank = np.full((n, len(ci)), 99)
            top3 = np.zeros((n, len(ci)), bool)
            for d in divs:
                in_div_rank = rank_desc(key[:, d])
                rank[:, d] = np.where(in_div_rank < 3, in_div_rank, 99)
                top3[:, d] = in_div_rank < 3
            rank = np.where(top3, rank, 3 + rank_desc(key - 1e6 * top3))   # the rest are ranked across the conference
            div_win[:, ci] = rank == 0
            top[:, ci] = rank_desc(key) == 0
        slot[:, ci] = np.where(rank < slots, rank, -1)
        if lg == "nba":
            # play-in: 7 hosts 8 for the 7th place; 9 hosts 10; the loser of the first hosts the winner of the second for the 8th
            order = np.argsort(rank, axis=1)
            t7, t8, t9, t10 = (ci[order[:, k]] for k in (6, 7, 8, 9))
            power = r[None, :] + walk[:, -1, :]
            beats = lambda x, y: rng.random(n) < 1 / (1 + np.exp(-(power[rows_, x] - power[rows_, y] + model["home"])))  # noqa: E731
            first = beats(t7, t8)
            seventh, loser = np.where(first, t7, t8), np.where(first, t8, t7)
            ninth = np.where(beats(t9, t10), t9, t10)
            eighth = np.where(beats(loser, ninth), loser, ninth)
            playoff[:, ci] = rank < 6
            playoff[rows_, seventh] = True
            playoff[rows_, eighth] = True
        else:
            playoff[:, ci] = rank < slots
        if lg != "nhl":
            top[:, ci] = rank == 0

    out = {}
    for i, t in enumerate(abbrs):
        out[t] = dict(w=float(wins[:, i].mean()), l=float(losses[:, i].mean()), otl=float(otl[:, i].mean()) if otl is not None else None,
                      pts=float(pts[:, i].mean()) if pts is not None else None, playoff=float(playoff[:, i].mean()),
                      seeds=[float((slot[:, i] == k).mean()) for k in range(slots)], div=float(div_win[:, i].mean()) if lg != "nba" else None,
                      top=float(top[:, i].mean()), playin=float(((slot[:, i] >= 6) & (slot[:, i] <= 9)).mean()) if lg == "nba" else None)
    return out


def overtime_rate(stand):
    """Share of NHL games decided after regulation so far: every such game leaves exactly one overtime loss."""
    games = sum(x["w"] + x["l"] + x["otl"] for x in stand.values()) / 2
    return min(0.28, max(0.18, sum(x["otl"] for x in stand.values()) / games)) if games >= 100 else 0.23


# %% history
def load_history():
    if not HISTORY.exists():
        return {}
    with HISTORY.open() as f:
        return {(r["date"], r["league"], r["team"]): r for r in csv.DictReader(f)}


def save_history(hist, now):
    """Keep what the page draws plus a margin, so the file stays the same size."""
    cut = (now - timedelta(days=HISTORY_DAYS + 15)).strftime("%Y-%m-%d")
    write_csv(HISTORY, HISTORY_FIELDS, sorted((r for r in hist.values() if r["date"] >= cut), key=lambda r: (r["league"], r["date"], r["team"])))


def backfill_history(hist, lg, cfg, rows, teams, now):
    """Fill missing past days with the game-market rating as it would have stood at noon UTC that day. A game then
    upcoming is priced at its eventual close, since no earlier snapshot exists."""
    have = {d for d, league, _ in hist if league == lg}
    for back in range(HISTORY_DAYS, 0, -1):
        asof = (now - timedelta(days=back)).replace(hour=12, minute=0, second=0, microsecond=0)
        day = asof.strftime("%Y-%m-%d")
        if day in have:
            continue
        games = fit_inputs([r for r in rows if r["state"] == "final"], asof, cfg["lookahead_days"], cfg["half_life"])
        if not enough(games, teams, asof, cfg["half_life"]):
            continue
        m = fit(games, teams, asof, cfg["half_life"], b2b=cfg["b2b"])
        for t, r in m["ratings"].items():
            hist[(day, lg, t)] = dict(date=day, league=lg, team=t, game_wp=f"{sigmoid(r):.4f}", wp="")


def trend(hist, lg, team, today):
    """(sparkline of game-market ratings, change over TREND_DAYS)"""
    pts = sorted((d, float(r["game_wp"])) for (d, league, t), r in hist.items() if league == lg and t == team and r["game_wp"] and d <= today)
    pts = pts[-HISTORY_DAYS:]
    cut = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")
    floor = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=TREND_DAYS + 3)).strftime("%Y-%m-%d")
    then = [v for d, v in pts if floor <= d <= cut]
    return [[d, round(v, 4)] for d, v in pts], (pts[-1][1] - then[-1] if then and pts else None)


# %% collect
def scan_dates(state, lg, cfg, now):
    """Eastern dates whose schedule needs reading, and the state to store once they have been read.
    state[lg] = {from, through}: every date in that range is settled and need not be read again."""
    today = now.astimezone(ET).date()
    first, last = today - timedelta(days=cfg["backfill_days"]), today + timedelta(days=cfg["lookahead_days"])
    st = state.get(lg) or {}
    if st.get("from") and st.get("through"):
        lo, hi = (datetime.strptime(st[k], "%Y-%m-%d").date() for k in ("from", "through"))
        days = [first + timedelta(days=i) for i in range(max(0, (lo - first).days))]
        start = min(hi + timedelta(days=1), today - timedelta(days=2))
    else:
        lo, days, start = first, [], first
    days += [start + timedelta(days=i) for i in range((last - start).days + 1)]
    return days, {"from": str(min(lo, first)), "through": str(today - timedelta(days=3))}


def collect(lg, cfg, ledger, state, now, status, schedules):
    """Refresh one league's ledger rows, season schedule and leaders; return what the league's build needs."""
    def attempt(source, what, fn, default=None):
        try:
            out = fn()
            status[source][lg][what] = out if isinstance(out, int) else len(out or {})
            return out
        except Exception as e:  # noqa: BLE001  one venue failing must not stop the build
            status[source][lg]["error"] = f"{what}: {e}"[:200]
            return default

    teams = fetch_teams(cfg)
    standings = attempt("espn", "standings", lambda: fetch_standings(cfg, teams), {}) or {}

    days, new_state = scan_dates(state, lg, cfg, now)
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda d: attempt("espn", f"schedule {d}", lambda: espn_day(cfg, d, teams), None), days))
    if all(r is not None for r in results):
        state[lg] = new_state
    for g in (g for r in results if r for g in r):
        upsert(ledger, lg, g, now)
    players = attempt("espn", "key players", lambda: fetch_key_players(lg, cfg, teams), {}) or {}
    injuries = attempt("espn", "injuries", lambda: fetch_injuries(cfg, teams), {}) or {}
    stored = schedules.get(lg) or {}
    if not stored.get("games") or parse_time(stored["fetched_utc"]) < now - timedelta(hours=SCHEDULE_HOURS):
        season = attempt("espn", "season games", lambda: fetch_schedule(cfg, teams))
        if season:
            schedules[lg] = dict(fetched_utc=iso(now), games=season)
    status["espn"][lg] = {k: v for k, v in status["espn"][lg].items() if not k.startswith("schedule")} | {"dates": len(days)}

    rows = [r for (league, _), r in ledger.items() if league == lg]
    index = Index(rows)
    finished = [r for r in rows if r["closed"] != "1" and r["state"] == "final"]
    need_all = any(not r["kalshi_home_ticker"] for r in finished)  # games first seen after they started: read settled markets too
    attempt("kalshi", "games", lambda: kalshi_live(cfg, teams, index, now, all_markets=need_all))
    attempt("polymarket", "games", lambda: polymarket_live(cfg, teams, index, now))
    pin = attempt("pinnacle", "feed", lambda: (pinnacle_get(f"/leagues/{cfg['pinnacle']}/matchups"), pinnacle_get(f"/leagues/{cfg['pinnacle']}/markets/straight")))
    status["pinnacle"][lg].pop("feed", None)
    if pin:
        attempt("pinnacle", "games", lambda: pinnacle_live(pin[0], pin[1], teams, index, now))
    status["draftkings"][lg]["games"] = sum(1 for r in rows if r["draftkings_ts"] == iso(now))

    # closing prices, once, for games that have finished
    if finished:
        ok = attempt("kalshi", "closes", lambda: kalshi_close(finished)) is not None

        def close(r):
            try:
                return r, espn_close(cfg, r["event_id"]), True
            except Exception:  # noqa: BLE001
                return r, None, False
        with ThreadPoolExecutor(6) as pool:
            closes = list(pool.map(close, finished))
        for r, dk, fetched in closes:
            if dk:
                set_book(r, "draftkings", dk, parse_time(r["start_utc"]))
            if ok and fetched:
                r["closed"] = "1"
        status["draftkings"][lg]["closes"] = sum(1 for _, dk, _ in closes if dk)

    boards = {
        "kalshi": attempt("kalshi", "title", lambda: kalshi_board(cfg["kalshi_title"], cfg, teams), {}),
        "polymarket": attempt("polymarket", "title", lambda: polymarket_title(cfg, teams), {}),
        "pinnacle": attempt("pinnacle", "title", lambda: pinnacle_title(pin[0], pin[1], teams), {}) if pin else {},
    }
    playoff = attempt("kalshi", "playoff", lambda: kalshi_board(cfg["kalshi_playoff"], cfg, teams), {}) or {}
    return dict(teams=teams, standings=standings, boards=boards, playoff=playoff, players=players, injuries=injuries,
                schedule=(schedules.get(lg) or {}).get("games") or [])


# %% build
def league_block(lg, cfg, rows, teams, standings, boards, playoff, hist, now, players=None, injuries=None, schedule=None, drift=None):
    """Fit one league and shape its page data. Returns None when too few games are priced."""
    if cfg["b2b"]:
        add_b2b(rows)
    games = fit_inputs(rows, now, cfg["lookahead_days"], cfg["half_life"])
    if not enough(games, teams.abbrs, now, cfg["half_life"]):
        return None
    model = fit(games, teams.abbrs, now, cfg["half_life"], b2b=cfg["b2b"])
    game_r = model["ratings"]

    venues = {s: n for s, b in boards.items() if (n := normalise(b or {}, len(teams.abbrs)))}
    title = {t: sum(v[t] for v in venues.values() if t in v) / sum(1 for v in venues.values() if t in v)
             for t in teams.abbrs if any(t in v for v in venues.values())}
    total = sum(title.values())
    title = {t: v / total for t, v in title.items()} if total else {}
    conf = {t: s.get("conf") for t, s in standings.items()}
    blend, info = title_blend(game_r, title, playoff if len(playoff) >= 0.6 * len(teams.abbrs) else {}, conf) if title else (None, "no title prices")
    final = {t: r + (blend[t]["weight"] * blend[t]["gap"] if blend and t in blend else 0.0) for t, r in game_r.items()}
    mean = sum(final.values()) / len(final)
    final = {t: r - mean for t, r in final.items()}
    final_model = dict(model, ratings=final)

    sim, left, drift = None, [], cfg["drift"] if drift is None else drift
    if schedule and all((standings.get(t) or {}).get("conf") for t in teams.abbrs):
        left = remaining_games(schedule, rows, now)
        sim = simulate(lg, teams.abbrs, standings, left, final_model, drift, now, p_ot=overtime_rate(standings) if lg == "nhl" else 0.23)

    sigma = points_scale(rows) if cfg["points"] else None
    nd = statistics.NormalDist()
    today = now.strftime("%Y-%m-%d")
    backfill_history(hist, lg, cfg, rows, teams.abbrs, now)
    for t in teams.abbrs:
        hist[(today, lg, t)] = dict(date=today, league=lg, team=t, game_wp=f"{sigmoid(game_r[t]):.4f}", wp=f"{sigmoid(final[t]):.4f}")

    game_rank = {t: i + 1 for i, t in enumerate(sorted(game_r, key=game_r.get, reverse=True))}
    out_teams = []
    for i, t in enumerate(sorted(final, key=final.get, reverse=True)):
        spark, d7 = trend(hist, lg, t, today)
        wp = sigmoid(final[t])
        b = blend.get(t) if blend else None
        out_teams.append(dict(
            rank=i + 1, abbr=t, name=teams.info[t]["name"], logo=teams.info[t]["logo"], logo_dark=teams.info[t]["logo_dark"],
            conf=conf.get(t), div=standings.get(t, {}).get("div"), record=standings.get(t, {}).get("record"),
            injuries=key_injuries((players or {}).get(t, []), (injuries or {}).get(t, [])),
            sim=dict({k: (round(v, 1) if v is not None else None) for k, v in sim[t].items() if k in ("w", "l", "otl", "pts")},
                     seeds=[round(x, 4) for x in sim[t]["seeds"]],
                     **{k: (round(sim[t][k], 4) if sim[t][k] is not None else None) for k in ("playoff", "div", "top", "playin")}) if sim else None,
            wp=round(wp, 4), game_wp=round(sigmoid(game_r[t]), 4), game_rank=game_rank[t],
            title_wp=round(sigmoid(game_r[t] + b["gap"]), 4) if b else None, title_weight=round(b["weight"], 3) if b else 0,
            pts=round(sigma * nd.inv_cdf(wp), 1) if sigma else None, title_p=round(title[t], 4) if t in title else None,
            playoff_p=round(playoff[t], 3) if t in playoff else None, d7=round(d7, 4) if d7 is not None else None,
            games_weight=round(model["n_eff"][t], 2), spark=spark))

    upcoming = []
    for r in sorted((r for r in rows if r["state"] == "pre" and now < parse_time(r["start_utc"]) <= now + timedelta(days=cfg["lookahead_days"])),
                    key=lambda r: r["start_utc"]):
        ps = source_probs(r)
        if ps:
            upcoming.append(dict(start_utc=r["start_utc"], home=r["home"], away=r["away"], neutral=int(r["neutral"] or 0),
                                 sources={s: round(p, 4) for s, p in ps.items()}, consensus=round(sigmoid(consensus(r)), 4),
                                 model=round(predict(final_model, r["home"], r["away"], int(r["neutral"] or 0), r.get("_b2b", 0) if cfg["b2b"] else 0), 4)))

    priced = [r for r in rows if consensus(r) is not None]
    both = [(sim[t]["playoff"], playoff[t]) for t in teams.abbrs if sim and t in playoff]
    unrated = [t for t in teams.abbrs if model["n_eff"][t] == 0]
    outlook = dict(sims=SIMS, drift=drift, games_left=len(left), priced=sum(1 for g in left if g["y"] is not None), seeds=SEEDS[lg],
                   playoff_gap=round(math.sqrt(sum((a - b) ** 2 for a, b in both) / len(both)), 4) if both else None) if sim else None
    return dict(
        label=cfg["label"], updated_utc=iso(now), stale=False, half_life_days=cfg["half_life"],
        games_fit=len(games), games_upcoming=len(upcoming), fit_rmse=round(model["rmse"], 4),
        home_adv=dict(logit=round(model["home"], 4), wp=round(sigmoid(model["home"]), 4), pts=round(sigma * nd.inv_cdf(sigmoid(model["home"])), 2) if sigma else None),
        b2b=dict(logit=round(model["b2b"], 4), wp=round(sigmoid(model["b2b"]) - 0.5, 4)) if cfg["b2b"] else None,
        points_sd=round(sigma, 2) if sigma else None,
        title=dict(sources=sorted(venues), weight_max=TITLE_WEIGHT, **({k: (round(v, 3) if isinstance(v, float) else v) for k, v in info.items()} if blend else {"skipped": info})),
        coverage={s: sum(1 for r in priced if s in source_probs(r)) for s in SOURCES},
        outlook=outlook, unrated=unrated, teams=out_teams, games=upcoming)


def build(leagues=None, now=None):
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    ledger, hist = load_ledger(), load_history()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    state = {lg: st for lg, st in state.items() if any(league == lg for league, _ in ledger)}  # no stored games: scan again
    previous = json.loads(OUT.read_text()) if OUT.exists() else {"leagues": {}}
    schedules = json.loads(SCHEDULE.read_text()) if SCHEDULE.exists() else {}
    before = json.dumps(schedules, sort_keys=True)
    status = {s: defaultdict(dict) for s in ("espn",) + SOURCES}
    blocks = {}
    for lg, cfg in LEAGUES.items():
        if leagues and lg not in leagues:
            continue
        try:
            got = collect(lg, cfg, ledger, state, now, status, schedules)
            rows = [r for (league, _), r in ledger.items() if league == lg]
            blocks[lg] = league_block(lg, cfg, rows, got.pop("teams"), got.pop("standings"), got.pop("boards"), got.pop("playoff"), hist, now, **got)
        except Exception as e:  # noqa: BLE001  keep the other leagues and the last good block
            status["espn"][lg]["error"] = f"build: {e}"[:200]
            blocks[lg] = None
        print(f"{lg}: " + ("ok" if blocks[lg] else "not rebuilt"), {s: dict(v[lg]) for s, v in status.items() if v[lg]}, flush=True)

    out_leagues = {}
    for lg in LEAGUES:
        if blocks.get(lg):
            out_leagues[lg] = blocks[lg]
        elif lg in previous.get("leagues", {}):  # not requested: keep as is. Out of season or failed: keep, marked stale
            out_leagues[lg] = previous["leagues"][lg] if lg not in blocks else dict(previous["leagues"][lg], stale=True)
    save_ledger(ledger)
    save_history(hist, now)
    write_text(STATE, json.dumps(state, indent=1, sort_keys=True) + "\n")
    if json.dumps(schedules, sort_keys=True) != before:  # about once a day
        write_text(SCHEDULE, json.dumps(schedules, separators=(",", ":"), sort_keys=True) + "\n")
    payload = dict(generated_utc=iso(now), sources={s: {lg: dict(v) for lg, v in d.items() if v} for s, d in status.items()},
                   params=dict(ridge=RIDGE, max_spread=MAX_SPREAD, title_weight=TITLE_WEIGHT, title_half=TITLE_HALF, trend_days=TREND_DAYS, sims=SIMS),
                   leagues=out_leagues)
    write_text(OUT, json.dumps(payload, separators=(",", ":")) + "\n")
    return payload


# %% tune
def tune(leagues=None):
    """Walk forward over the stored closes: fit on games before each day, predict that day's consensus."""
    ledger = load_ledger()
    for lg, cfg in LEAGUES.items():
        if leagues and lg not in leagues:
            continue
        rows = [r for (league, _), r in ledger.items() if league == lg and r["state"] == "final" and consensus(r) is not None]
        if cfg["b2b"]:
            add_b2b(rows)
        teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
        days = sorted({r["start_utc"][:10] for r in rows})
        print(f"\n{lg}: {len(rows)} priced finished games over {len(days)} days")
        for hl in (3, 5, 7, 10, 14, 21, 28, 42):
            line = []
            for ridge in (0.05, 0.1, 0.25, 0.5):
                se, ae, n = 0.0, 0.0, 0
                for day in days:
                    cut = parse_time(day + "T00:00:00Z")
                    before = [r for r in rows if parse_time(r["start_utc"]) < cut]
                    if not enough(fit_inputs(before, cut, 0, 14.0), teams, cut, 14.0):  # one fixed bar: every setting is scored on the same days
                        continue
                    train = fit_inputs(before, cut, 0, hl)
                    m = fit(train, teams, cut, hl, ridge=ridge, b2b=cfg["b2b"])
                    for r in rows:
                        if r["start_utc"][:10] == day:
                            p, y = predict(m, r["home"], r["away"], int(r["neutral"] or 0), r.get("_b2b", 0) if cfg["b2b"] else 0), consensus(r)
                            se += (logit(p) - y) ** 2
                            ae += abs(p - sigmoid(y))
                            n += 1
                line.append(f"ridge {ridge}: rmse {math.sqrt(se / n):.3f} mae {100 * ae / n:.2f}pp" if n else "no test games")
            print(f"  half-life {hl:>2}d  " + "   ".join(line) + f"   (n={n})")


# %% calibrate
def calibrate(leagues=None):
    """Simulated playoff odds against Kalshi's playoff prices, for a range of weekly strength drifts. Writes nothing."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ledger = load_ledger()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    schedules = json.loads(SCHEDULE.read_text()) if SCHEDULE.exists() else {}
    for lg, cfg in LEAGUES.items():
        if leagues and lg not in leagues:
            continue
        got = collect(lg, cfg, ledger, state, now, {s: defaultdict(dict) for s in ("espn",) + SOURCES}, schedules)
        rows = [r for (league, _), r in ledger.items() if league == lg]
        args = (got.pop("teams"), got.pop("standings"), got.pop("boards"), got.pop("playoff"))
        print(f"\n{lg}: root-mean-square gap between simulated and Kalshi playoff odds ({len(args[3])} teams priced)")
        for drift in sorted({0.0, 0.03, 0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.30, cfg["drift"]}):
            b = league_block(lg, cfg, rows, *args, {}, now, drift=drift, **got)
            if not b or not b["outlook"]:
                print("  no simulation: too few priced games, or no schedule or standings")
                break
            worst = max((t for t in b["teams"] if t["playoff_p"] is not None), key=lambda t: abs(t["sim"]["playoff"] - t["playoff_p"]))
            print(f"  drift {drift:.3f}: {100 * b['outlook']['playoff_gap']:.2f}pp   largest: {worst['abbr']} sim {100 * worst['sim']['playoff']:.0f}% vs Kalshi {100 * worst['playoff_p']:.0f}%"
                  + ("   <- in use" if drift == cfg["drift"] else ""))


# %% cli
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("build", "tune", "calibrate"))
    ap.add_argument("--leagues", default="", help="comma-separated subset of " + ",".join(LEAGUES))
    a = ap.parse_args(argv)
    leagues = [x for x in a.leagues.split(",") if x] or None
    if a.command == "tune":
        return tune(leagues)
    if a.command == "calibrate":
        return calibrate(leagues)
    payload = build(leagues)
    print("wrote", OUT.relative_to(ROOT), {lg: ("stale" if b["stale"] else f"{len(b['teams'])} teams, {b['games_fit']} games") for lg, b in payload["leagues"].items()})
    if not any(not b["stale"] for b in payload["leagues"].values()):
        sys.exit("no league could be rebuilt")


if __name__ == "__main__":
    main()
