"""Enrichment: the plan 4.2-4.3 columns the ingest leaves to the competition, rules, teams, players, venues
and weather modules, joined onto `matches` and `balls`.

Matches. `competitions_for_matches` gives competition_id, tier, event_id, the associate and official flags;
`season_key` is competition_id:season and `series_key` the competitions module's (bilateral series split by
team pair and 60-day gaps). `rules_for` (competition, date, event, teams, stage, file-stem overrides) gives
scheduled days (1 for limited overs) and overs per day, the free-hit rule and `p_free_hit_given_nb`, review
counts, the 80-over top-up and umpire's-call retention, the no-ball penalty, caught-crossing, powerplay and
fielding-restriction tables (stored as JSON), two new balls, impact player, tie-break and minimum overs.
`drs_available` is `competitions.drs_available_for_matches` (rules allow DRS AND a review in the match or
its series AND reviews not missing; null when missing). Canonical team ids and names, the as-of home status
of both sides and the start slot come from `match_teams.parquet` (teams.py); region, cricket country,
elevation and coordinates from `config/cricket-venues.csv`, with `ball_brand` the venue default for the
TEST family (Tests and multi-day domestic matches) only. `exp_loss_per_day` (TEST family) is the expected
shortfall in overs per scheduled day, opd - r with r = min(opd, overs / (D - 1 + phi)) as in plan 7.5,
averaged over strictly earlier matches only and shrunk venue -> region x month -> region -> match type with
K = 8 pseudo-matches each (a constant prior of 10 overs at the top), so it is leakage-free for every match.

Balls. Free hit: with k = `prev_free_hit_chain` (no-balls in the unbroken run of wides and no-balls just
before the delivery, so carry-over is included), `free_hit_p` = 1 - (1 - p)^k with p the rules'
`p_free_hit_given_nb` (1 for all no-balls, 0 for none, the estimated front-foot share where only front-foot
no-balls give one); `free_hit` is True at 1, False at 0 and null in between. Powerplay: the recorded window
when the innings has one (`pp_source = recorded`), else the rules' mandatory windows as pp1/pp2/pp3 (the
reduced-innings table for N = max_balls // bpo overs when the innings length known before the ball is
short, in legal balls; batting and fielding powerplays cannot be placed and read `none`). `field_restr` is
the maximum number of fielders outside the circle: by recorded level (pp1, pp2, pp3 the limit at the start
of the rules' mandatory windows 1-3, a window beyond the rules' count taking the last one's; batting /
fielding / power surge the rules' `max_outside`, else 3 / 3 / 2; `none` the rules' table at the over, the
non-powerplay limit inside the rules' first window) or by position in the rules table; null in the TEST
family. Reviews left: the rules' count per innings minus the ingest's failed
non-umpire's-call reviews, plus failed umpire's-call reviews where the rules do not retain them, counted
again from zero from over 80 where the top-up applies (Tests 2013-10 to 2017-09); null unless
`drs_available` is True; negative values (more failures than the rules allow) are clipped to 0 and counted
in the report. Batting / bowling team ids and home status follow `innings.team_idx` (1 = team1); the
striker's batting hand, the bowler's type and class, and the overseas flags (player country differs from the
venue's cricket country; club matches only, null when either is unknown) come from `players.parquet`.
`balls_enriched` is the ingest table (same rows and order, `fielders` dictionary-encoded) with these
columns appended; competition_id, season_key and tier repeat the match's for grouping in the fits.

Test clock. `est_day` is refined from the ingest's uniform rate: the overs lost over the D played days,
max(0, opd (D - 1 + phi) - overs), are spread over the days in proportion to day length (phi on the last day)
times 0.25 + s_d, s_d the day's rain severity (precipitation hours / 6, else mm / 10, else 0.5 x wet day,
else 0.3 x rain flag, capped at 1; days without data take the match's mean), capped at a full day; with no
rain anywhere this is exactly the uniform rule. The ingest's value is kept as `est_day_uniform`.
`exp_overs_left` = (S - d)(opd - L) + max(0, opd - o)(1 - L / opd): scheduled remaining overs minus the
observed shortfall so far, (d - 1) opd + o - overs bowled, minus the expected loss L for the rest of today
and every later scheduled day, d and o the refined day and overs into it. Weather: the realized match-day
row (`weather_match_day`, joined on the date of the ball's played day: `est_day` in the TEST family, the
first date otherwise) as `wx_*`; :func:`climatology_fill` replaces or fills them from
`weather.climatology(cutoff)` for clean pre-match inputs.

Limits. est_day, and so exp_overs_left, use the number of days played and the match's total overs
(ex post), as plan 7.5 accepts for training; the rain weights are a heuristic, not a calibrated loss model.
Limited-overs matches on two dates (46, reserve days) take the first date's weather for every ball. Batting
and fielding powerplays (ODIs 2005-2015, the BBL surge) are only known where Cricsheet records them, which is
nearly everywhere after 2005 (pre-2005 ODI windows come from the rules). Overseas status is judged against
the venue's country, so home players at a league's foreign season (IPL 2020 in the UAE) count as overseas,
and players without a country (16% of the register) are null.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from beating.cricket import competitions as C, ingest as IG, rules as R, venues as V

OUT_DIR = IG.OUT_DIR
BALLS_IN = OUT_DIR / "balls.parquet"
BALLS_OUT = OUT_DIR / "balls_enriched.parquet"
MATCHES_OUT = OUT_DIR / "matches_enriched.parquet"
MATCH_TEAMS = OUT_DIR / "match_teams.parquet"
PLAYERS = OUT_DIR / "players.parquet"
WEATHER_DAYS = OUT_DIR / "weather_match_day.parquet"
REPORT_PATH = IG.ROOT / "reports" / "cricket-enrich-validation.json"

PP_LEVELS = IG.PP_LEVELS
PP = {k: i for i, k in enumerate(PP_LEVELS)}
PP_SOURCES = ("recorded", "rules")
HOME = ("home", "away", "neutral")
SLOTS = ("day", "day_night", "night", "unknown")
HANDS = ("R", "L", "U")
BOWL_TYPES = ("pace_fast", "pace_medium", "off_spin", "leg_spin", "left_orth", "left_wrist", "none", "unknown")
BOWL_CLASSES = ("pace", "spin", "none", "unknown")
REGIONS = V.REGIONS
BRANDS = ("kookaburra", "dukes", "sg")
WX_SOURCES = ("isd_lite", "gsod", "none")
BIG = 10_000
LOSS_K, LOSS_PRIOR = 8.0, 10.0         # pseudo-matches per level; overs lost per day before any data
RAIN_EPS = 0.25                         # share of the loss weight every day gets regardless of rain
DAY_KEY = 64                            # per-ball (match, played-day) key: match_id * DAY_KEY + day
WX_COLS = {"wx_temp_c": "temp_c_mean", "wx_rh": "rh_mean", "wx_cloud_oktas": "cloud_oktas_mean",
           "wx_dew_dep_evening": "dew_depression_evening", "wx_precip_mm": "precip_mm_day",
           "wx_wind_ms": "wind_ms_mean", "wx_wet_day": "wet_day"}
WX_CLIMATE = {"wx_temp_c": "temp_c", "wx_rh": "rh", "wx_cloud_oktas": "cloud_oktas",
              "wx_dew_dep_evening": "dew_depression_evening", "wx_precip_mm": "precip_mm",
              "wx_wind_ms": "wind_ms", "wx_wet_day": "rain_day_freq"}
RULE_COLS = ["scheduled_days", "test_overs_per_day", "overs_per_innings", "balls_per_innings", "bowler_quota",
             "free_hit", "p_free_hit_given_nb", "noball_penalty_runs", "caught_crossing_counts", "drs_allowed",
             "drs_scope", "reviews_per_innings", "umpires_call_retains_review", "review_topup_after_80",
             "ucall_zone_era", "new_ball_after_overs", "two_new_balls", "two_new_balls_until_over", "impact_player",
             "tie_break", "min_overs_for_result", "follow_on_lead"]
RULE_RENAME = {"free_hit": "free_hit_rule", "overs_per_innings": "rules_overs_per_innings",
               "balls_per_innings": "rules_balls_per_innings"}
PP_RULE_KEYS = ("field_restr", "pp_windows", "pp_reduced_rule", "balls_per_over", "overs_per_innings")
# columns the per-ball step reads from the ingest table
BALL_INPUTS = ["match_id", "innings", "over", "ball_in_over", "legal_ball_index", "batter_id", "bowler_id",
               "review_by", "review_decision", "review_umpires_call", "bat_fail_reviews", "bowl_fail_reviews",
               "prev_free_hit_chain", "pp_window_recorded", "max_balls_known_before", "match_legal_balls",
               "est_day", "outcome_class"]


# ---------------------------------------------------------------- small helpers

def codes(values, levels) -> np.ndarray:
    """int16 codes of `values` in `levels` (-1 for null or unknown)."""
    idx = {v: i for i, v in enumerate(levels)}
    return np.array([idx.get(v, -1) if isinstance(v, str) else -1 for v in values], dtype=np.int16)


def _arrow_col(pf, name: str, fill):
    """One parquet column as numpy, nulls filled; dictionary columns as int codes with their levels."""
    import pyarrow as pa
    col = pf.read(columns=[name]).column(0).combine_chunks()
    if pa.types.is_dictionary(col.type):
        levels = col.dictionary.to_pylist()
        return col.indices.fill_null(-1).to_numpy(zero_copy_only=False).astype(np.int16), levels
    if pa.types.is_boolean(col.type):
        return col.cast(pa.int8()).fill_null(fill).to_numpy(zero_copy_only=False), None
    return col.fill_null(fill).to_numpy(zero_copy_only=False), None


def recode(c: np.ndarray, levels_from, levels_to) -> np.ndarray:
    """Map codes into one dictionary onto another (-1 stays -1)."""
    lut = np.array([levels_to.index(v) if v in levels_to else -1 for v in levels_from] + [-1], dtype=np.int16)
    return lut[c]


def _limits(fr) -> tuple:
    """(to1, l1, to2, l2, l3) of a rules field_restr table [[from, to, max_outside], ...]."""
    if not fr:
        return BIG, -1, BIG, -1, -1
    l = [int(x[2]) for x in fr]
    to = [int(x[1]) for x in fr]
    if len(fr) == 1:
        return BIG, l[0], BIG, l[0], l[0]
    if len(fr) == 2:
        return to[0], l[0], BIG, l[1], l[1]
    return to[0], l[0], to[1], l[1], l[-1]


def _max_outside(pp: dict | None, kind: str, default: int) -> int:
    w = (pp or {}).get(kind)
    return int(w["max_outside"]) if w and w.get("max_outside") is not None else default


# ---------------------------------------------------------------- matches

def match_rules(m: pd.DataFrame, comp: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Rules fields per match (RULE_COLS, renamed) and, in row order, the powerplay part of each rules dict
    (PP_RULE_KEYS)."""
    full, rows = [], []
    stages = m["event_stage"] if "event_stage" in m else [None] * len(m)
    stems = m["file_stem"] if "file_stem" in m else m["match_id"].astype(str)
    for i, (c, d, a, b, st, fs) in enumerate(zip(comp.itertuples(), m.start_date, m.team1_raw, m.team2_raw,
                                                 stages, stems)):
        if i % 1000 == 0:              # the rules cache holds every reduced-innings table: keep it small
            R._resolve.cache_clear()
        r = R.rules_for(c.competition_id, c.fmt, c.gender, d, event_id=c.event_id, teams=[a, b],
                        official=c.official or c.team_type != "international", assoc_match=c.assoc_match,
                        stage=None if pd.isna(st) else st, match_id=fs)
        full.append({k: r.get(k) for k in PP_RULE_KEYS})
        row = {k: r.get(k) for k in RULE_COLS}
        row["pp_windows_json"] = json.dumps(r.get("pp_windows"))
        row["field_restr_json"] = json.dumps(r.get("field_restr"))
        rows.append(row)
    R._resolve.cache_clear()
    IG._trim()
    out = pd.DataFrame(rows, index=m.index).rename(columns=RULE_RENAME)
    lim = m["fam"].ne("TEST")
    out["scheduled_days"] = out.scheduled_days.where(~lim, 1)
    for col in ("scheduled_days", "test_overs_per_day", "rules_overs_per_innings", "rules_balls_per_innings",
                "bowler_quota", "noball_penalty_runs", "reviews_per_innings", "new_ball_after_overs",
                "two_new_balls_until_over", "min_overs_for_result", "follow_on_lead"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int16")
    for col in ("caught_crossing_counts", "drs_allowed", "umpires_call_retains_review", "review_topup_after_80",
                "two_new_balls", "impact_player"):
        out[col] = out[col].astype("boolean")
    out["p_free_hit_given_nb"] = out.p_free_hit_given_nb.astype("float32")
    return out, full


def match_overs(innings: pd.DataFrame) -> pd.Series:
    """Legal balls bowled in each match's main innings."""
    return innings.groupby("match_id").legal_balls.sum()


def expected_loss(m: pd.DataFrame, k: float = LOSS_K, prior: float = LOSS_PRIOR) -> pd.DataFrame:
    """As-of expected overs lost per scheduled day for TEST-family matches (module docstring).

    Needs match_id, start_date, match_type, region, venue_id, opd, overs (legal overs bowled), n_dates and
    result. Returns `exp_loss_per_day` and `exp_loss_n` (earlier matches at the venue) for each row; a
    match's own outcome and those of matches on the same day never enter its value."""
    x = m.sort_values(["start_date", "match_id"])
    phi = np.where(x.result.isin(["draw", "no_result"]), 1.0, 0.5)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.minimum(x.opd, x.overs / np.maximum(x.n_dates - 1 + phi, 0.5))
    loss = np.where(x.overs > 0, np.clip(x.opd - r, 0, None), np.nan)
    month = x.start_date.str[5:7]
    keys = list(zip(x.match_type, x.match_type + "|" + x.region.fillna("other"),
                    x.match_type + "|" + x.region.fillna("other") + "|" + month, x.venue_id.fillna("?")))
    sums, cnts = {}, {}
    out_v, out_n = np.full(len(x), np.nan), np.zeros(len(x), dtype=np.int32)
    dates = x.start_date.to_numpy()
    i = 0
    while i < len(x):
        j = i
        while j < len(x) and dates[j] == dates[i]:
            j += 1
        for t in range(i, j):          # estimates from strictly earlier dates
            est = prior
            for key in keys[t]:
                est = (sums.get(key, 0.0) + k * est) / (cnts.get(key, 0) + k)
            out_v[t], out_n[t] = est, cnts.get(keys[t][3], 0)
        for t in range(i, j):
            if not np.isnan(loss[t]):
                for key in keys[t]:
                    sums[key] = sums.get(key, 0.0) + loss[t]
                    cnts[key] = cnts.get(key, 0) + 1
        i = j
    res = pd.DataFrame({"exp_loss_per_day": out_v.astype("float32"), "exp_loss_n": out_n,
                        "loss_per_day_obs": loss.astype("float32")}, index=x.index)
    return res.reindex(m.index)


def match_table(matches: pd.DataFrame, innings: pd.DataFrame, match_teams: pd.DataFrame,
                venues: pd.DataFrame, reviews_by_match) -> tuple[pd.DataFrame, list[dict]]:
    """`matches` plus every match-level enrichment column, and the rules dicts in the same row order."""
    m = matches.reset_index(drop=True).copy()
    comp = C.competitions_for_matches(m)
    m["competition_id"], m["tier"], m["event_id"] = comp.competition_id, comp.tier, comp.event_id
    m["assoc_match"], m["official"], m["competition_generic"] = comp.assoc_match, comp.official, comp.generic
    m["season_key"] = m.competition_id + ":" + m.season.astype(str)
    m["series_key"] = C.series_key(m)
    rules, full = match_rules(m, comp)
    m = pd.concat([m, rules], axis=1)
    drs = C.drs_available_for_matches(m[["match_id", "reviews_missing", "series_key", "drs_allowed"]],
                                      reviews_by_match)
    m["drs_available"], m["drs_source"] = drs.drs_available.astype("boolean"), drs.drs_source
    cols = ["team1_id", "team2_id", "team1", "team2", "home_status1", "home_status2", "home_source1",
            "home_source2", "start_slot", "start_slot_source", "start_slot_confidence"]
    mt = match_teams.drop_duplicates("match_id").set_index(match_teams.match_id.drop_duplicates().astype("int64"))
    mt = mt[cols].reindex(m.match_id.astype("int64").to_numpy())
    for c in cols:
        m[c] = mt[c].to_numpy()
    m["start_slot"] = m.start_slot.fillna("unknown")
    vt = venues.set_index("venue_id")
    for src, dst in (("region", "region"), ("cricket_country", "venue_country"), ("lat", "venue_lat"),
                     ("lon", "venue_lon"), ("elevation_m", "elevation_m"), ("ball_brand_default", "ball_brand")):
        m[dst] = m.venue_id.map(vt[src])
    m["ball_brand"] = m.ball_brand.where(m.fam.eq("TEST"))
    m["elevation_m"] = m.elevation_m.astype("float32")
    test = m.fam.eq("TEST")
    opd = m.test_overs_per_day.astype("float64").where(test).fillna(90.0)
    m["opd"] = opd.where(test).astype("float32")
    overs = m.match_id.map(match_overs(innings)).fillna(0) / m.balls_per_over
    m["overs_bowled"] = overs.astype("float32")
    t = m[test].assign(opd=opd[test], overs=overs[test])
    loss = expected_loss(t)
    for c in loss:
        m.loc[test, c] = loss[c]
    m["exp_loss_n"] = m.exp_loss_n.astype("Int16")
    for c in ("exp_loss_per_day", "loss_per_day_obs"):
        m[c] = m[c].astype("float32")
    return m.copy(), full


# ---------------------------------------------------------------- balls: rules-driven columns

def free_hit(chain: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(free_hit_p float32, free_hit int8 1/0/-1 unknown) from the no-ball chain and P(free hit | no-ball)."""
    k = chain.astype(np.float32)
    fp = np.where(k > 0, 1.0 - (1.0 - np.asarray(p, np.float32)) ** k, 0.0).astype(np.float32)
    fh = np.where(fp >= 1.0, 1, np.where(fp <= 0.0, 0, -1)).astype(np.int8)
    return fp, fh


def _mandatory_limits(r: dict) -> list[int]:
    """Fielders allowed out in the rules' mandatory windows 1..3 (a later recorded window beyond the rules'
    count, such as a split T20 powerplay, takes the last one's limit)."""
    fr = r.get("field_restr")
    wins = ((r.get("pp_windows") or {}).get("mandatory") or [])[:3]
    if not fr or not wins:
        return [-1, -1, -1]
    lims = [int(by_position(np.array([w[0]]), *_limits(fr))[0]) for w in wins]
    return (lims + [lims[-1]] * 3)[:3]


def match_pp_arrays(full: list[dict]) -> dict:
    """Per-match field-restriction segments and powerplay limits (row order of the rules list)."""
    lim = np.array([_limits(r.get("field_restr")) for r in full], dtype=np.int16).reshape(-1, 5)
    mand = np.array([_mandatory_limits(r) for r in full], dtype=np.int16).reshape(-1, 3)
    pp = [r.get("pp_windows") for r in full]
    return dict(to1=lim[:, 0], l1=lim[:, 1], to2=lim[:, 2], l2=lim[:, 3], l3=lim[:, 4],
                m1=mand[:, 0], m2=mand[:, 1], m3=mand[:, 2],
                bat=np.array([_max_outside(w, "batting", 3) for w in pp], dtype=np.int16),
                surge=np.array([_max_outside(w, "batting", 2) for w in pp], dtype=np.int16),
                fld=np.array([_max_outside(w, "fielding", 3) for w in pp], dtype=np.int16))


def by_position(pos: np.ndarray, to1, l1, to2, l2, l3) -> np.ndarray:
    return np.where(pos <= to1, l1, np.where(pos <= to2, l2, l3))


def recorded_field_restr(level: np.ndarray, over1: np.ndarray, a: dict, mi: np.ndarray) -> np.ndarray:
    """Fielders allowed outside the circle for balls with a recorded powerplay level (codes of PP_LEVELS)."""
    to1, l1, to2, l2, l3 = (a[k][mi] for k in ("to1", "l1", "to2", "l2", "l3"))
    base = by_position(over1, to1, l1, to2, l2, l3)
    none = np.where(over1 <= to1, l2, base)     # recorded 'none' inside the rules' pp1 span: non-pp limit
    out = np.select([level == PP["pp1"], level == PP["pp2"], level == PP["pp3"], level == PP["batting"],
                     level == PP["fielding"], level == PP["power_surge"]],
                    [a["m1"][mi], a["m2"][mi], a["m3"][mi], a["bat"][mi], a["fld"][mi], a["surge"][mi]], none)
    return out.astype(np.int16)


def rules_powerplay(rules: dict, over1: np.ndarray, ball1: np.ndarray, max_balls: np.ndarray) -> tuple:
    """(pp level codes, field_restr) for one unrecorded innings from the rules (full or reduced tables)."""
    bpo, n_full = rules.get("balls_per_over") or 6, rules.get("overs_per_innings")
    level = np.zeros(len(over1), dtype=np.int16)
    fr = np.full(len(over1), -1, dtype=np.int16)
    if not n_full or not rules.get("field_restr"):
        return level, fr
    full_balls, rule = n_full * bpo, rules.get("pp_reduced_rule")
    for mb in np.unique(max_balls):
        sel = max_balls == mb
        n = int(mb) // bpo if mb > 0 else n_full
        tab = (R.reduced_powerplay(rule, max(n, 1), bpo, rules["field_restr"])
               if rule and 0 < mb < full_balls else None)
        if tab:
            pos, wins, restr = ball1[sel], tab["mandatory"], tab["field_restr"]
        else:
            pos, wins, restr = over1[sel], (rules.get("pp_windows") or {}).get("mandatory") or [], rules["field_restr"]
        lv = np.zeros(sel.sum(), dtype=np.int16)
        for j, (a, b) in enumerate(wins[:3]):
            lv[(pos >= a) & (pos <= b)] = PP[("pp1", "pp2", "pp3")[j]]
        level[sel] = lv
        fr[sel] = by_position(pos, *_limits(restr))
    return level, fr


def exclusive_cumsum(x: np.ndarray, group_start: np.ndarray) -> np.ndarray:
    """Per-group running sum of x over the rows before each row (rows sorted by group)."""
    c = np.cumsum(x, dtype=np.int32)
    before = c - x
    return before - before[group_start]


def reviews_left(n_rev: np.ndarray, fails: np.ndarray, ucall_fails: np.ndarray, retains: np.ndarray,
                 topup: np.ndarray, over: np.ndarray, inn_id: np.ndarray) -> np.ndarray:
    """Reviews left before each ball for one side (int16, unclipped; n_rev < 0 means not applicable).

    fails: failed non-umpire's-call reviews so far; ucall_fails: failed umpire's-call reviews so far (they
    cost a review where `retains` is False); from over 80 under the top-up the count restarts at n_rev."""
    eff = fails.astype(np.int32) + np.where(retains, 0, ucall_fails)
    after = np.flatnonzero(topup & (over >= 80))
    if len(after):                     # rows are sorted, so the first row per innings is where over 80 starts
        ids = inn_id[after]
        _, first, inv = np.unique(ids, return_index=True, return_inverse=True)
        eff[after] -= eff[after][first][inv]
    return np.where(n_rev >= 0, n_rev - eff, -BIG).astype(np.int16)


# ---------------------------------------------------------------- balls: Test clock

def rain_severity(day: pd.DataFrame) -> np.ndarray:
    """Per match-day rain severity in [0, 1] (NaN when the day has no precipitation data)."""
    ph, mm = day.precip_hours.to_numpy(float), day.precip_mm_day.to_numpy(float)
    wet, flag = day.wet_day.to_numpy(float), day.rain_flag.to_numpy(float)
    s = np.where(~np.isnan(ph), ph / 6.0, np.where(~np.isnan(mm), mm / 10.0,
                 np.where(~np.isnan(wet), 0.5 * wet, 0.3 * flag)))
    return np.clip(s, 0.0, 1.0)


def day_capacity(opd: float, n_days: int, overs: float, phi: float, sev: np.ndarray | None = None,
                 eps: float = RAIN_EPS) -> np.ndarray:
    """Overs available on each of the D played days: the lost overs spread by day length x (eps + rain)."""
    lam = np.ones(n_days)
    lam[-1] = phi
    cap = opd * lam
    lost = max(0.0, cap.sum() - overs)
    s = np.zeros(n_days) if sev is None else np.asarray(sev, float).copy()
    if np.isnan(s).all():
        s[:] = 0.0
    else:
        s[np.isnan(s)] = np.nanmean(s)
    w = lam * (eps + s)
    loss, free = np.zeros(n_days), np.ones(n_days, bool)
    for _ in range(n_days):            # water-filling: a day cannot lose more than its length
        left = lost - loss[~free].sum()
        if left <= 1e-9 or not free.any():
            break
        share = np.where(free, w, 0.0)
        share = share if share.sum() > 0 else np.where(free, lam, 0.0)
        loss = np.where(free, left * share / share.sum(), loss)
        over = free & (loss > cap)
        if not over.any():
            break
        loss[over], free = cap[over], free & ~over
    return cap - np.minimum(loss, cap)


def clock_position(mo: np.ndarray, cap: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(est_day 1..D, overs into that day) for match overs bowled `mo` with per-day capacities `cap`."""
    end = np.cumsum(cap)
    d = np.searchsorted(end[:-1], mo, side="right")
    start = np.concatenate([[0.0], end])[d]
    return (d + 1).astype(np.int8), (mo - start).astype(np.float32)


def expected_overs_left(sched_days, opd, loss, day, into) -> np.ndarray:
    """(S - d)(opd - L) + max(0, opd - o)(1 - L / opd), floored at 0 (module docstring)."""
    rest = np.maximum(sched_days - day, 0) * (opd - loss)
    today = np.where(day <= sched_days, np.maximum(opd - into, 0) * (1 - loss / opd), 0.0)
    return np.maximum(rest + today, 0).astype(np.float32)


def played_days(m: pd.DataFrame, wx: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, played day k = 1..D) with its date, key and the realized weather row."""
    rows = [(mid, k, d) for mid, dp in zip(m.match_id, m.dates_played) for k, d in enumerate(json.loads(dp), 1)]
    days = pd.DataFrame(rows, columns=["match_id", "day_k", "date"])
    days["date"] = pd.to_datetime(days.date)
    w = wx.assign(match_id=wx.match_id.astype("int64"), date=pd.to_datetime(wx.date))
    w = w.drop_duplicates(["match_id", "date"])
    cols = ["source", "precip_hours", "rain_flag"] + list(dict.fromkeys(WX_COLS.values()))
    days = days.merge(w[["match_id", "date"] + cols], on=["match_id", "date"], how="left")
    days["key"] = days.match_id.astype(np.int64) * DAY_KEY + days.day_k
    return days.sort_values("key").reset_index(drop=True)


def test_clock(b: dict, m: pd.DataFrame, days: pd.DataFrame, mi: np.ndarray) -> dict:
    """Refined est_day / est_overs_into_day and exp_overs_left for TEST-family balls (others null)."""
    n = len(mi)
    est = np.full(n, -1, dtype=np.int8)
    into = np.full(n, np.nan, dtype=np.float32)
    left = np.full(n, np.nan, dtype=np.float32)
    sev_all = rain_severity(days)
    dstart = np.searchsorted(days.key.to_numpy(), m.match_id.to_numpy(np.int64) * DAY_KEY + 1)
    mids = b["match_id"]
    bounds = np.searchsorted(mids, m.match_id.to_numpy(), side="left"), np.searchsorted(mids, m.match_id.to_numpy(), side="right")
    for i in np.flatnonzero(m.fam.eq("TEST").to_numpy()):
        lo, hi = bounds[0][i], bounds[1][i]
        if hi <= lo:
            continue
        r = m.iloc[i]
        nd = max(int(r.n_dates), 1)
        bpo, opd = int(r.balls_per_over), float(r.opd)
        overs = float(r.overs_bowled)
        phi = 1.0 if r.result in ("draw", "no_result") else 0.5
        sev = sev_all[dstart[i]:dstart[i] + nd] if len(sev_all) else None
        if sev is not None and len(sev) != nd:
            sev = None
        cap = day_capacity(opd, nd, overs, phi, sev)
        mo = b["match_legal_balls"][lo:hi] / bpo
        d, o = clock_position(mo, cap)
        est[lo:hi], into[lo:hi] = d, o
        sd, loss = r.scheduled_days, r.exp_loss_per_day
        sd = float(sd) if pd.notna(sd) else float(nd)
        left[lo:hi] = expected_overs_left(sd, opd, float(loss) if pd.notna(loss) else LOSS_PRIOR, d, o)
    return dict(est_day=est, est_overs_into_day=into, exp_overs_left=left)


# ---------------------------------------------------------------- balls: everything

def match_index(m: pd.DataFrame, mid: np.ndarray) -> np.ndarray:
    """Row of `m` for each ball's match_id (int32)."""
    ids = m.match_id.to_numpy()
    order = np.argsort(ids, kind="stable")
    return order[np.searchsorted(ids[order], mid)].astype(np.int32)


def ball_columns(b: dict, levels: dict, m: pd.DataFrame, full: list[dict], innings: pd.DataFrame,
                 players: pd.DataFrame, days: pd.DataFrame) -> tuple[dict, dict]:
    """New per-ball arrays (codes for categoricals, -1 / NaN for null) and their category levels.

    `b` holds the BALL_INPUTS columns as numpy (sorted by match_id, innings, ball_seq), categorical ones as
    codes into `levels`; `m` is the match_table output (with `overs_bowled`), `full` its rules dicts."""
    mid = b["match_id"]
    mi = match_index(m, mid)
    n, out, lv = len(mid), {}, {}
    fam = m.fam.to_numpy()[mi]
    test = fam == "TEST"

    # competition and season
    for col in ("competition_id", "season_key", "tier"):
        cats = sorted(m[col].dropna().unique())
        out[col], lv[col] = codes(m[col], cats)[mi], cats

    # free hit
    p = m.p_free_hit_given_nb.astype("float64").fillna(0.0).to_numpy(np.float32)[mi]
    out["free_hit_p"], out["free_hit"] = free_hit(b["prev_free_hit_chain"], p)
    del p

    # powerplay window, its source and fielding restrictions
    rec = recode(b["pp_window_recorded"], levels["pp_window_recorded"], list(PP_LEVELS))
    over1 = b["over"].astype(np.int32) + 1
    a = match_pp_arrays(full)
    level = np.where(rec >= 0, rec, PP["none"]).astype(np.int16)
    fr = np.where(rec >= 0, recorded_field_restr(rec, over1, a, mi), -1).astype(np.int16)
    src = np.where(rec >= 0, 0, 1).astype(np.int16)
    todo = (rec < 0) & ~test
    if todo.any():
        key = mid.astype(np.int64)[todo] * 8 + b["innings"][todo]
        idx = np.flatnonzero(todo)
        for k in np.unique(key):
            sel = idx[key == k]
            lvl, f = rules_powerplay(full[mi[sel[0]]], over1[sel], b["legal_ball_index"][sel].astype(np.int32) + 1,
                                     b["max_balls_known_before"][sel].astype(np.int32))
            level[sel], fr[sel] = lvl, f
    fr[test] = -1
    out["pp_window"], out["pp_source"], out["field_restr"] = level.astype(np.int8), src.astype(np.int8), fr.astype(np.int8)
    del rec, over1, level, fr, src, todo
    lv["pp_window"], lv["pp_source"] = list(PP_LEVELS), list(PP_SOURCES)

    # DRS and reviews left
    drs = m.drs_available.astype("float64").fillna(-1).to_numpy().astype(np.int8)[mi]
    out["drs_available"] = drs
    n_rev = m.reviews_per_innings.astype("float64").fillna(-1).to_numpy().astype(np.int8)[mi]
    n_rev = np.where(drs == 1, n_rev, -1).astype(np.int8)
    retains = m.umpires_call_retains_review.fillna(False).astype(bool).to_numpy()[mi]
    topup = m.review_topup_after_80.fillna(False).astype(bool).to_numpy()[mi]
    inn_key = mid.astype(np.int64) * 8 + b["innings"]
    starts = np.r_[0, np.flatnonzero(np.diff(inn_key)) + 1].astype(np.int32)
    inn_id = np.repeat(np.arange(len(starts), dtype=np.int32), np.diff(np.r_[starts, n]))
    rby = recode(b["review_by"], levels["review_by"], ["bat", "bowl"])
    struck = recode(b["review_decision"], levels["review_decision"], ["struck_down"]) == 0
    ucall = b["review_umpires_call"] == 1
    for side, j in (("bat", 0), ("bowl", 1)):
        uc = exclusive_cumsum((struck & ucall & (rby == j)).astype(np.int32), starts[inn_id])
        raw = reviews_left(n_rev, b[f"{side}_fail_reviews"], uc, retains, topup, b["over"], inn_id)
        out[f"_{side}_reviews_raw"] = raw
        out[f"{side}_reviews_left"] = np.where(raw == -BIG, -1, np.maximum(raw, 0)).astype(np.int8)
    del inn_id, rby, struck, ucall, uc, n_rev, retains, topup, drs

    # teams, home status and start slot
    ik = innings.match_id.to_numpy(np.int64) * 8 + innings.innings.to_numpy()
    io = np.argsort(ik)
    pos = np.clip(np.searchsorted(ik[io], inn_key), 0, len(ik) - 1).astype(np.int32)
    tidx = np.where(ik[io][pos] == inn_key, innings.team_idx.to_numpy()[io][pos], 0).astype(np.int8)
    del pos, inn_key
    t1 = tidx == 1
    teams = sorted(set(m.team1_id.dropna()) | set(m.team2_id.dropna()))
    c1, c2 = codes(m.team1_id, teams)[mi], codes(m.team2_id, teams)[mi]
    h1, h2 = codes(m.home_status1, HOME)[mi], codes(m.home_status2, HOME)[mi]
    known = tidx > 0
    out["bat_team_id"] = np.where(known, np.where(t1, c1, c2), -1).astype(np.int16)
    out["bowl_team_id"] = np.where(known, np.where(t1, c2, c1), -1).astype(np.int16)
    out["bat_home_status"] = np.where(known, np.where(t1, h1, h2), -1).astype(np.int16)
    out["bowl_home_status"] = np.where(known, np.where(t1, h2, h1), -1).astype(np.int16)
    out["start_slot"] = codes(m.start_slot, SLOTS)[mi]
    lv.update(bat_team_id=teams, bowl_team_id=teams, bat_home_status=list(HOME), bowl_home_status=list(HOME),
              start_slot=list(SLOTS))

    # players: hand, bowling type and class, overseas
    pid = players.person_id.to_numpy()
    size = int(max(pid.max(), b["batter_id"].max(), b["bowler_id"].max())) + 2

    def per_person(col, cats):
        arr = np.full(size, -1, dtype=np.int16)
        arr[pid] = codes(players[col], cats)
        return arr

    bat, bowl = b["batter_id"], b["bowler_id"]
    out["striker_hand"] = per_person("bat_hand", HANDS)[bat]
    out["bowler_type"] = per_person("bowl_type", BOWL_TYPES)[bowl]
    out["bowler_class"] = per_person("bowl_class", BOWL_CLASSES)[bowl]
    lv.update(striker_hand=list(HANDS), bowler_type=list(BOWL_TYPES), bowler_class=list(BOWL_CLASSES))
    countries = sorted(set(players.country.dropna()) | set(m.venue_country.dropna()))
    pc = per_person("country", countries)
    vc = codes(m.venue_country, countries)[mi]
    club = (m.team_type.to_numpy() == "club")[mi]
    for name, who in (("striker_overseas", bat), ("bowler_overseas", bowl)):
        c = pc[who]
        out[name] = np.where(club & (c >= 0) & (vc >= 0), (c != vc).astype(np.int8), -1).astype(np.int8)

    # venue
    out["region"] = codes(m.region, REGIONS)[mi]
    out["elevation_m"] = m.elevation_m.to_numpy(np.float32)[mi]
    out["ball_brand"] = codes(m.ball_brand, BRANDS)[mi]
    lv.update(region=list(REGIONS), ball_brand=list(BRANDS))

    # Test clock and expected overs left
    out["est_day_uniform"] = b["est_day"].astype(np.int8)
    out.update(test_clock(b, m, days, mi))

    # realized weather on the ball's played day
    key = mid.astype(np.int64) * DAY_KEY + np.where(test & (out["est_day"] > 0), out["est_day"], 1)
    dkeys = days.key.to_numpy()
    p = np.clip(np.searchsorted(dkeys, key), 0, len(dkeys) - 1).astype(np.int32)
    hit = dkeys[p] == key
    del key
    for col, src_col in WX_COLS.items():
        v = days[src_col].to_numpy(np.float32)
        out[col] = np.where(hit, v[p], np.nan).astype(np.float32)
    out["wx_source"] = np.where(hit, codes(days.source, WX_SOURCES)[p], -1).astype(np.int16)
    lv["wx_source"] = list(WX_SOURCES)
    return out, lv


# ---------------------------------------------------------------- climatology fill

def climatology_fill(frame: pd.DataFrame, matches: pd.DataFrame, cutoff, replace: bool = True,
                     clim: pd.DataFrame | None = None) -> pd.DataFrame:
    """`wx_*` columns of a ball (or match) frame from the venue x month climatology of match days strictly
    before `cutoff` (weather.climatology), leakage-free for matches on or after it.

    `frame` needs match_id (and est_day for TEST balls; other rows use the first played date); `matches`
    is matches_enriched (venue_id, fam, dates_played). replace=True overwrites every value (clean pre-match
    inputs); False fills only missing ones. Adds `wx_clim` (1 where a value came from the climatology)."""
    from beating.cricket import weather as W

    clim = W.climatology(cutoff) if clim is None else clim
    rows = [(mid, k, d, v) for mid, dp, v in zip(matches.match_id, matches.dates_played, matches.venue_id)
            for k, d in enumerate(json.loads(dp), 1)]
    days = pd.DataFrame(rows, columns=["match_id", "day_k", "date", "venue_id"])
    days["month"] = pd.to_datetime(days.date).dt.month
    days["key"] = days.match_id.astype(np.int64) * DAY_KEY + days.day_k
    days = days.sort_values("key").reset_index(drop=True)
    look = clim.set_index(["venue_id", "month"]).reindex(pd.MultiIndex.from_arrays([days.venue_id, days.month]))
    mid = frame.match_id.to_numpy(np.int64)
    day = frame.est_day.to_numpy(float) if "est_day" in frame else np.ones(len(frame))
    day = np.where(np.isnan(day) | (day < 1), 1, day).astype(np.int64)
    dkeys = days.key.to_numpy()
    p = np.clip(np.searchsorted(dkeys, mid * DAY_KEY + day), 0, len(dkeys) - 1)
    p = np.where(dkeys[p] == mid * DAY_KEY + day, p, np.searchsorted(dkeys, mid * DAY_KEY + 1).clip(0, len(dkeys) - 1))
    hit = dkeys[p] // DAY_KEY == mid
    out = frame.copy()
    filled = np.zeros(len(frame), dtype=bool)
    for col, f in WX_CLIMATE.items():
        val = np.where(hit, look[f].to_numpy(np.float32)[p], np.nan).astype(np.float32)
        cur = out[col].to_numpy(np.float32, na_value=np.nan) if col in out else np.full(len(out), np.nan, np.float32)
        use = np.ones(len(out), bool) if replace else np.isnan(cur)
        out[col] = np.where(use, val, cur).astype(np.float32)
        filled |= use & ~np.isnan(val)
    out["wx_clim"] = filled.astype(np.int8)
    return out


# ---------------------------------------------------------------- reading and writing

def load_inputs(balls_path: Path | str = BALLS_IN) -> tuple[dict, dict, int]:
    """BALL_INPUTS columns of the ingest ball table as numpy (codes for dictionary columns)."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(balls_path)
    fills = {"batter_id": -1, "bowler_id": -1, "review_umpires_call": -1, "max_balls_known_before": -1,
             "est_day": -1, "outcome_class": -1}
    b, levels = {}, {}
    for c in BALL_INPUTS:
        arr, lev = _arrow_col(pf, c, fills.get(c, 0))
        b[c] = arr
        if lev is not None:
            levels[c] = lev
    return b, levels, pf.metadata.num_rows


def _to_arrow(name: str, arr: np.ndarray, levels: dict):
    import pyarrow as pa
    if name in levels:
        cats = levels[name]
        typ = pa.int8() if len(cats) < 127 else pa.int16()
        idx = pa.array(arr.astype(np.int8 if typ == pa.int8() else np.int16), mask=arr < 0, type=typ)
        return pa.DictionaryArray.from_arrays(idx, pa.array(cats, type=pa.string()))
    if arr.dtype.kind == "f":
        return pa.array(arr, mask=np.isnan(arr), type=pa.float32())
    if name in BOOL_COLS:
        return pa.array(arr == 1, mask=arr < 0, type=pa.bool_())
    return pa.array(arr, mask=arr < 0, type=pa.from_numpy_dtype(arr.dtype))


BOOL_COLS = {"free_hit", "drs_available", "striker_overseas", "bowler_overseas"}
REPLACED = ("est_day", "est_overs_into_day")


def write_balls(new: dict, levels: dict, src: Path | str = BALLS_IN, out: Path | str = BALLS_OUT,
                batch: int = 1_000_000) -> dict:
    """Stream the ingest ball table and write it with the new columns (est_day / est_overs_into_day
    replaced in place by the refined values; the `fielders` JSON strings dictionary-encoded, which reads
    back as a categorical about 200 MB smaller than the object column)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(src)
    names = [k for k in new if not k.startswith("_")]
    writer, off = None, 0
    for rb in pf.iter_batches(batch_size=batch):
        t = pa.Table.from_batches([rb])
        k = t.num_rows
        for c in REPLACED:
            i = t.schema.get_field_index(c)
            t = t.set_column(i, c, _to_arrow(c, new[c][off:off + k], levels))
        i = t.schema.get_field_index("fielders")
        if i >= 0 and pa.types.is_string(t.schema.field(i).type):
            t = t.set_column(i, "fielders", pc.dictionary_encode(t.column(i)))
        for c in names:
            if c not in REPLACED:
                t = t.append_column(c, _to_arrow(c, new[c][off:off + k], levels))
        if writer is None:
            writer = pq.ParquetWriter(out, t.schema, compression="zstd")
        writer.write_table(t, row_group_size=batch)
        off += k
    writer.close()
    return {"rows": off, "mb": round(Path(out).stat().st_size / 2 ** 20, 1)}


def write_matches(m: pd.DataFrame, out: Path | str = MATCHES_OUT) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq
    m = m.copy()
    for c in m.columns:
        if m[c].dtype == object:
            m[c] = m[c].astype("string")
    pq.write_table(pa.Table.from_pandas(m, preserve_index=False), out, compression="zstd")
    return {"rows": len(m), "mb": round(Path(out).stat().st_size / 2 ** 20, 2)}


# ---------------------------------------------------------------- validation

ERAS = ("-2009", "2010-14", "2015-19", "2020-")
FAMS = ("T20", "HUNDRED", "ODI", "TEST")


def _era(year: np.ndarray) -> np.ndarray:
    return np.searchsorted(np.array([2010, 2015, 2020]), year, side="right")


def _null(v: np.ndarray) -> np.ndarray:
    return np.isnan(v) if v.dtype.kind == "f" else v < 0


def _shares(v: np.ndarray, cats, mask=None) -> dict:
    v = v if mask is None else v[mask]
    n = max(len(v), 1)
    out = {c: round(float((v == i).sum()) / n, 4) for i, c in enumerate(cats)}
    out["null"] = round(float((v < 0).sum()) / n, 4)
    return out


def validate(b: dict, new: dict, lv: dict, m: pd.DataFrame, top: int = 25) -> dict:
    """Validation statistics for the enriched tables (plan 4.2-4.3; see the build tool)."""
    mid = b["match_id"]
    mi = match_index(m, mid)
    year = m.start_date.str[:4].astype(np.int16).to_numpy()[mi]
    fam = codes(m.fam, FAMS)[mi]
    era = _era(year).astype(np.int16)
    g = (fam * len(ERAS) + era).astype(np.int16)
    ng = len(FAMS) * len(ERAS)
    size = np.bincount(g, minlength=ng)
    rep = {"rows": int(len(mid)), "matches": int(len(m))}

    # null rates per column by family and era
    nulls = {}
    for c, v in new.items():
        if c.startswith("_"):
            continue
        cnt = np.bincount(g, weights=_null(v), minlength=ng)
        nulls[c] = {f"{FAMS[i // 4]} {ERAS[i % 4]}": round(float(cnt[i] / size[i]), 4) for i in range(ng) if size[i]}
    rep["null_rates"] = {"groups_rows": {f"{FAMS[i // 4]} {ERAS[i % 4]}": int(size[i]) for i in range(ng) if size[i]},
                         "columns": nulls}

    # DRS availability by competition season
    d = m.assign(v=m.drs_available.astype("float64"))
    keys = d.groupby("competition_id").drs_allowed.apply(lambda s: bool(s.fillna(False).any()))
    seasons = {}
    for sk, x in d[d.competition_id.map(keys)].groupby("season_key"):
        seasons[sk] = [int(len(x)), int((x.v == 1).sum()), int((x.v == 0).sum()), int(x.v.isna().sum())]
    by_year = d.groupby([d.fam, d.gender, d.team_type, d.start_date.str[:4]]).v.agg(
        lambda s: round(float((s == 1).mean()), 3))
    rep["drs"] = {"note": "per season key: [matches, available, not available, null (reviews missing)]",
                  "source_counts": m.drs_source.value_counts().to_dict(), "by_season_key": seasons,
                  "share_available_by_fam_gender_type_year": {" ".join(k): v for k, v in by_year.items()}}

    # reviews left
    rl = {}
    for side in ("bat", "bowl"):
        v, raw = new[f"{side}_reviews_left"], new[f"_{side}_reviews_raw"]
        dist = {}
        for i in range(ng):
            sel = (g == i) & (v >= 0)
            if sel.any():
                vc = np.bincount(np.minimum(v[sel], 4), minlength=5)
                dist[f"{FAMS[i // 4]} {ERAS[i % 4]}"] = {str(k) if k < 4 else "4+": int(c) for k, c in enumerate(vc)}
        neg = (raw < 0) & (raw > -BIG)
        ex = []
        if neg.any():
            inn = mid.astype(np.int64)[neg] * 8 + b["innings"][neg]
            u, first = np.unique(inn, return_index=True)
            for k in u[:top]:
                sel = np.flatnonzero(neg)[inn == k]
                r = m.iloc[mi[sel[0]]]
                ex.append({"match_id": int(r.match_id), "innings": int(k % 8), "date": r.start_date,
                           "competition_id": r.competition_id, "reviews_per_innings": int(r.reviews_per_innings),
                           "min_left_raw": int(raw[sel].min())})
            n_inn = int(len(u))
        else:
            n_inn = 0
        rl[side] = {"distribution": dist, "negative_rows": int(neg.sum()), "negative_innings": n_inn,
                    "negative_examples": ex}
    rep["reviews_left"] = rl

    # free hits
    chain = b["prev_free_hit_chain"] > 0
    fh, fp = new["free_hit"], new["free_hit_p"]
    out6 = b["outcome_class"] == 6
    fhr = {}
    lim = fam != FAMS.index("TEST")
    for f in range(3):
        for y in np.unique(year[lim & (fam == f)]):
            sel = (fam == f) & (year == y)
            fhr[f"{FAMS[f]} {y}"] = {"after_noball": int((sel & chain).sum()), "free_hit": int((sel & (fh == 1)).sum()),
                                     "uncertain": int((sel & (fh < 0)).sum()),
                                     "expected_free_hits": round(float(fp[sel].sum()), 1)}
    normal = lim & ~chain
    rate = lambda s: round(float(out6[s].mean()), 5) if s.any() else None
    rep["free_hit"] = {"by_fam_year": fhr, "bowler_credited_out_rate": {
        "free_hit_certain": rate(fh == 1), "free_hit_uncertain": rate(fh < 0), "no_free_hit_after_noball": rate(chain & (fh == 0) & lim),
        "normal_limited_overs": rate(normal),
        "note": "class 6 (bowler-credited out) should be near zero on free hits; on uncertain balls it sits "
                "between, in proportion to 1 - p"}}

    # home status
    hs = {}
    for (tt, tier), x in m.groupby(["team_type", "tier"]):
        pair = (x.home_status1.fillna("null") + "/" + x.home_status2.fillna("null")).value_counts()
        hs[f"{tt} {tier}"] = {"matches": int(len(x)), "pairs": pair.to_dict()}
    tier_b = codes(m.tier, lv["tier"])[mi]
    rep["home_status"] = {"matches": hs, "ball_bat_home_status_by_tier": {
        t: _shares(new["bat_home_status"], HOME, tier_b == i) for i, t in enumerate(lv["tier"])}}

    # weather coverage by year
    wy = {}
    for y in np.unique(year):
        sel = year == y
        wy[str(y)] = {"rows": int(sel.sum()), "temp": round(float((~np.isnan(new["wx_temp_c"][sel])).mean()), 4),
                      "precip": round(float((~np.isnan(new["wx_precip_mm"][sel])).mean()), 4),
                      "cloud": round(float((~np.isnan(new["wx_cloud_oktas"][sel])).mean()), 4),
                      "dew_dep": round(float((~np.isnan(new["wx_dew_dep_evening"][sel])).mean()), 4)}
    rep["weather_coverage_by_year"] = wy
    rep["weather_source"] = _shares(new["wx_source"], WX_SOURCES)

    # Test clock
    t = fam == FAMS.index("TEST")
    ch = t & (new["est_day"] != new["est_day_uniform"])
    xt = m[m.fam.eq("TEST")]
    starts = t & (np.r_[True, np.diff(mid.astype(np.int64) * 8 + b["innings"]) != 0])
    eol = {}
    for k in (1, 2, 3, 4):
        sel = starts & (b["innings"] == k)
        v = new["exp_overs_left"][sel]
        if len(v):
            eol[f"innings{k}_start"] = [round(float(q), 1) for q in np.nanpercentile(v, [10, 50, 90])]
    res = m.result.to_numpy()[mi]
    for lab, cond in (("draw", res == "draw"), ("result", res != "draw")):
        sel = starts & (b["innings"] == 4) & cond
        eol[f"innings4_start_median_{lab}"] = round(float(np.nanmedian(new["exp_overs_left"][sel])), 1) if sel.any() else None
    obs, est = xt.loss_per_day_obs.astype(float), xt.exp_loss_per_day.astype(float)
    ok = obs.notna()
    rep["test_clock"] = {
        "balls": int(t.sum()), "est_day_changed_share": round(float(ch.sum() / max(t.sum(), 1)), 4),
        "est_day_shift": {str(k): int(v) for k, v in zip(*np.unique(new["est_day"][ch].astype(int) - new["est_day_uniform"][ch], return_counts=True))},
        "exp_overs_left_p10_p50_p90": eol,
        "exp_loss_per_day": {"mean_observed": round(float(obs.mean()), 2), "mean_asof": round(float(est.mean()), 2),
                             "rmse_asof": round(float(np.sqrt(((obs - est)[ok] ** 2).mean())), 2),
                             "rmse_overall_mean_leaky": round(float(obs[ok].std(ddof=0)), 2),
                             "rmse_constant_prior": round(float(np.sqrt(((obs - LOSS_PRIOR)[ok] ** 2).mean())), 2),
                             "by_region_mean_observed": xt.groupby("region").loss_per_day_obs.mean().round(2).to_dict()}}

    # powerplays and fielding restrictions
    pp = {}
    for f in range(3):
        sel = fam == f
        if not sel.any():
            continue
        lvl, fr = new["pp_window"][sel], new["field_restr"][sel]
        pp[FAMS[f]] = {"source": _shares(new["pp_source"][sel], PP_SOURCES),
                       "field_restr_by_window": {PP_LEVELS[i]: {str(k): int(c) for k, c in zip(*np.unique(fr[lvl == i], return_counts=True))}
                                                 for i in range(len(PP_LEVELS)) if (lvl == i).any()}}
    src_era = {f"{FAMS[i // 4]} {ERAS[i % 4]}": round(float(np.mean(new["pp_source"][g == i] == 1)), 4)
               for i in range(ng) if size[i] and i // 4 < 3}
    rep["powerplay"] = {"by_fam": pp, "rules_derived_share_by_fam_era": src_era}

    # players and overseas
    club = (m.team_type.to_numpy() == "club")[mi]
    comp = codes(m.competition_id, lv["competition_id"])[mi]
    ov = {}
    top_c = pd.Series(comp[club]).value_counts().head(top).index
    for c in top_c:
        sel = comp == c
        v = new["striker_overseas"][sel]
        ov[lv["competition_id"][c]] = {"balls": int(sel.sum()), "striker_overseas": round(float((v == 1).mean()), 4),
                                       "striker_null": round(float((v < 0).mean()), 4),
                                       "bowler_overseas": round(float((new["bowler_overseas"][sel] == 1).mean()), 4)}
    rep["overseas_by_competition"] = ov
    rep["players"] = {f"{FAMS[i // 4]} {ERAS[i % 4]}": {
        "striker_hand_U": round(float(np.mean(new["striker_hand"][g == i] == HANDS.index("U"))), 4),
        "bowler_class_unknown_or_none": round(float(np.mean(new["bowler_class"][g == i] >= 2)), 4)}
        for i in range(ng) if size[i]}
    return rep
