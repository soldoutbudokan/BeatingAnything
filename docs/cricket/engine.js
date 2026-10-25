// Fast ball-by-ball cricket Monte Carlo engine: the exact JavaScript twin of beating/cricket/sim.py.
//
// Method. One simulation at a time in float64 on the shared xoshiro128** streams (plan 9.5; seeding as
// rng.js, uniforms generated in place). Match flow, rules, event order, random-number slots and float
// arithmetic order follow sim.py function by function (same names in camelCase): toss, innings order,
// arrivals, bowler choice under the eligibility and feasibility filter of 7.1, the delivery transition of
// 9.2, the DRS layer of 9.4, free-hit carry-over, run-out and crossing placement, chase crediting, the
// Test clock, declarations, follow-on, interruptions with the integer targets of 7.6, par results and no
// results, super overs and coins, match and innings latents with player form, the canonical in-play state
// of 9.3 with its 10-step Newton latent update, scripted-draw mode, event logs, and the outputs of 9.7
// (Acc is integer-only, so partial aggregates from any split of the sim range merge exactly). The slot
// map, event list and resolved rule ambiguities are documented in the sim.py module docstring and hold
// here unchanged. Every probability comes from a provider (provider.js).
//
// Performance. Per-sim state lives in typed arrays indexed by player slot (Prepared.slots); Match and
// Innings objects are pooled and reset per sim; the view object is refreshed in place (fields that only
// change at over ends, bowler choice, new balls, revisions and innings starts are rewritten only after
// one of those events); providers write into engine-owned Float64Arrays; nothing is allocated per
// delivery unless an event log is requested. Static per-scenario quantities (rule flags, windows per
// innings length, resources, form sliders, latent means) are computed once in Prepared. Every shortcut
// is exact: categorical draws memoize the cumulative sums of the last eta vector per call site and
// exponentials of bowler utilities by argument (identical floats in, identical floats out), form normals
// are transformed on first use from the uniforms drawn at match start, and simulate() accumulates the
// Acc from typed arrays (Acc.addMatch, the same sums as Acc.add(match.record())). With the StubProvider
// on the 4-CPU build machine: about 1.6M (T20), 1.75M (ODI) and 1.65M (Test) deliveries per second per
// thread; cli.js --workers 4 about 3.6M, 4.7M and 4.3M.
//
// Parity. tests/test_cricket_engine_parity.py replays tests/data/cricket_parity/{transitions,trajectories}
// .jsonl through cli.js. Decisions and integers match exactly; latent values (Box-Muller, Newton) match to
// about 1e-15 because V8's Math.log/cos/sin/exp differ from glibc in the last bit on some arguments.
//
// Limits. As sim.py: no retirements, nightwatchmen or multi-bowler overs (D2, D3, D7), no Hundred (D1),
// in-play states only inside a main innings.

import { fmix32 } from './rng.js';
import {
  DTYPES, KINDS, WIDE_WKTS, MASK_OFFSET, StubProvider, validateScenario, stateSchemaErrors, pyBool, pyOr, get, has,
  setdefault, deepcopy, pySum, pyRepr,
} from './provider.js';

export const LEGAL = 0, WIDE = 1, NOBALL = 2;
export const DOT = 0, ONE = 1, TWO = 2, THREE = 3, FOUR = 4, SIX = 5, OUT = 6, RUN_OUT = 7, BYES = 8;
export const CAUGHT = 0, BOWLED = 1, LBW = 2, STUMPED = 3, OTHER = 4, RO = 5;
export const KIND_ALL = [...KINDS, 'run_out'];
export const MAX_DAYS = 8, MAX_SUPER_OVERS = 6;
export const CODES = ['win0', 'win1', 'tie', 'draw', 'no_result'];
const NOMINAL_RUNS = [0, 1, 2, 3, 4, 6, 0, 0, 0];
const M_TOSS = 0, M_TOSS_BAT = 1, M_LAT = 2, M_INN_LAT = 6, M_DAYS = 14, M_RAIN = 22, M_COIN = 38;
const DT = { legal: 0, wide: 1, noball: 2 }, WW = { none: 0, stumped: 1, run_out: 2 };
const KI = Object.fromEntries(KIND_ALL.map((k, i) => [k, i]));
const RO_PENDING = -2, NONE = -1;
const INV32 = 2.3283064365386963e-10;
const VIEW_STATIC = new Set(['fam', 'gender', 'competition_id', 'date', 'venue_id', 'neutral', 'start_slot', 'weather',
  'umpires', 'rules', 'drs_enabled', 'sched_balls', 'scheduled_days', 'teams', 'home', 'prep', 'latent',
  'striker_idx', 'nonstriker_idx', 'bowler_idx']);
export const STAT_NAMES = ['bat_reviews', 'bat_overturned', 'bat_ucall', 'field_success', 'missed_standing', 'field_spec',
  'field_spec_ucall', 'bowler_fallback', 'latent_updates', ...KIND_ALL.map((k) => `kind_${k}`),
  ...KIND_ALL.map((k) => `kind_${k}_wide`)];
const S_BAT_REV = 0, S_BAT_OVT = 1, S_BAT_UC = 2, S_FIELD_OK = 3, S_MISSED = 4, S_SPEC = 5, S_SPEC_UC = 6,
  S_FALLBACK = 7, S_LATENT = 8, S_KIND = 9, S_KIND_WIDE = 9 + KIND_ALL.length;
const ZERO2 = new Float64Array(2);

export class ScriptError extends Error {
  constructor(msg) { super(msg); this.name = 'ScriptError'; }
}
class Stop {
  constructor(ev) { this.ev = ev; }
}

// ---------------------------------------------------------------- random numbers (plan 9.5)

// xoshiro128** stream, bit-identical to rng.js Stream, reseedable and filling buffers in place.
export class FastStream {
  constructor(seed = 0, sim = 0, stream = 0) {
    this.s = new Uint32Array(4);
    this.reseed(seed, sim, stream);
  }

  reseed(seed, sim, stream) {
    const s = this.s;
    let key = (fmix32(fmix32((seed ^ 0x243F6A88) >>> 0) ^ stream) ^ sim) >>> 0;
    for (let i = 0; i < 4; i++) {
      key = (key + 0x9E3779B9) >>> 0;
      s[i] = fmix32(key);
    }
    if (!s[0] && !s[1] && !s[2] && !s[3]) s[0] = 1;
  }

  fill(out, k) {
    const s = this.s;
    let s0 = s[0] | 0, s1 = s[1] | 0, s2 = s[2] | 0, s3 = s[3] | 0;
    for (let i = 0; i < k; i++) {
      const x = Math.imul(s1, 5);
      out[i] = (Math.imul((x << 7) | (x >>> 25), 9) >>> 0) * INV32;
      const t = s1 << 9;
      s2 ^= s0; s3 ^= s1; s1 ^= s2; s0 ^= s3; s2 ^= t;
      s3 = (s3 << 11) | (s3 >>> 21);
    }
    s[0] = s0; s[1] = s1; s[2] = s2; s[3] = s3;
    return out;
  }
}

let CUM = new Float64Array(64);

// Math.exp with a direct-mapped memo keyed by the argument's bits (same argument, same result): bowler
// utilities take few distinct values, so their exponentials repeat across overs and sims.
const MX = new Float64Array(1), MW = new Int32Array(MX.buffer);
const MEMO_K = new Float64Array(1024).fill(NaN), MEMO_V = new Float64Array(1024);
function expMemo(x) {
  MX[0] = x;
  const h = Math.imul(MW[0] ^ Math.imul(MW[1], 0x9E3779B1), 0x85EBCA6B) >>> 22;
  if (MEMO_K[h] === x) return MEMO_V[h];
  const y = Math.exp(x);
  MEMO_K[h] = x; MEMO_V[h] = y;
  return y;
}

// First class k with u * cum[n-1] < cum[k], cum the running sum of exp(eta - max) (sim.cat_eta).
export function catEta(u, eta, n) {
  if (n > CUM.length) CUM = new Float64Array(2 * n);
  let m = eta[0];
  for (let k = 1; k < n; k++) if (eta[k] > m) m = eta[k];
  let c = 0.0;
  for (let k = 0; k < n; k++) { c += expMemo(eta[k] - m); CUM[k] = c; }
  const t = u * c;
  for (let k = 0; k < n; k++) if (t < CUM[k]) return k;
  return n - 1;
}

// The same rule on running sums of non-negative weights (sim.cat_w).
export function catW(u, w, n) {
  if (n > CUM.length) CUM = new Float64Array(2 * n);
  let c = 0.0;
  for (let k = 0; k < n; k++) { c += w[k]; CUM[k] = c; }
  const t = u * c;
  for (let k = 0; k < n; k++) if (t < CUM[k]) return k;
  return n - 1;
}

// catEta with a memo of the last eta vector: identical floats give identical sums, so a repeated eta
// (the same striker, bowler and context) skips the exponentials without changing any draw.
export class CatCache {
  constructor(n, ways = 4) {
    this.n = n; this.ways = ways; this.next = 0;
    this.last = new Float64Array(n * ways).fill(NaN);
    this.cum = new Float64Array(n * ways);
  }

  draw(ua, ui, eta) {   // the uniform is ua[ui] (an array and index, so no boxed double is passed)
    const n = this.n, last = this.last, cum = this.cum;
    let o = -1;
    for (let w = 0, b = 0; w < this.ways; w++, b += n) {
      let k = 0;
      while (k < n && eta[k] === last[b + k]) k++;
      if (k === n) { o = b; break; }
    }
    if (o < 0) {
      o = this.next * n;
      this.next = this.next + 1 === this.ways ? 0 : this.next + 1;
      let m = eta[0];
      for (let j = 1; j < n; j++) if (eta[j] > m) m = eta[j];
      let c = 0.0;
      for (let j = 0; j < n; j++) { c += Math.exp(eta[j] - m); cum[o + j] = c; last[o + j] = eta[j]; }
    }
    const t = ua[ui] * cum[o + n - 1];
    for (let j = 0; j < n; j++) if (t < cum[o + j]) return j;
    return n - 1;
  }
}

export function normalPair(u1, u2) {
  const r = Math.sqrt(-2.0 * Math.log(1.0 - u1));
  return [r * Math.cos(2 * Math.PI * u2), r * Math.sin(2 * Math.PI * u2)];
}

const NP = new Float64Array(2);
function normalInto(u1, u2) {
  const r = Math.sqrt(-2.0 * Math.log(1.0 - u1));
  NP[0] = r * Math.cos(2 * Math.PI * u2);
  NP[1] = r * Math.sin(2 * Math.PI * u2);
  return NP;
}

export function softmax(eta) {
  let m = eta[0];
  for (let k = 1; k < eta.length; k++) if (eta[k] > m) m = eta[k];
  const ex = Array.from(eta, (e) => Math.exp(e - m));
  const s = pySum(ex);
  return ex.map((x) => x / s);
}

// ---------------------------------------------------------------- rules helpers

export function quota(nOvers, rule = 'fifth_min2') {
  if (rule === 'fifth_min2' && nOvers < 10) return [Math.min(2, nOvers), 0];
  return [Math.floor(nOvers / 5), nOvers % 5];
}

let Q_BASE = 0, Q_FREE = 0;   // quota base and unclaimed bonuses of the last eligibleInto call (limited overs)

// Plan 7.1 eligibility (sim.eligible_bowlers) on slot indices: opts (array of slots, length nOpts), overs
// per slot (completed overs, 0 for slots that have not bowled), present = slots that have bowled
// (for counting claimed bonuses), last slot or -1, nOvers null in Tests. Writes eligible slots to out.
export function eligibleInto(opts, nOpts, overs, present, nPresent, last, nOvers, done, rule, out) {
  let m = 0;
  if (nOvers === null) {
    for (let i = 0; i < nOpts; i++) if (opts[i] !== last) out[m++] = opts[i];
    return m;
  }
  nOvers |= 0;
  let base, free;
  if (rule === 'fifth_min2' && nOvers < 10) { base = nOvers < 2 ? nOvers : 2; free = 0; } else { base = (nOvers / 5) | 0; free = nOvers - 5 * base; }
  for (let i = 0; i < nPresent; i++) if (overs[present[i]] > base) free--;
  Q_BASE = base; Q_FREE = free;
  const r2 = nOvers - done - 1;
  const ci = r2 >> 1, co = (r2 + 1) >> 1;
  let tot = 0, nb = 0;                      // sum_j min(q_j, ceil(R'/2)) and #{q_j < ceil(R'/2)} over q_j >= 0
  for (let i = 0; i < nOpts; i++) {
    const q = base - overs[opts[i]];
    if (q >= 0) { if (q < co) { tot += q; nb++; } else tot += co; }
  }
  const fp = free > 0 ? free : 0, fm = free > 1 ? free - 1 : 0;
  for (let i = 0; i < nOpts; i++) {
    const b = opts[i], q = base - overs[b];
    if (b === last || q < 0 || (q === 0 && free <= 0)) continue;
    let t, n, fi;
    if (q < co) { t = tot - q; n = nb - 1; } else { t = tot - co; n = nb; }
    if (q > 0) {
      const q1 = q - 1;
      if (q1 < ci) { t += q1; n++; } else t += ci;
      fi = fp;
    } else {
      fi = fm;
    }
    if (t + (fi < n ? fi : n) >= r2) out[m++] = b;
  }
  return m;
}

// Id-based form of the same rule (Prepared and impute_state): opts ids, overs Map id -> overs.
export function eligibleBowlers(opts, overs, last, nOvers, done, rule = 'fifth_min2') {
  const keys = [...new Set([...opts, ...overs.keys()])];
  const ix = new Map(keys.map((k, i) => [k, i]));
  const ov = new Int32Array(keys.length), present = [...overs.keys()].map((k) => ix.get(k));
  for (const [k, x] of overs) ov[ix.get(k)] = x;
  const out = new Int32Array(opts.length);
  const m = eligibleInto(opts.map((k) => ix.get(k)), opts.length, ov, present, present.length,
    last === null || !ix.has(last) ? -1 : ix.get(last), nOvers, done, rule, out);
  return Array.from(out.subarray(0, m), (i) => keys[i]);
}

export function quotaLeft(overs, b, nOvers, rule = 'fifth_min2') {
  if (nOvers === null) return null;
  const [base, bonus] = quota(nOvers, rule);
  const o = overs.has(b) ? overs.get(b) : 0;
  if (o > base) return 0;
  let free = bonus;
  for (const x of overs.values()) if (x > base) free--;
  return base - o + (free > 0 ? 1 : 0);
}

export function revisedTarget(s1, r1, r2, g) {
  if (r2 <= r1) {
    if (r1 === 0) throw new Error('ZeroDivisionError: integer division or modulo by zero');
    return Math.floor(s1 * r2 / r1) + 1;
  }
  return s1 + Math.floor(g * (r2 - r1) / 1000) + 1;
}

export const scaleBall = (b, nNew, nSched) => Math.floor((2 * b * nNew + nSched) / (2 * nSched));

export function followOnThreshold(table, daysRemaining) {
  for (const [d, lead] of table || []) if (daysRemaining >= d) return lead;
  return null;
}

// Python's correctly rounded int / int true division for non-negative safe integers a * b / c style
// quantities that may exceed 2**53 (sumsq / n in the variance formulas).
function sqDiv(s, m) {
  const sq = s * s;
  if (Number.isSafeInteger(sq)) return sq / m;
  return bigDiv(BigInt(s) * BigInt(s), BigInt(m));
}

function bigDiv(a, b) {
  const la = a.toString(2).length, lb = b.toString(2).length;
  const shift = 55 - (la - lb);
  let q, r;
  if (shift >= 0) { const as = a << BigInt(shift); q = as / b; r = as % b; } else { const bs = b << BigInt(-shift); q = a / bs; r = a % bs; }
  if (r !== 0n) q |= 1n;
  return Number(q) * 2 ** -shift;
}

// ---------------------------------------------------------------- scenario preparation

function makeView() {
  return {
    fam: null, gender: null, competition_id: null, date: null, venue_id: null, neutral: null, start_slot: null,
    weather: null, umpires: null, rules: null, drs_enabled: null, sched_balls: null, scheduled_days: null, teams: null,
    home: null, prep: null, toss_winner: null, innings: null, super_over: 0, so_innings: 0, bat_team: null,
    bowl_team: null, bat_home_status: null, bowl_home_status: null, target_timing: null, followed_on: false,
    prev_innings: [], umpire_offset: null, latent: null, legal_balls: null, ball_in_over: null, over: null,
    max_balls: null, balls_remaining: null, runs: null, wkts: null, unavailable: null, target: null,
    runs_required: null, striker: null, nonstriker: null, bowler: null, striker_runs: null, striker_balls: null,
    nonstriker_runs: null, nonstriker_balls: null, striker_arrival: null, nonstriker_arrival: null, striker_pos: null,
    nonstriker_pos: null, bowler_balls: null, bowler_runs: null, bowler_wkts: null, bowler_overs: null,
    bowler_spell: null, bowler_part_timer: null, partnership_runs: null, partnership_balls: null, free_hit: null,
    pp_window: null, field_restr: null, reviews_bat: null, reviews_bowl: null, bat_fail_reviews: null,
    bowl_fail_reviews: null, ball_age_overs: null, second_new_ball: null, innings_overs: null,
    match_legal_balls: null, clock_used: null, est_day: null, overs_into_day: null, exp_overs_left: null, lead: null,
    striker_form: null, nonstriker_form: null, bowler_form: null, bowl_end_umpire: null, to_come: null,
    last_over_runs: null, last_over_wkt: null, dtype: null, striker_idx: -1, nonstriker_idx: -1, bowler_idx: -1,
  };
}

