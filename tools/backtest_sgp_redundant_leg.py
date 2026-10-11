"""Population back test of the redundant-leg SGP target event.

Checks whether the probability bounds behind the October 8-9, 2026
theScore Bet / FanDuel McCaffrey quotes are plausible, using nflverse weekly
rushing and receiving yards for running backs. Books set lines near the
player's median, so each running back game gets pseudo-lines from the median
of the player's previous qualifying games. The target events are then graded
at the actual thresholds in the quotes, inside the cohort of games whose
pseudo-lines resemble McCaffrey's October 2026 lines.

Usage:
    python tools/backtest_sgp_redundant_leg.py DATA_DIR [OUTPUT_JSON]

DATA_DIR holds nflverse weekly files: player_stats_YYYY.csv (through 2024)
and stats_player_week_YYYY.csv (2025 on). The script makes no network calls.
"""
# %% Settings
import json
import math
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else None
PRICES = Path("reports/sgp-rush-receive-2026-10-08/prices-and-ev.json")
WINDOW = 6          # prior qualifying games behind each pseudo-line
MIN_TOUCHES = 10    # carries + targets for a prior game to count
MIN_SEASON = 2015

# Quoted events. S = rushing + receiving, R = rushing, C = receiving.
QUOTES = {
    "oct8_score_4leg": {"american": 854, "label": "theScore Oct 8: S>=90, R<=54, C>=40",
                        "test": lambda d: (d.S >= 90) & (d.R <= 54) & (d.C >= 40)},
    "oct8_fd_ou_cell": {"american": 515, "label": "FanDuel Oct 8 OU cell: S>=92, R<=51",
                        "test": lambda d: (d.S >= 92) & (d.R <= 51)},
    "oct8_score_broad": {"american": 790, "label": "theScore Oct 8 broad: S>=90, R<=54",
                         "test": lambda d: (d.S >= 90) & (d.R <= 54)},
    "oct9_score_4leg": {"american": 1064, "label": "theScore Oct 9: S>=90, R<=49 (C legs implied)",
                        "test": lambda d: (d.S >= 90) & (d.R <= 49)},
    "oct9_score_low": {"american": 869, "label": "theScore Oct 9 with C10+: same event",
                       "test": lambda d: (d.S >= 90) & (d.R <= 49)},
    "oct9_fd_ou_cell": {"american": 506, "label": "FanDuel Oct 9 OU cell: S>=90, R<=49",
                        "test": lambda d: (d.S >= 90) & (d.R <= 49)},
}
# FanDuel partitions as captured (OO, OU, UO, UU)
FD_PARTITIONS = {
    "oct8": {"sum_line": 91.5, "rush_line": 51.5, "prices": {"OO": 127, "OU": 515, "UO": 550, "UU": 123}},
    "oct9": {"sum_line": 89.5, "rush_line": 49.5, "prices": {"OO": 128, "OU": 506, "UO": 521, "UU": 126}},
}
# Cohorts: calibrated pseudo-lines near the FanDuel lines (S 91.5, R 51.5)
COHORTS = {
    "wide": {"S": (83.5, 99.5), "R": (43.5, 59.5)},
    "tight": {"S": (87.5, 95.5), "R": (47.5, 55.5)},
}


# %% Helpers
def decimal(american):
    return 1 + american / 100 if american > 0 else 1 + 100 / -american


def fair_american(p):
    if p <= 0 or p >= 1:
        return None
    return round(100 * (1 / p - 1)) if p <= 0.5 else -round(100 * p / (1 - p))


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - half) / denom, (centre + half) / denom)


