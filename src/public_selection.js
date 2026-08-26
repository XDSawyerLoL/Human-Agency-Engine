const ENVIRONMENTAL_EVENTS = new Set([
  'major_earthquake','wildfire_emergency','flood_emergency','severe_storm_emergency','volcanic_emergency','drought_emergency',
  'landslide_emergency','cryosphere_disruption','air_quality_hazard','severe_winter_hazard','temperature_extreme','water_quality_anomaly',
  'natural_hazard_event','copernicus_emergency_activation','memory_climate_scenario'
]);

const DOMAIN_CAPS = {
  natural_hazards:3, weather_climate:6, public_health:8, cyber_technology:10, financial_stress:8,
  energy:9, economy_labor:10, supply_fuel:8, social_collective_behavior:9, geopolitics_security:10,
  regulation_policy:9, transport_mobility:5
};
const HORIZON_CAPS = { immediate:12, near:18, medium:26, long:24, strategic:16, deep:18 };

function score(row){
  const memoryPenalty = row?.memory?.recomputed ? 1.5 : 0;
  return Number(row?.probability?.percent||0) + Number(row?.consolidation?.score||row?.confidence||0)*.20 + Number(row?.commercial_priority||.5)*10 - Number(row?.horizon_order||0)*1.1 - memoryPenalty;
}
function canonicalScenario(row){
  return String(row?.scenario_id || row?.scenario_key || row?.title || '').toLowerCase().trim();
}
function isMemory(row){ return Boolean(row?.memory?.recomputed); }

export function selectPublicForecasts(rows, limit=72){
  const sorted=[...(rows||[])].filter(Boolean).sort((a,b)=>score(b)-score(a));

  // Absolute public dedup: one best representation for each distinct scenario.
  const unique=[]; const seenScenario=new Set();
  for(const row of sorted){
    const key=canonicalScenario(row); if(!key || seenScenario.has(key)) continue;
    seenScenario.add(key); unique.push(row);
  }

  const selected=[]; const selectedKeys=new Set();
  const domains=new Map(), horizons=new Map(), origins=new Map(), eventTypes=new Map();
  let environmental=0;

  const canAdd=(row, relaxed=false)=>{
    if(selectedKeys.has(row.scenario_key)) return false;
    const dc=domains.get(row.domain)||0, hc=horizons.get(row.horizon_tier)||0;
    const oc=origins.get(row.origin_group)||0, ec=eventTypes.get(row.event_type)||0;
    const memory=isMemory(row), env=ENVIRONMENTAL_EVENTS.has(row.event_type);
    if(dc >= (DOMAIN_CAPS[row.domain] ?? 7)) return false;
    if(hc >= (HORIZON_CAPS[row.horizon_tier] ?? 12)) return false;
    // Scenario-memory entries are already semantically unique. Do not throw away distinct hypotheses
    // merely because they originated from the same historic forecasting family.
    if(!memory && oc >= 2) return false;
    if(!memory && ec >= (relaxed ? 4 : 2)) return false;
    if(env && environmental >= 7) return false;
    return true;
  };
  const add=row=>{
    selected.push(row); selectedKeys.add(row.scenario_key);
    domains.set(row.domain,(domains.get(row.domain)||0)+1);
    horizons.set(row.horizon_tier,(horizons.get(row.horizon_tier)||0)+1);
    origins.set(row.origin_group,(origins.get(row.origin_group)||0)+1);
    eventTypes.set(row.event_type,(eventTypes.get(row.event_type)||0)+1);
    if(ENVIRONMENTAL_EVENTS.has(row.event_type)) environmental++;
  };

  // Breadth first: a strong representative for every available domain.
  const bestByDomain=new Map();
  for(const row of unique) if(!bestByDomain.has(row.domain)) bestByDomain.set(row.domain,row);
  for(const row of bestByDomain.values()) if(selected.length<limit && canAdd(row)) add(row);

  // Every time horizon gets a representative when possible.
  for(const h of ['immediate','near','medium','long','strategic','deep']){
    const row=unique.find(r=>r.horizon_tier===h && !selectedKeys.has(r.scenario_key) && canAdd(r));
    if(row && selected.length<limit) add(row);
  }

  // Protect live discovery: scenario memory must expand HORIZON, never replace it.
  const liveTarget=Math.min(Math.ceil(limit*.45), unique.filter(r=>!isMemory(r)).length);
  let liveSelected=selected.filter(r=>!isMemory(r)).length;
  for(const row of unique){
    if(selected.length>=limit || liveSelected>=liveTarget) break;
    if(isMemory(row) || !canAdd(row)) continue;
    add(row); liveSelected++;
  }

  // Fill the remaining field with the strongest distinct futures, live or remembered.
  for(const row of unique){
    if(selected.length>=limit) break;
    if(canAdd(row)) add(row);
  }

  // Relax only live event-family repetition. Never relax semantic dedup, domain/horizon or climate caps.
  for(const row of unique){
    if(selected.length>=limit) break;
    if(canAdd(row,true)) add(row);
  }

  return selected.sort((a,b)=>score(b)-score(a));
}