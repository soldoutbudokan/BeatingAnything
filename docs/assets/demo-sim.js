// Synthetic T20-style innings simulator used by demo.html to exercise Sheets.simulate().
// Contract: export run(params, ctx) and, for multi-worker runs, merge(a, b).
// ctx = {shard, shards, seed, rng, progress(frac, partial)}; rng() is a seeded uniform with .normal/.int/.poisson/.weighted.

export function run(p, ctx) {
  const { sims = 100000, order = [], aggression = 1, pitch = 1, balls = 120 } = p;
  const r = ctx.rng;
  const mine = Math.floor(sims / ctx.shards) + (ctx.shard < sims % ctx.shards ? 1 : 0);
  const counts = new Float64Array(321), wk = new Float64Array(11);
  const skills = order.length ? order : new Array(11).fill(0);
  for (let s = 0; s < mine; s++) {
    let runs = 0, w = 0, striker = 0;
    for (let b = 0; b < balls && w < 10; b++) {
      const sk = skills[Math.min(striker, skills.length - 1)];
      const phase = b < 36 ? 1.05 : b >= 96 ? 1.25 : 0.95;
      const pOut = 0.046 * (1.05 - 0.22 * sk) * (0.6 + 0.4 * aggression * phase) / pitch;
      let u = r();
      if (u < pOut) { w++; striker++; continue; }
      u = r();
      const p6 = 0.036 * aggression * phase * (1 + 0.5 * sk) * pitch, p4 = 0.092 * aggression * phase * pitch, p2 = 0.07, p1 = 0.37;
      if (u < p6) runs += 6; else if (u < p6 + p4) runs += 4; else if (u < p6 + p4 + p2) runs += 2; else if (u < p6 + p4 + p2 + p1) runs += 1;
      if (r() < 0.035) runs += 1; // extras
    }
    counts[Math.min(320, runs)]++; wk[w]++;
    if ((s & 2047) === 0) ctx.progress(s / mine, { counts: Array.from(counts), n: s + 1 });
  }
  ctx.progress(1, { counts: Array.from(counts), n: mine });
  return { counts: Array.from(counts), wk: Array.from(wk), n: mine };
}

export function merge(a, b) {
  return { counts: a.counts.map((v, i) => v + b.counts[i]), wk: a.wk.map((v, i) => v + b.wk[i]), n: a.n + b.n };
}
