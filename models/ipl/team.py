"""Team layer: latest-season IPL squads, default XI + Impact Player, batting order, bowling plan."""
# %% imports
import json

import numpy as np
import pandas as pd

from models.ipl.config import PROC

TEAM_ALIASES = {"Royal Challengers Bangalore": "Royal Challengers Bengaluru", "Kings XI Punjab": "Punjab Kings",
                "Delhi Daredevils": "Delhi Capitals", "Rising Pune Supergiants": "Rising Pune Supergiant"}
SHORT = {"Chennai Super Kings": "CSK", "Delhi Capitals": "DC", "Gujarat Titans": "GT", "Kolkata Knight Riders": "KKR",
         "Lucknow Super Giants": "LSG", "Mumbai Indians": "MI", "Punjab Kings": "PBKS", "Rajasthan Royals": "RR",
         "Royal Challengers Bengaluru": "RCB", "Sunrisers Hyderabad": "SRH"}
PHASE_TARGET = [6, 9, 5]
PHASE_CAP = [3, 4, 3]


def canon_team(t):
    return TEAM_ALIASES.get(t, t)


# %% nationality (overseas flag) from international appearances


def nationality(matches):
    intl = matches[matches["team_type"] == "international"]
    rows = []
    for pl in intl["players"]:
        for team, ids in json.loads(pl).items():
            rows += [(i, team) for i in ids]
    d = pd.DataFrame(rows, columns=["id", "team"])
    nat = d.groupby("id")["team"].agg(lambda s: s.value_counts().index[0])
    dom = matches[matches["comp"] == "SMA"]
    smat = set()
    for pl in dom["players"]:
        for ids in json.loads(pl).values():
            smat.update(ids)
    return nat, smat


def is_overseas(pid, nat, smat):
    if pid in nat.index:
        return nat[pid] != "India"
    return False  # uncapped players in IPL are almost all Indian (SMAT or not)


# %% plan helpers


def integer_plan(q):
    """q: dict id -> [pp, mid, death] historical overs per match. Returns id -> [pp, mid, death] integers.

    Step 1: whole-match quotas proportional to historical overs per match, scaled to 20, max 4 each.
    Step 2: death then powerplay then middle overs go to the bowler whose historical phase share most
    exceeds what he has been given so far (per-phase caps 3/4/3 = no consecutive overs possible)."""
    ids = list(q)
    tot = np.array([sum(q[i]) for i in ids], float)
    share = np.array([np.array(q[i]) / max(sum(q[i]), 1e-9) for i in ids])
    want = np.minimum(tot, 4.0)
    t = np.zeros(len(ids), int)
    for _ in range(20):  # hand out overs to whoever is furthest below his usual workload
        ok = t < 4
        if not ok.any():
            break
        gap = np.where(ok, want - t + 0.01 * want, -1e9)
        t[int(np.argmax(gap))] += 1
    alloc = np.zeros((len(ids), 3), int)
    for ph in (2, 0, 1):
        for _ in range(PHASE_TARGET[ph]):
            free = (alloc.sum(1) < t) & (alloc[:, ph] < PHASE_CAP[ph])
            if not free.any():
                free = (alloc.sum(1) < 4) & (alloc[:, ph] < PHASE_CAP[ph])
                if not free.any():
                    break
            sc = np.where(free, share[:, ph] * t - alloc[:, ph] + 0.001 * t, -1e9)
            alloc[int(np.argmax(sc)), ph] += 1
    return {i: alloc[k].tolist() for k, i in enumerate(ids)}


# %% build


