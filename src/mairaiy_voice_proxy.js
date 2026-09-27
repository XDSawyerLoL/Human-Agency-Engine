import { timingSafeEqual } from 'node:crypto';
import { Readable } from 'node:stream';
import { config } from './config.js';
import {
  consumeMairaiyQuota,
  mairaiyNodeStatus,
  synthesizeMairaiyNode,
} from './mairaiy_kokoro_node.js';

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

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'authorization, content-type');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
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

function nativeDiscovery() {
  return {
    schema: 'voicestudio-speech-compatible-v1',
    provider: 'AURA Mairaiy Node',
    openai_compatible_base: '/voice/v1',
    tts: true,
    voices: '/voice/v1/audio/voices',
    models: '/voice/v1/models',
    speech: '/voice/v1/audio/speech',
    identity: 'Mairaiy',
    zero_api_cost: true,
  };
}

function nativeVoices() {
  return {
    voices: [{
      voice_id: 'mairaiy',
      name: 'Mairaiy',
      type: 'profile',
      language: 'fr',
      engine_voice: 'ff_siwis',
    }],
    engines: [{
      id: 'kokoro',
      name: 'Kokoro ONNX Node',
      cloning: false,
      device: 'cpu',
    }],
  };
}

function nativeModels() {
  return {
    object: 'list',
    data: [{
      id: 'kokoro',
      object: 'model',
      owned_by: 'aura',
      voice: 'ff_siwis',
    }],
  };
}

async function publicStatus() {
  const native = mairaiyNodeStatus();
  const upstreamBase = normalizeMairaiyUpstream(config.mairaiyVoice.upstreamUrl);
  const upstreamConfigured = Boolean(
    upstreamBase
    && config.mairaiyVoice.proxyToken
    && config.mairaiyVoice.upstreamApiKey
  );

  if (native.enabled) {
    return {
      schema: 'quantic-mairaiy-voice-proxy-v3',
      configured: true,
      same_site_path: '/voice',
      provider: 'AURA Voice Fabric / native Node Kokoro',
      mode: 'node-native',
      engine: native.engine,
      voice: native.voice,
      language: native.language,
      service: native.service,
      identity_locked: native.identity_locked,
      model_ready: native.model_ready,
      state: native.state,
      generated_count: native.generated_count,
      last_generation_ms: native.last_generation_ms,
      last_error: native.last_error,
      zero_api_cost: true,
      public_speech_enabled: Boolean(config.mairaiyVoice.publicEnabled),
      upstream_configured: upstreamConfigured,
    };
  }

  const base = {
    schema: 'quantic-mairaiy-voice-proxy-v3',
    configured: upstreamConfigured,
    same_site_path: '/voice',
    provider: 'AURA Voice Fabric / Mairaiy speech backend',
    mode: 'upstream',
    upstream_reachable: false,
    upstream_http_status: 0,
    engine: '',
    voice: '',
    language: '',
    service: '',
    identity_locked: false,
    model_ready: null,
    state: upstreamConfigured ? 'probing' : 'not-configured',
    zero_api_cost: true,
  };
  if (!upstreamConfigured) return base;

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
    try { health = await response.json(); } catch {}
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
    return { ...base, state: timedOut ? 'timeout' : 'unreachable' };
  }
}

async function proxyUpstream(req, res, upstreamBase) {
  if (!equalSecret(bearer(req), config.mairaiyVoice.proxyToken)) {
    return res.status(401).json({ error: 'Mairaiy proxy token invalid' });
  }

  const path = req.path || '/';
  const signature = `${String(req.method || 'GET').toUpperCase()} ${path}`;
  if (!ALLOWED.has(signature)) {
    return res.status(404).json({ error: 'Voice route not exposed' });
  }

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
    upstream = await fetch(`${upstreamBase}${path}`, init);
  } catch (error) {
    const timedOut = error?.name === 'AbortError' || error?.name === 'TimeoutError';
    return res.status(timedOut ? 504 : 502).json({
      error: timedOut ? 'Mairaiy voice backend timeout' : 'Mairaiy voice backend unreachable',
      code: timedOut ? 'MAIRAIY_VOICE_TIMEOUT' : 'MAIRAIY_VOICE_UPSTREAM_UNREACHABLE',
    });
  }

  res.status(upstream.status);
  for (const name of ['content-type','content-length','retry-after']) {
    const value = upstream.headers.get(name);
    if (value) res.setHeader(name, value);
  }
  res.setHeader('Cache-Control', 'no-store');
  if (!upstream.body) return res.end();
  Readable.fromWeb(upstream.body).pipe(res);
}

