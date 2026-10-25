"""Player metadata and bowling-type inference (plan 4.4 `players`, columns of revision 1 section 4.3).

Sources. `people_index` (every Cricsheet registry id seen in the zip, dense `person_id`) joined to the
cricketdata `player_meta` table (key `cricsheet_id` = registry identifier). Eight identifiers appear twice
in `player_meta`; the row whose `cricinfo_id` equals people.csv `key_cricinfo` (then `key_cricinfo_2/3`)
wins, then the row with more filled fields. Five rows carry a bowling style in `batting_style` with an empty
`bowling_style`; the string is moved to the bowling side and the hand left unknown.

Style mapping. Strings are lower-cased with hyphens read as spaces and split on commas. Each part maps by
keyword: wrist spin / chinaman -> left_wrist, orthodox -> left_orth, offbreak -> off_spin, legbreak /
googly -> leg_spin, slow medium and medium -> pace_medium, fast / fast medium / medium fast -> pace_fast.
'Right/Left arm Bowler', 'Slow', 'Right arm Slow', '(Unknown Arm) Slow' map to nothing (the arm is kept).
`bowl_type` is the first mapped part, `bowl_type_2` the next distinct mapped part ('none' if there is no
later part, 'unknown' if the later parts are vague). `bowl_arm` is the arm stated with the first mapped
part, else the one the type implies (off-break and leg-break right-arm, orthodox and wrist spin left-arm).
Players listed with both a pace and a spin style are left out of training, and the two are swapped when
the bowler has at least 300 legal balls and the classifier gives the second style's class probability of
at least 0.9 (Laura Marsh: fast-medium, then off-break). `bat_hand` is R/L/U from /right|left hand/.

Usage (ball table, all main-innings deliveries). Per bowler: deliveries by family and gender, wides,
no-balls, byes, leg byes, runs, dots, boundaries, powerplay and death shares of limited-overs balls (over
thresholds T20 6/16, Hundred sets 5/16, ODI 10/40), the share in overs 1-2, mean spell length, the Test
new-ball share (ball age < 10 overs) and mean ball age, bowler-credited wickets by kind (caught,
caught-and-bowled, bowled, lbw, stumped, caught by a keeper) and a left-hander tilt (balls to left-handed
strikers minus the innings' left-hander share). A player is a `keeper` when `player_meta` gives a
wicketkeeper role or the ball table names him as the fielder of a stumping.

Inference. Rates become logits shrunk to the population mean with pseudo-counts (50 deliveries, 4
wickets), standardised. A six-way multinomial logit over the mapped types with a ridge penalty (chosen by
5-fold cross-validated log loss, folds by a hash of the registry id) is trained on known-style bowlers with
at least 60 legal balls; class probabilities are sums over the pace and spin types. When the arm is known,
type probabilities are multiplied by P(arm | type) from the training labels. Unknown-style bowlers with at
least 60 legal balls get `meta_source = inferred`, `bowl_class` = the likelier class with
`infer_confidence` its probability, and `bowl_type` = the likeliest type when its probability is at least
0.5 (`type_confidence` holds it either way). `p_spin` is filled for every bowler (out-of-fold for training
bowlers), so strong disagreements with Cricinfo are listed in the report (not overridden). No style and no
legal ball bowled -> `none`; fewer than 60 balls -> `unknown`.

Outputs. `data/processed/cricket/players.parquet` (row i = person_id i, metadata, labels and usage
summaries), `data/derived/cricket/player_types.csv` (committed labels of everyone who played) and
`reports/cricket-player-meta-coverage.json` (mapping, dedup, cross-validation with and without the arm,
inferred counts, delivery coverage since 2019 by family and gender, top unmapped players).

Limits. Usage is whole-career, so an inferred label for a match uses that bowler's later deliveries too
(a labelling lookahead; the label is a fixed trait, not a fitted effect). Cricinfo's fast/medium split is
coarse and noisy, spin subtypes are weakly identified without the arm (left_wrist is never inferred), and
part-time medium pacers used like spinners score as spin. Batting hand cannot be inferred from the data
and stays U for players without metadata.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import zlib

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from beating.cricket.ingest import OUT_DIR, PEOPLE_CSV, ROOT, read_table

META_RDA = ROOT.parent / "robjhyndman" / "cricketdata" / "data" / "player_meta.rda"
PLAYERS_PATH = OUT_DIR / "players.parquet"
TYPES_CSV = ROOT / "data" / "derived" / "cricket" / "player_types.csv"
REPORT_PATH = ROOT / "reports" / "cricket-player-meta-coverage.json"

TYPES = ("pace_fast", "pace_medium", "off_spin", "leg_spin", "left_orth", "left_wrist")
BOWL_TYPES = TYPES + ("none", "unknown")
CLASS_OF = {"pace_fast": "pace", "pace_medium": "pace", "off_spin": "spin", "leg_spin": "spin",
            "left_orth": "spin", "left_wrist": "spin"}
SPIN = np.array([CLASS_OF[t] == "spin" for t in TYPES])
ARM_OF = {"off_spin": "R", "leg_spin": "R", "left_orth": "L", "left_wrist": "L"}
MIN_BALLS = 60
TYPE_MIN_P = 0.5
SWAP_MIN_BALLS, SWAP_MIN_P = 300, 0.9
PSEUDO_BALLS = 50.0
PSEUDO_WKTS = 4.0
LAMBDAS = (1e-4, 1e-3, 3e-3, 1e-2, 3e-2, 0.1)
FOLDS = 5
PHASE_OVERS = {"T20": (6, 16), "HUNDRED": (5, 16), "ODI": (10, 40)}
FAMS = ("T20", "HUNDRED", "ODI", "TEST")
SINCE = "2019-01-01"
BOWLER_KINDS = {"caught": "w_caught", "caught and bowled": "w_cb", "bowled": "w_bowled", "lbw": "w_lbw",
                "stumped": "w_stumped", "hit wicket": "w_hitwkt"}


# ---------------------------------------------------------------- style strings

def norm_style(s) -> str:
    return re.sub(r"\s+", " ", str(s).lower().replace("-", " ")).strip() if isinstance(s, str) else ""


def _part(p: str) -> tuple[str | None, str]:
    arm = "R" if "right arm" in p else "L" if "left arm" in p else "U"
    if "wrist spin" in p or "chinaman" in p:
        t = "left_wrist"
    elif "orthodox" in p:
        t = "left_orth"
    elif "offbreak" in p or "off break" in p or "off spin" in p:
        t = "off_spin"
    elif "legbreak" in p or "leg break" in p or "googly" in p or "leg spin" in p:
        t = "leg_spin"
    elif "slow medium" in p:
        t = "pace_medium"
    elif "fast" in p:
        t = "pace_fast"
    elif "medium" in p:
        t = "pace_medium"
    else:
        t = None
    return t, arm


def parse_bowling(s) -> dict:
    """Bowling-style string -> bowl_type, bowl_type_2, bowl_arm, vague (a style that maps to nothing)."""
    parts = [_part(p.strip()) for p in norm_style(s).split(",") if p.strip()]
    if not parts:
        return dict(bowl_type="none", bowl_type_2="none", bowl_arm="U", vague=False)
    i0 = next((i for i, (t, _) in enumerate(parts) if t), None)
    if i0 is None:
        return dict(bowl_type="unknown", bowl_type_2="none", bowl_arm=next((a for _, a in parts if a != "U"), "U"), vague=True)
    first, later = parts[i0][0], parts[i0 + 1:]
    rest = [t for t in dict.fromkeys(t for t, _ in later if t) if t != first]
    second = rest[0] if rest else ("unknown" if any(t is None for t, _ in later) else "none")
    arm = parts[i0][1] if parts[i0][1] != "U" else ARM_OF.get(first, next((a for _, a in parts if a != "U"), "U"))
    return dict(bowl_type=first, bowl_type_2=second, bowl_arm=arm, vague=False)


def parse_hand(s) -> str:
    n = norm_style(s)
    return "R" if "right hand" in n else "L" if "left hand" in n else "U"


def looks_like_bowling(s) -> bool:
    n = norm_style(s)
    return bool(n) and "hand" not in n and _part(n)[0] is not None


# ---------------------------------------------------------------- metadata

def load_meta(path=META_RDA) -> pd.DataFrame:
    import pyreadr
    m = pyreadr.read_r(str(path))["player_meta"]
    m["dob"] = pd.to_datetime(m["dob"], errors="coerce").dt.strftime("%Y-%m-%d")
    return m


def dedupe_meta(meta: pd.DataFrame, people: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """One row per cricsheet_id: prefer cricinfo_id == key_cricinfo (then _2, _3), then the fuller row."""
    keys = people.set_index("identifier")
    m = meta.copy()
    m["_score"] = m.notna().sum(axis=1)
    for rank, col in ((3, "key_cricinfo"), (2, "key_cricinfo_2"), (1, "key_cricinfo_3")):
        if col in keys:
            k = m["cricsheet_id"].map(keys[col]).astype("string")
            m.loc[k.eq(m["cricinfo_id"].astype("string")).to_numpy(dtype=bool, na_value=False), "_score"] += 100 * rank
    m = m.sort_values(["cricsheet_id", "_score"], ascending=[True, False], kind="stable")
    dup = m[m["cricsheet_id"].duplicated(keep=False)]
    log = [dict(cricsheet_id=i, kept=str(g["cricinfo_id"].iloc[0]), dropped=[str(x) for x in g["cricinfo_id"].iloc[1:]],
                key_cricinfo=str(keys["key_cricinfo"].get(i)) if i in keys.index else None)
           for i, g in dup.groupby("cricsheet_id", sort=True)]
    return m.drop_duplicates("cricsheet_id").drop(columns="_score").reset_index(drop=True), log


def style_table(people_index: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """people_index rows (row i = person_id i) with metadata and mapped styles."""
    pi = people_index.sort_values("person_id").reset_index(drop=True)
    assert (pi["person_id"].to_numpy() == np.arange(len(pi))).all()
    m = meta.set_index("cricsheet_id")
    out = pi[["person_id", "identifier", "name", "unique_name", "key_cricinfo", "n_matches_player",
              "first_date", "last_date"]].rename(columns={"identifier": "player_id"})
    for c in ("cricinfo_id", "full_name", "country", "dob", "playing_role", "batting_style", "bowling_style"):
        out[c] = out["player_id"].map(m[c]) if c in m else None
    out["has_meta"] = out["player_id"].isin(m.index)
    shift = out["bowling_style"].isna() & out["batting_style"].map(looks_like_bowling)
    out["style_note"] = np.where(shift, "bowling_style_in_batting_column", "")
    out.loc[shift, "bowling_style"] = out.loc[shift, "batting_style"]
    out.loc[shift, "batting_style"] = None
    out["bat_hand"] = out["batting_style"].map(parse_hand)
    styles = pd.DataFrame([parse_bowling(s) for s in out["bowling_style"]], index=out.index)
    out = pd.concat([out, styles], axis=1)
    out.loc[styles["vague"], "style_note"] = np.where(out.loc[styles["vague"], "style_note"].eq(""), "vague_style",
                                                     out.loc[styles["vague"], "style_note"] + ";vague_style")
    out["bowl_class"] = out["bowl_type"].map(CLASS_OF).fillna(out["bowl_type"])
    out["meta_source"] = np.where(out["bowl_type"].isin(TYPES), "cricinfo_meta", "none")
    out["role"] = out.pop("playing_role")
    return out.rename(columns={"batting_style": "batting_style_raw", "bowling_style": "bowling_style_raw"})


# ---------------------------------------------------------------- ball-table usage

USAGE_COLS = ["match_id", "innings", "over", "batter_id", "bowler_id", "runs_batter", "non_boundary", "byes",
              "legbyes", "penalty", "runs_total", "dtype", "wicket_kind_raw", "fielders", "fam", "gender",
              "ball_age_overs", "bowler_spell_overs"]


def _ids(s) -> np.ndarray:
    return (s.fillna(-1) if hasattr(s, "fillna") else s).to_numpy("int64")


def _is(s: pd.Series, *values) -> np.ndarray:
    """Membership test that compares categorical codes instead of materialising strings."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        return np.isin(s.cat.codes.to_numpy(), [s.cat.categories.get_loc(v) for v in values if v in s.cat.categories])
    return s.isin(values).to_numpy(bool)


