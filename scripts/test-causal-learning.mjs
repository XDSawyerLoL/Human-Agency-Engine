import { buildCausalLearning } from '../src/causal_learning.js';
import { buildCausalWorldModel } from '../src/causal_world_model.js';

const rows=[];
for(let i=0;i<10;i++){
  rows.push({scenario_key:`s${i}`,domain:'supply_fuel',horizon_tier:'near',outcome:1,origin_group:'shock-france',meta:{forecast:{domain:'supply_fuel',horizon_tier:'near',origin_group:'shock-france',region:'France'}}});
}
for(let i=0;i<10;i++){
  rows.push({scenario_key:`e${i}`,domain:'economy_labor',horizon_tier:'medium',outcome:i<9?1:0,origin_group:'shock-france',meta:{forecast:{domain:'economy_labor',horizon_tier:'medium',origin_group:'shock-france',region:'France'}}});
}
const learning=buildCausalLearning(rows);
if(learning.schema!=='evidence-causal-learning-v1') throw new Error('causal learning schema missing');
const transition=learning.by_transition.find(x=>x.key==='supply_fuel>economy_labor');
if(!transition?.learning_active) throw new Error('expected supply → economy learning to activate');
if(transition.conditional_samples<8) throw new Error('causal learning sample guardrail broken');
if(!(transition.learned_strength>transition.prior_strength)) throw new Error('high observed downstream rate should strengthen prior');
if(learning.guardrails.causal_proof!==false||learning.guardrails.learns_conditional_association_not_intervention_effect!==true) throw new Error('causal learning guardrails broken');

const forecasts=[
 {scenario_key:'supply-now',title:'Approvisionnement sous tension',domain:'supply_fuel',origin_group:'shock-france',region:'France',horizon_tier:'near',horizon_order:1,probability:{estimate:.62,percent:62},confidence:70,causal_chain:['retards','stocks réduits','coûts logistiques'],evidence:[]},
 {scenario_key:'economy-next',title:'Activité économique sous pression',domain:'economy_labor',origin_group:'shock-france',region:'France',horizon_tier:'medium',horizon_order:2,probability:{estimate:.55,percent:55},confidence:67,causal_chain:['coûts élevés','marges réduites','activité ralentie'],evidence:[]}
];
const graph=buildCausalWorldModel(forecasts,learning);
const edge=graph.edges.find(e=>e.from==='forecast:supply-now'&&e.to==='forecast:economy-next'&&e.type==='structural_prior');
if(!edge) throw new Error('learned structural edge missing');
if(edge.status!=='learned_structural_prior'||edge.learning?.active!==true) throw new Error('learned structural prior not exposed');
if(graph.metrics.learned_structural_edges<1) throw new Error('learned edge metric missing');
if(graph.contract.learned_association_is_intervention_effect!==false) throw new Error('graph causal guardrail broken');

console.log(JSON.stringify({ok:true,samples:transition.conditional_samples,prior:transition.prior_strength,learned:transition.learned_strength,edge_strength:edge.strength}));
