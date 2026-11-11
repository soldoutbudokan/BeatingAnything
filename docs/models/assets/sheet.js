/* Sheets — a small, dependency-free framework for model "workbooks".
   Global: window.Sheets. See README.md in this folder for the API reference.
   ES2020, no build step. Load with <script src="../assets/sheet.js"></script> (in <head> to avoid a theme flash). */
(function (global) {
'use strict';

// Apply the stored theme as early as possible.
try { const t = localStorage.getItem('theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch (e) {}

const SCRIPT_SRC = (document.currentScript && document.currentScript.src) || '';
const ASSET_BASE = SCRIPT_SRC ? new URL('.', SCRIPT_SRC).href : new URL('assets/', document.baseURI).href;
const MINUS = '−';

/* ════════════════════ utilities ════════════════════ */
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ESC[c]);
const isNum = v => typeof v === 'number' && isFinite(v);
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
const $ = (s, r = document) => r.querySelector(s);

/** h('div', {class:'x', onclick: fn, style:{...}}, child, 'text', [more]) */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  return el;
}
function append(el, kids) {
  for (const k of kids) {
    if (k == null || k === false) continue;
    if (Array.isArray(k)) append(el, k);
    else el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}
function resolveEl(el) { return typeof el === 'string' ? document.querySelector(el) : el; }
function debounce(fn, ms) { let t; return function (...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); }; }
function setContent(el, c) {
  el.innerHTML = '';
  if (c == null) return;
  if (typeof c === 'function') c(el);
  else if (c instanceof Node) el.append(c);
  else if (Array.isArray(c)) append(el, c);
  else el.innerHTML = String(c);
}

/* ════════════════════ number formatting ════════════════════ */
function group3(s) { return s.replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
/** Fast fixed-decimal formatting with thousands separators and a true minus sign. */
function fixed(v, dp) {
  if (!isNum(v)) return '';
  let s = Math.abs(v).toFixed(dp);
  if (Math.abs(v) >= 1000) { const i = s.indexOf('.'); s = i < 0 ? group3(s) : group3(s.slice(0, i)) + s.slice(i); }
  return (v < 0 && /[1-9]/.test(s) ? MINUS : '') + s;
}
function signed(v, dp) {
  if (!isNum(v)) return '';
  const s = fixed(v, dp);
  return v > 0 && /[1-9]/.test(s) ? '+' + s : s;
}
const odds = {
  /** probability -> American price (number), e.g. 0.4 -> 150, 0.6 -> -150 */
  american(p) { if (!(p > 0 && p < 1)) return null; return p >= 0.5 ? (p === 0.5 ? 100 : -100 * p / (1 - p)) : 100 * (1 - p) / p; },
  /** probability -> decimal price, e.g. 0.4 -> 2.5 */
  decimal(p) { return p > 0 && p <= 1 ? 1 / p : null; },
  fromAmerican(a) { if (!isNum(a) || (a > -100 && a < 100)) return null; return a > 0 ? 100 / (a + 100) : -a / (-a + 100); },
  fromDecimal(d) { return isNum(d) && d > 1 ? 1 / d : null; },
  americanToDecimal(a) { if (!isNum(a) || (a > -100 && a < 100)) return null; return a > 0 ? 1 + a / 100 : 1 + 100 / -a; },
  decimalToAmerican(d) { if (!isNum(d) || d <= 1) return null; return d >= 2 ? (d - 1) * 100 : -100 / (d - 1); },
  /** Format an American price: 150 -> "+150", -150 -> "−150". */
  fmtAmerican(a) { if (!isNum(a)) return ''; const r = Math.round(a); return r > 0 ? '+' + r : MINUS + Math.abs(r); },
  /** Proportional de-vig of implied probabilities (or of American prices with {american:true}). */
  devig(xs, o = {}) { const ps = o.american ? xs.map(odds.fromAmerican) : xs.slice(); const s = ps.reduce((a, b) => a + b, 0); return ps.map(p => p / s); },
  /** Expected value per unit staked at decimal price d with win probability p. */
  ev(p, price, o = {}) { const d = o.american ? odds.americanToDecimal(price) : price; return isNum(p) && isNum(d) ? p * d - 1 : null; },
};

const fmt = {
  num: (v, dp = 1) => fixed(v, dp),
  int: v => fixed(v, 0),
  pct: (v, dp = 1) => isNum(v) ? fixed(v * 100, dp) + '%' : '',
  signed: (v, dp = 1) => signed(v, dp),
  spct: (v, dp = 1) => isNum(v) ? signed(v * 100, dp) + '%' : '',
  american: p => odds.fmtAmerican(odds.american(p)),
  odds: a => odds.fmtAmerican(a),
  dec: (p, dp = 2) => { const d = odds.decimal(p); return d == null ? '' : fixed(d, dp); },
  compact(v, dp = 1) {
    if (!isNum(v)) return ''; const a = Math.abs(v);
    if (a >= 1e9) return fixed(v / 1e9, dp) + 'B'; if (a >= 1e6) return fixed(v / 1e6, dp) + 'M';
    if (a >= 1e4) return fixed(v / 1e3, dp) + 'K'; return fixed(v, a >= 100 ? 0 : dp);
  },
  text: v => v == null ? '' : String(v),
  /** Build a formatter from a spec: 'num:2', 'int', 'pct:1', 'signed:1', 'spct:1', 'american', 'odds', 'dec:2', 'compact', 'text', or a function. */
  make(spec) {
    if (typeof spec === 'function') return spec;
    if (!spec) return null;
    const [k, a] = String(spec).split(':');
    const f = fmt[k]; if (!f || k === 'make') throw new Error('Sheets.fmt: unknown format "' + spec + '"');
    if (a === undefined) return v => f(v);
    const dp = +a; return v => f(v, dp);
  },
  /** Scale of the user-facing units of a format (pct formats are typed in percent). */
  scaleOf(spec) { const k = typeof spec === 'string' ? spec.split(':')[0] : ''; return k === 'pct' || k === 'spct' ? 100 : 1; },
};

/* ════════════════════ stats & distributions ════════════════════ */
function quantileSorted(s, q) {
  const n = s.length; if (!n) return NaN; const pos = (n - 1) * q, i = Math.floor(pos), f = pos - i;
  return i + 1 < n ? s[i] + (s[i + 1] - s[i]) * f : s[i];
}
function sortedFinite(arr) { const out = []; for (const v of arr) if (isNum(v)) out.push(v); return Float64Array.from(out).sort(); }
function lowerBound(s, x) { let lo = 0, hi = s.length; while (lo < hi) { const m = (lo + hi) >> 1; if (s[m] < x) lo = m + 1; else hi = m; } return lo; }
function upperBound(s, x) { let lo = 0, hi = s.length; while (lo < hi) { const m = (lo + hi) >> 1; if (s[m] <= x) lo = m + 1; else hi = m; } return lo; }
const stats = {
  mean(a) { let s = 0, n = 0; for (const v of a) if (isNum(v)) { s += v; n++; } return n ? s / n : NaN; },
  sd(a) { const m = stats.mean(a); let s = 0, n = 0; for (const v of a) if (isNum(v)) { s += (v - m) ** 2; n++; } return n > 1 ? Math.sqrt(s / (n - 1)) : NaN; },
  quantile(a, q) { return quantileSorted(sortedFinite(a), q); },
  extent(a) { let lo = Infinity, hi = -Infinity; for (const v of a) if (isNum(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } return [lo, hi]; },
};

/** Distribution objects with a common interface: pOver(x)=P(X>x), pUnder(x)=P(X<x), pEq(x), pAtMost(x), mean, sd, quantile(q), pmf(), min, max */
const dist = {
  fromSamples(arr) {
    const s = arr instanceof Float64Array ? Float64Array.from(arr).sort() : sortedFinite(arr); const n = s.length;
    let m = 0; for (let i = 0; i < n; i++) m += s[i]; m /= n || 1;
    let v = 0; for (let i = 0; i < n; i++) v += (s[i] - m) ** 2;
    return {
      kind: 'samples', n, samples: s, mean: m, sd: Math.sqrt(v / Math.max(1, n - 1)), min: s[0], max: s[n - 1],
      pOver: x => (n - upperBound(s, x)) / n, pUnder: x => lowerBound(s, x) / n,
      pEq: x => (upperBound(s, x) - lowerBound(s, x)) / n, pAtMost: x => upperBound(s, x) / n,
      quantile: q => quantileSorted(s, q),
      pmf() { const out = []; let i = 0; while (i < n) { const x = s[i]; const j = upperBound(s, x); out.push({ x, p: (j - i) / n }); i = j; } return out; },
    };
  },
  /** pmf as {x: p}, [[x,p]], or [{x,p}]; normalised automatically. */
  fromPmf(pmf) {
    let rows = Array.isArray(pmf) ? pmf.map(r => Array.isArray(r) ? { x: +r[0], p: +r[1] } : { x: +r.x, p: +r.p }) : Object.entries(pmf).map(([x, p]) => ({ x: +x, p: +p }));
    rows = rows.filter(r => isNum(r.x) && isNum(r.p) && r.p > 0).sort((a, b) => a.x - b.x);
    const tot = rows.reduce((a, r) => a + r.p, 0) || 1; rows.forEach(r => r.p /= tot);
    const xs = Float64Array.from(rows.map(r => r.x)), cum = new Float64Array(rows.length);
    let c = 0; rows.forEach((r, i) => { c += r.p; cum[i] = c; });
    const m = rows.reduce((a, r) => a + r.x * r.p, 0), v = rows.reduce((a, r) => a + r.p * (r.x - m) ** 2, 0);
    const atMost = x => { const i = upperBound(xs, x) - 1; return i < 0 ? 0 : cum[i]; };
    const below = x => { const i = lowerBound(xs, x) - 1; return i < 0 ? 0 : cum[i]; };
    return {
      kind: 'pmf', n: rows.length, mean: m, sd: Math.sqrt(v), min: xs[0], max: xs[xs.length - 1],
      pOver: x => 1 - atMost(x), pUnder: below, pEq: x => atMost(x) - below(x), pAtMost: atMost,
      quantile: q => { const i = lowerBound(cum, q - 1e-12); return xs[Math.min(i, xs.length - 1)]; },
      pmf: () => rows.map(r => ({ x: r.x, p: r.p })),
    };
  },
  /** Counts histogram {x: count} (e.g. from a simulator) -> pmf distribution. */
  fromCounts(counts) { return dist.fromPmf(counts); },
};

/** Seeded RNG (mulberry32) with helpers. r() -> [0,1); r.normal(mu,sd); r.int(n); r.poisson(l); r.weighted(cumWeights) */
function rng(seed = 1) {
  let a = seed >>> 0;
  const r = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  let spare = null;
  r.normal = (mu = 0, sd = 1) => { if (spare != null) { const s = spare; spare = null; return mu + sd * s; } let u, v, q; do { u = r() * 2 - 1; v = r() * 2 - 1; q = u * u + v * v; } while (q >= 1 || q === 0); const f = Math.sqrt(-2 * Math.log(q) / q); spare = v * f; return mu + sd * u * f; };
  r.int = n => Math.floor(r() * n);
  r.poisson = l => { if (l > 30) return Math.max(0, Math.round(r.normal(l, Math.sqrt(l)))); const L = Math.exp(-l); let k = 0, p = 1; do { k++; p *= r(); } while (p > L); return k - 1; };
  r.weighted = cum => { const u = r() * cum[cum.length - 1]; let i = 0; while (cum[i] < u) i++; return i; };
  return r;
}

/* ════════════════════ theme ════════════════════ */
const themeListeners = [];
const theme = {
  get() { return document.documentElement.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); },
  set(t) { document.documentElement.setAttribute('data-theme', t); try { localStorage.setItem('theme', t); } catch (e) {} themeListeners.forEach(f => f(t)); },
  toggle() { theme.set(theme.get() === 'dark' ? 'light' : 'dark'); },
  onChange(fn) { themeListeners.push(fn); },
  button(cls = 'sh-pill') { return h('button', { class: cls, type: 'button', 'aria-label': 'Toggle colour theme', onclick: () => theme.toggle(), text: 'Theme' }); },
};

/* ════════════════════ tooltip ════════════════════ */
let tipEl = null;
const tip = {
  show(x, y, html) {
    if (!tipEl) { tipEl = h('div', { class: 'sh-tip', role: 'tooltip' }); document.body.append(tipEl); }
    tipEl.innerHTML = html; tipEl.classList.add('on');
    const r = tipEl.getBoundingClientRect(), W = innerWidth, H = innerHeight;
    let L = x + 14, T = y + 14;
    if (L + r.width > W - 8) L = x - 14 - r.width;
    if (T + r.height > H - 8) T = y - 14 - r.height;
    tipEl.style.left = Math.max(8, L) + 'px'; tipEl.style.top = Math.max(8, T) + 'px';
  },
  hide() { if (tipEl) tipEl.classList.remove('on'); },
  /** Tooltip body: header + rows [{value, label, key:'k1'|css color class}] + optional description. All text escaped. */
  html(head, rows = [], desc) {
    let s = head ? `<div class="tt-h">${esc(head)}</div>` : '';
    for (const r of rows) s += `<div class="tt-r">${r.key ? `<i class="tt-k ${esc(r.key)}"></i>` : ''}<b>${esc(r.value)}</b><span>${esc(r.label ?? '')}</span></div>`;
    if (desc) s += `<div class="tt-d">${esc(desc)}</div>`;
    return s;
  },
};
// keys in tooltips use series background classes
const keyCls = i => 'b' + (i % 8 + 1);

/* ════════════════════ data loader ════════════════════ */
class LoadError extends Error {
  constructor(url, detail, status) { super(`Could not load ${url}: ${detail}`); this.name = 'LoadError'; this.url = url; this.detail = detail; this.status = status; }
}
const loadCache = new Map(), inflight = new Set(), inflightListeners = new Set();
function notifyInflight() { inflightListeners.forEach(f => f([...inflight])); }
/** Load JSON (default for .json) or text. Cached by absolute URL. Rejects with a LoadError carrying a readable message. */
function load(url, o = {}) {
  const abs = new URL(url, document.baseURI).href;
  const type = o.type || (/\.json(\?|#|$)/i.test(url) ? 'json' : 'text');
  const key = type + ' ' + abs;
  if (!o.reload && loadCache.has(key)) return loadCache.get(key);
  inflight.add(url); notifyInflight();
  const p = fetch(abs, { cache: o.cache || 'no-cache' })
    .catch(e => { throw new LoadError(url, location.protocol === 'file:' ? 'pages must be served over http (file:// blocks fetch)' : 'network error (' + e.message + ')'); })
    .then(r => {
      if (!r.ok) throw new LoadError(url, 'HTTP ' + r.status + ' ' + (r.statusText || (r.status === 404 ? 'Not Found' : '')), r.status);
      return type === 'json' ? r.text().then(t => { try { return JSON.parse(t); } catch (e) { throw new LoadError(url, 'invalid JSON: ' + e.message); } }) : r.text();
    })
    .finally(() => { inflight.delete(url); notifyInflight(); });
  p.catch(() => loadCache.delete(key));
  loadCache.set(key, p);
  return p;
}
/** Like load() but resolves null when the file is missing (404) or unreachable. */
load.optional = (url, o) => load(url, o).catch(e => { if (e instanceof LoadError) return null; throw e; });
/** Load several: load.all({ratings:'data/ratings.json', meta:'data/meta.json'}) -> {ratings, meta} */
load.all = async (map, o) => { const ks = Object.keys(map); const vs = await Promise.all(ks.map(k => load(map[k], o))); return Object.fromEntries(ks.map((k, i) => [k, vs[i]])); };
load.text = (url, o) => load(url, Object.assign({ type: 'text' }, o));

function loadingEl(label) {
  const list = h('div');
  const el = h('div', { class: 'sh-loading', role: 'status', 'aria-live': 'polite' }, h('div', { class: 'sh-lbar' }), h('div', { text: label || 'Loading…' }), list);
  const f = urls => { list.innerHTML = urls.slice(0, 6).map(u => `<code>${esc(u)}</code>`).join(' '); };
  f([...inflight]); inflightListeners.add(f);
  el._dispose = () => inflightListeners.delete(f);
  return el;
}
function errorEl(err, title) {
  const isLoad = err instanceof LoadError;
  return h('div', { class: 'sh-error', role: 'alert' },
    h('b', { text: title || (isLoad ? 'Data not available' : 'Something went wrong') }),
    h('div', { text: isLoad ? `${err.url} could not be loaded.` : 'This sheet failed to render.' }),
    h('div', { class: 'sh-err-detail', text: isLoad ? err.detail : (err && err.message) || String(err) }),
    isLoad && err.status === 404 ? h('div', { class: 'sh-err-hint', text: 'The model export may not have run yet, or the file was renamed.' }) : null);
}
/** Show a loading state in el while the promise (or async fn) runs; on failure show a readable error. Resolves to the value or undefined. */
async function into(el, work, o = {}) {
  el = resolveEl(el);
  const ld = loadingEl(o.label); el.innerHTML = ''; el.append(ld);
  try { const v = await (typeof work === 'function' ? work(el) : work); ld._dispose(); ld.remove(); return v; }
  catch (e) { ld._dispose(); el.innerHTML = ''; el.append(errorEl(e, o.errorTitle)); (e instanceof LoadError ? console.warn : console.error)(e.message || e); return undefined; }
}

/* ════════════════════ markdown ════════════════════ */
const md = (() => {
  const LI = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  const FENCE = /^\s*(```|~~~)\s*([\w+-]*)\s*$/;
  const TDELIM = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
  const indentOf = l => l.match(/^\s*/)[0].replace(/\t/g, '    ').length;
  const blockStart = l => /^\s{0,3}(#{1,6}\s|>|```|~~~|(\*\s*){3,}$|(-\s*){3,}$|(_\s*){3,}$)/.test(l) || LI.test(l);
  const slug = s => s.toLowerCase().replace(/<[^>]+>/g, '').replace(/&[a-z]+;/g, '').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-');

  function safeUrl(u, base) {
    u = u.trim(); if (/^(javascript|vbscript|data):/i.test(u)) return '#';
    if (base && !/^([a-z]+:|#|\/)/i.test(u)) { try { return new URL(u, base).href; } catch (e) {} }
    return u;
  }
  function inline(src, o) {
    const slots = [];
    const keep = html => '\u0000' + (slots.push(html) - 1) + '\u0000';
    let s = src.replace(/(`+)([\s\S]*?[^`])\1(?!`)/g, (m, t, c) => keep(`<code>${esc(c.trim())}</code>`));
    s = s.replace(/\\([\\`*_{}\[\]()#+\-.!|~<>$])/g, (m, c) => keep(esc(c)));
    s = s.replace(/<(https?:\/\/[^>\s]+)>/g, (m, u) => keep(`<a href="${esc(safeUrl(u))}">${esc(u)}</a>`));
    s = esc(s);
    s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (m, alt, u, t) => keep(`<img src="${esc(safeUrl(u, o.base))}" alt="${alt}"${t ? ` title="${t}"` : ''}>`));
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (m, txt, u, t) => {
      const href = safeUrl(u.replace(/&amp;/g, '&'), o.base); const ext = /^https?:/i.test(href) && !href.startsWith(location.origin);
      return keep(`<a href="${esc(href)}"${t ? ` title="${t}"` : ''}${ext ? ' target="_blank" rel="noopener"' : ''}>`) + txt + keep('</a>');
    });
    s = s.replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, '<strong>$2</strong>');
    s = s.replace(/(^|[^\w*])\*(?=\S)([^*]*?\S)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/(^|[^\w])_(?=\S)([^_]*?\S)_(?!\w)/g, '$1<em>$2</em>');
    s = s.replace(/~~(?=\S)([\s\S]*?\S)~~/g, '<del>$1</del>');
    s = s.replace(/ {2,}\n|\\\n/g, '<br>');
    return s.replace(/\u0000(\d+)\u0000/g, (m, i) => slots[+i]).replace(/\u0000(\d+)\u0000/g, (m, i) => slots[+i]);
  }
  function splitRow(l) {
    l = l.trim(); if (l.startsWith('|')) l = l.slice(1); if (l.endsWith('|') && !l.endsWith('\\|')) l = l.slice(0, -1);
    const out = []; let cur = '', code = false;
    for (let i = 0; i < l.length; i++) { const c = l[i]; if (c === '`') code = !code; if (c === '\\' && l[i + 1] === '|') { cur += '|'; i++; continue; } if (c === '|' && !code) { out.push(cur.trim()); cur = ''; } else cur += c; }
    out.push(cur.trim()); return out;
  }
  const NUMCELL = /^[\s+\-−]*[$£€]?[\d,]*\.?\d+(e[+-]?\d+)?\s*(%|x|pp|bp)?\s*$/i;
  function blocks(L, o) {
    let out = '', i = 0;
    while (i < L.length) {
      const line = L[i];
      if (!line.trim()) { i++; continue; }
      let m;
      if ((m = line.match(FENCE))) {
        const fence = m[1], lang = m[2]; const buf = []; i++;
        while (i < L.length && !L[i].trim().startsWith(fence)) buf.push(L[i++]);
        i++; out += `<pre><code${lang ? ` class="lang-${esc(lang)}"` : ''}>${esc(buf.join('\n'))}</code></pre>`; continue;
      }
      if ((m = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/))) {
        const lv = m[1].length, txt = inline(m[2], o), id = (o.idPrefix || '') + slug(txt);
        out += `<h${lv} id="${esc(id)}">${txt}${lv >= 2 && lv <= 3 ? `<a class="anchor" href="#${esc(id)}" aria-label="Link to section">#</a>` : ''}</h${lv}>`; i++; continue;
      }
      if (/^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)) { out += '<hr>'; i++; continue; }
      if (/^\s{0,3}>/.test(line)) {
        const buf = []; while (i < L.length && L[i].trim() && /^\s{0,3}>/.test(L[i])) buf.push(L[i++].replace(/^\s{0,3}>\s?/, ''));
        out += `<blockquote>${blocks(buf, o)}</blockquote>`; continue;
      }
      if (line.includes('|') && i + 1 < L.length && TDELIM.test(L[i + 1])) {
        const head = splitRow(line), al = splitRow(L[i + 1]).map(c => /^:-+:$/.test(c) ? 'center' : /-:$/.test(c) ? 'right' : /^:-/.test(c) ? 'left' : '');
        i += 2; const body = [];
        while (i < L.length && L[i].trim() && L[i].includes('|')) body.push(splitRow(L[i++]));
        head.forEach((_, j) => { if (!al[j] && body.length && body.every(r => !r[j] || NUMCELL.test(r[j]) || r[j] === '—' || r[j] === '-')) al[j] = 'right'; });
        const st = j => al[j] ? ` style="text-align:${al[j]}"` : '';
        out += `<table><thead><tr>${head.map((c, j) => `<th${st(j)}>${inline(c, o)}</th>`).join('')}</tr></thead><tbody>` +
          body.map(r => `<tr>${head.map((_, j) => `<td${st(j)}>${inline(r[j] || '', o)}</td>`).join('')}</tr>`).join('') + '</tbody></table>';
        continue;
      }
      if ((m = line.match(LI))) {
        const r = list(L, i, o); out += r[0]; i = r[1]; continue;
      }
      const buf = [line]; i++;
      while (i < L.length && L[i].trim() && !blockStart(L[i]) && !(L[i].includes('|') && i + 1 < L.length && TDELIM.test(L[i + 1]))) buf.push(L[i++]);
      out += `<p>${inline(buf.map(l => l.replace(/^\s+/, '')).join('\n'), o)}</p>`;
    }
    return out;
  }
  function list(L, i, o) {
    const m0 = L[i].match(LI), base = indentOf(L[i]), ordered = /\d/.test(m0[2]), start = ordered ? parseInt(m0[2], 10) : 1;
    const items = []; let cur = null, contentIndent = base + m0[2].length + 1, loose = false;
    while (i < L.length) {
      const line = L[i];
      if (!line.trim()) {
        const nx = L[i + 1];
        if (nx !== undefined && nx.trim() && (indentOf(nx) >= contentIndent || (LI.test(nx) && indentOf(nx) === base))) { if (cur) cur.lines.push(''); if (LI.test(nx) && indentOf(nx) === base) loose = true; i++; continue; }
        break;
      }
      const m = line.match(LI), ind = indentOf(line);
      if (m && ind === base && (/\d/.test(m[2]) === ordered)) { cur = { lines: [m[3]] }; items.push(cur); contentIndent = base + m[2].length + 1; i++; continue; }
      if (m && ind < base) break;
      if (ind >= contentIndent || (m && ind > base)) { cur.lines.push(line.replace(/\t/g, '    ').slice(Math.min(ind, contentIndent))); i++; continue; }
      if (cur && !blockStart(line) && cur.lines[cur.lines.length - 1] !== '') { cur.lines.push(line.trim()); i++; continue; }
      break;
    }
    const tag = ordered ? 'ol' : 'ul';
    const lis = items.map(it => {
      let inner = blocks(it.lines, o);
      if (!loose && !it.lines.includes('')) inner = inner.replace(/^<p>([\s\S]*?)<\/p>/, '$1');
      return `<li>${inner}</li>`;
    }).join('');
    return [`<${tag}${ordered && start !== 1 ? ` start="${start}"` : ''}>${lis}</${tag}>`, i];
  }
  /** Markdown text -> HTML string. o.base resolves relative links/images; o.idPrefix namespaces heading ids. */
  function toHtml(text, o = {}) { return blocks(String(text).replace(/\r\n?/g, '\n').split('\n'), o); }
  return toHtml;
})();
/** Render markdown into el (adds .sh-md). In-page #anchors scroll without touching the workbook hash. */
function markdown(el, text, o = {}) {
  el = resolveEl(el); el.classList.add('sh-md'); el.innerHTML = md(text, o);
  el.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#"]'); if (!a) return;
    const t = el.querySelector('#' + CSS.escape(decodeURIComponent(a.getAttribute('href').slice(1))));
    if (t) { e.preventDefault(); t.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
  });
  return el;
}
/** Fetch a markdown file and render it into el with loading/error states. */
function loadMarkdown(el, url, o = {}) {
  el = resolveEl(el);
  return into(el, async () => { const t = await load.text(url); markdown(el, t, Object.assign({ base: new URL(url, document.baseURI).href }, o)); return t; });
}

/* ════════════════════ grid ════════════════════ */
const FUNNEL = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M0.5 1h9L6 5.2V9L4 8V5.2z" fill="currentColor"/></svg>';
let openPop = null;
function closePop() { if (openPop) { openPop.remove(); openPop = null; } }
document.addEventListener('pointerdown', e => { if (openPop && !openPop.contains(e.target) && !e.target.closest('.sg-fb')) closePop(); }, true);

function encState(s) { return encodeURIComponent(s).replace(/%(7C|2C|3A|2F|40|24|7E|5B|5D|3D)/gi, m => decodeURIComponent(m)); }
function decState(s) { try { return decodeURIComponent(s.replace(/\+/g, '%20')); } catch (e) { return s; } }

function Grid(el, opts) {
  el = resolveEl(el);
  const G = this;
  const o = G.opts = Object.assign({ rowHeight: 24, height: 'fill', search: true, chips: true, csv: true, footer: true, followSelection: true, stateKey: '', overscan: null }, opts);
  const P = o.stateKey ? o.stateKey + '.' : '';
  const listeners = { change: [] };
  let rows = [], cols = [], groups = [], hiddenGroups = new Set(), sort = [], filters = new Map(), q = '';
  let view = new Int32Array(0), posOf = new Int32Array(0), vcols = [], frozenN = 0, leftOf = [], aggs = {};
  let rStart = 0, rEnd = 0, cStart = 0, cEnd = 0, sel = null, lastWritten = new Set(), suppressWrite = false;
  const rh = o.rowHeight;

  // DOM
  const root = h('div', { class: 'sg' + (o.height === 'fill' ? ' sg-fill' : '') + (o.onRowClick ? ' sg-click' : '') });
  root.style.setProperty('--rh', rh + 'px');
  if (typeof o.height === 'number') root.style.height = o.height + 'px';
  const tools = h('div', { class: 'sg-tools' });
  const search = o.search ? h('input', { class: 'sg-search', type: 'search', placeholder: o.searchPlaceholder || 'Search', 'aria-label': 'Search rows' }) : null;
  const chipBox = h('div', { class: 'sg-chips' }), fchipBox = h('div', { class: 'sg-chips' });
  const count = h('span', { class: 'sg-count', 'aria-live': 'polite' });
  const csvBtn = o.csv ? h('button', { class: 'sg-btn', type: 'button', title: 'Download the filtered view as CSV', onclick: () => G.downloadCSV() }, h('span', { class: 'sg-wide', text: 'Download ' }), 'CSV') : null;
  append(tools, [search, chipBox, fchipBox, h('span', { class: 'sg-spacer' }), count, o.tools || null, csvBtn]);
  const vp = h('div', { class: 'sg-vp', tabindex: '0', role: 'grid', 'aria-label': o.label || 'Data grid' });
  const table = h('table'), colgroup = h('colgroup'), thead = h('thead'), tbody = h('tbody'), tfoot = h('tfoot');
  table.append(colgroup, thead, tbody, tfoot); vp.append(table);
  root.append(tools, vp);
  el.append(root);
  G.el = root; G.viewport = vp;

  /* ---------- columns ---------- */
  function normCol(c, i) {
    c = Object.assign({}, c);
    c.key = c.key ?? ('c' + i); c.label = c.label ?? String(c.key);
    if (!c.get) { const k = c.key; c.get = r => r[k]; }
    if (!c.type) {
      if (c.spark) c.type = 'spark';
      else if (c.fmt && c.fmt !== 'text') c.type = 'num';
      else {
        let nn = 0, ns = 0; const seen = new Set();
        for (let r = 0; r < Math.min(rows.length, 300); r++) { const v = c.get(rows[r]); if (v == null || v === '') continue; if (typeof v === 'number') nn++; else { ns++; seen.add(v); } }
        c.type = nn >= ns && nn > 0 ? 'num' : (seen.size <= Math.max(24, ns * 0.2) && ns > 0 ? 'cat' : 'text');
      }
    }
    if (c.type === 'num' && !c.fmt) c.fmt = 'num:1';
    c.f = c.fmt ? fmt.make(c.fmt) : (v => v == null ? '' : String(v));
    c.scale = c.fmt ? fmt.scaleOf(c.fmt) : 1;
    c.isNum = c.type === 'num';
    if (c.filter === undefined) c.filter = c.type === 'num' ? 'range' : c.type === 'cat' ? 'set' : c.type === 'text' ? 'text' : false;
    if (c.agg === undefined) c.agg = c.isNum ? 'mean' : null;
    if (c.search === undefined) c.search = c.type === 'text' || c.type === 'cat';
    c.firstDir = c.firstDir || (c.isNum ? -1 : 1);
    c.align = c.align || (c.isNum || c.type === 'spark' ? 'n' : '');
    c.idx = i;
    return c;
  }
  function estWidth(c, vals) {
    if (c.width) return c.width;
    const lab = Math.ceil(c.label.length * 6.7 + 40);
    if (c.type === 'spark') return Math.max(lab, (c.spark.w || 72) + 18);
    let mx = 0; const n = Math.min(vals.length, 400), step = Math.max(1, Math.floor(vals.length / n));
    for (let r = 0; r < vals.length; r += step) { const v = vals[r]; if (v == null || (typeof v === 'number' && isNaN(v))) continue; const s = c.f(v); if (s.length > mx) mx = s.length; }
    if (c.agg === 'sum') { let t = 0; for (const v of vals) if (!isNaN(v)) t += v; mx = Math.max(mx, c.f(t).length + 2); }
    const data = Math.ceil(mx * (c.isNum ? 7.1 : 6.9) + 18);
    return clamp(Math.max(lab, data), 44, c.isNum ? 160 : 260);
  }

  /* ---------- data caches ---------- */
  let V = [], searchText = null, pctl = [], heatI = [], barD = [];
  function buildCaches() {
    const n = rows.length;
    V = cols.map(c => {
      if (c.isNum) { const a = new Float64Array(n); for (let r = 0; r < n; r++) { const v = c.get(rows[r]); a[r] = v == null || v === '' ? NaN : +v; } return a; }
      const a = new Array(n); for (let r = 0; r < n; r++) a[r] = c.get(rows[r]); return a;
    });
    const sc = cols.filter(c => c.search);
    searchText = new Array(n);
    for (let r = 0; r < n; r++) { let s = ''; for (const c of sc) { const v = V[c.idx][r]; if (v != null) s += String(v).toLowerCase() + '\u0001'; } searchText[r] = s; }
    pctl = []; heatI = []; barD = [];
    cols.forEach((c, j) => {
      if (!c.isNum) return;
      const vals = V[j], s = c.pctile || c.heat || c.bar ? sortedFinite(vals) : null;
      if (c.pctile) {
        const rev = typeof c.pctile === 'object' && c.pctile.reverse, a = new Float32Array(n), N = s.length;
        for (let r = 0; r < n; r++) { const v = vals[r]; if (isNaN(v)) { a[r] = NaN; continue; } const p = N > 1 ? (lowerBound(s, v) + upperBound(s, v) - 1) / 2 / (N - 1) : 0.5; a[r] = rev ? 1 - p : p; }
        pctl[j] = a;
      }
      if (c.heat) {
        const hc = typeof c.heat === 'object' ? c.heat : { type: 'div' };
        const type = hc.type || (hc.center != null ? 'div' : 'seq');
        const a = new Float32Array(n);
        if (type === 'div') {
          const ctr = hc.center ?? 0;
          let d = hc.domain ? Math.max(Math.abs(hc.domain[0] - ctr), Math.abs(hc.domain[1] - ctr)) : quantileSorted(Float64Array.from(s, v => Math.abs(v - ctr)).sort(), 0.96);
          if (!(d > 0)) d = 1;
          for (let r = 0; r < n; r++) { const v = vals[r]; a[r] = isNaN(v) ? NaN : clamp((v - ctr) / d, -1, 1) * (hc.reverse ? -1 : 1); }
        } else {
          const lo = hc.domain ? hc.domain[0] : quantileSorted(s, 0.02), hi = hc.domain ? hc.domain[1] : quantileSorted(s, 0.98), sp = (hi - lo) || 1;
          for (let r = 0; r < n; r++) { const v = vals[r]; let t = isNaN(v) ? NaN : clamp((v - lo) / sp, 0, 1); if (hc.reverse) t = 1 - t; a[r] = t; }
        }
        heatI[j] = { a, type };
      }
      if (c.bar) {
        const bc = typeof c.bar === 'object' ? c.bar : {};
        let lo = bc.domain ? bc.domain[0] : Math.min(0, s[0] ?? 0), hi = bc.domain ? bc.domain[1] : Math.max(0, s[s.length - 1] ?? 1);
        if (hi === lo) hi = lo + 1;
        const base = clamp(bc.base ?? 0, lo, hi);
        barD[j] = { lo, hi, base };
      }
    });
  }

  /* ---------- filtering & sorting ---------- */
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
  function filterFn() {
    const preds = [];
    for (const [k, f] of filters) {
      const c = cols.find(c => c.key === k); if (!c) continue; const a = V[c.idx];
      if (f.kind === 'range') { const lo = f.min, hi = f.max; preds.push(r => { const v = a[r]; return !isNaN(v) && (lo == null || v >= lo) && (hi == null || v <= hi); }); }
      else if (f.kind === 'set') { const S = f.vals; preds.push(r => S.has(a[r] == null ? '' : String(a[r]))); }
      else if (f.kind === 'text') { const t = f.q.toLowerCase(); preds.push(r => a[r] != null && String(a[r]).toLowerCase().includes(t)); }
    }
    const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length) preds.push(r => terms.every(t => searchText[r].includes(t)));
    return preds;
  }
  function compute() {
    const n = rows.length, preds = filterFn(), out = new Int32Array(n); let m = 0;
    outer: for (let r = 0; r < n; r++) { for (let k = 0; k < preds.length; k++) if (!preds[k](r)) continue outer; out[m++] = r; }
    let v = out.slice(0, m);
    const keys = sort.map(s => ({ c: cols.find(c => c.key === s.key), dir: s.dir })).filter(s => s.c);
    if (keys.length) {
      const arr = Array.from(v);
      arr.sort((x, y) => {
        for (const { c, dir } of keys) {
          const a = V[c.idx][x], b = V[c.idx][y];
          if (c.isNum) { const na = isNaN(a), nb = isNaN(b); if (na || nb) { if (na && nb) continue; return na ? 1 : -1; } if (a !== b) return (a - b) * dir; }
          else { const na = a == null || a === '', nb = b == null || b === ''; if (na || nb) { if (na && nb) continue; return na ? 1 : -1; } const r = typeof a === 'number' && typeof b === 'number' ? a - b : collator.compare(String(a), String(b)); if (r) return r * dir; }
        }
        return x - y;
      });
      v = Int32Array.from(arr);
    }
    view = v; posOf = new Int32Array(n).fill(-1); for (let p = 0; p < view.length; p++) posOf[view[p]] = p;
    aggs = {};
    for (const c of cols) {
      if (!c.agg) continue; const a = V[c.idx];
      if (typeof c.agg === 'function') { aggs[c.key] = c.agg(Array.from(view, r => rows[r])); continue; }
      let s = 0, k = 0; for (let p = 0; p < view.length; p++) { const x = a[view[p]]; if (!isNaN(x)) { s += x; k++; } }
      aggs[c.key] = c.agg === 'sum' ? s : c.agg === 'count' ? k : k ? s / k : NaN;
    }
  }

  /* ---------- layout ---------- */
  function layout() {
    vcols = cols.filter(c => !c.hidden && (!c.group || c.frozen || !hiddenGroups.has(c.group)));
    // frozen: leading columns flagged frozen (or o.frozen count); cap so they never take more than half the viewport
    let fz = 0; const want = o.frozen != null ? o.frozen : vcols.findIndex(c => !c.frozen);
    const wantN = want < 0 ? vcols.length : want;
    const avail = (vp.clientWidth || 1200) * 0.55; let acc = 0; leftOf = [];
    for (let j = 0; j < vcols.length; j++) { leftOf[j] = acc; if (j < wantN && acc + vcols[j].w <= avail) fz = j + 1; acc += vcols[j].w; }
    frozenN = Math.min(fz, wantN);
    table.style.width = acc + 'px';
    root.style.setProperty('--fw', (frozenN ? leftOf[frozenN] : 0) + 'px');
    colgroup.innerHTML = vcols.map(c => `<col style="width:${c.w}px">`).join('');
    renderHead(); renderChips();
  }
  function fzAttr(j, extra) {
    const cl = [extra]; let st = '';
    if (j < frozenN) { cl.push('fz'); if (j === frozenN - 1) cl.push('fz-last'); st = ` style="left:${leftOf[j]}px"`; }
    return [cl.filter(Boolean).join(' '), st];
  }
  function groupStart(j) { return j > 0 && j !== frozenN && (vcols[j].group || '') !== (vcols[j - 1].group || ''); }
  function renderHead() {
    const hasGroups = vcols.some(c => c.group);
    let gh = '';
    if (hasGroups) {
      let j = 0; gh = '<tr class="sg-gh">';
      while (j < vcols.length) {
        const g = vcols[j].group || ''; let k = j + 1;
        while (k < vcols.length && (vcols[k].group || '') === g && !(k === frozenN && j < frozenN)) k++;
        if (j < frozenN && k > frozenN) k = frozenN;
        const gl = groups.find(x => x.id === g); const lab = gl ? gl.label : g;
        const isFz = j < frozenN; const st = isFz ? ` style="left:0px"` : '';
        gh += `<th colspan="${k - j}" class="${j === 0 ? 'sg-g0' : ''}${isFz ? ' fz' + (k === frozenN ? ' fz-last' : '') : ''}"${st} title="${esc(lab)}"><span>${esc(lab)}</span></th>`;
        j = k;
      }
      gh += '</tr>';
    }
    let ch = '<tr class="sg-ch">';
    vcols.forEach((c, j) => {
      const si = sort.findIndex(s => s.key === c.key);
      const ar = si >= 0 ? `<span class="sg-ar">${sort[si].dir > 0 ? '▲' : '▼'}${sort.length > 1 ? `<sub>${si + 1}</sub>` : ''}</span>` : '';
      const [cl, st] = fzAttr(j, [c.align, si >= 0 ? 'sorted' : '', filters.has(c.key) ? 'filtered' : '', groupStart(j) ? 'gs' : ''].filter(Boolean).join(' '));
      ch += `<th class="${cl}"${st} data-j="${j}" aria-sort="${si < 0 ? 'none' : sort[si].dir > 0 ? 'ascending' : 'descending'}"><span class="sg-hl"><span class="sg-lab">${esc(c.label)}</span>${ar}</span>${c.filter ? `<span class="sg-fb" role="button" aria-label="Filter ${esc(c.label)}" data-j="${j}">${FUNNEL}</span>` : ''}</th>`;
    });
    thead.innerHTML = gh + ch + '</tr>'; chromeCache = null;
    root.style.setProperty('--gh', hasGroups ? '22px' : '0px');
  }
  function renderChips() {
    if (o.chips && groups.length > 1) {
      chipBox.innerHTML = groups.map(g => `<button type="button" class="sg-chip" data-g="${esc(g.id)}" aria-pressed="${!hiddenGroups.has(g.id)}">${esc(g.label)}</button>`).join('');
    } else chipBox.innerHTML = '';
    const fs = [];
    for (const [k, f] of filters) {
      const c = cols.find(c => c.key === k); if (!c) continue;
      let d = '';
      if (f.kind === 'range') { const F = v => c.f(v); d = f.min != null && f.max != null ? `${F(f.min)} – ${F(f.max)}` : f.min != null ? `≥ ${F(f.min)}` : `≤ ${F(f.max)}`; }
      else if (f.kind === 'set') { const a = [...f.vals]; d = a.length <= 3 ? a.map(x => x === '' ? '(blank)' : x).join(', ') : `${a.length} selected`; }
      else d = `contains “${f.q}”`;
      fs.push(`<span class="sg-fchip"><span><b>${esc(c.label)}</b> ${esc(d)}</span><button type="button" data-clear="${esc(k)}" aria-label="Clear filter on ${esc(c.label)}">×</button></span>`);
    }
    if (fs.length > 1) fs.push(`<button type="button" class="sg-btn" data-clear="*">Clear all</button>`);
    fchipBox.innerHTML = fs.join('');
  }
  function renderCount() {
    const t = view.length === rows.length ? `${fixed(rows.length, 0)} rows` : `${fixed(view.length, 0)} of ${fixed(rows.length, 0)} rows`;
    count.textContent = t;
  }
  function renderFoot() {
    if (!o.footer || !vcols.some(c => c.agg)) { tfoot.innerHTML = ''; chromeCache = null; return; }
    // the label cell spans all frozen columns so it has room
    const span = Math.max(1, frozenN);
    const label = o.footerLabel || (vcols.some(c => c.agg === 'mean') ? 'Mean' : 'Total');
    let spanW = 0; for (let j = 0; j < span; j++) spanW += vcols[j].w;
    let s = `<tr><td colspan="${span}" class="${frozenN ? 'fz fz-last' : ''}" style="${frozenN ? 'left:0px;' : ''}text-overflow:clip"><span class="sg-agg">${esc(label)}</span>${spanW >= 130 ? `<span class="sg-agg" style="text-transform:none;letter-spacing:0">${esc(fixed(view.length, 0))} row${view.length === 1 ? '' : 's'}</span>` : ''}</td>`;
    vcols.forEach((c, j) => {
      if (j < span) return;
      const [cl, st] = fzAttr(j, [c.align, groupStart(j) ? 'gs' : ''].filter(Boolean).join(' '));
      let txt = '';
      if (c.agg && c.key in aggs) { const v = aggs[c.key]; const f = c.aggFmt ? fmt.make(c.aggFmt) : (c.fmt === 'int' && c.agg === 'mean' ? fmt.make('num:1') : c.f); txt = (c.agg === 'sum' ? '<span class="sg-agg" title="Sum">Σ</span>' : '') + (typeof v === 'string' ? esc(v) : esc(f(v))); }
      s += `<td class="${cl}"${st}>${txt}</td>`;
    });
    tfoot.innerHTML = s + '</tr>'; chromeCache = null;
  }

  /* ---------- body (virtualised) ---------- */
  function cellHtml(c, j, r, p) {
    const v = V[c.idx][r], row = rows[r];
    const cls = [c.align]; let style = j < frozenN ? `left:${leftOf[j]}px;` : '';
    if (j < frozenN) { cls.push('fz'); if (j === frozenN - 1) cls.push('fz-last'); }
    if (groupStart(j)) cls.push('gs');
    let txt;
    const empty = v == null || v === '' || (c.isNum && isNaN(v));
    if (c.render) txt = c.render(c.isNum && isNaN(v) ? null : v, row);
    else if (c.type === 'spark') txt = Array.isArray(v) && v.length ? spark(v, c.spark) : '';
    else txt = empty ? '' : esc(c.f(v));
    if (c.type === 'spark') cls.push('sp');
    if (empty && !c.render && c.type !== 'spark') { cls.push('nul'); txt = '–'; }
    else if (c.isNum) {
      const hi = heatI[c.idx];
      if (hi) { const t = hi.a[r]; if (!isNaN(t) && t !== 0) { if (hi.type === 'div') cls.push(t > 0 ? 'hp' : 'hn'); else cls.push('hs'); style += `--h:${Math.round(Math.abs(t) * 100)}%;`; } }
      else if (pctl[c.idx]) { const t = pctl[c.idx][r]; if (!isNaN(t)) { cls.push('hs'); style += `--h:${Math.round(t * 85)}%;`; } }
      const bd = barD[c.idx];
      if (bd && !isNaN(v)) {
        const sp = bd.hi - bd.lo, x0 = (bd.base - bd.lo) / sp, x1 = (clamp(v, bd.lo, bd.hi) - bd.lo) / sp;
        const a = 3 + 94 * Math.min(x0, x1), b = 3 + 94 * Math.max(x0, x1);
        cls.push('db'); if (v < bd.base) cls.push('dbn'); style += `--b0:${a.toFixed(1)}%;--b1:${b.toFixed(1)}%;`;
      }
    }
    if (c.cls) { const x = typeof c.cls === 'function' ? c.cls(v, row) : c.cls; if (x) cls.push(x); }
    if (sel && sel.p === p && sel.j === j) cls.push('sg-sel');
    return `<td class="${cls.join(' ')}"${style ? ` style="${style}"` : ''}>${txt}</td>`;
  }
  // header/footer heights change only when they are re-rendered; cache them to avoid forced layouts while scrolling
  let chromeCache = null;
  function chrome() { if (!chromeCache) chromeCache = { theadH: thead.offsetHeight, footH: tfoot.offsetHeight }; return chromeCache; }
  /** DOM cell for visible column j in a rendered row (accounts for the virtual-column spacer). */
  function cellEl(tr, j) { if (j < frozenN) return tr.children[j]; if (j < cStart || j >= cEnd) return null; return tr.children[frozenN + (cStart > frozenN ? 1 : 0) + j - cStart]; }
  function colOf(td) { const ci = td.cellIndex; if (ci < frozenN) return ci; if (td.classList.contains('sg-xp')) return -1; return cStart + ci - frozenN - (cStart > frozenN ? 1 : 0); }
  function renderBody(force) {
    const n = view.length;
    if (!n) {
      rStart = rEnd = 0;
      tbody.innerHTML = `<tr><td colspan="${vcols.length}" style="border:0"><div class="sg-empty">${rows.length ? 'No rows match the current filters.' : esc(o.emptyText || 'No data.')}</div></td></tr>`;
      return;
    }
    const { theadH, footH } = chrome();
    const vh = vp.clientHeight, vw = vp.clientWidth, sl = vp.scrollLeft, nc = vcols.length;
    const vis = Math.ceil(Math.max(rh, vh - theadH - footH) / rh) + 1;
    const first = Math.floor(vp.scrollTop / rh);
    // visible column window (non-frozen part), in column indices
    const fw = frozenN ? leftOf[frozenN] : 0;
    let v0 = frozenN; while (v0 < nc - 1 && leftOf[v0] + vcols[v0].w <= sl + fw) v0++;
    let v1 = v0; while (v1 < nc && leftOf[v1] < sl + vw) v1++;
    if (!force && first >= rStart && first + vis <= rEnd && v0 >= cStart && v1 <= cEnd) return;
    const os = o.overscan != null ? o.overscan : 8;
    const nS = Math.max(0, first - os), nE = Math.min(n, first + vis + os);
    let c0 = Math.max(frozenN, v0 - 4), c1 = Math.min(nc, v1 + 4);
    if (o.virtualColumns === false) { c0 = frozenN; c1 = nc; }
    const rowsHtml = (a, b) => {
      let s = '';
      const rc = o.rowClass, padL = cStart > frozenN ? `<td class="sg-xp" colspan="${cStart - frozenN}"></td>` : '', padR = cEnd < nc ? `<td class="sg-xp" colspan="${nc - cEnd}"></td>` : '';
      for (let p = a; p < b; p++) {
        const r = view[p]; let cl = sel && sel.p === p ? 'sg-cur' : '';
        if (rc) { const x = rc(rows[r], r); if (x) cl += ' ' + x; }
        s += `<tr data-p="${p}"${cl ? ` class="${cl}"` : ''}>`;
        for (let j = 0; j < frozenN; j++) s += cellHtml(vcols[j], j, r, p);
        s += padL;
        for (let j = cStart; j < cEnd; j++) s += cellHtml(vcols[j], j, r, p);
        s += padR + '</tr>';
      }
      return s;
    };
    const padTop = tbody.firstElementChild, padBot = tbody.lastElementChild;
    // Incremental path: same columns, overlapping row window -> drop rows that left, add rows that entered.
    if (!force && c0 === cStart && c1 === cEnd && nS < rEnd && nE > rStart && padTop && padTop.classList.contains('sg-pad') && padBot !== padTop) {
      for (let p = rStart; p < nS; p++) padTop.nextElementSibling.remove();
      for (let p = Math.max(nE, rStart); p < rEnd; p++) padBot.previousElementSibling.remove();
      if (nS < rStart) padTop.insertAdjacentHTML('afterend', rowsHtml(nS, rStart));
      if (nE > rEnd) padBot.insertAdjacentHTML('beforebegin', rowsHtml(rEnd, nE));
      rStart = nS; rEnd = nE;
      padTop.firstElementChild.style.height = rStart * rh + 'px';
      padBot.firstElementChild.style.height = (n - rEnd) * rh + 'px';
      return;
    }
    rStart = nS; rEnd = nE; cStart = c0; cEnd = c1;
    tbody.innerHTML = `<tr class="sg-pad"><td colspan="${nc}" style="height:${rStart * rh}px"></td></tr>` + rowsHtml(rStart, rEnd) +
      `<tr class="sg-pad"><td colspan="${nc}" style="height:${(n - rEnd) * rh}px"></td></tr>`;
  }
  let raf = 0;
  vp.addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; renderBody(false); }); }, { passive: true });
  if (typeof ResizeObserver !== 'undefined') {
    let lastW = 0, lastH = 0;
    new ResizeObserver(() => {
      const w = vp.clientWidth, hh = vp.clientHeight; if (!w) return;
      if (Math.abs(w - lastW) > 1) { lastW = w; const before = frozenN; layout(); if (before !== frozenN) renderFoot(); renderBody(true); return; }
      if (Math.abs(hh - lastH) > 1) { lastH = hh; chromeCache = null; renderBody(true); }
    }).observe(vp);
  }

  function full() { compute(); renderHead(); renderChips(); renderCount(); renderFoot(); if (sel) { const p = posOf[sel.r]; sel = p >= 0 ? Object.assign(sel, { p }) : null; } renderBody(true); emit(); }
  function emit() { listeners.change.forEach(f => f(G)); writeState(); }

  /* ---------- selection & keyboard ---------- */
  function selAt(p, j, scroll = true) {
    if (!view.length) return;
    p = clamp(p, 0, view.length - 1); j = clamp(j, 0, vcols.length - 1);
    const prev = sel; sel = { p, j, r: view[p] };
    // update classes in place
    if (prev) { const tr = tbody.querySelector(`tr[data-p="${prev.p}"]`); if (tr) { tr.classList.remove('sg-cur'); const td = cellEl(tr, prev.j); if (td) td.classList.remove('sg-sel'); } }
    if (scroll) ensureVisible(p, j);
    const tr = tbody.querySelector(`tr[data-p="${p}"]`);
    const td = tr && cellEl(tr, j);
    if (td) { tr.classList.add('sg-cur'); td.classList.add('sg-sel'); } else renderBody(true);
  }
  function ensureVisible(p, j) {
    const { theadH, footH } = chrome(), top = p * rh, bodyH = vp.clientHeight - theadH - footH;
    if (top < vp.scrollTop) vp.scrollTop = top; else if (top + rh > vp.scrollTop + bodyH) vp.scrollTop = top + rh - bodyH;
    if (j >= frozenN) {
      const fw = frozenN ? leftOf[frozenN] : 0, L = leftOf[j], R = L + vcols[j].w;
      if (L - fw < vp.scrollLeft) vp.scrollLeft = L - fw; else if (R > vp.scrollLeft + vp.clientWidth) vp.scrollLeft = R - vp.clientWidth;
    }
    renderBody(false);
  }
  const followDrawer = debounce(() => { if (sel && o.onRowClick && o.followSelection && drawer.isOpen) o.onRowClick(rows[sel.r], sel.r, null); }, 70);
  vp.addEventListener('keydown', e => {
    if (e.target !== vp) return;
    const { theadH, footH } = chrome(), bodyRows = Math.max(1, Math.floor((vp.clientHeight - theadH - footH) / rh) - 1);
    const s = sel || { p: -1, j: 0 }; let p = s.p, j = s.j, moved = true;
    switch (e.key) {
      case 'ArrowDown': p = s.p < 0 ? 0 : p + 1; break;
      case 'ArrowUp': p = Math.max(0, p - 1); break;
      case 'ArrowRight': j++; if (p < 0) p = 0; break;
      case 'ArrowLeft': j--; if (p < 0) p = 0; break;
      case 'PageDown': p = Math.max(0, p) + bodyRows; break;
      case 'PageUp': p = Math.max(0, p - bodyRows); break;
      case 'Home': if (e.ctrlKey || e.metaKey) p = 0; j = 0; if (p < 0) p = 0; break;
      case 'End': if (e.ctrlKey || e.metaKey) p = view.length - 1; j = vcols.length - 1; if (p < 0) p = 0; break;
      case 'Enter': moved = false; if (sel && o.onRowClick) o.onRowClick(rows[sel.r], sel.r, e); break;
      case 'Escape': moved = false; if (drawer.isOpen) drawer.close(); else if (sel) { selAt(sel.p, sel.j, false); sel = null; renderBody(true); } break;
      default: return;
    }
    e.preventDefault();
    if (moved) { const rowChanged = !sel || p !== sel.p; selAt(p, j); if (rowChanged) followDrawer(); }
  });
  function cellText(r, c) {
    const v = V[c.idx][r];
    if (c.copyText) return c.copyText(v, rows[r]);
    if (c.type === 'spark') return Array.isArray(v) ? v.join(' ') : '';
    if (v == null || (c.isNum && isNaN(v))) return '';
    return c.f(v);
  }
  let flashT;
  function flash(msg) { const old = count.textContent; clearTimeout(flashT); count.textContent = msg; flashT = setTimeout(renderCount, 1200); }
  document.addEventListener('copy', e => {
    if (document.activeElement !== vp || !sel) return;
    const txt = cellText(sel.r, vcols[sel.j]);
    e.clipboardData.setData('text/plain', txt); e.preventDefault();
    flash(`Copied ${txt.length > 24 ? txt.slice(0, 24) + '…' : txt}`);
  });
  tbody.addEventListener('click', e => {
    const td = e.target.closest('td'); const tr = td && td.parentElement; if (!tr || tr.dataset.p == null) return;
    if (e.target.closest('a')) return;
    const p = +tr.dataset.p, j = colOf(td); if (j < 0) return;
    selAt(p, j, false); vp.focus({ preventScroll: true });
    if (o.onRowClick) o.onRowClick(rows[view[p]], view[p], e);
  });

  /* ---------- header interactions ---------- */
  let htT = null;
  thead.addEventListener('click', e => {
    const fb = e.target.closest('.sg-fb'); if (fb) { e.stopPropagation(); openFilter(vcols[+fb.dataset.j], fb.closest('th')); return; }
    const th = e.target.closest('tr.sg-ch th'); if (!th) return;
    clearTimeout(htT); tip.hide();
    const c = vcols[+th.dataset.j]; const i = sort.findIndex(s => s.key === c.key);
    if (e.shiftKey) {
      if (i < 0) sort.push({ key: c.key, dir: c.firstDir });
      else if (sort[i].dir === c.firstDir) sort[i].dir = -c.firstDir; else sort.splice(i, 1);
    } else {
      if (i < 0 || sort.length > 1) sort = [{ key: c.key, dir: i >= 0 && sort.length > 1 ? sort[i].dir : c.firstDir }];
      else if (sort[0].dir === c.firstDir) sort[0].dir = -c.firstDir; else sort = [];
    }
    full();
  });
  thead.addEventListener('mouseover', e => {
    const th = e.target.closest('tr.sg-ch th'); clearTimeout(htT);
    if (!th) { tip.hide(); return; }
    const c = vcols[+th.dataset.j];
    htT = setTimeout(() => {
      const r = th.getBoundingClientRect();
      let s = `<div class="tt-r"><b>${esc(c.label)}</b>${c.group ? `<span>${esc((groups.find(g => g.id === c.group) || {}).label || c.group)}</span>` : ''}</div>`;
      if (c.desc) s += `<div class="tt-d">${esc(c.desc)}</div>`;
      s += `<div class="tt-d">Click to sort · Shift-click to add</div>`;
      tip.show(r.left - 8, r.bottom - 6, s);
    }, 380);
  });
  thead.addEventListener('mouseleave', () => { clearTimeout(htT); tip.hide(); });
  tools.addEventListener('click', e => {
    const chip = e.target.closest('.sg-chip');
    if (chip) { const g = chip.dataset.g; hiddenGroups.has(g) ? hiddenGroups.delete(g) : hiddenGroups.add(g); layout(); renderFoot(); renderBody(true); emit(); return; }
    const cl = e.target.closest('[data-clear]');
    if (cl) { const k = cl.dataset.clear; if (k === '*') filters.clear(); else filters.delete(k); closePop(); full(); }
  });
  if (search) search.addEventListener('input', debounce(() => { q = search.value; vp.scrollTop = 0; full(); }, 90));

  function openFilter(c, th) {
    closePop(); tip.hide();
    const pop = h('div', { class: 'sg-pop', role: 'dialog', 'aria-label': 'Filter ' + c.label });
    const f = filters.get(c.key);
    const sortBtn = (dir, lab) => h('button', { class: 'sg-btn', type: 'button', text: lab, onclick: () => { sort = [{ key: c.key, dir }]; full(); } });
    append(pop, [
      h('div', { class: 'sg-pop-h' }, h('span', { text: c.label }), h('button', { class: 'sg-link', type: 'button', text: 'Close', onclick: closePop })),
      c.desc ? h('div', { class: 'sg-pop-d', text: c.desc }) : null,
      h('div', { class: 'sg-pop-sort' }, sortBtn(c.isNum ? -1 : 1, c.isNum ? 'High → low' : 'A → Z'), sortBtn(c.isNum ? 1 : -1, c.isNum ? 'Low → high' : 'Z → A')),
    ]);
    const apply = nf => { if (nf) filters.set(c.key, nf); else filters.delete(c.key); vp.scrollTop = 0; full(); };
    if (c.filter === 'range') {
      const sc = c.scale, ex = stats.extent(V[c.idx]);
      const mk = (lab, val) => { const i = h('input', { type: 'number', step: 'any', value: val == null ? '' : +(val * sc).toPrecision(10), placeholder: lab === 'Min' ? fixed(ex[0] * sc, 2) : fixed(ex[1] * sc, 2) }); return [h('label', null, lab, i), i]; };
      const [l1, i1] = mk('Min', f && f.min), [l2, i2] = mk('Max', f && f.max);
      const go = debounce(() => { const a = i1.value === '' ? null : +i1.value / sc, b = i2.value === '' ? null : +i2.value / sc; apply(a == null && b == null ? null : { kind: 'range', min: a, max: b }); }, 160);
      i1.addEventListener('input', go); i2.addEventListener('input', go);
      append(pop, [h('div', { class: 'sg-mm' }, l1, l2), h('div', { class: 'sg-hint', text: `Range in data: ${c.f(ex[0])} to ${c.f(ex[1])}${sc !== 1 ? ' (type in %)' : ''}` })]);
      setTimeout(() => i1.focus(), 0);
    } else if (c.filter === 'set') {
      const counts = new Map(); for (const v of V[c.idx]) { const k = v == null ? '' : String(v); counts.set(k, (counts.get(k) || 0) + 1); }
      const vals = [...counts.keys()].sort((a, b) => collator.compare(a, b));
      const cur = f ? new Set(f.vals) : new Set(vals);
      const box = h('div', { class: 'sg-set' });
      const flt = vals.length > 12 ? h('input', { type: 'text', placeholder: 'Find value' }) : null;
      const draw = () => {
        const t = flt ? flt.value.toLowerCase() : '';
        box.innerHTML = vals.filter(v => !t || v.toLowerCase().includes(t)).map(v => `<label><input type="checkbox" value="${esc(v)}"${cur.has(v) ? ' checked' : ''}>${esc(v === '' ? '(blank)' : v)}<span class="sg-n">${fixed(counts.get(v), 0)}</span></label>`).join('');
      };
      draw(); if (flt) flt.addEventListener('input', draw);
      const commit = () => apply(cur.size === vals.length ? null : { kind: 'set', vals: new Set(cur) });
      box.addEventListener('change', e => { const v = e.target.value; e.target.checked ? cur.add(v) : cur.delete(v); commit(); });
      const all = h('button', { class: 'sg-link', type: 'button', text: 'All', onclick: () => { vals.forEach(v => cur.add(v)); draw(); commit(); } });
      const none = h('button', { class: 'sg-link', type: 'button', text: 'None', onclick: () => { cur.clear(); draw(); commit(); } });
      append(pop, [flt, box, h('div', { class: 'sg-pop-f' }, h('span', null, all, ' · ', none), h('span', { class: 'sg-hint', text: `${vals.length} values` }))]);
      if (flt) setTimeout(() => flt.focus(), 0);
    } else if (c.filter === 'text') {
      const i = h('input', { type: 'text', placeholder: 'Contains…', value: f ? f.q : '' });
      i.addEventListener('input', debounce(() => apply(i.value ? { kind: 'text', q: i.value } : null), 120));
      pop.append(i); setTimeout(() => i.focus(), 0);
    }
    pop.append(h('div', { class: 'sg-pop-f' }, h('button', { class: 'sg-link', type: 'button', text: 'Clear filter', onclick: () => { apply(null); closePop(); } })));
    pop.addEventListener('keydown', e => { if (e.key === 'Escape') { closePop(); vp.focus(); } });
    document.body.append(pop); openPop = pop;
    const r = th.getBoundingClientRect(), pw = pop.offsetWidth;
    pop.style.left = clamp(c.isNum ? r.right - pw : r.left, 8, innerWidth - pw - 8) + 'px';
    pop.style.top = Math.min(r.bottom + 4, innerHeight - pop.offsetHeight - 8) + 'px';
  }

  /* ---------- state (URL hash) ---------- */
  function encFilter(c, f) {
    if (f.kind === 'range') return `${f.min ?? ''}..${f.max ?? ''}`;
    if (f.kind === 'set') return '=' + [...f.vals].map(v => v.replace(/[|%]/g, m => encodeURIComponent(m))).join('|');
    return '~' + f.q;
  }
  function decFilter(s) {
    if (s.startsWith('~')) return { kind: 'text', q: s.slice(1) };
    if (s.startsWith('=')) return { kind: 'set', vals: new Set(s.slice(1).split('|').map(v => decState(v))) };
    const m = s.match(/^(-?[\d.e+-]*)\.\.(-?[\d.e+-]*)$/);
    if (m) return { kind: 'range', min: m[1] === '' ? null : +m[1], max: m[2] === '' ? null : +m[2] };
    return null;
  }
  G.getState = () => {
    const st = {};
    if (sort.length) st[P + 'sort'] = sort.map(s => (s.dir < 0 ? '-' : '') + s.key).join(',');
    if (q) st[P + 'q'] = q;
    if (hiddenGroups.size) st[P + 'hide'] = [...hiddenGroups].join(',');
    for (const [k, f] of filters) { const c = cols.find(c => c.key === k); if (c) st[P + 'f.' + k] = encFilter(c, f); }
    return st;
  };
  G.setState = (params, silent) => {
    params = params || {};
    sort = (params[P + 'sort'] || '').split(',').filter(Boolean).map(t => ({ key: t.replace(/^[-+]/, ''), dir: t.startsWith('-') ? -1 : 1 })).filter(s => cols.some(c => c.key === s.key));
    if (!params[P + 'sort'] && o.sort) sort = parseSort(o.sort);
    q = params[P + 'q'] || ''; if (search) search.value = q;
    hiddenGroups = new Set((params[P + 'hide'] || '').split(',').filter(Boolean));
    if (!(P + 'hide' in params)) groups.forEach(g => { if (g.hidden) hiddenGroups.add(g.id); });
    filters = new Map();
    for (const k in params) if (k.startsWith(P + 'f.')) { const key = k.slice(P.length + 2); const f = decFilter(params[k]); if (f && cols.some(c => c.key === key)) filters.set(key, f); }
    suppressWrite = true; layout(); full(); suppressWrite = false;
    if (!silent) listeners.change.forEach(f => f(G));
  };
  function parseSort(s) { return (Array.isArray(s) ? s : String(s).split(',')).filter(Boolean).map(t => typeof t === 'object' ? t : ({ key: t.replace(/^[-+]/, ''), dir: t.startsWith('-') ? -1 : 1 })); }
  function writeState() {
    if (suppressWrite || !o.state || !o.state.set) return;
    const st = G.getState(); const patch = {};
    for (const k of lastWritten) if (!(k in st)) patch[k] = null;
    Object.assign(patch, st);
    // hidden groups that equal the defaults are still written so the URL is explicit
    lastWritten = new Set(Object.keys(st));
    o.state.set(patch);
  }

  /* ---------- public API ---------- */
  /** Replace the rows (keeps columns, sort, filters and column widths). */
  G.setRows = rs => { rows = rs || []; buildCaches(); sel = null; full(); };
  G.setColumns = (cs, gs) => {
    groups = (gs || o.groups || []).map(g => typeof g === 'string' ? { id: g, label: g } : g);
    cols = cs.map(normCol);
    // derive groups from columns when not given
    for (const c of cols) if (c.group && !c.frozen && !groups.some(g => g.id === c.group)) groups.push({ id: c.group, label: c.group });
    buildCaches();
    cols.forEach((c, j) => { c.w = estWidth(c, V[j]); });
    layout();
  };
  G.refresh = () => { buildCaches(); full(); };
  G.getView = () => Array.from(view, r => rows[r]);
  G.getRows = () => rows;
  G.getColumns = () => cols;
  G.setSort = s => { sort = parseSort(s); full(); };
  G.setFilter = (key, f) => { if (f) filters.set(key, f.kind ? f : (Array.isArray(f) ? { kind: 'set', vals: new Set(f.map(String)) } : typeof f === 'string' ? { kind: 'text', q: f } : { kind: 'range', min: f.min ?? null, max: f.max ?? null })); else filters.delete(key); full(); };
  G.clearFilters = () => { filters.clear(); q = ''; if (search) search.value = ''; full(); };
  G.setSearch = s => { q = s || ''; if (search) search.value = q; full(); };
  G.setGroupVisible = (id, on) => { on ? hiddenGroups.delete(id) : hiddenGroups.add(id); layout(); renderFoot(); renderBody(true); emit(); };
  G.select = (rowIndex, colKey) => { const p = posOf[rowIndex]; if (p < 0) return false; const j = colKey ? Math.max(0, vcols.findIndex(c => c.key === colKey)) : (sel ? sel.j : 0); selAt(p, j); return true; };
  G.selected = () => sel ? { row: rows[sel.r], index: sel.r, column: vcols[sel.j] && vcols[sel.j].key } : null;
  /** Move the selected row by delta within the current view and fire onRowClick (for drawer prev/next). */
  G.step = delta => { if (!view.length) return; const p = clamp((sel ? sel.p : -1) + delta, 0, view.length - 1); selAt(p, sel ? sel.j : 0); if (o.onRowClick) o.onRowClick(rows[view[p]], view[p], null); };
  G.on = (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); return G; };
  G.toCSV = () => {
    const q = s => { s = s == null ? '' : String(s); return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const cs = vcols;
    const lines = [cs.map(c => q(c.csvLabel || (c.group && o.csvGroupPrefix ? c.group + ' ' : '') + c.label)).join(',')];
    for (let p = 0; p < view.length; p++) {
      const r = view[p];
      lines.push(cs.map(c => { const v = V[c.idx][r]; if (c.csv) return q(c.csv(v, rows[r])); if (Array.isArray(v)) return q(v.join(';')); if (c.isNum) return isNaN(v) ? '' : String(v); return q(v); }).join(','));
    }
    return lines.join('\n') + '\n';
  };
  G.downloadCSV = name => {
    const blob = new Blob([G.toCSV()], { type: 'text/csv;charset=utf-8' });
    const a = h('a', { href: URL.createObjectURL(blob), download: name || (typeof o.csv === 'string' ? o.csv : (o.name || 'sheet') + '.csv') });
    document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  };
  G.focus = () => vp.focus();
  G.destroy = () => { root.remove(); };

  // init
  rows = o.rows || [];
  G.setColumns(o.columns || []);
  const initial = o.state && o.state.params ? o.state.params : (o.initialState || {});
  G.setState(initial, true);
  if (o.state && o.state.onState) o.state.onState(params => G.setState(params));
  if (o.onChange) G.on('change', o.onChange);
}
function grid(el, opts) { return new Grid(el, opts); }

