/* IPL workbook: sheet definitions. Depends on ../assets/sheet.js (Sheets) and app.js (IPL). */
(function () {
'use strict';
const S = Sheets, I = IPL, D = I.D, h = S.h, esc = S.esc, F = S.fmt, isNum = I.isNum;
const get = path => row => { let o = row; for (const k of path.split('.')) { if (o == null) return null; o = o[k]; } return o == null || (typeof o === 'number' && !isFinite(o)) ? null : o; };
const pct100 = v => isNum(v) ? F.num(v, 1) + '%' : '';      // rates already per 100 balls
const IPLC = 'IPL 2024–26 conditions: every real IPL delivery of 2024–26 with this player swapped in (same opponent, venue, season and situation).';

/* ───────── shared bits ───────── */
const SET_BUCKETS = { early: [0, 1, 2, 3], set: [6, 7, 8] };   // settling buckets: balls faced 0–9 vs 20+
const BW = [1, 2, 3, 4, 5, 5, 10, 15, 1];                        // bucket widths (balls) for the weighted early mean
function settle(arr, which, k) {
  if (!Array.isArray(arr) || arr.length < 9) return null;
  const ix = SET_BUCKETS[which]; let s = 0, w = 0;
  ix.forEach(i => { const v = arr[i] && arr[i][k]; if (isNum(v)) { const ww = which === 'early' ? BW[i] : 1; s += v * ww; w += ww; } });
  return w ? s / w : null;
}
const teamCol = { key: 'team', label: 'Team', group: 'Profile', type: 'cat', get: r => r._team ? r._team.short : '—', width: 58, desc: 'Franchise in the 2026 IPL season (— = not in an IPL squad).' };
const nameCol = { key: 'name', label: 'Player', frozen: true, width: 160, desc: 'Click a row for the player card. Arrow keys move rows while the card is open.' };
const mixCols = [
  { key: 'mx_ipl', label: 'IPL %', group: 'Sample', get: get('league_mix.ipl'), fmt: 'pct:0', desc: 'Share of his (recency-weighted) deliveries that came in the IPL.' },
  { key: 'mx_int', label: 'Intl %', group: 'Sample', get: get('league_mix.intl'), fmt: 'pct:0', desc: 'Share in full-member T20 internationals.' },
  { key: 'mx_fr', label: 'Fran %', group: 'Sample', get: r => r.league_mix ? (r.league_mix.top_fr || 0) + (r.league_mix.fr2 || 0) : null, fmt: 'pct:0', desc: 'Share in overseas franchise leagues (BBL, PSL, CPL, SA20, ILT20, MLC, BPL, LPL, Blast…).' },
  { key: 'mx_dom', label: 'Dom %', group: 'Sample', get: r => r.league_mix ? (r.league_mix.india_dom || 0) + (r.league_mix.dom || 0) + (r.league_mix.assoc || 0) : null, fmt: 'pct:0', desc: 'Share in domestic T20 (Syed Mushtaq Ali and others) and associate T20Is: the most heavily discounted leagues (see Leagues).' },
  { key: 'last', label: 'Last played', group: 'Sample', type: 'text', get: r => r._last, width: 92, desc: 'Date of his most recent T20 match in the data (any competition).' },
  { key: 'lastipl', label: 'Last IPL', group: 'Sample', type: 'text', get: r => r.last_played_ipl || '', width: 92, desc: 'Date of his most recent IPL match.' },
];
const TYPES = [['pace_R', 'R pace', 'right-arm pace'], ['pace_L', 'L pace', 'left-arm pace'], ['OB', 'Off-spin', 'off-spin'], ['LB', 'Leg-spin', 'leg-spin'], ['SLA', 'SLA', 'left-arm orthodox spin'], ['SLW', 'L wrist', 'left-arm wrist spin']];
const byTypeCols = () => TYPES.flatMap(([k, l, d]) => [
  { key: 'ty_' + k, label: 'SR ' + l, group: 'vs bowl type', get: get('bat.by_type.' + k + '.sr'), fmt: 'num:1', desc: `True strike rate against ${d} (deliveries of that type only; blank = under 200 reference deliveries).` },
  { key: 'tyd_' + k, label: 'Δ ' + l, group: 'vs bowl type', get: get('bat.by_type.' + k + '.vs_avg.sr'), fmt: 'signed:1', heat: { center: 0 }, desc: `Strike rate against ${d} minus the average IPL batter on the same deliveries.` },
  { key: 'tyo_' + k, label: 'Out ' + l, group: 'vs bowl type', get: get('bat.by_type.' + k + '.out_pct'), fmt: 'num:2', heat: { type: 'seq' }, hidden: true, desc: `Dismissals per 100 balls against ${d}. Lower is better.` },
]);
const projCol = (key, label, f, desc, extra) => Object.assign({ key, label, group: 'Projection', get: r => { const p = I.proj(r.id); return p ? f(p) : null; }, fmt: 'num:1', desc: desc + ' Mean over his team\'s 18 precomputed matchups (default XI, home and away). Fills in once matchups.json has loaded.' }, extra);
const actCol = (key, label, f, desc) => ({ key, label, group: 'IPL 2026', get: r => r._act ? f(r._act) : null, fmt: 'num:1', desc: desc + ' Actual IPL 2026 per match, when the export carries it.' });

/* ───────── Batters grid ───────── */
function batCols() {
  const A = D.avgBat || {}, a = s => (A[s] || {});
  return [
    nameCol, teamCol,
    { key: 'role', label: 'Role', group: 'Profile', type: 'cat', get: r => ({ open: 'Open', top: 'Top', middle: 'Middle', lower: 'Lower' })[r.role_bat] || '', width: 62, desc: 'Prior group by career median batting position: Open (1–2), Top (3–4), Middle (5–7), Lower (8–11).' },
    { key: 'hand', label: 'Hand', group: 'Profile', type: 'cat', get: r => r.bat_hand ? r.bat_hand + 'HB' : (r.bat_hand_used || r.style_defaulted && r.style_defaulted.bat_hand ? (r.bat_hand_used || 'R') + 'HB*' : ''), cls: (v, r) => r.style_defaulted && r.style_defaulted.bat_hand ? 'muted' : '', width: 58, desc: 'Batting hand. * (grey) = hand unknown; the simulator assumes right-handed.' },
    { key: 'os', label: 'OS', group: 'Profile', type: 'cat', get: r => r.overseas ? 'OS' : '', width: 42, desc: 'Overseas player (played T20Is for a country other than India).' },
    { key: 'slot', label: 'Slot', group: 'Profile', get: get('bat.value.slot'), fmt: 'int', width: 46, desc: 'Batting slot used for his value: default team order, else his IPL median position.' },
    { key: 'iplb', label: 'IPL balls', group: 'Sample', get: get('bat.obs_ipl_2024.balls'), fmt: 'int', desc: 'Balls faced in the IPL since 2024.' },
    { key: 'allb', label: 'All balls', group: 'Sample', get: get('bat.obs_2024.balls'), fmt: 'int', desc: 'Balls faced in all 20-over T20 since 2024.' },
    ...mixCols,
    { key: 'vr', label: 'Runs/m', group: 'Value', get: get('bat.value.varp_runs'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Batting value above replacement, runs per match: (his run value − replacement) per 100 balls × the balls his slot faces per innings.' },
    { key: 'vw', label: 'Win%/m', group: 'Value', get: get('bat.value.varp_wp'), fmt: 'spct:1', heat: { center: 0 }, desc: 'The same in win probability per match (percentage points).' },
    { key: 'rv', label: 'RV/100', group: 'Value', get: get('bat.all.rv100'), fmt: 'num:1', heat: { center: a('all').rv100 ?? 109 }, desc: 'Run value per 100 balls = runs minus wickets × the runs a wicket costs in that situation. ' + IPLC },
    { key: 'vpct', label: 'Pctile', group: 'Value', get: get('bat.pct.bat_varp'), fmt: 'int', desc: 'Percentile of batting value among pool batters (≥100 IPL balls or ≥300 balls anywhere since 2024).' },
    { key: 'sr', label: 'SR', group: 'True rates', get: get('bat.all.sr'), fmt: 'num:1', heat: { center: a('all').sr ?? 150 }, desc: 'True strike rate, runs per 100 balls, in his own phase mix. ' + IPLC },
    { key: 'srsd', label: '± SR', group: 'True rates', get: get('bat.sd.sr'), fmt: 'num:1', desc: 'Posterior SD of the true strike rate (somewhat too small: ignores correlation with other terms).' },
    { key: 'avg', label: 'Avg', group: 'True rates', get: get('bat.all.avg'), fmt: 'num:1', heat: { center: a('all').avg ?? 30 }, desc: 'True average, runs per dismissal. ' + IPLC },
    { key: 'avsd', label: '± Avg', group: 'True rates', get: get('bat.sd.avg'), fmt: 'num:1', desc: 'Posterior SD of the true average.' },
    { key: 'out', label: 'Out/100', group: 'True rates', get: get('bat.all.out_pct'), fmt: 'num:2', heat: { center: a('all').out_pct ?? 5, reverse: true }, desc: 'Dismissals per 100 balls. Lower is better (red = gets out more).' },
    { key: 'dsr', label: 'SR vs avg', group: 'True rates', get: get('bat.vs_avg.all.sr'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Strike rate minus the average IPL batter on the same deliveries.' },
    { key: 'bnd', label: 'Bnd %', group: 'True rates', get: get('bat.all.bnd_pct'), fmt: pct100, heat: { center: a('all').bnd_pct ?? 21 }, desc: 'Boundaries (4s + 6s) per 100 balls.' },
    { key: 'f4', label: '4 %', group: 'True rates', get: get('bat.all.four_pct'), fmt: pct100, desc: 'Fours per 100 balls.' },
    { key: 's6', label: '6 %', group: 'True rates', get: get('bat.all.six_pct'), fmt: pct100, heat: { center: a('all').six_pct ?? 7.6 }, desc: 'Sixes per 100 balls.' },
    { key: 'dot', label: 'Dot %', group: 'True rates', get: get('bat.all.dot_pct'), fmt: pct100, heat: { center: a('all').dot_pct ?? 34, reverse: true }, desc: 'Balls with no run off the bat (incl. dismissals), per 100. Lower is better.' },
    { key: 'nbsr', label: 'NB SR', group: 'True rates', get: get('bat.all.nbsr'), fmt: 'num:1', heat: { center: a('all').nbsr ?? 64 }, desc: 'Strike rate on non-boundary balls: how well he rotates strike.' },
    { key: 'osr', label: 'SR', group: 'vs expected', get: get('bat.obs_2024.sr'), fmt: 'num:1', desc: 'Actual strike rate since 2024, all competitions (unshrunk).' },
    { key: 'oxsr', label: 'xSR', group: 'vs expected', get: get('bat.obs_2024.xsr'), fmt: 'num:1', desc: 'What an average IPL batter would have struck on the same deliveries (same bowlers, venue, league, situation).' },
    { key: 'rae', label: 'RAE/100', group: 'vs expected', get: get('bat.obs_2024.rae100'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Runs above expected per 100 balls since 2024 (actual − expected). Unshrunk; the true rating shrinks this toward his prior.' },
    { key: 'oox', label: 'Outs vs x', group: 'vs expected', get: get('bat.obs_2024.outs_vs_x'), fmt: 'signed:1', heat: { center: 0, reverse: true }, desc: 'Dismissals minus expected since 2024. Negative = got out less than an average batter would (good).' },
    { key: 'o4x', label: '4s vs x', group: 'vs expected', get: r => { const o = r.bat && r.bat.obs_2024; return o && isNum(o.fours) && isNum(o.x4) ? o.fours - o.x4 : null; }, fmt: 'signed:0', heat: { center: 0 }, desc: 'Fours hit minus expected since 2024.' },
    { key: 'o6x', label: '6s vs x', group: 'vs expected', get: r => { const o = r.bat && r.bat.obs_2024; return o && isNum(o.sixes) && isNum(o.x6) ? o.sixes - o.x6 : null; }, fmt: 'signed:0', heat: { center: 0 }, desc: 'Sixes hit minus expected since 2024.' },
    { key: 'iprae', label: 'IPL RAE', group: 'vs expected', get: get('bat.obs_ipl_2024.rae100'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Runs above expected per 100 balls, IPL only, since 2024.' },
    { key: 'wpa', label: 'WPA/m', group: 'vs expected', get: get('bat.obs_2024.wpa_per_match'), fmt: 'spct:1', desc: 'Win probability added per match since 2024 (separate win-probability model).' },
    ...I.PH.map(p => ({ key: 'sr_' + p, label: 'SR ' + { pp: 'PP', mid: 'Mid', death: 'Death' }[p], group: 'Phases', get: get('bat.' + p + '.sr'), fmt: 'num:1', heat: { center: a(p).sr ?? 150 }, desc: `True strike rate in the ${I.PH_LABEL[p].toLowerCase()} (${I.PH_OVERS[p]}), on every IPL delivery of that phase.` })),
    ...I.PH.map(p => ({ key: 'out_' + p, label: 'Out ' + { pp: 'PP', mid: 'Mid', death: 'Death' }[p], group: 'Phases', get: get('bat.' + p + '.out_pct'), fmt: 'num:2', heat: { center: a(p).out_pct ?? 5, reverse: true }, desc: `Dismissals per 100 balls in the ${I.PH_LABEL[p].toLowerCase()}. Lower is better.` })),
    { key: 'sr_pace', label: 'SR pace', group: 'Pace / spin', get: get('bat.pace.sr'), fmt: 'num:1', heat: { center: a('pace').sr ?? 155 }, desc: 'True strike rate against pace.' },
    { key: 'sr_spin', label: 'SR spin', group: 'Pace / spin', get: get('bat.spin.sr'), fmt: 'num:1', heat: { center: a('spin').sr ?? 140 }, desc: 'True strike rate against spin.' },
    { key: 'out_pace', label: 'Out pace', group: 'Pace / spin', get: get('bat.pace.out_pct'), fmt: 'num:2', heat: { center: a('pace').out_pct ?? 5, reverse: true }, desc: 'Dismissals per 100 balls against pace. Lower is better.' },
    { key: 'out_spin', label: 'Out spin', group: 'Pace / spin', get: get('bat.spin.out_pct'), fmt: 'num:2', heat: { center: a('spin').out_pct ?? 5, reverse: true }, desc: 'Dismissals per 100 balls against spin. Lower is better.' },
    { key: 'spgap', label: 'Spin − pace', group: 'Pace / spin', get: r => r.bat && r.bat.vs_avg && isNum(r.bat.vs_avg.spin.sr) ? r.bat.vs_avg.spin.sr - r.bat.vs_avg.pace.sr : null, fmt: 'signed:1', heat: { center: 0 }, desc: 'SR vs average against spin minus SR vs average against pace. + = relatively better against spin.' },
    { key: 'st_sr0', label: 'SR 1–10', group: 'Settling', get: r => settle(r.bat && r.bat.settling, 'early', 0), fmt: 'num:1', desc: 'Strike rate over his first 10 balls (middle-overs context; balls-weighted over the 0, 1–2, 3–5 and 6–9 buckets).' },
    { key: 'st_sr1', label: 'SR set', group: 'Settling', get: r => settle(r.bat && r.bat.settling, 'set', 0), fmt: 'num:1', desc: 'Strike rate once set (20+ balls faced, middle-overs context).' },
    { key: 'st_o0', label: 'Out 1–10', group: 'Settling', get: r => settle(r.bat && r.bat.settling, 'early', 1), fmt: 'num:2', heat: { type: 'seq' }, desc: 'Dismissals per 100 balls over his first 10 balls.' },
    { key: 'st_d', label: 'Start vs avg', group: 'Settling', get: r => { const v = settle(r.bat && r.bat.settling, 'early', 0), av = settle(D.settlingAvg, 'early', 0); return isNum(v) && isNum(av) ? v - av : null; }, fmt: 'signed:1', heat: { center: 0 }, desc: 'His first-10-balls strike rate minus the average batter\'s. + = starts faster.' },
    projCol('pr', 'Runs', p => p.runs_mean, 'Projected runs per innings.', { heat: { type: 'seq' } }),
    projCol('pb', 'Balls', p => p.balls_mean, 'Projected balls faced per innings.'),
    projCol('p30', 'P(30+)', p => p.pRuns && p.pRuns['30'], 'Probability of 30 or more.', { fmt: 'pct:0' }),
    projCol('p6', '6s', p => p.sixes_mean, 'Projected sixes per innings.', { fmt: 'num:2' }),
    projCol('ppos', 'Pos', p => p.pos, 'Batting position in the default XI.', { fmt: 'int' }),
    actCol('am', 'M', l => l.m, 'Matches.'), actCol('ai', 'Inns', l => l.bat_inns, 'Batting innings.'), actCol('ar', 'Runs/m', l => l.runs, 'Runs per match.'), actCol('asr', 'SR', l => l.sr, 'Strike rate.'), actCol('aavg', 'Avg', l => l.avg, 'Batting average.'),
    { key: 'dpr', label: 'Proj − act', group: 'IPL 2026', get: r => { const p = I.proj(r.id); return p && isNum(p.runs_mean) && r._act && isNum(r._act.runs) ? p.runs_mean - r._act.runs : null; }, fmt: 'signed:1', heat: { center: 0 }, desc: 'Projected runs per match (default role) minus actual IPL 2026 runs per match. Regression toward the prior and batting-slot changes both feed this.' },
    ...byTypeCols(),
    { key: 'ci', label: 'Inns', group: 'IPL career', get: get('bat.ipl_career.inns'), fmt: 'int', desc: 'IPL career innings.' },
    { key: 'cr', label: 'Runs', group: 'IPL career', get: get('bat.ipl_career.runs'), fmt: 'int', desc: 'IPL career runs.' },
    { key: 'csr', label: 'SR', group: 'IPL career', get: get('bat.ipl_career.sr'), fmt: 'num:1', desc: 'IPL career strike rate (raw).' },
  ];
}
const BAT_GROUPS = ['Profile', 'Sample', 'Value', 'True rates', 'vs expected', 'Phases', 'Pace / spin', 'Settling', 'Projection', 'IPL 2026', 'vs bowl type', 'IPL career'];

/* ───────── Bowlers grid ───────── */
function bowlCols() {
  const A = D.avgBowl || {}, a = s => (A[s] || {});
  return [
    nameCol, teamCol,
    { key: 'type', label: 'Type', group: 'Profile', type: 'cat', get: r => (r.bowl_type && r.bowl_type !== 'none' ? r.bowl_type : r.bowl_subtype || '') + (r.style_defaulted && r.style_defaulted.bowl_type ? '*' : ''), cls: (v, r) => r.style_defaulted && r.style_defaulted.bowl_type ? 'muted' : '', width: 66, desc: 'Bowling type: RF/RFM/RM/LF/LFM/LM pace; OB off-spin, LB leg-spin, SLA left-arm orthodox, SLW left-arm wrist. * (grey) = type unknown, the simulator uses the generic pace/spin subtype.' },
    { key: 'grp', label: 'Group', group: 'Profile', type: 'cat', get: r => r.bowl_group || '', width: 56, desc: 'Pace or spin.' },
    { key: 'inf', label: 'Inferred', group: 'Profile', type: 'cat', get: r => r.style_inferred ? 'inferred' : '', width: 64, desc: 'Pace/spin label came from a classifier, not the styles file.' },
    { key: 'rb', label: 'Workload', group: 'Profile', type: 'cat', get: r => ({ part: 'Part-time', reg: 'Regular', front: 'Frontline' })[(r.role_bowl || '').split('_')[1]] || '', width: 74, desc: 'Prior group by career overs per match: part-time (<1.5), regular (1.5–2.75), frontline (>2.75).' },
    { key: 'os', label: 'OS', group: 'Profile', type: 'cat', get: r => r.overseas ? 'OS' : '', width: 42, desc: 'Overseas player.' },
    { key: 'inplan', label: 'In plan', group: 'Profile', type: 'cat', get: r => r.bowl && r.bowl.in_plan === true ? 'Yes' : r.bowl && r.bowl.in_plan === false && r._team ? 'No' : '', width: 60, desc: 'Has overs in his team\'s default 20-over bowling plan. "No" = squad player who bowls a little in his role (under 1 projected over) but is not in the integer plan the simulator bowls.' },
    { key: 'iplb', label: 'IPL balls', group: 'Sample', get: get('bowl.obs_ipl_2024.balls'), fmt: 'int', desc: 'Legal balls bowled in the IPL since 2024.' },
    { key: 'allb', label: 'All balls', group: 'Sample', get: get('bowl.obs_2024.balls'), fmt: 'int', desc: 'Legal balls bowled in all T20 since 2024.' },
    ...mixCols,
    { key: 'vr', label: 'Runs/m', group: 'Value', get: get('bowl.value.varp_runs'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Bowling value above replacement, runs per match: (replacement run value − his) per over × his projected overs in his current role.' },
    { key: 'v4', label: 'Per 4 ov', group: 'Value', get: get('bowl.value.varp_4ov'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Value per 4 overs: compares specialists regardless of workload.' },
    { key: 'vw', label: 'Win%/m', group: 'Value', get: get('bowl.value.varp_wp'), fmt: 'spct:1', heat: { center: 0 }, desc: 'Value in win probability per match.' },
    { key: 'eo', label: 'Proj ov', group: 'Value', get: get('bowl.value.exp_overs'), fmt: 'num:1', desc: 'Projected overs per match in his current role: his default team plan for squad players, else overs per match played since 2024.' },
    { key: 'rvo', label: 'RV/over', group: 'Value', get: get('bowl.all.rv_over'), fmt: 'num:2', heat: { center: a('all').rv_over ?? 7, reverse: true }, desc: 'Run value per over: runs conceded minus wickets × wicket value. Lower is better (blue = better).' },
    { key: 'vpct', label: 'Pctile', group: 'Value', get: get('bowl.pct.bowl_varp'), fmt: 'int', desc: 'Percentile of bowling value among pool bowlers (higher = better).' },
    { key: 'econ', label: 'Econ', group: 'True rates', get: get('bowl.all.econ'), fmt: 'num:2', heat: { center: a('all').econ ?? 9.4, reverse: true }, desc: 'True economy: runs per 6 legal balls incl. wides and no-balls, in his phase mix. Lower is better (blue). ' + IPLC },
    { key: 'esd', label: '± Econ', group: 'True rates', get: get('bowl.sd.econ'), fmt: 'num:2', desc: 'Posterior SD of the true economy.' },
    { key: 'wk', label: 'Wkt %', group: 'True rates', get: get('bowl.all.wkt_pct'), fmt: 'num:2', heat: { center: a('all').wkt_pct ?? 4.9 }, desc: 'Bowler wickets per 100 legal balls (run outs excluded). Higher is better.' },
    { key: 'bsr', label: 'SR', group: 'True rates', get: get('bowl.all.sr'), fmt: 'num:1', heat: { center: a('all').sr ?? 20.5, reverse: true }, desc: 'True bowling strike rate: balls per wicket. Lower is better.' },
    { key: 'bav', label: 'Avg', group: 'True rates', get: get('bowl.all.avg'), fmt: 'num:1', heat: { center: a('all').avg ?? 32, reverse: true }, desc: 'True bowling average: runs per wicket. Lower is better.' },
    { key: 'dec', label: 'Econ vs avg', group: 'True rates', get: get('bowl.vs_avg.all.econ'), fmt: 'signed:2', heat: { center: 0, reverse: true }, desc: 'Economy minus the average IPL bowler on the same deliveries. Negative = concedes less (good, blue).' },
    { key: 'dot', label: 'Dot %', group: 'True rates', get: get('bowl.all.dot_pct'), fmt: pct100, heat: { center: a('all').dot_pct ?? 34.5 }, desc: 'Dot balls per 100 legal balls. Higher is better.' },
    { key: 'bnd', label: 'Bnd %', group: 'True rates', get: get('bowl.all.bnd_pct'), fmt: pct100, heat: { center: a('all').bnd_pct ?? 21, reverse: true }, desc: 'Boundaries conceded per 100 balls. Lower is better.' },
    { key: 's6', label: '6 %', group: 'True rates', get: get('bowl.all.six_pct'), fmt: pct100, heat: { center: a('all').six_pct ?? 7.6, reverse: true }, desc: 'Sixes conceded per 100 balls. Lower is better.' },
    { key: 'wd', label: 'Wd/over', group: 'True rates', get: get('bowl.all.wides_per_over'), fmt: 'num:2', heat: { center: a('all').wides_per_over ?? 0.26, reverse: true }, desc: 'Wides per over. Lower is better.' },
    { key: 'nb', label: 'NB/over', group: 'True rates', get: get('bowl.all.nb_per_over'), fmt: 'num:3', hidden: true, desc: 'No-balls per over (when exported).' },
    { key: 'oec', label: 'Econ', group: 'vs expected', get: get('bowl.obs_2024.econ'), fmt: 'num:2', desc: 'Actual economy since 2024, all competitions (unshrunk).' },
    { key: 'oxec', label: 'xEcon', group: 'vs expected', get: get('bowl.obs_2024.xecon'), fmt: 'num:2', desc: 'What an average IPL bowler would have conceded on the same deliveries.' },
    { key: 'rs', label: 'Saved/4ov', group: 'vs expected', get: r => { const o = r.bowl && r.bowl.obs_2024; return o && o.balls ? o.runs_saved / o.balls * 24 : null; }, fmt: 'signed:1', heat: { center: 0 }, desc: 'Runs saved vs expected per 24 legal balls since 2024. + = conceded less than expected (good).' },
    { key: 'wx', label: 'Wkts vs x', group: 'vs expected', get: get('bowl.obs_2024.wkts_vs_x'), fmt: 'signed:1', heat: { center: 0 }, desc: 'Wickets minus expected since 2024. + = took more (good).' },
    { key: 'dx', label: 'Dot vs x', group: 'vs expected', get: r => { const o = r.bowl && r.bowl.obs_2024; return o && isNum(o.dot_pct) && isNum(o.xdot_pct) ? o.dot_pct - o.xdot_pct : null; }, fmt: 'signed:1', desc: 'Dot % minus expected dot % since 2024.' },
    { key: 'irs', label: 'IPL saved/4ov', group: 'vs expected', get: r => { const o = r.bowl && r.bowl.obs_ipl_2024; return o && o.balls ? o.runs_saved / o.balls * 24 : null; }, fmt: 'signed:1', heat: { center: 0 }, desc: 'Runs saved vs expected per 24 balls, IPL only since 2024.' },
    { key: 'wpa', label: 'WPA/m', group: 'vs expected', get: get('bowl.obs_2024.wpa_per_match'), fmt: 'spct:1', desc: 'Win probability added per match since 2024.' },
    ...I.PH.map(p => ({ key: 'ec_' + p, label: 'Econ ' + { pp: 'PP', mid: 'Mid', death: 'Death' }[p], group: 'Phases', get: get('bowl.' + p + '.econ'), fmt: 'num:2', heat: { center: a(p).econ ?? 9.4, reverse: true }, desc: `True economy in the ${I.PH_LABEL[p].toLowerCase()} (${I.PH_OVERS[p]}). Lower is better.` })),
    ...I.PH.map(p => ({ key: 'wk_' + p, label: 'Wkt ' + { pp: 'PP', mid: 'Mid', death: 'Death' }[p], group: 'Phases', get: get('bowl.' + p + '.wkt_pct'), fmt: 'num:2', heat: { center: a(p).wkt_pct ?? 4.9 }, desc: `Wickets per 100 balls in the ${I.PH_LABEL[p].toLowerCase()}. Higher is better.` })),
    { key: 'ec_r', label: 'Econ RHB', group: 'vs hand', get: get('bowl.rhb.econ'), fmt: 'num:2', heat: { center: a('rhb').econ ?? 9.4, reverse: true }, desc: 'True economy against right-handers.' },
    { key: 'ec_l', label: 'Econ LHB', group: 'vs hand', get: get('bowl.lhb.econ'), fmt: 'num:2', heat: { center: a('lhb').econ ?? 9.4, reverse: true }, desc: 'True economy against left-handers.' },
    { key: 'wk_r', label: 'Wkt RHB', group: 'vs hand', get: get('bowl.rhb.wkt_pct'), fmt: 'num:2', desc: 'Wickets per 100 balls against right-handers.' },
    { key: 'wk_l', label: 'Wkt LHB', group: 'vs hand', get: get('bowl.lhb.wkt_pct'), fmt: 'num:2', desc: 'Wickets per 100 balls against left-handers.' },
    { key: 'lgap', label: 'L − R', group: 'vs hand', get: r => r.bowl && r.bowl.vs_avg && isNum(r.bowl.vs_avg.lhb.econ) ? r.bowl.vs_avg.lhb.econ - r.bowl.vs_avg.rhb.econ : null, fmt: 'signed:2', heat: { center: 0, reverse: true }, desc: 'Economy vs average against left-handers minus against right-handers. Negative = relatively better against left-handers.' },
    ...I.PH.map((p, i) => ({ key: 'mx_' + p, label: { pp: 'PP', mid: 'Mid', death: 'Death' }[p] + ' %', group: 'Usage', get: r => r.bowl && r.bowl.phase_mix ? r.bowl.phase_mix[i] : null, fmt: 'pct:0', heat: { type: 'seq', domain: [0, 1] }, desc: `Share of his recency-weighted balls bowled in the ${I.PH_LABEL[p].toLowerCase()}.` })),
    projCol('po', 'Overs', p => p.overs_mean, 'Projected overs per match.', { fmt: v => I.oversF(v) }),
    projCol('pw', 'Wkts', p => p.wkts_mean, 'Projected wickets per match.', { fmt: 'num:2', heat: { type: 'seq' } }),
    projCol('pc', 'Conc', p => p.conceded_mean, 'Projected runs conceded per match.'),
    projCol('pe', 'Econ', p => p.overs_mean ? p.conceded_mean / p.overs_mean : null, 'Projected economy.', { fmt: 'num:2' }),
    projCol('p2', 'P(2+)', p => p.pWkts && p.pWkts['2'], 'Probability of 2 or more wickets.', { fmt: 'pct:0' }),
    actCol('am', 'M', l => l.m, 'Matches.'), actCol('aov', 'Overs/m', l => l.overs, 'Overs per match.'), actCol('aw', 'Wkts/m', l => l.wkts, 'Wickets per match.'), actCol('ae', 'Econ', l => l.econ, 'Economy.'),
    { key: 'dwk', label: 'Proj − act wk', group: 'IPL 2026', get: r => { const p = I.proj(r.id); return p && isNum(p.wkts_mean) && r._act && isNum(r._act.wkts) ? p.wkts_mean - r._act.wkts : null; }, fmt: 'signed:2', heat: { center: 0 }, desc: 'Projected minus actual IPL 2026 wickets per match.' },
    { key: 'ci', label: 'Inns', group: 'IPL career', get: get('bowl.ipl_career.inns'), fmt: 'int', desc: 'IPL career innings bowled.' },
    { key: 'cw', label: 'Wkts', group: 'IPL career', get: get('bowl.ipl_career.wkts'), fmt: 'int', desc: 'IPL career wickets.' },
    { key: 'ce', label: 'Econ', group: 'IPL career', get: get('bowl.ipl_career.econ'), fmt: 'num:2', desc: 'IPL career economy (raw).' },
  ];
}
const BOWL_GROUPS = ['Profile', 'Sample', 'Value', 'True rates', 'vs expected', 'Phases', 'vs hand', 'Usage', 'Projection', 'IPL 2026', 'IPL career'];

/* ───────── player card ───────── */
let navGrid = null;
I.playerCard = async (id, o = {}) => {
  await I.loadPlayers();
  const p = typeof id === 'object' ? id : I.player(id);
  if (!p) return;
  I.loadMatchups().catch(() => null);
  const t = p._team;
  const bowls = p.bowl && p.bowl.is_bowler !== false;
  const focus = o.focus === 'bowl' && !bowls ? 'bat' : o.focus || (bowls && (!p.bat || (p.bowl.value.varp_runs || -9) > (p.bat.value.varp_runs || -9)) ? 'bowl' : 'bat');
  const sdf = p.style_defaulted || {};
  const style = [p.bat_hand ? p.bat_hand + 'HB' : sdf.bat_hand ? (p.bat_hand_used || 'R') + 'HB (assumed)' : null, p.bowl_type && p.bowl_group !== 'none' ? p.bowl_type + (p.style_inferred ? ' (inferred)' : '') : sdf.bowl_type && bowls ? (p.bowl_group || '') + ' (type unknown)' : null].filter(Boolean).join(', ');
  S.drawer.open({
    title: p.name,
    sub: `${t ? t.name : 'Not in a 2026 IPL squad'} · ${I.ROLE_LABEL[p.role_bat] || ''}${style ? ' · ' + style : ''}${p.overseas ? ' · overseas' : ''}${p.country ? ' · ' + p.country : ''}${p._last ? ' · last ' + p._last : ''}`,
    keepScroll: true, nav: o.nav || (navGrid ? { prev: () => navGrid.step(-1), next: () => navGrid.step(1) } : null),
    body: async el => {
      el.append(S.tiles([
        { label: 'Value / match', value: F.signed(p.varp_runs, 1) + ' runs', sub: `${F.spct(p.varp_wp, 1)} win · #${p._rk_all || '–'} of ${D.nAll}` },
        p.bat ? { label: 'Batting', value: F.signed(p.bat.value.varp_runs, 1), sub: `runs/m · #${p._rk_bat || '–'} of ${D.nBat}` } : null,
        bowls ? { label: 'Bowling', value: F.signed(p.bowl.value.varp_runs, 1), sub: `runs/m · #${p._rk_bowl || '–'} of ${D.nBowl}` } : null,
      ].filter(Boolean)));
      actualVsProj(el, p, bowls);
      const secs = focus === 'bowl' ? [bowlSection, batSection] : [batSection, bowlSection];
      for (const f of secs) await f(el, p);
      el.append(h('div', { class: 'sh-h', text: 'Where his sample comes from' }), h('div', { class: 'sh-note', text: 'Share of his recency-weighted deliveries by league tier. Non-IPL form is put on the IPL scale by the league terms (see Leagues).' }));
      const lm = p.league_mix || {};
      S.bar(el.appendChild(h('div')), { data: Object.keys(I.TIER_LABEL).filter(k => lm[k] > 0.0005).map(k => ({ label: I.TIER_LABEL[k], value: lm[k] })), sort: 'desc', fmt: 'pct:0', diverging: false, domain: [0, 1], barHeight: 10, rowGap: 5 });
      if ((p.ipl_teams || []).length) el.append(S.kv([['IPL franchises', p.ipl_teams.map(x => `${I.short(x.team)} ${x.from}${x.to !== x.from ? '–' + x.to : ''}`).join(', ')]]));
      const links = h('div', { class: 'sh-note ip-links' });
      if (t) {
        links.append(h('a', { href: I.hashFor('teams', { t: t.short }), text: 'Team sheet' }));
        if ((t.xii || []).includes(p.id)) {
          const opp = D.teams.find(x => x !== t && Math.abs(x.rating.win_pct_neutral - 0.5) === Math.min(...D.teams.filter(y => y !== t).map(y => Math.abs(y.rating.win_pct_neutral - 0.5))));
          links.append(' · ', h('a', { href: I.hashFor('sim', simOutHash(t, opp, p.id)), text: `Simulate ${t.short} v ${opp.short} without him` }));
        }
      } else links.append(h('a', { href: I.hashFor('sim', simInHash(p)), text: 'Try him in an XI in the simulator' }));
      el.append(links);
    },
  });
};
function simOutHash(t, opp, pid) {
  // replace him with the best unused squad player of the same kind; overs inherit
  const best = bestReplacement(t, pid);
  const order = t.order.slice(), ip = t.impact_player; let plan = t.plan.map(x => Object.assign({}, x));
  const o = { a: t.short, b: opp.short };
  if (!best) return o;
  if (pid === ip) o.ai = best; else { order[order.indexOf(pid)] = best; o.ao = order.join(','); }
  plan = plan.map(x => x.id === pid ? Object.assign(x, { id: best }) : x);
  if (plan.some(x => x.id === best)) o.ap = planStr(plan);
  return o;
}
function bestReplacement(t, pid) {
  const p = I.player(pid), bowlsMore = p && p.bowl && (!p.bat || (p.bowl.value.varp_runs || 0) > (p.bat.value.varp_runs || 0));
  const pool = (t.squad || []).filter(s => !t.xii.includes(s.id) && s.in_pool).map(s => I.player(s.id)).filter(Boolean);
  const score = q => bowlsMore ? (q.bowl ? q.bowl.value.varp_runs : -99) : (q.bat ? q.bat.value.varp_runs : -99);
  const cand = pool.filter(q => p && q.overseas === p.overseas || !q.overseas).sort((x, y) => score(y) - score(x));
  return cand[0] ? cand[0].id : null;
}
function simInHash(p) {
  const t = D.teams.slice().sort((a, b) => a.rating.win_pct_neutral - b.rating.win_pct_neutral)[0], opp = D.teams.slice().sort((a, b) => b.rating.win_pct_neutral - a.rating.win_pct_neutral)[0];
  const order = t.order.slice(), plan = t.plan.map(x => Object.assign({}, x));
  // swap out his weakest same-kind XI member
  const bowler = p.bowl && (!p.bat || (p.bowl.value.varp_runs || 0) > (p.bat.value.varp_runs || 0));
  const val = id => { const q = I.player(id); return !q ? -99 : bowler ? (q.bowl ? q.bowl.value.varp_runs : -99) : (q.bat ? q.bat.value.varp_runs : -99); };
  const outs = (bowler ? plan.map(x => x.id) : order.slice(0, 7)).filter(id => id !== t.impact_player).sort((x, y) => val(x) - val(y));
  const out = outs[0]; const o = { a: t.short, b: opp.short };
  order[order.indexOf(out)] = p.id; o.ao = order.join(',');
  if (plan.some(x => x.id === out)) o.ap = planStr(plan.map(x => x.id === out ? Object.assign(x, { id: p.id }) : x));
  return o;
}
function actualVsProj(el, p, bowls) {
  const pr = I.proj(p.id), ac = p._act;
  if (!pr && !ac) return;
  const rows = [];
  const add = (k, a, b, dp = 1) => { if (isNum(a) || isNum(b)) rows.push({ k, a, b, dp }); };
  if (p.bat) { add('Runs', ac && ac.runs, pr && pr.runs_mean); add('Balls faced', ac && ac.balls, pr && pr.balls_mean); add('Strike rate', ac && ac.sr, pr && isNum(pr.runs_mean) && pr.balls_mean ? pr.runs_mean / pr.balls_mean * 100 : null); add('P(30+)', null, pr && pr.pRuns && pr.pRuns['30'], 3); }
  if (bowls) { add('Overs', ac && ac.overs, pr && pr.overs_mean); add('Wickets', ac && ac.wkts, pr && pr.wkts_mean, 2); add('Runs conceded', ac && ac.conc, pr && pr.conceded_mean); add('Economy', ac && ac.econ, pr && (pr.econ ?? (pr.overs_mean ? pr.conceded_mean / pr.overs_mean : null)), 2); }
  if (!rows.length) return;
  el.append(h('div', { class: 'sh-h', text: `Per match: IPL ${ac && ac.season || 2026} actual vs projected` }), h('div', { class: 'sh-note', text: `${ac ? `Actual: ${ac.m || 0} matches${isNum(ac.bat_inns) ? `, ${ac.bat_inns} batting innings` : ''}${isNum(ac.bowl_inns) ? `, ${ac.bowl_inns} bowling` : ''}.` : 'Did not play in the latest IPL season.'} ${pr ? `Projected: his default role (bats ${pr.pos ?? '–'}), mean over ${pr.n || 18} matchups, including matches where he does not bat.` : 'No projection: not in a default 12.'}` }));
  S.table(el.appendChild(h('div')), [{ key: 'k', label: '' }, { key: 'a', label: 'Actual', render: (v, r) => isNum(v) ? (r.dp === 3 ? F.pct(v, 0) : F.num(v, r.dp)) : '–' }, { key: 'b', label: 'Projected', render: (v, r) => isNum(v) ? (r.dp === 3 ? F.pct(v, 0) : F.num(v, r.dp)) : '–' }, { key: 'd', label: 'Proj − act', render: (v, r) => isNum(r.a) && isNum(r.b) && r.dp !== 3 ? F.signed(r.b - r.a, r.dp) : '' }], rows);
}
async function batSection(el, p) {
  const b = p.bat; if (!b) return;
  const va = b.vs_avg || {}, sd = b.sd || {};
  el.append(h('div', { class: 'sh-h ip-sech', text: 'Batting' }), h('div', { class: 'sh-note', text: IPLC + ' Value uses slot ' + (b.value.slot || '–') + ` (${F.num(b.value.exp_balls, 1)} balls per innings).` }));
  el.append(S.tiles([
    { label: 'True SR', value: F.num(b.all.sr, 1), sub: `±${F.num(sd.sr, 1)} · ${F.signed(va.all && va.all.sr, 1)} v avg` },
    { label: 'True avg', value: F.num(b.all.avg, 1), sub: `± ${F.num(sd.avg, 1)}` },
    { label: 'Outs / 100', value: F.num(b.all.out_pct, 2), sub: `±${F.num(sd.out_pct, 2)} · low = good` },
    { label: 'Run value', value: F.num(b.all.rv100, 1), sub: `/100 · ${F.signed(va.all && va.all.rv100, 1)} v avg` },
    { label: 'Boundary %', value: F.num(b.all.bnd_pct, 1), sub: `4s ${F.num(b.all.four_pct, 1)} · 6s ${F.num(b.all.six_pct, 1)}` },
    { label: 'Dot %', value: F.num(b.all.dot_pct, 1), sub: `NB SR ${F.num(b.all.nbsr, 0)}` },
  ]));
  const strata = [['all', 'All'], ['pp', 'Powerplay'], ['mid', 'Middle'], ['death', 'Death'], ['pace', 'vs pace'], ['spin', 'vs spin']];
  const av = (s, k) => b[s] && va[s] && isNum(b[s][k]) && isNum(va[s][k]) ? b[s][k] - va[s][k] : null;
  I.vsAvg(el.appendChild(h('div', { class: 'sh-section' })), {
    title: 'By phase and bowling type, vs the average IPL batter', who: p.name,
    panels: [
      { title: 'Strike rate', fmt: 'num:0', better: 'high', rows: strata.map(([s, l]) => ({ label: l, v: b[s] && b[s].sr, avg: av(s, 'sr'), sd: s === 'all' ? sd.sr : null })) },
      { title: 'Dismissals / 100 balls', fmt: 'num:1', better: 'low', rows: strata.map(([s, l]) => ({ label: l, v: b[s] && b[s].out_pct, avg: av(s, 'out_pct'), sd: s === 'all' ? sd.out_pct : null })) },
      { title: 'Boundary %', fmt: 'num:1', better: 'high', rows: strata.map(([s, l]) => ({ label: l, v: b[s] && b[s].bnd_pct, avg: av(s, 'bnd_pct') })) },
    ],
    legend: 'Bar: his true rate (blue = better than average, red = worse; for dismissals lower is better). Black tick: the average IPL batter on the same deliveries. Whisker: ±1 posterior SD.',
  });
  if (Array.isArray(b.settling) && b.settling.length) {
    const lab = D.settlingBuckets.length ? D.settlingBuckets : b.settling.map((_, i) => String(i));
    const g = h('div', { class: 'ip-two ip-two-wide' }); el.append(g);
    const l1 = h('div'), l2 = h('div'); g.append(l1, l2);
    const xf = v => lab[Math.round(v)] ?? '';
    S.line(l1, { title: 'Settling: strike rate by balls faced', series: [{ name: p.name.split(' ').slice(-1)[0], points: b.settling.map((x, i) => [i, x[0]]) }, { name: 'Average', points: D.settlingAvg.map((x, i) => [i, x[1] != null ? x[0] : null]) }], xFmt: xf, xLabel: 'balls faced before the ball', yFmt: 'num:0', height: 150, zero: false });
    S.line(l2, { title: 'Dismissal risk by balls faced', series: [{ name: p.name.split(' ').slice(-1)[0], points: b.settling.map((x, i) => [i, x[1]]) }, { name: 'Average', points: D.settlingAvg.map((x, i) => [i, x[1]]) }], xFmt: xf, xLabel: 'balls faced before the ball', yFmt: 'num:1', height: 150, zero: false });
    el.append(h('div', { class: 'sh-note', text: `Middle-overs context. Runs per 100 balls and dismissals per 100 balls on the next ball, by how many he has already faced (buckets ${lab.join(', ')}).` }));
  }
  const bt = b.by_type || {};
  const tys = TYPES.filter(([k]) => bt[k] && isNum(bt[k].sr));
  if (tys.length) {
    const av = (k, m) => bt[k].vs_avg && isNum(bt[k].vs_avg[m]) ? bt[k][m] - bt[k].vs_avg[m] : null;
    I.vsAvg(el.appendChild(h('div', { class: 'sh-section' })), {
      title: 'Against each bowling type', who: p.name,
      panels: [
        { title: 'Strike rate', fmt: 'num:0', better: 'high', rows: tys.map(([k, l, d]) => ({ label: l, v: bt[k].sr, avg: av(k, 'sr'), desc: d })) },
        { title: 'Dismissals / 100 balls', fmt: 'num:1', better: 'low', rows: tys.map(([k, l, d]) => ({ label: l, v: bt[k].out_pct, avg: av(k, 'out_pct'), desc: d })) },
      ],
      legend: `Deliveries from that type only, in IPL 2024–26 conditions; splits are shrunk hard toward his overall rating. Types with under 200 reference deliveries are left out${TYPES.length > tys.length ? ' (' + TYPES.filter(t => !tys.includes(t)).map(t => t[1]).join(', ') + ')' : ''}.`,
    });
  }
  await I.loadMatchups().catch(() => null); const pr = I.proj(p.id);
  if (pr && isNum(pr.runs_mean)) {
    el.append(h('div', { class: 'sh-h', text: 'A typical innings' }), h('div', { class: 'sh-note', text: `Mean over ${p._team ? p._team.short : 'his team'}'s ${pr.n} precomputed matchups (bats ${pr.pos}, default XI, 10,000 sims each). Includes the chance he does not bat.` }));
    el.append(S.tiles([{ label: 'Runs', value: F.num(pr.runs_mean, 1), sub: `${F.num(pr.balls_mean, 1)} balls` }, { label: 'Fours / sixes', value: `${F.num(pr.fours_mean, 1)} / ${F.num(pr.sixes_mean, 1)}` }, { label: 'P(bats)', value: F.pct(pr.p_bat, 0) }, { label: 'Top scorer', value: F.pct(pr.p_top_bat, 1), sub: 'for his side' }]));
    const thr = Object.keys(pr.pRuns).map(Number).sort((x, y) => x - y);
    S.bar(el.appendChild(h('div')), { title: 'P(runs ≥ t) in an innings', data: thr.map(t => ({ label: t + '+', value: pr.pRuns[t], desc: 'fair ' + I.fp(pr.pRuns[t]) })), fmt: 'pct:0', diverging: false, domain: [0, 1], barHeight: 10, rowGap: 5 });
  } else if (pr === null && p._team) el.append(h('div', { class: 'sh-note', text: 'Not in his team\'s default XI, so no precomputed innings projection. Add him in the simulator.' }));
  // observed vs expected
  const ob = [['Since 2024, all T20', b.obs_2024], ['IPL since 2024', b.obs_ipl_2024]].filter(x => x[1]);
  if (ob.length) {
    el.append(h('div', { class: 'sh-h', text: 'What actually happened vs expected' }), h('div', { class: 'sh-note', text: 'Unshrunk: his real output against what an average IPL batter would have done on the same deliveries. The true rates above shrink this toward his prior.' }));
    S.table(el.appendChild(h('div')), [{ key: 'k', label: '' }, { key: 'balls', label: 'Balls', fmt: 'int' }, { key: 'runs', label: 'Runs', fmt: 'int' }, { key: 'sr', label: 'SR', fmt: 'num:1' }, { key: 'xsr', label: 'xSR', fmt: 'num:1' }, { key: 'rae100', label: 'RAE/100', fmt: 'signed:1' }, { key: 'outs', label: 'Outs', fmt: 'int' }, { key: 'outs_vs_x', label: 'vs x', fmt: 'signed:1', desc: 'dismissals minus expected (negative good)' }, { key: 'avg', label: 'Avg', fmt: 'num:1' }, { key: 'xavg', label: 'xAvg', fmt: 'num:1' }, { key: 'f', label: '4s / x', get: r => `${F.int(r.fours)} / ${F.int(r.x4)}` }, { key: 's', label: '6s / x', get: r => `${F.int(r.sixes)} / ${F.int(r.x6)}` }],
      ob.map(([k, o]) => Object.assign({ k }, o)));
  }
  if (b.pct) {
    const pk = [['bat_varp', 'Batting value'], ['all_rv100', 'Run value'], ['all_sr', 'Strike rate'], ['all_avg', 'Average'], ['pp_sr', 'Powerplay SR'], ['death_sr', 'Death SR'], ['pace_sr', 'SR vs pace'], ['spin_sr', 'SR vs spin']];
    S.bar(el.appendChild(h('div', { class: 'sh-section' })), { title: 'Where he ranks (batting)', subtitle: 'Percentile among pool batters with ≥100 IPL balls or ≥300 balls anywhere since 2024.', data: pk.filter(([k]) => isNum(b.pct[k])).map(([k, l]) => ({ label: l, value: b.pct[k] })), fmt: 'int', domain: [0, 100], diverging: false, barHeight: 10, rowGap: 5 });
  }
  const c = b.ipl_career; if (c) el.append(S.kv([['IPL career', `${F.int(c.inns)} inns, ${F.int(c.runs)} runs off ${F.int(c.balls)} balls, SR ${F.num(c.sr, 1)}, avg ${c.outs ? F.num(c.runs / c.outs, 1) : '–'}`]]));
}
async function bowlSection(el, p) {
  const w = p.bowl; if (!w) return;
  if (w.is_bowler === false) { el.append(h('div', { class: 'sh-h ip-sech', text: 'Bowling' }), h('div', { class: 'sh-note', text: `Does not bowl in his current role, so he has no bowling value or rank (model rates exist from ${F.int(w.ipl_career ? w.ipl_career.balls : 0)} IPL balls; true economy ${F.num(w.all.econ, 2)}).` })); return; }
  const va = w.vs_avg || {}, sd = w.sd || {}, v = w.value || {};
  el.append(h('div', { class: 'sh-h ip-sech', text: 'Bowling' }), h('div', { class: 'sh-note', text: IPLC + ` Value at his projected ${F.num(v.exp_overs, 1)} overs per match in his current role; per 4 overs ${F.signed(v.varp_4ov, 1)} runs.${w.in_plan === false && p._team ? ` Not in ${p._team.short}'s default bowling plan, so he bowls no overs in the precomputed matches (add him in the Simulator).` : ''}` }));
  el.append(S.tiles([
    { label: 'True econ', value: F.num(w.all.econ, 2), sub: `±${F.num(sd.econ, 2)} · ${F.signed(va.all && va.all.econ, 2)} v avg` },
    { label: 'Wkts / 100', value: F.num(w.all.wkt_pct, 2), sub: `±${F.num(sd.wkt_pct, 2)} · SR ${F.num(w.all.sr, 1)}` },
    { label: 'Average', value: F.num(w.all.avg, 1), sub: 'runs per wicket' },
    { label: 'RV / over', value: F.num(w.all.rv_over, 2), sub: `low = good · repl ${F.num(v.rep_rv_over, 2)}` },
    { label: 'Dot %', value: F.num(w.all.dot_pct, 1), sub: `bdy ${F.num(w.all.bnd_pct, 1)} · 6s ${F.num(w.all.six_pct, 1)}` },
    { label: 'Wides / over', value: F.num(w.all.wides_per_over, 2), sub: isNum(w.all.nb_per_over) ? `no-balls ${F.num(w.all.nb_per_over, 3)}` : '' },
  ]));
  const strata = [['all', 'All'], ['pp', 'Powerplay'], ['mid', 'Middle'], ['death', 'Death'], ['rhb', 'vs RHB'], ['lhb', 'vs LHB']];
  const av = (s, k) => w[s] && va[s] && isNum(w[s][k]) && isNum(va[s][k]) ? w[s][k] - va[s][k] : null;
  I.vsAvg(el.appendChild(h('div', { class: 'sh-section' })), {
    title: 'By phase and batter hand, vs the average IPL bowler', who: p.name,
    panels: [
      { title: 'Economy (runs / over)', fmt: 'num:1', better: 'low', zero: false, rows: strata.map(([s, l]) => ({ label: l, v: w[s] && w[s].econ, avg: av(s, 'econ'), sd: s === 'all' ? sd.econ : null })) },
      { title: 'Wickets / 100 balls', fmt: 'num:1', better: 'high', rows: strata.map(([s, l]) => ({ label: l, v: w[s] && w[s].wkt_pct, avg: av(s, 'wkt_pct'), sd: s === 'all' ? sd.wkt_pct : null })) },
      { title: 'Dot %', fmt: 'num:0', better: 'high', rows: strata.map(([s, l]) => ({ label: l, v: w[s] && w[s].dot_pct, avg: av(s, 'dot_pct') })) },
    ],
    legend: 'Bar: his true rate (blue = better than average: lower economy, more wickets, more dots). Black tick: the average IPL bowler on the same deliveries. Whisker: ±1 posterior SD.',
  });
  const t = p._team, pl = t && (t.plan || []).find(x => x.id === p.id);
  if (Array.isArray(w.phase_mix)) {
    S.bar(el.appendChild(h('div')), { title: 'Where he bowls', subtitle: 'Share of his recency-weighted balls by phase' + (pl ? `; ${t.short}'s default plan gives him ${pl.pp}/${pl.mid}/${pl.death} overs (PP/Mid/Death).` : '.'), data: I.PH.map((k, i) => ({ label: I.PH_LABEL[k], value: w.phase_mix[i], desc: I.PH_OVERS[k] })), fmt: 'pct:0', diverging: false, domain: [0, 1], barHeight: 12, rowGap: 6 });
  }
  await I.loadMatchups().catch(() => null); const pr = I.proj(p.id);
  if (pr && isNum(pr.overs_mean)) {
    el.append(h('div', { class: 'sh-h', text: 'A typical match' }), h('div', { class: 'sh-note', text: `Mean over ${t ? t.short : 'his team'}'s ${pr.n} precomputed matchups (default plan).` }));
    el.append(S.tiles([{ label: 'Overs', value: I.oversF(pr.overs_mean) }, { label: 'Wickets', value: F.num(pr.wkts_mean, 2), sub: `P(2+) ${F.pct(pr.pWkts['2'], 0)}` }, { label: 'Conceded', value: F.num(pr.conceded_mean, 1), sub: `econ ${F.num(pr.conceded_mean / pr.overs_mean, 2)}` }, { label: 'Top wicket-taker', value: F.pct(pr.p_top_bowl, 1), sub: 'for his side' }]));
  }
  const ob = [['Since 2024, all T20', w.obs_2024], ['IPL since 2024', w.obs_ipl_2024]].filter(x => x[1]);
  if (ob.length) {
    el.append(h('div', { class: 'sh-h', text: 'What actually happened vs expected' }), h('div', { class: 'sh-note', text: 'Unshrunk: his real figures against an average IPL bowler on the same deliveries. Runs saved + = conceded less than expected.' }));
    S.table(el.appendChild(h('div')), [{ key: 'k', label: '' }, { key: 'balls', label: 'Balls', fmt: 'int' }, { key: 'ov', label: 'Overs', get: r => I.overs(r.balls) }, { key: 'conc', label: 'Runs', fmt: 'int' }, { key: 'econ', label: 'Econ', fmt: 'num:2' }, { key: 'xecon', label: 'xEcon', fmt: 'num:2' }, { key: 'runs_saved', label: 'Saved', fmt: 'signed:0' }, { key: 'wkts', label: 'Wkts', fmt: 'int' }, { key: 'wkts_vs_x', label: 'vs x', fmt: 'signed:1' }, { key: 'dot_pct', label: 'Dot %', fmt: 'num:1' }, { key: 'xdot_pct', label: 'xDot %', fmt: 'num:1' }],
      ob.map(([k, o]) => Object.assign({ k }, o)));
  }
  if (w.pct) {
    const pk = [['bowl_varp', 'Bowling value'], ['all_rv_over', 'Run value'], ['all_econ', 'Economy'], ['all_wkt_pct', 'Wicket rate'], ['pp_econ', 'Powerplay econ'], ['death_econ', 'Death econ']];
    S.bar(el.appendChild(h('div', { class: 'sh-section' })), { title: 'Where he ranks (bowling)', subtitle: 'Percentile among pool bowlers; higher = better (low economy ranks high).', data: pk.filter(([k]) => isNum(w.pct[k])).map(([k, l]) => ({ label: l, value: w.pct[k] })), fmt: 'int', domain: [0, 100], diverging: false, barHeight: 10, rowGap: 5 });
  }
  const c = w.ipl_career; if (c) el.append(S.kv([['IPL career', `${F.int(c.inns)} inns, ${I.overs(c.balls)} overs, ${F.int(c.wkts)} wkts, econ ${F.num(c.econ, 2)}`]]));
}

/* ───────── Overview ───────── */
async function overview(panel) {
  await I.loadTeams();
  const intro = I.card(panel, null, null, 'ip-intro');
  intro.append(h('div', { class: 'sh-md', html: S.md(
    '**What this is.** Every batter and bowler gets "true" rates (strike rate, average, economy, wicket rate, boundary and dot rates, by phase and against pace/spin or left/right-handers) from one ball-by-ball model fitted jointly on every men\'s 20-over T20 match on cricsheet, with leagues, venues and seasons netted out. ' +
    'A ball-by-ball simulator then plays each match thousands of times from the two XIs, batting orders and bowling plans, so the winner, totals, powerplay, sixes and every player line come from the same simulated matches. ' +
    'Nothing here was fitted to or tested against betting prices: fair odds are the model\'s no-vig prices, not a claim of an edge.\n\n' +
    '**How to read it.** Strike rate is runs per 100 balls, economy runs per over, overs are written O.B. Phases: Powerplay (overs 1–6), Middle (7–15), Death (16–20). Rates are shown "in IPL 2024–26 conditions". ' +
    'In grids, blue means better and red worse, so for bowlers a lower economy shades blue. Value is runs per match above a replacement-level player. Hover any header or chart for definitions; odds switch between American and decimal in the header. ' +
    'Click a player for his card, a matchup cell for the match, and use **Simulator** to change XIs, batting orders and bowling plans.') }));
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  const c1 = I.card(cols, 'Team strength', 'Bottom-up from each default XI (+ Impact Player). Win% = mean P(win) against the other nine at a neutral ground; runs for/against are mean simulated totals over the 18 home/away matchups. Value = sum of the XI\'s batting and bowling value above replacement, runs per match. Click a team.');
  const tb = h('div'); c1.append(tb);
  const trows = D.teams.slice().sort((a, b) => b.rating.win_pct_neutral - a.rating.win_pct_neutral);
  S.table(tb, [
    { key: 'rk', label: '#', get: r => r.rating.rank, fmt: 'int' }, { key: 'short', label: 'Team', render: (v, r) => `<a href="${I.hashFor('teams', { t: v })}" title="${esc(r.name)}">${esc(v)}</a>` },
    { key: 'wn', label: 'Win%', get: r => r.rating.win_pct_neutral, fmt: 'pct:1', desc: 'Mean P(win) vs the other 9, neutral ground.' },
    { key: 'wh', label: 'H/A', get: r => r.rating.win_pct_home_away, fmt: 'pct:1', desc: 'Mean P(win) over the 18 home/away matchups.' },
    { key: 'rf', label: 'Runs for', get: r => r.rating.runs_for, fmt: 'num:1', desc: 'Mean simulated total scored.' }, { key: 'ra', label: 'Against', get: r => r.rating.runs_against, fmt: 'num:1', desc: 'Mean simulated total conceded.' },
    { key: 'nr', label: 'Net', get: r => r.rating.net_runs, fmt: 'signed:1' },
    { key: 'bv', label: 'Bat value', get: r => r.rating.xi_bat_varp, fmt: 'num:1', desc: 'Sum of the XI\'s batting value above replacement, runs per match.' },
    { key: 'wv', label: 'Bowl value', get: r => r.rating.xi_bowl_varp, fmt: 'num:1', desc: 'Sum over the bowling plan: each bowler\'s value per 4 overs × planned overs / 4.' },
  ], trows);
  I.clickRows(tb, trows, t => I.go('teams', { t: t.short }));
  const c2 = I.card(cols, 'Batting vs bowling strength', 'XI batting value (right = stronger batting) against bowling value (up = stronger attack), runs per match above replacement. Click a team.');
  S.scatter(c2.appendChild(h('div')), { points: D.teams.map(t => ({ x: t.rating.xi_bat_varp, y: t.rating.xi_bowl_varp, label: t.short, id: t.short, desc: `${t.name}: neutral win ${F.pct(t.rating.win_pct_neutral, 1)}` })), labels: D.teams.map(t => t.short), xLabel: 'batting value, runs / match', yLabel: 'bowling value, runs / match', xFmt: 'num:0', yFmt: 'num:0', height: 220, onClick: pt => I.go('teams', { t: pt.id }) });
  S.bar(c2.appendChild(h('div', { style: { marginTop: '10px' } })), { title: 'Neutral-ground win % vs the field', data: trows.map(t => ({ label: t.short, value: t.rating.win_pct_neutral, id: t.short, desc: t.name })), fmt: 'pct:1', center: 0.5, barHeight: 10, rowGap: 5, onClick: d => I.go('teams', { t: d.id }) });
  const cols2 = h('div', { class: 'sh-cols' }); panel.append(cols2);
  const c3 = I.card(cols2, 'Most valuable batters', 'Batting value above replacement, runs per match, players in a 2026 squad. Click a bar for the card.');
  const c4 = I.card(cols2, 'Most valuable bowlers', 'Bowling value above replacement, runs per match at his projected overs, players in a 2026 squad.');
  const b3 = h('div'), b4 = h('div'); c3.append(b3); c4.append(b4);
  b3.append(S.loadingEl('Loading players…')); b4.append(S.loadingEl('Loading players…'));
  const meta = await I.loadMeta().catch(() => null);
  if (meta) {
    const c5 = I.card(cols2, 'Build', 'What went into this export.');
    const dg = await S.load.optional('data/diagnostics.json').catch(() => null), ms = dg && dg.match_shock;
    const ishock = ms && isNum(ms.innings_sd) ? 'SD ' + F.num(ms.innings_sd, 3) + ' (logit, drawn separately for each innings)' : '–';
    const sp = meta.sim || {}, par = sp.parity || {};
    c5.append(S.kv([['Data cut-off', meta.data_cutoff], ['Last IPL match', meta.ipl_last_match], ['Built', String(meta.build_utc || '').replace('T', ' ').replace('Z', ' UTC')], ['Matches / deliveries', `${F.int(meta.counts && meta.counts.matches)} / ${F.int(meta.counts && meta.counts.deliveries)}`], ['Deliveries in the fit', F.int(meta.counts && meta.counts.deliveries_modelled)], ['Reduced / DLS excluded', F.int(meta.counts && meta.counts.matches_reduced_or_dls_excluded)], ['Recency half-life', isNum(meta.model && meta.model.half_life_years) ? meta.model.half_life_years + ' years' : '–'], ['Coefficients', F.int(meta.model && meta.model.n_coefficients)], ['JS sim speed', isNum(sp.js_node_sec_per_10k) ? F.num(sp.js_node_sec_per_10k, 2) + ' s per 10,000 matches' : '–'], ['JS vs Python parity', par.comparisons ? `${par.pass ? 'pass' : 'FAIL'}: ${par.comparisons} checks, mean |z| ${F.num(par.mean_abs_z, 2)}, max ${F.num(par.max_abs_z, 2)}` : '–'], ['1 run of expected margin', isNum(sp.runs_to_win_prob) ? F.pct(sp.runs_to_win_prob, 2) + ' win probability' + (sp.runs_to_win_prob_detail && sp.runs_to_win_prob_detail.pairs ? ` (simulated, ${sp.runs_to_win_prob_detail.pairs.length} matchups)` : '') : '–'], ['Match-conditions shock', isNum(sp.match_shock) ? 'SD ' + F.num(sp.match_shock, 3) + ' (logit, shared by both innings)' : '–'], ['Innings-level shock', ishock], ['Sims per precomputed match', D.M ? F.int(D.M.n_sims) : '20,000']]));
  }
  I.loadPlayers().then(() => {
    const top = (f, n) => D.players.filter(p => p._team && isNum(f(p))).sort((a, b) => f(b) - f(a)).slice(0, n);
    const fb = p => p.bat && p.bat.value.varp_runs, fw = p => p.bowl && p.bowl.value.varp_runs;
    b3.innerHTML = ''; b4.innerHTML = '';
    S.bar(b3, { data: top(fb, 15).map(p => ({ label: `${p.name} (${p._team.short})`, value: fb(p), id: p.id, desc: `SR ${F.num(p.bat.all.sr, 1)}, avg ${F.num(p.bat.all.avg, 1)}, slot ${p.bat.value.slot}` })), fmt: 'signed:1', diverging: false, barHeight: 10, rowGap: 5, onClick: d => I.playerCard(d.id, { focus: 'bat', nav: { prev() {}, next() {} } }) });
    S.bar(b4, { data: top(fw, 15).map(p => ({ label: `${p.name} (${p._team.short})`, value: fw(p), id: p.id, desc: `econ ${F.num(p.bowl.all.econ, 2)}, wkt% ${F.num(p.bowl.all.wkt_pct, 2)}, ${F.num(p.bowl.value.exp_overs, 1)} ov` })), fmt: 'signed:1', diverging: false, barHeight: 10, rowGap: 5, onClick: d => I.playerCard(d.id, { focus: 'bowl', nav: { prev() {}, next() {} } }) });
  }).catch(e => { b3.innerHTML = ''; b3.append(S.errorEl(e)); b4.innerHTML = ''; });
}

/* ───────── Batters / Bowlers ───────── */
function squadFilterTool(grid, sheet, key) {
  const t = S.ui.toggle({ label: 'IPL squads only', value: sheet.get(key) !== '0', onChange: v => { sheet.set({ [key]: v ? null : '0' }); apply(); } });
  const apply = () => grid && grid.setRows(rowsFor());
  let rowsFor = () => [];
  return { el: t, bind(g, f) { grid = g; rowsFor = f; } };
}
async function batters(panel, sheet) {
  await I.loadPlayers();
  const all = D.players.filter(p => p.bat);
  const tool = squadFilterTool(null, sheet, 'all');
  const status = h('span', { class: 'sh-note ip-status' });
  const rowsFor = () => sheet.get('all') === '0' ? all : all.filter(p => p._team);
  const g = sheet.grid(panel, { columns: batCols(), groups: BAT_GROUPS.map(x => ({ id: x, label: x, hidden: ['Sample', 'IPL career', 'Settling', 'vs bowl type'].includes(x) || (x === 'IPL 2026' && !all.some(p => p._act)) })), rows: rowsFor(), sort: '-vr', label: 'Batters', csv: 'ipl-batters.csv', searchPlaceholder: 'Search batter, team, role', tools: h('span', { class: 'ip-tools' }, tool.el, status),
    onRowClick: r => { navGrid = g; I.playerCard(r, { focus: 'bat', nav: { prev: () => g.step(-1), next: () => g.step(1) } }); } });
  tool.bind(g, rowsFor);
  if (!D.proj) { status.textContent = 'Loading projections…'; I.loadMatchups().then(() => { g.refresh(); status.textContent = ''; }).catch(e => { status.textContent = 'Projections unavailable: ' + e.message; }); }
}
async function bowlers(panel, sheet) {
  await I.loadPlayers();
  const all = D.players.filter(p => p.bowl && p.bowl.is_bowler !== false);
  const tool = squadFilterTool(null, sheet, 'all');
  const status = h('span', { class: 'sh-note ip-status' });
  const rowsFor = () => sheet.get('all') === '0' ? all : all.filter(p => p._team);
  const g = sheet.grid(panel, { columns: bowlCols(), groups: BOWL_GROUPS.map(x => ({ id: x, label: x, hidden: ['Sample', 'IPL career', 'vs hand'].includes(x) })), rows: rowsFor(), sort: '-vr', label: 'Bowlers', csv: 'ipl-bowlers.csv', searchPlaceholder: 'Search bowler, team, type', tools: h('span', { class: 'ip-tools' }, tool.el, status),
    onRowClick: r => { navGrid = g; I.playerCard(r, { focus: 'bowl', nav: { prev: () => g.step(-1), next: () => g.step(1) } }); } });
  tool.bind(g, rowsFor);
  if (!D.proj) { status.textContent = 'Loading projections…'; I.loadMatchups().then(() => { g.refresh(); status.textContent = ''; }).catch(e => { status.textContent = 'Projections unavailable: ' + e.message; }); }
}

/* ───────── Teams ───────── */
function phaseStrength(t) {
  const A = D.avgBat, B = D.avgBowl, sb = D.slotBalls || [];
  const out = [];
  I.PH.forEach(ph => {
    let s = 0, w = 0, so = 0;
    t.order.forEach((id, i) => { const p = I.player(id); const ww = sb[i] || 0; if (p && p.bat && isNum(p.bat[ph].sr)) { s += ww * (p.bat[ph].sr - A[ph].sr); so += ww * (p.bat[ph].out_pct - A[ph].out_pct); w += ww; } });
    let e = 0, o = 0, wk = 0;
    t.plan.forEach(x => { const p = I.player(x.id), ov = x[ph] || 0; if (p && p.bowl && ov) { e += ov * (p.bowl[ph].econ - B[ph].econ); wk += ov * (p.bowl[ph].wkt_pct - B[ph].wkt_pct); o += ov; } });
    out.push({ ph, bat: w ? s / w * 6 / 100 : null, batOut: w ? so / w : null, bowl: o ? -e / o : null, bowlWk: o ? wk / o : null });
  });
  return out;
}
async function teams(panel, sheet) {
  await Promise.all([I.loadPlayers(), I.loadVenues()]);
  I.loadMatchups().catch(() => null);
  const body = h('div', { class: 'sh-section ip-gap' }); panel.append(body);
  const draw = () => {
    const t = I.team(sheet.get('t')) || D.teams.slice().sort((a, b) => a.rating.rank - b.rating.rank)[0], mode = sheet.get('mode') || 'all';
    body.innerHTML = '';
    const i = D.teams.indexOf(t), N = D.teams.length;
    const sel = S.ui.select({ label: 'Team', options: D.teams.map(x => ({ value: x.short, label: `${x.short} · ${x.name}` })), value: t.short, onChange: v => { sheet.set({ t: v }); draw(); } });
    const prev = S.ui.button({ label: '← ' + D.teams[(i + N - 1) % N].short, onClick: () => { sheet.set({ t: D.teams[(i + N - 1) % N].short }); draw(); } });
    const next = S.ui.button({ label: D.teams[(i + 1) % N].short + ' →', onClick: () => { sheet.set({ t: D.teams[(i + 1) % N].short }); draw(); } });
    const opp = D.teams.find(x => x !== t);
    body.append(h('div', { class: 'ip-ctlbar' }, S.ui.row(sel, prev, next), h('span', { class: 'sh-note ip-links' }, h('a', { href: I.hashFor('match', { a: t.short, b: opp.short }), text: 'Open a match' }), ' · ', h('a', { href: I.hashFor('sim', { a: t.short, b: opp.short }), text: 'Edit this XI in the simulator' }))));
    const R = t.rating;
    body.append(S.tiles([
      { label: 'Rank', value: '#' + R.rank, sub: `of ${N}, neutral win%` }, { label: 'Win % neutral', value: F.pct(R.win_pct_neutral, 1), sub: 'vs the other 9' }, { label: 'Win % home/away', value: F.pct(R.win_pct_home_away, 1), sub: '18 matchups' },
      { label: 'Runs for', value: F.num(R.runs_for, 1), sub: `against ${F.num(R.runs_against, 1)}` }, { label: 'Net runs', value: F.signed(R.net_runs, 1), sub: 'per match' },
      { label: 'XI value', value: F.num(R.xi_varp, 1), sub: `bat ${F.num(R.xi_bat_varp, 1)} · bowl ${F.num(R.xi_bowl_varp, 1)}` },
      { label: 'Home ground', value: (D.vById && D.vById.get(t.home_venue) && D.vById.get(t.home_venue).city) || I.venueName(t.home_venue).split(',').slice(-1)[0].trim(), sub: I.venueName(t.home_venue).split(',')[0] },
    ]));
    const cols = h('div', { class: 'sh-cols' }); body.append(cols);
    // XI
    const c1 = I.card(cols, `Default XI and Impact Player`, 'Batting order (recency-weighted mean position this season). Rates are true rates in IPL 2024–26 conditions; value is runs per match above replacement in this slot. The Impact Player bowls but does not bat.');
    const xt = h('div'); c1.append(xt);
    const xr = t.order.map((id, k) => ({ id, pos: k + 1, p: I.player(id) })).concat(t.impact_player ? [{ id: t.impact_player, pos: null, p: I.player(t.impact_player) }] : []);
    const pr = id => I.proj(id);
    const drawXI = () => S.table(xt, [
      { key: 'pos', label: '#', get: r => r.pos ?? 'IP' }, { key: 'n', label: 'Player', get: r => I.pname(r.id), render: (v, r) => esc(v) + (r.p && r.p.overseas ? ' <span class="muted" title="overseas">OS</span>' : '') },
      { key: 'role', label: 'Style', get: r => r.p ? [r.p.bat_hand ? r.p.bat_hand + 'HB' : '', r.p.bowl_group && r.p.bowl_group !== 'none' && (t.plan.some(x => x.id === r.id)) ? r.p.bowl_type || r.p.bowl_group : ''].filter(Boolean).join(' · ') : '' },
      { key: 'sr', label: 'SR', get: r => r.pos && r.p && r.p.bat ? r.p.bat.all.sr : null, fmt: 'num:1' }, { key: 'avg', label: 'Avg', get: r => r.pos && r.p && r.p.bat ? r.p.bat.all.avg : null, fmt: 'num:1' },
      { key: 'pr', label: 'Proj runs', get: r => pr(r.id) && r.pos ? pr(r.id).runs_mean : null, fmt: 'num:1', desc: 'Mean runs per innings over the 18 matchups' },
      { key: 'v', label: 'Bat value', get: r => r.pos && r.p && r.p.bat ? r.p.bat.value.varp_runs : null, fmt: 'signed:1' },
    ], xr);
    drawXI(); I.clickRows(xt, xr, r => I.playerCard(r.id, { focus: r.pos ? 'bat' : 'bowl', nav: { prev() {}, next() {} } }));
    // plan
    const c2 = I.card(cols, 'Bowling plan', 'Whole overs per phase from this season\'s workloads (6 / 9 / 5, at most 4 each); the strip is the over-by-over order the simulator\'s captain heuristic produces from it.');
    const plan = t.plan.slice().sort((a, b) => (b.pp + b.mid + b.death) - (a.pp + a.mid + a.death));
    const ids = plan.map(x => x.id);
    I.overStrip(c2.appendChild(h('div')), { sched: t.schedule && t.schedule.length === 20 ? t.schedule : [], bowlers: ids });
    const pt = h('div', { style: { marginTop: '8px' } }); c2.append(pt);
    S.table(pt, [
      { key: 'n', label: 'Bowler', get: x => I.pname(x.id) }, { key: 'ty', label: 'Type', get: x => { const p = I.player(x.id); return p ? p.bowl_type || p.bowl_subtype : ''; } },
      { key: 'pp', label: 'PP', fmt: 'int' }, { key: 'mid', label: 'Mid', fmt: 'int' }, { key: 'death', label: 'Death', fmt: 'int' }, { key: 'tot', label: 'Overs', get: x => x.pp + x.mid + x.death, fmt: 'int' },
      { key: 'ec', label: 'Econ', get: x => { const p = I.player(x.id); return p && p.bowl ? p.bowl.all.econ : null; }, fmt: 'num:2', desc: 'True economy (lower is better)' },
      { key: 'w', label: 'Wkt%', get: x => { const p = I.player(x.id); return p && p.bowl ? p.bowl.all.wkt_pct : null; }, fmt: 'num:2' },
      { key: 'v', label: 'Value', get: x => { const p = I.player(x.id); return p && p.bowl ? p.bowl.value.varp_4ov * (x.pp + x.mid + x.death) / 4 : null; }, fmt: 'signed:1', desc: 'Value per 4 overs × planned overs / 4, runs per match' },
    ], plan);
    I.clickRows(pt, plan, x => I.playerCard(x.id, { focus: 'bowl', nav: { prev() {}, next() {} } }));
    // decomposition
    const cols2 = h('div', { class: 'sh-cols' }); body.append(cols2);
    const md = S.ui.segmented({ label: 'Show', options: [{ value: 'all', label: 'Bat + bowl' }, { value: 'bat', label: 'Batting' }, { value: 'bowl', label: 'Bowling' }], value: mode, onChange: v => { sheet.set({ mode: v === 'all' ? null : v }); draw(); } });
    const items = [];
    if (mode !== 'bowl') t.order.forEach((id, k) => { const p = I.player(id); if (p && p.bat) items.push({ label: `${k + 1}. ${p.name}`, value: p.bat.value.varp_runs, id, desc: `batting, slot ${k + 1}: (${F.num(p.bat.value.rv100_slot, 1)} − ${F.num(p.bat.value.rep_rv100, 1)}) per 100 × ${F.num(p.bat.value.exp_balls, 1)} balls` }); });
    if (mode !== 'bat') t.plan.forEach(x => { const p = I.player(x.id), ov = x.pp + x.mid + x.death; if (p && p.bowl) items.push({ label: `${p.name} (${ov} ov)`, value: p.bowl.value.varp_4ov * ov / 4, id: x.id, desc: `bowling: ${F.signed(p.bowl.value.varp_4ov, 2)} per 4 overs × ${ov}/4` }); });
    items.sort((a, b) => b.value - a.value);
    const c3 = I.card(cols2, 'How the team strength adds up', `Each player's value above a replacement-level player of his role, runs per match. Batting: in his slot of the default order; bowling: at his planned overs. Sums: batting ${F.num(R.xi_bat_varp, 1)}, bowling ${F.num(R.xi_bowl_varp, 1)}, total ${F.num(R.xi_varp, 1)}.`);
    c3.append(S.ui.row(md));
    I.waterfall(c3.appendChild(h('div')), { items, start: 0, startLabel: 'Replacement XI', endLabel: t.short + (mode === 'bat' ? ' batting' : mode === 'bowl' ? ' bowling' : ' total'), fmt: 'signed:1', tickFmt: 'num:0', onClick: it => I.playerCard(it.id, { nav: { prev() {}, next() {} } }) });
    // phase strengths
    const ps = phaseStrength(t);
    const c4 = I.card(cols2, 'Strengths and weaknesses by phase', 'Runs per over better (+) or worse (−) than an average IPL side, from the players\' true phase rates. Batting: strike rate edge weighted by the balls each slot faces (approximate: every slot is given the same phase mix). Bowling: economy edge weighted by planned overs in that phase.');
    S.bar(c4.appendChild(h('div')), { data: ps.flatMap(r => [{ label: `Batting · ${I.PH_LABEL[r.ph]}`, value: r.bat, desc: `dismissals ${F.signed(r.batOut, 2)} per 100 balls vs average (lower is better)` }, { label: `Bowling · ${I.PH_LABEL[r.ph]}`, value: r.bowl, desc: `wickets ${F.signed(r.bowlWk, 2)} per 100 balls vs average (higher is better)` }]), fmt: 'signed:2', center: 0, barHeight: 11, rowGap: 6 });
    S.table(c4.appendChild(h('div', { style: { marginTop: '8px' } })), [{ key: 'ph', label: 'Phase', get: r => I.PH_LABEL[r.ph] }, { key: 'bat', label: 'Bat runs/over', fmt: 'signed:2' }, { key: 'batOut', label: 'Bat outs/100', fmt: 'signed:2', desc: 'lower is better' }, { key: 'bowl', label: 'Bowl runs/over saved', fmt: 'signed:2' }, { key: 'bowlWk', label: 'Bowl wkts/100', fmt: 'signed:2' }], ps);
    // squad
    const c5 = I.card(body, 'Squad this season', 'Everyone who played for the franchise in the latest season: appearances, last appearance, recency-weighted batting position and overs per match by phase. ✓ = in the default 12. Click a row for the card.');
    const sq = (t.squad || []).slice().sort((a, b) => b.apps - a.apps || a.bat_pos - b.bat_pos);
    const st = h('div'); c5.append(st);
    S.table(st, [
      { key: 'in', label: '', get: s => t.xii.includes(s.id) ? '✓' : '' }, { key: 'name', label: 'Player', render: (v, s) => esc(v) + (s.overseas ? ' <span class="muted">OS</span>' : '') + (s.in_pool ? '' : ' <span class="muted">(no rating)</span>') },
      { key: 'apps', label: 'Apps', fmt: 'int' }, { key: 'last_app', label: 'Last' }, { key: 'bat_pos', label: 'Bat pos', fmt: 'num:1' },
      { key: 'overs_pm', label: 'Ov/m', fmt: 'num:1' }, { key: 'ov_pp', label: 'PP', fmt: 'num:1' }, { key: 'ov_mid', label: 'Mid', fmt: 'num:1' }, { key: 'ov_death', label: 'Death', fmt: 'num:1' },
      { key: 'v', label: 'Value', get: s => { const p = I.player(s.id); return p ? p.varp_runs : null; }, fmt: 'signed:1', desc: 'Batting + bowling value, runs per match' },
    ], sq);
    I.clickRows(st, sq, s => I.playerCard(s.id, { nav: { prev() {}, next() {} } }));
  };
  draw();
  sheet.onState(draw);
  if (!D.proj) I.loadMatchups().then(() => { if (sheet.wb.active === sheet || !panel.hidden) draw(); }).catch(() => null);
}

/* ───────── Matchups ───────── */
async function matchups(panel, sheet) {
  await I.loadMatchups(); await I.loadVenues();
  const T = D.teams, M = D.M;
  const top = I.card(panel, 'Every matchup', null);
  const note = h('div', { class: 'sh-note' }), hm = h('div');
  const metric = S.ui.segmented({ label: 'Show', options: [{ value: 'win', label: 'Win %' }, { value: 't1', label: 'Row total' }, { value: 'tt', label: 'Match total' }], value: sheet.get('m') || 'win', onChange: v => { sheet.set({ m: v === 'win' ? null : v }); draw(); } });
  const ven = S.ui.segmented({ label: 'Venue', options: [{ value: 'home', label: 'Row team at home' }, { value: 'n', label: 'Neutral ground' }], value: sheet.get('v') === 'n' ? 'n' : 'home', onChange: v => { sheet.set({ v: v === 'n' ? 'n' : null }); draw(); } });
  top.append(note, S.ui.row(metric, ven), hm);
  const val = (a, b, m, neu) => {
    if (a === b) return null;
    if (neu) {
      const r = M.neutral.find(x => (x.A === a.name && x.B === b.name) || (x.A === b.name && x.B === a.name)); if (!r) return null; const sw = r.A !== a.name;
      return m === 'win' ? (sw ? 1 - r.p_win_A : r.p_win_A) : m === 't1' ? (sw ? r.runs_B : r.runs_A) : r.runs_A + r.runs_B;
    }
    const P = I.preMatch(a, b, 'A'); if (!P) return null;
    return m === 'win' ? P.pWinA : m === 't1' ? P.A.total.mean : P.A.total.mean + P.B.total.mean;
  };
  const draw = () => {
    const m = sheet.get('m') || 'win', neu = sheet.get('v') === 'n';
    note.textContent = `Rows: the team named; columns: the opponent. ${neu ? 'Neutral ground (average venue), half the sims each way; matchups.json carries only win probability and mean runs for these.' : 'Row team at its home ground.'} ${F.int(M.n_sims)} simulations per match, default XIs, toss unknown (half each way). Click a cell for the match.`;
    const vals = T.map(a => T.map(b => val(a, b, m, neu)));
    const spec = m === 'win' ? { center: 0.5, domain: [0.25, 0.75], fmt: 'pct:0', vl: 'P(row team wins)' } : m === 't1' ? { fmt: 'num:0', vl: 'row team mean total, runs' } : { fmt: 'num:0', vl: 'match total (both innings), runs' };
    S.heatmap(hm, { rows: T.map(t => t.short), cols: T.map(t => t.short), values: vals, center: spec.center, domain: spec.domain, fmt: spec.fmt, valueLabel: spec.vl, scaleLabel: spec.vl, vs: neu ? 'v' : 'hosting', maxCell: 64, cellH: 26, onCell: (i, j) => { if (i !== j) I.go('match', { a: T[i].short, b: T[j].short, v: neu ? 'n' : null }); } });
  };
  draw();
  sheet.onState(() => { metric.value = sheet.get('m') || 'win'; ven.value = sheet.get('v') === 'n' ? 'n' : 'home'; draw(); });
  const rows = (M.matchups || []).map(r => {
    const H = I.team(r.home), A2 = I.team(r.home === r.A ? r.B : r.A), P = I.preMatch(H, A2, 'A');
    return { h: H.short, a: A2.short, ven: I.venueName(r.venue).split(',')[0], hw: P.pWinA, tie: P.pTie, ht: P.A.total.mean, at: P.B.total.mean, mt: P.A.total.mean + P.B.total.mean, hpp: P.A.pp.mean, app: P.B.pp.mean, s6: P.A.sixes.mean + P.B.sixes.mean, hb1: P.A.pWinBat1, hb2: P.A.pWinBat2 };
  });
  const gc = h('div', { class: 'sh-section' }); panel.append(gc);
  gc.append(h('div', { class: 'sh-h', text: 'All 90 home matches' }), h('div', { class: 'sh-note', text: 'Each pair at each side\'s home ground. Fair prices follow the odds toggle. Click a row for the match.' }));
  const grid = sheet.grid(gc, { stateKey: 'g', height: 460, rows, sort: '-hw', csv: 'ipl-matchups.csv', searchPlaceholder: 'Search team', footer: false, onRowClick: r => I.go('match', { a: r.h, b: r.a }),
    columns: [
      { key: 'h', label: 'Home', type: 'cat', frozen: true, width: 62 }, { key: 'a', label: 'Away', type: 'cat', frozen: true, width: 62 }, { key: 'ven', label: 'Ground', type: 'text', width: 150 },
      { key: 'hw', label: 'Home win', fmt: 'pct:1', heat: { center: 0.5, domain: [0.3, 0.7] }, desc: 'P(home side wins), super over included.' },
      { key: 'hml', label: 'Home fair', get: r => r.hw, fmt: p => I.fp(p), desc: 'Fair (no-vig) price, home side.' }, { key: 'aml', label: 'Away fair', get: r => 1 - r.hw, fmt: p => I.fp(p), desc: 'Fair price, away side.' },
      { key: 'ht', label: 'Home runs', fmt: 'num:1', desc: 'Mean home total.' }, { key: 'at', label: 'Away runs', fmt: 'num:1', desc: 'Mean away total.' }, { key: 'mt', label: 'Match', fmt: 'num:1', heat: { type: 'seq' }, desc: 'Mean runs in both innings.' },
      { key: 'hpp', label: 'Home PP', fmt: 'num:1', desc: 'Mean home powerplay runs.' }, { key: 'app', label: 'Away PP', fmt: 'num:1' }, { key: 's6', label: 'Sixes', fmt: 'num:1', desc: 'Mean sixes in the match.' },
      { key: 'hb1', label: 'H win bat 1st', fmt: 'pct:1', desc: 'P(home wins) when it bats first.' }, { key: 'hb2', label: 'H win chasing', fmt: 'pct:1', desc: 'P(home wins) when it bats second.' }, { key: 'tie', label: 'Tie', fmt: 'pct:1', desc: 'P(level after 20 overs).' },
    ] });
  I.odds.bind(gc, () => grid.refresh());
}

/* ───────── Match ───────── */
function pickTeams(sheet) {
  const T = D.teams; let a = I.team(sheet.get('a')) || T.find(t => t.short === 'MI') || T[0], b = I.team(sheet.get('b')) || T.find(t => t.short === 'CSK') || T[1];
  if (a === b) b = T.find(t => t !== a);
  return { a, b, vk: ['A', 'B', 'n'].includes(sheet.get('v')) ? sheet.get('v') : 'A', bf: ['A', 'B'].includes(sheet.get('t')) ? sheet.get('t') : null };
}
function matchPicker(sheet, onPick) {
  const { a, b, vk, bf } = pickTeams(sheet);
  const opts = D.teams.map(t => ({ value: t.short, label: `${t.short} · ${t.name}` }));
  const sa = S.ui.select({ label: 'Team', options: opts, value: a.short, onChange: v => pick(v, sb.value, vk, bf) });
  const sb = S.ui.select({ label: 'Opponent', options: opts, value: b.short, onChange: v => pick(sa.value, v, vk, bf) });
  const ven = S.ui.segmented({ label: 'Ground', options: [{ value: 'A', label: a.short + ' home' }, { value: 'B', label: b.short + ' home' }, { value: 'n', label: 'Neutral' }], value: vk, onChange: v => pick(sa.value, sb.value, v, bf) });
  const tos = S.ui.segmented({ label: 'Bats first', options: [{ value: '', label: 'Toss unknown' }, { value: 'A', label: a.short }, { value: 'B', label: b.short }], value: bf || '', onChange: v => pick(sa.value, sb.value, vk, v || null) });
  function pick(x, y, v, t) { if (x === y) y = D.teams.find(tt => tt.short !== x).short; onPick(x, y, v, t); }
  return { el: S.ui.row(sa, sb, ven, tos), a, b, vk, bf };
}
/** the match for a picker state: exact pmfs from data/matchups/<HOST>.json; neutral grounds (and old exports) fill
    the distributions from an in-browser simulation of the default XIs */
async function matchFor(pk, onApprox) {
  const { a, b, vk, bf } = pk;
  if (vk !== 'n') {
    const M = await I.exactMatch(a, b, vk, bf);
    if (!M || M.exact) return M;
    if (onApprox) onApprox(M);
    const X = await I.exactFor(a, b, vk).catch(e => { console.warn(e); return null; });
    return X ? I.overlay(M, X) : M;
  }
  if (bf) {
    const X = await I.exactFor(a, b, 'n', bf);
    X.tossNote = 'The export has no per-toss neutral-ground distributions, so this match is simulated in the browser.';
    return X;
  }
  const M = I.preMatch(a, b, 'n'); if (!M) return null;
  if (M.neutralOnly) return I.exactFor(a, b, 'n');
  if (onApprox) onApprox(M);
  const X = await I.exactFor(a, b, 'n').catch(e => { console.warn(e); return null; });
  return X ? I.overlay(M, X) : M;
}
async function match(panel, sheet) {
  await I.loadMatchups(); await I.loadVenues();
  I.loadPlayers().catch(() => null);
  const ctl = h('div'), body = h('div', { class: 'sh-section ip-gap' }); panel.append(ctl, body);
  let token = 0;
  const lk = ['ta', 'tb', 'mt', 'i1', 'pa', 'pb', 'fa', 'fb', 'sa', 'sb', 'xa', 'xb'];
  const draw = async () => {
    const my = ++token;
    const pk = matchPicker(sheet, (x, y, v, t) => { sheet.set(Object.assign({ a: x, b: y, v: v === 'A' ? null : v, t }, Object.fromEntries(lk.map(k => [k, null])))); draw(); });
    ctl.innerHTML = ''; ctl.append(h('div', { class: 'ip-ctlbar' }, pk.el, h('span', { class: 'sh-note ip-links' }, h('a', { href: I.hashFor('props', { a: pk.a.short, b: pk.b.short, v: pk.vk === 'A' ? null : pk.vk, t: pk.bf }), text: 'Player props' }), ' · ', h('a', { href: I.hashFor('sim', { a: pk.a.short, b: pk.b.short, v: pk.vk === 'B' ? pk.b.home_venue : pk.vk === 'n' ? 'neutral' : null, tw: pk.bf ? 'a' : null, td: pk.bf === 'B' ? 'bowl' : null }), text: 'Change it in the simulator' }))));
    const L = k => { const v = parseFloat(sheet.get(k)); return isFinite(v) ? v : null; };
    const opts = () => ({ lines: Object.fromEntries(lk.map(k => [k, L(k)])), onLines: o => sheet.set(o) });
    body.innerHTML = ''; body.append(S.loadingEl('Loading the match…'));
    let shown = false;
    const M = await matchFor(pk, M0 => { if (my !== token) return; body.innerHTML = ''; I.renderMatch(body, M0, opts()); shown = true; }).catch(e => e);
    if (my !== token) return;
    if (M instanceof Error) { body.innerHTML = ''; body.append(S.errorEl(M, 'Could not build the match')); return; }
    if (!M) { body.innerHTML = ''; body.append(S.errorEl(new Error('No precomputed matchup for this pair.'))); return; }
    const sc = panel.scrollTop;
    I.renderMatch(body, M, opts());
    if (shown) panel.scrollTop = sc;
    I.matchLast = { M };
  };
  await draw();
  sheet.onState(draw);
}

/* ───────── Player props ───────── */
async function props(panel, sheet) {
  await I.loadMatchups(); await I.loadVenues();
  I.loadPlayers().catch(() => null);
  const ctl = h('div'), pricer = I.card(null, null, null, 'ip-pricer'), gwrap = h('div', { class: 'sh-section' });
  panel.append(ctl, pricer, gwrap);
  let grid = null, M = null, rows = [];
  const statCols = [];
  I.STATS.forEach(([k, lab, sh]) => {
    const s = r => I.statOf(r.p, k);
    const g = lab;
    statCols.push({ key: k + '_m', label: 'Mean', group: g, get: r => s(r) && s(r).mean, fmt: k === 'wkts' ? 'num:2' : 'num:1', heat: { type: 'seq' }, desc: `${lab}: simulated mean.` });
    statCols.push({ key: k + '_md', label: 'Med', group: g, get: r => s(r) && s(r).dist && s(r).dist.quantile(0.5), fmt: 'num:0', desc: `${lab}: median.` });
    statCols.push({ key: k + '_q10', label: '10%', group: g, get: r => s(r) && s(r).dist && s(r).dist.quantile(0.1), fmt: 'num:0', desc: `${lab}: 10th percentile.` });
    statCols.push({ key: k + '_q90', label: '90%', group: g, get: r => s(r) && s(r).dist && s(r).dist.quantile(0.9), fmt: 'num:0', desc: `${lab}: 90th percentile.` });
    statCols.push({ key: k + '_ln', label: '50% line', group: g, get: r => s(r) && s(r).dist ? I.fairLine(s(r).dist, s(r).mean) : null, fmt: 'num:1', desc: `${lab}: the half-run line closest to a 50/50 split.` });
  });
  const columns = [
    { key: 'name', label: 'Player', frozen: true, width: 150, get: r => r.p.name },
    { key: 'team', label: 'Team', type: 'cat', width: 56, get: r => r.team },
    { key: 'pos', label: '#', get: r => r.p.pos, fmt: 'int', width: 40, desc: 'Batting position (blank = Impact Player, bowls only).' },
    ...statCols,
    { key: 'p30', label: 'P(30+)', group: 'Milestones', get: r => r.p.pRuns && r.p.pRuns[30], fmt: 'pct:1', desc: 'P(30 or more runs).' },
    { key: 'p50', label: 'P(50+)', group: 'Milestones', get: r => r.p.pRuns && r.p.pRuns[50], fmt: 'pct:1', desc: 'P(50 or more runs).' },
    { key: 'f50', label: '50+ fair', group: 'Milestones', get: r => r.p.pRuns && r.p.pRuns[50], fmt: p => I.fp(p), desc: 'Fair price for a fifty.' },
    { key: 'w2', label: 'P(2+ wk)', group: 'Milestones', get: r => r.p.bowl && r.p.bowl.pW[2], fmt: 'pct:1', desc: 'P(2 or more wickets).' },
    { key: 'tb', label: 'Top bat', group: 'Milestones', get: r => r.p.pTop, fmt: 'pct:1', desc: 'P(top run-scorer for his side), dead heats split.' },
    { key: 'tbf', label: 'Fair', group: 'Milestones', get: r => r.p.pTop, fmt: p => I.fp(p), desc: 'Fair price, top team batter.' },
    { key: 'tw', label: 'Top bowl', group: 'Milestones', get: r => r.p.bowl && r.p.bowl.pTop, fmt: 'pct:1', desc: 'P(top wicket-taker for his side).' },
  ];
  const groups = I.STATS.map(([, lab]) => ({ id: lab, label: lab, hidden: !['Runs', 'Sixes', 'Wickets'].includes(lab) })).concat([{ id: 'Milestones', label: 'Milestones' }]);
  const drawPricer = () => {
    pricer.innerHTML = '';
    const pid = sheet.get('p'), key = I.STATS.some(x => x[0] === sheet.get('st')) ? sheet.get('st') : 'runs';
    let row = rows.find(r => r.p.id === pid) || rows.slice().sort((x, y) => ((y.p.runs && y.p.runs.mean) || 0) - ((x.p.runs && x.p.runs.mean) || 0))[0];
    if (!row) return;
    const psel = S.ui.select({ label: 'Player', options: rows.map(r => ({ value: r.p.id, label: `${r.p.name} (${r.team})` })), value: row.p.id, onChange: v => { sheet.set({ p: v, ln: null }); drawPricer(); } });
    const avail = I.STATS.filter(([k]) => I.statOf(row.p, k));
    const k2 = avail.some(x => x[0] === key) ? key : avail[0][0];
    const ssel = S.ui.segmented({ label: 'Stat', options: avail.map(([k, , s]) => ({ value: k, label: s })), value: k2, onChange: v => { sheet.set({ st: v === 'runs' ? null : v, ln: null }); drawPricer(); } });
    const m = I.STATS.find(x => x[0] === k2);
    pricer.append(h('div', { class: 'sh-h', text: 'Prop pricer' }), h('div', { class: 'sh-note', text: `${row.p.name} (${row.team}), ${m[1].toLowerCase()} in ${M.a.short} v ${M.b.short} at ${M.venue === 'neutral' ? 'a neutral ground' : I.venueName(M.venue)}. Type a line for P(over/under) and fair prices.` }), S.ui.row(psel, ssel));
    const sp = h('div', { class: 'sh-section' }); pricer.append(sp);
    const ln = parseFloat(sheet.get('ln'));
    I.statPanel(sp, I.statOf(row.p, k2), { key: k2, label: m[1], short: m[2], line: isFinite(ln) ? ln : null, onLine: L => sheet.set({ ln: L }) });
  };
  let token = 0;
  const draw = async () => {
    const my = ++token;
    const pk = matchPicker(sheet, (x, y, v, t) => { sheet.set({ a: x, b: y, v: v === 'A' ? null : v, t, p: null, ln: null }); draw(); });
    ctl.innerHTML = ''; ctl.append(h('div', { class: 'ip-ctlbar' }, pk.el, h('span', { class: 'sh-note ip-links' }, h('a', { href: I.hashFor('match', { a: pk.a.short, b: pk.b.short, v: pk.vk === 'A' ? null : pk.vk, t: pk.bf }), text: 'Match sheet' }))));
    pricer.innerHTML = ''; pricer.append(S.loadingEl(pk.vk === 'n' ? 'Simulating this neutral-ground match in the browser…' : 'Loading exact distributions…'));
    const M2 = await matchFor(pk).catch(e => e);
    if (my !== token) return;
    if (M2 instanceof Error || !M2) { pricer.innerHTML = ''; pricer.append(S.errorEl(M2 || new Error('No matchup'), 'Could not build the match')); return; }
    M = M2;
    rows = [...M.A.players.map(p => ({ p, sd: 'A', team: M.a.short })), ...M.B.players.map(p => ({ p, sd: 'B', team: M.b.short }))];
    drawPricer();
    if (!grid) {
      gwrap.append(h('div', { class: 'sh-h', text: 'Everyone in this match' }), h('div', { class: 'sh-note', text: 'Means from the precomputed matchup (or from the distributions when a batting-first side is chosen); medians, percentiles and 50% lines from the exact simulated distributions. Stat groups toggle with the chips. Click a row to load him in the pricer (clicking inside a stat group also picks that stat).' }));
      grid = sheet.grid(gwrap, { stateKey: 'g', height: 520, columns, groups, rows, sort: '-runs_m', csv: 'ipl-player-props.csv', footer: false, searchPlaceholder: 'Search player',
        onRowClick: r => { const sel = grid.selected(); const col = sel && sel.column ? sel.column.split('_')[0] : null; sheet.set({ p: r.p.id, ln: null, st: col && I.STATS.some(x => x[0] === col) ? (col === 'runs' ? null : col) : sheet.get('st') }); drawPricer(); pricer.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } });
      I.odds.bind(gwrap, () => grid.refresh());
    } else grid.setRows(rows);
  };
  await draw();
  sheet.onState(() => draw());
}

/* ───────── Simulator ───────── */
const planStr = plan => plan.filter(x => x.pp + x.mid + x.death > 0).map(x => `${x.id}:${x.pp}.${x.mid}.${x.death}`).join(',');
const parsePlan = s => (s || '').split(',').filter(Boolean).map(t => { const [id, q] = t.split(':'); const [pp, mid, death] = (q || '').split('.').map(Number); return { id, pp: pp || 0, mid: mid || 0, death: death || 0 }; }).filter(x => x.id);
function checkPlan(plan, xii) {
  const tot = { pp: 0, mid: 0, death: 0 }, errs = [];
  plan.forEach(x => { I.PH.forEach(p => { tot[p] += x[p]; }); const o = x.pp + x.mid + x.death; if (o > 4) errs.push(`${I.pname(x.id)} has ${o} overs (max 4)`); if (!xii.includes(x.id)) errs.push(`${I.pname(x.id)} is not in the XII`); });
  if (tot.pp !== 6) errs.push(`powerplay has ${tot.pp} of 6 overs`); if (tot.mid !== 9) errs.push(`middle has ${tot.mid} of 9 overs`); if (tot.death !== 5) errs.push(`death has ${tot.death} of 5 overs`);
  if (plan.filter(x => x.pp + x.mid + x.death > 0).length < 5) errs.push('at least 5 bowlers are needed (no one may bowl consecutive overs)');
  return { tot, errs };
}
async function simulator(panel, sheet) {
  await Promise.all([I.loadPlayers(), I.loadMatchups(), I.loadVenues()]);
  const SP = await I.loadSimParams();
  await loadSimJs().catch(() => null);
  const left = h('div', { class: 'sh-card ip-simctl' }), right = h('div', { class: 'ip-simout' });
  panel.append(h('div', { class: 'ip-simgrid' }, left, right));
  const baseCache = new Map();
  let job = null, last = null, stale = false;
  const prog = S.ui.progress(), status = h('span', { class: 'sh-note num' }), res = h('div', { class: 'sh-section' });
  right.append(h('div', { class: 'ip-progrow' }, prog, status), res);
  const rated = id => !!(SP.batters[id] || SP.bowlers[id]);
  const st = () => {
    const T = D.teams; let a = I.team(sheet.get('a')) || T.find(t => t.short === 'MI') || T[0], b = I.team(sheet.get('b')) || T.find(t => t.short === 'CSK') || T[1];
    if (a === b) b = T.find(t => t !== a);
    let v = sheet.get('v') || a.home_venue; if (v !== 'neutral' && !SP.venues[v]) v = a.home_venue;
    const side = (k, t) => {
      let order = (sheet.get(k + 'o') || '').split(',').filter(Boolean); if (order.length !== 11) order = t.order.slice();
      let ip = sheet.get(k + 'i') || t.impact_player; if (order.includes(ip)) ip = t.impact_player && !order.includes(t.impact_player) ? t.impact_player : null;
      let plan = sheet.get(k + 'p') ? parsePlan(sheet.get(k + 'p')) : t.plan.map(x => Object.assign({}, x));
      return { t, order, ip, plan, xii: order.concat(ip ? [ip] : []) };
    };
    const tw = sheet.get('tw') === 'a' || sheet.get('tw') === 'b' ? sheet.get('tw') : '', td = sheet.get('td') === 'bowl' ? 'bowl' : 'bat';
    const batFirst = !tw ? null : (tw === 'a') === (td === 'bat') ? 'A' : 'B';
    const CO = SP.conditions || {};
    const pitch = CO.pitch && CO.pitch[sheet.get('pi')] ? sheet.get('pi') : 'normal', dew = CO.dew && CO.dew[sheet.get('dw')] ? sheet.get('dw') : 'normal';
    const conditions = {}; if (pitch !== 'normal') conditions.pitch = pitch; if (dew !== 'normal') conditions.dew = dew;
    return { a, b, v, tw, td, batFirst, pitch, dew, conditions, n: +(sheet.get('n') || 20000), A: side('a', a), B: side('b', b) };
  };
  const sideDefault = sd => sd.order.join() === sd.t.order.join() && sd.ip === sd.t.impact_player && planStr(sd.plan) === planStr(sd.t.plan);
  const spec = sd => ({ name: sd.t.name, order: sd.order, plan: sd.plan.filter(x => x.pp + x.mid + x.death > 0), schedule: sideDefault(sd) ? sd.t.schedule : null });
  function drawControls() {
    const s = st(); left.innerHTML = '';
    const set = (o, re = true) => { sheet.set(o); markStale(); if (re) drawControls(); };
    const clearSides = { ao: null, ai: null, ap: null, bo: null, bi: null, bp: null };
    const opts = D.teams.map(t => ({ value: t.short, label: `${t.short} · ${t.name}` }));
    const sa = S.ui.select({ label: 'Team A', options: opts, value: s.a.short, onChange: v => set(Object.assign({ a: v, b: v === s.b.short ? s.a.short : s.b.short, v: null }, clearSides)) });
    const sb = S.ui.select({ label: 'Team B', options: opts, value: s.b.short, onChange: v => set(Object.assign({ b: v, a: v === s.a.short ? s.b.short : s.a.short, v: null }, clearSides)) });
    const vopts = [{ value: s.a.home_venue, label: `${s.a.short} home · ${I.venueName(s.a.home_venue).split(',')[0]}` }, { value: s.b.home_venue, label: `${s.b.short} home · ${I.venueName(s.b.home_venue).split(',')[0]}` }, { value: 'neutral', label: 'Neutral (average ground)' }]
      .concat(D.venues.filter(x => x.ipl_matches > 0 && SP.venues[x.venue] && x.venue !== s.a.home_venue && x.venue !== s.b.home_venue).sort((x, y) => y.ipl_matches - x.ipl_matches).map(x => ({ value: x.venue, label: `${x.name.split(',')[0]} (${x.ipl_matches} IPL)` })));
    const ven = S.ui.select({ label: 'Ground', options: vopts, value: s.v, onChange: v => set({ v: v === s.a.home_venue ? null : v }, false) });
    const tw = S.ui.select({ label: 'Toss won by', options: [{ value: '', label: 'Unknown (50/50)' }, { value: 'a', label: s.a.short }, { value: 'b', label: s.b.short }], value: s.tw, onChange: v => set({ tw: v || null }) });
    const td = S.ui.segmented({ label: 'Chooses to', options: [{ value: 'bat', label: 'Bat' }, { value: 'bowl', label: 'Bowl' }], value: s.td, onChange: v => set({ td: v === 'bat' ? null : v }, false) });
    const sims = S.ui.select({ label: 'Simulations', options: [5000, 10000, 20000, 50000, 100000].map(v => ({ value: v, label: F.int(v) })), value: s.n, onChange: v => set({ n: v === 20000 ? null : v }, false) });
    const run = S.ui.button({ label: 'Run simulation', primary: true, onClick: () => go(true) });
    const reset = S.ui.button({ label: 'Reset all', onClick: () => { sheet.set(Object.assign({ v: null, tw: null, td: null, n: null, pi: null, dw: null }, clearSides)); markStale(); drawControls(); } });
    const CO = SP.conditions || {}, lab = { normal: 'Normal', flat: 'Flat', slow_low: 'Slow / low', seaming: 'Seaming', none: 'None', heavy: 'Heavy' };
    const ord = (g, pref) => pref.filter(k => CO[g] && CO[g][k]).concat(Object.keys(CO[g] || {}).filter(k => !pref.includes(k)));
    const pi = CO.pitch ? S.ui.select({ label: 'Pitch', options: ord('pitch', ['flat', 'normal', 'slow_low', 'seaming']).map(k => ({ value: k, label: lab[k] || k })), value: s.pitch, onChange: v => set({ pi: v === 'normal' ? null : v }, false) }) : null;
    const dw = CO.dew ? S.ui.select({ label: 'Dew (2nd innings)', options: ord('dew', ['none', 'normal', 'heavy']).map(k => ({ value: k, label: lab[k] || k })), value: s.dew, onChange: v => set({ dw: v === 'normal' ? null : v }, false) }) : null;
    run.classList.add('ip-run');
    const errsA = checkPlan(s.A.plan, s.A.xii).errs, errsB = checkPlan(s.B.plan, s.B.xii).errs;
    if (errsA.length || errsB.length) run.disabled = true;
    left.append(S.ui.row(sa, sb), S.ui.row(ven, sims), pi || dw ? S.ui.row(pi || h('span'), dw || h('span')) : h('span'), S.ui.row(tw, s.tw ? td : h('span')), S.ui.row(run, reset));
    if (pi || dw) left.append(h('div', { class: 'sh-note', text: 'Pitch and dew are scenario dials estimated from the data, not fitted to a match. Flat = +1 SD of the shared match-conditions shock on every ball; slow/low = −1 SD plus the spin edge of the most spin-friendly fifth of grounds; seaming = −0.5 SD plus the pace-wicket edge of the most seam-friendly fifth. Heavy / no dew shift scoring on 2nd-innings balls by the 90th / 10th percentile of the real match-level chase advantage (IPL 2022–26, sampling noise removed). Every simulated match also draws a shared match shock and a separate shock per innings. See Method.' }));
    if (s.tw) left.append(h('div', { class: 'sh-note', text: `${s.batFirst === 'A' ? s.a.short : s.b.short} bat first.` }));
    if (errsA.length || errsB.length) left.append(h('div', { class: 'sh-note bad', text: 'Fix the bowling plan before running: ' + [...errsA.map(e => s.a.short + ': ' + e), ...errsB.map(e => s.b.short + ': ' + e)].join('; ') + '.' }));
    left.append(sideEditor(s, 'a'), sideEditor(s, 'b'));
    left.append(h('div', { class: 'sh-note', text: `Seed ${I.SIM_SEED}, ${I.SIM_WORKERS} workers: the same link reproduces the same numbers. Players without a rating use the prior for a middle-order batter / regular pace bowler.` }));
  }
  function sideEditor(s, k) {
    const sd = k === 'a' ? s.A : s.B, t = sd.t, box = h('div', { class: 'ip-roster' });
    const setSide = (o) => { sheet.set({ [k + 'o']: o.order ? (o.order.join() === t.order.join() ? null : o.order.join(',')) : undefined, [k + 'i']: o.ip !== undefined ? (o.ip === t.impact_player ? null : o.ip) : undefined, [k + 'p']: o.plan ? (planStr(o.plan) === planStr(t.plan) ? null : planStr(o.plan)) : undefined }); markStale(); drawControls(); };
    const setSideClean = o => { const x = {}; for (const kk in o) if (o[kk] !== undefined) x[kk] = o[kk]; setSide(x); };
    box.append(h('div', { class: 'ip-rhead' }, h('div', { class: 'sh-h', text: `${t.short} XI` }), sideDefault(sd) ? h('span', { class: 'sh-note', text: 'default' }) : S.ui.button({ label: 'Reset ' + t.short, onClick: () => { sheet.set({ [k + 'o']: null, [k + 'i']: null, [k + 'p']: null }); markStale(); drawControls(); } })));
    const lab = id => { const p = I.player(id); return p && p.bat ? `SR ${F.num(p.bat.all.sr, 0)} · avg ${F.num(p.bat.all.avg, 0)}` : 'no batting rating'; };
    const dl = S.ui.dragList({ label: 'Batting order (drag, or focus and Alt+↑/↓)', items: sd.order.map(id => ({ id, label: I.pname(id) + (rated(id) ? '' : ' *'), sub: lab(id) })), onChange: ids => setSideClean({ order: ids }) });
    box.append(dl);
    // impact player + swap
    const ipSel = S.ui.select({ label: 'Impact Player (bowls, does not bat)', options: sd.xii.map(id => ({ value: id, label: I.pname(id) })), value: sd.ip, onChange: v => { if (v === sd.ip) return; const order = sd.order.slice(); const i = order.indexOf(v); if (i >= 0 && sd.ip) order[i] = sd.ip; setSideClean({ order, ip: v }); } });
    box.append(ipSel);
    const outSel = S.ui.select({ label: 'Take out', options: sd.xii.map(id => ({ value: id, label: I.pname(id) })), value: sd.xii[0] });
    const sq = (t.squad || []).filter(x => !sd.xii.includes(x.id)).map(x => x.id);
    const other = D.players.filter(p => !sd.xii.includes(p.id) && !sq.includes(p.id) && rated(p.id)).sort((x, y) => (y.varp_runs || -99) - (x.varp_runs || -99)).map(p => p.id);
    const vlab = id => { const p = I.player(id); if (!p) return ''; const b = p.bat ? F.signed(p.bat.value.varp_runs, 1) : '–', w = p.bowl ? F.signed(p.bowl.value.varp_runs, 1) : '–'; return `bat ${b} / bowl ${w}`; };
    const inSel = S.ui.select({ label: 'Bring in (squad first, then anyone)', options: sq.map(id => ({ value: id, label: `${I.pname(id)} · ${t.short} squad · ${vlab(id)}` })).concat(other.map(id => ({ value: id, label: `${I.pname(id)} · ${I.player(id)._team ? I.player(id)._team.short : 'no IPL team'} · ${vlab(id)}` }))), value: sq[0] || other[0] });
    const swap = S.ui.button({ label: 'Swap', onClick: () => {
      const o = outSel.value, n = inSel.value; if (!o || !n) return;
      const order = sd.order.map(id => id === o ? n : id), ip = sd.ip === o ? n : sd.ip, plan = sd.plan.map(x => x.id === o ? Object.assign({}, x, { id: n }) : x);
      setSideClean({ order, ip, plan });
    } });
    box.append(h('div', { class: 'ip-swap' }, outSel, inSel, swap));
    // bowling plan editor
    const ck = checkPlan(sd.plan, sd.xii);
    const tb = h('table', { class: 'sh-tbl ip-ptab' });
    tb.append(h('thead', null, h('tr', null, h('th', { text: 'Bowler' }), ...['PP', 'Mid', 'Death'].map((x, i) => h('th', { class: 'n', text: x, title: ['Overs 1–6', 'Overs 7–15', 'Overs 16–20'][i] })), h('th', { class: 'n', text: 'Econ', title: 'True economy (lower is better)' }))));
    const bd = h('tbody'); tb.append(bd);
    const cand = sd.xii.filter(id => sd.plan.some(x => x.id === id) || (I.player(id) && I.player(id).bowl && I.player(id).bowl_group !== 'none'));
    cand.sort((x, y) => { const px = sd.plan.find(z => z.id === x), py = sd.plan.find(z => z.id === y); return ((py ? py.pp + py.mid + py.death : 0) - (px ? px.pp + px.mid + px.death : 0)); });
    cand.forEach(id => {
      const row = sd.plan.find(x => x.id === id) || { id, pp: 0, mid: 0, death: 0 }, p = I.player(id);
      const tr = h('tr', null, h('td', { class: 'ip-pn', text: I.pname(id) + (p && p.bowl_type ? ' · ' + p.bowl_type : '') }));
      I.PH.forEach(ph => {
        const inp = h('input', { type: 'number', min: 0, max: 4, step: 1, class: 'ip-ov', value: row[ph], 'aria-label': `${I.pname(id)} ${I.PH_LABEL[ph]} overs` });
        inp.addEventListener('change', () => { const v = Math.max(0, Math.min(4, Math.round(+inp.value || 0))); const plan = sd.plan.map(x => Object.assign({}, x)); let r = plan.find(x => x.id === id); if (!r) { r = { id, pp: 0, mid: 0, death: 0 }; plan.push(r); } r[ph] = v; setSideClean({ plan }); });
        tr.append(h('td', { class: 'n' }, inp));
      });
      tr.append(h('td', { class: 'n muted', text: p && p.bowl ? F.num(p.bowl.all.econ, 2) : '–' }));
      bd.append(tr);
    });
    bd.append(h('tr', { class: 'ip-tot' }, h('td', { text: 'Total (need 6 / 9 / 5)' }), ...I.PH.map(ph => h('td', { class: 'n' + (ck.tot[ph] !== { pp: 6, mid: 9, death: 5 }[ph] ? ' bad' : ''), text: String(ck.tot[ph]) })), h('td')));
    box.append(h('div', { class: 'ui-l', text: 'Bowling plan (overs per phase)' }), h('div', { class: 'sh-tbl-wrap' }, tb));
    if (!ck.errs.length && window.IPLSim) {
      const sched = window.IPLSim.bowlingSchedule(sd.plan.filter(x => x.pp + x.mid + x.death > 0));
      I.overStrip(box.appendChild(h('div')), { sched, bowlers: [...new Set(sched)] });
    }
    return box;
  }
  function markStale() { if (last && !stale) { stale = true; status.textContent = 'Settings changed. Run again to update.'; } }
  let runTok = 0;
  function go(fromUser) {
    if (job) job.cancel();
    const tok = ++runTok;
    const s = st();
    if (checkPlan(s.A.plan, s.A.xii).errs.length || checkPlan(s.B.plan, s.B.xii).errs.length) { status.textContent = 'Fix the bowling plan first.'; return; }
    const venue = s.v === 'neutral' ? null : s.v;
    const personnel = !sideDefault(s.A) || !sideDefault(s.B), changed = personnel || !!s.batFirst || Object.keys(s.conditions).length > 0;
    const bkey = [s.a.short, s.b.short, s.v, s.n].join('|');
    const needBase = changed && !baseCache.has(bkey);
    const params = { A: spec(s.A), B: spec(s.B), opts: { venue, batFirst: s.batFirst, conditions: Object.keys(s.conditions).length ? s.conditions : null }, sims: s.n, base: needBase ? { A: I.defTeam(s.a), B: I.defTeam(s.b), opts: { venue } } : null };
    prog.set(0); status.textContent = `Running ${F.int(s.n)} matches${needBase ? ' plus the default for comparison' : ''}…`; stale = false;
    const t0 = performance.now();
    I.simulate(params, f => { if (tok === runTok) prog.set(f); }).then(w => { if (tok !== runTok) { w.job.cancel(); const e = new Error('superseded'); e.cancelled = true; throw e; } job = w.job; return w.job.promise; }).then(r => {
      if (tok !== runTok) return;
      job = null; prog.set(1);
      const ctxv = { venue: s.v, source: 'in-browser simulation', batFirst: s.batFirst, conditions: s.conditions, orders: { A: s.A.order, B: s.B.order } };
      const M = I.fromRaw(r.main, s.a, s.b, ctxv);
      if (needBase) baseCache.set(bkey, I.fromRaw(r.base, s.a, s.b, { venue: s.v, orders: { A: s.a.order, B: s.b.order } }));
      if (!changed) baseCache.set(bkey, M);
      last = { s, M };
      const secs = (performance.now() - t0) / 1000;
      status.textContent = `${F.int(M.n)} matches in ${F.num(secs, 1)} s.`;
      I.simLast = { M, base: changed ? baseCache.get(bkey) : null, params, seconds: secs, state: s };
      drawResults(s, M, changed ? baseCache.get(bkey) : null);
      if (fromUser === true && innerWidth < 980) right.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }).catch(e => { job = null; if (e && e.cancelled) return; status.textContent = ''; res.innerHTML = ''; res.append(S.errorEl(e, 'Simulation failed')); });
  }
  function drawResults(s, M, base) {
    res.innerHTML = '';
    const vk = s.v === s.a.home_venue ? 'A' : s.v === s.b.home_venue ? 'B' : s.v === 'neutral' ? 'n' : null;
    if (!base && vk) {
      const ref = I.preMatch(s.a, s.b, vk);
      if (ref) {
        const n2 = ref.n || 10000, zW = (M.pWinA - ref.pWinA) / Math.sqrt(M.pWinA * (1 - M.pWinA) * (1 / M.n + 1 / n2));
        const msg = ref.neutralOnly ? `Precomputed (matchups.json neutral, ${F.int(ref.n)} sims): ${s.a.short} win ${F.pct(ref.pWinA, 1)}, runs ${F.num(ref.runsA, 1)}–${F.num(ref.runsB, 1)}. This run: ${F.spct(M.pWinA - ref.pWinA, 1)} (z ${F.signed(zW, 1)}).`
          : (() => { const zT = (M.A.total.mean - ref.A.total.mean) / (M.A.total.sd * Math.sqrt(1 / M.n + 1 / n2)); return `Precomputed (matchups.json, ${F.int(ref.n)} sims): ${s.a.short} win ${F.pct(ref.pWinA, 1)}, ${s.a.short} total ${F.num(ref.A.total.mean, 1)}, ${s.b.short} total ${F.num(ref.B.total.mean, 1)}. This run differs by ${F.spct(M.pWinA - ref.pWinA, 1)} (z ${F.signed(zW, 1)}) and ${F.signed(M.A.total.mean - ref.A.total.mean, 1)} runs (z ${F.signed(zT, 1)}); |z| below 2 is Monte Carlo noise.`; })();
        res.append(h('div', { class: 'sh-note ip-ref', text: msg }));
      }
    }
    const gv = h('div', { class: 'sh-section ip-gap' }); res.append(gv);
    const desc = ['A', 'B'].map(k => { const sd = s[k]; if (sideDefault(sd)) return null; const outs = sd.t.xii.filter(id => !sd.xii.includes(id)).map(I.pname), ins = sd.xii.filter(id => !sd.t.xii.includes(id)).map(I.pname); return `${sd.t.short}: ${[outs.length ? 'out ' + outs.join(', ') : '', ins.length ? 'in ' + ins.join(', ') : '', sd.order.join() !== sd.t.order.join() && !outs.length ? 'batting order changed' : '', planStr(sd.plan) !== planStr(sd.t.plan) ? 'bowling plan changed' : ''].filter(Boolean).join('; ')}`; }).filter(Boolean).join('. ');
    I.renderMatch(gv, M, { base, context: desc ? desc + '.' : '', baseNote: `Default = both default XIs and bowling plans at ${s.v === 'neutral' ? 'a neutral ground' : I.venueName(s.v)}, toss unknown, normal pitch and dew, run with the same seeds (common random numbers). ± is 1 SE treating the runs as independent, so it overstates the noise in the difference.` });
  }
  drawControls();
  sheet.onState(() => { drawControls(); go(); });
  go();
}
function loadSimJs() {
  if (window.IPLSim) return Promise.resolve();
  return new Promise((res, rej) => { const s = document.createElement('script'); s.src = 'sim.js'; s.onload = res; s.onerror = () => rej(new Error('Could not load sim.js')); document.head.append(s); });
}

/* ───────── Venues ───────── */
async function venues(panel, sheet) {
  const V = await I.loadVenues(); await I.loadTeams();
  const homes = new Set(D.teams.map(t => t.home_venue));
  const rows = V.venues.map(v => Object.assign({ _home: D.teams.filter(t => t.home_venue === v.venue).map(t => t.short).join(' ') }, v));
  const ipl = rows.filter(v => v.ipl_matches >= 10 && v.last_match >= '2019');
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  const c1 = I.card(cols, 'Runs and wickets by ground', 'Venue effects in IPL 2024–26 conditions, relative to an average ground (1.00). Right = more runs per over, up = more wickets per over. IPL grounds with ≥10 IPL matches since 2019; current home grounds labelled.');
  S.scatter(c1.appendChild(h('div')), { points: ipl.map(v => ({ x: v.all_rpo_mult, y: v.all_wpo_mult, label: v._home || v.name.split(',')[0], id: v.venue, group: v._home ? 'Home ground' : 'Other IPL ground', desc: `${v.name}${v.name_raw && v.name_raw !== v.name ? ' (' + v.name_raw + ')' : ''}: ${F.num(v.all_rpo, 2)} runs/over, ±${F.num(v.all_rpo_mult_sd, 3)} (SD of runs multiplier); ${v.ipl_matches} IPL matches` })), groups: ['Home ground', 'Other IPL ground'], labels: ipl.filter(v => v._home).map(v => v._home), xLabel: 'runs per over vs average', yLabel: 'wickets per over vs average', xFmt: 'num:2', yFmt: 'num:2', refX: 1, refY: 1, height: 260 });
  const c2 = I.card(cols, 'Chasing, pace and spin at the home grounds', 'Chase effect = 2nd-innings run rate ÷ 1st-innings run rate at this ground, relative to the average ground (>1: batting second is easier, e.g. dew). Spin − pace = spin runs multiplier minus pace runs multiplier (negative: spin is relatively harder to score off here).');
  const hr = rows.filter(v => homes.has(v.venue));
  S.bar(c2.appendChild(h('div')), { title: 'Chase effect', data: hr.map(v => ({ label: `${v._home} · ${v.city || v.name.split(',')[0]}`, value: v.inn2_rpo_mult / v.inn1_rpo_mult - 1, desc: `2nd ${F.num(v.inn2_rpo, 2)} vs 1st ${F.num(v.inn1_rpo, 2)} runs/over` })), sort: 'desc', fmt: 'spct:1', center: 0, barHeight: 10, rowGap: 5 });
  S.bar(c2.appendChild(h('div', { style: { marginTop: '10px' } })), { title: 'Spin − pace (runs multiplier)', data: hr.map(v => ({ label: `${v._home} · ${v.city || v.name.split(',')[0]}`, value: v.spin_rpo_mult - v.pace_rpo_mult, desc: `spin ${F.num(v.spin_rpo_mult, 3)}, pace ${F.num(v.pace_rpo_mult, 3)}; spin wickets ×${F.num(v.spin_wpo_mult, 3)}` })), sort: 'desc', fmt: 'signed:3', center: 0, barHeight: 10, rowGap: 5 });
  const gc = h('div', { class: 'sh-section' }); panel.append(gc);
  gc.append(h('div', { class: 'sh-h', text: 'Every ground in the simulator' }), h('div', { class: 'sh-note', text: `${rows.length} grounds with ≥5 matches and one since 2018. Multipliers are ratios to an average ground (${F.num(V.neutral_reference.all.rpo, 2)} runs, ${F.num(V.neutral_reference.all.wpo, 3)} wickets per over); blue = above average. Shrunk toward 1 for small samples.` }));
  const m = (k, lab, desc) => ({ key: k, label: lab, get: get(k), fmt: 'num:3', heat: { center: 1, domain: [0.85, 1.15] }, desc });
  sheet.grid(gc, { height: 520, rows, sort: '-ipl_matches', csv: 'ipl-venues.csv', searchPlaceholder: 'Search ground or city', footer: false,
    columns: [
      { key: 'name', label: 'Ground', frozen: true, width: 210, desc: 'Current ground name.' }, { key: 'name_raw', label: 'Name in data', type: 'text', width: 180, hidden: true, desc: 'Most common spelling in the cricsheet data (older names, e.g. Feroz Shah Kotla).' }, { key: 'city', label: 'City', type: 'text', width: 100 }, { key: '_home', label: 'Home of', type: 'text', width: 64 },
      { key: 'matches', label: 'Matches', fmt: 'int', desc: 'All T20 matches in the data.' }, { key: 'ipl_matches', label: 'IPL', fmt: 'int', desc: 'IPL matches.' }, { key: 'last_match', label: 'Last', type: 'text', width: 100 },
      { key: 'all_rpo', label: 'Runs/over', fmt: 'num:2', desc: 'Runs per over here in IPL 2024–26 conditions.' },
      m('all_rpo_mult', 'Runs ×', 'Runs per over relative to an average ground.'), { key: 'all_rpo_mult_sd', label: '± Runs', fmt: 'num:3', desc: 'Posterior SD of the runs multiplier.' },
      m('all_wpo_mult', 'Wkts ×', 'Wickets per over (incl. run outs) vs average.'), m('all_fpo_mult', 'Fours ×', 'Fours per over vs average.'), m('all_spo_mult', 'Sixes ×', 'Sixes per over vs average.'),
      m('pace_rpo_mult', 'Pace runs ×', 'Runs per over off pace vs average.'), m('spin_rpo_mult', 'Spin runs ×', 'Runs per over off spin vs average.'),
      m('pace_wpo_mult', 'Pace wkts ×', 'Pace wickets per over vs average.'), m('spin_wpo_mult', 'Spin wkts ×', 'Spin wickets per over vs average (>1: spinners take more wickets here).'),
      { key: 'chase', label: 'Chase ×', get: v => v.inn2_rpo_mult / v.inn1_rpo_mult, fmt: 'num:3', heat: { center: 1, domain: [0.93, 1.07] }, desc: '2nd-innings runs multiplier ÷ 1st-innings: >1 = batting second is easier here.' },
    ] });
}

/* ───────── Leagues ───────── */
async function leagues(panel, sheet) {
  const L = await I.loadLeagues();
  const rows = (L.leagues || []).slice().sort((a, b) => b.strength_vs_ipl - a.strength_vs_ipl);
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  const c1 = I.card(cols, 'How strong is each league?', 'Runs per 20 overs that the league\'s average batter and bowler (who played there since 2023) are worse than the IPL\'s, both evaluated in IPL conditions. A batter\'s runs elsewhere count on the IPL scale through this gap: the model fits leagues and players jointly, so form in a −40 league is discounted heavily.');
  S.bar(c1.appendChild(h('div')), { data: rows.filter(r => r.comp !== 'IPL').map(r => ({ label: r.name.replace(/ \(.*\)/, ''), value: r.strength_vs_ipl, desc: `batting ${F.signed(r.bat_runs_vs_ipl, 1)}, bowling ${F.signed(r.bowl_runs_vs_ipl, 1)} per 20 overs; ${F.int(r.balls)} balls since 2023` })), fmt: 'signed:0', barHeight: 10, rowGap: 5 });
  const c2 = I.card(cols, 'Batting gap vs bowling gap', 'Runs per 20 overs vs the IPL. Left = weaker batters, down = weaker bowlers.');
  S.scatter(c2.appendChild(h('div')), { points: rows.filter(r => r.comp !== 'IPL').map(r => ({ x: r.bat_runs_vs_ipl, y: r.bowl_runs_vs_ipl, label: r.comp, desc: r.name })), labels: 10, xLabel: 'batting gap, runs / 20 ov', yLabel: 'bowling gap, runs / 20 ov', xFmt: 'num:0', yFmt: 'num:0', refX: 0, refY: 0, height: 260 });
  const gc = h('div', { class: 'sh-section' }); panel.append(gc);
  gc.append(h('div', { class: 'sh-h', text: 'League table' }), h('div', { class: 'sh-note', text: '"Average batter" columns are the league\'s average batter evaluated in IPL conditions; "environment" is the league\'s own run rate in its latest season (pitches, grounds, ball).' }));
  sheet.grid(gc, { height: 'auto', rows, sort: '-strength_vs_ipl', csv: 'ipl-leagues.csv', footer: false, search: false, chips: false,
    columns: [
      { key: 'comp', label: 'Code', frozen: true, width: 62 }, { key: 'name', label: 'League', type: 'text', width: 230 }, { key: 'tier', label: 'Tier', type: 'cat', get: r => I.TIER_LABEL[r.tier] || r.tier, width: 150 },
      { key: 'strength_vs_ipl', label: 'Strength', fmt: 'signed:1', heat: { center: 0 }, desc: 'Batting + bowling gap, runs per 20 overs vs the IPL (IPL = 0).' },
      { key: 'bat_runs_vs_ipl', label: 'Bat gap', fmt: 'signed:1', desc: 'Runs per 120 balls the league\'s average batter scores vs the IPL\'s average batter, in IPL conditions.' },
      { key: 'bowl_runs_vs_ipl', label: 'Bowl gap', fmt: 'signed:1', desc: 'Runs saved per 20 overs by the league\'s average bowler vs the IPL\'s (negative = weaker).' },
      { key: 'bat_sr', label: 'Avg bat SR', fmt: 'num:1', desc: 'The league\'s average batter in IPL conditions.' }, { key: 'bat_out_pct', label: 'Out/100', fmt: 'num:2' },
      { key: 'bowl_econ', label: 'Avg bowl econ', fmt: 'num:2', desc: 'The league\'s average bowler in IPL conditions (higher = weaker).' }, { key: 'bowl_wkt_pct', label: 'Wkt/100', fmt: 'num:2' },
      { key: 'env_runs_per_over', label: 'Env runs/over', fmt: 'num:2', desc: 'The league\'s own run environment, latest season.' }, { key: 'env_wkt_pct', label: 'Env wkt/100', fmt: 'num:2' },
      { key: 'balls', label: 'Balls', fmt: 'int', desc: 'Deliveries since 2023.' }, { key: 'matches', label: 'Matches', fmt: 'int', desc: 'Matches since 2023.' }, { key: 'last_season', label: 'Last', type: 'text', width: 70 },
    ] });
}

/* ───────── Player value ───────── */
async function value(panel, sheet) {
  await I.loadPlayers(); I.loadMatchups().catch(() => null);
  const rows = D.players.filter(p => p._team).map(p => ({ p, inXI: p._team.xii.includes(p.id) }));
  const cols = h('div', { class: 'sh-cols' }); panel.append(cols);
  const c1 = I.card(cols, 'Biggest losses if replaced', 'Win probability per match his team gives up if he is swapped for a replacement-level player of his role (batting in his slot + bowling at his projected overs, converted at ' + F.pct(D.P.runs_to_wp, 2) + ' per run). Players in a default 12.');
  const top = rows.filter(r => r.inXI).sort((a, b) => b.p.varp_wp - a.p.varp_wp).slice(0, 20);
  S.bar(c1.appendChild(h('div')), { data: top.map(r => ({ label: `${r.p.name} (${r.p._team.short})`, value: r.p.varp_wp, id: r.p.id, desc: `${F.signed(r.p.varp_runs, 1)} runs per match` })), fmt: 'pct:1', diverging: false, valueLabel: 'win probability per match', barHeight: 10, rowGap: 5, onClick: d => I.playerCard(d.id, { nav: { prev() {}, next() {} } }) });
  const c2 = I.card(cols, 'Batting value vs bowling value', 'Runs per match above replacement. All-rounders sit up and to the right. Default-12 players.');
  S.scatter(c2.appendChild(h('div')), { points: rows.filter(r => r.inXI).map(r => ({ x: r.p.bat ? r.p.bat.value.varp_runs : 0, y: r.p.bowl ? r.p.bowl.value.varp_runs : 0, label: r.p.name, id: r.p.id, desc: r.p._team.short })), xLabel: 'batting value', yLabel: 'bowling value', xFmt: 'num:0', yFmt: 'num:0', refX: 0, refY: 0, labels: 8, height: 280, onClick: pt => I.playerCard(pt.id, { nav: { prev() {}, next() {} } }) });
  const gc = h('div', { class: 'sh-section' }); panel.append(gc);
  gc.append(h('div', { class: 'sh-h', text: 'Every squad player' }), h('div', { class: 'sh-note', text: 'Value is measured against a replacement-level player of the same role, not against his team\'s actual next man up. "Simulate" opens the simulator with him replaced by the best unused squad player of his kind, so the full ball-by-ball knock-ons (batting order, bowling overs) are included.' }));
  sheet.grid(gc, { height: 520, rows, sort: '-wp', csv: 'ipl-player-value.csv', searchPlaceholder: 'Search player or team', footer: false,
    onRowClick: r => I.playerCard(r.p, { nav: { prev() {}, next() {} } }),
    columns: [
      { key: 'name', label: 'Player', frozen: true, width: 160, get: r => r.p.name }, { key: 'team', label: 'Team', type: 'cat', get: r => r.p._team.short, width: 58 },
      { key: 'xi', label: 'In 12', type: 'cat', get: r => r.inXI ? 'Yes' : '', width: 56, desc: 'In the default XI + Impact Player.' },
      { key: 'wp', label: 'Win%/m', get: r => r.p.varp_wp, fmt: 'spct:2', heat: { center: 0 }, desc: 'Win probability per match above replacement (batting + bowling).' },
      { key: 'rm', label: 'Runs/m', get: r => r.p.varp_runs, fmt: 'signed:1', heat: { center: 0 }, desc: 'Runs per match above replacement.' },
      { key: 'bv', label: 'Bat', get: r => r.p.bat ? r.p.bat.value.varp_runs : null, fmt: 'signed:1', desc: 'Batting value, runs per match, in his slot.' },
      { key: 'wv', label: 'Bowl', get: r => r.p.bowl ? r.p.bowl.value.varp_runs : null, fmt: 'signed:1', desc: 'Bowling value, runs per match, at his projected overs (0 for non-bowlers).' },
      { key: 'eo', label: 'Proj ov', get: r => r.p.bowl ? r.p.bowl.value.exp_overs : null, fmt: 'num:1', desc: 'Projected overs per match in his current role, used for bowling value.' },
      { key: 'slot', label: 'Slot', get: r => r.p.bat ? r.p.bat.value.slot : null, fmt: 'int' },
      { key: 'sim', label: 'Simulate', get: r => r.p.id, fmt: 'text', filter: false, render: (v, r) => { if (!r.inXI) return ''; const t = r.p._team, opp = D.teams.find(x => x !== t && x.rating.rank === (t.rating.rank === 1 ? 2 : 1)) || D.teams.find(x => x !== t); return `<a href="${I.hashFor('sim', simOutHash(t, opp, r.p.id))}">without him</a>`; }, width: 90, desc: 'Run the full simulator with him replaced.' },
    ] });
}

/* ───────── Diagnostics ───────── */
const CLS_LABEL = { wide: 'Wide', noball: 'No-ball', byes: 'Byes / leg-byes', wicket: 'Bowler wicket', runout: 'Run out', r0: 'Dot', r1: 'Single', r2: 'Two', r3: 'Three', r4: 'Four', r6: 'Six' };
async function diagnostics(panel, sheet) {
  const Dg = await I.loadDiag();
  const sec = (title, note) => { panel.append(h('div', { class: 'ip-sec' }, h('div', { class: 'sh-h ip-sech', text: title }), note ? h('div', { class: 'sh-note', text: note }) : null)); const c = h('div', { class: 'sh-cols' }); panel.append(c); return c; };
  const ho = Dg.holdout || {};
  const c1 = sec('Out of sample: ball-by-ball predictions', `Fitted only on deliveries before ${ho.cutoff || 'the cutoff'}, then scored on everything after (IPL 2025 and 2026 included). This checks fit quality, not betting performance; nothing here uses market prices.`);
  ['ipl', 'all'].forEach(sc => {
    const o = ho[sc]; if (!o) return;
    const gain = (o.logloss_marginal - o.logloss) / o.logloss_marginal;
    const dR = o.innings_runs_actual - o.innings_runs_expected;
    const cm = Object.entries(o.classes || {}).filter(([k]) => ['wicket', 'r0', 'r1', 'r4', 'r6', 'wide'].includes(k)).map(([k, v]) => [k, v.obs_rate / v.mean_pred]).sort((x, y) => Math.abs(y[1] - 1) - Math.abs(x[1] - 1)).filter(x => Math.abs(x[1] - 1) > 0.04);
    const cmTxt = cm.length ? ' By outcome: ' + cm.slice(0, 2).map(([k, r]) => `${(CLS_LABEL[k] || k).toLowerCase()}s came ${F.pct(Math.abs(r - 1), 0)} ${r > 1 ? 'more' : 'less'} often than predicted`).join(', ') + '.' : '';
    const c = I.card(c1, sc === 'ipl' ? 'IPL deliveries after the cutoff' : 'All T20 deliveries after the cutoff', `${F.int(o.n_balls)} balls. Log-loss ${F.num(o.logloss, 4)} vs ${F.num(o.logloss_marginal, 4)} for plain outcome frequencies (${F.pct(gain, 1)} better). ${Math.abs(dR) > 2 ? `Where it misses: real innings scored ${F.signed(dR, 1)} runs vs the model's expectation (${F.num(o.innings_runs_actual, 1)} vs ${F.num(o.innings_runs_expected, 1)}), because a season the model has not seen is played at its league's previous run environment.` : `Innings runs: ${F.num(o.innings_runs_actual, 1)} real vs ${F.num(o.innings_runs_expected, 1)} expected.`}${cmTxt}`);
    c.append(S.tiles([{ label: 'Log-loss', value: F.num(o.logloss, 4), sub: 'no skill ' + F.num(o.logloss_marginal, 4) }, { label: 'Runs / innings', value: F.num(o.innings_runs_actual, 1), sub: 'expected ' + F.num(o.innings_runs_expected, 1) }, { label: 'Wkts / innings', value: F.num(o.innings_wkts_actual, 2), sub: 'expected ' + F.num(o.innings_wkts_expected, 2) }]));
    const cl = o.classes || {};
    S.table(c.appendChild(h('div', { style: { marginTop: '8px' } })), [{ key: 'k', label: 'Outcome' }, { key: 'mean_pred', label: 'Predicted', fmt: 'pct:2' }, { key: 'obs_rate', label: 'Observed', fmt: 'pct:2' }, { key: 'r', label: 'Obs / pred', get: r => r.obs_rate / r.mean_pred, fmt: 'num:3' }],
      Object.keys(cl).map(k => Object.assign({ k: CLS_LABEL[k] || k }, cl[k])));
  });
  const ip = ho.ipl || ho.all;
  if (ip && ip.classes) {
    const c = I.card(c1, 'Reliability by outcome', 'Deliveries sorted into tenths by predicted probability; each dot is a tenth. On the diagonal = the predicted rates come true. ' + relSentence(ip.classes));
    c.classList.add('ip-wide');
    const ctl = h('div'), ch = h('div'); c.append(ctl, ch);
    let scope = ho.ipl ? 'ipl' : 'all';
    const draw = () => {
      ch.innerHTML = '';
      const cls = ho[scope].classes, keys = ['wicket', 'r4', 'r6', 'r0', 'r1', 'wide'];
      const grid = h('div', { class: 'ip-mgrid' }); ch.append(grid);
      keys.filter(k => cls[k] && cls[k].bins).forEach(k => { const b = cls[k].bins, box = h('div'); grid.append(box); S.scatter(box, { title: CLS_LABEL[k], points: b.pred.map((x, i) => ({ x, y: b.obs[i], label: '', desc: `${F.int(b.n[i])} balls: predicted ${F.pct(x, 2)}, observed ${F.pct(b.obs[i], 2)}` })), diag: true, xFmt: 'pct:0', yFmt: 'pct:0', xLabel: 'predicted', yLabel: 'observed', labels: false, height: 140 }); });
    };
    ctl.append(S.ui.segmented({ label: 'Deliveries', options: [{ value: 'ipl', label: 'IPL' }, { value: 'all', label: 'All T20' }].filter(o => ho[o.value]), value: scope, onChange: v => { scope = v; draw(); } }));
    draw();
  }
  if (Array.isArray(Dg.tuning) && Dg.tuning.length) {
    const tu = Dg.tuning, base = tu.find(t => t.lam && t.lam.bat >= 1e8), best = tu.slice().sort((a, b) => a.ll_ipl - b.ll_ipl)[0];
    const c = I.card(c1, 'Tuning: what player skill adds', `Every holdout fit tried. The no-player-skill baseline (all players average) scores ${base ? F.num(base.ll_ipl, 4) : '–'} on IPL balls; the best fit ${F.num(best.ll_ipl, 4)}. Player ratings carry real signal, but single deliveries are mostly noise, so the gain looks small in log-loss.`);
    S.table(c.appendChild(h('div')), [{ key: 'half_life', label: 'Half-life (yrs)', fmt: 'num:1' }, { key: 'b', label: 'Player penalty', get: r => r.lam && r.lam.bat >= 1e8 ? 'no skill' : r.lam ? F.num(r.lam.bat, 0) : '' }, { key: 'sp', label: 'Split penalty', get: r => r.lam && r.lam.bat >= 1e8 ? '' : r.lam ? F.num(r.lam.bat_split, 0) : '' }, { key: 'iters', label: 'Iters', fmt: 'int' }, { key: 'll_ipl', label: 'IPL log-loss', fmt: 'num:4' }, { key: 'll_all', label: 'All log-loss', fmt: 'num:4' }],
      tu.slice().sort((a, b) => a.ll_ipl - b.ll_ipl), { highlight: r => r === best });
    c.classList.add('ip-wide');
  }
  round2Diag(panel, Dg, sec);
  if ((Dg.replay && Dg.replay.margin) || (Dg.oos && Dg.oos.margin)) {
    const cm = sec('Winning margins: simulated vs real', 'How the simulator\'s margins compare with real IPL matches: runs margins when the side batting first wins, wickets and balls to spare when the chaser wins, and how far losing chases fall short by target. These back the Winning-margin markets on the Match sheet.');
    cm.parentNode && (cm.id = 'diag-margins');
    if (Dg.replay && Dg.replay.margin) marginCal(cm, Dg.replay.margin, `In-sample replay, IPL ${(Dg.replay.margin.seasons || []).length ? Dg.replay.margin.seasons[0] + '–' + String(Dg.replay.margin.seasons.slice(-1)[0]).slice(2) : ''}`);
    if (Dg.oos && Dg.oos.margin) marginCal(cm, Dg.oos.margin, `Out of sample, IPL ${Dg.oos.margin.season || 2026}`);
  }
  const rp = Dg.replay;
  if (rp) {
    const c2 = sec(`In-sample: re-simulating real ${rp.seasons ? rp.seasons.join(' and ') : ''} matches`, `${F.int(rp.matches)} IPL matches re-simulated ${F.int(rp.sims_per_match)} times each with the XIs, orders and venues that actually happened. The ratings were fitted on these matches, so this checks the simulator's mechanics, not forecasting skill.`);
    const rows = rp.rows || [];
    const big = rows.map(r => ({ r, z: (r.sim_mean - r.actual_mean) / (r.actual_sd / Math.sqrt(rp.matches)) })).sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
    const c = I.card(c2, 'Simulated vs real, per innings', 'Where it misses: ' + big.filter(x => Math.abs(x.z) > 1.5).slice(0, 3).map(x => `${x.r.metric.toLowerCase()} ${F.signed(x.r.sim_mean - x.r.actual_mean, x.r.actual_mean < 1.5 ? 3 : 1)}${x.r.actual_mean < 1.5 ? '' : ''} (sim ${F.num(x.r.sim_mean, x.r.actual_mean < 1.5 ? 3 : 1)} vs real ${F.num(x.r.actual_mean, x.r.actual_mean < 1.5 ? 3 : 1)})`).join('; ') + (rows.find(r => /2nd-innings total/.test(r.metric)) ? `. The simulated second innings is also too tightly spread (SD ${F.num(rows.find(r => /2nd-innings total/.test(r.metric)).sim_sd, 1)} vs ${F.num(rows.find(r => /2nd-innings total/.test(r.metric)).actual_sd, 1)}), so wide chase-total lines are priced short.` : '.'));
    c.classList.add('ip-wide');
    S.table(c.appendChild(h('div')), [{ key: 'metric', label: 'Measure' }, { key: 'actual_mean', label: 'Real', render: (v, r) => /rate/i.test(r.metric) ? F.pct(v, 1) : F.num(v, 2) }, { key: 'sim_mean', label: 'Sim', render: (v, r) => /rate/i.test(r.metric) ? F.pct(v, 1) : F.num(v, 2) }, { key: 'd', label: 'Sim − real', render: (v, r) => /rate/i.test(r.metric) ? F.spct(r.sim_mean - r.actual_mean, 1) : F.signed(r.sim_mean - r.actual_mean, 2) }, { key: 'actual_sd', label: 'Real SD', fmt: 'num:1' }, { key: 'sim_sd', label: 'Sim SD', fmt: 'num:1' }, { key: 'z', label: 'z', get: r => (r.sim_mean - r.actual_mean) / (r.actual_sd / Math.sqrt(rp.matches)), fmt: 'signed:1', desc: 'Difference in standard errors of the real mean' }], rows);
    if (rp.individual && rp.individual.sim) {
      const iv = rp.individual, ks = [['mean', 'Mean runs per batting innings', 'num:1'], ['duck_pct', 'Ducks, % of innings', 'num:1'], ['ge30_pct', '30+, % of innings', 'num:1'], ['ge50_pct', '50+, % of innings', 'num:1']];
      const d50 = iv.sim.ge50_pct - iv.actual.ge50_pct, d30 = iv.sim.ge30_pct - iv.actual.ge30_pct;
      const ci = I.card(c2, 'Individual batting innings', `${F.int(iv.n_actual)} real innings. Simulated batters reach 30 ${F.num(Math.abs(d30), 1)} points ${d30 < 0 ? 'less' : 'more'} often and 50 ${F.num(Math.abs(d50), 1)} points ${d50 < 0 ? 'less' : 'more'} often than real ones${d30 < -0.8 ? ', so batter milestone overs (30+, 50+) are priced slightly low' : ''}.`);
      S.table(ci.appendChild(h('div')), [{ key: 'l', label: 'Measure' }, { key: 'a', label: 'Real', fmt: 'num:1' }, { key: 's', label: 'Sim', fmt: 'num:1' }, { key: 'd', label: 'Sim − real', get: r => r.s - r.a, fmt: 'signed:1' }], ks.map(([k, l]) => ({ l, a: iv.actual[k], s: iv.sim[k] })));
    }
    const th = rp.t1_hist;
    if (th && th.edges) {
      const ct = I.card(c2, 'First-innings totals: real vs simulated', `Share of first innings per 10-run bin. With only ${F.int(rp.matches)} real innings the real curve is lumpy; the simulated shape and centre match, and the real tails are no wider than simulated.`);
      const mid = th.edges.slice(0, -1).map((e, i) => (e + th.edges[i + 1]) / 2);
      S.line(ct.appendChild(h('div')), { series: [{ name: 'Real', points: mid.map((x, i) => [x, th.actual[i]]) }, { name: 'Simulated', points: mid.map((x, i) => [x, th.sim[i]]) }], xLabel: 'first-innings total', yFmt: 'pct:0', height: 180 });
    }
  }
  if (rp && (rp.players || rp.phase || rp.match)) {
    const c4 = sec('In-sample: players, phases and matches', 'The same 2025–26 replay, broken down. In-sample, so these check the simulator mechanics.');
    if (rp.match) matchCal(c4, rp.match, 'Replay, match level');
    if (rp.phase) phaseCal(c4, rp.phase, 'Replay, runs by phase');
    if (rp.players) playerCal(c4, rp.players, 'Replay, player lines');
  }
  const known = ['holdout', 'tuning', 'replay', 'oos', 'match_shock', 'holdout_final'];
  const extra = Object.keys(Dg).filter(k => !known.includes(k) && !/^tuning_round\d+$/.test(k));
  if (extra.length) { const c3 = sec('Further checks', 'Added by a later model export; shown as exported.'); extra.forEach(k => genericDiag(c3, k, Dg[k])); }
  const jump = () => { if (sheet && sheet.get('s') === 'margins') { const t = panel.querySelector('#diag-margins'); if (t && t.previousElementSibling) panel.scrollTop = t.previousElementSibling.offsetTop - 10; } };
  requestAnimationFrame(jump); if (sheet) sheet.onState(jump);
}
const T2 = x => typeof x === 'number' && isFinite(x);
function round2Diag(panel, Dg, sec) {
  const oo = Dg.oos;
  if (oo) {
    const c = sec(`Out of sample: IPL ${oo.season || 2026} matches`, `A model fitted only on data before ${oo.model_cutoff}, re-simulating every IPL ${oo.season} match ${F.int(oo.sims_per_match)} times with the real XIs, ground and batting-first side. ${oo.env_note || ''}. No market prices are used.`);
    if (oo.match) matchCal(c, oo.match, 'Win probability and totals');
    if (Array.isArray(oo.rows)) {
      const rows = oo.rows, pp = rows.find(r => /1st-innings powerplay/i.test(r.metric)), i2 = rows.find(r => /2nd-innings total/i.test(r.metric));
      const cc = I.card(c, 'Simulated vs real per innings, 2026', [pp ? `First-innings powerplay runs ${F.signed(pp.sim_mean - pp.actual_mean, 1)} (sim ${F.num(pp.sim_mean, 1)} vs real ${F.num(pp.actual_mean, 1)}).` : '', i2 ? `Second-innings totals are too tightly spread: SD ${F.num(i2.sim_sd, 1)} simulated vs ${F.num(i2.actual_sd, 1)} real, so wide chase-total lines are priced short.` : ''].join(' '));
      cc.classList.add('ip-wide');
      replayTable(cc, rows, oo.match && oo.match.n_matches);
    }
    if (oo.phase) phaseCal(c, oo.phase, 'Runs and wickets by phase, 2026');
    if (oo.players) playerCal(c, oo.players, 'Player lines, 2026');
    const sh = oo.shrinkage_calibration;
    if (sh) {
      const cs = I.card(c, 'Are the player ratings too extreme?', 'Slope of each player\'s actual deviation from an average IPL batter/bowler in 2026 on the predicted deviation, by how much he had played before the cutoff. 1 = right size; below 1 = ratings too extreme; above 1 = too timid. Dismissal slopes well below 1 mean the out-rate splits are over-stretched for small samples.');
      cs.classList.add('ip-wide');
      const g = h('div', { class: 'ip-two ip-two-wide' }); cs.append(g);
      const t1 = h('div'), t2 = h('div'); g.append(t1, t2);
      if (sh.bat) { t1.append(h('div', { class: 'ip-sub', text: 'Batters' })); S.table(t1.appendChild(h('div')), [{ key: 'bucket', label: 'Balls before' }, { key: 'n_players', label: 'Players', fmt: 'int' }, { key: 'test_balls', label: 'Test balls', fmt: 'int' }, { key: 'slope_runs', label: 'Runs slope', fmt: 'num:2' }, { key: 'slope_outs', label: 'Outs slope', fmt: 'num:2' }, { key: 'top20_pred_runs_per100', label: 'Top-20 pred', fmt: 'signed:1', desc: 'runs per 100 balls vs average, the 20 best-rated' }, { key: 'top20_act_runs_per100', label: 'Top-20 act', fmt: 'signed:1' }], sh.bat); }
      if (sh.bowl) { t2.append(h('div', { class: 'ip-sub', text: 'Bowlers' })); S.table(t2.appendChild(h('div')), [{ key: 'bucket', label: 'Balls before' }, { key: 'n_players', label: 'Players', fmt: 'int' }, { key: 'test_balls', label: 'Test balls', fmt: 'int' }, { key: 'slope_conceded', label: 'Conceded slope', fmt: 'num:2' }, { key: 'slope_wkts', label: 'Wkts slope', fmt: 'num:2' }], sh.bowl); }
    }
  }
  const rounds = Object.keys(Dg).filter(k => /^tuning_round\d+$/.test(k)).sort((x, y) => +x.match(/\d+/)[0] - +y.match(/\d+/)[0]);
  const ms = Dg.match_shock;
  if (rounds.length || ms || Dg.holdout_final) {
    const c = sec('Design choices: what was kept and rejected', 'Each model block tested on the forward holdout (fit before 1 June 2025, score everything after), and the shared match-conditions shock.');
    if (rounds.length) {
      const toks = l => { const t = String(l || '').split(';').slice(1).join(';').split(',').map(x => x.trim()).filter(Boolean); return t; };
      const lastR = Dg[rounds[rounds.length - 1]], final = new Set(toks(lastR[lastR.length - 1].label));
      const BLOCK = { bowl: 'bowler shrinkage', bat: 'batter shrinkage', bat_split: 'batter split shrinkage', bowl_split: 'bowler split shrinkage', venue: 'venue shrinkage', venue2: 'venue split shrinkage', cs: 'league-season shrinkage', bat_wkt_mult: 'heavier shrinkage of batters\' dismissal rates', bat_type: 'per-batter bowling-type splits', pair: 'batter × bowler head-to-heads', bowl_arch: 'bowler split vs middle/lower-order batters', day: 'day game (first of a double-header)', wear: 'pitch wear through the season', toss: 'toss winner chose to bat', cs_i2: 'league-season × 2nd innings environment', chase_w: 'chase pressure × wickets in hand', chase_hi: 'finer required-rate buckets above 17 an over' };
      const rows = [];
      const r1 = Array.isArray(Dg.tuning) ? Dg.tuning.filter(e => e.label).sort((x, y) => x.ll_ipl - y.ll_ipl)[0] : null;
      let prev = r1 ? toks(r1.label) : null, ref = r1 ? r1.ll_ipl : null;
      rounds.forEach(rk => {
        const R = Dg[rk]; if (!Array.isArray(R) || !R.length) return;
        const sets = R.map(e => toks(e.label));
        const P0 = prev || sets[0].filter(t => sets.every(x => x.includes(t)));
        const name = t => { const [k, v] = t.split('='); return `${BLOCK[k] || k}${v != null && !/^1$/.test(v) ? ' (' + v + ')' : ''}`; };
        R.forEach((e, i) => {
          const test = sets[i].filter(t => !P0.includes(t));
          const label = rk.replace('tuning_round', 'Round ');
          if (!test.length) { rows.push({ r: label, what: 'previous configuration, refitted', setting: sets[i].join(', '), ll: e.ll_ipl, la: e.ll_all, d: isNum(ref) ? e.ll_ipl - ref : null, dec: 'base' }); return; }
          const kept = test.every(t => final.has(t));
          rows.push({ r: label, what: test.map(name).join(' + '), setting: sets[i].join(', '), ll: e.ll_ipl, la: e.ll_all, d: isNum(ref) ? e.ll_ipl - ref : null, dec: kept ? 'kept' : 'rejected' });
        });
        const k = R.map((e, i) => [e, sets[i]]).filter(([, st]) => st.every(t => final.has(t)) && st.some(t => !P0.includes(t))).sort((x, y) => x[0].ll_ipl - y[0].ll_ipl)[0];
        if (k) { prev = k[1]; ref = k[0].ll_ipl; } else if (!prev) prev = P0;
      });
      const hf = Dg.holdout_final;
      const nk = rows.filter(r => r.dec === 'kept').length, nr = rows.filter(r => r.dec === 'rejected').length;
      const ct = I.card(c, 'Blocks tested', `${nk} kept, ${nr} rejected, from the labels in diagnostics.json (kept = the setting is in the final configuration). Log loss on balls after the cutoff, IPL only and all T20s; lower is better. Each fit is compared with the configuration kept so far (Δ IPL; negative = better on IPL balls); a block is kept only if it is in the final configuration, which also weighs all-T20 log loss and simulator realism.${hf ? ` Final configuration fitted to convergence: ${F.num(hf.ll_ipl, 5)} IPL, ${F.num(hf.ll_all, 5)} all T20s.` : ''} The gains are in the fourth decimal: single balls are mostly noise.`);
      ct.classList.add('ip-wide');
      S.table(ct.appendChild(h('div')), [{ key: 'r', label: 'Round' }, { key: 'what', label: 'Block tested', render: (v, r) => `<span title="${esc(r.setting)}">${esc(v)}</span>` }, { key: 'dec', label: 'Decision', render: v => v === 'kept' ? '<b>kept</b>' : esc(v) }, { key: 'll', label: 'IPL log-loss', fmt: 'num:5' }, { key: 'la', label: 'All log-loss', fmt: 'num:5' }, { key: 'd', label: 'Δ IPL', fmt: 'signed:5' }], rows);
    }
    if (ms) {
      const cm = I.card(c, 'Shared match conditions', `Real innings in the same match run hot or cold together (residual correlation ${F.num(ms.residual_corr, 3)} across ${F.int(ms.n_matches)} IPL matches). The simulator draws one shock per match with SD ${F.num(ms.sd, 3)} on the logit scale along the recent IPL scoring direction (${F.num(ms.runs_per_ball_per_unit, 3)} runs per ball per unit), which widens total tails and tempers win probabilities.${T2(ms.innings_sd) ? ` Each innings also draws its own shock (SD ${F.num(ms.innings_sd, 3)}), sized from the part of a single innings' residual variance that is neither shared with the other innings nor sampling noise${T2(ms.chase_sd) ? `; the chase-advantage spread behind the dew dial has SD ${F.num(ms.chase_sd, 3)}` : ''}.` : ''}`);
      cm.append(S.kv([['Shock SD (logit)', F.num(ms.sd, 3)], ['Innings shock SD', T2(ms.innings_sd) ? F.num(ms.innings_sd, 3) : '–'], ['Chase residual SD', T2(ms.chase_sd) ? F.num(ms.chase_sd, 3) : '–'], ['Residual covariance', F.num(ms.residual_cov, 4)], ['Residual correlation', F.num(ms.residual_corr, 3)], ['Runs per ball per unit', F.num(ms.runs_per_ball_per_unit, 3)], ['Matches', F.int(ms.n_matches)]]));
    }
  }
}
function marginCal(parent, m, title) {
  const S0 = m.sim || {}, A0 = m.actual || {}, lc = m.losing_chase_by_target || [];
  const big = lc.filter(r => isNum(r.sim_shortfall_mean) && isNum(r.act_shortfall_mean) && (r.act_n || 0) >= 10).sort((x, y) => Math.abs(y.sim_shortfall_mean - y.act_shortfall_mean) - Math.abs(x.sim_shortfall_mean - x.act_shortfall_mean))[0];
  const r1 = S0.bat1_win_runs || {}, a1 = A0.bat1_win_runs || {};
  const small = isNum(a1.n) && a1.n < 60;
  const c = I.card(parent, title, `${F.int(m.n_matches)} matches; ${F.int(a1.n)} real wins batting first and ${F.int((A0.bat2_win_wkts || {}).n)} real chases won.${small ? ` Only ${F.int(a1.n)} bat-first wins, so every real share here has a wide margin of error (±${F.pct(Math.sqrt(0.25 / a1.n), 0)} or so).` : ''} Batting-first winning margins: simulated median ${F.num((r1.q || [])[2], 0)} runs vs ${F.num((a1.q || [])[2], 0)} real, mean ${F.num(r1.mean, 1)} vs ${F.num(a1.mean, 1)}${isNum(r1.mean) && isNum(a1.mean) ? (r1.mean - a1.mean > 2 ? ', so the simulator\'s runs margins run wide and "win by 50+" lines are priced long' : r1.mean - a1.mean < -2 ? (small ? ', narrower than this small sample, which is within its noise' : ', so simulated runs margins run narrow') : ', close') : ''}.${big ? ` Biggest miss: losing chases of ${big.target_band} fall ${F.num(big.sim_shortfall_mean, 0)} runs short in the simulation vs ${F.num(big.act_shortfall_mean, 0)} in reality (${F.int(big.act_n)} real matches).` : ''}`);
  c.classList.add('ip-wide');
  const g = h('div', { class: 'ip-two ip-two-wide' }); c.append(g);
  const b1 = h('div'), b2 = h('div'); g.append(b1, b2);
  const bands = Object.keys(r1.bands || a1.bands || {});
  if (bands.length) { b1.append(h('div', { class: 'ip-sub', text: 'Bat-first wins: share by margin' })); S.table(b1.appendChild(h('div')), [{ key: 'b', label: 'Runs' }, { key: 's', label: 'Sim', fmt: 'pct:1' }, { key: 'a', label: 'Real', fmt: 'pct:1' }, { key: 'd', label: 'Sim − real', get: r => r.s - r.a, fmt: 'spct:1' }], bands.map(k => ({ b: k, s: (r1.bands || {})[k], a: (a1.bands || {})[k] }))); }
  const qrow = (lab, sd, ad) => sd || ad ? [{ k: lab + ' (sim)', n: sd && sd.n, m: sd && sd.mean, q: (sd && sd.q) || [] }, { k: lab + ' (real)', n: ad && ad.n, m: ad && ad.mean, q: (ad && ad.q) || [] }] : [];
  const qr = [...qrow('Runs margin, bat-first win', r1, a1), ...qrow('Wickets in hand, chase won', S0.bat2_win_wkts, A0.bat2_win_wkts), ...qrow('Balls to spare, chase won', S0.bat2_win_balls, A0.bat2_win_balls)];
  b2.append(h('div', { class: 'ip-sub', text: 'Quantiles' }));
  S.table(b2.appendChild(h('div')), [{ key: 'k', label: '' }, { key: 'm', label: 'Mean', fmt: 'num:1' }].concat([10, 25, 50, 75, 90].map((p, i) => ({ key: 'q' + p, label: p + '%', fmt: 'num:0', get: r => r.q[i] }))).concat([{ key: 'n', label: 'n', fmt: 'int' }]), qr);
  b2.append(S.kv([['Chases into the last over, sim / real', `${F.pct(S0.share_last_over, 1)} / ${F.pct(A0.share_last_over, 1)}`], ['Chasing side all out, sim / real', `${F.pct(S0.share_chase_all_out, 1)} / ${F.pct(A0.share_chase_all_out, 1)}`]].concat(isNum(S0.corr_s1_s2) ? [['Simulated correlation of the two totals', F.num(S0.corr_s1_s2, 3)]] : [])));
  if (lc.length) {
    const g2 = h('div', { class: 'ip-two ip-two-wide', style: { marginTop: '10px' } }); c.append(g2);
    const l = h('div'), r = h('div'); g2.append(l, r);
    S.line(l, { title: 'Losing chases: runs short, by target', series: [{ name: 'Real', points: lc.map((x, i) => [i, x.act_shortfall_mean]) }, { name: 'Simulated', points: lc.map((x, i) => [i, x.sim_shortfall_mean]) }], xFmt: v => Number.isInteger(v) ? (lc[v] || {}).target_band || '' : '', xLabel: 'target', yFmt: 'num:0', height: 150, zero: false });
    S.table(r, [{ key: 'target_band', label: 'Target' }, { key: 'act_shortfall_mean', label: 'Short, real', fmt: 'num:1' }, { key: 'sim_shortfall_mean', label: 'Sim', fmt: 'num:1' }, { key: 'act_all_out', label: 'All out, real', fmt: 'pct:0' }, { key: 'sim_all_out', label: 'Sim', fmt: 'pct:0' }, { key: 'act_n', label: 'Real n', fmt: 'int' }], lc);
  }
}
function replayTable(c, rows, n) {
  S.table(c.appendChild(h('div')), [{ key: 'metric', label: 'Measure' }, { key: 'actual_mean', label: 'Real', render: (v, r) => /rate/i.test(r.metric) ? F.pct(v, 1) : F.num(v, 2) }, { key: 'sim_mean', label: 'Sim', render: (v, r) => /rate/i.test(r.metric) ? F.pct(v, 1) : F.num(v, 2) }, { key: 'd', label: 'Sim − real', render: (v, r) => /rate/i.test(r.metric) ? F.spct(r.sim_mean - r.actual_mean, 1) : F.signed(r.sim_mean - r.actual_mean, 2) }, { key: 'actual_sd', label: 'Real SD', fmt: 'num:1' }, { key: 'sim_sd', label: 'Sim SD', fmt: 'num:1' }].concat(n ? [{ key: 'z', label: 'z', get: r => (r.sim_mean - r.actual_mean) / (r.actual_sd / Math.sqrt(n)), fmt: 'signed:1', desc: 'Difference in standard errors of the real mean' }] : []), rows);
}
function matchCal(parent, m, title) {
  const cv = m.t1_quantile_coverage || {}, mv = m.match_total_quantile_coverage || {};
  const qs = ['q10', 'q25', 'q50', 'q75', 'q90'].filter(q => T2(cv[q]) || T2(mv[q]));
  const worst = qs.map(q => [q, (cv[q] ?? NaN) - (+q.slice(1) / 100)]).filter(x => T2(x[1])).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
  const base = [T2(m.t1_rmse_venue_mean) ? `venue average ${F.num(m.t1_rmse_venue_mean, 1)}` : '', T2(m.t1_rmse_overall_mean) ? `league average ${F.num(m.t1_rmse_overall_mean, 1)}` : ''].filter(Boolean).join(', ');
  const c = I.card(parent, title, `${F.int(m.n_matches)} matches. Win-probability log loss ${F.num(m.wp_logloss, 3)} vs ${F.num(m.wp_logloss_coinflip, 3)} for a coin flip. First-innings total RMSE ${F.num(m.t1_rmse_model, 1)} runs${base ? ` (vs ${base})` : ''}, bias ${F.signed(m.t1_bias_model, 1)}.${worst && Math.abs(worst[1]) > 0.03 ? ` Coverage miss: ${F.pct(cv[worst[0]], 0)} of real first innings fell below the simulated ${worst[0].slice(1)}th percentile (should be ${worst[0].slice(1)}%)${worst[0] === 'q90' && worst[1] < 0 ? ', so the upper tail is too short' : ''}.` : ''} With ${F.int(m.n_matches)} matches each coverage share has a standard error of about ${F.pct(Math.sqrt(0.25 / m.n_matches), 0)}.`);
  c.classList.add('ip-wide');
  c.append(S.tiles([{ label: 'WP log loss', value: F.num(m.wp_logloss, 3), sub: 'coin flip ' + F.num(m.wp_logloss_coinflip, 3) }, { label: 'Brier', value: F.num(m.wp_brier, 3), sub: 'coin flip 0.250' }, { label: '1st-inns RMSE', value: F.num(m.t1_rmse_model, 1), sub: base || 'runs' }, { label: '1st-inns bias', value: F.signed(m.t1_bias_model, 1), sub: 'sim − real, runs' }]));
  const g = h('div', { class: 'ip-two', style: { marginTop: '8px' } }); c.append(g);
  const r = m.wp_reliability;
  if (r && r.pred) { const b1 = h('div'); g.append(b1); S.scatter(b1, { title: 'Win probability reliability', points: r.pred.map((x, i) => ({ x, y: r.obs[i], label: '', desc: `${r.n[i]} matches: predicted ${F.pct(x, 1)}, won ${F.pct(r.obs[i], 1)}` })), diag: true, xDomain: [0, 1], yDomain: [0, 1], xFmt: 'pct:0', yFmt: 'pct:0', xLabel: 'predicted', yLabel: 'actual', labels: false, height: 150 }); S.table(b1.appendChild(h('div')), [{ key: 'pred', label: 'Predicted', fmt: 'pct:1' }, { key: 'obs', label: 'Won', fmt: 'pct:1' }, { key: 'n', label: 'Matches', fmt: 'int' }], r.pred.map((x, i) => ({ pred: x, obs: r.obs[i], n: r.n[i] }))); }
  if (qs.length) { const b2 = h('div'); g.append(b2); b2.append(h('div', { class: 'ip-sub', text: 'Quantile coverage' })); S.table(b2.appendChild(h('div')), [{ key: 'q', label: 'Simulated quantile' }, { key: 't', label: '1st innings', fmt: 'pct:0' }, { key: 'm', label: 'Match total', fmt: 'pct:0' }, { key: 'want', label: 'Target', fmt: 'pct:0' }], qs.map(q => ({ q: q.slice(1) + 'th', t: cv[q], m: mv[q], want: +q.slice(1) / 100 }))); b2.append(h('div', { class: 'sh-note', text: 'Share of real totals that fell below each simulated quantile; on target = the spread is right.' })); }
}
function phaseCal(parent, ph, title) {
  const n = (ph.phase || []).length, rows = Array.from({ length: n }, (_, i) => ({ inn: ph.innings[i], ph: ['Powerplay', 'Middle', 'Death'][ph.phase[i]] || ph.phase[i], sr: ph.sim_runs[i], ar: ph.act_runs[i], sw: ph.sim_wkts[i], aw: ph.act_wkts[i] }));
  const big = rows.slice().sort((a, b) => Math.abs(b.sr - b.ar) - Math.abs(a.sr - a.ar))[0];
  const c = I.card(parent, title, big ? `Mean per innings. Largest miss: innings ${big.inn} ${String(big.ph).toLowerCase()}, ${F.signed(big.sr - big.ar, 1)} runs (sim ${F.num(big.sr, 1)} vs real ${F.num(big.ar, 1)}).` : '');
  c.classList.add('ip-wide');
  S.table(c.appendChild(h('div')), [{ key: 'inn', label: 'Inns', fmt: 'int' }, { key: 'ph', label: 'Phase' }, { key: 'ar', label: 'Runs real', fmt: 'num:1' }, { key: 'sr', label: 'Sim', fmt: 'num:1' }, { key: 'd', label: 'Sim − real', get: r => r.sr - r.ar, fmt: 'signed:1' }, { key: 'aw', label: 'Wkts real', fmt: 'num:2' }, { key: 'sw', label: 'Sim', fmt: 'num:2' }], rows);
}
const CAL_X = { runs: 'Runs', balls: 'Balls', fours: 'Fours', sixes: 'Sixes', p30: 'P(30+)', p50: 'P(50+)', pduck: 'P(duck)', wkts: 'Wickets', conceded: 'Runs conceded', overs: 'Overs', p2w: 'P(2+ wkts)' };
function playerCal(parent, P, title) {
  const bf = P.bat_fit || {}, wf = P.bowl_fit || {};
  const flag = Object.entries(Object.assign({}, bf, wf)).filter(([, v]) => v && T2(v.slope) && Math.abs(v.slope - 1) > 0.15).map(([k, v]) => `${(CAL_X[k] || k).toLowerCase()} ${F.num(v.slope, 2)}`);
  const c = I.card(parent, title, `Actual against simulated, one point per decile of the simulated value (or per batting position), ${F.int(P.bat_n)} batter-innings and ${F.int(P.bowl_n)} bowler-innings. A fit slope of 1 means the simulated differences between players are the right size.${flag.length ? ' Off target: ' + flag.join(', ') + (wf.conceded && wf.conceded.slope < 0.85 ? ' — simulated runs-conceded spread between bowlers is too wide (cheap bowlers concede more than simulated, expensive ones less), so bowler runs-conceded lines at the extremes are too far from the middle.' : '.') : ''}`);
  c.classList.add('ip-wide');
  const ctl = h('div', { class: 'ui-ctl' }), out = h('div', { class: 'ip-two ip-two-wide' }); c.append(ctl, out);
  let who = 'bat', x = 'runs', by = 'decile';
  const draw = () => {
    out.innerHTML = '';
    const src = who === 'bat' ? (by === 'pos' ? P.bat_by_position : P.bat_by_decile) : P.bowl_by_decile;
    if (!src) return;
    const k = src.bat_pos ? 'bat_pos' : 'decile', sim = src['sim_' + x], act = src['act_' + x]; if (!sim) return;
    const pct = /^p/.test(x), f = pct ? 'pct:0' : 'num:1';
    const left = h('div'), right = h('div'); out.append(left, right);
    S.scatter(left, { points: sim.map((v, i) => ({ x: v, y: act[i], label: k === 'bat_pos' ? '#' + src[k][i] : '', desc: `${k === 'bat_pos' ? 'batting position ' + src[k][i] : 'decile ' + (src[k][i] + 1)}: ${F.int(src.n[i])} innings` })), diag: true, labels: k === 'bat_pos' ? 6 : false, xFmt: f, yFmt: f, xLabel: 'simulated', yLabel: 'actual', height: 200 });
    const fit = (who === 'bat' ? bf : wf)[x];
    S.table(right, [{ key: 'g', label: k === 'bat_pos' ? 'Bat pos' : 'Decile' }, { key: 's', label: 'Sim', fmt: pct ? 'pct:1' : 'num:2' }, { key: 'a', label: 'Actual', fmt: pct ? 'pct:1' : 'num:2' }, { key: 'd', label: 'Act − sim', get: r => r.a - r.s, fmt: pct ? 'spct:1' : 'signed:2' }, { key: 'n', label: 'n', fmt: 'int' }], sim.map((v, i) => ({ g: k === 'bat_pos' ? src[k][i] : src[k][i] + 1, s: v, a: act[i], n: src.n[i] })));
    if (fit) right.append(h('div', { class: 'sh-note', text: `Fit of actual on simulated: slope ${F.num(fit.slope, 2)}, intercept ${F.signed(fit.intercept, 2)}.` }));
  };
  const xs = () => Object.keys(CAL_X).filter(k => (who === 'bat' ? P.bat_by_decile : P.bowl_by_decile) && (who === 'bat' ? P.bat_by_decile : P.bowl_by_decile)['sim_' + k]);
  const mkCtl = () => {
    ctl.innerHTML = '';
    ctl.append(S.ui.segmented({ label: 'Players', options: [{ value: 'bat', label: 'Batters' }, { value: 'bowl', label: 'Bowlers' }].filter(o => o.value === 'bat' ? P.bat_by_decile : P.bowl_by_decile), value: who, onChange: v => { who = v; x = xs()[0]; if (who === 'bowl') by = 'decile'; mkCtl(); draw(); } }));
    ctl.append(S.ui.select({ label: 'Stat', options: xs().map(k => ({ value: k, label: CAL_X[k] })), value: x, onChange: v => { x = v; draw(); } }));
    if (who === 'bat' && P.bat_by_position) ctl.append(S.ui.segmented({ label: 'Group by', options: [{ value: 'decile', label: 'Decile' }, { value: 'pos', label: 'Batting position' }], value: by, onChange: v => { by = v; draw(); } }));
    const fits = Object.entries(who === 'bat' ? bf : wf);
    if (fits.length) ctl.append(h('span', { class: 'sh-note', text: 'Slopes: ' + fits.map(([k, v]) => `${CAL_X[k] || k} ${F.num(v.slope, 2)}`).join(' · ') }));
  };
  mkCtl(); draw();
}
function relSentence(cls) {
  const worst = Object.entries(cls).filter(([k, v]) => v.bins && ['wicket', 'r0', 'r1', 'r4', 'r6', 'wide'].includes(k)).map(([k, v]) => { const i = v.bins.pred.length - 1; return [k, v.bins.obs[i] / v.bins.pred[i], v.bins.pred[i], v.bins.obs[i]]; }).sort((a, b) => Math.abs(Math.log(b[1])) - Math.abs(Math.log(a[1])))[0];
  if (!worst) return '';
  return `Largest miss in the top tenth: ${CLS_LABEL[worst[0]] || worst[0]}, predicted ${F.pct(worst[2], 1)} but observed ${F.pct(worst[3], 1)}${worst[1] < 1 ? ' (the model is too confident at the extreme)' : ' (under-predicted at the extreme)'}.`;
}
const titleCase = k => k.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
function findXY(o) {
  const keys = Object.keys(o).filter(k => Array.isArray(o[k]) && o[k].length > 1 && o[k].every(v => v == null || isNum(v)));
  const px = keys.find(k => /pred|model|sim|expected|proj|^p$|forecast/i.test(k)), py = keys.find(k => k !== px && /obs|actual|real|empirical|outcome|freq|rate/i.test(k));
  return px && py && o[px].length === o[py].length ? [px, py, keys] : null;
}
function genericDiag(parent, key, val) {
  if (val == null || typeof val !== 'object') { if (val != null) I.card(parent, titleCase(key), null).append(S.kv([[titleCase(key), String(val)]])); return; }
  const c = I.card(parent, titleCase(key), /calib|reliab/i.test(key) ? 'Predicted against observed: points on the diagonal are well calibrated.' : null);
  const body = h('div'); c.append(body);
  const asTable = arr => { const ks = [...new Set(arr.flatMap(r => Object.keys(r)))].filter(k => arr.some(r => r[k] == null || typeof r[k] !== 'object')); S.table(body.appendChild(h('div')), ks.map(k => ({ key: k, label: k, render: v => esc(isNum(v) ? (Math.abs(v) < 1 && v !== 0 ? F.num(v, 3) : F.num(v, Number.isInteger(v) ? 0 : 2)) : v ?? '') })), arr.slice(0, 40)); };
  const xy = !Array.isArray(val) && findXY(val);
  if (xy) { const [px, py, keys] = xy; S.scatter(body.appendChild(h('div')), { points: val[px].map((x, i) => ({ x, y: val[py][i], label: val.n ? 'n ' + F.int(val.n[i]) : '' })).filter(p => isNum(p.x) && isNum(p.y)), diag: true, xLabel: px, yLabel: py, labels: false, height: 200 }); asTable(val[px].map((_, i) => Object.fromEntries(keys.map(k => [k, val[k][i]])))); return; }
  if (Array.isArray(val)) {
    if (val.length && typeof val[0] === 'object') {
      const f = val[0], x2 = ['pred', 'p_pred', 'predicted', 'model', 'sim', 'sim_mean', 'proj'].find(k => isNum(f[k])), y2 = ['obs', 'actual', 'real', 'observed', 'freq', 'actual_mean'].find(k => isNum(f[k]));
      if (x2 && y2) S.scatter(body.appendChild(h('div')), { points: val.map(r => ({ x: r[x2], y: r[y2], label: r.name || r.bin || r.metric || '' })), diag: true, xLabel: x2, yLabel: y2, labels: 5, height: 220 });
      asTable(val);
    } else body.append(h('div', { class: 'sh-note', text: JSON.stringify(val).slice(0, 600) }));
    return;
  }
  const flat = [];
  for (const [k, v] of Object.entries(val)) {
    if (Array.isArray(v) && v.length && typeof v[0] === 'object') { body.append(h('div', { class: 'ip-sub', text: titleCase(k) })); asTable(v); }
    else if (v && typeof v === 'object' && !Array.isArray(v) && findXY(v)) { const sub = h('div'); body.append(h('div', { class: 'ip-sub', text: titleCase(k) }), sub); genericDiag(sub, k, v); }
    else if (v && typeof v === 'object' && !Array.isArray(v)) flat.push(...Object.entries(v).map(([k2, v2]) => [k + ' · ' + k2, v2]));
    else flat.push([k, v]);
  }
  if (flat.length) body.append(S.kv(flat.slice(0, 60).map(([k, v]) => [titleCase(k), Array.isArray(v) ? v.map(x => isNum(x) ? F.num(x, 3) : x).join(', ') : isNum(v) ? F.num(v, Math.abs(v) < 10 ? 3 : 1) : typeof v === 'object' ? JSON.stringify(v).slice(0, 200) : String(v)])));
}

/* ───────── Method ───────── */
async function method(panel) {
  const a = h('div'); panel.append(a);
  await S.loadMarkdown(a, 'data/method.md');
  const b = h('details', { class: 'ip-schema' }, h('summary', { text: 'Data files and field definitions (schema.md)' }));
  const bd = h('div'); b.append(bd); panel.append(b);
  b.addEventListener('toggle', () => { if (b.open && !bd.childElementCount) S.loadMarkdown(bd, 'data/schema.md', { idPrefix: 'schema-' }); });
}

/* ───────── workbook ───────── */
const oddsCtl = S.ui.segmented({ options: [{ value: 'american', label: 'US' }, { value: 'decimal', label: 'Dec' }], value: I.odds.mode, onChange: v => I.odds.set(v) });
oddsCtl.classList.add('ip-odds'); oddsCtl.title = 'Fair-odds format: American (US) or decimal';
I.wb = S.workbook({
  title: 'IPL projections', subtitle: 'Ball-by-ball player ratings and match simulator', hub: '../',
  meta: 'data/meta.json', actions: oddsCtl, defaultSheet: 'overview',
  onSheet: () => { if (S.drawer.isOpen) S.drawer.close(); },
  sheets: [
    { id: 'overview', name: 'Overview', render: overview },
    { id: 'batters', name: 'Batters', fill: true, render: batters },
    { id: 'bowlers', name: 'Bowlers', fill: true, render: bowlers },
    { id: 'teams', name: 'Teams', render: teams },
    { id: 'matchups', name: 'Matchups', render: matchups },
    { id: 'match', name: 'Match', render: match },
    { id: 'props', name: 'Player props', render: props },
    { id: 'sim', name: 'Simulator', render: simulator },
    { id: 'venues', name: 'Venues', render: venues },
    { id: 'leagues', name: 'Leagues', render: leagues },
    { id: 'value', name: 'Player value', render: value },
    { id: 'diag', name: 'Diagnostics', render: diagnostics },
    { id: 'method', name: 'Method', render: method },
  ],
});
})();
