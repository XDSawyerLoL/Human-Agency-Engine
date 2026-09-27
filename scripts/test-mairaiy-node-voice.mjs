import assert from 'node:assert/strict';
import { mairaiyNodeStatus, synthesizeMairaiyNode } from '../src/mairaiy_kokoro_node.js';

process.env.MAIRAIY_KOKORO_DTYPE = process.env.MAIRAIY_KOKORO_DTYPE || 'q4';
process.env.MAIRAIY_KOKORO_CACHE_DIR = process.env.MAIRAIY_KOKORO_CACHE_DIR || '/tmp/quantic-mairaiy-ci';

const result = await synthesizeMairaiyNode('Bonjour. Je suis Mairaiy, la voix d’AURA.', { speed: 1 });
assert.equal(result.mime_type, 'audio/wav');
assert.equal(result.engine, 'kokoro-onnx-node');
assert.equal(result.voice, 'ff_siwis');
assert.equal(result.language, 'fr-fr');
assert.ok(Buffer.isBuffer(result.buffer));
assert.ok(result.buffer.length > 1000, `WAV too small: ${result.buffer.length}`);
assert.equal(result.buffer.subarray(0, 4).toString('ascii'), 'RIFF');
assert.equal(result.buffer.subarray(8, 12).toString('ascii'), 'WAVE');

const status = mairaiyNodeStatus();
assert.equal(status.ready, true);
assert.equal(status.model_ready, true);
assert.equal(status.identity_locked, true);
assert.equal(status.zero_api_cost, true);
assert.equal(status.voice, 'ff_siwis');

console.log(JSON.stringify({
  ok: true,
  engine: result.engine,
  voice: result.voice,
  language: result.language,
  bytes: result.buffer.length,
  generation_ms: result.generation_ms,
  model_ready: status.model_ready,
}));
