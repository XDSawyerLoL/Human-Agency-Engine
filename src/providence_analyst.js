import { config } from './config.js';
import { buildSuperposition } from './superposition_engine.js';

const clampText=(v,n)=>String(v??'').slice(0,n);
const active=f=>!['resolved','invalidated','expired'].includes(String(f?.status||'').toLowerCase());
const prob=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return Math.round(p*10)/10;const e=Number(f?.probability?.estimate);return Number.isFinite(e)?Math.round(e*1000)/10:null};
const confidence=f=>Math.round(Number(f?.consolidation?.score??f?.confidence??0)||0);
const title=f=>String(f?.title||f?.headline||f?.outcome||'Scénario');
const norm=v=>String(v??'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const STOP=new Set('que quoi qu est ce qui va t il elle ils elles se passer pour dans sur en au aux le la les un une des du de d et ou a à avec sans par vers vois voir venir priorite priorité compare comparer scenario scenarios scénario scénarios principal principaux actuelle actuellement prediction prevision prévision predictions prévisions'.split(/\s+/).map(norm));
const GENERIC=new Set(['fragile','faible','signal','signaux','surveiller','surveille','preuve','preuves','source','sources','avenir','futur','futurs','trajectoire','trajectoires']);
const EXPAND={
  election:['election','elections','electoral','electorale','scrutin','vote','presidentiel','presidentielle','candidat','candidate','politique'],
  elections:['election','elections','electoral','electorale','scrutin','vote','presidentiel','presidentielle','candidat','candidate','politique'],
  france:['france','francais','francaise','hexagone'],
  emploi:['emploi','emplois','travail','chomage','chomeur'],
  climat:['climat','climatique','canicule','temperature','meteo'],
  ia:['ia','intelligence artificielle','modele','modeles'],
  energie:['energie','electricite','nucleaire','petrole','gaz'],
  ukraine:['ukraine','ukrainien','russie','russe'],
  sante:['sante','oms','epidemie','pandemie','maladie']
};
const DOMAIN_WORDS={
  regulation_policy:'politique regulation loi gouvernement election scrutin',
  geopolitics_security:'geopolitique politique guerre conflit securite gouvernement election',
  economy_labor:'economie emploi travail chomage croissance',
  weather_climate:'climat meteo canicule chaleur temperature',
  natural_hazards:'risque naturel seisme inondation incendie tempete',
  cyber_technology:'technologie ia intelligence artificielle cyber',
  public_health:'sante oms epidemie pandemie maladie',
  financial_stress:'finance marche taux banque inflation',
  energy:'energie electricite nucleaire petrole gaz'
};
function queryTerms(query){
  const raw=norm(query).split(/\s+/).filter(Boolean);
  return [...new Set(raw.filter(x=>x.length>2||/^20\d{2}$/.test(x)).filter(x=>!STOP.has(x)))];
}
function queryIsSpecific(query){
  const terms=queryTerms(query);
  if(!terms.length)return false;
  return terms.some(t=>!GENERIC.has(t));
}
function forecastHay(f){
  const signals=[...(f?.signal_convergence?.strong_signals||[]),...(f?.signal_convergence?.weak_signals||[]),...(f?.contrary_signals||[]),...(f?.signal_convergence?.contrary_signals||[])].map(x=>x?.title||x?.label||'').join(' ');
  return norm([title(f),f?.summary,f?.public_summary,f?.why_now,f?.region,f?.geography,f?.horizon_label,f?.horizon_tier,DOMAIN_WORDS[f?.domain]||f?.domain,signals].filter(Boolean).join(' '));
}
function termMatches(hay,term){
  const variants=EXPAND[term]||[term];
  return variants.some(v=>hay.includes(norm(v)));
}
export function rankForecastsForQuery(snapshot,query,{limit=14}={}){
  const rows=(snapshot?.forecasts||[]).filter(active);
  if(!queryIsSpecific(query))return rows.sort((a,b)=>(prob(b)||0)-(prob(a)||0)).slice(0,limit);
  const terms=queryTerms(query);
  const ranked=rows.map(f=>{
    const hay=forecastHay(f);let matched=0,weighted=0,total=0;
    for(const term of terms){const w=/^20\d{2}$/.test(term)?1.25:1;total+=w;if(termMatches(hay,term)){matched++;weighted+=w;}}
    const score=total?weighted/total:0;
    return {f,score,matched};
  }).filter(x=>x.score>=.45&&x.matched>=Math.min(2,terms.length)).sort((a,b)=>b.score-a.score||(prob(b.f)||0)-(prob(a.f)||0));
  return ranked.slice(0,limit).map(x=>x.f);
}
const endpoint=base=>{const b=String(base||'').replace(/\/$/,'');if(!b)return '';return /\/chat\/completions$/i.test(b)?b:`${b}/chat/completions`;};

export function analystStatus(){
  return {
    configured:Boolean(config.ai.baseUrl&&config.ai.analystModel),
    provider:'openai-compatible',
    analyst_model:config.ai.analystModel||null,
    red_team_configured:Boolean(config.ai.baseUrl&&config.ai.redTeamModel),
    red_team_model:config.ai.redTeamModel||null,
    execution_authority:false,
    tools_enabled:false,
    probabilities_writable:false
  };
}

function emptySuperposition(query){
  return {schema:'providence-superposition-v1',generated_at:new Date().toISOString(),query:query||null,scenario_key:null,worlds:[],consensus:{dominant_world_id:null,dominant_relative_weight_percent:null,branch_count:0,entropy_bits:0,uncertainty_index:0,interpretation:'aucune trajectoire correspondante'},observers:{A:'preuves fortes',B:'signaux faibles',C:'red team'},semantics:{quantum_computing_claim:false,world_weights_are_event_probabilities:false,forecast_probabilities_remain_canonical:true}};
}

export function buildAnalystContext(snapshot,trackRecord,{query='',scenarioKey=''}={}){
  const specific=queryIsSpecific(query);
  const forecasts=rankForecastsForQuery(snapshot,query,{limit:14});
  const scopedSnapshot=specific?{...snapshot,forecasts}:snapshot;
  const superposition=forecasts.length?buildSuperposition(scopedSnapshot,{query: specific?'':query,scenarioKey,limit:4}):emptySuperposition(query);
  const calibration=trackRecord?.calibration?.global||{};
  return {
    generated_at:snapshot?.generated_at||null,
    query_scope:{specific,query,matched_forecasts:forecasts.length},
    system_contract:{
      forecast_probability_is_canonical:true,
      llm_cannot_change_probability:true,
      confidence_is_not_probability:true,
      world_weight_is_not_probability:true,
      intent_engine_execution_available:false,
      unrelated_forecast_fallback_forbidden:true
    },
    calibration:{
      brier:calibration?.brier??trackRecord?.brier_score??null,
      log_loss:calibration?.log_loss??trackRecord?.log_loss??null,
      ece:calibration?.ece??null,
      resolved:trackRecord?.resolution?.resolved??trackRecord?.resolved_scenarios??null
    },
    superposition,
    forecasts:forecasts.map(f=>({
      scenario_key:f?.scenario_key||null,
      title:title(f),
      probability_percent:prob(f),
      confidence_score:confidence(f),
      domain:f?.domain||null,
      region:f?.region||f?.geography||'Monde',
      horizon:f?.horizon_label||f?.horizon_tier||null,
      movement_points:Number(f?.probability_delta_points)||0,
      strong_signals:(f?.signal_convergence?.strong_signals||[]).slice(0,4).map(x=>x?.title||x?.label||'Signal'),
      weak_signals:(f?.signal_convergence?.weak_signals||[]).slice(0,3).map(x=>x?.title||x?.label||'Signal faible'),
      contrary_signals:(f?.contrary_signals||f?.signal_convergence?.contrary_signals||[]).slice(0,3).map(x=>x?.title||x?.label||'Contre-signal'),
      source_providers:(f?.consolidation?.source_providers||[]).slice(0,5).map(x=>x?.label||x?.key||String(x)),
      causal_chain:(f?.causal_chain||[]).slice(0,4),
      falsification:f?.falsification||null,
      watch_next:(f?.watch_next||[]).slice(0,4)
    })),
    causal_world:{
      nodes:snapshot?.causal_world?.metrics?.nodes??null,
      edges:snapshot?.causal_world?.metrics?.edges??null,
      learned_edges:snapshot?.causal_world?.metrics?.learned_structural_edges??null
    }
  };
}

function engineOnlyAnswer(context,message,mode){
  const worlds=context?.superposition?.worlds||[];
  const lead=worlds[0];
  if(!lead){
    if(context?.query_scope?.specific)return {text:`Je n’ai actuellement aucune prévision active suffisamment pertinente pour répondre sérieusement à « ${clampText(message,220)} ». Je préfère te le dire plutôt que de recycler une trajectoire sans rapport.\n\nTu peux consulter les prévisions disponibles ou reformuler avec un sujet plus large ; dès qu’un scénario correspondant existe dans Providence, je l’utiliserai.`,citations:[],mode:'engine_only',no_relevant_forecast:true};
    return {text:"Providence n’a pas actuellement assez de prévisions actives pour produire une réponse ancrée. Je préfère le signaler plutôt que d’inventer une conclusion.",citations:[],mode:'engine_only'};
  }
  const red=mode==='red_team';
  const prefix=context?.query_scope?.specific?'Pour ta question, la trajectoire active la plus pertinente est':'La trajectoire actuellement la plus saillante est';
  const lines=red?[
    `Je conteste d’abord « ${lead.title} » à ${lead.forecast_probability_percent}% de probabilité publique.`,
    `Contre-signaux observés : ${lead.contrary_signal_count}. Solidité : ${lead.confidence_score}/100. Sources indépendantes : ${lead.source_count}.`,
    lead.falsification?`Condition de falsification à surveiller : ${typeof lead.falsification==='string'?lead.falsification:JSON.stringify(lead.falsification).slice(0,260)}.`:'Aucune condition de falsification exploitable n’est suffisamment explicite dans le contexte actuel.',
    `Le poids relatif du monde dominant (${lead.relative_world_weight_percent}%) n’est pas une probabilité d’événement : il mesure seulement le soutien relatif parmi les hypothèses sélectionnées.`
  ]:[
    `${prefix} « ${lead.title} » avec une probabilité publique de ${lead.forecast_probability_percent}% et une solidité de ${lead.confidence_score}/100.`,
    `Providence a trouvé ${context?.query_scope?.matched_forecasts||worlds.length} prévision(s) active(s) suffisamment liée(s) à ta question.`,
    `Cette trajectoire s’appuie actuellement sur ${lead.strong_signal_count} signal(aux) fort(s), ${lead.weak_signal_count} signal(aux) faible(s), ${lead.contrary_signal_count} contre-signal(aux) et ${lead.source_count} source(s) contributrice(s).`,
    `Je peux détailler les preuves, les contre-signaux ou comparer uniquement les scénarios pertinents pour ce sujet.`
  ];
  return {text:lines.join('\n\n'),citations:worlds.slice(0,4).map(w=>({scenario_key:w.scenario_key,title:w.title,probability_percent:w.forecast_probability_percent})),mode:'engine_only',user_message:clampText(message,500)};
}

function systemPrompt(mode){
  const red=mode==='red_team';
  return `Tu es Providence Analyst, interface conversationnelle d'un moteur de prévision probabiliste. ${red?'Tu agis en RED TEAM : cherche les hypothèses fragiles, contre-signaux, biais et conditions de falsification sans chercher artificiellement à contredire les données.':'Tu expliques les sorties de Providence de façon claire, concise et vérifiable.'}\n\nRÈGLES STRICTES:\n- Tu réponds à la question posée, pas à la prévision globale la mieux classée.\n- Tu n'inventes JAMAIS une probabilité, un score, une source ou un événement.\n- Si query_scope.matched_forecasts vaut 0 pour une question spécifique, dis explicitement que Providence n'a pas encore de prévision pertinente ; ne recycle jamais un scénario sans rapport.\n- La probabilité publique du Forecast Engine est canonique et non modifiable par toi.\n- Le score de confiance n'est pas une probabilité.\n- Le poids d'un monde de Superposition est un poids relatif de soutien, PAS une probabilité d'événement.\n- Si l'information manque, dis-le.\n- Distingue faits observés, inférences, scénarios et spéculation.\n- Tu n'as aucune autorité d'exécution et aucun accès à des clés, wallets, appareils physiques ou mandats Intent Engine.\n- N'affirme jamais utiliser de calcul quantique : Superposition est une architecture multi-hypothèses inspirée d'une métaphore.\n- Cite les titres/scenario_key pertinents quand cela aide la vérification.\n- Réponds en français sauf demande contraire.`;
}

async function callModel({model,messages,temperature}){
  const url=endpoint(config.ai.baseUrl);
  if(!url||!model)throw new Error('analyst_model_not_configured');
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),config.ai.timeoutMs);
  try{
    const headers={'content-type':'application/json'};
    if(config.ai.apiKey)headers.authorization=`Bearer ${config.ai.apiKey}`;
    const res=await fetch(url,{method:'POST',headers,signal:controller.signal,body:JSON.stringify({model,messages,temperature,max_tokens:config.ai.maxTokens,stream:false})});
    const raw=await res.text();
    if(!res.ok)throw new Error(`analyst_provider_${res.status}:${raw.slice(0,240)}`);
    const data=JSON.parse(raw);
    const text=data?.choices?.[0]?.message?.content;
    if(!text)throw new Error('analyst_provider_empty_response');
    return clampText(text,12000);
  }finally{clearTimeout(timer);}
}

