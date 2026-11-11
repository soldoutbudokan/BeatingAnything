// JS-vs-Python parity check for docs/models/wnba/sim.js
// Run from the repo root after `python -m models.wnba.parity`:  node models/wnba/parity_check.js
'use strict';
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..', '..');
const WNBASim = require(path.join(root, 'docs/models/wnba/sim.js'));
const params = JSON.parse(fs.readFileSync(path.join(root, 'docs/models/wnba/data/sim_params.json')));
const ref = JSON.parse(fs.readFileSync(path.join(root, 'data/processed/wnba/parity_py.json')));

const N = 20000;
let fails = 0, checks = 0;
const report = [];
function check(label, a, b, se, tol) {
  checks++;
  const z = Math.abs(a - b) / Math.max(se, 1e-9);
  const ok = z <= tol;
  if (!ok) fails++;
  return { label, py: +b.toFixed(4), js: +a.toFixed(4), z: +z.toFixed(2), ok };
}

for (const sc of ref) {
  const t0 = Date.now();
  const r = WNBASim.simulate(params, sc.home, sc.away, Object.assign({ nSims: N, seed: 7 }, sc.opts));
  const secs = (Date.now() - t0) / 1000;
  const t1 = Date.now();
  WNBASim.simulate(params, sc.home, sc.away, Object.assign({ nSims: 10000, seed: 3 }, sc.opts));
  const secs10k = (Date.now() - t1) / 1000;
  const g = r.game, p = sc.game, rows = [];
  const se2 = (sd) => Math.sqrt(2 * sd * sd / N);
  rows.push(check('home_win', g.home_win, p.home_win, Math.sqrt(2 * p.home_win * (1 - p.home_win) / N), 4));
  rows.push(check('margin_mean', g.margin.mean, p.margin.mean, se2(p.margin.sd), 4));
  rows.push(check('total_mean', g.total.mean, p.total.mean, se2(p.total.sd), 4));
  rows.push(check('margin_sd', g.margin.sd, p.margin.sd, p.margin.sd / Math.sqrt(N), 4));
  rows.push(check('total_sd', g.total.sd, p.total.sd, p.total.sd / Math.sqrt(N), 4));
  rows.push(check('poss', g.poss_per_team, p.poss, 0.05, 4));
  rows.push(check('p_ot', g.p_ot, p.p_ot, Math.sqrt(2 * Math.max(p.p_ot, 0.01) / N), 4));
  // minutes reallocation must be identical (deterministic)
  let maxMinDiff = 0;
  [[r.home, r.meta.home_minutes], [r.away, r.meta.away_minutes]].forEach(([pl, mins]) => {
    pl.forEach((x, i) => { maxMinDiff = Math.max(maxMinDiff, Math.abs(mins[i] - sc.minutes[String(x.id)])); });
  });
  checks++; if (maxMinDiff > 1e-3) fails++;
  // player means
  let pz = [], pf = 0;
  for (const x of r.home.concat(r.away)) {
    const q = sc.players[String(x.id)];
    if (!q) continue;
    for (const k of ['min', 'pts', 'reb', 'ast', 'fg3m', 'stl', 'blk', 'tov']) {
      const se = Math.sqrt(2 * q[k][1] * q[k][1] / N) + 1e-3;
      const z = Math.abs(x[k].mean - q[k][0]) / se;
      pz.push(z); checks++;
      if (z > 4.5) { pf++; fails++; }
    }
  }
  report.push({ scenario: sc.name, js_seconds_20k: secs, js_seconds_10k: secs10k, py_seconds_20k: sc.seconds, game: rows,
    max_minutes_diff: maxMinDiff, player_checks: pz.length, player_fail: pf,
    player_mean_abs_z: +(pz.reduce((a, b) => a + b, 0) / pz.length).toFixed(2) });
}
const out = { checks, fails, pass: fails === 0, report };
fs.writeFileSync(path.join(root, 'data/processed/wnba/parity_report.json'), JSON.stringify(out, null, 1));
for (const r of report) {
  console.log(`${r.scenario}: js10k ${r.js_seconds_10k.toFixed(2)}s py20k ${r.py_seconds_20k.toFixed(2)}s | ` +
    r.game.map((x) => `${x.label} py ${x.py} js ${x.js} z ${x.z}${x.ok ? '' : ' FAIL'}`).join('; ') +
    ` | minutesΔ ${r.max_minutes_diff.toExponential(1)} | players mean|z| ${r.player_mean_abs_z} fails ${r.player_fail}/${r.player_checks}`);
}
console.log(`parity: ${checks - fails}/${checks} checks pass`);
process.exit(fails === 0 ? 0 : 1);
