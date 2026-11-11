/*
 * WNBA possession-level Monte Carlo engine (pure, DOM-free).
 * Mirrors models/wnba/sim.py (vectorised Python version); see schema.md / method.md.
 *
 * Browser:  <script src="sim.js"></script>  -> window.WNBASim
 * Node:     const WNBASim = require('./sim.js')
 *
 * WNBASim.simulate(params, homeSpec, awaySpec, opts) -> { game, home, away, meta }
 *   params   : parsed sim_params.json
 *   homeSpec : team id (number) or { team: id, players: [{ id, min?: number, out?: bool }] }
 *   opts     : { nSims=10000, seed=1, neutral=false, home_b2b=false, away_b2b=false,
 *                home_rest_days=2, away_rest_days=2, home_travel_miles=0, away_travel_miles=0 }
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.WNBASim = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var ZONES = ['rim', 'short_mid', 'long_mid', 'corner3', 'above_break3'];
  var ZV = [2, 2, 2, 3, 3];
  var POSG = { G: 0, F: 1, C: 2 };
  var QS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95];
  var LADDER_STEP = { min: 2, pts: 2, reb: 1, ast: 1, fg3m: 1, stl: 1, blk: 1, tov: 1, pra: 2, pr: 2, pa: 2 };
  // stat slots in the per-player box
  var PTS = 0, FGA = 1, FGM = 2, FG3A = 3, FG3M = 4, FTA = 5, FTM = 6, ORB = 7, DRB = 8, AST = 9, STL = 10,
    BLK = 11, TOV = 12, SEC = 13, NST = 14;

  function expit(x) { return 1 / (1 + Math.exp(-x)); }
  function logit(p) { p = Math.min(Math.max(p, 1e-6), 1 - 1e-6); return Math.log(p / (1 - p)); }
  function clip(x, a, b) { return x < a ? a : (x > b ? b : x); }

  // ---------------------------------------------------------------- RNG
  function makeRng(seed) {
    var a = (seed >>> 0) || 1;
    var spare = null;
    function u() {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    function normal() {
      if (spare !== null) { var s = spare; spare = null; return s; }
      var u1 = u() || 1e-12, u2 = u();
      var r = Math.sqrt(-2 * Math.log(u1));
      spare = r * Math.sin(2 * Math.PI * u2);
      return r * Math.cos(2 * Math.PI * u2);
    }
    function gamma(k, theta) { // Marsaglia-Tsang, k >= 1
      var d = k - 1 / 3, c = 1 / Math.sqrt(9 * d);
      for (;;) {
        var x, v;
        do { x = normal(); v = 1 + c * x; } while (v <= 0);
        v = v * v * v;
        var uu = u();
        if (uu < 1 - 0.0331 * x * x * x * x) return d * v * theta;
        if (Math.log(uu) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v * theta;
      }
    }
    return { u: u, normal: normal, gamma: gamma };
  }

  function catSample(w, n, r) {
    var tot = 0, i;
    for (i = 0; i < n; i++) tot += w[i];
    var x = r * tot, c = 0;
    for (i = 0; i < n; i++) { c += w[i]; if (c >= x && w[i] > 0) return i; }
    for (i = n - 1; i >= 0; i--) if (w[i] > 0) return i;
    return n - 1;
  }

  // ---------------------------------------------------------------- minutes
  function scaleFill(m, fixed, total, cap) {
    m = m.slice();
    var n = m.length, target = total, i, nfree = 0;
    for (i = 0; i < n; i++) { if (fixed[i]) target -= m[i]; else if (m[i] > 0) nfree++; }
    if (nfree === 0 || target <= 0) return m;
    var lo = 0, hi = 20;
    for (var it = 0; it < 50; it++) {
      var s = 0.5 * (lo + hi), tot = 0;
      for (i = 0; i < n; i++) if (!fixed[i] && m[i] > 0) tot += Math.min(m[i] * s, cap);
      if (tot > target) hi = s; else lo = s;
    }
    for (i = 0; i < n; i++) if (!fixed[i] && m[i] > 0) m[i] = Math.min(m[i] * lo, cap);
    return m;
  }

  function reallocate(minutes, posGroup, out, fixed, cap, total) {
    cap = cap || 38; total = total || 200;
    var n = minutes.length, m = minutes.slice(), i, p;
    fixed = fixed || new Array(n).fill(false);
    for (p = 0; p < n; p++) {
      if (!out[p]) continue;
      var R = m[p]; m[p] = 0;
      if (R <= 0) continue;
      var rec = [], nrec = 0;
      for (i = 0; i < n; i++) { rec[i] = !out[i] && m[i] > 0 && !fixed[i]; if (rec[i]) nrec++; }
      if (nrec === 0) { for (i = 0; i < n; i++) { rec[i] = !out[i] && !fixed[i]; if (rec[i]) nrec++; } }
      if (nrec === 0) continue;
      var w = [], ws = 0;
      for (i = 0; i < n; i++) { w[i] = rec[i] ? Math.max(m[i], 0.5) * (posGroup[i] === posGroup[p] ? 1.5 : 1.0) : 0; ws += w[i]; }
      for (i = 0; i < n; i++) m[i] += R * w[i] / ws;
      for (var it = 0; it < 10; it++) {
        var ex = 0, any = false;
        for (i = 0; i < n; i++) if (rec[i] && m[i] > cap) { ex += m[i] - cap; m[i] = cap; any = true; }
        if (!any) break;
        var w2s = 0;
        for (i = 0; i < n; i++) if (rec[i] && m[i] < cap) w2s += w[i];
        if (w2s === 0) break;
        for (i = 0; i < n; i++) if (rec[i] && m[i] < cap) m[i] += ex * w[i] / w2s;
      }
    }
    var fx = [];
    for (i = 0; i < n; i++) { if (out[i]) m[i] = 0; fx[i] = fixed[i] || out[i]; }
    return scaleFill(m, fx, total, 40);
  }

  // ---------------------------------------------------------------- teams
  function prepareTeam(params, spec) {
    if (!params._byId) {
      params._byId = {};
      params.players.forEach(function (p) { params._byId[p.id] = p; });
    }
    if (typeof spec === 'number') spec = { team: spec };
    var plist = spec.players;
    if (!plist) plist = params.players.filter(function (p) { return p.team === spec.team; }).map(function (p) { return { id: p.id }; });
    var rows = plist.map(function (x) { var r = params._byId[x.id]; if (!r) throw new Error('unknown player ' + x.id); return r; });
    var n = rows.length, T = { n: n, tid: spec.team, ids: [], names: [] };
    var keys = ['O', 'D', 'usg', 'tov', 'sfd', 'trip3', 'and1', 'ftp', 'ast', 'astd', 'orb', 'drb', 'stl', 'blk',
      'pace_o', 'pace_d', 'ff_tov_D', 'ff_ftr_D', 'min_sd'];
    keys.forEach(function (k) { T[k] = rows.map(function (r) { return +r[k]; }); });
    T.mix = rows.map(function (r) { return ZONES.map(function (z) { return r['mix_' + z]; }); });
    T.lfg = rows.map(function (r) { return ZONES.map(function (z) { return logit(r['fg_' + z]); }); });
    T.posg = rows.map(function (r) { return POSG[r.pos_group] !== undefined ? POSG[r.pos_group] : 1; });
    T.ids = rows.map(function (r) { return r.id; });
    T.names = rows.map(function (r) { return r.name; });
    var fixed = plist.map(function (x) { return x.min !== undefined && x.min !== null; });
    var out = plist.map(function (x) { return !!x.out; });
    var m = plist.map(function (x, i) { return fixed[i] ? +x.min : rows[i].min; });
    T.minutes = reallocate(m, T.posg, out, fixed, params.sim.realloc_cap, 200);
    T.out = out;
    var flag = rows.map(function (r, i) { return !!r.starter && !out[i]; });
    var order = []; for (var i = 0; i < n; i++) order.push(i);
    order.sort(function (a, b) { return (flag[b] - flag[a]) || (T.minutes[b] - T.minutes[a]) || (a - b); });
    T.starter = new Array(n).fill(false);
    for (i = 0; i < Math.min(5, n); i++) T.starter[order[i]] = true;
    return T;
  }

  function contextPts100(prm, o) {
    var c = prm.context, P = prm.league.poss_per_team_game, mh = 0;
    if (!o.neutral) mh += c.hca_pts;
    mh += c.b2b_pts * ((o.home_b2b ? 1 : 0) - (o.away_b2b ? 1 : 0));
    var rh = clip(o.home_rest_days === undefined ? 2 : o.home_rest_days, 1, 4) - 1;
    var ra = clip(o.away_rest_days === undefined ? 2 : o.away_rest_days, 1, 4) - 1;
    mh += c.rest_day_pts * (rh - ra);
    mh += c.travel_pts_per_1000mi * ((o.home_travel_miles || 0) - (o.away_travel_miles || 0)) / 1000;
    return [(mh / 2) / P * 100, -(mh / 2) / P * 100];
  }

  // ---------------------------------------------------------------- calibration of a matchup
  function calibrate(prm, To, Td, L, M, ctx, paceOff, paceDef) {
    var lg = prm.league, sim = prm.sim, i, z, k;
    var w = [], t = [], f = [], g = [], us = 0;
    for (i = 0; i < 5; i++) us += To.usg[L[i]];
    var dT = 0, dF = 0, A = 0, B = 0, Os = 0, Ds = 0, blk = 0, stl = 0, po = 0, pd = 0;
    for (i = 0; i < 5; i++) {
      dT -= Td.ff_tov_D[M[i]]; dF -= Td.ff_ftr_D[M[i]];
      A += To.orb[L[i]]; B += Td.drb[M[i]];
      Os += To.O[L[i]]; Ds += Td.D[M[i]];
      blk += Td.blk[M[i]]; stl += Td.stl[M[i]];
      po += To.pace_o[L[i]]; pd += Td.pace_d[M[i]];
    }
    dT = dT / 100 * sim.ff_def_weight; dF = dF / 100 * sim.ff_def_weight;
    var sT = Math.log(clip((lg.tov_per_poss + dT) / lg.tov_per_poss, 0.5, 1.6));
    var sF = Math.log(clip((lg.ft_trips_per_poss + dF) / lg.ft_trips_per_poss, 0.5, 1.6));
    for (i = 0; i < 5; i++) {
      var p = L[i];
      w[i] = To.usg[p] / us;
      var ti = expit(logit(To.tov[p]) + sT), fi = expit(logit(To.sfd[p]) + sF);
      var tf = ti + fi, sc = tf > 0.9 ? 0.9 / tf : 1;
      t[i] = ti * sc; f[i] = fi * sc; g[i] = 1 - t[i] - f[i];
    }
    A /= lg.orb_player_credit; B /= lg.drb_player_credit;
    var porb = A / (A + B), porbft = porb * lg.orb_rate_ft / lg.orb_rate;
    var target = (lg.ortg + Os - Ds + ctx) / 100;
    var fixedPts = 0, fixedC = 0;
    for (i = 0; i < 5; i++) {
      var pp = L[i];
      fixedPts += w[i] * f[i] * (2 + To.trip3[pp]) * To.ftp[pp];
      fixedC += w[i] * f[i] * (1 - To.ftp[pp]);
    }
    fixedC *= porbft;
    var d = 0;
    for (k = 0; k < sim.newton_iter; k++) {
      var E = fixedPts, C = fixedC, Ep = 0, Cp = 0;
      for (i = 0; i < 5; i++) {
        var q2 = L[i], a1f = To.and1[q2] * To.ftp[q2], se = 0, sc2 = 0, sep = 0, scp = 0;
        for (z = 0; z < 5; z++) {
          var q = expit(To.lfg[q2][z] + d), mx = To.mix[q2][z], dq = q * (1 - q), val = ZV[z] + a1f;
          se += mx * q * val; sc2 += mx * (1 - q); sep += mx * dq * val; scp += mx * dq;
        }
        E += w[i] * g[i] * se; C += w[i] * g[i] * sc2 * porb; Ep += w[i] * g[i] * sep; Cp -= w[i] * g[i] * scp * porb;
      }
      var ppp = E / (1 - C), dppp = (Ep * (1 - C) + E * Cp) / ((1 - C) * (1 - C));
      d = clip(d - (ppp - target) / dppp, -1.5, 1.5);
    }
    var Q = [];
    for (i = 0; i < 5; i++) { Q[i] = []; for (z = 0; z < 5; z++) Q[i][z] = expit(To.lfg[L[i]][z] + d); }
    var mu = prm.pace.first_play_sec + po + pd + paceOff + paceDef;
    return {
      w: w, t: t, f: f, Q: Q, porb: porb, porbft: porbft,
      blkf: blk / (5 * lg.lg_player_blk),
      stlp: clip(lg.steal_share_of_tov * stl / (5 * lg.lg_player_stl), 0, 0.95),
      mu: clip(mu, 8, 22), shift: d, target: target
    };
  }

  // ---------------------------------------------------------------- lineup choice (one sim)
  function chooseLineup(T, M, played, consec, seg, nsegReg, margin, period, remRegSec, prm, ot, outL) {
    var n = T.n, i, k, pri = new Float64Array(n), remMin = Math.max(remRegSec / 60, 2);
    var blow = false;
    if (!ot && period === 4) {
      prm.sim.blowout.forEach(function (b) { if (Math.abs(margin) >= b[0] && remRegSec <= b[1]) blow = true; });
    }
    for (i = 0; i < n; i++) {
      var need = (M[i] - played[i] / 60) / remMin, p;
      if (ot) p = M[i] / 40;
      else {
        p = need;
        if (seg === 0 || seg === (nsegReg >> 1)) p += 2 * (T.starter[i] ? 1 : 0);
        if (seg >= nsegReg - 2 && Math.abs(margin) <= 10) p += 0.6 * M[i] / 40;
        if (consec[i] >= 3) p -= 0.25 * (consec[i] - 2);
        if (blow) p = M[i] > 0 ? 100 - M[i] : -50;
      }
      if (!(M[i] > 0)) p = -100;
      if (T.out[i]) p = -1e9;
      pri[i] = p;
    }
    var picked = new Uint8Array(n), nC = 0, hasG = false;
    for (k = 0; k < 5; k++) {
      var best = -1, bv = -Infinity;
      for (i = 0; i < n; i++) {
        if (picked[i]) continue;
        var v = pri[i];
        if (nC >= prm.sim.max_c && T.posg[i] === 2) v -= 1000;
        if (k === 4 && !hasG && T.posg[i] !== 0) v -= 1000;
        if (v > bv) { bv = v; best = i; }
      }
      picked[best] = 1; outL[k] = best;
      if (T.posg[best] === 2) nC++;
      if (T.posg[best] === 0) hasG = true;
    }
    for (i = 0; i < n; i++) consec[i] = picked[i] ? consec[i] + 1 : 0;
  }

  // ---------------------------------------------------------------- simulate
  function simulate(prm, homeSpec, awaySpec, opts) {
    opts = opts || {};
    var S = opts.nSims || 10000, rng = makeRng(opts.seed || 1);
    var H = homeSpec && homeSpec.minutes ? homeSpec : prepareTeam(prm, homeSpec);
    var A = awaySpec && awaySpec.minutes ? awaySpec : prepareTeam(prm, awaySpec);
    var TM = [H, A], sim = prm.sim, lg = prm.league, ctx = contextPts100(prm, opts);
    var paceOff = TM.map(function (T) { return prm.pace.team_off[String(T.tid)] || 0; });
    var paceDef = TM.map(function (T) { return prm.pace.team_def[String(T.tid)] || 0; });
    var NP = H.n + A.n, maxP = 4 + sim.max_ot;
    var box = []; for (var st = 0; st < NP * NST; st++) box.push(new Float32Array(S));
    var scoreH = new Float64Array(S), scoreA = new Float64Array(S), possCount = new Float64Array(S);
    var qsH = [], qsA = [];
    for (var pq = 0; pq < maxP; pq++) { qsH.push(new Float64Array(S)); qsA.push(new Float64Array(S)); }
    var segLen = sim.segment_sec, nsegReg = Math.round(2400 / segLen), zoff = lg.astd_zone_offset, bz = lg.blk_given_miss_zone;
    var gsh = prm.pace.gamma_shape, orbSec = prm.pace.orb_play_sec;
    var Ltmp = [[0, 0, 0, 0, 0], [0, 0, 0, 0, 0]];
    var wtmp = new Float64Array(5);

    function add(g, stat, s, v) { box[g * NST + stat][s] += v; }
    function periodEnd(p) { return p <= 4 ? 600 * p : 2400 + 300 * (p - 4); }

    for (var s = 0; s < S; s++) {
      // minutes targets
      var Ms = TM.map(function (T) {
        var M = new Float64Array(T.n), i;
        for (i = 0; i < T.n; i++) {
          var sd = Math.min(T.min_sd[i], 0.5 * T.minutes[i] + 2);
          var z = rng.normal();
          M[i] = T.minutes[i] > 0 ? clip(T.minutes[i] + sd * z, 0, sim.min_cap) : 0;
        }
        for (var it = 0; it < 3; it++) {
          var tot = 0; for (i = 0; i < T.n; i++) tot += M[i];
          var f = 200 / Math.max(tot, 1e-9);
          for (i = 0; i < T.n; i++) M[i] = Math.min(M[i] * f, sim.min_cap);
        }
        return M;
      });
      var played = TM.map(function (T) { return new Float64Array(T.n); });
      var consec = TM.map(function (T) { return new Float64Array(T.n); });
      var score = [0, 0], qsum = [0, 0], clock = 0, stealFlag = false, nposs = 0;
      var possTeam = rng.u() < 0.5 ? 1 : 0, firstTeam = possTeam;
      var otPlayed = 0;

      var runSegment = function (t0, t1, period, seg, ot) {
        var marginH = score[0] - score[1], remReg = Math.max(2400 - t0, 0);
        chooseLineup(H, Ms[0], played[0], consec[0], seg, nsegReg, marginH, period, remReg, prm, ot, Ltmp[0]);
        chooseLineup(A, Ms[1], played[1], consec[1], seg, nsegReg, -marginH, period, remReg, prm, ot, Ltmp[1]);
        var Lh = Ltmp[0].slice(), La = Ltmp[1].slice();
        var cal = [calibrate(prm, H, A, Lh, La, ctx[0], paceOff[0], paceDef[1]),
          calibrate(prm, A, H, La, Lh, ctx[1], paceOff[1], paceDef[0])];
        var lus = [Lh, La], offBase = [0, H.n];
        var pend = periodEnd(period), t = Math.max(clock, t0);
        while (t < t1 - 1e-9 && t < pend - 1e-9) {
          var o = possTeam, dd = 1 - o, C = cal[o], To = TM[o], Td = TM[dd], offL = lus[o], defL = lus[dd];
          var ob = offBase[o], db = offBase[dd];
          var rem = pend - t, lead = score[o] - score[dd], late = period >= 4 && rem <= 120;
          var mu = C.mu;
          if (stealFlag) mu *= 0.7;
          if (late && lead > 0 && rem > 24) mu = 21;
          if (late && lead < 0) mu = 9;
          var foul = period >= 4 && rem <= sim.late_foul_sec && lead >= 1 && lead <= sim.late_foul_max_lead;
          var dur = rng.gamma(gsh, mu / gsh);
          if (foul) dur = 2 + rng.gamma(2, 1);
          dur = Math.min(dur, rem);
          var trail3 = late && lead <= -3;
          stealFlag = false;
          nposs++;
          var i, k;
          if (rng.u() < lg.tech_ft_per_poss) {
            var bi = 0; for (i = 1; i < 5; i++) if (To.ftp[offL[i]] > To.ftp[offL[bi]]) bi = i;
            var mk = rng.u() < lg.tech_ft_pct ? 1 : 0, gp = ob + offL[bi];
            add(gp, PTS, s, mk); add(gp, FTA, s, 1); add(gp, FTM, s, mk); score[o] += mk;
          }
          var elapsed = dur, alive = true, first = true;
          for (var play = 0; play < 6 && alive; play++) {
            var u = catSample(C.w, 5, rng.u());
            var isfoul = foul && first;
            if (isfoul) {
              for (i = 0; i < 5; i++) wtmp[i] = C.w[i] * To.ftp[offL[i]];
              u = catSample(wtmp, 5, rng.u());
            }
            var pl = offL[u], gpid = ob + pl, ftp = To.ftp[pl], r1 = rng.u(), cont = false;
            var tv = C.t[u], fv = C.f[u];
            if (!isfoul && r1 < tv) {                       // turnover
              add(gpid, TOV, s, 1);
              if (rng.u() < C.stlp) {
                for (i = 0; i < 5; i++) wtmp[i] = Td.stl[defL[i]];
                add(db + defL[catSample(wtmp, 5, rng.u())], STL, s, 1);
                stealFlag = true;
              }
            } else if (isfoul || r1 < tv + fv) {            // FT trip
              var nft = isfoul ? 2 : (rng.u() < To.trip3[pl] ? 3 : 2), made = 0, last = false;
              for (k = 0; k < nft; k++) { last = rng.u() < ftp; if (last) made++; }
              add(gpid, PTS, s, made); add(gpid, FTA, s, nft); add(gpid, FTM, s, made); score[o] += made;
              if (!last) {
                if (rng.u() < C.porbft) { cont = true; rebound(true); } else rebound(false);
              }
            } else {                                        // field goal attempt
              var mx = To.mix[pl], zw = wtmp;
              for (i = 0; i < 5; i++) zw[i] = mx[i] * (trail3 && i >= 3 ? 1.8 : 1);
              var z = catSample(zw, 5, rng.u()), three = z >= 3;
              add(gpid, FGA, s, 1); if (three) add(gpid, FG3A, s, 1);
              if (rng.u() < C.Q[u][z]) {
                var v = three ? 3 : 2;
                add(gpid, FGM, s, 1); if (three) add(gpid, FG3M, s, 1); add(gpid, PTS, s, v); score[o] += v;
                if (rng.u() < To.and1[pl]) {
                  var fm = rng.u() < ftp ? 1 : 0;
                  add(gpid, FTA, s, 1); add(gpid, FTM, s, fm); add(gpid, PTS, s, fm); score[o] += fm;
                }
                if (rng.u() < expit(logit(To.astd[pl]) + zoff[z])) {
                  for (i = 0; i < 5; i++) wtmp[i] = i === u ? 0 : To.ast[offL[i]];
                  add(ob + offL[catSample(wtmp, 5, rng.u())], AST, s, 1);
                }
              } else {
                if (rng.u() < clip(bz[z] * C.blkf, 0, 0.6)) {
                  for (i = 0; i < 5; i++) wtmp[i] = Td.blk[defL[i]];
                  add(db + defL[catSample(wtmp, 5, rng.u())], BLK, s, 1);
                }
                if (rng.u() < C.porb) { cont = true; rebound(true); } else rebound(false);
              }
            }
            first = false;
            if (cont) {
              var ex = rng.gamma(2, orbSec / 2), room = rem - elapsed;
              elapsed = Math.min(elapsed + ex, rem);
              alive = room > 0.5;
            } else alive = false;
          }
          t += elapsed;
          for (k = 0; k < 5; k++) {
            add(Lh[k], SEC, s, elapsed); played[0][Lh[k]] += elapsed;
            add(H.n + La[k], SEC, s, elapsed); played[1][La[k]] += elapsed;
          }
          possTeam = 1 - possTeam;

          function rebound(off) {
            var j;
            if (off) {
              if (rng.u() < lg.orb_player_credit) {
                for (j = 0; j < 5; j++) wtmp[j] = To.orb[offL[j]];
                add(ob + offL[catSample(wtmp, 5, rng.u())], ORB, s, 1);
              }
            } else if (rng.u() < lg.drb_player_credit) {
              for (j = 0; j < 5; j++) wtmp[j] = Td.drb[defL[j]];
              add(db + defL[catSample(wtmp, 5, rng.u())], DRB, s, 1);
            }
          }
        }
        clock = t;
      };

      for (var seg = 0; seg < nsegReg; seg++) {
        var t0 = seg * segLen, period = Math.floor(t0 / 600) + 1;
        if (t0 % 600 === 0 && period > 1) possTeam = (period === 2 || period === 3) ? 1 - firstTeam : firstTeam;
        runSegment(t0, t0 + segLen, period, seg, false);
        if ((t0 + segLen) % 600 === 0) {
          qsH[period - 1][s] = score[0] - qsum[0]; qsA[period - 1][s] = score[1] - qsum[1];
          qsum[0] = score[0]; qsum[1] = score[1];
        }
      }
      for (var ot = 0; ot < sim.max_ot && score[0] === score[1]; ot++) {
        var base = 2400 + 300 * ot, b0 = score[0], b1 = score[1];
        possTeam = rng.u() < 0.5 ? 1 : 0;
        var nso = Math.round(300 / sim.ot_segment_sec);
        for (var s2 = 0; s2 < nso; s2++) runSegment(base + s2 * sim.ot_segment_sec, base + (s2 + 1) * sim.ot_segment_sec, 5 + ot, 0, true);
        qsH[4 + ot][s] = score[0] - b0; qsA[4 + ot][s] = score[1] - b1;
      }
      if (score[0] === score[1]) score[rng.u() < 0.5 ? 1 : 0] += 1;
      scoreH[s] = score[0]; scoreA[s] = score[1]; possCount[s] = nposs;
    }
    var res = { S: S, scoreH: scoreH, scoreA: scoreA, qsH: qsH, qsA: qsA, box: box, nposs: possCount, H: H, A: A };
    return {
      game: gameSummary(res, prm),
      home: playerSummary(res, 0),
      away: playerSummary(res, 1),
      meta: { n_sims: S, seed: opts.seed || 1, home_minutes: H.minutes, away_minutes: A.minutes }
    };
  }

  // ---------------------------------------------------------------- summaries
  function sorted(x) { var a = Array.prototype.slice.call(x); a.sort(function (p, q) { return p - q; }); return a; }
  function quantiles(x) {
    var a = sorted(x), n = a.length;
    return QS.map(function (q) { var h = (n - 1) * q, lo = Math.floor(h), hi = Math.ceil(h); return a[lo] + (a[hi] - a[lo]) * (h - lo); });
  }
  function meanSd(x) {
    var n = x.length, m = 0, v = 0, i;
    for (i = 0; i < n; i++) m += x[i];
    m /= n;
    for (i = 0; i < n; i++) v += (x[i] - m) * (x[i] - m);
    return [m, Math.sqrt(v / n)];
  }
  function dist(x) { var ms = meanSd(x); return { mean: ms[0], sd: ms[1], q: quantiles(x) }; }
  function hist(x, lo, hi) {
    var c = new Array(hi - lo + 1).fill(0), n = x.length;
    for (var i = 0; i < n; i++) { var v = clip(Math.round(x[i]), lo, hi); c[v - lo]++; }
    return { lo: lo, hi: hi, p: c.map(function (v) { return v / n; }) };
  }
  function pyRound(v) { // numpy round-half-to-even
    var f = Math.floor(v), d = v - f;
    if (d > 0.5) return f + 1; if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }
  function ladder(x, step) {
    var m = meanSd(x)[0], c = step === 2 ? pyRound(m) + 0.5 : Math.floor(m / step) * step + 0.5;
    var lines = [], po = [];
    for (var k = -3; k <= 3; k++) {
      var ln = c + step * k;
      if (ln <= 0) continue;
      var cnt = 0; for (var i = 0; i < x.length; i++) if (x[i] > ln) cnt++;
      lines.push(ln); po.push(cnt / x.length);
    }
    return [lines, po];
  }

  function gameSummary(r, prm) {
    var S = r.S, mar = new Float64Array(S), tot = new Float64Array(S), i, wins = 0, ot = 0;
    for (i = 0; i < S; i++) {
      mar[i] = r.scoreH[i] - r.scoreA[i]; tot[i] = r.scoreH[i] + r.scoreA[i];
      if (mar[i] > 0) wins++;
      var o = 0; for (var k = 4; k < r.qsH.length; k++) o += r.qsH[k][i] + r.qsA[k][i];
      if (o > 0) ot++;
    }
    var out = {
      n_sims: S, home_win: wins / S, margin: dist(mar), total: dist(tot), home_pts: dist(r.scoreH), away_pts: dist(r.scoreA),
      p_ot: ot / S, poss_per_team: meanSd(r.nposs)[0] / 2, margin_hist: hist(mar, -50, 50), total_hist: hist(tot, 110, 240)
    };
    out.quarters = [0, 1, 2, 3].map(function (k) {
      var qm = new Float64Array(S), qt = new Float64Array(S), hw = 0, tie = 0;
      for (i = 0; i < S; i++) { qm[i] = r.qsH[k][i] - r.qsA[k][i]; qt[i] = r.qsH[k][i] + r.qsA[k][i]; if (qm[i] > 0) hw++; if (qm[i] === 0) tie++; }
      return { home: meanSd(r.qsH[k])[0], away: meanSd(r.qsA[k])[0], home_win: hw / S, tie: tie / S, margin_sd: meanSd(qm)[1], total_sd: meanSd(qt)[1] };
    });
    out.halves = [0, 1].map(function (h) {
      var hh = new Float64Array(S), ha = new Float64Array(S), hm = new Float64Array(S), ht = new Float64Array(S), hw = 0, tie = 0;
      for (i = 0; i < S; i++) {
        hh[i] = r.qsH[2 * h][i] + r.qsH[2 * h + 1][i]; ha[i] = r.qsA[2 * h][i] + r.qsA[2 * h + 1][i];
        if (h === 1) for (var k = 4; k < r.qsH.length; k++) { hh[i] += r.qsH[k][i]; ha[i] += r.qsA[k][i]; }
        hm[i] = hh[i] - ha[i]; ht[i] = hh[i] + ha[i]; if (hm[i] > 0) hw++; if (hm[i] === 0) tie++;
      }
      var m = meanSd(hm), t = meanSd(ht);
      return { home: meanSd(hh)[0], away: meanSd(ha)[0], home_win: hw / S, tie: tie / S, margin_mean: m[0], margin_sd: m[1], total_mean: t[0], total_sd: t[1] };
    });
    return out;
  }

  function playerSummary(r, side) {
    var T = side === 0 ? r.H : r.A, off = side === 0 ? 0 : r.H.n, S = r.S, out = [];
    for (var i = 0; i < T.n; i++) {
      var g = off + i, b = function (st) { return r.box[g * NST + st]; };
      var d = { min: new Float64Array(S), pts: b(PTS), reb: new Float64Array(S), ast: b(AST), fg3m: b(FG3M), stl: b(STL), blk: b(BLK), tov: b(TOV),
        pra: new Float64Array(S), pr: new Float64Array(S), pa: new Float64Array(S) };
      var dd = 0, sec = b(SEC), orb = b(ORB), drb = b(DRB), pts = b(PTS), ast = b(AST);
      for (var s = 0; s < S; s++) {
        d.min[s] = sec[s] / 60; d.reb[s] = orb[s] + drb[s];
        d.pra[s] = pts[s] + d.reb[s] + ast[s]; d.pr[s] = pts[s] + d.reb[s]; d.pa[s] = pts[s] + ast[s];
        if ((pts[s] >= 10 ? 1 : 0) + (d.reb[s] >= 10 ? 1 : 0) + (ast[s] >= 10 ? 1 : 0) >= 2) dd++;
      }
      var rec = { id: T.ids[i], name: T.names[i], proj_min: T.minutes[i], out: !!T.out[i] };
      Object.keys(d).forEach(function (k) {
        var ms = meanSd(d[k]), lad = ladder(d[k], LADDER_STEP[k]);
        rec[k] = { mean: ms[0], sd: ms[1], q: quantiles(d[k]), lines: lad[0], p_over: lad[1] };
      });
      rec.fga = meanSd(b(FGA))[0]; rec.fg3a = meanSd(b(FG3A))[0]; rec.fta = meanSd(b(FTA))[0]; rec.p_dd = dd / S;
      out.push(rec);
    }
    return out;
  }

  return { simulate: simulate, prepareTeam: prepareTeam, reallocate: reallocate, calibrate: calibrate, makeRng: makeRng, version: 1 };
});
