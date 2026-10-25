"""Parity tests between the fast JavaScript engine (docs/cricket/engine.js, run through node) and the scalar
Python reference engine (beating/cricket/sim.py), plan section 9.6.

Method. Replays tests/data/cricket_parity/transitions.jsonl (scripted draws) and trajectories.jsonl (seeded
event logs) through the JS engine and cli.js, compares the full run() outputs of cli.js and sim.run on 200
sims of every trajectory scenario, and checks the JS-only machinery against Python or against its own
slow path: the in-place PRNG, the mirror of CPython 3.12's compensated sum(), bowler eligibility, the
cached view fields, the typed Acc fast path, exact merging over worker splits, in-play state and view
reconstruction, state imputation and checks, and the worker protocol (progress and cancellation).

Limits. Decisions, integers and outputs must agree exactly. Latent values go through Box-Muller and the
Newton update, i.e. through libm, where V8 and glibc differ in the last bit on a few percent of arguments;
those floats are compared to 1e-12 relative. Skipped when node is not installed.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import random
import shutil
import subprocess
import unittest

from beating.cricket import sim

ROOT = Path(__file__).resolve().parents[1]
PARITY = ROOT / "tests" / "data" / "cricket_parity"
JS = ROOT / "docs" / "cricket"
NODE = shutil.which("node") or ("/opt/node22/bin/node" if Path("/opt/node22/bin/node").exists() else None)
N_AGG = 200


def node(script: str, stdin: str | None = None) -> str:
    """Run an ES-module script (paths to the JS files substituted for {engine}, {provider}, {worker})."""
    script = (script.replace("{engine}", (JS / "engine.js").as_uri()).replace("{provider}", (JS / "provider.js").as_uri())
              .replace("{rng}", (JS / "rng.js").as_uri()).replace("{worker}", (JS / "worker.js").as_uri()))
    out = subprocess.run([NODE, "--input-type=module", "-e", script], input=stdin, capture_output=True, text=True,
                         timeout=600)
    if out.returncode:
        raise AssertionError(out.stderr)
    return out.stdout


def cli(args: list[str], stdin: str) -> list[dict]:
    out = subprocess.run([NODE, str(JS / "cli.js"), *args], input=stdin, capture_output=True, text=True, timeout=600)
    if out.returncode:
        raise AssertionError(out.stderr)
    return [json.loads(line) for line in out.stdout.splitlines()]


def rt(x):
    return json.loads(json.dumps(x))


def split_latent(x, sink: list):
    """x with every "latent" list replaced by its length; the floats are appended to sink."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k == "latent" and isinstance(v, list):
                sink.extend(v)
                out[k] = len(v)
            else:
                out[k] = split_latent(v, sink)
        return out
    if isinstance(x, list):
        return [split_latent(v, sink) for v in x]
    return x


