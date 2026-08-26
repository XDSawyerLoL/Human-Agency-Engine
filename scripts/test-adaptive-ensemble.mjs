import { buildAdaptiveEnsembleLearning, attachAdaptiveEnsemble } from '../src/adaptive_ensemble.js';

const rows=[];
for(let i=0;i<60;i++){
  const outcome=i%2;
  const good=outcome?.82:.18;
  const bad=outcome?.25:.75;
  rows.push({
    scenario_key:`resolved-${i}`,
    domain:'energy',horizon_tier:'medium',origin_group:'native',
    first_probability:i%3===0?good:.58,
    outcome,
    meta:{forecast:{first_adaptive_ensemble:{
      estimate:good,
      components:[
        {key:'model',estimate:i%3===0?good:.58},
        {key:'evidence_quality',estimate:good},
        {key:'trajectory',estimate:bad},
        {key:'signal_update',estimate:good}
      ]
    }}}
  });
}
const ensemble=buildAdaptiveEnsembleLearning(rows);
const signal=ensemble.by_component.find(x=>x.key==='signal_update');
const trajectory=ensemble.by_component.find(x=>x.key==='trajectory');
if(!signal?.ready||!trajectory?.ready) throw new Error('component histories not ready');
if(!(signal.brier<trajectory.brier)) throw new Error('Brier ranking failed');
if(!(signal.reliability_multiplier>trajectory.reliability_multiplier)) throw new Error('adaptive reliability did not reward better component');
if(ensemble.replaces_public_probability!==false) throw new Error('guardrail must keep public probability unchanged');

const learning={
  calibration:{
    calibration_ready:true,
    global:{base_rate:.5},
    by_domain:[{key:'energy',ready:true,n:60,base_rate:.5}],
    by_horizon:[{key:'medium',ready:true,n:60,base_rate:.5}],
    by_origin:[{key:'native',ready:true,n:60,base_rate:.5}]
  },
  ensemble
};
const forecast={
  scenario_key:'current',domain:'energy',horizon_tier:'medium',origin_group:'native',
  probability:{estimate:.64,percent:64},confidence_breakdown:{score:78},probability_delta_points:4,
  favorable_signals:['a','b','c'],contrary_signals:['d']
};
attachAdaptiveEnsemble(forecast,learning);
if(!forecast.adaptive_ensemble||forecast.adaptive_ensemble.components.length<5) throw new Error('adaptive ensemble not attached');
const weightSum=forecast.adaptive_ensemble.components.reduce((s,x)=>s+x.weight,0);
if(Math.abs(weightSum-1)>.01) throw new Error(`weights do not normalize: ${weightSum}`);
const liveSignal=forecast.adaptive_ensemble.components.find(x=>x.key==='signal_update');
const liveTrajectory=forecast.adaptive_ensemble.components.find(x=>x.key==='trajectory');
if(!(liveSignal.reliability_multiplier>liveTrajectory.reliability_multiplier)) throw new Error('learned multipliers not applied');
if(forecast.adaptive_ensemble.replaces_public_probability!==false) throw new Error('forecast guardrail broken');
console.log(JSON.stringify({ok:true,signal_brier:signal.brier,trajectory_brier:trajectory.brier,ensemble_percent:forecast.adaptive_ensemble.percent}));
