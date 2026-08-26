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
import { selectPublicForecasts } from './src/public_selection.js';
import { getWorldEye } from './src/world_eye.js';
import { moduleCatalog, runLabModule, collectResearchModuleCandidates } from './src/lab_modules.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const store = new EvidenceStore();
let refreshing = null;
let lastError = null;
const moduleRuns = new Map();

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
    { key:'polymarket-reference', label:'Polymarket', role:'Consensus de marché externe · hors calcul ÉVIDENCE', active:true, model_input:false },
    { key:'google-trends-reference', label:'Google Trends', role:'Attention collective · hors calcul seul', active:true, model_input:false },
    { key:'metaculus-reference', label:'Metaculus', role:'Référence externe · hors calcul de probabilité', active:Boolean(configured.metaculus_reference_only), model_input:false },
    { key:'point-reference', label:'Point', role:'Référence documentaire · hors calcul de probabilité', active:Boolean(configured.point_reference_only), model_input:false },
    { key:'windy-reference', label:'Windy', role:'Configuration présente · données test non utilisées en preuve', active:Boolean(configured.windy_configured_not_used_as_production_evidence), model_input:false }
  ];
}

async function refreshWorld() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const generatedAt = new Date().toISOString();
    try {
      const [collected, breadth, research] = await Promise.all([
        collectWorldSignals(),
        collectBreadthSignals(),
        collectResearchModuleCandidates()
      ]);
      collected.signals.push(...breadth.signals);
      collected.source_status.push(breadth.status, ...(research.statuses ?? []));
      collected.duration_ms = Math.max(collected.duration_ms, breadth.status.duration_ms ?? 0);

      // Large internal pool first; public selection removes duplicates and balances domains/horizons.
      const coreCandidates = buildForecasts(collected.signals, Math.max(config.maxForecasts * 3, 120));
      const breadthCandidates = buildBreadthForecasts(breadth.signals);
      const deepCandidates = buildDeepForecasts(collected.signals);
      const researchCandidates = research.forecasts ?? [];
      const allCandidates = [...coreCandidates, ...breadthCandidates, ...deepCandidates, ...researchCandidates];
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
      }
      const sourceProviders = new Set(forecasts.flatMap(f => (f.consolidation?.source_providers ?? []).map(s => s.key)));
      const sourceFamilies = new Set(forecasts.flatMap(f => (f.consolidation?.source_families ?? []).map(s => s.key)));
      const domainCounts = forecasts.reduce((acc, f) => {
        acc[f.domain] = (acc[f.domain] ?? 0) + 1;
        return acc;
      }, {});
      const horizonCounts = forecasts.reduce((acc, f) => {
        acc[f.horizon_tier] = (acc[f.horizon_tier] ?? 0) + 1;
        return acc;
      }, {});
      const catalog = sourceCatalog(collected, sourceProviders);
      const snapshot = {
        schema: 'evidence-node-world-eye-v5',
        engine: 'evidence-node-predictive-public-v5-lab',
        generated_at: generatedAt,
        runtime_mode: 'hostinger-node-managed',
        status: 'live',
        summary: {
          signals_considered: collected.signals.length,
          raw_candidate_forecasts: allCandidates.length,
          predictions_returned: forecasts.length,
          research_candidate_forecasts: researchCandidates.length,
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
          modular_lab_enabled: true,
          numeric_model_estimates_enabled: true,
          duplicate_probability_inflation_prevented: true,
          public_semantic_dedup_enabled: true,
          environmental_public_cap_enabled: true,
          breadth_radar_enabled: true,
          research_frontier_enabled: researchCandidates.length > 0,
          long_range_5_plus_enabled: deepCandidates.length > 0,
          public_french_localization_enabled: true,
          second_order_only: true,
          empirical_probability_calibration_enabled: false,
          storage_mode: store.mode,
          providers_configured: collected.providers_configured
        },
        forecasts,
        contract: {
          product_promise: 'Anticiper des conséquences plausibles avant qu’elles deviennent évidentes.',
          probability_is_certainty: false,
          consolidation_is_probability: false,
          current_event_is_not_forecast: true,
          external_consensus_is_model_probability: false,
          falsification_required: true,
          expired_forecasts_must_resolve: true,
          duplicate_public_scenarios_allowed: false,
          five_plus_year_scenarios_are_conditional: true
        }
      };
      await store.saveSnapshot(snapshot);
      lastError = null;
      console.log(JSON.stringify({ event: 'world_refresh', signals: collected.signals.length, forecasts: forecasts.length, candidates:allCandidates.length, domains: domainCounts, horizons: horizonCounts, sources: collected.source_status }));
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
  res.json({
    status: snapshot ? 'ok' : 'warming',
    service: 'evidence-world-eye-node',
    storage: store.mode,
    port: config.port,
    last_snapshot: snapshot?.generated_at ?? null,
    last_error: lastError,
    providers: providerState()
  });
});

app.get('/api/world-eye', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=900, stale-while-revalidate=3600');
  try {
    res.json(await getWorldEye());
  } catch (error) {
    res.status(503).json({ status:'unavailable', provider:'NASA DSCOVR / EPIC', error:String(error?.message || error) });
  }
});

app.get('/api/snapshot', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30, stale-while-revalidate=120');
  const snapshot = await store.getSnapshot();
  if (snapshot) return res.json(snapshot);
  const built = await refreshWorld();
  if (!built) return res.status(503).json({ status: 'warming', error: lastError?.message ?? 'initialisation' });
  res.json(built);
});

app.get('/api/modules', (_req, res) => {
  res.set('Cache-Control', 'public, max-age=60');
  res.json({ generated_at:new Date().toISOString(), modules:moduleCatalog() });
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
    res.status(502).json({ status:'error', module:key, error:String(error?.message || error).slice(0,240) });
  }
});

app.get('/api/track-record', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30');
  res.json(await store.getTrackRecord());
});

app.post('/api/refresh', async (req, res) => {
  if (!config.adminRefreshKey || req.get('x-evidence-admin-key') !== config.adminRefreshKey) return res.status(403).json({ error: 'forbidden' });
  const snapshot = await refreshWorld();
  res.json({ status: snapshot ? 'ok' : 'failed', generated_at: snapshot?.generated_at ?? null, error: lastError });
});

app.get('/{*path}', (_req, res) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const server = app.listen(config.port, '0.0.0.0', () => {
  console.log(`[evidence] Node World Eye listening on 0.0.0.0:${config.port}; storage=${store.mode}`);
});

server.on('error', error => {
  console.error('[evidence] server error', error);
  process.exitCode = 1;
});

store.init().catch(error => console.error('[store-init]', error));
refreshWorld();
setInterval(refreshWorld, config.refreshMs).unref();
