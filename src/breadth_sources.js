const UA = 'Evidence-World-Eye/1.0 (+public predictive intelligence)';
const ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc';

const QUERIES = [
  { type:'media_cyber_disruption', label:'cyberattaques et perturbations numériques', query:'("cyberattack" OR ransomware OR "critical infrastructure cyber")' },
  { type:'media_conflict_escalation', label:'escalade militaire et tensions sécuritaires', query:'("military escalation" OR "cross-border strike" OR "armed clashes")' },
  { type:'media_industrial_stress', label:'fermetures d’usines, restructurations et licenciements', query:'("factory closure" OR "plant closure" OR "mass layoffs" OR restructuring)' },
  { type:'media_energy_grid_stress', label:'tensions sur les réseaux électriques et coupures', query:'("power outage" OR blackout OR "grid emergency" OR "electricity shortage")' },
  { type:'media_food_supply_signal', label:'tensions agricoles et alimentaires', query:'("crop failure" OR "food shortage" OR "grain export" OR "agricultural losses")' },
  { type:'media_technology_regulation', label:'durcissement de la régulation technologique et IA', query:'("AI regulation" OR "artificial intelligence regulation" OR "tech regulation" OR "digital regulation")' },
  { type:'media_ai_investment', label:'investissements IA, puces et centres de données', query:'("AI investment" OR "data center investment" OR "AI chips demand" OR "semiconductor investment")' }
];

function text(v){ return String(v ?? '').replace(/\s+/g,' ').trim(); }

async function fetchJson(url, timeoutMs=18000){
  const controller = new AbortController();
  const timer = setTimeout(()=>controller.abort(), timeoutMs);
  try {
    const response = await fetch(url,{signal:controller.signal,headers:{'user-agent':UA,accept:'application/json'}});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally { clearTimeout(timer); }
}

async function query(spec){
  const url = new URL(ENDPOINT);
  url.searchParams.set('query', spec.query);
  url.searchParams.set('mode','ArtList');
  url.searchParams.set('format','json');
  url.searchParams.set('maxrecords','50');
  url.searchParams.set('timespan','12h');
  url.searchParams.set('sort','DateDesc');
  const payload = await fetchJson(url,20000);
  const articles = Array.isArray(payload?.articles) ? payload.articles : [];
  const domains = new Set(articles.map(a=>a.domain).filter(Boolean));
  if(articles.length < 7 || domains.size < 4) return [];
  const now = new Date().toISOString();
  return [{
    source_key:'gdelt-breadth-radar', source_label:'GDELT · radar thématique', source_family:'global_media_aggregator', source_trust:0.64,
    observed_at:now, event_at:now, external_key:`gdelt-breadth:${spec.type}:${now.slice(0,13)}`,
    event_type:spec.type, title:`Convergence médiatique : ${spec.label}`, geography:'Monde',
    severity:Math.min(.76,.36 + articles.length/130 + domains.size/110), url:articles[0]?.url ?? '',
    facts:{article_count:articles.length,domain_count:domains.size,sample_titles:articles.slice(0,6).map(a=>text(a.title)),breadth_radar:true}
  }];
}

export async function collectBreadthSignals(){
  const started=Date.now();
  const settled=await Promise.allSettled(QUERIES.map(query));
  const signals=settled.flatMap(r=>r.status==='fulfilled'?r.value:[]);
  return {
    signals,
    status:{source:'gdelt_breadth',ok:true,signals:signals.length,queries:QUERIES.length,duration_ms:Date.now()-started}
  };
}
