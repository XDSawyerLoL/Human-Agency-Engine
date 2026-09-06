import { buildElectionOutcomeProjection } from '../src/election_outcome_inference.js';

const model={
  election:'Présidentielle française 2027',
  quality:{score:76},
  first_round:{
    candidates:[
      {candidate:'Candidate A',poll_average:31,qualification_probability:96},
      {candidate:'Candidate B',poll_average:21,qualification_probability:58},
      {candidate:'Candidate C',poll_average:19,qualification_probability:41}
    ],
    pair_scenarios:[
      {scenario_key:'ab',title:'Second tour : Candidate A / Candidate B',candidates:['Candidate A','Candidate B'],probability_percent:56},
      {scenario_key:'ac',title:'Second tour : Candidate A / Candidate C',candidates:['Candidate A','Candidate C'],probability_percent:39},
      {scenario_key:'bc',title:'Second tour : Candidate B / Candidate C',candidates:['Candidate B','Candidate C'],probability_percent:5}
    ]
  },
  second_round:[
    {matchup:['Candidate A','Candidate B'],polls:4,model_win_probability:[{candidate:'Candidate A',percent:46},{candidate:'Candidate B',percent:54}]}
  ]
};
const situation={quality:{score:68},pressure:{recomposition:4,shock:2,macro_shift:5},deductions:[{id:'deduction:test'}]};
const result=buildElectionOutcomeProjection(model,situation);
if(result.schema!=='providence-election-outcome-v1'||result.status!=='ok')throw new Error('projection unavailable');
if(Math.abs(result.candidates.reduce((s,x)=>s+Number(x.victory_probability_percent||0),0)-100)>.5)throw new Error('victory probabilities not normalized');
if(Math.abs(Number(result.coverage.direct_head_to_head_coverage_percent)-56)>.3)throw new Error(`direct coverage mismatch ${result.coverage.direct_head_to_head_coverage_percent}`);
if(!result.pair_outcomes.some(x=>x.method==='synthetic_runoff_prior'))throw new Error('missing conservative synthetic runoff');
if(!result.candidates.some(x=>Number(x.inferred_runoff_contribution_points)>0))throw new Error('inferred contribution missing');
if(!result.candidates.every(x=>Array.isArray(x.interval_percent)&&x.interval_percent.length===2))throw new Error('uncertainty interval missing');
if(result.semantics.synthetic_runoff_is_observed_data!==false||result.semantics.situational_deductions_are_observed_data!==false)throw new Error('inference semantics missing');
for(const pair of result.pair_outcomes.filter(x=>x.method==='synthetic_runoff_prior'))for(const x of pair.conditional_outcome)if(x.conditional_win_percent<38||x.conditional_win_percent>62)throw new Error('synthetic runoff escaped conservative bounds');
console.log(JSON.stringify({ok:true,winner:result.winner_projection,quality:result.quality,coverage:result.coverage,pairs:result.pair_outcomes}));
