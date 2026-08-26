const DAY = 86_400_000;
const clamp = (v, a, b) => Math.max(a, Math.min(b, Number(v) || 0));

const DIMENSIONS = {
  economy: { label:'Économie', icon:'€' },
  society: { label:'Société', icon:'◎' },
  health: { label:'Santé', icon:'+' },
  environment: { label:'Environnement', icon:'◇' },
  infrastructure: { label:'Infrastructures', icon:'⌁' },
  security: { label:'Sécurité', icon:'△' },
  technology: { label:'Technologie', icon:'◈' },
  policy: { label:'Décision publique', icon:'§' }
};

const DOMAIN_IMPACT = {
  natural_hazards: { environment:90, infrastructure:84, society:68, economy:56, health:58, security:44 },
  weather_climate: { environment:92, infrastructure:64, economy:58, society:52, health:48, policy:44 },
  cyber_technology: { technology:88, infrastructure:75, economy:64, security:78, society:46, policy:45 },
  public_health: { health:94, society:72, economy:48, policy:56, infrastructure:34 },
  financial_stress: { economy:94, society:58, policy:62, security:24 },
  energy: { economy:82, infrastructure:82, environment:58, society:54, policy:52 },
  economy_labor: { economy:92, society:76, policy:46, health:24 },
  supply_fuel: { economy:84, infrastructure:74, society:62, policy:42 },
  social_collective_behavior: { society:92, economy:58, security:62, policy:72 },
  geopolitics_security: { security:94, economy:68, society:58, policy:78, infrastructure:48 },
  regulation_policy: { policy:94, economy:56, society:52, technology:44 },
  transport_mobility: { infrastructure:90, economy:66, society:58, environment:30 }
};

