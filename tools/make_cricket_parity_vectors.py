#!/usr/bin/env python3
"""Write the engine parity vectors tests/data/cricket_parity/{transitions,trajectories}.jsonl.

.venv/bin/python tools/make_cricket_parity_vectors.py [--check]
Both files are produced by the scalar reference engine (beating/cricket/sim.py) under the StubProvider
and must be reproduced exactly by docs/cricket/engine.js (plan section 9.6). Every input is passed
through a JSON round trip first, so the Python results are computed from exactly what the JavaScript
engine loads.

transitions.jsonl: one scripted-draw case per line, {"name", "note", "scenario", "state" (canonical
pre-state or null for a fresh match), "script" (forced decisions, sim.Match), "expect": {"state"
(canonical post-state, null once the match is over), "result", "events"} or {"error": "ScriptError"}}.
trajectories.jsonl: one line per (scenario, sim), {"name", "scenario", "seed", "sim", "events", "result",
"summary"}: the full event log (every uniform-consuming decision and the post-ball score) of sims 0-2.
--check regenerates both and exits non-zero when they differ from the files on disk.
"""
# %% setup
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.cricket import sim  # noqa: E402

OUT = ROOT / "tests" / "data" / "cricket_parity"


def rt(x):
    """JSON round trip (tuples become lists, keys strings)."""
    return json.loads(json.dumps(x))


def team(p: str, home: bool = False, **kw) -> dict:
    return {"name": p, "batting_order": [f"{p}{i}" for i in range(1, 12)], "keeper": f"{p}7", "home": home, **kw}


def scen(fam: str, date: str = "2025-06-01", **kw) -> dict:
    sc = {"fam": fam, "gender": "male", "date": date, "venue_id": "v1", "start_slot": "day",
          "teams": [team("A", True), team("B")], "toss": {"winner": 0, "decision": "bat"}, "umpires": ["U1", "U2"],
          "seed": 7}
    sc.update(kw)
    return sc


def state(sc: dict, number: int = 1, team_: int = 0, runs: int = 0, wkts: int = 0, legal: int = 0, done=(),
          **over) -> dict:
    """A canonical state from sim.impute_state plus explicit overrides of cur fields; umpire offset 0, Test
    days full."""
    p = {"cur": {"number": number, "team": team_, "runs": runs, "wkts": wkts, "legal_balls": legal},
         "done": [dict(d) for d in done]}
    if "innings_team" in over:
        p["innings_team"] = over.pop("innings_team")
    if "followed_on" in over:
        p["followed_on"] = over.pop("followed_on")
    for k in ("unavailable", "max_balls", "target"):
        if k in over:
            p["cur"][k] = over.pop(k)
    st = sim.impute_state(p, sc)
    st["cur"]["umpire_offset"] = 0
    pr = sim.Prepared(sc)
    if not pr.limited:
        st["clock"]["avail"] = [6 * pr.rules["test_overs_per_day"]] * pr.rules["test_days"]
    for k, v in over.items():
        st["cur"][k] = v
    cur = st["cur"]
    if cur["bowler"] is None and "bowler" not in over:
        n_overs = cur["max_balls"] // 6 if pr.limited else None
        overs = {}
        for b in cur["over_bowlers"]:
            overs[b] = overs.get(b, 0) + 1
        cur["bowler"] = sim.eligible_bowlers(pr.opts[1 - cur["team"]], overs, cur["last_bowler"], n_overs,
                                             len(cur["over_bowlers"]), pr.qrule)[0]
        cur["bowlers"].setdefault(cur["bowler"], {"balls": 0, "runs": 0, "wkts": 0})
    errs = sim.check_state(st, pr)

    if errs:
        raise ValueError(errs)
    return st


def ball(**kw) -> dict:
    return {"e": "ball", "dtype": "legal", **kw}


def dot(**kw) -> dict:
    return ball(cls=0, **kw)


def resume(**kw) -> dict:
    return {"e": "resume", **kw}


def over(bowler: str, **kw) -> dict:
    return {"e": "over", "bowler": bowler, **kw}


def case(name: str, note: str, sc: dict, st, script: list) -> dict:
    sc, st, script = rt(sc), rt(st), rt(script)
    try:
        out = sim.apply_script(copy.deepcopy(sc), copy.deepcopy(script), copy.deepcopy(st))
        expect = {"state": out["state"], "result": out["result"], "events": out["events"]}
    except sim.ScriptError as e:
        expect = {"error": "ScriptError", "message": str(e)}
    return {"name": name, "note": note, "scenario": sc, "state": st, "script": script, "expect": rt(expect)}


