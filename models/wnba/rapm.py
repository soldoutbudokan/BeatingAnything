# %% Multi-season RAPM, statistical plus-minus prior, prior-informed RAPM, four-factor RAPM
"""
Model (per possession, points x100):
    y = mu + h*home_off + sum_{i in off5} O_i - sum_{j in def5} D_j + e
O > 0 = better offence, D > 0 = better defence (fewer points allowed).
Weights: recency 0.5**(dtau/H) in 'season time' (see common.tau), x0.5 for garbage time
(|margin| >= 20 in the 4th quarter / OT).
Steps
  1. Tune lambda/H by forward holdout: fit on 2017-2025, score 2026 possessions (MSE).
  2. Long-run RAPM (all seasons, mild recency) -> targets for the box prior (SPM).
  3. SPM: weighted ridge of long-run O and D on per-100 box/pbp/shot-quality features.
  4. Prior-informed RAPM: ridge shrinking toward the SPM prediction (features recency-weighted).
     Prior strength tuned by the same forward holdout (features built from pre-2026 data only).
  5. Four-factor RAPM (eFG on FGA, TOV per poss, ORB per rebound chance, FTA per poss), both ends.
Outputs: data/processed/wnba/rapm_players.parquet, rapm_meta.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import scipy.sparse as sp

from models.wnba.common import PROC, season_bounds, tau, tau_end

CUR = 2026


# %% data
def load():
    poss = pd.read_parquet(PROC / "possessions.parquet")
    poss = poss[~poss.is_empty & poss.lineup_ok].reset_index(drop=True)
    games = pd.read_parquet(PROC / "games.parquet")
    b = season_bounds(games)
    poss["tau"] = tau(poss.season.values, poss.date.values, b)
    poss["garbage"] = (poss.period >= 4) & (poss.margin.abs() >= 20)
    # orb opportunities: own ORBs + 1 if the next possession (other team) started with a defensive rebound
    nxt = poss.groupby("game_id").start_drb.shift(-1).fillna(0)
    poss["orb_opp"] = poss.orb + nxt
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[pg.pid > 0]
    gd = games.set_index("game_id")
    pg["season"] = pg.game_id.map(gd.season)
    pg["date"] = pg.game_id.map(gd.date)
    pg = pg[pg.season.notna()]
    pg["tau"] = tau(pg.season.astype(int).values, pg.date.values, b)
    shots = pd.read_parquet(PROC / "shots_xfg.parquet")
    shots["tau"] = tau(shots.season.values, shots.game_date.values, b)
    return poss, pg, shots, b


def player_index(poss):
    ids = np.unique(poss[[f"o{k}" for k in range(5)] + [f"d{k}" for k in range(5)]].values.ravel())
    ids = ids[ids > 0]
    return pd.Index(ids)


def design(df, pidx, ocol="o", dcol="d"):
    n, P = len(df), len(pidx)
    rows = np.repeat(np.arange(n), 5)
    oc = pidx.get_indexer(df[[f"{ocol}{k}" for k in range(5)]].values.ravel())
    dc = pidx.get_indexer(df[[f"{dcol}{k}" for k in range(5)]].values.ravel())
    X = sp.csr_matrix((np.r_[np.ones(5 * n), -np.ones(5 * n)], (np.r_[rows, rows], np.r_[oc, P + dc])), shape=(n, 2 * P))
    return X


def ridge(X, y, w, lam, extra=None, prior=None, lam_vec=None, return_cov=False):
    """Weighted ridge with unpenalised extra columns (intercept etc.). lam may be scalar or vector."""
    if extra is not None:
        X = sp.hstack([X, sp.csr_matrix(extra)]).tocsr()
    k = X.shape[1]
    ne = 0 if extra is None else extra.shape[1]
    WX = X.multiply(w[:, None]).tocsr()
    A = (X.T @ WX).toarray()
    rhs = WX.T @ y
    L = np.full(k, float(lam)) if lam_vec is None else np.r_[lam_vec, np.zeros(ne)]
    if ne:
        L[-ne:] = 1e-6
    if prior is not None:
        pr = np.r_[prior, np.zeros(ne)]
        rhs = rhs + L * pr
    A[np.diag_indices(k)] += L
    beta = np.linalg.solve(A, rhs)
    if not return_cov:
        return beta
    resid = y - X @ beta
    s2 = float(np.sum(w * resid ** 2) / np.sum(w))
    # effective weight normalisation: weights scaled so that mean weight ~ 1 posterior covariance
    cov_diag = np.diag(np.linalg.inv(A)) * s2
    return beta, cov_diag, s2


def weights(t, t_ref, H, garbage):
    w = 0.5 ** (np.maximum(t_ref - t, 0) / H)
    return w * np.where(garbage, 0.5, 1.0)


# %% features for the box prior
FEATS = ["pts100", "rim100", "smid100", "lmid100", "c3_100", "ab3_100", "fta100", "ast100", "tov100", "orb_pct", "drb_pct",
         "stl100", "blk100", "pf100", "smoe100", "astd_share", "mpg"]


def player_features(pg, shots, t_ref, H, k_shrink=250.0, pids=None):
    """Recency-weighted per-100 features (H=None -> uniform). Shrunk toward the weighted population mean."""
    pg = pg[pg.tau < t_ref]
    w = np.ones(len(pg)) if H is None else 0.5 ** ((t_ref - pg.tau.values) / H)
    g = pg.assign(w=w)
    cols = dict(poss="off_poss", dposs="def_poss", pts="points", fta="fta", ast="ast", tov="turnovers", orb="orb", drb="drb",
                orb_opp="orb_opp", drb_opp="drb_opp", stl="stl", blk="blk", pf="pf_def", sec="sec_on", gp="one")
    g = g.assign(one=((g.minutes.fillna(0) > 0) | (g.sec_on.fillna(0) > 0)).astype(float))
    for z in range(5):
        cols[f"z{z}"] = f"fga_z{z}"
        cols[f"astd{z}"] = f"astd_z{z}"
        cols[f"fgm{z}"] = f"fgm_z{z}"
    agg = {}
    for k, c in cols.items():
        agg[k] = (g[c].fillna(0) * g.w).groupby(g.pid).sum()
    A = pd.DataFrame(agg)
    sw = shots[shots.tau < t_ref]
    ws = np.ones(len(sw)) if H is None else 0.5 ** ((t_ref - sw.tau.values) / H)
    A["smoe"] = ((sw.pts - sw.xpts) * ws).groupby(sw.shooter).sum().reindex(A.index).fillna(0)
    if pids is not None:
        A = A.reindex(pids).fillna(0)
    poss = A.poss.clip(lower=1e-9)
    F = pd.DataFrame(index=A.index)
    F["pts100"] = A.pts / poss * 100
    for z, nm in enumerate(["rim100", "smid100", "lmid100", "c3_100", "ab3_100"]):
        F[nm] = A[f"z{z}"] / poss * 100
    F["fta100"] = A.fta / poss * 100
    F["ast100"] = A.ast / poss * 100
    F["tov100"] = A.tov / poss * 100
    F["orb_pct"] = A.orb / A.orb_opp.clip(lower=1e-9) * 100
    F["drb_pct"] = A.drb / A.drb_opp.clip(lower=1e-9) * 100
    dp = A.dposs.clip(lower=1e-9)
    F["stl100"] = A.stl / dp * 100
    F["blk100"] = A.blk / dp * 100
    F["pf100"] = A.pf / dp * 100
    F["smoe100"] = A.smoe / poss * 100
    fgm = sum(A[f"fgm{z}"] for z in range(5))
    F["astd_share"] = sum(A[f"astd{z}"] for z in range(5)) / fgm.clip(lower=1e-9)
    F["mpg"] = (A.sec / 60 / A.gp.clip(lower=1e-9)).clip(0, 40)
    # shrink toward weighted mean with pseudo-possessions
    n = A.poss.values
    m = (F.mul(n, axis=0).sum() / n.sum())
    m["mpg"] = 8.0  # fringe-player minutes when there is no information
    lam = n / (n + k_shrink)
    F = F.mul(lam, axis=0) + np.outer(1 - lam, m.values)
    F["n_poss"] = A.poss
    return F


def fit_spm(F, target, wts, alpha=1.0):
    X = F[FEATS].values
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    W = wts / wts.mean()
    Zb = np.c_[np.ones(len(Z)), Z]
    A = Zb.T @ (Zb * W[:, None]) + np.diag(np.r_[0, np.full(Z.shape[1], alpha)])
    coef = np.linalg.solve(A, Zb.T @ (W * target))
    return dict(mu=mu, sd=sd, coef=coef)


def predict_spm(m, F):
    Z = (F[FEATS].values - m["mu"]) / m["sd"]
    return m["coef"][0] + Z @ m["coef"][1:]


# %% main fit
def main(force=False):
    out = PROC / "rapm_players.parquet"
    if out.exists() and not force:
        print("rapm: cached")
        return
    poss, pg, shots, bounds = load()
    pidx = player_index(poss)
    P = len(pidx)
    X = design(poss, pidx)
    y = poss.pts.values * 100.0
    SEAS = sorted(poss.season.unique())

    def season_extra(home, season, cap=None):
        season = np.asarray(season)
        if cap is not None:
            season = np.minimum(season, cap)
        return np.c_[np.asarray(home, float), (season[:, None] == np.array(SEAS)[None, :]).astype(float)]

    extra = season_extra(poss.home_off.values, poss.season.values)
    i26 = 1 + SEAS.index(CUR)
    t = poss.tau.values
    meta = {}

    # ---- 1. forward holdout tuning: for test seasons 2024/25/26 train on everything before, score that season
    TEST = (2024, 2025, 2026)
    folds = []
    for S in TEST:
        ts = S * 1.25
        tr, te = t < ts, (t >= ts) & (t < ts + 1.0)
        ex_te = season_extra(poss.home_off.values[te], poss.season.values[te], cap=S - 1)
        folds.append((ts, tr, te, X[tr], sp.hstack([X[te], sp.csr_matrix(ex_te)]).tocsr()))
    mse_base = float(sum(np.sum((y[te] - y[tr].mean()) ** 2) for _, tr, te, _, _ in folds) / sum(te.sum() for _, _, te, _, _ in folds))

    def holdout(H, lam, H_feat=None):
        err, n = 0.0, 0
        for ts, tr, te, Xtr, Xte in folds:
            w = weights(t[tr], ts, H, poss.garbage.values[tr])
            prior = None
            if H_feat is not None:
                Ft = player_features(pg, shots, ts, H_feat, pids=pidx)
                prior = np.r_[predict_spm(spmO, Ft), predict_spm(spmD, Ft)]
            bb = ridge(Xtr, y[tr], w, lam, extra=extra[tr], prior=prior)
            err += float(np.sum((y[te] - Xte @ bb) ** 2))
            n += int(te.sum())
        return err / n

    grid = [dict(H=H, lam=lam, mse=holdout(H, lam)) for H in (0.35, 0.5, 0.75, 1.0, 1.5) for lam in (400, 800, 1500, 3000)]
    gdf = pd.DataFrame(grid)
    best = gdf.loc[gdf.mse.idxmin()]
    H_best, lam_best = float(best.H), float(best.lam)
    meta["rapm_grid"] = gdf.assign(gain_vs_const=mse_base - gdf.mse).round(3).to_dict("records")
    meta["mse_const_holdout"] = mse_base

    # ---- 2. long-run RAPM (targets for SPM): all seasons, slow decay (H=4)
    w_lr = weights(t, tau_end(CUR), 4.0, poss.garbage.values)
    b_lr, cov_lr, s2 = ridge(X, y, w_lr, lam_best, extra=extra, return_cov=True)
    O_lr, D_lr = b_lr[:P], b_lr[P:2 * P]

    # ---- 3. SPM fit on long-run features (uniform-ish H=4 to match)
    F_lr = player_features(pg, shots, tau_end(CUR) + 1e-6, 4.0, pids=pidx)
    nposs_lr = F_lr.n_poss.values
    sel = nposs_lr > 300
    wsp = np.sqrt(nposs_lr[sel])
    best_alpha, spm_cv = None, []
    rng = np.random.default_rng(3)
    fold = rng.integers(0, 5, sel.sum())
    for alpha in (0.3, 3.0, 30.0, 100.0):
        err = 0.0
        for side, tgt in (("O", O_lr[sel]), ("D", D_lr[sel])):
            for k in range(5):
                m = fit_spm(F_lr[sel][fold != k], tgt[fold != k], wsp[fold != k], alpha)
                pr = predict_spm(m, F_lr[sel][fold == k])
                err += np.sum(wsp[fold == k] * (tgt[fold == k] - pr) ** 2)
        spm_cv.append(dict(alpha=alpha, wsse=float(err)))
    best_alpha = min(spm_cv, key=lambda r: r["wsse"])["alpha"]
    spmO = fit_spm(F_lr[sel], O_lr[sel], wsp, best_alpha)
    spmD = fit_spm(F_lr[sel], D_lr[sel], wsp, best_alpha)
    meta["spm_alpha_cv"] = spm_cv
    meta["spm_coef"] = {"features": FEATS, "O": dict(zip(["intercept"] + FEATS, np.round(spmO["coef"], 3).tolist())),
                        "D": dict(zip(["intercept"] + FEATS, np.round(spmD["coef"], 3).tolist()))}
    fitO = predict_spm(spmO, F_lr[sel])
    fitD = predict_spm(spmD, F_lr[sel])
    meta["spm_r2_w"] = dict(
        O=float(1 - np.sum(wsp * (O_lr[sel] - fitO) ** 2) / np.sum(wsp * (O_lr[sel] - np.average(O_lr[sel], weights=wsp)) ** 2)),
        D=float(1 - np.sum(wsp * (D_lr[sel] - fitD) ** 2) / np.sum(wsp * (D_lr[sel] - np.average(D_lr[sel], weights=wsp)) ** 2)))

    # ---- 4. prior-informed RAPM; tune data half-life, feature half-life and prior strength by forward holdout
    grid2 = [dict(H=H, H_feat=Hf, lam=lam, mse=holdout(H, lam, Hf))
             for H in (0.5, 0.75, 1.0) for Hf in (0.5, 1.0, 2.0) for lam in (1500, 3000, 6000)]
    g2 = pd.DataFrame(grid2)
    bp = g2.loc[g2.mse.idxmin()]
    H_rapm, H_feat, lam_prior = float(bp.H), float(bp.H_feat), float(bp.lam)
    meta["prior_rapm_grid"] = g2.assign(gain_vs_const=mse_base - g2.mse).round(3).to_dict("records")
    meta.update(H_plain=H_best, lam_plain=lam_best, H=H_rapm, H_feat=H_feat, lam_prior=lam_prior)

    # pre-2026 fit with the chosen hyper-parameters (used only by diagnostics for an out-of-sample check)
    ts = CUR * 1.25
    trm = t < ts
    Fp = player_features(pg, shots, ts, H_feat, pids=pidx)
    prp = np.r_[predict_spm(spmO, Fp), predict_spm(spmD, Fp)]
    bp_ = ridge(X[trm], y[trm], weights(t[trm], ts, H_rapm, poss.garbage.values[trm]), lam_prior, extra=extra[trm], prior=prp)
    pd.DataFrame({"pid": pidx, "O": bp_[:P], "D": bp_[P:2 * P]}).to_parquet(PROC / "rapm_pre2026.parquet")

    # final fit at the cut-off
    t_end = tau_end(CUR)
    F_now = player_features(pg, shots, t_end + 1e-6, H_feat, pids=pidx)
    prior_now = np.r_[predict_spm(spmO, F_now), predict_spm(spmD, F_now)]
    w = weights(t, t_end, H_rapm, poss.garbage.values)
    b_pi, cov_pi, s2_pi = ridge(X, y, w, lam_prior, extra=extra, prior=prior_now, return_cov=True)
    b_pl, cov_pl, _ = ridge(X, y, w, lam_best, extra=extra, return_cov=True)
    meta["intercept"] = float(b_pi[2 * P + i26])
    meta["season_intercepts"] = {int(S): float(b_pi[2 * P + 1 + i]) for i, S in enumerate(SEAS)}
    meta["home_coef_per100"] = float(b_pi[2 * P])
    # effective sample size for uncertainty: weights are relative; scale covariance by mean weight
    res = pd.DataFrame(index=pidx)
    res["O"], res["D"] = b_pi[:P], b_pi[P:2 * P]
    res["O_sd"], res["D_sd"] = np.sqrt(cov_pi[:P]), np.sqrt(cov_pi[P:2 * P])
    res["O_rapm"], res["D_rapm"] = b_pl[:P], b_pl[P:2 * P]
    res["O_prior"], res["D_prior"] = prior_now[:P], prior_now[P:]
    res["O_longrun"], res["D_longrun"] = O_lr, D_lr
    res["wposs"] = np.asarray(abs(X).T @ w).ravel()[:P] / 1.0  # recency-weighted offensive possessions
    res["wposs_d"] = np.asarray(abs(X).T @ w).ravel()[P:]
    for c in FEATS + ["n_poss"]:
        res[f"f_{c}"] = F_now[c].values

    # ---- 5. four-factor RAPM (plain ridge toward 0, same recency, lambda scaled to outcome variance)
    ff = {}
    # TOV per possession
    ytov = poss.tov.clip(upper=1).values * 100.0
    ff["tov"] = ridge(X, ytov, w, lam_best * 1.0, extra=extra)
    # FTA per possession
    yfta = poss.fta.values * 100.0 / 2.0  # per-100 FT trips-equivalent
    ff["ftr"] = ridge(X, yfta, w, lam_best, extra=extra)
    # ORB per rebound chance (possession-level rate, weighted by chances)
    m = poss.orb_opp.values > 0
    yorb = np.where(m, poss.orb.values / np.maximum(poss.orb_opp.values, 1), 0) * 100.0
    ff["orb"] = ridge(X[m], yorb[m], w[m] * poss.orb_opp.values[m], lam_best, extra=extra[m])
    # eFG per FGA (shot level)
    s = shots[shots.shooter > 0].copy()
    home_sh = s.team_id == s.home_team_id
    H5 = s[[f"h{k}" for k in range(5)]].values
    A5 = s[[f"a{k}" for k in range(5)]].values
    ok = (H5 > 0).all(1) & (A5 > 0).all(1)
    s = s[ok]
    home_sh = home_sh[ok].values
    H5, A5 = H5[ok], A5[ok]
    off5 = np.where(home_sh[:, None], H5, A5)
    def5 = np.where(home_sh[:, None], A5, H5)
    sd = pd.DataFrame(np.c_[off5, def5], columns=[f"o{k}" for k in range(5)] + [f"d{k}" for k in range(5)])
    keep = np.isin(off5, pidx).all(1) & np.isin(def5, pidx).all(1)
    sd, s, home_sh = sd[keep], s[keep], home_sh[keep]
    Xs = design(sd, pidx)
    ws = weights(s.tau.values, t_end, H_rapm, np.zeros(len(s), bool))
    yefg = s.made.values * (1 + 0.5 * s.pts3.values) * 100.0
    exs = season_extra(home_sh, s.season.values)
    ff["efg"] = ridge(Xs, yefg, ws, lam_best * 0.5, extra=exs)
    # shot quality: xPTS allowed / generated (selection) and make-over-expected allowed (contest)
    ff["xpts"] = ridge(Xs, s.xpts.values * 100.0, ws, lam_best, extra=exs)
    ff["moe"] = ridge(Xs, (s.pts - s.xpts).values * 100.0, ws, lam_best * 2, extra=exs)
    for k, b in ff.items():
        res[f"ff_{k}_O"] = b[:P]
        res[f"ff_{k}_D"] = b[P:2 * P]  # D>0 = suppresses the opponent's rate
        meta[f"ff_{k}_intercept"] = float(b[2 * P + i26])
    res.index.name = "pid"
    res.reset_index().to_parquet(out)
    meta["n_players"] = P
    meta["n_possessions"] = int(len(poss))
    meta["resid_var"] = s2_pi
    (PROC / "rapm_meta.json").write_text(json.dumps(meta, default=float))
    print(f"rapm: P={P} poss={len(poss)} H={H_rapm} Hfeat={H_feat} lam={lam_best} lam_prior={lam_prior} spm_alpha={best_alpha} "
          f"spmR2 O={meta['spm_r2_w']['O']:.2f} D={meta['spm_r2_w']['D']:.2f} home={meta['home_coef_per100']:.2f}/100")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
