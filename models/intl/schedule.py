"""Upcoming men's Tests and ODIs for the Schedule sheet, with a pre-match projection for each.

Fixtures come from ESPN's public cricket scoreboard API. Each is mapped to the model's teams and grounds, given
a lineup (the announced XI once ESPN has it, otherwise the side's most recent XI in comparable conditions)
and simulated with the same engine the browser runs. Needs only the published exports (teams.json,
venues.json, ids.json, sim_params.json), so it can run on a schedule without the model data.

Usage: python -m models.intl.schedule [odi] [test] [--days 300] [--no-sim]
"""
# %% imports
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from beating.power import get_json
from models.intl.config import FORMATS, REGION
from models.intl.team import integer_plan, share_plan
from models.ipl.ingest import canon_venue

API = "https://site.api.espn.com/apis/site/v2/sports/cricket"
NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RAW_KEYS = ("id", "league", "fmt", "date", "start_utc", "end_utc", "series", "desc", "status", "status_text", "teams",
            "venue_name", "city", "country_raw", "seen_utc")
CLASS = {"1": "test", "2": "odi"}                 # ESPN internationalClassId -> format (men's internationals)
TEAM_ALIASES = {"USA": "United States of America", "U.S.A.": "United States of America",
                "United States": "United States of America", "UAE": "United Arab Emirates", "U.A.E.": "United Arab Emirates",
                "PNG": "Papua New Guinea", "P.N.G.": "Papua New Guinea", "Hong Kong, China": "Hong Kong"}
COUNTRY_ALIASES = {"Wales": "England", "UAE": "United Arab Emirates", "USA": "United States of America",
                   "United States": "United States of America", "U.S.A.": "United States of America"}
CARIBBEAN = {"Jamaica", "Barbados", "Trinidad and Tobago", "Trinidad & Tobago", "Guyana", "Antigua and Barbuda", "Antigua",
             "Saint Lucia", "St Lucia", "St. Lucia", "Grenada", "Dominica", "Saint Kitts and Nevis", "St Kitts and Nevis",
             "St. Kitts and Nevis", "Saint Vincent and the Grenadines", "St Vincent and the Grenadines", "St Vincent"}
SIMS = {"test": 6000, "odi": 10000}
BAT_SLOT_ROLE = ["open", "open", "top", "top", "middle", "middle", "middle", "lower", "lower", "tail", "tail"]


def get(url, tries=3):
    """One HTTP client for every ESPN call in the repo (beating.power.get_json: gzip, retries on 429 / 5xx)."""
    try:
        out = get_json(url, tries=tries)
    except Exception as e:  # noqa: BLE001 (reported by the caller, which skips that date or match)
        raise RuntimeError(f"fetch failed: {url}: {e}") from e
    if out is None:
        raise RuntimeError(f"fetch failed: {url}: 404")
    return out


def norm_country(c):
    c = (c or "").strip()
    if c in CARIBBEAN:
        return "West Indies"
    return COUNTRY_ALIASES.get(c, c)


def norm_team(t):
    t = (t or "").strip()
    return TEAM_ALIASES.get(t, t)


# %% fetch


def discover(today, days):
    """Series (ESPN leagues) with men's Tests or ODIs between today and today + days."""
    leagues = {}
    for off in range(0, days + 1, 6):
        d = (today + timedelta(days=off)).strftime("%Y%m%d")
        try:
            panel = get(f"{API}/scorepanel?dates={d}")
        except RuntimeError as e:
            print("warn:", e)
            continue
        for s in panel.get("scores", []):
            lg = (s.get("leagues") or [{}])[0]
            for ev in s.get("events", []):
                cl = ((ev.get("competitions") or [{}])[0].get("class") or {})
                if cl.get("internationalClassId") in CLASS and lg.get("id"):
                    leagues[lg["id"]] = {"id": lg["id"], "name": lg.get("name"), "calendar": [c[:10] for c in lg.get("calendar", [])]}
        time.sleep(0.15)
    return leagues


