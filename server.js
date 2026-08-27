import express from 'express';
import compression from 'compression';
import helmet from 'helmet';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config, providerState } from './src/config.js';
import { EvidenceStore } from './src/store.js';
import { collectWorldSignals } from './src/sources.js';
import { collectBreadthSignals } from './src/breadth_sources.js';
import { buildForecasts } from './src/predictor.js';
import { buildBreadthForecasts } from './src/breadth_predictor.js';
import { buildDeepForecasts } from './src/deep_predictor.js';
import { buildScenarioMemoryForecasts, scenarioMemoryStats } from './src/scenario_memory.js';
import { selectPublicForecasts } from './src/public_selection.js';
import { getWorldEye } from './src/world_eye.js';
import { moduleCatalog, runLabModule, collectResearchModuleCandidates } from './src/lab_modules.js';
import { enrichForecastIntelligence, buildCycleSignalSummary, buildSnapshotAnalytics } from './src/decision_intelligence.js';
import { attachShadowEnsemble, counterfactualSensitivity } from './src/forecast_reasoning.js';
import { attachAdaptiveEnsemble } from './src/adaptive_ensemble.js';
import { compileForecastQuestion } from './src/forecast_compiler.js';
import { buildCausalWorldModel, attachCausalContext, simulateCausalScenario } from './src/causal_world_model.js';
import { sportsCalibrationLab, benchmarkRoadmap } from './src/calibration_labs.js';
import { sportsCatalog, sportsLeagueIntelligence } from './src/sports_intelligence.js';
import { SupabaseBridge, mirrorV11State } from './src/supabase_bridge.js';
import { buildResolutionAssessments } from './src/resolution_engine.js';
import {
  initLearningStore,
  recordForecastMetadata,
  getDueResolutionRows,
  saveResolutionAssessment,
  resolveForecast,
  getLearningReport,
  storageReadiness
} from './src/learning_store.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const store = new EvidenceStore();
const supabase = new SupabaseBridge();
let refreshing = null;
let lastError = null;
let learningReady = false;
let persistedCausalLearning = null;
const moduleRuns = new Map();
const RESEARCH_DEADLINE_MS = 9_000;

app.disable('x-powered-by');
app.set('trust proxy', 1);
app.use(helmet({ contentSecurityPolicy: false, crossOriginResourcePolicy: { policy: 'cross-origin' } }));
app.use(compression());
app.use(express.json({ limit: '64kb' }));
app.use(express.static(path.join(__dirname, 'public'), {
  maxAge: 0,
  etag: true,
  setHeaders(res, filePath) {
    if (/\.(?:html|css|js)$/i.test(filePath)) {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
    }
  }
}));

