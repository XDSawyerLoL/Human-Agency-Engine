const UA='Providence-Quantic-Dynamic-Forecast/1.0';
const STOP=new Set('que quoi qu est ce qui va t il elle ils elles se passer pour dans sur en au aux le la les un une des du de d et ou a avec sans par vers quel quelle quels quelles comment pourquoi avenir futur future futurs prediction prevision predictions previsions'.split(/\s+/));
const COUNTRY_MAP=[
  {terms:['france','francais','francaise'],name:'France',iso3:'FRA',iso2:'FR'},
  {terms:['allemagne','germany','allemand'],name:'Allemagne',iso3:'DEU',iso2:'DE'},
  {terms:['italie','italy','italien'],name:'Italie',iso3:'ITA',iso2:'IT'},
  {terms:['espagne','spain','espagnol'],name:'Espagne',iso3:'ESP',iso2:'ES'},
  {terms:['royaume uni','uk','united kingdom','britannique'],name:'Royaume-Uni',iso3:'GBR',iso2:'GB'},
  {terms:['etats unis','usa','united states','americain'],name:'États-Unis',iso3:'USA',iso2:'US'}
];
const DOMAIN_PATTERNS={
  politics:['election','elections','electoral','scrutin','vote','president','presidentielle','presidentiel','candidat','candidate','politique','gouvernement','parlement'],
  economy:['economie','economique','inflation','chomage','emploi','croissance','pib','dette','taux','pouvoir achat','banque','banques'],
  climate:['climat','meteo','canicule','chaleur','inondation','secheresse','temperature'],
  geopolitics:['guerre','conflit','ukraine','russie','chine','iran','israel','otan','sanction'],
  technology:['ia','intelligence artificielle','technologie','cyber','quantique','robot','semi conducteur'],
  health:['sante','maladie','epidemie','pandemie','vaccin','hopital']
};
const ENGLISH_EXPANSIONS={
  election:['election','poll','presidential','vote'],elections:['election','poll','presidential','vote'],presidentielle:['presidential election','poll'],politique:['politics'],
  economie:['economy'],economique:['economy'],inflation:['inflation'],chomage:['unemployment'],emploi:['employment'],croissance:['growth'],dette:['debt'],banque:['bank'],banques:['banks'],
  france:['France'],francais:['France'],francaise:['France'],lobbying:['lobbying'],lobbyisme:['lobbying'],sondage:['poll'],sondages:['polls']
};
const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=2)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const clean=v=>String(v??'').replace(/\s+/g,' ').trim();
const norm=v=>clean(v).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
const tokens=v=>[...new Set(norm(v).split(/\s+/).filter(x=>(x.length>2||/^20\d{2}$/.test(x))&&!STOP.has(x)))];
const active=f=>!['resolved','invalidated','expired'].includes(String(f?.status||'').toLowerCase());
const ftitle=f=>String(f?.title||f?.headline||f?.outcome||'Scénario');
const fprob=f=>{const p=Number(f?.probability?.percent);if(Number.isFinite(p))return clamp(p,0,100);const e=Number(f?.probability?.estimate);return Number.isFinite(e)?clamp(e*100,0,100):null};
const fconfidence=f=>clamp(Number(f?.consolidation?.score??f?.confidence??0),0,100);

