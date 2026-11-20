"""Diagnostics (not a backtest): walk-forward per-ball calibration and a replay of real matches through the simulator.

Usage: python -m models.intl.diagnostics odi|test
"""
# %% imports
import json
import pickle
import sys

import numpy as np
import pandas as pd

from models.intl.config import CLASSES, FORMATS, REF
from models.intl.final_fit import hyper
from models.intl.fit import load, probs_from_eta
from models.intl.ratings import C, total_row
from models.intl.simrun import run_jobs
from models.intl.team import integer_plan, share_plan

REPLAY_SINCE = {"test": "2022-01-01", "odi": "2023-07-01"}
REPLAY_SIMS = 300


# %% holdout calibration


def holdout(fmt, f, exs):
    p = fmt.proc / "holdout_eta.npz"
    if not p.exists():
        return None
    z = np.load(p, allow_pickle=True)
    r = f.iloc[z["row"]].reset_index(drop=True)
    P = probs_from_eta(z["eta"].astype(float))
    y = r["y"].to_numpy()
    ll = float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))))
    freq = np.bincount(y, minlength=len(CLASSES)) / len(y)
    cls = []
    for k, c in enumerate(CLASSES):
        pk, obs = P[:, k], (y == k).astype(float)
        lo, hi = np.quantile(pk, [0.2, 0.8])
        top, bot = pk >= hi, pk <= lo
        cls.append({"cls": c, "pred": float(pk.mean()), "obs": float(obs.mean()), "slope": float(pk[top].mean()),
                    "slope_obs": float(obs[top].mean()), "lo": float(pk[bot].mean()), "lo_obs": float(obs[bot].mean())})
    inn = pd.DataFrame({"k": r["match_id"].astype(str) + "|" + r["inn"].astype(str), "x": total_row(P, exs),
                        "a": r["runs_total"].to_numpy(), "w": P[:, C["wicket"]] + P[:, C["runout"]],
                        "wa": np.isin(y, [C["wicket"], C["runout"]])}).groupby("k").sum()
    folds = []
    for k, (lo, hi) in enumerate(fmt.cutoffs):
        rk = r[z["fold"] == k]
        folds.append({"from": lo, "to": str(rk["date"].max().date()) if len(rk) else hi, "balls": int(len(rk)),
                      "matches": int(rk["match_id"].nunique())})
    return {"logloss": ll, "logloss_marginal": float(-np.mean(np.log(freq[y]))), "n_balls": int(len(y)), "folds": folds,
            "classes": cls, "innings_runs_expected": float(inn["x"].mean()), "innings_runs_actual": float(inn["a"].mean()),
            "innings_wkts_expected": float(inn["w"].mean()), "innings_wkts_actual": float(inn["wa"].mean())}


def tuning(fmt):
    rows = []
    for k in (1, 2, 3):
        p = fmt.proc / f"tuning_r{k}.json"
        if p.exists():
            for r in json.loads(p.read_text()):
                rows.append({"name": r["name"] if k == 1 else f"round {k}: {r['name']}", "half_life": r["half_life"], "ll": r["ll"],
                             "d_vs_base": r.get("d_vs_base"), "d_se": r.get("d_se"), "ll_folds": r["ll_folds"]})
    return rows


# %% replay of real matches


