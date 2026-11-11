# %% DARKO-style skill projections for every rate the simulator needs
"""
For each rate r = num/den (per player):
    p_hat = (sum_g w_g num_g + k * p0_pos) / (sum_g w_g den_g + k),   w_g = 0.5 ** ((t_cut - tau_g) / H)
then an age adjustment in logit space: logit(p) += C(age_now) - C(age_data), where C is the integrated
season-over-season age delta curve (delta method, harmonic-mean weights, linear in age, players with known
birth dates only) and age_data is the decay*den weighted mean age of the observations.
p0 is the recency-weighted (H=0.5) mean of the player's prior group before the cut-off: position (G/F/C) x
role tier (<12, 12-24, 24+ minutes per game played, decayed, before the cut-off), or position only -
whichever wins the holdout for that rate (tuned['prior']).
H (half-life in season-time, see common.tau) and k (pseudo-denominator) are tuned per rate on a forward
holdout: cut-offs at the start and middle of 2024, 2025 and 2026, target = the next half season,
loss = binomial deviance. Uncertainty: sd = sqrt(p(1-p)/(n_eff + k)).
Outputs: data/processed/wnba/skills.parquet, skills_meta.json
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from models.wnba.common import PROC, ZONES, expit, logit, season_bounds, tau, tau_end

CUR = 2026

# name: (numerator expr, denominator expr, k0 scale, description)
RATES = {
    "usg": ("used", "off_poss", 200.0, "plays used (FGA + non-and-one FT trips + TOV) per team possession on court"),
    "tov": ("turnovers", "used", 100.0, "turnovers per play used"),
    "sfd": ("trips_sf", "used", 100.0, "shooting-foul FT trips drawn (not and-ones) per play used"),
    "trip3": ("ft_trips3", "trips_sf", 20.0, "share of shooting-foul trips that are 3-shot"),
    "and1": ("and1", "fgm", 50.0, "and-ones per made FG"),
    "ftp": ("ftm", "fta", 60.0, "free-throw %"),
    "ast": ("ast", "tm_fgm", 100.0, "assists per teammate made FG while on court"),
    "astd": ("astd", "fgm", 50.0, "share of own made FGs that were assisted"),
    "orb": ("orb", "orb_opp", 100.0, "offensive rebounds per own-team miss while on court"),
    "drb": ("drb", "drb_opp", 100.0, "defensive rebounds per opponent miss while on court"),
    "stl": ("stl", "def_poss", 400.0, "steals per defensive possession"),
    "blk": ("blk", "opp_fga_on", 300.0, "blocks per opponent FGA while on court"),
    "pf": ("pf_def", "def_poss", 400.0, "personal (non-offensive, non-technical) fouls per defensive possession"),
}
for z, zn in enumerate(ZONES):
    RATES[f"mix_{zn}"] = (f"fga_z{z}", "fga", 50.0, f"share of FGA from {zn}")
    RATES[f"fg_{zn}"] = (f"fgm_z{z}", f"fga_z{z}", 40.0, f"FG% from {zn}")

H_GRID = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
K_MULT = (0.0625, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)


def load():
    pg = pd.read_parquet(PROC / "player_games.parquet")
    games = pd.read_parquet(PROC / "games.parquet")
    b = season_bounds(games)
    pg = pg[(pg.pid > 0) & pg.game_id.isin(games.game_id)].copy()
    gd = games.set_index("game_id")
    pg["season"] = pg.game_id.map(gd.season).astype(int)
    pg["date"] = pg.game_id.map(gd.date)
    pg["tau"] = tau(pg.season.values, pg.date.values, b)
    f = pg.fillna({c: 0 for c in pg.columns if pg[c].dtype.kind == "f"})
    f["fga"] = sum(f[f"fga_z{z}"] for z in range(5))
    f["fgm"] = sum(f[f"fgm_z{z}"] for z in range(5))
    f["astd"] = sum(f[f"astd_z{z}"] for z in range(5))
    f["trips_sf"] = f.ft_trips2 + f.ft_trips3
    f["used"] = f.fga + f.trips_sf + f.turnovers
    f["tm_fgm"] = (f.team_fgm_on - f.fgm).clip(lower=0)
    bio = pd.read_parquet(PROC / "players_bio.parquet").set_index("pid")
    posmap = f.groupby("pid").athlete_position_abbreviation.agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else "F")
    pos = posmap.str[0].map({"G": "G", "F": "F", "C": "C"}).fillna("F")
    pos.update(bio.pos_group)
    f["pos"] = f.pid.map(pos).fillna("F")
    dob = bio.dob.dropna()
    f["age"] = (pd.to_datetime(f.date) - f.pid.map(dob)).dt.days / 365.25
    return f, pos, bio


def era_factor(f, num, den, t_cut):
    """League-environment adjustment: each season's numerators are scaled by ref/p_season, where p_season is
    the league rate in that season (data before t_cut only) and ref the league rate over the half season
    before t_cut. A veteran's history is thus expressed in today's environment (e.g. the 2026 whistle)."""
    m = f.tau.values < t_cut
    d = pd.DataFrame({"s": f.season.values[m], "n": f[num].values[m], "d": f[den].values[m], "t": f.tau.values[m]})
    ps = d.groupby("s").n.sum() / d.groupby("s").d.sum().clip(lower=1e-9)
    rec = d[d.t >= t_cut - 0.5]
    ref = rec.n.sum() / max(rec.d.sum(), 1e-9)
    fac = (ref / ps.clip(lower=1e-9)).clip(0.5, 2.0)
    return fac


def decayed(f, num, den, t_cut, H, era=False):
    m = f.tau.values < t_cut
    w = 0.5 ** ((t_cut - f.tau.values[m]) / H)
    g = f.pid.values[m]
    nv = f[num].values[m]
    if era:
        fac = era_factor(f, num, den, t_cut)
        nv = np.minimum(nv * pd.Series(f.season.values[m]).map(fac).fillna(1.0).values, f[den].values[m])
    N = pd.Series(w * nv).groupby(g).sum()
    D = pd.Series(w * f[den].values[m]).groupby(g).sum()
    return N, D


ROLE_TIERS = (12.0, 24.0)


def groups_at(f, pos, t_cut):
    """Prior group = position x role tier, the tier from decayed (H=0.5) minutes per game played before t_cut,
    shrunk toward 8 mpg with 5 pseudo-games (players without data -> 'lo'). Fringe players are worse than
    their position average on most skills, so a position-only prior over-projects them."""
    m = (f.tau.values < t_cut) & (f.minutes.fillna(0).values > 0)
    w = 0.5 ** ((t_cut - f.tau.values[m]) / 0.5)
    g = f.pid.values[m]
    mins = pd.Series(w * f.minutes.fillna(0).values[m]).groupby(g).sum()
    gp = pd.Series(w).groupby(g).sum()
    mpg = (mins + 8.0 * 5) / (gp + 5)
    tier = pd.Series(np.where(mpg < ROLE_TIERS[0], "lo", np.where(mpg < ROLE_TIERS[1], "mid", "hi")), index=mpg.index)
    allp = pos.index.union(tier.index)
    return pos.reindex(allp).fillna("F") + "_" + tier.reindex(allp).fillna("lo")


def pos_prior(f, num, den, t_cut, grp=None):
    m = f.tau.values < t_cut
    w = 0.5 ** ((t_cut - f.tau.values[m]) / 0.5)
    key = f.pos.values[m] if grp is None else f.pid.map(grp).fillna("F_lo").values[m]
    d = pd.DataFrame({"pos": key, "n": w * f[num].values[m], "d": w * f[den].values[m]})
    s = d.groupby("pos")[["n", "d"]].sum()
    p = (s.n / s.d.clip(lower=1e-9)).clip(1e-4, 1 - 1e-4)
    return p


def binom_dev(y, n, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (n - y) * np.log(1 - p)).sum()


# %% tuning
def tune(f, pos):
    cuts = []
    for S in (2024, 2025, 2026):
        cuts += [S * 1.25, S * 1.25 + 0.5]
    res = {}
    for r, (num, den, k0, _) in RATES.items():
        rows = []
        targets = []
        for c in cuts:
            m = (f.tau.values >= c) & (f.tau.values < c + 0.5)
            ty = pd.Series(f[num].values[m]).groupby(f.pid.values[m]).sum()
            tn = pd.Series(f[den].values[m]).groupby(f.pid.values[m]).sum()
            ty, tn = ty[tn > 0], tn[tn > 0]
            gm = groups_at(f, pos, c)
            pr = pos_prior(f, num, den, c, gm)
            targets.append((c, ty, tn, pr, gm))
        base = sum(binom_dev(ty.values, tn.values, gm.reindex(ty.index).map(pr).fillna(pr.mean()).values) for c, ty, tn, pr, gm in targets)
        pr_pos = [pos_prior(f, num, den, c) for c, *_ in targets]
        base_pos = sum(binom_dev(ty.values, tn.values, pos.reindex(ty.index).map(pp).fillna(pp.mean()).values)
                       for (c, ty, tn, pr, gm), pp in zip(targets, pr_pos))
        for H in H_GRID:
            sums = [decayed(f, num, den, c, H) for c, *_ in targets]
            for km in K_MULT:
                k = k0 * km
                loss = 0.0
                for ptype in ("role", "position"):
                    loss = 0.0
                    for (c, ty, tn, pr, gm), (N, D), pp in zip(targets, sums, pr_pos):
                        if ptype == "role":
                            p0 = gm.reindex(ty.index).map(pr).fillna(pr.mean()).values
                        else:
                            p0 = pos.reindex(ty.index).map(pp).fillna(pp.mean()).values
                        n_ = N.reindex(ty.index).fillna(0).values
                        d_ = D.reindex(ty.index).fillna(0).values
                        p = (n_ + k * p0) / (d_ + k)
                        loss += binom_dev(ty.values, tn.values, p)
                    rows.append(dict(H=H, k=k, prior=ptype, loss=loss))
        g = pd.DataFrame(rows)
        b = g.loc[g.loss.idxmin()]
        # naive comparison: season-to-date raw rate (H=inf, k->0 with fallback to prior)
        res[r] = dict(H=float(b.H), k=float(b.k), prior=str(b.prior), loss=float(b.loss), loss_prior_only=float(base),
                      gain_vs_prior_pct=float(100 * (base_pos - b.loss) / base_pos),
                      gain_vs_group_prior_pct=float(100 * (base - b.loss) / base),
                      group_prior_gain_vs_position_pct=float(100 * (base_pos - base) / base_pos),
                      n_target=float(sum(tn.sum() for _, _, tn, _, _ in targets)))
    return res


# %% age curves (delta method on player-seasons with known DOB)
def age_curves(f):
    out = {}
    s = f[f.age.notna()].groupby(["pid", "season"])
    for r, (num, den, k0, _) in RATES.items():
        a = s.agg(n=(num, "sum"), d=(den, "sum"), age=("age", "mean")).reset_index()
        a = a[a.d > 0]
        a["lp"] = logit((a.n + 0.5) / (a.d + 1.0))
        nxt = a.copy()
        nxt["season"] -= 1
        j = a.merge(nxt, on=["pid", "season"], suffixes=("", "_n"))
        if len(j) < 30:
            out[r] = dict(a=0.0, b=0.0)
            continue
        w = 1 / (1 / j.d + 1 / j.d_n)
        # shrink noisy rate deltas: weight also capped so a few big-sample players don't dominate
        w = np.minimum(w, np.quantile(w, 0.9))
        dl = (j.lp_n - j.lp).clip(-1.5, 1.5)
        x = j.age - 27.0
        Xm = np.c_[np.ones(len(x)), x]
        beta = np.linalg.lstsq(Xm * np.sqrt(w.values)[:, None], dl.values * np.sqrt(w.values), rcond=None)[0]
        out[r] = dict(a=float(beta[0]), b=float(beta[1]), n_pairs=int(len(j)))
    return out


def curve_integral(c, age):
    """C(age) = integral_{27}^{age} (a + b (x-27)) dx; delta per year at age x."""
    x = np.asarray(age, float) - 27.0
    return c["a"] * x + 0.5 * c["b"] * x ** 2


# %% final projections
def project(f, pos, tuned, curves, bio, t_cut=None, age_shift=0.0):
    """Projections at t_cut (default: end of 2026). age_shift = years to subtract from cut-off ages."""
    t_cut = tau_end(CUR) + 1e-6 if t_cut is None else t_cut
    pids = pd.Index(sorted(set(f.pid.unique()) | set(bio.index)))
    age_now = bio.age.reindex(pids) - age_shift
    P = {}
    P["pos_group"] = pos.reindex(pids).fillna(bio.pos_group.reindex(pids)).fillna("F")
    for r, (num, den, k0, _) in RATES.items():
        H, k = tuned[r]["H"], tuned[r]["k"]
        N, D = decayed(f, num, den, t_cut, H)
        if tuned[r].get("prior", "position") == "role":
            gm = groups_at(f, pos, t_cut)
            pr = pos_prior(f, num, den, t_cut, gm)
            p0 = gm.reindex(pids).fillna(P["pos_group"] + "_lo").map(pr).fillna(pr.mean()).values
        else:
            pr = pos_prior(f, num, den, t_cut)
            p0 = P["pos_group"].map(pr).fillna(pr.mean()).values
        n_ = N.reindex(pids).fillna(0).values
        d_ = D.reindex(pids).fillna(0).values
        p = (n_ + k * p0) / (d_ + k)
        # age adjustment
        m = (f.tau.values < t_cut) & f.age.notna().values
        w = 0.5 ** ((t_cut - f.tau.values[m]) / H) * f[den].values[m]
        agedata = pd.Series(w * f.age.values[m]).groupby(f.pid.values[m]).sum() / pd.Series(w).groupby(f.pid.values[m]).sum().clip(lower=1e-9)
        ad = agedata.reindex(pids)
        adj = curve_integral(curves[r], age_now.values) - curve_integral(curves[r], ad.values)
        adj = np.where(np.isfinite(adj), np.clip(adj, -0.4, 0.4), 0.0)
        # age adjustment shrinks with the share of the estimate that is data (prior is age-neutral)
        share = d_ / (d_ + k)
        p_adj = expit(logit(p) + adj * share)
        P[r] = p_adj
        P[f"{r}_raw"] = np.where(d_ > 0, n_ / np.maximum(d_, 1e-9), np.nan)
        P[f"{r}_n"] = d_
        P[f"{r}_sd"] = np.sqrt(p_adj * (1 - p_adj) / (d_ + k))
        P[f"{r}_prior"] = p0
    P = pd.DataFrame(P, index=pids)
    # renormalise the zone mix
    mix = P[[f"mix_{z}" for z in ZONES]].values
    P[[f"mix_{z}" for z in ZONES]] = mix / mix.sum(1, keepdims=True)
    P.index.name = "pid"
    return P


def main(force=False):
    out = PROC / "skills.parquet"
    if out.exists() and not force:
        print("skills: cached")
        return
    f, pos, bio = load()
    tuned = tune(f, pos)
    curves = age_curves(f)
    P = project(f, pos, tuned, curves, bio)
    P.reset_index().to_parquet(out)
    meta = dict(tuned=tuned, age_curves=curves, rates={k: v[3] for k, v in RATES.items()})
    (PROC / "skills_meta.json").write_text(json.dumps(meta))
    g = np.mean([v["gain_vs_prior_pct"] for v in tuned.values()])
    print(f"skills: {len(P)} players, {len(RATES)} rates, mean holdout deviance gain vs position prior {g:.2f}%")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
