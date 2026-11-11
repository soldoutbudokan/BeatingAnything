# %% Python side of the JS/Python parity check: write reference results for a few scenarios
"""python -m models.wnba.parity  -> data/processed/wnba/parity_py.json, then
   node models/wnba/parity_check.js  (compares docs/models/wnba/sim.js on the same scenarios)"""
from __future__ import annotations

import json
import time

import numpy as np

from models.wnba.common import EXPORT, PROC
from models.wnba.sim import game_summary, player_summary, simulate

N = 20000


def scenarios(prm):
    by_team = {}
    for p in prm["players"]:
        if p["team"] is not None:
            by_team.setdefault(p["team"], []).append(p)
    teams = sorted(by_team, key=lambda t: t)
    t1, t2, t3, t4 = 17, 9, 5, 131935
    star = max(by_team[t1], key=lambda p: p["min"])
    sc = [
        dict(name="LV vs NY default", home=t1, away=t2, opts={}),
        dict(name="IND vs TOR neutral, home b2b", home=t3, away=t4, opts={"neutral": True, "home_b2b": True}),
        dict(name=f"LV without {star['name']} vs NY", home={"team": t1, "players": [{"id": p["id"], "out": p["id"] == star["id"]} for p in by_team[t1]]},
             away=t2, opts={}),
    ]
    return sc


def main():
    prm = json.loads((EXPORT / "sim_params.json").read_text())  # use the exported (rounded) params, same as JS
    out = []
    for s in scenarios(prm):
        t = time.time()
        r = simulate(prm, s["home"], s["away"], n_sims=N, seed=11, opts=s["opts"])
        dt = time.time() - t
        g = game_summary(r)
        hp = player_summary(r, 0)
        ap = player_summary(r, 1)
        out.append(dict(name=s["name"], home=s["home"], away=s["away"], opts=s["opts"], n=N, seconds=dt,
                        game=dict(home_win=g["home_win"], margin=g["margin"], total=g["total"], home_pts=g["home_pts"],
                                  away_pts=g["away_pts"], p_ot=g["p_ot"], poss=g["poss_per_team"]),
                        players={str(p["id"]): {k: [p[k]["mean"], p[k]["sd"]] for k in ["min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]}
                                 for p in hp + ap if p["proj_min"] > 0},
                        minutes={str(int(i)): float(m) for T in (r["home"], r["away"]) for i, m in zip(T.ids, T.minutes)}))
        print(f"parity py: {s['name']}: {dt:.2f}s for {N} sims, home win {g['home_win']:.3f}, total {g['total']['mean']:.1f}")
    (PROC / "parity_py.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