def usage(balls: pd.DataFrame, matches: pd.DataFrame, bat_hand: np.ndarray, role_keeper: np.ndarray) -> pd.DataFrame:
    """Per-person usage counts from the ball table; row i = person_id i (len(bat_hand) rows)."""
    n = len(bat_hand)
    bw, bt = _ids(balls["bowler_id"]), _ids(balls["batter_id"])
    ok = bw >= 0
    out = {}

    def cnt(mask, ids=bw, w=None):
        m = mask & (ids >= 0)
        return np.bincount(ids[m], weights=None if w is None else w[m], minlength=n)

    legal, female = _is(balls["dtype"], "legal"), _is(balls["gender"], "female")
    fam = {f: _is(balls["fam"], f) for f in FAMS}
    mt = matches.set_index("match_id")
    mid = balls["match_id"].to_numpy()
    since = pd.Series(mt["start_date"].astype(str) >= SINCE).reindex(mid).to_numpy(bool)
    club = pd.Series(mt["team_type"].astype(str) == "club").reindex(mid).to_numpy(bool)
    out["n_del"], out["n_legal"] = cnt(ok), cnt(legal)
    out["n_wide"], out["n_nb"] = cnt(_is(balls["dtype"], "wide")), cnt(_is(balls["dtype"], "noball"))
    for f in FAMS:
        out[f"balls_{f}"] = cnt(fam[f])
    out["balls_female"], out["balls_club"], out["balls_since_2019"] = cnt(female), cnt(club), cnt(since)
    rb, nbd = balls["runs_batter"].to_numpy("int64"), balls["non_boundary"].to_numpy(bool)
    conceded = balls["runs_total"].to_numpy("float64") - balls["byes"].to_numpy() - balls["legbyes"].to_numpy() \
        - balls["penalty"].to_numpy()
    out["runs"] = cnt(ok, w=conceded)
    out["n_dot"] = cnt(legal & (balls["runs_total"].to_numpy() == 0))
    out["n_boundary"] = cnt(legal & ~nbd & ((rb == 4) | (rb == 6)))
    out["n_lb"], out["n_bye"] = cnt(legal & (balls["legbyes"].to_numpy() > 0)), cnt(legal & (balls["byes"].to_numpy() > 0))
    over = balls["over"].to_numpy("int64")
    pp_end = np.select([fam[f] for f in PHASE_OVERS], [v[0] for v in PHASE_OVERS.values()], -1)
    death_from = np.select([fam[f] for f in PHASE_OVERS], [v[1] for v in PHASE_OVERS.values()], 10 ** 6)
    lo = ~fam["TEST"]
    out["n_lo"], out["n_pp"], out["n_death"] = cnt(lo), cnt(lo & (over < pp_end)), cnt(lo & (over >= death_from))
    out["n_open"] = cnt(lo & (over < 2))
    out["sum_spell"] = cnt(ok, w=balls["bowler_spell_overs"].to_numpy("float64"))
    age = balls["ball_age_overs"]
    age = (age.astype("float64").fillna(-1) if hasattr(age, "fillna") else age).to_numpy("float64")
    known_age = fam["TEST"] & (age >= 0)
    out["n_age"], out["n_newball"] = cnt(known_age), cnt(known_age & (age < 10))
    out["sum_age"] = cnt(known_age, w=np.where(known_age, age, 0.0))
    kind = balls["wicket_kind_raw"]
    for k, c in BOWLER_KINDS.items():
        out[c] = cnt(_is(kind, k))
    out["w_caught"] = out["w_caught"] + out["w_cb"]
    # stumping fielders mark keepers; then catches taken by keepers
    fl = balls["fielders"].to_numpy(object)
    st_rows = np.flatnonzero(_is(kind, "stumped"))
    st_f = np.array([_first_fielder(fl[i]) for i in st_rows], dtype="int64")
    n_stumpings = np.bincount(st_f[st_f >= 0], minlength=n)
    keeper = role_keeper | (n_stumpings > 0)
    c_rows = np.flatnonzero(_is(kind, "caught"))
    c_f = np.array([_first_fielder(fl[i]) for i in c_rows], dtype="int64")
    kc = c_rows[(c_f >= 0) & keeper[np.maximum(c_f, 0)] & (c_f != bw[c_rows])]
    out["w_keeper_caught"] = np.bincount(bw[kc][bw[kc] >= 0], minlength=n)
    # left-hander tilt: balls to left-handed strikers minus the innings' left-hand share
    btx = np.maximum(bt, 0)
    lhb, known = (bat_hand == "L")[btx] & (bt >= 0), legal & (bat_hand != "U")[btx] & (bt >= 0)
    inn = pd.factorize(mid.astype("int64") * 8 + balls["innings"].to_numpy("int64"))[0]
    share = np.bincount(inn[known], weights=lhb[known], minlength=inn.max() + 1) / \
        np.maximum(np.bincount(inn[known], minlength=inn.max() + 1), 1)
    out["n_hand"], out["n_lhb"] = cnt(known), cnt(known & lhb)
    out["exp_lhb"] = cnt(known, w=share[inn])
    out["n_faced"], out["n_faced_female"] = cnt(legal, bt), cnt(legal & female, bt)
    out["n_stumpings_fielded"] = n_stumpings
    return pd.DataFrame(out).astype({c: "int64" for c in out if c not in ("runs", "sum_age", "exp_lhb", "sum_spell")})


