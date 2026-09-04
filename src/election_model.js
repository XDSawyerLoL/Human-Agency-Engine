const UA='Providence-Election-Model/1.0';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=2)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const clean=v=>String(v??'').replace(/\s+/g,' ').trim();
const norm=v=>clean(v).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const stripHtml=value=>clean(String(value||'').replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<sup[\s\S]*?<\/sup>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&#39;/g,"'").replace(/&quot;/g,'"').replace(/&[a-z]+;/gi,' '));
const parsePct=v=>{const m=clean(v).match(/(?:^|\s)(\d{1,2}(?:[.,]\d+)?)\s*%/);return m?Number(m[1].replace(',','.')):null};
const likelyMeta=s=>/(date|sondeur|institut|echantillon|échantillon|hypothese|hypothèse|terrain|commanditaire|source|marge|participation|abstention|indecis|indécis|aucun|autre)/i.test(s);
const candidateName=s=>clean(s).replace(/\[[^\]]+\]/g,'').replace(/\([^)]*(?:parti|ensemble|rn|lfi|lr|ps|eelv|reconquete|reconquête)[^)]*\)/ig,'').trim();

async function fetchJson(url,{timeoutMs=9000}={}){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{const r=await fetch(url,{signal:controller.signal,headers:{accept:'application/json','user-agent':UA}});if(!r.ok)throw new Error(`HTTP ${r.status}`);return await r.json();}finally{clearTimeout(timer);}
}

function tableRows(html){
  return (String(html||'').match(/<table[\s\S]*?<\/table>/gi)||[]).map((table,tableIndex)=>{
    const rawRows=table.match(/<tr[\s\S]*?<\/tr>/gi)||[];
    return {tableIndex,rows:rawRows.map(row=>({cells:(row.match(/<(?:td|th)[\s\S]*?<\/(?:td|th)>/gi)||[]).map(stripHtml)})).filter(r=>r.cells.length)};
  });
}

function bestHeaders(rows,dataIndex){
  const candidates=[];
  for(let i=Math.max(0,dataIndex-4);i<dataIndex;i++){
    const cells=rows[i]?.cells||[];
    const score=cells.filter(c=>!likelyMeta(c)&&!parsePct(c)&&candidateName(c).length>=3&&candidateName(c).length<=42).length;
    if(score>=2)candidates.push({cells,score,i});
  }
  return candidates.sort((a,b)=>b.score-a.score||b.i-a.i)[0]?.cells||[];
}
function extractSampleSize(cells){
  const nums=cells.flatMap(c=>[...(String(c).matchAll(/\b(\d{3,5})\b/g))].map(m=>Number(m[1]))).filter(n=>n>=300&&n<=30000);
  return nums[0]||null;
}
function extractPollster(cells){
  return cells.find(c=>/ifop|ipsos|bva|elabe|harris|odoxa|cluster17|opinionway|verian|kantar|toluna|yougov|csa|institut/i.test(c))||cells.find(c=>c.length>=3&&c.length<=40&&!parsePct(c)&&!likelyMeta(c))||'Institut non identifié';
}
function alignCandidateColumns(headers,cells){
  const pctCells=cells.map((c,i)=>({i,p:parsePct(c)})).filter(x=>Number.isFinite(x.p));
  if(pctCells.length<2)return null;
  const pairs=[];
  for(const x of pctCells){
    const h=headers[x.i];
    if(h&&!likelyMeta(h)){const name=candidateName(h);if(name.length>=2)pairs.push({name,value:x.p});}
  }
  if(pairs.length>=2)return pairs;
  const candidateHeaders=headers.filter(h=>!likelyMeta(h)&&!parsePct(h)).map(candidateName).filter(x=>x.length>=2&&x.length<=42);
  if(candidateHeaders.length>=pctCells.length){
    const tail=candidateHeaders.slice(-pctCells.length);return tail.map((name,i)=>({name,value:pctCells[i].p}));
  }
  return null;
}

export function parseElectionPollingHtml(html){
  const polls=[];const matchups=[];
  for(const table of tableRows(html)){
    const dataIndex=table.rows.findIndex(r=>r.cells.filter(c=>Number.isFinite(parsePct(c))).length>=2);
    if(dataIndex<0)continue;
    const headers=bestHeaders(table.rows,dataIndex);
    for(let ri=dataIndex;ri<table.rows.length;ri++){
      const cells=table.rows[ri].cells;const pairs=alignCandidateColumns(headers,cells);if(!pairs||pairs.length<2)continue;
      const poll={table_index:table.tableIndex,row_index:ri,pollster:extractPollster(cells),sample_size:extractSampleSize(cells),candidates:pairs};
      if(pairs.length===2)matchups.push(poll);else polls.push(poll);
    }
  }
  return {polls,matchups,tables:tableRows(html).length};
}

