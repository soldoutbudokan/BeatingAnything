# %% Diagnostics: does the simulator reproduce reality in aggregate? out-of-sample fit of the components
"""
1. Re-simulate every 2025-2026 game (regular season + playoffs) with the players who actually played,
   their actual minutes (scaled to 200) and actual starters, using the end-of-2026 parameters
   (so this is a calibration check, not an out-of-sample test). Pool the simulated games and compare with
   the real games: total and margin mean/SD, possessions, OT rate, home win rate, distribution of
   individual scoring for high-usage players, teammate scoring correlation.
2. Out-of-sample: skill projections (forward holdout deviance vs position prior), RAPM (possession MSE),
   and bottom-up team ratings fitted on data before 2026 predicting 2026 game margins from the actual
   minutes played.
Output: docs/models/wnba/data/diagnostics.json (+ data/processed/wnba/diag_sims.parquet)
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd

from models.wnba.common import EXPORT, PROC, write_json
from models.wnba.sim import SI, Team, load_params, simulate


def game_specs(prm, pg, gid, home, away):
    known = {p["id"] for p in prm["players"]}
    specs = []
    for tid in (home, away):
        d = pg[(pg.game_id == gid) & (pg.team_id == tid) & (pg.minutes.fillna(0) > 0) & pg.pid.isin(known)]
        if len(d) < 5:
            return None
        m = d.minutes.values.astype(float)
        m = m * 200.0 / m.sum()
        specs.append({"team": int(tid), "players": [{"id": int(i), "min": float(x), "starter": bool(s)}
                                                     for i, x, s in zip(d.pid, m, d.starter.fillna(False))]})
    return specs


def sim_history(prm, n_sims=300, seasons=(2025, 2026)):
    games = pd.read_parquet(PROC / "games.parquet")
    games = games[games.season.isin(seasons)].dropna(subset=["home_pts"])
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[pg.game_id.isin(games.game_id)]
    rows, prow = [], []
    t0 = time.time()
    for k, g in enumerate(games.itertuples()):
        sp = game_specs(prm, pg, g.game_id, g.home, g.away)
        if sp is None:
            continue
        r = simulate(prm, sp[0], sp[1], n_sims=n_sims, seed=int(g.game_id) % 100000,
                     opts={"neutral": bool(g.neutral_site) if pd.notna(g.neutral_site) else False})
        sc = r["score"]
        rows.append(pd.DataFrame({"game_id": g.game_id, "h": sc[:, 0], "a": sc[:, 1],
                                  "ot": (r["quarters"][:, 4:].sum((1, 2)) > 0), "poss": r["n_poss"] / 2}))
        for side, T in ((0, r["home"]), (1, r["away"])):
            off = 0 if side == 0 else r["home"].n
            for i in range(T.n):
                prow.append(pd.DataFrame({"game_id": g.game_id, "pid": int(T.ids[i]), "team": T.tid, "sim": np.arange(n_sims),
                                          "pts": r["box"][SI["pts"], :, off + i].astype(np.int16),
                                          "reb": (r["box"][SI["orb"], :, off + i] + r["box"][SI["drb"], :, off + i]).astype(np.int16),
                                          "ast": r["box"][SI["ast"], :, off + i].astype(np.int16),
                                          "min": (r["box"][SI["sec"], :, off + i] / 60).astype(np.float32)}))
    S = pd.concat(rows)
    PS = pd.concat(prow)
    return games, S, PS, time.time() - t0


def corr_pairs(df, val="pts", min_n=15):
    """Mean within-team correlation of teammates' values over common games (df: game_id, pid, team, key, val)."""
    out = []
    for t, d in df.groupby("team"):
        w = d.pivot_table(index="key", columns="pid", values=val)
        cols = [c for c in w.columns if w[c].notna().sum() >= min_n]
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                x = w[[cols[i], cols[j]]].dropna()
                if len(x) >= min_n and x.iloc[:, 0].std() > 0 and x.iloc[:, 1].std() > 0:
                    out.append(np.corrcoef(x.iloc[:, 0], x.iloc[:, 1])[0, 1])
    return float(np.mean(out)) if out else None, len(out)


