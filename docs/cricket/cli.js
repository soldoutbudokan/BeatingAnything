#!/usr/bin/env node
// Command-line wrapper of the cricket engine for bulk evaluation and parity checks (plan section 9.6).
//
//   node docs/cricket/cli.js [scenarios.jsonl | -] [--workers N] [--sims N] [--seed S] [--start K]
//        [--chunk N] [--bundle params.json] [--trace [--trace-sims 0,1,2]] [--timing] [--progress]
//
// Input: JSON lines, each a scenario (plan 9.1) or a wrapper {"name", "scenario"} (the rows of
// tests/data/cricket_parity/trajectories.jsonl; rows whose scenario is null are skipped); blank lines are
// ignored. Output: one JSON line per scenario, {"name", ...} with the outputs of beating.cricket.sim.run
// (summarize keys, part_timers_added, sensitivity when the scenario asks for it), in input order. --trace
// writes instead one line per traced sim in the trajectories.jsonl format: {"name", "scenario" (the
// input scenario on the first traced sim, else null), "seed", "sim", "events", "result", "summary"}.
//
// --workers N runs the sim range on N worker_threads (worker.js) in chunks of --chunk sims (default about
// n / (4 N), at least 250); each chunk returns an integer Acc and the merge is exact, so the output is
// identical for any N. Sensitivity factor reruns are dispatched the same way. --timing reports elapsed
// time and deliveries per second per scenario on stderr; --progress prints sim counts to stderr.

import fs from 'node:fs';
import os from 'node:os';
import { Worker } from 'node:worker_threads';
import { Prepared, simulate, summarize, Acc, trajectory, defaultFactors, sensitivityFrom } from './engine.js';
import { createProvider, validateScenario, pyBool } from './provider.js';

function parseArgs(argv) {
  const o = { input: '-', workers: 1, sims: null, seed: null, start: 0, chunk: null, bundle: null, trace: false,
    traceSims: [0, 1, 2], timing: false, progress: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], next = () => argv[++i];
    if (a === '--workers') o.workers = Math.max(1, parseInt(next(), 10));
    else if (a === '--sims') o.sims = parseInt(next(), 10);
    else if (a === '--seed') o.seed = parseInt(next(), 10);
    else if (a === '--start') o.start = parseInt(next(), 10);
    else if (a === '--chunk') o.chunk = parseInt(next(), 10);
    else if (a === '--bundle') o.bundle = next();
    else if (a === '--trace') o.trace = true;
    else if (a === '--trace-sims') o.traceSims = next().split(',').filter(Boolean).map((x) => parseInt(x, 10));
    else if (a === '--timing') o.timing = true;
    else if (a === '--progress') o.progress = true;
    else if (a === '-h' || a === '--help') {
      process.stdout.write(fs.readFileSync(new URL(import.meta.url), 'utf8').split('\n').slice(1, 20)
        .map((l) => l.replace(/^\/\/ ?/, '')).join('\n') + '\n');
      process.exit(0);
    } else if (a.startsWith('--')) throw new Error(`unknown option ${a}`);
    else o.input = a;
  }
  return o;
}

function readItems(input) {
  const text = fs.readFileSync(input === '-' ? 0 : input, 'utf8');
  const items = [];
  text.split('\n').forEach((line, i) => {
    if (!line.trim()) return;
    const x = JSON.parse(line);
    if (x !== null && typeof x === 'object' && 'fam' in x) items.push({ name: x.name ?? `line${i + 1}`, scenario: x });
    else if (x && x.scenario) items.push({ name: x.name ?? `line${i + 1}`, scenario: x.scenario });
  });
  return items;
}

const write = (obj) => new Promise((r) => { if (process.stdout.write(JSON.stringify(obj) + '\n')) r(); else process.stdout.once('drain', r); });

class Pool {
  constructor(n) {
    const execArgv = process.execArgv.filter((a) => !a.startsWith('--input-type') && a !== '-e' && a !== '--eval');
    this.workers = Array.from({ length: n }, () => new Worker(new URL('./worker.js', import.meta.url), { execArgv }));
    this.idle = [...this.workers];
    this.queue = [];
    this.pending = new Map();
    this.nextId = 0;
    for (const w of this.workers) {
      w.on('message', (m) => this._onMessage(w, m));
      w.on('error', (e) => { for (const p of this.pending.values()) p.reject(e); });
    }
  }

  _onMessage(w, m) {
    const p = this.pending.get(m.id);
    if (!p) return;
    if (m.type === 'progress') { if (p.onProgress) p.onProgress(m); return; }
    this.pending.delete(m.id);
    this.idle.push(w);
    this._pump();
    if (m.type === 'error') p.reject(new Error(m.message));
    else p.resolve(m);
  }