// Reset the dynamic view keys to view0 (the static scenario keys are never written by the engine).
function resetView(v, v0) {
  v.toss_winner = v0.toss_winner; v.innings = v0.innings; v.super_over = v0.super_over; v.so_innings = v0.so_innings;
  v.bat_team = v0.bat_team; v.bowl_team = v0.bowl_team; v.bat_home_status = v0.bat_home_status;
  v.bowl_home_status = v0.bowl_home_status; v.target_timing = v0.target_timing; v.followed_on = v0.followed_on;
  v.prev_innings = v0.prev_innings; v.umpire_offset = v0.umpire_offset; v.latent = v0.latent;
  v.legal_balls = v0.legal_balls; v.ball_in_over = v0.ball_in_over; v.over = v0.over; v.max_balls = v0.max_balls;
  v.balls_remaining = v0.balls_remaining; v.runs = v0.runs; v.wkts = v0.wkts; v.unavailable = v0.unavailable;
  v.target = v0.target; v.runs_required = v0.runs_required; v.striker = v0.striker; v.nonstriker = v0.nonstriker;
  v.bowler = v0.bowler; v.striker_runs = v0.striker_runs; v.striker_balls = v0.striker_balls;
  v.nonstriker_runs = v0.nonstriker_runs; v.nonstriker_balls = v0.nonstriker_balls;
  v.striker_arrival = v0.striker_arrival; v.nonstriker_arrival = v0.nonstriker_arrival;
  v.striker_pos = v0.striker_pos; v.nonstriker_pos = v0.nonstriker_pos; v.bowler_balls = v0.bowler_balls;
  v.bowler_runs = v0.bowler_runs; v.bowler_wkts = v0.bowler_wkts; v.bowler_overs = v0.bowler_overs;
  v.bowler_spell = v0.bowler_spell; v.bowler_part_timer = v0.bowler_part_timer;
  v.partnership_runs = v0.partnership_runs; v.partnership_balls = v0.partnership_balls; v.free_hit = v0.free_hit;
  v.pp_window = v0.pp_window; v.field_restr = v0.field_restr; v.reviews_bat = v0.reviews_bat;
  v.reviews_bowl = v0.reviews_bowl; v.bat_fail_reviews = v0.bat_fail_reviews;
  v.bowl_fail_reviews = v0.bowl_fail_reviews; v.ball_age_overs = v0.ball_age_overs;
  v.second_new_ball = v0.second_new_ball; v.innings_overs = v0.innings_overs;
  v.match_legal_balls = v0.match_legal_balls; v.clock_used = v0.clock_used; v.est_day = v0.est_day;
  v.overs_into_day = v0.overs_into_day; v.exp_overs_left = v0.exp_overs_left; v.lead = v0.lead;
  v.striker_form = v0.striker_form; v.nonstriker_form = v0.nonstriker_form; v.bowler_form = v0.bowler_form;
  v.bowl_end_umpire = v0.bowl_end_umpire; v.to_come = v0.to_come; v.last_over_runs = v0.last_over_runs;
  v.last_over_wkt = v0.last_over_wkt; v.dtype = v0.dtype; v.striker_idx = v0.striker_idx;
  v.nonstriker_idx = v0.nonstriker_idx; v.bowler_idx = v0.bowler_idx;
}

// Scenario-level statics shared by every simulation (sim.Prepared).
export class Prepared {
  constructor(scenario, provider = null) {
    const sc = validateScenario(scenario);
    const P = provider || new StubProvider();
    this.sc = sc; this.P = P;
    this.fam = sc.fam;
    this.limited = this.fam !== 'TEST';
    this.isTest = !this.limited;
    const r = { ...P.rules(sc) };
    const d = sc.drs;
    if (d.enabled !== null) r.drs_enabled = pyBool(d.enabled);
    if (d.reviews_per_innings !== null) r.reviews_per_innings = Math.trunc(d.reviews_per_innings);
    if (d.umpires_call_retains !== null) r.umpires_call_retains = pyBool(d.umpires_call_retains);
    if (pyBool(sc.scheduled_days)) r.test_days = Math.trunc(sc.scheduled_days);
    if (r.balls_per_over !== 6) throw new Error('only 6-ball overs are simulated (deviation D1)');
    this.rules = r; this.bpo = 6;
    this.qrule = pyOr(get(r, 'quota_rule'), 'fifth_min2');
    this.acc = d.accuracy_mult; this.ucm = d.ucall_mult;
    this.rpi = pyBool(r.drs_enabled) ? Math.trunc(pyOr(r.reviews_per_innings, 0)) : 0;
    this.drsOn = pyBool(r.drs_enabled); this.retain = pyBool(r.umpires_call_retains);
    this.crossing = pyBool(r.caught_crossing_counts); this.topup = pyBool(r.review_topup_after_80);
    const spec = P.latent_spec(sc);
    this.lat_m = [...spec.match]; this.lat_i = [...spec.innings];
    if (this.lat_m.length > 4 || this.lat_i.length > 2) throw new Error('at most 4 match and 2 innings latents');
    this.G = this.limited ? P.resource_G(sc) : null;
    this._res = new Map(); this._post = null; this._win = new Map();

    this.orders = []; this.absent = []; this.keeper = []; this.opts = []; this.part_timers = []; this.xi = [];
    this.pos = new Map(); this.slots = [];
    sc.teams.forEach((team, t) => {
      const order = [...team.batting_order];
      this.orders.push(order);
      const absent = new Set(team.absent);
      this.absent.push(absent);
      this.keeper.push(team.keeper);
      order.forEach((p, i) => this.pos.set(p, i + 1));
      const xi = team.bowling_xi.filter((p) => !absent.has(p));
      this.xi.push(xi);
      const opts = pyBool(get(team, 'bowlers')) ? [...team.bowlers] : [...xi].reverse().filter((p) => p !== team.keeper);
      const added = [];
      if (this.limited) {
        const n = Math.floor(r.max_balls / 6);
        const extra = order.filter((p) => !opts.includes(p) && p !== team.keeper && !absent.has(p));
        while (!eligibleBowlers(opts, new Map(), null, n, 0, this.qrule).length && extra.length) {
          const p = extra.shift();
          opts.push(p);
          added.push(p);
        }
      }
      this.opts.push(opts);
      this.part_timers.push(new Set(added));
      const xiSet = new Set(team.bowling_xi), orderSet = new Set(order);
      for (const p of [...order, ...team.bowling_xi.filter((p) => !orderSet.has(p)),
        ...opts.filter((p) => !orderSet.has(p) && !xiSet.has(p))]) {
        if (!this.slots.includes(p)) this.slots.push(p);
        if (!this.pos.has(p)) this.pos.set(p, 11);
      }
    });
    this.part_timer_report = this.part_timers.map((s) => [...s].sort());
    const home = sc.teams.map((t) => t.home);
    this.home_status = [0, 1].map((t) => (sc.neutral || !(home[t] || home[1 - t]) ? 'neutral' : home[t] ? 'home' : 'away'));

    // integer (slot) forms of the statics
    const n = this.slots.length;
    this.nSlots = n;
    this.ids = this.slots;
    this.slotOf = new Map(this.slots.map((p, i) => [p, i]));
    const S = (p) => this.slotOf.get(p);
    this.posIdx = Int32Array.from(this.slots, (p) => this.pos.get(p));
    this.ordersIdx = this.orders.map((o) => Int32Array.from(o, S));
    this.absentFlag = this.absent.map((a) => { const f = new Uint8Array(n); for (const p of a) f[S(p)] = 1; return f; });
    this.keeperIdx = this.keeper.map((k) => (k !== null && this.slotOf.has(k) ? S(k) : -1));
    this.optsIdx = this.opts.map((o) => Int32Array.from(o, S));
    this.optIndex = this.optsIdx.map((o) => {
      const f = new Int32Array(n).fill(o.length);
      for (let i = o.length - 1; i >= 0; i--) f[o[i]] = i;
      return f;
    });
    this.ptFlag = this.part_timers.map((a) => { const f = new Uint8Array(n); for (const p of a) f[S(p)] = 1; return f; });
    this.xiIdx = this.xi.map((x) => Int32Array.from(x, S));
    this.prep = P.prepare(sc, this.slots);
    this.formSliders = new Float64Array(4 * n);
    this.slots.forEach((p, i) => {
      const sl = get(sc.player_form, p, {});
      ['bat_runs_sd', 'bat_wkt_sd', 'bowl_runs_sd', 'bowl_wkt_sd'].forEach((k, j) => { this.formSliders[4 * i + j] = Number(get(sl, k, 0.0)); });
    });
    this.hasUmpires = pyBool(sc.umpires);
    this.pitchKnown = pyBool(sc.pitch.known);
    this.latMu = Float64Array.from(this.lat_m, (s) => Number(pyOr(get(sc.pitch, s.pitch, 0.0), 0.0)) * s.sd);
    this.latSdM = Float64Array.from(this.lat_m, (s) => s.sd);
    this.latSdI = Float64Array.from(this.lat_i, (s) => s.sd);
    this.viewKeys = null;

    const sd = this.isTest ? r.test_days : null;
    const v = makeView();
    Object.assign(v, {
      fam: this.fam, gender: sc.gender, competition_id: sc.competition_id, date: sc.date, venue_id: sc.venue_id,
      neutral: sc.neutral, start_slot: sc.start_slot, weather: sc.weather, umpires: sc.umpires, rules: r,
      drs_enabled: pyBool(r.drs_enabled), sched_balls: r.max_balls, scheduled_days: sd,
      teams: sc.teams.map((t) => t.name), home, prep: this.prep, super_over: 0, so_innings: 0, followed_on: false,
      prev_innings: [],
    });
    this.view0 = v;
  }

  // Laplace posterior of the in-play latents from state.balls (sim.Prepared.posterior).
  posterior() {
    if (this._post === null) {
      const sc = this.sc, pitch = sc.pitch, nm = this.lat_m.length, ni = this.lat_i.length;
      const st = sc.state;
      const known = pyBool(pitch.known);
      const free = [...(known ? [] : [...Array(nm).keys()]), ...[...Array(ni).keys()].map((j) => nm + j)];
      const mu = [...this.lat_m.map((s) => Number(pyOr(get(pitch, s.pitch, 0.0), 0.0)) * s.sd), ...Array(ni).fill(0.0)];
      const sd = [...this.lat_m.map((s) => s.sd), ...this.lat_i.map((s) => s.sd)];
      const fixed = mu.map((x, j) => (known && j < nm ? x : 0.0));
      const pf = sc.player_form;
      const form = (p, a, b) => {
        const f = pyOr(get(pf, p), {});
        return [Number(pyOr(get(f, a, 0.0), 0.0)), Number(pyOr(get(f, b, 0.0), 0.0))];
      };
      const recs = st.balls.map((r) => {
        const v = { ...r.view };
        for (const [key, pid] of [['striker_form', 'striker'], ['nonstriker_form', 'nonstriker']]) {
          if (get(v, pid) !== null) v[key] = form(v[pid], 'bat_runs_sd', 'bat_wkt_sd');
        }
        if (get(v, 'bowler') !== null) v.bowler_form = form(v.bowler, 'bowl_runs_sd', 'bowl_wkt_sd');
        return { inn: r.inn, cls: r.cls, view: v };
      });
      const base = { ...this.view0 };
      base.toss_winner = get(pyOr(get(st, 'toss'), {}), 'winner');
      const [mode, chol] = latentPosterior(this.P, base, recs, st.cur.number, free, free.map((j) => mu[j]),
        free.map((j) => sd[j]), fixed, nm, 10, this);
      this._post = { free, mode, chol };
    }
    return this._post;
  }

  res(ballsRemaining, wkts) {
    const key = ballsRemaining * 16 + wkts;
    let v = this._res.get(key);
    if (v === undefined) {
      v = Math.trunc(this.P.resource(this.sc, ballsRemaining, wkts));
      this._res.set(key, v);
    }
    return v;
  }

  // [field-restriction windows [lo, hi, max_outside]], [powerplay windows [lo, hi, name]] (sim.Prepared.windows).
  windows(maxBalls) {
    let w = this._win.get(maxBalls);
    if (w === undefined) {
      const [fr, pp] = this._windows(maxBalls);
      w = new Windows(fr, pp, maxBalls === null ? 0 : maxBalls);
      this._win.set(maxBalls, w);
    }
    return w;
  }

  _windows(maxBalls) {
    const r = this.rules;
    if (!this.limited) return [[], []];
    const red = get(pyOr(get(r, 'pp_reduced'), {}), String(Math.floor(maxBalls / 6)));
    if (red !== null) {
      return [pyOr(get(red, 'field_restr'), []).map(([a, b, m]) => [a - 1, b, m]),
        pyOr(get(red, 'mandatory'), []).map(([a, b], i) => [a - 1, b, `pp${i + 1}`])];
    }
    const n = r.max_balls;
    return [pyOr(r.fielders_outside, []).map(([a, b, m]) => [scaleBall((a - 1) * 6, maxBalls, n), scaleBall(b * 6, maxBalls, n), m]),
      pyOr(r.pp_mandatory, []).map(([a, b], i) => [scaleBall((a - 1) * 6, maxBalls, n), scaleBall(b * 6, maxBalls, n), `pp${i + 1}`])];
  }

  // JS-only view keys for views built from foreign data (state.balls snapshots).
  addIdx(v) {
    const f = (p) => (p === null || p === undefined || !this.slotOf.has(p) ? -1 : this.slotOf.get(p));
    v.striker_idx = f(get(v, 'striker'));
    v.nonstriker_idx = f(get(v, 'nonstriker'));
    v.bowler_idx = f(get(v, 'bowler'));
    return v;
  }
}

// ---------------------------------------------------------------- innings

// Field-restriction windows fr [[lo, hi, max_outside]] and powerplay windows pp [[lo, hi, name]] of an innings
// of n legal balls (half-open legal-ball ranges), with the first-match lookups precomputed for 0 <= L < n.
class Windows {
  constructor(fr, pp, n) {
    this.fr = fr; this.pp = pp; this.n = n > 0 ? n : 0;
    this.frAt = new Array(this.n); this.ppAt = new Array(this.n);
    for (let L = 0; L < this.n; L++) { this.frAt[L] = this.frOf(L); this.ppAt[L] = this.ppOf(L); }
  }

  frOf(L) {
    for (const w of this.fr) if (w[0] <= L && L < w[1]) return w[2];
    return null;
  }

  ppOf(L) {
    for (const w of this.pp) if (w[0] <= L && L < w[1]) return w[2];
    return 'none';
  }
}
const NO_WINDOWS = new Windows([], [], 0);

function grow(a) {
  const b = new Int32Array(a.length * 2);
  b.set(a);
  return b;
}

class Innings {
  constructor(n) {
    this.nSlots = n;
    this.batRuns = new Int32Array(n); this.batBalls = new Int32Array(n); this.batArr = new Int32Array(n);
    this.batFours = new Int32Array(n); this.batSixes = new Int32Array(n); this.batOut = new Array(n).fill(null);
    this.batIn = new Uint8Array(n); this.batList = new Int32Array(n);
    this.bowlBalls = new Int32Array(n); this.bowlRuns = new Int32Array(n); this.bowlWkts = new Int32Array(n);
    this.bowlOvers = new Int32Array(n); this.bowlIn = new Uint8Array(n); this.bowlList = new Int32Array(n);
    this.outList = new Int32Array(n); this.unavail = new Uint8Array(n); this.unavList = new Int32Array(n);
    this.toCome = new Int32Array(n);
    this.overBowlers = new Int32Array(64); this.overScores = new Int32Array(64);
    this.reviews = new Int32Array(2); this.fail_reviews = new Int32Array(2);
    this.reset();
  }

