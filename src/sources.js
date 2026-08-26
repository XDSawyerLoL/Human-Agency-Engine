import { config } from './config.js';

const UA = 'Evidence-World-Eye/1.0 (+public predictive intelligence)';
const HOUR = 3600_000;
const DAY = 24 * HOUR;
const forecastMemo = new Map();

const ENDPOINTS = {
  usgs: 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson',
  noaa: 'https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json',
  eonet: 'https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=14&limit=100',
  who: 'https://www.who.int/api/hubs/diseaseoutbreaknews?$top=30&$orderby=PublicationDate%20desc',
  copernicus: 'https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/',
  fred: 'https://api.stlouisfed.org/fred/series/observations',
  forecast: 'https://forecastapi.com/v2/forecast',
  gdelt: 'https://api.gdeltproject.org/api/v2/doc/doc'
};

const SOURCE_META = {
  usgs: { key: 'usgs-earthquake-live', label: 'USGS', family: 'official_primary', trust: 0.98 },
  noaa: { key: 'noaa-swpc-kp-forecast', label: 'NOAA SWPC', family: 'model_forecast', trust: 0.90 },
  eonet: { key: 'nasa-eonet', label: 'NASA EONET', family: 'official_aggregator', trust: 0.88 },
  who: { key: 'who-disease-outbreak-news', label: 'Organisation mondiale de la Santé', family: 'official_multilateral', trust: 0.96 },
  copernicus: { key: 'copernicus-cems-rapid-mapping', label: 'Copernicus EMS', family: 'official_multilateral', trust: 0.95 },
  fred: { key: 'fred-macro-pulse', label: 'FRED · Federal Reserve', family: 'official_statistical', trust: 0.95 },
  forecast: { key: 'forecastapi', label: 'ForecastAPI', family: 'statistical_model', trust: 0.78 },
  gdelt: { key: 'gdelt-doc-2', label: 'GDELT', family: 'global_media_aggregator', trust: 0.66 }
};

const EONET_TYPES = {
  wildfires: 'wildfire_emergency', severeStorms: 'severe_storm_emergency', volcanoes: 'volcanic_emergency',
  floods: 'flood_emergency', drought: 'drought_emergency', landslides: 'landslide_emergency',
  seaLakeIce: 'cryosphere_disruption', dustHaze: 'air_quality_hazard', snow: 'severe_winter_hazard',
  tempExtremes: 'temperature_extreme', waterColor: 'water_quality_anomaly'
};

const FRED_SERIES = {
  VIXCLS: { type: 'financial_stress', label: 'volatilité financière', frequency: 'D' },
  BAMLH0A0HYM2: { type: 'credit_stress', label: 'tension du crédit à haut rendement', frequency: 'D' },
  DCOILWTICO: { type: 'energy_price_spike', label: 'pétrole WTI', frequency: 'D' },
  ICSA: { type: 'labor_market_softening', label: 'inscriptions au chômage américain', frequency: 'W' }
};

const GDELT_QUERIES = [
  { type: 'media_supply_chain_signal', query: '("port closure" OR "shipping disruption" OR "supply disruption")', label: 'tensions logistiques mondiales' },
  { type: 'media_civil_disruption', query: '("general strike" OR "mass protest" OR "transport strike")', label: 'mobilisations et grèves à fort impact' },
  { type: 'media_geopolitical_trade', query: '("export ban" OR sanctions OR "trade restriction")', label: 'restrictions commerciales et sanctions' },
  { type: 'media_financial_stress', query: '("bank run" OR "liquidity crisis" OR "bank stress")', label: 'stress bancaire et liquidité' }
];

const safeDate = v => {
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
};

const text = v => String(v ?? '').replace(/\s+/g, ' ').trim();

