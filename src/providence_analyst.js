import { config } from './config.js';
import { buildSuperposition } from './superposition_engine.js';
import { buildDynamicForecast } from './quantic_dynamic_forecast.js';

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
function queryTerms(query){const raw=norm(query).split(/\s+/).filter(Boolean);return [...new Set(raw.filter(x=>x.length>2||/^20\d{2}$/.test(x)).filter(x=>!STOP.has(x)))];}
function queryIsSpecific(query){const terms=queryTerms(query);return Boolean(terms.length&&terms.some(t=>!GENERIC.has(t)));}
function forecastHay(f){const signals=[...(f?.signal_convergence?.strong_signals||[]),...(f?.signal_convergence?.weak_signals||[]),...(f?.contrary_signals||[]),...(f?.signal_convergence?.contrary_signals||[])].map(x=>x?.title||x?.label||'').join(' ');return norm([title(f),f?.summary,f?.public_summary,f?.why_now,f?.region,f?.geography,f?.horizon_label,f?.horizon_tier,DOMAIN_WORDS[f?.domain]||f?.domain,signals].filter(Boolean).join(' '));}
function termMatches(hay,term){const variants=EXPAND[term]||[term];return variants.some(v=>hay.includes(norm(v)));}

export function rankForecastsForQuery(snapshot,query,{limit=14}={}){
  const rows=(snapshot?.forecasts||[]).filter(active);
  if(!queryIsSpecific(query))return rows.sort((a,b)=>(prob(b)||0)-(prob(a)||0)).slice(0,limit);
  const terms=queryTerms(query);
  const ranked=rows.map(f=>{const hay=forecastHay(f);let matched=0,weighted=0,total=0;for(const term of terms){const w=/^20\d{2}$/.test(term)?1.25:1;total+=w;if(termMatches(hay,term)){matched++;weighted+=w;}}return {f,score:total?weighted/total:0,matched};})
    .filter(x=>x.score>=.45&&x.matched>=Math.min(2,terms.length))
    .sort((a,b)=>b.score-a.score||(prob(b.f)||0)-(prob(a.f)||0));
  return ranked.slice(0,limit).map(x=>x.f);
}
const endpoint=base=>{const b=String(base||'').replace(/\/$/,'');if(!b)return '';return /\/chat\/completions$/i.test(b)?b:`${b}/chat/completions`;};

export function analystStatus(){return {configured:Boolean(config.ai.baseUrl&&config.ai.analystModel),provider:'openai-compatible',analyst_model:config.ai.analystModel||null,red_team_configured:Boolean(config.ai.baseUrl&&config.ai.redTeamModel),red_team_model:config.ai.redTeamModel||null,execution_authority:false,tools_enabled:false,probabilities_writable:false,dynamic_forecast_enabled:true};}
function emptySuperposition(query){return {schema:'providence-superposition-v1',generated_at:new Date().toISOString(),query:query||null,scenario_key:null,worlds:[],consensus:{dominant_world_id:null,dominant_relative_weight_percent:null,branch_count:0,entropy_bits:0,uncertainty_index:0,interpretation:'aucune trajectoire correspondante'},observers:{A:'preuves fortes',B:'signaux faibles',C:'red team'},semantics:{quantum_computing_claim:false,world_weights_are_event_probabilities:false,forecast_probabilities_remain_canonical:true}};}

