/* WNBA workbook: sheet definitions. Depends on ../assets/sheet.js (Sheets) and app.js (WNBA). */
(function () {
'use strict';
const S = Sheets, W = WNBA, D = W.D, h = S.h, esc = S.esc, F = S.fmt, isNum = W.isNum;
const get = path => row => { let o = row; for (const k of path.split('.')) { if (o == null) return null; o = o[k]; } return o == null || (typeof o === 'number' && !isFinite(o)) ? null : o; };
const rate = k => r => r.rates && r.rates[k] && isNum(r.rates[k].p) ? r.rates[k].p : null;
const ZONES = [['rim', 'Rim', '<4 ft'], ['short_mid', 'Short mid', '4–14 ft'], ['long_mid', 'Long mid', '14 ft+ two'], ['corner3', 'Corner 3', 'three, ≤9 ft above hoop line'], ['above_break3', 'Above-break 3', 'other threes']];
const PER100 = 'Points per 100 possessions vs league average (2026 possession-weighted mean = 0).';

/* ───────── column definitions (definitions from schema.md) ───────── */
const RATE_DEFS = {
  usg: ['Usage', 'Plays used (FGA + non-and-one FT trips + TOV) / team possessions while on court.'],
  tov: ['TOV%', 'Turnovers / plays used. Lower is better.'],
  sfd: ['FT trip%', 'Shooting-foul (incl. bonus) FT trips drawn / plays used.'],
  trip3: ['3-shot trip%', 'Three-shot FT trips / all FT trips.'],
  and1: ['And-1%', 'And-ones / made FG.'],
  ftp: ['FT%', 'Free-throw percentage.'],
  ast: ['AST%', 'Assists / teammate made FGs while on court.'],
  astd: ['Ast\'d%', 'Share of her own makes that were assisted.'],
  orb: ['ORB%', 'Offensive rebounds / own-team rebound chances on court.'],
  drb: ['DRB%', 'Defensive rebounds / opponent rebound chances on court.'],
  stl: ['STL%', 'Steals / defensive possessions.'],
  blk: ['BLK%', 'Blocks / opponent FGA while on court.'],
  pf: ['PF%', 'Personal fouls / defensive possessions.'],
};
const rc = (k, fmt, extra) => Object.assign({ key: 'r_' + k, label: RATE_DEFS[k][0], group: 'Rates', get: rate(k), fmt: fmt || 'pct:1', desc: RATE_DEFS[k][1] + ' Projected (age-adjusted, shrunk to a position prior).' }, extra);
const ff = (k, label, desc, rev) => ({ key: 'ff_' + k, label, group: 'Four factors', get: get('four_factor.' + k), fmt: 'signed:2', heat: { center: 0, reverse: !!rev }, desc });
const PCOLS = [
  { key: 'name', label: 'Player', frozen: true, width: 168, desc: 'Click a row for the player card. Arrow keys move rows while the card is open.' },
  { key: 'team', label: 'Team', group: 'Profile', type: 'cat', get: r => r.team_abbr || 'FA', width: 58, desc: 'End-of-2026 team (last 2026 team, else ESPN roster). FA = played 2025, not 2026, on no roster.' },
  { key: 'pos', label: 'Pos', group: 'Profile', type: 'cat', get: r => r.pos_group, width: 50, desc: 'Position group used by the model (G/F/C).' },
  { key: 'age', label: 'Age', group: 'Profile', fmt: 'num:1', get: get('age'), cls: (v, r) => r.age_imputed ? 'dim' : '', desc: 'Age at data cut-off. Grey = imputed from first season.' },
  { key: 'ht', label: 'Height', group: 'Profile', get: get('height_in'), fmt: W.heightText, width: 62, cls: (v, r) => r.height_imputed ? 'dim' : '', desc: 'Height. Grey = imputed (position mean).' },
  { key: 'gp26', label: 'GP 26', group: 'Profile', fmt: 'int', get: get('sample.gp_2026'), desc: 'Games played in 2026.' },
  { key: 'min26', label: 'Min 26', group: 'Profile', fmt: 'int', get: get('sample.min_2026'), desc: 'Total minutes in 2026.' },
  { key: 'possw', label: 'Poss (w)', group: 'Profile', fmt: 'int', get: get('sample.poss_w'), desc: 'Recency-weighted offensive possessions in the RAPM (the effective sample behind her impact rating).' },
  { key: 'o', label: 'O', group: 'Impact', get: get('impact.O'), fmt: 'signed:1', heat: { center: 0, domain: [-4, 4] }, desc: 'Offensive impact. ' + PER100 + ' Prior-informed RAPM. + = better offence.' },
  { key: 'd', label: 'D', group: 'Impact', get: get('impact.D'), fmt: 'signed:1', heat: { center: 0, domain: [-4, 4] }, desc: 'Defensive impact. ' + PER100 + ' + = better defence (fewer points allowed).' },
  { key: 'tot', label: 'Total', group: 'Impact', get: get('impact.total'), fmt: 'signed:1', heat: { center: 0, domain: [-6, 6] }, desc: 'O + D, per 100 possessions vs league average.' },
  { key: 'tsd', label: '± SD', group: 'Impact', get: get('impact.total_sd'), fmt: 'num:1', desc: 'Posterior SD of Total (independence of O and D assumed). Typical regular ≈ ±1.9.' },
  { key: 'pt', label: 'Pctile', group: 'Impact', get: get('pct.total'), fmt: 'int', desc: 'Percentile of Total among qualified players (on a roster, ≥10 projected min).' },
  { key: 'po', label: 'O pct', group: 'Impact', get: get('pct.O'), fmt: 'int', hidden: false, desc: 'Percentile of O among qualified players.' },
  { key: 'pd', label: 'D pct', group: 'Impact', get: get('pct.D'), fmt: 'int', desc: 'Percentile of D among qualified players.' },
  { key: 'or', label: 'O RAPM', group: 'Components', get: get('impact.O_rapm'), fmt: 'signed:1', desc: 'Offence from the same data, ridge toward 0, no box prior.' },
  { key: 'op', label: 'O prior', group: 'Components', get: get('impact.O_prior'), fmt: 'signed:1', desc: 'Offence from the box-score SPM prior alone.' },
  { key: 'dr', label: 'D RAPM', group: 'Components', get: get('impact.D_rapm'), fmt: 'signed:1', desc: 'Defence, ridge toward 0, no prior.' },
  { key: 'dp', label: 'D prior', group: 'Components', get: get('impact.D_prior'), fmt: 'signed:1', desc: 'Defence from the box-score prior alone.' },
  { key: 'ol', label: 'O long-run', group: 'Components', get: get('impact.O_longrun'), fmt: 'signed:1', desc: 'All-seasons slow-decay RAPM used to train the prior (not centred).' },
  { key: 'dl', label: 'D long-run', group: 'Components', get: get('impact.D_longrun'), fmt: 'signed:1', desc: 'All-seasons slow-decay defensive RAPM (not centred).' },
  ff('tov_O', 'TOV O', 'Four-factor RAPM, turnovers per 100 poss on offence. + = her offence commits MORE turnovers (bad).', true),
  ff('tov_D', 'TOV D', 'Turnovers forced. + = opponents commit FEWER turnovers with her on defence, so negative is good.', true),
  ff('orb_O', 'ORB O', 'Own-team ORB% effect per 100 rebound chances. + = more offensive rebounds.'),
  ff('orb_D', 'ORB D', 'Opponent ORB% effect. + = opponents rebound fewer of their misses.'),
  ff('ftr_O', 'FTr O', 'FT trips per 100 possessions drawn. + = more trips.'),
  ff('ftr_D', 'FTr D', 'Opponent FT trips per 100. + = fewer opponent trips.'),
  ff('efg_O', 'eFG O', 'eFG points ×100 per FGA. + = better own shooting.'),
  ff('efg_D', 'eFG D', 'Opponent eFG points ×100 per FGA. + = lower opponent eFG.'),
  ff('xpts_O', 'xPts O', 'Shot quality generated: expected points ×100 per FGA.'),
  ff('xpts_D', 'xPts D', 'Shot quality suppressed: + = opponents take worse shots.'),
  ff('moe_O', 'MOE O', 'Make over expected ×100 per FGA, on offence.'),
  ff('moe_D', 'MOE D', 'Opponent make over expected. + = opponents make fewer than expected.'),
  { key: 'shots', label: 'FGA (w)', group: 'Shot quality', get: get('shot_quality.shots_w'), fmt: 'int', desc: 'Recency-weighted FGA behind the shot-quality numbers.' },
  { key: 'pps', label: 'Pts/shot', group: 'Shot quality', get: get('shot_quality.pts_per_shot'), fmt: 'num:3', desc: 'Points per FGA (recency-weighted).' },
  { key: 'xpps', label: 'xPts/shot', group: 'Shot quality', get: get('shot_quality.xpts_per_shot'), fmt: 'num:3', desc: 'Expected points per FGA from the xFG model (location, type, context).' },
  { key: 'sel', label: 'Selection', group: 'Shot quality', get: get('shot_quality.shot_selection'), fmt: 'signed:3', heat: { center: 0 }, desc: 'xPts per shot − league mean (pts per FGA). + = takes better shots.' },
  { key: 'mk', label: 'Making', group: 'Shot quality', get: get('shot_quality.shot_making'), fmt: 'signed:3', heat: { center: 0 }, desc: 'Points over expected per shot, shrunk with 150 pseudo-shots. + = makes more than location/type predicts.' },
  { key: 'mk3', label: 'Making 3', group: 'Shot quality', get: get('shot_quality.shot_making_3pt'), fmt: 'signed:3', heat: { center: 0 }, desc: 'Points over expected per three-point attempt (shrunk).' },
  { key: 'dxa', label: 'Def xPts', group: 'Shot quality', get: get('shot_quality.def_xpts_allowed'), fmt: 'signed:2', heat: { center: 0, reverse: true }, desc: 'On-court opponent expected pts ×100 per FGA vs average. Negative = suppresses shot quality (good).' },
  { key: 'dma', label: 'Def making', group: 'Shot quality', get: get('shot_quality.def_making_allowed'), fmt: 'signed:2', heat: { center: 0, reverse: true }, desc: 'Opponent make over expected ×100 per FGA. Negative = good contest.' },
  rc('usg', 'pct:1', { heat: { type: 'seq' } }), rc('tov'), rc('sfd'), rc('ftp'), rc('ast'), rc('astd'), rc('orb'), rc('drb'), rc('stl', 'pct:2'), rc('blk', 'pct:2'), rc('pf', 'pct:2'), rc('and1'), rc('trip3'),
  ...ZONES.map(([z, l, d]) => ({ key: 'mx_' + z, label: l, group: 'Shot mix', get: rate('mix_' + z), fmt: 'pct:0', heat: { type: 'seq' }, desc: `Projected share of her FGA from ${l} (${d}). The five zones sum to 100%.` })),
  ...ZONES.map(([z, l, d]) => ({ key: 'fg_' + z, label: l, group: 'FG% by zone', get: rate('fg_' + z), fmt: 'pct:1', desc: `Projected FG% from ${l} (${d}).` })),
  { key: 'mp', label: 'Proj', group: 'Minutes', get: get('minutes.proj'), fmt: 'num:1', bar: { domain: [0, 40] }, desc: 'Default projected minutes per 40-minute game (team sums to 200).' },
  { key: 'msd', label: 'SD', group: 'Minutes', get: get('minutes.sd'), fmt: 'num:1', desc: 'Game-to-game SD of minutes.' },
  { key: 'st', label: 'Starter', group: 'Minutes', get: r => r.minutes && r.minutes.starter ? 'Yes' : '', type: 'cat', width: 64, desc: 'In the default starting five.' },
  { key: 'rm', label: 'Role min', group: 'Minutes', get: get('minutes.role_min'), fmt: 'num:1', desc: 'Recent minutes when playing.' },
  { key: 'av', label: 'Avail', group: 'Minutes', get: get('minutes.avail'), fmt: 'pct:0', desc: 'Share of healthy team games played.' },
  { key: 'v100', label: 'VARP/100', group: 'Value', get: get('value.varp100'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Total impact − replacement level, per 100 possessions.' },
  { key: 'vw', label: 'Wins', group: 'Value', get: get('value.varp_wins'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Season wins above replacement at projected minutes (44 games).' },
  { key: 'nd', label: 'Δ Net', group: 'Value', get: get('value.net_delta'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Change in her team\'s net rating per 100 when she is removed and minutes re-allocated. Negative = team gets worse.' },
  { key: 'wd', label: 'Δ Win%', group: 'Value', get: get('value.winp_delta'), fmt: 'spct:1', heat: { center: 0 }, desc: 'Change in single-game win probability vs a league-average opponent, neutral floor, when she is out (normal approximation).' },
  { key: 'pmin', label: 'Min', group: 'Per game', get: r => r._proj && r._proj.min, fmt: 'num:1', desc: 'Projected minutes per game (simulated, mean over her team\'s 28 matchups). Fills in once matchups.json has loaded.' },
  { key: 'ppts', label: 'Pts', group: 'Per game', get: r => r._proj && r._proj.pts, fmt: 'num:1', desc: 'Projected points per game (simulated, mean over her team\'s matchups).' },
  { key: 'preb', label: 'Reb', group: 'Per game', get: r => r._proj && r._proj.reb, fmt: 'num:1', desc: 'Projected rebounds per game.' },
  { key: 'past', label: 'Ast', group: 'Per game', get: r => r._proj && r._proj.ast, fmt: 'num:1', desc: 'Projected assists per game.' },
  { key: 'p3m', label: '3PM', group: 'Per game', get: r => r._proj && r._proj.fg3m, fmt: 'num:1', desc: 'Projected threes made per game.' },
  { key: 'ampg', label: 'MPG 26', group: 'Per game', get: r => r._act && r._act.min, fmt: 'num:1', desc: '2026 actual minutes per game.' },
  { key: 'appg', label: 'PPG 26', group: 'Per game', get: r => r._act && r._act.pts, fmt: 'num:1', desc: '2026 actual points per game.' },
  { key: 'arpg', label: 'RPG 26', group: 'Per game', get: r => r._act && r._act.reb, fmt: 'num:1', desc: '2026 actual rebounds per game.' },
  { key: 'aapg', label: 'APG 26', group: 'Per game', get: r => r._act && r._act.ast, fmt: 'num:1', desc: '2026 actual assists per game.' },
  { key: 'a3pg', label: '3PM 26', group: 'Per game', get: r => r._act && r._act.fg3m, fmt: 'num:1', desc: '2026 actual threes per game (if exported).' },
  { key: 'dpts', label: 'Δ Pts', group: 'Per game', get: r => r._proj && r._act && isNum(r._proj.pts) && isNum(r._act.pts) ? r._proj.pts - r._act.pts : null, fmt: 'signed:1', heat: { center: 0, domain: [-5, 5] }, desc: 'Projected − 2026 actual points per game. Minutes changes and regression to priors both feed this.' },
  { key: 'dmin', label: 'Δ Min', group: 'Per game', get: r => r._proj && r._act && isNum(r._proj.min) && isNum(r._act.min) ? r._proj.min - r._act.min : null, fmt: 'signed:1', heat: { center: 0, domain: [-8, 8] }, desc: 'Projected − 2026 actual minutes per game.' },
];
const PGROUPS = ['Profile', 'Impact', 'Components', 'Four factors', 'Shot quality', 'Rates', 'Shot mix', 'FG% by zone', 'Minutes', 'Value', 'Per game']
  .map(g => ({ id: g, label: g, hidden: g === 'Components' || g === 'Four factors' || g === 'FG% by zone' }));

/* ───────── player card ───────── */
let playerGrid = null;
W.playerCard = (p, nav) => {
  const t = W.team(p.team);
  const box = p.box_2026 || {}, sm = p.sample || {}, im = p.impact || {}, v = p.value || {}, mn = p.minutes || {}, pct = p.pct || {};
  S.drawer.open({
    title: p.name,
    sub: `${t ? t.name : 'Free agent'} · ${p.pos || ''}${p.pos_group && p.pos_group !== p.pos ? ' (' + p.pos_group + ')' : ''} · ${F.num(p.age, 1)}${p.age_imputed ? '*' : ''} yrs · ${W.heightText(p.height_in)}${p.height_imputed ? '*' : ''} · 2026: ${F.int(sm.gp_2026) || 0} GP${isNum(box.mpg) ? ', ' + F.num(box.mpg, 1) + ' MPG' : ''}${p.age_imputed || p.height_imputed ? ' · * imputed' : ''}`,
    keepScroll: true, nav: nav || (playerGrid && S.drawer.isOpen !== undefined ? { prev: () => playerGrid.step(-1), next: () => playerGrid.step(1) } : null),
    body: async el => {
      el.append(S.tiles([
        { label: 'Impact', value: F.signed(im.total, 1), sub: `±${F.num(im.total_sd, 1)} · ${p._rank ? '#' + p._rank + ' of ' + D.nQualified : 'unranked'}` },
        { label: 'Offence', value: F.signed(im.O, 1), sub: isNum(pct.O) ? pct.O + 'th pct' : '± ' + F.num(im.O_sd, 1) },
        { label: 'Defence', value: F.signed(im.D, 1), sub: isNum(pct.D) ? pct.D + 'th pct' : '± ' + F.num(im.D_sd, 1) },
        { label: 'Season WAR', value: F.signed(v.varp_wins, 1), sub: F.signed(v.varp100, 1) + ' /100 vs repl.' },
        { label: 'Minutes', value: F.num(mn.proj, 1), sub: mn.starter ? 'starter' : 'bench' },
        { label: 'If out', value: isNum(v.winp_delta) ? F.spct(v.winp_delta, 1) : '–', sub: isNum(v.net_delta) ? F.signed(v.net_delta, 1) + ' net / 100' : 'not in rotation' },
      ]));
      const iv = h('div', { class: 'sh-section' }); el.append(iv);
      W.intervals(iv, {
        title: 'Impact, per 100 possessions', rows: [
          { label: 'Offence', v: im.O, sd: im.O_sd, marks: [{ v: im.O_rapm, label: 'RAPM only' }, { v: im.O_prior, label: 'box prior', kind: 'tick' }] },
          { label: 'Defence', v: im.D, sd: im.D_sd, marks: [{ v: im.D_rapm, label: 'RAPM only' }, { v: im.D_prior, label: 'box prior', kind: 'tick' }] },
          { label: 'Total', v: im.total, sd: im.total_sd, marks: [{ v: (im.O_rapm ?? NaN) + (im.D_rapm ?? NaN), label: 'RAPM only' }, { v: (im.O_prior ?? NaN) + (im.D_prior ?? NaN), label: 'box prior', kind: 'tick' }] },
        ], legend: 'Filled dot: the rating used (prior-informed RAPM). Bar ±1 SD, line 90% interval. Ring: RAPM from data alone. Tick: box-score prior alone. + is good at both ends.',
      });
      // shot zones need league reference from sim_params
      const zc = h('div', { class: 'sh-section' }); el.append(zc);
      const SP = await W.loadSimParams().catch(() => null);
      const lg = SP && SP.league || {};
      const rr = k => p.rates && p.rates[k] || {};
      W.zoneChart(zc, { title: 'Shot profile', zones: ZONES.map(([z, l], i) => ({ label: l, mix: rr('mix_' + z).p, lgMix: (lg.mix_by_zone || [])[i], fg: rr('fg_' + z).p, fgSd: rr('fg_' + z).sd, lgFg: (lg.fg_by_zone || [])[i] })) });
      const sq = p.shot_quality || {};
      el.append(S.kv([['Shot selection', F.signed(sq.shot_selection, 3) + ' pts/FGA'], ['Shot making', F.signed(sq.shot_making, 3) + ' pts/FGA'], ['Pts / xPts per shot', `${F.num(sq.pts_per_shot, 3)} / ${F.num(sq.xpts_per_shot, 3)}`], ['Making on threes', F.signed(sq.shot_making_3pt, 3)], ['Opp. xPts allowed', F.signed(sq.def_xpts_allowed, 2) + ' /100 FGA'], ['Opp. making allowed', F.signed(sq.def_making_allowed, 2) + ' /100 FGA']]));
      // projection vs actual
      el.append(h('div', { class: 'sh-h', text: 'Projected per game vs 2026' }));
      const pl = p._proj, ac = p._act, lt = h('div'); el.append(lt);
      const rows = ['min', 'pts', 'reb', 'ast', 'fg3m', 'stl', 'blk', 'tov', 'pra'].map(k => ({ k: W.STAT_SHORT[k], a: ac && ac[k], p: pl && pl[k] })).filter(r => isNum(r.a) || isNum(r.p));
      if (rows.length) S.table(lt, [{ key: 'k', label: 'Stat' }, { key: 'a', label: '2026 actual', fmt: 'num:1' }, { key: 'p', label: 'Projected', fmt: 'num:1' }, { key: 'd', label: 'Δ', fmt: 'signed:1', get: r => isNum(r.a) && isNum(r.p) ? r.p - r.a : null }], rows);
      lt.append(h('div', { class: 'sh-note', text: pl ? (pl.src === 'matchups.json' ? `Projected = simulated mean over her team's ${pl.games || 28} default matchups (vs every opponent, home and away).` : 'Projected line from players.json.') : (D.M ? 'No projected minutes: she is not in a default rotation.' : 'Projected line appears once matchups.json loads (open Matchups or Game).') }));
      // ranks
      if (p.qualified_for_pct) {
        const rk = h('div'); el.append(rk);
        const pk = [['total', 'Total impact'], ['O', 'Offence'], ['D', 'Defence'], ['varp100', 'VARP/100'], ['shot_making', 'Shot making'], ['shot_selection', 'Shot selection'], ['usg', 'Usage'], ['ast', 'AST%'], ['tov', 'TOV% (high = more)'], ['orb', 'ORB%'], ['drb', 'DRB%'], ['stl', 'STL%'], ['blk', 'BLK%'], ['ftp', 'FT%']];
        S.bar(rk, { title: 'Where she ranks', subtitle: `Percentile among ${D.nQualified} qualified players (rostered, ≥10 projected min).`, data: pk.filter(([k]) => isNum(pct[k])).map(([k, l]) => ({ label: l, value: pct[k] })), fmt: 'int', domain: [0, 100], diverging: false, barHeight: 11, rowGap: 6 });
      } else el.append(h('div', { class: 'sh-note', text: 'No percentiles: not qualified (needs a roster spot and ≥10 projected minutes).' }));
      // rates
      el.append(h('div', { class: 'sh-h', text: 'Projected rates' }));
      const rt = h('div'); el.append(rt);
      const rkeys = Object.keys(RATE_DEFS).concat(ZONES.flatMap(([z]) => ['mix_' + z, 'fg_' + z]));
      const zl = Object.fromEntries(ZONES.flatMap(([z, l]) => [['mix_' + z, l + ' share'], ['fg_' + z, l + ' FG%']]));
      S.table(rt, [{ key: 'l', label: 'Rate', render: (x, r) => `<span title="${esc(r.d)}">${esc(x)}</span>` }, { key: 'p', label: 'Proj', fmt: 'pct:1' }, { key: 'sd', label: '± SD', fmt: 'pct:1' }, { key: 'raw', label: 'Raw', fmt: 'pct:1', desc: 'Recency-weighted raw rate' }, { key: 'prior', label: 'Prior', fmt: 'pct:1', desc: 'Position-group prior' }, { key: 'n', label: 'n', fmt: 'int', desc: 'Recency-weighted denominator' }],
        rkeys.filter(k => p.rates && p.rates[k]).map(k => Object.assign({ l: RATE_DEFS[k] ? RATE_DEFS[k][0] : zl[k], d: RATE_DEFS[k] ? RATE_DEFS[k][1] : '' }, p.rates[k])));
      const f4 = p.four_factor || {};
      el.append(h('div', { class: 'sh-h', text: 'Four-factor impact' }), h('div', { class: 'sh-note', text: 'Per 100 possessions (rebounds: per 100 chances; shooting: ×100 per FGA). TOV O + = commits more; TOV D + = forces fewer. Elsewhere + is good.' }),
        S.kv([['TOV O / D', `${F.signed(f4.tov_O, 2)} / ${F.signed(f4.tov_D, 2)}`], ['ORB O / D', `${F.signed(f4.orb_O, 2)} / ${F.signed(f4.orb_D, 2)}`], ['FT rate O / D', `${F.signed(f4.ftr_O, 2)} / ${F.signed(f4.ftr_D, 2)}`], ['eFG O / D', `${F.signed(f4.efg_O, 2)} / ${F.signed(f4.efg_D, 2)}`], ['xPts O / D', `${F.signed(f4.xpts_O, 2)} / ${F.signed(f4.xpts_D, 2)}`], ['Making O / D', `${F.signed(f4.moe_O, 2)} / ${F.signed(f4.moe_D, 2)}`]]));
      el.append(h('div', { class: 'sh-h', text: 'Sample and minutes' }), S.kv([['Weighted poss', F.int(sm.poss_w)], ['Career poss', F.int(sm.career_poss)], ['Career GP', F.int(sm.career_gp)], ['2026 shots', F.int(sm.shots_2026)], ['Minutes SD', F.num(mn.sd, 1)], ['Role minutes', F.num(mn.role_min, 1)], ['Availability', F.pct(mn.avail, 0)], ['Δ ORtg / DRtg if out', isNum(v.off_delta) ? `${F.signed(v.off_delta, 1)} / ${F.signed(v.def_delta, 1)}` : '–']]));
      const links = h('div', { class: 'sh-note wn-links' });
      if (t) {
        links.append(h('a', { href: W.hashFor('teams', { t: t.abbr }), text: 'Team sheet' }), ' · ');
        const opp = D.teams.find(x => x.id !== t.id && Math.abs(x.net) === Math.min(...D.teams.filter(y => y.id !== t.id).map(y => Math.abs(y.net))));
        links.append(h('a', { href: W.hashFor('sim', { h: t.id, a: opp.id, out: p.id }), text: `Simulate ${t.abbr} vs ${opp.abbr} without her` }));
      } else links.append(h('a', { href: W.hashFor('sim', { h: D.teams[D.teams.length - 1].id, a: D.teams[0].id, addh: p.id }), text: 'Try her on a roster in the simulator' }));
      el.append(links);
    },
  });
};

/* ───────── shared controls ───────── */
const teamOpts = () => D.teams.map(t => ({ value: t.id, label: `${t.abbr} · ${t.name}` }));
function matchupPicker(sheet, onPick) {
  const hId = +sheet.get('h') || D.teams[0].id, aId = +sheet.get('a') || D.teams[1].id;
  const home = S.ui.select({ label: 'Home', options: teamOpts(), value: hId, onChange: v => pick(v, away.value) });
  const away = S.ui.select({ label: 'Away', options: teamOpts(), value: aId, onChange: v => pick(home.value, v) });
  const swap = S.ui.button({ label: 'Swap', onClick: () => pick(away.value, home.value) });
  function pick(hh, aa) { if (hh === aa) { aa = D.teams.find(t => t.id !== hh).id; } onPick(hh, aa); }
  return { el: S.ui.row(home, away, swap), hId, aId: aId === hId ? D.teams.find(t => t.id !== hId).id : aId };
}

/* ───────── Overview ───────── */
async function overview(panel) {
  await W.loadCore();
  const meta = await S.load.optional('data/meta.json');
  const intro = W.card(panel, null, null, 'wn-intro');
  intro.append(h('div', { class: 'sh-md', html: S.md(
    '**What this is.** Every WNBA player gets an offensive and a defensive impact rating (points per 100 possessions against league average, from prior-informed RAPM on 2017–26 play-by-play) plus projected skill rates for usage, shot mix and shooting by zone, free throws, passing, rebounding and turnovers. ' +
    'A possession-by-possession simulator plays each game thousands of times from those inputs and default rotations, so sides, totals, quarters and player lines all come from the same simulated games. ' +
    'Nothing here was fitted to or tested against betting prices: fair odds are the model\'s no-vig prices, not a claim of an edge.\n\n' +
    '**How to read it.** O and D are both "+ is good" (D > 0 = fewer points allowed); Total = O + D. Team ratings are built bottom-up: ORtg = league + Σ (minutes/40) × O. ' +
    'Margins are home − away; a spread is quoted for the team named ("LV −3.5"). Hover any column header or chart for definitions. Odds switch between American and decimal in the header. ' +
    'Click a row for a player card, a matchup cell for the game, and use **Simulator** to change rotations.') }));
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  const c1 = W.card(cols, 'Team power', `Bottom-up ratings per 100 possessions from default rotations (league ORtg ${F.num(D.lgORtg, 1)}). Win% = mean P(win) over each team's 28 simulated home/away matchups. Click a team for its sheet.`);
  const tb = h('div'); c1.append(tb);
  const trows = D.teams.slice().sort((a, b) => b.net - a.net).map((t, i) => Object.assign({ rk: i + 1 }, t));
  S.table(tb, [
    { key: 'rk', label: '#', fmt: 'int' }, { key: 'abbr', label: 'Team', render: (v, r) => `<a href="${W.hashFor('teams', { t: v })}" title="${esc(r.name)}">${esc(v)}</a>` },
    { key: 'ortg', label: 'ORtg', fmt: 'num:1', desc: 'Points scored per 100 possessions vs an average defence.' }, { key: 'drtg', label: 'DRtg', fmt: 'num:1', desc: 'Points allowed per 100 possessions vs an average offence (lower is better).' },
    { key: 'net', label: 'Net', fmt: 'signed:1', desc: 'ORtg − DRtg.' }, { key: 'pace_sim', label: 'Pace', fmt: 'num:1', desc: 'Mean simulated possessions per team per game in its matchups.' },
    { key: 'sim_avg_win_prob', label: 'Win%', get: r => r.sim_avg_win_prob ?? r.proj_win_pct_vs_league, fmt: 'pct:1', desc: 'Mean simulated win probability over its 28 matchups (14 home, 14 away).' },
    { key: 'sim_pts_for', label: 'PF', fmt: 'num:1', desc: 'Mean simulated points scored.' }, { key: 'sim_pts_against', label: 'PA', fmt: 'num:1', desc: 'Mean simulated points allowed.' },
  ], trows);
  const c2 = W.card(cols, 'Offence vs defence', 'Each team\'s bottom-up ratings relative to league average, per 100 possessions. Up = better defence, right = better offence.');
  S.scatter(c2.appendChild(h('div')), { points: D.teams.map(t => ({ x: t.ortg - D.lgORtg, y: D.lgORtg - t.drtg, label: t.abbr, id: t.abbr, desc: `${t.name}: net ${F.signed(t.net, 1)}` })), labels: D.teams.map(t => t.abbr), xLabel: 'offence (ORtg − lg)', yLabel: 'defence (lg − DRtg)', xFmt: 'signed:0', yFmt: 'signed:0', refX: 0, refY: 0, height: 240, onClick: pt => W.go('teams', { t: pt.id }) });
  S.bar(c2.appendChild(h('div', { style: { marginTop: '12px' } })), { title: 'Net rating', data: trows.map(t => ({ label: t.abbr, value: t.net, id: t.abbr, desc: t.name })), fmt: 'signed:1', barHeight: 11, rowGap: 5, onClick: d => W.go('teams', { t: d.id }) });
  const cols2 = h('div', { class: 'sh-cols' }); panel.append(cols2);
  const c3 = W.card(cols2, 'Top players by impact', 'Total impact (O + D) per 100 possessions, rostered players. Click a bar for her card.');
  const top = D.players.filter(p => p.team != null && isNum(p.impact.total) && p.minutes.proj >= 10).sort((a, b) => b.impact.total - a.impact.total).slice(0, 20);
  S.bar(c3.appendChild(h('div')), { data: top.map(p => ({ label: `${p.name} (${p.team_abbr})`, value: p.impact.total, id: p.id, desc: `O ${F.signed(p.impact.O, 1)}, D ${F.signed(p.impact.D, 1)}, ± ${F.num(p.impact.total_sd, 1)}` })), fmt: 'signed:1', diverging: false, barHeight: 11, rowGap: 5, onClick: d => W.playerCard(W.player(d.id), { prev: () => {}, next: () => {} }) });
  const c4 = W.card(cols2, 'Most valuable (season)', 'Wins above replacement at projected minutes over a 44-game season, and the single-game win-probability hit if she sits.');
  const vt = h('div'); c4.append(vt);
  const vrows = D.players.filter(p => isNum(p.value.varp_wins) && p.team != null).sort((a, b) => b.value.varp_wins - a.value.varp_wins).slice(0, 12);
  S.table(vt, [{ key: 'name', label: 'Player' }, { key: 'team_abbr', label: 'Team' }, { key: 'm', label: 'Min', get: r => r.minutes.proj, fmt: 'num:1' }, { key: 'v', label: 'VARP/100', get: r => r.value.varp100, fmt: 'signed:1' }, { key: 'w', label: 'Wins', get: r => r.value.varp_wins, fmt: 'signed:1' }, { key: 'wp', label: 'Δ Win% out', get: r => r.value.winp_delta, fmt: 'spct:1' }], vrows);
  vt.classList.add('wn-click'); vt.querySelectorAll('tbody tr').forEach((tr, i) => tr.addEventListener('click', () => W.playerCard(vrows[i], { prev: () => {}, next: () => {} })));
  if (meta) {
    const c5 = W.card(cols2, 'Build', 'What went into this export.');
    const lr = meta.recon_minutes_within_1;
    c5.append(S.kv([['Data cut-off', meta.data_cutoff], ['Last game', meta.last_game_date], ['Built', meta.build_date], ['Seasons', meta.seasons ? meta.seasons[0] + '–' + meta.seasons[meta.seasons.length - 1] : '–'], ['Games', F.int(meta.n_games)], ['Possessions', F.int(meta.n_possessions)], ['Field-goal attempts', F.int(meta.n_shots)], ['Players / teams', `${F.int(meta.n_players_exported)} / ${F.int(meta.n_teams)}`], ['Sims per matchup', F.int(meta.matchup_sims)], ['Lineups recovered', isNum(meta.recon_poss_lineup_ok) ? F.pct(meta.recon_poss_lineup_ok, 1) + ' of possessions' : '–'], ['Minutes within 1', isNum(lr) ? F.pct(lr, 1) + ' of player-games' : '–'], ['Replacement level', isNum(meta.value && meta.value.replacement_per100) ? F.signed(meta.value.replacement_per100, 2) + ' / 100' : '–']]));
  }
}

/* ───────── Players ───────── */
async function players(panel, sheet) {
  await W.loadCore();
  const rows = D.players;
  const status = h('span', { class: 'sh-note wn-status' });
  const cols = PCOLS.map(c => c.key === 'a3pg' && !rows.some(r => r._act && isNum(r._act.fg3m)) ? Object.assign({}, c, { hidden: true }) : c);
  playerGrid = sheet.grid(panel, { columns: cols, groups: PGROUPS, rows, sort: '-tot', label: 'Players', csv: 'wnba-players.csv', searchPlaceholder: 'Search player or team', tools: status,
    onRowClick: r => W.playerCard(r, { prev: () => playerGrid.step(-1), next: () => playerGrid.step(1) }), rowClass: r => r.team == null ? 'wn-fa' : '' });
  if (!rows.some(r => r._proj)) {
    status.textContent = 'Loading projected lines…';
    W.loadMatchups().then(() => { playerGrid.setRows(rows); status.textContent = ''; }).catch(e => { status.textContent = 'Projected lines unavailable: ' + e.message; });
  }
}

/* ───────── Teams ───────── */
async function teams(panel, sheet) {
  await W.loadCore();
  const body = h('div', { class: 'sh-section wn-gap' });
  const draw = () => {
    const t = W.team(sheet.get('t')) || D.teams[0], mode = sheet.get('mode') || 'net';
    body.innerHTML = '';
    const sel = S.ui.select({ label: 'Team', options: D.teams.map(x => ({ value: x.abbr, label: `${x.abbr} · ${x.name}` })), value: t.abbr, onChange: v => { sheet.set({ t: v }); draw(); } });
    const md = S.ui.segmented({ label: 'Decompose', options: [{ value: 'net', label: 'Net' }, { value: 'off', label: 'Offence' }, { value: 'def', label: 'Defence' }], value: mode, onChange: v => { sheet.set({ mode: v === 'net' ? null : v }); draw(); } });
    const i = D.teams.indexOf(t);
    const prev = S.ui.button({ label: '← ' + D.teams[(i + D.teams.length - 1) % D.teams.length].abbr, onClick: () => { sheet.set({ t: D.teams[(i + D.teams.length - 1) % D.teams.length].abbr }); draw(); } });
    const next = S.ui.button({ label: D.teams[(i + 1) % D.teams.length].abbr + ' →', onClick: () => { sheet.set({ t: D.teams[(i + 1) % D.teams.length].abbr }); draw(); } });
    body.append(S.ui.row(sel, md, prev, next));
    const rk = D.teams.slice().sort((a, b) => b.net - a.net).indexOf(t) + 1;
    body.append(S.tiles([
      { label: 'Net', value: F.signed(t.net, 1), sub: `rank ${rk} of ${D.teams.length}` },
      { label: 'ORtg', value: F.num(t.ortg, 1), sub: F.signed(t.ortg - D.lgORtg, 1) + ' vs lg' },
      { label: 'DRtg', value: F.num(t.drtg, 1), sub: F.signed(D.lgORtg - t.drtg, 1) + ' better than lg' },
      { label: 'Pace', value: F.num(t.pace_sim, 1), sub: 'sim poss / team' },
      { label: 'Mean win%', value: F.pct(t.sim_avg_win_prob ?? t.proj_win_pct_vs_league, 1), sub: '28 matchups' },
      { label: 'Pts for / against', value: `${F.num(t.sim_pts_for, 1)}`, sub: `against ${F.num(t.sim_pts_against, 1)}` },
    ]));
    const cols = h('div', { class: 'sh-cols' }); body.append(cols);
    const rot = (t.rotation || []).filter(r => r.min > 0).map(r => { const p = W.player(r.id) || { impact: {} }; const o = r.min / 40 * (p.impact.O || 0), d = r.min / 40 * (p.impact.D || 0); return Object.assign({}, r, { p, o, d, n: o + d }); });
    const key = mode === 'off' ? 'o' : mode === 'def' ? 'd' : 'n';
    const items = rot.slice().sort((a, b) => b[key] - a[key]).map(r => ({ label: r.name, value: r[key], id: r.id, desc: `${F.num(r.min, 1)} min × ${mode === 'off' ? 'O ' + F.signed(r.p.impact.O, 2) : mode === 'def' ? 'D ' + F.signed(r.p.impact.D, 2) : 'total ' + F.signed(r.p.impact.total, 2)} / 40` }));
    const c1 = W.card(cols, mode === 'off' ? 'How the ORtg adds up' : mode === 'def' ? 'How the defence adds up' : 'How the net rating adds up',
      `Each player's contribution = (projected minutes / 40) × her ${mode === 'off' ? 'O' : mode === 'def' ? 'D' : 'O + D'} rating, per 100 possessions. Contributions sum exactly to the team's ${mode === 'off' ? 'ORtg − league (' + F.signed(t.ortg - D.lgORtg, 2) + ')' : mode === 'def' ? 'league − DRtg (' + F.signed(D.lgORtg - t.drtg, 2) + ')' : 'net rating (' + F.signed(t.net, 2) + ')'}.`);
    W.waterfall(c1.appendChild(h('div')), { items, start: 0, startLabel: 'League average', endLabel: t.abbr + (mode === 'off' ? ' offence' : mode === 'def' ? ' defence' : ' net'), fmt: 'signed:2', tickFmt: 'signed:0', onClick: it => W.playerCard(W.player(it.id), { prev: () => {}, next: () => {} }) });
    const c2 = W.card(cols, 'Rotation', 'Default minutes (sum to 200), the ratings behind them, and the cost of removing each player (minutes re-allocated). Click a row for her card.');
    const rt = h('div'); c2.append(rt);
    const rrows = (t.rotation || []).map(r => ({ r, p: W.player(r.id) || { impact: {}, value: {} } }));
    S.table(rt, [
      { key: 'n', label: 'Player', get: x => x.r.name + (x.r.starter ? '' : ''), render: (v, x) => esc(v) + (x.r.starter ? ' <span class="muted">S</span>' : '') }, { key: 'pos', label: 'Pos', get: x => x.r.pos_group },
      { key: 'min', label: 'Min', get: x => x.r.min, fmt: 'num:1' }, { key: 'sd', label: '±', get: x => x.r.min_sd, fmt: 'num:1', desc: 'game-to-game minutes SD' },
      { key: 'o', label: 'O', get: x => x.p.impact.O, fmt: 'signed:1' }, { key: 'd', label: 'D', get: x => x.p.impact.D, fmt: 'signed:1' },
      { key: 'c', label: 'Contrib', get: x => x.r.min / 40 * ((x.p.impact.O || 0) + (x.p.impact.D || 0)), fmt: 'signed:2', desc: 'min/40 × (O + D): her share of the team net rating' },
      { key: 'nd', label: 'Δ Net out', get: x => x.p.value.net_delta, fmt: 'signed:1', desc: 'team net change if she is out' },
      { key: 'wd', label: 'Δ Win% out', get: x => x.p.value.winp_delta, fmt: 'spct:1' },
    ], rrows);
    rt.classList.add('wn-click'); rt.querySelectorAll('tbody tr').forEach((tr, k) => tr.addEventListener('click', () => { if (rrows[k].p.id) W.playerCard(rrows[k].p, { prev: () => {}, next: () => {} }); }));
    const cols2 = h('div', { class: 'sh-cols' }); body.append(cols2);
    const c3 = W.card(cols2, 'Most-used 2026 lineups', 'Raw on-court net points per 100 possessions (not adjusted for opponent or luck). Context only.');
    const lt = h('div'); c3.append(lt);
    S.table(lt, [{ key: 'names', label: 'Lineup', render: v => esc((v || []).map(n => n.split(' ').slice(-1)[0]).join(', ')) }, { key: 'poss', label: 'Poss', fmt: 'int' }, { key: 'net100', label: 'Net/100', fmt: 'signed:1' }], t.top_lineups_2026 || []);
    const c4 = W.card(cols2, 'Pace and context', 'Team (coach/system) residuals in seconds per first play, shrunk. + = slower.');
    c4.append(S.kv([['Sim possessions / team', F.num(t.pace_sim, 1)], ['Offence pace residual', F.signed(t.pace_team_residual && t.pace_team_residual.off, 2) + ' s'], ['Defence pace residual', F.signed(t.pace_team_residual && t.pace_team_residual.deff, 2) + ' s'], ['Roster size', String((t.roster || []).length)]]));
    c4.append(h('div', { class: 'sh-note wn-links' }, h('a', { href: W.hashFor('game', { h: t.id, a: D.teams.find(x => x.id !== t.id).id }), text: 'Open a game' }), ' · ', h('a', { href: W.hashFor('sim', { h: t.id, a: D.teams.find(x => x.id !== t.id).id }), text: 'Simulator' })));
  };
  panel.append(body); draw();
  sheet.onState(draw);
}

/* ───────── Matchups ───────── */
const METRICS = {
  win: { label: 'Home win %', get: g => g.home_win, fmt: 'pct:0', center: 0.5, domain: [0.1, 0.9], vl: 'P(home team wins)' },
  margin: { label: 'Home margin', get: g => mean(g.margin), fmt: 'signed:1', center: 0, vl: 'mean margin, home − away (pts)' },
  total: { label: 'Total', get: g => mean(g.total), fmt: 'num:0', vl: 'mean total points' },
  ot: { label: 'P(OT)', get: g => g.p_ot, fmt: 'pct:1', vl: 'P(overtime)' },
};
const mean = x => Array.isArray(x) ? x[0] : x && x.mean;
async function matchups(panel, sheet) {
  await W.loadCore(); await W.loadMatchups();
  const M = D.M, T = D.teams;
  const top = h('div', { class: 'sh-card' }); panel.append(top);
  const hm = h('div');
  const metric = S.ui.segmented({ label: 'Show', options: Object.entries(METRICS).map(([k, v]) => ({ value: k, label: v.label })), value: sheet.get('m') || 'win', onChange: v => { sheet.set({ m: v === 'win' ? null : v }); draw(); } });
  top.append(h('div', { class: 'sh-h', text: 'Every matchup' }), h('div', { class: 'sh-note', text: `Rows = home team, columns = away team. ${F.int(M.n_sims)} sims per game, default rotations, two days' rest, no travel. Click a cell for the game.` }), S.ui.row(metric), hm);
  const draw = () => {
    const m = METRICS[sheet.get('m') || 'win'] || METRICS.win;
    const vals = T.map(a => T.map(b => { const g = M.pairs[a.id + '_' + b.id]; return g ? m.get(g.game) : null; }));
    S.heatmap(hm, { rows: T.map(t => t.abbr), cols: T.map(t => t.abbr), values: vals, center: m.center, domain: m.domain, fmt: m.fmt, valueLabel: m.vl, scaleLabel: m.vl, vs: 'hosting', maxCell: 64, cellH: 26, onCell: (i, j) => { if (i !== j) W.go('game', { h: T[i].id, a: T[j].id }); } });
  };
  draw();
  sheet.onState(draw);
  const rows = Object.values(M.pairs).map(mu => {
    const g = mu.game, H = W.team(mu.home), A = W.team(mu.away);
    return { h: H.abbr, a: A.abbr, hId: H.id, aId: A.id, hw: g.home_win, m: mean(g.margin), msd: g.margin[1] ?? g.margin.sd, t: mean(g.total), tsd: g.total[1] ?? g.total.sd, hp: mean(g.home_pts), ap: mean(g.away_pts), ot: g.p_ot, poss: g.poss };
  });
  const gc = h('div', { class: 'sh-section' }); panel.append(gc);
  gc.append(h('div', { class: 'sh-h', text: 'All games' }), h('div', { class: 'sh-note', text: 'Sortable list of the same 210 games. Fair prices follow the odds toggle. Click a row for the game sheet.' }));
  const grid = sheet.grid(gc, { stateKey: 'g', height: 460, rows, sort: '-hw', csv: 'wnba-matchups.csv', searchPlaceholder: 'Search team', footer: false, onRowClick: r => W.go('game', { h: r.hId, a: r.aId }),
    columns: [
      { key: 'h', label: 'Home', type: 'cat', frozen: true, width: 64 }, { key: 'a', label: 'Away', type: 'cat', frozen: true, width: 64 },
      { key: 'hw', label: 'Home win', fmt: 'pct:1', heat: { center: 0.5, domain: [0.1, 0.9] }, desc: 'P(home wins), incl. OT.' },
      { key: 'hml', label: 'Home fair', get: r => r.hw, fmt: p => W.fp(p), desc: 'Fair (no-vig) moneyline for the home team.' },
      { key: 'aml', label: 'Away fair', get: r => 1 - r.hw, fmt: p => W.fp(p), desc: 'Fair moneyline for the away team.' },
      { key: 'm', label: 'Margin', fmt: 'signed:1', heat: { center: 0 }, desc: 'Mean final margin, home − away (pts). Fair home spread ≈ minus this.' },
      { key: 'msd', label: 'Mgn SD', fmt: 'num:1' }, { key: 't', label: 'Total', fmt: 'num:1', heat: { type: 'seq' }, desc: 'Mean total points.' }, { key: 'tsd', label: 'Tot SD', fmt: 'num:1' },
      { key: 'hp', label: 'Home pts', fmt: 'num:1' }, { key: 'ap', label: 'Away pts', fmt: 'num:1' }, { key: 'ot', label: 'P(OT)', fmt: 'pct:1' }, { key: 'poss', label: 'Poss', fmt: 'num:1', desc: 'Mean possessions per team.' },
    ] });
  W.odds.bind(gc, () => grid.refresh());
}

/* ───────── Game ───────── */
async function game(panel, sheet) {
  await W.loadCore(); await W.loadMatchups();
  const ctl = h('div'), body = h('div', { class: 'sh-section wn-gap' }); panel.append(ctl, body);
  const draw = () => {
    const pk = matchupPicker(sheet, (hh, aa) => { sheet.set({ h: hh, a: aa, sl: null, tl: null, hl: null, al: null }); draw(); });
    ctl.innerHTML = ''; ctl.append(h('div', { class: 'wn-ctlbar' }, pk.el, h('span', { class: 'sh-note wn-links' }, h('a', { href: W.hashFor('props', { h: pk.hId, a: pk.aId }), text: 'Player props' }), ' · ', h('a', { href: W.hashFor('sim', { h: pk.hId, a: pk.aId }), text: 'Change it in the simulator' }))));
    const G = W.game(pk.hId, pk.aId);
    if (!G) { body.innerHTML = ''; body.append(S.errorEl(new Error('No precomputed matchup for this pair.'))); return; }
    const L = k => { const v = parseFloat(sheet.get(k)); return isFinite(v) ? v : null; };
    W.renderGame(body, G, { lines: { sl: L('sl'), tl: L('tl'), hl: L('hl'), al: L('al') }, onLines: o => sheet.set(o) });
  };
  draw();
  sheet.onState(draw);
}

/* ───────── Player props ───────── */
async function props(panel, sheet) {
  await W.loadCore(); await W.loadMatchups();
  const ctl = h('div'), pricer = W.card(null, null, null, 'wn-pricer'), gwrap = h('div', { class: 'sh-section' });
  panel.append(ctl, pricer, gwrap);
  let grid = null, G = null, rows = [];
  const statCols = [];
  W.STATS.forEach(k => {
    const g = W.STAT_SHORT[k], s = r => r.p.stats[k];
    statCols.push({ key: k + '_m', label: 'Mean', group: g, get: r => s(r) && s(r).mean, fmt: 'num:1', heat: k === 'min' ? null : { type: 'seq' }, desc: `${W.STAT_LABEL[k]}: simulated mean.` });
    statCols.push({ key: k + '_md', label: 'Med', group: g, get: r => s(r) && s(r).median, fmt: 'num:1', desc: `${W.STAT_LABEL[k]}: simulated median.` });
    statCols.push({ key: k + '_sd', label: 'SD', group: g, get: r => s(r) && s(r).sd, fmt: 'num:1', desc: `${W.STAT_LABEL[k]}: simulated SD.` });
    statCols.push({ key: k + '_q10', label: '10%', group: g, get: r => s(r) && W.qAt(s(r), 0.1), fmt: 'num:0', desc: `${W.STAT_LABEL[k]}: 10th percentile.` });
    statCols.push({ key: k + '_q90', label: '90%', group: g, get: r => s(r) && W.qAt(s(r), 0.9), fmt: 'num:0', desc: `${W.STAT_LABEL[k]}: 90th percentile.` });
    statCols.push({ key: k + '_ln', label: '50% line', group: g, get: r => s(r) && W.defaultPropLine(s(r)), fmt: 'num:1', desc: `${W.STAT_LABEL[k]}: tabulated half-point line closest to a 50/50 split.` });
  });
  const columns = [
    { key: 'name', label: 'Player', frozen: true, width: 160, get: r => r.p.name },
    { key: 'team', label: 'Team', type: 'cat', width: 58, get: r => r.team },
    ...statCols,
    { key: 'fga', label: 'FGA', group: 'Other', get: r => r.p.fga, fmt: 'num:1', desc: 'Mean field-goal attempts.' },
    { key: 'fg3a', label: '3PA', group: 'Other', get: r => r.p.fg3a, fmt: 'num:1', desc: 'Mean three-point attempts.' },
    { key: 'fta', label: 'FTA', group: 'Other', get: r => r.p.fta, fmt: 'num:1', desc: 'Mean free-throw attempts.' },
    { key: 'dd', label: 'P(DD)', group: 'Other', get: r => r.p.pDD, fmt: 'pct:1', desc: 'P(double-double).' },
    { key: 'ddf', label: 'DD fair', group: 'Other', get: r => r.p.pDD, fmt: p => W.fp(p), desc: 'Fair price for a double-double.' },
  ];
  const groups = W.STATS.map(k => ({ id: W.STAT_SHORT[k], label: W.STAT_SHORT[k], hidden: !['min', 'pts', 'reb', 'ast', 'fg3m', 'pra'].includes(k) })).concat([{ id: 'Other', label: 'Other' }]);
  const drawPricer = () => {
    pricer.innerHTML = '';
    const pid = +sheet.get('p'), key = W.STATS.includes(sheet.get('st')) ? sheet.get('st') : 'pts';
    let row = rows.find(r => r.p.id === pid) || rows.slice().sort((a, b) => (b.p.stats.pts ? b.p.stats.pts.mean : 0) - (a.p.stats.pts ? a.p.stats.pts.mean : 0))[0];
    if (!row) return;
    const psel = S.ui.select({ label: 'Player', options: rows.map(r => ({ value: r.p.id, label: `${r.p.name} (${r.team})` })), value: row.p.id, onChange: v => { sheet.set({ p: v, ln: null }); drawPricer(); } });
    const ssel = S.ui.segmented({ label: 'Stat', options: W.STATS.map(k => ({ value: k, label: W.STAT_SHORT[k] })), value: key, onChange: v => { sheet.set({ st: v === 'pts' ? null : v, ln: null }); drawPricer(); } });
    pricer.append(h('div', { class: 'sh-h', text: 'Prop pricer' }), h('div', { class: 'sh-note', text: `${row.p.name}, ${W.STAT_LABEL[key].toLowerCase()} in ${row.side === 'home' ? 'this home game vs ' + W.abbr(G.aId) : 'this road game at ' + W.abbr(G.hId)}. Type a line for P(over/under) and fair prices.` }), S.ui.row(psel, ssel));
    const sp = h('div', { class: 'sh-section' }); pricer.append(sp);
    const ln = parseFloat(sheet.get('ln'));
    W.statPanel(sp, row.p.stats[key], { key, line: isFinite(ln) ? ln : null, onLine: L => sheet.set({ ln: L }) });
  };
  const draw = () => {
    const pk = matchupPicker(sheet, (hh, aa) => { sheet.set({ h: hh, a: aa, p: null, ln: null }); draw(); });
    ctl.innerHTML = ''; ctl.append(h('div', { class: 'wn-ctlbar' }, pk.el, h('span', { class: 'sh-note wn-links' }, h('a', { href: W.hashFor('game', { h: pk.hId, a: pk.aId }), text: 'Game sheet' }))));
    G = W.game(pk.hId, pk.aId); if (!G) return;
    rows = [...G.home.map((p, i) => ({ p, i, side: 'home', team: W.abbr(G.hId) })), ...G.away.map((p, i) => ({ p, i, side: 'away', team: W.abbr(G.aId) }))].filter(r => r.p.stats.min && r.p.stats.min.mean >= 0.05);
    drawPricer();
    if (!grid) {
      gwrap.append(h('div', { class: 'sh-h', text: 'Every player in this game' }), h('div', { class: 'sh-note', text: 'Distribution summaries from the simulation. Stat groups toggle with the chips. Click a row to load her in the pricer (clicking a stat column also picks that stat).' }));
      grid = sheet.grid(gwrap, { stateKey: 'g', height: 520, columns, groups, rows, sort: '-pts_m', csv: 'wnba-player-props.csv', footer: false, searchPlaceholder: 'Search player',
        onRowClick: (r) => { const sel = grid.selected(); const col = sel && sel.column ? sel.column.split('_')[0] : null; sheet.set({ p: r.p.id, ln: null, st: col && W.STATS.includes(col) ? (col === 'pts' ? null : col) : sheet.get('st') }); drawPricer(); pricer.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } });
      W.odds.bind(gwrap, () => grid.refresh());
    } else grid.setRows(rows);
  };
  draw();
  sheet.onState(() => draw());
}

/* ───────── Simulator ───────── */
const SIM_WORKERS = 4, SIM_SEED = 7;
async function simulator(panel, sheet) {
  await W.loadCore();
  const SP = await W.loadSimParams();
  const spById = new Map(SP.players.map(p => [p.id, p]));
  const left = h('div', { class: 'sh-card wn-simctl' }), right = h('div', { class: 'wn-simout' });
  panel.append(h('div', { class: 'wn-simgrid' }, left, right));
  const baseCache = new Map();
  let job = null, last = null;
  const list = k => (sheet.get(k) || '').split(',').filter(Boolean).map(Number).filter(isFinite);
  const minMap = () => Object.fromEntries((sheet.get('min') || '').split(',').filter(Boolean).map(s => s.split(':').map(Number)).filter(a => a.length === 2 && isFinite(a[0]) && isFinite(a[1])));
  const writeMin = m => sheet.set({ min: Object.entries(m).map(([k, v]) => k + ':' + v).join(',') || null });
  const st = () => {
    const hId = +sheet.get('h') || D.teams[0].id; let aId = +sheet.get('a') || D.teams[1].id; if (aId === hId) aId = D.teams.find(t => t.id !== hId).id;
    return { hId, aId, neu: sheet.get('neu') === '1', hr: +(sheet.get('hr') || 2), ar: +(sheet.get('ar') || 2), hb: sheet.get('hb') === '1', ab: sheet.get('ab') === '1', ht: +(sheet.get('ht') || 0), at: +(sheet.get('at') || 0), n: +(sheet.get('n') || 20000), out: new Set(list('out')), min: minMap(), addh: list('addh'), adda: list('adda') };
  };
  const roster = (s, side) => {
    const tid = side === 'h' ? s.hId : s.aId, mine = side === 'h' ? s.addh : s.adda, theirs = side === 'h' ? s.adda : s.addh;
    const base = SP.players.filter(p => p.team === tid).map(p => p.id).filter(id => !theirs.includes(id));
    return base.concat(mine.filter(id => !base.includes(id) && spById.has(id)));
  };
  const sideChanged = (s, side) => { const ids = roster(s, side), tid = side === 'h' ? s.hId : s.aId; return ids.some(id => s.out.has(id) || s.min[id] != null || spById.get(id).team !== tid) || ids.length !== SP.players.filter(p => p.team === tid).length; };
  const ctxChanged = s => s.neu || s.hr !== 2 || s.ar !== 2 || s.hb || s.ab || s.ht || s.at;
  const spec = (s, side) => {
    const tid = side === 'h' ? s.hId : s.aId;
    if (!sideChanged(s, side)) return { team: tid };
    return { team: tid, players: roster(s, side).map(id => { const x = { id }; if (s.out.has(id)) x.out = true; if (s.min[id] != null) x.min = s.min[id]; else if (spById.get(id).team !== tid) x.min = Math.max(spById.get(id).min || 0, 1) > 1 ? spById.get(id).min : 15; return x; }) };
  };
  const opts = s => ({ neutral: s.neu, home_b2b: s.hb, away_b2b: s.ab, home_rest_days: s.hr, away_rest_days: s.ar, home_travel_miles: s.ht, away_travel_miles: s.at });
  const ctxText = s => [s.neu ? 'neutral floor' : '', s.hr !== 2 || s.ar !== 2 ? `rest ${s.hr}/${s.ar} days` : '', s.hb ? W.abbr(s.hId) + ' on a back-to-back' : '', s.ab ? W.abbr(s.aId) + ' on a back-to-back' : '', s.ht || s.at ? `travel ${s.ht}/${s.at} mi` : ''].filter(Boolean).join(', ');

  const prog = S.ui.progress(), status = h('span', { class: 'sh-note num' });
  const res = h('div', { class: 'sh-section' });
  right.append(h('div', { class: 'wn-progrow' }, prog, status), res);

  function drawControls() {
    const s = st();
    left.innerHTML = '';
    const set = (o, rerender = true) => { sheet.set(o); markStale(); if (rerender) drawControls(); };
    const home = S.ui.select({ label: 'Home', options: teamOpts(), value: s.hId, onChange: v => set({ h: v, a: v === s.aId ? s.hId : s.aId, out: null, min: null, addh: null, adda: null }) });
    const away = S.ui.select({ label: 'Away', options: teamOpts(), value: s.aId, onChange: v => set({ a: v, h: v === s.hId ? s.aId : s.hId, out: null, min: null, addh: null, adda: null }) });
    const venue = S.ui.segmented({ label: 'Venue', options: [{ value: 0, label: 'Home court' }, { value: 1, label: 'Neutral' }], value: s.neu ? 1 : 0, onChange: v => set({ neu: v ? 1 : null }, false) });
    const restOpts = [1, 2, 3, 4].map(v => ({ value: v, label: v === 1 ? '1 day' : v + ' days' }));
    const hr = S.ui.select({ label: W.abbr(s.hId) + ' rest', options: restOpts, value: s.hr, onChange: v => set({ hr: v === 2 ? null : v }, false) });
    const ar = S.ui.select({ label: W.abbr(s.aId) + ' rest', options: restOpts, value: s.ar, onChange: v => set({ ar: v === 2 ? null : v }, false) });
    const hb = S.ui.toggle({ label: W.abbr(s.hId) + ' back-to-back', value: s.hb, onChange: v => set({ hb: v ? 1 : null }, false) });
    const ab = S.ui.toggle({ label: W.abbr(s.aId) + ' back-to-back', value: s.ab, onChange: v => set({ ab: v ? 1 : null }, false) });
    const ht = S.ui.stepper({ label: W.abbr(s.hId) + ' travel mi', min: 0, max: 3000, step: 250, value: s.ht, onChange: v => set({ ht: v || null }, false) });
    const at = S.ui.stepper({ label: W.abbr(s.aId) + ' travel mi', min: 0, max: 3000, step: 250, value: s.at, onChange: v => set({ at: v || null }, false) });
    const sims = S.ui.select({ label: 'Simulations', options: [5000, 10000, 20000, 50000, 100000].map(v => ({ value: v, label: F.int(v) })), value: s.n, onChange: v => set({ n: v === 20000 ? null : v }, false) });
    const run = S.ui.button({ label: 'Run simulation', primary: true, onClick: () => go(true) });
    const reset = S.ui.button({ label: 'Reset', onClick: () => { sheet.set({ neu: null, hr: null, ar: null, hb: null, ab: null, ht: null, at: null, out: null, min: null, addh: null, adda: null }); markStale(); drawControls(); } });
    run.classList.add('wn-run');
    const c = SP.context || {};
    left.append(S.ui.row(home, away), S.ui.row(venue, sims), S.ui.row(hr, ar), S.ui.row(hb, ab), S.ui.row(ht, at),
      h('div', { class: 'sh-note', text: `Context effects (fitted, shrunk): home court ${F.signed(c.hca_pts, 2)} pts, back-to-back ${F.signed(c.b2b_pts, 2)}, each extra rest day ${F.signed(c.rest_day_pts, 2)}, travel ${F.signed(c.travel_pts_per_1000mi, 2)} per 1,000 mi.` }),
      S.ui.row(run, reset));
    ['h', 'a'].forEach(side => left.append(rosterEditor(s, side)));
    left.append(h('div', { class: 'sh-note', text: `Seed ${SIM_SEED}, ${SIM_WORKERS} workers: the same link reproduces the same numbers. Minutes left blank are filled automatically (out players' minutes go to teammates, same position ×1.5, cap 38; each team totals 200).` }));
  }
  function rosterEditor(s, side) {
    const tid = side === 'h' ? s.hId : s.aId, t = W.team(tid), ids = roster(s, side);
    const box = h('div', { class: 'wn-roster' });
    box.append(h('div', { class: 'sh-h', text: `${t.abbr} rotation (${side === 'h' ? 'home' : 'away'})` }));
    const simMin = last && last.s && last.s[side === 'h' ? 'hId' : 'aId'] === tid ? last.minutes[side] : null;
    const tb = h('table', { class: 'sh-tbl wn-rtab' });
    tb.append(h('thead', null, h('tr', null, h('th', { text: 'In' }), h('th', { text: 'Player' }), h('th', { class: 'n', text: 'Dflt', title: 'Default projected minutes (her team role)' }), h('th', { class: 'n', text: 'Min', title: 'Fix her minutes (blank = automatic)' }), h('th', { class: 'n', text: 'Sim', title: 'Minutes used in the last run, after re-allocation' }))));
    const body = h('tbody'); tb.append(body);
    const sorted = ids.slice().sort((a, b) => (spById.get(b).min || 0) - (spById.get(a).min || 0));
    sorted.forEach(id => {
      const p = spById.get(id), moved = p.team !== tid, pl = W.player(id);
      const cb = h('input', { type: 'checkbox', class: 'ui-tog', checked: s.out.has(id) ? null : true, 'aria-label': 'Playing: ' + p.name });
      cb.addEventListener('change', () => { const o = st().out; cb.checked ? o.delete(id) : o.add(id); sheet.set({ out: [...o].join(',') || null }); markStale(); drawControls(); });
      const mi = h('input', { type: 'number', min: 0, max: 40, step: 1, class: 'wn-min', value: s.min[id] ?? '', placeholder: 'auto', 'aria-label': 'Minutes for ' + p.name });
      mi.addEventListener('change', () => { const m = st().min, v = parseFloat(mi.value); if (isFinite(v)) m[id] = Math.max(0, Math.min(40, v)); else delete m[id]; writeMin(m); markStale(); });
      const i = ids.indexOf(id);
      const nameCell = h('td', { class: 'wn-pn' }, h('a', { href: '#', text: p.name, onclick: e => { e.preventDefault(); if (pl) W.playerCard(pl, { prev: () => {}, next: () => {} }); } }), h('span', { class: 'muted', text: ' ' + p.pos_group + (moved ? ' · from ' + W.abbr(p.team) : '') }));
      if (moved) nameCell.append(' ', h('button', { class: 'sg-btn wn-x', type: 'button', text: '×', title: 'Remove from this roster', onclick: () => { const k = side === 'h' ? 'addh' : 'adda'; const m = st().min; delete m[id]; writeMin(m); sheet.set({ [k]: (side === 'h' ? st().addh : st().adda).filter(x => x !== id).join(',') || null }); markStale(); drawControls(); } }));
      body.append(h('tr', { class: s.out.has(id) ? 'wn-out' : '' }, h('td', null, cb), nameCell, h('td', { class: 'n muted', text: F.num(p.min, 1) }), h('td', { class: 'n' }, mi), h('td', { class: 'n', text: simMin && simMin[i] != null ? F.num(simMin[i], 1) : '' })));
    });
    box.append(h('div', { class: 'sh-tbl-wrap' }, tb));
    // add a player from anywhere
    const pool = SP.players.filter(p => !ids.includes(p.id)).map(p => ({ p, pl: W.player(p.id) })).sort((a, b) => ((a.p.team == null) - (b.p.team == null)) || ((b.pl && b.pl.impact.total) || -99) - ((a.pl && a.pl.impact.total) || -99));
    const sel = S.ui.select({ label: 'Add a player to ' + t.abbr, options: [{ value: 0, label: 'Choose: any team or free agent…' }].concat(pool.map(({ p, pl }) => ({ value: p.id, label: `${p.name} · ${W.abbr(p.team)} · ${pl && isNum(pl.impact.total) ? F.signed(pl.impact.total, 1) : ''}` }))), value: 0 });
    const add = S.ui.button({ label: 'Add', onClick: () => {
      const id = sel.value; if (!id) return;
      const k = side === 'h' ? 'addh' : 'adda', cur = side === 'h' ? st().addh : st().adda, other = side === 'h' ? 'adda' : 'addh', oc = side === 'h' ? st().adda : st().addh;
      const m = st().min; const p = spById.get(id); m[id] = p.min >= 1 ? Math.round(p.min) : 15; writeMin(m);
      sheet.set({ [k]: cur.concat(id).join(','), [other]: oc.filter(x => x !== id).join(',') || null }); markStale(); drawControls();
    } });
    box.append(S.ui.row(sel, add));
    return box;
  }
  let stale = false;
  function markStale() { if (last && !stale) { stale = true; status.textContent = 'Settings changed. Run again to update.'; } }
  function go(fromUser) {
    if (job) job.cancel();
    const s = st(), changed = sideChanged(s, 'h') || sideChanged(s, 'a') || ctxChanged(s);
    const bkey = s.hId + '_' + s.aId + '_' + s.n;
    const needBase = changed && !baseCache.has(bkey);
    const params = { sp: SP, home: spec(s, 'h'), away: spec(s, 'a'), opts: opts(s), sims: s.n, base: needBase ? { home: { team: s.hId }, away: { team: s.aId }, opts: {} } : null };
    prog.set(0); status.textContent = `Running ${F.int(s.n)} games${needBase ? ' plus the default for comparison' : ''}…`; stale = false;
    const t0 = performance.now();
    job = S.simulate({ module: 'sim-run.js', params, workers: SIM_WORKERS, seed: SIM_SEED, onProgress: f => prog.set(f) });
    job.then(r => {
      job = null; prog.set(1);
      const merged = W.mergeRuns(r.runs);
      const G = W.canonGame(merged.game, merged.home, merged.away, s.hId, s.aId); G.source = 'in-browser simulation';
      if (needBase) { const mb = W.mergeRuns(r.base); baseCache.set(bkey, W.canonGame(mb.game, mb.home, mb.away, s.hId, s.aId)); }
      if (!changed) baseCache.set(bkey, G);
      last = { s, G, minutes: { h: merged.meta.home_minutes, a: merged.meta.away_minutes } };
      status.textContent = `${F.int(G.n)} games in ${F.num((performance.now() - t0) / 1000, 1)} s.`;
      W.sim = { G, base: changed ? baseCache.get(bkey) : null, spec: params, seconds: (performance.now() - t0) / 1000 };   // exposed for checks
      drawResults(s, G, changed ? baseCache.get(bkey) : null);
      drawControls();
      if (fromUser === true && innerWidth < 980) right.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }).catch(e => { job = null; if (e.cancelled) return; status.textContent = ''; res.innerHTML = ''; res.append(S.errorEl(e, 'Simulation failed')); });
  }
  function drawResults(s, G, base) {
    res.innerHTML = '';
    const ref = D.M && !base ? W.game(s.hId, s.aId) : null;
    if (ref) {
      const n = Math.min(G.n, ref.n || 10000), zW = (G.homeWin - ref.homeWin) / Math.sqrt(G.homeWin * (1 - G.homeWin) * (1 / G.n + 1 / n)), zT = (G.total.mean - ref.total.mean) / (G.total.sd * Math.sqrt(1 / G.n + 1 / n));
      res.append(h('div', { class: 'sh-note', text: `Precomputed (matchups.json, ${F.int(ref.n)} sims): ${W.abbr(s.hId)} win ${F.pct(ref.homeWin, 1)}, total ${F.num(ref.total.mean, 1)}. Difference from this run: ${F.spct(G.homeWin - ref.homeWin, 1)} (z ${F.signed(zW, 1)}), ${F.signed(G.total.mean - ref.total.mean, 1)} pts (z ${F.signed(zT, 1)}).` }));
    }
    const gv = h('div', { class: 'sh-section wn-gap' }); res.append(gv);
    W.renderGame(gv, G, { base, neutral: s.neu, context: ctxText(s), lines: {}, playersNote: 'Out players are listed under each table.' });
  }
  drawControls();
  sheet.onState(() => { drawControls(); go(); });
  go();
}

/* ───────── Injury impact ───────── */
async function injury(panel, sheet) {
  await W.loadCore();
  const rows = D.players.filter(p => p.team != null && isNum(p.value.winp_delta));
  const near = t => D.teams.filter(x => x.id !== t).sort((a, b) => Math.abs(a.net) - Math.abs(b.net))[0];
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  const c1 = W.card(cols, 'Biggest single-game hits', 'Win probability lost (percentage points) vs a league-average opponent on a neutral floor when she is out and her minutes are re-allocated to teammates (normal approximation, from players.json). Click a bar for her card.');
  const top = rows.slice().sort((a, b) => a.value.winp_delta - b.value.winp_delta).slice(0, 20);
  S.bar(c1.appendChild(h('div')), { data: top.map(p => ({ label: `${p.name} (${p.team_abbr})`, value: -p.value.winp_delta, id: p.id, desc: `net ${F.signed(p.value.net_delta, 1)} per 100 when out` })), fmt: 'pct:1', diverging: false, valueLabel: 'win probability lost', barHeight: 11, rowGap: 5, onClick: d => W.playerCard(W.player(d.id), { prev: () => {}, next: () => {} }) });
  const c2 = W.card(cols, 'Where the drop comes from', 'Offence (ORtg change) against defence (DRtg change; + = team allows more) per 100 possessions when each rotation player sits. Top-right = the team loses offence and defence.');
  S.scatter(c2.appendChild(h('div')), { points: rows.filter(p => p.minutes.proj >= 10).map(p => ({ x: -p.value.off_delta, y: p.value.def_delta, label: p.name, id: p.id, desc: `${p.team_abbr} · Δwin ${F.spct(p.value.winp_delta, 1)}` })), xLabel: 'offence lost (−Δ ORtg)', yLabel: 'Δ DRtg (+ = worse D)', xFmt: 'signed:0', yFmt: 'signed:0', refX: 0, refY: 0, labels: 8, height: 280, onClick: pt => W.playerCard(W.player(pt.id), { prev: () => {}, next: () => {} }) });
  const gc = h('div', { class: 'sh-section' }); panel.append(gc);
  gc.append(h('div', { class: 'sh-h', text: 'Every rostered player' }), h('div', { class: 'sh-note', text: 'Sorted by win-probability hit. "Simulate" opens the simulator with her out against the most average opponent; the full possession sim captures usage and minutes knock-ons the normal approximation misses.' }));
  sheet.grid(gc, { height: 520, rows, sort: 'wd', csv: 'wnba-injury-impact.csv', searchPlaceholder: 'Search player or team', footer: false,
    onRowClick: r => W.playerCard(r, { prev: () => {}, next: () => {} }),
    columns: [
      { key: 'name', label: 'Player', frozen: true, width: 160 }, { key: 'team', label: 'Team', type: 'cat', get: r => r.team_abbr, width: 58 }, { key: 'pos', label: 'Pos', type: 'cat', get: r => r.pos_group, width: 50 },
      { key: 'mp', label: 'Min', get: get('minutes.proj'), fmt: 'num:1', desc: 'Default projected minutes.' }, { key: 'tot', label: 'Impact', get: get('impact.total'), fmt: 'signed:1', desc: 'O + D per 100.' },
      { key: 'wd', label: 'Δ Win%', get: get('value.winp_delta'), fmt: 'spct:1', heat: { center: 0 }, desc: 'Win-probability change when out (vs average opponent, neutral).' },
      { key: 'nd', label: 'Δ Net', get: get('value.net_delta'), fmt: 'signed:2', heat: { center: 0 }, desc: 'Team net rating change per 100 when out.' },
      { key: 'od', label: 'Δ ORtg', get: get('value.off_delta'), fmt: 'signed:2', desc: 'Team ORtg change per 100 when out.' },
      { key: 'dd', label: 'Δ DRtg', get: get('value.def_delta'), fmt: 'signed:2', heat: { center: 0, reverse: true }, desc: 'Team DRtg change per 100 when out (+ = defence gets worse).' },
      { key: 'vw', label: 'Wins', get: get('value.varp_wins'), fmt: 'signed:1', desc: 'Season wins above replacement.' },
      { key: 'sim', label: 'Sim', get: r => r.id, fmt: 'text', filter: false, render: (v, r) => { const o = near(r.team); return `<a href="${W.hashFor('sim', { h: r.team, a: o.id, out: r.id })}">vs ${esc(o.abbr)}</a>`; }, width: 70, desc: 'Run the full simulator with her out.' },
    ] });
}

/* ───────── Diagnostics ───────── */
const KNOWN_DIAG = ['aggregate', 'by_season', 'total_hist', 'margin_hist', 'star_scoring', 'star_scoring_by_player', 'teammate_pts_corr', 'skills_holdout', 'rapm_holdout', 'team_ratings_oos_2026', 'shot_model', 'lineup_reconstruction', 'sim_seconds'];
const pair = x => Array.isArray(x) && x.length === 2 && isNum(x[0]) ? x : null;
async function diagnostics(panel) {
  await W.loadCore();
  const Dg = await W.loadDiag();
  const ag = Dg.aggregate || {};
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  if (ag.total_mean) {
    const dT = ag.total_mean[1] - ag.total_mean[0];
    const c = W.card(cols, 'Re-simulated 2025–26 games', `${F.int(ag.n_games)} real games re-simulated ${F.int(ag.n_sims_per_game)} times each with the players, minutes and starters who actually played. Simulated totals average ${F.num(ag.total_mean[1], 1)} vs ${F.num(ag.total_mean[0], 1)} real (${F.signed(dT, 1)} pts), and the margin spread is close (${F.num(ag.margin_sd[1], 1)} vs ${F.num(ag.margin_sd[0], 1)}). In-sample: the ratings were fitted on these games.`);
    const lab = { total_mean: 'Total, mean', total_sd: 'Total, SD', margin_mean: 'Margin, mean (home)', margin_sd: 'Margin, SD', abs_margin_mean: '|Margin|, mean', home_win: 'Home win rate', ot_rate: 'OT rate', poss_per_team: 'Possessions / team' };
    const rows = Object.keys(lab).filter(k => pair(ag[k])).map(k => ({ k: lab[k], real: ag[k][0], sim: ag[k][1], pct: k === 'home_win' || k === 'ot_rate' }));
    S.table(c.appendChild(h('div')), [{ key: 'k', label: 'Measure' }, { key: 'real', label: 'Real', render: (v, r) => r.pct ? F.pct(v, 1) : F.num(v, 2) }, { key: 'sim', label: 'Simulated', render: (v, r) => r.pct ? F.pct(v, 1) : F.num(v, 2) }, { key: 'd', label: 'Sim − real', render: (v, r) => r.pct ? F.spct(r.sim - r.real, 1) : F.signed(r.sim - r.real, 2) }], rows);
  }
  if (Dg.by_season) {
    const bs = Object.entries(Dg.by_season);
    const worst = bs.map(([s, v]) => [s, v.total_mean ? v.total_mean[1] - v.total_mean[0] : 0]).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
    const c = W.card(cols, 'By season', `The totals gap is a season effect: simulated totals are ${F.signed(worst[1], 1)} pts off in ${worst[0]}, because every game is played at 2026 league scoring levels. Columns: real, then simulated.`);
    S.table(c.appendChild(h('div')), [{ key: 's', label: 'Season' }, { key: 'tr', label: 'Total', fmt: 'num:1', desc: 'real mean total' }, { key: 'ts', label: 'Sim', fmt: 'num:1', desc: 'simulated mean total' }, { key: 'sr', label: 'SD', fmt: 'num:1', desc: 'real total SD' }, { key: 'ss', label: 'Sim', fmt: 'num:1', desc: 'simulated total SD' }, { key: 'mr', label: 'Mgn SD', fmt: 'num:1', desc: 'real margin SD' }, { key: 'ms', label: 'Sim', fmt: 'num:1', desc: 'simulated margin SD' }],
      bs.map(([s, v]) => ({ s, tr: (v.total_mean || [])[0], ts: (v.total_mean || [])[1], sr: (v.total_sd || [])[0], ss: (v.total_sd || [])[1], mr: (v.margin_sd || [])[0], ms: (v.margin_sd || [])[1] })));
  }
  const histCard = (key, title, note, xl) => {
    const hh = Dg[key]; if (!hh || !hh.edges) return;
    const c = W.card(cols, title, note);
    const mid = hh.edges.slice(0, -1).map((e, i) => (e + hh.edges[i + 1]) / 2);
    S.line(c.appendChild(h('div')), { series: [{ name: 'Real', points: mid.map((x, i) => [x, hh.real[i] * (hh.edges[1] - hh.edges[0])]) }, { name: 'Simulated', points: mid.map((x, i) => [x, hh.sim[i] * (hh.edges[1] - hh.edges[0])]) }], xLabel: xl, yFmt: 'pct:0', height: 170 });
  };
  histCard('total_hist', 'Total points: real vs simulated', 'Share of games per 5-point bin. The simulated curve sits slightly right of the real one: the totals bias above.', 'total');
  histCard('margin_hist', 'Margin: real vs simulated', 'Share of games per 5-point bin of home margin. The simulated spread of outcomes matches the real one closely.', 'home margin');
  const ss = Dg.star_scoring;
  if (ss) {
    const c = W.card(cols, 'Star scoring', `High-usage players (projected usage ≥ 24%) in games with ≥ 25 minutes, ${F.int(ss.n_player_games)} player-games: simulated stars score ${F.num(ss.mean_pts[1], 1)} vs ${F.num(ss.mean_pts[0], 1)} real, and reach 20+ less often. Star overs are priced low by this model.`);
    S.table(c.appendChild(h('div')), [{ key: 'k', label: 'Measure' }, { key: 'r', label: 'Real' }, { key: 's', label: 'Simulated' }],
      [['Mean points', 'mean_pts', 1], ['SD points', 'sd_pts', 1], ['Share 20+', 'share_20plus', 0], ['Share 30+', 'share_30plus', 0], ['Share under 10', 'share_10minus', 0]].filter(x => pair(ss[x[1]])).map(([k, f, dp]) => ({ k, r: dp ? F.num(ss[f][0], 1) : F.pct(ss[f][0], 1), s: dp ? F.num(ss[f][1], 1) : F.pct(ss[f][1], 1) })));
  }
  if (Array.isArray(Dg.star_scoring_by_player)) {
    const L = Dg.star_scoring_by_player;
    const below = L.filter(x => x.sim < x.real).length;
    const c = W.card(cols, 'Star scoring by player', `${below} of ${L.length} stars score less in the re-simulation than they did (points below the diagonal). Hover for each player.`);
    S.scatter(c.appendChild(h('div')), { points: L.map(x => ({ x: x.real, y: x.sim, label: x.name, id: x.pid, desc: `${x.games} games` })), xLabel: 'real ppg', yLabel: 'simulated ppg', diag: true, labels: 5, height: 240, onClick: pt => { const p = W.player(pt.id); if (p) W.playerCard(p, { prev: () => {}, next: () => {} }); } });
  }
  const oos = Dg.team_ratings_oos_2026;
  if (oos) {
    const c = W.card(cols, 'Out of sample: 2026 team ratings', `Ratings fitted on 2017–25 only, predicting 2026 margins from each game's actual minutes. RMSE ${F.num(oos.rmse_model, 2)} vs ${F.num(oos.rmse_prev_season_diff, 2)} for last season's point differential and ${F.num(oos.rmse_hca_only, 2)} for home court alone. No market comparison.`);
    c.append(S.tiles([{ label: 'RMSE', value: F.num(oos.rmse_model, 2), sub: F.int(oos.n_games) + ' games' }, { label: 'Corr.', value: F.num(oos.corr_model, 3) }, { label: 'Winner', value: F.pct(oos.win_acc_model, 1), sub: 'picked right' }, { label: 'Slope', value: F.num(oos.calibration_slope, 3), sub: '1 = well scaled' }]));
  }
  const rh = Dg.rapm_holdout;
  if (rh) {
    const c = W.card(cols, 'Out of sample: RAPM', 'Forward holdouts (train on seasons before S, score every possession of S, 2024–26). The prior-informed version beats plain RAPM; gains are small because single possessions are mostly noise.');
    S.table(c.appendChild(h('div')), [{ key: 'k', label: 'Model' }, { key: 'mse', label: 'MSE', fmt: 'num:1' }, { key: 'g', label: 'Gain vs const', fmt: 'num:1' }, { key: 'p', label: 'Params' }],
      [{ k: 'Constant', mse: rh.mse_const, g: 0, p: '' }, rh.best_plain && { k: 'Plain RAPM', mse: rh.best_plain.mse, g: rh.best_plain.gain_vs_const, p: `H ${rh.best_plain.H}, λ ${rh.best_plain.lam}` }, rh.best_prior && { k: 'Prior-informed', mse: rh.best_prior.mse, g: rh.best_prior.gain_vs_const, p: `H ${rh.best_prior.H}, λ ${rh.best_prior.lam}` }].filter(Boolean));
    if (rh.spm_r2_weighted) c.append(h('div', { class: 'sh-note', text: `Box-score prior weighted R²: O ${F.num(rh.spm_r2_weighted.O, 2)}, D ${F.num(rh.spm_r2_weighted.D, 2)} (defence is the noisier half).` }));
  }
  if (Dg.skills_holdout) {
    const sk = Object.entries(Dg.skills_holdout).map(([k, v]) => ({ label: k.replace(/_/g, ' '), value: v.deviance_gain_vs_position_prior_pct, desc: `half-life ${v.H} seasons, prior strength k = ${v.k}` }));
    const c = W.card(cols, 'Out of sample: skill projections', 'Binomial deviance gain (%) over a position-group prior on forward holdouts, per projected rate. Shot mix and passing carry the most player signal; FG% by zone the least.');
    S.bar(c.appendChild(h('div')), { data: sk, sort: 'desc', fmt: 'num:1', diverging: false, barHeight: 10, rowGap: 4 });
  }
  const sm = Dg.shot_model;
  if (sm && sm.calib) {
    const c = W.card(cols, 'Shot model calibration', `Cross-fitted xFG on ${F.int(sm.n)} shots: log-loss ${F.num(sm.logloss, 4)} vs ${F.num(sm.logloss_zone, 4)} zone-only and ${F.num(sm.logloss_const, 4)} constant. Predicted and actual FG% agree in every bin.`);
    S.scatter(c.appendChild(h('div')), { points: sm.calib.xfg.map((x, i) => ({ x, y: sm.calib.fg[i], label: F.int(sm.calib.n[i]) + ' shots', desc: `predicted ${F.pct(x, 1)}, actual ${F.pct(sm.calib.fg[i], 1)}` })), diag: true, xFmt: 'pct:0', yFmt: 'pct:0', xLabel: 'predicted FG%', yLabel: 'actual FG%', labels: false, height: 200 });
  }
  const tc = Dg.teammate_pts_corr;
  if (tc) {
    const c = W.card(cols, 'Teammate scoring correlation', 'Correlation of two teammates\' points (both ≥ 20 min). Real games show a slight negative correlation (one player\'s points come out of the other\'s), and the simulation reproduces it; same-game parlays need this.');
    c.append(S.kv([['Real, across games', F.num(tc.real_across_games, 3) + ` (${F.int(tc.n_real_pairs)} pairs)`], ['Simulated, across games', F.num(tc.sim_across_games, 3) + ` (${F.int(tc.n_sim_pairs)} pairs)`], ['Simulated, within one matchup', F.num(tc.sim_within_game, 3)]]));
  }
  if (Dg.lineup_reconstruction) {
    const c = W.card(cols, 'Lineup reconstruction', 'Who was on the floor, rebuilt from play-by-play substitutions and checked against box-score minutes. 2018–19 are the weakest seasons.');
    S.table(c.appendChild(h('div')), [{ key: 's', label: 'Season' }, { key: 'games', label: 'Games', fmt: 'int' }, { key: 'poss_lineup_ok', label: '5v5 known', fmt: 'pct:1' }, { key: 'min_within_1', label: 'Min ±1', fmt: 'pct:1' }, { key: 'min_mae', label: 'Min MAE', fmt: 'num:2' }, { key: 'phantom_fix', label: 'Fixes', fmt: 'int', desc: 'players inserted because they acted while not on court' }],
      Object.entries(Dg.lineup_reconstruction).map(([s, v]) => Object.assign({ s }, v)));
  }
  // anything a later export adds (player calibration tables, win-probability reliability, …)
  Object.keys(Dg).filter(k => !KNOWN_DIAG.includes(k)).forEach(k => genericDiag(cols, k, Dg[k]));
}
const titleCase = k => k.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
function findXY(o) {
  const keys = Object.keys(o).filter(k => Array.isArray(o[k]) && o[k].length > 1 && o[k].every(v => v == null || isNum(v)));
  const px = keys.find(k => /pred|model|sim|xfg|expected|proj|^p$|forecast/i.test(k)), py = keys.find(k => k !== px && /obs|actual|real|empirical|outcome|^fg$|freq|rate/i.test(k));
  return px && py && o[px].length === o[py].length ? [px, py, keys] : null;
}
function genericDiag(parent, key, val) {
  if (val == null || typeof val !== 'object') { if (val != null) W.card(parent, titleCase(key), null).append(S.kv([[titleCase(key), String(val)]])); return; }
  const c = W.card(parent, titleCase(key), /calib|reliab/i.test(key) ? 'Predicted against observed: points on the diagonal are well calibrated.' : 'Added by a later model export; shown as exported.');
  const body = h('div'); c.append(body);
  const asTable = arrObj => { const ks = [...new Set(arrObj.flatMap(r => Object.keys(r)))].filter(k => arrObj.some(r => r[k] == null || typeof r[k] !== 'object')); S.table(body.appendChild(h('div')), ks.map(k => ({ key: k, label: k, render: v => esc(isNum(v) ? (Math.abs(v) < 1 && v !== 0 ? F.num(v, 3) : F.num(v, Number.isInteger(v) ? 0 : 2)) : v ?? '') })), arrObj.slice(0, 40)); };
  const xy = !Array.isArray(val) && findXY(val);
  if (xy) {
    const [px, py, keys] = xy;
    S.scatter(body.appendChild(h('div')), { points: val[px].map((x, i) => ({ x, y: val[py][i], label: val.n ? 'n ' + F.int(val.n[i]) : '' })).filter(p => isNum(p.x) && isNum(p.y)), diag: true, xLabel: px, yLabel: py, labels: false, height: 200 });
    asTable(val[px].map((_, i) => Object.fromEntries(keys.map(k => [k, val[k][i]]))));
    return;
  }
  if (Array.isArray(val)) {
    if (val.length && typeof val[0] === 'object') {
      const first = val[0], xy2 = ['pred', 'p_pred', 'predicted', 'model', 'sim', 'proj'].find(k => isNum(first[k])), yy = ['obs', 'actual', 'real', 'observed', 'freq'].find(k => isNum(first[k]));
      if (xy2 && yy) S.scatter(body.appendChild(h('div')), { points: val.map(r => ({ x: r[xy2], y: r[yy], label: r.name || r.bin || '' })), diag: true, xLabel: xy2, yLabel: yy, labels: 5, height: 220 });
      asTable(val);
    } else body.append(h('div', { class: 'sh-note', text: JSON.stringify(val).slice(0, 600) }));
    return;
  }
  // object: nested tables per sub-key, or a flat key/value list
  const flat = [];
  for (const [k, v] of Object.entries(val)) {
    if (Array.isArray(v) && v.length && typeof v[0] === 'object') { body.append(h('div', { class: 'wn-sub', text: titleCase(k) })); asTable(v); }
    else if (v && typeof v === 'object' && !Array.isArray(v) && findXY(v)) { const sub = h('div'); body.append(h('div', { class: 'wn-sub', text: titleCase(k) }), sub); genericDiag(sub, k, v); }
    else if (v && typeof v === 'object' && !Array.isArray(v)) flat.push(...Object.entries(v).map(([k2, v2]) => [k + ' · ' + k2, v2]));
    else flat.push([k, v]);
  }
  if (flat.length) body.append(S.kv(flat.slice(0, 60).map(([k, v]) => [titleCase(k), Array.isArray(v) ? v.map(x => isNum(x) ? F.num(x, 3) : x).join(', ') : isNum(v) ? F.num(v, Math.abs(v) < 10 ? 3 : 1) : String(v)])));
}

/* ───────── Method ───────── */
async function method(panel) {
  const a = h('div'); panel.append(a);
  await S.loadMarkdown(a, 'data/method.md');
  const b = h('details', { class: 'wn-schema' }, h('summary', { text: 'Data files and field definitions (schema.md)' }));
  const bd = h('div'); b.append(bd); panel.append(b);
  b.addEventListener('toggle', () => { if (b.open && !bd.childElementCount) S.loadMarkdown(bd, 'data/schema.md', { idPrefix: 'schema-' }); }, { once: false });
}

/* ───────── workbook ───────── */
const oddsCtl = S.ui.segmented({ options: [{ value: 'american', label: 'US' }, { value: 'decimal', label: 'Dec' }], value: W.odds.mode, onChange: v => W.odds.set(v) });
oddsCtl.classList.add('wn-odds'); oddsCtl.title = 'Fair-odds format: American (US) or decimal';
W.wb = S.workbook({
  title: 'WNBA projections', subtitle: 'Bottom-up player ratings, possession simulator', hub: '../',
  meta: 'data/meta.json', actions: oddsCtl, defaultSheet: 'overview',
  sheets: [
    { id: 'overview', name: 'Overview', render: overview },
    { id: 'players', name: 'Players', fill: true, render: players },
    { id: 'teams', name: 'Teams', render: teams },
    { id: 'matchups', name: 'Matchups', render: matchups },
    { id: 'game', name: 'Game', render: game },
    { id: 'props', name: 'Player props', render: props },
    { id: 'sim', name: 'Simulator', render: simulator },
    { id: 'injury', name: 'Injury impact', render: injury },
    { id: 'diag', name: 'Diagnostics', render: diagnostics },
    { id: 'method', name: 'Method', render: method },
  ],
});
})();
