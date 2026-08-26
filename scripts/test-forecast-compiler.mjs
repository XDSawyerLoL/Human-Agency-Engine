import { compileForecastQuestion } from '../src/forecast_compiler.js';

const snapshot={forecasts:[
  {scenario_key:'nuclear-1',title:'La capacité nucléaire française augmente avant 2030',summary:'Nouveaux réacteurs et prolongation du parc en France',domain:'energy',horizon_tier:'long',event_type:'nuclear_capacity',region:'France',probability:{percent:68},time_window:{end_at:'2030-12-31T23:59:59Z'}},
  {scenario_key:'nuclear-2',title:'Le nucléaire gagne du poids dans le mix électrique français',summary:'La production nucléaire française progresse avec les investissements du parc',domain:'energy',horizon_tier:'long',event_type:'energy_mix_nuclear',region:'France',probability:{percent:63},time_window:{end_at:'2030-12-31T23:59:59Z'}},
  {scenario_key:'nuclear-3',title:'Les investissements énergétiques français se réorientent vers le nucléaire',summary:'Décisions industrielles et financement nucléaire en France',domain:'energy',horizon_tier:'medium',event_type:'energy_investment',region:'France',probability:{percent:72},time_window:{end_at:'2029-12-31T23:59:59Z'}},
  {scenario_key:'health-noise',title:'Une campagne vaccinale mondiale accélère',summary:'Santé publique',domain:'health',horizon_tier:'near',event_type:'health',region:'Monde',probability:{percent:55}}
]};

const result=compileForecastQuestion('Le nucléaire prendra-t-il une place plus importante en France d’ici 2030 ?',snapshot,{now:'2026-08-26T20:00:00Z'});
if(result.inferred.domain!=='energy') throw new Error(`domain inference failed: ${result.inferred.domain}`);
if(!result.inferred.target_date.startsWith('2030-12-31')) throw new Error(`explicit target date failed: ${result.inferred.target_date}`);
if(result.sub_forecasts.length!==4) throw new Error('compiler decomposition incomplete');
if(!result.resolution_contract.falsifiable) throw new Error('compiler must create falsifiable contract');
if(result.matched_forecasts.length<2) throw new Error('relevant forecasts were not matched');
if(result.synthesis.probability_percent===null) throw new Error('recomposition should be allowed with sufficient coverage');
if(result.synthesis.probability_percent<60||result.synthesis.probability_percent>75) throw new Error(`unexpected recomposed probability: ${result.synthesis.probability_percent}`);

const sparse=compileForecastQuestion('Les océans d’Europe, lune de Jupiter, abriteront-ils une ville humaine en 2035 ?',snapshot,{now:'2026-08-26T20:00:00Z'});
if(sparse.coverage.numeric_probability_allowed!==false) throw new Error('compiler invented a probability without coverage');
console.log(JSON.stringify({ok:true,domain:result.inferred.domain,probability:result.synthesis.probability_percent,sparse:sparse.coverage.status}));
