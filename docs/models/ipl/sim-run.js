// ES-module adapter between Sheets.simulate (assets/sim-worker.js) and the UMD engine in sim.js.
// sim.js's simMatch() returns quantile summaries, which cannot be pooled across workers. This adapter
// replays simMatch's match loop (two innings + super over, exactly as sim.js simOneWay) on the exported
// IPLSim.simInnings, and accumulates integer histograms for every quantity, so shards merge by addition
// and every distribution on the page is exact. With the same seed it consumes the RNG exactly as
// IPLSim.simMatch does (checked in node against IPLSim.summarize).
// Optional `base` runs a second scenario with the same chunk seeds (common random numbers).
import './sim.js';

const I = self.IPLSim;
const CHUNK = 1000;
const TOP = [10, 20, 30, 40, 50, 75, 100];
const Z = n => new Array(n).fill(0);
const bump = (a, v) => { a[v < 0 ? 0 : v >= a.length ? a.length - 1 : v]++; };

function share(total, k, parts) { return Math.floor(total / parts) + (k < total % parts ? 1 : 0); }

function deathBowler(sched) {
  const last5 = sched.slice(15); let best = last5[0], bc = 0;
  last5.forEach(b => { const c = last5.filter(x => x === b).length; if (c > bc) { bc = c; best = b; } });
  return best;
}
function uniq(sched) { const out = []; sched.forEach(b => { if (!out.includes(b)) out.push(b); }); return out; }

function newSide(team) {
  return {
    order: team.order.slice(0, 11), bowlers: uniq(team.schedule), schedule: team.schedule,
    total: Z(451), t1: Z(451), t2: Z(451), pp: Z(201), fow1: Z(451), fours: Z(61), sixes: Z(61), wk: Z(11), wides: Z(31), extras: Z(61),
    n1: 0, n2: 0, win1: 0, win2: 0,
    bat: team.order.slice(0, 11).map(id => ({ id, runs: Z(201), balls: Z(121), f4: Z(31), s6: Z(26), batted: 0, out: 0, duck: 0, top: 0 })),
    bowl: uniq(team.schedule).map(id => ({ id, balls: 0, wk: Z(11), conc: Z(101), top: 0 })),
  };
}
export function newAcc(A, B) {
  return { n: 0, winA: 0, tie: 0, total: Z(901), inn1: Z(451), sixes: Z(121), fours: Z(141), A: newSide(A), B: newSide(B) };
}

/* add one innings (res from simInnings, track=true) for batting side X, bowled by side Y */
function addInnings(acc, X, Y, res, n, first, winX) {
  const nb = X.order.length, ids = res.bowlIds, nw = ids.length;
  const map = ids.map(id => Y.bowl.findIndex(b => b.id === id));
  for (let i = 0; i < n; i++) {
    const sc = res.score[i];
    bump(X.total, sc); bump(first ? X.t1 : X.t2, sc); bump(X.pp, res.pp[i]); bump(X.fow1, res.fow1[i]);
    bump(X.fours, res.fours[i]); bump(X.sixes, res.sixes[i]); bump(X.wk, res.wk[i]); bump(X.wides, res.wides[i]); bump(X.extras, res.extras[i]);
    if (first) { X.n1++; X.win1 += winX[i]; } else { X.n2++; X.win2 += winX[i]; }
    const off = i * nb; let top = -1, ntop = 0, k;
    for (k = 0; k < nb; k++) if (res.batRuns[off + k] > top) top = res.batRuns[off + k];
    for (k = 0; k < nb; k++) if (res.batted[off + k] && res.batRuns[off + k] === top) ntop++;
    for (k = 0; k < nb; k++) {
      const b = X.bat[k], r = res.batRuns[off + k];
      bump(b.runs, r); bump(b.balls, res.batBalls[off + k]); bump(b.f4, res.bat4[off + k]); bump(b.s6, res.bat6[off + k]);
      b.batted += res.batted[off + k]; b.out += res.batOut[off + k];
      if (res.batOut[off + k] && r === 0) b.duck++;
      if (res.batted[off + k] && r === top && ntop > 0) b.top += 1 / ntop;
    }
    const ow = i * nw; let best = -1e9, nbst = 0;
    for (k = 0; k < nw; k++) { const key = res.bowlWkts[ow + k] * 1000 - res.bowlRuns[ow + k]; if (key > best) best = key; }
    for (k = 0; k < nw; k++) if (res.bowlWkts[ow + k] * 1000 - res.bowlRuns[ow + k] === best) nbst++;
    for (k = 0; k < nw; k++) {
      const j = map[k]; if (j < 0) continue; const bw = Y.bowl[j];
      bw.balls += res.bowlBalls[ow + k]; bump(bw.wk, res.bowlWkts[ow + k]); bump(bw.conc, res.bowlRuns[ow + k]);
      if (res.bowlWkts[ow + k] * 1000 - res.bowlRuns[ow + k] === best) bw.top += 1 / nbst;
    }
  }
}