def main(force=False, n_sims=300):
    out = EXPORT / "diagnostics.json"
    if out.exists() and not force:
        print("diagnostics: cached")
        return
    prm = load_params()
    games, S, PS, secs = sim_history(prm, n_sims=n_sims)
    S.to_parquet(PROC / "diag_sims.parquet")
    used = games[games.game_id.isin(S.game_id.unique())]
    real_tot = used.home_pts + used.away_pts
    real_mar = used.home_pts - used.away_pts
    sim_tot = S.h + S.a
    sim_mar = S.h - S.a
    poss = pd.read_parquet(PROC / "possessions.parquet")
    poss = poss[poss.game_id.isin(used.game_id) & ~poss.is_empty]
    real_poss = poss.groupby("game_id").size() / 2
    D = {}
    D["aggregate"] = dict(
        n_games=int(len(used)), n_sims_per_game=n_sims,
        total_mean=[float(real_tot.mean()), float(sim_tot.mean())], total_sd=[float(real_tot.std()), float(sim_tot.std())],
        margin_mean=[float(real_mar.mean()), float(sim_mar.mean())], margin_sd=[float(real_mar.std()), float(sim_mar.std())],
        abs_margin_mean=[float(real_mar.abs().mean()), float(sim_mar.abs().mean())],
        home_win=[float((real_mar > 0).mean()), float((sim_mar > 0).mean())],
        ot_rate=[float((used.nper > 4).mean()), float(S.ot.mean())],
        poss_per_team=[float(real_poss.mean()), float(S.poss.mean())],
        note="[real, simulated]; simulated = pooled single-game draws using actual players/minutes per game")
    # per-season split
    seas = {}
    for y in (2025, 2026):
        gi = used[used.season == y].game_id
        r_ = used[used.season == y]
        s_ = S[S.game_id.isin(gi)]
        seas[str(y)] = dict(total_mean=[float((r_.home_pts + r_.away_pts).mean()), float((s_.h + s_.a).mean())],
                            total_sd=[float((r_.home_pts + r_.away_pts).std()), float((s_.h + s_.a).std())],
                            margin_sd=[float((r_.home_pts - r_.away_pts).std()), float((s_.h - s_.a).std())])
    D["by_season"] = seas
    # histogram of totals and margins (real vs sim)
    bins_t = np.arange(110, 245, 5)
    bins_m = np.arange(-50, 55, 5)
    D["total_hist"] = dict(edges=bins_t.tolist(), real=np.histogram(real_tot, bins_t, density=True)[0].tolist(),
                           sim=np.histogram(sim_tot, bins_t, density=True)[0].tolist())
    D["margin_hist"] = dict(edges=bins_m.tolist(), real=np.histogram(real_mar, bins_m, density=True)[0].tolist(),
                            sim=np.histogram(sim_mar, bins_m, density=True)[0].tolist())
    # individual scoring: high-usage players (projected usg >= 0.24) in games where they played >= 25 min
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[pg.game_id.isin(used.game_id) & (pg.minutes.fillna(0) >= 25)]
    usg = {p["id"]: p["usg"] for p in prm["players"]}
    hi = pg[pg.pid.map(usg).fillna(0) >= 0.24]
    keys = set(zip(hi.game_id, hi.pid))
    ps = PS[[k in keys for k in zip(PS.game_id, PS.pid)]]
    D["star_scoring"] = dict(n_player_games=int(len(hi)), n_players=int(hi.pid.nunique()),
                             mean_pts=[float(hi.points.mean()), float(ps.pts.mean())],
                             sd_pts=[float(hi.points.std()), float(ps.pts.std())],
                             share_20plus=[float((hi.points >= 20).mean()), float((ps.pts >= 20).mean())],
                             share_30plus=[float((hi.points >= 30).mean()), float((ps.pts >= 30).mean())],
                             share_10minus=[float((hi.points < 10).mean()), float((ps.pts < 10).mean())])
    # per-player scoring calibration: actual mean vs simulated mean across these games, top usage players
    cmp = hi.groupby("pid").agg(name=("athlete_display_name", "last"), games=("points", "size"), real=("points", "mean"))
    cmp["sim"] = ps.groupby("pid").pts.mean()
    cmp = cmp[cmp.games >= 15].sort_values("real", ascending=False).head(25)
    D["star_scoring_by_player"] = cmp.reset_index().round(2).to_dict("records")
    # teammate correlation (pooled over games, minutes >= 20 in reality / sim)
    pg2 = pd.read_parquet(PROC / "player_games.parquet")
    pg2 = pg2[pg2.game_id.isin(used.game_id) & (pg2.minutes.fillna(0) >= 20) & (pg2.season == 2026)]
    real_c, n_rc = corr_pairs(pg2.assign(key=pg2.game_id, team=pg2.team_id.astype(int), pts=pg2.points), "pts", 15)
    ps2 = PS[(PS["min"] >= 20) & PS.game_id.isin(pg2.game_id)].copy()
    ps2 = ps2[ps2.sim < 20]
    ps2["key"] = ps2.game_id.astype(str) + "_" + ps2.sim.astype(str)
    sim_c, n_sc = corr_pairs(ps2, "pts", 100)
    # within-game (same matchup) correlation from the simulator only
    wg = []
    for gid, d in PS[PS.game_id.isin(pg2.game_id.unique()[:120])].groupby("game_id"):
        for t, dd in d.groupby("team"):
            w = dd.pivot_table(index="sim", columns="pid", values="pts")
            mins = dd.groupby("pid")["min"].mean()
            cols = [c for c in w.columns if mins.get(c, 0) >= 20]
            if len(cols) >= 2:
                c = np.corrcoef(w[cols].values.T)
                wg.append(c[np.triu_indices(len(cols), 1)].mean())
    D["teammate_pts_corr"] = dict(real_across_games=real_c, n_real_pairs=n_rc, sim_across_games=sim_c, n_sim_pairs=n_sc,
                                  sim_within_game=float(np.mean(wg)) if wg else None)
    # ---- out-of-sample components
    sk = json.loads((PROC / "skills_meta.json").read_text())
    D["skills_holdout"] = {k: dict(H=v["H"], k=v["k"], deviance_gain_vs_position_prior_pct=v["gain_vs_prior_pct"]) for k, v in sk["tuned"].items()}
    rm = json.loads((PROC / "rapm_meta.json").read_text())
    D["rapm_holdout"] = dict(mse_const=rm["mse_const_holdout"], best_plain=min(rm["rapm_grid"], key=lambda r: r["mse"]),
                             best_prior=min(rm["prior_rapm_grid"], key=lambda r: r["mse"]),
                             spm_r2_weighted=rm["spm_r2_w"], note="possession points x100, test seasons 2024-26, train on prior seasons")
    D["team_ratings_oos_2026"] = team_oos(prm)
    D["shot_model"] = json.loads((PROC / "shot_model.json").read_text())
    D["lineup_reconstruction"] = json.loads((PROC / "recon.json").read_text())
    D["sim_seconds"] = secs
    write_json(out, D, digits=4)
    a = D["aggregate"]
    print(f"diagnostics: {a['n_games']} games; total {a['total_mean'][0]:.1f}/{a['total_mean'][1]:.1f} sd {a['total_sd'][0]:.1f}/{a['total_sd'][1]:.1f}; "
          f"margin sd {a['margin_sd'][0]:.1f}/{a['margin_sd'][1]:.1f}; home win {a['home_win'][0]:.3f}/{a['home_win'][1]:.3f}; "
          f"OT {a['ot_rate'][0]:.3f}/{a['ot_rate'][1]:.3f}; poss {a['poss_per_team'][0]:.1f}/{a['poss_per_team'][1]:.1f}")


