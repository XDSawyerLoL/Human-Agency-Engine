import { config } from './config.js';

const memo=new Map();
const UA='Evidence-Providence/11 (+sports-intelligence)';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=4)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const normalize=v=>String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const sigmoid=x=>1/(1+Math.exp(-x));

const FOOTBALL_DATA_CODES=[
  [/premier league/i,'PL'],[/ligue 1/i,'FL1'],[/bundesliga/i,'BL1'],[/serie a/i,'SA'],[/la liga|laliga/i,'PD'],
  [/champions league/i,'CL'],[/primeira liga/i,'PPL'],[/eredivisie/i,'DED'],[/championship/i,'ELC'],[/campeonato brasileiro|brasileir/i,'BSA']
];

async function fetchJson(url,{timeoutMs=10_000,headers={}}={}){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const r=await fetch(url,{signal:controller.signal,headers:{'user-agent':UA,accept:'application/json',...headers}});
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally { clearTimeout(timer); }
}

function outcomeOf(m){
  const h=Number(m.home_score),a=Number(m.away_score);
  if(!Number.isFinite(h)||!Number.isFinite(a)) return null;
  return h>a?'home':h===a?'draw':'away';
}
function statsBombTeam(m,side){return String(m?.[`${side}_team`]?.[`${side}_team_name`]||'');}
function brier3(pred,outcome){
  const y=outcome==='home'?[1,0,0]:outcome==='draw'?[0,1,0]:[0,0,1];
  return ((pred[0]-y[0])**2+(pred[1]-y[1])**2+(pred[2]-y[2])**2)/3;
}
function resultLabel(o){return o==='home'?'1':o==='draw'?'N':'2';}

function newModel(){return {ratings:new Map(),home:1,draw:1,away:1,played:0,forms:new Map()};}
function rating(model,team){return model.ratings.get(normalize(team))??1500;}
function form(model,team){return model.forms.get(normalize(team))??[];}
function leaguePrior(model){
  const total=model.home+model.draw+model.away;
  return [model.home/total,model.draw/total,model.away/total];
}
function predictMatch(model,homeTeam,awayTeam){
  const prior=leaguePrior(model);
  const rh=rating(model,homeTeam),ra=rating(model,awayTeam);
  const draw=clamp(prior[1],.16,.36);
  const homeDecisive=sigmoid(((rh+72)-ra)/185);
  let pHome=(1-draw)*homeDecisive;
  let pAway=(1-draw)*(1-homeDecisive);
  const hf=form(model,homeTeam),af=form(model,awayTeam);
  const formDelta=(hf.reduce((a,b)=>a+b,0)/Math.max(1,hf.length))-(af.reduce((a,b)=>a+b,0)/Math.max(1,af.length));
  const shift=clamp(formDelta*.018,-.045,.045);
  pHome=clamp(pHome+shift,.05,.85);pAway=clamp(pAway-shift,.05,.85);
  const total=pHome+draw+pAway;
  return [pHome/total,draw/total,pAway/total];
}
function updateModel(model,m){
  const outcome=outcomeOf(m);if(!outcome)return;
  const home=statsBombTeam(m,'home'),away=statsBombTeam(m,'away');
  const pred=predictMatch(model,home,away);
  const actual=outcome==='home'?1:outcome==='draw'?.5:0;
  const expected=pred[0]+.5*pred[1];
  const k=24;
  const delta=k*(actual-expected);
  model.ratings.set(normalize(home),rating(model,home)+delta);
  model.ratings.set(normalize(away),rating(model,away)-delta);
  model[outcome]++;model.played++;
  const hp=outcome==='home'?3:outcome==='draw'?1:0,ap=outcome==='away'?3:outcome==='draw'?1:0;
  model.forms.set(normalize(home),[...form(model,home),hp].slice(-5));
  model.forms.set(normalize(away),[...form(model,away),ap].slice(-5));
}

function calibrationBuckets(rows){
  const defs=[[0,.4,'<40%'],[.4,.5,'40–49%'],[.5,.6,'50–59%'],[.6,.7,'60–69%'],[.7,1.01,'≥70%']];
  return defs.map(([lo,hi,label])=>{
    const picked=rows.filter(r=>r.top_probability>=lo&&r.top_probability<hi);
    const hits=picked.filter(r=>r.correct).length;
    return {label,n:picked.length,mean_confidence:picked.length?round(picked.reduce((a,r)=>a+r.top_probability,0)/picked.length,3):null,observed_accuracy:picked.length?round(hits/picked.length,3):null};
  }).filter(x=>x.n);
}

async function competitionCatalogRaw(){
  const key='statsbomb_catalog';const cached=memo.get(key);
  if(cached&&Date.now()-cached.at<12*3600_000)return cached.value;
  const rows=await fetchJson('https://raw.githubusercontent.com/statsbomb/open-data/master/data/competitions.json',{timeoutMs:12_000});
  const value=(Array.isArray(rows)?rows:[]).filter(x=>String(x.competition_gender||'').toLowerCase()==='male');
  memo.set(key,{at:Date.now(),value});return value;
}