  _pump() {
    while (this.idle.length && this.queue.length) {
      const [msg, p] = this.queue.shift();
      this.pending.set(msg.id, p);
      this.idle.pop().postMessage(msg);
    }
  }

  run(msg, onProgress = null) {
    return new Promise((resolve, reject) => {
      const m = { type: 'run', id: this.nextId++, ...msg };
      this.queue.push([m, { resolve, reject, onProgress }]);
      this._pump();
    });
  }

  close() { return Promise.all(this.workers.map((w) => w.terminate())); }
}

// Run sims [a, b) of `scenario` on the pool in chunks; returns the merged Acc and the part-timer report.
async function poolSimulate(pool, scenario, key, a, b, seed, opts) {
  const chunk = opts.chunk || Math.max(250, Math.ceil((b - a) / (4 * pool.workers.length)));
  const jobs = [];
  let done = 0;
  for (let i = a; i < b; i += chunk) {
    jobs.push(pool.run({ scenario, key, simRange: [i, Math.min(b, i + chunk)], seed, bundleUrl: opts.bundle },
      opts.progress ? () => {} : null));
  }
  const res = await Promise.all(jobs.map((j) => j.then((r) => {
    done += r.simRange[1] - r.simRange[0];
    if (opts.progress) process.stderr.write(`  ${key}: ${done}/${b - a} sims\n`);
    return r;
  })));
  const acc = Acc.fromJSON(res[0].acc);
  for (const r of res.slice(1)) acc.merge(Acc.fromJSON(r.acc));
  return { acc, partTimers: res[0].part_timers_added };
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  const items = readItems(o.input);
  const bundle = o.bundle ? JSON.parse(fs.readFileSync(o.bundle, 'utf8')) : null;
  const provider = createProvider(bundle);
  if (o.trace) {
    for (const { name, scenario } of items) {
      const pr = new Prepared(scenario, provider);
      const seed = o.seed === null ? pr.sc.seed : o.seed;
      for (const [i, sim] of o.traceSims.entries()) {
        const t = trajectory(null, sim, seed, provider, pr);
        await write({ name, scenario: i === 0 ? scenario : null, seed, sim, events: t.events, result: t.result, summary: t.summary });
      }
    }
    return;
  }
  const pool = o.workers > 1 ? new Pool(o.workers) : null;
  try {
    for (const [idx, { name, scenario }] of items.entries()) {
      const t0 = process.hrtime.bigint();
      const sc = validateScenario(scenario);
      const n = o.sims === null ? sc.n_sims : o.sims;
      const seed = o.seed === null ? sc.seed : o.seed;
      const a = o.start, b = o.start + n;
      const factors = sc.sensitivity ? defaultFactors(sc) : {};
      let acc, partTimers;
      const fc = {};
      if (pool === null) {
        const pr = new Prepared(sc, provider);
        acc = simulate(pr, a, b, seed, { onProgress: o.progress ? (k) => process.stderr.write(`  ${name}: ${k}/${n} sims\n`) : null });
        partTimers = pr.part_timer_report;
        for (const [fname, over] of Object.entries(factors)) fc[fname] = simulate(new Prepared({ ...sc, ...over }, provider), a, b, seed).codes;
      } else {
        const runs = [poolSimulate(pool, sc, `${idx}`, a, b, seed, o),
          ...Object.entries(factors).map(([fname, over]) => poolSimulate(pool, { ...sc, ...over }, `${idx}:${fname}`, a, b, seed, o))];
        const res = await Promise.all(runs);
        ({ acc, partTimers } = res[0]);
        Object.keys(factors).forEach((fname, j) => { fc[fname] = res[j + 1].acc.codes; });
      }
      const out = { name, ...summarize(acc), part_timers_added: partTimers };
      if (pyBool(factors) || sc.sensitivity) out.sensitivity = sensitivityFrom(acc.codes, fc);
      await write(out);
      if (o.timing) {
        const dt = Number(process.hrtime.bigint() - t0) / 1e9;
        process.stderr.write(`${name}: ${n} sims, ${acc.deliveries} deliveries, ${dt.toFixed(3)} s, ` +
          `${(acc.deliveries / dt / 1e6).toFixed(3)} M deliveries/s, workers ${o.workers} (${os.availableParallelism?.() ?? os.cpus().length} cpus)\n`);
      }
    }
  } finally {
    if (pool !== null) await pool.close();
  }
}

main().catch((e) => {
  process.stderr.write(`${e && e.stack ? e.stack : e}\n`);
  process.exit(1);
});
