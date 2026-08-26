import express from 'express';
import compression from 'compression';
import helmet from 'helmet';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config, providerState } from './src/config.js';
import { EvidenceStore } from './src/store.js';
import { collectWorldSignals } from './src/sources.js';
import { buildForecasts } from './src/predictor.js';

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
app.use(express.static(path.join(__dirname, 'public'), { maxAge: '5m', etag: true }));

async function refreshWorld() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const generatedAt = new Date().toISOString();
    try {
      const collected = await collectWorldSignals();
      const forecasts = buildForecasts(collected.signals, config.maxForecasts);
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
      const snapshot = {
        schema: 'evidence-node-world-eye-v1',
        engine: 'evidence-node-predictive-public-v1',
        generated_at: generatedAt,
        runtime_mode: 'hostinger-node-managed',
        status: 'live',
        summary: {
          signals_considered: collected.signals.length,
          predictions_returned: forecasts.length,
          source_families: sourceFamilies.size,
          source_providers: sourceProviders.size,
          active_source_providers: [...sourceProviders],
          source_status: collected.source_status,
          collection_duration_ms: collected.duration_ms,
          probability_history_enabled: true,
          numeric_model_estimates_enabled: true,
          duplicate_probability_inflation_prevented: true,
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
          expired_forecasts_must_resolve: true
        }
      };
      await store.saveSnapshot(snapshot);
      lastError = null;
      console.log(JSON.stringify({ event: 'world_refresh', signals: collected.signals.length, forecasts: forecasts.length, sources: collected.source_status }));
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

// Express 5 / path-to-regexp v8 wildcard syntax. This also matches the root path.
app.get('/{*path}', (_req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));

// Hostinger expects server-side Node Web Apps to be reachable on port 3000.
const server = app.listen(config.port, '0.0.0.0', () => {
  console.log(`[evidence] Node World Eye listening on 0.0.0.0:${config.port}; storage=${store.mode}`);
});

server.on('error', error => {
  console.error('[evidence] server error', error);
  process.exitCode = 1;
});

// Storage is optional. Never block the HTTP process while MySQL is being detected.
store.init().catch(error => console.error('[store-init]', error));
refreshWorld();
setInterval(refreshWorld, config.refreshMs).unref();
