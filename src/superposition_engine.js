const clamp=(n,min=0,max=1)=>Math.max(min,Math.min(max,Number(n)||0));
const pct=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return clamp(p,0,100);const e=Number(f?.probability?.estimate);return Number.isFinite(e)?clamp(e*100,0,100):0};
const confidence=f=>clamp(Number(f?.consolidation?.score??f?.confidence??0),0,100);
const title=f=>String(f?.title||f?.headline||f?.outcome||'Scénario');
const active=f=>!['resolved','invalidated','expired'].includes(String(f?.status||'').toLowerCase());
const providers=f=>Array.isArray(f?.consolidation?.source_providers)?f.consolidation.source_providers:[];
const strongSignals=f=>Array.isArray(f?.signal_convergence?.strong_signals)?f.signal_convergence.strong_signals:[];
const weakSignals=f=>Array.isArray(f?.signal_convergence?.weak_signals)?f.signal_convergence.weak_signals:[];
const contrarySignals=f=>Array.isArray(f?.contrary_signals)?f.contrary_signals:Array.isArray(f?.signal_convergence?.contrary_signals)?f.signal_convergence.contrary_signals:[];
const tokens=s=>new Set(String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').split(/\s+/).filter(x=>x.length>2));
const overlap=(a,b)=>{const A=tokens(a),B=tokens(b);if(!A.size||!B.size)return 0;let n=0;for(const x of A)if(B.has(x))n++;return n/Math.max(1,Math.min(A.size,B.size));};
const latestDelta=f=>{const explicit=Number(f?.probability_delta_points);if(Number.isFinite(explicit))return explicit;const h=Array.isArray(f?.probability_history)?f.probability_history:[];if(h.length<2)return 0;const a=Number(h.at(-2)?.percent),b=Number(h.at(-1)?.percent);return Number.isFinite(a)&&Number.isFinite(b)?b-a:0;};

function supportScore(f){
  const probability=pct(f)/100;
  const proof=confidence(f)/100;
  const sourceBreadth=clamp(providers(f).length/6);
  const strong=clamp(strongSignals(f).length/4);
  const movement=clamp(Math.abs(latestDelta(f))/12);
  const contrary=clamp(contrarySignals(f).length/4);
  return clamp(.42*probability+.26*proof+.14*sourceBreadth+.10*strong+.08*movement-.10*contrary);
}

function relevance(f,query){
  if(!query)return 1;
  const hay=[title(f),f?.summary,f?.public_summary,f?.region,f?.domain,f?.horizon_tier].filter(Boolean).join(' ');
  return overlap(hay,query);
}

function diversify(sorted,limit){
  const out=[];
  for(const item of sorted){
    const duplicate=out.some(x=>x.f.domain===item.f.domain&&String(x.f.region||'')===String(item.f.region||'')&&overlap(title(x.f),title(item.f))>.52);
    if(duplicate&&out.length<Math.max(2,Math.ceil(limit/2)))continue;
    out.push(item);
    if(out.length>=limit)break;
  }
  if(out.length<limit){for(const item of sorted){if(!out.includes(item))out.push(item);if(out.length>=limit)break;}}
  return out;
}

function normalizedWeights(items){
  if(!items.length)return [];
  const exps=items.map(x=>Math.exp((x.support-.5)*3.4));
  const total=exps.reduce((a,b)=>a+b,0)||1;
  const raw=exps.map(x=>x/total*100);
  const rounded=raw.map(x=>Math.round(x*10)/10);
  const drift=Math.round((100-rounded.reduce((a,b)=>a+b,0))*10)/10;
  rounded[0]=Math.round((rounded[0]+drift)*10)/10;
  return rounded;
}

function observerScores(f){
  const official=clamp((confidence(f)/100)*.55+clamp(providers(f).length/5)*.45);
  const weak=clamp(clamp(weakSignals(f).length/4)*.55+clamp(Math.max(0,latestDelta(f))/10)*.45);
  const adversarial=clamp(clamp(contrarySignals(f).length/4)*.55+(1-confidence(f)/100)*.25+clamp((f?.falsification?1:0))*.20);
  return {
    observer_a:{label:'Preuves fortes',score:Math.round(official*100),basis:'sources indépendantes + solidité'},
    observer_b:{label:'Signaux faibles',score:Math.round(weak*100),basis:'signaux contextuels + mouvement'},
    observer_c:{label:'Red team',score:Math.round(adversarial*100),basis:'contre-signaux + falsification'}
  };
}

function branchFrom(f,weight,index){
  return {
    world_id:`world_${index+1}`,
    scenario_key:f?.scenario_key||null,
    title:title(f),
    domain:f?.domain||'other',
    region:f?.region||f?.geography||'Monde',
    horizon:f?.horizon_label||f?.horizon_tier||'actif',
    forecast_probability_percent:Math.round(pct(f)*10)/10,
    relative_world_weight_percent:weight,
    support_score:Math.round(supportScore(f)*1000)/1000,
    movement_points:Math.round(latestDelta(f)*10)/10,
    confidence_score:Math.round(confidence(f)),
    strong_signal_count:strongSignals(f).length,
    weak_signal_count:weakSignals(f).length,
    contrary_signal_count:contrarySignals(f).length,
    source_count:providers(f).length,
    observers:observerScores(f),
    evidence:strongSignals(f).slice(0,4).map(x=>({title:x?.title||x?.label||'Signal',source:x?.source||x?.provider||null})),
    falsification:f?.falsification||null,
    watch_next:Array.isArray(f?.watch_next)?f.watch_next.slice(0,4):[],
    canonical_probability_untouched:true
  };
}

function entropy(weights){
  const ps=weights.map(x=>x/100).filter(x=>x>0);
  const bits=-ps.reduce((s,p)=>s+p*Math.log2(p),0);
  const max=ps.length>1?Math.log2(ps.length):1;
  return {bits:Math.round(bits*1000)/1000,normalized:Math.round(clamp(bits/max)*1000)/1000};
}

export function buildSuperposition(snapshot,{query='',scenarioKey='',limit=4}={}){
  const forecasts=(snapshot?.forecasts||[]).filter(active);
  const safeLimit=Math.max(2,Math.min(6,Number(limit)||4));
  let pool=forecasts;
  if(scenarioKey){const focal=forecasts.find(f=>String(f?.scenario_key)===String(scenarioKey));if(focal){const ref=[title(focal),focal.domain,focal.region].filter(Boolean).join(' ');pool=forecasts.map(f=>({f,r:relevance(f,ref)})).filter(x=>x.f===focal||x.r>.08).sort((a,b)=>(b.f===focal)-(a.f===focal)||b.r-a.r).map(x=>x.f);}}
  if(query){const ranked=pool.map(f=>({f,r:relevance(f,query)})).filter(x=>x.r>0).sort((a,b)=>b.r-a.r);if(ranked.length)pool=ranked.map(x=>x.f);}
  const scored=pool.map(f=>({f,support:supportScore(f),relevance:query?relevance(f,query):1})).sort((a,b)=>(b.relevance-a.relevance)||b.support-a.support);
  const selected=diversify(scored,safeLimit);
  const weights=normalizedWeights(selected);
  const worlds=selected.map((x,i)=>branchFrom(x.f,weights[i],i));
  const ent=entropy(weights);
  return {
    schema:'providence-superposition-v1',
    generated_at:new Date().toISOString(),
    query:query||null,
    scenario_key:scenarioKey||null,
    worlds,
    consensus:{
      dominant_world_id:worlds[0]?.world_id||null,
      dominant_relative_weight_percent:worlds[0]?.relative_world_weight_percent??null,
      branch_count:worlds.length,
      entropy_bits:ent.bits,
      uncertainty_index:ent.normalized,
      interpretation:ent.normalized>.72?'futur très distribué':ent.normalized>.42?'plusieurs trajectoires crédibles':'trajectoire dominante'
    },
    observers:{
      A:'preuves fortes / sources institutionnelles et quantitatives',
      B:'signaux faibles / anomalies et contexte émergent',
      C:'red team / contre-signaux et conditions de falsification'
    },
    semantics:{
      quantum_computing_claim:false,
      inspiration:'multi-hypothesis parallel worlds',
      world_weights_are_event_probabilities:false,
      world_weights_mean:'relative support/attention mass among selected active hypotheses',
      forecast_probabilities_remain_canonical:true,
      no_branch_collapses_without_new_evidence:true
    }
  };
}
