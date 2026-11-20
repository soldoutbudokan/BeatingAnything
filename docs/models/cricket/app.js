/* Test / ODI workbooks: shared data access, match state, the simulator sheet and result renderers (window.CK).
   The page sets window.CRICKET_FMT = 'test' | 'odi' before loading this file; sheets.js builds the workbook. */
(function () {
'use strict';
const S = Sheets, h = S.h, F = S.fmt;
const FMT = window.CRICKET_FMT === 'odi' ? 'odi' : 'test', isTest = FMT === 'test';
const CK = window.CK = { FMT, isTest };
const isNum = v => typeof v === 'number' && isFinite(v);
CK.isNum = isNum;
CK.PH = isTest ? ['nb', 'mid', 'old'] : ['pp', 'mid', 'death'];
CK.PH_LABEL = isTest ? ['New ball', 'Middle', 'Old ball'] : ['Powerplay', 'Middle', 'Death'];
CK.PH_HINT = isTest ? ['Overs 1–20 of each ball', 'Overs 21–55 of each ball', 'Overs 56–80 of each ball'] : ['Overs 1–10', 'Overs 11–40', 'Overs 41–50'];
CK.ROLE = { open: 'Opener', top: 'Top order', middle: 'Middle order', lower: 'Lower order', tail: 'Tail' };
CK.BROLE = { pace_part: 'Part-time pace', pace_reg: 'Support pace', pace_front: 'Frontline pace', spin_part: 'Part-time spin', spin_reg: 'Support spin', spin_front: 'Frontline spin' };
CK.TYPES = [['pace_R', 'Right-arm pace'], ['pace_L', 'Left-arm pace'], ['OB', 'Off-spin'], ['LB', 'Leg-spin'], ['SLA', 'Slow left-arm'], ['SLW', 'Left-arm wrist spin']];
CK.SIM_WORKERS = 4; CK.SIM_SEED = 7;

/* ════════ odds mode (American default, decimal toggle) ════════ */
let oddsMode = 'american';
try { const m = localStorage.getItem('cricket.odds'); if (m === 'decimal' || m === 'american') oddsMode = m; } catch (e) { /* storage blocked */ }
const oddsViews = [];
CK.odds = {
  get mode() { return oddsMode; },
  set(m) {
    if (m === oddsMode) return;
    oddsMode = m; try { localStorage.setItem('cricket.odds', m); } catch (e) { /* ignore */ }
    for (let i = oddsViews.length - 1; i >= 0; i--) { const v = oddsViews[i]; if (!v.el.isConnected) { oddsViews.splice(i, 1); continue; } try { v.fn(m); } catch (e) { console.error(e); } }
  },
  bind(el, fn) { oddsViews.push({ el, fn }); },
};
/** fair (no-vig) price of a probability in the current odds mode */
const fp = CK.fp = p => !(p > 0 && p < 1) ? '–' : oddsMode === 'decimal' ? F.dec(p, 2) : F.american(p);
const pc = (p, d = 1) => isNum(p) ? F.pct(p, d) : '–';

/* ════════ data ════════ */
const D = CK.D = { names: new Map(), roles: new Map() };
CK.load = () => CK._l || (CK._l = Promise.all([S.load('data/players.json'), S.load('data/teams.json'), S.load('data/venues.json'),
  S.load.optional('data/schedule.json'), S.load.optional('data/ids.json')]).then(([P, T, V, SCH, IDS]) => {
  D.P = P; D.players = P.players || []; D.pById = new Map(D.players.map(p => [p.id, p]));
  if (IDS && IDS.names) for (const id in IDS.names) D.names.set(id, IDS.names[id]);
  D.players.forEach(p => D.names.set(p.id, p.name));
  D.T = T; D.teams = T.teams || []; D.tByName = new Map(D.teams.map(t => [t.name, t])); D.tByShort = new Map(D.teams.map(t => [t.short, t]));
  D.regionOf = T.region_of || {};
  D.teams.forEach(t => (t.squad || []).forEach(s => { if (!D.names.has(s.id)) D.names.set(s.id, s.name); }));
  D.V = V; D.venues = V.venues || []; D.vById = new Map(D.venues.map(v => [v.venue, v])); D.countries = V.countries || [];
  D.SCH = SCH || { fixtures: [] }; D.fixtures = D.SCH.fixtures || []; D.fxById = new Map(D.fixtures.map(f => [String(f.id), f]));
  D.fixtures.forEach(f => ['A', 'B'].forEach(k => { const lu = f.lineups && f.lineups[k]; if (!lu) return; for (const id in lu.names || {}) if (!D.names.has(id)) D.names.set(id, lu.names[id]); for (const id in lu.roles || {}) D.roles.set(id, lu.roles[id]); }));
  return D;
}));
CK.loadSimParams = () => CK._sp || (CK._sp = S.load('data/sim_params.json'));
CK.team = k => k == null ? null : D.tByName.get(k) || D.tByShort.get(k) || D.tByShort.get(String(k).toUpperCase()) || null;
CK.short = k => { const t = CK.team(k); return t ? t.short : (k ? String(k) : '—'); };
CK.pname = id => D.names.get(id) || String(id);
CK.player = id => D.pById.get(id) || null;
CK.venueName = id => { const v = D.vById.get(id); return v ? v.name : String(id || ''); };
/** a side's lineup for a host country: its most recent XI in those conditions, else its latest XI */
CK.lineupFor = (t, country) => (country && t.by_region && t.by_region[D.regionOf[country] || 'other']) || t.default;
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const dateStr = s => { if (!s) return ''; const d = new Date(s + 'T00:00:00Z'); return isNaN(d) ? s : `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
CK.dateStr = dateStr;

/* ════════ distributions from raw simulator counts ════════ */
const distOf = CK.distOf = (hist, off = 0) => { const rows = []; (hist || []).forEach((c, i) => { if (c > 0) rows.push([i - off, c]); }); return rows.length ? S.dist.fromPmf(rows) : null; };
const hmerge = (a, b) => { const o = (a || []).slice(); (b || []).forEach((c, i) => { o[i] = (o[i] || 0) + c; }); return o; };

/* ════════ match state (URL <-> lineups) ════════ */
const planStr = plan => plan.map(x => `${x.id}:${CK.PH.map(k => +(+x[k] || 0).toFixed(1)).join('_')}`).join(',');
const parsePlan = s => (s || '').split(',').filter(Boolean).map(t => { const i = t.lastIndexOf(':'), id = t.slice(0, i), q = t.slice(i + 1).split('_').map(Number), o = { id }; CK.PH.forEach((k, j) => { o[k] = q[j] || 0; }); return o; }).filter(x => x.id);
const planTotal = x => CK.PH.reduce((s, k) => s + (+x[k] || 0), 0);
CK.planStr = planStr;
const ODI_NEED = [10, 30, 10];
CK.checkPlan = (plan, order) => {
  const tot = CK.PH.map(k => plan.reduce((s, x) => s + (+x[k] || 0), 0)), errs = [];
  const active = plan.filter(x => planTotal(x) > 0);
  active.forEach(x => { if (!order.includes(x.id)) errs.push(`${CK.pname(x.id)} is not in the XI`); });
  if (isTest) {
    CK.PH.forEach((k, i) => { if (plan.filter(x => +x[k] > 0).length < 2) errs.push(`${CK.PH_LABEL[i].toLowerCase()} needs at least two bowlers with a share`); });
  } else {
    active.forEach(x => { if (planTotal(x) > 10) errs.push(`${CK.pname(x.id)} has ${planTotal(x)} overs (max 10)`); });
    tot.forEach((v, i) => { if (v !== ODI_NEED[i]) errs.push(`${CK.PH_LABEL[i].toLowerCase()} has ${v} of ${ODI_NEED[i]} overs`); });
    if (active.length < 5) errs.push('at least 5 bowlers are needed');
  }
  return { tot, errs };
};
/** engine roles for a player the simulator has no rating for */
function rolesFor(ids, SP) {
  const out = {};
  ids.forEach((id, k) => {
    if (SP.batters[id] && SP.bowlers[id]) return;
    const p = CK.player(id), r = D.roles.get(id) || {};
    const slot = ['open', 'open', 'top', 'top', 'middle', 'middle', 'middle', 'lower', 'lower', 'tail', 'tail'][Math.min(k, 10)];
    out[id] = { bat: r.bat || (p && p.bat && p.bat.role) || slot, bowl: r.bowl || (p && p.bowl && p.bowl.role) || (p && p.bowl_group === 'spin' ? 'spin_part' : 'pace_part'), hand: (p && p.bat_hand) || 'R' };
  });
  return out;
}
const GROUND_NEUTRAL = 'n';
/** resolve the Match sheet's URL state into teams, ground, lineups and options */
CK.matchState = (sheet, SP) => {
  const fx = D.fxById.get(String(sheet.get('fx') || '')) || null, fxOk = fx && fx.modelled;
  const T = D.teams;
  let a = CK.team(sheet.get('a')) || (fxOk && CK.team(fx.A)) || T[0], b = CK.team(sheet.get('b')) || (fxOk && CK.team(fx.B)) || T[1];
  if (a === b) b = T.find(t => t !== a);
  const custom = !fxOk || a.name !== fx.A || b.name !== fx.B;
  // ground: 'v:<venue id>', 'c:<host country>' or 'n' (neutral, average full-member conditions)
  const fxGround = fxOk ? (fx.venue ? 'v:' + fx.venue : (fx.env_known ? 'c:' + fx.country : GROUND_NEUTRAL)) : null;
  let g = sheet.get('g') || (!custom && fxGround) || (SP.env[a.name] ? 'c:' + a.name : GROUND_NEUTRAL);
  let venue = null, country = null;
  if (g.startsWith('v:') && SP.venues[g.slice(2)]) { venue = g.slice(2); country = SP.venues[venue].country; }
  else if (g.startsWith('c:') && SP.env[g.slice(2)]) country = g.slice(2);
  else g = GROUND_NEUTRAL;
  const home = country === a.name ? 'A' : country === b.name ? 'B' : null;
  const side = (k, t) => {
    const def = !custom ? fx.lineups[k === 'a' ? 'A' : 'B'] : CK.lineupFor(t, country);
    let order = (sheet.get(k + 'o') || '').split(',').filter(Boolean); if (order.length !== 11) order = def.order.slice(0, 11);
    const plan = sheet.get(k + 'p') ? parsePlan(sheet.get(k + 'p')) : def.plan.map(x => Object.assign({}, x));
    return { t, def, order, plan, source: def.source || `most recent XI in comparable conditions (${def.date}, ${def.country})` };
  };
  const fxToss = !custom && fx.toss ? fx.toss : null;
  const tw = sheet.get('tw') === 'a' || sheet.get('tw') === 'b' ? sheet.get('tw') : (sheet.get('tw') === 'x' || !fxToss ? '' : (fxToss.winner === a.name ? 'a' : 'b'));
  const td = sheet.get('td') === 'bowl' || sheet.get('td') === 'bat' ? sheet.get('td') : (fxToss && fxToss.decision === 'field' ? 'bowl' : 'bat');
  const batFirst = !tw ? null : (tw === 'a') === (td === 'bat') ? 'A' : 'B';
  const CO = SP.conditions || {};
  const pitch = CO.pitch && CO.pitch[sheet.get('pi')] ? sheet.get('pi') : 'normal', dew = CO.dew && CO.dew[sheet.get('dw')] ? sheet.get('dw') : 'normal';
  const conditions = {}; if (pitch !== 'normal') conditions.pitch = pitch; if (dew !== 'normal') conditions.dew = dew;
  const ov = isTest ? (sheet.get('ov') || '') : '';
  const nDef = isTest ? 4000 : 20000;
  return { fx: custom ? null : fx, fxAny: fx, custom, a, b, g, venue, country, home, tw, td, batFirst, pitch, dew, conditions, ov, n: +(sheet.get('n') || nDef), nDef, A: side('a', a), B: side('b', b) };
};
CK.sideDefault = sd => sd.order.join() === sd.def.order.slice(0, 11).join() && planStr(sd.plan) === planStr(sd.def.plan);
CK.spec = (sd, SP) => ({ name: sd.t.name, order: sd.order, plan: sd.plan.filter(x => planTotal(x) > 0), roles: rolesFor(sd.order, SP) });
CK.simOpts = s => {
  const o = { venue: s.venue, country: s.country || '_default', home: s.home, batFirst: s.batFirst, conditions: Object.keys(s.conditions).length ? s.conditions : null };
  if (isTest) { if (s.ov === 'full') o.overs = 450; else if (/^m\d+$/.test(s.ov)) o.oversAdj = -(+s.ov.slice(1)); }
  return o;
};
CK.groundLabel = s => s.venue ? CK.venueName(s.venue) : s.country ? `${s.country} (no specific ground)` : 'Neutral ground, average conditions';
/** link into the Match sheet */
CK.matchHash = o => '#sheet=match&' + Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');

/* ════════ in-browser simulation ════════ */
/** spec {A, B, opts, sims}; returns {job}; the job resolves to pooled raw counts (see sim.js). */
CK.simulate = async (spec, onProgress) => {
  const sp = await CK.loadSimParams();
  return { job: S.simulate({ module: '../cricket/sim-run.js', params: Object.assign({ sp, chunk: isTest ? 250 : 1000 }, spec), workers: CK.SIM_WORKERS, seed: CK.SIM_SEED, onProgress }) };
};

/* ════════ result renderers ════════ */
/** histogram + ladder + a custom line for one distribution */
CK.marketView = (el, d, o = {}) => {
  el.innerHTML = '';
  if (!d) { el.append(h('div', { class: 'sh-note', text: 'No simulated values for this market.' })); return; }
  const top = h('div'), lad = h('div'), px = h('div', { class: 'ck-px' });
  const whole = o.step === 1;   // lines at half points unless the market is priced on whole numbers
  const def = o.line != null ? o.line : Math.floor(d.quantile(0.5)) + 0.5;
  const inp = h('input', { type: 'number', step: whole ? 1 : 0.5, class: 'ck-line', value: def, 'aria-label': 'Line' });
  const drawPx = () => {
    const x = +inp.value; if (!isFinite(x)) { px.textContent = ''; return; }
    const po = d.pOver(x), pu = d.pUnder(x), push = Math.max(0, 1 - po - pu), nv = po + pu || 1;
    px.innerHTML = `<span>Over ${F.num(x, x % 1 ? 1 : 0)}: <b>${pc(po)}</b> · fair ${fp(po / nv)}</span><span>Under: <b>${pc(pu)}</b> · fair ${fp(pu / nv)}</span>${push > 1e-9 ? `<span>Push ${pc(push)}</span>` : ''}`;
  };
  inp.addEventListener('input', drawPx);
  S.histogram(top, { title: o.title, subtitle: `mean ${F.num(d.mean, 1)} · SD ${F.num(d.sd, 1)} · median ${F.num(d.quantile(0.5), 0)}`, dist: d, markers: [{ x: d.mean, label: 'Mean' }], cumulative: 'over', xLabel: o.unit || '', height: 150, maxBars: 60 });
  const drawLadder = () => { lad.innerHTML = ''; S.ladder(lad, { dist: d, label: o.short || 'Line', odds: CK.odds.mode, lines: o.lines }); drawPx(); };
  drawLadder(); CK.odds.bind(el, drawLadder);
  el.append(top, h('div', { class: 'ck-lrow' }, h('label', { class: 'ck-lab' }, h('span', { class: 'ui-l', text: 'Your line' }), inp), px), lad);
};

function batRows(T, order) {
  return order.map((id, k) => {
    const p = T.players[id]; if (!p || !p.n) return null;
    const r = distOf(p.r1), rm = isTest ? distOf(p.rm) : null;
    return { id, pos: k + 1, name: CK.pname(id), runs: r.mean, med: r.quantile(0.5), p25: r.pOver(24.5), p50: r.pOver(49.5), p100: r.pOver(99.5), top: p.top1 / p.n, balls: p.b1 / p.n,
             fours: distOf(p.f).mean, sixes: distOf(p.s).mean, duck: p.duck1 / p.n, pbat: p.bat1 / p.n, rm: rm ? rm.mean : null, c100: p.c100 / p.n, c50: p.c50 / p.n, _p: p };
  }).filter(Boolean);
}
function bowlRows(T, ids) {
  return ids.map(id => {
    const p = T.players[id]; if (!p || !p.nw) return null;
    const w = distOf(p.w1), wm = isTest ? distOf(p.wm) : null;
    return { id, name: CK.pname(id), overs: p.bb1 / p.nw / 6, wkts: w.mean, p1: w.pOver(0.5), p2: w.pOver(1.5), p3: w.pOver(2.5), p4: w.pOver(3.5), p5: w.pOver(4.5), conc: p.cr1 / p.nw, econ: p.bbm ? p.crm / p.bbm * 6 : null,
             top: p.topw1 / p.nw, wm: wm ? wm.mean : null, om: p.bbm / p.nw / 6, _p: p };
  }).filter(r => r && r.overs > 0.05).sort((x, y) => y.overs - x.overs);
}
function playerDrawer(row, kind, tshort) {
  const p = row._p, inn = isTest ? '1st innings' : 'innings';
  S.drawer.open({ title: row.name, sub: `${tshort} · simulated ${kind === 'bat' ? 'batting' : 'bowling'}`, body: el => {
    if (kind === 'bat') {
      el.append(S.tiles([{ label: `Runs, ${inn}`, value: F.num(row.runs, 1), sub: 'median ' + F.num(row.med, 0) }, { label: '50+', value: pc(row.p50), sub: 'fair ' + fp(row.p50) },
        { label: '100+', value: pc(row.p100), sub: 'fair ' + fp(row.p100) }, { label: 'Top team batter', value: pc(row.top), sub: 'fair ' + fp(row.top) }]));
      CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.r1), { title: `Runs, ${inn}`, unit: 'runs', short: 'Runs' });
      if (isTest) CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.rm), { title: 'Runs in the match (both innings)', unit: 'runs', short: 'Match runs' });
      CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.f), { title: isTest ? 'Fours in the match' : 'Fours', unit: 'fours', short: 'Fours' });
      CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.s), { title: isTest ? 'Sixes in the match' : 'Sixes', unit: 'sixes', short: 'Sixes' });
      el.append(S.kv([['Balls faced (mean)', F.num(row.balls, 1)], ['Duck', pc(row.duck)], ['Gets to bat', pc(row.pbat)]].concat(isTest ? [['A fifty in either innings', pc(row.c50)], ['A hundred in either innings', pc(row.c100)]] : []), { cols: 2 }));
    } else {
      el.append(S.tiles([{ label: `Wickets, ${inn}`, value: F.num(row.wkts, 2), sub: F.num(row.overs, 1) + ' overs' }, { label: '3+', value: pc(row.p3), sub: 'fair ' + fp(row.p3) },
        { label: '5+', value: pc(row.p5), sub: 'fair ' + fp(row.p5) }, { label: 'Top team bowler', value: pc(row.top), sub: 'fair ' + fp(row.top) }]));
      CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.w1), { title: `Wickets, ${inn}`, unit: 'wickets', short: 'Wickets', line: 1.5 });
      if (isTest) CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.wm), { title: 'Wickets in the match', unit: 'wickets', short: 'Match wickets', line: 3.5 });
      CK.marketView(el.appendChild(h('div', { class: 'sh-card' })), distOf(p.c1), { title: `Runs conceded, ${inn}`, unit: 'runs', short: 'Conceded' });
      el.append(S.kv([['Economy', F.num(row.econ, 2)], [`Overs, ${inn}`, F.num(row.overs, 1)]].concat(isTest ? [['Overs in the match', F.num(row.om, 1)]] : []), { cols: 2 }));
    }
  } });
}
const fairCol = (key, label, desc) => ({ key, label, fmt: 'pct:1', desc, render: v => isNum(v) ? `${F.pct(v, 1)} <span class="muted">${fp(v)}</span>` : '–', width: 104 });

/** everything shown for one simulated match. raw: pooled counts; s: match state */
CK.renderResults = (root, raw, s) => {
  const draw = () => {
    root.innerHTML = '';
    const N = raw.n, a = s.a.short, b = s.b.short, R = raw.res;
    const tiles = [{ label: `${a} win`, value: pc(R.A / N), sub: 'fair ' + fp(R.A / N) }];
    if (isTest) tiles.push({ label: 'Draw', value: pc(R.draw / N), sub: 'fair ' + fp(R.draw / N) });
    tiles.push({ label: `${b} win`, value: pc(R.B / N), sub: 'fair ' + fp(R.B / N) });
    if (!isTest) tiles.push({ label: 'Tie', value: pc(R.tie / N, 2), sub: 'fair ' + fp(R.tie / N) });
    if (isTest) { const dec = R.A + R.B || 1; tiles.push({ label: 'Draw no bet', value: `${pc(R.A / dec)} / ${pc(R.B / dec)}`, sub: `fair ${fp(R.A / dec)} / ${fp(R.B / dec)}` }); }
    root.append(S.tiles(tiles));
    const se = Math.sqrt((R.A / N) * (1 - R.A / N) / N);
    root.append(h('div', { class: 'sh-note', text: `${F.int(N)} simulated matches at ${CK.groundLabel(s)}${s.home ? `, ${s.home === 'A' ? a : b} at home` : ', neutral'}. Monte Carlo error on a win probability: ±${F.pct(se, 1)} (1 SE). Fair prices carry no margin.` }));
    // ---- by toss
    const fr = ['A', 'B'].map(k => { const f = raw.first[k]; return f && f.n ? { who: `${k === 'A' ? a : b} bat first`, n: f.n, pa: f.A / f.n, pd: f.draw / f.n, pb: f.B / f.n, inn1: distOf(f.inn1).mean } : null; }).filter(Boolean);
    const sec1 = h('div', { class: 'sh-card' }); root.append(sec1);
    sec1.append(h('div', { class: 'sh-h', text: 'By who bats first' }));
    S.table(sec1.appendChild(h('div')), [{ key: 'who', label: '' }, { key: 'n', label: 'Sims', fmt: 'int' }, fairCol('pa', `${a} win`), ...(isTest ? [fairCol('pd', 'Draw')] : []), fairCol('pb', `${b} win`),
      { key: 'inn1', label: 'First-innings total', fmt: 'num:1' }], fr);
    if (isTest) {
      const m = raw.match, dayP = [3, 4, 5].map(dn => (m.day[dn] || 0)), early = (m.day[1] || 0) + (m.day[2] || 0);
      sec1.append(S.kv([['Result inside three days', pc((early + dayP[0]) / N)], ['Innings victory', pc(m.inns_win / N)], ['Follow-on enforced', pc(m.fo / N)],
        ['Follow-on available', pc(m.fo_ok / N)], ['Overs bowled (mean)', F.num(distOf(m.overs).mean, 0)], [`${a} lead on first innings`, pc(distOf(m.lead1, 1000).pOver(0.5))]], { cols: 3 }));
    }
    // ---- markets
    const mk = [];
    const add = (label, d, o) => { if (d) mk.push(Object.assign({ label, d }, o)); };
    if (isTest) {
      add(`First-innings lead: ${a} minus ${b}`, distOf(raw.match.lead1, 1000), { unit: 'runs', short: 'Lead', step: 0.5 });
      ['A', 'B'].forEach(k => { const T = raw.teams[k], n = k === 'A' ? a : b; add(`${n} 1st-innings total`, distOf(T.t1), { unit: 'runs', short: 'Total' }); });
      ['A', 'B'].forEach(k => { const T = raw.teams[k], n = k === 'A' ? a : b; add(`${n} 2nd-innings total (when they bat again)`, distOf(T.t2), { unit: 'runs', short: 'Total' }); });
    } else {
      add('First-innings total (either side)', distOf(hmerge(raw.first.A.inn1, raw.first.B.inn1)), { unit: 'runs', short: 'Total' });
      ['A', 'B'].forEach(k => { const n = k === 'A' ? a : b; add(`${n} total, batting first`, distOf(raw.first[k].inn1), { unit: 'runs', short: 'Total' }); });
      ['A', 'B'].forEach(k => { const n = k === 'A' ? a : b; add(`${n} total, any toss (a chase stops at the target)`, distOf(raw.teams[k].t1), { unit: 'runs', short: 'Total' }); });
    }
    add('Match runs', distOf(raw.match.total), { unit: 'runs', short: 'Runs' });
    add('Match sixes', distOf(raw.match.sixes), { unit: 'sixes', short: 'Sixes' });
    add('Match fours', distOf(raw.match.fours), { unit: 'fours', short: 'Fours' });
    ['A', 'B'].forEach(k => {
      const T = raw.teams[k], n = k === 'A' ? a : b, inn = isTest ? ', 1st innings' : '';
      add(`${n} runs in the first 10 overs${inn}`, distOf(T.pp), { unit: 'runs', short: 'Runs' });
      add(`${n} score at the fall of the 1st wicket${inn}`, distOf(T.fow1), { unit: 'runs', short: 'Runs' });
      add(`${n} wickets lost${inn}`, distOf(T.w1), { unit: 'wickets', short: 'Wickets' });
      add(`${n} sixes${isTest ? ' in the match' : ''}`, distOf(T.sixes), { unit: 'sixes', short: 'Sixes' });
      add(`${n} fours${isTest ? ' in the match' : ''}`, distOf(T.fours), { unit: 'fours', short: 'Fours' });
    });
    if (isTest) add('Overs bowled in the match', distOf(raw.match.overs), { unit: 'overs', short: 'Overs' });
    else { add('Winning margin in runs (side batting first wins)', distOf(raw.match.m_runs), { unit: 'runs', short: 'Runs' }); add('Winning margin in wickets (chasing side wins)', distOf(raw.match.m_wkts), { unit: 'wickets', short: 'Wickets' }); add('Balls to spare (chasing side wins)', distOf(raw.match.m_balls), { unit: 'balls', short: 'Balls' }); }
    const sec2 = h('div', { class: 'sh-card' }), view = h('div'); root.append(sec2);
    let cur = CK._mkSel && mk.some(x => x.label === CK._mkSel) ? CK._mkSel : mk[0].label;
    const sel = S.ui.select({ label: 'Market', options: mk.map(x => ({ value: x.label, label: x.label })), value: cur, onChange: v => { CK._mkSel = cur = v; show(); } });
    const show = () => { const x = mk.find(y => y.label === cur); CK.marketView(view, x.d, { title: x.label, unit: x.unit, short: x.short, step: x.step }); };
    sec2.append(h('div', { class: 'sh-h', text: 'Totals and lines' }), sel, view); show();
    if (isTest) {
      const m = raw.match, sec3 = h('div', { class: 'sh-card' }); root.append(sec3);
      S.bar(sec3, { title: 'When the match ends', subtitle: 'share of simulated matches; days are fifths of the overs available', data: [1, 2, 3, 4, 5].map(dn => ({ label: 'Day ' + dn, value: ((m.day[dn] || 0) - (dn === 5 ? R.draw : 0)) / N })).concat([{ label: 'Draw', value: R.draw / N }]), fmt: 'pct:1', diverging: false });
    }
    // ---- players
    ['A', 'B'].forEach(k => {
      const sd = s[k], T = raw.teams[k], nme = sd.t.short, box = h('div', { class: 'sh-card' }); root.append(box);
      const inn = isTest ? '1st innings' : 'innings';
      box.append(h('div', { class: 'sh-h', text: `${sd.t.name}: batting` }));
      const bcols = [{ key: 'pos', label: '#', fmt: 'int', width: 34 }, { key: 'name', label: 'Batter', width: 150, frozen: true },
        { key: 'runs', label: 'Runs', fmt: 'num:1', desc: `Mean runs, ${inn}.`, bar: true }, { key: 'med', label: 'Median', fmt: 'int' },
        fairCol('p25', '25+', `P(25 or more), ${inn}, and the fair price.`), fairCol('p50', '50+', `P(50 or more), ${inn}.`), fairCol('p100', '100+', `P(100 or more), ${inn}.`),
        fairCol('top', 'Top bat', `Chance of being the side's top scorer in its ${inn} (ties split).`),
        { key: 'balls', label: 'Balls', fmt: 'num:0' }, { key: 'fours', label: '4s', fmt: 'num:1', desc: isTest ? 'Fours in the match.' : 'Fours.' }, { key: 'sixes', label: '6s', fmt: 'num:2', desc: isTest ? 'Sixes in the match.' : 'Sixes.' },
        { key: 'duck', label: 'Duck', fmt: 'pct:1' }];
      if (isTest) bcols.push({ key: 'rm', label: 'Match runs', fmt: 'num:1', desc: 'Mean runs over both innings.' }, fairCol('c100', '100 in match', 'A hundred in either innings.'));
      const gb = S.grid(box.appendChild(h('div')), { columns: bcols, rows: batRows(T, sd.order), height: 'auto', search: false, chips: false, footer: false, csv: `${nme}-batting.csv`, onRowClick: r => playerDrawer(r, 'bat', nme) });
      box.append(h('div', { class: 'sh-h', text: `${sd.t.name}: bowling` }));
      const wcols = [{ key: 'name', label: 'Bowler', width: 150, frozen: true }, { key: 'overs', label: 'Overs', fmt: 'num:1', desc: `Mean overs, ${inn}.` },
        { key: 'wkts', label: 'Wkts', fmt: 'num:2', desc: `Mean wickets, ${inn}.`, bar: true },
        ...(isTest ? [fairCol('p3', '3+', `P(3 or more wickets), ${inn}.`), fairCol('p5', '5+', `P(5 or more wickets), ${inn}.`)] : [fairCol('p2', '2+', 'P(2 or more wickets).'), fairCol('p3', '3+', 'P(3 or more wickets).'), fairCol('p4', '4+', 'P(4 or more wickets).')]),
        fairCol('top', 'Top bowler', `Most wickets for the side in the ${inn} (then fewest runs; ties split).`),
        { key: 'conc', label: 'Runs', fmt: 'num:1', desc: `Mean runs conceded, ${inn}.` }, { key: 'econ', label: 'Econ', fmt: 'num:2' }];
      if (isTest) wcols.push({ key: 'wm', label: 'Match wkts', fmt: 'num:2' }, { key: 'om', label: 'Match overs', fmt: 'num:1' });
      const ids = s[k === 'A' ? 'A' : 'B'].plan.map(x => x.id);
      S.grid(box.appendChild(h('div')), { columns: wcols, rows: bowlRows(T, ids), height: 'auto', search: false, chips: false, footer: false, csv: `${nme}-bowling.csv`, onRowClick: r => playerDrawer(r, 'bowl', nme) });
      void gb;
    });
    root.append(h('div', { class: 'sh-note', text: 'Click a player for his full distributions and a line pricer. Top bat and top bowler follow the usual market: the side\'s first innings.' }));
  };
  draw(); CK.odds.bind(root, draw);
};
})();