function sourceCatalog(collected, activeKeys) {
  const configured = collected?.providers_configured || {};
  const active = key => activeKeys.has(key);
  return [
    { key:'usgs-earthquake-live', label:'USGS', role:'Observation officielle', active:active('usgs-earthquake-live'), model_input:true },
    { key:'noaa-swpc-kp-forecast', label:'NOAA SWPC', role:'Prévision officielle', active:active('noaa-swpc-kp-forecast'), model_input:true },
    { key:'nasa-eonet', label:'NASA EONET', role:'Agrégateur d’observations', active:active('nasa-eonet'), model_input:true },
    { key:'who-disease-outbreak-news', label:'OMS', role:'Source multilatérale officielle', active:active('who-disease-outbreak-news'), model_input:true },
    { key:'copernicus-cems-rapid-mapping', label:'Copernicus EMS', role:'Cartographie d’urgence officielle', active:active('copernicus-cems-rapid-mapping'), model_input:true },
    { key:'fred-macro-pulse', label:'FRED · Federal Reserve', role:'Statistiques officielles', active:active('fred-macro-pulse'), model_input:true },
    { key:'forecastapi', label:'ForecastAPI', role:'Projection statistique secondaire', active:active('forecastapi'), model_input:true },
    { key:'gdelt-doc-2', label:'GDELT', role:'Convergence médias mondiaux', active:active('gdelt-doc-2'), model_input:true },
    { key:'gdelt-breadth-radar', label:'GDELT · radar thématique', role:'Détection de signaux émergents', active:active('gdelt-breadth-radar'), model_input:true },
    { key:'pubmed-module', label:'PubMed', role:'Frontière scientifique biomédicale', active:active('pubmed-module'), model_input:true },
    { key:'arxiv-module', label:'arXiv', role:'Frontière scientifique et technologique', active:active('arxiv-module'), model_input:true },
    { key:'polymarket-reference', label:'Polymarket', role:'Consensus de marché externe', active:true, model_input:false },
    { key:'google-trends-reference', label:'Google Trends', role:'Attention collective', active:true, model_input:false },
    { key:'metaculus-reference', label:'Metaculus', role:'Benchmark / questions de forecasting', active:Boolean(configured.metaculus_reference_only), model_input:false },
    { key:'point-reference', label:'Point', role:'Référence documentaire', active:Boolean(configured.point_reference_only), model_input:false },
    { key:'windy-reference', label:'Windy', role:'Visualisation météo', active:Boolean(configured.windy_configured_not_used_as_production_evidence), model_input:false }
  ];
}