def replay(fmt, f):
    """Each real match re-simulated with the real XIs, batting order of appearance, each bowler's real workload
    by phase, ground and side batting first."""
    key = fmt.key
    m = pd.read_parquet(fmt.proc / "matches.parquet")
    m = m[(m["date"] >= REPLAY_SINCE[key]) & (~m["reduced"])].sort_values("date")
    sp = json.loads((fmt.export / "sim_params.json").read_text())
    fr = f[f["date"] >= REPLAY_SINCE[key]]
    pos = fr.drop_duplicates(["match_id", "bat_team", "batter"]).groupby(["match_id", "bat_team"], observed=True)
    order_of = {k: g.sort_values(["inn", "bat_pos"])["batter"].tolist() for k, g in pos}
    lg = fr[fr["legal"]]
    use = lg.groupby(["match_id", "bowl_team", "bowler", "phase"], observed=True).size().rename("b").reset_index()
    tot = lg.groupby(["match_id", "bowl_team", "phase"], observed=True).size().rename("tb").reset_index()
    use = use.merge(tot, on=["match_id", "bowl_team", "phase"])
    jobs, act = [], {}
    for r in m.itertuples():
        inns = json.loads(r.innings)
        players = json.loads(r.players)
        if len(inns) < 2 or any(len(players.get(t, [])) < 11 for t in (r.team1, r.team2)):
            continue
        first = inns[0]["team"]
        second = r.team2 if first == r.team1 else r.team1
        spec = {}
        for t in (first, second):
            seen = order_of.get((r.match_id, t), [])
            order = seen + [p for p in players[t] if p not in seen]
            u = use[(use["match_id"] == r.match_id) & (use["bowl_team"].astype(str) == t)]
            q = {}
            for b, g in u.groupby("bowler"):
                v = [0.0, 0.0, 0.0]
                for ph, bb, tb in zip(g["phase"], g["b"], g["tb"]):
                    v[int(ph)] = bb / 6.0 if key == "odi" else bb / tb
                if b in order:
                    q[b] = v
            if len(q) < (5 if key == "odi" else 2):
                spec = None
                break
            plan = integer_plan(q) if key == "odi" else share_plan(q)
            spec[t] = {"name": t, "order": order[:11], "plan": plan}
        if not spec:
            continue
        venue = r.venue if r.venue in sp["venues"] else None
        country = r.country if r.country in sp["env"] else "_default"
        home = "A" if first == r.country else ("B" if second == r.country else None)
        jobs.append({"id": r.match_id, "A": spec[first], "B": spec[second], "n": REPLAY_SIMS, "seed": 17 + len(jobs),
                     "opts": {"venue": venue, "country": country, "home": home, "batFirst": "A"}, "hists": ["A.t1", "B.t1"]})
        a = {"t1A": inns[0]["runs"], "t1B": inns[1]["runs"], "wA": inns[0]["wkts"], "wB": inns[1]["wkts"],
             "decA": inns[0]["declared"], "aoA": inns[0]["wkts"] >= 10 - inns[0].get("absent", 0),
             "result": "draw" if r.result == "draw" else ("tie" if r.result == "tie" else ("A" if r.winner == first else "B")),
             "overs": r.m_legal / 6.0, "fo": any(x.get("follow_on") for x in inns),
             "fo_ok": len(inns) >= 2 and inns[0]["runs"] - inns[1]["runs"] >= 200, "ov1": inns[0]["legal"] / 6.0,
             "runs": sum(x["runs"] for x in inns)}
        if key == "test":
            a["t2"] = [x["runs"] for x in inns[2:]]
        act[r.match_id] = a
    res = run_jobs(fmt.export / "sim_params.json", jobs)
    A = pd.DataFrame.from_dict(act, orient="index")
    S = {i: res[i]["summary"] for i in A.index}
    g = lambda fn: np.array([fn(S[i]) for i in A.index], float)
    # where each real first-innings total fell in its simulated distribution (randomised within ties)
    rng = np.random.default_rng(0)
    pit, sd_sim = [], []
    for i in A.index:
        h = np.asarray(res[i]["hists"]["A.t1"], float)
        x = int(A.loc[i, "t1A"])
        below = h[:x].sum() if x < len(h) else h.sum()
        at = h[x] if x < len(h) else 0.0
        pit.append((below + rng.random() * at) / h.sum())
        v = np.arange(len(h))
        mu = (v * h).sum() / h.sum()
        sd_sim.append(np.sqrt(((v - mu) ** 2 * h).sum() / h.sum()))
    pit = np.array(pit)
    pA = g(lambda s: s["p_A"])
    won = (A["result"] == "A").to_numpy().astype(float)
    rows = [
        {"metric": "First innings of the match: mean total", "actual": A["t1A"].mean(), "sim": g(lambda s: s["A"]["t1_mean"]).mean()},
        {"metric": "First innings of the match: SD of totals", "actual": A["t1A"].std(),
         "sim": float(np.sqrt(np.mean(np.square(sd_sim)) + np.var(g(lambda s: s["A"]["t1_mean"]))))},
        {"metric": "First innings: wickets lost", "actual": A["wA"].mean(), "sim": g(lambda s: s["A"]["w1_mean"]).mean()},
        {"metric": "First innings: all out (%)", "actual": 100 * A["aoA"].mean(), "sim": 100 * g(lambda s: s["A"]["p_allout1"]).mean()},
        {"metric": "First innings: overs", "actual": A["ov1"].mean(), "sim": g(lambda s: s["A"]["overs1_mean"]).mean()},
        {"metric": "Side batting first wins (%)", "actual": 100 * won.mean(), "sim": 100 * pA.mean()},
        {"metric": "Match runs", "actual": A["runs"].mean(), "sim": g(lambda s: s["match_runs"]).mean()},
    ]
    if key == "test":
        rows += [
            {"metric": "Second side's first innings: mean total", "actual": A["t1B"].mean(), "sim": g(lambda s: s["B"]["t1_mean"]).mean()},
            {"metric": "First innings: declared (%)", "actual": 100 * A["decA"].mean(), "sim": 100 * g(lambda s: s["A"]["p_decl1"]).mean()},
            {"metric": "Draw (%)", "actual": 100 * (A["result"] == "draw").mean(), "sim": 100 * g(lambda s: s["p_draw"]).mean()},
            {"metric": "Overs bowled in the match", "actual": A["overs"].mean(), "sim": g(lambda s: s["overs_mean"]).mean()},
            {"metric": "Follow-on enforced (%)", "actual": 100 * A["fo"].mean(), "sim": 100 * g(lambda s: s["p_follow_on"]).mean()},
            {"metric": "Second-innings totals (third and fourth innings of the match)",
             "actual": float(np.mean([x for v in A["t2"] for x in v])),
             "sim": float(np.mean([np.mean([t for t in (S[i]["A"]["t2_mean"], S[i]["B"]["t2_mean"]) if t is not None]) for i in A.index]))},
        ]
    else:
        rows += [
            {"metric": "Tie (%)", "actual": 100 * (A["result"] == "tie").mean(), "sim": 100 * g(lambda s: s["p_tie"]).mean()},
            {"metric": "First innings: runs in overs 1-10", "actual": float(first10(fr, A.index)), "sim": g(lambda s: s["A"]["pp_mean"]).mean()},
        ]
    # pre-match win probability of the side batting first, in fifths (draws and ties count as not won)
    q = np.quantile(pA, [0.2, 0.4, 0.6, 0.8])
    b = np.searchsorted(q, pA)
    cal = [{"bin": f"{100 * pA[b == k].min():.0f}-{100 * pA[b == k].max():.0f}%", "n": int((b == k).sum()),
            "pred": float(pA[b == k].mean()), "obs": float(won[b == k].mean())} for k in range(5) if (b == k).any()]
    brier = float(np.mean((pA - won) ** 2))
    base = float(np.mean((won.mean() - won) ** 2))
    return {"matches": int(len(A)), "since": REPLAY_SINCE[key], "sims": REPLAY_SIMS, "rows": rows,
            "pit": (np.bincount(np.minimum((pit * 10).astype(int), 9), minlength=10) / len(pit)).tolist(),
            "result_calibration": cal, "brier": brier, "brier_base_rate": base,
            "note": ("Each match is re-simulated with the real XIs, batting order of appearance, each bowler's real share of the "
                     "bowling by phase, the ground and the side that batted first. The ratings were fitted on these same "
                     "matches, so this checks that the simulator turns per-ball probabilities into realistic matches. It is "
                     "not evidence of predictive skill, and the win-probability table flatters the model for the same reason.")}


