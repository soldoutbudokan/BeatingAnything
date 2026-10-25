"""Scalar reference engine for the ball-by-ball cricket Monte Carlo (plan sections 7 and 9).

Method. One simulation at a time, in float64, with the shared xoshiro128** streams of rng.py. The engine
owns match flow and the rules; every probability comes from a provider (provider.py). It simulates T20,
ODI and Test cricket, men and women: toss, innings order (follow-on [A, B, B, A]), batting order and
arrivals, bowler choice under the eligibility and feasibility filter of 7.1, the delivery transition of
9.2 in its exact order, the DRS layer of 9.4, free-hit carry-over, run-out and crossing placement, chase
completion crediting, all-out with unavailable batters, the Test clock, declarations, follow-on,
innings victories, limited-overs interruptions with integer DLS-style targets (7.6), no result, ties and
tie-breaks (7.7), match/innings latents and player form, the in-play canonical state (9.3) with its
latent update, and the outputs of 9.7. ``docs/cricket/engine.js`` is the fast twin and must reproduce
this file's decisions, slots and arithmetic exactly.

Random numbers (plan 9.5). Five streams per (seed, sim): 0 ball, 1 over, 2 innings, 3 match, 4 player.
Every event takes a fixed block from its stream whether or not it needs each uniform; slot i is the
i-th uniform of the block. Conversions: categorical = first k with u * cum[-1] < cum[k] over running
float64 sums of exp(eta - max) (eta) or of the weights themselves (tables), falling back to the last
class; Bernoulli = u < p; normal = Box-Muller with log(1 - u), pair (u1, u2) -> (r cos 2 pi u2,
r sin 2 pi u2).

  ball, 12 per delivery (every delivery, super overs included)
    0  dtype: categorical over dtype_eta (legal, wide, noball)
    1  outcome class: categorical over outcome_eta, class 6 + MASK_OFFSET on no-balls and free hits
    2  exact runs: wide k = 1 + categorical(wide_runs(view, wide wicket)); four: 5 if u < p5 else 4;
       six: 7 if u < p7 else 6; byes 1 + categorical(bye_runs); run-out runs completed
       categorical(runout_runs) over 0..3
    3  legal class 6: kind = categorical(wk_eta); wide: wide wicket = categorical(wide_wkt) over
       none/stumped/run_out with stumped weight 0 on a free hit; no-ball under front_foot rules:
       free hit next if u < p_free_hit_given_nb
    4  run-out victim: the striker if u < runout_who(view, runs)
    5  run-out: new batter on strike if u < runout_new_on_strike(view, who, min(runs, 2)); caught when
       caught_crossing_counts: new batter to the non-striker's end if u < p_crossed
    6  batting review: u < q_bat (on-field caught or lbw, DRS on, reviews left, not a free hit)
    7  overturned: u < min(1, p_overturn_bat * accuracy_mult) -> the ball becomes a dot
    8  umpire's call (lbw only): u < min(1, p_ucall_bat * ucall_mult)
    9  missed out on a legal dot or bye that is not a free hit: u < min(1, lambda_field * accuracy_mult);
       it becomes a successful fielding review when DRS is on and the fielding side has a review,
       otherwise it is counted as a missed out standing
    10 kind of a reviewed missed out: lbw if u < lbw share else caught
    11 speculative fielding review on a legal non-wicket ball or a wicketless wide (DRS on, fielding
       review left, not a free hit): failed review if u < r_spec, umpire's call if u < r_spec * share
  over, 4 per over-end event
    0 interruption (reserved; the schedule is pre-drawn from the match stream)
    1 declaration (Tests, innings 1-2, or 3 with lead > 0): u < declare_hazard
    2 next bowler: categorical over bowler_utility of the eligible bowlers, in bowling-option order
    3 new ball (Tests, ball age >= new_ball_after_overs): u < new_ball_prob
  innings, 4 per innings-start event (main innings, super-over innings, in-play resume)
    0 follow-on (start of Test innings 3 when the lead reaches the threshold): u < follow_on_prob
    1 umpire end: offset 0 if u < 0.5 else 1; bowler's-end umpire = umpires[(over + offset) % 2]
    2 opening bowler (resume: the next over's bowler when no over is in progress)
    3 spare
  match, 64 at match start or in-play resume
    0 toss winner team 0 if u < 0.5        1 bat first if u < toss_bat_prob
    2-5 match latent normals: pairs (2,3), (4,5) -> z for match latents 0..3
    6-13 innings latent normals: pair (6+2k, 7+2k) -> z for main innings k = 0..3 (runs, wicket)
    14-21 Test day availability: day d = 1..8 uses slot 13 + d
    22-37 interruption schedule: the 16 uniforms passed to the provider
    38 tie-break coin: team 0 if u < 0.5 (bowl-out, or after the last super over)
    39-63 spare
  player, 4 per player slot (team 0's batting order, then its bowling XI and options not in it, then
  team 1 the same): pair (0,1) -> batting (runs, wicket) z, pair (2,3) -> bowling (runs, wicket) z

Events fire as follows. The match-start event (or the resume event of an in-play state) runs once. An
innings-start event opens every main and super-over innings. An over-end event fires after a delivery
that completes an over or ends an innings while the match is undecided and more main-innings
deliveries can follow (never in super overs); in order it applies due interruptions, then (innings
continuing) the declaration, the next bowler and the new ball.

Rules resolved here (see also the module report): interruption starts are measured in match legal balls
bowled; a mid-innings-1 reduction cuts both innings to old - lost, closing innings 1 if it has already
passed that length; a reduction at the innings break or in innings 2 changes innings 2 only; resources
lost = P(u_before, w) - P(u_after, w); par ties stand without a tie-break; at most 6 super overs (one
plus five repeats) and then the coin. Super overs use the match latent and the batting side's
main-innings latent; their selections use zero latents and zero form. Run-out runs are bat runs.

Limits. Pure Python: roughly 50-70k deliveries per second on this machine; bulk evaluation belongs to
docs/cricket/cli.js. No retirements, nightwatchmen or multi-bowler overs (deviations D2, D3, D7); the
Hundred is not simulated (D1); in-play states must be inside a main innings.
"""
from __future__ import annotations

from collections import Counter
import copy
import math

from beating.cricket.glm import MASK_OFFSET
from beating.cricket.provider import (DTYPES, KINDS, VIEW_KEYS, StubProvider, WIDE_WKTS, state_schema_errors,
                                      validate_scenario)
from beating.cricket.rng import Stream

LEGAL, WIDE, NOBALL = 0, 1, 2
DOT, ONE, TWO, THREE, FOUR, SIX, OUT, RUN_OUT, BYES = range(9)
CAUGHT, BOWLED, LBW, STUMPED, OTHER, RO = range(6)
KIND_ALL = KINDS + ("run_out",)
NOMINAL_RUNS = (0, 1, 2, 3, 4, 6, 0, 0, 1)
M_TOSS, M_TOSS_BAT, M_LAT, M_INN_LAT, M_DAYS, M_RAIN, M_COIN = 0, 1, 2, 6, 14, 22, 38
MAX_DAYS, MAX_SUPER_OVERS = 8, 6
END_REASONS = ("all_out", "balls", "target", "declared", "clock", "cut", "no_result")
CODES = ("win0", "win1", "tie", "draw", "no_result")
_DT = {k: i for i, k in enumerate(DTYPES)}
_WW = {k: i for i, k in enumerate(WIDE_WKTS)}
_KI = {k: i for i, k in enumerate(KIND_ALL)}
VIEW_ORDER = tuple(VIEW_KEYS)


class ScriptError(ValueError):
    """A scripted decision is missing, impossible, or the script ended between events."""


class _Stop(Exception):
    pass


# ---------------------------------------------------------------- conversions (plan 9.5)

def cat_eta(u: float, eta) -> int:
    m = max(eta)
    cum = []
    c = 0.0
    for e in eta:
        c += math.exp(e - m)
        cum.append(c)
    t = u * c
    for k, ck in enumerate(cum):
        if t < ck:
            return k
    return len(cum) - 1


def cat_w(u: float, w) -> int:
    cum = []
    c = 0.0
    for x in w:
        c += x
        cum.append(c)
    t = u * c
    for k, ck in enumerate(cum):
        if t < ck:
            return k
    return len(cum) - 1


def normal_pair(u1: float, u2: float) -> tuple[float, float]:
    r = math.sqrt(-2.0 * math.log(1.0 - u1))
    return r * math.cos(2 * math.pi * u2), r * math.sin(2 * math.pi * u2)


def softmax(eta) -> list[float]:
    m = max(eta)
    ex = [math.exp(e - m) for e in eta]
    s = sum(ex)
    return [x / s for x in ex]


# ---------------------------------------------------------------- rules helpers

def eligible_bowlers(opts, overs: dict, last, n_overs: int | None, done: int) -> list:
    """Plan 7.1: bowlers who may take the next over. `overs` maps id -> completed overs, `n_overs` is
    the innings length in overs (None: no quota), `done` the overs completed. The quota is n // 5 with
    n % 5 one-over bonuses; after giving i the over, the remaining R' overs must be coverable:
    sum_j min(q_j, cap_j) + bonuses >= R', cap_j = R' // 2 for j = i and ceil(R' / 2) otherwise, with
    the unclaimed bonuses added greedily to bowlers whose quota is below their cap."""
    if n_overs is None:
        return [i for i in opts if i != last]
    base, bonus = divmod(n_overs, 5)
    free = bonus - sum(1 for o in overs.values() if o > base)
    r2 = n_overs - done - 1
    out = []
    for i in opts:
        oi = overs.get(i, 0)
        if i == last or oi > base or (oi == base and free <= 0):
            continue
        fi = free - (1 if oi == base else 0)
        tot = nb = 0
        for j in opts:
            oj = overs.get(j, 0) + (1 if j == i else 0)
            cap = r2 // 2 if j == i else (r2 + 1) // 2
            if oj > base:
                tot += min(max(0, base + 1 - oj), cap)
            else:
                q = base - oj
                tot += min(q, cap)
                nb += q < cap
        if tot + min(max(fi, 0), nb) >= r2:
            out.append(i)
    return out


def quota_left(overs: dict, b, n_overs: int | None):
    if n_overs is None:
        return None
    base, bonus = divmod(n_overs, 5)
    o = overs.get(b, 0)
    if o > base:
        return max(0, base + 1 - o)
    free = bonus - sum(1 for x in overs.values() if x > base)
    return base - o + (1 if free > 0 else 0)


def spell_overs(over_bowlers: list, b) -> int:
    n, j = 0, len(over_bowlers) - 2
    while j >= 0 and over_bowlers[j] == b:
        n += 1
        j -= 2
    return n


def revised_target(s1: int, r1: int, r2: int, g: float) -> int:
    """Plan 7.6, integer arithmetic: R2 <= R1: S*R2 // R1 + 1; else S + floor(G*(R2-R1)/1000) + 1."""
    if r2 <= r1:
        return s1 * r2 // r1 + 1
    return s1 + math.floor(g * (r2 - r1) / 1000) + 1


def scale_ball(b: int, n_new: int, n_sched: int) -> int:
    """Window boundary b (legal balls) of the scheduled innings scaled to a revised length, half up."""
    return (2 * b * n_new + n_sched) // (2 * n_sched)


