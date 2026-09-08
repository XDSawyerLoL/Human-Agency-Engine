import '../public/providence-early-warning-v17.js';
import assert from 'node:assert/strict';

const E=globalThis.ProvidenceEarlyWarning;
assert.ok(E,'Early warning engine must be exposed');

const now=Date.now();
const forecast={
  title:'Test scenario',status:'active',region:'Europe',horizon_label:'Jours & semaines',origin_group:'test|eu',event_type:'test',
  probability:{percent:68,estimate:.68},confidence:74,
  probability_history:[
    {at:new Date(now-23*3600000).toISOString(),percent:57},
    {at:new Date(now-8*3600000).toISOString(),percent:61},
    {at:new Date(now-1*3600000).toISOString(),percent:68}
  ],
  evidence:[
    {source_key:'official-a',source_family:'official',observed_at:new Date(now-2*3600000).toISOString()},
    {source_key:'research-b',source_family:'research',observed_at:new Date(now-3*3600000).toISOString()}
  ],
  consolidation:{score:74,source_providers:[{key:'official-a'},{key:'research-b'}],source_families:[{key:'official'},{key:'research'}]},
  why_now:'Deux familles de sources convergent.',
  watch_next:['confirmation A','confirmation B'],contrary_signals:['normalisation'],falsification:'Le signal se normalise.'
};

assert.equal(E.probability(forecast),68);
assert.equal(E.historyDelta(forecast,24),11);
assert.ok(E.acceleration(forecast)>0);
assert.deepEqual(E.evidenceSources(forecast),{providers:2,families:2});
const report=E.report(forecast);
assert.equal(report.delta,11);
assert.ok(report.score>=60);
assert.ok(report.drivers.length>=2);
assert.equal(report.falsification,'Le signal se normalise.');
const analysis=E.analyze({generated_at:new Date().toISOString(),forecasts:[forecast,{...forecast,title:'Alternative',scenario_key:'alt',probability:{percent:44},probability_history:[],confidence:55}]});
assert.equal(analysis.reports.length,2);
assert.equal(analysis.clusters.length,1);
assert.equal(analysis.top_changes[0].title,'Test scenario');
console.log(JSON.stringify({ok:true,version:'1.17.0',score:report.score,level:report.level.label,delta:report.delta}));
