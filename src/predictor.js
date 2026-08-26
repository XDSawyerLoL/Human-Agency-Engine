import crypto from 'node:crypto';

const HOUR = 3600_000;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const sigmoid = x => 1 / (1 + Math.exp(-x));
const logit = p => Math.log(p / (1 - p));
const hash = value => crypto.createHash('sha256').update(value).digest('hex').slice(0, 24);

const PATTERNS = {
  major_earthquake: {
    domain: 'natural_hazards', prior: 0.38, hours: [0, 72], pattern: 0.84,
    headline: g => `Après le séisme : risque d’après-chocs et de perturbations d’accès autour de ${g}.`,
    known: 'Un séisme significatif vient d’être détecté.',
    chain: ['séisme significatif', 'répliques / inspection des infrastructures', 'restrictions locales et ralentissement des accès', 'perturbations de mobilité et de services'],
    watch: ['répliques M5+', 'fermetures de routes/aéroports', 'alertes tsunami ou évacuations'],
    falsify: 'Aucune réplique significative ni restriction d’accès observable avant la fin de la fenêtre.'
  },
  geomagnetic_storm_watch: {
    domain: 'cyber_technology', prior: 0.24, hours: [0, 48], pattern: 0.78,
    headline: () => 'Météo spatiale : risque accru de perturbations GNSS, radio HF et services satellitaires.',
    known: 'NOAA projette une activité géomagnétique élevée.',
    chain: ['activité solaire / géomagnétique prévue', 'dégradation de la propagation ionosphérique', 'erreurs GNSS et radio HF', 'perturbations ponctuelles de services dépendants'],
    watch: ['Kp ≥ 6', 'alertes NOAA G2+', 'rapports d’erreurs GNSS/radio'],
    falsify: 'Le pic géomagnétique n’atteint pas le niveau prévu ou aucune perturbation technique n’est rapportée dans la fenêtre.'
  },
  disease_outbreak_signal: {
    domain: 'public_health', prior: 0.31, hours: [72, 504], pattern: 0.72,
    headline: g => `Santé : risque d’intensification de la surveillance et de la pression locale autour de ${g}.`,
    known: 'L’OMS publie un signal officiel de foyer ou d’événement sanitaire.',
    chain: ['signal sanitaire officiel', 'surveillance et confirmations supplémentaires', 'adaptation des recommandations', 'pression locale sur soins, déplacements ou prévention'],
    watch: ['nouveaux cas confirmés', 'extension géographique', 'recommandations sanitaires renforcées'],
    falsify: 'Le foyer reste contenu sans extension ni renforcement des mesures pendant 21 jours.'
  },
  wildfire_emergency: {
    domain: 'natural_hazards', prior: 0.42, hours: [0, 96], pattern: 0.82,
    headline: g => `Incendies : risque d’aggravation de la qualité de l’air et de perturbations de mobilité près de ${g}.`,
    known: 'Un incendie actif est signalé par une source d’observation terrestre.',
    chain: ['incendie actif', 'fumées / propagation', 'visibilité et qualité de l’air dégradées', 'évacuations ou perturbations de transport'],
    watch: ['extension du périmètre', 'alertes qualité de l’air', 'évacuations / fermetures'],
    falsify: 'Le feu est contenu sans extension, évacuation ni dégradation notable de l’air dans la fenêtre.'
  },
  flood_emergency: {
    domain: 'natural_hazards', prior: 0.43, hours: [0, 96], pattern: 0.84,
    headline: g => `Inondations : risque de coupures d’accès et de tensions logistiques autour de ${g}.`,
    known: 'Une inondation active ou une activation d’urgence est détectée.',
    chain: ['crue / inondation', 'routes et réseaux exposés', 'accès restreints', 'retards logistiques et perturbations de services'],
    watch: ['routes coupées', 'évacuations', 'ruptures locales de réseau'],
    falsify: 'Les niveaux baissent sans coupure d’accès ni perturbation logistique notable avant l’échéance.'
  },
  severe_storm_emergency: {
    domain: 'weather_climate', prior: 0.40, hours: [0, 72], pattern: 0.80,
    headline: g => `Tempête : risque de perturbations de transport et d’électricité autour de ${g}.`,
    known: 'Une tempête sévère active est suivie par les observateurs mondiaux.',
    chain: ['tempête sévère', 'vents / pluies extrêmes', 'infrastructures exposées', 'retards, annulations et coupures ponctuelles'],
    watch: ['rafales extrêmes', 'annulations de transport', 'coupures électriques'],
    falsify: 'La tempête faiblit sans perturbation significative des transports ou de l’électricité.'
  },
  volcanic_emergency: {
    domain: 'natural_hazards', prior: 0.34, hours: [0, 168], pattern: 0.76,
    headline: g => `Volcan : risque accru de restrictions aériennes et d’exposition aux cendres près de ${g}.`,
    known: 'Une activité volcanique active est détectée.',
    chain: ['activité volcanique', 'émissions de cendres / gaz', 'zones aériennes et populations exposées', 'restrictions ou déroutements'],
    watch: ['VAAC / NOTAM', 'panache de cendres', 'évacuations'],
    falsify: 'Aucun panache significatif, restriction aérienne ou évacuation n’apparaît dans la fenêtre.'
  },
  drought_emergency: {
    domain: 'weather_climate', prior: 0.29, hours: [168, 2160], pattern: 0.70,
    headline: g => `Sécheresse : risque de pression accrue sur l’eau et certaines productions agricoles autour de ${g}.`,
    known: 'Un épisode de sécheresse persistant est suivi par les observateurs.',
    chain: ['déficit hydrique persistant', 'réserves et sols sous pression', 'restrictions / rendement agricole', 'tension locale sur eau et coûts'],
    watch: ['restrictions d’eau', 'baisse des réserves', 'révisions de récolte'],
    falsify: 'Les réserves se normalisent et aucune restriction ou révision agricole significative n’apparaît dans les 90 jours.'
  },
  financial_stress: {
    domain: 'financial_stress', prior: 0.27, hours: [24, 336], pattern: 0.73,
    headline: () => 'Marchés : risque de durcissement rapide de l’aversion au risque et des conditions de financement.',
    known: 'Les indicateurs officiels de volatilité financière se tendent.',
    chain: ['volatilité en hausse', 'réduction de l’appétit pour le risque', 'conditions de financement plus strictes', 'pression sur actifs risqués et investissement'],
    watch: ['VIX persistant > 25', 'élargissement des spreads', 'baisse du crédit / émissions'],
    falsify: 'La volatilité et les spreads se normalisent durablement avant la fin de la fenêtre.'
  },
  credit_stress: {
    domain: 'financial_stress', prior: 0.30, hours: [72, 720], pattern: 0.77,
    headline: () => 'Crédit : risque de resserrement des conditions de financement des entreprises.',
    known: 'Les spreads de crédit se détériorent.',
    chain: ['spreads en hausse', 'prime de risque plus élevée', 'financement plus cher', 'ralentissement d’investissement / refinancement'],
    watch: ['spreads HY en hausse', 'dégradation des émissions', 'conditions bancaires plus strictes'],
    falsify: 'Les spreads retombent sans durcissement observable du financement dans les 30 jours.'
  },
  energy_price_spike: {
    domain: 'energy', prior: 0.33, hours: [72, 504], pattern: 0.75,
    headline: () => 'Énergie : risque de transmission de la hausse du pétrole vers carburants, fret et coûts aval.',
    known: 'Le pétrole accélère sur les données FRED.',
    chain: ['pétrole en hausse', 'coûts d’approvisionnement énergétique', 'carburants et fret', 'pression sur certains prix aval'],
    watch: ['prix spot carburants', 'indices de fret', 'révisions de marges'],
    falsify: 'Le pétrole reperd rapidement sa hausse et aucun coût aval ne se tend dans les trois semaines.'
  },
  energy_price_relief: {
    domain: 'energy', prior: 0.32, hours: [72, 504], pattern: 0.72,
    headline: () => 'Énergie : possibilité d’un relâchement des pressions sur carburants et fret si la baisse du pétrole se confirme.',
    known: 'La trajectoire du pétrole s’oriente nettement à la baisse.',
    chain: ['pétrole en baisse', 'coût d’approvisionnement réduit', 'détente progressive carburants / fret', 'pression inflationniste marginalement moindre'],
    watch: ['confirmation WTI/Brent', 'prix de gros carburants', 'indices de fret'],
    falsify: 'Le pétrole rebondit ou la baisse ne se transmet pas aux coûts aval dans les trois semaines.'
  },
  labor_market_softening: {
    domain: 'economy_labor', prior: 0.28, hours: [336, 1440], pattern: 0.70,
    headline: () => 'Emploi US : risque de ralentissement des embauches et de remontée du chômage dans les prochaines semaines.',
    known: 'Les inscriptions au chômage se détériorent rapidement.',
    chain: ['demandes d’allocation en hausse', 'licenciements plus visibles', 'embauches plus prudentes', 'détérioration du marché du travail'],
    watch: ['claims persistants', 'JOLTS / payrolls', 'annonces de licenciements'],
    falsify: 'Les inscriptions se normalisent et les données d’emploi restent solides pendant 60 jours.'
  },
  media_supply_chain_signal: {
    domain: 'supply_fuel', prior: 0.23, hours: [48, 504], pattern: 0.62,
    headline: () => 'Commerce mondial : risque de retards logistiques plus visibles si la convergence sur ports et transport maritime se poursuit.',
    known: 'Plusieurs médias et zones de publication convergent sur des tensions logistiques.',
    chain: ['multiplication de signaux logistiques', 'capacité / itinéraires perturbés', 'délais de transport', 'retards d’approvisionnement aval'],
    watch: ['fermetures de ports', 'déroutements', 'hausse des délais ou du fret'],
    falsify: 'La convergence médiatique retombe sans perturbation confirmée des délais ou itinéraires.'
  },
  media_civil_disruption: {
    domain: 'social_collective_behavior', prior: 0.22, hours: [24, 168], pattern: 0.61,
    headline: () => 'Mobilisations : risque de perturbations de transport ou de services si les grèves/protestations gagnent en ampleur.',
    known: 'Une convergence médiatique multi-source signale des mobilisations importantes.',
    chain: ['mobilisation / grève', 'participation croissante', 'points de blocage', 'perturbations de mobilité ou de services'],
    watch: ['appels syndicaux', 'fermetures / blocages', 'annulations'],
    falsify: 'La mobilisation se dissipe sans blocage ou perturbation de services dans la semaine.'
  },
  media_geopolitical_trade: {
    domain: 'geopolitics_security', prior: 0.24, hours: [72, 720], pattern: 0.64,
    headline: () => 'Commerce : risque de tension sur certains prix ou flux si les restrictions commerciales se matérialisent.',
    known: 'Les signaux médiatiques convergent sur sanctions, interdictions d’export ou restrictions commerciales.',
    chain: ['restriction commerciale', 'offre / itinéraires contraints', 'substitution plus coûteuse', 'pression sur prix ou délais'],
    watch: ['texte réglementaire', 'réaction des exportateurs', 'prix / volumes concernés'],
    falsify: 'Les restrictions annoncées ne sont pas appliquées ou n’affectent pas les flux dans les 30 jours.'
  },
  media_financial_stress: {
    domain: 'financial_stress', prior: 0.20, hours: [24, 336], pattern: 0.58,
    headline: () => 'Banques : risque de contagion de défiance si les signaux de liquidité se confirment par des données officielles.',
    known: 'Des médias indépendants convergent sur un stress bancaire ou de liquidité.',
    chain: ['signal de défiance', 'retraits / tension de liquidité', 'réponse des banques / autorités', 'contagion éventuelle aux conditions financières'],
    watch: ['données de dépôts', 'facilités de liquidité', 'communiqués régulateurs'],
    falsify: 'Aucune donnée officielle ne confirme le stress et les signaux médiatiques disparaissent dans les deux semaines.'
  },
  copernicus_emergency_activation: {
    domain: 'natural_hazards', prior: 0.31, hours: [0, 168], pattern: 0.66,
    headline: g => `Crise suivie par satellite : risque de contraintes logistiques et d’accès autour de ${g}.`,
    known: 'Copernicus EMS a activé une cartographie d’urgence.',
    chain: ['activation d’urgence', 'cartographie de dommages / exposition', 'adaptation des accès et secours', 'contraintes logistiques locales'],
    watch: ['cartes de dommages', 'évacuations', 'routes / réseaux affectés'],
    falsify: 'L’activation se clôt sans dommage ni contrainte opérationnelle significative dans la semaine.'
  }
};