def _first_fielder(x) -> int:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return -1
    v = json.loads(x) if isinstance(x, str) else list(x)
    return int(v[0]) if len(v) and v[0] is not None else -1


# ---------------------------------------------------------------- features and classifier

def _rate(k, n, pseudo, logit=True):
    k, n = np.asarray(k, float), np.asarray(n, float)
    p0 = k.sum() / max(n.sum(), 1.0)
    p = (k + pseudo * p0) / (n + pseudo)
    if not logit:
        return p
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def features(u: pd.DataFrame) -> pd.DataFrame:
    """Shrunk logit rates and shares per player (rows aligned with u)."""
    w = u[["w_caught", "w_bowled", "w_lbw", "w_stumped", "w_hitwkt"]].sum(axis=1)
    f = {
        "wide": _rate(u.n_wide, u.n_del, PSEUDO_BALLS), "noball": _rate(u.n_nb, u.n_del, PSEUDO_BALLS),
        "legbye": _rate(u.n_lb, u.n_legal, PSEUDO_BALLS), "bye": _rate(u.n_bye, u.n_legal, PSEUDO_BALLS),
        "dot": _rate(u.n_dot, u.n_legal, PSEUDO_BALLS), "boundary": _rate(u.n_boundary, u.n_legal, PSEUDO_BALLS),
        "econ": np.log(_rate(u.runs, u.n_del, PSEUDO_BALLS, logit=False) + 0.05),
        "wkt_rate": _rate(w, u.n_legal, PSEUDO_BALLS),
        "pp": _rate(u.n_pp, u.n_lo, PSEUDO_BALLS), "death": _rate(u.n_death, u.n_lo, PSEUDO_BALLS),
        "open": _rate(u.n_open, u.n_lo, PSEUDO_BALLS),
        "spell": np.log1p(_rate(u.sum_spell, u.n_del, PSEUDO_BALLS, logit=False)),
        "newball": _rate(u.n_newball, u.n_age, PSEUDO_BALLS),
        "age": _rate(u.sum_age / 80.0, u.n_age, PSEUDO_BALLS, logit=False),
        "stumped": _rate(u.w_stumped, w, PSEUDO_WKTS), "lbw": _rate(u.w_lbw, w, PSEUDO_WKTS),
        "bowled": _rate(u.w_bowled, w, PSEUDO_WKTS), "cb": _rate(u.w_cb, w, PSEUDO_WKTS),
        "keeper_caught": _rate(u.w_keeper_caught, w, PSEUDO_WKTS),
        "lhb_tilt": (u.n_lhb - u.exp_lhb) / (u.n_hand + PSEUDO_BALLS),
        "share_t20": _rate(u.balls_T20 + u.balls_HUNDRED, u.n_del, 5.0),
        "share_test": _rate(u.balls_TEST, u.n_del, 5.0),
        "female": _rate(u.balls_female + u.n_faced_female, u.n_del + u.n_faced, 2.0),
        "club": _rate(u.balls_club, u.n_del, 5.0),
        "log_balls": np.log1p(u.n_legal),
    }
    return pd.DataFrame(f, index=u.index)