# %% transition cases (plan 9.6 list plus the extra rules)
def transition_cases() -> list[dict]:
    T20, ODI, TEST = scen("T20"), scen("ODI"), scen("TEST")
    T20_OLD = scen("T20", date="2019-06-01")
    out = []
    first = {"team": 0, "runs": 160, "wkts": 6, "legal_balls": 120, "max_balls": 120, "target": None, "end": "balls"}
    chase = dict(number=2, team_=1, done=[first])
    st = state(T20, runs=150, wkts=3, legal=100, **chase)
    out.append(case("chase_one_needed_five_wide", "1 needed, a 5-wide boundary is credited in full", T20,
                    state(T20, runs=160, wkts=3, legal=100, **chase), [resume(), ball(dtype="wide", wide_wkt="none", runs=5)]))
    out.append(case("chase_one_needed_wide_two_run", "1 needed, a wide with 2 run: only the wide counts", T20,
                    state(T20, runs=160, wkts=3, legal=100, **chase), [resume(), ball(dtype="wide", wide_wkt="none", runs=3)]))
    out.append(case("chase_two_needed_three_run_wicket_void", "2 needed, 3 run then a run-out attempt is void", T20,
                    state(T20, runs=159, wkts=3, legal=100, **chase), [resume(), ball(cls=7, runs=3)]))
    out.append(case("free_hit_wide_then_run_out", "free hit carries through a wide; run-out allowed, stumping not",
                    T20, state(T20, runs=40, wkts=1, legal=20, free_hit=True),
                    [resume(), ball(dtype="wide", wide_wkt="none", runs=1),
                     ball(cls=7, runs=0, ro_striker=True, ro_new_on_strike=True), dot()]))
    out.append(case("free_hit_wide_stumping_impossible", "stumping off a wide on a free hit is refused", T20,
                    state(T20, runs=40, wkts=1, legal=20, free_hit=True),
                    [resume(), ball(dtype="wide", wide_wkt="stumped", runs=1)]))
    out.append(case("free_hit_out_masked", "a bowler-credited out on a free hit is refused", T20,
                    state(T20, runs=40, wkts=1, legal=20, free_hit=True), [resume(), ball(cls=6, kind="bowled")]))
    out.append(case("wicket_last_ball_of_innings", "caught on ball 120: innings 1 ends on balls, innings 2 opens",
                    T20, state(T20, runs=170, wkts=5, legal=119),
                    [resume(), ball(cls=6, kind="caught"), {"e": "over"},
                     {"e": "innings", "umpire_offset": 1, "bowler": "A11"}]))
    out.append(case("ten_wickets", "the tenth wicket ends the innings (all out)", T20,
                    state(T20, runs=120, wkts=9, legal=100),
                    [resume(), ball(cls=6, kind="bowled"), {"e": "over"}, {"e": "innings", "umpire_offset": 0,
                                                                            "bowler": "A10"}]))
    out.append(case("nine_wickets_one_absent", "with one batter absent the ninth wicket is all out", T20,
                    state(T20, runs=110, wkts=8, legal=90, unavailable=["A11"]),
                    [resume(), ball(cls=6, kind="lbw"), {"e": "over"}, {"e": "innings", "umpire_offset": 0,
                                                                         "bowler": "A10"}]))
    out.append(case("run_out_one_completed", "striker run out going for a second: 1 run counts, placement table",
                    T20, state(T20, runs=60, wkts=2, legal=50), [resume(), ball(cls=7, runs=1, ro_striker=True,
                                                                                   ro_new_on_strike=False)]))
    out.append(case("caught_crossed_before_2022", "caught_crossing_counts: the batters crossed, new batter at the "
                    "non-striker's end", T20_OLD, state(T20_OLD, runs=60, wkts=2, legal=50),
                    [resume(), ball(cls=6, kind="caught", bat_review=False, crossed=True)]))
    out.append(case("caught_after_2022", "from October 2022 the new batter always faces", T20,
                    state(T20, runs=60, wkts=2, legal=50), [resume(), ball(cls=6, kind="caught", bat_review=False)]))
    # quota dead end: 3 overs left; B11 has 2 left, B10 (last) none, B9 one. Giving B9 the 18th over leaves
    # overs 19-20 to B11 alone, so only B11 (and the other options) are feasible.
    bw = {"B11": {"balls": 12, "runs": 20, "wkts": 1}, "B10": {"balls": 24, "runs": 30, "wkts": 1},
          "B9": {"balls": 18, "runs": 25, "wkts": 0}, "B8": {"balls": 24, "runs": 30, "wkts": 1},
          "B6": {"balls": 24, "runs": 35, "wkts": 1}}
    ob = ["B10", "B8", "B10", "B8", "B6", "B9", "B6", "B9", "B10", "B8", "B6", "B11", "B6", "B9", "B11", "B8", "B10"]
    qd = dict(bowlers=bw, over_bowlers=ob, bowler=None, last_bowler="B10", ball_in_over=0)
    opts5 = scen("T20", teams=[team("A", True), team("B", bowlers=["B11", "B10", "B9", "B8", "B6"])])
    out.append(case("quota_dead_end_filter", "B9 has quota left but choosing it makes overs 19-20 uncoverable",
                    opts5, state(opts5, runs=130, wkts=4, legal=102, **qd), [resume(bowler="B11"), dot()]))
    out.append(case("quota_dead_end_refused", "forcing the infeasible bowler is refused", opts5,
                    state(opts5, runs=130, wkts=4, legal=102, **qd), [resume(bowler="B9")]))
    odi_first = {"team": 0, "runs": 280, "wkts": 7, "legal_balls": 300, "max_balls": 300, "target": None,
                 "end": "balls"}
    st = state(ODI, number=2, team_=1, runs=110, wkts=2, legal=120, done=[odi_first])
    st["pending_interruptions"] = [{"start": 410, "lost": 60}]
    out.append(case("dls_revision_mid_innings", "an interruption at the over end cuts innings 2 by 10 overs and "
                    "revises the target", ODI, st, [resume()] + [dot()] * 5 + [ball(cls=1)] + [over("A8")]))
    st = state(ODI, number=2, team_=1, runs=200, wkts=4, legal=180, done=[odi_first])
    st["pending_interruptions"] = [{"start": 486, "lost": 240}]
    out.append(case("dls_cut_par_result", "innings 2 cut short after 31 overs: decided against par", ODI, st,
                    [resume()] + [dot()] * 6 + [{"e": "over"}]))
    out.append(case("dls_par_tie", "innings 2 cut short level with par: a tie that stands", ODI,
                    _par_tie_state(ODI, odi_first), [resume()] + [dot()] * 6 + [{"e": "over"}]))
    T20_TOSS = scen("T20", toss=None)
    out.append(case("pre_match_reduction", "a reduction before play shortens both innings equally", T20_TOSS, None,
                    [{"e": "match", "toss_winner": 1, "toss_bat": False, "interruptions": [{"start": 0, "lost": 30}]},
                     {"e": "innings", "umpire_offset": 0, "bowler": "B11"}]))
    t1 = {"team": 0, "runs": 450, "wkts": 10, "legal_balls": 900, "max_balls": None, "target": None, "end": "all_out"}
    st = state(TEST, number=2, team_=1, runs=180, wkts=9, legal=400, done=[t1])
    out.append(case("follow_on_enforced", "lead 270 >= 200 with 5 days: the follow-on is enforced, order "
                    "[A, B, B, A]", TEST, st, [resume(), ball(cls=6, kind="bowled"), {"e": "over"},
                                                {"e": "innings", "follow_on": True, "umpire_offset": 1,
                                                 "bowler": "A11"}]))
    out.append(case("follow_on_declined", "follow-on not enforced: A bats again", TEST, st,
                    [resume(), ball(cls=6, kind="bowled"), {"e": "over"},
                     {"e": "innings", "follow_on": False, "umpire_offset": 1, "bowler": "B11"}]))
    t2 = {"team": 1, "runs": 180, "wkts": 10, "legal_balls": 401, "max_balls": None, "target": None, "end": "all_out"}
    st = state(TEST, number=3, team_=1, runs=200, wkts=9, legal=420, done=[t1, t2], innings_team=[0, 1, 1, 0],
               followed_on=True)
    out.append(case("follow_on_innings_defeat", "B, following on, all out 70 behind: A wins by an innings", TEST, st,
                    [resume(), ball(cls=6, kind="lbw", bat_review=False)]))
    t2b, t2c = dict(t2, runs=380), dict(t2, runs=520)
    st = state(TEST, number=3, team_=0, runs=60, wkts=4, legal=149, done=[t1, t2c])
    out.append(case("innings3_no_declaration_without_lead", "innings 3 with lead -10 at an over end: no declaration "
                    "draw", TEST, st, [resume(), dot(), over("B10"), dot()]))
    out.append(case("innings3_declaration_refused_without_lead", "a forced declaration with lead <= 0 is refused",
                    TEST, st, [resume(), dot(), over("B10", declare=True)]))
    st = state(TEST, number=3, team_=0, runs=69, wkts=9, legal=200, done=[t1, t2c])
    out.append(case("innings3_all_out_level", "innings 3 all out exactly level: innings 4 target is 1", TEST, st,
                    [resume(), ball(cls=1), ball(cls=6, kind="bowled"), {"e": "over"},
                     {"e": "innings", "umpire_offset": 0, "bowler": "A11"}]))
    st = state(TEST, number=3, team_=0, runs=69, wkts=9, legal=200, done=[t1, t2c])
    out.append(case("innings3_all_out_behind", "innings 3 all out still behind: innings victory", TEST, st,
                    [resume(), ball(cls=6, kind="bowled")]))
    st = state(TEST, number=1, team_=0, runs=520, wkts=6, legal=899)
    out.append(case("declaration", "declared at the end of over 150; innings 2 opens", TEST, st,
                    [resume(), ball(cls=4, runs=4), {"e": "over", "declare": True},
                     {"e": "innings", "umpire_offset": 0, "bowler": "A11"}]))
    t3 = {"team": 0, "runs": 200, "wkts": 10, "legal_balls": 450, "max_balls": None, "target": None, "end": "all_out"}
    st = state(TEST, number=4, team_=1, runs=269, wkts=9, legal=500, done=[t1, t2b, t3])
    out.append(case("fourth_innings_tie", "innings 4 all out with scores level: a tie", TEST, st,
                    [resume(), ball(cls=1), ball(cls=6, kind="stumped")]))
    st = state(TEST, number=4, team_=1, runs=269, wkts=5, legal=500, done=[t1, t2b, t3])
    out.append(case("test_clock_draw", "the clock runs out with the scores level: a draw, not a tie", TEST, _clock_state(TEST, st),
                    [resume(), ball(cls=1)]))
    st = state(TEST, number=1, team_=0, runs=250, wkts=3, legal=479, reviews=[0, 1])
    sct = scen("TEST", rules={"review_topup_after_80": True})
    st2 = state(sct, number=1, team_=0, runs=250, wkts=3, legal=479, reviews=[0, 1])
    out.append(case("test_ball_80_new_ball", "ball 480 ends over 80: new ball taken, reviews topped up", sct, st2,
                    [resume(), dot(), over("B11", new_ball=True), dot()]))
    out.append(case("test_ball_80_new_ball_declined", "new ball declined at 80 overs (asked again next over)", TEST,
                    st, [resume(), dot(), over("B11", new_ball=False), dot()]))
    # super over: innings 2 ends level, then two super overs (the second decides).
    so = scen("T20", rules={"tie_break": "so_repeat"})
    st = state(so, number=2, team_=1, runs=159, wkts=6, legal=119, done=[first])
    sc1 = [ball(cls=4, runs=4), ball(cls=1), dot(), ball(cls=6, kind="bowled"), ball(cls=2), ball(cls=1)]
    sc2 = [ball(cls=5, runs=6), dot(), ball(cls=1), ball(cls=6, kind="caught", bat_review=False), dot(), ball(cls=1)]
    sc3 = [ball(cls=1), ball(cls=4, runs=4), dot(), dot(), ball(cls=1), dot()]
    sc4 = [ball(cls=4, runs=4), ball(cls=2), ball(cls=1)]
    out.append(case("super_over", "tie, then a tied super over and a repeat won by the chasing side", so, st,
                    [resume(), ball(cls=1), {"e": "innings", "umpire_offset": 0}] + sc1 +
                    [{"e": "innings", "umpire_offset": 1}] + sc2 + [{"e": "innings", "umpire_offset": 0}] + sc3 +
                    [{"e": "innings", "umpire_offset": 1}] + sc4))
    nso = scen("T20", rules={"tie_break": "none"})
    out.append(case("tie_no_tie_break", "a tie stands when the rules have no tie-break", nso,
                    state(nso, number=2, team_=1, runs=159, wkts=6, legal=119, done=[first]), [resume(), ball(cls=1)]))
    bo = scen("T20", rules={"tie_break": "bowl_out"})
    stb = state(bo, number=2, team_=1, runs=159, wkts=6, legal=119, done=[first])
    out.append(case("tie_bowl_out_coin", "bowl-out simplified to a coin (D5)", bo, stb,
                    [resume(coin=1), ball(cls=1)]))
    base = state(T20, runs=60, wkts=2, legal=50)
    out.append(case("five_runs_rotate_strike", "runs 5 off the bat (four class) are odd: the batters swap", T20, base,
                    [resume(), ball(cls=4, runs=5)]))
    out.append(case("four_byes_boundary", "4 byes: a boundary, no swap, not charged to the bowler", T20, base,
                    [resume(), ball(cls=8, runs=4, missed=False, spec=False)]))
    out.append(case("three_byes_rotate", "3 leg-byes run: swap, not charged to the bowler", T20, base,
                    [resume(), ball(cls=8, runs=3, missed=False, spec=False)]))
    out.append(case("wide_stumping", "stumped off a wide: 1 wide, wicket to the bowler, new batter on strike", T20,
                    base, [resume(), ball(dtype="wide", wide_wkt="stumped", runs=1)]))
    out.append(case("wide_run_out", "run out off a wide after 1 run", T20, base,
                    [resume(), ball(dtype="wide", wide_wkt="run_out", runs=2, ro_striker=False,
                                    ro_new_on_strike=True)]))
    out.append(case("noball_run_out", "run out off a no-ball: penalty to team and bowler, ball faced, free hit next",
                    T20, base, [resume(), ball(dtype="noball", cls=7, runs=1, ro_striker=False,
                                               ro_new_on_strike=False)]))
    out.append(case("noball_four", "4 off a no-ball: 5 to the team and the bowler", T20, base,
                    [resume(), ball(dtype="noball", cls=4, runs=4)]))
    out.append(case("free_hit_chain_two_wides", "no-ball -> free hit through two wides, cleared by a legal ball",
                    T20, base, [resume(), ball(dtype="noball", cls=0), ball(dtype="wide", wide_wkt="none", runs=1),
                                ball(dtype="wide", wide_wkt="none", runs=1), ball(cls=1), dot()]))
    fh_odd = scen("T20", date="2014-06-01")
    out.append(case("front_foot_free_hit_draw", "front-foot era: a no-ball gives a free hit only when drawn", fh_odd,
                    state(fh_odd, runs=60, wkts=2, legal=50), [resume(), ball(dtype="noball", cls=0, free_hit=False),
                                                              ball(cls=6, kind="bowled")]))
    out.append(case("over_end_after_last_ball_wicket", "bowled on ball 6: new batter at the striker's end, then the "
                    "over-end swap puts him at the non-striker's end", T20, state(T20, runs=60, wkts=2, legal=47),
                    [resume(), ball(cls=6, kind="bowled"), over("B9"), dot()]))
    out.append(case("drs_bat_overturned", "batting review overturns an lbw: a dot, review kept", T20, base,
                    [resume(), ball(cls=6, kind="lbw", bat_review=True, overturned=True)]))
    out.append(case("drs_bat_umpires_call", "lbw review struck down on umpire's call: out, review retained", T20,
                    base, [resume(), ball(cls=6, kind="lbw", bat_review=True, overturned=False, ucall=True)]))
    out.append(case("drs_bat_failed", "caught review struck down: out, review lost", T20, base,
                    [resume(), ball(cls=6, kind="caught", bat_review=True, overturned=False)]))
    old_uc = scen("T20", date="2016-06-01")
    out.append(case("drs_umpires_call_lost_pre_2017", "before October 2017 an umpire's call review is lost", old_uc,
                    state(old_uc, runs=60, wkts=2, legal=50),
                    [resume(), ball(cls=6, kind="lbw", bat_review=True, overturned=False, ucall=True)]))
    out.append(case("drs_field_success", "missed out on a dot reviewed by the fielding side: lbw, out", T20, base,
                    [resume(), dot(missed=True, missed_lbw=True)]))
    out.append(case("drs_field_speculative", "failed speculative fielding review on a single", T20, base,
                    [resume(), ball(cls=1, spec=True, spec_ucall=False)]))
    nodrs = scen("T20", drs={"enabled": False})
    out.append(case("drs_disabled_missed_out_stands", "no DRS: the missed out stands and is counted", nodrs,
                    state(nodrs, runs=60, wkts=2, legal=50), [resume(), dot(missed=True), ball(cls=6, kind="lbw")]))
    out.append(case("fresh_match_toss", "fresh T20 before the toss: forced toss, first over", T20_TOSS, None,
                    [{"e": "match", "toss_winner": 1, "toss_bat": True, "interruptions": []},
                     {"e": "innings", "umpire_offset": 1, "bowler": "A11"}, ball(cls=1), dot()]))
    out.append(case("fresh_match_given_toss", "fresh ODI with the toss given by the scenario", ODI, None,
                    [{"e": "match", "interruptions": []},
                     {"e": "innings", "umpire_offset": 1, "bowler": "B11"}, ball(cls=1), dot()]))
    return out