def first10(fr, ids):
    d = fr[(fr["inn"] == 1) & (fr["over"] < 10) & fr["match_id"].isin(ids)]
    return d.groupby("match_id")["runs_total"].sum().mean()


# %% main


def main(key):
    fmt = FORMATS[key]
    f = load(key)
    with open(fmt.proc / "ratings.pkl", "rb") as fh:
        R = pickle.load(fh)
    H, lam = hyper(fmt)
    sh = R["shock"]
    out = {"holdout": holdout(fmt, f, R["exs"]), "tuning": tuning(fmt),
           "adopted": f"half-life {H:g} years; penalties " + ", ".join(f"{k} {v:g}" for k, v in sorted(lam.items())),
           "replay": replay(fmt, f)}
    G = np.asarray(sh["G"])
    Sm, Si = np.asarray(sh["S_match"]), np.asarray(sh["S_inn"])
    per = 6 if key == "test" else 300   # runs per over (Test) or per 50 overs (ODI) for one SD
    unit = "runs per over" if key == "test" else "runs per 50 overs"
    out["shock"] = {
        "note": (f"Estimated on {sh['source']}: {sh['n_innings']} innings, {sh['n_pairs']} cross-team innings pairs. Both sides of a "
                 "match share a pitch and weather; the covariance of their residual scoring and wicket rates sizes a match-level "
                 "shock on a scoring axis and a wicket axis, and what is left of the within-innings variance after sampling "
                 "noise sizes an innings-level shock. Both are drawn in every simulated match."),
        "rows": [["Match shock, scoring axis (SD, log-odds)", f"{np.sqrt(Sm[0, 0]):.3f} (about {np.sqrt(Sm[0, 0]) * G[0, 0] * per:+.2f} {unit})"],
                 ["Match shock, wicket axis (SD, log-odds)", f"{np.sqrt(Sm[1, 1]):.3f} (wicket rate x {np.exp(np.sqrt(Sm[1, 1])):.2f} at +1 SD)"],
                 ["Innings shock, scoring axis (SD)", f"{np.sqrt(Si[0, 0]):.3f}"], ["Innings shock, wicket axis (SD)", f"{np.sqrt(Si[1, 1]):.3f}"],
                 ["Cross-team correlation of scoring residuals", f"{sh['C_match'][0][0] / max(sh['C_total'][0][0], 1e-12):.2f} of the innings variance"]]}
    if key == "test":
        fl = json.loads((fmt.export / "sim_params.json").read_text())["flow"]
        out["flow"] = {"rows": [[f"Innings {k}: declared / all innings since 2010", f"{v['declared']} / {v['innings']} (model expects {v['expected']})"]
                                for k, v in fl["decl_rate"].items()]
                       + [["Follow-on enforced when available (since 2010)", f"{fl['follow_on']['enforced']} of {fl['follow_on']['n']}"],
                          ["Mean spell, pace / spin (overs)", " / ".join(f"{np.sum(np.cumprod(np.r_[1, 1 - np.array(h)])[:-1]):.1f}" for h in (fl["spell_hazard"]["pace"], fl["spell_hazard"]["spin"]))]]}

    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [clean(v) for v in x]
        if isinstance(x, (float, np.floating)):
            return None if not np.isfinite(x) else round(float(x), 5)
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, np.bool_):
            return bool(x)
        return x

    (fmt.export / "diagnostics.json").write_text(json.dumps(clean(out), separators=(",", ":")))
    rp = out["replay"]
    print(f"{key}: diagnostics replay matches={rp['matches']} brier={rp['brier']:.4f} (base rate {rp['brier_base_rate']:.4f})")
    for r in rp["rows"]:
        print(f"   {r['metric']}: real {r['actual']:.2f} sim {r['sim']:.2f}")
    print("   PIT", [round(x, 3) for x in rp["pit"]])
    print("   win-prob fifths", [(c["bin"], c["n"], round(c["pred"], 3), round(c["obs"], 3)) for c in rp["result_calibration"]])


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        main(k)