async function collectResearchWithDeadline() {
  let timer;
  try {
    return await Promise.race([
      collectResearchModuleCandidates(),
      new Promise(resolve => {
        timer = setTimeout(() => resolve({
          forecasts: [],
          statuses: [{ source:'research-frontier', ok:false, deferred:true, error:`deadline ${RESEARCH_DEADLINE_MS}ms; snapshot principal prioritaire` }]
        }), RESEARCH_DEADLINE_MS);
      })
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function runResolutionCycle(signals, generatedAt) {
  try {
    const due = await getDueResolutionRows(store, {limit:120, now:new Date(generatedAt)});
    const assessments = buildResolutionAssessments(due, signals, {now:Date.parse(generatedAt)});
    for (const assessment of assessments) await saveResolutionAssessment(store, assessment);
    return {due:due.length,assessed:assessments.length,auto_resolved:assessments.filter(x=>x.status==='auto_resolved').length};
  } catch (error) {
    console.error('[resolution-cycle]', error.message);
    return {due:0,assessed:0,auto_resolved:0,error:error.message};
  }
}

function effectiveCausalLearning(learning){
  const live=learning?.causal;
  if(Number(live?.resolved_forecasts||0)>0 || Number(live?.active_transitions||0)>0) return live;
  return persistedCausalLearning || live || null;
}

async function refreshWorld() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const generatedAt = new Date().toISOString();
    try {
      const [collected, breadth, research] = await Promise.all([
        collectWorldSignals(),
        collectBreadthSignals(),
        collectResearchWithDeadline()
      ]);
      collected.signals.push(...breadth.signals);
      collected.source_status.push(breadth.status, ...(research.statuses ?? []));
      collected.duration_ms = Math.max(collected.duration_ms, breadth.status.duration_ms ?? 0);

      const signalCycle = buildCycleSignalSummary(collected.signals, generatedAt);
      await store.recordSignalCycle(signalCycle);

      const resolutionCycle = await runResolutionCycle(collected.signals, generatedAt);
      const learning = await getLearningReport(store);
      const causalLearning = effectiveCausalLearning(learning);

      const coreCandidates = buildForecasts(collected.signals, Math.max(config.maxForecasts * 3, 160));
      const breadthCandidates = buildBreadthForecasts(breadth.signals);
      const deepCandidates = buildDeepForecasts(collected.signals);
      const researchCandidates = research.forecasts ?? [];
      const memoryCandidates = buildScenarioMemoryForecasts(collected.signals);
      const allCandidates = [...coreCandidates, ...breadthCandidates, ...deepCandidates, ...researchCandidates, ...memoryCandidates];
      const forecasts = selectPublicForecasts(allCandidates, config.maxForecasts);

      await store.appendHistory(forecasts, generatedAt);
      await store.attachHistory(forecasts);
      await store.recordForecastRegistry(forecasts, generatedAt);
      for (const f of forecasts) {
        const history = f.probability_history ?? [];
        if (history.length >= 2) {
          const prev = history.at(-2)?.percent ?? f.probability.percent;
          const delta = f.probability.percent - prev;
          f.probability_delta_points = delta;
          f.probability_direction = delta > 1 ? 'rising' : delta < -1 ? 'falling' : 'stable';
        } else {
          f.probability_direction = 'new';
        }
        enrichForecastIntelligence(f);
        attachShadowEnsemble(f);
        attachAdaptiveEnsemble(f, learning);
      }

      const causalWorld = buildCausalWorldModel(forecasts, causalLearning);
      attachCausalContext(forecasts, causalWorld);
      await recordForecastMetadata(store, forecasts, generatedAt);

      const memoryPublished = forecasts.filter(f => f?.memory?.recomputed).length;
      const livePublished = forecasts.length - memoryPublished;
      const memoryStats = scenarioMemoryStats();
      const sourceProviders = new Set(forecasts.flatMap(f => (f.consolidation?.source_providers ?? []).map(s => s.key)));
      const sourceFamilies = new Set(forecasts.flatMap(f => (f.consolidation?.source_families ?? []).map(s => s.key)));
      const domainCounts = forecasts.reduce((acc, f) => { acc[f.domain] = (acc[f.domain] ?? 0) + 1; return acc; }, {});
      const horizonCounts = forecasts.reduce((acc, f) => { acc[f.horizon_tier] = (acc[f.horizon_tier] ?? 0) + 1; return acc; }, {});
      const catalog = sourceCatalog(collected, sourceProviders);
      const signalAnalytics = await store.getSignalAnalytics();
      const snapshot = {
        schema: 'evidence-node-world-eye-v11',
        engine: 'evidence-node-predictive-public-v11-providence-learning-os',
        generated_at: generatedAt,
        runtime_mode: 'hostinger-node-managed',
        status: 'live',
        summary: {
          signals_considered: collected.signals.length,
          raw_candidate_forecasts: allCandidates.length,
          predictions_returned: forecasts.length,
          live_discovery_forecasts_returned: livePublished,
          scenario_memory_forecasts_returned: memoryPublished,
          scenario_memory_candidates: memoryCandidates.length,
          scenario_memory_stats: memoryStats,
          research_candidate_forecasts: researchCandidates.length,
          research_deadline_ms: RESEARCH_DEADLINE_MS,
          source_families: sourceFamilies.size,
          source_providers: sourceProviders.size,
          active_source_providers: [...sourceProviders],
          source_catalog: catalog,
          source_status: collected.source_status,
          collection_duration_ms: collected.duration_ms,
          domain_distribution: domainCounts,
          horizon_distribution: horizonCounts,
          probability_history_enabled: true,
          forecast_registry_enabled: true,
          signal_ledger_7d_enabled: true,
          modular_lab_enabled: true,
          all_modules_actionable_enabled: true,
          scenario_memory_enabled: true,
          impact_analysis_enabled: true,
          confidence_breakdown_enabled: true,
          decision_layer_enabled: true,
          counterfactual_sensitivity_enabled: true,
          shadow_ensemble_enabled: true,
          adaptive_ensemble_enabled: true,
          adaptive_ensemble_learning_resolutions: learning.ensemble.live_backtest.n,
          adaptive_ensemble_promotion_ready: learning.ensemble.promotion_ready,
          forecast_compiler_enabled: true,
          causal_world_model_enabled: true,
          causal_learning_enabled: true,
          causal_learning_resolutions: Number(causalLearning?.resolved_forecasts||0),
          causal_learning_active_transitions: Number(causalLearning?.active_transitions||0),
          causal_world_nodes: causalWorld.metrics.nodes,
          causal_world_edges: causalWorld.metrics.edges,
          causal_world_evidence_edges: causalWorld.metrics.evidence_backed_edges,
          causal_world_learned_edges: causalWorld.metrics.learned_structural_edges,
          scenario_lab_enabled: true,
          sports_intelligence_enabled: true,
          sports_calibration_lab_enabled: true,
          supabase_mirror_configured: supabase.enabled,
          resolution_engine_enabled: true,
          resolution_due: resolutionCycle.due,
          resolution_assessed: resolutionCycle.assessed,
          resolution_auto_resolved: resolutionCycle.auto_resolved,
          calibration_engine_enabled: true,
          calibration_scorable_resolutions: learning.calibration.scorable_resolutions,
          empirical_probability_calibration_enabled: learning.calibration.calibration_ready,
          persistent_learning_enabled: learning.persistent,
          numeric_model_estimates_enabled: true,
          duplicate_probability_inflation_prevented: true,
          public_semantic_dedup_enabled: true,
          environmental_public_cap_enabled: true,
          breadth_radar_enabled: true,
          research_frontier_enabled: researchCandidates.length > 0,
          long_range_5_plus_enabled: deepCandidates.length > 0 || memoryCandidates.some(f => f.horizon_tier === 'deep'),
          public_french_localization_enabled: true,
          second_order_only: true,
          storage_mode: store.mode,
          providers_configured: collected.providers_configured
        },
        learning: {
          persistent: learning.persistent,
          calibration_ready: learning.calibration.calibration_ready,
          scorable_resolutions: learning.calibration.scorable_resolutions,
          brier_score: learning.calibration.global.brier,
          log_loss: learning.calibration.global.log_loss,
          ece: learning.calibration.global.ece,
          adaptive_ensemble_status: learning.ensemble.status,
          adaptive_ensemble_live_backtest: learning.ensemble.live_backtest,
          adaptive_ensemble_promotion_ready: learning.ensemble.promotion_ready,
          causal_learning: causalLearning,
          resolution_states: learning.resolution.states
        },
        causal_world: causalWorld,
        forecasts,
        contract: {
          product_promise: 'Anticiper des conséquences plausibles, mesurer leur impact, apprendre des résolutions, relier leurs mécanismes, tester des hypothèses puis vérifier objectivement la prévision.',
          probability_is_certainty: false,
          consolidation_is_probability: false,
          confidence_is_probability: false,
          current_event_is_not_forecast: true,
          external_consensus_is_model_probability: false,
          scenario_memory_is_recomputed_by_horizon: true,
          decision_brief_is_automatic_order: false,
          shadow_ensemble_is_public_probability: false,
          adaptive_ensemble_is_public_probability: false,
          adaptive_ensemble_requires_live_track_record: true,
          forecast_compiler_can_invent_probability: false,
          causal_graph_is_causal_proof: false,
          causal_learning_proves_intervention_effect: false,
          structural_priors_are_observed_facts: false,
          scenario_lab_replaces_public_probability: false,
          sports_prediction_is_betting_advice: false,
          falsification_required: true,
          expired_forecasts_must_resolve: true,
          ambiguous_forecasts_auto_scored: false,
          binary_scores_use_first_published_probability: true,
          duplicate_public_scenarios_allowed: false,
          five_plus_year_scenarios_are_conditional: true
        }
      };
      snapshot.analytics = buildSnapshotAnalytics(snapshot, signalAnalytics);
      await store.saveSnapshot(snapshot);
      persistedCausalLearning = causalLearning || persistedCausalLearning;
      void mirrorV11State(supabase,{snapshot,causalLearning}).catch(error=>console.error('[supabase-mirror]',error.message));
      lastError = null;
      console.log(JSON.stringify({ event:'world_refresh', signals:collected.signals.length, forecasts:forecasts.length, live:livePublished, memory:memoryPublished, candidates:allCandidates.length, resolution:resolutionCycle, calibration_n:learning.calibration.scorable_resolutions, ensemble_n:learning.ensemble.live_backtest.n, causal_learning_n:Number(causalLearning?.resolved_forecasts||0), causal_nodes:causalWorld.metrics.nodes, causal_edges:causalWorld.metrics.edges, domains:domainCounts, horizons:horizonCounts, sources:collected.source_status }));
      return snapshot;
    } catch (error) {
      lastError = { at: new Date().toISOString(), message: error.message };
      console.error('[world-refresh]', error);
      return await store.getSnapshot();
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

app.get('/api/health', async (_req, res) => {
  const snapshot = await store.getSnapshot();
  const storage = await storageReadiness(store);
  res.json({
    status: snapshot ? 'ok' : 'warming',
    service: 'evidence-world-eye-node',
    version:'v11',
    storage: store.mode,
    learning_ready: learningReady,
    persistent_learning: storage.persistent,
    supabase_mirror_configured:supabase.enabled,
    causal_world_ready:Boolean(snapshot?.causal_world?.nodes?.length),
    causal_learning_ready:Boolean(snapshot?.learning?.causal_learning),
    sports_intelligence_ready:true,
    port: config.port,
    last_snapshot: snapshot?.generated_at ?? null,
    last_error: lastError,
    scenario_memory: scenarioMemoryStats(),
    providers: providerState()
  });
});

app.get('/api/world-eye', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=900, stale-while-revalidate=3600');
  try { res.json(await getWorldEye()); }
  catch (error) { res.status(503).json({ status:'unavailable', provider:'NASA DSCOVR / EPIC', error:String(error?.message || error) }); }
});

app.get('/api/snapshot', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30, stale-while-revalidate=120');
  const snapshot = await store.getSnapshot();
  if (snapshot) return res.json(snapshot);
  const built = await refreshWorld();
  if (!built) return res.status(503).json({ status:'warming', error:lastError?.message ?? 'initialisation' });
  res.json(built);
});

app.get('/api/analytics', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30');
  const snapshot = await store.getSnapshot() || await refreshWorld();
  if (!snapshot) return res.status(503).json({status:'warming'});
  const signalAnalytics = await store.getSignalAnalytics();
  res.json({ generated_at:new Date().toISOString(), ...buildSnapshotAnalytics(snapshot, signalAnalytics) });
});

app.get('/api/modules', (_req, res) => {
  res.set('Cache-Control', 'public, max-age=60');
  res.json({ generated_at:new Date().toISOString(), modules:moduleCatalog().filter(m => m.key !== 'future-engine') });
});

app.post('/api/modules/:key/run', async (req, res) => {
  const key = String(req.params.key || '').toLowerCase();
  const client = String(req.ip || req.socket?.remoteAddress || 'anonymous');
  const rateKey = `${client}:${key}`;
  const previous = moduleRuns.get(rateKey) || 0;
  if (Date.now() - previous < 4000) return res.status(429).json({ error:'module_too_fast', retry_after_seconds:4 });
  moduleRuns.set(rateKey, Date.now());
  try {
    const result = await runLabModule(key, { theme:String(req.body?.theme || '') });
    res.json({ status:'ok', generated_at:new Date().toISOString(), ...result });
  } catch (error) {
    res.json({status:'degraded', module:key, key, label:key.toUpperCase(), items:[], forecasts:[],generated_at:new Date().toISOString(),notice:`La source distante est momentanément indisponible (${String(error?.message || error).slice(0,160)}). Le module reste actif et sera retenté.`});
  }
});

app.get('/api/track-record', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30');
  const [legacy, learning] = await Promise.all([store.getTrackRecord(), getLearningReport(store)]);
  const global = learning.calibration.global;
  res.json({...legacy,calibration_ready:learning.calibration.calibration_ready,empirical_calibration_enabled:learning.calibration.calibration_ready,brier_score:global.brier,log_loss:global.log_loss,hit_rate:global.hit_rate===null?null:Math.round(global.hit_rate*1000)/10,calibration:learning.calibration,ensemble:learning.ensemble,causal_learning:effectiveCausalLearning(learning),resolution:learning.resolution,persistent_learning:learning.persistent});
});

app.get('/api/calibration', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30');
  const learning = await getLearningReport(store);
  res.json(learning.calibration);
});

