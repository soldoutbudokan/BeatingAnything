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
    test = f[f["date"] >= CUTOFF].reset_index(drop=True)
    ref = train["date"].max()
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    done = {r["key"] for r in results}
    for H, lam_over in grid:
        lam = dict(DEFAULT_LAM, **lam_over)
        key = json.dumps([H, lam], sort_keys=True)
        if key in done:
            continue
        t = time.time()
        fitr, D, _ = fit_model(train, cov, lam, H, ref, maxiter=500, idx=idx)
        ev, _ = evaluate(fitr, idx, test, cov)
        r = dict(key=key, half_life=H, lam=lam, iters=int(fitr.res.nit), secs=round(time.time() - t), **ev)
        results.append(r)
        OUT.write_text(json.dumps(results, indent=1))
        print(f"H={H} {lam_over} it={r['iters']} ll_all={ev['ll_all']:.5f} ll_ipl={ev['ll_ipl']:.5f} {r['secs']}s", flush=True)
    return results


def null_baseline():
    """Context-only reference: same model with player terms frozen at zero (huge penalty)."""
    lam = dict(DEFAULT_LAM, bat=1e9, bat_split=1e9, bowl=1e9, bowl_split=1e9)
    return [(2.5, dict(bat=1e9, bat_split=1e9, bowl=1e9, bowl_split=1e9))]


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "1"
    if stage == "1":
        grid = [(H, {}) for H in (1.5, 2.5, 4.0, 7.0)] + null_baseline()
    else:
        H = float(sys.argv[2])
        grid = [(H, dict(bat=b, bowl=b, bat_split=s, bowl_split=s)) for b, s in
                [(75, 400), (300, 400), (150, 200), (150, 800)]]
        grid += [(H, dict(venue=v, venue2=2 * v)) for v in (100, 1000)]
        grid += [(H, dict(cs=c)) for c in (50, 1000)]
    run(grid)
