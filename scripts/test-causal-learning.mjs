import { buildCausalLearning } from '../src/causal_learning.js';
import { buildCausalWorldModel } from '../src/causal_world_model.js';

const rows=[];
for(let i=0;i<10;i++){
  const day=String(i+1).padStart(2,'0');
  const origin=`shock-france-${i}`;
  rows.push({scenario_key:`s${i}`,domain:'supply_fuel',horizon_tier:'near',outcome:1,origin_group:origin,resolved_at:`2026-01-${day}T08:00:00Z`,meta:{forecast:{domain:'supply_fuel',horizon_tier:'near',origin_group:origin,region:'France',target_date:`2026-01-${day}T08:00:00Z`}}});
  // Duplicate upstream forecast in the same context must not inflate samples.
  rows.push({scenario_key:`s${i}-dup`,domain:'supply_fuel',horizon_tier:'near',outcome:1,origin_group:origin,resolved_at:`2026-01-${day}T09:00:00Z`,meta:{forecast:{domain:'supply_fuel',horizon_tier:'near',origin_group:origin,region:'France',target_date:`2026-01-${day}T09:00:00Z`}}});
  rows.push({scenario_key:`e${i}`,domain:'economy_labor',horizon_tier:'medium',outcome:i<9?1:0,origin_group:origin,resolved_at:`2026-01-${day}T18:00:00Z`,meta:{forecast:{domain:'economy_labor',horizon_tier:'medium',origin_group:origin,region:'France',target_date:`2026-01-${day}T18:00:00Z`}}});
}
// A downstream outcome that predates its upstream signal must not count.
rows.push({scenario_key:'late-upstream',domain:'supply_fuel',horizon_tier:'near',outcome:1,origin_group:'reverse-order',resolved_at:'2026-03-02T00:00:00Z',meta:{forecast:{domain:'supply_fuel',horizon_tier:'near',origin_group:'reverse-order',region:'France',target_date:'2026-03-02T00:00:00Z'}}});
rows.push({scenario_key:'early-downstream',domain:'economy_labor',horizon_tier:'medium',outcome:1,origin_group:'reverse-order',resolved_at:'2026-03-01T00:00:00Z',meta:{forecast:{domain:'economy_labor',horizon_tier:'medium',origin_group:'reverse-order',region:'France',target_date:'2026-03-01T00:00:00Z'}}});

const learning=buildCausalLearning(rows);
if(learning.schema!=='evidence-causal-learning-v1') throw new Error('causal learning schema missing');
const transition=learning.by_transition.find(x=>x.key==='supply_fuel>economy_labor');
if(!transition?.learning_active) throw new Error('expected supply → economy learning to activate');
if(transition.conditional_samples!==10) throw new Error(`expected 10 independent samples, got ${transition.conditional_samples}`);
if(transition.independent_context_buckets!==10) throw new Error('independent context accounting missing');
if(!(transition.learned_strength>transition.prior_strength)) throw new Error('high observed downstream rate should strengthen prior');
if(learning.guardrails.duplicate_forecast_pairs_count_as_independent_samples!==false) throw new Error('duplicate-pair guardrail broken');
if(learning.guardrails.temporal_order_required_when_dates_exist!==true) throw new Error('temporal ordering guardrail broken');
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
