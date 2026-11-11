"""Final fit on all data with the tuned hyper-parameters; saves coefficients and Laplace SDs."""
# %% imports
import json
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.fit import DEFAULT_LAM, build_design, fit_model, indices, load, predict_eta, probs_from_eta


def best_hyper():
    p = PROC / "tuning.json"
    if not p.exists():
        return 2.5, DEFAULT_LAM, None
    res = [r for r in json.loads(p.read_text()) if r["lam"]["bat"] < 1e8]
    r = min(res, key=lambda r: r["ll_all"])
    return r["half_life"], r["lam"], r


# %% fit
def main(maxiter=600):
    f, cov = load()
    H, lam, r = best_hyper()
    ref = f["date"].max()
    fitr, D, idx = fit_model(f, cov, lam, H, ref, maxiter=maxiter)
    hd = fitr.hessian_diag()
    sd = 1.0 / np.sqrt(hd)
    out = dict(W=fitr.W, sd=sd, blocks=D.blocks, p=D.p, half_life=H, lam=lam, ref_date=str(ref.date()),
               iters=int(fitr.res.nit), loss=float(fitr.res.fun), n=int(fitr.n), idx=idx)
    with open(PROC / "model.pkl", "wb") as fh:
        pickle.dump(out, fh)
    print(f"final fit H={H} iters={out['iters']} n={out['n']:,} p={D.p:,}")


if __name__ == "__main__":
    main()
