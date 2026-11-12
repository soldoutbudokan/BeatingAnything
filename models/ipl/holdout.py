"""Forward-holdout model: same design and hyper-parameters as the final fit, trained on deliveries before
the tuning cut-off (1 June 2025). Used for out-of-sample diagnostics (per-ball, player-level, match-level)."""
# %% imports
import pickle

import numpy as np
import pandas as pd

from models.ipl.config import CLASSES, PROC
from models.ipl.final_fit import best_hyper
from models.ipl.fit import build_design, fit_model, indices, load, predict_eta, probs_from_eta
from models.ipl.tune import CUTOFF, map_env


def main():
    f, cov = load()
    idx = indices(f)
    train = f[f["date"] < CUTOFF].reset_index(drop=True)
    test = map_env(train, f[f["date"] >= CUTOFF].reset_index(drop=True))
    H, lam, _ = best_hyper()
    fitr, D, _ = fit_model(train, cov, lam, H, train["date"].max(), maxiter=800, idx=idx, tol=1e-9)
    sd = 1.0 / np.sqrt(fitr.hessian_diag())
    with open(PROC / "model_holdout.pkl", "wb") as fh:
        pickle.dump(dict(W=fitr.W, sd=sd, blocks=D.blocks, p=D.p, half_life=H, lam=lam,
                         ref_date=str(train["date"].max().date()), iters=int(fitr.res.nit), loss=float(fitr.res.fun),
                         n=int(fitr.n), idx=idx, cutoff=str(CUTOFF.date())), fh)
    _, Xt = build_design(test, cov, *idx)
    P = probs_from_eta(predict_eta(Xt, fitr.W))
    out = pd.DataFrame(P.astype("float32"), columns=[f"p_{c}" for c in CLASSES])
    for c in ("y", "match_id", "innings", "runs_total", "batter", "bowler", "phase"):
        out[c] = test[c].to_numpy()
    out["comp"] = test["comp"].astype(str).to_numpy()
    out.to_parquet(PROC / "holdout_pred.parquet", index=False)
    y = out["y"].to_numpy()
    ll = -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))
    ipl = out["comp"].to_numpy() == "IPL"
    print(f"holdout fit iters={fitr.res.nit} ll_all={ll.mean():.5f} ll_ipl={ll[ipl].mean():.5f}")


if __name__ == "__main__":
    main()