/* ════════════════════ drawer ════════════════════ */
const drawer = (() => {
  let el, head, title, sub, body, nav, scrim, onClose, lastFocus;
  function ensure() {
    if (el) return;
    title = h('h2'); sub = h('div', { class: 'sh-sub' }); nav = h('div', { class: 'sh-drawer-nav' });
    const x = h('button', { class: 'sh-drawer-x', type: 'button', 'aria-label': 'Close panel', text: '×', onclick: () => api.close() });
    head = h('div', { class: 'sh-drawer-h' }, h('div', { style: { minWidth: 0 } }, title, sub), nav, x);
    body = h('div', { class: 'sh-drawer-b' });
    el = h('aside', { class: 'sh-drawer', 'aria-label': 'Details', 'aria-hidden': 'true' }, head, body);
    scrim = h('div', { class: 'sh-scrim', onclick: () => api.close() });
    document.body.append(scrim, el);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && api.isOpen && !openPop && !e.defaultPrevented) api.close(); });
  }
  const api = {
    isOpen: false,
    get body() { ensure(); return body; },
    /** open({title, sub, body: Node|html|fn(el), nav:{prev:fn, next:fn}, onClose, focus}) — calling again while open replaces content. */
    open(o = {}) {
      ensure();
      title.textContent = o.title || ''; sub.textContent = o.sub || ''; sub.hidden = !o.sub;
      nav.innerHTML = '';
      if (o.nav) append(nav, [h('button', { class: 'sh-drawer-x', type: 'button', title: 'Previous row', 'aria-label': 'Previous row', text: '↑', onclick: o.nav.prev }), h('button', { class: 'sh-drawer-x', type: 'button', title: 'Next row', 'aria-label': 'Next row', text: '↓', onclick: o.nav.next })]);
      const st = body.scrollTop; setContent(body, o.body); if (o.keepScroll) body.scrollTop = st;
      if (!api.isOpen) lastFocus = document.activeElement;
      el.classList.add('open'); scrim.classList.add('open'); el.setAttribute('aria-hidden', 'false'); api.isOpen = true; onClose = o.onClose;
      if (o.focus) el.querySelector('.sh-drawer-x').focus();
      return body;
    },
    close() {
      if (!el || !api.isOpen) return;
      el.classList.remove('open'); scrim.classList.remove('open'); el.setAttribute('aria-hidden', 'true'); api.isOpen = false;
      if (onClose) onClose();
      if (lastFocus && document.contains(lastFocus) && el.contains(document.activeElement)) lastFocus.focus();
    },
  };
  return api;
})();