def follow_on_threshold(table, days_remaining: int) -> int | None:
    for d, lead in table or ():
        if days_remaining >= d:
            return lead
    return None


# ---------------------------------------------------------------- scenario preparation

class Prepared:
    """Scenario-level statics shared by every simulation: rules, teams, bowling options, slots, view."""

    def __init__(self, scenario: dict, provider=None):
        sc = validate_scenario(scenario)
        P = provider if provider is not None else StubProvider()
        self.sc, self.P = sc, P
        self.fam = sc["fam"]
        self.limited = self.fam != "TEST"
        r = dict(P.rules(sc))
        d = sc["drs"]
        if d["enabled"] is not None:
            r["drs_enabled"] = bool(d["enabled"])
        if d["reviews_per_innings"] is not None:
            r["reviews_per_innings"] = int(d["reviews_per_innings"])
        if d["umpires_call_retains"] is not None:
            r["umpires_call_retains"] = bool(d["umpires_call_retains"])
        if sc["scheduled_days"]:
            r["test_days"] = int(sc["scheduled_days"])
        if r["balls_per_over"] != 6:
            raise ValueError("only 6-ball overs are simulated (deviation D1)")
        self.rules, self.bpo = r, 6
        self.acc, self.ucm = d["accuracy_mult"], d["ucall_mult"]
        self.rpi = int(r["reviews_per_innings"] or 0) if r["drs_enabled"] else 0
        self.prep = P.prepare(sc)
        spec = P.latent_spec(sc)
        self.lat_m, self.lat_i = list(spec["match"]), list(spec["innings"])
        if len(self.lat_m) > 4 or len(self.lat_i) > 2:
            raise ValueError("at most 4 match and 2 innings latents")
        self.G = P.resource_G(sc) if self.limited else None
        self._res = {}
        self.orders, self.absent, self.keeper, self.opts, self.part_timers, self.xi = [], [], [], [], [], []
        self.pos, self.slots = {}, []
        for t, team in enumerate(sc["teams"]):
            order = list(team["batting_order"])
            self.orders.append(order)
            self.absent.append(set(team["absent"]))
            self.keeper.append(team["keeper"])
            for i, p in enumerate(order):
                self.pos[p] = i + 1
            xi = [p for p in team["bowling_xi"] if p not in team["absent"]]
            self.xi.append(xi)
            opts = list(team["bowlers"]) if team.get("bowlers") else [p for p in reversed(xi) if p != team["keeper"]]
            added = []
            if self.limited:
                n = r["max_balls"] // 6
                extra = [p for p in order if p not in opts and p != team["keeper"] and p not in team["absent"]]
                while not eligible_bowlers(opts, {}, None, n, 0) and extra:
                    p = extra.pop(0)
                    opts.append(p)
                    added.append(p)
            self.opts.append(opts)
            self.part_timers.append(set(added))
            for p in order + [p for p in team["bowling_xi"] if p not in order] + \
                    [p for p in opts if p not in order and p not in team["bowling_xi"]]:
                if p not in self.slots:
                    self.slots.append(p)
                self.pos.setdefault(p, 11)
        self.part_timer_report = [sorted(s) for s in self.part_timers]
        home = [t["home"] for t in sc["teams"]]
        self.home_status = ["neutral" if sc["neutral"] or not (home[t] or home[1 - t]) else
                            "home" if home[t] else "away" for t in (0, 1)]
        sd = r["test_days"] if self.fam == "TEST" else None
        self.view0 = {k: None for k in VIEW_ORDER}
        self.view0.update(fam=self.fam, gender=sc["gender"], competition_id=sc["competition_id"], date=sc["date"],
                          venue_id=sc["venue_id"], neutral=sc["neutral"], start_slot=sc["start_slot"],
                          weather=sc["weather"], umpires=sc["umpires"], rules=r, drs_enabled=bool(r["drs_enabled"]),
                          sched_balls=r["max_balls"], scheduled_days=sd,
                          teams=tuple(t["name"] for t in sc["teams"]), home=tuple(home), prep=self.prep,
                          super_over=0, so_innings=0, followed_on=False, prev_innings=())

    def res(self, balls_remaining: int, wkts: int) -> int:
        key = (balls_remaining, wkts)
        v = self._res.get(key)
        if v is None:
            v = self._res[key] = int(self.P.resource(self.sc, balls_remaining, wkts))
        return v

    def windows(self, max_balls):
        r = self.rules
        if not self.limited:
            return [], []
        n = r["max_balls"]
        fo = [(scale_ball((a - 1) * 6, max_balls, n), scale_ball(b * 6, max_balls, n), m)
              for a, b, m in r["fielders_outside"] or []]
        pp = [(scale_ball((a - 1) * 6, max_balls, n), scale_ball(b * 6, max_balls, n), f"pp{i + 1}")
              for i, (a, b) in enumerate(r["pp_mandatory"] or [])]
        return fo, pp




class Innings:
    __slots__ = ("number", "so", "so_inn", "team", "opp", "order", "runs", "wkts", "legal", "max_balls",
                 "max_wkts", "target", "timing", "striker", "nonstriker", "bat", "out", "unavail", "to_come",
                 "n_arrived", "bowl", "over_bowlers", "bowler", "last_bowler", "spell", "ball_in_over",
                 "free_hit", "reviews", "fail_reviews", "umpire_offset", "p_runs", "p_balls", "ball_age",
                 "second_new_ball", "over_runs", "wkt_this_over", "last_over_runs", "last_over_wkt",
                 "over_scores", "end", "windows", "agg_bat", "agg_opp", "closed", "extras")

    def __init__(self):
        self.so = self.so_inn = 0
        self.runs = self.wkts = self.legal = self.ball_in_over = self.n_arrived = 0
        self.max_wkts = 10
        self.target = self.timing = self.bowler = self.last_bowler = self.umpire_offset = self.end = None
        self.striker = self.nonstriker = None
        self.bat, self.bowl = {}, {}
        self.out, self.over_bowlers, self.over_scores, self.to_come = [], [], [], []
        self.unavail = set()
        self.spell = 0
        self.free_hit = self.second_new_ball = self.wkt_this_over = self.last_over_wkt = self.closed = False
        self.reviews, self.fail_reviews = [0, 0], [0, 0]
        self.p_runs = self.p_balls = self.ball_age = self.over_runs = self.last_over_runs = self.extras = 0
        self.windows = ([], [])
        self.agg_bat = self.agg_opp = 0


# ---------------------------------------------------------------- one simulation