def devig(prices):
    q = {c: 1 / decimal(a) for c, a in prices.items()}
    total = sum(q.values())
    lo, hi = 0.0, 50.0
    for _ in range(200):
        k = (lo + hi) / 2
        if sum(v ** k for v in q.values()) > 1:
            lo = k
        else:
            hi = k
    power = {c: v ** ((lo + hi) / 2) for c, v in q.items()}
    additive = {c: v - (total - 1) / 4 for c, v in q.items()}
    multiplicative = {c: v / total for c, v in q.items()}
    # Iterative proportional fitting to 50/50 marginals on each line, keeping
    # the raw odds ratio. Books post main lines near the median, so this
    # treats the single-leg markets as the reliable part of the partition.
    m = {c: q[c] for c in q}
    for _ in range(100):
        for side in ("O", "U"):
            tot = m[side + "O"] + m[side + "U"]
            m[side + "O"], m[side + "U"] = 0.5 * m[side + "O"] / tot, 0.5 * m[side + "U"] / tot
        for side in ("O", "U"):
            tot = m["O" + side] + m["U" + side]
            m["O" + side], m["U" + side] = 0.5 * m["O" + side] / tot, 0.5 * m["U" + side] / tot
    return {"raw": q, "overround": total - 1, "power": power, "additive": additive,
            "multiplicative": multiplicative, "marginal_ipf": m}


def event_rate(frame, test, american):
    hits = int(test(frame).sum())
    n = int(len(frame))
    p = hits / n if n else float("nan")
    lo, hi = wilson(hits, n)
    dec = decimal(american)
    return {"n": n, "hits": hits, "rate": p, "ci95": [lo, hi], "fair_american": fair_american(p),
            "quoted_american": american, "ev_at_quote": dec * p - 1,
            "ev_ci95": [dec * lo - 1, dec * hi - 1], "break_even_probability": 1 / dec}


# %% Load every weekly file and map both nflverse schemas to one layout
def load(path):
    df = pd.read_csv(path, low_memory=False)
    df = df.rename(columns={"recent_team": "team", "player_display_name": "name"})
    if "name" not in df.columns:
        df["name"] = df["player_name"]
    cols = ["player_id", "name", "position", "team", "season", "week", "season_type",
            "opponent_team", "carries", "rushing_yards", "targets", "receptions", "receiving_yards"]
    return df[cols]


files = sorted(DATA.glob("player_stats_20*.csv")) + sorted(DATA.glob("stats_player_week_20*.csv"))
if not files:
    sys.exit(f"no weekly files in {DATA}")
raw = pd.concat([load(f) for f in files], ignore_index=True)
rb = raw[(raw.position == "RB") & (raw.season_type == "REG") & (raw.season >= MIN_SEASON)].copy()
rb["R"] = rb.rushing_yards.fillna(0).astype(int)
rb["C"] = rb.receiving_yards.fillna(0).astype(int)
rb["S"] = rb.R + rb.C
rb["touches"] = rb.carries.fillna(0) + rb.targets.fillna(0)
rb = rb.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
seasons = sorted(rb.season.unique().tolist())


# %% Pseudo-lines from each player's previous WINDOW qualifying games
# Two methods. "median": trailing median, which overstates a player's next
# game because the window selects on past usage. "regression": a population
# fit of the next game on trailing features, shifted so that the population
# over rate is one half, which is what a posted line is meant to achieve.
def half_line(value):
    return math.floor(float(value)) + 0.5


rows = []
for _, games in rb.groupby("player_id", sort=False):
    history = deque(maxlen=WINDOW)
    season_games = {}
    for g in games.itertuples(index=False):
        prior_this_season = season_games.get(g.season, 0)
        if len(history) == WINDOW:
            h = np.array(history, dtype=float)   # columns R, C, S, carries, targets
            rows.append({"player_id": g.player_id, "name": g.name, "season": g.season, "week": g.week,
                         "team": g.team, "opponent": g.opponent_team, "R": g.R, "C": g.C, "S": g.S,
                         "touches": g.touches,
                         "med_R": np.median(h[:, 0]), "med_C": np.median(h[:, 1]), "med_S": np.median(h[:, 2]),
                         "mean_R": h[:, 0].mean(), "mean_C": h[:, 1].mean(), "mean_S": h[:, 2].mean(),
                         "mean_carries": h[:, 3].mean(), "mean_targets": h[:, 4].mean(),
                         "last_R": h[-1, 0], "last_C": h[-1, 1],
                         "prior_this_season": prior_this_season})
        if g.touches >= MIN_TOUCHES:
            history.append((g.R, g.C, g.S, g.carries, g.targets))
            season_games[g.season] = prior_this_season + 1
lined = pd.DataFrame(rows)
lined = lined[lined.touches >= 1].copy()   # a listed player who never touched the ball would void
lined["early_season"] = (lined.prior_this_season == 0).astype(float)

