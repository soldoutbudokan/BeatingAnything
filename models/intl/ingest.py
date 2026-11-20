"""Ball table for one format from cricsheet (tests_male_json.zip / odis_male_json.zip).

One row per delivery with the match state before it. Tests carry the extra state a five-day match needs:
innings 1-4, overs bowled in the match so far, the batting side's lead, and the fourth-innings target.
"""
# %% imports
import json
import sys
import zipfile
from multiprocessing import Pool

import numpy as np
import pandas as pd

from models.intl.config import BOWLER_WICKETS, FORMATS
from models.ipl.ingest import canon_venue

# %% host country of each ground
CITY_COUNTRY = {
    "England": ["London", "Birmingham", "Nottingham", "Manchester", "Leeds", "Southampton", "Cardiff", "Chester-le-Street",
                "Bristol", "Chelmsford", "Taunton", "Canterbury"],
    "Australia": ["Brisbane", "Perth", "Hobart", "Sydney", "Melbourne", "Adelaide", "Canberra", "Darwin", "Cairns", "Mackay",
                  "Townsville"],
    "India": ["Ahmedabad", "Mumbai", "Chandigarh", "Kolkata", "Chennai", "Delhi", "Nagpur", "Hyderabad", "Pune",
              "Visakhapatnam", "Bangalore", "Bengaluru", "Kanpur", "Rajkot", "Indore", "Ranchi", "Jaipur", "Dharamsala",
              "Dharmasala", "Cuttack", "Guwahati", "Vadodara", "Lucknow", "Kochi", "Thiruvananthapuram", "Gwalior", "Raipur",
              "Faridabad", "Margao", "New Chandigarh", "Jamshedpur", "Mohali"],
    "Sri Lanka": ["Colombo", "Hambantota", "Galle", "Kandy", "Dambulla", "Pallekele"],
    "Bangladesh": ["Mirpur", "Dhaka", "Chattogram", "Chittagong", "Sylhet", "Fatullah", "Bogra", "Khulna"],
    "Zimbabwe": ["Bulawayo", "Harare"],
    "South Africa": ["Centurion", "Johannesburg", "Cape Town", "Durban", "Port Elizabeth", "Gqeberha", "Bloemfontein",
                     "Potchefstroom", "Benoni", "Paarl", "East London", "Kimberley", "Pietermaritzburg"],
    "United Arab Emirates": ["Dubai", "Abu Dhabi", "Sharjah"],
    "New Zealand": ["Wellington", "Hamilton", "Christchurch", "Auckland", "Napier", "Mount Maunganui", "Dunedin", "Nelson",
                    "Whangarei", "Queenstown", "Lincoln"],
    "Namibia": ["Windhoek"],
    "Nepal": ["Kirtipur", "Kathmandu"],
    "Pakistan": ["Lahore", "Karachi", "Rawalpindi", "Multan", "Faisalabad", "Peshawar", "Sind"],
    "Ireland": ["Dublin", "Belfast", "Bready"],
    "Oman": ["Al Amarat"],
    "West Indies": ["Jamaica", "Trinidad", "Antigua", "Barbados", "St Lucia", "Guyana", "Bridgetown", "St Kitts",
                    "North Sound", "Grenada", "Kingston", "St Vincent", "Dominica", "Port of Spain", "Providence",
                    "St George's", "Gros Islet", "Tarouba", "St John's", "Basseterre", "Kingstown", "Roseau"],
    "Canada": ["King City", "Toronto"],
    "Scotland": ["Dundee", "Aberdeen", "Edinburgh", "Glasgow", "Ayr"],
    "Kenya": ["Nairobi"],
    "Netherlands": ["Amstelveen", "Utrecht", "Rotterdam", "The Hague", "Deventer"],
    "United States of America": ["Pearland", "Dallas", "Lauderhill"],
    "Malaysia": ["Kuala Lumpur", "Bangi"],
    "Papua New Guinea": ["Port Moresby"],
    "Hong Kong": ["Hong Kong"],
}
COUNTRY_OF_CITY = {c: k for k, v in CITY_COUNTRY.items() for c in v}
VENUE_COUNTRY = {
    "adelaide oval": "Australia", "melbourne cricket ground": "Australia", "sydney cricket ground": "Australia",
    "perth stadium": "Australia", "bir shrestha shahid ruhul amin stadium": "Bangladesh",
    "sylhet international cricket stadium": "Bangladesh", "bulawayo athletic club": "Zimbabwe",
    "harare sports club": "Zimbabwe", "dubai international cricket stadium": "United Arab Emirates",
    "sharjah cricket stadium": "United Arab Emirates", "galle international stadium": "Sri Lanka",
    "pallekele international cricket stadium": "Sri Lanka", "rangiri dambulla international stadium": "Sri Lanka",
    "mombasa sports club ground": "Kenya", "multan cricket stadium": "Pakistan", "rawalpindi cricket stadium": "Pakistan",
    "sheikhupura stadium": "Pakistan", "queenstown events centre": "New Zealand",
}


