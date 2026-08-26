import { config } from './config.js';
import { buildForecasts } from './predictor.js';
import { buildBreadthForecasts } from './breadth_predictor.js';
import { selectPublicForecasts } from './public_selection.js';
import { getFutureEngineReferenceForecasts, getFutureEngineCatalogStats } from './future_engine_reference.js';

const UA = 'Evidence-World-Eye/1.1 (+functional modular predictive lab)';
const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const memo = new Map();

const GDELT_ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc';
const PUBMED_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils';
const POLYMARKET_BASE = 'https://gamma-api.polymarket.com';
const FORECAST_API = 'https://forecastapi.com/v2/forecast';
const WINDY_EMBED = 'https://embed.windy.com/embed2.html?lat=25&lon=10&zoom=2&level=surface&overlay=wind&menu=&message=&marker=&calendar=now&pressure=true&type=map&location=coordinates&detail=&metricWind=default&metricTemp=%C2%B0C&radarRange=-1';

const GDELT_THEMES = {
  cyber: { label:'Cyber & infrastructures', type:'media_cyber_disruption', query:'("cyberattack" OR ransomware OR "critical infrastructure cyber")', fallback:'cyberattack' },
  conflit: { label:'Conflits & escalade', type:'media_conflict_escalation', query:'("military escalation" OR "cross-border strike" OR "armed clashes")', fallback:'military escalation' },
  industrie: { label:'Industrie & emploi', type:'media_industrial_stress', query:'("factory closure" OR "plant closure" OR "mass layoffs" OR restructuring)', fallback:'mass layoffs' },
  energie: { label:'Électricité & réseaux', type:'media_energy_grid_stress', query:'("power outage" OR blackout OR "grid emergency" OR "electricity shortage")', fallback:'power outage' },
  alimentation: { label:'Agriculture & alimentation', type:'media_food_supply_signal', query:'("crop failure" OR "food shortage" OR "grain export" OR "agricultural losses")', fallback:'food shortage' },
  regulation: { label:'Régulation IA & numérique', type:'media_technology_regulation', query:'("AI regulation" OR "artificial intelligence regulation" OR "tech regulation" OR "digital regulation")', fallback:'AI regulation' },
  ia: { label:'IA, puces & data centers', type:'media_ai_investment', query:'("AI investment" OR "data center investment" OR "AI chips demand" OR "semiconductor investment")', fallback:'AI investment' },
  logistique: { label:'Commerce & logistique', type:'media_supply_chain_signal', query:'("port closure" OR "shipping disruption" OR "supply disruption")', fallback:'shipping disruption' },
  social: { label:'Mouvements sociaux', type:'media_civil_disruption', query:'("general strike" OR "mass protest" OR "transport strike")', fallback:'general strike' },
  commerce: { label:'Sanctions & commerce', type:'media_geopolitical_trade', query:'("export ban" OR sanctions OR "trade restriction" OR tariff)', fallback:'sanctions' },
  finance: { label:'Banques & liquidité', type:'media_financial_stress', query:'("bank run" OR "liquidity crisis" OR "bank stress")', fallback:'bank stress' }
};

const PUBMED_TOPICS = [
  { key:'immunotherapie', label:'Immunothérapie & cancer', query:'(cancer[Title] AND immunotherapy[Title/Abstract])', domain:'public_health', title:'Immunothérapie : de nouvelles validations cliniques devraient émerger dans les prochains mois.', tags:['Accès aux soins','Innovation thérapeutique'] },
  { key:'ia-medicale', label:'IA médicale', query:'("artificial intelligence"[Title] AND health[Title/Abstract])', domain:'public_health', title:'IA médicale : davantage d’essais et de validations cliniques sont probables à court-moyen terme.', tags:['Accès aux soins','Validation clinique'] },
  { key:'climat-sante', label:'Climat, santé & agriculture', query:'(climate[Title] AND (health OR agriculture)[Title/Abstract])', domain:'weather_climate', title:'Climat et santé : les travaux récents devraient accélérer de nouvelles mesures d’adaptation.', tags:['Adaptation','Sécurité alimentaire'] },
  { key:'edition-genetique', label:'Édition génétique', query:'("gene editing"[Title] OR CRISPR[Title])', domain:'public_health', title:'Édition génétique : de nouvelles applications cliniques devraient franchir des étapes de validation.', tags:['Biotechnologie','Accès aux soins'] }
];

