// Generic module worker used by Sheets.simulate(). Do not edit per sport: pass your own sim module URL instead.
// Message in:  {module, params, shard, shards, seed}
// Messages out: {type:'progress', frac, partial} | {type:'done', result} | {type:'error', message, stack}
function rng(seed) {
  let a = seed >>> 0;
  const r = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  let spare = null;
  r.normal = (mu = 0, sd = 1) => { if (spare != null) { const s = spare; spare = null; return mu + sd * s; } let u, v, q; do { u = r() * 2 - 1; v = r() * 2 - 1; q = u * u + v * v; } while (q >= 1 || q === 0); const f = Math.sqrt(-2 * Math.log(q) / q); spare = v * f; return mu + sd * u * f; };
  r.int = n => Math.floor(r() * n);
  r.poisson = l => { if (l > 30) return Math.max(0, Math.round(r.normal(l, Math.sqrt(l)))); const L = Math.exp(-l); let k = 0, p = 1; do { k++; p *= r(); } while (p > L); return k - 1; };
  r.weighted = cum => { const u = r() * cum[cum.length - 1]; let i = 0; while (cum[i] < u) i++; return i; };
  return r;
}
self.onmessage = async e => {
  const { module, params, shard = 0, shards = 1, seed = 1 } = e.data || {};
  try {
    const mod = await import(module);
    const fn = mod.run || mod.default;
    if (typeof fn !== 'function') throw new Error(module + ' does not export run(params, ctx)');
    let last = 0;
    const ctx = {
      shard, shards, seed,
      rng: rng(seed + shard * 0x9E3779B1),
      // throttled to ~20 messages a second; the final call (frac >= 1) always goes through
      progress(frac, partial) { const t = performance.now(); if (frac < 1 && t - last < 50) return; last = t; self.postMessage({ type: 'progress', frac, partial }); },
    };
    const result = await fn(params, ctx);
    self.postMessage({ type: 'done', result });
  } catch (err) {
    self.postMessage({ type: 'error', message: String((err && err.message) || err), stack: err && err.stack });
  }
};
