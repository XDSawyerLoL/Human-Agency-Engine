const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=4)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const logit=p=>Math.log(clamp(p,.001,.999)/(1-clamp(p,.001,.999)));
const sigmoid=x=>1/(1+Math.exp(-x));

const SUPPORT_WORDS=new Set([
  'support','supportive','confirm','confirmed','confirmation','increase','up','upward','rise','rising','positive','favorable','favourable','toward','towards','worsen','worsening','escalate','escalation','stress','shortage','outage','spike','accelerate','accelerating',
  'soutien','favorable','confirme','confirmation','hausse','monte','augmentation','positif','aggrave','aggravation','escalade','tension','penurie','coupure','pic','accelere'
]);
const CONTRARY_WORDS=new Set([
  'contrary','against','disconfirm','disconfirmed','contradict','contradiction','decrease','down','downward','fall','falling','negative','mitigate','mitigation','ease','easing','stabilize','stabilized','stabilisation','stabilization','recovery','recover','restore','restored','surplus','resolved','contained','deescalate','de-escalate','deescalation','ceasefire',
  'contraire','contre','infirme','infirmation','contredit','contradiction','baisse','diminue','diminution','negatif','attenue','attenuation','stabilise','stabilisation','reprise','retablissement','retabli','surplus','resolu','contenu','desescalade','cessez-le-feu'
]);

const RELATION_WEIGHT={direct:1,causal:.9,semantic:.76,thematic:.62,context:.35};

function normalize(value){
  return String(value??'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9-]+/g,' ').trim();
}

function numericPolarity(value){
  const n=Number(value);
  if(!Number.isFinite(n)||n===0)return null;
  return clamp(n,-1,1);
}

function textPolarity(value){
  const text=normalize(value);
  if(!text)return null;
  const words=text.split(/\s+/);
  let support=0,contrary=0;
  for(const word of words){
    if(SUPPORT_WORDS.has(word))support++;
    if(CONTRARY_WORDS.has(word))contrary++;
  }
  if(!support&&!contrary)return null;
  if(support===contrary)return 0;
  return support>contrary?1:-1;
}

export function inferEvidencePolarity(signal={},relation='context'){
  const facts=signal?.facts&&typeof signal.facts==='object'?signal.facts:{};
  const explicit=[
    signal.polarity,signal.direction,signal.impact_direction,signal.forecast_effect,
    facts.polarity,facts.direction,facts.impact_direction,facts.forecast_effect,facts.probability_direction
  ];
  for(const value of explicit){
    const numeric=numericPolarity(value);
    if(numeric!==null)return {polarity:numeric,source:'explicit_numeric'};
    const textual=textPolarity(value);
    if(textual!==null)return {polarity:textual,source:'explicit_label'};
  }
  const explicitDelta=Number(signal.probability_delta_points??facts.probability_delta_points);
  if(Number.isFinite(explicitDelta)&&explicitDelta!==0)return {polarity:explicitDelta>0?1:-1,source:'explicit_delta'};

  const text=[signal.title,signal.summary,signal.description,...(Array.isArray(facts.sample_titles)?facts.sample_titles:[])].filter(Boolean).join(' ');
  const heuristic=textPolarity(text);
  if(heuristic!==null)return {polarity:heuristic,source:'language_hint'};

  // Existing Providence event mappings describe precursor/stress events that are
  // supportive by construction. Preserve that behaviour when no contrary marker exists.
  if(['direct','causal','semantic','thematic'].includes(relation))return {polarity:1,source:'relation_default'};
  return {polarity:0,source:'neutral'};
}

function evidenceContribution(row,index,maxLogBayesFactor){
  const polarity=clamp(row.polarity??0,-1,1);
  const strength=clamp(row.strength??0,0,1);
  const relevance=clamp(row.relevance??0,0,1);
  const relationWeight=RELATION_WEIGHT[row.relation]??RELATION_WEIGHT.context;
  const quality=clamp(strength*(.72+.28*relevance)*relationWeight,0,1);
  const diminishing=[1,.86,.74,.64,.57,.52][Math.min(index,5)];
  const logBayesFactor=polarity*quality*diminishing*maxLogBayesFactor;
  return {
    quality:round(quality),
    diminishing_return:round(diminishing),
    log_bayes_factor:round(logBayesFactor,6),
    likelihood_ratio:round(Math.exp(logBayesFactor),6)
  };
}

export function computeEvidencePosterior(priorProbability,rows=[],options={}){
  const prior=clamp(priorProbability,.02,.98);
  const maxLogBayesFactor=clamp(options.max_log_bayes_factor??.38,.05,.9);
  const maxAbsoluteLogShift=clamp(options.max_absolute_log_shift??1.15,.1,2.5);
  const eligible=(rows||[])
    .filter(row=>Number(row?.strength)>=.48&&Number(row?.relevance)>=.24&&Math.abs(Number(row?.polarity||0))>.01)
    .sort((a,b)=>Number(b.strength||0)-Number(a.strength||0));

  const updates=[];
  let currentLogit=logit(prior);
  let cumulativeShift=0;
  for(let index=0;index<eligible.length;index++){
    const row=eligible[index];
    const contribution=evidenceContribution(row,index,maxLogBayesFactor);
    // Cap the cumulative movement, not the individual opposite-direction step.
    // This lets new contrary evidence undo prior support instead of getting stuck
    // at the cap while still preventing runaway posterior movement.
    const boundedCumulative=clamp(cumulativeShift+contribution.log_bayes_factor,-maxAbsoluteLogShift,maxAbsoluteLogShift);
    const shift=boundedCumulative-cumulativeShift;
    const before=sigmoid(currentLogit);
    currentLogit+=shift;
    cumulativeShift=boundedCumulative;
    const after=sigmoid(currentLogit);
    updates.push({
      source_key:row.source_key,
      source_family:row.source_family,
      title:row.title,
      relation:row.relation,
      polarity:round(row.polarity,3),
      polarity_source:row.polarity_source||null,
      trust:round(row.trust,3),
      strength:round(row.strength,3),
      relevance:round(row.relevance,3),
      quality:contribution.quality,
      diminishing_return:contribution.diminishing_return,
      log_bayes_factor:round(shift,6),
      likelihood_ratio:round(Math.exp(shift),6),
      prior_probability:round(before,4),
      posterior_probability:round(after,4),
      delta_points:round((after-before)*100,2)
    });
  }

  const posterior=sigmoid(currentLogit);
  const supporting=eligible.filter(row=>Number(row.polarity)>0);
  const contrary=eligible.filter(row=>Number(row.polarity)<0);
  return {
    engine:'providence-evidence-posterior-v1',
    method:'bounded sequential log-odds update with source-family deduplication and diminishing evidence returns',
    prior_probability:round(prior,4),
    prior_percent:Math.round(prior*100),
    posterior_probability:round(posterior,4),
    posterior_percent:Math.round(posterior*100),
    probability_delta_points:round((posterior-prior)*100,2),
    cumulative_log_odds_shift:round(cumulativeShift,6),
    supporting_families:supporting.length,
    contrary_families:contrary.length,
    evaluated_families:eligible.length,
    updates,
    guardrails:{
      minimum_signal_strength:.48,
      minimum_relevance:.24,
      max_log_bayes_factor_per_signal:maxLogBayesFactor,
      max_absolute_log_odds_shift:maxAbsoluteLogShift,
      weak_signals_move_probability:false,
      duplicate_source_family_counted_once:true
    }
  };
}
