import fs from 'node:fs';

const catalog = JSON.parse(fs.readFileSync(new URL('./future_engine_catalog.json', import.meta.url), 'utf8'));
const DAY = 86_400_000;
const DOMAIN_MAP = {
  'Technologie':'cyber_technology','Climat':'weather_climate','Emploi':'economy_labor','Énergie':'energy',
  'Santé':'public_health','Société':'social_collective_behavior','Géopolitique':'geopolitics_security','Économie':'financial_stress'
};

const safeKey = value => String(value || 'source').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');

function horizon(target, now=Date.now()) {
  const delta = Math.max(0, Date.parse(target) - now);
  const days = delta / DAY;
  if (days <= 3) return { tier:'immediate', label:'≤ 72 heures', order:0 };
  if (days <= 45) return { tier:'near', label:'Jours à semaines', order:1 };
  if (days <= 365) return { tier:'medium', label:'Mois à venir', order:2 };
  if (days <= 365*3) return { tier:'long', label:'1 à 3 ans', order:3 };
  if (days <= 365*5) return { tier:'strategic', label:'3 à 5 ans', order:4 };
  return { tier:'deep', label:'5 ans et +', order:5 };
}

function toForecast(row, now=Date.now()) {
  const h = horizon(row.target_date, now);
  const active = Date.parse(row.target_date) >= now;
  const p = Math.max(.01, Math.min(.99, Number(row.probability || 0)/100));
  const providers = (row.sources || []).map(label => ({ key:safeKey(label), label, role:'source déclarée par le catalogue Future Engine' }));
  return {
    id:`future-engine-${row.id}`, scenario_key:`future-engine-${row.id}`, scenario_id:`future-engine-${row.id}`,
    origin:'future_engine_catalog', origin_label:'Future Engine · catalogue importé', reference_only:true,
    status:active?'active':'expired_reference', domain:DOMAIN_MAP[row.domain] || 'social_collective_behavior', domain_label:row.domain,
    title:row.title, headline:row.title, outcome:row.title, summary:row.summary, region:row.region || 'Monde', public_language:'fr',
    target_date:row.target_date, horizon_tier:h.tier, horizon_label:h.label, horizon_order:h.order,
    probability:{ type:'legacy_reference_estimate', estimate:p, percent:Math.round(p*100), interval_low:null, interval_high:null, interval_percent:null,
      method:'future-engine-export-reference-v1', calibration_status:'unknown_external_legacy_estimate', empirically_calibrated:false, can_be_read_as_empirical_frequency:false },
    confidence:Number(row.confidence || 0), confidence_label:'solidité historique Future Engine',
    external_signal_counts:{ favorable:Number(row.favorables || 0), contrary:Number(row.contraires || 0) },
    human_needs:Array.isArray(row.impacts)?row.impacts:[], favorable_signals:[], contrary_signals:[], probability_up_if:[], probability_down_if:[],
    what_we_know:row.summary, why_now:row.summary, reference_url:row.url,
    falsification:`Le scénario n’est pas observé avant l’échéance ${String(row.target_date).slice(0,10)} ou sa condition de résolution n’est pas satisfaite.`,
    evidence:providers.map(p=>({ title:`Référence déclarée : ${p.label}`, source_key:p.key, source_label:p.label, source_family:'future_engine_reference', source_trust:null, url:row.url, observed_at:null, event_at:null })),
    consolidation:{ score:Number(row.confidence || 0), score_is_probability:false, level:'référence', source_families:[{key:'future_engine_reference',label:'Catalogue Future Engine'}], source_providers:providers,
      strengths:['Scénario récupéré depuis le catalogue Future Engine fourni dans le projet.'],
      weaknesses:['Probabilité historique : elle n’est pas recalculée par ÉVIDENCE.','Les sources originelles ne sont pas revalidées automatiquement au moment de l’import.'] },
    commercial_priority:.50, commercial_contract:{ certainty_claimed:false, falsifiable:true, expiry_enforced:true }
  };
}

export function getFutureEngineReferenceForecasts({ activeOnly=true, now=Date.now() }={}) {
  const rows = catalog.map(row=>toForecast(row,now));
  return activeOnly ? rows.filter(x=>x.status==='active') : rows;
}

export function getFutureEngineCatalogStats(now=Date.now()) {
  const rows=getFutureEngineReferenceForecasts({activeOnly:false,now});
  return { total:rows.length, active:rows.filter(x=>x.status==='active').length, expired:rows.filter(x=>x.status!=='active').length,
    sources:[...new Set(rows.flatMap(x=>(x.consolidation?.source_providers||[]).map(s=>s.label)))].sort() };
}
