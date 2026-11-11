"""Build the ball table from cricsheet all_male_json.zip (men's 20-over T20 only)."""
# %% imports
import json
import re
import zipfile
from multiprocessing import Pool

import numpy as np
import pandas as pd

from models.ipl.config import ALL_ZIP, BOWLER_WICKETS, FULL_MEMBERS, PROC, RAW

# %% readme -> competition codes


def readme_codes():
    with zipfile.ZipFile(ALL_ZIP) as z:
        txt = z.read("README.txt").decode()
    codes = {}
    for line in txt.splitlines():
        parts = line.split(" - ")
        if len(parts) >= 6 and re.match(r"\d{4}-\d{2}-\d{2}", parts[0]):
            codes[parts[4].strip()] = (parts[2].strip(), parts[1].strip())
    return codes


# %% venue canonicalisation
VENUE_ALIASES = {
    "feroz shah kotla": "arun jaitley stadium",
    "sardar patel stadium": "narendra modi stadium",
    "sardar patel stadium motera": "narendra modi stadium",
    "punjab cricket association is bindra stadium": "punjab cricket association stadium",
    "is bindra stadium": "punjab cricket association stadium",
    "pca stadium": "punjab cricket association stadium",
    "sheikh zayed stadium": "zayed cricket stadium",
    "zayed cricket stadium": "zayed cricket stadium",
    "sheikh zayed cricket stadium": "zayed cricket stadium",
    "dubai international cricket stadium": "dubai international cricket stadium",
    "subrata roy sahara stadium": "maharashtra cricket association stadium",
    "maharashtra cricket association stadium": "maharashtra cricket association stadium",
    "dr dy patil sports academy": "dy patil stadium",
    "dy patil stadium": "dy patil stadium",
    "rajiv gandhi intl cricket stadium": "rajiv gandhi international stadium",
    "rajiv gandhi international stadium uppal": "rajiv gandhi international stadium",
    "ma chidambaram stadium chepauk": "ma chidambaram stadium",
    "m chinnaswamy stadium": "m chinnaswamy stadium",
    "mchinnaswamy stadium": "m chinnaswamy stadium",
    "bharat ratna shri atal bihari vajpayee ekana cricket stadium": "ekana cricket stadium",
    "ekana cricket stadium": "ekana cricket stadium",
    "dr ys rajasekhara reddy acavdca cricket stadium": "aca-vdca stadium",
    "acavdca stadium": "aca-vdca stadium",
    "andhra cricket associationvisakhapatnam district cricket association stadium": "aca-vdca stadium",
    "maharaja yadavindra singh international cricket stadium": "mullanpur stadium",
    "maharaja yadavindra singh international cricket stadium mullanpur": "mullanpur stadium",
    "himachal pradesh cricket association stadium": "hpca stadium",
    "barsapara cricket stadium": "barsapara stadium",
    "assam cricket association stadium": "barsapara stadium",
    "shaheed veer narayan singh international stadium": "sns stadium raipur",
    "vidarbha cricket association stadium": "vca stadium jamtha",
    "holkar cricket stadium": "holkar stadium",
    "the rose bowl": "rose bowl", "the ageas bowl": "rose bowl", "ageas bowl": "rose bowl",
    "utilita bowl": "rose bowl",
    "sophia gardens": "sophia gardens", "swalec stadium": "sophia gardens",
    "the oval": "kennington oval", "kia oval": "kennington oval",
    "kennington oval": "kennington oval",
    "edgbaston": "edgbaston", "headingley": "headingley",
    "old trafford": "old trafford", "emirates old trafford": "old trafford",
    "lords": "lords", "lord's": "lords",
    "trent bridge": "trent bridge", "riverside ground": "riverside ground",
    "emirates riverside": "riverside ground",
    "kensington oval bridgetown": "kensington oval",
    "brian lara stadium": "brian lara cricket academy",
    "gaddafi stadium": "gaddafi stadium",
    "sharjah cricket stadium": "sharjah cricket stadium",
    "sharjah cricket association stadium": "sharjah cricket stadium",
    "wanderers stadium": "the wanderers stadium", "new wanderers stadium": "the wanderers stadium",
    "the wanderers stadium": "the wanderers stadium",
    "supersport park": "supersport park", "centurion park": "supersport park",
    "kingsmead": "kingsmead", "newlands": "newlands",
    "st georges park": "st georges park",
    "boland park": "boland park",
    "melbourne cricket ground": "melbourne cricket ground",
    "sydney cricket ground": "sydney cricket ground",
    "adelaide oval": "adelaide oval", "the gabba": "brisbane cricket ground",
    "brisbane cricket ground": "brisbane cricket ground",
    "brisbane cricket ground woolloongabba": "brisbane cricket ground",
    "perth stadium": "perth stadium", "optus stadium": "perth stadium",
    "western australia cricket association ground": "waca ground",
    "w a c a ground": "waca ground", "waca ground": "waca ground",
    "bellerive oval": "bellerive oval", "blundstone arena": "bellerive oval",
    "docklands stadium": "docklands stadium", "marvel stadium": "docklands stadium",
    "carrara oval": "carrara oval", "metricon stadium": "carrara oval",
    "sydney showground stadium": "sydney showground stadium",
    "spotless stadium": "sydney showground stadium",
    "manuka oval": "manuka oval",
    "shere bangla national stadium": "shere bangla national stadium",
    "zahur ahmed chowdhury stadium": "zahur ahmed chowdhury stadium",
    "r premadasa stadium": "r premadasa stadium",
    "rangiri dambulla international stadium": "rangiri dambulla international stadium",
    "grand prairie stadium": "grand prairie stadium",
    "providence stadium": "providence stadium",
    "warner park": "warner park", "queens park oval": "queens park oval",
    "daren sammy national cricket stadium": "daren sammy stadium",
    "beausejour stadium": "daren sammy stadium",
    "sabina park": "sabina park",
    "sir vivian richards stadium": "sir vivian richards stadium",
}


