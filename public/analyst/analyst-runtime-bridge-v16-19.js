(()=>{'use strict';
const nativeFetch=window.fetch.bind(window);
const clean=v=>String(v??'').replace(/\s+/g,' ').trim();
const norm=v=>clean(v).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=1)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json;charset=utf-8','cache-control':'no-store'}});
const requestUrl=input=>{try{return new URL(typeof input==='string'?input:input?.url,location.href)}catch{return null}};
const bodyOf=options=>{try{return JSON.parse(String(options?.body||'{}'))}catch{return {}}};
const isElection=q=>{const x=norm(q);return x.includes('france')&&x.includes('2027')&&/(election|president|scrutin|vote)/.test(x)};
const isSignalPrompt=q=>{const x=norm(q);return /signal/.test(x)&&/(surveill|merit|priorit)/.test(x)&&!/(election|climat|emploi|energie|ukraine|sante|banque|inflation|france 2027)/.test(x)};
const active=f=>!['resolved','invalidated','expired'].includes(String(f?.status||'').toLowerCase());
const ftitle=f=>String(f?.title||f?.headline||f?.outcome||'Scénario');
const fprob=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return clamp(p,0,100);const e=Number(f?.probability?.estimate);return Number.isFinite(e)?clamp(e*100,0,100):0};
const fconf=f=>clamp(Number(f?.consolidation?.score??f?.confidence??0),0,100);
const strong=f=>Array.isArray(f?.signal_convergence?.strong_signals)?f.signal_convergence.strong_signals:[];
const signalLabel=s=>clean(typeof s==='string'?s:(s?.title||s?.label||s?.name||s?.signal||''));

async function snapshot(){
  for(const url of ['/api/snapshot','/data/evidence-live.json']){
    try{const r=await nativeFetch(url,{cache:'no-store'});if(r.ok)return await r.json();}catch{}
  }
  return null;
}
function worldsFrom(rows){return {fallback:true,consensus:{interpretation:'prévisions actives'},worlds:rows.slice(0,4).map((f,i)=>({world_id:`browser_${i}`,title:ftitle(f),domain:f?.domain||'Prévision',region:f?.region||f?.geography||'Monde',forecast_probability_percent:fprob(f),relative_world_weight_percent:null,movement_points:Number(f?.probability_delta_points)||0,confidence_score:fconf(f),source_count:(f?.consolidation?.source_providers||[]).length,fallback:true}))};}
async function signalAnswer(){
  const data=await snapshot();const rows=(data?.forecasts||[]).filter(active);
  if(!rows.length)return {schema:'providence-analyst-response-v1',status:'ok',provider:'browser_quantic',text:'Je ne dispose pas encore de signaux actifs exploitables sur ce déploiement public.',superposition:{fallback:true,consensus:{interpretation:'aucun signal'},worlds:[]},execution_authority:false};
  const ranked=rows.map(f=>{const movement=Math.abs(Number(f?.probability_delta_points)||0);const sigs=strong(f).map(signalLabel).filter(Boolean);const score=fconf(f)*.45+fprob(f)*.25+movement*4+sigs.length*5;return {f,sigs,score,movement};}).sort((a,b)=>b.score-a.score);
  const lead=ranked[0];const label=lead.sigs[0]||ftitle(lead.f);const delta=Number(lead.f?.probability_delta_points)||0;
  const text=`Le signal à surveiller en priorité est « ${label} ».\n\nIl est actuellement lié à la trajectoire « ${ftitle(lead.f)} » : probabilité publique ${round(fprob(lead.f),1)}% · solidité ${Math.round(fconf(lead.f))}/100${delta?` · variation ${delta>0?'+':''}${round(delta,1)} point(s)`:''}.\n\nJe le place devant les autres signaux parce qu’il combine niveau de confiance, probabilité de la trajectoire et mouvement récent. Ce classement reste un indicateur de surveillance, pas une preuve causale.`;
  return {schema:'providence-analyst-response-v1',status:'ok',provider:'browser_quantic',text,superposition:worldsFrom(ranked.map(x=>x.f)),execution_authority:false};
}

