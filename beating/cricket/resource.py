"""Fitted resource table Z(u, w) for chase pressure and DLS-style revised targets (plan 7.6).

Method. Z(u, w) = Z0(w) (1 - exp(-b(w) u)) is the expected number of runs a side scores from a state with
u legal balls remaining and w wickets lost to the end of its innings (Duckworth and Lewis's 1998 form). It
is fitted per (family, gender), T20 (six-ball overs only, so not the Hundred) and ODI, on first innings of
matches dated before 2023-01-01 and frozen there, because the chase feature and both engines use it at
every later cutoff. Innings enter only when nothing reduced them: the scheduled length is the family's
standard (120 / 300 balls), the length known before every ball is that standard, innings 1 was not cut
and no revised target or rain method is recorded, the match was not awarded, and the innings ended all
out or with its full allocation bowled. One state per legal-ball position (the first delivery there) with
u = the ingest's `balls_remaining` and w = `inn_wkts`; the target is runs from that delivery to the end of
the innings (deliveries plus pre-innings penalties). States are weighted 0.5 ** (age / 4 years) at the
cutoff, so the table reflects recent scoring, and summed into (u, w) cells; Z0(w), b(w) for w = 0..9 come
from weighted least squares on the cell means (scipy least_squares, Z0 > 0, b > 0). Z(u, 10) = 0.

Table. P[u][w] = floor(1000 Z(u, w) / Z(N, 0) + 0.5) in tenths of a percent for u = 0..N and w = 0..10,
after a cumulative minimum over w so resources never rise with a wicket; G = Z(N, 0) is the runs scale of
the plan's revised-target rule, implemented in :func:`revised_target` with integer arithmetic.

Limits. This is a DLS-like table fitted to Cricsheet first innings, not DLS Professional Edition
(deviation D4): one exponential per wicket count, no adjustment for high-scoring eras beyond the recency
weights, and the same table for every tier, venue and competition. States with many wickets down and many
balls left are rare, so Z0(8), Z0(9) rest mostly on the late-innings states.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from beating.cricket import ingest as IG

ROOT = IG.ROOT
TABLE_PATH = ROOT / "data" / "derived" / "cricket" / "resource_table.json"
FIT_CUTOFF = "2023-01-01"
HALF_LIFE_YEARS = 4.0
FAMILIES = {"T20": 120, "ODI": 300}
GENDERS = ("male", "female")
WICKETS = 10
BALL_COLS = ["match_id", "innings", "over", "ball_in_over", "balls_remaining", "inn_runs", "inn_wkts",
             "max_balls_known_before"]
# Approximate values of the published Duckworth-Lewis Standard Edition table (50 overs, 2002 revision), as
# recalled from the commonly printed version: % of resources at overs left x wickets lost. Shape reference only.
DLS_STANDARD = {50: [100.0, 93.4, 85.1, 74.9, 62.7, 49.0, 34.9, 22.0, 11.9, 4.7],
                40: [89.3, 84.2, 77.8, 69.6, 59.5, 47.6, 34.6, 22.0, 11.9, 4.7],
                30: [75.1, 71.8, 67.3, 61.6, 54.1, 44.7, 33.6, 21.8, 11.9, 4.7],
                25: [66.5, 63.9, 60.5, 56.0, 50.0, 42.2, 32.6, 21.6, 11.9, 4.7],
                20: [56.6, 54.8, 52.4, 49.1, 44.6, 38.6, 30.8, 21.2, 11.9, 4.7],
                10: [32.1, 31.6, 30.8, 29.8, 28.3, 26.1, 22.8, 17.9, 11.4, 4.7],
                5: [17.2, 17.0, 16.8, 16.5, 16.1, 15.4, 14.3, 12.5, 9.4, 4.6]}
STANDARD_OVERS = {"T20": (20, 15, 10, 6, 5, 3, 1), "ODI": (50, 40, 30, 25, 20, 10, 5)}
STANDARD_WKTS = (0, 2, 4, 5, 7, 9)


# ---------------------------------------------------------------- model

def z_curve(u, z0: float, b: float):
    return z0 * (1.0 - np.exp(-b * np.asarray(u, float)))


def eligible_innings(matches: pd.DataFrame, innings: pd.DataFrame, cutoff: str = FIT_CUTOFF) -> pd.DataFrame:
    """First innings eligible for the fit (module docstring), with fam, gender, N, date and final runs."""
    m = matches.copy()
    m["N"] = m.fam.map(FAMILIES)
    ok = (m.N.notna() & (m.start_date < cutoff) & m.scheduled_balls.eq(m.N) & ~m.awarded.fillna(False).astype(bool)
          & ~m.inn1_cut.fillna(False).astype(bool) & m.method.isna()
          & (m.target_balls.isna() | m.target_balls.eq(m.N)) & m.balls_per_over.eq(6))
    i1 = innings[innings.innings == 1].set_index("match_id")
    m = m[ok].join(i1[["all_out", "legal_balls", "runs_deliveries", "pen_pre", "declared", "forfeited"]],
                   on="match_id", how="inner")
    done = m.all_out.astype(bool) | (m.legal_balls >= m.N)
    m = m[done & ~m.declared.astype(bool) & ~m.forfeited.astype(bool)]
    m["final_runs"] = m.runs_deliveries + m.pen_pre
    return m[["match_id", "fam", "gender", "N", "start_date", "final_runs"]]


def states(balls: pd.DataFrame, elig: pd.DataFrame, cutoff: str = FIT_CUTOFF,
           half_life: float = HALF_LIFE_YEARS) -> pd.DataFrame:
    """One weighted state per legal-ball position of each eligible innings: fam, gender, u, w, y, weight."""
    b = balls[balls.innings == 1]
    b = b.merge(elig, on="match_id", how="inner")
    mb = b.max_balls_known_before.astype("float64")
    bad = mb.ne(b.N).groupby(b.match_id).transform("any")      # the length changed somewhere in the innings
    b = b[~bad].drop_duplicates(["match_id", "over", "ball_in_over"], keep="first")
    age = (pd.Timestamp(cutoff) - pd.to_datetime(b.start_date)).dt.days / 365.25
    return pd.DataFrame({"fam": b.fam.to_numpy(), "gender": b.gender.to_numpy(),
                         "u": b.balls_remaining.astype(int).to_numpy(), "w": b.inn_wkts.astype(int).to_numpy(),
                         "y": (b.final_runs - b.inn_runs).astype(float).to_numpy(),
                         "weight": (0.5 ** (age / half_life)).to_numpy(), "match_id": b.match_id.to_numpy(),
                         "year": b.start_date.str[:4].astype(int).to_numpy()})


def cells(st: pd.DataFrame) -> pd.DataFrame:
    """Weighted (fam, gender, u, w) cells: W, mean, sd and raw count."""
    st = st.assign(wy=st.weight * st.y, wyy=st.weight * st.y ** 2)
    g = st.groupby(["fam", "gender", "u", "w"])
    c = g.agg(W=("weight", "sum"), S=("wy", "sum"), Q=("wyy", "sum"), n=("y", "size")).reset_index()
    c["mean"] = c.S / c.W
    c["sd"] = np.sqrt(np.maximum(c.Q / c.W - c["mean"] ** 2, 0))
    return c.drop(columns=["S", "Q"])


def fit_curve(u: np.ndarray, ybar: np.ndarray, W: np.ndarray, n_balls: int) -> tuple[float, float, dict]:
    """(Z0, b, diagnostics) minimising sum W (ybar - Z0 (1 - exp(-b u)))^2."""
    from scipy.optimize import least_squares
    sw = np.sqrt(W)
    res = lambda p: sw * (ybar - z_curve(u, p[0], p[1]))
    z0 = max(float(np.max(ybar)) * 1.3, 1.0)
    best = None
    for b0 in (0.3 / n_balls, 1.0 / n_balls, 3.0 / n_balls, 10.0 / n_balls):
        r = least_squares(res, [z0, b0], bounds=([1e-6, 1e-6], [1e5, 5.0]), x_scale=[z0, b0])
        if best is None or r.cost < best.cost:
            best = r
    fit = z_curve(u, *best.x)
    rmse = float(np.sqrt(np.sum(W * (ybar - fit) ** 2) / np.sum(W)))
    return float(best.x[0]), float(best.x[1]), {"rmse_cell_mean": round(rmse, 3), "cells": int(len(u)),
                                                 "weight": round(float(W.sum()), 1)}


def fit(c: pd.DataFrame) -> dict:
    """Fitted parameters and tables per family and gender from the cells."""
    out = {}
    for fam, N in FAMILIES.items():
        for gender in GENDERS:
            x = c[(c.fam == fam) & (c.gender == gender)]
            if x.empty:
                continue
            z0, b, diag = [], [], []
            for w in range(WICKETS):
                xw = x[x.w == w]
                if xw.W.sum() <= 0 or len(xw) < 3:
                    z0.append(z0[-1] if z0 else 1.0)
                    b.append(b[-1] if b else 1.0 / N)
                    diag.append({"cells": int(len(xw)), "fallback": True})
                    continue
                a, bb, d = fit_curve(xw.u.to_numpy(float), xw["mean"].to_numpy(float), xw.W.to_numpy(float), N)
                z0.append(a), b.append(bb), diag.append(d)
            out.setdefault(fam, {})[gender] = table(fam, N, z0, b) | {"fit": diag}
    return out


def table(fam: str, N: int, z0: list, b: list) -> dict:
    u = np.arange(N + 1)
    Z = np.column_stack([z_curve(u, z0[w], b[w]) for w in range(WICKETS)] + [np.zeros(N + 1)])
    mono = np.minimum.accumulate(Z, axis=1)
    G = float(mono[N, 0])
    P = np.floor(1000.0 * mono / G + 0.5).astype(int)
    return {"N": N, "G": round(G, 2), "Z0": [round(float(v), 3) for v in z0], "b": [round(float(v), 6) for v in b],
            "monotone_adjusted_cells": int((mono < Z - 1e-9).sum()), "P": P.tolist()}


# ---------------------------------------------------------------- use

def load_table(path: Path | str = TABLE_PATH) -> dict:
    return json.loads(Path(path).read_text())


def resource(tab: dict, fam: str, gender: str, u: int, w: int) -> int:
    """Resource in tenths of a percent at u legal balls remaining and w wickets lost (clamped)."""
    t = tab["tables"][fam][gender]
    return int(t["P"][max(0, min(int(u), t["N"]))][max(0, min(int(w), WICKETS))])


def z_runs(tab: dict, fam: str, gender: str, u, w) -> np.ndarray:
    """Z(u, w) in runs from the integer table (vectorized): P / 1000 * G."""
    t = tab["tables"][fam][gender]
    P = np.asarray(t["P"], dtype=np.float64)
    u = np.clip(np.asarray(u, dtype=np.int64), 0, t["N"])
    w = np.clip(np.asarray(w, dtype=np.int64), 0, WICKETS)
    return P[u, w] * t["G"] / 1000.0


def revised_target(S: int, R1: int, R2: int, G: float) -> int:
    """Plan 7.6: team 2's target from team 1's score S and resources R1, R2 (tenths of a percent)."""
    if R2 <= R1:
        return (S * R2) // R1 + 1
    return S + math.floor(G * (R2 - R1) / 1000.0) + 1


# ---------------------------------------------------------------- build and report

def load_states(cutoff: str = FIT_CUTOFF, balls_path=None) -> pd.DataFrame:
    import pyarrow.parquet as pq
    matches = IG.read_table("matches")
    innings = IG.read_table("innings")
    elig = eligible_innings(matches, innings, cutoff)
    path = balls_path or IG.OUT_DIR / "balls.parquet"
    t = pq.read_table(path, columns=BALL_COLS, filters=[("innings", "==", 1)])
    balls = t.to_pandas()
    balls = balls[balls.match_id.isin(elig.match_id)]
    return states(balls, elig, cutoff)


def standard_points(fitted: dict) -> dict:
    """Fitted resource percentages at standard (overs left, wickets lost) points, next to the DLS shape."""
    out = {}
    for fam, by_g in fitted.items():
        for gender, t in by_g.items():
            rows = {}
            for ov in STANDARD_OVERS[fam]:
                P = t["P"][ov * 6]
                row = {"fitted": [round(P[w] / 10, 1) for w in STANDARD_WKTS]}
                if fam == "ODI" and ov in DLS_STANDARD:
                    row["dls_standard"] = [DLS_STANDARD[ov][w] for w in STANDARD_WKTS]
                if fam == "T20":
                    ref = _dls_interp(ov)
                    row["dls_standard_rescaled_20"] = [round(100 * ref[w] / DLS_STANDARD[20][0], 1)
                                                       for w in STANDARD_WKTS]
                rows[str(ov)] = row
            out[f"{fam}-{gender}"] = {"wickets": list(STANDARD_WKTS), "overs_left": rows, "G": t["G"]}
    return out


def _dls_interp(ov: float) -> list:
    """Linear interpolation of the recalled DLS table in overs left (0 at 0 overs)."""
    xs = sorted(DLS_STANDARD)
    pts = [0] + xs
    vals = [[0.0] * 10] + [DLS_STANDARD[x] for x in xs]
    return [float(np.interp(ov, pts, [v[w] for v in vals])) for w in range(10)]


def shape_comparison(fitted: dict) -> dict:
    """Max and mean absolute differences (percentage points) from the recalled DLS shape at its points."""
    out = {}
    for fam, by_g in fitted.items():
        for gender, t in by_g.items():
            diffs = []
            top = 50 if fam == "ODI" else 20
            for ov in (o for o in DLS_STANDARD if o <= top):
                fitted_row = np.array(t["P"][ov * 6][:10]) / 10
                ref = np.array(DLS_STANDARD[ov]) * (100.0 / DLS_STANDARD[top][0])
                diffs.append(fitted_row - ref)
            d = np.array(diffs)
            out[f"{fam}-{gender}"] = {"max_abs_pp": round(float(np.abs(d).max()), 1),
                                      "mean_abs_pp": round(float(np.abs(d).mean()), 1),
                                      "mean_signed_by_wkts": [round(float(v), 1) for v in d.mean(axis=0)]}
    return out


def era_scale(st: pd.DataFrame) -> dict:
    """Mean first-innings total by era (unweighted) and the recency-weighted mean, a check on the weights."""
    first = st[(st.u == st.groupby("match_id").u.transform("max")) & (st.w == 0)].drop_duplicates("match_id")
    era = pd.cut(first.year, [0, 2009, 2014, 2019, 2100], labels=["-2009", "2010-14", "2015-19", "2020-22"])
    out = {}
    for (fam, gender), g in first.groupby(["fam", "gender"]):
        e = g.groupby(era[g.index], observed=True).y.agg(["size", "mean"])
        out[f"{fam}-{gender}"] = {"innings": int(len(g)),
                                  "weighted_mean_total": round(float(np.average(g.y, weights=g.weight)), 1),
                                  "mean_total_by_era": {str(k): [int(r["size"]), round(float(r["mean"]), 1)]
                                                        for k, r in e.iterrows()}}
    return out


def build(path: Path | str = TABLE_PATH, cutoff: str = FIT_CUTOFF) -> tuple[dict, dict]:
    """Fit, write the JSON table and return (table, report)."""
    st = load_states(cutoff)
    c = cells(st)
    fitted = fit(c)
    meta = dict(version=1, fit_cutoff=cutoff, half_life_years=HALF_LIFE_YEARS,
                form="Z(u, w) = Z0(w) (1 - exp(-b(w) u)); u legal balls remaining, w wickets lost",
                units="P[u][w] tenths of a percent of G = Z(N, 0): floor(1000 Z / G + 0.5), w = 0..10",
                selection="first innings before the cutoff, standard length, unreduced, completed (all out or "
                          "full allocation), six-ball overs; one state per legal-ball position",
                revised_target="R2 <= R1: floor(S R2 / R1) + 1; R2 > R1: S + floor(G (R2 - R1) / 1000) + 1")
    counts = st.groupby(["fam", "gender"]).agg(states=("y", "size"), innings=("match_id", "nunique"))
    for (fam, gender), r in counts.iterrows():
        fitted[fam][gender]["n_innings"], fitted[fam][gender]["n_states"] = int(r.innings), int(r.states)
    tab = dict(meta, tables={f: {g: {k: v for k, v in t.items() if k != "fit"} for g, t in by.items()}
                             for f, by in fitted.items()})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(tab, separators=(",", ":")))
    report = {"params": {f"{f}-{g}": {k: t[k] for k in ("N", "G", "Z0", "b", "n_innings", "n_states",
                                                        "monotone_adjusted_cells", "fit")}
                         for f, by in fitted.items() for g, t in by.items()},
              "standard_points": standard_points(tab["tables"]), "dls_shape": shape_comparison(tab["tables"]),
              "totals": era_scale(st)}
    return tab, report