class Match:
    """One simulated match. `script` (list of event dicts) replaces every random decision by a forced
    value (scripted-draw mode, no random numbers are drawn); `log` collects the event log; `state` is an
    in-play canonical state (plan 9.3) to resume from."""

    def __init__(self, pr: Prepared, sim: int = 0, seed: int = 0, *, script=None, log=None, state=None,
                 views=None):
        self.pr, self.P, self.rules, self.sc = pr, pr.P, pr.rules, pr.sc
        self.sim, self.seed = sim, seed
        self.script = None if script is None else list(script)
        self.log, self.views = log, views
        if self.script is None:
            self.s_ball, self.s_over, self.s_inn, self.s_match, self.s_player = (
                Stream(seed, sim, k) for k in range(5))
        self.view = dict(pr.view0)
        self.inn_team, self.toss, self.done, self.cur = None, None, [], None
        self.result, self.tie_before, self.main_done, self.followed_on = None, False, False, False
        self.so_k, self.so_first, self.so_target = 0, None, None
        self.match_legal = self.changeovers = 0
        self.avail = self.cum = self.suffix = None
        self.A_total, self.day, self.play_start_day = 0, 0, 0
        self.lengths, self.R, self.pending, self.revised_pre = None, [None, None], [], False
        self.lat_m = [0.0] * len(pr.lat_m)
        self.lat_i = [[0.0] * len(pr.lat_i) for _ in range(4)]
        self.bat_form, self.bowl_form = {}, {}
        self.coin_u = self.coin_forced = None
        self.stats = Counter()
        self.deliveries = 0
        self.state0 = state

    # --- script plumbing
    def _next(self, ev: str):
        if self.script is None:
            return None
        if not self.script:
            raise _Stop(ev)
        f = self.script.pop(0)
        if f.get("e") != ev:
            raise ScriptError(f"script has {f.get('e')!r} where the engine expects a {ev!r} event")
        return f

    @staticmethod
    def _need(F, key):
        if key not in F:
            raise ScriptError(f"scripted {F.get('e')} event needs {key!r}")
        return F[key]

    # --- driver
    def play(self) -> "Match":
        try:
            if self.state0 is not None:
                self._resume(self.state0)
            else:
                self._start_match()
            while self.result is None:
                if self.cur is None:
                    if self.so_k:
                        self._start_so_innings()
                    else:
                        self._start_innings()
                    continue
                over_done = self._delivery()
                c = self.cur
                if c.end is not None:
                    self._finish_innings()
                if self.result is None and not self.main_done and c.so == 0 and (over_done or c.end is not None):
                    self._over_event()
                    if c.end is not None and not c.closed:
                        self._finish_innings()
                if c.end is not None:
                    self.cur = None
        except _Stop as stop:
            if stop.args[0] != "ball":
                raise ScriptError(f"script ended before a {stop.args[0]!r} event; end scripts before a delivery")
        if self.result is not None and self.log is not None:
            self.log.append({"e": "end", **self.result})
        return self

    # --- match start
    def _draw_forms(self):
        sc, unc = self.sc, self.sc["draw_player_uncertainty"]
        for pid in self.pr.slots:
            sl = sc["player_form"].get(pid, {})
            b = [float(sl.get(k, 0.0)) for k in ("bat_runs_sd", "bat_wkt_sd", "bowl_runs_sd", "bowl_wkt_sd")]
            if self.script is None:
                u = self.s_player.uniforms(4)
                if unc:
                    z0, z1 = normal_pair(u[0], u[1])
                    z2, z3 = normal_pair(u[2], u[3])
                    b = [b[0] + z0, b[1] + z1, b[2] + z2, b[3] + z3]
            self.bat_form[pid], self.bowl_form[pid] = (b[0], b[1]), (b[2], b[3])

    def _prior_latents(self, um, skip_inn=None, skip_match=False):
        pr, pitch = self.pr, self.sc["pitch"]
        zm = []
        if um is not None:
            zm = [*normal_pair(um[M_LAT], um[M_LAT + 1]), *normal_pair(um[M_LAT + 2], um[M_LAT + 3])]
        for j, s in enumerate(pr.lat_m):
            if not skip_match:
                mu = float(pitch.get(s["pitch"], 0.0) or 0.0) * s["sd"]
                self.lat_m[j] = mu if (pitch["known"] or um is None) else mu + s["sd"] * zm[j]
        for k in range(4):
            if k == skip_inn:
                continue
            z = normal_pair(um[M_INN_LAT + 2 * k], um[M_INN_LAT + 2 * k + 1]) if um is not None else (0.0, 0.0)
            for j, s in enumerate(pr.lat_i):
                self.lat_i[k][j] = s["sd"] * z[j]

    def _set_clock(self, avail):
        sc, P = self.sc, self.P
        self.avail = [int(a) for a in avail]
        cum, c = [], 0
        for a in self.avail:
            c += a
            cum.append(c)
        self.cum, self.A_total = cum, c
        means = [P.day_availability_mean(sc, d + 1) for d in range(len(avail))]
        suffix, s = [0.0] * len(avail), 0.0
        for d in range(len(avail) - 1, -1, -1):
            suffix[d] = s
            s += means[d]
        self.suffix = suffix
        self.play_start_day = next((d for d, a in enumerate(self.avail) if a > 0), len(avail) - 1)
        self.day = 0

    def _start_match(self):
        sc, P, v, pr = self.sc, self.P, self.view, self.pr
        F = self._next("match")
        rec = {"e": "match"} if self.log is not None else None
        um = self.s_match.uniforms(64) if F is None else None
        self._draw_forms()
        toss = sc["toss"]
        if toss is not None:
            winner, bat = toss["winner"], toss["decision"] == "bat"
        elif F is not None:
            winner, bat = self._need(F, "toss_winner"), self._need(F, "toss_bat")
        else:
            winner = 0 if um[M_TOSS] < 0.5 else 1
            v["toss_winner"] = winner
            bat = um[M_TOSS_BAT] < P.toss_bat_prob(v)
        v["toss_winner"] = winner
        first = winner if bat else 1 - winner
        self.toss = {"winner": winner, "decision": "bat" if bat else "field"}
        self.inn_team = [first, 1 - first] * (2 if pr.fam == "TEST" else 1)
        self._prior_latents(um)
        if pr.fam == "TEST":
            days = self.rules["test_days"]
            if days > MAX_DAYS:
                raise ValueError(f"at most {MAX_DAYS} scheduled days")
            avail = self._need(F, "avail") if F is not None else \
                [P.day_availability(sc, d + 1, um[M_DAYS + d]) for d in range(days)]
            self._set_clock(avail)
        else:
            n = self.rules["max_balls"]
            self.lengths, self.R = [n, n], [pr.res(n, 0), None]
            self.pending = [dict(x) for x in (F.get("interruptions", []) if F is not None else
                                              P.interruption_schedule(sc, 0, um[M_RAIN:M_RAIN + 16]))]
        self.coin_u = um[M_COIN] if um is not None else None
        self.coin_forced = F.get("coin") if F is not None else None
        if rec is not None:
            rec.update(toss_winner=winner, toss_bat=bat, bat_first=first)
            if F is None:
                rec["latent"] = [*self.lat_m, *[x for row in self.lat_i for x in row]]
            if pr.fam == "TEST":
                rec["avail"] = list(self.avail)
            else:
                rec["interruptions"] = [dict(x) for x in self.pending]
            self.log.append(rec)
        while pr.limited and self.pending and self.pending[0]["start"] <= 0 and self.result is None:
            apply_interruption(self, self.pending.pop(0)["lost"])

    # --- innings
    def _agg(self, team: int) -> int:
        return sum(i.runs for i in self.done if i.team == team)

    def _new_innings(self, k: int, team: int) -> Innings:
        pr = self.pr
        c = Innings()
        c.number, c.team, c.opp = k, team, 1 - team
        c.order = pr.orders[team]
        c.unavail = set(pr.absent[team])
        c.to_come = [p for p in c.order if p not in c.unavail]
        for p in c.to_come[:2]:
            self._arrive(c, p)
        c.striker, c.nonstriker = c.to_come.pop(0), c.to_come.pop(0)
        c.reviews = [pr.rpi, pr.rpi]
        c.agg_bat, c.agg_opp = self._agg(team), self._agg(1 - team)
        if pr.limited:
            c.max_balls = self.lengths[k - 1]
            if k == 2:
                self.R[1] = pr.res(c.max_balls, 0)
                c.target = revised_target(self.done[0].runs, self.R[0], self.R[1], pr.G)
                c.timing = "pre_inn2" if self.revised_pre else "original"
        elif k == 4:
            c.target = c.agg_opp - c.agg_bat + 1
            c.timing = "original"
        c.windows = pr.windows(c.max_balls)
        return c

    @staticmethod
    def _arrive(c: Innings, p):
        c.n_arrived += 1
        c.bat[p] = [0, 0, c.n_arrived, None, 0, 0]

    def _innings_view(self, c: Innings):
        v, pr = self.view, self.pr
        v["innings"] = c.number
        v["super_over"], v["so_innings"] = c.so, c.so_inn
        v["bat_team"], v["bowl_team"] = c.team, c.opp
        v["bat_home_status"], v["bowl_home_status"] = pr.home_status[c.team], pr.home_status[c.opp]
        v["target_timing"] = c.timing
        v["followed_on"] = self.followed_on
        v["prev_innings"] = tuple((i.team, i.runs, i.wkts, i.legal, i.end) for i in self.done)
        v["umpire_offset"] = c.umpire_offset
        k = c.number if c.so == 0 else self._main_innings_of(c.team)
        v["latent"] = (*self.lat_m, *self.lat_i[k - 1])

    def _main_innings_of(self, team: int) -> int:
        return self.inn_team.index(team) + 1

    def _start_innings(self):
        pr, P, v = self.pr, self.P, self.view
        k = len(self.done) + 1
        F = self._next("innings")
        u = self.s_inn.uniforms(4) if F is None else None
        rec = {"e": "innings", "n": k, "so": 0} if self.log is not None else None
        if k > 1:
            self.changeovers += 1
        if pr.fam == "TEST" and self._used() >= self.A_total:
            if rec is not None:
                self.log.append(rec)
            self._set_result("draw")
            return
        team = self.inn_team[k - 1]
        if pr.fam == "TEST" and k == 3:
            a, b = self.inn_team[0], self.inn_team[1]
            lead = self.done[0].runs - self.done[1].runs
            thr = follow_on_threshold(self.rules["follow_on_lead"], len(self.avail) - self.play_start_day)
            if thr is not None and lead >= thr:
                c = self._new_innings(k, a)
                self.cur = c
                self._innings_view(c)
                self._refresh()
                fo = self._need(F, "follow_on") if F is not None else u[0] < P.follow_on_prob(v)
                if rec is not None:
                    rec["follow_on"] = bool(fo)
                if fo:
                    self.inn_team[2], self.inn_team[3] = b, a
                    self.followed_on = True
                    team = b
        c = self._new_innings(k, team)
        self.cur = c
        c.umpire_offset = self._need(F, "umpire_offset") if F is not None else (0 if u[1] < 0.5 else 1)
        self._innings_view(c)
        self._refresh()
        self._choose_bowler(None if u is None else u[2], F, rec)
        if rec is not None:
            rec.update(team=team, umpire_offset=c.umpire_offset)
            self.log.append(rec)

    _SEL_KEYS = ("striker", "bowler", "striker_form", "bowler_form", "latent", "dtype", "striker_pos",
                 "striker_runs", "striker_balls", "striker_arrival", "bowler_balls", "bowler_runs", "bowler_wkts",
                 "bowler_overs", "bowler_spell", "bowler_part_timer")

    def _expected_runs(self, striker, bowler) -> float:
        """Super-over selection: expected runs per legal ball for `striker` (None = average batter) against
        `bowler` (None = average bowler) in the super-over context, zero latents and zero form."""
        v = self.view
        keep = {k: v[k] for k in self._SEL_KEYS}
        v["striker"], v["bowler"] = striker, bowler
        v["striker_pos"] = None if striker is None else self.pr.pos[striker]
        v["striker_runs"], v["striker_balls"], v["striker_arrival"] = 0, 0, None if striker is None else 1
        v["striker_form"], v["bowler_form"] = (0.0, 0.0), (None if bowler is None else (0.0, 0.0))
        v["bowler_balls"], v["bowler_runs"], v["bowler_wkts"], v["bowler_overs"], v["bowler_spell"] = \
            (None,) * 5 if bowler is None else (0, 0, 0, 0, 0)
        v["bowler_part_timer"] = False
        v["latent"] = (0.0,) * (len(self.pr.lat_m) + len(self.pr.lat_i))
        v["dtype"] = "legal"
        p = softmax(self.P.outcome_eta(v))
        v.update(keep)
        return sum(pk * r for pk, r in zip(p, NOMINAL_RUNS))

    def _start_so_innings(self):
        pr = self.pr
        F = self._next("innings")
        u = self.s_inn.uniforms(4) if F is None else None
        first = self.so_target is None
        team = self.so_first if first else 1 - self.so_first
        c = Innings()
        c.number, c.so, c.so_inn, c.team, c.opp = 0, self.so_k, 1 if first else 2, team, 1 - team
        c.max_balls, c.max_wkts = 6, 2
        c.target, c.timing = (None, None) if first else (self.so_target, "original")
        c.reviews = [1, 1] if pr.rules["drs_enabled"] else [0, 0]
        c.agg_bat, c.agg_opp = self._agg(team), self._agg(1 - team)
        fo = pr.rules["fielders_outside"]
        c.windows = ([(0, 6, fo[-1][2])] if fo else [], [])
        c.umpire_offset = self._need(F, "umpire_offset") if F is not None else (0 if u[1] < 0.5 else 1)
        c.order = [p for p in pr.orders[team] if p not in pr.absent[team]]
        c.striker, c.nonstriker = c.order[0], c.order[1]
        c.bat = {c.striker: [0, 0, 1, None, 0, 0], c.nonstriker: [0, 0, 2, None, 0, 0]}
        self.cur = c
        self._innings_view(c)
        self._refresh()
        er = [(-self._expected_runs(p, None), i, p) for i, p in enumerate(c.order)]
        top = [p for _, _, p in sorted(er)[:3]]
        c.order, c.bat, c.n_arrived = top, {}, 0
        for p in top[:2]:
            self._arrive(c, p)
        c.striker, c.nonstriker, c.to_come = top[0], top[1], top[2:]
        self._refresh()
        cands = [p for p in pr.xi[c.opp] if p != pr.keeper[c.opp]]
        eb = [(self._expected_runs(None, p), i, p) for i, p in enumerate(cands)]
        c.bowler = sorted(eb)[0][2]
        c.bowl[c.bowler] = [0, 0, 0, 0]
        if self.log is not None:
            self.log.append({"e": "innings", "n": 0, "so": c.so, "team": team, "umpire_offset": c.umpire_offset,
                             "batters": top, "bowler": c.bowler})

    # --- bowler choice
    def _cand(self, b, n_overs) -> dict:
        c, pr = self.cur, self.pr
        s = c.bowl.get(b, (0, 0, 0, 0))
        overs = {x: y[3] for x, y in c.bowl.items()}
        return {"id": b, "option": pr.opts[c.opp].index(b) if b in pr.opts[c.opp] else len(pr.opts[c.opp]),
                "overs": s[3], "balls": s[0], "runs": s[1], "wkts": s[2], "spell": spell_overs(c.over_bowlers, b),
                "quota_left": quota_left(overs, b, n_overs),
                "overs_left": None if n_overs is None else n_overs - len(c.over_bowlers),
                "part_timer": b in pr.part_timers[c.opp], "opened": b in c.over_bowlers[:2]}

    def _choose_bowler(self, u, F, rec):
        c, pr, P, v = self.cur, self.pr, self.P, self.view
        opts = pr.opts[c.opp]
        n_overs = c.max_balls // 6 if pr.limited else None
        overs = {x: y[3] for x, y in c.bowl.items()}
        elig = eligible_bowlers(opts, overs, c.last_bowler, n_overs, len(c.over_bowlers))
        if not elig:
            self.stats["bowler_fallback"] += 1
            elig = [b for b in opts if b != c.last_bowler and (quota_left(overs, b, n_overs) or 0) > 0] or \
                [b for b in opts if b != c.last_bowler] or list(opts)
        if F is not None:
            b = self._need(F, "bowler")
            if b not in elig:
                raise ScriptError(f"forced bowler {b!r} is not eligible; eligible: {elig}")
        else:
            ut = [P.bowler_utility(v, self._cand(x, n_overs)) for x in elig]
            b = elig[cat_eta(u, ut)]
        c.bowler = b
        c.spell = spell_overs(c.over_bowlers, b)
        c.bowl.setdefault(b, [0, 0, 0, 0])
        if rec is not None:
            rec["bowler"], rec["elig"] = b, elig

    # --- view
    def _used(self) -> int:
        return self.match_legal + 12 * self.changeovers

    def _refresh(self):
        c, v, pr = self.cur, self.view, self.pr
        st, ns, bw = c.striker, c.nonstriker, c.bowler
        bs, bn = c.bat[st], c.bat[ns]
        L = c.legal
        ov = len(c.over_bowlers)
        v["legal_balls"], v["ball_in_over"], v["over"], v["max_balls"] = L, c.ball_in_over, ov, c.max_balls
        v["balls_remaining"] = None if c.max_balls is None else c.max_balls - L
        v["runs"], v["wkts"], v["unavailable"] = c.runs, c.wkts, c.wkts + len(c.unavail)
        v["target"] = c.target
        v["runs_required"] = None if c.target is None else c.target - c.runs
        v["striker"], v["nonstriker"], v["bowler"] = st, ns, bw
        v["striker_runs"], v["striker_balls"], v["striker_arrival"] = bs[0], bs[1], bs[2]
        v["nonstriker_runs"], v["nonstriker_balls"], v["nonstriker_arrival"] = bn[0], bn[1], bn[2]
        v["striker_pos"], v["nonstriker_pos"] = pr.pos[st], pr.pos[ns]
        if bw is None:
            v["bowler_balls"] = v["bowler_runs"] = v["bowler_wkts"] = v["bowler_overs"] = None
            v["bowler_spell"] = v["bowler_form"] = None
            v["bowler_part_timer"] = False
        else:
            bb = c.bowl[bw]
            v["bowler_balls"], v["bowler_runs"], v["bowler_wkts"], v["bowler_overs"] = bb[0], bb[1], bb[2], bb[3]
            v["bowler_spell"], v["bowler_form"] = c.spell, self.bowl_form[bw]
            v["bowler_part_timer"] = bw in pr.part_timers[c.opp]
        v["partnership_runs"], v["partnership_balls"] = c.p_runs, c.p_balls
        v["free_hit"] = c.free_hit
        fr = None
        for lo, hi, m in c.windows[0]:
            if lo <= L < hi:
                fr = m
                break
        pw = "none"
        for lo, hi, name in c.windows[1]:
            if lo <= L < hi:
                pw = name
                break
        v["field_restr"], v["pp_window"] = fr, pw
        v["reviews_bat"], v["reviews_bowl"] = c.reviews
        v["bat_fail_reviews"], v["bowl_fail_reviews"] = c.fail_reviews
        v["ball_age_overs"], v["second_new_ball"], v["innings_overs"] = c.ball_age, c.second_new_ball, ov
        v["match_legal_balls"] = self.match_legal
        if pr.fam == "TEST" and self.cum is not None:
            used = self._used()
            d, last = self.day, len(self.cum) - 1
            while d < last and used >= self.cum[d]:
                d += 1
            self.day = d
            prev = self.cum[d - 1] if d else 0
            v["clock_used"], v["est_day"] = used, d + 1
            v["overs_into_day"] = max(0, used - prev) // 6
            v["exp_overs_left"] = (self.cum[d] + self.suffix[d] - used) / 6
        v["lead"] = c.agg_bat + c.runs - c.agg_opp
        um = v["umpires"]
        v["bowl_end_umpire"] = um[(ov + c.umpire_offset) % 2] if um and c.umpire_offset is not None else None
        v["striker_form"], v["nonstriker_form"] = self.bat_form[st], self.bat_form[ns]
        v["to_come"] = tuple(c.to_come)
        v["last_over_runs"], v["last_over_wkt"] = c.last_over_runs, c.last_over_wkt
        v["dtype"] = None

    # --- one delivery (plan 9.2)
    def _delivery(self) -> bool:
        c, P, v, r, pr = self.cur, self.P, self.view, self.rules, self.pr
        F = self._next("ball")
        u = self.s_ball.uniforms(12) if F is None else None
        rec = {"e": "ball", "n": c.number, "so": c.so, "lb": c.legal, "s": c.striker, "ns": c.nonstriker,
               "b": c.bowler} if self.log is not None else None
        self.deliveries += 1
        self._refresh()
        st, ns, bw = c.striker, c.nonstriker, c.bowler
        fh = c.free_hit
        drs = r["drs_enabled"] and not fh
        retain = r["umpires_call_retains"]
        st_ = self.stats
        # 2. dtype
        d = _DT[self._need(F, "dtype")] if F is not None else cat_eta(u[0], P.dtype_eta(v))
        if rec is not None:
            rec["dtype"] = DTYPES[d]
        bat = byes = wides = pen = 0
        cls, kind, victim, boundary, fh_new = -1, -1, None, False, False
        ro_runs = 0
        if d == WIDE:                                           # 3. wide
            v["dtype"] = "wide"
            w = list(P.wide_wkt(v))
            if fh:
                w[1] = 0.0
            ww = _WW[self._need(F, "wide_wkt")] if F is not None else cat_w(u[3], w)
            if F is not None and w[ww] <= 0.0:
                raise ScriptError(f"wide wicket {WIDE_WKTS[ww]!r} is impossible here")
            k = self._need(F, "runs") if F is not None else 1 + cat_w(u[2], P.wide_runs(v, ww))
            wides, boundary = k, k == 5
            if rec is not None:
                rec["wide_wkt"], rec["runs"] = WIDE_WKTS[ww], k
            if ww == 1:
                victim, kind = st, STUMPED
            elif ww == 2:
                victim, kind, ro_runs = True, RO, k - 1
            elif drs and c.reviews[1] > 0:
                self._spec(F, u, rec, 9, retain)
        else:
            v["dtype"] = "noball" if d == NOBALL else "legal"
            eta = list(P.outcome_eta(v))
            if d == NOBALL or fh:
                eta[OUT] += MASK_OFFSET
            cls = self._need(F, "cls") if F is not None else cat_eta(u[1], eta)
            if F is not None and cls == OUT and (d == NOBALL or fh):
                raise ScriptError("a bowler-credited out is masked on no-balls and free hits")
            if rec is not None:
                rec["cls"] = cls
            if d == NOBALL:                                     # 4. no-ball
                pen = r["noball_runs"]
                if r["free_hit"] == "all_noballs":
                    fh_new = True
                elif r["free_hit"] == "front_foot":
                    fh_new = self._need(F, "free_hit") if F is not None else u[3] < r["p_free_hit_given_nb"]
                    if rec is not None:
                        rec["free_hit"] = bool(fh_new)
            elif cls == OUT:                                    # 5. legal ball, on-field out
                kind = _KI[self._need(F, "kind")] if F is not None else cat_eta(u[3], P.wk_eta(v))
                if rec is not None:
                    rec["kind"] = KIND_ALL[kind]
                if drs and kind in (CAUGHT, LBW) and c.reviews[0] > 0:
                    q, po, pu = P.drs_bat(v, kind)
                    rv = self._need(F, "bat_review") if F is not None else u[6] < q
                    if rec is not None:
                        rec["bat_review"] = bool(rv)
                    if rv:
                        st_["bat_reviews"] += 1
                        ov = self._need(F, "overturned") if F is not None else u[7] < min(1.0, po * pr.acc)
                        if rec is not None:
                            rec["overturned"] = bool(ov)
                        if ov:
                            st_["bat_overturned"] += 1
                            cls, kind = DOT, -1
                        else:
                            uc = False
                            if kind == LBW:
                                uc = self._need(F, "ucall") if F is not None else u[8] < min(1.0, pu * pr.ucm)
                                if rec is not None:
                                    rec["ucall"] = bool(uc)
                            st_["bat_ucall"] += uc
                            if not (uc and retain):
                                c.reviews[0] -= 1
                            if not uc:
                                c.fail_reviews[0] += 1
                if cls == OUT:
                    victim = st
            elif not fh:                                        # 5. legal non-wicket: fielding reviews
                spec_ok = drs and c.reviews[1] > 0
                if cls in (DOT, BYES):
                    lam, lbw_share, _, _ = P.drs_field(v, cls)
                    ms = self._need(F, "missed") if F is not None else u[9] < min(1.0, lam * pr.acc)
                    if rec is not None:
                        rec["missed"] = bool(ms)
                    if ms and drs and c.reviews[1] > 0:
                        lb = self._need(F, "missed_lbw") if F is not None else u[10] < lbw_share
                        if rec is not None:
                            rec["missed_lbw"] = bool(lb)
                        st_["field_success"] += 1
                        cls, kind, victim, spec_ok = OUT, (LBW if lb else CAUGHT), st, False
                    elif ms:
                        st_["missed_standing"] += 1
                if spec_ok and cls != RUN_OUT:
                    self._spec(F, u, rec, cls, retain)
            # 6. exact runs
            if cls in (ONE, TWO, THREE):
                bat = cls
            elif cls == FOUR or cls == SIX:
                p5, p7 = P.runs5_7(v)
                bat = self._need(F, "runs") if F is not None else \
                    ((5 if u[2] < p5 else 4) if cls == FOUR else (7 if u[2] < p7 else 6))
                boundary = True
            elif cls == BYES:
                byes = self._need(F, "runs") if F is not None else 1 + cat_w(u[2], P.bye_runs(v))
                boundary = byes >= 4
            elif cls == RUN_OUT:
                ro_runs = bat = self._need(F, "runs") if F is not None else cat_w(u[2], P.runout_runs(v))
                victim, kind = True, RO
            if rec is not None and cls in (FOUR, SIX, BYES, RUN_OUT):
                rec["runs"] = bat + byes
        # 7. chase completion
        won = False
        if c.target is not None and c.runs + bat + byes + wides + pen >= c.target:
            won = True
            need = c.target - c.runs
            if not boundary:
                if d == WIDE:
                    wides = 1 + min(wides - 1, max(need - 1, 0))
                else:
                    allow = max(need - pen, 0)
                    bat, byes = min(bat, allow), min(byes, allow)
            victim, kind = None, -1
        total = bat + byes + wides + pen
        ran = bat + byes + (wides - 1 if wides else 0)
        # 10. counters (the pre-ball striker and bowler)
        sb = c.bat[st]
        if d != WIDE:
            sb[1] += 1
            sb[0] += bat
            if boundary and bat in (4, 5):
                sb[4] += 1
            elif boundary and bat in (6, 7):
                sb[5] += 1
            c.p_balls += 1
        bb = c.bowl[bw]
        bb[1] += bat + wides + pen
        c.runs += total
        c.extras += byes + wides + pen
        c.p_runs += total
        c.over_runs += total
        if d == LEGAL:
            c.legal += 1
            c.ball_in_over += 1
            bb[0] += 1
            if c.so == 0:
                self.match_legal += 1
        # 8. wicket
        all_out = False
        if victim is not None:
            if kind == RO:
                so = self._need(F, "ro_striker") if F is not None else u[4] < P.runout_who(v, ro_runs)
                if rec is not None:
                    rec["ro_striker"] = bool(so)
                victim = st if so else ns
            c.wkts += 1
            c.wkt_this_over = True
            c.bat[victim][3] = KIND_ALL[kind]
            c.out.append(victim)
            if kind != RO:
                bb[2] += 1
            st_["kind_" + KIND_ALL[kind] + ("_wide" if d == WIDE else "")] += 1
            c.p_runs = c.p_balls = 0
            nb = c.to_come[0] if c.to_come else None
            if nb is None or c.wkts >= c.max_wkts:
                all_out = True
            else:
                c.to_come.pop(0)
                self._arrive(c, nb)
                if kind == RO:
                    surv = ns if victim == st else st
                    p = P.runout_new_on_strike(v, 0 if victim == st else 1, min(ro_runs, 2))
                    nos = self._need(F, "ro_new_on_strike") if F is not None else u[5] < p
                    if rec is not None:
                        rec["ro_new_on_strike"] = bool(nos)
                    c.striker, c.nonstriker = (nb, surv) if nos else (surv, nb)
                elif kind == CAUGHT and r["caught_crossing_counts"]:
                    cr = self._need(F, "crossed") if F is not None else u[5] < P.p_crossed(v)
                    if rec is not None:
                        rec["crossed"] = bool(cr)
                    c.striker, c.nonstriker = (ns, nb) if cr else (nb, ns)
                else:
                    c.striker = nb
        elif ran % 2 == 1:                                      # 9. no wicket: swap on odd runs run
            c.striker, c.nonstriker = ns, st
        # 11. end checks
        if won:
            c.end = "target"
        elif all_out:
            c.end = "all_out"
        elif c.max_balls is not None and c.legal >= c.max_balls:
            c.end = "balls"
        elif pr.fam == "TEST" and c.so == 0 and self._used() >= self.A_total:
            c.end = "clock"
        # 12. over end
        over_done = d == LEGAL and c.ball_in_over == 6
        if over_done:
            c.over_scores.append(c.runs)
            c.over_bowlers.append(bw)
            bb[3] += 1
            c.last_over_runs, c.last_over_wkt = c.over_runs, c.wkt_this_over
            c.over_runs, c.wkt_this_over = 0, False
            c.ball_age += 1
            if r["review_topup_after_80"] and len(c.over_bowlers) == 80 and pr.rpi:
                c.reviews = [pr.rpi, pr.rpi]
            if c.end is None:
                c.striker, c.nonstriker = c.nonstriker, c.striker
                c.ball_in_over = 0
                c.last_bowler, c.bowler = bw, None
        # 13. free hit for the next delivery
        c.free_hit = False if d == LEGAL else (fh or fh_new)
        if self.views is not None and d != WIDE and cls >= 0:
            snap = {k: x for k, x in v.items() if k not in ("prep", "rules", "latent")}
            snap["dtype"] = DTYPES[d]
            self.views.append({"inn": c.number, "so": c.so, "view": snap, "cls": cls,
                               "latent": list(v["latent"])})
        if rec is not None:
            rec["post"] = [c.runs, c.wkts, c.legal, c.striker, c.nonstriker, c.free_hit]
            self.log.append(rec)
        return over_done

    def _spec(self, F, u, rec, cls: int, retain: bool):
        _, _, rs, share = self.P.drs_field(self.view, cls)
        c = self.cur
        if F is not None:
            sp = self._need(F, "spec")
            uc = self._need(F, "spec_ucall") if sp else False
        else:
            sp, uc = u[11] < rs, u[11] < rs * share
        if rec is not None:
            rec["spec"] = bool(sp)
            if sp:
                rec["spec_ucall"] = bool(uc)
        if sp:
            self.stats["field_spec"] += 1
            self.stats["field_spec_ucall"] += uc
            if not (uc and retain):
                c.reviews[1] -= 1
            if not uc:
                c.fail_reviews[1] += 1

    # --- over end (plan 9.2 step 12)
    def _over_event(self):
        c, P, v, pr = self.cur, self.P, self.view, self.pr
        F = self._next("over")
        u = self.s_over.uniforms(4) if F is None else None
        rec = {"e": "over", "n": c.number, "ov": len(c.over_bowlers)} if self.log is not None else None
        if pr.limited:
            applied = []
            while self.pending and self.pending[0]["start"] <= self.match_legal and self.result is None:
                it = self.pending.pop(0)
                apply_interruption(self, it["lost"])
                applied.append(it)
            if rec is not None and applied:
                rec["intr"] = applied
                rec["target"], rec["lengths"] = c.target if c.number == 2 else None, list(self.lengths)
        if self.result is None and c.end is None:
            self._refresh()
            if pr.fam == "TEST" and (c.number < 3 or (c.number == 3 and v["lead"] > 0)):
                dec = self._need(F, "declare") if F is not None else u[1] < P.declare_hazard(v)
                if rec is not None:
                    rec["declare"] = bool(dec)
                if dec:
                    c.end = "declared"
            if c.end is None:
                self._choose_bowler(None if u is None else u[2], F, rec)
                nb = self.rules["new_ball_after_overs"]
                if pr.fam == "TEST" and nb and c.ball_age >= nb:
                    self._refresh()
                    take = self._need(F, "new_ball") if F is not None else u[3] < P.new_ball_prob(v)
                    if rec is not None:
                        rec["new_ball"] = bool(take)
                    if take:
                        c.ball_age, c.second_new_ball = 0, True
        if rec is not None:
            self.log.append(rec)

    # --- innings end and results
    def _set_result(self, result: str, winner=None, method=None, margin=None, margin_kind=None):
        self.result = {"result": result, "winner": winner, "method": method, "margin": margin,
                       "margin_kind": margin_kind, "tie_before": self.tie_before, "super_overs": self.so_k}

    def _finish_innings(self):
        c, pr = self.cur, self.pr
        c.closed = True
        if c.legal % 6 or (c.over_scores[-1] if c.over_scores else 0) != c.runs:
            c.over_scores.append(c.runs)
        if c.so:
            return self._finish_so(c)
        self.done.append(c)
        if self.result is not None:
            return
        k = c.number
        if pr.limited:
            if k == 1:
                return
            self.main_done = True
            method = "normal" if c.timing == "original" else "dls"
            if c.end == "target":
                return self._set_result("win", c.team, method, 10 - c.wkts, "wickets")
            par = c.target - 1
            if c.end == "cut":
                if c.runs > par:
                    return self._set_result("win", c.team, "par", 10 - c.wkts, "wickets")
                if c.runs < par:
                    return self._set_result("win", c.opp, "par", par - c.runs, "runs")
                self.tie_before = True
                return self._set_result("tie", None, "par")
            if c.runs < par:
                return self._set_result("win", c.opp, method, par - c.runs, "runs")
            self.tie_before = True
            return self._tie_break()
        if c.end == "clock":
            self.main_done = True
            return self._set_result("draw")
        if k == 3:
            agg_x, agg_y = self._agg(c.team), self._agg(c.opp)
            if agg_x < agg_y:
                self.main_done = True
                return self._set_result("win", c.opp, "normal", agg_y - agg_x, "innings")
        elif k == 4:
            self.main_done = True
            if c.end == "target":
                return self._set_result("win", c.team, "normal", 10 - c.wkts, "wickets")
            if c.runs == c.target - 1:
                self.tie_before = True
                return self._set_result("tie", None, "normal")
            return self._set_result("win", c.opp, "normal", c.target - 1 - c.runs, "runs")

    def _coin(self) -> int:
        if self.script is not None:
            if self.coin_forced is None:
                raise ScriptError("the tie-break coin needs 'coin' in the match or resume event")
            return self.coin_forced
        return 0 if self.coin_u < 0.5 else 1

    def _tie_break(self):
        tb = self.rules["tie_break"]
        if tb == "none":
            return self._set_result("tie", None, "normal")
        if tb == "bowl_out":
            return self._set_result("win", self._coin(), "coin")
        self.so_k, self.so_first, self.so_target = 1, self.inn_team[1], None

    def _finish_so(self, c: Innings):
        if c.so_inn == 1:
            self.so_target = c.runs + 1
            return
        self.so_target = None
        if c.end == "target":
            return self._set_result("win", c.team, "super_over")
        if c.runs < c.target - 1:
            return self._set_result("win", c.opp, "super_over")
        if self.so_k < MAX_SUPER_OVERS:
            self.so_k += 1
            self.so_first = c.team
            return
        self._set_result("win", self._coin(), "coin")

    # --- in-play resume
    def _resume(self, st: dict):
        pr, sc, P = self.pr, self.sc, self.P
        errs = check_state(st, pr)
        if errs:
            raise ValueError("invalid in-play state: " + "; ".join(errs))
        F = self._next("resume")
        rec = {"e": "resume"} if self.log is not None else None
        um = self.s_match.uniforms(64) if F is None else None
        self._draw_forms()
        self.toss = copy.deepcopy(st.get("toss"))
        self.inn_team = list(st["innings_team"])
        self.followed_on = bool(st.get("followed_on", False))
        for i, d in enumerate(st["done"]):
            x = Innings()
            x.number, x.team, x.opp = i + 1, d["team"], 1 - d["team"]
            x.runs, x.wkts, x.legal, x.max_balls = d["runs"], d["wkts"], d["legal_balls"], d["max_balls"]
            x.target, x.end, x.closed = d["target"], d["end"], True
            self.done.append(x)
        c = _innings_from_state(st["cur"], pr, self)
        self.cur = c
        self.match_legal = sum(x.legal for x in self.done) + c.legal
        if pr.fam == "TEST":
            ck = st["clock"]
            self.changeovers = ck["changeovers"]
            avail = list(ck["avail"])
            for dd, a in enumerate(avail):
                if a is None:
                    avail[dd] = P.day_availability(sc, dd + 1, um[M_DAYS + dd]) if um is not None else \
                        6 * self.rules["test_overs_per_day"]
            self._set_clock(avail)
        else:
            n = self.rules["max_balls"]
            lens = st.get("lengths") or [None, None]
            self.lengths = [lens[0] if lens[0] is not None else (self.done[0].max_balls if self.done else c.max_balls),
                            lens[1] if lens[1] is not None else c.max_balls]
            rs = st.get("resources") or [None, None]
            self.R = [rs[0] if rs[0] is not None else pr.res(self.lengths[0], 0),
                      rs[1] if rs[1] is not None else (pr.res(c.max_balls, 0) if c.number == 2 else None)]
            if c.number == 2 and c.target is None:
                c.target = revised_target(self.done[0].runs, self.R[0], self.R[1], pr.G)
            self.revised_pre = bool(st.get("revised_pre", self.lengths[1] != n))
            pend = st.get("pending_interruptions")
            if pend is None:
                pend = [] if um is None else P.interruption_schedule(sc, self.match_legal, um[M_RAIN:M_RAIN + 16])
            self.pending = [dict(x) for x in pend]
        c.agg_bat, c.agg_opp = self._agg(c.team), self._agg(c.opp)
        if c.number == 4 and c.target is None:
            c.target = c.agg_opp - c.agg_bat + 1
        self._prior_latents(um)
        self._innings_view(c)
        recs = st.get("balls")
        if recs and self.script is None:
            self._posterior_latents(recs, um)
            self._innings_view(c)
        self.coin_u = um[M_COIN] if um is not None else None
        self.coin_forced = F.get("coin") if F is not None else None
        ui = self.s_inn.uniforms(4) if F is None else None
        if c.umpire_offset is None:
            c.umpire_offset = self._need(F, "umpire_offset") if F is not None else (0 if ui[1] < 0.5 else 1)
            if rec is not None:
                rec["umpire_offset"] = c.umpire_offset
        self._innings_view(c)
        self._refresh()
        if c.bowler is None:
            self._choose_bowler(None if ui is None else ui[2], F, rec)
        if rec is not None:
            if F is None:
                rec["latent"] = [*self.lat_m, *[x for row in self.lat_i for x in row]]
            self.log.append(rec)

    def _posterior_latents(self, recs, um):
        """Plan 9.3: Laplace posterior of the match and current-innings latents, drawn per sim."""
        pr, c, pitch = self.pr, self.cur, self.sc["pitch"]
        known = bool(pitch["known"])
        nm, ni = len(pr.lat_m), len(pr.lat_i)
        free = ([] if known else list(range(nm))) + [nm + j for j in range(ni)]
        mu_full = [float(pitch.get(s["pitch"], 0.0) or 0.0) * s["sd"] for s in pr.lat_m] + [0.0] * ni
        sd_full = [s["sd"] for s in pr.lat_m] + [s["sd"] for s in pr.lat_i]
        fixed = [mu_full[j] if known and j < nm else 0.0 for j in range(nm + ni)]
        mode, chol = latent_posterior(self.P, self.view, recs, c.number, free, [mu_full[j] for j in free],
                                      [sd_full[j] for j in free], fixed, nm)
        zm = [*normal_pair(um[M_LAT], um[M_LAT + 1]), *normal_pair(um[M_LAT + 2], um[M_LAT + 3])]
        k = c.number - 1
        zi = normal_pair(um[M_INN_LAT + 2 * k], um[M_INN_LAT + 2 * k + 1])
        x = _back_solve_t(chol, [zm[j] if j < nm else zi[j - nm] for j in free])
        for t, j in enumerate(free):
            if j < nm:
                self.lat_m[j] = mode[t] + x[t]
            else:
                self.lat_i[k][j - nm] = mode[t] + x[t]
        self.stats["latent_updates"] += 1
        self.posterior = {"mode": mode, "free": free, "chol": chol}

    # --- state
    def to_state(self) -> dict:
        """Canonical in-play state (plan 9.3) at the current pre-ball point."""
        c, pr = self.cur, self.pr
        if c is None or c.so:
            raise ValueError("the canonical state exists only inside a main innings")
        order = pr.orders[c.team]
        nxt = order.index(c.to_come[0]) if c.to_come else len(order)
        cur = {"number": c.number, "team": c.team, "runs": c.runs, "wkts": c.wkts, "legal_balls": c.legal,
               "max_balls": c.max_balls, "target": c.target, "target_timing": c.timing,
               "striker": c.striker, "nonstriker": c.nonstriker,
               "batters": {p: {"runs": b[0], "balls": b[1], "arrival": b[2], "out": b[3], "fours": b[4],
                               "sixes": b[5]} for p, b in c.bat.items()},
               "unavailable": [p for p in order if p in c.unavail], "next": nxt,
               "bowlers": {p: {"balls": b[0], "runs": b[1], "wkts": b[2], "overs": b[3]} for p, b in c.bowl.items()},
               "over_bowlers": list(c.over_bowlers), "bowler": c.bowler, "last_bowler": c.last_bowler,
               "ball_in_over": c.ball_in_over, "free_hit": c.free_hit, "reviews": list(c.reviews),
               "fail_reviews": list(c.fail_reviews), "umpire_offset": c.umpire_offset,
               "partnership": [c.p_runs, c.p_balls], "ball_age_overs": c.ball_age,
               "second_new_ball": c.second_new_ball, "last_over_runs": c.last_over_runs,
               "last_over_wkt": c.last_over_wkt, "over_runs": c.over_runs, "wkt_this_over": c.wkt_this_over,
               "over_scores": list(c.over_scores), "extras": c.extras}
        st = {"innings_team": list(self.inn_team), "toss": copy.deepcopy(self.toss), "followed_on": self.followed_on,
              "done": [{"team": x.team, "runs": x.runs, "wkts": x.wkts, "legal_balls": x.legal,
                        "max_balls": x.max_balls, "target": x.target, "end": x.end} for x in self.done],
              "cur": cur}
        if pr.limited:
            st.update(lengths=list(self.lengths), resources=list(self.R), revised_pre=self.revised_pre,
                      pending_interruptions=[dict(x) for x in self.pending])
        else:
            st["clock"] = {"used": self._used(), "changeovers": self.changeovers, "avail": list(self.avail)}
        return st

    def record(self) -> dict:
        """Per-simulation summary consumed by Acc (integers only, so merges are exact)."""
        res = self.result
        code = 2 if res["result"] == "tie" else 3 if res["result"] == "draw" else 4 \
            if res["result"] == "no_result" else res["winner"]
        players = {}
        for c in self.done:
            for p, b in c.bat.items():
                s = players.setdefault(p, [0] * 9)
                s[0] += b[0]
                s[1] += b[1]
                s[2] += 1
                s[3] += b[3] is not None
                s[4] = max(s[4], b[0])
            for p, b in c.bowl.items():
                s = players.setdefault(p, [0] * 9)
                s[5] += b[0]
                s[6] += b[1]
                s[7] += b[2]
        return {"sim": self.sim, "code": code, "result": res,
                "innings": [(c.number, c.team, c.runs, c.wkts, c.legal, c.end) for c in self.done],
                "overs": [list(c.over_scores) for c in self.done], "players": players, "stats": dict(self.stats),
                "deliveries": self.deliveries}