const ACTIONS = {
  natural_hazards: {
    urgency:'immédiate',
    now:['Identifier les zones et réseaux exposés.', 'Préparer une alternative de mobilité, d’approvisionnement ou de continuité.', 'Suivre les prochains bulletins officiels avant d’engager une décision coûteuse.'],
    watch:['extension géographique', 'coupures ou fermetures', 'évacuations / restrictions'],
    avoid:'Ne pas transformer un signal d’urgence en conclusion nationale ou durable sans confirmation.',
    inaction:'Risque de réaction tardive si l’accès, les réseaux ou les services se dégradent rapidement.'
  },
  weather_climate: {
    urgency:'élevée',
    now:['Localiser l’exposition réelle des activités et personnes.', 'Préparer une mesure de continuité proportionnée au scénario.', 'Comparer la trajectoire aux alertes officielles suivantes.'],
    watch:['intensification météo', 'alertes locales', 'impacts réseau / transport'],
    avoid:'Ne pas confondre carte météo et preuve d’impact réel.',
    inaction:'Coût potentiel de préparation tardive face aux perturbations météo ou climatiques.'
  },
  cyber_technology: {
    urgency:'élevée',
    now:['Vérifier les dépendances critiques et plans de secours.', 'Renforcer la surveillance des services exposés.', 'Préparer un mode dégradé si les précurseurs se confirment.'],
    watch:['incident confirmé', 'nouveaux acteurs touchés', 'interruption de service'],
    avoid:'Éviter une réaction massive sur la seule base d’un bruit médiatique.',
    inaction:'Risque de perte de continuité ou de temps de réaction en cas d’incident réel.'
  },
  public_health: {
    urgency:'modérée',
    now:['Suivre les recommandations officielles et la géographie des cas.', 'Identifier les populations ou opérations sensibles.', 'Préparer des mesures réversibles avant toute réponse lourde.'],
    watch:['cas supplémentaires', 'extension géographique', 'hospitalisations / recommandations'],
    avoid:'Ne pas extrapoler un foyer local en crise globale.',
    inaction:'Risque de retard dans la prévention si la transmission s’étend.'
  },
  financial_stress: {
    urgency:'modérée',
    now:['Tester la sensibilité de trésorerie et de financement.', 'Comparer le scénario aux données de crédit et volatilité.', 'Préparer plusieurs options plutôt qu’un pari directionnel unique.'],
    watch:['spreads de crédit', 'volatilité', 'liquidité / annonces banques centrales'],
    avoid:'Ne pas traiter ÉVIDENCE comme un conseil d’investissement personnalisé.',
    inaction:'Risque de subir un durcissement du financement sans scénario de repli.'
  },
  economy_labor: {
    urgency:'modérée',
    now:['Identifier les secteurs et zones les plus exposés.', 'Préparer un scénario haut / central / bas.', 'Suivre emploi, faillites, commandes et consommation.'],
    watch:['offres d’emploi', 'licenciements', 'PMI / consommation'],
    avoid:'Ne pas généraliser un signal sectoriel à toute l’économie.',
    inaction:'Risque d’adaptation tardive des recrutements, stocks ou budgets.'
  },
  supply_fuel: {
    urgency:'élevée',
    now:['Cartographier fournisseurs, stocks et alternatives.', 'Identifier les points de rupture les plus proches.', 'Préparer une substitution avant la matérialisation d’une pénurie.'],
    watch:['délais de livraison', 'prix spot', 'fermetures de ports / routes'],
    avoid:'Éviter le surstockage automatique qui peut amplifier la tension.',
    inaction:'Risque de rupture ou de surcoût faute d’alternative préparée.'
  },
  geopolitics_security: {
    urgency:'élevée',
    now:['Identifier les dépendances géographiques et opérationnelles.', 'Préparer des scénarios de continuité si l’escalade progresse.', 'Attendre une convergence multi-source avant une action irréversible.'],
    watch:['mouvements militaires', 'sanctions', 'fermetures d’espace / frontières'],
    avoid:'Ne pas présenter une escalade possible comme un conflit certain.',
    inaction:'Risque d’exposition logistique, réglementaire ou sécuritaire non anticipée.'
  },
  regulation_policy: {
    urgency:'planification',
    now:['Identifier les obligations possibles et leur calendrier.', 'Préparer les adaptations réversibles à faible coût.', 'Surveiller textes officiels, consultations et votes.'],
    watch:['projet de texte', 'vote / publication', 'guidelines de mise en œuvre'],
    avoid:'Ne pas investir lourdement avant clarification réglementaire.',
    inaction:'Risque de conformité tardive ou de coût d’adaptation accéléré.'
  },
  social_collective_behavior: {
    urgency:'modérée',
    now:['Mesurer l’ampleur réelle et la dispersion géographique.', 'Préparer continuité et communication sans dramatiser.', 'Suivre les relais organisationnels et annonces officielles.'],
    watch:['participation', 'extension géographique', 'grèves / blocages'],
    avoid:'Ne pas confondre viralité en ligne et mobilisation réelle.',
    inaction:'Risque de perturbation opérationnelle si le mouvement s’élargit.'
  },
  energy: {
    urgency:'modérée',
    now:['Tester l’exposition aux prix et à la disponibilité.', 'Préparer substitution ou réduction temporaire de consommation.', 'Suivre stocks, réseau et décisions publiques.'],
    watch:['prix énergie', 'stocks', 'tension réseau / production'],
    avoid:'Ne pas extrapoler un mouvement court en tendance structurelle.',
    inaction:'Risque de coût ou de contrainte d’approvisionnement sans plan alternatif.'
  },
  transport_mobility: {
    urgency:'élevée',
    now:['Identifier itinéraires et modes alternatifs.', 'Préparer une marge horaire et logistique.', 'Suivre opérateurs et autorités locales.'],
    watch:['annulations', 'fermetures', 'retards persistants'],
    avoid:'Ne pas considérer une alerte locale comme une paralysie générale.',
    inaction:'Risque de retard ou d’interruption évitable.'
  }
};

function freshnessScore(evidence, now) {
  if (!evidence.length) return 45;
  const scores = evidence.map(e => {
    const t = Date.parse(e.observed_at || e.event_at || '');
    if (!Number.isFinite(t)) return 45;
    const ageH = Math.max(0, (now - t) / 3_600_000);
    if (ageH <= 3) return 100;
    if (ageH <= 24) return 88;
    if (ageH <= 72) return 72;
    if (ageH <= 168) return 55;
    return 35;
  });
  return Math.round(scores.reduce((a,b)=>a+b,0) / scores.length);
}

