import { EvidenceStore } from '../src/store.js';

const store = new EvidenceStore();
const forecast = {
  scenario_key:'test-track', scenario_id:'test-track', title:'Scénario test', domain:'economy_labor', horizon_tier:'near', status:'active',
  target_date:new Date(Date.now()+86400000).toISOString(),
  probability:{estimate:.62,percent:62,interval_low:.45,interval_high:.76,interval_percent:[45,76]}
};
const t1=new Date().toISOString();
await store.appendHistory([forecast],t1);
await store.recordForecastRegistry([forecast],t1);
forecast.probability={...forecast.probability,estimate:.67,percent:67};
const t2=new Date(Date.now()+1000).toISOString();
await store.appendHistory([forecast],t2);
await store.recordForecastRegistry([forecast],t2);
const track=await store.getTrackRecord();
if(track.tracked_scenarios!==1) throw new Error(`registry count mismatch: ${track.tracked_scenarios}`);
if(track.probability_history_points!==2) throw new Error(`history count mismatch: ${track.probability_history_points}`);
if(track.scenarios_with_revisions!==1) throw new Error(`revision count mismatch: ${track.scenarios_with_revisions}`);
if(track.brier_score!==null || track.calibration_ready!==false) throw new Error('track record must not invent calibration before resolutions');
console.log('track record memory registry ok');