export async function answerProvidence({message,mode='analyst',history=[],snapshot,trackRecord}){
  const safeMode=mode==='red_team'?'red_team':'analyst';
  const clean=clampText(message,5000).trim();
  if(clean.length<2)throw new Error('message_too_short');
  const context=buildAnalystContext(snapshot,trackRecord,{query:clean});
  const status=analystStatus();
  const model=safeMode==='red_team'?(config.ai.redTeamModel||config.ai.analystModel):config.ai.analystModel;
  if(context.query_scope.specific&&context.query_scope.matched_forecasts===0){return {status:'ok',provider:'engine_only',model:null,...engineOnlyAnswer(context,clean,safeMode),superposition:context.superposition};}
  if(!status.configured||!model){return {status:'ok',provider:'engine_only',model:null,...engineOnlyAnswer(context,clean,safeMode),superposition:context.superposition};}
  const compactHistory=(Array.isArray(history)?history:[]).slice(-8).map(x=>({role:x?.role==='assistant'?'assistant':'user',content:clampText(x?.content,1800)}));
  const messages=[
    {role:'system',content:systemPrompt(safeMode)},
    {role:'system',content:`CONTEXTE PROVIDENCE EN LECTURE SEULE:\n${JSON.stringify(context).slice(0,28000)}`},
    ...compactHistory,
    {role:'user',content:clean}
  ];
  try{
    const text=await callModel({model,messages,temperature:safeMode==='red_team'?.45:.2});
    return {status:'ok',provider:'openai-compatible',model,mode:safeMode,text,superposition:context.superposition,execution_authority:false};
  }catch(error){
    return {status:'degraded',provider:'engine_only',model:null,error:String(error?.message||error),...engineOnlyAnswer(context,clean,safeMode),superposition:context.superposition};
  }
}