const ARXIV_TOPICS = [
  { key:'agents-ia', label:'Agents IA & grands modèles', query:'cat:cs.AI', domain:'cyber_technology', title:'IA : l’automatisation par agents devrait gagner de nouveaux usages professionnels dans les 6–18 mois.', tags:['Productivité','Automatisation'] },
  { key:'apprentissage', label:'Apprentissage machine', query:'cat:cs.LG', domain:'cyber_technology', title:'Machine learning : de nouvelles méthodes devraient passer plus vite de la recherche aux produits.', tags:['Innovation','Logiciels'] },
  { key:'bio-informatique', label:'Bio-informatique', query:'cat:q-bio', domain:'public_health', title:'Bio-informatique : l’accélération de la recherche devrait produire de nouvelles applications biomédicales.', tags:['Recherche','Santé'] },
  { key:'systemes-sociaux', label:'Systèmes sociaux complexes', query:'cat:physics.soc-ph', domain:'social_collective_behavior', title:'Systèmes sociaux : les modèles de comportements collectifs devraient gagner en usage opérationnel.', tags:['Comportements collectifs','Décision'] }
];

const text = v => String(v ?? '').replace(/\s+/g, ' ').trim();
const clamp = (v,a,b) => Math.max(a, Math.min(b, Number(v)||0));
const hash = s => { let h=2166136261; for (const c of s) { h ^= c.charCodeAt(0); h=Math.imul(h,16777619); } return `lab-${(h>>>0).toString(16)}`; };

async function fetchJson(url, options={}, timeoutMs=18_000) {
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), timeoutMs);
  try {
    const response = await fetch(url,{...options,signal:controller.signal,headers:{'user-agent':UA,accept:'application/json',...(options.headers||{})}});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

async function fetchText(url, options={}, timeoutMs=18_000) {
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), timeoutMs);
  try {
    const response = await fetch(url,{...options,signal:controller.signal,headers:{'user-agent':UA,accept:'*/*',...(options.headers||{})}});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.text();
  } finally { clearTimeout(timer); }
}

async function cached(key, ttlMs, loader) {
  const old = memo.get(key);
  if (old && Date.now()-old.at < ttlMs) return {...old.value,cached:true};
  const value = await loader();
  memo.set(key,{at:Date.now(),value});
  return {...value,cached:false};
}

function sourceSignal({key,label,family='public_research',trust=.72,type,title,url='',facts={},severity=.55,geography='Monde',eventAt}) {
  const now = new Date().toISOString();
  return { source_key:key,source_label:label,source_family:family,source_trust:trust,observed_at:now,event_at:eventAt||now,external_key:`${key}:${hash(`${title}|${eventAt||now}`)}`,event_type:type,title,geography,severity,url,facts };
}

async function gdeltRequest(query) {
  const url = new URL(GDELT_ENDPOINT);
  url.searchParams.set('query',query);
  url.searchParams.set('mode','ArtList');
  url.searchParams.set('format','json');
  url.searchParams.set('maxrecords','75');
  url.searchParams.set('timespan','12h');
  url.searchParams.set('sort','DateDesc');
  return fetchJson(url,{},18_000);
}

