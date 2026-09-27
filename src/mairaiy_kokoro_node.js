import { config } from './config.js';

const MODEL_ID = 'onnx-community/Kokoro-82M-v1.0-ONNX';
const MODEL_REVISION = '1939ad2a8e416c0acfeecc08a694d14ef25f2231';
const SAMPLE_RATE = 24000;
const STYLE_DIM = 256;
const VOICE = 'ff_siwis';
const LANGUAGE = 'fr-fr';

let runtimePromise = null;
let voicePromise = null;
let synthQueue = Promise.resolve();
let ready = false;
let lastError = '';
let lastGenerationMs = 0;
let generatedCount = 0;
let modelLoadedAt = '';
const rateWindows = new Map();
let dailyWindow = { day: '', count: 0 };

function cleanText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, 4096);
}

function splitText(value, limit = 430) {
  const text = cleanText(value);
  if (!text) return [];
  const sentences = text.match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g) || [text];
  const chunks = [];
  let current = '';
  for (const raw of sentences) {
    const sentence = raw.trim();
    if (!sentence) continue;
    const candidate = current ? `${current} ${sentence}` : sentence;
    if (candidate.length <= limit) {
      current = candidate;
      continue;
    }
    if (current) chunks.push(current);
    current = '';
    if (sentence.length <= limit) {
      current = sentence;
      continue;
    }
    let part = '';
    for (const word of sentence.split(/\s+/)) {
      const next = part ? `${part} ${word}` : word;
      if (next.length <= limit) part = next;
      else {
        if (part) chunks.push(part);
        part = word;
      }
    }
    if (part) current = part;
  }
  if (current) chunks.push(current);
  return chunks;
}

function wavFromFloat32(samples, sampleRate = SAMPLE_RATE) {
  const dataBytes = samples.length * 2;
  const out = Buffer.allocUnsafe(44 + dataBytes);
  out.write('RIFF', 0, 4, 'ascii');
  out.writeUInt32LE(36 + dataBytes, 4);
  out.write('WAVE', 8, 4, 'ascii');
  out.write('fmt ', 12, 4, 'ascii');
  out.writeUInt32LE(16, 16);
  out.writeUInt16LE(1, 20);
  out.writeUInt16LE(1, 22);
  out.writeUInt32LE(sampleRate, 24);
  out.writeUInt32LE(sampleRate * 2, 28);
  out.writeUInt16LE(2, 32);
  out.writeUInt16LE(16, 34);
  out.write('data', 36, 4, 'ascii');
  out.writeUInt32LE(dataBytes, 40);
  for (let i = 0; i < samples.length; i += 1) {
    const x = Math.max(-1, Math.min(1, Number(samples[i] || 0)));
    out.writeInt16LE(Math.round(x < 0 ? x * 32768 : x * 32767), 44 + i * 2);
  }
  return out;
}

function concatenateFloat32(parts, silenceSamples = 2400) {
  if (parts.length === 1) return parts[0];
  const total = parts.reduce((sum, part) => sum + part.length, 0)
    + Math.max(0, parts.length - 1) * silenceSamples;
  const out = new Float32Array(total);
  let offset = 0;
  for (let i = 0; i < parts.length; i += 1) {
    out.set(parts[i], offset);
    offset += parts[i].length;
    if (i < parts.length - 1) offset += silenceSamples;
  }
  return out;
}

async function phonemizeFrench(text) {
  const { phonemize } = await import('phonemizer');
  const raw = await phonemize(text, LANGUAGE);
  const value = Array.isArray(raw) ? raw.join(' ') : String(raw || '');
  return value
    .replace(/ʲ/g, 'j')
    .replace(/x/g, 'k')
    .replace(/ɬ/g, 'l')
    .replace(/\s+/g, ' ')
    .trim();
}

async function loadVoice() {
  if (voicePromise) return voicePromise;
  voicePromise = (async () => {
    const url = `https://huggingface.co/${MODEL_ID}/resolve/${MODEL_REVISION}/voices/${VOICE}.bin`;
    const response = await fetch(url, {
      headers: { 'User-Agent': 'Quantic-Mairaiy/1.0' },
      redirect: 'follow',
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error(`Mairaiy voice asset HTTP ${response.status}`);
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength < STYLE_DIM * 4) throw new Error('Mairaiy voice asset is invalid');
    return new Float32Array(bytes);
  })().catch((error) => {
    voicePromise = null;
    throw error;
  });
  return voicePromise;
}

async function loadRuntime() {
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    const transformers = await import('@huggingface/transformers');
    const {
      StyleTextToSpeech2Model,
      AutoTokenizer,
      Tensor,
      env,
    } = transformers;

    if (env) {
      env.cacheDir = String(
        process.env.MAIRAIY_KOKORO_CACHE_DIR || '/tmp/quantic-mairaiy-kokoro',
      );
      env.allowRemoteModels = true;
    }

    const common = {
      revision: MODEL_REVISION,
      progress_callback: null,
    };
    const [model, tokenizer, voiceData] = await Promise.all([
      StyleTextToSpeech2Model.from_pretrained(MODEL_ID, {
        ...common,
        dtype: String(process.env.MAIRAIY_KOKORO_DTYPE || 'q8'),
        device: 'cpu',
      }),
      AutoTokenizer.from_pretrained(MODEL_ID, common),
      loadVoice(),
    ]);

    ready = true;
    modelLoadedAt = new Date().toISOString();
    lastError = '';
    return { model, tokenizer, voiceData, Tensor };
  })().catch((error) => {
    runtimePromise = null;
    ready = false;
    lastError = String(error?.message || error).slice(0, 500);
    throw error;
  });
  return runtimePromise;
}