function confidenceBreakdown(f, now = Date.now()) {
  const evidence = Array.isArray(f.evidence) ? f.evidence : [];
  const sourceKeys = new Set(evidence.map(e => e.source_key).filter(Boolean));
  const families = new Set(evidence.map(e => e.source_family).filter(Boolean));
  const trusts = evidence.map(e => Number(e.source_trust)).filter(Number.isFinite);
  const reliability = trusts.length ? Math.round(trusts.reduce((a,b)=>a+b,0) / trusts.length * 100) : Math.round(Number(f.consolidation?.score || f.confidence || 48));
  const freshness = freshnessScore(evidence, now);
  const convergence = Math.round(clamp(28 + sourceKeys.size * 16 + Math.min(evidence.length, 8) * 4, 25, 100));
  const diversity = Math.round(clamp(30 + families.size * 18 + Math.max(0, sourceKeys.size - 1) * 8, 30, 100));
  const score = Math.round(reliability * .34 + freshness * .24 + convergence * .27 + diversity * .15);
  return {
    score: clamp(score, 20, 98),
    label: score >= 78 ? 'forte' : score >= 60 ? 'solide' : score >= 45 ? 'modérée' : 'fragile',
    source_count: sourceKeys.size,
    evidence_count: evidence.length,
    source_family_count: families.size,
    reliability,
    freshness,
    convergence,
    diversity,
    formula:'34% fiabilité + 24% fraîcheur + 27% convergence + 15% diversité',
    is_probability:false
  };
}

function impactAnalysis(f) {
  const base = DOMAIN_IMPACT[f.domain] || { economy:45, society:45, policy:35 };
  const p = clamp(Number(f.probability?.percent || Number(f.probability?.estimate || 0) * 100), 0, 100) / 100;
  return Object.entries(DIMENSIONS).map(([key, meta]) => {
    const severity = Math.round(clamp(base[key] || 12, 0, 100));
    const expected = Math.round(severity * (.35 + .65 * p));
    const level = expected >= 70 ? 'critique' : expected >= 52 ? 'élevé' : expected >= 32 ? 'modéré' : 'faible';
    return { key, ...meta, severity, expected, level };
  }).filter(x => x.expected >= 24).sort((a,b)=>b.expected-a.expected).slice(0,6);
}

function decisionBrief(f) {
  const spec = ACTIONS[f.domain] || ACTIONS.economy_labor;
  const p = clamp(Number(f.probability?.percent || 0), 0, 100);
  const confidence = Number(f.confidence_breakdown?.score || f.confidence || 50);
  const actionability = Math.round(clamp(p * .55 + confidence * .25 + (f.horizon_order <= 1 ? 20 : f.horizon_order <= 2 ? 12 : 6), 0, 100));
  const level = actionability >= 72 ? 'agir maintenant' : actionability >= 54 ? 'préparer' : actionability >= 38 ? 'surveiller activement' : 'observer';
  return {
    level,
    actionability,
    urgency: spec.urgency,
    primary_action: spec.now[0],
    do_now: spec.now,
    watch: [...new Set([...(f.watch_next || []).slice(0,3), ...spec.watch])].slice(0,6),
    avoid: spec.avoid,
    cost_of_inaction: spec.inaction,
    trigger_to_escalate: (f.probability_up_if || f.favorable_signals || [])[0] || spec.watch[0],
    baseline_option:{ label:'Ne rien faire', consequence:spec.inaction },
    prepared_option:{ label:'Préparer maintenant', consequence:'Réduire le temps de réaction avec des mesures proportionnées et réversibles.' },
    decisive_option:{ label:'Agir', consequence:'À réserver aux scénarios à forte probabilité, forte confiance et impact élevé.' },
    disclaimer:'Aide à la décision générale, pas un ordre automatique ni un conseil professionnel personnalisé.'
  };
}

export function enrichForecastIntelligence(f, now = Date.now()) {
  f.confidence_breakdown = confidenceBreakdown(f, now);
  f.impact_analysis = impactAnalysis(f);
  f.decision_brief = decisionBrief(f);
  f.linked_signals = (f.evidence || []).slice(0,12).map(e => ({
    title:e.title || 'Signal', source_key:e.source_key || '', source_label:e.source_label || e.source_key || 'Source',
    trust:Number.isFinite(Number(e.source_trust)) ? Math.round(Number(e.source_trust)*100) : null,
    observed_at:e.observed_at || e.event_at || null, url:e.url || '', family:e.source_family || ''
  }));
  return f;
}

function signalDomain(signal) {
  const t = String(signal.event_type || '').toLowerCase();
  if (/earthquake|wildfire|flood|storm|volcano|drought/.test(t)) return 'Environnement';
  if (/health|disease|outbreak/.test(t)) return 'Santé';
  if (/cyber|ai_|technology/.test(t)) return 'Technologie & cyber';
  if (/financial|credit|labor|industrial/.test(t)) return 'Économie & emploi';
  if (/energy|oil|grid|power/.test(t)) return 'Énergie';
  if (/conflict|geopolitical|trade|sanction/.test(t)) return 'Géopolitique';
  if (/civil|protest|social/.test(t)) return 'Société';
  if (/supply|logistic|transport/.test(t)) return 'Logistique & transport';
  return 'Autres';
}