def country_of(venue, city):
    return VENUE_COUNTRY.get(venue) or COUNTRY_OF_CITY.get(city or "") or ""


# %% per-match parse
_ZIP = None
_FMT = None


def _init(key):
    global _ZIP, _FMT
    _FMT = FORMATS[key]
    _ZIP = zipfile.ZipFile(_FMT.zip)


def _pp_type(pps, o, b):
    """Powerplay in force for ball o.b (ODIs): 1 mandatory, 2 batting, 3 fielding, 0 none."""
    x = o + (b + 1) / 10.0
    for p in pps:
        if p["from"] - 1e-9 <= x <= p["to"] + 1e-9:
            return {"mandatory": 1, "batting": 2, "fielding": 3}.get(p.get("type"), 0)
    return 0


def parse_match(name):
    fmt = _FMT
    d = json.loads(_ZIP.read(name))
    info = d["info"]
    if info.get("gender") != "male" or info.get("match_type") != fmt.match_type or info.get("balls_per_over", 6) != 6:
        return None
    if fmt.max_overs and info.get("overs", fmt.max_overs) != fmt.max_overs:
        return None
    mid = name.replace(".json", "")
    teams = info["teams"]
    reg = info.get("registry", {}).get("people", {})
    pid = lambda n: reg.get(n, "nm:" + n)
    out = info.get("outcome", {})
    winner = out.get("winner") or ""
    result = out.get("result", "win" if winner else "unknown")
    method = out.get("method", "")
    toss = info.get("toss", {})
    dates = info["dates"]
    max_legal = fmt.max_overs * 6
    rows, inn_meta = [], []
    agg = {t: 0 for t in teams}       # runs so far in the match per team
    m_legal = 0                       # legal balls bowled in the match
    reduced = False
    first_total, first_legal, first_wk = None, max_legal, 10
    inn_no = 0
    for inn in d.get("innings", []):
        if inn.get("super_over") or inn.get("forfeited"):
            continue
        inn_no += 1
        if inn_no > fmt.n_inn:
            break
        team = inn["team"]
        bowl_team = teams[1] if teams[0] == team else teams[0]
        pps = inn.get("powerplays", [])
        target = np.nan
        if fmt.key == "odi" and inn_no == 2:
            tg = inn.get("target")
            if tg:
                target = tg.get("runs", np.nan)
                if float(tg.get("overs", fmt.max_overs)) < fmt.max_overs:
                    reduced = True
            elif first_total is not None:
                target = first_total + 1
        if fmt.key == "test" and inn_no == 4:
            target = agg[bowl_team] - agg[team] + 1
        lead0 = agg[team] - agg[bowl_team]   # batting side's lead before this innings
        score = wk = legal = 0
        bf, brun, order, bowl_legal = {}, {}, {}, {}
        for ov in inn.get("overs", []):
            o = ov["over"]
            lb_in_over = 0
            for dl in ov["deliveries"]:
                bat, ns, bowl = dl["batter"], dl["non_striker"], dl["bowler"]
                for p in (bat, ns):
                    if p not in order:
                        order[p] = len(order) + 1
                ex = dl.get("extras", {})
                r = dl["runs"]
                wide, nb = ex.get("wides", 0), ex.get("noballs", 0)
                byes = ex.get("byes", 0) + ex.get("legbyes", 0)
                wkts = dl.get("wickets", [])
                kinds = [w["kind"] for w in wkts]
                is_legal = wide == 0 and nb == 0
                rb = r["batter"]
                if wide:
                    cls = "wide"
                elif nb:
                    cls = "noball"
                elif any(k in BOWLER_WICKETS for k in kinds):
                    cls = "wicket"
                elif "run out" in kinds:
                    cls = "runout"
                elif byes:
                    cls = "byes"
                else:
                    cls = {0: "r0", 1: "r1", 2: "r2", 3: "r3", 4: "r4", 5: "r4", 6: "r6"}.get(rb, "r6" if rb > 6 else "r0")
                wout = wkts[0]["player_out"] if wkts else ""
                rows.append((
                    inn_no, team, bowl_team, o, lb_in_over, legal, m_legal, pid(bat), pid(ns), pid(bowl), cls, rb,
                    r["extras"], r["total"], wide, nb, byes, kinds[0] if kinds else "", pid(wout) if wout else "",
                    wk, score, bf.get(bat, 0), brun.get(bat, 0), order[bat], order[ns], bf.get(ns, 0), target,
                    lead0 + score, bowl_legal.get(bowl, 0), _pp_type(pps, o, lb_in_over) if pps else 0,
                ))
                score += r["total"]
                if wide == 0:
                    bf[bat] = bf.get(bat, 0) + 1
                brun[bat] = brun.get(bat, 0) + rb
                for k in kinds:
                    if k not in ("retired hurt", "retired not out"):
                        wk += 1
                if is_legal:
                    legal += 1
                    lb_in_over += 1
                    m_legal += 1
                    bowl_legal[bowl] = bowl_legal.get(bowl, 0) + 1
        agg[team] += score
        follow_on = bool(inn_no == 3 and inn_meta and inn_meta[-1]["team"] == team)
        inn_meta.append(dict(inn=inn_no, team=team, runs=score, wkts=wk, legal=legal, declared=bool(inn.get("declared")),
                             follow_on=follow_on, absent=len(inn.get("absent_hurt", []))))
        if inn_no == 1:
            first_total, first_legal, first_wk = score, legal, wk
    if not rows:
        return None
    if fmt.key == "odi":
        # shortened before or during the first innings (cricsheet does not always record it), or abandoned
        if result in ("win", "tie") and inn_no >= 2 and first_legal <= max_legal - 6 and first_wk < 9:
            reduced = True
        reduced = reduced or bool(method) or result not in ("win", "tie")
    cols = ["inn", "bat_team", "bowl_team", "over", "ball_in_over", "legal_before", "m_legal_before", "batter",
            "non_striker", "bowler", "cls", "runs_bat", "runs_extras", "runs_total", "wides", "noballs", "byes",
            "wicket_kind", "player_out", "wkts_before", "score_before", "bf_before", "brun_before", "bat_pos", "ns_pos",
            "ns_bf_before", "target", "lead_before", "bowl_legal_before", "pp_type"]
    df = pd.DataFrame(rows, columns=cols)
    df["match_id"] = mid
    venue_raw, city = info.get("venue", ""), info.get("city", "") or ""
    venue = canon_venue(venue_raw, city)
    meta = dict(match_id=mid, date=dates[0], last_date=dates[-1], n_days=len(dates), season=str(info.get("season", dates[0][:4])),
                event=info.get("event", {}).get("name", ""), venue_raw=venue_raw, city=city, venue=venue,
                country=country_of(venue, city), team1=teams[0], team2=teams[1], toss_winner=toss.get("winner", ""),
                toss_decision=toss.get("decision", ""), winner=winner, result=result, method=method, reduced=bool(reduced),
                m_legal=m_legal, innings=json.dumps(inn_meta),
                players=json.dumps({t: [pid(p) for p in ps] for t, ps in info.get("players", {}).items()}))
    return df, meta