async function gdeltTheme(themeKey) {
  const spec = GDELT_THEMES[themeKey];
  if (!spec) throw new Error('thème GDELT inconnu');
  let payload, usedQuery=spec.query, fallbackUsed=false;
  try { payload=await gdeltRequest(spec.query); }
  catch { payload=await gdeltRequest(spec.fallback); usedQuery=spec.fallback; fallbackUsed=true; }
  let articles = Array.isArray(payload?.articles) ? payload.articles : [];
  if (!articles.length && !fallbackUsed) {
    try { payload=await gdeltRequest(spec.fallback); articles=Array.isArray(payload?.articles)?payload.articles:[]; usedQuery=spec.fallback; fallbackUsed=true; } catch {}
  }
  const domains = new Set(articles.map(a=>a.domain).filter(Boolean));
  const signal = articles.length >= 5 && domains.size >= 3 ? sourceSignal({
    key:'gdelt-module-radar',label:'GDELT · analyse à la demande',family:'global_media_aggregator',trust:.64,type:spec.type,
    title:`Convergence médiatique : ${spec.label}`,url:articles[0]?.url||'',severity:Math.min(.80,.34+articles.length/130+domains.size/110),
    facts:{theme:themeKey,article_count:articles.length,domain_count:domains.size,sample_titles:articles.slice(0,8).map(a=>text(a.title)),on_demand_analysis:true,fallback_used:fallbackUsed}
  }) : null;
  const signals = signal ? [signal] : [];
  const forecasts = selectPublicForecasts([...buildForecasts(signals,16),...buildBreadthForecasts(signals)],12);
  return {key:'gdelt',label:'Analyse GDELT',theme:themeKey,theme_label:spec.label,items:articles.slice(0,20).map(a=>({title:text(a.title),domain:a.domain||'',url:a.url||'',seen_at:a.seendate||null})),signals,forecasts,meta:{article_count:articles.length,domain_count:domains.size,query:usedQuery,fallback_used:fallbackUsed},notice:articles.length?'':'Aucun article suffisamment récent sur cette requête ; le module fonctionne mais le signal est actuellement vide.'};
}

async function pubmedTopic(topic) {
  const sres = await fetchJson(`${PUBMED_BASE}/esearch.fcgi?db=pubmed&term=${encodeURIComponent(topic.query)}&retmax=5&sort=date&retmode=json`,{},12_000);
  const ids = sres?.esearchresult?.idlist || [];
  if (!ids.length) return [];
  const sum = await fetchJson(`${PUBMED_BASE}/esummary.fcgi?db=pubmed&id=${ids.join(',')}&retmode=json`,{},12_000);
  return ids.map(uid=>sum?.result?.[uid]).filter(Boolean).map(rec=>({uid:rec.uid||'',title:text(rec.title),date:rec.sortpubdate||rec.pubdate||'',url:`https://pubmed.ncbi.nlm.nih.gov/${rec.uid}/`}));
}

async function pubmedModule() {
  const settled=await Promise.allSettled(PUBMED_TOPICS.map(async topic=>({topic,items:await pubmedTopic(topic)})));
  const groups=settled.map((r,i)=>r.status==='fulfilled'?r.value:{topic:PUBMED_TOPICS[i],items:[]});
  const forecasts=groups.filter(g=>g.items.length).map(g=>researchForecast(g.topic,g.items,'PubMed','pubmed-research-frontier',.74,.39,[1440,13140]));
  return {key:'pubmed',label:'Radar PubMed',items:groups.flatMap(g=>g.items.slice(0,4).map(x=>({...x,topic:g.topic.label}))),forecasts,meta:{topics:PUBMED_TOPICS.length,topics_ok:groups.filter(g=>g.items.length).length}};
}

async function arxivTopic(topic) {
  const xml = await fetchText(`https://export.arxiv.org/api/query?search_query=${encodeURIComponent(topic.query)}&max_results=5&sortBy=submittedDate&sortOrder=descending`,{},14_000);
  return xml.split('<entry>').slice(1).map(entry=>{
    const title=text((entry.match(/<title>([\s\S]*?)<\/title>/)||[])[1]);
    const rawId=text((entry.match(/<id>([\s\S]*?)<\/id>/)||[])[1]);
    const id=rawId.split('/abs/')[1]||rawId;
    const date=text((entry.match(/<published>([\s\S]*?)<\/published>/)||[])[1]);
    return title&&id?{id,title,date,url:`https://arxiv.org/abs/${id}`}:null;
  }).filter(Boolean);
}

async function arxivModule() {
  const settled=await Promise.allSettled(ARXIV_TOPICS.map(async topic=>({topic,items:await arxivTopic(topic)})));
  const groups=settled.map((r,i)=>r.status==='fulfilled'?r.value:{topic:ARXIV_TOPICS[i],items:[]});
  const forecasts=groups.filter(g=>g.items.length).map(g=>researchForecast(g.topic,g.items,'arXiv','arxiv-research-frontier',.64,.34,[2160,17520]));
  return {key:'arxiv',label:'Radar arXiv',items:groups.flatMap(g=>g.items.slice(0,4).map(x=>({...x,topic:g.topic.label}))),forecasts,meta:{topics:ARXIV_TOPICS.length,topics_ok:groups.filter(g=>g.items.length).length}};
}