app.get('/api/ensemble', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30');
  const learning = await getLearningReport(store);
  res.json({generated_at:new Date().toISOString(),...learning.ensemble});
});

app.get('/api/causal-learning', async (_req,res)=>{
  res.set('Cache-Control','public, max-age=30');
  const learning=await getLearningReport(store);
  res.json(effectiveCausalLearning(learning)||{schema:'evidence-causal-learning-v1',status:'collecting',resolved_forecasts:0,active_transitions:0});
});

app.get('/api/causal-graph', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30, stale-while-revalidate=120');
  const snapshot=await store.getSnapshot() || await refreshWorld();
  if(!snapshot) return res.status(503).json({status:'warming'});
  const graph=snapshot.causal_world || buildCausalWorldModel(snapshot.forecasts||[],snapshot.learning?.causal_learning||persistedCausalLearning);
  res.json(graph);
});

app.post('/api/scenario-lab', async (req, res) => {
  try {
    const snapshot=await store.getSnapshot() || await refreshWorld();
    if(!snapshot) return res.status(503).json({status:'warming'});
    const graph=snapshot.causal_world || buildCausalWorldModel(snapshot.forecasts||[],snapshot.learning?.causal_learning||persistedCausalLearning);
    res.json(simulateCausalScenario(graph,snapshot.forecasts||[],req.body?.interventions||[],{max_hops:req.body?.max_hops}));
  } catch(error) {
    const message=String(error?.message||error);
    const clientError=['intervention_required','causal_graph_unavailable'].includes(message);
    res.status(clientError?400:500).json({status:'error',error:message});
  }
});

