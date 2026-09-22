"""Build docs/index.html: the early-payout scanner page (GitHub Pages serves docs/).

Reads live/early-payout/picks.json and history.csv plus the payout curves and renders one
self-contained page (no assets, stdlib only). Generated: never hand-edit docs/index.html.

    python3 site/build_early_payout.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beating.early_payout import CONFIG, CURVES, LIVE, decimal_to_american  # noqa: E402

OUT = ROOT / "docs/index.html"
REPO = "https://github.com/soldoutbudokan/BeatingAnything"
REPORT = f"{REPO}/blob/main/reports/early-payout-2026-09-22.md"
LABEL = {"NFL": "NFL", "NCAAF": "College football", "NBA": "NBA", "SOCCER": "Soccer"}


def breakeven_rows(curves):
    out = []
    for sport, c in curves.items():
        for pt in c["points"]:
            p, e = pt["p"], pt["extra"]
            if 0.1 <= p <= 0.7:
                out.append({"sport": sport, "p": p, "fair": decimal_to_american(1 / p),
                            "breakeven": decimal_to_american(1 / (p + e)), "discount": e / (p + e)})
    return out


def build():
    picks_file, hist_file = LIVE / "picks.json", LIVE / "history.csv"
    picks = json.loads(picks_file.read_text()) if picks_file.exists() else {"generated_utc": None, "rows": [], "events": {}, "errors": []}
    history = list(csv.DictReader(hist_file.open())) if hist_file.exists() else []
    cfg, curves = json.loads(CONFIG.read_text()), json.loads(CURVES.read_text())["sports"]
    data = {"picks": picks, "history": history[-400:][::-1], "rules": cfg["rules"], "promos": cfg["promos"],
            "breakeven": breakeven_rows(curves), "labels": LABEL}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = PAGE.replace("__DATA__", payload).replace("__REPO__", REPO).replace("__REPORT__", REPORT)
    if not OUT.exists() or OUT.read_text() != page:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(page)
        print("wrote", OUT)
    else:
        print("unchanged", OUT)
    (OUT.parent / ".nojekyll").touch()


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Early Payout Scanner</title>
<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>
<style>
:root{color-scheme:light;--plane:#f9f9f7;--surface:#fcfcfb;--sunk:#f3f2ee;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --rule:#e6e5df;--base:#c3c2b7;--model:#2a78d6;--market:#eb6834;--good:#006300;--bad:#d03b3b;--warn:#b07100;
  --shadow:0 1px 2px rgba(11,11,11,.05),0 8px 24px rgba(11,11,11,.05);
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,"Roboto Mono",monospace}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;
  --sunk:#141413;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--rule:#2c2c2a;--base:#383835;--model:#3987e5;--market:#d95926;
  --good:#0ca30c;--bad:#e66767;--warn:#fab219;--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35)}}
:root[data-theme="dark"]{color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;--sunk:#141413;--ink:#fff;--ink2:#c3c2b7;
  --muted:#898781;--rule:#2c2c2a;--base:#383835;--model:#3987e5;--market:#d95926;--good:#0ca30c;--bad:#e66767;--warn:#fab219;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35)}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:inherit}
h1,h2,h3{margin:0;line-height:1.2;text-wrap:balance}
p{margin:0}
code{font-family:var(--mono);font-size:.88em;background:var(--sunk);padding:.1em .35em;border-radius:4px}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px 72px}
.masthead{border-bottom:1px solid var(--rule);background:var(--surface)}
.masthead .wrap{padding-top:26px;padding-bottom:0;display:flex;flex-wrap:wrap;gap:16px 28px;align-items:flex-start;justify-content:space-between}
.brand h1{font-size:27px;letter-spacing:-.02em}
.brand p{color:var(--ink2);max-width:62ch;margin-top:6px}
.stamp{color:var(--muted);font-size:12.5px;display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.stamp-row{display:flex;gap:8px}
.pill{text-decoration:none;border:1px solid var(--base);border-radius:999px;padding:5px 12px;color:var(--ink2);font-size:12.5px;
  white-space:nowrap;background:none;font:inherit;cursor:pointer}
.pill:hover{border-color:var(--ink2);color:var(--ink)}
.tabs{display:flex;gap:2px;margin:22px 0 0;flex-wrap:wrap;width:100%}
.tab{appearance:none;background:none;border:0;border-bottom:2px solid transparent;padding:10px 14px;font:inherit;font-size:14px;
  color:var(--ink2);cursor:pointer;border-radius:6px 6px 0 0}
.tab:hover{color:var(--ink);background:var(--sunk)}
.tab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--model);font-weight:600}
.panel{padding-top:28px}
.panel[hidden]{display:none}
.tiles{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(156px,1fr))}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:14px 16px;box-shadow:var(--shadow)}
.tile-label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.tile-val{font-size:24px;font-weight:600;letter-spacing:-.02em;margin-top:4px;font-variant-numeric:tabular-nums}
.tile-sub{font-size:12.5px;color:var(--ink2);margin-top:2px}
.block{margin-top:34px}
.block>h3{font-size:16px}
.note{font-size:13px;color:var(--ink2);max-width:72ch;margin-top:6px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.filters select,.filters input{font:inherit;font-size:13px;padding:5px 9px;border:1px solid var(--base);border-radius:8px;background:var(--surface);color:var(--ink)}
.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:10px;background:var(--surface);margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:500;padding:10px;white-space:nowrap;
  border-bottom:1px solid var(--rule);text-align:left}
td{padding:9px 10px;border-bottom:1px solid var(--rule);white-space:nowrap;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
.r{text-align:right}
.good{color:var(--good);font-weight:600}.bad{color:var(--bad)}.warn{color:var(--warn)}.muted{color:var(--muted)}
.empty{padding:18px;color:var(--muted);font-size:13.5px}
.flag{font-family:var(--mono);font-size:11px;color:var(--warn);font-weight:400}
.sub{font-size:11.5px;color:var(--muted);font-weight:400}
td a{text-decoration:underline;text-decoration-color:var(--base);text-underline-offset:3px}
@media (max-width:640px){.stamp{align-items:flex-start}}
.foot{margin-top:40px;padding-top:16px;border-top:1px solid var(--rule);font-size:12.5px;color:var(--muted);max-width:80ch}
.formula{font-family:var(--mono);background:var(--sunk);padding:10px 14px;border-radius:8px;margin-top:10px;display:inline-block}
</style>
</head>
<body>
<header class="masthead"><div class="wrap">
  <div class="brand"><h1>Early Payout Scanner</h1>
    <p>Moneylines where a book's early-payout rule turns its price into positive expected value, priced against the sharpest odds available.</p></div>
  <div class="stamp"><div class="stamp-row"><a class="pill" href="__REPO__">Repository</a>
    <button class="pill" id="theme" type="button" aria-label="Toggle colour theme">Theme</button></div>
    <div id="scanned"></div></div>
  <nav class="tabs" role="tablist">
    <button class="tab" role="tab" data-tab="now" aria-selected="true">Now</button>
    <button class="tab" role="tab" data-tab="how">How it works</button>
    <button class="tab" role="tab" data-tab="log">Log</button>
  </nav>
</div></header>
<main class="wrap">
<section class="panel" id="now">
  <div class="tiles" id="tiles"></div>
  <div class="block"><h3>Playable</h3>
    <p class="note">Expected value clears the minimum and every gate passes. Check the price is still there and the team's news before betting.</p>
    <div class="filters"><select id="f-sport"><option value="">All sports</option></select>
      <select id="f-book"><option value="">All books</option></select>
      <input id="f-q" type="search" placeholder="Team or matchup"></div>
    <div class="scroll"><table id="t-play"></table></div></div>
  <div class="block"><h3>Close calls</h3><p class="note">Within two points of the minimum, or blocked by a gate (flag shown).</p>
    <div class="scroll"><table id="t-near"></table></div></div>
  <div class="block" id="errs" hidden><h3>Scan problems</h3><p class="note" id="errtext"></p></div>
</section>
<section class="panel" id="how" hidden>
  <div class="block" style="margin-top:0"><h3>The calculation</h3>
    <p class="note">The book pays the bet as a win once the team leads by the set margin, even if it goes on to lose. That adds the chance the team reaches the lead and still fails to win.</p>
    <div class="formula">EV = book decimal odds &times; (fair win prob + payout extra) &minus; 1</div>
    <p class="note">Fair win probability: Pinnacle's de-vigged price when quoted, otherwise the median of the prediction-market exchanges, otherwise the median of the other sportsbooks. Payout extra comes from play-by-play history for each sport. The stake is fractional Kelly on the payout-adjusted win probability, capped.</p>
    <p class="note" id="rules"></p></div>
  <div class="block"><h3>Break-even prices</h3>
    <p class="note">The longest-looking price that still breaks even, by fair win probability. A book price at or better than the break-even column is positive EV. <a href="__REPORT__">Full analysis</a>.</p>
    <div class="scroll"><table id="t-be"></table></div></div>
</section>
<section class="panel" id="log" hidden>
  <div class="block" style="margin-top:0"><h3>Every playable price seen</h3>
    <p class="note">One row each time a playable price first appears or moves. Results and closing-line value are not graded yet.</p>
    <div class="scroll"><table id="t-log"></table></div></div>
</section>
<p class="foot">Generated from <code>live/early-payout/picks.json</code> by <code>site/build_early_payout.py</code>. Research, not advice. Book terms change; confirm the payout rule in the app.</p>
</main>
<script>
const D=__DATA__;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const am=a=>a==null?'':(a>0?'+':'')+a;
const pct=x=>x==null?'':(x>0?'+':'')+(100*x).toFixed(1)+'%';
const et=iso=>iso?new Date(iso).toLocaleString('en-US',{timeZone:'America/New_York',weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' ET':'';
const lab=s=>D.labels[s]||s;
const rows=D.picks.rows||[];
$('#scanned').textContent=D.picks.generated_utc?'Last scan '+et(D.picks.generated_utc):'No scan yet';
const plays=rows.filter(r=>r.play);
const priced=rows.filter(r=>r.ev!=null);
const best=plays.length?Math.max(...plays.map(r=>r.ev)):null;
const ev=D.picks.events||{};
$('#tiles').innerHTML=[['Playable',plays.length,'min EV '+pct(D.rules.min_ev)],['Best EV',best==null?'—':pct(best),''],
 ['Prices checked',priced.length,Object.keys(ev).map(k=>lab(k)+' '+ev[k]).join(' · ')],
 ['Logged',D.history.length,'playable prices seen']].map(t=>`<div class="tile"><div class="tile-label">${t[0]}</div><div class="tile-val">${t[1]}</div><div class="tile-sub">${esc(t[2])}</div></div>`).join('');
const head=['Bet','Price','EV','Break-even','Stake','Book','Fair','Extra','Starts','Matchup'];
function row(r){const team=r.link?`<a href="${esc(r.link)}" target="_blank" rel="noopener">${esc(r.team)}</a>`:esc(r.team);
 const flags=(r.flags||[]).length?`<div class="flag">${esc(r.flags.join(' '))}</div>`:'';
 return `<tr><td><b>${team}</b><div class="sub">${esc(lab(r.sport))}</div>${flags}</td>
 <td class="r">${am(r.american)}</td><td class="r ${r.ev>=D.rules.min_ev?'good':r.ev<0?'bad':''}">${pct(r.ev)}</td>
 <td class="r">${am(r.breakeven_american)}</td><td class="r">${r.play?'$'+Number(r.stake).toFixed(2):''}</td><td>${esc(r.book)}</td>
 <td class="r muted">${am(r.fair_american)}</td><td class="r muted">${r.extra==null?'':(100*r.extra).toFixed(1)+' pts'}</td>
 <td>${esc(et(r.start_utc))}</td><td class="muted">${esc(r.matchup)}</td></tr>`}
function table(el,list,empty){el.innerHTML=list.length?`<thead><tr>${head.map((h,i)=>`<th class="${(i>=1&&i<=4)||i===6||i===7?'r':''}">${h}</th>`).join('')}</tr></thead><tbody>${list.map(row).join('')}</tbody>`:`<tbody><tr><td class="empty">${empty}</td></tr></tbody>`}
for(const [id,key] of [['#f-sport','sport'],['#f-book','book']]){[...new Set(rows.map(r=>r[key]))].sort().forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=key==='sport'?lab(v):v;$(id).appendChild(o)})}
function render(){const s=$('#f-sport').value,b=$('#f-book').value,q=$('#f-q').value.toLowerCase();
 const f=r=>(!s||r.sport===s)&&(!b||r.book===b)&&(!q||(r.team+' '+r.matchup).toLowerCase().includes(q));
 table($('#t-play'),plays.filter(f),'Nothing playable right now.');
 table($('#t-near'),rows.filter(r=>!r.play&&r.ev!=null&&(r.ev>=D.rules.min_ev-0.02||(r.flags||[]).length&&r.ev>0)).filter(f).slice(0,60),'No close calls.')}
['#f-sport','#f-book','#f-q'].forEach(id=>$(id).addEventListener('input',render));render();
const errs=D.picks.errors||[];if(errs.length){$('#errs').hidden=false;$('#errtext').textContent=errs.slice(0,8).join(' | ')}
$('#rules').textContent='Current rules: minimum EV '+pct(D.rules.min_ev)+', claims above '+pct(D.rules.max_ev)+' blocked as suspect, quotes older than '+D.rules.max_quote_age_minutes+' minutes blocked, stake '+D.rules.kelly_fraction+' Kelly capped at '+pct(D.rules.max_stake_fraction)+' of a $'+D.rules.bankroll+' bankroll. Payout rules: '+Object.entries(D.promos).map(([b,s])=>b+' ('+Object.entries(s).map(([k,v])=>lab(k)+' '+v).join(', ')+')').join('; ')+'.';
const be=D.breakeven;const sports=[...new Set(be.map(r=>r.sport))];
$('#t-be').innerHTML=`<thead><tr><th>Fair win prob</th>${sports.map(s=>`<th class="r">${esc(lab(s))}</th>`).join('')}</tr></thead><tbody>`+
 [0.1,0.2,0.3,0.4,0.5,0.6].map(lo=>`<tr><td>${Math.round(lo*100)}–${Math.round(lo*100)+10}%</td>${sports.map(s=>{const r=be.find(x=>x.sport===s&&x.p>lo&&x.p<=lo+0.1);
 return `<td class="r">${r?`<span class="muted">${am(r.fair)} →</span> <b>${am(r.breakeven)}</b>`:'—'}</td>`}).join('')}</tr>`).join('')+'</tbody>';
const H=D.history;$('#t-log').innerHTML=H.length?`<thead><tr><th>Seen</th><th>Sport</th><th>Matchup</th><th>Bet</th><th>Book</th><th class="r">Price</th><th class="r">Fair p</th><th class="r">EV</th><th class="r">Stake</th></tr></thead><tbody>`+
 H.map(h=>`<tr><td>${esc(et(h.seen_utc))}</td><td>${esc(lab(h.sport))}</td><td>${esc(h.matchup)}</td><td>${esc(h.team)}</td><td>${esc(h.book)}</td><td class="r">${am(+h.american)}</td><td class="r">${(+h.fair_p).toFixed(3)}</td><td class="r good">${pct(+h.ev)}</td><td class="r">$${esc(h.stake)}</td></tr>`).join('')+'</tbody>'
 :'<tbody><tr><td class="empty">Nothing logged yet.</td></tr></tbody>';
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-selected',x===t));
 document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!==t.dataset.tab)}));
$('#theme').addEventListener('click',()=>{const cur=document.documentElement.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
 const next=cur==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',next);try{localStorage.setItem('theme',next)}catch(e){}});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