export async function sportsCatalog(){
  const comps=await competitionCatalogRaw();
  const countries=new Map();
  for(const c of comps){
    const country=String(c.country_name||'International');
    const arr=countries.get(country)||[];
    arr.push({competition_id:c.competition_id,season_id:c.season_id,competition_name:c.competition_name,season_name:c.season_name,match_updated:c.match_updated||null});
    countries.set(country,arr);
  }
  const out=[...countries.entries()].map(([country,seasons])=>{
    const byLeague=new Map();
    for(const s of seasons){const arr=byLeague.get(s.competition_name)||[];arr.push(s);byLeague.set(s.competition_name,arr);}
    return {country,leagues:[...byLeague.entries()].map(([name,rows])=>({name,seasons:rows.sort((a,b)=>String(b.season_name).localeCompare(String(a.season_name)))})).sort((a,b)=>a.name.localeCompare(b.name))};
  }).sort((a,b)=>a.country.localeCompare(b.country));
  return {schema:'evidence-sports-catalog-v2',provider:'StatsBomb Open Data',countries:out,competition_seasons:comps.length};
}

function chooseCompetition(comps,{country='',competitionId=null,seasonId=null,league=''}){
  let rows=[...comps];
  if(competitionId!==null&&competitionId!==undefined&&String(competitionId)!=='') rows=rows.filter(c=>String(c.competition_id)===String(competitionId));
  if(country) rows=rows.filter(c=>normalize(c.country_name)===normalize(country));
  if(league) rows=rows.filter(c=>normalize(c.competition_name).includes(normalize(league))||normalize(league).includes(normalize(c.competition_name)));
  if(seasonId!==null&&seasonId!==undefined&&String(seasonId)!=='') rows=rows.filter(c=>String(c.season_id)===String(seasonId));
  return rows.sort((a,b)=>String(b.season_name||'').localeCompare(String(a.season_name||'')))[0]||null;
}

async function nextFixturesFootballData(competitionName){
  if(!config.footballDataApiKey)return null;
  const code=(FOOTBALL_DATA_CODES.find(([re])=>re.test(competitionName))||[])[1];
  if(!code)return null;
  const data=await fetchJson(`https://api.football-data.org/v4/competitions/${code}/matches?status=SCHEDULED`,{headers:{'X-Auth-Token':config.footballDataApiKey},timeoutMs:10_000});
  return (data.matches||[]).slice(0,12).map(m=>({id:String(m.id),utc_date:m.utcDate,home:m.homeTeam?.name||'—',away:m.awayTeam?.name||'—',competition:data.competition?.name||competitionName,source:'football-data.org'}));
}

function leagueNames(row){
  return [row?.strLeague,...String(row?.strLeagueAlternate||'').split(/[,;/|]/g)].map(normalize).filter(Boolean);
}

export function sportsLeagueMatchScore(row,competitionName){
  const target=normalize(competitionName);
  if(!target)return 0;
  const targetTokens=new Set(target.split(' ').filter(x=>x.length>1));
  let best=0;
  for(const name of leagueNames(row)){
    if(name===target)best=Math.max(best,1);
    else if(name.includes(target)||target.includes(name))best=Math.max(best,.85);
    else{
      const tokens=new Set(name.split(' ').filter(x=>x.length>1));
      let common=0;for(const t of targetTokens)if(tokens.has(t))common++;
      const overlap=common/Math.max(1,Math.min(targetTokens.size,tokens.size));
      best=Math.max(best,overlap*.7);
    }
  }
  return round(best,3)||0;
}

async function nextFixturesSportsDb(country,competitionName){
  const key=encodeURIComponent(config.theSportsDbApiKey||'123');
  const c=encodeURIComponent(country||'England');
  const leagues=await fetchJson(`https://www.thesportsdb.com/api/v1/json/${key}/search_all_leagues.php?c=${c}&s=Soccer`,{timeoutMs:9_000});
  const rows=leagues?.countries||leagues?.leagues||[];
  const ranked=rows.map(row=>({row,score:sportsLeagueMatchScore(row,competitionName)})).sort((a,b)=>b.score-a.score);
  const best=ranked[0];
  // Aucun nom suffisamment proche : mieux vaut zéro fixture qu'une autre compétition présentée comme la bonne.
  if(!best?.row?.idLeague||best.score<.55)return [];
  const target=best.row;
  const data=await fetchJson(`https://www.thesportsdb.com/api/v1/json/${key}/eventsnextleague.php?id=${encodeURIComponent(target.idLeague)}`,{timeoutMs:9_000});
  return (data.events||[]).slice(0,8).map(e=>({id:String(e.idEvent||''),utc_date:e.strTimestamp||`${e.dateEvent||''}T${e.strTime||'00:00:00'}Z`,home:e.strHomeTeam||'—',away:e.strAwayTeam||'—',competition:e.strLeague||competitionName,source:'TheSportsDB',league_match_score:best.score}));
}

