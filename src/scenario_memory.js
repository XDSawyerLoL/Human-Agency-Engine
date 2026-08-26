import fs from 'node:fs';

const catalog = JSON.parse(fs.readFileSync(new URL('./future_engine_catalog.json', import.meta.url), 'utf8'));
const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const DOMAIN_MAP = {
  'Technologie':'cyber_technology','Climat':'weather_climate','Emploi':'economy_labor','Énergie':'energy',
  'Santé':'public_health','Société':'social_collective_behavior','Géopolitique':'geopolitics_security','Économie':'financial_stress'
};
const STOP = new Set(`a à au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous the of and or will what when who how before after by from into over under be is are was were to in on at as an any its this that than more less global world monde marché predictif question suivie probability probabilite estime moteur future engine`.split(/\s+/));
const NORMALIZE = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const logit=p=>Math.log(clamp(p,.01,.99)/(1-clamp(p,.01,.99)));
const logistic=x=>1/(1+Math.exp(-x));
const hash=s=>{let h=2166136261;for(const c of String(s)){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `memory-${(h>>>0).toString(16)}`};

function tokens(value){
  return [...new Set(NORMALIZE(value).split(/\s+/).filter(x=>x.length>=4&&!STOP.has(x)))];
}
function horizon(target, now=Date.now()) {
  const days=Math.max(0,Date.parse(target)-now)/DAY;
  if(days<=3)return{tier:'immediate',label:'≤ 72 heures',order:0};
  if(days<=45)return{tier:'near',label:'Jours à semaines',order:1};
  if(days<=365)return{tier:'medium',label:'Mois à venir',order:2};
  if(days<=365*3)return{tier:'long',label:'1 à 3 ans',order:3};
  if(days<=365*5)return{tier:'strategic',label:'3 à 5 ans',order:4};
  return{tier:'deep',label:'5 ans et +',order:5};
}
function sourceKey(value){return NORMALIZE(value).replace(/\s+/g,'-')||'future-engine-memory'}
function signalText(signal){return NORMALIZE(`${signal?.title||''} ${signal?.event_type||''} ${signal?.geography||''} ${signal?.source_label||''} ${signal?.source_key||''} ${JSON.stringify(signal?.facts||{})}`)}
function matchSeed(seed, signals){
  const seedTokens=tokens(`${seed.title} ${seed.summary} ${seed.region} ${(seed.sources||[]).join(' ')}`);
  const region=NORMALIZE(seed.region);
  const sourceTokens=(seed.sources||[]).map(NORMALIZE).filter(Boolean);
  const scored=[];
  for(const signal of signals||[]){
    const text=signalText(signal); if(!text)continue;
    let hits=0;
    for(const t of seedTokens) if(text.includes(t)) hits++;
    const lexical=seedTokens.length?hits/Math.min(seedTokens.length,12):0;
    const regionBoost=region&&region!=='monde'&&text.includes(region)?0.28:0;
    const sourceBoost=sourceTokens.some(s=>s&&text.includes(s))?0.18:0;
    const eventBoost=(seed.domain==='Climat'&&/weather|climat|flood|heat|storm|drought|wildfire|temperature/.test(text))||
      (seed.domain==='Santé'&&/health|who|disease|outbreak|sante/.test(text))||
      (seed.domain==='Énergie'&&/energy|oil|fred|grid|electric|energie/.test(text))||
      (seed.domain==='Emploi'&&/layoff|labor|emploi|industrial|unemployment/.test(text))||
      (seed.domain==='Géopolitique'&&/conflict|military|sanction|geopolit|trade/.test(text))||
      (seed.domain==='Technologie'&&/ai |artificial|technology|cyber|regulation|data center/.test(text))?0.12:0;
    const score=lexical+regionBoost+sourceBoost+eventBoost;
    if(score>=0.16)scored.push({signal,score});
  }
  return scored.sort((a,b)=>b.score-a.score).slice(0,6);
}
function probability(seed,matches){
  const base=clamp(Number(seed.probability||50)/100,.04,.96);
  const confidence=clamp(Number(seed.confidence||35)/100,.2,.95);
  // Future Engine is internal scenario memory: keep its prior, but shrink toward 50% when current HORIZON has little support.
  const retained=.45+confidence*.35;
  let z=logit(base)*retained;
  const independent=new Set(); let support=0;
  for(const {signal,score} of matches){
    const family=signal?.source_family||signal?.source_key||'unknown';
    const duplicate=independent.has(family); independent.add(family);
    const trust=clamp(signal?.source_trust??.62,.35,1);
    support += clamp(score,0,.9)*trust*(duplicate?.35:1)*.62;
  }
  z += clamp(support,0,1.35);
  const p=clamp(logistic(z),.07,.92);
  return {p,independentFamilies:independent.size,support};
}
function eventType(seed){
  const title=NORMALIZE(seed.title);
  if(seed.domain==='Technologie'&&/regulation|cadre contraignant|ai act/.test(title))return'memory_ai_regulation';
  if(seed.domain==='Emploi'&&/suppressions|licenci|turnover|chomage/.test(title))return'memory_labor_ai';
  if(seed.domain==='Énergie'&&/carbone|ets/.test(title))return'memory_carbon_market';
  if(seed.domain==='Santé'&&/who|oms|urgence|disease|infectious/.test(title))return'memory_health_outbreak';
  if(seed.domain==='Société'&&/greve|strike|logistique/.test(title))return'memory_social_logistics';
  if(seed.domain==='Géopolitique'&&/naval|chine|china|taiwan|military|conflit/.test(title))return'memory_geopolitical_escalation';
  if(seed.domain==='Économie'&&/banque centrale|inflation|cpi|recession/.test(title))return'memory_macro_transition';
  if(seed.domain==='Climat')return'memory_climate_scenario';
  if((seed.sources||[]).includes('PubMed'))return'memory_research_biomedical';
  if((seed.sources||[]).includes('arXiv'))return'memory_research_technology';
  if((seed.sources||[]).includes('Polymarket'))return'memory_market_consensus';
  if((seed.sources||[]).includes('Metaculus'))return'memory_forecasting_question';
  return'memory_future_scenario';
}
function trajectory(p,matches){return matches.length>=3&&p>=.55?'building':matches.length>=1?'forming':'watching'}

export function buildScenarioMemoryForecasts(signals,{now=Date.now()}={}){
  const out=[];
  for(const seed of catalog){
    if(Date.parse(seed.target_date)<now)continue;
    const matches=matchSeed(seed,signals);
    const {p,independentFamilies,support}=probability(seed,matches);
    const hm=horizon(seed.target_date,now); const pct=Math.round(p*100); const id=hash(seed.id);
    const evidence=matches.map(({signal,score})=>({title:signal.title,source_key:signal.source_key,source_label:signal.source_label,source_family:signal.source_family,source_trust:signal.source_trust,url:signal.url,observed_at:signal.observed_at,event_at:signal.event_at,facts:{...(signal.facts||{}),scenario_memory_match:Number(score.toFixed(3))}}));
    const declared=(seed.sources||[]).map(label=>({key:sourceKey(label),label,role:'source de la mémoire Future Engine'}));
    out.push({
      id,scenario_key:id,scenario_id:`memory-${seed.id}`,origin_group:`scenario-memory|${eventType(seed)}|${seed.region||'Monde'}`,status:'active',
      domain:DOMAIN_MAP[seed.domain]||'social_collective_behavior',event_type:eventType(seed),title:seed.title,headline:seed.title,outcome:seed.title,summary:seed.summary,
      region:seed.region||'Monde',public_language:'fr',fact_status:'forecast_recomputed_from_internal_scenario_memory',horizon_tier:hm.tier,horizon_label:hm.label,horizon_order:hm.order,target_date:seed.target_date,
      trajectory:trajectory(p,matches),commercial_priority:clamp(.58+Number(seed.confidence||35)/250,.58,.90),
      probability:{type:'model_estimate',estimate:p,percent:pct,interval_low:clamp(p-.16,.02,.88),interval_high:clamp(p+.16,.10,.95),interval_percent:[Math.round(clamp(p-.16,.02,.88)*100),Math.round(clamp(p+.16,.10,.95)*100)],method:'evidence-scenario-memory-v1',calibration_status:'uncalibrated_model_estimate',empirically_calibrated:false,can_be_read_as_empirical_frequency:false},
      confidence:Math.round(clamp(Number(seed.confidence||35)*.55+independentFamilies*8+Math.min(matches.length,4)*4,30,92)),confidence_label:matches.length?'réévalué avec signaux live':'hypothèse surveillée',
      time_window:{kind:'absolute_scenario_memory_window',start_at:new Date(now).toISOString(),end_at:seed.target_date,target_date:seed.target_date,human:hm.label,...hm},
      what_we_know:matches.length?`${matches.length} signaux HORIZON actuels recoupent cette hypothèse issue de la mémoire Future Engine.`:'Cette hypothèse appartient à la mémoire prédictive Future Engine et reste sous surveillance active par HORIZON.',
      why_now:matches.length?`HORIZON retrouve actuellement ${matches.length} recoupement(s) utile(s), issus de ${Math.max(1,independentFamilies)} famille(s) de sources.`:'Le moteur conserve ce scénario comme hypothèse active et attend des précurseurs actuels suffisamment proches pour le renforcer ou l’affaiblir.',
      causal_chain:['hypothèse issue de Future Engine','recherche de précurseurs actuels','corroboration indépendante','matérialisation ou réfutation avant échéance'],
      watch_next:['nouveaux signaux indépendants','confirmation officielle ou opérationnelle','indicateurs contraires'],
      favorable_signals:evidence.slice(0,5).map(x=>x.title),contrary_signals:matches.length?['absence de confirmation supplémentaire','normalisation du mécanisme observé']:['aucun précurseur actuel suffisamment proche'],
      probability_up_if:['plusieurs sources indépendantes convergent','un précurseur opérationnel ou officiel apparaît'],probability_down_if:['les signaux convergents disparaissent','un indicateur officiel contredit le mécanisme'],human_needs:Array.isArray(seed.impacts)?seed.impacts:[],
      resolution_conditions:`Le scénario est évalué à l’échéance ${String(seed.target_date).slice(0,10)} selon la formulation de la carte.`,falsification:`Le résultat annoncé ne se matérialise pas avant l’échéance ${String(seed.target_date).slice(0,10)}.`,
      evidence,
      fusion:{engine:'evidence-scenario-memory-v1',raw_signal_count:evidence.length,source_keys:evidence.map(x=>x.source_key),duplicate_probability_inflation_prevented:true,geography_aware_grouping:true,probability_recomputed_after_fusion:true,multiple_distinct_outcomes_per_precursor_allowed:true},
      consolidation:{score:Math.round(clamp(Number(seed.confidence||35)*.55+independentFamilies*8+Math.min(matches.length,4)*4,30,92)),score_is_probability:false,level:matches.length?'en consolidation':'surveillance',source_families:[...new Map(evidence.map(x=>[x.source_family,{key:x.source_family,label:x.source_family}])).values()],source_providers:[...declared,...evidence.map(x=>({key:x.source_key,label:x.source_label||x.source_key,role:x.source_family||'signal HORIZON'}))].filter((x,i,a)=>a.findIndex(y=>y.key===x.key)===i),dimensions:[],strengths:[`Mémoire Future Engine : ${seed.probability}% avant réévaluation.`,matches.length?`${matches.length} recoupement(s) actuel(s) détecté(s).`:'Hypothèse explicite avec échéance.'],weaknesses:matches.length?[]:['Pas encore de recoupement live assez fort.']},
      memory:{engine:'Future Engine',seed_id:seed.id,seed_probability:Number(seed.probability||0),seed_confidence:Number(seed.confidence||0),live_match_count:matches.length,live_support:Number(support.toFixed(3)),recomputed:true}
    });
  }
  return out;
}

export function scenarioMemoryStats(now=Date.now()){
  const active=catalog.filter(x=>Date.parse(x.target_date)>=now);
  return{total:catalog.length,active:active.length,expired:catalog.length-active.length,domains:[...new Set(catalog.map(x=>x.domain))].sort(),sources:[...new Set(catalog.flatMap(x=>x.sources||[]))].sort()};
}
