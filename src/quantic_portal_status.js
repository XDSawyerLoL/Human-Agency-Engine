import { embeddedRelayPublicEndpoint } from "./quantic_embedded_relay.js";

const DEFAULT_PUBLIC_ORIGIN="https://mediumorchid-badger-314305.hostingersite.com";

function normalizedHttpsUrl(value){
  const raw=String(value||"").trim();
  if(!raw)return null;
  try{
    const parsed=new URL(raw);
    if(parsed.protocol!=="https:")return null;
    parsed.pathname=parsed.pathname.replace(/\/$/,"");
    parsed.search="";
    parsed.hash="";
    return parsed.toString().replace(/\/$/,"");
  }catch{return null;}
}

export function quanticServiceTargets(env=process.env){
  const publicOrigin=normalizedHttpsUrl(env.QUANTIC_PUBLIC_ORIGIN)||DEFAULT_PUBLIC_ORIGIN;
  const hostingerRelay=normalizedHttpsUrl(env.QUANTIC_HOSTINGER_RELAY_URL)||embeddedRelayPublicEndpoint(env);
  return Object.freeze([
    Object.freeze({ id:'vision', label:'Quantic Vision', kind:'vision', public_url:'/vision/', probe_url:`${publicOrigin}/vision/`, probe_contract:'protected-page', state:'active' }),
    Object.freeze({ id:'mail', label:'Quantic Mail', kind:'application', public_url:'/mail/', probe_url:`${publicOrigin}/mail/`, probe_contract:'protected-page', state:'active' }),
    Object.freeze({ id:'relay-render', label:'Quantic Relay · Render', kind:'relay', public_url:'https://quanticmail-network-relay.onrender.com', probe_url:'https://quanticmail-network-relay.onrender.com/api/quantic/health', probe_contract:'relay-health', state:'active' }),
    Object.freeze({ id:'relay-railway', label:'Quantic Relay · Railway', kind:'relay', public_url:'https://quantic-network-relay-backup-production.up.railway.app', probe_url:'https://quantic-network-relay-backup-production.up.railway.app/api/quantic/health', probe_contract:'relay-health', state:'active' }),
    Object.freeze(hostingerRelay
      ? { id:'relay-hostinger', label:'Quantic Relay · Hostinger', kind:'relay', public_url:hostingerRelay, probe_url:`${hostingerRelay}/api/quantic/health`, probe_contract:'relay-health', state:'active' }
      : { id:'relay-hostinger', label:'Quantic Relay · Hostinger', kind:'relay', public_url:'/network/', probe_url:null, probe_contract:'relay-health', state:'pending' })
  ]);
}

export const QUANTIC_SERVICE_TARGETS=quanticServiceTargets();

function protectedPageHealthy(response){
  if(response.status===200)return true;
  if(![301,302,303,307,308].includes(response.status))return false;
  const location=String(response.headers?.get?.('location')||'');
  return location.startsWith('/quantic/?next=')||location.includes('/quantic/?next=');
}

async function relayHealthy(response){
  if(response.status!==200)return false;
  try{
    const payload=await response.clone().json();
    return payload?.ok===true&&payload?.protocol==='quantic-relay/1';
  }catch{return false;}
}

export async function probeQuanticService(target,{timeoutMs=2500,fetchImpl=fetch}={}){
  if(!target.probe_url)return {reachable:null,functional:null,http_status:null,checked_at:new Date().toISOString()};
  try{
    const response=await fetchImpl(target.probe_url,{
      method:'GET',
      headers:{'user-agent':'Quantic-Portal-Health/2.0','accept':'application/json,text/html;q=0.9,*/*;q=0.8'},
      redirect:'manual',
      signal:AbortSignal.timeout(timeoutMs)
    });
    let functional=response.status>=200&&response.status<300;
    if(target.probe_contract==='protected-page')functional=protectedPageHealthy(response);
    if(target.probe_contract==='relay-health')functional=await relayHealthy(response);
    return {reachable:true,functional,http_status:response.status,checked_at:new Date().toISOString()};
  }catch{
    return {reachable:false,functional:false,http_status:null,checked_at:new Date().toISOString()};
  }
}

function publicService(target,result){
  return {
    id:target.id,label:target.label,kind:target.kind,url:target.public_url,state:target.state,
    reachable:result?.reachable??null,functional:result?.functional??null,http_status:result?.http_status??null,
    checked_at:result?.checked_at??null,probe_contract:target.probe_contract||null
  };
}

async function safeProbe(target,probe){
  try{return await probe(target);}
  catch{return {reachable:false,functional:false,http_status:null,checked_at:new Date().toISOString()};}
}

export async function buildQuanticPortalStatus({probe=probeQuanticService,targets=QUANTIC_SERVICE_TARGETS}={}){
  const activeTargets=targets.filter(target=>target.state!=='pending');
  const activeResults=await Promise.all(activeTargets.map(target=>safeProbe(target,probe)));
  const resultById=new Map(activeTargets.map((target,index)=>[target.id,activeResults[index]]));
  const services=targets.map(target=>publicService(target,target.state==='pending'?null:resultById.get(target.id)));
  const degraded=services.some(service=>service.state==='pending'||service.functional!==true);
  return {status:degraded?'degraded':'ok',checked_at:new Date().toISOString(),services};
}

export function installQuanticPortalStatusRoute(app){
  if(app.__quanticPortalStatusInstalled)return;
  app.__quanticPortalStatusInstalled=true;
  app.get('/api/quantic-portal/status',async(_req,res)=>{
    res.set('Cache-Control','no-store');
    const payload=await buildQuanticPortalStatus();
    res.status(payload.status==='ok'?200:503).json(payload);
  });
}
