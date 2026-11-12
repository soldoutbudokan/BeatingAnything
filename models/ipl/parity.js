// Node parity harness: runs docs/models/ipl/sim.js on the matchups listed in a Python reference file and
// writes the JS summaries plus timings.  Usage: node models/ipl/parity.js <py_ref.json> <out.json>
const fs = require("fs");
const path = require("path");
const root = path.resolve(__dirname, "..", "..");
const IPLSim = require(path.join(root, "docs/models/ipl/sim.js"));
const params = JSON.parse(fs.readFileSync(path.join(root, "docs/models/ipl/data/sim_params.json"), "utf8"));
const ref = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const P = IPLSim.prepare(params);
const out = { cases: [], timings: [] };
// warm-up + timing on the first case
const c0 = ref.cases[0];
for (let rep = 0; rep < 3; rep++) {
  const t = Date.now();
  IPLSim.simMatch(P, c0.A, c0.B, { venue: c0.venue, n: 10000, seed: 100 + rep });
  out.timings.push((Date.now() - t) / 1000);
}
ref.cases.forEach((c, i) => {
  const s = IPLSim.simMatch(P, c.A, c.B, { venue: c.venue, n: c.n, seed: 7 + i, batFirst: c.batFirst || null, conditions: c.conditions || null });
  out.cases.push(s);
});
fs.writeFileSync(process.argv[3], JSON.stringify(out));
console.log("js timings (10k sims):", out.timings.map((x) => x.toFixed(2)).join(", "));