# %% run
def main(key):
    fmt = FORMATS[key]
    with zipfile.ZipFile(fmt.zip) as z:
        names = [n for n in z.namelist() if n.endswith(".json")]
    with Pool(4, initializer=_init, initargs=(key,)) as pool:
        res = [r for r in pool.imap_unordered(parse_match, names, chunksize=20) if r is not None]
    matches = pd.DataFrame([r[1] for r in res])
    matches["date"] = pd.to_datetime(matches["date"])
    matches["last_date"] = pd.to_datetime(matches["last_date"])
    # grounds without a mapped city: the side that plays there most is the host
    need = matches["country"] == ""
    if need.any():
        long = pd.concat([matches[["venue", "team1"]].rename(columns={"team1": "t"}),
                          matches[["venue", "team2"]].rename(columns={"team2": "t"})])
        modal = long.groupby("venue")["t"].agg(lambda s: s.value_counts().index[0])
        matches.loc[need, "country"] = matches.loc[need, "venue"].map(modal)
    balls = pd.concat([r[0] for r in res], ignore_index=True)
    mm = matches.set_index("match_id")
    for c in ("date", "season", "venue", "country", "winner", "result", "reduced", "toss_winner", "toss_decision"):
        balls[c] = balls["match_id"].map(mm[c])
    for c in ("bat_team", "bowl_team", "cls", "wicket_kind", "season", "venue", "country", "winner", "result",
              "toss_winner", "toss_decision"):
        balls[c] = balls[c].astype("category")
    balls["target"] = balls["target"].astype("float32")
    balls = balls.sort_values(["date", "match_id", "inn", "over", "legal_before"], kind="stable").reset_index(drop=True)
    balls.to_parquet(fmt.proc / "balls.parquet", index=False)
    matches.sort_values(["date", "match_id"]).reset_index(drop=True).to_parquet(fmt.proc / "matches.parquet", index=False)
    print(f"{key}: balls={len(balls):,} matches={len(matches):,} reduced={int(matches['reduced'].sum())} "
          f"unmapped country={int(need.sum())} last={matches['date'].max().date()}")


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        main(k)