FEATURES = ["med_R", "med_C", "mean_R", "mean_C", "mean_carries", "mean_targets", "last_R", "last_C", "early_season"]
ORACLE = ["carries", "targets"]   # the game's own usage: more than any book knows beforehand
BINS = 20


def calibrated_lines(frame, features, stat):
    """Least-squares fit, then a median shift inside each predicted-value bin.

    Returns half-integer lines with a 50% over rate in every bin, so a cohort
    chosen on the line is itself calibrated, not just the whole population.
    """
    X = np.column_stack([np.ones(len(frame))] + [frame[f].to_numpy(float) for f in features])
    y = frame[stat].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    order = np.argsort(pred, kind="stable")
    shift = np.zeros(len(frame))
    for chunk in np.array_split(order, BINS):
        shift[chunk] = np.median(y[chunk] - pred[chunk])
    return beta, np.array([half_line(v) for v in pred + shift]), shift


lined = lined.merge(rb[["player_id", "season", "week", "carries", "targets"]], on=["player_id", "season", "week"], how="left")
lined["carries"] = lined.carries.fillna(0)
lined["targets"] = lined.targets.fillna(0)
fit = {}
for stat in ("R", "C", "S"):
    beta, lines, _ = calibrated_lines(lined, FEATURES, stat)
    fit[stat] = {"beta": beta.tolist()}
    lined[f"{stat}_line"] = lines
    _, oracle_lines, _ = calibrated_lines(lined, FEATURES + ORACLE, stat)
    lined[f"{stat}_oracle"] = oracle_lines
    lined[f"{stat}_medline"] = [half_line(v) for v in lined[f"med_{stat}"]]


def cells(frame, suffix="_line"):
    return (np.where(frame.S > frame["S" + suffix], "O", "U")
            + np.where(frame.R > frame["R" + suffix], "O", "U"))


lined["cell"] = cells(lined)
lined["cell_median"] = cells(lined, "_medline")
lined["cell_oracle"] = cells(lined, "_oracle")


# %% Calibration of the pseudo-lines and the four-cell shares, all running backs
def summarize(frame, suffix="_line"):
    cell = {"_line": frame.cell, "_medline": frame.cell_median, "_oracle": frame.cell_oracle}[suffix]
    return {
        "games": int(len(frame)), "players": int(frame.player_id.nunique()),
        "p_S_over": float((frame.S > frame["S" + suffix]).mean()),
        "p_R_over": float((frame.R > frame["R" + suffix]).mean()),
        "p_C_over": float((frame.C > frame["C" + suffix]).mean()),
        "cells": {c: float((cell == c).mean()) for c in ("OO", "OU", "UO", "UU")},
        "corr_R_C_residual": float(np.corrcoef(frame.R - frame["R" + suffix], frame.C - frame["C" + suffix])[0, 1]),
    }


calibration = {"all_rb_regression_lines": summarize(lined), "all_rb_trailing_median_lines": summarize(lined, "_medline"),
               "all_rb_usage_oracle_lines": summarize(lined, "_oracle")}
cohort_frames = {}
for key, box in COHORTS.items():
    frame = lined[lined.S_line.between(*box["S"]) & lined.R_line.between(*box["R"])]
    cohort_frames[key] = frame
    calibration[key] = summarize(frame) | {"box": box}
    calibration[key + "_touches10"] = summarize(frame[frame.touches >= MIN_TOUCHES])
    oracle_frame = lined[lined.S_oracle.between(*box["S"]) & lined.R_oracle.between(*box["R"])]
    calibration[key + "_oracle_lines"] = summarize(oracle_frame, "_oracle")


# %% Target event rates inside the cohorts
results = {}
# Whole-population view: cells are at each game's own lines, so quote the OU cell share directly
population_cells = {"regression_lines": calibration["all_rb_regression_lines"]["cells"],
                    "usage_oracle_lines": calibration["all_rb_usage_oracle_lines"]["cells"]}