def _innings_from_state(cs: dict, pr: Prepared, m: Match) -> Innings:
    c = Innings()
    c.number, c.team, c.opp = cs["number"], cs["team"], 1 - cs["team"]
    c.order = pr.orders[c.team]
    c.runs, c.wkts, c.legal, c.max_balls = cs["runs"], cs["wkts"], cs["legal_balls"], cs["max_balls"]
    c.target, c.timing = cs["target"], cs.get("target_timing") or ("original" if cs["target"] is not None else None)
    c.striker, c.nonstriker = cs["striker"], cs["nonstriker"]
    c.unavail = set(cs["unavailable"]) | pr.absent[c.team]
    for p, b in sorted(cs["batters"].items(), key=lambda kv: kv[1]["arrival"]):
        c.bat[p] = [b["runs"], b["balls"], b["arrival"], b.get("out"), b.get("fours", 0), b.get("sixes", 0)]
        if b.get("out"):
            c.out.append(p)
    c.n_arrived = max((b[2] for b in c.bat.values()), default=0)
    c.to_come = [p for p in c.order if p not in c.bat and p not in c.unavail]
    c.over_bowlers = list(cs["over_bowlers"])
    for p, b in cs["bowlers"].items():
        c.bowl[p] = [b["balls"], b["runs"], b["wkts"], c.over_bowlers.count(p)]
    c.bowler, c.last_bowler, c.ball_in_over = cs["bowler"], cs["last_bowler"], cs["ball_in_over"]
    if c.bowler is not None:
        c.bowl.setdefault(c.bowler, [0, 0, 0, 0])
        c.spell = spell_overs(c.over_bowlers, c.bowler)
    c.free_hit = bool(cs["free_hit"])
    c.reviews, c.fail_reviews = list(cs["reviews"]), list(cs["fail_reviews"])
    c.umpire_offset = cs["umpire_offset"]
    c.p_runs, c.p_balls = cs["partnership"]
    c.ball_age, c.second_new_ball = cs["ball_age_overs"], bool(cs["second_new_ball"])
    c.last_over_runs, c.last_over_wkt = cs["last_over_runs"], bool(cs["last_over_wkt"])
    c.over_runs, c.wkt_this_over = cs["over_runs"], bool(cs["wkt_this_over"])
    c.over_scores = list(cs["over_scores"])
    c.extras = cs.get("extras", 0)
    c.windows = pr.windows(c.max_balls)
    return c