def _softmax(Z):
    Z = Z - Z.max(axis=1, keepdims=True)
    E = np.exp(Z)
    return E / E.sum(axis=1, keepdims=True)


def fit_softmax(X: np.ndarray, y: np.ndarray, k: int, lam: float, w0=None) -> np.ndarray:
    """Ridge multinomial logit (intercepts unpenalised); returns a (d+1, k) weight matrix."""
    n, d = X.shape
    Xb, Y = np.c_[X, np.ones(n)], np.eye(k)[y]

    def f(w):
        W = w.reshape(d + 1, k)
        Z = Xb @ W
        Z -= Z.max(axis=1, keepdims=True)
        lse = np.log(np.exp(Z).sum(axis=1))
        G = Xb.T @ (np.exp(Z - lse[:, None]) - Y) / n
        G[:-1] += lam * W[:-1]
        return (lse - (Z * Y).sum(axis=1)).mean() + 0.5 * lam * (W[:-1] ** 2).sum(), G.ravel()

    w0 = np.zeros((d + 1) * k) if w0 is None else w0.ravel()
    return minimize(f, w0, jac=True, method="L-BFGS-B", options=dict(maxiter=2000)).x.reshape(d + 1, k)


def predict_softmax(W: np.ndarray, X: np.ndarray) -> np.ndarray:
    return _softmax(np.c_[X, np.ones(len(X))] @ W)


