import { config } from './config.js';
import { buildSuperposition } from './superposition_engine.js';
import { analystStatus, answerProvidence } from './providence_analyst.js';
import { buildDynamicForecast } from './quantic_dynamic_forecast.js';
import { collectIndependentEvidence } from './quantic_independent_evidence.js';
import { buildElectionModel, isFrench2027ElectionQuestion } from './election_model.js';
import { buildElectionDeduction } from './election_deduction_engine.js';
import { buildSituationalInference, applyInferenceToBranchWeights } from './situational_inference.js';
import { buildElectionOutcomeProjection } from './election_outcome_inference.js';

const analystRuns=new Map();
const WINDOW_MS=60_000;
const MAX_CALLS=8;

async function localJson(pathname,options={}){
  const url=`http://127.0.0.1:${config.port}${pathname}`;
  const res=await fetch(url,{cache:'no-store',...options});
  if(!res.ok)throw new Error(`internal_${res.status}_${pathname}`);
  return res.json();
}

function allowed(client){
  const now=Date.now();
  const list=(analystRuns.get(client)||[]).filter(t=>now-t<WINDOW_MS);
  if(list.length>=MAX_CALLS){analystRuns.set(client,list);return false;}
  list.push(now);analystRuns.set(client,list);return true;
}

function outcomeWorlds(projection){
  return (projection?.candidates||[]).slice(0,6).map((x,i)=>({
    world_id:`election_projection_${i+1}`,scenario_key:null,title:`Victoire finale : ${x.candidate}`,domain:'politics',region:'France',horizon_label:'Présidentielle 2027',
    relative_world_weight_percent:Number(x.victory_probability_percent)||0,forecast_probability_percent:Number(x.victory_probability_percent)||0,
    probability_kind:'derived_model_probability_of_final_election_win',dynamic_research:true,source_count:0,
    interval_percent:x.interval_percent||null
  }));
}

function electionSuperposition(model,deduction,fallback,projection=null){
  const final=deduction?.final_outcome;
  if(final?.status==='publishable'&&Array.isArray(final.candidates)&&final.candidates.length){
    const worlds=final.candidates.slice(0,6).map((x,i)=>({
      world_id:`election_winner_${i+1}`,scenario_key:null,title:`Victoire finale : ${x.candidate}`,domain:'politics',region:'France',horizon_label:'Présidentielle 2027',
      relative_world_weight_percent:Number(x.win_probability_percent)||0,forecast_probability_percent:Number(x.win_probability_percent)||0,
      probability_kind:'model_probability_of_final_election_win',dynamic_research:true,source_count:x.paths?.length||0
    }));
    if(Number(final.unresolved_probability_mass_percent)>0)worlds.push({world_id:'election_unresolved',title:'Issue encore non résolue par les duels disponibles',domain:'politics',region:'France',horizon_label:'Présidentielle 2027',relative_world_weight_percent:Number(final.unresolved_probability_mass_percent)||0,forecast_probability_percent:null,probability_kind:'unresolved_probability_mass',dynamic_research:true});
    return {schema:'providence-election-superposition-v2',generated_at:model.generated_at,query:'Présidentielle française 2027',worlds,consensus:{dominant_world_id:worlds[0]?.world_id||null,branch_count:worlds.length,interpretation:`résultat final simulé · couverture des duels ${final.coverage_percent}%`},semantics:{world_weights_are_event_probabilities:true,world_probability_kind:'final_election_outcome_with_unresolved_mass',forecast_probabilities_remain_canonical:true,quantum_computing_claim:false,unresolved_mass_is_not_redistributed:true}};
  }
  if(projection?.status==='ok'&&Number(projection?.quality?.score||0)>=50){
    const worlds=outcomeWorlds(projection);
    return {schema:'providence-election-superposition-v3',generated_at:model.generated_at,query:'Présidentielle française 2027',worlds,consensus:{dominant_world_id:worlds[0]?.world_id||null,branch_count:worlds.length,interpretation:`projection finale déduite · qualité ${projection.quality.score}/100`},semantics:{world_weights_are_event_probabilities:true,world_probability_kind:'derived_final_election_projection',forecast_probabilities_remain_canonical:true,quantum_computing_claim:false,synthetic_runoffs_are_observations:false,situational_deductions_are_observations:false}};
  }
  const branches=model?.temporal_branches||[];
  if(!branches.length)return fallback;
  return {schema:'providence-election-superposition-v1',generated_at:model.generated_at,query:'Présidentielle française 2027',worlds:branches,consensus:{dominant_world_id:branches[0]?.world_id||null,branch_count:branches.length,interpretation:'configurations de second tour simulées'},semantics:{world_weights_are_event_probabilities:true,world_probability_kind:'model_probability_of_second_round_configuration',forecast_probabilities_remain_canonical:true,quantum_computing_claim:false}};
}