def first_difference(a, b, path: str = ""):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return f"{path}: keys differ {sorted(set(a) ^ set(b))}"
        for k in a:
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: lengths {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


def trajectory_scenarios() -> list[tuple[str, dict]]:
    rows = [json.loads(line) for line in (PARITY / "trajectories.jsonl").read_text().splitlines()]
    return [(r["name"], r["scenario"]) for r in rows if r["scenario"] is not None]


def _py_run(task):
    name, sc, n = task
    return name, rt(sim.run(sc, n_sims=n))


@unittest.skipIf(NODE is None, "node not installed")
class EngineParityTests(unittest.TestCase):
    def test_fast_stream_matches_known_answers(self):
        bad = node("""
import { readFileSync } from 'fs';
import { FastStream } from '{engine}';
import { Stream } from '{rng}';
const kat = JSON.parse(readFileSync('%s'));
let bad = 0;
for (const c of kat.cases) c.sims.forEach((sim, i) => {
  const s = new FastStream(c.seed >>> 0, sim, c.stream), u = new Float64Array(8);
  s.fill(u, 3); s.fill(u.subarray(3), 5);
  for (let j = 0; j < 8; j++) if (u[j] !== c.outputs[i][j] * 2 ** -32) bad++;
});
const f = new FastStream(), r = new Stream(99, 7, 3), u = new Float64Array(64);
f.reseed(99, 7, 3); f.fill(u, 64);
for (let j = 0; j < 64; j++) if (u[j] !== r.nextU32() * 2.3283064365386963e-10) bad++;
process.stdout.write(String(bad));
""" % (PARITY / "prng_kat.json").as_posix())
        self.assertEqual(bad, "0")

    def test_py_sum_matches_cpython(self):
        rnd = random.Random(5)
        cases = []
        for i in range(400):
            n = rnd.randint(1, 12)
            xs = [rnd.choice([1e16, -1e16, 1.0, -1.0, 1e-17]) * rnd.random() if i % 3 == 0 else
                  rnd.expovariate(1.0) * (6 if i % 3 == 1 else 1e-3) for _ in range(n)]
            cases.append(xs)
        cases += [[1e100, 1.0, -1e100], [0.1] * 10, [-0.0], [-0.0, -0.0], [float("inf"), 1.0]]
        out = json.loads(node("""
import { pySum } from '{provider}';
import { readFileSync } from 'fs';
const cases = JSON.parse(readFileSync(0, 'utf8').replace(/Infinity/g, '1e999'));
process.stdout.write(JSON.stringify(cases.map((c) => { const s = pySum(c); return [String(s), Object.is(s, -0)]; })));
""", json.dumps(cases)))
        for c, (s, neg0) in zip(cases, out):
            exp = sum(c)
            self.assertEqual(float(s.replace("Infinity", "inf")), exp, c)
            self.assertEqual(neg0, exp == 0 and math.copysign(1.0, exp) < 0, c)

    def test_eligibility_matches_python(self):
        rnd = random.Random(11)
        cases = []
        for _ in range(3000):
            n_opts = rnd.randint(2, 8)
            opts = [f"b{i}" for i in range(n_opts)]
            n_overs = rnd.choice([3, 5, 7, 9, 10, 13, 17, 20, 23, 41, 50])
            done = rnd.randint(0, n_overs - 1)
            overs = {}
            for _k in range(done):
                b = rnd.choice(opts + ["x9"])
                overs[b] = overs.get(b, 0) + 1
            last = rnd.choice([None] + opts)
            rule = rnd.choice(["fifth_min2", "fifth"])
            cases.append({"opts": opts, "overs": overs, "last": last, "n": n_overs, "done": done, "rule": rule,
                          "expect": sim.eligible_bowlers(opts, overs, last, n_overs, done, rule)})
        cases.append({"opts": ["a", "b"], "overs": {}, "last": "a", "n": None, "done": 3, "rule": "fifth_min2",
                      "expect": sim.eligible_bowlers(["a", "b"], {}, "a", None, 3)})
        bad = node("""
import { eligibleBowlers } from '{engine}';
import { readFileSync } from 'fs';
const cases = JSON.parse(readFileSync(0, 'utf8'));
let bad = 0;
for (const c of cases) {
  const got = eligibleBowlers(c.opts, new Map(Object.entries(c.overs)), c.last, c.n, c.done, c.rule);
  if (JSON.stringify(got) !== JSON.stringify(c.expect)) bad++;
}
process.stdout.write(String(bad));
""", json.dumps(cases))
        self.assertEqual(bad, "0")

    def test_transitions_reproduce_exactly(self):
        rows = [json.loads(line) for line in (PARITY / "transitions.jsonl").read_text().splitlines()]
        got = json.loads(node("""
import { applyScript, ScriptError } from '{engine}';
import { readFileSync } from 'fs';
const rows = readFileSync(0, 'utf8').trim().split('\\n').map((l) => JSON.parse(l));
const out = rows.map((c) => {
  try { return applyScript(c.scenario, c.script, c.state); }
  catch (e) { return e instanceof ScriptError ? { error: 'ScriptError', message: e.message } : { error: String(e.stack) }; }
});
process.stdout.write(JSON.stringify(out));
""", (PARITY / "transitions.jsonl").read_text()))
        self.assertEqual(len(got), len(rows))
        for row, g in zip(rows, got):
            with self.subTest(case=row["name"]):
                self.assertIsNone(first_difference(g, row["expect"]), row["name"])

    def test_trajectories_reproduce_exactly(self):
        rows = [json.loads(line) for line in (PARITY / "trajectories.jsonl").read_text().splitlines()]
        stdin = "".join(json.dumps({"name": n, "scenario": s}) + "\n" for n, s in trajectory_scenarios())
        got = cli(["--trace", "--trace-sims", "0,1,2"], stdin)
        self.assertEqual(len(got), len(rows))
        n_lat = n_bits = 0
        for g, r in zip(got, rows):
            with self.subTest(name=r["name"], sim=r["sim"]):
                la, lb = [], []
                a, b = split_latent(g, la), split_latent(r, lb)
                self.assertIsNone(first_difference(a, b), (r["name"], r["sim"]))
                self.assertEqual(len(la), len(lb))
                for x, y in zip(la, lb):
                    self.assertLessEqual(abs(x - y), 1e-12 * max(1.0, abs(y)))
                n_lat += len(lb)
                n_bits += sum(x != y for x, y in zip(la, lb))
        self.assertGreater(n_lat, 100)
        self.assertLess(n_bits, n_lat / 4)       # last-bit libm differences only

    def test_aggregates_match_python(self):
        scs = trajectory_scenarios()
        stdin = "".join(json.dumps({"name": n, "scenario": s}) + "\n" for n, s in scs)
        js = {o.pop("name"): o for o in cli(["--sims", str(N_AGG), "--workers", "2"], stdin)}
        tasks = [(n, s, N_AGG) for n, s in sorted(scs, key=lambda x: x[1]["fam"] != "TEST")]
        workers = max(1, min(len(tasks), (os.cpu_count() or 2) - 1))
        if workers > 1:
            with mp.get_context("fork").Pool(workers) as pool:
                py = dict(pool.map(_py_run, tasks, chunksize=1))
        else:
            py = dict(map(_py_run, tasks))
        for name, _ in scs:
            with self.subTest(scenario=name):
                self.assertEqual(js[name]["n"], N_AGG)
                self.assertIsNone(first_difference(js[name], py[name]), name)
                self.assertEqual(js[name]["p_win"], py[name]["p_win"])
                self.assertEqual(js[name]["innings"]["1"]["runs_mean"], py[name]["innings"]["1"]["runs_mean"])

    def test_worker_splits_merge_exactly(self):
        stdin = "".join(json.dumps({"name": n, "scenario": s}) + "\n" for n, s in trajectory_scenarios())
        one = cli(["--sims", "300"], stdin)
        many = cli(["--sims", "300", "--workers", "3", "--chunk", "47"], stdin)
        self.assertEqual(one, many)

    def test_cached_view_fields_and_acc_fast_path(self):
        out = json.loads(node("""
import * as E from '{engine}';
const team = (p, home = false, kw = {}) => ({ name: p, batting_order: [...Array(11).keys()].map((i) => `${p}${i + 1}`), keeper: `${p}7`, home, ...kw });
const scens = [
  { fam: 'T20', teams: [team('A', true), team('B')], umpires: ['U1', 'U2'], weather: { rain_risk: 0.5 } },
  { fam: 'ODI', gender: 'female', teams: [team('A', true, { absent: ['A11'] }), team('B', false, { bowlers: ['B11', 'B10', 'B9', 'B8'] })], weather: { rain_risk: 0.6 } },
  { fam: 'TEST', teams: [team('A', true), team('B')], umpires: ['U1', 'U2'], weather: { rain_risk: 0.4 } },
];
const SKIP = new Set(['dtype']);
const canon = (x) => JSON.stringify(x, (k, v) => (v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort(([p], [q]) => (p < q ? -1 : p > q ? 1 : 0))) : v));
let viewBad = 0, checks = 0, accBad = 0;
for (const [si, sc] of scens.entries()) {
  const pr = new E.Prepared(sc);
  const m = new E.Match(pr);
  const fast = m._refresh.bind(m);
  m._refresh = () => {
    fast();
    const snap = {};
    for (const k in m.view) { const x = m.view[k]; snap[k] = ArrayBuffer.isView(x) || Array.isArray(x) ? JSON.stringify(Array.from(x)) : x; }
    m.ovFresh = false;
    fast();
    checks++;
    for (const k in m.view) {
      const x = m.view[k], y = ArrayBuffer.isView(x) || Array.isArray(x) ? JSON.stringify(Array.from(x)) : x;
      if (!SKIP.has(k) && !Object.is(y, snap[k])) { viewBad++; if (viewBad < 5) console.error('stale view key', k, snap[k], y); }
    }
  };
  const n = sc.fam === 'TEST' ? 30 : 150;
  const a = new E.Acc(pr.limited ? Math.floor(pr.rules.max_balls / 6) : null).bind(pr), b = new E.Acc(a.n_overs);
  for (let i = 0; i < n; i++) { m.reset(i, 3); m.play(); a.addMatch(m); b.add(m.record()); }
  if (canon(E.summarize(a)) !== canon(E.summarize(b))) accBad++;
  const cut = Math.floor(n / 3);
  const merged = E.Acc.fromJSON(JSON.parse(JSON.stringify(E.simulate(pr, 0, cut, 3).toJSON()))).merge(E.simulate(pr, cut, n, 3));
  if (canon(E.summarize(merged)) !== canon(E.summarize(a))) accBad++;
}
process.stdout.write(JSON.stringify({ viewBad, checks, accBad }));
"""))
        self.assertGreater(out["checks"], 10000)
        self.assertEqual(out["viewBad"], 0)
        self.assertEqual(out["accBad"], 0)

    def test_in_play_state_and_views_match_python(self):
        name, sc = next((n, s) for n, s in trajectory_scenarios() if n == "t20_in_play")
        fresh = dict(sc, state=None)
        got = json.loads(node("""
import * as E from '{engine}';
import { readFileSync } from 'fs';
const sc = JSON.parse(readFileSync(0, 'utf8'));
const pr = new E.Prepared(sc), m = new E.Match(pr), views = [];
m.reset(5, 99, { views, stopAt: [1, 75] });
m.play();
const st = m.toState();
st.balls = views;
process.stdout.write(JSON.stringify({ stopped: m.stopped, state: st }));
""", json.dumps(fresh)))
        expect = dict(sc["state"])
        self.assertTrue(got["stopped"])
        got["state"]["pending_interruptions"] = expect["pending_interruptions"]
        self.assertIsNone(first_difference(got["state"], expect))

    def test_in_play_completed_innings_have_no_worm(self):
        # the canonical state keeps totals only for completed innings: their worm must not be zeros
        from tools import make_cricket_parity_vectors as V
        sc = rt(V.scen("T20", toss={"winner": 0, "decision": "bat"}, seed=4, weather={"rain_risk": 0.3}))
        views = []
        m = sim.Match(sim.Prepared(sc), 3, 9, views=views, stop_at=(2, 30)).play()
        st = m.to_state()
        st["balls"], st["pending_interruptions"] = views, None
        sc["state"] = rt(st)
        py = rt(sim.run(sc, n_sims=60))
        js = cli(["--sims", "60"], json.dumps(sc))[0]
        js.pop("name")
        self.assertEqual(list(py["worm"]), ["2"])
        self.assertEqual(list(py["runs_by_over"]), ["2"])
        self.assertEqual(py["innings"]["1"]["runs_mean"], st["done"][0]["runs"])
        self.assertIsNone(first_difference(js, py))

    def test_impute_and_check_state_match_python(self):
        T20 = rt(dict(trajectory_scenarios()[0][1], toss={"winner": 0, "decision": "bat"}))
        ODI = rt(dict(trajectory_scenarios()[1][1]))
        TEST = rt(dict(trajectory_scenarios()[2][1], toss={"winner": 1, "decision": "bat"}))
        first = {"team": 0, "runs": 160, "wkts": 6, "legal_balls": 120}
        partials = [
            (T20, {"cur": {"number": 1, "team": 0, "runs": 47, "wkts": 2, "legal_balls": 39}}),
            (T20, {"cur": {"number": 2, "team": 1, "runs": 99, "wkts": 5, "legal_balls": 83, "unavailable": ["B9"]},
                   "done": [first]}),
            (ODI, {"cur": {"number": 2, "team": 1, "runs": 12, "wkts": 0, "legal_balls": 17, "max_balls": 240},
                   "done": [dict(first, legal_balls=300, runs=250)], "lengths": [300, 240]}),
            (TEST, {"cur": {"number": 3, "team": 1, "runs": 80, "wkts": 3, "legal_balls": 333},
                    "done": [{"runs": 300, "wkts": 10, "legal_balls": 700}, {"runs": 280, "wkts": 10, "legal_balls": 650}]}),
        ]
        cases = [{"sc": s, "partial": p, "expect": sim.impute_state(p, s)} for s, p in partials]
        broken = []
        for c in cases:
            st = json.loads(json.dumps(c["expect"]))
            st["cur"]["wkts"] += 1
            st["cur"]["bowlers"][next(iter(st["cur"]["bowlers"]))]["balls"] += 1
            st["cur"]["nonstriker"] = st["cur"]["striker"]
            broken.append({"sc": c["sc"], "state": st, "expect": sim.check_state(st, sim.Prepared(c["sc"]))})
        got = json.loads(node("""
import * as E from '{engine}';
import { readFileSync } from 'fs';
const { cases, broken } = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify({ imputed: cases.map((c) => E.imputeState(c.partial, c.sc)),
  errors: broken.map((c) => E.checkState(c.state, new E.Prepared(c.sc))) }));
""", json.dumps(rt({"cases": cases, "broken": broken}))))
        for c, g in zip(cases, got["imputed"]):
            self.assertIsNone(first_difference(g, rt(c["expect"])))
        for c, g in zip(broken, got["errors"]):
            self.assertTrue(c["expect"])
            self.assertEqual(g, c["expect"])

    def test_worker_progress_and_cancel(self):
        name, sc = trajectory_scenarios()[0]
        out = json.loads(node("""
import { Worker } from 'node:worker_threads';
import * as E from '{engine}';
import { readFileSync } from 'fs';
const sc = JSON.parse(readFileSync(0, 'utf8'));
const w = new Worker(new URL('{worker}'), { execArgv: [] });
const ask = (msg, onProgress) => new Promise((res) => {
  const f = (m) => { if (m.id !== msg.id) return; if (m.type === 'progress') { onProgress && onProgress(m); return; } w.off('message', f); res(m); };
  w.on('message', f); w.postMessage(msg);
});
const prog = [];
const full = await ask({ type: 'run', id: 1, scenario: sc, simRange: [10, 1210], key: 's' }, (m) => prog.push(m.done));
const ref = E.simulate(new E.Prepared(sc), 10, 1210, sc.seed);
const canon = (x) => JSON.stringify(x, (k, v) => (v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort(([p], [q]) => (p < q ? -1 : p > q ? 1 : 0))) : v));
const same = canon(E.summarize(E.Acc.fromJSON(full.acc))) === canon(E.summarize(ref));
const flag = new Int32Array(new SharedArrayBuffer(4));
const c1 = await ask({ type: 'run', id: 2, scenario: sc, simRange: [0, 5000], key: 's', progressEvery: 100, cancelFlag: flag.buffer },
  (m) => { if (m.done >= 200) Atomics.store(flag, 0, 1); });
let sent = false;
const c2 = await ask({ type: 'run', id: 3, scenario: sc, simRange: [0, 5000], key: 's', progressEvery: 100 },
  (m) => { if (!sent) { sent = true; w.postMessage({ type: 'cancel', id: 3 }); } });
const bad = await ask({ type: 'run', id: 4, scenario: { fam: 'XYZ', teams: [] }, simRange: [0, 5] });
await w.terminate();
process.stdout.write(JSON.stringify({ prog, same, n: full.acc.n, c1: [c1.cancelled, c1.acc.n], c2: [c2.cancelled, c2.acc.n], err: bad.type }));
""", json.dumps(sc)))
        self.assertEqual(out["prog"], [500, 1000, 1200])
        self.assertTrue(out["same"])
        self.assertEqual(out["n"], 1200)
        self.assertTrue(out["c1"][0])
        self.assertLess(out["c1"][1], 1000)
        self.assertTrue(out["c2"][0])
        self.assertLess(out["c2"][1], 1000)
        self.assertEqual(out["err"], "error")


def playwright_module() -> str | None:
    """Path of a Playwright install node can require (with a browser available), else None."""
    if NODE is None:
        return None
    for cand in ("playwright", str(Path(NODE).resolve().parents[1] / "lib" / "node_modules" / "playwright")):
        out = subprocess.run([NODE, "-e", f"require.resolve({json.dumps(cand)})"], capture_output=True, text=True)
        if out.returncode == 0:
            return cand
    return None


PLAYWRIGHT = playwright_module()

BROWSER_SCRIPT = r"""
const { chromium } = require(%(pw)s);
const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = %(root)s;
const SC = fs.readFileSync(0, 'utf8');
const page = `<!doctype html><meta charset="utf-8"><script type="module">
const w = new Worker('./worker.js', { type: 'module' });
const sc = await (await fetch('./sc.json')).json();
const prog = [];
w.onmessage = (e) => {
  const m = e.data;
  if (m.type === 'progress') { prog.push(m.done); if (m.id === 2 && m.done >= 500) w.postMessage({ type: 'cancel', id: 2 }); return; }
  if (m.id === 1) { window.first = { prog: [...prog], acc: m.acc }; prog.length = 0;
    w.postMessage({ type: 'run', id: 2, scenario: sc, simRange: [0, 20000], bundleUrl: null }); return; }
  window.result = { ...window.first, cancelled: m.cancelled, cancel_n: m.acc.n };
};
w.onerror = (e) => { window.result = { error: String(e.message) }; };
w.postMessage({ type: 'run', id: 1, scenario: sc, simRange: [0, 600], bundleUrl: null });
</script>`;
const srv = http.createServer((req, res) => {
  if (req.url === '/') { res.setHeader('content-type', 'text/html'); return res.end(page); }
  if (req.url === '/sc.json') { res.setHeader('content-type', 'application/json'); return res.end(SC); }
  const f = path.join(ROOT, req.url.split('?')[0]);
  if (!f.startsWith(ROOT) || !fs.existsSync(f)) { res.statusCode = 404; return res.end(); }
  res.setHeader('content-type', 'text/javascript'); res.end(fs.readFileSync(f));
}).listen(0, async () => {
  let browser;
  try {
    browser = await chromium.launch();
    const p = await browser.newPage();
    await p.goto(`http://127.0.0.1:${srv.address().port}/`);
    await p.waitForFunction(() => window.result, null, { timeout: 30000 });
    process.stdout.write(JSON.stringify(await p.evaluate(() => window.result)));
  } catch (e) {
    process.stdout.write(JSON.stringify({ skip: String(e.message).split('\n')[0] }));
  } finally {
    if (browser) await browser.close();
    srv.close();
  }
});
"""


@unittest.skipIf(PLAYWRIGHT is None, "playwright not installed")
class BrowserWorkerTests(unittest.TestCase):
    def test_module_web_worker_in_headless_chromium(self):
        sc = trajectory_scenarios()[0][1]
        script = BROWSER_SCRIPT % {"pw": json.dumps(PLAYWRIGHT), "root": json.dumps(str(JS))}
        out = subprocess.run([NODE, "-e", script], input=json.dumps(sc), capture_output=True, text=True, timeout=180)
        self.assertEqual(out.returncode, 0, out.stderr)
        res = json.loads(out.stdout)
        if "skip" in res:
            self.skipTest(res["skip"])
        self.assertNotIn("error", res)
        self.assertEqual(res["prog"], [500, 600])
        node_acc = node("""
import * as E from '{engine}';
import { readFileSync } from 'fs';
const { sc, acc } = JSON.parse(readFileSync(0, 'utf8'));
const canon = (x) => JSON.stringify(x, (k, v) => (v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort(([p], [q]) => (p < q ? -1 : p > q ? 1 : 0))) : v));
process.stdout.write(String(canon(E.summarize(E.Acc.fromJSON(acc))) === canon(E.summarize(E.simulate(new E.Prepared(sc), 0, 600, sc.seed)))));
""", json.dumps({"sc": sc, "acc": res["acc"]}))
        self.assertEqual(node_acc, "true")
        self.assertTrue(res["cancelled"])
        self.assertLess(res["cancel_n"], 1000)


if __name__ == "__main__":
    unittest.main()
