const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=4)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const horizonOrder=t=>({immediate:0,near:1,medium:2,long:3,strategic:4,deep:5}[String(t||'')]??2);

const PRIOR_MEAN={
  'natural_hazards>transport_mobility':.62,'natural_hazards>supply_fuel':.60,'natural_hazards>regulation_policy':.44,'natural_hazards>public_health':.34,
  'weather_climate>transport_mobility':.60,'weather_climate>energy':.54,'weather_climate>supply_fuel':.48,'weather_climate>economy_labor':.43,'weather_climate>regulation_policy':.40,
  'geopolitics_security>supply_fuel':.68,'geopolitics_security>energy':.61,'geopolitics_security>financial_stress':.54,'geopolitics_security>economy_labor':.50,'geopolitics_security>regulation_policy':.47,
  'supply_fuel>economy_labor':.70,'supply_fuel>transport_mobility':.46,'supply_fuel>financial_stress':.37,'supply_fuel>regulation_policy':.34,
  'energy>economy_labor':.68,'energy>regulation_policy':.53,'energy>supply_fuel':.43,
  'financial_stress>economy_labor':.72,'financial_stress>regulation_policy':.54,'financial_stress>social_collective_behavior':.43,
  'economy_labor>social_collective_behavior':.59,'economy_labor>regulation_policy':.45,'economy_labor>financial_stress':.38,
  'public_health>social_collective_behavior':.56,'public_health>regulation_policy':.53,'public_health>economy_labor':.47,'public_health>transport_mobility':.34,
  'cyber_technology>regulation_policy':.54,'cyber_technology>economy_labor':.45,'cyber_technology>supply_fuel':.34,'cyber_technology>transport_mobility':.30,
  'social_collective_behavior>regulation_policy':.65,'social_collective_behavior>economy_labor':.42,'social_collective_behavior>transport_mobility':.36,
  'transport_mobility>supply_fuel':.66,'transport_mobility>economy_labor':.55,
  'regulation_policy>economy_labor':.43,'regulation_policy>energy':.37,'regulation_policy>cyber_technology':.36
};

function normalizedRow(row){
  const meta=row?.meta?.forecast||{};
  const eventAt=meta.target_date||row.target_at||row.resolved_at||null;
  const t=eventAt?Date.parse(eventAt):NaN;
  return {
    scenario_key:String(row.scenario_key||''),
    domain:String(row.domain||meta.domain||''),
    horizon_tier:String(row.horizon_tier||meta.horizon_tier||''),
    horizon_order:horizonOrder(row.horizon_tier||meta.horizon_tier),
    outcome:Number(row.outcome),
    origin_group:String(row.origin_group||meta.origin_group||''),
    region:String(meta.region||row.region||''),
    event_at:Number.isFinite(t)?t:null,
    event_at_iso:Number.isFinite(t)?new Date(t).toISOString():null,
    resolved_at:row.resolved_at||null
  };
}

function contextKey(r){
  if(r.origin_group)return `origin:${r.origin_group}`;
  if(r.region&&!/^monde$/i.test(r.region))return `region:${r.region}`;
  return '';
}

function sameContext(a,b){
  const ca=contextKey(a),cb=contextKey(b);
  return Boolean(ca&&cb&&ca===cb);
}

function orderedBefore(a,b){
  if(a.event_at!==null&&b.event_at!==null)return a.event_at<=b.event_at;
  return a.horizon_order<=b.horizon_order;
}

function observationBucket(b){
  const context=contextKey(b);
  if(!context)return null;
  if(b.event_at!==null){
    const d=new Date(b.event_at);
    const week=Math.floor((b.event_at-Date.UTC(d.getUTCFullYear(),0,1))/604800000);
    return `${context}|${d.getUTCFullYear()}-w${String(week).padStart(2,'0')}`;
  }
  // Sans date exploitable, rester conservateur : un seul échantillon par contexte.
  return `${context}|undated`;
}