for key, frame in cohort_frames.items():
    results[key] = {q: event_rate(frame, spec["test"], spec["american"]) | {"label": spec["label"]}
                    for q, spec in QUOTES.items()}
    results[key + "_touches10"] = {q: event_rate(frame[frame.touches >= MIN_TOUCHES], spec["test"], spec["american"]) | {"label": spec["label"]}
                                   for q, spec in QUOTES.items()}

# Season split for the wide cohort, to show stability
by_period = {}
wide = cohort_frames["wide"]
for label, mask in {"2015-2019": wide.season <= 2019, "2020-2024": wide.season.between(2020, 2024),
                    "2025-2026": wide.season >= 2025}.items():
    sub = wide[mask]
    by_period[label] = {q: event_rate(sub, spec["test"], spec["american"]) for q, spec in QUOTES.items()}


# %% Local estimates at the FanDuel lines (S 91.5, R 51.5)
# Book S lines sit above the R and C lines added together: 5.1 yards on
# average here, and 5.5 in the October 8 McCaffrey quotes (91.5 versus
# 51.5 + 34.5). Both local estimators therefore work in (S line, R line)
# space, which is also the space of the FanDuel partition.
line_gap = {"trailing_feature_lines": float((lined.S_line - lined.R_line - lined.C_line).mean()),
            "usage_oracle_lines": float((lined.S_oracle - lined.R_oracle - lined.C_oracle).mean())}


def kernel_estimate(frame, suffix, h_s, h_r):
    """Gaussian-weighted event rates around the McCaffrey lines."""
    w = np.exp(-0.5 * (((frame["S" + suffix] - 91.5) / h_s) ** 2 + ((frame["R" + suffix] - 51.5) / h_r) ** 2))
    ess = float(w.sum() ** 2 / (w ** 2).sum())
    ou = (frame.S > frame["S" + suffix]) & (frame.R < frame["R" + suffix])
    out = {"effective_n": ess, "bandwidth_S_R": [h_s, h_r], "ou_cell": float((w * ou).sum() / w.sum()), "events": {}}
    for q, spec in QUOTES.items():
        p = float((w * spec["test"](frame)).sum() / w.sum())
        lo, hi = wilson(p * ess, ess)
        dec = decimal(spec["american"])
        out["events"][q] = {"rate": p, "ci95": [lo, hi], "ev_at_quote": dec * p - 1, "ev_ci95": [dec * lo - 1, dec * hi - 1]}
    return out


def scaled_estimate(frame, suffix):
    """Rescale each game's S and R to the McCaffrey lines by ratio; C follows."""
    pseudo = pd.DataFrame({"S": 91.5 * frame.S / frame["S" + suffix], "R": 51.5 * frame.R / frame["R" + suffix]})
    pseudo["C"] = pseudo.S - pseudo.R
    return {"n": int(len(pseudo)), "ou_cell": float(((pseudo.S > 91.5) & (pseudo.R < 51.5)).mean()),
            "events": {q: event_rate(pseudo, spec["test"], spec["american"]) for q, spec in QUOTES.items()}}


local = {}
for label, suffix in (("trailing_feature_lines", "_line"), ("usage_oracle_lines", "_oracle")):
    boxes = {"wide_box": COHORTS["wide"], "all_balanced": {"S": (45.5, 999.0), "R": (25.5, 999.0)}}
    local[label] = {
        "kernel": {f"h{hs}x{hr}": kernel_estimate(lined, suffix, hs, hr) for hs, hr in ((6, 5), (10, 8), (15, 12))},
        "scaled": {name: scaled_estimate(lined[lined["S" + suffix].between(*b["S"]) & lined["R" + suffix].between(*b["R"])], suffix)
                   for name, b in boxes.items()},
    }


# %% FanDuel partition probabilities under each de-vig model
partitions = {}
for key, part in FD_PARTITIONS.items():
    d = devig(part["prices"])
    partitions[key] = {"lines": {"S": part["sum_line"], "R": part["rush_line"]}, "prices": part["prices"],
                       "overround": d["overround"],
                       "OU_probability": {m: d[m]["OU"] for m in ("raw", "multiplicative", "power", "additive", "marginal_ipf")},
                       "power_marginals": {"S_over": d["power"]["OO"] + d["power"]["OU"], "R_under": d["power"]["OU"] + d["power"]["UU"]}}