async function synthChunk(text, speed) {
  const { model, tokenizer, voiceData, Tensor } = await loadRuntime();
  const phonemes = await phonemizeFrench(text);
  if (!phonemes) throw new Error('Mairaiy French phonemizer returned no phonemes');
  const { input_ids } = tokenizer(phonemes, { truncation: true });
  const numTokens = Math.min(Math.max(Number(input_ids?.dims?.at(-1) || 0) - 2, 0), 509);
  const offset = numTokens * STYLE_DIM;
  if (offset + STYLE_DIM > voiceData.length) {
    throw new Error('Mairaiy voice style vector is too short');
  }
  const style = voiceData.slice(offset, offset + STYLE_DIM);
  const inputs = {
    input_ids,
    style: new Tensor('float32', style, [1, STYLE_DIM]),
    speed: new Tensor('float32', [speed], [1]),
  };
  const output = await model(inputs);
  const waveform = output?.waveform?.data;
  if (!waveform?.length) throw new Error('Kokoro returned empty audio');
  return new Float32Array(waveform);
}

function dayKey() {
  return new Date().toISOString().slice(0, 10);
}

export function consumeMairaiyQuota(clientKey = 'anonymous') {
  const now = Date.now();
  const minuteLimit = Number(config.mairaiyVoice?.publicRequestsPerMinute || 6);
  const dailyLimit = Number(config.mairaiyVoice?.publicRequestsPerDay || 240);

  const today = dayKey();
  if (dailyWindow.day !== today) dailyWindow = { day: today, count: 0 };
  if (dailyWindow.count >= dailyLimit) {
    return { ok: false, retry_after_seconds: 3600, reason: 'daily-cap' };
  }

  const key = String(clientKey || 'anonymous').slice(0, 160);
  const list = (rateWindows.get(key) || []).filter((stamp) => now - stamp < 60000);
  if (list.length >= minuteLimit) {
    const retry = Math.max(1, Math.ceil((60000 - (now - list[0])) / 1000));
    rateWindows.set(key, list);
    return { ok: false, retry_after_seconds: retry, reason: 'rate-limit' };
  }

  list.push(now);
  rateWindows.set(key, list);
  dailyWindow.count += 1;
  return { ok: true, retry_after_seconds: 0, reason: '' };
}

export async function synthesizeMairaiyNode(text, options = {}) {
  const clean = cleanText(text);
  if (!clean) throw new Error('Texte vocal vide');
  const speed = Math.max(0.72, Math.min(1.35, Number(options.speed || 1)));

  const run = async () => {
    const started = Date.now();
    const parts = [];
    for (const chunk of splitText(clean)) {
      parts.push(await synthChunk(chunk, speed));
    }
    const samples = concatenateFloat32(parts);
    const wav = wavFromFloat32(samples);
    lastGenerationMs = Date.now() - started;
    generatedCount += 1;
    lastError = '';
    return {
      buffer: wav,
      mime_type: 'audio/wav',
      engine: 'kokoro-onnx-node',
      voice: VOICE,
      language: LANGUAGE,
      generation_ms: lastGenerationMs,
      chars: clean.length,
    };
  };

  const promise = synthQueue.then(run, run);
  synthQueue = promise.catch(() => {});
  try {
    return await promise;
  } catch (error) {
    lastError = String(error?.message || error).slice(0, 500);
    throw error;
  }
}

export function mairaiyNodeStatus() {
  return {
    enabled: config.mairaiyVoice?.nodeNativeEnabled !== false,
    ready,
    model_ready: ready,
    state: ready ? 'ready' : (lastError ? 'error' : 'idle'),
    engine: 'kokoro-onnx-node',
    voice: VOICE,
    language: LANGUAGE,
    service: 'mairaiy-kokoro-node',
    identity_locked: true,
    model_id: MODEL_ID,
    model_revision: MODEL_REVISION,
    dtype: String(process.env.MAIRAIY_KOKORO_DTYPE || 'q8'),
    model_loaded_at: modelLoadedAt,
    generated_count: generatedCount,
    last_generation_ms: lastGenerationMs,
    last_error: lastError,
    zero_api_cost: true,
  };
}
