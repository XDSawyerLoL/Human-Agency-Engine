import { buildElectionDeduction } from '../src/election_deduction_engine.js';

const electionModel={
  first_round:{
    candidates:[
      {candidate:'Candidate A',qualification_probability:96,poll_average:31},
      {candidate:'Candidate B',qualification_probability:58,poll_average:21},
      {candidate:'Candidate C',qualification_probability:41,poll_average:19}
    ],
    pair_scenarios:[
      {title:'Second tour : Candidate A / Candidate B',candidates:['Candidate A','Candidate B'],probability_percent:56},
      {title:'Second tour : Candidate A / Candidate C',candidates:['Candidate A','Candidate C'],probability_percent:39},
      {title:'Second tour : Candidate B / Candidate C',candidates:['Candidate B','Candidate C'],probability_percent:5}
    ]
  },
  second_round:[
    {matchup:['Candidate A','Candidate B'],polls:4,model_win_probability:[{candidate:'Candidate A',percent:46},{candidate:'Candidate B',percent:54}]},
    {matchup:['Candidate A','Candidate C'],polls:3,model_win_probability:[{candidate:'Candidate A',percent:57},{candidate:'Candidate C',percent:43}]}
  ]
};

const dynamicForecast={research:{evidence:[
  {id:'wb',family:'macro',label:'Banque mondiale',status:'ok',quality:86,metrics:{indicators:[{label:'Inflation',delta:0.5},{label:'Chômage',delta:-0.2}]}},
  {id:'eurostat',family:'macro_independent_eu',correlation_group:'macro_conditions',label:'Eurostat',status:'ok',quality:92,independence:{source_owner:'Eurostat'},metrics:{indicators:[{label:'Inflation harmonisée',value:2.4},{label:'Chômage harmonisé',value:7.3}]}},
  {id:'gdelt',family:'media_attention',label:'GDELT',status:'ok',quality:64,metrics:{domain_count:18,article_count:42}},
  {id:'hatvp',family:'lobbying_transparency',correlation_group:'institutional_influence',label:'HATVP',status:'ok',quality:94,independence:{source_owner:'HATVP'},metrics:{}},
  {id:'hatvp',family:'lobbying_transparency',correlation_group:'institutional_influence',label:'HATVP',status:'ok',quality:94,independence:{source_owner:'HATVP'},metrics:{}}
]}};

const result=buildElectionDeduction({electionModel,dynamicForecast});
if(result.schema!=='providence-election-deduction-v1')throw new Error('schema mismatch');
if(result.final_outcome.status!=='publishable')throw new Error(`final outcome should be publishable: ${result.final_outcome.status}`);
if(Math.abs(Number(result.final_outcome.coverage_percent)-95)>.2)throw new Error(`coverage mismatch ${result.final_outcome.coverage_percent}`);
if(Math.abs(Number(result.final_outcome.unresolved_probability_mass_percent)-5)>.2)throw new Error('unresolved mass mismatch');
if(!result.final_outcome.winner?.candidate)throw new Error('winner ranking missing');
const total=result.final_outcome.candidates.reduce((s,x)=>s+Number(x.win_probability_percent||0),0);
if(Math.abs(total-95)>.3)throw new Error(`winner mass should equal covered pair mass: ${total}`);
if(result.evidence_independence.duplicates_suppressed!==1)throw new Error(`duplicate suppression failed: ${result.evidence_independence.duplicates_suppressed}`);
if(result.learning.no_double_counting!==true)throw new Error('learning guardrail missing');
if(!result.deductions.some(x=>x.key==='final_result'))throw new Error('final result deduction missing');
console.log(JSON.stringify({ok:true,winner:result.final_outcome.winner,coverage:result.final_outcome.coverage_percent,unresolved:result.final_outcome.unresolved_probability_mass_percent,independence:result.evidence_independence}));