# ---------------------------------------------------------------- interruptions (plan 7.6)

def apply_interruption(m: Match, lost: int) -> None:
    """Apply `lost` legal balls per innings at the current over end (or before play).

    Before or during innings 1: both innings become old - lost (innings 1 ends if it has passed that),
    R1 loses P(u_before, w) - P(u_after, w). At the innings break: innings 2 only. During innings 2:
    innings 2 only, R2 loses the same difference, the target is revised; innings 2 is cut short when the
    new length is not above the balls faced (a par result) and the match is a no result when innings 2
    cannot reach min_balls_for_result."""
    pr, c = m.pr, m.cur
    minb = m.rules["min_balls_for_result"] or 0
    if c is None or (c.number == 1 and c.end is None):
        legal, w = (0, 0) if c is None else (c.legal, c.wkts)
        old = m.lengths[0]
        new = max(old - lost, 0)
        m.R[0] -= pr.res(old - legal, w) - pr.res(max(new - legal, 0), w)
        m.lengths = [max(new, legal), new]
        m.revised_pre = True
        if c is not None:
            c.max_balls = m.lengths[0]
            c.windows = pr.windows(c.max_balls)
        if new < minb:
            if c is not None:
                c.end = "no_result"
            m._set_result("no_result")
        elif c is not None and legal >= new:
            c.end = "cut"
    elif c.number == 1:
        m.lengths[1] = max(m.lengths[1] - lost, 0)
        m.revised_pre = True
        if m.lengths[1] < minb:
            m._set_result("no_result")
    else:
        old = c.max_balls
        new = max(old - lost, 0)
        m.R[1] -= pr.res(old - c.legal, c.wkts) - pr.res(max(new - c.legal, 0), c.wkts)
        c.target = revised_target(m.done[0].runs, m.R[0], m.R[1], pr.G)
        c.timing = "revised"
        m.view["target_timing"] = "revised"
        if new <= c.legal:
            c.max_balls = c.legal
            if c.legal < minb:
                c.end = "no_result"
                m._set_result("no_result")
            else:
                c.end = "cut"
        else:
            c.max_balls = m.lengths[1] = new
            c.windows = pr.windows(new)
            if new < minb:
                c.end = "no_result"
                m._set_result("no_result")
            elif c.runs >= c.target:
                c.end = "target"


