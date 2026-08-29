import { config } from './config.js';
import { buildSuperposition } from './superposition_engine.js';
import { analystStatus, answerProvidence } from './providence_analyst.js';

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

export function installProvidenceExtensions(app){
  if(app.__providenceExtensionsInstalled)return;
  app.__providenceExtensionsInstalled=true;

  app.get('/api/analyst/status',(_req,res)=>{
    res.set('Cache-Control','no-store');
    res.json({schema:'providence-analyst-status-v1',...analystStatus(),superposition_engine:true,red_team_read_only:true});
  });

  app.get('/api/superposition',async(req,res)=>{
    res.set('Cache-Control','public, max-age=20, stale-while-revalidate=60');
    try{
      const snapshot=await localJson('/api/snapshot');
      res.json(buildSuperposition(snapshot,{query:String(req.query.q||''),scenarioKey:String(req.query.scenario_key||''),limit:Number(req.query.limit)||4}));
    }catch(error){res.status(503).json({schema:'providence-superposition-v1',status:'unavailable',error:String(error?.message||error)});}
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
      res.json({schema:'providence-analyst-response-v1',...result});
    }catch(error){res.status(500).json({status:'error',error:String(error?.message||error)});}
  });
}
