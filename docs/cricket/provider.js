// Probability providers for the JavaScript cricket engine: the Provider interface, the hand-set
// StubProvider (bit-for-bit twin of beating/cricket/provider.py), rules defaults and the scenario/state
// schema checks shared with engine.js.
//
// Method. engine.js owns match flow, the rules and random-number consumption; a provider owns every
// probability (plan section 9.6). Every provider method receives either the scenario or the *view*: one
// plain object per Match, refreshed in place before each call, with exactly the keys of VIEW_KEYS (the
// same names and meanings as beating/cricket/provider.py) plus three JS-only integer keys
// striker_idx, nonstriker_idx and bowler_idx (index into the slots array passed to prepare, -1 for
// None) so a provider can use typed per-player tables instead of id lookups. A provider treats the view
// as read-only and never keeps references to it or to anything in it (striker_form, latent, to_come
// and prev_innings are engine-owned arrays that change between calls).
//
// Return conventions (no per-ball allocation): methods returning several floats write every entry of the
// `out` Float64Array the engine passes and return it; the engine may modify `out` afterwards. Equal
// inputs must give bitwise-equal outputs (the engine memoizes categorical sums on repeated eta vectors).
//   dtype_eta(v, out3)            3 log-odds: legal, wide, noball
//   outcome_eta(v, out9)          9 unmasked log-odds (OUTCOMES); the engine adds MASK_OFFSET to class 6
//   wk_eta(v, out5)               5 log-odds (KINDS) for an on-field bowler-credited out
//   drs_bat(v, kind, out3)        q_bat, p_overturn_bat, p_ucall_bat (kind 0 caught, 2 lbw)
//   drs_field(v, cls, out4)       lambda_field, lbw share of missed outs, r_spec, ucall share (cls 9 = wide)
//   wide_wkt(v, out3)             weights none, stumped, run_out
//   wide_runs(v, wkt, out5)       weights for wide runs 1..5 (5 = boundary) given the wide wicket
//   bye_runs(v, out5)             weights for byes/leg-byes 1..5
//   runs5_7(v, out2)              P(5 | four), P(7 | six)
//   runout_runs(v, out4)          weights for runs completed 0..3
//   runout_who(v, runs) -> p      P(striker is the victim)
//   runout_new_on_strike(v, who, runs) -> p ;  p_crossed(v) -> p
//   bowler_utility(v, cand) -> u  cand: {id, idx, option, overs, balls, runs, wkts, spell, quota_left,
//                                 overs_left, part_timer, opened} (engine-owned object, reused)
//   toss_bat_prob, declare_hazard, follow_on_prob, new_ball_prob (v) -> p
//   prepare(scenario, slots) -> prep (exposed as view.prep); rules(scenario) -> RULE_KEYS dict
//   latent_spec(scenario) -> {match: [{name, sd, pitch}] (<= 4), innings: [{name, sd}] (<= 2)}
//   latent_directions(v) -> d x 9 arrays; latent_loglik(v, cls, idx, offset) -> [ll, grad, hess]
//   interruption_schedule(scenario, from_ball, u16) -> [{start, lost}] sorted by start
//   day_availability(scenario, day, u) -> int balls; day_availability_mean(scenario, day) -> float
//   resource(scenario, balls_remaining, wkts) -> int tenths of a percent; resource_G(scenario) -> float
// Weights need not sum to one; latent values are in eta units; form shifts are in player-SD units.
//
// Arithmetic follows the Python twin operation by operation (same association order; Python's
// compensated builtin sum() is mirrored by pySum). Math.exp/log/pow in V8 and glibc differ in the last
// bit for about 10% of arguments, so probabilities agree to about 1e-16 relative and a draw can differ
// only when u * cum_last lies within that of a class boundary (allowed by plan 9.6).
//
// Limits. Only the stub exists; createProvider(bundle) throws for a real parameter bundle until the
// bundle-interpreting provider is written against this interface.

export const FAMS = ['T20', 'ODI', 'TEST'];
export const OUTCOMES = ['dot', 'one', 'two', 'three', 'four', 'six', 'out', 'run_out', 'byes'];
export const DTYPES = ['legal', 'wide', 'noball'];
export const KINDS = ['caught', 'bowled', 'lbw', 'stumped', 'other'];
export const WIDE_WKTS = ['none', 'stumped', 'run_out'];
export const SCORING = [0.0, 1 / 6.5, 2 / 6.5, 3 / 6.5, 4 / 6.5, 6 / 6.5, 0.0, 0.0, 1 / 6.5];
export const WICKET = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0];
export const FOLLOW_ON_TABLE = [[5, 200], [3, 150], [2, 100], [1, 75]];
export const MASK_OFFSET = -30.0;