function grid(table){
  const out=[],carry=[];
  for(const tr of [...table.rows]){
    const row=[];
    for(let c=0;c<carry.length;c++)if(carry[c]?.left>0){row[c]=carry[c].text;carry[c].left--;}
    let col=0;
    for(const cell of [...tr.cells]){
      while(row[col]!==undefined)col++;
      const text=clean(cell.textContent);const cs=Math.max(1,Number(cell.colSpan)||1),rs=Math.max(1,Number(cell.rowSpan)||1);
      for(let k=0;k<cs;k++){row[col+k]=text;if(rs>1)carry[col+k]={text,left:rs-1};}
      col+=cs;
    }
    out.push(row);
  }
  return out;
}
const meta=s=>/(sondeur|institut|date|echantillon|échantillon|autres?|marge|hypoth|terrain|commanditaire|participation|abstention)/i.test(s);
function scoreValue(text){
  const s=clean(text);if(!s||/^[-—–]$/.test(s))return null;if(/^<\s*1(?:\s*%)?$/.test(s))return .5;
  const m=s.match(/(?:^|\s)(\d{1,2}(?:[.,]\d+)?)(?:\s*%)?(?=\s|$)/);if(!m)return null;const n=Number(m[1].replace(',','.'));return n>=0&&n<=60?n:null;
}
function cellCandidate(text){
  const s=clean(text).replace(/<\s*1\s*%?/g,' ').replace(/\b\d{1,2}(?:[.,]\d+)?\s*%?/g,' ').replace(/[—–-]/g,' ').replace(/\([^)]*\)/g,' ').replace(/\s+/g,' ').trim();
  if(!s||meta(s)||/^(oui|non|nc|nspp)$/i.test(s))return null;return /[A-Za-zÀ-ÿ]{3}/.test(s)?s:null;
}
function headerCandidate(text){
  let s=clean(text).replace(/\([^)]*\)/g,' ').replace(/^candidat(?:e)?\s+/i,'').trim();if(!s||meta(s)||/^candidat/i.test(s)||/^(lo|lfi|pcf|ps|pp|epr|lr|lfh|dlf|rn|rec|le)$/i.test(s))return null;return /[A-Za-zÀ-ÿ]{3}/.test(s)?s:null;
}
function parsePollTables(html){
  const doc=new DOMParser().parseFromString(html,'text/html');const polls=[];
  for(const table of [...doc.querySelectorAll('table.wikitable')].slice(0,12)){
    const m=grid(table);if(m.length<3)continue;
    let dataStart=m.findIndex(r=>r.filter(x=>scoreValue(x)!==null).length>=4);if(dataStart<0)continue;
    const colCount=Math.max(...m.map(r=>r.length));const headers=[];
    for(let c=0;c<colCount;c++){
      let h=null;for(let r=Math.max(0,dataStart-3);r<dataStart;r++){const x=headerCandidate(m[r]?.[c]);if(x)h=x;}headers[c]=h;
    }
    for(let r=dataStart;r<m.length;r++){
      const cells=m[r];const sample=cells.flatMap(x=>[...(String(x||'').matchAll(/\b(\d{3,5})\b/g))].map(z=>Number(z[1]))).find(n=>n>=300&&n<=30000)||null;
      const pollster=cells.find(x=>/ifop|ipsos|bva|elabe|harris|odoxa|cluster17|opinionway|verian|kantar|toluna|yougov|csa/i.test(String(x)))||'Institut';
      const candidates=[];
      for(let c=0;c<cells.length;c++){
        if(meta(headers[c]||''))continue;const v=scoreValue(cells[c]);if(v===null)continue;
        const inCell=cellCandidate(cells[c]);const name=inCell||headers[c];if(!name||meta(name))continue;
        candidates.push({name:clean(name),value:v});
      }
      const uniq=[];const seen=new Set();for(const x of candidates){const k=norm(x.name);if(k&& !seen.has(k)){seen.add(k);uniq.push(x);}}
      if(uniq.length>=3)polls.push({pollster,sample_size:sample,candidates:uniq});
    }
  }
  return polls;
}
function canon(s){return norm(s).replace(/\b(mme|monsieur|madame)\b/g,'').trim();}
function consistentScenario(polls){
  const groups=new Map();polls.slice(0,40).forEach((p,index)=>{const ids=p.candidates.map(c=>canon(c.name)).filter(Boolean).sort();if(ids.length<3)return;const key=ids.join('|');const g=groups.get(key)||{rows:[],first:index};g.rows.push(p);groups.set(key,g);});
  const ranked=[...groups.values()].filter(g=>g.rows.length>=2).sort((a,b)=>b.rows.length-a.rows.length||a.first-b.first);return ranked[0]?.rows||[];
}
function aggregate(polls){
  const by=new Map();polls.forEach((p,i)=>{const w=Math.exp(-i/9)*clamp(p.sample_size?Math.sqrt(p.sample_size/1000):1,.7,1.7);p.candidates.forEach(c=>{const k=canon(c.name);const x=by.get(k)||{candidate:c.name,sum:0,w:0,vals:[]};x.sum+=c.value*w;x.w+=w;x.vals.push(c.value);by.set(k,x);});});
  return [...by.entries()].map(([key,x])=>{const mean=x.sum/x.w;const variance=x.vals.length>1?x.vals.reduce((s,v)=>s+(v-mean)**2,0)/(x.vals.length-1):9;return {key,candidate:x.candidate,poll_average:mean,sd:Math.sqrt(Math.max(1,variance))};}).sort((a,b)=>b.poll_average-a.poll_average);
}
function rng(seed){let a=seed>>>0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}
function gauss(r){let u=0,v=0;while(!u)u=r();while(!v)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}
function simulate(rows,iterations=8000){
  if(rows.length<3)return null;const r=rng(20270905);const q=new Map(rows.map(x=>[x.key,0])),pairs=new Map();
  const months=Math.max(0,(Date.UTC(2027,3,11)-Date.now())/(864e5*30.44));const floor=clamp(2.4+months*.22,2.6,5.8);
  for(let i=0;i<iterations;i++){
    const common=gauss(r)*.6;const d=rows.map(x=>({...x,draw:Math.max(.05,x.poll_average+common+gauss(r)*Math.sqrt(floor*floor+x.sd*x.sd*.3))})).sort((a,b)=>b.draw-a.draw);q.set(d[0].key,q.get(d[0].key)+1);q.set(d[1].key,q.get(d[1].key)+1);const key=[d[0].key,d[1].key].sort().join('|');pairs.set(key,(pairs.get(key)||0)+1);
  }
  const candidates=rows.map(x=>({...x,qualification_probability:round((q.get(x.key)||0)/iterations*100,1)})).sort((a,b)=>b.qualification_probability-a.qualification_probability);
  const pairRows=[...pairs.entries()].map(([key,n])=>{const ids=key.split('|'),names=ids.map(id=>rows.find(x=>x.key===id)?.candidate||id);return {title:`Second tour : ${names.join(' / ')}`,probability_percent:round(n/iterations*100,1),names};}).sort((a,b)=>b.probability_percent-a.probability_percent).slice(0,5);
  return {iterations,candidates,pairs:pairRows};
}
async function macroContext(){
  const indicators=[['FP.CPI.TOTL.ZG','inflation'],['SL.UEM.TOTL.ZS','chômage'],['NY.GDP.MKTP.KD.ZG','croissance']];const out=[];
  for(const [code,label] of indicators){try{const r=await nativeFetch(`https://api.worldbank.org/v2/country/FRA/indicator/${code}?format=json&per_page=4`,{cache:'no-store'});if(!r.ok)continue;const j=await r.json();const row=(j?.[1]||[]).find(x=>Number.isFinite(Number(x?.value)));if(row)out.push({label,value:Number(row.value),year:row.date});}catch{}}
  return out;
}
async function browserElection(question){
  const u=new URL('https://fr.wikipedia.org/w/api.php');u.searchParams.set('action','parse');u.searchParams.set('format','json');u.searchParams.set('prop','text');u.searchParams.set('page',"Liste de sondages sur l'élection présidentielle française de 2027");u.searchParams.set('origin','*');
  let polls=[];try{const r=await nativeFetch(u,{cache:'no-store'});if(r.ok){const j=await r.json();polls=parsePollTables(j?.parse?.text?.['*']||'');}}catch{}
  const scenario=consistentScenario(polls);const averages=aggregate(scenario);const sim=simulate(averages);const macro=await macroContext();
  if(!sim){
    const m=macro.map(x=>`${x.label} ${round(x.value,1)}% (${x.year})`).join(' · ');
    return {schema:'providence-quantic-dynamic-forecast-v1',status:'degraded',provider:'browser_quantic',research:{sources_ok:(polls.length?1:0)+(macro.length?1:0),sources_attempted:2,coverage_score:polls.length?48:24,evidence:[{label:'Sondages publics 2027',status:polls.length?'partial':'unavailable'},{label:'Banque mondiale · France',status:macro.length?'ok':'unavailable'}]},estimate:{probability_percent:null},superposition:{schema:'providence-browser-superposition-v1',consensus:{interpretation:'scénarios exploratoires — données électorales insuffisamment structurées'},semantics:{world_weights_are_event_probabilities:false},worlds:[]},election_model:{status:'insufficient_poll_structure'},browser_text:`J’ai bien lancé la recherche Quantic depuis le navigateur. Les données macroéconomiques publiques sont accessibles${m?` (${m})`:''}, mais les tableaux de sondages n’ont pas pu être structurés avec assez de fiabilité pour publier une probabilité électorale. Je préfère ne pas inventer de chiffres. Le backend Node complet reste nécessaire pour la calibration historique et les effets institut.`};
  }
  const top=sim.candidates.slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — qualification au second tour ${x.qualification_probability}% · moyenne de l’hypothèse suivie ${round(x.poll_average,1)}%`).join('\n');
  const pairs=sim.pairs.slice(0,4).map((x,i)=>`${i+1}. ${x.title} — ${x.probability_percent}%`).join('\n');const m=macro.map(x=>`${x.label} ${round(x.value,1)}% (${x.year})`).join(' · ');
  const worlds=sim.pairs.slice(0,4).map((x,i)=>({world_id:`browser_election_${i}`,title:x.title,relative_world_weight_percent:x.probability_percent,probability_kind:'model_probability_of_second_round_configuration',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France'}));
  return {schema:'providence-quantic-dynamic-forecast-v1',status:'ok',provider:'browser_quantic_election',research:{sources_ok:1+(macro.length?1:0),sources_attempted:2,coverage_score:Math.min(72,48+scenario.length*2),evidence:[{label:'Sondages publics · Présidentielle 2027',status:'ok'},{label:'Banque mondiale · France',status:macro.length?'ok':'unavailable'}]},estimate:{probability_percent:null},election_model:{schema:'providence-election-model-browser-v1',status:'ok',methodology:{monte_carlo_iterations:sim.iterations},first_round:{candidates:sim.candidates,pair_scenarios:sim.pairs},quality:{score:Math.min(78,45+scenario.length*4)}},superposition:{schema:'providence-election-superposition-browser-v1',consensus:{interpretation:'configurations de second tour simulées'},semantics:{world_weights_are_event_probabilities:true,world_probability_kind:'model_probability_of_second_round_configuration'},worlds},browser_text:`Election Model navigateur · ${sim.iterations} simulations sur une hypothèse de candidature cohérente extraite des sondages publics.\n\nQualification au second tour :\n${top}\n\nConfigurations principales :\n${pairs}${m?`\n\nContexte macro disponible : ${m}.`:''}\n\nLes données macro, banques, médias et lobbying ne modifient pas directement les scores sans calibration historique.`};
}
function analystFromDynamic(d){return {schema:'providence-analyst-response-v1',status:'ok',provider:d?.election_model?.status==='ok'?'quantic_election_browser':'quantic_dynamic_browser',text:d?.browser_text||'Recherche Quantic terminée.',superposition:d?.superposition||null,dynamic_forecast:d,election_model:d?.election_model||null,execution_authority:false};}

window.fetch=async function(input,options={}){
  const url=requestUrl(input);if(!url)return nativeFetch(input,options);const path=url.pathname;
  if(path==='/api/analyst/chat'){
    let first=null,err=null;try{first=await nativeFetch(input,options);if(first.ok)return first;}catch(e){err=e;}
    const q=String(bodyOf(options).message||'');
    if(isSignalPrompt(q))return response(await signalAnswer());
    if(isElection(q))return response(analystFromDynamic(await browserElection(q)));
    if(first)return first;throw err||new TypeError('fetch failed');
  }
  if(path==='/api/dynamic-forecast'){
    let first=null,err=null;try{first=await nativeFetch(input,options);if(first.ok)return first;}catch(e){err=e;}
    const q=String(bodyOf(options).question||bodyOf(options).message||'');if(isElection(q))return response(await browserElection(q));if(first)return first;throw err||new TypeError('fetch failed');
  }
  return nativeFetch(input,options);
};
window.__PROVIDENCE_RUNTIME_BRIDGE__={version:'16.19',mode:'hostinger-public-resilience'};
})();