function normalizeGeo(value) {
  return String(value || 'Monde').toLowerCase().replace(/[^a-z0-9à-ÿ]+/gi, ' ').trim().slice(0, 80);
}

function hoursSince(at) {
  const t = new Date(at).getTime();
  return Number.isFinite(t) ? Math.max(0, (Date.now() - t) / HOUR) : 24;
}

function consolidation(signals, pattern, probability) {
  const trust = signals.reduce((s, x) => s + x.source_trust, 0) / signals.length;
  const families = new Set(signals.map(x => x.source_family)).size;
  const freshness = Math.max(0, 1 - Math.min(...signals.map(x => hoursSince(x.observed_at))) / 72);
  const diversity = clamp((families - 1) / 3, 0, 1);
  const corroboration = clamp((signals.length - 1) / 4, 0, 1);
  const score = Math.round(100 * (0.30 * trust + 0.18 * diversity + 0.16 * freshness + 0.22 * pattern.pattern + 0.14 * corroboration));
  return {
    score, score_is_probability: false,
    level: score >= 78 ? 'très solide' : score >= 64 ? 'solide' : score >= 50 ? 'en consolidation' : 'fragile',
    source_families: [...new Map(signals.map(s => [s.source_family, { key: s.source_family, label: s.source_family }])).values()],
    source_providers: [...new Map(signals.map(s => [s.source_key, { key: s.source_key, label: s.source_label, role: s.source_family }])).values()],
    dimensions: [
      { key: 'source_quality', label: 'Qualité des sources', score: Math.round(trust * 100) },
      { key: 'source_diversity', label: 'Diversité', score: Math.round(25 + diversity * 75) },
      { key: 'freshness', label: 'Fraîcheur', score: Math.round(freshness * 100) },
      { key: 'pattern', label: 'Pattern / mécanisme', score: Math.round(pattern.pattern * 100) },
      { key: 'corroboration', label: 'Corroboration', score: Math.round(35 + corroboration * 65) }
    ],
    strengths: [
      trust >= .9 ? 'Le précurseur principal vient d’une source officielle à forte fiabilité.' : null,
      families > 1 ? `${families} familles de sources indépendantes ou complémentaires soutiennent le mécanisme.` : null,
      signals.length > 1 ? `${signals.length} signaux compatibles ont été fusionnés sans multiplier artificiellement la probabilité.` : null,
      pattern.pattern >= .75 ? 'Le mécanisme de propagation est bien défini.' : null
    ].filter(Boolean),
    weaknesses: [
      families === 1 ? 'La diversité de familles de sources reste limitée.' : null,
      pattern.pattern < .7 ? 'Le mécanisme est encore exploratoire.' : null,
      probability.empirically_calibrated ? null : 'La probabilité est une estimation de modèle, pas encore une fréquence empirique calibrée.'
    ].filter(Boolean)
  };
}