export const VIEW_KEYS = {
  fam: 'T20 | ODI | TEST', gender: 'male | female', competition_id: 'competition id or null',
  date: 'match date YYYY-MM-DD', venue_id: 'venue id or null', neutral: 'bool',
  start_slot: 'day | day_night | night | unknown', weather: 'scenario weather object or null',
  umpires: '[umpire1, umpire2] or null', rules: 'engine rules (RULE_KEYS)', drs_enabled: 'bool',
  sched_balls: 'scheduled innings length in legal balls or null', scheduled_days: 'Tests: days, else null',
  teams: '[team0 name, team1 name]', home: '[team0 home, team1 home]', prep: 'Provider.prepare result',
  toss_winner: '0 | 1 | null', innings: 'main innings 1..4 (super overs 0)', super_over: '0, or k-th super over',
  so_innings: '1 | 2 in a super over, else 0', bat_team: 'int', bowl_team: 'int',
  bat_home_status: 'home | away | neutral', bowl_home_status: 'home | away | neutral',
  target_timing: 'original | pre_inn2 | revised | null', followed_on: 'bool',
  prev_innings: '[[team, runs, wkts, legal_balls, end], ...] completed main innings',
  umpire_offset: '0 | 1', latent: 'match latents then this innings latents (Float64Array)',
  legal_balls: 'int', ball_in_over: 'int', over: 'completed overs', max_balls: 'int or null',
  balls_remaining: 'int or null', runs: 'int', wkts: 'int', unavailable: 'wickets + unavailable batters',
  target: 'int or null', runs_required: 'int or null', striker: 'id (null = average batter)',
  nonstriker: 'id', bowler: 'id or null', striker_runs: 'int', striker_balls: 'legal + no-balls faced',
  nonstriker_runs: 'int', nonstriker_balls: 'int', striker_arrival: 'int', nonstriker_arrival: 'int',
  striker_pos: '1-based batting position', nonstriker_pos: 'int', bowler_balls: 'int', bowler_runs: 'int',
  bowler_wkts: 'int', bowler_overs: 'int', bowler_spell: 'int', bowler_part_timer: 'bool',
  partnership_runs: 'int', partnership_balls: 'int', free_hit: 'bool', pp_window: 'pp1 | pp2 | pp3 | none',
  field_restr: 'max fielders outside or null', reviews_bat: 'int', reviews_bowl: 'int',
  bat_fail_reviews: 'int', bowl_fail_reviews: 'int', ball_age_overs: 'int', second_new_ball: 'bool',
  innings_overs: 'int', match_legal_balls: 'int', clock_used: 'Tests int', est_day: 'Tests int',
  overs_into_day: 'Tests int', exp_overs_left: 'Tests float', lead: 'int',
  striker_form: '[bat_runs, bat_wkt] player-SD units', nonstriker_form: '[bat_runs, bat_wkt]',
  bowler_form: '[bowl_runs, bowl_wkt] or null', bowl_end_umpire: 'id or null',
  to_come: 'ids still to bat, in order', last_over_runs: 'int', last_over_wkt: 'bool',
  dtype: 'legal | wide | noball while later models are asked, else null',
};

export const RULE_KEYS = [
  'balls_per_over', 'max_balls', 'min_balls_for_result', 'free_hit', 'p_free_hit_given_nb', 'noball_runs',
  'caught_crossing_counts', 'drs_enabled', 'reviews_per_innings', 'umpires_call_retains',
  'review_topup_after_80', 'tie_break', 'fielders_outside', 'pp_mandatory', 'test_days',
  'test_overs_per_day', 'follow_on_lead', 'new_ball_after_overs', 'balls_in_use', 'quota_rule', 'pp_reduced',
];

// ---------------------------------------------------------------- Python semantics helpers

// Python truthiness (empty arrays and objects are false).
export function pyBool(x) {
  if (x === null || x === undefined || x === false || x === 0 || x === '' || Number.isNaN(x)) return false;
  if (Array.isArray(x) || ArrayBuffer.isView(x)) return x.length > 0;
  if (typeof x === 'object') return Object.keys(x).length > 0;
  return true;
}
export const pyOr = (a, b) => (pyBool(a) ? a : b);
export const has = (o, k) => o !== null && o !== undefined && Object.prototype.hasOwnProperty.call(o, k);
export const get = (o, k, d = null) => (has(o, k) ? o[k] : d);
export function setdefault(o, k, d) {
  if (!has(o, k)) o[k] = d;
  return o[k];
}
export const deepcopy = (x) => (x === null || x === undefined ? x : structuredClone(x));

// CPython 3.12 builtin sum() of floats from the int start 0: Neumaier compensated summation.
export function pySum(a, n = a.length) {
  if (n === 0) return 0;
  let f = 0 + a[0];
  let c = 0.0;
  for (let i = 1; i < n; i++) {
    const x = a[i];
    const t = f + x;
    if (Math.abs(f) >= Math.abs(x)) c += (f - t) + x;
    else c += (x - t) + f;
    f = t;
  }
  if (c !== 0 && Number.isFinite(c)) f += c;
  return f;
}

// Python repr for the strings, numbers, booleans, null and arrays used in messages.
export function pyRepr(x) {
  if (x === null || x === undefined) return 'None';
  if (x === true) return 'True';
  if (x === false) return 'False';
  if (typeof x === 'string') return x.includes("'") && !x.includes('"') ? `"${x}"` : `'${x.replace(/'/g, "\\'")}'`;
  if (Array.isArray(x)) return `[${x.map(pyRepr).join(', ')}]`;
  return String(x);
}

// ---------------------------------------------------------------- rules

