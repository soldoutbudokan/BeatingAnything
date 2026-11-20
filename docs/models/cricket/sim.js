/*
 * Ball-by-ball Monte Carlo engine for ODIs and Tests (browser worker + node, no DOM).
 *
 *   const P = CricketSim.prepare(simParamsJson);            // docs/models/<odi|test>/data/sim_params.json
 *   const raw = CricketSim.simMatchRaw(P, teamA, teamB, opts);
 *   const out = CricketSim.summarizeRaw(raw);
 *
 * team = { name, order: [11 player ids],
 *          plan: ODI  [{id, pp, mid, death}]  whole overs per phase (1-10, 11-40, 41-50), 50 in total, 10 a bowler
 *                Test [{id, nb, mid, old}]    share of the overs with the new ball (ball 1-20 overs old), middle
 *                                             (21-55) and old ball (56-80); any positive numbers
 *          roles: {id: {bat: 'open'|'top'|'middle'|'lower'|'tail', bowl: 'pace_front'|...}}  optional, for ids the
 *                                             model has no rating for (they get the role prior plus the team term) }
 * opts = { venue, country, home: 'A'|'B'|null, batFirst: 'A'|'B'|null (null = half the sims each way),
 *          conditions: {pitch, dew}, n, seed,
 *          overs: fixed overs available in the Test (default: drawn per sim from the host country's curve),
 *          oversAdj: overs added to (or, negative, taken from) each drawn value }
 *
 * Per-ball probabilities are a softmax over 11 outcome classes. The logits are the sum of the exported
 * tables: match situation, settling, environment (year, host country, season, ground), bowling type, bowler,
 * batter, home advantage, the match's pitch shock and any user conditions. ODIs add chase pressure. Tests add
 * pitch wear, the batting side's position (score, lead, target, time left), spell length and tail batting,
 * plus models for declarations, the follow-on and the overs the weather leaves.
 *
 * This is the only simulator for these formats: the site build runs this file under node (models/intl/sim_cli.js),
 * so published numbers and the in-browser numbers come from one implementation.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CricketSim = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  var NC = 11, WIDE = 0, NOBALL = 1, BYES = 2, WICKET = 3, RUNOUT = 4, R0 = 5;
  var BAT_RUNS = [0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 6];
  var MAX_SPELL = 25, NBAT = 11;
  var ZERO = new Array(NC).fill(0);

  // ---------------------------------------------------------------- RNG (sfc32) + normal
  function makeRng(seed) {
    var a = 0x9e3779b9, b = 0x243f6a88, c = 0xb7e15162, d = (seed >>> 0) ^ 0xdeadbeef;
    function next() {
      a >>>= 0; b >>>= 0; c >>>= 0; d >>>= 0;
      var t = (a + b) | 0;
      a = b ^ (b >>> 9);
      b = (c + (c << 3)) | 0;
      c = (c << 21) | (c >>> 11);
      d = (d + 1) | 0;
      t = (t + d) | 0;
      c = (c + t) | 0;
      return (t >>> 0) / 4294967296;
    }
    for (var i = 0; i < 15; i++) next();
    return next;
  }
  function gauss(rng) {
    var u = 0;
    while (u === 0) u = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rng());
  }

  // ---------------------------------------------------------------- params
  function f64(a) { return a ? Float64Array.from(a) : null; }
  function prepare(raw) {
    var P = { raw: raw, fmt: raw.fmt, isTest: raw.fmt === 'test' };
    P.nInn = raw.n_inn; P.nOvb = raw.n_ovb; P.maxOvers = raw.max_overs; P.cap = raw.max_bowler_overs;
    P.base = f64(raw.base); P.ipw = f64(raw.ipw); P.bf = f64(raw.bf);
    P.nBf = raw.bf_edges.length; P.bfEdges = raw.bf_edges; P.earlyBf = raw.early_bf; P.overEdges = raw.over_edges;
    P.ex = {};
    ['wide_runs', 'nb_bat', 'bye_runs', 'runout_runs'].forEach(function (k) {
      var d = raw.extras[k], s = 0, acc = 0, cp = [];
      d.p.forEach(function (x) { s += x; });
      d.p.forEach(function (x) { acc += x / s; cp.push(acc); });
      P.ex[k] = { v: d.v, cp: cp };
    });
    P.qRoStriker = raw.extras.runout_striker;
    var sh = raw.shock || {};
    P.dirR = sh.dir_r || ZERO; P.dirW = sh.dir_w || ZERO;
    P.Lm = sh.L_match || [[0, 0], [0, 0]]; P.Li = sh.L_inn || [[0, 0], [0, 0]];
    if (P.isTest) {
      ['mo', 'mo_spin', 'pos12', 'lead3', 'need4', 'rr4', 'spell', 'tail'].forEach(function (k) { P[k] = f64(raw[k]); });
      P.flow = raw.flow;
      P.haz = { pace: raw.flow.spell_hazard.pace, spin: raw.flow.spell_hazard.spin };
      P.meanSpell = {};
      ['pace', 'spin'].forEach(function (t) {  // expected spell length under the hazard curve
        var s = 0, surv = 1, h = P.haz[t];
        for (var k = 0; k < 60; k++) { s += surv; surv *= 1 - h[Math.min(k, h.length - 1)]; }
        P.meanSpell[t] = s;
      });
    } else {
      P.chase = f64(raw.chase); P.chaseW = f64(raw.chase_w); P.nRrr = raw.n_rrr; P.rrrEdges = raw.rrr_edges;
    }
    return P;
  }
  function draw(d, u) {
    for (var i = 0; i < d.cp.length; i++) if (u < d.cp[i]) return d.v[i];
    return d.v[d.v.length - 1];
  }
  /** number of interior edges <= x */
  function bk(edges, x) { var k = 0; for (var i = 0; i < edges.length; i++) if (x >= edges[i]) k = i + 1; return k; }
  /** bucket for lower-edge lists that start at 0 */
  function bl(edges, x) { var k = 0; for (var i = 1; i < edges.length; i++) if (x >= edges[i]) k = i; return k; }
  function phaseOf(P, o) {
    if (!P.isTest) return o < 10 ? 0 : (o < 40 ? 1 : 2);
    var age = o % 80;
    return age < 20 ? 0 : (age < 55 ? 1 : 2);
  }
  function add(a, b, s) { if (b) for (var c = 0; c < NC; c++) a[c] += (s === undefined ? 1 : s) * b[c]; }

  // ---------------------------------------------------------------- players
  var TAIL_ROLES = { lower: 1, tail: 1 };
  function batterOf(P, id, team) {
    var b = P.raw.batters[id];
    if (b) return b;
    var role = (team.roles && team.roles[id] && team.roles[id].bat) || 'middle';
    var v = (P.raw.batter_priors[role] || P.raw.batter_priors.middle).slice();
    add(v, (P.raw.team_prior[team.name] || {}).bat);
    return { b: v, pp: ZERO, de: ZERO, sp: ZERO, ea: ZERO, aw: ZERO, hand: (team.roles && team.roles[id] && team.roles[id].hand) || 'R', tl: TAIL_ROLES[role] ? 1 : 0 };
  }
  function bowlerOf(P, id, team) {
    var w = P.raw.bowlers[id];
    if (w) return w;
    var role = (team.roles && team.roles[id] && team.roles[id].bowl) || 'pace_part';
    var v = (P.raw.bowler_priors[role] || P.raw.bowler_priors.pace_part).slice();
    add(v, (P.raw.team_prior[team.name] || {}).bowl);
    var spin = role.indexOf('spin') === 0 ? 1 : 0;
    return { b: v, pp: ZERO, de: ZERO, lh: ZERO, aw: ZERO, sub: spin ? 'spin_U' : 'pace_U', spin: spin };
  }

  // ---------------------------------------------------------------- bowling plans
  /** ODI captain: whole overs per phase -> one bowler per over. Each over goes to the bowler with the most
      planned overs left in that phase who did not bowl the previous over, is under the cap, and whose choice
      leaves the remaining quotas bowlable without consecutive overs. */
  function bowlingSchedule(plan, nOvers, cap, bounds) {
    nOvers = nOvers || 50; cap = cap || 10; bounds = bounds || [10, 40];
    var nb = plan.length, i, j, k;
    var q = plan.map(function (p) { return [p.pp || 0, p.mid || 0, p.death || 0]; });
    var quota = q.map(function (x) { return Math.min(cap, Math.round(x[0] + x[1] + x[2])); });
    var sum = function (a) { var s = 0; for (var t = 0; t < a.length; t++) s += a[t]; return s; };
    if (sum(quota) < nOvers) {
      var order = q.map(function (x, t) { return [-(x[0] + x[1] + x[2]), t]; })
        .sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; }).map(function (x) { return x[1]; });
      var it = 0;
      while (sum(quota) < nOvers && it < 2000) { j = order[it % nb]; if (quota[j] < cap) quota[j]++; it++; }
    }
    var used = new Array(nb).fill(0), phUsed = q.map(function () { return [0, 0, 0]; }), sched = [], last = -1;
    for (var o = 0; o < nOvers; o++) {
      var ph = o < bounds[0] ? 0 : (o < bounds[1] ? 1 : 2), R2 = nOvers - o - 1, best = -1, bestS = -1e9;
      for (j = 0; j < nb; j++) {
        if (j === last || used[j] >= quota[j]) continue;
        var tot = 0, ok = true;
        for (k = 0; k < nb && ok; k++) {
          var rem = quota[k] - used[k] - (k === j ? 1 : 0);
          tot += rem;
          if (rem > (k === j ? Math.floor(R2 / 2) : Math.floor((R2 + 1) / 2))) ok = false;
        }
        if (!ok || tot < R2) continue;
        var s = (q[j][ph] - phUsed[j][ph]) * 10 + (quota[j] - used[j]) * 0.1 - j * 1e-4;
        if (s > bestS) { best = j; bestS = s; }
      }
      if (best < 0) {
        var bu = 1e9;
        for (j = 0; j < nb; j++) if (j !== last && used[j] < bu) { bu = used[j]; best = j; }
        if (best < 0) best = 0;
      }
      sched.push(best);
      used[best]++; phUsed[best][ph]++; last = best;
    }
    return sched;
  }

  // ---------------------------------------------------------------- per-match static tables
  function conditionTerms(P, conditions) {
    var out = { all: new Array(NC).fill(0), pace: new Array(NC).fill(0), spin: new Array(NC).fill(0), inn: [] }, k;
    for (k = 0; k < 4; k++) out.inn.push(new Array(NC).fill(0));
    var tbl = P.raw.conditions || {};
    Object.keys(conditions || {}).forEach(function (g) {
      var t = (tbl[g] || {})[conditions[g]];
      if (!t) return;
      add(out.all, t.all); add(out.pace, t.pace); add(out.spin, t.spin);
      for (k = 0; k < 4; k++) add(out.inn[k], t['i' + (k + 1)]);
    });
    return out;
  }

  /** Static logits for every (batter, bowler, phase) of one side batting against the other's attack. */
  function buildSide(P, bat, bowl, C, batHome, bowlHome) {
    var order = bat.order.slice(0, NBAT), nb = order.length, i, j, p, c;
    var ids = [];
    bowl.plan.forEach(function (x) { if (ids.indexOf(x.id) < 0) ids.push(x.id); });
    var nw = ids.length, raw = P.raw, ha = raw.ha;
    var bt = order.map(function (id) { return batterOf(P, id, bat); });
    var bw = ids.map(function (id) { return bowlerOf(P, id, bowl); });
    var S = new Float64Array(nb * nw * 3 * NC), edge = batHome ? 1 : (bowlHome ? -1 : 0);
    for (i = 0; i < nb; i++) for (j = 0; j < nw; j++) {
      var b = bt[i], w = bw[j], spin = w.spin ? 1 : 0, lh = b.hand === 'L' ? 1 : 0;
      var sub = raw.sub[w.sub], subl = raw.sub_lhb[w.sub], ty = b.ty && b.ty[w.sub];
      for (p = 0; p < 3; p++) {
        var subph = raw.sub_phase[w.sub][p], eph = C.env.ph[p], off = ((i * nw + j) * 3 + p) * NC;
        for (c = 0; c < NC; c++) {
          var v = C.env.all[c] + eph[c] + C.V.base[c] + sub[c] + subph[c] + w.b[c] + b.b[c] + C.cond.all[c] +
            (p === 0 ? w.pp[c] + b.pp[c] : 0) + (p === 2 ? w.de[c] + b.de[c] : 0) +
            (bowlHome ? 0 : w.aw[c]) + (batHome ? 0 : b.aw[c]) +
            (ty ? ty[c] : 0) + lh * (subl[c] + w.lh[c]);
          // home advantage: Tests carry one signed edge (batting side at home +1, bowling side -1), ODIs a term each way
          if (ha.edge) v += edge * (ha.edge[c] + (spin ? ha.edge_spin[c] : 0));
          else v += (batHome ? ha.bat_home[c] + (spin ? ha.bat_home_spin[c] : 0) : 0) + (bowlHome ? ha.bowl_home[c] + (spin ? ha.bowl_home_spin[c] : 0) : 0);
          if (spin) v += C.env.spin[c] + C.V.spin[c] + b.sp[c] + C.cond.spin[c];
          else v += C.cond.pace[c];
          S[off + c] = v;
        }
      }
    }
    var side = { order: order, ids: ids, nb: nb, nw: nw, S: S, ea: bt.map(function (x) { return x.ea; }),
                 tl: bt.map(function (x) { return x.tl ? 1 : 0; }), spin: bw.map(function (x) { return x.spin ? 1 : 0; }) };
    if (P.isTest) {
      // spell model: chance of being handed the ball = share of the phase's overs / expected spell length
      side.w = [0, 1, 2].map(function (ph) {
        var key = ['nb', 'mid', 'old'][ph];
        return bowl.plan.reduce(function (acc, x) {
          var k = ids.indexOf(x.id);
          acc[k] += Math.max(0, +x[key] || 0) / P.meanSpell[bw[k].spin ? 'spin' : 'pace'];
          return acc;
        }, new Array(nw).fill(0));
      });
    } else {
      var byId = {};
      bowl.plan.forEach(function (x) { byId[x.id] = x; });
      side.sched = bowl.schedule && bowl.schedule.length === P.maxOvers
        ? bowl.schedule.map(function (id) { return Math.max(0, ids.indexOf(id)); })
        : bowlingSchedule(ids.map(function (id) { return byId[id]; }), P.maxOvers, P.cap);
    }
    return side;
  }

  function newInnings(nw) {
    return { score: 0, wk: 0, legal: 0, pp: 0, fow1: 0, fours: 0, sixes: 0, extras: 0, end: '', overs: 0,
             runs: new Int32Array(NBAT), balls: new Int32Array(NBAT), f4: new Int32Array(NBAT), s6: new Int32Array(NBAT),
             out: new Uint8Array(NBAT), batted: new Uint8Array(NBAT),
             bBalls: new Int32Array(nw), bRuns: new Int32Array(nw), bWk: new Int32Array(nw) };
  }

  function declFeatures(inn, score, lead, wk, ov, rem) {  // mirrors models/intl/flow.py decl_features
    if (inn === 1) return [1, score / 100, Math.max(score - 400, 0) / 100, wk, ov / 50, rem / 90];
    if (inn === 2) return [1, lead / 100, Math.max(lead, 0) / 100, wk, ov / 50, rem / 90];
    return [1, lead / 100, Math.max(lead - 200, 0) / 100, wk, rem / 90, Math.min(lead / Math.max(rem, 1), 12)];
  }
  function logistic(coef, x) { var s = 0; for (var i = 0; i < coef.length; i++) s += coef[i] * x[i]; return 1 / (1 + Math.exp(-s)); }

  // ---------------------------------------------------------------- one innings
  var lg = new Float64Array(NC), pr = new Float64Array(NC), ovAdd = new Float64Array(NC), wgt = new Float64Array(16);
  /**
   * S: side tables; I: innings record (filled); x = {inn (1-based), target (number or null), shock (11-vector),
   * innAdd (11-vector), lead0, M (Test match clock: {balls, avail})}
   */
  function playInnings(P, S, rng, I, x) {
    var isTest = P.isTest, nb = S.nb, nw = S.nw, inn0 = x.inn - 1, c, k;
    var score = 0, wk = 0, legal = 0, stk = 0, nst = 1, nxt = 2, free = false, done = '';
    var fow1 = -1, fours = 0, sixes = 0, extras = 0, pp = 0;
    I.runs.fill(0); I.balls.fill(0); I.f4.fill(0); I.s6.fill(0); I.out.fill(0); I.batted.fill(0);
    I.bBalls.fill(0); I.bRuns.fill(0); I.bWk.fill(0);
    I.batted[0] = 1; if (nb > 1) I.batted[1] = 1;
    var tgt = x.target, M = x.M, lead0 = x.lead0 || 0;
    var endB0 = -1, endB1 = -1, endL0 = 0, endL1 = 0;
    var exW = P.ex.wide_runs, exN = P.ex.nb_bat, exB = P.ex.bye_runs, exR = P.ex.runout_runs;
    var maxO = isTest ? 100000 : P.maxOvers, o = 0;
    for (; o < maxO && !done; o++) {
      if (isTest && M.balls >= M.avail * 6) { done = 'time'; break; }
      var ph = phaseOf(P, o), j;
      // ---- who bowls this over
      if (!isTest) j = S.sched[o];
      else {
        var e = o & 1, cur = e ? endB1 : endB0, len = e ? endL1 : endL0, other = e ? endB0 : endB1;
        var newBall = o >= 80 && (o % 80) < 2;
        if (newBall) cur = -1;   // the new ball goes to whoever the new-ball shares favour, the current bowler included
        var change = cur < 0;
        if (!change) {
          var hz = P.haz[S.spin[cur] ? 'spin' : 'pace'];
          change = rng() < hz[Math.min(len, MAX_SPELL) - 1];
        }
        if (change) {
          var w = S.w[ph], tot = 0;
          for (k = 0; k < nw; k++) { wgt[k] = (k === other || k === cur) ? 0 : w[k]; tot += wgt[k]; }
          if (tot <= 0) { for (k = 0; k < nw; k++) { wgt[k] = k === other ? 0 : (w[k] > 0 ? w[k] : 1e-6); tot += wgt[k]; } }
          var u0 = rng() * tot, acc0 = 0, pick = -1;
          for (k = 0; k < nw; k++) { acc0 += wgt[k]; if (u0 < acc0) { pick = k; break; } }
          if (pick < 0) { for (k = nw - 1; k >= 0; k--) if (wgt[k] > 0) { pick = k; break; } }
          if (pick < 0) pick = other === 0 ? Math.min(1, nw - 1) : 0;
          cur = pick; len = 0;
        }
        len++;
        if (e) { endB1 = cur; endL1 = len; } else { endB0 = cur; endL0 = len; }
        j = cur;
      }
      var spin = S.spin[j], ovb = bl(P.overEdges, o);
      for (c = 0; c < NC; c++) ovAdd[c] = x.shock[c] + x.innAdd[c];
      if (isTest) {
        var mob = bl(P.raw.mo_edges, M.balls / 6) * NC, spb = (spin * P.raw.spell_edges.length + bl(P.raw.spell_edges, Math.floor(I.bBalls[j] / 6))) * NC;
        for (c = 0; c < NC; c++) ovAdd[c] += P.mo[mob + c] + (spin ? P.mo_spin[mob + c] : 0) + P.spell[spb + c];
      }
      var lio = 0;
      for (var step = 0; step < 30 && !done && lio < 6; step++) {
        var wkc = wk < 9 ? wk : 9, sbf = I.balls[stk];
        var baseOff = ((inn0 * P.nOvb + ovb) * 10 + wkc) * NC, ipwOff = ((inn0 * 3 + ph) * 10 + wkc) * NC;
        var bfOff = (ph * P.nBf + bl(P.bfEdges, sbf)) * NC, sOff = ((stk * nw + j) * 3 + ph) * NC;
        for (c = 0; c < NC; c++) lg[c] = P.base[baseOff + c] + P.ipw[ipwOff + c] + P.bf[bfOff + c] + S.S[sOff + c] + ovAdd[c];
        if (sbf < P.earlyBf) { var ea = S.ea[stk]; for (c = 0; c < NC; c++) lg[c] += ea[c]; }
        if (!isTest) {
          if (tgt !== null) {
            var rrr = (tgt - score) * 6.0 / Math.max(maxO * 6 - legal, 1), rb = bk(P.rrrEdges, rrr), chOff = (ph * P.nRrr + rb) * NC;
            for (c = 0; c < NC; c++) lg[c] += P.chase[chOff + c];
            if (P.chaseW) { var cwOff = ((ph * P.nRrr + rb) * 3 + (wk >= 7 ? 0 : (wk >= 4 ? 1 : 2))) * NC; for (c = 0; c < NC; c++) lg[c] += P.chaseW[cwOff + c]; }
          }
          if (free) lg[WICKET] = -50;
        } else {
          var wkg = wk <= 3 ? 0 : (wk <= 6 ? 1 : 2), dOff, tbl;
          if (x.inn === 1) { tbl = P.pos12; dOff = (bk(P.raw.score1_edges, score) * 3 + wkg) * NC; }
          else if (x.inn === 2) { tbl = P.pos12; dOff = ((5 + bk(P.raw.lead2_edges, lead0 + score)) * 3 + wkg) * NC; }
          else if (x.inn === 3) { tbl = P.lead3; dOff = (bk(P.raw.lead3_edges, lead0 + score) * 3 + wkg) * NC; }
          else {
            tbl = P.need4; var need = tgt - score, remO = Math.max(M.avail - M.balls / 6, 1);
            dOff = (bk(P.raw.need4_edges, need) * 3 + wkg) * NC;
            var rOff = (bk(P.raw.rr4_edges, need / remO) * 4 + bk(P.raw.rem4_edges, remO)) * NC;
            for (c = 0; c < NC; c++) lg[c] += P.rr4[rOff + c];
          }
          for (c = 0; c < NC; c++) lg[c] += tbl[dOff + c];
          if (wk >= 7 && !S.tl[stk]) { var tOff = (wk - 7 > 2 ? 2 : wk - 7) * NC; for (c = 0; c < NC; c++) lg[c] += P.tail[tOff + c]; }
        }
        if (step >= 14) { lg[WIDE] = -50; lg[NOBALL] = -50; }  // pathological run of extras: force a legal ball
        var mx = -1e9, tot2 = 0;
        for (c = 0; c < NC; c++) if (lg[c] > mx) mx = lg[c];
        for (c = 0; c < NC; c++) { pr[c] = Math.exp(lg[c] - mx); tot2 += pr[c]; }
        var u = rng() * tot2, cls = NC - 1, acc = 0;
        for (c = 0; c < NC; c++) { acc += pr[c]; if (u < acc) { cls = c; break; } }
        var runs = 0, batr = BAT_RUNS[cls], ran = batr, conc = 0, isl = cls > NOBALL;
        var batScoring = cls >= R0 || cls === NOBALL || cls === RUNOUT;
        if (cls === WIDE) { var wr = draw(exW, rng()); runs = wr; conc = wr; ran = wr === 5 ? 0 : wr - 1; }
        else if (cls === NOBALL) { var nbr = draw(exN, rng()); batr = nbr; ran = (nbr === 4 || nbr === 6) ? 0 : nbr; runs = 1 + nbr; conc = 1 + nbr; }
        else if (cls === BYES) { var byr = draw(exB, rng()); runs = byr; ran = byr === 4 ? 0 : byr; }
        else if (cls === RUNOUT) { var ror = draw(exR, rng()); batr = ror; ran = ror; }
        if (batScoring && cls !== NOBALL) { runs = batr; conc = batr; }
        if (batScoring) I.runs[stk] += batr;
        if (cls !== WIDE) I.balls[stk] += 1;
        if (batScoring && cls !== RUNOUT) {
          if (batr === 4) { I.f4[stk]++; fours++; } else if (batr === 6) { I.s6[stk]++; sixes++; }
        }
        if (isl) { I.bBalls[j]++; legal++; lio++; if (isTest) M.balls++; }
        I.bRuns[j] += conc;
        if (cls === WICKET) I.bWk[j]++;
        if (cls <= BYES) extras += (cls === NOBALL ? 1 : runs);
        score += runs;
        free = cls === NOBALL ? true : (isl ? false : free);
        var faced = stk;
        if (ran % 2 === 1) { var t0 = stk; stk = nst; nst = t0; }
        if (cls === WICKET || cls === RUNOUT) {
          var victim = faced;
          if (cls === RUNOUT && rng() >= P.qRoStriker) victim = (stk === faced) ? nst : stk;
          I.out[victim] = 1;
          if (fow1 < 0) fow1 = score;
          wk++;
          if (nxt < nb) { if (stk === victim) stk = nxt; else nst = nxt; I.batted[nxt] = 1; }
          nxt++;
          if (wk >= nb - 1) done = 'allout';
        }
        if (tgt !== null && score >= tgt) done = 'target';
      }
      if (o === 9) pp = score;
      if (!done) {
        var t1 = stk; stk = nst; nst = t1;
        if (isTest && x.inn <= 3 && !(x.inn === 3 && lead0 + score <= 0)) {
          var pd = logistic(P.flow.decl[x.inn], declFeatures(x.inn, score, lead0 + score, wk, o + 1, M.avail - M.balls / 6));
          if (rng() < pd) done = 'declared';
        }
      }
    }
    if (!done) done = 'overs';
    if (o <= 9) pp = score;
    I.score = score; I.wk = wk; I.legal = legal; I.pp = pp; I.fow1 = fow1 < 0 ? score : fow1; I.fours = fours; I.sixes = sixes;
    I.extras = extras; I.end = done;
    return I;
  }

  // ---------------------------------------------------------------- raw accumulators (poolable integer counts)
  function hadd(h, v) { if (v < 0) v = 0; while (h.length <= v) h.push(0); h[v] += 1; }
  function hmerge(a, b) {
    var out = (a || []).slice();
    for (var i = 0; i < (b || []).length; i++) { if (i >= out.length) out.push(0); out[i] += b[i]; }
    return out;
  }
  var T_HISTS = ['t1', 't2', 'w1', 'fow1', 'fours', 'sixes', 'pp'], T_NUMS = ['n1', 'n2', 'decl1', 'allout1', 'ov1'];
  var P_HISTS = ['r1', 'r2', 'rm', 'f', 's', 'w1', 'wm', 'c1'];
  var P_NUMS = ['n', 'b1', 'bat1', 'out1', 'duck1', 'top1', 'c50', 'c100', 'bb1', 'cr1', 'bbm', 'crm', 'topw1', 'nw'];
  var M_HISTS = ['total', 'sixes', 'fours', 'lead1', 'overs', 'day', 'm_runs', 'm_wkts', 'm_balls'];
  function newPlayer() { var o = {}; P_HISTS.forEach(function (k) { o[k] = []; }); P_NUMS.forEach(function (k) { o[k] = 0; }); return o; }
  function newTeam() { var o = { players: {} }; T_HISTS.forEach(function (k) { o[k] = []; }); T_NUMS.forEach(function (k) { o[k] = 0; }); return o; }
  function newFirst() { return { n: 0, A: 0, B: 0, draw: 0, tie: 0, inn1: [] }; }
  function newRaw(fmt, A, B) {
    var raw = { v: 1, fmt: fmt, n: 0, names: { A: A.name, B: B.name }, res: { A: 0, B: 0, draw: 0, tie: 0 },
                first: { A: newFirst(), B: newFirst() }, teams: { A: newTeam(), B: newTeam() }, match: { inns_win: 0, fo: 0, fo_ok: 0 } };
    M_HISTS.forEach(function (k) { raw.match[k] = []; });
    return raw;
  }
  var LEAD_OFF = 1000;

  /** fold one team's innings of one match into its accumulators. digs: innings records of this team (1 or 2);
      bowl: innings records in which this team bowled (same order); S: the side table where this team bats; SB: where it bowls */
  function accTeam(T, digs, bowl, S, SB) {
    var d1 = digs[0], i, k, id, p;
    T.n1++; hadd(T.t1, d1.score); hadd(T.w1, d1.wk); hadd(T.fow1, d1.fow1);
    if (d1.end === 'declared') T.decl1++;
    if (d1.end === 'allout') T.allout1++;
    T.ov1 += d1.legal / 6;
    if (d1.ppOk) hadd(T.pp, d1.pp);
    var fours = 0, sixes = 0;
    digs.forEach(function (d) { fours += d.fours; sixes += d.sixes; });
    hadd(T.fours, fours); hadd(T.sixes, sixes);
    if (digs.length > 1) { T.n2++; hadd(T.t2, digs[1].score); }
    var top = -1, ntop = 0;
    for (k = 0; k < S.nb; k++) if (d1.batted[k] && d1.runs[k] > top) top = d1.runs[k];
    for (k = 0; k < S.nb; k++) if (d1.batted[k] && d1.runs[k] === top) ntop++;
    for (k = 0; k < S.nb; k++) {
      id = S.order[k]; p = T.players[id] || (T.players[id] = newPlayer());
      var r1 = d1.runs[k], rm = r1, f = d1.f4[k], s = d1.s6[k], best = r1;
      p.n++; hadd(p.r1, r1); p.b1 += d1.balls[k]; p.bat1 += d1.batted[k]; p.out1 += d1.out[k];
      if (d1.out[k] && r1 === 0) p.duck1++;
      if (d1.batted[k] && r1 === top && ntop > 0) p.top1 += 1 / ntop;
      if (digs.length > 1) { var d2 = digs[1]; hadd(p.r2, d2.runs[k]); rm += d2.runs[k]; f += d2.f4[k]; s += d2.s6[k]; if (d2.runs[k] > best) best = d2.runs[k]; }
      hadd(p.rm, rm); hadd(p.f, f); hadd(p.s, s);
      if (best >= 50) p.c50++;
      if (best >= 100) p.c100++;
    }
    if (!bowl.length) return;
    var b1 = bowl[0], bestKey = -1e9, nbest = 0, key;
    for (k = 0; k < SB.nw; k++) { key = b1.bWk[k] * 1000 - b1.bRuns[k]; if (b1.bBalls[k] > 0 && key > bestKey) bestKey = key; }
    for (k = 0; k < SB.nw; k++) if (b1.bBalls[k] > 0 && b1.bWk[k] * 1000 - b1.bRuns[k] === bestKey) nbest++;
    for (k = 0; k < SB.nw; k++) {
      id = SB.ids[k]; p = T.players[id] || (T.players[id] = newPlayer());
      var wm = 0, bm = 0, cm = 0;
      bowl.forEach(function (b) { wm += b.bWk[k]; bm += b.bBalls[k]; cm += b.bRuns[k]; });
      p.nw++; hadd(p.w1, b1.bWk[k]); hadd(p.wm, wm); hadd(p.c1, b1.bRuns[k]);
      p.bb1 += b1.bBalls[k]; p.cr1 += b1.bRuns[k]; p.bbm += bm; p.crm += cm;
      if (b1.bBalls[k] > 0 && b1.bWk[k] * 1000 - b1.bRuns[k] === bestKey) p.topw1 += 1 / nbest;
    }
  }
  function snapshot(I, nw) {  // copy an innings record (the engine reuses its buffers)
    return { score: I.score, wk: I.wk, legal: I.legal, pp: I.pp, ppOk: I.legal >= 60 || I.end !== 'time', fow1: I.fow1, fours: I.fours, sixes: I.sixes, end: I.end,
             runs: I.runs.slice(), balls: I.balls.slice(), f4: I.f4.slice(), s6: I.s6.slice(), out: I.out.slice(), batted: I.batted.slice(),
             bBalls: I.bBalls.slice(0, nw), bRuns: I.bRuns.slice(0, nw), bWk: I.bWk.slice(0, nw) };
  }

  // ---------------------------------------------------------------- match
  function shockVec(P, out, zr, zw) { for (var c = 0; c < NC; c++) out[c] = zr * P.dirR[c] + zw * P.dirW[c]; }

  function context(P, A, B, opts) {
    var raw = P.raw, V = (opts.venue && raw.venues[opts.venue]) || raw.venue_neutral;
    var country = opts.country || V.country || null;
    var env = raw.env[country] || raw.env._default;
    var cond = conditionTerms(P, opts.conditions);
    var C = { env: env, V: V, cond: cond, country: country };
    var hA = opts.home === 'A', hB = opts.home === 'B';
    C.sides = { A: buildSide(P, A, B, C, hA, hB), B: buildSide(P, B, A, C, hB, hA) };  // sides[X]: X batting
    C.avail = raw.avail_q ? (raw.avail_q[country] || raw.avail_q._pooled) : null;
    return C;
  }

  function simMatchRaw(P, A, B, opts) {
    opts = opts || {};
    var n = opts.n || 10000, rng = makeRng(opts.seed || 1), C = context(P, A, B, opts), raw = newRaw(P.fmt, A, B);
    var SA = C.sides.A, SB = C.sides.B, nwMax = Math.max(SA.nw, SB.nw);
    var I = newInnings(nwMax), shock = new Float64Array(NC), innAdd = new Float64Array(NC), isTest = P.isTest, c;
    var late0 = isTest ? 2 : 1;
    for (var s = 0; s < n; s++) {
      var first = opts.batFirst === 'A' || opts.batFirst === 'B' ? opts.batFirst : (s < n / 2 ? 'A' : 'B');
      var second = first === 'A' ? 'B' : 'A';
      var g1 = gauss(rng), g2 = gauss(rng), zr = P.Lm[0][0] * g1, zw = P.Lm[1][0] * g1 + P.Lm[1][1] * g2;
      var M = { balls: 0, avail: 0 };
      if (isTest) {
        M.avail = opts.overs != null ? +opts.overs : C.avail[Math.min(C.avail.length - 1, Math.floor(rng() * C.avail.length))] + (+opts.oversAdj || 0);
        if (M.avail < 1) M.avail = 1;
      }
      var digs = { A: [], B: [] }, bowl = { A: [], B: [] }, agg = { A: 0, B: 0 };
      var batting = first, result = null, fo = false, nInn = isTest ? 4 : 2, k, target = null;
      for (k = 1; k <= nInn && !result; k++) {
        if (k === 2) batting = second;
        else if (k === 3) {
          var lead = agg[first] - agg[second];
          batting = first;
          if (isTest && lead >= P.flow.follow_on.min_lead) {
            raw.match.fo_ok++;
            var fc = P.flow.follow_on.coef, i2 = digs[second][0];
            var pf = 1 / (1 + Math.exp(-(fc[0] + fc[1] * (lead - 200) / 100 + fc[2] * i2.legal / 300 + fc[3] * (M.avail - M.balls / 6) / 90)));
            if (rng() < pf) { batting = second; fo = true; raw.match.fo++; }
          }
        } else if (k === 4) batting = digs[first].length === 2 ? second : first;
        var fielding = batting === 'A' ? 'B' : 'A', S = C.sides[batting];
        target = null;
        if (!isTest && k === 2) target = agg[first] + 1;
        if (isTest && k === 4) {
          target = agg[fielding] - agg[batting] + 1;
          if (target <= 0) { result = batting; raw.match.inns_win++; break; }   // the side yet to bat again already leads
        }
        var g3 = gauss(rng), g4 = gauss(rng);
        shockVec(P, shock, zr + P.Li[0][0] * g3, zw + P.Li[1][0] * g3 + P.Li[1][1] * g4);
        var late = k > late0 ? C.V.late : null, ci = C.cond.inn[k - 1];
        for (c = 0; c < NC; c++) innAdd[c] = (late ? late[c] : 0) + ci[c];
        playInnings(P, S, rng, I, { inn: k, target: target, shock: shock, innAdd: innAdd, lead0: agg[batting] - agg[fielding], M: M });
        var snap = snapshot(I, C.sides[batting].nw);
        digs[batting].push(snap); bowl[fielding].push(snap); agg[batting] += I.score;
        if (I.end === 'time') { result = 'draw'; break; }
        if (I.end === 'target') { result = batting; break; }
        if (!isTest && k === 2) result = agg[second] === agg[first] ? 'tie' : first;
        if (isTest && k === 4) result = agg[batting] === agg[fielding] ? 'tie' : fielding;
      }
      if (!result) result = 'draw';
      // ---- accumulate
      raw.n++; raw.res[result]++;
      var F = raw.first[first]; F.n++; F[result]++; hadd(F.inn1, digs[first][0].score);
      if (digs.A.length) accTeam(raw.teams.A, digs.A, bowl.A, SA, SB);
      if (digs.B.length) accTeam(raw.teams.B, digs.B, bowl.B, SB, SA);
      var mt = raw.match, tr = agg.A + agg.B, s6 = 0, f4 = 0;
      ['A', 'B'].forEach(function (t) { digs[t].forEach(function (d) { s6 += d.sixes; f4 += d.fours; }); });
      hadd(mt.total, tr); hadd(mt.sixes, s6); hadd(mt.fours, f4);
      if (digs.A.length && digs.B.length) hadd(mt.lead1, digs.A[0].score - digs.B[0].score + LEAD_OFF);
      if (isTest) {
        var ov = Math.ceil(M.balls / 6);
        hadd(mt.overs, ov);
        hadd(mt.day, Math.max(1, Math.min(5, Math.ceil(M.balls / 6 / (M.avail / 5) - 1e-9))));
      } else if (result === first) hadd(mt.m_runs, agg[first] - agg[second]);
      else if (result === second) { var d2 = digs[second][0]; hadd(mt.m_wkts, 10 - d2.wk); hadd(mt.m_balls, P.maxOvers * 6 - d2.legal); }
    }
    return raw;
  }

  function mergePlayers(a, b) {
    var out = {};
    Object.keys(a).concat(Object.keys(b).filter(function (x) { return !(x in a); })).forEach(function (id) {
      var x = a[id] || newPlayer(), y = b[id] || newPlayer(), z = {};
      P_HISTS.forEach(function (k) { z[k] = hmerge(x[k], y[k]); });
      P_NUMS.forEach(function (k) { z[k] = x[k] + y[k]; });
      out[id] = z;
    });
    return out;
  }
  /** Pool two raw results of the same matchup (different seeds). */
  function mergeRaw(a, b) {
    var o = { v: a.v, fmt: a.fmt, n: a.n + b.n, names: a.names, res: {}, first: {}, teams: {}, match: {} };
    ['A', 'B', 'draw', 'tie'].forEach(function (k) { o.res[k] = a.res[k] + b.res[k]; });
    ['A', 'B'].forEach(function (t) {
      var x = a.first[t], y = b.first[t];
      o.first[t] = { n: x.n + y.n, A: x.A + y.A, B: x.B + y.B, draw: x.draw + y.draw, tie: x.tie + y.tie, inn1: hmerge(x.inn1, y.inn1) };
      var T = { players: mergePlayers(a.teams[t].players, b.teams[t].players) };
      T_HISTS.forEach(function (k) { T[k] = hmerge(a.teams[t][k], b.teams[t][k]); });
      T_NUMS.forEach(function (k) { T[k] = a.teams[t][k] + b.teams[t][k]; });
      o.teams[t] = T;
    });
    M_HISTS.forEach(function (k) { o.match[k] = hmerge(a.match[k], b.match[k]); });
    ['inns_win', 'fo', 'fo_ok'].forEach(function (k) { o.match[k] = a.match[k] + b.match[k]; });
    return o;
  }

  function hstats(h, off) {
    off = off || 0;
    var n = 0, s = 0, s2 = 0, i;
    for (i = 0; i < h.length; i++) { n += h[i]; s += (i - off) * h[i]; s2 += (i - off) * (i - off) * h[i]; }
    var mean = n ? s / n : 0;
    return { n: n, mean: mean, sd: n ? Math.sqrt(Math.max(s2 / n - mean * mean, 0)) : 0,
      q: function (pq) { var target = pq * (n - 1), acc = 0; for (var v = 0; v < h.length; v++) { acc += h[v]; if (acc > target) return v - off; } return h.length - 1 - off; },
      ge: function (t) { var c = 0; for (var v = Math.max(0, t + off); v < h.length; v++) c += h[v]; return n ? c / n : 0; } };
  }

  /** Headline numbers from (pooled) raw counts: what the build writes for every scheduled fixture. */
  function summarizeRaw(raw) {
    var N = raw.n, isTest = raw.fmt === 'test';
    var out = { n: N, fmt: raw.fmt, p_A: raw.res.A / N, p_B: raw.res.B / N, p_draw: raw.res.draw / N, p_tie: raw.res.tie / N,
                match_runs: hstats(raw.match.total).mean, match_sixes: hstats(raw.match.sixes).mean, match_fours: hstats(raw.match.fours).mean };
    var l1 = hstats(raw.match.lead1, LEAD_OFF);
    if (isTest) {
      out.lead1_mean = l1.mean; out.p_lead1_A = l1.ge(1);
      out.overs_mean = hstats(raw.match.overs).mean;
      out.day = raw.match.day.map(function (c) { return c / N; });
      out.p_innings_win = raw.match.inns_win / N; out.p_follow_on = raw.match.fo / N;
    } else {
      out.margin_runs = hstats(raw.match.m_runs).mean; out.margin_wkts = hstats(raw.match.m_wkts).mean;
    }
    out.first = {};
    ['A', 'B'].forEach(function (t) {
      var F = raw.first[t];
      out.first[t] = F.n ? { n: F.n, p_A: F.A / F.n, p_B: F.B / F.n, p_draw: F.draw / F.n, inn1_mean: hstats(F.inn1).mean } : null;
      var T = raw.teams[t], t1 = hstats(T.t1), o = { t1_mean: t1.mean, t1_sd: t1.sd, t1_q: [0.05, 0.25, 0.5, 0.75, 0.95].map(t1.q),
        w1_mean: hstats(T.w1).mean, fow1_mean: hstats(T.fow1).mean, fours_mean: hstats(T.fours).mean, sixes_mean: hstats(T.sixes).mean,
        p_allout1: T.n1 ? T.allout1 / T.n1 : null, overs1_mean: T.n1 ? T.ov1 / T.n1 : null, players: {} };
      if (isTest) { o.t2_mean = T.n2 ? hstats(T.t2).mean : null; o.p_second_dig = T.n2 / N; o.p_decl1 = T.n1 ? T.decl1 / T.n1 : null; }
      else o.pp_mean = hstats(T.pp).mean;
      Object.keys(T.players).forEach(function (id) {
        var p = T.players[id], d = {};
        if (p.n) {
          var r = hstats(p.r1);
          d.runs1 = r.mean; d.p50 = r.ge(50); d.p100 = r.ge(100); d.p_top = p.top1 / p.n; d.balls1 = p.b1 / p.n;
          d.p_duck = p.duck1 / p.n; d.fours = hstats(p.f).mean; d.sixes = hstats(p.s).mean;
          if (isTest) { d.runs_match = hstats(p.rm).mean; d.p100_match = p.c100 / p.n; d.p50_match = p.c50 / p.n; }
        }
        if (p.nw) {
          var w = hstats(p.w1);
          d.wkts1 = w.mean; d.overs1 = p.bb1 / p.nw / 6; d.conc1 = p.cr1 / p.nw; d.p_topw = p.topw1 / p.nw;
          d.p3w = w.ge(3); d.p5w = w.ge(5); d.econ = p.bbm ? p.crm / p.bbm * 6 : null;
          if (isTest) { d.wkts_match = hstats(p.wm).mean; d.overs_match = p.bbm / p.nw / 6; }
        }
        o.players[id] = d;
      });
      out[t] = o;
    });
    return out;
  }

  return { prepare: prepare, simMatchRaw: simMatchRaw, mergeRaw: mergeRaw, summarizeRaw: summarizeRaw, hstats: hstats,
           bowlingSchedule: bowlingSchedule, makeRng: makeRng, LEAD_OFF: LEAD_OFF, context: context, playInnings: playInnings,
           newInnings: newInnings };
});