# %% McCaffrey's own games
cmc = rb[rb.name == "Christian McCaffrey"].copy()
cmc_seasons = []
for season, games in cmc.groupby("season"):
    cmc_seasons.append({
        "season": int(season), "games": int(len(games)),
        "median_R": float(games.R.median()), "median_C": float(games.C.median()),
        "median_S": float(games.S.median()),
        **{q: int(spec["test"](games).sum()) for q, spec in QUOTES.items()},
    })
cmc_total = {q: event_rate(cmc, spec["test"], spec["american"]) for q, spec in QUOTES.items()}
cmc_lined = lined[lined.name == "Christian McCaffrey"]
cmc_similar = cmc_lined[cmc_lined.S_line.between(*COHORTS["wide"]["S"]) & cmc_lined.R_line.between(*COHORTS["wide"]["R"])]
# What the population fit would post for McCaffrey's next game, versus FanDuel's 91.5 / 51.5
cmc_hist = rb[(rb.name == "Christian McCaffrey") & (rb.touches >= MIN_TOUCHES)].tail(WINDOW)
h = cmc_hist[["R", "C", "S", "carries", "targets"]].to_numpy(float)
x_next = np.array([1, np.median(h[:, 0]), np.median(h[:, 1]), h[:, 0].mean(), h[:, 1].mean(), h[:, 3].mean(), h[:, 4].mean(), h[-1, 0], h[-1, 1], 0.0])
cmc_next_lines = {stat: half_line(x_next @ np.array(fit[stat]["beta"])) for stat in ("R", "C", "S")}  # uncalibrated fit value
cmc_similar_rates = {q: event_rate(cmc_similar, spec["test"], spec["american"]) for q, spec in QUOTES.items()}
cmc_2026 = cmc[cmc.season == 2026][["season", "week", "team", "opponent_team", "carries", "R", "targets", "C", "S"]]


# %% How much theScore's engine paid for redundant legs (October 8 census)
boost = None
if PRICES.exists():
    data = json.loads(PRICES.read_text())
    multipliers = []
    for inst in data["instances"]:
        if inst.get("base_american") is None or inst.get("best_american") is None:
            continue
        m = decimal(inst["best_american"]) / decimal(inst["base_american"])
        multipliers.append({"player": inst["player"], "base": inst["base_american"], "best": inst["best_american"],
                            "multiplier": m, "added": inst.get("best_added_legs")})
    changed = [m for m in multipliers if m["multiplier"] > 1.0001]
    boost = {"constructions_with_prices": len(multipliers),
             "constructions_where_redundant_legs_raised_payout": len(changed),
             "median_multiplier_when_raised": float(np.median([m["multiplier"] for m in changed])) if changed else None,
             "max_multiplier": max(m["multiplier"] for m in multipliers) if multipliers else None,
             "implied_conditional_probability_assigned": {
                 "median": float(np.median([1 / m["multiplier"] for m in changed])) if changed else None,
                 "min": min(1 / m["multiplier"] for m in changed) if changed else None},
             "rows": multipliers}


# %% Report
def pct(x):
    return f"{100 * x:.1f}%"


print(f"files: {len(files)}  seasons: {seasons[0]}-{seasons[-1]}  RB games with pseudo-lines: {len(lined)}")
for key, cal in calibration.items():
    print(f"[{key}] games={cal['games']} players={cal['players']} "
          f"P(S over)={pct(cal['p_S_over'])} P(R over)={pct(cal['p_R_over'])} P(C over)={pct(cal['p_C_over'])} "
          f"cells OO/OU/UO/UU={'/'.join(pct(cal['cells'][c]) for c in ('OO', 'OU', 'UO', 'UU'))} "
          f"corr(R,C resid)={cal['corr_R_C_residual']:+.3f}")
for key, part in partitions.items():
    print(f"[FD {key}] overround={pct(part['overround'])} OU: " +
          " ".join(f"{m}={pct(p)}" for m, p in part["OU_probability"].items()) +
          f"  power marginals S_over={pct(part['power_marginals']['S_over'])} R_under={pct(part['power_marginals']['R_under'])}")