# ---------------------------------------------------------------- in-play latent update (plan 9.3)

def _cholesky(a):
    n = len(a)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = a[i][j]
            for k in range(j):
                s -= L[i][k] * L[j][k]
            L[i][j] = math.sqrt(s) if i == j else s / L[j][j]
    return L


def _solve_spd(L, b):
    n = len(b)
    y = [0.0] * n
    for i in range(n):
        s = b[i]
        for k in range(i):
            s -= L[i][k] * y[k]
        y[i] = s / L[i][i]
    return _back_solve_t(L, y)


def _back_solve_t(L, y):
    """x with L^T x = y."""
    n = len(y)
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = y[i]
        for k in range(i + 1, n):
            s -= L[k][i] * x[k]
        x[i] = s / L[i][i]
    return x


def latent_posterior(P, base_view: dict, recs, cur_number: int, free, mu, sd, fixed, n_match: int,
                     iters: int = 10):
    """Newton iterations from 0 (exactly `iters`, no line search) for the latents with indices `free`
    in the full latent vector (match latents 0..n_match-1, then the current innings'), on the outcome
    log-likelihood of the recorded balls `recs` (dicts with inn, view, cls; view holds pre-ball view
    keys, dtype legal or noball) plus the Gaussian prior N(mu, sd^2); `fixed` is the full latent vector
    at which eta0 is evaluated (free entries 0). Balls of other innings inform only the match latents.
    Returns (mode, L), L the Cholesky factor of the posterior precision at the mode; a draw is
    mode + L^-T z. Sums run over balls in list order, classes 0..8, then latent indices."""
    nf = len(free)
    pre = []
    for r in recs:
        vb = dict(base_view)
        vb.update(r["view"])
        vb["latent"] = tuple(fixed)
        eta0 = list(P.outcome_eta(vb))
        if vb.get("dtype") == "noball" or vb.get("free_hit"):
            eta0[OUT] += MASK_OFFSET
        D = P.latent_directions(vb)
        rows = [[0.0] * 9 if j >= n_match and r["inn"] != cur_number else list(D[j]) for j in free]
        pre.append((eta0, rows, r["cls"]))
    var = [s * s for s in sd]

    def grad_prec(th):
        g = [-(th[j] - mu[j]) / var[j] for j in range(nf)]
        h = [[(1.0 / var[i] if i == j else 0.0) for j in range(nf)] for i in range(nf)]
        for eta0, rows, cls in pre:
            eta = [e + sum(th[j] * rows[j][k] for j in range(nf)) for k, e in enumerate(eta0)]
            p = softmax(eta)
            md = [sum(pk * rk for pk, rk in zip(p, rows[j])) for j in range(nf)]
            for i in range(nf):
                g[i] += rows[i][cls] - md[i]
                for j in range(nf):
                    h[i][j] += sum(pk * ri * rj for pk, ri, rj in zip(p, rows[i], rows[j])) - md[i] * md[j]
        return g, h

    th = [0.0] * nf
    for _ in range(iters):
        g, h = grad_prec(th)
        step = _solve_spd(_cholesky(h), g)
        th = [a + b for a, b in zip(th, step)]
    _, h = grad_prec(th)
    return th, _cholesky(h)