function canonicalName(name){return norm(name).replace(/\b(mme|m|monsieur|madame)\b/g,'').trim();}
function candidateCatalog(polls){
  const map=new Map();
  for(const p of polls)for(const c of p.candidates){const k=canonicalName(c.name);if(k.length<2)continue;const old=map.get(k)||{key:k,name:c.name,count:0};old.count++;if(c.name.length>old.name.length)old.name=c.name;map.set(k,old);}
  return [...map.values()].filter(x=>x.count>=2).sort((a,b)=>b.count-a.count);
}
function recencyWeight(index){return Math.exp(-index/11);}
function sampleWeight(n){return n?clamp(Math.sqrt(n/1000),.65,1.8):1;}

function weightedAverages(polls,catalog){
  const by=new Map(catalog.map(c=>[c.key,{...c,sum:0,w:0,values:[],pollsters:new Set()}]));
  polls.forEach((p,index)=>{
    const rw=recencyWeight(index),sw=sampleWeight(p.sample_size),base=rw*sw;
    for(const c of p.candidates){const row=by.get(canonicalName(c.name));if(!row)continue;row.sum+=c.value*base;row.w+=base;row.values.push(c.value);row.pollsters.add(p.pollster);}
  });
  return [...by.values()].filter(x=>x.w>0).map(x=>{
    const mean=x.sum/x.w;const variance=x.values.length>1?x.values.reduce((s,v)=>s+(v-mean)**2,0)/(x.values.length-1):9;const sd=Math.sqrt(Math.max(variance,1));
    return {candidate_key:x.key,candidate:x.name,poll_average:round(mean,2),poll_sd:round(sd,2),observations:x.values.length,pollsters:x.pollsters.size};
  }).sort((a,b)=>b.poll_average-a.poll_average);
}

function mulberry32(seed){return function(){let t=seed+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;}}
function seedFrom(s){let h=2166136261;for(const c of String(s)){h^=c.charCodeAt(0);h=Math.imul(h,16777619);}return h>>>0;}
function normal(rng){let u=0,v=0;while(!u)u=rng();while(!v)v=rng();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}

function simulateFirstRound(rows,{iterations=18000,monthsToElection=7,seed='providence-election'}={}){
  if(rows.length<3)return null;
  const rng=mulberry32(seedFrom(seed));const qualify=new Map(rows.map(r=>[r.candidate_key,0]));const pairs=new Map();
  const uncertaintyFloor=clamp(2.2+monthsToElection*.22,2.4,5.8);
  for(let it=0;it<iterations;it++){
    const national=normal(rng)*.65;
    const draws=rows.map(r=>{const empirical=clamp(Number(r.poll_sd)||3,1.4,6);const sigma=Math.sqrt(uncertaintyFloor**2+empirical**2*.35);return {...r,draw:Math.max(.05,r.poll_average+national+normal(rng)*sigma)};});
    const sum=draws.reduce((s,x)=>s+x.draw,0)||1;for(const d of draws)d.draw=d.draw/sum*100;
    draws.sort((a,b)=>b.draw-a.draw);const a=draws[0],b=draws[1];qualify.set(a.candidate_key,qualify.get(a.candidate_key)+1);qualify.set(b.candidate_key,qualify.get(b.candidate_key)+1);
    const key=[a.candidate_key,b.candidate_key].sort().join('|');pairs.set(key,(pairs.get(key)||0)+1);
  }
  const candidates=rows.map(r=>({...r,qualification_probability:round((qualify.get(r.candidate_key)||0)/iterations*100,1)})).sort((a,b)=>b.qualification_probability-a.qualification_probability);
  const pairRows=[...pairs.entries()].map(([key,n])=>{const ids=key.split('|');const names=ids.map(id=>rows.find(r=>r.candidate_key===id)?.candidate||id);return {scenario_key:`second-round:${key}`,title:`Second tour : ${names.join(' / ')}`,candidates:names,probability_percent:round(n/iterations*100,1)};}).sort((a,b)=>b.probability_percent-a.probability_percent).slice(0,6);
  return {iterations,uncertainty_floor_points:round(uncertaintyFloor,2),candidates,pair_scenarios:pairRows};
}

function aggregateHeadToHead(matchups){
  const groups=new Map();
  for(const p of matchups){const names=p.candidates.map(c=>canonicalName(c.name));if(names.length!==2)continue;const key=[...names].sort().join('|');const g=groups.get(key)||{rows:[],display:new Map()};g.rows.push(p);p.candidates.forEach(c=>g.display.set(canonicalName(c.name),c.name));groups.set(key,g);}
  return [...groups.entries()].map(([key,g])=>{
    if(g.rows.length<2)return null;const ids=key.split('|');const accum=new Map(ids.map(id=>[id,{sum:0,w:0}]));g.rows.forEach((p,i)=>{const w=recencyWeight(i)*sampleWeight(p.sample_size);p.candidates.forEach(c=>{const a=accum.get(canonicalName(c.name));if(a){a.sum+=c.value*w;a.w+=w;}});});
    const scores=ids.map(id=>({candidate:g.display.get(id)||id,score:accum.get(id).w?accum.get(id).sum/accum.get(id).w:null})).filter(x=>Number.isFinite(x.score));if(scores.length!==2)return null;
    const diff=scores[0].score-scores[1].score;const sigma=3.2;const p=1/(1+Math.exp(-diff/(sigma*.78)));
    return {matchup:scores.map(x=>x.candidate),poll_average:scores.map(x=>({candidate:x.candidate,percent:round(x.score,1)})),model_win_probability:[{candidate:scores[0].candidate,percent:round(p*100,1)},{candidate:scores[1].candidate,percent:round((1-p)*100,1)}],polls:g.rows.length,method:'weighted head-to-head polling with conservative uncertainty'};
  }).filter(Boolean).sort((a,b)=>b.polls-a.polls).slice(0,8);
}