/** Definition list: kv([['Runs', '412'], ['SR', '138.2']], {cols:2}) */
function kv(pairs, o = {}) {
  const dl = h('dl', { class: 'sh-kv' + (o.cols === 2 ? ' cols2' : '') });
  for (const [k, v] of pairs) dl.append(h('dt', { text: k }), v instanceof Node ? h('dd', null, v) : h('dd', { text: v ?? '–' }));
  return dl;
}
/** Stat tiles: tiles([{label, value, sub}]) */
function tiles(items) {
  return h('div', { class: 'sh-tiles' }, items.map(t => h('div', { class: 'sh-tile' }, h('div', { class: 'sh-tile-l', text: t.label }), h('div', { class: 'sh-tile-v', text: t.value ?? '–' }), t.sub ? h('div', { class: 'sh-tile-s', text: t.sub }) : null)));
}
/** Simple static table from columns + rows (for small tables in cards and drawers). */
function table(el, cols, rows, o = {}) {
  el = resolveEl(el);
  cols = cols.map(c => typeof c === 'string' ? { key: c, label: c } : c).map(c => Object.assign({ f: c.fmt ? fmt.make(c.fmt) : (v => v ?? '') }, c));
  const th = cols.map(c => `<th class="${c.fmt && c.fmt !== 'text' ? 'n' : ''}"${c.desc ? ` title="${esc(c.desc)}"` : ''}>${esc(c.label ?? c.key)}</th>`).join('');
  const tb = rows.map((r, i) => `<tr${o.highlight && o.highlight(r, i) ? ' class="hl"' : ''}>${cols.map(c => { const v = c.get ? c.get(r) : r[c.key]; return `<td class="${c.fmt && c.fmt !== 'text' ? 'n' : ''}">${c.render ? c.render(v, r) : esc(c.f(v))}</td>`; }).join('')}</tr>`).join('');
  el.innerHTML = `<div class="sh-tbl-wrap"><table class="sh-tbl"><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`;
  return el;
}

