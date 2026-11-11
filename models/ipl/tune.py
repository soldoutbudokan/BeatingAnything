"""Forward-holdout tuning of time-decay half-life and shrinkage strengths (fit quality, not a backtest)."""
# %% imports
import json
import sys
import time

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.fit import (DEFAULT_LAM, build_design, fit_model, indices, load, predict_eta,
                            probs_from_eta)

CUTOFF = pd.Timestamp("2025-06-01")
OUT = PROC / "tuning.json"


def map_env(train, test):
    """Unseen league-seasons in the holdout get the league's latest training season environment
    (exactly what a projection does: next season inherits the current season's environment)."""
    last = train.sort_values("date").groupby("comp", observed=True)["comp_season"].last().astype(str)
    seen = set(train["comp_season"].astype(str).unique())
    cs = test["comp_season"].astype(str)
    new = [c if c in seen else last.get(c.split("|")[0], c) for c in cs]
    test = test.copy()
    test["comp_season"] = pd.Categorical(new)
    return test


def evaluate(fitr, idx, test, cov):
    D, Xt = build_design(test, cov, *idx)
    P = probs_from_eta(predict_eta(Xt, fitr.W))
    y = test["y"].to_numpy()
    ll = -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))
    ipl = (test["comp"].astype(str) == "IPL").to_numpy()
    return dict(ll_all=float(ll.mean()), ll_ipl=float(ll[ipl].mean()), n_test=int(len(y)), n_ipl=int(ipl.sum())), P


def run(grid):
    f, cov = load()
    idx = indices(f)
    train = f[f["date"] < CUTOFF].reset_index(drop=True)
    test = map_env(train, f[f["date"] >= CUTOFF].reset_index(drop=True))
    ref = train["date"].max()
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    done = {r["key"] for r in results}
    for g in grid:
        H, lam_over = g[0], g[1]
        tol = g[2] if len(g) > 2 else 1e-7
        lam = dict(DEFAULT_LAM, **lam_over)
        key = json.dumps([H, lam] + ([tol] if tol != 1e-7 else []), sort_keys=True)
        if key in done:
            continue
        t = time.time()
        fitr, D, _ = fit_model(train, cov, lam, H, ref, maxiter=1000 if tol < 1e-7 else 500, idx=idx, tol=tol)
        ev, _ = evaluate(fitr, idx, test, cov)
        r = dict(key=key, half_life=H, lam=lam, tol=tol, iters=int(fitr.res.nit), secs=round(time.time() - t), **ev)
        results.append(r)
        OUT.write_text(json.dumps(results, indent=1))
        print(f"H={H} {lam_over} it={r['iters']} ll_all={ev['ll_all']:.5f} ll_ipl={ev['ll_ipl']:.5f} {r['secs']}s", flush=True)
    return results


def null_baseline():
    """Context-only reference: same model with player terms frozen at zero (huge penalty)."""
    lam = dict(DEFAULT_LAM, bat=1e9, bat_split=1e9, bowl=1e9, bowl_split=1e9)
    return [(2.5, dict(bat=1e9, bat_split=1e9, bowl=1e9, bowl_split=1e9))]


def best_H():
    res = [r for r in json.loads(OUT.read_text()) if r["lam"]["bat"] < 1e8]
    return min(res, key=lambda r: r["ll_ipl"] + r["ll_all"])["half_life"]


def stage2_grid(H=None):
    H = H or best_H()
    grid = [(H, dict(bat=b, bowl=b)) for b in (75, 300)]
    grid += [(H, dict(bat_split=s, bowl_split=s)) for s in (200, 800)]
    grid += [(H, dict(venue=100, venue2=200)), (H, dict(cs=50))]
    return grid


def stage3_grid(H=4.0):
    """Finer search around the stage-2 optimum, then the same config fitted to full convergence
    (the final fit is run to convergence, so the holdout score of that setting is what we report)."""
    return [(H, dict(bat=40, bowl=40, bat_split=200, bowl_split=200)),
            (H, dict(bat=20, bowl=20, bat_split=200, bowl_split=200)),
            (H, dict(bat=40, bowl=40, bat_split=100, bowl_split=100))]


def stage3_converged(H=4.0):
    res = [r for r in json.loads(OUT.read_text()) if r["lam"]["bat"] < 1e8 and r.get("tol", 1e-7) == 1e-7]
    best = min(res, key=lambda r: r["ll_ipl"] + r["ll_all"])
    over = {k: best["lam"][k] for k in ("bat", "bowl", "bat_split", "bowl_split", "venue", "venue2", "cs")}
    return [(best["half_life"], over, 1e-10)]


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "1"
    if stage == "1":
        grid = [(H, {}) for H in (4.0, 2.5, 6.0)] + null_baseline()
    elif stage == "2":
        grid = stage2_grid(float(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif stage == "3":
        grid = stage3_grid()
    else:
        grid = stage3_converged()
    run(grid)