app.get('/api/sports/catalog',async(_req,res)=>{
  res.set('Cache-Control','public, max-age=21600, stale-while-revalidate=86400');
  try{res.json(await sportsCatalog());}catch(error){res.status(502).json({status:'error',error:String(error?.message||error)});}
});

app.get('/api/sports/league',async(req,res)=>{
  res.set('Cache-Control','public, max-age=1800, stale-while-revalidate=7200');
  try{
    const result=await sportsLeagueIntelligence({country:String(req.query.country||''),league:String(req.query.league||''),competitionId:req.query.competition_id,seasonId:req.query.season_id});
    void mirrorV11State(supabase,{sports:result}).catch(error=>console.error('[supabase-sports]',error.message));
    res.json(result);
  }catch(error){res.status(502).json({status:'error',error:String(error?.message||error)});}
});

app.get('/api/resolutions', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30');
  const [queue, learning] = await Promise.all([getDueResolutionRows(store,{limit:100}),getLearningReport(store)]);
  res.json({generated_at:new Date().toISOString(),queue:queue.map(r=>({scenario_key:r.scenario_key,title:r.title,domain:r.domain,horizon_tier:r.horizon_tier,target_at:r.target_at,first_probability:Number(r.first_probability),last_probability:Number(r.last_probability),resolution_status:r.resolution_status||'pending',contract:r.meta?.resolution_contract||null})),states:learning.resolution.states,recent:learning.resolution.recent});
});