export function defaultRules(fam, gender = 'male', date = '2025-06-01') {
  date = String(date).slice(0, 10);
  const r = {
    balls_per_over: 6, max_balls: null, min_balls_for_result: null, free_hit: 'none', p_free_hit_given_nb: 1.0,
    noball_runs: 1, caught_crossing_counts: date < '2022-10-01', drs_enabled: date >= '2008-07-01',
    reviews_per_innings: 2, umpires_call_retains: date >= '2017-10-01', review_topup_after_80: false,
    tie_break: 'none', fielders_outside: null, pp_mandatory: null, test_days: null, test_overs_per_day: null,
    follow_on_lead: null, new_ball_after_overs: null, balls_in_use: 'one', quota_rule: 'fifth_min2',
    pp_reduced: null,
  };
  if (fam === 'T20' || fam === 'ODI') {
    r.free_hit = date >= '2015-07-05' ? 'all_noballs' : 'front_foot';
    r.p_free_hit_given_nb = date >= '2015-07-05' ? 1.0 : 0.75;
  }
  if (fam === 'T20') {
    Object.assign(r, {
      max_balls: 120, min_balls_for_result: 30, pp_mandatory: [[1, 6]], fielders_outside: [[1, 6, 2], [7, 20, 5]],
      reviews_per_innings: date >= '2020-08-28' ? 2 : 1,
      tie_break: date >= '2019-10-14' ? 'so_repeat' : date >= '2008-12-26' ? 'so_boundary_count' : 'bowl_out',
    });
  } else if (fam === 'ODI') {
    Object.assign(r, {
      max_balls: 300, min_balls_for_result: 120, pp_mandatory: [[1, 10], [11, 40], [41, 50]],
      fielders_outside: [[1, 10, 2], [11, 40, 4], [41, 50, 5]], reviews_per_innings: date >= '2020-08-01' ? 2 : 1,
      tie_break: gender === 'male' ? 'none' : 'so_repeat',
      balls_in_use: date >= '2011-10-01' && date < '2025-07-01' ? 'two_new_balls' : 'one',
    });
  } else if (fam === 'TEST') {
    Object.assign(r, {
      test_days: gender === 'male' ? 5 : 4, test_overs_per_day: gender === 'male' ? 90 : 100,
      follow_on_lead: deepcopy(FOLLOW_ON_TABLE), new_ball_after_overs: 80,
      reviews_per_innings: date >= '2020-07-16' ? 3 : 2,
      review_topup_after_80: date >= '2013-10-01' && date < '2017-10-01',
    });
  } else {
    throw new Error(`unsupported fam ${pyRepr(fam)}`);
  }
  return r;
}

// Map a rules.rules_for result (plan section 5 names) to the engine rules dict (provider.engine_rules).
export function engineRules(raw, fam) {
  const r = defaultRules(fam);
  const pp = get(raw, 'pp_windows'), fo = get(raw, 'follow_on_lead_by_days');
  const two = get(raw, 'two_new_balls'), until = get(raw, 'two_new_balls_until_over');
  const fh = pyOr(get(raw, 'free_hit'), 'none');
  const pfh = get(raw, 'p_free_hit_given_nb');
  Object.assign(r, {
    balls_per_over: pyOr(get(raw, 'balls_per_over'), 6), max_balls: get(raw, 'balls_per_innings'),
    min_balls_for_result: get(raw, 'min_balls_for_result'), free_hit: fh,
    p_free_hit_given_nb: pfh !== null ? Number(pfh) : fh === 'none' ? 0.0 : 1.0,
    noball_runs: pyOr(get(raw, 'noball_penalty_runs'), 1),
    caught_crossing_counts: pyBool(get(raw, 'caught_crossing_counts')), drs_enabled: pyBool(get(raw, 'drs_allowed')),
    reviews_per_innings: pyOr(get(raw, 'reviews_per_innings'), 0),
    umpires_call_retains: pyBool(get(raw, 'umpires_call_retains_review')),
    review_topup_after_80: pyBool(get(raw, 'review_topup_after_80')), tie_break: pyOr(get(raw, 'tie_break'), 'none'),
    fielders_outside: get(raw, 'field_restr'),
    pp_mandatory: pp !== null && typeof pp === 'object' && !Array.isArray(pp) ? get(pp, 'mandatory') : null,
    test_days: get(raw, 'scheduled_days'), test_overs_per_day: get(raw, 'test_overs_per_day'),
    follow_on_lead: pyBool(fo) ? Object.entries(fo).map(([d, x]) => [Math.trunc(Number(d)), Math.trunc(Number(x))])
      .sort((a, b) => b[0] - a[0] || b[1] - a[1]) : null,
    new_ball_after_overs: get(raw, 'new_ball_after_overs'),
    balls_in_use: pyBool(two) && pyBool(until) ? 'two_balls_until_34' : pyBool(two) ? 'two_new_balls' : 'one',
    quota_rule: pyOr(get(raw, 'reduced_quota_rule'), 'fifth_min2'), pp_reduced: get(raw, 'pp_windows_reduced'),
  });
  if (fam === 'TEST') r.max_balls = r.min_balls_for_result = null;
  return r;
}

// ---------------------------------------------------------------- latent log-likelihood helper

