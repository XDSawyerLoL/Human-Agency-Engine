const ENVIRONMENTAL_EVENTS = new Set([
  'major_earthquake','wildfire_emergency','flood_emergency','severe_storm_emergency','volcanic_emergency','drought_emergency',
  'landslide_emergency','cryosphere_disruption','air_quality_hazard','severe_winter_hazard','temperature_extreme','water_quality_anomaly',
  'natural_hazard_event','copernicus_emergency_activation'
]);

const DOMAIN_CAPS = {
  natural_hazards:3, weather_climate:3, public_health:4, cyber_technology:5, financial_stress:5,
  energy:5, economy_labor:6, supply_fuel:6, social_collective_behavior:4, geopolitics_security:6,
  regulation_policy:5, transport_mobility:4
};
const HORIZON_CAPS = { immediate:8, near:11, medium:12, long:8, strategic:6, deep:4 };

function score(row){
  return Number(row?.probability?.percent||0) + Number(row?.consolidation?.score||row?.confidence||0)*.20 + Number(row?.commercial_priority||.5)*10 - Number(row?.horizon_order||0)*1.1;
}

function canonicalScenario(row){
  return String(row?.scenario_id || row?.scenario_key || row?.title || '').toLowerCase().trim();
}

export function selectPublicForecasts(rows, limit=44){
  const sorted=[...(rows||[])].filter(Boolean).sort((a,b)=>score(b)-score(a));

  // Absolute public dedup: one best representation for each scenario family.
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
    const isEnv=ENVIRONMENTAL_EVENTS.has(row.event_type);
    if(dc >= (DOMAIN_CAPS[row.domain] ?? 4)) return false;
    if(hc >= (HORIZON_CAPS[row.horizon_tier] ?? 8)) return false;
    if(oc >= 2) return false;
    if(ec >= (relaxed ? 3 : 2)) return false;
    if(isEnv && environmental >= 6) return false;
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

  // Pass 1: breadth first — the strongest scenario available for every domain.
  const bestByDomain=new Map();
  for(const row of unique) if(!bestByDomain.has(row.domain)) bestByDomain.set(row.domain,row);
  for(const row of bestByDomain.values()) if(selected.length<limit && canAdd(row)) add(row);

  // Pass 2: every horizon gets a public representative when a candidate exists.
  for(const h of ['immediate','near','medium','long','strategic','deep']){
    const row=unique.find(r=>r.horizon_tier===h && !selectedKeys.has(r.scenario_key) && canAdd(r));
    if(row && selected.length<limit) add(row);
  }

  // Pass 3: fill with the best remaining futures under strict diversity caps.
  for(const row of unique){
    if(selected.length>=limit) break;
    if(canAdd(row)) add(row);
  }

  // Pass 4: only relax event-family count, never duplicate scenarios or environmental cap.
  for(const row of unique){
    if(selected.length>=limit) break;
    if(canAdd(row,true)) add(row);
  }

  return selected.sort((a,b)=>score(b)-score(a));
}
