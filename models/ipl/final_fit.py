"""Final fit on all data with the tuned hyper-parameters; saves coefficients and Laplace SDs."""
# %% imports
import json
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.fit import DEFAULT_LAM, build_design, fit_model, indices, load, predict_eta, probs_from_eta


def best_hyper():
    # the latest search on the current design takes precedence (round 3 = block tests, round 2 = shrinkage)
    p = next((q for q in (PROC / "tuning_r3.json", PROC / "tuning_r2.json", PROC / "tuning.json") if q.exists()), None)
    if p is None:
        return 2.5, DEFAULT_LAM, None
    res = [r for r in json.loads(p.read_text()) if r["lam"]["bat"] < 1e8]
    r = min(res, key=lambda r: r["ll_ipl"] + r["ll_all"])  # IPL holdout and all-T20 holdout weighted equally
    return r["half_life"], r["lam"], r


# %% fit
def main(maxiter=1000):
    f, cov = load()
    H, lam, r = best_hyper()
    ref = f["date"].max()
    fitr, D, idx = fit_model(f, cov, lam, H, ref, maxiter=maxiter, tol=1e-10,
                             checkpoint=PROC / "final_fit_ckpt.npy")
    hd = fitr.hessian_diag()
    sd = 1.0 / np.sqrt(hd)
    out = dict(W=fitr.W, sd=sd, blocks=D.blocks, p=D.p, half_life=H, lam=lam, ref_date=str(ref.date()),
               iters=int(fitr.res.nit), loss=float(fitr.res.fun), n=int(fitr.n), idx=idx,
               opts=getattr(fitr, "opts", None))
    with open(PROC / "model.pkl.tmp", "wb") as fh:
        pickle.dump(out, fh)
    import os
    os.replace(PROC / "model.pkl.tmp", PROC / "model.pkl")
    (PROC / "final_fit_ckpt.npy").unlink(missing_ok=True)
    print(f"final fit H={H} iters={out['iters']} n={out['n']:,} p={D.p:,}")


if __name__ == "__main__":
    main()