// latent_loglik for an outcome_eta affine in the latents with slopes latent_directions (sums over
// classes 0..8 in order, exactly as provider.affine_latent_loglik).
export function affineLatentLoglik(P, view, cls, idx, offset) {
  const eta = Array.from(P.outcome_eta(view, new Float64Array(9)), (e, k) => e + offset[k]);
  const D = P.latent_directions(view);
  let mx = -Infinity;
  for (const e of eta) if (e > mx) mx = e;
  const ex = eta.map((e) => Math.exp(e - mx));
  let s = 0.0;
  for (const x of ex) s += x;
  const p = ex.map((x) => x / s);
  const ll = eta[cls] - mx - Math.log(s);
  const rows = idx.map((j) => D[j]);
  const md = rows.map((r) => {
    let a = 0.0;
    for (let k = 0; k < 9; k++) a += p[k] * r[k];
    return a;
  });
  const g = rows.map((r, i) => r[cls] - md[i]);
  const h = rows.map((ri, i) => rows.map((rj, j) => {
    let a = 0.0;
    for (let k = 0; k < 9; k++) a += p[k] * ri[k] * rj[k];
    return -(a - md[i] * md[j]);
  }));
  return [ll, g, h];
}

// ---------------------------------------------------------------- stub provider

const etaOf = (p) => p.map((x) => Math.log(x / p[0]));
const sigmoid = (x) => 1.0 / (1.0 + Math.exp(-x));

const BASE = {
  T20: [0.35, 0.37, 0.07, 0.004, 0.105, 0.048, 0.04, 0.005, 0.016],
  ODI: [0.50, 0.33, 0.06, 0.006, 0.07, 0.014, 0.0215, 0.004, 0.015],
  TEST: [0.71, 0.17, 0.04, 0.008, 0.052, 0.004, 0.0145, 0.0015, 0.012],
};
const PHASES = ['pp', 'mid', 'death', 'test'];
const PHASE_ADD = {
  pp: [0, -0.15, -0.15, 0, 0.30, 0.05, -0.10, 0, 0], mid: [0, 0.08, 0.05, 0, -0.15, -0.10, -0.12, 0, 0],
  death: [0, 0.0, 0.35, 0.2, 0.25, 0.65, 0.55, 0.4, 0], test: [0, 0, 0, 0, 0, 0, 0, 0, 0],
};
const POS = {
  1: [0, 0], 2: [0, 0], 3: [0, 0], 4: [0, 0], 5: [0, 0], 6: [-0.05, 0.1], 7: [-0.15, 0.25], 8: [-0.35, 0.5],
  9: [-0.55, 0.75], 10: [-0.75, 0.95], 11: [-0.9, 1.1],
};
const DTYPE = { T20: [0.040, 0.0055], ODI: [0.033, 0.005], TEST: [0.010, 0.012] };
const KIND = { T20: [0.64, 0.17, 0.12, 0.06, 0.01], ODI: [0.60, 0.19, 0.14, 0.06, 0.01], TEST: [0.52, 0.20, 0.22, 0.04, 0.02] };
const TOSS = { T20: 0.38, ODI: 0.55, TEST: 0.75 };
const CROSSED = { T20: 0.47, ODI: 0.27, TEST: 0.06 };
const RAIN = { T20: 0.06, ODI: 0.12, TEST: 0.25 };
const RES = { T20: [330.0, 0.040], ODI: [300.0, 0.030] };
const NEW_ON_STRIKE = [[0.40, 0.85, 0.45], [0.55, 0.27, 0.50]];
const CAL = { T20: [0.16, 0.0], ODI: [0.22, -0.2], TEST: [0.0, -0.47] };
const FAM_I = { T20: 0, ODI: 1, TEST: 2 };
const WIDE_RUNS = [[0.90, 0.02, 0.005, 0.002, 0.073], [1.0, 0, 0, 0, 0], [0.7, 0.25, 0.05, 0, 0]];
const BYE_RUNS = [0.62, 0.10, 0.02, 0.255, 0.005];
const RO_RUNS_WIDE = [0.6, 0.3, 0.1, 0.0], RO_RUNS = [0.55, 0.32, 0.11, 0.02];

export class StubProvider {
  // `players` maps id -> optional overrides: bat, bat_wkt, bowl, bowl_wkt (eta shifts), spin (bool).
  constructor(players = null) {
    this.players = players || {};
    this._base = new Float64Array(3 * 4 * 9);
    for (const fam of FAMS) {
      const p = BASE[fam], S = pySum(p);
      const e = etaOf(p.map((x) => x / S));
      PHASES.forEach((ph, j) => {
        for (let k = 0; k < 9; k++) this._base[(FAM_I[fam] * 4 + j) * 9 + k] = e[k] + PHASE_ADD[ph][k];
      });
    }
    this._dtype = new Float64Array(9);
    this._kind = new Float64Array(15);
    for (const f of FAMS) {
      const [w, n] = DTYPE[f], i = FAM_I[f];
      this._dtype.set([0.0, Math.log(w / (1 - w - n)), Math.log(n / (1 - w - n))], 3 * i);
      this._kind.set(etaOf(KIND[f]), 5 * i);
    }
    this._rulesCache = new WeakMap(); this._schedN = new WeakMap();
  }

