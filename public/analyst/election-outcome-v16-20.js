(()=>{'use strict';
const prev=window.fetch.bind(window);
const clean=v=>String(v??'').replace(/\s+/g,' ').trim();
const norm=v=>clean(v).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=1)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const canon=s=>norm(s).replace(/\b(mme|m|monsieur|madame)\b/g,'').trim();
const isElection=q=>{const x=norm(q);return x.includes('france')&&x.includes('2027')&&/(election|president|scrutin|vote)/.test(x)};
const reqUrl=input=>{try{return new URL(typeof input==='string'?input:input?.url,location.href)}catch{return null}};
const bodyOf=options=>{try{return JSON.parse(String(options?.body||'{}'))}catch{return {}}};
const response=data=>new Response(JSON.stringify(data),{status:200,headers:{'content-type':'application/json;charset=utf-8','cache-control':'no-store'}});

function grid(table){
  const out=[],carry=[];
  for(const tr of [...table.rows]){
    const row=[];for(let c=0;c<carry.length;c++)if(carry[c]?.left>0){row[c]=carry[c].text;carry[c].left--;}
    let col=0;for(const cell of [...tr.cells]){while(row[col]!==undefined)col++;const text=clean(cell.textContent),cs=Math.max(1,Number(cell.colSpan)||1),rs=Math.max(1,Number(cell.rowSpan)||1);for(let k=0;k<cs;k++){row[col+k]=text;if(rs>1)carry[col+k]={text,left:rs-1};}col+=cs;}
    if(row.length)out.push(row);
  }
  return out;
}
const meta=s=>/(sondeur|institut|date|echantillon|échantillon|autres?|marge|hypoth|terrain|commanditaire|participation|abstention|source)/i.test(String(s||''));
function scoreValue(text){const s=clean(text);if(!s||/^[-—–]$/.test(s))return null;if(/^<\s*1(?:\s*%)?$/.test(s))return .5;const m=s.match(/^(\d{1,2}(?:[.,]\d+)?)\s*%?$/);if(!m)return null;const n=Number(m[1].replace(',','.'));return n>=0&&n<=100?n:null;}
function headerName(text){let s=clean(text).replace(/\([^)]*\)/g,' ').replace(/^candidat(?:e)?\s+/i,'').trim();if(!s||meta(s)||/^(lo|lfi|pcf|ps|pp|epr|lr|lfh|dlf|rn|rec|le)$/i.test(s))return null;return /[A-Za-zÀ-ÿ]{3}/.test(s)?s:null;}
function recencyWeight(i){return Math.exp(-i/9)}
function sampleWeight(n){return n?clamp(Math.sqrt(n/1000),.7,1.7):1}

function parseDuels(html){
  const doc=new DOMParser().parseFromString(html,'text/html'),duels=[];
  for(const table of [...doc.querySelectorAll('table.wikitable')].slice(0,30)){
    const rows=grid(table);if(rows.length<3)continue;
    const dataStart=rows.findIndex(r=>r.filter(x=>scoreValue(x)!==null).length>=2);if(dataStart<0)continue;
    const colCount=Math.max(...rows.map(r=>r.length));const headers=[];
    for(let c=0;c<colCount;c++){let h=null;for(let r=Math.max(0,dataStart-4);r<dataStart;r++){const x=headerName(rows[r]?.[c]);if(x)h=x;}headers[c]=h;}
    for(let r=dataStart;r<rows.length;r++){
      const cells=rows[r],pairs=[];for(let c=0;c<cells.length;c++){const v=scoreValue(cells[c]),name=headers[c];if(v===null||!name||meta(name))continue;pairs.push({candidate:name,value:v});}
      const uniq=[];const seen=new Set();for(const p of pairs){const k=canon(p.candidate);if(k&&!seen.has(k)){seen.add(k);uniq.push(p);}}
      if(uniq.length!==2)continue;const total=uniq[0].value+uniq[1].value;if(total<70||total>110)continue;
      const sample=cells.flatMap(x=>[...(String(x||'').matchAll(/\b(\d{3,5})\b/g))].map(m=>Number(m[1]))).find(n=>n>=300&&n<=30000)||null;
      duels.push({sample,candidates:uniq});
    }
  }
  return duels;
}

function aggregateDuels(rows){
  const groups=new Map();for(const row of rows){const key=row.candidates.map(x=>canon(x.candidate)).sort().join('|');const g=groups.get(key)||[];g.push(row);groups.set(key,g);}
  const out=new Map();
  for(const [key,g] of groups){if(g.length<2)continue;const ids=key.split('|'),acc=new Map(ids.map(id=>[id,{sum:0,w:0,name:id}]));g.forEach((row,i)=>{const w=recencyWeight(i)*sampleWeight(row.sample);row.candidates.forEach(c=>{const a=acc.get(canon(c.candidate));if(a){a.sum+=c.value*w;a.w+=w;a.name=c.candidate;}});});const scores=ids.map(id=>{const a=acc.get(id);return {candidate:a.name,score:a.w?a.sum/a.w:null};}).filter(x=>Number.isFinite(x.score));if(scores.length!==2)continue;const diff=scores[0].score-scores[1].score,p=1/(1+Math.exp(-diff/(3.2*.78)));out.set(key,{polls:g.length,probabilities:[{candidate:scores[0].candidate,percent:p*100},{candidate:scores[1].candidate,percent:(1-p)*100}]});}
  return out;
}

