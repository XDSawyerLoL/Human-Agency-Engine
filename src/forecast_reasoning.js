const clamp=(v,a,b)=>Math.max(a,Math.min(b,Number(v)||0));
const logit=p=>Math.log(clamp(p,.01,.99)/(1-clamp(p,.01,.99)));
const sigmoid=x=>1/(1+Math.exp(-x));

export function attachShadowEnsemble(f){
  const p=clamp(Number(f.probability?.estimate ?? Number(f.probability?.percent||0)/100),.03,.97);
  const confidence=clamp(Number(f.confidence_breakdown?.score||f.confidence||50)/100,.2,.98);
  const delta=clamp(Number(f.probability_delta_points||0)/100,-.2,.2);
  const favorable=(f.favorable_signals||f.probability_up_if||[]).length;
  const contrary=(f.contrary_signals||f.probability_down_if||[]).length;
  const evidenceAdjusted=.5+(p-.5)*(.55+.45*confidence);
  const trendAdjusted=clamp(p+delta*.35,.03,.97);
  const pseudoBayes=sigmoid(logit(p)+(favorable-contrary)*.055*confidence);
  const estimates=[
    {key:'model',label:'Moteur ÉVIDENCE',estimate:p,weight:.50},
    {key:'evidence',label:'Ajustement confiance',estimate:evidenceAdjusted,weight:.22},
    {key:'trend',label:'Trajectoire récente',estimate:trendAdjusted,weight:.13},
    {key:'update',label:'Mise à jour signaux',estimate:pseudoBayes,weight:.15}
  ];
  const weighted=estimates.reduce((s,x)=>s+x.estimate*x.weight,0)/estimates.reduce((s,x)=>s+x.weight,0);
  f.shadow_ensemble={
    estimate:Math.round(weighted*1000)/1000,
    percent:Math.round(weighted*100),
    components:estimates.map(x=>({...x,percent:Math.round(x.estimate*100)})),
    status:'shadow_only',
    replaces_public_probability:false,
    independence_warning:'Ces estimateurs partagent une partie des mêmes données et ne constituent pas encore un ensemble indépendant calibré.',
    promotion_rule:'Ne remplacera la probabilité publique qu’après backtests et gain mesuré de Brier/Log Loss.'
  };
  return f;
}

export function counterfactualSensitivity(f, changes=[]){
  const base=clamp(Number(f.probability?.estimate ?? Number(f.probability?.percent||0)/100),.03,.97);
  let odds=logit(base);
  const applied=[];
  for(const change of (Array.isArray(changes)?changes:[]).slice(0,8)){
    const direction=String(change.direction||'').toLowerCase()==='down'?-1:1;
    const strength=clamp(Number(change.strength||1),.25,3);
    const contribution=direction*strength*.16;
    odds+=contribution;
    applied.push({label:String(change.label||'Hypothèse').slice(0,120),direction:direction>0?'up':'down',strength,log_odds_delta:Math.round(contribution*1000)/1000});
  }
  const estimate=clamp(sigmoid(odds),.02,.98);
  const distance=Math.abs(estimate-base);
  return {
    scenario_key:f.scenario_key,
    base_probability:Math.round(base*100),
    simulated_probability:Math.round(estimate*100),
    delta_points:Math.round((estimate-base)*100),
    interval_percent:[Math.max(2,Math.round((estimate-.14-distance*.4)*100)),Math.min(98,Math.round((estimate+.14+distance*.4)*100))],
    applied,
    mode:'counterfactual_sensitivity',
    is_world_simulation:false,
    note:'Simulation locale de sensibilité. Elle indique comment les hypothèses déplacent l’estimation, sans prétendre simuler exhaustivement le monde.'
  };
}
