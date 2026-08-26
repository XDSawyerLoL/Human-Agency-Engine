import { buildResolutionAssessments, classifyResolutionKind } from '../src/resolution_engine.js';

if(classifyResolutionKind({title:'What will be the highest score on August 31?'})!=='open_question') throw new Error('open question classification failed');
if(classifyResolutionKind({title:'Un grand groupe annonce une baisse de 10 %'})!=='binary_event') throw new Error('binary classification failed');

const now=Date.parse('2026-08-26T12:00:00Z');
const rows=[
  {scenario_key:'machine',title:'Alerte test',target_at:'2026-08-25T00:00:00Z',meta:{resolution_contract:{kind:'binary_event',machine_rule:{type:'signal_event_type_present',event_type:'verified_event',minimum_matches:1}}}},
  {scenario_key:'suggest',title:'Incident naval majeur Chine',target_at:'2026-08-25T00:00:00Z',meta:{forecast:{summary:'incident naval Chine sécurité'},resolution_contract:{kind:'binary_event'}}},
  {scenario_key:'empty',title:'Événement sans preuve',target_at:'2026-08-25T00:00:00Z',meta:{resolution_contract:{kind:'binary_event'}}}
];
const signals=[
  {event_type:'verified_event',title:'Événement vérifié',source_key:'official-a',source_family:'official_primary',source_trust:.99,geography:'Monde'},
  {event_type:'media_conflict_escalation',title:'Incident naval majeur en Chine confirmé',source_key:'official-b',source_family:'official_multilateral',source_trust:.92,geography:'Chine'},
  {event_type:'media_conflict_escalation',title:'Incident naval Chine : nouvelles informations',source_key:'media-c',source_family:'global_media_aggregator',source_trust:.82,geography:'Chine'}
];
const out=buildResolutionAssessments(rows,signals,{now});
const machine=out.find(x=>x.scenario_key==='machine');
if(machine?.status!=='auto_resolved'||machine?.outcome!==1) throw new Error('machine rule did not auto-resolve');
const suggested=out.find(x=>x.scenario_key==='suggest');
if(!['suggested_positive','needs_review'].includes(suggested?.status)||suggested?.outcome!==null) throw new Error('text evidence must never become automatic outcome');
const empty=out.find(x=>x.scenario_key==='empty');
if(empty?.status!=='needs_review'||empty?.outcome!==null) throw new Error('absence of evidence must remain unresolved');
console.log(JSON.stringify({ok:true,statuses:Object.fromEntries(out.map(x=>[x.scenario_key,x.status]))}));
