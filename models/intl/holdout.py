"""Walk-forward holdout predictions with the adopted configuration.

For each fold the model is trained on deliveries before the cut-off and scores the window after it. The
per-ball logits are kept (holdout_eta.npz): diagnostics read calibration from them and the ratings step sizes
the match and innings shocks on them, out of sample.
Usage: python -m models.intl.holdout odi|test
"""
# %% imports
import sys

import numpy as np
import pandas as pd

from models.intl.config import FORMATS
from models.intl.final_fit import hyper
from models.intl.fit import build_design, fit_model, indices, load, map_env, predict_eta


def main(key):
    fmt = FORMATS[key]
    f = load(key)
    idx = indices(f)
    H, lam = hyper(fmt)
    warm = fmt.proc / "tuning_r1_base.npz"
    W0 = np.load(warm, allow_pickle=True) if warm.exists() else None
    rows, etas, folds = [], [], []
    for k, (lo, hi) in enumerate(fmt.cutoffs):
        lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)
        tr = f["date"] < lo
        te = (f["date"] >= lo) & (f["date"] < hi)
        train = f[tr].reset_index(drop=True)
        test = map_env(train, f[te].reset_index(drop=True))
        w0 = W0[f"W{k}"] if W0 is not None and f"W{k}" in W0 else None
        fitr, D, _ = fit_model(train, fmt, lam, H, train["date"].max(), idx=idx, maxiter=600, tol=1e-9, W0=w0, verbose=True)
        _, Xt = build_design(test, idx, fmt, lam)
        etas.append(predict_eta(Xt, fitr.W).astype(np.float32))
        rows.append(np.flatnonzero(te.to_numpy()))
        folds.append(np.full(int(te.sum()), k, np.int8))
    np.savez(fmt.proc / "holdout_eta.npz", row=np.concatenate(rows), eta=np.vstack(etas), fold=np.concatenate(folds))
    print(f"{key}: holdout rows={sum(len(r) for r in rows):,}")


if __name__ == "__main__":
    main(sys.argv[1])