export function buildAnalystContext(snapshot,trackRecord,{query='',scenarioKey=''}={}){
  const specific=queryIsSpecific(query);const forecasts=rankForecastsForQuery(snapshot,query,{limit:14});const scopedSnapshot=specific?{...snapshot,forecasts}:snapshot;const superposition=forecasts.length?buildSuperposition(scopedSnapshot,{query:specific?'':query,scenarioKey,limit:4}):emptySuperposition(query);const calibration=trackRecord?.calibration?.global||{};
  return {
    generated_at:snapshot?.generated_at||null,query_scope:{specific,query,matched_forecasts:forecasts.length},
    system_contract:{forecast_probability_is_canonical:true,llm_cannot_change_probability:true,confidence_is_not_probability:true,world_weight_is_not_probability:true,intent_engine_execution_available:false,unrelated_forecast_fallback_forbidden:true,dynamic_research_allowed:true},
    calibration:{brier:calibration?.brier??trackRecord?.brier_score??null,log_loss:calibration?.log_loss??trackRecord?.log_loss??null,ece:calibration?.ece??null,resolved:trackRecord?.resolution?.resolved??trackRecord?.resolved_scenarios??null},
    superposition,
    forecasts:forecasts.map(f=>({scenario_key:f?.scenario_key||null,title:title(f),probability_percent:prob(f),confidence_score:confidence(f),domain:f?.domain||null,region:f?.region||f?.geography||'Monde',horizon:f?.horizon_label||f?.horizon_tier||null,movement_points:Number(f?.probability_delta_points)||0,strong_signals:(f?.signal_convergence?.strong_signals||[]).slice(0,4).map(x=>x?.title||x?.label||'Signal'),weak_signals:(f?.signal_convergence?.weak_signals||[]).slice(0,3).map(x=>x?.title||x?.label||'Signal faible'),contrary_signals:(f?.contrary_signals||f?.signal_convergence?.contrary_signals||[]).slice(0,3).map(x=>x?.title||x?.label||'Contre-signal'),source_providers:(f?.consolidation?.source_providers||[]).slice(0,5).map(x=>x?.label||x?.key||String(x)),causal_chain:(f?.causal_chain||[]).slice(0,4),falsification:f?.falsification||null,watch_next:(f?.watch_next||[]).slice(0,4)})),
    causal_world:{nodes:snapshot?.causal_world?.metrics?.nodes??null,edges:snapshot?.causal_world?.metrics?.edges??null,learned_edges:snapshot?.causal_world?.metrics?.learned_structural_edges??null}
  };
}

function engineOnlyAnswer(context,message,mode){
  const worlds=context?.superposition?.worlds||[];const lead=worlds[0];
  if(!lead)return {text:"Providence n’a pas actuellement assez de prévisions actives pour produire une réponse ancrée. Je préfère le signaler plutôt que d’inventer une conclusion.",citations:[],mode:'engine_only'};
  const red=mode==='red_team';const prefix=context?.query_scope?.specific?'Pour ta question, la trajectoire active la plus pertinente est':'La trajectoire actuellement la plus saillante est';
  const lines=red?[`Je conteste d’abord « ${lead.title} » à ${lead.forecast_probability_percent}% de probabilité publique.`,`Contre-signaux observés : ${lead.contrary_signal_count}. Solidité : ${lead.confidence_score}/100. Sources indépendantes : ${lead.source_count}.`,lead.falsification?`Condition de falsification à surveiller : ${typeof lead.falsification==='string'?lead.falsification:JSON.stringify(lead.falsification).slice(0,260)}.`:'Aucune condition de falsification exploitable n’est suffisamment explicite dans le contexte actuel.',`Le poids relatif du monde dominant (${lead.relative_world_weight_percent}%) n’est pas une probabilité d’événement.`]:[`${prefix} « ${lead.title} » avec une probabilité publique de ${lead.forecast_probability_percent}% et une solidité de ${lead.confidence_score}/100.`,`Providence a trouvé ${context?.query_scope?.matched_forecasts||worlds.length} prévision(s) active(s) suffisamment liée(s) à ta question.`,`Cette trajectoire s’appuie actuellement sur ${lead.strong_signal_count} signal(aux) fort(s), ${lead.weak_signal_count} signal(aux) faible(s), ${lead.contrary_signal_count} contre-signal(aux) et ${lead.source_count} source(s) contributrice(s).`,`Je peux détailler les preuves, les contre-signaux ou comparer uniquement les scénarios pertinents pour ce sujet.`];
  return {text:lines.join('\n\n'),citations:worlds.slice(0,4).map(w=>({scenario_key:w.scenario_key,title:w.title,probability_percent:w.forecast_probability_percent})),mode:'engine_only',user_message:clampText(message,500)};
}

