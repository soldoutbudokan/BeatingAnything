// Simulation worker for the cricket engine: a browser Web Worker (new Worker(url, {type: 'module'})) and a
// Node worker_threads worker (cli.js --workers) from the same file.
//
// Protocol. In: {type: 'run', id, scenario, simRange: [a, b], bundleUrl | bundle, seed?, key?,
// progressEvery = 500, cancelFlag?: SharedArrayBuffer, logSims?: [sim...]} and {type: 'cancel', id}.
// Out: {type: 'progress', id, done, total} every progressEvery sims; {type: 'result', id, acc, simRange,
// cancelled, part_timers_added, elapsed_s, logs?} where acc is Acc.toJSON() (integer sufficient statistics:
// Acc.fromJSON(...).merge(...) over any split of the sim range is exact, then engine.summarize); and
// {type: 'error', id, message}. A null bundleUrl and bundle use the StubProvider. Sims are independent of
// how the range is split because every (seed, sim) has its own random streams.
//
// Cancellation is checked between sims: through cancelFlag (Int32 slot 0 set non-zero with Atomics.store)
// at every sim, and through 'cancel' messages, which are read when the worker yields to its event loop
// every checkEvery sims (default 25; SharedArrayBuffer needs cross-origin isolation in browsers, messages
// do not). Prepared scenarios are cached by `key` so repeated ranges skip preparation (and the in-play
// latent posterior).

import { Prepared, Match, Acc, simulate } from './engine.js';
import { createProvider } from './provider.js';

const isNode = typeof self === 'undefined' || typeof self.postMessage !== 'function';
let post, onMessage;
if (isNode) {
  const { parentPort } = await import('node:worker_threads');
  post = (m) => parentPort.postMessage(m);
  onMessage = (f) => parentPort.on('message', f);
} else {
  post = (m) => self.postMessage(m);
  onMessage = (f) => { self.onmessage = (e) => f(e.data); };
}

const yieldNow = isNode ? () => new Promise((r) => setImmediate(r)) : (() => {
  const ch = new MessageChannel(), q = [];
  ch.port1.onmessage = () => q.shift()();
  return () => new Promise((r) => { q.push(r); ch.port2.postMessage(0); });
})();

const providers = new Map(), prepared = new Map(), cancelled = new Set();

async function loadBundle(url) {
  if (isNode) {
    const fs = await import('node:fs/promises');
    return JSON.parse(await fs.readFile(url.startsWith('file:') ? new URL(url) : url, 'utf8'));
  }
  const r = await fetch(url);
  if (!r.ok) throw new Error(`bundle ${url}: HTTP ${r.status}`);
  return r.json();
}

async function getProvider(msg) {
  if (msg.bundle !== undefined) return createProvider(msg.bundle);
  const url = msg.bundleUrl || '';
  if (!providers.has(url)) providers.set(url, createProvider(url ? await loadBundle(url) : null));
  return providers.get(url);
}

async function getPrepared(msg) {
  const P = await getProvider(msg);
  const key = msg.key === undefined || msg.key === null ? null : `${msg.bundleUrl || ''}\u0000${msg.key}`;
  if (key !== null && prepared.has(key)) return prepared.get(key);
  const pr = new Prepared(msg.scenario, P);
  if (key !== null) {
    if (prepared.size >= 8) prepared.delete(prepared.keys().next().value);
    prepared.set(key, pr);
  }
  return pr;
}

async function run(msg) {
  const t0 = Date.now();
  const { id } = msg;
  const [a, b] = msg.simRange;
  const every = Math.max(1, msg.progressEvery || 500);
  const pr = await getPrepared(msg);
  const seed = msg.seed === undefined || msg.seed === null ? pr.sc.seed : msg.seed;
  const flag = msg.cancelFlag ? new Int32Array(msg.cancelFlag) : null;
  const isCancelled = () => cancelled.has(id) || (flag !== null && Atomics.load(flag, 0) !== 0);
  const logs = msg.logSims && msg.logSims.length ? new Map(msg.logSims.map((i) => [i, null])) : null;
  const sub = Math.max(1, Math.min(every, msg.checkEvery || 25));
  const match = new Match(pr);
  const acc = new Acc(pr.limited ? Math.floor(pr.rules.max_balls / 6) : null).bind(pr);
  let i = a, stop = false, nextProgress = a + every;
  while (i < b) {
    const j = Math.min(b, i + sub, nextProgress);
    simulate(pr, i, j, seed, { match, logs, acc, cancelled: flag !== null ? isCancelled : null });
    i = a + acc.n;
    if (acc.cancelled) { stop = true; break; }
    if (i >= nextProgress || i === b) {
      post({ type: 'progress', id, done: i - a, total: b - a });
      nextProgress += every;
    }
    await yieldNow();
    if (isCancelled()) { stop = true; break; }
  }
  acc.fold();
  cancelled.delete(id);
  const out = { type: 'result', id, acc: acc.toJSON(), simRange: [a, i], cancelled: stop && i < b,
    part_timers_added: pr.part_timer_report, elapsed_s: (Date.now() - t0) / 1000 };
  if (logs !== null) out.logs = Object.fromEntries([...logs].filter(([, l]) => l !== null));
  post(out);
}

onMessage((msg) => {
  if (msg.type === 'cancel') { cancelled.add(msg.id); return; }
  if (msg.type === 'run') {
    run(msg).catch((e) => post({ type: 'error', id: msg.id, message: String(e && e.stack ? e.stack : e) }));
  }
});
