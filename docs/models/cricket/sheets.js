/* Test / ODI workbooks: the sheets. Loaded after app.js (window.CK). */
(function () {
'use strict';
const S = Sheets, h = S.h, F = S.fmt, CK = window.CK, D = CK.D, isTest = CK.isTest, isNum = CK.isNum, fp = CK.fp;
const get = path => r => path.split('.').reduce((o, k) => (o == null ? o : o[k]), r);
const NAME = isTest ? 'Test' : 'ODI';
let WB = null;

/* ───────── Schedule ───────── */
async function schedule(panel, sheet) {
  await CK.load();
  const fx = D.fixtures, gen = D.SCH.generated_utc;
  panel.append(h('p', { class: 'ck-intro', html: `Upcoming men's ${NAME}s${gen ? `, fetched ${S.esc(gen.replace('T', ' ').replace(/:\d\dZ$/, ' UTC'))}` : ''}. Each fixture is simulated ${F.int(D.SCH.sims_per_fixture || 0)} times before the match with the announced XI when there is one, otherwise each side's most recent XI in comparable conditions. <b>Click a row</b> to open it in the Match sheet, where the XI, batting order, bowling plan, toss, pitch${isTest ? ' and time available' : ' and dew'} can all be changed and the match re-simulated.` }));
  if (!fx.length) { panel.append(h('div', { class: 'sh-note', text: 'No fixtures published yet. The Match sheet works without one: pick any two sides and a ground.' })); return; }
  const prob = k => r => r.proj ? r.proj[k] : null;
  const bar = r => { const p = r.proj; if (!p) return ''; const t = p.p_A + p.p_B + p.p_draw || 1; return `<span class="ck-bar3" title="${S.esc(r.A)} ${F.pct(p.p_A, 0)}${isTest ? ' · draw ' + F.pct(p.p_draw, 0) : ''} · ${S.esc(r.B)} ${F.pct(p.p_B, 0)}"><i class="a" style="width:${100 * p.p_A / t}%"></i><i class="d" style="width:${100 * p.p_draw / t}%"></i><i class="b" style="width:${100 * p.p_B / t}%"></i></span>`; };
  const status = r => r.status === 'in' ? '<span class="ck-chip live">In progress</span>' : !r.modelled ? '<span class="ck-chip off">Not modelled</span>' : '<span class="ck-chip">Upcoming</span>';
  const cols = [
    { key: 'date', label: 'Date', type: 'text', width: 128, frozen: true, desc: 'First day (local).', render: v => S.esc(CK.dateStr(v)) },
    { key: 'match', label: 'Match', type: 'text', width: 210, frozen: true, get: r => `${r.A} v ${r.B}`, desc: 'Home side first when the ground is in one side\'s country.' },
    { key: 'desc', label: 'Game', type: 'text', width: 96 },
    { key: 'st', label: 'Status', type: 'cat', width: 104, get: r => r.status === 'in' ? 'In progress' : r.modelled ? 'Upcoming' : 'Not modelled', render: (v, r) => status(r) },
    { key: 'pa', label: 'Side A', group: 'Model', get: prob('p_A'), fmt: 'pct:1', heat: { type: 'seq', domain: [0, 1] }, desc: 'Win probability of the first-named side.' },
    ...(isTest ? [{ key: 'pd', label: 'Draw', group: 'Model', get: prob('p_draw'), fmt: 'pct:1', heat: { type: 'seq', domain: [0, 1] } }] : []),
    { key: 'pb', label: 'Side B', group: 'Model', get: prob('p_B'), fmt: 'pct:1', heat: { type: 'seq', domain: [0, 1] }, desc: 'Win probability of the second-named side.' },
    { key: 'bar', label: 'Split', group: 'Model', type: 'text', width: 112, get: r => r.proj ? r.proj.p_A : null, render: (v, r) => bar(r), filter: false, csv: () => '' },
    { key: 'fa', label: 'Fair A', group: 'Fair price', get: prob('p_A'), fmt: v => fp(v), type: 'num', desc: 'No-vig price of the first-named side (toggle American / decimal in the header).' },
    ...(isTest ? [{ key: 'fd', label: 'Fair draw', group: 'Fair price', get: prob('p_draw'), fmt: v => fp(v), type: 'num' }] : []),
    { key: 'fb', label: 'Fair B', group: 'Fair price', get: prob('p_B'), fmt: v => fp(v), type: 'num' },
    { key: 'ta', label: 'A bat first', group: 'Projected', get: r => r.proj && r.proj.A.bat_first_total, fmt: 'num:0', desc: `Mean ${isTest ? 'first-innings' : ''} total when the first-named side bats first.` },
    { key: 'tb', label: 'B bat first', group: 'Projected', get: r => r.proj && r.proj.B.bat_first_total, fmt: 'num:0' },
    ...(isTest ? [{ key: 'ov', label: 'Overs', group: 'Projected', get: r => r.proj && r.proj.overs_mean, fmt: 'num:0', desc: 'Mean overs bowled in the match.' }] : [{ key: 'six', label: 'Sixes', group: 'Projected', get: r => r.proj && r.proj.match_sixes, fmt: 'num:1' }]),
    { key: 'topa', label: 'Top bat A', group: 'Projected', type: 'text', width: 150, get: r => r.proj && r.proj.A.top_bat[0] ? `${r.proj.A.top_bat[0].name} ${F.num(r.proj.A.top_bat[0].runs, 0)}` : null, desc: 'Highest projected first-innings runs.' },
    { key: 'topb', label: 'Top bat B', group: 'Projected', type: 'text', width: 150, get: r => r.proj && r.proj.B.top_bat[0] ? `${r.proj.B.top_bat[0].name} ${F.num(r.proj.B.top_bat[0].runs, 0)}` : null },
    { key: 'ground', label: 'Ground', group: 'Fixture', type: 'text', width: 220, get: r => r.venue_name },
    { key: 'country', label: 'Host', group: 'Fixture', type: 'cat', width: 110 },
    { key: 'series', label: 'Series', group: 'Fixture', type: 'text', width: 230 },
    { key: 'xi', label: 'Lineups', group: 'Fixture', type: 'cat', width: 150, get: r => !r.modelled ? r.reason : ['A', 'B'].every(k => /announced/.test(r.lineups[k].source)) ? 'Announced XIs' : ['A', 'B'].some(k => /announced/.test(r.lineups[k].source)) ? 'One announced XI' : 'Most recent XIs', desc: 'Where the simulated lineups came from.' },
    { key: 'toss', label: 'Toss', group: 'Fixture', type: 'text', width: 170, get: r => r.toss ? `${CK.short(r.toss.winner)} won, chose to ${r.toss.decision}` : null },
  ];
  const tools = h('span', { class: 'ck-links' }, h('a', { href: CK.matchHash({}), text: 'Custom match →', onclick: e => { e.preventDefault(); WB.activate('match', { push: true, params: {} }); } }));
  const grid = sheet.grid(panel, { height: 'auto', frozen: innerWidth < 640 ? 1 : 2, columns: cols, rows: fx, sort: 'date', csv: `${CK.FMT}-schedule.csv`, footer: false, tools, searchPlaceholder: 'Search sides, grounds, series',
    rowClass: r => r.modelled ? '' : 'dim',
    onRowClick: r => { if (!r.modelled) return; WB.activate('match', { push: true, params: { fx: String(r.id) } }); } });
  CK.odds.bind(panel, () => grid.setRows(fx));
  panel.append(h('div', { class: 'ck-legend' }, h('span', null, h('i', { style: { background: 'var(--s1)' } }), 'first-named side'), isTest ? h('span', null, h('i', { style: { background: 'var(--div-mid)' } }), 'draw') : null, h('span', null, h('i', { style: { background: 'var(--s2)' } }), 'second-named side'),
    h('span', { class: 'muted', text: 'Matches in progress show the pre-match projection, not a live one. Sides without ball-by-ball data on cricsheet (Afghanistan, most associates) are listed but not simulated.' })));
}

/* ───────── Match (simulator) ───────── */
async function match(panel, sheet) {
  await CK.load();
  const SP = await CK.loadSimParams();
  const left = h('div', { class: 'sh-card ck-simctl' }), right = h('div', { class: 'ck-simout' });
  panel.append(h('div', { class: 'ck-simgrid' }, left, right));
  const prog = S.ui.progress(), status = h('span', { class: 'sh-note num' }), res = h('div', { class: 'sh-section', style: { gap: '14px' } });
  right.append(h('div', { class: 'ck-progrow' }, prog, status), res);
  let job = null, last = null, stale = false, runTok = 0;
  const st = () => CK.matchState(sheet, SP);
  const CLEAR = { ao: null, ap: null, bo: null, bp: null };
  const markStale = () => { if (last && !stale) { stale = true; status.textContent = 'Settings changed. Run again to update.'; } };
  const rated = id => !!(SP.batters[id] || SP.bowlers[id]);

  function drawControls() {
    const s = st(); left.innerHTML = '';
    const set = (o, re = true) => { sheet.set(o); markStale(); if (re) drawControls(); };
    if (s.fx) {
      const f = s.fx;
      left.append(h('div', { class: 'ck-fx' }, h('div', { class: 't', text: `${f.A} v ${f.B}` }), h('div', { class: 'sh-note', text: `${f.desc} · ${f.series}` }),
        h('div', { class: 'sh-note', text: `${CK.dateStr(f.date)} · ${f.venue_name}${f.status === 'in' ? ' · in progress (this is the pre-match view)' : ''}` })));
    } else if (s.fxAny && !s.fxAny.modelled) left.append(h('div', { class: 'sh-note warn', text: `${s.fxAny.A} v ${s.fxAny.B} cannot be simulated: ${s.fxAny.reason}. Showing a custom match instead.` }));
    const topts = D.teams.map(t => ({ value: t.short, label: `${t.short} · ${t.name}` }));
    const pick = (k, v) => { const o = Object.assign({ fx: null, g: null, tw: null, td: null }, CLEAR); o.a = k === 'a' ? v : (v === s.a.short ? s.b.short : s.a.short); o.b = k === 'b' ? v : (v === s.b.short ? s.a.short : s.b.short); set(o); };
    const sa = S.ui.select({ label: 'Side A', options: topts, value: s.a.short, onChange: v => pick('a', v) });
    const sb = S.ui.select({ label: 'Side B', options: topts, value: s.b.short, onChange: v => pick('b', v) });
    // grounds: fixture / home countries first, then every ground by country
    const gopts = [];
    const seen = new Set(), push = (value, label) => { if (!seen.has(value)) { seen.add(value); gopts.push({ value, label }); } };
    if (s.fx) push(s.fx.venue ? 'v:' + s.fx.venue : (s.fx.env_known ? 'c:' + s.fx.country : 'n'), `Fixture ground · ${s.fx.venue_name}`);
    [s.a, s.b].forEach(t => { if (SP.env[t.name]) push('c:' + t.name, `In ${t.name} (no specific ground)`); });
    push('n', 'Neutral ground, average conditions');
    D.venues.filter(v => SP.venues[v.venue]).sort((x, y) => x.country.localeCompare(y.country) || y.matches - x.matches).forEach(v => push('v:' + v.venue, `${v.country} · ${v.name}`));
    Object.keys(SP.env).filter(c => c !== '_default').sort().forEach(c => push('c:' + c, `In ${c} (no specific ground)`));
    const gsel = S.ui.select({ label: 'Ground', options: gopts, value: s.g, onChange: v => set(Object.assign({ g: v }, s.custom ? CLEAR : {})) });
    const tw = S.ui.select({ label: 'Toss won by', options: [{ value: '', label: 'Unknown (half each way)' }, { value: 'a', label: s.a.short }, { value: 'b', label: s.b.short }], value: s.tw, onChange: v => set({ tw: v || 'x' }) });
    const td = S.ui.segmented({ label: 'Chooses to', options: [{ value: 'bat', label: 'Bat' }, { value: 'bowl', label: 'Bowl' }], value: s.td, onChange: v => set({ td: v }, false) });
    const CO = SP.conditions || {}, lab = { normal: 'Normal for the ground', flat: 'Flat (a road)', green: 'Green seamer', turning: 'Dry, turning', tough: 'Hard to bat on', none: 'None', heavy: 'Heavy' };
    const pi = CO.pitch ? S.ui.select({ label: 'Pitch', options: ['normal', 'flat', 'green', 'turning', 'tough'].filter(k => CO.pitch[k]).map(k => ({ value: k, label: lab[k] })), value: s.pitch, onChange: v => set({ pi: v === 'normal' ? null : v }, false) }) : null;
    const dw = CO.dew ? S.ui.select({ label: 'Dew (second innings)', options: ['none', 'normal', 'heavy'].filter(k => CO.dew[k]).map(k => ({ value: k, label: k === 'normal' ? 'Normal' : lab[k] })), value: s.dew, onChange: v => set({ dw: v === 'normal' ? null : v }, false) }) : null;
    const ov = isTest ? S.ui.select({ label: 'Time available', options: [{ value: '', label: 'Typical for the host (weather curve)' }, { value: 'full', label: 'No time lost (450 overs)' }, { value: 'm45', label: 'Half a day lost (−45 overs)' }, { value: 'm90', label: 'A day lost (−90 overs)' }, { value: 'm180', label: 'Two days lost (−180 overs)' }], value: s.ov, onChange: v => set({ ov: v || null }, false) }) : null;
    const nopts = isTest ? [2000, 4000, 10000, 20000] : [5000, 10000, 20000, 50000];
    const sims = S.ui.select({ label: 'Simulations', options: nopts.map(v => ({ value: v, label: F.int(v) })), value: s.n, onChange: v => set({ n: v === s.nDef ? null : v }, false) });
    const run = S.ui.button({ label: 'Run simulation', primary: true, onClick: () => go(true) });
    run.classList.add('ck-run');
    const reset = S.ui.button({ label: 'Reset', onClick: () => { sheet.set(Object.assign({ g: null, tw: null, td: null, n: null, pi: null, dw: null, ov: null }, CLEAR)); markStale(); drawControls(); } });
    const eA = CK.checkPlan(s.A.plan, s.A.order).errs, eB = CK.checkPlan(s.B.plan, s.B.order).errs;
    if (eA.length || eB.length) run.disabled = true;
    left.append(S.ui.row(sa, sb), gsel, S.ui.row(tw, s.tw ? td : h('span')), S.ui.row(pi || h('span'), dw || ov || h('span')), S.ui.row(sims, run, reset));
    left.append(h('div', { class: 'sh-note', text: `${s.home ? (s.home === 'A' ? s.a.short : s.b.short) + ' are at home' : 'Neutral ground: no home advantage'}${s.batFirst ? `; ${s.batFirst === 'A' ? s.a.short : s.b.short} bat first` : ''}. Pitch${isTest ? ' and time' : ' and dew'} are scenario dials sized from the data (Method), not forecasts for this match.` }));
    if (eA.length || eB.length) left.append(h('div', { class: 'sh-note bad', text: 'Fix the bowling plan before running: ' + [...eA.map(e => s.a.short + ': ' + e), ...eB.map(e => s.b.short + ': ' + e)].join('; ') + '.' }));
    left.append(sideEditor(s, 'a'), sideEditor(s, 'b'));
    left.append(h('div', { class: 'sh-note', text: `Seed ${CK.SIM_SEED}, ${CK.SIM_WORKERS} workers: the same link reproduces the same numbers. A player marked * has no rating in this format and uses the prior for his role plus his side's team term.` }));
  }

  function sideEditor(s, k) {
    const sd = k === 'a' ? s.A : s.B, t = sd.t, box = h('div', { class: 'ck-roster' });
    const put = o => {
      const x = {};
      if (o.order) x[k + 'o'] = o.order.join() === sd.def.order.slice(0, 11).join() ? null : o.order.join(',');
      if (o.plan) x[k + 'p'] = CK.planStr(o.plan) === CK.planStr(sd.def.plan) ? null : CK.planStr(o.plan);
      sheet.set(x); markStale(); drawControls();
    };
    box.append(h('div', { class: 'ck-rhead' }, h('div', { class: 'sh-h', text: `${t.name} XI` }), CK.sideDefault(sd) ? h('span', { class: 'sh-note', text: 'default' }) : S.ui.button({ label: 'Reset ' + t.short, onClick: () => { sheet.set({ [k + 'o']: null, [k + 'p']: null }); markStale(); drawControls(); } })));
    box.append(h('div', { class: 'sh-note', text: 'Default: ' + sd.source + '.' }));
    const blab = id => { const p = CK.player(id); return p && p.bat ? `avg ${F.num(p.bat.all.avg, 1)} · SR ${F.num(p.bat.all.sr, 0)}` : 'no batting record'; };
    box.append(S.ui.dragList({ label: 'Batting order (drag, or focus and Alt+↑/↓)', items: sd.order.map(id => ({ id, label: CK.pname(id) + (rated(id) ? '' : ' *'), sub: blab(id) })), onChange: ids => put({ order: ids }) }));
    // swap a player
    const outSel = S.ui.select({ label: 'Take out', options: sd.order.map(id => ({ value: id, label: CK.pname(id) })), value: sd.order[sd.order.length - 1] });
    const sq = (t.squad || []).map(x => x.id).filter(id => !sd.order.includes(id));
    const mine = D.players.filter(p => p.team === t.name && !sd.order.includes(p.id) && !sq.includes(p.id)).map(p => p.id);
    const other = D.players.filter(p => p.team !== t.name && !sd.order.includes(p.id)).sort((x, y) => String(x.team).localeCompare(String(y.team)) || x.name.localeCompare(y.name)).map(p => p.id);
    const plab = id => { const p = CK.player(id); if (!p) return CK.pname(id); const bits = []; if (p.bat) bits.push('bat ' + F.num(p.bat.all.avg, 0)); if (p.bowl) bits.push('bowl ' + F.num(p.bowl.all.avg, 0)); return `${p.name} · ${bits.join(' / ')}`; };
    const inSel = S.ui.select({ label: 'Bring in (squad first, then anyone)', options: sq.map(id => ({ value: id, label: `${plab(id)} · squad` })).concat(mine.map(id => ({ value: id, label: plab(id) })), other.map(id => ({ value: id, label: `${plab(id)} · ${CK.short(CK.player(id).team)}` }))), value: sq[0] || mine[0] || other[0] });
    const swap = S.ui.button({ label: 'Swap', onClick: () => {
      const o = outSel.value, n = inSel.value; if (!o || !n) return;
      const order = sd.order.map(id => id === o ? n : id);
      let plan = sd.plan.map(x => Object.assign({}, x));
      const had = plan.find(x => x.id === o), pn = CK.player(n), sqn = (t.squad || []).find(x => x.id === n);
      // the incoming player takes the outgoing bowler's workload only if he bowls; otherwise it is left to rebalance
      if (had && pn && pn.bowl && pn.bowl.role && !/part/.test(pn.bowl.role)) had.id = n;
      else {
        plan = plan.filter(x => x.id !== o);
        if (sqn && sqn.usage && sqn.usage.some(v => v > 0) && !plan.some(x => x.id === n)) { const r = { id: n }; CK.PH.forEach((q, i) => { r[q] = isTest ? +(100 * sqn.usage[i]).toFixed(1) : Math.round(sqn.usage[i]); }); if (CK.PH.some(q => r[q] > 0)) plan.push(r); }
      }
      put({ order, plan });
    } });
    box.append(h('div', { class: 'ck-swap' }, outSel, inSel, swap));
    // bowling plan
    const ck = CK.checkPlan(sd.plan, sd.order);
    const tb = h('table', { class: 'sh-tbl ck-ptab' });
    tb.append(h('thead', null, h('tr', null, h('th', { text: 'Bowler' }), ...(isTest ? ['New', 'Mid', 'Old'] : ['PP', 'Mid', 'Death']).map((x, i) => h('th', { class: 'n', text: x, title: `${CK.PH_LABEL[i]}: ${CK.PH_HINT[i].toLowerCase()}` })), h('th', { class: 'n', text: 'Avg', title: 'True bowling average (lower is better)' }))));
    const bd = h('tbody'); tb.append(bd);
    const tot = x => CK.PH.reduce((a, q) => a + (+x[q] || 0), 0);
    const cand = sd.order.filter(id => sd.plan.some(x => x.id === id) || (CK.player(id) && CK.player(id).bowl));
    cand.sort((x, y) => tot(sd.plan.find(z => z.id === y) || {}) - tot(sd.plan.find(z => z.id === x) || {}));
    cand.forEach(id => {
      const row = sd.plan.find(x => x.id === id) || { id }, p = CK.player(id);
      const tr = h('tr', null, h('td', { class: 'ck-pn', text: CK.pname(id) + (p && p.bowl_type ? ' · ' + p.bowl_type : '') }));
      CK.PH.forEach((q, i) => {
        const inp = h('input', { type: 'number', min: 0, max: isTest ? 100 : 10, step: isTest ? 1 : 1, class: 'ck-ov', value: +(row[q] || 0), 'aria-label': `${CK.pname(id)} ${CK.PH_LABEL[i]}` });
        inp.addEventListener('change', () => { let v = Math.max(0, +inp.value || 0); v = isTest ? Math.min(100, +v.toFixed(1)) : Math.min(10, Math.round(v)); const plan = sd.plan.map(x => Object.assign({}, x)); let r = plan.find(x => x.id === id); if (!r) { r = { id }; CK.PH.forEach(z => { r[z] = 0; }); plan.push(r); } r[q] = v; put({ plan }); });
        tr.append(h('td', { class: 'n' }, inp));
      });
      tr.append(h('td', { class: 'n muted', text: p && p.bowl ? F.num(p.bowl.all.avg, 1) : '–' }));
      bd.append(tr);
    });
    bd.append(h('tr', { class: 'ck-tot' }, h('td', { text: isTest ? 'Total' : 'Total (need 10 / 30 / 10)' }), ...ck.tot.map((v, i) => h('td', { class: 'n' + (!isTest && v !== [10, 30, 10][i] ? ' bad' : ''), text: isTest ? F.num(v, 0) + '%' : String(v) })), h('td')));
    box.append(h('div', { class: 'ui-l', text: 'Bowling plan' }), h('div', { class: 'sh-note', text: isTest ? 'Share (%) of the side\'s overs while the ball is new (its first 20 overs), in the middle (21–55) and old (56–80). Each column is rescaled to 100%. Spells are drawn from these shares, so no two simulated innings are bowled the same way.' : 'Whole overs per phase: powerplay (1–10), middle (11–40), death (41–50). At most 10 a bowler.' }), h('div', { class: 'sh-tbl-wrap' }, tb));
    return box;
  }
  function go(fromUser) {
    if (job) job.cancel();
    const tok = ++runTok, s = st();
    if (CK.checkPlan(s.A.plan, s.A.order).errs.length || CK.checkPlan(s.B.plan, s.B.order).errs.length) { status.textContent = 'Fix the bowling plan first.'; return; }
    const params = { A: CK.spec(s.A, SP), B: CK.spec(s.B, SP), opts: CK.simOpts(s), sims: s.n };
    prog.set(0); status.textContent = `Running ${F.int(s.n)} matches…`; stale = false;
    const t0 = performance.now();
    CK.simulate(params, f => { if (tok === runTok) prog.set(f); }).then(w => { if (tok !== runTok) { w.job.cancel(); const e = new Error('superseded'); e.cancelled = true; throw e; } job = w.job; return w.job.promise; }).then(raw => {
      if (tok !== runTok) return;
      job = null; prog.set(1); last = { s, raw };
      status.textContent = `${F.int(raw.n)} matches in ${F.num((performance.now() - t0) / 1000, 1)} s.`;
      CK.simLast = { raw, params, state: s };
      CK.renderResults(res, raw, s);
      if (fromUser === true && innerWidth < 1000) right.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }).catch(e => { job = null; if (e && e.cancelled) return; status.textContent = ''; res.innerHTML = ''; res.append(S.errorEl(e, 'Simulation failed')); });
  }
  drawControls();
  sheet.onState(() => { drawControls(); go(); });
  go();
}

/* ───────── Batters / Bowlers ───────── */
const phaseShort = isTest ? ['New', 'Mid', 'Old'] : ['PP', 'Mid', 'Death'];
function batCols() {
  const a = k => (D.P.avg_bat && D.P.avg_bat[k]) || {};
  const main = isTest ? 'avg' : 'sr';
  return [
    { key: 'name', label: 'Batter', type: 'text', width: 170, frozen: true },
    { key: 'team', label: 'Side', type: 'cat', width: 64, frozen: true, get: r => CK.short(r.team) },
    { key: 'role', label: 'Role', type: 'cat', width: 104, get: r => r.bat && CK.ROLE[r.bat.role], desc: 'From his mean batting position over his last ten innings.' },
    { key: 'hand', label: 'Hand', type: 'cat', width: 56, get: r => r.bat_hand },
    { key: 'age', label: 'Age', fmt: 'num:1', width: 56 },
    { key: 'avg', label: 'True avg', group: 'Rating', get: get('bat.all.avg'), fmt: 'num:1', heat: { center: a('all').avg ?? 30 }, desc: 'Runs per dismissal against the reference deliveries (recent matches between full members), with the real opponents, grounds and match states. Shrunk toward players like him.' },
    { key: 'sr', label: 'True SR', group: 'Rating', get: get('bat.all.sr'), fmt: 'num:1', heat: { center: a('all').sr ?? 60 }, desc: 'Runs per 100 balls on the same deliveries.' },
    { key: 'bpd', label: 'Balls/out', group: 'Rating', get: r => r.bat ? 100 / r.bat.all.out_pct : null, fmt: 'num:0', desc: 'Balls faced per dismissal.' },
    { key: 'rv', label: 'Value/100b', group: 'Rating', get: get('bat.vs_avg.all.rv100'), fmt: 'signed:1', heat: { center: 0 }, desc: `Runs added per 100 balls against the average batter on the same deliveries. A dismissal costs ${isTest ? 'the reference runs per wicket' : 'the runs a wicket is worth at that point of an innings'}.` },
    { key: 'sd', label: '± avg', group: 'Rating', get: get('bat.sd.avg'), fmt: 'num:1', desc: 'Posterior SD of the true average from his own coefficients (somewhat too small: it ignores the other terms).' },
    { key: 'pace', label: isTest ? 'Avg v pace' : 'SR v pace', group: 'Splits', get: get('bat.pace.' + main), fmt: 'num:1', heat: { center: a('pace')[main] } },
    { key: 'spin', label: isTest ? 'Avg v spin' : 'SR v spin', group: 'Splits', get: get('bat.spin.' + main), fmt: 'num:1', heat: { center: a('spin')[main] } },
    { key: 'home', label: 'Avg home', group: 'Splits', get: get('bat.home.avg'), fmt: 'num:1', heat: { center: a('home').avg } },
    { key: 'away', label: 'Avg away', group: 'Splits', get: get('bat.away.avg'), fmt: 'num:1', heat: { center: a('away').avg }, desc: 'Away includes neutral grounds.' },
    ...[0, 1, 2].map(i => ({ key: 'p' + i, label: `${isTest ? 'Avg' : 'SR'} ${phaseShort[i]}`, group: 'Phases', get: get(`bat.p${i}.${main}`), fmt: 'num:1', heat: { center: a('p' + i)[main] }, desc: `${D.P.phase_labels[i]}: every reference delivery of that phase.` })),
    ...CK.TYPES.map(([k, l]) => ({ key: 't_' + k, label: l, group: 'By bowling type', get: get(`bat.by_type.${k}.d_avg`), fmt: 'signed:1', heat: { center: 0 }, desc: `True average against ${l.toLowerCase()} minus the average batter's on the same deliveries.` })),
    { key: 'c_inns', label: 'Inns', group: 'Career', get: get('bat.career.inns'), fmt: 'int' },
    { key: 'c_runs', label: 'Runs', group: 'Career', get: get('bat.career.runs'), fmt: 'int' },
    { key: 'c_avg', label: 'Avg', group: 'Career', get: get('bat.career.avg'), fmt: 'num:1' },
    { key: 'c_sr', label: 'SR', group: 'Career', get: get('bat.career.sr'), fmt: 'num:1' },
    { key: 'c_hs', label: 'HS', group: 'Career', get: get('bat.career.hs'), fmt: 'int' },
    { key: 'c_100', label: '100s', group: 'Career', get: get('bat.career.hundreds'), fmt: 'int' },
    { key: 'r_inns', label: 'Inns', group: 'Recent', get: get('bat.recent.inns'), fmt: 'int', desc: `Since ${D.P.pool_since}.` },
    { key: 'r_avg', label: 'Avg', group: 'Recent', get: get('bat.recent.avg'), fmt: 'num:1' },
    { key: 'r_sr', label: 'SR', group: 'Recent', get: get('bat.recent.sr'), fmt: 'num:1' },
    { key: 'last', label: 'Last played', group: 'Recent', type: 'text', width: 96, get: r => r.last_played },
  ];
}
function bowlCols() {
  const a = k => (D.P.avg_bowl && D.P.avg_bowl[k]) || {};
  return [
    { key: 'name', label: 'Bowler', type: 'text', width: 170, frozen: true },
    { key: 'team', label: 'Side', type: 'cat', width: 64, frozen: true, get: r => CK.short(r.team) },
    { key: 'type', label: 'Type', type: 'cat', width: 64, get: r => r.bowl_type || (r.bowl_group ? r.bowl_group + '?' : null), desc: 'A trailing ? means pace / spin was inferred from how his deliveries behave.' },
    { key: 'role', label: 'Role', type: 'cat', width: 120, get: r => r.bowl && CK.BROLE[r.bowl.role] },
    { key: 'age', label: 'Age', fmt: 'num:1', width: 56 },
    { key: 'avg', label: 'True avg', group: 'Rating', get: get('bowl.all.avg'), fmt: 'num:1', heat: { center: a('all').avg ?? 32, reverse: true }, desc: 'Runs conceded per wicket against the reference deliveries, in his own mix of phases. Lower is better.' },
    { key: 'econ', label: 'True econ', group: 'Rating', get: get('bowl.all.econ'), fmt: 'num:2', heat: { center: a('all').econ ?? 4, reverse: true } },
    { key: 'sr', label: 'Balls/wkt', group: 'Rating', get: get('bowl.all.sr'), fmt: 'num:0', heat: { center: a('all').sr ?? 60, reverse: true } },
    { key: 'rv', label: 'Value/over', group: 'Rating', get: r => r.bowl ? -r.bowl.vs_avg.all.rv_over : null, fmt: 'signed:2', heat: { center: 0 }, desc: 'Runs saved per over against the average bowler on the same deliveries, wickets valued in runs. Higher is better.' },
    { key: 'sd', label: '± avg', group: 'Rating', get: get('bowl.sd.avg'), fmt: 'num:1' },
    { key: 'rhb', label: 'Avg v RHB', group: 'Splits', get: get('bowl.rhb.avg'), fmt: 'num:1', heat: { center: a('rhb').avg, reverse: true } },
    { key: 'lhb', label: 'Avg v LHB', group: 'Splits', get: get('bowl.lhb.avg'), fmt: 'num:1', heat: { center: a('lhb').avg, reverse: true } },
    { key: 'home', label: 'Avg home', group: 'Splits', get: get('bowl.home.avg'), fmt: 'num:1', heat: { center: a('home').avg, reverse: true } },
    { key: 'away', label: 'Avg away', group: 'Splits', get: get('bowl.away.avg'), fmt: 'num:1', heat: { center: a('away').avg, reverse: true } },
    ...[0, 1, 2].map(i => ({ key: 'p' + i, label: `${isTest ? 'Avg' : 'Econ'} ${phaseShort[i]}`, group: 'Phases', get: get(`bowl.p${i}.${isTest ? 'avg' : 'econ'}`), fmt: isTest ? 'num:1' : 'num:2', heat: { center: a('p' + i)[isTest ? 'avg' : 'econ'], reverse: true }, desc: D.P.phase_labels[i] })),
    ...[0, 1, 2].map(i => ({ key: 'mx' + i, label: phaseShort[i] + ' %', group: 'Usage', get: r => r.bowl && r.bowl.phase_mix ? r.bowl.phase_mix[i] : null, fmt: 'pct:0', heat: { type: 'seq', domain: [0, 1] }, desc: 'Share of his recency-weighted balls bowled in the phase.' })),
    { key: 'opm', label: 'Overs/match', group: 'Usage', get: get('bowl.overs_per_match'), fmt: 'num:1' },
    { key: 'c_m', label: 'Matches', group: 'Career', get: get('bowl.career.matches'), fmt: 'int' },
    { key: 'c_w', label: 'Wkts', group: 'Career', get: get('bowl.career.wkts'), fmt: 'int' },
    { key: 'c_avg', label: 'Avg', group: 'Career', get: get('bowl.career.avg'), fmt: 'num:1' },
    { key: 'c_econ', label: 'Econ', group: 'Career', get: get('bowl.career.econ'), fmt: 'num:2' },
    { key: 'r_w', label: 'Wkts', group: 'Recent', get: get('bowl.recent.wkts'), fmt: 'int', desc: `Since ${D.P.pool_since}.` },
    { key: 'r_avg', label: 'Avg', group: 'Recent', get: get('bowl.recent.avg'), fmt: 'num:1' },
    { key: 'last', label: 'Last played', group: 'Recent', type: 'text', width: 96, get: r => r.last_played },
  ];
}
function splitTable(el, blk, rows, cols) {
  S.table(el, [{ key: 'l', label: '' }].concat(cols.map(([k, l, f]) => ({ key: k, label: l, fmt: f }))), rows.filter(([k]) => blk[k]).map(([k, l]) => Object.assign({ l }, blk[k])));
}
function openBatter(p, grid) {
  S.drawer.open({ title: p.name, sub: [p.team, p.bat.role && CK.ROLE[p.bat.role], p.bat_hand && (p.bat_hand === 'L' ? 'left-hand bat' : 'right-hand bat'), p.age && 'age ' + F.num(p.age, 0)].filter(Boolean).join(' · '),
    nav: grid ? { prev: () => grid.step(-1), next: () => grid.step(1) } : null, keepScroll: true, body: el => {
      const b = p.bat;
      el.append(S.tiles([{ label: 'True average', value: F.num(b.all.avg, 1), sub: '± ' + F.num(b.sd.avg, 1) }, { label: 'True strike rate', value: F.num(b.all.sr, 1), sub: '± ' + F.num(b.sd.sr, 1) },
        { label: 'Value per 100 balls', value: F.signed(b.vs_avg.all.rv100, 1), sub: 'v average batter' }, { label: 'Balls per dismissal', value: F.num(100 / b.all.out_pct, 0) }]));
      const C = [['avg', 'Avg', 'num:1'], ['sr', 'SR', 'num:1'], ['bnd_pct', 'Boundary %', 'num:1'], ['dot_pct', 'Dot %', 'num:1']];
      el.append(h('div', { class: 'ck-sub', text: 'Splits (true rates on the reference deliveries)' }));
      splitTable(el.appendChild(h('div')), b, [['all', 'All (his own phase mix)'], ['pace', 'v pace'], ['spin', 'v spin'], ['home', 'At home'], ['away', 'Away / neutral'], ['p0', D.P.phase_labels[0]], ['p1', D.P.phase_labels[1]], ['p2', D.P.phase_labels[2]]], C);
      const bt = CK.TYPES.filter(([k]) => b.by_type && b.by_type[k]).map(([k, l]) => ({ label: l, value: b.by_type[k].d_avg, desc: `avg ${F.num(b.by_type[k].avg, 1)}, SR ${F.num(b.by_type[k].sr, 1)}` }));
      if (bt.length) S.bar(el.appendChild(h('div')), { title: 'Average v each bowling type, against the average batter', data: bt, center: 0, fmt: 'signed:1' });
      const kv = [];
      if (b.career) kv.push(['Career', `${F.int(b.career.runs)} runs @ ${F.num(b.career.avg, 1)}, SR ${F.num(b.career.sr, 1)}, ${b.career.inns} inns, HS ${b.career.hs}, ${b.career.hundreds} hundreds`]);
      if (b.recent) kv.push([`Since ${D.P.pool_since}`, `${F.int(b.recent.runs)} runs @ ${F.num(b.recent.avg, 1)}, SR ${F.num(b.recent.sr, 1)}, ${b.recent.inns} inns`]);
      kv.push(['Last played', p.last_played || '–']);
      if (b.inactive_factor < 0.999) kv.push(['Inactivity', `individual rating kept at ${F.pct(b.inactive_factor, 0)}; the rest reverts to players like him`]);
      el.append(S.kv(kv));
    } });
}
function openBowler(p, grid) {
  S.drawer.open({ title: p.name, sub: [p.team, p.bowl.role && CK.BROLE[p.bowl.role], p.bowl_type, p.age && 'age ' + F.num(p.age, 0)].filter(Boolean).join(' · '),
    nav: grid ? { prev: () => grid.step(-1), next: () => grid.step(1) } : null, keepScroll: true, body: el => {
      const b = p.bowl;
      el.append(S.tiles([{ label: 'True average', value: F.num(b.all.avg, 1), sub: '± ' + F.num(b.sd.avg, 1) }, { label: 'True economy', value: F.num(b.all.econ, 2), sub: '± ' + F.num(b.sd.econ, 2) },
        { label: 'Balls per wicket', value: F.num(b.all.sr, 0) }, { label: 'Value per over', value: F.signed(-b.vs_avg.all.rv_over, 2), sub: 'runs saved v average' }]));
      const C = [['avg', 'Avg', 'num:1'], ['econ', 'Econ', 'num:2'], ['sr', 'Balls/wkt', 'num:0'], ['dot_pct', 'Dot %', 'num:1']];
      el.append(h('div', { class: 'ck-sub', text: 'Splits (true rates on the reference deliveries)' }));
      splitTable(el.appendChild(h('div')), b, [['all', 'All (his own phase mix)'], ['rhb', 'v right-handers'], ['lhb', 'v left-handers'], ['home', 'At home'], ['away', 'Away / neutral'], ['p0', D.P.phase_labels[0]], ['p1', D.P.phase_labels[1]], ['p2', D.P.phase_labels[2]]], C);
      const kv = [];
      if (b.career) kv.push(['Career', `${b.career.wkts} wickets @ ${F.num(b.career.avg, 1)}, econ ${F.num(b.career.econ, 2)}, ${b.career.matches} matches`]);
      if (b.recent) kv.push([`Since ${D.P.pool_since}`, `${b.recent.wkts} wickets @ ${F.num(b.recent.avg, 1)}, econ ${F.num(b.recent.econ, 2)}`]);
      kv.push(['Last played', p.last_played || '–']);
      if (p.style_inferred) kv.push(['Bowling type', 'pace / spin inferred from his deliveries (no label on file)']);
      el.append(S.kv(kv));
    } });
}
/** rows + a toolbar toggle: players with no match in the last two years are hidden until asked for */
function activeFilter(sheet, all, apply) {
  const latest = D.players.reduce((m, p) => (p.last_played && p.last_played > m ? p.last_played : m), '');
  const cut = new Date(new Date(latest + 'T00:00:00Z') - 730 * 864e5).toISOString().slice(0, 10);
  const active = all.filter(p => p.last_played && p.last_played >= cut);
  const rows = () => (sheet.get('all') === '1' ? all : active);
  const tog = S.ui.toggle({ label: `Include inactive (${all.length - active.length})`, value: sheet.get('all') === '1', onChange: v => { sheet.set({ all: v ? '1' : null }); apply(rows()); } });
  tog.title = `Players with no ${NAME} since ${cut}.`;
  return { rows, tools: tog };
}
async function batters(panel, sheet) {
  await CK.load();
  const all = D.players.filter(p => p.bat && p.bat.career && p.bat.career.balls >= (isTest ? 120 : 60));
  let g = null;
  const f = activeFilter(sheet, all, r => g.setRows(r));
  g = sheet.grid(panel, { columns: batCols(), rows: f.rows(), sort: '-rv', csv: `${CK.FMT}-batters.csv`, tools: f.tools, groups: ['Rating', 'Splits', 'Phases', 'By bowling type', 'Career', 'Recent'].map(id => ({ id, label: id, hidden: id === 'By bowling type' })), onRowClick: r => openBatter(r, g) });
}
async function bowlers(panel, sheet) {
  await CK.load();
  const all = D.players.filter(p => p.bowl && p.bowl.career && p.bowl.career.balls >= (isTest ? 300 : 120));
  let g = null;
  const f = activeFilter(sheet, all, r => g.setRows(r));
  g = sheet.grid(panel, { columns: bowlCols(), rows: f.rows(), sort: '-rv', csv: `${CK.FMT}-bowlers.csv`, tools: f.tools, onRowClick: r => openBowler(r, g) });
}

/* ───────── Teams ───────── */
async function teams(panel) {
  await CK.load();
  panel.append(h('p', { class: 'ck-intro', html: `Each side's default XI against every other on a neutral ground in average conditions (${F.int(D.T.rating_sims || 0)} simulated matches a pair). Team strength is not a sum of player ratings: it comes from playing the XI ball by ball. <b>Click a side</b> for its XI and bowling plan.` }));
  const rows = D.teams.map(t => Object.assign({ t }, t.rating, { name: t.name, short: t.short }));
  const g = S.grid(panel.appendChild(h('div')), { height: 'auto', search: false, chips: false, footer: false, csv: `${CK.FMT}-teams.csv`, sort: 'rank', columns: [
    { key: 'rank', label: '#', fmt: 'int', width: 40, firstDir: 1 }, { key: 'name', label: 'Side', type: 'text', width: 190, frozen: true },
    { key: 'win_pct_fm', label: 'Win %', fmt: 'pct:1', bar: { domain: [0, 1] }, desc: 'Mean win probability against the full members in the table.' },
    ...(isTest ? [{ key: 'draw_pct_fm', label: 'Draw %', fmt: 'pct:1' }] : []),
    { key: 'win_pct', label: 'Win % v all', fmt: 'pct:1', desc: 'Against every side in the table.' },
    { key: 'bat_first_total', label: 'Bat first', fmt: 'num:0', heat: { type: 'seq' }, desc: `Mean ${isTest ? 'first-innings ' : ''}total batting first against full members.` },
    { key: 'bowl_first_total', label: 'Concede', fmt: 'num:0', heat: { type: 'seq', reverse: true }, desc: 'Mean total conceded when the opposition bats first.' },
    { key: 'net_runs', label: 'Net', fmt: 'signed:0', heat: { center: 0 } },
    { key: 'last', label: 'Last match', type: 'text', width: 100, get: r => r.t.last_match },
  ], rows, onRowClick: r => openTeam(r.t) });
  void g;
  const names = D.teams.map(t => t.name), ix = new Map(names.map((n, i) => [n, i])), M = names.map(() => names.map(() => null));
  (D.T.pairs_neutral || []).forEach(p => { const i = ix.get(p.A), j = ix.get(p.B); if (i == null || j == null) return; const dec = p.p_A + p.p_B || 1; M[i][j] = p.p_A / dec; M[j][i] = p.p_B / dec; });
  S.heatmap(panel.appendChild(h('div', { class: 'sh-card' })), { title: `Row side beats column side${isTest ? ' (draws left out)' : ''}, neutral ground`, rows: D.teams.map(t => t.short), cols: D.teams.map(t => t.short), values: M, center: 0.5, domain: [0.1, 0.9], fmt: 'pct:0', valueLabel: 'win probability', maxCell: 46,
    onCell: (i, j) => { if (i !== j) WB.activate('match', { push: true, params: { a: D.teams[i].short, b: D.teams[j].short, g: 'n' } }); } });
}
function openTeam(t) {
  S.drawer.open({ title: t.name, sub: `Rank ${t.rating.rank} · last ${NAME} ${t.last_match}`, body: el => {
    const lu = t.default;
    el.append(h('div', { class: 'ck-sub', text: `Default XI (most recent: ${lu.date}, ${lu.country})` }));
    S.table(el.appendChild(h('div')), [{ key: 'k', label: '#', fmt: 'int' }, { key: 'name', label: 'Player' }, { key: 'bat', label: 'Bat avg', fmt: 'num:1' }, { key: 'sr', label: 'SR', fmt: 'num:0' }, { key: 'bowl', label: 'Bowl avg', fmt: 'num:1' }, { key: 'plan', label: CK.PH_LABEL.join(' / ') }],
      lu.order.map((id, k) => { const p = CK.player(id), pl = lu.plan.find(x => x.id === id); return { k: k + 1, name: CK.pname(id), bat: p && p.bat ? p.bat.all.avg : null, sr: p && p.bat ? p.bat.all.sr : null, bowl: p && p.bowl && pl ? p.bowl.all.avg : null, plan: pl ? CK.PH.map(q => isTest ? F.num(pl[q], 0) + '%' : pl[q]).join(' / ') : '' }; }));
    const other = Object.entries(t.by_region || {}).filter(([, x]) => x.from_match !== lu.from_match);
    other.forEach(([reg, x]) => el.append(S.kv([[`XI in ${{ asia: 'Asian', sena: 'SENA-type', other: 'other' }[reg]} conditions (${x.date}, ${x.country})`, x.order.map(CK.pname).join(', ')]])));
    el.append(h('div', { class: 'ck-links' }, h('a', { href: CK.matchHash({ a: t.short }), text: 'Open in the Match sheet →', onclick: e => { e.preventDefault(); S.drawer.close(); WB.activate('match', { push: true, params: { a: t.short } }); } })));
    el.append(h('div', { class: 'ck-sub', text: `Squad: everyone who has played a ${NAME} for the side in the last 30 months` }));
    S.table(el.appendChild(h('div')), [{ key: 'name', label: 'Player' }, { key: 'apps', label: 'Matches', fmt: 'int' }, { key: 'last_app', label: 'Last' }, { key: 'bat_pos', label: 'Bat pos', fmt: 'num:1' }], t.squad);
  } });
}

/* ───────── Venues ───────── */
async function venues(panel, sheet) {
  await CK.load();
  const M = k => ({ heat: { center: 1 }, fmt: 'num:2', get: r => r[k] });
  sheet.grid(panel, { sort: '-matches_since_2019', csv: `${CK.FMT}-venues.csv`, columns: [
    { key: 'name', label: 'Ground', type: 'text', width: 250, frozen: true }, { key: 'country', label: 'Host', type: 'cat', width: 120 },
    { key: 'matches', label: 'Matches', fmt: 'int' }, { key: 'matches_since_2019', label: 'Since 2019', fmt: 'int' }, { key: 'last_match', label: 'Last', type: 'text', width: 96 },
    Object.assign({ key: 'rpo', label: 'Runs', group: 'Against average', desc: 'Runs per over at this ground (its host country\'s current environment plus its own terms) divided by the average full-member ground. Above 1 = higher scoring.' }, M('all_rpo_mult')),
    Object.assign({ key: 'wpo', label: 'Wickets', group: 'Against average', desc: 'Wickets per over against the average ground.' }, M('all_wpo_mult')),
    Object.assign({ key: 'rpw', label: 'Runs/wkt', group: 'Against average', desc: 'Runs per wicket against the average ground: above 1 favours batting.' }, M('all_rpw_mult')),
    Object.assign({ key: 'spo', label: 'Sixes', group: 'Against average' }, M('all_spo_mult')),
    Object.assign({ key: 'pw', label: 'Pace wkts', group: 'Pace and spin', desc: 'Wickets per over on pace deliveries against the average ground.' }, M('pace_wpo_mult')),
    Object.assign({ key: 'sw', label: 'Spin wkts', group: 'Pace and spin' }, M('spin_wpo_mult')),
    Object.assign({ key: 'pr', label: 'Pace runs', group: 'Pace and spin' }, M('pace_rpo_mult')),
    Object.assign({ key: 'sr', label: 'Spin runs', group: 'Pace and spin' }, M('spin_rpo_mult')),
    Object.assign({ key: 'lr', label: isTest ? 'Runs inns 3-4' : 'Runs chasing', group: isTest ? 'Late in the match' : 'Chasing', desc: isTest ? 'Runs per over in the third and fourth innings against the average ground.' : 'Runs per over in the second innings against the average ground.' }, M('late_rpo_mult')),
    Object.assign({ key: 'lw', label: isTest ? 'Wkts inns 3-4' : 'Wkts chasing', group: isTest ? 'Late in the match' : 'Chasing' }, M('late_wpo_mult')),
    { key: 'abs_rpo', label: 'Runs/over', group: 'Rates', get: r => r.all_rpo, fmt: 'num:2' }, { key: 'abs_rpw', label: 'Runs/wkt', group: 'Rates', get: r => r.all_rpw, fmt: 'num:1' },
  ], rows: D.venues });
}

/* ───────── Diagnostics ───────── */
async function diagnostics(panel) {
  const Dg = await S.load.optional('data/diagnostics.json');
  if (!Dg) { panel.append(h('div', { class: 'sh-note', text: 'Diagnostics have not been published for this build.' })); return; }
  panel.append(h('p', { class: 'ck-intro', html: 'These check fit quality and whether the simulator turns per-ball probabilities into realistic matches. They are <b>not a betting backtest</b>: nothing here compares the model with market prices.' }));
  const card = t => { const c = h('div', { class: 'sh-card' }); c.append(h('div', { class: 'sh-h', text: t })); panel.append(c); return c; };
  const H = Dg.holdout;
  if (H) {
    const c = card('Walk-forward holdout: per-ball log loss');
    c.append(h('div', { class: 'sh-note', text: `Trained before each cut-off, scored on the window after it (${H.folds.map(f => `${f.from} to ${f.to}: ${F.int(f.balls)} balls, ${f.matches} matches`).join('; ')}).` }));
    c.append(S.tiles([{ label: 'Model', value: F.num(H.logloss, 4), sub: 'nats per ball' }, { label: 'Outcome frequencies only', value: F.num(H.logloss_marginal, 4) }, { label: 'Gain', value: F.num(H.logloss_marginal - H.logloss, 4), sub: 'nats per ball' },
      { label: 'Runs per innings', value: `${F.num(H.innings_runs_expected, 1)} / ${F.num(H.innings_runs_actual, 1)}`, sub: 'expected / actual' }, { label: 'Wickets per innings', value: `${F.num(H.innings_wkts_expected, 2)} / ${F.num(H.innings_wkts_actual, 2)}`, sub: 'expected / actual' }]));
    S.table(c.appendChild(h('div')), [{ key: 'cls', label: 'Outcome' }, { key: 'pred', label: 'Predicted', fmt: 'pct:2' }, { key: 'obs', label: 'Observed', fmt: 'pct:2' }, { key: 'slope', label: 'Top fifth: predicted', fmt: 'pct:2', desc: 'Mean prediction in the fifth of deliveries where the model gives this outcome its highest chance.' }, { key: 'slope_obs', label: 'Top fifth: observed', fmt: 'pct:2' }, { key: 'lo', label: 'Bottom fifth: predicted', fmt: 'pct:2' }, { key: 'lo_obs', label: 'Bottom fifth: observed', fmt: 'pct:2' }], H.classes);
  }
  if (Dg.tuning && Dg.tuning.length) {
    const c = card('Configurations tried on the holdout');
    c.append(h('div', { class: 'sh-note', text: 'Difference in log loss from the base configuration, ball by ball, with a standard error clustered by match. Negative is better. A difference inside about two standard errors is not evidence either way.' }));
    S.table(c.appendChild(h('div')), [{ key: 'name', label: 'Variant' }, { key: 'half_life', label: 'Half-life (yrs)', fmt: 'num:0' }, { key: 'll', label: 'Log loss', fmt: 'num:5' }, { key: 'd_vs_base', label: 'v base', fmt: 'signed:5' }, { key: 'd_se', label: 'SE', fmt: 'num:5' }, { key: 'verdict', label: '' }],
      Dg.tuning.map(r => Object.assign({ verdict: r.name === 'base' ? '' : !isNum(r.d_vs_base) ? '' : r.d_vs_base < -2 * r.d_se ? 'better' : r.d_vs_base > 2 * r.d_se ? 'worse' : 'no clear difference' }, r)), { highlight: r => r.adopted });
    if (Dg.adopted) c.append(h('div', { class: 'sh-note', text: 'Adopted: ' + Dg.adopted }));
  }
  const R = Dg.replay;
  if (R) {
    const c = card(`Simulator replay: ${R.matches} real matches since ${R.since}, ${R.sims} simulations each`);
    c.append(h('div', { class: 'sh-note', text: R.note }));
    S.table(c.appendChild(h('div')), [{ key: 'metric', label: 'Quantity' }, { key: 'actual', label: 'Real', fmt: 'num:2' }, { key: 'sim', label: 'Simulated', fmt: 'num:2' }], R.rows);
    if (R.result_calibration) {
      c.append(h('div', { class: 'ck-sub', text: 'Pre-match win probability of the side batting first, in fifths' }));
      S.table(c.appendChild(h('div')), [{ key: 'bin', label: 'Model said' }, { key: 'n', label: 'Matches', fmt: 'int' }, { key: 'pred', label: 'Mean prediction', fmt: 'pct:1' }, { key: 'obs', label: 'Won', fmt: 'pct:1' }], R.result_calibration);
    }
    if (R.pit) S.bar(c.appendChild(h('div')), { title: 'Where real first-innings totals fell in their simulated distribution', subtitle: 'a calibrated simulator gives ten equal bars (10% each)', data: R.pit.map((v, i) => ({ label: `${i * 10}–${i * 10 + 10}%`, value: v })), fmt: 'pct:1', diverging: false });
  }
  if (Dg.shock) {
    const c = card('Conditions the model cannot see');
    c.append(h('div', { class: 'sh-note', text: Dg.shock.note }));
    c.append(S.kv(Dg.shock.rows.map(r => [r[0], r[1]]), { cols: 2 }));
  }
  if (Dg.flow) {
    const c = card('Declarations, follow-on and time');
    c.append(S.kv(Dg.flow.rows.map(r => [r[0], r[1]]), { cols: 2 }));
  }
}

/* ───────── Method ───────── */
function method(panel) { return S.loadMarkdown(panel.appendChild(h('div')), 'data/method.md'); }

/* ───────── workbook ───────── */
const oddsSeg = S.ui.segmented({ options: [{ value: 'american', label: 'American' }, { value: 'decimal', label: 'Decimal' }], value: CK.odds.mode, onChange: v => CK.odds.set(v) });
oddsSeg.classList.add('ck-odds');
WB = CK.wb = S.workbook({
  title: isTest ? 'Test cricket projections' : 'ODI projections',
  subtitle: 'Ball-by-ball ratings and match simulator',
  meta: 'data/meta.json', actions: oddsSeg, defaultSheet: 'schedule',
  sheets: [
    { id: 'schedule', name: 'Schedule', render: schedule },
    { id: 'match', name: 'Match', render: match },
    { id: 'batters', name: 'Batters', fill: true, render: batters },
    { id: 'bowlers', name: 'Bowlers', fill: true, render: bowlers },
    { id: 'teams', name: 'Teams', render: teams },
    { id: 'venues', name: 'Grounds', fill: true, render: venues },
    { id: 'diag', name: 'Diagnostics', render: diagnostics },
    { id: 'method', name: 'Method', render: method },
  ],
});
})();
