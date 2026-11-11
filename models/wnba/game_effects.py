# %% Shared game-level random effects, sized from data
"""
Re-simulate 2026 games (actual players/minutes, shared shocks switched off) and compare residuals:
  efficiency: sigma_e^2 = cov(real home PPP resid, real away PPP resid) - mean within-game sim cov
              (residual = real game value - simulated mean for that game; the two teams' residuals share
              officiating / conditions / shooting-night effects that a possession sim treats as independent)
  whistle:    sigma_FTA^2 = cov(real home FTA resid, real away FTA resid) - sim within-game cov,
              converted to a log FT-trip-rate SD via the mean team FTA
  pace:       sigma_p^2 = var(real possessions resid) - (sim within-game var + var of the sim mean error)
              (estimated, floored at 0)
Writes data/processed/wnba/game_effects.json and the sim settings eff_shock_sd (per 100 possessions),
whistle_sd and pace_shock_sd into sim_params.json.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from models.wnba.calib import resim
from models.wnba.common import PROC
from models.wnba.sim import load_params


def main(force=False, n_games=200, n_sims=200):
    out = PROC / "game_effects.json"
    prm = load_params()
    if out.exists() and not force:
        ge = json.loads(out.read_text())
    else:
        p0 = json.loads(json.dumps(prm))
        p0["sim"].update(eff_shock_sd=0.0, whistle_sd=0.0, pace_shock_sd=0.0)
        games = pd.read_parquet(PROC / "games.parquet")
        g = games[games.season == 2026].dropna(subset=["home_pts"])
        g = g.sample(min(n_games, len(g)), random_state=11)
        P, G = resim(p0, g, n_sims=n_sims, keep_draws=False)
        gi = g.set_index("game_id")
        poss = pd.read_parquet(PROC / "possessions.parquet")
        rp = poss[~poss.is_empty].groupby("game_id").size() / 2
        rows = []
        for x in G:
            gid = x["game_id"]
            h, a, ps = x["h"].astype(float), x["a"].astype(float), x["poss"]
            eh, ea = h / ps, a / ps
            rows.append(dict(game_id=gid, mh=h.mean(), ma=a.mean(), mp=ps.mean(), meh=eh.mean(), mea=ea.mean(),
                             cov_e=np.cov(eh, ea)[0, 1], var_p=ps.var()))
        D = pd.DataFrame(rows).set_index("game_id")
        R = rp.reindex(D.index)
        reh = gi.home_pts.reindex(D.index) / R - D.meh
        rea = gi.away_pts.reindex(D.index) / R - D.mea
        cov_real = float(np.cov(reh, rea)[0, 1])
        cov_sim = float(D.cov_e.mean())
        var_e = max(cov_real - cov_sim, 0.0)
        # FTA
        t = P.groupby(["game_id", "team"]).agg(s=("sim_fta", "sum"), a=("act_fta", "sum")).reset_index()
        t["home"] = t.team.values == gi.home.reindex(t.game_id).values
        t["r"] = t.a - t.s
        w = t.pivot(index="game_id", columns="home", values="r").dropna()
        cov_fta = float(np.cov(w[True], w[False])[0, 1])
        mean_fta = float(t.s.mean())
        whistle_sd = float(np.sqrt(max(cov_fta, 0.0)) / mean_fta)
        # pace
        rres = (R - D.mp)
        var_p_extra = float(rres.var() - D.var_p.mean())
        pace_sd = float(np.sqrt(max(var_p_extra, 0.0)) / D.mp.mean())
        ge = dict(n_games=int(len(D)), n_sims=n_sims, ppp_resid_cov_real=cov_real, ppp_within_cov_sim=cov_sim,
                  eff_shock_sd_per100=float(np.sqrt(var_e) * 100), fta_resid_cov_real=cov_fta, mean_team_fta=mean_fta,
                  whistle_sd=whistle_sd, poss_resid_var_real=float(rres.var()), poss_within_var_sim=float(D.var_p.mean()),
                  pace_shock_sd=pace_sd, ppp_resid_corr_real=float(np.corrcoef(reh, rea)[0, 1]))
        out.write_text(json.dumps(ge, indent=1))
    prm["sim"].update(eff_shock_sd=ge["eff_shock_sd_per100"], whistle_sd=ge["whistle_sd"], pace_shock_sd=ge["pace_shock_sd"])
    (PROC / "sim_params.json").write_text(json.dumps(prm))
    print(f"game_effects: eff shock sd {ge['eff_shock_sd_per100']:.2f}/100, whistle sd {ge['whistle_sd']:.3f}, "
          f"pace sd {ge['pace_shock_sd']:.3f} (n={ge['n_games']})")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