function inferDomain(question){
  const q=norm(question);let best={domain:'general',score:0};
  for(const [domain,words] of Object.entries(DOMAIN_PATTERNS)){
    const score=words.reduce((n,w)=>n+(q.includes(norm(w))?1:0),0);
    if(score>best.score)best={domain,score};
  }
  return best.domain;
}
function inferCountry(question){const q=norm(question);return COUNTRY_MAP.find(c=>c.terms.some(t=>q.includes(norm(t))))||null;}
function inferYear(question){const m=norm(question).match(/\b(20\d{2})\b/);return m?Number(m[1]):null;}
function inferQuestionType(question,domain){const q=norm(question);if(domain==='politics'&&/(election|scrutin|vote|president)/.test(q))return'election';if(/gagner|vainqueur|winner|qualifie|second tour/.test(q))return'competitive_outcome';return'open_forecast';}
function queryTerms(question){return tokens(question).slice(0,12);}
function englishResearchQuery(spec){
  const parts=[];
  if(spec.country?.name)parts.push(spec.country.name);
  for(const t of spec.terms){const x=ENGLISH_EXPANSIONS[t];if(x)parts.push(...x);else if(/^20\d{2}$/.test(t))parts.push(t);}
  if(spec.domain==='politics')parts.push('politics');
  return [...new Set(parts)].slice(0,8).join(' ');
}
export function planDynamicForecast(rawQuestion){
  const question=clean(rawQuestion).slice(0,1200);if(question.length<8)throw new Error('question_too_short');
  const domain=inferDomain(question),country=inferCountry(question),year=inferYear(question),terms=queryTerms(question),question_type=inferQuestionType(question,domain);
  const dimensions=domain==='politics'?['sondages et rapports de force','situation économique','historique électoral','attention médiatique','représentation d’intérêts / lobbying','risques de rupture']:domain==='economy'?['macroéconomie','emploi','inflation','finance','attention médiatique','risques exogènes']:['prévisions existantes','signaux récents','historique','sources institutionnelles','contre-signaux'];
  return {question,domain,country,year,terms,question_type,dimensions,research_query:englishResearchQuery({domain,country,year,terms})};
}

async function fetchJson(url,{timeoutMs=6500,headers={}}={}){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{const res=await fetch(url,{signal:controller.signal,headers:{accept:'application/json','user-agent':UA,...headers}});if(!res.ok)throw new Error(`HTTP ${res.status}`);return await res.json();}finally{clearTimeout(timer);}
}

function relevance(question,forecast){
  const qt=queryTerms(question);if(!qt.length)return 0;
  const hay=norm([ftitle(forecast),forecast?.summary,forecast?.public_summary,forecast?.region,forecast?.geography,forecast?.domain,forecast?.horizon_label].filter(Boolean).join(' '));
  let score=0;for(const t of qt)if(hay.includes(t))score+=/^20\d{2}$/.test(t)?1.35:1;
  return clamp(score/Math.max(2,qt.length),0,1);
}
function localEvidence(spec,snapshot){
  const ranked=(snapshot?.forecasts||[]).filter(active).map(f=>({f,r:relevance(spec.question,f)})).filter(x=>x.r>=.12).sort((a,b)=>b.r-a.r||(fprob(b.f)||0)-(fprob(a.f)||0)).slice(0,10);
  return {
    id:'local_forecasts',family:'forecast_engine',label:'Prévisions Providence déjà publiées',quality:92,kind:'model',contributes_to_probability:true,
    status:ranked.length?'ok':'empty',summary:ranked.length?`${ranked.length} prévision(s) existante(s) recoupent partiellement la question.`:'Aucune prévision publiée ne recoupe suffisamment la question.',
    metrics:{matches:ranked.map(x=>({scenario_key:x.f?.scenario_key||null,title:ftitle(x.f),probability_percent:fprob(x.f),confidence_score:Math.round(fconfidence(x.f)),relevance:round(x.r,3),region:x.f?.region||x.f?.geography||'Monde'}))}
  };
}

async function gdeltEvidence(spec){
  const query=spec.research_query||spec.question;const u=new URL('https://api.gdeltproject.org/api/v2/doc/doc');u.searchParams.set('query',query);u.searchParams.set('mode','ArtList');u.searchParams.set('format','json');u.searchParams.set('maxrecords','50');u.searchParams.set('timespan','7d');u.searchParams.set('sort','DateDesc');
  const data=await fetchJson(u,{timeoutMs:8000});const rows=Array.isArray(data?.articles)?data.articles:[];const domains=new Set(rows.map(x=>x.domain).filter(Boolean));
  return {id:'gdelt_dynamic',family:'media_attention',label:'GDELT · recherche dynamique',quality:64,kind:'signal',contributes_to_probability:false,status:rows.length?'ok':'empty',url:String(u),summary:rows.length?`${rows.length} article(s) récents provenant de ${domains.size} domaine(s) médiatiques recoupent la recherche.`:'Aucune convergence médiatique récente détectée.',metrics:{article_count:rows.length,domain_count:domains.size,sample:rows.slice(0,8).map(x=>({title:clean(x.title),domain:x.domain||'',url:x.url||'',seen_at:x.seendate||null}))}};
}

