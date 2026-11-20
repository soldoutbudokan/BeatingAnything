"""Walk-forward tuning of recency half-life, shrinkage strengths and optional blocks (fit quality, not a backtest).

Two folds per format: train on everything before a cut-off, score per-ball log loss on the window after it.
Each variant is compared with the base configuration ball by ball, with a standard error clustered by match.
Round 3 adds team form to the best of rounds 1-2.
Usage: python -m models.intl.tune odi|test [round | adopt]
"""
# %% imports
import json
import sys
import time

import numpy as np
import pandas as pd

from models.intl.config import FORMATS
from models.intl.fit import build_design, fit_model, indices, load, logloss_rows, map_env

NO_PLAYERS = dict(bat=1e9, bat_split=1e9, bat_type=1e9, bowl=1e9, bowl_split=1e9)
TEAM_FORM_WALKS = (100, 300, 30, 1000)


def grid(fmt, rnd):
    H = fmt.default_half_life
    if rnd == 1:
        # ordered so the variants round 2 depends on most come first
        g = [("base", H, {}), ("no player terms", H, NO_PLAYERS), ("half-life 9", 9.0, {}), ("half-life 14", 14.0, {}),
             ("season walk tighter", H, dict(rw=800)), ("no other-format prior", H, dict(xf=None)),
             ("team prior tighter", H, dict(team=30)), ("venue tighter", H, dict(venue=1000, venue2=2000))]
        if fmt.key == "odi":
            g += [("chase x wickets in hand", H, dict(chase_w=30.0)), ("no old-powerplay terms", H, dict(pp_old=None))]
        else:
            g += [("match-state tighter", H, dict(sit=10.0)), ("match-state looser", H, dict(sit=1.0))]
        g += [("half-life 3", 3.0, {}), ("season walk looser", H, dict(rw=50)), ("venue looser", H, dict(venue=100, venue2=200)),
              ("players looser", H, dict(bat=20, bowl=50)), ("players tighter", H, dict(bat=80, bowl=200)),
              ("splits looser", H, dict(bat_split=50, bowl_split=50, bat_type=75)),
              ("splits tighter", H, dict(bat_split=300, bowl_split=300, bat_type=450))]
        return g
    if rnd == 3:
        # round 3: the best of rounds 1-2 plus team form, at four strengths of the year-to-year walk
        prev = [r for k in (1, 2) for r in json.loads((fmt.proc / f"tuning_r{k}.json").read_text()) if r["lam"].get("bat", 0) < 1e8]
        best = min(prev, key=lambda r: r["ll"])
        over = dict({k: None for k in fmt.default_lam if k not in best["lam"]}, **best["lam"])
        return [(f"team form, walk {w}", best["half_life"], dict(over, tf=30.0, rw_tf=float(w))) for w in TEAM_FORM_WALKS]
    # round 2: everything round 1 supported, taken together, then a few steps further along the same axes
    r1 = {r["name"]: r for r in json.loads((fmt.proc / "tuning_r1.json").read_text())}
    better = lambda n: n in r1 and r1[n].get("d_vs_base", 0) < -1.5 * r1[n].get("d_se", 1)
    not_worse = lambda n: n in r1 and r1[n].get("d_vs_base", 1) <= 0.5 * r1[n].get("d_se", 0)
    hl = [r for n, r in r1.items() if n == "base" or n.startswith("half-life")]
    H2 = min(hl, key=lambda r: r["ll"])["half_life"]
    over = {}
    for n, o in (("season walk tighter", dict(rw=800)), ("season walk looser", dict(rw=50)),
                 ("venue tighter", dict(venue=1000, venue2=2000)), ("venue looser", dict(venue=100, venue2=200)),
                 ("team prior tighter", dict(team=30)), ("players tighter", dict(bat=80, bowl=200)),
                 ("players looser", dict(bat=20, bowl=50)), ("splits tighter", dict(bat_split=300, bowl_split=300, bat_type=450)),
                 ("splits looser", dict(bat_split=50, bowl_split=50, bat_type=75)), ("match-state tighter", dict(sit=10.0)),
                 ("match-state looser", dict(sit=1.0)), ("chase x wickets in hand", dict(chase_w=30.0))):
        if better(n):
            over.update(o)
    for n, k in (("no other-format prior", "xf"), ("no old-powerplay terms", "pp_old")):
        if not_worse(n):   # a block that does not pay for itself is left out
            over[k] = None
    g = [("combined", H2, dict(over))]
    if over.get("rw") == 800:   # the tighter walk won in round 1: try one step further
        g.append(("combined, season walk 3000", H2, dict(over, rw=3000)))
    return g