  reset() {
    this.number = 0; this.so = 0; this.so_inn = 0; this.team = 0; this.opp = 1;
    this.runs = 0; this.wkts = 0; this.legal = 0; this.ball_in_over = 0; this.n_arrived = 0;
    this.max_balls = null; this.max_wkts = 10; this.target = null; this.timing = null; this.end = null;
    this.striker = NONE; this.nonstriker = NONE; this.bowler = NONE; this.last_bowler = NONE; this.umpire_offset = null;
    this.spell = 0; this.free_hit = false; this.second_new_ball = false; this.wkt_this_over = false;
    this.last_over_wkt = false; this.closed = false;
    this.p_runs = 0; this.p_balls = 0; this.ball_age = 0; this.over_runs = 0; this.last_over_runs = 0;
    this.extras = 0; this.byes = 0; this.agg_bat = 0; this.agg_opp = 0;
    if (this.nBat === undefined) {
      this.batRuns.fill(0); this.batBalls.fill(0); this.batArr.fill(0); this.batFours.fill(0); this.batSixes.fill(0);
      this.batOut.fill(null); this.batIn.fill(0);
      this.bowlBalls.fill(0); this.bowlRuns.fill(0); this.bowlWkts.fill(0); this.bowlOvers.fill(0); this.bowlIn.fill(0);
      this.unavail.fill(0);
    } else {                              // only batters, bowlers and unavailable slots can be non-zero
      for (let i = 0; i < this.nBat; i++) {
        const p = this.batList[i];
        this.batRuns[p] = this.batBalls[p] = this.batArr[p] = this.batFours[p] = this.batSixes[p] = this.batIn[p] = 0;
        this.batOut[p] = null;
      }
      for (let i = 0; i < this.nBowl; i++) {
        const p = this.bowlList[i];
        this.bowlBalls[p] = this.bowlRuns[p] = this.bowlWkts[p] = this.bowlOvers[p] = this.bowlIn[p] = 0;
      }
      for (let i = 0; i < this.nUnavail; i++) this.unavail[this.unavList[i]] = 0;
    }
    this.nBat = 0; this.nBowl = 0; this.nOut = 0; this.nUnavail = 0; this.tcHead = 0; this.tcLen = 0;
    this.nOvers = 0; this.nScores = 0; this.tcStamp = 0;
    this.reviews[0] = this.reviews[1] = 0; this.fail_reviews[0] = this.fail_reviews[1] = 0;
    this.windows = NO_WINDOWS;
    this.order = null;
    this.noOvers = false;
  }

  arrive(p) {
    this.n_arrived += 1;
    if (!this.batIn[p]) { this.batIn[p] = 1; this.batList[this.nBat++] = p; }
    this.batRuns[p] = 0; this.batBalls[p] = 0; this.batArr[p] = this.n_arrived; this.batOut[p] = null;
    this.batFours[p] = 0; this.batSixes[p] = 0;
  }

  addBowler(b) {
    if (!this.bowlIn[b]) { this.bowlIn[b] = 1; this.bowlList[this.nBowl++] = b; }
  }

  pushOver(b) {
    if (this.nOvers === this.overBowlers.length) this.overBowlers = grow(this.overBowlers);
    this.overBowlers[this.nOvers++] = b;
  }

  pushScore(x) {
    if (this.nScores === this.overScores.length) this.overScores = grow(this.overScores);
    this.overScores[this.nScores++] = x;
  }

  spellOf(b) {
    let n = 0, j = this.nOvers - 2;
    while (j >= 0 && this.overBowlers[j] === b) { n++; j -= 2; }
    return n;
  }

  oversMap(ids) {
    const m = new Map();
    for (let i = 0; i < this.nBowl; i++) { const b = this.bowlList[i]; m.set(ids[b], this.bowlOvers[b]); }
    return m;
  }
}

// ---------------------------------------------------------------- one simulation

// One simulated match (sim.Match), reusable: reset(sim, seed, opts) starts another simulation.
export class Match {
  constructor(pr) {
    this.pr = pr; this.P = pr.P; this.rules = pr.rules; this.sc = pr.sc;
    const n = pr.nSlots;
    this.streams = [0, 1, 2, 3, 4].map(() => new FastStream());
    this.main = [0, 1, 2, 3].map(() => new Innings(n));
    this.soPool = Array.from({ length: 2 * MAX_SUPER_OVERS }, () => new Innings(n));
    this.view = { ...pr.view0 };
    this.batForm = new Float64Array(2 * n); this.bowlForm = new Float64Array(2 * n);
    this.formU = new Float64Array(4 * n); this.formReady = new Uint8Array(n); this.formLazy = false;
    this.batFormV = Array.from({ length: n }, (_, i) => this.batForm.subarray(2 * i, 2 * i + 2));
    this.bowlFormV = Array.from({ length: n }, (_, i) => this.bowlForm.subarray(2 * i, 2 * i + 2));
    this.nm = pr.lat_m.length; this.ni = pr.lat_i.length;
    this.lat_m = new Float64Array(this.nm);
    this.lat_i = [0, 1, 2, 3].map(() => new Float64Array(this.ni));
    this.viewLat = new Float64Array(this.nm + this.ni);
    this.zeroLat = new Float64Array(this.nm + this.ni);
    this.zm = new Float64Array(4);
    this.u12 = new Float64Array(12); this.u4o = new Float64Array(4); this.u4i = new Float64Array(4);
    this.u64 = new Float64Array(64);
    this.e3 = new Float64Array(3); this.e9 = new Float64Array(9); this.e5 = new Float64Array(5);
    this.ccDtype = new CatCache(3, 1); this.ccOutcome = new CatCache(9, 2); this.ccKind = new CatCache(5, 1);
    this.w3 = new Float64Array(3); this.w4 = new Float64Array(4); this.w5 = new Float64Array(5);
    this.o2 = new Float64Array(2); this.o3 = new Float64Array(3); this.o4 = new Float64Array(4); this.o4b = new Float64Array(4);
    this.elig = new Int32Array(n + 1); this.ut = new Float64Array(n + 1);
    // bowler_utility candidates, one per (fielding team, slot), static fields set once
    this.candOf = [0, 1].map((t) => Array.from({ length: n }, (_, x) => ({ id: pr.ids[x], idx: x, option: pr.optIndex[t][x],
      overs: 0, balls: 0, runs: 0, wkts: 0, spell: 0, quota_left: null, overs_left: null, part_timer: pr.ptFlag[t][x] === 1,
      opened: false })));
    this.stats = new Float64Array(STAT_NAMES.length);
    this.stamp = 0; this.viewStamp = -1;
    this.toComeView = [];
    this.done = [];
    this.reset(0, 0);
  }

  reset(sim = 0, seed = 0, { script = null, log = null, state = null, views = null, stopAt = null } = {}) {
    const pr = this.pr;
    this.sim = sim; this.seed = seed;
    this.script = script === null ? null : [...script];
    this.log = log; this.views = views;
    if (this.script === null) for (let k = 0; k < 5; k++) this.streams[k].reseed(seed, sim, k);
    [this.sBall, this.sOver, this.sInn, this.sMatch, this.sPlayer] = this.streams;
    resetView(this.view, pr.view0);
    this.view.to_come = this.toComeView;
    this.viewStamp = -1;
    this.inn_team = null; this.toss = null; this.done.length = 0; this.cur = null;
    this.ovFresh = false; this.ovCur = null;
    this.result = null; this.tie_before = false; this.main_done = false; this.followed_on = false;
    this.so_k = 0; this.so_first = null; this.so_target = null;
    this.match_legal = 0; this.changeovers = 0;
    this.avail = null; this.cum = null; this.suffix = null;
    this.A_total = 0; this.day = 0; this.play_start_day = 0;
    this.lengths = null; this.R = [null, null]; this.pending = []; this.revised_pre = false;
    this.lat_m.fill(0.0);
    for (const a of this.lat_i) a.fill(0.0);
    this.coin_u = null; this.coin_forced = null;
    this.stats.fill(0);
    this.deliveries = 0;
    this.state0 = state;
    this.stop_at = stopAt;
    this.stopped = false;
    return this;
  }

  // --- script plumbing
  _next(ev) {
    if (this.script === null) return null;
    if (!this.script.length) throw new Stop(ev);
    const f = this.script.shift();
    if (get(f, 'e') !== ev) throw new ScriptError(`script has ${pyRepr(get(f, 'e'))} where the engine expects a ${pyRepr(ev)} event`);
    return { ...f };
  }

  static _need(F, key) {
    if (!has(F, key)) throw new ScriptError(`scripted ${get(F, 'e')} event needs ${pyRepr(key)}`);
    const x = F[key];
    delete F[key];
    return x;
  }

  static _pop(F, key, d) {
    if (!has(F, key)) return d;
    const x = F[key];
    delete F[key];
    return x;
  }

  static _done(F) {
    if (F === null) return;
    const left = Object.keys(F).filter((k) => k !== 'e').sort();
    if (left.length) throw new ScriptError(`scripted ${F.e} event has unused decisions ${pyRepr(left)}`);
  }

  // --- driver
  play() {
    try {
      if (this.state0 !== null) this._resume(this.state0);
      else this._startMatch();
      while (this.result === null) {
        if (this.cur === null) {
          if (this.so_k) this._startSoInnings();
          else this._startInnings();
          continue;
        }
        const sa = this.stop_at;
        if (sa !== null && this.cur.so === 0 &&
          (this.cur.number > sa[0] || (this.cur.number === sa[0] && this.cur.legal >= sa[1]))) {
          this.stopped = true;
          break;
        }
        const overDone = this._delivery();
        const c = this.cur;
        if (c.end !== null) this._finishInnings();
        if (this.result === null && !this.main_done && c.so === 0 && (overDone || c.end !== null)) {
          this._overEvent();
          if (c.end !== null && !c.closed) this._finishInnings();
        }
        if (c.end !== null) this.cur = null;
      }
    } catch (e) {
      if (!(e instanceof Stop)) throw e;
      if (e.ev !== 'ball') throw new ScriptError(`script ended before a ${pyRepr(e.ev)} event; end scripts before a delivery`);
    }
    if (this.result !== null && this.log !== null) this.log.push({ e: 'end', ...this.result });
    return this;
  }

  // --- match start
  // Player form (sim.Match._draw_forms): the 4 uniforms of every slot are drawn here in slot order; the
  // Box-Muller transform of a slot runs on its first use (_form), which gives the same values.
  _drawForms() {
    const n = this.pr.nSlots;
    this.formLazy = this.script === null && this.sc.draw_player_uncertainty;
    if (this.script === null) this.sPlayer.fill(this.formU, 4 * n);
    this.formReady.fill(0);
    if (!this.formLazy) for (let i = 0; i < n; i++) this._form(i);
  }

  _form(i) {
    const sl0 = this.pr.formSliders, u = this.formU;
    let b0 = sl0[4 * i], b1 = sl0[4 * i + 1], b2 = sl0[4 * i + 2], b3 = sl0[4 * i + 3];
    if (this.formLazy) {
      let z = normalInto(u[4 * i], u[4 * i + 1]);
      b0 += z[0]; b1 += z[1];
      z = normalInto(u[4 * i + 2], u[4 * i + 3]);
      b2 += z[0]; b3 += z[1];
    }
    this.batForm[2 * i] = b0; this.batForm[2 * i + 1] = b1;
    this.bowlForm[2 * i] = b2; this.bowlForm[2 * i + 1] = b3;
    this.formReady[i] = 1;
  }

  _priorLatents(um) {
    const pr = this.pr, zm = this.zm, mu = pr.latMu, sd = pr.latSdM, sdi = pr.latSdI, known = pr.pitchKnown;
    if (um !== null) {
      let z = normalInto(um[M_LAT], um[M_LAT + 1]);
      zm[0] = z[0]; zm[1] = z[1];
      z = normalInto(um[M_LAT + 2], um[M_LAT + 3]);
      zm[2] = z[0]; zm[3] = z[1];
    }
    for (let j = 0; j < this.nm; j++) this.lat_m[j] = known || um === null ? mu[j] : mu[j] + sd[j] * zm[j];
    for (let k = 0; k < 4; k++) {
      let z0 = 0.0, z1 = 0.0;
      if (um !== null) { const z = normalInto(um[M_INN_LAT + 2 * k], um[M_INN_LAT + 2 * k + 1]); z0 = z[0]; z1 = z[1]; }
      const li = this.lat_i[k];
      if (this.ni > 0) li[0] = sdi[0] * z0;
      if (this.ni > 1) li[1] = sdi[1] * z1;
    }
  }

  _setClock(avail) {
    const sc = this.sc, P = this.P;
    this.avail = avail.map((a) => Math.trunc(a));
    const cum = [];
    let c = 0;
    for (const a of this.avail) { c += a; cum.push(c); }
    this.cum = cum; this.A_total = c;
    const means = avail.map((_, d) => P.day_availability_mean(sc, d + 1));
    const suffix = new Array(avail.length).fill(0.0);
    let s = 0.0;
    for (let d = avail.length - 1; d >= 0; d--) { suffix[d] = s; s += means[d]; }
    this.suffix = suffix;
    const ps = this.avail.findIndex((a) => a > 0);
    this.play_start_day = ps >= 0 ? ps : avail.length - 1;
    this.day = 0;
  }

  _startMatch() {
    const sc = this.sc, P = this.P, v = this.view, pr = this.pr;
    const F = this._next('match');
    const rec = this.log !== null ? { e: 'match' } : null;
    let um = null;
    if (F === null) um = this.sMatch.fill(this.u64, 64);
    this._drawForms();
    const toss = sc.toss;
    let winner, bat;
    if (toss !== null) {
      winner = toss.winner; bat = toss.decision === 'bat';
    } else if (F !== null) {
      winner = Match._need(F, 'toss_winner'); bat = Match._need(F, 'toss_bat');
    } else {
      winner = um[M_TOSS] < 0.5 ? 0 : 1;
      v.toss_winner = winner;
      bat = um[M_TOSS_BAT] < P.toss_bat_prob(v);
    }
    v.toss_winner = winner;
    const first = pyBool(bat) ? winner : 1 - winner;
    this.toss = { winner, decision: pyBool(bat) ? 'bat' : 'field' };
    this.inn_team = pr.isTest ? [first, 1 - first, first, 1 - first] : [first, 1 - first];
    this._priorLatents(um);
    if (pr.isTest) {
      const days = this.rules.test_days;
      if (days > MAX_DAYS) throw new Error(`at most ${MAX_DAYS} scheduled days`);
      const avail = F !== null ? Match._need(F, 'avail') : [...Array(days).keys()].map((d) => P.day_availability(sc, d + 1, um[M_DAYS + d]));
      this._setClock(avail);
    } else {
      const n = this.rules.max_balls;
      this.lengths = [n, n];
      this.R = [pr.res(n, 0), null];
      const src = F !== null ? Match._pop(F, 'interruptions', []) : P.interruption_schedule(sc, 0, um.subarray(M_RAIN, M_RAIN + 16));
      this.pending = src.map((x) => ({ ...x }));
    }
    this.coin_u = um !== null ? um[M_COIN] : null;
    this.coin_forced = F !== null ? Match._pop(F, 'coin', null) : null;
    Match._done(F);
    if (rec !== null) {
      Object.assign(rec, { toss_winner: winner, toss_bat: bat, bat_first: first });
      if (F === null) rec.latent = [...this.lat_m, ...this.lat_i.flatMap((row) => [...row])];
      if (pr.isTest) rec.avail = [...this.avail];
      else rec.interruptions = this.pending.map((x) => ({ ...x }));
      this.log.push(rec);
    }
    while (pr.limited && this.pending.length && this.pending[0].start <= 0 && this.result === null) {
      applyInterruption(this, this.pending.shift().lost);
    }
  }

  // --- innings
  _agg(team) {
    let s = 0;
    for (const i of this.done) if (i.team === team) s += i.runs;
    return s;
  }

  _newInnings(k, team) {
    const pr = this.pr;
    this.ovFresh = false;
    const c = this.main[k - 1];
    c.reset();
    c.number = k; c.team = team; c.opp = 1 - team;
    c.order = pr.ordersIdx[team];
    const ab = pr.absentFlag[team];
    for (let i = 0; i < pr.nSlots; i++) if (ab[i]) { c.unavail[i] = 1; c.unavList[c.nUnavail++] = i; }
    for (const p of c.order) if (!c.unavail[p]) c.toCome[c.tcLen++] = p;
    c.tcStamp = ++this.stamp;
    for (let i = 0; i < Math.min(2, c.tcLen); i++) c.arrive(c.toCome[i]);
    c.striker = c.toCome[c.tcHead++];
    c.nonstriker = c.toCome[c.tcHead++];
    c.reviews[0] = c.reviews[1] = pr.rpi;
    c.agg_bat = this._agg(team); c.agg_opp = this._agg(1 - team);
    if (pr.limited) {
      c.max_balls = this.lengths[k - 1];
      if (k === 2) {
        this.R[1] = pr.res(c.max_balls, 0);
        c.target = revisedTarget(this.done[0].runs, this.R[0], this.R[1], pr.G);
        c.timing = this.revised_pre && this.R[1] !== this.R[0] ? 'pre_inn2' : 'original';
      }
    } else if (k === 4) {
      c.target = c.agg_opp - c.agg_bat + 1;
      c.timing = 'original';
    }
    c.windows = pr.windows(c.max_balls);
    return c;
  }