  // --- statics
  prepare(scenario, slots = null) {
    const pos = new Map(), spin = new Map(), teamOf = new Map();
    scenario.teams.forEach((team, t) => {
      team.batting_order.forEach((pid, i) => { pos.set(pid, i + 1); teamOf.set(pid, t); });
      for (const pid of new Set([...(team.bowling_xi || []), ...(team.bowlers || [])])) {
        if (!pos.has(pid)) pos.set(pid, 11);
        if (!teamOf.has(pid)) teamOf.set(pid, t);
      }
    });
    for (const [pid, p] of pos) {
      const over = get(this.players, pid, {}) || {};
      spin.set(pid, has(over, 'spin') ? (over.spin ? 1 : -1) : (p >= 10 ? 1 : p >= 7 ? -1 : 1));
    }
    const names = this.latent_spec(scenario).match.map((x) => x.name);
    const fi = FAM_I[scenario.fam];
    const prep = { pos, spin, team_of: teamOf, n_match: names.length, wear: names.includes('m_wear'), famI: fi,
      isTest: scenario.fam === 'TEST', isT20: scenario.fam === 'T20', cal: CAL[scenario.fam], crossed: CROSSED[scenario.fam] };
    const w = get(scenario, 'weather');
    prep.cloudy = pyBool(w) && pyOr(get(w, 'cloud_oktas'), 0) >= 6;   // static: v.weather is scenario.weather
    // per-slot tables (JS only): spin, position adjustments and player overrides by slot index
    slots = slots || [...pos.keys()];
    const n = slots.length;
    prep.slotSpin = new Int8Array(n);
    prep.posRuns = new Float64Array(n + 1);
    prep.posWkt = new Float64Array(n + 1);
    prep.batOver = new Array(n + 1).fill(null);
    prep.bowlOver = new Array(n + 1).fill(null);
    const fill = (i, pid) => {
      const pa = POS[pid === null ? 11 : (pos.has(pid) ? pos.get(pid) : 11)] || [0, 0];
      prep.posRuns[i] = pa[0];
      prep.posWkt[i] = pa[1];
      const ps = pid === null ? null : get(this.players, pid);
      if (pyBool(ps)) {
        prep.batOver[i] = [get(ps, 'bat', 0.0), get(ps, 'bat_wkt', 0.0)];
        prep.bowlOver[i] = [get(ps, 'bowl', 0.0), get(ps, 'bowl_wkt', 0.0)];
      }
    };
    slots.forEach((pid, i) => { prep.slotSpin[i] = spin.has(pid) ? spin.get(pid) : 0; fill(i, pid); });
    fill(n, null);   // slot index -1 (None) maps to entry n
    prep.nSlots = n;
    return prep;
  }

  rules(scenario) {
    const r = defaultRules(scenario.fam, get(scenario, 'gender', 'male'), pyOr(get(scenario, 'date'), '2025-06-01'));
    Object.assign(r, pyOr(get(scenario, 'rules'), {}));
    return r;
  }

  _rules(sc) {
    let r = this._rulesCache.get(sc);
    if (r === undefined) { r = this.rules(sc); this._rulesCache.set(sc, r); }
    return r;
  }

  latent_spec(scenario) {
    const m = [{ name: 'm_runs', sd: 0.22, pitch: 'runs_sd' }, { name: 'm_wkt', sd: 0.14, pitch: 'wkt_sd' },
      { name: 'm_spin', sd: 0.12, pitch: 'spin_sd' }];
    if (scenario.fam === 'TEST') m.push({ name: 'm_wear', sd: 0.15, pitch: 'wear_sd' });
    return { match: m, innings: [{ name: 'i_runs', sd: 0.14 }, { name: 'i_wkt', sd: 0.10 }] };
  }

  // --- delivery models
  _wear(v) {
    const d = v.scheduled_days;
    return !pyBool(d) || v.est_day === null ? 0.0 : (v.est_day - 1) / (d - 1);
  }

  _spinOf(v, idx) {
    return idx >= 0 ? v.prep.slotSpin[idx] : 0;
  }

  latent_directions(v) {
    const sp = v.bowler !== null ? this._spinOf(v, v.bowler_idx) : 0;
    const rows = [SCORING, WICKET, WICKET.map((x) => sp * x)];
    if (v.prep.wear) {
      const w = this._wear(v);
      rows.push(WICKET.map((x) => w * x));
    }
    return [...rows, SCORING, WICKET].map((r) => Array.from(r));
  }

  latent_loglik(v, cls, idx, offset) {
    return affineLatentLoglik(this, v, cls, idx, offset);
  }

  _phase(v) {   // 0 pp, 1 mid, 2 death, 3 test
    const prep = v.prep;
    if (prep.isTest) return 3;
    if (v.super_over) return 2;
    const n = v.max_balls, b = v.legal_balls;
    if (prep.isT20) return 10 * b < 3 * n ? 0 : 4 * b >= 3 * n ? 2 : 1;
    return 5 * b < n ? 0 : 5 * b >= 4 * n ? 2 : 1;
  }

  toss_bat_prob(v) {
    const p = TOSS[v.fam];
    return v.start_slot === 'night' && v.fam !== 'TEST' ? p - 0.12 : p;
  }

  dtype_eta(v, out) {
    const e = this._dtype, o = 3 * v.prep.famI;
    out[0] = e[o]; out[1] = e[o + 1]; out[2] = e[o + 2];
    if (v.bowler !== null && this._spinOf(v, v.bowler_idx) > 0) out[1] -= 0.4;
    if (!v.prep.isTest && this._phase(v) === 2) out[1] += 0.15;
    return out;
  }

