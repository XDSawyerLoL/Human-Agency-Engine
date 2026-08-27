import { sportsBrier3 } from './sports_intelligence.js';

const round=(v,n=4)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const memory=new Map();

function topOutcome(p){
  const arr=[Number(p?.home||0),Number(p?.draw||0),Number(p?.away||0)],i=arr.indexOf(Math.max(...arr));return ['home','draw','away'][i];
}
function rowFromFixture(competition,f,at){
  return {
    fixture_key:f.fixture_key,
    country:String(competition?.country||f.country||''),league:String(competition?.name||f.competition||''),
    external_id:String(f.id||''),kickoff_at:f.utc_date||null,kickoff_date:String(f.date_local||f.utc_date||'').slice(0,10)||null,
    home_team:String(f.home||''),away_team:String(f.away||''),source:String(f.source||''),
    p_home:Number(f.probabilities?.home),p_draw:Number(f.probabilities?.draw),p_away:Number(f.probabilities?.away),
    model_pick:String(f.model_outcome||topOutcome(f.probabilities)),model_confidence:Number(f.model_confidence_percent||0)/100,
    predicted_at:at,status:'pending',outcome:null,home_score:null,away_score:null,correct:null,brier:null,resolved_at:null
  };
}
function scored(row,result){
  const p=[Number(row.p_home),Number(row.p_draw),Number(row.p_away)],outcome=result.outcome;
  return {...row,status:'resolved',outcome,home_score:Number(result.home_score),away_score:Number(result.away_score),correct:String(row.model_pick)===outcome,brier:round(sportsBrier3(p,outcome),5),resolved_at:new Date().toISOString()};
}
function calibrationBuckets(rows){
  const defs=[[0,.4,'<40%'],[.4,.5,'40–49%'],[.5,.6,'50–59%'],[.6,.7,'60–69%'],[.7,1.01,'≥70%']];
  return defs.map(([lo,hi,label])=>{const x=rows.filter(r=>Number(r.model_confidence)>=lo&&Number(r.model_confidence)<hi);return {label,n:x.length,mean_confidence:x.length?round(x.reduce((a,r)=>a+Number(r.model_confidence),0)/x.length,3):null,observed_accuracy:x.length?round(x.filter(r=>r.correct===true).length/x.length,3):null};}).filter(x=>x.n);
}
function reportFromRows(rows,{country='',league=''}={}){
  const scoped=rows.filter(r=>(!country||r.country===country)&&(!league||r.league===league)),resolved=scoped.filter(r=>r.status==='resolved'&&Number.isFinite(Number(r.brier))),pending=scoped.filter(r=>r.status==='pending');
  const byLeague=new Map();for(const r of resolved){const k=`${r.country}|${r.league}`,x=byLeague.get(k)||{country:r.country,league:r.league,n:0,brier:0,hits:0};x.n++;x.brier+=Number(r.brier);x.hits+=r.correct?1:0;byLeague.set(k,x);}
  return {schema:'evidence-sports-track-record-v1',generated_at:new Date().toISOString(),tracked_matches:scoped.length,pending_matches:pending.length,resolved_matches:resolved.length,multiclass_brier:resolved.length?round(resolved.reduce((a,r)=>a+Number(r.brier),0)/resolved.length,4):null,top_pick_accuracy:resolved.length?round(resolved.filter(r=>r.correct===true).length/resolved.length,3):null,calibration_buckets:calibrationBuckets(resolved),by_league:[...byLeague.values()].map(x=>({...x,multiclass_brier:round(x.brier/x.n,4),top_pick_accuracy:round(x.hits/x.n,3)})).sort((a,b)=>b.n-a.n),recent_resolved:[...resolved].sort((a,b)=>String(b.resolved_at).localeCompare(String(a.resolved_at))).slice(0,30),upcoming_tracked:[...pending].sort((a,b)=>String(a.kickoff_at||a.kickoff_date).localeCompare(String(b.kickoff_at||b.kickoff_date))).slice(0,30),guardrails:{probability_frozen_at_first_publication:true,result_does_not_rewrite_prediction:true,gambling_advice:false}};
}

export class SportsTrackRecord {
  constructor(bridge){this.bridge=bridge;}
  async recordPredictions(competition,fixtures=[]){
    const at=new Date().toISOString(),rows=fixtures.filter(f=>f?.fixture_key&&Number.isFinite(Number(f.probabilities?.home))).map(f=>rowFromFixture(competition,f,at));
    for(const row of rows)if(!memory.has(row.fixture_key))memory.set(row.fixture_key,row);
    if(this.bridge?.enabled&&rows.length){
      try{await this.bridge.request('/rest/v1/evidence_sports_forecasts?on_conflict=fixture_key',{method:'POST',headers:{Prefer:'resolution=ignore-duplicates,return=minimal'},body:rows});}
      catch(error){console.error('[sports-track-record:record]',String(error?.message||error));}
    }
    return rows.length;
  }
  async rows({country='',league='',status=''}={}){
    if(this.bridge?.enabled){
      try{
        const q=new URLSearchParams({select:'*',order:'predicted_at.desc',limit:'1000'});if(country)q.set('country',`eq.${country}`);if(league)q.set('league',`eq.${league}`);if(status)q.set('status',`eq.${status}`);
        const rows=await this.bridge.request(`/rest/v1/evidence_sports_forecasts?${q.toString()}`);if(Array.isArray(rows))return rows;
      }catch(error){console.error('[sports-track-record:rows]',String(error?.message||error));}
    }
    return [...memory.values()].filter(r=>(!country||r.country===country)&&(!league||r.league===league)&&(!status||r.status===status));
  }
  async resolveResults(results=[]){
    const resultMap=new Map(results.filter(r=>r?.fixture_key&&r.status==='finished').map(r=>[r.fixture_key,r]));if(!resultMap.size)return 0;
    const pending=await this.rows({status:'pending'});let n=0;
    for(const row of pending){const result=resultMap.get(row.fixture_key);if(!result)continue;const next=scored(row,result);memory.set(row.fixture_key,next);n++;
      if(this.bridge?.enabled){try{const key=encodeURIComponent(row.fixture_key);await this.bridge.request(`/rest/v1/evidence_sports_forecasts?fixture_key=eq.${key}`,{method:'PATCH',headers:{Prefer:'return=minimal'},body:{status:next.status,outcome:next.outcome,home_score:next.home_score,away_score:next.away_score,correct:next.correct,brier:next.brier,resolved_at:next.resolved_at}});}catch(error){console.error('[sports-track-record:resolve]',String(error?.message||error));}}
    }
    return n;
  }
  async report(scope={}){return reportFromRows(await this.rows(scope),scope);}
  async pendingCompetitions(){const rows=await this.rows({status:'pending'}),seen=new Map();for(const r of rows){const k=`${r.country}|${r.league}`;if(!seen.has(k))seen.set(k,{country:r.country,league:r.league});}return [...seen.values()].slice(0,24);}
}