/* ════════════════════ charts ════════════════════ */
function niceStep(span, n) { const s0 = span / Math.max(1, n); const mag = 10 ** Math.floor(Math.log10(s0)); const e = s0 / mag; return (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag; }
function ticks(lo, hi, n = 5) {
  if (!isFinite(lo) || !isFinite(hi)) return { ticks: [0, 1], lo: 0, hi: 1, step: 1 };
  if (lo === hi) { lo -= 1; hi += 1; }
  const step = niceStep(hi - lo, n); const out = [];
  for (let t = Math.ceil(lo / step - 1e-9) * step; t <= hi + step * 1e-9; t += step) out.push(+t.toFixed(12));
  return { ticks: out, step, lo, hi };
}
function niceDomain(lo, hi, n = 5) { if (lo === hi) { lo -= 1; hi += 1; } const s = niceStep(hi - lo, n); return [Math.floor(lo / s + 1e-9) * s, Math.ceil(hi / s - 1e-9) * s]; }
function lin(d0, d1, r0, r1) { const k = (r1 - r0) / ((d1 - d0) || 1); const f = v => r0 + (v - d0) * k; f.inv = p => d0 + (p - r0) / k; f.d = [d0, d1]; f.r = [r0, r1]; return f; }
function autoTickFmt(step, maxAbs) {
  if (maxAbs >= 1e4) return v => fmt.compact(v, step >= 1000 ? 0 : 1);
  const dp = Math.max(0, Math.min(6, -Math.floor(Math.log10(step) + 1e-9)));
  return v => fixed(v, dp);
}
function tickFmtFor(spec, t) { return spec ? fmt.make(spec) : autoTickFmt(t.step, Math.max(Math.abs(t.lo), Math.abs(t.hi))); }
const textW = (s, px = 10.5) => String(s).length * px * 0.56;
function vbar(x, y, w, hgt, r = 4) { if (hgt <= 0.3 || w <= 0) return ''; r = Math.min(r, w / 2, hgt); return `M${x},${y + hgt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt}Z`; }
function hbar(x0, x1, y, hgt, r = 4) {
  const w = Math.abs(x1 - x0); if (w < 0.3) return ''; r = Math.min(r, hgt / 2, w);
  return x1 >= x0 ? `M${x0},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${y + hgt - r}Q${x1},${y + hgt} ${x1 - r},${y + hgt}H${x0}Z`
    : `M${x0},${y}H${x1 + r}Q${x1},${y} ${x1},${y + r}V${y + hgt - r}Q${x1},${y + hgt} ${x1 + r},${y + hgt}H${x0}Z`;
}
function yAxis(y, t, f, x0, x1) {
  let s = '<g class="gr">'; for (const v of t.ticks) s += `<line x1="${x0}" x2="${x1}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/>`; s += '</g><g class="ax">';
  for (const v of t.ticks) s += `<text x="${x0 - 6}" y="${y(v).toFixed(1)}" dy="0.32em" text-anchor="end">${esc(f(v))}</text>`;
  return s + '</g>';
}
function xAxis(x, t, f, y0, o = {}) {
  let s = `<g class="ax"><line x1="${x.r[0]}" x2="${x.r[1]}" y1="${y0}" y2="${y0}"/>`;
  let lastR = -Infinity;
  for (const v of t.ticks) { const px = x(v); const lab = f(v); const w = textW(lab); if (px - w / 2 < lastR + 6) continue; lastR = px + w / 2; s += `<line x1="${px.toFixed(1)}" x2="${px.toFixed(1)}" y1="${y0}" y2="${y0 + 4}"/><text x="${px.toFixed(1)}" y="${y0 + 15}" text-anchor="middle">${esc(lab)}</text>`; }
  return s + '</g>';
}
function legendHtml(items, kind = 'r') { return `<div class="sc-legend">${items.map((n, i) => `<span><i class="${kind === 'l' ? 'l ' : kind === 'd' ? 'd ' : ''}${keyCls(i)}"></i>${esc(n)}</span>`).join('')}</div>`; }
function markersSvg(markers, x, top, bottom) {
  let s = '', lab = 0;
  (markers || []).forEach((m, i) => {
    const px = x(m.x); if (!(px >= x.r[0] - 0.5 && px <= x.r[1] + 0.5)) return;
    const anchor = px > (x.r[0] + x.r[1]) / 2 + (x.r[1] - x.r[0]) * 0.3 ? 'end' : 'start';
    const row = m.label ? lab++ % 2 : 0;
    s += `<g class="mk${m.strong ? ' m1' : ''}"><line x1="${px.toFixed(1)}" x2="${px.toFixed(1)}" y1="${top - (m.label ? 3 + row * 12 : 0)}" y2="${bottom}"/>${m.label ? `<text x="${(px + (anchor === 'end' ? -4 : 4)).toFixed(1)}" y="${top - 4 - row * 12}" text-anchor="${anchor}">${esc(m.label)}</text>` : ''}</g>`;
  });
  return s;
}
/** Vertical space to reserve above a plot for marker labels. */
const mkBand = ms => { const n = (ms || []).filter(m => m.label).length; return n ? (n > 1 ? 28 : 16) : 0; };
/** Base wrapper: resolves el, re-renders on width change, exposes update(). */
function chartBase(el, opts, draw) {
  el = resolveEl(el); el.classList.add('sc');
  const api = { el, opts };
  let lastW = 0;
  const render = () => { const w = opts.width || el.clientWidth || 600; lastW = w; draw(el, w, opts, api); };
  api.update = o => { if (o) Object.assign(opts, o); render(); return api; };
  render();
  if (!opts.width && typeof ResizeObserver !== 'undefined') {
    let raf = 0; const ro = new ResizeObserver(() => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; if (Math.abs((el.clientWidth || 0) - lastW) > 2) render(); }); });
    ro.observe(el); api.destroy = () => ro.disconnect();
  }
  return api;
}
function wireHover(svg, sel, fn) {
  svg.addEventListener('pointermove', e => { const t = e.target.closest(sel); if (t) { const html = fn(t, e); if (html) tip.show(e.clientX, e.clientY, html); } else tip.hide(); });
  svg.addEventListener('pointerleave', () => tip.hide());
}
const titleHtml = o => o.title ? `<div class="sh-h" style="margin-bottom:${o.subtitle ? 0 : 6}px">${esc(o.title)}</div>${o.subtitle ? `<div class="sh-note" style="margin-bottom:6px">${esc(o.subtitle)}</div>` : ''}` : '';