const WB_INDICATORS=[
  ['NY.GDP.MKTP.KD.ZG','Croissance du PIB'],['FP.CPI.TOTL.ZG','Inflation'],['SL.UEM.TOTL.ZS','Chômage'],['GC.DOD.TOTL.GD.ZS','Dette publique']
];
async function worldBankEvidence(spec){
  if(!spec.country||!['politics','economy'].includes(spec.domain))return null;
  const settled=await Promise.allSettled(WB_INDICATORS.map(async([key,label])=>{const u=`https://api.worldbank.org/v2/country/${spec.country.iso3}/indicator/${key}?format=json&per_page=8`;const data=await fetchJson(u,{timeoutMs:6000});const rows=Array.isArray(data?.[1])?data[1].filter(x=>Number.isFinite(Number(x?.value))):[];const latest=rows[0],prev=rows[1];return {key,label,value:latest?Number(latest.value):null,year:latest?.date||null,previous:prev?Number(prev.value):null,previous_year:prev?.date||null,delta:latest&&prev?round(Number(latest.value)-Number(prev.value),2):null};}));
  const indicators=settled.filter(x=>x.status==='fulfilled').map(x=>x.value).filter(x=>x.value!==null);
  return {id:'world_bank_macro',family:'macro',label:`Banque mondiale · ${spec.country.name}`,quality:86,kind:'official_statistics',contributes_to_probability:false,status:indicators.length?'ok':'empty',url:`https://api.worldbank.org/v2/country/${spec.country.iso3}`,summary:indicators.length?`${indicators.length} indicateur(s) macroéconomique(s) récents intégrés comme contexte structurel.`:'Indicateurs macroéconomiques momentanément indisponibles.',metrics:{indicators}};
}