function probabilityFor(signals, pattern) {
  const trust = signals.reduce((s, x) => s + x.source_trust, 0) / signals.length;
  const severity = Math.max(...signals.map(x => clamp(Number(x.severity) || .5, 0, 1)));
  const families = new Set(signals.map(x => x.source_family)).size;
  const freshness = Math.max(0, 1 - Math.min(...signals.map(x => hoursSince(x.observed_at))) / 72);
  const corroboration = clamp((signals.length - 1) / 4, 0, 1);
  let z = logit(pattern.prior);
  z += (trust - .72) * 2.0;
  z += (severity - .5) * 1.15;
  z += clamp(families - 1, 0, 3) * .18;
  z += freshness * .24;
  z += corroboration * .22;
  const projection = signals.map(s => s.facts?.statistical_projection).find(Boolean);
  if (projection && Number.isFinite(projection.change)) z += Math.min(.28, Math.abs(projection.change) * 1.6);
  const estimate = clamp(sigmoid(z), .08, .88);
  const consolidationHint = clamp(.45 + trust * .25 + pattern.pattern * .2 + corroboration * .1, .45, .95);
  const half = clamp(.24 - consolidationHint * .11, .10, .19);
  return {
    type: 'model_estimate', estimate,
    percent: Math.round(estimate * 100),
    interval_low: clamp(estimate - half, .03, .95),
    interval_high: clamp(estimate + half, .05, .97),
    interval_percent: [Math.round(clamp(estimate - half, .03, .95) * 100), Math.round(clamp(estimate + half, .05, .97) * 100)],
    method: 'evidence-node-log-odds-v1', calibration_status: 'uncalibrated_model_estimate',
    empirically_calibrated: false, can_be_read_as_empirical_frequency: false
  };
}