# ---------------------------------------------------------------- in-play state checks and imputation

def check_state(st: dict, pr: Prepared) -> list[str]:
    """Invariants of plan 9.3 plus structural checks; [] when the state is valid."""
    errs = state_schema_errors(st, pr.sc)
    if errs:
        return errs
    c, it = st["cur"], st["innings_team"]
    n = c["number"]
    if len(st["done"]) != n - 1:
        errs.append(f"cur.number {n} but {len(st['done'])} completed innings")
    if not 1 <= n <= len(it) or it[n - 1] != c["team"]:
        errs.append("cur.team does not match innings_team")
    for i, d in enumerate(st["done"]):
        if i < len(it) and d["team"] != it[i]:
            errs.append(f"done[{i}].team does not match innings_team")
    team, opp = c["team"], 1 - c["team"]
    order = set(pr.orders[team])
    outs = [p for p, b in c["batters"].items() if b.get("out")]
    if c["wkts"] != len(outs):
        errs.append(f"wkts {c['wkts']} != dismissed count {len(outs)}")
    if sum(b["balls"] for b in c["bowlers"].values()) != c["legal_balls"]:
        errs.append("sum of bowler balls != legal_balls")
    if len(c["over_bowlers"]) != c["legal_balls"] // 6 or c["ball_in_over"] != c["legal_balls"] % 6:
        errs.append("over_bowlers / ball_in_over inconsistent with legal_balls")
    for p in (c["striker"], c["nonstriker"]):
        if p not in order or p not in c["batters"] or c["batters"][p].get("out") or p in c["unavailable"]:
            errs.append(f"current batter {p} is not an available, not-out batter of the batting side")
    if c["striker"] == c["nonstriker"]:
        errs.append("striker == nonstriker")
    if set(c["batters"]) - order:
        errs.append("batters outside the batting order")
    fielders = set(pr.xi[opp]) | set(pr.opts[opp])
    if set(c["bowlers"]) - fielders or set(c["over_bowlers"]) - fielders:
        errs.append("bowlers outside the fielding side")
    if c["target"] is not None and c["target"] - c["runs"] <= 0:
        errs.append("runs_required must be > 0")
    if c["max_balls"] is not None and c["legal_balls"] >= c["max_balls"]:
        errs.append("legal_balls must be < max_balls")
    if pr.limited and c["max_balls"] is None:
        errs.append("limited overs need cur.max_balls")
    if c["ball_in_over"] and c["bowler"] is None:
        errs.append("mid-over states need the current bowler")
    if c["bowler"] is not None and c["bowler"] == c["last_bowler"]:
        errs.append("the current bowler bowled the previous over")
    if min(c["reviews"]) < 0:
        errs.append("negative reviews")
    if c["wkts"] >= 10:
        errs.append("the innings is already all out")
    if not pr.limited:
        ck = st["clock"]
        used = sum(d["legal_balls"] for d in st["done"]) + c["legal_balls"] + 12 * ck["changeovers"]
        if ck.get("used") is not None and ck["used"] != used:
            errs.append("clock.used != match legal balls + 12 * changeovers")
        if len(ck["avail"]) != pr.rules["test_days"]:
            errs.append("clock.avail needs one entry per scheduled day")
    return errs