async function fetchJson(url, options = {}, timeoutMs = 18_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: { 'user-agent': UA, accept: 'application/json', ...(options.headers ?? {}) }
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function signal(meta, data) {
  return {
    source_key: meta.key,
    source_label: meta.label,
    source_family: meta.family,
    source_trust: meta.trust,
    observed_at: new Date().toISOString(),
    ...data
  };
}

async function usgs() {
  const payload = await fetchJson(ENDPOINTS.usgs);
  const now = Date.now();
  return (payload.features ?? []).flatMap(feature => {
    const p = feature?.properties ?? {};
    const mag = Number(p.mag);
    const at = Number(p.time);
    if (!Number.isFinite(mag) || mag < 5.5 || !Number.isFinite(at) || now - at > 36 * HOUR) return [];
    const place = text(p.place) || 'zone non précisée';
    return [signal(SOURCE_META.usgs, {
      external_key: `usgs:${feature.id}`,
      event_type: 'major_earthquake',
      title: `Séisme M${mag.toFixed(1)} — ${place}`,
      geography: place,
      event_at: new Date(at).toISOString(),
      severity: Math.min(1, 0.45 + (mag - 5.5) * 0.16 + (Number(p.tsunami) ? 0.12 : 0)),
      url: p.url || '',
      facts: { magnitude: mag, tsunami: Number(p.tsunami) || 0, significance: Number(p.sig) || 0 }
    })];
  });
}

async function noaa() {
  const payload = await fetchJson(ENDPOINTS.noaa);
  if (!Array.isArray(payload) || payload.length < 2) return [];
  const headers = Array.isArray(payload[0]) ? payload[0].map(String) : null;
  const rows = headers ? payload.slice(1).map(r => Object.fromEntries(headers.map((h, i) => [h, r[i]]))) : payload;
  const now = Date.now();
  const future = rows.map(r => {
    const at = safeDate(r.time_tag);
    const kp = Number(r.kp);
    const observed = text(r.observed).toLowerCase();
    return { at, kp, observed };
  }).filter(r => r.at && r.at.getTime() >= now - HOUR && Number.isFinite(r.kp) && !['observed', 'estimated'].includes(r.observed));
  if (!future.length) return [];
  const peak = future.reduce((a, b) => b.kp > a.kp ? b : a);
  if (peak.kp < 5) return [];
  return [signal(SOURCE_META.noaa, {
    external_key: `noaa-kp:${peak.at.toISOString().slice(0, 13)}:${peak.kp}`,
    event_type: 'geomagnetic_storm_watch',
    title: `Pic géomagnétique Kp ${peak.kp.toFixed(1)} prévu par NOAA`,
    geography: 'Monde',
    event_at: peak.at.toISOString(),
    severity: Math.min(1, (peak.kp - 3) / 6),
    url: ENDPOINTS.noaa,
    facts: { peak_kp: peak.kp, forecast_at: peak.at.toISOString(), official_model_forecast: true }
  })];
}

async function eonet() {
  const payload = await fetchJson(ENDPOINTS.eonet);
  const events = Array.isArray(payload.events) ? payload.events : [];
  return events.flatMap(item => {
    const categories = (item.categories ?? []).map(x => x?.id).filter(Boolean);
    const type = categories.map(c => EONET_TYPES[c]).find(Boolean) || 'natural_hazard_event';
    const geo = Array.isArray(item.geometry) && item.geometry.length ? item.geometry[item.geometry.length - 1] : null;
    const at = safeDate(geo?.date) ?? new Date();
    const title = text(item.title);
    if (!title) return [];
    const ageDays = Math.max(0, (Date.now() - at.getTime()) / DAY);
    const severity = Math.max(0.35, Math.min(0.82, 0.72 - ageDays * 0.02));
    return [signal(SOURCE_META.eonet, {
      external_key: `eonet:${item.id}`,
      event_type: type,
      title,
      geography: title,
      event_at: at.toISOString(),
      severity,
      url: item.link || item.sources?.[0]?.url || ENDPOINTS.eonet,
      facts: { eonet_id: item.id, categories, coordinates: geo?.coordinates ?? null, open_event: !item.closed }
    })];
  });
}

async function who() {
  const payload = await fetchJson(ENDPOINTS.who);
  const rows = payload?.value ?? payload?.Items ?? payload?.items ?? payload?.results ?? (Array.isArray(payload) ? payload : []);
  if (!Array.isArray(rows)) return [];
  const cutoff = Date.now() - 21 * DAY;
  return rows.flatMap(item => {
    const at = safeDate(item.PublicationDate ?? item.PublicationDateAndTime);
    if (!at || at.getTime() < cutoff) return [];
    const title = text(item.Title ?? item.OverrideTitle ?? item.UrlName);
    if (!title) return [];
    const geography = text(item.regionscountries ?? item.TitleSuffix ?? item.Summary).slice(0, 180) || 'Monde';
    let url = text(item.ItemDefaultUrl);
    if (url.startsWith('/')) url = `https://www.who.int${url}`;
    return [signal(SOURCE_META.who, {
      external_key: `who:${item.Id ?? item.UrlName ?? title}:${at.toISOString().slice(0,10)}`,
      event_type: 'disease_outbreak_signal',
      title,
      geography,
      event_at: at.toISOString(),
      severity: 0.63,
      url: url || 'https://www.who.int/emergencies/disease-outbreak-news',
      facts: { official_outbreak_report: true, summary: text(item.Summary ?? item.Overview ?? item.Assessment).slice(0, 600) }
    })];
  });
}

function classifyCopernicus(item) {
  const hay = `${item?.name ?? ''} ${item?.title ?? ''} ${item?.eventType ?? ''} ${item?.type ?? ''}`.toLowerCase();
  if (hay.includes('flood')) return 'flood_emergency';
  if (hay.includes('wildfire') || hay.includes('fire')) return 'wildfire_emergency';
  if (hay.includes('earthquake')) return 'major_earthquake';
  if (hay.includes('volcan')) return 'volcanic_emergency';
  if (hay.includes('storm') || hay.includes('cyclone') || hay.includes('hurricane')) return 'severe_storm_emergency';
  if (hay.includes('drought')) return 'drought_emergency';
  return 'copernicus_emergency_activation';
}

async function copernicus() {
  const payload = await fetchJson(ENDPOINTS.copernicus);
  const rows = Array.isArray(payload) ? payload : payload?.results ?? payload?.activations ?? payload?.items ?? [];
  if (!Array.isArray(rows)) return [];
  const cutoff = Date.now() - 14 * DAY;
  return rows.slice(0, 80).flatMap(item => {
    const at = safeDate(item.activationTime ?? item.activationDate ?? item.createdAt ?? item.date ?? item.eventTime);
    if (at && at.getTime() < cutoff) return [];
    const title = text(item.name ?? item.title ?? item.eventName ?? item.activationCode);
    if (!title) return [];
    const geography = text(item.country ?? item.location ?? item.aoIName ?? item.aoi ?? item.region) || title;
    return [signal(SOURCE_META.copernicus, {
      external_key: `cems:${item.id ?? item.activationCode ?? title}`,
      event_type: classifyCopernicus(item),
      title,
      geography,
      event_at: (at ?? new Date()).toISOString(),
      severity: 0.72,
      url: item.url ?? item.link ?? 'https://rapidmapping.emergency.copernicus.eu/',
      facts: { activation_code: item.activationCode ?? null, official_activation: true }
    })];
  });
}

function fredTrigger(id, values) {
  const latest = values[0]?.value;
  const older = values[Math.min(5, values.length - 1)]?.value;
  if (!Number.isFinite(latest) || !Number.isFinite(older)) return { triggered: false, severity: 0 };
  if (id === 'VIXCLS') return { triggered: latest >= 25 || latest - older >= 7, severity: Math.min(1, Math.max(0.35, (latest - 18) / 25)) };
  if (id === 'BAMLH0A0HYM2') return { triggered: latest >= 4.5 || latest - older >= 0.75, severity: Math.min(1, Math.max(0.35, (latest - 3) / 4)) };
  if (id === 'DCOILWTICO') {
    const change = older > 0 ? latest / older - 1 : 0;
    return { triggered: Math.abs(change) >= 0.08, severity: Math.min(1, 0.45 + Math.abs(change) * 2.5), direction: Math.sign(change) };
  }
  if (id === 'ICSA') {
    const mean = values.slice(1, 5).reduce((s, x) => s + x.value, 0) / Math.max(1, values.slice(1, 5).length);
    const change = mean > 0 ? latest / mean - 1 : 0;
    return { triggered: change >= 0.15, severity: Math.min(1, 0.45 + change * 1.8) };
  }
  return { triggered: false, severity: 0 };
}

async function forecastSeries(seriesId, points, frequency) {
  if (!config.forecastApiKey || points.length < 12) return null;
  const memo = forecastMemo.get(seriesId);
  if (memo && Date.now() - memo.at < DAY) return memo.value;
  const data = [...points].reverse().slice(-60).map(p => ({ date: p.date, value: p.value }));
  try {
    const payload = await fetchJson(ENDPOINTS.forecast, {
      method: 'POST',
      headers: { authorization: `Bearer ${config.forecastApiKey}`, 'content-type': 'application/json' },
      body: JSON.stringify({ identifier: `evidence-${seriesId}`, data, periods: 4, frequency, data_type: 'revenue', confidence_level: 0.8, selection_metric: 'smape' })
    }, 25_000);
    const rows = payload?.result?.forecasts;
    if (!Array.isArray(rows) || !rows.length) return null;
    const last = rows.at(-1);
    const start = data.at(-1)?.value;
    const end = Number(last.forecast);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start === 0) return null;
    const value = {
      start, end, change: end / start - 1,
      lower: Number(last.lower), upper: Number(last.upper),
      best_model: payload?.result?.model_info?.best_model ?? null,
      validation_performed: Boolean(payload?.result?.model_info?.validation_performed)
    };
    forecastMemo.set(seriesId, { at: Date.now(), value });
    return value;
  } catch (error) {
    const value = { error: error.message };
    forecastMemo.set(seriesId, { at: Date.now(), value });
    return value;
  }
}

