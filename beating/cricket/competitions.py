"""Canonical competitions, tiers and season keys for Cricsheet matches.

Method. International matches (``team_type == 'international'``) always map to
``intl_<fmt>_<m|w>`` from the Cricsheet ``match_type`` family (Test/MDM -> test,
ODI/ODM -> odi, T20/IT20 -> t20); the event name only sets a finer ``event_id``
(ICC World Cup, T20 World Cup, qualifier, bilateral tour, multi-nation series, ...),
which the rules timeline uses for event-level overrides such as super overs.
``assoc_match`` is set when either side was not an ICC full member on the match
date (Zimbabwe from 1992-07-06, Bangladesh from 2000-06-26, Ireland and
Afghanistan from 2017-06-22; composite World/Asia/Africa XIs count as full) and
``official`` is False for IT20/ODM/MDM internationals, which carry no
T20I/ODI/Test status. Club matches map by the normalised event name through an
ordered regex alias table that absorbs sponsor renames (NatWest/Vitality Blast,
LV=/Specsavers County Championship, Marsh Sheffield Shield, HRV Cup -> Super
Smash, Ram Slam -> CSA T20 Challenge, Royal London -> One-Day Cup, ...). A club
event that matches nothing falls back to ``other_<fmt>_<m|w>`` with
``generic=True`` so every match maps; :func:`scan_events` reports those counts.

Limits. Mapping is by name, so a new sponsor name for a known competition maps to
the generic id until an alias is added. 'One-Day Cup' without a country is taken
to be England's (it is in Cricsheet 2023-2026). Full membership is by team name,
so A sides, Lions and development XIs appearing as 'international' would count as
associates. Bilateral versus multi-nation is guessed from the event name.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

FMT_FAMILY = {"Test": "TEST", "MDM": "TEST", "ODI": "ODI", "ODM": "ODI", "T20": "T20", "IT20": "T20"}
OFFICIAL_TYPES = {"Test", "ODI", "T20"}
TIERS = ("intl_full", "intl_assoc", "franchise_major", "domestic_major", "domestic_minor")

FULL_MEMBERS = {
    "England": "1900-01-01", "Australia": "1900-01-01", "South Africa": "1900-01-01",
    "West Indies": "1900-01-01", "New Zealand": "1900-01-01", "India": "1900-01-01",
    "Pakistan": "1900-01-01", "Sri Lanka": "1900-01-01", "Zimbabwe": "1992-07-06",
    "Bangladesh": "2000-06-26", "Ireland": "2017-06-22", "Afghanistan": "2017-06-22",
    "ICC World XI": "1900-01-01", "World XI": "1900-01-01", "Asia XI": "1900-01-01",
    "Africa XI": "1900-01-01",
}

# id: (display name, tier, fmt family, gender, country)
CLUB = {
    "ipl": ("Indian Premier League", "franchise_major", "T20", "male", "IND"),
    "bbl": ("Big Bash League", "franchise_major", "T20", "male", "AUS"),
    "psl": ("Pakistan Super League", "franchise_major", "T20", "male", "PAK"),
    "cpl": ("Caribbean Premier League", "franchise_major", "T20", "male", "WI"),
    "sa20": ("SA20", "franchise_major", "T20", "male", "RSA"),
    "ilt20": ("International League T20", "franchise_major", "T20", "male", "UAE"),
    "mlc": ("Major League Cricket", "franchise_major", "T20", "male", "USA"),
    "bpl": ("Bangladesh Premier League", "franchise_major", "T20", "male", "BAN"),
    "lpl": ("Lanka Premier League", "franchise_major", "T20", "male", "SL"),
    "msl": ("Mzansi Super League", "franchise_major", "T20", "male", "RSA"),
    "hundred_m": ("The Hundred (men)", "franchise_major", "HUNDRED", "male", "ENG"),
    "hundred_w": ("The Hundred (women)", "franchise_major", "HUNDRED", "female", "ENG"),
    "wpl": ("Women's Premier League", "franchise_major", "T20", "female", "IND"),
    "wbbl": ("Women's Big Bash League", "franchise_major", "T20", "female", "AUS"),
    "wcpl": ("Women's Caribbean Premier League", "franchise_major", "T20", "female", "WI"),
    "wcsl": ("Women's Cricket Super League", "franchise_major", "T20", "female", "ENG"),
    "blast": ("T20 Blast", "domestic_major", "T20", "male", "ENG"),
    "blast_w": ("T20 Blast (women)", "domestic_major", "T20", "female", "ENG"),
    "charlotte_edwards_cup": ("Charlotte Edwards Cup", "domestic_major", "T20", "female", "ENG"),
    "county_championship": ("County Championship", "domestic_major", "TEST", "male", "ENG"),
    "eng_one_day_cup": ("One-Day Cup (England)", "domestic_major", "ODI", "male", "ENG"),
    "eng_women_one_day": ("Women's One-Day Cup (England)", "domestic_major", "ODI", "female", "ENG"),
    "sheffield_shield": ("Sheffield Shield", "domestic_major", "TEST", "male", "AUS"),
    "aus_one_day_cup": ("One-Day Cup (Australia)", "domestic_major", "ODI", "male", "AUS"),
    "wncl": ("Women's National Cricket League", "domestic_major", "ODI", "female", "AUS"),
    "plunket_shield": ("Plunket Shield", "domestic_major", "TEST", "male", "NZ"),
    "ford_trophy": ("Ford Trophy", "domestic_major", "ODI", "male", "NZ"),
    "super_smash": ("Super Smash", "domestic_major", "T20", "male", "NZ"),
    "super_smash_w": ("Women's Super Smash", "domestic_major", "T20", "female", "NZ"),
    "smat": ("Syed Mushtaq Ali Trophy", "domestic_major", "T20", "male", "IND"),
    "ranji_trophy": ("Ranji Trophy", "domestic_major", "TEST", "male", "IND"),
    "vijay_hazare": ("Vijay Hazare Trophy", "domestic_major", "ODI", "male", "IND"),
    "csa_t20": ("CSA T20 Challenge", "domestic_major", "T20", "male", "RSA"),
    "csa_4day": ("CSA 4-Day Series", "domestic_major", "TEST", "male", "RSA"),
    "csa_one_day": ("CSA One-Day Cup", "domestic_major", "ODI", "male", "RSA"),
    "quaid_e_azam": ("Quaid-e-Azam Trophy", "domestic_major", "TEST", "male", "PAK"),
    "pak_national_t20": ("National T20 Cup", "domestic_major", "T20", "male", "PAK"),
    "slc_major_clubs_t20": ("Major Clubs T20 Tournament", "domestic_major", "T20", "male", "SL"),
    "slc_major_clubs_odm": ("Major Clubs Limited Over Tournament", "domestic_major", "ODI", "male", "SL"),
    "slc_major_league": ("Major League Tournament", "domestic_major", "TEST", "male", "SL"),
    "wi_women_super50": ("Women's Super50 Cup", "domestic_major", "ODI", "female", "WI"),
    "wi_women_t20": ("Women's T20 Blaze", "domestic_major", "T20", "female", "WI"),
    "ire_ip_t20": ("Inter-Provincial Twenty20 Trophy", "domestic_minor", "T20", "male", "IRE"),
    "ire_ip_odm": ("Inter-Provincial Limited Over Cup", "domestic_minor", "ODI", "male", "IRE"),
    "ire_ip_fc": ("Inter-Provincial Championship", "domestic_minor", "TEST", "male", "IRE"),
    "womens_t20_challenge": ("Women's T20 Challenge", "domestic_minor", "T20", "female", "IND"),
    "fairbreak": ("FairBreak Invitational", "domestic_minor", "T20", "female", "INT"),
    "npl": ("Nepal Premier League", "domestic_minor", "T20", "male", "NEP"),
    "etpl": ("European T20 Premier League", "domestic_minor", "T20", "male", "EUR"),
    "global_t20_canada": ("Global T20 Canada", "domestic_minor", "T20", "male", "CAN"),
}

# Ordered (pattern, id) on the normalised event name; first match wins.
CLUB_ALIASES = [
    (r"^indian premier league|^ipl\b", "ipl"),
    (r"^women'?s big bash", "wbbl"),
    (r"^(kfc |kfc t20 )?big bash league|^bbl\b", "bbl"),
    (r"^pakistan super league|^psl\b", "psl"),
    (r"^women'?s caribbean premier league", "wcpl"),
    (r"^(hero |republic bank |dream11 )?caribbean premier league|^cpl\b", "cpl"),
    (r"^(betway )?sa20\b", "sa20"),
    (r"^(dp world )?international league t20|^ilt20\b", "ilt20"),
    (r"^major league cricket", "mlc"),
    (r"^bangladesh premier league", "bpl"),
    (r"^lanka premier league", "lpl"),
    (r"^mzansi super league", "msl"),
    (r"^the hundred women", "hundred_w"),
    (r"^the hundred", "hundred_m"),
    (r"^women'?s premier league", "wpl"),
    (r"^(kia )?women'?s cricket super league|^kia super league", "wcsl"),
    (r"^(natwest |vitality |friends provident |friends life )?(t20 blast|blast) women", "blast_w"),
    (r"^(natwest |vitality |friends provident |friends life )?(t20 blast|blast|t20)( men)?$|^twenty20 cup$", "blast"),
    (r"^charlotte edwards cup", "charlotte_edwards_cup"),
    (r"^((lv=?|specsavers|rothesay|liverpool victoria) )?county championship|^bob willis trophy",
     "county_championship"),
    (r"^(royal london |metro bank )?one-day cup$|^(clydesdale|yorkshire) bank 40|^friends provident trophy",
     "eng_one_day_cup"),
    (r"^rachael heyhoe flint trophy|^ecb women'?s one-day cup|^royal london women'?s one-day cup", "eng_women_one_day"),
    (r"^(marsh )?sheffield shield", "sheffield_shield"),
    (r"^(the )?marsh (one-day )?cup|^one-day cup \(australia\)|^(ryobi|matador bbqs|jlt) one-day cup",
     "aus_one_day_cup"),
    (r"^women'?s national cricket league", "wncl"),
    (r"^plunket shield", "plunket_shield"),
    (r"^(the )?ford trophy", "ford_trophy"),
    (r"^women'?s super smash|^new zealand cricket women'?s twenty20", "super_smash_w"),
    (r"^((georgie pie|burger king|dream11) )?super smash|^hrv (cup|twenty20)", "super_smash"),
    (r"^syed mushtaq ali", "smat"),
    (r"^ranji trophy", "ranji_trophy"),
    (r"^vijay hazare", "vijay_hazare"),
    (r"^(csa|ram slam|miway|momentum)( t20| pro20)( challenge)?|^csa pro20", "csa_t20"),
    (r"^csa (4|four)-day|^sunfoil series", "csa_4day"),
    (r"^(csa|momentum) one-day cup", "csa_one_day"),
    (r"^quaid-e-azam", "quaid_e_azam"),
    (r"^national t20 cup", "pak_national_t20"),
    (r"^major clubs t20", "slc_major_clubs_t20"),
    (r"^major clubs limited over", "slc_major_clubs_odm"),
    (r"^major league tournament", "slc_major_league"),
    (r"^(cg united )?women'?s super50", "wi_women_super50"),
    (r"^(women'?s )?t20 blaze", "wi_women_t20"),
    (r"^cricket ireland inter-provincial twenty20|^inter-provincial twenty20", "ire_ip_t20"),
    (r"^cricket ireland inter-provincial limited over|^inter-provincial (limited over|cup)", "ire_ip_odm"),
    (r"^cricket ireland inter-provincial championship|^inter-provincial championship", "ire_ip_fc"),
    (r"^women'?s t20 challenge", "womens_t20_challenge"),
    (r"^fairbreak", "fairbreak"),
    (r"^nepal premier league", "npl"),
    (r"^european t20 premier league", "etpl"),
    (r"^global t20 canada|^t20 canada", "global_t20_canada"),
]
_CLUB_RE = [(re.compile(p), cid) for p, cid in CLUB_ALIASES]

BILATERAL_TROPHIES = (
    "the ashes", "women's ashes", "border-gavaskar", "chappell-hadlee", "frank worrell", "wisden trophy",
    "pataudi trophy", "basil d'oliveira", "warne-muralitharan", "sobers/tissera", "clive lloyd trophy",
    "freedom trophy", "trans-tasman", "rose bowl", "sir vivian richards", "natwest challenge", "stan nagaiah",
    "saudari cup", "inter-insular", "mcc spirit of cricket", "anthony de mello", "sir frank worrell",
)
# Ordered (pattern, event_id) for international events; first match wins.
INTL_EVENTS = [
    (r"world test championship", "icc_wtc_final"),
    (r"world cup super league", "bilateral"),
    (r"world cricket league|challenge league|world cup league|cricket league", "icc_league"),
    (r"qualif|region|play-off|playoff", "icc_qualifier"),
    (r"intercontinental", "icc_intercontinental"),
    (r"^icc champions trophy|^champions trophy", "icc_ct"),
    (r"world twenty20|t20 world cup|world t20", "icc_t20wc"),
    (r"world cup", "icc_cwc"),
    (r"^icc women's championship", "icc_womens_championship"),
    (r"^(men's |women's |asian cricket council women's )?(t20 |twenty20 )?asia cup", "asia_cup"),
    (r"asian games|commonwealth games|sea games|south asian games|african games|pacific games", "multisport"),
    (r"tri-|\btri |triangular|quadrangular|pentangular", "multi_nation"),
    (r" tour of |\bv\.? |\bvs\.? |^[a-z0-9 .'-]+ in [a-z0-9 .'-]+$", "bilateral"),
]
_INTL_RE = [(re.compile(p), eid) for p, eid in INTL_EVENTS]
_MULTI_RE = re.compile(r"series|cup|trophy|championship|tournament|league|challenge|games|competition|"
                       r"invitational|t20|twenty20")


@dataclass(frozen=True)
class Competition:
    competition_id: str
    tier: str
    fmt: str
    gender: str
    team_type: str
    event_id: str
    event_name: str | None
    assoc_match: bool
    official: bool
    generic: bool

    def __str__(self) -> str:
        return self.competition_id

    def as_dict(self) -> dict:
        return asdict(self)


def normalise_name(name: str | None) -> str:
    s = (name or "").replace("’", "'").replace("‘", "'").lower()
    return re.sub(r"\s+", " ", s).strip()


def gender_suffix(gender: str) -> str:
    return "w" if gender == "female" else "m"


def fmt_family(match_type: str, event_name: str | None = None) -> str:
    if normalise_name(event_name).startswith("the hundred"):
        return "HUNDRED"
    return FMT_FAMILY[match_type]


def is_full_member(team: str, date: str) -> bool:
    since = FULL_MEMBERS.get(team)
    return since is not None and str(date)[:10] >= since


def intl_event_id(event_name: str | None) -> tuple[str, bool]:
    """(event_id, generic) for an international event name."""
    s = normalise_name(event_name)
    if not s:
        return "intl_unnamed", True
    if any(t in s for t in BILATERAL_TROPHIES):
        return "bilateral", False
    for rx, eid in _INTL_RE:
        if rx.search(s):
            return eid, False
    if _MULTI_RE.search(s):
        return "multi_nation", False
    return "intl_other", True


def club_competition_id(event_name: str | None, gender: str) -> str | None:
    s = normalise_name(event_name)
    for rx, cid in _CLUB_RE:
        if rx.search(s):
            if CLUB[cid][3] == gender:
                return cid
            alt = cid + "_w" if gender == "female" else cid.removesuffix("_w")
            return alt if alt in CLUB and CLUB[alt][3] == gender else None
    return None


def competition_for(info: dict) -> Competition:
    """Map a Cricsheet ``info`` dict to its canonical :class:`Competition`."""
    event_name = (info.get("event") or {}).get("name")
    gender, team_type, match_type = info["gender"], info["team_type"], info["match_type"]
    fmt = fmt_family(match_type, event_name)
    date = str(info["dates"][0])
    if team_type == "international":
        assoc = not all(is_full_member(t, date) for t in info["teams"])
        official = match_type in OFFICIAL_TYPES
        event_id, generic = intl_event_id(event_name)
        cid = f"intl_{FMT_FAMILY[match_type].lower()}_{gender_suffix(gender)}"
        tier = "intl_assoc" if assoc or not official else "intl_full"
        return Competition(cid, tier, fmt, gender, team_type, event_id, event_name, assoc, official, generic)
    cid = club_competition_id(event_name, gender)
    if cid is None:
        cid = f"other_{fmt.lower()}_{gender_suffix(gender)}"
        return Competition(cid, "domestic_minor", fmt, gender, team_type, cid, event_name, False, False, True)
    return Competition(cid, CLUB[cid][1], fmt, gender, team_type, cid, event_name, False, False, False)


def season_key(info: dict, competition: Competition | None = None) -> str:
    """``competition_id:season``, e.g. ``ipl:2023`` or ``intl_test_m:2016/17``."""
    comp = competition or competition_for(info)
    return f"{comp.competition_id}:{info['season']}"


def competition_meta(competition_id: str) -> dict:
    """Static facts about a competition id (international, club or generic)."""
    if competition_id in CLUB:
        name, tier, fmt, gender, country = CLUB[competition_id]
        return dict(competition_id=competition_id, name=name, tier=tier, fmt=fmt, gender=gender,
                    team_type="club", country=country)
    m = re.fullmatch(r"(intl|other)_(t20|odi|test|hundred)_([mw])", competition_id)
    if not m:
        raise KeyError(f"unknown competition_id {competition_id!r}")
    gender = "female" if m.group(3) == "w" else "male"
    intl = m.group(1) == "intl"
    return dict(competition_id=competition_id, name=competition_id, tier="intl_full" if intl else "domestic_minor",
                fmt=m.group(2).upper(), gender=gender, team_type="international" if intl else "club", country=None)


def scan_events(zip_path) -> "pd.DataFrame":
    """Stream the Cricsheet zip; one row per distinct (event name, match_type, gender, team_type)."""
    import json
    import zipfile

    import pandas as pd

    rows = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            info = json.loads(z.read(name))["info"]
            comp = competition_for(info)
            rows.append(dict(event_name=comp.event_name, match_type=info["match_type"], gender=info["gender"],
                             team_type=info["team_type"], date=str(info["dates"][0]), **{
                                 k: getattr(comp, k) for k in ("competition_id", "event_id", "tier", "fmt",
                                                               "assoc_match", "official", "generic")}))
    df = pd.DataFrame(rows)
    keys = ["event_name", "match_type", "gender", "team_type", "competition_id", "event_id", "tier", "fmt", "generic"]
    return (df.assign(event_name=df.event_name.fillna("(none)"))
            .groupby(keys).agg(n_matches=("date", "size"), first=("date", "min"), last=("date", "max"),
                               n_assoc=("assoc_match", "sum"))
            .reset_index().sort_values("n_matches", ascending=False, ignore_index=True))
