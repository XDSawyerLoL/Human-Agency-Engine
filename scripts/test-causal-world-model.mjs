import { buildCausalWorldModel, attachCausalContext, simulateCausalScenario } from '../src/causal_world_model.js';

const forecasts=[
  {
    scenario_key:'hazard-1',title:'Inondations : accès perturbés',domain:'natural_hazards',origin_group:'flood|france',region:'France',horizon_tier:'immediate',horizon_order:0,
    probability:{estimate:.72,percent:72},confidence_breakdown:{score:82},target_date:'2026-09-01T00:00:00Z',
    causal_chain:['inondation sévère','routes et réseaux exposés','accès restreints','retards logistiques'],
    evidence:[{source_key:'copernicus',source_label:'Copernicus',source_family:'official_primary',source_trust:.94}]
  },
  {
    scenario_key:'supply-1',title:'Approvisionnements locaux sous pression',domain:'supply_fuel',origin_group:'flood|france',region:'France',horizon_tier:'near',horizon_order:1,
    probability:{estimate:.61,percent:61},confidence_breakdown:{score:74},target_date:'2026-09-15T00:00:00Z',
    causal_chain:['accès perturbés','livraisons retardées','stocks locaux sous pression','hausse temporaire de coûts'],
    evidence:[{source_key:'copernicus',source_label:'Copernicus',source_family:'official_primary',source_trust:.94}]
  },
  {
    scenario_key:'economy-1',title:'Coûts locaux et activité affectés',domain:'economy_labor',origin_group:'flood|france',region:'France',horizon_tier:'medium',horizon_order:2,
    probability:{estimate:.54,percent:54},confidence_breakdown:{score:68},target_date:'2026-12-31T00:00:00Z',
    causal_chain:['coûts logistiques élevés','marges sous pression','activité locale ralentie','emploi et investissement prudents'],
    evidence:[{source_key:'fred',source_label:'FRED',source_family:'official_statistics',source_trust:.9}]
  }
];

const graph=buildCausalWorldModel(forecasts);
if(graph.schema!=='evidence-causal-world-v1') throw new Error('causal graph schema missing');
if(graph.metrics.forecast_nodes!==3) throw new Error(`expected 3 forecast nodes, got ${graph.metrics.forecast_nodes}`);
if(!(graph.metrics.evidence_backed_edges>=2)) throw new Error('evidence support edges missing');
const structural=graph.edges.filter(e=>e.type==='structural_prior');
if(!structural.some(e=>e.from==='forecast:hazard-1'&&e.to==='forecast:supply-1')) throw new Error('hazard → supply structural prior missing');
if(!structural.some(e=>e.from==='forecast:supply-1'&&e.to==='forecast:economy-1')) throw new Error('supply → economy structural prior missing');

attachCausalContext(forecasts,graph);
if(!forecasts[0].causal_context?.downstream_scenarios?.some(x=>x.scenario_key==='supply-1')) throw new Error('causal context not attached');

const sim=simulateCausalScenario(graph,forecasts,[{target:'hazard-1',direction:'up',strength:1.4}],{max_hops:4});
if(sim.schema!=='evidence-scenario-lab-v1') throw new Error('scenario lab schema missing');
const hazard=sim.affected_forecasts.find(x=>x.scenario_key==='hazard-1');
const supply=sim.affected_forecasts.find(x=>x.scenario_key==='supply-1');
const economy=sim.affected_forecasts.find(x=>x.scenario_key==='economy-1');
if(!hazard||hazard.delta_points<=0) throw new Error('direct intervention did not move target forecast');
if(!supply||supply.delta_points<=0) throw new Error('first-order propagation failed');
if(!economy||economy.delta_points<=0) throw new Error('second-order propagation failed');
if(!economy.paths.some(p=>p.hops>=2)) throw new Error('second-order path not exposed');
if(sim.guardrails.is_causal_proof!==false||sim.guardrails.replaces_public_probability!==false) throw new Error('Scenario Lab guardrails broken');

const down=simulateCausalScenario(graph,forecasts,[{target:'domain:supply_fuel',direction:'down',strength:1}],{max_hops:3});
const economyDown=down.affected_forecasts.find(x=>x.scenario_key==='economy-1');
if(!economyDown||economyDown.delta_points>=0) throw new Error('downward domain intervention did not propagate');

console.log(JSON.stringify({ok:true,nodes:graph.metrics.nodes,edges:graph.metrics.edges,structural:structural.length,second_order_delta:economy.delta_points}));
