# %% Model test against Kalshi: full simulator, parameters from earlier data only, told who was active
"""
python -m models.wnba.market_test sim      simulate every game with a Kalshi market (slow, cached)
python -m models.wnba.market_test grade    score the cached simulations against the quotes

This sets player news aside. Each team's active list is the players who appeared (process tier
"oracle_active"); their minutes come from earlier games. Everything else is refitted on data before one of
ten cut-offs a season:
  ratings      prior-informed RAPM (rapm.rating_at), centred on the trailing season of possessions
  skills       every simulator rate projected at the cut-off (skills.project), usage strength refitted
  environment  league points per 100 and possessions per game, recency-weighted (half-life 0.25 season) on
               games before the cut-off, so a 2025 game is simulated in the 2025 scoring environment
Left at their full-sample values (small leaks): four-factor defence and pace terms, home court, the shared
shock sizes, the score effect, the skill and RAPM hyper-parameters.

Scored at the last quote before tip: game winner, every spread strike ("X wins by over s") and every total
strike ("over s"). Bets are one contract at the quoted ask (or 1 - bid) when the model beats the all-in
price by EDGE. Intervals are bootstrapped by game.

Outputs: data/markets/wnba/sim_forecasts.csv.gz, sim_dists.npz; docs/models/wnba/data/market_model_test.json
"""
from __future__ import annotations

import copy
import json
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

from models.wnba.common import CURRENT_SEASON, EXPORT, PROC, ROOT, ZONES, season_bounds, tau, write_json

OUT = ROOT / "data" / "markets" / "wnba"
N_SIMS = 2000
STEP = 0.1
ENV_HL = 0.25
M_LO, M_HI, T_LO, T_HI = -70, 70, 90, 270
FEE, EDGE = 0.07, 0.03
RATE_KEYS = ["usg", "tov", "sfd", "trip3", "and1", "ftp", "ast", "astd", "orb", "drb", "stl", "blk", "pf"] + \
            [f"mix_{z}" for z in ZONES] + [f"fg_{z}" for z in ZONES]