def impute_state(partial: dict, scenario: dict, provider=None) -> dict:
    """Fill a minimal in-play state deterministically (plan 9.3): batters are the next two not yet
    dismissed at 0 runs and 0 balls (the first `wkts` available batters are taken as dismissed),
    bowler overs are filled greedily in bowling-option order under the consecutive-over, quota and
    feasibility rules, runs are split over bowlers in proportion to balls, reviews are full, the umpire
    end is left to the engine. Tests: past days are full days, the current day full, later days drawn."""
    pr = Prepared(scenario, provider)
    p = copy.deepcopy(partial)
    cur = p["cur"]
    n = cur.get("number", len(p.get("done", [])) + 1)
    if "innings_team" not in p:
        first = cur["team"] if n % 2 else 1 - cur["team"]
        p["innings_team"] = [first, 1 - first] * (1 if pr.limited else 2)
    it = p["innings_team"]
    team = cur.setdefault("team", it[n - 1])
    cur["number"] = n
    sched = pr.rules["max_balls"]
    done = []
    for i, d in enumerate(p.get("done", [])):
        done.append({"team": d.get("team", it[i]), "runs": d["runs"], "wkts": d["wkts"],
                     "legal_balls": d.get("legal_balls", sched or 0), "max_balls": d.get("max_balls", sched),
                     "target": d.get("target"), "end": d.get("end", "all_out" if d["wkts"] >= 10 else
                                                             "balls" if pr.limited else "declared")})
    p["done"] = done
    L, w = cur["legal_balls"], cur["wkts"]
    cur.setdefault("max_balls", (p.get("lengths") or [sched, sched])[n - 1] if pr.limited else None)
    cur.setdefault("target", None)
    cur.setdefault("target_timing", None if cur["target"] is None else "original")
    unav = list(cur.get("unavailable", []))
    avail = [x for x in pr.orders[team] if x not in unav and x not in pr.absent[team]]
    if "batters" not in cur:
        bats = {}
        for i, x in enumerate(avail[:w + 2]):
            bats[x] = {"runs": 0, "balls": 0, "arrival": i + 1, "out": "unknown" if i < w else None}
        cur["batters"] = bats
        cur["striker"], cur["nonstriker"] = avail[w], avail[w + 1]
    cur["unavailable"] = unav
    cur.setdefault("next", 0)
    if "bowlers" not in cur:
        opts = pr.opts[1 - team]
        n_overs = cur["max_balls"] // 6 if pr.limited else None
        ob, overs = [], {}
        for k in range(L // 6 + (1 if L % 6 else 0)):
            last = ob[-1] if ob else None
            el = eligible_bowlers(opts, overs, last, n_overs, k) or [x for x in opts if x != last]
            b = el[0]
            ob.append(b)
            overs[b] = overs.get(b, 0) + 1
        balls = Counter(ob[:L // 6])
        balls = {b: 6 * x for b, x in balls.items()}
        if L % 6:
            balls[ob[-1]] = balls.get(ob[-1], 0) + L % 6
        runs = cur["runs"]
        share = {b: runs * x // L if L else 0 for b, x in balls.items()}
        rem = runs - sum(share.values())
        for b in list(share)[:rem]:
            share[b] += 1
        cur["bowlers"] = {b: {"balls": balls[b], "runs": share[b], "wkts": 0} for b in balls}
        cur["over_bowlers"] = ob[:L // 6]
        cur["bowler"] = ob[-1] if L % 6 else None
        cur["last_bowler"] = ob[L // 6 - 1] if L // 6 else None
    cur.setdefault("ball_in_over", L % 6)
    cur.setdefault("free_hit", False)
    cur.setdefault("reviews", [pr.rpi, pr.rpi])
    cur.setdefault("fail_reviews", [0, 0])
    cur.setdefault("umpire_offset", None)
    cur.setdefault("partnership", [0, 0])
    cur.setdefault("ball_age_overs", (L // 6) % 80 if not pr.limited else L // 6)
    cur.setdefault("second_new_ball", (L // 6) >= 80 and not pr.limited)
    cur.setdefault("last_over_runs", 0)
    cur.setdefault("last_over_wkt", False)
    cur.setdefault("over_runs", 0)
    cur.setdefault("wkt_this_over", False)
    cur.setdefault("over_scores", [])
    if pr.limited:
        p.setdefault("lengths", [sched, cur["max_balls"] if n == 2 else sched])
        p.setdefault("resources", [None, None])
        p.setdefault("pending_interruptions", None)
    elif "clock" not in p:
        opd6 = 6 * pr.rules["test_overs_per_day"]
        ch = n - 1
        used = sum(d["legal_balls"] for d in done) + L + 12 * ch
        day = min(pr.rules["test_days"], 1 + used // opd6)
        p["clock"] = {"used": used, "changeovers": ch,
                      "avail": [opd6 if d < day else None for d in range(pr.rules["test_days"])]}
    p.setdefault("toss", None)
    return p


# ---------------------------------------------------------------- many simulations and outputs (plan 9.7)

def _quantile(cnt: Counter, n: int, q100: int):
    """Lower inverted-CDF quantile: smallest x with cumulative count * 100 >= q100 * n."""
    if not n:
        return None
    cum = 0
    for x in sorted(cnt):
        cum += cnt[x]
        if 100 * cum >= q100 * n:
            return x
    return max(cnt)


class Acc:
    """Integer sufficient statistics of a set of simulations; merge(a, b) is exact."""

    def __init__(self, n_overs: int | None = None):
        self.n = 0
        self.n_overs = n_overs
        self.codes = []
        self.counts = Counter()
        self.inn = {}
        self.over_runs = {}
        self.worm = {}
        self.players = {}
        self.stats = Counter()
        self.deliveries = 0

    def add(self, rec: dict):
        self.n += 1
        res = rec["result"]
        self.codes.append((rec["sim"], rec["code"]))
        cn = self.counts
        cn["code", rec["code"]] += 1
        cn["tie_before"] += res["tie_before"]
        cn["method", res["method"]] += 1
        cn["super_overs", res["super_overs"]] += 1
        if res["result"] == "win":
            cn["margin", res["winner"], res["margin_kind"], res["margin"]] += 1
        for (k, team, runs, wkts, legal, end), ov in zip(rec["innings"], rec["overs"]):
            d = self.inn.setdefault(k, {"n": 0, "runs": Counter(), "runs2": 0, "wkts": Counter(),
                                        "balls": 0, "end": Counter()})
            d["n"] += 1
            d["runs"][runs] += 1
            d["runs2"] += runs * runs
            d["wkts"][wkts] += 1
            d["balls"] += legal
            d["end"][end] += 1
            po, wm = self.over_runs.setdefault(k, []), self.worm.setdefault(k, [])
            prev = 0
            length = max(len(ov), self.n_overs or 0) if self.n_overs else len(ov)
            for j in range(length):
                if j < len(ov):
                    if len(po) <= j:
                        po.append(Counter())
                    po[j][ov[j] - prev] += 1
                    prev = ov[j]
                if len(wm) <= j:
                    wm.append(Counter())
                wm[j][ov[j] if j < len(ov) else ov[-1] if ov else 0] += 1
        for p, s in rec["players"].items():
            a = self.players.setdefault(p, [0] * 12)
            a[0] += 1
            a[1] += s[0]
            a[2] += s[0] * s[0]
            a[3] += s[1]
            a[4] += s[2]
            a[5] += s[3]
            a[6] += s[4] >= 50
            a[7] += s[4] >= 100
            a[8] += s[5]
            a[9] += s[6]
            a[10] += s[7]
            a[11] += s[7] >= 3
        self.stats.update(rec["stats"])
        self.deliveries += rec["deliveries"]

    def merge(self, o: "Acc") -> "Acc":
        out = Acc(self.n_overs)
        for a in (self, o):
            out.n += a.n
            out.codes += a.codes
            out.counts.update(a.counts)
            out.stats.update(a.stats)
            out.deliveries += a.deliveries
            for k, d in a.inn.items():
                e = out.inn.setdefault(k, {"n": 0, "runs": Counter(), "runs2": 0, "wkts": Counter(),
                                           "balls": 0, "end": Counter()})
                for f in ("n", "runs2", "balls"):
                    e[f] += d[f]
                for f in ("runs", "wkts", "end"):
                    e[f].update(d[f])
            for src, dst in ((a.over_runs, out.over_runs), (a.worm, out.worm)):
                for k, rows in src.items():
                    t = dst.setdefault(k, [])
                    for j, cnt in enumerate(rows):
                        if len(t) <= j:
                            t.append(Counter())
                        t[j].update(cnt)
            for p, s in a.players.items():
                t = out.players.setdefault(p, [0] * 12)
                for i, x in enumerate(s):
                    t[i] += x
        return out


def _p(x: int, n: int) -> dict:
    p = x / n if n else 0.0
    return {"p": p, "se": math.sqrt(p * (1 - p) / n) if n else 0.0}


def summarize(acc: Acc) -> dict:
    n, cn = acc.n, acc.counts
    code = [cn["code", i] for i in range(5)]
    out = {"n": n, "p_win": [_p(code[0], n), _p(code[1], n)], "p_tie_before": _p(cn["tie_before"], n),
           "p_tie": _p(code[2], n), "p_draw": _p(code[3], n), "p_no_result": _p(code[4], n),
           "deliveries": acc.deliveries}
    out["methods"] = {str(k[1]): v for k, v in cn.items() if k[0] == "method"}
    out["super_overs"] = {str(k[1]): v for k, v in cn.items() if k[0] == "super_overs"}
    margins = {}
    for k, v in sorted((k, v) for k, v in cn.items() if k[0] == "margin"):
        margins.setdefault(f"{k[1]}:{k[2]}", []).append([k[3], v])
    out["margins"] = margins
    inns = {}
    for k in sorted(acc.inn):
        d = acc.inn[k]
        m = d["n"]
        s1 = sum(x * c for x, c in d["runs"].items())
        mean = s1 / m
        var = max(0.0, (d["runs2"] - s1 * s1 / m) / (m - 1)) if m > 1 else 0.0
        inns[str(k)] = {"n": m, "runs_mean": mean, "runs_sd": math.sqrt(var), "runs_se": math.sqrt(var / m),
                        "runs_q": {q: _quantile(d["runs"], m, q) for q in (5, 10, 25, 50, 75, 90, 95)},
                        "runs_hist": sorted([x, c] for x, c in d["runs"].items()),
                        "wkts_dist": [d["wkts"][w] / m for w in range(11)],
                        "wkts_mean": sum(w * c for w, c in d["wkts"].items()) / m,
                        "balls_mean": d["balls"] / m, "end": dict(d["end"])}
    out["innings"] = inns

    def rows(src):
        res = {}
        for k, lst in sorted(src.items()):
            res[str(k)] = [{"over": j + 1, "n": sum(c.values()),
                            "mean": sum(x * y for x, y in c.items()) / sum(c.values()),
                            "q10": _quantile(c, sum(c.values()), 10), "q50": _quantile(c, sum(c.values()), 50),
                            "q90": _quantile(c, sum(c.values()), 90)} for j, c in enumerate(lst)]
        return res
    out["runs_by_over"], out["worm"] = rows(acc.over_runs), rows(acc.worm)
    pl = {}
    for p, a in sorted(acc.players.items()):
        k = a[0]
        mean = a[1] / n
        var = max(0.0, (a[2] - a[1] * a[1] / n) / (n - 1)) if n > 1 else 0.0
        pl[p] = {"matches_involved": k, "bat_runs": mean, "bat_runs_se": math.sqrt(var / n), "bat_balls": a[3] / n,
                 "bat_innings": a[4] / n, "outs": a[5] / n, "p50": _p(a[6], n), "p100": _p(a[7], n),
                 "bowl_balls": a[8] / n, "bowl_runs": a[9] / n, "bowl_wkts": a[10] / n, "p3w": _p(a[11], n),
                 "economy": 6 * a[9] / a[8] if a[8] else None}
    out["players"] = pl
    kinds = {k[5:]: v for k, v in acc.stats.items() if k.startswith("kind_")}
    tot = sum(kinds.values())
    out["dismissals"] = {k: {"per_match": v / n, "share": v / tot} for k, v in sorted(kinds.items())}
    drs_keys = ("bat_reviews", "bat_overturned", "bat_ucall", "field_success", "field_spec", "field_spec_ucall",
                "missed_standing")
    out["drs"] = {k: acc.stats[k] / n for k in drs_keys}
    out["drs"]["missed_outs_lower_bound"] = (acc.stats["field_success"] + acc.stats["missed_standing"]) / n
    out["bowler_fallbacks"] = acc.stats["bowler_fallback"]
    return out


def simulate(pr: Prepared, sims, seed: int, *, logs: dict | None = None) -> Acc:
    """Run the sims (any iterable of indices) for a prepared scenario; logs[sim] collects event logs."""
    acc = Acc(pr.rules["max_balls"] // 6 if pr.limited else None)
    state = pr.sc["state"]
    for i in sims:
        log = [] if logs is not None and i in logs else None
        m = Match(pr, i, seed, log=log, state=state).play()
        if log is not None:
            logs[i] = log
        acc.add(m.record())
    return acc


def default_factors(sc: dict) -> dict:
    """Sensitivity factors (scenario overrides) that change something in this scenario."""
    f = {}
    pitch = sc.get("pitch") or {}
    if any(pitch.get(k) for k in ("runs_sd", "wkt_sd", "spin_sd", "wear_sd")):
        f["pitch"] = {"pitch": {**pitch, "runs_sd": 0.0, "wkt_sd": 0.0, "spin_sd": 0.0, "wear_sd": 0.0}}
    for pid, s in (sc.get("player_form") or {}).items():
        if any(s.values()):
            f[f"form:{pid}"] = {"player_form": {k: v for k, v in sc["player_form"].items() if k != pid}}
    if sc.get("weather"):
        f["weather"] = {"weather": None}
    if not sc.get("neutral") and any(t.get("home") for t in sc["teams"]):
        f["home"] = {"neutral": True}
    if sc.get("umpires"):
        f["umpires"] = {"umpires": None}
    drs = sc.get("drs") or {}
    if (drs.get("accuracy_mult") or 1.0) != 1.0 or (drs.get("ucall_mult") or 1.0) != 1.0:
        f["drs"] = {"drs": {**drs, "accuracy_mult": 1.0, "ucall_mult": 1.0}}
    return f


def _paired(base: dict, var: dict, target) -> dict:
    sims = sorted(base)
    n = len(sims)
    d = [(base[s] in target) - (var[s] in target) for s in sims]
    s1, s2 = sum(d), sum(x * x for x in d)
    vd = (s2 - s1 * s1 / n) / (n - 1) if n > 1 else 0.0
    return {"effect": s1 / n, "se": math.sqrt(max(vd, 0.0) / n)}


def sensitivity(scenario: dict, provider=None, sims=range(2000), seed: int = 0, factors: dict | None = None,
                base: Acc | None = None) -> dict:
    """Plan 9.7: rerun with each factor reset to neutral on common random numbers. `effect` is the
    scenario's probability minus the reset scenario's, with a paired-difference SE."""
    sc = validate_scenario(scenario)
    factors = default_factors(sc) if factors is None else factors
    if base is None:
        base = simulate(Prepared(sc, provider), sims, seed)
    b = dict(base.codes)
    out = {}
    for name, over in factors.items():
        v = dict(simulate(Prepared({**sc, **over}, provider), sims, seed).codes)
        out[name] = {"p_win0": _paired(b, v, (0,)), "p_win1": _paired(b, v, (1,)),
                     "p_draw_tie": _paired(b, v, (2, 3))}
    return out


def run(scenario: dict, provider=None, *, n_sims: int | None = None, seed: int | None = None, start: int = 0,
        log_sims=(), factors: dict | None = None) -> dict:
    """Simulate a scenario (plan 9.1) and return the plan 9.7 outputs."""
    pr = Prepared(scenario, provider)
    sc = pr.sc
    n = sc["n_sims"] if n_sims is None else n_sims
    seed = sc["seed"] if seed is None else seed
    logs = {i: None for i in log_sims}
    acc = simulate(pr, range(start, start + n), seed, logs=logs if log_sims else None)
    out = summarize(acc)
    out["part_timers_added"] = pr.part_timer_report
    if log_sims:
        out["logs"] = logs
    if sc["sensitivity"] or factors:
        out["sensitivity"] = sensitivity(sc, provider, range(start, start + n), seed, factors, base=acc)
    return out


def apply_script(scenario: dict, script: list, state: dict | None = None, provider=None) -> dict:
    """Scripted-draw mode: apply forced decisions to `state` (or a fresh match when None) and return the
    post-state (None when the match ended), the result and the event log."""
    pr = Prepared(scenario, provider)
    m = Match(pr, script=script, log=[], state=state).play()
    return {"state": None if m.result is not None else m.to_state(), "result": m.result, "events": m.log}


def trajectory(scenario: dict, sim: int, seed: int, provider=None) -> dict:
    """Full event log of one seeded simulation."""
    pr = Prepared(scenario, provider)
    log = []
    m = Match(pr, sim, seed, log=log, state=pr.sc["state"]).play()
    return {"events": log, "result": m.result}
