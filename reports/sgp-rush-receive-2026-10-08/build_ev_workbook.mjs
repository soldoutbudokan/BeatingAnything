import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

// Run through the Codex primary runtime from a task-specific temporary directory.
// Input contains normalized observed prices; this workbook recalculates all EVs.
const inputPath = process.argv[2];
const outputDir = process.argv[3];
if (!inputPath || !outputDir) throw new Error('Usage: build_ev_workbook.mjs input.json outputDir');
const data = JSON.parse(await fs.readFile(inputPath, 'utf8'));
await fs.mkdir(outputDir, { recursive: true });
const wb = Workbook.create();
const summary = wb.worksheets.add('Summary');
const detail = wb.worksheets.add('Prices and calculations');
summary.tabColor = '#263D54';
detail.tabColor = '#8095A8';
const navy = '#263D54', gray = '#EDF1F5', ink = '#202C38', muted = '#647386';
const fmtOdds = '+0;-0;0';
const col = n => { let s=''; for(n++;n;n=Math.floor((n-1)/26)) s=String.fromCharCode(65+(n-1)%26)+s; return s; };
const header = (sheet, row, labels) => {
  const range = sheet.getRange(`A${row}:${col(labels.length-1)}${row}`);
  range.values = [labels];
  range.format = { fill: navy, font: { name:'Arial', size:10, bold:true, color:'#FFFFFF' }, wrapText:true, horizontalAlignment:'center', verticalAlignment:'center', rowHeight:32 };
  range.format.borders = {insideVertical:{style:'thin',color:'#FFFFFF'}};
};
const text = (sheet, address, value) => sheet.getRange(address).values=[[value]];
const formulas = (sheet, address, value) => sheet.getRange(address).formulas=[[value]];
const style = (sheet, range) => {sheet.showGridLines=false; sheet.getRange(range).format={font:{name:'Arial',size:10,color:ink},verticalAlignment:'center',rowHeight:22};};
const refStart = 9;
const refsById = new Map(data.references.map((r,i)=>[r.id,{...r,row:refStart+i}]));
const variantHeader = refStart + data.references.length + 5;
const variantStart = variantHeader+1;
const variantsById = new Map(data.variants.map((v,i)=>[v.id,{...v,row:variantStart+i}]));
const notesStart = variantStart+data.variants.length+4;
const detailLast = notesStart+Math.max(data.coverage.length,8)+(data.notes||[]).length+10;
style(detail,`A1:AH${detailLast}`);
style(summary,`A1:P${data.instances.length+14}`);

text(summary,'A2','Rushing + receiving over / rushing under');
summary.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:ink};
text(summary,'A3',data.scope);
summary.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:muted};
text(summary,'A4','EV uses FanDuel four-outcome SGP prices. Bounds apply within each devig model and common completed-game settlement.');
text(summary,'A5','S = rushing + receiving yards; R = rushing yards; C = receiving yards. Prices are recorded snapshots, not live quotes.');
text(summary,'A6','All quoted and rejected variants, source references and editable calculations appear on the second sheet.');
header(summary,8,['Player','Game','S selection','R under','C floor','Base odds','Best redundant additions','Best odds','FD S','FD R','FD relation / EV meaning','Power EV','Additive EV','Status','FD window UTC','Time gap (minutes)']);

text(detail,'A2','FanDuel reference prices and calculations');
detail.getRange('A2').format.font={name:'Arial',size:15,bold:true,color:ink};
text(detail,'A3','OO, OU, UO, UU list S direction first and R direction second. OU is the target.');
text(detail,'A4','q = 1 / decimal odds. Additive p = q − (sum(q) − 1)/4. Negative additive probabilities make that model unavailable.');
text(detail,'A5','Power p = q^k, where sum(q^k) = 1. Ten Newton steps starting at k = 1 are shown in T:AD.');
text(detail,'A6','EV = offered decimal odds × devigged OU probability − 1. Same lines: estimate. FD subset: lower bound. FD superset: upper bound.');
text(detail,'A7','Crossed line changes: EV unavailable. Complete exact FD lines take priority, then the closest FD time window. Positive gaps mean Score was captured later.');
header(detail,8,['Ref ID','Player','FD S line','FD R line','OO odds','OU odds','UO odds','UU odds','q OO','q OU','q UO','q UU','Sum q','Overround','Power k','Power p OU','Additive p OU','Prop. p OU','Additive valid','k 0','k 1','k 2','k 3','k 4','k 5','k 6','k 7','k 8','k 9','k 10','','Captured UTC','Source','URL']);

