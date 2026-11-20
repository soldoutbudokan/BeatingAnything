"""Process backtest: what would we have forecast with the information available at the time?

A forecast is made at an *information state*. Each state fixes what is known, and the lineup, batting order
and bowling plan fed to the simulator are projected from that alone:

  pre_news   team sheets unknown. The 12 are projected from each side's earlier matches (this season and
             last), minus anyone listed in the availability file as out by then. Toss unknown.
  post_toss  toss and the players who took part are known (cricsheet). Order and bowling plan are still
             projected from earlier matches. (The used Impact Player is a small look-ahead: at the toss only the
             five options are named.)
  hindsight  real order of appearance and real overs per phase (models/ipl/replay.py). Not available before
             the match; kept as the ceiling for what better lineup information could buy.

Ratings come from a model fitted before the season (sim_params files written by oos.py / the rolling fits), so
nothing in a forecast postdates the match. Market prices join on (match_id, state): see market/prices.py.

python -m models.ipl.process 2026 [sim_params.json]
"""
# %% imports
import json
import sys

import numpy as np
import pandas as pd

from models.ipl.config import PROC, STATIC
from models.ipl.sim import Params, sim_match
from models.ipl.team import canon_team, integer_plan, nationality

AVAIL = STATIC / "availability.csv"   # match_date, team, player_id, status (out|in), known_at (UTC), source
PREV_SEASON_WEIGHT = 0.3              # last season's appearances count this much (squads turn over)
HALF_LIFE_MATCHES = 5.0
N_SIMS = 4000


# %% history tables (IPL only)


class History:
    def __init__(self):
        m = pd.read_parquet(PROC / "matches.parquet")
        m = m[m["comp"] == "IPL"].sort_values(["date", "match_id"]).reset_index(drop=True)
        m["year"] = m["date"].dt.year
        for c in ("team1", "team2", "winner", "toss_winner"):
            m[c] = m[c].map(canon_team)
        self.m = m
        rows = []
        for r in m.itertuples():
            for team, ids in json.loads(r.players).items():
                rows += [(r.match_id, r.date, r.year, canon_team(team), i) for i in ids]
        self.apps = pd.DataFrame(rows, columns=["match_id", "date", "year", "team", "id"])
        f = pd.read_parquet(PROC / "frame.parquet",
                            columns=["match_id", "comp", "date", "innings", "phase", "batter", "bowler", "bat_pos",
                                     "bat_team", "legal", "runs_total"])
        f = f[f["comp"] == "IPL"]
        self.pos = f.drop_duplicates(["match_id", "batter"])[["match_id", "date", "batter", "bat_pos"]]
        ov = f[f["legal"]].groupby(["match_id", "bowler", "phase"], observed=True).size().unstack(fill_value=0)
        self.overs = (ov.reindex(columns=[0, 1, 2], fill_value=0) / 6).reset_index()
        i1 = f[f["innings"] == 1]
        self.bat_first = i1.drop_duplicates("match_id").set_index("match_id")["bat_team"].astype(str).map(canon_team)
        self.t1 = i1.groupby("match_id")["runs_total"].sum()
        self.cov = pd.read_parquet(PROC / "covariates.parquet")
        self.nat, _ = nationality(pd.read_parquet(PROC / "matches.parquet"))
        self.avail = (pd.read_csv(AVAIL, dtype=str, parse_dates=["match_date", "known_at"]) if AVAIL.exists()
                      else pd.DataFrame(columns=["match_date", "team", "player_id", "status", "known_at", "source"]))

    def overseas(self, pid):
        return pid in self.nat.index and self.nat[pid] != "India"

    def unavailable(self, team, date, as_of=None):
        a = self.avail[(self.avail["team"] == team) & (self.avail["match_date"] == date) & (self.avail["status"] == "out")]
        if as_of is not None:
            a = a[a["known_at"] <= as_of]
        return set(a["player_id"])


# %% lineup projection from earlier matches only


