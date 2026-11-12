/* IPL workbook: shared data access, distributions, match model and renderers (window.IPL).
   sheets.js builds the workbook on top of this. Exports are read defensively: optional fields added by later
   model passes (exact pmfs, per-team matchup files, 2026 lines) are used when present, with labelled fallbacks. */
(function () {
'use strict';
const S = Sheets, h = S.h, esc = S.esc, F = S.fmt;
const I = window.IPL = {};
const isNum = v => typeof v === 'number' && isFinite(v);
I.isNum = isNum;
I.PH = ['pp', 'mid', 'death'];
I.PH_LABEL = { pp: 'Powerplay', mid: 'Middle', death: 'Death' };
I.PH_OVERS = { pp: 'overs 1–6', mid: 'overs 7–15', death: 'overs 16–20' };
I.ROLE_LABEL = { open: 'Opener', top: 'Top order', middle: 'Middle order', lower: 'Lower order' };
I.TIER_LABEL = { ipl: 'IPL', intl: 'T20 internationals', top_fr: 'Top franchise leagues', fr2: 'Other franchise leagues', india_dom: 'Indian domestic', dom: 'Other domestic', assoc: 'Associate T20Is' };

/* ════════ odds mode (American default, decimal toggle) ════════ */
let oddsMode = 'american';
try { const m = localStorage.getItem('ipl.odds'); if (m === 'decimal' || m === 'american') oddsMode = m; } catch (e) { /* storage blocked */ }
const oddsViews = [];
I.odds = {
  get mode() { return oddsMode; },
  set(m) {
    if (m === oddsMode) return;
    oddsMode = m; try { localStorage.setItem('ipl.odds', m); } catch (e) { /* ignore */ }
    for (let i = oddsViews.length - 1; i >= 0; i--) {
      const v = oddsViews[i];
      if (!v.el.isConnected) { oddsViews.splice(i, 1); continue; }
      try { v.fn(m); } catch (e) { console.error(e); }
    }
  },
  bind(el, fn) { oddsViews.push({ el, fn }); },
};
I.fp = p => !(p > 0 && p < 1) ? '–' : oddsMode === 'decimal' ? F.dec(p, 2) : F.american(p);

/* ════════ data ════════ */
const D = I.D = { pById: null, names: new Map() };
const slug = s => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
I.loadTeams = () => I._t || (I._t = S.load('data/teams.json').then(T => {
  D.season = T.season;
  D.teams = (T.teams || []).slice().sort((a, b) => String(a.short).localeCompare(String(b.short)));
  D.tByShort = new Map(D.teams.map(t => [t.short, t]));
  D.tByName = new Map(D.teams.map(t => [t.name, t]));
  D.squadOf = new Map();
  D.teams.forEach(t => (t.squad || []).forEach(s => { if (!D.names.has(s.id)) D.names.set(s.id, s.name); if (!D.squadOf.has(s.id)) D.squadOf.set(s.id, { team: t, s }); }));
  return D;
}));
I.team = k => k == null ? null : D.tByShort.get(k) || D.tByName.get(k) || D.tByShort.get(String(k).toUpperCase()) || null;
I.short = k => { const t = I.team(k); return t ? t.short : (k ? String(k) : '—'); };
I.pname = id => (D.pById && D.pById.get(id) && D.pById.get(id).name) || D.names.get(id) || id;
I.player = id => (D.pById && D.pById.get(id)) || null;
I.loadPlayers = () => I._p || (I._p = Promise.all([S.load('data/players.json'), I.loadTeams()]).then(([P]) => {
  D.P = P;
  D.players = (P.players || []).slice();
  D.pById = new Map(D.players.map(p => [p.id, p]));
  D.players.forEach(p => { D.names.set(p.id, p.name); });
  D.avgBat = P.avg_bat || {}; D.avgBowl = P.avg_bowl || {};
  D.settlingAvg = P.settling_avg || []; D.settlingBuckets = P.settling_buckets || [];
  D.replacement = P.replacement || {}; D.slotBalls = P.slot_balls || [];
  // ranks among percentile-qualified players (bat.pct / bowl.pct present)
  const rk = (list, f) => { list.sort((a, b) => f(b) - f(a)).forEach((p, i) => f(p) != null && (p['_rk_' + f.k] = i + 1)); return list.length; };
  const fb = p => p.bat && p.bat.value ? p.bat.value.varp_runs : null; fb.k = 'bat';
  const fw = p => p.bowl && p.bowl.value ? p.bowl.value.varp_runs : null; fw.k = 'bowl';
  const ft = p => p.varp_runs; ft.k = 'all';
  D.nBat = rk(D.players.filter(p => isNum(fb(p))), fb);
  D.nBowl = rk(D.players.filter(p => isNum(fw(p))), fw);
  D.nAll = rk(D.players.filter(p => isNum(ft(p))), ft);
  D.players.forEach(p => {
    p._team = p.team ? I.team(p.team) : null;
    p._last = lastPlayed(p);
    p._act = actualLine(p);
    p._projP = projLineFromPlayer(p);
  });
  return D;
}));
function lastPlayed(p) {
  if (p.last_played) return p.last_played;
  const sq = D.squadOf.get(p.id);
  if (sq && sq.s.last_app) return sq.s.last_app;
  for (const k of ['last_match', 'last_played', 'last_app', 'last_date']) if (p[k]) return String(p[k]);
  const yrs = (p.ipl_teams || []).map(t => t.to).filter(isNum);
  return yrs.length ? 'IPL ' + Math.max(...yrs) : null;
}
/* per-match lines a later export may add: actual IPL 2026 and projected per match */
const LINE_KEYS = {
  m: ['m', 'matches', 'inns', 'innings', 'gp'], runs: ['runs', 'runs_pm', 'runs_per_match', 'runs_mean'], balls: ['balls', 'balls_pm', 'balls_mean'],
  fours: ['fours', '4s', 'fours_pm', 'fours_mean'], sixes: ['sixes', '6s', 'sixes_pm', 'sixes_mean'], sr: ['sr', 'strike_rate'], avg: ['avg', 'average'],
  overs: ['overs', 'overs_pm', 'overs_mean'], wkts: ['wkts', 'wickets', 'wkts_pm', 'wkts_mean'], conc: ['conc', 'conceded', 'runs_conceded', 'conceded_mean'], econ: ['econ', 'economy'],
};
function readLine(o) {
  if (!o || typeof o !== 'object') return null;
  const out = {}; let any = false;
  for (const k in LINE_KEYS) for (const a of LINE_KEYS[k]) { let v = o[a]; if (v && typeof v === 'object' && !Array.isArray(v)) v = v.mean ?? v.value; if (isNum(v)) { out[k] = v; any = true; break; } }
  return any ? out : null;
}
function actualLine(p) {
  const L = p.ipl_last_season;
  if (L && typeof L === 'object') {
    const m = L.matches || null, o = { src: 'ipl_last_season', season: L.season, m, bat_inns: L.bat_inns, bowl_inns: L.bowl_inns };
    if (isNum(L.runs)) Object.assign(o, { runs_tot: L.runs, runs: m ? L.runs / m : null, runs_inn: L.bat_inns ? L.runs / L.bat_inns : null, balls: m && isNum(L.balls) ? L.balls / m : null, sr: L.sr, avg: L.avg });
    if (isNum(L.wkts)) Object.assign(o, { wkts_tot: L.wkts, wkts: m ? L.wkts / m : null, overs_tot: L.overs, overs: m && isNum(L.overs) ? L.overs / m : null, conc: m && isNum(L.conceded) ? L.conceded / m : null, econ: L.econ });
    return o;
  }
  for (const k of Object.keys(p)) if (/^(actual|act|obs)_?(ipl_?)?2026|^ipl_?2026(_actual|_line)?$|^line_2026|^season_2026/i.test(k)) { const l = readLine(p[k]); if (l) return Object.assign(l, { src: k }); }
  return null;
}
function projLineFromPlayer(p) {
  for (const k of Object.keys(p)) if (/^(proj|projected)_?(line|per_match|pm|match)|^line_proj/i.test(k)) { const l = readLine(p[k]); if (l) return Object.assign(l, { src: k }); }
  return null;
}
I.loadVenues = () => I._v || (I._v = S.load('data/venues.json').then(V => {
  D.V = V; D.venues = V.venues || []; D.vById = new Map(D.venues.map(v => [v.venue, v]));
  return V;
}));
I.venueName = id => { if (!id || id === 'neutral') return 'neutral ground'; const v = D.vById && D.vById.get(id); return v ? v.name : id.replace(/\b\w/g, c => c.toUpperCase()); };
I.loadSimParams = () => I._sp || (I._sp = S.load('data/sim_params.json'));
I.loadDiag = () => S.load('data/diagnostics.json');
I.loadLeagues = () => S.load('data/leagues.json');
I.loadMeta = () => S.load.optional('data/meta.json');
I.loadMatchups = () => I._m || (I._m = Promise.all([S.load('data/matchups.json'), I.loadTeams()]).then(([M]) => {
  D.M = M;
  // mean per-match projection for every player over his team's matchups (home and away rows)
  const acc = new Map();
  for (const r of M.matchups || []) for (const s of ['A_stats', 'B_stats']) {
    const pl = (r[s] && r[s].players) || {};
    for (const id in pl) {
      const x = pl[id]; let a = acc.get(id); if (!a) acc.set(id, a = { n: 0, s: {}, pr: {}, pw: {} });
      a.n++;
      ['runs_mean', 'balls_mean', 'fours_mean', 'sixes_mean', 'p_bat', 'p_out', 'p_top_bat', 'overs_mean', 'wkts_mean', 'conceded_mean', 'p_top_bowl'].forEach(k => { if (isNum(x[k])) a.s[k] = (a.s[k] || 0) + x[k]; });
      for (const t in x.p_runs || {}) a.pr[t] = (a.pr[t] || 0) + x.p_runs[t];
      for (const t in x.p_wkts || {}) a.pw[t] = (a.pw[t] || 0) + x.p_wkts[t];
      if (x.bat_pos != null) a.pos = x.bat_pos;
    }
  }
  D.proj = new Map();
  for (const [id, a] of acc) {
    const o = { n: a.n, pos: a.pos ?? null, pRuns: {}, pWkts: {} };
    for (const k in a.s) o[k] = a.s[k] / a.n;
    for (const t in a.pr) o.pRuns[t] = a.pr[t] / a.n;
    for (const t in a.pw) o.pWkts[t] = a.pw[t] / a.n;
    D.proj.set(id, o);
  }
  return M;
}));
/** projected per-match line: players.json proj_match (round 2) merged over the matchups.json means */
I.proj = id => {
  const m = D.proj && D.proj.get(id), p = D.pById && D.pById.get(id), pm = p && p.proj_match;
  if (!pm) return m || null;
  const o = Object.assign({ pRuns: {}, pWkts: {} }, m || {});
  o.pRuns = Object.assign({}, o.pRuns); if (isNum(pm.p30)) o.pRuns['30'] = pm.p30; if (isNum(pm.p50)) o.pRuns['50'] = pm.p50;
  Object.assign(o, { n: pm.matchups ?? o.n, pos: pm.bat_pos ?? o.pos ?? null, src: 'proj_match' });
  [['runs', 'runs_mean'], ['balls', 'balls_mean'], ['fours', 'fours_mean'], ['sixes', 'sixes_mean'], ['overs', 'overs_mean'], ['wkts', 'wkts_mean'], ['conceded', 'conceded_mean']].forEach(([k, t]) => { if (isNum(pm[k])) o[t] = pm[k]; else if (pm[k] === null && !m) delete o[t]; });
  if (isNum(pm.econ)) o.econ = pm.econ;
  return o;
};

/* ════════ distributions ════════ */
function erf(x) { const t = 1 / (1 + 0.3275911 * Math.abs(x)); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y; }
const Phi = z => 0.5 * (1 + erf(z / Math.SQRT2));
I.Phi = Phi;
/** monotone cubic (Fritsch–Carlson) through increasing xs */
function pchip(xs, ys) {
  const n = xs.length, d = [], m = new Array(n).fill(0);
  for (let i = 0; i < n - 1; i++) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
  m[0] = d[0]; m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
    const a = m[i] / d[i], b = m[i + 1] / d[i], s = a * a + b * b;
    if (s > 9) { const t = 3 / Math.sqrt(s); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
  }
  return x => {
    if (x <= xs[0]) return ys[0]; if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0; while (x > xs[i + 1]) i++;
    const hh = xs[i + 1] - xs[i], t = (x - xs[i]) / hh, t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * hh * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * hh * m[i + 1];
  };
}
const pmfDist = arr => { let s = 0; for (const v of arr) s += v; return s > 0 ? S.dist.fromPmf(arr.map((p, k) => [k, p])) : S.dist.fromPmf([[0, 1]]); };
/** smooth integer pmf through simulated quantiles (5/25/50/75/95 or 10/…/90), normal-shaped tails */
function quantDist(q, ps, sd, lo = 0) {
  const xs = [], ys = [];
  q.forEach((v, i) => { let x = v + i * 1e-3; if (xs.length && x <= xs[xs.length - 1]) x = xs[xs.length - 1] + 0.05; xs.push(x); ys.push(ps[i]); });
  const zL = 1.645, gl = Math.max((xs[1] - xs[0]) / Math.max(0.3, (-0.674 + zL)), (sd || 1) * 0.4, 0.5), gu = Math.max((xs[xs.length - 1] - xs[xs.length - 2]) / 0.97, (sd || 1) * 0.4, 0.5);
  const x0 = xs[0] - gl * 2.4, x1 = xs[xs.length - 1] + gu * 2.4;
  const X = [x0].concat(xs, [x1]), Y = [0].concat(ys, [1]);
  if (ps[0] > 0.05) { /* 10th pct first: add a 5% anchor by the tail scale */ }
  const f = pchip(X, Y), K0 = Math.max(lo, Math.floor(x0)), K1 = Math.ceil(x1);
  const out = []; let prev = Math.max(0, Math.min(1, f(K0 - 0.5)));
  for (let k = K0; k <= K1; k++) { const c = Math.max(prev, Math.min(1, f(k + 0.5))); out.push([k, (k === K0 ? c : c - prev)]); prev = c; }
  return S.dist.fromPmf(out);
}
/** CDF array -> pmf that passes exactly through anchors {k, T = P(X <= k)} and follows F0's shape between them */
function anchored(F0, anchors) {
  const K = F0.length - 1;
  let A = anchors.filter(a => a.k >= 0 && a.k <= K && isNum(a.T)).sort((a, b) => a.k - b.k);
  let mx = 0; A = A.filter((a, i) => { if (i && a.k === A[i - 1].k) return false; a.T = Math.min(1, Math.max(mx, a.T)); mx = a.T; return true; });
  const Fx = new Float64Array(K + 1);
  if (!A.length) Fx.set(F0);
  else {
    const first = A[0], last = A[A.length - 1]; let i = 0;
    for (let k = 0; k <= K; k++) {
      if (k <= first.k) Fx[k] = F0[first.k] > 1e-12 ? F0[k] * first.T / F0[first.k] : first.T * (k + 1) / (first.k + 1);
      else if (k >= last.k) { const rem = 1 - F0[last.k]; Fx[k] = rem > 1e-12 ? 1 - (1 - F0[k]) * (1 - last.T) / rem : 1; }
      else { while (A[i + 1].k < k) i++; const a = A[i], b = A[i + 1], dd = F0[b.k] - F0[a.k]; Fx[k] = a.T + (dd > 1e-12 ? (F0[k] - F0[a.k]) / dd : (k - a.k) / (b.k - a.k)) * (b.T - a.T); }
    }
  }
  Fx[K] = 1;
  const pmf = []; let prev = 0;
  for (let k = 0; k <= K; k++) { const v = Math.max(prev, Math.min(1, Fx[k])); pmf.push(v - prev); prev = v; }
  return pmf;
}
const cdfOf = pmf => { const c = new Float64Array(pmf.length); let s = 0; pmf.forEach((p, i) => { s += p; c[i] = s; }); for (let i = 0; i < c.length; i++) c[i] /= s || 1; return c; };
/** zero-inflated negative binomial on 0..K: P(play) = pb, conditional mean mc, variance mc*phi + mc²*psi */
function zinb(mean, pb, phi = 1.5, psi = 0, K = 200) {
  pb = Math.max(1e-6, Math.min(1, pb || 1)); const mc = Math.max(1e-6, mean / pb); const v = mc * phi + mc * mc * psi;
  const P = new Array(K + 1).fill(0);
  if (v > mc * 1.0001) { const r = mc * mc / (v - mc), q = r / (r + mc); let p = Math.exp(r * Math.log(q)); P[0] = p; for (let k = 0; k < K; k++) { p = p * (k + r) / (k + 1) * (1 - q); P[k + 1] = p; } }
  else { let p = Math.exp(-mc); P[0] = p; for (let k = 0; k < K; k++) { p = p * mc / (k + 1); P[k + 1] = p; } }
  return P.map((p, k) => p * pb + (k === 0 ? 1 - pb : 0));
}
/** player-innings runs from matchups.json: zero-inflated geometric shape anchored on the simulated P(runs ≥ t) */
function runsApprox(x) {
  const pb = Math.max(1e-6, x.p_bat ?? 1), K = 220;
  const d0 = Math.min(0.9, (x.p_duck || 0) / pb + 0.02), mc = (x.runs_mean || 0) / pb, mpos = Math.max(1.05, mc / Math.max(0.05, 1 - d0));
  const base = new Array(K + 1).fill(0), g = 1 / mpos;
  base[0] = (1 - pb) + pb * d0;
  for (let k = 1; k <= K; k++) base[k] = pb * (1 - d0) * g * Math.pow(1 - g, k - 1);
  const anchors = Object.entries(x.p_runs || {}).map(([t, p]) => ({ k: +t - 1, T: 1 - p })).filter(a => isNum(a.T));
  return S.dist.fromPmf(anchored(cdfOf(base), anchors).map((p, k) => [k, p]));
}
/* exported exact pmfs (later model passes): accept several shapes */
function toDist(x) {
  if (x == null) return null;
  if (x.pOver) return x;
  let rows = null;
  if (Array.isArray(x)) {
    if (x.length && Array.isArray(x[0])) rows = x;                                     // [[x, p], …]
    else if (x.length === 2 && isNum(x[0]) && Array.isArray(x[1])) rows = x[1].map((p, i) => [x[0] + i, p]);   // [lo, [p…]]
    else if (x.length && typeof x[0] === 'object') rows = x.map(r => [r.x ?? r.v ?? r.value, r.p ?? r.prob]);
    else if (x.every(isNum)) rows = x.map((p, i) => [i, p]);                           // [p0, p1, …]
  } else if (typeof x === 'object') {
    const p = x.p || x.pmf || x.probs || x.prob, v = x.x || x.v || x.values;
    if (Array.isArray(p) && Array.isArray(v)) rows = p.map((q, i) => [v[i], q]);
    else if (Array.isArray(p)) rows = p.map((q, i) => [(x.o ?? x.lo ?? x.min ?? x.offset ?? 0) + i, q]);
    else if (Array.isArray(x.counts)) rows = x.counts.map((q, i) => [(x.lo ?? 0) + i, q]);
    else { const e = Object.entries(x).filter(([k, v]) => /^-?\d+$/.test(k) && isNum(v)); if (e.length) rows = e.map(([k, v]) => [+k, v]); }
  }
  if (!rows || !rows.length) return null;
  const d = S.dist.fromPmf(rows.filter(r => isNum(+r[0]) && isNum(+r[1])).map(r => [+r[0], +r[1]]));
  return d.n ? d : null;
}
function pmfOf(o, names) {
  if (!o) return null;
  for (const n of names) {
    for (const k of [n + '_pmf', n + '_hist', n + '_dist', 'pmf_' + n]) if (o[k] != null) { const d = toDist(o[k]); if (d) return d; }
    for (const g of ['pmf', 'pmfs', 'hist', 'dist']) if (o[g] && o[g][n] != null) { const d = toDist(o[g][n]); if (d) return d; }
  }
  return null;
}
I.toDist = toDist;

/** Stat = {mean, sd, q:{p:v}, dist (lazy), exact, note} */
function mkStat(o) {
  const st = { mean: o.mean, sd: o.sd, q: o.q || {}, exact: !!o.exact, src: o.src || '', note: o.note || '' };
  let d = o.dist || null; const make = o.make;
  Object.defineProperty(st, 'dist', { get() { return d || (d = make ? make() : null); }, set(v) { d = v; }, enumerable: false });
  return st;
}
const QP5 = [0.05, 0.25, 0.5, 0.75, 0.95], QP10 = [0.1, 0.25, 0.5, 0.75, 0.9];
const qObj = (q, ps) => { const o = {}; (q || []).forEach((v, i) => { o[ps[i]] = v; }); return o; };
function statFromDist(d, src) {
  const q = {}; [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95].forEach(p => { q[p] = d.quantile(p); });
  return mkStat({ mean: d.mean, sd: d.sd, q, dist: d, exact: true, src });
}
function statQ(mean, sd, qv, ps, exported, note, lo) {
  if (exported) return statFromDist(exported, 'export');
  return mkStat({ mean, sd, q: qObj(qv, ps), exact: false, src: 'approx', note, make: () => Array.isArray(qv) && qv.length >= 3 ? quantDist(qv, ps, sd, lo) : I.normalDist(mean, sd || Math.sqrt(Math.max(mean, 1))) });
}
I.normalDist = (mean, sd, lo, hi) => {
  lo = lo ?? Math.max(0, Math.floor(mean - 6 * sd)); hi = hi ?? Math.ceil(mean + 6 * sd);
  const rows = []; for (let k = lo; k <= hi; k++) rows.push([k, Phi((k + 0.5 - mean) / sd) - Phi((k - 0.5 - mean) / sd)]);
  return S.dist.fromPmf(rows);
};
I.statFromDist = statFromDist;

/* ════════ matches ════════ */
/** default team spec (for sim.js) */
I.defTeam = t => ({ name: t.name, order: t.order.slice(0, 11), plan: t.plan.map(x => Object.assign({}, x)), schedule: (t.schedule || []).slice(), ip: t.impact_player });
I.venueKey = (vk, a, b) => vk === 'n' ? 'neutral' : vk === 'B' ? b.home_venue : vk === 'A' || !vk ? a.home_venue : vk;
const APPROX_T = 'Approximate shape: a smooth curve through the simulated 5th/25th/50th/75th/95th percentiles (matchups.json carries no full distribution).';
function preSide(ts, t, row, sideKey) {
  const side = {
    team: t,
    total: statQ(ts.total_mean, ts.total_sd, ts.total_q, QP5, pmfOf(ts, ['total', 'runs']), APPROX_T),
    pp: statQ(ts.pp_mean, null, ts.pp_q, QP5, pmfOf(ts, ['pp', 'powerplay']), APPROX_T),
    fow1: statQ(ts.fow1_mean, null, ts.fow1_q, QP5, pmfOf(ts, ['fow1']), APPROX_T),
    fours: statQ(ts.fours_mean, null, ts.fours_q, QP5, pmfOf(ts, ['fours']), APPROX_T),
    sixes: statQ(ts.sixes_mean, null, ts.sixes_q, QP5, pmfOf(ts, ['sixes']), APPROX_T),
    wkts: mkStat({ mean: ts.wkts_mean, exact: false }), wides: ts.wides_mean, extras: ts.extras_mean,
    bat1: ts.bat1_total_mean, bat2: ts.bat2_total_mean, pWinBat1: ts.p_win_bat1, pWinBat2: ts.p_win_bat2,
    players: [],
  };
  const pl = ts.players || {};
  const ids = [...new Set(t.order.concat(t.impact_player ? [t.impact_player] : [], t.plan.map(x => x.id), Object.keys(pl)))].filter(id => pl[id]);
  ids.forEach(id => {
    const x = pl[id], o = { id, name: I.pname(id), pos: x.bat_pos ?? null };
    if (x.bat_pos != null && isNum(x.runs_mean)) {
      const pb = x.p_bat ?? 1, note = 'Approximate: a zero-inflated shape matched to the simulated mean and anchored exactly on the simulated P(runs ≥ 10, 20, 30, 40, 50, 75, 100).';
      Object.assign(o, { pBat: pb, pOut: x.p_out, pDuck: x.p_duck, pTop: x.p_top_bat, pRuns: x.p_runs || {} });
      const ex = pmfOf(x, ['runs']);
      o.runs = ex ? statFromDist(ex, 'export') : mkStat({ mean: x.runs_mean, q: qObj(x.runs_q, QP10), exact: false, src: 'approx', note, make: () => runsApprox(x) });
      const cnt = (k, mean, phi, psi, K, label) => { const e = pmfOf(x, [k]); return e ? statFromDist(e, 'export') : mkStat({ mean, exact: false, src: 'approx', note: `Approximate: matchups.json gives only the mean ${label}; shape is a zero-inflated negative binomial (no-bat probability ${F.pct(1 - pb, 0)}).`, make: () => S.dist.fromPmf(zinb(mean || 0, pb, phi, psi, K).map((p, k2) => [k2, p])) }); };
      o.balls = cnt('balls', x.balls_mean, 1.2, 0.8, 120, 'balls faced');
      o.fours = cnt('fours', x.fours_mean, 1.6, 0.05, 30, 'fours');
      o.sixes = cnt('sixes', x.sixes_mean, 1.6, 0.05, 25, 'sixes');
    }
    if (isNum(x.overs_mean)) {
      const pw = x.p_wkts || {}, ex = pmfOf(x, ['wkts', 'wickets']);
      let wd = ex;
      if (!wd && Object.keys(pw).length) { const ks = [1, 2, 3, 4, 5].map(k => pw[k] ?? 0); wd = S.dist.fromPmf([[0, 1 - ks[0]], [1, ks[0] - ks[1]], [2, ks[1] - ks[2]], [3, ks[2] - ks[3]], [4, ks[3] - ks[4]], [5, ks[4]]].map(r => [r[0], Math.max(0, r[1])])); }
      const ce = pmfOf(x, ['conceded', 'runs_conceded', 'conc']);
      o.bowl = {
        overs: x.overs_mean, econ: x.econ, pTop: x.p_top_bowl, pW: pw,
        wkts: wd ? Object.assign(statFromDist(wd, ex ? 'export' : 'p_wkts'), { mean: x.wkts_mean, note: ex ? '' : 'From the simulated P(wickets ≥ 1…5); 5+ is lumped at 5.' }) : mkStat({ mean: x.wkts_mean }),
        conceded: ce ? statFromDist(ce, 'export') : mkStat({ mean: x.conceded_mean, exact: false, src: 'approx', note: 'Approximate: matchups.json gives only the mean runs conceded; shape is normal with SD ≈ 0.3 × mean.', make: () => I.normalDist(x.conceded_mean, Math.max(4, 0.3 * x.conceded_mean)) }),
      };
    }
    side.players.push(o);
  });
  return side;
}
function findRow(a, b, venue) {
  const rows = (D.M && D.M.matchups) || [];
  return rows.find(r => ((r.A === a.name && r.B === b.name) || (r.A === b.name && r.B === a.name)) && r.venue === venue) || null;
}
const swapStats = r => ({ A: r.B, B: r.A, A_stats: r.B_stats, B_stats: r.A_stats, p_win_A: 1 - r.p_win_A - 0, p_tie: r.p_tie, venue: r.venue, home: r.home, n: r.n, _swapped: true, _raw: r });
/** canonical match from matchups.json; vk: 'A' (a's home), 'B' (b's home), 'n' (neutral ground) */
I.preMatch = (a, b, vk) => {
  let r, venue;
  if (vk === 'n') {
    const nf = (D.M.neutral_full || []).find(x => (x.A === a.name && x.B === b.name) || (x.A === b.name && x.B === a.name));
    if (!nf) {
      const x = (D.M.neutral || []).find(y => (y.A === a.name && y.B === b.name) || (y.A === b.name && y.B === a.name));
      if (!x) return null; const sw = x.A !== a.name;
      return { a, b, venue: 'neutral', vk, neutralOnly: true, n: D.M.n_sims, pWinA: sw ? 1 - x.p_win_A : x.p_win_A, runsA: sw ? x.runs_B : x.runs_A, runsB: sw ? x.runs_A : x.runs_B, source: 'matchups.json (neutral)' };
    }
    r = nf; venue = 'neutral';
  } else { venue = I.venueKey(vk, a, b); r = findRow(a, b, venue); if (!r) return null; }
  const raw = r; if (r.A !== a.name) r = swapStats(r);
  const M = { a, b, venue, vk, raw, n: r.n || D.M.n_sims, pWinA: r.p_win_A, pTie: r.p_tie, source: vk === 'n' ? 'matchups.json, neutral' : 'matchups.json', toss: D.M.toss };
  M.A = preSide(r.A_stats, a, r, 'A'); M.B = preSide(r.B_stats, b, r, 'B');
  const sdT = Math.sqrt((M.A.total.sd || 30) ** 2 + (M.B.total.sd || 30) ** 2);
  M.total = mkStat({ mean: M.A.total.mean + M.B.total.mean, sd: sdT, exact: false, src: 'approx', note: 'Approximate: normal with the two innings treated as independent.', make: () => I.normalDist(M.A.total.mean + M.B.total.mean, sdT) });
  const m1 = (M.A.bat1 + M.B.bat1) / 2;
  M.inn1 = mkStat({ mean: m1, exact: false, src: 'approx', note: 'Approximate: each team\'s total curve shifted to its batting-first mean, mixed 50/50.', make: () => {
    const da = M.A.total.dist, db = M.B.total.dist, sa = Math.round(M.A.bat1 - M.A.total.mean), sb = Math.round(M.B.bat1 - M.B.total.mean), acc = {};
    da.pmf().forEach(r2 => { acc[r2.x + sa] = (acc[r2.x + sa] || 0) + r2.p / 2; }); db.pmf().forEach(r2 => { acc[r2.x + sb] = (acc[r2.x + sb] || 0) + r2.p / 2; });
    return S.dist.fromPmf(acc);
  } });
  M.exact = false;
  return M;
};

/* exact pmfs from data/matchups/<HOST>.json: {o, p, t} per stat, one condition per batting-first side */
/* {o, p, t, tl, th} pmfs (full mass since round 3: p[0] = P(X <= o), p[last] = P(X >= o + len - 1); older files were trimmed) */
const mixPmf = parts => {
  const acc = {}; let any = false, trim = 0, tl = 0, th = 0, folded = false, lo = Infinity, hi = -Infinity;
  parts.forEach(([w, pm]) => {
    if (!w || !pm || !Array.isArray(pm.p)) return; any = true;
    const o = pm.o || 0, n = pm.p.length, s = pm.p.reduce((x, y) => x + y, 0);
    if ('tl' in pm || 'th' in pm) { folded = true; tl += w * (pm.tl || 0); th += w * (pm.th || 0); } else trim += w * (pm.t || 0);
    lo = Math.min(lo, o); hi = Math.max(hi, o + n - 1);
    pm.p.forEach((q, k) => { if (q > 0) acc[o + k] = (acc[o + k] || 0) + w * q / (folded && s > 0 ? s : 1); });
  });
  if (!any) return null;
  const d = S.dist.fromPmf(acc); Object.assign(d, { trim, tl, th, folded, lo, hi }); return d;
};
I.pmfFiles = async () => { const m = await I.loadMeta().catch(() => null); const f = (m && m.matchups && m.matchups.files) || Object.keys((m && m.files_bytes) || {}); return f.filter(x => /^matchups\/(?!index)/.test(x)); };
I.loadPmfRow = async (a, b, vk) => {
  if (vk === 'n') return null;
  const host = vk === 'B' ? b : a, files = await I.pmfFiles(), f = files.find(x => x === 'matchups/' + host.short + '.json');
  if (!f) return null;
  const J = await S.load('data/' + f).catch(() => null); if (!J) return null;
  const r = (J.matchups || []).find(x => ((x.A === a.name && x.B === b.name) || (x.A === b.name && x.B === a.name)));
  return r ? { r, file: f, J } : null;
};
/** precomputed match with exact distributions; bf = null (toss unknown, 50/50), 'A' or 'B' (that side bats first) */
I.exactMatch = async (a, b, vk, bf) => {
  const M = I.preMatch(a, b, vk); if (!M) return null;
  const L = await I.loadPmfRow(a, b, vk);
  if (!L) return M;
  const { r, file, J } = L, ca = r.conditions.find(c => c.bat_first === a.name), cb = r.conditions.find(c => c.bat_first === b.name);
  if (!ca || !cb) return M;
  const W = bf === 'A' ? [[1, ca], [0, cb]] : bf === 'B' ? [[0, ca], [1, cb]] : [[0.5, ca], [0.5, cb]];
  const side = (c, k) => c[r.A === a.name ? k : (k === 'A' ? 'B' : 'A')];
  const mk = get => mixPmf(W.map(([w, c]) => [w, get(c)]));
  const wmean = get => { let s = 0, ws = 0; W.forEach(([w, c]) => { const v = get(c); if (w && isNum(v)) { s += w * v; ws += w; } }); return ws ? s / ws : null; };
  const nPer = J.n_sims_per_condition || ca.n;
  const put = (st, d) => { if (!st || !d) return; st.dist = d; st.exact = true; st.src = 'export'; st.note = ''; st.file = file; st.nCond = nPer; if (bf) { st.mean = d.mean; st.sd = d.sd; st.q = {}; [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95].forEach(p => { st.q[p] = d.quantile(p); }); } };
  const fresh = d => d ? Object.assign(statFromDist(d, 'export'), { file, nCond: nPer }) : null;
  put(M.total, mk(c => c.match_total_pmf)); put(M.inn1, mk(c => c.first_innings_total_pmf));
  M.fours = fresh(mk(c => c.match_fours_pmf)); M.sixes = fresh(mk(c => c.match_sixes_pmf));
  ['A', 'B'].forEach(sd => {
    const T = M[sd], g = k => c => (side(c, sd) || {})[k];
    put(T.total, mk(g('total_pmf'))); put(T.pp, mk(g('pp_pmf'))); put(T.fow1, mk(g('fow1_pmf'))); put(T.fours, mk(g('fours_pmf'))); put(T.sixes, mk(g('sixes_pmf')));
    const wk = mk(g('wkts_pmf')); if (wk) T.wkts = Object.assign(fresh(wk), bf ? {} : { mean: T.wkts.mean });
    T.players.forEach(p => {
      const pp = k => c => (((side(c, sd) || {}).players || {})[p.id] || {})[k];
      const mean = k => wmean(c => { const x = pp('mean')(c); return x ? x[k] : null; });
      ['runs', 'balls', 'fours', 'sixes'].forEach(k => { if (p[k]) put(p[k], mk(pp(k + '_pmf'))); });
      if (bf) {
        // per-toss means and probabilities (round-3 files carry them per condition)
        ['runs', 'balls', 'fours', 'sixes'].forEach(k => { const v = mean(k); if (p[k] && isNum(v)) p[k].mean = v; });
        if (isNum(mean('p_duck'))) { p.pDuck = mean('p_duck'); p.duckPerToss = true; }
        if (isNum(mean('p_bat'))) p.pBat = mean('p_bat'); if (isNum(mean('p_out'))) p.pOut = mean('p_out'); if (isNum(mean('p_top_bat'))) p.pTop = mean('p_top_bat');
        if (p.runs && p.runs.exact) [10, 20, 30, 40, 50, 75, 100].forEach(t => { p.pRuns[t] = p.runs.dist.pOver(t - 0.5); });
        if (p.runs && p.runs.exact && isNum(p.pDuck)) p.perTossDuck = false;
      }
      if (p.bowl) {
        const w = mk(pp('wkts_pmf')); if (w) { const keep = p.bowl.wkts.mean; p.bowl.wkts = Object.assign(fresh(w), bf ? {} : { mean: keep }); if (bf) [1, 2, 3, 4, 5].forEach(t => { p.bowl.pW[t] = w.pOver(t - 0.5); }); }
        put(p.bowl.conceded, mk(pp('conceded_pmf')));
        if (bf) {
          if (isNum(mean('wkts'))) p.bowl.wkts.mean = mean('wkts'); if (isNum(mean('conceded'))) p.bowl.conceded.mean = mean('conceded');
          if (isNum(mean('overs'))) { p.bowl.overs = mean('overs'); if (isNum(mean('conceded')) && p.bowl.overs) p.bowl.econ = mean('conceded') / p.bowl.overs; }
          if (isNum(mean('p_top_bowl'))) p.bowl.pTop = mean('p_top_bowl');
        }
      }
    });
  });
  // winning margins: per team, batting first (runs) and chasing (wickets, balls to spare)
  const mg = {};
  [['A', a, ca, cb, bf === 'A' ? 1 : bf === 'B' ? 0 : 0.5], ['B', b, cb, ca, bf === 'B' ? 1 : bf === 'A' ? 0 : 0.5]].forEach(([sd, t, own, oth, w]) => {
    mg[sd] = {
      first: { w, p: own.p_bat1_win_in_20, runs: own.bat1_win_runs_pmf ? mixPmf([[1, own.bat1_win_runs_pmf]]) : null },
      chase: { w: 1 - w, p: oth.p_bat2_win_in_20, wkts: oth.bat2_win_wkts_pmf ? mixPmf([[1, oth.bat2_win_wkts_pmf]]) : null, balls: oth.bat2_win_balls_pmf ? mixPmf([[1, oth.bat2_win_balls_pmf]]) : null },
    };
  });
  if (isNum(ca.p_bat1_win_in_20)) M.margin = mg;
  if (bf) {
    const c = bf === 'A' ? ca : cb, pA = r.A === a.name ? c.p_win_A : 1 - c.p_win_A;
    const perToss = Object.values((side(c, 'A') || {}).players || {}).some(x => x.mean);
    const duck = M.A.players.concat(M.B.players).some(x => x.duckPerToss);
    Object.assign(M, { pWinA: pA, pTie: c.p_tie, n: c.n, batFirst: bf, tossNote: perToss ? `Player means, P(bat), P(out)${duck ? ', P(duck)' : ''} and top scorer/bowler are for this toss; ${duck ? '' : 'P(duck) and '}the batting-first table ${duck ? 'is' : 'are'} pooled over both tosses.` : 'P(bat), P(out), top scorer/bowler and the batting-first table are pooled over both tosses (the export keeps only distributions per toss).' });
  } else M.n = 2 * nPer;
  M.exact = true; M.source = file; M.distSource = file;
  return M;
};

/** canonical match from IPLSim raw counts (sim-run.js / simMatchRaw + mergeRaw) */
const hstat = arr => statFromDist(pmfDist(arr || []), 'sim');
const hmean = arr => { let s = 0, n = 0; (arr || []).forEach((c, i) => { s += c * i; n += c; }); return n ? s / n : null; };
function rawSide(T, t, order) {
  const side = {
    team: t, total: hstat(T.total), pp: hstat(T.pp), fow1: hstat(T.fow1), fours: hstat(T.fours), sixes: hstat(T.sixes), wkts: hstat(T.wkts),
    wides: hmean(T.wides), extras: hmean(T.extras), bat1: T.bat1 && T.bat1.n ? hmean(T.bat1.total) : null, bat2: T.bat2 && T.bat2.n ? hmean(T.bat2.total) : null,
    pWinBat1: T.bat1 && T.bat1.n ? T.bat1.wins / T.bat1.n : null, pWinBat2: T.bat2 && T.bat2.n ? T.bat2.wins / T.bat2.n : null, players: [],
  };
  const ids = (order || []).concat(Object.keys(T.players).filter(id => !(order || []).includes(id)));
  ids.forEach(id => {
    const x = T.players[id]; if (!x) return;
    const o = { id, name: I.pname(id), pos: null };
    if (x.n_bat) {
      const runs = hstat(x.runs), pr = {}; [10, 20, 30, 40, 50, 75, 100].forEach(th => { pr[th] = runs.dist.pOver(th - 0.5); });
      Object.assign(o, { pos: (order || []).indexOf(id) + 1 || null, pBat: x.batted / x.n_bat, pOut: x.out / x.n_bat, pDuck: x.duck / x.n_bat, pTop: x.top_bat / x.n_bat, pRuns: pr, runs, balls: hstat(x.balls), fours: hstat(x.fours), sixes: hstat(x.sixes) });
    }
    if (x.n_bowl) {
      const wk = hstat(x.wkts), pw = {}; [1, 2, 3, 4, 5].forEach(th => { pw[th] = wk.dist.pOver(th - 0.5); });
      const conc = hstat(x.conceded);
      o.bowl = { overs: x.legal_balls / x.n_bowl / 6, econ: x.legal_balls ? conc.mean * x.n_bowl / x.legal_balls * 6 : null, pTop: x.top_bowl / x.n_bowl, pW: pw, wkts: wk, conceded: conc };
    }
    side.players.push(o);
  });
  return side;
}
/** o: {venue, vk, source, batFirst, orders: {A, B}, conditions} */
I.fromRaw = (raw, a, b, o = {}) => {
  const N = raw.n;
  const M = { a, b, venue: o.venue || null, vk: o.vk, n: N, pWinA: raw.A.wins / N, pTie: raw.ties / N, source: o.source || 'in-browser simulation', batFirst: o.batFirst || null, conditions: o.conditions || null, exact: true };
  M.A = rawSide(raw.A, a, o.orders && o.orders.A); M.B = rawSide(raw.B, b, o.orders && o.orders.B);
  M.total = hstat(raw.match_total); M.inn1 = hstat(raw.first_innings_total);
  if (raw.match_fours) M.fours = hstat(raw.match_fours); if (raw.match_sixes) M.sixes = hstat(raw.match_sixes);
  const by = raw.by_bat_first;
  if (by && (by.A || by.B)) {
    const nA = by.A ? by.A.n : 0, nB = by.B ? by.B.n : 0, tot = nA + nB || 1, hd = h => h && h.some(x => x > 0) ? pmfDist(h) : null;
    const first = (c, w) => c && c.n ? { w, p: c.bat1_wins_in_20 / c.n, runs: hd(c.bat1_win_runs) } : { w: 0, p: null };
    const chase = (c, w) => c && c.n ? { w, p: c.bat2_wins_in_20 / c.n, wkts: hd(c.bat2_win_wkts), balls: hd(c.bat2_win_balls) } : { w: 0, p: null };
    M.margin = { A: { first: first(by.A, nA / tot), chase: chase(by.B, nB / tot) }, B: { first: first(by.B, nB / tot), chase: chase(by.A, nA / tot) } };
  }
  return M;
};
/** replace approximate distributions in M (precomputed) with the exact ones from X (same lineups, in-browser) */
I.overlay = (M, X) => {
  const put = (s, x) => { if (s && x && !s.exact) { s.dist = x.dist; s.exact = true; s.src = 'sim'; s.simMean = x.mean; s.simN = X.n; s.note = ''; } };
  ['total', 'inn1'].forEach(k => put(M[k], X[k]));
  ['A', 'B'].forEach(sd => {
    ['total', 'pp', 'fow1', 'fours', 'sixes'].forEach(k => put(M[sd][k], X[sd][k]));
    M[sd].players.forEach(p => {
      const q = X[sd].players.find(y => y.id === p.id); if (!q) return;
      ['runs', 'balls', 'fours', 'sixes'].forEach(k => put(p[k], q[k]));
      if (p.bowl && q.bowl) ['wkts', 'conceded'].forEach(k => { if (p.bowl[k].src !== 'export') put(p.bowl[k], q.bowl[k]); });
    });
  });
  M.exact = true; M.distN = X.n; M.distSource = X.source;
  return M;
};

/* ════════ in-browser simulation ════════ */
I.SIM_WORKERS = 4; I.SIM_SEED = 7;
/** run sim-run.js; spec {A, B (team specs), opts {venue, batFirst, conditions}, sims, base?}.
    Returns {job} (wrapped: a job is thenable, and an async function would adopt it); job resolves to {main, base} raw counts. */
I.simulate = async (spec, onProgress) => {
  const sp = await I.loadSimParams();
  return { job: S.simulate({ module: 'sim-run.js', params: Object.assign({ sp }, spec), workers: I.SIM_WORKERS, seed: I.SIM_SEED, onProgress }) };
};
D.exact = new Map();
/** exact distributions for a default matchup without an exported pmf file (neutral grounds): 20,000 in-browser sims */
I.exactFor = (a, b, vk, bf) => {
  const venue = I.venueKey(vk, a, b), key = a.short + '|' + b.short + '|' + venue + '|' + (bf || '');
  if (D.exact.has(key)) return D.exact.get(key);
  const p = (async () => {
    const { job } = await I.simulate({ A: I.defTeam(a), B: I.defTeam(b), opts: { venue: venue === 'neutral' ? null : venue, batFirst: bf || null }, sims: 20000 });
    const r = await job.promise;
    return I.fromRaw(r.main, a, b, { venue, vk, batFirst: bf || null, source: 'in-browser simulation of the default XIs', orders: { A: a.order, B: b.order } });
  })();
  p.catch(() => D.exact.delete(key));
  D.exact.set(key, p);
  return p;
};

/* ════════ small helpers ════════ */
I.card = (parent, title, note, cls) => {
  const c = h('div', { class: 'sh-card' + (cls ? ' ' + cls : '') });
  if (title) c.append(h('div', { class: 'sh-h', text: title }));
  if (note) c.append(h('div', { class: 'sh-note', html: note }));
  if (parent) parent.append(c);
  return c;
};
I.go = (sheet, params) => I.wb.activate(sheet, { params: params || {}, push: true });
I.hashFor = (sheet, params) => '#sheet=' + sheet + Object.entries(params || {}).filter(([, v]) => v != null && v !== '').map(([k, v]) => '&' + encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('');
I.fmtLine = v => F.num(v, Number.isInteger(v) ? 0 : 1);
I.overs = balls => { if (!isNum(balls)) return '–'; const b = Math.round(balls); return Math.floor(b / 6) + '.' + (b % 6); };
I.oversF = ov => isNum(ov) ? I.overs(ov * 6) : '–';
I.fairLine = (d, center) => { let best = null, bd = 9; const c0 = Math.floor(center) + 0.5; for (let k = -40; k <= 40; k++) { const L = c0 + k; if (L < 0) continue; const v = Math.abs(d.pOver(L) - 0.5); if (v < bd) { bd = v; best = L; } } return best ?? 0.5; };
I.clickRows = (wrap, rows, fn) => { wrap.classList.add('ip-click'); wrap.querySelectorAll('tbody tr').forEach((tr, k) => { tr.tabIndex = 0; tr.addEventListener('click', () => fn(rows[k], k)); tr.addEventListener('keydown', e => { if (e.key === 'Enter') fn(rows[k], k); }); }); };

/* ════════ custom charts (inline SVG, framework tokens) ════════ */
function chartBase(el, draw) {
  el.classList.add('sc');
  let lastW = 0;
  const render = () => { const w = el.clientWidth || 600; lastW = w; draw(el, w); };
  render();
  if (typeof ResizeObserver !== 'undefined') { let raf = 0; new ResizeObserver(() => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; if (Math.abs((el.clientWidth || 0) - lastW) > 2) render(); }); }).observe(el); }
  return { el, update: render };
}
const tw = (s, px = 11) => String(s).length * px * 0.56;
function niceStep(span, n) { const s0 = span / Math.max(1, n); const mag = 10 ** Math.floor(Math.log10(s0 || 1)); const e = s0 / mag; return (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag; }
function ticks(lo, hi, n) { const st = niceStep(hi - lo, n), out = []; for (let t = Math.ceil(lo / st - 1e-9) * st; t <= hi + 1e-9; t += st) out.push(+t.toFixed(10)); return out; }
function hb(x0, x1, y, hh, r = 3) {
  const w = Math.abs(x1 - x0); if (w < 0.4) return `M${x0},${y}h0.6v${hh}h-0.6Z`; r = Math.min(r, hh / 2, w);
  return x1 >= x0 ? `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + hh - r}Q${x1},${y + hh} ${x1 - r},${y + hh}H${x0}Z`
    : `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + hh - r}Q${x1},${y + hh} ${x1 + r},${y + hh}H${x0}Z`;
}
function hover(svg, sel, fn) {
  svg.addEventListener('pointermove', e => { const t = e.target.closest(sel); if (t) { const html = fn(t); if (html) S.tip.show(e.clientX, e.clientY, html); } else S.tip.hide(); });
  svg.addEventListener('pointerleave', () => S.tip.hide());
}
const titleHtml = o => o.title ? `<div class="sh-h">${esc(o.title)}</div>${o.subtitle ? `<div class="sh-note" style="margin-bottom:6px">${esc(o.subtitle)}</div>` : ''}` : '';

/** Waterfall: start → +each item → total. items [{label, value, desc, id}] */
I.waterfall = (el, o) => chartBase(el, (el, Wd) => {
  const f = F.make(o.fmt || 'signed:1');
  const rows = []; let cum = o.start || 0;
  rows.push({ label: o.startLabel || 'Start', v0: cum, v1: cum, kind: 'start' });
  o.items.forEach(it => { rows.push({ label: it.label, v0: cum, v1: cum + it.value, value: it.value, desc: it.desc, kind: 'item', it }); cum += it.value; });
  rows.push({ label: o.endLabel || 'Total', v0: o.start || 0, v1: cum, kind: 'total', value: cum });
  let lo = Math.min(...rows.map(r => Math.min(r.v0, r.v1))), hi = Math.max(...rows.map(r => Math.max(r.v0, r.v1)));
  const pad = (hi - lo) * 0.04 || 1; lo -= pad; hi += pad;
  const labW = Math.min(Wd * 0.4, Math.max(...rows.map(r => tw(r.label, 11.5))) + 10), valW = 46;
  const bh = 13, gap = 6, band = bh + gap, mt = 4, Hh = rows.length * band, ml = labW + 6, mr = valW;
  const x = v => ml + (v - lo) / (hi - lo) * (Wd - ml - mr);
  const tk = ticks(lo, hi, Math.max(2, Math.floor((Wd - ml - mr) / 70)));
  let s = `<svg width="${Wd}" height="${mt + Hh + 22}" role="img" aria-label="${esc(o.title || 'Waterfall')}"><g class="gr">`;
  for (const t of tk) s += `<line x1="${x(t).toFixed(1)}" x2="${x(t).toFixed(1)}" y1="${mt}" y2="${mt + Hh}"/>`;
  s += '</g>';
  rows.forEach((r, k) => {
    const y = mt + k * band + gap / 2, strong = r.kind !== 'item';
    s += `<text class="${strong ? 'lab-s' : 'lab'}" x="${labW}" y="${y + bh / 2}" dy="0.32em" text-anchor="end">${esc(r.label)}</text>`;
    if (r.kind === 'start') s += `<line class="ip-tick" x1="${x(r.v0)}" x2="${x(r.v0)}" y1="${y - 1}" y2="${y + bh + 1}"/>`;
    else s += `<path class="bar ${r.kind === 'total' ? 'f1' : r.value >= 0 ? 'fpos' : 'fneg'}" data-k="${k}" d="${hb(x(r.v0), x(r.v1), y, bh)}"/>`;
    if (k < rows.length - 1 && r.kind !== 'total') { const nx = rows[k + 1]; if (nx.kind === 'item') s += `<line class="ip-conn" x1="${x(r.v1)}" x2="${x(r.v1)}" y1="${y + bh}" y2="${y + band}"/>`; }
    if (r.kind !== 'start') { const right = Math.max(r.v0, r.v1); s += `<text class="${strong ? 'lab-s' : 'lab'}" x="${x(right) + 5}" y="${y + bh / 2}" dy="0.32em">${esc(f(r.value))}</text>`; }
    s += `<rect class="hit" data-k="${k}" x="0" y="${y - gap / 2}" width="${Wd}" height="${band}"/>`;
  });
  s += `<g class="ax"><line x1="${x(o.start || 0)}" x2="${x(o.start || 0)}" y1="${mt}" y2="${mt + Hh}"/>`;
  let lastR = -1e9; for (const t of tk) { const px = x(t), lab = F.make(o.tickFmt || o.fmt || 'signed:0')(t); if (px - tw(lab, 10.5) / 2 < lastR + 6) continue; lastR = px + tw(lab, 10.5) / 2; s += `<text x="${px.toFixed(1)}" y="${mt + Hh + 15}" text-anchor="middle">${esc(lab)}</text>`; }
  s += '</g></svg>';
  el.innerHTML = titleHtml(o) + s + (o.legend ? `<div class="sh-note ip-legend">${o.legend}</div>` : '');
  const svg = el.querySelector('svg');
  hover(svg, '[data-k]', t => { const r = rows[+t.dataset.k]; if (r.kind === 'start') return S.tip.html(r.label, [{ value: f(r.v0), label: 'baseline' }]); return S.tip.html(r.label, [{ value: f(r.value), label: r.kind === 'total' ? 'sum' : 'contribution' }].concat(r.kind === 'item' ? [{ value: f(r.v1), label: 'running total' }] : []), r.desc); });
  if (o.onClick) svg.addEventListener('click', e => { const t = e.target.closest('[data-k]'); if (t) { const r = rows[+t.dataset.k]; if (r.it) o.onClick(r.it); } });
});

/** Player vs league average, small multiples: panels [{title, fmt, better:'high'|'low', rows:[{label, v, avg, sd}]}] */
I.vsAvg = (el, o) => chartBase(el, (el, Wd) => {
  const P = o.panels.filter(p => p.rows.some(r => isNum(r.v)));
  const nCol = Wd >= 560 && P.length > 1 ? P.length : 1, gapX = 22;
  const labW = Math.max(...P.flatMap(p => p.rows.map(r => tw(r.label, 11.5)))) + 8;
  const pw = (Wd - gapX * (nCol - 1)) / nCol, rh = 24, mt = 18, valW = 44;
  let html = titleHtml(o) + '<div class="ip-mult">';
  P.forEach((p, pi) => {
    const f = F.make(p.fmt || 'num:1');
    const vals = p.rows.flatMap(r => [r.v, r.avg, isNum(r.sd) ? r.v + r.sd : null, isNum(r.sd) ? r.v - r.sd : null]).filter(isNum);
    let lo = p.domain ? p.domain[0] : Math.min(0, ...vals), hi = p.domain ? p.domain[1] : Math.max(...vals) * 1.06;
    if (p.zero === false) { const span = Math.max(...vals) - Math.min(...vals) || 1; lo = Math.min(...vals) - span * 0.25; hi = Math.max(...vals) + span * 0.15; }
    const x = v => labW + (v - lo) / ((hi - lo) || 1) * (pw - labW - valW);
    const Hh = p.rows.length * rh;
    let s = `<svg width="${pw}" height="${mt + Hh + 4}" role="img" aria-label="${esc(p.title)}"><text class="al" x="${labW}" y="11">${esc(p.title)}</text>`;
    p.rows.forEach((r, k) => {
      const y = mt + k * rh + 5, bh = rh - 10;
      s += `<text class="lab-s" x="${labW - 8}" y="${y + bh / 2}" dy="0.32em" text-anchor="end">${esc(r.label)}</text>`;
      if (isNum(r.v)) {
        const good = isNum(r.avg) ? (p.better === 'low' ? r.v <= r.avg : r.v >= r.avg) : true;
        s += `<path class="bar ${isNum(r.avg) ? (good ? 'fpos' : 'fneg') : 'f1'}" data-p="${pi}" data-k="${k}" d="${hb(x(lo), x(r.v), y, bh)}"/>`;
        if (isNum(r.sd) && r.sd > 0) s += `<line class="ip-whisk" x1="${x(r.v - r.sd)}" x2="${x(r.v + r.sd)}" y1="${y + bh / 2}" y2="${y + bh / 2}"/>`;
        s += `<text class="lab" x="${x(Math.max(r.v, r.avg ?? -1e9, isNum(r.sd) ? r.v + r.sd : -1e9)) + 5}" y="${y + bh / 2}" dy="0.32em">${esc(f(r.v))}</text>`;
      }
      if (isNum(r.avg)) s += `<line class="ip-tick" x1="${x(r.avg)}" x2="${x(r.avg)}" y1="${y - 3}" y2="${y + bh + 3}"/>`;
      s += `<rect class="hit" data-p="${pi}" data-k="${k}" x="0" y="${y - 5}" width="${pw}" height="${rh}"/>`;
    });
    s += '</svg>';
    html += `<div style="width:${pw}px">${s}</div>`;
  });
  html += '</div>' + (o.legend ? `<div class="sh-note ip-legend">${o.legend}</div>` : '');
  el.innerHTML = html;
  el.querySelectorAll('svg').forEach(svg => hover(svg, '[data-k]', t => { const p = P[+t.dataset.p], r = p.rows[+t.dataset.k], f = F.make(p.fmt || 'num:1'); return S.tip.html(`${r.label} · ${p.title}`, [{ value: f(r.v), label: o.who || 'player', key: 'b1' }, { value: f(r.avg), label: 'IPL average' }].concat(isNum(r.sd) ? [{ value: '± ' + f(r.sd), label: 'posterior SD' }] : []).concat(isNum(r.v) && isNum(r.avg) ? [{ value: F.signed(r.v - r.avg, 1), label: 'vs average' + (p.better === 'low' ? ' (lower is better)' : '') }] : []), r.desc); }));
});

/** Over-by-over bowling strip: sched = 20 ids; colour = bowler (fixed plan order), initials in each cell */
I.overStrip = (el, o) => chartBase(el, (el, Wd) => {
  const ids = o.bowlers || [...new Set(o.sched)], idx = id => ids.indexOf(id);
  const narrow = Wd < 520, per = narrow ? 10 : 20, rowsN = Math.ceil(20 / per);
  const cw = Math.min(46, (Wd - 4) / per), ch = 26, gapY = 20, mt = 14;
  const ini = id => { const n = I.pname(id).split(' '); return n.length > 1 ? (n[0][0] + n[n.length - 1].slice(0, 3)) : n[0].slice(0, 4); };
  let s = `<svg width="${Wd}" height="${mt + rowsN * (ch + gapY)}" role="img" aria-label="${esc(o.title || 'Bowling plan by over')}">`;
  for (let r = 0; r < rowsN; r++) {
    const y0 = mt + r * (ch + gapY);
    for (let k = 0; k < per; k++) {
      const ov = r * per + k; if (ov >= 20) break; const id = o.sched[ov], j = idx(id), x0 = 2 + k * cw;
      if (ov === 0 || ov === 6 || ov === 15) s += `<text class="al" x="${x0}" y="${y0 - 4}">${ov === 0 ? 'Powerplay' : ov === 6 ? 'Middle' : 'Death'}</text>`;
      s += `<rect class="cell f${j % 8 + 1}" data-o="${ov}" x="${x0 + 1}" y="${y0}" width="${cw - 2}" height="${ch}" rx="3" opacity=".42"/>`;
      if (cw > 30) s += `<text class="ip-ctext" x="${x0 + cw / 2}" y="${y0 + ch / 2}" dy="0.32em" text-anchor="middle">${esc(ini(id))}</text>`;
      s += `<text class="al" x="${x0 + cw / 2}" y="${y0 + ch + 11}" text-anchor="middle">${ov + 1}</text>`;
    }
  }
  s += '</svg>';
  const legend = `<div class="sc-legend">${ids.map((id, i) => `<span><i class="b${i % 8 + 1}"></i>${esc(I.pname(id))}${o.sub ? ' <span class="muted">' + esc(o.sub(id)) + '</span>' : ''}</span>`).join('')}</div>`;
  el.innerHTML = titleHtml(o) + legend + s;
  hover(el.querySelector('svg'), '[data-o]', t => { const ov = +t.dataset.o, id = o.sched[ov]; return S.tip.html(`Over ${ov + 1} · ${ov < 6 ? 'Powerplay' : ov < 15 ? 'Middle' : 'Death'}`, [{ value: I.pname(id), label: 'bowler', key: 'b' + (idx(id) % 8 + 1) }]); });
});

/* ════════ line pricer: input + summary + ladder centred on the entered line ════════ */
I.linePricer = (el, o) => {
  const step = o.step || 1, rows = o.rows ?? 4;
  const inp = h('input', { type: 'number', step: 0.5, class: 'ip-line', value: o.line, 'aria-label': (o.inputLabel || 'Line') });
  const summary = h('div', { class: 'ip-px' }), lad = h('div'), note = o.note ? h('div', { class: 'sh-note', html: o.note }) : null;
  el.append(h('div', { class: 'ip-lrow' }, h('label', { class: 'ip-lab' }, h('span', { class: 'ui-l', text: o.inputLabel || 'Line' }), inp), summary), lad);
  if (note) el.append(note);
  let cur = o.line;
  const draw = () => {
    let L = parseFloat(inp.value); if (!isFinite(L)) L = o.line; cur = L;
    const d = o.dist, po = d.pOver(L), pu = d.pUnder(L), pe = d.pEq(L), nf = 1 - pe;
    summary.innerHTML = `<span>Over <b>${esc(I.fmtLine(L))}</b> <b>${F.pct(po, 1)}</b> · fair <b>${esc(I.fp(po / nf))}</b></span><span>Under <b>${F.pct(pu, 1)}</b> · fair <b>${esc(I.fp(pu / nf))}</b>${pe > 0.0005 ? ` · push ${F.pct(pe, 1)}` : ''}</span>`;
    const ls = []; for (let k = -rows; k <= rows; k++) { const v = +(L + k * step).toFixed(2); if (o.min == null || v >= o.min) ls.push(v); }
    S.ladder(lad, { dist: d, lines: ls, label: o.label || 'Line', odds: I.odds.mode, highlight: L, note: o.ladderNote === false ? false : undefined, compact: o.compact });
    if (o.onLine) o.onLine(L);
  };
  inp.addEventListener('input', S.debounce(draw, 200));
  inp.addEventListener('change', draw);
  draw();
  I.odds.bind(el, draw);
  return { el, get line() { return cur; }, set(L) { inp.value = L; draw(); } };
};

/** histogram + pricer for one Stat; opts {label, xLabel, step, min, line, onLine, rows, compact, height} */
I.distBox = (el, st, o = {}) => {
  if (!st || !st.dist) { el.append(h('div', { class: 'sh-note', text: 'No distribution.' })); return; }
  const d = st.dist, hh = h('div'); el.append(hh);
  const lo = Math.max(0, d.quantile(0.002)), hi = d.quantile(0.998);
  const chart = S.histogram(hh, { dist: d, xDomain: [Math.floor(lo) - 0.5, Math.ceil(hi) + 0.5], height: o.height || 110, xLabel: o.xLabel || '', maxBars: o.maxBars || 70 });
  const pr = h('div', { style: { marginTop: '4px' } }); el.append(pr);
  const fair = Math.max(0.5, I.fairLine(d, st.mean)), L0 = isNum(o.line) ? o.line : fair;
  I.linePricer(pr, { dist: d, line: L0, step: o.step || 1, rows: o.rows ?? 3, min: 0.5, label: o.label || 'Line', inputLabel: (o.label || '') + ' line', ladderNote: false, compact: o.compact ?? true,
    onLine: L => { chart.update({ split: L, markers: I.markers(d, L) }); if (o.onLine) o.onLine(L === fair ? null : L); } });
  el.append(h('div', { class: 'sh-note ip-src', text: I.srcNote(st) }));
};
/** line marker, plus a mean marker when it is far enough from the line not to collide */
I.markers = (d, L) => { const span = Math.max(1, d.quantile(0.998) - d.quantile(0.002)), m = [{ x: L, label: 'O/U ' + I.fmtLine(L), strong: true }]; if (Math.abs(d.mean - L) / span > 0.12) m.push({ x: d.mean, label: 'mean' }); return m; };
I.srcNote = st => {
  if (!st) return '';
  if (st.src === 'export') { const d = st.dist || {}; return `Exact simulated distribution from data/${st.file || 'the model export'}${st.nCond ? ` (${F.int(st.nCond)} sims with each side batting first)` : ''}.` + (d.folded ? ` The end values are open-ended: ${F.int(d.lo)} means ≤${F.int(d.lo)} and ${F.int(d.hi)} means ≥${F.int(d.hi)} (${F.pct((d.tl || 0) + (d.th || 0), 2)} folded in).` : isNum(d.trim) && d.trim > 0 ? ` Values rarer than 0.05% each are left out (${F.pct(d.trim, 1)} in all), so far-tail lines are slightly off.` : ''); }
  if (st.src === 'sim' && isNum(st.simMean)) return `Distribution: ${F.int(st.simN)} in-browser simulations of the same XIs (seed ${I.SIM_SEED}); mean ${F.num(st.simMean, 1)} there vs ${F.num(st.mean, 1)} precomputed, the gap is Monte Carlo noise.`;
  if (st.src === 'sim') return 'Exact simulated distribution.';
  if (st.src === 'p_wkts') return st.note || 'From the simulated P(wickets ≥ k).';
  return (st.note || 'Approximate shape.') + ' Exact distribution loading from an in-browser simulation…';
};

/* ════════ match view (Match sheet and Simulator) ════════ */
const T1 = v => F.num(v, 1);
I.STATS = [['runs', 'Runs', 'runs'], ['balls', 'Balls faced', 'balls'], ['fours', 'Fours', '4s'], ['sixes', 'Sixes', '6s'], ['wkts', 'Wickets', 'wkts'], ['conceded', 'Runs conceded', 'conceded']];
I.statOf = (p, k) => k === 'wkts' || k === 'conceded' ? (p.bowl ? p.bowl[k] : null) : p[k] || null;
I.renderMatch = (el, M, o = {}) => {
  el.innerHTML = '';
  const a = M.a.short, b = M.b.short;
  const lines = o.lines || {}, setLine = (k, v) => { if (o.onLines) o.onLines({ [k]: v }); };
  const venueTxt = M.venue === 'neutral' ? 'a neutral (average) ground' : I.venueName(M.venue);
  const toss = M.batFirst ? `${M.batFirst === 'A' ? a : b} batting first` : 'toss unknown (half the simulations with each side batting first)';
  const condTxt = M.conditions && Object.keys(M.conditions).length ? ' Conditions: ' + Object.entries(M.conditions).map(([g, v]) => `${g} ${String(v).replace('_', '/')}`).join(', ') + '.' : '';
  el.append(h('div', { class: 'sh-note', text: `${a} v ${b} at ${venueTxt}; ${toss}. ${F.int(M.n)} simulated matches (${M.source}). Fair prices are no-vig; "tie" means level after 20 overs, settled by the super over inside the win probabilities.${condTxt}${M.tossNote ? ' ' + M.tossNote : ''}${o.context ? ' ' + o.context : ''}` }));
  const tileEl = h('div');
  const drawTiles = () => {
    tileEl.innerHTML = '';
    tileEl.append(S.tiles([
      { label: `${a} win`, value: F.pct(M.pWinA, 1), sub: 'fair ' + I.fp(M.pWinA) },
      { label: `${b} win`, value: F.pct(1 - M.pWinA, 1), sub: 'fair ' + I.fp(1 - M.pWinA) },
      { label: `${a} total`, value: T1(M.A.total.mean), sub: `med ${F.num(M.A.total.q[0.5], 0)} · sd ${F.num(M.A.total.sd, 0)}` },
      { label: `${b} total`, value: T1(M.B.total.mean), sub: `med ${F.num(M.B.total.q[0.5], 0)} · sd ${F.num(M.B.total.sd, 0)}` },
      { label: 'Match total', value: T1(M.total.mean), sub: 'both innings' },
      { label: '1st-inns total', value: T1(M.inn1.mean), sub: 'bat-first side' },
      { label: 'Tie after 20', value: F.pct(M.pTie, 1), sub: 'fair ' + I.fp(M.pTie) },
    ]));
  };
  drawTiles(); I.odds.bind(tileEl, drawTiles);
  el.append(tileEl);

  if (o.base) {
    const B = o.base, n = Math.min(M.n, B.n);
    const seW = Math.sqrt(2 * M.pWinA * (1 - M.pWinA) / n), seA = Math.sqrt(2 / n) * M.A.total.sd, seB = Math.sqrt(2 / n) * M.B.total.sd;
    const dl = (label, v, se, f, sub) => ({ label, value: f(v), sub: '±' + f(Math.abs(se)).replace(/^[+−]/, '') + (sub ? ' · ' + sub : ''), }); // ± = 1 SE
    el.append(h('div', { class: 'sh-h', text: 'Change vs default' }), h('div', { class: 'sh-note', text: o.baseNote || 'Default = both teams\' default XIs and bowling plans at the same venue, toss unknown, run with the same seeds (common random numbers). ± is 1 SE treating the runs as independent, so it overstates the noise in the difference.' }),
      S.tiles([
        dl(`Δ ${a} win`, M.pWinA - B.pWinA, seW, v => F.spct(v, 1), 'was ' + F.pct(B.pWinA, 1)),
        dl(`Δ ${a} total`, M.A.total.mean - B.A.total.mean, seA, v => F.signed(v, 1), 'was ' + T1(B.A.total.mean)),
        dl(`Δ ${b} total`, M.B.total.mean - B.B.total.mean, seB, v => F.signed(v, 1), 'was ' + T1(B.B.total.mean)),
        { label: 'Δ match total', value: F.signed(M.total.mean - B.total.mean, 1), sub: 'default ' + T1(B.total.mean) },
        { label: `Δ ${a} powerplay`, value: F.signed(M.A.pp.mean - B.A.pp.mean, 1), sub: 'default ' + T1(B.A.pp.mean) },
        { label: `Δ ${b} powerplay`, value: F.signed(M.B.pp.mean - B.B.pp.mean, 1), sub: 'default ' + T1(B.B.pp.mean) },
      ]));
  }

  // toss / batting-first split
  const cs = h('div', { class: 'sh-cols' }); el.append(cs);
  const ct = I.card(cs, 'Batting first or second', `Each side's win probability and mean total by innings. ${M.batFirst ? 'This run fixes who bats first, so only one row has data.' : 'Half of the simulations have each side batting first.'}`);
  const tt = h('div'); ct.append(tt);
  const drawToss = () => S.table(tt, [
    { key: 'k', label: 'Bats first' }, { key: 'wa', label: `P(${a} win)`, fmt: 'pct:1' }, { key: 'fa', label: `${a} fair`, fmt: v => v ?? '', get: r => I.fp(r.wa) },
    { key: 'ta', label: `${a} total`, fmt: 'num:1', desc: 'mean' }, { key: 'tb', label: `${b} total`, fmt: 'num:1', desc: 'mean' },
  ], [
    { k: a, wa: M.A.pWinBat1, ta: M.A.bat1, tb: M.B.bat2 },
    { k: b, wa: isNum(M.B.pWinBat1) ? 1 - M.B.pWinBat1 : null, ta: M.A.bat2, tb: M.B.bat1 },
  ].filter(r => isNum(r.wa)));
  drawToss(); I.odds.bind(tt, drawToss);
  ct.append(h('div', { class: 'sh-note', text: `Chasing is ${M.A.pWinBat2 > M.A.pWinBat1 ? 'better' : 'worse'} for ${a} here (${F.pct(M.A.pWinBat2, 1)} chasing vs ${F.pct(M.A.pWinBat1, 1)} setting).` }));
  if (!isNum(M.A.pWinBat2) || !isNum(M.A.pWinBat1)) ct.lastChild.remove();
  const ce = I.card(cs, 'Innings shape', 'Means per innings: wickets lost, extras conceded by the other side\'s bowlers, and the score when the first wicket fell (whole total if none).');
  const et = h('div'); ce.append(et);
  S.table(et, [{ key: 'k', label: '' }, { key: 'a', label: a, fmt: 'num:1' }, { key: 'b', label: b, fmt: 'num:1' }], [
    { k: 'Powerplay runs (overs 1–6)', a: M.A.pp.mean, b: M.B.pp.mean }, { k: 'Wickets lost', a: M.A.wkts.mean, b: M.B.wkts.mean },
    { k: 'Score at fall of 1st wicket', a: M.A.fow1.mean, b: M.B.fow1.mean }, { k: 'Fours', a: M.A.fours.mean, b: M.B.fours.mean }, { k: 'Sixes', a: M.A.sixes.mean, b: M.B.sixes.mean },
    { k: 'Wides received', a: M.A.wides, b: M.B.wides }, { k: 'Extras received', a: M.A.extras, b: M.B.extras },
  ]);

  // line boxes
  const lineCard = (parent, title, note, pairs) => {
    const c = I.card(parent, title, note); const g = h('div', { class: 'ip-two' }); c.append(g);
    pairs.forEach(([lab, st, key, xl, step]) => { const box = h('div'); g.append(box); box.append(h('div', { class: 'ip-sub', text: lab })); I.distBox(box, st, { label: lab, xLabel: xl, line: isNum(lines[key]) ? lines[key] : null, step, onLine: L => setLine(key, L) }); });
    return c;
  };
  const c1 = h('div', { class: 'sh-cols' }); el.append(c1);
  lineCard(c1, 'Team totals', 'Each side\'s innings total (runs, incl. extras). A chasing side stops when it passes the target, so its total is capped by the chase. Type a line to price it.', [[a, M.A.total, 'ta', 'runs'], [b, M.B.total, 'tb', 'runs']]);
  lineCard(c1, 'Match total and first innings', 'Runs in both innings together, and the first-innings total whichever side bats first.', [['Match total', M.total, 'mt', 'runs', 2], ['1st innings', M.inn1, 'i1', 'runs']]);
  const c2 = h('div', { class: 'sh-cols' }); el.append(c2);
  lineCard(c2, 'Powerplay runs', 'Runs in overs 1–6 (whole innings if it ends sooner).', [[a, M.A.pp, 'pa', 'runs'], [b, M.B.pp, 'pb', 'runs']]);
  lineCard(c2, 'Fall of first wicket', 'Team score when the first wicket falls (the whole total if no wicket falls). Opening-partnership markets.', [[a, M.A.fow1, 'fa', 'runs'], [b, M.B.fow1, 'fb', 'runs']]);
  const c3 = h('div', { class: 'sh-cols' }); el.append(c3);
  lineCard(c3, 'Sixes', 'Sixes hit by each batting side in its innings' + (M.sixes ? ', and in the whole match.' : '.'), [[a, M.A.sixes, 'sa', 'sixes'], [b, M.B.sixes, 'sb', 'sixes']].concat(M.sixes ? [['Match', M.sixes, 'sm', 'sixes']] : []));
  lineCard(c3, 'Fours', 'Fours hit by each batting side in its innings' + (M.fours ? ', and in the whole match.' : '.'), [[a, M.A.fours, 'xa', 'fours'], [b, M.B.fours, 'xb', 'fours']].concat(M.fours ? [['Match', M.fours, 'xm', 'fours']] : []));

  if (M.margin) I.marginCard(el, M);

  // top batter / bowler
  const c4 = h('div', { class: 'sh-cols' }); el.append(c4);
  [['A', a], ['B', b]].forEach(([sd, ab]) => {
    const c = I.card(c4, `Top ${ab} batter and bowler`, 'P(his side\'s top run-scorer) and P(his side\'s top wicket-taker; fewest runs breaks ties). Dead heats are split, so each column sums to 100%.');
    const g = h('div', { class: 'ip-two' }); c.append(g);
    const tb = h('div'), tw2 = h('div'); g.append(tb, tw2);
    const bats = M[sd].players.filter(p => isNum(p.pTop)).sort((x, y) => y.pTop - x.pTop), bowls = M[sd].players.filter(p => p.bowl && isNum(p.bowl.pTop)).sort((x, y) => y.bowl.pTop - x.bowl.pTop);
    const draw = () => {
      S.table(tb, [{ key: 'n', label: 'Top batter', get: p => p.name }, { key: 'p', label: 'P', get: p => p.pTop, fmt: 'pct:1' }, { key: 'f', label: 'Fair', fmt: v => v ?? '', get: p => I.fp(p.pTop) }], bats.slice(0, 7));
      S.table(tw2, [{ key: 'n', label: 'Top bowler', get: p => p.name }, { key: 'p', label: 'P', get: p => p.bowl.pTop, fmt: 'pct:1' }, { key: 'f', label: 'Fair', fmt: v => v ?? '', get: p => I.fp(p.bowl.pTop) }], bowls);
      I.clickRows(tb, bats.slice(0, 7), p => I.openProp(M, sd, p.id, 'runs')); I.clickRows(tw2, bowls, p => I.openProp(M, sd, p.id, 'wkts'));
    };
    draw(); I.odds.bind(g, draw);
  });

  // player projections
  const c5 = I.card(el, 'Player projections', `Batting and bowling for both XIs from the same simulated matches. Runs columns: mean, median and 10th–90th percentile per innings (0 if he does not bat). Click a player for distributions, ladders and fair prices.${o.playersNote ? ' ' + o.playersNote : ''}`);
  [['A', a], ['B', b]].forEach(([sd, ab]) => {
    const pl = M[sd].players;
    const bat = pl.filter(p => p.pos != null).sort((x, y) => x.pos - y.pos), bowl = pl.filter(p => p.bowl).sort((x, y) => y.bowl.overs - x.bowl.overs);
    c5.append(h('div', { class: 'ip-sub', text: `${ab} batting` }));
    const t1 = h('div'); c5.append(t1);
    const q = (st, p) => st && st.q ? st.q[p] : null;
    const drawB = () => S.table(t1, [
      { key: 'pos', label: '#', get: p => p.pos, fmt: 'int' }, { key: 'n', label: 'Batter', get: p => p.name },
      { key: 'pb', label: 'P(bat)', get: p => p.pBat, fmt: 'pct:0', desc: 'Probability he gets to the crease' },
      { key: 'rm', label: 'Runs', get: p => p.runs && p.runs.mean, fmt: 'num:1', desc: 'Mean runs per innings' }, { key: 'md', label: 'Med', get: p => q(p.runs, 0.5), fmt: 'num:0', desc: 'Median runs' },
      { key: 'r10', label: '10–90%', fmt: v => v ?? '', get: p => p.runs && isNum(q(p.runs, 0.1)) ? `${F.num(q(p.runs, 0.1), 0)}–${F.num(q(p.runs, 0.9), 0)}` : '', desc: '10th to 90th percentile of runs' },
      { key: 'bl', label: 'Balls', get: p => p.balls && p.balls.mean, fmt: 'num:1' }, { key: 'f4', label: '4s', get: p => p.fours && p.fours.mean, fmt: 'num:2' }, { key: 's6', label: '6s', get: p => p.sixes && p.sixes.mean, fmt: 'num:2' },
      ...[10, 20, 30, 50].map(t => ({ key: 'p' + t, label: t + '+', get: p => p.pRuns && p.pRuns[t], fmt: 'pct:0', desc: `P(${t} or more runs)` })),
      { key: 'f30', label: '30+ fair', fmt: v => v ?? '', get: p => I.fp(p.pRuns && p.pRuns[30]), desc: 'Fair price, 30 or more runs' },
      { key: 'po', label: 'P(out)', get: p => p.pOut, fmt: 'pct:0', desc: 'P(dismissed); 1 − this − P(did not bat) = not out' }, { key: 'dk', label: 'Duck', get: p => p.pDuck, fmt: 'pct:1', desc: 'P(out for 0)' },
    ], bat);
    drawB(); I.odds.bind(t1, () => { drawB(); I.clickRows(t1, bat, p => I.openProp(M, sd, p.id, 'runs')); });
    I.clickRows(t1, bat, p => I.openProp(M, sd, p.id, 'runs'));
    c5.append(h('div', { class: 'ip-sub', text: `${ab} bowling` }));
    const t2 = h('div'); c5.append(t2);
    const drawW = () => S.table(t2, [
      { key: 'n', label: 'Bowler', get: p => p.name + (p.pos == null ? ' (Impact)' : '') }, { key: 'ov', label: 'Overs', fmt: v => v ?? '', get: p => I.oversF(p.bowl.overs), desc: 'Mean overs bowled (O.B)' },
      { key: 'wm', label: 'Wkts', get: p => p.bowl.wkts.mean, fmt: 'num:2', desc: 'Mean wickets (bowler\'s wickets; run outs excluded)' },
      ...[1, 2, 3].map(t => ({ key: 'w' + t, label: t + '+', get: p => p.bowl.pW[t], fmt: 'pct:0', desc: `P(${t} or more wickets)` })),
      { key: 'f2', label: '2+ fair', fmt: v => v ?? '', get: p => I.fp(p.bowl.pW[2]), desc: 'Fair price, 2 or more wickets' },
      { key: 'cm', label: 'Conceded', get: p => p.bowl.conceded.mean, fmt: 'num:1', desc: 'Mean runs conceded (incl. wides and no-balls)' }, { key: 'ec', label: 'Econ', get: p => p.bowl.econ, fmt: 'num:2', desc: 'Runs conceded per 6 legal balls (lower is better)' },
    ], bowl);
    drawW(); I.odds.bind(t2, () => { drawW(); I.clickRows(t2, bowl, p => I.openProp(M, sd, p.id, 'wkts')); });
    I.clickRows(t2, bowl, p => I.openProp(M, sd, p.id, 'wkts'));
  });
  return el;
};

/* ════════ winning margin ════════ */
const BANDS = {
  runs: [[1, 9], [10, 19], [20, 29], [30, 49], [50, 999]],
  wkts: [[1, 3], [4, 6], [7, 10]],
  balls: [[1, 6], [7, 12], [13, 24], [25, 999]],
};
const bandLab = ([lo, hi], unit) => hi >= 999 ? `${lo}+ ${unit}` : `${lo}–${hi} ${unit}`;
const pBand = (d, [lo, hi]) => d ? Math.max(0, d.pAtMost(hi) - d.pAtMost(lo - 1)) : null;
I.marginCard = (el, M) => {
  const G = M.margin, ab = { A: M.a.short, B: M.b.short };
  const tossTxt = M.batFirst ? `${ab[M.batFirst]} bats first in this view.` : 'Toss unknown: each side bats first in half the simulations, so every probability below already includes the 50% chance of that innings order.';
  const c = I.card(el, 'Winning margin', `How each side wins inside the 20 overs: batting first by runs, or chasing with wickets in hand and balls to spare. Probabilities are unconditional (they include the chance of winning that way at all), with no-vig fair prices. The rest of the probability is the other side winning, or a tie settled by the super over. ${tossTxt}`);
  c.classList.add('ip-wide');
  const g = h('div', { class: 'ip-two ip-two-wide' }); c.append(g);
  const tbls = [];
  ['A', 'B'].forEach(sd => {
    const m = G[sd]; if (!m) return;
    const box = h('div'); g.append(box);
    const rows = [];
    const pf = m.first && m.first.w ? m.first.w * (m.first.p || 0) : 0, pc = m.chase && m.chase.w ? m.chase.w * (m.chase.p || 0) : 0;
    if (m.first && m.first.w) { rows.push({ k: `Bat first, win by runs`, p: pf, strong: true }); BANDS.runs.forEach(bd => rows.push({ k: '  by ' + bandLab(bd, 'runs'), p: pf * pBand(m.first.runs, bd) })); }
    if (m.chase && m.chase.w) {
      rows.push({ k: `Chase, win by wickets`, p: pc, strong: true }); BANDS.wkts.forEach(bd => rows.push({ k: '  with ' + bandLab(bd, 'wkts') + ' left', p: pc * pBand(m.chase.wkts, bd) }));
      if (m.chase.balls) BANDS.balls.forEach(bd => rows.push({ k: '  with ' + bandLab(bd, 'balls') + ' to spare', p: pc * pBand(m.chase.balls, bd), alt: true }));
    }
    box.append(h('div', { class: 'ip-sub', text: `${ab[sd]} wins` }));
    const t = h('div'); box.append(t); tbls.push([t, rows]);
  });
  const drawT = () => tbls.forEach(([t, rows]) => S.table(t, [{ key: 'k', label: 'Outcome', render: (v, r) => r.strong ? `<b>${esc(v.trim())}</b>` : `<span class="${r.alt ? 'muted' : ''}">&nbsp;&nbsp;${esc(v.trim())}</span>` }, { key: 'p', label: 'P', fmt: 'pct:1' }, { key: 'f', label: 'Fair', fmt: v => v ?? '', get: r => I.fp(r.p) }], rows));
  drawT(); I.odds.bind(g, drawT);
  c.append(h('div', { class: 'sh-note ip-links' }, 'Wickets-left and balls-to-spare rows are two ways of splitting the same chasing wins (each set sums to the chase line). How well simulated margins match real ones: ', h('a', { href: I.hashFor('diag', { s: 'margins' }), text: 'Diagnostics, winning margins' }), '.'));
  // conditional distributions
  const opts = [];
  ['A', 'B'].forEach(sd => { const m = G[sd]; if (!m) return; if (m.first && m.first.w && m.first.runs) opts.push({ value: sd + '|runs', label: `${ab[sd]} by runs`, d: m.first.runs, x: 'runs', what: `${ab[sd]}'s margin in runs, given ${ab[sd]} bats first and wins` }); if (m.chase && m.chase.w && m.chase.wkts) opts.push({ value: sd + '|wkts', label: `${ab[sd]} by wkts`, d: m.chase.wkts, x: 'wickets in hand', what: `wickets in hand, given ${ab[sd]} chases and wins` }); if (m.chase && m.chase.w && m.chase.balls) opts.push({ value: sd + '|balls', label: `${ab[sd]} balls left`, d: m.chase.balls, x: 'balls to spare', what: `balls to spare, given ${ab[sd]} chases and wins` }); });
  if (!opts.length) return;
  const box = h('div', { class: 'sh-section' }); c.append(box);
  let cur = opts[0].value;
  const draw = () => {
    box.innerHTML = '';
    const o = opts.find(x => x.value === cur) || opts[0];
    box.append(S.ui.segmented({ label: 'Margin given the win', options: opts.map(x => ({ value: x.value, label: x.label })), value: o.value, onChange: v => { cur = v; draw(); } }));
    box.append(h('div', { class: 'sh-note', text: `Distribution of ${o.what} (conditional, so it sums to 100%). Use it for winning-margin lines quoted "if ${o.label.split(' ')[0]} wins".` }));
    const inner = h('div', { class: 'ip-two ip-two-wide' }); box.append(inner);
    const l = h('div'), r = h('div'); inner.append(l, r);
    I.distBox(l, Object.assign(statFromDist(o.d, M.source === 'in-browser simulation' ? 'sim' : 'export'), { file: M.source, nCond: null }), { label: o.label, xLabel: o.x, height: 110 });
    S.table(r, [{ key: 'q', label: 'Quantile' }, { key: 'v', label: o.x, fmt: 'num:0' }], [0.1, 0.25, 0.5, 0.75, 0.9].map(p => ({ q: (p * 100) + '%', v: o.d.quantile(p) })));
  };
  draw();
};

/* ════════ prop drawer ════════ */
I.statPanel = (el, st, o = {}) => {
  el.innerHTML = '';
  if (!st) { el.append(h('div', { class: 'sh-note', text: 'No projection for this stat (he does not bat or bowl in this XI).' })); return; }
  const qv = p => st.q && st.q[p] != null ? st.q[p] : st.dist ? st.dist.quantile(p) : null;
  el.append(S.tiles([
    { label: 'Mean', value: F.num(st.mean, o.key === 'wkts' ? 2 : 1), sub: isNum(st.sd) ? 'sd ' + F.num(st.sd, 1) : (st.dist ? 'sd ' + F.num(st.dist.sd, 1) : '') },
    { label: 'Median', value: F.num(qv(0.5), 0), sub: `10–90%: ${F.num(qv(0.1), 0)}–${F.num(qv(0.9), 0)}` },
    { label: 'P(0)', value: F.pct(st.dist.pAtMost(0), 1), sub: o.key === 'wkts' ? 'wicketless' : 'zero (incl. no bat)' },
  ]));
  const g = h('div', { class: 'ip-statgrid' }); el.append(g);
  const left = h('div'), hh = h('div'); left.append(hh); g.append(left);
  const d = st.dist, top = Math.max(3, d.quantile(0.997));
  const chart = S.histogram(hh, { dist: d, xDomain: [-0.5, top + 0.5], height: 130, xLabel: o.short || '', maxBars: 160 });
  const pr = h('div'); g.append(pr);
  const L0 = isNum(o.line) ? o.line : Math.max(0.5, I.fairLine(d, st.mean));
  I.linePricer(pr, { dist: d, line: L0, step: o.key === 'runs' || o.key === 'conceded' || o.key === 'balls' ? 5 : 1, rows: 4, min: 0.5, label: o.short || 'Line', inputLabel: (o.label || '') + ' line', ladderNote: false, note: esc(I.srcNote(st)),
    onLine: L => { chart.update({ split: L, markers: I.markers(d, L) }); if (o.onLine) o.onLine(L); } });
  const qt = h('div', { style: { marginTop: '10px' } }); left.append(qt);
  S.table(qt, [{ key: 'k', label: 'Quantile' }].concat([0.1, 0.25, 0.5, 0.75, 0.9].map(p => ({ key: 'q' + p, label: (p * 100) + '%', fmt: 'num:0', get: () => qv(p) }))), [{ k: o.label || '' }]);
};
I.openProp = (M, sd, id, key) => {
  const list = [...M.A.players.map(p => ['A', p]), ...M.B.players.map(p => ['B', p])];
  const pos = list.findIndex(r => r[0] === sd && r[1].id === id); if (pos < 0) return;
  const p = list[pos][1], team = M[sd].team, opp = sd === 'A' ? M.b : M.a;
  const avail = I.STATS.filter(([k]) => I.statOf(p, k));
  let cur = avail.some(x => x[0] === key) ? key : (avail[0] || ['runs'])[0];
  const role = [p.pos != null ? `bats ${p.pos}` : 'Impact Player (does not bat)', p.bowl ? `bowls ${I.oversF(p.bowl.overs)} overs` : null].filter(Boolean).join(', ');
  S.drawer.open({
    title: p.name, sub: `${team.short} v ${opp.short} · ${role}${isNum(p.pTop) ? ' · top-scorer ' + F.pct(p.pTop, 1) : ''}`,
    keepScroll: true,
    nav: { prev: () => { const r = list[Math.max(0, pos - 1)]; I.openProp(M, r[0], r[1].id, cur); }, next: () => { const r = list[Math.min(list.length - 1, pos + 1)]; I.openProp(M, r[0], r[1].id, cur); } },
    body: el => {
      const panel = h('div', { class: 'sh-section' });
      const seg = S.ui.segmented({ options: avail.map(([k, , s]) => ({ value: k, label: s })), value: cur, onChange: v => { cur = v; draw(); } });
      const draw = () => { const m = I.STATS.find(x => x[0] === cur); I.statPanel(panel, I.statOf(p, cur), { key: cur, label: m[1], short: m[2] }); };
      el.append(seg, panel); draw();
      const extra = [];
      if (isNum(p.pTop)) extra.push(['Top team batter', `${F.pct(p.pTop, 1)} · fair ${I.fp(p.pTop)}`]);
      if (p.bowl && isNum(p.bowl.pTop)) extra.push(['Top team bowler', `${F.pct(p.bowl.pTop, 1)} · fair ${I.fp(p.bowl.pTop)}`]);
      if (isNum(p.pBat)) extra.push(['P(bats)', F.pct(p.pBat, 1)], ['P(out)', F.pct(p.pOut, 1)], ['P(duck)', F.pct(p.pDuck, 1)]);
      if (p.bowl) extra.push(['Economy', F.num(p.bowl.econ, 2) + ' per over']);
      if (extra.length) el.append(S.kv(extra, { cols: 2 }));
      el.append(h('div', { class: 'sh-note ip-links' }, h('a', { href: '#', text: 'Open his player card', onclick: e => { e.preventDefault(); I.playerCard && I.playerCard(p.id); } })));
    },
  });
};
})();