/* ---- histogram / pmf ---- */
function toBins(o) {
  if (o.bins && Array.isArray(o.bins)) return { bins: o.bins.map(b => ({ x0: b.x0, x1: b.x1, y: b.y ?? b.p ?? b.count })), discrete: false };
  let pmf = o.pmf;
  if (o.dist) pmf = o.dist.pmf();
  if (!pmf && o.values) {
    const s = sortedFinite(o.values), n = s.length; if (!n) return { bins: [], discrete: false };
    const allInt = s.every(v => Number.isInteger(v));
    if (allInt && s[n - 1] - s[0] <= (o.maxDiscrete || 160) && !o.binWidth && !o.binCount) { const m = new Map(); for (const v of s) m.set(v, (m.get(v) || 0) + 1); pmf = [...m].map(([x, c]) => ({ x, p: c / n })); }
    else {
      const lo = s[0], hi = s[n - 1];
      let bw = o.binWidth || (o.binCount ? (hi - lo) / o.binCount : niceStep(hi - lo, 30));
      const start = Math.floor(lo / bw) * bw, k = Math.max(1, Math.ceil((hi - start) / bw + 1e-9));
      const c = new Array(k).fill(0); for (const v of s) c[Math.min(k - 1, Math.floor((v - start) / bw))]++;
      return { bins: c.map((y, i) => ({ x0: start + i * bw, x1: start + (i + 1) * bw, y: o.normalize === false ? y : y / n })), discrete: false };
    }
  }
  if (!pmf) return { bins: [], discrete: true };
  const rows = Array.isArray(pmf) ? pmf.map(r => Array.isArray(r) ? { x: +r[0], p: +r[1] } : { x: +r.x, p: +(r.p ?? r.y) }) : Object.entries(pmf).map(([x, p]) => ({ x: +x, p: +p }));
  rows.sort((a, b) => a.x - b.x);
  if (o.normalize !== false) { const t = rows.reduce((a, r) => a + r.p, 0) || 1; rows.forEach(r => r.p /= t); }
  const w = o.binWidth && !o.groupWidth ? o.binWidth : (rows.length > 1 ? Math.min(...rows.slice(1).map((r, i) => r.x - rows[i].x)) : 1) || 1;
  const span = rows.length ? rows[rows.length - 1].x - rows[0].x : 0;
  // many discrete values (e.g. innings totals): group into wider bins so bars stay legible
  const gw = o.groupWidth || (span / w > (o.maxBars || 60) ? Math.max(w, Math.ceil(niceStep(span, 40) / w) * w) : 0);
  if (gw > w) {
    const start = Math.floor(rows[0].x / gw) * gw, m = new Map();
    for (const r of rows) { const k = Math.floor((r.x - start) / gw + 1e-9); m.set(k, (m.get(k) || 0) + r.p); }
    const ks = [...m.keys()].sort((a, b) => a - b), out = [];
    for (let k = ks[0]; k <= ks[ks.length - 1]; k++) { const lo = start + k * gw; out.push({ x0: lo - w / 2, x1: lo + gw - w / 2, y: m.get(k) || 0, lo, hi: lo + gw - w }); }
    return { bins: out, discrete: true, grouped: true };
  }
  return { bins: rows.map(r => ({ x0: r.x - w / 2, x1: r.x + w / 2, y: r.p, x: r.x })), discrete: true };
}
function histogram(el, opts) {
  return chartBase(el, Object.assign({ height: 200 }, opts), (el, W, o) => {
    let { bins, discrete, grouped } = toBins(o);
    if (o.xDomain) bins = bins.filter(b => b.x1 > o.xDomain[0] && b.x0 < o.xDomain[1]);
    if (!bins.length) { el.innerHTML = titleHtml(o) + '<div class="sh-note">No data.</div>'; return; }
    const tot = bins.reduce((a, b) => a + b.y, 0) || 1, cum = []; let c = 0; for (const b of bins) { c += b.y; cum.push(c / tot); }
    const yf = fmt.make(o.yFmt || (o.normalize === false ? 'int' : 'pct:1')), xf = fmt.make(o.xFmt || (discrete ? 'num:0' : null)) || null;
    const ymax = Math.max(...bins.map(b => b.y));
    const ty = ticks(...niceDomain(0, ymax, 4), 4); const yfmtT = o.yFmt ? fmt.make(o.yFmt) : (o.normalize === false ? autoTickFmt(ty.step, ymax) : v => fixed(v * 100, Math.max(0, -Math.floor(Math.log10(ty.step * 100) + 1e-9))) + '%');
    const ml = Math.max(28, ...ty.ticks.map(v => textW(yfmtT(v)))) + 10, mr = 12, mt = (o.yLabel ? 18 : 8) + mkBand(o.markers);
    const cumH = o.cumulative ? Math.round(o.height * 0.42) : 0, gap = o.cumulative ? 26 : 0;
    const mb = 22 + (o.xLabel ? 16 : 0);
    const H = mt + o.height + cumH + gap, plotB = mt + o.height - 0; // main plot bottom
    const xlo = o.xDomain ? o.xDomain[0] : bins[0].x0, xhi = o.xDomain ? o.xDomain[1] : bins[bins.length - 1].x1;
    const x = lin(xlo, xhi, ml, W - mr), y = lin(0, ty.ticks[ty.ticks.length - 1] || ymax, plotB, mt);
    const tx = ticks(xlo, xhi, Math.max(3, Math.floor((W - ml - mr) / 70)));
    const xfT = xf || autoTickFmt(tx.step, Math.max(Math.abs(xlo), Math.abs(xhi)));
    let s = `<svg width="${W}" height="${H + mb}" role="img" aria-label="${esc(o.title || 'Histogram')}">`;
    if (o.yLabel) s += `<text class="al" x="${ml}" y="10">${esc(o.yLabel)}</text>`;
    s += yAxis(y, ty, yfmtT, ml, W - mr);
    const mid = b => b.x ?? (b.lo != null ? (b.lo + b.hi) / 2 : (b.x0 + b.x1) / 2);
    const band = (x(bins[0].x1) - x(bins[0].x0));
    const bw = Math.max(1, Math.min(o.maxBar || (discrete ? 24 : 40), band - 2));
    bins.forEach((b, i) => {
      const cx = (x(b.x0) + x(b.x1)) / 2, top = y(b.y);
      const hot = o.split != null ? (mid(b) > o.split) === (o.splitSide !== 'under') : true;
      const d = vbar(cx - bw / 2, top, bw, plotB - top, Math.min(4, bw / 3));
      s += `<path class="bar ${hot ? 'f1' : 'fmut'}" data-i="${i}" d="${d}"/>`;
    });
    s += `<g class="ax"><line x1="${ml}" x2="${W - mr}" y1="${plotB}" y2="${plotB}"/></g>`;
    s += markersSvg(o.markers, x, mt, plotB);
    // invisible hit columns (bigger than the marks)
    bins.forEach((b, i) => { const x0 = x(b.x0), x1 = x(b.x1); s += `<rect class="hit" data-i="${i}" x="${x0}" y="${mt}" width="${Math.max(1, x1 - x0)}" height="${plotB - mt}"/>`; });
    let axisY = plotB;
    if (o.cumulative) {
      const top = plotB + gap, bot = top + cumH; const yc = lin(0, 1, bot, top + 4); const tc = { ticks: [0, 0.5, 1], step: 0.5, lo: 0, hi: 1 };
      const over = o.cumulative === 'over';
      s += `<text class="al" x="${ml}" y="${top - 6}">${over ? 'P(X ≥ x)' : 'P(X ≤ x)'}</text>`;
      s += yAxis(yc, tc, v => (v * 100).toFixed(0) + '%', ml, W - mr);
      let d = ''; bins.forEach((b, i) => { const v = over ? 1 - (i ? cum[i - 1] : 0) : cum[i]; const x0 = x(b.x0), x1 = x(b.x1); d += (i ? 'L' : 'M') + x0.toFixed(1) + ',' + yc(v).toFixed(1) + 'H' + x1.toFixed(1); });
      s += `<path class="ln k1" d="${d}"/>`;
      s += `<g class="ax"><line x1="${ml}" x2="${W - mr}" y1="${bot}" y2="${bot}"/></g>`;
      s += markersSvg((o.markers || []).map(m => Object.assign({}, m, { label: '' })), x, top, bot);
      bins.forEach((b, i) => { const x0 = x(b.x0), x1 = x(b.x1); s += `<rect class="hit" data-i="${i}" x="${x0}" y="${top}" width="${Math.max(1, x1 - x0)}" height="${cumH}"/>`; });
      axisY = bot;
    }
    s += xAxis(x, tx, xfT, axisY).replace(/<line x1="[\d.]+" x2="[\d.]+" y1="[\d.]+" y2="[\d.]+"\/>/, '');
    if (o.xLabel) s += `<text class="al" x="${W - mr}" y="${axisY + 32}" text-anchor="end">${esc(o.xLabel)}</text>`;
    s += '</svg>';
    el.innerHTML = titleHtml(o) + s;
    const svg = el.querySelector('svg');
    wireHover(svg, '[data-i]', t => {
      const i = +t.dataset.i, b = bins[i];
      svg.querySelectorAll('.bar.hot').forEach(n => n.classList.remove('hot')); const bar = svg.querySelector(`.bar[data-i="${i}"]`); if (bar) bar.classList.add('hot');
      const head = grouped ? `${o.xLabel || 'x'} ${xfT(b.lo)} to ${xfT(b.hi)}` : discrete ? `${o.xLabel || 'x'} = ${xfT(b.x ?? (b.x0 + b.x1) / 2)}` : `${xfT(b.x0)} to ${xfT(b.x1)}`;
      return tip.html(head, [{ value: yf(b.y), label: o.normalize === false ? 'count' : 'probability', key: 'b1' }, { value: fmt.pct(cum[i], 1), label: 'at or below' }, { value: fmt.pct(1 - (i ? cum[i - 1] : 0), 1), label: 'at or above' }]);
    });
    svg.addEventListener('pointerleave', () => svg.querySelectorAll('.bar.hot').forEach(n => n.classList.remove('hot')));
  });
}