function horizonMeta(hours) {
  const end=hours[1];
  if(end<=72)return{tier:'immediate',label:'≤ 72 heures',order:0};
  if(end<=720)return{tier:'near',label:'Jours à semaines',order:1};
  if(end<=8760)return{tier:'medium',label:'Mois à venir',order:2};
  if(end<=26280)return{tier:'long',label:'1 à 3 ans',order:3};
  if(end<=43800)return{tier:'strategic',label:'3 à 5 ans',order:4};
  return{tier:'deep',label:'5 ans et +',order:5};
}

function researchForecast(topic, items, label, eventType, trust, prior, hours) {
  const now=Date.now(); const hm=horizonMeta(hours); const end=new Date(now+hours[1]*HOUR); const p=clamp(prior,.12,.62); const pct=Math.round(p*100);
  const scenarioKey=hash(`${eventType}|${topic.key}`);
  const evidence=items.slice(0,5).map(item=>({title:item.title,source_key:`${label.toLowerCase()}-module`,source_label:label,source_family:'public_research',source_trust:trust,url:item.url,observed_at:new Date().toISOString(),event_at:item.date||new Date().toISOString(),facts:{topic:topic.label}}));
  return {
    id:scenarioKey,scenario_key:scenarioKey,scenario_id:`${eventType}-${topic.key}`,origin_group:`${eventType}|${topic.key}`,status:'active',domain:topic.domain,event_type:eventType,
    title:topic.title,headline:topic.title,outcome:topic.title,summary:`Le radar ${label} détecte plusieurs travaux récents sur « ${topic.label} ». ÉVIDENCE ne prédit pas une découverte précise : il estime la probabilité qu’une étape de validation, d’adoption ou d’application devienne visible dans la fenêtre annoncée.`,region:'Monde',public_language:'fr',fact_status:'exploratory_forecast_from_research_frontier',
    horizon_tier:hm.tier,horizon_label:hm.label,horizon_order:hm.order,target_date:end.toISOString(),trajectory:'forming',
    probability:{type:'model_estimate',estimate:p,percent:pct,interval_low:clamp(p-.18,.03,.85),interval_high:clamp(p+.18,.10,.88),interval_percent:[Math.round(clamp(p-.18,.03,.85)*100),Math.round(clamp(p+.18,.10,.88)*100)],method:'evidence-research-frontier-v1',calibration_status:'uncalibrated_model_estimate',empirically_calibrated:false,can_be_read_as_empirical_frequency:false},
    confidence:Math.round(38+evidence.length*5),confidence_label:'exploratoire',time_window:{kind:'relative_after_research_signal',low_hours:hours[0],high_hours:hours[1],start_at:new Date(now+hours[0]*HOUR).toISOString(),end_at:end.toISOString(),target_date:end.toISOString(),human:hm.label,...hm},
    what_we_know:`${evidence.length} publications récentes sont visibles dans le radar ${label} pour ce thème.`,why_now:`Le volume de recherche récente sur « ${topic.label} » constitue un précurseur d’innovation, mais pas une preuve d’adoption.`,
    causal_chain:['recherche active','résultats reproduits / validés','essais ou prototypes','adoption ou application visible'],watch_next:['réplication indépendante','essais cliniques / benchmarks','annonces réglementaires ou industrielles'],
    favorable_signals:['réplication indépendante','nouveaux essais ou prototypes','financements ou partenariats industriels'],contrary_signals:['résultats non reproduits','absence de validation','blocage réglementaire ou technique'],probability_up_if:['réplication indépendante','validation externe'],probability_down_if:['échec de réplication','absence d’étape suivante'],human_needs:topic.tags,
    resolution_conditions:`Une étape publique de validation, essai, prototype ou adoption liée au thème devient observable avant ${end.toLocaleDateString('fr-FR')}.`,falsification:'Aucune étape de validation ou d’application significative liée au thème ne devient observable dans la fenêtre.',evidence,
    fusion:{engine:'evidence-research-frontier-v1',raw_signal_count:evidence.length,source_keys:[`${label.toLowerCase()}-module`],duplicate_probability_inflation_prevented:true,geography_aware_grouping:false,probability_recomputed_after_fusion:true,multiple_distinct_outcomes_per_precursor_allowed:false},
    consolidation:{score:Math.round(38+evidence.length*5),score_is_probability:false,level:'exploratoire',source_families:[{key:'public_research',label:'Recherche publique'}],source_providers:[{key:`${label.toLowerCase()}-module`,label,role:'frontière scientifique'}],dimensions:[],strengths:[`${evidence.length} travaux récents détectés.`],weaknesses:['Une publication n’implique pas une adoption future.','Estimation non calibrée empiriquement.']},
    novelty:'research_to_application_outcome',commercial_priority:.54,commercial_contract:{certainty_claimed:false,falsifiable:true,expiry_enforced:true}
  };
}