  _inningsView(c) {
    const v = this.view, pr = this.pr;
    v.innings = c.number;
    v.super_over = c.so; v.so_innings = c.so_inn;
    v.bat_team = c.team; v.bowl_team = c.opp;
    v.bat_home_status = pr.home_status[c.team]; v.bowl_home_status = pr.home_status[c.opp];
    v.target_timing = c.timing;
    v.followed_on = this.followed_on;
    v.prev_innings = this.done.map((i) => [i.team, i.runs, i.wkts, i.legal, i.end]);
    v.umpire_offset = c.umpire_offset;
    const k = c.so === 0 ? c.number : this._mainInningsOf(c.team);
    const L = this.viewLat, nm = this.nm, li = this.lat_i[k - 1];
    for (let j = 0; j < nm; j++) L[j] = this.lat_m[j];
    for (let j = 0; j < this.ni; j++) L[nm + j] = li[j];
    v.latent = L;
  }

  _mainInningsOf(team) {
    return this.inn_team.indexOf(team) + 1;
  }

  _startInnings() {
    const pr = this.pr, P = this.P, v = this.view;
    const k = this.done.length + 1;
    const F = this._next('innings');
    let u = null;
    if (F === null) u = this.sInn.fill(this.u4i, 4);
    const rec = this.log !== null ? { e: 'innings', n: k, so: 0 } : null;
    if (k > 1) this.changeovers += 1;
    if (pr.isTest && this._used() >= this.A_total) {
      Match._done(F);
      if (rec !== null) this.log.push(rec);
      this._setResult('draw');
      return;
    }
    let team = this.inn_team[k - 1];
    if (pr.isTest && k === 3) {
      const a = this.inn_team[0], b = this.inn_team[1];
      const lead = this.done[0].runs - this.done[1].runs;
      const thr = followOnThreshold(this.rules.follow_on_lead, this.avail.length - this.play_start_day);
      if (thr !== null && lead >= thr) {
        const c = this._newInnings(k, a);
        this.cur = c;
        this._inningsView(c);
        this._refresh();
        const fo = F !== null ? Match._need(F, 'follow_on') : u[0] < P.follow_on_prob(v);
        if (rec !== null) rec.follow_on = pyBool(fo);
        if (pyBool(fo)) {
          this.inn_team[2] = b; this.inn_team[3] = a;
          this.followed_on = true;
          team = b;
        }
      }
    }
    const c = this._newInnings(k, team);
    this.cur = c;
    c.umpire_offset = F !== null ? Match._need(F, 'umpire_offset') : (u[1] < 0.5 ? 0 : 1);
    this._inningsView(c);
    this._refresh();
    this._chooseBowler(u, 2, F, rec);
    Match._done(F);
    if (rec !== null) {
      rec.team = team; rec.umpire_offset = c.umpire_offset;
      this.log.push(rec);
    }
  }

  // Super-over selection: expected bat runs per legal ball for striker slot (-1 = average batter) against
  // bowler slot (-1 = average bowler), zero latents and zero form (sim.Match._expected_runs).
  _expectedRuns(striker, bowler) {
    const v = this.view, pr = this.pr;
    const keep = [v.striker, v.bowler, v.striker_form, v.bowler_form, v.latent, v.dtype, v.striker_pos, v.striker_runs,
      v.striker_balls, v.striker_arrival, v.bowler_balls, v.bowler_runs, v.bowler_wkts, v.bowler_overs, v.bowler_spell,
      v.bowler_part_timer, v.striker_idx, v.bowler_idx];
    v.striker = striker < 0 ? null : pr.ids[striker];
    v.bowler = bowler < 0 ? null : pr.ids[bowler];
    v.striker_idx = striker; v.bowler_idx = bowler;
    v.striker_pos = striker < 0 ? null : pr.posIdx[striker];
    v.striker_runs = 0; v.striker_balls = 0; v.striker_arrival = striker < 0 ? null : 1;
    v.striker_form = ZERO2; v.bowler_form = bowler < 0 ? null : ZERO2;
    if (bowler < 0) v.bowler_balls = v.bowler_runs = v.bowler_wkts = v.bowler_overs = v.bowler_spell = null;
    else v.bowler_balls = v.bowler_runs = v.bowler_wkts = v.bowler_overs = v.bowler_spell = 0;
    v.bowler_part_timer = false;
    v.latent = this.zeroLat;
    v.dtype = 'legal';
    const p = softmax(this.P.outcome_eta(v, this.e9));
    [v.striker, v.bowler, v.striker_form, v.bowler_form, v.latent, v.dtype, v.striker_pos, v.striker_runs,
      v.striker_balls, v.striker_arrival, v.bowler_balls, v.bowler_runs, v.bowler_wkts, v.bowler_overs, v.bowler_spell,
      v.bowler_part_timer, v.striker_idx, v.bowler_idx] = keep;
    this.ovFresh = false;
    return pySum(p.map((pk, k) => pk * NOMINAL_RUNS[k]));
  }

  _startSoInnings() {
    const pr = this.pr;
    const F = this._next('innings');
    let u = null;
    if (F === null) u = this.sInn.fill(this.u4i, 4);
    const first = this.so_target === null;
    const team = first ? this.so_first : 1 - this.so_first;
    const c = this.soPool[2 * (this.so_k - 1) + (first ? 0 : 1)];
    c.reset();
    this.ovFresh = false;
    c.number = 0; c.so = this.so_k; c.so_inn = first ? 1 : 2; c.team = team; c.opp = 1 - team;
    c.max_balls = 6; c.max_wkts = 2;
    if (first) { c.target = null; c.timing = null; } else { c.target = this.so_target; c.timing = 'original'; }
    c.reviews[0] = c.reviews[1] = pyBool(this.rules.drs_enabled) ? 1 : 0;
    c.agg_bat = this._agg(team); c.agg_opp = this._agg(1 - team);
    const fo = this.rules.fielders_outside;
    c.windows = new Windows(pyBool(fo) ? [[0, 6, fo[fo.length - 1][2]]] : [], [], 6);
    c.umpire_offset = F !== null ? Match._need(F, 'umpire_offset') : (u[1] < 0.5 ? 0 : 1);
    const ab = pr.absentFlag[team];
    const order = [...pr.ordersIdx[team]].filter((p) => !ab[p]);
    c.striker = order[0]; c.nonstriker = order[1];
    c.batArr[order[0]] = 1; c.batArr[order[1]] = 2;
    this.cur = c;
    this._inningsView(c);
    this._refresh();
    const er = order.map((p, i) => [-this._expectedRuns(p, -1), i, p]);
    er.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const top = er.slice(0, 3).map((x) => x[2]);
    c.batArr[order[0]] = 0; c.batArr[order[1]] = 0;
    c.order = top; c.nBat = 0; c.n_arrived = 0;
    for (const p of top.slice(0, 2)) c.arrive(p);
    c.striker = top[0]; c.nonstriker = top[1];
    c.tcHead = 0; c.tcLen = 0;
    for (const p of top.slice(2)) c.toCome[c.tcLen++] = p;
    c.tcStamp = ++this.stamp;
    this._refresh();
    const kp = pr.keeperIdx[c.opp];
    const cands = [...pr.xiIdx[c.opp]].filter((p) => p !== kp);
    const eb = cands.map((p, i) => [this._expectedRuns(-1, p), i, p]);
    eb.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    c.bowler = eb[0][2];
    c.addBowler(c.bowler);
    this.ovFresh = false;
    Match._done(F);
    if (this.log !== null) {
      this.log.push({ e: 'innings', n: 0, so: c.so, team, umpire_offset: c.umpire_offset, batters: top.map((p) => pr.ids[p]),
        bowler: pr.ids[c.bowler] });
    }
  }

  // --- bowler choice
  _chooseBowler(ua, ui, F, rec) {   // the uniform is ua[ui] (ua null in scripted mode)
    const c = this.cur, pr = this.pr, P = this.P, v = this.view, ids = pr.ids;
    const opts = pr.optsIdx[c.opp];
    const nOvers = pr.limited ? Math.floor(c.max_balls / 6) : null;
    const elig = this.elig;
    let m = eligibleInto(opts, opts.length, c.bowlOvers, c.bowlList, c.nBowl, c.last_bowler, nOvers, c.nOvers, pr.qrule, elig);
    const fallback = m === 0;
    if (m === 0) {
      this.stats[S_FALLBACK] += 1;
      const ov = c.oversMap(ids);
      const lb = c.last_bowler;
      for (const b of opts) if (b !== lb && (quotaLeft(ov, ids[b], nOvers, pr.qrule) || 0) > 0) elig[m++] = b;
      if (m === 0) for (const b of opts) if (b !== lb) elig[m++] = b;
      if (m === 0) for (const b of opts) elig[m++] = b;
    }
    let b;
    if (F !== null) {
      const id = Match._need(F, 'bowler');
      const bi = pr.slotOf.has(id) ? pr.slotOf.get(id) : -1;
      let ok = false;
      for (let i = 0; i < m; i++) if (elig[i] === bi) ok = true;
      if (!ok) throw new ScriptError(`forced bowler ${pyRepr(id)} is not eligible; eligible: ${pyRepr(Array.from(elig.subarray(0, m), (x) => ids[x]))}`);
      b = bi;
    } else {
      let base = 0, free = 0;
      if (nOvers !== null) {
        if (fallback) {
          [base, free] = quota(nOvers, pr.qrule);
          for (let i = 0; i < c.nBowl; i++) if (c.bowlOvers[c.bowlList[i]] > base) free--;
        } else {
          base = Q_BASE; free = Q_FREE;
        }
      }
      const ob = c.overBowlers, no = c.nOvers, cands = this.candOf[c.opp];
      const left = nOvers === null ? null : nOvers - no;
      for (let i = 0; i < m; i++) {               // slots that have not bowled hold zeros in the bowl arrays
        const x = elig[i], cd = cands[x];
        const ovs = c.bowlOvers[x];
        cd.overs = ovs; cd.balls = c.bowlBalls[x]; cd.runs = c.bowlRuns[x]; cd.wkts = c.bowlWkts[x];
        cd.spell = c.spellOf(x);
        cd.quota_left = nOvers === null ? null : ovs > base ? 0 : base - ovs + (free > 0 ? 1 : 0);
        cd.overs_left = left;
        cd.opened = (no > 0 && ob[0] === x) || (no > 1 && ob[1] === x);
        this.ut[i] = P.bowler_utility(v, cd);
      }
      b = elig[catEta(ua[ui], this.ut, m)];
    }
    c.bowler = b;
    c.spell = c.spellOf(b);
    c.addBowler(b);
    this.ovFresh = false;
    if (rec !== null) {
      rec.bowler = ids[b];
      rec.elig = Array.from(elig.subarray(0, m), (x) => ids[x]);
    }
  }

  // --- view
  _used() {
    return this.match_legal + 12 * this.changeovers;
  }

  _refresh() {
    const c = this.cur, v = this.view, pr = this.pr, ids = pr.ids;
    const st = c.striker, ns = c.nonstriker, bw = c.bowler;
    const L = c.legal, ov = c.nOvers;
    if (!this.ovFresh || this.ovCur !== c) {
      // fields that change only at over ends, bowler choice, new balls, revisions and innings starts, each of
      // which clears ovFresh
      v.over = ov; v.innings_overs = ov; v.max_balls = c.max_balls; v.target = c.target;
      v.bowler = bw < 0 ? null : ids[bw]; v.bowler_idx = bw;
      if (bw < 0) {
        v.bowler_balls = v.bowler_runs = v.bowler_wkts = v.bowler_overs = null;
        v.bowler_spell = v.bowler_form = null;
        v.bowler_part_timer = false;
      } else {
        v.bowler_overs = c.bowlOvers[bw];
        v.bowler_spell = c.spell;
        if (!this.formReady[bw]) this._form(bw);
        v.bowler_form = this.bowlFormV[bw];
        v.bowler_part_timer = pr.ptFlag[c.opp][bw] === 1;
      }
      v.ball_age_overs = c.ball_age; v.second_new_ball = c.second_new_ball;
      v.bowl_end_umpire = pr.hasUmpires && c.umpire_offset !== null ? v.umpires[(ov + c.umpire_offset) % 2] : null;
      v.last_over_runs = c.last_over_runs; v.last_over_wkt = c.last_over_wkt;
      this.ovFresh = true; this.ovCur = c;
    }
    v.legal_balls = L; v.ball_in_over = c.ball_in_over;
    v.balls_remaining = c.max_balls === null ? null : c.max_balls - L;
    v.runs = c.runs; v.wkts = c.wkts; v.unavailable = c.wkts + c.nUnavail;
    v.runs_required = c.target === null ? null : c.target - c.runs;
    v.striker = ids[st]; v.nonstriker = ids[ns];
    v.striker_idx = st; v.nonstriker_idx = ns;
    v.striker_runs = c.batRuns[st]; v.striker_balls = c.batBalls[st]; v.striker_arrival = c.batArr[st];
    v.nonstriker_runs = c.batRuns[ns]; v.nonstriker_balls = c.batBalls[ns]; v.nonstriker_arrival = c.batArr[ns];
    v.striker_pos = pr.posIdx[st]; v.nonstriker_pos = pr.posIdx[ns];
    if (bw >= 0) { v.bowler_balls = c.bowlBalls[bw]; v.bowler_runs = c.bowlRuns[bw]; v.bowler_wkts = c.bowlWkts[bw]; }
    v.partnership_runs = c.p_runs; v.partnership_balls = c.p_balls;
    v.free_hit = c.free_hit;
    const W = c.windows;
    if (L < W.n) { v.field_restr = W.frAt[L]; v.pp_window = W.ppAt[L]; } else { v.field_restr = W.frOf(L); v.pp_window = W.ppOf(L); }
    v.reviews_bat = c.reviews[0]; v.reviews_bowl = c.reviews[1];
    v.bat_fail_reviews = c.fail_reviews[0]; v.bowl_fail_reviews = c.fail_reviews[1];
    v.match_legal_balls = this.match_legal;
    if (pr.isTest && this.cum !== null) {
      const used = this._used(), cum = this.cum;
      let d = this.day;
      const last = cum.length - 1;
      while (d < last && used >= cum[d]) d++;
      this.day = d;
      const prev = d ? cum[d - 1] : 0;
      v.clock_used = used; v.est_day = d + 1;
      v.overs_into_day = Math.floor(Math.max(0, used - prev) / 6);
      v.exp_overs_left = (cum[d] + this.suffix[d] - used) / 6;
    }
    v.lead = c.agg_bat + c.runs - c.agg_opp;
    if (!this.formReady[st]) this._form(st);
    if (!this.formReady[ns]) this._form(ns);
    v.striker_form = this.batFormV[st]; v.nonstriker_form = this.batFormV[ns];
    if (c.tcStamp !== this.viewStamp) {
      const a = v.to_come;
      a.length = 0;
      for (let i = c.tcHead; i < c.tcLen; i++) a.push(ids[c.toCome[i]]);
      this.viewStamp = c.tcStamp;
    }
    v.dtype = null;
  }

