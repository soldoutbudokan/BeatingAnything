"""Team lineage, home/away/neutral status and match start slots.

Lineage. `config/cricket-teams.csv` has one row per Cricsheet team name x gender x team type x
competition, with its match count and dates, mapping it to `team_id` (slug of the canonical name plus
`_m`/`_w`, so a franchise's men's and women's sides stay apart) and `team_name` (the latest name).
Renames of one club or franchise share an id (`RENAMES`: Kings XI Punjab -> Punjab Kings, Delhi
Daredevils -> Delhi Capitals, Royal Challengers Bangalore -> Bengaluru, Rising Pune Supergiants ->
Supergiant, Trinidad & Tobago Red Steel -> Trinbago Knight Riders, St Lucia Zouks/Stars -> Kings,
Barbados Tridents/Royals, the three Hundred sides sold in 2026, New Zealand associations' first-class
brands, Birmingham Bears -> Warwickshire, the women's super-league sides that became regional teams,
Swaziland -> Eswatini). A replacement franchise for the same city or region keeps its own id and names
its predecessor in `succeeds` (Deccan Chargers -> Sunrisers Hyderabad, the BPL and LPL city slots, the
2025 English women's county sides); `lineage_id` is the root of that chain, for baselines that want
continuity. Internationals carry `country` (the venue table's `cricket_country`, Barbados excepted) and
`full_member_from` from `competitions.FULL_MEMBERS` (Zimbabwe 1992-07-06, Bangladesh 2000-06-26, Ireland
and Afghanistan 2017-06-22; earlier members are listed as 1900-01-01).

Home status (plan 4.4). Internationals: home when the venue's cricket country (or its own country) is
the team's, away when it is the opponent's, otherwise neutral. Clubs, per competition season: a venue is
neutral when it lies outside the competition's country (IPL 2009 and 2020, PSL 2016-19, the CPL in
Florida), hosts more than 40% of the season's matches, or - an extension - has no single team in at
least half of its matches (hubs such as the Syed Mushtaq Ali groups or IPL 2022). A team's home venues
are the non-neutral venues it dominates where it played at least 30% of its season's matches, plus, as
a second extension, secondary grounds where it played at least two matches and 75% of the ground's
matches (Guwahati, Dharamsala, Cheltenham). Only league-stage matches define home venues (knockout
pairings depend on results and are often at neutral grounds); every match is labelled.
`home_status_table` labels each match twice. `home_status1/2` are as of the match day, from matches on
earlier days only. A team's home venues are first the grounds whose latest home season of the
competition in the last five years was the team's (hub and abroad seasons have none; a team new to the
competition takes its home grounds in another competition, an extension); once the season has 4 matches
and the team 2, its home grounds in the season so far join them and earlier grounds another team has
taken this season drop out. The season so far makes a venue neutral only once it has max(8, half the
expected length) matches, the expected length being the larger of the two previous seasons', and the
venue 3, with host share judged against the expected length, so leagues that play blocks of games in
one city (PSL, CPL) are not read as hubs. A forecast season uses the earlier seasons alone.
`home_status1/2_full` use the whole season's league stage (the fixture list, public before a season, so
no results) and are kept as a diagnostic; the validation report gives the two labels' agreement.

Start slots. `config/cricket-day-night.csv` lists every match a rule covers with its `start_slot`
(`day`, `day_night`, `night`, or `unknown` where a rule finds the slot ambiguous), `source` and
`confidence`; a match not listed is `unknown`. Rules, later ones winning: first-class cricket and
international Tests are day; the curated pink-ball Test list (matched on date, gender and teams) is
day_night. League defaults (IPL, WPL, PSL, LPL, ILT20, BPL, CPL, MLC, SA20, BBL) give the earlier match
of a double-header by `match_number` the afternoon slot and the last the evening one, with the earlier
match unknown when a later one that day is 1.5+ hours further west (BBL games in Perth); IPL 2009's
evening games in South Africa started near dusk (day_night), and IPL 2021's last two league games were
played at the same time (both night). A women's match sharing a ground and day
with a men's match is the earlier game (the Hundred, Super Smash, internationals; WBBL curtain raisers),
and Hundred men's games after one are day_night. Full-member ODIs in India (2005+), Australia (not the
winter-tropics grounds), the UAE, Pakistan (2019+) and at Sri Lanka's floodlit grounds are day_night;
full-member T20Is in India, Pakistan, the UAE, Sri Lanka and Australia are night, the earlier game of
an ICC double-header there day. All else, including the T20 Blast, Syed Mushtaq Ali and most women's
internationals, is unknown.

Limits. Renames, successors, the pink-ball list (complete to about January 2026) and slot defaults are
the curator's knowledge of the leagues, not scraped schedules; the slot is a category, not a start
time, and a double-header whose other match is missing from Cricsheet is misread as a single. Home
grounds are inferred from where teams played: a club's single match at an outground is neutral, and two
clubs sharing a ground both lose it. As of the day, a team's first match at a ground new to it, and the
first Cricsheet season of a competition (county cricket 2014, IPL 2008) unless the team plays another
competition, cannot be labelled home; about 9% of club matches get a different label from the full
season. BPL and LPL franchises churn nearly every edition, so their `team_id`s are short-lived and
`lineage_id` is the useful key there.

Matches are keyed by ingest's integer `match_id` (the file stem; `wi_` stems map to 90M + number).
Run `python -m beating.cricket.teams` (about 30 s) to rebuild both config files, the home-venue table
`data/derived/cricket/team-home-venues.csv`, `data/processed/cricket/match_teams.parquet` and
`reports/cricket-teams-validation.json` from the Cricsheet zip.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd

from beating.cricket.competitions import FULL_MEMBERS, competition_for, competition_meta, fmt_family
from beating.cricket.ingest import match_id_of
from beating.cricket.rules import is_knockout
from beating.cricket.venues import dst_shift, load_venues, venue_id_for

ROOT = Path(__file__).resolve().parents[2]
CRICSHEET_ZIP = ROOT / "data" / "raw" / "cricsheet" / "all_json.zip"
TEAMS_CSV = ROOT / "config" / "cricket-teams.csv"
DAY_NIGHT_CSV = ROOT / "config" / "cricket-day-night.csv"
HOMES_CSV = ROOT / "data" / "derived" / "cricket" / "team-home-venues.csv"
MATCH_TEAMS = ROOT / "data" / "processed" / "cricket" / "match_teams.parquet"
REPORT = ROOT / "reports" / "cricket-teams-validation.json"

SHARE_MIN = 0.30          # plan 4.4: home when the team plays >= 30% of its season's matches there
HOST_SHARE_MAX = 0.40     # plan 4.4: neutral when the venue hosts > 40% of the season's matches
DOMINANT_MIN = 0.50       # extension: neutral unless one team plays in >= half the venue's matches
SECONDARY_SHARE = 0.75    # extension: secondary home ground, the team in >= 75% of its matches ...
SECONDARY_MIN = 2         # ... and at least two of them
ASOF_MIN_SEASON = 4       # as of a day, the season so far adds home venues once it has this many matches ...
ASOF_MIN_TEAM = 2         # ... and the team this many
ASOF_NEUTRAL_MIN = 8      # it can make a venue neutral once it has this many matches ...
ASOF_SEASON_FRAC = 0.5    # ... and this share of the expected season length ...
ASOF_MIN_VENUE = 3        # ... and the venue this many
LOOKBACK_YEARS = 5        # earlier seasons (started this many years back at most) searched for home venues
TZ_GAP_HOURS = 1.5        # a later match this far west may be the night game of the day
TEAM_COLUMNS = ["team_raw", "gender", "team_type", "competition_id", "team_id", "team_name", "lineage_id",
                "succeeds", "country", "full_member_from", "n_matches", "first_date", "last_date", "notes"]
SLOTS = ("day", "day_night", "night", "unknown")
SLOT_COLUMNS = ["match_id", "start_date", "competition_id", "venue_id", "start_slot", "source", "confidence", "note"]
COMP_COUNTRY = {"IND": "India", "AUS": "Australia", "PAK": "Pakistan", "WI": "West Indies",
                "RSA": "South Africa", "UAE": "United Arab Emirates", "USA": "United States of America",
                "BAN": "Bangladesh", "SL": "Sri Lanka", "ENG": "England", "NZ": "New Zealand",
                "IRE": "Ireland", "NEP": "Nepal", "CAN": "Canada"}

# (Cricsheet name, gender or "" for both, canonical name, note). The canonical name is the latest one.
RENAMES = [
    ("Kings XI Punjab", "male", "Punjab Kings", "renamed 2021"),
    ("Delhi Daredevils", "male", "Delhi Capitals", "renamed 2019"),
    ("Royal Challengers Bangalore", "", "Royal Challengers Bengaluru", "renamed 2024 (men) and 2025 (WPL)"),
    ("Rising Pune Supergiants", "male", "Rising Pune Supergiant", "2016 spelling of the 2016-17 franchise"),
    ("Trinidad & Tobago Red Steel", "male", "Trinbago Knight Riders", "bought and renamed 2016"),
    ("Barbados Royals", "", "Barbados Tridents", "Tridents 2013-20, Royals 2021-25, Tridents again 2026"),
    ("St Lucia Zouks", "male", "St Lucia Kings", "Zouks 2013-16 and 2019-20, Stars 2017-18, Kings 2021-"),
    ("St Lucia Stars", "male", "St Lucia Kings", "Zouks 2013-16 and 2019-20, Stars 2017-18, Kings 2021-"),
    ("Manchester Originals", "", "Manchester Super Giants", "renamed 2026 after the sale of the franchise"),
    ("Oval Invincibles", "", "MI London", "renamed 2026 after the sale of the franchise"),
    ("Northern Superchargers", "", "Sunrisers Leeds", "renamed 2026 after the sale of the franchise"),
    ("Sharjah Warriors", "male", "Sharjah Warriorz", "respelt 2025"),
    ("Jaffna Stallions", "male", "Jaffna Kings", "same owner, renamed 2021"),
    ("B-Love Kandy", "male", "Kandy Falcons", "Kandy Falcons' 2023 name"),
    ("Kathmandu Gurkhas", "male", "Kathmandu Gorkhas", "spelling variant"),
    ("Birmingham Bears", "male", "Warwickshire", "Warwickshire's T20 name; same club"),
    ("Auckland Aces", "male", "Auckland", "Auckland's first-class brand; same association"),
    ("Central Stags", "male", "Central Districts", "Central Districts' first-class brand; same association"),
    ("Otago Volts", "male", "Otago", "Otago's first-class brand; same association"),
    ("Wellington Firebirds", "male", "Wellington", "Wellington's first-class brand; same association"),
    ("Himachal", "male", "Himachal Pradesh", "name variant"),
    ("Loughborough Lightning", "female", "The Blaze", "super-league side 2016-19, Lightning 2020-22, The Blaze 2023-"),
    ("Lightning", "female", "The Blaze", "super-league side 2016-19, Lightning 2020-22, The Blaze 2023-"),
    ("Lancashire Thunder", "female", "Thunder", "super-league side continued as the 2020 regional side"),
    ("Yorkshire Diamonds", "female", "Northern Diamonds", "super-league side continued as the 2020 regional side"),
    ("Surrey Stars", "female", "South East Stars", "super-league side continued as the 2020 regional side"),
    ("Warriors", "female", "Warriors (FairBreak)", "FairBreak Invitational side; 2022 and 2023 names"),
    ("Swaziland", "male", "Eswatini", "country renamed 2018"),
]
# (gender, team, predecessor, note): a different franchise taking over the same city or region slot.
_BPL = {"Dhaka": ["Dhaka Gladiators", "Dhaka Dynamites", "Dhaka Platoon", "Minister Group Dhaka",
                  "Dhaka Dominators", "Durdanto Dhaka", "Dhaka Capitals"],
        "Chattogram": ["Chittagong Kings", "Chittagong Vikings", "Chattogram Challengers"],
        "Khulna": ["Khulna Royal Bengals", "Khulna Titans", "Khulna Tigers"],
        "Rajshahi": ["Duronto Rajshahi", "Rajshahi Kings", "Rajshahi Royals", "Durbar Rajshahi",
                     "Rajshahi Warriors"],
        "Sylhet": ["Sylhet Royals", "Sylhet Super Stars", "Sylhet Sixers", "Sylhet Thunder", "Sylhet Sunrisers",
                   "Sylhet Strikers", "Sylhet Titans"],
        "Barishal": ["Barisal Burners", "Barisal Bulls", "Fortune Barishal"],
        "Comilla": ["Comilla Victorians", "Cumilla Warriors"], "Rangpur": ["Rangpur Riders", "Rangpur Rangers"]}
_LPL = {"Colombo": ["Colombo Kings", "Colombo Stars", "Colombo Strikers", "Colombo Kaps"],
        "Dambulla": ["Dambulla Viiking", "Dambulla Giants", "Dambulla Aura", "Dambulla Sixers"],
        "Galle": ["Galle Gladiators", "Galle Titans", "Galle Marvels", "Galle Gallants"],
        "Kandy": ["Kandy Tuskers", "Kandy Warriors", "Kandy Falcons", "Kandy Royals"]}
SUCCEEDS = [
    ("male", "Sunrisers Hyderabad", "Deccan Chargers", "Hyderabad franchise re-awarded 2012; distinct team"),
    ("male", "Jamaica Kingsmen", "Jamaica Tallawahs",
     "Jamaica's return in 2026 after the Tallawahs' slot went to Antigua"),
    ("male", "Western Province", "Cape Cobras", "Cape franchise replaced by the provincial side 2021-22"),
    ("male", "Chattogram Royals", "Chittagong Kings", "BPL Chattogram slot"),
    *[("male", b, a, f"BPL {city} slot") for city, chain in _BPL.items() for a, b in zip(chain, chain[1:])],
    *[("male", b, a, f"LPL {city} slot") for city, chain in _LPL.items() for a, b in zip(chain, chain[1:])],
    *[("female", b, a, "2025 county side in the regional side's tier-1 slot") for b, a in (
        ("Hampshire", "Southern Vipers"), ("Surrey", "South East Stars"), ("Lancashire", "Thunder"),
        ("Warwickshire", "Central Sparks"), ("Somerset", "Western Storm"), ("Essex", "Sunrisers"))],
]
INTL_COUNTRY = {"ICC World XI": "", "World XI": "", "Asia XI": "", "Africa XI": "",
                "Turks and Caicos Island": "Turks and Caicos Islands"}

# (date, gender, home, away, ground): every day/night pink-ball Test the curator knows of, to January 2026.
PINK_BALL_TESTS = [
    ("2015-11-27", "male", "Australia", "New Zealand", "Adelaide Oval"),
    ("2016-10-13", "male", "Pakistan", "West Indies", "Dubai International Cricket Stadium"),
    ("2016-11-24", "male", "Australia", "South Africa", "Adelaide Oval"),
    ("2016-12-15", "male", "Australia", "Pakistan", "Brisbane Cricket Ground"),
    ("2017-08-17", "male", "England", "West Indies", "Edgbaston"),
    ("2017-10-06", "male", "Pakistan", "Sri Lanka", "Dubai International Cricket Stadium"),
    ("2017-11-09", "female", "Australia", "England", "North Sydney Oval"),
    ("2017-12-02", "male", "Australia", "England", "Adelaide Oval"),
    ("2017-12-26", "male", "South Africa", "Zimbabwe", "St George's Park"),
    ("2018-03-22", "male", "New Zealand", "England", "Eden Park"),
    ("2018-06-23", "male", "West Indies", "Sri Lanka", "Kensington Oval"),
    ("2019-01-24", "male", "Australia", "Sri Lanka", "Brisbane Cricket Ground"),
    ("2019-11-22", "male", "India", "Bangladesh", "Eden Gardens"),
    ("2019-11-29", "male", "Australia", "Pakistan", "Adelaide Oval"),
    ("2020-12-17", "male", "Australia", "India", "Adelaide Oval"),
    ("2021-02-24", "male", "India", "England", "Narendra Modi Stadium"),
    ("2021-09-30", "female", "Australia", "India", "Carrara Oval"),
    ("2021-12-16", "male", "Australia", "England", "Adelaide Oval"),
    ("2022-03-12", "male", "India", "Sri Lanka", "M Chinnaswamy Stadium"),
    ("2022-12-08", "male", "Australia", "West Indies", "Adelaide Oval"),
    ("2023-02-16", "male", "New Zealand", "England", "Bay Oval"),
    ("2024-01-25", "male", "Australia", "West Indies", "Brisbane Cricket Ground"),
    ("2024-12-06", "male", "Australia", "India", "Adelaide Oval"),
    ("2025-01-30", "female", "Australia", "England", "Melbourne Cricket Ground"),
    ("2025-07-12", "male", "West Indies", "Australia", "Sabina Park"),
    ("2025-12-04", "male", "Australia", "England", "Brisbane Cricket Ground"),
]
PINK_LIST_END = "2026-01-31"
# competition: (single match, earlier match of a multi-match day, last match of the day, confidence)
LEAGUE_SLOTS = {
    "ipl": ("night", "day", "night", "high"), "wpl": ("night", "day", "night", "medium"),
    "psl": ("night", "day", "night", "medium"), "lpl": ("night", "day", "night", "medium"),
    "ilt20": ("night", "day", "night", "medium"), "bbl": ("night", "day", "night", "medium"),
    "sa20": ("day_night", "day", "day_night", "medium"), "bpl": ("unknown", "day", "night", "medium"),
    "cpl": ("unknown", "day", "night", "medium"), "mlc": ("unknown", "day", "night", "medium"),
}
SIMULTANEOUS_DAYS = [("ipl", "2021-10-08")]   # IPL 2021's last two league games, both 19:30 IST
FIRST_CLASS_DAY = {"county_championship", "sheffield_shield", "plunket_shield", "ranji_trophy", "csa_4day",
                   "quaid_e_azam", "slc_major_league", "ire_ip_fc"}
ONE_DAY_DAY = {"vijay_hazare": None, "eng_one_day_cup": "2020-01-01", "eng_women_one_day": None}
COUNTY_PINK_ROUND = ("2017-06-26", "2017-06-27")   # the County Championship's floodlit round
ODI_DN_COUNTRIES = {"India": "2005-01-01", "Australia": None, "United Arab Emirates": None, "Pakistan": "2019-01-01"}
ODI_DN_VENUES = {"premadasa_stadium", "pallekele_stadium", "dambulla_stadium", "hambantota_stadium"}
ODI_UNKNOWN_VENUES = {"hpca_dharamsala", "cazalys_stadium", "marrara_cricket_ground", "harrup_park",
                      "tony_ireland_stadium", "riverway_stadium"}   # hill and winter-tropics grounds: day starts
T20I_NIGHT = {"India": "high", "Pakistan": "medium", "United Arab Emirates": "medium", "Sri Lanka": "medium",
              "Australia": "medium"}
ICC_EVENTS = {"icc_t20wc", "icc_cwc", "icc_ct", "asia_cup"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower().replace("&", " and ")).strip("_")


def gcode(gender: str) -> str:
    return "w" if gender == "female" else "m"


_RENAME = {(raw, g): (new, note) for raw, g, new, note in RENAMES}


def canonical_name(raw: str, gender: str) -> str:
    hit = _RENAME.get((raw, gender)) or _RENAME.get((raw, ""))
    return hit[0] if hit else raw


def intl_country(name: str) -> str:
    return INTL_COUNTRY.get(name, name)


def team_id_for(raw: str, gender: str, team_type: str = "club") -> str:
    name = canonical_name(raw, gender)
    if team_type == "international":
        name = intl_country(name) or name
    return f"{slug(name)}_{gcode(gender)}"


def _club_id(name: str, gender: str) -> str:
    return team_id_for(name, gender, "club")


SUCCEEDS_ID = {_club_id(t, g): (_club_id(p, g), note) for g, t, p, note in SUCCEEDS}


def lineage_id(team_id: str) -> str:
    seen = {team_id}
    while team_id in SUCCEEDS_ID and SUCCEEDS_ID[team_id][0] not in seen:
        team_id = SUCCEEDS_ID[team_id][0]
        seen.add(team_id)
    return team_id


def full_member_from(country: str) -> str:
    return FULL_MEMBERS.get(country, "") if country and not country.endswith("XI") else ""


def is_full_member(country: str, day) -> bool:
    since = full_member_from(country)
    return bool(since) and str(day)[:10] >= since


def comp_country(competition_id: str) -> str | None:
    try:
        return COMP_COUNTRY.get(competition_meta(competition_id).get("country"))
    except KeyError:
        return None


# ---------------------------------------------------------------- scanning

def _info(b: bytes) -> dict:
    k = b.find(b'"innings"')  # Cricsheet writes meta and info before the long innings list
    if k > 0:
        try:
            return json.loads(b[:k].rstrip().rstrip(b",") + b"}")["info"]
        except (ValueError, KeyError):
            pass
    return json.loads(b)["info"]


def match_row(stem: str, info: dict) -> dict:
    """The info-level facts this module needs from one Cricsheet match (file stem -> ingest's int id)."""
    ev, out, toss = info.get("event") or {}, info.get("outcome") or {}, info.get("toss") or {}
    comp = competition_for(info)
    t1, t2 = info["teams"][:2]
    mn = ev.get("match_number")
    return dict(match_id=match_id_of(str(stem)), file_stem=str(stem), start_date=str(info["dates"][0]),
                season=str(info.get("season")),
                match_type=info["match_type"], fam=fmt_family(info["match_type"], ev.get("name")),
                gender=info["gender"], team_type=info["team_type"], event_name=ev.get("name"),
                match_number=int(mn) if isinstance(mn, (int, float)) or str(mn).isdigit() else None,
                stage=None if ev.get("stage") is None else str(ev.get("stage")),
                competition_id=comp.competition_id, event_id=comp.event_id, generic=comp.generic,
                assoc_match=comp.assoc_match, venue_raw=info.get("venue"), city_raw=info.get("city"),
                team1_raw=t1, team2_raw=t2, winner_raw=out.get("winner"),
                result=out.get("result") or ("win" if out.get("winner") else None), method=out.get("method"),
                toss_winner_raw=toss.get("winner"), toss_decision=toss.get("decision"))


def scan_matches(zip_path: Path | str = CRICSHEET_ZIP) -> pd.DataFrame:
    rows = []
    with zipfile.ZipFile(zip_path) as z:
        for i in z.infolist():
            if i.filename.endswith(".json"):
                rows.append(match_row(Path(i.filename).stem, _info(z.read(i))))
    df = pd.DataFrame(rows)
    df["match_number"] = df.match_number.astype("Int64")
    return df


def add_ids(m: pd.DataFrame, venues_path: Path | str | None = None) -> pd.DataFrame:
    """Team ids and names, venue ids (unless present), the home-venue competition key, team countries."""
    m = m.copy()
    for k in ("team1", "team2", "winner", "toss_winner"):
        raw = m[f"{k}_raw"]
        m[f"{k}_id"] = [team_id_for(r, g, t) if isinstance(r, str) else None
                        for r, g, t in zip(raw, m.gender, m.team_type)]
        if k.startswith("team"):
            m[k] = [canonical_name(r, g) for r, g in zip(raw, m.gender)]
            m[f"{k}_country"] = [intl_country(n) if t == "international" else (comp_country(c) or "")
                                 for n, t, c in zip(m[k], m.team_type, m.competition_id)]
    if "venue_id" not in m:
        kw = {} if venues_path is None else {"path": venues_path}
        m["venue_id"] = [_venue_id(v, c, **kw) for v, c in zip(m.venue_raw, m.city_raw)]
    m["comp_key"] = np.where(m.generic.astype(bool), "other:" + m.event_name.fillna(""), m.competition_id)
    return m


def _venue_id(v, c, **kw):
    try:
        return venue_id_for(v, c, **kw)
    except KeyError:
        return None


# ---------------------------------------------------------------- team table

def team_table(m: pd.DataFrame) -> pd.DataFrame:
    """One row per (Cricsheet name, gender, team type, competition) with ids, lineage and dates."""
    long = pd.concat([m.assign(team_raw=m[f"team{k}_raw"]) for k in (1, 2)])
    g = (long.groupby(["team_raw", "gender", "team_type", "competition_id"])
         .agg(n_matches=("match_id", "size"), first_date=("start_date", "min"), last_date=("start_date", "max"))
         .reset_index())
    g["team_name"] = [canonical_name(r, s) for r, s in zip(g.team_raw, g.gender)]
    g["team_id"] = [team_id_for(r, s, t) for r, s, t in zip(g.team_raw, g.gender, g.team_type)]
    g["succeeds"] = [SUCCEEDS_ID.get(i, ("", ""))[0] for i in g.team_id]
    g["lineage_id"] = g.team_id.map(lineage_id)
    g["country"] = [intl_country(n) if t == "international" else (comp_country(c) or "")
                    for n, t, c in zip(g.team_name, g.team_type, g.competition_id)]
    g["full_member_from"] = [full_member_from(c) if t == "international" else ""
                             for c, t in zip(g.country, g.team_type)]
    notes = []
    for r, s, i in zip(g.team_raw, g.gender, g.team_id):
        hit = _RENAME.get((r, s)) or _RENAME.get((r, ""))
        parts = [hit[1]] if hit else []
        if i in SUCCEEDS_ID:
            parts.append(f"succeeds {SUCCEEDS_ID[i][0]}: {SUCCEEDS_ID[i][1]}")
        notes.append("; ".join(parts))
    g["notes"] = notes
    return g[TEAM_COLUMNS].sort_values(["team_type", "gender", "team_id", "competition_id", "team_raw"],
                                       ignore_index=True)


def load_teams(path: Path | str = TEAMS_CSV) -> pd.DataFrame:
    return _load_csv(str(path), Path(path).stat().st_mtime_ns).copy()


@lru_cache(maxsize=4)
def _load_csv(path: str, mtime: int) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def team_country(team_id: str, path: Path | str = TEAMS_CSV) -> str:
    t = load_teams(path)
    hit = t.loc[t.team_id.eq(team_id) & t.team_type.eq("international"), "country"]
    return hit.iloc[0] if len(hit) else ""


# ---------------------------------------------------------------- home status

def venue_countries(venues: pd.DataFrame) -> dict[str, frozenset]:
    return {v: frozenset(x for x in (cc, c) if x) for v, cc, c in
            zip(venues.venue_id, venues.cricket_country, venues.country)}


def intl_status(country: str, opp_country: str, at: frozenset) -> str:
    """Plan 4.4: home in the team's own country, away in the opponent's, otherwise neutral."""
    mine, theirs = bool(country) and country in at, bool(opp_country) and opp_country in at
    return "home" if mine and not theirs else "away" if theirs and not mine else "neutral"


def _years_back(day: str) -> str:
    return f"{int(day[:4]) - LOOKBACK_YEARS}{day[4:10]}"


class _Season:
    __slots__ = ("first", "last", "n", "n_venue", "vt", "tv")

    def __init__(self):
        self.first = self.last = None
        self.n, self.n_venue = 0, Counter()
        self.vt, self.tv = defaultdict(Counter), defaultdict(Counter)

    def add(self, day: str, venue: str, teams) -> None:
        self.first = day if self.first is None else min(self.first, day)
        self.last = day if self.last is None else max(self.last, day)
        self.n += 1
        self.n_venue[venue] += 1
        for t in teams:
            self.vt[venue][t] += 1
            self.tv[t][venue] += 1


class HomeVenues:
    """Club home venues per competition season from the matches added so far.

    Build it from matches strictly before a cutoff (`home_venues_at`) or add matches day by day
    (`home_status_table`), so nothing a label uses can postdate the match it labels.
    """

    def __init__(self, venue_country: dict[str, str], comp_country: dict[str, str | None] | None = None):
        self.venue_country = venue_country
        self.comp_country = comp_country or {}
        self.seasons: dict[str, dict[str, _Season]] = defaultdict(dict)
        self._cache: dict = {}
        self.team_comps: dict[str, set] = defaultdict(set)

    def add(self, comp: str, season: str, day: str, venue: str, teams) -> None:
        self.seasons[comp].setdefault(season, _Season()).add(day, venue, teams)
        for t in teams:
            self.team_comps[t].add(comp)

    def abroad(self, comp: str, venue: str) -> bool:
        c, v = self.comp_country.get(comp), self.venue_country.get(venue)
        return bool(c and v and v != c)

    def owner(self, comp: str, s: _Season, venue: str, n_expected: float = 0) -> tuple[str | None, str]:
        """(the team the venue is home to in this season or None, the reason it is neutral).

        The host-share test divides by the larger of the season's matches and `n_expected`, so a season
        to date whose fixtures come in blocks by city is judged against its expected length."""
        if self.abroad(comp, venue):
            return None, "abroad"
        nv = s.n_venue[venue]
        if nv == 0:
            return None, "unplayed"
        if nv > HOST_SHARE_MAX * max(s.n, n_expected) + 1e-9:
            return None, "host_share"
        top = s.vt[venue].most_common(2)
        if (len(top) > 1 and top[0][1] == top[1][1]) or top[0][1] < DOMINANT_MIN * nv - 1e-9:
            return None, "no_dominant_team"
        return top[0][0], ""

    def rule(self, comp: str, s: _Season, team: str, venue: str, n_expected: float = 0) -> str:
        """'share' (plan rule), 'secondary' (extension) or '' for one team and venue in a season."""
        if self.owner(comp, s, venue, n_expected)[0] != team:
            return ""
        c, nt = s.tv[team][venue], sum(s.tv[team].values())
        if c >= SHARE_MIN * nt - 1e-9:
            return "share"
        return "secondary" if c >= SECONDARY_MIN and c >= SECONDARY_SHARE * s.n_venue[venue] - 1e-9 else ""

    def home_set(self, comp: str, season: str, team: str, n_expected: float = 0) -> frozenset:
        s = self.seasons[comp].get(season)
        if s is None or team not in s.tv:
            return frozenset()
        key = (comp, season, s.n, team, n_expected)
        if key not in self._cache:
            self._cache[key] = frozenset(v for v in s.tv[team] if self.rule(comp, s, team, v, n_expected))
        return self._cache[key]

    def earlier(self, comp: str, season: str, day: str) -> list[str]:
        """Seasons of the competition other than `season` that started before day, latest first."""
        return [k for k, s in sorted(self.seasons[comp].items(), key=lambda kv: kv[1].first, reverse=True)
                if k != season and s.first < day]

    def expected_n(self, comp: str, season: str, day: str) -> int:
        """Expected league-stage length of a season: the larger of the two previous seasons' (0 if none)."""
        return max([self.seasons[comp][k].n for k in self.earlier(comp, season, day)[:2]], default=0)

    def previous(self, comp: str, season: str, day: str, team: str) -> tuple[frozenset, str]:
        """The team's home venues before this season: venues whose latest home season of the competition
        in the last LOOKBACK_YEARS made them the team's (hub and abroad seasons have none), else its home
        venues in another competition (`elsewhere`)."""
        own = self.prior_owners(comp, season, day)
        h = frozenset(v for v, (t, _) in own.items() if t == team)
        if not h:
            return self.elsewhere(comp, day, team)
        return h, "prev:" + max((own[v][1] for v in h), key=lambda k: self.seasons[comp][k].first)

    def prior_owners(self, comp: str, season: str, day: str) -> dict[str, tuple[str, str]]:
        """venue -> (team, season) for the latest earlier season in which the venue was a team's home."""
        ks = [k for k in self.earlier(comp, season, day) if self.seasons[comp][k].first >= _years_back(day)]
        key = ("owners", comp, tuple((k, self.seasons[comp][k].n) for k in ks))
        if key not in self._cache:
            own: dict = {}
            for k in ks:
                for t in self.seasons[comp][k].tv:
                    for v in self.home_set(comp, k, t):
                        own.setdefault(v, (t, k))
            self._cache[key] = own
        return self._cache[key]

    def elsewhere(self, comp: str, day: str, team: str) -> tuple[frozenset, str]:
        """The team's home venues in its latest season of another competition (extension), as far as
        that season had been played, for a team new to this competition."""
        lo = _years_back(day)
        cand = sorted(((s.first, c, k) for c in self.team_comps.get(team, ()) if c != comp
                       for k, s in self.seasons[c].items() if lo <= s.first < day and team in s.tv), reverse=True)
        for _, c, k in cand:
            h = self.home_set(c, k, team)
            if h:
                return h, f"other:{c}:{k}"
        return frozenset(), "none"

    def status(self, comp: str, season: str, day: str, venue: str, a: str, b: str,
               full: bool = False) -> tuple[str, str, str, str]:
        """(status of a, status of b, source for a, source for b) for a match at venue on day.

        full: home venues from the whole season's league stage. As of the day (default): each team's
        home venues from earlier seasons (`previous`), joined by those of the season so far once it has
        ASOF_MIN_SEASON matches and the team ASOF_MIN_TEAM; the season so far makes the venue neutral
        only once it has max(ASOF_NEUTRAL_MIN, ASOF_SEASON_FRAC x the expected length) matches, judging
        host share against the expected length, so fixtures blocked by city do not look like a hub."""
        if self.abroad(comp, venue):
            return "neutral", "neutral", "abroad", "abroad"
        s = self.seasons[comp].get(season)
        homes, srcs = [], []
        if full:
            for t in (a, b):
                h, src = (self.home_set(comp, season, t), "season") if s is not None and t in s.tv else \
                    self.previous(comp, season, day, t)
                homes.append(h)
                srcs.append(src)
        else:
            n_exp = self.expected_n(comp, season, day)
            s = s if s is not None and s.n >= ASOF_MIN_SEASON else None
            if (s is not None and s.n >= max(ASOF_NEUTRAL_MIN, ASOF_SEASON_FRAC * n_exp)
                    and s.n_venue[venue] >= ASOF_MIN_VENUE and self.owner(comp, s, venue, n_exp)[0] is None):
                return "neutral", "neutral", "season_neutral", "season_neutral"
            for t in (a, b):
                h, src = self.previous(comp, season, day, t)
                if s is not None and sum(s.tv.get(t, {}).values()) >= ASOF_MIN_TEAM:
                    # this season's grounds plus earlier ones no other team has taken (festival outgrounds)
                    h = self.home_set(comp, season, t, n_exp) | {
                        v for v in h if self.owner(comp, s, v, n_exp)[0] in (None, t)}
                    src = "season"
                homes.append(h)
                srcs.append(src)
        ha, hb = venue in homes[0], venue in homes[1]
        st = ("home", "away") if ha and not hb else ("away", "home") if hb and not ha else ("neutral", "neutral")
        return st[0], st[1], srcs[0], srcs[1]

    def table(self) -> pd.DataFrame:
        """Every home (team, venue) per competition season with the counts behind it."""
        rows = []
        for comp, seasons in self.seasons.items():
            for season, s in seasons.items():
                for team, vs in s.tv.items():
                    nt = sum(vs.values())
                    for v, c in vs.items():
                        r = self.rule(comp, s, team, v)
                        if r:
                            rows.append(dict(comp_key=comp, season=season, season_first=s.first, team_id=team,
                                             venue_id=v, rule=r, n_team=nt, n_team_venue=c,
                                             n_venue=s.n_venue[v], n_season=s.n, share=round(c / nt, 3),
                                             dominance=round(s.vt[v][team] / s.n_venue[v], 3)))
        cols = ["comp_key", "season", "season_first", "team_id", "venue_id", "rule", "n_team", "n_team_venue",
                "n_venue", "n_season", "share", "dominance"]
        return pd.DataFrame(rows, columns=cols).sort_values(["comp_key", "season_first", "team_id", "venue_id"],
                                                             ignore_index=True)

    def neutral_venues(self) -> pd.DataFrame:
        rows = [dict(comp_key=comp, season=season, venue_id=v, n_venue=s.n_venue[v], reason=self.owner(comp, s, v)[1])
                for comp, seasons in self.seasons.items() for season, s in seasons.items() for v in s.n_venue]
        return pd.DataFrame(rows, columns=["comp_key", "season", "venue_id", "n_venue", "reason"])


def _club_frame(m: pd.DataFrame) -> pd.DataFrame:
    return m[m.team_type.eq("club") & m.venue_id.notna()].sort_values(["start_date", "match_id"])


def _league_stage(m: pd.DataFrame) -> np.ndarray:
    """False for knockout matches, which are labelled but do not define home venues."""
    return ~np.array([is_knockout(s) for s in m.stage], dtype=bool)


def _new_home_venues(m: pd.DataFrame, venues: pd.DataFrame) -> HomeVenues:
    vc = dict(zip(venues.venue_id, venues.cricket_country))
    cc = {k: (None if str(k).startswith("other:") else comp_country(k)) for k in m.comp_key.unique()}
    return HomeVenues(vc, cc)


def home_venues_at(m: pd.DataFrame, cutoff: str | None = None, venues: pd.DataFrame | None = None) -> HomeVenues:
    """Home venues from club matches starting strictly before cutoff (all matches when None)."""
    venues = load_venues() if venues is None else venues
    club = _club_frame(m)
    club = club[_league_stage(club)]
    if cutoff is not None:
        club = club[club.start_date < str(cutoff)[:10]]
    hv = _new_home_venues(m, venues)
    for r in club.itertuples():
        hv.add(r.comp_key, r.season, r.start_date, r.venue_id, (r.team1_id, r.team2_id))
    return hv


def home_status(team_id: str, opponent_id: str, team_type: str, venue_id: str, competition_id: str | None = None,
                season: str | None = None, day: str | None = None, homes: HomeVenues | None = None,
                venues: pd.DataFrame | None = None, team_countries: tuple[str, str] | None = None) -> str:
    """'home', 'away' or 'neutral' for team_id against opponent_id at venue_id (plan 4.4).

    Clubs need `homes` built from matches before the match day (`home_venues_at(matches, day)`); a
    season absent from it, such as a forecast season, falls back to the team's previous seasons. A
    venue_id missing from the venue table raises KeyError rather than reading as neutral.
    """
    venues = load_venues() if venues is None else venues
    if not venues.venue_id.eq(venue_id).any():
        raise KeyError(f"venue_id {venue_id!r} is not in the venue table")
    if team_type == "international":
        at = venue_countries(venues[venues.venue_id.eq(venue_id)]).get(venue_id, frozenset())
        a, b = team_countries or (team_country(team_id), team_country(opponent_id))
        return intl_status(a, b, at)
    if homes is None:
        raise ValueError("club home status needs a HomeVenues built from earlier matches")
    return homes.status(competition_id, season, day or "9999-12-31", venue_id, team_id, opponent_id)[0]


def home_status_table(m: pd.DataFrame, venues: pd.DataFrame | None = None) -> tuple[pd.DataFrame, HomeVenues]:
    """Per match: as-of and full-season home status of both teams, plus the full-season HomeVenues.

    home_status1/2 are as of the match day (from matches on earlier days only) and home_source1/2 say
    what decided them (`season`, `prev:<season>`, `other:<competition>:<season>`, `none`,
    `season_neutral`, `abroad`, `country`, `no_venue`); home_status1/2_full are the full-season labels."""
    venues = load_venues() if venues is None else venues
    at = venue_countries(venues)
    out = {}
    intl = m[m.team_type.eq("international")]
    for r in intl.itertuples():
        where = at.get(r.venue_id, frozenset())
        s1 = intl_status(r.team1_country, r.team2_country, where)
        s2 = intl_status(r.team2_country, r.team1_country, where)
        out[r.match_id] = (s1, s2, "country", "country", s1, s2)
    club = _club_frame(m)
    full = home_venues_at(m, None, venues)
    hv = _new_home_venues(m, venues)
    for _, g in club.groupby("start_date", sort=True):
        rows = list(g.itertuples())
        for r in rows:
            a = hv.status(r.comp_key, r.season, r.start_date, r.venue_id, r.team1_id, r.team2_id)
            f = full.status(r.comp_key, r.season, r.start_date, r.venue_id, r.team1_id, r.team2_id, full=True)
            out[r.match_id] = (a[0], a[1], a[2], a[3], f[0], f[1])
        for r in rows:
            if not is_knockout(r.stage):
                hv.add(r.comp_key, r.season, r.start_date, r.venue_id, (r.team1_id, r.team2_id))
    cols = ["home_status1", "home_status2", "home_source1", "home_source2", "home_status1_full", "home_status2_full"]
    st = pd.DataFrame.from_dict(out, orient="index", columns=cols).rename_axis("match_id").reset_index()
    res = m[["match_id"]].merge(st, on="match_id", how="left")
    for c in cols:
        res[c] = res[c].fillna("neutral" if "status" in c else "no_venue")
    return res, full


# ---------------------------------------------------------------- start slots

def _offsets(m: pd.DataFrame, venues: pd.DataFrame) -> pd.Series:
    v = venues.set_index("venue_id")
    base = m.venue_id.map(v.utc_offset_hours).astype(float)
    region = m.venue_id.map(v.dst_region).fillna("none")
    return base + [dst_shift(r, d) if not np.isnan(b) else 0.0 for r, d, b in zip(region, m.start_date, base)]


def start_slots(m: pd.DataFrame, venues: pd.DataFrame | None = None) -> pd.DataFrame:
    """start_slot, source, confidence and note for every match (see the module docstring)."""
    venues = load_venues() if venues is None else venues
    vmeta = venues.set_index("venue_id")
    out = m[["match_id", "start_date", "competition_id", "venue_id"]].copy()
    out["start_slot"], out["source"], out["confidence"], out["note"] = "unknown", "no_rule", "", ""

    def put(mask, slot, source, conf, note=""):
        mask = np.asarray(mask, dtype=bool)
        out.loc[mask, ["start_slot", "source", "confidence", "note"]] = [
            slot, source, conf if slot != "unknown" else "", note]

    country = m.venue_id.map(vmeta.cricket_country).fillna("")
    intl, comp, d = m.team_type.eq("international"), m.competition_id, m.start_date
    female = m.gender.eq("female")
    # first-class cricket by day; Tests after the curated list, women's Tests in Australia and the
    # County Championship's floodlit round are less certain
    test = m.match_type.isin(["Test", "MDM"]) & intl
    put(test, "day", "test_default", "high")
    put(test & d.gt(PINK_LIST_END), "day", "test_default_after_list", "medium")
    put(test & female & country.eq("Australia") & m.match_type.eq("Test"), "unknown", "womens_test_australia", "")
    put(comp.isin(FIRST_CLASS_DAY), "day", "first_class_default", "high")
    put(comp.eq("sheffield_shield") & d.lt("2020-07-01"), "day", "first_class_default", "medium",
        "occasional pink-ball day/night Shield rounds not identified")
    put(comp.eq("county_championship") & d.isin(COUNTY_PINK_ROUND), "day_night", "county_floodlit_round", "medium")
    for cid, since in ONE_DAY_DAY.items():
        put(comp.eq(cid) & (d.ge(since) if since else True), "day", "domestic_one_day_default", "medium")
    # international limited-overs patterns
    full = intl & ~m.assoc_match.astype(bool)
    icc = m.event_id.isin(ICC_EVENTS)
    odi = m.match_type.eq("ODI") & ~female & (full | icc)
    for c, since in ODI_DN_COUNTRIES.items():
        put(odi & country.eq(c) & (d.ge(since) if since else True), "day_night", "odi_country_pattern", "medium")
    put(odi & country.eq("Sri Lanka") & m.venue_id.isin(ODI_DN_VENUES), "day_night", "odi_floodlit_venue", "medium")
    put(odi & m.venue_id.isin(ODI_UNKNOWN_VENUES), "unknown", "odi_day_start_venue", "")
    put(m.match_type.eq("ODI") & female & m.event_id.eq("icc_cwc") & d.between("2025-09-01", "2025-11-30"),
        "day_night", "womens_cwc_2025_afternoon_starts", "medium")
    t20i = m.match_type.eq("T20") & intl & ~female & (full | icc)
    for c, conf in T20I_NIGHT.items():
        put(t20i & country.eq(c), "night", "t20i_country_pattern", conf)
    # earlier match of an ICC multi-match day where the host pattern is an evening slot
    known = out.start_slot.isin(["night", "day_night"]).to_numpy()
    _multi_match_days(m, out, put, intl & icc & m.match_type.isin(["ODI", "T20"]) & known, venues,
                      ("day", None, "medium"), "icc_double_header", key="event_name")
    # franchise leagues
    for cid, (single, early, late, conf) in LEAGUE_SLOTS.items():
        sel = comp.eq(cid)
        put(sel, single, f"{cid}_single_default", conf)
        _multi_match_days(m, out, put, sel, venues, (early, late, conf), f"{cid}_double_header")
    # IPL 2009 in South Africa kept Indian broadcast times: the evening game started about 16:30 local
    put(comp.eq("ipl") & country.eq("South Africa") & out.start_slot.eq("night"), "day_night",
        "ipl_2009_south_africa", "medium")
    for cid, day in SIMULTANEOUS_DAYS:   # two evening games at once, not an afternoon-evening pair
        put(comp.eq(cid) & d.eq(day), "night", "simultaneous_league_games", "high")
    # women's match before the men's at the same ground on the same day
    limited = ~m.match_type.isin(["Test", "MDM"])
    pairs = m[limited].groupby(["start_date", "venue_id"]).gender.agg(set)
    both = pairs[pairs.map(lambda g: g == {"male", "female"})].index
    key = pd.MultiIndex.from_arrays([m.start_date, m.venue_id])
    shared = key.isin(both) & limited
    put(shared & female & ~comp.isin(["wbbl"]), "day", "women_before_men_same_ground", "medium")
    put(shared & ~female & comp.eq("hundred_m"), "day_night", "hundred_men_after_women", "medium")
    # WBBL: earlier games of a same-ground multi-match day, and curtain raisers to BBL games
    w = comp.eq("wbbl")
    mn = m.match_number.astype("float")
    last_mn = mn[w].groupby([m.start_date[w], m.venue_id[w]]).transform("max").reindex(m.index)
    put(w & (mn < last_mn), "day", "wbbl_same_ground_earlier", "high")
    bbl_keys = pd.MultiIndex.from_frame(m.loc[comp.eq("bbl"), ["start_date", "venue_id"]])
    put(w & key.isin(bbl_keys), "day", "wbbl_curtain_raiser", "medium")
    # curated day/night Tests last, so they win
    for day, g, home, away, ground in PINK_BALL_TESTS:
        hit = (test & m.match_type.eq("Test") & d.eq(day) & m.gender.eq(g)
               & (m.team1_raw.isin([home, away]) & m.team2_raw.isin([home, away])))
        put(hit, "day_night", "pink_ball_list", "high", f"{home} v {away}, {ground}")
    return out


def load_start_slots(path: Path | str = DAY_NIGHT_CSV) -> pd.DataFrame:
    """The curated slot table; matches missing from it have no rule and are 'unknown'."""
    return _load_csv(str(path), Path(path).stat().st_mtime_ns).copy()


def start_slot_for(match_id: int, path: Path | str = DAY_NIGHT_CSV) -> str:
    t = _slot_index(str(path), Path(path).stat().st_mtime_ns)
    return t.get(str(match_id), "unknown")


@lru_cache(maxsize=2)
def _slot_index(path: str, mtime: int) -> dict:
    t = _load_csv(path, mtime)
    return dict(zip(t.match_id, t.start_slot))


def _multi_match_days(m, out, put, sel, venues, slots, source, key="competition_id"):
    """Order the selected matches of each competition-day by match_number and set earlier/last slots.

    slots = (earlier, last, confidence); last None leaves the last match as it was. A middle match of
    three, or an earlier match when a later one that day is TZ_GAP_HOURS or more further west, is unknown.
    """
    sel = np.asarray(sel, dtype=bool)
    if not sel.any():
        return
    early, late, conf = slots
    x = m[sel].assign(off=_offsets(m[sel], venues).to_numpy(), mn=m.match_number[sel].astype("float"))
    x = x[x.groupby([key, "start_date"]).match_id.transform("size") >= 2]
    for _, g in x.sort_values([key, "start_date", "mn"]).groupby([key, "start_date"]):
        ids = g.match_id.to_numpy()
        if g.mn.isna().any() or g.mn.duplicated().any():
            put(m.match_id.isin(ids), "unknown", f"{source}_unordered", "")
            continue
        offs = g.off.to_numpy()
        for j, mid in enumerate(ids):
            mask = m.match_id.eq(mid)
            if j == len(ids) - 1:
                if late:
                    put(mask, late, source, conf)
            elif j > 0 or np.nanmin(offs[j + 1:]) <= offs[j] - TZ_GAP_HOURS:
                put(mask, "unknown", f"{source}_ambiguous", "")
            else:
                put(mask, early, source, conf)


# ---------------------------------------------------------------- validation

def _win_rate(df: pd.DataFrame, s1: str, s2: str) -> dict:
    d = df[df.winner_id.notna() & df.result.eq("win")]
    h1 = d[s1].eq("home") & d[s2].eq("away")
    h2 = d[s2].eq("home") & d[s1].eq("away")
    won = int(((d.winner_id == d.team1_id) & h1).sum() + ((d.winner_id == d.team2_id) & h2).sum())
    n = int(h1.sum() + h2.sum())
    return dict(n_decisive=n, home_wins=won, home_win_rate=round(won / n, 3) if n else None)


def _event_host_rate(df: pd.DataFrame) -> dict:
    """The domain review's definition: host named by the event ('X tour of Y', 'X in Y ... Series')."""
    rx1, rx2 = re.compile(r" tour of (.+)$"), re.compile(r" in (.+?)(?: (?:Test|ODI|T20I?|T20) Series)?$")
    won = n = 0
    for ev, t1, t2, w in zip(df.event_name.fillna(""), df.team1_raw, df.team2_raw, df.winner_raw):
        hit = rx1.search(ev) or rx2.search(ev)
        host = hit.group(1).strip() if hit else None
        if host in (t1, t2) and isinstance(w, str):
            n += 1
            won += w == host
    return dict(n_decisive=n, host_wins=won, host_win_rate=round(won / n, 3) if n else None)


def _pink_venue_mismatch(m: pd.DataFrame, slots: pd.DataFrame) -> list:
    hit = slots[slots.source.eq("pink_ball_list")].merge(m[["match_id", "venue_raw"]], on="match_id")
    ground = hit.note.str.split(", ", n=1).str[1].fillna("")
    return hit.loc[[max(g.split(), key=len).lower() not in str(v).lower() for g, v in zip(ground, hit.venue_raw)],
                   ["match_id", "start_date", "venue_raw", "note"]].values.tolist()


def _side(s1: pd.Series, s2: pd.Series) -> np.ndarray:
    return np.where(s1.eq("home") & s2.eq("away"), "team1", np.where(s2.eq("home") & s1.eq("away"), "team2", "neutral"))


def _asof_vs_full(c: pd.DataFrame) -> dict:
    """How the as-of labels compare with the full-season ones, and what decided the disagreements."""
    a, f = _side(c.home_status1, c.home_status2), _side(c.home_status1_full, c.home_status2_full)
    kind = np.where(a == f, "agree", np.where(a == "neutral", "asof_neutral_full_home",
                                              np.where(f == "neutral", "asof_home_full_neutral", "flipped")))
    src = (c.home_source1.str.replace(r":.*", "", regex=True) + "/"
           + c.home_source2.str.replace(r":.*", "", regex=True))
    miss = kind == "asof_neutral_full_home"
    return dict(n_matches=len(c), agreement=round(float((a == f).mean()), 4) if len(c) else None,
                coverage_asof=round(float((a != "neutral").mean()), 3) if len(c) else None,
                coverage_full=round(float((f != "neutral").mean()), 3) if len(c) else None,
                by_kind=pd.Series(kind).value_counts().to_dict(),
                asof_neutral_full_home_by_source=src[miss].value_counts().to_dict(),
                asof_home_full_neutral_by_source=src[kind == "asof_home_full_neutral"].value_counts().to_dict(),
                home_win_agree=_win_rate(c[kind == "agree"], "home_status1", "home_status2"),
                home_win_asof_only=_win_rate(c[kind == "asof_home_full_neutral"], "home_status1", "home_status2"),
                home_win_full_only=_win_rate(c[miss], "home_status1_full", "home_status2_full"))


ASOF_EXAMPLES = {1354937: "PSL 2022/23 at Karachi, which hosted 8 of the season's first 13 games and 9 of 34"}
EXPECTED_SAME_SEASON = {("blast", "2026", "warwickshire_m"): "Cricsheet switches from Birmingham Bears to "
                        "Warwickshire mid-season (2026-05-29)"}


def validate(m: pd.DataFrame, teams: pd.DataFrame, slots: pd.DataFrame, homes: HomeVenues) -> dict:
    rep: dict = {}
    # lineage
    merged = teams.groupby("team_id").team_raw.agg(lambda x: sorted(set(x)))
    long = pd.concat([m.assign(raw=m[f"team{k}_raw"], tid=m[f"team{k}_id"]) for k in (1, 2)])
    per = long.groupby(["competition_id", "season", "tid"]).raw.nunique()
    names = teams.groupby("team_id").team_name.nunique()
    rep["lineage"] = dict(
        n_rows=len(teams), n_raw_names=int(teams[["team_raw", "gender", "team_type"]].drop_duplicates().shape[0]),
        n_team_ids=int(teams.team_id.nunique()),
        n_club_ids=int(teams.loc[teams.team_type.eq("club"), "team_id"].nunique()),
        n_international_ids=int(teams.loc[teams.team_type.eq("international"), "team_id"].nunique()),
        merged_ids={k: v for k, v in merged.items() if len(v) > 1},
        n_with_predecessor=int(teams.loc[teams.succeeds.ne(""), "team_id"].nunique()),
        two_names_one_id_same_season={":".join(k): EXPECTED_SAME_SEASON.get(k, "UNEXPECTED")
                                      for k in per[per > 1].index},
        ids_with_two_canonical_names=names[names > 1].index.tolist(),
        self_matches=int((m.team1_id == m.team2_id).sum()),
        matches_without_venue_id=int(m.venue_id.isna().sum()),
        full_members=sorted(teams.loc[teams.full_member_from.ne(""), "country"].unique().tolist()))
    # home status
    intl = m[m.team_type.eq("international") & m.match_type.isin(["Test", "ODI", "T20"])]
    bil = intl[intl.event_id.eq("bilateral")]
    target = {"TEST": 0.611, "ODI": 0.592, "T20": 0.543}
    rep["intl_home_win"] = {
        f"{fam}_{g}": dict(bilateral=_win_rate(bil[bil.fam.eq(fam) & bil.gender.eq(g)], "home_status1", "home_status2"),
                           all_events=_win_rate(intl[intl.fam.eq(fam) & intl.gender.eq(g)], "home_status1",
                                                "home_status2"),
                           event_host_definition=_event_host_rate(intl[intl.fam.eq(fam) & intl.gender.eq(g)]),
                           target_men_event_host=target[fam] if g == "male" else None)
        for fam in ("TEST", "ODI", "T20") for g in ("male", "female")}
    club = m[m.team_type.eq("club")]
    comps = club.competition_id.value_counts()
    rep["club_home_win"] = {}
    for cid in comps.index[comps >= 50]:
        c = club[club.competition_id.eq(cid)]
        st = pd.concat([c.home_status1, c.home_status2]).value_counts().to_dict()
        agree = float(((c.home_status1 == c.home_status1_full) & (c.home_status2 == c.home_status2_full)).mean())
        rep["club_home_win"][cid] = dict(n_matches=len(c), asof=_win_rate(c, "home_status1", "home_status2"),
                                         full=_win_rate(c, "home_status1_full", "home_status2_full"),
                                         asof_status_counts=st, asof_full_agreement=round(agree, 3))
    tier = club.competition_id.map(lambda c: competition_meta(c)["tier"])
    rep["club_home_win_pooled"] = {t: dict(asof=_win_rate(club[tier.eq(t)], "home_status1", "home_status2"),
                                           full=_win_rate(club[tier.eq(t)], "home_status1_full", "home_status2_full"))
                                   for t in sorted(tier.unique())}
    rep["club_home_win_pooled"]["all"] = dict(asof=_win_rate(club, "home_status1", "home_status2"),
                                              full=_win_rate(club, "home_status1_full", "home_status2_full"))
    with_venue = club.venue_id.notna()
    rep["asof_vs_full"] = {"all": _asof_vs_full(club[with_venue]),
                           **{t: _asof_vs_full(club[with_venue & tier.eq(t)]) for t in sorted(tier.unique())}}
    ex = m.set_index("match_id")
    rep["asof_examples"] = {str(k): dict(note=note, **ex.loc[k, ["team1_id", "team2_id", "venue_id", "home_status1",
                                                                  "home_status2", "home_source1", "home_status1_full",
                                                                  "home_status2_full"]].to_dict())
                            for k, note in ASOF_EXAMPLES.items() if k in ex.index}
    ht = homes.table()
    nv = homes.neutral_venues()
    rep["home_venues"] = dict(
        n_rows=len(ht), by_rule=ht.rule.value_counts().to_dict(),
        neutral_reasons=nv.reason.replace("", "home_or_open").value_counts().to_dict(),
        seasons_all_neutral=sorted({f"{k}:{s}" for k, s in nv.groupby(["comp_key", "season"]).reason
                                    .agg(lambda r: (r != "").all()).pipe(lambda x: x[x]).index}),
        asof_sources=pd.concat([club.home_source1, club.home_source2]).str.replace(r":.*", "", regex=True)
        .value_counts().to_dict())
    # start slots
    s = slots.merge(m[["match_id", "match_type", "gender", "team_type", "toss_decision"]], on="match_id")
    cov = s.assign(known=s.start_slot.ne("unknown")).groupby("competition_id").agg(
        n=("match_id", "size"), known_share=("known", "mean"))
    cov["known_share"] = cov.known_share.round(3)
    by_slot = s.groupby(["competition_id", "start_slot"]).size().unstack(fill_value=0)
    rep["start_slot"] = dict(
        overall_known_share=round(float(s.start_slot.ne("unknown").mean()), 3),
        invalid_slots=int((~s.start_slot.isin(SLOTS)).sum()),
        by_slot=s.start_slot.value_counts().to_dict(), by_source=s.source.value_counts().to_dict(),
        coverage_by_competition={k: dict(n=int(r.n), known_share=float(r.known_share),
                                         **{c: int(by_slot.at[k, c]) for c in by_slot.columns})
                                 for k, r in cov.sort_values("n", ascending=False).iterrows()},
        pink_ball_listed=len(PINK_BALL_TESTS), pink_ball_matched=int(s.source.eq("pink_ball_list").sum()),
        pink_ball_venue_mismatch=_pink_venue_mismatch(m, slots),
        pink_ball_unmatched=[p for p in PINK_BALL_TESTS if not (s.source.eq("pink_ball_list")
                                                                & s.start_date.eq(p[0])).any()],
        toss_field_share_by_slot={
            cid: g.groupby("start_slot").toss_decision.agg(lambda x: round(float((x == "field").mean()), 3)).to_dict()
            for cid, g in s[s.competition_id.isin([*LEAGUE_SLOTS, "intl_t20_m", "intl_odi_m"])].groupby("competition_id")})
    return rep


def build(zip_path: Path | str = CRICSHEET_ZIP, venues_path: Path | str | None = None):
    venues = load_venues() if venues_path is None else load_venues(venues_path)
    m = add_ids(scan_matches(zip_path), venues_path)
    teams = team_table(m)
    status, homes = home_status_table(m, venues)
    m = m.merge(status, on="match_id")
    slots = start_slots(m, venues)
    return m, teams, slots, homes


def main() -> None:
    m, teams, slots, homes = build()
    teams.to_csv(TEAMS_CSV, index=False)
    slots.loc[slots.source.ne("no_rule"), SLOT_COLUMNS].sort_values(["start_date", "match_id"]) \
        .to_csv(DAY_NIGHT_CSV, index=False)
    HOMES_CSV.parent.mkdir(parents=True, exist_ok=True)
    homes.table().drop(columns="season_first").to_csv(HOMES_CSV, index=False)
    MATCH_TEAMS.parent.mkdir(parents=True, exist_ok=True)
    keep = ["match_id", "file_stem", "start_date", "season", "competition_id", "comp_key", "venue_id", "team1_raw", "team2_raw",
            "team1_id", "team2_id", "team1", "team2", "home_status1", "home_status2", "home_source1", "home_source2",
            "home_status1_full", "home_status2_full"]
    m[keep].merge(slots[["match_id", "start_slot", "source", "confidence"]].rename(
        columns={"source": "start_slot_source", "confidence": "start_slot_confidence"}), on="match_id") \
        .to_parquet(MATCH_TEAMS, index=False)
    rep = dict(params=dict(share_min=SHARE_MIN, host_share_max=HOST_SHARE_MAX, dominant_min=DOMINANT_MIN,
                           secondary_share=SECONDARY_SHARE, secondary_min=SECONDARY_MIN, asof_min_season=ASOF_MIN_SEASON,
                           asof_min_team=ASOF_MIN_TEAM, asof_neutral_min=ASOF_NEUTRAL_MIN,
                           asof_season_frac=ASOF_SEASON_FRAC, asof_min_venue=ASOF_MIN_VENUE,
                           lookback_years=LOOKBACK_YEARS, tz_gap_hours=TZ_GAP_HOURS),
               rows={"config/cricket-teams.csv": len(teams),
                     "config/cricket-day-night.csv": int(slots.source.ne("no_rule").sum()),
                     "data/derived/cricket/team-home-venues.csv": len(homes.table()),
                     "data/processed/cricket/match_teams.parquet": len(m)},
               **validate(m, teams, slots, homes))
    REPORT.write_text(json.dumps(rep, indent=1, default=str) + "\n")
    print(json.dumps({k: rep[k] for k in ("rows", "intl_home_win")}, indent=1, default=str))


if __name__ == "__main__":
    main()
