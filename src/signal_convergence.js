const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));

const STOP=new Set('le la les de des du un une et ou a au aux en dans sur pour par avec sans vers ce cette ces est sont plus moins entre apres avant sous over from the and for with into than'.split(/\s+/));
const DOMAIN_HINTS={
  natural_hazards:['earthquake','quake','wildfire','fire','flood','storm','volcan','drought','landslide','hazard','emergency','seisme','incend','inond','tempete','secheresse'],
  weather_climate:['weather','climate','storm','temperature','air quality','winter','heat','cold','meteo','climat','chaleur','froid'],
  cyber_technology:['cyber','technology','ai ',' ia ','semiconductor','chips','data center','digital','ransomware','satellite','gnss'],
  public_health:['health','disease','outbreak','hospital','vaccine','sante','maladie','epidem','foyer'],
  financial_stress:['finance','bank','credit','yield','market','liquidity','financial','banque','marche'],
  energy:['energy','electric','grid','power','fuel','oil','gas','energie','electricite','petrole','gaz'],
  economy_labor:['econom','jobs','employment','layoff','industry','factory','wage','emploi','industrie','usine','croissance'],
  supply_fuel:['supply','food','grain','shipping','logistic','export','import','approvisionnement','aliment','transport maritime','logistique'],
  social_collective_behavior:['social','protest','migration','attention','behavior','manifest','comportement'],
  geopolitics_security:['conflict','military','war','security','trade restriction','geopolit','guerre','militaire','securite'],
  regulation_policy:['regulation','policy','law','government','rules','reglement','politique','loi','gouvernement'],
  transport_mobility:['transport','aviation','shipping','road','rail','mobility','route','ferroviaire','mobilite']
};
const EVENT_DOMAINS={
  media_cyber_disruption:['cyber_technology','economy_labor','transport_mobility','financial_stress'],
  media_conflict_escalation:['geopolitics_security','energy','supply_fuel','economy_labor','transport_mobility'],
  media_industrial_stress:['economy_labor','energy','supply_fuel','financial_stress'],
  media_energy_grid_stress:['energy','economy_labor','supply_fuel','cyber_technology'],
  media_food_supply_signal:['supply_fuel','economy_labor','regulation_policy','public_health'],
  media_technology_regulation:['regulation_policy','cyber_technology','economy_labor'],
  media_ai_investment:['cyber_technology','energy','economy_labor','regulation_policy'],
  disease_outbreak_signal:['public_health','economy_labor','transport_mobility','regulation_policy'],
  energy_price_spike:['energy','economy_labor','supply_fuel','financial_stress'],
  major_earthquake:['natural_hazards','transport_mobility','supply_fuel','economy_labor'],
  wildfire_emergency:['natural_hazards','weather_climate','transport_mobility','economy_labor','public_health'],
  flood_emergency:['natural_hazards','weather_climate','transport_mobility','supply_fuel','economy_labor'],
  severe_storm_emergency:['weather_climate','natural_hazards','transport_mobility','energy','supply_fuel'],
  drought_emergency:['weather_climate','natural_hazards','supply_fuel','economy_labor','regulation_policy']
};
function norm(v){return String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();}
function tokens(v){return new Set(norm(v).split(/\s+/).filter(x=>x.length>2&&!STOP.has(x)));}
function overlap(a,b){if(!a.size||!b.size)return 0;let n=0;for(const x of a)if(b.has(x))n++;return n/Math.max(3,Math.min(a.size,b.size));}
function signalText(s){return [s.title,s.event_type,s.geography,JSON.stringify(s.facts?.sample_titles||[]),JSON.stringify(s.facts?.keywords||[])].filter(Boolean).join(' ');}
function forecastText(f){return [f.title,f.summary,f.event_type,f.region,...(f.causal_chain||[]),...(f.human_needs||[]),...(f.watch_next||[])].filter(Boolean).join(' ');}
function geoMatch(f,s){const a=norm(f.region||''),b=norm(s.geography||'');if(!a||!b||a==='monde'||b==='monde'||a==='global'||b==='global')return .18;return a===b||a.includes(b)||b.includes(a)?1:0;}
function relation(f,s){
  const ft=tokens(forecastText(f)),st=tokens(signalText(s)),lex=overlap(ft,st);
  const exact=f.event_type&&f.event_type===s.event_type;
  const domainList=EVENT_DOMAINS[s.event_type]||[];
  const causal=domainList.includes(f.domain);
  const hints=(DOMAIN_HINTS[f.domain]||[]).some(h=>norm(signalText(s)).includes(norm(h)));
  const geo=geoMatch(f,s);
  const score=clamp((exact?.54:0)+(causal?.30:0)+(hints?.12:0)+Math.min(.34,lex*.75)+geo*.08,0,1);
  return {score,kind:exact?'direct':causal?'causal':lex>=.22?'semantic':hints?'thematic':'context',lex,geo};
}
function hoursSince(v){const t=Date.parse(v||'');return Number.isFinite(t)?Math.max(0,(Date.now()-t)/3600000):48;}
function strengthRow(f,s){
  const r=relation(f,s),trust=clamp(s.source_trust??.55,0,1),severity=clamp(s.severity??.5,0,1),freshness=clamp(1-hoursSince(s.observed_at)/120,.18,1);
  const strength=clamp(r.score*(.42+.58*trust)*(.52+.48*severity)*freshness,0,1);
  return {source_key:s.source_key,source_label:s.source_label||s.source_key,source_family:s.source_family||'unknown',event_type:s.event_type,title:s.title||s.event_type,geography:s.geography||'Monde',trust:Number(trust.toFixed(3)),severity:Number(severity.toFixed(3)),relation:r.kind,relevance:Number(r.score.toFixed(3)),strength:Number(strength.toFixed(3)),observed_at:s.observed_at,event_at:s.event_at,url:s.url||null,facts:s.facts||null};
}
function uniqueFamilies(rows){const best=new Map();for(const r of rows){const k=r.source_family||r.source_key;if(!best.has(k)||best.get(k).strength<r.strength)best.set(k,r);}return [...best.values()].sort((a,b)=>b.strength-a.strength);}
function asEvidence(r,tier){return {title:r.title,source_key:r.source_key,source_label:r.source_label,source_family:r.source_family,source_trust:r.trust,url:r.url,observed_at:r.observed_at,event_at:r.event_at,facts:r.facts,convergence_tier:tier,convergence_relation:r.relation,convergence_strength:r.strength};}
export function applySignalConvergence(forecasts,signals){
  const all=Array.isArray(signals)?signals:[];
  for(const f of forecasts||[]){
    const existingKeys=new Set((f.evidence||[]).map(x=>x.source_key).filter(Boolean));
    const rows=uniqueFamilies(all.filter(s=>!existingKeys.has(s.source_key)).map(s=>strengthRow(f,s)).filter(r=>r.relevance>=.24));
    const strong=rows.filter(r=>r.strength>=.48&&['causal','semantic','direct','thematic'].includes(r.relation)).slice(0,6);
    const weak=rows.filter(r=>r.strength>=.22&&r.strength<.48).slice(0,8);
    const causalStrong=strong.filter(r=>r.relation==='causal'||r.relation==='semantic'||r.relation==='direct');
    const support=causalStrong.reduce((a,r)=>a+r.strength,0),familyBonus=Math.min(1,causalStrong.length/3);
    const delta=causalStrong.length>=2?clamp((support-.9)*2.4+familyBonus*2.2,0,6):0;
    const old=clamp(f?.probability?.estimate??((f?.probability?.percent||0)/100),.02,.95),next=clamp(old+delta/100,.02,.94);
    if(f.probability&&delta>0){f.probability.base_percent=Math.round(old*100);f.probability.estimate=next;f.probability.percent=Math.round(next*100);f.probability.cross_signal_delta_points=Number(delta.toFixed(1));if(Array.isArray(f.probability.interval_percent)){f.probability.interval_percent=f.probability.interval_percent.map(x=>Math.min(97,Math.round(Number(x)+delta)));}if(Number.isFinite(f.probability.interval_low))f.probability.interval_low=clamp(f.probability.interval_low+delta/100,.01,.96);if(Number.isFinite(f.probability.interval_high))f.probability.interval_high=clamp(f.probability.interval_high+delta/100,.03,.98);}
    const boost=Math.min(8,strong.length*1.4+weak.length*.35);
    if(f.consolidation){
      f.consolidation.score=Math.min(100,Math.round((f.consolidation.score||0)+boost));
      f.consolidation.dimensions=[...(f.consolidation.dimensions||[]).filter(x=>x.key!=='cross_signal_convergence'),{key:'cross_signal_convergence',label:'Convergence inter-domaines',score:Math.round(clamp(strong.reduce((a,r)=>a+r.strength,0)/Math.max(1,strong.length),0,1)*100)}];
      const providers=new Map((f.consolidation.source_providers||[]).map(x=>[x.key,x]));for(const r of [...strong,...weak])if(!providers.has(r.source_key))providers.set(r.source_key,{key:r.source_key,label:r.source_label,role:`${r.source_family} · ${r.relation}`});f.consolidation.source_providers=[...providers.values()];
      const families=new Map((f.consolidation.source_families||[]).map(x=>[x.key,x]));for(const r of [...strong,...weak])if(!families.has(r.source_family))families.set(r.source_family,{key:r.source_family,label:r.source_family});f.consolidation.source_families=[...families.values()];
    }
    const evidence=[...(f.evidence||[])],evidenceSeen=new Set(evidence.map(x=>`${x.source_key}|${x.title}`));for(const [r,tier] of [...strong.map(x=>[x,'strong']),...weak.slice(0,4).map(x=>[x,'weak'])]){const key=`${r.source_key}|${r.title}`;if(!evidenceSeen.has(key)){evidence.push(asEvidence(r,tier));evidenceSeen.add(key);}}f.evidence=evidence;
    const explanation=strong.length?`${strong.length} signal(s) indépendants fortement compatibles et ${weak.length} signal(s) faibles/contextuels ont été croisés avec cette trajectoire.`:`Aucun signal inter-domaine assez fort pour déplacer la probabilité; ${weak.length} signal(s) faibles restent sous surveillance.`;
    f.signal_convergence={engine:'providence-cross-signal-v1',strong_signals:strong,weak_signals:weak,independent_families:new Set([...strong,...weak].map(x=>x.source_family)).size,probability_delta_points:Number(delta.toFixed(1)),base_probability_percent:Math.round(old*100),final_probability_percent:Math.round(next*100),weak_signals_do_not_move_probability_alone:true,duplicate_family_capped:true,explanation};
    const suffix=delta>0?` La convergence inter-domaines ajoute ${Number(delta.toFixed(1))} point(s) à l’estimation de base.`:' Les signaux faibles seuls ne modifient pas la probabilité.';
    f.why_now=`${String(f.why_now||f.what_we_know||'').trim()} ${explanation}${suffix}`.trim();
  }
  return forecasts;
}