for (const ref of refsById.values()) {
  const r = ref.row;
  detail.getRange(`A${r}:H${r}`).values=[[ref.id,ref.player,ref.sum_line,ref.rush_line,...['OO','OU','UO','UU'].map(c=>ref.prices[c]??null)]];
  const complete = ['OO','OU','UO','UU'].every(c=>Number.isFinite(ref.prices[c]));
  if(complete) {
    for(let c=4;c<8;c++) formulas(detail,`${col(c+4)}${r}`,`=1/IF(${col(c)}${r}>0,1+${col(c)}${r}/100,1+100/ABS(${col(c)}${r}))`);
    formulas(detail,`M${r}`,`=SUM(I${r}:L${r})`);
    formulas(detail,`N${r}`,`=M${r}-1`);
    formulas(detail,`T${r}`,'=1');
    for(let c=20;c<=29;c++) {
      const previous=`${col(c-1)}${r}`;
      const q=['I','J','K','L'].map(l=>`${l}${r}`);
      const sum=q.map(p=>`${p}^${previous}`).join('+');
      const derivative=q.map(p=>`${p}^${previous}*LN(${p})`).join('+');
      formulas(detail,`${col(c)}${r}`,`=${previous}-(${sum}-1)/(${derivative})`);
    }
    formulas(detail,`O${r}`,`=AD${r}`);
    formulas(detail,`P${r}`,`=J${r}^O${r}`);
    formulas(detail,`S${r}`,`=AND(MIN(I${r}:L${r})-N${r}/4>=0,MAX(I${r}:L${r})-N${r}/4<=1)`);
    formulas(detail,`Q${r}`,`=IF(S${r},J${r}-N${r}/4,"n.a.")`);
    formulas(detail,`R${r}`,`=J${r}/M${r}`);
  } else detail.getRange(`I${r}:S${r}`).values=[Array(11).fill('n.a.')];
  detail.getRange(`AF${r}:AH${r}`).values=[[ref.captured_at||'',ref.source||'',ref.url||'']];
}
detail.getRange(`E${refStart}:H${refStart+data.references.length-1}`).setNumberFormat(fmtOdds);
detail.getRange(`E${refStart}:H${refStart+data.references.length-1}`).format.fill='#EDF1F5';
detail.getRange(`E${refStart}:H${refStart+data.references.length-1}`).format.font.color='#234D8C';
detail.getRange(`I${refStart}:N${refStart+data.references.length-1}`).setNumberFormat('0.00%');
detail.getRange(`O${refStart}:O${refStart+data.references.length-1}`).setNumberFormat('0.000000');
detail.getRange(`P${refStart}:R${refStart+data.references.length-1}`).setNumberFormat('0.00%');
detail.getRange(`T${refStart}:AD${refStart+data.references.length-1}`).setNumberFormat('0.000000');
text(detail,`A${variantHeader-2}`,'Every observed Score variant');
detail.getRange(`A${variantHeader-2}`).format.font={name:'Arial',size:13,bold:true,color:ink};
header(detail,variantHeader,['Variant ID','Player','S selection','R under','Added legs','Score odds','Decimal odds','FD ref ID','Power p OU','Additive p OU','Power EV','Additive EV','EV meaning','Captured UTC','Game','Source','Score URL','Quote status','FD window UTC','Time gap (minutes)']);
for(const v of variantsById.values()) {
  const r=v.row, ref=refsById.get(v.reference_id);
  const baseReceiving=v.base_receiving?`Base also ${v.base_receiving}; `:'';
  detail.getRange(`A${r}:F${r}`).values=[[v.id,v.player,v.sum_selection,v.rush_line,baseReceiving+(v.added_legs||'Base'),v.american??'n.a.']];
  text(detail,`H${r}`,v.reference_id||'Missing');
  if(Number.isFinite(v.american)) formulas(detail,`G${r}`,`=IF(F${r}>0,1+F${r}/100,1+100/ABS(F${r}))`);
  else text(detail,`G${r}`,'n.a.');
  if(ref && v.relation!=='incomparable' && ['OO','OU','UO','UU'].every(c=>Number.isFinite(ref.prices[c]))) {
    formulas(detail,`I${r}`,`=P${ref.row}`);
    formulas(detail,`J${r}`,`=Q${ref.row}`);
    formulas(detail,`K${r}`,`=IF(ISNUMBER(G${r}),G${r}*I${r}-1,"n.a.")`);
    formulas(detail,`L${r}`,`=IF(AND(ISNUMBER(G${r}),ISNUMBER(J${r})),G${r}*J${r}-1,"n.a.")`);
  } else detail.getRange(`I${r}:L${r}`).values=[['n.a.','n.a.','n.a.','n.a.']];
  detail.getRange(`M${r}:R${r}`).values=[[v.ev_meaning||'Unavailable',v.captured_at?new Date(v.captured_at):'',v.game||'',v.source||'',v.url||'',v.status||'Quoted']];
  detail.getRange(`S${r}:T${r}`).values=[[v.reference_window||'n.a.',Number.isFinite(v.reference_time_gap_seconds)?v.reference_time_gap_seconds/60:'n.a.']];
}
detail.getRange(`F${variantStart}:F${variantStart+data.variants.length-1}`).setNumberFormat(fmtOdds);
detail.getRange(`G${variantStart}:G${variantStart+data.variants.length-1}`).setNumberFormat('0.00');
detail.getRange(`I${variantStart}:L${variantStart+data.variants.length-1}`).setNumberFormat('0.00%');
detail.getRange(`N${variantStart}:N${variantStart+data.variants.length-1}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
detail.getRange(`T${variantStart}:T${variantStart+data.variants.length-1}`).setNumberFormat('+0.0;-0.0;0.0');

for(const [i,instance] of data.instances.entries()) {
  const r=9+i, best=variantsById.get(instance.best_variant_id), base=variantsById.get(instance.base_variant_id), ref=refsById.get(best?.reference_id||instance.reference_id);
  const baseReceiving=instance.base_receiving?`Base also ${instance.base_receiving}; `:'';
  summary.getRange(`A${r}:G${r}`).values=[[instance.player,instance.game,instance.sum_selection,instance.rush_line,instance.receiving_floor,instance.base_american??'n.a.',baseReceiving+(best?(best.added_legs||'None (base price)'):'None quoted')]];
  if(base) formulas(summary,`F${r}`,`='Prices and calculations'!F${base.row}`);
  if(best) formulas(summary,`H${r}`,`='Prices and calculations'!F${best.row}`); else text(summary,`H${r}`,'n.a.');
  summary.getRange(`I${r}:K${r}`).values=[[ref?.sum_line??'n.a.',ref?.rush_line??'n.a.',best?.ev_meaning||'Unavailable']];
  if(best && instance.relation!=='incomparable') summary.getRange(`L${r}:M${r}`).formulas=[[`='Prices and calculations'!K${best.row}`,`='Prices and calculations'!L${best.row}`]];
  else summary.getRange(`L${r}:M${r}`).values=[['n.a.','n.a.']];
  text(summary,`N${r}`,instance.status||'');
  summary.getRange(`O${r}:P${r}`).values=[[instance.reference_window||'n.a.',Number.isFinite(instance.reference_time_gap_seconds)?instance.reference_time_gap_seconds/60:'n.a.']];
  if(i%2===1) summary.getRange(`A${r}:P${r}`).format.fill='#F3F5F7';
}
summary.getRange(`F9:F${8+data.instances.length}`).setNumberFormat(fmtOdds);
summary.getRange(`H9:H${8+data.instances.length}`).setNumberFormat(fmtOdds);
summary.getRange(`L9:M${8+data.instances.length}`).setNumberFormat('0.00%;-0.00%;0.00%');
summary.getRange(`P9:P${8+data.instances.length}`).setNumberFormat('+0.0;-0.0;0.0');
for(const range of [summary.getRange(`L9:M${8+data.instances.length}`),detail.getRange(`K${variantStart}:L${variantStart+data.variants.length-1}`)]) {
  range.conditionalFormats.add('cellIs',{operator:'lessThan',formula:0,format:{font:{color:'#9B3131'}}});
}

text(detail,`A${notesStart}`,'Market coverage');
header(detail,notesStart+2,['Game','Coverage status','Observed UTC','Notes']);
for(const [i,c] of data.coverage.entries()) detail.getRange(`A${notesStart+3+i}:D${notesStart+3+i}`).values=[[c.game,c.status,c.captured_at?new Date(c.captured_at):'',c.notes||'']];
if(data.coverage.length) detail.getRange(`C${notesStart+3}:C${notesStart+2+data.coverage.length}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
const methodRow=notesStart+data.coverage.length+6;
text(detail,`A${methodRow}`,'Method and limits');
for(const [i,n] of (data.notes||[]).entries()) text(detail,`A${methodRow+1+i}`,n);

const widths=[24,14,10,10,10,12,35,12,10,10,30,13,13,28,38,14];
widths.forEach((w,i)=>summary.getRange(`${col(i)}1:${col(i)}${data.instances.length+14}`).format.columnWidth=w);
summary.getRange(`A9:P${8+data.instances.length}`).format.rowHeight=42;
summary.getRange(`G9:G${8+data.instances.length}`).format.wrapText=true;
summary.getRange(`K9:K${8+data.instances.length}`).format.wrapText=true;
summary.getRange(`N9:N${8+data.instances.length}`).format.wrapText=true;
summary.getRange(`O9:O${8+data.instances.length}`).format.wrapText=true;
for(const c of ['D','E','F','H','I','J','L','M']) summary.getRange(`${c}9:${c}${8+data.instances.length}`).format.horizontalAlignment='right';
summary.freezePanes.freezeRows(8);
summary.freezePanes.freezeColumns(2);
detail.getRange(`A1:AH${detailLast}`).format.columnWidth=13;
detail.getRange(`A1:B${detailLast}`).format.columnWidth=25;
detail.getRange(`E${variantHeader}:E${variantStart+data.variants.length-1}`).format.columnWidth=35;
detail.getRange(`M1:N${detailLast}`).format.columnWidth=26;
detail.getRange(`O1:R${detailLast}`).format.columnWidth=26;
detail.getRange(`P1:Q${detailLast}`).format.columnWidth=45;
detail.getRange(`S1:S${detailLast}`).format.columnWidth=38;
detail.getRange(`AF1:AH${detailLast}`).format.columnWidth=36;
detail.getRange(`A${variantStart}:R${variantStart+data.variants.length-1}`).format.rowHeight=32;
detail.getRange(`E${variantStart}:E${variantStart+data.variants.length-1}`).format.wrapText=true;
detail.getRange(`M${variantStart}:M${variantStart+data.variants.length-1}`).format.wrapText=true;
detail.getRange(`R${variantStart}:R${variantStart+data.variants.length-1}`).format.wrapText=true;
detail.getRange(`S${variantStart}:S${variantStart+data.variants.length-1}`).format.wrapText=true;
detail.getRange(`P${variantStart}:Q${variantStart+data.variants.length-1}`).format.wrapText=true;
detail.getRange(`A${variantStart}:R${variantStart+data.variants.length-1}`).format.rowHeight=58;
for(const c of ['D','F','G','I','J','K','L']) detail.getRange(`${c}${variantStart}:${c}${variantStart+data.variants.length-1}`).format.horizontalAlignment='right';
detail.freezePanes.freezeRows(8);
detail.freezePanes.freezeColumns(2);
// Verify editable FD inputs flow through the power solver and variant EV.
const probe = [...variantsById.values()].find(v=>Number.isFinite(v.ev_power));
if (probe) {
  const ref=refsById.get(probe.reference_id);
  const input=detail.getRange(`E${ref.row}`);
  const original=input.values[0][0];
  const before=detail.getRange(`K${probe.row}`).values[0][0];
  input.values=[[original+1]];
  const changed=detail.getRange(`K${probe.row}`).values[0][0];
  if(typeof changed!=='number'||Math.abs(changed-before)<1e-10) throw new Error('FD input perturbation did not recalculate EV');
  input.values=[[original]];
}
wb.recalculate();

// Independently calculated JSON values must agree with workbook formulas.
for(const v of variantsById.values()) {
  if(Number.isFinite(v.ev_power)) {
    const actual=detail.getRange(`K${v.row}`).values[0][0];
    if(typeof actual !== 'number'||Math.abs(actual-v.ev_power)>1e-9) throw new Error(`Power EV mismatch ${v.id}: ${actual} versus ${v.ev_power}`);
  }
  if(Number.isFinite(v.ev_additive)) {
    const actual=detail.getRange(`L${v.row}`).values[0][0];
    if(typeof actual !== 'number'||Math.abs(actual-v.ev_additive)>1e-9) throw new Error(`Additive EV mismatch ${v.id}: ${actual} versus ${v.ev_additive}`);
  }
}
const inspect=await wb.inspect({kind:'table',range:`Summary!A8:N${Math.min(13,8+data.instances.length)}`,include:'values,formulas',tableMaxRows:6,tableMaxCols:14,maxChars:7000});
await fs.writeFile(path.join(outputDir,'workbook-inspection.ndjson'),inspect.ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'Formula error scan'});
await fs.writeFile(path.join(outputDir,'workbook-errors.ndjson'),errors.ndjson);
for(const [name,sheetName,range] of [['summary-preview','Summary',`A1:P${Math.min(23,8+data.instances.length)}`],['summary-tail-preview','Summary',`A${Math.max(8,8+data.instances.length-10)}:P${8+data.instances.length}`],['references-preview','Prices and calculations',`A1:R${Math.min(18,refStart+data.references.length-1)}`],['variants-preview','Prices and calculations',`A${variantHeader-2}:T${Math.min(variantStart+8,variantStart+data.variants.length-1)}`]]) {
  const preview=await wb.render({sheetName,range,scale:1.5,format:'png'});
  await fs.writeFile(path.join(outputDir,`${name}.png`),new Uint8Array(await preview.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(outputDir,'sgp-fanduel-ev.xlsx'));
console.log(JSON.stringify({instances:data.instances.length,variants:data.variants.length,references:data.references.length,output:path.join(outputDir,'sgp-fanduel-ev.xlsx'),errorScan:errors.ndjson}));
