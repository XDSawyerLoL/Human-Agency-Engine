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
import { selectPublicForecasts } from './src/public_selection.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const store = new EvidenceStore();
let refreshing = null;
let lastError = null;

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

async function refreshWorld() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const generatedAt = new Date().toISOString();
    try {
      const [collected, breadth] = await Promise.all([collectWorldSignals(), collectBreadthSignals()]);
      collected.signals.push(...breadth.signals);
      collected.source_status.push(breadth.status);
      collected.duration_ms = Math.max(collected.duration_ms, breadth.status.duration_ms ?? 0);

      // Build a wide candidate pool first. The public selector then removes semantic duplicates
      // and enforces a balanced mix of domains/horizons instead of letting hazard feeds dominate.
      const coreCandidates = buildForecasts(collected.signals, Math.max(config.maxForecasts * 3, 96));
      const breadthCandidates = buildBreadthForecasts(breadth.signals);
      const forecasts = selectPublicForecasts([...coreCandidates, ...breadthCandidates], config.maxForecasts);

      await store.appendHistory(forecasts, generatedAt);
      await store.attachHistory(forecasts);
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
      const sourceProviders = new Set(forecasts.flatMap(f => f.consolidation.source_providers.map(s => s.key)));
      const sourceFamilies = new Set(forecasts.flatMap(f => f.consolidation.source_families.map(s => s.key)));
      const domainCounts = forecasts.reduce((acc, f) => {
        acc[f.domain] = (acc[f.domain] ?? 0) + 1;
        return acc;
      }, {});
      const horizonCounts = forecasts.reduce((acc, f) => {
        acc[f.horizon_tier] = (acc[f.horizon_tier] ?? 0) + 1;
        return acc;
      }, {});
      const snapshot = {
        schema: 'evidence-node-world-eye-v2-breadth',
        engine: 'evidence-node-predictive-public-v2-diverse',
        generated_at: generatedAt,
        runtime_mode: 'hostinger-node-managed',
        status: 'live',
        summary: {
          signals_considered: collected.signals.length,
          raw_candidate_forecasts: coreCandidates.length + breadthCandidates.length,
          predictions_returned: forecasts.length,
          source_families: sourceFamilies.size,
          source_providers: sourceProviders.size,
          active_source_providers: [...sourceProviders],
          source_status: collected.source_status,
          collection_duration_ms: collected.duration_ms,
          domain_distribution: domainCounts,
          horizon_distribution: horizonCounts,
          probability_history_enabled: true,
          numeric_model_estimates_enabled: true,
          duplicate_probability_inflation_prevented: true,
          public_semantic_dedup_enabled: true,
          environmental_public_cap_enabled: true,
          breadth_radar_enabled: true,
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
          falsification_required: true,
          expired_forecasts_must_resolve: true,
          duplicate_public_scenarios_allowed: false
        }
      };
      await store.saveSnapshot(snapshot);
      lastError = null;
      console.log(JSON.stringify({ event: 'world_refresh', signals: collected.signals.length, forecasts: forecasts.length, domains: domainCounts, horizons: horizonCounts, sources: collected.source_status }));
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

app.get('/api/snapshot', async (_req, res) => {
  res.set('Cache-Control', 'public, max-age=30, stale-while-revalidate=120');
  const snapshot = await store.getSnapshot();
  if (snapshot) return res.json(snapshot);
  const built = await refreshWorld();
  if (!built) return res.status(503).json({ status: 'warming', error: lastError?.message ?? 'initialisation' });
  res.json(built);
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
