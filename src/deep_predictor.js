const HOUR = 3600_000;
const YEAR_HOURS = 365 * 24;
const clamp = (v, a, b) => Math.max(a, Math.min(b, Number(v) || 0));
const hash = value => {
  let h = 2166136261;
  for (const c of String(value)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); }
  return `deep-${(h >>> 0).toString(16)}`;
};

const MODELS = {
  drought_emergency: {
    id:'deep-water-territory', domain:'regulation_policy', prior:.14,
    title:g=>`À 5–10 ans : possibilité d’une transformation durable de la gestion de l’eau et de l’aménagement autour de ${g}.`,
    summary:'Si le stress hydrique devient récurrent, les décisions peuvent finir par toucher stockage, réseaux, irrigation, urbanisme et localisation de certaines activités.',
    tags:['Eau','Infrastructure','Aménagement'],
    chain:['stress hydrique répété','coûts économiques récurrents','investissements lourds','gestion territoriale de l’eau transformée']
  },
  media_geopolitical_trade: {
    id:'deep-industrial-blocs', domain:'geopolitics_security', prior:.13,
    title:()=>`À 5–10 ans : possibilité d’une géographie industrielle plus régionalisée si les frictions commerciales restent chroniques.`,
    summary:'Des restrictions répétées peuvent finir par déplacer les lieux de production, les investissements et les dépendances stratégiques.',
    tags:['Industrie','Commerce','Géopolitique'],
    chain:['frictions commerciales répétées','substitutions durables','capex déplacé','géographie industrielle reconfigurée']
  },
  media_conflict_escalation: {
    id:'deep-security-architecture', domain:'geopolitics_security', prior:.12,
    title:()=>`À 5–10 ans : possibilité d’une architecture de sécurité plus coûteuse et plus régionalisée si les crises se répètent.`,
    summary:'Une succession de tensions peut modifier durablement budgets, alliances opérationnelles, chaînes d’approvisionnement et capacités industrielles de défense.',
    tags:['Sécurité','Défense','Industrie'],
    chain:['crises répétées','budgets de sécurité en hausse','capacités industrielles renforcées','architecture de sécurité durable']
  },
  media_ai_investment: {
    id:'deep-ai-infrastructure', domain:'cyber_technology', prior:.16,
    title:()=>`À 5–10 ans : possibilité d’une transformation durable des infrastructures numériques et électriques sous l’effet de l’IA.`,
    summary:'Si l’investissement actuel se prolonge, les contraintes peuvent se déplacer vers énergie, réseaux, foncier, refroidissement, semi-conducteurs et capacité de calcul.',
    tags:['IA','Électricité','Data centers'],
    chain:['capex IA durable','demande de calcul croissante','contraintes énergie / réseau','infrastructures régionales reconfigurées']
  },
  media_energy_grid_stress: {
    id:'deep-grid-rebuild', domain:'energy', prior:.13,
    title:()=>`À 5–10 ans : possibilité d’une accélération durable des investissements de réseau si les tensions électriques deviennent récurrentes.`,
    summary:'Des épisodes répétés de tension peuvent rendre inévitables de nouveaux investissements de transport, stockage, production et flexibilité.',
    tags:['Réseaux','Électricité','Investissement'],
    chain:['tensions réseau répétées','coût des incidents','plans pluriannuels','réseau renforcé / reconfiguré']
  },
  media_technology_regulation: {
    id:'deep-ai-governance', domain:'regulation_policy', prior:.12,
    title:()=>`À 5–10 ans : possibilité d’une gouvernance de l’IA beaucoup plus structurante pour les entreprises et les États.`,
    summary:'Si les règles s’empilent et convergent, la conformité, l’audit, la responsabilité et la souveraineté technologique peuvent devenir des fonctions permanentes.',
    tags:['IA','Régulation','Gouvernance'],
    chain:['règles répétées','standards convergents','contrôle permanent','gouvernance IA institutionnalisée']
  },
  energy_price_spike: {
    id:'deep-energy-substitution', domain:'energy', prior:.11,
    title:()=>`À 5–10 ans : possibilité d’une accélération durable de la substitution énergétique si les épisodes de prix élevés se répètent.`,
    summary:'La répétition de chocs énergétiques peut modifier la rentabilité des investissements d’efficacité, d’électrification et de diversification.',
    tags:['Énergie','Transition','Investissement'],
    chain:['chocs de prix répétés','coût de dépendance visible','capex de substitution','mix énergétique plus diversifié']
  }
};

