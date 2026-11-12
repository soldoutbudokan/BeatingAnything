/*
 * IPL ball-by-ball Monte Carlo engine (browser + node, no DOM).
 *
 *   const P = IPLSim.prepare(simParamsJson);
 *   const out = IPLSim.simMatch(P, teamA, teamB, {venue: "wankhede stadium", n: 10000, seed: 1});
 *
 * team = {name, order: [11 player ids], plan: [{id, pp, mid, death}, ...]}   (or schedule: [20 bowler ids])
 * opts = {venue, n, seed, batFirst: "A" | "B" | null (null = half the sims each way), env,
 *         conditions: {pitch: "flat"|"normal"|"slow_low"|"seaming", dew: "none"|"normal"|"heavy"} (optional)}
 *
 * Mirrors models/ipl/sim.py. Per-ball probabilities are a softmax over 11 outcome classes whose logits are the
 * sum of the exported tables: context base[innings][over][wickets] + balls-faced(settling) + chase pressure +
 * bowler subtype (overall, by phase, vs left-handers) + season environment + venue + batter (overall/phase/vs spin/early) + bowler
 * (overall/phase/vs LHB).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.IPLSim = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  var NC = 11;
  var WIDE = 0, NOBALL = 1, BYES = 2, WICKET = 3, RUNOUT = 4, R0 = 5;
  var BAT_RUNS = [0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 6];
  var PHASE_OF = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2];
  var TOP_THRESH = [10, 20, 30, 40, 50, 75, 100];

  // ---------------------------------------------------------------- RNG (sfc32)
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

  // ---------------------------------------------------------------- params
  function prepare(raw) {
    var P = { raw: raw };
    P.base = Float64Array.from(raw.base);       // [2][20][8][11]
    P.bf = Float64Array.from(raw.bf);           // [3][9][11]
    P.chase = Float64Array.from(raw.chase);     // [3][8][11]
    P.chaseW = raw.chase_w ? Float64Array.from(raw.chase_w) : null;  // [3][8][3 wickets-in-hand bands][11]
    P.chaseHi = raw.chase_hi ? Float64Array.from(raw.chase_hi) : null;  // [3][2: rrr 20-24, 24+][11]
    P.bfEdges = raw.bf_edges;                   // lower edges of the 9 buckets
    P.rrrEdges = raw.rrr_edges;                 // 7 interior edges -> 8 buckets
    P.earlyBf = raw.early_bf;
    P.ex = {};
    ["wide_runs", "nb_bat", "bye_runs", "runout_runs"].forEach(function (k) {
      var d = raw.extras[k], s = 0, cp = [];
      d.p.forEach(function (x) { s += x; });
      var acc = 0;
      d.p.forEach(function (x) { acc += x / s; cp.push(acc); });
      P.ex[k] = { v: d.v, cp: cp };
    });
    P.qRoStriker = raw.extras.runout_striker;
    var ms = raw.match_shock || { sd: 0, dir: new Array(NC).fill(0) };
    P.shockSd = ms.sd; P.shockDir = ms.dir; P.shockInnSd = ms.innings_sd || 0;
    return P;
  }

  function draw(d, u) {
    for (var i = 0; i < d.cp.length; i++) if (u < d.cp[i]) return d.v[i];
    return d.v[d.v.length - 1];
  }

  function batterOf(P, id) {
    return P.raw.batters[id] || P.raw.batter_priors.middle;
  }
  function bowlerOf(P, id) {
    return P.raw.bowlers[id] || P.raw.bowler_priors.pace_reg;
  }

  function bucketIdx(edges, x) { // number of edges <= x, minus 1 (edges include the lowest)
    var k = 0;
    for (var i = 0; i < edges.length; i++) if (x >= edges[i]) k = i;
    return k;
  }
  function rrrIdx(edges, x) { // interior edges -> bucket 0..edges.length
    var k = 0;
    for (var i = 0; i < edges.length; i++) if (x >= edges[i]) k = i + 1;
    return k;
  }

  // ---------------------------------------------------------------- bowling schedule (captain heuristic)
  function bowlingSchedule(plan, nOvers) {
    nOvers = nOvers || 20;
    var nb = plan.length, i, j, k;
    var q = plan.map(function (p) { return [p.pp || 0, p.mid || 0, p.death || 0]; });
    var cap = q.map(function (x) { return Math.min(4, Math.round(x[0] + x[1] + x[2])); });
    var sum = function (a) { return a.reduce(function (s, x) { return s + x; }, 0); };
    if (sum(cap) < nOvers) {
      var order = q.map(function (x, i) { return [-(x[0] + x[1] + x[2]), i]; })
        .sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; }).map(function (x) { return x[1]; });
      var it = 0;
      while (sum(cap) < nOvers && it < 200) { j = order[it % nb]; if (cap[j] < 4) cap[j]++; it++; }
    }
    var used = new Array(nb).fill(0), phUsed = q.map(function () { return [0, 0, 0]; });
    var sched = [], last = -1;
    for (var o = 0; o < nOvers; o++) {
      var ph = nOvers === 20 ? PHASE_OF[o] : 2, R = nOvers - o, best = -1, bestS = -1e9;
      for (j = 0; j < nb; j++) {
        if (j === last || used[j] >= cap[j]) continue;
        var rem = cap.map(function (c, i) { return c - used[i]; });
        rem[j] -= 1;
        var R2 = R - 1, ok = sum(rem) >= R2;
        for (k = 0; k < nb && ok; k++) {
          var lim = k === j ? Math.floor(R2 / 2) : Math.floor((R2 + 1) / 2);
          if (rem[k] > lim) ok = false;
        }
        if (!ok) continue;
        var s = (q[j][ph] - phUsed[j][ph]) * 10 + (cap[j] - used[j]) * 0.1 - j * 1e-4;
        if (s > bestS) { best = j; bestS = s; }
      }
      if (best < 0) {
        var bu = 1e9;
        for (j = 0; j < nb; j++) if (j !== last && used[j] < bu) { bu = used[j]; best = j; }
        if (best < 0) best = 0;
      }
      sched.push(plan[best].id);
      used[best]++; phUsed[best][ph]++; last = best;
    }
    return sched;
  }

  // ---------------------------------------------------------------- innings
  // user conditions: {group: option} -> summed {all, pace, spin, i1, i2} 11-vectors (sim_params.conditions)
  function conditionTerms(P, conditions) {
    if (!conditions) return null;
    var out = {}, tbl = P.raw.conditions || {};
    ["all", "pace", "spin", "i1", "i2"].forEach(function (k) { out[k] = new Array(NC).fill(0); });
    Object.keys(conditions).forEach(function (g) {
      var t = (tbl[g] || {})[conditions[g]];
      if (!t) throw new Error("unknown condition " + g + "=" + conditions[g]);
      Object.keys(t).forEach(function (k) { if (out[k]) for (var c = 0; c < NC; c++) out[k][c] += t[k][c]; });
    });
    return out;
  }

  function simInnings(P, rng, n, order, sched, V, env, inn, target, maxWkts, maxOvers, track, envPh, shock, cond) {
    maxWkts = maxWkts || 10; maxOvers = maxOvers || 20;
    var nbat = order.length, i, c, o;
    var bt = order.map(function (id) { return batterOf(P, id); });
    var bowlIds = [];
    sched.forEach(function (b) { if (bowlIds.indexOf(b) < 0) bowlIds.push(b); });
    var nbw = bowlIds.length;
    // per-over (batter x class) logit matrices
    var M = [], bwIdx = [];
    for (o = 0; o < maxOvers; o++) {
      var ph = maxOvers === 20 ? PHASE_OF[o] : 2;
      var bw = bowlerOf(P, sched[o]);
      var spin = bw.spin ? 1 : 0;
      var sub = P.raw.sub[bw.sub], subl = P.raw.sub_lhb[bw.sub], subph = P.raw.sub_phase[bw.sub][ph];
      var mo = new Float64Array(nbat * NC);
      for (i = 0; i < nbat; i++) {
        var b = bt[i], lh = b.hand === "L" ? 1 : 0;
        var h2h = (P.raw.pairs && P.raw.pairs[order[i]] && P.raw.pairs[order[i]][sched[o]]) || null;
        for (c = 0; c < NC; c++) {
          var v = env[c] + (envPh ? (envPh.length === 2 ? envPh[inn - 1][ph][c] : envPh[ph][c]) : 0) +
            (cond ? cond.all[c] + (spin ? cond.spin[c] : cond.pace[c]) + (inn === 2 ? cond.i2[c] : cond.i1[c]) : 0) +
            (b.ty && b.ty[bw.sub] ? b.ty[bw.sub][c] : 0) + (h2h ? h2h[c] : 0) + V.base[c] + (inn === 2 ? V.i2[c] : 0) + spin * V.spin[c] + sub[c] + subph[c] + bw.b[c] +
            (ph === 0 ? bw.pp[c] : 0) + (ph === 2 ? bw.de[c] : 0) +
            b.b[c] + (ph === 0 ? b.pp[c] : 0) + (ph === 2 ? b.de[c] : 0) + spin * b.sp[c] +
            lh * (subl[c] + bw.lh[c]);
          mo[i * NC + c] = v;
        }
      }
      M.push(mo);
      bwIdx.push(bowlIds.indexOf(sched[o]));
    }
    var EA = bt.map(function (b) { return b.ea; });
    var res = {
      score: new Int32Array(n), wk: new Int32Array(n), pp: new Int32Array(n), fow1: new Int32Array(n),
      fours: new Int32Array(n), sixes: new Int32Array(n), wides: new Int32Array(n), extras: new Int32Array(n),
      legal: new Int32Array(n), bowlIds: bowlIds
    };
    if (track) {
      res.batRuns = new Int16Array(n * nbat); res.batBalls = new Int16Array(n * nbat);
      res.bat4 = new Int16Array(n * nbat); res.bat6 = new Int16Array(n * nbat);
      res.batOut = new Uint8Array(n * nbat); res.batted = new Uint8Array(n * nbat);
      res.bowlBalls = new Int16Array(n * nbw); res.bowlRuns = new Int16Array(n * nbw);
      res.bowlWkts = new Int16Array(n * nbw);
    }
    var lg = new Float64Array(NC), pr = new Float64Array(NC);
    var bfArr = new Int32Array(nbat), brArr = new Int32Array(nbat);
    var exW = P.ex.wide_runs, exN = P.ex.nb_bat, exB = P.ex.bye_runs, exR = P.ex.runout_runs;
    for (var s = 0; s < n; s++) {
      var score = 0, wk = 0, legal = 0, stk = 0, nst = 1, nxt = 2, done = false, free = false;
      var pp = 0, fow1 = -1, fours = 0, sixes = 0, wides = 0, extras = 0;
      var tgt = target ? target[s] : null;
      bfArr.fill(0); brArr.fill(0);
      var off = s * nbat, offw = s * nbw;
      if (track) { res.batted[off] = 1; res.batted[off + 1] = 1; }
      for (o = 0; o < maxOvers && !done; o++) {
        var ph2 = maxOvers === 20 ? PHASE_OF[o] : 2, oo = maxOvers === 20 ? o : 19;
        var mo2 = M[o], j = bwIdx[o], lio = 0;
        for (var step = 0; step < 30 && !done && lio < 6; step++) {
          var sbf = bfArr[stk];
          var baseOff = (((inn - 1) * 20 + oo) * 8 + Math.min(wk, 7)) * NC;
          var bfb = bucketIdx(P.bfEdges, sbf), bfOff = (ph2 * 9 + bfb) * NC;
          var chOff = -1, cwOff = -1, chHiOff = -1;
          if (tgt !== null) {
            var bl = Math.max(maxOvers * 6 - legal, 1);
            var rrr = (tgt - score) * 6.0 / bl;
            var rbk = Math.min(Math.max(rrrIdx(P.rrrEdges, rrr), 0), 7);
            chOff = (ph2 * 8 + rbk) * NC;
            if (P.chaseHi && rrr >= 20) chHiOff = (ph2 * 2 + (rrr >= 24 ? 1 : 0)) * NC;
            if (P.chaseW) { var wih = 10 - wk; cwOff = ((ph2 * 8 + rbk) * 3 + (wih <= 3 ? 0 : (wih <= 6 ? 1 : 2))) * NC; }
          }
          var early = sbf < P.earlyBf ? 1 : 0, ea = EA[stk], mx = -1e9;
          for (c = 0; c < NC; c++) {
            var x = P.base[baseOff + c] + mo2[stk * NC + c] + P.bf[bfOff + c] + early * ea[c];
            if (chOff >= 0) x += P.chase[chOff + c];
            if (cwOff >= 0) x += P.chaseW[cwOff + c];
            if (chHiOff >= 0) x += P.chaseHi[chHiOff + c];
            lg[c] = x;
          }
          if (shock) { var zs = shock[s]; for (c = 0; c < NC; c++) lg[c] += zs * P.shockDir[c]; }
          if (free) lg[WICKET] = -50;
          if (step >= 14) { lg[WIDE] = -50; lg[NOBALL] = -50; }
          for (c = 0; c < NC; c++) if (lg[c] > mx) mx = lg[c];
          var tot = 0;
          for (c = 0; c < NC; c++) { pr[c] = Math.exp(lg[c] - mx); tot += pr[c]; }
          var u = rng() * tot, k = NC - 1, acc = 0;
          for (c = 0; c < NC; c++) { acc += pr[c]; if (u < acc) { k = c; break; } }
          var runs = 0, batr = BAT_RUNS[k], ran = batr, conc = 0, isl = k > NOBALL;
          var batScoring = k >= R0 || k === NOBALL || k === RUNOUT;
          if (k === WIDE) { var wr = draw(exW, rng()); runs = wr; conc = wr; ran = wr === 5 ? 0 : wr - 1; }
          else if (k === NOBALL) { var nbr = draw(exN, rng()); batr = nbr; ran = (nbr === 4 || nbr === 6) ? 0 : nbr; runs = 1 + nbr; conc = 1 + nbr; }
          else if (k === BYES) { var byr = draw(exB, rng()); runs = byr; ran = byr === 4 ? 0 : byr; }
          else if (k === RUNOUT) { var ror = draw(exR, rng()); batr = ror; ran = ror; }
          if (batScoring && k !== NOBALL) { runs = batr; conc = batr; }
          if (batScoring) brArr[stk] += batr;
          if (k !== WIDE) bfArr[stk] += 1;
          var hit4 = batScoring && k !== RUNOUT && batr === 4, hit6 = batScoring && k !== RUNOUT && batr === 6;
          if (track) {
            if (batScoring) res.batRuns[off + stk] += batr;
            if (k !== WIDE) res.batBalls[off + stk] += 1;
            if (hit4) res.bat4[off + stk] += 1;
            if (hit6) res.bat6[off + stk] += 1;
            if (isl) res.bowlBalls[offw + j] += 1;
            res.bowlRuns[offw + j] += conc;
            if (k === WICKET) res.bowlWkts[offw + j] += 1;
          }
          if (hit4) fours++;
          if (hit6) sixes++;
          if (k === WIDE) wides++;
          if (k <= BYES) extras += (k === NOBALL ? 1 : runs);
          score += runs;
          if (isl) { legal++; lio++; }
          free = k === NOBALL ? true : (isl ? false : free);
          var faced = stk;
          if (ran % 2 === 1) { var t0 = stk; stk = nst; nst = t0; }
          if (k === WICKET || k === RUNOUT) {
            var roStriker = rng() < P.qRoStriker;
            var victim = faced;
            if (k === RUNOUT && !roStriker) victim = (stk === faced) ? nst : stk;
            if (track) res.batOut[off + victim] = 1;
            if (fow1 < 0) fow1 = score;
            wk++;
            if (nxt < nbat) {
              if (stk === victim) stk = nxt; else nst = nxt;
              if (track) res.batted[off + nxt] = 1;
            }
            nxt++;
            if (wk >= Math.min(maxWkts, nbat - 1)) done = true;
          }
          if (tgt !== null && score >= tgt) done = true;
        }
        if (o === 5) pp = score;
        if (!done) { var t1 = stk; stk = nst; nst = t1; }
        if (legal >= maxOvers * 6) done = true;
      }
      if (o <= 5 || maxOvers < 6) pp = score;  // innings ended inside the powerplay
      res.score[s] = score; res.wk[s] = wk; res.pp[s] = pp; res.fow1[s] = fow1 < 0 ? score : fow1;
      res.fours[s] = fours; res.sixes[s] = sixes; res.wides[s] = wides; res.extras[s] = extras; res.legal[s] = legal;
    }
    return res;
  }

  // ---------------------------------------------------------------- match
  function deathBowler(sched) {
    var last5 = sched.slice(15), best = last5[0], bc = 0;
    last5.forEach(function (b) {
      var c = last5.filter(function (x) { return x === b; }).length;
      if (c > bc) { bc = c; best = b; }
    });
    return best;
  }

  function gauss(rng) { // Box-Muller
    var u = 0, v = 0;
    while (u === 0) u = rng();
    v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function simOneWay(P, A, B, V, env, n, rng, first, envPh, cond) {
    var sa = A.schedule || bowlingSchedule(A.plan), sb = B.schedule || bowlingSchedule(B.plan);
    var oa = A.order.slice(0, 11), ob = B.order.slice(0, 11);
    var F = first === "A" ? { k: "A", o: oa, s: sa } : { k: "B", o: ob, s: sb };
    var S = first === "A" ? { k: "B", o: ob, s: sb } : { k: "A", o: oa, s: sa };
    var shock = null, i;
    if (P.shockSd > 0) { shock = new Float64Array(n); for (i = 0; i < n; i++) shock[i] = gauss(rng) * P.shockSd; }
    var sh1 = shock, sh2 = shock;
    if (P.shockInnSd > 0) {  // independent innings-level component on top of the shared match shock
      sh1 = new Float64Array(n); sh2 = new Float64Array(n);
      for (i = 0; i < n; i++) sh1[i] = (shock ? shock[i] : 0) + gauss(rng) * P.shockInnSd;
      for (i = 0; i < n; i++) sh2[i] = (shock ? shock[i] : 0) + gauss(rng) * P.shockInnSd;
    }
    var i1 = simInnings(P, rng, n, F.o, S.s, V, env, 1, null, 10, 20, true, envPh, sh1, cond);
    var tg = new Int32Array(n);
    for (i = 0; i < n; i++) tg[i] = i1.score[i] + 1;
    var i2 = simInnings(P, rng, n, S.o, F.s, V, env, 2, tg, 10, 20, true, envPh, sh2, cond);
    var firstWins = new Float64Array(n), tie = new Uint8Array(n), tied = [];
    for (i = 0; i < n; i++) {
      if (i1.score[i] > i2.score[i]) firstWins[i] = 1;
      else if (i1.score[i] === i2.score[i]) { tie[i] = 1; tied.push(i); }
    }
    if (tied.length) {
      var m = tied.length;
      var sh2 = null;
      if (shock) { sh2 = new Float64Array(m); for (i = 0; i < m; i++) sh2[i] = shock[tied[i]]; }
      var so1 = simInnings(P, rng, m, S.o.slice(0, 3), [deathBowler(F.s)], V, env, 1, null, 2, 1, false, envPh, sh2, cond);
      var t2 = new Int32Array(m);
      for (i = 0; i < m; i++) t2[i] = so1.score[i] + 1;
      var so2 = simInnings(P, rng, m, F.o.slice(0, 3), [deathBowler(S.s)], V, env, 2, t2, 2, 1, false, envPh, sh2, cond);
      for (i = 0; i < m; i++) {
        var fw = so2.score[i] > so1.score[i] ? 1 : 0;
        if (so2.score[i] === so1.score[i]) fw = rng() < 0.5 ? 1 : 0;
        firstWins[tied[i]] = fw;
      }
    }
    var part = { first: first, tie: tie, n: n };
    part[F.k] = i1; part[S.k] = i2;
    part.winA = first === "A" ? firstWins : firstWins.map(function (x) { return 1 - x; });
    return part;
  }

  function simMatch(P, A, B, opts) {
    opts = opts || {};
    var n = opts.n || 10000, rng = makeRng(opts.seed || 1);
    var V = (opts.venue && P.raw.venues[opts.venue]) || P.raw.venue_neutral;
    var ek = opts.env || P.raw.default_env;
    var env = P.raw.env[ek], cond = conditionTerms(P, opts.conditions);
    var envPh = (P.raw.env_phase_inn || {})[ek] || (P.raw.env_phase || {})[ek] || null;
    var parts;
    if (opts.batFirst === "A" || opts.batFirst === "B") parts = [simOneWay(P, A, B, V, env, n, rng, opts.batFirst, envPh, cond)];
    else {
      var h = Math.floor(n / 2);
      parts = [simOneWay(P, A, B, V, env, h, rng, "A", envPh, cond), simOneWay(P, A, B, V, env, n - h, rng, "B", envPh, cond)];
    }
    return summarize(parts, A, B);
  }

  // ---------------------------------------------------------------- summaries
  function percentile(arr, q) { // numpy-style linear interpolation; arr is sorted
    var n = arr.length;
    if (!n) return 0;
    var pos = (q / 100) * (n - 1), lo = Math.floor(pos), hi = Math.ceil(pos);
    return arr[lo] + (arr[hi] - arr[lo]) * (pos - lo);
  }
  function quant(values, qs) {
    var a = Float64Array.from(values).sort();
    return qs.map(function (q) { return percentile(a, q); });
  }
  function mean(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return a.length ? s / a.length : 0; }
  function sd(a) { var m = mean(a), s = 0; for (var i = 0; i < a.length; i++) s += (a[i] - m) * (a[i] - m); return Math.sqrt(s / a.length); }
  function cat(parts, side, key) {
    var len = 0;
    parts.forEach(function (p) { len += p[side][key].length; });
    var out = new Float64Array(len), o = 0;
    parts.forEach(function (p) { out.set(p[side][key], o); o += p[side][key].length; });
    return out;
  }
  var Q5 = [5, 25, 50, 75, 95], Q10 = [10, 25, 50, 75, 90];

  function summarize(parts, A, B) {
    var N = 0;
    parts.forEach(function (p) { N += p.n; });
    var winA = [], tieN = 0;
    parts.forEach(function (p) { for (var i = 0; i < p.n; i++) { winA.push(p.winA[i]); tieN += p.tie[i]; } });
    var out = { n: N, p_win_A: mean(winA), p_tie: tieN / N };
    [["A", A], ["B", B]].forEach(function (pair) {
      var side = pair[0], team = pair[1], other = side === "A" ? "B" : "A";
      var tot = cat(parts, side, "score");
      var tm = {
        total_mean: mean(tot), total_sd: sd(tot), total_q: quant(tot, Q5),
        wkts_mean: mean(cat(parts, side, "wk")), pp_mean: mean(cat(parts, side, "pp")), pp_q: quant(cat(parts, side, "pp"), Q5),
        fow1_mean: mean(cat(parts, side, "fow1")), fow1_q: quant(cat(parts, side, "fow1"), Q5),
        fours_mean: mean(cat(parts, side, "fours")), sixes_mean: mean(cat(parts, side, "sixes")),
        sixes_q: quant(cat(parts, side, "sixes"), Q5), fours_q: quant(cat(parts, side, "fours"), Q5),
        wides_mean: mean(cat(parts, side, "wides")), extras_mean: mean(cat(parts, side, "extras"))
      };
      parts.forEach(function (p) {
        var isFirst = p.first === side;
        tm[(isFirst ? "bat1" : "bat2") + "_total_mean"] = mean(p[side].score);
        var w = p.winA, s = 0;
        for (var i = 0; i < p.n; i++) s += side === "A" ? w[i] : 1 - w[i];
        tm[isFirst ? "p_win_bat1" : "p_win_bat2"] = s / p.n;
      });
      // batting
      var order = team.order.slice(0, 11), nb = order.length, players = {};
      var runsBy = order.map(function () { return []; }), stats = order.map(function () {
        return { bat: 0, out: 0, duck: 0, balls: 0, f: 0, s6: 0, top: 0 };
      });
      parts.forEach(function (p) {
        var r = p[side];
        for (var i = 0; i < p.n; i++) {
          var off = i * nb, top = -1, ntop = 0, k;
          for (k = 0; k < nb; k++) if (r.batRuns[off + k] > top) top = r.batRuns[off + k];
          for (k = 0; k < nb; k++) if (r.batted[off + k] && r.batRuns[off + k] === top) ntop++;
          for (k = 0; k < nb; k++) {
            var rk = r.batRuns[off + k], st = stats[k];
            runsBy[k].push(rk);
            st.bat += r.batted[off + k]; st.out += r.batOut[off + k];
            if (r.batOut[off + k] && rk === 0) st.duck++;
            st.balls += r.batBalls[off + k]; st.f += r.bat4[off + k]; st.s6 += r.bat6[off + k];
            if (r.batted[off + k] && rk === top && ntop > 0) st.top += 1 / ntop;
          }
        }
      });
      order.forEach(function (pid, k) {
        var rr = runsBy[k], st = stats[k], pr = {};
        TOP_THRESH.forEach(function (t) { var c = 0; rr.forEach(function (x) { if (x >= t) c++; }); pr[String(t)] = c / N; });
        players[pid] = {
          bat_pos: k + 1, p_bat: st.bat / N, runs_mean: mean(rr), runs_q: quant(rr, Q10), p_runs: pr,
          p_duck: st.duck / N, balls_mean: st.balls / N, fours_mean: st.f / N, sixes_mean: st.s6 / N,
          p_out: st.out / N, p_top_bat: st.top / N
        };
      });
      // bowling (this team's bowlers appear in the other side's innings)
      var ids = parts[0][other].bowlIds, nw = ids.length;
      var acc = ids.map(function () { return { b: 0, r: 0, w: [], top: 0 }; });
      parts.forEach(function (p) {
        var r = p[other];
        for (var i = 0; i < p.n; i++) {
          var off = i * nw, best = -1e9, nbst = 0, k;
          for (k = 0; k < nw; k++) { var key = r.bowlWkts[off + k] * 1000 - r.bowlRuns[off + k]; if (key > best) best = key; }
          for (k = 0; k < nw; k++) if (r.bowlWkts[off + k] * 1000 - r.bowlRuns[off + k] === best) nbst++;
          for (k = 0; k < nw; k++) {
            var a = acc[k];
            a.b += r.bowlBalls[off + k]; a.r += r.bowlRuns[off + k]; a.w.push(r.bowlWkts[off + k]);
            if (r.bowlWkts[off + k] * 1000 - r.bowlRuns[off + k] === best) a.top += 1 / nbst;
          }
        }
      });
      ids.forEach(function (pid, k) {
        var a = acc[k], d = players[pid] || (players[pid] = { bat_pos: null }), pw = {};
        [1, 2, 3, 4, 5].forEach(function (t) { var c = 0; a.w.forEach(function (x) { if (x >= t) c++; }); pw[String(t)] = c / N; });
        d.overs_mean = a.b / N / 6; d.wkts_mean = mean(a.w); d.p_wkts = pw; d.conceded_mean = a.r / N;
        d.econ = a.r / Math.max(a.b, 1) * 6; d.p_top_bowl = a.top / N;
      });
      tm.players = players;
      out[side] = tm;
    });
    out.margin_mean_A = out.A.total_mean - out.B.total_mean;
    return out;
  }

  // ---------------------------------------------------------------- raw (poolable) mode
  // Dense integer histograms: h[v] = number of sims with value v (v >= 0). Pool runs from several workers
  // with mergeRaw(a, b); summarizeRaw(raw) gives means / quantiles / P(>= t) from the pooled counts.
  function hadd(h, v) { if (v < 0) v = 0; while (h.length <= v) h.push(0); h[v] += 1; }
  function hmerge(a, b) {
    var out = a.slice();
    for (var i = 0; i < b.length; i++) { if (i >= out.length) out.push(0); out[i] += b[i]; }
    return out;
  }
  function newTeamRaw() {
    return { total: [], pp: [], sixes: [], fours: [], fow1: [], wkts: [], wides: [], extras: [], wins: 0, n: 0,
             bat1: { n: 0, wins: 0, total: [] }, bat2: { n: 0, wins: 0, total: [] }, players: {} };
  }
  function newPlayerRaw() {
    return { runs: [], balls: [], fours: [], sixes: [], wkts: [], conceded: [], legal_balls: 0,
             batted: 0, out: 0, duck: 0, top_bat: 0, top_bowl: 0, n_bat: 0, n_bowl: 0 };
  }

  function rawFromParts(parts, A, B, nested) {
    var raw = { version: 2, n: 0, ties: 0, first_innings_total: [], match_total: [], match_fours: [], match_sixes: [],
                bat1_win_runs: [], bat2_win_wkts: [], bat2_win_balls: [], bat1_wins_in_20: 0, bat2_wins_in_20: 0,
                A: newTeamRaw(), B: newTeamRaw(), names: { A: A.name, B: B.name } };
    if (!nested) {
      raw.by_bat_first = {};
      parts.forEach(function (p) { raw.by_bat_first[p.first] = rawFromParts([p], A, B, true); });
    }
    parts.forEach(function (p) {
      var first = p.first, second = first === "A" ? "B" : "A";
      raw.n += p.n;
      for (var i = 0; i < p.n; i++) {
        raw.ties += p.tie[i];
        var s1 = p[first].score[i], s2 = p[second].score[i];
        hadd(raw.first_innings_total, s1);
        hadd(raw.match_total, s1 + s2);
        hadd(raw.match_fours, p[first].fours[i] + p[second].fours[i]);
        hadd(raw.match_sixes, p[first].sixes[i] + p[second].sixes[i]);
        if (s1 > s2) { raw.bat1_wins_in_20++; hadd(raw.bat1_win_runs, s1 - s2); }
        else if (s2 > s1) {
          raw.bat2_wins_in_20++; hadd(raw.bat2_win_wkts, 10 - p[second].wk[i]); hadd(raw.bat2_win_balls, 120 - p[second].legal[i]);
        }
      }
      [["A", A], ["B", B]].forEach(function (pair) {
        var side = pair[0], team = pair[1], other = side === "A" ? "B" : "A", T = raw[side], r = p[side], i, k;
        var cond = p.first === side ? T.bat1 : T.bat2;
        var order = team.order.slice(0, 11), nb = order.length;
        var ro = p[other], ids = ro.bowlIds, nw = ids.length;
        order.forEach(function (pid) { if (!T.players[pid]) T.players[pid] = newPlayerRaw(); });
        ids.forEach(function (pid) { if (!T.players[pid]) T.players[pid] = newPlayerRaw(); });
        for (i = 0; i < p.n; i++) {
          var win = side === "A" ? p.winA[i] : 1 - p.winA[i];
          T.n++; T.wins += win; cond.n++; cond.wins += win; hadd(cond.total, r.score[i]);
          hadd(T.total, r.score[i]); hadd(T.pp, r.pp[i]); hadd(T.sixes, r.sixes[i]); hadd(T.fours, r.fours[i]);
          hadd(T.fow1, r.fow1[i]); hadd(T.wkts, r.wk[i]); hadd(T.wides, r.wides[i]); hadd(T.extras, r.extras[i]);
          var off = i * nb, top = -1, ntop = 0;
          for (k = 0; k < nb; k++) if (r.batRuns[off + k] > top) top = r.batRuns[off + k];
          for (k = 0; k < nb; k++) if (r.batted[off + k] && r.batRuns[off + k] === top) ntop++;
          for (k = 0; k < nb; k++) {
            var P_ = T.players[order[k]], rk = r.batRuns[off + k];
            P_.n_bat++;
            hadd(P_.runs, rk); hadd(P_.balls, r.batBalls[off + k]); hadd(P_.fours, r.bat4[off + k]); hadd(P_.sixes, r.bat6[off + k]);
            P_.batted += r.batted[off + k]; P_.out += r.batOut[off + k];
            if (r.batOut[off + k] && rk === 0) P_.duck++;
            if (r.batted[off + k] && rk === top && ntop > 0) P_.top_bat += 1 / ntop;
          }
          var offw = i * nw, best = -1e9, nbst = 0;
          for (k = 0; k < nw; k++) { var key = ro.bowlWkts[offw + k] * 1000 - ro.bowlRuns[offw + k]; if (key > best) best = key; }
          for (k = 0; k < nw; k++) if (ro.bowlWkts[offw + k] * 1000 - ro.bowlRuns[offw + k] === best) nbst++;
          for (k = 0; k < nw; k++) {
            var Q = T.players[ids[k]];
            Q.n_bowl++;
            hadd(Q.wkts, ro.bowlWkts[offw + k]); hadd(Q.conceded, ro.bowlRuns[offw + k]); Q.legal_balls += ro.bowlBalls[offw + k];
            if (ro.bowlWkts[offw + k] * 1000 - ro.bowlRuns[offw + k] === best) Q.top_bowl += 1 / nbst;
          }
        }
      });
    });
    return raw;
  }

  /** Same inputs as simMatch; returns poolable integer counts (see mergeRaw / summarizeRaw). */
  function simMatchRaw(P, A, B, opts) {
    opts = opts || {};
    var n = opts.n || 10000, rng = makeRng(opts.seed || 1);
    var V = (opts.venue && P.raw.venues[opts.venue]) || P.raw.venue_neutral;
    var ek = opts.env || P.raw.default_env;
    var env = P.raw.env[ek], cond = conditionTerms(P, opts.conditions);
    var envPh = (P.raw.env_phase_inn || {})[ek] || (P.raw.env_phase || {})[ek] || null;
    var parts;
    if (opts.batFirst === "A" || opts.batFirst === "B") parts = [simOneWay(P, A, B, V, env, n, rng, opts.batFirst, envPh, cond)];
    else {
      var h = Math.floor(n / 2);
      parts = [simOneWay(P, A, B, V, env, h, rng, "A", envPh, cond), simOneWay(P, A, B, V, env, n - h, rng, "B", envPh, cond)];
    }
    return rawFromParts(parts, A, B, false);
  }

  function mergeTeam(a, b) {
    var o = { n: a.n + b.n, wins: a.wins + b.wins, players: {} };
    ["total", "pp", "sixes", "fours", "fow1", "wkts", "wides", "extras"].forEach(function (k) { o[k] = hmerge(a[k], b[k]); });
    ["bat1", "bat2"].forEach(function (k) {
      o[k] = { n: a[k].n + b[k].n, wins: a[k].wins + b[k].wins, total: hmerge(a[k].total, b[k].total) };
    });
    var ids = Object.keys(a.players).concat(Object.keys(b.players).filter(function (x) { return !(x in a.players); }));
    ids.forEach(function (pid) {
      var x = a.players[pid] || newPlayerRaw(), y = b.players[pid] || newPlayerRaw(), z = {};
      ["runs", "balls", "fours", "sixes", "wkts", "conceded"].forEach(function (k) { z[k] = hmerge(x[k], y[k]); });
      ["legal_balls", "batted", "out", "duck", "top_bat", "top_bowl", "n_bat", "n_bowl"].forEach(function (k) { z[k] = x[k] + y[k]; });
      o.players[pid] = z;
    });
    return o;
  }

  /** Pool two raw results of the same matchup (e.g. from two workers with different seeds). */
  function mergeRaw(a, b) {
    var o = { version: a.version, n: a.n + b.n, ties: a.ties + b.ties, names: a.names,
              A: mergeTeam(a.A, b.A), B: mergeTeam(a.B, b.B),
              bat1_wins_in_20: (a.bat1_wins_in_20 || 0) + (b.bat1_wins_in_20 || 0),
              bat2_wins_in_20: (a.bat2_wins_in_20 || 0) + (b.bat2_wins_in_20 || 0) };
    ["first_innings_total", "match_total", "match_fours", "match_sixes", "bat1_win_runs", "bat2_win_wkts",
     "bat2_win_balls"].forEach(function (k) { o[k] = hmerge(a[k] || [], b[k] || []); });
    if (a.by_bat_first || b.by_bat_first) {
      o.by_bat_first = {};
      ["A", "B"].forEach(function (k) {
        var x = (a.by_bat_first || {})[k], y = (b.by_bat_first || {})[k];
        if (x && y) o.by_bat_first[k] = mergeRaw(x, y); else if (x || y) o.by_bat_first[k] = x || y;
      });
    }
    return o;
  }

  function hstats(h) {
    var n = 0, s = 0, i;
    for (i = 0; i < h.length; i++) { n += h[i]; s += i * h[i]; }
    var q = function (pq) {
      var target = pq / 100 * (n - 1), acc = 0;
      for (var v = 0; v < h.length; v++) { acc += h[v]; if (acc > target) return v; }
      return h.length - 1;
    };
    var ge = function (t) { var c = 0; for (var v = t; v < h.length; v++) c += h[v]; return n ? c / n : 0; };
    return { n: n, mean: n ? s / n : 0, q: q, ge: ge, pmf: h.map(function (c) { return n ? c / n : 0; }) };
  }

  /** Convenience: summary numbers from (pooled) raw counts. Quantiles are the lower order statistic. */
  function summarizeRaw(raw) {
    var out = { n: raw.n, p_win_A: raw.A.wins / raw.n, p_tie: raw.ties / raw.n,
                first_innings_total: hstats(raw.first_innings_total).mean, match_total: hstats(raw.match_total).mean };
    ["A", "B"].forEach(function (side) {
      var T = raw[side], st = hstats(T.total), o = { total_mean: st.mean, total_q: [5, 25, 50, 75, 95].map(st.q),
        pp_mean: hstats(T.pp).mean, sixes_mean: hstats(T.sixes).mean, fours_mean: hstats(T.fours).mean,
        fow1_mean: hstats(T.fow1).mean, wkts_mean: hstats(T.wkts).mean,
        p_win_bat1: T.bat1.n ? T.bat1.wins / T.bat1.n : null, p_win_bat2: T.bat2.n ? T.bat2.wins / T.bat2.n : null,
        players: {} };
      Object.keys(T.players).forEach(function (pid) {
        var p = T.players[pid], d = {};
        if (p.n_bat) {
          var r = hstats(p.runs);
          d.runs_mean = r.mean; d.p_runs = {}; [10, 20, 30, 40, 50, 75, 100].forEach(function (t) { d.p_runs[String(t)] = r.ge(t); });
          d.balls_mean = hstats(p.balls).mean; d.fours_mean = hstats(p.fours).mean; d.sixes_mean = hstats(p.sixes).mean;
          d.p_bat = p.batted / p.n_bat; d.p_out = p.out / p.n_bat; d.p_duck = p.duck / p.n_bat; d.p_top_bat = p.top_bat / p.n_bat;
        }
        if (p.n_bowl) {
          var w = hstats(p.wkts), c = hstats(p.conceded);
          d.wkts_mean = w.mean; d.p_wkts = {}; [1, 2, 3, 4, 5].forEach(function (t) { d.p_wkts[String(t)] = w.ge(t); });
          d.conceded_mean = c.mean; d.overs_mean = p.legal_balls / p.n_bowl / 6;
          d.econ = p.legal_balls ? c.mean * p.n_bowl / p.legal_balls * 6 : null; d.p_top_bowl = p.top_bowl / p.n_bowl;
        }
        o.players[pid] = d;
      });
      out[side] = o;
    });
    return out;
  }

  return { prepare: prepare, simMatch: simMatch, simInnings: simInnings, bowlingSchedule: bowlingSchedule,
           makeRng: makeRng, summarize: summarize,
           simMatchRaw: simMatchRaw, mergeRaw: mergeRaw, summarizeRaw: summarizeRaw };
});
