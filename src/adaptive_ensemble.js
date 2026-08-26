const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const round=(v,n=4)=>Number.isFinite(Number(v))?Number(Number(v).toFixed(n)):null;
const logit=p=>Math.log(clamp(p,.001,.999)/(1-clamp(p,.001,.999)));
const sigmoid=x=>1/(1+Math.exp(-x));

const BASE_WEIGHTS={
  model:.36,
  empirical_base_rate:.16,
  evidence_quality:.16,
  trajectory:.12,
  signal_update:.12,
  origin_prior:.08
};

function score(records=[]){
  const rows=records.filter(r=>[0,1].includes(Number(r?.outcome))&&Number.isFinite(Number(r?.estimate)));
  if(!rows.length) return {n:0,brier:null,log_loss:null,hit_rate:null};
  let brier=0,logLoss=0,hits=0;
  for(const row of rows){
    const p=clamp(row.estimate,.001,.999); const y=Number(row.outcome);
    brier+=(p-y)**2;
    logLoss+=-(y*Math.log(p)+(1-y)*Math.log(1-p));
    hits+=((p>=.5?1:0)===y)?1:0;
  }
  return {n:rows.length,brier:round(brier/rows.length),log_loss:round(logLoss/rows.length),hit_rate:round(hits/rows.length)};
}

function firstEnsemble(row){
  return row?.meta?.forecast?.first_adaptive_ensemble || row?.meta?.forecast?.adaptive_ensemble || null;
}

function componentRecords(rows,key,domain=null){
  const out=[];
  for(const row of rows){
    if(domain && String(row?.domain||'unknown')!==String(domain)) continue;
    if(![0,1].includes(Number(row?.outcome))) continue;
    if(key==='model'){
      if(Number.isFinite(Number(row.first_probability))) out.push({estimate:Number(row.first_probability),outcome:Number(row.outcome)});
      continue;
    }
    const component=(firstEnsemble(row)?.components||[]).find(x=>x?.key===key);
    if(Number.isFinite(Number(component?.estimate))) out.push({estimate:Number(component.estimate),outcome:Number(row.outcome)});
  }
  return out;
}

function reliabilityMultiplier(stats){
  if(!stats || stats.n<8 || stats.brier===null) return 1;
  const sampleConfidence=stats.n/(stats.n+24);
  const skill=clamp((.25-stats.brier)/.18,-.8,1.2);
  return round(clamp(1+skill*.7*sampleConfidence,.45,1.75),4);
}

function performanceRow(key,rows,domain=null){
  const stats=score(componentRecords(rows,key,domain));
  return {key,...stats,reliability_multiplier:reliabilityMultiplier(stats),ready:stats.n>=8};
}

export function buildAdaptiveEnsembleLearning(rows=[]){
  const keys=Object.keys(BASE_WEIGHTS);
  const byComponent=keys.map(key=>performanceRow(key,rows));
  const domains=[...new Set(rows.map(r=>String(r?.domain||'unknown')))];
  const byDomain=[];
  for(const domain of domains){
    for(const key of keys){
      const item=performanceRow(key,rows,domain);
      if(item.n) byDomain.push({domain,...item});
    }
  }

  const liveRows=rows.filter(r=>Number.isFinite(Number(firstEnsemble(r)?.estimate)));
  const ensembleScore=score(liveRows.map(r=>({estimate:Number(firstEnsemble(r).estimate),outcome:Number(r.outcome)})));
  const publicSameSample=score(liveRows.map(r=>({estimate:Number(r.first_probability),outcome:Number(r.outcome)})));
  const brierImprovement=ensembleScore.brier!==null&&publicSameSample.brier!==null?round(publicSameSample.brier-ensembleScore.brier):null;
  const logLossImprovement=ensembleScore.log_loss!==null&&publicSameSample.log_loss!==null?round(publicSameSample.log_loss-ensembleScore.log_loss):null;
  const promotionReady=ensembleScore.n>=50 && Number(brierImprovement)>=.005 && Number(logLossImprovement)>0;

  return {
    status:'shadow_learning',
    method:'historical component Brier with shrinkage toward prior weights',
    minimum_component_samples:8,
    promotion_minimum_live_resolutions:50,
    by_component:byComponent,
    by_domain:byDomain,
    live_backtest:{
      n:ensembleScore.n,
      adaptive_ensemble:ensembleScore,
      public_model_same_sample:publicSameSample,
      brier_improvement:brierImprovement,
      log_loss_improvement:logLossImprovement
    },
    promotion_ready:promotionReady,
    replaces_public_probability:false,
    guardrail:'La probabilité publique reste celle du modèle principal jusqu’à un gain live mesuré sur au moins 50 résolutions.'
  };
}

