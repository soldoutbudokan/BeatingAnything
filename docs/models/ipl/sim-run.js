// ES-module adapter between Sheets.simulate (assets/sim-worker.js) and the UMD engine in sim.js.
// Each shard runs its share of the sims in chunks (for progress) with IPLSim.simMatchRaw, pools the chunks with
// IPLSim.mergeRaw, and returns the raw integer histograms; shards merge the same way, so every distribution on
// the page is exact. Optional `base` runs a second scenario with the same chunk seeds (common random numbers).
import './sim.js';

const I = self.IPLSim;
const CHUNK = 1000;
const share = (total, k, parts) => Math.floor(total / parts) + (k < total % parts ? 1 : 0);
const team = t => ({ name: t.name, order: t.order.slice(0, 11), plan: t.plan, schedule: t.schedule && t.schedule.length === 20 ? t.schedule : I.bowlingSchedule(t.plan) });

export function run(params, ctx) {
  if (!I || !I.simMatchRaw) throw new Error('sim.js did not load (IPLSim.simMatchRaw missing)');
  const P = I.prepare(params.sp);
  const n = share(params.sims, ctx.shard, ctx.shards), chunks = Math.max(1, Math.ceil(n / CHUNK));
  const A = team(params.A), B = team(params.B);
  const bA = params.base ? team(params.base.A) : null, bB = params.base ? team(params.base.B) : null;
  const jobs = params.base ? 2 : 1;
  let main = null, base = null, done = 0;
  for (let c = 0; c < chunks; c++) {
    const size = share(n, c, chunks); if (!size) continue;
    const seed = (ctx.seed * 7919 + c * 104729 + 1) >>> 0;
    const r = I.simMatchRaw(P, A, B, Object.assign({}, params.opts, { n: size, seed }));
    main = main ? I.mergeRaw(main, r) : r;
    done++; ctx.progress(done / (chunks * jobs));
    if (params.base) {
      const rb = I.simMatchRaw(P, bA, bB, Object.assign({}, params.base.opts, { n: size, seed }));
      base = base ? I.mergeRaw(base, rb) : rb;
      done++; ctx.progress(done / (chunks * jobs));
    }
  }
  return { main, base };
}

export function merge(a, b) {
  return { main: a.main && b.main ? I.mergeRaw(a.main, b.main) : a.main || b.main, base: a.base && b.base ? I.mergeRaw(a.base, b.base) : a.base || b.base };
}
