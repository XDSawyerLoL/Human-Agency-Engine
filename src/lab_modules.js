import { config } from './config.js';
import { buildForecasts } from './predictor.js';
import { buildBreadthForecasts } from './breadth_predictor.js';
import { selectPublicForecasts } from './public_selection.js';

const UA = 'Evidence-World-Eye/1.0 (+modular predictive lab)';
const HOUR = 3600_000;
const DAY = 24 * HOUR;
const memo = new Map();

const GDELT_ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc';
const PUBMED_BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils';
const POLYMARKET_BASE = 'https://gamma-api.polymarket.com';

const GDELT_THEMES = {
  cyber: { label:'Cyber & infrastructures', type:'media_cyber_disruption', query:'("cyberattack" OR ransomware OR "critical infrastructure cyber")' },
  conflit: { label:'Conflits & escalade', type:'media_conflict_escalation', query:'("military escalation" OR "cross-border strike" OR "armed clashes")' },
  industrie: { label:'Industrie & emploi', type:'media_industrial_stress', query:'("factory closure" OR "plant closure" OR "mass layoffs" OR restructuring)' },
  energie: { label:'Électricité & réseaux', type:'media_energy_grid_stress', query:'("power outage" OR blackout OR "grid emergency" OR "electricity shortage")' },
  alimentation: { label:'Agriculture & alimentation', type:'media_food_supply_signal', query:'("crop failure" OR "food shortage" OR "grain export" OR "agricultural losses")' },
  regulation: { label:'Régulation IA & numérique', type:'media_technology_regulation', query:'("AI regulation" OR "artificial intelligence regulation" OR "tech regulation" OR "digital regulation")' },
  ia: { label:'IA, puces & data centers', type:'media_ai_investment', query:'("AI investment" OR "data center investment" OR "AI chips demand" OR "semiconductor investment")' },
  logistique: { label:'Commerce & logistique', type:'media_supply_chain_signal', query:'("port closure" OR "shipping disruption" OR "supply disruption")' },
  social: { label:'Mouvements sociaux', type:'media_civil_disruption', query:'("general strike" OR "mass protest" OR "transport strike")' },
  commerce: { label:'Sanctions & commerce', type:'media_geopolitical_trade', query:'("export ban" OR sanctions OR "trade restriction" OR tariff)' },
  finance: { label:'Banques & liquidité', type:'media_financial_stress', query:'("bank run" OR "liquidity crisis" OR "bank stress")' }
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

async function gdeltTheme(themeKey) {
  const spec = GDELT_THEMES[themeKey];
  if (!spec) throw new Error('thème GDELT inconnu');
  const url = new URL(GDELT_ENDPOINT);
  url.searchParams.set('query',spec.query);
  url.searchParams.set('mode','ArtList');
  url.searchParams.set('format','json');
  url.searchParams.set('maxrecords','75');
  url.searchParams.set('timespan','12h');
  url.searchParams.set('sort','DateDesc');
  const payload = await fetchJson(url,{},22_000);
  const articles = Array.isArray(payload?.articles) ? payload.articles : [];
  const domains = new Set(articles.map(a=>a.domain).filter(Boolean));
  const signal = articles.length >= 5 && domains.size >= 3 ? sourceSignal({
    key:'gdelt-module-radar',label:'GDELT · analyse à la demande',family:'global_media_aggregator',trust:.64,type:spec.type,
    title:`Convergence médiatique : ${spec.label}`,url:articles[0]?.url||'',severity:Math.min(.80,.34+articles.length/130+domains.size/110),
    facts:{theme:themeKey,article_count:articles.length,domain_count:domains.size,sample_titles:articles.slice(0,8).map(a=>text(a.title)),on_demand_analysis:true}
  }) : null;
  const signals = signal ? [signal] : [];
  const forecasts = selectPublicForecasts([...buildForecasts(signals,16),...buildBreadthForecasts(signals)],12);
  return {key:'gdelt',label:'Analyse GDELT',theme:themeKey,theme_label:spec.label,items:articles.slice(0,12).map(a=>({title:text(a.title),domain:a.domain||'',url:a.url||'',seen_at:a.seendate||null})),signals,forecasts,meta:{article_count:articles.length,domain_count:domains.size}};
}

async function pubmedTopic(topic) {
  const sres = await fetchJson(`${PUBMED_BASE}/esearch.fcgi?db=pubmed&term=${encodeURIComponent(topic.query)}&retmax=5&sort=date&retmode=json`,{},16_000);
  const ids = sres?.esearchresult?.idlist || [];
  if (!ids.length) return [];
  const sum = await fetchJson(`${PUBMED_BASE}/esummary.fcgi?db=pubmed&id=${ids.join(',')}&retmode=json`,{},16_000);
  return ids.map(uid=>sum?.result?.[uid]).filter(Boolean).map(rec=>({uid:rec.uid||'',title:text(rec.title),date:rec.sortpubdate||rec.pubdate||'',url:`https://pubmed.ncbi.nlm.nih.gov/${rec.uid}/`}));
}

async function pubmedModule() {
  const groups=[];
  for (const topic of PUBMED_TOPICS) {
    try { groups.push({topic,items:await pubmedTopic(topic)}); } catch { groups.push({topic,items:[]}); }
  }
  const forecasts = groups.filter(g=>g.items.length).map(g=>researchForecast(g.topic,g.items,'PubMed','pubmed-research-frontier',.74,.39,[1440,13140]));
  return {key:'pubmed',label:'Radar PubMed',items:groups.flatMap(g=>g.items.slice(0,3).map(x=>({...x,topic:g.topic.label}))),forecasts};
}

async function arxivTopic(topic) {
  const xml = await fetchText(`https://export.arxiv.org/api/query?search_query=${encodeURIComponent(topic.query)}&max_results=5&sortBy=submittedDate&sortOrder=descending`,{},18_000);
  return xml.split('<entry>').slice(1).map(entry=>{
    const title=text((entry.match(/<title>([\s\S]*?)<\/title>/)||[])[1]);
    const rawId=text((entry.match(/<id>([\s\S]*?)<\/id>/)||[])[1]);
    const id=rawId.split('/abs/')[1]||rawId;
    const date=text((entry.match(/<published>([\s\S]*?)<\/published>/)||[])[1]);
    return title&&id?{id,title,date,url:`https://arxiv.org/abs/${id}`}:null;
  }).filter(Boolean);
}

async function arxivModule() {
  const groups=[];
  for (const topic of ARXIV_TOPICS) {
    try { groups.push({topic,items:await arxivTopic(topic)}); } catch { groups.push({topic,items:[]}); }
  }
  const forecasts = groups.filter(g=>g.items.length).map(g=>researchForecast(g.topic,g.items,'arXiv','arxiv-research-frontier',.64,.34,[2160,17520]));
  return {key:'arxiv',label:'Radar arXiv',items:groups.flatMap(g=>g.items.slice(0,3).map(x=>({...x,topic:g.topic.label}))),forecasts};
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
  const params=new URLSearchParams({closed:'false',order:'volume',ascending:'false',limit:'24'});
  const markets=await fetchJson(`${POLYMARKET_BASE}/markets?${params.toString()}`,{},18_000);
  const items=(Array.isArray(markets)?markets:[]).map(m=>{
    let probability=null;
    try { const prices=typeof m.outcomePrices==='string'?JSON.parse(m.outcomePrices):m.outcomePrices; if(Array.isArray(prices)&&Number.isFinite(Number(prices[0]))) probability=Math.round(Number(prices[0])*100); } catch {}
    return {question:text(m.question),probability,volume:Number(m.volume||0),end_date:m.endDate||null,url:`https://polymarket.com/event/${m.slug||m.id}`};
  }).filter(x=>x.question&&Number.isFinite(x.probability));
  return {key:'polymarket',label:'Consensus Polymarket',items,forecasts:[],notice:'Consensus de marché externe. Ces pourcentages ne sont jamais présentés comme une probabilité calculée par ÉVIDENCE.'};
}

async function googleTrendsModule() {
  const raw=await fetchText('https://trends.google.com/trends/api/dailytrends?hl=fr&geo=',{},18_000);
  const json=JSON.parse(raw.replace(/^[^{]*\{/,'{'));
  const days=json?.default?.trendingSearchesDays||[];
  const items=[];
  for(const day of days.slice(0,2)) for(const row of (day.trendingSearches||[])) {
    const query=text(row?.title?.query); if(!query) continue;
    items.push({query,traffic:row?.formattedTraffic||'',url:row?.articles?.[0]?.url||'https://trends.google.com/trends/'});
  }
  return {key:'trends',label:'Google Trends',items:items.slice(0,20),forecasts:[],notice:'Signal d’attention collective uniquement. Une hausse de recherches n’est pas, à elle seule, une prédiction.'};
}

async function fredModule() {
  if(!config.fredApiKey) return {key:'fred',label:'FRED + ForecastAPI',items:[],forecasts:[],notice:'Clé FRED non configurée.'};
  const series=[['VIXCLS','Volatilité VIX'],['BAMLH0A0HYM2','Spreads crédit HY'],['DCOILWTICO','Pétrole WTI'],['ICSA','Inscriptions chômage US']];
  const items=[];
  for(const [id,label] of series){
    try{
      const u=new URL('https://api.stlouisfed.org/fred/series/observations'); u.searchParams.set('series_id',id);u.searchParams.set('api_key',config.fredApiKey);u.searchParams.set('file_type','json');u.searchParams.set('sort_order','desc');u.searchParams.set('limit','8');
      const data=await fetchJson(u,{},16_000); const obs=(data?.observations||[]).map(x=>({date:x.date,value:Number(x.value)})).filter(x=>Number.isFinite(x.value));
      if(obs.length) items.push({series:id,label,latest:obs[0].value,previous:obs[1]?.value??null,date:obs[0].date,url:`https://fred.stlouisfed.org/series/${id}`});
    }catch{}
  }
  return {key:'fred',label:'FRED + ForecastAPI',items,forecasts:[],notice:'Les trajectoires statistiques FRED/ForecastAPI alimentent déjà le moteur principal lorsqu’elles franchissent les seuils de mouvement.'};
}

export const moduleCatalog = () => [
  {key:'gdelt',label:'Analyse GDELT',category:'monde',status:'actif',actionable:true,core_input:true,description:'Lance un scan thématique des médias mondiaux et transforme une convergence en scénarios réfutables.',themes:Object.entries(GDELT_THEMES).map(([key,v])=>({key,label:v.label}))},
  {key:'pubmed',label:'Radar PubMed',category:'science',status:'actif',actionable:true,core_input:true,description:'Surveille les fronts de recherche biomédicale et projette les étapes de validation ou d’adoption.'},
  {key:'arxiv',label:'Radar arXiv',category:'science',status:'actif',actionable:true,core_input:true,description:'Repère les fronts de recherche IA, machine learning, bio-informatique et systèmes sociaux.'},
  {key:'polymarket',label:'Consensus Polymarket',category:'consensus',status:'référence',actionable:true,core_input:false,description:'Affiche le consensus de marché comme référence externe, séparé du calcul ÉVIDENCE.'},
  {key:'trends',label:'Google Trends',category:'attention',status:'référence',actionable:true,core_input:false,description:'Détecte les pics d’attention collective. Signal exploratoire, jamais preuve suffisante seul.'},
  {key:'fred',label:'FRED + ForecastAPI',category:'macro',status:config.fredApiKey?'actif':'à configurer',actionable:true,core_input:true,description:'Indicateurs macro officiels et trajectoires statistiques secondaires.'},
  {key:'metaculus',label:'Metaculus',category:'consensus',status:config.metaculusApiKey?'référence configurée':'référence',actionable:false,core_input:false,description:'Référence externe uniquement. Pas injectée dans la probabilité ÉVIDENCE sans autorisation/licence adaptée.'},
  {key:'windy',label:'Windy',category:'météo',status:config.windyApiKey?'référence configurée':'référence',actionable:false,core_input:false,description:'Visualisation/référence météo. Les données de test Windy ne servent pas de preuve de production.'}
];

export async function runLabModule(key, options={}) {
  if(key==='gdelt') return cached(`gdelt:${options.theme||'cyber'}`,20*60_000,()=>gdeltTheme(options.theme||'cyber'));
  if(key==='pubmed') return cached('pubmed',12*HOUR,pubmedModule);
  if(key==='arxiv') return cached('arxiv',12*HOUR,arxivModule);
  if(key==='polymarket') return cached('polymarket',HOUR,polymarketModule);
  if(key==='trends') return cached('trends',6*HOUR,googleTrendsModule);
  if(key==='fred') return cached('fred-module',6*HOUR,fredModule);
  if(key==='metaculus') return {key,label:'Metaculus',items:[],forecasts:[],notice:'Référence externe configurée, volontairement hors calcul de probabilité.'};
  if(key==='windy') return {key,label:'Windy',items:[],forecasts:[],notice:'Référence météo uniquement ; non utilisée comme preuve de production.'};
  throw new Error('module inconnu');
}

export async function collectResearchModuleCandidates() {
  const [pubmed,arxiv]=await Promise.allSettled([cached('pubmed',12*HOUR,pubmedModule),cached('arxiv',12*HOUR,arxivModule)]);
  const forecasts=[]; const statuses=[];
  for(const [key,result] of [['pubmed',pubmed],['arxiv',arxiv]]){
    if(result.status==='fulfilled'){ forecasts.push(...(result.value.forecasts||[])); statuses.push({source:key,ok:true,forecasts:result.value.forecasts?.length||0}); }
    else statuses.push({source:key,ok:false,error:String(result.reason?.message||result.reason).slice(0,160)});
  }
  return {forecasts,statuses};
}
