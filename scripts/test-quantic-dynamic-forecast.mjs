import { planDynamicForecast, buildDynamicForecast } from '../src/quantic_dynamic_forecast.js';

const originalFetch=globalThis.fetch;
globalThis.fetch=async input=>{
  const url=String(input);
  if(url.includes('gdeltproject.org'))return new Response(JSON.stringify({articles:[
    {title:'France election poll shifts ahead of 2027',domain:'example1.fr',url:'https://example1.fr/a',seendate:'20260905T000000Z'},
    {title:'French presidential race and economy',domain:'example2.fr',url:'https://example2.fr/a',seendate:'20260905T000000Z'},
    {title:'Election 2027 polling update',domain:'example3.fr',url:'https://example3.fr/a',seendate:'20260905T000000Z'}
  ]}),{status:200,headers:{'content-type':'application/json'}});
  if(url.includes('api.worldbank.org'))return new Response(JSON.stringify([{page:1,pages:1,per_page:8,total:2},[{date:'2025',value:2.1},{date:'2024',value:1.7}]]),{status:200,headers:{'content-type':'application/json'}});
  if(url.includes('fr.wikipedia.org/w/api.php'))return new Response(JSON.stringify({parse:{text:{'*':'<table class="wikitable"><tr><th>Sondeur</th><th>A</th><th>B</th></tr><tr><td>Institut</td><td>51%</td><td>49%</td></tr><tr><td>Institut 2</td><td>52%</td><td>48%</td></tr></table>'}}}),{status:200,headers:{'content-type':'application/json'}});
  if(url.includes('data.gouv.fr/api/1/datasets'))return new Response(JSON.stringify({data:[{title:'Résultats électoraux',organization:{name:'Ministère'},last_update:'2026-09-01',page:'https://data.gouv.fr/test'}]}),{status:200,headers:{'content-type':'application/json'}});
  throw new Error(`unexpected fetch ${url}`);
};

try{
  const plan=planDynamicForecast('Que va-t-il se passer pour les élections 2027 en France ?');
  if(plan.domain!=='politics'||plan.country?.iso3!=='FRA'||plan.year!==2027)throw new Error('research plan inference failed');
  const snapshot={forecasts:[{scenario_key:'weather',title:'Canicules en Europe',domain:'weather_climate',region:'Europe',status:'active',probability:{percent:81},consolidation:{score:83,source_providers:[]}}]};
  const result=await buildDynamicForecast(plan.question,snapshot);
  if(result.schema!=='providence-quantic-dynamic-forecast-v1')throw new Error('dynamic schema');
  if(result.research.sources_ok<3)throw new Error('insufficient mocked source fusion');
  if(result.estimate.numeric_probability_allowed!==false||result.estimate.probability_percent!==null)throw new Error('invented probability despite no relevant published forecasts');
  if(result.superposition?.semantics?.world_weights_are_event_probabilities!==false)throw new Error('world-weight semantics missing');
  const worlds=result.superposition?.worlds||[];
  if(worlds.length!==4)throw new Error('dynamic branches missing');
  const total=worlds.reduce((s,w)=>s+Number(w.relative_world_weight_percent||0),0);
  if(Math.abs(total-100)>.2)throw new Error(`dynamic branch weights do not sum to 100: ${total}`);
  if(!result.guardrails?.lobbying_requires_documented_public_data||!result.guardrails?.banking_signal_is_not_causal_proof)throw new Error('sensitive evidence guardrails missing');
  console.log(JSON.stringify({ok:true,domain:plan.domain,country:plan.country.name,year:plan.year,sources_ok:result.research.sources_ok,coverage:result.research.coverage_score,branches:worlds.length,numeric_probability_allowed:result.estimate.numeric_probability_allowed}));
} finally {globalThis.fetch=originalFetch;}
