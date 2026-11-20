"""Career trend layer: a player's level as a moving estimate, in the manner of DARKO.

The joint model (fit.py) gives each player one rating, from deliveries weighted by a single half-life, and one
ageing curve shared by everyone. This layer keeps the joint model for context and lets the player's own level
move. For every delivery it takes the joint model's expectation with the player's individual terms removed
(venue, league, opposition, match situation and the player's prior covariates all stay), sums actual minus
expected per player, competition and month, and runs a Kalman filter over each player's months:

    level_t = phi^dt * level_(t-1) + drift[age band] * dt + noise        noise ~ N(0, q * dt), dt in years
    y_month ~ N(v * level_t, kappa * v)                                  v = model variance of the month's sum

The level is on the model's own scale (a shift in log odds for dismissals and wickets, a tilt of the run
distribution for runs), so a month counts by its information v and not by its deliveries: an innings ends when
the batter is out, and weighting by deliveries reads a first-ball duck as a huge per-ball rate. Four skills, each
with its own parameters: batting runs and dismissals, bowling runs conceded and wickets. Parameters are fitted
by maximum likelihood on the filter's one-step-ahead errors, pooled or separately for Indian and overseas
players. Two uses of the filter are tested against the joint model's rating: on y (the level replaces the rating)
and on y minus the rating's own forecast (the level corrects it).

python -m models.ipl.trend fit 2024-06-01 2023-06-01    joint model as of earlier dates (the 2025 one is holdout.py's)
python -m models.ipl.trend walk 2023-06-01 2024-06-01 2025-06-01    fit the filters before each date, score the year after
python -m models.ipl.trend project                      career series and April 2027 levels from the final model
"""
# %% imports
import pickle
import sys

import numba as nb
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from models.ipl.config import CLASSES, FULL_MEMBERS, PROC, PROJ_DATE
from models.ipl.final_fit import best_hyper
from models.ipl.fit import build_design, fit_model, indices, load, predict_eta, probs_from_eta
from models.ipl.prep import load_dob
from models.ipl.ratings import C, extras_dists, outs_per_row
from models.ipl.team import nationality
from models.ipl.tune import CUTOFF, map_env

BAT_BLOCKS = ("bat", "bat_pp", "bat_death", "bat_spin", "bat_early", "bat_type")   # a batter's individual terms
BOWL_BLOCKS = ("bowl", "bowl_pp", "bowl_death", "bowl_lhb", "bowl_arch")
SKILLS = {"bat_runs": "batter", "bat_outs": "batter", "bowl_runs": "bowler", "bowl_wkts": "bowler"}
AGE_EDGES = [22, 25, 28, 31, 34]   # drift bands: under 22, 22-24, 25-27, 28-30, 31-33, 34 and over
N_BANDS = len(AGE_EDGES) + 1
MIN_BALLS = 60                     # a player's deliveries after the cut-off before his season rate is scored


# %% the joint model as of a date


def cut_path(cutoff):
    return PROC / ("model_holdout.pkl" if cutoff == CUTOFF else f"model_cut_{cutoff.date()}.pkl")


def fit_at(cutoff):
    """The joint model on deliveries before `cutoff`, with the adopted hyper-parameters (as holdout.py)."""
    f, cov = load()
    idx = indices(f)
    train = f[f["date"] < cutoff].reset_index(drop=True)
    H, lam, _ = best_hyper()
    fitr, D, _ = fit_model(train, cov, lam, H, train["date"].max(), maxiter=800, idx=idx, tol=1e-9,
                           checkpoint=PROC / f"cut_{cutoff.date()}_ckpt.npy")
    with open(cut_path(cutoff), "wb") as fh:
        pickle.dump(dict(W=fitr.W, blocks=D.blocks, p=D.p, half_life=H, lam=lam, idx=idx, cutoff=str(cutoff.date()),
                         iters=int(fitr.res.nit), opts=fitr.opts), fh)
    print(f"fit before {cutoff.date()}: iters={fitr.res.nit} n={fitr.n:,}")


# %% deliveries -> one observation per player, match and skill


def without(M, blocks):
    """Coefficients with the named blocks set to zero."""
    W = M["W"].copy()
    for b in blocks:
        if b in M["blocks"]:
            o, labels, _ = M["blocks"][b]
            W[o:o + len(labels)] = 0.0
    return W