function stripHtml(value){return clean(String(value||'').replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&#39;/g,"'").replace(/&quot;/g,'"').replace(/&[a-z]+;/gi,' '));}
function parsePollingHtml(html){
  const tables=String(html||'').match(/<table[\s\S]*?<\/table>/gi)||[];const rows=[];
  for(const table of tables){for(const tr of table.match(/<tr[\s\S]*?<\/tr>/gi)||[]){const cells=(tr.match(/<(?:td|th)[\s\S]*?<\/(?:td|th)>/gi)||[]).map(stripHtml).filter(Boolean);const percentages=cells.flatMap(c=>[...(c.matchAll(/\b(\d{1,2}(?:[.,]\d+)?)\s*%/g))].map(m=>Number(m[1].replace(',','.')))).filter(x=>x>=0&&x<=100);if(percentages.length>=2)rows.push({cells:cells.slice(0,18),percentages});}}
  return {table_count:tables.length,poll_rows:rows.length,recent_vectors:rows.slice(0,12).map(r=>r.percentages.slice(0,14)),sample_rows:rows.slice(0,5).map(r=>r.cells.slice(0,12))};
}
async function wikipediaPollingEvidence(spec){
  if(!(spec.domain==='politics'&&spec.country?.iso3==='FRA'&&spec.year===2027))return null;
  const title="Liste de sondages sur l'élection présidentielle française de 2027";const u=new URL('https://fr.wikipedia.org/w/api.php');u.searchParams.set('action','parse');u.searchParams.set('format','json');u.searchParams.set('prop','text');u.searchParams.set('page',title);u.searchParams.set('origin','*');
  const data=await fetchJson(u,{timeoutMs:8000});const html=data?.parse?.text?.['*']||'';const parsed=parsePollingHtml(html);
  return {id:'fr_2027_polling',family:'polling',label:'Sondages publics · Présidentielle française 2027',quality:72,kind:'polling_aggregator',contributes_to_probability:false,status:parsed.poll_rows?'ok':'empty',url:`https://fr.wikipedia.org/wiki/Liste_de_sondages_sur_l%27élection_présidentielle_française_de_2027`,summary:parsed.poll_rows?`${parsed.poll_rows} ligne(s) de sondages publics détectées. Les chiffres servent de matière de recherche ; Providence ne les transforme pas encore automatiquement en probabilité de victoire sans identification robuste des candidats et des scénarios.`:'Aucune table de sondage exploitable détectée.',metrics:parsed};
}

async function dataGouvEvidence(spec){
  if(spec.country?.iso3!=='FRA'||spec.domain!=='politics')return null;
  const queries=['résultats élections présidentielles France','répertoire représentants intérêts HATVP'];const datasets=[];
  for(const q of queries){try{const u=new URL('https://www.data.gouv.fr/api/1/datasets/');u.searchParams.set('q',q);u.searchParams.set('page_size','4');const data=await fetchJson(u,{timeoutMs:5500});for(const d of data?.data||[])datasets.push({title:clean(d.title),organization:clean(d.organization?.name),last_update:d.last_update||d.last_modified||null,page:d.page||d.uri||null});}catch{}}
  return {id:'fr_open_data',family:'institutional_context',label:'data.gouv.fr · élections & transparence',quality:82,kind:'official_metadata',contributes_to_probability:false,status:datasets.length?'ok':'empty',url:'https://www.data.gouv.fr/',summary:datasets.length?`${datasets.length} jeu(x) de données officiels identifiés pour l’historique électoral et la transparence des intérêts.`:'Métadonnées publiques momentanément indisponibles.',metrics:{datasets:datasets.slice(0,8)}};
}

function synthesizeLocalProbability(local){
  const rows=local?.metrics?.matches||[];const strong=rows.filter(x=>x.relevance>=.25&&Number.isFinite(x.probability_percent));
  if(strong.length<2)return {probability_percent:null,coverage:0,status:'insufficient_direct_probability'};
  const total=strong.reduce((s,x)=>s+Math.max(.1,x.relevance)*Math.max(.35,(x.confidence_score||0)/100),0);if(!total)return {probability_percent:null,coverage:0,status:'insufficient_direct_probability'};
  const p=strong.reduce((s,x)=>s+x.probability_percent*Math.max(.1,x.relevance)*Math.max(.35,(x.confidence_score||0)/100),0)/total;
  return {probability_percent:Math.round(p),coverage:round(strong.reduce((s,x)=>s+x.relevance,0)/strong.length,3),status:'recomposed_from_published_forecasts'};
}
function branchTemplate(domain){
  if(domain==='politics')return [
    ['continuity','Continuité des rapports de force observés'],['recomposition','Recomposition des candidatures, alliances ou reports de voix'],['macro_shift','Bascule provoquée par le contexte économique et social'],['shock','Rupture tardive liée à un événement majeur ou une forte mobilisation']
  ];
  if(domain==='economy')return [['continuity','Poursuite de la tendance macroéconomique'],['reversal','Retournement cyclique'],['policy','Bascule liée aux décisions publiques ou monétaires'],['shock','Choc externe']];
  return [['continuity','Trajectoire dominante actuelle'],['alternative','Trajectoire concurrente'],['reversal','Retournement des signaux'],['shock','Rupture / événement exogène']];
}
function buildRelativeBranches(spec,evidence){
  const t=branchTemplate(spec.domain);let weights=[38,27,21,14];
  const poll=evidence.find(x=>x?.family==='polling'&&x.status==='ok');const macro=evidence.find(x=>x?.family==='macro'&&x.status==='ok');const media=evidence.find(x=>x?.family==='media_attention'&&x.status==='ok');
  if(poll){weights[0]+=5;weights[1]+=3;weights[3]-=4;weights[2]-=4;}if(macro){const ind=macro.metrics?.indicators||[];const stress=ind.filter(x=>['Inflation','Chômage','Dette publique'].includes(x.label)&&Number(x.delta)>0).length;if(stress>=2){weights[2]+=8;weights[0]-=5;weights[3]-=3;}}
  if(media&&Number(media.metrics?.domain_count)>=12){weights[1]+=3;weights[3]+=3;weights[0]-=4;weights[2]-=2;}
  weights=weights.map(x=>Math.max(5,x));const sum=weights.reduce((a,b)=>a+b,0);weights=weights.map(x=>Math.round(x/sum*1000)/10);const drift=Math.round((100-weights.reduce((a,b)=>a+b,0))*10)/10;weights[0]=Math.round((weights[0]+drift)*10)/10;
  return t.map(([key,title],i)=>({world_id:`dynamic_${key}`,scenario_key:null,title,domain:spec.domain,region:spec.country?.name||'Monde',horizon:spec.year?String(spec.year):'dynamique',forecast_probability_percent:null,relative_world_weight_percent:weights[i],confidence_score:null,strong_signal_count:0,weak_signal_count:0,contrary_signal_count:0,source_count:evidence.filter(x=>x?.status==='ok').length,dynamic_research:true,probability_kind:'relative_support_only',canonical_probability_untouched:true}));
}
function evidenceCoverage(evidence){const ok=evidence.filter(x=>x?.status==='ok');if(!ok.length)return 0;const families=new Set(ok.map(x=>x.family)).size;const avg=ok.reduce((s,x)=>s+Number(x.quality||0),0)/ok.length;return Math.round(clamp(families/6*.55+avg/100*.45,0,1)*100);}

export async function buildDynamicForecast(rawQuestion,snapshot={},options={}){
  const spec=planDynamicForecast(rawQuestion);const started=Date.now();const local=localEvidence(spec,snapshot);
  const tasks=[gdeltEvidence(spec),worldBankEvidence(spec),wikipediaPollingEvidence(spec),dataGouvEvidence(spec)].filter(Boolean);
  const settled=await Promise.allSettled(tasks);const evidence=[local,...settled.map((r,i)=>r.status==='fulfilled'?r.value:{id:`remote_${i}`,family:'remote',label:'Source distante',quality:0,kind:'unavailable',contributes_to_probability:false,status:'unavailable',summary:String(r.reason?.message||r.reason||'indisponible')})].filter(Boolean);
  const direct=synthesizeLocalProbability(local);const coverage=evidenceCoverage(evidence);const branches=buildRelativeBranches(spec,evidence);const ok=evidence.filter(x=>x.status==='ok');
  const missing=[];if(spec.domain==='politics'){if(!evidence.some(x=>x.family==='polling'&&x.status==='ok'))missing.push('sondages structurés');if(!evidence.some(x=>x.family==='macro'&&x.status==='ok'))missing.push('contexte macroéconomique');if(!evidence.some(x=>x.family==='institutional_context'&&x.status==='ok'))missing.push('historique électoral / transparence institutionnelle');}
  const numericAllowed=direct.probability_percent!==null;
  return {
    schema:'providence-quantic-dynamic-forecast-v1',status:'ok',generated_at:new Date().toISOString(),duration_ms:Date.now()-started,
    input:{question:spec.question},plan:spec,research:{sources_attempted:evidence.length,sources_ok:ok.length,coverage_score:coverage,dimensions:spec.dimensions,evidence,missing},
    estimate:{probability_percent:direct.probability_percent,status:direct.status,numeric_probability_allowed:numericAllowed,coverage:direct.coverage,warning:numericAllowed?'Probabilité recomposée uniquement à partir de prévisions Providence déjà publiées et pertinentes.':'Aucun pourcentage d’événement n’est publié sans couverture numérique suffisante. Les branches ci-dessous sont des poids de soutien relatifs, pas des probabilités de victoire.'},
    superposition:{schema:'providence-superposition-v1',generated_at:new Date().toISOString(),query:spec.question,scenario_key:null,worlds:branches,consensus:{dominant_world_id:branches[0]?.world_id||null,dominant_relative_weight_percent:branches[0]?.relative_world_weight_percent||null,branch_count:branches.length,entropy_bits:null,uncertainty_index:null,interpretation:coverage>=70?'recherche multi-source substantielle':coverage>=45?'recherche partielle':'couverture encore limitée'},observers:{A:'données institutionnelles et sondages',B:'signaux économiques et médiatiques',C:'contre-scénarios / ruptures'},semantics:{quantum_computing_claim:false,inspiration:'multi-hypothesis dynamic research',world_weights_are_event_probabilities:false,world_weights_mean:'relative support among dynamically researched hypotheses',forecast_probabilities_remain_canonical:true,dynamic_research:true}},
    guardrails:{no_probability_without_numeric_coverage:true,lobbying_requires_documented_public_data:true,banking_signal_is_not_causal_proof:true,media_attention_is_not_vote_intention:true,world_weights_are_not_event_probabilities:true}
  };
}