def fixtures_of(lg, today, days):
    """Walk a series calendar, one request per match (a Test's later days are skipped)."""
    out, skip_until = {}, None
    lo, hi = today - timedelta(days=5), today + timedelta(days=days)
    for ds in lg["calendar"]:
        day = datetime.strptime(ds, "%Y-%m-%d").date()
        if day < lo or day > hi or (skip_until and day <= skip_until):
            continue
        sb = None
        for attempt in range(2):   # ESPN answers 502 in bursts: one slow retry before giving the date up
            try:
                sb = get(f"{API}/{lg['id']}/scoreboard?dates={ds.replace('-', '')}")
                break
            except RuntimeError as e:
                print("warn:", e)
                time.sleep(8)
        if sb is None:
            continue
        evs = sb.get("events", [])
        for ev in evs:
            comp = (ev.get("competitions") or [{}])[0]
            cl = comp.get("class") or {}
            fmt = CLASS.get(cl.get("internationalClassId"))
            if not fmt or ev["id"] in out:
                continue
            teams = sorted(comp.get("competitors", []), key=lambda c: c.get("order", 0))
            if len(teams) != 2:
                continue
            ven = comp.get("venue") or {}
            st = (comp.get("status") or {}).get("type") or {}
            out[ev["id"]] = {
                "id": ev["id"], "league": lg["id"], "fmt": fmt, "date": ds, "start_utc": ev.get("date"), "end_utc": ev.get("endDate"),
                "series": lg.get("name"), "desc": comp.get("description") or "", "status": st.get("state", "pre"),
                "status_text": (comp.get("status") or {}).get("summary") or st.get("detail") or "",
                "teams": [norm_team(t["team"].get("displayName")) for t in teams],
                "venue_name": ven.get("fullName") or "", "city": (ven.get("address") or {}).get("city") or "",
                "country_raw": (ven.get("address") or {}).get("country") or "", "seen_utc": NOW(),
            }
        if len(evs) == 1 and (((evs[0].get("competitions") or [{}])[0].get("class") or {}).get("internationalClassId") == "1"):
            skip_until = day + timedelta(days=4)
        time.sleep(0.15)
    return out


def announced(fx):
    """Playing XIs (cricinfo ids, scorecard order) and the toss from the match summary; {} before they exist."""
    try:
        s = get(f"{API}/{fx['league']}/summary?event={fx['id']}", tries=2)
    except RuntimeError:
        return {}
    out = {"xi": {}}
    for r in s.get("rosters", []):
        name = norm_team((r.get("team") or {}).get("displayName"))
        xi = [{"cricinfo": str((p.get("athlete") or {}).get("id")), "name": (p.get("athlete") or {}).get("displayName"),
               "pos": ((p.get("position") or {}).get("name") or "")} for p in r.get("roster", []) if p.get("starter", True)]
        if len(xi) >= 11:
            out["xi"][name] = xi[:11]
    for n in s.get("notes", []):
        if n.get("type") == "toss" and n.get("text"):
            m = re.match(r"\s*(.+?)\s*,\s*elected to (bat|field)", n["text"])
            if m:
                out["toss"] = {"winner": norm_team(m.group(1)), "decision": m.group(2)}
    return out


# %% map to the model


def venue_index(venues):
    by_id = {v["venue"]: v for v in venues}
    by_city = {}
    for v in sorted(venues, key=lambda v: -v["matches"]):
        if v.get("city"):
            by_city.setdefault((v["city"].lower(), v["country"]), v["venue"])
    return by_id, by_city


def map_venue(fx, by_id, by_city, country):
    vid = canon_venue(fx["venue_name"], fx["city"])
    if vid in by_id:
        return vid
    head = canon_venue(fx["venue_name"].split(",")[0], fx["city"])
    if head in by_id:
        return head
    return by_city.get((fx["city"].lower(), country))


def plan_from_usage(fmt, team, xi):
    """Bowling plan for an XI from the squad's usage table in teams.json."""
    use = {s["id"]: s["usage"] for s in team["squad"] if s.get("usage")}
    q = {p: use[p] for p in xi if p in use and sum(use[p]) > 0}
    if fmt.key == "odi":
        q = {p: u for p, u in q.items() if sum(u) >= 0.3}
        top = sorted(q, key=lambda p: -sum(q[p]))[:8]
        return integer_plan({p: q[p] for p in top}) if top else []
    return share_plan(q) if q else []


