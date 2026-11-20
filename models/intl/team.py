"""National sides: recent squad, likely XI by conditions, batting order and bowling plan.

The default XI is the side's most recent XI (scorecard order). Because sides pick differently by conditions
(more spin in Asia, more pace elsewhere), each side also carries its most recent XI in each conditions
group; a fixture uses the one for its host country when it is recent enough.
"""
# %% imports
import json

import numpy as np
import pandas as pd

from models.intl.config import FORMATS, REGION, TEAM_SHORT

SQUAD_MONTHS = 30      # squad = everyone who appeared in this window
REGION_MONTHS = 24     # a conditions-specific XI older than this is not used
USAGE_MATCHES = 30     # bowling usage is read from the side's last matches
USAGE_HALF_LIFE = 6.0  # ... weighted by recency (in matches)


# %% plans


def integer_plan(q, total=50, cap=10, targets=(10, 30, 10), ph_caps=(5, 10, 5)):
    """q: {id: [pp, mid, death] usual overs per match}. Whole overs per phase that fill `targets` with at most
    `cap` a bowler. Quotas follow the usual workload; death then powerplay then middle overs go to the bowler
    whose usual share of the phase most exceeds what he has been given."""
    ids = list(q)
    usual = np.array([sum(q[i]) for i in ids], float)
    share = np.array([np.array(q[i]) / max(sum(q[i]), 1e-9) for i in ids])
    want = np.minimum(usual, float(cap))
    t = np.zeros(len(ids), int)
    left = total
    for k in np.argsort(-want, kind="stable"):
        t[k] = min(int(np.round(want[k])), left)
        left -= t[k]
    while left > 0:
        ok = t < cap
        if not ok.any():
            break
        k = int(np.argmax(np.where(ok, want - t, -1e9)))
        t[k] += 1
        left -= 1
    alloc = np.zeros((len(ids), 3), int)
    for ph in (2, 0, 1):
        for _ in range(targets[ph]):
            free = (alloc.sum(1) < t) & (alloc[:, ph] < ph_caps[ph])
            if not free.any():
                free = (alloc.sum(1) < cap) & (alloc[:, ph] < ph_caps[ph])
                if not free.any():
                    break
            sc = np.where(free, share[:, ph] * t - alloc[:, ph] + 0.001 * t, -1e9)
            alloc[int(np.argmax(sc)), ph] += 1
    return [{"id": i, "pp": int(a[0]), "mid": int(a[1]), "death": int(a[2])} for i, a in zip(ids, alloc) if a.sum() > 0]


def share_plan(q):
    """q: {id: [new, mid, old] share of the side's overs}. Percentages per ball phase that sum to 100."""
    ids = [i for i in q if max(q[i]) >= 0.01]
    a = np.array([q[i] for i in ids], float)
    a = 100 * a / np.maximum(a.sum(0, keepdims=True), 1e-9)
    return [{"id": i, "nb": round(float(r[0]), 1), "mid": round(float(r[1]), 1), "old": round(float(r[2]), 1)}
            for i, r in zip(ids, a)]


def fallback_usage(fmt, opm_other, spin):
    """Usage guess for a bowler with no record in this format, from his overs per match in the other one."""
    if not opm_other or opm_other < 1.0:
        return None
    if fmt.key == "odi":
        tot = float(np.clip(opm_other / 3.5, 0, 10))
        mix = (0.05, 0.85, 0.10) if spin else (0.25, 0.50, 0.25)
        return [tot * x for x in mix]
    sh = float(np.clip(opm_other / 50.0, 0, 0.3))
    mix = (0.3, 1.3, 1.2) if spin else (1.3, 0.9, 0.9)
    return [sh * x for x in mix]


# %% build