  outcome_eta(v, e) {
    const prep = v.prep;
    const b0 = (prep.famI * 4 + this._phase(v)) * 9;
    const base = this._base;
    const bw = v.bowler, lat = v.latent, nm = prep.n_match;
    const si = v.striker_idx < 0 ? prep.nSlots : v.striker_idx;
    const sp = bw !== null ? this._spinOf(v, v.bowler_idx) : 0;
    const pr = prep.posRuns[si], pw = prep.posWkt[si];
    const cal = prep.cal;
    let aRuns = cal[0] + pr + lat[0] + lat[nm];
    let aWkt = cal[1] + pw + lat[1] + sp * lat[2] + lat[nm + 1];
    const sb = v.striker_balls;
    if (prep.isTest) {
      if (sb < 10) { aRuns = aRuns - 0.3; aWkt = aWkt + 0.3; } else if (sb < 30) { aRuns = aRuns - 0.1; aWkt = aWkt + 0.1; }
      const day = pyOr(v.est_day, 1);
      aWkt += 0.1 * (v.innings === 4 ? 1 : 0) + 0.1 * Math.max(0, day - 3) + (sp > 0 ? 0.1 * Math.max(0, day - 2) : 0);
      if (v.ball_age_overs < 10 && sp < 0) aWkt += 0.25;
      else if (v.ball_age_overs > 30 && sp > 0) aWkt += 0.1;
      if (prep.wear) aWkt += this._wear(v) * lat[3];
    } else {
      if (sb < 5) { aRuns = aRuns - 0.25; aWkt = aWkt + 0.2; } else if (sb < 15) { aRuns = aRuns - 0.08; aWkt = aWkt + 0.05; }
      const rr = v.runs_required;
      if (rr !== null && v.balls_remaining) {
        const par = prep.isT20 ? 8.0 : 5.4;
        const x = Math.min(1.5, Math.max(-0.6, (6.0 * rr / v.balls_remaining - par) / par));
        aRuns = aRuns + 0.45 * x;
        aWkt = aWkt + 0.6 * x;
      }
      if (v.super_over) { aRuns = aRuns + 0.25; aWkt = aWkt + 0.25; }
    }
    if (prep.cloudy && sp < 0) aWkt += 0.1;
    if (v.bat_home_status === 'home') aRuns += 0.05;
    if (v.bowl_home_status === 'home') aWkt += 0.05;
    const ps = prep.batOver[si];
    if (ps !== null) { aRuns = aRuns + ps[0]; aWkt = aWkt + ps[1]; }
    let f = v.striker_form;
    aRuns = aRuns + 0.12 * f[0];
    aWkt = aWkt + 0.12 * f[1];
    if (bw !== null) {
      const pb = prep.bowlOver[v.bowler_idx];
      if (pb !== null) { aRuns = aRuns + pb[0]; aWkt = aWkt + pb[1]; }
      f = v.bowler_form;
      aRuns = aRuns + 0.08 * f[0];
      aWkt = aWkt + 0.10 * f[1];
    }
    for (let k = 0; k < 9; k++) e[k] = base[b0 + k] + aRuns * SCORING[k];
    e[6] += aWkt;
    if (v.free_hit) { e[4] += 0.3; e[5] += 0.3; }
    return e;
  }

  wk_eta(v, out) {
    const e = this._kind, o = 5 * v.prep.famI;
    for (let k = 0; k < 5; k++) out[k] = e[o + k];
    const sp = this._spinOf(v, v.bowler === null ? -1 : v.bowler_idx);
    if (sp > 0) { out[2] += 0.2; out[3] += 0.7; } else out[3] -= 1.5;
    if (!v.drs_enabled) out[2] -= 0.25;
    return out;
  }

  // --- DRS
  drs_bat(v, kind, out) {
    out[0] = (kind === 0 ? 0.10 : 0.30) + (v.reviews_bat >= 2 ? 0.08 : 0.0);
    out[1] = kind === 0 ? 0.40 : 0.22;
    out[2] = kind === 0 ? 0.0 : 0.30;
    return out;
  }

  drs_field(v, cls, out) {
    out[0] = cls === 0 ? 0.0015 : cls === 8 ? 0.003 : 0.0;
    out[1] = 0.75;
    out[2] = cls === 0 ? 0.003 : cls === 8 ? 0.004 : cls === 9 ? 0.0004 : 0.0008;
    out[3] = 0.25;
    return out;
  }

  // --- empirical tables
  wide_wkt(v, out) {
    const sp = this._spinOf(v, v.bowler === null ? -1 : v.bowler_idx) > 0;
    out[0] = 1.0; out[1] = sp ? 0.004 : 0.0004; out[2] = 0.0006;
    return out;
  }

  wide_runs(v, wkt, out) {
    const w = WIDE_RUNS[wkt];
    for (let k = 0; k < 5; k++) out[k] = w[k];
    return out;
  }

  bye_runs(v, out) {
    for (let k = 0; k < 5; k++) out[k] = BYE_RUNS[k];
    return out;
  }

  runs5_7(v, out) {
    out[0] = 0.012; out[1] = 0.002;
    return out;
  }

  runout_runs(v, out) {
    const w = v.dtype === 'wide' ? RO_RUNS_WIDE : RO_RUNS;
    for (let k = 0; k < 4; k++) out[k] = w[k];
    return out;
  }

  runout_who(v, runs) { return 0.5; }

