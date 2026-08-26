import { EvidenceStore } from '../src/store.js';
import { recordForecastMetadata, getDueResolutionRows, resolveForecast, getLearningReport, storageReadiness } from '../src/learning_store.js';

const store=new EvidenceStore();
const at='2026-08-26T12:00:00Z';
const forecast={
  scenario_key:'learning-test',scenario_id:'learning-test',title:'Scénario binaire test',summary:'test',domain:'energy',horizon_tier:'near',region:'Monde',event_type:'test_event',origin_group:'native',target_date:'2026-08-25T00:00:00Z',status:'active',
  probability:{estimate:.7,percent:70,interval_low:.55,interval_high:.8,interval_percent:[55,80]},
  time_window:{end_at:'2026-08-25T00:00:00Z'},resolution_conditions:'Le scénario se réalise avant échéance.',falsification:'Sinon échec.',consolidation:{source_providers:[],source_families:[]}
};
await store.recordForecastRegistry([forecast],at);
await recordForecastMetadata(store,[forecast],at);
const due=await getDueResolutionRows(store,{now:new Date(at)});
if(due.length!==1||due[0].scenario_key!=='learning-test') throw new Error('due queue failed in memory mode');
await resolveForecast(store,'learning-test',{outcome:1,note:'vérité terrain test',evidence:[{url:'https://example.test'}]});
const learning=await getLearningReport(store);
if(learning.calibration.scorable_resolutions!==1) throw new Error('resolved forecast did not enter calibration');
if(learning.calibration.global.brier===null) throw new Error('Brier not calculated after resolution');
const storage=await storageReadiness(store);
if(storage.persistent!==false||storage.mode!=='memory') throw new Error('memory readiness incorrectly reports persistence');
console.log(JSON.stringify({ok:true,brier:learning.calibration.global.brier,persistent:storage.persistent}));