function dynamicDeterministicAnswer(dynamic,mode){
  const r=dynamic?.research||{},est=dynamic?.estimate||{},worlds=dynamic?.superposition?.worlds||[],spec=dynamic?.plan||{};const ok=(r.evidence||[]).filter(x=>x.status==='ok');
  const sourceLabels=ok.map(x=>x.label).slice(0,5);const intro=`Je n’avais pas de prévision déjà publiée assez spécifique, donc j’ai lancé Quantic Dynamic Forecast pour « ${clampText(dynamic?.input?.question,240)} ».`;
  const coverage=`Recherche croisée : ${r.sources_ok||0}/${r.sources_attempted||0} familles de données exploitables · couverture ${r.coverage_score||0}/100${sourceLabels.length?` · ${sourceLabels.join(' · ')}`:''}.`;
  let estimateText=est.probability_percent!==null&&est.probability_percent!==undefined?`Une recomposition de prévisions Providence déjà publiées donne ${est.probability_percent}% pour l’hypothèse centrale. Ce chiffre n’est utilisé que parce que la couverture numérique minimale est atteinte.`:`Je ne publie pas encore de probabilité d’événement unique : les données numériques directement comparables sont insuffisantes. Les pourcentages ci-dessous sont des poids de soutien relatifs entre futurs possibles, pas des probabilités de victoire.`;
  if(mode==='red_team')estimateText+=` Je considère en priorité les sources manquantes et les ruptures susceptibles d’invalider la trajectoire dominante.`;
  const branches=worlds.slice(0,4).map((w,i)=>`${i+1}. ${w.title} — soutien relatif ${w.relative_world_weight_percent}%`).join('\n');
  const missing=(r.missing||[]).length?`\n\nÀ renforcer avant une estimation plus agressive : ${(r.missing||[]).join(', ')}.`:'';
  return {text:`${intro}\n\n${coverage}\n\n${estimateText}${branches?`\n\nFuturs plausibles actuellement explorés :\n${branches}`:''}${missing}`,citations:[],mode:'dynamic_research',dynamic_forecast:dynamic};
}

function systemPrompt(mode,{dynamic=false}={}){
  const red=mode==='red_team';
  return `Tu es Providence Analyst, interface conversationnelle d'un moteur de prévision probabiliste. ${red?'Tu agis en RED TEAM : cherche les hypothèses fragiles, contre-signaux, biais et conditions de falsification.':'Tu expliques les sorties de Providence de façon claire, concise et vérifiable.'}\n\nRÈGLES STRICTES:\n- Tu réponds exactement à la question posée.\n- Tu n'inventes JAMAIS une probabilité, un score, une source ou un événement.\n- ${dynamic?'Le contexte contient une recherche Quantic Dynamic Forecast déclenchée à la demande. Utilise uniquement ses preuves et ses scénarios ; signale clairement ses lacunes.':'La probabilité publique du Forecast Engine est canonique et non modifiable par toi.'}\n- Un poids de monde / soutien relatif n'est JAMAIS une probabilité d'événement ou de victoire.\n- Les données de lobbying, banques ou médias ne sont jamais traitées comme preuve causale sans lien documenté.\n- L'attention médiatique n'est pas une intention de vote.\n- Si l'information manque, dis-le.\n- Distingue faits observés, inférences, scénarios et spéculation.\n- Tu n'as aucune autorité d'exécution.\n- N'affirme jamais utiliser de calcul quantique : Quantic Simulated est une architecture multi-hypothèses exécutée sur calcul classique.\n- Réponds en français sauf demande contraire.`;
}