function calibrationBaseRate(f,learning){
  const calibration=learning?.calibration||{};
  const domain=(calibration.by_domain||[]).find(x=>x.key===f.domain&&x.ready&&Number.isFinite(Number(x.base_rate)));
  const horizon=(calibration.by_horizon||[]).find(x=>x.key===f.horizon_tier&&x.ready&&Number.isFinite(Number(x.base_rate)));
  if(domain&&horizon){
    const total=Math.max(1,Number(domain.n)+Number(horizon.n));
    return clamp((Number(domain.base_rate)*Number(domain.n)+Number(horizon.base_rate)*Number(horizon.n))/total,.03,.97);
  }
  if(domain) return clamp(domain.base_rate,.03,.97);
  if(horizon) return clamp(horizon.base_rate,.03,.97);
  if(calibration.calibration_ready&&Number.isFinite(Number(calibration.global?.base_rate))) return clamp(calibration.global.base_rate,.03,.97);
  return null;
}

function originBaseRate(f,learning){
  const row=(learning?.calibration?.by_origin||[]).find(x=>x.key===(f.origin_group||'native')&&x.ready&&Number.isFinite(Number(x.base_rate)));
  return row?clamp(row.base_rate,.03,.97):null;
}

function learnedMultiplier(key,domain,ensembleLearning){
  const domainRow=(ensembleLearning?.by_domain||[]).find(x=>x.domain===domain&&x.key===key&&x.ready);
  if(domainRow) return {multiplier:Number(domainRow.reliability_multiplier)||1,samples:Number(domainRow.n)||0,scope:`domain:${domain}`};
  const globalRow=(ensembleLearning?.by_component||[]).find(x=>x.key===key&&x.ready);
  if(globalRow) return {multiplier:Number(globalRow.reliability_multiplier)||1,samples:Number(globalRow.n)||0,scope:'global'};
  return {multiplier:1,samples:0,scope:'prior'};
}

export function attachAdaptiveEnsemble(f,learning={}){
  const p=clamp(Number(f.probability?.estimate ?? Number(f.probability?.percent||0)/100),.03,.97);
  const confidence=clamp(Number(f.confidence_breakdown?.score||f.confidence||50)/100,.2,.98);
  const delta=clamp(Number(f.probability_delta_points||0)/100,-.25,.25);
  const favorable=(f.favorable_signals||f.probability_up_if||[]).length;
  const contrary=(f.contrary_signals||f.probability_down_if||[]).length;
  const empiricalBase=calibrationBaseRate(f,learning);
  const originPrior=originBaseRate(f,learning);
  const anchor=empiricalBase??.5;

  const candidates=[
    {key:'model',label:'Modèle principal',estimate:p},
    empiricalBase===null?null:{key:'empirical_base_rate',label:'Taux de base empirique',estimate:empiricalBase},
    {key:'evidence_quality',label:'Qualité des preuves',estimate:clamp(anchor+(p-anchor)*(.48+.52*confidence),.03,.97)},
    {key:'trajectory',label:'Trajectoire temporelle',estimate:clamp(p+delta*.35,.03,.97)},
    {key:'signal_update',label:'Balance des signaux',estimate:clamp(sigmoid(logit(p)+(favorable-contrary)*.055*confidence),.03,.97)},
    originPrior===null?null:{key:'origin_prior',label:'Historique du moteur d’origine',estimate:originPrior}
  ].filter(Boolean);

  const ensembleLearning=learning?.ensemble||{};
  const weighted=candidates.map(component=>{
    const learned=learnedMultiplier(component.key,f.domain,ensembleLearning);
    const prior=BASE_WEIGHTS[component.key]||.05;
    return {...component,base_weight:prior,reliability_multiplier:learned.multiplier,training_samples:learned.samples,weight_scope:learned.scope,raw_weight:prior*learned.multiplier};
  });
  const total=weighted.reduce((sum,x)=>sum+x.raw_weight,0)||1;
  const components=weighted.map(x=>({...x,weight:round(x.raw_weight/total,4),estimate:round(x.estimate,4),percent:Math.round(x.estimate*100)}));
  const estimate=clamp(components.reduce((sum,x)=>sum+x.estimate*x.weight,0),.02,.98);

  f.adaptive_ensemble={
    estimate:round(estimate,4),
    percent:Math.round(estimate*100),
    components,
    status:'shadow_learning',
    learning_resolutions:Number(ensembleLearning?.live_backtest?.n||0),
    promotion_ready:Boolean(ensembleLearning?.promotion_ready),
    replaces_public_probability:false,
    weight_source:'historical Brier + sample shrinkage + domain fallback',
    guardrail:'Aucune promotion automatique : le Track Record doit d’abord démontrer un gain live mesuré.'
  };
  return f;
}
