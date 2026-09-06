import { planDynamicForecast } from './quantic_dynamic_forecast.js';

const UA='Providence-Independent-Evidence/1.0';
const clean=v=>String(v??'').replace(/\s+/g,' ').trim();
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=2)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;

async function fetchJson(url,{timeoutMs=7000}={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const res=await fetch(url,{signal:controller.signal,headers:{accept:'application/json','user-agent':UA}});
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {clearTimeout(timer);}
}

async function fetchText(url,{timeoutMs=7000}={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const res=await fetch(url,{signal:controller.signal,headers:{accept:'text/html,application/xhtml+xml','user-agent':UA}});
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally {clearTimeout(timer);}
}

function latestJsonStatValue(data){
  const values=data?.value;
  if(!values)return null;
  const entries=Array.isArray(values)
    ? values.map((v,i)=>[i,v]).filter(([,v])=>Number.isFinite(Number(v)))
    : Object.entries(values).filter(([,v])=>Number.isFinite(Number(v))).map(([k,v])=>[Number(k),v]);
  if(!entries.length)return null;
  entries.sort((a,b)=>b[0]-a[0]);
  const [idx,value]=entries[0];
  const timeIndex=data?.dimension?.time?.category?.index||data?.dimension?.time?.index||{};
  let period=null;
  for(const [label,pos] of Object.entries(timeIndex))if(Number(pos)===Number(idx)){period=label;break;}
  return {value:Number(value),period};
}

async function eurostatEvidence(spec){
  if(spec.country?.iso3!=='FRA'||!['politics','economy'].includes(spec.domain))return null;
  const requests=[
    {
      key:'unemployment',label:'Chômage harmonisé',
      url:'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?geo=FR&age=TOTAL&sex=T&s_adj=SA&unit=PC_ACT'
    },
    {
      key:'hicp',label:'Inflation harmonisée',
      url:'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?geo=FR&coicop=CP00&unit=RCH_A'
    }
  ];
  const settled=await Promise.allSettled(requests.map(async r=>({request:r,latest:latestJsonStatValue(await fetchJson(r.url,{timeoutMs:7500}))})));
  const indicators=settled.filter(x=>x.status==='fulfilled'&&x.value.latest).map(x=>({key:x.value.request.key,label:x.value.request.label,value:round(x.value.latest.value,2),period:x.value.latest.period,source_url:x.value.request.url}));
  return {
    id:'eurostat_fr_macro',family:'macro_independent_eu',correlation_group:'macro_conditions',label:'Eurostat · France',quality:92,kind:'official_statistics',contributes_to_probability:false,
    status:indicators.length?'ok':'empty',url:'https://ec.europa.eu/eurostat/',
    summary:indicators.length?`${indicators.length} indicateur(s) macroéconomique(s) indépendants de la Banque mondiale ont été récupérés.`:'Les indicateurs Eurostat sont momentanément indisponibles.',
    metrics:{indicators},independence:{source_owner:'Eurostat',same_owner_as:[],correlation_group:'macro_conditions',direct_vote_effect:false}
  };
}

async function hatvpEvidence(spec){
  if(spec.country?.iso3!=='FRA'||spec.domain!=='politics')return null;
  const url='https://www.hatvp.fr/open-data-repertoire/';
  try{
    const html=await fetchText(url,{timeoutMs:6500});
    const text=clean(html.replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' '));
    const hasJson=/format\s+\.?(?:json)|fichier\s+unique\s+au\s+format\s+\.?(?:json)/i.test(text);
    const hasCsv=/\.csv|format\s+csv|tables?\s+au\s+format\s+\.csv/i.test(text);
    const nightly=/chaque\s+nuit|mis(?:es)?\s+à\s+jour\s+.*nuit/i.test(text);
    return {
      id:'hatvp_lobbying_open_data',family:'lobbying_transparency',correlation_group:'institutional_influence',label:'HATVP · représentants d’intérêts',quality:94,kind:'official_transparency',contributes_to_probability:false,status:'ok',url,
      summary:'Le registre officiel des représentants d’intérêts est disponible comme source de contexte vérifiable. Il n’est jamais converti directement en bonus ou malus électoral.',
      metrics:{json_available:hasJson,csv_available:hasCsv,nightly_update:nightly},
      independence:{source_owner:'HATVP',same_owner_as:[],correlation_group:'institutional_influence',direct_vote_effect:false}
    };
  }catch(error){
    return {id:'hatvp_lobbying_open_data',family:'lobbying_transparency',correlation_group:'institutional_influence',label:'HATVP · représentants d’intérêts',quality:94,kind:'official_transparency',contributes_to_probability:false,status:'unavailable',url,summary:String(error?.message||error),metrics:{},independence:{source_owner:'HATVP',same_owner_as:[],correlation_group:'institutional_influence',direct_vote_effect:false}};
  }
}

export async function collectIndependentEvidence(question){
  const spec=planDynamicForecast(question);
  const tasks=[eurostatEvidence(spec),hatvpEvidence(spec)].filter(Boolean);
  const settled=await Promise.allSettled(tasks);
  const evidence=settled.map((r,i)=>r.status==='fulfilled'?r.value:{id:`independent_${i}`,family:'independent_remote',correlation_group:'unknown',label:'Source indépendante',quality:0,kind:'unavailable',contributes_to_probability:false,status:'unavailable',summary:String(r.reason?.message||r.reason||'indisponible')}).filter(Boolean);
  const ok=evidence.filter(x=>x.status==='ok');
  return {
    schema:'providence-independent-evidence-v1',generated_at:new Date().toISOString(),sources_attempted:evidence.length,sources_ok:ok.length,
    independence_score:Math.round(clamp(new Set(ok.map(x=>x.independence?.source_owner||x.family)).size/Math.max(1,evidence.length),0,1)*100),
    evidence
  };
}
