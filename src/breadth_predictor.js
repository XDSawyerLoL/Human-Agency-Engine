const HOUR=3600_000;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const hash=s=>{let h=2166136261;for(const c of s){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `breadth-${(h>>>0).toString(16)}`};

const MODELS={
  media_industrial_stress:[
    {id:'industry-jobs',domain:'economy_labor',p:.38,h:[72,720],title:'Industrie : risque de nouvelles restructurations et suppressions d’emplois si la vague actuelle se confirme.',summary:'Une convergence sur fermetures d’usines et licenciements peut précéder d’autres annonces sectorielles dans les prochaines semaines.',tags:['Industrie','Emploi'],chain:['annonces de restructuration','pression sur coûts / demande','plans d’économies','emploi industriel sous pression']},
    {id:'industry-capacity',domain:'economy_labor',p:.27,h:[720,4320],title:'Industrie : risque de réduction durable de certaines capacités de production dans les prochains mois.',summary:'Si les fermetures cessent d’être isolées, elles peuvent se transformer en ajustement de capacité et d’investissement.',tags:['Production','Investissement'],chain:['restructurations répétées','capacité excédentaire','capex réduit','production réallouée']}
  ],
  media_energy_grid_stress:[
    {id:'grid-operations',domain:'energy',p:.36,h:[12,168],title:'Électricité : risque accru de restrictions, délestages ou mesures d’urgence sur les réseaux sous tension.',summary:'Une hausse convergente des alertes réseau et coupures peut précéder des mesures opérationnelles plus visibles.',tags:['Électricité','Réseaux'],chain:['réseau sous tension','marges réduites','mesures opérateurs','coupures / restrictions possibles']},
    {id:'grid-prices',domain:'energy',p:.28,h:[168,1440],title:'Énergie : risque de volatilité accrue des prix si les tensions réseau persistent plusieurs semaines.',summary:'Les contraintes physiques durables peuvent se transmettre aux marchés de gros et aux coûts des acteurs exposés.',tags:['Prix','Énergie'],chain:['tension réseau','coûts marginaux élevés','marchés de gros volatils','pression sur prix']}
  ],
  media_food_supply_signal:[
    {id:'food-prices',domain:'supply_fuel',p:.34,h:[336,2160],title:'Alimentation : risque de pression sur certains prix si les pertes agricoles et restrictions d’export s’accumulent.',summary:'Plusieurs signaux agricoles convergents peuvent se transmettre aux matières premières puis aux prix alimentaires sur quelques mois.',tags:['Alimentation','Agriculture','Prix'],chain:['pertes / restrictions','offre exportable réduite','matières premières plus tendues','prix alimentaires exposés']}
  ],
  media_technology_regulation:[
    {id:'tech-rules',domain:'regulation_policy',p:.31,h:[720,4320],title:'Technologie : probabilité accrue de nouvelles règles contraignantes sur l’IA et les plateformes dans les prochains mois.',summary:'La multiplication des projets et annonces réglementaires peut déboucher sur des obligations plus concrètes pour les entreprises.',tags:['IA','Régulation'],chain:['pression réglementaire','projets de texte','arbitrages politiques','nouvelles obligations']},
    {id:'tech-compliance',domain:'regulation_policy',p:.22,h:[4320,26280],title:'À horizon 1–3 ans : hausse probable des dépenses de conformité liées à l’IA et au numérique.',summary:'Une réglementation plus dense peut déplacer durablement les budgets vers audit, gouvernance des données et conformité.',tags:['Conformité','Investissement'],chain:['règles nouvelles','obligations de contrôle','process internes renforcés','dépenses de conformité']}
  ],
  media_ai_investment:[
    {id:'ai-capex',domain:'cyber_technology',p:.35,h:[2160,17520],title:'IA : probabilité d’une nouvelle accélération des investissements en centres de données, puces et infrastructures.',summary:'La convergence des annonces d’investissement peut annoncer une hausse durable de la demande d’infrastructure numérique sur 1 à 2 ans.',tags:['IA','Data centers','Semi-conducteurs'],chain:['demande IA','capacité de calcul insuffisante','capex infrastructure','nouveaux centres / puces']},
    {id:'ai-energy',domain:'energy',p:.23,h:[8760,43800],title:'À horizon 1–5 ans : risque de pression accrue de l’IA sur la demande électrique dans les régions concentrant les data centers.',summary:'Si les investissements annoncés se matérialisent, la contrainte peut se déplacer vers raccordements, production et réseau électrique.',tags:['IA','Électricité','Infrastructure'],chain:['capex data centers','demande électrique locale','raccordements sous pression','investissements réseau / production']}
  ]
};

function horizon(hours){const e=hours[1];if(e<=72)return{tier:'immediate',label:'Prochaines heures',order:0};if(e<=720)return{tier:'near',label:'Jours & semaines',order:1};if(e<=8760)return{tier:'medium',label:'Mois à venir',order:2};if(e<=26280)return{tier:'long',label:'1–3 ans',order:3};return{tier:'strategic',label:'3–5 ans',order:4}}
function human(h){const [a,b]=h;if(b<=72)return`dans les prochaines ${b} h`;const d=b/24;if(d<=45)return`d’ici ${Math.max(1,Math.round(a/24))} à ${Math.round(d)} jours`;const m=d/30.44;if(m<=18)return`d’ici ${Math.max(1,Math.round(a/24/30.44))} à ${Math.round(m)} mois`;return`d’ici ${Math.max(1,Math.round(a/24/365))} à ${Math.max(1,Math.round(b/24/365))} ans`}

export function buildBreadthForecasts(signals){
  const now=Date.now(); const out=[];
  for(const s of signals){
    for(const model of MODELS[s.event_type]??[]){
      const hm=horizon(model.h); const strength=clamp((Number(s.severity)||.5)-.5,-.25,.3);
      const p=clamp(model.p+strength*.22-hm.order*.018,.08,.72); const pct=Math.round(p*100); const end=new Date(now+model.h[1]*HOUR);
      const id=hash(`${s.event_type}|${model.id}`);
      out.push({id,scenario_key:id,scenario_id:model.id,origin_group:`${s.event_type}|global`,status:'active',domain:model.domain,event_type:s.event_type,
        title:model.title,headline:model.title,outcome:model.title,summary:model.summary,region:'Monde',public_language:'fr',fact_status:'forecast_from_precursor',
        horizon_tier:hm.tier,horizon_label:hm.label,horizon_order:hm.order,target_date:end.toISOString(),trajectory:pct>=55?'building':pct>=35?'forming':'fragile',
        probability:{type:'model_estimate',estimate:p,percent:pct,interval_low:clamp(p-.17,.03,.9),interval_high:clamp(p+.17,.08,.92),interval_percent:[Math.round(clamp(p-.17,.03,.9)*100),Math.round(clamp(p+.17,.08,.92)*100)],method:'evidence-breadth-media-v1',calibration_status:'uncalibrated_model_estimate',empirically_calibrated:false,can_be_read_as_empirical_frequency:false},
        confidence:Math.round(45+(Number(s.severity)||.5)*28),confidence_label:'en consolidation',time_window:{kind:'relative_after_precursor',low_hours:model.h[0],high_hours:model.h[1],start_at:new Date(now+model.h[0]*HOUR).toISOString(),end_at:end.toISOString(),target_date:end.toISOString(),human:human(model.h),...hm},
        what_we_know:'Plusieurs médias indépendants convergent sur ce signal thématique.',why_now:`GDELT détecte une convergence multi-domaines sur « ${s.title.replace('Convergence médiatique : ','')} ».`,causal_chain:model.chain,watch_next:model.chain.slice(1),favorable_signals:model.chain.slice(1),contrary_signals:['la convergence médiatique retombe rapidement','aucune donnée officielle ou opérationnelle ne confirme la trajectoire'],probability_up_if:model.chain.slice(1),probability_down_if:['normalisation rapide','absence de confirmation indépendante'],human_needs:model.tags,
        resolution_conditions:`La trajectoire est considérée comme matérialisée si « ${model.chain.at(-1)} » devient observable avant ${end.toLocaleDateString('fr-FR')}.`,falsification:'Aucun indicateur opérationnel ou officiel cohérent avec la conséquence annoncée n’apparaît dans la fenêtre.',
        evidence:[{title:s.title,source_key:s.source_key,source_label:s.source_label,source_family:s.source_family,source_trust:s.source_trust,url:s.url,observed_at:s.observed_at,event_at:s.event_at,facts:s.facts}],
        fusion:{engine:'evidence-breadth-media-v1',raw_signal_count:1,source_keys:[s.source_key],duplicate_probability_inflation_prevented:true,geography_aware_grouping:false,probability_recomputed_after_fusion:true,multiple_distinct_outcomes_per_precursor_allowed:true},
        consolidation:{score:Math.round(45+(Number(s.severity)||.5)*28),score_is_probability:false,level:'en consolidation',source_families:[{key:s.source_family,label:s.source_family}],source_providers:[{key:s.source_key,label:s.source_label,role:s.source_family}],dimensions:[],strengths:['Convergence multi-domaines détectée.'],weaknesses:['Signal média : confirmation officielle encore nécessaire.','Estimation de modèle non calibrée empiriquement.']},novelty:'second_order_outcome',commercial_priority:.72,commercial_contract:{certainty_claimed:false,falsifiable:true,expiry_enforced:true}}
      );
    }
  }
  return out;
}