function timeWindow(pattern) {
  const now = new Date();
  const start = new Date(now.getTime() + pattern.hours[0] * HOUR);
  const end = new Date(now.getTime() + pattern.hours[1] * HOUR);
  const human = pattern.hours[1] <= 96
    ? `entre ${pattern.hours[0]} h et ${pattern.hours[1]} h`
    : `entre ${Math.round(pattern.hours[0] / 24)} et ${Math.round(pattern.hours[1] / 24)} jours`;
  return { kind: 'relative_after_precursor', low_hours: pattern.hours[0], high_hours: pattern.hours[1], start_at: start.toISOString(), end_at: end.toISOString(), human };
}

function groupSignals(signals) {
  const groups = new Map();
  for (const s of signals) {
    const pattern = PATTERNS[s.event_type];
    if (!pattern) continue;
    const specific = ['major_earthquake','wildfire_emergency','flood_emergency','severe_storm_emergency','volcanic_emergency','drought_emergency','disease_outbreak_signal','copernicus_emergency_activation'].includes(s.event_type);
    const key = `${s.event_type}|${specific ? normalizeGeo(s.geography || s.title) : 'global'}`;
    const arr = groups.get(key) ?? [];
    arr.push(s);
    groups.set(key, arr);
  }
  return groups;
}

