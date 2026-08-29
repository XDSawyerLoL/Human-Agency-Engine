import { buildSuperposition } from '../src/superposition_engine.js';

const mk=(key,title,domain,percent,confidence,region='Monde',delta=0)=>({
  scenario_key:key,title,domain,region,horizon_tier:'near',status:'active',
  probability:{percent},probability_delta_points:delta,
  consolidation:{score:confidence,source_providers:[{key:'a'},{key:'b'},{key:'c'}]},
  signal_convergence:{strong_signals:[{title:'signal 1'},{title:'signal 2'}],weak_signals:[{title:'weak'}]},
  falsification:'La condition opposée est observée.'
});
const snapshot={generated_at:new Date().toISOString(),forecasts:[
  mk('a','Tensions logistiques en Europe','supply_fuel',72,78,'Europe',5),
  mk('b','Ralentissement industriel européen','economy_labor',63,70,'Europe',2),
  mk('c','Perturbation satellitaire','cyber_technology',58,74,'Monde',1),
  mk('d','Risque sanitaire saisonnier','public_health',49,66,'Europe',0)
]};
const result=buildSuperposition(snapshot,{limit:4});
if(result.schema!=='providence-superposition-v1')throw new Error('schema');
if(result.worlds.length!==4)throw new Error(`world count ${result.worlds.length}`);
const sum=result.worlds.reduce((a,w)=>a+w.relative_world_weight_percent,0);
if(Math.abs(sum-100)>.11)throw new Error(`weights do not sum to 100: ${sum}`);
if(result.semantics.world_weights_are_event_probabilities!==false)throw new Error('weights incorrectly labelled as probabilities');
if(result.semantics.quantum_computing_claim!==false)throw new Error('quantum claim must be false');
if(result.worlds[0].forecast_probability_percent!==72)throw new Error('canonical probability changed');
if(!result.worlds.every(w=>w.canonical_probability_untouched===true))throw new Error('canonical flag');
if(typeof result.consensus.uncertainty_index!=='number')throw new Error('uncertainty index');
console.log(JSON.stringify({ok:true,worlds:result.worlds.length,weights:result.worlds.map(w=>w.relative_world_weight_percent),uncertainty:result.consensus.uncertainty_index}));