def lineup(fmt, team, country, ann, ids):
    """Announced XI when the feed has one for this side, else the side's XI for these conditions."""
    reg = REGION.get(country, "other")
    base = team["by_region"].get(reg) or team["default"]
    if ann:
        order, names, roles = [], {}, {}
        for k, p in enumerate(ann):
            pid = ids.get(p["cricinfo"])
            if pid is None:   # no rating: the engine gives him the role prior plus the side's team term
                pid = "espn:" + p["cricinfo"]
                bowl = "pace_front" if "bowl" in p["pos"].lower() else ("pace_reg" if "allround" in p["pos"].lower() else "pace_part")
                roles[pid] = {"bat": BAT_SLOT_ROLE[min(k, 10)], "bowl": bowl}
            names[pid] = p["name"]
            order.append(pid)
        plan = plan_from_usage(fmt, team, order)
        have = {p["id"] for p in plan}
        extra = [p for p in order if p in roles and roles[p]["bowl"] != "pace_part" and p not in have]
        if fmt.key == "test":
            plan += [{"id": p, "nb": 20.0, "mid": 20.0, "old": 20.0} for p in extra]
        elif extra or len(plan) < 5:   # rebuild whole-over quotas with a usual 8 overs for each unrated bowler
            use = {s["id"]: s["usage"] for s in team["squad"] if s.get("usage")}
            q = {p: use[p] for p in order if p in use and sum(use[p]) >= 0.3}
            q.update({p: [2.0, 4.5, 1.5] for p in extra})
            plan = integer_plan(q) if q else []
        if len(plan) >= (5 if fmt.key == "odi" else 3):
            return {"order": order, "plan": plan, "roles": roles, "names": names, "source": "announced XI"}
    return {"order": base["order"], "plan": base["plan"], "roles": {}, "names": {},
            "source": f"most recent XI in comparable conditions ({base['date']}, {base['country']})"}