print("McCaffrey next-game lines from the population fit:", cmc_next_lines, "FanDuel Oct 8: S 91.5 / R 51.5")
for key in results:
    print(f"--- cohort {key} ---")
    for q, r in results[key].items():
        print(f"{r['label']:<45} n={r['n']:5d} hits={r['hits']:4d} rate={pct(r['rate'])} "
              f"CI=[{pct(r['ci95'][0])}, {pct(r['ci95'][1])}] fair={r['fair_american']:+d} "
              f"quoted={r['quoted_american']:+d} break-even={pct(r['break_even_probability'])} "
              f"EV={pct(r['ev_at_quote'])} EV CI=[{pct(r['ev_ci95'][0])}, {pct(r['ev_ci95'][1])}]")
print(f"mean S line minus (R line + C line): " + ", ".join(f"{k}={v:+.2f}" for k, v in line_gap.items()))
print("--- local estimates at S 91.5 / R 51.5 (T1 = Oct 8 four-leg event; FD = its OU cell; Oct9 = S>=90,R<=49) ---")
for label, res in local.items():
    for name, k in res["kernel"].items():
        e = k["events"]
        print(f"[{label} kernel {name}] eff n={k['effective_n']:6.1f} OU cell={pct(k['ou_cell'])} "
              f"T1={pct(e['oct8_score_4leg']['rate'])} [{pct(e['oct8_score_4leg']['ci95'][0])}, {pct(e['oct8_score_4leg']['ci95'][1])}] "
              f"FD={pct(e['oct8_fd_ou_cell']['rate'])} Oct9={pct(e['oct9_score_4leg']['rate'])} [{pct(e['oct9_score_4leg']['ci95'][0])}, {pct(e['oct9_score_4leg']['ci95'][1])}]")
    for name, sc in res["scaled"].items():
        e = sc["events"]
        print(f"[{label} scaled {name}] n={sc['n']} OU cell={pct(sc['ou_cell'])} T1={pct(e['oct8_score_4leg']['rate'])} "
              f"[{pct(e['oct8_score_4leg']['ci95'][0])}, {pct(e['oct8_score_4leg']['ci95'][1])}] FD={pct(e['oct8_fd_ou_cell']['rate'])} Oct9={pct(e['oct9_score_4leg']['rate'])}")
print("--- wide cohort by period: oct8_score_4leg rate (n) ---")
for label, res in by_period.items():
    r = res["oct8_score_4leg"]
    print(f"{label}: {pct(r['rate'])} ({r['n']})   FD OU cell: {pct(res['oct8_fd_ou_cell']['rate'])}")
print("--- McCaffrey by season ---")
print(pd.DataFrame(cmc_seasons).to_string(index=False))
print("McCaffrey career:", {q: f"{r['hits']}/{r['n']}" for q, r in cmc_total.items()})
print("McCaffrey games with CMC-like pseudo-lines:", {q: f"{r['hits']}/{r['n']}" for q, r in cmc_similar_rates.items()})
print(cmc_2026.to_string(index=False))
if boost:
    print(f"--- theScore redundant-leg boost (Oct 8 census) --- raised in {boost['constructions_where_redundant_legs_raised_payout']}/{boost['constructions_with_prices']}; "
          f"median multiplier {boost['median_multiplier_when_raised']:.3f}; max {boost['max_multiplier']:.3f}; "
          f"median conditional probability the engine assigned to an implied leg: {boost['implied_conditional_probability_assigned']['median']:.3f}")

if OUT:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "settings": {"window": WINDOW, "min_touches": MIN_TOUCHES, "min_season": MIN_SEASON, "seasons": seasons,
                     "files": [f.name for f in files], "cohorts": COHORTS},
        "calibration": calibration, "population_cells": population_cells, "fanduel_partitions": partitions,
        "cohort_results": results, "wide_cohort_by_period": by_period, "line_gap": line_gap, "local_estimates": local,
        "line_fit": fit | {"features": FEATURES},
        "mccaffrey": {"seasons": cmc_seasons, "career": cmc_total, "similar_line_games": cmc_similar_rates,
                      "next_game_lines_from_fit": cmc_next_lines,
                      "games_2026": cmc_2026.to_dict("records")},
        "thescore_boost": boost,
    }, indent=1, default=float))
    print("wrote", OUT)
