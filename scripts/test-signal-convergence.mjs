import { applySignalConvergence } from '../src/signal_convergence.js';

const baseForecast=()=>({
  id:'f1',scenario_key:'f1',event_type:'media_energy_grid_stress',domain:'energy',region:'Monde',
  title:'Risque de tensions sur le réseau et les prix de l’électricité',summary:'Les contraintes électriques peuvent se transmettre aux prix et aux opérations industrielles.',
  causal_chain:['réseau électrique sous tension','marges réduites','prix plus volatils'],human_needs:['Énergie','Industrie'],watch_next:['restrictions réseau'],
  probability:{estimate:.50,percent:50,interval_low:.35,interval_high:.65,interval_percent:[35,65]},
  consolidation:{score:58,source_providers:[],source_families:[],dimensions:[]},evidence:[]
});
const now=new Date().toISOString();
const supportSignals=[
  {source_key:'grid-official',source_label:'Grid operator',source_family:'official_energy',source_trust:.94,severity:.84,observed_at:now,event_type:'media_energy_grid_stress',title:'Power grid emergency and electricity shortage',geography:'Monde',facts:{}},
  {source_key:'industry-media',source_label:'Industry radar',source_family:'global_media',source_trust:.72,severity:.72,observed_at:now,event_type:'media_industrial_stress',title:'Factory shutdowns as electricity costs rise',geography:'Monde',facts:{}},
  {source_key:'ai-capex',source_label:'AI infrastructure radar',source_family:'research_market',source_trust:.78,severity:.70,observed_at:now,event_type:'media_ai_investment',title:'Data center electricity demand accelerates',geography:'Monde',facts:{}},
  // Same family as industry-media: must not count as an extra independent family.
  {source_key:'industry-copy',source_label:'Industry copy',source_family:'global_media',source_trust:.75,severity:.75,observed_at:now,event_type:'media_industrial_stress',title:'More factory electricity pressure',geography:'Monde',facts:{}}
];
const [supportive]=applySignalConvergence([baseForecast()],supportSignals);
if((supportive.signal_convergence?.strong_signals||[]).length<2)throw new Error('expected at least two independent strong cross-domain signals');
if(!(supportive.signal_convergence.probability_delta_points>0))throw new Error(`supportive evidence must increase posterior: ${supportive.signal_convergence.probability_delta_points}`);
if(supportive.signal_convergence.independent_families>3)throw new Error('duplicate source family was counted more than once');
if(!supportive.evidence.some(x=>x.convergence_tier==='strong'))throw new Error('strong convergence evidence not published');
if(!String(supportive.why_now).includes('convergence inter-domaines'))throw new Error('convergence explanation missing from forecast');
if(supportive.evidence_posterior?.engine!=='providence-evidence-posterior-v1')throw new Error('posterior engine metadata missing');
if(!Array.isArray(supportive.evidence_posterior?.updates)||supportive.evidence_posterior.updates.length<2)throw new Error('posterior audit trail missing');
if(!supportive.evidence_posterior.updates.every(x=>x.likelihood_ratio>1))throw new Error('supportive likelihood ratios must be > 1');

const contrarySignals=[
  {source_key:'grid-restored',source_label:'Grid operator',source_family:'official_energy',source_trust:.95,severity:.86,observed_at:now,event_type:'media_energy_grid_stress',title:'Grid capacity restored after emergency',geography:'Monde',facts:{direction:'contrary'}},
  {source_key:'market-surplus',source_label:'Market monitor',source_family:'energy_market',source_trust:.84,severity:.78,observed_at:now,event_type:'energy_price_spike',title:'Electricity reserve surplus stabilizes prices',geography:'Monde',facts:{forecast_effect:'against'}}
];
const [contrary]=applySignalConvergence([baseForecast()],contrarySignals);
if(!(contrary.signal_convergence.probability_delta_points<0))throw new Error(`contrary evidence must reduce posterior: ${contrary.signal_convergence.probability_delta_points}`);
if(!(contrary.probability.percent<50))throw new Error('contrary evidence did not lower public probability');
if(!contrary.evidence_posterior.updates.every(x=>x.likelihood_ratio<1))throw new Error('contrary likelihood ratios must be < 1');
if(!String(contrary.why_now).includes('réduit'))throw new Error('negative posterior movement explanation missing');

const decisive=baseForecast();
const [singleOfficial]=applySignalConvergence([decisive],[
  {source_key:'direct-official',source_label:'Official operator',source_family:'official_direct',source_trust:.98,severity:.96,observed_at:now,event_type:'media_energy_grid_stress',title:'Official grid emergency confirmed',geography:'Monde',facts:{direction:'support'}}
]);
if(!singleOfficial.signal_convergence.posterior_applied)throw new Error('decisive direct official evidence should be eligible by itself');
if(!(singleOfficial.signal_convergence.probability_delta_points>0))throw new Error('decisive official signal should move posterior');

const weakForecast=baseForecast();
const weakSignal={source_key:'weak',source_label:'Weak context',source_family:'context',source_trust:.55,severity:.40,observed_at:now,event_type:'media_food_supply_signal',title:'General consumer discussion',geography:'Monde',facts:{}};
const before=weakForecast.probability.percent;
const [weak]=applySignalConvergence([weakForecast],[weakSignal]);
if(weak.probability.percent!==before)throw new Error('a weak signal moved probability on its own');
if(weak.signal_convergence.probability_delta_points!==0)throw new Error('weak-only delta must be zero');
if(weak.signal_convergence.posterior_applied)throw new Error('weak-only evidence must not trigger posterior application');

console.log(JSON.stringify({
  ok:true,
  support_delta:supportive.signal_convergence.probability_delta_points,
  support_final:supportive.probability.percent,
  contrary_delta:contrary.signal_convergence.probability_delta_points,
  contrary_final:contrary.probability.percent,
  single_official_delta:singleOfficial.signal_convergence.probability_delta_points,
  weak_delta:weak.signal_convergence.probability_delta_points
}));
