// Node driver for docs/models/cricket/sim.js: the build runs every published simulation through the same
// engine the browser uses.  Usage: node models/intl/sim_cli.js <jobs.json> <out.json>
//   jobs.json = {params: "<path to sim_params.json>", jobs: [{id, A, B, opts, n, seed, hists}]}
//   out.json  = {results: [{id, summary, hists?}], secs}
// hists: optional list of "A.t1"-style paths into the raw counts to return alongside the summary.
const fs = require('fs');
const path = require('path');
const Sim = require(path.resolve(__dirname, '..', '..', 'docs', 'models', 'cricket', 'sim.js'));

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const P = Sim.prepare(JSON.parse(fs.readFileSync(spec.params, 'utf8')));
const t0 = Date.now();
const results = spec.jobs.map((j, k) => {
  const raw = Sim.simMatchRaw(P, j.A, j.B, Object.assign({}, j.opts, { n: j.n || 5000, seed: j.seed || (k + 1) }));
  const out = { id: j.id, summary: Sim.summarizeRaw(raw) };
  if (j.hists) {
    out.hists = {};
    j.hists.forEach(h => {
      const [a, b] = h.split('.');
      out.hists[h] = a === 'match' ? raw.match[b] : a === 'res' ? raw.res : a === 'first' ? raw.first : raw.teams[a][b];
    });
  }
  return out;
});
fs.writeFileSync(process.argv[3], JSON.stringify({ results, secs: (Date.now() - t0) / 1000 }));