  // --- one delivery (plan 9.2)
  _delivery() {
    const c = this.cur, P = this.P, v = this.view, r = this.rules, pr = this.pr, ids = pr.ids, stats = this.stats;
    const F = this._next('ball');
    let u = null;
    if (F === null) u = this.sBall.fill(this.u12, 12);
    const rec = this.log !== null ? { e: 'ball', n: c.number, so: c.so, lb: c.legal, s: ids[c.striker], ns: ids[c.nonstriker],
      b: c.bowler < 0 ? null : ids[c.bowler] } : null;
    this.deliveries += 1;
    this._refresh();
    const st = c.striker, ns = c.nonstriker, bw = c.bowler;
    const fh = c.free_hit;
    const drs = pr.drsOn && !fh;
    const retain = pr.retain;
    // 2. dtype
    let d;
    if (F !== null) {
      const x = Match._need(F, 'dtype');
      if (!has(DT, x)) throw new Error(`KeyError: ${pyRepr(x)}`);
      d = DT[x];
    } else {
      d = this.ccDtype.draw(u, 0, P.dtype_eta(v, this.e3));
    }
    if (rec !== null) rec.dtype = DTYPES[d];
    let bat = 0, byes = 0, wides = 0, pen = 0;
    let cls = -1, kind = -1, victim = NONE, boundary = false, fhNew = false;
    let clsOn = -1, roRuns = 0;
    if (d === WIDE) {                                                 // 3. wide
      v.dtype = 'wide';
      const w = P.wide_wkt(v, this.w3);
      if (fh) w[1] = 0.0;
      let ww;
      if (F !== null) {
        const x = Match._need(F, 'wide_wkt');
        if (!has(WW, x)) throw new Error(`KeyError: ${pyRepr(x)}`);
        ww = WW[x];
        if (w[ww] <= 0.0) throw new ScriptError(`wide wicket ${pyRepr(WIDE_WKTS[ww])} is impossible here`);
      } else {
        ww = catW(u[3], w, 3);
      }
      const k = F !== null ? Match._need(F, 'runs') : 1 + catW(u[2], P.wide_runs(v, ww, this.w5), 5);
      wides = k; boundary = k === 5;
      if (rec !== null) { rec.wide_wkt = WIDE_WKTS[ww]; rec.runs = k; }
      if (ww === 1) { victim = st; kind = STUMPED; } else if (ww === 2) { victim = RO_PENDING; kind = RO; roRuns = k - 1; } else if (drs && c.reviews[1] > 0) this._spec(F, u, rec, 9, retain);
    } else {
      v.dtype = d === NOBALL ? 'noball' : 'legal';
      const eta = P.outcome_eta(v, this.e9);
      if (d === NOBALL || fh) eta[OUT] += MASK_OFFSET;
      if (F !== null) {
        cls = Match._need(F, 'cls');
        if (cls === OUT && (d === NOBALL || fh)) throw new ScriptError('a bowler-credited out is masked on no-balls and free hits');
        if (!(cls >= 0 && cls <= 8)) throw new ScriptError(`outcome class ${pyRepr(cls)} out of range`);
      } else {
        cls = this.ccOutcome.draw(u, 1, eta);
      }
      clsOn = cls;
      if (rec !== null) rec.cls = cls;
      if (d === NOBALL) {                                             // 4. no-ball
        pen = r.noball_runs;
        if (r.free_hit === 'all_noballs') fhNew = true;
        else if (r.free_hit === 'front_foot') {
          fhNew = F !== null ? Match._need(F, 'free_hit') : u[3] < r.p_free_hit_given_nb;
          if (rec !== null) rec.free_hit = pyBool(fhNew);
        }
      } else if (cls === OUT) {                                       // 5. legal ball, on-field out
        if (F !== null) {
          const x = Match._need(F, 'kind');
          if (!has(KI, x)) throw new Error(`KeyError: ${pyRepr(x)}`);
          kind = KI[x];
        } else {
          kind = this.ccKind.draw(u, 3, P.wk_eta(v, this.e5));
        }
        if (rec !== null) rec.kind = KIND_ALL[kind];
        if (drs && (kind === CAUGHT || kind === LBW) && c.reviews[0] > 0) {
          const q3 = P.drs_bat(v, kind, this.o3);
          const q = q3[0], po = q3[1], pu = q3[2];
          const rv = F !== null ? Match._pop(F, 'bat_review', false) : u[6] < q;
          if (rec !== null) rec.bat_review = pyBool(rv);
          if (pyBool(rv)) {
            stats[S_BAT_REV] += 1;
            const ovt = F !== null ? Match._need(F, 'overturned') : u[7] < Math.min(1.0, po * pr.acc);
            if (rec !== null) rec.overturned = pyBool(ovt);
            if (pyBool(ovt)) {
              stats[S_BAT_OVT] += 1;
              cls = DOT; kind = -1;
            } else {
              let uc = false;
              if (kind === LBW) {
                uc = F !== null ? Match._need(F, 'ucall') : u[8] < Math.min(1.0, pu * pr.ucm);
                if (rec !== null) rec.ucall = pyBool(uc);
              }
              stats[S_BAT_UC] += pyBool(uc) ? 1 : 0;
              if (!(pyBool(uc) && retain)) c.reviews[0] -= 1;
              if (!pyBool(uc)) c.fail_reviews[0] += 1;
            }
          }
        }
        if (cls === OUT) victim = st;
      } else if (!fh) {                                               // 5. legal non-wicket: fielding reviews
        let specOk = drs && c.reviews[1] > 0;
        if (cls === DOT || cls === BYES) {
          const df = P.drs_field(v, cls, this.o4);
          const lam = df[0], lbwShare = df[1];
          const ms = F !== null ? Match._pop(F, 'missed', false) : u[9] < Math.min(1.0, lam * pr.acc);
          if (rec !== null) rec.missed = pyBool(ms);
          if (pyBool(ms) && drs && c.reviews[1] > 0) {
            const lb = F !== null ? Match._need(F, 'missed_lbw') : u[10] < lbwShare;
            if (rec !== null) rec.missed_lbw = pyBool(lb);
            stats[S_FIELD_OK] += 1;
            cls = OUT; kind = pyBool(lb) ? LBW : CAUGHT; victim = st; specOk = false;
          } else if (pyBool(ms)) stats[S_MISSED] += 1;
        }
        if (specOk && cls !== RUN_OUT) this._spec(F, u, rec, cls, retain, cls === DOT || cls === BYES ? this.o4 : null);
      }
      // 6. exact runs
      if (cls === ONE || cls === TWO || cls === THREE) bat = cls;
      else if (cls === FOUR || cls === SIX) {
        const p57 = P.runs5_7(v, this.o2);
        if (F !== null) bat = Match._need(F, 'runs');
        else bat = cls === FOUR ? (u[2] < p57[0] ? 5 : 4) : (u[2] < p57[1] ? 7 : 6);
        boundary = true;
      } else if (cls === BYES) {
        byes = F !== null ? Match._need(F, 'runs') : 1 + catW(u[2], P.bye_runs(v, this.w5), 5);
        boundary = byes >= 4;
      } else if (cls === RUN_OUT) {
        roRuns = bat = F !== null ? Match._need(F, 'runs') : catW(u[2], P.runout_runs(v, this.w4), 4);
        victim = RO_PENDING; kind = RO;
      }
      if (rec !== null && (cls === FOUR || cls === SIX || cls === BYES || cls === RUN_OUT)) rec.runs = bat + byes;
    }
    // 7. chase completion
    let won = false;
    if (c.target !== null && c.runs + bat + byes + wides + pen >= c.target) {
      won = true;
      const need = c.target - c.runs;
      if (!boundary) {
        if (d === WIDE) wides = 1 + Math.min(wides - 1, Math.max(need - 1, 0));
        else {
          const allow = Math.max(need - pen, 0);
          bat = Math.min(bat, allow); byes = Math.min(byes, allow);
        }
      }
      victim = NONE; kind = -1;
    }
    const total = bat + byes + wides + pen;
    const ran = bat + byes + (wides ? wides - 1 : 0);
    // 10. counters (the pre-ball striker and bowler)
    if (d !== WIDE) {
      c.batBalls[st] += 1;
      c.batRuns[st] += bat;
      if (boundary && (bat === 4 || bat === 5)) c.batFours[st] += 1;
      else if (boundary && (bat === 6 || bat === 7)) c.batSixes[st] += 1;
      c.p_balls += 1;
    }
    c.bowlRuns[bw] += bat + wides + pen;
    c.runs += total;
    c.extras += byes + wides + pen;
    c.byes += byes;
    c.p_runs += total;
    c.over_runs += total;
    if (d === LEGAL) {
      c.legal += 1;
      c.ball_in_over += 1;
      c.bowlBalls[bw] += 1;
      if (c.so === 0) this.match_legal += 1;
    }
    // 8. wicket
    let allOut = false;
    if (victim !== NONE) {
      if (kind === RO) {
        const so = F !== null ? Match._need(F, 'ro_striker') : u[4] < P.runout_who(v, roRuns);
        if (rec !== null) rec.ro_striker = pyBool(so);
        victim = pyBool(so) ? st : ns;
      }
      c.wkts += 1;
      c.wkt_this_over = true;
      c.batOut[victim] = KIND_ALL[kind];
      c.outList[c.nOut++] = victim;
      if (kind !== RO) c.bowlWkts[bw] += 1;
      stats[(d === WIDE ? S_KIND_WIDE : S_KIND) + kind] += 1;
      c.p_runs = 0; c.p_balls = 0;
      const nb = c.tcHead < c.tcLen ? c.toCome[c.tcHead] : NONE;
      if (nb === NONE || c.wkts >= c.max_wkts) allOut = true;
      else {
        c.tcHead += 1;
        c.tcStamp = ++this.stamp;
        c.arrive(nb);
        if (kind === RO) {
          const surv = victim === st ? ns : st;
          const p = P.runout_new_on_strike(v, victim === st ? 0 : 1, Math.min(roRuns, 2));
          const nos = F !== null ? Match._need(F, 'ro_new_on_strike') : u[5] < p;
          if (rec !== null) rec.ro_new_on_strike = pyBool(nos);
          if (pyBool(nos)) { c.striker = nb; c.nonstriker = surv; } else { c.striker = surv; c.nonstriker = nb; }
        } else if (kind === CAUGHT && pr.crossing) {
          const cr = F !== null ? Match._need(F, 'crossed') : u[5] < P.p_crossed(v);
          if (rec !== null) rec.crossed = pyBool(cr);
          if (pyBool(cr)) { c.striker = ns; c.nonstriker = nb; } else { c.striker = nb; c.nonstriker = ns; }
        } else {
          c.striker = nb;
        }
      }
    } else if (ran % 2 === 1) {                                       // 9. no wicket: swap on odd runs run
      c.striker = ns; c.nonstriker = st;
    }
    // 11. end checks
    if (won) c.end = 'target';
    else if (allOut) c.end = 'all_out';
    else if (c.max_balls !== null && c.legal >= c.max_balls) c.end = 'balls';
    else if (pr.isTest && c.so === 0 && this._used() >= this.A_total) c.end = 'clock';
    // 12. over end
    const overDone = d === LEGAL && c.ball_in_over === 6;
    if (overDone) {
      c.pushScore(c.runs);
      c.pushOver(bw);
      c.bowlOvers[bw] += 1;
      c.last_over_runs = c.over_runs; c.last_over_wkt = c.wkt_this_over;
      c.over_runs = 0; c.wkt_this_over = false;
      c.ball_age += 1;
      if (pr.topup && c.nOvers === 80 && pr.rpi) c.reviews[0] = c.reviews[1] = pr.rpi;
      if (c.end === null) {
        const t = c.striker; c.striker = c.nonstriker; c.nonstriker = t;
        c.ball_in_over = 0;
        c.last_bowler = bw; c.bowler = NONE;
      }
      this.ovFresh = false;
    }
    // 13. free hit for the next delivery
    c.free_hit = d === LEGAL ? false : (fh || fhNew);
    if (this.views !== null && clsOn >= 0 && c.so === 0) {
      const snap = {};
      for (const k in v) {
        if (VIEW_STATIC.has(k)) continue;
        const x = v[k];
        snap[k] = ArrayBuffer.isView(x) ? Array.from(x) : Array.isArray(x) ? deepcopy(x) : x;
      }
      snap.dtype = DTYPES[d];
      this.views.push({ inn: c.number, cls: clsOn, view: snap });
    }
    Match._done(F);
    if (rec !== null) {
      rec.post = [c.runs, c.wkts, c.legal, ids[c.striker], ids[c.nonstriker], c.free_hit];
      this.log.push(rec);
    }
    return overDone;
  }

  // Speculative fielding review; df = drs_field(view, cls) when the caller already has it (providers are pure).
  _spec(F, u, rec, cls, retain, df = null) {
    if (df === null) df = this.P.drs_field(this.view, cls, this.o4b);
    const rs = df[2], share = df[3];
    const c = this.cur;
    let sp, uc;
    if (F !== null) {
      sp = Match._pop(F, 'spec', false);
      uc = pyBool(sp) ? Match._need(F, 'spec_ucall') : false;
    } else {
      sp = u[11] < rs; uc = u[11] < rs * share;
    }
    if (rec !== null) {
      rec.spec = pyBool(sp);
      if (pyBool(sp)) rec.spec_ucall = pyBool(uc);
    }
    if (pyBool(sp)) {
      this.stats[S_SPEC] += 1;
      this.stats[S_SPEC_UC] += pyBool(uc) ? 1 : 0;
      if (!(pyBool(uc) && retain)) c.reviews[1] -= 1;
      if (!pyBool(uc)) c.fail_reviews[1] += 1;
    }
  }

  // --- over end (plan 9.2 step 12)
  _overEvent() {
    const c = this.cur, P = this.P, v = this.view, pr = this.pr;
    const F = this._next('over');
    let u = null;
    if (F === null) u = this.sOver.fill(this.u4o, 4);
    const rec = this.log !== null ? { e: 'over', n: c.number, ov: c.nOvers } : null;
    this.ovFresh = false;
    if (pr.limited) {
      const applied = [];
      while (this.pending.length && this.pending[0].start <= this.match_legal && this.result === null) {
        const it = this.pending.shift();
        applyInterruption(this, it.lost);
        applied.push(it);
      }
      if (rec !== null && applied.length) {
        rec.intr = applied;
        rec.target = c.number === 2 ? c.target : null;
        rec.lengths = [...this.lengths];
      }
    }
    if (this.result === null && c.end === null) {
      this._refresh();
      if (pr.isTest && (c.number < 3 || (c.number === 3 && v.lead > 0))) {
        const dec = F !== null ? Match._pop(F, 'declare', false) : u[1] < P.declare_hazard(v);
        if (rec !== null) rec.declare = pyBool(dec);
        if (pyBool(dec)) c.end = 'declared';
      }
      if (c.end === null) {
        this._chooseBowler(u, 2, F, rec);
        const nb = this.rules.new_ball_after_overs;
        if (pr.isTest && pyBool(nb) && c.ball_age >= nb) {
          this._refresh();
          const take = F !== null ? Match._need(F, 'new_ball') : u[3] < P.new_ball_prob(v);
          if (rec !== null) rec.new_ball = pyBool(take);
          if (pyBool(take)) { c.ball_age = 0; c.second_new_ball = true; this.ovFresh = false; }
        }
      }
    }
    Match._done(F);
    if (rec !== null) this.log.push(rec);
  }

  // --- innings end and results
  _setResult(result, winner = null, method = null, margin = null, marginKind = null) {
    this.result = { result, winner, method, margin, margin_kind: marginKind, tie_before: this.tie_before, super_overs: this.so_k };
  }

  _finishInnings() {
    const c = this.cur, pr = this.pr;
    c.closed = true;
    if (c.legal % 6 || (c.nScores ? c.overScores[c.nScores - 1] : 0) !== c.runs) c.pushScore(c.runs);
    if (c.so) return this._finishSo(c);
    this.done.push(c);
    if (this.result !== null) return undefined;
    const k = c.number;
    if (pr.limited) {
      if (k === 1) return undefined;
      this.main_done = true;
      const method = c.timing === 'original' ? 'normal' : 'dls';
      if (c.end === 'target') return this._setResult('win', c.team, method, 10 - c.wkts, 'wickets');
      const par = c.target - 1;
      if (c.end === 'cut') {
        if (c.runs > par) return this._setResult('win', c.team, 'par', 10 - c.wkts, 'wickets');
        if (c.runs < par) return this._setResult('win', c.opp, 'par', par - c.runs, 'runs');
        this.tie_before = true;
        return this._setResult('tie', null, 'par');
      }
      if (c.runs < par) return this._setResult('win', c.opp, method, par - c.runs, 'runs');
      this.tie_before = true;
      return this._tieBreak();
    }
    if (c.end === 'clock') {
      this.main_done = true;
      return this._setResult('draw');
    }
    if (k === 3) {
      const ax = this._agg(c.team), ay = this._agg(c.opp);
      if (ax < ay) {
        this.main_done = true;
        return this._setResult('win', c.opp, 'normal', ay - ax, 'innings');
      }
    } else if (k === 4) {
      this.main_done = true;
      if (c.end === 'target') return this._setResult('win', c.team, 'normal', 10 - c.wkts, 'wickets');
      if (c.runs === c.target - 1) {
        this.tie_before = true;
        return this._setResult('tie', null, 'normal');
      }
      return this._setResult('win', c.opp, 'normal', c.target - 1 - c.runs, 'runs');
    }
    return undefined;
  }

  _coin() {
    if (this.script !== null) {
      if (this.coin_forced === null) throw new ScriptError("the tie-break coin needs 'coin' in the match or resume event");
      return this.coin_forced;
    }
    return this.coin_u < 0.5 ? 0 : 1;
  }

  _tieBreak() {
    const tb = this.rules.tie_break;
    if (tb === 'none') return this._setResult('tie', null, 'normal');
    if (tb === 'bowl_out') return this._setResult('win', this._coin(), 'coin');
    this.so_k = 1; this.so_first = this.inn_team[1]; this.so_target = null;
    return undefined;
  }

