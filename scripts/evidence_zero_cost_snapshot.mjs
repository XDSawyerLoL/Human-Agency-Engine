import fs from 'node:fs/promises';
import path from 'node:path';
import { collectWorldSignals } from '../src/sources.js';
import { buildForecasts } from '../src/predictor.js';
import { config, providerState } from '../src/config.js';

const OUTPUT = process.env.EVIDENCE_OUTPUT ?? 'evidence-live.json';
const PREVIOUS_URL = process.env.EVIDENCE_PREVIOUS_URL ?? 'https://raw.githubusercontent.com/XDSawyerLoL/Human-Agency-Engine/evidence-live-data/evidence-live.json';
const HISTORY_LIMIT = 48;

async function loadPrevious() {
  try {
    const response = await fetch(`${PREVIOUS_URL}?t=${Date.now()}`, { headers: { accept: 'application/json' } });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

function attachCompactHistory(forecasts, previous, generatedAt) {
  const prior = new Map((previous?.forecasts ?? []).filter(x => x?.scenario_key).map(x => [x.scenario_key, x]));
  for (const forecast of forecasts) {
    const old = prior.get(forecast.scenario_key);
    const history = Array.isArray(old?.probability_history) ? [...old.probability_history] : [];
    if (old?.probability?.percent != null) {
      const last = history.at(-1);
      if (!last || last.percent !== old.probability.percent) {
        history.push({ at: previous?.generated_at ?? generatedAt, percent: old.probability.percent });
      }
    }
    history.push({ at: generatedAt, percent: forecast.probability.percent });
    forecast.probability_history = history.slice(-HISTORY_LIMIT);
    const previousPercent = old?.probability?.percent;
    if (Number.isFinite(previousPercent)) {
      const delta = forecast.probability.percent - previousPercent;
      forecast.probability_delta_points = delta;
      forecast.probability_direction = delta > 1 ? 'rising' : delta < -1 ? 'falling' : 'stable';
    } else {
      forecast.probability_direction = 'new';
    }
  }
}

async function main() {
  const generatedAt = new Date().toISOString();
  const previous = await loadPrevious();
  const collected = await collectWorldSignals();
  const forecasts = buildForecasts(collected.signals, config.maxForecasts);
  attachCompactHistory(forecasts, previous, generatedAt);

  const providers = new Set(forecasts.flatMap(f => f.consolidation?.source_providers ?? []).map(x => x.key));
  const families = new Set(forecasts.flatMap(f => f.consolidation?.source_families ?? []).map(x => x.key));

  const snapshot = {
    schema: 'evidence-zero-cost-live-v1',
    engine: 'evidence-node-predictive-public-v1',
    generated_at: generatedAt,
    runtime_mode: 'github-actions-stateless-node',
    status: 'live',
    summary: {
      signals_considered: collected.signals.length,
      predictions_returned: forecasts.length,
      source_families: families.size,
      source_providers: providers.size,
      active_source_providers: [...providers],
      source_status: collected.source_status,
      collection_duration_ms: collected.duration_ms,
      probability_history_enabled: true,
      numeric_model_estimates_enabled: true,
      duplicate_probability_inflation_prevented: true,
      public_french_localization_enabled: true,
      second_order_only: true,
      empirical_probability_calibration_enabled: false,
      storage_mode: 'single-compact-json',
      providers_configured: collected.providers_configured,
      provider_state: providerState(),
      zero_cost_runtime: true,
      rolling_database_artifacts: false
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

  await fs.mkdir(path.dirname(path.resolve(OUTPUT)), { recursive: true });
  await fs.writeFile(OUTPUT, JSON.stringify(snapshot, null, 2) + '\n', 'utf8');
  console.log(JSON.stringify({ event: 'snapshot_written', output: OUTPUT, signals: collected.signals.length, forecasts: forecasts.length, bytes: Buffer.byteLength(JSON.stringify(snapshot)) }));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