async function callModel({model,messages,temperature}){const url=endpoint(config.ai.baseUrl);if(!url||!model)throw new Error('analyst_model_not_configured');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),config.ai.timeoutMs);try{const headers={'content-type':'application/json'};if(config.ai.apiKey)headers.authorization=`Bearer ${config.ai.apiKey}`;const res=await fetch(url,{method:'POST',headers,signal:controller.signal,body:JSON.stringify({model,messages,temperature,max_tokens:config.ai.maxTokens,stream:false})});const raw=await res.text();if(!res.ok)throw new Error(`analyst_provider_${res.status}:${raw.slice(0,240)}`);const data=JSON.parse(raw);const text=data?.choices?.[0]?.message?.content;if(!text)throw new Error('analyst_provider_empty_response');return clampText(text,12000);}finally{clearTimeout(timer);}}

export async function answerProvidence({message,mode='analyst',history=[],snapshot,trackRecord}){
  const safeMode=mode==='red_team'?'red_team':'analyst';const clean=clampText(message,5000).trim();if(clean.length<2)throw new Error('message_too_short');
  const context=buildAnalystContext(snapshot,trackRecord,{query:clean});const status=analystStatus();const model=safeMode==='red_team'?(config.ai.redTeamModel||config.ai.analystModel):config.ai.analystModel;
  if(context.query_scope.specific&&context.query_scope.matched_forecasts===0){
    let dynamic;try{dynamic=await buildDynamicForecast(clean,snapshot);}catch(error){return {status:'degraded',provider:'engine_only',model:null,error:String(error?.message||error),text:`Je n’ai pas trouvé de prévision existante sur ce sujet et la recherche dynamique a échoué (${String(error?.message||error)}). Je ne vais pas remplacer ta question par un scénario sans rapport.`,superposition:context.superposition,no_relevant_forecast:true};}
    const fallback=dynamicDeterministicAnswer(dynamic,safeMode);
    if(!status.configured||!model)return {status:'ok',provider:'quantic_dynamic',model:null,...fallback,superposition:dynamic.superposition};
    const compactHistory=(Array.isArray(history)?history:[]).slice(-6).map(x=>({role:x?.role==='assistant'?'assistant':'user',content:clampText(x?.content,1400)}));
    const messages=[{role:'system',content:systemPrompt(safeMode,{dynamic:true})},{role:'system',content:`RECHERCHE QUANTIC DYNAMIC FORECAST EN LECTURE SEULE:\n${JSON.stringify(dynamic).slice(0,30000)}`},...compactHistory,{role:'user',content:clean}];
    try{const text=await callModel({model,messages,temperature:safeMode==='red_team'?.35:.15});return {status:'ok',provider:'quantic_dynamic+openai-compatible',model,mode:safeMode,text,superposition:dynamic.superposition,dynamic_forecast:dynamic,execution_authority:false};}catch(error){return {status:'degraded',provider:'quantic_dynamic',model:null,error:String(error?.message||error),...fallback,superposition:dynamic.superposition};}
  }
  if(!status.configured||!model)return {status:'ok',provider:'engine_only',model:null,...engineOnlyAnswer(context,clean,safeMode),superposition:context.superposition};
  const compactHistory=(Array.isArray(history)?history:[]).slice(-8).map(x=>({role:x?.role==='assistant'?'assistant':'user',content:clampText(x?.content,1800)}));
  const messages=[{role:'system',content:systemPrompt(safeMode)},{role:'system',content:`CONTEXTE PROVIDENCE EN LECTURE SEULE:\n${JSON.stringify(context).slice(0,28000)}`},...compactHistory,{role:'user',content:clean}];
  try{const text=await callModel({model,messages,temperature:safeMode==='red_team'?.45:.2});return {status:'ok',provider:'openai-compatible',model,mode:safeMode,text,superposition:context.superposition,execution_authority:false};}catch(error){return {status:'degraded',provider:'engine_only',model:null,error:String(error?.message||error),...engineOnlyAnswer(context,clean,safeMode),superposition:context.superposition};}
}