def run_values(ex, bowling):
    """Runs per class: off the bat for a batter, conceded for a bowler (as runs_per_row and conceded_per_row)."""
    r = np.zeros(len(CLASSES))
    for c, x in (("r1", 1), ("r2", 2), ("r3", 3), ("r4", 4), ("r6", 6)):
        r[C[c]] = x
    r[C["noball"]] = ex["nb_bat_mean"] + (1.0 if bowling else 0.0)
    r[C["runout"]] = ex["ro_runs_mean"]
    if bowling:
        r[C["wide"]] = ex["wide_mean"]
    return r


def observations(M, f, cov, ex):
    """Long table, one row per skill, player and match: n deliveries, y = actual minus expected without the
    player's own terms, s = the joint model's rating on the same deliveries (its forecast of y), v = the model
    variance of y."""
    _, X = build_design(f, cov, *M["idx"], opts=M["opts"])
    P = probs_from_eta(predict_eta(X, M["W"]))
    cls = f["cls"].astype(str).to_numpy()
    mcode, mids = pd.factorize(f["match_id"])
    match = f.drop_duplicates("match_id").set_index("match_id").loc[mids, ["date", "comp"]]
    out = []
    for blocks, who in ((BAT_BLOCKS, "batter"), (BOWL_BLOCKS, "bowler")):
        P0 = probs_from_eta(predict_eta(X, without(M, blocks)))
        r = run_values(ex, who == "bowler")
        if who == "batter":
            act = np.where(np.isin(cls, ["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), f["runs_bat"].to_numpy(), 0)
            hit = (cls == "wicket") | ((cls == "runout") & (f["player_out"] == f["batter"]).to_numpy())
            h0, h1 = outs_per_row(P0, ex), outs_per_row(P, ex)
            names = ("bat_runs", "bat_outs")
        else:
            act = f["runs_total"].to_numpy() - f["byes"].to_numpy()
            hit = cls == "wicket"
            h0, h1 = P0[:, C["wicket"]], P[:, C["wicket"]]
            names = ("bowl_runs", "bowl_wkts")
        e0, e1 = P0 @ r, P @ r
        per_ball = {names[0]: (act - e0, e1 - e0, P0 @ r ** 2 - e0 ** 2), names[1]: (hit - h0, h1 - h0, h0 * (1 - h0))}
        pcode, pids = pd.factorize(f[who])
        key, inv = np.unique(pcode.astype(np.int64) * len(mids) + mcode, return_inverse=True)
        base = pd.DataFrame({"player": pids[key // len(mids)], "match_id": mids[key % len(mids)],
                             "date": match["date"].to_numpy()[key % len(mids)],
                             "comp": match["comp"].astype(str).to_numpy()[key % len(mids)],
                             "n": np.bincount(inv, minlength=len(key)).astype(float)})
        for skill, (y, s, v) in per_ball.items():
            out.append(base.assign(skill=skill, y=np.bincount(inv, y, len(key)), s=np.bincount(inv, s, len(key)),
                                   v=np.bincount(inv, v, len(key))))
    return pd.concat(out, ignore_index=True)


def groups(matches, players):
    """india | overseas (the other full members) | associate. A player with no country who has played the Syed
    Mushtaq Ali Trophy is Indian."""
    nat, smat = nationality(matches)
    c = nat.reindex(players)
    g = np.where(c == "India", "india", np.where(c.isin(FULL_MEMBERS), "overseas", "associate"))
    g = np.where(c.isna().to_numpy() & np.isin(players, list(smat)), "india", g)
    return pd.Series(g, index=players)


def prepare(obs, matches):
    """Pool a player's matches in one competition and calendar month into one observation, sort each player's
    observations in time and add what the filter reads: first (a player's first observation), dt (years since his
    previous one), band (age band, -1 unknown) and group. An innings ends at a dismissal, so one match's
    information is tied to its own outcome (a first-ball duck is all surprise and almost no information); a month's
    is much less so."""
    d = obs.assign(month=obs["date"].dt.to_period("M"))
    d = (d.groupby(["skill", "player", "comp", "month"], sort=False, observed=True)
          .agg(date=("date", "max"), matches=("n", "size"), n=("n", "sum"), y=("y", "sum"), s=("s", "sum"), v=("v", "sum"))
          .reset_index().drop(columns="month"))
    d = d.sort_values(["skill", "player", "date", "comp"], kind="stable").reset_index(drop=True)
    same = (d["player"] == d["player"].shift()) & (d["skill"] == d["skill"].shift())
    d["first"] = ~same
    d["dt"] = np.where(same, (d["date"] - d["date"].shift()).dt.days / 365.25, 0.0)
    dob = load_dob()
    age = (d["date"] - dob.reindex(d["player"]).to_numpy()).dt.days / 365.25
    d["age"] = age
    d["band"] = np.where(age.isna(), -1, np.searchsorted(AGE_EDGES, age.fillna(0), side="right")).astype(np.int64)
    d["group"] = groups(matches, pd.Index(d["player"].unique())).reindex(d["player"]).to_numpy()
    return d


# %% the filter


@nb.njit(cache=True)
def kalman(first, dt, band, v, y, tau2, q, phi, kappa, m0, drift, pre_m, post_m, post_p):
    """Filter every player's observations in order (rows sorted by player and time). Writes the level expected
    before each one and the level and its variance after it; returns the log likelihood of the one-step-ahead errors."""
    ll, m, p = 0.0, 0.0, 0.0
    for i in range(len(v)):
        if first[i]:
            m, p = m0, tau2
        else:
            g = phi ** dt[i]
            m = g * m + (drift[band[i]] * dt[i] if band[i] >= 0 else 0.0)
            p = g * g * p + q * dt[i]
        pre_m[i] = m
        e = y[i] - v[i] * m
        S = v[i] * v[i] * p + kappa * v[i]
        ll -= 0.5 * (np.log(2 * np.pi * S) + e * e / S)
        k = v[i] * p / S
        m += k * e
        p *= 1.0 - k * v[i]
        post_m[i], post_p[i] = m, p
    return ll


def unpack(x):
    """Optimiser vector -> tau2, q, phi, kappa, m0, drift. Variances are fitted on a log scale and phi on a logit."""
    return np.exp(x[0]), np.exp(x[1]), 1 / (1 + np.exp(-x[2])), np.exp(x[3]), x[4], np.ascontiguousarray(x[5:5 + N_BANDS])


def run_filter(d, x, ycol="y"):
    o = [np.empty(len(d)) for _ in range(3)]
    ll = kalman(*(d[c].to_numpy() for c in ("first", "dt", "band", "v", ycol)), *unpack(x), *o)
    return ll, o


def fit_params(d, ycol="y"):
    """Maximum likelihood on one skill's rows. Levels are rescaled to about one while the optimiser works."""
    scale = float(np.sqrt((d[ycol] ** 2).sum() / (d["v"] ** 2).sum()))
    a = [d[c].to_numpy() for c in ("first", "dt", "band")] + [d["v"].to_numpy() * scale ** 2, d[ycol].to_numpy() * scale]
    o = [np.empty(len(d)) for _ in range(3)]
    x0 = np.concatenate([[0.0, -3.0, 3.0, 0.0, 0.0], np.zeros(N_BANDS)])
    best = None
    for start in (x0, x0 + np.concatenate([[-1.0, -2.0, 1.5, 0.3, 0.0], np.zeros(N_BANDS)])):
        r = minimize(lambda x: -kalman(*a, *unpack(x), *o), start, method="L-BFGS-B",
                     bounds=[(-12, 6), (-16, 4), (-2, 9), (-2, 3), (-5, 5)] + [(-5, 5)] * N_BANDS)
        if best is None or r.fun < best.fun:
            best = r
    x = best.x.copy()   # back to the skill's own units: level = scale * (fitted level)
    x[0] += 2 * np.log(scale)
    x[1] += 2 * np.log(scale)
    x[4:] *= scale
    return x, -best.fun + len(d) * np.log(scale)


def band_names():
    e = AGE_EDGES
    return [f"u{e[0]}"] + [f"{a}-{b - 1}" for a, b in zip(e[:-1], e[1:])] + [f"{e[-1]}+"]


def describe(x, per):
    """Parameters in the skill's units per 100 deliveries (`per` = 100 x the typical variance of one delivery)."""
    tau2, q, phi, kappa, m0, drift = unpack(x)
    return dict(sd_first=per * np.sqrt(tau2), sd_year=per * np.sqrt(q), keep_year=phi, kappa=kappa, m0=per * m0,
                **{f"drift_{b}": per * v for b, v in zip(band_names(), drift)})


# %% walk forward: fit before a date, forecast the following year from each player's level at the date


def frozen_forecast(d, x, cutoff, ycol="y"):
    """Level expected at each match in the year after `cutoff`, from the player's state at his last match before
    it. NaN for a player with no earlier match."""
    tau2, q, phi, kappa, m0, drift = unpack(x)
    tr = d[d["date"] < cutoff]
    _, (_, post_m, _) = run_filter(tr, x, ycol)
    last = tr.assign(m=post_m).groupby("player", sort=False).tail(1).set_index("player")[["m", "date"]]
    te = d[(d["date"] >= cutoff) & (d["date"] < cutoff + pd.DateOffset(years=1))]
    m, t = last["m"].reindex(te["player"]).to_numpy(), last["date"].reindex(te["player"]).to_numpy()
    gap = (te["date"].to_numpy() - t) / np.timedelta64(1, "D") / 365.25
    band = te["band"].to_numpy()
    step = np.where(band >= 0, drift[np.clip(band, 0, None)], 0.0) * gap
    return pd.Series(phi ** gap * m + step, index=te.index)


def fold(cutoff):
    """Observations from the joint model fitted before `cutoff`, and every forecast of the following year."""
    f, cov = load()
    with open(cut_path(cutoff), "rb") as fh:
        M = pickle.load(fh)
    train = f[f["date"] < cutoff].reset_index(drop=True)
    _, ex = extras_dists(train)
    f = pd.concat([train, map_env(train, f[f["date"] >= cutoff].reset_index(drop=True))], ignore_index=True)
    d = prepare(observations(M, f, cov, ex), pd.read_parquet(PROC / "matches.parquet"))
    d = d[d["group"].isin(["india", "overseas"])].reset_index(drop=True)
    d["r"] = d["y"] - d["s"]   # what the joint model's rating leaves over
    params, out = [], []
    for skill in SKILLS:
        k = d[d["skill"] == skill]
        tr = k[k["date"] < cutoff]
        ipl = tr[tr["comp"] == "IPL"]
        per = 100 * ipl["v"].sum() / ipl["n"].sum()
        te = k[(k["date"] >= cutoff) & (k["date"] < cutoff + pd.DateOffset(years=1))].copy()
        for ycol, name in (("y", "level"), ("r", "correction")):
            fits = {g: fit_params(tr if g == "pooled" else tr[tr["group"] == g], ycol) for g in ("pooled", "india", "overseas")}
            for g, (x, ll) in fits.items():
                params.append(dict(cutoff=cutoff.date(), skill=skill, filter=name, fit=g, loglik=ll, **describe(x, per)))
            base = te["s"] if ycol == "r" else 0.0
            te[f"{name}_pooled"] = base + te["v"] * frozen_forecast(k, fits["pooled"][0], cutoff, ycol)
            te[f"{name}_split"] = base + te["v"] * pd.concat([frozen_forecast(k[k["group"] == g], fits[g][0], cutoff, ycol)
                                                                for g in ("india", "overseas")])
        out.append(te.dropna(subset=["level_pooled"]))   # players with a match before the date
    return pd.concat(out).assign(cutoff=cutoff), pd.DataFrame(params)


FORECASTS = ["prior", "level_pooled", "level_split", "correction_pooled", "correction_split"]
STACKS = ["stack_pooled", "stack_split"]


def stack_weights(te, col):
    """Per skill and group, the weight b in rating + b * (filter - rating) that best fits forecast years already
    seen (least squares on the observations, each weighted by 1 / v), kept inside 0 to 1."""
    gap, left = te[col] - te["s"], te["y"] - te["s"]
    g = pd.DataFrame({"skill": te["skill"], "group": te["group"], "num": left * gap / te["v"], "den": gap ** 2 / te["v"]})
    g = g.groupby(["skill", "group"])[["num", "den"]].sum()
    return (g["num"] / g["den"]).clip(0, 1)


def add_stacks(te, past):
    """Blend the rating with each filter's level, with weights learned on `past` forecast years only."""
    te = te.copy()
    for kind in ("pooled", "split"):
        b = stack_weights(past, f"level_{kind}")
        w = pd.MultiIndex.from_frame(te[["skill", "group"]]).map(b).to_numpy()
        te[f"stack_{kind}"] = te["s"] + w * (te[f"level_{kind}"] - te["s"])
    return te


def season_error(te, cols, rng, n_boot=300):
    """Error in a player's rate over the year after a cut-off (per 100 deliveries; players with MIN_BALLS in that
    year), root mean square weighted by deliveries: the joint model's rating, then each forecast in `cols` minus
    it, with a standard error from resampling players."""
    g = te.assign(static=te["s"], prior=0.0).groupby(["cutoff", "player"])[["n", "y", "static"] + cols].sum()
    g = g[g["n"] >= MIN_BALLS]
    w, who = g["n"].to_numpy(), pd.factorize(g.index.get_level_values("player"))[0]
    err = {c: 100 * (g["y"] - g[c]).to_numpy() / w for c in ["static"] + cols}

    def rmse(i):
        return {c: np.sqrt(np.average(e[i] ** 2, weights=w[i])) for c, e in err.items()}
    rows_of = [np.flatnonzero(who == p) for p in range(who.max() + 1)]
    boot = pd.DataFrame([rmse(np.concatenate([rows_of[p] for p in rng.integers(0, len(rows_of), len(rows_of))]))
                         for _ in range(n_boot)])
    full = rmse(np.arange(len(g)))
    row = dict(player_seasons=len(g), balls=int(w.sum()), static=full["static"])
    for c in cols:
        row[c] = full[c] - full["static"]
        row[f"se_{c}"] = float((boot[c] - boot["static"]).std())
    return row


def report(te, cols):
    rng = np.random.default_rng(0)
    rows = []
    for skill in SKILLS:
        k = te[te["skill"] == skill]
        for label, x in (("all T20", k), ("all T20, india", k[k["group"] == "india"]), ("all T20, overseas", k[k["group"] == "overseas"]),
                         ("IPL", k[k["comp"] == "IPL"]), ("IPL, india", k[(k["comp"] == "IPL") & (k["group"] == "india")]),
                         ("IPL, overseas", k[(k["comp"] == "IPL") & (k["group"] == "overseas")])):
            rows.append(dict(skill=skill, sample=label, **season_error(x, cols, rng)))
    return pd.DataFrame(rows)


def walk(cutoffs):
    res = [fold(c) for c in cutoffs]
    params = pd.concat([r[1] for r in res], ignore_index=True)
    folds = [r[0] for r in res]
    for i in range(1, len(folds)):
        folds[i] = add_stacks(folds[i], pd.concat(folds[:i]))
    te = pd.concat(folds, ignore_index=True)
    te.to_parquet(PROC / "trend_walk.parquet", index=False)
    params.to_csv(PROC / "trend_params.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(params.round(3).to_string(index=False))
    for c in cutoffs:
        print(f"year after {c.date()}\n{report(te[te['cutoff'] == c], FORECASTS).round(3).to_string(index=False)}")
    R = report(te, FORECASTS)
    R.to_csv(PROC / "trend_walk.csv", index=False)
    print(f"all {len(cutoffs)} years\n{R.round(3).to_string(index=False)}")
    if len(cutoffs) > 1:
        later = te[te["cutoff"] > cutoffs[0]]
        S = report(later, ["level_pooled", "level_split"] + STACKS)
        S.to_csv(PROC / "trend_stack.csv", index=False)
        print(f"years after the first, with blends weighted on earlier years\n{S.round(3).to_string(index=False)}")
        print(stack_weights(te, "level_split").round(3).unstack().to_string())
    return te, params


# %% projection: every player's level through his career and on the projection date, from the final model


def project(kind="split"):
    """Writes trend_series.parquet (level after each observation) and trend_projection.csv (one row per skill and
    player who appeared in the latest IPL season). Levels are in the skill's units per 100 deliveries in IPL
    conditions, relative to what the joint model expects of a player with his role, experience and age:
      rating   the joint model's own rating over his last two years of deliveries
      now      the filter's level after his last observation
      proj     that level carried to PROJ_DATE (decay toward zero, drift for his age), with its sd
      blend    rating + b * (proj - rating), b from the walk-forward years (trend_walk.parquet)
    `kind`: "split" fits Indian and overseas players separately, "pooled" together."""
    f, cov = load()
    with open(PROC / "model.pkl", "rb") as fh:
        M = pickle.load(fh)
    _, ex = extras_dists(f)
    with open(PROC / "ratings.pkl", "rb") as fh:
        names = pickle.load(fh)["names"]
    d = prepare(observations(M, f, cov, ex), pd.read_parquet(PROC / "matches.parquet"))
    d = d[d["group"].isin(["india", "overseas"])].reset_index(drop=True)
    walked = PROC / "trend_walk.parquet"
    b = stack_weights(pd.read_parquet(walked), f"level_{kind}") if walked.exists() else pd.Series(dtype=float)
    proj, season = pd.Timestamp(PROJ_DATE), f.loc[f["comp"] == "IPL", "date"].dt.year.max()
    ipl = f[(f["comp"] == "IPL") & (f["date"].dt.year == season)]
    team = pd.concat([ipl.drop_duplicates("batter", keep="last").set_index("batter")["bat_team"].astype(str),
                      ipl.drop_duplicates("bowler", keep="last").set_index("bowler")["bowl_team"].astype(str)])
    team = team[~team.index.duplicated()]
    series, rows = [], []
    for skill in SKILLS:
        k = d[d["skill"] == skill]
        ref = k[(k["comp"] == "IPL") & (k["date"] >= proj - pd.DateOffset(years=4))]
        per = 100 * ref["v"].sum() / ref["n"].sum()
        for g in (("india", "overseas") if kind == "split" else ("pooled",)):
            kg = k if g == "pooled" else k[k["group"] == g]
            x, _ = fit_params(kg)
            tau2, q, phi, kappa, m0, drift = unpack(x)
            _, (_, post_m, post_p) = run_filter(kg, x)
            kg = kg.assign(level=per * post_m, sd=per * np.sqrt(post_p))
            series.append(kg[["skill", "player", "date", "comp", "n", "level", "sd"]])
            last = kg.groupby("player", sort=False).tail(1).set_index("player")
            recent = kg[kg["date"] >= kg["date"].max() - pd.DateOffset(years=2)].groupby("player")[["n", "s", "v"]].sum()
            gap = (proj - last["date"]).dt.days / 365.25
            band = np.where(last["age"].isna(), -1, np.searchsorted(AGE_EDGES, (last["age"] + gap / 2).fillna(0), side="right"))
            step = np.where(band >= 0, drift[np.clip(band, 0, None)], 0.0) * gap
            o = pd.DataFrame({"skill": skill, "group": last["group"], "age": last["age"] + gap, "last": last["date"],
                              "balls_2y": recent["n"].reindex(last.index), "rating": per * (recent["s"] / recent["v"]).reindex(last.index),
                              "now": last["level"], "proj": per * (phi ** gap * last["level"] / per + step),
                              "sd": per * np.sqrt(phi ** (2 * gap) * (last["sd"] / per) ** 2 + q * gap)})
            w = pd.MultiIndex.from_arrays([o["skill"], o["group"]]).map(b).to_numpy() if len(b) else np.nan
            o["weight"] = w
            o["blend"] = o["rating"] + w * (o["proj"] - o["rating"])
            rows.append(o[o.index.isin(team.index)])
    out = pd.concat(rows).reset_index(names="player")
    out.insert(1, "name", out["player"].map(names))
    out.insert(2, "team", out["player"].map(team))
    out["change"] = out["blend"] - out["rating"]
    pd.concat(series, ignore_index=True).to_parquet(PROC / "trend_series.parquet", index=False)
    out.to_csv(PROC / "trend_projection.csv", index=False)
    print(f"projection to {proj.date()}: {out['player'].nunique()} players from IPL {season}")
    return out


if __name__ == "__main__":
    if sys.argv[1] == "fit":
        for c in sys.argv[2:]:
            fit_at(pd.Timestamp(c))
    elif sys.argv[1] == "project":
        project(*sys.argv[2:])
    else:
        walk(sorted(pd.Timestamp(c) for c in sys.argv[2:]) or [CUTOFF])
