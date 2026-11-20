// ES-module adapter between Sheets.simulate (assets/sim-worker.js) and the UMD engine in sim.js.
// Each shard runs its share of the sims in chunks (for progress) with CricketSim.simMatchRaw and pools the
// chunks with CricketSim.mergeRaw. Shards merge the same way, so every distribution on the page is exact.
import './sim.js';

const C = self.CricketSim;
const share = (total, k, parts) => Math.floor(total / parts) + (k < total % parts ? 1 : 0);

export function run(params, ctx) {
  if (!C || !C.simMatchRaw) throw new Error('sim.js did not load (CricketSim.simMatchRaw missing)');
  const P = C.prepare(params.sp);
  const n = share(params.sims, ctx.shard, ctx.shards), chunk = params.chunk || 500, chunks = Math.max(1, Math.ceil(n / chunk));
  let out = null;
  for (let c = 0; c < chunks; c++) {
    const size = share(n, c, chunks); if (!size) continue;
    const seed = (ctx.seed * 7919 + c * 104729 + 1) >>> 0;
    // half the sims each way when the toss is open: alternate the side batting first by chunk
    const opts = Object.assign({}, params.opts, { n: size, seed });
    if (!opts.batFirst) opts.batFirst = ((c + ctx.shard) & 1) ? 'B' : 'A';
    const r = C.simMatchRaw(P, params.A, params.B, opts);
    out = out ? C.mergeRaw(out, r) : r;
    ctx.progress((c + 1) / chunks);
  }
  return out;
}

export function merge(a, b) { return a && b ? C.mergeRaw(a, b) : a || b; }
