const $ = (id) => document.getElementById(id);
const classes = ['DOWN', 'NO_MATERIAL_MOVE', 'UP'];
const labels = ['Down', 'Neutral', 'Up'];
const pct = (v) => Number.isFinite(v) ? `${(v * 100).toFixed(2)}%` : '—';
let envelope, research, indexes = [], request;
function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
function winner(p) { return p.indexOf(Math.max(...p)); }
function metrics(name, selected = indexes) {
  const confusion = [[0,0,0],[0,0,0],[0,0,0]];
  for (const i of selected) confusion[classes.indexOf(research.rows[i].label)][winner(research.probabilities[name][i])]++;
  const recall = confusion.map((row, i) => row.reduce((a,b)=>a+b,0) ? row[i]/row.reduce((a,b)=>a+b,0) : null);
  const accuracy = selected.length ? confusion.reduce((s,r,i)=>s+r[i],0)/selected.length : null;
  // All three classes participate. A class absent from the filter is reported undefined.
  return {accuracy, recall, balanced: recall.includes(null) ? null : recall.reduce((a,b)=>a+b,0)/3};
}
function bar(container, title, value, count, color) {
  const row=el('div',undefined,'mix-row'), track=el('div',undefined,'track'), fill=el('div',undefined,'fill');
  fill.style.width=`${100*value}%`; if(color) fill.style.background=color;
  track.append(fill); row.append(el('span',title),track,el('span',count ?? pct(value))); container.append(row);
}
function renderResearch() {
  const selected=$('candidate').value;
  indexes=research.rows.map((_,i)=>i).filter(i=>$('symbol').value==='ALL'||research.rows[i].symbol===$('symbol').value);
  const score=metrics(selected), baseline=indexes.filter(i=>research.rows[i].label==='NO_MATERIAL_MOVE').length/indexes.length;
  $('stats').replaceChildren();
  for(const [title,value,note] of [['Examples',indexes.length,'Independent company-days'],['Accuracy',pct(score.accuracy),'Saved candidate probabilities'],['Equal-class recall',pct(score.balanced),'Down / neutral / up treated equally'],['Neutral-only accuracy',pct(baseline),'Predict neutral on every example']]) {
    const node=el('div',undefined,'stat'); node.append(el('span',title),el('strong',value),el('small',note)); $('stats').append(node);
  }
  $('comparison').replaceChildren();
  for(const name of Object.keys(research.probabilities)) {
    const m=metrics(name), row=el('tr');
    for(const value of [research.model_names[name]||name,pct(m.accuracy),pct(m.balanced),pct(m.recall[2]),pct(m.recall[0])]) row.append(el('td',value));
    $('comparison').append(row);
  }
  $('mix').replaceChildren();
  classes.forEach((c,i)=>{const count=indexes.filter(n=>research.rows[n].label===c).length; bar($('mix'),labels[i],count/indexes.length,String(count),['#f08c8c','#a5b4b9','#67dbbd'][i]);});
  monthly(selected);
  $('example').replaceChildren();
  for(const i of indexes) {const row=research.rows[i], option=el('option',`${row.session} · ${row.symbol}`); option.value=String(i); $('example').append(option);}
  renderReplay();
}
function monthly(name) {
  const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 660 240'); svg.setAttribute('role','img'); svg.setAttribute('aria-label','Monthly candidate and neutral-only accuracy');
  function shape(tag, attrs, text) {const n=document.createElementNS(ns,tag); for(const [k,v] of Object.entries(attrs)) n.setAttribute(k,String(v)); if(text) n.textContent=text; svg.append(n); return n;}
  for(const value of [0,.25,.5,.75,1]) {const y=200-170*value; shape('line',{x1:45,x2:640,y1:y,y2:y,stroke:'#30383d'}); shape('text',{x:0,y:y+4,fill:'#adb8bc','font-size':11},`${value*100}%`);}
  const months=[...new Set(indexes.map(i=>research.rows[i].session.slice(0,7)))].sort();
  months.forEach((month,n)=>{
    const selected=indexes.filter(i=>research.rows[i].session.startsWith(month));
    const candidate=metrics(name,selected).accuracy, neutral=selected.filter(i=>research.rows[i].label==='NO_MATERIAL_MOVE').length/selected.length;
    const x=50+n*(580/Math.max(months.length,1)), width=Math.min(18,220/months.length);
    for(const [value,offset,color] of [[candidate,0,'#67dbbd'],[neutral,width+3,'#839499']]) {
      const rect=shape('rect',{x:x+offset,y:200-170*value,width,height:170*value,fill:color,tabindex:0,'aria-label':`${month}: ${offset?'neutral baseline':'candidate'} ${pct(value)}`});
      const title=document.createElementNS(ns,'title'); title.textContent=`${month} · ${offset?'Neutral baseline':'Candidate'} ${pct(value)} · ${selected.length} examples`; rect.append(title);
    }
    shape('text',{x,y:224,fill:'#adb8bc','font-size':10},month.slice(5));
  });
  $('monthly').replaceChildren(svg);
}
function renderReplay() {
  $('outcome').textContent='Outcome hidden'; $('reveal').disabled=false;
  const i=Number($('example').value), name=$('candidate').value, row=research.rows[i];
  $('prediction').replaceChildren(); if(!row) return;
  const values=research.probabilities[name][i];
  $('prediction').append(el('h2',`${row.symbol} · ${row.session} · Predicted ${labels[winner(values)]}`));
  values.forEach((value,n)=>bar($('prediction'),labels[n],value));
  $('prediction').append(el('p',`Historical approximate inputs · ${research.model_names[name]||name}`,'caption'));
}
function renderOperations() {
  $('forward').textContent=envelope.forward ? `Latest published forward result: ${envelope.forward.session}. Research shadow only; not promoted.` : 'No forward prediction has been published. Historical results below are not live forecasts.';
  $('jobs').replaceChildren();
  for(const job of envelope.jobs) {const row=el('tr'); for(const value of [job.kind,job.status,job.updated_at]) row.append(el('td',value)); $('jobs').append(row);}
  if(!envelope.jobs.length) {const row=el('tr'), cell=el('td','No cloud jobs recorded.'); cell.colSpan=3; row.append(cell); $('jobs').append(row);}
  $('provenance').replaceChildren();
  for(const [key,value] of Object.entries({Period:research.period,'Availability tier':research.availability_tier,'Target convention':research.target,'Report hash':research.report_hash,'Release hash':research.release_hash,'Native receipt':research.native_receipt.verify_receipt,'Model promotion':'Disabled','Broker orders':'Disabled'})) $('provenance').append(el('dt',key),el('dd',value));
}
async function load() {
  request?.abort(); request=new AbortController(); const current=request;
  research=null; envelope=null; $('outcome').textContent=''; $('reveal').disabled=true;
  for(const id of ['stats','comparison','monthly','mix','prediction','jobs','provenance']) $(id).replaceChildren();
  $('forward').textContent='Loading current publication state…';
  $('refresh').disabled=true; $('notice').textContent='Loading verified private projections…';
  try {
    const response=await fetch(`/api/dashboard?period=${encodeURIComponent($('period').value)}`,{signal:current.signal,cache:'no-store',credentials:'same-origin'});
    if(!response.ok) throw new Error(`Data request failed (${response.status}). Refresh after checking the cloud job.`);
    envelope=await response.json(); research=envelope.research;
    if(!research) throw new Error('No verified research projection is published for this period yet.');
    if(research.live!==false||research.availability_tier!=='HISTORICAL_APPROXIMATE'||research.classes.join()!==classes.join()) throw new Error('Unsupported projection. Research display held.');
    const previous=$('candidate').value; $('candidate').replaceChildren();
    for(const name of Object.keys(research.probabilities)) {const option=el('option',research.model_names[name]||name); option.value=name; $('candidate').append(option);}
    $('candidate').value=Object.hasOwn(research.probabilities,previous)?previous:'price';
    $('notice').textContent=`${research.period}: retrospective research, not a live signal or a fresh blind test. No learned candidate has beaten the neutral-only baseline on full-population overall accuracy.`;
    renderResearch(); renderOperations();
  } catch(error) {if(error.name!=='AbortError') {research=null; $('notice').textContent=error.message; $('stats').replaceChildren(); $('comparison').replaceChildren(); $('monthly').replaceChildren(); $('mix').replaceChildren(); $('prediction').replaceChildren(); $('outcome').textContent=''; $('reveal').disabled=true;}}
  finally {if(current===request) $('refresh').disabled=false;}
}
$('refresh').addEventListener('click',load); $('period').addEventListener('change',load);
for(const id of ['symbol','candidate']) $(id).addEventListener('change',()=>{if(research)renderResearch();});
$('example').addEventListener('change',()=>{if(research)renderReplay();});
$('reveal').addEventListener('click',()=>{if(!research)return; const row=research.rows[Number($('example').value)]; $('outcome').textContent=`Observed: ${labels[classes.indexOf(row.label)]} · open-to-close return ${pct(row.return_fraction)}. Not an executable fill or trading profit.`; $('reveal').disabled=true;});
document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});document.querySelectorAll('.view').forEach(view=>view.hidden=view.id!==button.dataset.view);}));
load();