async function fred() {
  if (!config.fredApiKey) return [];
  const seriesRows = await Promise.all(Object.entries(FRED_SERIES).map(async ([id, spec]) => {
    const url = new URL(ENDPOINTS.fred);
    url.searchParams.set('series_id', id);
    url.searchParams.set('api_key', config.fredApiKey);
    url.searchParams.set('file_type', 'json');
    url.searchParams.set('sort_order', 'desc');
    url.searchParams.set('limit', '60');
    const payload = await fetchJson(url);
    const points = (payload.observations ?? []).flatMap(x => {
      const v = Number(x.value);
      return Number.isFinite(v) ? [{ date: x.date, value: v }] : [];
    });
    if (points.length < 6) return [];
    const trigger = fredTrigger(id, points);
    const projected = trigger.triggered ? await forecastSeries(id, points, spec.frequency) : null;
    if (!trigger.triggered && !(projected && !projected.error && Math.abs(projected.change) >= 0.06)) return [];
    const latest = points[0];
    const direction = projected && !projected.error ? Math.sign(projected.change) : trigger.direction ?? 1;
    const type = id === 'DCOILWTICO' && direction < 0 ? 'energy_price_relief' : spec.type;
    return [signal(SOURCE_META.fred, {
      external_key: `fred:${id}:${latest.date}:${latest.value}`,
      event_type: type,
      title: `FRED · ${spec.label} — signal de trajectoire`,
      geography: 'États-Unis / Monde',
      event_at: `${latest.date}T00:00:00Z`,
      severity: trigger.severity || Math.min(0.8, 0.45 + Math.abs(projected?.change ?? 0)),
      url: `https://fred.stlouisfed.org/series/${id}`,
      facts: { series_id: id, latest_value: latest.value, recent_values: points.slice(0, 6), statistical_projection: projected && !projected.error ? projected : null }
    })];
  }));
  return seriesRows.flat();
}