  _finishSo(c) {
    if (c.so_inn === 1) {
      this.so_target = c.runs + 1;
      return undefined;
    }
    this.so_target = null;
    if (c.end === 'target') return this._setResult('win', c.team, 'super_over');
    if (c.runs < c.target - 1) return this._setResult('win', c.opp, 'super_over');
    if (this.so_k < MAX_SUPER_OVERS) {
      this.so_k += 1;
      this.so_first = c.team;
      return undefined;
    }
    return this._setResult('win', this._coin(), 'coin');
  }

  // --- in-play resume
  _resume(st) {
    const pr = this.pr, sc = this.sc, P = this.P;
    const errs = checkState(st, pr);
    if (errs.length) throw new Error('invalid in-play state: ' + errs.join('; '));
    const F = this._next('resume');
    const rec = this.log !== null ? { e: 'resume' } : null;
    let um = null;
    if (F === null) um = this.sMatch.fill(this.u64, 64);
    this._drawForms();
    this.toss = deepcopy(get(st, 'toss'));
    this.inn_team = [...st.innings_team];
    this.followed_on = pyBool(get(st, 'followed_on', false));
    st.done.forEach((d, i) => {
      const x = this.main[i];
      x.reset();
      x.number = i + 1; x.team = d.team; x.opp = 1 - d.team;
      x.runs = d.runs; x.wkts = d.wkts; x.legal = d.legal_balls; x.max_balls = d.max_balls;
      x.target = d.target; x.end = d.end; x.closed = true;
      x.noOvers = true;                                 // the state keeps totals only: no worm for x
      this.done.push(x);
    });
    const c = this._inningsFromState(st.cur);
    this.cur = c;
    this.match_legal = this.done.reduce((a, x) => a + x.legal, 0) + c.legal;
    if (pr.isTest) {
      const ck = st.clock;
      this.changeovers = ck.changeovers;
      const avail = [...ck.avail];
      avail.forEach((a, dd) => {
        if (a === null) avail[dd] = um !== null ? P.day_availability(sc, dd + 1, um[M_DAYS + dd]) : 6 * this.rules.test_overs_per_day;
      });
      this._setClock(avail);
    } else {
      const n = this.rules.max_balls;
      const lens = pyOr(get(st, 'lengths'), [null, null]);
      this.lengths = [lens[0] !== null ? lens[0] : (this.done.length ? this.done[0].max_balls : c.max_balls),
        lens[1] !== null ? lens[1] : c.max_balls];
      const rs = pyOr(get(st, 'resources'), [null, null]);
      this.R = [rs[0] !== null ? rs[0] : pr.res(this.lengths[0], 0),
        rs[1] !== null ? rs[1] : (c.number === 2 ? pr.res(c.max_balls, 0) : null)];
      if (c.number === 2 && c.target === null) {
        c.target = revisedTarget(this.done[0].runs, this.R[0], this.R[1], pr.G);
        c.timing = this.R[1] === this.R[0] ? 'original' : 'pre_inn2';
      }
      this.revised_pre = pyBool(get(st, 'revised_pre', this.lengths[1] !== n));
      let pend = get(st, 'pending_interruptions');
      if (pend === null) pend = um === null ? [] : P.interruption_schedule(sc, this.match_legal, um.subarray(M_RAIN, M_RAIN + 16));
      this.pending = pend.map((x) => ({ ...x }));
    }
    c.agg_bat = this._agg(c.team); c.agg_opp = this._agg(c.opp);
    if (c.number === 4 && c.target === null) { c.target = c.agg_opp - c.agg_bat + 1; c.timing = 'original'; }
    this._priorLatents(um);
    this._inningsView(c);
    if (pyBool(get(st, 'balls'))) {
      this._posteriorLatents(um);
      this._inningsView(c);
    }
    this.coin_u = um !== null ? um[M_COIN] : null;
    this.coin_forced = F !== null ? Match._pop(F, 'coin', null) : null;
    let ui = null;
    if (F === null) ui = this.sInn.fill(this.u4i, 4);
    if (c.umpire_offset === null) {
      c.umpire_offset = F !== null ? Match._need(F, 'umpire_offset') : (ui[1] < 0.5 ? 0 : 1);
      if (rec !== null) rec.umpire_offset = c.umpire_offset;
    }
    this._inningsView(c);
    this.ovFresh = false;
    this._refresh();
    if (c.bowler === NONE) this._chooseBowler(ui, 2, F, rec);
    Match._done(F);
    if (rec !== null) {
      if (F === null) rec.latent = [...this.lat_m, ...this.lat_i.flatMap((row) => [...row])];
      this.log.push(rec);
    }
  }

  _inningsFromState(cs) {
    const pr = this.pr, S = (p) => pr.slotOf.get(p);
    this.ovFresh = false;
    const c = this.main[cs.number - 1];
    c.reset();
    c.number = cs.number; c.team = cs.team; c.opp = 1 - cs.team;
    c.order = pr.ordersIdx[c.team];
    c.runs = cs.runs; c.wkts = cs.wkts; c.legal = cs.legal_balls; c.max_balls = cs.max_balls;
    c.target = cs.target;
    c.timing = pyOr(get(cs, 'target_timing'), cs.target !== null ? 'original' : null);
    c.striker = S(cs.striker); c.nonstriker = S(cs.nonstriker);
    const un = new Set([...cs.unavailable, ...pr.absent[c.team]]);
    for (const p of un) {
      const i = S(p);
      if (i !== undefined) c.unavail[i] = 1;
      c.unavList[c.nUnavail++] = i === undefined ? 0 : i;
    }
    const bats = Object.entries(cs.batters).sort((a, b) => a[1].arrival - b[1].arrival);
    let mx = 0;
    for (const [p, b] of bats) {
      const i = S(p);
      if (!c.batIn[i]) { c.batIn[i] = 1; c.batList[c.nBat++] = i; }
      c.batRuns[i] = b.runs; c.batBalls[i] = b.balls; c.batArr[i] = b.arrival; c.batOut[i] = get(b, 'out');
      c.batFours[i] = get(b, 'fours', 0); c.batSixes[i] = get(b, 'sixes', 0);
      if (pyBool(get(b, 'out'))) c.outList[c.nOut++] = i;
      mx = Math.max(mx, b.arrival);
    }
    c.n_arrived = mx;
    for (const p of c.order) if (!c.batIn[p] && !c.unavail[p]) c.toCome[c.tcLen++] = p;
    c.tcStamp = ++this.stamp;
    for (const p of cs.over_bowlers) c.pushOver(S(p));
    for (const [p, b] of Object.entries(cs.bowlers)) {
      const i = S(p);
      c.addBowler(i);
      c.bowlBalls[i] = b.balls; c.bowlRuns[i] = b.runs; c.bowlWkts[i] = b.wkts;
      c.bowlOvers[i] = cs.over_bowlers.filter((x) => x === p).length;
    }
    c.bowler = cs.bowler === null ? NONE : S(cs.bowler);
    c.last_bowler = cs.last_bowler === null ? NONE : S(cs.last_bowler);
    c.ball_in_over = cs.ball_in_over;
    if (c.bowler !== NONE) {
      c.addBowler(c.bowler);
      c.spell = c.spellOf(c.bowler);
    }
    c.free_hit = pyBool(cs.free_hit);
    c.reviews[0] = cs.reviews[0]; c.reviews[1] = cs.reviews[1];
    c.fail_reviews[0] = cs.fail_reviews[0]; c.fail_reviews[1] = cs.fail_reviews[1];
    c.umpire_offset = cs.umpire_offset;
    [c.p_runs, c.p_balls] = cs.partnership;
    c.ball_age = cs.ball_age_overs; c.second_new_ball = pyBool(cs.second_new_ball);
    c.last_over_runs = cs.last_over_runs; c.last_over_wkt = pyBool(cs.last_over_wkt);
    c.over_runs = cs.over_runs; c.wkt_this_over = pyBool(cs.wkt_this_over);
    for (const x of cs.over_scores) c.pushScore(x);
    c.extras = get(cs, 'extras', 0); c.byes = get(cs, 'byes', 0);
    c.windows = pr.windows(c.max_balls);
    return c;
  }

  _posteriorLatents(um) {
    const pr = this.pr, c = this.cur;
    const post = pr.posterior();
    const nm = pr.lat_m.length, free = post.free, mode = post.mode, chol = post.chol;
    const k = c.number - 1;
    let x;
    if (um === null) x = free.map(() => 0.0);
    else {
      const zm = [...normalPair(um[M_LAT], um[M_LAT + 1]), ...normalPair(um[M_LAT + 2], um[M_LAT + 3])];
      const zi = normalPair(um[M_INN_LAT + 2 * k], um[M_INN_LAT + 2 * k + 1]);
      x = backSolveT(chol, free.map((j) => (j < nm ? zm[j] : zi[j - nm])));
    }
    free.forEach((j, t) => {
      if (j < nm) this.lat_m[j] = mode[t] + x[t];
      else this.lat_i[k][j - nm] = mode[t] + x[t];
    });
    this.stats[S_LATENT] += 1;
  }

  // --- state
  toState() {
    const c = this.cur, pr = this.pr, ids = pr.ids;
    if (c === null || c.so) throw new Error('the canonical state exists only inside a main innings');
    const order = pr.orders[c.team];
    const nxt = c.tcHead < c.tcLen ? order.indexOf(ids[c.toCome[c.tcHead]]) : order.length;
    const batters = {};
    for (let i = 0; i < c.nBat; i++) {
      const p = c.batList[i];
      batters[ids[p]] = { runs: c.batRuns[p], balls: c.batBalls[p], arrival: c.batArr[p], out: c.batOut[p],
        fours: c.batFours[p], sixes: c.batSixes[p] };
    }
    const bowlers = {};
    for (let i = 0; i < c.nBowl; i++) {
      const p = c.bowlList[i];
      bowlers[ids[p]] = { balls: c.bowlBalls[p], runs: c.bowlRuns[p], wkts: c.bowlWkts[p], overs: c.bowlOvers[p] };
    }
    const cur = {
      number: c.number, team: c.team, runs: c.runs, wkts: c.wkts, legal_balls: c.legal, max_balls: c.max_balls,
      target: c.target, target_timing: c.timing, striker: ids[c.striker], nonstriker: ids[c.nonstriker], batters,
      unavailable: order.filter((p) => c.unavail[pr.slotOf.get(p)]), next: nxt, bowlers,
      over_bowlers: Array.from(c.overBowlers.subarray(0, c.nOvers), (x) => ids[x]),
      bowler: c.bowler === NONE ? null : ids[c.bowler], last_bowler: c.last_bowler === NONE ? null : ids[c.last_bowler],
      ball_in_over: c.ball_in_over, free_hit: c.free_hit, reviews: [c.reviews[0], c.reviews[1]],
      fail_reviews: [c.fail_reviews[0], c.fail_reviews[1]], umpire_offset: c.umpire_offset,
      partnership: [c.p_runs, c.p_balls], ball_age_overs: c.ball_age, second_new_ball: c.second_new_ball,
      last_over_runs: c.last_over_runs, last_over_wkt: c.last_over_wkt, over_runs: c.over_runs,
      wkt_this_over: c.wkt_this_over, over_scores: Array.from(c.overScores.subarray(0, c.nScores)), extras: c.extras,
      byes: c.byes,
    };
    const st = {
      innings_team: [...this.inn_team], toss: deepcopy(this.toss), followed_on: this.followed_on,
      done: this.done.map((x) => ({ team: x.team, runs: x.runs, wkts: x.wkts, legal_balls: x.legal, max_balls: x.max_balls,
        target: x.target, end: x.end })),
      cur,
    };
    if (pr.limited) {
      Object.assign(st, { lengths: [...this.lengths], resources: [...this.R], revised_pre: this.revised_pre,
        pending_interruptions: this.pending.map((x) => ({ ...x })) });
    } else {
      st.clock = { used: this._used(), changeovers: this.changeovers, avail: [...this.avail] };
    }
    return st;
  }

  // Per-simulation summary consumed by Acc (integers only, so merges are exact).
  record() {
    const res = this.result, ids = this.pr.ids;
    const code = res.result === 'tie' ? 2 : res.result === 'draw' ? 3 : res.result === 'no_result' ? 4 : res.winner;
    const players = new Map();
    const row = (p) => {
      let s = players.get(p);
      if (s === undefined) { s = [0, 0, 0, 0, 0, 0, 0, 0, 0]; players.set(p, s); }
      return s;
    };
    for (const c of this.done) {
      for (let i = 0; i < c.nBat; i++) {
        const p = c.batList[i], s = row(ids[p]);
        s[0] += c.batRuns[p]; s[1] += c.batBalls[p]; s[2] += 1; s[3] += c.batOut[p] !== null ? 1 : 0;
        s[4] = Math.max(s[4], c.batRuns[p]);
      }
      for (let i = 0; i < c.nBowl; i++) {
        const p = c.bowlList[i], s = row(ids[p]);
        s[5] += c.bowlBalls[p]; s[6] += c.bowlRuns[p]; s[7] += c.bowlWkts[p]; s[8] = Math.max(s[8], c.bowlWkts[p]);
      }
    }
    const stats = {};
    this.stats.forEach((x, i) => { if (x) stats[STAT_NAMES[i]] = x; });
    return {
      sim: this.sim, code, result: res,
      innings: this.done.map((c) => [c.number, c.team, c.runs, c.wkts, c.legal, c.end]),
      overs: this.done.map((c) => (c.noOvers ? null : Array.from(c.overScores.subarray(0, c.nScores)))),
      players, stats, deliveries: this.deliveries,
    };
  }
}

// ---------------------------------------------------------------- interruptions (plan 7.6)

export function applyInterruption(m, lost) {
  const pr = m.pr, c = m.cur;
  m.ovFresh = false;
  const minb = pyOr(m.rules.min_balls_for_result, 0);
  if (c === null || (c.number === 1 && c.end === null)) {
    const legal = c === null ? 0 : c.legal, w = c === null ? 0 : c.wkts;
    const old = m.lengths[0];
    const nw = Math.max(old - lost, 0);
    m.R[0] -= pr.res(old - legal, w) - pr.res(Math.max(nw - legal, 0), w);
    m.lengths = [Math.max(nw, legal), nw];
    m.revised_pre = true;
    if (c !== null) {
      c.max_balls = m.lengths[0];
      c.windows = pr.windows(c.max_balls);
    }
    if (nw < minb) {
      if (c !== null) c.end = 'no_result';
      m._setResult('no_result');
    } else if (c !== null && legal >= nw) {
      c.end = 'cut';
    }
  } else if (c.number === 1) {
    m.lengths[1] = Math.max(m.lengths[1] - lost, 0);
    m.revised_pre = true;
    if (m.lengths[1] < minb) m._setResult('no_result');
  } else {
    const old = c.max_balls;
    const nw = Math.max(old - lost, 0);
    m.R[1] -= pr.res(old - c.legal, c.wkts) - pr.res(Math.max(nw - c.legal, 0), c.wkts);
    c.target = revisedTarget(m.done[0].runs, m.R[0], m.R[1], pr.G);
    c.timing = 'revised';
    m.view.target_timing = 'revised';
    if (nw <= c.legal) {
      c.max_balls = m.lengths[1] = c.legal;
      if (c.legal < minb) {
        c.end = 'no_result';
        m._setResult('no_result');
      } else {
        c.end = 'cut';
      }
    } else {
      c.max_balls = m.lengths[1] = nw;
      c.windows = pr.windows(nw);
      if (nw < minb) {
        c.end = 'no_result';
        m._setResult('no_result');
      } else if (c.runs >= c.target) {
        c.end = 'target';
      }
    }
  }
}

// ---------------------------------------------------------------- in-play latent update (plan 9.3)

function cholesky(a) {
  const n = a.length;
  const L = Array.from({ length: n }, () => new Array(n).fill(0.0));
  for (let i = 0; i < n; i++) {
    for (let j = 0; j <= i; j++) {
      let s = a[i][j];
      for (let k = 0; k < j; k++) s -= L[i][k] * L[j][k];
      L[i][j] = i === j ? Math.sqrt(s) : s / L[j][j];
    }
  }
  return L;
}

function solveSpd(L, b) {
  const n = b.length, y = new Array(n).fill(0.0);
  for (let i = 0; i < n; i++) {
    let s = b[i];
    for (let k = 0; k < i; k++) s -= L[i][k] * y[k];
    y[i] = s / L[i][i];
  }
  return backSolveT(L, y);
}

function backSolveT(L, y) {
  const n = y.length, x = new Array(n).fill(0.0);
  for (let i = n - 1; i >= 0; i--) {
    let s = y[i];
    for (let k = i + 1; k < n; k++) s -= L[k][i] * x[k];
    x[i] = s / L[i][i];
  }
  return x;
}