  runout_new_on_strike(v, who, runs) { return NEW_ON_STRIKE[who][Math.min(runs, 2)]; }

  p_crossed(v) { return v.prep.crossed; }

  // --- tactics
  bowler_utility(v, c) {
    let u = c.option < 5 ? 0.0 : -3.5;
    if (c.part_timer) u -= 2.0;
    const k = v.over;
    if (v.prep.isTest) {
      const sp = this._spinOf(v, c.idx) > 0;
      u += c.spell ? 1.0 - 0.35 * c.spell : 0.0;
      if (k < 2 || v.ball_age_overs < 2) u += c.option < 2 ? 1.5 : 0.0;
      if (sp) u += v.ball_age_overs > 20 ? 0.6 : -0.8;
      return u;
    }
    if (c.spell && c.spell < 3) u += 0.8;
    if (k < 2) u += c.option < 2 ? 1.5 : 0.0;
    if (v.max_balls && 4 * v.legal_balls >= 3 * v.max_balls && (c.option === 0 || c.option === 3)) u += 0.8;
    if (c.quota_left && c.overs_left) u += 1.5 * c.quota_left / c.overs_left;
    return u;
  }

  declare_hazard(v) {
    const lead = v.lead, k = v.innings, left = v.exp_overs_left;
    if (k === 3) {
      const need = 220 + 1.4 * Math.min(left, 150);
      return sigmoid(0.03 * (lead - need) + (v.last_over_wkt ? 0.3 : 0.0));
    }
    if (lead < 250) return 0.0;
    return sigmoid(-14 + 0.018 * v.runs + 0.3 * v.wkts - 0.01 * Math.max(0.0, left - 300));
  }

  follow_on_prob(v) {
    const pi = v.prev_innings;
    const bowled = pi.length ? pi[pi.length - 1][3] / 6 : 0.0;
    return sigmoid(0.6 + 0.01 * (v.lead - 200) - 0.01 * Math.max(0.0, bowled - 110));
  }

  new_ball_prob(v) { return 0.85; }

  // --- time and rain
  interruption_schedule(sc, fromBall, u) {
    const w = pyOr(get(sc, 'weather'), {});
    let risk = get(w, 'rain_risk');
    risk = risk === null ? RAIN[sc.fam] : risk;
    let n = this._schedN.get(sc);
    if (n === undefined) {
      n = pyOr(get(pyOr(get(sc, 'rules'), {}), 'max_balls'), defaultRules(sc.fam).max_balls);
      this._schedN.set(sc, n);
    }
    const out = [];
    const cuts = [risk, risk / 3];
    for (let j = 0; j < 2; j++) {
      if (u[5 * j] >= cuts[j]) break;
      let start;
      if (fromBall === 0 && u[1 + 5 * j] < 0.35) start = 0;
      else start = fromBall + Math.trunc(u[2 + 5 * j] * Math.max(1, 2 * n - fromBall));
      out.push({ start, lost: 6 * (1 + Math.trunc(u[3 + 5 * j] * 0.6 * n / 6)) });
    }
    return out.sort((a, b) => a.start - b.start);
  }

  _day(sc) {
    const r = this._rules(sc);
    const w = pyOr(get(sc, 'weather'), {});
    const risk = get(w, 'rain_risk');
    return [6 * r.test_overs_per_day, risk === null ? 0.8 : 1.0 - risk];
  }

  day_availability(sc, day, u) {
    const [full, pFull] = this._day(sc);
    return u < pFull ? full : Math.trunc(full * (u - pFull) / (1.0 - pFull));
  }

  day_availability_mean(sc, day) {
    const [full, pFull] = this._day(sc);
    return full * (pFull + (1.0 - pFull) / 2);
  }

  _z(sc, overs, wkts) {
    const [z0, b] = RES[sc.fam];
    return z0 * (1 - wkts / 10) ** 1.3 * (1 - Math.exp(-b * (1 + 0.25 * wkts) * overs));
  }

  resource(sc, ballsRemaining, wkts) {
    if (wkts >= 10 || ballsRemaining <= 0) return 0;
    const n = this._rules(sc).max_balls;
    return Math.floor(1000 * this._z(sc, ballsRemaining / 6, wkts) / this._z(sc, n / 6, 0) + 0.5);
  }

  resource_G(sc) {
    return this._z(sc, this._rules(sc).max_balls / 6, 0);
  }
}

// Provider for a parameter bundle (null -> StubProvider; {stub: true, players} -> StubProvider(players)).
export function createProvider(bundle = null) {
  if (bundle === null || bundle === undefined) return new StubProvider();
  if (bundle.stub) return new StubProvider(bundle.players || null);
  throw new Error('no bundle-interpreting provider yet: pass null for the StubProvider');
}

// ---------------------------------------------------------------- scenario and state schema