export function installMairaiyVoiceProxy(app) {
  app.get('/voice/status', async (_req, res) => {
    cors(res);
    res.json(await publicStatus());
  });

  app.use('/voice', async (req, res) => {
    cors(res);
    if (req.method === 'OPTIONS') return res.status(204).end();

    const path = req.path || '/';
    const signature = `${String(req.method || 'GET').toUpperCase()} ${path}`;

    if (config.mairaiyVoice.nodeNativeEnabled) {
      if (signature === 'GET /health') {
        return res.json({ status: 'ok', ...mairaiyNodeStatus() });
      }
      if (signature === 'GET /.well-known/voicestudio-speech') {
        return res.json(nativeDiscovery());
      }
      if (signature === 'GET /v1/audio/voices') {
        return res.json(nativeVoices());
      }
      if (signature === 'GET /v1/models') {
        return res.json(nativeModels());
      }
      if (signature === 'POST /v1/audio/speech') {
        if (!config.mairaiyVoice.publicEnabled) {
          if (!config.mairaiyVoice.proxyToken || !equalSecret(bearer(req), config.mairaiyVoice.proxyToken)) {
            return res.status(401).json({ error: 'Mairaiy voice token invalid' });
          }
        } else {
          const quota = consumeMairaiyQuota(req.ip || req.socket?.remoteAddress || 'anonymous');
          if (!quota.ok) {
            res.setHeader('Retry-After', String(quota.retry_after_seconds));
            return res.status(429).json({
              error: 'Mairaiy voice capacity limit reached',
              code: 'MAIRAIY_RATE_LIMIT',
              reason: quota.reason,
              retry_after_seconds: quota.retry_after_seconds,
            });
          }
        }

        const text = String(req.body?.input || req.body?.text || '').trim();
        if (!text) return res.status(422).json({ error: 'Texte vocal vide' });
        const model = String(req.body?.model || 'kokoro').toLowerCase();
        if (!['kokoro','tts-1','tts-1-hd','omnivoice','omnivoice-gguf'].includes(model)) {
          return res.status(400).json({ error: `Unsupported voice model: ${model}` });
        }

        try {
          const audio = await synthesizeMairaiyNode(text, {
            speed: Number(req.body?.speed || 1),
          });
          res.setHeader('Content-Type', audio.mime_type);
          res.setHeader('X-Mairaiy-Engine', audio.engine);
          res.setHeader('X-Mairaiy-Voice', audio.voice);
          return res.status(200).send(audio.buffer);
        } catch (error) {
          const upstreamBase = normalizeMairaiyUpstream(config.mairaiyVoice.upstreamUrl);
          if (upstreamBase && config.mairaiyVoice.proxyToken && config.mairaiyVoice.upstreamApiKey) {
            return proxyUpstream(req, res, upstreamBase);
          }
          return res.status(503).json({
            error: String(error?.message || error).slice(0, 500),
            code: 'MAIRAIY_NODE_TTS_UNAVAILABLE',
            diagnostic: mairaiyNodeStatus(),
          });
        }
      }

      return res.status(404).json({ error: 'Voice route not exposed' });
    }

    const upstreamBase = normalizeMairaiyUpstream(config.mairaiyVoice.upstreamUrl);
    if (!upstreamBase || !config.mairaiyVoice.proxyToken || !config.mairaiyVoice.upstreamApiKey) {
      return res.status(503).json({
        error: 'Mairaiy voice backend is not configured',
        code: 'MAIRAIY_VOICE_NOT_CONFIGURED',
      });
    }
    return proxyUpstream(req, res, upstreamBase);
  });
}