async function gdeltQuery(spec) {
  const url = new URL(ENDPOINTS.gdelt);
  url.searchParams.set('query', spec.query);
  url.searchParams.set('mode', 'ArtList');
  url.searchParams.set('format', 'json');
  url.searchParams.set('maxrecords', '50');
  url.searchParams.set('timespan', '6h');
  url.searchParams.set('sort', 'DateDesc');
  const payload = await fetchJson(url, {}, 20_000);
  const articles = payload?.articles ?? [];
  if (!Array.isArray(articles) || articles.length < 7) return [];
  const domains = new Set(articles.map(a => a.domain).filter(Boolean));
  if (domains.size < 4) return [];
  return [signal(SOURCE_META.gdelt, {
    external_key: `gdelt:${spec.type}:${new Date().toISOString().slice(0, 13)}`,
    event_type: spec.type,
    title: `Convergence médiatique : ${spec.label}`,
    geography: 'Monde',
    event_at: new Date().toISOString(),
    severity: Math.min(0.78, 0.38 + articles.length / 120 + domains.size / 100),
    url: articles[0]?.url ?? '',
    facts: { article_count: articles.length, domain_count: domains.size, sample_titles: articles.slice(0, 5).map(a => text(a.title)) }
  })];
}

async function gdelt() {
  const results = await Promise.allSettled(GDELT_QUERIES.map(gdeltQuery));
  return results.flatMap(r => r.status === 'fulfilled' ? r.value : []);
}

export async function collectWorldSignals() {
  const adapters = { usgs, noaa, eonet, who, copernicus, fred, gdelt };
  const started = Date.now();
  const settled = await Promise.all(Object.entries(adapters).map(async ([name, fn]) => {
    try {
      return { name, ok: true, signals: await fn() };
    } catch (error) {
      return { name, ok: false, signals: [], error: String(error?.message ?? error).slice(0, 240) };
    }
  }));
  const signals = [];
  const source_status = [];
  for (const result of settled) {
    signals.push(...result.signals);
    source_status.push(result.ok
      ? { source: result.name, ok: true, signals: result.signals.length }
      : { source: result.name, ok: false, error: result.error });
  }
  return {
    signals,
    source_status,
    duration_ms: Date.now() - started,
    providers_configured: {
      fred: Boolean(config.fredApiKey), forecastapi: Boolean(config.forecastApiKey),
      windy_configured_not_used_as_production_evidence: Boolean(config.windyApiKey),
      copernicus_public: true, metaculus_reference_only: Boolean(config.metaculusApiKey), point_reference_only: Boolean(config.pointApiKey)
    }
  };
}
