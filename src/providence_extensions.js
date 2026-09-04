import { config } from './config.js';
import { buildSuperposition } from './superposition_engine.js';
import { analystStatus, answerProvidence } from './providence_analyst.js';
import { buildDynamicForecast } from './quantic_dynamic_forecast.js';
import { buildElectionModel, isFrench2027ElectionQuestion } from './election_model.js';

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

function electionSuperposition(model,fallback){
  const branches=model?.temporal_branches||[];
  if(!branches.length)return fallback;
  return {
    schema:'providence-election-superposition-v1',generated_at:model.generated_at,query:'Présidentielle française 2027',worlds:branches,
    consensus:{dominant_world_id:branches[0]?.world_id||null,branch_count:branches.length,interpretation:'configurations de second tour simulées'},
    semantics:{world_weights_are_event_probabilities:true,world_probability_kind:'model_probability_of_second_round_configuration',forecast_probabilities_remain_canonical:true,quantum_computing_claim:false}
  };
}

function electionText(model){
  if(!model||model.status==='degraded')return '';
  const rows=model?.first_round?.candidates||[];
  const top=rows.slice(0,5).map((x,i)=>`${i+1}. ${x.candidate} — ${x.qualification_probability}% de probabilité de qualification au second tour · moyenne sondages ${x.poll_average}%`).join('\n');
  const pairs=(model?.first_round?.pair_scenarios||[]).slice(0,4).map((x,i)=>`${i+1}. ${x.title} — ${x.probability_percent}%`).join('\n');
  if(!top)return `Le module Election Model a été lancé, mais les tableaux de sondages disponibles ne sont pas encore assez structurés pour produire une simulation fiable.`;
  return `Election Model a simulé ${model.methodology?.monte_carlo_iterations||0} trajectoires à partir des sondages publics structurés.\n\nQualification au second tour :\n${top}\n\nConfigurations de second tour les plus plausibles :\n${pairs||'Pas assez de données structurées.'}\n\nQualité du modèle : ${model.quality?.score||0}/100. Les sondages ne sont pas des votes ; aucun bonus causal n’est ajouté pour les banques, le lobbying ou les médias sans calibration historique.`;
}

async function buildDynamicBundle(question,snapshot){
  const dynamic=await buildDynamicForecast(question,snapshot);
  const election=isFrench2027ElectionQuestion(question)?await buildElectionModel(question):null;
  if(!election)return dynamic;
  return {...dynamic,election_model:election,superposition:electionSuperposition(election,dynamic.superposition)};
}

export function installProvidenceExtensions(app){
  if(app.__providenceExtensionsInstalled)return;
  app.__providenceExtensionsInstalled=true;

  app.get('/api/analyst/status',(_req,res)=>{
    res.set('Cache-Control','no-store');
    res.json({schema:'providence-analyst-status-v1',...analystStatus(),superposition_engine:true,dynamic_forecast_engine:true,election_model:true,red_team_read_only:true});
  });

  app.get('/api/superposition',async(req,res)=>{
    res.set('Cache-Control','public, max-age=20, stale-while-revalidate=60');
    try{
      const snapshot=await localJson('/api/snapshot');
      res.json(buildSuperposition(snapshot,{query:String(req.query.q||''),scenarioKey:String(req.query.scenario_key||''),limit:Number(req.query.limit)||4}));
    }catch(error){res.status(503).json({schema:'providence-superposition-v1',status:'unavailable',error:String(error?.message||error)});}
  });

  app.post('/api/election-model',async(req,res)=>{
    res.set('Cache-Control','no-store');
    const client=String(req.ip||req.socket?.remoteAddress||'anonymous');
    if(!allowed(`${client}:election`))return res.status(429).json({status:'error',error:'election_model_rate_limit',retry_after_seconds:60});
    try{
      const question=String(req.body?.question||req.body?.message||'Que va-t-il se passer pour les élections 2027 en France ?').trim();
      const model=await buildElectionModel(question);
      if(!model)return res.status(400).json({status:'error',error:'unsupported_election_scope'});
      res.json(model);
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
          const eText=electionText(dynamic?.election_model);
          const baseText=`J’ai lancé Quantic Dynamic Forecast car aucune prévision publiée ne couvrait suffisamment ta question. Recherche multi-source : ${dynamic?.research?.sources_ok||0}/${dynamic?.research?.sources_attempted||0} sources exploitables · couverture ${dynamic?.research?.coverage_score||0}/100.`;
          return res.json({schema:'providence-analyst-response-v1',status:'ok',provider:dynamic?.election_model?'quantic_election_model':'quantic_dynamic',model:null,mode:'analyst',text:[baseText,eText].filter(Boolean).join('\n\n'),superposition:dynamic.superposition,dynamic_forecast:dynamic,election_model:dynamic.election_model||null,execution_authority:false});
        }catch(dynamicError){
          return res.json({schema:'providence-analyst-response-v1',...result,dynamic_forecast_error:String(dynamicError?.message||dynamicError)});
        }
      }
      res.json({schema:'providence-analyst-response-v1',...result});
    }catch(error){res.status(500).json({status:'error',error:String(error?.message||error)});}
  });
}