def team_oos(prm):
    """Ratings fitted on data before 2026 -> predict each 2026 game margin from actual minutes."""
    pre = pd.read_parquet(PROC / "rapm_pre2026.parquet").set_index("pid")
    poss = pd.read_parquet(PROC / "possessions.parquet")
    p25 = poss[(poss.season == 2025) & ~poss.is_empty]
    wo = pd.Series(p25[[f"o{k}" for k in range(5)]].values.ravel()).value_counts()
    wd = pd.Series(p25[[f"d{k}" for k in range(5)]].values.ravel()).value_counts()
    O = pre.O - np.average(pre.O.reindex(wo.index).fillna(0), weights=wo.values)
    Dd = pre.D - np.average(pre.D.reindex(wd.index).fillna(0), weights=wd.values)
    # unseen players (rookies / new): fringe prior -> use replacement-ish -1.0 / -0.5
    games = pd.read_parquet(PROC / "games.parquet")
    g = games[(games.season == 2026)].dropna(subset=["home_pts"])
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[pg.game_id.isin(g.game_id) & (pg.minutes.fillna(0) > 0)]
    pg["O"] = pg.pid.map(O).fillna(-1.0)
    pg["D"] = pg.pid.map(Dd).fillna(-0.5)
    pg["w"] = pg.minutes / pg.groupby(["game_id", "team_id"]).minutes.transform("sum") * 5
    agg = pg.groupby(["game_id", "team_id"]).apply(lambda d: pd.Series({"O": (d.w * d.O).sum(), "D": (d.w * d.D).sum()}), include_groups=False)
    hca = prm["context"]["hca_pts"]
    P = prm["league"]["poss_per_team_game"]
    pred, real, base_prev = [], [], []
    # previous-season team net rating per game (point differential / game in 2025) as a naive baseline
    g25 = games[games.season == 2025].dropna(subset=["home_pts"])
    d25 = pd.concat([pd.Series((g25.home_pts - g25.away_pts).values, index=g25.home.values),
                     pd.Series((g25.away_pts - g25.home_pts).values, index=g25.away.values)]).groupby(level=0).mean()
    for r in g.itertuples():
        try:
            h, a = agg.loc[(r.game_id, r.home)], agg.loc[(r.game_id, r.away)]
        except KeyError:
            continue
        neth = h.O + h.D
        neta = a.O + a.D
        pred.append((neth - neta) * P / 100 + (0 if r.neutral_site else hca))
        real.append(r.home_pts - r.away_pts)
        base_prev.append(0.5 * (d25.get(r.home, 0) - d25.get(r.away, 0)) + hca)
    pred, real, base_prev = map(np.array, (pred, real, base_prev))
    rmse = lambda x: float(np.sqrt(np.mean((real - x) ** 2)))  # noqa: E731
    slope = float(np.polyfit(pred, real, 1)[0])
    return dict(n_games=int(len(real)), rmse_model=rmse(pred), rmse_hca_only=rmse(np.full(len(real), hca)),
                rmse_prev_season_diff=rmse(base_prev), corr_model=float(np.corrcoef(pred, real)[0, 1]),
                win_acc_model=float(((pred > 0) == (real > 0)).mean()), calibration_slope=slope,
                note="ratings fit only on 2017-2025 data; uses each 2026 game's actual minutes; no market data")


if __name__ == "__main__":
    main(force="--force" in sys.argv, n_sims=int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 300)