def _norm(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"[.'`]", "", s)
    s = re.sub(r"[^a-z0-9, -]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


GENERIC_HEADS = {"county ground", "the county ground", "national stadium", "gymkhana club ground",
                 "queens park", "nigeria cricket federation oval", "icc academy ground"}
CITY_ALIASES = {"brighton": "hove", "bengaluru": "bangalore", "chattogram": "chittagong",
                "gqeberha": "port elizabeth"}


def canon_venue(venue, city):
    v = _norm(venue or "")
    head0 = v.split(",")[0].strip()
    if head0 in GENERIC_HEADS:
        c = _norm(city or (v.split(",")[1] if "," in v else ""))
        return head0.replace("the ", "") + " " + CITY_ALIASES.get(c, c)
    head = v.split(",")[0].strip()
    head = head.replace("-", "")
    head = re.sub(r"\s+", " ", head)
    if head in VENUE_ALIASES:
        return VENUE_ALIASES[head]
    full = re.sub(r"[,-]", "", v)
    full = re.sub(r"\s+", " ", full)
    if full in VENUE_ALIASES:
        return VENUE_ALIASES[full]
    # common trailing location words
    head2 = re.sub(r"\b(stadium|ground|oval|park)\b.*$", lambda m: m.group(1), head)
    return VENUE_ALIASES.get(head2, head2)


# %% per-match parse


def parse_match(args):
    name, code_team = args
    with zipfile.ZipFile(ALL_ZIP) as z:
        d = json.loads(z.read(name))
    info = d["info"]
    if info.get("gender") != "male" or info.get("match_type") not in ("T20", "IT20"):
        return None
    if info.get("overs", 20) != 20 or info.get("balls_per_over", 6) != 6:
        return None
    mid = name.replace(".json", "")
    code, team_type = code_team if code_team else ("T20", info.get("team_type"))
    teams = info["teams"]
    if info.get("team_type") == "international":
        comp = "T20I" if all(t in FULL_MEMBERS for t in teams) else "T20I-A"
    else:
        comp = code if code not in ("T20", "IT20") else "OTHER"
    reg = info.get("registry", {}).get("people", {})
    pid = lambda n: reg.get(n, "nm:" + n)
    out = info.get("outcome", {})
    winner = out.get("winner")
    if winner is None and out.get("eliminator"):
        winner = out.get("eliminator")
    result = out.get("result", "win" if winner else "unknown")
    method = out.get("method", "")
    toss = info.get("toss", {})
    date = info["dates"][0]
    season = str(info.get("season", date[:4]))
    venue_raw = info.get("venue", "")
    city = info.get("city", "")
    rows = []
    inns = d.get("innings", [])
    first_total = None
    reduced = False
    impact_rows = []
    match_players = {t: [pid(p) for p in ps] for t, ps in info.get("players", {}).items()}
    inn_no = 0
    for ii, inn in enumerate(inns):
        so = bool(inn.get("super_over"))
        if not so:
            inn_no += 1
        team = inn["team"]
        bowl_team = teams[1] if teams[0] == team else teams[0]
        tgt = inn.get("target")
        target_runs = target_overs = None
        if not so and inn_no == 2:
            if tgt:
                target_runs = tgt.get("runs")
                target_overs = tgt.get("overs", 20)
            elif first_total is not None:
                target_runs, target_overs = first_total + 1, 20
            if target_overs is not None and float(target_overs) < 20:
                reduced = True
        score = wk = legal = 0
        bf = {}
        brun = {}
        order = {}
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
                wide = ex.get("wides", 0)
                nb = ex.get("noballs", 0)
                byes = ex.get("byes", 0) + ex.get("legbyes", 0)
                pen = ex.get("penalty", 0)
                wkts = dl.get("wickets", [])
                kinds = [w["kind"] for w in wkts]
                is_legal = (wide == 0 and nb == 0)
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
                wkind = kinds[0] if kinds else ""
                wout = wkts[0]["player_out"] if wkts else ""
                fielder = ""
                if wkts and wkts[0].get("fielders"):
                    fielder = wkts[0]["fielders"][0].get("name", "")
                repl = dl.get("replacements", {}).get("match", [])
                for rp in repl:
                    if rp.get("reason") == "impact_player":
                        impact_rows.append((mid, rp.get("team"), pid(rp["in"]), pid(rp["out"]), inn_no, o))
                rows.append((
                    inn_no if not so else 3, so, team, bowl_team, o, lb_in_over, legal,
                    pid(bat), pid(ns), pid(bowl), bat, bowl,
                    cls, rb, r["extras"], r["total"], wide, nb, byes, pen,
                    wkind, pid(wout) if wout else "", pid(fielder) if fielder else "",
                    wk, score, bf.get(bat, 0), brun.get(bat, 0), order[bat], order[ns],
                    target_runs, len(wkts), "non_boundary" in r, bf.get(ns, 0),
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
        if not so and inn_no == 1:
            first_total = score
    if not rows:
        return None
    cols = ["innings", "super_over", "bat_team", "bowl_team", "over", "ball_in_over", "legal_before",
            "batter", "non_striker", "bowler", "batter_name", "bowler_name",
            "cls", "runs_bat", "runs_extras", "runs_total", "wides", "noballs", "byes", "penalty",
            "wicket_kind", "player_out", "fielder", "wkts_before", "score_before", "bf_before",
            "brun_before", "bat_pos", "ns_pos", "target", "n_wkts", "non_boundary", "ns_bf_before"]
    df = pd.DataFrame(rows, columns=cols)
    df["match_id"] = mid
    df["comp"] = comp
    df["event"] = info.get("event", {}).get("name", "")
    df["season"] = season
    df["date"] = date
    df["venue_raw"] = venue_raw
    df["city"] = city
    df["toss_winner"] = toss.get("winner", "")
    df["toss_decision"] = toss.get("decision", "")
    df["winner"] = winner or ""
    df["result"] = result
    df["method"] = method
    df["reduced"] = reduced or bool(method)
    meta = dict(match_id=mid, comp=comp, event=info.get("event", {}).get("name", ""), season=season,
                date=date, venue_raw=venue_raw, city=city, team1=teams[0], team2=teams[1],
                toss_winner=toss.get("winner", ""), toss_decision=toss.get("decision", ""),
                winner=winner or "", result=result, method=method, reduced=reduced or bool(method),
                players=json.dumps(match_players), team_type=info.get("team_type"))
    return df, meta, impact_rows


# %% run
def main():
    codes = readme_codes()
    with zipfile.ZipFile(ALL_ZIP) as z:
        names = [n for n in z.namelist() if n.endswith(".json")]
    args = [(n, codes.get(n.replace(".json", ""))) for n in names]
    with Pool(4) as pool:
        res = [r for r in pool.imap_unordered(parse_match, args, chunksize=50) if r is not None]
    balls = pd.concat([r[0] for r in res], ignore_index=True)
    matches = pd.DataFrame([r[1] for r in res])
    impact = pd.DataFrame([x for r in res for x in r[2]],
                          columns=["match_id", "team", "player_in", "player_out", "innings", "over"])
    balls["venue"] = [canon_venue(v, c) for v, c in zip(balls["venue_raw"], balls["city"])]
    matches["venue"] = [canon_venue(v, c) for v, c in zip(matches["venue_raw"], matches["city"])]
    # city for each canonical venue (modal)
    balls["date"] = pd.to_datetime(balls["date"])
    matches["date"] = pd.to_datetime(matches["date"])
    for c in ["bat_team", "bowl_team", "comp", "event", "season", "venue_raw", "city", "venue",
              "toss_winner", "toss_decision", "winner", "result", "method", "cls", "wicket_kind"]:
        balls[c] = balls[c].astype("category")
    balls["target"] = balls["target"].astype("float32")
    balls = balls.sort_values(["date", "match_id", "innings", "over", "legal_before"], kind="stable").reset_index(drop=True)
    balls.to_parquet(PROC / "balls.parquet", index=False)
    matches.to_parquet(PROC / "matches.parquet", index=False)
    impact.to_parquet(PROC / "impact_subs.parquet", index=False)
    print(f"balls={len(balls):,} matches={len(matches):,} impact_subs={len(impact):,}")


if __name__ == "__main__":
    main()
