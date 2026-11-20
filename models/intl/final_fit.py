"""Final fit on all data with the adopted hyper-parameters; saves coefficients and Laplace SDs.

Usage: python -m models.intl.final_fit odi|test [maxiter]
"""
# %% imports
import json
import os
import pickle
import sys

import numpy as np

from models.intl.config import FORMATS, STATIC
from models.intl.fit import fit_model, load


def hyper(fmt):
    """Adopted configuration (tracked, so a fresh clone reproduces the model); defaults until one is adopted."""
    p = STATIC / f"hyper_{fmt.key}.json"
    if p.exists():
        h = json.loads(p.read_text())
        return float(h["half_life"]), {k: v for k, v in h["lam"].items() if v is not None}
    return fmt.default_half_life, dict(fmt.default_lam)


def main(key, maxiter=800, tol=1e-9, out_name="model.pkl", before=None):
    fmt = FORMATS[key]
    f = load(key)
    idx = None
    if before is not None:   # forward-holdout model: same design, trained on deliveries before the cut-off
        from models.intl.fit import indices
        idx = indices(f)
        f = f[f["date"] < before].reset_index(drop=True)
    H, lam = hyper(fmt)
    ref = f["date"].max()
    fitr, D, idx = fit_model(f, fmt, lam, H, ref, idx=idx, maxiter=maxiter, tol=tol, verbose=True)
    sd = 1.0 / np.sqrt(fitr.hessian_diag())
    out = dict(W=fitr.W, sd=sd, blocks=D.blocks, p=D.p, half_life=H, lam=lam, ref_date=str(ref.date()),
               iters=int(fitr.res.nit), loss=float(fitr.res.fun), n=int(fitr.n), idx=idx, fmt=key)
    tmp = fmt.proc / (out_name + ".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(out, fh)
    os.replace(tmp, fmt.proc / out_name)
    print(f"{key}: final fit H={H} iters={out['iters']} n={out['n']:,} p={D.p:,} -> {out_name}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 800)