def fold_of(ids, k=FOLDS) -> np.ndarray:
    return np.array([zlib.crc32(str(i).encode()) % k for i in ids])


def cross_validate(X, y, k, folds, lambdas=LAMBDAS) -> dict:
    """Out-of-fold probabilities per lambda; picks the lambda with the lowest OOF log loss."""
    res = {}
    for lam in lambdas:
        P = np.zeros((len(y), k))
        for f in np.unique(folds):
            tr = folds != f
            P[~tr] = predict_softmax(fit_softmax(X[tr], y[tr], k, lam), X[~tr])
        res[lam] = (float(-np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1)).mean()), P)
    best = min(res, key=lambda l: res[l][0])
    return dict(lam=best, oof=res[best][1], loss={str(l): round(v[0], 5) for l, v in res.items()})


def arm_likelihood(types: np.ndarray, arms: np.ndarray, pseudo=1.0) -> dict:
    """P(arm | type) from labelled players with a stated arm, smoothed."""
    out = {}
    for j, t in enumerate(TYPES):
        a = arms[(types == j) & (arms != "U")]
        r, l = (a == "R").sum() + pseudo, (a == "L").sum() + pseudo
        out[t] = {"R": r / (r + l), "L": l / (r + l)}
    return out


def apply_arm(P: np.ndarray, arms: np.ndarray, lik: dict) -> np.ndarray:
    L = np.ones_like(P)
    for j, t in enumerate(TYPES):
        for a in ("R", "L"):
            L[arms == a, j] = lik[t][a]
    Q = P * L
    return Q / Q.sum(axis=1, keepdims=True)


def _acc(hit: np.ndarray):
    return round(float(hit.mean()), 4) if len(hit) else None


def _confusion(y, yhat, labels) -> dict:
    c = Counter(zip(y, yhat))
    return {labels[i]: {labels[j]: int(c[(i, j)]) for j in range(len(labels))} for i in range(len(labels))}


def cv_stats(oof: np.ndarray, y: np.ndarray, nb: np.ndarray) -> dict:
    """Class and type accuracy, confusion, Brier score and calibration of out-of-fold type probabilities."""
    ps = oof[:, SPIN].sum(axis=1)
    yc, yc_hat = SPIN[y].astype(int), (ps >= 0.5).astype(int)
    hit, conf = yc == yc_hat, np.maximum(ps, 1 - ps)
    buckets = {"60-299": nb < 300, "300-1199": (nb >= 300) & (nb < 1200), "1200+": nb >= 1200}
    cal = [dict(conf=f"{lo}-{min(hi, 1)}", n=int(m.sum()), mean_conf=_acc(conf[m]), accuracy=_acc(hit[m]))
           for lo, hi in ((0.5, 0.7), (0.7, 0.9), (0.9, 0.97), (0.97, 1.01)) for m in [(conf >= lo) & (conf < hi)]]
    t = oof.argmax(axis=1)
    sure = oof.max(axis=1) >= TYPE_MIN_P
    return dict(class_accuracy=_acc(hit), class_baseline=round(float(max(yc.mean(), 1 - yc.mean())), 4),
                class_brier=round(float(((ps - yc) ** 2).mean()), 4), class_confusion=_confusion(yc, yc_hat, ("pace", "spin")),
                class_accuracy_by_balls={k: dict(n=int(m.sum()), acc=_acc(hit[m])) for k, m in buckets.items()},
                class_calibration=cal, type_accuracy=_acc(t == y),
                type_accuracy_when_set=dict(n=int(sure.sum()), acc=_acc((t == y)[sure])),
                spin_subtype_accuracy=_acc((t == y)[SPIN[y] & SPIN[t]]),
                pace_subtype_accuracy=_acc((t == y)[~SPIN[y] & ~SPIN[t]]),
                type_confusion=_confusion(y, t, TYPES))