export function uniqueSignals(signals = []) {
  const seen = new Set();
  const out = [];
  for (const s of signals) {
    const key = s.external_key || `${s.source_key}|${s.event_type}|${s.geography}|${s.title}`;
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

export function buildCycleSignalSummary(signals = [], at = new Date().toISOString()) {
  const unique = uniqueSignals(signals);
  const domains = {};
  const sources = {};
  const countries = new Set();
  for (const s of unique) {
    const d = signalDomain(s); domains[d] = (domains[d] || 0) + 1;
    const source = s.source_label || s.source_key || 'Autre'; sources[source] = (sources[source] || 0) + 1;
    const g = String(s.geography || '').trim(); if (g && !/^monde$/i.test(g)) countries.add(g);
  }
  return {
    at,
    count:unique.length,
    domains,
    sources,
    countries:[...countries].slice(0,80),
    feed:unique.slice().sort((a,b)=>Date.parse(b.observed_at||b.event_at||0)-Date.parse(a.observed_at||a.event_at||0)).slice(0,50).map(s=>({
      title:s.title, source_key:s.source_key, source_label:s.source_label, source_trust:s.source_trust,
      observed_at:s.observed_at || s.event_at, geography:s.geography || 'Monde', event_type:s.event_type, domain:signalDomain(s), url:s.url || ''
    }))
  };
}

export function buildSnapshotAnalytics(snapshot, signalAnalytics = {}) {
  const forecasts = snapshot?.forecasts || [];
  const avgProbability = forecasts.length ? Math.round(forecasts.reduce((a,f)=>a+Number(f.probability?.percent||0),0)/forecasts.length) : 0;
  const countrySet = new Set();
  forecasts.forEach(f=>{ const r=String(f.region||f.geography||'').trim(); if(r && !/^monde$/i.test(r)) countrySet.add(r); });
  const perSource = {};
  for (const f of forecasts) for (const p of (f.consolidation?.source_providers || [])) perSource[p.label || p.key] = (perSource[p.label || p.key] || 0) + 1;
  const configured = snapshot?.summary?.providers_configured || {};
  const sourceBoard = ['GDELT','Metaculus','Windy','Polymarket','PubMed','arXiv','Google Trends','FRED'].map(label=>{
    const match = Object.entries(perSource).find(([k])=>k.toLowerCase().includes(label.toLowerCase().replace('google trends','trends')));
    const count = match ? match[1] : 0;
    const reference = ['Metaculus','Windy','Polymarket','Google Trends'].includes(label);
    return { label, count, mode:reference?'référence':'moteur', configured: label==='Metaculus'?Boolean(configured.metaculus_reference_only):label==='Windy'?Boolean(configured.windy_configured_not_used_as_production_evidence):true };
  });
  const avgConfidence = forecasts.length ? Math.round(forecasts.reduce((a,f)=>a+Number(f.confidence_breakdown?.score||0),0)/forecasts.length) : 0;
  return {
    kpis:{ active_forecasts:forecasts.length, signals_analyzed:signalAnalytics.current_cycle_count ?? snapshot?.summary?.signals_considered ?? 0, average_probability:avgProbability, countries_covered:countrySet.size, average_confidence:avgConfidence },
    predictions_by_source:sourceBoard,
    signal_volume_7d:signalAnalytics.volume_7d || [],
    recent_domain_distribution:signalAnalytics.domain_distribution || {},
    realtime_signal_feed:signalAnalytics.realtime_feed || [],
    sources_fused:(snapshot?.summary?.source_catalog || []).filter(s=>s.active || s.model_input).map(s=>({label:s.label,key:s.key,model_input:s.model_input,role:s.role})),
    weather:{
      windy_configured:Boolean(configured.windy_configured_not_used_as_production_evidence),
      windy_production_evidence:false,
      map_embed_url:'https://embed.windy.com/embed2.html?lat=25&lon=10&zoom=2&level=surface&overlay=wind&menu=&message=&marker=&calendar=now&pressure=true&type=map&location=coordinates&detail=&metricWind=default&metricTemp=%C2%B0C&radarRange=-1',
      note:'Carte Windy de référence. Les alertes ÉVIDENCE restent fondées sur les sources météo/officielles autorisées tant que l’API Windy de production n’est pas autorisée pour ce domaine.'
    }
  };
}
