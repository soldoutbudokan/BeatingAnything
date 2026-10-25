"""Cricsheet JSON -> canonical cricket tables (plan sections 4.2-4.4, 6.5, 6.6 and 7.5).

Method. Pass 1 reads only each file's info block and gives every registry identifier a dense int
`person_id` (sorted by identifier). Pass 2 parses every match, in worker processes, with one state
machine per main innings that records the state *before* each delivery: runs (from
`penalty_runs.pre`), wickets (retired out and timed out count, retired hurt / not out do not),
unavailable batters (wickets + absent hurt + batters currently off the field after a retirement), each
batter's runs and balls (legal balls and no-balls), the partnership (reset on any change of the batting
pair, so temporary retirements reset it too), arrival rank (first appearance as striker or non-striker,
striker first; a resuming batter keeps his rank), the bowler's legal balls and spell (consecutive
alternate overs k-2, k-4 bowled; in the Hundred alternate 10-ball blocks plus an earlier set in the same
block), powerplay window, failed reviews so far and the previous delivery's type. Departures without a
wicket are temporary retirements when the innings has a role-batter replacement naming that batter, else
`unexplained_departure` events; both, with resumptions, go to `events`.

Targets follow the data audit: `target.overs` is overs.balls notation ('40.2' = 242 balls, Hundred
'8.4' = 44); a stored target is `original` when its length is the scheduled one and either there is no
revision method (D/L, VJD) or its runs equal innings 1's total + 1; `pre_inn2` when it was reduced and
there is no method, or innings 1 was cut (not all out) at exactly the target length; otherwise `unknown`.
Without a stored target, innings-1 total + 1 is used when there is no method and innings 2 ended
normally. `max_balls_known_before` is the scheduled length, the target length in innings 2 when the
timing is original/pre_inn2, and the target length in innings 1 only when the reduction was equal with no
method and innings 1 did not exceed it (taken as a pre-match reduction). Tests get the aggregate lead
(negative after a follow-on) and an innings-4 target from aggregates.

On-field reconstruction (plan 6.5) runs on legal deliveries whose review concerns the recorded wicket:
an upheld batting review without a wicket is an on-field bowler-credited out (class 6) whose kind is
imputed after the parse: lbw with probability equal to the lbw share of struck-down lbw/caught batting
reviews in the same fitting family and year (shrunk to the family share with 20 pseudo-reviews), drawn
with a fixed hash of (match_id, innings, ball_seq) so the build is reproducible and the imputed mix
matches that share; `onfield_wk_p_lbw` keeps the probability. An upheld fielding review is an on-field
dot. Reviews on wides and no-balls, technical failures, reviews of another batter than the one out and
reviews that disagree with the recorded wicket leave the recorded outcome as the on-field one.

Umpire ends (plan 6.6): within an innings, named reviews (not run-out/stumping rows) and named
`miscounted_overs` entries are votes for umpire 1 standing at even or odd units (overs; Hundred
floor(set/2)); with n agreeing votes p = 0.98^n / (0.98^n + 0.02^n), conflicting votes or none give 0.5.
`est_day` (Tests) uses D = len(dates), r = min(opd, overs_total / (D - 1 + phi)), phi 0.5 for a result
and 1 for a draw, opd 98 when the rules timeline schedules four days and 90 otherwise. Player context
(`striker_exp`, `bowler_exp`: prior balls faced / legal balls bowled; `striker_role_pos`: median arrival
over the previous 10 innings) uses strictly earlier dates in the same fitting family and gender.

Tables (data/processed/cricket/*.parquet; `tools/build_cricket_tables.py` runs the build): `balls` (one row
per main-innings delivery), `matches`, `innings` (JSON totals next to the state machine's, targets, umpire
votes), `events` (retirements, timed out, absent hurt, temporary retirement / resumption, replacements,
mid-over bowler changes, a second ball-wicket on one delivery, declarations, forfeitures, follow-ons,
penalty runs, miscounted overs, interruptions inferred from targets), `super_overs`, `player_innings`
(arrival, balls faced, balls bowled per player and innings) and `people_index`. In memory, missing ints
are -1 (-32768 for `lead` and `runs_required`) and categoricals are int8 codes; on disk they are real
nulls and dictionary columns, and :func:`read_table` returns pandas nullable dtypes only for columns that
hold nulls. `prev_free_hit_chain` is the number of no-balls in the unbroken run of wides and no-balls just
before the delivery, so the enrichment step can apply any free-hit rule. Non-numeric file stems
('wi_201706') get match_id 90,000,000 + number.

Limits. Only the final revised target is stored by Cricsheet, so revisions during innings 2 are
`unknown`. The timed-out and retired-out entries are non-ball events (the delivery is coded from its own
outcome). Absent-hurt batters count as unavailable from the first ball. Hundred spells and bowler ends
are approximate, and with three or four listed umpires only the first two are used for ends.
Overturned-kind imputation is a mix-preserving rule, not an observation. Columns that
need the competition, rules, teams or weather modules (competition_id, scheduled_days, home status,
start_slot, drs_available, free_hit, pp windows from rules, overseas flags) are left to the enrichment
step; this module only adds `venue_id`.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
import multiprocessing as mp
from pathlib import Path
import resource
import statistics
import time
import zipfile
import zlib

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CRICSHEET_ZIP = ROOT / "data" / "raw" / "cricsheet" / "all_json.zip"
PEOPLE_CSV = ROOT / "data" / "raw" / "cricsheet" / "people.csv"
OUT_DIR = ROOT / "data" / "processed" / "cricket"
REPORT_PATH = ROOT / "reports" / "cricket-ingest-validation.json"

FAMILY = {"T20": "T20", "IT20": "T20", "ODI": "ODI", "ODM": "ODI", "Test": "TEST", "MDM": "TEST"}
FIT_FAMILY = {"T20": "T20", "HUNDRED": "T20", "ODI": "ODI", "TEST": "TEST"}
DEFAULT_OVERS = {"T20": 20, "HUNDRED": 20, "ODI": 50}
UCALL_FIRST = {"TEST": "2017-08-25", "ODI": "2017-10-16", "T20": "2017-12-24", "HUNDRED": "2021-07-30"}
REVISION_METHODS = {"D/L", "DLS", "VJD"}
NAME_ERROR = 0.02
OPD, OPD_FOUR_DAY = 90, 98
ROLE_WINDOW = 10
KIND_SHRINK = 20.0
NA, NA16 = -1, -32768

FAMS = ("T20", "HUNDRED", "ODI", "TEST")
GENDERS = ("male", "female")
DTYPES = ("legal", "wide", "noball")
KINDS_RAW = ("caught", "caught and bowled", "bowled", "lbw", "stumped", "run out", "hit wicket",
             "obstructing the field", "handled the ball", "hit the ball twice", "timed out", "retired hurt",
             "retired not out", "retired out")
WK = ("caught", "bowled", "lbw", "stumped", "run_out", "other")
WK_OF = {"caught": 0, "caught and bowled": 0, "bowled": 1, "lbw": 2, "stumped": 3, "run out": 4, "hit wicket": 5,
         "obstructing the field": 5, "handled the ball": 5, "hit the ball twice": 5}
RETIRE = ("retired_hurt", "retired_not_out", "retired_out")
RETIRE_OF = {"retired hurt": 0, "retired not out": 1, "retired out": 2}
NOT_OUT_KINDS = {"retired hurt", "retired not out"}
EVENT_KINDS = {"retired hurt", "retired not out", "retired out", "timed out"}
NOT_BOWL_END = {"run out", "stumped", "hit wicket", "obstructing the field", "handled the ball", "timed out"}
OUT_ROLES = ("striker", "non_striker", "neither")
REVIEW_BY = ("bat", "bowl")
DECISIONS = ("upheld", "struck_down", "technical")
DECISION_OF = {"upheld": 0, "struck down": 1, "technical failure": 2}
RECON = ("none", "bat_struck_down", "bat_upheld", "bowl_upheld", "bowl_struck_down", "technical",
         "ignored_extra", "ignored_other")
TIMINGS = ("original", "pre_inn2", "unknown")
PP_LEVELS = ("none", "pp1", "pp2", "pp3", "batting", "fielding", "power_surge")
CLASS_NAMES = ("dot", "one", "two", "three", "four", "six", "out", "run_out", "byes")
RUN_CLASS = (0, 1, 2, 3, 4, 4, 5, 5)
KIND_CODE = {k: i for i, k in enumerate(KINDS_RAW)}
PP_CODE = {k: i for i, k in enumerate(PP_LEVELS)}

# (column, numpy dtype, null sentinel) in the order parse_match builds each delivery tuple
ROW_COLS = [
    ("match_id", "int32", None), ("innings", "int8", None), ("ball_seq", "int16", None), ("over", "int16", None),
    ("ball_in_over", "int8", None), ("legal_ball_index", "int16", None), ("bat_team_idx", "int8", None),
    ("batter_id", "int32", NA), ("non_striker_id", "int32", NA), ("bowler_id", "int32", NA),
    ("runs_batter", "int8", None), ("non_boundary", "bool", None), ("wides", "int8", None),
    ("noballs", "int8", None), ("byes", "int8", None), ("legbyes", "int8", None), ("penalty", "int8", None),
    ("runs_total", "int8", None), ("dtype", "cat", None), ("outcome_class", "int8", NA),
    ("wicket_kind_raw", "cat", NA), ("wk", "cat", NA), ("player_out_id", "int32", NA), ("out_role", "cat", NA),
    ("second_wicket", "bool", None), ("retire_event", "cat", NA), ("fielders", "object", None),
    ("fielder_sub", "bool", None), ("review_by", "cat", NA), ("review_decision", "cat", NA),
    ("review_umpires_call", "boolna", NA), ("review_umpire_id", "int32", NA), ("review_batter_id", "int32", NA),
    ("review_about_wicket", "boolna", NA), ("recon_case", "cat", None), ("onfield_out", "bool", None),
    ("onfield_class", "int8", NA), ("onfield_wk", "cat", NA), ("final_out", "bool", None),
    ("inn_runs", "int16", None), ("inn_wkts", "int8", None), ("inn_unavailable", "int8", None),
    ("striker_runs", "int16", None), ("striker_balls", "int16", None), ("nonstriker_runs", "int16", None),
    ("nonstriker_balls", "int16", None), ("partnership_runs", "int16", None), ("partnership_balls", "int16", None),
    ("striker_arrival", "int8", None), ("nonstriker_arrival", "int8", None), ("bowler_balls_inn", "int16", None),
    ("bowler_spell_overs", "int8", None), ("match_legal_balls", "int16", None), ("lead", "int16", NA16),
    ("target_runs", "int16", NA), ("target_known", "bool", None), ("target_timing", "cat", NA),
    ("max_balls_known_before", "int16", NA), ("prev_dtype", "cat", NA), ("prev_free_hit_chain", "int8", None),
    ("pp_window_recorded", "cat", NA), ("bat_fail_reviews", "int8", None), ("bowl_fail_reviews", "int8", None),
]
DERIVED_COLS = [
    ("fam", "cat", None), ("gender", "cat", None), ("bat_team", "cat", NA), ("bowl_team", "cat", NA),
    ("balls_remaining", "int16", NA), ("runs_required", "int16", NA16), ("ball_age_overs", "int16", NA),
    ("second_new_ball", "boolna", NA), ("bowl_end_umpire_p", "float32", None), ("est_day", "int8", NA),
    ("est_overs_into_day", "float32", None), ("striker_exp", "int32", None), ("bowler_exp", "int32", None),
    ("striker_role_pos", "float32", None), ("onfield_wk_p_lbw", "float32", None),
]
BALL_SPEC = {c: (t, s) for c, t, s in ROW_COLS + DERIVED_COLS}
CATEGORIES = {"dtype": DTYPES, "prev_dtype": DTYPES, "wicket_kind_raw": KINDS_RAW, "wk": WK, "onfield_wk": WK,
              "out_role": OUT_ROLES, "retire_event": RETIRE, "review_by": REVIEW_BY, "review_decision": DECISIONS,
              "recon_case": RECON, "target_timing": TIMINGS, "pp_window_recorded": PP_LEVELS, "fam": FAMS,
              "gender": GENDERS}
SO_COLS = ["match_id", "so_index", "bat_team_idx", "ball_seq", "over", "ball_in_over", "batter_id",
           "non_striker_id", "bowler_id", "runs_batter", "non_boundary", "wides", "noballs", "byes", "legbyes",
           "penalty", "runs_total", "dtype", "wicket_kind_raw", "player_out_id", "review_by", "review_decision",
           "review_umpires_call", "review_umpire_id"]
EVENT_COLS = ["match_id", "innings", "ball_seq", "event", "player_id", "other_id", "team_idx", "reason", "detail"]
PI_COLS = ["match_id", "innings", "team_idx", "player_id", "arrival", "balls_faced", "bat_runs", "balls_bowled",
           "runs_conceded"]


# ---------------------------------------------------------------- small parsers

def info_block(raw: bytes) -> dict:
    """The `info` dict without parsing the innings (Cricsheet writes meta and info first)."""
    k = raw.find(b'"innings"')
    if k > 0:
        try:
            return json.loads(raw[:k].rstrip().rstrip(b",") + b"}")["info"]
        except (ValueError, KeyError):
            pass
    return json.loads(raw)["info"]


def match_id_of(stem: str) -> int:
    """Integer match_id from the file stem; non-numeric stems ('wi_201706', 25 files) map to 90M + number."""
    if stem.isdigit():
        return int(stem)
    prefix, _, num = stem.rpartition("_")
    if prefix == "wi" and num.isdigit():
        return 90_000_000 + int(num)
    return 100_000_000 + zlib.crc32(stem.encode()) % 100_000_000


def family(info: dict) -> str:
    return "HUNDRED" if info.get("balls_per_over") == 5 else FAMILY[info["match_type"]]


def overs_to_balls(x, bpo: int) -> int:
    """Cricsheet overs.balls notation (40.2, '8.4', 50) -> legal balls."""
    s = repr(float(x)) if isinstance(x, float) else str(x)
    whole, _, part = s.partition(".")
    return int(whole) * bpo + (int(part) if part else 0)


def pp_point(x) -> tuple[int, int]:
    whole, _, part = repr(float(x)).partition(".")
    return int(whole), int(part or 0)


def powerplay_windows(pps: list, fam: str, n_deliveries: dict) -> list[tuple]:
    """[(from_over, from_seq, to_over, to_seq, level_code)] with (over, delivery-sequence) bounds.

    A 10th delivery is serialised as '.1' (49.10 -> 49.1), so a `to` of x.1 on an over with 10 or more
    deliveries means x.10. Mandatory windows are pp1, pp2, pp3 in order; a T20 batting powerplay is the
    BBL power surge."""
    out, n_mand = [], 0
    for p in sorted(pps, key=lambda p: pp_point(p["from"])):
        fo, fs = pp_point(p["from"])
        to, ts = pp_point(p["to"])
        if ts == 1 and n_deliveries.get(to, 0) >= 10:
            ts = 10
        typ = p.get("type")
        if typ == "mandatory":
            n_mand += 1
            lvl = ("pp1", "pp2", "pp3")[min(n_mand, 3) - 1]
        elif typ == "batting":
            lvl = "power_surge" if fam in ("T20", "HUNDRED") else "batting"
        elif typ == "fielding":
            lvl = "fielding"
        else:
            continue
        out.append((fo, max(fs, 1), to, ts, PP_CODE[lvl]))
    return out


def pp_level(windows: list[tuple], over: int, seq: int) -> int:
    for fo, fs, to, ts, lvl in windows:
        if (over > fo or (over == fo and seq >= fs)) and (over < to or (over == to and seq <= ts)):
            return lvl
    return 0


def outcome_class(dtype: int, runs_batter: int, byes_legbyes: int, wk: int) -> int:
    """Plan 6.3 nine-class coding of a recorded delivery (-1 for wides)."""
    if dtype == 1:
        return NA
    if wk != NA:
        return 7 if wk == 4 else 6
    if runs_batter:
        return RUN_CLASS[min(runs_batter, 7)]
    return 8 if byes_legbyes else 0


def reconstruct(dtype: int, cls: int, wk: int, side: int, decision: int, about: int) -> tuple:
    """(recon_case, onfield_out, onfield_class, onfield_wk, final_out) per plan 6.5.

    `wk` is the recorded ball-wicket code (NA when none), `side` 0 bat / 1 bowl / NA, `decision` 0 upheld /
    1 struck down / 2 technical, `about` 0 when the review named another batter than the one out."""
    out = wk != NA
    base = (out, cls, wk, out)
    if side == NA:
        return (0,) + base
    if dtype != 0:
        return (6,) + base
    if about == 0:
        return (7,) + base
    if decision == 2:
        return (5,) + base
    if side == 0:
        if decision == 1:
            return ((1,) if out else (7,)) + base
        return (2, True, 6, NA, False) if not out else (7,) + base
    if decision == 0:
        return (3, False, 0, NA, True) if out else (7,) + base
    return ((4,) if not out else (7,)) + base


def umpire_end_p(obs: list[tuple[int, str]], u1: str | None, u2: str | None, err: float = NAME_ERROR) -> tuple:
    """(p that umpire 1 is at the bowler's end in even units, votes even, votes odd)."""
    a = b = 0
    for par, name in obs:
        if u1 is not None and name == u1:
            even = par == 0
        elif u2 is not None and name == u2:
            even = par == 1
        else:
            continue
        a, b = (a + 1, b) if even else (a, b + 1)
    if (a and b) or not (a or b):
        return 0.5, a, b
    n = a or b
    q = (1 - err) ** n / ((1 - err) ** n + err ** n)
    return (q if a else 1 - q), a, b


def est_rate(total_legal: int, bpo: int, n_dates: int, result: str, scheduled_days: int | None) -> tuple:
    """(opd, r) of plan 7.5: r = min(opd, O_total / (D - 1 + phi))."""
    opd = OPD_FOUR_DAY if scheduled_days == 4 else OPD
    phi = 1.0 if result in ("draw", "no_result") else 0.5
    overs = total_legal / bpo
    r = min(opd, overs / (max(n_dates, 1) - 1 + phi)) if overs > 0 else float(opd)
    return opd, max(r, 1e-6)


def _scheduled_days(info: dict, match_id) -> int | None:
    try:
        from beating.cricket.rules import rules_for_match
        return rules_for_match(info, match_id=match_id).get("test_days")
    except Exception:
        return {"Test": 5, "MDM": 4}.get(info.get("match_type"))


def _venue_id(venue, city):
    try:
        from beating.cricket.venues import venue_id_for
        return venue_id_for(venue, city)
    except Exception:
        return None


def _scheduled_overs(info: dict, fam: str) -> tuple:
    raw = info.get("overs")
    if fam not in DEFAULT_OVERS:
        return None, raw, None
    if raw is None:
        return DEFAULT_OVERS[fam], raw, "missing"
    if fam in ("T20", "HUNDRED") and raw > 20:
        return 20, raw, f"{raw}->20"
    return int(raw), raw, None


def _int_or_none(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _missing(info: dict) -> list:
    return info.get("missing") or []


# ---------------------------------------------------------------- one match

def _raw_innings(inn: dict) -> dict:
    """Totals straight from the JSON (independent of the state machine) plus replacement entries."""
    legal = runs = wkts = rhurt = nd = 0
    repl, role_bat = [], {}
    for ov in inn.get("overs", ()):
        for dl in ov["deliveries"]:
            ex = dl.get("extras") or {}
            legal += "wides" not in ex and "noballs" not in ex
            runs += dl["runs"]["total"]
            for w in dl.get("wickets", ()):
                if w["kind"] in NOT_OUT_KINDS:
                    rhurt += 1
                else:
                    wkts += 1
            rp = dl.get("replacements")
            if rp:
                repl += [(nd, r) for r in rp.get("match", ())]
                for r in rp.get("role", ()):
                    if r.get("role") == "batter" and r.get("out"):
                        role_bat.setdefault(r["out"], r.get("in"))
            nd += 1
    pen = inn.get("penalty_runs") or {}
    pre, post = int(pen.get("pre", 0)), int(pen.get("post", 0))
    return dict(team=inn.get("team"), n_deliveries=nd, legal=legal, runs=runs, pen_pre=pre, pen_post=post,
                total=runs + pre + post, wkts_raw=wkts, retired_raw=rhurt, absent=list(inn.get("absent_hurt") or []),
                declared=bool(inn.get("declared")), forfeited=bool(inn.get("forfeited")), target_raw=inn.get("target"),
                repl=repl, role_bat=role_bat)


def limited_targets(raw: list[dict], sched_balls: int, bpo: int, method: str | None) -> tuple[list[dict], dict]:
    """Per-innings (target, known, timing, max_balls) for a limited-overs match, plus match fields."""
    per = [dict(target=NA, known=False, timing=NA, max_balls=sched_balls) for _ in raw]
    meta = dict(target_runs_raw=None, target_overs_raw=None, target_balls=None, target_runs=None,
                target_timing=None, inn1_cut=False, inn1_effective_balls=None)
    if not raw:
        return per, meta
    m1 = raw[0]
    meta["inn1_cut"] = bool(not m1["allout"] and m1["legal"] < sched_balls and len(raw) > 1 and not raw[1].get("forfeited"))
    meta["inn1_effective_balls"] = m1["legal"] if meta["inn1_cut"] else sched_balls
    if len(raw) < 2:
        return per, meta
    m2, revised = raw[1], method in REVISION_METHODS
    orig, t = m1["total"] + 1, m2["target_raw"] or {}
    if t.get("runs") is not None:
        target = int(t["runs"])
        tb = overs_to_balls(t["overs"], bpo) if t.get("overs") is not None else sched_balls
        meta.update(target_runs_raw=target, target_overs_raw=t.get("overs"), target_balls=tb)
        if tb == sched_balls:
            timing = 0 if (not revised or target == orig) else (1 if meta["inn1_cut"] else 2)
        elif not revised or (not m1["allout"] and m1["legal"] == tb):
            timing = 1
        else:
            timing = 2
    else:
        tb = sched_balls
        ended = m2["total"] >= orig or m2["allout"] or m2["legal"] >= sched_balls
        target, timing = (orig, 0) if (not revised and ended) else (NA, 2)
    per[1] = dict(target=target, known=target != NA, timing=timing, max_balls=tb if timing in (0, 1) else sched_balls)
    if timing == 1 and not revised and m1["legal"] <= tb:
        per[0]["max_balls"] = tb
    meta.update(target_runs=None if target == NA else target, target_timing=TIMINGS[timing])
    return per, meta


def parse_match(d: dict, match_id: int, pid_of: dict, file_stem: str | None = None) -> dict:
    """Parse one Cricsheet match dict into rows for every table (see module docstring)."""
    info = d["info"]
    fam = family(info)
    bpo = int(info.get("balls_per_over", 6))
    hundred = fam == "HUNDRED"
    date = str(info["dates"][0])
    teams = list(info.get("teams") or [])
    t1, t2 = (teams + [None, None])[:2]
    reg = (info.get("registry") or {}).get("people") or {}
    stats = Counter(season_int=int(isinstance(info.get("season"), int)))
    pid_cache = {}

    def pid(name):
        if name is None:
            return NA
        v = pid_cache.get(name)
        if v is None:
            ident = reg.get(name)
            v = pid_of.get(ident, NA) if ident else NA
            if v == NA:
                stats["unknown_name"] += 1
            pid_cache[name] = v
        return v

    players = info.get("players") or {}
    officials = info.get("officials") or {}
    umps = list(officials.get("umpires") or [])
    u1, u2 = (umps + [None, None])[:2]
    oc = info.get("outcome") or {}
    method = oc.get("method")
    result = "win" if oc.get("winner") else {"no result": "no_result"}.get(oc.get("result"), oc.get("result"))
    sched, sched_raw, sched_fix = _scheduled_overs(info, fam)
    sched_balls = None if sched is None else sched * bpo
    ucall_from = UCALL_FIRST[fam]
    events: list[tuple] = []

    # match replacements and the starting XIs
    all_inns = d.get("innings") or []
    main = [inn for inn in all_inns if not inn.get("super_over")]
    raw = [_raw_innings(inn) for inn in main]
    subs, ins = [], defaultdict(set)
    for k, rk in enumerate(raw, 1):
        for seq, r in rk["repl"]:
            subs.append({"reason": r.get("reason"), "team": r.get("team"), "in": pid(r.get("in")),
                         "out": pid(r.get("out")), "innings": k, "ball_seq": seq})
            ins[r.get("team")].add(r.get("in"))
            ti = 1 if r.get("team") == t1 else (2 if r.get("team") == t2 else 0)
            events.append((match_id, k, seq, "replacement", pid(r.get("in")), pid(r.get("out")), ti, r.get("reason"),
                           None))
    for team, name in (info.get("supersubs") or {}).items():
        ins[team].add(name)
    xi = {t: [p for p in players.get(t, []) if p not in ins[t]] for t in teams}
    for r in raw:
        n_xi = len(xi.get(r["team"], []))
        limit = min(10, n_xi - 1) if n_xi >= 2 else 10
        r["allout"] = r["wkts_raw"] + len(r["absent"]) + r["retired_raw"] >= limit
    if fam == "TEST":
        per = [dict(target=NA, known=False, timing=NA, max_balls=NA) for _ in raw]
        tmeta = dict(target_runs_raw=None, target_overs_raw=None, target_balls=None, target_runs=None,
                     target_timing=None, inn1_cut=False, inn1_effective_balls=None)
    else:
        per, tmeta = limited_targets(raw, sched_balls, bpo, method)
    follow_on = fam == "TEST" and len(main) >= 3 and main[2].get("team") == main[1].get("team")

    rows, ump_p, pi_rows, innings_rows = [], [], [], []
    agg = Counter()
    match_legal = 0
    bat_orders = {}
    for k, inn in enumerate(main, 1):
        team = inn.get("team")
        ti = 1 if team == t1 else (2 if team == t2 else 0)
        opp = t2 if ti == 1 else t1
        rk = raw[k - 1]
        tgt, tknown, ttiming, maxb = per[k - 1]["target"], per[k - 1]["known"], per[k - 1]["timing"], per[k - 1]["max_balls"]
        lead_off = NA16
        if fam == "TEST":
            lead_off = agg[team] - agg[opp]
            if k == 4:
                tgt, tknown, ttiming = agg[opp] - agg[team] + 1, True, 0
        if rk["forfeited"]:
            events.append((match_id, k, NA, "forfeiture", NA, NA, ti, None, None))
        if follow_on and k == 3:
            events.append((match_id, k, NA, "follow_on", NA, NA, ti, None, json.dumps({"lead": agg[opp] - agg[team]})))
        for name in rk["absent"]:
            events.append((match_id, k, NA, "absent_hurt", pid(name), NA, ti, None, None))
        if rk["pen_pre"] or rk["pen_post"]:
            events.append((match_id, k, NA, "penalty_runs", NA, NA, ti, None,
                           json.dumps({"pre": rk["pen_pre"], "post": rk["pen_post"]})))
        for o, v in (inn.get("miscounted_overs") or {}).items():
            v = v if isinstance(v, dict) else {"balls": v}
            events.append((match_id, k, NA, "miscounted_over", pid(v.get("umpire")), NA, ti, None,
                           json.dumps({"over": int(o), "balls": int(v.get("balls")), "umpire": v.get("umpire")})))
        overs = inn.get("overs") or []
        n_deliv = {ov["over"]: len(ov["deliveries"]) for ov in overs}
        windows = powerplay_windows(inn["powerplays"], fam, n_deliv) if inn.get("powerplays") else None
        role_bat = rk["role_bat"]
        inn_runs, inn_wkts, n_off = rk["pen_pre"], 0, len(rk["absent"])
        legal_idx = part_runs = part_balls = fails_bat = fails_bowl = nb_chain = 0
        prev_dt, seq = NA, 0
        bruns, bballs, arrival, bowl_balls, bowl_runs = Counter(), Counter(), {}, Counter(), Counter()
        over_bowlers = defaultdict(set)
        dismissed, off = set(), set()
        pb = pn = None
        obs = []
        spell_key, spell = None, 0
        start_row = len(rows)
        for ov in overs:
            o = ov["over"]
            unit = o // 2 if hundred else o
            bio = 0
            for si, dl in enumerate(ov["deliveries"], 1):
                bat, ns, bw = dl["batter"], dl["non_striker"], dl["bowler"]
                if bat != pb or ns != pn:
                    if pb is None or {bat, ns} != {pb, pn}:
                        prev_set = set() if pb is None else {pb, pn}
                        for g in prev_set - {bat, ns}:
                            if g in dismissed or g in off:
                                continue
                            if g in role_bat:
                                off.add(g)
                                n_off += 1
                                events.append((match_id, k, seq, "temporary_retirement", pid(g), pid(role_bat[g]), ti,
                                               None, None))
                            else:
                                stats["unexplained_departure"] += 1
                                events.append((match_id, k, seq, "unexplained_departure", pid(g), NA, ti, None, None))
                        for p in ([bat, ns] if bat != ns else [bat]):
                            if p in prev_set:
                                continue
                            if p not in arrival:
                                arrival[p] = len(arrival) + 1
                            elif p in off:
                                off.discard(p)
                                n_off -= 1
                                events.append((match_id, k, seq, "resumption", pid(p), NA, ti, None, None))
                            elif p in dismissed:
                                stats["reappearance_after_out"] += 1
                                events.append((match_id, k, seq, "reappearance", pid(p), NA, ti, None, None))
                        part_runs = part_balls = 0
                    pb, pn = bat, ns
                if (o, bw) != spell_key:
                    spell_key, spell = (o, bw), 0
                    if hundred and o % 2 == 1 and bw in over_bowlers[o - 1]:
                        spell += 1
                    u = unit - 2
                    while u >= 0:
                        c = sum(bw in over_bowlers[s] for s in ((2 * u, 2 * u + 1) if hundred else (u,)))
                        if not c:
                            break
                        spell, u = spell + c, u - 2
                over_bowlers[o].add(bw)
                ex = dl.get("extras") or {}
                r = dl["runs"]
                rb, rt = r["batter"], r["total"]
                wd, nb = ex.get("wides", 0), ex.get("noballs", 0)
                by, lb, pen = ex.get("byes", 0), ex.get("legbyes", 0), ex.get("penalty", 0)
                dt = 2 if nb else (1 if wd else 0)
                if wd and nb:
                    stats["wide_and_noball"] += 1
                if rb and (by or lb):
                    stats["bat_and_bye_runs"] += 1
                if rb > 7:
                    stats["runs_batter_gt7"] += 1
                # wickets: the first non-event wicket is the ball's wicket
                kind = wk = po = role = NA
                retire, second, fjson, fsub, ball_w = NA, False, None, False, None
                wl = dl.get("wickets")
                if wl:
                    second = len(wl) > 1
                    for w in wl:
                        if "playeer_out" in w:
                            stats["playeer_out"] += 1
                        kr = w["kind"]
                        name = w.get("player_out") or w.get("playeer_out")
                        if kr in EVENT_KINDS:
                            if retire == NA and kr in RETIRE_OF:
                                retire = RETIRE_OF[kr]
                            events.append((match_id, k, seq, kr.replace(" ", "_"), pid(name), NA, ti, None,
                                           json.dumps({"at": "striker" if name == bat else
                                                       ("non_striker" if name == ns else "neither")})))
                        elif ball_w is not None:
                            events.append((match_id, k, seq, "second_ball_wicket", pid(name), NA, ti, kr, None))
                        else:
                            ball_w = w
                            kind, wk, po = KIND_CODE.get(kr, NA), WK_OF.get(kr, 5), pid(name)
                            if kr not in KIND_CODE:
                                stats["unknown_kind"] += 1
                            role = 0 if name == bat else (1 if name == ns else 2)
                            fl = w.get("fielders") or []
                            if fl:
                                fjson = json.dumps([pid(f["name"]) if f.get("name") else None for f in fl])
                                fsub = any(f.get("substitute") for f in fl)
                cls = outcome_class(dt, rb, by + lb, wk)
                rv = dl.get("review")
                if rv:
                    side = 0 if rv.get("by") == team else (1 if rv.get("by") == opp else NA)
                    dec = DECISION_OF.get(rv.get("decision"), NA)
                    uc = 1 if rv.get("umpires_call") else (0 if date >= ucall_from else NA)
                    rbat_name = rv.get("batter")
                    about = NA if ball_w is None or not rbat_name else int(rbat_name == (ball_w.get("player_out") or ball_w.get("playeer_out")))
                    rv_ump, rv_bat = pid(rv.get("umpire")), pid(rbat_name)
                    if rv.get("umpire") and not (ball_w is not None and ball_w["kind"] in NOT_BOWL_END):
                        obs.append((unit & 1, rv["umpire"]))
                    rc, onf_out, onf_cls, onf_wk, fin = reconstruct(dt, cls, wk, side, dec, about)
                else:
                    side = dec = uc = about = rv_ump = rv_bat = NA
                    rc, onf_out, onf_cls, onf_wk, fin = 0, wk != NA, cls, wk, wk != NA
                lead = NA16 if lead_off == NA16 else lead_off + inn_runs
                rows.append((
                    match_id, k, seq, o, bio, legal_idx, ti, pid(bat), pid(ns), pid(bw),
                    rb, bool(r.get("non_boundary")), wd, nb, by, lb, pen, rt, dt, cls,
                    kind, wk, po, role, second, retire, fjson, fsub,
                    side, dec, uc, rv_ump, rv_bat, about, rc, onf_out, onf_cls, onf_wk, fin,
                    inn_runs, inn_wkts, inn_wkts + n_off, bruns[bat], bballs[bat], bruns[ns], bballs[ns],
                    part_runs, part_balls, arrival.get(bat, 0), arrival.get(ns, 0), bowl_balls[bw], spell,
                    match_legal, lead, tgt, tknown, ttiming, maxb, prev_dt, nb_chain,
                    NA if windows is None else pp_level(windows, o, si), fails_bat, fails_bowl,
                ))
                # update state after the delivery
                inn_runs += rt
                bruns[bat] += rb
                part_runs += rt
                bowl_runs[bw] += rb + wd + nb
                if not wd:
                    bballs[bat] += 1
                    part_balls += 1
                if dt == 0:
                    legal_idx += 1
                    bio += 1
                    match_legal += 1
                    bowl_balls[bw] += 1
                    nb_chain = 0
                else:
                    nb_chain += dt == 2
                prev_dt = dt
                if wl:
                    for w in wl:
                        name = w.get("player_out") or w.get("playeer_out")
                        if w["kind"] in NOT_OUT_KINDS:
                            if name not in off:
                                off.add(name)
                                n_off += 1
                        else:
                            inn_wkts += 1
                            dismissed.add(name)
                            if name in off:
                                off.discard(name)
                                n_off -= 1
                if rv and dec == 1 and uc != 1 and side != NA:
                    if side == 0:
                        fails_bat += 1
                    else:
                        fails_bowl += 1
                for r_ in (dl.get("replacements") or {}).get("role", ()):
                    ev = "bowler_change_mid_over" if r_.get("role") == "bowler" else "role_replacement"
                    events.append((match_id, k, seq, ev, pid(r_.get("in")), pid(r_.get("out")), ti, r_.get("reason"),
                                   json.dumps({"role": r_.get("role")})))
                seq += 1
        for o_, v in (inn.get("miscounted_overs") or {}).items():
            if isinstance(v, dict) and v.get("umpire"):
                obs.append((((int(o_) // 2) if hundred else int(o_)) & 1, v["umpire"]))
        p_even, va, vb = umpire_end_p(obs, u1, u2)
        ump_p.extend([p_even] * (len(rows) - start_row))
        if rk["declared"] and seq:
            events.append((match_id, k, seq - 1, "declaration", NA, NA, ti, None, None))
        order = sorted(arrival, key=arrival.get)
        n_team_inn = sum(1 for j in range(k) if main[j].get("team") == team)
        bat_orders[(ti, n_team_inn)] = [pid(p) for p in order]
        listed = players.get(team) or []
        if listed and order:
            ls = set(listed)
            arr_l = [p for p in order if p in ls]
            seen = set(order)
            order_ok = int(arr_l == [p for p in listed if p in seen])
        else:
            order_ok = NA
        bowlers = set().union(*over_bowlers.values())
        for p in set(arrival) | bowlers:
            pi_rows.append((match_id, k, ti, pid(p), arrival.get(p, NA), bballs[p] if p in arrival else 0,
                            bruns[p] if p in arrival else 0, bowl_balls[p] if p in bowlers else 0,
                            bowl_runs[p] if p in bowlers else 0))
        final_runs = inn_runs + rk["pen_post"]
        innings_rows.append(dict(
            match_id=match_id, innings=k, team_idx=ti, team_raw=team, n_deliveries=rk["n_deliveries"],
            legal_balls=rk["legal"], runs_deliveries=rk["runs"], pen_pre=rk["pen_pre"], pen_post=rk["pen_post"],
            total=rk["total"], wkts_raw=rk["wkts_raw"], retired_hurt_raw=rk["retired_raw"], n_absent_hurt=len(rk["absent"]),
            all_out=rk["allout"], declared=rk["declared"], forfeited=rk["forfeited"],
            state_final_runs=final_runs, state_final_wkts=inn_wkts, state_legal=legal_idx,
            target_runs=None if tgt == NA else tgt, target_timing=None if ttiming == NA else TIMINGS[ttiming],
            max_balls_known_before=None if maxb == NA else maxb, pp_recorded=windows is not None,
            umpire_p_even=p_even, umpire_votes_even=va, umpire_votes_odd=vb, order_matches_listed=order_ok,
            n_batters=len(arrival)))
        agg[team] += rk["total"]

    # super overs
    so_rows = []
    for j, inn in enumerate(x for x in all_inns if x.get("super_over")):
        team = inn.get("team")
        ti = 1 if team == t1 else (2 if team == t2 else 0)
        opp = t2 if ti == 1 else t1
        seq = 0
        for ov in inn.get("overs", ()):
            bio = 0
            for dl in ov["deliveries"]:
                ex = dl.get("extras") or {}
                wd, nb = ex.get("wides", 0), ex.get("noballs", 0)
                dt = 2 if nb else (1 if wd else 0)
                w = next((w for w in dl.get("wickets", ()) if w["kind"] not in EVENT_KINDS), None)
                rv = dl.get("review") or {}
                so_rows.append((match_id, j, ti, seq, ov["over"], bio, pid(dl["batter"]), pid(dl["non_striker"]),
                                pid(dl["bowler"]), dl["runs"]["batter"], bool(dl["runs"].get("non_boundary")), wd, nb,
                                ex.get("byes", 0), ex.get("legbyes", 0), ex.get("penalty", 0), dl["runs"]["total"],
                                DTYPES[dt], None if w is None else w["kind"],
                                NA if w is None else pid(w.get("player_out") or w.get("playeer_out")),
                                None if not rv else ("bat" if rv.get("by") == team else ("bowl" if rv.get("by") == opp else None)),
                                None if not rv else DECISIONS[DECISION_OF[rv["decision"]]] if rv.get("decision") in DECISION_OF else None,
                                None if not rv else bool(rv.get("umpires_call")),
                                NA if not rv else pid(rv.get("umpire"))))
                bio += dt == 0
                seq += 1

    # inferred interruptions and the match row
    if tmeta["target_balls"] is not None and sched_balls and tmeta["target_balls"] != sched_balls or tmeta["inn1_cut"]:
        events.append((match_id, 2 if len(main) > 1 else 1, NA, "interruption_inferred", NA, NA, 0, method,
                       json.dumps({"scheduled_balls": sched_balls, "target_balls": tmeta["target_balls"],
                                   "target_timing": tmeta["target_timing"], "inn1_cut": tmeta["inn1_cut"]})))
    toss = info.get("toss") or {}
    ev = info.get("event") or {}
    by = oc.get("by") or {}
    n_so = sum(1 for x in all_inns if x.get("super_over"))
    tie_break = ("super_over" if n_so else "bowl_out" if oc.get("bowl_out") else
                 "fewer_wickets" if method == "Lost fewer wickets" else "unrecorded" if oc.get("eliminator") else None)
    sched_days = _scheduled_days(info, match_id) if fam == "TEST" else None
    total_legal = sum(r["legal"] for r in raw)
    opd, rate = est_rate(total_legal, bpo, len(info["dates"]), result, sched_days) if fam == "TEST" else (None, None)
    ids = lambda names: json.dumps([pid(p) for p in names])
    first = lambda key: pid((officials.get(key) or [None])[0])
    m = dict(
        match_id=match_id, file_stem=file_stem or str(match_id),
        data_version=(d.get("meta") or {}).get("data_version"), start_date=date,
        dates_played=json.dumps([str(x) for x in info["dates"]]), season=str(info.get("season")),
        match_type=info.get("match_type"), match_type_number=info.get("match_type_number"), fam=fam,
        fit_fam=FIT_FAMILY[fam], gender=info.get("gender"), team_type=info.get("team_type"),
        event_name=ev.get("name"), event_match_number=_int_or_none(ev.get("match_number")),
        event_group=None if ev.get("group") is None else str(ev.get("group")),
        event_stage=ev.get("stage"), event_sub_name=ev.get("sub_name"), venue_raw=info.get("venue"),
        city_raw=info.get("city"), venue_id=_venue_id(info.get("venue"), info.get("city")), team1_raw=t1,
        team2_raw=t2, toss_winner=toss.get("winner"), toss_decision=toss.get("decision"),
        toss_uncontested=bool(toss.get("uncontested")), winner=oc.get("winner"), result=result, method=method,
        win_by_runs=by.get("runs"), win_by_wickets=by.get("wickets"), win_by_innings=bool(by.get("innings")),
        eliminator=oc.get("eliminator"), bowl_out=oc.get("bowl_out"), tie_break_used=tie_break,
        scheduled_overs=sched, scheduled_overs_raw=sched_raw, scheduled_overs_fix=sched_fix,
        scheduled_balls=sched_balls, balls_per_over=bpo, umpire1_id=pid(u1), umpire2_id=pid(u2),
        n_umpires_listed=len(umps), tv_umpire_id=first("tv_umpires"), referee_id=first("match_referees"),
        reserve_umpire_id=first("reserve_umpires"),
        squad_listed_team1=ids(players.get(t1, [])), squad_listed_team2=ids(players.get(t2, [])),
        xi_start_team1=ids(xi.get(t1, [])), xi_start_team2=ids(xi.get(t2, [])),
        n_listed_team1=len(players.get(t1, [])), n_listed_team2=len(players.get(t2, [])), subs=json.dumps(subs),
        **{f"bat_order_team{t}_inn{n}": (json.dumps(bat_orders[(t, n)]) if (t, n) in bat_orders else None)
           for t in (1, 2) for n in (1, 2)},
        reviews_missing="reviews" in [x for x in _missing(info) if isinstance(x, str)],
        missing=json.dumps(_missing(info)) if _missing(info) else None, follow_on=follow_on, n_innings=len(main),
        super_over=n_so > 0, n_super_over_innings=n_so, awarded=method == "Awarded",
        player_of_match=ids(info.get("player_of_match") or []), n_balls=len(rows), est_opd=opd, est_rate=rate,
        n_dates=len(info["dates"]), **tmeta)
    return dict(rows=rows, ump_p=ump_p, match=m, innings=innings_rows, events=events, super_overs=so_rows,
                player_innings=pi_rows, stats=stats)


# ---------------------------------------------------------------- chunk assembly

def _as_array(vals, typ: str):
    if typ == "object":
        out = np.empty(len(vals), dtype=object)
        out[:] = vals
        return out
    if typ in ("cat", "boolna"):
        return np.asarray(vals, dtype=np.int8)
    return np.asarray(vals, dtype=typ)


def assemble(parsed: list[dict]) -> dict:
    """Column arrays (numpy, sentinels for nulls) for the deliveries of several parsed matches."""
    rows = [r for p in parsed for r in p["rows"]]
    cols = list(zip(*rows)) if rows else [[] for _ in ROW_COLS]
    out = {name: _as_array(cols[i], typ) for i, (name, typ, _) in enumerate(ROW_COLS)}
    n = np.array([p["match"]["n_balls"] for p in parsed], dtype=np.int64)
    rep = lambda key, dtype=None: np.repeat(np.array([p["match"][key] for p in parsed], dtype=dtype), n)
    fam_code = np.array([FAMS.index(f) for f in (p["match"]["fam"] for p in parsed)], dtype=np.int8)
    out["fam"] = np.repeat(fam_code, n)
    out["gender"] = np.repeat(np.array([GENDERS.index(p["match"]["gender"]) for p in parsed], dtype=np.int8), n)
    out.update(derive(out, rep("balls_per_over", np.int16), np.asarray([x for p in parsed for x in p["ump_p"]],
                                                                       dtype=np.float32),
                      rep("n_dates", np.int16), np.asarray(rep("est_rate", object), dtype=float)))
    return out


def derive(c: dict, bpo: np.ndarray, p_even: np.ndarray, n_dates: np.ndarray, rate: np.ndarray) -> dict:
    """Vectorized pre-ball columns that depend only on the row and its match."""
    test = c["fam"] == FAMS.index("TEST")
    hundred = c["fam"] == FAMS.index("HUNDRED")
    over = c["over"].astype(np.int32)
    maxb = c["max_balls_known_before"].astype(np.int32)
    br = np.where(maxb >= 0, np.maximum(1, maxb - (over * bpo + c["ball_in_over"])), NA)
    tgt = c["target_runs"].astype(np.int32)
    rr = np.where(tgt >= 0, tgt - c["inn_runs"], NA16)
    unit = np.where(hundred, over // 2, over)
    p = np.where(unit % 2 == 0, p_even, 1 - p_even).astype(np.float32)
    mo = c["match_legal_balls"] / np.maximum(bpo, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        day = np.minimum(n_dates, 1 + np.floor(mo / rate))
        into = mo - (day - 1) * rate
    return dict(
        balls_remaining=br.astype(np.int16), runs_required=np.clip(rr, NA16, 32767).astype(np.int16),
        ball_age_overs=np.where(test, over % 80, NA).astype(np.int16),
        second_new_ball=np.where(test, over >= 80, NA).astype(np.int8), bowl_end_umpire_p=p,
        est_day=np.where(test, np.nan_to_num(day, nan=NA), NA).astype(np.int8),
        est_overs_into_day=np.where(test, into, np.nan).astype(np.float32))


_ZIP: dict = {}
_PID: dict = {}


def _init_worker(pid_of: dict) -> None:
    global _PID
    _PID = pid_of


def _parse_names(args) -> dict:
    path, names = args
    z = _ZIP.get(path) or _ZIP.setdefault(path, zipfile.ZipFile(path))
    parsed, failures = [], []
    for name in names:
        try:
            stem = Path(name).stem
            parsed.append(parse_match(json.loads(z.read(name)), match_id_of(stem), _PID, stem))
        except Exception as e:  # recorded and reported, never silently dropped
            failures.append((name, f"{type(e).__name__}: {e}"))
    stats = Counter()
    for p in parsed:
        stats.update(p["stats"])
    return dict(balls=assemble(parsed), matches=[p["match"] for p in parsed],
                innings=[r for p in parsed for r in p["innings"]], events=[e for p in parsed for e in p["events"]],
                super_overs=[r for p in parsed for r in p["super_overs"]],
                player_innings=[r for p in parsed for r in p["player_innings"]], stats=stats, failures=failures)


# ---------------------------------------------------------------- people index (pass 1)

def scan_people(zip_path: Path | str = CRICSHEET_ZIP, people_csv: Path | str | None = PEOPLE_CSV,
                names: list[str] | None = None) -> pd.DataFrame:
    """Dense `person_id` for every registry identifier in the zip, with names and roles."""
    names_seen, roles, dates = defaultdict(Counter), defaultdict(Counter), defaultdict(list)
    with zipfile.ZipFile(zip_path) as z:
        for n in names or [n for n in z.namelist() if n.endswith(".json")]:
            info = info_block(z.read(n))
            reg = (info.get("registry") or {}).get("people") or {}
            for name, ident in reg.items():
                names_seen[ident][name] += 1
                dates[ident].append(str(info["dates"][0]))
            for team, pl in (info.get("players") or {}).items():
                for p in pl:
                    if p in reg:
                        roles[reg[p]]["player"] += 1
            for key, lst in (info.get("officials") or {}).items():
                for p in lst:
                    if p in reg:
                        roles[reg[p]][key] += 1
    idents = sorted(names_seen)
    df = pd.DataFrame(dict(person_id=np.arange(len(idents), dtype=np.int32), identifier=idents,
                           name=[names_seen[i].most_common(1)[0][0] for i in idents],
                           names=[json.dumps(sorted(names_seen[i])) for i in idents],
                           n_matches_player=[roles[i]["player"] for i in idents],
                           n_matches_umpire=[roles[i]["umpires"] for i in idents],
                           n_matches_tv_umpire=[roles[i]["tv_umpires"] for i in idents],
                           n_matches_referee=[roles[i]["match_referees"] for i in idents],
                           first_date=[min(dates[i]) for i in idents], last_date=[max(dates[i]) for i in idents]))
    if people_csv is not None and Path(people_csv).exists():
        ppl = pd.read_csv(people_csv, dtype=str, keep_default_na=False)
        ppl = ppl[["identifier", "name", "unique_name", "key_cricinfo"]].rename(columns={"name": "register_name"})
        df = df.merge(ppl, on="identifier", how="left")
    return df


# ---------------------------------------------------------------- whole-table steps

def to_frame(cols: dict) -> pd.DataFrame:
    """In-memory balls frame: categoricals from codes, everything else as stored (sentinels kept)."""
    data = {}
    for name, arr in cols.items():
        if name in CATEGORIES:
            data[name] = pd.Categorical.from_codes(arr.astype(np.int8), categories=list(CATEGORIES[name]))
        else:
            data[name] = arr
    return pd.DataFrame(data, copy=False)


def team_columns(balls: pd.DataFrame, matches: pd.DataFrame) -> None:
    """bat_team / bowl_team categoricals from bat_team_idx and the matches' raw team names (same order)."""
    teams = sorted(set(matches.team1_raw.dropna()) | set(matches.team2_raw.dropna()))
    code = {t: i for i, t in enumerate(teams)}
    n = matches.n_balls.to_numpy()
    c1 = np.repeat(matches.team1_raw.map(code).fillna(NA).to_numpy(np.int32), n)
    c2 = np.repeat(matches.team2_raw.map(code).fillna(NA).to_numpy(np.int32), n)
    idx = balls.bat_team_idx.to_numpy()
    bat = np.where(idx == 1, c1, np.where(idx == 2, c2, NA))
    bowl = np.where(idx == 1, c2, np.where(idx == 2, c1, NA))
    balls["bat_team"] = pd.Categorical.from_codes(bat, categories=teams)
    balls["bowl_team"] = pd.Categorical.from_codes(bowl, categories=teams)


def player_context(pi: pd.DataFrame, matches: pd.DataFrame, window: int = ROLE_WINDOW) -> pd.DataFrame:
    """Per (match_id, player_id): prior balls faced / bowled and median arrival over the previous
    `window` innings, from strictly earlier dates in the same fitting family and gender."""
    meta = matches[["match_id", "start_date", "fit_fam", "gender"]]
    x = pi.merge(meta, on="match_id")
    per = x.groupby(["match_id", "player_id"], as_index=False).agg(
        balls_faced=("balls_faced", "sum"), balls_bowled=("balls_bowled", "sum"), start_date=("start_date", "first"),
        fit_fam=("fit_fam", "first"), gender=("gender", "first"))
    keys = ["fit_fam", "gender", "player_id", "start_date"]
    day = per.groupby(keys)[["balls_faced", "balls_bowled"]].sum()
    prior = day.groupby(level=[0, 1, 2]).cumsum() - day
    per = per.join(prior.rename(columns={"balls_faced": "striker_exp", "balls_bowled": "bowler_exp"}), on=keys)
    bats = x[x.arrival > 0].sort_values(keys + ["match_id", "innings"])
    role = {}
    for (ff, g, p), grp in bats.groupby(["fit_fam", "gender", "player_id"], sort=False):
        d, a = grp.start_date.to_numpy(), grp.arrival.to_numpy()
        for mid, sd in zip(grp.match_id.to_numpy(), grp.start_date.to_numpy()):
            i = np.searchsorted(d, sd, side="left")
            if i:
                role[(mid, p)] = float(statistics.median(a[max(0, i - window):i].tolist()))
    per["striker_role_pos"] = [role.get(k, np.nan) for k in zip(per.match_id, per.player_id)]
    return per[["match_id", "player_id", "striker_exp", "bowler_exp", "striker_role_pos"]]


def _lookup(keys_sorted: np.ndarray, values: np.ndarray, query: np.ndarray, default):
    i = np.searchsorted(keys_sorted, query)
    i = np.minimum(i, len(keys_sorted) - 1)
    hit = keys_sorted[i] == query if len(keys_sorted) else np.zeros(len(query), bool)
    return np.where(hit, values[i] if len(keys_sorted) else default, default)


def attach_player_context(balls: pd.DataFrame, ctx: pd.DataFrame) -> None:
    key = ctx.match_id.to_numpy(np.int64) * (1 << 21) + ctx.player_id.to_numpy(np.int64)
    order = np.argsort(key)
    key = key[order]
    mid = balls.match_id.to_numpy(np.int64) * (1 << 21)
    bat_key = mid + balls.batter_id.to_numpy(np.int64)
    balls["striker_exp"] = _lookup(key, ctx.striker_exp.to_numpy(np.int64)[order], bat_key, 0).astype(np.int32)
    balls["bowler_exp"] = _lookup(key, ctx.bowler_exp.to_numpy(np.int64)[order], mid + balls.bowler_id.to_numpy(np.int64),
                                  0).astype(np.int32)
    rp = _lookup(key, ctx.striker_role_pos.to_numpy(np.float64)[order], bat_key, np.nan)
    balls["striker_role_pos"] = np.where(np.isnan(rp), balls.striker_arrival.to_numpy(), rp).astype(np.float32)


def _unit_hash(*cols) -> np.ndarray:
    """Uniforms in [0, 1) from a splitmix64 hash of integer columns (reproducible imputation draws)."""
    x = np.zeros(len(cols[0]), dtype=np.uint64)
    with np.errstate(over="ignore"):
        for c in cols:
            x = (x * np.uint64(1_000_003)) ^ np.asarray(c, dtype=np.uint64)
            x = x + np.uint64(0x9E3779B97F4A7C15)
            x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
            x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
            x = x ^ (x >> np.uint64(31))
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def impute_overturned_kind(balls: pd.DataFrame, matches: pd.DataFrame, k: float = KIND_SHRINK) -> dict:
    """Kind of on-field outs overturned on batting review (plan 6.5); returns the rates used."""
    year = pd.Series(matches.start_date.str[:4].astype(int).to_numpy(), index=matches.match_id)
    ffam = pd.Series(matches.fit_fam.to_numpy(), index=matches.match_id)
    rc = balls.recon_case.cat.codes.to_numpy()
    wk = balls.wk.cat.codes.to_numpy()
    sd = (rc == RECON.index("bat_struck_down")) & np.isin(wk, (WK.index("lbw"), WK.index("caught")))
    ref = pd.DataFrame({"fit_fam": ffam.reindex(balls.match_id[sd]).to_numpy(),
                        "year": year.reindex(balls.match_id[sd]).to_numpy(),
                        "lbw": wk[sd] == WK.index("lbw")})
    fam_rate = ref.groupby("fit_fam").lbw.mean().to_dict()
    yr = ref.groupby(["fit_fam", "year"]).lbw.agg(["sum", "count"])
    rates = {(f, y): (s + k * fam_rate[f]) / (n + k) for (f, y), (s, n) in yr.iterrows()}
    up = np.flatnonzero(rc == RECON.index("bat_upheld"))
    mids = balls.match_id.to_numpy()[up]
    f, y = ffam.reindex(mids).to_numpy(), year.reindex(mids).to_numpy()
    p = np.array([rates.get((a, b), fam_rate.get(a, 0.9)) for a, b in zip(f, y)], dtype=np.float64)
    u = _unit_hash(mids, balls.innings.to_numpy()[up], balls.ball_seq.to_numpy()[up])
    codes = balls.onfield_wk.cat.codes.to_numpy().copy()
    codes[up] = np.where(u < p, WK.index("lbw"), WK.index("caught"))
    balls["onfield_wk"] = pd.Categorical.from_codes(codes, categories=list(WK))
    plbw = np.full(len(balls), np.nan, dtype=np.float32)
    plbw[up] = p
    balls["onfield_wk_p_lbw"] = plbw
    return {"family_lbw_share": fam_rate, "n_imputed": int(len(up)),
            "imputed_lbw": int((codes[up] == WK.index("lbw")).sum()), "shrink_pseudo_reviews": k}


# ---------------------------------------------------------------- validation

AUDIT_REVIEWS = {"bat|struck_down|wicket": 4589, "bat|upheld|no_wicket": 2500, "bowl|upheld|wicket": 2203,
                 "bowl|struck_down|no_wicket": 7846}
AUDIT_ORDER = {"T20|2018+": 0.976, "ODI|all": 0.991, "HUNDRED|all": 0.996, "TEST|all": 0.766}
AUDIT_ENDS_2019 = {"Test|international": 0.894, "ODI|international": 0.385, "HUNDRED|club": 0.449,
                   "T20|club": 0.250, "T20|international": 0.117, "MDM|club": 0.0, "ODM|club": 0.0}


def _share(s: pd.Series, digits: int = 4) -> dict:
    return {str(k): round(float(v), digits) for k, v in s.items()}


def _examples(df: pd.DataFrame, cols: list[str], n: int = 5) -> list:
    return df[cols].head(n).astype(object).where(df[cols].head(n).notna(), None).values.tolist()


def validate(t: dict) -> dict:
    """The ingest checks of the task brief; returns a JSON-able dict."""
    balls, matches, inns, events = t["balls"], t["matches"], t["innings"], t["events"]
    rep = {"failures": {"n": len(t["failures"]), "examples": t["failures"][:10]}, "parse_stats": dict(t["stats"])}
    n_match = matches.n_balls.to_numpy()
    if n_match.sum() != len(balls) or not np.array_equal(np.repeat(matches.match_id.to_numpy(), n_match),
                                                         balls.match_id.to_numpy()):
        raise ValueError("balls are not stored in matches order")
    mid, inn = balls.match_id.to_numpy(), balls.innings.to_numpy()
    starts = np.flatnonzero(np.r_[True, (mid[1:] != mid[:-1]) | (inn[1:] != inn[:-1])]) if len(balls) else np.array([], int)
    ends = np.r_[starts[1:], len(balls)].astype(int)
    red = lambda a: np.add.reduceat(np.asarray(a, dtype=np.int64), starts) if len(starts) else np.array([], np.int64)
    g = pd.DataFrame({"n": ends - starts, "runs": red(balls.runs_total.to_numpy()),
                      "legal": red(balls.dtype.cat.codes.to_numpy() == 0),
                      "ball_wkts": red(balls.wk.cat.codes.to_numpy() >= 0),
                      "last_inn_runs": balls.inn_runs.to_numpy()[ends - 1],
                      "last_runs": balls.runs_total.to_numpy()[ends - 1]},
                     index=pd.MultiIndex.from_arrays([mid[starts], inn[starts]], names=["match_id", "innings"]))
    ev = events[events.event.isin(["retired_out", "timed_out", "second_ball_wicket"])].groupby(["match_id", "innings"]).size()
    x = inns.merge(g, left_on=["match_id", "innings"], right_index=True, how="left")
    x = x.join(ev.rename("event_wkts"), on=["match_id", "innings"]).fillna(
        {"n": 0, "runs": 0, "legal": 0, "ball_wkts": 0, "last_inn_runs": 0, "last_runs": 0, "event_wkts": 0})
    x["state_total"] = np.where(x.n > 0, x.last_inn_runs + x.last_runs + x.pen_post, x.pen_pre + x.pen_post)
    checks = {
        "deliveries_equal": x.n == x.n_deliveries,
        "legal_equal": x.legal == x.legal_balls,
        "runs_sum_equal": x.runs == x.runs_deliveries,
        "state_total_equal": x.state_total == x.total,
        "state_runs_equal": x.state_final_runs == x.total,
        "wickets_state_equal": x.state_final_wkts == x.wkts_raw,
        "wickets_from_ball_rows_equal": x.ball_wkts + x.event_wkts == x.wkts_raw,
    }
    one = {k: {"agree": int(v.sum()), "n": int(len(v)),
               "examples": _examples(x[~v], ["match_id", "innings", "total", "state_total", "wkts_raw",
                                              "state_final_wkts"])} for k, v in checks.items()}
    # totals implied by the JSON: stored targets and result margins
    lim = matches[matches.fam != "TEST"].set_index("match_id")
    tot = x.pivot_table(index="match_id", columns="innings", values="total", aggfunc="first")
    wk2 = x[x.innings == 2].set_index("match_id")
    tg = lim[lim.target_runs_raw.notna() & ~lim.method.isin(REVISION_METHODS) & (lim.target_balls == lim.scheduled_balls)]
    ok = tot.reindex(tg.index)[1] + 1 == tg.target_runs_raw
    one["innings1_total_plus1_equals_stored_target"] = {
        "agree": int(ok.sum()), "n": int(len(ok)),
        "note": "limited overs, no D/L/VJD method, target length = scheduled",
        "examples": [[int(m), float(tot.loc[m, 1]), float(tg.target_runs_raw[m])] for m in ok[~ok].index[:10]]}
    wr = lim[lim.win_by_runs.notna() & lim.method.isna() & (lim.n_innings == 2)]
    marg = tot.reindex(wr.index)[1] - tot.reindex(wr.index)[2]
    ok = marg == wr.win_by_runs
    one["win_by_runs_margin"] = {"agree": int(ok.sum()), "n": int(len(ok)),
                                 "examples": [[int(m), float(marg[m]), float(wr.win_by_runs[m])] for m in ok[~ok].index[:10]]}
    ww = lim[lim.win_by_wickets.notna() & lim.method.isna() & (lim.n_innings == 2)]
    w2 = wk2.reindex(ww.index)
    ok = (10 - w2.wkts_raw == ww.win_by_wickets) & (tot.reindex(ww.index)[2] >= tot.reindex(ww.index)[1] + 1)
    ok_ah = 10 - w2.wkts_raw - w2.n_absent_hurt - w2.retired_hurt_raw == ww.win_by_wickets
    one["win_by_wickets_margin"] = {"agree": int(ok.sum()), "agree_after_absent_and_retired": int((ok | ok_ah).sum()),
                                    "n": int(len(ok)), "examples": [int(m) for m in ok[~(ok | ok_ah)].index[:10]]}
    rep["1_innings_totals"] = one

    # 2 outcome classes (counted on category codes; rows are never copied)
    fam_c, gen_c = balls.fam.cat.codes.to_numpy().astype(np.int64), balls.gender.cat.codes.to_numpy().astype(np.int64)
    grp = fam_c * len(GENDERS) + gen_c
    fit = balls.dtype.cat.codes.to_numpy() != 1
    n_grp = len(FAMS) * len(GENDERS)
    label = lambda j: f"{FAMS[j // len(GENDERS)]}|{GENDERS[j % len(GENDERS)]}"

    def table(codes, names, mask):
        k = len(names)
        cnt = np.bincount((grp * (k + 1) + codes.astype(np.int64) + 1)[mask], minlength=n_grp * (k + 1))
        cnt = cnt.reshape(n_grp, k + 1)[:, 1:]
        return {label(j): {names[c]: round(float(cnt[j, c] / cnt[j].sum()), 4) for c in np.argsort(-cnt[j]) if cnt[j, c]}
                for j in range(n_grp) if cnt[j].sum()}

    out = {col: table(balls[col].to_numpy(), CLASS_NAMES, fit) for col in ("outcome_class", "onfield_class")}
    out["n_rows_legal_or_noball"] = {label(j): int(c) for j, c in enumerate(np.bincount(grp[fit], minlength=n_grp)) if c}
    out["dtype_share"] = table(balls.dtype.cat.codes.to_numpy(), DTYPES, np.ones(len(balls), bool))
    rep["2_outcome_classes"] = out

    # 3 reviews
    rv = balls[balls.review_by.notna()]
    has_w = rv.wk.notna() | rv.retire_event.notna()
    cat = rv.review_by.astype(str) + "|" + rv.review_decision.astype(str) + "|" + np.where(has_w, "wicket", "no_wicket")
    so = t["super_overs"]
    so_rv = so[so.review_by.notna()]
    so_cat = so_rv.review_by + "|" + so_rv.review_decision.astype(str) + "|" + np.where(
        so_rv.wicket_kind_raw.notna(), "wicket", "no_wicket")
    counts = pd.concat([cat, so_cat]).value_counts()
    rep["3_reviews"] = {
        "raw_categories_main_and_super_overs": {k: int(v) for k, v in counts.items()},
        "audit_table": {k: {"audit": v, "here": int(counts.get(k, 0))} for k, v in AUDIT_REVIEWS.items()},
        "n_reviews_total": int(len(rv) + len(so_rv)), "n_reviews_main": int(len(rv)),
        "recon_case_counts": {k: int(v) for k, v in balls.recon_case.value_counts().items()},
        "recon_case_by_dtype": {f"{a}|{b}": int(v) for (a, b), v in
                                rv.groupby(["recon_case", "dtype"], observed=True).size().items()},
        "review_about_wicket_false": int((rv.review_about_wicket == 0).sum()),
        "review_umpire_missing": int((rv.review_umpire_id < 0).sum()),
        "umpires_call_true": int((rv.review_umpires_call == 1).sum()),
        "umpires_call_null": int((rv.review_umpires_call < 0).sum()),
        "bat_upheld_runs_total_zero": int((rv[rv.recon_case == "bat_upheld"].runs_total == 0).sum()),
        "bowl_upheld_runs_total_zero": int((rv[rv.recon_case == "bowl_upheld"].runs_total == 0).sum()),
        "kind_imputation": t.get("kind_imputation"),
        "onfield_wk_on_bat_upheld": {k: int(v) for k, v in rv[rv.recon_case == "bat_upheld"].onfield_wk.value_counts().items()}
        if "onfield_wk" in rv else None}
    if "onfield_wk" in balls:
        bu = balls.recon_case == "bat_upheld"
        rep["3_reviews"]["onfield_wk_on_bat_upheld"] = {k: int(v) for k, v in balls.onfield_wk[bu].value_counts().items()}

    # 4 arrival order vs listed order
    o = inns[inns.order_matches_listed >= 0].merge(matches[["match_id", "fam", "start_date"]], on="match_id")
    yr = o.start_date.str[:4].astype(int)
    o["era"] = np.where(yr < 2010, "pre2010", np.where(yr < 2018, "2010_17", "2018+"))
    by_fam = o.groupby("fam").order_matches_listed.agg(["mean", "size"])
    by_era = o.groupby(["fam", "era"]).order_matches_listed.agg(["mean", "size"])
    rep["4_arrival_vs_listed_order"] = {
        "by_family": {f: {"share_exact": round(r["mean"], 4), "innings": int(r["size"])} for f, r in by_fam.iterrows()},
        "by_family_era": {f"{f}|{e}": {"share_exact": round(r["mean"], 4), "innings": int(r["size"])}
                          for (f, e), r in by_era.iterrows()},
        "audit": AUDIT_ORDER}

    # 5 umpire ends (segment and year repeated from the match rows)
    p = balls.bowl_end_umpire_p.to_numpy()
    seg_cat = pd.Categorical(np.where(matches.fam == "HUNDRED", "HUNDRED", matches.match_type) + "|" + matches.team_type)
    seg = np.repeat(seg_cat.codes.astype(np.int64), n_match)
    y19 = np.repeat(matches.start_date.str[:4].astype(int).to_numpy() >= 2019, n_match)
    flags = {"known": (p <= NAME_ERROR) | (p >= 1 - NAME_ERROR), "exact01": (p == 0) | (p == 1), "half": p == 0.5}

    def by_seg(mask):
        n = np.bincount(seg[mask], minlength=len(seg_cat.categories))
        out = {}
        for j, name in enumerate(seg_cat.categories):
            if n[j]:
                out[name] = {k: round(float(np.bincount(seg[mask], weights=v[mask], minlength=len(n))[j] / n[j]), 4)
                             for k, v in flags.items()}
                out[name]["balls"] = int(n[j])
        return out

    rep["5_umpire_end_identified"] = {
        "definition": "known = p <= 0.02 or p >= 0.98 (one or more agreeing named votes); exact01 = p exactly 0 or 1 "
                      "after float32 rounding (four or more votes); half = no or conflicting votes",
        "overall": {k: round(float(v.mean()), 4) for k, v in flags.items()},
        "by_segment_all_years": by_seg(np.ones(len(p), bool)), "by_segment_2019_plus": by_seg(y19),
        "audit_2019_plus_identified": AUDIT_ENDS_2019,
        "innings_with_conflicting_votes": int(((inns.umpire_votes_even > 0) & (inns.umpire_votes_odd > 0)).sum()),
        "matches_with_more_than_two_umpires": int((matches.n_umpires_listed > 2).sum())}

    # 6 target timing
    lm = matches[(matches.fam != "TEST") & (matches.n_innings >= 2)]
    i2 = (balls.innings.to_numpy() == 2) & (fam_c != FAMS.index("TEST"))
    tt = balls.target_timing.cat.codes.to_numpy().astype(np.int64)
    cnt = np.bincount((fam_c * 4 + tt + 1)[i2], minlength=len(FAMS) * 4).reshape(len(FAMS), 4)
    rep["6_target_timing"] = {
        "matches_by_family": {f: {str(k): int(v) for k, v in s_.value_counts(dropna=False).items()}
                              for f, s_ in lm.groupby("fam").target_timing},
        "innings2_balls_by_family": {FAMS[f]: {(["null"] + list(TIMINGS))[c]: int(cnt[f, c]) for c in range(4) if cnt[f, c]}
                                     for f in range(len(FAMS)) if cnt[f].sum()},
        "target_absent_innings2": {f: int(v) for f, v in
                                   lm[lm.target_runs_raw.isna()].groupby("match_type").size().items()},
        "target_length_differs": {f: int(v) for f, v in
                                  lm[lm.target_balls.notna() & (lm.target_balls != lm.scheduled_balls)]
                                  .groupby("match_type").size().items()},
        "target_known_false_innings2_balls": int((i2 & ~balls.target_known.to_numpy()).sum())}

    # regression targets from the data audit
    ev_counts = events.event.value_counts()
    lists = pd.concat([matches[["fam", "n_listed_team1"]].rename(columns={"n_listed_team1": "n"}),
                       matches[["fam", "n_listed_team2"]].rename(columns={"n_listed_team2": "n"})])
    rep["audit_regressions"] = {
        "matches": int(len(matches)), "deliveries_main": int(len(balls)), "deliveries_super_over": int(len(so)),
        "deliveries_total_audit_11689170": int(len(balls) + len(so)),
        "hundred_matches_audit_389": int((matches.fam == "HUNDRED").sum()),
        "scheduled_overs_fixes_audit_19": {k: int(v) for k, v in matches.scheduled_overs_fix.value_counts().items()},
        "season_int_audit_1685": int(t["stats"].get("season_int", 0)),
        "toss_uncontested_audit_263": int(matches.toss_uncontested.sum()),
        "forfeited_innings_audit_14": int(inns.forfeited.sum()),
        "absent_hurt_innings_audit_311": int((inns.n_absent_hurt > 0).sum()),
        "double_wicket_deliveries_audit_17": int(balls.second_wicket.sum()),
        "playeer_out_audit_1": int(t["stats"].get("playeer_out", 0)),
        "non_boundary_audit_1319": int(balls.non_boundary.sum()),
        "runs5_audit_1548": int((balls.runs_batter == 5).sum()), "runs7_audit_13": int((balls.runs_batter == 7).sum()),
        "retired_hurt_audit_466": int(ev_counts.get("retired_hurt", 0)),
        "retired_not_out_audit_45": int(ev_counts.get("retired_not_out", 0)),
        "retired_out_audit_127": int(ev_counts.get("retired_out", 0)),
        "temporary_retirements_audit_335": int(ev_counts.get("temporary_retirement", 0)),
        "resumptions": int(ev_counts.get("resumption", 0)),
        "unexplained_departures": int(ev_counts.get("unexplained_departure", 0)),
        "bowler_change_mid_over_entries": int(ev_counts.get("bowler_change_mid_over", 0)),
        "follow_ons": int(matches.follow_on.sum()),
        "team_sheets_over_11": {f"{f}|{n}": int(c) for (f, n), c in lists[lists.n > 11].groupby(["fam", "n"]).size().items()},
        "team_sheets_under_11": {f"{f}|{n}": int(c) for (f, n), c in
                                 lists[(lists.n < 11) & (lists.n > 0)].groupby(["fam", "n"]).size().items()},
        "events": {k: int(v) for k, v in ev_counts.items()},
        "venue_id_missing": int(matches.venue_id.isna().sum()),
        "unknown_person_names": int(t["stats"].get("unknown_name", 0))}
    return rep


# ---------------------------------------------------------------- parquet io

def _arrow_column(s: pd.Series, typ: str, sentinel):
    import pyarrow as pa
    if typ == "cat":
        return pa.DictionaryArray.from_arrays(pa.array(s.cat.codes.to_numpy(), mask=s.cat.codes.to_numpy() < 0),
                                              pa.array(list(s.cat.categories), type=pa.string()))
    v = s.to_numpy()
    if typ == "boolna":
        return pa.array(v == 1, mask=v < 0)
    if typ == "object":
        return pa.array(v, type=pa.string(), from_pandas=True)
    if sentinel is not None:
        return pa.array(v, mask=v == sentinel)
    return pa.array(v)


def write_table(df: pd.DataFrame, path: Path | str, spec: dict | None = None, row_group: int = 1_000_000,
                columns: list[str] | None = None) -> None:
    """Parquet with real nulls for sentinel columns; `spec` maps column -> (type, sentinel)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if spec is None:
        df = df.copy()
        for c in df.columns[df.dtypes == object]:
            if not df[c].map(lambda v: v is None or isinstance(v, str)).all():
                df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v))
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")
        return
    writer = None
    try:
        for start in range(0, max(len(df), 1), row_group):
            part = df.iloc[start:start + row_group]
            names = list(columns or df.columns)
            arrays = [_arrow_column(part[c], *spec.get(c, ("plain", None))) for c in names]
            table = pa.Table.from_arrays(arrays, names=names)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()


def read_table(name_or_path, columns: list[str] | None = None) -> pd.DataFrame:
    """Read a processed table; integer and boolean columns with nulls come back as pandas nullable dtypes,
    dictionary columns as categoricals, the rest as plain numpy."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    path = Path(name_or_path)
    if not path.suffix:
        path = OUT_DIR / f"{name_or_path}.parquet"
    pf = pq.ParquetFile(path)
    nullable = {pa.int8(): pd.Int8Dtype(), pa.int16(): pd.Int16Dtype(), pa.int32(): pd.Int32Dtype(),
                pa.int64(): pd.Int64Dtype(), pa.bool_(): pd.BooleanDtype()}
    out = {}
    for name in columns or pf.schema_arrow.names:  # one column at a time keeps the peak near the frame size
        col = pf.read(columns=[name]).column(0)
        out[name] = col.to_pandas(types_mapper=nullable.get) if col.null_count and col.type in nullable else col.to_pandas()
        del col
    return pd.DataFrame(out, copy=False)


AUX_DTYPES = {
    "matches": {"match_id": "int32", "match_type_number": "Int32", "event_match_number": "Int16", "win_by_runs": "Int16",
                "win_by_wickets": "Int16", "scheduled_overs": "Int16", "scheduled_overs_raw": "Int16",
                "scheduled_balls": "Int16", "balls_per_over": "int8", "umpire1_id": "Int32", "umpire2_id": "Int32",
                "tv_umpire_id": "Int32", "referee_id": "Int32", "reserve_umpire_id": "Int32", "n_umpires_listed": "int8",
                "n_listed_team1": "int8", "n_listed_team2": "int8", "n_innings": "int8", "n_super_over_innings": "int8",
                "n_balls": "int32", "est_opd": "Int16", "n_dates": "int8", "target_runs_raw": "Int16",
                "target_balls": "Int16", "target_runs": "Int16", "inn1_effective_balls": "Int16",
                "target_overs_raw": "float32", "est_rate": "float32"},
    "innings": {"match_id": "int32", "innings": "int8", "team_idx": "int8", "target_runs": "Int16",
                "max_balls_known_before": "Int16", "order_matches_listed": "Int8", "umpire_p_even": "float32"},
    "events": {"match_id": "int32", "innings": "int8", "ball_seq": "Int16", "player_id": "Int32", "other_id": "Int32",
               "team_idx": "int8"},
    "super_overs": {"match_id": "int32", "so_index": "int8", "bat_team_idx": "int8", "ball_seq": "int16",
                    "over": "int16", "ball_in_over": "int8", "batter_id": "Int32", "non_striker_id": "Int32",
                    "bowler_id": "Int32", "player_out_id": "Int32", "review_umpire_id": "Int32"},
    "player_innings": {"match_id": "int32", "innings": "int8", "team_idx": "int8", "player_id": "Int32",
                       "arrival": "Int8", "balls_faced": "int16", "bat_runs": "int16", "balls_bowled": "int16",
                       "runs_conceded": "int16"},
}


def tidy(name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Copy of a small table with -1 id / count sentinels as nulls and compact dtypes."""
    df = df.copy()
    for c, typ in AUX_DTYPES.get(name, {}).items():
        if c not in df:
            continue
        v = df[c]
        if typ[0].isupper():
            v = pd.to_numeric(v, errors="coerce")
            v = v.where(v >= 0) if c.endswith("_id") or c in ("ball_seq", "arrival", "order_matches_listed") else v
        df[c] = v.astype(typ)
    return df


# ---------------------------------------------------------------- build

def _trim() -> None:
    """Hand freed heap pages back to the OS (many small chunk arrays fragment the heap)."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def _rss_mb() -> dict:
    self_ = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    kids = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
    return {"main_peak_mb": round(self_, 1), "worker_peak_mb": round(kids, 1)}


def parse_zip(zip_path: Path | str = CRICSHEET_ZIP, people: pd.DataFrame | None = None, workers: int = 3,
              chunk: int = 100, limit: int | None = None, names: list[str] | None = None) -> dict:
    """Parse every match in the zip (in `workers` forked processes) into in-memory tables."""
    with zipfile.ZipFile(zip_path) as z:
        names = names or sorted((n for n in z.namelist() if n.endswith(".json")), key=lambda n: match_id_of(Path(n).stem))
    names = names[:limit]
    if people is None:
        people = scan_people(zip_path, names=names)
    pid_of = dict(zip(people.identifier, people.person_id.astype(int)))
    jobs = [(str(zip_path), names[i:i + chunk]) for i in range(0, len(names), chunk)]
    if workers <= 1:
        _init_worker(pid_of)
        return _collect(map(_parse_names, jobs), people)
    with mp.get_context("fork").Pool(min(workers, 3), initializer=_init_worker, initargs=(pid_of,)) as pool:
        return _collect(pool.imap(_parse_names, jobs), people)


def _collect(results, people: pd.DataFrame) -> dict:
    cols, matches, innings, events, so, pi, stats, failures = defaultdict(list), [], [], [], [], [], Counter(), []
    for res in results:
        for name, arr in res["balls"].items():
            cols[name].append(arr)
        matches += res["matches"]
        innings += res["innings"]
        events += res["events"]
        so += res["super_overs"]
        pi += res["player_innings"]
        stats.update(res["stats"])
        failures += res["failures"]
    arrays = {}
    for name in list(cols):
        parts = cols.pop(name)
        arrays[name] = np.concatenate(parts) if parts else np.array([])
        del parts
        _trim()
    balls = to_frame(arrays)
    del arrays
    matches = pd.DataFrame(matches)
    return dict(balls=balls, matches=matches, innings=pd.DataFrame(innings),
                events=pd.DataFrame(events, columns=EVENT_COLS).astype({"event": "category"}),
                super_overs=pd.DataFrame(so, columns=SO_COLS), player_innings=pd.DataFrame(pi, columns=PI_COLS),
                people=people, stats=stats, failures=failures)


def enrich(t: dict) -> dict:
    """Whole-table steps: team names, player context, overturned-kind imputation."""
    balls, matches = t["balls"], t["matches"]
    team_columns(balls, matches)
    ctx = player_context(t["player_innings"], matches)
    attach_player_context(balls, ctx)
    t["kind_imputation"] = impute_overturned_kind(balls, matches)
    del balls["bat_team_idx"]
    _trim()
    t["ball_columns"] = [c for c, _, _ in ROW_COLS + DERIVED_COLS if c in balls.columns]
    return t


def write_all(t: dict, out_dir: Path | str = OUT_DIR) -> dict:
    out_dir = Path(out_dir)
    sizes = {}
    for name, spec in (("balls", BALL_SPEC), ("matches", None), ("innings", None), ("events", None),
                       ("super_overs", None), ("player_innings", None), ("people_index", None)):
        df = t["people"] if name == "people_index" else t[name]
        if name != "balls":
            df = tidy(name, df)
        path = out_dir / f"{name}.parquet"
        write_table(df, path, spec, columns=t.get("ball_columns") if name == "balls" else None)
        sizes[name] = {"rows": int(len(df)), "mb": round(path.stat().st_size / 2 ** 20, 1)}
    return sizes


def build(zip_path: Path | str = CRICSHEET_ZIP, out_dir: Path | str = OUT_DIR, workers: int = 3,
          limit: int | None = None, report_path: Path | str | None = REPORT_PATH) -> dict:
    """Full build: people index, parse, enrichment, parquet, validation report."""
    timing, t0 = {}, time.time()
    people = scan_people(zip_path)
    timing["people_s"] = round(time.time() - t0, 1)
    t = parse_zip(zip_path, people, workers=workers, limit=limit)
    timing["parse_s"] = round(time.time() - t0 - timing["people_s"], 1)
    t1 = time.time()
    enrich(t)
    timing["enrich_s"] = round(time.time() - t1, 1)
    t1 = time.time()
    sizes = write_all(t, out_dir)
    timing["write_s"] = round(time.time() - t1, 1)
    t1 = time.time()
    report = validate(t)
    timing["validate_s"] = round(time.time() - t1, 1)
    timing["total_s"] = round(time.time() - t0, 1)
    report["build"] = dict(timing=timing, memory=_rss_mb(), tables=sizes, workers=workers,
                           balls_in_memory_mb=round(t["balls"].memory_usage(deep=False).sum() / 2 ** 20, 1))
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=1, default=str))
    return report
