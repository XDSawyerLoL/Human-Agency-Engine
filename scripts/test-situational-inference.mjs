import { buildSituationalInference, applyInferenceToBranchWeights } from '../src/situational_inference.js';

const evidence=[
  {family:'macro',status:'ok',label:'Banque mondiale · France',metrics:{indicators:[
    {key:'inflation',label:'Inflation',value:3.2,delta:.6,year:'2026'},
    {key:'unemployment',label:'Chômage',value:8.1,delta:.4,year:'2026'},
    {key:'gdp',label:'Croissance du PIB',value:.4,delta:-.7,year:'2026'}
  ]}},
  {family:'media_attention',status:'ok',label:'GDELT',metrics:{article_count:44,domain_count:17}},
  {family:'polling',status:'ok',label:'Sondages 2027',metrics:{poll_rows:16}},
  {family:'forecast_engine',status:'ok',label:'Providence',metrics:{matches:[
    {scenario_key:'politics-a',probability_percent:62,confidence_score:74,relevance:.8},
    {scenario_key:'politics-b',probability_percent:48,confidence_score:68,relevance:.6}
  ]}}
];
const electionModel={first_round:{candidates:[
  {candidate:'A',qualification_probability:94,poll_average:31},
  {candidate:'B',qualification_probability:55,poll_average:19},
  {candidate:'C',qualification_probability:47,poll_average:18}
]}};
const snapshot={
  learning:{causal_learning:{resolved_forecasts:18,active_transitions:4}},
  causal_world:{
    nodes:[
      {id:'forecast:politics-a',type:'forecast',scenario_key:'politics-a',label:'Pression politique',domain:'regulation_policy'},
      {id:'forecast:economy-next',type:'forecast',scenario_key:'economy-next',label:'Dégradation de la confiance économique',domain:'economy_labor'}
    ],
    edges:[{from:'forecast:politics-a',to:'forecast:economy-next',type:'structural_prior',strength:.66,rationale:'transition historique test',learning:{active:true,samples:12}}]
  }
};

const situation=buildSituationalInference({spec:{domain:'politics'},evidence,snapshot,electionModel});
if(situation.schema!=='providence-situational-inference-v1')throw new Error('schema mismatch');
if(!situation.deductions.some(x=>x.id==='deduction:macro-stress-cluster'))throw new Error('macro deduction missing');
if(!situation.deductions.some(x=>x.kind==='learned_structural_deduction'))throw new Error('learned structural deduction missing');
if(situation.semantics.deductions_are_causal_proof!==false)throw new Error('causal guardrail missing');
if(situation.semantics.canonical_probabilities_changed!==false)throw new Error('canonical probability guardrail missing');

const branches=[
  {world_id:'dynamic_continuity',relative_world_weight_percent:38},
  {world_id:'dynamic_recomposition',relative_world_weight_percent:27},
  {world_id:'dynamic_macro_shift',relative_world_weight_percent:21},
  {world_id:'dynamic_shock',relative_world_weight_percent:14}
];
const adjusted=applyInferenceToBranchWeights(branches,situation);
const total=adjusted.reduce((s,x)=>s+Number(x.relative_world_weight_percent||0),0);
if(Math.abs(total-100)>.11)throw new Error(`branch weights must sum to 100, got ${total}`);
if(!adjusted.some(x=>Math.abs(Number(x.inference_adjustment_points||0))>.1))throw new Error('inference did not move any branch');
console.log(JSON.stringify({ok:true,quality:situation.quality,deductions:situation.deductions.map(x=>x.id),branches:adjusted.map(x=>({id:x.world_id,w:x.relative_world_weight_percent,d:x.inference_adjustment_points}))}));