def infer_types(players: pd.DataFrame, u: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Train on known-style bowlers, cross-validate, label unknown-style bowlers; returns (players, report)."""
    F = features(u)
    mu, sd = F.mean(), F.std().replace(0, 1)
    X = ((F - mu) / sd).to_numpy()
    tidx = {t: i for i, t in enumerate(TYPES)}
    known = players["bowl_type"].isin(TYPES).to_numpy()
    enough = u["n_legal"].to_numpy() >= MIN_BALLS
    t2 = players["bowl_type_2"]
    mixed = known & t2.isin(TYPES).to_numpy() & (players["bowl_type"].map(CLASS_OF) != t2.map(CLASS_OF)).to_numpy()
    tr = known & enough & ~mixed
    y = players.loc[tr, "bowl_type"].map(tidx).to_numpy()
    arms = players["bowl_arm"].to_numpy(str)
    cv = cross_validate(X[tr], y, len(TYPES), fold_of(players.loc[tr, "player_id"]))
    W = fit_softmax(X[tr], y, len(TYPES), cv["lam"])
    lik = arm_likelihood(y, arms[tr])
    P = predict_softmax(W, X)
    P[tr] = cv["oof"]
    P = apply_arm(P, arms, lik)
    p_spin = P[:, SPIN].sum(axis=1)
    has_balls = u["n_legal"].to_numpy() > 0
    p = players.copy()
    p["p_spin"] = np.where(has_balls, p_spin, np.nan).astype("float32")
    pc2 = np.where(t2.map(CLASS_OF).eq("spin").to_numpy(), p_spin, 1 - p_spin)
    swap = mixed & (u["n_legal"].to_numpy() >= SWAP_MIN_BALLS) & (pc2 >= SWAP_MIN_P)
    p.loc[swap, ["bowl_type", "bowl_type_2"]] = p.loc[swap, ["bowl_type_2", "bowl_type"]].to_numpy()
    p.loc[swap, "bowl_class"] = p.loc[swap, "bowl_type"].map(CLASS_OF)
    p.loc[swap, "bowl_arm"] = p.loc[swap, "bowl_type"].map(ARM_OF).fillna(p.loc[swap, "bowl_arm"])
    p.loc[swap, "style_note"] = (p.loc[swap, "style_note"] + ";swapped_by_usage").str.lstrip(";")
    target = ~known & enough
    cls = np.where(p_spin >= 0.5, "spin", "pace")
    best = P.argmax(axis=1)
    p.loc[target, "bowl_class"] = cls[target]
    p.loc[target, "meta_source"] = "inferred"
    conf = np.where(p_spin >= 0.5, p_spin, 1 - p_spin)
    p["infer_confidence"] = np.where(target, conf, np.nan).astype("float32")
    p["type_confidence"] = np.where(target, P.max(axis=1), np.nan).astype("float32")
    sure = target & (P.max(axis=1) >= TYPE_MIN_P)
    p.loc[sure, "bowl_type"] = np.array(TYPES)[best[sure]]
    p.loc[target & ~sure, "bowl_type"] = "unknown"
    rest = ~known & ~enough
    vague0 = p["style_note"].str.contains("vague").to_numpy()
    p.loc[rest, "bowl_class"] = np.where((has_balls | vague0)[rest], "unknown", "none")
    p.loc[rest & (has_balls | vague0), "bowl_type"] = "unknown"
    # validation on out-of-fold predictions of the training bowlers: without the arm (as for players with no
    # style at all) and with the stated arm (as for 'Right arm Bowler' and similar)
    nb = u["n_legal"].to_numpy()[tr]
    rep = dict(n_train=int(tr.sum()), n_features=X.shape[1], features=list(F.columns), lambda_grid_oof_logloss=cv["loss"],
               lambda_chosen=cv["lam"], train_type_counts=dict(Counter(np.array(TYPES)[y])),
               cv_no_arm=cv_stats(cv["oof"], y, nb), cv_with_arm=cv_stats(apply_arm(cv["oof"], arms[tr], lik), y, nb))
    rep.update(
        arm_likelihood={t: {a: round(v, 4) for a, v in d.items()} for t, d in lik.items()},
        coef={c: {t: round(float(W[i, j]), 3) for j, t in enumerate(TYPES)} for i, c in enumerate(F.columns)},
        n_inferred=int(target.sum()), n_inferred_type_set=int(sure.sum()), n_inferred_arm_known=int((target & (arms != "U")).sum()),
        inferred_class_counts=dict(Counter(cls[target])),
        inferred_type_counts=dict(Counter(p.loc[target, "bowl_type"])),
        inferred_confidence_quantiles={q: round(float(np.quantile(conf[target], float(q))), 4) for q in ("0.1", "0.25", "0.5", "0.75")}
        if target.any() else {})
    vague = target & p["style_note"].str.contains("vague").to_numpy()
    slow = vague & p["bowling_style_raw"].map(norm_style).str.contains("slow").to_numpy()
    rep["vague_style_inferred"] = dict(n=int(vague.sum()), n_slow=int(slow.sum()),
                                       slow_inferred_spin=int((slow & (cls == "spin")).sum()))
    rep["mixed_class_styles"] = dict(n=int(mixed.sum()), with_min_balls=int((mixed & enough).sum()), swapped=int(swap.sum()),
                                     swapped_players=[dict(player_id=p.player_id[i], name=p.unique_name[i],
                                                           style=p.bowling_style_raw[i], p_second_class=round(float(pc2[i]), 4),
                                                           legal_balls=int(u.n_legal[i])) for i in np.flatnonzero(swap)])
    kc = known & has_balls & ~mixed
    kcls = SPIN[players.loc[kc, "bowl_type"].map(tidx).to_numpy()]
    p_true = np.where(kcls, p_spin[kc], 1 - p_spin[kc])
    bad = np.flatnonzero(kc)[(p_true < 0.05) & (u["n_legal"].to_numpy()[kc] >= 300)]
    bad = bad[np.argsort(-u["n_legal"].to_numpy()[bad])]
    rep["meta_conflicts_p_lt_0.05_300_balls"] = dict(n=len(bad), top=[
        dict(player_id=p.player_id[i], name=p.unique_name[i], style=p.bowling_style_raw[i],
             p_spin=round(float(p_spin[i]), 4), legal_balls=int(u.n_legal[i])) for i in bad[:25]])
    return p, rep


# ---------------------------------------------------------------- coverage and build

def coverage(players: pd.DataFrame, balls: pd.DataFrame, matches: pd.DataFrame, u: pd.DataFrame) -> dict:
    since = matches.set_index("match_id")["start_date"].astype(str).ge(SINCE)
    m = since.reindex(balls["match_id"].to_numpy()).to_numpy(bool)
    b = balls.loc[m, ["fam", "gender", "bowler_id", "batter_id"]]
    bw, bt = _ids(b["bowler_id"]), _ids(b["batter_id"])
    src = players["meta_source"].to_numpy(str)[np.maximum(bw, 0)]
    cls = players["bowl_class"].to_numpy(str)[np.maximum(bw, 0)]
    typ = players["bowl_type"].to_numpy(str)[np.maximum(bw, 0)]
    hand = players["bat_hand"].to_numpy(str)[np.maximum(bt, 0)]
    d = pd.DataFrame(dict(fam=b["fam"].to_numpy(), gender=b["gender"].to_numpy(),
                          cls_meta=(src == "cricinfo_meta") & (bw >= 0),
                          cls_inferred=(src == "inferred") & (bw >= 0),
                          type_known=np.isin(typ, TYPES) & (bw >= 0),
                          hand_known=(hand != "U") & (bt >= 0)))
    g = d.groupby(["fam", "gender"])
    tab = g.mean().round(4).assign(deliveries=g.size())
    tot = d.drop(columns=["fam", "gender"]).mean().round(4).to_dict()
    tab["cls_known_or_inferred"] = (tab["cls_meta"] + tab["cls_inferred"]).round(4)
    by = {f"{f}/{gd}": {**r.drop("deliveries").to_dict(), "deliveries": int(r["deliveries"])} for (f, gd), r in tab.iterrows()}
    nb = np.bincount(bw[bw >= 0], minlength=len(players))
    nf = np.bincount(bt[bt >= 0], minlength=len(players))
    unb = np.flatnonzero(~np.isin(players["bowl_class"].to_numpy(str), ("pace", "spin")) & (nb > 0))
    unb = unb[np.argsort(-nb[unb])][:30]
    unh = np.flatnonzero((players["bat_hand"].to_numpy(str) == "U") & (nf > 0))
    unh = unh[np.argsort(-nf[unh])][:30]
    na = lambda x: None if pd.isna(x) else x
    row = lambda i, n: dict(player_id=players.player_id[i], name=players.unique_name[i], country=na(players.country[i]),
                            has_meta=bool(players.has_meta[i]), style=na(players.bowling_style_raw[i]), deliveries_since_2019=int(n[i]),
                            legal_balls_career=int(u.n_legal[i]))
    return dict(since=SINCE, deliveries=int(len(d)), overall=tot, by_fam_gender=by,
                top_unmapped_bowlers=[row(i, nb) for i in unb], top_unknown_hand_batters=[row(i, nf) for i in unh],
                unmapped_bowlers_with_deliveries=int((~np.isin(players["bowl_class"].to_numpy(str), ("pace", "spin")) & (nb > 0)).sum()),
                unknown_hand_batters_with_deliveries=int(((players["bat_hand"].to_numpy(str) == "U") & (nf > 0)).sum()))


OUT_COLS = ["person_id", "player_id", "name", "unique_name", "full_name", "cricinfo_id", "key_cricinfo", "country", "dob",
            "role", "gender", "bat_hand", "bowl_type", "bowl_type_2", "bowl_arm", "bowl_class", "keeper", "keeper_source",
            "meta_source", "infer_confidence", "type_confidence", "p_spin", "has_meta", "batting_style_raw",
            "bowling_style_raw", "style_note", "n_matches_player", "first_date", "last_date", "n_del", "n_legal",
            "balls_T20", "balls_HUNDRED", "balls_ODI", "balls_TEST", "balls_since_2019", "n_faced", "wide_rate",
            "noball_rate", "pp_share", "death_share", "newball_share", "wickets", "stumped_share", "lbw_share",
            "bowled_share", "n_stumpings_fielded"]
CSV_COLS = ["player_id", "unique_name", "country", "gender", "bat_hand", "bowl_type", "bowl_type_2", "bowl_arm",
            "bowl_class", "keeper", "meta_source", "infer_confidence", "type_confidence"]


def assemble(players: pd.DataFrame, u: pd.DataFrame) -> pd.DataFrame:
    p = players.copy()
    for c in u.columns:
        p[c] = u[c].to_numpy()
    w = u[["w_caught", "w_bowled", "w_lbw", "w_stumped", "w_hitwkt"]].sum(axis=1).to_numpy()
    div = lambda a, b: np.where(b > 0, a / np.maximum(b, 1), np.nan).astype("float32")
    p["wickets"] = w
    p["wide_rate"], p["noball_rate"] = div(u.n_wide, u.n_del), div(u.n_nb, u.n_del)
    p["pp_share"], p["death_share"], p["newball_share"] = div(u.n_pp, u.n_lo), div(u.n_death, u.n_lo), div(u.n_newball, u.n_age)
    p["stumped_share"], p["lbw_share"], p["bowled_share"] = div(u.w_stumped, w), div(u.w_lbw, w), div(u.w_bowled, w)
    fem, tot = u.balls_female + u.n_faced_female, u.n_del + u.n_faced
    p["gender"] = np.where(tot > 0, np.where(fem * 2 > tot, "female", "male"), "unknown")
    role_k = p["role"].fillna("").str.contains("wicketkeeper", case=False).to_numpy()
    stump_k = u["n_stumpings_fielded"].to_numpy() > 0
    p["keeper"] = role_k | stump_k
    p["keeper_source"] = np.select([role_k & stump_k, role_k, stump_k], ["role+stumping", "role", "stumping"], "none")
    for c in ("cricinfo_id", "key_cricinfo", "full_name", "country", "dob", "role", "batting_style_raw", "bowling_style_raw"):
        p[c] = p[c].astype("string")
    return p[OUT_COLS]


def load_balls() -> pd.DataFrame:
    return read_table("balls", USAGE_COLS)


def build(meta_path=META_RDA, out=PLAYERS_PATH, csv=TYPES_CSV, report=REPORT_PATH, balls=None, matches=None,
          people_index=None, people=None) -> tuple[pd.DataFrame, dict]:
    people = pd.read_csv(PEOPLE_CSV, dtype=str) if people is None else people
    people_index = read_table("people_index") if people_index is None else people_index
    meta_raw = load_meta(meta_path) if isinstance(meta_path, (str, Path)) else meta_path
    meta, dedup_log = dedupe_meta(meta_raw, people)
    st = style_table(people_index, meta)
    matches = read_table("matches", ["match_id", "start_date", "team_type"]) if matches is None else matches
    balls = load_balls() if balls is None else balls
    role_keeper = st["role"].fillna("").str.contains("wicketkeeper", case=False).to_numpy()
    u = usage(balls, matches, st["bat_hand"].to_numpy(str), role_keeper)
    st, inf_rep = infer_types(st, u)
    p = assemble(st, u)
    cov = coverage(p, balls, matches, u)
    styles = Counter(meta_raw["bowling_style"].dropna())
    unmapped = {s: n for s, n in styles.items() if parse_bowling(s)["vague"]}
    rep = dict(
        rows={"players": len(p), "with_matches": int((p.n_matches_player > 0).sum()), "with_meta": int(p.has_meta.sum()),
              "with_meta_and_matches": int((p.has_meta & (p.n_matches_player > 0)).sum()),
              "player_meta_rows": len(meta_raw), "player_meta_unique": len(meta),
              "player_meta_not_in_people_csv": int((~meta["cricsheet_id"].isin(people["identifier"])).sum()),
              "player_meta_not_in_zip": int((~meta["cricsheet_id"].isin(people_index["identifier"])).sum())},
        dedup=dedup_log,
        batting_style_fixed=p.loc[p.style_note.str.contains("bowling_style_in_batting"), ["player_id", "unique_name", "bowling_style_raw"]]
        .to_dict("records"),
        style_strings=dict(n_distinct=len(styles), unmapped_vague=unmapped,
                           mapped={s: parse_bowling(s)["bowl_type"] + ("/" + parse_bowling(s)["bowl_type_2"]
                                                                       if parse_bowling(s)["bowl_type_2"] != "none" else "")
                                   for s in sorted(styles)}),
        counts=dict(meta_source=p.loc[p.n_matches_player > 0, "meta_source"].value_counts().to_dict(),
                    bowl_class=p.loc[p.n_matches_player > 0, "bowl_class"].value_counts().to_dict(),
                    bowl_type=p.loc[p.n_matches_player > 0, "bowl_type"].value_counts().to_dict(),
                    bowl_type_2=p.loc[p.n_matches_player > 0, "bowl_type_2"].value_counts().to_dict(),
                    bat_hand=p.loc[p.n_matches_player > 0, "bat_hand"].value_counts().to_dict(),
                    keeper=p.keeper_source.value_counts().to_dict(),
                    bowlers_ge_min_balls=int((p.n_legal >= MIN_BALLS).sum()),
                    bowlers_ge_min_balls_no_style=int(((p.n_legal >= MIN_BALLS) & (p.meta_source != "cricinfo_meta")).sum())),
        inference=inf_rep, coverage=cov)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        p.to_parquet(out, index=False)
    if csv:
        Path(csv).parent.mkdir(parents=True, exist_ok=True)
        c = p.loc[p.n_matches_player > 0, CSV_COLS].copy()
        c["infer_confidence"], c["type_confidence"] = c["infer_confidence"].round(3), c["type_confidence"].round(3)
        c.sort_values("player_id").to_csv(csv, index=False)
    if report:
        Path(report).parent.mkdir(parents=True, exist_ok=True)
        Path(report).write_text(json.dumps(rep, indent=1, default=str) + "\n")
    return p, rep


def main():
    p, rep = build()
    inf = rep["inference"]
    print(json.dumps(dict(rows=rep["rows"], counts=rep["counts"], cv_no_arm=inf["cv_no_arm"]["class_accuracy"],
                          cv_type_no_arm=inf["cv_no_arm"]["type_accuracy"], n_inferred=inf["n_inferred"],
                          overall_coverage=rep["coverage"]["overall"]), indent=1, default=str))


if __name__ == "__main__":
    main()
