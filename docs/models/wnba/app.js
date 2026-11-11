/* WNBA workbook: shared data access, distributions and renderers (window.WNBA).
   sheets.js builds the workbook on top of this. Reads the exports defensively: compact or schema-form
   matchup arrays, sim.js objects, and optional fields added by later model passes. */
(function () {
'use strict';
const S = Sheets, h = S.h, esc = S.esc, F = S.fmt;
const W = window.WNBA = {};
const isNum = v => typeof v === 'number' && isFinite(v);
W.isNum = isNum;

/* ════════ odds mode (American default, decimal toggle) ════════ */
let oddsMode = 'american';
try { const m = localStorage.getItem('wnba.odds'); if (m === 'decimal' || m === 'american') oddsMode = m; } catch (e) { /* storage blocked */ }
const oddsViews = [];
W.odds = {
  get mode() { return oddsMode; },
  set(m) {
    if (m === oddsMode) return;
    oddsMode = m; try { localStorage.setItem('wnba.odds', m); } catch (e) { /* ignore */ }
    for (let i = oddsViews.length - 1; i >= 0; i--) {
      const v = oddsViews[i];
      if (!v.el.isConnected) { oddsViews.splice(i, 1); continue; }
      try { v.fn(m); } catch (e) { console.error(e); }
    }
  },
  /** re-run fn when the odds mode changes, for as long as el stays in the document */
  bind(el, fn) { oddsViews.push({ el, fn }); },
};
/** fair price for probability p in the current odds format */
W.fp = p => !(p > 0 && p < 1) ? '–' : oddsMode === 'decimal' ? F.dec(p, 2) : F.american(p);
W.oddsWord = () => oddsMode === 'decimal' ? 'decimal' : 'American';

/* ════════ data ════════ */
const D = W.D = { M: null };
W.loadCore = () => W._core || (W._core = S.load.all({ P: 'data/players.json', T: 'data/teams.json' }).then(({ P, T }) => {
  D.players = (P.players || []).slice();
  D.valueMeta = P.value_meta || {};
  D.lgXpts = P.league_xpts_per_shot;
  D.teams = (T.teams || []).slice();
  D.lgORtg = T.league_ortg;
  D.pById = new Map(D.players.map(p => [p.id, p]));
  D.tById = new Map(D.teams.map(t => [t.id, t]));
  D.tByAbbr = new Map(D.teams.map(t => [t.abbr, t]));
  // rank by total impact among percentile-qualified players
  const q = D.players.filter(p => p.qualified_for_pct && isNum(p.impact && p.impact.total)).sort((a, b) => b.impact.total - a.impact.total);
  q.forEach((p, i) => { p._rank = i + 1; });
  D.nQualified = q.length;
  D.players.forEach(p => { p._proj = projLineFromPlayer(p); p._act = actLineFromPlayer(p); });
  return D;
}));
W.loadMatchups = () => W._m || (W._m = S.load('data/matchups.json').then(m => {
  D.M = m; D.lineStep = m.line_step || {};
  D.games = new Map();
  if (!D.players.some(p => p._proj && p._proj.src === 'players.json')) projLinesFromMatchups(m);
  return m;
}));
W.loadSimParams = () => S.load('data/sim_params.json');
W.loadDiag = () => S.load('data/diagnostics.json');
W.team = id => D.tById.get(+id) || D.tByAbbr.get(id) || null;
W.abbr = id => { const t = W.team(id); return t ? t.abbr : 'FA'; };
W.player = id => D.pById.get(+id) || null;

/* per-game lines: projected (players.json if a later export adds it, else mean over matchups.json) and 2026 actual */
const LINE_KEYS = {
  min: ['min', 'mpg', 'minutes'], pts: ['pts', 'ppg', 'points'], reb: ['reb', 'rpg', 'trb'], ast: ['ast', 'apg'],
  fg3m: ['fg3m', 'fg3', '3pm', 'tpm', 'fg3m_pg', 'threes'], stl: ['stl', 'spg'], blk: ['blk', 'bpg'], tov: ['tov', 'to', 'topg'],
  pra: ['pra'], gp: ['gp', 'games', 'g'],
};
function readLine(o) {
  if (!o || typeof o !== 'object') return null;
  const out = {}; let any = false;
  for (const k in LINE_KEYS) for (const a of LINE_KEYS[k]) {
    let v = o[a]; if (Array.isArray(v)) v = v[0]; else if (v && typeof v === 'object') v = v.mean ?? v.p ?? v.value;
    if (isNum(v)) { out[k] = v; any = true; break; }
  }
  if (any && !isNum(out.pra) && isNum(out.pts) && isNum(out.reb) && isNum(out.ast)) out.pra = out.pts + out.reb + out.ast;
  return any ? out : null;
}
function projLineFromPlayer(p) {
  for (const k of Object.keys(p)) if (/^(proj|projected)_?(line|box|per_game|pg|game)|^line_proj|^proj_2027/i.test(k)) { const l = readLine(p[k]); if (l) return Object.assign(l, { src: 'players.json' }); }
  return null;
}
function actLineFromPlayer(p) {
  for (const k of Object.keys(p)) if (/^(actual|act)_?(2026|line|box|per_game)|^line_2026|^2026_actual|^box_2026_full/i.test(k)) { const l = readLine(p[k]); if (l) return Object.assign(l, { src: k }); }
  const l = readLine(p.box_2026); return l ? Object.assign(l, { src: 'box_2026' }) : null;
}
function projLinesFromMatchups(m) {
  const acc = new Map(), keys = ['min', 'pts', 'reb', 'ast', 'fg3m', 'stl', 'blk', 'tov', 'pra'];
  for (const k in m.pairs) {
    const mu = m.pairs[k];
    for (const x of (mu.home_players || []).concat(mu.away_players || [])) {
      let a = acc.get(x.id); if (!a) acc.set(x.id, a = { n: 0 });
      a.n++;
      for (const s of keys) { const v = x[s]; const mean = Array.isArray(v) ? v[0] : v && v.mean; if (isNum(mean)) a[s] = (a[s] || 0) + mean; }
    }
  }
  for (const [id, a] of acc) {
    const p = D.pById.get(id); if (!p) continue;
    const l = { src: 'matchups.json', games: a.n }; keys.forEach(s => { if (isNum(a[s])) l[s] = a[s] / a.n; });
    p._proj = l;
  }
}

/* ════════ distributions ════════ */
const QS7 = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95], QS5 = [0.1, 0.25, 0.5, 0.75, 0.9];
const DEFAULT_STEP = { min: 2, pts: 2, reb: 1, ast: 1, fg3m: 1, stl: 1, blk: 1, tov: 1, pra: 2, pr: 2, pa: 2 };
function qPairs(q) {
  if (!Array.isArray(q) || !q.length) return [];
  const ps = q.length === 7 ? QS7 : q.length === 5 ? QS5 : q.map((_, i) => (i + 1) / (q.length + 1));
  return q.map((v, i) => [ps[i], v]);
}
W.qAt = (st, p) => { const f = st && st.q && st.q.find(x => Math.abs(x[0] - p) < 1e-9); return f ? f[1] : null; };
function erf(x) { const t = 1 / (1 + 0.3275911 * Math.abs(x)); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y; }
const Phi = z => 0.5 * (1 + erf(z / Math.SQRT2));
W.Phi = Phi;
/** P(X <= k), k = 0..K, for a count with this mean/sd: negative binomial when over-dispersed, else a discretised normal */
function baseCdf(m, s, K) {
  const P = new Float64Array(K + 1);
  if (!(m > 0)) P[0] = 1;
  else {
    const v = s * s;
    if (v > m * 1.05) {
      const r = m * m / (v - m), q = r / (r + m); let p = Math.exp(r * Math.log(q)); P[0] = p;
      for (let k = 0; k < K; k++) { p = p * (k + r) / (k + 1) * (1 - q); P[k + 1] = p; }
    } else {
      const sd = Math.max(s || Math.sqrt(m), 0.35);
      for (let k = 0; k <= K; k++) P[k] = Phi((k + 0.5 - m) / sd) - (k === 0 ? 0 : Phi((k - 0.5 - m) / sd));
    }
  }
  let c = 0; const Fc = new Float64Array(K + 1); for (let k = 0; k <= K; k++) { c += P[k]; Fc[k] = c; }
  for (let k = 0; k <= K; k++) Fc[k] /= c || 1;
  return Fc;
}
/** pmf on 0..K whose CDF passes exactly through the simulated P(over line) points and follows the fitted shape between them */
function anchoredPmf(m, s, lines, po) {
  let K = Math.ceil(Math.max(m + 7 * (s || 1) + 5, 4)); for (const l of lines) K = Math.max(K, Math.ceil(l) + 6);
  const F0 = baseCdf(m, s, K);
  let A = lines.map((l, i) => ({ k: Math.floor(l + 1e-9), T: 1 - po[i] })).filter(a => a.k >= 0 && a.k <= K && isNum(a.T)).sort((a, b) => a.k - b.k);
  let mx = 0; A = A.filter((a, i) => { if (i && a.k === A[i - 1].k) return false; a.T = Math.min(1, Math.max(mx, a.T)); mx = a.T; return true; });
  const Fx = new Float64Array(K + 1);
  if (!A.length) Fx.set(F0);
  else {
    const first = A[0], last = A[A.length - 1]; let i = 0;
    for (let k = 0; k <= K; k++) {
      if (k <= first.k) Fx[k] = F0[first.k] > 1e-12 ? F0[k] * first.T / F0[first.k] : first.T * (k + 1) / (first.k + 1);
      else if (k >= last.k) { const rem = 1 - F0[last.k]; Fx[k] = rem > 1e-12 ? 1 - (1 - F0[k]) * (1 - last.T) / rem : 1; }
      else {
        while (A[i + 1].k < k) i++;
        const a = A[i], b = A[i + 1], d = F0[b.k] - F0[a.k];
        Fx[k] = a.T + (d > 1e-12 ? (F0[k] - F0[a.k]) / d : (k - a.k) / (b.k - a.k)) * (b.T - a.T);
      }
    }
  }
  Fx[K] = 1;
  const pmf = new Float64Array(K + 1); let prev = 0;
  for (let k = 0; k <= K; k++) { const v = Math.max(prev, Math.min(1, Fx[k])); pmf[k] = v - prev; prev = v; }
  return pmf;
}
function mixDist(st) {
  const comps = st.comps && st.comps.length ? st.comps : [{ w: 1, mean: st.mean, sd: st.sd, lines: [], po: [] }];
  const acc = [];
  for (const c of comps) { const p = anchoredPmf(c.mean, c.sd, c.lines || [], c.po || []); for (let k = 0; k < p.length; k++) acc[k] = (acc[k] || 0) + c.w * p[k]; }
  return S.dist.fromPmf(acc.map((p, k) => [k, p || 0]));
}
function mkStat(mean, sd, q, comps) {
  const st = { mean, sd, q: qPairs(q), comps: comps || [] };
  let d = null;
  Object.defineProperty(st, 'dist', { get() { return d || (d = mixDist(st)); } });
  st.median = W.qAt(st, 0.5);
  st.exactLines = [...new Set(st.comps.flatMap(c => c.lines || []))].sort((a, b) => a - b);
  return st;
}
/** stat from matchups.json (compact [mean, sd, q5, first_line, p_over[]] or schema [mean, sd, q7, lines[], p_over[]]) or a sim.js object */
function statFrom(x, key) {
  if (x == null) return null;
  if (typeof x === 'number') return mkStat(x, null, [], []);
  if (Array.isArray(x)) {
    const [mean, sd, q, a3, po] = x;
    let lines = [];
    if (Array.isArray(a3)) lines = a3;
    else if (isNum(a3)) { const step = (D.lineStep && D.lineStep[key]) || DEFAULT_STEP[key] || 1; lines = (po || []).map((_, i) => +(a3 + i * step).toFixed(4)); }
    return mkStat(mean, sd, q, [{ w: 1, mean, sd, lines, po: po || [] }]);
  }
  return mkStat(x.mean, x.sd, x.q, x.comps || [{ w: 1, mean: x.mean, sd: x.sd, lines: x.lines || [], po: x.p_over || [] }]);
}
W.normalDist = (mean, sd, lo, hi) => {
  lo = lo ?? Math.max(0, Math.floor(mean - 6 * sd)); hi = hi ?? Math.ceil(mean + 6 * sd);
  const rows = []; for (let k = lo; k <= hi; k++) rows.push([k, Phi((k + 0.5 - mean) / sd) - Phi((k - 0.5 - mean) / sd)]);
  return S.dist.fromPmf(rows);
};

/* ════════ games ════════ */
W.STATS = ['min', 'pts', 'reb', 'ast', 'fg3m', 'stl', 'blk', 'tov', 'pra', 'pr', 'pa'];
W.STAT_LABEL = { min: 'Minutes', pts: 'Points', reb: 'Rebounds', ast: 'Assists', fg3m: '3-pointers made', stl: 'Steals', blk: 'Blocks', tov: 'Turnovers', pra: 'Pts+Reb+Ast', pr: 'Pts+Reb', pa: 'Pts+Ast' };
W.STAT_SHORT = { min: 'Min', pts: 'Pts', reb: 'Reb', ast: 'Ast', fg3m: '3PM', stl: 'Stl', blk: 'Blk', tov: 'TOV', pra: 'PRA', pr: 'P+R', pa: 'P+A' };
const sumOf = x => !x ? null : Array.isArray(x) ? { mean: x[0], sd: x[1], q: qPairs(x[2]) } : { mean: x.mean, sd: x.sd, q: qPairs(x.q) };
function histOf(hh) {
  let lo, p; if (Array.isArray(hh)) { lo = hh[0]; p = hh[1]; } else if (hh) { lo = hh.lo; p = hh.p; }
  return Array.isArray(p) ? S.dist.fromPmf(p.map((v, i) => [lo + i, v])) : null;
}
function periodOf(x) {
  if (Array.isArray(x)) return { home: x[0], away: x[1], homeWin: x[2], tie: x[3], marginSd: x[4], totalSd: x[5], marginMean: x[0] - x[1], totalMean: x[0] + x[1] };
  return { home: x.home, away: x.away, homeWin: x.home_win, tie: x.tie, marginSd: x.margin_sd, totalSd: x.total_sd, marginMean: x.margin_mean ?? (x.home - x.away), totalMean: x.total_mean ?? (x.home + x.away) };
}
function canonPlayer(x) {
  const p = D.pById.get(x.id), st = {};
  W.STATS.forEach(k => { if (x[k] != null) st[k] = statFrom(x[k], k); });
  return { id: x.id, name: x.name || (p && p.name) || String(x.id), pos: p ? p.pos_group : '', projMin: x.min_proj ?? x.proj_min, out: !!x.out, stats: st, fga: x.fga, fg3a: x.fg3a, fta: x.fta, pDD: x.p_dd };
}
/** canonical game object from matchups.json `game` or sim.js `game` (+ player arrays) */
W.canonGame = (g, homePl, awayPl, hId, aId) => {
  const G = {
    hId: +hId, aId: +aId, n: g.n_sims || (D.M && D.M.n_sims) || null,
    homeWin: g.home_win, pOT: g.p_ot, poss: g.poss ?? g.poss_per_team,
    margin: sumOf(g.margin), total: sumOf(g.total), homePts: sumOf(g.home_pts), awayPts: sumOf(g.away_pts),
    quarters: (g.quarters || []).map(periodOf), halves: (g.halves || []).map(periodOf),
    home: (homePl || []).map(canonPlayer), away: (awayPl || []).map(canonPlayer),
  };
  G.marginDist = histOf(g.margin_hist) || W.normalDist(G.margin.mean, G.margin.sd, -60, 60);
  G.totalDist = histOf(g.total_hist) || W.normalDist(G.total.mean, G.total.sd);
  return G;
};
W.game = (hId, aId) => {
  const key = hId + '_' + aId;
  if (D.games.has(key)) return D.games.get(key);
  const mu = D.M && D.M.pairs[key]; if (!mu) return null;
  const G = W.canonGame(mu.game, mu.home_players, mu.away_players, mu.home ?? hId, mu.away ?? aId);
  G.source = 'matchups.json';
  D.games.set(key, G); return G;
};
/** pool sim.js results from several chunks (same rosters) into one sim.js-shaped result */
W.mergeRuns = parts => {
  const N = parts.reduce((a, p) => a + p.game.n_sims, 0), w = parts.map(p => p.game.n_sims / N);
  const wav = f => parts.reduce((a, p, i) => a + w[i] * f(p), 0);
  const pool = (fm, fs) => { let m = 0, e2 = 0; parts.forEach((p, i) => { const a = fm(p), b = fs(p); m += w[i] * a; e2 += w[i] * (b * b + a * a); }); return [m, Math.sqrt(Math.max(0, e2 - m * m))]; };
  const wq = f => f(parts[0]).map((_, k) => wav(p => f(p)[k]));
  const hist = key => { const h0 = parts[0].game[key]; return { lo: h0.lo, hi: h0.hi, p: h0.p.map((_, k) => wav(p => p.game[key].p[k])) }; };
  const g0 = parts[0].game, game = { n_sims: N, home_win: wav(p => p.game.home_win), p_ot: wav(p => p.game.p_ot), poss_per_team: wav(p => p.game.poss_per_team) };
  game.margin_hist = hist('margin_hist'); game.total_hist = hist('total_hist');
  for (const k of ['margin', 'total', 'home_pts', 'away_pts']) {
    const [m, s] = pool(p => p.game[k].mean, p => p.game[k].sd);
    let q = wq(p => p.game[k].q);
    if (k === 'margin' || k === 'total') { const d = histOf(game[k + '_hist']); q = QS7.map(x => d.quantile(x)); }
    game[k] = { mean: m, sd: s, q };
  }
  game.quarters = g0.quarters.map((_, j) => {
    const Q = p => p.game.quarters[j];
    return { home: wav(p => Q(p).home), away: wav(p => Q(p).away), home_win: wav(p => Q(p).home_win), tie: wav(p => Q(p).tie),
      margin_sd: pool(p => Q(p).home - Q(p).away, p => Q(p).margin_sd)[1], total_sd: pool(p => Q(p).home + Q(p).away, p => Q(p).total_sd)[1] };
  });
  game.halves = g0.halves.map((_, j) => {
    const Hh = p => p.game.halves[j];
    const mm = pool(p => Hh(p).margin_mean, p => Hh(p).margin_sd), tt = pool(p => Hh(p).total_mean, p => Hh(p).total_sd);
    return { home: wav(p => Hh(p).home), away: wav(p => Hh(p).away), home_win: wav(p => Hh(p).home_win), tie: wav(p => Hh(p).tie), margin_mean: mm[0], margin_sd: mm[1], total_mean: tt[0], total_sd: tt[1] };
  });
  const side = s => parts[0][s].map((pl, i) => {
    const rec = { id: pl.id, name: pl.name, proj_min: pl.proj_min, out: pl.out };
    for (const k of W.STATS) {
      const g = p => p[s][i][k];
      const [m, sd] = pool(p => g(p).mean, p => g(p).sd);
      rec[k] = { mean: m, sd, q: wq(p => g(p).q), comps: parts.map((p, j) => ({ w: w[j], mean: g(p).mean, sd: g(p).sd, lines: g(p).lines, po: g(p).p_over })) };
    }
    rec.fga = wav(p => p[s][i].fga); rec.fg3a = wav(p => p[s][i].fg3a); rec.fta = wav(p => p[s][i].fta); rec.p_dd = wav(p => p[s][i].p_dd);
    return rec;
  });
  return { game, home: side('home'), away: side('away'), meta: Object.assign({}, parts[0].meta, { n_sims: N }) };
};

/* ════════ small helpers ════════ */
W.card = (parent, title, note, cls) => {
  const c = h('div', { class: 'sh-card' + (cls ? ' ' + cls : '') });
  if (title) c.append(h('div', { class: 'sh-h', text: title }));
  if (note) c.append(h('div', { class: 'sh-note', html: note }));
  if (parent) parent.append(c);
  return c;
};
W.go = (sheet, params) => W.wb.activate(sheet, { params: params || {}, push: true });
W.hashFor = (sheet, params) => '#sheet=' + sheet + Object.entries(params || {}).filter(([, v]) => v != null && v !== '').map(([k, v]) => '&' + encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('');
W.signed = (v, dp = 1) => F.signed(v, dp);
W.halfLine = v => Math.floor(v) + 0.5;
W.fmtLine = v => F.num(v, Number.isInteger(v) ? 0 : 1);
W.spreadText = (abbr, s) => `${abbr} ${s > 0 ? '+' : s < 0 ? '−' : ''}${F.num(Math.abs(s), Number.isInteger(s) ? 0 : 1)}`;
W.heightText = v => { if (!isNum(v)) return ''; const t = Math.round(v); return `${Math.floor(t / 12)}′${t % 12}″`; };
/** half-point line whose P(over) is closest to 0.5 (searching ±25 around the mean) */
W.fairLine = (d, center, step = 1) => {
  let best = null, bd = 9; const c0 = Math.floor(center) + 0.5;
  for (let k = -25; k <= 25; k++) { const L = c0 + k * step; const v = Math.abs(d.pOver(L) - 0.5); if (v < bd) { bd = v; best = L; } }
  return best;
};

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
function niceStep(span, n) { const s0 = span / Math.max(1, n); const mag = 10 ** Math.floor(Math.log10(s0)); const e = s0 / mag; return (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag; }
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

/** Waterfall: start → +each item → total (horizontal, one row per item). items [{label, value, desc, id}] */
W.waterfall = (el, o) => chartBase(el, (el, Wd) => {
  const f = F.make(o.fmt || 'signed:2');
  const rows = []; let cum = o.start || 0;
  rows.push({ label: o.startLabel || 'Start', v0: cum, v1: cum, kind: 'start' });
  o.items.forEach(it => { rows.push({ label: it.label, v0: cum, v1: cum + it.value, value: it.value, desc: it.desc, kind: 'item', it }); cum += it.value; });
  rows.push({ label: o.endLabel || 'Total', v0: o.start || 0, v1: cum, kind: 'total', value: cum });
  let lo = Math.min(...rows.map(r => Math.min(r.v0, r.v1))), hi = Math.max(...rows.map(r => Math.max(r.v0, r.v1)));
  const pad = (hi - lo) * 0.04 || 1; lo -= pad; hi += pad;
  const labW = Math.min(Wd * 0.36, Math.max(...rows.map(r => tw(r.label, 11.5))) + 10), valW = 46;
  const bh = 14, gap = 6, band = bh + gap, mt = 4, Hh = rows.length * band, ml = labW + 6, mr = valW;
  const x = v => ml + (v - lo) / (hi - lo) * (Wd - ml - mr);
  const tk = ticks(lo, hi, Math.max(2, Math.floor((Wd - ml - mr) / 70)));
  let s = `<svg width="${Wd}" height="${mt + Hh + 22}" role="img" aria-label="${esc(o.title || 'Waterfall')}"><g class="gr">`;
  for (const t of tk) s += `<line x1="${x(t).toFixed(1)}" x2="${x(t).toFixed(1)}" y1="${mt}" y2="${mt + Hh}"/>`;
  s += '</g>';
  rows.forEach((r, k) => {
    const y = mt + k * band + gap / 2, strong = r.kind !== 'item';
    s += `<text class="${strong ? 'lab-s' : 'lab'}" x="${labW}" y="${y + bh / 2}" dy="0.32em" text-anchor="end">${esc(r.label)}</text>`;
    if (r.kind === 'start') s += `<line class="wn-tick" x1="${x(r.v0)}" x2="${x(r.v0)}" y1="${y - 1}" y2="${y + bh + 1}"/>`;
    else s += `<path class="bar ${r.kind === 'total' ? 'f1' : r.value >= 0 ? 'fpos' : 'fneg'}" data-k="${k}" d="${hb(x(r.v0), x(r.v1), y, bh)}"/>`;
    if (k < rows.length - 1 && r.kind !== 'total') { const nx = rows[k + 1]; if (nx.kind === 'item') s += `<line class="wn-conn" x1="${x(r.v1)}" x2="${x(r.v1)}" y1="${y + bh}" y2="${y + band}"/>`; }
    if (r.kind !== 'start') { const right = Math.max(r.v0, r.v1); s += `<text class="${strong ? 'lab-s' : 'lab'}" x="${x(right) + 5}" y="${y + bh / 2}" dy="0.32em">${esc(f(r.value))}</text>`; }
    s += `<rect class="hit" data-k="${k}" x="0" y="${y - gap / 2}" width="${Wd}" height="${band}"/>`;
  });
  s += `<g class="ax"><line x1="${x(o.start || 0)}" x2="${x(o.start || 0)}" y1="${mt}" y2="${mt + Hh}"/>`;
  let lastR = -1e9; for (const t of tk) { const px = x(t), lab = F.make(o.tickFmt || o.fmt || 'signed:0')(t); if (px - tw(lab, 10.5) / 2 < lastR + 6) continue; lastR = px + tw(lab, 10.5) / 2; s += `<text x="${px.toFixed(1)}" y="${mt + Hh + 15}" text-anchor="middle">${esc(lab)}</text>`; }
  s += '</g></svg>';
  el.innerHTML = titleHtml(o) + s;
  const svg = el.querySelector('svg');
  hover(svg, '[data-k]', t => { const r = rows[+t.dataset.k]; if (r.kind === 'start') return S.tip.html(r.label, [{ value: f(r.v0), label: 'baseline' }]); return S.tip.html(r.label, [{ value: f(r.value), label: r.kind === 'total' ? 'sum' : 'contribution' }].concat(r.kind === 'item' ? [{ value: f(r.v1), label: 'running total' }] : []), r.desc); });
  if (o.onClick) svg.addEventListener('click', e => { const t = e.target.closest('[data-k]'); if (t) { const r = rows[+t.dataset.k]; if (r.it) o.onClick(r.it); } });
});

/** Dot-and-whisker rows: [{label, v, sd, marks:[{v, label, kind:'ring'|'tick'}]}]; whisker = 90% interval, thick bar = ±1 SD */
W.intervals = (el, o) => chartBase(el, (el, Wd) => {
  const rows = o.rows.filter(r => isNum(r.v));
  let lo = -2, hi = 2; rows.forEach(r => { lo = Math.min(lo, r.v - 1.645 * (r.sd || 0)); hi = Math.max(hi, r.v + 1.645 * (r.sd || 0)); (r.marks || []).forEach(k => { if (isNum(k.v)) { lo = Math.min(lo, k.v); hi = Math.max(hi, k.v); } }); });
  lo = Math.floor(lo - 0.5); hi = Math.ceil(hi + 0.5);
  const labW = Math.max(...rows.map(r => tw(r.label, 11.5))) + 10, valW = 82, rh = 26, mt = 6, Hh = rows.length * rh;
  const x = v => labW + (v - lo) / (hi - lo) * (Wd - labW - valW);
  const tk = ticks(lo, hi, Math.max(3, Math.floor((Wd - labW - valW) / 55)));
  let s = `<svg width="${Wd}" height="${mt + Hh + 22}" role="img" aria-label="${esc(o.title || 'Ratings with uncertainty')}"><g class="gr">`;
  tk.forEach(t => { s += `<line x1="${x(t).toFixed(1)}" x2="${x(t).toFixed(1)}" y1="${mt}" y2="${mt + Hh}"/>`; });
  s += `</g><g class="ax"><line x1="${x(0)}" x2="${x(0)}" y1="${mt}" y2="${mt + Hh}"/>`;
  tk.forEach(t => { s += `<text x="${x(t).toFixed(1)}" y="${mt + Hh + 15}" text-anchor="middle">${esc(F.signed(t, 0) || '0')}</text>`; });
  s += '</g>';
  rows.forEach((r, k) => {
    const cy = mt + k * rh + rh / 2;
    s += `<text class="lab-s" x="${labW - 8}" y="${cy}" dy="0.32em" text-anchor="end">${esc(r.label)}</text>`;
    if (r.sd) {
      s += `<line class="wn-whisk" x1="${x(r.v - 1.645 * r.sd)}" x2="${x(r.v + 1.645 * r.sd)}" y1="${cy}" y2="${cy}"/>`;
      s += `<rect class="wn-sdbar" x="${x(r.v - r.sd)}" y="${cy - 4}" width="${Math.max(1, x(r.v + r.sd) - x(r.v - r.sd))}" height="8" rx="2"/>`;
    }
    (r.marks || []).forEach(mk => { if (!isNum(mk.v)) return; s += mk.kind === 'tick' ? `<line class="wn-tick" x1="${x(mk.v)}" x2="${x(mk.v)}" y1="${cy - 8}" y2="${cy + 8}"/>` : `<circle class="wn-ring" cx="${x(mk.v)}" cy="${cy}" r="4"/>`; });
    s += `<circle class="dot f1" cx="${x(r.v)}" cy="${cy}" r="5"/>`;
    s += `<text class="lab" x="${Wd - valW + 6}" y="${cy}" dy="0.32em">${esc(F.signed(r.v, 1) + (r.sd ? ' ± ' + F.num(r.sd, 1) : ''))}</text>`;
    s += `<rect class="hit" data-k="${k}" x="0" y="${cy - rh / 2}" width="${Wd}" height="${rh}"/>`;
  });
  s += '</svg>';
  el.innerHTML = titleHtml(o) + s + (o.legend ? `<div class="sh-note wn-legend">${o.legend}</div>` : '');
  const svg = el.querySelector('svg');
  hover(svg, '[data-k]', t => { const r = rows[+t.dataset.k]; return S.tip.html(r.label, [{ value: F.signed(r.v, 2), label: 'estimate (per 100)', key: 'b1' }].concat(r.sd ? [{ value: F.num(r.sd, 2), label: 'posterior SD' }, { value: `${F.signed(r.v - 1.645 * r.sd, 1)} to ${F.signed(r.v + 1.645 * r.sd, 1)}`, label: '90% interval' }] : []).concat((r.marks || []).filter(m => isNum(m.v)).map(m => ({ value: F.signed(m.v, 2), label: m.label })))); });
});

/** Shot zones: per zone a mix bar and an FG% bar, each with a league-average tick and printed values */
W.zoneChart = (el, o) => chartBase(el, (el, Wd) => {
  const Z = o.zones, labW = 92, gap = 18, rh = 24, mt = 20, Hh = Z.length * rh;
  const pw = (Wd - labW - gap) / 2, mixMax = Math.max(0.5, ...Z.map(z => Math.max(z.mix || 0, z.lgMix || 0))) * 1.05, fgMax = 0.85;
  const x1 = v => labW + v / mixMax * (pw - 40), x2 = v => labW + pw + gap + v / fgMax * (pw - 40);
  let s = `<svg width="${Wd}" height="${mt + Hh + 6}" role="img" aria-label="Shot zones"><text class="al" x="${labW}" y="11">Share of FGA</text><text class="al" x="${labW + pw + gap}" y="11">FG% (projected)</text>`;
  Z.forEach((z, k) => {
    const y = mt + k * rh + 5, bh = rh - 10;
    s += `<text class="lab-s" x="${labW - 8}" y="${y + bh / 2}" dy="0.32em" text-anchor="end">${esc(z.label)}</text>`;
    if (isNum(z.mix)) s += `<path class="bar f1" data-k="${k}" d="${hb(x1(0), x1(z.mix), y, bh)}"/><text class="lab" x="${x1(Math.max(z.mix, z.lgMix || 0)) + 5}" y="${y + bh / 2}" dy="0.32em">${esc(F.pct(z.mix, 0))}</text>`;
    if (isNum(z.lgMix)) s += `<line class="wn-tick" x1="${x1(z.lgMix)}" x2="${x1(z.lgMix)}" y1="${y - 3}" y2="${y + bh + 3}"/>`;
    if (isNum(z.fg)) s += `<path class="bar f1" data-k="${k}" d="${hb(x2(0), x2(z.fg), y, bh)}"/><text class="lab" x="${x2(Math.max(z.fg, z.lgFg || 0)) + 5}" y="${y + bh / 2}" dy="0.32em">${esc(F.pct(z.fg, 0))}</text>`;
    if (isNum(z.lgFg)) s += `<line class="wn-tick" x1="${x2(z.lgFg)}" x2="${x2(z.lgFg)}" y1="${y - 3}" y2="${y + bh + 3}"/>`;
    s += `<rect class="hit" data-k="${k}" x="0" y="${y - 5}" width="${Wd}" height="${rh}"/>`;
  });
  s += '</svg>';
  el.innerHTML = titleHtml(o) + s + `<div class="sh-note wn-legend">Bars: her projection. Black tick: league average (2026).</div>`;
  const svg = el.querySelector('svg');
  hover(svg, '[data-k]', t => { const z = Z[+t.dataset.k]; return S.tip.html(z.label, [{ value: F.pct(z.mix, 1), label: 'of her FGA', key: 'b1' }, { value: F.pct(z.lgMix, 1), label: 'league share' }, { value: F.pct(z.fg, 1), label: 'her FG% (±' + F.pct(z.fgSd, 1) + ')' }, { value: F.pct(z.lgFg, 1), label: 'league FG%' }]); });
});

/* ════════ line pricer: input + summary + ladder centred on the entered line ════════ */
W.linePricer = (el, o) => {
  const step = o.step || 1, rows = o.rows ?? 4;
  const inp = h('input', { type: 'number', step: 0.5, class: 'wn-line', value: o.line, 'aria-label': (o.inputLabel || 'Line') });
  const summary = h('div', { class: 'wn-px' }), lad = h('div'), note = o.note ? h('div', { class: 'sh-note', html: o.note }) : null;
  el.append(h('div', { class: 'wn-lrow' }, h('label', { class: 'wn-lab' }, h('span', { class: 'ui-l', text: o.inputLabel || 'Line' }), inp), summary), lad);
  if (note) el.append(note);
  let cur = o.line;
  const draw = () => {
    let L = parseFloat(inp.value); if (!isFinite(L)) L = o.line; cur = L;
    const d = o.dist;
    if (o.spread) {
      const { home, away } = o.spread, thr = -L;
      const pc = d.pOver(thr), pa = d.pUnder(thr), pe = d.pEq(thr), nf = 1 - pe;
      summary.innerHTML = `<span><b>${esc(W.spreadText(home, L))}</b> covers <b>${F.pct(pc, 1)}</b> · fair <b>${esc(W.fp(pc / nf))}</b></span><span><b>${esc(W.spreadText(away, -L))}</b> <b>${F.pct(pa, 1)}</b> · fair <b>${esc(W.fp(pa / nf))}</b>${pe > 0.0005 ? ` · push ${F.pct(pe, 1)}` : ''}</span>`;
      const ls = []; for (let k = -rows; k <= rows; k++) ls.push(+(L + k * step).toFixed(2));
      const anyPush = ls.some(s => d.pEq(-s) > 0);
      let t = `<div class="sh-tbl-wrap"><table class="sh-tbl wn-spread"><thead><tr><th>${esc(home)} line</th><th class="n">P(cover)</th><th class="n">Fair</th><th>${esc(away)} line</th><th class="n">P(cover)</th><th class="n">Fair</th>${anyPush ? '<th class="n">Push</th>' : ''}</tr></thead><tbody>`;
      ls.forEach(s => { const th = -s, a = d.pOver(th), b = d.pUnder(th), e = d.pEq(th), n = 1 - e; t += `<tr${s === L ? ' class="hl"' : ''}><td>${esc(W.spreadText(home, s))}</td><td class="n">${F.pct(a, 1)}</td><td class="n">${esc(W.fp(a / n))}</td><td>${esc(W.spreadText(away, -s))}</td><td class="n">${F.pct(b, 1)}</td><td class="n">${esc(W.fp(b / n))}</td>${anyPush ? `<td class="n">${e > 0 ? F.pct(e, 1) : ''}</td>` : ''}</tr>`; });
      lad.innerHTML = t + '</tbody></table></div>';
    } else {
      const po = d.pOver(L), pu = d.pUnder(L), pe = d.pEq(L), nf = 1 - pe;
      summary.innerHTML = `<span>Over <b>${esc(W.fmtLine(L))}</b> <b>${F.pct(po, 1)}</b> · fair <b>${esc(W.fp(po / nf))}</b></span><span>Under <b>${F.pct(pu, 1)}</b> · fair <b>${esc(W.fp(pu / nf))}</b>${pe > 0.0005 ? ` · push ${F.pct(pe, 1)}` : ''}</span>`;
      const ls = []; for (let k = -rows; k <= rows; k++) { const v = +(L + k * step).toFixed(2); if (o.min == null || v >= o.min) ls.push(v); }
      S.ladder(lad, { dist: d, lines: ls, label: o.label || 'Line', odds: W.odds.mode, highlight: L, note: o.ladderNote === false ? false : undefined, compact: o.compact });
    }
    if (o.onLine) o.onLine(L);
  };
  inp.addEventListener('input', S.debounce(draw, 200));
  inp.addEventListener('change', draw);
  draw();
  W.odds.bind(el, draw);
  return { el, get line() { return cur; }, set(L) { inp.value = L; draw(); } };
};

/* ════════ game view (shared by Game and Simulator) ════════ */
const T3 = (v, dp = 1) => F.num(v, dp);
W.renderGame = (el, G, o = {}) => {
  el.innerHTML = '';
  const H = o.home || W.team(G.hId), A = o.away || W.team(G.aId), ha = H ? H.abbr : 'Home', aa = A ? A.abbr : 'Away';
  const lines = o.lines || {}, setLine = (k, v) => { if (o.onLines) o.onLines({ [k]: v }); };
  const fairS = -W.fairLine(G.marginDist, G.margin.mean);   // home spread whose cover prob is closest to 50%
  const fairT = W.fairLine(G.totalDist, G.total.mean);
  const venue = o.neutral ? 'neutral floor' : `${ha} at home`;
  const tileEl = h('div');
  const drawTiles = () => {
    tileEl.innerHTML = '';
    tileEl.append(S.tiles([
      { label: `${ha} win`, value: F.pct(G.homeWin, 1), sub: 'fair ' + W.fp(G.homeWin) },
      { label: `${aa} win`, value: F.pct(1 - G.homeWin, 1), sub: 'fair ' + W.fp(1 - G.homeWin) },
      { label: 'Fair spread', value: W.spreadText(ha, fairS), sub: `mean margin ${F.signed(G.margin.mean, 1)}` },
      { label: 'Total', value: T3(G.total.mean), sub: `sd ${T3(G.total.sd)} · 50/50 ${W.fmtLine(fairT)}` },
      { label: `${ha} points`, value: T3(G.homePts.mean), sub: 'sd ' + T3(G.homePts.sd) },
      { label: `${aa} points`, value: T3(G.awayPts.mean), sub: 'sd ' + T3(G.awayPts.sd) },
      { label: 'Overtime', value: F.pct(G.pOT, 1), sub: `${T3(G.poss)} poss / team` },
    ]));
  };
  drawTiles(); W.odds.bind(tileEl, drawTiles);
  el.append(h('div', { class: 'sh-note', text: `${ha} vs ${aa}, ${venue}${o.context ? ', ' + o.context : ''}. ${F.int(G.n)} simulated games${G.source ? ' (' + G.source + ')' : ''}. Margins are ${ha} minus ${aa}; spreads are quoted for the team named. Fair prices are no-vig.` }), tileEl);

  if (o.base) {
    const B = o.base, n = Math.min(G.n, B.n);
    const seW = Math.sqrt(2 * G.homeWin * (1 - G.homeWin) / n), seM = Math.sqrt(2 / n) * G.margin.sd, seT = Math.sqrt(2 / n) * G.total.sd;
    const dl = (v, se, f) => ({ value: f(v), sub: '± ' + f(Math.abs(se)).replace(/^[+−]/, '') + ' (1 SE)' });
    el.append(h('div', { class: 'sh-h', text: 'Change vs default' }), h('div', { class: 'sh-note', text: `Default = both teams' default rotations, ${ha} at home, two days' rest, run with the same seeds. SE treats the two runs as independent, so it overstates the noise.` }),
      S.tiles([
        Object.assign({ label: `Δ ${ha} win` }, dl(G.homeWin - B.homeWin, seW, v => F.spct(v, 1))),
        Object.assign({ label: 'Δ margin' }, dl(G.margin.mean - B.margin.mean, seM, v => F.signed(v, 1))),
        Object.assign({ label: 'Δ total' }, dl(G.total.mean - B.total.mean, seT, v => F.signed(v, 1))),
        { label: `Δ ${ha} pts`, value: F.signed(G.homePts.mean - B.homePts.mean, 1), sub: `default ${T3(B.homePts.mean)}` },
        { label: `Δ ${aa} pts`, value: F.signed(G.awayPts.mean - B.awayPts.mean, 1), sub: `default ${T3(B.awayPts.mean)}` },
        { label: 'Default win', value: F.pct(B.homeWin, 1), sub: `${ha} · total ${T3(B.total.mean)}` },
      ]));
  }

  const cols = h('div', { class: 'sh-cols' }); el.append(cols);
  // spread
  const c1 = W.card(cols, 'Spread', `Distribution of the final margin (${ha} − ${aa}, incl. OT). Enter a spread for ${ha} to price both sides; blue bars are outcomes where ${ha} covers.`);
  const mh = h('div'); c1.append(mh);
  const md = G.marginDist, mlo = md.quantile(0.004), mhi = md.quantile(0.996);
  const mchart = S.histogram(mh, { dist: md, xDomain: [mlo - 0.5, mhi + 0.5], height: 150, xLabel: `${ha} margin`, xFmt: 'signed:0', markers: [], maxBars: 140 });
  const sp = h('div', { style: { marginTop: '6px' } }); c1.append(sp);
  W.linePricer(sp, { dist: md, line: isNum(lines.sl) ? lines.sl : fairS, spread: { home: ha, away: aa }, inputLabel: `${ha} spread`, rows: 4, onLine: L => { mchart.update({ split: -L, markers: [{ x: -L, label: W.spreadText(ha, L), strong: true }, { x: G.margin.mean, label: 'mean' }] }); setLine('sl', L === fairS ? null : L); } });
  // total
  const c2 = W.card(cols, 'Total', 'Distribution of the combined final score (incl. OT). Type a line to price over/under.');
  const th = h('div'); c2.append(th);
  const td = G.totalDist;
  const tchart = S.histogram(th, { dist: td, xDomain: [td.quantile(0.004) - 0.5, td.quantile(0.996) + 0.5], height: 150, xLabel: 'total points', maxBars: 160 });
  const tp = h('div', { style: { marginTop: '6px' } }); c2.append(tp);
  W.linePricer(tp, { dist: td, line: isNum(lines.tl) ? lines.tl : fairT, step: 2, rows: 4, label: 'Total', inputLabel: 'Total line', onLine: L => { tchart.update({ split: L, markers: [{ x: L, label: 'Line ' + W.fmtLine(L), strong: true }, { x: G.total.mean, label: 'mean' }] }); setLine('tl', L === fairT ? null : L); } });

  // team totals + periods
  const cols2 = h('div', { class: 'sh-cols' }); el.append(cols2);
  const c3 = W.card(cols2, 'Team totals', 'Normal approximation to each team\'s simulated points (mean and SD from the sims; the export does not carry the full team-score distribution).');
  const tt = h('div', { class: 'wn-two' }); c3.append(tt);
  [[ha, G.homePts, 'hl'], [aa, G.awayPts, 'al']].forEach(([ab, st, key]) => {
    const box = h('div'); tt.append(box);
    const d = W.normalDist(st.mean, st.sd);
    W.linePricer(box, { dist: d, line: isNum(lines[key]) ? lines[key] : W.halfLine(st.mean), step: 1, rows: 3, label: ab, inputLabel: ab + ' line', ladderNote: false, compact: true, onLine: L => setLine(key, L === W.halfLine(st.mean) ? null : L) });
  });
  const c4 = W.card(cols2, 'Quarters and halves', `Simulated period scoring. 2nd half includes OT. "Fair 2-way" prices ${ha} with ties void.`);
  const per = []; G.quarters.forEach((q, i) => per.push(Object.assign({ p: 'Q' + (i + 1) }, q))); G.halves.forEach((q, i) => per.push(Object.assign({ p: i ? '2nd half' : '1st half' }, q)));
  const ptab = h('div'); c4.append(ptab);
  const drawPer = () => S.table(ptab, [
    { key: 'p', label: 'Period' }, { key: 'home', label: ha, fmt: 'num:1', desc: `${ha} points, mean` }, { key: 'away', label: aa, fmt: 'num:1', desc: `${aa} points, mean` },
    { key: 'marginMean', label: 'Margin', fmt: 'signed:1', desc: `${ha} − ${aa}, mean` }, { key: 'marginSd', label: 'Mgn SD', fmt: 'num:1' },
    { key: 'totalMean', label: 'Total', fmt: 'num:1' }, { key: 'totalSd', label: 'Tot SD', fmt: 'num:1' },
    { key: 'homeWin', label: `P(${ha})`, fmt: 'pct:1', desc: `P(${ha} outscores ${aa} in the period)` }, { key: 'tie', label: 'P(tie)', fmt: 'pct:1' },
    { key: 'fair', label: 'Fair 2-way', get: r => W.fp(r.homeWin / (1 - r.tie)), desc: `${ha} to win the period, ties void` },
  ], per);
  drawPer(); W.odds.bind(ptab, drawPer);

  // players
  const c5 = W.card(el, 'Player projections', `Means from the same simulated games as the team scores. Click a player for distributions, ladders and fair prices.${o.playersNote ? ' ' + o.playersNote : ''}`);
  const both = [['home', G.home, ha], ['away', G.away, aa]];
  const wrap = h('div', { class: 'wn-two wn-two-wide' }); c5.append(wrap);
  both.forEach(([side, list, ab]) => {
    const box = h('div'); wrap.append(box); box.append(h('div', { class: 'wn-sub', text: ab }));
    const rows = list.map((p, i) => ({ p, i })).filter(r => !r.p.out && r.p.stats.min && r.p.stats.min.mean >= 0.05).sort((a, b) => b.p.stats.min.mean - a.p.stats.min.mean);
    const outs = list.filter(p => p.out);
    const t = h('div'); box.append(t);
    const m = k => r => r.p.stats[k] ? r.p.stats[k].mean : null;
    S.table(t, [
      { key: 'n', label: 'Player', get: r => r.p.name }, { key: 'min', label: 'Min', get: m('min'), fmt: 'num:1' }, { key: 'pts', label: 'Pts', get: m('pts'), fmt: 'num:1' },
      { key: 'reb', label: 'Reb', get: m('reb'), fmt: 'num:1' }, { key: 'ast', label: 'Ast', get: m('ast'), fmt: 'num:1' }, { key: 'fg3m', label: '3PM', get: m('fg3m'), fmt: 'num:1' },
      { key: 'stl', label: 'Stl', get: m('stl'), fmt: 'num:1' }, { key: 'blk', label: 'Blk', get: m('blk'), fmt: 'num:1' }, { key: 'tov', label: 'TOV', get: m('tov'), fmt: 'num:1' },
      { key: 'pra', label: 'PRA', get: m('pra'), fmt: 'num:1' }, { key: 'dd', label: 'P(DD)', get: r => r.p.pDD, fmt: 'pct:0', desc: 'P(double-double)' },
    ], rows);
    t.classList.add('wn-click');
    t.querySelectorAll('tbody tr').forEach((tr, k) => { tr.tabIndex = 0; const go = () => W.openProp(G, side, rows[k].i, 'pts', o); tr.addEventListener('click', go); tr.addEventListener('keydown', e => { if (e.key === 'Enter') go(); }); });
    if (outs.length) box.append(h('div', { class: 'sh-note', text: 'Out: ' + outs.map(p => p.name).join(', ') }));
  });
  return el;
};

/* ════════ player prop card (drawer) ════════ */
W.defaultPropLine = st => {
  const c = st.comps && st.comps[0];
  if (c && c.lines && c.lines.length) { let best = c.lines[0], bd = 9; c.lines.forEach((l, i) => { const v = Math.abs(c.po[i] - 0.5); if (v < bd) { bd = v; best = l; } }); return best; }
  return Math.max(0.5, Math.floor(st.mean) + 0.5);
};
W.propNote = st => {
  const ex = st.exactLines.filter(isNum);
  return `Simulated mean ${F.num(st.mean, 2)}, SD ${F.num(st.sd, 2)}. P(over) is exact from the simulation at ${ex.length ? ex.map(W.fmtLine).join(', ') : 'no lines'}${st.comps.length > 1 ? ' (per run, pooled)' : ''}; other lines are interpolated on a negative-binomial shape fitted to the mean and SD.`;
};
/** stat panel: tiles + histogram + pricer for one player stat; returns nothing */
W.statPanel = (el, st, o = {}) => {
  el.innerHTML = '';
  if (!st) { el.append(h('div', { class: 'sh-note', text: 'No projection for this stat.' })); return; }
  const qs = [0.1, 0.25, 0.5, 0.75, 0.9].map(p => [p, W.qAt(st, p)]).filter(x => x[1] != null);
  el.append(S.tiles([
    { label: 'Mean', value: F.num(st.mean, 1), sub: 'sd ' + F.num(st.sd, 1) },
    { label: 'Median', value: st.median != null ? F.num(st.median, st.median % 1 ? 1 : 0) : '–', sub: qs.length ? `10–90%: ${F.num(W.qAt(st, 0.1), 0)}–${F.num(W.qAt(st, 0.9), 0)}` : '' },
    { label: 'P(0)', value: F.pct(st.dist.pAtMost(0), 1), sub: o.key === 'min' ? 'did not play' : 'zero' },
  ]));
  const grid2 = h('div', { class: 'wn-statgrid' }); el.append(grid2);
  const leftCol = h('div'), hh = h('div'); leftCol.append(hh); grid2.append(leftCol);
  const d = st.dist, top = d.quantile(0.997);
  const chart = S.histogram(hh, { dist: d, xDomain: [-0.5, top + 0.5], height: 130, xLabel: (W.STAT_SHORT[o.key] || 'value').toLowerCase(), maxBars: 400 });
  const pr = h('div'); grid2.append(pr);
  const L0 = isNum(o.line) ? o.line : W.defaultPropLine(st);
  W.linePricer(pr, { dist: d, line: L0, step: DEFAULT_STEP[o.key] === 2 ? 1 : 1, rows: 4, min: 0.5, label: W.STAT_SHORT[o.key] || 'Line', inputLabel: (W.STAT_SHORT[o.key] || '') + ' line', ladderNote: false, note: W.propNote(st),
    onLine: L => { chart.update({ split: L, markers: [{ x: L, label: 'O/U ' + W.fmtLine(L), strong: true }, { x: st.mean, label: 'mean' }] }); if (o.onLine) o.onLine(L); } });
  if (qs.length) { const qt = h('div', { style: { marginTop: '10px' } }); leftCol.append(qt); S.table(qt, [{ key: 'k', label: 'Quantile' }].concat(qs.map(([p]) => ({ key: 'q' + p, label: (p * 100) + '%', fmt: 'num:1', get: () => W.qAt(st, p) }))), [{ k: 'Simulated' }]); }
};
W.openProp = (G, side, idx, key, o = {}) => {
  const list = G[side], p = list[idx]; if (!p) return;
  const order = [...G.home.map((x, i) => ['home', i, x]), ...G.away.map((x, i) => ['away', i, x])].filter(r => !r[2].out && r[2].stats.min && r[2].stats.min.mean >= 0.05);
  const pos = order.findIndex(r => r[0] === side && r[1] === idx);
  const team = W.team(side === 'home' ? G.hId : G.aId), opp = W.team(side === 'home' ? G.aId : G.hId);
  let cur = key || 'pts';
  S.drawer.open({
    title: p.name, sub: `${team ? team.abbr : ''} ${side === 'home' ? 'vs' : 'at'} ${opp ? opp.abbr : ''} · ${F.num(p.stats.min ? p.stats.min.mean : p.projMin, 1)} min projected${isNum(p.pDD) ? ' · P(double-double) ' + F.pct(p.pDD, 1) : ''}`,
    keepScroll: true,
    nav: { prev: () => { const r = order[Math.max(0, pos - 1)]; W.openProp(G, r[0], r[1], cur, o); }, next: () => { const r = order[Math.min(order.length - 1, pos + 1)]; W.openProp(G, r[0], r[1], cur, o); } },
    body: el => {
      const seg = S.ui.segmented({ options: W.STATS.map(k => ({ value: k, label: W.STAT_SHORT[k] })), value: cur, onChange: v => { cur = v; W.statPanel(panel, p.stats[cur], { key: cur }); } });
      const panel = h('div', { class: 'sh-section' });
      el.append(seg, panel);
      W.statPanel(panel, p.stats[cur], { key: cur });
      const pl = W.player(p.id);
      if (pl) el.append(h('div', { class: 'sh-note' }, h('a', { href: '#', text: 'Open her player card', onclick: e => { e.preventDefault(); W.playerCard(pl); } }), isNum(p.fga) ? ` · per game: ${F.num(p.fga, 1)} FGA, ${F.num(p.fg3a, 1)} 3PA, ${F.num(p.fta, 1)} FTA` : ''));
    },
  });
};
})();