/* mirror of sim.js simOneWay, accumulating into acc */
function oneWay(P, acc, A, B, V, env, n, rng, first) {
  if (n <= 0) return;
  const F = first === 'A' ? { k: 'A', t: A } : { k: 'B', t: B }, S = first === 'A' ? { k: 'B', t: B } : { k: 'A', t: A };
  const i1 = I.simInnings(P, rng, n, F.t.order.slice(0, 11), S.t.schedule, V, env, 1, null, 10, 20, true);
  const tg = new Int32Array(n); for (let i = 0; i < n; i++) tg[i] = i1.score[i] + 1;
  const i2 = I.simInnings(P, rng, n, S.t.order.slice(0, 11), F.t.schedule, V, env, 2, tg, 10, 20, true);
  const fw = new Float64Array(n), tied = [];
  for (let i = 0; i < n; i++) { if (i1.score[i] > i2.score[i]) fw[i] = 1; else if (i1.score[i] === i2.score[i]) tied.push(i); }
  if (tied.length) {
    const m = tied.length;
    const so1 = I.simInnings(P, rng, m, S.t.order.slice(0, 3), [deathBowler(F.t.schedule)], V, env, 1, null, 2, 1, false);
    const t2 = new Int32Array(m); for (let i = 0; i < m; i++) t2[i] = so1.score[i] + 1;
    const so2 = I.simInnings(P, rng, m, F.t.order.slice(0, 3), [deathBowler(S.t.schedule)], V, env, 2, t2, 2, 1, false);
    for (let i = 0; i < m; i++) { let w = so2.score[i] > so1.score[i] ? 1 : 0; if (so2.score[i] === so1.score[i]) w = rng() < 0.5 ? 1 : 0; fw[tied[i]] = w; }
  }
  const fl = new Float64Array(n); for (let i = 0; i < n; i++) fl[i] = 1 - fw[i];
  addInnings(acc, acc[F.k], acc[S.k], i1, n, true, fw);
  addInnings(acc, acc[S.k], acc[F.k], i2, n, false, fl);
  for (let i = 0; i < n; i++) {
    acc.n++; acc.tie += i1.score[i] === i2.score[i] ? 1 : 0; acc.winA += F.k === 'A' ? fw[i] : fl[i];
    bump(acc.total, i1.score[i] + i2.score[i]); bump(acc.inn1, i1.score[i]);
    bump(acc.sixes, i1.sixes[i] + i2.sixes[i]); bump(acc.fours, i1.fours[i] + i2.fours[i]);
  }
}

/** one simMatch-equivalent call (same RNG use as IPLSim.simMatch with this seed) */
export function simChunk(P, acc, A, B, opts, n, seed) {
  const rng = I.makeRng(seed || 1);
  const V = (opts.venue && P.raw.venues[opts.venue]) || P.raw.venue_neutral;
  const env = P.raw.env[opts.env || P.raw.default_env];
  if (opts.batFirst === 'A' || opts.batFirst === 'B') oneWay(P, acc, A, B, V, env, n, rng, opts.batFirst);
  else { const hh = Math.floor(n / 2); oneWay(P, acc, A, B, V, env, hh, rng, 'A'); oneWay(P, acc, A, B, V, env, n - hh, rng, 'B'); }
}

const team = t => ({ name: t.name, order: t.order.slice(0, 11), plan: t.plan, schedule: t.schedule && t.schedule.length === 20 ? t.schedule : I.bowlingSchedule(t.plan) });

export function run(params, ctx) {
  if (!I) throw new Error('sim.js did not load (IPLSim missing)');
  const P = I.prepare(params.sp);
  const n = share(params.sims, ctx.shard, ctx.shards);
  const chunks = Math.max(1, Math.ceil(n / CHUNK));
  const A = team(params.A), B = team(params.B);
  const out = { main: newAcc(A, B), base: null };
  let bA, bB;
  if (params.base) { bA = team(params.base.A); bB = team(params.base.B); out.base = newAcc(bA, bB); }
  const jobs = params.base ? 2 : 1; let done = 0;
  for (let c = 0; c < chunks; c++) {
    const size = share(n, c, chunks); if (!size) continue;
    const seed = (ctx.seed * 7919 + c * 104729 + 1) >>> 0;
    simChunk(P, out.main, A, B, params.opts || {}, size, seed);
    done++; ctx.progress(done / (chunks * jobs));
    if (params.base) { simChunk(P, out.base, bA, bB, params.base.opts || {}, size, seed); done++; ctx.progress(done / (chunks * jobs)); }
  }
  return out;
}

function addArr(a, b) { for (let i = 0; i < a.length; i++) a[i] += b[i]; }
function mergeSide(a, b) {
  ['total', 't1', 't2', 'pp', 'fow1', 'fours', 'sixes', 'wk', 'wides', 'extras'].forEach(k => addArr(a[k], b[k]));
  ['n1', 'n2', 'win1', 'win2'].forEach(k => { a[k] += b[k]; });
  a.bat.forEach((x, i) => { const y = b.bat[i]; ['runs', 'balls', 'f4', 's6'].forEach(k => addArr(x[k], y[k])); ['batted', 'out', 'duck', 'top'].forEach(k => { x[k] += y[k]; }); });
  a.bowl.forEach((x, i) => { const y = b.bowl[i]; addArr(x.wk, y.wk); addArr(x.conc, y.conc); x.balls += y.balls; x.top += y.top; });
}
function mergeAcc(a, b) {
  if (!a) return b; if (!b) return a;
  a.n += b.n; a.winA += b.winA; a.tie += b.tie; ['total', 'inn1', 'sixes', 'fours'].forEach(k => addArr(a[k], b[k]));
  mergeSide(a.A, b.A); mergeSide(a.B, b.B);
  return a;
}
export function merge(a, b) { return { main: mergeAcc(a.main, b.main), base: mergeAcc(a.base, b.base) }; }
export const TOP_THRESH = TOP;
