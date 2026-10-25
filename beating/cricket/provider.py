"""Probability providers for the cricket engines, a hand-set stub, and scenario/state schema checks.

Method. The engines (``beating/cricket/sim.py`` and ``docs/cricket/engine.js``) own match flow, the rules
and random-number consumption; a provider owns every probability (plan section 9.6). The engine never
looks inside a provider and a provider never mutates engine state. Every provider method receives either
the scenario or a *view*: a plain dict snapshot of the pre-ball state plus the static scenario context,
with exactly the keys documented in :data:`VIEW_KEYS`. The engine owns the dict and refreshes it in
place before each call (no per-ball allocation), so a provider must treat it as read-only and must not
keep references to it. Sequences a provider returns are owned by the caller, which may modify them.

Conventions shared by both engines:

- ``dtype_eta`` returns 3 log-odds (legal, wide, noball; legal is 0 by convention but need not be);
  ``outcome_eta`` returns 9 (classes of :data:`OUTCOMES`), unmasked: the engine adds
  ``glm.MASK_OFFSET`` (-30) to class 6 on no-balls and free hits. ``wk_eta`` returns 5 (classes of
  :data:`KINDS`). The engine converts log-odds and weights to draws itself (plan 9.5).
- The in-play latent update (plan 9.3) is the engine's Newton loop; per ball it asks
  ``latent_loglik(view, cls, idx, offset)`` for the log-likelihood, gradient and Hessian along the
  latents ``idx`` at ``view["latent"]``. :func:`affine_latent_loglik` implements it for any provider
  whose ``outcome_eta`` is affine in the latents with slopes ``latent_directions(view)``.
- Bowler choice: ``bowler_utility(view, cand)`` is called for each eligible candidate in bowling-option
  order with the view at the over end (``bowler`` None, the next over's striker and non-striker).

- Empirical tables return non-negative weights (they need not sum to one); the engine draws from them
  with the categorical rule of plan 9.5 applied to running sums of the weights.
- Form shifts in the view are in player-SD units (slider + standard normal draw); the provider scales
  them by its own player posterior SDs. Latent values are in eta units along the provider's directions.
- Resources are integers in tenths of a percent of the full scheduled innings, computed as
  ``floor(1000 * Z(u, w) / Z(N_sched, 0) + 0.5)`` (half-up, not Python's banker's rounding).

:class:`StubProvider` is a small hand-set model (no data) that gives plausible cricket: T20 first
innings about 160, ODI about 270, Test innings about 330 with about 15% draws. It exists so the engine
tests and parity vectors are meaningful; its numbers are not estimates of anything.

Limits. The view is the contract for the real provider: a feature it needs that is not derivable from
these keys plus the parameter bundle needs a new key in both engines.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Protocol, Sequence

FAMS = ("T20", "ODI", "TEST")
OUTCOMES = ("dot", "one", "two", "three", "four", "six", "out", "run_out", "byes")
DTYPES = ("legal", "wide", "noball")
KINDS = ("caught", "bowled", "lbw", "stumped", "other")
WIDE_WKTS = ("none", "stumped", "run_out")
SCORING = (0.0, 1 / 6.5, 2 / 6.5, 3 / 6.5, 4 / 6.5, 6 / 6.5, 0.0, 0.0, 1 / 6.5)
WICKET = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
FOLLOW_ON_TABLE = [[5, 200], [3, 150], [2, 100], [1, 75]]

VIEW_KEYS = {
    # static scenario context (fixed for the simulation)
    "fam": "T20 | ODI | TEST",
    "gender": "male | female",
    "competition_id": "competition id or None",
    "date": "match date YYYY-MM-DD",
    "venue_id": "venue id or None",
    "neutral": "bool",
    "start_slot": "day | day_night | night | unknown",
    "weather": "scenario weather dict or None (None = climatology)",
    "umpires": "[umpire1, umpire2] or None",
    "rules": "engine rules dict (RULE_KEYS)",
    "drs_enabled": "bool, DRS in use in this simulation",
    "sched_balls": "scheduled innings length in legal balls (limited overs) or None",
    "scheduled_days": "Tests: scheduled days, else None",
    "teams": "(team0 name, team1 name)",
    "home": "(team0 home, team1 home) bools",
    "prep": "whatever Provider.prepare(scenario) returned",
    "toss_winner": "0 | 1 | None; set when toss_bat_prob is asked",
    # innings context (set at innings start)
    "innings": "main innings number 1..4 (super-over innings keep the main number 0)",
    "super_over": "0 in the main match, k >= 1 in the k-th super over",
    "so_innings": "1 | 2 within a super over, else 0",
    "bat_team": "batting team index 0 | 1",
    "bowl_team": "fielding team index",
    "bat_home_status": "home | away | neutral (batting side)",
    "bowl_home_status": "home | away | neutral (fielding side)",
    "target_timing": "original | pre_inn2 | revised | None (no target)",
    "followed_on": "bool, the follow-on was enforced in this match",
    "prev_innings": "tuple of (team, runs, wkts, legal_balls, end) for completed main innings",
    "umpire_offset": "0 | 1: umpire index at the bowler's end in even overs",
    "latent": "tuple of latent values: match latents then this innings' latents (latent_spec order)",
    # pre-ball state
    "legal_balls": "legal balls bowled in this innings",
    "ball_in_over": "legal balls already bowled in this over",
    "over": "0-based over index (completed overs in the innings)",
    "max_balls": "current innings length in legal balls (limited; super over 6) or None",
    "balls_remaining": "max_balls - legal_balls or None",
    "runs": "innings runs",
    "wkts": "innings wickets",
    "unavailable": "wickets plus batters unavailable (absent, retired hurt)",
    "target": "runs needed to win in total (chases) or None",
    "runs_required": "target - runs or None",
    "striker": "striker id (None = an average batter, super-over bowler selection only)",
    "nonstriker": "non-striker id",
    "bowler": "bowler id (None between overs, and = an average bowler in super-over batter selection)",

    "striker_runs": "int", "striker_balls": "legal balls + no-balls faced",
    "nonstriker_runs": "int", "nonstriker_balls": "int",
    "striker_arrival": "rank of arrival 1..11", "nonstriker_arrival": "int",
    "striker_pos": "1-based batting-order position", "nonstriker_pos": "int",
    "bowler_balls": "legal balls bowled by the bowler this innings",
    "bowler_runs": "bat runs + wides + no-ball penalty conceded",
    "bowler_wkts": "bowler-credited wickets",
    "bowler_overs": "completed overs",
    "bowler_spell": "consecutive alternate overs k-2, k-4, ... bowled before this over",
    "bowler_part_timer": "bool, appended because the options were infeasible (zero player vectors)",
    "partnership_runs": "int", "partnership_balls": "legal balls + no-balls since the pair formed",
    "free_hit": "bool, this delivery is a free hit",
    "pp_window": "pp1 | pp2 | pp3 | none (mandatory powerplay windows, scaled to max_balls)",
    "field_restr": "max fielders outside the circle or None",
    "reviews_bat": "reviews left, batting side", "reviews_bowl": "reviews left, fielding side",
    "bat_fail_reviews": "unsuccessful non-umpire's-call reviews this innings", "bowl_fail_reviews": "int",
    "ball_age_overs": "completed overs since the last new ball",
    "second_new_ball": "bool, a new ball has been taken this innings",
    "innings_overs": "completed overs in the innings",
    "match_legal_balls": "legal balls in the match so far (main innings)",
    "clock_used": "Tests: match_legal_balls + 12 * changeovers, else None",
    "est_day": "Tests: 1-based day from the simulated clock, else None",
    "overs_into_day": "Tests: completed overs into est_day, else None",
    "exp_overs_left": "Tests: (realized availability through est_day + expected later days - used) / 6",
    "lead": "batting side's match aggregate minus the opponent's (includes this innings)",
    "striker_form": "(bat_runs, bat_wkt) in player-SD units", "nonstriker_form": "(bat_runs, bat_wkt)",
    "bowler_form": "(bowl_runs, bowl_wkt) in player-SD units or None",
    "bowl_end_umpire": "umpire id at the bowler's end or None",
    "to_come": "tuple of ids still to bat, in order (not yet batted, available)",
    "last_over_runs": "runs in the over just completed (over-end decisions)",
    "last_over_wkt": "bool, a wicket fell in the over just completed",
    "dtype": "legal | wide | noball while the delivery's later models are asked, else None",
}

RULE_KEYS = {
    "balls_per_over": "6 (the Hundred is not simulated)",
    "max_balls": "scheduled innings length in legal balls; None for Tests",
    "min_balls_for_result": "legal balls innings 2 must be able to face for a result",
    "free_hit": "none | front_foot | all_noballs",
    "p_free_hit_given_nb": "probability a no-ball gives a free hit under front_foot",
    "noball_runs": "no-ball penalty runs",
    "caught_crossing_counts": "bool, batters who crossed before a catch stay crossed",
    "drs_enabled": "bool", "reviews_per_innings": "int", "umpires_call_retains": "bool",
    "review_topup_after_80": "bool, Tests reset reviews to the allowance after 80 overs",
    "tie_break": "none | so_repeat | so_boundary_count | bowl_out",
    "fielders_outside": "[[from_over, to_over, max_outside], ...] 1-based inclusive, or None",
    "pp_mandatory": "[[from_over, to_over], ...] mandatory powerplay windows, or None",
    "test_days": "int or None", "test_overs_per_day": "int or None",
    "follow_on_lead": "[[min_days_remaining, lead], ...] descending, or None",
    "new_ball_after_overs": "int or None",
    "balls_in_use": "one | two_new_balls | two_balls_until_34",
    "quota_rule": "fifth_min2 | fifth: bowler quota of an n-over innings (rules.reduced_quota)",
    "pp_reduced": "{str(n_overs): {mandatory: [[a, b]], field_restr: [[a, b, max]]}} in 1-based inclusive "
                  "legal balls (rules pp_windows_reduced), or None (scale the scheduled windows)",
}


class Provider(Protocol):
    """Everything probabilistic the engines need. All floats are float64."""

    def prepare(self, scenario: dict) -> Any:
        """Called once per scenario; the result is exposed as view["prep"] (precomputed statics)."""

    def rules(self, scenario: dict) -> dict:
        """Engine rules dict with the keys of RULE_KEYS (scenario["drs"] overrides are applied by the engine)."""

    def latent_spec(self, scenario: dict) -> dict:
        """{"match": [{"name", "sd", "pitch"}...] (at most 4; pitch = scenario pitch slider key),
        "innings": [{"name", "sd"}...] (at most 2)}. Order defines view["latent"]."""

    def latent_directions(self, view: dict) -> Sequence[Sequence[float]]:
        """d x 9 slopes of outcome_eta with respect to each latent of view["latent"] at this ball
        (d = number of match plus innings latents; documentation and the affine helper only)."""

    def latent_loglik(self, view: dict, cls: int, idx: Sequence[int], offset: Sequence[float]
                      ) -> tuple[float, list[float], list[list[float]]]:
        """In-play latent update (plan 9.3). Log-likelihood of on-field outcome class `cls` at
        view["latent"], with the engine's mask offsets `offset` (9 floats) added to outcome_eta, and
        its gradient (len(idx)) and Hessian (len(idx) x len(idx)) with respect to the latents
        view["latent"][j] for j in idx. Providers whose outcome_eta is affine in the latents use
        affine_latent_loglik(self, ...)."""

    def toss_bat_prob(self, view: dict) -> float:
        """P(toss winner view["toss_winner"] bats first)."""

    def dtype_eta(self, view: dict) -> Sequence[float]:
        """3 log-odds: legal, wide, noball."""

    def outcome_eta(self, view: dict) -> Sequence[float]:
        """9 unmasked log-odds for the classes of OUTCOMES (view["dtype"] is legal or noball)."""

    def wk_eta(self, view: dict) -> Sequence[float]:
        """5 log-odds for the dismissal kinds of KINDS given an on-field bowler-credited out."""

    def drs_bat(self, view: dict, kind: int) -> tuple[float, float, float]:
        """(q_bat, p_overturn_bat, p_ucall_bat) for an on-field out of kind index `kind` (caught or lbw)."""

    def drs_field(self, view: dict, cls: int) -> tuple[float, float, float, float]:
        """(lambda_field, lbw share of missed outs, r_spec, umpire's-call share of failed speculative reviews)
        for outcome class `cls` 0..8, or 9 for a wide."""

    def wide_wkt(self, view: dict) -> Sequence[float]:
        """3 weights: none, stumped, run_out (the engine zeroes stumped on a free hit)."""

    def wide_runs(self, view: dict, wkt: int) -> Sequence[float]:
        """5 weights for wide runs k = 1..5 (5 = boundary) given the wide-wicket index."""

    def bye_runs(self, view: dict) -> Sequence[float]:
        """5 weights for byes/leg-byes 1..5 (4 = boundary)."""

    def runs5_7(self, view: dict) -> tuple[float, float]:
        """(P(5 | four class), P(7 | six class))."""

    def runout_runs(self, view: dict) -> Sequence[float]:
        """4 weights for runs completed 0..3 before a run-out (view["dtype"] gives the delivery type)."""

    def runout_who(self, view: dict, runs: int) -> float:
        """P(the striker is the run-out victim | runs completed)."""

    def runout_new_on_strike(self, view: dict, who: int, runs: int) -> float:
        """P(new batter faces next | victim who (0 striker, 1 non-striker), min(runs, 2), view["dtype"])."""

    def p_crossed(self, view: dict) -> float:
        """P(new batter goes to the non-striker's end after a catch) when crossing counts."""

    def bowler_utility(self, view: dict, cand: dict) -> float:
        """Conditional-logit utility of candidate `cand` for the next over. cand keys: id, option (index
        in the bowling options), overs, balls, runs, wkts, spell (consecutive alternate overs ending at the
        previous-but-one over), quota_left (overs incl. any reduced-match bonus, None in Tests),
        overs_left (innings overs left incl. this one, None in Tests), part_timer, opened (bowled over 0
        or 1 of this innings)."""

    def declare_hazard(self, view: dict) -> float:
        """Tests: P(declare at this over end)."""

    def follow_on_prob(self, view: dict) -> float:
        """Tests: P(enforce the follow-on); the view is innings 3 with the leading side batting."""

    def new_ball_prob(self, view: dict) -> float:
        """Tests: P(take the new ball at this over end) once it is due."""

    def interruption_schedule(self, scenario: dict, from_ball: int, u: Sequence[float]) -> list[dict]:
        """Limited overs: [{"start", "lost"}...] sorted by start; start in match legal balls (0 = before
        play), lost in legal balls per innings (a multiple of 6); every start >= from_ball. u: 16 uniforms."""

    def day_availability(self, scenario: dict, day: int, u: float) -> int:
        """Tests: legal balls available on 1-based `day`."""

    def day_availability_mean(self, scenario: dict, day: int) -> float:
        """Tests: expected legal balls available on `day` (for expected overs left)."""

    def resource(self, scenario: dict, balls_remaining: int, wkts: int) -> int:
        """Limited overs: integer resource in tenths of a percent of the full scheduled innings."""

    def resource_G(self, scenario: dict) -> float:
        """Limited overs: G = Z(N_sched, 0) in runs (for revised targets above the first-innings resource)."""


def affine_latent_loglik(P, view: dict, cls: int, idx, offset):
    """latent_loglik for an outcome_eta affine in the latents with slopes latent_directions. Sums run
    over classes 0..8 in order, as in engine.js: p = softmax(eta), m_i = sum_k p_k d_ik,
    g_i = d_i,cls - m_i, H_ij = -(sum_k p_k d_ik d_jk - m_i m_j)."""
    eta = [e + o for e, o in zip(P.outcome_eta(view), offset)]
    D = P.latent_directions(view)
    mx = max(eta)
    ex = [math.exp(e - mx) for e in eta]
    s = 0.0
    for x in ex:
        s += x
    p = [x / s for x in ex]
    ll = eta[cls] - mx - math.log(s)
    rows = [D[j] for j in idx]
    md = []
    for r in rows:
        a = 0.0
        for k in range(9):
            a += p[k] * r[k]
        md.append(a)
    g = [r[cls] - m for r, m in zip(rows, md)]
    h = []
    for i, ri in enumerate(rows):
        hr = []
        for j, rj in enumerate(rows):
            a = 0.0
            for k in range(9):
                a += p[k] * ri[k] * rj[k]
            hr.append(-(a - md[i] * md[j]))
        h.append(hr)
    return ll, g, h


# ---------------------------------------------------------------- rules

def default_rules(fam: str, gender: str = "male", date: str = "2025-06-01") -> dict:
    """Engine rules for a typical international match of `fam` on `date` (subset of the rules timeline)."""
    date = str(date)[:10]
    r = {"balls_per_over": 6, "max_balls": None, "min_balls_for_result": None, "free_hit": "none",
         "p_free_hit_given_nb": 1.0, "noball_runs": 1, "caught_crossing_counts": date < "2022-10-01",
         "drs_enabled": date >= "2008-07-01", "reviews_per_innings": 2,
         "umpires_call_retains": date >= "2017-10-01", "review_topup_after_80": False, "tie_break": "none",
         "fielders_outside": None, "pp_mandatory": None, "test_days": None, "test_overs_per_day": None,
         "follow_on_lead": None, "new_ball_after_overs": None, "balls_in_use": "one", "quota_rule": "fifth_min2",
         "pp_reduced": None}
    if fam in ("T20", "ODI"):
        r["free_hit"] = "all_noballs" if date >= "2015-07-05" else "front_foot"
        r["p_free_hit_given_nb"] = 1.0 if date >= "2015-07-05" else 0.75
    if fam == "T20":
        r.update(max_balls=120, min_balls_for_result=30, pp_mandatory=[[1, 6]],
                 fielders_outside=[[1, 6, 2], [7, 20, 5]],
                 reviews_per_innings=2 if date >= "2020-08-28" else 1,
                 tie_break="so_repeat" if date >= "2019-10-14" else
                 "so_boundary_count" if date >= "2008-12-26" else "bowl_out")
    elif fam == "ODI":
        r.update(max_balls=300, min_balls_for_result=120, pp_mandatory=[[1, 10], [11, 40], [41, 50]],
                 fielders_outside=[[1, 10, 2], [11, 40, 4], [41, 50, 5]],
                 reviews_per_innings=2 if date >= "2020-08-01" else 1,
                 tie_break="none" if gender == "male" else "so_repeat",
                 balls_in_use="two_new_balls" if "2011-10-01" <= date < "2025-07-01" else "one")
    elif fam == "TEST":
        r.update(test_days=5 if gender == "male" else 4, test_overs_per_day=90 if gender == "male" else 100,
                 follow_on_lead=copy.deepcopy(FOLLOW_ON_TABLE), new_ball_after_overs=80,
                 reviews_per_innings=3 if date >= "2020-07-16" else 2,
                 review_topup_after_80="2013-10-01" <= date < "2017-10-01")
    else:
        raise ValueError(f"unsupported fam {fam!r}")
    return r


def engine_rules(raw: dict, fam: str) -> dict:
    """Map a ``rules.rules_for`` result (plan section 5 names) to the engine rules dict. DRS is on when
    the rules allow it (``drs_allowed``); the scenario's drs settings override it."""
    r = default_rules(fam)
    pp = raw.get("pp_windows")
    fo = raw.get("follow_on_lead_by_days")
    two, until = raw.get("two_new_balls"), raw.get("two_new_balls_until_over")
    fh = raw.get("free_hit") or "none"
    pfh = raw.get("p_free_hit_given_nb")
    r.update(balls_per_over=raw.get("balls_per_over") or 6, max_balls=raw.get("balls_per_innings"),
             min_balls_for_result=raw.get("min_balls_for_result"), free_hit=fh,
             p_free_hit_given_nb=float(pfh) if pfh is not None else (0.0 if fh == "none" else 1.0),
             noball_runs=raw.get("noball_penalty_runs") or 1,
             caught_crossing_counts=bool(raw.get("caught_crossing_counts")),
             drs_enabled=bool(raw.get("drs_allowed")), reviews_per_innings=raw.get("reviews_per_innings") or 0,
             umpires_call_retains=bool(raw.get("umpires_call_retains_review")),
             review_topup_after_80=bool(raw.get("review_topup_after_80")),
             tie_break=raw.get("tie_break") or "none", fielders_outside=raw.get("field_restr"),
             pp_mandatory=pp.get("mandatory") if isinstance(pp, dict) else None,
             test_days=raw.get("scheduled_days"), test_overs_per_day=raw.get("test_overs_per_day"),
             follow_on_lead=sorted(([int(d), int(x)] for d, x in fo.items()), reverse=True) if fo else None,
             new_ball_after_overs=raw.get("new_ball_after_overs"),
             balls_in_use="two_balls_until_34" if two and until else "two_new_balls" if two else "one",
             quota_rule=raw.get("reduced_quota_rule") or "fifth_min2", pp_reduced=raw.get("pp_windows_reduced"))
    if fam == "TEST":
        r["max_balls"] = r["min_balls_for_result"] = None
    return r



# ---------------------------------------------------------------- stub provider

def _eta(p):
    return tuple(math.log(x / p[0]) for x in p)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


_BASE = {
    "T20": (0.35, 0.37, 0.07, 0.004, 0.105, 0.048, 0.04, 0.005, 0.016),
    "ODI": (0.50, 0.33, 0.06, 0.006, 0.07, 0.014, 0.0215, 0.004, 0.015),
    "TEST": (0.71, 0.17, 0.04, 0.008, 0.052, 0.004, 0.0145, 0.0015, 0.012),
}
_PHASE = {"pp": (0, -0.15, -0.15, 0, 0.30, 0.05, -0.10, 0, 0), "mid": (0, 0.08, 0.05, 0, -0.15, -0.10, -0.12, 0, 0),
          "death": (0, 0.0, 0.35, 0.2, 0.25, 0.65, 0.55, 0.4, 0), "test": (0,) * 9}
_POS = {1: (0, 0), 2: (0, 0), 3: (0, 0), 4: (0, 0), 5: (0, 0), 6: (-0.05, 0.1), 7: (-0.15, 0.25), 8: (-0.35, 0.5),
        9: (-0.55, 0.75), 10: (-0.75, 0.95), 11: (-0.9, 1.1)}
_DTYPE = {"T20": (0.040, 0.0055), "ODI": (0.033, 0.005), "TEST": (0.010, 0.012)}
_KIND = {"T20": (0.64, 0.17, 0.12, 0.06, 0.01), "ODI": (0.60, 0.19, 0.14, 0.06, 0.01),
         "TEST": (0.52, 0.20, 0.22, 0.04, 0.02)}
_TOSS = {"T20": 0.38, "ODI": 0.55, "TEST": 0.75}
_CROSSED = {"T20": 0.47, "ODI": 0.27, "TEST": 0.06}
_RAIN = {"T20": 0.06, "ODI": 0.12, "TEST": 0.25}
_RES = {"T20": (330.0, 0.040), "ODI": (300.0, 0.030)}
_NEW_ON_STRIKE = ((0.40, 0.85, 0.45), (0.55, 0.27, 0.50))
_CAL = {"T20": (0.16, 0.0), "ODI": (0.22, -0.2), "TEST": (0.0, -0.47)}



class StubProvider:
    """Hand-set provider for tests and parity vectors. `players` maps id -> optional overrides:
    bat, bat_wkt, bowl, bowl_wkt (eta shifts along the scoring and wicket directions), spin (bool)."""

    def __init__(self, players: dict | None = None):
        self.players = players or {}
        base = {}
        for fam, p in _BASE.items():
            e = _eta([x / sum(p) for x in p])
            for ph, add in _PHASE.items():
                base[fam, ph] = tuple(a + b for a, b in zip(e, add))
        self._base = base
        self._dtype = {f: (0.0, math.log(w / (1 - w - n)), math.log(n / (1 - w - n))) for f, (w, n) in _DTYPE.items()}
        self._kind = {f: _eta(p) for f, p in _KIND.items()}

    # --- statics
    def prepare(self, scenario: dict) -> dict:
        pos, spin, team_of = {}, {}, {}
        for t, team in enumerate(scenario["teams"]):
            for i, pid in enumerate(team["batting_order"]):
                pos[pid] = i + 1
                team_of[pid] = t
            for pid in set(team.get("bowling_xi") or []) | set(team.get("bowlers") or []):
                pos.setdefault(pid, 11)
                team_of.setdefault(pid, t)
        for pid, p in pos.items():
            over = self.players.get(pid, {})
            spin[pid] = (1 if over["spin"] else -1) if "spin" in over else (1 if p >= 10 else -1 if p >= 7 else 1)
        names = [x["name"] for x in self.latent_spec(scenario)["match"]]
        return {"pos": pos, "spin": spin, "team_of": team_of, "n_match": len(names),
                "wear": "m_wear" in names}

    def rules(self, scenario: dict) -> dict:
        r = default_rules(scenario["fam"], scenario.get("gender", "male"), scenario.get("date") or "2025-06-01")
        r.update(scenario.get("rules") or {})
        return r

    def latent_spec(self, scenario: dict) -> dict:
        m = [{"name": "m_runs", "sd": 0.22, "pitch": "runs_sd"}, {"name": "m_wkt", "sd": 0.14, "pitch": "wkt_sd"},
             {"name": "m_spin", "sd": 0.12, "pitch": "spin_sd"}]
        if scenario["fam"] == "TEST":
            m.append({"name": "m_wear", "sd": 0.15, "pitch": "wear_sd"})
        return {"match": m, "innings": [{"name": "i_runs", "sd": 0.14}, {"name": "i_wkt", "sd": 0.10}]}

    # --- delivery models
    def _wear(self, v) -> float:
        d = v["scheduled_days"]
        return 0.0 if not d or v["est_day"] is None else (v["est_day"] - 1) / (d - 1)

    def latent_directions(self, v: dict):
        sp = v["prep"]["spin"].get(v["bowler"], 0) if v["bowler"] is not None else 0
        rows = [SCORING, WICKET, tuple(sp * x for x in WICKET)]
        if v["prep"]["wear"]:
            w = self._wear(v)
            rows.append(tuple(w * x for x in WICKET))
        return [list(r) for r in rows + [SCORING, WICKET]]

    def latent_loglik(self, v: dict, cls: int, idx, offset):
        return affine_latent_loglik(self, v, cls, idx, offset)


    def _phase(self, v) -> str:
        fam = v["fam"]
        if fam == "TEST":
            return "test"
        if v["super_over"]:
            return "death"
        n, b = v["max_balls"], v["legal_balls"]
        if fam == "T20":
            return "pp" if 10 * b < 3 * n else "death" if 4 * b >= 3 * n else "mid"
        return "pp" if 5 * b < n else "death" if 5 * b >= 4 * n else "mid"

    def toss_bat_prob(self, v: dict) -> float:
        p = _TOSS[v["fam"]]
        return p - 0.12 if v["start_slot"] == "night" and v["fam"] != "TEST" else p

    def dtype_eta(self, v: dict):
        e = list(self._dtype[v["fam"]])
        bw = v["bowler"]
        if bw is not None and v["prep"]["spin"].get(bw, 0) > 0:
            e[1] -= 0.4
        if v["fam"] != "TEST" and self._phase(v) == "death":
            e[1] += 0.15
        return e

    def outcome_eta(self, v: dict):
        fam, prep = v["fam"], v["prep"]
        base = self._base[fam, self._phase(v)]
        st, bw = v["striker"], v["bowler"]
        lat = v["latent"]
        nm = prep["n_match"]
        sp = prep["spin"].get(bw, 0) if bw is not None else 0
        pr, pw = _POS.get(prep["pos"].get(st, 11), (0, 0))
        cr, cw = _CAL[fam]
        a_runs, a_wkt = cr + pr + lat[0] + lat[nm], cw + pw + lat[1] + sp * lat[2] + lat[nm + 1]

        sb = v["striker_balls"]
        if fam == "TEST":
            a_runs, a_wkt = (a_runs - 0.3, a_wkt + 0.3) if sb < 10 else (a_runs - 0.1, a_wkt + 0.1) if sb < 30 else \
                (a_runs, a_wkt)
            day = v["est_day"] or 1
            a_wkt += 0.1 * (v["innings"] == 4) + 0.1 * max(0, day - 3) + (0.1 * max(0, day - 2) if sp > 0 else 0)
            if v["ball_age_overs"] < 10 and sp < 0:
                a_wkt += 0.25
            elif v["ball_age_overs"] > 30 and sp > 0:
                a_wkt += 0.1
            if prep["wear"]:
                a_wkt += self._wear(v) * lat[3]
        else:
            if sb < 5:
                a_runs, a_wkt = a_runs - 0.25, a_wkt + 0.2
            elif sb < 15:
                a_runs, a_wkt = a_runs - 0.08, a_wkt + 0.05
            rr = v["runs_required"]
            if rr is not None and v["balls_remaining"]:
                par = 8.0 if fam == "T20" else 5.4
                x = min(1.5, max(-0.6, (6.0 * rr / v["balls_remaining"] - par) / par))
                a_runs, a_wkt = a_runs + 0.45 * x, a_wkt + 0.6 * x
            if v["super_over"]:
                a_runs, a_wkt = a_runs + 0.25, a_wkt + 0.25
        w = v["weather"]
        if w and (w.get("cloud_oktas") or 0) >= 6 and sp < 0:
            a_wkt += 0.1
        if v["bat_home_status"] == "home":
            a_runs += 0.05
        if v["bowl_home_status"] == "home":
            a_wkt += 0.05
        ps = self.players.get(st)
        if ps:
            a_runs, a_wkt = a_runs + ps.get("bat", 0.0), a_wkt + ps.get("bat_wkt", 0.0)
        f = v["striker_form"]
        a_runs, a_wkt = a_runs + 0.12 * f[0], a_wkt + 0.12 * f[1]
        if bw is not None:
            pb = self.players.get(bw)
            if pb:
                a_runs, a_wkt = a_runs + pb.get("bowl", 0.0), a_wkt + pb.get("bowl_wkt", 0.0)
            f = v["bowler_form"]
            a_runs, a_wkt = a_runs + 0.08 * f[0], a_wkt + 0.10 * f[1]
        e = [b + a_runs * s for b, s in zip(base, SCORING)]
        e[6] += a_wkt
        if v["free_hit"]:
            e[4] += 0.3
            e[5] += 0.3
        return e

    def wk_eta(self, v: dict):
        e = list(self._kind[v["fam"]])
        sp = v["prep"]["spin"].get(v["bowler"], 0)
        if sp > 0:
            e[2] += 0.2
            e[3] += 0.7
        else:
            e[3] -= 1.5
        if not v["drs_enabled"]:
            e[2] -= 0.25
        return e

    # --- DRS
    def drs_bat(self, v: dict, kind: int):
        q = (0.10 if kind == 0 else 0.30) + (0.08 if v["reviews_bat"] >= 2 else 0.0)
        return q, (0.40 if kind == 0 else 0.22), (0.0 if kind == 0 else 0.30)

    def drs_field(self, v: dict, cls: int):
        lam = 0.0015 if cls == 0 else 0.003 if cls == 8 else 0.0
        spec = 0.003 if cls == 0 else 0.004 if cls == 8 else 0.0004 if cls == 9 else 0.0008
        return lam, 0.75, spec, 0.25

    # --- empirical tables
    def wide_wkt(self, v: dict):
        sp = v["prep"]["spin"].get(v["bowler"], 0) > 0
        return [1.0, 0.004 if sp else 0.0004, 0.0006]

    def wide_runs(self, v: dict, wkt: int):
        return [[0.90, 0.02, 0.005, 0.002, 0.073], [1.0, 0, 0, 0, 0], [0.7, 0.25, 0.05, 0, 0]][wkt]

    def bye_runs(self, v: dict):
        return [0.62, 0.10, 0.02, 0.255, 0.005]

    def runs5_7(self, v: dict):
        return 0.012, 0.002

    def runout_runs(self, v: dict):
        return [0.6, 0.3, 0.1, 0.0] if v["dtype"] == "wide" else [0.55, 0.32, 0.11, 0.02]

    def runout_who(self, v: dict, runs: int) -> float:
        return 0.5

    def runout_new_on_strike(self, v: dict, who: int, runs: int) -> float:
        return _NEW_ON_STRIKE[who][min(runs, 2)]

    def p_crossed(self, v: dict) -> float:
        return _CROSSED[v["fam"]]

    # --- tactics
    def bowler_utility(self, v: dict, c: dict) -> float:
        u = 0.0 if c["option"] < 5 else -3.5
        if c["part_timer"]:
            u -= 2.0
        k = v["over"]
        if v["fam"] == "TEST":
            sp = v["prep"]["spin"].get(c["id"], 0) > 0
            u += 1.0 - 0.35 * c["spell"] if c["spell"] else 0.0
            if k < 2 or v["ball_age_overs"] < 2:
                u += 1.5 if c["option"] < 2 else 0.0
            if sp:
                u += 0.6 if v["ball_age_overs"] > 20 else -0.8
            return u
        if c["spell"] and c["spell"] < 3:
            u += 0.8
        if k < 2:
            u += 1.5 if c["option"] < 2 else 0.0
        if v["max_balls"] and 4 * v["legal_balls"] >= 3 * v["max_balls"] and c["option"] in (0, 3):
            u += 0.8
        if c["quota_left"] and c["overs_left"]:
            u += 1.5 * c["quota_left"] / c["overs_left"]
        return u

    def declare_hazard(self, v: dict) -> float:
        lead, k, left = v["lead"], v["innings"], v["exp_overs_left"]
        if k == 3:
            need = 220 + 1.4 * min(left, 150)
            return _sigmoid(0.03 * (lead - need) + (0.3 if v["last_over_wkt"] else 0.0))
        if lead < 250:
            return 0.0
        return _sigmoid(-14 + 0.018 * v["runs"] + 0.3 * v["wkts"] - 0.01 * max(0.0, left - 300))


    def follow_on_prob(self, v: dict) -> float:
        bowled = v["prev_innings"][-1][3] / 6 if v["prev_innings"] else 0.0
        return _sigmoid(0.6 + 0.01 * (v["lead"] - 200) - 0.01 * max(0.0, bowled - 110))

    def new_ball_prob(self, v: dict) -> float:
        return 0.85

    # --- time and rain
    def interruption_schedule(self, sc: dict, from_ball: int, u):
        w = sc.get("weather") or {}
        risk = w.get("rain_risk")
        risk = _RAIN[sc["fam"]] if risk is None else risk
        n = (sc.get("rules") or {}).get("max_balls") or default_rules(sc["fam"])["max_balls"]
        out = []
        for j, cut in enumerate((risk, risk / 3)):
            if u[0 + 5 * j] >= cut:
                break
            if from_ball == 0 and u[1 + 5 * j] < 0.35:
                start = 0
            else:
                start = from_ball + int(u[2 + 5 * j] * max(1, 2 * n - from_ball))
            out.append({"start": start, "lost": 6 * (1 + int(u[3 + 5 * j] * 0.6 * n / 6))})
        return sorted(out, key=lambda x: x["start"])

    def _day(self, sc: dict) -> tuple[int, float]:
        r = self.rules(sc)
        w = sc.get("weather") or {}
        risk = w.get("rain_risk")
        return 6 * r["test_overs_per_day"], 0.8 if risk is None else 1.0 - risk

    def day_availability(self, sc: dict, day: int, u: float) -> int:
        full, p_full = self._day(sc)
        return full if u < p_full else int(full * (u - p_full) / (1.0 - p_full))

    def day_availability_mean(self, sc: dict, day: int) -> float:
        full, p_full = self._day(sc)
        return full * (p_full + (1.0 - p_full) / 2)

    def _z(self, sc: dict, overs: float, wkts: int) -> float:
        z0, b = _RES[sc["fam"]]
        return z0 * (1 - wkts / 10) ** 1.3 * (1 - math.exp(-b * (1 + 0.25 * wkts) * overs))

    def resource(self, sc: dict, balls_remaining: int, wkts: int) -> int:
        if wkts >= 10 or balls_remaining <= 0:
            return 0
        n = self.rules(sc)["max_balls"]
        return math.floor(1000 * self._z(sc, balls_remaining / 6, wkts) / self._z(sc, n / 6, 0) + 0.5)

    def resource_G(self, sc: dict) -> float:
        return self._z(sc, self.rules(sc)["max_balls"] / 6, 0)


# ---------------------------------------------------------------- scenario and state schema

def validate_scenario(sc: dict) -> dict:
    """Check a section 9.1 scenario and return a normalized deep copy with defaults filled.

    Optional extensions beyond 9.1: team "bowlers" (bowling options, in preference order; default the
    bowling XI minus the keeper), "keeper", "absent" (ids who will not bat); scenario "rules" (engine-rule
    overrides), "scheduled_days" (Tests), "draw_player_uncertainty" (default true)."""
    sc = copy.deepcopy(sc)
    errs = []
    if sc.get("fam") not in FAMS:
        errs.append(f"fam must be one of {FAMS}")
    sc.setdefault("gender", "male")
    sc.setdefault("competition_id", None)
    sc["date"] = str(sc.get("date") or "2025-06-01")[:10]
    sc.setdefault("venue_id", None)
    sc["neutral"] = bool(sc.get("neutral", False))
    sc.setdefault("start_slot", "day")
    teams = sc.get("teams")
    if not isinstance(teams, list) or len(teams) != 2:
        raise ValueError("scenario needs two teams")
    seen = set()
    for t, team in enumerate(teams):
        order = team.get("batting_order") or []
        if len(order) < 2 or len(set(order)) != len(order) or len(order) > 11:
            errs.append(f"team {t}: batting_order needs 2..11 distinct ids")
        team.setdefault("name", f"team{t}")
        team["bowling_xi"] = list(team.get("bowling_xi") or order)
        team.setdefault("keeper", None)
        team["absent"] = list(team.get("absent") or [])
        team["home"] = bool(team.get("home", False))
        ids = set(order) | set(team["bowling_xi"]) | set(team.get("bowlers") or [])
        if ids & seen:
            errs.append(f"team {t}: ids shared with the other team: {sorted(ids & seen)}")
        seen |= ids
        bad = set(team["absent"]) - set(order)
        if bad:
            errs.append(f"team {t}: absent ids not in batting_order: {sorted(bad)}")
        if team.get("bowlers") is not None and not team["bowlers"]:
            errs.append(f"team {t}: bowlers list is empty")
    toss = sc.setdefault("toss", None)
    if toss is not None and (toss.get("winner") not in (0, 1) or toss.get("decision") not in ("bat", "field")):
        errs.append("toss must be null or {winner: 0|1, decision: bat|field}")
    um = sc.setdefault("umpires", None)
    if um is not None and len(um) != 2:
        errs.append("umpires must be null or two ids")
    drs = dict(sc.get("drs") or {})
    for k in ("enabled", "reviews_per_innings", "umpires_call_retains"):
        drs.setdefault(k, None)
    drs["accuracy_mult"] = float(drs.get("accuracy_mult") or 1.0)
    drs["ucall_mult"] = float(drs.get("ucall_mult") or 1.0)
    sc["drs"] = drs
    sc.setdefault("weather", None)
    pitch = {"known": False, "runs_sd": 0.0, "wkt_sd": 0.0, "spin_sd": 0.0, "wear_sd": 0.0}
    pitch.update(sc.get("pitch") or {})
    sc["pitch"] = pitch
    sc["player_form"] = dict(sc.get("player_form") or {})
    for pid, f in sc["player_form"].items():
        if pid not in seen:
            errs.append(f"player_form for unknown id {pid}")
        for k in f:
            if k not in ("bat_runs_sd", "bat_wkt_sd", "bowl_runs_sd", "bowl_wkt_sd"):
                errs.append(f"player_form[{pid}]: unknown key {k}")
    sc.setdefault("state", None)
    sc.setdefault("n_sims", 4000 if sc.get("fam") == "TEST" else 10000)
    sc.setdefault("seed", 0)
    sc["sensitivity"] = bool(sc.get("sensitivity", False))
    sc.setdefault("rules", None)
    sc.setdefault("scheduled_days", None)
    sc["draw_player_uncertainty"] = bool(sc.get("draw_player_uncertainty", True))
    if errs:
        raise ValueError("; ".join(errs))
    return sc


STATE_CUR_KEYS = ("number", "team", "runs", "wkts", "legal_balls", "max_balls", "target", "target_timing",
                  "striker", "nonstriker", "batters", "unavailable", "next", "bowlers", "over_bowlers", "bowler",
                  "last_bowler", "ball_in_over", "free_hit", "reviews", "fail_reviews", "umpire_offset",
                  "partnership", "ball_age_overs", "second_new_ball", "last_over_runs", "last_over_wkt",
                  "over_runs", "wkt_this_over", "over_scores")


def state_schema_errors(state: dict, sc: dict) -> list[str]:
    """Structural problems of a canonical (fully specified) section 9.3 state; [] when well formed."""
    errs = []
    for k in ("innings_team", "done", "cur"):
        if k not in state:
            errs.append(f"state missing {k}")
    if errs:
        return errs
    cur = state["cur"]
    for k in STATE_CUR_KEYS:
        if k not in cur:
            errs.append(f"state.cur missing {k}")
    for i, inn in enumerate(state["done"]):
        for k in ("team", "runs", "wkts", "legal_balls", "max_balls", "target", "end"):
            if k not in inn:
                errs.append(f"state.done[{i}] missing {k}")
    if sc["fam"] == "TEST" and not state.get("clock"):
        errs.append("Tests need state.clock {used, changeovers, avail}")
    if sc["fam"] != "TEST" and "resources" not in state:
        errs.append("limited overs need state.resources [R1, R2] (null entries allowed)")
    return errs