async function fetchFrench2027Polling(){
  const page="Liste de sondages sur l'élection présidentielle française de 2027";const u=new URL('https://fr.wikipedia.org/w/api.php');u.searchParams.set('action','parse');u.searchParams.set('format','json');u.searchParams.set('prop','text');u.searchParams.set('page',page);u.searchParams.set('origin','*');
  const data=await fetchJson(u);const html=data?.parse?.text?.['*']||'';return {url:`https://fr.wikipedia.org/wiki/Liste_de_sondages_sur_l%27élection_présidentielle_française_de_2027`,...parseElectionPollingHtml(html)};
}

export function isFrench2027ElectionQuestion(question){const q=norm(question);return q.includes('france')&&q.includes('2027')&&/(election|president|scrutin|vote)/.test(q);}

export async function buildElectionModel(question,{now=Date.now()}={}){
  if(!isFrench2027ElectionQuestion(question))return null;
  const generatedAt=new Date(now).toISOString();let polling;
  try{polling=await fetchFrench2027Polling();}catch(error){return {schema:'providence-election-model-v1',status:'degraded',generated_at:generatedAt,election:'Présidentielle française 2027',error:String(error?.message||error),numeric_model_available:false,guardrails:{polls_are_not_votes:true,lobbying_not_direct_vote_shift:true,macro_context_not_direct_vote_shift:true}};}
  const catalog=candidateCatalog(polling.polls);const averages=weightedAverages(polling.polls,catalog);
  const electionDate=Date.UTC(2027,3,11);const monthsToElection=Math.max(0,(electionDate-Number(now))/(86400000*30.44));
  const simulation=simulateFirstRound(averages,{monthsToElection,seed:`france-2027|${polling.polls.length}|${generatedAt.slice(0,10)}`});
  const headToHead=aggregateHeadToHead(polling.matchups);
  const structured=Boolean(simulation&&averages.length>=3&&polling.polls.length>=4);
  const quality=clamp(Math.round(20+Math.min(35,polling.polls.length*1.2)+Math.min(20,new Set(polling.polls.map(p=>p.pollster)).size*3)+Math.min(15,averages.length*2)),0,90);
  return {
    schema:'providence-election-model-v1',status:structured?'ok':'insufficient_poll_structure',generated_at:generatedAt,election:'Présidentielle française 2027',country:'France',year:2027,
    source:{label:'Sondages publics agrégés',url:polling.url,poll_rows:polling.polls.length,head_to_head_rows:polling.matchups.length,tables:polling.tables},
    methodology:{poll_weighting:['récence','taille d’échantillon lorsqu’elle est disponible'],house_effects:'non appliqués tant qu’un historique institut suffisamment fiable n’est pas chargé',historical_election_calibration:'architecture prête, correction chiffrée non appliquée sans corpus validé',monte_carlo_iterations:simulation?.iterations||0,uncertainty_floor_points:simulation?.uncertainty_floor_points||null},
    first_round:simulation?{candidates:simulation.candidates,pair_scenarios:simulation.pair_scenarios}:null,
    second_round:headToHead,
    quality:{score:quality,structured_polling:structured,candidate_count:averages.length,pollsters:new Set(polling.polls.map(p=>p.pollster)).size,months_to_election:round(monthsToElection,1)},
    temporal_branches:(simulation?.pair_scenarios||[]).slice(0,4).map((s,i)=>({world_id:`election_${i+1}`,scenario_key:s.scenario_key,title:s.title,relative_world_weight_percent:s.probability_percent,probability_kind:'model_probability_of_second_round_configuration',dynamic_research:true,horizon_label:'Présidentielle 2027',region:'France'})),
    guardrails:{polls_are_not_votes:true,lobbying_not_direct_vote_shift:true,macro_context_not_direct_vote_shift:true,banking_context_not_direct_vote_shift:true,candidate_win_probability_requires_head_to_head_data:true,first_round_qualification_is_model_probability:true},
    limitations:['Les candidatures définitives peuvent ne pas être connues.','Les sondages mesurent un état de l’opinion, pas le vote final.','Les reports de voix, la participation et les événements de campagne ne sont pas encore entièrement calibrés.','Aucun effet causal de lobbying, banque ou média n’est ajouté sans validation historique.']
  };
}
