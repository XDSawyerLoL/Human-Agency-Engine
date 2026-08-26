import { selectPublicForecasts } from '../src/public_selection.js';

const make=(scenario_id,event_type,domain,p=60,horizon='near',order=1)=>({
  scenario_id,scenario_key:`${scenario_id}-${event_type}-${Math.random()}`,origin_group:`${event_type}|x`,event_type,domain,horizon_tier:horizon,horizon_order:order,
  probability:{percent:p},consolidation:{score:65},commercial_priority:.7
});

const rows=[
  make('same-scenario','wildfire_emergency','natural_hazards',80),
  make('same-scenario','wildfire_emergency','natural_hazards',70),
  ...Array.from({length:12},(_,i)=>make(`env-${i}`,'wildfire_emergency','natural_hazards',78-i)),
  make('cyber-a','media_cyber_disruption','cyber_technology',65),
  make('finance-a','financial_stress','financial_stress',64),
  make('jobs-a','media_industrial_stress','economy_labor',63),
  make('energy-a','media_energy_grid_stress','energy',62),
  make('trade-a','media_geopolitical_trade','geopolitics_security',61),
  make('health-a','disease_outbreak_signal','public_health',60),
  make('policy-a','media_technology_regulation','regulation_policy',59),
  make('long-a','media_technology_regulation','regulation_policy',31,'long',3),
  make('strategic-a','media_ai_investment','cyber_technology',24,'strategic',4),
  make('deep-a','media_ai_investment','cyber_technology',18,'deep',5)
];
const selected=selectPublicForecasts(rows,20);
const ids=selected.map(x=>x.scenario_id);
if(new Set(ids).size!==ids.length) throw new Error('duplicate scenario_id leaked to public selection');
const env=selected.filter(x=>['wildfire_emergency','flood_emergency','major_earthquake','severe_storm_emergency','drought_emergency'].includes(x.event_type));
if(env.length>6) throw new Error(`environmental cap broken: ${env.length}`);
for(const domain of ['cyber_technology','financial_stress','economy_labor','energy','geopolitics_security','public_health','regulation_policy']){
  if(!selected.some(x=>x.domain===domain)) throw new Error(`domain breadth missing: ${domain}`);
}
for(const horizon of ['long','strategic','deep']){
  if(rows.some(x=>x.horizon_tier===horizon) && !selected.some(x=>x.horizon_tier===horizon)) throw new Error(`public horizon missing: ${horizon}`);
}
console.log(JSON.stringify({ok:true,selected:selected.length,environmental:env.length,domains:[...new Set(selected.map(x=>x.domain))],horizons:[...new Set(selected.map(x=>x.horizon_tier))]}));