def run(key, rnd=1, extra=None):
    fmt = FORMATS[key]
    out = fmt.proc / f"tuning_r{rnd}.json"
    f = load(key)
    idx = indices(f)
    results = json.loads(out.read_text()) if out.exists() else []
    done = {r["name"] for r in results}
    todo = [g for g in (extra or grid(fmt, rnd)) if g[0] not in done]
    if not todo:
        return results
    folds = []
    for lo, hi in fmt.cutoffs:
        lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)
        train = f[f["date"] < lo].reset_index(drop=True)
        test = map_env(train, f[(f["date"] >= lo) & (f["date"] < hi)].reset_index(drop=True))
        folds.append((train, test))
    base_ll, base_W = None, [None] * len(folds)
    if "base" in done or rnd > 1:   # reload the round-1 base losses for paired comparisons (and as a warm start)
        cache = np.load(fmt.proc / "tuning_r1_base.npz", allow_pickle=True)
        base_ll = [cache[f"ll{k}"] for k in range(len(folds))]
        base_W = [cache[f"W{k}"] for k in range(len(folds))]
    for name, H, over in todo:
        lam = {k: v for k, v in dict(fmt.default_lam, **over).items() if v is not None}
        t = time.time()
        lls, its, probs = [], [], {}
        for k, (train, test) in enumerate(folds):
            fitr, D, _ = fit_model(train, fmt, lam, H, train["date"].max(), idx=idx, maxiter=400 if rnd == 1 else 600,
                                   tol=1e-7 if rnd == 1 else 1e-9, W0=base_W[k])
            _, Xt = build_design(test, idx, fmt, lam)
            ll, P = logloss_rows(Xt, test["y"].to_numpy(), fitr.W)
            lls.append(ll)
            probs[f"P{k}"] = P.astype(np.float32)
            its.append(int(fitr.res.nit))
            if name == "base":
                base_W[k] = fitr.W.copy()
        if name == "base":
            base_ll = lls
            np.savez(fmt.proc / "tuning_r1_base.npz", **{f"ll{k}": v for k, v in enumerate(lls)},
                     **{f"W{k}": v for k, v in enumerate(base_W)})
        r = dict(name=name, half_life=H, lam=lam, iters=its, secs=round(time.time() - t),
                 ll=float(np.concatenate(lls).mean()), ll_folds=[float(x.mean()) for x in lls],
                 n_balls=[int(len(x)) for x in lls])
        if base_ll is not None and name != "base":
            d = np.concatenate(lls) - np.concatenate(base_ll)
            mid = np.concatenate([t_["match_id"].to_numpy() for _, t_ in folds])
            g = pd.DataFrame({"m": mid, "d": d}).groupby("m")["d"].agg(["sum", "size"])
            nm = len(g)
            r["d_vs_base"] = float(d.mean())
            r["d_se"] = float(np.sqrt(nm / (nm - 1) * np.sum((g["sum"] - d.mean() * g["size"]) ** 2)) / len(d))
            r["n_matches"] = int(nm)
        if rnd == 3:   # per-ball probabilities, for calibration by team
            np.savez_compressed(fmt.proc / f"tuning_r3_{name.replace(', ', '_').replace(' ', '_')}.npz", **probs)
        results.append(r)
        out.write_text(json.dumps(results, indent=1))
        print(f"{key} r{rnd} {name}: ll={r['ll']:.5f} folds={[round(x, 5) for x in r['ll_folds']]} "
              f"d={r.get('d_vs_base', 0):+.5f}+/-{r.get('d_se', 0):.5f} it={its} {r['secs']}s", flush=True)
    return results


def adopt(key):
    """Write the configuration with the best holdout score to models/intl/static/hyper_<format>.json."""
    from models.intl.config import STATIC
    fmt = FORMATS[key]
    rows = []
    for rnd in (1, 2, 3):
        p = fmt.proc / f"tuning_r{rnd}.json"
        if p.exists():
            rows += [dict(r, round=rnd) for r in json.loads(p.read_text()) if r["lam"].get("bat", 0) < 1e8]
    best = min(rows, key=lambda r: r["ll"])
    out = {"half_life": best["half_life"], "lam": best["lam"],
           "note": (f"Adopted: round {best['round']} '{best['name']}', walk-forward log loss {best['ll']:.5f} "
                    f"({best.get('d_vs_base', 0):+.5f} +/- {best.get('d_se', 0):.5f} against the base). "
                    "Evidence: Diagnostics sheet, tuning table.")}
    (STATIC / f"hyper_{key}.json").write_text(json.dumps(out, indent=1))
    print(f"{key}: adopted {best['name']} (round {best['round']}) H={best['half_life']} ll={best['ll']:.5f}")
    return out


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "adopt":
        adopt(sys.argv[1])
    else:
        run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1)