async function polymarketModule() {
  const params=new URLSearchParams({closed:'false',order:'volume',ascending:'false',limit:'40'});
  const markets=await fetchJson(`${POLYMARKET_BASE}/markets?${params.toString()}`,{},15_000);
  const items=(Array.isArray(markets)?markets:[]).map(m=>{
    let probability=null, outcome='Oui';
    try {
      const prices=typeof m.outcomePrices==='string'?JSON.parse(m.outcomePrices):m.outcomePrices;
      const outcomes=typeof m.outcomes==='string'?JSON.parse(m.outcomes):m.outcomes;
      if(Array.isArray(prices)) {
        let idx=0;
        if(Array.isArray(outcomes)) { const yes=outcomes.findIndex(x=>/^yes|oui$/i.test(String(x))); if(yes>=0){idx=yes;outcome=String(outcomes[yes]);} }
        if(Number.isFinite(Number(prices[idx]))) probability=Math.round(Number(prices[idx])*100);
      }
    } catch {}
    return {question:text(m.question),probability,outcome,volume:Number(m.volume||0),liquidity:Number(m.liquidity||0),end_date:m.endDate||null,url:`https://polymarket.com/event/${m.slug||m.id}`};
  }).filter(x=>x.question&&Number.isFinite(x.probability));
  return {key:'polymarket',label:'Consensus Polymarket',items:items.slice(0,30),forecasts:[],notice:'Consensus de marché externe. Ces pourcentages ne sont jamais présentés comme une probabilité calculée par ÉVIDENCE.'};
}

function xmlValue(block, tag) {
  const m=String(block||'').match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`,'i'));
  return text((m?.[1]||'').replace(/<!\[CDATA\[|\]\]>/g,''));
}

async function googleTrendsModule() {
  let raw='';
  try { raw=await fetchText('https://trends.google.com/trending/rss?geo=FR',{},12_000); } catch {}
  const items=[];
  for(const block of raw.split(/<item>/i).slice(1,31)) {
    const query=xmlValue(block,'title');
    if(!query) continue;
    const traffic=xmlValue(block,'ht:approx_traffic')||xmlValue(block,'approx_traffic');
    const link=xmlValue(block,'link')||`https://trends.google.com/trending?geo=FR&hl=fr`;
    items.push({query,traffic,url:link});
  }
  if(!items.length) items.push({query:'Tendances Google France',traffic:'ouvrir le flux actuel',url:'https://trends.google.com/trending?geo=FR&hl=fr'});
  return {key:'trends',label:'Google Trends',items,forecasts:[],notice:'Signal d’attention collective uniquement. Une hausse de recherches n’est jamais une preuve suffisante de matérialisation.'};
}

function weeklySeries(observations) {
  return [...observations].reverse().filter(x=>Number.isFinite(x.value)).slice(-52).map(x=>({date:x.date,value:x.value}));
}

async function forecastApiSeries(identifier, observations) {
  if(!config.forecastApiKey || observations.length<8) return null;
  const body={identifier,data:weeklySeries(observations),periods:4,frequency:'W',data_type:'standard',confidence_level:.8};
  const payload=await fetchJson(FORECAST_API,{method:'POST',headers:{authorization:`Bearer ${config.forecastApiKey}`,'content-type':'application/json'},body:JSON.stringify(body)},22_000);
  const rows=Array.isArray(payload?.forecast)?payload.forecast:Array.isArray(payload?.forecasts)?payload.forecasts:[];
  return {identifier,forecast:rows.slice(0,8),model_info:payload?.model_info||null};
}

