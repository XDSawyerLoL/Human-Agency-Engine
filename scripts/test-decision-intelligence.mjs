import assert from 'node:assert/strict';
import { enrichForecastIntelligence, buildCycleSignalSummary, buildSnapshotAnalytics } from '../src/decision_intelligence.js';
import { attachShadowEnsemble, counterfactualSensitivity } from '../src/forecast_reasoning.js';

const now=new Date().toISOString();
const f={
  scenario_key:'test-v6',scenario_id:'test-v6',domain:'geopolitics_security',region:'Europe',horizon_tier:'near',horizon_order:1,
  title:'Escalade test',probability:{estimate:.62,percent:62,interval_percent:[49,73]},
  favorable_signals:['mouvement militaire','sanctions'],contrary_signals:['canal diplomatique'],probability_up_if:['nouvelle mobilisation'],probability_down_if:['accord vérifié'],
  evidence:[
    {title:'Source A',source_key:'a',source_label:'A',source_family:'official',source_trust:.94,observed_at:now,url:''},
    {title:'Source B',source_key:'b',source_label:'B',source_family:'media',source_trust:.70,observed_at:now,url:''}
  ],
  consolidation:{score:71,source_providers:[{key:'a',label:'A'},{key:'b',label:'B'}],source_families:[{key:'official'},{key:'media'}]}
};
enrichForecastIntelligence(f); attachShadowEnsemble(f);
assert.ok(f.confidence_breakdown.score>50);
assert.ok(f.impact_analysis.length>=3);
assert.ok(f.decision_brief.primary_action);
assert.equal(f.linked_signals.length,2);
assert.equal(f.shadow_ensemble.replaces_public_probability,false);
const cf=counterfactualSensitivity(f,[{label:'renforcement',direction:'up',strength:2}]);
assert.ok(cf.simulated_probability>cf.base_probability);

const cycle=buildCycleSignalSummary([
  {external_key:'1',source_key:'a',source_label:'A',event_type:'media_conflict_escalation',title:'x',geography:'France',observed_at:now},
  {external_key:'1',source_key:'a',source_label:'A',event_type:'media_conflict_escalation',title:'x duplicate',geography:'France',observed_at:now},
  {external_key:'2',source_key:'b',source_label:'B',event_type:'media_cyber_disruption',title:'y',geography:'Allemagne',observed_at:now}
],now);
assert.equal(cycle.count,2);
const snapshot={forecasts:[f],summary:{signals_considered:2,source_catalog:[],providers_configured:{metaculus_reference_only:true}}};
const analytics=buildSnapshotAnalytics(snapshot,{current_cycle_count:2,volume_7d:[{date:now.slice(0,10),count:2}],domain_distribution:cycle.domains,realtime_feed:cycle.feed});
assert.equal(analytics.kpis.active_forecasts,1);
assert.equal(analytics.kpis.signals_analyzed,2);
assert.ok(analytics.predictions_by_source.some(x=>x.label==='Metaculus'));
console.log('decision intelligence ok');