def build(season=None):
    m = pd.read_parquet(PROC / "matches.parquet")
    f = pd.read_parquet(PROC / "frame.parquet",
                        columns=["match_id", "comp", "season", "date", "innings", "over", "phase", "batter",
                                 "non_striker", "bowler", "bat_pos", "bat_team", "bowl_team", "cls", "legal"])
    ipl_m = m[m["comp"] == "IPL"].copy()
    ipl_m["year"] = ipl_m["date"].dt.year
    season = season or int(ipl_m["year"].max())
    cur = ipl_m[ipl_m["year"] == season].sort_values("date")
    nat, smat = nationality(m)
    fi = f[(f["comp"] == "IPL")]
    fi = fi.assign(year=fi["date"].dt.year)
    teams = {}
    for team in sorted(set(cur["team1"]) | set(cur["team2"])):
        tm = cur[(cur["team1"] == team) | (cur["team2"] == team)].reset_index(drop=True)
        nmt = len(tm)
        app = {}
        for k, pl in enumerate(tm["players"]):
            ids = json.loads(pl).get(team, [])
            wt = 0.5 ** ((nmt - 1 - k) / 5.0)  # later matches count more (half-life 5 matches)
            for i in ids:
                a = app.setdefault(i, [0, 0.0, None])
                a[0] += 1
                a[1] += wt
                a[2] = str(tm.loc[k, "date"].date())
        sq = pd.DataFrame([(i, *v) for i, v in app.items()], columns=["id", "apps", "wapps", "last"])
        sq["overseas"] = [is_overseas(i, nat, smat) for i in sq["id"]]
        # batting position (recency-weighted mean) and bowling usage this season (fallback: prior seasons)
        tb = fi[(fi["bat_team"] == team)]
        mids = list(tm["match_id"])
        mw = {mid: 0.5 ** ((nmt - 1 - k) / 5.0) for k, mid in enumerate(mids)}
        first = tb[tb["match_id"].isin(mids)].drop_duplicates(["match_id", "batter"])
        first = first.assign(w=first["match_id"].map(mw))
        pos = (first["bat_pos"] * first["w"]).groupby(first["batter"]).sum() / first.groupby("batter")["w"].sum()
        nbat = first.groupby("batter").size()
        bw = fi[(fi["bowl_team"] == team) & fi["match_id"].isin(mids) & fi["legal"]]
        ov = bw.groupby(["bowler", "match_id", "phase"]).size().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0) / 6
        per_match = ov.groupby(level=0).mean()
        sq["bat_pos"] = sq["id"].map(pos)
        sq["innings_batted"] = sq["id"].map(nbat).fillna(0).astype(int)
        sq["ov_pp"] = sq["id"].map(per_match[0]).fillna(0)
        sq["ov_mid"] = sq["id"].map(per_match[1]).fillna(0)
        sq["ov_death"] = sq["id"].map(per_match[2]).fillna(0)
        sq["overs_pm"] = sq[["ov_pp", "ov_mid", "ov_death"]].sum(axis=1)
        sq = sq.sort_values(["wapps", "apps"], ascending=False).reset_index(drop=True)
        # default 12: top recency-weighted appearances, <= 4 overseas
        chosen, nos = [], 0
        for _, r in sq.iterrows():
            if len(chosen) == 12:
                break
            if r["overseas"] and nos >= 4:
                continue
            chosen.append(r["id"])
            nos += int(r["overseas"])
        x = sq.set_index("id").loc[chosen]
        # batting order: by weighted batting position; players who never batted go last by fewest overs
        x = x.assign(sortpos=x["bat_pos"].fillna(12 + (4 - x["overs_pm"])))
        order12 = list(x.sort_values("sortpos").index)
        # the 12th (bowling-only Impact Player) is the lowest-ordered player who is a frontline bowler
        cand = [p for p in reversed(order12) if x.loc[p, "overs_pm"] >= 2.0]
        drop = cand[0] if cand else order12[-1]
        order = [p for p in order12 if p != drop]
        bowlers = x[x["overs_pm"] > 0.2].sort_values("overs_pm", ascending=False)
        q = {p: [float(bowlers.loc[p, "ov_pp"]), float(bowlers.loc[p, "ov_mid"]), float(bowlers.loc[p, "ov_death"])]
             for p in bowlers.index[:7]}
        plan = integer_plan(q)
        plan = [{"id": p, "pp": a[0], "mid": a[1], "death": a[2]} for p, a in plan.items() if sum(a) > 0]
        # home venue: most frequent venue in this and the previous season (this season counted double)
        hv = ipl_m[((ipl_m["team1"] == team) | (ipl_m["team2"] == team)) & (ipl_m["year"] >= season - 1)]
        vc = (hv["venue"].where(hv["year"] == season).value_counts() * 2).add(hv["venue"].value_counts(), fill_value=0)
        teams[team] = dict(name=team, short=SHORT.get(team, team[:3].upper()), season=season,
                           matches=nmt, home_venue=vc.idxmax(), venues_used=vc.sort_values(ascending=False).head(3).index.tolist(),
                           squad=sq, xii=chosen, order=order, impact=drop, plan=plan)
    return teams, nat, smat


if __name__ == "__main__":
    teams, nat, _ = build()
    for t, d in teams.items():
        print(d["short"], d["home_venue"], d["matches"], len(d["squad"]), "impact:", d["impact"],
              "plan:", [(p["id"], p["pp"], p["mid"], p["death"]) for p in d["plan"]])