export function buildCausalLearning(resolvedRows=[]){
  const rows=(resolvedRows||[]).map(normalizedRow).filter(r=>r.scenario_key&&r.domain&&[0,1].includes(r.outcome));
  const transitionObservations=new Map();

  for(const key of Object.keys(PRIOR_MEAN)){
    const [fromDomain,toDomain]=key.split('>');
    const grouped=new Map();
    for(const b of rows){
      if(b.domain!==toDomain)continue;
      const bucket=observationBucket(b);
      if(!bucket)continue;
      const upstream=rows.filter(a=>
        a.scenario_key!==b.scenario_key&&
        a.domain===fromDomain&&
        a.outcome===1&&
        a.horizon_order<=b.horizon_order&&
        sameContext(a,b)&&
        orderedBefore(a,b)
      );
      if(!upstream.length)continue;
      const observationKey=`${key}|${bucket}`;
      const g=grouped.get(observationKey)||{outcomes:[],downstream_keys:new Set(),upstream_keys:new Set(),context:contextKey(b),bucket};
      if(!g.downstream_keys.has(b.scenario_key)){
        g.downstream_keys.add(b.scenario_key);
        g.outcomes.push(b.outcome);
      }
      // Une multitude de prévisions amont dans le même contexte ne crée jamais de nouveaux échantillons.
      upstream.forEach(a=>g.upstream_keys.add(a.scenario_key));
      grouped.set(observationKey,g);
    }
    transitionObservations.set(key,[...grouped.values()]);
  }

  const transitions=Object.entries(PRIOR_MEAN).map(([key,prior])=>{
    const [fromDomain,toDomain]=key.split('>');
    const observations=transitionObservations.get(key)||[];
    const conditionalSamples=observations.length;
    const downstreamOccurrences=observations.reduce((sum,g)=>sum+(g.outcomes.reduce((a,b)=>a+b,0)/Math.max(1,g.outcomes.length)),0);
    const priorStrength=10;
    const posterior=(prior*priorStrength+downstreamOccurrences)/(priorStrength+conditionalSamples);
    const shrink=clamp(conditionalSamples/24,0,1);
    const learned=prior*(1-shrink)+posterior*shrink;
    const multiplier=clamp(learned/Math.max(.05,prior),.65,1.35);
    return {
      key,from_domain:fromDomain,to_domain:toDomain,
      conditional_samples:conditionalSamples,
      downstream_occurrences:round(downstreamOccurrences,3),
      independent_context_buckets:conditionalSamples,
      prior_strength:round(prior,3),
      observed_rate:conditionalSamples?round(downstreamOccurrences/conditionalSamples,3):null,
      posterior_strength:round(posterior,3),
      learned_strength:round(learned,3),
      multiplier:round(multiplier,3),
      learning_active:conditionalSamples>=8
    };
  });

  const active=transitions.filter(x=>x.learning_active);
  return {
    schema:'evidence-causal-learning-v1',
    status:active.length?'learning':'collecting',
    resolved_forecasts:rows.length,
    active_transitions:active.length,
    minimum_samples_per_transition:8,
    sample_definition:'one independent context/time bucket per transition; duplicate upstream/downstream forecasts are collapsed',
    by_transition:transitions,
    strongest_updates:[...active].sort((a,b)=>Math.abs(b.multiplier-1)-Math.abs(a.multiplier-1)).slice(0,12),
    guardrails:{
      causal_proof:false,
      learns_conditional_association_not_intervention_effect:true,
      shrunk_to_structural_prior:true,
      temporal_order_required_when_dates_exist:true,
      duplicate_forecast_pairs_count_as_independent_samples:false
    },
    note:'Le moteur ajuste progressivement la force des liens structurels à partir d’observations dédupliquées et temporellement ordonnées. Cela apprend des associations conditionnelles, pas une causalité expérimentale.'
  };
}