// Plan 9.3 (sim.latent_posterior): exactly `iters` Newton steps from 0 on the outcome log-likelihood
// of `recs` plus the prior; returns [mode, Cholesky factor of the posterior precision at the mode].
export function latentPosterior(P, baseView, recs, curNumber, free, mu, sd, fixed, nMatch, iters = 10, pr = null) {
  const nf = free.length;
  const pre = recs.map((r) => {
    const vb = { ...baseView, ...r.view };
    if (pr !== null) pr.addIdx(vb);
    const off = new Array(9).fill(0.0);
    if (get(vb, 'dtype') === 'noball' || pyBool(get(vb, 'free_hit'))) off[OUT] = MASK_OFFSET;
    const own = r.inn === curNumber;
    const loc = [];
    free.forEach((j, t) => { if (j < nMatch || own) loc.push(t); });
    return [vb, Math.trunc(r.cls), loc, loc.map((t) => free[t]), own, off];
  });
  const vr = sd.map((s) => s * s);
  const gradPrec = (th) => {
    const g = th.map((x, j) => -(x - mu[j]) / vr[j]);
    const h = Array.from({ length: nf }, (_, i) => Array.from({ length: nf }, (__, j) => (i === j ? 1.0 / vr[i] : 0.0)));
    const full = [...fixed];
    free.forEach((j, t) => { full[j] = th[t]; });
    const other = full.map((x, j) => (j < nMatch ? x : 0.0));
    for (const [vb, cls, loc, idx, own, off] of pre) {
      vb.latent = own ? full : other;
      const [, gb, hb] = P.latent_loglik(vb, cls, idx, off);
      loc.forEach((ta, a) => {
        g[ta] += gb[a];
        loc.forEach((tb, b) => { h[ta][tb] -= hb[a][b]; });
      });
    }
    return [g, h];
  };
  let th = new Array(nf).fill(0.0);
  for (let it = 0; it < iters; it++) {
    const [g, h] = gradPrec(th);
    const step = solveSpd(cholesky(h), g);
    th = th.map((a, i) => a + step[i]);
  }
  const [, h] = gradPrec(th);
  return [th, cholesky(h)];
}

// ---------------------------------------------------------------- in-play state checks and imputation

export function checkState(st, pr) {
  let errs = stateSchemaErrors(st, pr.sc);
  if (errs.length) return errs;
  errs = [];
  const c = st.cur, it = st.innings_team;
  const n = c.number;
  if (st.done.length !== n - 1) errs.push(`cur.number ${n} but ${st.done.length} completed innings`);
  if (!(n >= 1 && n <= it.length) || it[n - 1] !== c.team) errs.push('cur.team does not match innings_team');
  st.done.forEach((d, i) => { if (i < it.length && d.team !== it[i]) errs.push(`done[${i}].team does not match innings_team`); });
  const team = c.team, opp = 1 - c.team;
  const order = new Set(pr.orders[team]);
  const outs = Object.entries(c.batters).filter(([, b]) => pyBool(get(b, 'out')));
  if (c.wkts !== outs.length) errs.push(`wkts ${c.wkts} != dismissed count ${outs.length}`);
  if (Object.values(c.bowlers).reduce((a, b) => a + b.balls, 0) !== c.legal_balls) errs.push('sum of bowler balls != legal_balls');
  if (c.over_bowlers.length !== Math.floor(c.legal_balls / 6) || c.ball_in_over !== c.legal_balls % 6) {
    errs.push('over_bowlers / ball_in_over inconsistent with legal_balls');
  }
  for (const p of [c.striker, c.nonstriker]) {
    if (!order.has(p) || !has(c.batters, p) || pyBool(get(c.batters[p], 'out')) || c.unavailable.includes(p)) {
      errs.push(`current batter ${p} is not an available, not-out batter of the batting side`);
    }
  }
  if (c.striker === c.nonstriker) errs.push('striker == nonstriker');
  if (Object.keys(c.batters).some((p) => !order.has(p))) errs.push('batters outside the batting order');
  const fielders = new Set([...pr.xi[opp], ...pr.opts[opp]]);
  if (Object.keys(c.bowlers).some((p) => !fielders.has(p)) || c.over_bowlers.some((p) => !fielders.has(p))) {
    errs.push('bowlers outside the fielding side');
  }
  if (c.target !== null && c.target - c.runs <= 0) errs.push('runs_required must be > 0');
  if (c.max_balls !== null && c.legal_balls >= c.max_balls) errs.push('legal_balls must be < max_balls');
  if (pr.limited && c.max_balls === null) errs.push('limited overs need cur.max_balls');
  if (c.ball_in_over && c.bowler === null) errs.push('mid-over states need the current bowler');
  if (c.bowler !== null && c.bowler === c.last_bowler) errs.push('the current bowler bowled the previous over');
  if (Math.min(...c.reviews) < 0) errs.push('negative reviews');
  if (c.wkts >= 10) errs.push('the innings is already all out');
  if (!pr.limited) {
    const ck = st.clock;
    const used = st.done.reduce((a, d) => a + d.legal_balls, 0) + c.legal_balls + 12 * ck.changeovers;
    if (get(ck, 'used') !== null && ck.used !== used) errs.push('clock.used != match legal balls + 12 * changeovers');
    if (ck.avail.length !== pr.rules.test_days) errs.push('clock.avail needs one entry per scheduled day');
  }
  return errs;
}

// Fill a minimal in-play state deterministically (sim.impute_state, plan 9.3).
export function imputeState(partial, scenario, provider = null) {
  const pr = new Prepared(scenario, provider);
  const p = deepcopy(partial);
  const cur = p.cur;
  const n = get(cur, 'number', pyOr(get(p, 'done'), []).length + 1);
  if (!has(p, 'innings_team')) {
    const first = n % 2 ? cur.team : 1 - cur.team;
    p.innings_team = pr.limited ? [first, 1 - first] : [first, 1 - first, first, 1 - first];
  }
  const it = p.innings_team;
  const team = setdefault(cur, 'team', it[n - 1]);
  cur.number = n;
  const sched = pr.rules.max_balls;
  p.done = pyOr(get(p, 'done'), []).map((d, i) => ({
    team: get(d, 'team', it[i]), runs: d.runs, wkts: d.wkts, legal_balls: get(d, 'legal_balls', pyOr(sched, 0)),
    max_balls: get(d, 'max_balls', sched), target: get(d, 'target'),
    end: get(d, 'end', d.wkts >= 10 ? 'all_out' : pr.limited ? 'balls' : 'declared'),
  }));
  const done = p.done;
  const L = cur.legal_balls, w = cur.wkts;
  setdefault(cur, 'max_balls', pr.limited ? pyOr(get(p, 'lengths'), [sched, sched])[n - 1] : null);
  setdefault(cur, 'target', null);
  setdefault(cur, 'target_timing', cur.target === null ? null : 'original');
  const unav = [...get(cur, 'unavailable', [])];
  const avail = pr.orders[team].filter((x) => !unav.includes(x) && !pr.absent[team].has(x));
  if (!has(cur, 'batters')) {
    const bats = {};
    avail.slice(0, w + 2).forEach((x, i) => { bats[x] = { runs: 0, balls: 0, arrival: i + 1, out: i < w ? 'unknown' : null }; });
    cur.batters = bats;
    cur.striker = avail[w]; cur.nonstriker = avail[w + 1];
  }
  cur.unavailable = unav;
  setdefault(cur, 'next', 0);
  if (!has(cur, 'bowlers')) {
    const opts = pr.opts[1 - team];
    const nOvers = pr.limited ? Math.floor(cur.max_balls / 6) : null;
    const ob = [], overs = new Map();
    for (let k = 0; k < Math.floor(L / 6) + (L % 6 ? 1 : 0); k++) {
      const last = ob.length ? ob[ob.length - 1] : null;
      let el = eligibleBowlers(opts, overs, last, nOvers, k, pr.qrule);
      if (!el.length) el = opts.filter((x) => x !== last);
      const b = el[0];
      ob.push(b);
      overs.set(b, (overs.get(b) || 0) + 1);
    }
    const balls = new Map();
    for (const b of ob.slice(0, Math.floor(L / 6))) balls.set(b, (balls.get(b) || 0) + 1);
    for (const [b, x] of balls) balls.set(b, 6 * x);
    if (L % 6) { const lb = ob[ob.length - 1]; balls.set(lb, (balls.get(lb) || 0) + L % 6); }
    const runs = cur.runs;
    const share = new Map();
    for (const [b, x] of balls) share.set(b, L ? Math.floor(runs * x / L) : 0);
    const rem = runs - [...share.values()].reduce((a, x) => a + x, 0);
    for (const b of [...share.keys()].slice(0, rem)) share.set(b, share.get(b) + 1);
    cur.bowlers = Object.fromEntries([...balls.keys()].map((b) => [b, { balls: balls.get(b), runs: share.get(b), wkts: 0 }]));
    cur.over_bowlers = ob.slice(0, Math.floor(L / 6));
    cur.bowler = L % 6 ? ob[ob.length - 1] : null;
    cur.last_bowler = Math.floor(L / 6) ? ob[Math.floor(L / 6) - 1] : null;
  }
  setdefault(cur, 'ball_in_over', L % 6);
  setdefault(cur, 'free_hit', false);
  setdefault(cur, 'reviews', [pr.rpi, pr.rpi]);
  setdefault(cur, 'fail_reviews', [0, 0]);
  setdefault(cur, 'umpire_offset', null);
  setdefault(cur, 'partnership', [0, 0]);
  setdefault(cur, 'ball_age_overs', !pr.limited ? Math.floor(L / 6) % 80 : Math.floor(L / 6));
  setdefault(cur, 'second_new_ball', Math.floor(L / 6) >= 80 && !pr.limited);
  setdefault(cur, 'last_over_runs', 0);
  setdefault(cur, 'last_over_wkt', false);
  setdefault(cur, 'over_runs', 0);
  setdefault(cur, 'wkt_this_over', false);
  setdefault(cur, 'over_scores', []);
  if (pr.limited) {
    setdefault(p, 'lengths', [sched, n === 2 ? cur.max_balls : sched]);
    setdefault(p, 'resources', [null, null]);
    setdefault(p, 'pending_interruptions', null);
  } else if (!has(p, 'clock')) {
    const opd6 = 6 * pr.rules.test_overs_per_day;
    const ch = n - 1;
    const used = done.reduce((a, d) => a + d.legal_balls, 0) + L + 12 * ch;
    const day = Math.min(pr.rules.test_days, 1 + Math.floor(used / opd6));
    p.clock = { used, changeovers: ch, avail: [...Array(pr.rules.test_days).keys()].map((d) => (d < day ? opd6 : null)) };
  }
  setdefault(p, 'toss', null);
  return p;
}

// ---------------------------------------------------------------- many simulations and outputs (plan 9.7)

function quantile(cnt, n, q100) {
  if (!n) return null;
  let cum = 0;
  const keys = [...cnt.keys()].sort((a, b) => a - b);
  for (const x of keys) {
    cum += cnt.get(x);
    if (100 * cum >= q100 * n) return x;
  }
  return keys[keys.length - 1];
}

const inc = (m, k, d = 1) => m.set(k, (m.get(k) || 0) + d);

// Counter of integer values (Map-like: get, keys, entries in ascending order); dense for 0..2**20.
class Hist {
  constructor() { this.a = new Float64Array(16); this.other = null; }

  add(x, c = 1) {
    if (x >= 0 && x < 1048576 && x === Math.floor(x)) {
      if (x >= this.a.length) {
        let n = this.a.length * 2;
        while (n <= x) n *= 2;
        const b = new Float64Array(n);
        b.set(this.a);
        this.a = b;
      }
      this.a[x] += c;
    } else {
      if (this.other === null) this.other = new Map();
      inc(this.other, x, c);
    }
  }

  get(x) {
    if (x >= 0 && x < this.a.length && x === Math.floor(x)) return this.a[x] || undefined;
    return this.other === null ? undefined : this.other.get(x);
  }

  entries() {
    const out = [];
    for (let x = 0; x < this.a.length; x++) if (this.a[x]) out.push([x, this.a[x]]);
    if (this.other !== null) out.push(...this.other);
    return out.sort((p, q) => p[0] - q[0]);
  }

  keys() { return this.entries().map((e) => e[0]); }

  [Symbol.iterator]() { return this.entries()[Symbol.iterator](); }

  merge(o) { for (const [x, c] of o.entries()) this.add(x, c); }

  static from(entries) { const h = new Hist(); for (const [x, c] of entries) h.add(x, c); return h; }
}
const mapToEntries = (m) => [...m.entries()];
const newInn = () => ({ n: 0, runs: new Hist(), runs2: 0, wkts: new Hist(), balls: 0, end: new Map() });

// Integer sufficient statistics of a set of simulations; merge is exact (sim.Acc).
export class Acc {
  constructor(nOvers = null) {
    this.n = 0;
    this.n_overs = nOvers;
    this.codes = [];
    this.code = [0, 0, 0, 0, 0];
    this.tie_before = 0;
    this.methods = new Map();
    this.super_overs = new Map();
    this.margins = new Map();
    this.inn = new Map();
    this.over_runs = new Map();
    this.worm = new Map();
    this.players = new Map();
    this.stats = new Map();
    this.deliveries = 0;
  }

  add(rec) {
    this.n += 1;
    const res = rec.result;
    this.codes.push([rec.sim, rec.code]);
    this.code[rec.code] += 1;
    this.tie_before += res.tie_before ? 1 : 0;
    inc(this.methods, res.method === null ? 'None' : res.method);
    inc(this.super_overs, res.super_overs);
    if (res.margin_kind !== null) inc(this.margins, `${res.winner}\t${res.margin_kind}\t${res.margin}`);
    rec.innings.forEach(([k, , runs, wkts, legal, end], i) => {
      const ov = rec.overs[i];
      let d = this.inn.get(k);
      if (d === undefined) { d = newInn(); this.inn.set(k, d); }
      d.n += 1; d.runs.add(runs); d.runs2 += runs * runs; d.wkts.add(wkts); d.balls += legal; inc(d.end, end);
      if (ov === null) return;                          // completed innings of an in-play state
      let po = this.over_runs.get(k), wm = this.worm.get(k);
      if (po === undefined) { po = []; this.over_runs.set(k, po); }
      if (wm === undefined) { wm = []; this.worm.set(k, wm); }
      let prev = 0;
      const length = this.n_overs ? Math.max(ov.length, this.n_overs || 0) : ov.length;
      for (let j = 0; j < length; j++) {
        if (j < ov.length) {
          if (po.length <= j) po.push(new Hist());
          po[j].add(ov[j] - prev);
          prev = ov[j];
        }
        if (wm.length <= j) wm.push(new Hist());
        wm[j].add(j < ov.length ? ov[j] : ov.length ? ov[ov.length - 1] : 0);
      }
    });
    for (const [p, s] of rec.players) {
      let a = this.players.get(p);
      if (a === undefined) { a = new Array(12).fill(0); this.players.set(p, a); }
      a[0] += 1; a[1] += s[0]; a[2] += s[0] * s[0]; a[3] += s[1]; a[4] += s[2]; a[5] += s[3];
      a[6] += s[4] >= 50 ? 1 : 0; a[7] += s[4] >= 100 ? 1 : 0; a[8] += s[5]; a[9] += s[6]; a[10] += s[7];
      a[11] += s[8] >= 3 ? 1 : 0;
    }
    for (const [k, x] of Object.entries(rec.stats)) inc(this.stats, k, x);
    this.deliveries += rec.deliveries;
  }

  // Same accumulation as add(m.record()) straight from a finished Match's typed arrays (simulate's fast
  // path); bind(pr) first and fold() before reading players or stats.
  bind(pr) {
    const n = pr.nSlots;
    this._ids = pr.ids;
    this._pl = new Float64Array(12 * n);
    this._s = new Float64Array(9 * n);
    this._touched = new Uint8Array(n);
    this._list = new Int32Array(n);
    this._st = new Float64Array(STAT_NAMES.length);
    return this;
  }

