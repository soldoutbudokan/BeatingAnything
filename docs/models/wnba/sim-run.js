// ES-module adapter between Sheets.simulate (assets/sim-worker.js) and the UMD engine in sim.js.
// Each shard runs its share of the sims in chunks (for progress) and returns the raw sim.js summaries;
// the page pools the chunks (WNBA.mergeRuns). Optional `base` runs the default scenario with the same
// seeds (common random numbers) so "vs default" deltas carry less Monte Carlo noise.
import './sim.js';

const W = self.WNBASim;
const CHUNK = 1250;

function share(total, shard, shards) { return Math.floor(total / shards) + (shard < total % shards ? 1 : 0); }

export function run(params, ctx) {
  if (!W) throw new Error('sim.js did not load (WNBASim missing)');
  const n = share(params.sims, ctx.shard, ctx.shards);
  const chunks = Math.max(1, Math.ceil(n / CHUNK));
  const runs = [], base = [];
  const jobs = params.base ? 2 : 1;
  let done = 0;
  for (let c = 0; c < chunks; c++) {
    const size = share(n, c, chunks);
    if (!size) continue;
    const seed = (ctx.seed * 7919 + c * 104729 + 1) >>> 0;
    runs.push(W.simulate(params.sp, params.home, params.away, Object.assign({}, params.opts, { nSims: size, seed })));
    done++; ctx.progress(done / (chunks * jobs));
    if (params.base) {
      base.push(W.simulate(params.sp, params.base.home, params.base.away, Object.assign({}, params.base.opts, { nSims: size, seed })));
      done++; ctx.progress(done / (chunks * jobs));
    }
  }
  return { runs, base };
}

export function merge(a, b) {
  return { runs: a.runs.concat(b.runs), base: a.base.concat(b.base) };
}
