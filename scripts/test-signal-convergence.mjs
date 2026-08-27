import { applySignalConvergence } from '../src/signal_convergence.js';

const baseForecast=()=>({
  id:'f1',scenario_key:'f1',event_type:'media_energy_grid_stress',domain:'energy',region:'Monde',
  title:'Risque de tensions sur le réseau et les prix de l’électricité',summary:'Les contraintes électriques peuvent se transmettre aux prix et aux opérations industrielles.',
  causal_chain:['réseau électrique sous tension','marges réduites','prix plus volatils'],human_needs:['Énergie','Industrie'],watch_next:['restrictions réseau'],
  probability:{estimate:.50,percent:50,interval_low:.35,interval_high:.65,interval_percent:[35,65]},
  consolidation:{score:58,source_providers:[],source_families:[],dimensions:[]},evidence:[]
});
const now=new Date().toISOString();
const signals=[
  {source_key:'grid-official',source_label:'Grid operator',source_family:'official_energy',source_trust:.94,severity:.84,observed_at:now,event_type:'media_energy_grid_stress',title:'Power grid emergency and electricity shortage',geography:'Monde',facts:{}},
  {source_key:'industry-media',source_label:'Industry radar',source_family:'global_media',source_trust:.72,severity:.72,observed_at:now,event_type:'media_industrial_stress',title:'Factory shutdowns as electricity costs rise',geography:'Monde',facts:{}},
  {source_key:'ai-capex',source_label:'AI infrastructure radar',source_family:'research_market',source_trust:.78,severity:.70,observed_at:now,event_type:'media_ai_investment',title:'Data center electricity demand accelerates',geography:'Monde',facts:{}},
  // Same family as industry-media: must not count as an extra independent family.
  {source_key:'industry-copy',source_label:'Industry copy',source_family:'global_media',source_trust:.75,severity:.75,observed_at:now,event_type:'media_industrial_stress',title:'More factory electricity pressure',geography:'Monde',facts:{}}
];
const [strong]=applySignalConvergence([baseForecast()],signals);
if((strong.signal_convergence?.strong_signals||[]).length<2)throw new Error('expected at least two independent strong cross-domain signals');
if(!(strong.signal_convergence.probability_delta_points>0&&strong.signal_convergence.probability_delta_points<=6))throw new Error(`probability boost out of bounds: ${strong.signal_convergence.probability_delta_points}`);
if(strong.signal_convergence.independent_families>3)throw new Error('duplicate source family was counted more than once');
if(!strong.evidence.some(x=>x.convergence_tier==='strong'))throw new Error('strong convergence evidence not published');
if(!String(strong.why_now).includes('convergence inter-domaines'))throw new Error('convergence explanation missing from forecast');

const weakForecast=baseForecast();
const weakSignal={source_key:'weak',source_label:'Weak context',source_family:'context',source_trust:.55,severity:.40,observed_at:now,event_type:'media_food_supply_signal',title:'General consumer discussion',geography:'Monde',facts:{}};
const before=weakForecast.probability.percent;
const [weak]=applySignalConvergence([weakForecast],[weakSignal]);
if(weak.probability.percent!==before)throw new Error('a weak signal moved probability on its own');
if(weak.signal_convergence.probability_delta_points!==0)throw new Error('weak-only delta must be zero');

console.log(JSON.stringify({ok:true,strong:(strong.signal_convergence.strong_signals||[]).length,weak:(strong.signal_convergence.weak_signals||[]).length,delta:strong.signal_convergence.probability_delta_points,final:strong.probability.percent}));