def build(key, raw_fixtures, sim=True):
    fmt = FORMATS[key]
    ex = fmt.export
    teams = {t["name"]: t for t in json.loads((ex / "teams.json").read_text())["teams"]}
    venues = json.loads((ex / "venues.json").read_text())["venues"]
    ids = json.loads((ex / "ids.json").read_text())["cricinfo"]
    sp = json.loads((ex / "sim_params.json").read_text())
    by_id, by_city = venue_index(venues)
    now = datetime.now(timezone.utc)
    rows, jobs = [], []
    for fx in sorted((f for f in raw_fixtures if f["fmt"] == key), key=lambda f: (f["start_utc"] or f["date"], f["id"])):
        if fx["status"] == "post":
            continue
        a, b = fx["teams"]
        country = norm_country(fx["country_raw"])
        vid = map_venue(fx, by_id, by_city, country)
        if vid and not country:
            country = by_id[vid]["country"]
        if b == country:   # home side first
            a, b = b, a
        r = {k: fx[k] for k in ("id", "fmt", "date", "start_utc", "end_utc", "series", "desc", "status", "status_text",
                                "venue_name", "city")}
        r["raw"] = {k: fx.get(k) for k in RAW_KEYS}   # lets the next run keep this fixture if the feed drops out
        r.update({"A": a, "B": b, "country": country, "venue": vid if vid in sp["venues"] else None,
                  "home": "A" if a == country else ("B" if b == country else None),
                  "env_known": country in sp["env"], "url": f"https://www.espncricinfo.com/ci/engine/match/{fx['id']}.html"})
        missing = [t for t in (a, b) if t not in teams]
        if missing or "TBC" in (a, b) or "TBA" in (a, b):
            r.update({"modelled": False, "reason": ("Sides to be confirmed" if not missing or "TBC" in missing or "TBA" in missing
                                                    else f"No ball-by-ball data for {' or '.join(missing)}")})
            rows.append(r)
            continue
        soon = fx["status"] == "in" or (fx["start_utc"] and datetime.fromisoformat(fx["start_utc"].replace("Z", "+00:00")) - now < timedelta(days=3))
        ann = announced(fx) if soon else {}
        r["lineups"] = {"A": lineup(fmt, teams[a], country, ann.get("xi", {}).get(a), ids),
                        "B": lineup(fmt, teams[b], country, ann.get("xi", {}).get(b), ids)}
        if ann.get("toss"):
            w, dec = ann["toss"]["winner"], ann["toss"]["decision"]
            first = w if dec == "bat" else (b if w == a else a)
            r["toss"] = {"winner": w, "decision": dec, "bat_first": "A" if first == a else "B"}
        r["modelled"] = True
        spec = lambda side, name: {"name": name, "order": r["lineups"][side]["order"], "plan": r["lineups"][side]["plan"],
                                   "roles": r["lineups"][side]["roles"]}
        jobs.append({"id": fx["id"], "A": spec("A", a), "B": spec("B", b), "n": SIMS[key],
                     "opts": {"venue": r["venue"], "country": country if r["env_known"] else "_default", "home": r["home"],
                              "batFirst": (r.get("toss") or {}).get("bat_first")}})
        rows.append(r)
    if sim and jobs:
        from models.intl.simrun import run_jobs
        res = run_jobs(ex / "sim_params.json", jobs)
        names = json.loads((ex / "ids.json").read_text())["names"]
        for r in rows:
            if r.get("modelled") and r["id"] in res:
                s = res[r["id"]]["summary"]
                proj = {k: s[k] for k in ("n", "p_A", "p_B", "p_draw", "p_tie", "match_runs", "match_sixes")}
                for side in ("A", "B"):
                    T = s[side]
                    nm = dict(names, **r["lineups"][side]["names"])
                    bats = sorted(((pid, d) for pid, d in T["players"].items() if "runs1" in d), key=lambda x: -x[1]["runs1"])[:3]
                    bowl = sorted(((pid, d) for pid, d in T["players"].items() if "wkts1" in d), key=lambda x: -x[1]["wkts1"])[:3]
                    proj[side] = {"bat_first_total": (s["first"][side] or {}).get("inn1_mean"), "t1_mean": T["t1_mean"],
                                  "t1_q": T["t1_q"], "top_bat": [{"id": p, "name": nm.get(p, p), "runs": d["runs1"], "p_top": d["p_top"]} for p, d in bats],
                                  "top_bowl": [{"id": p, "name": nm.get(p, p), "wkts": d["wkts1"], "p_top": d["p_topw"]} for p, d in bowl]}
                if key == "test":
                    proj.update({"lead1_mean": s["lead1_mean"], "overs_mean": s["overs_mean"], "day": s["day"]})
                r["proj"] = proj
    out = {"generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "ESPN cricket scoreboard API", "fmt": key,
           "sims_per_fixture": SIMS[key] if sim else 0, "fixtures": rows}
    (ex / "schedule.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"{key}: schedule fixtures={len(rows)} modelled={sum(1 for r in rows if r.get('modelled'))} simulated={len(jobs) if sim else 0}")
    return out


def main(argv):
    keys = [a for a in argv if a in FORMATS] or ["odi", "test"]
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 300
    today = datetime.now(timezone.utc).date()
    leagues = discover(today, days)
    fixtures = {}
    for lg in leagues.values():
        fixtures.update(fixtures_of(lg, today, days))
    print(f"series={len(leagues)} fixtures={len(fixtures)}")
    if not fixtures:
        raise SystemExit("no fixtures fetched: leaving the published schedule untouched")
    # a series the feed failed on this run keeps its published fixtures until they are over
    kept = 0
    for k in FORMATS:
        p = FORMATS[k].export / "schedule.json"
        if not p.exists():
            continue
        for r in json.loads(p.read_text()).get("fixtures", []):
            raw = r.get("raw")
            if not raw or str(raw["id"]) in fixtures:
                continue
            last_day = datetime.strptime(raw["date"], "%Y-%m-%d").date() + timedelta(days=5 if raw["fmt"] == "test" else 1)
            if last_day >= today:
                fixtures[str(raw["id"])] = raw
                kept += 1
    if kept:
        print(f"kept {kept} published fixtures the feed did not return this run")
    for k in keys:
        build(k, list(fixtures.values()), sim="--no-sim" not in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