# %% parameters at a cut-off
class Refit:
    def __init__(self):
        from models.wnba import rapm, skills
        self.rapm, self.skills = rapm, skills
        self.prm = json.loads((PROC / "sim_params.json").read_text())
        self.rm = json.loads((PROC / "rapm_meta.json").read_text())
        self.c = rapm.prepare()
        self.f, self.pos, self.bio = skills.load()
        self.sk_meta = json.loads((PROC / "skills_meta.json").read_text())
        games = pd.read_parquet(PROC / "games.parquet").reset_index(drop=True)
        self.bounds = season_bounds(games)
        allp = pd.read_parquet(PROC / "possessions.parquet")
        allp = allp[~allp.is_empty]
        allp["tau"] = tau(allp.season.values, allp.date.values, self.bounds)
        self.env = allp.groupby("game_id").agg(tau=("tau", "first"), pts=("pts", "sum"), n=("pts", "size")).reset_index()

    def environment(self, tc):
        e = self.env[self.env.tau < tc]
        w = 0.5 ** ((tc - e.tau.values) / ENV_HL)
        return float((w * e.pts).sum() / (w * e.n).sum() * 100), float((w * e.n).sum() / w.sum() / 2)

    def at(self, tc):
        from models.wnba.params import usage_strength
        c, rm = self.c, self.rm
        p2 = copy.deepcopy(self.prm)
        b, _ = self.rapm.rating_at(c, tc, rm["H"], rm["H_feat"], rm["lam_prior"], rm.get("spm_alpha", 0.3))
        poss, pidx, P = c["poss"], c["pidx"], c["P"]
        oc, dc = [f"o{k}" for k in range(5)], [f"d{k}" for k in range(5)]
        q = poss[(poss.tau < tc) & (poss.tau >= tc - 1.25)]
        wo = pd.Series(q[oc].values.ravel()).value_counts()
        wd = pd.Series(q[dc].values.ravel()).value_counts()
        O, D = pd.Series(b[:P], index=pidx), pd.Series(b[P:2 * P], index=pidx)
        seen = set(np.unique(q[oc + dc].values))
        O = O - np.average(O.reindex(wo.index).fillna(0), weights=wo.values)
        D = D - np.average(D.reindex(wd.index).fillna(0), weights=wd.values)
        season = int(tc // 1.25)
        years_back = (CURRENT_SEASON - season) + (1.0 - (tc - season * 1.25)) * 0.45
        S = self.skills.project(self.f, self.pos, self.sk_meta["tuned"], self.sk_meta["age_curves"], self.bio, t_cut=tc, age_shift=years_back)
        for p in p2["players"]:
            i = p["id"]
            if i in S.index:
                for k in RATE_KEYS:
                    p[k] = float(S.loc[i, k])
            ok = i in seen
            p["O"], p["D"] = (float(O[i]), float(D[i])) if ok else (-1.0, -0.5)
        # usage strength over the two latest seasons before the cut-off (the function expects them labelled as
        # the current and previous season)
        u = poss[poss.tau < tc]
        u = u[u.season >= u.season.max() - 1]
        usage_strength(p2["players"], u.assign(season=u.season + (CURRENT_SEASON - u.season.max())))
        ortg, pace = self.environment(tc)
        ref = p2["league"]["poss_per_team_game"]
        p2["league"]["ortg"] = ortg
        p2["pace"]["first_play_sec"] *= (ref / pace) ** 1.2
        p2["league"]["poss_per_team_game"] = pace
        p2["_env"] = dict(cut=tc, ortg=ortg, pace=pace)
        return p2


# %% simulate one cut-off's games
def _sim_block(args):
    from models.wnba.sim import simulate
    prm, specs = args
    out = []
    for gid, home, away, neutral in specs:
        r = simulate(prm, home, away, n_sims=N_SIMS, seed=int(gid) % 100000, opts={"neutral": neutral})
        sc = r["score"]
        m, t = sc[:, 0] - sc[:, 1], sc[:, 0] + sc[:, 1]
        mh = np.bincount(np.clip(m, M_LO, M_HI).astype(int) - M_LO, minlength=M_HI - M_LO + 1)
        th = np.bincount(np.clip(t, T_LO, T_HI).astype(int) - T_LO, minlength=T_HI - T_LO + 1)
        out.append((gid, float((m > 0).mean()), float(m.mean()), float(m.std()), float(t.mean()), float(t.std()),
                    float(r["n_poss"].mean() / 2), mh.astype(np.int32), th.astype(np.int32)))
    return out


def run_sims(seasons=(2025, 2026), workers=3):
    from models.wnba import process
    all_games, pg = process.load()
    mk = pd.read_csv(OUT / "kalshi_markets.csv.gz")
    games = all_games[all_games.season.isin(seasons) & all_games.game_id.isin(mk.game_id)]
    L = process.Lineups(all_games, pg)
    R = Refit()
    known = {p["id"] for p in R.prm["players"]}
    blocks, envs = [], []
    for S in seasons:
        cuts = np.arange(S * 1.25, S * 1.25 + 1.0, STEP)
        for i, tc in enumerate(cuts):
            hi = cuts[i + 1] if i + 1 < len(cuts) else tc + 9
            gg = games[(games.season == S) & (games.tau >= tc) & (games.tau < hi)]
            if gg.empty:
                continue
            prm = R.at(tc)
            envs.append(prm.pop("_env"))
            specs = []
            for g in gg.itertuples():
                sp = []
                for t in (g.home, g.away):
                    lu, _ = L.project(int(t), g, g.tip, "oracle_active")
                    lu = {p: m for p, m in (lu or {}).items() if p in known}
                    if len(lu) < 5:
                        sp = None
                        break
                    tot = sum(lu.values())
                    top = set(sorted(lu, key=lu.get, reverse=True)[:5])
                    sp.append({"team": int(t), "players": [{"id": int(p), "min": float(m * 200 / tot), "starter": p in top} for p, m in lu.items()]})
                if sp:
                    specs.append((int(g.game_id), sp[0], sp[1], bool(g.neutral_site) if pd.notna(g.neutral_site) else False))
            blocks.append((prm, specs))
            print(f"  cut {tc:.2f}: {len(specs)} games, env ortg {envs[-1]['ortg']:.1f} pace {envs[-1]['pace']:.1f}", flush=True)
    with Pool(workers) as pool:
        res = [x for blk in pool.imap(_sim_block, blocks) for x in blk]
    F = pd.DataFrame([r[:7] for r in res], columns=["game_id", "p_home", "margin_mean", "margin_sd", "total_mean", "total_sd", "poss"])
    F = F.merge(games[["game_id", "season", "tip", "home", "away", "home_pts", "away_pts"]], on="game_id")
    F.assign(tip=F.tip.astype(str)).round(4).to_csv(OUT / "sim_forecasts.csv.gz", index=False)
    np.savez_compressed(OUT / "sim_dists.npz", game_id=np.array([r[0] for r in res]), margin=np.stack([r[7] for r in res]),
                        total=np.stack([r[8] for r in res]), m_lo=M_LO, t_lo=T_LO, n_sims=N_SIMS)
    (OUT / "sim_environments.json").write_text(json.dumps(envs))
    print(f"market_test sim: {len(F)} games")


# %% grading
def model_probs():
    """P(home margin > x) and P(total > x) per game from the simulated distributions."""
    z = np.load(OUT / "sim_dists.npz")
    n = float(z["n_sims"])
    return ({int(g): h / n for g, h in zip(z["game_id"], z["margin"])}, {int(g): h / n for g, h in zip(z["game_id"], z["total"])},
            int(z["m_lo"]), int(z["t_lo"]))


def p_over(pmf, lo, x):
    """P(value > x) from an integer pmf starting at lo; x is a half-integer strike in practice."""
    k = int(np.floor(x)) + 1 - lo
    return float(pmf[max(k, 0):].sum())


def logloss(p, y):
    p = np.clip(p, 0.01, 0.99)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_by_game(values, games, fn=np.mean, n=1000, seed=3):
    """95% interval of fn over rows, resampling whole games."""
    r = np.random.default_rng(seed)
    idx = pd.Series(np.arange(len(values))).groupby(np.asarray(games)).apply(lambda s: s.values)
    keys = np.arange(len(idx))
    v = np.asarray(values, float)
    out = []
    for _ in range(n):
        pick = np.concatenate([idx.iloc[k] for k in r.choice(keys, len(keys))])
        out.append(fn(v[pick]))
    return [float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))]