async function fetchH2H(){
  const u=new URL('https://fr.wikipedia.org/w/api.php');u.searchParams.set('action','parse');u.searchParams.set('format','json');u.searchParams.set('prop','text');u.searchParams.set('page',"Liste de sondages sur l'élection présidentielle française de 2027");u.searchParams.set('origin','*');
  const r=await prev(u,{cache:'no-store'});if(!r.ok)throw new Error(`polling_${r.status}`);const j=await r.json();return aggregateDuels(parseDuels(j?.parse?.text?.['*']||''));
}

function outcome(model,duels){
  const pairs=model?.first_round?.pair_scenarios||model?.first_round?.pairs||[];const wins=new Map();let covered=0,total=0;const unresolved=[];
  for(const pair of pairs){const pp=clamp(Number(pair.probability_percent),0,100)/100;if(!pp)continue;total+=pp;const names=pair.candidates||pair.names||[];const key=names.map(canon).sort().join('|'),duel=duels.get(key);if(!duel){unresolved.push({title:pair.title,probability_percent:round(pp*100)});continue;}covered+=pp;for(const p of duel.probabilities){const contribution=pp*(p.percent/100);const k=canon(p.candidate),x=wins.get(k)||{candidate:p.candidate,value:0};x.value+=contribution;wins.set(k,x);}}
  const candidates=[...wins.values()].map(x=>({candidate:x.candidate,win_probability_percent:round(x.value*100)})).sort((a,b)=>b.win_probability_percent-a.win_probability_percent);const coverage=round(covered/Math.max(.0001,total)*100),unresolvedMass=round(Math.max(0,total-covered)*100);
  return {status:covered>=.55&&candidates.length>=2?'publishable':'partial',coverage_percent:coverage,unresolved_probability_mass_percent:unresolvedMass,candidates,winner:candidates[0]||null,unresolved};
}

async function enhance(data){
  const model=data?.election_model;if(!model||data?.election_deduction?.final_outcome)return data;
  let final;try{final=outcome(model,await fetchH2H())}catch{return data;}
  data.election_deduction={schema:'providence-election-deduction-browser-v1',status:'ok',final_outcome:final,deductions:[{key:'browser_final',statement:final.status==='publishable'?`Le résultat final combine chaque configuration de second tour avec les duels structurés disponibles. Couverture ${final.coverage_percent}%.`:`Les duels structurés ne couvrent encore que ${final.coverage_percent}% des configurations ; Providence ne redistribue pas la masse non résolue.`}],guardrails:{unresolved_probability_mass_not_redistributed:true,context_never_becomes_candidate_bonus_without_calibration:true}};
  if(final.status==='publishable'){
    const ranking=final.candidates.slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — victoire finale ${x.win_probability_percent}%`).join('\n');
    data.text=`${clean(data.text)}\n\nRésultat final simulé :\n${ranking}\nMasse non résolue : ${final.unresolved_probability_mass_percent}% · couverture : ${final.coverage_percent}%.\n\nCette étape assemble les probabilités de configuration du second tour et les probabilités conditionnelles issues des duels ; elle ne transforme pas l’économie, les médias ou le lobbying en points électoraux sans calibration.`;
    const worlds=final.candidates.slice(0,5).map((x,i)=>({world_id:`browser_final_${i}`,title:`Victoire finale : ${x.candidate}`,relative_world_weight_percent:x.win_probability_percent,forecast_probability_percent:x.win_probability_percent,probability_kind:'model_probability_of_final_election_win',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France'}));if(final.unresolved_probability_mass_percent>0)worlds.push({world_id:'browser_final_unresolved',title:'Issue non résolue',relative_world_weight_percent:final.unresolved_probability_mass_percent,probability_kind:'unresolved_probability_mass',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France'});data.superposition={schema:'providence-election-superposition-browser-v2',consensus:{interpretation:`résultat final · couverture ${final.coverage_percent}%`},semantics:{world_weights_are_event_probabilities:true,unresolved_mass_is_not_redistributed:true},worlds};
  }
  return data;
}

window.fetch=async function(input,options={}){
  const url=reqUrl(input),r=await prev(input,options);if(!url||!['/api/analyst/chat','/api/dynamic-forecast','/api/election-model'].includes(url.pathname)||!r.ok)return r;
  const q=String(bodyOf(options).message||bodyOf(options).question||'');if(!isElection(q))return r;
  try{const data=await r.clone().json();return response(await enhance(data));}catch{return r;}
};
window.__PROVIDENCE_ELECTION_OUTCOME__={version:'16.20',mode:'final-result-fallback'};
})();