async function fredModule() {
  if(!config.fredApiKey) return {key:'fred',label:'FRED + ForecastAPI',items:[],forecasts:[],notice:'Clé FRED non configurée.'};
  const series=[['VIXCLS','Volatilité VIX'],['BAMLH0A0HYM2','Spreads crédit HY'],['DCOILWTICO','Pétrole WTI'],['ICSA','Inscriptions chômage US']];
  const settled=await Promise.allSettled(series.map(async([id,label])=>{
    const u=new URL('https://api.stlouisfed.org/fred/series/observations'); u.searchParams.set('series_id',id);u.searchParams.set('api_key',config.fredApiKey);u.searchParams.set('file_type','json');u.searchParams.set('sort_order','desc');u.searchParams.set('limit','60');
    const data=await fetchJson(u,{},13_000); const obs=(data?.observations||[]).map(x=>({date:x.date,value:Number(x.value)})).filter(x=>Number.isFinite(x.value));
    let projection=null; try { projection=await forecastApiSeries(id,obs); } catch(error){ projection={error:String(error?.message||error).slice(0,120)}; }
    return {series:id,label,latest:obs[0]?.value??null,previous:obs[1]?.value??null,date:obs[0]?.date||null,url:`https://fred.stlouisfed.org/series/${id}`,projection};
  }));
  const items=settled.filter(x=>x.status==='fulfilled').map(x=>x.value);
  return {key:'fred',label:'FRED + ForecastAPI',items,forecasts:[],meta:{fred:true,forecastapi:Boolean(config.forecastApiKey),quota_guard:'cache 24 h'},notice:config.forecastApiKey?'Les intervalles ForecastAPI sont des intervalles de valeurs futures, pas des probabilités d’événement.':'FRED actif ; ForecastAPI non configuré.'};
}

function localReferenceItems(source) {
  return getFutureEngineReferenceForecasts({activeOnly:true})
    .filter(f=>(f.consolidation?.source_providers||[]).some(s=>String(s.label).toLowerCase().includes(String(source).toLowerCase())))
    .map(f=>({title:f.title,question:f.title,probability:f.probability?.percent,target_date:f.target_date,region:f.region,url:f.reference_url,origin:'Catalogue Future Engine',summary:f.summary}));
}

async function metaculusModule() {
  const items=localReferenceItems('Metaculus');
  return {key:'metaculus',label:'Metaculus + FutureEval',items,forecasts:[],meta:{api_key_detected:Boolean(config.metaculusApiKey),live_api_ingestion:false,local_reference_questions:items.length},links:[{label:'Metaculus',url:'https://www.metaculus.com/'},{label:'FutureEval',url:'https://www.metaculus.com/futureeval/'}],notice:'Module fonctionnel en mode référence : il expose les questions Metaculus déjà présentes dans le catalogue Future Engine et FutureEval. L’API Metaculus live reste volontairement hors ingestion commerciale sans accord écrit adapté.'};
}

async function windyModule() {
  const items=localReferenceItems('Windy');
  return {key:'windy',label:'Windy + World Weather Eye',items,forecasts:[],map_embed_url:WINDY_EMBED,meta:{api_key_detected:Boolean(config.windyApiKey),production_evidence:false,legacy_alerts:items.length},links:[{label:'Carte météo ÉVIDENCE',url:'/intelligence/'},{label:'Windy',url:'https://www.windy.com/'}],notice:'Carte Windy active comme visualisation. Les anciennes cartes Windy du catalogue Future Engine restent des références ; les alertes HORIZON actuelles reposent sur les sources autorisées/officielles.'};
}

async function futureEngineCatalogModule() {
  const forecasts=getFutureEngineReferenceForecasts({activeOnly:true});
  return {key:'future-engine',label:'Catalogue Future Engine',items:forecasts.map(f=>({title:f.title,probability:f.probability?.percent,target_date:f.target_date,region:f.region,url:f.reference_url,source:(f.consolidation?.source_providers||[]).map(s=>s.label).join(', ')})),forecasts:[],meta:getFutureEngineCatalogStats(),notice:'Catalogue importé comme référence. Ses probabilités historiques ne sont pas rebaptisées probabilités ÉVIDENCE.'};
}