def rows_for(kind):
    """One row per market with a usable quote at tip: model probability, market mid, bid/ask, outcome."""
    mk = pd.read_csv(OUT / "kalshi_markets.csv.gz")
    qt = pd.read_csv(OUT / "kalshi_quotes.csv.gz")
    F = pd.read_csv(OUT / "sim_forecasts.csv.gz").set_index("game_id")
    pm, pt, mlo, tlo = model_probs()
    d = mk[mk.kind == kind].merge(qt[qt.horizon == "tip"], on="ticker")
    d = d[d.game_id.isin(F.index) & d.bid.notna() & d.ask.notna() & (d.ask - d.bid <= 0.10)]
    if kind == "ml":
        d = d[d.yes_is_home == True]  # noqa: E712
    out = []
    for r in d.itertuples():
        g = F.loc[r.game_id]
        margin, total = g.home_pts - g.away_pts, g.home_pts + g.away_pts
        if kind == "ml":
            p, y = g.p_home, float(margin > 0)
        elif kind == "spread":
            if pd.isna(r.strike) or r.yes_is_home is None or pd.isna(r.yes_is_home):
                continue
            home = str(r.yes_is_home) == "True"
            # YES = that team wins by more than the strike
            p = p_over(pm[r.game_id], mlo, r.strike) if home else 1 - p_over(pm[r.game_id], mlo, -r.strike - 1e-9)
            y = float(margin > r.strike) if home else float(-margin > r.strike)
        else:
            if pd.isna(r.strike):
                continue
            p, y = p_over(pt[r.game_id], tlo, r.strike), float(total > r.strike)
        out.append(dict(game_id=r.game_id, season=g.season, ticker=r.ticker, strike=r.strike, p=p, bid=r.bid, ask=r.ask,
                        mid=(r.bid + r.ask) / 2, y=y, age_min=r.age_min))
    return pd.DataFrame(out)


def score(d):
    """Model vs market on a set of market rows."""
    if len(d) < 30:
        return None
    lm, lk = logloss(d.p.values, d.y.values), logloss(d.mid.values, d.y.values)
    rec = dict(n_markets=int(len(d)), n_games=int(d.game_id.nunique()), logloss_model=float(lm.mean()), logloss_market=float(lk.mean()),
               logloss_diff=float((lm - lk).mean()), logloss_diff_ci=boot_by_game(lm - lk, d.game_id))
    # does the model add anything to the price? logistic regression of the outcome on both logits
    from sklearn.linear_model import LogisticRegression
    lg = lambda p: np.log(np.clip(p, 0.01, 0.99) / (1 - np.clip(p, 0.01, 0.99)))  # noqa: E731
    X = np.c_[lg(d.mid.values), lg(d.p.values)]
    if d.y.nunique() == 2:
        co = LogisticRegression(C=1e6, max_iter=500).fit(X, d.y.values).coef_[0]
        rec["blend_weights"] = dict(market=float(co[0]), model=float(co[1]))
    # flat bets at the quote, after the fee
    edge_yes = d.p - d.ask - FEE * d.ask * (1 - d.ask)
    edge_no = (1 - d.p) - (1 - d.bid) - FEE * d.bid * (1 - d.bid)
    yes, no = edge_yes > EDGE, (edge_no > EDGE) & ~(edge_yes > EDGE)
    cost = np.where(yes, d.ask + FEE * d.ask * (1 - d.ask), (1 - d.bid) + FEE * d.bid * (1 - d.bid))
    profit = np.where(yes, d.y - cost, (1 - d.y) - cost)
    b = (yes | no).values
    rec["n_bets"] = int(b.sum())
    if b.sum() >= 20:
        roi = lambda i: profit[b][i].sum() / cost[b][i].sum()  # noqa: E731
        ix = np.arange(b.sum())
        g = d.game_id.values[b]
        r = np.random.default_rng(4)
        grp = pd.Series(ix).groupby(g).apply(lambda s: s.values)
        bs = [roi(np.concatenate([grp.iloc[k] for k in r.integers(0, len(grp), len(grp))])) for _ in range(1000)]
        rec.update(roi=float(roi(ix)), roi_ci=[float(np.quantile(bs, 0.025)), float(np.quantile(bs, 0.975))],
                   win_rate=float((profit[b] > 0).mean()), avg_price=float(cost[b].mean()))
    return rec