def project(H, team, date, year, fixed=None, unavailable=frozenset()):
    """Returns {order, plan, xii, n_prior} or None when the side has no earlier match to go on."""
    a = H.apps[(H.apps["date"] < date) & H.apps["year"].isin([year, year - 1])]
    mine = a[a["team"] == team]
    if fixed is None:
        mids = mine.drop_duplicates("match_id")[["match_id", "year"]].reset_index(drop=True)
        if not len(mids):
            return None
        n = len(mids)
        w = 0.5 ** ((n - 1 - np.arange(n)) / HALF_LIFE_MATCHES) * np.where(mids["year"] == year, 1.0, PREV_SEASON_WEIGHT)
        wapps = mine["match_id"].map(dict(zip(mids["match_id"], w))).groupby(mine["id"]).sum()
        # a player whose latest appearance this season is for another side has moved
        last_team = a[a["year"] == year].drop_duplicates("id", keep="last").set_index("id")["team"]
        gone = set(last_team.index[last_team != team]) | set(unavailable)
        chosen, nos = [], 0
        for pid in wapps.sort_values(ascending=False).index:
            if len(chosen) == 12:
                break
            if pid in gone or (H.overseas(pid) and nos >= 4):
                continue
            chosen.append(pid)
            nos += int(H.overseas(pid))
        n_prior = int((mids["year"] == year).sum())
    else:
        chosen, n_prior = list(fixed), int(mine[mine["year"] == year]["match_id"].nunique())
    # batting position and overs per phase: each player's own IPL matches this season and last, any side
    win = a[a["id"].isin(chosen)]
    played = win.groupby("id")["match_id"].nunique()
    pos = H.pos[H.pos["match_id"].isin(win["match_id"]) & H.pos["batter"].isin(chosen)].groupby("batter")["bat_pos"].mean()
    ov = H.overs[H.overs["match_id"].isin(win["match_id"]) & H.overs["bowler"].isin(chosen)].groupby("bowler")[[0, 1, 2]].sum()
    q = {}
    for pid in chosen:
        if pid in ov.index and played.get(pid, 0) > 0:
            q[pid] = (ov.loc[pid] / played[pid]).tolist()
        else:  # no IPL in the window: career workload (all T20s), usual phase split
            opm = H.cov["overs_per_match"].get(pid, 0.0)
            q[pid] = [0.3 * opm, 0.45 * opm, 0.25 * opm] if pd.notna(opm) else [0.0, 0.0, 0.0]
    tot = {p: sum(v) for p, v in q.items()}
    sortpos = {p: pos.get(p, H.cov["bat_pos_med"].get(p, np.nan)) for p in chosen}
    sortpos = {p: (v if pd.notna(v) else 12 + (4 - tot[p])) for p, v in sortpos.items()}
    order12 = sorted(chosen, key=lambda p: sortpos[p])
    if len(order12) > 11:  # the 12th bowls but does not bat: lowest-ordered frontline bowler
        cand = [p for p in reversed(order12) if tot[p] >= 2.0]
        drop = cand[0] if cand else order12[-1]
        order = [p for p in order12 if p != drop]
    else:
        order = order12
    while len(order) < 11:
        order.append(order[-1])
    bowlers = sorted((p for p in chosen if tot[p] > 0.2), key=lambda p: -tot[p])[:7]
    if not bowlers:
        bowlers = order12[-5:]
        q.update({p: [1.2, 1.8, 1.0] for p in bowlers})
    plan = [{"id": p, "pp": v[0], "mid": v[1], "death": v[2]} for p, v in integer_plan({p: q[p] for p in bowlers}).items()
            if sum(v) > 0]
    return {"order": order[:11], "plan": plan, "xii": chosen, "n_prior": n_prior}


# %% forecasts


def forecast(P, H, r, state, n=N_SIMS, seed=0):
    actual = {canon_team(t): ids for t, ids in json.loads(r.players).items()}
    sides, over = {}, {}
    for t in (r.team1, r.team2):
        fixed = actual.get(t) if state == "post_toss" else None
        s = project(H, t, r.date, r.year, fixed=fixed, unavailable=H.unavailable(t, r.date))
        if s is None:
            return None
        sides[t] = s
        over[t] = len(set(s["xii"]) & set(actual.get(t, []))) / max(len(s["xii"]), 1)
    A = {"name": r.team1, **{k: sides[r.team1][k] for k in ("order", "plan")}}
    B = {"name": r.team2, **{k: sides[r.team2][k] for k in ("order", "plan")}}
    first = H.bat_first.get(r.match_id)
    bf = None if state == "pre_news" else ("A" if first == r.team1 else "B")
    res = sim_match(P, A, B, r.venue, n=n, seed=seed, bat_first=bf)
    parts = res.get("parts", [res])
    t1 = np.concatenate([p[p["first"][0]]["score"] for p in parts])
    return {"p_team1": float(res["winA"].mean()), "overlap1": over[r.team1], "overlap2": over[r.team2],
            "n_prior1": sides[r.team1]["n_prior"], "n_prior2": sides[r.team2]["n_prior"],
            "t1_mean": float(t1.mean())}


def run(year, params_path):
    H = History()
    P = Params.load(params_path)
    ms = H.m[(H.m["year"] == year) & (H.m["result"].isin(["win", "tie"])) & (~H.m["reduced"])]
    rows = []
    for k, r in enumerate(ms.itertuples()):
        for state in ("pre_news", "post_toss"):
            fc = forecast(P, H, r, state, seed=10 * k + (state == "post_toss"))
            if fc is None:
                continue
            rows.append(dict(match_id=r.match_id, date=r.date, year=year, team1=r.team1, team2=r.team2, venue=r.venue,
                             state=state, team1_won=0.5 if not r.winner else float(r.winner == r.team1),
                             team1_bat_first=float(H.bat_first.get(r.match_id) == r.team1),
                             t1_actual=float(H.t1.get(r.match_id, np.nan)), **fc))
    out = pd.DataFrame(rows)
    out.to_parquet(PROC / f"process_{year}.parquet", index=False)
    return out


# %% scoring


def logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-3, 1 - 1e-3)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def summary(d, ref=None):
    """Per state: n, log loss, log loss minus the reference forecast (default 0.5) with a paired SE, lineup
    overlap, and first-innings bias (post_toss only: the side batting first is known)."""
    rows = []
    for s, x in d.groupby("state", sort=False):
        ll = logloss(x["p_team1"], x["team1_won"])
        r = logloss(x[ref] if ref else np.full(len(x), 0.5), x["team1_won"])
        rows.append(dict(state=s, n=len(x), logloss=ll.mean(), ref_logloss=r.mean(), diff=(ll - r).mean(),
                         diff_se=(ll - r).std(ddof=1) / np.sqrt(len(x)),
                         fav_won=float(((x["p_team1"] > 0.5) == (x["team1_won"] > 0.5)).mean()),
                         xii_overlap=float(x[["overlap1", "overlap2"]].to_numpy().mean()),
                         t1_bias=float((x["t1_mean"] - x["t1_actual"]).mean()) if s != "pre_news" else np.nan))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    yr = int(sys.argv[1])
    path = sys.argv[2] if len(sys.argv) > 2 else PROC / ("sim_params_holdout.json" if yr == 2026 else f"sim_params_roll_{yr}.json")
    d = run(yr, path)
    pd.set_option("display.width", 200)
    print(summary(d).round(4).to_string(index=False))