function selectDiverse(rows, limit) {
  const selected = [];
  const domainCounts = new Map();
  const typeCounts = new Map();
  for (const row of rows) {
    const dc = domainCounts.get(row.domain) ?? 0;
    const tc = typeCounts.get(row.event_type) ?? 0;
    if (dc >= 5 || tc >= 4) continue;
    selected.push(row);
    domainCounts.set(row.domain, dc + 1);
    typeCounts.set(row.event_type, tc + 1);
    if (selected.length >= limit) break;
  }
  return selected;
}

export function buildForecasts(signals, limit = 20) {
  const forecasts = [];
  for (const [groupKey, group] of groupSignals(signals)) {
    const representative = [...group].sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0))[0];
    const pattern = PATTERNS[representative.event_type];
    const probability = probabilityFor(group, pattern);
    const c = consolidation(group, pattern, probability);
    const geography = representative.geography || 'Monde';
    const scenarioKey = hash(`${groupKey}|${pattern.headline(geography)}`);
    forecasts.push({
      scenario_key: scenarioKey,
      domain: pattern.domain,
      event_type: representative.event_type,
      headline: pattern.headline(geography),
      outcome: pattern.headline(geography),
      public_language: 'fr',
      fact_status: 'forecast_from_precursor',
      trajectory: probability.percent >= 55 ? 'building' : probability.percent >= 35 ? 'forming' : 'fragile',
      probability,
      time_window: timeWindow(pattern),
      what_we_know: pattern.known,
      why_now: `${group.length} signal${group.length > 1 ? 'aux' : ''} actuellement observable${group.length > 1 ? 's' : ''} déclenche${group.length > 1 ? 'nt' : ''} un mécanisme de second ordre. La sortie ci-dessous décrit ce qui pourrait arriver ensuite, pas ce qui est déjà arrivé.`,
      causal_chain: pattern.chain,
      watch_next: pattern.watch,
      probability_up_if: pattern.watch.map(x => `confirmation supplémentaire : ${x}`),
      probability_down_if: ['les indicateurs intermédiaires attendus restent absents', 'des sources indépendantes montrent une normalisation du mécanisme'],
      falsification: pattern.falsify,
      evidence: group.slice(0, 6).map(s => ({
        title: s.title, source_key: s.source_key, source_label: s.source_label, source_family: s.source_family,
        source_trust: s.source_trust, url: s.url, observed_at: s.observed_at, event_at: s.event_at, facts: s.facts
      })),
      fusion: {
        engine: 'evidence-node-scenario-fusion-v1', raw_signal_count: group.length,
        source_keys: [...new Set(group.map(s => s.source_key))], duplicate_probability_inflation_prevented: true,
        geography_aware_grouping: true, probability_recomputed_after_fusion: true
      },
      consolidation: c,
      novelty: 'second_order_outcome',
      commercial_contract: { certainty_claimed: false, falsifiable: true, expiry_enforced: true }
    });
  }
  forecasts.sort((a, b) => {
    const aScore = a.probability.percent + a.consolidation.score * .35 + (a.domain === 'geopolitics_security' || a.domain === 'financial_stress' ? 4 : 0);
    const bScore = b.probability.percent + b.consolidation.score * .35 + (b.domain === 'geopolitics_security' || b.domain === 'financial_stress' ? 4 : 0);
    return bScore - aScore;
  });
  return selectDiverse(forecasts, limit);
}