app.post('/api/resolutions/:scenarioKey', async (req, res) => {
  if (!config.adminRefreshKey || req.get('x-evidence-admin-key') !== config.adminRefreshKey) return res.status(403).json({error:'forbidden'});
  try {
    const result = await resolveForecast(store,String(req.params.scenarioKey),{outcome:Number(req.body?.outcome),note:String(req.body?.note||''),evidence:Array.isArray(req.body?.evidence)?req.body.evidence.slice(0,20):[],resolver:'manual_verified'});
    const learning = await getLearningReport(store);
    res.json({status:'ok',resolution:result,calibration:learning.calibration,ensemble:learning.ensemble,causal_learning:learning.causal});
  } catch (error) {res.status(400).json({status:'error',error:String(error?.message||error)});}
});

app.get('/api/storage', async (_req, res) => {
  res.set('Cache-Control', 'no-store');
  const base=await storageReadiness(store);const sb=await supabase.health();
  res.json({...base,supabase:sb,durable_snapshot_available:sb.connected});
});

app.get('/api/supabase',async(_req,res)=>{res.set('Cache-Control','no-store');res.json(await supabase.health());});

app.get('/api/calibration/sports', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=21600, stale-while-revalidate=86400');
  try { res.json(await sportsCalibrationLab()); }
  catch(error){ res.status(502).json({status:'error',error:String(error?.message||error)}); }
});