// Check a section 9.1 scenario and return a normalized deep copy with defaults filled (validate_scenario).
export function validateScenario(sc0) {
  const sc = deepcopy(sc0);
  const errs = [];
  if (!FAMS.includes(sc.fam)) errs.push(`fam must be one of ('T20', 'ODI', 'TEST')`);
  setdefault(sc, 'gender', 'male');
  setdefault(sc, 'competition_id', null);
  sc.date = String(pyOr(get(sc, 'date'), '2025-06-01')).slice(0, 10);
  setdefault(sc, 'venue_id', null);
  sc.neutral = pyBool(get(sc, 'neutral', false));
  setdefault(sc, 'start_slot', 'day');
  const teams = get(sc, 'teams');
  if (!Array.isArray(teams) || teams.length !== 2) throw new Error('scenario needs two teams');
  const seen = new Set();
  teams.forEach((team, t) => {
    const order = pyOr(get(team, 'batting_order'), []);
    if (order.length < 2 || new Set(order).size !== order.length || order.length > 11) {
      errs.push(`team ${t}: batting_order needs 2..11 distinct ids`);
    }
    setdefault(team, 'name', `team${t}`);
    team.bowling_xi = [...pyOr(get(team, 'bowling_xi'), order)];
    setdefault(team, 'keeper', null);
    team.absent = [...pyOr(get(team, 'absent'), [])];
    team.home = pyBool(get(team, 'home', false));
    const ids = new Set([...order, ...team.bowling_xi, ...pyOr(get(team, 'bowlers'), [])]);
    const shared = [...ids].filter((x) => seen.has(x)).sort();
    if (shared.length) errs.push(`team ${t}: ids shared with the other team: ${pyRepr(shared)}`);
    for (const x of ids) seen.add(x);
    const bad = team.absent.filter((x) => !order.includes(x)).sort();
    if (bad.length) errs.push(`team ${t}: absent ids not in batting_order: ${pyRepr(bad)}`);
    if (get(team, 'bowlers') !== null && !pyBool(team.bowlers)) errs.push(`team ${t}: bowlers list is empty`);
  });
  const toss = setdefault(sc, 'toss', null);
  if (toss !== null && (![0, 1].includes(get(toss, 'winner')) || !['bat', 'field'].includes(get(toss, 'decision')))) {
    errs.push('toss must be null or {winner: 0|1, decision: bat|field}');
  }
  const um = setdefault(sc, 'umpires', null);
  if (um !== null && um.length !== 2) errs.push('umpires must be null or two ids');
  const drs = { ...pyOr(get(sc, 'drs'), {}) };
  for (const k of ['enabled', 'reviews_per_innings', 'umpires_call_retains']) setdefault(drs, k, null);
  drs.accuracy_mult = Number(pyOr(get(drs, 'accuracy_mult'), 1.0));
  drs.ucall_mult = Number(pyOr(get(drs, 'ucall_mult'), 1.0));
  sc.drs = drs;
  setdefault(sc, 'weather', null);
  sc.pitch = { known: false, runs_sd: 0.0, wkt_sd: 0.0, spin_sd: 0.0, wear_sd: 0.0, ...pyOr(get(sc, 'pitch'), {}) };
  sc.player_form = { ...pyOr(get(sc, 'player_form'), {}) };
  for (const [pid, f] of Object.entries(sc.player_form)) {
    if (!seen.has(pid)) errs.push(`player_form for unknown id ${pid}`);
    for (const k of Object.keys(f)) {
      if (!['bat_runs_sd', 'bat_wkt_sd', 'bowl_runs_sd', 'bowl_wkt_sd'].includes(k)) errs.push(`player_form[${pid}]: unknown key ${k}`);
    }
  }
  setdefault(sc, 'state', null);
  setdefault(sc, 'n_sims', get(sc, 'fam') === 'TEST' ? 4000 : 10000);
  setdefault(sc, 'seed', 0);
  sc.sensitivity = pyBool(get(sc, 'sensitivity', false));
  setdefault(sc, 'rules', null);
  setdefault(sc, 'scheduled_days', null);
  sc.draw_player_uncertainty = pyBool(get(sc, 'draw_player_uncertainty', true));
  if (errs.length) throw new Error(errs.join('; '));
  return sc;
}

export const STATE_CUR_KEYS = ['number', 'team', 'runs', 'wkts', 'legal_balls', 'max_balls', 'target', 'target_timing',
  'striker', 'nonstriker', 'batters', 'unavailable', 'next', 'bowlers', 'over_bowlers', 'bowler', 'last_bowler',
  'ball_in_over', 'free_hit', 'reviews', 'fail_reviews', 'umpire_offset', 'partnership', 'ball_age_overs',
  'second_new_ball', 'last_over_runs', 'last_over_wkt', 'over_runs', 'wkt_this_over', 'over_scores'];

// Structural problems of a canonical (fully specified) section 9.3 state; [] when well formed.
export function stateSchemaErrors(state, sc) {
  const errs = [];
  for (const k of ['innings_team', 'done', 'cur']) if (!has(state, k)) errs.push(`state missing ${k}`);
  if (errs.length) return errs;
  const cur = state.cur;
  for (const k of STATE_CUR_KEYS) if (!has(cur, k)) errs.push(`state.cur missing ${k}`);
  state.done.forEach((inn, i) => {
    for (const k of ['team', 'runs', 'wkts', 'legal_balls', 'max_balls', 'target', 'end']) {
      if (!has(inn, k)) errs.push(`state.done[${i}] missing ${k}`);
    }
  });
  if (sc.fam === 'TEST' && !pyBool(get(state, 'clock'))) errs.push('Tests need state.clock {used, changeovers, avail}');
  if (sc.fam !== 'TEST' && !has(state, 'resources')) errs.push('limited overs need state.resources [R1, R2] (null entries allowed)');
  return errs;
}
