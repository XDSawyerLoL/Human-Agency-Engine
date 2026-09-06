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

async function fetchMacro(){
  const defs=[['FP.CPI.TOTL.ZG','Inflation'],['SL.UEM.TOTL.ZS','Chômage'],['NY.GDP.MKTP.KD.ZG','Croissance du PIB']];const rows=[];
  for(const [code,label] of defs){try{const r=await prev(`https://api.worldbank.org/v2/country/FRA/indicator/${code}?format=json&per_page=6`,{cache:'no-store'});if(!r.ok)continue;const j=await r.json();const vals=(j?.[1]||[]).filter(x=>Number.isFinite(Number(x?.value)));if(vals.length){const a=vals[0],b=vals[1];rows.push({code,label,value:Number(a.value),year:a.date,delta:b?Number(a.value)-Number(b.value):null});}}catch{}}
  return rows;
}
function situational(model,macro=[]){
  const rows=model?.first_round?.candidates||[],ded=[];const a=rows[0],b=rows[1],c=rows[2];
  if(Number(a?.qualification_probability)>=90)ded.push({id:'browser:first-slot-lock',label:'Première place de qualification relativement verrouillée',confidence:.82,statement:`${a.candidate} est très fortement installé dans les simulations de qualification ; l’incertitude se déplace surtout vers la seconde place.`});
  if(b&&c){const gap=Math.abs(Number(b.qualification_probability)-Number(c.qualification_probability));if(gap<=20)ded.push({id:'browser:second-slot-contest',label:'Course ouverte pour la seconde qualification',confidence:clamp(.8-gap/100,.5,.8),statement:`L’écart de qualification entre ${b.candidate} et ${c.candidate} reste assez faible pour que des événements de campagne puissent modifier le second tour.`});}
  const stress=macro.filter(x=>(x.label==='Inflation'||x.label==='Chômage')&&Number(x.delta)>.1).length+(macro.filter(x=>x.label==='Croissance du PIB'&&Number(x.delta)<-.2).length);
  if(stress>=2)ded.push({id:'browser:macro-stress',label:'Pression macroéconomique convergente',confidence:.62,statement:'Plusieurs indicateurs macro se dégradent simultanément. Providence augmente donc l’incertitude et le poids des scénarios de recomposition, sans attribuer de bonus direct à un candidat.'});
  const quality=clamp(Math.round(38+ded.length*12+Math.min(18,macro.length*6)),0,82);
  return {schema:'providence-situational-inference-browser-v1',status:ded.length?'active':'collecting',facts:macro,deductions:ded,quality:{score:quality},semantics:{deductions_are_observations:false,deductions_are_causal_proof:false,canonical_probabilities_changed:false}};
}

function directOutcome(model,duels){
  const pairs=model?.first_round?.pair_scenarios||model?.first_round?.pairs||[];const wins=new Map();let covered=0,total=0;const unresolved=[];
  for(const pair of pairs){const pp=clamp(Number(pair.probability_percent),0,100)/100;if(!pp)continue;total+=pp;const names=pair.candidates||pair.names||[];const key=names.map(canon).sort().join('|'),duel=duels.get(key);if(!duel){unresolved.push({title:pair.title,probability_percent:round(pp*100)});continue;}covered+=pp;for(const p of duel.probabilities){const contribution=pp*(p.percent/100);const k=canon(p.candidate),x=wins.get(k)||{candidate:p.candidate,value:0};x.value+=contribution;wins.set(k,x);}}
  const candidates=[...wins.values()].map(x=>({candidate:x.candidate,win_probability_percent:round(x.value*100)})).sort((a,b)=>b.win_probability_percent-a.win_probability_percent);const coverage=round(covered/Math.max(.0001,total)*100),unresolvedMass=round(Math.max(0,total-covered)*100);
  return {status:covered>=.55&&candidates.length>=2?'publishable':'partial',coverage_percent:coverage,unresolved_probability_mass_percent:unresolvedMass,candidates,winner:candidates[0]||null,unresolved};
}
function conservativePair(names,first){
  const A=first.get(canon(names[0])),B=first.get(canon(names[1]));const pa=Number(A?.poll_average),pb=Number(B?.poll_average);if(!Number.isFinite(pa)||!Number.isFinite(pb))return[{candidate:names[0],percent:50},{candidate:names[1],percent:50}];const lean=Math.tanh((pa-pb)/12)*10;return[{candidate:names[0],percent:clamp(50+lean,38,62)},{candidate:names[1],percent:clamp(50-lean,38,62)}];
}
function inferredProjection(model,duels,situation){
  const pairs=model?.first_round?.pair_scenarios||[],first=new Map((model?.first_round?.candidates||[]).map(x=>[canon(x.candidate),x])),wins=new Map();let directMass=0,total=0;const paths=[];
  for(const pair of pairs){const pp=clamp(Number(pair.probability_percent),0,100);if(!pp)continue;total+=pp;const names=pair.candidates||[];if(names.length!==2)continue;const direct=duels.get(names.map(canon).sort().join('|'));const probs=direct?direct.probabilities:conservativePair(names,first);if(direct)directMass+=pp;const sum=probs.reduce((s,x)=>s+Number(x.percent||0),0)||100;for(const p of probs){const contribution=pp*(Number(p.percent)/sum);const key=canon(p.candidate),x=wins.get(key)||{candidate:p.candidate,value:0};x.value+=contribution;wins.set(key,x);}paths.push({title:pair.title,configuration_probability_percent:pp,method:direct?'direct_head_to_head':'synthetic_runoff_prior'});}
  const candidates=[...wins.values()].map(x=>({candidate:x.candidate,victory_probability_percent:round(x.value/Math.max(.0001,total)*100,1)})).sort((a,b)=>b.victory_probability_percent-a.victory_probability_percent);const directCoverage=round(directMass/Math.max(.0001,total)*100,1),vol=clamp(6+(100-directCoverage)*.05+(situation?.deductions?.length||0)*.6,6,17);for(const c of candidates)c.interval_percent=[round(Math.max(0,c.victory_probability_percent-vol),1),round(Math.min(100,c.victory_probability_percent+vol),1)];return {schema:'providence-election-outcome-browser-v1',status:candidates.length?'ok':'insufficient',winner_projection:candidates[0]||null,candidates,paths,coverage:{direct_head_to_head_coverage_percent:directCoverage,synthetic_runoff_coverage_percent:round(100-directCoverage,1)},quality:{score:Math.round(clamp(42+directCoverage*.35+Number(situation?.quality?.score||0)*.2,0,88))},semantics:{synthetic_runoff_is_observed_data:false,situational_deductions_are_observed_data:false}};
}

