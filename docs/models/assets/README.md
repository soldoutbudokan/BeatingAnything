# Sheets: workbook framework for the model pages

`sheet.css` + `sheet.js` turn a static page into a spreadsheet-style workbook: named sheets with tabs along the bottom, a fast virtualised grid, inline-SVG charts, simulator controls, a markdown renderer, a cached data loader and a Web Worker runner. There are no dependencies and no build step. Everything is ES2020 and every URL is relative, so pages work under `https://<user>.github.io/<repo>/models/...` and under `python -m http.server` from `docs/`.

`demo.html` in this folder is the reference example. It uses every component on synthetic data. Open it at `http://localhost:8000/models/assets/demo.html` after `cd docs && python -m http.server`. Copy from it.

```
docs/models/
  index.html            hub (reads ipl/data/meta.json, wnba/data/meta.json)
  assets/sheet.css      all styles + theme tokens
  assets/sheet.js       window.Sheets
  assets/sim-worker.js  generic module worker used by Sheets.simulate (do not edit per sport)
  assets/demo.html      reference workbook
  ipl/index.html        ← sport page (you write this)
  ipl/sim.js            ← sport simulator module (optional)
  ipl/data/*.json       ← model exports
```

## Contents

1. [Page skeleton](#1-page-skeleton)
2. [Workbook](#2-workbook)
3. [Grid](#3-grid)
4. [Formats and odds](#4-formats-and-odds)
5. [Drawer, tiles, kv, table](#5-drawer-tiles-kv-table)
6. [Charts](#6-charts)
7. [Distributions and the ladder](#7-distributions-and-the-ladder)
8. [Controls](#8-controls)
9. [Markdown](#9-markdown)
10. [Data loader](#10-data-loader)
11. [Simulation worker](#11-simulation-worker)
12. [Theme, tooltip, helpers](#12-theme-tooltip-helpers)
13. [Design rules](#13-design-rules)

---

## 1. Page skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPL projections</title>
<link rel="stylesheet" href="../assets/sheet.css">
<script src="../assets/sheet.js"></script>   <!-- in <head>: applies the saved theme before first paint -->
</head>
<body>
<script>
const S = Sheets;
S.workbook({
  title: 'IPL projections',
  subtitle: 'Bottom-up ratings + ball-by-ball simulator',
  meta: 'data/meta.json',                 // build stamp in the header; missing file shows "No build yet"
  sheets: [
    { id: 'batters', name: 'Batters', fill: true, async render(panel, sheet) {
        const rows = await S.load('data/batters.json');
        sheet.grid(panel, { columns: BATTER_COLS, rows, sort: '-value', onRowClick: openBatter });
    } },
    { id: 'method', name: 'Method', render: panel => S.loadMarkdown(panel.appendChild(S.h('div')), 'data/method.md') },
  ],
});
</script>
</body>
</html>
```

The body is replaced by a full-height app: a header bar, the active sheet, and tabs along the bottom. Nothing scrolls the page itself. Each sheet panel scrolls vertically, and the grid scrolls inside itself.

## 2. Workbook

```js
const wb = Sheets.workbook({
  title, subtitle,          // header text
  hub: '../',               // link back to the hub (false to hide); hubLabel: 'Models'
  meta: 'data/meta.json',   // URL or object -> stamp via Sheets.stampFromMeta(); onMeta(meta) callback
  stamp: 'Data to …',       // explicit stamp text (overrides meta)
  actions: element,         // optional extra element(s) in the header, left of the theme toggle
  defaultSheet: 'batters',
  onSheet(id, sheet) {},    // called when the active sheet changes
  sheets: [{ id, name, fill, render(panel, sheet) }],
});
wb.activate('teams');  wb.sheet('teams');  wb.setStamp('…');  wb.meta /* loaded meta.json */
```

- **render(panel, sheet)** runs the first time a sheet is opened. It may be `async`. A loading state shows until it resolves, and if it throws or rejects, the panel shows a readable error instead.
- **fill: true** turns off the panel's own scrolling so a grid created with `height: 'fill'` (the default) takes all remaining height. Leave it off for sheets with charts, where the panel scrolls.
- Panels are flex columns with a 14px gap. You can append anything to them.

**URL state.** The hash holds the active sheet and that sheet's state, so links are shareable:

```
#sheet=batters&sort=-value,name&q=kohli&f.team==MI|CSK&f.sr=130..&f.name=~sharma&hide=Bowling
```

`sheet` is the object passed to `render`:

| member | |
|---|---|
| `sheet.get(key)` / `sheet.set({key: value})` | Read or write this sheet's URL state (`null` or `''` deletes a key). Use it for simulator settings and similar. |
| `sheet.params` | The current state object. |
| `sheet.onState(fn)` | Called with `params` when the hash changes (back/forward, or a pasted link). |
| `sheet.grid(el, opts)` | `Sheets.grid` bound to this sheet's URL state. The grid reads its state from the hash on creation and writes changes back. |
| `sheet.panel`, `sheet.id`, `sheet.wb` | |

Each sheet remembers its own state while you switch tabs. With two grids on one sheet, give each one a `stateKey` (for example `'b'`) so their keys don't collide (`b.sort=…`).

`Sheets.stampFromMeta(meta)` is schema-tolerant. It looks for `data_through | data_cutoff | cutoff | through | as_of`, then `built_utc | generated_utc | build_utc | built_at | generated_at | built | generated`, then `version | model_version | commit | git_sha | sha`. The result looks like `Data to 2026-11-01 · Built 2026-11-10 14:02 UTC · v1.2`.

## 3. Grid

```js
const grid = sheet.grid(panel, {          // or Sheets.grid(el, opts) without URL binding
  columns: [...],                          // see below
  rows: [...],                             // array of plain objects
  groups: [{ id: 'Batting', label: 'Batting', hidden: false }],   // optional; derived from column.group if omitted
  sort: '-value,name',                     // default sort when the URL has none ('-' = descending)
  onRowClick(row, index, event) {},        // click or Enter; also re-fired when arrows move rows while the drawer is open
  height: 'fill',                          // 'fill' (flex to panel), a number of px, or 'auto'
  rowHeight: 24,
  frozen: 2,                               // number of leading frozen columns (default: leading columns with frozen:true)
  search: true, searchPlaceholder: 'Search',
  chips: true,                             // column-group show/hide chips
  csv: true,                               // or a filename, e.g. 'batters.csv'
  footer: true, footerLabel: 'Mean',
  rowClass: (row, i) => row.injured ? 'dim' : '',
  stateKey: '',                            // prefix for URL keys when several grids share a sheet
  tools: element,                          // extra element in the toolbar
  onChange(grid) {},                       // after any sort/filter/search/visibility change
  emptyText: 'No data.',
  virtualColumns: true,                    // render only the visible columns (keep on for wide grids)
});
```

**Column definition**

```js
{
  key: 'sr',                    // property name (and URL key); required unless get is given
  label: 'SR',                  // header text
  group: 'Batting',             // two-level header + show/hide chip
  desc: 'Runs per 100 balls.',  // header tooltip and filter-popover text: put the definition here
  get: row => row.bat.sr,       // value accessor (default row[key]); return null for missing
  fmt: 'num:1',                 // formatter spec or function (section 4); implies a numeric column
  type: 'num' | 'text' | 'cat' | 'spark',   // inferred if omitted (numbers -> num, few distinct strings -> cat)
  width: 64,                    // px; estimated from header and data if omitted
  frozen: true,                 // leading frozen columns
  hidden: true,                 // not shown and not exported (CSV is the visible view)

  // conditional formatting (numeric columns). Works in both themes.
  heat: { center: 0 },                       // diverging around center; domain auto (96th pct of |v-center|)
  heat: { center: 8.0, reverse: true },      // lower is better (economy, turnovers)
  heat: { center: 0, domain: [-2, 2] },      // fixed domain
  heat: { type: 'seq' },                     // sequential, domain = 2nd to 98th percentile
  heat: { type: 'seq', domain: [100, 180] },
  bar: true,                                 // in-cell data bar from 0 (negative values extend left, in red)
  bar: { domain: [0, 90], base: 0 },
  pctile: true,                              // shade by percentile rank in the full data ({reverse:true} flips)

  spark: { w: 64, h: 16, kind: 'line' | 'bar', ref: 0 },   // value is an array -> sparkline cell

  render: (v, row) => '<a href="…">…</a>',   // custom cell HTML (trusted; escape with Sheets.esc)
  cls: (v, row) => v > 0.05 ? 'good' : '',   // extra cell class (good, bad, warn, muted, dim)
  filter: 'range' | 'set' | 'text' | false,  // default: num -> range, cat -> set, text -> contains
  agg: 'mean' | 'sum' | 'count' | null | (rows => value),   // footer; num columns default to mean
  aggFmt: 'num:1',
  search: true,                 // include in the global search (default for text/cat)
  firstDir: -1,                 // first click sorts descending (default for numbers)
  csv: (v, row) => …,           // CSV value (default: the raw value at full precision)
  csvLabel: 'Strike rate',
  copyText: (v, row) => …,      // what Ctrl/Cmd+C copies (default: the formatted value)
}
```

**Interaction.** Click a header to sort (numbers sort high to low first; a third click clears the sort). Shift-click adds a secondary sort, and the header shows its priority. The funnel icon on a header opens the filter: min/max for numbers (percent formats are typed in percent), a checklist with counts for categories, "contains" for text. Active filters appear as removable chips in the toolbar. The search box matches every word against the text and category columns. Group chips show and hide column groups. **Download CSV** exports the filtered, sorted, visible view with raw values. The footer shows the mean of the filtered rows (Σ marks a sum).

**Keyboard** (with the grid focused): arrow keys move between cells, PageUp/PageDown move a page, Home/End go to the first/last column, Ctrl+Home/End to the first/last row, Enter opens the row, Escape closes the drawer or clears the selection, and Ctrl/Cmd+C copies the selected cell.

**Methods**

```js
grid.setRows(rows)                 // new data, same columns/sort/filters
grid.setColumns(columns, groups)
grid.getView()                     // filtered + sorted row objects
grid.setSort('-value,name')        // or [{key, dir: -1}]
grid.setFilter('team', ['MI', 'CSK'])        // set filter
grid.setFilter('sr', { min: 130, max: null }) // range (raw units)
grid.setFilter('name', 'sharma')              // contains
grid.setFilter('team', null)                  // clear one
grid.clearFilters(); grid.setSearch('kohli'); grid.setGroupVisible('Bowling', false);
grid.select(rowIndex, 'sr'); grid.selected(); grid.step(+1)   // step: move selection and fire onRowClick
grid.toCSV(); grid.downloadCSV('name.csv'); grid.getState(); grid.setState(params)
grid.on('change', fn); grid.focus(); grid.el; grid.viewport
```

**Performance.** Rows and columns are both virtualised: only the visible window plus a small overscan is in the DOM (about 40 rows × 25 columns), and scrolling patches rows in and out instead of re-rendering. Sorting and filtering 3,000 rows × 60 columns runs on cached typed arrays.

## 4. Formats and odds

Format specs work everywhere a `fmt` is accepted (grid columns, chart axes, ladder, `Sheets.table`):

| spec | input | output |
|---|---|---|
| `num:2` | 1234.5 | `1,234.50` (true minus sign for negatives) |
| `int` | 41.6 | `42` |
| `pct:1` | 0.1234 | `12.3%` |
| `signed:2` | 0.5 | `+0.50` |
| `spct:1` | -0.012 | `−1.2%` |
| `american` | probability 0.4 | `+150` (fair price) |
| `odds` | American price -150 | `−150` |
| `dec:2` | probability 0.4 | `2.50` (fair decimal price) |
| `compact` | 12500 | `12.5K` |
| `text` | anything | `String(v)` |
| function | `v => …` | your string |

```js
Sheets.fmt.num(3.14159, 2)    Sheets.fmt.pct(0.42, 0)   Sheets.fmt.make('signed:1')(x)
Sheets.odds.american(0.4)        // 150
Sheets.odds.decimal(0.4)         // 2.5
Sheets.odds.fromAmerican(-150)   // 0.6
Sheets.odds.fromDecimal(2.5)     // 0.4
Sheets.odds.americanToDecimal(-110)   // 1.909
Sheets.odds.decimalToAmerican(2.5)    // 150
Sheets.odds.fmtAmerican(150)     // '+150'
Sheets.odds.devig([-110, -110], { american: true })   // [0.5, 0.5]
Sheets.odds.ev(0.55, -110, { american: true })        // 0.05 (EV per unit staked)
```

## 5. Drawer, tiles, kv, table

```js
function openBatter(row) {
  Sheets.drawer.open({
    title: row.name, sub: `${row.team} · ${row.role}`,
    nav: { prev: () => grid.step(-1), next: () => grid.step(1) },   // up/down buttons
    keepScroll: true,                    // keep the scroll position when flipping between rows
    body: el => {                        // Node, HTML string, or function(el)
      el.append(Sheets.tiles([
        { label: 'Value', value: Sheets.fmt.signed(row.value, 2), sub: '± ' + Sheets.fmt.num(row.sd, 2) },
        { label: 'P(50+)', value: Sheets.fmt.pct(row.p50, 1), sub: 'fair ' + Sheets.fmt.american(row.p50) },
      ]));
      el.append(Sheets.kv([['Matches', row.m], ['Strike rate', Sheets.fmt.num(row.sr, 1)]], { cols: 2 }));
      Sheets.histogram(el.appendChild(Sheets.h('div')), { title: 'Runs', dist: Sheets.dist.fromPmf(row.runs_pmf) });
    },
  });
}
Sheets.drawer.close(); Sheets.drawer.isOpen; Sheets.drawer.body
```

The drawer is a non-modal right-hand panel (full width on a phone). While it is open, arrow keys in the grid move rows and the drawer follows. Escape closes it.

`Sheets.table(el, columns, rows, { highlight: (row, i) => bool })` renders a small static table (no virtualisation). Columns are `{key, label, fmt, get, render, desc}`.

## 6. Charts

All charts render inline SVG into `el`, resize with their container, take colours from CSS tokens (so they follow the theme without re-rendering), and show tooltips on hover. Each returns `{ el, update(opts) }`, and `update` merges new options and re-renders. Common options: `title`, `subtitle`, `height` (plot height in px), `xLabel`, `yLabel`, `xFmt`, `yFmt`, `width` (fixed instead of responsive).

**Histogram / probability mass**

```js
Sheets.histogram(el, {
  dist: Sheets.dist.fromSamples(totals),      // or pmf: {150: 0.01, …} | [[x, p]] | [{x, p}]
                                              // or values: [...] (raw samples) | bins: [{x0, x1, y}]
  markers: [{ x: 170.5, label: 'Line 170.5', strong: true }, { x: mean, label: 'Mean' }],
  cumulative: 'over',                         // adds a P(X ≥ x) panel below ('under' or true gives P(X ≤ x))
  split: 170.5,                               // emphasise bars above the line, grey the rest (splitSide: 'under')
  xDomain: [60, 260], maxBars: 60,            // discrete pmfs with more values are grouped into wider bins
  groupWidth: 5, binWidth, binCount, normalize: true,
  xLabel: 'runs', height: 180,
});
```

**Line (multi-series)**

```js
Sheets.line(el, {
  series: [
    { name: 'MI', points: [[1, 8.2], [2, 16.9], …], band: [[1, 6.1, 10.3], …] },   // band = [x, lo, hi]
    { name: 'CSK', values: [...] },                                                // with x: [...] or index
  ],
  x: [...], xLabel: 'over', yFmt: 'num:0',
  markers: [{ x: 6, label: 'end of powerplay' }], hlines: [{ y: 0, label: '' }],
  area: false, zero: true, endLabels: true, yDomain, xDomain,
});
```

The crosshair snaps to the nearest x and the tooltip lists every series. Two or more series get a legend. With four or fewer, the lines are also labelled at their ends unless the labels would collide.

**Horizontal bar / diverging bar**

```js
Sheets.bar(el, { data: [{ label: 'MI', value: 1.27, desc: 'tooltip text' }, …], sort: 'desc', fmt: 'signed:2' });
Sheets.bar(el, { data, center: 0 });             // diverging: blue above center, red below (auto when values straddle it)
Sheets.bar(el, { data, diverging: false, highlight: 'MI', limit: 15, onClick: d => … });
```

**Scatter**

```js
Sheets.scatter(el, {
  points: [{ x, y, label, group, id, desc }],
  groups: ['Batter', 'Bowler', 'All-rounder'],   // fixed colour order; keep to 3 or fewer
  labels: 6,                                     // label the N most extreme points, or an array of ids/labels, or false
  xLabel, yLabel, xFmt, yFmt, refX: 0, refY: 0, diag: false,
  onClick: point => …,
});
```

Hover snaps to the nearest point within 30px.

**Sparkline** (returns an SVG string, fast enough for every grid cell)

```js
Sheets.spark([1, 3, 2, 5], { w: 72, h: 16, kind: 'line' | 'bar', ref: 0, domain: [lo, hi], end: true })
```

**Matrix heatmap** (team vs team)

```js
Sheets.heatmap(el, {
  rows: teams, cols: teamAbbrevs, values: matrix,   // matrix[i][j]; null shows as a blank cell
  center: 0.5, domain: [0.2, 0.8], fmt: 'pct:0',    // omit center for a sequential scale
  valueLabel: 'win probability', vs: 'vs', reverse: false, cellText: true, maxCell: 64,
  onCell(i, j, v) {},
});
```

## 7. Distributions and the ladder

```js
const d = Sheets.dist.fromSamples(arrayOfSimulatedTotals);
const d = Sheets.dist.fromPmf({ 0: 0.1, 1: 0.3, 2: 0.6 });    // or [[x, p]] / [{x, p}]; normalised
const d = Sheets.dist.fromCounts(countsByValue);
d.pOver(170.5)  d.pUnder(170.5)  d.pEq(170)  d.pAtMost(170)  d.mean  d.sd  d.quantile(0.9)  d.pmf()  d.min  d.max

Sheets.ladder(el, {
  dist: d,                                   // or samples array, or pmf
  lines: [150.5, 160.5, 170.5, 180.5],       // default: about 8 lines across the 10th to 90th percentiles
  label: 'Total', odds: 'american',          // 'american' | 'decimal' | 'both'
  prices: { 170.5: { over: -110, under: -110 } },   // optional: adds price + EV columns (American)
  highlight: 'median',                       // or a line value
  compact: undefined,                        // drop the P(under) column; automatic below 560px wide
});
```

Fair odds are no-vig. On whole-number lines, the push is removed before pricing and P(push) gets its own column. EV counts a push as a refund.

## 8. Controls

Each control returns a labelled element. Read or set its `.value`, get notified through `onChange(value)`, and it also dispatches a `change` event whose `detail` is the value.

```js
const venue  = Sheets.ui.select({ label: 'Venue', options: [{ value: 'wankhede', label: 'Wankhede' }, 'Neutral'], value: 'Neutral', onChange: v => … });
const mode   = Sheets.ui.segmented({ label: 'Format', options: ['T20', 'Impact'], value: 'T20' });
const sims   = Sheets.ui.stepper({ label: 'Simulations', min: 1000, max: 1e6, step: 1000, value: 100000 });
const pace   = Sheets.ui.slider({ label: 'Pace', min: 0.8, max: 1.2, step: 0.01, value: 1, fmt: 'num:2', live: false });
const order  = Sheets.ui.dragList({ label: 'Batting order', items: xi.map(p => ({ id: p.id, label: p.name, sub: '+1.2', off: false })) });
const avail  = Sheets.ui.toggleList({ label: 'Available', items: squad.map(p => ({ id: p.id, label: p.name, sub: p.role, on: true })) });
const auto   = Sheets.ui.toggle({ label: 'Re-run on change', value: false });
const run    = Sheets.ui.button({ label: 'Run', primary: true, onClick: go });
const prog   = Sheets.ui.progress();  prog.set(0.4);
panel.append(Sheets.ui.row(venue, mode, sims), pace, order, avail, Sheets.ui.row(run, auto, prog));

order.value          // ['id3', 'id1', …] in the current order; order.value = [...] reorders; order.setItems(items)
avail.value          // ids that are on
```

`dragList` reorders with mouse or touch, or with the keyboard: arrow keys move focus and Alt/Shift + arrow moves the item.

## 9. Markdown

```js
Sheets.loadMarkdown(el, 'data/method.md');                 // fetch + render with loading/error states
Sheets.markdown(el, text, { base: 'data/method.md' });     // render a string; base resolves relative links/images
Sheets.md(text)                                            // -> HTML string
```

The renderer supports headings (with ids and hover anchors), paragraphs, ordered and nested lists, tables (with alignment; all-numeric columns are right-aligned automatically), fenced code, inline code, bold, italic, strikethrough, links, images, blockquotes and horizontal rules. Raw HTML is escaped. `#anchor` links scroll inside the page without touching the workbook hash.

## 10. Data loader

```js
const rows = await Sheets.load('data/batters.json');          // cached by absolute URL; JSON for .json, else text
const txt  = await Sheets.load.text('data/method.md');
const meta = await Sheets.load.optional('data/meta.json');    // null when missing
const { ratings, meta } = await Sheets.load.all({ ratings: 'data/ratings.json', meta: 'data/meta.json' });
Sheets.load(url, { reload: true });                           // bypass the in-memory cache
```

Failures reject with a `Sheets.LoadError` (`.url`, `.status`, `.detail`) whose message is readable, for example `Could not load data/batters.json: HTTP 404 Not Found`.

**Loading and error states.** A sheet's `render` already gets both. For any other region:

```js
const data = await Sheets.into(el, Sheets.load('data/teams.json'), { label: 'Loading teams…' });
if (data) Sheets.heatmap(el, { … });     // on failure el shows the error box and data is undefined
el.append(Sheets.errorEl(err, 'Custom title'));   el.append(Sheets.loadingEl('Working…'));
```

The loading state lists the URLs currently in flight.

## 11. Simulation worker

The sport page ships an ES module with a `run` function. Use plain modules only; there is no bundler.

```js
// ipl/sim.js
export function run(params, ctx) {           // may be async; return a structured-cloneable result
  const r = ctx.rng;                          // seeded uniform [0,1): r.normal(mu, sd), r.int(n), r.poisson(l), r.weighted(cum)
  const n = Math.floor(params.sims / ctx.shards) + (ctx.shard < params.sims % ctx.shards ? 1 : 0);
  const counts = new Float64Array(400);
  for (let i = 0; i < n; i++) {
    /* … simulate one game … */
    if ((i & 4095) === 0) ctx.progress(i / n, { counts: Array.from(counts), n: i });   // throttled to ~20/s
  }
  return { counts: Array.from(counts), n };
}
export function merge(a, b) {                 // required when workers > 1
  return { counts: a.counts.map((v, i) => v + b.counts[i]), n: a.n + b.n };
}
```

```js
const job = Sheets.simulate({
  module: 'sim.js',                 // relative to the page
  params: { sims: 200000, order: …, ratings: … },   // structured-cloned to each worker
  workers: 4,                       // shards; each gets ctx.shard / ctx.shards / its own seed
  seed: 7,                          // optional; random if omitted
  onProgress(frac, partial, shard) { prog.set(frac); },
});
job.then(result => …);   job.catch(err => …);   job.cancel();   job.elapsed /* ms */   job.seed
```

`cancel()` terminates the workers and rejects the job with an error where `err.cancelled === true`. If module workers are unavailable, the module runs on the main thread with the same `ctx`. See the Simulator sheet in `demo.html` and `demo-sim.js` for a complete example, including live partial histograms.

## 12. Theme, tooltip, helpers

```js
Sheets.theme.get(); Sheets.theme.set('dark'); Sheets.theme.toggle(); Sheets.theme.onChange(fn); Sheets.theme.button()
Sheets.tip.show(clientX, clientY, Sheets.tip.html('Header', [{ value: '12.3%', label: 'P(over)', key: 'b1' }], 'note')); Sheets.tip.hide();
Sheets.h('div', { class: 'sh-card', onclick: fn, style: { gap: '8px' } }, child, 'text')   // DOM helper
Sheets.esc(str)  Sheets.debounce(fn, ms)  Sheets.rng(seed)  Sheets.stats.mean/sd/quantile/extent
```

The theme toggle saves to `localStorage['theme']` (the same key as the scanner page). Without a saved choice the OS preference applies.

**Layout classes** for panel content: `sh-card` (bordered surface), `sh-cols` (responsive grid of cards, 420px minimum), `sh-row` (wrapping flex row), `sh-section`, `sh-h` (section heading), `sh-note` (secondary text), `ui-ctl` (control bar), and on text `num`, `muted`, `ink2`, `good`, `bad`, `warn`.

## 13. Design rules

- **Tokens.** These are the scanner page's tokens (`--plane --surface --sunk --ink --ink2 --muted --rule --base --model --good --bad --warn`, `--sans`, `--mono`) plus chart tokens: categorical `--s1…--s8` in fixed order, `--heat-pos/neg/seq` for cell backgrounds, `--div-pos/neg/mid` for diverging marks, and `--grid` and `--axis`. Each has a light and a dark value. Use the tokens; never hard-code hex in a page.
- **Colour has a job.** Categorical colour shows identity, in fixed order and never cycled. Sequential (blue) shows magnitude, and diverging (blue/red around a grey midpoint) shows sign. Status colours (`good`/`bad`/`warn`) are only for state. Keep scatter and multi-line charts to three groups or fewer, and fold the rest into "Other" or small multiples.
- **Text uses ink tokens, not series colours.** Heat cells mix toward the surface so the ink stays readable in both themes.
- **Numbers** are tabular and right-aligned. Use the true minus sign (the formatters do this). Large standalone figures (tiles) use proportional digits.
- **One axis per chart.** Never use a dual axis. The histogram's cumulative view is a separate panel for this reason.
- **Every chart needs a non-hover path to its values**: a table, a ladder, or labels.
