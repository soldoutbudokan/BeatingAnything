# %% Shot-quality model: xFG / expected points per shot from location + shot type
"""
Gradient-boosted classifier on every FGA 2017-2026, cross-fitted by game (5 folds) so each shot's xFG
comes from a model that never saw that game. Features: distance, angle, raw x/y, 3pt flag, shot family
(layup / dunk / tip / hook / floater / pullup / stepback / fade / bank / jumper / alley-oop), putback flag,
seconds left in period (heaves), season (league trend).
Outputs data/processed/wnba/shots_xfg.parquet (adds xfg, xpts) and shot_model.json (fit metrics).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss

from models.wnba.common import PROC

FAMS = ["dunk", "alleyoop", "tip", "layup", "hook", "floater", "stepback", "pullup", "fade", "bank", "jumper"]


def features(s):
    X = pd.DataFrame({
        "dist": s.dist.clip(0, 60), "ang": s.ang, "x": s.coordinate_x_raw, "y": s.coordinate_y_raw,
        "pts3": s.pts3, "fam": s.shot_family.map({f: i for i, f in enumerate(FAMS)}).fillna(len(FAMS) - 1),
        "putback": s.putback, "secleft": (s.clock_minutes * 60 + s.clock_seconds).clip(0, 60),
        "season": s.season,
    })
    return X


def main(force=False):
    out = PROC / "shots_xfg.parquet"
    if out.exists() and not force:
        print("shot_model: cached")
        return
    s = pd.read_parquet(PROC / "shots.parquet")
    s = s[s.shooter > 0].reset_index(drop=True)
    X = features(s)
    y = s.made.values
    games = s.game_id.unique()
    rng = np.random.default_rng(7)
    fold_of = dict(zip(games, rng.integers(0, 5, len(games))))
    fold = s.game_id.map(fold_of).values
    xfg = np.zeros(len(s))
    for k in range(5):
        tr, te = fold != k, fold == k
        m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=80,
                                           categorical_features=[5], l2_regularization=1.0, random_state=k)
        m.fit(X[tr], y[tr])
        xfg[te] = m.predict_proba(X[te])[:, 1]
    s["xfg"] = xfg
    s["xpts"] = xfg * np.where(s.pts3 == 1, 3, 2)
    s["pts"] = s.made * np.where(s.pts3 == 1, 3, 2)
    base = np.array([y[fold != k].mean() for k in range(5)])[fold]
    zone_base = s.groupby("zone").made.transform("mean")
    metrics = dict(n=int(len(s)), logloss=float(log_loss(y, xfg)), brier=float(brier_score_loss(y, xfg)),
                   logloss_const=float(log_loss(y, base)), logloss_zone=float(log_loss(y, zone_base)),
                   brier_zone=float(brier_score_loss(y, zone_base)),
                   calib=s.assign(b=pd.cut(s.xfg, np.linspace(0, 1, 11))).groupby("b", observed=True).agg(
                       xfg=("xfg", "mean"), fg=("made", "mean"), n=("made", "size")).reset_index(drop=True).round(4).to_dict("list"))
    s.to_parquet(out)
    (PROC / "shot_model.json").write_text(json.dumps(metrics))
    print(f"shot_model: n={len(s)} logloss {metrics['logloss']:.4f} (zone-only {metrics['logloss_zone']:.4f}, const {metrics['logloss_const']:.4f})")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
