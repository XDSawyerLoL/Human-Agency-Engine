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

function publicStatus() {
  return {
    schema: 'quantic-mairaiy-voice-proxy-v1',
    configured: Boolean(
      normalizeMairaiyUpstream(config.mairaiyVoice.upstreamUrl)
      && config.mairaiyVoice.proxyToken
      && config.mairaiyVoice.upstreamApiKey
    ),
    same_site_path: '/voice',
    provider: 'AURA Voice Fabric / Mairaiy speech backend',
  };
}

export function installMairaiyVoiceProxy(app) {
  app.get('/voice/status', (_req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.json(publicStatus());
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