function situationText(situation){
  const rows=(situation?.deductions||[]).slice(0,5);
  if(!rows.length)return'';
  return `Déductions de situation :\n${rows.map((x,i)=>`${i+1}. ${x.label} — confiance d’inférence ${Math.round(Number(x.confidence||0)*100)}%`).join('\n')}\nQualité de l’assemblage : ${situation?.quality?.score||0}/100 · ${situation?.quality?.independent_evidence_families||0} familles de données.`;
}

function electionText(model,deduction,projection=null,situation=null){
  if(!model||model.status==='degraded')return '';
  const rows=model?.first_round?.candidates||[];
  const top=rows.slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — qualification au second tour ${x.qualification_probability}% · moyenne de l’hypothèse suivie ${x.poll_average}%`).join('\n');
  const pairs=(model?.first_round?.pair_scenarios||[]).slice(0,4).map((x,i)=>`${i+1}. ${x.title} — ${x.probability_percent}%`).join('\n');
  if(!top)return `Le module Election Model a été lancé, mais les tableaux de sondages disponibles ne sont pas encore assez structurés pour produire une simulation fiable.`;
  const final=deduction?.final_outcome;
  let finalBlock='';
  if(final?.status==='publishable'){
    const ranking=(final.candidates||[]).slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — victoire finale ${x.win_probability_percent}%`).join('\n');
    finalBlock=`\n\nRésultat final simulé sur les duels documentés :\n${ranking}\nMasse encore non résolue faute de duel structuré : ${final.unresolved_probability_mass_percent}% · couverture des configurations : ${final.coverage_percent}%.`;
  }else if(projection?.status==='ok'){
    const ranking=(projection.candidates||[]).slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — projection de victoire ${x.victory_probability_percent}% · intervalle ${x.interval_percent?.[0]}–${x.interval_percent?.[1]}%`).join('\n');
    finalBlock=`\n\nProjection du résultat final par assemblage de situations :\n${ranking}\nCouverture directe des sondages de duel : ${projection.coverage?.direct_head_to_head_coverage_percent||0}%. Les duels manquants utilisent un prior très prudent ramené vers 50/50 ; cette partie est une déduction du modèle, pas un sondage.`;
  }else if(final){
    finalBlock=`\n\nRésultat final : la couverture des sondages de duel est encore insuffisante (${final.coverage_percent||0}%). Providence conserve donc les configurations de second tour sans inventer un vainqueur.`;
  }
  const deductionRows=(deduction?.deductions||[]).slice(0,5).map(x=>`• ${x.statement}`).join('\n');
  const deductionBlock=deductionRows?`\n\nDéductions électorales croisées :\n${deductionRows}\nIndépendance des sources : ${deduction?.evidence_independence?.score||0}/100 · doublons supprimés : ${deduction?.evidence_independence?.duplicates_suppressed||0}.`:'';
  const situationBlock=situationText(situation);
  return `Election Model a simulé ${model.methodology?.monte_carlo_iterations||0} trajectoires puis Quantic a assemblé les scénarios, les duels, le contexte macro, les signaux médiatiques et le graphe causal appris.\n\nQualification au second tour :\n${top}\n\nConfigurations de second tour les plus plausibles :\n${pairs||'Pas assez de données structurées.'}${finalBlock}${deductionBlock}${situationBlock?`\n\n${situationBlock}`:''}\n\nQualité du modèle électoral : ${model.quality?.score||0}/100${projection?.quality?.score?` · qualité de la projection finale : ${projection.quality.score}/100`:''}. Les données économiques, médiatiques, bancaires ou de lobbying servent à construire des situations et contre-scénarios ; elles ne deviennent jamais automatiquement des points pour un candidat sans calibration historique.`;
}

function mergeIndependentEvidence(dynamic,independent){
  if(!dynamic?.research||!independent)return dynamic;
  const old=Array.isArray(dynamic.research.evidence)?dynamic.research.evidence:[];
  const extra=Array.isArray(independent.evidence)?independent.evidence:[];
  dynamic.research.evidence=[...old,...extra];
  dynamic.research.sources_attempted=Number(dynamic.research.sources_attempted||old.length)+Number(independent.sources_attempted||extra.length);
  dynamic.research.sources_ok=Number(dynamic.research.sources_ok||old.filter(x=>x?.status==='ok').length)+Number(independent.sources_ok||extra.filter(x=>x?.status==='ok').length);
  dynamic.research.independent_evidence_score=independent.independence_score;
  dynamic.research.coverage_score=Math.min(100,Math.round(Number(dynamic.research.coverage_score||0)+Math.min(14,Number(independent.sources_ok||0)*6)));
  return dynamic;
}

async function buildDynamicBundle(question,snapshot){
  const [dynamicBase,independent]=await Promise.all([buildDynamicForecast(question,snapshot),collectIndependentEvidence(question)]);
  const dynamic=mergeIndependentEvidence(dynamicBase,independent);
  const election=isFrench2027ElectionQuestion(question)?await buildElectionModel(question):null;
  const situation=buildSituationalInference({spec:dynamic.plan,evidence:dynamic?.research?.evidence||[],snapshot,electionModel:election});
  dynamic.situational_inference=situation;
  dynamic.superposition={...dynamic.superposition,worlds:applyInferenceToBranchWeights(dynamic?.superposition?.worlds||[],situation),consensus:{...(dynamic?.superposition?.consensus||{}),interpretation:situation?.deductions?.length?`futurs repondérés par ${situation.deductions.length} déduction(s) de situation`:dynamic?.superposition?.consensus?.interpretation}};
  if(!election)return {...dynamic,independent_evidence:independent,situational_inference:situation};
  const deduction=buildElectionDeduction({electionModel:election,dynamicForecast:dynamic});
  const projection=buildElectionOutcomeProjection(election,situation);
  return {...dynamic,independent_evidence:independent,election_model:election,election_deduction:deduction,election_outcome_projection:projection,situational_inference:situation,superposition:electionSuperposition(election,deduction,dynamic.superposition,projection)};
}

export function installProvidenceExtensions(app){
  if(app.__providenceExtensionsInstalled)return;
  app.__providenceExtensionsInstalled=true;

  app.get('/api/analyst/status',(_req,res)=>{
    res.set('Cache-Control','no-store');
    res.json({schema:'providence-analyst-status-v1',...analystStatus(),superposition_engine:true,dynamic_forecast_engine:true,election_model:true,election_deduction_engine:true,independent_evidence_engine:true,situational_inference_engine:true,election_outcome_inference:true,red_team_read_only:true});
  });

  app.get('/api/superposition',async(req,res)=>{
    res.set('Cache-Control','public, max-age=20, stale-while-revalidate=60');
    try{const snapshot=await localJson('/api/snapshot');res.json(buildSuperposition(snapshot,{query:String(req.query.q||''),scenarioKey:String(req.query.scenario_key||''),limit:Number(req.query.limit)||4}));}
    catch(error){res.status(503).json({schema:'providence-superposition-v1',status:'unavailable',error:String(error?.message||error)});}
  });

  app.post('/api/election-model',async(req,res)=>{
    res.set('Cache-Control','no-store');
    const client=String(req.ip||req.socket?.remoteAddress||'anonymous');
    if(!allowed(`${client}:election`))return res.status(429).json({status:'error',error:'election_model_rate_limit',retry_after_seconds:60});
    try{
      const question=String(req.body?.question||req.body?.message||'Que va-t-il se passer pour les élections 2027 en France ?').trim();
      if(!isFrench2027ElectionQuestion(question))return res.status(400).json({status:'error',error:'unsupported_election_scope'});
      const snapshot=await localJson('/api/snapshot');
      const bundle=await buildDynamicBundle(question,snapshot);
      res.json({...bundle.election_model,deduction:bundle.election_deduction,outcome_projection:bundle.election_outcome_projection,situational_inference:bundle.situational_inference,independent_evidence:bundle.independent_evidence});
    }catch(error){res.status(502).json({status:'error',error:String(error?.message||error)});}
  });

  app.post('/api/dynamic-forecast',async(req,res)=>{
    res.set('Cache-Control','no-store');
    const client=String(req.ip||req.socket?.remoteAddress||'anonymous');
    if(!allowed(`${client}:dynamic`))return res.status(429).json({status:'error',error:'dynamic_forecast_rate_limit',retry_after_seconds:60});
    try{
      const question=String(req.body?.question||req.body?.message||'').trim();
      if(question.length<8)return res.status(400).json({status:'error',error:'question_too_short'});
      const snapshot=await localJson('/api/snapshot');
      res.json(await buildDynamicBundle(question,snapshot));
    }catch(error){res.status(502).json({status:'error',error:String(error?.message||error)});}
  });

  app.post('/api/analyst/chat',async(req,res)=>{
    res.set('Cache-Control','no-store');
    const client=String(req.ip||req.socket?.remoteAddress||'anonymous');
    if(!allowed(client))return res.status(429).json({status:'error',error:'analyst_rate_limit',retry_after_seconds:60});
    try{
      const message=String(req.body?.message||'');
      if(message.trim().length<2)return res.status(400).json({status:'error',error:'message_too_short'});
      const [snapshot,trackRecord]=await Promise.all([localJson('/api/snapshot'),localJson('/api/track-record')]);
      const result=await answerProvidence({message,mode:String(req.body?.mode||'analyst'),history:Array.isArray(req.body?.history)?req.body.history:[],snapshot,trackRecord});
      if(result?.no_relevant_forecast&&message.trim().length>=8){
        try{
          const dynamic=await buildDynamicBundle(message,snapshot);
          const eText=electionText(dynamic?.election_model,dynamic?.election_deduction,dynamic?.election_outcome_projection,dynamic?.situational_inference);
          const baseText=`J’ai lancé Quantic Dynamic Forecast car aucune prévision publiée ne couvrait suffisamment ta question. Recherche multi-source : ${dynamic?.research?.sources_ok||0}/${dynamic?.research?.sources_attempted||0} sources exploitables · couverture ${dynamic?.research?.coverage_score||0}/100 · ${(dynamic?.situational_inference?.deductions||[]).length} déduction(s) de situation.`;
          const genericInference=!eText?situationText(dynamic?.situational_inference):'';
          return res.json({schema:'providence-analyst-response-v1',status:'ok',provider:dynamic?.election_model?'quantic_election_model':'quantic_dynamic',model:null,mode:'analyst',text:[baseText,eText,genericInference].filter(Boolean).join('\n\n'),superposition:dynamic.superposition,dynamic_forecast:dynamic,election_model:dynamic.election_model||null,election_deduction:dynamic.election_deduction||null,election_outcome_projection:dynamic.election_outcome_projection||null,situational_inference:dynamic.situational_inference||null,execution_authority:false});
        }catch(dynamicError){return res.json({schema:'providence-analyst-response-v1',...result,dynamic_forecast_error:String(dynamicError?.message||dynamicError)});}
      }
      res.json({schema:'providence-analyst-response-v1',...result});
    }catch(error){res.status(500).json({status:'error',error:String(error?.message||error)});}
  });
}