/* ---- line chart ---- */
function line(el, opts) {
  return chartBase(el, Object.assign({ height: 220 }, opts), (el, W, o) => {
    const S = (o.series || []).map((s, i) => ({ name: s.name ?? 'Series ' + (i + 1), pts: (s.points || (s.values || []).map((v, k) => [o.x ? o.x[k] : k, v])).filter(p => isNum(p[0])), band: s.band, ci: s.color != null ? s.color : i }));
    const xs = [...new Set(S.flatMap(s => s.pts.map(p => p[0])))].sort((a, b) => a - b);
    if (!xs.length) { el.innerHTML = titleHtml(o) + '<div class="sh-note">No data.</div>'; return; }
    let ylo = Infinity, yhi = -Infinity;
    for (const s of S) { for (const p of s.pts) if (isNum(p[1])) { ylo = Math.min(ylo, p[1]); yhi = Math.max(yhi, p[1]); } if (s.band) for (const b of s.band) { ylo = Math.min(ylo, b[1]); yhi = Math.max(yhi, b[2]); } }
    for (const hl of o.hlines || []) { ylo = Math.min(ylo, hl.y); yhi = Math.max(yhi, hl.y); }
    if (o.yDomain) [ylo, yhi] = o.yDomain; else if (o.zero !== false && ylo > 0 && ylo < (yhi - ylo) * 0.6) ylo = 0;
    const ty = ticks(...niceDomain(ylo, yhi, 4), 4), yfT = tickFmtFor(o.yFmt, ty), yf = o.yFmt ? fmt.make(o.yFmt) : (v => fixed(v, Math.max(0, -Math.floor(Math.log10(ty.step) + 1e-9)) + 1));
    const ml = Math.max(28, ...ty.ticks.map(v => textW(yfT(v)))) + 10, mt = (o.yLabel ? 18 : 8) + mkBand(o.markers), mb = 22 + (o.xLabel ? 16 : 0);
    const endLab = S.length > 1 && S.length <= 4 && o.endLabels !== false;
    const mr = endLab ? Math.min(120, Math.max(...S.map(s => textW(s.name, 11))) + 14) : 12;
    const Hh = o.height, x = lin(o.xDomain ? o.xDomain[0] : xs[0], o.xDomain ? o.xDomain[1] : xs[xs.length - 1], ml, W - mr), y = lin(ty.ticks[0], ty.ticks[ty.ticks.length - 1], mt + Hh, mt);
    const tx = ticks(x.d[0], x.d[1], Math.max(3, Math.floor((W - ml - mr) / 80))), xfT = tickFmtFor(o.xFmt, tx), xf = o.xFmt ? fmt.make(o.xFmt) : xfT;
    let s = `<svg width="${W}" height="${mt + Hh + mb}" role="img" aria-label="${esc(o.title || 'Line chart')}">`;
    if (o.yLabel) s += `<text class="al" x="${ml}" y="10">${esc(o.yLabel)}</text>`;
    s += yAxis(y, ty, yfT, ml, W - mr) + xAxis(x, tx, xfT, mt + Hh);
    for (const hl of o.hlines || []) s += `<g class="mk"><line x1="${ml}" x2="${W - mr}" y1="${y(hl.y).toFixed(1)}" y2="${y(hl.y).toFixed(1)}"/>${hl.label ? `<text x="${ml + 4}" y="${y(hl.y) - 4}">${esc(hl.label)}</text>` : ''}</g>`;
    s += markersSvg(o.markers, x, mt, mt + Hh);
    S.forEach(se => {
      const k = se.ci % 8 + 1;
      if (se.band && se.band.length) { const up = se.band.map(b => `${x(b[0]).toFixed(1)},${y(b[2]).toFixed(1)}`), dn = se.band.slice().reverse().map(b => `${x(b[0]).toFixed(1)},${y(b[1]).toFixed(1)}`); s += `<path class="area f${k}" d="M${up.join('L')}L${dn.join('L')}Z"/>`; }
      if (o.area && S.length === 1) { const p = se.pts.filter(p => isNum(p[1])); s += `<path class="area f${k}" d="M${x(p[0][0])},${y(ty.ticks[0])}L${p.map(q => `${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`).join('L')}L${x(p[p.length - 1][0])},${y(ty.ticks[0])}Z"/>`; }
      let d = '', pen = false; for (const p of se.pts) { if (!isNum(p[1])) { pen = false; continue; } d += (pen ? 'L' : 'M') + x(p[0]).toFixed(1) + ',' + y(p[1]).toFixed(1); pen = true; }
      s += `<path class="ln k${k}" d="${d}"/>`;
    });
    if (endLab) {
      const ends = S.map((se, i) => { const p = [...se.pts].reverse().find(p => isNum(p[1])); return p ? { i, y: y(p[1]), x: x(p[0]), name: se.name } : null; }).filter(Boolean).sort((a, b) => a.y - b.y);
      const collide = ends.some((e, i) => i && e.y - ends[i - 1].y < 12);
      if (!collide) for (const e of ends) s += `<circle class="dot f${S[e.i].ci % 8 + 1}" cx="${e.x}" cy="${e.y}" r="4"/><text class="lab" x="${e.x + 8}" y="${e.y}" dy="0.32em">${esc(e.name)}</text>`;
    }
    if (o.xLabel) s += `<text class="al" x="${W - mr}" y="${mt + Hh + 32}" text-anchor="end">${esc(o.xLabel)}</text>`;
    s += `<line class="xh" y1="${mt}" y2="${mt + Hh}" x1="-10" x2="-10" visibility="hidden"/><g class="hd"></g><rect class="hit" x="${ml}" y="${mt}" width="${W - ml - mr}" height="${Hh}"/></svg>`;
    el.innerHTML = titleHtml(o) + (S.length > 1 ? legendHtml(S.map(s => s.name), 'l') : '') + s;
    const svg = el.querySelector('svg'), xh = svg.querySelector('.xh'), hd = svg.querySelector('.hd'), hit = svg.querySelector('.hit');
    const show = (cx, e) => {
      const xv = x.inv(cx); let i = lowerBound(Float64Array.from(xs), xv); if (i >= xs.length) i = xs.length - 1; if (i > 0 && Math.abs(xs[i - 1] - xv) < Math.abs(xs[i] - xv)) i--;
      const X = xs[i], px = x(X); xh.setAttribute('x1', px); xh.setAttribute('x2', px); xh.setAttribute('visibility', 'visible');
      const rows = []; let dots = '';
      S.forEach((se, k) => { const p = se.pts.find(p => p[0] === X); if (p && isNum(p[1])) { rows.push({ value: yf(p[1]), label: se.name, key: keyCls(se.ci) }); dots += `<circle class="dot f${se.ci % 8 + 1}" cx="${px}" cy="${y(p[1])}" r="4"/>`; } });
      hd.innerHTML = dots;
      tip.show(e.clientX, e.clientY, tip.html((o.xLabel ? o.xLabel + ' ' : '') + xf(X), rows));
    };
    hit.addEventListener('pointermove', e => { const r = svg.getBoundingClientRect(); show(e.clientX - r.left, e); });
    hit.addEventListener('pointerleave', () => { xh.setAttribute('visibility', 'hidden'); hd.innerHTML = ''; tip.hide(); });
  });
}

/* ---- horizontal bar / diverging bar ---- */
function bar(el, opts) {
  return chartBase(el, Object.assign({ barHeight: 14, rowGap: 8 }, opts), (el, W, o) => {
    let D = (o.data || []).filter(d => isNum(d.value)).map((d, i) => Object.assign({ i }, d));
    if (o.sort === 'desc' || o.sort === true) D.sort((a, b) => b.value - a.value); else if (o.sort === 'asc') D.sort((a, b) => a.value - b.value);
    if (o.limit) D = D.slice(0, o.limit);
    const f = fmt.make(o.fmt || 'num:1');
    const center = o.center != null ? o.center : 0;
    const div = o.diverging != null ? o.diverging : D.some(d => d.value < center) && D.some(d => d.value > center);
    let lo = Math.min(center, ...D.map(d => d.value)), hi = Math.max(center, ...D.map(d => d.value)); if (o.domain) [lo, hi] = o.domain;
    const labW = Math.min(W * 0.38, Math.max(...D.map(d => textW(d.label, 11.5))) + 10);
    const valW = Math.max(...D.map(d => textW(f(d.value), 11))) + 8;
    const band = o.barHeight + o.rowGap, mt = 4, Hh = D.length * band;
    const ml = labW + 6 + (D.some(d => d.value < center) ? valW : 0), mr = valW + 6;
    const x = lin(lo, hi, ml, W - mr), x0 = x(center);
    const tx = ticks(lo, hi, Math.max(2, Math.floor((W - ml - mr) / 80))), xfT = tickFmtFor(o.fmt, tx);
    let s = `<svg width="${W}" height="${mt + Hh + 22}" role="img" aria-label="${esc(o.title || 'Bar chart')}"><g class="gr">`;
    for (const t of tx.ticks) s += `<line x1="${x(t).toFixed(1)}" x2="${x(t).toFixed(1)}" y1="${mt}" y2="${mt + Hh}"/>`;
    s += '</g>';
    D.forEach((d, k) => {
      const y = mt + k * band + o.rowGap / 2, xv = x(d.value), cls = div ? (d.value >= center ? 'fpos' : 'fneg') : (o.highlight != null ? (d.label === o.highlight || d.id === o.highlight ? 'f1' : 'fmut') : 'f1');
      s += `<text class="lab${o.highlight != null && (d.label === o.highlight || d.id === o.highlight) ? '-s' : ''}" x="${labW}" y="${y + o.barHeight / 2}" dy="0.32em" text-anchor="end">${esc(d.label)}</text>`;
      s += `<path class="bar ${cls}" data-k="${k}" d="${hbar(x0, xv, y, o.barHeight)}"/>`;
      const neg = d.value < center; s += `<text class="lab" x="${neg ? xv - 5 : xv + 5}" y="${y + o.barHeight / 2}" dy="0.32em" text-anchor="${neg ? 'end' : 'start'}">${esc(f(d.value))}</text>`;
      s += `<rect class="hit" data-k="${k}" x="0" y="${y - o.rowGap / 2}" width="${W}" height="${band}"/>`;
    });
    s += `<g class="ax"><line x1="${x0}" x2="${x0}" y1="${mt}" y2="${mt + Hh}"/></g>`;
    s += xAxis(x, tx, xfT, mt + Hh).replace(/<line x1="[\d.]+" x2="[\d.]+" y1="[\d.]+" y2="[\d.]+"\/>/, '');
    s += '</svg>';
    el.innerHTML = titleHtml(o) + s;
    const svg = el.querySelector('svg');
    wireHover(svg, '[data-k]', t => { const d = D[+t.dataset.k]; svg.querySelectorAll('.bar.hot').forEach(n => n.classList.remove('hot')); const b = svg.querySelector(`.bar[data-k="${t.dataset.k}"]`); if (b) b.classList.add('hot'); return tip.html(d.label, [{ value: f(d.value), label: o.valueLabel || '', key: div ? (d.value >= center ? '' : '') : 'b1' }], d.desc); });
    svg.addEventListener('pointerleave', () => svg.querySelectorAll('.bar.hot').forEach(n => n.classList.remove('hot')));
    if (o.onClick) svg.addEventListener('click', e => { const t = e.target.closest('[data-k]'); if (t) o.onClick(D[+t.dataset.k]); });
  });
}

/* ---- scatter ---- */
function scatter(el, opts) {
  return chartBase(el, Object.assign({ height: 300 }, opts), (el, W, o) => {
    const Pts = (o.points || []).filter(p => isNum(p.x) && isNum(p.y));
    if (!Pts.length) { el.innerHTML = titleHtml(o) + '<div class="sh-note">No data.</div>'; return; }
    const groups = o.groups || [...new Set(Pts.map(p => p.group).filter(g => g != null))];
    const gi = g => Math.max(0, groups.indexOf(g));
    let [xlo, xhi] = o.xDomain || stats.extent(Pts.map(p => p.x)), [ylo, yhi] = o.yDomain || stats.extent(Pts.map(p => p.y));
    if (o.diag) { xlo = ylo = Math.min(xlo, ylo); xhi = yhi = Math.max(xhi, yhi); }
    const padx = (xhi - xlo) * 0.04 || 1, pady = (yhi - ylo) * 0.04 || 1;
    const ty = ticks(...(o.yDomain || [ylo - pady, yhi + pady]), 5), tx0 = [xlo - padx, xhi + padx];
    const yfT = tickFmtFor(o.yFmt, ty), yf = o.yFmt ? fmt.make(o.yFmt) : yfT;
    const ml = Math.max(28, ...ty.ticks.map(v => textW(yfT(v)))) + 10, mr = 14, mt = o.yLabel ? 18 : 8, mb = 22 + (o.xLabel ? 16 : 0), Hh = o.height;
    const x = lin(...(o.xDomain || tx0), ml, W - mr), y = lin(...(o.yDomain || [ylo - pady, yhi + pady]), mt + Hh, mt);
    const tx = ticks(x.d[0], x.d[1], Math.max(3, Math.floor((W - ml - mr) / 80))), xfT = tickFmtFor(o.xFmt, tx), xf = o.xFmt ? fmt.make(o.xFmt) : xfT;
    const tyT = { ticks: ty.ticks.filter(v => v >= y.d[0] && v <= y.d[1]), step: ty.step, lo: ty.lo, hi: ty.hi };
    let s = `<svg width="${W}" height="${mt + Hh + mb}" role="img" aria-label="${esc(o.title || 'Scatter plot')}">`;
    if (o.yLabel) s += `<text class="al" x="${ml}" y="10">${esc(o.yLabel)}</text>`;
    s += yAxis(y, tyT, yfT, ml, W - mr) + xAxis(x, { ticks: tx.ticks.filter(v => v >= x.d[0] && v <= x.d[1]), step: tx.step, lo: tx.lo, hi: tx.hi }, xfT, mt + Hh);
    if (o.diag) { const a = Math.max(x.d[0], y.d[0]), b = Math.min(x.d[1], y.d[1]); s += `<g class="mk"><line x1="${x(a)}" y1="${y(a)}" x2="${x(b)}" y2="${y(b)}"/></g>`; }
    if (o.refX != null) s += `<g class="mk"><line x1="${x(o.refX)}" x2="${x(o.refX)}" y1="${mt}" y2="${mt + Hh}"/></g>`;
    if (o.refY != null) s += `<g class="mk"><line x1="${ml}" x2="${W - mr}" y1="${y(o.refY)}" y2="${y(o.refY)}"/></g>`;
    const r = o.r || (Pts.length > 400 ? 3 : 4), op = Pts.length > 300 ? ' opacity=".75"' : '';
    const px = Pts.map(p => [x(p.x), y(p.y)]);
    let dots = ''; Pts.forEach((p, i) => { dots += `<circle class="dot f${gi(p.group) % 8 + 1}" cx="${px[i][0].toFixed(1)}" cy="${px[i][1].toFixed(1)}" r="${r}"${op}/>`; });
    s += `<g>${dots}</g>`;
    // selective labels: explicit list, or the N most extreme points
    let lab = [];
    if (Array.isArray(o.labels)) lab = Pts.map((p, i) => i).filter(i => o.labels.includes(Pts[i].id ?? Pts[i].label) || o.labels.includes(Pts[i].label));
    else { const N = o.labels === false ? 0 : (o.labels ?? 6); const mx = stats.mean(Pts.map(p => p.x)), my = stats.mean(Pts.map(p => p.y)), sx = stats.sd(Pts.map(p => p.x)) || 1, sy = stats.sd(Pts.map(p => p.y)) || 1; lab = Pts.map((p, i) => [i, ((p.x - mx) / sx) ** 2 + ((p.y - my) / sy) ** 2]).sort((a, b) => b[1] - a[1]).slice(0, N).map(a => a[0]); }
    const boxes = [];
    for (const i of lab) {
      const p = Pts[i]; if (!p.label) continue; const w = textW(p.label, 11); let [cx, cy] = px[i];
      const right = cx + 7 + w < W - mr; const bx = right ? cx + 7 : cx - 7 - w, box = [bx - 2, cy - 8, bx + w + 2, cy + 8];
      if (boxes.some(b => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) continue;
      boxes.push(box); s += `<text class="lab" x="${right ? cx + 7 : cx - 7}" y="${cy}" dy="0.32em" text-anchor="${right ? 'start' : 'end'}">${esc(p.label)}</text>`;
    }
    if (o.xLabel) s += `<text class="al" x="${W - mr}" y="${mt + Hh + 32}" text-anchor="end">${esc(o.xLabel)}</text>`;
    s += `<circle class="dot hot" r="${r + 1.5}" cx="-20" cy="-20" visibility="hidden"/><rect class="hit" x="${ml}" y="${mt}" width="${W - ml - mr}" height="${Hh}"/></svg>`;
    el.innerHTML = titleHtml(o) + (groups.length > 1 ? legendHtml(groups, 'd') : '') + s;
    const svg = el.querySelector('svg'), hot = svg.querySelector('circle.hot'), hit = svg.querySelector('.hit');
    let cur = -1;
    hit.addEventListener('pointermove', e => {
      const b = svg.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top; let bi = -1, bd = 900;
      for (let i = 0; i < px.length; i++) { const dx = px[i][0] - mx, dy = px[i][1] - my, d = dx * dx + dy * dy; if (d < bd) { bd = d; bi = i; } }
      if (bi < 0) { hot.setAttribute('visibility', 'hidden'); tip.hide(); cur = -1; return; }
      cur = bi; const p = Pts[bi];
      hot.setAttribute('cx', px[bi][0]); hot.setAttribute('cy', px[bi][1]); hot.setAttribute('class', `dot hot f${gi(p.group) % 8 + 1}`); hot.setAttribute('visibility', 'visible');
      tip.show(e.clientX, e.clientY, tip.html(p.label || '', [{ value: xf(p.x), label: o.xLabel || 'x' }, { value: yf(p.y), label: o.yLabel || 'y' }].concat(p.group != null ? [{ value: String(p.group), label: '', key: keyCls(gi(p.group)) }] : []), p.desc));
    });
    hit.addEventListener('pointerleave', () => { hot.setAttribute('visibility', 'hidden'); tip.hide(); cur = -1; });
    if (o.onClick) hit.addEventListener('click', () => { if (cur >= 0) o.onClick(Pts[cur]); });
  });
}

/* ---- sparkline (returns an SVG string; fast enough for grid cells) ---- */
function spark(values, o = {}) {
  const w = o.w || 72, hh = o.h || 16, n = values.length; if (!n) return '';
  let lo = Infinity, hi = -Infinity; for (const v of values) if (isNum(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (o.domain) [lo, hi] = o.domain; if (o.ref != null) { lo = Math.min(lo, o.ref); hi = Math.max(hi, o.ref); }
  if (!(hi > lo)) { hi = lo + 1; }
  const pad = 2, X = i => pad + (n === 1 ? (w - 2 * pad) / 2 : i * (w - 2 * pad) / (n - 1)), Y = v => hh - pad - (v - lo) / (hi - lo) * (hh - 2 * pad);
  let s = `<svg class="spk" width="${w}" height="${hh}" viewBox="0 0 ${w} ${hh}" aria-hidden="true">`;
  if (o.kind === 'bar') {
    const bw = Math.max(1, (w - 2 * pad) / n - 1), base = Y(o.ref != null ? o.ref : Math.max(lo, Math.min(0, hi)));
    values.forEach((v, i) => { if (!isNum(v)) return; const yy = Y(v), x0 = pad + i * (w - 2 * pad) / n; s += `<rect class="${v >= (o.ref ?? 0) ? 'bp' : 'bn'}" x="${x0.toFixed(1)}" y="${Math.min(yy, base).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.8, Math.abs(base - yy)).toFixed(1)}"/>`; });
  } else {
    if (o.ref != null) s += `<line class="ref" x1="0" x2="${w}" y1="${Y(o.ref).toFixed(1)}" y2="${Y(o.ref).toFixed(1)}"/>`;
    let d = '', pen = false; values.forEach((v, i) => { if (!isNum(v)) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(v).toFixed(1); pen = true; });
    s += `<path class="ln" d="${d}"/>`;
    const li = values.length - 1; if (o.end !== false && isNum(values[li])) s += `<circle class="end" cx="${X(li).toFixed(1)}" cy="${Y(values[li]).toFixed(1)}" r="2"/>`;
  }
  return s + '</svg>';
}

/* ---- matrix heatmap ---- */
function heatmap(el, opts) {
  return chartBase(el, Object.assign({ cellH: 24 }, opts), (el, W, o) => {
    const R = o.rows || [], C = o.cols || [], M = o.values || [];
    const f = fmt.make(o.fmt || 'num:2');
    const all = M.flat().filter(isNum);
    const isDiv = o.center != null;
    let lo, hi; if (o.domain) [lo, hi] = o.domain; else [lo, hi] = stats.extent(all);
    const dev = isDiv ? Math.max(Math.abs(lo - o.center), Math.abs(hi - o.center)) || 1 : 0;
    const labW = Math.min(W * 0.3, Math.max(...R.map(r => textW(r, 12.5))) + 14);
    const cw = clamp((W - labW - 4) / Math.max(1, C.length), 18, o.maxCell || 64);
    const rot = C.some(c => textW(c, 10.5) > cw - 4);
    const headH = rot ? Math.min(90, Math.max(...C.map(c => textW(c, 10.5))) * 0.75 + 12) : 18;
    const mt = headH + 2, ch = o.cellH;
    const Wt = labW + cw * C.length + 4;
    let s = `<svg width="${Wt}" height="${mt + ch * R.length + 2}" role="img" aria-label="${esc(o.title || 'Heatmap')}">`;
    C.forEach((c, j) => { const cx = labW + j * cw + cw / 2; s += rot ? `<text class="ax" transform="translate(${cx + 3},${mt - 6}) rotate(-50)" text-anchor="start">${esc(c)}</text>`.replace('class="ax"', 'class="ax" style="fill:var(--ink2)"') : `<text class="ax" style="fill:var(--ink2)" x="${cx}" y="${mt - 6}" text-anchor="middle">${esc(c)}</text>`; });
    R.forEach((r, i) => {
      const yy = mt + i * ch; s += `<text class="lab" x="${labW - 6}" y="${yy + ch / 2}" dy="0.32em" text-anchor="end">${esc(r)}</text>`;
      C.forEach((c, j) => {
        const v = (M[i] || [])[j], xx = labW + j * cw;
        if (!isNum(v)) { s += `<rect class="cell" x="${xx}" y="${yy}" width="${cw}" height="${ch}" style="fill:var(--sunk)" data-i="${i}" data-j="${j}"/>`; return; }
        let t, col;
        if (isDiv) { t = clamp((v - o.center) / dev, -1, 1) * (o.reverse ? -1 : 1); col = t >= 0 ? 'var(--heat-pos)' : 'var(--heat-neg)'; }
        else { t = clamp((v - lo) / ((hi - lo) || 1), 0, 1); col = 'var(--heat-seq)'; }
        s += `<rect class="cell" x="${xx}" y="${yy}" width="${cw}" height="${ch}" rx="2" style="fill:color-mix(in oklab,${col} ${Math.round(Math.abs(t) * 100)}%,var(--div-mid))" data-i="${i}" data-j="${j}"/>`;
        if (o.cellText !== false && cw >= textW(f(v), 11) + 6) s += `<text class="ctext" x="${xx + cw / 2}" y="${yy + ch / 2}" dy="0.32em" text-anchor="middle" style="fill:var(--ink)">${esc(f(v))}</text>`;
      });
    });
    s += '</svg>';
    const scale = isDiv
      ? `<div class="sc-scale"><span>${esc(f(o.center - dev))}</span><span class="bar" style="background:linear-gradient(90deg,var(--heat-neg),var(--div-mid),var(--heat-pos))"></span><span>${esc(f(o.center + dev))}</span>${o.scaleLabel ? `<span>${esc(o.scaleLabel)}</span>` : ''}</div>`
      : `<div class="sc-scale"><span>${esc(f(lo))}</span><span class="bar" style="background:linear-gradient(90deg,var(--div-mid),var(--heat-seq))"></span><span>${esc(f(hi))}</span>${o.scaleLabel ? `<span>${esc(o.scaleLabel)}</span>` : ''}</div>`;
    el.innerHTML = titleHtml(o) + `<div style="overflow-x:auto">${s}</div>` + scale;
    const svg = el.querySelector('svg');
    wireHover(svg, '.cell', t => { const i = +t.dataset.i, j = +t.dataset.j, v = (M[i] || [])[j]; return tip.html(`${R[i]} ${o.vs || 'vs'} ${C[j]}`, [{ value: isNum(v) ? f(v) : '–', label: o.valueLabel || '' }]); });
    if (o.onCell) svg.addEventListener('click', e => { const t = e.target.closest('.cell'); if (t) o.onCell(+t.dataset.i, +t.dataset.j, (M[+t.dataset.i] || [])[+t.dataset.j]); });
  });
}

/* ---- distribution ladder ---- */
/** ladder(el, {dist, lines:[...], odds:'american'|'decimal'|'both', label, prices:{line:{over, under}} (American), highlight:'median'|line}) */
function ladder(el, o) {
  el = resolveEl(el);
  const D = o.dist && o.dist.pOver ? o.dist : Array.isArray(o.dist) ? dist.fromSamples(o.dist) : dist.fromPmf(o.dist || o.pmf);
  const lines = o.lines || (() => { const a = D.quantile(0.1), b = D.quantile(0.9), st = niceStep(b - a, 8); const out = []; for (let v = Math.floor(a / st) * st; v <= b; v += st) out.push(+(v + (o.half === false ? 0 : st >= 1 ? 0.5 : 0)).toFixed(6)); return out; })();
  const oddsMode = o.odds || 'american';
  const fo = p => { if (!(p > 0 && p < 1)) return '–'; const a = fmt.american(p), d = fmt.dec(p, 2); return oddsMode === 'decimal' ? d : oddsMode === 'both' ? `${a} / ${d}` : a; };
  const anyPush = lines.some(x => D.pEq(x) > 0);
  const prices = o.prices || null;
  // compact: drop the P(under) column (it is 1 − P(over) − P(push)); automatic in narrow containers such as the drawer
  const compact = o.compact ?? ((el.clientWidth || 999) < 560);
  let best = -1, bd = 2; lines.forEach((x, i) => { const d = Math.abs(D.pOver(x) - 0.5); if (d < bd) { bd = d; best = i; } });
  const hl = o.highlight === undefined || o.highlight === 'median' ? best : lines.indexOf(o.highlight);
  let s = `<div class="sh-tbl-wrap"><table class="sh-tbl${compact ? ' compact' : ''}"><thead><tr><th>${esc(o.label || 'Line')}</th><th class="n">P(over)</th><th class="n">Fair ${compact ? 'O' : 'over'}</th>${compact ? '' : '<th class="n">P(under)</th>'}<th class="n">Fair ${compact ? 'U' : 'under'}</th>${anyPush ? `<th class="n">${compact ? 'Push' : 'P(push)'}</th>` : ''}${prices ? `<th class="n">${compact ? 'Price' : 'Price O/U'}</th><th class="n">EV ${compact ? 'O' : 'over'}</th><th class="n">EV ${compact ? 'U' : 'under'}</th>` : ''}</tr></thead><tbody>`;
  lines.forEach((x, i) => {
    const po = D.pOver(x), pu = D.pUnder(x), pe = D.pEq(x);
    // fair odds exclude the push: price on the conditional probability given no push
    const nf = 1 - pe, fo1 = nf > 0 ? po / nf : NaN, fu1 = nf > 0 ? pu / nf : NaN;
    s += `<tr${i === hl ? ' class="hl"' : ''}><td class="n" style="text-align:left">${esc(fixed(x, Number.isInteger(x) ? 0 : 1))}</td><td class="n">${fmt.pct(po, 1)}</td><td class="n">${esc(fo(fo1))}</td>${compact ? '' : `<td class="n">${fmt.pct(pu, 1)}</td>`}<td class="n">${esc(fo(fu1))}</td>${anyPush ? `<td class="n">${pe > 0 ? fmt.pct(pe, 1) : ''}</td>` : ''}`;
    if (prices) {
      const pr = prices[x] || prices[String(x)] || {};
      const evO = pr.over != null ? po * odds.americanToDecimal(pr.over) + pe - 1 : null, evU = pr.under != null ? pu * odds.americanToDecimal(pr.under) + pe - 1 : null;
      const cl = v => v == null ? '' : v > 0 ? ' good' : ' muted';
      s += `<td class="n">${pr.over != null ? esc(odds.fmtAmerican(pr.over)) + (compact ? '/' : ' / ') + esc(odds.fmtAmerican(pr.under)) : ''}</td><td class="n${cl(evO)}">${evO == null ? '' : fmt.spct(evO, 1)}</td><td class="n${cl(evU)}">${evU == null ? '' : fmt.spct(evU, 1)}</td>`;
    }
    s += '</tr>';
  });
  s += '</tbody></table></div>';
  el.innerHTML = titleHtml(o) + s + (o.note !== false ? `<div class="sh-note" style="margin-top:4px">Mean ${esc(fixed(D.mean, 1))} · median ${esc(fixed(D.quantile(0.5), 1))} · sd ${esc(fixed(D.sd, 1))}. Fair odds are no-vig${anyPush ? ', with pushes removed' : ''}.</div>` : '');
  return { el, dist: D, lines };
}

/* ════════════════════ controls ════════════════════ */
function field(label, ctl, cls) { const f = h('div', { class: 'ui-f' + (cls ? ' ' + cls : '') }, label ? h('span', { class: 'ui-l', text: label }) : null, ctl); return f; }
function defValue(el, get, set) { Object.defineProperty(el, 'value', { get, set, configurable: true }); return el; }
function fire(el, o, v) { if (o.onChange) o.onChange(v, el); el.dispatchEvent(new CustomEvent('change', { detail: v })); }
const normOpts = opts => opts.map(x => typeof x === 'object' ? { value: x.value, label: x.label ?? String(x.value) } : { value: x, label: String(x) });
const ui = {
  /** select({label, options:[v | {value,label}], value, onChange}) */
  select(o) {
    const opts = normOpts(o.options || []);
    const s = h('select', { class: 'ui-sel', 'aria-label': o.label || null });
    opts.forEach((x, i) => s.append(h('option', { value: i, text: x.label })));
    const idx = v => Math.max(0, opts.findIndex(x => x.value === v));
    s.value = String(idx(o.value ?? opts[0]?.value));
    const el = field(o.label, s);
    s.addEventListener('change', e => { e.stopPropagation(); fire(el, o, opts[+s.value].value); });
    el.input = s;
    return defValue(el, () => opts[+s.value]?.value, v => { s.value = String(idx(v)); });
  },
  /** segmented({label, options, value, onChange}) */
  segmented(o) {
    const opts = normOpts(o.options || []); let cur = o.value ?? opts[0]?.value;
    const g = h('div', { class: 'ui-seg', role: 'radiogroup', 'aria-label': o.label || null });
    const draw = () => g.querySelectorAll('button').forEach((b, i) => { const on = opts[i].value === cur; b.setAttribute('aria-checked', on); b.tabIndex = on ? 0 : -1; });
    opts.forEach((x, i) => g.append(h('button', { type: 'button', role: 'radio', text: x.label, onclick: () => { cur = x.value; draw(); fire(el, o, cur); } })));
    g.addEventListener('keydown', e => { if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return; e.preventDefault(); const i = clamp(opts.findIndex(x => x.value === cur) + (e.key === 'ArrowRight' ? 1 : -1), 0, opts.length - 1); cur = opts[i].value; draw(); g.children[i].focus(); fire(el, o, cur); });
    const el = field(o.label, g); draw();
    return defValue(el, () => cur, v => { cur = v; draw(); });
  },
  /** stepper({label, min, max, step, value, dp, onChange}) */
  stepper(o) {
    const step = o.step || 1, dp = o.dp ?? (String(step).split('.')[1] || '').length;
    const inp = h('input', { type: 'number', inputmode: 'decimal', min: o.min, max: o.max, step, value: o.value ?? o.min ?? 0, 'aria-label': o.label || null });
    const norm = v => { v = +v; if (!isFinite(v)) v = o.value ?? 0; if (o.min != null) v = Math.max(o.min, v); if (o.max != null) v = Math.min(o.max, v); return +v.toFixed(dp); };
    const set = v => { inp.value = norm(v).toFixed(dp); fire(el, o, +inp.value); };
    const minus = h('button', { type: 'button', 'aria-label': 'Decrease', text: MINUS, onclick: () => set(+inp.value - step) });
    const plus = h('button', { type: 'button', 'aria-label': 'Increase', text: '+', onclick: () => set(+inp.value + step) });
    inp.addEventListener('change', e => { e.stopPropagation(); set(inp.value); });
    inp.addEventListener('input', e => e.stopPropagation());
    inp.addEventListener('keydown', e => { if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); set(+inp.value + (e.key === 'ArrowUp' ? 1 : -1) * step * (e.shiftKey ? 10 : 1)); } });
    inp.value = norm(inp.value).toFixed(dp);
    const el = field(o.label, h('div', { class: 'ui-step' }, minus, inp, plus));
    return defValue(el, () => +inp.value, v => { inp.value = norm(v).toFixed(dp); });
  },
  /** slider({label, min, max, step, value, fmt, onChange, live}) — live:true fires on every input event */
  slider(o) {
    const f = fmt.make(o.fmt) || (v => String(v));
    const r = h('input', { type: 'range', min: o.min ?? 0, max: o.max ?? 1, step: o.step ?? 'any', value: o.value ?? o.min ?? 0, 'aria-label': o.label || null });
    const out = h('output', { text: f(+r.value) });
    r.addEventListener('input', e => { e.stopPropagation(); out.textContent = f(+r.value); if (o.live) fire(el, o, +r.value); });
    r.addEventListener('change', e => { e.stopPropagation(); if (!o.live) fire(el, o, +r.value); });
    const el = field(o.label, h('div', { class: 'ui-sl' }, r, out), 'ui-f-sl');
    el.style.minWidth = (o.width || 200) + 'px';
    return defValue(el, () => +r.value, v => { r.value = v; out.textContent = f(+r.value); });
  },
  /** dragList({label, items:[{id,label,sub,off}], onChange(ids)}) — drag with mouse/touch; keyboard: arrows move focus, Alt/Shift+arrows move the item */
  dragList(o) {
    let items = (o.items || []).map(x => typeof x === 'object' ? Object.assign({}, x) : { id: x, label: String(x) });
    const ul = h('ol', { class: 'ui-dl', 'aria-label': o.label || 'Reorder list' });
    const draw = (focusId) => {
      ul.innerHTML = '';
      items.forEach(it => ul.append(h('li', { tabindex: '0', 'data-id': it.id, class: it.off ? 'off' : null, 'aria-label': it.label }, h('span', { class: 'g', text: '⋮⋮' }), h('span', { text: it.label }), it.sub != null ? h('span', { class: 's', text: it.sub }) : null)));
      if (focusId != null) { const n = ul.querySelector(`li[data-id="${CSS.escape(String(focusId))}"]`); if (n) n.focus(); }
    };
    const changed = () => fire(el, o, items.map(i => i.id));
    ul.addEventListener('keydown', e => {
      const li = e.target.closest('li'); if (!li) return; const i = [...ul.children].indexOf(li);
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return; e.preventDefault();
      const j = clamp(i + (e.key === 'ArrowUp' ? -1 : 1), 0, items.length - 1);
      if (e.altKey || e.shiftKey) { if (j !== i) { const [m] = items.splice(i, 1); items.splice(j, 0, m); draw(m.id); changed(); } }
      else ul.children[j].focus();
    });
    let drag = null;
    ul.addEventListener('pointerdown', e => {
      const li = e.target.closest('li'); if (!li || e.button) return;
      e.preventDefault(); li.setPointerCapture(e.pointerId); li.focus({ preventScroll: true });
      const rows = [...ul.children], hgt = li.offsetHeight;
      drag = { li, start: e.clientY, from: rows.indexOf(li), to: rows.indexOf(li), hgt, rows };
      li.classList.add('drag');
    });
    ul.addEventListener('pointermove', e => {
      if (!drag) return; const dy = e.clientY - drag.start; drag.li.style.transform = `translateY(${dy}px)`;
      const to = clamp(drag.from + Math.round(dy / drag.hgt), 0, drag.rows.length - 1); drag.to = to;
      drag.rows.forEach((r, k) => { if (r === drag.li) return; let sh = 0; if (drag.from < to && k > drag.from && k <= to) sh = -drag.hgt; if (drag.from > to && k < drag.from && k >= to) sh = drag.hgt; r.style.transform = sh ? `translateY(${sh}px)` : ''; });
    });
    const end = () => { if (!drag) return; const { from, to, li } = drag; drag.rows.forEach(r => r.style.transform = ''); li.classList.remove('drag'); drag = null; if (from !== to) { const [m] = items.splice(from, 1); items.splice(to, 0, m); draw(m.id); changed(); } };
    ul.addEventListener('pointerup', end); ul.addEventListener('pointercancel', end);
    draw();
    const el = field(o.label, ul, 'ui-f-dl');
    el.setItems = its => { items = its.map(x => Object.assign({}, x)); draw(); };
    return defValue(el, () => items.map(i => i.id), ids => { const by = new Map(items.map(i => [i.id, i])); items = ids.map(id => by.get(id)).filter(Boolean).concat(items.filter(i => !ids.includes(i.id))); draw(); });
  },
  /** toggleList({label, items:[{id,label,sub,on}], onChange(onIds)}) */
  toggleList(o) {
    const items = (o.items || []).map(x => Object.assign({ on: true }, x));
    const box = h('div', { class: 'ui-tl', role: 'group', 'aria-label': o.label || null });
    items.forEach(it => { const cb = h('input', { type: 'checkbox', class: 'ui-tog', checked: it.on ? true : null }); cb.addEventListener('change', e => { e.stopPropagation(); it.on = cb.checked; fire(el, o, items.filter(i => i.on).map(i => i.id)); }); it.cb = cb; box.append(h('label', null, cb, h('span', { text: it.label }), it.sub != null ? h('span', { class: 's', text: it.sub }) : null)); });
    const el = field(o.label, box, 'ui-f-tl');
    return defValue(el, () => items.filter(i => i.on).map(i => i.id), ids => items.forEach(i => { i.on = ids.includes(i.id); i.cb.checked = i.on; }));
  },
  /** toggle({label, value, onChange}) — single switch */
  toggle(o) {
    const cb = h('input', { type: 'checkbox', class: 'ui-tog', checked: o.value ? true : null, 'aria-label': o.label || null });
    const el = h('label', { class: 'ui-f', style: { flexDirection: 'row', alignItems: 'center', gap: '8px', fontSize: '12.5px', cursor: 'pointer', height: '28px' } }, cb, h('span', { text: o.label || '' }));
    cb.addEventListener('change', e => { e.stopPropagation(); fire(el, o, cb.checked); });
    return defValue(el, () => cb.checked, v => { cb.checked = !!v; });
  },
  button(o) { return h('button', { type: 'button', class: 'ui-btn' + (o.primary ? ' pri' : ''), text: o.label, onclick: o.onClick }); },
  /** progress() -> element with .set(fraction) */
  progress() { const i = h('i'); const el = h('div', { class: 'ui-prog', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100 }, i); el.set = f => { const p = clamp(f, 0, 1) * 100; i.style.width = p + '%'; el.setAttribute('aria-valuenow', Math.round(p)); }; return el; },
  /** row(...controls) — a wrapping control bar */
  row(...kids) { return h('div', { class: 'ui-ctl' }, kids); },
};

/* ════════════════════ simulation worker ════════════════════ */
/** simulate({module, params, workers, seed, onProgress(frac, partial, shard), transfer}) -> job {promise, then, cancel, elapsed}
    The module is an ES module exporting run(params, ctx) (sync or async) and, if workers>1, merge(a, b). */
function simulate(o) {
  const modUrl = new URL(o.module, document.baseURI).href;
  const n = Math.max(1, o.workers || 1), seed = o.seed ?? ((Math.random() * 2 ** 31) | 0);
  const workers = [], fracs = new Array(n).fill(0), t0 = performance.now();
  let cancelled = false, rejectFn;
  const job = { cancelled: false, elapsed: 0, seed };
  const report = (k, frac, partial) => { fracs[k] = frac; if (o.onProgress) o.onProgress(fracs.reduce((a, b) => a + b, 0) / n, partial, k); };
  const runMain = async () => {
    const mod = await import(modUrl); const fn = mod.run || mod.default; const outs = [];
    for (let k = 0; k < n; k++) outs.push(await fn(o.params, { shard: k, shards: n, seed: seed + k, rng: rng(seed + k * 0x9E3779B1), progress: (f, p) => report(k, f, p) }));
    return n > 1 ? outs.reduce(mod.merge) : outs[0];
  };
  job.promise = new Promise((resolve, reject) => {
    rejectFn = reject;
    let wk;
    try { wk = Array.from({ length: n }, () => new Worker(ASSET_BASE + 'sim-worker.js', { type: 'module' })); }
    catch (e) { runMain().then(resolve, reject); return; }
    const results = new Array(n); let done = 0;
    wk.forEach((w, k) => {
      workers.push(w);
      w.onmessage = async e => {
        const m = e.data;
        if (m.type === 'progress') report(k, m.frac, m.partial);
        else if (m.type === 'done') {
          results[k] = m.result; report(k, 1, null); w.terminate();
          if (++done === n) {
            try { let r = results[0]; if (n > 1) { const mod = await import(modUrl); if (!mod.merge) throw new Error('sim module must export merge(a, b) when workers > 1'); r = results.reduce(mod.merge); } job.elapsed = performance.now() - t0; resolve(r); }
            catch (err) { reject(err); }
          }
        } else if (m.type === 'error') { wk.forEach(x => x.terminate()); reject(new Error('Simulation failed: ' + m.message)); }
      };
      w.onerror = e => { e.preventDefault(); wk.forEach(x => x.terminate()); reject(new Error('Simulation worker error: ' + (e.message || 'could not load ' + o.module))); };
      w.postMessage({ module: modUrl, params: o.params, shard: k, shards: n, seed: seed + k });
    });
  });
  job.then = (a, b) => job.promise.then(a, b);
  job.catch = b => job.promise.catch(b);
  job.cancel = () => { if (cancelled) return; cancelled = job.cancelled = true; workers.forEach(w => w.terminate()); const e = new Error('cancelled'); e.cancelled = true; rejectFn && rejectFn(e); };
  return job;
}

/* ════════════════════ workbook shell ════════════════════ */
function fmtStampDate(s) {
  if (!s) return '';
  const m = String(s).match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/); if (!m) return String(s);
  return m[2] && /[zZ]|[+-]00:?00$/.test(String(s)) ? `${m[1]} ${m[2]} UTC` : m[2] ? `${m[1]} ${m[2]}` : m[1];
}
/** Readable build stamp from a meta.json object (schema-tolerant). */
function stampFromMeta(m) {
  if (!m) return '';
  const cut = m.data_through || m.data_cutoff || m.cutoff || m.through || m.as_of;
  const built = m.built_utc || m.generated_utc || m.build_utc || m.built_at || m.generated_at || m.built || m.generated || m.build_date || m.built_date;
  const ver = m.version || m.model_version || (m.commit || m.git_sha || m.sha ? String(m.commit || m.git_sha || m.sha).slice(0, 7) : null);
  return [cut && 'Data to ' + fmtStampDate(cut), built && 'Built ' + fmtStampDate(built), ver && (String(ver).match(/^\d/) ? 'v' + ver : ver)].filter(Boolean).join(' · ');
}
function parseHash() {
  const s = location.hash.replace(/^#/, ''), out = {};
  if (!s) return out;
  for (const part of s.split('&')) { if (!part) continue; const i = part.indexOf('='); out[decState(i < 0 ? part : part.slice(0, i))] = i < 0 ? '' : decState(part.slice(i + 1)); }
  return out;
}
/** workbook({title, subtitle, hub, hubLabel, meta, stamp, sheets:[{id, name, render(panel, sheet), fill}], defaultSheet, actions, onSheet}) */
function workbook(o) {
  document.body.classList.add('sh-app');
  const mount = resolveEl(o.el) || document.body;
  const stamp = h('span', { class: 'sh-stamp', title: 'Data cut-off and build' });
  const bar = h('header', { class: 'sh-bar' },
    o.hub !== false ? h('a', { class: 'sh-hub', href: o.hub || '../', text: '← ' + (o.hubLabel || 'Models') }) : null,
    o.hub !== false ? h('span', { class: 'sh-sep' }) : null,
    h('h1', { class: 'sh-title', text: o.title || document.title }),
    o.subtitle ? h('span', { class: 'sh-sub', text: o.subtitle }) : null,
    stamp, o.actions || null, theme.button());
  const main = h('main', { class: 'sh-main' });
  const tabs = h('nav', { class: 'sh-tabs', role: 'tablist', 'aria-label': 'Sheets' });
  const root = h('div', { class: 'sh-wb' }, bar, main, tabs);
  mount.append(root);
  if (o.title && !document.title) document.title = o.title;

  const wb = { el: root, sheets: [], active: null };
  const byId = {};
  function writeHash(push) {
    const a = wb.active; if (!a) return;
    const parts = ['sheet=' + encState(a.id)];
    for (const k in a.params) { const v = a.params[k]; if (v != null && v !== '') parts.push(encState(k) + '=' + encState(v)); }
    const str = '#' + parts.join('&');
    if (location.hash !== str) history[push ? 'pushState' : 'replaceState'](null, '', str);
  }
  (o.sheets || []).forEach(def => {
    const tab = h('button', { class: 'sh-tab', role: 'tab', type: 'button', id: 'tab-' + def.id, 'aria-controls': 'sheet-' + def.id, 'aria-selected': 'false', tabindex: '-1', text: def.name || def.id });
    const panel = h('section', { class: 'sh-panel' + (def.fill ? ' sh-fill' : ''), id: 'sheet-' + def.id, role: 'tabpanel', 'aria-labelledby': 'tab-' + def.id, hidden: true });
    const listeners = [];
    const sh = {
      id: def.id, name: def.name || def.id, def, panel, tab, params: {}, rendered: false, wb,
      get: k => sh.params[k],
      /** Merge params into this sheet's URL state (null/'' deletes). */
      set(obj) { for (const k in obj) { const v = obj[k]; if (v == null || v === '') delete sh.params[k]; else sh.params[k] = String(v); } if (wb.active === sh) writeHash(false); },
      onState(fn) { listeners.push(fn); },
      _notify() { listeners.forEach(f => f(sh.params)); },
      grid: (el, opts) => grid(el, Object.assign({ state: sh, name: sh.id }, opts)),
    };
    tab.addEventListener('click', () => wb.activate(sh.id, { push: true }));
    tabs.append(tab); main.append(panel);
    wb.sheets.push(sh); byId[sh.id] = sh;
  });
  tabs.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = wb.sheets.indexOf(wb.active), j = clamp(i + (e.key === 'ArrowRight' ? 1 : -1), 0, wb.sheets.length - 1);
    wb.activate(wb.sheets[j].id, { push: true }); wb.sheets[j].tab.focus();
  });
  async function renderSheet(sh) {
    sh.rendered = true; sh.panel.innerHTML = '';
    const ld = loadingEl(); sh.panel.append(ld);
    try { const r = sh.def.render && sh.def.render(sh.panel, sh); if (r && r.then) await r; }
    catch (e) { console.error(e); sh.panel.innerHTML = ''; sh.panel.append(errorEl(e)); }
    finally { ld._dispose(); ld.remove(); }
  }
  /** activate(id, {push, params}) */
  wb.activate = (id, opt = {}) => {
    const sh = byId[id] || wb.sheets[0]; if (!sh) return;
    const prev = wb.active;
    if (opt.params) sh.params = Object.assign({}, opt.params);
    wb.active = sh;
    wb.sheets.forEach(s => { const on = s === sh; s.tab.setAttribute('aria-selected', on); s.tab.tabIndex = on ? 0 : -1; s.panel.hidden = !on; });
    sh.tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (!sh.rendered) renderSheet(sh); else if (opt.params) sh._notify();
    writeHash(opt.push && prev !== sh);
    if (prev !== sh) { closePop(); if (o.onSheet) o.onSheet(sh.id, sh); }
  };
  wb.sheet = id => byId[id];
  wb.setStamp = t => { stamp.textContent = t || ''; stamp.title = t || ''; };
  const fromHash = () => { const p = parseHash(); const id = p.sheet; delete p.sheet; const target = byId[id] ? id : (wb.active ? wb.active.id : (o.defaultSheet || wb.sheets[0]?.id)); wb.activate(target, { params: p }); };
  addEventListener('popstate', fromHash);
  addEventListener('hashchange', fromHash);
  // stamp
  if (o.stamp) wb.setStamp(o.stamp);
  else if (o.meta && typeof o.meta === 'object') wb.setStamp(stampFromMeta(o.meta));
  else if (o.meta) { stamp.textContent = '…'; load.optional(o.meta).then(m => { wb.meta = m; wb.setStamp(m ? stampFromMeta(m) : 'No build yet'); if (o.onMeta) o.onMeta(m); }); }
  fromHash();
  return wb;
}

/* ════════════════════ export ════════════════════ */
global.Sheets = {
  version: '1.0.0', assetBase: ASSET_BASE,
  workbook, grid, Grid, drawer, kv, tiles, table,
  chart: { histogram, line, bar, scatter, heatmap, spark, ladder },
  histogram, line, bar, scatter, heatmap, spark, ladder,
  ui, simulate, rng, load, LoadError, into, loadingEl, errorEl,
  md, markdown, loadMarkdown,
  fmt, odds, dist, stats, theme, tip, stampFromMeta,
  h, esc, debounce,
};
})(window);
