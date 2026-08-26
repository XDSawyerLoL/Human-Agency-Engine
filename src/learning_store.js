import { buildCalibrationReport } from './calibration_engine.js';
import { resolutionContract } from './resolution_engine.js';

const memoryMeta = new Map();
const memoryResolution = new Map();
const json = value => JSON.stringify(value ?? null);
const parse = value => typeof value === 'string' ? JSON.parse(value) : value;

export async function initLearningStore(store) {
  if (!store?.pool) return {mode:'memory',persistent:false};
  await store.pool.query(`CREATE TABLE IF NOT EXISTS evidence_forecast_meta (
    scenario_key VARCHAR(96) PRIMARY KEY,
    payload JSON NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  await store.pool.query(`CREATE TABLE IF NOT EXISTS evidence_resolution_state (
    scenario_key VARCHAR(96) PRIMARY KEY,
    resolution_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    outcome TINYINT NULL,
    resolver VARCHAR(64) NULL,
    confidence DECIMAL(6,4) NULL,
    resolution_kind VARCHAR(32) NULL,
    evidence JSON NULL,
    note VARCHAR(1200) NULL,
    checked_at DATETIME(3) NOT NULL,
    resolved_at DATETIME(3) NULL,
    INDEX idx_resolution_status (resolution_status),
    INDEX idx_resolution_checked (checked_at)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`);
  return {mode:'mysql',persistent:true};
}

export async function recordForecastMetadata(store, forecasts = [], at = new Date().toISOString()) {
  for (const f of forecasts) {
    const payload = {
      forecast:{
        scenario_key:f.scenario_key,scenario_id:f.scenario_id,title:f.title||f.headline,summary:f.summary,
        domain:f.domain,horizon_tier:f.horizon_tier,region:f.region,target_date:f.target_date||f.time_window?.end_at,
        event_type:f.event_type,origin_group:f.origin_group,first_probability:Number(f.probability?.estimate??0),
        source_providers:f.consolidation?.source_providers||[],source_families:f.consolidation?.source_families||[],
        memory:f.memory||null
      },
      resolution_contract:resolutionContract(f),
      recorded_at:at
    };
    memoryMeta.set(f.scenario_key,payload);
  }
  if (!store?.pool || !forecasts.length) return;
  const values=forecasts.map(f=>[f.scenario_key,json(memoryMeta.get(f.scenario_key))]);
  await store.pool.query(`INSERT INTO evidence_forecast_meta (scenario_key,payload) VALUES ?
    ON DUPLICATE KEY UPDATE payload=VALUES(payload), updated_at=CURRENT_TIMESTAMP`,[values]);
}

export async function getDueResolutionRows(store,{limit=100,now=new Date()}={}) {
  if (store?.pool) {
    const [rows] = await store.pool.query(`SELECT r.scenario_key,r.scenario_id,r.title,r.domain,r.horizon_tier,r.first_seen,r.last_seen,r.target_at,
      r.first_probability,r.last_probability,r.status,r.resolved_at,r.outcome,m.payload,rs.resolution_status,rs.checked_at
      FROM evidence_forecast_registry r
      LEFT JOIN evidence_forecast_meta m ON m.scenario_key=r.scenario_key
      LEFT JOIN evidence_resolution_state rs ON rs.scenario_key=r.scenario_key
      WHERE r.target_at IS NOT NULL AND r.target_at <= ? AND r.status NOT IN ('resolved','invalidated')
      ORDER BY r.target_at ASC LIMIT ?`,[now,Number(limit)]);
    return rows.map(r=>({...r,meta:parse(r.payload)||{},target_at:r.target_at?new Date(r.target_at).toISOString():null}));
  }
  return [...(store?.registry?.values?.()||[])].filter(r=>r.target_at&&new Date(r.target_at)<=now&&!['resolved','invalidated'].includes(String(r.status))).slice(0,limit).map(r=>({...r,meta:memoryMeta.get(r.scenario_key)||{},resolution_status:memoryResolution.get(r.scenario_key)?.status||null}));
}

export async function saveResolutionAssessment(store, assessment) {
  if (!assessment?.scenario_key) return;
  const now = new Date();
  const current={...assessment,checked_at:now.toISOString(),resolved_at:(assessment.status==='auto_resolved'||assessment.status==='resolved')?now.toISOString():null};
  memoryResolution.set(assessment.scenario_key,current);
  if (assessment.status==='auto_resolved' && [0,1].includes(Number(assessment.outcome)) && store?.registry?.has?.(assessment.scenario_key)) {
    const old=store.registry.get(assessment.scenario_key);
    store.registry.set(assessment.scenario_key,{...old,status:'resolved',outcome:Number(assessment.outcome),resolved_at:now.toISOString()});
  }
  if (!store?.pool) return;
  await store.pool.query(`INSERT INTO evidence_resolution_state
    (scenario_key,resolution_status,outcome,resolver,confidence,resolution_kind,evidence,note,checked_at,resolved_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)
    ON DUPLICATE KEY UPDATE resolution_status=VALUES(resolution_status),outcome=VALUES(outcome),resolver=VALUES(resolver),confidence=VALUES(confidence),
      resolution_kind=VALUES(resolution_kind),evidence=VALUES(evidence),note=VALUES(note),checked_at=VALUES(checked_at),resolved_at=VALUES(resolved_at)`,[
    assessment.scenario_key,assessment.status,assessment.outcome,assessment.resolver||null,assessment.confidence??null,assessment.resolution_kind||null,
    json(assessment.evidence||[]),String(assessment.note||'').slice(0,1200),now,(assessment.status==='auto_resolved'||assessment.status==='resolved')?now:null
  ]);
  if (assessment.status==='auto_resolved' && [0,1].includes(Number(assessment.outcome))) {
    await store.pool.query(`UPDATE evidence_forecast_registry SET status='resolved',outcome=?,resolved_at=? WHERE scenario_key=?`,[Number(assessment.outcome),now,assessment.scenario_key]);
  }
}

async function assertScenarioExists(store,scenarioKey) {
  if(store?.pool){
    const [rows]=await store.pool.query('SELECT scenario_key FROM evidence_forecast_registry WHERE scenario_key=? LIMIT 1',[scenarioKey]);
    if(!rows.length) throw new Error('scenario_not_found');
    return;
  }
  if(!store?.registry?.has?.(scenarioKey)) throw new Error('scenario_not_found');
}

export async function resolveForecast(store,scenarioKey,{outcome,note='',evidence=[],resolver='manual_verified'}={}) {
  if (![0,1].includes(Number(outcome))) throw new Error('outcome must be 0 or 1');
  await assertScenarioExists(store,scenarioKey);
  const resolvedAt=new Date();
  const meta=memoryMeta.get(scenarioKey)||{};
  const assessment={scenario_key:scenarioKey,status:'resolved',outcome:Number(outcome),resolver,confidence:1,resolution_kind:meta?.resolution_contract?.kind||null,evidence,note};
  memoryResolution.set(scenarioKey,{...assessment,checked_at:resolvedAt.toISOString(),resolved_at:resolvedAt.toISOString()});
  if (store?.registry?.has?.(scenarioKey)) {
    const old=store.registry.get(scenarioKey); store.registry.set(scenarioKey,{...old,status:'resolved',outcome:Number(outcome),resolved_at:resolvedAt.toISOString()});
  }
  if (store?.pool) {
    await store.pool.query(`UPDATE evidence_forecast_registry SET status='resolved',outcome=?,resolved_at=? WHERE scenario_key=?`,[Number(outcome),resolvedAt,scenarioKey]);
    await store.pool.query(`INSERT INTO evidence_resolution_state
      (scenario_key,resolution_status,outcome,resolver,confidence,resolution_kind,evidence,note,checked_at,resolved_at)
      VALUES (?,'resolved',?,?,1,?,?,?, ?,?)
      ON DUPLICATE KEY UPDATE resolution_status='resolved',outcome=VALUES(outcome),resolver=VALUES(resolver),confidence=1,resolution_kind=VALUES(resolution_kind),evidence=VALUES(evidence),note=VALUES(note),checked_at=VALUES(checked_at),resolved_at=VALUES(resolved_at)`,
      [scenarioKey,Number(outcome),resolver,meta?.resolution_contract?.kind||null,json(evidence),String(note).slice(0,1200),resolvedAt,resolvedAt]);
  }
  return assessment;
}

async function resolvedRows(store) {
  if (store?.pool) {
    const [rows]=await store.pool.query(`SELECT r.scenario_key,r.title,r.domain,r.horizon_tier,r.first_probability,r.last_probability,r.outcome,r.resolved_at,m.payload
      FROM evidence_forecast_registry r LEFT JOIN evidence_forecast_meta m ON m.scenario_key=r.scenario_key
      WHERE r.status IN ('resolved','invalidated') AND r.outcome IN (0,1) ORDER BY r.resolved_at DESC`);
    return rows.map(r=>{
      const meta=parse(r.payload)||{};
      return {...r,meta,resolution_kind:meta?.resolution_contract?.kind,origin_group:meta?.forecast?.origin_group};
    });
  }
  return [...(store?.registry?.values?.()||[])].filter(r=>['resolved','invalidated'].includes(String(r.status))&&[0,1].includes(Number(r.outcome))).map(r=>{
    const meta=memoryMeta.get(r.scenario_key)||{};return{...r,meta,resolution_kind:meta?.resolution_contract?.kind,origin_group:meta?.forecast?.origin_group};
  });
}

export async function getLearningReport(store) {
  const rows=await resolvedRows(store);
  const calibration=buildCalibrationReport(rows);
  let resolutionStates=[]; let stateCounts={};
  if(store?.pool){
    const [states]=await store.pool.query(`SELECT scenario_key,resolution_status,outcome,resolver,confidence,resolution_kind,evidence,note,checked_at,resolved_at
      FROM evidence_resolution_state ORDER BY checked_at DESC LIMIT 100`);
    resolutionStates=states.map(r=>({...r,evidence:parse(r.evidence)||[],checked_at:r.checked_at?new Date(r.checked_at).toISOString():null,resolved_at:r.resolved_at?new Date(r.resolved_at).toISOString():null}));
    const [counts]=await store.pool.query('SELECT resolution_status,COUNT(*) AS n FROM evidence_resolution_state GROUP BY resolution_status');
    stateCounts=Object.fromEntries(counts.map(x=>[x.resolution_status,Number(x.n)]));
  } else {
    resolutionStates=[...memoryResolution.values()].slice(-100).reverse();
    stateCounts=resolutionStates.reduce((a,r)=>{a[r.status||r.resolution_status]=(a[r.status||r.resolution_status]||0)+1;return a;},{});
  }
  return {storage_mode:store?.mode||'memory',persistent:store?.mode==='mysql',calibration,resolution:{states:stateCounts,recent:resolutionStates.slice(0,30)}};
}

export async function storageReadiness(store) {
  return {
    mode:store?.mode||'memory',persistent:store?.mode==='mysql',mysql_connected:Boolean(store?.pool),
    learning_tables_ready:Boolean(store?.pool),
    accepted_configuration:['MYSQL_URL','DATABASE_URL(mysql://...)','MYSQL_HOST + MYSQL_PORT + MYSQL_USER + MYSQL_PASSWORD + MYSQL_DATABASE'],
    note:store?.pool?'Historique, résolutions et calibration sont persistants.':'Le moteur fonctionne, mais l’apprentissage historique sera perdu au redémarrage tant que MySQL n’est pas connecté.'
  };
}