  addMatch(m) {
    this.n += 1;
    const res = m.result;
    const code = res.result === 'tie' ? 2 : res.result === 'draw' ? 3 : res.result === 'no_result' ? 4 : res.winner;
    this.codes.push([m.sim, code]);
    this.code[code] += 1;
    this.tie_before += res.tie_before ? 1 : 0;
    inc(this.methods, res.method === null ? 'None' : res.method);
    inc(this.super_overs, res.super_overs);
    if (res.margin_kind !== null) inc(this.margins, `${res.winner}\t${res.margin_kind}\t${res.margin}`);
    const S = this._s, T = this._touched, Lst = this._list, A = this._pl;
    let nl = 0;
    const touch = (p) => {
      if (!T[p]) { T[p] = 1; Lst[nl++] = p; S.fill(0, 9 * p, 9 * p + 9); }
      return 9 * p;
    };
    for (const c of m.done) {
      const k = c.number, runs = c.runs, nov = c.nScores, ov = c.overScores;
      let d = this.inn.get(k);
      if (d === undefined) { d = newInn(); this.inn.set(k, d); }
      d.n += 1; d.runs.add(runs); d.runs2 += runs * runs; d.wkts.add(c.wkts); d.balls += c.legal; inc(d.end, c.end);
      if (c.noOvers) continue;                          // completed innings of an in-play state (totals only)
      let po = this.over_runs.get(k), wm = this.worm.get(k);
      if (po === undefined) { po = []; this.over_runs.set(k, po); }
      if (wm === undefined) { wm = []; this.worm.set(k, wm); }
      let prev = 0;
      const length = this.n_overs ? Math.max(nov, this.n_overs || 0) : nov;
      for (let j = 0; j < length; j++) {
        if (j < nov) {
          if (po.length <= j) po.push(new Hist());
          po[j].add(ov[j] - prev);
          prev = ov[j];
        }
        if (wm.length <= j) wm.push(new Hist());
        wm[j].add(j < nov ? ov[j] : nov ? ov[nov - 1] : 0);
      }
      for (let i = 0; i < c.nBat; i++) {
        const p = c.batList[i], o = touch(p), r = c.batRuns[p];
        S[o] += r; S[o + 1] += c.batBalls[p]; S[o + 2] += 1; S[o + 3] += c.batOut[p] !== null ? 1 : 0;
        if (r > S[o + 4]) S[o + 4] = r;
      }
      for (let i = 0; i < c.nBowl; i++) {
        const p = c.bowlList[i], o = touch(p), w = c.bowlWkts[p];
        S[o + 5] += c.bowlBalls[p]; S[o + 6] += c.bowlRuns[p]; S[o + 7] += w;
        if (w > S[o + 8]) S[o + 8] = w;
      }
    }
    for (let i = 0; i < nl; i++) {
      const p = Lst[i], o = 9 * p, a = 12 * p;
      T[p] = 0;
      A[a] += 1; A[a + 1] += S[o]; A[a + 2] += S[o] * S[o]; A[a + 3] += S[o + 1]; A[a + 4] += S[o + 2];
      A[a + 5] += S[o + 3]; A[a + 6] += S[o + 4] >= 50 ? 1 : 0; A[a + 7] += S[o + 4] >= 100 ? 1 : 0;
      A[a + 8] += S[o + 5]; A[a + 9] += S[o + 6]; A[a + 10] += S[o + 7]; A[a + 11] += S[o + 8] >= 3 ? 1 : 0;
    }
    const st = m.stats, ST = this._st;
    for (let i = 0; i < ST.length; i++) ST[i] += st[i];
    this.deliveries += m.deliveries;
  }

  fold() {
    if (!this._ids) return this;
    const ids = this._ids, A = this._pl;
    for (let p = 0; p < ids.length; p++) {
      if (!A[12 * p]) continue;
      let t = this.players.get(ids[p]);
      if (t === undefined) { t = new Array(12).fill(0); this.players.set(ids[p], t); }
      for (let i = 0; i < 12; i++) t[i] += A[12 * p + i];
    }
    this._st.forEach((x, i) => { if (x) inc(this.stats, STAT_NAMES[i], x); });
    this._ids = this._pl = this._s = this._touched = this._list = this._st = undefined;
    return this;
  }

  merge(o) {
    this.fold(); o.fold();
    this.n += o.n;
    for (const x of o.codes) this.codes.push(x);
    o.code.forEach((x, i) => { this.code[i] += x; });
    this.tie_before += o.tie_before;
    for (const f of ['methods', 'super_overs', 'margins', 'stats']) for (const [k, x] of o[f]) inc(this[f], k, x);
    this.deliveries += o.deliveries;
    for (const [k, d] of o.inn) {
      let e = this.inn.get(k);
      if (e === undefined) { e = newInn(); this.inn.set(k, e); }
      e.n += d.n; e.runs2 += d.runs2; e.balls += d.balls;
      e.runs.merge(d.runs); e.wkts.merge(d.wkts);
      for (const [x, y] of d.end) inc(e.end, x, y);
    }
    for (const f of ['over_runs', 'worm']) {
      for (const [k, rows] of o[f]) {
        let t = this[f].get(k);
        if (t === undefined) { t = []; this[f].set(k, t); }
        rows.forEach((cnt, j) => {
          if (t.length <= j) t.push(new Hist());
          t[j].merge(cnt);
        });
      }
    }
    for (const [p, s] of o.players) {
      let t = this.players.get(p);
      if (t === undefined) { t = new Array(12).fill(0); this.players.set(p, t); }
      s.forEach((x, i) => { t[i] += x; });
    }
    return this;
  }

  toJSON() {
    this.fold();
    const inn = mapToEntries(this.inn).map(([k, d]) => [k, { n: d.n, runs: d.runs.entries(), runs2: d.runs2,
      wkts: d.wkts.entries(), balls: d.balls, end: mapToEntries(d.end) }]);
    const rows = (m) => mapToEntries(m).map(([k, r]) => [k, r.map((h) => h.entries())]);
    return { n: this.n, n_overs: this.n_overs, codes: this.codes, code: this.code, tie_before: this.tie_before,
      methods: mapToEntries(this.methods), super_overs: mapToEntries(this.super_overs), margins: mapToEntries(this.margins),
      inn, over_runs: rows(this.over_runs), worm: rows(this.worm), players: mapToEntries(this.players),
      stats: mapToEntries(this.stats), deliveries: this.deliveries };
  }

  static fromJSON(j) {
    const a = new Acc(j.n_overs);
    Object.assign(a, { n: j.n, codes: j.codes, code: j.code, tie_before: j.tie_before, methods: new Map(j.methods),
      super_overs: new Map(j.super_overs), margins: new Map(j.margins), players: new Map(j.players),
      stats: new Map(j.stats), deliveries: j.deliveries });
    a.inn = new Map(j.inn.map(([k, d]) => [k, { n: d.n, runs: Hist.from(d.runs), runs2: d.runs2, wkts: Hist.from(d.wkts),
      balls: d.balls, end: new Map(d.end) }]));
    a.over_runs = new Map(j.over_runs.map(([k, r]) => [k, r.map((x) => Hist.from(x))]));
    a.worm = new Map(j.worm.map(([k, r]) => [k, r.map((x) => Hist.from(x))]));
    return a;
  }
}

function pP(x, n) {
  const p = n ? x / n : 0.0;
  return { p, se: n ? Math.sqrt(p * (1 - p) / n) : 0.0 };
}

const sumMap = (m, f) => { let s = 0; for (const [x, c] of m) s += f(x, c); return s; };

// The plan 9.7 outputs of an Acc, key for key as sim.summarize.
export function summarize(acc) {
  acc.fold();
  const n = acc.n, code = acc.code;
  const out = { n, p_win: [pP(code[0], n), pP(code[1], n)], p_tie_before: pP(acc.tie_before, n), p_tie: pP(code[2], n),
    p_draw: pP(code[3], n), p_no_result: pP(code[4], n), deliveries: acc.deliveries };
  out.methods = Object.fromEntries(acc.methods);
  out.super_overs = Object.fromEntries([...acc.super_overs].map(([k, x]) => [String(k), x]));
  const mg = [...acc.margins].map(([k, x]) => { const [w, kind, m] = k.split('\t'); return [Number(w), kind, Number(m), x]; });
  mg.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0) || a[2] - b[2]);
  const margins = {};
  for (const [w, kind, m, x] of mg) (margins[`${w}:${kind}`] ||= []).push([m, x]);
  out.margins = margins;
  const inns = {};
  for (const k of [...acc.inn.keys()].sort((a, b) => a - b)) {
    const d = acc.inn.get(k), m = d.n;
    const s1 = sumMap(d.runs, (x, c) => x * c);
    const mean = s1 / m;
    const vr = m > 1 ? Math.max(0.0, (d.runs2 - sqDiv(s1, m)) / (m - 1)) : 0.0;
    inns[String(k)] = {
      n: m, runs_mean: mean, runs_sd: Math.sqrt(vr), runs_se: Math.sqrt(vr / m),
      runs_q: Object.fromEntries([5, 10, 25, 50, 75, 90, 95].map((q) => [q, quantile(d.runs, m, q)])),
      runs_hist: [...d.runs].sort((a, b) => a[0] - b[0] || a[1] - b[1]),
      wkts_dist: [...Array(11).keys()].map((w) => (d.wkts.get(w) || 0) / m),
      wkts_mean: sumMap(d.wkts, (w, c) => w * c) / m, balls_mean: d.balls / m, end: Object.fromEntries(d.end),
    };
  }
  out.innings = inns;
  const rows = (src) => {
    const res = {};
    for (const k of [...src.keys()].sort((a, b) => a - b)) {
      res[String(k)] = src.get(k).map((c, j) => {
        const tot = sumMap(c, (x, y) => y);
        return { over: j + 1, n: tot, mean: sumMap(c, (x, y) => x * y) / tot, q10: quantile(c, tot, 10),
          q50: quantile(c, tot, 50), q90: quantile(c, tot, 90) };
      });
    }
    return res;
  };
  out.runs_by_over = rows(acc.over_runs);
  out.worm = rows(acc.worm);
  const pl = {};
  for (const p of [...acc.players.keys()].sort()) {
    const a = acc.players.get(p);
    const mean = a[1] / n;
    const vr = n > 1 ? Math.max(0.0, (a[2] - sqDiv(a[1], n)) / (n - 1)) : 0.0;
    pl[p] = { matches_involved: a[0], bat_runs: mean, bat_runs_se: Math.sqrt(vr / n), bat_balls: a[3] / n,
      bat_innings: a[4] / n, outs: a[5] / n, p50: pP(a[6], n), p100: pP(a[7], n), bowl_balls: a[8] / n,
      bowl_runs: a[9] / n, bowl_wkts: a[10] / n, p3w: pP(a[11], n), economy: a[8] ? 6 * a[9] / a[8] : null };
  }
  out.players = pl;
  const kinds = [...acc.stats].filter(([k]) => k.startsWith('kind_')).map(([k, x]) => [k.slice(5), x]);
  const tot = kinds.reduce((s, [, x]) => s + x, 0);
  kinds.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  out.dismissals = Object.fromEntries(kinds.map(([k, x]) => [k, { per_match: x / n, share: x / tot }]));
  const sg = (k) => acc.stats.get(k) || 0;
  out.drs = Object.fromEntries(['bat_reviews', 'bat_overturned', 'bat_ucall', 'field_success', 'field_spec',
    'field_spec_ucall', 'missed_standing'].map((k) => [k, sg(k) / n]));
  out.drs.missed_outs_lower_bound = (sg('field_success') + sg('missed_standing')) / n;
  out.bowler_fallbacks = sg('bowler_fallback');
  return out;
}

// Run sims [a, b) of a prepared scenario into an Acc. opts: logs (Map sim -> null to collect event logs),
// onProgress(done) every `progressEvery` sims, cancelled() checked between sims (sets acc.cancelled),
// match (a Match of pr to reuse), acc (a bound, unfolded Acc of pr to add to; the caller folds it).
export function simulate(pr, a, b, seed, { logs = null, onProgress = null, progressEvery = 500, cancelled = null, match = null,
  acc = null } = {}) {
  const own = acc === null;
  if (own) acc = new Acc(pr.limited ? Math.floor(pr.rules.max_balls / 6) : null).bind(pr);
  const state = pr.sc.state;
  const m = match || new Match(pr);
  for (let i = a; i < b; i++) {
    if (cancelled !== null && cancelled()) { acc.cancelled = true; break; }
    const log = logs !== null && logs.has(i) ? [] : null;
    m.reset(i, seed, { log, state });
    m.play();
    if (log !== null) logs.set(i, log);
    acc.addMatch(m);
    if (onProgress !== null && (i - a + 1) % progressEvery === 0) onProgress(i - a + 1);
  }
  return own ? acc.fold() : acc;
}

// Sensitivity factors (scenario overrides) that change something in this scenario (sim.default_factors).
export function defaultFactors(sc) {
  const f = {};
  const pitch = pyOr(get(sc, 'pitch'), {});
  if (['runs_sd', 'wkt_sd', 'spin_sd', 'wear_sd'].some((k) => pyBool(get(pitch, k)))) {
    f.pitch = { pitch: { ...pitch, runs_sd: 0.0, wkt_sd: 0.0, spin_sd: 0.0, wear_sd: 0.0 } };
  }
  for (const [pid, s] of Object.entries(pyOr(get(sc, 'player_form'), {}))) {
    if (Object.values(s).some(pyBool)) {
      f[`form:${pid}`] = { player_form: Object.fromEntries(Object.entries(sc.player_form).filter(([k]) => k !== pid)) };
    }
  }
  if (pyBool(get(sc, 'weather'))) f.weather = { weather: null };
  if (!pyBool(get(sc, 'neutral')) && sc.teams.some((t) => pyBool(get(t, 'home')))) f.home = { neutral: true };
  if (pyBool(get(sc, 'umpires'))) f.umpires = { umpires: null };
  const drs = pyOr(get(sc, 'drs'), {});
  if (pyOr(get(drs, 'accuracy_mult'), 1.0) !== 1.0 || pyOr(get(drs, 'ucall_mult'), 1.0) !== 1.0) {
    f.drs = { drs: { ...drs, accuracy_mult: 1.0, ucall_mult: 1.0 } };
  }
  return f;
}

// Paired-difference effect of a factor from per-sim codes ([sim, code] pairs of the base and variant runs).
export function paired(baseCodes, varCodes, target) {
  const b = new Map(baseCodes), v = new Map(varCodes);
  const sims = [...b.keys()].sort((x, y) => x - y);
  const n = sims.length;
  const d = sims.map((s) => (target.includes(b.get(s)) ? 1 : 0) - (target.includes(v.get(s)) ? 1 : 0));
  const s1 = d.reduce((a, x) => a + x, 0), s2 = d.reduce((a, x) => a + x * x, 0);
  const vd = n > 1 ? (s2 - s1 * s1 / n) / (n - 1) : 0.0;
  return { effect: s1 / n, se: Math.sqrt(Math.max(vd, 0.0) / n) };
}

export function sensitivityFrom(baseCodes, factorCodes) {
  const out = {};
  for (const [name, codes] of Object.entries(factorCodes)) {
    out[name] = { p_win0: paired(baseCodes, codes, [0]), p_win1: paired(baseCodes, codes, [1]),
      p_draw_tie: paired(baseCodes, codes, [2, 3]) };
  }
  return out;
}

// Plan 9.7: rerun with each factor reset to neutral on common random numbers (sim.sensitivity).
export function sensitivity(scenario, provider = null, a = 0, b = 2000, seed = 0, factors = null, base = null) {
  const sc = validateScenario(scenario);
  factors = factors === null ? defaultFactors(sc) : factors;
  if (base === null) base = simulate(new Prepared(sc, provider), a, b, seed);
  const fc = {};
  for (const [name, over] of Object.entries(factors)) fc[name] = simulate(new Prepared({ ...sc, ...over }, provider), a, b, seed).codes;
  return sensitivityFrom(base.codes, fc);
}

// Simulate a scenario (plan 9.1) and return the plan 9.7 outputs (sim.run).
export function run(scenario, provider = null, { nSims = null, seed = null, start = 0, logSims = [], factors = null } = {}) {
  const pr = new Prepared(scenario, provider);
  const sc = pr.sc;
  const n = nSims === null ? sc.n_sims : nSims;
  seed = seed === null ? sc.seed : seed;
  const logs = logSims.length ? new Map(logSims.map((i) => [i, null])) : null;
  const acc = simulate(pr, start, start + n, seed, { logs });
  const out = summarize(acc);
  out.part_timers_added = pr.part_timer_report;
  if (logs !== null) out.logs = Object.fromEntries(logs);
  if (sc.sensitivity || pyBool(factors)) out.sensitivity = sensitivity(sc, provider, start, start + n, seed, factors, acc);
  return out;
}

// Scripted-draw mode: apply forced decisions to `state` (or a fresh match) (sim.apply_script).
export function applyScript(scenario, script, state = null, provider = null) {
  const pr = new Prepared(scenario, provider);
  const m = new Match(pr);
  m.reset(0, 0, { script, log: [], state });
  m.play();
  if (m.result === null && m.cur.so) throw new ScriptError('a script must not end inside a super over');
  return { state: m.result !== null ? null : m.toState(), result: m.result, events: m.log };
}

// Full event log of one seeded simulation (sim.trajectory).
export function trajectory(scenario, sim, seed, provider = null, pr = null) {
  pr = pr || new Prepared(scenario, provider);
  const m = new Match(pr);
  const log = [];
  m.reset(sim, seed, { log, state: pr.sc.state });
  m.play();
  const rec = m.record();
  return { events: log, result: m.result, summary: { innings: rec.innings, code: rec.code, deliveries: rec.deliveries } };
}
