import { timingSafeEqual } from 'node:crypto';
import { Readable } from 'node:stream';
import { config } from './config.js';

const ALLOWED = new Set([
  'GET /health',
  'GET /.well-known/voicestudio-speech',
  'GET /v1/audio/voices',
  'GET /v1/models',
  'POST /v1/audio/speech',
]);

function equalSecret(actual, expected) {
  if (!actual || !expected) return false;
  const a = Buffer.from(String(actual));
  const b = Buffer.from(String(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}

function bearer(req) {
  const header = String(req.headers.authorization || '');
  return header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : '';
}

export function normalizeMairaiyUpstream(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    url.pathname = url.pathname.replace(/\/+$/, '');
    url.search = '';
    url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch {
    return null;
  }
}

async function publicStatus() {
  const upstreamBase = normalizeMairaiyUpstream(config.mairaiyVoice.upstreamUrl);
  const configured = Boolean(
    upstreamBase
    && config.mairaiyVoice.proxyToken
    && config.mairaiyVoice.upstreamApiKey
  );
  const base = {
    schema: 'quantic-mairaiy-voice-proxy-v2',
    configured,
    same_site_path: '/voice',
    provider: 'AURA Voice Fabric / Mairaiy speech backend',
    upstream_reachable: false,
    upstream_http_status: 0,
    engine: '',
    voice: '',
    language: '',
    service: '',
    identity_locked: false,
    model_ready: null,
    state: configured ? 'probing' : 'not-configured',
  };

  if (!configured) return base;

  try {
    const response = await fetch(`${upstreamBase}/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${config.mairaiyVoice.upstreamApiKey}`,
      },
      redirect: 'error',
      signal: AbortSignal.timeout(Math.min(config.mairaiyVoice.timeoutMs, 7000)),
    });

    let health = {};
    try {
      health = await response.json();
    } catch {}

    return {
      ...base,
      upstream_reachable: response.ok,
      upstream_http_status: response.status,
      engine: String(health?.engine || ''),
      voice: String(health?.voice || ''),
      language: String(health?.language || ''),
      service: String(health?.service || ''),
      identity_locked: health?.identity_locked === true,
      model_ready: typeof health?.model_ready === 'boolean' ? health.model_ready : null,
      state: response.ok ? 'ready' : 'upstream-error',
    };
  } catch (error) {
    const timedOut = error?.name === 'AbortError' || error?.name === 'TimeoutError';
    return {
      ...base,
      state: timedOut ? 'timeout' : 'unreachable',
    };
  }
}

export function installMairaiyVoiceProxy(app) {
  app.get('/voice/status', async (_req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.json(await publicStatus());
  });

  app.use('/voice', async (req, res) => {
    const upstreamBase = normalizeMairaiyUpstream(config.mairaiyVoice.upstreamUrl);
    if (!upstreamBase || !config.mairaiyVoice.proxyToken || !config.mairaiyVoice.upstreamApiKey) {
      return res.status(503).json({
        error: 'Mairaiy voice backend is not configured',
        code: 'MAIRAIY_VOICE_NOT_CONFIGURED',
      });
    }

    if (!equalSecret(bearer(req), config.mairaiyVoice.proxyToken)) {
      return res.status(401).json({ error: 'Mairaiy proxy token invalid' });
    }

    const path = req.path || '/';
    const signature = `${String(req.method || 'GET').toUpperCase()} ${path}`;
    if (!ALLOWED.has(signature)) {
      return res.status(404).json({ error: 'Voice route not exposed' });
    }

    const upstreamUrl = `${upstreamBase}${path}`;
    const headers = {
      Accept: String(req.headers.accept || '*/*'),
      Authorization: `Bearer ${config.mairaiyVoice.upstreamApiKey}`,
    };
    const init = {
      method: req.method,
      headers,
      redirect: 'error',
      signal: AbortSignal.timeout(config.mairaiyVoice.timeoutMs),
    };

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(req.body || {});
    }

    let upstream;
    try {
      upstream = await fetch(upstreamUrl, init);
    } catch (error) {
      const timedOut = error?.name === 'AbortError' || error?.name === 'TimeoutError';
      return res.status(timedOut ? 504 : 502).json({
        error: timedOut ? 'Mairaiy voice backend timeout' : 'Mairaiy voice backend unreachable',
        code: timedOut ? 'MAIRAIY_VOICE_TIMEOUT' : 'MAIRAIY_VOICE_UPSTREAM_UNREACHABLE',
      });
    }

    res.status(upstream.status);
    for (const name of [
      'content-type',
      'content-length',
      'retry-after',
      'x-voicestudio-routing',
      'x-voicestudio-routing-reason',
    ]) {
      const value = upstream.headers.get(name);
      if (value) res.setHeader(name, value);
    }
    res.setHeader('Cache-Control', 'no-store');

    if (!upstream.body) return res.end();
    Readable.fromWeb(upstream.body).pipe(res);
  });
}
