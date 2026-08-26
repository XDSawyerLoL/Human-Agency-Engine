import { buildCalibrationReport } from '../src/calibration_engine.js';

const rows=[];
for(let i=0;i<20;i++) rows.push({scenario_key:`hi-${i}`,first_probability:.8,outcome:i<16?1:0,domain:i<10?'energy':'geopolitics_security',horizon_tier:'medium',resolution_kind:'binary_event',origin_group:'native'});
for(let i=0;i<20;i++) rows.push({scenario_key:`lo-${i}`,first_probability:.2,outcome:i<4?1:0,domain:i<10?'energy':'geopolitics_security',horizon_tier:'near',resolution_kind:'binary_event',origin_group:'memory'});
rows.push({scenario_key:'numeric-question',first_probability:.9,outcome:1,domain:'cyber_technology',horizon_tier:'deep',resolution_kind:'numeric'});

const report=buildCalibrationReport(rows,{minimumGlobal:30,minimumSegment:8});
if(report.scorable_resolutions!==40) throw new Error(`expected 40 scorable rows, got ${report.scorable_resolutions}`);
if(!report.calibration_ready) throw new Error('global calibration should be ready');
if(Math.abs(report.global.brier-.16)>.0001) throw new Error(`unexpected Brier: ${report.global.brier}`);
if(Math.abs(report.global.ece)>.0001) throw new Error(`expected ECE 0, got ${report.global.ece}`);
if(Math.abs(report.global.brier_skill_score-.36)>.0001) throw new Error(`unexpected skill score: ${report.global.brier_skill_score}`);
if(report.by_domain.length<2||!report.by_domain.every(x=>x.ready)) throw new Error('domain calibration segments not ready');
if(report.weights_applied_to_public_probability!==false) throw new Error('shadow weights must not alter public probability');
console.log(JSON.stringify({ok:true,brier:report.global.brier,ece:report.global.ece,skill:report.global.brier_skill_score,domains:report.by_domain.length}));