def _par_tie_state(sc, first):
    """Innings 2 state whose cut at the next over end leaves the score exactly on par."""
    pr = sim.Prepared(rt(sc))
    for runs in range(150, 280):
        st = state(sc, number=2, team_=1, runs=runs, wkts=4, legal=180, done=[first])
        st["pending_interruptions"] = [{"start": 486, "lost": 240}]
        m = sim.Match(pr, script=[{"e": "resume"}] + [dot()] * 6 + [{"e": "over"}], log=[], state=rt(st)).play()
        if m.result and m.result["result"] == "tie":
            return st
    raise RuntimeError("no par tie found")


def _clock_state(sc, st):
    """Test innings-4 state one legal ball before the clock runs out (scores 1 short)."""
    pr = sim.Prepared(rt(sc))
    used = sum(d["legal_balls"] for d in st["done"]) + st["cur"]["legal_balls"] + 12 * 3
    st["clock"]["avail"] = [540] * 4 + [used + 1 - 4 * 540]
    st["clock"]["used"] = used
    if sum(st["clock"]["avail"]) != used + 1 or not 0 < st["clock"]["avail"][-1] <= 540:
        raise RuntimeError("bad clock")
    assert not sim.check_state(st, pr)
    return st


# %% trajectories (sims 0-2 of four fixed scenarios)
def trajectory_scenarios() -> list[dict]:
    t20 = scen("T20", toss=None, seed=101, weather={"temp_c": 30, "rh": 70, "cloud_oktas": 6, "rain_risk": 0.3},
               player_form={"A3": {"bat_runs_sd": 1.0}, "B11": {"bowl_wkt_sd": -0.5}}, pitch={"runs_sd": 0.5})
    odi = scen("ODI", toss={"winner": 1, "decision": "field"}, seed=202, weather={"rain_risk": 1.0})
    test = scen("TEST", toss=None, seed=303, start_slot="day", weather={"rain_risk": 0.3})
    live = scen("T20", toss={"winner": 0, "decision": "bat"}, seed=404, pitch={"known": False, "runs_sd": 0.0})
    pr = sim.Prepared(rt(live))
    views = []
    m = sim.Match(pr, 5, 99, views=views, stop_at=(1, 75)).play()
    st = m.to_state()
    st["balls"] = views
    st["pending_interruptions"] = None
    live["state"] = st
    return [("t20_pre_toss", t20), ("odi_rain", odi), ("test", test), ("t20_in_play", live)]


def trajectories() -> list[dict]:
    out = []
    for name, sc in trajectory_scenarios():
        sc = rt(sc)
        pr = sim.Prepared(sc)
        for i in range(3):
            log = []
            m = sim.Match(pr, i, sc["seed"], log=log, state=pr.sc["state"]).play()
            rec = m.record()
            summary = {"innings": rec["innings"], "code": rec["code"], "deliveries": rec["deliveries"]}
            out.append(rt({"name": name, "scenario": sc if i == 0 else None, "seed": sc["seed"], "sim": i,
                           "events": log, "result": m.result, "summary": summary}))
    return out


def dump(rows) -> str:
    return "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in rows)


# %% write
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = {"transitions.jsonl": dump(transition_cases()), "trajectories.jsonl": dump(trajectories())}
    bad = 0
    for fn, text in files.items():
        path = OUT / fn
        if args.check:
            same = path.exists() and path.read_text() == text
            print(fn, "ok" if same else "DIFFERS")
            bad += not same
        else:
            path.write_text(text)
            print(fn, len(text.splitlines()), "rows", len(text) // 1024, "KB")
    sys.exit(1 if bad else 0)
