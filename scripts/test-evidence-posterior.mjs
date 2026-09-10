import { computeEvidencePosterior, inferEvidencePolarity } from '../src/evidence_posterior.js';

const supportRows=[
  {source_key:'a',source_family:'official',title:'Official confirmation',relation:'direct',trust:.95,strength:.82,relevance:.92,polarity:1,polarity_source:'test'},
  {source_key:'b',source_family:'market',title:'Independent market signal',relation:'causal',trust:.82,strength:.70,relevance:.78,polarity:1,polarity_source:'test'}
];
const up=computeEvidencePosterior(.31,supportRows);
if(!(up.posterior_probability>.31))throw new Error('supportive posterior must be above prior');
if(!(up.probability_delta_points>0))throw new Error('supportive posterior delta must be positive');
if(up.updates.length!==2)throw new Error('supportive audit trail must contain both independent families');

const down=computeEvidencePosterior(.47,supportRows.map((row,index)=>({...row,source_key:`n${index}`,source_family:`negative-${index}`,polarity:-1})));
if(!(down.posterior_probability<.47))throw new Error('contrary posterior must be below prior');
if(!(down.probability_delta_points<0))throw new Error('contrary posterior delta must be negative');

const weak=computeEvidencePosterior(.5,[{source_key:'weak',source_family:'weak',relation:'direct',strength:.30,relevance:.9,polarity:1}]);
if(weak.posterior_probability!==.5)throw new Error('weak evidence must not move posterior');

const explicit=inferEvidencePolarity({facts:{direction:'contrary'}},'direct');
if(explicit.polarity!==-1)throw new Error('explicit contrary direction not detected');
const implicit=inferEvidencePolarity({title:'Official emergency confirmed'},'direct');
if(implicit.polarity!==1)throw new Error('supportive language/relation not detected');
const mitigated=inferEvidencePolarity({title:'Capacity restored and situation stabilized'},'direct');
if(mitigated.polarity!==-1)throw new Error('contrary language not detected');

console.log(JSON.stringify({ok:true,up:up.posterior_percent,down:down.posterior_percent,up_delta:up.probability_delta_points,down_delta:down.probability_delta_points}));
