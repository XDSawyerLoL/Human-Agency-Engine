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
  return {
    scenario_key:row.scenario_key,
    domain:String(row.domain||meta.domain||''),
    horizon_tier:String(row.horizon_tier||meta.horizon_tier||''),
    horizon_order:horizonOrder(row.horizon_tier||meta.horizon_tier),
    outcome:Number(row.outcome),
    origin_group:String(row.origin_group||meta.origin_group||''),
    region:String(meta.region||''),
    resolved_at:row.resolved_at||null
  };
}

function sameContext(a,b){
  if(a.origin_group&&b.origin_group&&a.origin_group===b.origin_group) return true;
  if(a.region&&b.region&&a.region===b.region&&!/^monde$/i.test(a.region)) return true;
  return false;
}

export function buildCausalLearning(resolvedRows=[]){
  const rows=(resolvedRows||[]).map(normalizedRow).filter(r=>r.domain&&[0,1].includes(r.outcome));
  const stats=new Map();
  for(let i=0;i<rows.length;i++) for(let j=0;j<rows.length;j++){
    if(i===j) continue;
    const a=rows[i],b=rows[j];
    if(a.outcome!==1||a.horizon_order>b.horizon_order||!sameContext(a,b)) continue;
    const key=`${a.domain}>${b.domain}`;
    if(!(key in PRIOR_MEAN)) continue;
    const s=stats.get(key)||{key,from_domain:a.domain,to_domain:b.domain,conditional_samples:0,downstream_occurrences:0};
    s.conditional_samples++;
    s.downstream_occurrences+=b.outcome===1?1:0;
    stats.set(key,s);
  }

  const transitions=Object.entries(PRIOR_MEAN).map(([key,prior])=>{
    const s=stats.get(key)||{key,from_domain:key.split('>')[0],to_domain:key.split('>')[1],conditional_samples:0,downstream_occurrences:0};
    const priorStrength=10;
    const posterior=(prior*priorStrength+s.downstream_occurrences)/(priorStrength+s.conditional_samples);
    const shrink=clamp(s.conditional_samples/24,0,1);
    const learned=prior*(1-shrink)+posterior*shrink;
    const multiplier=clamp(learned/Math.max(.05,prior),.65,1.35);
    return {...s,prior_strength:round(prior,3),observed_rate:s.conditional_samples?round(s.downstream_occurrences/s.conditional_samples,3):null,posterior_strength:round(posterior,3),learned_strength:round(learned,3),multiplier:round(multiplier,3),learning_active:s.conditional_samples>=8};
  });
  const active=transitions.filter(x=>x.learning_active);
  return {
    schema:'evidence-causal-learning-v1',
    status:active.length?'learning':'collecting',
    resolved_forecasts:rows.length,
    active_transitions:active.length,
    minimum_samples_per_transition:8,
    by_transition:transitions,
    strongest_updates:[...active].sort((a,b)=>Math.abs(b.multiplier-1)-Math.abs(a.multiplier-1)).slice(0,12),
    guardrails:{causal_proof:false,learns_conditional_association_not_intervention_effect:true,shrunk_to_structural_prior:true},
    note:'Le moteur ajuste progressivement la force des liens structurels selon les scénarios résolus dans un même contexte. Cela apprend des associations temporelles conditionnelles, pas une causalité expérimentale.'
  };
}