def build(key):
    fmt = FORMATS[key]
    m = pd.read_parquet(fmt.proc / "matches.parquet").sort_values(["date", "match_id"]).reset_index(drop=True)
    f = pd.read_parquet(fmt.proc / "frame.parquet",
                        columns=["match_id", "date", "inn", "phase", "bowler", "bowl_team", "legal", "batter", "bat_team",
                                 "bat_pos"])
    styles = pd.read_parquet(fmt.proc / "styles.parquet")
    okey = "test" if key == "odi" else "odi"
    opath = FORMATS[okey].proc / "frame.parquet"
    opm_other = {}
    if opath.exists():
        o = pd.read_parquet(opath, columns=["match_id", "bowler", "legal", "date"])
        o = o[o["legal"] & (o["date"] >= o["date"].max() - pd.DateOffset(months=36))]
        opm_other = (o.groupby(["bowler", "match_id"]).size().groupby(level=0).mean() / 6.0).to_dict()
    ref = m["date"].max()
    since = ref - pd.DateOffset(months=SQUAD_MONTHS)
    lg = f[f["legal"]]
    by_match = lg.groupby(["match_id", "bowl_team", "bowler", "phase"], observed=True).size().rename("balls").reset_index()
    team_ph = lg.groupby(["match_id", "bowl_team", "phase"], observed=True).size().rename("tb").reset_index()
    first = f.drop_duplicates(["match_id", "inn", "batter"])
    teams = {}
    names = sorted(set(m.loc[m["date"] >= since, "team1"]) | set(m.loc[m["date"] >= since, "team2"]))
    for team in names:
        tm = m[(m["team1"] == team) | (m["team2"] == team)].reset_index(drop=True)
        recent = tm[tm["date"] >= since]
        if len(recent) < (2 if key == "test" else 3):
            continue
        lists = [json.loads(p).get(team, []) for p in tm["players"]]
        tm = tm.assign(xi=lists, region=tm["country"].map(REGION).fillna("other"))
        tm = tm[tm["xi"].map(len) >= 11].reset_index(drop=True)
        if not len(tm):
            continue
        # ---- squad
        app = {}
        for r in tm[tm["date"] >= since].itertuples():
            for pid in r.xi:
                a = app.setdefault(pid, [0, None])
                a[0] += 1
                a[1] = str(r.date.date())
        # ---- bowling usage over the last matches (recency-weighted over the matches each bowler played)
        use = tm.tail(USAGE_MATCHES).reset_index(drop=True)
        nmt = len(use)
        wt = {mid: 0.5 ** ((nmt - 1 - k) / USAGE_HALF_LIFE) for k, mid in enumerate(use["match_id"])}
        played = {}
        for r in use.itertuples():
            for pid in r.xi:
                played[pid] = played.get(pid, 0.0) + wt[r.match_id]
        bm = by_match[(by_match["bowl_team"].astype(str) == team) & by_match["match_id"].isin(wt)]
        tp = team_ph[(team_ph["bowl_team"].astype(str) == team) & team_ph["match_id"].isin(wt)]
        bm = bm.merge(tp[["match_id", "phase", "tb"]], on=["match_id", "phase"])
        bm["w"] = bm["match_id"].map(wt)
        if key == "odi":
            bm["x"] = bm["balls"] / 6.0 * bm["w"]            # overs per match played
        else:
            bm["x"] = bm["balls"] / bm["tb"] * bm["w"]        # share of the side's overs in the phase
        num = bm.groupby(["bowler", "phase"])["x"].sum().unstack(fill_value=0.0).reindex(columns=[0, 1, 2], fill_value=0.0)
        usage = {pid: (num.loc[pid] / max(played.get(pid, 0.0), 1e-9)).tolist() for pid in num.index}
        spin_of = lambda pid: bool(styles["bowl_group"].get(pid) == "spin")

        def plan_for(xi):
            q = {}
            for pid in xi:
                u = usage.get(pid)
                if u is None or sum(u) <= 0:
                    u = fallback_usage(fmt, opm_other.get(pid), spin_of(pid))
                if u is not None and sum(u) > 0:
                    q[pid] = u
            if key == "odi":
                q = {p: u for p, u in q.items() if sum(u) >= 0.3}
                top = sorted(q, key=lambda p: -sum(q[p]))[:8]
                return integer_plan({p: q[p] for p in top}) if top else []
            return share_plan(q) if q else []

        def lineup(row):
            xi = list(row.xi)[:11]
            # batting order: mean order of appearance over each player's last ten innings for the side (cricsheet's
            # team sheet is not always in batting order); a player yet to bat goes after the rest, bowlers last
            key = {p: (float(pos[p]) if p in pos.index else 12.0 + sum(usage.get(p, [0, 0, 0])), k) for k, p in enumerate(xi)}
            order = sorted(xi, key=lambda p: key[p])
            return {"xi": xi, "order": order, "plan": plan_for(xi), "from_match": row.match_id, "date": str(row.date.date()),
                    "venue": row.venue, "country": row.country}

        tb = first[(first["bat_team"].astype(str) == team) & (first["date"] >= since)]
        pos = tb.groupby("batter")["bat_pos"].apply(lambda s: s.tail(10).mean())
        last = tm.iloc[-1]
        by_region = {}
        for reg in ("asia", "sena", "other"):
            rr = tm[(tm["region"] == reg) & (tm["date"] >= ref - pd.DateOffset(months=REGION_MONTHS))]
            if len(rr):
                by_region[reg] = lineup(rr.iloc[-1])
        squad = [{"id": pid, "apps": a[0], "last_app": a[1], "bat_pos": None if pid not in pos.index else round(float(pos[pid]), 1),
                  "usage": None if pid not in usage else [round(float(x), 3) for x in usage[pid]]}
                 for pid, a in sorted(app.items(), key=lambda kv: (-kv[1][0], kv[0]))]
        teams[team] = dict(name=team, short=TEAM_SHORT.get(team, team[:3].upper()), region=REGION.get(team, "other"),
                           matches=int(len(recent)), last_match=str(last.date.date()), default=lineup(last),
                           by_region=by_region, squad=squad)
    return teams


def lineup_for(team, country):
    """The side's lineup for a fixture in `country`: the conditions-specific XI when there is one."""
    reg = REGION.get(country, "other")
    return team["by_region"].get(reg) or team["default"]


if __name__ == "__main__":
    import sys
    for k in (sys.argv[1:] or ["odi", "test"]):
        T = build(k)
        for t, d in T.items():
            print(k, d["short"], d["matches"], d["last_match"], len(d["squad"]), list(d["by_region"]),
                  [(p["id"],) + tuple(v for kk, v in p.items() if kk != "id") for p in d["default"]["plan"]][:8])