function probability(signal, model) {
  const severity = clamp(signal?.severity ?? .5, 0, 1);
  const trust = clamp(signal?.source_trust ?? .65, 0, 1);
  return clamp(model.prior + (severity - .5) * .10 + (trust - .65) * .06, .06, .34);
}

export function buildDeepForecasts(signals) {
  const now = Date.now();
  const low = 5 * YEAR_HOURS;
  const high = 10 * YEAR_HOURS;
  const out = [];
  const seen = new Set();
  for (const signal of signals || []) {
    const model = MODELS[signal?.event_type];
    if (!model || seen.has(model.id)) continue;
    seen.add(model.id);
    const p = probability(signal, model);
    const pct = Math.round(p * 100);
    const geo = signal.geography || 'Monde';
    const id = hash(`${signal.event_type}|${model.id}`);
    const end = new Date(now + high * HOUR);
    const start = new Date(now + low * HOUR);
    const title = model.title(geo);
    const provider = signal.source_label || signal.source_key || 'Source publique';
    out.push({
      id, scenario_key:id, scenario_id:model.id, origin_group:`deep|${signal.event_type}`, status:'active',
      domain:model.domain, event_type:signal.event_type, title, headline:title, outcome:title, summary:model.summary, region:geo,
      public_language:'fr', fact_status:'conditional_long_range_forecast', horizon_tier:'deep', horizon_label:'5–10 ans', horizon_order:5,
      target_date:end.toISOString(), trajectory:'fragile', commercial_priority:.52,
      probability:{type:'model_estimate',estimate:p,percent:pct,interval_low:clamp(p-.13,.02,.5),interval_high:clamp(p+.16,.08,.58),interval_percent:[Math.round(clamp(p-.13,.02,.5)*100),Math.round(clamp(p+.16,.08,.58)*100)],method:'evidence-deep-conditional-v1',calibration_status:'uncalibrated_model_estimate',empirically_calibrated:false,can_be_read_as_empirical_frequency:false},
      confidence:Math.round(36 + clamp(signal.source_trust,.4,1)*24), confidence_label:'exploratoire',
      time_window:{kind:'conditional_long_range',low_hours:low,high_hours:high,start_at:start.toISOString(),end_at:end.toISOString(),target_date:end.toISOString(),human:'d’ici 5 à 10 ans',tier:'deep',label:'5–10 ans',order:5},
      what_we_know:'Un précurseur actuel est observable, mais sa persistance sur plusieurs années reste inconnue.',
      why_now:`Le signal « ${signal.title || signal.event_type} » fourni par ${provider} ouvre une trajectoire structurelle à très long terme. Cette carte reste conditionnelle à la répétition du mécanisme.`,
      causal_chain:model.chain, watch_next:model.chain.slice(1), favorable_signals:model.chain.slice(1),
      contrary_signals:['le signal actuel reste ponctuel','les investissements ou politiques prennent une direction opposée','le mécanisme disparaît pendant plusieurs années'],
      probability_up_if:model.chain.slice(1), probability_down_if:['normalisation durable','absence de répétition du signal'], human_needs:model.tags,
      resolution_conditions:`Le scénario est évalué sur l’apparition d’éléments structurels cohérents avec « ${model.chain.at(-1)} » avant ${end.toLocaleDateString('fr-FR')}.`,
      falsification:'Le précurseur ne se répète pas et aucun changement structurel cohérent n’apparaît sur la période.',
      evidence:[{title:signal.title,source_key:signal.source_key,source_label:signal.source_label,source_family:signal.source_family,source_trust:signal.source_trust,url:signal.url,observed_at:signal.observed_at,event_at:signal.event_at,facts:signal.facts}],
      fusion:{engine:'evidence-deep-conditional-v1',raw_signal_count:1,source_keys:[signal.source_key],duplicate_probability_inflation_prevented:true,geography_aware_grouping:false,probability_recomputed_after_fusion:true,multiple_distinct_outcomes_per_precursor_allowed:false},
      consolidation:{score:Math.round(36 + clamp(signal.source_trust,.4,1)*24),score_is_probability:false,level:'exploratoire',source_families:[{key:signal.source_family,label:signal.source_family}],source_providers:[{key:signal.source_key,label:provider,role:signal.source_family}],dimensions:[],strengths:['Mécanisme structurel explicite et falsifiable.'],weaknesses:['Horizon 5–10 ans : incertitude très élevée.','Le scénario dépend de la répétition du précurseur.','Estimation non calibrée empiriquement.']},
      novelty:'conditional_structural_outcome', commercial_contract:{certainty_claimed:false,falsifiable:true,expiry_enforced:true}
    });
  }
  return out;
}