def implied_line(d):
    """Market's central line per game: the strike where the mid crosses one half (linear interpolation)."""
    out = {}
    for g, x in d.groupby("game_id"):
        x = x.sort_values("strike")
        s, m = x.strike.values, x.mid.values
        if len(x) < 2 or not (m.max() >= 0.5 >= m.min()):
            continue
        j = int(np.argmax(m < 0.5))  # mids fall as the strike rises
        if j == 0:
            continue
        out[g] = s[j - 1] + (m[j - 1] - 0.5) / max(m[j - 1] - m[j], 1e-9) * (s[j] - s[j - 1])
    return pd.Series(out)


def grade():
    F = pd.read_csv(OUT / "sim_forecasts.csv.gz").set_index("game_id")
    margin, total = F.home_pts - F.away_pts, F.home_pts + F.away_pts
    S = dict(n_games_simulated=int(len(F)), n_sims=N_SIMS, settings=dict(fee=FEE, edge=EDGE, env_half_life=ENV_HL, refit_step=STEP),
             sim_bias=dict(margin=float((F.margin_mean - margin).mean()), total=float((F.total_mean - total).mean()),
                           total_by_season={int(s): float((x.total_mean - (x.home_pts + x.away_pts)).mean()) for s, x in F.groupby("season")},
                           margin_rmse=float(np.sqrt(((F.margin_mean - margin) ** 2).mean())),
                           total_rmse=float(np.sqrt(((F.total_mean - total) ** 2).mean()))))
    for kind in ("ml", "spread", "total"):
        d = rows_for(kind)
        if d.empty:
            continue
        blk = dict(all=score(d), by_season={int(s): score(x) for s, x in d.groupby("season")})
        if kind != "ml":
            core = d[(d.mid >= 0.25) & (d.mid <= 0.75)]
            blk["near_the_line"] = dict(all=score(core), by_season={int(s): score(x) for s, x in core.groupby("season")})
            # home-team rows only for the spread line, so the strike axis is one-directional
            line = implied_line(d[d.ticker.str.contains("-") & (d.strike.notna())] if kind == "total" else _home_axis(d))
            real = (total if kind == "total" else margin).reindex(line.index)
            mine = (F.total_mean if kind == "total" else F.margin_mean).reindex(line.index)
            blk["line"] = dict(n_games=int(len(line)), rmse_market=float(np.sqrt(((real - line) ** 2).mean())),
                               rmse_model=float(np.sqrt(((real - mine) ** 2).mean())), corr=float(np.corrcoef(line, mine)[0, 1]),
                               mean_model_minus_market=float((mine - line).mean()),
                               by_season={int(s): dict(n=int((F.season.reindex(line.index) == s).sum()),
                                                       rmse_market=float(np.sqrt(((real - line)[F.season.reindex(line.index) == s] ** 2).mean())),
                                                       rmse_model=float(np.sqrt(((real - mine)[F.season.reindex(line.index) == s] ** 2).mean())),
                                                       model_minus_market=float((mine - line)[F.season.reindex(line.index) == s].mean()))
                                          for s in sorted(F.season.unique())})
        S[kind] = blk
    write_json(EXPORT / "market_model_test.json", S, digits=4)
    return S


def _home_axis(d):
    """Spread rows as P(home margin > x): a 'home by over s' market sits at x = s, an 'away by over s' market
    at x = -s with the complement price."""
    mk = pd.read_csv(OUT / "kalshi_markets.csv.gz").set_index("ticker").yes_is_home.astype(str)
    h = mk.reindex(d.ticker).values == "True"
    return pd.DataFrame(dict(game_id=d.game_id.values, strike=np.where(h, d.strike, -d.strike), mid=np.where(h, d.mid, 1 - d.mid)))


if __name__ == "__main__":
    if "sim" in sys.argv:
        run_sims()
    if "grade" in sys.argv:
        print(json.dumps(grade(), indent=1, default=float)[:6000])