app.get('/api/benchmarks', (_req, res) => {
  res.set('Cache-Control', 'public, max-age=300');
  res.json({generated_at:new Date().toISOString(),...benchmarkRoadmap()});
});

app.post('/api/counterfactual/:scenarioKey', async (req, res) => {
  const snapshot = await store.getSnapshot() || await refreshWorld();
  const f = snapshot?.forecasts?.find(x => String(x.scenario_key) === String(req.params.scenarioKey));
  if (!f) return res.status(404).json({error:'scenario_not_found'});
  res.json(counterfactualSensitivity(f, req.body?.changes || []));
});

app.post('/api/forecast/compile', async (req, res) => {
  try {
    const snapshot=await store.getSnapshot() || await refreshWorld();
    if(!snapshot) return res.status(503).json({status:'warming'});
    res.json(compileForecastQuestion(String(req.body?.question||''),snapshot));
  } catch(error) {
    const message=String(error?.message||error);
    const clientError=['question_too_short','invalid_now'].includes(message);
    res.status(clientError?400:500).json({status:'error',error:message});
  }
});

app.post('/api/refresh', async (req, res) => {
  if (!config.adminRefreshKey || req.get('x-evidence-admin-key') !== config.adminRefreshKey) return res.status(403).json({ error:'forbidden' });
  const snapshot = await refreshWorld();
  res.json({ status:snapshot ? 'ok':'failed', generated_at:snapshot?.generated_at ?? null, error:lastError });
});

app.get('/{*path}', (_req, res) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const server = app.listen(config.port, '0.0.0.0', () => {
  console.log(`[evidence] Providence V11 listening on 0.0.0.0:${config.port}; storage=${store.mode}; supabase=${supabase.enabled?'configured':'off'}`);
});

server.on('error', error => {
  console.error('[evidence] server error', error);
  process.exitCode = 1;
});

async function boot() {
  try {
    await store.init();
    await initLearningStore(store);
    if(supabase.enabled){
      try{
        const [savedSnapshot,savedCausal]=await Promise.all([supabase.readState('latest_snapshot'),supabase.readState('causal_learning')]);
        if(!store.snapshot&&savedSnapshot?.payload)store.snapshot=savedSnapshot.payload;
        if(savedCausal?.payload)persistedCausalLearning=savedCausal.payload;
      }catch(error){console.error('[supabase-restore]',String(error?.message||error));}
    }
    learningReady = true;
  } catch (error) {
    console.error('[learning-init]', error.message);
    learningReady = false;
  }
  await refreshWorld();
  setInterval(refreshWorld, config.refreshMs).unref();
}

boot().catch(error => {
  lastError = {at:new Date().toISOString(),message:error.message};
  console.error('[boot]', error);
});