export const moduleCatalog = () => [
  {key:'future-engine',label:'Catalogue Future Engine',category:'référence',status:'actif',actionable:true,core_input:false,description:'Parcourt les prédictions de l’ancien moteur importées dans ÉVIDENCE, sans réécrire leur origine.'},
  {key:'gdelt',label:'Analyse GDELT',category:'monde',status:'actif',actionable:true,core_input:true,description:'Lance un scan thématique des médias mondiaux et transforme une convergence en scénarios réfutables.',themes:Object.entries(GDELT_THEMES).map(([key,v])=>({key,label:v.label}))},
  {key:'pubmed',label:'Radar PubMed',category:'science',status:'actif',actionable:true,core_input:true,description:'Surveille les fronts de recherche biomédicale et projette les étapes de validation ou d’adoption.'},
  {key:'arxiv',label:'Radar arXiv',category:'science',status:'actif',actionable:true,core_input:true,description:'Repère les fronts de recherche IA, machine learning, bio-informatique et systèmes sociaux.'},
  {key:'polymarket',label:'Consensus Polymarket',category:'consensus',status:'actif · référence',actionable:true,core_input:false,description:'Affiche les marchés ouverts et leur consensus, séparés de la probabilité ÉVIDENCE.'},
  {key:'trends',label:'Google Trends',category:'attention',status:'actif · référence',actionable:true,core_input:false,description:'Lit les tendances de recherche françaises actuelles comme signal d’attention collective.'},
  {key:'fred',label:'FRED + ForecastAPI',category:'macro',status:config.fredApiKey?'actif':'à configurer',actionable:true,core_input:true,description:'Lit les séries macro officielles FRED et calcule des trajectoires ForecastAPI lorsque la clé est présente.'},
  {key:'metaculus',label:'Metaculus + FutureEval',category:'benchmark',status:config.metaculusApiKey?'référence configurée':'référence locale',actionable:true,core_input:false,description:'Expose les questions Metaculus du catalogue importé et FutureEval sans injecter le consensus externe dans notre probabilité.'},
  {key:'windy',label:'Windy + Weather Eye',category:'météo',status:'actif · référence',actionable:true,core_input:false,description:'Affiche la carte Windy et les anciennes alertes météo du catalogue ; HORIZON garde ses preuves météo autorisées séparées.'}
];

export async function runLabModule(key, options={}) {
  if(key==='future-engine') return cached('future-engine-catalog',6*HOUR,futureEngineCatalogModule);
  if(key==='gdelt') return cached(`gdelt:${options.theme||'cyber'}`,20*60_000,()=>gdeltTheme(options.theme||'cyber'));
  if(key==='pubmed') return cached('pubmed',6*HOUR,pubmedModule);
  if(key==='arxiv') return cached('arxiv',6*HOUR,arxivModule);
  if(key==='polymarket') return cached('polymarket',30*60_000,polymarketModule);
  if(key==='trends') return cached('trends',30*60_000,googleTrendsModule);
  if(key==='fred') return cached('fred-module',24*HOUR,fredModule);
  if(key==='metaculus') return cached('metaculus-reference',6*HOUR,metaculusModule);
  if(key==='windy') return cached('windy-reference',60*60_000,windyModule);
  throw new Error('module inconnu');
}

export async function collectResearchModuleCandidates() {
  const [pubmed,arxiv]=await Promise.allSettled([cached('pubmed',6*HOUR,pubmedModule),cached('arxiv',6*HOUR,arxivModule)]);
  const forecasts=[]; const statuses=[];
  for(const [key,result] of [['pubmed',pubmed],['arxiv',arxiv]]){
    if(result.status==='fulfilled'){ forecasts.push(...(result.value.forecasts||[])); statuses.push({source:key,ok:true,forecasts:result.value.forecasts?.length||0}); }
    else statuses.push({source:key,ok:false,error:String(result.reason?.message||result.reason).slice(0,160)});
  }
  return {forecasts,statuses};
}
