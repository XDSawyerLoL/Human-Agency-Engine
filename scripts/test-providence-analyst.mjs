import { analystStatus, buildAnalystContext, answerProvidence } from '../src/providence_analyst.js';

const snapshot={generated_at:new Date().toISOString(),causal_world:{metrics:{nodes:10,edges:14,learned_structural_edges:2}},forecasts:[{
  scenario_key:'alpha',title:'Tensions logistiques en Europe',domain:'supply_fuel',region:'Europe',horizon_tier:'near',status:'active',probability:{percent:71},probability_delta_points:4,
  consolidation:{score:76,source_providers:[{key:'fred',label:'FRED'},{key:'gdelt',label:'GDELT'}]},
  signal_convergence:{strong_signals:[{title:'Ports sous tension'}],weak_signals:[{title:'Coûts de transport'}]},
  causal_chain:['capacité portuaire','délais logistiques'],falsification:'Les délais reviennent à leur niveau de référence.',watch_next:['indices de fret']
}]};
const trackRecord={calibration:{global:{brier:.18,log_loss:.42,ece:.07}},resolution:{resolved:12}};
const context=buildAnalystContext(snapshot,trackRecord,{query:'Europe logistique'});
if(context.system_contract.llm_cannot_change_probability!==true)throw new Error('LLM write contract missing');
if(context.system_contract.world_weight_is_not_probability!==true)throw new Error('world weight contract missing');
if(context.forecasts[0].probability_percent!==71)throw new Error('probability changed');
if(context.superposition.semantics.world_weights_are_event_probabilities!==false)throw new Error('superposition semantics');
const status=analystStatus();
if(typeof status.configured!=='boolean'||status.execution_authority!==false||status.tools_enabled!==false)throw new Error('status contract');
if(!status.configured){const answer=await answerProvidence({message:'Que vois-tu venir ?',snapshot,trackRecord,history:[]});if(answer.provider!=='engine_only')throw new Error('engine fallback');if(!answer.text.includes('probabilité publique'))throw new Error('grounded fallback');}
console.log(JSON.stringify({ok:true,configured:status.configured,worlds:context.superposition.worlds.length,probability:context.forecasts[0].probability_percent}));