async function upcomingFixtures(country,competitionName){
  try{
    const full=await nextFixturesFootballData(competitionName);
    if(full?.length)return {provider:'football-data.org',coverage:'full_free_tier_when_configured',fixtures:full};
  }catch(error){console.warn('[sports] football-data',String(error?.message||error));}
  try{
    const fallback=await nextFixturesSportsDb(country,competitionName);
    return {provider:'TheSportsDB',coverage:fallback.length?'free_fallback_limited':'no_verified_league_match',fixtures:fallback};
  }catch(error){
    return {provider:'unavailable',coverage:'none',fixtures:[],error:String(error?.message||error)};
  }
}

function fixturePredictions(fixtures,model){
  return (fixtures||[]).map(f=>{
    const p=predictMatch(model,f.home,f.away);
    const labels=['1','N','2'];const best=p.indexOf(Math.max(...p));
    return {...f,probabilities:{home:round(p[0],3),draw:round(p[1],3),away:round(p[2],3),home_percent:Math.round(p[0]*100),draw_percent:Math.round(p[1]*100),away_percent:Math.round(p[2]*100)},model_pick:labels[best],model_confidence_percent:Math.round(p[best]*100),known_home_team:model.ratings.has(normalize(f.home)),known_away_team:model.ratings.has(normalize(f.away))};
  });
}

export async function sportsLeagueIntelligence(options={}){
  const comps=await competitionCatalogRaw();
  const chosen=chooseCompetition(comps,options)||chooseCompetition(comps,{country:'England',league:'Premier League'});
  if(!chosen)throw new Error('sports_competition_not_found');
  const cacheKey=`league:${chosen.competition_id}:${chosen.season_id}`;const cached=memo.get(cacheKey);
  if(cached&&Date.now()-cached.at<90*60_000)return {...cached.value,cached:true};
  const base='https://raw.githubusercontent.com/statsbomb/open-data/master/data';
  const matches=await fetchJson(`${base}/matches/${chosen.competition_id}/${chosen.season_id}.json`,{timeoutMs:12_000});
  const ordered=(Array.isArray(matches)?matches:[]).filter(m=>outcomeOf(m)).sort((a,b)=>Date.parse(a.match_date||0)-Date.parse(b.match_date||0));
  if(ordered.length<16)throw new Error('sports_history_too_small');
  const cut=Math.max(12,Math.floor(ordered.length*.7));
  const model=newModel();ordered.slice(0,cut).forEach(m=>updateModel(model,m));
  const testRows=[];
  for(const m of ordered.slice(cut)){
    const home=statsBombTeam(m,'home'),away=statsBombTeam(m,'away'),outcome=outcomeOf(m),p=predictMatch(model,home,away);
    const top=Math.max(...p),pick=['home','draw','away'][p.indexOf(top)];
    testRows.push({date:m.match_date,home,away,outcome,prediction:pick,prediction_label:resultLabel(pick),probabilities:{home:round(p[0],3),draw:round(p[1],3),away:round(p[2],3)},top_probability:top,correct:pick===outcome,brier:brier3(p,outcome)});
    updateModel(model,m);
  }
  const brier=testRows.reduce((a,r)=>a+r.brier,0)/Math.max(1,testRows.length);
  const accuracy=testRows.filter(r=>r.correct).length/Math.max(1,testRows.length);
  const prior=leaguePrior(model);
  const fixtures=await upcomingFixtures(chosen.country_name,chosen.competition_name);
  const upcoming=fixturePredictions(fixtures.fixtures,model);
  const teams=[...model.ratings.entries()].map(([key,rating])=>({key,rating:Math.round(rating),form_points:form(model,key).reduce((a,b)=>a+b,0),form_matches:form(model,key).length})).sort((a,b)=>b.rating-a.rating);
  const value={
    schema:'evidence-sports-intelligence-v2',status:'ok',generated_at:new Date().toISOString(),
    competition:{country:chosen.country_name,name:chosen.competition_name,competition_id:chosen.competition_id,season:chosen.season_name,season_id:chosen.season_id},
    historical:{provider:'StatsBomb Open Data',matches:ordered.length,training_matches:cut,test_matches:testRows.length,multiclass_brier:round(brier,4),top_pick_accuracy:round(accuracy,3),league_outcome_rates:{home:round(prior[0],3),draw:round(prior[1],3),away:round(prior[2],3)},calibration_buckets:calibrationBuckets(testRows),recent_test_matches:testRows.slice(-20).reverse()},
    model:{name:'Providence Sports Elo-Cal v1',features:['chronological Elo','home advantage','rolling draw prior','5-match form'],lookahead_prevented:true,trained_only_on_prior_matches:true},
    teams:{count:teams.length,top_ratings:teams.slice(0,12)},
    upcoming:{provider:fixtures.provider,coverage:fixtures.coverage,fixtures:upcoming,error:fixtures.error||null},
    interpretation:'Le sport sert de banc d’essai à résolution rapide pour mesurer la calibration probabiliste. Les pronostics futurs restent expérimentaux et ne sont pas des conseils de pari.',
    guardrails:{gambling_advice:false,guaranteed_outcomes:false,historical_calibration_is_general_forecasting_proof:false,unmatched_fixture_league_is_rejected:true}
  };
  memo.set(cacheKey,{at:Date.now(),value});return {...value,cached:false};
}