async function enhance(data){
  const model=data?.election_model;if(!model)return data;
  let duels=new Map(),macro=[];try{[duels,macro]=await Promise.all([fetchH2H(),fetchMacro()]);}catch{}
  const situation=data?.situational_inference||situational(model,macro);data.situational_inference=situation;
  let final=data?.election_deduction?.final_outcome||directOutcome(model,duels);
  if(!data.election_deduction)data.election_deduction={schema:'providence-election-deduction-browser-v1',status:'ok',final_outcome:final,deductions:[],guardrails:{unresolved_probability_mass_not_redistributed:true,context_never_becomes_candidate_bonus_without_calibration:true}};
  const projection=data?.election_outcome_projection||inferredProjection(model,duels,situation);data.election_outcome_projection=projection;
  const deductions=situation?.deductions||[];data.election_deduction.deductions=[...(data.election_deduction.deductions||[]),...deductions.map(x=>({key:x.id,statement:x.statement,strength:'inférence'}))];
  let ranking='',worlds=[];
  if(final?.status==='publishable'){
    ranking=final.candidates.slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — victoire finale ${x.win_probability_percent}%`).join('\n');
    worlds=final.candidates.slice(0,5).map((x,i)=>({world_id:`browser_final_${i}`,title:`Victoire finale : ${x.candidate}`,relative_world_weight_percent:x.win_probability_percent,forecast_probability_percent:x.win_probability_percent,probability_kind:'model_probability_of_final_election_win',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France'}));if(final.unresolved_probability_mass_percent>0)worlds.push({world_id:'browser_final_unresolved',title:'Issue non résolue',relative_world_weight_percent:final.unresolved_probability_mass_percent,probability_kind:'unresolved_probability_mass',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France'});
    data.text=`${clean(data.text)}\n\nRésultat final simulé sur les duels documentés :\n${ranking}\nMasse non résolue : ${final.unresolved_probability_mass_percent}% · couverture : ${final.coverage_percent}%.`;
  }else if(projection?.status==='ok'){
    ranking=projection.candidates.slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — projection de victoire ${x.victory_probability_percent}% · intervalle ${x.interval_percent[0]}–${x.interval_percent[1]}%`).join('\n');
    worlds=projection.candidates.slice(0,5).map((x,i)=>({world_id:`browser_projection_${i}`,title:`Victoire finale : ${x.candidate}`,relative_world_weight_percent:x.victory_probability_percent,forecast_probability_percent:x.victory_probability_percent,probability_kind:'derived_model_probability_of_final_election_win',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France',interval_percent:x.interval_percent}));
    data.text=`${clean(data.text)}\n\nProjection du résultat final par assemblage de situations :\n${ranking}\nCouverture directe des duels : ${projection.coverage.direct_head_to_head_coverage_percent}%. Les duels manquants sont ramenés vers 50/50 et bornés 38/62 : cette partie est une déduction prudente, pas un sondage.`;
  }
  if(deductions.length)data.text+=`\n\nDéductions de situation :\n${deductions.slice(0,4).map((x,i)=>`${i+1}. ${x.label} — confiance ${Math.round(Number(x.confidence||0)*100)}%`).join('\n')}\nCes déductions structurent l’incertitude ; elles ne donnent pas automatiquement des points à un candidat.`;
  if(worlds.length)data.superposition={schema:'providence-election-superposition-browser-v3',consensus:{interpretation:final?.status==='publishable'?`résultat final · couverture ${final.coverage_percent}%`:`projection finale déduite · qualité ${projection?.quality?.score||0}/100`},semantics:{world_weights_are_event_probabilities:true,synthetic_runoffs_are_observations:false,situational_deductions_are_observations:false},worlds};
  return data;
}

window.fetch=async function(input,options={}){
  const url=reqUrl(input),r=await prev(input,options);if(!url||!['/api/analyst/chat','/api/dynamic-forecast','/api/election-model'].includes(url.pathname)||!r.ok)return r;
  const q=String(bodyOf(options).message||bodyOf(options).question||'');if(!isElection(q))return r;
  try{const data=await r.clone().json();return response(await enhance(data));}catch{return r;}
};
window.__PROVIDENCE_ELECTION_OUTCOME__={version:'16.20.1',mode:'deductive-final-result-fallback'};
})();